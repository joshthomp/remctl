import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

// Thursday, October 1, 2026 at 20:00 local time.
const NOW = new Date(2026, 9, 1, 20, 0).getTime()

const TODAY = [
  { id: 1, title: 'App Radar', list: 'Weekly 530', dueDate: '2026-09-25T15:00:00', allDay: false, flagged: true, priority: 'high' },
  { id: 2, title: 'Toothbrush Chicche', list: 'Family', dueDate: '2026-10-01T22:00:00', allDay: false, flagged: false, priority: 'none' },
  { id: 3, title: 'Edit the review', list: 'Editorial', dueDate: '2026-10-01T00:00:00', allDay: true, flagged: false, priority: 'none' },
]
const LISTS = [
  { title: 'Editorial', color: { hex: '#CC73E1' } },
  { title: 'Family', color: { hex: '#FF2968' } },
  { title: 'Weekly 530', color: { hex: '#1BADF8' } },
]

const result = (structuredContent: object) => ({
  value: { content: [{ type: 'text', text: JSON.stringify(structuredContent) }], structuredContent, isError: false },
})

// This plugin's RemCTL server as Claude Code connects it, answering from the
// fixtures; every call lands in `calls`.
const SERVER = 'plugin:remctl:remctl'

function remctl(on: On, calls: { tool: string; args: Record<string, unknown> }[], tasks: object[] = TODAY) {
  const clock = mock.clock(on, { now: NOW })
  on('mcp.connect', () => ({ value: { isConnected: true, server: SERVER } }))
  on('mcp.call', ($, e) => {
    if (e.server !== SERVER) throw new Error(`no server ${e.server}`)
    calls.push({ tool: e.tool, args: e.args })
    if (e.tool === 'today') return result({ items: tasks, count: tasks.length })
    if (e.tool === 'lists') return result({ items: LISTS, count: LISTS.length })
    return result({ ok: true })
  })
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('command.register', () => ({ value: { command: 'reminders' } }))
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  return clock
}

const BAND = { component: 'AbovePrompt', props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120 } } as const

describe('remctl today', () => {
  test('the band counts today and draws each list in its color', async ($, on) => {
    const clock = remctl(on, [])
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.settle()

    for (const surface of ['terminal', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'remctl', surface, ...BAND })
      expect(await ui.find({ type: 'Text', text: /^\s*3 left$/ })).toBeDefined()
      expect(await ui.find({ type: 'Text', text: /^ · 1 overdue$/ })).toBeDefined()
      expect((await ui.find({ type: 'Text', text: /^● Family $/ }))?.props).toMatchObject({ color: '#FF2968' })
      expect((await ui.find({ type: 'Text', text: /^Sep 25$/ }))?.props).toMatchObject({ color: '#FF453A' })
      await ui.unmount()
    }
  })

  test('on a narrow band the list chips get a row of their own', async ($, on) => {
    const clock = remctl(on, [])
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.settle()

    const ui = await $.ui.mount({ plugin: 'remctl', surface: 'terminal', ...BAND, props: { ...BAND.props, bodyColumns: 72 } })
    for (const name of ['Editorial', 'Family', 'Weekly 530']) {
      expect(await ui.find({ type: 'Text', text: new RegExp(`^● ${name} $`) })).toBeDefined()
    }
  })

  test('the pane check button completes that reminder', async ($, on) => {
    const calls: { tool: string; args: Record<string, unknown> }[] = []
    const clock = remctl(on, calls)
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.settle()

    const ui = await $.ui.mount({
      plugin: 'remctl',
      surface: 'terminal',
      component: 'Pane',
      requestId: 'remctl-today',
      props: { title: 'Today', isFocused: true, bodyColumns: 48, placement: 'dock' },
    })
    await ui.press({ key: 'done-2' })

    expect(calls).toContainEqual({ tool: 'set_completion', args: { reminder_id: 2, completed: true } })
    expect(await ui.find({ key: 'undo' })).toBeDefined()
  })

  test('the band uses the display date for both labels and overdue counts', async ($, on) => {
    const clock = remctl(on, [], [{ ...TODAY[1], displayDate: '2026-09-30T18:00:00' }])
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.settle()

    const ui = await $.ui.mount({ plugin: 'remctl', surface: 'terminal', ...BAND })
    expect(await ui.find({ type: 'Text', text: /^ · 1 overdue$/ })).toBeDefined()
    expect((await ui.find({ type: 'Text', text: /^Yesterday$/ }))?.props).toMatchObject({ color: '#FF453A' })
  })

  test('completing a repeating task does not offer an undo that cannot restore its occurrence', async ($, on) => {
    const calls: { tool: string; args: Record<string, unknown> }[] = []
    const clock = remctl(on, calls, [{ ...TODAY[1], recurrence: { frequency: 'daily', interval: 1 } }])
    await $.session.start({ cwd: '/tmp', surface: 'terminal', isInteractive: true })
    await clock.settle()

    const ui = await $.ui.mount({ plugin: 'remctl', surface: 'terminal', component: 'Pane',
      requestId: 'remctl-today', props: { title: 'Today', isFocused: true, bodyColumns: 48, placement: 'dock' } })
    await ui.press({ key: 'done-2' })
    expect(calls).toContainEqual({ tool: 'set_completion', args: { reminder_id: 2, completed: true } })
    expect(await ui.find({ key: 'undo' })).toBeUndefined()
  })
})
