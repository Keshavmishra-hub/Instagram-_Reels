import { api } from "./api.js";
import { h, icon, modal, toast } from "./util.js";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: "gauge" },
  { id: "studio", label: "Recording Studio", short: "Record", icon: "mic" },
  { id: "curriculum", label: "Curriculum", icon: "book" },
  { id: "analytics", label: "Voice Analytics", short: "Insights", icon: "chart" },
  { id: "dataset", label: "Dataset Manager", short: "Dataset", icon: "db" },
  { id: "settings", label: "Settings", icon: "gear" },
];
const TABS = ["dashboard", "studio", "curriculum", "dataset", "analytics"];

export const app = {
  state: null,
  view: null,
  get profile() { return this.state?.profile; },
  get prefs() { return this.state?.profile?.preferences || {}; },
  get caps() { return this.state?.capabilities || {}; },
  get vocab() { return this.state?.vocab || {}; },
  async refresh() {
    this.state = await api.get("/api/state");
    applyTheme();
    renderFoot();
    return this.state;
  },
  async savePrefs(patch) {
    const p = await api.put("/api/profile", { preferences: patch });
    this.state.profile = p;
    applyTheme();
    return p;
  },
  async saveProfile(patch) {
    const p = await api.put("/api/profile", patch);
    this.state.profile = p;
    return p;
  },
  go(hash) { if (location.hash !== hash) location.hash = hash; else route(); },
  pendingCount: 0,
};
window.myvoice = app;

function applyTheme() {
  const t = app.prefs.theme || "system";
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  document.documentElement.style.setProperty("--prompt-scale", String(app.prefs.text_scale || 1));
}

function renderNav(active) {
  const nav = document.getElementById("nav");
  nav.replaceChildren(...NAV.map((n) => h("a", { href: `#/${n.id}`, class: n.id === active ? "active" : "" }, icon(n.icon), n.label,
    n.id === "dataset" && app.pendingCount ? h("span", { class: "badge warn", title: "takes waiting for your review" }, app.pendingCount) : null)));
  const tb = document.getElementById("tabbar");
  tb.replaceChildren(...TABS.map((id) => { const n = NAV.find((x) => x.id === id); return h("a", { href: `#/${id}`, class: id === active ? "active" : "" }, icon(n.icon), n.short || n.label); }));
}

function renderFoot() {
  const f = document.getElementById("sidebar-foot");
  if (!f || !app.state) return;
  const asr = app.caps.asr || {};
  const asrOk = asr.installed && asr.enabled;
  f.replaceChildren(
    h("div", { class: "row small", style: { gap: "8px" } }, h("span", { class: `dot ${asrOk ? "ok" : "warn"}` }),
      h("span", { class: "muted" }, asrOk ? `Read-check: Whisper ${asr.model}` : "Read-check off")),
    h("div", { class: "row small", style: { gap: "8px", marginTop: "6px" } }, icon("lock", ""), h("span", { class: "muted" }, "Stored locally only")),
    h("div", { class: "tiny faint", style: { marginTop: "8px" } }, `v${app.state.version}`),
  );
  f.querySelectorAll("svg").forEach((s) => { s.style.width = "14px"; s.style.height = "14px"; s.style.color = "var(--muted)"; });
}

function shortcutsHelp() {
  const rows = [
    ["Space", "Record / stop"], ["Enter", "Approve take and continue"], ["R", "Re-record"], ["P", "Play / pause the take"],
    ["K", "Pause / resume recording"], ["N", "Skip to the next exercise"], ["B", "Back to the previous exercise"],
    ["T", "Show / hide Roman transliteration"], ["+ / −", "Bigger / smaller text"], ["?", "This help"],
  ];
  modal({
    title: "Keyboard shortcuts",
    body: h("div", { class: "shortcuts" }, rows.flatMap(([k, d]) => [h("span", {}, ...k.split(" / ").flatMap((x, i) => [i ? " / " : "", h("span", { class: "kbd" }, x)])), h("span", {}, d)])),
    actions: [{ label: "Close", cls: "btn-primary" }],
  });
}

export function welcome(force = false) {
  const p = app.profile || {};
  if (!force && (p.speaker_name || sessionStorage.getItem("myvoice-welcome-later"))) return;
  const name = h("input", { type: "text", placeholder: "Your name", value: p.speaker_name || "", maxlength: "80" });
  let forms = p.hindi_forms || "";
  const seg = h("div", { class: "seg" },
    h("button", { type: "button", class: forms === "m" ? "on" : "", onClick: (e) => pick("m", e) }, "मैं जा रहा हूँ"),
    h("button", { type: "button", class: forms === "f" ? "on" : "", onClick: (e) => pick("f", e) }, "मैं जा रही हूँ"));
  function pick(v, e) { forms = v; seg.querySelectorAll("button").forEach((b) => b.classList.remove("on")); e.currentTarget.classList.add("on"); }
  modal({
    title: "Welcome to MY VOICE",
    body: h("div", { class: "stack" },
      h("p", { class: "muted" }, "The studio shows you what to say, records it losslessly, checks every take and builds a documented dataset of your voice — English, Hindi and Hinglish — for cloning. Everything stays on this computer."),
      h("label", { class: "field" }, "Your name (used in your consent statement)", name),
      h("div", { class: "field" }, h("span", { class: "small", style: { fontWeight: 600, color: "var(--text-2)" } }, "Hindi sentences in first person should use"), seg,
        h("span", { class: "tiny muted" }, "So the Hindi you read matches how you naturally speak. You can change this later in Settings.")),
    ),
    actions: [
      { label: "Later", cls: "btn-ghost", onClick: () => sessionStorage.setItem("myvoice-welcome-later", "1") },
      { label: "Save and start", cls: "btn-primary", onClick: async () => {
        await app.saveProfile({ speaker_name: name.value.trim(), hindi_forms: forms });
        toast("Saved. Let's record.", "ok");
        if (app.view && app.view.refreshExercise) app.view.refreshExercise();
      } },
    ],
  });
}

const VIEWS = {
  dashboard: () => import("./views/dashboard.js"),
  studio: () => import("./views/studio.js"),
  curriculum: () => import("./views/curriculum.js"),
  analytics: () => import("./views/analytics.js"),
  dataset: () => import("./views/dataset.js"),
  settings: () => import("./views/settings.js"),
};

let routing = Promise.resolve();
function route() {
  routing = routing.then(doRoute).catch((e) => { console.error(e); toast(e.message || String(e), "bad"); });
}

async function doRoute() {
  const parts = (location.hash.replace(/^#\/?/, "") || "studio").split("/");
  const name = VIEWS[parts[0]] ? parts[0] : "studio";
  if (app.view && app.view.unmount) { try { await app.view.unmount(); } catch (e) { console.error(e); } }
  app.view = null;
  renderNav(name);
  const main = document.getElementById("main");
  main.replaceChildren(h("div", { class: "empty" }, h("span", { class: "spinner" })));
  const mod = await VIEWS[name]();
  const root = h("div", {});
  main.replaceChildren(root);
  app.view = (await mod.mount(root, parts.slice(1), app)) || {};
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

document.addEventListener("keydown", (e) => {
  const tag = (e.target && e.target.tagName) || "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || e.target.isContentEditable) return;
  if (document.querySelector(".modal-back")) return;
  if (e.key === "?") { e.preventDefault(); shortcutsHelp(); return; }
  if (app.view && app.view.onKey && !e.metaKey && !e.ctrlKey && !e.altKey) app.view.onKey(e);
});

export async function updatePendingBadge() {
  try {
    const r = await api.get("/api/takes?status=pending&limit=1");
    app.pendingCount = r.total;
    const active = (location.hash.replace(/^#\/?/, "") || "studio").split("/")[0];
    renderNav(VIEWS[active] ? active : "studio");
  } catch {}
}

async function boot() {
  document.getElementById("brand-mark").append(icon("wave"));
  try { await app.refresh(); }
  catch (e) {
    document.getElementById("main").replaceChildren(h("div", { class: "card" }, h("h2", {}, "Cannot reach the studio server"), h("p", { class: "muted" }, e.message)));
    return;
  }
  window.addEventListener("hashchange", route);
  route();
  updatePendingBadge();
}

boot();
export { shortcutsHelp };
