# RemCTL 2.2.0 release validation

October 2, 2026. Apple silicon release built from `8f84a80`.

## Changes and tests

The [October 2 audit](audit-2026-10-02.md) records the No Priority smart-list fix, reduced workspace and statistics work, date consistency, recurring completion behavior, and installer packaging changes. Its combined Python result is 859 passing tests and six skips on both Python 3.13 and 3.14. All three native tests initially affected by an unrelated keychain dialog passed after it was cleared.

After the version bump, TypeScript checking, workspace interaction tests, SDK contract checks, strict Claude Code plugin and marketplace validation, and all five Claude Code tests passed again. Distribution checks passed; the actual release bundle also passed an isolated install, upgrade, injected publication failure with rollback, uninstall, and tamper rejection.

The complete embedded Python archive, all 12 packaged client modules, generated workspace, MCP widget, both plugins, and marketplace match the release source. The host and installer both report 2.2.0 for their version and build number.

## Signed download

- Build: `dist/release-2.2.0-arm64`.
- App submission: `b5c1bc29-6691-4934-86b9-87a4aadc893a` (Accepted).
- Disk image submission: `2301b51c-f84c-4cad-9c38-7734ee626064` (Accepted).
- DMG SHA-256: `f7a3c5114755215ea820cf9a8fe4ebe38260f7643d121f54e6679e417a79952a`.
- Protected Python runtime: `7713b6bbddc818a91ebb1eed21bff50316b7cab6c6e5cda987ed6c5cb2419550`.

Both apps and the disk image carry validated notarization tickets. Gatekeeper accepted a quarantined copy of the disk image and both apps mounted from it as Notarized Developer ID. Nested signatures passed strict verification.

## Installed acceptance

The Mac Studio now runs the exact notarized 2.2.0 app. Its executable, app metadata, runtime manifest, and installed client files match the release bundle. The installed code hash is `551d025d1b8041df02737ea6fa0d4c732c6612a8`.

`remctl --version` reports 2.2.0. `doctor --for-agent --json` reports zero warnings and failures, the signed host ready, protocol 2, private protocol 3, and authorized Full Disk Access, Reminders, and Automation. Fresh Today and smart-list reads passed. The installed Codex 2.2.0 plugin cache matches the release source.

These checks ran on Apple silicon with macOS 27. Intel, older supported macOS versions, and physical iPhone/iPad clients were not tested for this release. The audit records the limits of the Claude Desktop UI check separately.
