"""Draws the website's icons and link-preview picture from the brand mark.

Needs nothing beyond Python itself. Run from the website folder:

    python3 -I scripts/icons.py

It writes public/icons/*.png and public/brand/social-card.png. The mark is the
one in public/brand/mark.svg (three round strokes: two threads joining one
line), on the brand blue. Commit the files it writes.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BLUE = (0x0D, 0x4E, 0xD6)
PAPER = (0xF7, 0xF8, 0xFA)
WHITE = (0xFF, 0xFF, 0xFF)
PUBLIC = Path(__file__).resolve().parent.parent / "public"

# The mark's strokes in the icon's 64-unit space (from threadline-icon.svg):
# three paths, the curved ones flattened into short segments.
_SCALE = 0.1704
_SHIFT = (11.6 - 159 * _SCALE, 20.6 - 214 * _SCALE)
_STROKE = 24 * _SCALE


def _point(x: float, y: float) -> tuple[float, float]:
    return (x * _SCALE + _SHIFT[0], y * _SCALE + _SHIFT[1])


def _cubic(p0, p1, p2, p3, steps: int = 32):
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        yield (
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        )


def _mark_polylines() -> list[list[tuple[float, float]]]:
    top = [_point(159, 214), _point(182, 214)] + [_point(*p) for p in _cubic((182, 214), (222, 214), (228, 281), (268, 281))]
    bottom = [_point(159, 348), _point(182, 348)] + [_point(*p) for p in _cubic((182, 348), (222, 348), (228, 281), (268, 281))]
    line = [_point(159, 281), _point(397, 281)]
    return [top, bottom, line]


def _segment_distance(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _stroke_distance(p, polylines) -> float:
    best = math.inf
    for line in polylines:
        for a, b in zip(line, line[1:]):
            best = min(best, _segment_distance(p, a, b))
    return best


def _rounded_rect_distance(p, size: float, radius: float) -> float:
    """Signed distance to a rounded square of `size` at the origin; negative inside."""
    half = size / 2
    qx = abs(p[0] - half) - half + radius
    qy = abs(p[1] - half) - half + radius
    outside = math.hypot(max(qx, 0), max(qy, 0))
    inside = min(max(qx, qy), 0)
    return outside + inside - radius


def _coverage(distance: float, pixels_per_unit: float) -> float:
    """How much of a pixel lies on the drawn side of an edge `distance` units away."""
    edge = distance * pixels_per_unit
    return max(0.0, min(1.0, 0.5 - edge))


def _blend(under, over, alpha: float):
    return tuple(round(u + (o - u) * alpha) for u, o in zip(under, over))


def draw_icon(size: int, *, full_square: bool, mark_scale: float = 1.0) -> bytes:
    """One icon: the mark on the blue square, rounded or filling the whole file."""
    pixels_per_unit = size / 64
    polylines = _mark_polylines()
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            u = ((x + 0.5) / pixels_per_unit - 32) / mark_scale + 32
            v = ((y + 0.5) / pixels_per_unit - 32) / mark_scale + 32
            square = 1.0 if full_square else _coverage(_rounded_rect_distance((u, v), 64, 14), pixels_per_unit * mark_scale)
            mark = _coverage(_stroke_distance((u, v), polylines) - _STROKE / 2, pixels_per_unit * mark_scale)
            colour = _blend(BLUE, WHITE, mark)
            alpha = round(255 * square)
            row += bytes(colour) + bytes([alpha])
        rows.append(bytes(row))
    return _encode_png(size, size, rows)


def draw_social_card(width: int = 1200, height: int = 630) -> bytes:
    """The link-preview picture: the icon, large, centred on paper."""
    icon = 320
    left, top = (width - icon) // 2, (height - icon) // 2
    pixels_per_unit = icon / 64
    polylines = _mark_polylines()
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            u = (x - left + 0.5) / pixels_per_unit
            v = (y - top + 0.5) / pixels_per_unit
            square = _coverage(_rounded_rect_distance((u, v), 64, 14), pixels_per_unit)
            mark = _coverage(_stroke_distance((u, v), polylines) - _STROKE / 2, pixels_per_unit) if square > 0 else 0.0
            colour = _blend(PAPER, _blend(BLUE, WHITE, mark), square)
            row += bytes(colour) + b"\xff"
        rows.append(bytes(row))
    return _encode_png(width, height, rows)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _encode_png(width: int, height: int, rows: list[bytes]) -> bytes:
    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def main() -> None:
    icons = PUBLIC / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "icon-512.png").write_bytes(draw_icon(512, full_square=False))
    (icons / "icon-192.png").write_bytes(draw_icon(192, full_square=False))
    (icons / "apple-touch-icon-180.png").write_bytes(draw_icon(180, full_square=True))
    (icons / "icon-maskable-512.png").write_bytes(draw_icon(512, full_square=True, mark_scale=0.8))
    (PUBLIC / "brand" / "social-card.png").write_bytes(draw_social_card())


if __name__ == "__main__":
    main()
