"""colorpipe: open-source color-only ORF -> DNG (route B).

This package aims for visual equivalence using the recovered color pipeline
as a research reference. It does not call or load the original product.
"""

__version__ = "0.1.0"

from .types import Settings, RawImage

__all__ = ["Settings", "RawImage", "__version__"]
