"""Deterministic, hierarchical seeding.

Every random decision is drawn from a ``random.Random`` whose seed is a hash of
a path such as ``(dataset_seed, family, index, "scene")``. That gives three
properties the factory relies on:

* the same inputs always produce byte-identical images and questions;
* adding a new family or question never shifts the randomness of others;
* any single task can be regenerated in isolation from its id.
"""
from __future__ import annotations

import hashlib
import random

import numpy as np


def derive_seed(*parts: object) -> int:
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big")


def rng(*parts: object) -> random.Random:
    return random.Random(derive_seed(*parts))


def np_rng(*parts: object) -> np.random.Generator:
    return np.random.default_rng(derive_seed(*parts))
