"""Default color tail: WB -> tone -> filter -> G+diff -> RL -> quantize.

See docs/ALGORITHM.md for formulas and docs/LEGAL.md for provenance.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from .types import RawImage, Settings
from .filter import filter_plane, filter_parameters
from .rl import deconvolve_luma, rl_sigma
from .tone import tone_luts

F = np.float32
StageCallback = Callable[[str, np.ndarray], None]


def wb_ratios(wb: tuple[float, float, float]) -> np.ndarray:
    a = np.asarray(wb, dtype=np.float32)
    if a.shape != (3,) or np.any(a <= 0) or not np.isfinite(a).all():
        raise ValueError("wb must be three finite positive values")
    return a / np.max(a)


def quantize_u16(v: np.ndarray) -> np.ndarray:
    return np.floor(np.clip(np.asarray(v, dtype=np.float32), F(0), F(1)) * F(65535) + F(.5)).astype(np.uint16)


def run_tail(
    rgb16: np.ndarray,
    raw: RawImage,
    settings: Settings,
    stage_callback: StageCallback | None = None,
    *, chunk_rows: int = 16,
) -> np.ndarray:
    """Apply the default color tail. Returns uint16 H x W x 3.

    The input is the already black-corrected HiFi RGB16 stage. Source levels
    remain provenance and are never applied again. Callbacks borrow mutable
    working arrays; copy a stage if it needs to survive the next callback.
    """
    settings.validate()
    if settings.algorithm != 'hifi':
        raise NotImplementedError("the default tail is validated for HiFi only")
    if (rgb16.dtype != np.uint16 or rgb16.ndim != 3 or rgb16.shape[-1] != 3
            or rgb16.shape[:2] != raw.processing_size[::-1]):
        raise ValueError("tail input must be post-HiFi uint16 HWC RGB at the processing size")
    if type(chunk_rows) is not int or chunk_rows < 1:
        raise ValueError("chunk_rows must be a positive integer")
    wb = settings.wb if settings.wb is not None else raw.wb
    if wb is None:
        raise ValueError("wb metadata or an explicit wb setting is required")
    ratios = wb_ratios(wb)
    if raw.iso is None:
        raise ValueError("iso metadata is required")
    if raw.pixel_scale is None:
        raise ValueError("pixel_scale metadata is required")
    h, w, _ = rgb16.shape
    A, B = filter_parameters(raw.iso, h * w)
    sigma = rl_sigma(raw.width, raw.pixel_scale, raw.iso)
    forward, inverse = tone_luts(float(max(wb)))

    def emit(name, array):
        if stage_callback is not None:
            stage_callback(name, array)

    a = rgb16.astype(np.float32) * F(1 / 65535)
    emit('normalized', a)
    for top in range(0, h, chunk_rows):
        weighted = a[top:top + chunk_rows] * ratios
        a[top:top + chunk_rows] = forward[quantize_u16(weighted)].astype(np.float32) / F(65535)
    emit('weighted_tone', a)
    for channel in (1, 0, 2):
        a[..., channel] = filter_plane(a[..., channel], A, B, chunk_rows=chunk_rows)
    emit('filtered_rgb', a)
    for top in range(0, h, chunk_rows):
        block = a[top:top + chunk_rows]
        green = block[..., 1].copy()
        red = (block[..., 0] - green) * F(.5) + F(.5)
        blue = (block[..., 2] - green) * F(.5) + F(.5)
        block[..., 0], block[..., 1], block[..., 2] = green, red, blue
    emit('default_diff', a)
    if sigma is not None:
        a[..., 0] = deconvolve_luma(a[..., 0], sigma, chunk_rows=chunk_rows)
    emit('default_deconvolved', a)
    for top in range(0, h, chunk_rows):
        block = a[top:top + chunk_rows]
        green = block[..., 0].copy()
        red = green + (F(2) * block[..., 1] - F(1))
        blue = green + (F(2) * block[..., 2] - F(1))
        block[..., 0], block[..., 1], block[..., 2] = red, green, blue
        block[:] = inverse[quantize_u16(block)].astype(np.float32) / F(65535)
        block *= F(1) / ratios
    emit('rgb_linear', a)
    result = np.empty(rgb16.shape, np.uint16)
    for top in range(0, h, chunk_rows):
        result[top:top + chunk_rows] = quantize_u16(a[top:top + chunk_rows])
    emit('quantized', result)
    return result
