// One reminder due today (or overdue), as RemCTL's `today` tool returns it.
export type TodayTask = {
  id: number
  title: string
  list: string
  // Local time without a zone, as RemCTL writes it: `2026-10-01T22:00:00`.
  due: string | null
  allDay: boolean
  flagged: boolean
  priority: string
}

// A Reminders list's look, from RemCTL's `lists` tool.
export type TodayList = { color: string; order: number }

// One read of Reminders: the tasks, their lists' colors, and when it was taken.
export type TodaySnapshot = {
  server: string
  tasks: TodayTask[]
  lists: Record<string, TodayList>
  // Local `YYYY-MM-DDTHH:MM` at the read: what "today" and "late" mean.
  now: string
}

export type TodayDone = { id: number; title: string }

declare module 'claude-code' {
  interface PluginState {
    remctl: {
      snapshot: TodaySnapshot | null
      failure: string | null
      checked: number[]
      lastDone: TodayDone | null
      isPaneOpen: boolean
    }
  }
}
