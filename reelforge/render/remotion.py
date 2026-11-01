"""Bridge to the Node/Remotion renderer (renderer/render.mjs)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from ..config import Settings, settings as default_settings


class RenderError(RuntimeError):
    pass


def run(
    props_path: Path,
    *,
    out: Optional[Path] = None,
    still: Optional[Path] = None,
    frame: int = 0,
    composition: str = "Reel",
    assets_root: Optional[Path] = None,
    scale: float = 1.0,
    frames: Optional[tuple[int, int]] = None,
    progress: Callable[[float], None] = lambda p: None,
    log: Callable[[str], None] = print,
    s: Settings = default_settings,
) -> Path:
    if not (s.renderer_dir / "node_modules" / "remotion").exists():
        raise RenderError("Renderer dependencies missing. Run: cd renderer && npm install")
    cmd = [s.node_bin, str(s.renderer_dir / "render.mjs"), "--props", str(props_path), "--composition", composition]
    if still:
        cmd += ["--still", str(still), "--frame", str(int(frame))]
    else:
        cmd += ["--out", str(out), "--concurrency", str(s.render_concurrency)]
    if assets_root:
        cmd += ["--assets-root", str(assets_root)]
    if scale != 1.0:
        cmd += ["--scale", str(scale)]
    if frames:
        cmd += ["--frames", f"{frames[0]}-{frames[1]}"]
    env = dict(os.environ)
    if s.chrome_executable:
        env["REELFORGE_CHROME"] = s.chrome_executable
    proc = subprocess.Popen(cmd, cwd=s.renderer_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    errors: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "progress":
            progress(float(msg.get("progress", 0)))
        elif msg.get("type") == "status":
            log(msg.get("message", ""))
        elif msg.get("type") == "error":
            errors.append(msg.get("message", "unknown error"))
    stderr = proc.stderr.read() if proc.stderr else ""
    code = proc.wait()
    if code != 0 or errors:
        noise = ("Memory reported", "MemAvailable", "docker run", "Using the lower amount", "Detected differing")
        tail = "\n".join(l for l in stderr.splitlines() if l.strip() and not any(n in l for n in noise))[-2000:]
        raise RenderError((errors[0] if errors else f"renderer exited with code {code}") + ("\n" + tail if tail else ""))
    return Path(still or out)  # type: ignore[arg-type]
