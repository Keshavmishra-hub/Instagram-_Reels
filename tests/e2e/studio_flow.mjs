// Browser end-to-end test for MY VOICE (optional; needs Node + Playwright with Chromium).
//
//   python -m myvoice serve --port 8123        (with MYVOICE_DATA_DIR pointing at a scratch folder)
//   BASE=http://127.0.0.1:8123 MEDIA=/path/to/wavs OUT=/path/for/screenshots node tests/e2e/studio_flow.mjs
//
// A fake microphone (Web Audio stream with quiet room noise) replaces getUserMedia, and real speech
// WAVs are played into it when a take starts, so whole takes go through the real recorder, upload,
// analysis and review UI. Every page is then visited on desktop, mobile and dark mode; any console
// error or page error fails the run.
import { readFileSync } from "node:fs";

let playwright;
try { playwright = await import("playwright"); } catch { playwright = await import("/opt/node-tools/node_modules/playwright/index.mjs"); }
const { chromium, devices } = playwright;

const BASE = process.env.BASE || "http://127.0.0.1:8123";
const MEDIA = process.env.MEDIA;
const OUT = process.env.OUT || ".";
const failures = [];

const fakeMic = () => {
  window.__fake = {};
  navigator.mediaDevices.getUserMedia = async () => {
    const ctx = new AudioContext({ sampleRate: 48000 });
    const dest = ctx.createMediaStreamDestination();
    const buf = ctx.createBuffer(1, 48000 * 2, 48000);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * 0.0005; // ≈ -71 dBFS room noise
    const noise = ctx.createBufferSource();
    noise.buffer = buf; noise.loop = true; noise.connect(dest); noise.start();
    window.__fake = { ctx, dest };
    return dest.stream;
  };
  window.__speak = async (url) => {
    const f = window.__fake;
    const b = await f.ctx.decodeAudioData(await (await fetch(url)).arrayBuffer());
    const s = f.ctx.createBufferSource();
    s.buffer = b; s.connect(f.dest); s.start();
  };
};

async function newPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: +(process.env.DSF || 1), ...opts });
  await ctx.grantPermissions(["microphone"], { origin: BASE });
  await ctx.route("**/fake/*.wav", (route) => route.fulfill({ body: readFileSync(`${MEDIA}/${route.request().url().split("/").pop()}`), contentType: "audio/wav" }));
  await ctx.addInitScript(fakeMic);
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") failures.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
  return page;
}

async function take(page, wav, label, retries = 2) {
  const r = await takeOnce(page, wav, label);
  // a dropout here means the *test harness* audio glitched (CPU load); the studio flagging it is correct —
  // do what a user would do: record again
  if (retries > 0 && r.issues.some((i) => i.startsWith("Audio dropout"))) {
    console.log("             (audio glitch in the fake microphone detected as a dropout — re-recording)");
    await page.keyboard.press("r"); await page.waitForTimeout(300);
    return take(page, wav, label, retries - 1);
  }
  return r;
}

async function takeOnce(page, wav, label) {
  const before = await page.$eval(".prompt-card", (el) => el.textContent.slice(0, 60)).catch(() => "");
  await page.keyboard.press("Space");
  await page.waitForTimeout(250);
  if (wav) await page.evaluate((u) => window.__speak(u), `/fake/${wav}.wav`);
  await page.waitForSelector(".review .score-ring", { timeout: 45000 });
  const verdict = (await page.textContent(".review .verdict")).trim();
  const score = await page.textContent(".review .score-ring .val");
  const issues = await page.$$eval(".review .issue .msg", (els) => els.map((e) => e.textContent));
  const metrics = await page.$$eval(".review .metric", (els) => els.map((e) => e.textContent.replace(/\s+/g, " ")));
  console.log(`${label.padEnd(12)} ${verdict} (${score}) ${issues.join(" | ")}\n             ${metrics.join(" · ")}\n             prompt: ${before}`);
  return { verdict, score: +score, issues };
}

const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
const page = await newPage(browser);
await page.goto(`${BASE}/#/studio`);
await page.waitForSelector(".modal", { timeout: 10000 });
await page.fill(".modal input[type=text]", "Test Speaker");
await page.click(".modal .seg button:first-child");
await page.click(".modal .btn-primary");
await page.waitForSelector(".prompt-card .chip");
await page.screenshot({ path: `${OUT}/01_studio_room_tone.png` });

const results = {};
results.room = await take(page, null, "room tone");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
results.clap = await take(page, "clap", "clap");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
results.mic = await take(page, "mic", "mic check");
await page.screenshot({ path: `${OUT}/02_studio_review.png` });
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
results.consent = await take(page, "consent", "consent EN");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
await page.keyboard.press("n"); await page.waitForTimeout(800); // skip the Hindi consent for now
results.anchor = await take(page, "anchor", "anchor");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
// a Hindi prompt with Roman transliteration should be reachable directly
await page.goto(`${BASE}/#/studio/A-NORM-04`); await page.waitForSelector(".prompt-roman");
await page.screenshot({ path: `${OUT}/03_studio_hindi.png` });
results.hindi = await take(page, "hindi", "hindi");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);
await page.goto(`${BASE}/#/studio/A-NORM-01`); await page.waitForSelector(".prompt-text");
results.short = await take(page, "anorm", "A-NORM-01");
// re-record keeps the old take (rejected), then approve the new one
await page.keyboard.press("r"); await page.waitForTimeout(300);
results.again = await take(page, "anorm", "re-record");
await page.keyboard.press("Enter"); await page.waitForTimeout(800);

for (const [route, file] of [["dashboard", "04_dashboard"], ["curriculum", "05_curriculum"], ["curriculum/E", "06_module_E"], ["analytics", "07_analytics"], ["dataset", "08_dataset"], ["settings", "09_settings"]]) {
  await page.goto(`${BASE}/#/${route}`);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: route !== "dataset" });
}
await page.goto(`${BASE}/#/dataset`); await page.waitForTimeout(800);
await page.click(".seg button:nth-child(4)"); await page.waitForTimeout(600); // "All"
await page.click(".take-row .tx >> nth=1"); await page.waitForSelector(".drawer");
await page.waitForTimeout(600);
await page.screenshot({ path: `${OUT}/10_dataset_drawer.png` });

// mobile + dark
const mobile = await newPage(browser, { ...devices["iPhone 13"], colorScheme: "dark" });
await mobile.goto(`${BASE}/#/studio`); await mobile.waitForSelector(".prompt-card .chip", { timeout: 15000 });
await mobile.waitForTimeout(800);
await mobile.screenshot({ path: `${OUT}/11_mobile_studio_dark.png` });
await mobile.goto(`${BASE}/#/dashboard`); await mobile.waitForTimeout(1500);
await mobile.screenshot({ path: `${OUT}/12_mobile_dashboard_dark.png` });
const dark = await newPage(browser, { colorScheme: "dark" });
await dark.goto(`${BASE}/#/studio/G-HOOK-04`); await dark.waitForSelector(".prompt-text"); await dark.waitForTimeout(800);
await dark.screenshot({ path: `${OUT}/13_studio_dark.png` });
await dark.goto(`${BASE}/#/analytics`); await dark.waitForTimeout(1500);
await dark.screenshot({ path: `${OUT}/14_analytics_dark.png`, fullPage: true });

await browser.close();
const expect = (cond, msg) => { if (!cond) failures.push(msg); };
expect(results.room.verdict.includes("Great"), "room tone should be good");
expect(results.clap.issues.length === 0 || results.clap.verdict.includes("Great"), "clap in a 0.35 s room should be good");
expect(results.mic.verdict.includes("Great"), "mic check should be good");
expect(results.anchor.verdict.includes("Great"), "anchor should be good");
console.log(failures.length ? `\nFAILURES:\n${failures.join("\n")}` : "\nE2E OK");
process.exit(failures.length ? 1 : 0);
