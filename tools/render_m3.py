"""Headless external DCP rendering and DNG application compatibility checks.

This is validation tooling, never a production conversion dependency. Supply
official RawTherapee/darktable CLIs; their state and all outputs stay in --out.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
from skimage.color import deltaE_ciede2000, rgb2lab
import tifffile

from m2_metrics import ssim_statistics
from validate_m1 import metrics, sha256


def rendered_delta_statistics(predicted, reference, output):
    h, w = predicted.shape[:2]
    values = np.memmap(output, mode='w+', dtype='<f4', shape=(h, w))
    total, maximum = 0., 0.
    for top in range(0, h, 32):
        a, b = [rgb2lab(x[top:top + 32].astype(np.float64) / 65535, illuminant='D65', observer='2')
                for x in (predicted, reference)]
        delta = deltaE_ciede2000(a, b)
        if not np.isfinite(delta).all():
            raise ValueError('nonfinite rendered Delta E')
        values[top:top + len(delta)] = delta
        total += float(delta.sum())
        maximum = max(maximum, float(delta.max()))
    values.flush()
    p95, p99 = np.quantile(values, [.95, .99]).tolist()
    del values
    return dict(mean=total / (h * w), p95=p95, p99=p99, maximum=maximum, samples=h * w,
                model='common RTv4_sRGB output decoded as standard sRGB to Lab D65/2deg, CIEDE2000',
                scope='all rendered pixels, full-resolution float32 quantile map, no mask or exposure fit')


def pp3(profile, *, disabled=None, illuminant=0):
    enabled = lambda key: 'false' if disabled == key else 'true'
    return f'''[Version]
AppVersion=5.13
Version=352

[Exposure]
Auto=false
Compensation=0
Brightness=0
Contrast=0
Saturation=0
Black=0
HighlightCompr=0
ShadowCompr=0

[White Balance]
Enabled=true
Setting=Camera

[Color Management]
InputProfile={profile}
ToneCurve={enabled('ToneCurve')}
ApplyLookTable={enabled('ApplyLookTable')}
ApplyBaselineExposureOffset=true
ApplyHueSatMap={enabled('ApplyHueSatMap')}
DCPIlluminant={illuminant}
WorkingProfile=ProPhoto
OutputProfile=RTv4_sRGB
OutputProfileIntent=Relative
OutputBPC=false

[Sharpening]
Enabled=false
[PostDemosaicSharpening]
Enabled=false
[PostResizeSharpening]
Enabled=false
[Impulse Denoising]
Enabled=false
[Directional Pyramid Denoising]
Enabled=false
[Defringing]
Enabled=false
[Resize]
Enabled=false
[Crop]
Enabled=false
'''


def execute(command, log, env, cwd, *, allowed=(0,)):
    with Path(log).open('wb') as stream:
        completed = subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT,
                                   env=env, cwd=cwd, timeout=600)
    result = dict(command=list(map(str, command)), exit_code=completed.returncode,
                  log=str(log), log_sha256=sha256(log))
    if completed.returncode not in allowed:
        raise RuntimeError(f'external command failed ({completed.returncode}); see {log}')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'rawtherapee', 'darktable', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    args.out = args.out.resolve()
    args.rawtherapee, args.darktable = args.rawtherapee.resolve(), args.darktable.resolve()
    source = json.loads(args.report.read_text(encoding='utf-8'))
    if source['status'] != 'PASS' or len(source['cases']) != 3:
        p.error('a completed three-case M3 writer report is required')
    args.out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    state = args.out / 'state'
    for name in ('tmp', 'rt-settings', 'rt-cache', 'appdata', 'localappdata', 'dt-config', 'dt-cache'):
        (state / name).mkdir(parents=True)
    env.update(TEMP=str(state / 'tmp'), TMP=str(state / 'tmp'), RT_SETTINGS=str(state / 'rt-settings'),
               RT_CACHE=str(state / 'rt-cache'), APPDATA=str(state / 'appdata'), LOCALAPPDATA=str(state / 'localappdata'),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', GSETTINGS_BACKEND='memory')
    (state / 'rt-settings/options').write_text('[General]\nVerbose=true\n', encoding='utf-8')
    report = dict(schema='colorpipe-m3-external-validation/v1', created_utc=datetime.now(timezone.utc).isoformat(),
                  status='INCOMPLETE', source_report_sha256=sha256(args.report), tool_sha256=sha256(__file__),
                  executables={name: dict(path=str(exe), sha256=sha256(exe)) for name, exe in
                               (('rawtherapee', args.rawtherapee), ('darktable', args.darktable))},
                  processing_scope='RawTherapee full available DCP operations enabled; darktable tests reading only, without claiming DCP LUT parity',
                  cases=[])
    # This Windows build returns -1 (reported as unsigned by subprocess) for
    # successful help. Rendering itself must still return zero.
    report['rawtherapee_help'] = execute([args.rawtherapee, '-h'], args.out / 'rawtherapee-help.log', env, args.out,
                                        allowed=(0, 1, -1, 2 ** 32 - 1))
    report['darktable_version'] = execute([args.darktable, '--version'], args.out / 'darktable-version.log', env, args.out)

    for index, case in enumerate(source['cases']):
        if sha256(case['output']) != case['output_sha256'] or sha256(case['reference_dng']) != case['reference_dng_sha256']:
            raise ValueError('DNG identity changed since writer validation')
        directory = args.out / case['name']
        directory.mkdir()
        operations = []

        def render(label, input_path, profile='(embedded)', **options):
            recipe = directory / (label + '.pp3')
            recipe.write_text(pp3(profile, **options), encoding='utf-8')
            output = directory / (label + '.tif')
            operation = execute([args.rawtherapee, '-o', output, '-q', '-p', recipe, '-t', '-b16', '-c', input_path],
                                directory / (label + '.log'), env, args.out)
            log = Path(operation['log']).read_text(encoding='utf-8', errors='replace')
            if "Can't load DCP profile" in log:
                raise RuntimeError('RawTherapee fell back from the requested DCP')
            image = tifffile.memmap(output, page=0, mode='r')
            if image.dtype != np.uint16 or image.ndim != 3 or image.shape[-1] != 3:
                raise ValueError('expected a 16-bit RGB TIFF render')
            operation.update(output=str(output), recipe_sha256=sha256(recipe), output_sha256=sha256(output), shape=list(image.shape))
            operations.append(operation)
            print(case['name'], label, 'rendered', flush=True)
            return image

        predicted = render('embedded', case['output'])
        reference = render('reference', case['reference_dng'])
        explicit = render('explicit', case['output'], 'file:' + Path(case['profile']['source']).as_posix())
        if predicted.shape != reference.shape or predicted.shape != explicit.shape:
            raise ValueError('rendered image domains do not match')
        final, embedded_vs_explicit = metrics(predicted, reference), metrics(predicted, explicit)
        ssim = ssim_statistics(predicted, reference)
        delta = rendered_delta_statistics(predicted, reference, directory / 'delta_e00.f32')
        probes = []
        if index == 0:
            for flag in ('ApplyHueSatMap', 'ApplyLookTable', 'ToneCurve'):
                disabled = render('without-' + flag, case['output'], disabled=flag)
                probes.append(dict(disabled=flag, difference_from_full=metrics(disabled, predicted)))
                del disabled
            for illuminant in (1, 2):
                forced = render('illuminant-' + str(illuminant), case['output'], illuminant=illuminant)
                probes.append(dict(forced_illuminant=illuminant, difference_from_auto=metrics(forced, predicted)))
                del forced
        del predicted, reference, explicit
        jpeg = directory / 'darktable.jpg'
        operation = execute([args.darktable, Path(case['output']).as_posix(), jpeg.as_posix(), '--apply-custom-presets', 'false', '--core',
                             '--configdir', (state / 'dt-config').as_posix(), '--cachedir', (state / 'dt-cache').as_posix(), '--tmpdir', (state / 'tmp').as_posix(),
                             '--library', ':memory:', '--disable-opencl', '--conf', 'write_sidecar_files=never'],
                            directory / 'darktable.log', env, args.out)
        with Image.open(jpeg) as image:
            extrema = image.convert('RGB').getextrema()
            opened = image.width > 0 and image.height > 0 and any(low != high for low, high in extrema)
            operation.update(output=str(jpeg), output_sha256=sha256(jpeg), size_wh=list(image.size), extrema=extrema)
        operations.append(operation)
        gates = dict(embedded_matches_explicit=embedded_vs_explicit['max_abs_error'] == 0,
                     rendered_psnr_gt_40=final['psnr_db'] == 'inf' or final['psnr_db'] > 40,
                     rendered_ssim_gt_098=ssim['mean'] > .98, rendered_delta_e_mean_lt_2=delta['mean'] < 2,
                     rendered_delta_e_p95_lt_4=delta['p95'] < 4, darktable_opened=opened,
                     dcp_components_observed=all(probe['difference_from_full']['mismatches'] > 0 for probe in probes if 'disabled' in probe))
        result = dict(name=case['name'], status='PASS' if all(gates.values()) else 'FAIL', gates=gates,
                      full_render=final, ssim=ssim, delta_e00=delta, embedded_vs_explicit=embedded_vs_explicit,
                      dcp_component_probes=probes, operations=operations)
        report['cases'].append(result)
        if len(report['cases']) == len(source['cases']):
            report['status'] = 'PASS' if all(c['status'] == 'PASS' for c in report['cases']) else 'FAIL'
        (args.out / 'validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        print(case['name'], result['status'], final['psnr_db'], delta['mean'], flush=True)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
