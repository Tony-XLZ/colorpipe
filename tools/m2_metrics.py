"""Validation-only fixed-profile D50 Lab / CIEDE2000 comparison."""

from pathlib import Path

import numpy as np
from skimage.color import deltaE_ciede2000, xyz2lab
from skimage.metrics import structural_similarity
import tifffile


def ssim_statistics(predicted, reference, *, chunk_rows=32):
    """Match skimage's uniform 7x7 RGB SSIM with bounded strip memory.

    Every valid window center is included, with a three-row halo across strip
    seams. The standard score omits centers in the outer three pixels; those
    border pixels still contribute to adjacent windows. PSNR/max/Delta E keep
    their separate full-image domains.
    """
    if (predicted.shape != reference.shape or predicted.ndim != 3
            or predicted.shape[-1] != 3 or min(predicted.shape[:2]) < 7
            or predicted.dtype != np.uint16 or reference.dtype != np.uint16):
        raise ValueError('SSIM requires matching uint16 HWC RGB images at least 7x7')
    if type(chunk_rows) is not int or chunk_rows < 1:
        raise ValueError('chunk_rows must be a positive integer')
    h, w = predicted.shape[:2]
    radius = 3
    sums = np.zeros(3, np.float64)
    for top in range(radius, h - radius, chunk_rows):
        stop = min(top + chunk_rows, h - radius)
        for channel in range(3):
            rows = slice(top - radius, stop + radius)
            _, score = structural_similarity(reference[rows, :, channel], predicted[rows, :, channel],
                                             data_range=65535, win_size=7, gaussian_weights=False,
                                             use_sample_covariance=True, full=True)
            sums[channel] += score[radius:radius + stop - top, radius:w - radius].sum(dtype=np.float64)
    centers = (h - 2 * radius) * (w - 2 * radius)
    channels = sums / centers
    return dict(mean=float(channels.mean()), channels=dict(zip(('R', 'G', 'B'), channels.tolist())),
                valid_centers_per_channel=centers, window_size=7, data_range=65535,
                model='skimage uniform 7x7, sample covariance, K1=0.01, K2=0.03; equal RGB channel mean',
                scope='all valid window centers; standard three-pixel border of centers excluded; no mask or sampling')


def camera_to_xyz(forward, calibration, analog_balance, neutral):
    individual_to_reference = np.linalg.inv(np.diag(analog_balance) @ calibration)
    reference_neutral = individual_to_reference @ neutral
    if not np.isfinite(reference_neutral).all() or np.any(reference_neutral <= 0):
        raise ValueError('invalid reference neutral for color comparison')
    return forward @ np.diag(1 / reference_neutral) @ individual_to_reference


def color_transform(dng):
    with tifffile.TiffFile(dng) as tf:
        tags = tf.pages[0].tags

        def rationals(tag, shape):
            values = np.asarray(tags[tag].value, dtype=np.float64).reshape(-1, 2)
            if np.any(values[:, 1] == 0):
                raise ValueError('zero denominator in color metadata')
            return (values[:, 0] / values[:, 1]).reshape(shape)

        forward = rationals(50965, (3, 3))
        calibration = rationals(50724, (3, 3))
        analog = rationals(50727, (3,))
        neutral = rationals(50728, (3,))
    matrix = camera_to_xyz(forward, calibration, analog, neutral)
    return matrix, dict(model='fixed ForwardMatrix2 + CameraCalibration2 + AnalogBalance + AsShotNeutral to XYZ D50 / Lab 2deg',
                        matrix=matrix.tolist(), illuminant='D50', observer='2',
                        profile_scope='matrix-only diagnostic; no illuminant interpolation, HueSatMap, LookTable, tone rendering, exposure fit, or gamut clipping',
                        source_dng=str(Path(dng).resolve()),
                        source='Adobe DNG Specification 1.7.1 section Camera to XYZ (D50) Transform')


def camera_lab(rgb16, matrix):
    xyz = np.einsum('...c,kc->...k', rgb16.astype(np.float64) / 65535, matrix)
    return xyz2lab(xyz, illuminant='D50', observer='2')


def delta_e_statistics(predicted, reference, matrix, output):
    h, w = predicted.shape[:2]
    values = np.memmap(output, mode='w+', dtype='<f4', shape=(h, w))
    total, maximum, above2, worst = 0., 0., 0, None
    for y in range(0, h, 32):
        delta = deltaE_ciede2000(camera_lab(reference[y:y + 32], matrix),
                               camera_lab(predicted[y:y + 32], matrix))
        if not np.isfinite(delta).all():
            raise ValueError('nonfinite Delta E; comparison is invalid')
        total += float(delta.sum())
        above2 += int(np.count_nonzero(delta >= 2))
        local_max = float(delta.max())
        if local_max > maximum:
            maximum = local_max
            iy, ix = np.unravel_index(delta.argmax(), delta.shape)
            worst = [int(y + iy), int(ix)]
        values[y:y + len(delta)] = delta
    values.flush()
    p95, p99 = np.quantile(values, [.95, .99]).tolist()
    del values
    return dict(samples=h * w, mean=total / (h * w), p95=p95, p99=p99, maximum=maximum,
                pixels_at_or_above_2=above2, worst_array_coordinate=worst,
                quantiles='full-resolution float32 Delta E map, no sampling or mask',
                map=str(Path(output).resolve()))
