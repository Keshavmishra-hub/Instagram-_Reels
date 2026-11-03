import { api } from "../api.js";
import { updatePendingBadge, welcome } from "../app.js";
import { outbox } from "../outbox.js";
import { CLIENT_VERSION, MicRecorder, encodeWavFloat32 } from "../recorder.js";
import { fmt, h, icon, isDeva, LANG_LABEL, modal, scoreRing, toast } from "../util.js";
import { LevelMeter, LiveWave, Player, StaticWave } from "../waveform.js";

const DEVICE_KEY = "myvoice-device";

export async function mount(root, params, app) {
  const mic = new MicRecorder();
  const player = new Player();
  const S = {
    state: "init", ex: null, pick: null, take: null, local: null, history: [], session: null, replaces: "",
    mode: sessionStorage.getItem("myvoice-mode") || "adaptive", showRoman: app.prefs.show_roman !== false,
    poll: null, raf: null, breakAt: 0, sessionTakes: [], coverage: null, disposed: false, nospeechShown: false,
  };
  let live = null, meter = null, review = null;

  // ------------------------------------------------------------------ skeleton
  const top = h("div", { class: "studio-top" });
  const promptCard = h("div", { class: "card prompt-card" });
  const deck = h("div", { class: "card deck" });
  const reviewCard = h("div", { class: "card review hidden" });
  const side = h("aside", { class: "side stack" });
  root.append(
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Recording Studio"),
      h("p", {}, "Read what you see, the way you would naturally say it. The studio checks every take before it joins your dataset."))),
    top, h("div", { class: "studio" }, h("div", {}, promptCard, deck, reviewCard), side));

  // ------------------------------------------------------------------ session
  try { S.session = await api.post("/api/sessions", {}); } catch (e) { toast(e.message, "bad"); }

  async function loadSessionTakes() {
    if (!S.session) return;
    try { S.sessionTakes = (await api.get(`/api/takes?session=${S.session.id}&limit=1000`)).items; } catch {}
    renderSide();
  }

  async function loadCoverage() {
    try { S.coverage = await api.get("/api/coverage"); } catch {}
    renderSide();
  }

  // ------------------------------------------------------------------ exercises
  async function loadExercise(eid, { pushHistory = true } = {}) {
    stopPolling();
    player.stop();
    S.take = null; S.local = null; S.replaces = "";
    try {
      if (eid) {
        S.ex = await api.get(`/api/exercises/${encodeURIComponent(eid)}`);
        S.pick = { phase: "manual", reason: "Chosen by you." };
      } else {
        const exclude = S.history.slice(-1).join(",");
        const r = await api.get(`/api/next?session=${S.session?.id || ""}&mode=${encodeURIComponent(S.mode)}&exclude=${encodeURIComponent(exclude)}`);
        S.pick = r;
        S.ex = r.exercise;
      }
    } catch (e) { toast(e.message, "bad"); return; }
    if (S.ex && pushHistory && S.history[S.history.length - 1] !== S.ex.id) S.history.push(S.ex.id);
    setState(mic.isOpen ? "ready" : "nomic");
    renderPrompt();
    reviewCard.classList.add("hidden");
  }

  // ------------------------------------------------------------------ prompt
  function chips(ex) {
    const c = [h("span", { class: "chip accent" }, `${ex.module} · ${ex.section_title}`)];
    if (ex.lang !== "none") c.push(h("span", { class: "chip" }, icon("globe"), LANG_LABEL[ex.lang] || ex.lang));
    if (ex.emotion !== "neutral") c.push(h("span", { class: "chip warn" }, ex.emotion_title));
    if (!["neutral", "analysis"].includes(ex.style)) c.push(h("span", { class: "chip" }, ex.style_title));
    if (ex.pace !== "normal") c.push(h("span", { class: "chip info" }, ex.pace === "slow" ? "Slow pace" : "Fast pace"));
    if (ex.volume !== "normal") c.push(h("span", { class: "chip info" }, { soft: "Soft voice", loud: "Projected voice", whisper: "Whisper-like" }[ex.volume]));
    if (S.pick && S.pick.phase === "warmup") c.push(h("span", { class: "chip ok" }, "Session warm-up"));
    if (ex.takes && ex.takes.approved) c.push(h("span", { class: "chip ok" }, icon("check"), `${ex.takes.approved} approved`));
    return c;
  }

  function promptTextEl(ex, missing) {
    const kindCls = { paragraph: "paragraph", word_list: "wordlist", silence: "silence", clap: "silence" }[ex.kind] || "";
    const el = h("div", { class: `prompt-text ${kindCls} ${isDeva(ex.text) ? "deva" : ""}`, lang: ex.lang === "en" ? "en" : "hi" });
    if (ex.kind === "silence") {
      el.append(h("div", {}, h("div", { style: { fontSize: "54px", lineHeight: 1 } }, "🤫"), h("div", { style: { marginTop: "10px" } }, `Stay silent for ${ex.fixed_sec || 5} seconds`)));
      return el;
    }
    if (ex.kind === "clap") {
      el.append(h("div", {}, h("div", { style: { fontSize: "54px", lineHeight: 1 } }, "👏"), h("div", { style: { marginTop: "10px" } }, "Clap once, sharply — then stay silent")));
      return el;
    }
    if (missing && missing.words && missing.idx.length && !ex.spoken) {
      let pos = 0;
      const text = ex.text;
      missing.words.forEach((w, i) => {
        const at = text.indexOf(w, pos);
        if (at < 0) return;
        if (at > pos) el.append(text.slice(pos, at));
        el.append(missing.idx.includes(i) ? h("span", { class: "miss", title: "Speech recognition did not hear this word" }, w) : w);
        pos = at + w.length;
      });
      el.append(text.slice(pos));
    } else el.textContent = ex.text;
    return el;
  }

  function renderPrompt(missing) {
    const ex = S.ex;
    promptCard.replaceChildren();
    if (!ex) {
      promptCard.append(h("div", { class: "empty" }, icon("sparkle"), h("h3", {}, "Nothing left to record right now"),
        h("p", {}, S.pick?.reason || ""), h("div", { class: "row", style: { justifyContent: "center" } },
          h("a", { class: "btn", href: "#/dataset?status=pending" }, "Review pending takes"), h("a", { class: "btn btn-primary", href: "#/dashboard" }, "See dashboard"))));
      return;
    }
    const tools = h("div", { class: "prompt-tools" },
      h("button", { class: "btn btn-sm btn-ghost btn-icon", title: "Smaller text (−)", onClick: (e) => { e.currentTarget.blur(); scale(-0.1); } }, "A−"),
      h("button", { class: "btn btn-sm btn-ghost btn-icon", title: "Bigger text (+)", onClick: (e) => { e.currentTarget.blur(); scale(0.1); } }, "A+"),
      ex.roman ? h("button", { class: `btn btn-sm ${S.showRoman ? "" : "btn-ghost"}`, title: "Roman transliteration (T)", onClick: (e) => { e.currentTarget.blur(); toggleRoman(); } }, "Roman") : null);
    promptCard.append(tools, h("div", { class: "prompt-meta" }, chips(ex)));
    if (ex.instruction) promptCard.append(h("div", { class: "prompt-instruction" }, icon("info"), h("span", {}, ex.instruction)));
    if (ex.context) promptCard.append(h("div", { class: "prompt-context" }, h("b", {}, ex.kind === "silence" ? "" : "Situation: "), ex.context));
    if (ex.templated && ex.text.includes("/") && !(app.profile.hindi_forms)) {
      promptCard.append(h("div", { class: "notice info", style: { marginTop: "10px" } }, icon("user"),
        h("div", {}, "Choose your Hindi verb forms (रहा / रही) so sentences match how you speak. ", h("a", { href: "#", onClick: (e) => { e.preventDefault(); welcome(true); } }, "Set now"))));
    }
    if (ex.cue) promptCard.append(h("div", { class: "prompt-cue" }, h("span", { class: "who" }, "They say"), ex.cue));
    promptCard.append(promptTextEl(ex, missing));
    if (ex.roman && S.showRoman) promptCard.append(h("div", { class: "prompt-roman" }, ex.roman));
    if (ex.hints && ex.hints.length) promptCard.append(h("div", { class: "prompt-hints" }, h("span", { class: "small muted" }, "Talking points:"), ex.hints.map((t) => h("span", { class: "chip" }, t))));
    if (ex.kind === "prompt") promptCard.append(h("div", { class: "small muted", style: { marginTop: "10px" } },
      `Speak freely for ${ex.min_sec || 30}–${ex.max_sec || 90} seconds. Pauses are fine; auto-stop waits for ${ex.auto_stop_sec}s of silence.`));
    if (S.pick && S.pick.reason) promptCard.append(h("div", { class: "prompt-reason" }, icon("target"), h("span", {}, S.pick.reason)));
  }

  function scale(d) {
    const v = Math.max(0.7, Math.min(1.8, +(app.prefs.text_scale || 1) + d));
    document.documentElement.style.setProperty("--prompt-scale", String(v));
    app.savePrefs({ text_scale: +v.toFixed(2) }).catch(() => {});
  }
  function toggleRoman() {
    S.showRoman = !S.showRoman;
    app.savePrefs({ show_roman: S.showRoman }).catch(() => {});
    renderPrompt(lastMissing());
  }
  function lastMissing() {
    const m = S.take?.asr?.match;
    return m && m.verdict !== "unchecked" ? { words: m.expected_words, idx: m.missing } : null;
  }

  // ------------------------------------------------------------------ deck (mic + controls)
  const timerEl = h("div", { class: "timer" }, "00:00.0", h("small", {}, "duration"));
  const stateLine = h("div", { class: "state-line" });
  const recBtn = h("button", { class: "rec-btn", title: "Record (Space)", "aria-label": "Record" }, h("span", { class: "ico" }));
  const pauseBtn = h("button", { class: "btn btn-icon", title: "Pause / resume (K)", "aria-label": "Pause" }, icon("pause"));
  const backBtn = h("button", { class: "btn btn-icon", title: "Previous exercise (B)", "aria-label": "Previous" }, icon("back"));
  const skipBtn = h("button", { class: "btn", title: "Skip (N)" }, icon("skip"), "Skip", h("span", { class: "kbd" }, "N"));
  const waveCanvas = h("canvas", {});
  const waveLabel = h("div", { class: "wave-label" }, h("span", { class: "dot" }), "Microphone");
  const stopHint = h("div", { class: "stop-ring" });
  const meterEl = h("div", { class: "level" });

  recBtn.addEventListener("click", (e) => { e.currentTarget.blur(); toggleRecord(); });
  pauseBtn.addEventListener("click", (e) => { e.currentTarget.blur(); togglePause(); });
  backBtn.addEventListener("click", (e) => { e.currentTarget.blur(); goBack(); });
  skipBtn.addEventListener("click", (e) => { e.currentTarget.blur(); skip(); });

  function renderDeck() {
    deck.replaceChildren();
    if (S.state === "nomic" || S.state === "init") { deck.append(micGate()); return; }
    deck.append(
      h("div", { class: "meter-row" }, h("div", { class: "wave-wrap" }, waveCanvas, waveLabel, stopHint), meterEl),
      h("div", { class: "controls" }, backBtn, pauseBtn, recBtn, timerEl, skipBtn),
      stateLine);
    if (!live) { live = new LiveWave(waveCanvas); live.setRate(mic.sampleRate || 48000); }
    if (!meter) meter = new LevelMeter(meterEl);
    updateControls();
  }

  function micGate() {
    const supported = MicRecorder.supported();
    if (!supported) {
      const insecure = !window.isSecureContext;
      return h("div", { class: "mic-gate" }, h("div", { class: "big" }, icon("mic")), h("h2", {}, "Microphone not available here"),
        insecure ? h("p", {}, "Browsers only allow microphone access on secure pages: http://localhost / 127.0.0.1 on this computer, or HTTPS. To record from a phone, start the studio with ",
          h("span", { class: "mono" }, "python -m myvoice serve --lan"), " and open the https:// link it prints.")
          : h("p", {}, "This browser does not support the Web Audio recording the studio needs. Use a current Chrome, Edge, Firefox or Safari."));
    }
    const btn = h("button", { class: "btn btn-primary btn-lg" }, icon("mic"), "Enable microphone");
    btn.addEventListener("click", () => openMic());
    return h("div", { class: "mic-gate" }, h("div", { class: "big" }, icon("mic")),
      h("h2", {}, "Let's hear your voice"),
      h("p", {}, "Your browser will ask for permission to use the microphone. Audio is recorded losslessly and saved only on this computer."),
      h("ul", {},
        h("li", {}, "Use a wired or USB microphone if you have one. Bluetooth headsets switch to low-quality “call mode” when their mic is used."),
        h("li", {}, "Pick a quiet room with soft furnishings; switch off fans and AC for the session."),
        h("li", {}, "Sit a hand's width from the mic and keep that distance for every session."),
        h("li", {}, "The studio turns off the browser's echo cancellation, noise suppression and auto-gain, which would alter your voice.")),
      btn,
      h("p", { class: "small muted", style: { marginTop: "12px" } }, "If you blocked the microphone earlier, allow it again from the padlock / site settings icon in the address bar."));
  }

  async function openMic(deviceId) {
    try {
      const want = deviceId ?? localStorage.getItem(DEVICE_KEY) ?? "";
      let info;
      try { info = await mic.open(want || undefined); }
      catch (e) { if (want && e.name === "OverconstrainedError") info = await mic.open(); else throw e; }
      localStorage.setItem(DEVICE_KEY, mic.deviceId || "");
      if (live) live.setRate(mic.sampleRate);
      mic.addEventListener("chunk", onChunk);
      mic.addEventListener("autostop", (e) => { if (S.state === "recording") stopAndSave(e.detail.reason); });
      mic.addEventListener("trackevent", (e) => {
        if (e.detail.type === "ended") { toast("The microphone was disconnected.", "bad"); if (S.state === "recording") stopAndSave("ended"); setState("nomic"); }
        else if (e.detail.type === "mute" && S.state === "recording") toast("The microphone was muted by the system.", "bad");
      });
      if (S.session) api.patch(`/api/sessions/${S.session.id}`, { device_label: info.label, sample_rate: info.sampleRate, constraints_applied: info.applied }).catch(() => {});
      setState("ready");
      renderSide();
      const processed = ["echoCancellation", "noiseSuppression", "autoGainControl"].filter((k) => info.applied[k] === true);
      if (processed.length) toast(`Your browser kept ${processed.join(", ")} on. Takes will be flagged; Chrome/Edge/Firefox on a computer turn it off.`, "bad", 8000);
    } catch (e) {
      const msg = e.name === "NotAllowedError" ? "Microphone permission was denied. Allow it from the address bar's site settings, then try again."
        : e.name === "NotFoundError" ? "No microphone found. Connect one and try again." : `Could not open the microphone: ${e.message}`;
      toast(msg, "bad", 8000);
      setState("nomic");
    }
  }

  let lastEp = null;
  function onChunk(e) {
    const { samples, peak, recording, ep } = e.detail;
    if (live) live.push(samples, recording);
    if (meter) meter.update(peak);
    if (ep) lastEp = ep;
  }

  function setState(st) {
    S.state = st;
    if (st === "nomic" || st === "init" || !deck.querySelector(".controls")) renderDeck();
    updateControls();
  }

  function updateControls() {
    const st = S.state;
    recBtn.classList.toggle("recording", st === "recording" || st === "paused");
    recBtn.classList.toggle("paused", st === "paused");
    recBtn.disabled = !S.ex || st === "saving" || st === "nomic";
    recBtn.title = st === "recording" || st === "paused" ? "Stop (Space)" : "Record (Space)";
    pauseBtn.disabled = !(st === "recording" || st === "paused") || ["silence", "clap"].includes(S.ex?.kind);
    pauseBtn.replaceChildren(icon(st === "paused" ? "play" : "pause"));
    backBtn.disabled = st === "recording" || st === "paused" || st === "saving" || S.history.length < 2;
    skipBtn.disabled = st === "recording" || st === "paused" || st === "saving" || !S.ex;
    waveLabel.firstChild.className = `dot ${st === "recording" ? "rec" : st === "paused" ? "warn" : mic.isOpen ? "ok" : ""}`;
    waveLabel.lastChild && (waveLabel.childNodes[1].textContent = st === "recording" ? " Recording" : st === "paused" ? " Paused" : ` ${mic.label || "Microphone"}`);
    const lines = {
      ready: S.ex?.kind === "silence" ? "Press Space or the red button, then stay silent."
        : S.ex?.kind === "clap" ? "Press Space or the red button, clap once, then stay silent." : "Press Space or the red button and start speaking. It stops by itself when you finish.",
      recording: S.ex && S.ex.auto_stop_sec > 0 && app.prefs.auto_stop !== false ? "Recording… stops after a pause of " + S.ex.auto_stop_sec + " s, or press Space." : "Recording… press Space to stop.",
      paused: "Paused. Press K to resume or Space to stop.",
      saving: "Saving and analysing your take…",
      review: "Listen back, then approve or record again.",
    };
    stateLine.textContent = lines[st] || "";
    stateLine.className = `state-line ${st === "recording" ? "rec" : ""}`;
  }

  function tick() {
    if (S.state !== "recording" && S.state !== "paused") return;
    timerEl.firstChild.textContent = fmt.timer(mic.elapsed);
    if (lastEp && lastEp.started && lastEp.progress > 0.25 && S.state === "recording") stopHint.textContent = `auto-stop ${Math.max(0, (1 - lastEp.progress) * S.ex.auto_stop_sec).toFixed(1)} s`;
    else stopHint.textContent = "";
    if (!S.nospeechShown && lastEp && !lastEp.started && mic.elapsed > 8 && !["silence", "clap"].includes(S.ex.kind)) {
      S.nospeechShown = true; toast("We can't hear speech yet — check the level meter moves when you talk.", "bad");
    }
    S.raf = requestAnimationFrame(tick);
  }

  // ------------------------------------------------------------------ record / stop
  async function toggleRecord() {
    if (S.state === "recording" || S.state === "paused") return stopAndSave("manual");
    if (!["ready", "review"].includes(S.state) || !S.ex) return;
    if (S.state === "review" && S.take) S.replaces = S.take.status === "pending" ? S.take.id : "";
    await mic.resumeContext();
    player.stop();
    const ex = S.ex;
    const autoStop = app.prefs.auto_stop !== false ? ex.auto_stop_sec || 0 : 0;
    const fixed = ex.kind === "silence" || ex.kind === "clap";
    mic.start({ prerollMs: fixed ? 0 : app.prefs.preroll_ms ?? 500, autoStopSec: fixed ? 0 : autoStop,
      maxSec: fixed ? (ex.fixed_sec || 5) + 2 : Math.min(600, ex.max_sec || (ex.kind === "prompt" ? 180 : 300)),
      fixedSec: fixed ? ex.fixed_sec || 5 : 0 });
    lastEp = null; S.nospeechShown = false;
    reviewCard.classList.add("hidden");
    setState("recording");
    cancelAnimationFrame(S.raf);
    S.raf = requestAnimationFrame(tick);
  }

  function togglePause() {
    if (S.state === "recording") { mic.pause(); setState("paused"); }
    else if (S.state === "paused") { mic.resume(); setState("recording"); cancelAnimationFrame(S.raf); S.raf = requestAnimationFrame(tick); }
  }

  async function stopAndSave(reason) {
    const rec = mic.stop();
    cancelAnimationFrame(S.raf);
    stopHint.textContent = "";
    if (!rec) return;
    timerEl.firstChild.textContent = fmt.timer(Math.max(0, rec.samples.length / rec.sampleRate - rec.prerollSec));
    if (rec.samples.length < rec.sampleRate * 0.3) { toast("That was too short to keep.", ""); setState("ready"); return; }
    setState("saving");
    S.local = rec;
    player.loadSamples(rec.samples, rec.sampleRate);
    const meta = {
      exercise_id: S.ex.id, session_id: S.session?.id || "", device_label: mic.label, device_id: mic.deviceId,
      user_agent: navigator.userAgent, context_sample_rate: rec.sampleRate, constraints_applied: mic.applied,
      preroll_sec: rec.prerollSec, auto_stopped: rec.autoStopped && reason !== "manual", paused_at: rec.pausedAt,
      track_events: rec.events, client_version: CLIENT_VERSION, replaces: S.replaces || "", channel_mode: rec.channelMode,
    };
    const blob = encodeWavFloat32(rec.samples, rec.sampleRate);
    renderReview(null);
    try {
      S.take = await upload(blob, meta);
      S.replaces = "";
      setState("review");
      renderReview(S.take);
      startPolling();
      loadSessionTakes();
      updatePendingBadge();
    } catch (e) {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
      const saved = await outbox.put({ id, blob, meta, created: new Date().toISOString() });
      setState("review");
      renderReview(null, saved ? "The server could not be reached, so this take is stored in your browser and will upload automatically." : `Upload failed: ${e.message}`);
      scheduleOutbox();
    }
  }

  async function upload(blob, meta) {
    const fd = new FormData();
    fd.append("audio", blob, "take.wav");
    fd.append("meta", JSON.stringify(meta));
    return api.post("/api/takes", fd);
  }

  let outboxTimer = null;
  function scheduleOutbox() { clearTimeout(outboxTimer); outboxTimer = setTimeout(flushOutbox, 8000); }
  async function flushOutbox() {
    const items = await outbox.all();
    for (const it of items) {
      try { await upload(it.blob, it.meta); await outbox.del(it.id); toast("A take saved in the browser has now been uploaded.", "ok"); }
      catch { scheduleOutbox(); return; }
    }
    if (items.length) { loadSessionTakes(); updatePendingBadge(); }
  }

  // ------------------------------------------------------------------ review
  function issueEl(i) {
    const ic = i.severity === "error" ? "alert" : i.severity === "warning" ? "warn" : "info";
    return h("div", { class: `issue ${i.severity}` }, icon(ic), h("div", {}, h("div", { class: "msg" }, i.message), i.hint ? h("div", { class: "hint" }, i.hint) : null));
  }

  function metric(k, v, unit) { return h("div", { class: "metric" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v, unit ? h("small", {}, " " + unit) : null)); }

  function renderReview(take, offlineMsg) {
    reviewCard.classList.remove("hidden");
    if (review) { review.destroy(); review = null; }
    reviewCard.replaceChildren();
    const canvas = h("canvas", {});
    const waveBox = h("div", { class: "review-wave", title: "Click to play from here" }, canvas);
    const an = take?.analysis || {};
    const duration = take ? take.audio.duration : S.local.samples.length / S.local.sampleRate;
    const markers = [...((an.clipping || {}).times || []).map((t) => ({ t, kind: "clip" })),
      ...(((an.dropouts || {}).items) || []).map((d) => ({ t: d.at, kind: "drop" })), ...(((an.clicks || {}).times) || []).map((t) => ({ t, kind: "click" }))];
    review = new StaticWave(canvas, { peaks: an.waveform || [], duration, segments: an.segments || [], markers, onSeek: (t) => { player.play(t); } });
    if (!an.waveform && S.local) review.setPeaksFromSamples(S.local.samples);
    player.onprogress = (t) => review && review.setPlayhead(t);
    const playBtn = h("button", { class: "btn" }, icon("play"), "Play", h("span", { class: "kbd" }, "P"));
    playBtn.addEventListener("click", (e) => { e.currentTarget.blur(); player.toggle(); });

    if (!take) {
      reviewCard.append(h("div", { class: "review-head" }, offlineMsg ? icon("warn") : h("span", { class: "spinner" }),
        h("div", {}, h("div", { class: "verdict" }, offlineMsg ? "Saved in your browser" : "Analysing…"), h("div", { class: "small muted" }, offlineMsg || "Measuring noise, level, clipping, silence and pitch."))), waveBox,
        h("div", { class: "review-actions" }, playBtn, offlineMsg ? h("button", { class: "btn", onClick: flushOutbox }, icon("refresh"), "Retry upload") : null,
          offlineMsg ? h("button", { class: "btn btn-primary", onClick: () => loadExercise() }, "Next exercise", icon("next")) : null));
      return;
    }
    const q = take.quality;
    const head = h("div", { class: "review-head" }, scoreRing(q.score, q.verdict),
      h("div", { style: { flex: 1, minWidth: "200px" } },
        h("div", { class: `verdict ${q.verdict}` }, q.verdict === "good" ? "Great take" : q.verdict === "usable" ? "Usable — your call" : "Re-record recommended"),
        h("div", { class: "small muted" }, `${q.summary}  ·  take ${take.attempt}  ·  ${fmt.dur(take.audio.duration)}`)));
    const issues = h("div", { class: "issues" }, (q.issues || []).filter((i) => i.severity !== "info" || i.penalty > 0 || i.code.startsWith("pace")).slice(0, 6).map(issueEl));
    const pitch = an.pitch || {};
    const rate = an.rate || {};
    const room = an.room || {};
    const metrics = take.kind === "clap"
      ? h("div", { class: "metrics" },
        metric("Room echo (T60)", room.t60 != null ? room.t60.toFixed(2) : "–", room.t60 != null ? "s" : ""),
        metric("Clap above noise", room.dynamic_range_db != null ? Math.round(room.dynamic_range_db) : "–", "dB"),
        metric("Room noise", fmt.db(an.noise_floor_dbfs), "dBFS"))
      : take.kind === "silence"
      ? h("div", { class: "metrics" },
        metric("Room noise", fmt.db(an.noise_floor_dbfs), "dBFS"),
        metric("Peak", fmt.db(an.peak_dbfs), "dBFS"),
        metric("Hum", an.hum?.detected ? `${an.hum.base_hz} Hz` : "none"),
        metric("Sound heard", (an.speech_seconds ?? 0).toFixed(1), "s"))
      : h("div", { class: "metrics" },
        metric("Speech", (an.speech_seconds ?? 0).toFixed(1), "s"),
        metric("SNR", an.snr_db != null ? Math.round(an.snr_db) : "–", "dB"),
        metric("Noise floor", fmt.db(an.noise_floor_dbfs), "dBFS"),
        metric("Speech level", fmt.db(an.speech_level_dbfs), "dBFS"),
        metric("Peak", fmt.db(an.peak_dbfs), "dBFS"),
        metric("Bandwidth", an.bandwidth?.effective_hz ? (an.bandwidth.effective_hz / 1000).toFixed(1) : "–", "kHz"),
        pitch.median_hz ? metric("Pitch", Math.round(pitch.median_hz), "Hz") : null,
        rate.articulation_rate ? metric("Rate", rate.articulation_rate.toFixed(1), "syll/s") : null);
    const asrLine = h("div", { class: "asr-line" });
    renderAsr(asrLine, take);
    const primaryIsRerecord = q.verdict === "rerecord";
    const approve = h("button", { class: `btn ${primaryIsRerecord ? "" : "btn-primary"}` }, icon("check"), primaryIsRerecord ? "Approve anyway" : "Approve & next", primaryIsRerecord ? null : h("span", { class: "kbd" }, "↵"));
    const redo = h("button", { class: `btn ${primaryIsRerecord ? "btn-primary" : ""}` }, icon("redo"), "Re-record", h("span", { class: "kbd" }, primaryIsRerecord ? "↵" : "R"));
    const reject = h("button", { class: "btn btn-ghost", title: "Reject (X): kept in the dataset as rejected" }, icon("x"), "Reject");
    approve.addEventListener("click", (e) => { e.currentTarget.blur(); approveTake(); });
    redo.addEventListener("click", (e) => { e.currentTarget.blur(); reRecord(); });
    reject.addEventListener("click", (e) => { e.currentTarget.blur(); rejectTake(); });
    reviewCard.append(head, waveBox, issues, metrics, asrLine, h("div", { class: "review-actions" }, playBtn, reject, redo, approve));
    if (take.kind === "prompt") reviewCard.insertBefore(transcriptBox(take), asrLine);
    const r = reviewCard.getBoundingClientRect();
    if (r.bottom > window.innerHeight) reviewCard.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function transcriptBox(take) {
    const ta = h("textarea", { placeholder: "The transcript appears here after speech recognition. Correct it so it matches exactly what you said." }, take.transcript || "");
    const save = h("button", { class: "btn btn-sm" }, "Save transcript");
    save.addEventListener("click", async () => {
      try { S.take = await api.patch(`/api/takes/${take.id}`, { transcript: ta.value }); toast("Transcript saved.", "ok"); } catch (e) { toast(e.message, "bad"); }
    });
    return h("div", { class: "stack", style: { marginTop: "12px" } }, h("div", { class: "small", style: { fontWeight: 650 } }, "Transcript (spontaneous speech)"), ta, h("div", { class: "row" }, save,
      h("span", { class: "tiny muted" }, "Training needs an exact transcript of spontaneous speech. Please check it.")));
  }

  function renderAsr(el, take) {
    el.replaceChildren();
    const a = take.asr || {};
    if (a.status === "pending" || a.status === "running") el.append(h("span", { class: "spinner" }), a.status === "running" ? (a.error || "Checking what you said…") : "Read-check queued…");
    else if (a.status === "done" && a.match && a.match.verdict !== "unchecked") {
      const m = a.match;
      el.append(icon(m.verdict === "read" ? "okc" : "warn"), `Read-check: ${Math.round(m.coverage * 100)}% of words recognised`,
        h("span", { class: "faint" }, `· Whisper ${a.model} · heard: “${(a.text || "").slice(0, 140)}${a.text && a.text.length > 140 ? "…" : ""}”`));
      el.querySelector("svg").style.color = m.verdict === "read" ? "var(--ok)" : "var(--warn)";
    } else if (a.status === "done") el.append(icon("okc"), "Transcribed", h("span", { class: "faint" }, ` · Whisper ${a.model}`));
    else if (a.status === "unavailable") el.append(icon("info"), "Read-check unavailable: ", h("span", { class: "faint" }, a.error || "install faster-whisper to compare what you said with the text"));
    else if (a.status === "error") el.append(icon("warn"), "Read-check failed: ", h("span", { class: "faint" }, a.error));
    el.querySelectorAll("svg").forEach((s) => { s.style.width = "15px"; s.style.height = "15px"; });
  }

  function startPolling() {
    stopPolling();
    const id = S.take?.id;
    if (!id) return;
    let n = 0;
    S.poll = setInterval(async () => {
      if (S.disposed || !S.take || S.take.id !== id) return stopPolling();
      if (++n > 600) return stopPolling(); // first use may include a large model download
      const st = S.take.asr?.status;
      if (!["pending", "running"].includes(st)) return stopPolling();
      try {
        const t = await api.get(`/api/takes/${id}`);
        const changed = t.asr.status !== st;
        S.take = t;
        if (changed && S.state === "review") {
          renderReview(t);
          renderPrompt(lastMissing());
          if (t.quality.verdict === "rerecord" && t.asr.match && t.asr.match.verdict !== "read") toast("The read-check found missing words — see the highlighted text.", "bad");
        }
      } catch {}
    }, 1200);
  }
  function stopPolling() { clearInterval(S.poll); S.poll = null; }

  async function approveTake() {
    if (S.state !== "review") return;
    if (!S.take) { await loadExercise(); return; }
    try {
      S.take = await api.patch(`/api/takes/${S.take.id}`, { status: "approved" });
      toast("Approved and added to your dataset.", "ok", 1800);
      updatePendingBadge();
      loadSessionTakes();
      loadCoverage();
      if (app.prefs.auto_advance !== false) await loadExercise();
      else { renderReview(S.take); }
    } catch (e) {
      toast(e.message, "bad");
    }
  }

  async function rejectTake() {
    if (S.state !== "review" || !S.take) return;
    try {
      await api.patch(`/api/takes/${S.take.id}`, { status: "rejected", reason: "rejected in studio" });
      toast("Rejected. The recording is kept (restorable in the Dataset Manager).", "", 3000);
      S.take = null; S.replaces = "";
      reviewCard.classList.add("hidden");
      setState("ready");
      loadSessionTakes(); updatePendingBadge();
      renderPrompt();
    } catch (e) { toast(e.message, "bad"); }
  }

  function reRecord() {
    if (S.state !== "review") return;
    S.replaces = S.take && S.take.status === "pending" ? S.take.id : "";
    player.stop();
    reviewCard.classList.add("hidden");
    setState("ready");
    renderPrompt();
  }

  async function skip() {
    if (["recording", "paused", "saving"].includes(S.state)) return;
    if (S.session && S.ex) api.patch(`/api/sessions/${S.session.id}`, { skip: S.ex.id }).catch(() => {});
    if (S.take && S.take.status === "pending") toast("The take stays in the Dataset Manager, waiting for review.", "", 2500);
    await loadExercise();
  }

  async function goBack() {
    if (S.history.length < 2 || ["recording", "paused", "saving"].includes(S.state)) return;
    S.history.pop();
    await loadExercise(S.history[S.history.length - 1], { pushHistory: false });
  }

  // ------------------------------------------------------------------ side panel + top bar
  function renderSide() {
    const ts = S.sessionTakes || [];
    const approved = ts.filter((t) => t.status === "approved");
    const secs = ts.reduce((n, t) => n + t.audio.duration, 0);
    const scores = ts.map((t) => t.quality.score);
    const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
    const sess = S.session;
    const cov = S.coverage;
    const micInfo = mic.isOpen ? [
      ["Device", mic.label || "–"], ["Sample rate", `${mic.sampleRate} Hz`],
      ["Voice processing", ["echoCancellation", "noiseSuppression", "autoGainControl"].some((k) => mic.applied?.[k] === true) ? "on (!)" : "off ✓"],
      ["Room noise", sess && sess.noise_floor_db != null ? `${Math.round(sess.noise_floor_db)} dBFS` : "measure in warm-up"],
    ] : [["Status", "not connected"]];
    const showModule = cov && S.ex && !["S", "J"].includes(S.ex.module) && S.ex.source !== "generated";
    const modRow = showModule ? cov.modules.find((m) => m.id === S.ex.module) : null;
    side.replaceChildren(
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "This session")),
        h("div", { class: "kv" },
          h("span", { class: "k" }, "Takes"), h("span", { class: "v" }, ts.length),
          h("span", { class: "k" }, "Approved"), h("span", { class: "v" }, approved.length),
          h("span", { class: "k" }, "Recorded"), h("span", { class: "v" }, fmt.dur(secs)),
          h("span", { class: "k" }, "Average score"), h("span", { class: "v" }, avg ?? "–"))),
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Microphone"), mic.isOpen ? deviceSelect() : null),
        h("div", { class: "kv" }, micInfo.flatMap(([k, v]) => [h("span", { class: "k" }, k), h("span", { class: "v", style: { maxWidth: "170px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, title: v }, v)]))),
      cov ? h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Dataset"), h("a", { href: "#/dashboard", class: "small" }, "Dashboard →")),
        h("div", { class: "row spread small" }, h("span", { class: "muted" }, "Completeness"), h("b", { class: "num" }, `${Math.round(cov.completeness)}%`)),
        h("div", { class: "progress", style: { margin: "6px 0 12px" } }, h("i", { style: { width: `${cov.completeness}%` } })),
        h("div", { class: "small muted" }, "Next milestone: ", h("b", { style: { color: "var(--text)" } }, cov.stage)),
        modRow ? h("div", { style: { marginTop: "12px" } }, h("div", { class: "row spread small" }, h("span", { class: "muted" }, `Module ${modRow.id} core`), h("span", { class: "num" }, `${modRow.core_approved}/${modRow.core}`)),
          h("div", { class: "progress thin", style: { marginTop: "6px" } }, h("i", { style: { width: `${modRow.core ? (100 * modRow.core_approved) / modRow.core : 0}%` } }))) : null) : null,
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", {}, "Tips")),
        h("div", { class: "small muted stack", style: { gap: "6px" } },
          h("div", {}, "Keep the same mic, distance and room for every session."),
          h("div", {}, "Stay natural. Different deliveries are welcome; your identity should stay the same."),
          h("div", {}, "Take a break every 20–30 minutes and sip water; a tired voice changes the dataset."),
          h("div", { class: "hint-keys" }, "Press ", h("span", { class: "kbd" }, "?"), " for keyboard shortcuts."))));
  }

  function deviceSelect() {
    const sel = h("select", { style: { width: "auto", maxWidth: "150px", minHeight: "30px", height: "30px", padding: "3px 8px", fontSize: "12px" }, title: "Input device" });
    MicRecorder.devices().then((ds) => {
      ds.forEach((d) => sel.append(h("option", { value: d.deviceId, selected: d.deviceId === mic.deviceId }, d.label || "Microphone")));
    });
    sel.addEventListener("change", async () => {
      if (["recording", "paused", "saving"].includes(S.state)) return;
      localStorage.setItem(DEVICE_KEY, sel.value);
      toast("Switching microphone… keep the same mic for a whole session if you can.", "", 2500);
      mic.removeEventListener("chunk", onChunk);
      await openMic(sel.value);
    });
    return sel;
  }

  function renderTop() {
    const modes = [["adaptive", "Adaptive (recommended)"], ...Object.entries(app.vocab.modules || {}).filter(([k]) => k !== "S").map(([k, m]) => [`module:${k}`, `Module ${k} · ${m.title}`])];
    const sel = h("select", { style: { width: "auto", minWidth: "220px" }, title: "What to record" }, modes.map(([v, l]) => h("option", { value: v, selected: v === S.mode }, l)));
    sel.addEventListener("change", async () => { S.mode = sel.value; sessionStorage.setItem("myvoice-mode", S.mode); if (!["recording", "paused", "saving"].includes(S.state)) await loadExercise(); });
    const brk = h("button", { class: "btn btn-sm", title: "Take a break" }, icon("coffee"), "Break");
    brk.addEventListener("click", takeBreak);
    const end = h("button", { class: "btn btn-sm btn-ghost" }, "End session");
    end.addEventListener("click", endSession);
    const started = S.session ? fmt.date(S.session.started_at) : "";
    top.replaceChildren(h("span", { class: "session-pill" }, h("span", { class: `dot ${S.session ? "ok" : ""}` }), S.session ? `Session started ${started}` : "No session"),
      sel, h("span", { style: { flex: 1 } }), brk, end);
  }

  function takeBreak() {
    if (["recording", "paused", "saving"].includes(S.state)) return;
    S.breakAt = Date.now();
    const t = h("div", { class: "t" }, "00:00");
    const iv = setInterval(() => { t.textContent = fmt.dur((Date.now() - S.breakAt) / 1000); }, 500);
    const back = h("div", { class: "break-screen" }, h("div", {}, h("div", { style: { fontSize: "46px" } }, "☕"), h("h2", {}, "Break time"),
      h("p", { class: "muted" }, "Rest your voice, drink some water. Your session is paused."), t,
      h("button", { class: "btn btn-primary btn-lg", onClick: () => {
        clearInterval(iv); back.remove();
        const secs = (Date.now() - S.breakAt) / 1000;
        if (S.session) api.patch(`/api/sessions/${S.session.id}`, { paused_seconds: secs }).catch(() => {});
      } }, "Resume recording")));
    document.body.append(back);
  }

  async function endSession() {
    if (["recording", "paused", "saving"].includes(S.state)) return;
    if (!S.session) return;
    await loadSessionTakes();
    const ts = S.sessionTakes;
    const appr = ts.filter((t) => t.status === "approved").length;
    const pend = ts.filter((t) => t.status === "pending").length;
    modal({
      title: "End this session?",
      body: h("div", { class: "stack" }, h("p", {}, `${ts.length} takes recorded (${fmt.dur(ts.reduce((n, t) => n + t.audio.duration, 0))}), ${appr} approved${pend ? `, ${pend} still waiting for review` : ""}.`),
        h("p", { class: "muted small" }, "Ending a session closes it for consistency tracking. Your next visit starts a new session with a short warm-up.")),
      actions: [{ label: "Keep recording", cls: "btn-ghost" }, { label: "End session", cls: "btn-primary", onClick: async () => {
        await api.patch(`/api/sessions/${S.session.id}`, { end: true });
        await mic.close();
        app.go(pend ? "#/dataset" : "#/dashboard");
      } }],
    });
  }

  // ------------------------------------------------------------------ boot
  renderTop();
  renderSide();
  const perm = await MicRecorder.permissionState();
  if (perm === "granted" && MicRecorder.supported()) await openMic();
  else setState("nomic");
  await loadExercise(params[0] ? decodeURIComponent(params[0]) : undefined);
  loadSessionTakes();
  loadCoverage();
  flushOutbox();
  welcome();

  return {
    refreshExercise: () => S.ex && loadExercise(S.ex.id, { pushHistory: false }),
    onKey(e) {
      const k = e.key;
      if (k === " " || k === "Spacebar") { e.preventDefault(); toggleRecord(); }
      else if (k === "Enter") { e.preventDefault(); if (S.state === "review") (S.take && S.take.quality.verdict === "rerecord" ? reRecord() : approveTake()); }
      else if (k === "Escape") { if (S.state === "recording" || S.state === "paused") stopAndSave("manual"); }
      else if (k === "r" || k === "R") reRecord();
      else if (k === "p" || k === "P") { if (S.state === "review") player.toggle(); }
      else if (k === "k" || k === "K") togglePause();
      else if (k === "n" || k === "N") skip();
      else if (k === "b" || k === "B") goBack();
      else if (k === "x" || k === "X") rejectTake();
      else if (k === "t" || k === "T") { if (S.ex && S.ex.roman) toggleRoman(); }
      else if (k === "+" || k === "=") scale(0.1);
      else if (k === "-" || k === "_") scale(-0.1);
    },
    async unmount() {
      S.disposed = true;
      stopPolling();
      clearTimeout(outboxTimer);
      cancelAnimationFrame(S.raf);
      if (mic.recording) await stopAndSave("navigate");
      player.stop();
      if (live) live.destroy();
      if (review) review.destroy();
      await mic.close();
    },
  };
}
