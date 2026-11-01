"""Script stage: write from verified claims (Claude API) or accept a hand/Claude-Code-written script."""

from __future__ import annotations

from typing import Callable

from ..config import Settings, settings as default_settings
from ..languages import get_language
from ..models import Beat, Research, Script, now_iso
from ..storage import ProjectStore
from ..styles import get_style
from .validate import estimated_seconds, validate_script


def claims_table(research: Research, include_single: bool = True) -> str:
    rows = []
    for c in research.claims:
        if not c.use_in_script or c.status in ("unverified", "excluded"):
            continue
        if c.status == "single_source" and not include_single:
            continue
        rows.append(f"{c.id} | {c.status} | {c.certainty} | {c.as_of or '-'} | {c.statement} | {c.caveats or '-'}")
    return "\n".join(rows)


def write_script(pid: str, store: ProjectStore, s: Settings = default_settings, log: Callable[[str], None] = print) -> Script:
    from ..llm.client import Claude
    from ..llm.prompts import SCRIPT_PROMPT, SCRIPT_SYSTEM
    from ..llm.schemas import XScript

    project = store.project(pid)
    ps = project.settings
    research = store.research(pid)
    if research is None:
        raise RuntimeError("Run research first")
    if not research.sufficiency.enough:
        raise RuntimeError(f"Research is not sufficient for an accurate reel: {research.sufficiency.reason}")
    style = get_style(ps.style)
    speech = max(10, ps.duration - 4)
    prompt = SCRIPT_PROMPT.format(
        topic=ps.topic, language=get_language(ps.language).name, style_name=style.name, style_desc=style.description,
        hooks="; ".join(style.hook_patterns), voice=style.voice_direction, structure=style.structure_notes,
        duration=ps.duration, words_min=int(speech * 2.2), words_max=int(speech * 2.6),
        audience=ps.audience or "general Instagram audience", angle=ps.angle or "(none)",
        summary=research.summary, claims=claims_table(research), uncertainties="\n".join(f"- {u}" for u in research.uncertainties) or "-",
    )
    log("Writing script with Claude ...")
    x = Claude(s).structured(SCRIPT_SYSTEM, prompt, XScript, effort="high")
    beats = [Beat(id=f"B{i}", section=b.section, text=b.text.strip(), claim_ids=b.claim_ids, emphasis=b.emphasis,
                  on_screen_text=b.on_screen_text) for i, b in enumerate(x.beats, 1)]
    prev = store.script(pid)
    script = Script(title=x.title, hook_type=x.hook_type, style=ps.style, language=ps.language, beats=beats,
                    cta_question=x.cta_question, version=(prev.version + 1) if prev else 1, written_by=f"claude_api:{s.llm_model}")
    script.issues = validate_script(script, research, ps.duration)
    save_script(pid, store, script)
    store.write_text(pid, "script_notes.md", f"# Integrity notes\n\n{x.integrity_notes}\n")
    log(f"Script v{script.version}: {len(beats)} beats, ~{estimated_seconds(script):.0f}s, {sum(1 for i in script.issues if i.severity == 'error')} error(s)")
    return script


def save_script(pid: str, store: ProjectStore, script: Script) -> None:
    research = store.research(pid)
    project = store.project(pid)
    script.issues = validate_script(script, research, project.settings.duration)
    store.save("script", pid, script)
    store.write_text(pid, "script.md", script_markdown(script, research))


def approve_script(pid: str, store: ProjectStore) -> Script:
    script = store.script(pid)
    if script is None:
        raise RuntimeError("No script")
    errors = [i for i in script.issues if i.severity == "error"]
    if errors:
        raise RuntimeError("Fix script errors before approval: " + "; ".join(f"{i.beat_id or ''} {i.message}" for i in errors))
    script.approved = True
    script.approved_at = now_iso()
    store.save("script", pid, script)
    return script


def script_markdown(script: Script, research: Research | None) -> str:
    out = [f"# {script.title}", "", f"Style: {script.style} · Language: {script.language} · Version {script.version} · Estimated {estimated_seconds(script):.0f}s", ""]
    for b in script.beats:
        cites = ", ".join(b.claim_ids) or "-"
        out.append(f"**{b.id} [{b.section}]** {b.text}  ")
        out.append(f"<sub>claims: {cites}" + (f" · on-screen: {b.on_screen_text}" if b.on_screen_text else "") + "</sub>")
        out.append("")
    if script.cta_question:
        out += [f"**Closing question:** {script.cta_question}", ""]
    if script.issues:
        out += ["## Validation", ""] + [f"- [{i.severity}] {i.beat_id or ''} {i.message}" for i in script.issues] + [""]
    if research:
        used = {cid for b in script.beats for cid in b.claim_ids}
        out += ["## Claims used", ""]
        for cid in sorted(used, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
            c = research.claim(cid)
            if c:
                srcs = ", ".join(f"{e.source_id}" for e in c.evidence)
                out.append(f"- {cid} ({c.status}): {c.statement} [{srcs}]")
        out.append("")
    return "\n".join(out)
