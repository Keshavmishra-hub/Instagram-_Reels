import { api } from "../api.js";
import { updatePendingBadge } from "../app.js";
import { debounce, emptyState, fmt, h, icon, LANG_LABEL, modal, scoreColor, toast } from "../util.js";
import { Player, StaticWave } from "../waveform.js";

const TABS = [["pending", "Review queue"], ["approved", "Approved"], ["rejected", "Rejected"], ["", "All"], ["trash", "Trash"]];

export async function mount(root, _params, app) {
  const player = new Player();
  const S = { tab: "pending", module: "", lang: "", verdict: "", q: "", items: [], total: 0, selected: new Set(), playing: "" };
  if (location.hash.includes("status=")) S.tab = new URLSearchParams(location.hash.split("?")[1]).get("status") || "pending";

  const tabs = h("div", { class: "seg" });
  const filters = h("div", { class: "filters" });
  const bulk = h("div", { class: "row" });
  const list = h("div", {});
  const exportCard = h("div", { class: "card" });
  root.append(
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Dataset Manager"), h("p", {}, "Listen, approve, correct transcripts and export. Nothing is deleted without your say-so: rejected takes stay on disk and deleted ones go to the trash first."))),
    h("div", { class: "card" }, h("div", { class: "row spread", style: { marginBottom: "12px" } }, tabs, bulk), filters, list),
    exportCard);

  function renderTabs() {
    tabs.replaceChildren(...TABS.map(([v, l]) => h("button", { class: S.tab === v ? "on" : "", onClick: () => { S.tab = v; S.selected.clear(); renderTabs(); load(); } }, l)));
  }

  function renderFilters() {
    const mods = Object.entries(app.vocab.modules || {});
    const sel = (key, opts, label) => {
      const el = h("select", {}, h("option", { value: "" }, label), opts.map(([v, l]) => h("option", { value: v, selected: S[key] === v }, l)));
      el.addEventListener("change", () => { S[key] = el.value; load(); });
      return el;
    };
    const search = h("input", { type: "search", placeholder: "Search text or exercise id", value: S.q, style: { minWidth: "220px" } });
    search.addEventListener("input", debounce(() => { S.q = search.value; load(); }, 250));
    filters.replaceChildren(
      sel("module", mods.map(([k, m]) => [k, `${k} · ${m.title}`]), "All modules"),
      sel("lang", [["en", "English"], ["hi", "Hindi"], ["hinglish", "Hinglish"], ["none", "No speech"]], "All languages"),
      sel("verdict", [["good", "Good"], ["usable", "Usable"], ["rerecord", "Re-record recommended"]], "Any quality"),
      search);
  }

  function renderBulk() {
    const n = S.selected.size;
    const b = (label, action, cls = "") => h("button", { class: `btn btn-sm ${cls}`, disabled: !n, onClick: () => doBulk(action) }, label);
    bulk.replaceChildren(h("span", { class: "small muted" }, n ? `${n} selected` : `${S.total} take${S.total === 1 ? "" : "s"}`),
      S.tab === "trash" ? b("Restore", "restore") : b("Approve", "approved", "btn-ok"),
      S.tab === "trash" ? null : b("Reject", "rejected"),
      S.tab === "trash" ? h("button", { class: "btn btn-sm btn-danger", onClick: emptyTrash, disabled: !S.total }, icon("trash"), "Empty trash") : b("Move to trash", "trash", "btn-danger"));
  }

  async function doBulk(action) {
    const ids = [...S.selected];
    if (action === "trash" && !(await confirmBox(`Move ${ids.length} take(s) to the trash?`, "They can be restored from the Trash tab until you empty it."))) return;
    const r = await api.post("/api/takes/bulk", { ids, action });
    toast(`${r.done.length} updated${r.failed.length ? `, ${r.failed.length} failed: ${r.failed[0].error}` : ""}`, r.failed.length ? "bad" : "ok");
    S.selected.clear();
    await load();
    updatePendingBadge();
  }

  function confirmBox(title, text) {
    return new Promise((resolve) => modal({ title, body: h("p", { class: "muted" }, text), onClose: () => resolve(false),
      actions: [{ label: "Cancel", cls: "btn-ghost", onClick: () => resolve(false) }, { label: "Confirm", cls: "btn-primary", onClick: () => resolve(true) }] }));
  }

  function emptyTrash() {
    const input = h("input", { type: "text", placeholder: "Type DELETE" });
    modal({
      title: "Permanently delete the trash?",
      body: h("div", { class: "stack" }, h("p", { class: "muted" }, `This deletes ${S.total} recording(s) and their metadata from disk. It cannot be undone.`), input),
      actions: [{ label: "Cancel", cls: "btn-ghost" }, { label: "Delete forever", cls: "btn-danger", onClick: async () => {
        if (input.value !== "DELETE") { toast("Type DELETE to confirm.", "bad"); return true; }
        const r = await api.post("/api/trash/empty", { confirm: "DELETE" });
        toast(`${r.deleted} recordings permanently deleted.`);
        load();
      } }],
    });
  }

  async function load() {
    const qs = new URLSearchParams({ limit: "400" });
    if (S.tab === "trash") qs.set("trashed", "true");
    else if (S.tab) qs.set("status", S.tab);
    for (const k of ["module", "lang", "verdict", "q"]) if (S[k]) qs.set(k, S[k]);
    try {
      const r = await api.get(`/api/takes?${qs}`);
      S.items = r.items; S.total = r.total;
    } catch (e) { toast(e.message, "bad"); }
    renderList();
    renderBulk();
  }

  function renderList() {
    if (!S.items.length) {
      list.replaceChildren(emptyState(S.tab === "pending" ? "check" : "db", S.tab === "pending" ? "Nothing waiting for review" : "No takes here",
        S.tab === "pending" ? "Takes you record but don't approve or reject in the studio appear here." : "Try another tab or filter."));
      return;
    }
    const all = h("input", { type: "checkbox", title: "Select all", checked: S.selected.size === S.items.length });
    all.addEventListener("change", () => { if (all.checked) S.items.forEach((t) => S.selected.add(t.id)); else S.selected.clear(); renderList(); renderBulk(); });
    list.replaceChildren(h("div", { class: "take-row", style: { borderBottom: "1px solid var(--line-2)", paddingTop: 0 } }, all, h("span", {}), h("span", { class: "small muted" }, "Take"),
      h("span", { class: "small muted c-dur" }, "Duration"), h("span", { class: "small muted c-score" }, "Quality"), h("span", { class: "small muted" }, "Status")),
      ...S.items.map(row));
  }

  function row(t) {
    const cb = h("input", { type: "checkbox", checked: S.selected.has(t.id) });
    cb.addEventListener("change", () => { cb.checked ? S.selected.add(t.id) : S.selected.delete(t.id); renderBulk(); });
    const play = h("button", { class: "btn btn-sm btn-icon btn-ghost", title: "Play" }, icon(S.playing === t.id ? "pause" : "play"));
    play.addEventListener("click", async () => {
      if (S.playing === t.id) { player.pause(); S.playing = ""; renderList(); return; }
      try { await player.loadUrl(`/api/takes/${t.id}/audio`); S.playing = t.id; player.onend = () => { S.playing = ""; renderList(); }; player.play(); renderList(); }
      catch (e) { toast(e.message, "bad"); }
    });
    const q = t.quality;
    const statusChip = h("span", { class: `chip ${t.status === "approved" ? "ok" : t.status === "rejected" ? "bad" : "warn"}` }, t.status);
    const actions = h("div", { class: "row", style: { gap: "4px", flexWrap: "nowrap", justifyContent: "flex-end" } }, statusChip,
      !t.trashed && t.status !== "approved" ? iconBtn("check", "Approve", () => setStatus(t, "approved")) : null,
      !t.trashed && t.status !== "rejected" ? iconBtn("x", "Reject", () => setStatus(t, "rejected")) : null,
      t.trashed ? iconBtn("restore", "Restore", async () => { await api.post(`/api/takes/${t.id}/restore`); load(); }) : null,
      iconBtn("next", "Details", () => openDrawer(t.id)));
    const asrWarn = t.asr?.match && t.asr.match.verdict !== "read" && t.asr.match.verdict !== "unchecked";
    return h("div", { class: "take-row" }, cb, play,
      h("div", { class: "tx", onClick: () => openDrawer(t.id), style: { cursor: "pointer" } },
        h("div", { class: "t", lang: t.lang === "en" ? "en" : "hi" }, t.text || (t.kind === "silence" ? "Room tone" : t.kind === "clap" ? "Room echo check (clap)" : t.transcript || "(no text)")),
        h("div", { class: "m" }, `${t.exercise_id} · ${LANG_LABEL[t.lang] || t.lang} · ${fmt.date(t.created_at)}${t.kind === "prompt" && !t.transcript_reviewed ? " · transcript needs review" : ""}${asrWarn ? ` · read-check ${Math.round(t.asr.match.coverage * 100)}%` : ""}`)),
      h("span", { class: "num small c-dur" }, fmt.dur(t.audio.duration)),
      h("span", { class: "score-pill c-score", style: { color: scoreColor(q.score, q.verdict) } }, h("span", { class: "dot", style: { background: scoreColor(q.score, q.verdict) } }), q.score, h("span", { class: "tiny muted", style: { fontWeight: 600 } }, q.grade)),
      actions);
  }

  function iconBtn(ic, title, fn) {
    const b = h("button", { class: "btn btn-sm btn-icon btn-ghost", title }, icon(ic));
    b.addEventListener("click", (e) => { e.stopPropagation(); fn(); });
    return b;
  }

  async function setStatus(t, status) {
    try { await api.patch(`/api/takes/${t.id}`, { status }); toast(`Take ${status}.`, status === "approved" ? "ok" : ""); load(); updatePendingBadge(); }
    catch (e) { toast(e.message, "bad"); }
  }

  // ------------------------------------------------------------------ drawer
  let drawer = null, wave = null;
  async function openDrawer(id) {
    closeDrawer();
    let t;
    try { t = await api.get(`/api/takes/${id}`); } catch (e) { toast(e.message, "bad"); return; }
    const back = h("div", { class: "drawer-back", onClick: closeDrawer });
    const panel = h("div", { class: "drawer", role: "dialog" });
    drawer = { back, panel };
    document.body.append(back, panel);
    renderDrawer(panel, t);
  }
  function closeDrawer() {
    if (wave) { wave.destroy(); wave = null; }
    if (drawer) { drawer.back.remove(); drawer.panel.remove(); drawer = null; }
  }

  function renderDrawer(panel, t) {
    const an = t.analysis || {}, q = t.quality, a = t.asr || {};
    const canvas = h("canvas", {});
    const dPlayer = new Player();
    const playBtn = h("button", { class: "btn btn-sm" }, icon("play"), "Play");
    playBtn.addEventListener("click", async () => {
      if (!dPlayer.duration) await dPlayer.loadUrl(`/api/takes/${t.id}/audio`);
      dPlayer.onprogress = (x) => wave && wave.setPlayhead(x);
      dPlayer.toggle();
    });
    const ta = h("textarea", {}, t.transcript || "");
    const saveT = h("button", { class: "btn btn-sm" }, "Save transcript");
    saveT.addEventListener("click", async () => { try { const nt = await api.patch(`/api/takes/${t.id}`, { transcript: ta.value }); toast("Transcript saved.", "ok"); renderDrawer(panel, nt); load(); } catch (e) { toast(e.message, "bad"); } });
    const kv = (rows) => h("div", { class: "kv" }, rows.filter(Boolean).flatMap(([k, v]) => [h("span", { class: "k" }, k), h("span", { class: "v", style: { textAlign: "right", overflowWrap: "anywhere" } }, v ?? "–")]));
    const pitch = an.pitch || {}, rate = an.rate || {}, ps = an.pause_stats || {}, vq = an.voice_quality || {};
    const statusBtns = h("div", { class: "row" },
      t.trashed ? h("button", { class: "btn btn-sm", onClick: async () => { await api.post(`/api/takes/${t.id}/restore`); closeDrawer(); load(); } }, icon("restore"), "Restore") : null,
      !t.trashed && t.status !== "approved" ? h("button", { class: "btn btn-sm btn-ok", onClick: async () => { await setStatus(t, "approved"); closeDrawer(); } }, icon("check"), "Approve") : null,
      !t.trashed && t.status !== "rejected" ? h("button", { class: "btn btn-sm", onClick: async () => { await setStatus(t, "rejected"); closeDrawer(); } }, icon("x"), "Reject") : null,
      !t.trashed ? h("a", { class: "btn btn-sm", href: `#/studio/${encodeURIComponent(t.exercise_id)}`, onClick: closeDrawer }, icon("redo"), "Re-record") : null,
      !t.trashed && ["done", "error"].includes(a.status) ? h("button", { class: "btn btn-sm btn-ghost", onClick: async () => { try { await api.post(`/api/takes/${t.id}/recheck`); toast("Read-check queued."); } catch (e) { toast(e.message, "bad"); } } }, icon("refresh"), "Re-check") : null,
      !t.trashed ? h("button", { class: "btn btn-sm btn-danger", onClick: async () => { await api.post(`/api/takes/${t.id}/trash`); toast("Moved to trash."); closeDrawer(); load(); updatePendingBadge(); } }, icon("trash"), "Trash") : null,
      h("a", { class: "btn btn-sm btn-ghost", href: `/api/takes/${t.id}/audio?variant=original&download=true` }, icon("download"), "Original"));
    panel.replaceChildren(
      h("div", { class: "row spread" }, h("div", {}, h("div", { class: "small muted mono" }, `${t.exercise_id} · take ${t.attempt} · ${t.id}`), h("h2", { style: { marginTop: "4px" } }, `${q.score} · ${q.grade}`)),
        h("button", { class: "btn btn-icon btn-ghost", onClick: closeDrawer, title: "Close" }, icon("x"))),
      h("p", { class: "muted small" }, q.summary),
      h("div", { style: { fontSize: "18px", lineHeight: 1.6, margin: "10px 0" }, lang: t.lang === "en" ? "en" : "hi" }, t.text || "(room tone)"),
      h("div", { class: "review-wave", style: { marginTop: "6px" } }, canvas),
      h("div", { class: "row", style: { marginTop: "10px" } }, playBtn, h("span", { class: "chip" }, fmt.dur(t.audio.duration)), h("span", { class: `chip ${t.status === "approved" ? "ok" : t.status === "rejected" ? "bad" : "warn"}` }, t.status + (t.status_reason ? ` · ${t.status_reason}` : ""))),
      h("div", { class: "divider" }), statusBtns,
      (q.issues || []).length ? h("div", { class: "issues" }, q.issues.map((i) => h("div", { class: `issue ${i.severity}` }, icon(i.severity === "error" ? "alert" : i.severity === "warning" ? "warn" : "info"),
        h("div", {}, h("div", { class: "msg" }, i.message), i.hint ? h("div", { class: "hint" }, i.hint) : null)))) : null,
      h("div", { class: "divider" }),
      h("h3", {}, "Transcript"), h("p", { class: "tiny muted" }, `Source: ${t.transcript_source}${t.transcript_reviewed ? " · reviewed" : ""}. Exports use this text, so it must match what was actually said.`),
      ta, h("div", { class: "row", style: { marginTop: "8px" } }, saveT),
      a.status === "done" ? h("div", { class: "notice info", style: { marginTop: "10px" } }, icon("info"), h("div", {}, h("b", {}, `Whisper ${a.model} heard: `), `“${a.text}”`,
        a.match && a.match.verdict !== "unchecked" ? h("div", { class: "small", style: { marginTop: "4px" } }, `${Math.round(a.match.coverage * 100)}% of the expected words recognised${a.match.missing.length ? " · possibly missed: " + a.match.missing.map((i) => a.match.expected_words[i]).slice(0, 10).join(", ") : ""}`) : null)) : null,
      h("div", { class: "divider" }), h("h3", { style: { marginBottom: "8px" } }, "Measurements"),
      kv([["Speech", `${an.speech_seconds ?? "–"} s`], ["SNR", an.snr_db != null ? `${an.snr_db} dB` : "–"], ["Noise floor", `${an.noise_floor_dbfs} dBFS`],
        ["Speech level", `${an.speech_level_dbfs} dBFS`], ["Peak", `${an.peak_dbfs} dBFS`], ["Clipping", `${an.clipping?.events ?? 0} events`],
        ["Bandwidth", an.bandwidth?.effective_hz ? `${(an.bandwidth.effective_hz / 1000).toFixed(1)} kHz` : "–"], an.room ? ["Room echo (T60, clap)", an.room.t60 != null ? `${an.room.t60} s` : (an.room.reason || "–")] : null,
        ["Hum", an.hum?.detected ? `${an.hum.base_hz} Hz` : "none"], ["Leading / trailing silence", `${an.leading_silence ?? "–"} / ${an.trailing_silence ?? "–"} s`],
        pitch.median_hz ? ["Pitch median (5–95%)", `${pitch.median_hz} Hz (${pitch.p5_hz}–${pitch.p95_hz})`] : null, pitch.range_st ? ["Pitch range", `${pitch.range_st} semitones`] : null,
        an.hnr_db != null ? ["Harmonicity (HNR)", `${an.hnr_db} dB`] : null,
        rate.articulation_rate ? ["Articulation rate", `${rate.articulation_rate} syll/s`] : null, rate.wpm ? ["Words per minute", rate.wpm] : null,
        ps.count != null ? ["Pauses ≥0.2 s", `${ps.count}${ps.mean_s ? ` · mean ${ps.mean_s}s` : ""}`] : null, ["Breaths heard", an.breaths ?? "–"],
        vq.jitter_local_pct != null ? ["Jitter / shimmer (local)", `${vq.jitter_local_pct}% / ${vq.shimmer_local_pct}%`] : null, vq.hnr_db != null ? ["Sustained-vowel HNR", `${vq.hnr_db} dB`] : null]),
      h("div", { class: "divider" }), h("h3", { style: { marginBottom: "8px" } }, "Recording"),
      kv([["Device", t.capture.device_label], ["Sample rate", `${t.audio.sample_rate} Hz · ${t.audio.subtype}`], ["Browser processing", Object.entries(t.capture.constraints_applied || {}).filter(([k]) => ["echoCancellation", "noiseSuppression", "autoGainControl"].includes(k)).map(([k, v]) => `${k}: ${v}`).join(", ") || "–"],
        ["Pre-roll", `${t.capture.preroll_sec?.toFixed?.(2) ?? t.capture.preroll_sec} s`], ["Auto-stopped", t.capture.auto_stopped ? "yes" : "no"], ["Session", t.session_id], ["Recorded", fmt.date(t.created_at)],
        ["File", t.audio.file], ["SHA-256", t.audio.sha256.slice(0, 16) + "…"]]));
    const markers = [...((an.clipping || {}).times || []).map((x) => ({ t: x, kind: "clip" })), ...((an.dropouts || {}).items || []).map((d) => ({ t: d.at, kind: "drop" }))];
    wave = new StaticWave(canvas, { peaks: an.waveform || [], duration: t.audio.duration, segments: an.segments || [], markers,
      onSeek: async (x) => { if (!dPlayer.duration) await dPlayer.loadUrl(`/api/takes/${t.id}/audio`); dPlayer.onprogress = (y) => wave && wave.setPlayhead(y); dPlayer.play(x); } });
  }

  // ------------------------------------------------------------------ exports
  async function renderExports() {
    let data;
    try { data = await api.get("/api/exports"); } catch (e) { exportCard.replaceChildren(h("div", { class: "notice bad" }, icon("alert"), e.message)); return; }
    const profiles = data.profiles;
    const sel = h("select", {}, Object.entries(profiles).map(([k, p]) => h("option", { value: k, selected: k === (app.profile.clone_backend_export || "master") }, p.title)));
    const desc = h("p", { class: "small muted", style: { margin: "8px 0" } });
    const sr = h("select", { style: { width: "auto" } });
    const incl = h("input", { type: "checkbox" });
    const update = () => {
      const p = profiles[sel.value];
      desc.textContent = p.summary + (p.note ? " " + p.note : "");
      sr.replaceChildren(...(p.sample_rates || []).map((r) => h("option", { value: r, selected: r === p.default_rate }, r ? `${r / 1000} kHz` : "original rate")));
      sr.parentElement && (sr.parentElement.style.display = (p.sample_rates || []).length > 1 ? "" : "none");
    };
    sel.addEventListener("change", update);
    const go = h("button", { class: "btn btn-primary" }, icon("download"), "Create export");
    const result = h("div", {});
    go.addEventListener("click", async () => {
      go.disabled = true; go.replaceChildren(h("span", { class: "spinner" }), "Exporting…");
      try {
        const r = await api.post("/api/exports", { profile: sel.value, options: { sample_rate: +sr.value || 0, include_pending: incl.checked } });
        result.replaceChildren(h("div", { class: "notice ok", style: { marginTop: "12px" } }, icon("okc"), h("div", {}, h("b", {}, `${r.takes} takes · ${fmt.mins(r.seconds)} min exported. `),
          h("a", { href: r.download }, "Download ZIP"), h("div", { class: "small muted" }, r.path), r.warnings?.length ? h("div", { class: "small", style: { marginTop: "4px" } }, r.warnings.join(" ")) : null)));
        renderPrevious();
      } catch (e) { toast(e.message, "bad", 6000); }
      go.disabled = false; go.replaceChildren(icon("download"), "Create export");
    });
    const prev = h("div", {});
    async function renderPrevious() {
      const d = await api.get("/api/exports");
      prev.replaceChildren(d.exports.length ? h("table", { class: "tbl", style: { marginTop: "14px" } }, h("thead", {}, h("tr", {}, h("th", {}, "Export"), h("th", {}, "Takes"), h("th", {}, "Minutes"), h("th", {}, ""))),
        h("tbody", {}, d.exports.slice(0, 10).map((x) => h("tr", {}, h("td", { class: "mono" }, x.name), h("td", { class: "num" }, x.takes ?? "–"), h("td", { class: "num" }, x.seconds != null ? fmt.mins(x.seconds) : "–"),
          h("td", {}, x.zip ? h("a", { href: `/api/exports/${encodeURIComponent(x.name)}/download` }, "ZIP") : ""))))) : null);
    }
    exportCard.replaceChildren(h("div", { class: "card-head" }, h("h3", {}, icon("download"), "Export dataset")),
      h("p", { class: "muted small" }, "Exports contain approved takes only (unless you tick the box), trimmed to speech with a little padding, with transcripts and full metadata. Originals are never modified."),
      h("div", { class: "row" }, h("label", { class: "field", style: { minWidth: "260px", flex: 1 } }, "Format", sel), h("label", { class: "field" }, "Sample rate", sr),
        h("label", { class: "switch", style: { marginTop: "18px" } }, incl, "Include pending takes"), h("div", { style: { marginTop: "18px" } }, go)),
      desc, result, prev);
    update();
    renderPrevious();
  }

  renderTabs(); renderFilters(); renderBulk();
  await load();
  renderExports();
  return {
    unmount() { player.stop(); closeDrawer(); },
    onKey(e) { if (e.key === "Escape") closeDrawer(); },
  };
}
