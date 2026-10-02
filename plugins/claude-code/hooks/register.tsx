/**
 * Today: the RemCTL plugin's mod for Claude Code.
 *
 * Reads today's Apple Reminders through RemCTL's MCP server and draws them
 * above the prompt, in the status line, or in a /reminders pane, each in its
 * Reminders list's color. Until the server answers it draws nothing.
 */
import { atom, read, update } from 'claude-code'
import type { Elements, EngineInterface, PluginOptions, Register } from 'claude-code'

import type { TodayDone, TodayList, TodaySnapshot, TodayTask } from '../types'

type Kit = Pick<Elements['terminal'], 'Box' | 'Text' | 'Button'>

type Settings = {
  display: (typeof DISPLAYS)[number]
  rows: number
  includeOverdue: boolean
  lists: string[]
  checkboxes: boolean
  refreshMinutes: number
  openOnStart: boolean
}

// A task as drawn: its list's color, whether it is past due, its due label.
type Row = TodayTask & { color: string; isLate: boolean; label: string }

type Group = { name: string; color: string; order: number; rows: Row[] }

const PANE = 'remctl-today'
const DISPLAYS = ['band', 'compact', 'status', 'pane only'] as const
// This plugin's server, as .mcp.json names it; also the name
// `remctl mcp install --client claude-code` gives a server it adds by hand.
const SERVER = 'remctl'
// RemCTL tools that change reminders: when Claude calls one, re-read.
const WRITES =
  /^mcp__(plugin_remctl_)?remctl__(create_reminder|update_reminder|set_completion|set_flagged|delete_reminder|restore_reminder|run)$/
// The band's widest, in columns.
const BAND_COLUMNS = 96
// The docked pane's width, in columns.
const PANE_COLUMNS = 52
// Waits between looks for the server while MCP servers connect at startup.
const RETRIES = [2_000, 5_000, 15_000, 30_000]

// Apple's dark-mode system colors, as Reminders draws them.
const RED = '#FF453A'
const ORANGE = '#FF9F0A'
const GREEN = '#30D158'
const BLUE = '#0A84FF'
const GRAY = '#8E8E93'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const LONG_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const PRIORITY_MARKS: Record<string, string> = { high: '!!!', medium: '!!', low: '!' }

const snapshot = atom({ plugin: 'remctl', key: 'snapshot' } as const, null)
const failure = atom({ plugin: 'remctl', key: 'failure' } as const, null)
const checked = atom({ plugin: 'remctl', key: 'checked' } as const, [])
const lastDone = atom({ plugin: 'remctl', key: 'lastDone' } as const, null)
const isPaneOpen = atom({ plugin: 'remctl', key: 'isPaneOpen' } as const, false)

// RemCTL answered, but with an error (a missing permission, a stopped host).
class RemctlError extends Error {}

// The server name RemCTL answered under; a reload finds it again.
let server: string | null = null

export const register: Register = (on, options) => {
  const settings = settingsFrom(options)

  on('session.start', async ($, e, next) => {
    const result = await next(e)
    await registerCommand($)
    $.clock.after(0, () => void discover($, settings, 0))
    $.clock.every(settings.refreshMinutes * 60_000, () => void refresh($, settings))
    return result
  })

  // A /clear starts a new session with empty state and no session.start.
  on('session.end', async ($, e, next) => {
    const result = await next(e)
    if (e.reason === 'clear') {
      $.clock.after(0, () => void registerCommand($))
      $.clock.after(0, () => void discover($, settings, 0))
    }
    return result
  })

  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    if (WRITES.test(e.tool)) $.clock.after(0, () => void refresh($, settings))
    return result
  })

  on('command.run', { command: 'reminders' }, async $ => {
    if (!(await refresh($, settings))) {
      return {
        text: "RemCTL didn't answer. Install RemCTL (https://github.com/viticci/remctl), check it with `remctl doctor`, then run /reminders again.",
      }
    }
    await openPane($)
    const snap = await read($, snapshot)
    return { text: snap ? `Today: ${countsLine(rowsOf(snap))}.` : 'Today' }
  })

  on('ui.close', async ($, e, next) => {
    const result = await next(e)
    if (e.id === PANE) await update($, isPaneOpen, () => false)
    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || (settings.display !== 'band' && settings.display !== 'compact')) {
      return next(e)
    }
    const [snap, error, isPaneUp] = await Promise.all([read($, snapshot), read($, failure), read($, isPaneOpen)])
    if (isPaneUp || (snap === null && error === null)) return next(e)

    const kit = $.ui.resolve(e)
    const { Box, Text, Button } = kit

    if (error !== null) {
      return (
        <Box paddingX={1}>
          <Text wrap="truncate-end">
            <Text color={BLUE} bold>◉ Today</Text>
            <Text color={RED}>{`  RemCTL couldn't read Reminders: ${error}`}</Text>
          </Text>
        </Box>
      )
    }
    if (snap === null) return next(e)

    const rows = rowsOf(snap)
    if (rows.length === 0) {
      return (
        <Box paddingX={1}>
          <Text>
            <Text color={GREEN} bold>✓ Today</Text>
            <Text dimColor>  All done. Nothing left in Reminders.</Text>
          </Text>
        </Box>
      )
    }

    // Capped so a task's due label stays near its title on a wide terminal,
    // and clear of the engine's collapse mark at the band's right edge.
    const width = Math.min(e.props.bodyColumns - 4, BAND_COLUMNS)
    const groups = groupsOf(rows, snap.lists)
    // The list chips sit beside the summary when they all fit there, and get
    // a row of their own otherwise, as on an 80-column terminal.
    const beside = fitChips(groups, width - headText(rows).length - 8)
    const isOwnRow = beside.hidden > 0
    const chips = isOwnRow ? fitChips(groups, width - 4) : beside
    const shown = settings.display === 'band' ? rows.slice(0, settings.rows) : []
    const more = rows.length - shown.length

    return (
      <Box flexDirection="column" paddingX={1} width={width}>
        <Box justifyContent="space-between">
          <Text wrap="truncate-end">
            <Text color={BLUE} bold>◉ Today</Text>
            <Text bold>{`  ${rows.length} left`}</Text>
            {lateCount(rows) > 0 ? <Text color={RED}>{` · ${lateCount(rows)} overdue`}</Text> : null}
            {isOwnRow ? null : <Text>{'    '}</Text>}
            {isOwnRow ? null : chipTexts(kit, chips)}
          </Text>
          <Button key="open" plain dimColor label="Open ›" onPress={() => void openPane($)} />
        </Box>
        {isOwnRow ? (
          <Box paddingLeft={2}>
            <Text wrap="truncate-end">{chipTexts(kit, chips)}</Text>
          </Box>
        ) : null}
        {shown.map(row => taskLine(kit, row, { showList: true }))}
        {shown.length > 0 && more > 0 ? <Text dimColor>{`  +${more} more · /reminders`}</Text> : null}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const [snap, error, ticked, done] = await Promise.all([
      read($, snapshot),
      read($, failure),
      read($, checked),
      read($, lastDone),
    ])
    const kit = $.ui.resolve(e)
    const { Box, Text, Button } = kit

    if (snap === null) {
      return (
        <Box paddingX={1}>
          <Text dimColor>{error ?? "RemCTL didn't answer. Check it with `remctl doctor`."}</Text>
        </Box>
      )
    }

    const rows = rowsOf(snap)
    const late = lateCount(rows)

    return (
      <Box flexDirection="column" paddingX={1}>
        <Box justifyContent="space-between" paddingRight={2} gap={2}>
          <Text color={BLUE} bold wrap="truncate-end">{dayTitle(snap.now, countsWidth(rows), e.props.bodyColumns)}</Text>
          <Text>
            <Text bold>{`${rows.length} left`}</Text>
            {late > 0 ? <Text color={RED}>{` · ${late} overdue`}</Text> : null}
          </Text>
        </Box>
        {error !== null ? <Text color={RED}>{`RemCTL: ${error}`}</Text> : null}
        {rows.length === 0 ? (
          <Box marginTop={1}>
            <Text>
              <Text color={GREEN} bold>✓ </Text>
              <Text>All done for today.</Text>
            </Text>
          </Box>
        ) : null}
        {groupsOf(rows, snap.lists).map(group => (
          <Box flexDirection="column" marginTop={1}>
            <Box justifyContent="space-between">
              <Text color={group.color} bold wrap="truncate-end">{`● ${group.name}`}</Text>
              <Text color={group.color}>{String(group.rows.length)}</Text>
            </Box>
            {group.rows.map(row =>
              taskLine(kit, row, {
                isChecked: ticked.includes(row.id),
                onCheck: settings.checkboxes ? () => void complete($, settings, snap.server, row) : undefined,
              }),
            )}
          </Box>
        ))}
        <Box marginTop={1} justifyContent="space-between">
          <Text dimColor>{`Updated ${snap.now.slice(11, 16)}`}</Text>
          <Box gap={1}>
            {done !== null ? <Button key="undo" label="Undo" onPress={() => void undo($, settings, snap.server, done)} /> : null}
            <Button key="refresh" label="Refresh" onPress={() => void refresh($, settings)} />
          </Box>
        </Box>
      </Box>
    )
  })
}

// Opens /reminders: docked, wide enough for a task and its due time; above
// the prompt, tall enough for every row rather than the default third.
async function openPane($: EngineInterface) {
  const snap = await read($, snapshot)
  const size = snap ? { rows: paneRows(snap) } : {}
  const opened = await $.ui.open({ id: PANE, title: 'Today', columns: PANE_COLUMNS, ...size })
  await update($, isPaneOpen, () => opened.isPlaced)
}

// The pane's height: the date row, a gap and a heading per list, its tasks,
// then a gap and the footer.
function paneRows(snap: TodaySnapshot): number {
  const rows = rowsOf(snap)
  const lists = new Set(rows.map(row => row.list)).size
  return 1 + (rows.length === 0 ? 2 : lists * 2 + rows.length) + 2
}

// Looks for RemCTL until it answers or the retries run out.
async function discover($: EngineInterface, settings: Settings, attempt: number) {
  if (attempt === 0) {
    const panes = await $.ui.panes()
    await update($, isPaneOpen, () => panes.some(pane => pane.id === PANE && pane.isPlaced))
  }
  if (await refresh($, settings)) {
    if (settings.openOnStart) await openPane($)
    return
  }
  const wait = RETRIES[attempt]
  if (wait !== undefined) $.clock.after(wait, () => void discover($, settings, attempt + 1))
}

// Ticks a task off in Reminders from the pane's check button.
async function complete($: EngineInterface, settings: Settings, name: string, row: Row) {
  await update($, checked, ids => [...ids, row.id])
  try {
    await callTool($, name, 'set_completion', { reminder_id: row.id, completed: true })
  } catch (cause) {
    await update($, checked, ids => ids.filter(id => id !== row.id))
    $.ui.toast(`Couldn't complete “${row.title}”: ${messageOf(cause)}`)
    return
  }
  await update($, lastDone, () => ({ id: row.id, title: row.title }))
  // Leave the ticked row up for a moment, as Reminders does.
  $.clock.after(1_500, () => void refresh($, settings))
}

// Puts back the task the pane last ticked off.
async function undo($: EngineInterface, settings: Settings, name: string, done: TodayDone) {
  try {
    await callTool($, name, 'set_completion', { reminder_id: done.id, completed: false })
  } catch (cause) {
    $.ui.toast(`Couldn't undo “${done.title}”: ${messageOf(cause)}`)
    return
  }
  await update($, lastDone, () => null)
  await refresh($, settings)
}

// Each list as a chip in its color with its count, then how many did not fit.
function chipTexts(kit: Kit, chips: { shown: Group[]; hidden: number }) {
  const { Text } = kit
  return [
    ...chips.shown.map(group => (
      <Text>
        <Text color={group.color}>{`● ${group.name} `}</Text>
        <Text dimColor>{`${group.rows.length}   `}</Text>
      </Text>
    )),
    chips.hidden > 0 ? <Text dimColor>{`+${chips.hidden} ${chips.hidden === 1 ? 'list' : 'lists'}`}</Text> : null,
  ]
}

// One task's line: a circle in its list's color, the title with its flag and
// priority marks, then the list (in the band) and the due label on the right.
function taskLine(
  kit: Kit,
  row: Row,
  options: { showList?: boolean; isChecked?: boolean; onCheck?: (() => void) | undefined },
) {
  const { Box, Text, Button } = kit
  const mark = PRIORITY_MARKS[row.priority]
  const due = row.isLate ? { color: RED } : { dimColor: true }

  return (
    <Box justifyContent="space-between" paddingLeft={2}>
      <Box flexShrink={1}>
        <Text wrap="truncate-end">
          <Text color={row.color}>{options.isChecked ? '●' : '○'}</Text>
          <Text dimColor={options.isChecked === true} strikethrough={options.isChecked === true}>{` ${row.title}`}</Text>
          {mark !== undefined ? <Text color={row.color} bold>{` ${mark}`}</Text> : null}
          {row.flagged ? <Text color={ORANGE}>{' ⚑'}</Text> : null}
        </Text>
      </Box>
      <Box flexShrink={0} gap={1} paddingLeft={2}>
        <Text>
          {options.showList ? <Text color={row.color}>{row.list}</Text> : null}
          {options.showList && row.label !== '' ? <Text dimColor>{' · '}</Text> : null}
          {row.label !== '' ? <Text {...due}>{row.label}</Text> : null}
        </Text>
        {options.onCheck !== undefined && !options.isChecked ? (
          <Button key={`done-${row.id}`} plain dimColor label="✓" onPress={options.onCheck} />
        ) : null}
      </Box>
    </Box>
  )
}

// Re-reads today's tasks and the lists' colors; says whether RemCTL answered.
// With no RemCTL server in the session it clears everything, so nothing draws.
async function refresh($: EngineInterface, settings: Settings): Promise<boolean> {
  for (const name of await serverNames($)) {
    try {
      const [today, lists] = await Promise.all([
        callTool($, name, 'today', { include_overdue: settings.includeOverdue }),
        callTool($, name, 'lists'),
      ])
      server = name
      const fresh = snapshotFrom(name, itemsOf(today), itemsOf(lists), settings, await $.clock.now())
      await update($, snapshot, () => fresh)
      await update($, failure, () => null)
      await update($, checked, () => [])
      $.ui.status(settings.display === 'status' ? statusText(rowsOf(fresh)) : undefined)
      return true
    } catch (cause) {
      if (!(cause instanceof RemctlError)) continue
      server = name
      await update($, failure, () => cause.message)
      $.ui.status(settings.display === 'status' ? `RemCTL: ${cause.message}` : undefined)
      return true
    }
  }
  server = null
  await update($, snapshot, () => null)
  await update($, failure, () => null)
  $.ui.status(undefined)
  return false
}

// Where RemCTL may answer, most likely first: the server that answered last,
// this plugin's own (under whatever name the session runs it), and one added
// by hand with `remctl mcp install`, for a session where the plugin's is off.
async function serverNames($: EngineInterface): Promise<string[]> {
  const own = await $.mcp.connect(SERVER)
  const names = [server, own.isConnected ? own.server : null, SERVER]
  return [...new Set(names.filter((name): name is string => name !== null))]
}

// Adds /reminders to this session.
async function registerCommand($: EngineInterface) {
  await $.command.register({ name: 'reminders', description: "Open today's Reminders in a pane, in your lists' colors" })
}

// Calls one RemCTL tool and answers its structured result. Rejects with a
// RemctlError when RemCTL reports a failure, and with the engine's own error
// when no server by that name is connected.
async function callTool($: EngineInterface, name: string, tool: string, args: Record<string, unknown> = {}) {
  const result = await $.mcp.call(name, tool, args)
  const text = result.content.find(block => block.type === 'text')?.text ?? ''
  const data = (result.structuredContent ?? parseJson(text)) as Record<string, unknown> | null
  const error = data?.error as { message?: string; code?: string } | string | undefined
  if (result.isError || (error !== undefined && error !== null)) {
    const message = typeof error === 'string' ? error : (error?.message ?? error?.code)
    throw new RemctlError(message ?? (text || `${tool} failed`))
  }
  return data ?? {}
}

function itemsOf(data: Record<string, unknown>): Record<string, unknown>[] {
  return Array.isArray(data.items) ? (data.items as Record<string, unknown>[]) : []
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function messageOf(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}

function snapshotFrom(
  name: string,
  taskItems: Record<string, unknown>[],
  listItems: Record<string, unknown>[],
  settings: Settings,
  at: number,
): TodaySnapshot {
  const lists: Record<string, TodayList> = {}
  listItems.forEach((item, order) => {
    const hex = (item.color as { hex?: unknown } | undefined)?.hex
    if (typeof item.title === 'string' && item.isGroup !== true) {
      lists[item.title] = { color: typeof hex === 'string' ? hex : GRAY, order }
    }
  })
  const tasks = taskItems
    .map(toTask)
    .filter(task => settings.lists.length === 0 || settings.lists.includes(task.list.toLowerCase()))
  return { server: name, tasks, lists, now: localStamp(new Date(at)) }
}

function toTask(item: Record<string, unknown>): TodayTask {
  return {
    id: Number(item.id),
    title: typeof item.title === 'string' && item.title !== '' ? item.title : 'Untitled',
    list: typeof item.list === 'string' ? item.list : '',
    due: typeof item.dueDate === 'string' ? item.dueDate : null,
    allDay: item.allDay === true,
    flagged: item.flagged === true,
    priority: typeof item.priority === 'string' ? item.priority : 'none',
  }
}

// Today's tasks in Reminders' order: overdue first, then all-day, then by time.
function rowsOf(snap: TodaySnapshot): Row[] {
  const today = snap.now.slice(0, 10)
  return snap.tasks
    .map(task => {
      const due = task.due ?? today
      const isLate = task.allDay ? due.slice(0, 10) < today : due.slice(0, 16) < snap.now
      const color = snap.lists[task.list]?.color ?? GRAY
      return { ...task, color, isLate, label: dueLabel(due, task.allDay, today) }
    })
    .sort((a, b) => compare(sortKey(a), sortKey(b)))
}

function sortKey(task: TodayTask): string {
  const due = task.due ?? ''
  return due.slice(0, 10) + (task.allDay ? '' : due.slice(11, 16))
}

function compare(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

// The rows by list, in the order Reminders' sidebar shows the lists.
function groupsOf(rows: Row[], lists: Record<string, TodayList>): Group[] {
  const groups = new Map<string, Group>()
  for (const row of rows) {
    const group = groups.get(row.list) ?? {
      name: row.list || 'Reminders',
      color: row.color,
      order: lists[row.list]?.order ?? Number.MAX_SAFE_INTEGER,
      rows: [],
    }
    group.rows.push(row)
    groups.set(row.list, group)
  }
  return [...groups.values()].sort((a, b) => a.order - b.order)
}

// As many list chips as fit in `room` columns, and how many did not.
function fitChips(groups: Group[], room: number): { shown: Group[]; hidden: number } {
  const shown: Group[] = []
  let used = 0
  for (const group of groups) {
    const width = group.name.length + String(group.rows.length).length + 6
    if (used + width > room) break
    shown.push(group)
    used += width
  }
  return { shown, hidden: groups.length - shown.length }
}

function lateCount(rows: Row[]): number {
  return rows.filter(row => row.isLate).length
}

function countsLine(rows: Row[]): string {
  if (rows.length === 0) return 'all done'
  const late = lateCount(rows)
  return `${rows.length} left${late > 0 ? `, ${late} overdue` : ''}`
}

// The band's summary as plain text, to measure what room the chips have.
function headText(rows: Row[]): string {
  const late = lateCount(rows)
  return `◉ Today  ${rows.length} left${late > 0 ? ` · ${late} overdue` : ''}    `
}

function statusText(rows: Row[]): string {
  if (rows.length === 0) return '✓ Today: all done'
  const next = rows.find(row => !row.isLate) ?? rows[0]
  const when = next !== undefined && next.label !== '' ? ` ${next.label}` : ''
  return `Today: ${countsLine(rows).replace(',', ' ·')}${next ? ` · next: ${next.title}${when}` : ''}`
}

// Today: the time, or nothing for an all-day task. Earlier: Yesterday, Sep 25.
function dueLabel(due: string, allDay: boolean, today: string): string {
  const day = due.slice(0, 10)
  if (day === today) return allDay ? '' : due.slice(11, 16)
  if (day === shiftDay(today, -1)) return 'Yesterday'
  const [, month = 1, date = 1] = day.split('-').map(Number)
  return `${MONTHS[month - 1]} ${date}`
}

function shiftDay(day: string, by: number): string {
  const [year = 1970, month = 1, date = 1] = day.split('-').map(Number)
  return localStamp(new Date(year, month - 1, date + by)).slice(0, 10)
}

// `Thursday, October 1` for a local stamp.
// The pane's date: `Thursday, October 1`, or `Thu, Oct 1` when the long form
// would crowd the counts beside it.
function dayTitle(stamp: string, counts: number, columns: number): string {
  const [year = 1970, month = 1, date = 1] = stamp.slice(0, 10).split('-').map(Number)
  const weekday = WEEKDAYS[new Date(year, month - 1, date).getDay()] ?? ''
  const long = `${weekday}, ${LONG_MONTHS[month - 1]} ${date}`
  // The pane's padding, the gap, and room for the close mark.
  return long.length + counts + 7 <= columns ? long : `${weekday.slice(0, 3)}, ${MONTHS[month - 1]} ${date}`
}

// The width of the pane's `6 left · 1 overdue`.
function countsWidth(rows: Row[]): number {
  const late = lateCount(rows)
  return `${rows.length} left`.length + (late > 0 ? ` · ${late} overdue`.length : 0)
}

// Local `YYYY-MM-DDTHH:MM`: how RemCTL's zone-less due dates begin.
function localStamp(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function settingsFrom(options: PluginOptions): Settings {
  return {
    display: DISPLAYS.find(one => one === options.display) ?? 'band',
    rows: clamp(options.rows, 3, 0, 8),
    includeOverdue: options.includeOverdue !== false,
    lists: String(options.lists ?? '')
      .split(',')
      .map(name => name.trim().toLowerCase())
      .filter(Boolean),
    checkboxes: options.checkboxes !== false,
    refreshMinutes: clamp(options.refreshMinutes, 5, 1, 60),
    openOnStart: options.openOnStart === true,
  }
}

function clamp(value: unknown, fallback: number, low: number, high: number): number {
  const n = Number(value)
  return Number.isFinite(n) ? Math.min(high, Math.max(low, Math.round(n))) : fallback
}
