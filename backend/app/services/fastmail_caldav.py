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
APPLE_ICAL = "http://apple.com/ns/ical/"
DEFAULT_CALENDAR_COLOR = "#2563EB"
EVENT_COLORS = (
    "#2563EB",
    "#DC2626",
    "#059669",
    "#D97706",
    "#7C3AED",
    "#DB2777",
    "#0891B2",
    "#EA580C",
)


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


NO_CALENDARS = "No calendars — create one on Fastmail.com"
SKIP_RESOURCE_TYPES = {"addressbook", "schedule-inbox", "schedule-outbox", "dropbox", "notification"}


def _parse_root(xml_text: str) -> ET.Element | None:
    blob = xml_text or ""
    if not blob.strip():
        return None
    try:
        return ET.fromstring(blob.encode("utf-8") if isinstance(blob, str) else blob)
    except ET.ParseError:
        return None


def parse_prop_href(xml_text: str, prop_name: str) -> str | None:
    """Href nested in a DAV/CalDAV property — not the response href of the request URL."""
    root = _parse_root(xml_text)
    if root is None:
        return None
    for el in root.iter():
        if _local_name(el.tag) != prop_name:
            continue
        if el.text and el.text.strip() and _local_name(el.tag) == "href":
            return el.text.strip()
        for nested in el.iter():
            if _local_name(nested.tag) == "href" and nested.text and nested.text.strip():
                return nested.text.strip()
    return None


def _raise_fastmail(response: httpx.Response, *, connect: bool = False) -> None:
    if response.status_code in {401, 403}:
        detail = (
            "Fastmail did not accept that token. Use an app password or API token, not your account password."
            if connect
            else "Fastmail Calendar needs to be connected again."
        )
        raise HTTPException(status_code=401 if not connect else 400, detail=detail)
    if response.status_code == 404:
        if connect:
            raise HTTPException(status_code=404, detail="That CalDAV path was not found.")
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
    allow_missing: bool = False,
) -> httpx.Response | None:
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True, auth=_auth(email, token)) as client:
            response = client.request(method, url, headers=_headers(headers), content=content)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Fastmail Calendar.") from exc
    if allow_missing and response.status_code in {404, 405}:
        return None
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
        location = _ics_unescape(fields.get("LOCATION", ("", ""))[1] or "")
        meeting_url = _ics_unescape(fields.get("URL", ("", ""))[1] or "")
        color = normalize_color(fields.get("COLOR", ("", ""))[1] or fields.get("X-APPLE-CALENDAR-COLOR", ("", ""))[1])
        online_flag = (fields.get("X-STORYKEEP-ONLINE", ("", ""))[1] or "").strip().upper() in {"1", "TRUE", "YES"}
        online = online_flag or (bool(meeting_url) and (not location or location.strip().lower() == "online"))
        events.append(
            {
                "uid": uid,
                "title": title,
                "start": start_iso,
                "end": end_iso,
                "all_day": all_day,
                "location": location,
                "meeting_url": meeting_url,
                "online": online,
                "color": color,
            }
        )
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


def normalize_color(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("#") and len(raw) >= 7:
        hexpart = raw[1:7]
        if all(ch in "0123456789abcdefABCDEF" for ch in hexpart):
            return f"#{hexpart.upper()}"
    return None


def _event_out(
    event: dict[str, object],
    *,
    href: str,
    calendar: dict[str, str] | None = None,
) -> dict[str, object]:
    color = normalize_color(event.get("color") if isinstance(event.get("color"), str) else None) or (calendar or {}).get("color") or DEFAULT_CALENDAR_COLOR
    cal_id = (calendar or {}).get("id") or ""
    return {
        "id": encode_event_id(href),
        "title": event.get("title") or "(No title)",
        "start": event.get("start"),
        "end": event.get("end"),
        "all_day": bool(event.get("all_day")),
        "html_link": event.get("meeting_url") or None,
        "location": event.get("location") or "",
        "meeting_url": event.get("meeting_url") or "",
        "online": bool(event.get("online")),
        "color": color,
        "calendar_id": cal_id,
        "calendar_name": (calendar or {}).get("name") or "",
    }


def build_vevent(
    *,
    uid: str,
    title: str,
    start: str,
    end: str,
    location: str | None = None,
    meeting_url: str | None = None,
    online: bool = False,
    color: str | None = None,
) -> str:
    start_ics, start_all = to_utc_ics(start)
    end_ics, end_all = to_utc_ics(end)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_line = f"DTSTART;VALUE=DATE:{start_ics}" if start_all else f"DTSTART:{start_ics}"
    end_line = f"DTEND;VALUE=DATE:{end_ics}" if end_all else f"DTEND:{end_ics}"
    lines = [
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
    ]
    place = (location or "").strip()
    link = (meeting_url or "").strip()
    if online and not place:
        place = "Online"
    if place:
        lines.append(f"LOCATION:{_ics_escape(place)}")
    if link:
        lines.append(f"URL:{_ics_escape(link)}")
    if online:
        lines.append("X-STORYKEEP-ONLINE:TRUE")
    painted = normalize_color(color)
    if painted:
        lines.append(f"COLOR:{painted}")
        lines.append(f"X-APPLE-CALENDAR-COLOR:{painted}")
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(lines)


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
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<D:propfind xmlns:D="{DAV}" xmlns:C="{CALDAV}" xmlns:A="{APPLE_ICAL}">'
        f"<D:prop>{inner}</D:prop></D:propfind>"
    )


def _responses(xml_text: str) -> list[ET.Element]:
    root = _parse_root(xml_text)
    if root is None:
        return []
    return [el for el in root.iter() if _local_name(el.tag) == "response"]


def _href_of(response: ET.Element) -> str | None:
    for child in list(response):
        if _local_name(child.tag) == "href" and child.text:
            return child.text.strip()
    return None


def _resource_types(response: ET.Element) -> set[str]:
    names: set[str] = set()
    for el in response.iter():
        if _local_name(el.tag) != "resourcetype":
            continue
        for child in list(el):
            names.add(_local_name(child.tag).lower())
    return names


def _has_calendar_type(response: ET.Element) -> bool:
    types = _resource_types(response)
    if types & SKIP_RESOURCE_TYPES:
        return False
    if "calendar" in types:
        return True
    comps = _component_names(response)
    return "VEVENT" in comps


def _component_names(response: ET.Element) -> set[str]:
    found: set[str] = set()
    for el in response.iter():
        local = _local_name(el.tag)
        if local in {"comp", "calendar-component"}:
            name = (el.get("name") or el.text or "").strip().upper()
            if name:
                found.add(name)
    return found


def _displayname(response: ET.Element) -> str:
    for el in response.iter():
        if _local_name(el.tag) == "displayname" and el.text:
            return el.text.strip()
    return ""


def _same_href(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _calendar_color(response: ET.Element) -> str | None:
    for el in response.iter():
        if _local_name(el.tag) in {"calendar-color", "calendarcolor"}:
            painted = normalize_color(el.text or el.get("rgb") or "")
            if painted:
                return painted
    return None


def calendar_record(href: str, name: str, color: str | None, *, index: int = 0) -> dict[str, str]:
    path = href if href.endswith("/") else href + "/"
    painted = normalize_color(color) or EVENT_COLORS[index % len(EVENT_COLORS)]
    return {"id": encode_event_id(path), "href": path, "name": name or "Calendar", "color": painted}


def calendars_from_listing(xml_text: str, home: str) -> list[dict[str, str]]:
    calendars: list[dict[str, str]] = []
    for response in _responses(xml_text):
        href = _href_of(response)
        if not href:
            continue
        absolute = _abs(home, href)
        if _same_href(absolute, home):
            continue
        types = _resource_types(response)
        if types & SKIP_RESOURCE_TYPES:
            continue
        comps = _component_names(response)
        if not ("calendar" in types or "VEVENT" in comps):
            continue
        if comps and "VEVENT" not in comps:
            continue
        name = _displayname(response) or "Calendar"
        calendars.append(calendar_record(absolute, name, _calendar_color(response), index=len(calendars)))
    return calendars


def pick_calendar(calendars: list[dict[str, str]]) -> dict[str, str] | None:
    if not calendars:
        return None
    for item in calendars:
        if item.get("name", "").strip().lower() in {"calendar", "personal", "home"}:
            return item
    return calendars[0]


def normalize_calendar_url(raw: str | None, *, email: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    origin = caldav_origin()
    user = email.strip()
    if value.startswith("/"):
        return _abs(origin + "/", value if value.endswith("/") else value + "/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Paste a CalDAV URL from Fastmail Settings, or leave it blank.")
    allowed = urlparse(origin + "/").netloc.lower()
    if parsed.netloc.lower() != allowed:
        raise HTTPException(status_code=400, detail="Paste a CalDAV URL on caldav.fastmail.com from Fastmail Settings.")
    path = parsed.path or "/"
    if path in {"/", ""}:
        return None
    if "{email}" in path:
        path = path.replace("{email}", user)
    return _abs(f"{parsed.scheme}://{parsed.netloc}", path if path.endswith("/") else path + "/")


def _propfind(
    url: str,
    *,
    email: str,
    token: str,
    depth: str,
    props: tuple[str, ...],
    connect: bool = True,
    allow_missing: bool = False,
) -> httpx.Response | None:
    return _request(
        "PROPFIND",
        url,
        email=email,
        token=token,
        headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
        content=_propfind_xml(*props),
        connect=connect,
        allow_missing=allow_missing,
    )


def _list_at_home(email: str, token: str, home: str) -> list[dict[str, str]]:
    listing = _propfind(
        home if home.endswith("/") else home + "/",
        email=email,
        token=token,
        depth="1",
        props=("<D:displayname/>", "<D:resourcetype/>", "<C:supported-calendar-component-set/>", "<A:calendar-color/>"),
        connect=True,
        allow_missing=True,
    )
    if listing is None:
        return []
    home_url = str(listing.url) if listing.url else home
    found = calendars_from_listing(listing.text or "", home_url)
    if found:
        return found
    loose: list[dict[str, str]] = []
    for response in _responses(listing.text or ""):
        href = _href_of(response)
        if not href:
            continue
        absolute = _abs(home_url, href)
        if _same_href(absolute, home_url):
            continue
        types = _resource_types(response)
        if types & SKIP_RESOURCE_TYPES or "principal" in types:
            continue
        if "collection" not in types:
            continue
        name = _displayname(response) or "Calendar"
        loose.append(calendar_record(absolute, name, _calendar_color(response), index=len(loose)))
    return loose


def _discover_result(user: str, calendars: list[dict[str, str]], chosen: dict[str, str] | None) -> dict[str, object]:
    if not chosen:
        raise HTTPException(status_code=409, detail=NO_CALENDARS)
    return {
        "email": user,
        "calendar_href": chosen["href"],
        "calendar_name": chosen["name"],
        "calendars": calendars or [chosen],
    }


def discover_calendar(email: str, token: str, calendar_url: str | None = None) -> dict[str, object]:
    """Well-known / principal discovery. Username is the full Fastmail email."""
    origin = caldav_origin()
    user = email.strip()
    pasted = normalize_calendar_url(calendar_url, email=user)
    if pasted:
        depth0 = _propfind(
            pasted,
            email=user,
            token=token,
            depth="0",
            props=("<D:displayname/>", "<D:resourcetype/>", "<C:supported-calendar-component-set/>", "<C:calendar-home-set/>", "<A:calendar-color/>"),
            connect=True,
        )
        assert depth0 is not None
        listed = calendars_from_listing(depth0.text or "", pasted)
        color = None
        name = "Calendar"
        types: set[str] = set()
        for response in _responses(depth0.text or ""):
            types = _resource_types(response)
            name = _displayname(response) or name
            color = _calendar_color(response)
            break
        if listed:
            chosen = pick_calendar(listed)
            return _discover_result(user, listed, chosen)
        if "calendar" in types:
            chosen = calendar_record(pasted, name, color)
            return _discover_result(user, [chosen], chosen)
        home_href = parse_prop_href(depth0.text or "", "calendar-home-set")
        home = _abs(pasted, home_href) if home_href else pasted
        found = _list_at_home(user, token, home)
        return _discover_result(user, found, pick_calendar(found))

    principal = None
    well_known = _propfind(
        f"{origin}/.well-known/caldav",
        email=user,
        token=token,
        depth="0",
        props=("<D:current-user-principal/>", "<C:calendar-home-set/>"),
        connect=True,
        allow_missing=True,
    )
    if well_known is not None:
        href = parse_prop_href(well_known.text or "", "current-user-principal")
        if href:
            principal = _abs(str(well_known.url), href)
        home_href = parse_prop_href(well_known.text or "", "calendar-home-set")
        if home_href and not principal:
            principal = _abs(str(well_known.url), home_href)
    if not principal:
        principal = f"{origin}/dav/principals/user/{user}/"
        probe = _propfind(
            principal,
            email=user,
            token=token,
            depth="0",
            props=("<D:current-user-principal/>", "<C:calendar-home-set/>"),
            connect=True,
        )
        assert probe is not None
        href = parse_prop_href(probe.text or "", "current-user-principal")
        if href:
            principal = _abs(str(probe.url), href)

    home = None
    home_resp = _propfind(
        principal if principal.endswith("/") else principal + "/",
        email=user,
        token=token,
        depth="0",
        props=("<C:calendar-home-set/>",),
        connect=True,
        allow_missing=True,
    )
    if home_resp is not None:
        home_href = parse_prop_href(home_resp.text or "", "calendar-home-set")
        if home_href:
            home = _abs(str(home_resp.url), home_href)
    if not home:
        home = f"{origin}/dav/calendars/user/{user}/"

    calendars = _list_at_home(user, token, home)
    return _discover_result(user, calendars, pick_calendar(calendars))


def list_events(
    email: str,
    token: str,
    calendar: dict[str, str] | str,
    *,
    time_min: str,
    time_max: str,
) -> list[dict[str, object]]:
    if isinstance(calendar, str):
        calendar = calendar_record(calendar, "Calendar", None)
    calendar_href = calendar["href"]
    response = _request(
        "REPORT",
        calendar_href if calendar_href.endswith("/") else calendar_href + "/",
        email=email,
        token=token,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        content=calendar_query_xml(time_min, time_max),
    )
    assert response is not None
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
        items.append(_event_out(event, href=_abs(calendar_href, href), calendar=calendar))
    items.sort(key=lambda item: str(item.get("start") or ""))
    return items


def create_event(
    email: str,
    token: str,
    calendar: dict[str, str] | str,
    *,
    title: str,
    start: str,
    end: str,
    location: str | None = None,
    meeting_url: str | None = None,
    online: bool = False,
    color: str | None = None,
) -> dict[str, object]:
    if isinstance(calendar, str):
        calendar = calendar_record(calendar, "Calendar", None)
    calendar_href = calendar["href"]
    uid = f"{uuid.uuid4()}@storykeep"
    painted = normalize_color(color) or calendar.get("color")
    body = build_vevent(
        uid=uid,
        title=title,
        start=start,
        end=end,
        location=location,
        meeting_url=meeting_url,
        online=online,
        color=painted,
    )
    href = _abs(calendar_href if calendar_href.endswith("/") else calendar_href + "/", f"{uid}.ics")
    _request(
        "PUT",
        href,
        email=email,
        token=token,
        headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
        content=body,
    )
    parsed = parse_vevents(body)[0]
    return _event_out(parsed, href=href, calendar=calendar)


def _get_ics(email: str, token: str, href: str) -> str:
    response = _request("GET", href, email=email, token=token, headers={"Accept": "text/calendar"})
    assert response is not None
    return response.text or ""


def patch_event(
    email: str,
    token: str,
    event_id: str,
    *,
    title: str | None,
    start: str | None,
    end: str | None,
    location: str | None = None,
    meeting_url: str | None = None,
    online: bool | None = None,
    color: str | None = None,
    calendar: dict[str, str] | None = None,
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
    next_location = location if location is not None else str(event.get("location") or "")
    next_url = meeting_url if meeting_url is not None else str(event.get("meeting_url") or "")
    next_online = bool(event.get("online")) if online is None else online
    next_color = normalize_color(color) if color is not None else normalize_color(str(event.get("color") or ""))
    uid = str(event.get("uid") or uuid.uuid4())
    target_href = href
    if calendar and calendar.get("href"):
        filename = href.rstrip("/").rsplit("/", 1)[-1]
        target_href = _abs(calendar["href"], filename)
    body = build_vevent(
        uid=uid,
        title=next_title,
        start=next_start,
        end=next_end,
        location=next_location,
        meeting_url=next_url,
        online=next_online,
        color=next_color or (calendar or {}).get("color"),
    )
    _request(
        "PUT",
        target_href,
        email=email,
        token=token,
        headers={"Content-Type": "text/calendar; charset=utf-8"},
        content=body,
    )
    if target_href != href:
        try:
            _request("DELETE", href, email=email, token=token)
        except HTTPException:
            pass
    parsed = parse_vevents(body)[0]
    return _event_out(parsed, href=target_href, calendar=calendar)


def delete_event(email: str, token: str, event_id: str) -> None:
    href = decode_event_id(event_id)
    if not href:
        raise HTTPException(status_code=404, detail="That Fastmail event is gone.")
    try:
        _request("DELETE", href, email=email, token=token)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
