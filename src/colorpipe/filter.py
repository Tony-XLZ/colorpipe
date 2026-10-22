"""Active-image 3x3 median-guided inverse-difference filter, portable float32."""

import numpy as np

F = np.float32


def _sort_five(values):
    """Sort five finite planes elementwise, without per-pixel small sorts."""
    values = list(values)
    for left, right in ((0, 1), (3, 4), (2, 4), (2, 3), (1, 4),
                        (0, 3), (0, 2), (1, 3), (1, 2)):
        a, b = values[left], values[right]
        values[left], values[right] = np.minimum(a, b), np.maximum(a, b)
    return values


def filter_parameters(iso: int, pixels: int) -> tuple[np.float32, np.float32]:
    """The small-image ISO adjustment affects filtering, not the RL cutoff."""
    if type(iso) is not int or iso <= 0 or type(pixels) is not int or pixels <= 0:
        raise ValueError("iso and pixels must be positive integers")
    effective_iso = iso * (2 if pixels < 17_000_000 else 1)
    scale = 6.73
    for ceiling, value in ((200, 1), (400, 1.19), (800, 1.41), (1600, 1.68),
                           (3200, 2), (6400, 2.38), (12800, 2.83), (25600, 3.36),
                           (51200, 4), (102400, 4.76), (204800, 5.66)):
        if effective_iso <= ceiling:
            scale = value
            break
    return F(4096) / F(scale), F(.25) / F(scale)


def filter_plane(plane: np.ndarray, A: float, B: float, *, chunk_rows: int = 32) -> np.ndarray:
    """Read a fixed plane; replicate physical image edges, never chunk edges."""
    a = np.asarray(plane)
    if a.ndim != 2 or min(a.shape) < 2 or a.dtype != np.float32:
        raise ValueError("filter input must be a float32 plane of at least 2x2")
    if type(chunk_rows) is not int or chunk_rows < 1:
        raise ValueError("chunk_rows must be a positive integer")
    if not np.isfinite([A, B]).all() or min(A, B) <= 0:
        raise ValueError("A and B must be finite and positive")
    h, w = a.shape
    result = np.empty_like(a)
    epsilon = F(1) / F(A)
    # Check each source sample once, before any filtering can produce warnings.
    for top in range(0, h, chunk_rows):
        block = a[top:top + chunk_rows]
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError("filter input must be finite and within 0..1")
    for top in range(0, h, chunk_rows):
        stop = min(top + chunk_rows, h)
        source = a[max(0, top - 1):min(h, stop + 1)]
        padded = np.pad(source, ((int(top == 0), int(stop == h)), (1, 1)), mode='edge')
        n = [padded[y:y + stop - top, x:x + w] for y in range(3) for x in range(3)]
        center = n[4]
        cross = _sort_five(n[i] for i in (1, 3, 4, 5, 7))
        diagonal = _sort_five(n[i] for i in (0, 2, 4, 6, 8))
        mc, md = cross[2], diagonal[2]
        choose_diagonal = np.abs(center - md) < np.abs(center - mc)
        median = np.where(choose_diagonal, md, mc)
        second_high = np.where(choose_diagonal, diagonal[3], cross[3])
        second_low = np.where(choose_diagonal, diagonal[1], cross[1])
        bright = (center == cross[4]) & (center == diagonal[4])
        dark = (center == cross[0]) & (center == diagonal[0]) & ~bright
        replacement = np.where(bright, (F(2) * median + second_high) / F(3),
                               np.where(dark, (F(2) * median + second_low) / F(3), center))
        discrepancy = np.maximum(np.abs(center - replacement) - np.abs(mc - md), F(0))
        fraction = np.minimum(discrepancy / F(B), F(1))
        guide = replacement * fraction + center * (F(1) - fraction)
        weights = [F(1) / (epsilon + np.abs(value - guide)) for value in n]
        total = sum(weights)
        filtered = sum(value * weight for value, weight in zip(n, weights)) / total
        result[top:stop] = np.clip(filtered, 0, 1)
    return result
