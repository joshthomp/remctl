"""Bounded workspace reads, executed only through RemCTL's permission-owning host."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import plistlib
from urllib.parse import urlsplit
from datetime import datetime, timedelta
from pathlib import Path


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _integer(value, default, maximum):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError("Invalid page boundary")
    return value


def execute(request, api):
    """Use the CLI's existing queries and serializers; never create a second store."""
    if not isinstance(request, dict):
        raise ValueError("Workspace request must be an object")
    operation = request.get("operation", "query")
    if operation not in {"query", "detail", "attachment", "link_preview", "mentions", "events", "preview_filter"}:
        raise ValueError("Unknown workspace operation")
    db = api["open_db"]()
    try:
        return _read(db, request, api, operation)
    finally:
        db.close()


def _read(db, request, api, operation):
    lists = [api["list_to_dict"](r) for r in api["q_all_lists"](db)]
    by_id = {item["id"]: item for item in lists}
    if operation == "mentions":
        # Typeahead needs identifiers and labels, not attachments, alarms,
        # section membership or full reminder hydration on every keystroke.
        query = api["search_fold"](str(request.get("query", "")).strip())
        limit = min(30, _integer(request.get("limit"), 30, 500))
        matches = []
        for row in api["q_reminders"](db, completed=False, limit=100001):
            owner = by_id.get(row["ZLIST"])
            title = str(row["ZTITLE"] or "")
            if not owner or not row["ZCKIDENTIFIER"]:
                continue
            if query and query not in api["search_fold"](title):
                continue
            matches.append({"type":"resource_link", "uri":"remctl://reminder/" + row["ZCKIDENTIFIER"],
                            "name":title, "mimeType":"application/json", "description":owner["title"]})
            if len(matches) >= limit:
                break
        matches += [{"type":"resource_link", "uri":"remctl://list/" + item["objectUUID"],
                     "name":item["title"], "mimeType":"application/json", "description":"Reminders list"}
                    for item in lists if item.get("objectUUID") and
                    (not query or query in api["search_fold"](item["title"]))][:10]
        return {"items":matches}
    sections = [{"id": r["Z_PK"], "title": r["ZDISPLAYNAME"], "listId": r["ZLIST"],
                 "objectUUID": r["ZCKIDENTIFIER"]} for r in api["q_sections"](db)]
    memberships = {}
    for item in lists:
        if not item.get("isGroup"):
            memberships.update(api["q_section_memberships"](db, item["id"]))

    def payloads(rows, detail=False):
        values = api["reminders_to_dicts"](rows, db, memberships)
        for row, item in zip(rows, values):
            item.update(objectUUID=row["ZCKIDENTIFIER"], listId=row["ZLIST"])
            item["resourceUri"] = "remctl://reminder/" + str(item["objectUUID"])
            item["listUUID"] = by_id.get(item["listId"], {}).get("objectUUID")
            api["hydrate_reminder_detail"](db, item, item["id"])
            links = rich_link_rows(db, item["id"])
            if links:
                item["links"] = [{"url": link["ZURL"], "resourceUri": item["resourceUri"] + "/link/" + str(index),
                                  "revision": hashlib.sha256(link["ZMETADATA"] or b"").hexdigest()[:16]}
                                 for index, link in enumerate(links)]
            # Paths are host-only. Apps use a resource URI resolved against the real attachment.
            for index, attachment in enumerate(item.get("attachments", [])):
                attachment.pop("path", None)
                attachment["resourceUri"] = item["resourceUri"] + "/attachment/" + str(index)
            item["revision"] = revision(item)
        return values

    if operation in {"detail", "attachment", "link_preview"}:
        identifier = request.get("identifier")
        row = (api["q_reminder"](db, identifier) if isinstance(identifier, int)
               else api["q_reminder_by_identifier"](db, str(identifier)))
        if row is None:
            raise ValueError("This reminder no longer exists")
        item = payloads([row], detail=True)[0]
        if operation == "link_preview":
            links = rich_link_rows(db, row["Z_PK"])
            index = _integer(request.get("index"), 0, 500)
            if index >= len(links):
                raise ValueError("This saved link no longer exists")
            return saved_link_preview(links[index]["ZURL"], links[index]["ZMETADATA"])
        if operation == "attachment":
            index = _integer(request.get("index"), 0, 500)
            attachments = api["attachment_rows_to_json"](api["q_attachments"](db, row["Z_PK"]))
            if index >= len(attachments) or not attachments[index].get("path"):
                raise ValueError("Attachment is not downloaded on this Mac")
            path = Path(attachments[index]["path"])
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if request.get("download"):
                if path.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("Attachment download exceeds 50 MiB")
                return {"mimeType": mime, "filename": attachments[index].get("filename") or path.name,
                        "blob": base64.b64encode(path.read_bytes()).decode()}
            if not mime.startswith("image/") or path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Preview requires an image smaller than 8 MiB")
            return {"mimeType": mime, "blob": base64.b64encode(path.read_bytes()).decode()}
        item["subtasks"] = payloads(api["q_subtasks_for_parent"](db, row["Z_PK"]), detail=True)
        item["sharees"] = [api["sharee_to_dict"](s, current_user_ckid=api["q_list_shared_owner_ckid"](db, row["ZLIST"]))
                           for s in api["q_sharees"](db, row["ZLIST"])]
        return item

    if operation == "events":
        rows = api["q_reminders"](db, completed=True, limit=20001)
        if len(rows) > 20000:
            raise ValueError("Event observation exceeds 20,000 reminders; no partial snapshot was emitted")
        items = payloads([r for r in rows if r["ZLIST"] in by_id])
        # Event payloads contain summaries, while the private baseline retains
        # field fingerprints so changes to notes and attachments are observable.
        for item in items:
            item.pop("revision", None)
        return {"items": items, "lists": lists}

    limit = _integer(request.get("limit"), 100, 500)
    offset = _integer(request.get("offset"), 0, 100000)
    view = request.get("view", "today")
    query = api["search_fold"](str(request.get("query", "")).strip())
    smart = [api["smart_list_to_dict"](r) for r in api["q_smart_lists"](db)]
    # Filter inexpensive raw rows before hydrating only the requested page.
    rows = api["q_reminders"](db, completed=True, limit=100001)
    if len(rows) > 100000:
        raise ValueError("Workspace exceeds 100,000 reminders; narrow the store first")
    rows = [row for row in rows if row["ZLIST"] in by_id]
    search_ids = None
    if query:
        search_ids = {row["Z_PK"] for row in api["q_search"](db, query, completed=True, limit=100001)}
        # Tags belong to a separate table. Search them without hydrating every reminder.
        search_ids.update(row[0] for row in db.execute(
            "SELECT o.ZREMINDER3 FROM ZREMCDOBJECT o JOIN ZREMCDHASHTAGLABEL h ON o.ZHASHTAGLABEL=h.Z_PK "
            "WHERE o.ZMARKEDFORDELETION=0 AND instr(remctl_fold(h.ZNAME),?)>0", (query.removeprefix("#"),)))
    now = datetime.now().astimezone()
    today = now.date()

    def due(row):
        value = api["ts"](api["row_effective_due"](row))
        return value.date() if isinstance(value, datetime) else None

    counts = {key: 0 for key in ("today", "scheduled", "flagged", "all", "completed")}
    for row in rows:
        item = by_id.get(row["ZLIST"])
        if item:
            item["count"] = item.get("count", 0) + int(not row["ZCOMPLETED"])
        if row["ZCOMPLETED"]:
            counts["completed"] += 1
        else:
            counts["all"] += 1
            counts["flagged"] += int(bool(row["ZFLAGGED"]))
            counts["scheduled"] += int(due(row) is not None)
            counts["today"] += int(due(row) is not None and due(row) <= today)

    # Count pinned smart lists from the same predicates as their destination. Read
    # only filtering fields here; artwork and attachment payloads stay lazy.
    pinned_smart = [item for item in smart if item.get("kind") == "custom" and item.get("pinned") and item.get("filter", {}).get("supported")]
    if pinned_smart:
        candidates = []
        needs_location = any(_filter_uses(item["filter"], "location") for item in pinned_smart)
        for row in rows:
            if row["ZCOMPLETED"]:
                continue
            item = api["to_dict"](row)
            item.update(listId=row["ZLIST"], listUUID=by_id.get(row["ZLIST"], {}).get("objectUUID"),
                        tags=[tag["ZNAME"] for tag in api["q_hashtags"](db, row["Z_PK"])])
            if needs_location:
                item["alarms"] = api["alarm_rows_to_json"](api["q_alarms"](db, row["Z_PK"]))
            candidates.append(item)
        for smart_list in pinned_smart:
            try:
                smart_list["count"] = sum(matches_smart(item, smart_list["filter"], today) for item in candidates)
            except ValueError:
                # An unsupported predicate must never masquerade as an empty list.
                smart_list["count"] = None

    if view == "deleted":
        deleted = api["deleted_reminders"](db, json_mode=True)
        selected = [item for item in deleted if not query or query in item["title"].casefold()]
        items = selected[offset:offset + limit]
    else:
        selected = []
        list_id = request.get("listId")
        allowed_lists = {list_id}
        if list_id in by_id and by_id[list_id].get("isGroup"):
            allowed_lists.update(item["id"] for item in lists if item.get("parentListId") == list_id)
        for row in rows:
            completed = bool(row["ZCOMPLETED"])
            if view == "completed" and not completed:
                continue
            if view != "completed" and completed and not request.get("includeCompleted"):
                continue
            if list_id is not None and row["ZLIST"] not in allowed_lists:
                continue
            if view == "today" and (due(row) is None or due(row) > today):
                continue
            if view == "scheduled" and due(row) is None:
                continue
            if view == "flagged" and not row["ZFLAGGED"]:
                continue
            if view == "urgent" and not api["to_dict"](row).get("urgent"):
                continue
            if view == "overdue" and (due(row) is None or due(row) >= today):
                continue
            if view == "assigned":
                assignment = api["assignment_to_dict"](api["q_assignment"](db, row["Z_PK"])) or {}
                if not api["ckid_eq"](assignment.get("assignee", {}).get("objectUUID"), api["q_list_shared_owner_ckid"](db, row["ZLIST"])):
                    continue
            if search_ids is not None and row["Z_PK"] not in search_ids:
                continue
            selected.append(row)
        if view == "smart" or operation == "preview_filter":
            if operation == "preview_filter":
                from remctl_smart_lists import summarize_smart_list_filter
                target = {"filter": summarize_smart_list_filter(request["filterJSON"], strict=True)}
            else:
                target = next((item for item in smart if item["id"] == request.get("smartId")), None)
            if not target or not target.get("filter", {}).get("supported"):
                raise ValueError("This smart list uses filters RemCTL cannot decode")
            hydrated = payloads(selected, detail=True)
            selected = [row for row, item in zip(selected, hydrated) if matches_smart(item, target["filter"], today)]
        order = request.get("sort", "manual")
        if order == "manual" and list_id is not None:
            selected = api["sort_reminder_rows_by_identifier_order"](selected, api["q_list_reminder_order"](db, list_id))
        elif order == "title":
            selected.sort(key=lambda row: str(row["ZTITLE"] or "").casefold())
        elif order == "priority":
            selected.sort(key=lambda row: (row["ZPRIORITY"] or 99, row["Z_PK"]))
        elif order == "due" or view in {"today", "scheduled"}:
            selected.sort(key=lambda row: (due(row) is None, api["row_effective_due"](row) or 0, row["Z_PK"]))
        items = payloads(selected[offset:offset + limit])

    return {"items": items, "total": len(selected), "offset": offset, "limit": limit,
            "nextOffset": offset + len(items) if offset + len(items) < len(selected) else None,
            "lists": lists, "sections": sections, "smartLists": smart, "counts": counts,
            "view": view, "listId": request.get("listId"), "timezone": str(now.tzinfo),
            "generatedAt": now.isoformat(), "snapshot": revision([dict(row) for row in rows])}


def _filter_uses(spec, kind):
    return spec.get("kind") == kind or any(_filter_uses(child, kind) for child in spec.get("filters", []))


def matches_smart(item, spec, today):
    """Evaluate decoded predicates, refusing any unsupported family rather than widening it."""
    if "filters" in spec:
        outcomes = [matches_smart(item, child, today) for child in spec["filters"]]
        return any(outcomes) if spec.get("match") == "any" else all(outcomes)
    kind = spec.get("kind")
    if kind == "all":
        return True
    if kind == "flagged":
        return bool(item.get("flagged"))
    if kind == "priority":
        return item.get("priority") in spec.get("priorities", [])
    if kind == "tags":
        tags = set(item.get("tags", []))
        include, exclude = set(spec.get("tags", [])), set(spec.get("excludeTags", []))
        if not include and not exclude:
            return not tags if "untagged" in spec.get("description", "").lower() else bool(tags)
        return not tags.intersection(exclude) and (not include or (include <= tags if spec.get("tagMatch") == "all" else bool(include & tags)))
    if kind == "date":
        value = item.get("displayDate") or item.get("dueDate")
        scheduled = datetime.fromisoformat(value).date() if value else None
        rule = spec.get("date")
        if rule == "noDate":
            return scheduled is None
        if scheduled is None:
            return False
        if rule == "any":
            return True
        if rule == "today":
            return scheduled <= today if spec.get("includePastDue") else scheduled == today
        def parse(value):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
            raise ValueError("Invalid smart list date")
        if rule in {"onDate", "beforeDate", "afterDate"}:
            target = parse(spec["value"])
            return {"onDate": scheduled == target, "beforeDate": scheduled < target, "afterDate": scheduled > target}[rule]
        if rule == "dateRange":
            first, last = map(parse, spec["range"])
            return first <= scheduled <= last
        if rule == "relativeRange":
            import calendar
            relative = spec["relativeRange"]
            amount = int(relative["magnitude"])
            direction = -1 if relative["direction"] == "inPast" else 1
            unit = relative["units"]
            if amount < 0 or amount > 10000:
                raise ValueError("Invalid relative smart list date")
            if unit in {"month", "year"}:
                months = amount * direction * (12 if unit == "year" else 1)
                absolute = today.year * 12 + today.month - 1 + months
                year, month = divmod(absolute, 12)
                boundary = today.replace(year=year, month=month + 1, day=min(today.day, calendar.monthrange(year, month + 1)[1]))
            elif unit in {"day", "week"}:
                boundary = today + timedelta(days=amount * direction * (7 if unit == "week" else 1))
            elif unit in {"hour", "minute"}:
                if item.get("allDay"):
                    return False
                now = datetime.now().astimezone()
                target = datetime.fromisoformat(value)
                if target.tzinfo is None:
                    target = target.astimezone()
                delta = timedelta(seconds=amount * (3600 if unit == "hour" else 60))
                return (now - delta <= target <= now) if direction < 0 else (target <= now + delta if relative.get("includePastDue") else now <= target <= now + delta)
            else:
                raise ValueError("Unknown relative date unit")
            if direction < 0:
                return boundary <= scheduled <= today
            return scheduled <= boundary if relative.get("includePastDue") else today <= scheduled <= boundary
    if kind == "time":
        value = item.get("displayDate") or item.get("dueDate")
        if spec.get("time") == "noTime":
            return not value or bool(item.get("allDay"))
        if not value or item.get("allDay"):
            return False
        hour = datetime.fromisoformat(value).hour
        periods = {"morning": (6,12), "afternoon": (12,18), "evening": (18,24), "night": (0,6)}
        start, end = periods[spec["time"]]
        return start <= hour < end
    if kind == "location":
        if spec.get("vehicle"):
            raise ValueError("Car-trigger smart lists require metadata this macOS build does not expose")
        target = spec.get("location", {})
        proximity = "leaving" if target.get("proximity") in {"leave", "leaving", "exit"} else "arriving"
        for alarm in item.get("alarms", []):
            actual = alarm.get("location", {})
            if not actual or actual.get("proximity") != proximity:
                continue
            if all(target.get(key) is not None and actual.get(key) is not None and abs(float(target[key]) - float(actual[key])) < 0.00001 for key in ("latitude", "longitude")):
                return True
        return False
    if kind == "lists":
        keys = {str(item.get("listId")), str(item.get("listUUID")), item.get("list")}
        include, exclude = set(map(str, spec.get("include", []))), set(map(str, spec.get("exclude", [])))
        return not keys.intersection(exclude) and (not include or bool(keys & include))
    if "filters" in spec:
        outcomes = [matches_smart(item, child, today) for child in spec["filters"]]
        return any(outcomes) if spec.get("match") == "any" else all(outcomes)
    raise ValueError("Smart filter is not yet executable: " + str(kind))


def rich_link_rows(db, reminder_id):
    """Read only the saved URL attachments belonging to this reminder."""
    columns = {row[1] for row in db.execute('PRAGMA table_info(ZREMCDOBJECT)')}
    if not {'ZURL', 'ZREMINDER2', 'ZMARKEDFORDELETION'} <= columns:
        return []
    metadata = 'ZMETADATA' if 'ZMETADATA' in columns else 'NULL AS ZMETADATA'
    return db.execute(
        f'SELECT ZURL, {metadata} FROM ZREMCDOBJECT WHERE ZREMINDER2=? '
        "AND ZURL IS NOT NULL AND ZURL != '' AND +ZMARKEDFORDELETION=0 ORDER BY Z_PK",
        (reminder_id,),
    ).fetchall()


def decode_link_archive(raw):
    """Decode plist values without instantiating classes from an NSKeyedArchive."""
    if not isinstance(raw, bytes) or len(raw) > 16 * 1024 * 1024:
        return {}
    try:
        archive = plistlib.loads(raw)
    except (ValueError, TypeError, plistlib.InvalidFileException, OverflowError):
        return {}
    if not isinstance(archive, dict):
        return {}
    objects = archive.get('$objects', [])
    budget = [12000]

    def resolve(value, seen=frozenset(), depth=0):
        budget[0] -= 1
        if budget[0] < 0 or depth > 28:
            return None
        if isinstance(value, plistlib.UID):
            index = value.data
            if index in seen or not 0 <= index < len(objects):
                return None
            return resolve(objects[index], seen | {index}, depth + 1)
        if isinstance(value, dict):
            result = {key: resolve(child, seen, depth + 1) for key, child in value.items() if key != '$class'}
            if isinstance(result.get('NS.keys'), list) and isinstance(result.get('NS.objects'), list):
                return {str(k): v for k, v in zip(result['NS.keys'], result['NS.objects'])}
            if set(result) == {'NS.data'}:
                return result['NS.data']
            if 'NS.relative' in result:
                return result['NS.relative']
            return result
        if isinstance(value, list):
            return [resolve(child, seen, depth + 1) for child in value]
        return None if value == '$null' else value

    return resolve(archive.get('$top', {}).get('root', archive)) or {}


def saved_link_preview(url, raw):
    """Expose Apple's cached card, never fetch the linked website on a list read."""
    try:
        domain = urlsplit(url).hostname or ''
    except ValueError:
        domain = ''
    result = {'url': url, 'domain': domain, 'source': 'reminders', 'storedMetadataAvailable': bool(raw)}
    decoded = decode_link_archive(raw)
    result['storedMetadataDecoded'] = bool(decoded)
    fields = []

    def visit(value, path=''):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, path + '/' + str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + '/' + str(index))
        else:
            fields.append((path, value))
    visit(decoded)
    for target, names in [('title', ('title', 'name')), ('summary', ('summary', 'summaryText')), ('siteName', ('siteName', 'site'))]:
        for path, value in fields:
            if isinstance(value, str) and path.rsplit('/', 1)[-1].lstrip('_') in names and value:
                result[target] = value[:4096]
                break
    pictures = []
    for path, value in fields:
        if not isinstance(value, bytes) or len(value) > 8 * 1024 * 1024:
            continue
        mime = ('image/png' if value.startswith(b'\x89PNG\r\n\x1a\n') else
                'image/jpeg' if value.startswith(b'\xff\xd8\xff') else
                'image/gif' if value.startswith((b'GIF87a', b'GIF89a')) else
                'image/webp' if value[:4] == b'RIFF' and value[8:12] == b'WEBP' else None)
        if mime:
            pictures.append((path, value, mime))
    for role in ('image', 'icon'):
        candidates = [p for p in pictures if ('icon' in p[0].lower()) == (role == 'icon')]
        if candidates:
            path, value, mime = max(candidates, key=lambda p: len(p[1]))
            result[role] = {'mimeType': mime, 'data': base64.b64encode(value).decode()}
    return result


def fetch_public_preview(url):
    """Fetch a missing website card without cookies, private-network access or scripts."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin

    class Metadata(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.values = {}
            self.title = []
            self.in_title = False

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'meta':
                key = (attrs.get('property') or attrs.get('name') or '').lower()
                if key and attrs.get('content'):
                    self.values.setdefault(key, attrs['content'])
            elif tag == 'link' and 'icon' in attrs.get('rel', '').lower().split() and attrs.get('href'):
                self.values.setdefault('icon', attrs['href'])
            elif tag == 'title':
                self.in_title = True

        def handle_endtag(self, tag):
            if tag == 'title':
                self.in_title = False

        def handle_data(self, data):
            if self.in_title:
                self.title.append(data)

    content, mime, final_url = fetch_public_bytes(url, 2 * 1024 * 1024)
    if 'html' not in mime:
        return {}
    parser = Metadata()
    parser.feed(content.decode('utf-8', 'replace'))
    values = parser.values
    result = {'source':'website', 'title': (values.get('og:title') or values.get('twitter:title') or ''.join(parser.title))[:4096],
              'siteName': values.get('og:site_name', '')[:512]}
    for role, candidate in [('image', values.get('og:image') or values.get('twitter:image')), ('icon', values.get('icon'))]:
        if not candidate:
            continue
        try:
            data, mime, _ = fetch_public_bytes(urljoin(final_url, candidate), 4 * 1024 * 1024)
            mime = image_mime(data)
            if mime:
                result[role] = {'mimeType': mime, 'data': base64.b64encode(data).decode()}
        except (OSError, ValueError):
            continue
    return result


def image_mime(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def fetch_public_bytes(url, maximum, redirects=3):
    """Pin each connection to validated DNS results, validating redirects independently."""
    import http.client
    import socket
    import ssl
    import time
    from urllib.parse import urljoin
    from remctl_events import public_address

    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) <= 32 for c in url):
        raise ValueError('Invalid preview URL')
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Preview URL must be a public web address')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    if port not in (80, 443):
        raise ValueError('Preview URL port is not supported')
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not public_address(address[4][0]) for address in addresses):
        raise ValueError('Preview destination is not public')
    family, kind, proto, _, address = addresses[0]
    connection = http.client.HTTPConnection(parts.hostname, port, timeout=6)
    raw = socket.socket(family, kind, proto)
    try:
        raw.settimeout(6)
        raw.connect(address)
        connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) if parts.scheme == 'https' else raw
        connection.request('GET', (parts.path or '/') + ('?' + parts.query if parts.query else ''),
                           headers={'Host':parts.netloc, 'User-Agent':'RemCTL/0.2 LinkPreview', 'Accept':'text/html,image/*', 'Accept-Encoding':'identity', 'Connection':'close'})
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            if redirects <= 0 or not response.getheader('Location'):
                raise ValueError('Too many preview redirects')
            destination = urljoin(url, response.getheader('Location'))
            connection.close()
            return fetch_public_bytes(destination, maximum, redirects - 1)
        if response.status != 200:
            raise ValueError('Website preview is unavailable')
        size = response.getheader('Content-Length')
        if size and int(size) > maximum:
            raise ValueError('Preview exceeds size limit')
        chunks, count, deadline = [], 0, time.monotonic() + 12
        while True:
            if time.monotonic() > deadline:
                raise ValueError('Preview download timed out')
            chunk = response.read1(min(65536, maximum + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > maximum:
                raise ValueError('Preview exceeds size limit')
            chunks.append(chunk)
        return b''.join(chunks), response.getheader('Content-Type', ''), url
    except http.client.HTTPException as exc:
        raise ValueError('Website preview is unavailable') from exc
    finally:
        connection.close()
        raw.close()
