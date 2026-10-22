"""Single-input default color conversion; profiles remain user-supplied."""

from pathlib import Path

from .dcp import load_dcp
from .decode import load_raw
from .demosaic import demosaic_hifi
from .normalize import normalize_cfa
from .tail import StageCallback, run_tail
from .types import Settings
from .writer import write_dng


def convert_raw(input_path: str | Path, output_path: str | Path, settings: Settings, *,
                stage_callback: StageCallback | None = None) -> Path:
    """Decode -> normalize -> HiFi -> default tail -> camera-linear DNG.

    Callbacks borrow the same stages as the component APIs. No reference
    image, template, profile search path, or external renderer is consulted.
    """
    settings.validate()
    if settings.algorithm != 'hifi':
        raise NotImplementedError('only default HiFi conversion is implemented')
    output_path = Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f'refusing to overwrite: {output_path}')
    if output_path.suffix.lower() != '.dng':
        raise ValueError('output must have a .dng extension')
    if settings.profile is None:
        raise ValueError('a user-supplied DCP profile is required (--profile)')
    profile = load_dcp(settings.profile)
    if int(profile.array(50941, [0])[0]) == 2:
        raise ValueError('profile embed policy forbids embedding')
    raw = load_raw(input_path)
    normalized = normalize_cfa(raw.cfa, raw)
    rgb = demosaic_hifi(normalized, raw, settings, stage_callback=stage_callback)
    del normalized
    result = run_tail(rgb, raw, settings, stage_callback=stage_callback)
    del rgb
    return write_dng(result, raw, settings, output_path)
