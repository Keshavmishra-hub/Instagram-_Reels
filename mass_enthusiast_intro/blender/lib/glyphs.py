"""Custom letterforms for the MASS ENTHUSIAST title.

An original, angular heavy display face drawn from geometric primitives:
  * cap height = 1.0, heavy stems (~0.255) and slightly lighter bars (~0.21)
  * every convex corner is chamfered at 45 degrees; the top-left and bottom-right
    corners get a long "blade" chamfer, the others a small machining chamfer.
    The asymmetric cut gives the whole word a forward-leaning, forged feel.
  * the A has a triangular counter.

Only the nine glyphs the title needs are drawn: M A S E N T H U I.
Everything here is pure geometry (shapely), so the same outlines drive the 3D
models in Blender, the 2D previews and the compositor's spark emitters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely import affinity

BIG = 0.135     # blade chamfer (top-left / bottom-right corners)
SMALL = 0.026   # machining chamfer (all other convex corners)
HOLE = 0.022    # chamfer inside counters


# --------------------------------------------------------------------------- helpers
def _line_offset(p, v, d, n_sign=1):
    """Return a point on the line through p (direction v) shifted by distance d."""
    L = math.hypot(*v)
    n = (v[1] / L, -v[0] / L)
    return (p[0] + n_sign * d * n[0], p[1] + n_sign * d * n[1])


def _intersect_x(p, v, x):
    t = (x - p[0]) / v[0]
    return p[1] + t * v[1]


def _corner_size(prev, cur, nxt, is_hole, bbox=None):
    """Chamfer length for a convex corner.

    The long blade cut is reserved for the corners that sit at the glyph's top-left
    and bottom-right extremes; everything else gets a small machining chamfer.
    """
    if is_hole:
        return HOLE
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        near = 0.16
        tl = abs(cur[0] - x0) < near and abs(cur[1] - y1) < 1e-6
        br = abs(cur[0] - x1) < near and abs(cur[1] - y0) < 1e-6
        if not (tl or br):
            return SMALL
    a = (prev[0] - cur[0], prev[1] - cur[1])
    b = (nxt[0] - cur[0], nxt[1] - cur[1])
    la, lb = math.hypot(*a), math.hypot(*b)
    a = (a[0] / la, a[1] / la)
    b = (b[0] / lb, b[1] / lb)
    # outward bisector = -(a+b)
    bx, by = -(a[0] + b[0]), -(a[1] + b[1])
    if (bx < -0.2 and by > 0.2) or (bx > 0.2 and by < -0.2):
        return BIG
    return SMALL


def _chamfer_ring(coords, ccw_solid: bool, is_hole: bool, bbox=None):
    """Chamfer the convex corners (seen from the solid) of a closed ring."""
    pts = list(coords)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    out = []
    for i in range(n):
        prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = (cur[0] - prev[0], cur[1] - prev[1])
        e2 = (nxt[0] - cur[0], nxt[1] - cur[1])
        cross = e1[0] * e2[1] - e1[1] * e2[0]
        convex = cross > 1e-9 if ccw_solid else cross < -1e-9
        l1, l2 = math.hypot(*e1), math.hypot(*e2)
        if not convex or l1 < 1e-6 or l2 < 1e-6:
            out.append(cur)
            continue
        ang = math.degrees(math.acos(max(-1, min(1, -(e1[0] * e2[0] + e1[1] * e2[1]) / (l1 * l2)))))
        if ang > 150:          # nearly straight - nothing to cut
            out.append(cur)
            continue
        c = _corner_size(prev, cur, nxt, is_hole, bbox)
        if ang < 60:           # acute corners (A feet, M/N joins): keep the cut short
            c = min(c, SMALL)
        c = min(c, 0.45 * l1, 0.45 * l2)
        out.append((cur[0] - e1[0] / l1 * c, cur[1] - e1[1] / l1 * c))
        out.append((cur[0] + e2[0] / l2 * c, cur[1] + e2[1] / l2 * c))
    return out


def chamfer(poly: Polygon) -> Polygon:
    from shapely.geometry.polygon import orient
    poly = orient(poly, 1.0)  # exterior CCW, holes CW
    ext = _chamfer_ring(poly.exterior.coords, True, False, poly.bounds)
    holes = [_chamfer_ring(h.coords, False, True) for h in poly.interiors]
    return Polygon(ext, holes).buffer(0)


# --------------------------------------------------------------------------- glyphs
S_V = 0.255   # vertical stem
S_H = 0.212   # horizontal bar


def g_M():
    # stems + V; the V is defined by its top notch (yT) and bottom vertex (yV),
    # the inner edges of the stems meet the V's lower edges at yL.
    W, s, sT, yT, yV = 1.12, S_V, 0.31, 0.58, 0.13
    v = (W / 2 - sT, yT - 1.0)                      # direction of the upper edge
    yL = yV + (W / 2 - s) * (-v[1] / v[0])          # lower edge parallel, through (W/2, yV)
    pts = [(0, 0), (s, 0), (s, yL), (W / 2, yV), (W - s, yL), (W - s, 0), (W, 0), (W, 1),
           (W - sT, 1), (W / 2, yT), (sT, 1), (0, 1)]
    return Polygon(pts), W


def g_A():
    W, a, leg = 1.0, 0.115, 0.262
    k = W / 2 - a
    outer = Polygon([(0, 0), (W, 0), (W / 2 + a, 1), (W / 2 - a, 1)])
    yb0, yb1 = 0.185, 0.375   # crossbar bottom / top
    xl = lambda y: leg + y * k
    xr = lambda y: W - leg - y * k
    y_ap = (W - 2 * leg) / (2 * k)
    notch = Polygon([(xl(0), -0.01), (xr(0), -0.01), (xr(yb0), yb0), (xl(yb0), yb0)])
    counter = Polygon([(xl(yb1), yb1), (xr(yb1), yb1), (W / 2, y_ap)])
    return outer.difference(notch).difference(counter), W


def g_S():
    W, s, t, tm, ym, spur = 0.86, S_V, S_H, 0.205, 0.522, 0.105
    parts = [
        box(0, 1 - t, W, 1),                       # top bar
        box(0, ym - tm / 2, s, 1),                 # upper-left stem
        box(0, ym - tm / 2, W, ym + tm / 2),       # middle bar
        box(W - s, 0, W, ym + tm / 2),             # lower-right stem
        box(0, 0, W, t),                           # bottom bar
        box(W - s, 1 - t - spur, W, 1),            # top terminal spur
        box(0, 0, s, t + spur),                    # bottom terminal spur
    ]
    return unary_union(parts), W


def g_E():
    W, s, t = 0.72, S_V, S_H
    parts = [box(0, 0, s, 1), box(0, 1 - t, W, 1), box(0, 0.5 - t / 2, W * 0.9, 0.5 + t / 2), box(0, 0, W, t)]
    return unary_union(parts), W


def g_N():
    W, s, sT, d = 0.90, S_V, 0.305, 0.245

    def thickness(yQ):
        v = (W - s - sT, yQ - 1.0)
        L = math.hypot(*v)
        n = (-v[1] / L, v[0] / L)
        R = (s - sT, (1 - yQ) - 1.0)
        return abs(R[0] * n[0] + R[1] * n[1])

    lo, hi = 0.05, 0.95      # thickness grows with yQ on this interval
    for _ in range(60):
        mid = (lo + hi) / 2
        if thickness(mid) < d:
            lo = mid
        else:
            hi = mid
    yQ = (lo + hi) / 2
    pts = [(0, 0), (s, 0), (s, 1 - yQ), (W - sT, 0), (W, 0), (W, 1), (W - s, 1), (W - s, yQ), (sT, 1), (0, 1)]
    return Polygon(pts), W


def g_T():
    W, s, t = 0.80, S_V + 0.01, S_H + 0.01
    return unary_union([box(0, 1 - t, W, 1), box(W / 2 - s / 2, 0, W / 2 + s / 2, 1)]), W


def g_H():
    W, s, t = 0.87, S_V, S_H
    return unary_union([box(0, 0, s, 1), box(W - s, 0, W, 1), box(0, 0.5 - t / 2, W, 0.5 + t / 2)]), W


def g_U():
    W, s, t = 0.85, S_V, S_H + 0.02
    return unary_union([box(0, 0, s, 1), box(W - s, 0, W, 1), box(0, 0, W, t)]), W


def g_I():
    W = S_V + 0.01
    return box(0, 0, W, 1), W


GLYPHS = {"M": g_M, "A": g_A, "S": g_S, "E": g_E, "N": g_N, "T": g_T, "H": g_H, "U": g_U, "I": g_I}

# pair kerning (in cap-height units, applied on top of tracking)
KERN = {"MA": -0.05, "AS": -0.045, "IA": -0.03, "ST": -0.02, "NT": -0.015, "TH": -0.015}


@dataclass
class PlacedGlyph:
    char: str
    index: int          # index inside its word
    word: str
    poly: Polygon       # outline in lockup units (cap height of MASS = 1)
    inset: Polygon      # face plate outline
    groove_outer: Polygon
    x0: float
    x1: float
    scale: float        # cap height of this glyph


def glyph(char: str) -> tuple[Polygon, float]:
    poly, w = GLYPHS[char]()
    return chamfer(poly), w


def layout_word(word: str, cap: float, tracking: float):
    """Return [(char, poly_scaled, x0, x1)] with the baseline at y=0, starting at x=0."""
    out, x = [], 0.0
    for i, ch in enumerate(word):
        p, w = glyph(ch)
        p = affinity.scale(p, cap, cap, origin=(0, 0))
        p = affinity.translate(p, x, 0)
        out.append((ch, p, x, x + w * cap))
        x += w * cap
        if i < len(word) - 1:
            x += (tracking + KERN.get(word[i:i + 2], 0.0)) * cap
    return out, x


def lockup(gap=0.17, track_top=0.075, track_bottom=0.13):
    """MASS on top, ENTHUSIAST justified to the same width underneath.

    Returns placed glyphs centred on x=0, with the ENTHUSIAST baseline at y=0.
    """
    top, wt = layout_word("MASS", 1.0, track_top)
    # find the cap height that makes ENTHUSIAST exactly as wide as MASS
    _, w1 = layout_word("ENTHUSIAST", 1.0, track_bottom)
    cap2 = wt / w1
    bot, wb = layout_word("ENTHUSIAST", cap2, track_bottom)
    placed = []
    y_top = cap2 + gap
    for word, items, y0, cap in (("MASS", top, y_top, 1.0), ("ENTHUSIAST", bot, 0.0, cap2)):
        for i, (ch, p, x0, x1) in enumerate(items):
            p2 = affinity.translate(p, -wt / 2, y0)
            ins = p2.buffer(-0.047 * cap, join_style=2, mitre_limit=3.0)
            gro = p2.buffer(-0.034 * cap, join_style=2, mitre_limit=3.0)
            placed.append(PlacedGlyph(ch, i, word, p2, ins, gro, x0 - wt / 2, x1 - wt / 2, cap))
    height = y_top + 1.0
    return placed, wt, height, cap2


def rings(poly):
    """Iterate over every ring (exterior + holes) of a (multi)polygon as coordinate lists."""
    polys = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    for p in polys:
        yield list(p.exterior.coords)
        for h in p.interiors:
            yield list(h.coords)


def ring_length(coords):
    return sum(math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def point_on_ring(coords, u):
    """Point at normalised arc length u in [0,1] along a closed ring."""
    L = ring_length(coords)
    target = (u % 1.0) * L
    acc = 0.0
    for i in range(len(coords) - 1):
        seg = math.dist(coords[i], coords[i + 1])
        if acc + seg >= target and seg > 0:
            t = (target - acc) / seg
            return (coords[i][0] + t * (coords[i + 1][0] - coords[i][0]),
                    coords[i][1] + t * (coords[i + 1][1] - coords[i][1]))
        acc += seg
    return coords[-1]
