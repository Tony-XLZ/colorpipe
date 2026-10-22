from pathlib import Path
import sys

import numpy as np
import pytest
from skimage.color import deltaE_ciede2000
from skimage.metrics import structural_similarity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from m2_metrics import camera_to_xyz, delta_e_statistics, ssim_statistics


def test_color_transform_maps_camera_neutral_after_nontrivial_calibration():
    forward = np.array([[.5, .3, .1642], [.2, .7, .1], [.1, .1, .6249]])
    calibration = np.array([[.95, .02, .01], [.01, 1.02, .01], [0, .01, 1.05]])
    analog = np.array([1.1, .9, 1.2])
    neutral = np.array([.4, 1., .6])
    matrix = camera_to_xyz(forward, calibration, analog, neutral)
    np.testing.assert_allclose(matrix @ neutral, forward @ np.ones(3), atol=1e-14)


def test_ciede2000_published_pair_and_full_resolution_identity(tmp_path):
    # Sharma, Wu and Dalal (2005), first supplementary confirmation pair.
    value = deltaE_ciede2000(np.array([50., 2.6772, -79.7751]), np.array([50., 0., -82.7485]))
    assert float(value) == pytest.approx(2.0425, abs=5e-5)
    image = np.random.default_rng(84).integers(0, 65536, (7, 9, 3), dtype=np.uint16)
    result = delta_e_statistics(image, image, np.eye(3), tmp_path / 'delta.f32')
    assert result['samples'] == 63
    assert result['mean'] == result['p95'] == result['maximum'] == 0


@pytest.mark.parametrize('chunk_rows', [1, 7, 32])
def test_chunked_ssim_matches_full_image_with_border_and_strip_changes(chunk_rows):
    reference = np.random.default_rng(176).integers(0, 65536, (19, 23, 3), dtype=np.uint16)
    predicted = reference.copy()
    # Include physical borders and strip seams in the independently computed score.
    predicted[0, :, 0] = 0
    predicted[7, :, 1] = 65535
    predicted[-1, :, 2] = 0
    result = ssim_statistics(predicted, reference, chunk_rows=chunk_rows)
    expected = structural_similarity(reference, predicted, data_range=65535, channel_axis=-1)
    assert result['mean'] == pytest.approx(expected, abs=2e-14)
    for index, channel in enumerate(('R', 'G', 'B')):
        score = structural_similarity(reference[..., index], predicted[..., index], data_range=65535)
        assert result['channels'][channel] == pytest.approx(score, abs=2e-14)
    assert result['valid_centers_per_channel'] == (19 - 6) * (23 - 6)
    assert result['window_size'] == 7
    assert result['mean'] < 1


def test_ssim_identity_at_minimum_window_size():
    reference = np.full((7, 7, 3), 12345, np.uint16)
    result = ssim_statistics(reference, reference, chunk_rows=1)
    assert result['mean'] == 1
    assert result['valid_centers_per_channel'] == 1


@pytest.mark.parametrize('invalid', ['shape', 'dtype', 'size', 'chunk'])
def test_ssim_rejects_incompatible_comparison_domains(invalid):
    reference = np.zeros((9, 11, 3), np.uint16)
    predicted = reference.copy()
    chunk_rows = 32
    if invalid == 'shape':
        predicted = predicted[:, :-1]
    elif invalid == 'dtype':
        predicted = predicted.astype(np.float32)
    elif invalid == 'size':
        predicted = reference = reference[:6]
    else:
        chunk_rows = 0
    with pytest.raises(ValueError):
        ssim_statistics(predicted, reference, chunk_rows=chunk_rows)
