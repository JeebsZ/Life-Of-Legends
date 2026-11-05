"""Original line-drawn sigils for Life of Legends effects.

Every glyph here is invented for this app: short polylines in a unit box (-0.5..0.5, y down).
They are not letters from any real script or show. Effects stamp them onto a Canvas Path, so a
whole ring of glyphs costs one Canvas shape.
"""

from __future__ import annotations

import math
import random

import flet.canvas as cv

Pt = tuple[float, float]
Glyph = list[list[Pt]]

# 16 invented sigils: angular hooks, bars and nodes. Drawn by hand for this app.
GLYPHS: list[Glyph] = [
    [[(-.4, .5), (-.4, -.5), (.4, -.5)], [(-.4, 0), (.2, 0)], [(.4, -.1), (.4, .5)]],
    [[(-.4, -.5), (.4, -.5), (0, .5), (-.4, -.5)], [(0, -.5), (0, .1)]],
    [[(-.4, .5), (0, -.5), (.4, .5)], [(-.2, .1), (.2, .1)], [(-.4, -.5), (-.2, -.5)]],
    [[(.4, -.5), (-.4, -.5), (-.4, .5), (.4, .5)], [(0, -.2), (0, .2)]],
    [[(-.4, -.3), (0, -.5), (.4, -.3), (.4, .3), (0, .5)], [(-.4, .1), (.1, .1)]],
    [[(-.4, -.5), (-.4, .5)], [(.4, -.5), (.4, .5)], [(-.4, -.1), (.4, .2)]],
    [[(-.4, -.5), (.4, .5)], [(-.4, .5), (0, 0)], [(.1, -.5), (.4, -.5)]],
    [[(0, -.5), (.4, 0), (0, .5), (-.4, 0), (0, -.5)], [(0, -.15), (0, .15)]],
    [[(-.4, -.5), (.4, -.5)], [(0, -.5), (0, .5)], [(-.3, .5), (.3, .5)], [(-.4, 0), (-.15, 0)]],
    [[(-.4, .5), (-.4, -.2), (0, -.5), (.4, -.2)], [(.4, .1), (.4, .5)]],
    [[(-.4, -.4), (.4, -.4)], [(-.4, 0), (.4, 0)], [(-.4, .4), (.4, .4)], [(0, -.4), (0, 0)]],
    [[(-.4, .5), (-.4, -.5), (.4, .5), (.4, -.5)]],
    [[(-.4, 0), (.4, 0)], [(0, -.5), (0, .5)], [(-.4, -.5), (-.4, -.3)], [(.4, .3), (.4, .5)]],
    [[(.4, -.5), (-.2, -.5), (-.4, -.2), (-.2, 0), (.2, 0), (.4, .2), (.2, .5), (-.4, .5)]],
    [[(-.4, -.5), (.4, -.5), (.4, .5)], [(-.4, -.1), (.1, -.1), (.1, .5)]],
    [[(-.4, .5), (.4, -.5)], [(-.4, -.5), (-.1, -.2)], [(.1, .2), (.4, .5)]],
]


def glyph_elements(index: int, cx: float, cy: float, size: float,
                   angle: float = 0.0) -> list[cv.Path.PathElement]:
    """Path elements for glyph `index` centred on (cx, cy), `size` px tall, rotated `angle` rad
    (clockwise, screen coords)."""
    ca, sa = math.cos(angle), math.sin(angle)
    out: list[cv.Path.PathElement] = []
    for line in GLYPHS[index % len(GLYPHS)]:
        for i, (x, y) in enumerate(line):
            px = cx + (x * ca - y * sa) * size
            py = cy + (x * sa + y * ca) * size
            out.append(cv.Path.MoveTo(px, py) if i == 0 else cv.Path.LineTo(px, py))
    return out


def ring_elements(cx: float, cy: float, radius: float, count: int, size: float,
                  seed: int = 0, phase: float = 0.0) -> list[cv.Path.PathElement]:
    """A ring of `count` glyphs around (cx, cy), each glyph's top facing outward."""
    rnd = random.Random(seed)
    out: list[cv.Path.PathElement] = []
    for i in range(count):
        th = phase + 2 * math.pi * i / count
        x, y = cx + radius * math.cos(th), cy + radius * math.sin(th)
        out += glyph_elements(rnd.randrange(len(GLYPHS)), x, y, size, th + math.pi / 2)
    return out


def word_elements(x: float, cy: float, count: int, size: float, gap: float = 0.35,
                  seed: int = 0) -> list[cv.Path.PathElement]:
    """A short horizontal 'word' of glyphs starting at x (decorative caption lines)."""
    rnd = random.Random(seed)
    out: list[cv.Path.PathElement] = []
    step = size * (0.8 + gap)
    for i in range(count):
        out += glyph_elements(rnd.randrange(len(GLYPHS)), x + size / 2 + i * step, cy,
                              size * 0.8)
    return out


def circuit_elements(cx: float, cy: float, inner: float, outer: float, seed: int = 0,
                     lanes: tuple[float, ...] = (-0.6, 0.6),
                     ) -> tuple[list[cv.Path.PathElement], list[Pt]]:
    """Right-angle 'circuit' traces from an inner square (half-side `inner`) out toward
    a diamond (half-diagonal `outer`). `lanes`: trace start points along each square edge
    (-1..1). Returns (path elements, terminal points)."""
    rnd = random.Random(seed)
    els: list[cv.Path.PathElement] = []
    ends: list[Pt] = []
    for side in range(4):  # 0 top, 1 right, 2 bottom, 3 left
        for k in lanes:
            t = k * inner
            # start on the square edge, run outward, jog sideways, run out again
            run1 = rnd.uniform(0.18, 0.32) * (outer - inner)
            jog = (1 if k >= 0 else -1) * rnd.uniform(4, 9)  # bend away from the centre axis
            # stay inside the diamond: |x| + |y| <= outer at the trace tip
            room = outer - 7 - (abs(t + jog) + inner + run1 + abs(jog))
            run2 = max(2.0, rnd.uniform(0.45, 0.9) * room)
            pts: list[Pt] = [(t, -inner), (t, -inner - run1), (t + jog, -inner - run1 - abs(jog)),
                             (t + jog, -inner - run1 - abs(jog) - run2)]
            rot = side * math.pi / 2
            cr, sr = math.cos(rot), math.sin(rot)
            world = [(cx + x * cr - y * sr, cy + x * sr + y * cr) for x, y in pts]
            for i, (px, py) in enumerate(world):
                els.append(cv.Path.MoveTo(px, py) if i == 0 else cv.Path.LineTo(px, py))
            ends.append(world[-1])
    return els, ends
