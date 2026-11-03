// Minimal SVG charts following the studio's data-viz rules: validated categorical slots
// (English = series-1, Hindi = series-2, Hinglish = series-3; single series = series-1),
// thin marks (bars <= 16px, 4px rounded data end, square at the baseline; 2px lines;
// 8px end-dots with a 2px surface ring), hairline solid grid, hover tooltips, a legend for 2+
// series, and a table view for every chart.

import { h } from "./util.js";

const NS = "http://www.w3.org/2000/svg";
const LANG_SERIES = { en: "var(--series-1)", hi: "var(--series-2)", hinglish: "var(--series-3)" };
export const langColor = (l) => LANG_SERIES[l] || "var(--series-1)";

function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  kids.flat().forEach((k) => k != null && el.append(k instanceof Node ? k : document.createTextNode(String(k))));
  return el;
}

let tipEl = null;
function tip(e, html) {
  if (!tipEl) { tipEl = h("div", { class: "tooltip" }); document.body.append(tipEl); }
  if (html === null) { tipEl.style.display = "none"; return; }
  tipEl.innerHTML = html;
  tipEl.style.display = "block";
  const x = Math.min(window.innerWidth - tipEl.offsetWidth - 10, e.clientX + 14);
  const y = Math.min(window.innerHeight - tipEl.offsetHeight - 10, e.clientY + 14);
  tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
}
const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function niceTicks(lo, hi, n = 4) {
  if (hi === lo) hi = lo + 1;
  const span = hi - lo, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => span / st <= n + 0.5) || 10 * mag;
  const start = Math.floor(lo / step) * step;
  const out = [];
  for (let v = start; v <= hi + step * 0.001; v += step) out.push(+v.toFixed(6));
  return out;
}

function frame(container, draw, table) {
  const box = h("div", { class: "chart-box" });
  const tbl = h("div", { class: "hidden" });
  const toggle = h("button", { class: "btn btn-sm btn-ghost", type: "button" }, "Table");
  toggle.addEventListener("click", () => {
    const show = tbl.classList.toggle("hidden");
    box.classList.toggle("hidden", !show);
    toggle.textContent = show ? "Table" : "Chart";
  });
  if (table) {
    const t = h("table", { class: "chart-table" }, h("thead", {}, h("tr", {}, table.columns.map((c) => h("th", {}, c)))),
      h("tbody", {}, table.rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
    tbl.append(t);
  }
  container.replaceChildren(box, tbl, table ? h("div", { class: "chart-tools" }, toggle) : null);
  const render = () => { const w = box.clientWidth || container.clientWidth || 600; box.replaceChildren(draw(w)); };
  const ro = new ResizeObserver(() => render());
  ro.observe(box);
  render();
  return { destroy: () => ro.disconnect() };
}

/** Horizontal bars: rows [{label, value, display, color, note}] */
export function barChart(container, { rows, max, format = (v) => v, table, labelWidth = 120 }) {
  const top = Math.max(max ?? 0, ...rows.map((r) => r.value || 0), 1e-9);
  return frame(container, (W) => {
    const bar = 14, gap = 12, H = rows.length * (bar + gap) + 4, valueW = 64;
    const x0 = Math.min(labelWidth, W * 0.38), plotW = Math.max(40, W - x0 - valueW);
    const svg = s("svg", { class: "chart", width: W, height: H, role: "img" });
    svg.append(s("line", { class: "baseline", x1: x0 + 0.5, x2: x0 + 0.5, y1: 0, y2: H }));
    rows.forEach((r, i) => {
      const y = i * (bar + gap) + 4, w = Math.max(r.value > 0 ? 3 : 0, (plotW * (r.value || 0)) / top);
      const maxChars = Math.max(4, Math.floor((x0 - 14) / 6.6)); // ~6.6 px per character at 12 px; full label in tooltip/table
      svg.append(s("text", { class: "label", x: x0 - 10, y: y + bar / 2 + 4, "text-anchor": "end" }, r.label.length > maxChars ? r.label.slice(0, maxChars - 1) + "…" : r.label));
      if (w > 0) {
        const rr = Math.min(4, w);
        svg.append(s("path", { d: `M${x0},${y} h${w - rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${bar - 2 * rr} a${rr},${rr} 0 0 1 -${rr},${rr} h-${w - rr} z`, fill: r.color || "var(--series-1)" }));
      }
      svg.append(s("text", { class: "value", x: x0 + w + 8, y: y + bar / 2 + 4 }, r.display ?? format(r.value)));
      const hit = s("rect", { class: "hit", x: 0, y: y - gap / 2, width: W, height: bar + gap });
      hit.addEventListener("mousemove", (e) => tip(e, `<b>${esc(r.label)}</b><br>${esc(r.display ?? format(r.value))}${r.note ? "<br><span style='color:var(--muted)'>" + esc(r.note) + "</span>" : ""}`));
      hit.addEventListener("mouseleave", (e) => tip(e, null));
      svg.append(hit);
    });
    return svg;
  }, table || { columns: ["Item", "Value"], rows: rows.map((r) => [r.label, r.display ?? format(r.value)]) });
}

/** Columns for a binned distribution: bins [{x0, x1, count}] */
export function histogram(container, { bins, xFormat = (v) => v, xLabel = "", color = "var(--series-1)", table, height = 170 }) {
  const top = Math.max(1, ...bins.map((b) => b.count));
  return frame(container, (W) => {
    const padL = 34, padB = 30, padT = 8, H = height, plotW = W - padL - 6, plotH = H - padB - padT;
    const svg = s("svg", { class: "chart", width: W, height: H, role: "img" });
    const ticks = niceTicks(0, top, 3);
    const ymax = ticks[ticks.length - 1];
    ticks.forEach((t) => { const y = padT + plotH - (plotH * t) / ymax; svg.append(s("line", { class: "gridline", x1: padL, x2: W - 6, y1: Math.round(y) + 0.5, y2: Math.round(y) + 0.5 }), s("text", { x: padL - 6, y: y + 4, "text-anchor": "end" }, t)); });
    const slot = plotW / Math.max(1, bins.length), bw = Math.min(16, Math.max(2, slot - 2));
    bins.forEach((b, i) => {
      const hgt = (plotH * b.count) / ymax, x = padL + i * slot + (slot - bw) / 2, y = padT + plotH - hgt;
      if (b.count > 0) {
        const rr = Math.min(4, hgt, bw / 2);
        svg.append(s("path", { d: `M${x},${padT + plotH} v-${hgt - rr} a${rr},${rr} 0 0 1 ${rr},-${rr} h${bw - 2 * rr} a${rr},${rr} 0 0 1 ${rr},${rr} v${hgt - rr} z`, fill: color }));
      }
      const hit = s("rect", { class: "hit", x: padL + i * slot, y: padT, width: slot, height: plotH });
      hit.addEventListener("mousemove", (e) => tip(e, `<b>${esc(xFormat(b.x0))}–${esc(xFormat(b.x1))}</b><br>${b.count}`));
      hit.addEventListener("mouseleave", (e) => tip(e, null));
      svg.append(hit);
    });
    svg.append(s("line", { class: "baseline", x1: padL, x2: W - 6, y1: padT + plotH + 0.5, y2: padT + plotH + 0.5 }));
    const every = Math.ceil(bins.length / Math.max(2, Math.floor(plotW / 56)));
    bins.forEach((b, i) => { if (i % every === 0) svg.append(s("text", { x: padL + i * slot + slot / 2, y: H - 12, "text-anchor": "middle" }, xFormat(b.x0))); });
    if (xLabel) svg.append(s("text", { x: W - 6, y: H - 1, "text-anchor": "end" }, xLabel));
    return svg;
  }, table || { columns: ["From", "To", "Count"], rows: bins.map((b) => [xFormat(b.x0), xFormat(b.x1), b.count]) });
}

/** Lines over an ordinal x (sessions): series [{name, color, points:[{x (index), y, label}]}] */
export function lineChart(container, { series, xLabels, yFormat = (v) => v, yLabel = "", height = 190, table, yMin, yMax }) {
  const ys = series.flatMap((sr) => sr.points.map((p) => p.y)).filter((v) => v != null);
  let lo = yMin ?? Math.min(...ys), hi = yMax ?? Math.max(...ys);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12;
  const ticks = niceTicks(yMin ?? lo - pad, yMax ?? hi + pad, 4);
  const legend = series.length > 1 ? h("div", { class: "legend" }, series.map((sr) => h("span", {}, h("i", { style: { background: sr.color } }), sr.name))) : null;
  const handle = frame(container, (W) => {
    const padL = 42, padR = 16, padB = 30, padT = 10, H = height, plotW = W - padL - padR, plotH = H - padB - padT;
    const n = Math.max(1, xLabels.length - 1);
    const X = (i) => padL + (xLabels.length === 1 ? plotW / 2 : (plotW * i) / n);
    const Y = (v) => padT + plotH - (plotH * (v - ticks[0])) / (ticks[ticks.length - 1] - ticks[0]);
    const svg = s("svg", { class: "chart", width: W, height: H, role: "img" });
    ticks.forEach((t) => svg.append(s("line", { class: "gridline", x1: padL, x2: W - padR, y1: Math.round(Y(t)) + 0.5, y2: Math.round(Y(t)) + 0.5 }), s("text", { x: padL - 6, y: Y(t) + 4, "text-anchor": "end" }, yFormat(t))));
    svg.append(s("line", { class: "baseline", x1: padL, x2: W - padR, y1: padT + plotH + 0.5, y2: padT + plotH + 0.5 }));
    const every = Math.ceil(xLabels.length / Math.max(2, Math.floor(plotW / 70)));
    xLabels.forEach((l, i) => { if (i % every === 0 || i === xLabels.length - 1) svg.append(s("text", { x: X(i), y: H - 10, "text-anchor": "middle" }, l)); });
    if (yLabel) svg.append(s("text", { x: padL, y: 9 }, yLabel));
    for (const sr of series) {
      const pts = sr.points.filter((p) => p.y != null);
      if (pts.length > 1) svg.append(s("path", { d: pts.map((p, k) => `${k ? "L" : "M"}${X(p.x)},${Y(p.y)}`).join(" "), fill: "none", stroke: sr.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      pts.forEach((p) => svg.append(s("circle", { cx: X(p.x), cy: Y(p.y), r: 4, fill: sr.color, stroke: "var(--surface)", "stroke-width": 2 })));
    }
    const cross = s("line", { class: "baseline", x1: 0, x2: 0, y1: padT, y2: padT + plotH, opacity: 0 });
    svg.append(cross);
    const hit = s("rect", { class: "hit", x: padL, y: padT, width: plotW, height: plotH });
    hit.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(xLabels.length - 1, Math.round(((e.clientX - r.left - padL) / plotW) * n)));
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", 1);
      const lines = series.map((sr) => { const p = sr.points.find((q) => q.x === i); return p && p.y != null ? `<span class="swatch" style="background:${sr.color}"></span>${esc(sr.name)}: <b>${esc(yFormat(p.y))}</b>${p.label ? " · " + esc(p.label) : ""}` : null; }).filter(Boolean);
      tip(e, `<b>${esc(xLabels[i])}</b><br>${lines.join("<br>") || "no data"}`);
    });
    hit.addEventListener("mouseleave", (e) => { cross.setAttribute("opacity", 0); tip(e, null); });
    svg.append(hit);
    return svg;
  }, table || { columns: ["", ...series.map((sr) => sr.name)], rows: xLabels.map((l, i) => [l, ...series.map((sr) => { const p = sr.points.find((q) => q.x === i); return p && p.y != null ? yFormat(p.y) : "–"; })]) });
  if (legend) container.insertBefore(legend, container.firstChild);
  return handle;
}

/** Range + dot rows: rows [{label, lo, mid, hi, n, color}] on a shared horizontal scale */
export function rangePlot(container, { rows, format = (v) => v, unit = "", table, labelWidth = 130 }) {
  const all = rows.flatMap((r) => [r.lo, r.hi, r.mid]).filter((v) => v != null);
  const ticks = niceTicks(Math.min(...all), Math.max(...all), 4);
  return frame(container, (W) => {
    const rowH = 26, padT = 6, padB = 24, H = rows.length * rowH + padT + padB;
    const x0 = Math.min(labelWidth, W * 0.38), plotW = W - x0 - 20;
    const X = (v) => x0 + (plotW * (v - ticks[0])) / (ticks[ticks.length - 1] - ticks[0]);
    const svg = s("svg", { class: "chart", width: W, height: H, role: "img" });
    ticks.forEach((t) => svg.append(s("line", { class: "gridline", x1: Math.round(X(t)) + 0.5, x2: Math.round(X(t)) + 0.5, y1: padT, y2: H - padB }), s("text", { x: X(t), y: H - 8, "text-anchor": "middle" }, format(t))));
    rows.forEach((r, i) => {
      const y = padT + i * rowH + rowH / 2;
      const maxChars = Math.max(4, Math.floor((x0 - 14) / 6.6));
      svg.append(s("text", { class: "label", x: x0 - 10, y: y + 4, "text-anchor": "end" }, r.label.length > maxChars ? r.label.slice(0, maxChars - 1) + "…" : r.label));
      if (r.lo != null && r.hi != null) svg.append(s("line", { x1: X(r.lo), x2: X(r.hi), y1: y, y2: y, stroke: r.color || "var(--series-1)", "stroke-width": 2, "stroke-linecap": "round", opacity: 0.55 }));
      if (r.mid != null) svg.append(s("circle", { cx: X(r.mid), cy: y, r: 5, fill: r.color || "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 }));
      const hit = s("rect", { class: "hit", x: 0, y: y - rowH / 2, width: W, height: rowH });
      hit.addEventListener("mousemove", (e) => tip(e, `<b>${esc(r.label)}</b><br>median ${esc(format(r.mid))}${unit}<br>middle half ${esc(format(r.lo))}–${esc(format(r.hi))}${unit}<br>${r.n} take${r.n === 1 ? "" : "s"}`));
      hit.addEventListener("mouseleave", (e) => tip(e, null));
      svg.append(hit);
    });
    return svg;
  }, table || { columns: ["", "25th pct", "Median", "75th pct", "Takes"], rows: rows.map((r) => [r.label, format(r.lo), format(r.mid), format(r.hi), r.n]) });
}
