import { api } from "../api.js";
import { fmt, h, icon, toast } from "../util.js";

const ASR_MODELS = [
  ["large-v3-turbo", "large-v3-turbo · best for Hindi/Hinglish · ~1.6 GB download, ~2 GB RAM"],
  ["large-v3", "large-v3 · most accurate, slower · ~3 GB"],
  ["medium", "medium · good English, fair Hindi · ~1.5 GB"],
  ["small", "small · fast · weak on Hindi · ~0.5 GB"],
  ["base", "base · very fast · English only in practice"],
];

export async function mount(root, _params, app) {
  await app.refresh();
  const p = app.profile, prefs = app.prefs, caps = app.caps;
  let backends = { profiles: {} };
  try { backends = await api.get("/api/exports"); } catch {}

  const save = async (patch, msg = "Saved.") => { try { await app.saveProfile(patch); toast(msg, "ok", 1600); } catch (e) { toast(e.message, "bad"); } };
  const savePref = async (patch) => { try { await app.savePrefs(patch); toast("Saved.", "ok", 1200); } catch (e) { toast(e.message, "bad"); } };
  const sw = (label, checked, onChange, hint) => {
    const inp = h("input", { type: "checkbox", checked });
    inp.addEventListener("change", () => onChange(inp.checked));
    return h("div", {}, h("label", { class: "switch" }, inp, h("span", { style: { fontWeight: 600 } }, label)), hint ? h("div", { class: "tiny muted", style: { margin: "4px 0 0 48px" } }, hint) : null);
  };
  const range = (label, value, min, max, step, unit, onChange, hint) => {
    const out = h("b", { class: "num" }, `${value}${unit}`);
    const inp = h("input", { type: "range", min, max, step, value });
    inp.addEventListener("input", () => { out.textContent = `${inp.value}${unit}`; });
    inp.addEventListener("change", () => onChange(+inp.value));
    return h("div", { class: "stack", style: { gap: "4px" } }, h("div", { class: "row spread small" }, h("span", { style: { fontWeight: 600 } }, label), out), inp, hint ? h("div", { class: "tiny muted" }, hint) : null);
  };

  // profile
  const name = h("input", { type: "text", value: p.speaker_name, maxlength: "80", placeholder: "Your name" });
  name.addEventListener("change", () => save({ speaker_name: name.value.trim() }));
  const forms = h("div", { class: "seg" }, [["m", "मैं जा रहा हूँ"], ["f", "मैं जा रही हूँ"]].map(([v, l]) => {
    const b = h("button", { type: "button", class: p.hindi_forms === v ? "on" : "" }, l);
    b.addEventListener("click", () => { forms.querySelectorAll("button").forEach((x) => x.classList.remove("on")); b.classList.add("on"); save({ hindi_forms: v }); });
    return b;
  }));
  const consent = sw("I confirm that the voice in this dataset is my own and that I am recording it by choice.", p.consent_given, (v) => save({ consent_given: v }),
    p.consent_at ? `Confirmed ${fmt.date(p.consent_at)}. Your recorded consent statement is part of the setup module.` : "Commercial cloning services require proof that you own the voice; keep your recorded statement with the dataset.");

  // ASR
  const asr = caps.asr || {};
  const model = h("select", {}, ASR_MODELS.map(([v, l]) => h("option", { value: v, selected: v === asr.model }, l)));
  model.addEventListener("change", () => save({ asr_model: model.value }, "Model saved. It downloads on the next read-check."));

  // backend
  const targets = [["undecided", "Undecided — keep collecting broadly"], ...Object.entries(backends.profiles || {}).filter(([k]) => k !== "master").map(([k, v]) => [k, v.title])];
  const target = h("select", {}, targets.map(([v, l]) => h("option", { value: v, selected: v === p.clone_backend }, l)));
  const targetNote = h("p", { class: "small muted", style: { marginTop: "8px" } });
  const updTarget = () => { const pr = backends.profiles?.[target.value]; targetNote.textContent = pr ? `${pr.summary} ${pr.note || ""}` : "The dashboard milestones cover both zero-shot (reference clips) and fine-tuning (30 min → 2 h) strategies."; };
  target.addEventListener("change", () => { updTarget(); save({ clone_backend: target.value }); });
  updTarget();

  const theme = h("div", { class: "seg" }, [["system", "System"], ["dark", "Dark"], ["light", "Light"]].map(([v, l]) => {
    const b = h("button", { type: "button", class: (prefs.theme || "system") === v ? "on" : "" }, l);
    b.addEventListener("click", () => { theme.querySelectorAll("button").forEach((x) => x.classList.remove("on")); b.classList.add("on"); savePref({ theme: v }); });
    return b;
  }));

  const comp = (ok, label, fix) => h("div", { class: "row", style: { gap: "8px" } }, h("span", { class: `dot ${ok ? "ok" : "warn"}` }), h("span", {}, label), !ok && fix ? h("span", { class: "small muted mono" }, fix) : null);

  root.append(
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Settings"), h("p", {}, "Your profile, recording behaviour, speech recognition, cloning target, storage and privacy."))),
    h("div", { class: "grid g2" },
      h("div", { class: "card stack" }, h("h3", {}, icon("user"), " Profile & consent"),
        h("label", { class: "field" }, "Name (appears in your consent statement)", name),
        h("div", { class: "field" }, h("span", { class: "small", style: { fontWeight: 600, color: "var(--text-2)" } }, "Hindi first-person verb forms"), forms),
        consent),
      h("div", { class: "card stack" }, h("h3", {}, icon("mic"), " Recording"),
        sw("Stop automatically when I finish speaking", prefs.auto_stop !== false, (v) => savePref({ auto_stop: v })),
        range("Silence before auto-stop (sentences)", prefs.auto_stop_sec ?? 1.8, 1, 4, 0.1, " s", (v) => savePref({ auto_stop_sec: v }), "Paragraphs wait ~1.6×, spontaneous speech ~2.8× longer."),
        range("Pre-roll kept before RECORD", prefs.preroll_ms ?? 500, 0, 1000, 50, " ms", (v) => savePref({ preroll_ms: v }), "Protects the first syllable and gives the analysis a room-noise sample."),
        sw("Move to the next exercise after approving", prefs.auto_advance !== false, (v) => savePref({ auto_advance: v })),
        sw("Warm-up at the start of each session", prefs.warmup !== false, (v) => savePref({ warmup: v }), "Room tone, an echo check (one clap), mic check and two consistency anchors."),
        sw("Show Roman transliteration under Hindi", prefs.show_roman !== false, (v) => savePref({ show_roman: v })),
        range("Reading text size", prefs.text_scale ?? 1, 0.7, 1.8, 0.05, "×", (v) => savePref({ text_scale: v })),
        h("div", { class: "field" }, h("span", { class: "small", style: { fontWeight: 600, color: "var(--text-2)" } }, "Theme"), theme))),
    h("div", { class: "grid g2", style: { marginTop: "14px" } },
      h("div", { class: "card stack" }, h("h3", {}, icon("text"), " Read-check (speech recognition)"),
        asr.installed ? h("p", { class: "small muted" }, `Whisper runs on this computer via faster-whisper (${asr.state}${asr.error ? ": " + asr.error : ""}). It compares what you said with the displayed text and transcribes spontaneous speech. Nothing is uploaded.`)
          : h("div", { class: "notice warn" }, icon("warn"), h("div", {}, h("b", {}, "Not installed. "), "Takes are still saved and scored on their audio. To enable the read-check: ", h("span", { class: "mono" }, asr.install_hint || "pip install faster-whisper"))),
        h("label", { class: "field" }, "Whisper model", model),
        h("p", { class: "tiny muted" }, "Recognition quality is the limit of the read-check: Hindi and Hinglish are recognised less accurately than English, so the studio is more forgiving there and never fails a take on recognition alone when the recogniser is unsure.")),
      h("div", { class: "card stack" }, h("h3", {}, icon("target"), " Cloning target"),
        h("label", { class: "field" }, "Planned voice-cloning approach", target), targetNote,
        h("p", { class: "tiny muted" }, "This only sets the default export format. Do a blind listening test with your own reference clips before committing to a service; see docs/MYVOICE.md for the comparison."))),
    h("div", { class: "grid g2", style: { marginTop: "14px" } },
      h("div", { class: "card stack" }, h("h3", {}, icon("shield"), " Storage & privacy"),
        h("div", { class: "small" }, "Data folder: ", h("span", { class: "mono" }, caps.data_dir)),
        h("ul", { class: "small muted", style: { margin: 0, paddingLeft: "18px", lineHeight: 1.8 } },
          h("li", {}, "Recordings are stored only in this folder as lossless 24-bit WAV + a JSON sidecar each; the folder is owner-only (chmod 700)."),
          h("li", {}, "No cloud service is contacted. The Whisper model is downloaded once from Hugging Face; after that everything runs offline."),
          h("li", {}, "Back up by copying the whole folder. Deleted takes go to the trash first; only “Empty trash” removes files."),
          h("li", {}, "The server listens on 127.0.0.1 only. Network mode (--lan) adds HTTPS and a random access token."))),
      h("div", { class: "card stack" }, h("h3", {}, icon("info"), " Microphone & browser notes"),
        h("ul", { class: "small muted", style: { margin: 0, paddingLeft: "18px", lineHeight: 1.8 } },
          h("li", {}, "Microphone access only works on secure pages: http://127.0.0.1 / localhost on this computer, or HTTPS (use python -m myvoice serve --lan for a phone)."),
          h("li", {}, "Best: Chrome or Edge on a computer. Firefox works. Safari on iPhone/iPad may ignore the request to switch off voice processing — the studio detects and flags it."),
          h("li", {}, "Bluetooth headsets drop to telephone quality when their mic is in use. The studio detects narrow-band audio and warns you."),
          h("li", {}, "Keep the tab in front while recording; phones stop the microphone when the screen locks."),
          h("li", {}, "If you denied permission, re-allow it from the padlock icon in the address bar, then reload.")))),
    h("div", { class: "card", style: { marginTop: "14px" } }, h("h3", { style: { marginBottom: "10px" } }, "Components"),
      h("div", { class: "grid g3" },
        comp(caps.praat, "Praat pitch & voice analysis (parselmouth)", "pip install praat-parselmouth"),
        comp(caps.webrtcvad, "WebRTC voice activity detector", "pip install webrtcvad-wheels"),
        comp(caps.espeak?.available, "eSpeak NG English phonemes", "pip install espeakng-loader"),
        comp(asr.installed, "faster-whisper read-check", "pip install faster-whisper"),
        comp(caps.ffmpeg, "FFmpeg (MP3 export)", "install ffmpeg"),
        h("div", { class: "small muted" }, `MY VOICE v${caps.version}`))));
}
