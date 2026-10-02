# RemCTL 2.2.1 release validation

Published on October 2, 2026 from commit `3944548`, tagged `v2.2.1`.

The release includes the fixes for archived list colors (#53), unwanted plugin workspace tabs (#52), renamed iCloud accounts (#33), and stock 1.7.1 upgrades (#56). The [fix validation record](pr-fixes-2026-10-02.md) describes the reproductions, implementation choices, and live checks before publication.

## Release and installation checks

- Both Python 3.13 and 3.14 passed 871 tests, with six optional distribution checks skipped, before the version-only release changes. The workspace build, type checks, interaction tests, and SDK checks passed again for 2.2.1. All 23 desktop-plugin tests and four applicable distribution tests passed.
- The actual Developer ID release bundle passed isolated installation, upgrade, rollback after an injected failure, uninstall, and tamper rejection.
- All 12 packaged client modules, 13 plugin and marketplace files, the installer scripts, generated interfaces, and the host's embedded Python archive match the release source. Both app versions are 2.2.1.
- Apple accepted both apps and the disk image. The apps and disk image were stapled and validated. A quarantined copy of the finished disk image passed Gatekeeper; both mounted apps passed strict signature verification and Gatekeeper as Notarized Developer ID software.
- The public [2.2.1 release](https://github.com/viticci/remctl/releases/tag/v2.2.1) is published, not a draft or prerelease. Both assets were downloaded without authentication, and their sizes and checksum match the local release.

| Artifact | Verification value |
| --- | --- |
| App notarization submission | `f40353bf-da9d-4380-a9ff-40c27d7dd005` — Accepted |
| Disk image notarization submission | `6150a7b4-1196-453e-82fc-ff2448a5944f` — Accepted |
| `RemCTL-arm64.dmg` SHA-256 | `0ebf3a78be20dd08d241cc7ffe573716d2244e1f6d01818a4c7df54c2e5a3e26` |
| Bundled protected Python runtime ID | `60a8db3f2731c77b0d7b885066686776e73f685eec201ee676ee9c7d0d37794d` |

## Installed acceptance

This Mac was updated through the official source installer using the existing Developer ID identity and protected Python runtime. This verifies the source-built 2.2.1 installation; it is not a claim that the newly packaged disk image's Python runtime was installed on this Mac. That runtime requires an administrator password. The release bundle's installation checks used an isolated prefix.

- The installed CLI reports 2.2.1. Doctor reports the signed capability-host route ready, with zero failures and warnings.
- All 12 installed client modules, 13 plugin and marketplace files, generated interfaces, and the complete embedded Python archive match the source. The app signature verifies; its CDHash is `be1f2bbfc5a1bef624e530803c2df9a368d57456`.
- Fresh installed MCP sessions report 2.2.1 and pass both legacy and modern protocol paths: 21 standalone tools and 67 plugin tools. List reads, invalid-ID errors, explicit workspace resources, and standalone widget resources passed. Ordinary plugin tools and results omit interface metadata.
- Codex and Claude Code plugin caches were updated to 2.2.1 and their files match the source. Claude Code requires a new session to apply its plugin update.
- Before the version change, all 11 live edit checks and 34 private-feature checks passed. Two direct-helper checks were intentionally skipped; their signed-host equivalents passed. Installed MCP writes, workspace mutation replay, Claude Desktop's configured MCP transport, authenticated tailnet reads, and unauthenticated rejection also passed. Fixtures were cleaned up and checked as recorded in the fix validation record.

## Coverage limits

Testing ran on Apple silicon with macOS 27. It does not establish acceptance on Intel, older supported macOS releases, or physical iPhone/iPad clients. Renamed accounts were tested through the actual Swift classifier with synthetic account records and a real read-only account-ID mapping, without changing account settings.

Claude Code strict plugin and marketplace validation passed. Its unchanged native mod had passed all five tests during fix validation; the release-time rerun was unavailable because Claude's rollout switch disabled the test runner. A fresh Claude agent conversation remained blocked by the account's usage limit. Codex's explicit workspace passed native checks; automatic tab behavior was checked through the installed plugin protocol, not a fresh native agent conversation.

## Contributor follow-up

PRs [#53](https://github.com/viticci/remctl/pull/53#issuecomment-5953766308), [#52](https://github.com/viticci/remctl/pull/52#issuecomment-5953767251), and [#33](https://github.com/viticci/remctl/pull/33#issuecomment-5953768092) were closed after publication, with explanations posted by `viticci`. The first two commits retain their contributors' authorship; the account fix was reworked for the current signed-host architecture and credits the original proposal. Issue #56's fix is included in the release; the issue was not closed as part of this request to close the PRs.

The merged `codex/remctl-pr-fixes` worktree was archived in Codex and its remaining clean checkout removed with Git. Both that branch and the older merged `claude-code-plugin` branch were deleted, along with temporary review refs. Only the primary checkout and `main` remain locally; the remote has only `main`. The pre-existing untracked `.playwright-mcp/` directory was preserved.
