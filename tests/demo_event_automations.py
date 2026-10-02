"""Run three event-driven automations against synthetic data and real HTTPS.

No Apple Reminders, installed subscriptions, ChatGPT tasks, or public services
are accessed. The fixture alone trusts its temporary CA and loopback receiver.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import http.server
import json
import secrets
import socket
import ssl
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import remctl_events as events
import remctl_mcp as mcp
from test_mcp_server import FakeExecutor, MODERN, http_call, modern_meta


def run_demos():
    now = [datetime(2026, 9, 30, 10, tzinfo=timezone.utc).timestamp()]
    snapshot = {"lists": [{"id": 9, "title": "Event demo", "objectUUID": "demo-list"}], "items": [
        {"id": n, "title": title, "listId": 9, "objectUUID": f"demo-{n}",
         "resourceUri": f"remctl://reminder/demo-{n}", "completed": False,
         "flagged": False, "tags": ["eventdemo"] if n < 4 else ["unrelated"]}
        for n, title in enumerate(["Ship the demo", "Review the draft", "Join the rehearsal", "Ignore this control"], 1)
    ]}
    snapshot["items"][2].update(dueDate=events.iso(now[0] + 30), allDay=False)
    recipes = {
        "reminder.completed": ("Completion receipt", {}),
        "reminder.updated": ("Flagged change digest", {"flagged": True}),
        "reminder.due": ("Due-time nudge", {}),
    }
    receipts, seen, verified = [], set(), []
    token, key = secrets.token_urlsafe(32), secrets.token_bytes(32)
    secret = "whsec_" + base64.b64encode(key).decode()
    with tempfile.TemporaryDirectory(prefix="remctl-event-demos-") as directory:
        root = Path(directory)
        cert, private_key = root / "receiver.crt", root / "receiver.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(private_key), "-out", str(cert), "-days", "1", "-subj", "/CN=receiver.example", "-addext", "subjectAltName=DNS:receiver.example"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        class Receiver(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                message_id, timestamp = self.headers["webhook-id"], self.headers["webhook-timestamp"]
                signature = "v1," + base64.b64encode(hmac.new(key, f"{message_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
                valid = hmac.compare_digest(signature, self.headers["webhook-signature"]) and abs(now[0] - int(timestamp)) < 300
                payload = json.loads(body)
                reply = {}
                if valid and payload.get("type") == "verification":
                    verified.append(message_id)
                    reply = {"challenge": payload["challenge"]}
                elif valid and payload["eventId"] not in seen:
                    seen.add(payload["eventId"])
                    name = payload["name"]
                    receipts.append({"automation": recipes[name][0], "event": name,
                                     "title": payload["data"]["title"], "signatureVerified": True})
                encoded = json.dumps(reply).encode()
                self.send_response(200 if valid else 401)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        receiver = http.server.HTTPServer(("127.0.0.1", 0), Receiver)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, private_key)
        receiver.socket = tls.wrap_socket(receiver.socket, server_side=True)
        threading.Thread(target=receiver.serve_forever, daemon=True).start()
        client_tls = ssl.create_default_context(cafile=str(cert))
        receiver_port = receiver.server_address[1]
        service = events.EventService(lambda: copy.deepcopy(snapshot), root / "state", events.webhook_post,
                                      lambda: now[0], lambda owner: owner == events.http_principal(token))
        server = mcp.MCPServer(mcp.ServerConfig(version="event-demo", executor=FakeExecutor()))
        server.events = service
        httpd = mcp.make_http_server(server, mcp.HTTPTransportConfig(token=token, allowed_hosts=mcp.LOOPBACK_HOSTS), "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        original_dns = socket.getaddrinfo

        def fixture_dns(host, port, *args, **kwargs):
            if host == "receiver.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", receiver_port))]
            return original_dns(host, port, *args, **kwargs)

        def rpc(method, params):
            headers = {"Authorization": f"Bearer {token}", "MCP-Protocol-Version": MODERN, "Mcp-Method": method}
            if "name" in params: headers["Mcp-Name"] = params["name"]
            status, _, response = http_call(httpd.server_address[1], body={"jsonrpc": "2.0", "id": 1, "method": method, "params": {**params, "_meta": modern_meta()}}, headers=headers)
            assert status == 200 and "result" in response, response
            return response["result"]

        subscriptions = []
        try:
            with patch.object(events.socket, "getaddrinfo", side_effect=fixture_dns), patch.object(events, "public_address", return_value=True), patch.object(events.ssl, "create_default_context", return_value=client_tls):
                assert len(rpc("events/list", {})["events"]) == 10
                for name, (_, filters) in recipes.items():
                    params = {"name": name, "arguments": {"list_ids": [9], "tags": ["eventdemo"], **filters}, "ttlMs": 60000,
                              "delivery": {"mode": "webhook", "url": f"https://receiver.example:{receiver_port}/events", "secret": secret}}
                    result = rpc("events/subscribe", params)
                    assert result["deliveryStatus"]["active"]
                    subscriptions.append(params)
                assert len(verified) == 1 and not receipts, "No historical events should run automations"
                snapshot["items"][3]["completed"] = True
                now[0] += 5; service.tick()
                assert not receipts, "Unrelated tags must not trigger a demo"
                snapshot["items"][0]["completed"] = True
                now[0] += 5; service.tick()
                snapshot["items"][1]["flagged"] = True
                now[0] += 5; service.tick()
                now[0] += 20; service.tick()
                assert [row["event"] for row in receipts] == list(recipes), receipts
                now[0] += 5; service.tick()
                assert len(receipts) == 3, "Unchanged snapshots must not rerun automations"
                for params in subscriptions: rpc("events/unsubscribe", params)
                assert service.status(events.http_principal(token))["subscriptions"] == []
                snapshot["items"][1]["title"] = "Changed after unsubscribe"
                now[0] += 5; service.tick()
                assert len(receipts) == 3
        finally:
            httpd.shutdown(); httpd.server_close()
            receiver.shutdown(); receiver.server_close()
    return {"environment": "isolated fixture; no ChatGPT activation or live Reminders access", "transport": "authenticated MCP HTTP and signed HTTPS webhook delivery", "automations": receipts,
            "checks": ["endpoint challenge", "no historical replay", "tag filtering", "one run per change", "due boundary", "unsubscribe stops runs"], "remainingSubscriptions": 0}


if __name__ == "__main__":
    print(json.dumps(run_demos(), indent=2))
