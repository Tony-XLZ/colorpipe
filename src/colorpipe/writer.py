"""Camera-linear DNG writer.

See docs/METADATA_DIFFERENCES.md for supported fields and docs/LEGAL.md
for provenance. The caller supplies a profile with permission to embed it.
"""

from __future__ import annotations

from pathlib import Path
import os
import tempfile

import numpy as np

from .types import RawImage, Settings
from . import __version__
from .dcp import load_dcp
from .tiff import field, dng_header


def write_dng(
    rgb16: np.ndarray,
    raw: RawImage,
    settings: Settings,
    path: str | Path,
    dcp: str | Path | None = None,
) -> Path:
    """Write a 16-bit uncompressed camera-linear DNG.

    Required tags (minimum):
      DNGVersion, DNGBackwardVersion, UniqueCameraModel,
      ColorMatrix1/2, CameraCalibration1/2, CalibrationIlluminant1/2,
      AnalogBalance, AsShotNeutral, AsShotProfileName,
      BlackLevel, WhiteLevel, ActiveArea, DefaultCropOrigin/Size,
      Orientation, Software.

    - `dcp` is supplied by the caller; no profile is bundled or auto-selected.
    - Do not claim full EXIF equality; document differences.
    """
    settings.validate()
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    # Resolve the parent only: following the last component can redirect a
    # dangling symlink and bypass the exclusive publication contract.
    path = path.parent.resolve() / path.name
    if path.suffix.lower() != '.dng':
        raise ValueError('output must have a .dng extension')
    if (rgb16.dtype != np.uint16 or rgb16.ndim != 3 or rgb16.shape[-1] != 3
            or rgb16.shape[:2] != raw.processing_size[::-1]):
        raise ValueError('writer requires complete post-tail uint16 HWC RGB')
    if rgb16.nbytes >= 2 ** 32:
        raise ValueError('classic TIFF size limit exceeded')
    if settings.algorithm != 'hifi':
        raise NotImplementedError('only the validated default HiFi pipeline is supported')
    profile_path = dcp if dcp is not None else settings.profile
    if profile_path is None:
        raise ValueError('a user-supplied DCP profile is required')
    if dcp is not None and settings.profile is not None and Path(dcp).resolve() != Path(settings.profile).resolve():
        raise ValueError('conflicting DCP profile arguments')
    profile = load_dcp(profile_path)
    if int(profile.array(50941, [0])[0]) == 2:
        raise ValueError('profile embed policy forbids embedding')
    identity = ('OM Digital Solutions', 'OM-1MarkII')
    if (raw.metadata.get('make'), raw.metadata.get('model')) != identity:
        raise ValueError('writer camera metadata is missing or unsupported')
    camera_name = 'OM Digital Solutions OM-1 Mark II'
    if profile.text(50708, camera_name) != camera_name:
        raise ValueError('DCP camera model does not match the RAW')
    wb = settings.wb if settings.wb is not None else raw.wb
    if wb is None or not np.isfinite(wb).all() or min(wb) <= 0 or raw.iso is None:
        raise ValueError('positive WB and source ISO are required')
    orientation = raw.metadata.get('orientation')
    if type(orientation) is not int or not 1 <= orientation <= 8:
        raise ValueError('source orientation is required')
    if raw.camera_crop is None:
        raise ValueError('source camera crop is required')
    h, w, _ = rgb16.shape
    x, y, cw, ch = raw.camera_crop
    origin_x, origin_y = raw.crop[2], raw.crop[0]
    x0, y0 = max(x, origin_x), max(y, origin_y)
    x1, y1 = min(x + cw, origin_x + w), min(y + ch, origin_y + h)
    if x1 <= x0 or y1 <= y0:
        raise ValueError('camera crop does not intersect processed RGB')
    neutral = [int(np.floor(float(wb[1]) / float(v) * 1_000_000 + .5)) for v in wb]
    if any(not 0 < v < 2 ** 32 for v in neutral):
        raise ValueError('WB cannot be represented at the supported DNG neutral precision')
    calibration = np.eye(3)
    if profile.text(50932) == 'com.adobe':
        daylight = raw.metadata.get('daylight_wb')
        if daylight is None or len(daylight) != 3 or not np.isfinite(daylight).all() or min(daylight) <= 0:
            raise ValueError('source daylight_wb is required for the Adobe camera calibration')
        # Bounded OM-1 Mark II reference-camera gains from the handoff's
        # camera calibration metadata, not a DCP payload or image patch.
        reference = np.array([2.2030935287475586, 1., 1.8202753067016602], np.float32)
        gains = reference / np.asarray(daylight, np.float32)
        calibration = np.diag(np.floor(gains.astype(float) * 10000 + .5) / 10000)
    matrix = [(int(round(v * 10000)), 10000) for v in calibration.ravel()]
    root = {
        254: field(4, [0]), 256: field(4, [w]), 257: field(4, [h]),
        258: field(3, [16] * 3), 259: field(3, [1]), 262: field(3, [34892]),
        271: field(2, identity[0]), 272: field(2, identity[1]), 273: field(4, [0]),
        274: field(3, [orientation]), 277: field(3, [3]), 278: field(4, [h]),
        279: field(4, [rgb16.size * 2]), 284: field(3, [1]),
        305: field(2, f'colorpipe {__version__}'), 339: field(3, [1] * 3),
        50706: field(1, [1, 4, 0, 0]), 50707: field(1, [1, 2, 0, 0]),
        50708: field(2, camera_name), 50713: field(3, [1, 1]),
        50714: field(5, [(0, 1)] * 3), 50717: field(4, [65535] * 3),
        50718: field(5, [(1, 1)] * 2),
        50719: field(5, [(x0 - origin_x, 1), (y0 - origin_y, 1)]),
        50720: field(5, [(x1 - x0, 1), (y1 - y0, 1)]),
        50723: field(10, matrix), 50724: field(10, matrix),
        50727: field(5, [(1, 1)] * 3),
        50728: field(5, [(v, 1_000_000) for v in neutral]),
        50730: field(10, [(37, 100)]), 50731: field(5, [(125, 100)]),
        50732: field(5, [(150, 100)]), 50734: field(5, [(1, 1)]),
        50829: field(4, [0, 0, h, w]), 50934: field(2, profile.name),
    }
    if profile.text(50932):
        root[50931] = field(2, profile.text(50932))
    root.update({tag: entry for tag, entry in profile.fields.items() if tag != 50708})
    if raw.metadata.get('datetime'):
        root[306] = field(2, raw.metadata['datetime'])
    if raw.metadata.get('source'):
        root[50827] = field(2, Path(raw.metadata['source']).name)
    exif = {0x8827: field(3, [min(raw.iso, 65535)]), 0x8830: field(3, [1]),
            0x8831: field(4, [raw.iso]), 0xA002: field(4, [w]), 0xA003: field(4, [h])}
    for name, tag, kind in (('ExposureTime', 0x829A, 5), ('FNumber', 0x829D, 5),
                             ('FocalLength', 0x920A, 5), ('ExposureBiasValue', 0x9204, 10),
                             ('DateTimeOriginal', 0x9003, 2), ('DateTimeDigitized', 0x9004, 2),
                             ('LensModel', 0xA434, 2)):
        value = raw.metadata.get('exif', {}).get(name)
        if value is not None:
            exif[tag] = field(kind, value if kind == 2 else [value])
    header = dng_header(root, exif)
    if len(header) + rgb16.nbytes >= 2 ** 32:
        raise ValueError('classic TIFF size limit exceeded')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.partial', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(header)
            for top in range(0, h, 64):
                stream.write(np.ascontiguousarray(rgb16[top:top + 64], dtype='<u2').tobytes())
            stream.flush()
            os.fsync(stream.fileno())
        # An exclusive hard link publishes a complete file without replacing
        # an existing path, including a concurrently created destination.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
