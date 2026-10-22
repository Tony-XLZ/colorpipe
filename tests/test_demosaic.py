import numpy as np
import pytest

from colorpipe.demosaic import (
    demosaic, demosaic_hifi, _refine_green, _refine_green_rows, _guided, _fill_colors,
)
from colorpipe.normalize import normalize_cfa
from colorpipe.types import RawImage, Settings


def scene(cfa):
    return RawImage(cfa=cfa, black=(0,) * 4, white=(65535,) * 4)


@pytest.mark.parametrize("level", [0, 10000, 65535])
def test_constant_neutral_is_preserved(level):
    raw = scene(np.full((16, 20), level, dtype=np.uint16))
    rgb = demosaic(normalize_cfa(raw.cfa, raw), raw, Settings())
    assert rgb.shape == (12, 16, 3)
    assert rgb.dtype == np.uint16
    assert np.max(abs(rgb.astype(int) - level)) <= 4


def test_four_passes_preserve_measured_red_blue_and_stage_write_sets():
    rng = np.random.default_rng(42)
    raw = scene(rng.integers(1000, 60000, (20, 24), dtype=np.uint16))
    normalized = normalize_cfa(raw.cfa, raw)
    original = normalized.copy()
    stages = {}
    result = demosaic_hifi(normalized, raw, Settings(), stage_callback=lambda n, a: stages.update({n: a.copy()}))
    assert list(stages) == ["prepared_cfa", "pass1", "pass2", "pass3", "pass4"]
    np.testing.assert_array_equal(normalized, original)
    y, x = np.indices(result.shape[:2])
    green = (x + y) % 2 == 1
    red = (x % 2 == 0) & (y % 2 == 0)
    blue = (x % 2 == 1) & (y % 2 == 1)
    native = stages["prepared_cfa"][2:-2, 2:-2]
    np.testing.assert_array_equal(result[..., 0][red], native[red])
    np.testing.assert_array_equal(result[..., 2][blue], native[blue])
    np.testing.assert_array_equal(stages["pass1"][..., 1][~green], stages["pass2"][..., 1][~green])
    np.testing.assert_array_equal(stages["pass1"][..., ::2], stages["pass2"][..., ::2])
    np.testing.assert_array_equal(stages["pass2"][green], stages["pass3"][green])
    np.testing.assert_array_equal(stages["pass3"][..., 1], result[..., 1])
    np.testing.assert_array_equal(stages["pass3"][~green], result[~green])


def test_deterministic_across_chunk_sizes():
    rng = np.random.default_rng(3)
    raw = scene(rng.integers(0, 65536, (30, 36), dtype=np.uint16))
    normalized = normalize_cfa(raw.cfa, raw)
    a = demosaic_hifi(normalized, raw, Settings(), chunk_rows=3)
    b = demosaic_hifi(normalized, raw, Settings(), chunk_rows=16)
    np.testing.assert_array_equal(a, b)


def test_constant_color_and_boundary_averages():
    cfa = np.zeros((16, 20), dtype=np.uint16)
    cfa[::2, ::2] = 40000
    cfa[::2, 1::2] = cfa[1::2, ::2] = 30000
    cfa[1::2, 1::2] = 20000
    raw = scene(cfa)
    result = demosaic(normalize_cfa(cfa, raw), raw, Settings())
    assert np.max(abs(result.astype(int) - np.array([40000, 30000, 20000]))) <= 8


def test_neutral_linear_ramp_has_no_interior_color_cast():
    y, x = np.indices((32, 40))
    cfa = (10000 + 90 * x + 120 * y).astype(np.uint16)
    raw = scene(cfa)
    result = demosaic(normalize_cfa(cfa, raw), raw, Settings())
    truth = cfa[2:-2, 2:-2, None]
    assert np.max(abs(result[4:-4, 4:-4].astype(int) - truth[4:-4, 4:-4])) <= 8


def test_refinement_matches_independent_nine_sample_formula():
    green = np.full((8, 10), 20000, dtype=np.uint16)
    samples = np.array([[12000, 18000, 24000], [16000, 21000, 26000],
                        [14000, 22000, 28000]], dtype=np.uint16)
    green[1:4, 2:5] = samples
    epsilon = 65535 * 1e-5
    center = float(samples[1, 1])
    directions = [abs((float(samples.flat[a]) + float(samples.flat[b])) / 2 - center)
                  for a, b in ((0, 8), (1, 7), (2, 6), (3, 5))]
    weights = [epsilon / (epsilon + abs(float(samples.flat[i]) - center) + directions[d])
               for i, d in ((0, 0), (1, 1), (2, 2), (3, 3), (5, 3), (6, 2), (7, 1), (8, 0))]
    values = [float(samples.flat[i]) for i in (0, 1, 2, 3, 5, 6, 7, 8)]
    wc = epsilon / (epsilon + .25 * min(directions))
    expected = int((wc * center + sum(w * v for w, v in zip(weights, values))) / (wc + sum(weights)))
    _refine_green_rows(green, [2])
    assert abs(int(green[2, 3]) - expected) <= 1


def frozen_refinement_reference(green):
    """Scalar float64 oracle; every neighborhood comes from the same snapshot."""
    result = green.copy()
    epsilon = 65535 * 1e-5
    for y in range(2, green.shape[0] - 2):
        for x in range(2 if y % 2 else 3, green.shape[1] - 2, 2):
            n = green[y - 1:y + 2, x - 1:x + 2].astype(np.float64).ravel()
            errors = [abs((n[a] + n[b]) / 2 - n[4])
                      for a, b in ((0, 8), (1, 7), (2, 6), (3, 5))]
            weight = epsilon / (epsilon + .25 * min(errors))
            total, numerator = weight, weight * n[4]
            for i, direction in ((0, 0), (1, 1), (2, 2), (3, 3),
                                 (5, 3), (6, 2), (7, 1), (8, 0)):
                weight = epsilon / (epsilon + abs(n[i] - n[4]) + errors[direction])
                total += weight
                numerator += weight * n[i]
            result[y, x] = int(numerator / total)
    return result


@pytest.mark.parametrize("shape,seed", [((20, 24), 9), ((26, 32), 71)])
def test_refinement_stabilizes_feedback_without_changing_canonical_sweep(shape, seed):
    rng = np.random.default_rng(seed)
    source = rng.integers(1000, 60000, shape, dtype=np.uint16)
    canonical = source.copy()
    _refine_green_rows(canonical, range(2, shape[0] - 2))
    frozen = frozen_refinement_reference(source)
    # Each estimate retains the nine-point kernel. Winsorize their midpoint
    # to half an 8-bit working step; this is independent of acceptance limits.
    change = np.clip((frozen.astype(float) - canonical) / 2, -128, 128)
    expected = (canonical.astype(float) + change).astype(np.uint16)
    assert np.max(abs(expected.astype(int) - canonical)) == 128
    rgb = np.repeat(source[..., None], 3, axis=2)
    anchor = _refine_green(rgb)
    assert np.max(abs(rgb[..., 1].astype(int) - expected)) <= 1
    np.testing.assert_array_equal(anchor, canonical)
    np.testing.assert_array_equal(rgb[..., 0], source)
    np.testing.assert_array_equal(rgb[..., 2], source)
    assert not np.shares_memory(anchor, rgb)


def test_color_feedback_guard_prevents_ratio_weight_amplification():
    rng = np.random.default_rng(37)
    source = rng.integers(1000, 60000, (20, 24, 3), dtype=np.uint16)
    cfa = rng.integers(1000, 60000, (24, 28), dtype=np.uint16)
    yy, xx = np.indices(source.shape[:2])
    native_green = (yy + xx) % 2 == 1
    baseline = source.copy()
    _fill_colors(baseline, cfa, 4, 5)
    changed = source.copy()
    changed[..., 1][native_green] += 128
    unrestricted = changed.copy()
    _fill_colors(unrestricted, cfa, 4, 5)
    assert np.max(abs(unrestricted[..., ::2].astype(int) - baseline[..., ::2])) > 200
    result = changed.copy()
    _fill_colors(result, cfa, 4, 5, canonical_green=source[..., 1])
    expected = np.clip(unrestricted[..., ::2].astype(int),
                       baseline[..., ::2].astype(int) - 128,
                       baseline[..., ::2].astype(int) + 128)
    np.testing.assert_array_equal(result[..., ::2], expected)
    np.testing.assert_array_equal(result[..., 1], changed[..., 1])
    np.testing.assert_array_equal(result[~native_green], changed[~native_green])


def test_color_interpolation_uses_multiplicative_green_ratio():
    green = [5000, 7000, 8000, 9000]
    color = [3000, 18000, 6000, 25000]
    center, epsilon = 10000, 65535 * 1e-5
    weights = [epsilon / (abs(g - center) + epsilon) for g in green]
    total = sum(weights)
    average_green = sum(w * g for w, g in zip(weights, green)) / total
    average_color = sum(w * c for w, c in zip(weights, color)) / total
    expected = int(average_color * (center + epsilon) / (epsilon + .3 * center + .7 * average_green))
    result = _guided(np.float32(center), list(map(np.float32, green)), list(map(np.float32, color)))
    assert abs(int(result) - expected) <= 1
    assert abs(int(result) - int(average_color)) > 100


@pytest.mark.parametrize("changes", [{"pattern": "BGGR"}, {"crop": (1, 1, 1, 1)}])
def test_unsupported_geometry_is_rejected(changes):
    raw = scene(np.zeros((16, 20), dtype=np.uint16))
    for key, value in changes.items():
        setattr(raw, key, value)
    with pytest.raises(ValueError):
        demosaic(normalize_cfa(raw.cfa, raw), raw, Settings())
