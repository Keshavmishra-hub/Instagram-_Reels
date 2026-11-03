"""Command line:  python -m myvoice <command>

  serve [--port 8100] [--lan] [--https]   start the studio (http://127.0.0.1:8100)
  doctor                                  check microphone-independent components
  stats                                   dataset summary and readiness milestones
  export <profile> [--sample-rate N]      export approved takes (see `export --list`)
  import-exercises <file.json|yaml>       add exercises (e.g. written by Claude Code)
  coverage --json                         full coverage report (used by the Claude Code skill)
  rebuild-index                           re-read every sidecar file
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from . import PRODUCT_NAME, __version__
from .config import settings


def _p(*a):
    print(*a, flush=True)


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _self_signed_cert(cert_dir: Path, ip: str) -> tuple[Path, Path]:
    cert_dir.mkdir(parents=True, exist_ok=True)
    key, crt = cert_dir / "studio-key.pem", cert_dir / "studio-cert.pem"
    if key.exists() and crt.exists():
        return key, crt
    openssl = shutil.which("openssl")
    if not openssl:
        sys.exit("HTTPS needs a certificate. Install OpenSSL, or create one with mkcert and pass --cert/--key.")
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825", "-keyout", str(key), "-out", str(crt),
                    "-subj", "/CN=MY VOICE studio", "-addext", f"subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost"],
                   check=True, capture_output=True)
    key.chmod(0o600)
    return key, crt


def cmd_serve(args):
    import uvicorn

    from .server.app import create_app
    from .studio import Studio

    host = "0.0.0.0" if args.lan else args.host
    use_https = args.https or args.lan
    token = None
    if host not in ("127.0.0.1", "localhost", "::1"):
        token = secrets.token_urlsafe(18)
    studio = Studio()
    app = create_app(studio, token=token)
    ssl = {}
    scheme = "http"
    if use_https:
        ip = _lan_ip()
        key, crt = (Path(args.key), Path(args.cert)) if args.cert and args.key else _self_signed_cert(settings.data_dir / "certs", ip)
        ssl = {"ssl_keyfile": str(key), "ssl_certfile": str(crt)}
        scheme = "https"
    _p(f"\n  {PRODUCT_NAME}  v{__version__}")
    _p(f"  Data folder: {settings.data_dir.resolve()}")
    asr = studio.asr.status()
    _p(f"  Read-check:  {'faster-whisper ' + asr['model'] if asr['installed'] and asr['enabled'] else 'off — ' + (asr['install_hint'] or 'disabled')}")
    if token:
        ip = _lan_ip()
        _p(f"\n  Open on this computer:   {scheme}://127.0.0.1:{args.port}/?token={token}")
        _p(f"  Open on your phone:      {scheme}://{ip}:{args.port}/?token={token}")
        if use_https:
            _p("  (self-signed certificate: accept the browser warning once — microphones need HTTPS on phones)")
        _p("  Anyone with this link on your network can reach your recordings. Stop the server when done.\n")
    else:
        _p(f"\n  Open:  {scheme}://127.0.0.1:{args.port}\n")
    uvicorn.run(app, host=host, port=args.port, log_level="warning", **ssl)


def cmd_doctor(_args):
    from .studio import Studio

    st = Studio(asr_enabled=None)
    caps = st.capabilities()
    ok = lambda b: "ok " if b else "-- "  # noqa: E731
    _p(f"{PRODUCT_NAME} v{__version__}")
    _p(f"  {ok(True)}data folder      {caps['data_dir']}")
    _p(f"  {ok(caps['praat'])}Praat (parselmouth) pitch / voice analysis" + ("" if caps["praat"] else "  -> pip install praat-parselmouth"))
    _p(f"  {ok(caps['webrtcvad'])}WebRTC VAD" + ("" if caps["webrtcvad"] else "  -> pip install webrtcvad-wheels (energy VAD used meanwhile)"))
    _p(f"  {ok(caps['espeak']['available'])}eSpeak NG (English phonemes)" + ("" if caps["espeak"]["available"] else f"  -> {caps['espeak']['error']}"))
    a = caps["asr"]
    _p(f"  {ok(a['installed'])}faster-whisper read-check (model: {a['model']})" + ("" if a["installed"] else f"  -> {a['install_hint']}"))
    _p(f"  {ok(caps['ffmpeg'])}FFmpeg (MP3 export for ElevenLabs)")
    _p(f"  {ok(not caps['bank_errors'])}exercise bank: {len(st.bank.exercises)} exercises" + ("" if not caps["bank_errors"] else f"  errors: {caps['bank_errors']}"))
    if caps["load_errors"]:
        _p(f"  !! unreadable files: {caps['load_errors'][:5]}")


def cmd_stats(_args):
    from .studio import Studio

    st = Studio(asr_enabled=False)
    s = st.coverage().summary()
    t = s["totals"]
    _p(f"Approved: {t['approved_seconds'] / 60:.1f} min ({t['approved']} takes)   recorded: {t['recorded_seconds'] / 60:.1f} min   pending review: {t['pending']}")
    _p(f"Completeness: {s['completeness']:.0f}%   stage: {s['stage']}")
    for m in s["milestones"]:
        _p(f"\n[{'x' if m['done'] else ' '}] {m['title']}  ({m['progress'] * 100:.0f}%)")
        for c in m["checks"]:
            _p(f"     {'✓' if c['progress'] >= 1 else '·'} {c['label']}: {c['display']}")


def cmd_coverage(args):
    from .studio import Studio

    st = Studio(asr_enabled=False)
    s = st.coverage().summary()
    pick = st.next()
    s["next"] = {"phase": pick.phase, "reason": pick.reason, "factors": pick.factors}
    _p(json.dumps(s, ensure_ascii=False, indent=2 if not args.compact else None))


def cmd_export(args):
    from .export import PROFILES, run_export
    from .studio import Studio

    if args.list or not args.profile:
        for k, v in PROFILES.items():
            _p(f"  {k:14} {v['title']}: {v['summary']}")
        return
    st = Studio(asr_enabled=False)
    opts = {}
    if args.sample_rate:
        opts["sample_rate"] = args.sample_rate
    if args.include_pending:
        opts["include_pending"] = True
    res = run_export(st, args.profile, opts)
    _p(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_import(args):
    import yaml

    from .curriculum.bank import ExerciseBank

    src = Path(args.file)
    doc = json.loads(src.read_text(encoding="utf-8")) if src.suffix == ".json" else yaml.safe_load(src.read_text(encoding="utf-8"))
    settings.ensure_dirs()
    dest = settings.exercises_dir / (src.stem + ".json")
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    before = len(ExerciseBank().exercises)
    bank = ExerciseBank(extra_dirs=[settings.exercises_dir])
    if bank.errors:
        dest.unlink(missing_ok=True)
        sys.exit("Import rejected: " + "; ".join(bank.errors))
    _p(f"Imported {dest.name}: bank now has {len(bank.exercises)} exercises ({len(bank.exercises) - before} beyond the built-in curriculum).")


def cmd_rebuild(_args):
    from .store import DatasetStore

    settings.ensure_dirs()
    st = DatasetStore(settings.data_dir)
    _p(f"{len(st.takes(include_trashed=True))} takes, {len(st.sessions())} sessions indexed.")
    for e in st.load_errors:
        _p("  unreadable:", e)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m myvoice", description=PRODUCT_NAME)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the studio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8100)
    s.add_argument("--lan", action="store_true", help="serve on your network (HTTPS + access token) to record from a phone")
    s.add_argument("--https", action="store_true", help="serve over HTTPS (self-signed certificate unless --cert/--key)")
    s.add_argument("--cert", default="")
    s.add_argument("--key", default="")
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("doctor", help="check components").set_defaults(fn=cmd_doctor)
    sub.add_parser("stats", help="dataset summary").set_defaults(fn=cmd_stats)
    c = sub.add_parser("coverage", help="coverage report as JSON")
    c.add_argument("--json", action="store_true")
    c.add_argument("--compact", action="store_true")
    c.set_defaults(fn=cmd_coverage)
    e = sub.add_parser("export", help="export approved takes")
    e.add_argument("profile", nargs="?", default="")
    e.add_argument("--list", action="store_true")
    e.add_argument("--sample-rate", type=int, default=0)
    e.add_argument("--include-pending", action="store_true")
    e.set_defaults(fn=cmd_export)
    i = sub.add_parser("import-exercises", help="add exercises from a JSON/YAML file")
    i.add_argument("file")
    i.set_defaults(fn=cmd_import)
    sub.add_parser("rebuild-index", help="re-read all sidecar files").set_defaults(fn=cmd_rebuild)
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return
    args.fn(args)
