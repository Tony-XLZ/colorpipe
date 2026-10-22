import numpy as np
import pytest

from colorpipe.normalize import channel_black_white, normalize_cfa, prepare_cfa16
from colorpipe.types import RawImage


def test_normalize_levels_floor_green_and_preserve_highlights():
    cfa = np.array([[5, 50], [120, 200]], dtype=np.uint16)
    raw = RawImage(cfa=cfa, black=(10, 20, 31, 40), white=(110, 120, 131, 140), crop=(0,) * 4)
    out = normalize_cfa(cfa, raw)
    assert out.dtype == np.float32
    assert out[0, 0, 0] == 0
    assert out[0, 1, 1] == pytest.approx(.25)
    assert out[1, 0, 1] == pytest.approx(.95)
    assert out[1, 1, 2] == pytest.approx(1.6)
    assert np.count_nonzero(out) == 3
    prepared = prepare_cfa16(out, raw)
    np.testing.assert_array_equal(prepared, [[0, 16384], [62258, 65535]])


def test_green_level_average_cannot_overflow_uint16():
    raw = RawImage(cfa=np.zeros((2, 2), dtype=np.uint16), black=(0,) * 4,
                   white=tuple(np.uint16(x) for x in (65535, 60000, 60000, 65535)), crop=(0,) * 4)
    _, white = channel_black_white(raw)
    assert white[1] == 60000


@pytest.mark.parametrize("bad", [np.zeros((2, 2, 3), dtype=np.uint16),
                                  np.zeros((2, 2), dtype=np.float32)])
def test_normalize_requires_sensor_cfa(bad):
    raw = RawImage(cfa=np.zeros((2, 2), dtype=np.uint16), black=(0,) * 4, white=(1,) * 4, crop=(0,) * 4)
    with pytest.raises(ValueError):
        normalize_cfa(bad, raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -.1])
def test_prepared_cfa_rejects_invalid_native_values(value):
    raw = RawImage(cfa=np.zeros((2, 2), dtype=np.uint16), black=(0,) * 4, white=(1,) * 4, crop=(0,) * 4)
    normalized = np.zeros((2, 2, 3), dtype=np.float32)
    normalized[0, 0, 0] = value
    with pytest.raises(ValueError):
        prepare_cfa16(normalized, raw)
