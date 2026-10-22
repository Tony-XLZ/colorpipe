"""LibRaw pixel decoding plus independently checked source metadata."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .metadata import RawFormatError, read_orf_metadata
from .types import RawImage


def load_raw(path: str | Path) -> RawImage:
    """Return the full, unrotated sensor CFA; never call LibRaw postprocess.

    Levels are sensor-code values ordered R,G1,G2,B. The two-pixel demosaic
    boundary is recorded for M1, without applying either it or the camera crop.
    """
    source = Path(path).resolve()
    if source.suffix.lower() not in (".orf", ".ori"):
        raise RawFormatError("only .orf/.ori inputs are supported")
    meta = read_orf_metadata(source)
    try:
        import rawpy
    except ImportError as exc:
        raise ImportError("rawpy is required; install with: python -m pip install rawpy") from exc

    try:
        handle = rawpy.imread(str(source))
    except rawpy.LibRawError as exc:
        raise RawFormatError(f"LibRaw could not decode {source.name}: {exc}") from exc
    with handle as raw:
        pixels = raw.raw_image
        if pixels.ndim != 2 or pixels.dtype != np.uint16:
            raise RawFormatError("expected a 2-D uint16 Bayer CFA")
        if pixels.shape != (meta["height"], meta["width"]):
            raise RawFormatError("LibRaw CFA dimensions differ from source IFD")
        desc = raw.color_desc.decode("ascii", "replace").rstrip("\0")
        # raw_color uses full-sensor coordinates; visible margins may change parity.
        indices = tuple(int(raw.raw_color(y, x)) for y in range(2) for x in range(2))
        if any(i < 0 or i >= min(len(desc), 4) for i in indices) or "".join(desc[i] for i in indices) != "RGGB":
            raise RawFormatError("only full-sensor RGGB CFA is supported")
        libraw_black = tuple(int(v) for v in raw.black_level_per_channel)
        if len(libraw_black) != 4 or tuple(libraw_black[i] for i in indices) != meta["black"]:
            raise RawFormatError("LibRaw black levels differ from source MakerNote")
        white = int(raw.white_level)
        if (white,) * 4 != meta["white"]:
            raise RawFormatError("LibRaw white level differs from source ValidBits maximum")
        # An unused second-green WB entry can be zero. Select RGB by color index.
        wb_channels = np.asarray(raw.camera_whitebalance, dtype=np.float64)
        if wb_channels.shape != (4,) or not np.isfinite(wb_channels).all():
            raise RawFormatError("invalid LibRaw white balance")
        libraw_wb = wb_channels[[indices[0], indices[1], indices[3]]]
        if np.any(libraw_wb <= 0):
            raise RawFormatError("invalid LibRaw white balance")
        if not np.allclose(libraw_wb / libraw_wb[1], meta["wb"], rtol=1e-6, atol=0):
            raise RawFormatError("LibRaw white balance differs from source MakerNote")
        sizes = raw.sizes
        if (sizes.raw_width, sizes.raw_height) != (meta["width"], meta["height"]):
            raise RawFormatError("LibRaw reported RAW dimensions differ from source IFD")
        visible = [int(sizes.left_margin), int(sizes.top_margin), int(sizes.width), int(sizes.height)]
        x, y, width, height = visible
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > pixels.shape[1] or y + height > pixels.shape[0]:
            raise RawFormatError("LibRaw visible area outside full CFA")
        cfa = pixels.copy()
        details = dict(meta, source=str(source), color_desc=desc,
                       raw_pattern=[list(indices[:2]), list(indices[2:])],
                       visible_area_xywh=visible,
                       libraw_black_level_per_channel=list(libraw_black),
                       libraw_white_level=white,
                       camera_white_level_per_channel=raw.camera_white_level_per_channel,
                       libraw_camera_whitebalance=list(raw.camera_whitebalance))

    return RawImage(
        cfa=cfa, black=meta["black"], white=meta["white"], pattern=meta["pattern"],
        crop=(2, 2, 2, 2), iso=meta["iso"], wb=meta["wb"],
        pixel_scale=meta["pixel_scale"], width=meta["width"], height=meta["height"],
        valid_bits=meta["valid_bits"], camera_crop=meta["camera_crop"], metadata=details,
    )


def describe_raw(raw: RawImage) -> dict:
    """JSON-compatible M0 inspection, without exposing pixels or private EXIF."""
    return {
        "source": raw.metadata.get("source"),
        "camera": {name: raw.metadata.get(name) for name in ("make", "model", "orientation")},
        "cfa": {
            "size_wh": [raw.width, raw.height], "dtype": str(raw.cfa.dtype),
            "pattern": raw.pattern, "samples": int(raw.cfa.size),
            "min": int(raw.cfa.min()), "max": int(raw.cfa.max()),
            "mean": float(raw.cfa.mean()), "stage": raw.metadata.get("pixel_stage"),
        },
        "levels": {"order": "R,G1,G2,B", "black": list(raw.black), "white": list(raw.white),
                   "valid_bits": raw.valid_bits,
                   "camera_white_per_channel": raw.metadata.get("camera_white_level_per_channel")},
        "geometry": {"demosaic_crop_trbl": list(raw.crop),
                     "processing_size_wh": list(raw.processing_size),
                     "camera_crop_xywh": list(raw.camera_crop) if raw.camera_crop else None,
                     "libraw_visible_xywh": raw.metadata.get("visible_area_xywh")},
        "iso": raw.iso, "wb_rgb": list(raw.wb) if raw.wb else None,
        "pixel_scale": raw.pixel_scale,
        "focal_plane_diagonal": raw.metadata.get("focal_plane_diagonal"),
    }
