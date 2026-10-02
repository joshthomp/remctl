"""Durable MCP webhook subscriptions. Reminders access stays in the signed host."""
from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import ssl
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from remctl_runtime import resolve_config_dir, ensure_private_dir

NAMES = {
    "reminder.created": "A reminder was added after monitoring began.",
    "reminder.updated": "A reminder's fields changed, including tags, dates, notes or attachments.",
    "reminder.completed": "A reminder changed from incomplete to completed.",
    "reminder.reopened": "A completed reminder became incomplete again.",
    "reminder.deleted": "A reminder left the accessible Reminders store.",
    "reminder.restored": "A previously observed deleted reminder returned with its original identity.",
    "reminder.assigned": "A reminder's assignment changed.",
    "reminder.due": "An incomplete reminder reached its due time; all-day reminders fire at local midnight.",
    "reminder.overdue": "An incomplete reminder became overdue; all-day reminders fire the following midnight.",
    "list.updated": "A list or group was created, changed, or removed.",
}
FILTERS = {"type": "object", "properties": {
    "list_ids": {"type": "array", "items": {"type": "integer", "minimum": 1}, "maxItems": 50},
    "reminder_ids": {"type": "array", "items": {"type": "integer", "minimum": 1}, "maxItems": 50},
    "tags": {"type": "array", "items": {"type": "string", "maxLength": 128}, "maxItems": 30},
    "tag_match": {"type": "string", "enum": ["all", "any"]},
    "flagged": {"type": "boolean"},
    "priority": {"type": "array", "items": {"type": "string", "enum": ["none", "low", "medium", "high"]}, "maxItems": 4},
    "title_contains": {"type": "string", "maxLength": 256},
}, "additionalProperties": False}
PAYLOAD = {"type": "object", "properties": {
    "id": {"type": "integer"}, "title": {"type": "string"}, "list_id": {"type": "integer"},
    "resource_uri": {"type": "string"}, "url": {"type": "string"},
    "changed_fields": {"type": "array", "items": {"type": "string"}},
    "state": {"type": "object"}, "previous": {"type": "object"},
}, "required": ["id", "title", "resource_uri", "changed_fields", "state"], "additionalProperties": False}


class EventError(Exception):
    def __init__(self, code, message, reason=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.data = {"reason": reason} if reason else None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def local_principal():
    return "local:" + str(os.getuid())


def http_principal(token):
    return "http:" + hashlib.sha256(token.encode()).hexdigest()


def catalog():
    return [{"name": name, "description": description + " Local observation while this Mac and the RemCTL service are running; no historical replay.",
             "delivery": ["webhook"], "inputSchema": FILTERS if name != "list.updated" else {
                 "type": "object", "properties": {"list_ids": FILTERS["properties"]["list_ids"]}, "additionalProperties": False},
             "payloadSchema": PAYLOAD} for name, description in NAMES.items()]


def signing_key(secret):
    try:
        if not isinstance(secret, str) or not secret.startswith("whsec_"):
            raise ValueError()
        key = base64.b64decode(secret[6:], validate=True)
        if not 24 <= len(key) <= 64:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise EventError(-32602, "A whsec_ secret containing 24–64 bytes is required") from None


def callback_parts(url):
    try:
        if not isinstance(url, str) or len(url) > 4096 or any(ord(c) <= 32 for c in url):
            raise ValueError()
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError()
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError()
        return parts
    except ValueError:
        raise EventError(-32602, "Callback must be an HTTPS URL without credentials or a fragment") from None


def public_address(value):
    address = ipaddress.ip_address(value)
    if getattr(address, "ipv4_mapped", None):
        address = address.ipv4_mapped
    if isinstance(address, ipaddress.IPv6Address) and (address.sixtofour or address.teredo or address in ipaddress.ip_network("64:ff9b::/96")):
        return False
    return address.is_global and not (address.is_multicast or address.is_reserved or address.is_unspecified)


def webhook_post(url, body, headers):
    """Resolve once per attempt, pin the socket, preserve TLS SNI, never redirect."""
    parts = callback_parts(url)
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not public_address(a[4][0]) for a in addresses):
            raise EventError(-32015, "Callback destination is not public", "connection_refused")
        family, socktype, proto, _, address = addresses[0]
        with socket.socket(family, socktype, proto) as raw:
            raw.settimeout(10)
            raw.connect(address)
            with ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) as secured:
                connection = http.client.HTTPConnection(parts.hostname, parts.port or 443, timeout=10)
                connection.sock = secured
                try:
                    connection.request("POST", (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                                       body=body, headers={**headers, "Host": parts.netloc, "Connection": "close"})
                    response = connection.getresponse()
                    return response.status, response.read(16385)
                finally:
                    connection.close()
    except EventError:
        raise
    except (TimeoutError, socket.timeout):
        raise EventError(-32015, "Callback request timed out", "timeout") from None
    except ssl.SSLError:
        raise EventError(-32015, "Callback TLS failed", "tls_error") from None
    except (OSError, http.client.HTTPException):
        raise EventError(-32015, "Callback connection failed", "connection_refused") from None


def signed_headers(identifier, subscription, body, now):
    timestamp = str(int(now))
    prefix = (identifier + "." + timestamp + ".").encode() + body
    keys = [subscription["secret"]]
    if subscription.get("old_secret") and subscription.get("rotate_until", 0) > now:
        keys.append(subscription["old_secret"])
    signatures = ["v1," + base64.b64encode(hmac.new(signing_key(key), prefix, hashlib.sha256).digest()).decode() for key in keys]
    return {"Content-Type": "application/json", "webhook-id": identifier,
            "webhook-timestamp": timestamp, "webhook-signature": " ".join(signatures),
            "X-MCP-Subscription-Id": subscription["id"]}


def summary(item):
    return {key: item[key] for key in ("completed", "flagged", "urgent", "priority", "dueDate", "allDay", "tags", "section", "assignment") if key in item}


def occurrence(name, item, old, changed, now):
    data = {"id": item["id"], "title": str(item.get("title", ""))[:1024],
            "resource_uri": item.get("resourceUri") or "remctl://list/" + str(item.get("objectUUID", item["id"])),
            "changed_fields": sorted(changed), "state": summary(item)}
    if item.get("listId") is not None:
        data["list_id"] = item["listId"]
    if item.get("deepLink"):
        data["url"] = item["deepLink"]
    if old:
        data["previous"] = summary(old)
    return {"eventId": "evt_" + uuid.uuid4().hex, "name": name, "timestamp": iso(now), "data": data, "cursor": None}


def matches(item, args, lists=False):
    if args.get("list_ids") and (item["id"] if lists else item.get("listId")) not in args["list_ids"]:
        return False
    if args.get("reminder_ids") and item["id"] not in args["reminder_ids"]:
        return False
    if "flagged" in args and bool(item.get("flagged")) != args["flagged"]:
        return False
    if args.get("priority") and item.get("priority", "none") not in args["priority"]:
        return False
    if args.get("title_contains", "").casefold() not in str(item.get("title", "")).casefold():
        return False
    tags, wanted = set(item.get("tags", [])), set(args.get("tags", []))
    return not wanted or (wanted <= tags if args.get("tag_match") == "all" else bool(tags & wanted))


def changes(before, after, name, args, observed_at, now):
    """Compare complete snapshots. A failed or partial host read never implies deletion."""
    key = "lists" if name == "list.updated" else "items"
    old = {i["id"]: i for i in before.get(key, [])}
    current = {i["id"]: i for i in after.get(key, [])}
    deleted = set(before.get("deleted", []))
    events = []
    for identifier in sorted(old.keys() | current.keys()):
        previous, item = old.get(identifier), current.get(identifier)
        basis = item or previous
        if not matches(basis, args, key == "lists"):
            continue
        changed = [field for field in set(basis) | set(previous or {}) if field not in {"revision", "resourceUri"} and (previous or {}).get(field) != (item or {}).get(field)]
        fire = False
        if name == "list.updated": fire = bool(changed)
        elif name == "reminder.created": fire = previous is None and identifier not in deleted
        elif name == "reminder.restored": fire = previous is None and identifier in deleted
        elif name == "reminder.deleted": fire = item is None
        elif previous and item:
            if name == "reminder.updated": fire = bool(changed)
            elif name == "reminder.completed": fire = not previous.get("completed") and bool(item.get("completed"))
            elif name == "reminder.reopened": fire = bool(previous.get("completed")) and not item.get("completed")
            elif name == "reminder.assigned": fire = previous.get("assignment") != item.get("assignment")
            elif name in {"reminder.due", "reminder.overdue"} and not item.get("completed") and item.get("dueDate"):
                due = datetime.fromisoformat(item["dueDate"])
                if due.tzinfo is None: due = due.astimezone()
                if name == "reminder.overdue" and item.get("allDay"):
                    # Resolve the next local midnight independently across daylight-saving changes.
                    next_day = due.date() + timedelta(days=1)
                    boundary = datetime.combine(next_day, datetime.min.time()).astimezone().timestamp()
                else:
                    boundary = due.timestamp() + (1 if name == "reminder.overdue" else 0)
                fire = observed_at < boundary <= now
                if fire: changed = ["dueDate"]
        if fire:
            events.append(occurrence(name, basis, previous, changed, now))
    return events


class EventService:
    """A cross-process leader scans through the host; SQLite owns subscriptions and outbox."""
    def __init__(self, snapshot, directory=None, post=webhook_post, clock=time.time, authorized=None):
        self.directory = directory or resolve_config_dir() / "events"
        self.source_snapshot, self.post, self.clock = snapshot, post, clock
        self.authorized = authorized or self._authorized
        self.stop = threading.Event()
        self.thread = None

    def snapshot(self):
        """Persist comparison hashes instead of private note, alarm and attachment contents."""
        source = self.source_snapshot()
        public = {"id", "title", "listId", "objectUUID", "resourceUri", "deepLink", "completed", "flagged", "urgent", "priority", "dueDate", "allDay", "tags", "section", "assignment"}
        def redact(item):
            return {key: value if key in public else hashlib.sha256(canonical(value).encode()).hexdigest()
                    for key, value in item.items() if key != "revision"}
        return {"items": [redact(item) for item in source["items"]], "lists": [redact(item) for item in source["lists"]]}

    @contextlib.contextmanager
    def db(self):
        ensure_private_dir(self.directory)
        path = self.directory / "events.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        with contextlib.closing(sqlite3.connect(path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript("""CREATE TABLE IF NOT EXISTS subscriptions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, subscription TEXT NOT NULL, event TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS delivery_due ON outbox(status,next);""")
            yield db

    def _authorized(self, owner):
        if owner == local_principal(): return True
        from remctl_mcp import load_http_config
        config = load_http_config()
        return bool(config and owner == http_principal(config["token"]))

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, name="remctl-events", daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()

    def _loop(self):
        while not self.stop.is_set():
            try:
                ensure_private_dir(self.directory)
                with (self.directory / "worker.lock").open("a") as leader:
                    fcntl.flock(leader, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.tick()
            except BlockingIOError: pass
            except Exception:
                # Never put reminder text, destination URLs, or signing secrets in logs.
                with contextlib.suppress(Exception):
                    with self.db() as db:
                        db.execute("INSERT OR REPLACE INTO state VALUES('worker_error',?)", (iso(self.clock()),))
            self.stop.wait(5)

    def _identity(self, params, owner):
        from remctl_plugin import validate
        if params.get("name") not in NAMES:
            raise EventError(-32011, "Event not found")
        definition = next(x for x in catalog() if x["name"] == params["name"])
        args, delivery = params.get("arguments", {}), params.get("delivery", {})
        try: validate(args, definition["inputSchema"])
        except (ValueError, TypeError) as exc: raise EventError(-32602, str(exc)) from None
        if not isinstance(delivery, dict) or delivery.get("mode", "webhook") != "webhook":
            raise EventError(-32014, "Only webhook delivery is supported")
        callback_parts(delivery.get("url"))
        identity = canonical([owner, delivery["url"], params["name"], args])
        return "sub_" + hashlib.sha256(identity.encode()).hexdigest(), args, delivery

    def dispatch(self, method, params, owner):
        if method == "events/list":
            if params.get("cursor") is not None: raise EventError(-32602, "Invalid catalog cursor")
            return {"events": catalog()}
        identifier, args, delivery = self._identity(params, owner)
        if method == "events/unsubscribe":
            with self.db() as db:
                db.execute("DELETE FROM subscriptions WHERE id=? AND owner=?", (identifier, owner))
                db.execute("DELETE FROM outbox WHERE subscription=?", (identifier,))
            return {}
        if method != "events/subscribe": raise EventError(-32601, "Unknown event method")
        signing_key(delivery.get("secret"))
        ttl = params.get("ttlMs", 86400000)
        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0):
            raise EventError(-32602, "ttlMs must be a positive integer or null")
        if params.get("cursor") is not None: raise EventError(-32014, "These events do not support historical replay")
        now = self.clock()
        expires = now + min(ttl if ttl is not None else 86400000, 7 * 86400000) / 1000
        record = {"id": identifier, "owner": owner, "name": params["name"], "arguments": args,
                  "url": delivery["url"], "secret": delivery["secret"], "expires": expires,
                  "active": True, "lastError": None, "lastDeliveryAt": None, "created": now}
        with self.db() as db:
            oldrow = db.execute("SELECT value FROM subscriptions WHERE id=?", (identifier,)).fetchone()
            if db.execute("SELECT count(*) FROM subscriptions WHERE owner=?", (owner,)).fetchone()[0] >= 64 and not oldrow:
                raise EventError(-32013, "Subscription limit reached")
        fresh = self.snapshot()
        ids = {i["id"] for i in fresh["lists"]}
        if set(args.get("list_ids", [])) - ids or set(args.get("reminder_ids", [])) - {i["id"] for i in fresh["items"]}:
            raise EventError(-32012, "A selected Reminders resource is unavailable")
        verification_key = "verified:" + hashlib.sha256(canonical([owner, record["url"]]).encode()).hexdigest()
        with self.db() as db:
            cached = db.execute("SELECT value FROM state WHERE key=?", (verification_key,)).fetchone()
            verified = cached and float(cached[0]) > now
            db.execute("DELETE FROM state WHERE key LIKE 'verified:%' AND CAST(value AS REAL) < ?", (now,))
            db.execute("DELETE FROM state WHERE key LIKE 'attempt:%' AND CAST(value AS REAL) < ?", (now - 600,))
            attempt_key = "attempt:" + urlsplit(record["url"]).netloc
            attempted = db.execute("SELECT value FROM state WHERE key=?", (attempt_key,)).fetchone()
            if not verified and attempted and float(attempted[0]) > now - 2:
                raise EventError(-32013, "Callback verification is rate limited")
            db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (attempt_key, str(now)))
        if not verified:
            challenge = secrets.token_urlsafe(32)
            body = canonical({"type": "verification", "challenge": challenge}).encode()
            status, response = self.post(record["url"], body, signed_headers("msg_verification_" + uuid.uuid4().hex, record, body, now))
            try: echoed = json.loads(response).get("challenge", "")
            except (ValueError, AttributeError): echoed = ""
            if not 200 <= status < 300 or not isinstance(echoed, str) or not hmac.compare_digest(echoed.encode(), challenge.encode()) or self.clock() - now > 30:
                raise EventError(-32015, "Callback challenge failed", "challenge_failed")
        with self.db() as db:
            # Refresh identity is stable. Do not reset the observation baseline or pending deliveries.
            oldrow = db.execute("SELECT value FROM subscriptions WHERE id=?", (identifier,)).fetchone()
            old = json.loads(oldrow[0]) if oldrow else {}
            if old.get("expires", 0) > now:
                record.update({k: old[k] for k in ("snapshot", "observed", "created", "lastDeliveryAt") if k in old})
                if old.get("secret") != record["secret"]:
                    record.update(old_secret=old["secret"], rotate_until=now + 300)
                elif old.get("rotate_until", 0) > now:
                    record.update(old_secret=old["old_secret"], rotate_until=old["rotate_until"])
            record.setdefault("snapshot", fresh)
            record.setdefault("observed", now)
            db.execute("INSERT OR REPLACE INTO subscriptions VALUES(?,?,?)", (identifier, owner, canonical(record)))
            if not verified:
                db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (verification_key, str(now + 600)))
        return {"id": identifier, "refreshBefore": iso(expires), "cursor": None, "truncated": False,
                "deliveryStatus": {"active": True, "lastDeliveryAt": record["lastDeliveryAt"], "lastError": None}}

    def tick(self):
        now = self.clock()
        with self.db() as db:
            last_scan = db.execute("SELECT value FROM state WHERE key='last_scan_epoch'").fetchone()
            if last_scan and now - float(last_scan[0]) < 5:
                return
            records = [json.loads(row[0]) for row in db.execute("SELECT value FROM subscriptions")]
        active = []
        for record in records:
            if record["expires"] <= now or not self.authorized(record["owner"]):
                with self.db() as db:
                    db.execute("DELETE FROM subscriptions WHERE id=?", (record["id"],))
                    db.execute("DELETE FROM outbox WHERE subscription=?", (record["id"],))
            elif record["active"]: active.append(record)
        if not active: return
        fresh = self.snapshot()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for initial in active:
                row = db.execute("SELECT value FROM subscriptions WHERE id=?", (initial["id"],)).fetchone()
                if not row: continue
                record = json.loads(row[0])
                if not record["active"] or record["expires"] <= now: continue
                if record.get("rotate_until", 0) <= now:
                    record.pop("old_secret", None)
                    record.pop("rotate_until", None)
                if set(record["arguments"].get("list_ids", [])) - {i["id"] for i in fresh["lists"]} and record["name"] != "list.updated":
                    record.update(active=False, lastError="resource_unavailable")
                else:
                    pending = db.execute("SELECT count(*) FROM outbox WHERE subscription=? AND status='pending'", (record["id"],)).fetchone()[0]
                    events = changes(record["snapshot"], fresh, record["name"], record["arguments"], record["observed"], now)
                    if pending + len(events) > 1000:
                        record.update(active=False, lastError="queue_full")
                    else:
                        for event in events:
                            db.execute("INSERT INTO outbox(subscription,event,next) VALUES(?,?,?)", (record["id"], canonical(event), now))
                        deleted = set(record["snapshot"].get("deleted", [])) | ({i["id"] for i in record["snapshot"]["items"]} - {i["id"] for i in fresh["items"]})
                        record["snapshot"] = {**fresh, "deleted": sorted(deleted)[-10000:]}
                        record["observed"] = now
                db.execute("UPDATE subscriptions SET value=? WHERE id=?", (canonical(record), record["id"]))
            db.execute("INSERT OR REPLACE INTO state VALUES('last_scan',?)", (iso(now),))
            db.execute("INSERT OR REPLACE INTO state VALUES('last_scan_epoch',?)", (str(now),))
            db.execute("DELETE FROM state WHERE key='worker_error'")
            db.execute("DELETE FROM outbox WHERE status!='pending' AND next<?", (now - 7 * 86400,))
        self.deliver()

    def deliver(self):
        with self.db() as db:
            pending = list(db.execute("SELECT * FROM outbox WHERE status='pending' AND next<=? ORDER BY id LIMIT 20", (self.clock(),)))
        for job in pending:
            now = self.clock()
            with self.db() as db:
                row = db.execute("SELECT value FROM subscriptions WHERE id=?", (job["subscription"],)).fetchone()
            if not row: continue
            subscription = json.loads(row[0])
            if not subscription["active"] or subscription["expires"] <= now or not self.authorized(subscription["owner"]): continue
            event = json.loads(job["event"])
            body = job["event"].encode()
            try:
                status, _ = (413, b"") if len(body) > 262144 else self.post(subscription["url"], body, signed_headers(event["eventId"], subscription, body, now))
                reason = None if 200 <= status < 300 else ("http_5xx" if status >= 500 else "http_4xx")
            except EventError as exc: status, reason = 0, (exc.data or {}).get("reason", "connection_refused")
            attempts = job["attempts"] + 1
            terminal = status in {410, 413} or (300 <= status < 500 and status not in {408, 425, 429}) or attempts >= 8
            state = "delivered" if reason is None else "failed" if terminal else "pending"
            with self.db() as db:
                row = db.execute("SELECT value FROM subscriptions WHERE id=?", (job["subscription"],)).fetchone()
                if not row: continue
                latest = json.loads(row[0])
                latest["lastError"] = reason
                if reason is None: latest["lastDeliveryAt"] = iso(now)
                if status == 410: latest["active"] = False
                db.execute("UPDATE subscriptions SET value=? WHERE id=?", (canonical(latest), job["subscription"]))
                db.execute("UPDATE outbox SET status=?,attempts=?,next=? WHERE id=?", (state, attempts, now + (min(3600, 5 * 2 ** attempts) if state == "pending" else 0), job["id"]))

    def status(self, owner):
        with self.db() as db:
            subscriptions = []
            for row in db.execute("SELECT value FROM subscriptions WHERE owner=?", (owner,)):
                record = json.loads(row[0])
                value = {key: record.get(key) for key in ("id", "name", "arguments", "active", "lastError", "lastDeliveryAt")}
                value["refreshBefore"] = iso(record["expires"])
                value["destination"] = urlsplit(record["url"]).hostname
                value["pending"] = db.execute("SELECT count(*) FROM outbox WHERE subscription=? AND status='pending'", (record["id"],)).fetchone()[0]
                subscriptions.append(value)
            recent = [json.loads(row[0]) | {"delivery": row[1], "attempts": row[2]} for row in db.execute(
                "SELECT o.event,o.status,o.attempts FROM outbox o JOIN subscriptions s ON o.subscription=s.id WHERE s.owner=? ORDER BY o.id DESC LIMIT 30", (owner,))]
            state = dict(db.execute("SELECT key,value FROM state WHERE key IN ('last_scan','worker_error')"))
        return {"subscriptions": subscriptions, "recent": recent, "events": catalog(), **state}
