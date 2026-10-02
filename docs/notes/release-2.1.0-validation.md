# RemCTL 2.1.0 release validation

October 2, 2026. Apple silicon release, built from `24192d6`, the release commit that `main` fast-forwards to.

## What's in 2.1.0

- The Claude Code plugin (`plugins/claude-code`, listed by `.claude-plugin/marketplace.json` as `remctl@remctl`), with the Today mod: the band above the prompt, `/reminders`, and the status line.
- Searching completed reminders is fast again ([#54](https://github.com/viticci/remctl/issues/54)). Deleted-flag terms in RemCTL's queries carry a unary `+`, so SQLite uses each table's own reminder index instead of Reminders' deleted-flag index.
- Reads skip reminders whose list is deleted.
- `remctl mcp install`, onboarding, `doctor`, and `remctl mcp status` recognize the RemCTL plugins in Codex and Claude Code, add no second connection beside them, and remove one an earlier install added.
- `doctor` no longer crashes on a command line too long to be a path.

## Tests

The full Python suite ran 859 tests and passed, with 6 skipped. New tests cover the plugin-aware install paths for Codex and Claude Code, duplicate reporting in `registration_status`, `mcp status`, and onboarding, the deleted-list filter, the query plans for object lookups, and the long command line in `doctor`. The test classes that touch client configs now point every config at a missing file, so this Mac's own apps and plugins can't leak into them.

`claude plugin validate --strict` passed for the plugin and for the repository marketplace, and `claude plugin test` passed the mod's 3 tests.

## Signed artifact

- Build directory: `dist/release-2.1.0-arm64`.
- App submission (both apps): `16a995fb-6c2e-475b-ac08-5e327401fcd6` (Accepted).
- DMG submission: `be5785b9-85e3-460d-87a6-9d69051be9c2` (Accepted).
- DMG SHA-256: `048546626a174732b81505b4d77d259dff63aa586bf3827c65cf1c62f427eb29`.
- Protected Python runtime: `54832881ea8f84b6ccac525a984205d5bb5815fa47119a5b65b0c1a43f7e0f72`.

Both apps and the disk image have stapled tickets. From a quarantined copy of the disk image, Gatekeeper accepted the disk image, 'Install RemCTL', and the Capability Host as "Notarized Developer ID". The host keeps its `hidden` flag. As with 2.0.4, the release was published without the Taildrop test on the MacBook Pro.

## Installed acceptance

The Mac Studio was reinstalled with 'Install RemCTL' from this disk image, over a local 2.1.0 build. Federico entered his administrator password for the new protected Python runtime. The installed host's CDHash, `48547030a195f4d13b0153761b29c91b204b8cb2`, matches the notarized build. Afterward `remctl --version` reported 2.1.0, and `doctor` reported the host fully ready: protocol 2, private protocol 3, and Full Disk Access, Reminders, and Automation authorized. Its one warning was the expected note that direct database access is blocked for the calling process.

`remctl search the --completed --json` took 0.53 seconds on a library of 2,186 reminders, 2,129 of them completed. Before the fix, the same kind of search took 8.0 seconds on this library.

`remctl mcp install --client tailscale` moved the tailnet service to the 2.1.0 runtime, `/health` reported 2.1.0, and an authenticated `lists` call over the tailnet URL returned 10 lists.

### Plugins

- Codex: `codex plugin add remctl@remctl-local` refreshed the plugin to 2.1.0, and its cache matches the installed app. Codex runs one RemCTL server, the plugin's. Removing the `[mcp_servers.remctl]` table an earlier `remctl mcp install` had added brought back 'Reminders' in the sidebar after a restart.
- Claude Code: the main profile had both the plugin and a user-scope server from an earlier `remctl mcp install`. `remctl mcp install --client claude-code` on 2.1.0 removed that server and kept the plugin's, `plugin:remctl:remctl`. `doctor` then reported "MCP server connected to Claude Code (plugin), Codex (plugin), Claude Desktop and Cowork". The plugin was uninstalled and reinstalled at 2.1.0, and a new session showed the Today band with the day's reminders.
