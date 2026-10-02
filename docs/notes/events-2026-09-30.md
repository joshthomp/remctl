# RemCTL Events

> Deferred at Federico’s request on September 30. The desktop app hides Activity and Watch entry points. The implementation and protocol test evidence below remain for future work; native ChatGPT event automations are not part of the current release scope.

RemCTL implements the webhook profile of the [OpenAI MCP Events guide](https://developers.openai.com/plugins/build/mcp-events), reviewed September 30, 2026. Discovery advertises `events: {}`. `events/list`, `events/subscribe` and `events/unsubscribe` use the same authenticated principal as tools on both supported MCP protocol versions.

## Events and filters

| Event | Meaning |
| --- | --- |
| `reminder.created` | A new reminder appeared after the subscription began. |
| `reminder.updated` | Reminder fields changed, including notes, tags, recurrence and attachments. |
| `reminder.completed` / `reminder.reopened` | Completion changed in either direction. |
| `reminder.deleted` / `reminder.restored` | An observed reminder disappeared or returned with the same identity. |
| `reminder.assigned` | Assignment changed. |
| `reminder.due` / `reminder.overdue` | A due boundary was crossed while incomplete. All-day reminders become overdue at the following local midnight. |
| `list.updated` | A list or group appeared, changed or disappeared. |

Reminder subscriptions can combine list IDs, reminder IDs, any/all tags, flag, priority and a title substring. List subscriptions accept list IDs. Scope is checked against a complete host snapshot before accepting a subscription. Payloads contain identity, a title, a resource link, changed field names and compact previous/current state. Note text, attachment bytes, file paths and signing secrets are excluded. Private fields in the persisted comparison baseline are hashes.

## Delivery

The existing MCP process observes the signed Capability Host roughly every five seconds while subscriptions exist. A cross-process lock permits one observer; the existing installed HTTP service can keep observing when a conversation closes. This does not install another background service. The Mac must be awake and at least one RemCTL MCP process must remain running. With no subscriptions, no Reminders snapshots are collected.

This is **observation of net changes**, not an Apple change journal. A change reversed between reads can be missed. No history is replayed: cursors are null. Restores are identifiable only when the original deletion was observed. A failed, incomplete or oversized read never becomes a deletion event. The current full-snapshot ceiling is 20,000 reminders; exceeding it reports failure rather than silently dropping rows.

Subscriptions and a bounded delivery queue survive process restarts in `~/.config/remctl/events/events.sqlite3` (mode 0600, directory 0700). Default lifetime is one day, capped at seven days and never longer than a positive client request. Clients must refresh before expiry. Stable subscription identity includes the principal, callback URL, event name and canonical arguments. Expiry, revocation and unsubscribe remove pending deliveries and secrets.

Callbacks must use HTTPS. Connection-time DNS checks reject non-public addresses; the socket is pinned to the validated address, while TLS verifies the original hostname. Redirects are not followed. The signed verification challenge must be echoed before a subscription is accepted. Verification is scoped to principal and URL, rate limited, and expires after ten minutes. Event bodies use Standard Webhooks HMAC-SHA256 headers and the subscription ID. Retries keep the event ID and body, with fresh timestamps/signatures; secret rotation retains a five-minute overlap. Transient delivery errors receive bounded backoff, with eight attempts maximum. HTTP 410 pauses delivery; 413 is not retried. Responses and secrets never appear in diagnostic errors.

## Desktop use and current host limit

Activity shows real subscriptions, pending counts, delivery results and observation failures. **Watch this reminder** prepares a scoped monitoring request, which the user reviews before sending to a new conversation. This is a request to the host to establish a native subscription; it does not itself subscribe and is never presented as one.

On the tested September 30 Codex for Mac installation, the local plugin page exposes MCP servers and skills but no Events section. A fresh acceptance conversation opened RemCTL successfully, then reported that it had no native Events subscription interface or host-managed callback URL/signing secret. Therefore **ChatGPT-triggered webhook delivery is not verified on this host**. No polling automation, public tunnel or replacement service was created to disguise that limitation.

Revalidation used a fresh process of the installed `~/bin/remctl mcp`: `server/discover` returned protocol `2026-07-28`, `events: {}`, and `resultType: complete`; `events/list` returned all ten definitions. Refreshing the native plugin directory still showed RemCTL 0.2.2 with one MCP server and two skills, without an Events section or subscription action ([host screenshot](screenshots/events-host-022.png)). The guide's required host discovery/subscription/chat-invocation sequence therefore remains incomplete even though direct protocol discovery succeeds.

Protocol tests cover signed verification, authenticated HTTP ownership, filter misses, durable retry, expiry/revocation, rotation, unsubscribe, private-address rejection, permanent HTTP failures, incomplete snapshots and daylight-saving boundaries. These tests establish server behavior; they do not establish a ChatGPT receiver or a resulting chat invocation.

### App update retry — build 12404

After updating ChatGPT to 26.928.21956 (build 12404), three fresh conversations tested the same native `reminder.completed` subscription scoped to disposable reminder 5007:

- Codex: `01a0f127-99a7-7970-a8a3-36b1387b111f`.
- ChatGPT Work, explicitly running on this computer: `01a0f12d-f688-72f0-8beb-582329dbd8e6`.
- Regular Chat, with standalone RemCTL selected from the plugin picker: `6abcb7fb-9024-838f-8511-f1e03438c9b9`.

All three reported no callable native Events subscription interface or host-managed callback/signing-secret provisioning. The Work conversation successfully opened the RemCTL workspace. The updated plugin page exposed native settings, but still no Events section. No subscription was established and reminder 5007 was not changed during this retry. The [regular Chat result](screenshots/events-chat-build-12404.png) records the final acceptance failure. This demonstrates the limitation in these tested sessions; it does not establish availability for every account or host build.


## Repeatable demo automations

Run `PYTHONPATH=.:tests python3 tests/demo_event_automations.py` from the checkout. It creates three temporary subscriptions through authenticated MCP HTTP, verifies the callback challenge, and sends actual HTTPS requests to a local test receiver:

| Demo automation | Trigger | Verified result |
| --- | --- | --- |
| Completion receipt | Complete a reminder tagged `eventdemo`. | One signed completion receipt for “Ship the demo”. |
| Flagged change digest | Change a flagged reminder tagged `eventdemo`. | One signed update receipt for “Review the draft”. |
| Due-time nudge | A tagged, incomplete reminder crosses its due time. | One signed due receipt for “Join the rehearsal”. |

All three ran on September 30, 2026. Unrelated tags, unchanged snapshots, and post-unsubscribe changes produced no automation runs. The fixture removes its subscriptions, private state and temporary certificate when it exits. Its virtual clock makes the due test deterministic. Only the fixture permits its loopback receiver and temporary CA; the installed server retains public-address checks and normal certificate verification.

These are local protocol demos with synthetic reminder data and a deterministic receiver action. They are **not active ChatGPT automations**, do not call a model, and do not access live Apple Reminders. The native Scheduled screen was also inspected: it offered task starters, but no RemCTL event trigger configuration. Native host activation remains unverified.

A separate live observation check completed and reopened Milk (5007) in the disposable Groceries list through native standalone MCP tools. The installed signed-host Events reader returned each state, including the completed reminder. Replaying those captured demo snapshots through the installed Events module produced exactly one `reminder.completed` and one `reminder.reopened` delivery with verified signatures. The receiver for this check was an in-process verifier; HTTPS is covered by the three protocol demos above. The reminder was restored to incomplete, temporary state was removed, and no installed subscription was created. This checks real Reminders state compatibility without claiming a native ChatGPT invocation.

When a host exposes MCP Events, practical requests are: “When a reminder in my release list is completed, summarize what remains”; “When a flagged work reminder changes, explain the change”; and “When my rehearsal reminder becomes due, show its checklist.” Resolve actual list/reminder IDs, obtain a host-managed callback, and accept the subscription before saying any monitoring is active.
