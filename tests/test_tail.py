import numpy as np
import pytest

from colorpipe.tail import run_tail, quantize_u16
from colorpipe.types import RawImage, Settings


def raw_for(shape, *, iso=200, wb=(2.75, 1., 1.4296875)):
    h, w = shape[:2]
    return RawImage(np.full((h + 4, w + 4), 1000, np.uint16),
                    black=(254,) * 4, white=(4095,) * 4,
                    iso=iso, pixel_scale=2., wb=wb)


def test_tail_stage_units_chroma_and_input_ownership():
    rng = np.random.default_rng(310)
    source = rng.integers(500, 60000, (16, 20, 3), dtype=np.uint16)
    saved = source.copy()
    stages = {}
    result = run_tail(source, raw_for(source.shape), Settings(),
                      stage_callback=lambda n, a: stages.update({n: a.copy()}))
    assert list(stages) == ['normalized', 'weighted_tone', 'filtered_rgb',
                            'default_diff', 'default_deconvolved', 'rgb_linear', 'quantized']
    np.testing.assert_array_equal(source, saved)
    np.testing.assert_array_equal(stages['normalized'], source.astype(np.float32) * np.float32(1 / 65535))
    filtered = stages['filtered_rgb']
    np.testing.assert_array_equal(stages['default_diff'][..., 0], filtered[..., 1])
    for slot, channel in ((1, 0), (2, 2)):
        expected = (filtered[..., channel] - filtered[..., 1]) * np.float32(.5) + np.float32(.5)
        np.testing.assert_array_equal(stages['default_diff'][..., slot], expected)
    np.testing.assert_array_equal(stages['default_diff'][..., 1:], stages['default_deconvolved'][..., 1:])
    assert np.any(stages['default_diff'][..., 0] != stages['default_deconvolved'][..., 0])
    assert result.shape == source.shape and result.dtype == np.uint16
    np.testing.assert_array_equal(result, stages['quantized'])


def test_high_iso_skips_only_default_rl():
    source = np.random.default_rng(24).integers(1000, 50000, (12, 16, 3), dtype=np.uint16)
    stages = {}
    run_tail(source, raw_for(source.shape, iso=12800), Settings(),
             stage_callback=lambda n, a: stages.update({n: a.copy()}))
    np.testing.assert_array_equal(stages['default_diff'], stages['default_deconvolved'])
    assert np.any(stages['filtered_rgb'] != stages['weighted_tone'])


def test_tail_black_and_neutral_roundtrip():
    for level in (0, 1000, 20000, 65535):
        source = np.full((8, 12, 3), level, np.uint16)
        result = run_tail(source, raw_for(source.shape, wb=(1., 1., 1.)), Settings())
        assert np.max(abs(result.astype(int) - level)) <= 16


def test_tail_is_bit_identical_across_row_chunks():
    source = np.random.default_rng(57).integers(0, 65536, (18, 22, 3), dtype=np.uint16)
    raw = raw_for(source.shape)
    a = run_tail(source, raw, Settings(), chunk_rows=1)
    b = run_tail(source, raw, Settings(), chunk_rows=7)
    np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize('field', ['iso', 'pixel_scale', 'wb'])
def test_tail_requires_source_metadata(field):
    source = np.zeros((8, 12, 3), np.uint16)
    raw = raw_for(source.shape)
    setattr(raw, field, None)
    with pytest.raises(ValueError, match=field):
        run_tail(source, raw, Settings())


def test_explicit_wb_override_is_used():
    source = np.full((8, 12, 3), 12000, np.uint16)
    a = run_tail(source, raw_for(source.shape, wb=None), Settings(wb=(2., 1., 1.5)))
    b = run_tail(source, raw_for(source.shape, wb=(2., 1., 1.5)), Settings())
    np.testing.assert_array_equal(a, b)


def test_quantization_clamps_and_rounds_half_up():
    samples = np.array([-.1, 0, .5 / 65535, 1.5 / 65535, .5, 1., 1.1], np.float32)
    np.testing.assert_array_equal(quantize_u16(samples), [0, 0, 1, 2, 32768, 65535, 65535])


@pytest.mark.parametrize('chunk', [0, -1, True, 1.5])
def test_tail_rejects_invalid_chunk_sizes(chunk):
    source = np.zeros((8, 12, 3), np.uint16)
    with pytest.raises(ValueError):
        run_tail(source, raw_for(source.shape), Settings(), chunk_rows=chunk)


def test_tail_rejects_wrong_stage_shape_and_dtype():
    source = np.zeros((8, 12, 3), np.uint16)
    raw = raw_for(source.shape)
    for wrong in (source.astype(np.float32), source[..., 0], source[:, :-1]):
        with pytest.raises(ValueError):
            run_tail(wrong, raw, Settings())
