"""Preserve M4 float32 results while changing array access and order statistics."""

import hashlib
from itertools import permutations, product

import numpy as np
import pytest

from colorpipe import filter as filtering


def test_five_element_network_covers_every_strict_order():
    values = np.asarray([*permutations(range(5)), *product((0, 1), repeat=5)], dtype=np.float32).T
    actual = np.stack(filtering._sort_five(values))
    np.testing.assert_array_equal(actual, np.sort(values, axis=0))


@pytest.mark.parametrize('chunk_rows', [1, 7, 64])
@pytest.mark.parametrize('kind,expected', [
    ('random', 'b3dd1bf52f2f89fb3103536313e09cb91c755587896759c9566f514df9e0c256'),
    ('strided', 'b15d27b8f5221b701230a4cba174b6195473bf1e74131009d6dc393a4f996732'),
    ('ties', '8e27c6b7077067f6733c4c740542689b30e1844d931463bf0fecdb0d6d807148'),
])
def test_filter_matches_m4_float32_bytes(kind, expected, chunk_rows):
    A, B = 4096, .25
    if kind == 'random':
        source = np.random.default_rng(917).random((33, 47), dtype=np.float32)
    elif kind == 'strided':
        full = np.random.default_rng(918).integers(0, 65536, (56, 70), dtype=np.uint16)
        full = full.astype(np.float32) / np.float32(65535)
        source, A, B = full[::2, 1::2], 4096 / 1.19, .25 / 1.19
    else:
        levels = np.array([0., -0., np.nextafter(np.float32(0), np.float32(1)), .1, .3, .5, 1.], np.float32)
        source = np.resize(levels, (9, 13))
    before = source.copy()
    result = filtering.filter_plane(source, A, B, chunk_rows=chunk_rows)
    np.testing.assert_array_equal(source.view(np.uint32), before.view(np.uint32))
    assert hashlib.sha256(result.astype('<f4', copy=False).tobytes()).hexdigest() == expected
