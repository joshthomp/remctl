from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/build_capability_archive.py"
SPEC = importlib.util.spec_from_file_location("remctl_archive_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _source_tree(root: Path) -> None:
    sources = {
        "remctl": """
import json
import sys

def main():
    print(json.dumps({"argv": sys.argv, "bridge": __import__("os").environ["REMCTL_BRIDGE_PATH"]}))
    return 0
""",
        "remctl_broker.py": """
import json

def server_main(argv):
    print(json.dumps({"service": argv}))
    return 0
""",
    }
    for relative in builder.SOURCE_MANIFEST.values():
        (root / relative).write_text(
            sources.get(relative, "VALUE = 1\n"),
            encoding="utf-8",
        )


def _runtime_layout(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    app = root / "RemCTL Capability Host.app"
    runtime = app / "Contents/Resources/CapabilityRuntime"
    helpers = runtime / "bin"
    helpers.mkdir(parents=True)
    for name in ("remctl-bridge", "remctl-private"):
        helper = helpers / name
        helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        helper.chmod(0o755)
    return app, runtime


def _run_unlinked_archive(
    archive: Path,
    *,
    app: Path,
    runtime: Path,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    descriptor = os.open(archive, os.O_RDONLY)
    archive.unlink()
    try:
        saved_descriptor = os.dup(builder.ARCHIVE_DESCRIPTOR)
    except OSError:
        saved_descriptor = None
    os.dup2(descriptor, builder.ARCHIVE_DESCRIPTOR, inheritable=True)

    environment = {
        "HOME": str(Path.home()),
        "LANG": "en_US.UTF-8",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": "/private/tmp",
        builder.ARCHIVE_FD_ENV: str(builder.ARCHIVE_DESCRIPTOR),
        builder.HOST_ACTIVE_ENV: "1",
        builder.HOST_APP_ENV: str(app),
        builder.HOST_CDHASH_ENV: "a" * 40,
        builder.RUNTIME_ENV: str(runtime),
    }
    try:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                f"/dev/fd/{builder.ARCHIVE_DESCRIPTOR}",
                *arguments,
            ],
            cwd=runtime,
            env=environment,
            pass_fds=(builder.ARCHIVE_DESCRIPTOR,),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    finally:
        os.close(descriptor)
        if saved_descriptor is None:
            os.close(builder.ARCHIVE_DESCRIPTOR)
        else:
            os.dup2(saved_descriptor, builder.ARCHIVE_DESCRIPTOR)
            os.close(saved_descriptor)


class CapabilityArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_archive_is_deterministic_sourceless_and_exact(self):
        source = self.root / "source"
        source.mkdir()
        _source_tree(source)
        first = self.root / "first.pyz"
        second = self.root / "second.pyz"

        first_report = builder.build_archive(source, first)
        second_report = builder.build_archive(source, second)

        self.assertEqual(
            hashlib.sha256(first.read_bytes()).digest(),
            hashlib.sha256(second.read_bytes()).digest(),
        )
        self.assertEqual(first_report, second_report)
        self.assertEqual(first_report["modules"], sorted(builder.SOURCE_MANIFEST))
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
            self.assertEqual(names, first_report["entries"])
            self.assertEqual(names[0], "__main__.pyc")
            self.assertTrue(all(name.endswith(".pyc") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))

    def test_builder_rejects_an_undeclared_runtime_module(self):
        source = self.root / "source"
        source.mkdir()
        _source_tree(source)
        (source / "remctl_surprise.py").write_text("VALUE = 2\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "manifest is stale"):
            builder.build_archive(source, self.root / "archive.pyz")

    def test_unlinked_archive_dispatches_cli_from_sealed_runtime(self):
        source = self.root / "source"
        source.mkdir()
        _source_tree(source)
        archive = self.root / "archive.pyz"
        builder.build_archive(source, archive)
        app, runtime = _runtime_layout(self.root)

        result = _run_unlinked_archive(
            archive,
            app=app,
            runtime=runtime,
            arguments=["cli", "today", "--json"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["argv"], ["remctl", "today", "--json"])
        self.assertEqual(payload["bridge"], str(runtime / "bin/remctl-bridge"))

    def test_archive_refuses_a_linked_launch_path(self):
        source = self.root / "source"
        source.mkdir()
        _source_tree(source)
        archive = self.root / "archive.pyz"
        builder.build_archive(source, archive)
        app, runtime = _runtime_layout(self.root)
        environment = os.environ.copy()
        environment.update(
            {
                builder.ARCHIVE_FD_ENV: str(builder.ARCHIVE_DESCRIPTOR),
                builder.HOST_ACTIVE_ENV: "1",
                builder.HOST_APP_ENV: str(app),
                builder.HOST_CDHASH_ENV: "a" * 40,
                builder.RUNTIME_ENV: str(runtime),
            }
        )

        result = subprocess.run(
            [sys.executable, "-I", "-S", str(archive), "cli", "today"],
            cwd=runtime,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("descriptor is unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
