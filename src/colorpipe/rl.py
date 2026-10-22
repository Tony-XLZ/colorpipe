"""Two Richardson-Lucy iterations on luma with a formula-generated 3x3 PSF."""

import math

import numpy as np

F = np.float32


def rl_sigma(original_width: int, pixel_scale: float, iso: int) -> float | None:
    if type(original_width) is not int or original_width <= 0:
        raise ValueError("original_width must be a positive integer")
    if not math.isfinite(pixel_scale) or pixel_scale <= 0:
        raise ValueError("pixel_scale must be finite and positive")
    if type(iso) is not int or iso <= 0:
        raise ValueError("iso must be a positive integer")
    if iso >= 12800:
        return None
    size = original_width * pixel_scale / 4000
    sigma = .4 if size <= 1 else .2 * (math.sqrt(size) + 1)
    factor = next(value for ceiling, value in ((400, 1), (800, .9), (1600, .8),
                                              (3200, .7), (6400, .6), (12800, .5))
                  if iso <= ceiling)
    return sigma * factor


def gaussian_psf(sigma: float) -> np.ndarray:
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be finite and positive")
    y, x = np.indices((3, 3), dtype=np.float64) - 1
    kernel = np.exp(-(x * x + y * y) / (2 * sigma * sigma))
    return (kernel / kernel.sum()).astype(np.float32)


def _convolve(plane, kernel):
    padded = np.pad(plane, 1, mode='edge')
    h, w = plane.shape
    result = np.zeros_like(plane)
    for y in range(3):
        for x in range(3):
            result += kernel[y, x] * padded[y:y + h, x:x + w]
    return result


def deconvolve_luma(plane: np.ndarray, sigma: float, *, chunk_rows: int = 32) -> np.ndarray:
    """Extend the source once, then evolve that halo through both iterations.

    Four 3x3 convolutions have radius four. Independent row strips with that
    halo reproduce the full-image operation without reference tile geometry.
    """
    a = np.asarray(plane)
    if a.ndim != 2 or not a.size or a.dtype != np.float32:
        raise ValueError("RL input must be a nonempty float32 plane")
    if type(chunk_rows) is not int or chunk_rows < 1:
        raise ValueError("chunk_rows must be a positive integer")
    kernel = gaussian_psf(sigma)
    h, w = a.shape
    result = np.empty_like(a)
    halo, threshold = 4, F(.5 / 65535)
    columns = np.clip(np.arange(-halo, w + halo), 0, w - 1)
    for top in range(0, h, chunk_rows):
        stop = min(top + chunk_rows, h)
        rows = np.clip(np.arange(top - halo, stop + halo), 0, h - 1)
        original = a[rows[:, None], columns[None, :]]
        if not np.isfinite(original).all() or np.any(original < 0):
            raise ValueError("RL input must be finite and nonnegative")
        estimate = original.copy()
        for _ in range(2):
            blurred = _convolve(estimate, kernel)
            ratio = np.zeros_like(blurred)
            np.divide(original, blurred, out=ratio, where=np.abs(blurred) > threshold)
            estimate *= _convolve(ratio, kernel)
        estimate[np.abs(estimate) <= threshold] = F(0)
        result[top:stop] = estimate[halo:halo + stop - top, halo:halo + w]
    return result
