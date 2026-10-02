import React from "react";
import { CalendarDays, Clock, X } from "lucide-react";
import { DateField } from "./pickers";

/** Keep date-only reminders date-only; adding a time is always explicit. */
export function DueEditor({ value, change, weekStartsOn }: { value: string; change: (value: string) => void; weekStartsOn?: string }) {
  const date = value.slice(0, 10);
  const time = value.slice(11, 16);
  const day = (offset: number) => {
    const next = new Date();
    next.setDate(next.getDate() + offset);
    return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
  };
  const setDate = (next: string) => change(next ? next + (time ? ` ${time}` : "") : "");
  return <div className="due-editor">
    <label><CalendarDays size={16}/><span>Date</span><DateField aria-label="Due date" value={date} placeholder="No date" weekStartsOn={weekStartsOn} onChange={e => setDate(e.target.value)}/></label>
    {date && <label><Clock size={16}/><span>Time</span>{time ? <><input type="time" aria-label="Due time" value={time} onChange={e => change(date + (e.target.value ? ` ${e.target.value}` : ""))}/><button type="button" className="date-clear" aria-label="Remove due time" onClick={() => change(date)}><X size={12}/></button></> : <button type="button" className="date-add-time" aria-label="Add due time" onClick={() => change(`${date} 09:00`)}>Add time</button>}</label>}
    <div className="date-shortcuts"><button type="button" onClick={() => setDate(day(0))}>Today</button><button type="button" onClick={() => setDate(day(1))}>Tomorrow</button><button type="button" onClick={() => setDate(day(7))}>Next week</button>{date && <button type="button" aria-label="Clear due date" onClick={() => change("")}><X size={12}/></button>}</div>
  </div>;
}
