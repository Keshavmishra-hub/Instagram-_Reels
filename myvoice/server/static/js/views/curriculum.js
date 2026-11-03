import { api } from "../api.js";
import { h, icon, LANG_LABEL } from "../util.js";

const STATUS = {
  approved: ["check", "var(--ok)", "approved"],
  pending: ["clock", "var(--warn)", "waiting for review"],
  rejected: ["x", "var(--bad)", "only rejected takes"],
  new: ["target", "var(--faint)", "not recorded"],
};

export async function mount(root, params, app) {
  const mid = params[0] || "";
  const data = await api.get(`/api/curriculum${mid ? `?module=${encodeURIComponent(mid)}` : ""}`);
  const modules = data.modules.filter((m) => m.id !== "S");
  if (!mid) return overview(root, modules, data, app);
  return detail(root, mid, modules, data, app);
}

function recordModule(id, app) {
  sessionStorage.setItem("myvoice-mode", id === "adaptive" ? "adaptive" : `module:${id}`);
  app.go("#/studio");
}

function overview(root, modules, data, app) {
  const total = modules.reduce((n, m) => n + m.total, 0);
  const done = modules.reduce((n, m) => n + m.approved, 0);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Training Curriculum"),
    h("p", {}, `${total} exercises across ten modules · ${done} approved. Adaptive mode picks what your dataset needs next; you can also record a module in order.`)),
    h("button", { class: "btn btn-primary", onClick: () => recordModule("adaptive", app) }, icon("sparkle"), "Record adaptively")));
  root.append(h("div", { class: "grid g3" }, modules.map((m) => {
    const pct = m.total ? (100 * m.approved) / m.total : 0;
    const card = h("div", { class: "card module-card", tabindex: "0" },
      h("div", { class: "row", style: { gap: "12px" } }, h("div", { class: "module-letter" }, m.id), h("div", { style: { flex: 1, minWidth: 0 } }, h("h3", {}, m.title),
        h("div", { class: "small muted" }, `${m.approved}/${m.total} approved · core ${m.core_approved}/${m.core}${m.pending ? ` · ${m.pending} pending` : ""}`))),
      h("p", { class: "small muted", style: { margin: 0 } }, m.summary),
      h("div", { class: "progress thin" }, h("i", { style: { width: `${pct}%` } })),
      h("div", { class: "row", style: { marginTop: "4px" } },
        h("button", { class: "btn btn-sm", onClick: (e) => { e.stopPropagation(); recordModule(m.id, app); } }, icon("mic"), "Record this module"),
        h("a", { class: "btn btn-sm btn-ghost", href: `#/curriculum/${m.id}`, onClick: (e) => e.stopPropagation() }, "Exercises", icon("next"))));
    card.addEventListener("click", () => app.go(`#/curriculum/${m.id}`));
    card.addEventListener("keydown", (e) => { if (e.key === "Enter") app.go(`#/curriculum/${m.id}`); });
    return card;
  })));
  root.append(materialCard(data));
}

function materialCard(data) {
  return h("div", { class: "card", style: { marginTop: "14px" } }, h("div", { class: "card-head" }, h("h3", {}, icon("sparkle"), "Need more material?")),
    h("p", { class: "muted" }, "The planner fills gaps from the built-in bank first and generates fresh numbers, dates and amounts on its own. When the dashboard still shows a gap the bank cannot fill (say, more suspense narration in Hindi), add targeted exercises:"),
    h("ul", { class: "muted small", style: { lineHeight: 1.8 } },
      h("li", {}, "In Claude Code (no API key): run ", h("span", { class: "mono" }, "/voice-exercises"), " in this repository. It reads ", h("span", { class: "mono" }, "python -m myvoice coverage"), ", writes exercises for the weakest areas and imports them."),
      h("li", {}, "By hand: write a JSON/YAML file in the same structure as ", h("span", { class: "mono" }, "myvoice/curriculum/data/*.yaml"), " and run ", h("span", { class: "mono" }, "python -m myvoice import-exercises file.json"), ".")),
    data.bank_errors && data.bank_errors.length ? h("div", { class: "notice bad" }, icon("alert"), h("div", {}, h("b", {}, "Some imported exercise files were skipped: "), data.bank_errors.join("; "))) : null);
}

function detail(root, mid, modules, data, app) {
  const m = modules.find((x) => x.id === mid) || { id: mid, title: mid, summary: "" };
  root.append(h("div", { class: "page-head" }, h("div", {},
    h("a", { href: "#/curriculum", class: "small" }, "← All modules"),
    h("h1", { style: { marginTop: "6px" } }, `Module ${m.id} · ${m.title}`), h("p", {}, m.summary)),
    h("button", { class: "btn btn-primary", onClick: () => recordModule(m.id, app) }, icon("mic"), "Record this module")));
  for (const sec of data.sections) {
    const done = sec.items.filter((i) => i.status === "approved").length;
    root.append(h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, sec.title), h("span", { class: "small muted num" }, `${done}/${sec.items.length} approved`)),
      h("div", { class: "ex-list" }, sec.items.map((it) => {
        const [ic, color, label] = STATUS[it.status];
        const st = h("span", { title: label, style: { color, display: "inline-flex" } }, icon(ic));
        st.querySelector("svg").style.cssText = "width:16px;height:16px";
        return h("div", { class: "ex-item" },
          h("span", { class: "id" }, it.id),
          h("div", { class: "tx", title: it.text }, h("span", { lang: it.lang === "en" ? "en" : "hi" }, it.text || "(silence)")),
          h("div", { class: "row", style: { gap: "6px", flexWrap: "nowrap" } },
            it.lang !== "none" ? h("span", { class: "chip" }, LANG_LABEL[it.lang]) : null,
            it.emotion !== "neutral" ? h("span", { class: "chip warn" }, app.vocab.emotions[it.emotion]) : null,
            it.best != null ? h("span", { class: "small muted num", title: "best score" }, it.best) : null, st,
            h("a", { class: "btn btn-sm btn-ghost btn-icon", href: `#/studio/${encodeURIComponent(it.id)}`, title: "Record this exercise" }, icon("mic"))));
      }))));
  }
}
