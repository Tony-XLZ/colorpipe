"""CFA normalization: black/white -> float32 RGB planes.

This front-end stage uses per-channel black/white and floor-averaged green
levels without an upper clamp. The reference's 0x31560 is a later RGB stage;
it must not be applied again to the already prepared HiFi output.
"""

from __future__ import annotations

import numpy as np

from .types import RawImage

# 2x2 RGGB channel index: 0=R, 1=G, 2=B
_RGGB = np.array([[0, 1], [1, 2]], dtype=np.int8)


def _pattern_map(pattern: str) -> np.ndarray:
    base = _RGGB
    if pattern == "RGGB":
        return base
    if pattern == "BGGR":
        return np.array([[2, 1], [1, 0]], dtype=np.int8)
    if pattern == "GRBG":
        return np.array([[1, 0], [2, 1]], dtype=np.int8)
    if pattern == "GBRG":
        return np.array([[1, 2], [0, 1]], dtype=np.int8)
    raise ValueError(f"unsupported pattern: {pattern}")


def channel_black_white(raw: RawImage) -> tuple[np.ndarray, np.ndarray]:
    """Return per-channel black/white (R, G, B) using the reference G average."""
    b = np.array(
        [int(raw.black[0]), (int(raw.black[1]) + int(raw.black[2])) // 2, int(raw.black[3])],
        dtype=np.float64,
    )
    w = np.array(
        [int(raw.white[0]), (int(raw.white[1]) + int(raw.white[2])) // 2, int(raw.white[3])],
        dtype=np.float64,
    )
    return b, w


def normalize_cfa(cfa: np.ndarray, raw: RawImage) -> np.ndarray:
    """Return H x W x 3 float32, native CFA samples only; missing sites are 0.

    The demosaic stage is responsible for filling the missing sites. Keeping
    zeros here makes it explicit which samples are measured vs interpolated.
    """
    if cfa.ndim != 2 or cfa.dtype != np.uint16 or cfa.shape != raw.cfa.shape:
        raise ValueError("cfa must be uint16 with the full sensor shape")
    h, w = cfa.shape
    pmap = _pattern_map(raw.pattern)
    b, wht = channel_black_white(raw)
    k = 1.0 / (wht - b)

    out = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(2):
        for x in range(2):
            c = int(pmap[y, x])
            src = cfa[y::2, x::2].astype(np.float32)
            out[y::2, x::2, c] = np.maximum(src - np.float32(b[c]), 0) * np.float32(k[c])
    return out


def prepare_cfa16(normalized: np.ndarray, raw: RawImage) -> np.ndarray:
    """Quantize native samples once to the HiFi working range 0..65535.

    Linear normalization may exceed 1; clipping happens here. Missing channels
    must still be zero. This never subtracts the sensor black level again.
    """
    if normalized.shape != (*raw.cfa.shape, 3) or normalized.dtype != np.float32:
        raise ValueError("normalized CFA must be float32 H x W x 3")
    out = np.empty(raw.cfa.shape, dtype=np.uint16)
    pattern = _pattern_map(raw.pattern)
    for top in range(0, raw.height, 64):
        block = normalized[top:top + 64]
        if not np.isfinite(block).all() or np.any(block < 0):
            raise ValueError("normalized CFA must contain finite nonnegative values")
        for y in range(2):
            for x in range(2):
                c = int(pattern[(top + y) % 2, x])
                sites = block[y::2, x::2]
                if any(np.any(sites[..., other] != 0) for other in range(3) if other != c):
                    raise ValueError("normalized CFA contains nonzero missing channels")
                values = np.minimum(sites[..., c], np.float32(1)) * np.float32(65535)
                out[top + y:top + len(block):2, x::2] = np.floor(values + np.float32(.5)).astype(np.uint16)
    return out
