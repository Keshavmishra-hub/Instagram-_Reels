"""Master timeline for the MASS ENTHUSIAST intro (shared by Blender, compositor and audio).

Everything is expressed in global frames at 30 fps so picture and sound are cut from
the same numbers. Change a shot length here and every stage follows.
"""
from __future__ import annotations

import math

FPS = 30
DURATION_S = 33.0
N_FRAMES = int(round(DURATION_S * FPS))  # 990 frames: 0 .. 989


def sec(t: float) -> int:
    return int(round(t * FPS))


# (id, first frame, last frame inclusive, description)
SHOTS = [
    ("s01_chain", sec(0.0), sec(5.0) - 1, "A suspended steel chain turning in the dark"),
    ("s02_reel", sec(5.0), sec(6.3) - 1, "Match cut: 35mm film reel turning, lamp light through the spokes"),
    ("s03_film", sec(6.3), sec(7.5) - 1, "Film strip racing through the projector gate"),
    ("s04_projector", sec(7.5), sec(8.6) - 1, "Projector lens ignites, beam through haze"),
    ("s05_ticket", sec(8.6), sec(9.8) - 1, "Theatre ticket burning at the edges"),
    ("s06_lens", sec(9.8), sec(10.8) - 1, "Cine lens: the iris snaps shut"),
    ("s07_speaker", sec(10.8), sec(12.0) - 1, "Speaker cone pumping with the bass"),
    ("s08_redline", sec(12.0), sec(13.4) - 1, "A red light races along the coiled chain"),
    ("s09_sparks", sec(13.4), sec(14.6) - 1, "Sparks scream across steel"),
    ("s10_spot", sec(14.6), sec(15.8) - 1, "Spotlight swings into camera through smoke"),
    ("s11_vortex", sec(15.8), sec(18.3) - 1, "Every object turns toward camera; push through"),
    ("s12_flash", sec(18.3), sec(19.0) - 1, "Flash and suck-back to black (2D)"),
    ("s13_title", sec(19.0), sec(27.0) - 1, "MASS ENTHUSIAST is assembled"),
    ("s14_hero", sec(27.0), N_FRAMES - 1, "Hero shot of the title"),
]
SHOT = {s[0]: (s[1], s[2]) for s in SHOTS}

# Title choreography (global frames). Plates slam into the letter frames.
TITLE = {
    "slam_M": sec(19.20),
    "slam_A": sec(19.77),
    "slam_S1": sec(20.37),
    "slam_S2": sec(20.97),
    "mass_lock": sec(21.40),          # wide: whole word shudders, light sweep starts
    "sweep_mass": (sec(21.55), sec(22.55)),
    "enth_first": sec(23.20),         # first ENTHUSIAST plate
    "enth_step": 4,                   # frames between plates
    "sweep_all": (sec(25.45), sec(26.55)),
    "hero_impact": sec(29.80),
    "fade": (sec(32.0), N_FRAMES - 1),
}
TITLE["enth_slams"] = [TITLE["enth_first"] + i * TITLE["enth_step"] for i in range(10)]

# Title sub-cameras inside s13 (first frame of each camera)
TITLE_CAMS = [
    ("cam_M", sec(19.0)),
    ("cam_A", sec(19.6)),
    ("cam_S1", sec(20.2)),
    ("cam_S2", sec(20.8)),
    ("cam_wide", sec(21.4)),
    ("cam_enth", sec(23.0)),
    ("cam_pull", sec(25.0)),
]


def shot_of(frame: int) -> str:
    for sid, a, b, _ in SHOTS:
        if a <= frame <= b:
            return sid
    return SHOTS[-1][0]


# ----------------------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(a, b, x):
    t = clamp((x - a) / (b - a)) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def ease_in_out(t):
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_cubic(t):
    t = clamp(t)
    return t ** 3


def ease_out_expo(t):
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_expo(t):
    t = clamp(t)
    return 0.0 if t <= 0 else 2 ** (10 * (t - 1))


def damped_spring(t, freq=6.0, damp=5.0):
    """Overshooting settle 0->1 (t in seconds)."""
    if t <= 0:
        return 0.0
    return 1 - math.exp(-damp * t) * math.cos(2 * math.pi * freq * t)


def value_noise_1d(x: float, seed: int = 0) -> float:
    """Smooth deterministic noise in [-1, 1]."""
    def h(i):
        n = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
        n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0
    i = math.floor(x)
    f = x - i
    u = f * f * (3 - 2 * f)
    return h(i) * (1 - u) + h(i + 1) * u


def fbm_1d(x: float, seed: int = 0, octaves: int = 3) -> float:
    s, a, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        s += a * value_noise_1d(x * (2 ** o), seed + o * 17)
        tot += a
        a *= 0.5
    return s / tot
