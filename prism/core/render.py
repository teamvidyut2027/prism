"""Rendering helpers.

Scenes are drawn on a 2x supersampled canvas and downsampled with a Lanczos
filter, which gives anti-aliased, publication-quality images while staying
fully deterministic (bundled fonts, no system font lookup, no wall clock).
All public coordinates are in *final* image pixels.
"""
from __future__ import annotations

import hashlib
import io
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from .palette import PAPER

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SS = 2  # supersampling factor


def text_engine() -> str:
    """Pillow's text shaper. Byte-identical renders across machines need the same one: the committed
    benchmark was built with Raqm (HarfBuzz kerning). On Linux, Raqm needs libfribidi (the Docker image has it)."""
    return "raqm" if features.check("raqm") else "basic"


_LAYOUT = ImageFont.Layout.RAQM if text_engine() == "raqm" else ImageFont.Layout.BASIC


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSansMono.ttf" if mono else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return ImageFont.truetype(str(FONT_DIR / name), size, layout_engine=_LAYOUT)


class Canvas:
    def __init__(self, width: int, height: int, bg=PAPER):
        self.width, self.height = width, height
        self.img = Image.new("RGB", (width * SS, height * SS), bg)
        self.draw = ImageDraw.Draw(self.img)

    # --- primitives (final-pixel coordinates) -------------------------------
    @staticmethod
    def _s(v):
        return v * SS

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1, radius=0):
        box = [self._s(x0), self._s(y0), self._s(x1), self._s(y1)]
        if radius:
            self.draw.rounded_rectangle(box, radius=self._s(radius), fill=fill, outline=outline,
                                        width=max(1, round(self._s(width))) if outline else 0)
        else:
            self.draw.rectangle(box, fill=fill, outline=outline, width=max(1, round(self._s(width))) if outline else 0)

    def line(self, pts, fill, width=1, joint="curve"):
        self.draw.line([(self._s(x), self._s(y)) for x, y in pts], fill=fill, width=max(1, round(self._s(width))),
                       joint=joint)

    def ellipse(self, cx, cy, r, fill=None, outline=None, width=1):
        self.draw.ellipse([self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
                          fill=fill, outline=outline, width=max(1, round(self._s(width))) if outline else 0)

    def polygon(self, pts, fill=None, outline=None):
        self.draw.polygon([(self._s(x), self._s(y)) for x, y in pts], fill=fill, outline=outline)

    def text(self, x, y, s, size=14, fill=(31, 41, 55), anchor="la", bold=False, mono=False, angle=0):
        f = font(self._s(size), bold=bold, mono=mono)
        if angle == 0:
            self.draw.text((self._s(x), self._s(y)), s, font=f, fill=fill, anchor=anchor)
            return
        # rotated text: draw on a transparent tile, rotate, paste centred at (x, y)
        l, t, r, b = self.draw.textbbox((0, 0), s, font=f, anchor="lt")
        tile = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((2, 2), s, font=f, fill=fill, anchor="lt")
        tile = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
        px, py = self._s(x), self._s(y)
        if anchor.startswith("r"):
            px -= tile.width
        elif anchor.startswith("m"):
            px -= tile.width // 2
        py -= tile.height // 2
        self.img.paste(tile, (int(px), int(py)), tile)

    def text_size(self, s, size=14, bold=False, mono=False) -> tuple[float, float]:
        f = font(self._s(size), bold=bold, mono=mono)
        l, t, r, b = self.draw.textbbox((0, 0), s, font=f, anchor="lt")
        return (r - l) / SS, (b - t) / SS

    def finish(self) -> Image.Image:
        return self.img.resize((self.width, self.height), Image.LANCZOS)


def regular_polygon(cx, cy, r, n, rotation_deg=0.0) -> list[tuple[float, float]]:
    rot = math.radians(rotation_deg)
    return [(cx + r * math.cos(rot + 2 * math.pi * i / n - math.pi / 2),
             cy + r * math.sin(rot + 2 * math.pi * i / n - math.pi / 2)) for i in range(n)]


def star(cx, cy, r, points=5, inner=0.45, rotation_deg=0.0) -> list[tuple[float, float]]:
    rot = math.radians(rotation_deg)
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = rot + math.pi * i / points - math.pi / 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


# --- image identity -----------------------------------------------------------
def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    # fixed, metadata-free encoding so the bytes are reproducible
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def sha256(img: Image.Image) -> str:
    return hashlib.sha256(np.asarray(img.convert("RGB")).tobytes()).hexdigest()


def dhash(img: Image.Image, size: int = 8) -> str:
    """64-bit difference hash, used for near-duplicate detection."""
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return "%0*x" % (size * size // 4, int("".join("1" if b else "0" for b in bits), 2))


def hamming(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")
