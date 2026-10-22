"""Index existing read-only native stages; never capture or run target code."""

import argparse
import json
import math
from pathlib import Path

from validate_m1 import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--runtime20', type=Path, required=True)
    parser.add_argument('--runtime50-filter', type=Path, required=True)
    parser.add_argument('--runtime50-tail', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads(args.acceptance.read_text(encoding='utf-8'))
    entries = []
    for config in ('plain20', 'orf50'):
        case = next(c for c in parent['cases'] if c['configuration'] == config)
        manifest_path = Path(case['manifest'])
        if sha256(manifest_path) != case['manifest_sha256']:
            raise ValueError('parent manifest hash mismatch')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        h, w, _ = manifest['rgb_shape']
        if config == 'plain20':
            base = args.runtime20
            source = base / 'norm_001_input.rgb16'
            specifications = [('normalized', None, base / 'norm_001_output.f32le', 'CHW', (3, h, w)),
                              ('default_diff', None, base / 'tail_001_output.f32le', 'CHW', (3, h, w)),
                              ('weighted_tone', 1, base / 'filter_001_input.f32le', 'HW', (h, w)),
                              ('filtered_rgb', 1, base / 'filter_001_output.f32le', 'HW', (h, w))]
        else:
            base = args.runtime50_filter
            source = base / 'demosaic.rgb16'
            specifications = [('normalized', 1, base / 'normalized_G.f32le', 'HW', (h, w)),
                              ('weighted_tone', 1, base / 'tone_G.f32le', 'HW', (h, w)),
                              ('filtered_rgb', 1, base / 'lowpass_G.f32le', 'HW', (h, w)),
                              ('default_deconvolved', 0, args.runtime50_tail / 'rl_1_output.f32le', 'HW', (h, w))]
        if sha256(source) != manifest['pre_tail_sha256']:
            raise ValueError('native stages belong to another pre-tail fixture')
        for stage, channel, path, layout, shape in specifications:
            if path.stat().st_size != 4 * math.prod(shape):
                raise ValueError('native stage size mismatch')
            entries.append(dict(source_sha256=case['source_sha256'],
                                pre_tail_sha256=manifest['pre_tail_sha256'], stage=stage,
                                channel=channel, path=str(path.resolve()), sha256=sha256(path),
                                layout=layout, shape=shape,
                                provenance='existing native stage; complete source pre-tail identity independently verified'))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(entries, stream, indent=2)
        stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
