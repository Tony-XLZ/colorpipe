"""TEST ONLY same-input tail diagnostic; never a fresh-RAW acceptance result."""

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile

from colorpipe.decode import load_raw
from colorpipe.tail import run_tail
from colorpipe.types import Settings
from validate_m1 import metrics, sha256
from validate_m2 import CONFIGURATIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--oracles', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    parent = json.loads(args.acceptance.read_text(encoding='utf-8'))
    cases = []
    for fixture in json.loads(args.fixtures.read_text(encoding='utf-8'))['fixtures']:
        config = CONFIGURATIONS[fixture['kind']]
        case = next(c for c in parent['cases'] if c['configuration'] == config)
        index = json.loads((args.oracles / config / 'index.json').read_text(encoding='utf-8'))
        if sha256(fixture['path']) != fixture['sha256'] or sha256(index['pre_tail']) != index['pre_tail_sha256']:
            raise ValueError('fixture identity mismatch')
        raw = load_raw(fixture['path'])
        shape = (raw.processing_size[1], raw.processing_size[0], 3)
        # Explicit test-only use of a fixed reference stage isolates tail math
        # from upstream M1. Production and the acceptance tool cannot do this.
        source = np.memmap(index['pre_tail'], mode='r', dtype='<u2', shape=shape)
        folder = args.out / fixture['name']
        folder.mkdir()
        paths = {}

        def save(name, array):
            path = folder / (name + ('.u16' if array.dtype == np.uint16 else '.f32'))
            array.tofile(path)
            paths[name] = path

        result = run_tail(source, raw, Settings(), stage_callback=save)
        del result, source
        stages = {}
        for name, entry in index['stages'].items():
            if sha256(entry['path']) != entry['sha256']:
                raise ValueError('stage oracle hash mismatch')
            a = np.memmap(paths[name], mode='r', dtype='<f4', shape=shape)
            b = np.memmap(entry['path'], mode='r', dtype='<f4', shape=shape)
            stages[name] = metrics(a, b, peak=1)
            del a, b
        if sha256(case['output']) != case['output_file_sha256']:
            raise ValueError('final oracle hash mismatch')
        a = np.memmap(paths['quantized'], mode='r', dtype='<u2', shape=shape)
        b = tifffile.memmap(case['output'], page=0, mode='r')
        final = metrics(a, b)
        inner = metrics(a[8:-8, 8:-8], b[8:-8, 8:-8])
        del a, b
        record = dict(name=fixture['name'], test_only=True, stages=stages, final_rgb=final,
                      interior_excluding_8px_diagnostic_only=inner,
                      input_reference_sha256=index['pre_tail_sha256'],
                      scope='same pre-tail input isolates analytic tone/filter/RL/layout differences; never production acceptance')
        cases.append(record)
        (args.out / 'diagnostics.json').write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(name=fixture['name'], psnr=final['psnr_db'], maximum=final['max_abs_error'],
                              interior_max=inner['max_abs_error'])), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
