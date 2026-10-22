"""Validate independently generated DNG pixels, key metadata and user DCPs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import tifffile

from colorpipe.dcp import load_dcp
from colorpipe.pipeline import convert_raw
from colorpipe.types import Settings
from m2_metrics import color_transform, delta_e_statistics, ssim_statistics
from validate_m1 import metrics, sha256
from validate_m2 import CONFIGURATIONS


KEY_TAGS = (254, 256, 257, 258, 259, 262, 271, 272, 274, 277, 284,
            50706, 50708, 50713, 50714, 50717, 50718, 50719, 50720,
            50721, 50722, 50723, 50724, 50727, 50728, 50730, 50731,
            50732, 50734, 50778, 50779, 50829, 50931, 50932, 50934, 50936)


def value(tag):
    if int(tag.dtype) in (5, 10):
        a = np.asarray(tag.value, np.float64).reshape(-1, 2)
        return (a[:, 0] / a[:, 1]).tolist()
    v = tag.value
    if isinstance(v, bytes):
        return list(v)
    if isinstance(v, str):
        return v
    return np.asarray(v).tolist()


def metadata_comparison(output, reference, profile):
    critical, differences, payloads = [], [], []
    with tifffile.TiffFile(output) as actual, tifffile.TiffFile(reference) as expected:
        a, b = actual.pages[0].tags, expected.pages[0].tags
        for code in KEY_TAGS:
            av, bv = value(a[code]) if code in a else None, value(b[code]) if code in b else None
            critical.append(dict(tag=code, name=a[code].name if code in a else str(code),
                                 predicted=av, reference=bv, equal=code in a and code in b and av == bv))
        for code in sorted(set(a.keys()) | set(b.keys())):
            if code in a and code in b:
                same = int(a[code].dtype) == int(b[code].dtype) and a[code].count == b[code].count and value(a[code]) == value(b[code])
            else:
                same = False
            if not same:
                differences.append(dict(tag=code, name=(a[code] if code in a else b[code]).name,
                                        predicted_type_count=[int(a[code].dtype), a[code].count] if code in a else None,
                                        reference_type_count=[int(b[code].dtype), b[code].count] if code in b else None))
        for code, entry in sorted(profile.fields.items()):
            tag = a.get(code)
            data = b''
            if tag is not None:
                actual.filehandle.seek(tag.valueoffset)
                data = actual.filehandle.read(tag.valuebytecount)
            payloads.append(dict(tag=code, type=entry.kind, count=entry.count,
                                 source_value_sha256=hashlib.sha256(entry.data).hexdigest(),
                                 output_value_sha256=hashlib.sha256(data).hexdigest(),
                                 exact=tag is not None and int(tag.dtype) == entry.kind and tag.count == entry.count and data == entry.data))
    return dict(critical_tags=critical, container_differences=differences, dcp_payloads=payloads,
                scope='key semantic values and exact canonical little-endian DCP value bytes; no complete EXIF/XMP equality')


def validate_case(fixture, acceptance, oracles, profile_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if sha256(fixture['path']) != fixture['sha256']:
        raise ValueError('fixture identity mismatch')
    parent = json.loads(Path(acceptance).read_text(encoding='utf-8'))
    config = CONFIGURATIONS[fixture['kind']]
    case = next(c for c in parent['cases'] if c['configuration'] == config)
    if case['source_sha256'] != fixture['sha256'] or sha256(case['manifest']) != case['manifest_sha256']:
        raise ValueError('reference manifest identity mismatch')
    manifest = json.loads(Path(case['manifest']).read_text(encoding='utf-8'))
    index_path = Path(oracles) / config / 'index.json'
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if index['source_sha256'] != fixture['sha256'] or not index['test_only']:
        raise ValueError('pre-tail reference identity mismatch')
    profile = load_dcp(profile_path)
    stage_hashes = {}

    def observe(name, array):
        digest = hashlib.sha256()
        for top in range(0, len(array), 64):
            digest.update(np.ascontiguousarray(array[top:top + 64]).tobytes())
        stage_hashes[name] = digest.hexdigest()
        if name in ('pass4', 'quantized'):
            array.tofile(output / (name + '.u16'))

    start = time.perf_counter()
    path = convert_raw(fixture['path'], output / 'prediction.dng', Settings(profile=str(profile_path)), stage_callback=observe)
    elapsed = time.perf_counter() - start
    print(fixture['name'], 'DNG written', flush=True)
    # All production predictions, including the container, exist before reading oracle pixels.
    shape = tuple(manifest['rgb_shape'])
    pixels = tifffile.memmap(path, page=0, mode='r')
    if pixels.shape != shape or pixels.dtype != np.uint16:
        raise ValueError('DNG processing domain mismatch')
    tail = np.memmap(output / 'quantized.u16', mode='r', dtype='<u2', shape=shape)
    roundtrip = metrics(pixels, tail)
    del tail
    if sha256(index['pre_tail']) != manifest['pre_tail_sha256'] or sha256(case['output']) != case['output_file_sha256']:
        raise ValueError('reference pixel identity mismatch')
    demosaic = np.memmap(output / 'pass4.u16', mode='r', dtype='<u2', shape=shape)
    pre_reference = np.memmap(index['pre_tail'], mode='r', dtype='<u2', shape=shape)
    upstream = metrics(demosaic, pre_reference)
    del demosaic, pre_reference
    reference = tifffile.memmap(case['output'], page=0, mode='r')
    final = metrics(pixels, reference)
    ssim = ssim_statistics(pixels, reference)
    matrix, color_model = color_transform(case['output'])
    delta_e = delta_e_statistics(pixels, reference, matrix, output / 'delta_e00.f32')
    del pixels, reference
    metadata = metadata_comparison(path, case['output'], profile)
    gates = dict(pixel_roundtrip_exact=roundtrip['max_abs_error'] == 0,
                 key_metadata_equal=all(t['equal'] for t in metadata['critical_tags']),
                 dcp_payloads_exact=all(t['exact'] for t in metadata['dcp_payloads']),
                 m1_max_lt_200=upstream['max_abs_error'] < 200,
                 m2_psnr_gt_40=final['psnr_db'] == 'inf' or final['psnr_db'] > 40,
                 m2_ssim_gt_098=ssim['mean'] > .98,
                 matrix_delta_e_mean_lt_2=delta_e['mean'] < 2,
                 matrix_delta_e_p95_lt_4=delta_e['p95'] < 4)
    return dict(name=fixture['name'], status='PASS' if all(gates.values()) else 'FAIL', gates=gates,
                source=str(Path(fixture['path']).resolve()), source_sha256=fixture['sha256'],
                output=str(path), output_sha256=sha256(path), shape=list(shape),
                profile=dict(source=profile.source, sha256=profile.sha256, name=profile.name),
                reference_dng=case['output'], reference_dng_sha256=case['output_file_sha256'],
                acceptance_sha256=sha256(acceptance), parent_manifest_sha256=sha256(case['manifest']),
                stage_index_sha256=sha256(index_path), stage_sha256=stage_hashes,
                pixel_roundtrip=roundtrip, m1_pre_tail=upstream, final_rgb=final,
                final_ssim=ssim, delta_e00=delta_e, color_comparison=color_model,
                metadata=metadata, conversion_seconds=elapsed,
                scope='DNG writer + user DCP embedding; external rendering and application-open tests require their separate report')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('fixtures', 'acceptance', 'oracles', 'profile', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))['fixtures']
    cases = []
    for fixture in fixtures:
        result = validate_case(fixture, args.acceptance, args.oracles, args.profile, args.out / fixture['name'])
        cases.append(result)
        complete = len(cases) == len(fixtures)
        report = dict(schema='colorpipe-m3-validation/v1', created_utc=datetime.now(timezone.utc).isoformat(),
                      status=('PASS' if all(c['status'] == 'PASS' for c in cases) else 'FAIL') if complete else 'INCOMPLETE',
                      cases=cases, source_hashes={f.name: sha256(f) for f in (Path(__file__).resolve().parents[1] / 'src/colorpipe').glob('*.py')},
                      tool_sha256=sha256(__file__))
        (args.out / 'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        print(result['name'], result['status'], result['gates'], flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
