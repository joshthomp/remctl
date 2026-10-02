# Distribution implementation and validation

Historical artifact: the redesigned launch build has a separate [2.0 release validation record](release-2.0.0-validation.md). The artifact and installed-state claims below describe the earlier build.

September 30, 2026. Local branch: `codex/remctl-distribution`. No push, main update or public release.

## Implemented paths

- `./install.sh`: download the native-architecture DMG, verify the MacStories Developer ID and Gatekeeper acceptance, then install the immutable app and matching CLI.
- `./install.sh --from-source`: fetch checksum-pinned Python, compile the host/helpers, create or reuse an owner-only local signing key, verify the resulting app, and run the same installer.
- `--prebuilt APP`: install a reviewed existing build. Local certificate builds require `--allow-local-build`; ad-hoc signatures fail.
- Runtime installation uses an administrator-authorized native host command. It copies only the manifest-verified Python tree into a root-owned content-addressed directory. It never edits an existing system Python.
- Staged update, rollback and uninstall retain the existing ownership-manifest checks. Switching signing identities requires explicit `--migrate-signing`.

## Current evidence

| Check | Result |
| --- | --- |
| Complete arm64 local app build | Passed, including Python 3.13.15 and shared icon |
| One-command source build and dry run | Passed |
| Strict nested code signature verification | Passed |
| Persistent local key, changed binary under same identity, other-key rejection | Passed |
| Keychain search list preservation and private-file checks | Passed |
| Pinned archive extraction, traversal and symlink rejection | Passed |
| Isolated prebuilt install, update, injected publication failure, rollback, uninstall | Passed |
| Tampered bundle rejection and non-admin runtime-install rejection | Passed |
| Existing installer suite | 24 tests passed |
| Capability transport/archive/planner/diagnostics | 99 tests passed |
| CLI/MCP/desktop/events | 563 tests passed |
| Native host original identity, post-start resign rejection, sealed invocation/broker | 4 tests passed |
| Distribution-focused tests | 9 tests passed, including explicit signing migration and protected runtime reuse |
| Default download with no published artifact | Reports HTTP 404 and exits with failure; no silent fallback |
| Notarization of a local certificate build | Rejected before submission |
| Packaged license notices | Project, Python and locked UI dependency notices included |
| Protected free-build Python installation | Passed: manifest bytes, root ownership and non-writable modes verified |
| Actual packaged shell launcher | Passed: protected Python starts the CLI and reports 2.0.0 |
| Free-build persistent sealed broker | Passed: repeated live status requests, with missing permissions reported correctly |
| Free-build Reminders permission across an app update | Passed: changed code hash, identical local certificate, authorized state and real sealed EventKit read without another prompt |
| Signed-release protected runtime and broker | Passed: manifest bytes/root ownership, packaged CLI and live sealed broker |
| Developer ID app and DMG notarization | Accepted; both tickets stapled and validated |
| Gatekeeper execution and disk-image opening | Both accepted as Notarized Developer ID |
| Notarized payload installation | Default signature policy passed; isolated install/update/rollback/uninstall passed |
| Free source build with only Apple tools on PATH | Passed with Apple Python 3.9.6 and no Homebrew or separately installed Python |
| Existing runtime reused without elevation | Passed for local and Developer ID builds; missing runtime returns 77, damaged runtime returns 65 |

Isolated lifecycle tests use temporary prefixes. Live permission and runtime checks use the normal installed app and its LaunchAgent; they are separate evidence.

## Final coordinated source

Source commit: `ec32a0e`. Plugin build: `36b8d2553f71a011`.

Both `dist/source-delivery/RemCTL Capability Host.app` and `dist/release-delivery/RemCTL Capability Host.app` contain the final rich previews, floating Quick Add, native-style pinned tiles, smaller inline previews and capture corrections. Packaged workspace/server files and plugin configuration match source byte-for-byte. The generated HTML SHA-256 is `fcccb4ee9048052a3a1f19acd4ca65dd363e0b855495a862425ac3636a628141`.

The free artifact was built by `./install.sh --from-source --build-output dist/source-delivery --dry-run --shell-completions none`, using only `/usr/bin:/bin:/usr/sbin:/sbin` on PATH, temporary install paths and the normal persistent signing key. Apple Python 3.9.6 orchestrated the build; the packaged runtime is Python 3.13.15. Strict nested signatures passed. The newly signed runtime generation was not installed; live free-build evidence below uses the earlier installed generation.

The Developer ID artifact preserves the previously verified signed Python tree and protected runtime path. UI updates therefore reuse that runtime without another administrator prompt. Both artifacts passed final source parity checks. TypeScript checking, interaction contracts, SDK schemas and production bundling passed after the final capture and sidebar refinements, along with 18 desktop and 5 rich-preview tests. The coordinated thread verified actual artwork, Quick Add values and keyboard capture, plus regular and smart-list pins in the native ChatGPT workspace; see [desktop acceptance](desktop-validation-2026-09-30.md#rich-rows-floating-capture-and-sidebar-pins--september-30).

## Final notarized artifact and installed verification

`dist/release-delivery/RemCTL-arm64.dmg` is the final local artifact. Earlier `release-*` images are superseded. The app and DMG passed notarization, ticket stapling/validation and Gatekeeper execution/opening checks.

- App submission: `8bfbd380-5d32-4389-b587-5b4b05c3be50` (Accepted).
- DMG submission: `05db6fd1-8e2f-453a-bd83-0ae5e333e495` (Accepted).
- DMG SHA-256: `aab9e8468089bfa1a050fdf13f9693674c545c40fc46aa2fe1197370a2d6a834`.
- Installed code hash: `f88a3791a02ceaab159f2247869434ea8e981077`.

The final app was installed at the normal location through `--prebuilt`, without signing migration or administrator elevation. The protected runtime was reused and the MCP HTTP endpoint restarted and passed its health check. `doctor --for-agent --json` returned `ok: true`, zero failures, and authorized Full Disk Access, Reminders and Automation. A real protected-store `today --json` read returned 12 reminders. No new permission prompts appeared. The coordinated thread then verified the final native workspace: Completed count removed, pinned ordering and smaller artwork present, and the global entry still registered after reconnect.

Installed workspace/server files, plugin configuration and the refreshed plugin cache match source. The CLI body matches source after its expected protected-Python launcher header. The two isolated preview LaunchAgents were stopped and verified absent; production remains running. Private logs are `/private/tmp/remctl-release-delivery-install.log`, `/private/tmp/remctl-release-delivery-doctor.json` and `/private/tmp/remctl-release-delivery-read.json`.

## Release limits

- Intel runtime and advertised minimum-macOS acceptance remain unverified because suitable test systems were unavailable. Do not publish those claims from cross compilation alone.
- No GitHub release was published, and nothing was pushed or changed on main. The default public download currently fails with HTTP 404 because there is no published artifact. The local signed DMG and `--prebuilt` path are available now.
- macOS still requires each initial privacy grant. Ordinary updates retain the signing identity and preserve those grants. Deliberately switching between local signing and Developer ID, or losing the local key, requires permission migration.

## Build a release locally


```bash
python3 scripts/build_distribution.py --release \
  --identity 'Developer ID Application: …' --output dist/release-arm64
scripts/notarize_distribution.sh dist/release-arm64 --asc
```

`--asc` uses the existing App Store Connect CLI credential. Alternatively pass a `notarytool` keychain profile as the second argument. The script submits the app, requires Accepted, staples and verifies it, creates a DMG with the installer, submits and staples that DMG, checks Gatekeeper, and writes a SHA-256 receipt. Rejected submissions retain result/log files. Notarization uploads to Apple; it does not publish a GitHub release.

Build on each supported architecture. Artifacts are `RemCTL-arm64.dmg` and `RemCTL-x86_64.dmg`. Do not publish an architecture before its runtime and permission checks pass.

## Plugin discovery correction

The native app dropped RemCTL after a plugin refresh because the Agent Plugins loader rejects absolute stdio command paths. Its diagnostic named `/bin/sh` as invalid; the installed launcher itself still initialized and advertised all 67 tools. Changing the plugin command to bare `sh` preserves the exact `exec "$HOME/bin/remctl" mcp` invocation and the protected runtime.

The focused launcher test checks a permitted bare command and actual forwarding to the installed CLI under a home path containing spaces, using only `/usr/bin:/bin` on PATH. It passes without external Python. After refreshing the plugin cache and cycling the native plugin switch off and on, the global Reminders entry returned. This was plugin discovery, not a macOS privacy failure; no privacy grant was reset.

## Signing and protected runtime

After Federico approved creation, Xcode created Developer ID Application for team `4W35M4UN6R`, certificate SHA-1 `4F0E9E16BE3065B93E959199C1A4EFA21041C80A`. Initial M5 and M3 checks had found only Apple Development identities. The existing MacStories App Store Connect credential submitted artifacts without exporting its key.

The signed release uses `/Library/RemCTL/Python/a85b3a52b0d60214bfba8a3847ddded0ba077989138eda6152c41a43c6de1592`. Its bytes, root ownership and non-writable modes were verified. The installer distinguishes a missing runtime needing administrator authorization (exit 77) from invalid runtime data (exit 65); a valid runtime is reused without elevation. Installer lifecycle (19), diagnostics (5) and distribution checks (9) passed after this change.

Before live replacement, the old app, client directory and LaunchAgent were saved in `dist/pre-release-install-backup`. Each successful Developer ID transaction restarted and health-checked the existing MCP HTTP endpoint. The initial Apple Development-to-Developer ID migration required replacing the obsolete Full Disk Access entry with the exact installed app. The final source-build migration and restoration were deliberately sequential; the working notarized app was restored afterward.

The first experimental DMG was unsigned and failed Gatekeeper's disk-image opening assessment despite Apple accepting notarization. The script now signs the image with the app's exact Developer ID, then requires notarization, ticket validation and both app-execution and disk-image-opening assessments.

## Free-build permission continuity completed


The free build was installed at the normal app path with the existing protected runtime. After its initial macOS grants, `doctor --for-agent` reported all three permissions authorized and a real protected-store `today --json` read returned 12 items. The app was then updated with the transactional installer, using the same local certificate and a changed build number/code hash. All three permissions remained authorized and another protected-store read returned 12 items, without requesting any new permission.

- Local signing certificate: `CA5B3C8F2DDA499D8DFD35B004266CF94720C368`.
- Original code hash: `8f543c49bd0adcd7eb237b3fe75cb5c50b104366`.
- Updated code hash: `96a5e2b290fa049cd9233c867b8379418b558205`.
- Evidence: [distribution-permission-continuity.json](distribution-permission-continuity.json).

This verifies ordinary updates within the free-build identity. Switching between that certificate and Developer ID is a deliberate identity migration and needs new grants. The installer refuses an unrequested identity change. Following this test, the original final notarized app was restored; its Full Disk Access grant was restored, and its Reminders grant was restored. The installed notarized host again passed `doctor --for-agent` with all three permissions, a protected-store read, and the visible ChatGPT workspace Refresh without an error.
