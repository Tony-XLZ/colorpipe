"""TEST ONLY: materialize portable research-stage oracles, never production.

The handoff's parent manifests retain all stage hashes but not all pixel
files. Run the read-only independent reference on its own verified pre-tail
fixture in an isolated process. Replace hardware helpers with NumPy math;
no target binary, private DLL, injected machine code, or DCP is loaded.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import numpy as np

sys.dont_write_bytecode = True


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class PortableReciprocal:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __call__(self, value):
        return np.reciprocal(np.asarray(value, np.float32))


class PortableFused(PortableReciprocal):
    def __call__(self, a, b, c):
        return (np.asarray(a, np.float64) * np.asarray(b, np.float64)
                + np.asarray(c, np.float64)).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', choices=('plain20', 'ori20', 'orf50'), required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    rcp = types.ModuleType('host_rcpps')
    rcp.HostRcp = PortableReciprocal
    fused = types.ModuleType('host_fma')
    fused.np, fused.HostFma32 = np, PortableFused
    sys.modules['host_rcpps'], sys.modules['host_fma'] = rcp, fused
    sys.path.insert(0, str(args.reference_root))
    source = args.reference_root / 'tail.py'
    spec = importlib.util.spec_from_file_location('m2_test_reference_tail', source)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    acceptance = json.loads(args.acceptance.read_text(encoding='utf-8'))
    case = next(c for c in acceptance['cases'] if c['configuration'] == args.case)
    manifest_path = Path(case['manifest'])
    if sha(manifest_path) != case['manifest_sha256']:
        raise ValueError('reference parent manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rgb_path = manifest_path.parent / 'demosaic.rgb16'
    if sha(rgb_path) != manifest['pre_tail_sha256']:
        raise ValueError('reference pre-tail fixture hash mismatch')
    stages = {}

    def save(name, array):
        path = args.out / (name + '.f32')
        array.tofile(path)
        stages[name] = dict(path=str(path.resolve()), sha256=sha(path),
                            shape=list(array.shape), dtype=str(array.dtype),
                            provenance='portable independent research calculation on verified reference pre-tail fixture')
        print(args.case, name, flush=True)

    shape = tuple(manifest['rgb_shape'])
    rgb = np.memmap(rgb_path, mode='r', dtype='<u2', shape=shape)
    result = reference._run_tail_impl(rgb, manifest['tail_metadata'],
                                      {'chunk_rows': 32, 'stage_callback': save})
    target = args.out / 'quantized.u16'
    result.tofile(target)
    files = [source, args.reference_root / 'rl.py', args.reference_root / 'filter_adapter.py',
             args.reference_root / 'planar_layout.py', args.reference_root.parents[1] / 'phase4/filter_reference/filter_reference.py']
    report = dict(schema='colorpipe-m2-test-oracles/v1', test_only=True,
                  source_sha256=case['source_sha256'], parent_manifest=str(manifest_path),
                  parent_manifest_sha256=sha(manifest_path), pre_tail=str(rgb_path),
                  pre_tail_sha256=sha(rgb_path), stages=stages,
                  quantized=dict(path=str(target.resolve()), sha256=sha(target)),
                  reference_sources={str(p): sha(p) for p in files},
                  hardware_reciprocal=False, hardware_fma=False, target_code_executed=False,
                  note='Stage reference is portable research math; actual parent DNG remains the primary final-pixel oracle.')
    (args.out / 'index.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
