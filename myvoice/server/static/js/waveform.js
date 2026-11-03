// Live waveform, level meter, review waveform and a Web Audio player.

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function fit(canvas) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr)), hh = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== hh) { canvas.width = w; canvas.height = hh; }
  return { w, h: hh, dpr };
}

export class LiveWave {
  constructor(canvas, windowSec = 6, colsPerSec = 60) {
    this.c = canvas; this.ctx = canvas.getContext("2d");
    this.n = Math.round(windowSec * colsPerSec); this.colsPerSec = colsPerSec;
    this.cols = new Float32Array(this.n * 2); this.flag = new Uint8Array(this.n); this.head = 0;
    this.acc = 0; this.accMin = 1; this.accMax = -1; this.accRec = 0; this.sr = 48000;
    this.raf = null; this.dirty = true; this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }
  setRate(sr) { this.sr = sr; }
  clear() { this.cols.fill(0); this.flag.fill(0); this.dirty = true; }
  push(samples, recording) {
    const per = Math.max(1, Math.round(this.sr / this.colsPerSec));
    for (let i = 0; i < samples.length; i++) {
      const v = samples[i];
      if (v < this.accMin) this.accMin = v;
      if (v > this.accMax) this.accMax = v;
      if (++this.acc >= per) {
        const k = this.head;
        this.cols[2 * k] = this.accMin; this.cols[2 * k + 1] = this.accMax;
        const pk = Math.max(-this.accMin, this.accMax);
        this.flag[k] = (recording ? 1 : 0) | (pk >= 0.89 ? 2 : 0) | (pk >= 0.99 ? 4 : 0);
        this.head = (this.head + 1) % this.n;
        this.acc = 0; this.accMin = 1; this.accMax = -1;
      }
    }
    this.dirty = true;
  }
  loop() {
    this.raf = requestAnimationFrame(this.loop);
    if (!this.dirty || !this.c.isConnected) return;
    this.dirty = false;
    const { w, h } = fit(this.c);
    const g = this.ctx;
    g.clearRect(0, 0, w, h);
    const mid = h / 2;
    g.fillStyle = css("--line");
    g.fillRect(0, Math.round(mid), w, 1);
    const colW = w / this.n;
    const live = css("--wave"), dim = css("--wave-dim"), warn = css("--warn"), bad = css("--rec");
    for (let i = 0; i < this.n; i++) {
      const k = (this.head + i) % this.n;
      const mn = this.cols[2 * k], mx = this.cols[2 * k + 1];
      if (mn === 0 && mx === 0) continue;
      const f = this.flag[k];
      g.fillStyle = f & 4 ? bad : f & 2 ? warn : f & 1 ? live : dim;
      const y0 = mid - mx * mid * 0.95, y1 = mid - mn * mid * 0.95;
      g.fillRect(i * colW, y0, Math.max(1, colW - 0.6), Math.max(1, y1 - y0));
    }
  }
  destroy() { cancelAnimationFrame(this.raf); }
}

export class LevelMeter {
  constructor(root) {
    this.root = root;
    root.innerHTML = `<div class="level-bar"><div class="zone" style="left:70%;width:25%"></div><div class="fill"></div><div class="peak"></div></div>
      <div class="level-legend"><span>-60</span><span>-18</span><span>-6</span><span>0 dB</span></div>
      <div class="row spread"><span class="small muted" data-lvl>–</span><span class="clip-led" data-clip><span class="dot"></span>CLIP</span></div>`;
    this.fill = root.querySelector(".fill"); this.peakEl = root.querySelector(".peak");
    this.lbl = root.querySelector("[data-lvl]"); this.clip = root.querySelector("[data-clip]");
    this.hold = -90; this.holdT = 0; this.clipT = -Infinity; this.smooth = -90;
  }
  pos(db) { return Math.max(0, Math.min(100, ((db + 60) / 60) * 100)); }
  update(peak) {
    const db = 20 * Math.log10(Math.max(peak, 1e-6));
    const now = performance.now();
    this.smooth = db > this.smooth ? db : this.smooth - 1.2;
    if (db > this.hold || now - this.holdT > 1200) { this.hold = db; this.holdT = now; }
    if (peak >= 0.99) this.clipT = now;
    this.fill.style.width = this.pos(this.smooth) + "%";
    this.peakEl.style.left = `calc(${this.pos(this.hold)}% - 1px)`;
    this.lbl.textContent = this.hold > -89 ? `peak ${this.hold.toFixed(0)} dBFS` : "–";
    this.clip.classList.toggle("on", now - this.clipT < 2000);
  }
}

export class StaticWave {
  constructor(canvas, { peaks = [], duration = 0, segments = [], markers = [], onSeek } = {}) {
    this.c = canvas; this.ctx = canvas.getContext("2d");
    Object.assign(this, { peaks, duration, segments, markers, onSeek, playhead: -1 });
    canvas.addEventListener("click", (e) => {
      if (!this.duration || !this.onSeek) return;
      const r = canvas.getBoundingClientRect();
      this.onSeek(((e.clientX - r.left) / r.width) * this.duration);
    });
    this.ro = new ResizeObserver(() => this.draw());
    this.ro.observe(canvas);
    this.draw();
  }
  setPeaksFromSamples(samples, buckets = 600) {
    const out = [], n = samples.length, step = n / buckets;
    for (let b = 0; b < buckets; b++) {
      let mn = 1, mx = -1;
      const a = Math.floor(b * step), e = Math.max(a + 1, Math.floor((b + 1) * step));
      for (let i = a; i < e && i < n; i++) { const v = samples[i]; if (v < mn) mn = v; if (v > mx) mx = v; }
      out.push([mn, mx]);
    }
    this.peaks = out; this.draw();
  }
  setPlayhead(t) { this.playhead = t; this.draw(); }
  draw() {
    if (!this.c.isConnected) return;
    const { w, h } = fit(this.c);
    const g = this.ctx, mid = h / 2;
    g.clearRect(0, 0, w, h);
    const D = this.duration || 1;
    g.fillStyle = css("--speech-band");
    for (const [a, b] of this.segments) g.fillRect((a / D) * w, 0, ((b - a) / D) * w, h);
    const n = this.peaks.length;
    if (n) {
      const colW = w / n;
      const played = this.playhead >= 0 ? (this.playhead / D) * w : -1;
      for (let i = 0; i < n; i++) {
        const [mn, mx] = this.peaks[i];
        const x = i * colW;
        g.fillStyle = played >= 0 && x <= played ? css("--accent") : css("--wave");
        const pk = Math.max(-mn, mx);
        if (pk >= 0.99) g.fillStyle = css("--rec");
        const y0 = mid - mx * mid * 0.92, y1 = mid - mn * mid * 0.92;
        g.fillRect(x, y0, Math.max(1, colW - 0.5), Math.max(1, y1 - y0));
      }
    }
    for (const m of this.markers) {
      g.fillStyle = m.kind === "clip" ? css("--rec") : css("--warn");
      const x = (m.t / D) * w;
      g.fillRect(x - 1, 0, 2, 9 * (window.devicePixelRatio || 1));
    }
    if (this.playhead >= 0) {
      g.fillStyle = css("--text");
      g.fillRect((this.playhead / D) * w, 0, 1.5, h);
    }
  }
  destroy() { this.ro.disconnect(); }
}

export class Player {
  constructor() { this.ctx = null; this.buf = null; this.src = null; this.offset = 0; this.startAt = 0; this.playing = false; this.onprogress = null; this.onend = null; this.raf = null; }
  _ensure() { if (!this.ctx) this.ctx = new AudioContext(); return this.ctx; }
  loadSamples(samples, sampleRate) {
    const ctx = this._ensure();
    this.stop();
    this.buf = ctx.createBuffer(1, samples.length, sampleRate);
    this.buf.copyToChannel(samples, 0);
    this.offset = 0;
  }
  async loadUrl(url) {
    const ctx = this._ensure();
    this.stop();
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("could not load audio");
    this.buf = await ctx.decodeAudioData(await res.arrayBuffer());
    this.offset = 0;
  }
  get duration() { return this.buf ? this.buf.duration : 0; }
  get time() { return this.playing ? Math.min(this.duration, this.offset + this.ctx.currentTime - this.startAt) : this.offset; }
  async play(from) {
    if (!this.buf) return;
    const ctx = this._ensure();
    if (ctx.state === "suspended") await ctx.resume();
    this._stopSource();
    if (from !== undefined) this.offset = Math.max(0, Math.min(from, this.duration - 0.01));
    if (this.offset >= this.duration - 0.02) this.offset = 0;
    const src = ctx.createBufferSource();
    src.buffer = this.buf; src.connect(ctx.destination);
    src.onended = () => { if (this.src === src) { this.playing = false; this.offset = 0; this.onend && this.onend(); cancelAnimationFrame(this.raf); this.onprogress && this.onprogress(-1); } };
    src.start(0, this.offset);
    this.src = src; this.startAt = ctx.currentTime; this.playing = true;
    const tick = () => { if (!this.playing) return; this.onprogress && this.onprogress(this.time); this.raf = requestAnimationFrame(tick); };
    tick();
  }
  pause() { if (!this.playing) return; this.offset = this.time; this._stopSource(); this.playing = false; cancelAnimationFrame(this.raf); }
  toggle() { return this.playing ? this.pause() : this.play(); }
  seek(t) { const was = this.playing; this.pause(); this.offset = t; if (was) this.play(); else this.onprogress && this.onprogress(t); }
  _stopSource() { if (this.src) { const s = this.src; this.src = null; try { s.onended = null; s.stop(); } catch {} } }
  stop() { this._stopSource(); this.playing = false; this.offset = 0; cancelAnimationFrame(this.raf); }
}
