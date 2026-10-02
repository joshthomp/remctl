# RemCTL 2.0 release validation

September 30, 2026. Apple silicon release built from `release/2.0.0`, application source commit `b705a9c`.

## Redesigned signed artifact

This build supersedes the earlier `ec32a0e` distribution artifact. The previous notarization receipts in [distribution validation](distribution-validation-2026-09-30.md) cover the older workspace, not this redesign.

- Build directory: `dist/release-2.0.0-arm64`.
- Plugin build: `912f82237323316f`.
- Workspace SHA-256: `740c62eee4a4dcf5de35a2b03cb70f387d05f2b94e8462e689632abde4c560f0`.
- App submission: `875b4d08-e8c7-4faf-b5e0-69004c00cf11` (Accepted).
- DMG submission: `4967bedb-980c-4bf1-850f-ed70f9955f86` (Accepted).
- DMG SHA-256: `bd22e3de8b436003a2bed21ddc2c7310b5b0883be7eec476b519f9ff11c9e9ef`.
- Signing: MacStories Developer ID, team `4W35M4UN6R`.

The app and disk image have stapled tickets. Strict nested signature verification, ticket validation, and Gatekeeper app execution and disk-image opening all passed. The disk image mounted read-only; its app signature passed, and the packaged workspace matched the release branch byte for byte. Server modules and plugin manifests also match source.

The complete Python suite ran 844 tests successfully, with 6 skipped. TypeScript checks, interaction tests, SDK contracts, and the production UI build passed. Rebuilding the UI left its committed bundle and plugin build identifier unchanged.

## Installed acceptance

Installed from the mounted, read-only release DMG using the normal transactional installer after administrator authorization installed the protected Python runtime. The existing Developer ID was preserved; all three privacy grants remained authorized. The active MCP HTTP endpoint restarted and passed its health check.

- Installed code hash: `cf7b25ea9ba4cc487b4f0ebeea434b962c35fb13`.
- Protected Python runtime: `54cabb2c16214bd0554e0f92f676daa60b7b73b6ce4a9595b1ea55d702c9c11c`.
- CLI, plugin, and app report `2.0.0`.
- Installed workspace and server modules match release source byte for byte; nested signatures, stapled ticket, and Gatekeeper checks pass after installation.
- Doctor reports ready with zero failures and Reminders, Automation, and Full Disk Access authorized. Its direct-caller database warning is expected: protected reads use the signed host.
- Codex marketplace `remctl-local` now points to `~/Applications/RemCTL Capability Host.app/Contents/Resources`. Plugin cache version `2.0.0` reports build `912f82237323316f`.

Computer Use verified the native ChatGPT workspace after refreshing the plugin and reopening Reminders. The app log confirms it read `ui://remctl/workspace-740c62eee4a4.html`. Today loaded with native list icons and pinned tiles; the floating Quick Add panel stayed above the chat composer. Command-palette search and Return opened Weekly 531, whose nested reminders, rich link cards, saved images, and full-size attachment viewer worked. Closing an image restored focus to its preview button.

A disposable reminder, id `5023`, was created through Quick Add in `RemCTL Studio · Demo` with an all-day September 30 date, flag, and notes. A standalone RemCTL MCP read verified those values. An inspector edit saved updated notes, independently verified through MCP. The workspace then deleted the test reminder; MCP confirmed `deleted: true` and `recoverable: true`. No existing reminder was modified.

The previous checkout marketplace registration had to be removed before the installed-app source could be added under the same name. This upgrade step is now included in the plugin guide.

## Publication boundary

No tag or GitHub release has been created. The public download remains unavailable until the release is published. Apple silicon is the release target.
