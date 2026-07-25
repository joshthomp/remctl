# Multi-account support (optional extension)

RemCTL's core is single-account by design: it reads the one "live" Reminders
store and writes through iCloud. Reminders keeps a **separate SQLite store per
connected account**, so Exchange, Google, other CalDAV, and Local accounts are
invisible to the core tool.

`remctl_accounts.py` adds support for those accounts as a **drop-in optional
module**. It is not required, not imported by default behavior, and deleting
the file returns RemCTL to stock.

## Integration contract

The entire footprint in core `remctl` is **22 added lines, 0 modified or
deleted lines**, in four hunks:

| Hook | Purpose |
|------|---------|
| `try: import remctl_accounts` | Optional; `ImportError` leaves `remctl_accounts = None` |
| `_db_opener = None` in `open_db()` | Extension point letting a caller redirect reads to another store |
| `remctl_accounts.register_cli(p, sub)` | Adds `--account`/`--all-accounts` and the `accounts`/`config` commands |
| `remctl_accounts.install(cmds, a, sub)` | Wraps the command dispatch table |

Every hook is guarded by `if remctl_accounts:`. With the module absent, core
runs exactly as upstream — verified by the full upstream test suite.

## Why wrapping instead of editing commands

No core command is modified. Instead:

- **Reads** — `remctl._db_opener` is bound to the target account's store, and
  the *unmodified* core handler runs against it.
- **Writes** — an `account` field is injected into outgoing bridge payloads;
  `remctl-bridge` resolves a `(list, account)` pair to a stable calendar.
- **Aggregation** — for `lists`, `search`, `today`, etc. the core handler is
  run once per account and its output merged (JSON payloads are parsed and
  tagged with `account`/`accountType`; human output gets per-account headers).

The practical consequence: **upstream changes to those commands are inherited
automatically** rather than needing to be re-merged. When upstream added list
groups and inline images, multi-account output gained both for free.

## Opting in

Nothing above activates unless the user asks for it:

```bash
remctl lists --all-accounts          # every connected account
remctl lists --account Exchange      # one account
remctl --account Exchange lists      # flag works before the command too
export REMCTL_ACCOUNT_SCOPE=all      # session default
remctl config accountScope all       # persistent default
```

With no opt-in, `install()` returns the dispatch table untouched.

New commands:

```bash
remctl accounts                      # list connected accounts and types
remctl config [KEY] [VALUE]          # accountScope | storeDir | dbPath
```

## Account types

Account type is resolved from two sources and the **more specific** label wins:

1. EventKit via the bridge — authoritative for concrete kinds (Exchange, …).
2. A store heuristic over `ZREMCDREPLICAMANAGER` identifiers — needed because
   EventKit reports both iCloud and Google as plain `CalDAV`, and because the
   bridge may be unavailable.

Account *discovery* itself is type-agnostic: it enumerates every
`Data-*.sqlite` store and reads the `REMCDAccount` entity, so any account type
Reminders supports is found. Only `LocalInternal`, an internal bookkeeping
store, is skipped.

## Reminders without a CloudKit identifier

Only iCloud reminders carry `ZCKIDENTIFIER`. Core refuses to modify a reminder
without one rather than risk a title-based fallback — which would make every
Exchange/Google reminder read-only. When an account is explicitly targeted, the
extension resolves the real EventKit identifier (via the bridge's
`find_reminder`) and hands it to core's normal write path.

**Caveat:** EventKit is queried by `(calendar, title)`, so a list holding two
reminders with the identical title resolves to the first. This trades core's
exact refusal for a resolvable-but-ambiguous match, and only on accounts that
would otherwise be unusable.

## Bridge changes

`remctl-bridge.swift` gains a `list_calendars` action and accepts
`calendarIdentifier` / `account` on `Command`. `findList()` is unified to
accept `calendarIdentifier + name + listId + account`; its iCloud-only write
restriction is relaxed **only** when an account is explicitly targeted, so the
default path keeps upstream's behavior. The bridge must be recompiled via
`install.sh`.

## Known upstream test delta

`tests/test_cli.py` is upstream's suite, unmodified. With the module installed,
one test fails:

```
CliTests::test_unknown_command_error_is_readable_and_suggests_list_symbols
```

It asserts `"  add,"` — that `add` starts the first line of the command list.
Adding the `accounts` command shifts that to `"  accounts, add,"`. Any new
subcommand breaks this assertion; the fix is to assert `"add,"` instead. The
command list itself is correct.

Four further tests fail *only* when a user has opted in via a stored
`accountScope`; they assert the dispatched handler is identically `cmd_show`
etc., which any dispatch-wrapping extension changes by design. A maintainer's
CI, which has no such config, does not hit them.

## Tests

`tests/test_accounts.py` covers the extension in isolation (72 tests):
discovery and ranking, config precedence, scope resolution, the account
context manager and its restoration, JSON merging, target disambiguation,
dispatch installation, bridge payload handling, and identifier backfill.
