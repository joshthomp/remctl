# RemCTL 2.0.4 release validation

October 1, 2026. Apple silicon release, built from `main` at `0788f4b`.

## Why 2.0.4

After installing 2.0.3 on the Mac Studio, Federico ran `remctl mcp install --client tailscale`. It set up the tailnet service, then crashed while printing its summary with `NameError: name 'remctl_mcp' is not defined`. `print_mcp_result` used the module without importing it, and had since Tailscale access was added in `1a010d8`. Onboarding prints through a different function and `--json` skips the summary, so neither path hit the bug. 2.0.4 imports the module there. A pyflakes pass over every RemCTL Python source found no other undefined names.

## Tests

The full Python suite ran 851 tests and passed, with 6 skipped. The new test prints a Tailscale install result through `print_mcp_result`; without the fix it fails with the same `NameError`.

## Signed artifact

- Build directory: `dist/release-2.0.4-arm64`.
- App submission (both apps): `29a9993f-833a-4f95-933d-358e29b3ec8e` (Accepted).
- DMG submission: `4ef63c0c-fe56-458d-8823-d68b6d16ef64` (Accepted).
- DMG SHA-256: `6a87191e051cadd7876dc2c01f263c2e1ffa0a2f9b6cad9243720c0bb200e5b2`.
- Protected Python runtime: `c6ab23043487dfe0009af59144a8766b7747379279c9766301129c65a74b3818`.

Both apps and the disk image have stapled tickets. From a quarantined copy of the disk image, Gatekeeper accepted the disk image, 'Install RemCTL', and the Capability Host as "Notarized Developer ID". The host keeps its `hidden` flag. As with 2.0.3, the release was published without the Taildrop test on the MacBook Pro.

## Installed acceptance

The Mac Studio was reinstalled from 2.0.3 with 'Install RemCTL' from this disk image. Federico entered his administrator password for the new protected Python runtime. Afterward `remctl --version` reported 2.0.4, and `doctor` reported the host fully ready: protocol 2, private protocol 3, and Full Disk Access, Reminders, and Automation authorized. Its one warning was the expected note that direct database access is blocked for the calling process.

`remctl mcp install --client tailscale`, without `--json`, exited 0 and printed the full summary with the Keychain step and the Claude Code and Codex commands. The token did not appear in the output. The tailnet service moved to the 2.0.4 runtime, `/health` reported 2.0.4, and an authenticated `lists` call over the tailnet URL returned 9 lists.
