"""Core data types for colorpipe."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np


@dataclass(frozen=True)
class Settings:
    """Bounded settings for the color-only route B pipeline."""

    algorithm: Literal["hifi", "v3"] = "hifi"
    v3_mode: int = 0
    bit_depth: int = 16
    compression: str = "none"
    profile: str | None = None
    wb: tuple[float, float, float] | None = None
    exposure: float = 0.0

    def validate(self) -> None:
        if self.algorithm not in ("hifi", "v3"):
            raise ValueError("algorithm must be 'hifi' or 'v3'")
        if self.algorithm == "v3" and self.v3_mode not in (0, 1):
            raise ValueError("v3_mode must be 0 or 1")
        if self.bit_depth != 16:
            raise NotImplementedError("only 16-bit is supported in v1")
        if self.compression != "none":
            raise NotImplementedError("only uncompressed DNG is supported in v1")
        if self.exposure != 0:
            raise NotImplementedError("non-zero exposure is not supported in v1")
        if self.wb is not None:
            if len(self.wb) != 3 or any((not np.isfinite(x)) or x <= 0 for x in self.wb):
                raise ValueError("wb must be three finite positive numbers")


@dataclass
class RawImage:
    """Full sensor CFA; black/white order is R,G1,G2,B in sensor units.

    width/height describe the CFA. crop is the demosaic boundary ordered
    top,bottom,left,right; camera_crop is separate x,y,w,h metadata.
    Missing metadata is None for synthetic inputs and is never guessed.
    """

    cfa: np.ndarray  # uint16, H x W
    black: tuple[int, int, int, int]
    white: tuple[int, int, int, int]
    pattern: str = "RGGB"
    crop: tuple[int, int, int, int] = (2, 2, 2, 2)
    iso: int | None = None
    pixel_scale: float | None = None
    width: int | None = None
    height: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    wb: tuple[float, float, float] | None = None
    valid_bits: int | None = None
    camera_crop: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        if self.cfa.ndim != 2:
            raise ValueError("cfa must be 2-D")
        if self.cfa.dtype != np.uint16:
            raise ValueError("cfa must be uint16")
        if min(self.cfa.shape) <= 0:
            raise ValueError("cfa dimensions must be positive")
        if self.width is None:
            self.width = self.cfa.shape[1]
        if self.height is None:
            self.height = self.cfa.shape[0]
        if (self.height, self.width) != self.cfa.shape:
            raise ValueError("width/height dimensions must match the full CFA")
        if self.pattern not in ("RGGB", "BGGR", "GRBG", "GBRG"):
            raise ValueError("unsupported CFA pattern")
        if len(self.black) != 4 or len(self.white) != 4:
            raise ValueError("black/white must have four values")
        if any(not isinstance(x, (int, np.integer)) for x in (*self.black, *self.white)):
            raise ValueError("black/white must contain integers")
        if any(not 0 <= b < w <= 65535 for b, w in zip(self.black, self.white)):
            raise ValueError("black/white must satisfy 0 <= black < white <= 65535")
        if (len(self.crop) != 4 or any(not isinstance(v, int) or v < 0 for v in self.crop)
                or self.crop[0] + self.crop[1] >= self.height
                or self.crop[2] + self.crop[3] >= self.width):
            raise ValueError("invalid demosaic crop")
        if self.iso is not None and (not isinstance(self.iso, int) or self.iso <= 0):
            raise ValueError("iso must be a positive integer")
        if self.pixel_scale is not None and (not np.isfinite(self.pixel_scale) or self.pixel_scale <= 0):
            raise ValueError("pixel_scale must be finite and positive")
        if self.wb is not None and (len(self.wb) != 3 or any(not np.isfinite(v) or v <= 0 for v in self.wb)):
            raise ValueError("wb must be three finite positive values")
        if self.valid_bits is not None and self.valid_bits not in (12, 14, 16):
            raise ValueError("unsupported valid_bits")
        if self.camera_crop is not None:
            if len(self.camera_crop) != 4 or any(not isinstance(v, int) for v in self.camera_crop):
                raise ValueError("invalid camera_crop")
            x, y, w, h = self.camera_crop
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > self.width or y + h > self.height:
                raise ValueError("camera_crop outside full CFA")

    @property
    def processing_size(self) -> tuple[int, int]:
        """Width,height after the demosaic boundary, without slicing the CFA."""
        top, bottom, left, right = self.crop
        return self.width - left - right, self.height - top - bottom
