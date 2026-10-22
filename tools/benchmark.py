"""Benchmark isolated RAW conversions, source identity and process peak memory.

Multiple --python paths alternate order across repeats for an A/B comparison.
All conversion inputs are the user RAW and DCP; references are checked afterward.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def peak_memory():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                    'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return dict(peak_working_set_bytes=counters.PeakWorkingSetSize,
                    peak_commit_bytes=counters.PeakPagefileUsage, model='Windows process lifetime peak counters')
    import resource
    scale = 1 if sys.platform == 'darwin' else 1024
    return dict(peak_working_set_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale,
                peak_commit_bytes=None, model='getrusage process lifetime peak RSS')


def worker(args):
    import colorpipe
    import numpy as np
    import rawpy
    from colorpipe.pipeline import convert_raw
    from colorpipe.types import Settings

    start, cpu = time.perf_counter(), time.process_time()
    output = convert_raw(args.input, args.output, Settings(profile=str(args.profile)))
    elapsed, cpu_elapsed = time.perf_counter() - start, time.process_time() - cpu
    memory = peak_memory()
    package = Path(colorpipe.__file__).parent
    report = dict(conversion_seconds=elapsed, cpu_seconds=cpu_elapsed, memory=memory,
                  output=str(output), output_sha256=sha256(output), executable=sys.executable,
                  package=str(package), python=platform.python_version(), numpy=np.__version__,
                  rawpy=rawpy.__version__, libraw=rawpy.libraw_version,
                  source_hashes={path.name: sha256(path) for path in package.glob('*.py')})
    args.result.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--python', action='append', type=Path, help='backend interpreter; repeat for A/B')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--expected-report', type=Path, help='optional existing validation report with output_sha256')
    parser.add_argument('--case', action='append', help='fixture name; default is all fixtures')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    for name in ('input', 'output', 'result'):
        parser.add_argument('--' + name, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if not all((args.input, args.output, args.result)):
            parser.error('worker needs input, output and result')
        worker(args)
        return 0
    if not args.fixtures or not args.out or args.repeats < 1:
        parser.error('fixtures, a new out directory and positive repeats are required')
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))['fixtures']
    fixtures = [case for case in fixtures if not args.case or case['name'] in args.case]
    if not fixtures:
        parser.error('no matching fixtures')
    for case in fixtures:
        if sha256(case['path']) != case['sha256']:
            raise ValueError('RAW identity mismatch: ' + case['name'])
    expected = {}
    if args.expected_report:
        expected = {case['name']: case['output_sha256'] for case in
                    json.loads(args.expected_report.read_text(encoding='utf-8'))['cases']}
        if not all(case['name'] in expected for case in fixtures):
            parser.error('expected report must cover each selected fixture')
    backends = [str(path.resolve()) for path in (args.python or [Path(sys.executable)])]
    args.out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    report = dict(schema='colorpipe-performance/v1', status='INCOMPLETE', backends=backends,
                  platform=platform.platform(), processor=platform.processor(), repeats=args.repeats,
                  profile_sha256=sha256(args.profile), runs=[], summaries=[],
                  timing_scope='API RAW-to-DNG, including decode/validation/write; excludes process startup, imports and proof hashing; no stage callbacks or profiler',
                  wall_scope='Worker lifetime including imports, memory probe and proof hashing; not a CLI latency measurement')
    report_path = args.out / 'benchmark.json'
    for repeat in range(args.repeats):
        for case in fixtures:
            order = range(len(backends)) if repeat % 2 == 0 else reversed(range(len(backends)))
            for backend in order:
                directory = args.out / f"{case['name']}-backend{backend}-run{repeat}"
                directory.mkdir()
                result = directory / 'result.json'
                command = [backends[backend], '-I', '-B', str(Path(__file__).resolve()), '--worker',
                           '--input', case['path'], '--output', str((directory / 'output.dng').resolve()),
                           '--profile', str(args.profile.resolve()), '--result', str(result.resolve())]
                start = time.perf_counter()
                with (directory / 'worker.log').open('w', encoding='utf-8') as log:
                    completed = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                if completed.returncode:
                    raise RuntimeError('conversion failed; see ' + str(directory / 'worker.log'))
                row = json.loads(result.read_text(encoding='utf-8'))
                row.update(name=case['name'], backend=backend, repeat=repeat, command=command,
                           worker_wall_seconds=time.perf_counter() - start,
                           expected_sha256=expected.get(case['name']))
                row['matches_expected'] = None if not expected else row['output_sha256'] == expected[case['name']]
                report['runs'].append(row)
                report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                print(case['name'], backend, repeat, f"{row['conversion_seconds']:.3f}s", row['matches_expected'], flush=True)
    for backend in range(len(backends)):
        for case in fixtures:
            rows = [row for row in report['runs'] if row['backend'] == backend and row['name'] == case['name']]
            report['summaries'].append(dict(name=case['name'], backend=backend,
                median_seconds=statistics.median(row['conversion_seconds'] for row in rows),
                minimum_seconds=min(row['conversion_seconds'] for row in rows),
                maximum_seconds=max(row['conversion_seconds'] for row in rows),
                maximum_peak_working_set_bytes=max(row['memory']['peak_working_set_bytes'] for row in rows),
                maximum_peak_commit_bytes=max((row['memory']['peak_commit_bytes'] for row in rows
                                               if row['memory']['peak_commit_bytes'] is not None), default=None),
                repeated_output_exact=len({row['output_sha256'] for row in rows}) == 1,
                source_identity_constant=len({json.dumps(row['source_hashes'], sort_keys=True)
                                              for row in rows}) == 1))
    passed = (all(row['matches_expected'] is not False for row in report['runs'])
              and all(row['repeated_output_exact'] and row['source_identity_constant']
                      for row in report['summaries']))
    report['status'] = 'PASS' if passed else 'FAIL'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
