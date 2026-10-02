"""Account identity recognition without modifying macOS account settings."""

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_module

remctl = load_module("remctl_account_sources_test", "remctl")


class AccountSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        patch = mock.patch.object(remctl.Path, "home", return_value=self.home)
        patch.start()
        self.addCleanup(patch.stop)
        remctl.account_providers.cache_clear()
        self.addCleanup(remctl.account_providers.cache_clear)

    def test_lookup_uses_stable_provider_ids_and_sees_committed_wal_rows(self):
        path = self.home / "Library/Accounts/Accounts4.sqlite"
        path.parent.mkdir(parents=True)
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE ZACCOUNTTYPE (Z_PK INTEGER, ZIDENTIFIER TEXT);
            CREATE TABLE ZACCOUNT (Z_PK INTEGER, ZIDENTIFIER TEXT, ZACCOUNTTYPE INTEGER, ZPARENTACCOUNT INTEGER);
            INSERT INTO ZACCOUNTTYPE VALUES (1, 'com.apple.account.AppleAccount'), (2, 'com.apple.account.CalDAV');
            INSERT INTO ZACCOUNT VALUES (1, 'APPLE-ID', 1, NULL), (2, 'OTHER-ID', 2, NULL),
                (3, 'APPLE-CALDAV', 2, 1), (4, 'OTHER-CALDAV', 2, 2), (5, 'APPLE-CHILD', 2, 3);
        """)
        db.commit()
        self.assertEqual(remctl.account_providers(), {
            "apple-id": "com.apple.account.AppleAccount", "other-id": "com.apple.account.CalDAV",
            "apple-caldav": "com.apple.account.AppleAccount", "other-caldav": "com.apple.account.CalDAV",
            "apple-child": "com.apple.account.AppleAccount"})

    def test_missing_or_unreadable_schema_keeps_the_existing_fallback(self):
        path = self.home / "Library/Accounts/Accounts4.sqlite"
        self.assertEqual(remctl.account_providers(), {})
        self.assertFalse(path.exists())
        path.parent.mkdir(parents=True)
        path.write_bytes(b"not a database")
        remctl.account_providers.cache_clear()
        self.assertEqual(remctl.account_providers(), {})
        self.assertEqual(path.read_bytes(), b"not a database")

    def test_source_metadata_uses_bridge_json_only_when_resolving_an_account(self):
        providers = {"apple-id": "com.apple.account.AppleAccount"}
        response = subprocess.CompletedProcess([], 0, '{"status":"ok"}', '')
        with mock.patch.object(remctl, "account_providers", return_value=providers) as lookup, \
             mock.patch.object(remctl.subprocess, "run", return_value=response) as run:
            for data in ({"action":"create"}, {"action":"create_list"}, {"action":"rename_list"},
                         {"action":"delete_list"}, {"action":"read"},
                         {"action":"update", "list":"Work", "listId":"list-id"}):
                with self.subTest(data=data):
                    lookup.reset_mock()
                    remctl.bridge_call_result(data)
                    self.assertEqual(json.loads(run.call_args.kwargs["input"]), {**data, "accountProviders":providers})
                    self.assertNotIn("accountProviders", data)
                    lookup.assert_called_once_with()
            for action in ("authorize", "complete", "uncomplete", "delete", "geocode", "update"):
                with self.subTest(action=action):
                    lookup.reset_mock()
                    remctl.bridge_call_result({"action":action})
                    lookup.assert_not_called()
                    self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"action":action})

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("swiftc"), "requires macOS Swift")
    def test_eventkit_matches_account_id_not_renamed_or_duplicate_titles(self):
        bridge = (Path(__file__).resolve().parents[1] / "remctl-bridge.swift").read_text()
        classifier = bridge[bridge.index("func isICloudSource("):bridge.index("func isICloudReminderSource(")]
        source = "import Foundation\nimport EventKit\n" + classifier + r'''
let providers = ["apple-id": "com.apple.account.AppleAccount", "other-id": "com.apple.account.CalDAV"]
for title in ["Personal", "Work, Personal", "Shared name", "iCloud"] {
    assert(isICloudSource(identifier: "APPLE-ID", title: title, type: .calDAV, providers: providers))
    assert(!isICloudSource(identifier: "other-id", title: title, type: .calDAV, providers: providers))
}
assert(!isICloudSource(identifier: "apple-id", title: "iCloud", type: .local, providers: providers))
assert(isICloudSource(identifier: "unknown", title: "iCloud", type: .calDAV, providers: providers))
assert(!isICloudSource(identifier: "unknown", title: "Personal", type: .calDAV, providers: providers))
assert(isICloudSource(identifier: "apple-id", title: "iCloud", type: .calDAV, providers: [:]))
assert(!isICloudSource(identifier: "apple-id", title: "Personal", type: .calDAV, providers: [:]))
'''
        path = self.home / "sources.swift"
        binary = self.home / "sources"
        path.write_text(source)
        subprocess.run(["swiftc", str(path), "-o", str(binary)], check=True, capture_output=True)
        subprocess.run([str(binary)], check=True, capture_output=True)
