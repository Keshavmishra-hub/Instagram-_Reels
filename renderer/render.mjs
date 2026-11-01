#!/usr/bin/env node
/**
 * ReelForge render CLI (called by the Python backend).
 *
 *   node render.mjs --props props.json --out video.mp4 [--assets-root DIR] [--scale 0.5]
 *                   [--frames 0-89] [--concurrency 4] [--chrome PATH]
 *   node render.mjs --props cover.json --composition Cover --still cover.jpg
 *   node render.mjs --props props.json --still frame.jpg --frame 120
 *
 * Progress is printed as JSON lines: {"type":"progress","progress":0.42}
 */
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, arr) => {
    if (a.startsWith('--')) acc.push([a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : 'true']);
    return acc;
  }, []),
);
const log = (o) => process.stdout.write(JSON.stringify(o) + '\n');

const hashDir = (dir) => {
  const h = crypto.createHash('sha1');
  const walk = (d) => {
    for (const f of fs.readdirSync(d).sort()) {
      const p = path.join(d, f);
      const st = fs.statSync(p);
      if (st.isDirectory()) walk(p);
      else h.update(p).update(String(st.size)).update(String(st.mtimeMs));
    }
  };
  walk(dir);
  h.update(fs.readFileSync(path.join(here, 'package.json')));
  return h.digest('hex').slice(0, 16);
};

const getBundle = async () => {
  const key = hashDir(path.join(here, 'src')) + '-' + hashDir(path.join(here, 'public'));
  const outDir = path.join(here, '.bundle-cache', key);
  if (fs.existsSync(path.join(outDir, 'index.html'))) return outDir;
  log({type: 'status', message: 'Bundling compositions (first run takes ~20s)'});
  fs.rmSync(path.join(here, '.bundle-cache'), {recursive: true, force: true});
  return bundle({entryPoint: path.join(here, 'src', 'index.ts'), outDir, publicDir: path.join(here, 'public')});
};

const MIME = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.json': 'application/json', '.wav': 'audio/wav', '.mp3': 'audio/mpeg'};

const serve = (root) =>
  new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const rel = decodeURIComponent((req.url || '/').split('?')[0]).replace(/^\/+/, '');
      const file = path.resolve(root, rel);
      if (!file.startsWith(path.resolve(root)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404);
        return res.end();
      }
      const size = fs.statSync(file).size;
      const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
      const range = req.headers.range;
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Accept-Ranges', 'bytes');
      if (range) {
        const [s, e] = range.replace('bytes=', '').split('-');
        const start = Number(s);
        const end = e ? Number(e) : size - 1;
        res.writeHead(206, {'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1});
        fs.createReadStream(file, {start, end}).pipe(res);
      } else {
        res.writeHead(200, {'Content-Type': type, 'Content-Length': size});
        fs.createReadStream(file).pipe(res);
      }
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });

const main = async () => {
  const props = JSON.parse(fs.readFileSync(args.props, 'utf8'));
  const id = args.composition || 'Reel';
  const browserExecutable = args.chrome && args.chrome !== 'true' ? args.chrome : process.env.REELFORGE_CHROME || null;
  let server = null;
  if (args['assets-root']) {
    server = await serve(args['assets-root']);
    props.assetsBase = `http://127.0.0.1:${server.address().port}`;
  }
  try {
    const serveUrl = await getBundle();
    const chromiumOptions = {gl: null, disableWebSecurity: false};
    const composition = await selectComposition({serveUrl, id, inputProps: props, browserExecutable, chromiumOptions, logLevel: 'error'});
    if (args.still) {
      await renderStill({
        composition,
        serveUrl,
        output: args.still,
        inputProps: props,
        frame: Number(args.frame || 0),
        imageFormat: args.still.endsWith('.png') ? 'png' : 'jpeg',
        jpegQuality: 92,
        scale: Number(args.scale || 1),
        browserExecutable,
        chromiumOptions,
        logLevel: 'error',
      });
      log({type: 'done', output: args.still});
    } else {
      const frameRange = args.frames ? args.frames.split('-').map(Number) : null;
      let last = -1;
      await renderMedia({
        composition,
        serveUrl,
        codec: 'h264',
        outputLocation: args.out,
        inputProps: props,
        browserExecutable,
        chromiumOptions,
        concurrency: Number(args.concurrency || 0) || null,
        muted: true,
        crf: Number(args.crf || 18),
        pixelFormat: 'yuv420p',
        colorSpace: 'bt709',
        imageFormat: 'jpeg',
        jpegQuality: 90,
        scale: Number(args.scale || 1),
        frameRange: frameRange && frameRange.length === 2 ? frameRange : null,
        logLevel: 'error',
        onProgress: ({progress}) => {
          const p = Math.floor(progress * 100);
          if (p !== last) {
            last = p;
            log({type: 'progress', progress});
          }
        },
      });
      log({type: 'done', output: args.out});
    }
  } finally {
    if (server) server.close();
  }
};

main().catch((err) => {
  log({type: 'error', message: String(err && err.stack ? err.stack : err)});
  process.exit(1);
});
