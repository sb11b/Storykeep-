from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import redact_secrets
from app.services.demo_lock import is_locked

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
TIMEOUT_SEC = 25.0

STATUS_TOOL_NAME = "railway_status"
DEPLOY_TOOL_NAME = "railway_deploy"

RAILWAY_ON_APPEND = """
You have live Railway access for Storykeep (Steve's deploy host).
- For deploy status, latest deployment, build stamp, or "what's on production", call railway_status or use the attached snapshot.
- When Steve asks to deploy, redeploy, or push Storykeep to Railway, call railway_deploy after confirming intent in your reply.
- Report deployment status, commit/build id, and URL when known. Never invent deploy outcomes.
- Tokens stay server-side; never echo API keys.
"""

RAILWAY_OFF_APPEND = """
Railway tools exist (railway_status, railway_deploy) but RAILWAY_API_TOKEN is not set on the Storykeep Railway service yet.
Tell Steve to add the token value in Railway → storykeep service → Variables — never paste secrets into chat.
Once set, call railway_status or railway_deploy when he asks about deploys.
Do not say the only tool is web_search; you also have calendar/mail/chats when connected.
"""

_DEPLOY_RE = re.compile(
    r"\b(?:deploy(?:\s+to|\s+on|\s+it|\s+storykeep|\s+now)?|"
    r"redeploy|push(?:\s+to|\s+live|\s+prod)?|"
    r"railway(?:\s+up|\s+deploy)?|"
    r"ship(?:\s+it|\s+to\s+prod)?|"
    r"production(?:\s+deploy|\s+build)?)\b",
    re.I,
)
_STATUS_RE = re.compile(
    r"\b(?:railway|deploy(?:ment)?(?:\s+status)?|"
    r"production(?:\s+build|\s+status|\s+url)?|"
    r"what(?:'s|\s+is)\s+(?:on|in)\s+prod|"
    r"build(?:\s+stamp|\s+info)?|"
    r"latest(?:\s+deploy|\s+deployment)?|"
    r"storykeep(?:\s+production|\s+deploy)?)\b",
    re.I,
)
_SETUP_RE = re.compile(
    r"\b(?:RAILWAY_API_TOKEN|RAILWAY_TOKEN|railway\s+(?:api\s+)?token|"
    r"railway\s+variables?|service\s+variables?)\b",
    re.I,
)

RAILWAY_STATUS_TOOL = {
    "type": "function",
    "function": {
        "name": STATUS_TOOL_NAME,
        "description": (
            "Fetch Storykeep Railway deployment status: service, environment, latest deployment, "
            "status, created time, and public URL when available."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

RAILWAY_DEPLOY_TOOL = {
    "type": "function",
    "function": {
        "name": DEPLOY_TOOL_NAME,
        "description": (
            "Trigger a new Storykeep deployment on Railway (serviceInstanceDeployV2). "
            "Use only when Steve explicitly asks to deploy or redeploy Storykeep."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


@dataclass(frozen=True)
class RailwayTarget:
    project_id: str
    project_name: str
    service_id: str
    service_name: str
    environment_id: str
    environment_name: str


@dataclass(frozen=True)
class RailwayOutcome:
    ok: bool
    text: str
    status_code: int = 200


def _token() -> str:
    return (settings.railway_api_token or settings.railway_token or "").strip()


def configured() -> bool:
    return bool(_token())


def owner_can_use(user: object | None) -> bool:
    return configured() and not is_locked(user)


def reject_demo(user: object) -> None:
    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Railway is not enabled on this account")


def wants_railway_status(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_STATUS_RE.search(text))


def wants_railway_deploy(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_DEPLOY_RE.search(text))


def wants_railway_setup(message: str) -> bool:
    return bool(_SETUP_RE.search(message or ""))


def wants_railway(message: str) -> bool:
    return wants_railway_status(message) or wants_railway_deploy(message) or wants_railway_setup(message)


def is_railway_tool(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    fn = item.get("function") if isinstance(item.get("function"), dict) else {}
    name = str(fn.get("name") or item.get("name") or "").strip()
    return name in {STATUS_TOOL_NAME, DEPLOY_TOOL_NAME}


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"errors": [{"message": "Railway token not configured"}]}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.post(GRAPHQL_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        return {"errors": [{"message": "Railway API timeout"}]}
    except httpx.HTTPError as exc:
        return {"errors": [{"message": f"Railway transport error: {exc}"}]}
    if response.status_code >= 400:
        return {"errors": [{"message": f"HTTP {response.status_code}: {response.text[:200]}"}]}
    try:
        body = response.json()
    except json.JSONDecodeError:
        return {"errors": [{"message": "Railway returned non-JSON"}]}
    return body if isinstance(body, dict) else {"errors": [{"message": "Invalid Railway response"}]}


def _pick_environment(environments: list[dict[str, str]]) -> dict[str, str] | None:
    if not environments:
        return None
    preferred = (settings.railway_environment_name or "production").strip().lower()
    for row in environments:
        if (row.get("name") or "").strip().lower() == preferred:
            return row
    for row in environments:
        if (row.get("name") or "").strip().lower() == "production":
            return row
    return environments[0]


def _pick_service(services: list[dict[str, str]]) -> dict[str, str] | None:
    if not services:
        return None
    if settings.railway_service_id:
        for row in services:
            if row.get("id") == settings.railway_service_id:
                return row
    preferred = (settings.railway_service_name or "storykeep").strip().lower()
    for row in services:
        if (row.get("name") or "").strip().lower() == preferred:
            return row
    return services[0]


def resolve_target() -> RailwayTarget | None:
    if settings.railway_project_id and settings.railway_service_id and settings.railway_environment_id:
        return RailwayTarget(
            project_id=settings.railway_project_id,
            project_name=settings.railway_project_name or "Storykeep",
            service_id=settings.railway_service_id,
            service_name=settings.railway_service_name or "storykeep",
            environment_id=settings.railway_environment_id,
            environment_name=settings.railway_environment_name or "production",
        )
    query = """
    query Projects {
      projects {
        edges {
          node {
            id
            name
            environments {
              edges {
                node { id name }
              }
            }
            services {
              edges {
                node { id name }
              }
            }
          }
        }
      }
    }
    """
    body = _graphql(query)
    errors = body.get("errors")
    if errors:
        logger.warning("Railway resolve failed: %s", redact_secrets(str(errors)))
        return None
    projects = (((body.get("data") or {}).get("projects") or {}).get("edges")) or []
    rows: list[dict[str, Any]] = []
    for edge in projects:
        node = edge.get("node") if isinstance(edge, dict) else None
        if isinstance(node, dict):
            rows.append(node)
    if not rows:
        return None
    project = rows[0]
    if settings.railway_project_id:
        for row in rows:
            if row.get("id") == settings.railway_project_id:
                project = row
                break
    else:
        needle = (settings.railway_project_name or "storykeep").strip().lower()
        for row in rows:
            if needle in str(row.get("name") or "").lower():
                project = row
                break
    environments = [
        {"id": env_node.get("id", ""), "name": env_node.get("name", "")}
        for env_edge in ((project.get("environments") or {}).get("edges") or [])
        if isinstance(env_edge, dict)
        for env_node in [env_edge.get("node")]
        if isinstance(env_node, dict) and env_node.get("id")
    ]
    services = [
        {"id": svc_node.get("id", ""), "name": svc_node.get("name", "")}
        for svc_edge in ((project.get("services") or {}).get("edges") or [])
        if isinstance(svc_edge, dict)
        for svc_node in [svc_edge.get("node")]
        if isinstance(svc_node, dict) and svc_node.get("id")
    ]
    environment = _pick_environment(environments)
    service = _pick_service(services)
    if not environment or not service:
        return None
    return RailwayTarget(
        project_id=str(project.get("id") or ""),
        project_name=str(project.get("name") or "Storykeep"),
        service_id=str(service.get("id") or ""),
        service_name=str(service.get("name") or "storykeep"),
        environment_id=str(environment.get("id") or ""),
        environment_name=str(environment.get("name") or "production"),
    )


def fetch_status() -> RailwayOutcome:
    if not configured():
        return RailwayOutcome(False, RAILWAY_OFF_APPEND.strip(), 503)
    target = resolve_target()
    if target is None:
        return RailwayOutcome(False, "Could not resolve Railway project/service/environment.", 502)
    query = """
    query ServiceStatus($serviceId: String!, $environmentId: String!) {
      service(id: $serviceId) {
        id
        name
        serviceInstances {
          edges {
            node {
              domains {
                serviceDomain
              }
              latestDeployment {
                id
                status
                createdAt
                meta
              }
            }
          }
        }
      }
      environment(id: $environmentId) {
        id
        name
      }
    }
    """
    body = _graphql(
        query,
        {"serviceId": target.service_id, "environmentId": target.environment_id},
    )
    errors = body.get("errors")
    if errors:
        detail = redact_secrets(str(errors))[:300]
        return RailwayOutcome(False, f"Railway status failed: {detail}", 502)
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    service = data.get("service") if isinstance(data.get("service"), dict) else {}
    environment = data.get("environment") if isinstance(data.get("environment"), dict) else {}
    deployment: dict[str, Any] | None = None
    domain = ""
    for edge in ((service.get("serviceInstances") or {}).get("edges") or []):
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict):
            continue
        domains = node.get("domains") or []
        if isinstance(domains, list) and domains and isinstance(domains[0], dict):
            domain = str(domains[0].get("serviceDomain") or "")
        latest = node.get("latestDeployment")
        if isinstance(latest, dict):
            deployment = latest
            break
    public = f"https://{domain}" if domain else ""
    if not public and settings.railway_public_domain:
        public = f"https://{settings.railway_public_domain.strip()}"
    lines = [
        "Railway status snapshot (live):",
        f"- Project: {target.project_name} ({target.project_id})",
        f"- Service: {target.service_name} ({target.service_id})",
        f"- Environment: {environment.get('name') or target.environment_name} ({target.environment_id})",
    ]
    if public:
        lines.append(f"- URL: {public}")
    if deployment:
        meta = deployment.get("meta") if isinstance(deployment.get("meta"), dict) else {}
        commit = meta.get("commitMessage") or meta.get("commitSha") or meta.get("image")
        lines.extend(
            [
                f"- Latest deployment: {deployment.get('id')}",
                f"- Status: {deployment.get('status')}",
                f"- Created: {deployment.get('createdAt')}",
            ]
        )
        if commit:
            lines.append(f"- Build/commit: {commit}")
    else:
        lines.append("- Latest deployment: none found")
    return RailwayOutcome(True, "\n".join(lines), 200)


def deploy() -> RailwayOutcome:
    if not configured():
        return RailwayOutcome(False, RAILWAY_OFF_APPEND.strip(), 503)
    target = resolve_target()
    if target is None:
        return RailwayOutcome(False, "Could not resolve Railway project/service/environment.", 502)
    mutation = """
    mutation Deploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    body = _graphql(
        mutation,
        {"serviceId": target.service_id, "environmentId": target.environment_id},
    )
    errors = body.get("errors")
    if errors:
        detail = redact_secrets(str(errors))[:300]
        return RailwayOutcome(False, f"Railway deploy failed: {detail}", 502)
    deployment_id = ((body.get("data") or {}).get("serviceInstanceDeployV2")) if isinstance(body.get("data"), dict) else None
    if not deployment_id:
        return RailwayOutcome(False, "Railway deploy returned no deployment id.", 502)
    return RailwayOutcome(
        True,
        (
            f"Triggered Railway deploy for {target.service_name} in {target.environment_name}.\n"
            f"Deployment id: {deployment_id}\n"
            "Check Railway dashboard or ask for status in a minute."
        ),
        200,
    )


def format_status_for_model(outcome: RailwayOutcome) -> str:
    prefix = "Live Railway data for this turn:"
    if outcome.ok:
        return f"{prefix}\n{outcome.text}"
    return f"{prefix}\n{outcome.text}"


def assemble_tool_call(fragments: list[dict] | None) -> dict[str, str] | None:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        slot = buckets.setdefault(index, {"name": "", "arguments": ""})
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = fn.get("name") or item.get("name")
        if isinstance(name, str) and name:
            slot["name"] = name
    for slot in buckets.values():
        name = slot.get("name") or ""
        if name in {STATUS_TOOL_NAME, DEPLOY_TOOL_NAME}:
            return {"name": name}
    return None


def execute_tool_call(call: dict[str, str]) -> str:
    name = call.get("name")
    if name == STATUS_TOOL_NAME:
        return format_status_for_model(fetch_status())
    if name == DEPLOY_TOOL_NAME:
        outcome = deploy()
        prefix = "Railway deploy result:"
        return f"{prefix}\n{outcome.text}"
    return "Unknown Railway tool."
