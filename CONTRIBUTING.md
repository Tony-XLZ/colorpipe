# Contributing

Use Python 3.11+ and install `python -m pip install -e '.[dev]'`. Run `python -m pytest -q --ignore=tests/integration` before submitting a change; build and audit distributions as described in [BUILDING](docs/BUILDING.md).

For numerical changes, explain input units, arithmetic order, boundaries and deterministic row behavior. Preserve the M1 strict maximum-error gate and record measured stage differences. Prefer small synthetic regression inputs. Private real-image tests require external fixtures and oracles; see [validation](docs/PROGRESS.md).

Do not commit user photographs, output DNGs, vendor DCPs, binaries, captured buffers, credentials or proprietary/reference source. Use synthetic profiles and generated CFA fixtures. Issue reports should include the camera, bit depth, ISO, dependency versions and error text with personal metadata and local paths removed. Share images only with permission to distribute them.

Record the source and license of new algorithms, constants and dependencies. MIT does not replace third-party terms. The provenance and pending review boundary are in [LEGAL](docs/LEGAL.md).
