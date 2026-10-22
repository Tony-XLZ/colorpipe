"""Formula-generated forward/inverse tone tables for the default color tail."""

from functools import lru_cache
import math

import numpy as np


@lru_cache(maxsize=16)
def tone_luts(max_wb: float) -> tuple[np.ndarray, np.ndarray]:
    """Generate the continuous shoulder and its analytic inverse, then quantize.

    Route B evaluates the recovered curve in float64 directly. It does not
    copy a table, the reference's 1024-knot spline, or CRT rounding behavior.
    """
    if not math.isfinite(max_wb) or max_wb <= 0:
        raise ValueError("max_wb must be finite and positive")
    total = max(1., float(max_wb))
    span = min(7.5, max(1.02607, math.log2(total)) + 3.5)
    slope = 2. ** 3.5
    extent = 2. ** span - 1
    low, high = 0., 1.
    while math.log1p(extent * high) / high > slope - 1:
        high *= 2
    for _ in range(64):
        middle = (low + high) / 2
        if math.log1p(extent * middle) / middle > slope - 1:
            low = middle
        else:
            high = middle
    shoulder = (low + high) / 2

    def curve(value):
        linear = slope * value
        return np.where(linear <= 1, linear,
                        1 + np.log1p(shoulder * np.maximum(linear - 1, 0)) / shoulder)

    norm = float(curve(total))
    positions = np.arange(65536, dtype=np.float64) / 65535
    forward = np.power(curve(total * positions) / norm, 5 / 12)
    target = np.power(positions, 12 / 5) * norm
    linear = np.where(target <= 1, target,
                      1 + np.expm1(shoulder * (target - 1)) / shoulder)
    inverse = linear / (slope * total)
    tables = tuple(np.floor(np.clip(v, 0, 1) * 65535 + .5).astype(np.uint16)
                   for v in (forward, inverse))
    for table in tables:
        table[0], table[-1] = 0, 65535
        table.flags.writeable = False
    return tables
