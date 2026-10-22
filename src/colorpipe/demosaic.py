"""Color demosaic: deterministic HiFi four-pass implementation.

See docs/ALGORITHM.md for the numerical contract and docs/LEGAL.md for
research provenance. Route B uses standard float32 and its own global
top-to-bottom recursive row order. v3 is unsupported.
"""

from __future__ import annotations

import numpy as np

from typing import Callable

from .types import RawImage, Settings
from .normalize import prepare_cfa16

F = np.float32
EPS = F(65535) * F(1e-5)
# Half of one 8-bit step in the 16-bit working domain. This uniform trust
# region bounds feedback corrections; it is not an acceptance threshold.
FEEDBACK_LIMIT = F(128)
StageCallback = Callable[[str, np.ndarray], None]


def _blend(a, b, cost_a, cost_b):
    """Inverse squared directional cost, expressed without reciprocal estimates."""
    wa, wb = cost_b * cost_b, cost_a * cost_a
    return (wa * a + wb * b) / (wa + wb)


def _green_initial(cfa, rows, cols):
    """Seven-pixel directional ratio stencil on regular R/B parity grids."""
    cache = {}

    def sample(dy, dx):
        key = dy, dx
        if key not in cache:
            y0, y1 = int(rows[0]) + dy, int(rows[-1]) + dy + 1
            x0, x1 = int(cols[0]) + dx, int(cols[-1]) + dx + 1
            if 0 <= y0 and y1 <= cfa.shape[0] and 0 <= x0 and x1 <= cfa.shape[1]:
                cache[key] = cfa[y0:y1:2, x0:x1:2].astype(np.float32)
                return cache[key]
            y, x = rows + dy, cols + dx
            if dy == -3:
                y = np.where(rows < 3, 1, y)
            elif dy == 3:
                y = np.where(y >= cfa.shape[0], rows + 1, y)
            if dx == -3:
                x = np.where(cols < 3, 1, x)
            elif dx == 3:
                x = np.where(x >= cfa.shape[1], cols + 1, x)
            cache[key] = cfa[y[:, None], x[None, :]].astype(np.float32)
        return cache[key]

    center = sample(0, 0)
    vertical = [sample(d, 0) for d in (-3, -2, -1, 1, 2, 3)]
    horizontal = [sample(0, d) for d in (-3, -2, -1, 1, 2, 3)]
    cross = (vertical[2] + vertical[3] + horizontal[2] + horizontal[3]) * F(.25)
    curvature = F(.5) * np.abs(center - (F(4) * center + vertical[1] + vertical[4]
                                         + horizontal[1] + horizontal[4]) * F(.125))
    diagonal = sum(sample(y, x) for y, x in ((-1, -1), (-1, 1), (1, -1), (1, 1)))
    far_corners = sum(sample(y, x) for y, x in ((-3, -3), (-3, 3), (3, -3), (3, 3)))
    near_corners = sum(sample(y, x) for y, x in ((-2, -2), (-2, 2), (2, -2), (2, 2)))
    knights = sum(sample(y, x) for y, x in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                                          (1, -2), (1, 2), (2, -1), (2, 1)))
    diagonal_ratio = ((EPS + F(8) * cross + knights) / (EPS + F(4) * diagonal)
                      * (diagonal + far_corners) + EPS) / (EPS + F(4) * center + near_corners)

    def axis(values):
        gm3, cm2, gm1, gp1, cp2, gp3 = values
        mean = (gm1 + gp1) * F(.5)
        middle_ratio = (gm1 + gp1 + EPS) / (F(2) * center + EPS)
        left_ratio = (F(2) * gm1 + EPS) / (center + cm2 + EPS)
        right_ratio = (F(2) * gp1 + EPS) / (center + cp2 + EPS)
        far_left_ratio = (gm3 + gm1 + EPS) / (F(2) * cm2 + EPS)
        far_right_ratio = (gp3 + gp1 + EPS) / (F(2) * cp2 + EPS)
        cost = (np.abs(far_left_ratio - left_ratio) + np.abs(left_ratio - middle_ratio)
                + F(2) * (np.abs(left_ratio - right_ratio) + F(1e-5))
                + np.abs(middle_ratio - right_ratio) + np.abs(far_right_ratio - right_ratio))
        broad_ratio = (gm3 + gp3 + gm1 + gp1 + EPS) / (cm2 + cp2 + F(2) * center + EPS)
        ratio = (left_ratio + right_ratio) * F(.5)
        reference = (broad_ratio + diagonal_ratio) * F(.5)
        scale = F(.5) * (cross + EPS) / (center + EPS)
        gcost_m = np.abs(gm3 - gm1) + np.abs(cross - gm1)
        gcost_p = np.abs(gp3 - gp1) + np.abs(cross - gp1)
        gw_m, gw_p = EPS / (gcost_m + EPS), EPS / (gcost_p + EPS)
        cw_m = EPS / ((np.abs(cm2 - center) + curvature) * scale + EPS)
        cw_p = EPS / ((np.abs(cp2 - center) + curvature) * scale + EPS)
        local_m = (gw_m * mean + cw_m * center) / (gw_m + cw_m)
        local_p = (gw_p * mean + cw_p * center) / (gw_p + cw_p)
        color_m = (gw_m * (gm1 + gm3) * F(.5) + cw_m * cm2) / (gw_m + cw_m)
        color_p = (gw_p * (gp1 + gp3) * F(.5) + cw_p * cp2) / (gw_p + cw_p)
        corrected_m = gm1 * (EPS + F(2) * local_m) / (EPS + color_m + local_m)
        corrected_p = gp1 * (EPS + F(2) * local_p) / (EPS + color_p + local_p)
        contrast = EPS + np.abs(gm1 - gp1)
        wm, wp = EPS / (contrast + gcost_m), EPS / (contrast + gcost_p)
        wc = EPS / (F(2) * contrast + np.abs(cross - mean))
        total = wm + wc + wp
        smooth = (wm * (gm1 + F(.2) * (mean - gm3)) + wc * mean
                  + wp * (gp1 + F(.2) * (mean - gp3))) / total
        estimate = (wm * corrected_m + wc * smooth + wp * corrected_p) / total
        return estimate, ratio, reference, cost

    av, rv, refv, cv = axis(vertical)
    ah, rh, refh, ch = axis(horizontal)
    ratio = _blend(rv, rh, cv + F(4) * np.abs(refv - diagonal_ratio),
                   ch + F(4) * np.abs(refh - diagonal_ratio))
    cv = cv + F(2) * (np.abs(rv - refv) + np.abs(rv - ratio))
    ch = ch + F(2) * (np.abs(rh - refh) + np.abs(rh - ratio))
    return np.clip(_blend(av, ah, cv, ch), 0, 65535).astype(np.uint16)


def _refine_green(rgb):
    """Bound a frozen/recursive midpoint around our canonical row sweep.

    The recursive trajectory always consumes its own unmodified preceding
    row, never a fused output. Keep that trajectory for pass4's color guard.
    Only one source row is needed to evaluate the frozen alternative.
    """
    green = rgb[..., 1]
    canonical = green.copy()
    height, width = green.shape
    previous_source = canonical[1].copy()
    for y in range(2, height - 2):
        x = np.arange(2 if y % 2 else 3, width - 2, 2)
        neighbors = [canonical[y + dy, x + dx].astype(np.float32)
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        frozen_neighbors = neighbors.copy()
        for i, dx in ((0, -1), (2, 1)):
            frozen_neighbors[i] = previous_source[x + dx].astype(np.float32)
        previous_source = canonical[y].copy()
        recursive = _green_refinement(neighbors)
        frozen = _green_refinement(frozen_neighbors)
        canonical[y, x] = recursive
        midpoint = (recursive.astype(np.float32) + frozen.astype(np.float32)) * F(.5)
        green[y, x] = _limit_feedback(recursive, midpoint)
    return canonical


def _limit_feedback(canonical, candidate):
    anchor = canonical.astype(np.float32)
    delta = candidate.astype(np.float32) - anchor
    return np.clip(anchor + np.clip(delta, -FEEDBACK_LIMIT, FEEDBACK_LIMIT), 0, 65535).astype(np.uint16)


def _green_refinement(neighbors):
    """Nine-point directional weights, shared by both feedback estimates."""
    center = neighbors[4]
    errors = [np.abs((neighbors[a] + neighbors[b]) * F(.5) - center)
              for a, b in ((0, 8), (1, 7), (2, 6), (3, 5))]
    center_weight = EPS / (F(.25) * np.minimum.reduce(errors) + EPS)
    numerator, denominator = center * center_weight, center_weight.copy()
    for i, direction in ((0, 0), (1, 1), (2, 2), (3, 3), (5, 3), (6, 2), (7, 1), (8, 0)):
        weight = EPS / (np.abs(neighbors[i] - center) + errors[direction] + EPS)
        numerator += weight * neighbors[i]
        denominator += weight
    return np.clip(numerator / denominator, 0, 65535).astype(np.uint16)


def _refine_green_rows(green, rows):
    """Apply the same local formula to complete rows of a caller-owned plane."""
    height, width = green.shape
    for y in rows:
        if not 2 <= y < height - 2:
            raise ValueError("refinement row lacks the initialized two-pixel halo")
        x = np.arange(2 if y % 2 else 3, width - 2, 2)
        if not len(x):
            continue
        neighbors = [green[y + dy, x + dx].astype(np.float32)
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        green[y, x] = _green_refinement(neighbors)


def _guided(center, greens, colors):
    weights = [EPS / (np.abs(g - center) + EPS) for g in greens]
    total = sum(weights)
    weights = [w / total for w in weights]
    guide = sum(w * g for w, g in zip(weights, greens))
    value = sum(w * c for w, c in zip(weights, colors))
    ratio = (center + EPS) / (EPS + F(.3) * center + F(.7) * guide)
    return np.clip(value * ratio, 0, 65535).astype(np.uint16)


def _fill_colors(rgb, cfa, pass_number, chunk_rows, *, canonical_green=None):
    height, width = rgb.shape[:2]
    for top in range(0, height, chunk_rows):
        for phase in range(2):
            rows = np.arange(top + ((phase - top) % 2), min(top + chunk_rows, height), 2)
            cols = np.arange(phase if pass_number == 3 else 1 - phase, width, 2)
            yy, xx = rows[:, None], cols[None, :]
            if not len(rows):
                continue
            edge = (yy < 2) | (xx < 2) | (yy > height - 2) | (xx > width - 2)
            center = rgb[yy, xx, 1].astype(np.float32)
            if pass_number == 3:
                offsets = ((-1, -1), (-1, 1), (1, -1), (1, 1))
                guides = [rgb[np.clip(yy + dy, 0, height - 1), np.clip(xx + dx, 0, width - 1), 1].astype(np.float32)
                          for dy, dx in offsets]
                guides = [np.where(edge, cfa[yy + 2 + 2 * dy, xx + 2 + dx], g).astype(np.float32)
                          for (dy, dx), g in zip(offsets, guides)]
                colors = [cfa[yy + 2 + dy, xx + 2 + dx].astype(np.float32) for dy, dx in offsets]
                rgb[yy, xx, 2 if phase == 0 else 0] = _guided(center, guides, colors)
            else:
                offsets = ((-1, 0), (0, -1), (0, 1), (1, 0))
                guides = [rgb[np.clip(yy + dy, 0, height - 1), np.clip(xx + dx, 0, width - 1), 1].astype(np.float32)
                          for dy, dx in offsets]
                for channel in (0, 2):
                    colors = [rgb[np.clip(yy + dy, 0, height - 1), np.clip(xx + dx, 0, width - 1), channel].astype(np.float32)
                              for dy, dx in offsets]
                    value = _guided(center, guides, colors)
                    if canonical_green is not None:
                        # Pass3 uses only non-G sites, whose G and R/B values
                        # are unchanged by pass2. Consequently this is the
                        # exact canonical color estimate without a second RGB
                        # pipeline. Bound amplification of the fused center.
                        anchor = _guided(canonical_green[yy, xx].astype(np.float32), guides, colors)
                        value = _limit_feedback(anchor, value)
                    horizontal = (channel == 0) == (phase == 0)
                    dy, dx = (0, 1) if horizontal else (1, 0)
                    fallback = (cfa[yy + 2 - dy, xx + 2 - dx].astype(np.uint32)
                                + cfa[yy + 2 + dy, xx + 2 + dx]) // 2
                    rgb[yy, xx, channel] = np.where(edge, fallback, value).astype(np.uint16)


def demosaic_hifi(rgb: np.ndarray, raw: RawImage, settings: Settings, *,
                  stage_callback: StageCallback | None = None, chunk_rows: int = 64) -> np.ndarray:
    """HiFi 26.5 color demosaic: 4 passes, output uint16 H x W x 3.

    Input is sparse normalized float32 on the full sensor domain. A single
    quantization establishes the 16-bit working range before four passes:
    directional ratio G initialization, bounded native G refinement, opposite R/B at
    non-G sites, then R/B at G sites. Output is cropped by two pixels per side.
    Callbacks borrow each stage array; copy it to retain an earlier stage.
    """
    settings.validate()
    if settings.algorithm != "hifi" or raw.pattern != "RGGB" or raw.crop != (2, 2, 2, 2):
        raise ValueError("HiFi requires RGGB and a two-pixel boundary")
    if min(raw.cfa.shape) < 8 or any(size % 2 for size in raw.cfa.shape):
        raise ValueError("HiFi requires even sensor dimensions of at least 8")
    if not isinstance(chunk_rows, int) or chunk_rows < 1:
        raise ValueError("chunk_rows must be a positive integer")

    def emit(name, array):
        if stage_callback is not None:
            stage_callback(name, array)

    prepared = prepare_cfa16(rgb, raw)
    emit("prepared_cfa", prepared)
    height, width = raw.cfa.shape
    result = np.zeros((height - 4, width - 4, 3), dtype=np.uint16)
    for y, x, channel in ((0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 2)):
        result[y::2, x::2, channel] = prepared[2 + y:height - 2:2, 2 + x:width - 2:2]
    for top in range(2, height - 2, chunk_rows):
        for phase in range(2):
            rows = np.arange(top + ((phase - top) % 2), min(top + chunk_rows, height - 2), 2)
            if len(rows):
                cols = np.arange(2 + phase, width - 2, 2)
                result[(rows - 2)[:, None], (cols - 2)[None, :], 1] = _green_initial(prepared, rows, cols)
    emit("pass1", result)
    canonical_green = _refine_green(result)
    emit("pass2", result)
    _fill_colors(result, prepared, 3, chunk_rows)
    emit("pass3", result)
    _fill_colors(result, prepared, 4, chunk_rows, canonical_green=canonical_green)
    emit("pass4", result)
    return result


def demosaic_v3(rgb: np.ndarray, raw: RawImage, settings: Settings) -> np.ndarray:
    """v3 More Detailed / Smoother (6 passes); optional v1.1."""
    raise NotImplementedError(
        "Implement v3 6-pass after HiFi is green. See demosaic_v3/README.md and v3.py."
    )


def demosaic(rgb: np.ndarray, raw: RawImage, settings: Settings, *,
             stage_callback: StageCallback | None = None, chunk_rows: int = 64) -> np.ndarray:
    settings.validate()
    if settings.algorithm == "hifi":
        return demosaic_hifi(rgb, raw, settings, stage_callback=stage_callback, chunk_rows=chunk_rows)
    if settings.algorithm == "v3":
        return demosaic_v3(rgb, raw, settings)
    raise ValueError(f"unknown algorithm: {settings.algorithm}")
