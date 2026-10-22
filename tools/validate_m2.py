"""Predict RAW -> M1 -> default tail, then compare all available references."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np
import tifffile

from colorpipe.decode import load_raw
from colorpipe.normalize import normalize_cfa
from colorpipe.demosaic import demosaic_hifi
from colorpipe.tail import run_tail
from colorpipe.types import Settings
from validate_m1 import metrics, sha256
from m2_metrics import color_transform, delta_e_statistics, ssim_statistics

CONFIGURATIONS = {'20mp_orf': 'plain20', '20mp_ori': 'ori20', '50mp_orf': 'orf50'}


class FilteredReference:
    """Recover the pre-RL RGB lowpass from a G/DR/DB stage, test-only."""
    def __init__(self, diff):
        self.diff = diff

    def __getitem__(self, index):
        block = self.diff[index]
        green = block[..., 0]
        return np.stack([green + (2 * block[..., 1] - 1), green,
                         green + (2 * block[..., 2] - 1)], axis=-1)


def validate_case(fixture, acceptance, oracles, output, *, native_stages=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = Path(fixture['path'])
    if sha256(source) != fixture['sha256']:
        raise ValueError('fixture identity mismatch')
    acceptance = Path(acceptance)
    parent = json.loads(acceptance.read_text(encoding='utf-8'))
    config = CONFIGURATIONS[fixture['kind']]
    case = next(c for c in parent['cases'] if c['configuration'] == config)
    if case['source_sha256'] != fixture['sha256']:
        raise ValueError('reference source identity mismatch')
    index_path = Path(oracles) / config / 'index.json'
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if not index['test_only'] or index['source_sha256'] != fixture['sha256']:
        raise ValueError('stage reference identity mismatch')
    manifest_path = Path(case['manifest'])
    if sha256(manifest_path) != case['manifest_sha256']:
        raise ValueError('parent manifest identity mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    start = time.perf_counter()
    raw = load_raw(source)
    normalized = normalize_cfa(raw.cfa, raw)
    rgb = demosaic_hifi(normalized, raw, Settings())
    del normalized
    rgb.tofile(output / 'demosaic.u16')
    timings = {'decode_normalize_demosaic': time.perf_counter() - start}
    paths = {}
    last = time.perf_counter()

    def save(name, array):
        nonlocal last
        timings[name] = time.perf_counter() - last
        path = output / (name + ('.u16' if array.dtype == np.uint16 else '.f32'))
        array.tofile(path)
        paths[name] = path
        print(fixture['name'], name, flush=True)
        last = time.perf_counter()

    result = run_tail(rgb, raw, Settings(), stage_callback=save)
    shape = result.shape
    del rgb, result
    # No reference pixels are opened until all production predictions exist.
    if tuple(shape) != tuple(manifest['rgb_shape']):
        raise ValueError('processing shape mismatch')
    stages = {}
    for name, entry in index['stages'].items():
        if sha256(entry['path']) != entry['sha256'] or tuple(entry['shape']) != shape:
            raise ValueError('portable reference identity mismatch: ' + name)
        predicted = np.memmap(paths[name], mode='r', dtype='<f4', shape=shape)
        reference = np.memmap(entry['path'], mode='r', dtype='<f4', shape=shape)
        stages[name] = metrics(predicted, reference, peak=1)
        stages[name].update(reference_sha256=entry['sha256'], predicted_sha256=sha256(paths[name]),
                            reference_provenance=entry['provenance'], peak=1)
        if name == 'default_diff':
            lowpass = np.memmap(paths['filtered_rgb'], mode='r', dtype='<f4', shape=shape)
            stages['filtered_rgb'] = metrics(lowpass, FilteredReference(reference), peak=1)
            stages['filtered_rgb']['reference_provenance'] = 'algebraically reconstructed portable G/DR/DB; rounding may add one float ULP'
            del lowpass
        del predicted, reference
    pre_tail = np.memmap(output / 'demosaic.u16', mode='r', dtype='<u2', shape=shape)
    if sha256(index['pre_tail']) != manifest['pre_tail_sha256']:
        raise ValueError('pre-tail reference hash mismatch')
    pre_tail_reference = np.memmap(index['pre_tail'], mode='r', dtype='<u2', shape=shape)
    upstream = metrics(pre_tail, pre_tail_reference)
    del pre_tail, pre_tail_reference
    if sha256(case['output']) != case['output_file_sha256']:
        raise ValueError('final DNG reference identity mismatch')
    predicted = np.memmap(paths['quantized'], mode='r', dtype='<u2', shape=shape)
    reference = tifffile.memmap(case['output'], page=0, mode='r')
    if reference.shape != shape or reference.dtype != np.uint16:
        raise ValueError('final DNG pixel domain mismatch')
    final = metrics(predicted, reference)
    final['channels'] = {label: metrics(predicted[..., i], reference[..., i])
                         for i, label in enumerate(('R', 'G', 'B'))}
    final['predicted_sha256'] = sha256(paths['quantized'])
    ssim = ssim_statistics(predicted, reference)
    portable_path = Path(index['quantized']['path'])
    if sha256(portable_path) != index['quantized']['sha256']:
        raise ValueError('portable final reference hash mismatch')
    portable = np.memmap(portable_path, mode='r', dtype='<u2', shape=shape)
    portable_vs_native = metrics(portable, reference)
    del portable
    matrix, color_model = color_transform(case['output'])
    delta_e = delta_e_statistics(predicted, reference, matrix, output / 'delta_e00.f32')
    native = []
    if native_stages:
        for entry in json.loads(Path(native_stages).read_text(encoding='utf-8')):
            if entry['source_sha256'] != fixture['sha256']:
                continue
            if entry['pre_tail_sha256'] != manifest['pre_tail_sha256']:
                raise ValueError('native stage belongs to a different pre-tail input')
            if sha256(entry['path']) != entry['sha256']:
                raise ValueError('native stage hash mismatch')
            p = np.memmap(paths[entry['stage']], mode='r', dtype='<f4', shape=shape)
            r = np.memmap(entry['path'], mode='r', dtype='<f4', shape=tuple(entry['shape']))
            if entry['layout'] == 'CHW':
                r = r.transpose(1, 2, 0)
            if entry.get('channel') is not None:
                p = p[..., entry['channel']]
            statistic = metrics(p, r, peak=1)
            statistic.update(stage=entry['stage'], channel=entry.get('channel'), reference=entry)
            native.append(statistic)
            del p, r
    gates = dict(upstream_max_error_lt_200=upstream['max_abs_error'] < 200,
                 final_psnr_gt_40=final['psnr_db'] == 'inf' or final['psnr_db'] > 40,
                 final_ssim_gt_098=ssim['mean'] > .98,
                 delta_e_mean_lt_2=delta_e['mean'] < 2, delta_e_p95_lt_4=delta_e['p95'] < 4)
    del predicted, reference
    return dict(name=fixture['name'], source_sha256=fixture['sha256'],
                status='PASS' if all(gates.values()) else 'FAIL', gates=gates,
                stages=stages, final_rgb=final, final_ssim=ssim, delta_e00=delta_e, color_comparison=color_model,
                m1_pre_tail=upstream, portable_oracle_vs_native_final=portable_vs_native,
                native_stage_comparisons=native, timing_seconds=timings, output=str(output.resolve()),
                source_metadata=dict(wb=list(raw.wb), iso=raw.iso, pixel_scale=raw.pixel_scale,
                                     sensor_size=[raw.width, raw.height]),
                reference_dng=case['output'], reference_dng_sha256=case['output_file_sha256'],
                parent_manifest_sha256=sha256(manifest_path), stage_index_sha256=sha256(index_path),
                acceptance_sha256=sha256(acceptance),
                comparison_scope='PSNR/max/Delta E: all active pixels and borders; SSIM: all standard valid 7x7 window centers; no masks; final maximum recorded without inventing a new tail max-error gate',
                known_algorithm_differences=['M1 bounded feedback', 'analytic tone instead of knot spline',
                                             'portable division and sums', 'active-image edge replication',
                                             'all active green restored after RL; no aligned flat-prefix copy'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--oracles', type=Path, required=True)
    parser.add_argument('--native-stages', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))['fixtures']
    fixtures = [f for f in fixtures if not args.case or f['name'] in args.case]
    if not fixtures:
        parser.error('no matching fixtures')
    args.out.mkdir(parents=True, exist_ok=False)
    cases = []
    for fixture in fixtures:
        case = validate_case(fixture, args.acceptance, args.oracles, args.out / fixture['name'],
                             native_stages=args.native_stages)
        cases.append(case)
        print(json.dumps(dict(name=case['name'], status=case['status'],
                              psnr=case['final_rgb']['psnr_db'], maximum=case['final_rgb']['max_abs_error'],
                              ssim=case['final_ssim']['mean'],
                              delta_e=case['delta_e00']['mean'])), flush=True)
        complete = len(cases) == len(fixtures)
        report = dict(schema='colorpipe-m2-validation/v2', created_utc=datetime.now(timezone.utc).isoformat(),
                      status=('PASS' if all(c['status'] == 'PASS' for c in cases) else 'FAIL') if complete else 'INCOMPLETE',
                      expected_cases=[f['name'] for f in fixtures], cases=cases,
                      environment=dict(python=platform.python_version(), numpy=np.__version__),
                      scope='default color tail pixels; no new DNG container, DCP rendering or application-open validation',
                      source_hashes={p.name: sha256(p) for p in (Path(__file__).resolve().parents[1] / 'src/colorpipe').glob('*.py')},
                      tool_hashes={p.name: sha256(p) for p in (Path(__file__), Path(__file__).with_name('m2_metrics.py'))})
        (args.out / 'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
