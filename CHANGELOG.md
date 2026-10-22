# Changelog

## Unreleased

- Add `docs/REVERSE_ENGINEERING.md`: observed binary identity, dependency stack, module map, external interfaces and the measured DNG output contract of the studied converter. Documentation only; no shipped code, no vendor assets.

## 0.1.0

First standalone public source package, exported from the optimized `perf-hifi` milestone.

- OM-1 Mark II ORF/ORI decoding and bounded metadata validation via rawpy/LibRaw.
- Project-defined deterministic four-pass HiFi demosaicing with bounded feedback.
- Default WB/tone/filter/G-only Richardson–Lucy color tail.
- Uncompressed camera-linear RGB16 DNG with an explicitly supplied compatible DCP.
- Optimized slice access, five-value sorting and temporary buffers, retaining baseline numerical behavior.
- 185 public synthetic tests, 12 optional private real-image cases, distribution audit and Windows/Linux CI.

Coverage, performance, metadata differences and provenance are documented in docs/. Private fixtures and vendor assets are excluded.
