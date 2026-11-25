"""Named colours that are far apart in CIELAB space.

Colour names appear in questions ("How many *teal* objects?"), so two colours
must never be confusable, for a person, a model or the pixel verifier. Every pair below
is at least ~20 ΔE76 apart (``tests/test_palette.py`` enforces it).
"""
from __future__ import annotations

import numpy as np

NAMED: dict[str, tuple[int, int, int]] = {
    "red": (220, 38, 38),
    "orange": (245, 140, 20),
    "yellow": (240, 205, 20),
    "green": (34, 160, 70),
    "teal": (20, 170, 170),
    "blue": (37, 99, 235),
    "purple": (130, 60, 200),
    "pink": (236, 110, 180),
    "brown": (130, 80, 40),
    "gray": (128, 128, 128),
}

INK = (31, 41, 55)          # axis / text colour
GRID = (226, 232, 240)      # light grid lines
PAPER = (255, 255, 255)
WALL = (30, 35, 45)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Vectorised sRGB (0-255) -> CIELAB (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def delta_e(a, b) -> float:
    return float(np.linalg.norm(srgb_to_lab(np.array(a)) - srgb_to_lab(np.array(b))))


def blend_fit(img: np.ndarray, rgb, bg=PAPER) -> tuple[np.ndarray, np.ndarray]:
    """(alpha, residual) of modelling each pixel as bg + alpha*(rgb-bg)."""
    p = np.asarray(img, dtype=np.float32)[..., :3]
    b = np.array(bg, dtype=np.float32)
    d = np.array(rgb, dtype=np.float32) - b
    q = p - b
    alpha = (q @ d) / float(d @ d)
    r = q - alpha[..., None] * d
    resid = np.sqrt(np.einsum("...c,...c->...", r, r))
    return np.clip(alpha, 0.0, 1.0), resid


def exclusive_coverage(img: np.ndarray, palette: dict[str, tuple], max_residual: float = 40.0,
                       bg=PAPER) -> dict[str, np.ndarray]:
    """Coverage per palette colour where each pixel is assigned to the single
    colour whose blend-with-background model explains it best. This stops the
    anti-aliased rim of a brown object from also counting as 'gray'."""
    names = list(palette)
    fits = [blend_fit(img, palette[n], bg) for n in names]
    resid = np.stack([f[1] for f in fits])
    best = resid.argmin(axis=0)
    out = {}
    for i, n in enumerate(names):
        a = fits[i][0].copy()
        a[(best != i) | (fits[i][1] > max_residual)] = 0.0
        out[n] = a
    return out


def coverage(img: np.ndarray, rgb: tuple[int, int, int], bg=PAPER, max_residual: float = 45.0) -> np.ndarray:
    """Per-pixel coverage (0..1) of colour ``rgb`` blended over ``bg``.

    Anti-aliasing mixes a thin stroke with the background, so a 2.6px line at a
    sub-pixel offset may never produce a pixel close to its pure colour. We model
    each pixel as ``bg + alpha * (rgb - bg)`` and solve for alpha; pixels that are
    far from that blend line (another colour) get coverage 0.
    """
    p = np.asarray(img, dtype=np.float64)[..., :3]
    b = np.array(bg, dtype=np.float64)
    d = np.array(rgb, dtype=np.float64) - b
    alpha = ((p - b) @ d) / float(d @ d)
    resid = np.linalg.norm(p - (b + alpha[..., None] * d), axis=-1)
    alpha = np.clip(alpha, 0.0, 1.0)
    alpha[resid > max_residual] = 0.0
    return alpha


def color_mask(img: np.ndarray, rgb: tuple[int, int, int], max_de: float = 14.0,
               lab: np.ndarray | None = None) -> np.ndarray:
    """Boolean mask of pixels within ``max_de`` of ``rgb``."""
    if lab is None:
        lab = srgb_to_lab(img[..., :3])
    target = srgb_to_lab(np.array(rgb, dtype=np.float64))
    return np.linalg.norm(lab - target, axis=-1) <= max_de
