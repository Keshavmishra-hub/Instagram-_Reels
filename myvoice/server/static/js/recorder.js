// Microphone capture for voice-cloning data.
//  * Web Audio + AudioWorklet: raw PCM at the device rate (never MediaRecorder, which is lossy Opus/AAC).
//  * Browser voice processing (echo cancellation, noise suppression, auto gain) is switched off;
//    what the browser actually applied is reported so the studio can warn about it.
//  * A 1 s ring buffer keeps audio from just before RECORD was pressed (pre-roll), so the first
//    syllable is never clipped and the analysis has a room-noise reference.
//  * End-of-speech detection drives auto-stop (adaptive noise floor with hysteresis).

export const CLIENT_VERSION = "myvoice-web-1.0";

export class Endpointer {
  constructor(sampleRate) { this.sr = sampleRate; this.reset(-60, 1.8); }
  reset(floorDb, silenceSec) {
    this.floor = Math.min(-30, floorDb ?? -60);
    this.silenceSec = silenceSec;
    this.speechRun = 0; this.silenceRun = 0; this.started = false; this.elapsed = 0; this.speechTotal = 0;
  }
  feed(rms, n) {
    const db = 20 * Math.log10(Math.max(rms, 1e-6));
    const dt = n / this.sr;
    this.elapsed += dt;
    const loud = db > Math.max(this.floor + 12, -62);
    const quiet = db < this.floor + 7;
    if (loud) {
      this.speechRun += dt; this.silenceRun = 0; this.speechTotal += dt;
      if (this.speechRun >= 0.15) this.started = true;
    } else {
      this.speechRun = Math.max(0, this.speechRun - dt);
      if (quiet && this.started) this.silenceRun += dt;
    }
    if (db < this.floor) this.floor = db;
    else if (!loud) this.floor += Math.min(db - this.floor, 1.5 * dt); // floor rises slowly, falls at once
    return {
      db, floor: this.floor, started: this.started, silenceRun: this.silenceRun,
      progress: this.silenceSec > 0 ? Math.min(1, this.silenceRun / this.silenceSec) : 0,
      shouldStop: this.started && this.silenceSec > 0 && this.silenceRun >= this.silenceSec,
    };
  }
}

export class MicRecorder extends EventTarget {
  constructor() {
    super();
    this.ctx = null; this.stream = null; this.track = null; this.node = null;
    this.ring = []; this.ringLen = 0;
    this.recording = false; this.paused = false;
    this.chunks = []; this.recorded = 0;
    this.events = []; this.pausedAt = [];
    this.autoStopSec = 0; this.maxSec = 600; this.fixedSec = 0;
    this.autoStopped = false;
    this.ep = null;
    this.channelMode = "mono";
  }

  static supported() {
    return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.AudioWorkletNode);
  }

  static async permissionState() {
    try {
      const p = await navigator.permissions.query({ name: "microphone" });
      return p.state; // granted | denied | prompt
    } catch { return "unknown"; } // Firefox/Safari may not support querying the microphone permission
  }

  static async devices() {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      return all.filter((d) => d.kind === "audioinput");
    } catch { return []; }
  }

  get isOpen() { return !!this.ctx; }

  async open(deviceId) {
    await this.close();
    const audio = {
      channelCount: { ideal: 1 },
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      sampleRate: { ideal: 48000 },
    };
    if (deviceId) audio.deviceId = { exact: deviceId };
    // Chrome-specific legacy flags (ignored elsewhere): make sure no processing slips in
    Object.assign(audio, { googEchoCancellation: false, googAutoGainControl: false, googNoiseSuppression: false, googHighpassFilter: false });
    this.stream = await navigator.mediaDevices.getUserMedia({ audio, video: false });
    this.track = this.stream.getAudioTracks()[0];
    for (const type of ["mute", "unmute", "ended"]) {
      this.track.addEventListener(type, () => {
        const ev = { type, t: this.recording ? +(this.recorded / this.sampleRate).toFixed(2) : -1 };
        if (this.recording) this.events.push(ev);
        this.dispatchEvent(new CustomEvent("trackevent", { detail: ev }));
      });
    }
    this.ctx = new AudioContext({ latencyHint: "interactive" });
    this.sampleRate = this.ctx.sampleRate;
    await this.ctx.audioWorklet.addModule("/static/js/capture-worklet.js");
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "myvoice-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
    this.node.port.onmessage = (e) => this._onMessage(e.data);
    const silent = this.ctx.createGain();
    silent.gain.value = 0; // the graph must reach the destination to run; nothing is played back
    src.connect(this.node);
    this.node.connect(silent).connect(this.ctx.destination);
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.ctx.addEventListener("statechange", () => {
      if (this.ctx && this.ctx.state !== "running" && this.recording) this.events.push({ type: "context-" + this.ctx.state, t: +(this.recorded / this.sampleRate).toFixed(2) });
      this.dispatchEvent(new CustomEvent("contextstate", { detail: this.ctx ? this.ctx.state : "closed" }));
    });
    this.ep = new Endpointer(this.sampleRate);
    const s = this.track.getSettings ? this.track.getSettings() : {};
    this.applied = {
      echoCancellation: s.echoCancellation, noiseSuppression: s.noiseSuppression, autoGainControl: s.autoGainControl,
      sampleRate: s.sampleRate || this.sampleRate, channelCount: s.channelCount, deviceId: s.deviceId || "",
    };
    this.label = this.track.label || "Microphone";
    this.deviceId = s.deviceId || deviceId || "";
    return { label: this.label, sampleRate: this.sampleRate, applied: this.applied };
  }

  async close() {
    this.recording = false;
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx) { try { await this.ctx.close(); } catch {} }
    this.ctx = null; this.stream = null; this.track = null; this.node = null;
    this.ring = []; this.ringLen = 0;
  }

  async resumeContext() { if (this.ctx && this.ctx.state === "suspended") await this.ctx.resume(); }

  _onMessage(msg) {
    if (msg.type === "mode") { this.channelMode = msg.mode; return; }
    if (msg.type !== "chunk") return;
    const { samples, peak, rms } = msg;
    let ep = null;
    if (this.recording && !this.paused) {
      this.chunks.push(samples);
      this.recorded += samples.length;
      ep = this.ep.feed(rms, samples.length);
    } else if (!this.recording) {
      this.ring.push(samples);
      this.ringLen += samples.length;
      while (this.ringLen - this.ring[0].length > this.sampleRate) { this.ringLen -= this.ring[0].length; this.ring.shift(); }
    }
    this.dispatchEvent(new CustomEvent("chunk", { detail: { samples, peak, rms, recording: this.recording && !this.paused, ep } }));
    if (this.recording && !this.paused) {
      const sec = this.recorded / this.sampleRate;
      if (this.fixedSec && sec >= this.fixedSec + this.prerollSec) this._auto("fixed");
      else if (ep && ep.shouldStop) this._auto("silence");
      else if (sec >= this.maxSec) this._auto("max");
    }
  }

  _auto(reason) {
    if (!this.recording) return;
    this.autoStopped = reason !== "manual";
    this.dispatchEvent(new CustomEvent("autostop", { detail: { reason } }));
  }

  _ringFloorDb() {
    if (!this.ring.length) return -60;
    const dbs = this.ring.map((c) => { let s = 0; for (let i = 0; i < c.length; i++) s += c[i] * c[i]; return 10 * Math.log10(s / c.length + 1e-12); });
    dbs.sort((a, b) => a - b);
    return dbs[Math.floor(dbs.length / 2)];
  }

  start({ prerollMs = 500, autoStopSec = 0, maxSec = 600, fixedSec = 0 } = {}) {
    if (!this.ctx) throw new Error("microphone not open");
    const want = Math.round((prerollMs / 1000) * this.sampleRate);
    const all = this.ring.slice();
    let take = [], got = 0;
    for (let i = all.length - 1; i >= 0 && got < want; i--) {
      const c = all[i];
      const need = want - got;
      take.unshift(c.length <= need ? c : c.subarray(c.length - need));
      got += Math.min(c.length, need);
    }
    this.chunks = take; this.recorded = got;
    this.prerollSec = got / this.sampleRate;
    this.events = []; this.pausedAt = []; this.autoStopped = false;
    this.autoStopSec = autoStopSec; this.maxSec = maxSec; this.fixedSec = fixedSec;
    this.ep.reset(this._ringFloorDb(), autoStopSec);
    this.recording = true; this.paused = false;
    this.startedAt = performance.now();
  }

  pause() {
    if (!this.recording || this.paused) return;
    this.paused = true;
    this.pausedAt.push(+(this.recorded / this.sampleRate).toFixed(3));
  }

  resume() { if (this.recording && this.paused) this.paused = false; }

  get elapsed() { return this.sampleRate ? Math.max(0, this.recorded / this.sampleRate - (this.prerollSec || 0)) : 0; }

  stop() {
    if (!this.recording) return null;
    this.recording = false; this.paused = false;
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const out = new Float32Array(total);
    let o = 0;
    for (const c of this.chunks) { out.set(c, o); o += c.length; }
    this.chunks = [];
    this.ring = []; this.ringLen = 0;
    return {
      samples: out, sampleRate: this.sampleRate, prerollSec: this.prerollSec, pausedAt: this.pausedAt.slice(),
      events: this.events.slice(), autoStopped: this.autoStopped, channelMode: this.channelMode,
    };
  }
}

// 32-bit float WAV (lossless copy of the captured samples)
export function encodeWavFloat32(samples, sampleRate) {
  // 56-byte header (RIFF + 16-byte fmt + fact + data) keeps the sample data 4-byte aligned
  const n = samples.length;
  const buf = new ArrayBuffer(56 + n * 4);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 48 + n * 4, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 3, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 32, true);
  str(36, "fact"); v.setUint32(40, 4, true); v.setUint32(44, n, true);
  str(48, "data"); v.setUint32(52, n * 4, true);
  new Float32Array(buf, 56, n).set(samples);
  return new Blob([buf], { type: "audio/wav" });
}
