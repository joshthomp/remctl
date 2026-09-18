import fcntl
import io
import json
import os
import pty
import struct
import tempfile
import termios
import unittest
from pathlib import Path

import remctl_broker
from remctl_capabilities import (
    CAPABILITY_PREFIX,
    materialize_inputs,
    plan_invocation,
    validate_capability_bindings,
    validate_received_capabilities,
)


class _NonTTY:
    def isatty(self):
        return False


class CapabilityPlannerParityTests(unittest.TestCase):
    def setUp(self):
        self.parser = remctl_broker._load_real_parser()

    def _validate_bundle(self, bundle):
        _validated, parsed = remctl_broker.validate_argv(
            bundle.argv,
            parser=self.parser,
        )
        received = validate_received_capabilities(bundle.metadata, bundle.fds)
        validate_capability_bindings(bundle.argv, parsed, received)
        return parsed, received

    def test_post_terminator_option_shaped_positionals_remain_literal(self):
        cases = [
            (["add", "--", "--image"], "title", "--image"),
            (["add", "--", "--subtask"], "title", "--subtask"),
            (
                ["smart-list-create", "--", "--filter-json"],
                "name",
                "--filter-json",
            ),
        ]
        for argv, field, expected in cases:
            with self.subTest(argv=argv):
                parsed = self.parser.parse_args(argv)
                self.assertEqual(getattr(parsed, field), expected)
                with plan_invocation(
                    argv,
                    parsed,
                    stdin=_NonTTY(),
                    stdout=_NonTTY(),
                    stderr=_NonTTY(),
                ) as bundle:
                    self.assertEqual(bundle.argv, argv)
                    self.assertEqual(bundle.descriptors, [])
                    hosted, received = self._validate_bundle(bundle)
                    self.assertEqual(getattr(hosted, field), expected)
                    self.assertEqual(received, {})

    def test_import_file_before_and_after_terminator_remains_a_required_capability(self):
        with tempfile.TemporaryDirectory() as temp_value:
            source = Path(temp_value) / "reminders.json"
            source.write_text("[]")
            for argv in (["import", str(source)], ["import", "--", str(source)]):
                with self.subTest(argv=argv):
                    parsed = self.parser.parse_args(argv)
                    self.assertEqual(parsed.file, str(source))
                    with plan_invocation(
                        argv,
                        parsed,
                        stdin=_NonTTY(),
                        stdout=_NonTTY(),
                        stderr=_NonTTY(),
                    ) as bundle:
                        self.assertEqual(bundle.argv[:-1], argv[:-1])
                        self.assertTrue(bundle.argv[-1].startswith(CAPABILITY_PREFIX))
                        self.assertEqual(
                            [item.purpose for item in bundle.descriptors],
                            ["import"],
                        )
                        hosted, _received = self._validate_bundle(bundle)
                        self.assertEqual(hosted.file, bundle.argv[-1])

    def test_import_dash_captures_bounded_non_tty_stdin_without_a_file_capability(self):
        parsed = self.parser.parse_args(["import", "-", "--json"])
        stdin = io.BytesIO(b'[{"title":"Piped"}]')
        with plan_invocation(
            ["import", "-", "--json"],
            parsed,
            stdin=stdin,
            stdout=_NonTTY(),
            stderr=_NonTTY(),
        ) as bundle:
            self.assertEqual(bundle.argv, ["import", "-", "--json"])
            self.assertEqual(bundle.stdin_bytes, b'[{"title":"Piped"}]')
            self.assertEqual(bundle.descriptors, [])
            hosted, received = self._validate_bundle(bundle)
            self.assertEqual(hosted.file, "-")
            self.assertEqual(received, {})

    def test_import_dash_rejects_stdin_over_8_mib(self):
        parsed = self.parser.parse_args(["import", "-"])
        stdin = io.BytesIO(b"x" * (8 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "exceeds 8 MiB"):
            plan_invocation(
                ["import", "-"],
                parsed,
                stdin=stdin,
                stdout=_NonTTY(),
                stderr=_NonTTY(),
            )

    def test_pre_terminator_file_options_keep_all_supported_spellings(self):
        with tempfile.TemporaryDirectory() as temp_value:
            root = Path(temp_value)
            image = root / "cover.png"
            nested = root / "nested.png"
            filter_file = root / "filter.json"
            image.write_bytes(b"image")
            nested.write_bytes(b"nested")
            filter_file.write_text("{}")
            cases = [
                (["add", "Title", "--image", str(image)], ["image"]),
                (["add", "Title", "--image=" + str(image)], ["image"]),
                (
                    [
                        "edit",
                        "123",
                        "--subtask",
                        json.dumps({"title": "Child", "image": str(nested)}),
                    ],
                    ["subtask-image"],
                ),
                (
                    [
                        "edit",
                        "123",
                        "--subtask="
                        + json.dumps({"title": "Child", "image": str(nested)}),
                    ],
                    ["subtask-image"],
                ),
                (
                    [
                        "smart-list-create",
                        "Flagged",
                        "--filter-json",
                        "@" + str(filter_file),
                    ],
                    ["filter-json"],
                ),
                (
                    [
                        "smart-list-create",
                        "Flagged",
                        "--filter-json=@" + str(filter_file),
                    ],
                    ["filter-json"],
                ),
            ]
            for argv, expected_purposes in cases:
                with self.subTest(argv=argv):
                    parsed = self.parser.parse_args(argv)
                    with plan_invocation(
                        argv,
                        parsed,
                        stdin=_NonTTY(),
                        stdout=_NonTTY(),
                        stderr=_NonTTY(),
                    ) as bundle:
                        self.assertEqual(
                            [item.purpose for item in bundle.descriptors],
                            expected_purposes,
                        )
                        for path in (image, nested, filter_file):
                            self.assertFalse(
                                any(str(path) in token for token in bundle.argv)
                            )
                        self._validate_bundle(bundle)

    @unittest.skipUnless(hasattr(os, "openpty"), "PTY support is required")
    def test_600_column_tty_survives_planning_validation_and_materialization(self):
        master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(
            slave_fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", 24, 600, 0, 0),
        )
        output = os.fdopen(os.dup(slave_fd), "w")
        try:
            parsed = self.parser.parse_args(["today"])
            with plan_invocation(
                ["today"],
                parsed,
                stdin=_NonTTY(),
                stdout=output,
                stderr=_NonTTY(),
            ) as bundle:
                self.assertEqual(len(bundle.descriptors), 1)
                self.assertEqual(bundle.descriptors[0].purpose, "stdout")
                self.assertEqual(bundle.descriptors[0].columns, 600)
                received = validate_received_capabilities(bundle.metadata, bundle.fds)
                with tempfile.TemporaryDirectory() as temp_value:
                    rewritten, stdin_fd, columns, stderr_fd = materialize_inputs(
                        bundle.argv,
                        received,
                        Path(temp_value) / "stage",
                    )
                self.assertEqual(rewritten, ["today"])
                self.assertIsNone(stdin_fd)
                self.assertEqual(columns, 600)
                self.assertIsNone(stderr_fd)
        finally:
            output.close()
            os.close(slave_fd)
            os.close(master_fd)


if __name__ == "__main__":
    unittest.main()
