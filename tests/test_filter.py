import numpy as np
import pytest

from colorpipe.filter import filter_parameters, filter_plane


def scalar_patch(p, A, B):
    p = np.asarray(p, float).ravel()
    cross, diagonal = sorted(p[[1, 3, 4, 5, 7]]), sorted(p[[0, 2, 4, 6, 8]])
    c, g = p[4], p[4]
    selected = diagonal if abs(c - diagonal[2]) < abs(c - cross[2]) else cross
    bright = c == cross[4] == diagonal[4]
    dark = c == cross[0] == diagonal[0]
    if bright or dark:
        q = (2 * selected[2] + selected[3 if bright else 1]) / 3
        delta = abs(c - q) - abs(cross[2] - diagonal[2])
        if delta > 0:
            t = min(delta / B, 1.)
            g = (1 - t) * c + t * q
    weights = 1 / (abs(p - g) + 1 / A)
    return np.dot(p, weights) / weights.sum()


@pytest.mark.parametrize('center', [0., .35, 1.])
def test_extrema_use_neighbor_order_statistics_and_keep_flat_fields(center):
    image = np.full((7, 9), .3, np.float32)
    image[3, 4] = center
    actual = filter_plane(image, 4096, .25)
    expected = scalar_patch(image[2:5, 3:6], 4096, .25)
    assert abs(float(actual[3, 4]) - expected) < 2e-7
    assert abs(float(actual[0, 0]) - .3) < 2e-7
    assert abs(float(actual[3, 4]) - .3) < abs(center - .3) + 2e-7


def test_all_edges_match_independent_scalar_sampling():
    image = np.random.default_rng(81).random((6, 8), dtype=np.float32)
    actual = filter_plane(image, 4096 / 1.19, .25 / 1.19, chunk_rows=2)
    padded = np.pad(image, 1, mode='edge')
    expected = np.array([[scalar_patch(padded[y:y + 3, x:x + 3], 4096 / 1.19, .25 / 1.19)
                          for x in range(8)] for y in range(6)])
    np.testing.assert_allclose(actual, expected, atol=3e-7, rtol=0)
    np.testing.assert_array_equal(actual, filter_plane(image, 4096 / 1.19, .25 / 1.19, chunk_rows=5))


def test_filter_iso_buckets_and_small_image_adjustment():
    np.testing.assert_allclose(filter_parameters(200, 20_000_000), (4096, .25))
    np.testing.assert_allclose(filter_parameters(200, 16_000_000), (4096 / 1.19, .25 / 1.19))
    np.testing.assert_allclose(filter_parameters(204801, 20_000_000), (4096 / 6.73, .25 / 6.73))


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -.1, 1.1])
def test_filter_rejects_invalid_values(invalid):
    image = np.zeros((4, 5), np.float32)
    image[2, 3] = invalid
    with pytest.raises(ValueError):
        filter_plane(image, 4096, .25)
