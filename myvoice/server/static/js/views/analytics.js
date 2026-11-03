import { api } from "../api.js";
import { barChart, histogram, langColor, lineChart, rangePlot } from "../charts.js";
import { emptyState, fmt, h, icon } from "../util.js";

export async function mount(root) {
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Voice Analytics"),
    h("p", {}, "Measurements of your voice from your own recordings: pitch, pace, pauses, read accuracy, audio quality and consistency across sessions."))));
  const body = h("div", { class: "stack" }, h("div", { class: "empty" }, h("span", { class: "spinner" })));
  root.append(body);
  let d;
  try { d = await api.get("/api/analytics"); } catch (e) { body.replaceChildren(h("div", { class: "notice bad" }, icon("alert"), e.message)); return; }
  body.replaceChildren();
  const charts = [];
  // session labels in the viewer's own time zone
  for (const arr of [d.quality.sessions, d.consistency.anchor_sessions, d.consistency.mic]) for (const r of arr) if (r.started_at) r.label = fmt.date(r.started_at);
  if (!d.n_speech) {
    body.append(h("div", { class: "card" }, emptyState("chart", "No speech recordings to analyse yet", "Record and approve a few takes in the studio; every chart here is computed from them.",
      h("a", { class: "btn btn-primary", href: "#/studio" }, "Open the studio"))));
    return;
  }
  if (d.basis === "pending") body.append(h("div", { class: "notice info" }, icon("info"), h("div", {}, "Nothing is approved yet, so these figures use takes waiting for review. They switch to approved takes automatically.")));

  const card = (title, sub, ...content) => h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, title), sub ? h("span", { class: "small muted" }, sub) : null), ...content);
  const box = () => h("div", {});
  const stat = (k, v, unit) => h("div", { class: "metric" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v ?? "–", v != null && unit ? h("small", {}, " " + unit) : null));

  // ------------------------------------------------------------------ pitch
  const p = d.pitch;
  const pitchHist = box(), pitchEmo = box(), pitchLang = box();
  body.append(card("Pitch", `${p.frames.toLocaleString()} voiced frames from ${d.n_speech} takes (Praat, speaker-adaptive range)`,
    h("div", { class: "metrics", style: { marginTop: 0, marginBottom: "14px" } }, stat("Typical pitch", p.median_hz != null ? Math.round(p.median_hz) : null, "Hz"),
      stat("5th percentile", p.p5_hz != null ? Math.round(p.p5_hz) : null, "Hz"), stat("95th percentile", p.p95_hz != null ? Math.round(p.p95_hz) : null, "Hz"), stat("Speaking range", p.range_st, "semitones")),
    h("div", { class: "grid g2" }, h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Distribution of your pitch while speaking"), pitchHist),
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Median pitch per take, by emotion (dot = median, line = middle half)"), pitchEmo))));
  if (p.hist.length) charts.push(histogram(pitchHist, { bins: p.hist, xFormat: (v) => `${v}`, xLabel: "Hz" }));
  else pitchHist.append(h("p", { class: "muted small" }, "No voiced frames yet."));
  if (p.by_emotion.length) charts.push(rangePlot(pitchEmo, { rows: p.by_emotion, format: (v) => Math.round(v), unit: " Hz" }));
  if (p.by_lang.length > 1) {
    body.lastChild.append(h("div", { class: "small muted", style: { margin: "14px 0 6px" } }, "By language"), pitchLang);
    charts.push(rangePlot(pitchLang, { rows: p.by_lang.map((r) => ({ ...r, color: langColor(r.id) })), format: (v) => Math.round(v), unit: " Hz" }));
  }

  // ------------------------------------------------------------------ pace & pauses
  const rPace = box(), rPause = box();
  body.append(h("div", { class: "grid g2" },
    card("Speaking rate", "articulation rate, syllables per second (pauses excluded)", d.rate.by_pace.length ? rPace : h("p", { class: "muted small" }, "Needs read takes with a known script."),
      h("p", { class: "tiny muted", style: { marginTop: "8px" } }, "Shows whether slow and fast exercises really differ for you. Spontaneous speech: ",
        d.rate.spontaneous ? `${d.rate.spontaneous.mid} syll/s (${d.rate.spontaneous.n} takes)` : "not recorded yet", ".")),
    card("Pauses", "average pauses (≥0.2 s) per minute, by style", d.pauses.by_style.length ? rPause : h("p", { class: "muted small" }, "Needs takes longer than a few seconds."),
      h("p", { class: "tiny muted", style: { marginTop: "8px" } }, d.pauses.breaths_per_min != null ? `Audible breaths: about ${d.pauses.breaths_per_min} per minute in longer takes.` : ""))));
  if (d.rate.by_pace.length) charts.push(rangePlot(rPace, { rows: d.rate.by_pace, format: (v) => v.toFixed(1), unit: " syll/s", labelWidth: 80 }));
  if (d.pauses.by_style.length) charts.push(barChart(rPause, { rows: d.pauses.by_style.map((r) => ({ label: r.label, value: r.per_minute, display: `${r.per_minute}/min`, note: r.mean_s ? `mean pause ${r.mean_s} s · ${r.n} takes` : `${r.n} takes` })), labelWidth: 150,
    table: { columns: ["Style", "Pauses per minute", "Mean pause (s)", "Takes"], rows: d.pauses.by_style.map((r) => [r.label, r.per_minute, r.mean_s ?? "–", r.n]) } }));

  // ------------------------------------------------------------------ read-check
  const rRead = box();
  body.append(card("Read accuracy", `speech recognition word match · ${d.read.checked} checked takes`,
    d.read.by_lang.length ? rRead : h("p", { class: "muted small" }, "No read-checks yet (install faster-whisper to enable them)."),
    d.read.often_missed.length ? h("div", { style: { marginTop: "12px" } }, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Words the recogniser often did not hear — listen to these takes:"),
      h("div", { class: "emo-grid" }, d.read.often_missed.map((w) => h("span", { class: "emo" }, w.word, h("span", { class: "n" }, w.count))))) : null,
    h("p", { class: "tiny muted", style: { marginTop: "10px" } }, "This is the share of displayed words that Whisper recognised. It reflects both your reading and the recogniser's limits (weaker in Hindi); it is not a phonetic pronunciation score.")));
  if (d.read.by_lang.length) charts.push(barChart(rRead, { rows: d.read.by_lang.map((r) => ({ label: r.label, value: r.coverage * 100, color: langColor(r.id), display: `${Math.round(r.coverage * 100)}%`, note: `${r.n} takes · ${r.partial} partial` })), max: 100, labelWidth: 90,
    table: { columns: ["Language", "Words recognised", "Takes", "Partial"], rows: d.read.by_lang.map((r) => [r.label, `${Math.round(r.coverage * 100)}%`, r.n, r.partial]) } }));

  // ------------------------------------------------------------------ audio quality
  const q = d.quality;
  const qScore = box(), qIssues = box(), qSnr = box(), qNoise = box();
  body.append(card("Audio quality", q.mean != null ? `mean score ${q.mean}` : "",
    h("div", { class: "grid g2" }, h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Quality score distribution"), qScore),
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Most frequent problems (all takes)"), q.issues.length ? qIssues : h("p", { class: "muted small" }, "No warnings so far."))),
    q.sessions.length > 1 ? h("div", { class: "grid g2", style: { marginTop: "14px" } },
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Signal-to-noise ratio per session (dB)"), qSnr),
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Room noise floor per session (dBFS)"), qNoise)) : null));
  if (q.score_hist.length) charts.push(histogram(qScore, { bins: q.score_hist, xFormat: (v) => v, height: 150 }));
  if (q.issues.length) charts.push(barChart(qIssues, { rows: q.issues.map((i) => ({ label: i.code.replace(/_/g, " "), value: i.count, display: String(i.count), note: i.label })), labelWidth: 140 }));
  if (q.sessions.length > 1) {
    const labels = q.sessions.map((s) => s.label);
    charts.push(lineChart(qSnr, { series: [{ name: "SNR", color: "var(--series-1)", points: q.sessions.map((s, i) => ({ x: i, y: s.snr, label: `${s.n} takes` })) }], xLabels: labels, yFormat: (v) => Math.round(v), height: 170 }));
    charts.push(lineChart(qNoise, { series: [{ name: "Noise floor", color: "var(--series-1)", points: q.sessions.map((s, i) => ({ x: i, y: s.noise_floor, label: s.device })) }], xLabels: labels, yFormat: (v) => Math.round(v), height: 170 }));
  }
  const echoSessions = q.sessions.filter((s) => s.room_t60 != null);
  if (echoSessions.length) {
    const qEcho = box();
    body.lastChild.append(h("div", { style: { marginTop: "14px" } }, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Room echo per session (reverberation time from the warm-up clap, seconds — under 0.4 s is ideal)"), qEcho));
    charts.push(barChart(qEcho, { rows: echoSessions.map((s) => ({ label: s.label, value: s.room_t60, display: `${s.room_t60.toFixed(2)} s`, note: s.device })), labelWidth: 110 }));
  }

  // ------------------------------------------------------------------ consistency
  const c = d.consistency;
  const cF0 = box(), cMic = box();
  body.append(card("Consistency across sessions", "anchor sentences repeated each session",
    c.anchor_sessions.length >= 2 ? h("div", { class: "grid g2" },
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Median pitch of the anchor sentences (Hz)"), cF0,
        c.f0_spread_st != null ? h("p", { class: "tiny muted", style: { marginTop: "6px" } }, `Session-to-session spread: ${c.f0_spread_st} semitones. A semitone or two is normal day-to-day variation; much more usually means a tired or ill voice, or a different delivery.`) : null),
      h("div", {}, h("div", { class: "small muted", style: { marginBottom: "6px" } }, "Spectral difference from your average (dB) — microphone / position consistency"), c.mic.length >= 2 ? cMic : h("p", { class: "muted small" }, "Needs two sessions with approved takes.")))
      : h("p", { class: "muted small" }, "Record the warm-up anchors in at least two sessions (ideally on different days) to see this."),
    h("p", { class: "tiny muted", style: { marginTop: "8px" } }, "The goal is not identical takes — natural variation is part of your voice. Large jumps in microphone spectrum usually mean a different mic, distance or room.")));
  if (c.anchor_sessions.length >= 2) charts.push(lineChart(cF0, { series: [{ name: "Median pitch", color: "var(--series-1)", points: c.anchor_sessions.map((s, i) => ({ x: i, y: s.f0, label: `${s.n} anchors` })) }], xLabels: c.anchor_sessions.map((s) => s.label), yFormat: (v) => Math.round(v), height: 170 }));
  if (c.mic.length >= 2) charts.push(barChart(cMic, { rows: c.mic.map((m) => ({ label: m.label, value: m.distance_db, display: `${m.distance_db} dB`, note: m.device })), labelWidth: 100 }));

  // ------------------------------------------------------------------ voice quality
  if (d.voice_quality.length || d.range.length) {
    body.append(card("Voice baseline (sustained vowels & pitch glide)", "for reference — not a medical assessment",
      d.voice_quality.length ? h("table", { class: "tbl" }, h("thead", {}, h("tr", {}, ["Date", "Vowel", "Pitch", "Jitter", "Shimmer", "HNR"].map((x) => h("th", {}, x)))),
        h("tbody", {}, d.voice_quality.map((v) => h("tr", {}, h("td", {}, v.date), h("td", {}, v.text), h("td", { class: "num" }, v.f0 ? `${Math.round(v.f0)} Hz` : "–"),
          h("td", { class: "num" }, v.jitter != null ? `${v.jitter}%` : "–"), h("td", { class: "num" }, v.shimmer != null ? `${v.shimmer}%` : "–"), h("td", { class: "num" }, v.hnr != null ? `${v.hnr} dB` : "–"))))) : null,
      d.range.length ? h("p", { class: "small", style: { marginTop: "10px" } }, "Pitch glide range: ", d.range.map((r) => `${Math.round(r.low_hz)}–${Math.round(r.high_hz)} Hz (${r.range_st} semitones, ${r.date})`).join(" · ")) : null,
      h("p", { class: "tiny muted", style: { marginTop: "8px" } }, "Jitter, shimmer and harmonics-to-noise ratio are Praat measures of a steady vowel. Track them over time on the same microphone; values vary between devices and rooms.")));
  }
  return { unmount() { charts.forEach((ch) => ch.destroy()); } };
}
