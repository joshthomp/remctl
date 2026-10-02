from __future__ import annotations
import base64
import copy
import hashlib
import hmac
import json
import os
import tempfile
import time
import threading
import http.server
import ssl
import socket
import subprocess
import shutil
from datetime import datetime
import unittest
from pathlib import Path
from unittest.mock import patch

import remctl_events as e
import remctl_mcp as m
from test_mcp_server import FakeExecutor, request, http_call, modern_meta, MODERN

SECRET = "whsec_" + base64.b64encode(b"x" * 32).decode()
OTHER = "whsec_" + base64.b64encode(b"y" * 32).decode()


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1790776800.0
        self.snapshot = {"items":[{"id":1,"title":"Demo","listId":9,"objectUUID":"a","resourceUri":"remctl://reminder/a","completed":False,"tags":["demo"],"priority":"high"}],"lists":[{"id":9,"title":"Demo list","objectUUID":"b"}]}
        self.requests = []
        self.code = 200
        def post(url, body, headers):
            self.requests.append((url,body,headers))
            parsed=json.loads(body)
            return self.code, json.dumps({"challenge":parsed.get("challenge")}).encode()
        self.service=e.EventService(lambda:copy.deepcopy(self.snapshot),Path(self.temp.name),post,lambda:self.now,lambda owner:owner=="alice")
        self.params={"name":"reminder.updated","arguments":{"list_ids":[9]},"delivery":{"mode":"webhook","url":"https://receiver.example/callback","secret":SECRET},"cursor":None}

    def tearDown(self): self.temp.cleanup()

    def subscribe(self, **kwargs):
        return self.service.dispatch("events/subscribe",{**self.params,**kwargs},"alice")

    def test_catalog_schema_and_mcp_discovery(self):
        server=m.MCPServer(m.ServerConfig(version="test",executor=FakeExecutor()))
        self.assertIn("events",request(server,"server/discover")["result"]["capabilities"])
        events=request(server,"events/list")["result"]["events"]
        self.assertEqual(len(events),10)
        self.assertTrue(all(x["delivery"]==["webhook"] for x in events))

    def test_challenge_signature_and_private_storage(self):
        response=self.subscribe()
        _,body,headers=self.requests[0]
        expected=base64.b64encode(hmac.new(b"x"*32,(headers["webhook-id"]+"."+headers["webhook-timestamp"]+".").encode()+body,hashlib.sha256).digest()).decode()
        self.assertEqual(headers["webhook-signature"],"v1,"+expected)
        self.assertEqual(headers["X-MCP-Subscription-Id"],response["id"])
        self.assertIsNone(response["cursor"])
        self.assertEqual((Path(self.temp.name)/"events.sqlite3").stat().st_mode&0o777,0o600)

    def test_refresh_identity_canonical_keys_and_rotation(self):
        p={**self.params,"arguments":{"list_ids":[9],"flagged":False}}
        first=self.subscribe(**p)
        p["arguments"]={"flagged":False,"list_ids":[9]}
        p["delivery"]={**p["delivery"],"secret":OTHER}
        self.now+=10
        second=self.subscribe(**p)
        self.assertEqual(first["id"],second["id"])
        self.assertEqual(len(self.requests),1)
        self.snapshot["items"][0]["title"]="Changed"
        self.service.tick()
        self.assertEqual(len(self.requests[-1][2]["webhook-signature"].split()),2)

    def test_persistence_retry_stable_id_and_fresh_signature(self):
        self.subscribe()
        self.snapshot["items"][0]["title"]="Changed"
        self.code=503; self.now+=5; self.service.tick()
        first=self.requests[-1]
        restarted=e.EventService(lambda:copy.deepcopy(self.snapshot),Path(self.temp.name),self.service.post,lambda:self.now,lambda _:True)
        self.now+=60;self.code=200;restarted.tick()
        second=self.requests[-1]
        self.assertEqual(first[1],second[1])
        self.assertEqual(first[2]["webhook-id"],second[2]["webhook-id"])
        self.assertNotEqual(first[2]["webhook-signature"],second[2]["webhook-signature"])
        self.assertEqual(restarted.status("alice")["recent"][0]["delivery"],"delivered")

    def test_filter_miss_no_delivery_and_no_replay(self):
        self.subscribe(arguments={"tags":["other"]})
        self.snapshot["items"][0]["title"]="Changed";self.now+=5;self.service.tick()
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.service.status("alice")["recent"],[])
        with self.assertRaises(e.EventError):self.subscribe(cursor="untrusted")

    def test_expiry_revocation_and_unsubscribe(self):
        self.subscribe(ttlMs=1000);self.now+=2;self.service.tick()
        self.assertEqual(self.service.status("alice")["subscriptions"],[])
        self.subscribe();self.service.authorized=lambda _:False;self.service.tick()
        self.assertEqual(self.service.status("alice")["subscriptions"],[])
        self.service.authorized=lambda _:True;self.subscribe()
        self.service.dispatch("events/unsubscribe",self.params,"bob")
        self.assertEqual(len(self.service.status("alice")["subscriptions"]),1)
        for _ in range(2):self.service.dispatch("events/unsubscribe",self.params,"alice")
        self.assertEqual(self.service.status("alice")["subscriptions"],[])

    def test_failed_challenge_has_no_subscription_or_private_data(self):
        self.service.post=lambda *a:(200,b'{"challenge":"wrong"}')
        with self.assertRaises(e.EventError) as error:self.subscribe()
        self.assertEqual(error.exception.data,{"reason":"challenge_failed"})
        self.assertEqual(self.service.status("alice")["subscriptions"],[])

    def test_secret_validation_and_callback_urls(self):
        for secret in ["bad","whsec_invalid","whsec_"+base64.b64encode(b"x"*23).decode(),"whsec_"+base64.b64encode(b"x"*65).decode()]:
            with self.subTest(secret_length=len(secret)),self.assertRaises(e.EventError):e.signing_key(secret)
        for url in ["http://receiver.example","https://user:pass@receiver.example","https://receiver.example/#fragment","https://receiver.example/\r\nheader"]:
            with self.subTest(url=url),self.assertRaises(e.EventError):e.callback_parts(url)

    def test_delivery_time_private_address_check_blocks_dns_rebinding(self):
        for ip in ["127.0.0.1","10.0.0.1","169.254.169.254","::1","::ffff:127.0.0.1","fc00::1","224.0.0.1"]:
            with self.subTest(ip=ip):self.assertFalse(e.public_address(ip))
        with patch.object(e.socket,"getaddrinfo",return_value=[(2,1,6,"",("127.0.0.1",443))]),patch.object(e.socket,"socket") as connect:
            with self.assertRaises(e.EventError):e.webhook_post("https://receiver.example/callback",b"{}",{})
            connect.assert_not_called()

    def test_permanent_failures_are_not_retried(self):
        for status in [410,413]:
            with self.subTest(status=status):
                self.subscribe();self.snapshot["items"][0]["title"]=str(status);self.code=status;self.now+=10;self.service.tick()
                before=len(self.requests);self.now+=500;self.service.tick();self.assertEqual(len(self.requests),before)

    def test_failed_snapshot_does_not_create_deletion_events(self):
        self.subscribe(name="reminder.deleted")
        def fail():raise ValueError("No access")
        self.service.snapshot=fail
        with self.assertRaises(ValueError):self.service.tick()
        self.assertEqual(self.service.status("alice")["recent"],[])

    def test_schema_and_scope_validation(self):
        for args in [{"list_ids":[10]},{"reminder_ids":[99]},{"unexpected":1},{"list_ids":[True]}]:
            with self.subTest(args=args),self.assertRaises(e.EventError):self.subscribe(arguments=args)
        for ttl in [True,0,-1,"1"]:
            with self.subTest(ttl=ttl),self.assertRaises(e.EventError):self.subscribe(ttlMs=ttl)
        result=self.subscribe(ttlMs=None)
        self.assertIsNotNone(result["refreshBefore"])

    def test_completed_reopened_due_assignment_and_restore(self):
        before=copy.deepcopy(self.snapshot);after=copy.deepcopy(before)
        after["items"][0]["completed"]=True
        self.assertEqual(len(e.changes(before,after,"reminder.completed",{},self.now-5,self.now)),1)
        self.assertEqual(len(e.changes(after,before,"reminder.reopened",{},self.now-5,self.now)),1)
        after["items"][0]["assignment"]={"assignee":{"objectUUID":"test"}}
        self.assertEqual(len(e.changes(before,after,"reminder.assigned",{},self.now-5,self.now)),1)
        before["items"][0]["dueDate"]=e.iso(self.now-1);after=copy.deepcopy(before)
        self.assertEqual(len(e.changes(before,after,"reminder.due",{},self.now-5,self.now)),1)
        empty={"items":[],"lists":before["lists"],"deleted":[1]}
        self.assertEqual(len(e.changes(empty,after,"reminder.restored",{},self.now-5,self.now)),1)
        self.assertEqual(e.changes(empty,after,"reminder.created",{},self.now-5,self.now),[])

    def test_dst_midnight_and_private_baseline_hashes(self):
        old_tz=os.environ.get("TZ")
        try:
            os.environ["TZ"]="Europe/Rome";time.tzset()
            for day,next_day in [("2026-03-29","2026-03-30"),("2026-10-25","2026-10-26")]:
                before=copy.deepcopy(self.snapshot)
                before["items"][0].update(dueDate=day+"T00:00:00",allDay=True)
                midnight=datetime.fromisoformat(next_day).astimezone().timestamp()
                self.assertEqual(e.changes(before,before,"reminder.overdue",{},midnight-3600,midnight-1),[])
                self.assertEqual(len(e.changes(before,before,"reminder.overdue",{},midnight-1,midnight)),1)
        finally:
            if old_tz is None:os.environ.pop("TZ",None)
            else:os.environ["TZ"]=old_tz
            time.tzset()
        self.snapshot["items"][0]["notes"]="Never persist this private text"
        self.subscribe()
        with self.service.db() as db:
            stored=db.execute("SELECT value FROM subscriptions").fetchone()[0]
        self.assertNotIn("Never persist this private text",stored)
        self.snapshot["items"][0]["notes"]="Different private text"
        self.now+=5;self.service.tick()
        self.assertIn("notes",self.service.status("alice")["recent"][0]["data"]["changed_fields"])

    def test_verification_cache_expires_and_rotation_survives_refresh(self):
        self.subscribe();self.now+=10
        delivery={**self.params["delivery"],"secret":OTHER}
        self.subscribe(delivery=delivery);self.now+=10;self.subscribe(delivery=delivery)
        self.snapshot["items"][0]["title"]="Rotated";self.service.tick()
        self.assertEqual(len(self.requests[-1][2]["webhook-signature"].split()),2)
        self.now+=590;self.subscribe(delivery=delivery)
        self.assertEqual(json.loads(self.requests[-1][1])["type"],"verification")

    def test_http_event_methods_use_authenticated_principal(self):
        server=m.MCPServer(m.ServerConfig(version="test",executor=FakeExecutor()))
        server.events=self.service
        self.service.authorized=lambda owner:owner==e.http_principal("event-token")
        transport=m.HTTPTransportConfig(token="event-token",allowed_hosts=m.LOOPBACK_HOSTS)
        httpd=m.make_http_server(server,transport,"127.0.0.1",0)
        worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
        try:
            body={"jsonrpc":"2.0","id":1,"method":"events/subscribe","params":{**self.params,"_meta":modern_meta()}}
            headers={"Authorization":"Bearer event-token","MCP-Protocol-Version":MODERN,"Mcp-Method":"events/subscribe","Mcp-Name":"reminder.updated"}
            status,_,result=http_call(httpd.server_address[1],body=body,headers=headers)
            self.assertEqual(status,200,result);self.assertIn("id",result["result"])
            self.assertEqual(len(self.service.status(e.http_principal("event-token"))["subscriptions"]),1)
            self.assertEqual(self.service.status(e.local_principal())["subscriptions"],[])
            status,_,_=http_call(httpd.server_address[1],body=body,headers={**headers,"Authorization":"Bearer wrong"})
            self.assertEqual(status,401)
        finally:httpd.shutdown();httpd.server_close()

    @unittest.skipUnless(shutil.which("openssl"), "TLS fixture requires openssl")
    def test_real_https_signed_challenge_and_event_delivery(self):
        cert=Path(self.temp.name)/"receiver.crt";key=Path(self.temp.name)/"receiver.key"
        subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-keyout",str(key),"-out",str(cert),"-days","2","-subj","/CN=receiver.example","-addext","subjectAltName=DNS:receiver.example"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        received=[]
        class Receiver(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers["Content-Length"]))
                signed=(self.headers["webhook-id"]+"."+self.headers["webhook-timestamp"]+".").encode()+body
                signature="v1,"+base64.b64encode(hmac.new(b"x"*32,signed,hashlib.sha256).digest()).decode()
                valid=hmac.compare_digest(signature,self.headers["webhook-signature"])
                payload=json.loads(body);received.append((valid,self.headers["Host"],payload))
                reply=json.dumps({"challenge":payload.get("challenge")}).encode()
                self.send_response(200 if valid else 401);self.send_header("Content-Length",str(len(reply)));self.end_headers();self.wfile.write(reply)
        receiver=http.server.HTTPServer(("127.0.0.1",0),Receiver)
        server_tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_tls.load_cert_chain(cert,key)
        receiver.socket=server_tls.wrap_socket(receiver.socket,server_side=True)
        worker=threading.Thread(target=receiver.serve_forever,daemon=True);worker.start()
        client_tls=ssl.create_default_context(cafile=str(cert));port=receiver.server_address[1]
        self.service.post=e.webhook_post
        try:
            # Only the fixture permits loopback and its test CA. Production TLS and SSRF rules stay unchanged.
            with patch.object(e.socket,"getaddrinfo",return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",port))]),patch.object(e,"public_address",return_value=True),patch.object(e.ssl,"create_default_context",return_value=client_tls):
                self.subscribe(delivery={**self.params["delivery"],"url":f"https://receiver.example:{port}/callback"})
                self.snapshot["items"][0]["title"]="TLS delivery demo";self.now+=5;self.service.tick()
            self.assertEqual(len(received),2)
            self.assertTrue(all(row[0] for row in received))
            self.assertEqual(received[0][1],f"receiver.example:{port}")
            self.assertEqual(received[0][2]["type"],"verification")
            self.assertEqual(received[1][2]["data"]["title"],"TLS delivery demo")
            self.assertEqual(self.service.status("alice")["recent"][0]["delivery"],"delivered")
        finally:receiver.shutdown();receiver.server_close()

    def test_status_redacts_callback_secret_and_snapshot_notes(self):
        self.snapshot["items"][0]["notes"]="Private note text"
        self.subscribe();self.now+=5;self.snapshot["items"][0]["title"]="Changed";self.service.tick()
        text=json.dumps(self.service.status("alice"))
        for secret in [SECRET,"Private note text","/callback"]:self.assertNotIn(secret,text)
        self.assertEqual(self.service.status("bob")["subscriptions"],[])


if __name__=="__main__":unittest.main()
