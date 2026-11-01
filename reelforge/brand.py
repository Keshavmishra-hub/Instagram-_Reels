"""Brand kits (brands/*.yaml) -> renderer-ready dictionaries."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import settings
from .languages import FONT_STACKS, get_language

DEFAULT_BRAND = {
    "name": "Default",
    "handle": "",
    "watermark": True,
    "progress_bar": True,
    "colors": {
        "background": "#0A0F1C", "surface": "#121A2E", "primary": "#FFC93C", "secondary": "#4FD1C5",
        "text": "#FFFFFF", "muted": "#A3ADC6", "danger": "#FF6B6B",
        "map_ocean": "#060A14", "map_land": "#1B2540", "map_border": "#2F3D63",
    },
    "fonts": {"display": "Anton", "body": "Inter", "subtitle": "Montserrat"},
    "subtitles": {"case": "upper", "size": 64, "max_words": 3, "max_chars": 22, "style": "outline"},
    "grade": {"vignette": 0.4, "grain": 0.05, "contrast": 1.05, "saturation": 1.03},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def list_brands() -> list[dict]:
    out = []
    for p in sorted(Path(settings.brands_dir).glob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        out.append({"key": p.stem, "name": data.get("name", p.stem), "handle": data.get("handle", "")})
    return out


def load_brand(key: str = "default", language: str = "en") -> dict:
    p = Path(settings.brands_dir) / f"{key}.yaml"
    data = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    brand = _merge(DEFAULT_BRAND, data)
    brand["key"] = key
    lang = get_language(language)
    if lang.script != "latin":
        # Non-Latin scripts: swap to fonts that actually contain the glyphs.
        brand["fonts"] = dict(FONT_STACKS[lang.script])
        brand["subtitles"]["case"] = "sentence"
    brand["script"] = lang.script
    return brand
