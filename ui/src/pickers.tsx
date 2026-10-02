import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";

/* Pop-up menus and date pickers drawn by the workspace. Embedded web views
   draw native <select> lists and date popups like a Windows form, so every
   choice goes through these instead. */

export type Choice = { value: string; label: React.ReactNode; text: string; icon?: React.ReactNode; disabled?: boolean };
type ChangeEvent = { target: { value: string } };

/** Read <option> children, so a <select> becomes a <Select> without other changes. */
function choicesFrom(children: React.ReactNode): Choice[] {
  const result: Choice[] = [];
  const visit = (node: React.ReactNode) =>
    React.Children.forEach(node, (child) => {
      if (!React.isValidElement(child)) return;
      const props = child.props as any;
      if (child.type === React.Fragment) return visit(props.children);
      if (child.type !== "option") return;
      const text = React.Children.toArray(props.children).join("");
      result.push({ value: String(props.value ?? text), label: props.children ?? text, text, disabled: props.disabled });
    });
  visit(children);
  return result;
}

/** A floating glass panel beside its anchor. It lives in .workspace so it keeps the
    theme, and outside every glass panel so none of them can clip or re-blur it. */
function Popover({ anchor, close, children, className = "", minWidth = 0 }: {
  anchor: React.RefObject<HTMLElement | null>; close: () => void; children: React.ReactNode; className?: string; minWidth?: number;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({ visibility: "hidden" });
  const closeRef = useRef(close);
  closeRef.current = close;
  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.current?.getBoundingClientRect(), p = panel.current;
      if (!a || !p) return;
      const width = Math.max(p.offsetWidth, minWidth, a.width);
      const below = innerHeight - a.bottom - 10, above = a.top - 10;
      const up = p.scrollHeight > below && above > below;
      // Controls on the trailing side open their panel toward the middle of the window.
      const trailing = (a.left + a.right) / 2 > innerWidth * 0.6;
      setStyle({
        left: Math.max(8, Math.min(trailing ? a.right - width : a.left, innerWidth - width - 8)),
        top: up ? undefined : a.bottom + 5,
        bottom: up ? innerHeight - a.top + 5 : undefined,
        minWidth: Math.max(minWidth, a.width),
        maxHeight: Math.max(140, Math.min(380, up ? above : below)),
      });
    };
    place();
    const outside = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!panel.current?.contains(target) && !anchor.current?.contains(target)) closeRef.current();
    };
    const scroll = (e: Event) => { if (!panel.current?.contains(e.target as Node)) closeRef.current(); };
    document.addEventListener("pointerdown", outside, true);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", place);
    window.addEventListener("blur", closeRef.current);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", place);
      window.removeEventListener("blur", closeRef.current);
    };
  }, []);
  const host = anchor.current?.closest(".workspace") || document.body;
  return createPortal(<div ref={panel} className={"popover " + className} style={style}>{children}</div>, host);
}

/** A Mac pop-up button: the current choice with up-down chevrons, and a menu with a checkmark. */
export function Select({ value, onChange, children, options, disabled, className = "", id, required, title, placeholder, variant, "aria-label": ariaLabel }: {
  value?: string | number | null; onChange?: (event: ChangeEvent) => void; children?: React.ReactNode; options?: Choice[];
  disabled?: boolean; className?: string; id?: string; required?: boolean; title?: string; placeholder?: string;
  variant?: "icon"; "aria-label"?: string;
}) {
  const choices = options || choicesFrom(children);
  const selected = choices.findIndex((c) => c.value === String(value ?? ""));
  const current = selected >= 0 ? choices[selected] : placeholder || variant ? undefined : choices[0];
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const typed = useRef({ text: "", at: 0 });
  const menuId = useId();
  const show = () => {
    if (disabled) return;
    setActive(Math.max(0, selected));
    setOpen(true);
  };
  const choose = (choice: Choice) => {
    if (choice.disabled) return;
    setOpen(false);
    button.current?.focus();
    if (choice.value !== String(value ?? "")) onChange?.({ target: { value: choice.value } });
  };
  useEffect(() => {
    if (!open) return;
    list.current?.focus();
  }, [open]);
  useEffect(() => {
    if (open) list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);
  const step = (from: number, by: number) => {
    for (let i = 1; i <= choices.length; i++) {
      const next = (from + by * i + choices.length * 4) % choices.length;
      if (!choices[next].disabled) return next;
    }
    return from;
  };
  const keys = (e: React.KeyboardEvent) => {
    const handled = () => { e.preventDefault(); e.stopPropagation(); };
    if (e.key === "ArrowDown") { handled(); setActive((i) => step(i, 1)); }
    else if (e.key === "ArrowUp") { handled(); setActive((i) => step(i, -1)); }
    else if (e.key === "Home") { handled(); setActive(step(-1, 1)); }
    else if (e.key === "End") { handled(); setActive(step(choices.length, -1)); }
    else if (e.key === "Enter" || e.key === " ") { handled(); if (choices[active]) choose(choices[active]); }
    else if (e.key === "Escape") { handled(); setOpen(false); button.current?.focus(); }
    else if (e.key === "Tab") { setOpen(false); }
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) {
      handled();
      const now = Date.now();
      typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : "") + e.key.toLowerCase(), at: now };
      const match = choices.findIndex((c) => !c.disabled && c.text.toLowerCase().startsWith(typed.current.text));
      if (match >= 0) setActive(match);
    }
  };
  const control = (
    <button
      type="button" ref={button} id={id} title={title} disabled={disabled}
      className={"select-button " + (variant === "icon" ? "select-icon " : "") + (open ? "open " : "") + className}
      aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? menuId : undefined} aria-label={ariaLabel}
      onClick={() => (open ? setOpen(false) : show())}
      onKeyDown={(e) => {
        if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); e.stopPropagation(); show(); }
      }}
    >
      {variant !== "icon" && current?.icon}
      {variant !== "icon" && <span className="select-label">{current ? current.label : placeholder}</span>}
      {variant === "icon" ? <ChevronDown size={13} /> : <ChevronsUpDown size={12} className="select-chevron" />}
    </button>
  );
  return (
    <>
      {required ? (
        <span className="select-wrap">
          {control}
          <input className="select-proxy" tabIndex={-1} aria-hidden="true" required value={current?.value ?? ""} onChange={() => {}} />
        </span>
      ) : control}
      {open && (
        <Popover anchor={button} close={() => setOpen(false)} className="menu-popover" minWidth={variant === "icon" ? 190 : 0}>
          <div
            ref={list} id={menuId} role="listbox" tabIndex={-1} aria-label={ariaLabel} className="menu-list"
            aria-activedescendant={`${menuId}-${active}`} onKeyDown={keys}
          >
            {choices.map((choice, index) => (
              <div
                key={choice.value + index} id={`${menuId}-${index}`} data-index={index} role="option"
                aria-selected={choice === current} aria-disabled={choice.disabled || undefined}
                className={"menu-option " + (index === active ? "active " : "") + (choice.disabled ? "disabled" : "")}
                onPointerMove={() => { if (!choice.disabled && index !== active) setActive(index); }}
                onClick={() => choose(choice)}
              >
                <span className="menu-check">{choice === current && <Check size={13} />}</span>
                {choice.icon}
                <span className="menu-label">{choice.label}</span>
              </div>
            ))}
          </div>
        </Popover>
      )}
    </>
  );
}

const isoDay = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const parseDay = (value: string) => (/^\d{4}-\d{2}-\d{2}/.test(value || "") ? new Date(value.slice(0, 10) + "T12:00:00") : null);

/** A date field that opens a small month calendar instead of the web view's popup. */
export function DateField({ value, onChange, placeholder = "None", weekStartsOn = "monday", disabled, className = "", "aria-label": ariaLabel }: {
  value: string; onChange: (event: ChangeEvent) => void; placeholder?: string; weekStartsOn?: string; disabled?: boolean;
  className?: string; "aria-label"?: string;
}) {
  const chosen = parseDay(value);
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState<Date>(chosen || new Date());
  const button = useRef<HTMLButtonElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  useEffect(() => { if (open) grid.current?.focus(); }, [open]);
  const month = new Date(focus.getFullYear(), focus.getMonth(), 1);
  const offset = (month.getDay() + (weekStartsOn === "sunday" ? 0 : 6)) % 7;
  const days = Array.from({ length: 42 }, (_, i) => new Date(month.getFullYear(), month.getMonth(), 1 - offset + i));
  const names = Array.from({ length: 7 }, (_, i) =>
    new Date(2026, 0, (weekStartsOn === "sunday" ? 4 : 5) + i).toLocaleDateString(undefined, { weekday: "narrow" }));
  const today = isoDay(new Date());
  const pick = (day: Date) => { setOpen(false); button.current?.focus(); onChange({ target: { value: isoDay(day) } }); };
  const move = (by: number, unit: "day" | "month" = "day") =>
    setFocus((d) => unit === "day" ? new Date(d.getFullYear(), d.getMonth(), d.getDate() + by) : new Date(d.getFullYear(), d.getMonth() + by, Math.min(d.getDate(), 28)));
  const keys = (e: React.KeyboardEvent) => {
    const map: Record<string, () => void> = {
      ArrowLeft: () => move(-1), ArrowRight: () => move(1), ArrowUp: () => move(-7), ArrowDown: () => move(7),
      PageUp: () => move(-1, "month"), PageDown: () => move(1, "month"),
      Enter: () => pick(focus), " ": () => pick(focus),
      Escape: () => { setOpen(false); button.current?.focus(); },
    };
    if (map[e.key]) { e.preventDefault(); e.stopPropagation(); map[e.key](); }
    else if (e.key === "Tab") setOpen(false);
  };
  return (
    <>
      <button
        type="button" ref={button} disabled={disabled} aria-label={ariaLabel} aria-haspopup="dialog" aria-expanded={open}
        className={"select-button date-button " + (chosen ? "" : "empty ") + (open ? "open " : "") + className}
        onClick={() => { setFocus(chosen || new Date()); setOpen(!open); }}
      >
        <span className="select-label">
          {chosen ? chosen.toLocaleDateString(undefined, { month: "short", day: "numeric", year: chosen.getFullYear() === new Date().getFullYear() ? undefined : "numeric" }) : placeholder}
        </span>
      </button>
      {open && (
        <Popover anchor={button} close={() => setOpen(false)} className="calendar-popover">
          <div className="mini-heading">
            <strong>{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</strong>
            <button type="button" aria-label="Previous month" onClick={() => move(-1, "month")}><ChevronLeft size={15} /></button>
            <button type="button" className="mini-today" onClick={() => setFocus(new Date())}>Today</button>
            <button type="button" aria-label="Next month" onClick={() => move(1, "month")}><ChevronRight size={15} /></button>
          </div>
          <div ref={grid} className="mini-grid" role="grid" tabIndex={-1} aria-label={ariaLabel} onKeyDown={keys}>
            {names.map((name, i) => <span key={i} className="mini-weekday">{name}</span>)}
            {days.map((day) => {
              const iso = isoDay(day);
              return (
                <button
                  type="button" key={iso} tabIndex={-1} aria-label={day.toLocaleDateString(undefined, { dateStyle: "full" })}
                  aria-selected={chosen ? iso === isoDay(chosen) : false}
                  className={"mini-day " + (day.getMonth() !== month.getMonth() ? "outside " : "") + (iso === today ? "today " : "") +
                    (chosen && iso === isoDay(chosen) ? "chosen " : "") + (iso === isoDay(focus) ? "focused" : "")}
                  onClick={() => pick(day)}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>
        </Popover>
      )}
    </>
  );
}
