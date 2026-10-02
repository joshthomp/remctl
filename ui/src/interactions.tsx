import React, { useEffect, useRef, useState } from "react";
import { Folder, List, ChevronRight, Search } from "lucide-react";
import { RecordData as D } from "./bridge";
import { Select, Choice } from "./pickers";
import { colorFor } from "./reminder-helpers";

export function ListBadge({ list, color }: { list: D; color: string }) {
  const badge = list.badge || {};
  return (
    <span
      className={"list-symbol " + (badge.emoji ? "emoji-symbol" : "")}
      style={{ "--badge": color } as React.CSSProperties}
    >
      {list.isGroup ? (
        <Folder size={14} />
      ) : badge.emoji ? (
        <span>{badge.emoji}</span>
      ) : badge.image ? (
        <img src={badge.image} alt="" />
      ) : (
        <List size={14} />
      )}
    </span>
  );
}

/** Lists as pop-up menu choices, each with its own icon. */
export function listChoices(lists: D[]): Choice[] {
  return lists
    .filter((list) => !list.isGroup)
    .map((list, index) => ({ value: String(list.id), label: list.title, text: list.title || "", icon: <ListBadge list={list} color={colorFor(list, index)} /> }));
}

export type Action = {
  label: string;
  run?: () => void;
  icon?: React.ReactNode;
  shortcut?: string;
  disabled?: boolean;
  danger?: boolean;
  children?: Action[];
  keywords?: string;
};

export type DragPayload = {kind: "reminders"; ids: number[]; label: string} | {kind: "list"; id: number; label: string};

/** Internal moves avoid the native drag session used by embedded Mac web views. */
export function useInternalDrag(drop: (payload: DragPayload, target: HTMLElement) => void) {
  const pending = useRef<{payload: DragPayload; x: number; y: number; active: boolean} | null>(null);
  const callback = useRef(drop);
  callback.current = drop;
  const [preview, setPreview] = useState<{x: number; y: number; label: string} | null>(null);
  useEffect(() => {
    let highlighted: HTMLElement | null = null;
    let suppressClick = false;
    let suppressionTimer: ReturnType<typeof setTimeout>;
    const clear = () => {
      pending.current = null;
      highlighted?.classList.remove("drag-target");
      highlighted = null;
      setPreview(null);
    };
    const move = (event: PointerEvent) => {
      const state = pending.current;
      if (!state) return;
      if (!state.active && Math.hypot(event.clientX - state.x, event.clientY - state.y) < 7) return;
      state.active = true;
      event.preventDefault();
      setPreview({x: event.clientX, y: event.clientY, label: state.payload.label});
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-drop-kind]") || null;
      if (target !== highlighted) {
        highlighted?.classList.remove("drag-target");
        highlighted = target;
        highlighted?.classList.add("drag-target");
      }
    };
    const up = (event: PointerEvent) => {
      const state = pending.current;
      if (state?.active) {
        event.preventDefault();
        suppressClick = true;
        suppressionTimer = setTimeout(() => { suppressClick = false; }, 0);
        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-drop-kind]");
        if (target) callback.current(state.payload, target);
      }
      clear();
    };
    const click = (event: MouseEvent) => {
      if (!suppressClick) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      suppressClick = false;
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") clear(); };
    document.addEventListener("pointermove", move, {passive: false});
    document.addEventListener("pointerup", up, true);
    document.addEventListener("pointercancel", clear);
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", escape);
    window.addEventListener("blur", clear);
    return () => {
      clearTimeout(suppressionTimer);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up, true);
      document.removeEventListener("pointercancel", clear);
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("blur", clear);
      highlighted?.classList.remove("drag-target");
    };
  }, []);
  const begin = (event: React.PointerEvent, payload: DragPayload) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const target = event.target as HTMLElement;
    if (target.closest("input,textarea,select,a") || (target.closest("button") && target.closest("button") !== event.currentTarget)) return;
    pending.current = {payload, x: event.clientX, y: event.clientY, active: false};
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  return {begin, preview};
}

export function ContextMenu({
  x,
  y,
  items,
  close,
}: {
  x: number;
  y: number;
  items: Action[];
  close: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [branch, setBranch] = useState<Action | null>(null);
  const options = branch?.children || items;
  useEffect(() => {
    const outside = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("pointerdown", outside);
    ref.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus();
    return () => document.removeEventListener("pointerdown", outside);
  }, [branch]);
  return (
    <div
      ref={ref}
      role="menu"
      aria-label={branch?.label || "Actions"}
      className="context-menu"
      style={{
        left: Math.max(8, Math.min(x, window.innerWidth - 258)),
        top: Math.max(
          8,
          Math.min(
            y,
            window.innerHeight - Math.min(440, (options.length + 1) * 33),
          ),
        ),
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          close();
        }
        if (e.key === "ArrowLeft" && branch) {
          e.preventDefault();
          setBranch(null);
        }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          e.stopPropagation();
          const buttons = Array.from(
            ref.current!.querySelectorAll<HTMLButtonElement>(
              "button:not(:disabled)",
            ),
          );
          const index = buttons.indexOf(
            document.activeElement as HTMLButtonElement,
          );
          buttons[
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? buttons.length - 1
                : (index + (e.key === "ArrowDown" ? 1 : -1) + buttons.length) %
                  buttons.length
          ]?.focus();
        }
      }}
    >
      {branch && (
        <button
          role="menuitem"
          className="menu-back"
          onClick={() => setBranch(null)}
        >
          ‹ {branch.label}
        </button>
      )}
      {options.map((a, i) => (
        <button
          key={i}
          role="menuitem"
          disabled={a.disabled}
          className={a.danger ? "danger" : ""}
          onClick={() => {
            if (a.children) setBranch(a);
            else {
              close();
              a.run?.();
            }
          }}
        >
          {a.icon}
          <span>{a.label}</span>
          {a.children ? (
            <ChevronRight size={13} />
          ) : (
            a.shortcut && <kbd>{a.shortcut}</kbd>
          )}
        </button>
      ))}
    </div>
  );
}

export function CommandPalette({ actions }: { actions: Action[] }) {
  const [query, setQuery] = useState(""),
    [index, setIndex] = useState(0);
  const result = actions.filter((a) =>
    (a.label + " " + (a.keywords || ""))
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase()),
  );
  const selected = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    selected.current?.scrollIntoView({ block: "nearest" });
  }, [index]);
  return (
    <div
      className="command-palette"
      onKeyDown={(e) => {
        if (["ArrowDown", "ArrowUp"].includes(e.key)) {
          e.preventDefault();
          e.stopPropagation();
          setIndex(
            (i) =>
              (i + (e.key === "ArrowDown" ? 1 : -1) + result.length) %
              Math.max(1, result.length),
          );
        } else if (e.key === "Enter") {
          e.preventDefault();
          if (!result[index]?.disabled) result[index]?.run?.();
        }
      }}
    >
      <div className="command-search">
        <Search size={19} />
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls="command-results"
          aria-activedescendant={"command-" + index}
          placeholder="Actions, lists, reminders…"
          aria-label="Find an action"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
        />
        <kbd>esc</kbd>
      </div>
      <div id="command-results" role="listbox" className="command-results">
        {result.length ? (
          result.map((a, i) => (
            <button
              key={i}
              id={"command-" + i}
              ref={i === index ? selected : undefined}
              role="option"
              aria-selected={i === index}
              className={i === index ? "command-active" : ""}
              disabled={a.disabled}
              onClick={a.run}
            >
              {a.icon || <Search size={17} />}
              <span>{a.label}</span>
              {a.shortcut ? (
                <kbd>{a.shortcut}</kbd>
              ) : (
                <ChevronRight size={14} />
              )}
            </button>
          ))
        ) : (
          <p className="palette-empty">No matching actions or reminders</p>
        )}
      </div>
      <div className="palette-footer">
        <span>↑ ↓ Navigate</span>
        <span>↵ Open</span>
        <span>esc Close</span>
      </div>
    </div>
  );
}

export function ListAppearance({
  list,
  symbols,
  disabled,
  save,
}: {
  list: D;
  symbols: D;
  disabled: boolean;
  save: (args: D) => void;
}) {
  const [color, setColor] = useState(
    typeof list.color === "string" ? list.color : list.color?.hex || "#007aff",
  );
  const [groceries,setGroceries]=useState(!!list.isGroceries),[locale,setLocale]=useState(list.grocery?.locale || "en_US");
  const [badge, setBadge] = useState<D>(list.badge || {}),
    [search, setSearch] = useState("");
  return (
    <div className="appearance-picker">
      <div className="appearance-preview">
        <ListBadge list={{ badge }} color={color} />
        <strong>{list.title}</strong>
      </div>
      <div className="color-picker" aria-label="List color">
        {[
          "#ff453a",
          "#ff9f0a",
          "#ffd60a",
          "#30d158",
          "#64d2ff",
          "#0a84ff",
          "#bf5af2",
          "#ff375f",
          "#a2845e",
          "#8e8e93",
        ].map((c) => (
          <button
            key={c}
            style={{ background: c }}
            aria-label={"Color " + c}
            aria-pressed={color === c}
            onClick={() => setColor(c)}
          />
        ))}
        <input
          type="color"
          aria-label="Custom list color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
        />
      </div>
      <label className="emoji-entry">
        Emoji
        <input
          aria-label="List emoji"
          placeholder="Choose an emoji"
          value={badge.emoji || ""}
          onChange={(e) => setBadge({ emoji: e.target.value })}
        />
      </label>
      <div className="list-type-controls"><label>List type<Select aria-label="List type" value={groceries?"groceries":"standard"} onChange={e=>setGroceries(e.target.value==="groceries")}><option value="standard">Standard</option><option value="groceries">Groceries</option></Select></label>{groceries&&<label>Language<Select aria-label="Groceries language" value={locale} onChange={e=>setLocale(e.target.value)}>{["en_US","en_GB","it_IT","fr_FR","de_DE","es_ES"].map(v=><option key={v}>{v}</option>)}</Select></label>}</div>
      <input
        className="symbol-search"
        aria-label="Search list symbols"
        placeholder="Find a symbol…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="symbol-picker" aria-label="List symbols">
        {Object.entries(symbols)
          .filter(([name]) => name.includes(search.toLowerCase()))
          .map(([name, image]) => (
            <button
              key={name}
              title={name}
              aria-label={"Symbol " + name}
              aria-pressed={badge.symbol === name && !badge.emoji}
              onClick={() => setBadge({ symbol: name, image })}
            >
              <ListBadge list={{ badge: { image } }} color={color} />
            </button>
          ))}
      </div>
      <button
        className="primary"
        disabled={disabled}
        onClick={() =>
          save({
            list_id: list.id,
            ...(groceries!==!!list.isGroceries?{[groceries?"groceries":"standard"]:true}:{}),
            ...(groceries?{grocery_locale:locale}:{}),
            color,
            ...(badge.emoji
              ? { emoji: badge.emoji }
              : { symbol: badge.symbol || "default" }),
            private: true,
          })
        }
      >
        Save appearance
      </button>
    </div>
  );
}
