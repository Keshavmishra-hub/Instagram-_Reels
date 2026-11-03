// Runs on the audio rendering thread: forwards raw microphone samples (no processing, no codec)
// to the main thread in 1024-sample chunks, with peak and RMS per chunk.
// Stereo inputs: if one channel is silent (common with audio interfaces) the live channel is used,
// otherwise the channels are averaged; decided once after 0.5 s.

class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = 1024;
    this.buf = new Float32Array(this.size);
    this.n = 0;
    this.mode = null;
    this.e0 = 0;
    this.e1 = 0;
    this.seen = 0;
  }

  process(inputs) {
    const inp = inputs[0];
    if (!inp || inp.length === 0 || !inp[0]) return true;
    const c0 = inp[0];
    const c1 = inp.length > 1 ? inp[1] : null;
    if (c1 && this.mode === null) {
      for (let i = 0; i < c0.length; i++) { this.e0 += c0[i] * c0[i]; this.e1 += c1[i] * c1[i]; }
      this.seen += c0.length;
      if (this.seen >= sampleRate * 0.5 && (this.e0 + this.e1) > 1e-9) {
        const r = (this.e0 + 1e-12) / (this.e1 + 1e-12);
        this.mode = r > 1000 ? "ch0" : r < 0.001 ? "ch1" : "avg";
        this.port.postMessage({ type: "mode", mode: this.mode });
      }
    }
    for (let i = 0; i < c0.length; i++) {
      let v;
      if (!c1 || this.mode === "ch0") v = c0[i];
      else if (this.mode === "ch1") v = c1[i];
      else v = 0.5 * (c0[i] + c1[i]);
      this.buf[this.n++] = v;
      if (this.n === this.size) this.flush();
    }
    return true;
  }

  flush() {
    let peak = 0, ss = 0;
    for (let i = 0; i < this.n; i++) {
      const v = this.buf[i];
      const a = v < 0 ? -v : v;
      if (a > peak) peak = a;
      ss += v * v;
    }
    const chunk = this.buf.slice(0, this.n);
    this.port.postMessage({ type: "chunk", samples: chunk, peak, rms: Math.sqrt(ss / this.n) }, [chunk.buffer]);
    this.n = 0;
  }
}

registerProcessor("myvoice-capture", CaptureProcessor);
