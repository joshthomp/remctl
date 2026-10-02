// One reminder due today (or overdue), as RemCTL's `today` tool returns it.
export type TodayTask = {
  id: number
  title: string
  list: string
  // Reminders' display date, falling back to the due date, in local time.
  due: string | null
  allDay: boolean
  flagged: boolean
  priority: string
  recurring: boolean
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
