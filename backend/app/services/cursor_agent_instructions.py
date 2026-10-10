"""Copy-paste Ubuntu instruction blocks extracted from cursor_agent_tool."""

from __future__ import annotations

from typing import Any

from app.http_limits import redact_secrets


def _cursor_api_error_detail(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            if message:
                return message
        message = str(body.get("message") or "").strip()
        if message:
            return message
    return redact_secrets(str(body))[:400]


def push_workflow_for_user(
    *,
    agent_url: str | None,
    repo_slug: str | None = None,
    starting_branch: str = "main",
    auto_create_pr: bool = False,
) -> str:
    """Copy-paste Ubuntu steps — Cloud Agents use cursor/* branches, not local main."""
    from app.services import cursor_agent_transport

    slug = (repo_slug or cursor_agent_transport._repo_slug()).strip().strip("/")
    repo_https = f"https://github.com/{slug}.git"
    agent_line = agent_url or "(agent URL from above)"
    pr_note = (
        "An open PR to main will be created when the agent finishes — merge it on GitHub, then deploy."
        if auto_create_pr
        else "On GitHub → Branches, find the new cursor/… branch the agent pushed."
    )
    return (
        "Push to main (Ubuntu) — Cloud Agents commit on cursor/*, not your local main:\n\n"
        f"Easiest: open {agent_line} → **Open in Cursor** → review → push (or merge the PR).\n\n"
        "Existing clone in Cursor terminal. Abort a stuck merge first, then match GitHub main:\n"
        "```bash\n"
        "cd ~/Storykeep\n"
        "git merge --abort\n"
        f"git remote add github {repo_https} 2>/dev/null || true\n"
        "git fetch github\n"
        f"git checkout {starting_branch}\n"
        f"git reset --hard github/{starting_branch}\n"
        "```\n"
        f"{pr_note}\n"
        "Then in Junior: Show GitHub status, then deploy Storykeep."
    )


def merge_commands(branch: str, *, starting_branch: str = "main", repo_slug: str | None = None) -> str:
    from app.services import cursor_agent_transport

    slug = (repo_slug or cursor_agent_transport._repo_slug()).strip().strip("/")
    base = (starting_branch or "main").strip() or "main"
    remote = branch.strip()
    return (
        "```bash\n"
        "cd ~/Storykeep\n"
        "git merge --abort\n"
        f"git remote add github https://github.com/{slug}.git 2>/dev/null || true\n"
        "git fetch github\n"
        f"git checkout {base}\n"
        f"git reset --hard github/{base}\n"
        f"git merge --ff-only github/{remote}\n"
        f"git push github {base}\n"
        "```"
    )
