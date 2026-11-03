import { api } from "../api.js";
import { barChart, langColor } from "../charts.js";
import { emptyState, fmt, h, icon } from "../util.js";

const LANGS = [["en", "English"], ["hi", "Hindi"], ["hinglish", "Hinglish"]];

export async function mount(root, _params, app) {
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Dashboard"), h("p", {}, "How complete and how good your voice dataset is — measured on approved recordings, not on exercises ticked off.")),
    h("div", { class: "row" }, h("a", { class: "btn", href: "#/settings", title: "Settings" }, icon("gear")), h("a", { class: "btn btn-primary", href: "#/studio" }, icon("mic"), "Continue recording"))));
  const body = h("div", { class: "stack" }, h("div", { class: "empty" }, h("span", { class: "spinner" })));
  root.append(body);
  let cov, sessions;
  try { [cov, sessions] = await Promise.all([api.get("/api/coverage"), api.get("/api/sessions")]); }
  catch (e) { body.replaceChildren(h("div", { class: "notice bad" }, icon("alert"), e.message)); return; }
  const charts = [];
  const t = cov.totals;
  body.replaceChildren();

  // ------------------------------------------------------------------ hero
  const r = 80, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(100, cov.completeness));
  const ring = h("div", { class: "ring" });
  ring.innerHTML = `<svg viewBox="0 0 190 190"><defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b6cff"/><stop offset=".55" stop-color="#4f8bff"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>
    <circle cx="95" cy="95" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="14"/>
    <circle cx="95" cy="95" r="${r}" fill="none" stroke="url(#g1)" stroke-width="14" stroke-linecap="round" stroke-dasharray="${(c * pct) / 100} ${c}"/></svg>`;
  ring.append(h("div", { class: "center" }, h("div", { class: "pct", style: { fontSize: "48px" } }, `${Math.round(pct)}%`), h("div", { class: "lbl" }, "complete")));
  const current = cov.milestones.find((m) => !m.done);
  const nextExercise = cov.next?.exercise;
  body.append(h("div", { class: "card" }, h("div", { class: "hero" }, ring,
    h("div", { class: "stack" },
      h("div", { class: "small muted", style: { textTransform: "uppercase", letterSpacing: ".08em", fontWeight: 700 } }, "Current stage"),
      h("h2", { style: { fontSize: "24px" } }, current ? current.title : "Professional dataset reached"),
      current ? h("div", { class: "muted" }, `${Math.round(current.progress * 100)}% of this milestone · `, current.checks.filter((x) => x.progress < 1).slice(0, 2).map((x) => `${x.label}: ${x.display}`).join(" · ")) : null,
      h("div", { class: "notice info", style: { marginTop: "6px" } }, icon("target"), h("div", {}, h("b", {}, "Next focus: "), cov.next?.reason || "—",
        cov.next?.factors?.length > 1 ? h("div", { class: "small muted", style: { marginTop: "4px" } }, cov.next.factors.slice(1).join(" · ")) : null)),
      h("div", { class: "row", style: { marginTop: "6px" } },
        h("a", { class: "btn btn-primary", href: nextExercise ? "#/studio" : "#/curriculum" }, icon("mic"), nextExercise ? "Record the next exercise" : "Open curriculum"),
        t.pending ? h("a", { class: "btn", href: "#/dataset" }, icon("check"), `Review ${t.pending} pending take${t.pending > 1 ? "s" : ""}`) : null)))));

  // ------------------------------------------------------------------ KPI tiles
  const tile = (k, v, unit, sub) => h("div", { class: "card stat" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v, unit ? h("small", {}, unit) : null), sub ? h("div", { class: "s" }, sub) : null);
  body.append(h("div", { class: "grid g4" },
    tile("Approved audio", fmt.mins(t.approved_seconds), "min", `${fmt.mins(t.recorded_seconds)} min recorded in total`),
    tile("Approved takes", t.approved, "", `${t.pending} pending · ${t.rejected} rejected`),
    tile("Average quality", t.mean_score ?? "–", t.mean_score != null ? "/100" : "", "approved takes"),
    tile("Sessions", t.sessions, "", `${t.exercises_done} of ${t.exercises_total} exercises approved`)));

  if (!t.takes) body.append(h("div", { class: "card" }, emptyState("mic", "No recordings yet", "Open the Recording Studio: the first session starts with a 5-second room-tone measurement and a microphone check.",
    h("a", { class: "btn btn-primary", href: "#/studio" }, "Start recording"))));

  // ------------------------------------------------------------------ milestones + languages
  const msCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("layers"), "Readiness milestones")),
    h("div", { class: "milestones" }, cov.milestones.map((m) => milestone(m, m === current))),
    h("p", { class: "tiny muted", style: { marginTop: "10px" } }, "Zero-shot models (ElevenLabs Instant, IndicF5, Chatterbox) need a few excellent clips; professional cloning and fine-tuning need the larger targets. More data does not automatically make a better clone — coverage and consistency matter."));
  const langCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("globe"), "Language coverage"), h("span", { class: "small muted" }, "approved minutes")));
  const langBox = h("div", {});
  langCard.append(langBox, h("p", { class: "tiny muted", style: { marginTop: "8px" } }, "Targets: 8 min each for the fine-tune milestone, 30 min each for a professional dataset."));
  body.append(h("div", { class: "grid g2" }, msCard, langCard));
  charts.push(barChart(langBox, {
    rows: LANGS.map(([k, l]) => ({ label: l, value: (cov.languages[k] || 0) / 60, color: langColor(k), display: `${fmt.mins(cov.languages[k] || 0)} min` })),
    max: Math.max(8, ...LANGS.map(([k]) => (cov.languages[k] || 0) / 60)), labelWidth: 90,
    table: { columns: ["Language", "Approved minutes", "Fine-tune target", "Professional target"], rows: LANGS.map(([k, l]) => [l, fmt.mins(cov.languages[k] || 0), "8", "30"]) },
  }));

  // ------------------------------------------------------------------ phonetics
  const ph = cov.phonemes;
  const phCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("wave"), "Phonetic coverage"),
    h("span", { class: "small muted" }, "occurrences in approved recordings")));
  const phLegend = h("div", { class: "legend" }, h("span", {}, h("i", { style: { background: "transparent", border: "1px dashed var(--faint)" } }), "none yet"),
    h("span", {}, h("i", { style: { background: "var(--warn-bg)", border: "1px solid var(--warn)" } }), "below minimum"),
    h("span", {}, h("i", { style: { background: "color-mix(in srgb, var(--accent) 12%, transparent)", border: "1px solid var(--accent)" } }), "fine-tune minimum met"),
    h("span", {}, h("i", { style: { background: "var(--ok-bg)", border: "1px solid var(--ok)" } }), "professional target met"));
  const grid = (rows) => h("div", { class: "ph-grid" }, rows.map((p) => {
    const lvl = p.count === 0 ? "z" : p.count < (p.rare ? 3 : 10) ? "lo" : p.count < (p.rare ? 6 : 25) ? "mid" : "hi";
    return h("div", { class: `ph ${lvl}`, title: `${p.label}${p.rare ? " (rare sound: lower target)" : ""} — ${p.count}` }, h("div", { class: "p" }, p.p), h("div", { class: "c" }, p.count));
  }));
  phCard.append(
    h("div", { class: "row spread", style: { marginBottom: "8px" } }, h("b", {}, "English"), h("span", { class: "small muted" }, `${Math.round(ph.en_progress * 100)}% of professional target · diphones ${ph.en_diphones[0]}/${ph.en_diphones[1]}`)),
    grid(ph.en),
    h("div", { class: "row spread", style: { margin: "16px 0 8px" } }, h("b", {}, "Hindi"), h("span", { class: "small muted" }, `${Math.round(ph.hi_progress * 100)}% of professional target · diphones ${ph.hi_diphones[0]}/${ph.hi_diphones[1]}`)),
    grid(ph.hi), phLegend,
    h("p", { class: "tiny muted", style: { marginTop: "8px" } }, "Counted from the transcripts of approved takes (English via eSpeak NG phonemes, Hindi via the Devanagari rules). Diphones are measured against the sound pairs that occur in the curriculum. These are category counts, not a pronunciation score — your Indian-English realisation of each sound is exactly what the clone should learn."));
  body.append(phCard);

  // ------------------------------------------------------------------ emotions + genres
  const emoCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("sparkle"), "Emotional coverage"), h("span", { class: "small muted" }, "approved takes (target 3 → 6)")),
    h("div", { class: "emo-grid" }, cov.emotions.map((e) => h("span", { class: `emo ${e.count >= 6 ? "l3" : e.count >= 3 ? "l2" : e.count > 0 ? "l1" : ""}` },
      e.count >= 6 ? icon("check") : null, e.label, h("span", { class: "n" }, e.count)))));
  emoCard.querySelectorAll(".emo svg").forEach((x) => { x.style.width = "13px"; x.style.height = "13px"; x.style.color = "var(--ok)"; });
  const genreBox = h("div", {});
  const genreCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("chart"), "Narration genres"), h("span", { class: "small muted" }, "approved takes · target 4 each")), genreBox);
  body.append(h("div", { class: "grid g2" }, emoCard, genreCard));
  charts.push(barChart(genreBox, { rows: cov.genres.map((g) => ({ label: g.label, value: g.count, display: String(g.count) })), max: 4, labelWidth: 150 }));

  // ------------------------------------------------------------------ modules + sessions
  const modCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("book"), "Curriculum modules"), h("a", { class: "small", href: "#/curriculum" }, "Open →")),
    h("div", { class: "stack" }, cov.modules.filter((m) => m.id !== "S").map((m) => h("div", {},
      h("div", { class: "row spread small" }, h("span", {}, h("b", {}, m.id), "  ", m.title), h("span", { class: "muted num" }, `${m.approved}/${m.total} · ${fmt.mins(m.seconds)} min`)),
      h("div", { class: "progress thin", style: { marginTop: "5px" } }, h("i", { style: { width: `${m.total ? (100 * m.approved) / m.total : 0}%` } }))))));
  const sessCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, icon("clock"), "Recent sessions")),
    sessions.length ? h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Takes"), h("th", {}, "Approved"), h("th", {}, "Audio"), h("th", {}, "Room noise"), h("th", {}, "Echo"))),
      h("tbody", {}, sessions.slice(0, 8).map((s) => h("tr", {}, h("td", {}, fmt.date(s.started_at), s.voice_state ? h("span", { class: "chip", style: { marginLeft: "6px" } }, s.voice_state) : null),
        h("td", { class: "num" }, s.takes), h("td", { class: "num" }, s.approved), h("td", { class: "num" }, fmt.dur(s.seconds)),
        h("td", { class: "num" }, s.noise_floor_db != null ? `${Math.round(s.noise_floor_db)} dBFS` : "–"),
        h("td", { class: "num" }, s.room_t60 != null ? `${s.room_t60.toFixed(2)} s` : "–")))))
      : emptyState("clock", "No sessions yet", "Sessions are created automatically when you open the studio."));
  body.append(h("div", { class: "grid g2" }, modCard, sessCard));
  body.append(h("div", { class: "small faint" }, `Data folder: ${cov.disk.path} · recordings ${fmt.bytes(cov.disk.recordings_bytes)} · trash ${fmt.bytes(cov.disk.trash_bytes)}`));

  return { unmount() { charts.forEach((c) => c.destroy()); } };
}

function milestone(m, isCurrent) {
  const checks = h("div", { class: isCurrent ? "" : "hidden", style: { marginTop: "8px" } }, m.checks.map((c) => h("div", { class: "ms-check" },
    c.progress >= 1 ? h("span", { class: "ok" }, icon("check")) : h("span", { class: "faint" }, icon("target")),
    h("span", {}, c.label), h("span", { class: "muted num" }, c.display))));
  const head = h("div", { class: "ms-head" }, h("div", { class: "ms-icon" }, m.done ? icon("check") : h("span", { class: "tiny", style: { fontWeight: 800 } }, Math.round(m.progress * 100))),
    h("div", { class: "t" }, m.title), h("span", { class: "small muted num" }, m.done ? "done" : `${Math.round(m.progress * 100)}%`));
  head.addEventListener("click", () => checks.classList.toggle("hidden"));
  return h("div", { class: `ms ${m.done ? "done" : ""} ${isCurrent ? "current" : ""}` }, head,
    h("div", { class: "progress thin", style: { marginTop: "8px" } }, h("i", { style: { width: `${m.progress * 100}%` } })), checks);
}
