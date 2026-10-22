import numpy as np
import pytest

from colorpipe.rl import deconvolve_luma, gaussian_psf, rl_sigma


def scalar_convolve(a, kernel):
    padded = np.pad(a, 1, mode='edge')
    return np.array([[np.sum(padded[y:y + 3, x:x + 3] * kernel)
                      for x in range(a.shape[1])] for y in range(a.shape[0])])


def test_two_iterations_with_one_time_halo_match_independent_full_canvas():
    image = np.random.default_rng(4).random((5, 7), dtype=np.float32)
    kernel = gaussian_psf(.6).astype(float)
    source = np.pad(image.astype(float), 8, mode='edge')
    expected = source.copy()
    for _ in range(2):
        blurred = scalar_convolve(expected, kernel)
        ratio = np.divide(source, blurred, out=np.zeros_like(source), where=blurred > .5 / 65535)
        expected *= scalar_convolve(ratio, kernel)
    expected = expected[8:-8, 8:-8]
    actual = deconvolve_luma(image, .6, chunk_rows=1)
    np.testing.assert_allclose(actual, expected, atol=5e-7, rtol=0)
    np.testing.assert_array_equal(actual, deconvolve_luma(image, .6, chunk_rows=4))
    wrong = image.astype(float)
    for _ in range(2):
        blurred = scalar_convolve(wrong, kernel)
        wrong *= scalar_convolve(image / blurred, kernel)
    assert np.max(abs(wrong - expected)) > 1e-3


def test_psf_normalization_symmetry_and_nonnegative_black():
    kernel = gaussian_psf(.604277)
    assert abs(float(kernel.sum()) - 1) < 1e-7
    np.testing.assert_array_equal(kernel, kernel[::-1, ::-1])
    for level in (0., .2, 1.):
        source = np.full((8, 11), level, np.float32)
        actual = deconvolve_luma(source, .6, chunk_rows=3)
        np.testing.assert_allclose(actual, source, atol=3e-7, rtol=0)
        assert np.isfinite(actual).all() and np.all(actual >= 0)


def test_sigma_uses_sensor_width_and_scale_and_real_iso_cutoff():
    assert rl_sigma(2000, 2., 200) == pytest.approx(.4)
    assert rl_sigma(5220, 2., 200) == pytest.approx(.2 * (np.sqrt(2.61) + 1))
    assert rl_sigma(8172, 2., 800) == pytest.approx(.9 * .2 * (np.sqrt(4.086) + 1))
    assert rl_sigma(8172, 2., 12800) is None


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -.1])
def test_rl_rejects_nonfinite_or_negative_input(invalid):
    source = np.full((4, 5), .2, np.float32)
    source[0, 0] = invalid
    with pytest.raises(ValueError):
        deconvolve_luma(source, .6)
