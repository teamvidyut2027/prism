"""Deterministic image degradations, plus a check that the answer survives them.

A perturbed image is only admitted if the independent verifier can still
recover *exactly the same facts* from it after a light 3x3 median clean-up.
That keeps robustness scores honest: if a model fails on a perturbed image,
the information was provably still in the pixels.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

from ..core.rng import np_rng

KINDS = ("noise", "blur", "jpeg", "downscale")


def perturb(img: Image.Image, kind: str, strength: float, *seed) -> Image.Image:
    """strength in (0, 1]."""
    if kind == "noise":
        a = np.asarray(img, dtype=np.float32)
        a = a + np_rng(*seed, "noise").normal(0, 6 + 22 * strength, a.shape)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=0.6 + 1.2 * strength))
    if kind == "jpeg":
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=int(55 - 40 * strength))
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if kind == "downscale":
        f = 0.75 - 0.3 * strength
        w, h = img.size
        return img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.BILINEAR).resize((w, h), Image.BICUBIC)
    raise ValueError(kind)


def recoverable_view(img: Image.Image) -> np.ndarray:
    """What the verifier looks at for a perturbed image."""
    return np.asarray(img.filter(ImageFilter.MedianFilter(3)))
