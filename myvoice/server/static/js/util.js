// Small DOM + formatting helpers shared by every view.

// Views build children with `cond ? node : null`. Native append/prepend/replaceChildren would insert
// the text "null" for those; nothing here ever means to insert the strings "null"/"false", so these
// methods skip null, undefined and false everywhere (HTML and SVG elements, fragments).
for (const proto of [Element.prototype, DocumentFragment.prototype]) {
  for (const name of ["append", "prepend", "replaceChildren"]) {
    const native = proto[name];
    proto[name] = function (...nodes) { return native.apply(this, nodes.filter((n) => n !== null && n !== undefined && n !== false)); };
  }
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") el.innerHTML = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const P = {
  mic: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/>',
  wave: '<path d="M3 12h1M7 8v8M11 5v14M15 8v8M19 10v4M22 12h-1"/>',
  play: '<path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  redo: '<path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/>',
  skip: '<path d="M5 5l9 7-9 7z"/><path d="M18 5v14"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  next: '<path d="M9 5l7 7-7 7"/>',
  gauge: '<path d="M12 14l4-4"/><path d="M3.5 18a9 9 0 1 1 17 0"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  db: '<ellipse cx="12" cy="5.5" rx="8" ry="2.5"/><path d="M4 5.5v13c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-13"/><path d="M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  restore: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/>',
  warn: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17v.5"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16v.5"/>',
  okc: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  coffee: '<path d="M4 8h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M17 10h2a2 2 0 0 1 0 4h-2M7 3v2M11 3v2"/>',
  text: '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.6L4 8"/><path d="M4 4v4h4M4 13a8 8 0 0 0 14.3 4.6L20 16"/><path d="M20 20v-4h-4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H10l2 2h7.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
};

export function icon(name, cls = "") {
  const span = document.createElement("span");
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" class="${cls}" aria-hidden="true">${P[name] || ""}</svg>`;
  return span.firstChild;
}

export const fmt = {
  dur(sec) {
    if (sec === null || sec === undefined || isNaN(sec)) return "–";
    sec = Math.max(0, sec);
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  },
  mins(sec, digits = 1) {
    if (!sec) return "0";
    return (sec / 60).toFixed(sec < 600 ? digits : 0);
  },
  timer(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
  },
  db(v) { return v === null || v === undefined ? "–" : `${Math.round(v)}`; },
  pct(v) { return v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`; },
  date(iso) {
    try { return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); } catch { return iso; }
  },
  day(iso) {
    try { return new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }); } catch { return iso; }
  },
  bytes(n) {
    if (!n) return "0 MB";
    if (n > 1e9) return (n / 1e9).toFixed(2) + " GB";
    return (n / 1e6).toFixed(1) + " MB";
  },
};

export const LANG_LABEL = { en: "English", hi: "Hindi", hinglish: "Hinglish", none: "—" };
export const isDeva = (s) => /[ऀ-ॿ]/.test(s || "");

export function scoreColor(score, verdict) {
  if (verdict === "rerecord" || score < 50) return "var(--bad)";
  if (verdict === "usable" || score < 80) return "var(--warn)";
  return "var(--ok)";
}

export function scoreRing(score, verdict, size = 64) {
  const r = 26, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(100, score)) / 100;
  const wrap = h("div", { class: "score-ring", style: { width: size + "px", height: size + "px" } });
  wrap.innerHTML = `<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="6"/>
    <circle cx="30" cy="30" r="${r}" fill="none" stroke="${scoreColor(score, verdict)}" stroke-width="6" stroke-linecap="round"
      stroke-dasharray="${c * pct} ${c}"/></svg>`;
  wrap.append(h("div", { class: "val" }, Math.round(score)));
  return wrap;
}

export function toast(msg, kind = "", ms = 3800) {
  const root = document.getElementById("toasts");
  const t = h("div", { class: `toast ${kind}` }, msg);
  root.append(t);
  setTimeout(() => t.remove(), ms);
}

export function modal({ title, body, actions = [], onClose, wide = false }) {
  const root = document.getElementById("modal-root");
  const close = () => { back.remove(); document.removeEventListener("keydown", esc, true); onClose && onClose(); };
  const esc = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  const box = h("div", { class: "modal", role: "dialog", "aria-modal": "true", style: wide ? { width: "min(760px, 100%)" } : {} },
    title ? h("h2", {}, title) : null, body,
    actions.length ? h("div", { class: "actions" }, actions.map((a) => {
      const b = h("button", { class: `btn ${a.cls || ""}` }, a.label);
      b.addEventListener("click", async () => { const keep = await (a.onClick && a.onClick(close)); if (keep !== true) close(); });
      return b;
    })) : null);
  const back = h("div", { class: "modal-back", onClick: (e) => { if (e.target === back) close(); } }, box);
  root.append(back);
  document.addEventListener("keydown", esc, true);
  const first = box.querySelector("input,textarea,select,button.btn-primary");
  if (first) setTimeout(() => first.focus(), 30);
  return { close, box };
}

export function emptyState(iconName, title, text, action) {
  return h("div", { class: "empty" }, icon(iconName), h("h3", {}, title), h("p", {}, text), action || null);
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
