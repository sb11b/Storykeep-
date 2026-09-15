from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx
from fastapi import HTTPException

from app.config import settings

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
NSMAP = {"D": DAV, "C": CALDAV}

DEFAULT_CALDAV = "https://caldav.fastmail.com"


def caldav_origin() -> str:
    raw = (getattr(settings, "fastmail_caldav_url", None) or "").strip()
    return (raw or DEFAULT_CALDAV).rstrip("/")


def _auth(email: str, token: str) -> httpx.BasicAuth:
    return httpx.BasicAuth(email.strip(), token)


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "StoryKeep-Calendar/1.0",
        "Accept": "application/xml, text/xml, text/calendar, */*",
    }
    if extra:
        headers.update(extra)
    return headers


def _abs(base: str, href: str | None) -> str:
    if not href:
        return base
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if href.startswith("/"):
        return urljoin(root + "/", href)
    return urljoin(base if base.endswith("/") else base + "/", href)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(parent: ET.Element, names: set[str]) -> str | None:
    for child in list(parent):
        if _local_name(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
            for nested in list(child):
                if _local_name(nested.tag) == "href" and nested.text:
                    return nested.text.strip()
    return None


def _find_hrefs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    found: list[str] = []
    for el in root.iter():
        if _local_name(el.tag) == "href" and el.text and el.text.strip():
            found.append(el.text.strip())
    return found


def _raise_fastmail(response: httpx.Response, *, connect: bool = False) -> None:
    if response.status_code in {401, 403}:
        detail = (
            "Fastmail did not accept that token. Use an app password or API token, not your account password."
            if connect
            else "Fastmail Calendar needs to be connected again."
        )
        raise HTTPException(status_code=401 if not connect else 400, detail=detail)
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="That Fastmail event is gone.")
    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="Fastmail Calendar is unavailable right now.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Fastmail Calendar request failed.")


def _request(
    method: str,
    url: str,
    *,
    email: str,
    token: str,
    headers: dict[str, str] | None = None,
    content: str | bytes | None = None,
    connect: bool = False,
) -> httpx.Response:
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True, auth=_auth(email, token)) as client:
            response = client.request(method, url, headers=_headers(headers), content=content)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Fastmail Calendar.") from exc
    if response.status_code >= 400:
        _raise_fastmail(response, connect=connect)
    return response


def encode_event_id(href: str) -> str:
    packed = base64.urlsafe_b64encode(href.encode("utf-8")).decode("ascii").rstrip("=")
    return f"fm-{packed}"


def decode_event_id(event_id: str) -> str | None:
    raw = (event_id or "").strip()
    if not raw.startswith("fm-"):
        return None
    payload = raw[3:]
    pad = "=" * ((4 - len(payload) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(payload + pad).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def unfold_ics(blob: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", blob.replace("\r\n", "\n"))


def _ics_unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def parse_ics_datetime(value: str, params: str = "") -> tuple[str, bool]:
    raw = (value or "").strip()
    all_day = "VALUE=DATE" in params.upper() or (len(raw) == 8 and "T" not in raw)
    if all_day and len(raw) >= 8:
        stamp = datetime.strptime(raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        return stamp.date().isoformat(), True
    if raw.endswith("Z"):
        stamp = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return stamp.isoformat(), False
    if "T" in raw:
        stamp = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        tzid = None
        match = re.search(r"TZID=([^;:]+)", params, re.I)
        if match:
            tzid = match.group(1).strip()
        if tzid:
            return f"{stamp.isoformat()}", False
        return stamp.replace(tzinfo=timezone.utc).isoformat(), False
    return raw, all_day


def parse_vevents(ics: str) -> list[dict[str, object]]:
    text = unfold_ics(ics or "")
    blocks = re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", text, flags=re.I | re.S)
    events: list[dict[str, object]] = []
    for block in blocks:
        fields: dict[str, tuple[str, str]] = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            key, _, params = name.partition(";")
            fields[key.upper()] = (params, value)
        start_params, start_raw = fields.get("DTSTART", ("", ""))
        end_params, end_raw = fields.get("DTEND", ("", ""))
        if not end_raw and start_raw:
            start_iso, all_day = parse_ics_datetime(start_raw, start_params)
            if all_day:
                end_iso, all_day = start_iso, True
            else:
                parsed = datetime.fromisoformat(start_iso)
                end_iso = (parsed + timedelta(hours=1)).isoformat()
        else:
            start_iso, all_day = parse_ics_datetime(start_raw, start_params)
            end_iso, end_all = parse_ics_datetime(end_raw, end_params)
            all_day = all_day or end_all
        title = _ics_unescape(fields.get("SUMMARY", ("", "(No title)"))[1] or "(No title)")
        uid = fields.get("UID", ("", ""))[1]
        events.append({"uid": uid, "title": title, "start": start_iso, "end": end_iso, "all_day": all_day})
    return events


def to_utc_ics(value: str) -> tuple[str, bool]:
    raw = (value or "").strip().replace("Z", "+00:00")
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        compact = raw.replace("-", "")
        return compact, True
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc = parsed.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ"), False


def time_range_ics(value: str) -> str:
    compact, all_day = to_utc_ics(value)
    if all_day:
        return compact + "T000000Z"
    return compact


def build_vevent(*, uid: str, title: str, start: str, end: str) -> str:
    start_ics, start_all = to_utc_ics(start)
    end_ics, end_all = to_utc_ics(end)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_line = f"DTSTART;VALUE=DATE:{start_ics}" if start_all else f"DTSTART:{start_ics}"
    end_line = f"DTEND;VALUE=DATE:{end_ics}" if end_all else f"DTEND:{end_ics}"
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//StoryKeep//Calendar//EN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            start_line,
            end_line,
            f"SUMMARY:{_ics_escape(title.strip())}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def calendar_query_xml(time_min: str, time_max: str) -> str:
    start = time_range_ics(time_min)
    end = time_range_ics(time_max)
    return (
        '<?xml version="1.0" encoding="utf-8" ?>'
        f'<C:calendar-query xmlns:D="{DAV}" xmlns:C="{CALDAV}">'
        "<D:prop><D:getetag/><C:calendar-data/></D:prop>"
        "<C:filter><C:comp-filter name=\"VCALENDAR\"><C:comp-filter name=\"VEVENT\">"
        f'<C:time-range start="{start}" end="{end}"/>'
        "</C:comp-filter></C:comp-filter></C:filter>"
        "</C:calendar-query>"
    )


def _propfind_xml(*props: str) -> str:
    inner = "".join(props)
    return f'<?xml version="1.0" encoding="utf-8"?><D:propfind xmlns:D="{DAV}" xmlns:C="{CALDAV}"><D:prop>{inner}</D:prop></D:propfind>'


def _responses(xml_text: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    return [el for el in root.iter() if _local_name(el.tag) == "response"]


def _href_of(response: ET.Element) -> str | None:
    for child in list(response):
        if _local_name(child.tag) == "href" and child.text:
            return child.text.strip()
    return None


def _has_calendar_type(response: ET.Element) -> bool:
    for el in response.iter():
        if _local_name(el.tag) == "calendar":
            return True
    return False


def _displayname(response: ET.Element) -> str:
    for el in response.iter():
        if _local_name(el.tag) == "displayname" and el.text:
            return el.text.strip()
    return ""


def discover_calendar(email: str, token: str) -> dict[str, str]:
    """Find a writable VEVENT collection. Missing FASTMAIL_* env uses the public CalDAV host."""
    origin = caldav_origin()
    user = email.strip()
    principal = None
    try:
        well_known = _request(
            "PROPFIND",
            f"{origin}/.well-known/caldav",
            email=user,
            token=token,
            headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
            content=_propfind_xml("<D:current-user-principal/>"),
            connect=True,
        )
        hrefs = _find_hrefs(well_known.text or "")
        if hrefs:
            principal = _abs(str(well_known.url), hrefs[0])
    except HTTPException as exc:
        if exc.status_code in {400, 401}:
            raise
        principal = None
    if not principal:
        principal = f"{origin}/dav/principals/user/{user}/"
        _request(
            "PROPFIND",
            principal,
            email=user,
            token=token,
            headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
            content=_propfind_xml("<D:current-user-principal/><C:calendar-home-set/>"),
            connect=True,
        )
    home = None
    home_resp = _request(
        "PROPFIND",
        principal,
        email=user,
        token=token,
        headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
        content=_propfind_xml("<C:calendar-home-set/>"),
        connect=True,
    )
    hrefs = _find_hrefs(home_resp.text or "")
    if hrefs:
        home = _abs(principal, hrefs[0])
    if not home:
        home = f"{origin}/dav/calendars/user/{user}/"
    listing = _request(
        "PROPFIND",
        home if home.endswith("/") else home + "/",
        email=user,
        token=token,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        content=_propfind_xml("<D:displayname/>", "<D:resourcetype/>", "<C:supported-calendar-component-set/>"),
        connect=True,
    )
    calendars: list[tuple[str, str]] = []
    for response in _responses(listing.text or ""):
        if not _has_calendar_type(response):
            continue
        href = _href_of(response)
        if not href:
            continue
        name = _displayname(response) or "Calendar"
        supports_event = "VEVENT" in (listing.text or "").upper() or True
        if supports_event:
            calendars.append((_abs(home, href), name))
    if not calendars:
        raise HTTPException(status_code=400, detail="No Fastmail calendar was found on that account.")
    preferred = next((item for item in calendars if item[1].lower() == "calendar"), calendars[0])
    return {"calendar_href": preferred[0], "calendar_name": preferred[1], "email": user}


def list_events(email: str, token: str, calendar_href: str, *, time_min: str, time_max: str) -> list[dict[str, object]]:
    response = _request(
        "REPORT",
        calendar_href if calendar_href.endswith("/") else calendar_href + "/",
        email=email,
        token=token,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        content=calendar_query_xml(time_min, time_max),
    )
    items: list[dict[str, object]] = []
    for node in _responses(response.text or ""):
        href = _href_of(node)
        ics = None
        for el in node.iter():
            if _local_name(el.tag) in {"calendar-data", "calendar_data"} and el.text:
                ics = el.text
                break
        if not href or not ics:
            continue
        parsed = parse_vevents(ics)
        if not parsed:
            continue
        event = parsed[0]
        items.append(
            {
                "id": encode_event_id(_abs(calendar_href, href)),
                "title": event["title"],
                "start": event["start"],
                "end": event["end"],
                "all_day": event["all_day"],
                "html_link": None,
            }
        )
    items.sort(key=lambda item: str(item.get("start") or ""))
    return items


def create_event(
    email: str,
    token: str,
    calendar_href: str,
    *,
    title: str,
    start: str,
    end: str,
) -> dict[str, object]:
    uid = f"{uuid.uuid4()}@storykeep"
    body = build_vevent(uid=uid, title=title, start=start, end=end)
    href = _abs(calendar_href if calendar_href.endswith("/") else calendar_href + "/", f"{uid}.ics")
    _request(
        "PUT",
        href,
        email=email,
        token=token,
        headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
        content=body,
    )
    return {
        "id": encode_event_id(href),
        "title": title.strip(),
        "start": start,
        "end": end,
        "all_day": False,
        "html_link": None,
    }


def _get_ics(email: str, token: str, href: str) -> str:
    response = _request("GET", href, email=email, token=token, headers={"Accept": "text/calendar"})
    return response.text or ""


def patch_event(
    email: str,
    token: str,
    event_id: str,
    *,
    title: str | None,
    start: str | None,
    end: str | None,
) -> dict[str, object]:
    href = decode_event_id(event_id)
    if not href:
        raise HTTPException(status_code=404, detail="That Fastmail event is gone.")
    ics = _get_ics(email, token, href)
    current = parse_vevents(ics)
    if not current:
        raise HTTPException(status_code=404, detail="That Fastmail event is gone.")
    event = current[0]
    next_title = title.strip() if title else str(event["title"])
    next_start = start or str(event["start"])
    next_end = end or str(event["end"])
    uid = str(event.get("uid") or uuid.uuid4())
    body = build_vevent(uid=uid, title=next_title, start=next_start, end=next_end)
    _request(
        "PUT",
        href,
        email=email,
        token=token,
        headers={"Content-Type": "text/calendar; charset=utf-8"},
        content=body,
    )
    return {
        "id": encode_event_id(href),
        "title": next_title,
        "start": next_start,
        "end": next_end,
        "all_day": False,
        "html_link": None,
    }


def delete_event(email: str, token: str, event_id: str) -> None:
    href = decode_event_id(event_id)
    if not href:
        raise HTTPException(status_code=404, detail="That Fastmail event is gone.")
    try:
        _request("DELETE", href, email=email, token=token)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
