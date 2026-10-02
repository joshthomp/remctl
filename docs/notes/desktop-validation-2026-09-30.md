# Desktop acceptance — September 30, 2026

Installed locally as `remctl@remctl-local` version **0.1.15**. The interface runs inside Codex for Mac through the standalone RemCTL MCP server and signed Capability Host. No Mac Remote adapter is involved. This is a local development delivery; nothing was pushed or published.

## Installed checks

- CLI, MCP server, plugin adapter, workspace reader, generated HTML and runtime match the checkout byte for byte.
- Plugin manifest, MCP configuration and artwork match the installed plugin cache.
- Capability Host icon matches the four-circle source ICNS; the app retains its signing identity and permission grants.
- Installer doctor: 16 checks, one expected direct-caller access warning, zero failures. Effective access through the signed host is ready.
- Native Reminders list artwork: 71 symbols rendered locally, alongside each list's actual emoji and color.
- Global sidebar entry opens the workspace, with working narrow and full-width layouts.

## Computer acceptance

Tests used fake data in `RemCTL Studio · Demo` (list 175), its demo group, a reusable checklist and a Groceries list. Existing user reminders were not changed.

| Flow | Observed result |
| --- | --- |
| Command palette and keyboard selection | Native ⌘K opened RemCTL Commands; Shift–Down selected two reminders and exposed bulk controls. |
| Context menus | Native right-click opened reminder, list and section actions. |
| Section drag | Reminder 4989 moved from Build to Launch; MCP readback confirmed it. |
| Multiple-item drag | Reminders 4984 and 4985 moved together from Build to Launch. Tags, dates and the weekly recurrence remained intact. |
| Calendar drag | Reminder 4980 moved from September 30 to October 1, preserving 14:30 and its timed status. |
| List drag | Groceries list 179 moved into group 176; MCP readback confirmed the parent. |
| Quick entry and subtasks | Created 4991 and child 4992 through the interface, once each. Completion and Undo restored the parent to incomplete. |
| Native rich form | List thumbnails, tags and image selection worked. An accepted local file became an image attachment on 4990 without exposing its private path to the model. |
| Recovery | Deleted and restored 4990 through the interface. Original numeric ID, UUID, tags and attachment survived. |
| Smart list | Created an orange 🎯 list with an all-match tag/flag/list filter. It returned the two matching demo reminders. |
| Templates | Saved the demo list as a template and applied it to a new list with 14 reminders. |
| Groceries | Created list 179 with a 🥬 icon and Groceries categorization enabled; readback confirmed its type and language. |
| File entrypoint | Exported and opened a `.remctl` file, edited and saved it through host file APIs, then reviewed an import that created 4990. |
| Conversation handoff | Reviewed and sent a disposable prompt to a new conversation. The new conversation correctly acknowledged reminder 4991. |
| Composer mentions | Typed @RemCTL, opened the nested picker and inserted a reminder resource chip. A disposable conversation resolved it to “Verify subtask capture · Demo”, ID 4992. The installed compact lookup took 277 ms, down from about five seconds before removing detail hydration. |
| Dark appearance | Found and fixed host text-color inheritance. The installed global app now renders readable titles, controls and cards. Restored the System preference after checking. |

The native screenshots show the installed app, not a browser mock: [light workspace](screenshots/desktop-workspace.png) and [dark columns](screenshots/desktop-dark.png). Temporary acceptance tabs were closed; the demo workspace remains open.

## Repairs found during acceptance

- Replaced internal HTML drag sessions with pointer-based moves because the embedded Mac surface lost drop events. External image/link drops retain the native drop path.
- Preserved calendar times, multiple-selection payloads and recurrence representations.
- Fixed private recovery arguments, native image-file handling and a false file-save conflict caused by the app's own subscription notification.
- Removed duplicate name/ID fields, added human-readable list/template/smart-list choices, and restored the required Create List name field.
- Kept large list-artwork payloads in the app-only catalog instead of repeating them in model-visible snapshots.
- Added a code fingerprint to the MCP configuration so new connections distinguish development builds. Existing desktop app workers can retain old code until reconnected; the old mention-search worker was retired and its automatic replacement was verified.
- Accepted the desktop host's extra mention-picker `path` field while retaining strict validation of all other arguments.

## Automated coverage

Passed TypeScript checking, production bundling and UI interaction contracts (hierarchy, collapsed subtasks, range selection, calendar time preservation and recurrence fidelity). Generated forms, settings and entrypoints validate against the official OpenAI extension SDK.

Python suites passed: desktop plugin (12), MCP server (86), CLI (443), focused CLI fixes (8), installer lifecycle (19), planner (6), Capability Host runtime (17), capability archive (4). Installer and uninstaller shell syntax and Git whitespace checks also passed. Suites were rerun when their implementation changed; unchanged broad suites were not repeatedly rerun after visual-only changes.

## Boundaries

Car-trigger smart-list reads cannot be evaluated from the available alarm metadata and report an explicit unsupported error. Shared-list assignment needs actual members returned by Reminders; no existing shared list was modified to test it. Private ReminderKit capabilities depend on the installed macOS version.

The `.remctl` import is a reviewed copy operation, not a backup restore: identity, completion state, private metadata and attachments are explicitly reported as omitted. Recently Deleted is the recovery path that preserves identity and hierarchy.

This acceptance pass covers representative installed interactions and automated contracts, not every permutation of every RemCTL command, cross-device iCloud synchronization or every desktop host version.

## Expanded acceptance — 0.2.2

The September 30 follow-up adds visual smart filters, tag chips, attachment preview/download, Groceries type/language controls, JSON/CSV export, and MCP Events. It retains the four-circle translucent icon for the plugin and Capability Host.

Verified in the installed Mac application:

- Added `powerdemo` to reminder 4979; standalone MCP readback and a newly opened inspector preserved all three tags.
- Opened the attached image in the lightbox, downloaded it through the inspector, and opened the result in the host file viewer. The output was a 261,439-byte PNG with mode 0600.
- Created “RemCTL Studio · Next Seven Days” (smart list 180): next seven days, include `demo`, exclude `blocked`, restricted to demo list 175. Visual preview and saved list both returned eight reminders.
- Restored Today after a development connection was closed. A fresh standalone MCP read and workspace read returned the 15 reminders. The new interface shows unavailable reads explicitly and `—` during loading; failure is never presented as an empty list. Running workers retain the HTML matching their published resource URI.
- Exported smart list 180 to CSV through the installed 0.2.2 UI. The host file viewer showed exactly eight rows, all from demo list 175.
- Installed source parity passed for MCP, Events, plugin, workspace reader and generated HTML; the 0.2.2 plugin cache matched its manifest, configuration and icon. Installer doctor again reported 16 checks, one expected direct-access warning and zero failures.
- Created Milk (5007) in demo Groceries list 179; native inspector categorization completed and MCP readback showed Dairy, Eggs & Cheese. Changed its grocery language to en_GB through the standalone typed tool, verified it, and restored en_US. The UI displayed the saved type and language controls.
- An unsaved inspector note draft survived a completed refresh; Cancel restored the original note without saving it.
- The installed signed-host Events read succeeded through standalone MCP with 2,179 reminders and 13 lists, including the grocery demo.
- Activity loaded all ten advertised Events types. A fresh demo chat and the native Scheduled screen offered no usable native Events subscription interface. No ChatGPT automation was reported as active.

The three isolated automation demos in `tests/demo_event_automations.py` passed completion, flagged-update and due-boundary triggers over authenticated MCP HTTP and real signed HTTPS delivery. They also verified tag filtering, no historical replay, no duplicate runs from unchanged reads, and stop-on-unsubscribe. These do not prove a ChatGPT receiver or live Apple Reminders observation.

A separate native MCP check completed and reopened demo Milk (5007), captured each state through the installed full Events reader, and replayed only those demo rows through the installed Events module. It produced exactly one completion and one reopening event; an in-process receiver verified both signatures. The reminder was restored, temporary state removed, and no installed subscriptions remain from these checks. This verifies real-state compatibility separately from HTTPS delivery and native ChatGPT activation.

Follow-up suites passed: Events (18), desktop plugin (15), MCP server (87), installer lifecycle (19), capability archive (4), TypeScript checking, UI interaction contracts, and official extension SDK schemas. Final targeted reruns cover changed code. Broad CLI suites from the initial pass were not repeated for unrelated UI work.

Additional acceptance repairs: exports preserve the visible query (including a smart list and search), and generic CLI metadata cannot render as an undefined reminder card.

The [0.2.2 inspector screenshot](screenshots/desktop-inspector-022.png) shows the installed app. The [Codex plugin guide](../desktop-plugin.md) documents installation without gallery submission.

## Updated ChatGPT acceptance — build 12404

ChatGPT 26.928.21956 was tested in three fresh conversations: Codex, ChatGPT Work running locally, and regular Chat with the standalone RemCTL plugin explicitly selected. Both local work conversations opened the installed workspace. All three reported that native Events subscription and host-managed callback/signing-secret provisioning were unavailable. No subscription was claimed or created, and the demo reminder was left unchanged. [Events evidence](events-2026-09-30.md#app-update-retry--build-12404) includes conversation identifiers and a screenshot.

The updated plugin page now exposes RemCTL's native settings. This retry changed documentation only, leaving the installed runtime and signing configuration intact.

## Final desktop refinement — Events deferred

Federico deferred Events on September 30. Activity and Watch entry points are hidden; the protocol implementation is retained for future work. The remaining desktop scope was refined and installed locally, without a gallery submission or push.

The inspector now keeps drafts per task while the workspace stays open, puts Save and Cancel below its fixed header, supports Command-S, and exposes a date picker with explicit optional time. Attachments appear beside the task's core details. Section disclosure buttons collapse their rows, keyboard range selection skips collapsed sections, and wide task lists have a readable maximum width. Narrow panes automatically close the sidebar and provide explicit dismissal controls. Native date/time controls follow the selected app appearance.

Installed acceptance in ChatGPT 26.928.21956/build 12404 used the standalone plugin and demo list 175. Conversation `01a0f143-5ce3-7101-b157-225b4624b431` verified Command-S by saving demo reminder 4979 for October 1 at 09:00. Standalone MCP confirmed `allDay: false`. Removing the time and choosing Today restored September 30 with `allDay: true`; MCP readback confirmed restoration. Image preview, draft retention and cancellation, arrow-key range selection, section collapse, and Command-K were exercised in the native app.

Conversation `01a0f147-e1cb-7442-a3cb-083d3b749aad` verified the final responsive repair by resizing from 1341 to 390 points: the sidebar closed automatically, the inspector fit the pane, and the sidebar could be reopened and dismissed. Evidence: narrow inspector (`desktop-narrow-final.png`, not kept in the repo), light desktop (`desktop-light-final.png`, not kept in the repo).

Final build `53e02600ba62dc06` passed TypeScript, UI interaction contracts, official extension schemas, production bundling, and whitespace validation. Installed HTML and Python plugin/workspace/MCP files matched source byte-for-byte. Installer diagnostics reported 16 checks, one expected direct-caller access warning, and zero failures; signed-host access and existing permission identity were preserved.

The final build also passed the medium-width check in conversation `01a0f14c-4a82-7390-8693-5ad649026ecc`: at 785 points, the sidebar closes automatically and heading controls wrap, leaving room for the task list beside Details. Dark native date controls remain legible. Evidence: medium-width dark workspace (`desktop-medium-dark-final.png`, not kept in the repo). Generated HTML SHA256 prefix: `06e2d56c86bc7fa7`.

## Rich rows, floating capture and sidebar pins — September 30

Installed native acceptance used the standalone global Reminders entry in ChatGPT, backed by the signed build `19947cb0574b92bf`:

- Today displayed the actual saved Maestro Snap artwork, note and time, under Afternoon. Weekly 531 displayed the original Unread Portugal photograph and AtAt hero image, alongside readable App Radar notes and nested subtasks. Image attachments also appeared inline.
- Quick Add opened above the host composer. Escape preserved its draft. Creation of demo 5011 returned exactly the selected list, note, October 1 at 09:00, high priority and flag through standalone MCP readback.
- Command-Return created demo 5012 once and left an empty, focused panel. Return created demo 5013 once and closed the panel. All three temporary reminders were removed through normal recoverable deletion after testing.
- Clicking the regular-list pin on demo list 178 saved `pinned: true` and moved it above unpinned lists. Custom smart list 177 also persisted its pin. Both were restored to `pinned: false` through the interface and verified with MCP.
- Old conversation app tabs retained cached HTML after updating. The global Reminders entry loaded the installed build. Open a fresh workspace after an update.

The acceptance pass found two final refinements: compact date-editor layout inside Quick Add, and clearing successful creation drafts even if Reminders has not returned a numeric ID yet. Final installation verification is recorded after packaging below.

### Pinned tiles and compact artwork

Compared Apple Reminders and ChatGPT directly with Computer. Build `4e6776f1b435146a` displays Today, Scheduled, Completed, Reminders, Shopping, Projects, Work and Weekly 531 in the native order. Built-in hidden-state metadata controls the tile grid; other views remain available below. Regular and custom smart pins share the grid without duplicate rows, including lists inside groups. The sidebar scrolls as one area.

Native acceptance pinned grouped demo list 175 into one tile, then restored it to group 176. Smart list 177 appeared as an orange tile with count 0; its right-click menu unpinned it. Standalone MCP confirmed both restored pin states. The Nowdex link card and inline image are 360 pixels wide; the image opens full-size and Escape returns focus to its preview button. Quick Add’s date and optional time controls are aligned inside the floating panel.

The host’s disappearance during testing was traced to the plugin loader rejecting absolute stdio executable paths. The corrected bare `sh` launcher restored registration after disabling/re-enabling RemCTL; no privacy reset was required. The distribution worktree owns the launcher regression check and matching signed artifacts. A final visual correction removes the Completed count, matching Apple Reminders; final installed readback follows.


Final delivery build `36b8d2553f71a011` passed native readback after refreshing the plugin connection. The Completed tile has no crowded count; pinned ordering, Weekly 531 artwork and smaller inline images are visible, and the global entry remains registered. The matching installed host has all three permissions and passes a real protected-store read. Final local screenshot: `/private/tmp/remctl-acceptance/pinned-compact-final.png`. No remaining UI changes were identified.
