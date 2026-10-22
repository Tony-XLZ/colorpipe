# colorpipe

A deterministic, color-only ORF/ORI → linear DNG converter for the **OM SYSTEM OM-1 Mark II**. Python 3.11+, NumPy and rawpy/LibRaw. Project code is MIT licensed.

**中文：** 将 OM-1 Mark II 的 ORF/ORI 转为 16 位相机线性 DNG，包含自有确定性行序的 HiFi 四 pass、默认彩色 tail 和用户提供的 DCP。当前为早期版本，真实图像验证限于三个 ISO 200 样本。详见[算法](docs/ALGORITHM.md)、[指标](docs/PROGRESS.md)及[已知限制](docs/LIMITATIONS.md)。

## Install

Install from a source checkout in a virtual environment:

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install .
```

Alternatively, install the wheel from this project's GitHub Releases. This project has not been published to PyPI; use this checkout or its release wheel rather than assuming the PyPI name identifies it.

NumPy and rawpy are default dependencies. Running the converter requires no proprietary converter, research files or external renderer. **Supply your own compatible DCP profile with permission to embed it.** No vendor profiles or user photographs are distributed.

## Use

```sh
orf2dng input.orf output.dng --profile user-supplied.dcp
orf2dng input.ori output.dng --profile user-supplied.dcp
orf2dng input.orf --inspect
python -m colorpipe --version
```

Use a new output filename. Conversion rejects existing files, unsupported cameras/settings, invalid metadata and profiles that prohibit embedding. The destination filesystem must support hard links. `--inspect` decodes and prints metadata without creating a DNG. `--plan` prints the requested settings without decoding or validating a profile.

```python
from colorpipe.pipeline import convert_raw
from colorpipe.types import Settings

convert_raw("input.orf", "output.dng", Settings(profile="user-supplied.dcp"))
```

The pipeline unpacks the full sensor CFA, normalizes black/white levels, runs four-pass HiFi demosaicing and the default WB/tone/filter/G-only Richardson–Lucy tail, then writes an uncompressed RGB16 camera-linear DNG with the supplied profile. Profile rendering happens later in your RAW editor.

## Scope and validation

- Verified inputs: two 20MP ORF/ORI samples and one 50MP high-resolution ORF, all OM-1 Mark II / ISO 200 / RGGB / 12 or 14 bits.
- Default HiFi only, single-threaded. Other cameras, v3, monochrome modes, lens correction, non-default noise/sharpening controls, compression and previews are not implemented.
- Deterministic project-defined row order and bounded feedback; numerical and metadata differences from the research reference are documented.
- M1 demosaic maximum errors: **198 / 191 / 128**, all strictly **<200**. Final tail PSNR: **92.58 / 92.07 / 105.50 dB**; maximum errors **728 / 510 / 176**. The <200 gate applies to M1, not the later nonlinear tail.
- Optimized local baseline: **197 tests passed**, including 12 private real-image integration cases. The public synthetic suite contains **185 tests**. Private images/oracles are excluded. See [validation](docs/PROGRESS.md).

On an i7-14650HX / Windows / Python 3.14 machine, full CLI medians over three runs were **8.17s / 8.12s / 23.07s**, about **2.1–2.4×** faster in API A/B measurements than the earlier implementation. Maximum 50MP working set was **1.642 GB**, peak commit **1.669 GB**. See [method, ranges and limitations](docs/PERFORMANCE.md).

## Develop and build

```sh
python -m pip install -e '.[dev]'
python -m pytest -q --ignore=tests/integration
python -m pip install -r requirements-build.txt
python -m build --no-isolation
python -m twine check --strict dist/*
python tools/validate_distribution.py dist/colorpipe-0.1.0.tar.gz dist/colorpipe-0.1.0-py3-none-any.whl
```

[BUILDING](docs/BUILDING.md) covers isolated wheel verification, Windows commands and optional private integration inputs. CI builds and tests installed wheels on Windows/Linux with Python 3.11/3.14. The pinned historical Windows environment in `requirements-m0.txt` is optional; use `.[dev]` for platform-appropriate dependencies.

## Documentation and license

- [Architecture](docs/ARCHITECTURE.md), [algorithm](docs/ALGORITHM.md), [validation history](docs/PROGRESS.md), [standalone package verification](docs/RELEASE.md)
- [Metadata differences](docs/METADATA_DIFFERENCES.md), [limitations](docs/LIMITATIONS.md), [roadmap](docs/PLAN.md)
- [Performance](docs/PERFORMANCE.md), [building](docs/BUILDING.md), [contributing](CONTRIBUTING.md)
- [MIT license](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md), [provenance](docs/LEGAL.md)

Independent, unofficial project; unaffiliated with OM Digital Solutions, Adobe or Iridient Digital. Algorithm research included examination of a proprietary converter; this is **not a clean-room claim**. Source provenance and the remaining legal/patent review boundary are disclosed in [LEGAL](docs/LEGAL.md). MIT covers this project's code, not dependencies or supplied profiles. Provided without warranty.
