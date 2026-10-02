# RemCTL 2.0.3 release validation

October 1, 2026. Apple silicon release, built from `main` at `db22a91`.

## Why 2.0.3

[Issue #51](https://github.com/viticci/remctl/issues/51) reported that the Tailscale setup told Codex users to export the MCP bearer token from `~/.zshrc`. The other generated commands contained the token too: the Claude Code command left it in shell history and `~/.claude.json`, and the Claude Desktop entry put it in `claude_desktop_config.json`. Codex made the `.zshrc` route worse. Its config reference says `shell_environment_policy.ignore_default_excludes` defaults to true, so variables with `TOKEN` in the name reach the shell commands Codex runs for the model.

2.0.3 keeps the token in each device's login Keychain. Claude Code (`headersHelper`) and Codex (`http_headers_helper`) run a helper command when they connect and send the header it prints. Codex's source (`codex-rs/rmcp-client/src/http_headers.rs`) runs the helper with `sh -c`, a cleared environment, and a 10-second limit, and runs it again after a 401 or 403. Hermes reads the token through its `secrets.command` helper, and Claude Desktop starts `mcp-remote` through `/bin/sh` after reading it.

## Live client test

The endpoint was this Mac's own, `https://m5-ultra.tailc0622.ts.net/remctl`. The real token was saved in the login Keychain as `remctl-mcp-token`, and each client was registered as `remctl-tailnet` with the exact snippet the new code generates:

| Client | Version | Result |
| --- | --- | --- |
| Claude Code | 2.1.285 | `claude mcp get` reported Connected. `claude -p` called `lists` and got 9 lists, the same as `remctl lists`. |
| Codex | 0.159.2 | `codex exec` called `lists` and got 9. The first run logged two 401s; with every other MCP server disabled, the run was clean, so they came from other servers in the config. |
| Hermes Agent | 0.21.5 | `hermes mcp test` connected and listed 21 tools. The existing `secrets.command` helper, with the RemCTL line appended, applied 2 secrets. |
| Claude Desktop bridge | `mcp-remote` through npx, Node 24.21.0 | The generated `/bin/sh` wrapper answered `initialize`, and `lists` returned 9 over stdio. |

The Hermes block was also parsed with PyYAML and its helper run on its own. Afterward the test servers were removed, the Codex and Hermes configs were restored byte for byte from backups, and the Keychain item was deleted.

## Tests

The full Python suite ran 850 tests and passed, with 6 skipped. The new tests run the header helper through a real shell (it prints the header, or fails with no output when the Keychain item is missing), pass the Claude Code command through `/bin/sh` and parse the JSON it delivers, parse the Codex block with `tomllib`, check that no snippet contains the token, and check that the commands in `docs/mcp.md` and `docs/hermes.md` match the generator. The UI tests and type check passed.

## Signed artifact

- Build directory: `dist/release-2.0.3-arm64`.
- App submission (both apps): `c992e992-8ed1-4514-8c3c-d46c9311d020` (Accepted).
- DMG submission: `ec5bbf79-9079-4188-a58a-bab0e5fc93f6` (Accepted).
- DMG SHA-256: `553eaba5196db571934e29d54ebf02e5dd9567813c21a5c6cc2bb29e50c60c1d`.
- Protected Python runtime: `c2f0f5a6225c573981bd2527d6424c0daeed2e21a1d11e7d7680f8d19253396c`.

Both apps and the disk image have stapled tickets. From a quarantined copy of the disk image, Gatekeeper accepted the disk image, 'Install RemCTL', and the Capability Host as "Notarized Developer ID". The host keeps its `hidden` flag, so Finder shows only 'Install RemCTL'. Federico asked for the release once the local tests passed, so it was published without the usual Taildrop test on the MacBook Pro.

## Installed acceptance

The Mac Studio was still on 2.0.0 from the download. 'Install RemCTL' from the notarized disk image opened Terminal and waited for Federico's administrator password, which installs the new protected Python runtime. After he entered it, `remctl --version` reported 2.0.3, and `doctor` reported the host fully ready: protocol 2, private protocol 3, and Full Disk Access, Reminders, and Automation authorized. Its one warning was the expected note that direct database access is blocked for the calling process.

`remctl mcp install --client tailscale` moved the tailnet service from Homebrew's Python to the protected runtime. `/health` reported 2.0.3, and an authenticated `lists` call over the tailnet URL returned 9 lists. The command then crashed while printing its summary, with `NameError: name 'remctl_mcp' is not defined`. That bug has been there since Tailscale access was added, and it is fixed on `main` after 2.0.3, with a test.
