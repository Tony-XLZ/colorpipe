# Third-party dependency inventory

colorpipe's wheel contains its own Python implementation under the MIT license
(see LICENSE). NumPy and rawpy are separately resolved runtime distributions,
not vendored in this wheel. No implementation, binary, profile, or captured
image from the proprietary converter is bundled here.

| Runtime dependency | Upstream license | Project |
|---|---|---|
| NumPy | BSD-3-Clause, with additional notices for bundled wheel libraries | https://numpy.org/ |
| rawpy | MIT; its LibRaw dependency has separate terms | https://github.com/letmaik/rawpy |
| LibRaw (inside the upstream rawpy distribution) | LGPL-2.1 / CDDL-1.0 upstream; tested rawpy wheel carries LICENSE.LibRaw (LGPL-2.1) | https://www.libraw.org/ |

The tested rawpy 0.27.1 distribution carries licenses/LICENSE (MIT) and
licenses/LICENSE.LibRaw (LGPL-2.1) in its dist-info directory; see also its
[upstream license documentation](https://github.com/letmaik/rawpy#license).
NumPy's own distribution carries its license and bundled-library notices.
Installing dependencies does not relicense them under colorpipe's MIT terms.
Redistributing those dependencies or an executable bundle requires a separate
review of their actual contents, licenses and corresponding-source obligations.
This release does not produce such a bundle.

Development/test dependencies include tifffile (BSD-3-Clause), Pillow 13.0.0
(MIT-CMU), scikit-image (primarily BSD-3-Clause, with file-specific notices),
pytest (MIT) and packaging (Apache-2.0 OR BSD-2-Clause), with transitive
dependencies. Exact tested versions are in requirements-m0.txt;
separate build/check tools are in requirements-build.txt. Their installed
upstream license texts apply; their implementation is not copied into colorpipe.

Metadata field identities were checked against the public TIFF/EXIF conventions
and https://exiftool.org/TagNames/Olympus.html . No ExifTool implementation is
copied or required at runtime. The metadata reader is a new, bounded reader for
this camera. The recovered pixel-scale rule and supported source units are
documented in `docs/ARCHITECTURE.md` and the private research handoff.

M3 implements a small TIFF/DNG metadata codec without an Adobe DNG SDK or
third-party writer implementation. Public field reference: Adobe DNG
Specification 1.7.1. No vendor DCP is bundled; synthetic test profiles are
generated locally. Camera calibration scalar provenance is recorded in
`docs/LEGAL.md`.

Optional external validation uses separately supplied RawTherapee 5.13 and
darktable 5.6.2 command-line programs under their upstream GPL terms. These
programs and their source are not bundled or imported by colorpipe. Public
processing-parameter documentation was used to invoke their file interfaces.
Image verification uses the existing Pillow/scikit-image development
environment. These tools are optional and do not become production dependencies.

M4 wheel and sdist both include LICENSE and this notice. The source distribution
adds only project documentation, source, tests, validation tools and path examples;
it does not contain user media, vendor profiles, reference implementations,
external applications or native libraries. Actual archive checks and hashes are
recorded in out/m4/distribution-validation.json in the local validation workspace.
This engineering inventory does not conclude the legal/patent review recorded
as pending in docs/LEGAL.md.
