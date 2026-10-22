from pathlib import Path
import sys

import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from render_m3 import rendered_delta_statistics


def test_rendered_delta_uses_srgb_transfer_and_every_pixel(tmp_path):
    reference = np.random.default_rng(372).integers(0, 65536, (9, 13, 3), dtype=np.uint16)
    predicted = reference.copy()
    predicted[0, 0] = [65535, 0, 0]
    predicted[-1, -1] = [0, 65535, 0]
    expected = deltaE_ciede2000(rgb2lab(reference.astype(float) / 65535), rgb2lab(predicted.astype(float) / 65535))
    result = rendered_delta_statistics(predicted, reference, tmp_path / 'delta.f32')
    np.testing.assert_allclose(result['mean'], expected.mean(), atol=1e-14)
    np.testing.assert_allclose(result['maximum'], expected.max(), atol=1e-14)
    np.testing.assert_allclose(np.fromfile(tmp_path / 'delta.f32', dtype='<f4').reshape(9, 13), expected, atol=4e-6)
    assert result['samples'] == 117
