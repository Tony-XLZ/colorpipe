"""Audit local wheel/sdist structure, metadata and excluded assets; no upload."""

import argparse
import ast
import configparser
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inspect_distribution(path):
    path = Path(path)
    wheel = path.suffix == '.whl'
    errors = []
    if wheel:
        with zipfile.ZipFile(path) as archive:
            files = {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}
            links = [item.filename for item in archive.infolist() if stat.S_ISLNK(item.external_attr >> 16)]
        metadata_names = [name for name in files if name.endswith('.dist-info/METADATA')]
        prefix = metadata_names[0].split('/')[0] if len(metadata_names) == 1 else ''
        package = 'colorpipe/'
        notices = prefix + '/licenses/THIRD_PARTY_NOTICES.md'
        license_file = prefix + '/licenses/LICENSE'
        entry_points = prefix + '/entry_points.txt'
    else:
        with tarfile.open(path, 'r:gz') as archive:
            files = {item.name: archive.extractfile(item).read() for item in archive.getmembers() if item.isfile()}
            links = [item.name for item in archive.getmembers() if not (item.isfile() or item.isdir())]
        roots = {PurePosixPath(name).parts[0] for name in files}
        prefix = next(iter(roots)) if len(roots) == 1 else ''
        metadata_names = [prefix + '/PKG-INFO'] if prefix + '/PKG-INFO' in files else []
        package = prefix + '/src/colorpipe/'
        notices, license_file = prefix + '/THIRD_PARTY_NOTICES.md', prefix + '/LICENSE'
        entry_points = prefix + '/src/colorpipe.egg-info/entry_points.txt'
    if links:
        errors.append('archive contains links or special files: ' + ', '.join(links))
    for name in files:
        parts = PurePosixPath(name).parts
        unsafe = PurePosixPath(name).is_absolute() or '..' in parts or '\\' in name or ':' in name
        private = any(part.lower() in ('out', 'fixtures', '.venv', '.cache', '.git', '__pycache__', 'handoff') for part in parts)
        allowed_suffix = PurePosixPath(name).suffix.lower() in ('.py', '.md', '.txt', '.toml', '.cfg', '.yml', '.yaml')
        conventional = PurePosixPath(name).name in ('LICENSE', 'METADATA', 'WHEEL', 'RECORD', 'PKG-INFO', 'MANIFEST.in')
        example = name.endswith('/tests/fixtures.example.json')
        wheel_scope = (name.startswith('colorpipe/') and name.endswith('.py')) or name.startswith(prefix + '/')
        if unsafe or private or not (allowed_suffix or conventional or example) or (wheel and not wheel_scope):
            errors.append('unexpected distribution member: ' + name)
    required = [package + name for name in ('__init__.py', '__main__.py', 'cli.py', 'decode.py', 'pipeline.py', 'writer.py')]
    required += [notices, license_file, entry_points]
    if not wheel:
        required += [prefix + '/' + name for name in ('README.md', 'pyproject.toml', 'MANIFEST.in',
                     'requirements-build.txt', 'docs/BUILDING.md', 'docs/ALGORITHM.md', 'docs/LIMITATIONS.md',
                     'docs/LEGAL.md', 'tests/conftest.py', 'tests/dcp_helpers.py', 'tests/orf_factory.py',
                     'tests/fixtures.example.json', 'tests/integration/test_m3.py', 'tools/validate_m3.py',
                     'tools/validate_distribution.py')]
    errors.extend('missing distribution member: ' + name for name in required if not files.get(name))
    metadata = BytesParser().parsebytes(files[metadata_names[0]]) if len(metadata_names) == 1 else None
    dependencies = []
    version = None
    if metadata is None:
        errors.append('expected one core metadata file')
    else:
        version = metadata['Version']
        if metadata['Name'] != 'colorpipe' or not version:
            errors.append('invalid package identity')
        if metadata['License-Expression'] != 'MIT':
            errors.append('missing MIT license expression')
        if metadata['Description-Content-Type'] != 'text/markdown' or not metadata.get_payload().strip():
            errors.append('missing Markdown long description')
        for line in metadata.get_all('Requires-Dist', []):
            requirement = Requirement(line)
            if requirement.marker is None:
                dependencies.append(canonicalize_name(requirement.name))
        if not {'numpy', 'rawpy'}.issubset(dependencies):
            errors.append('default installation must include NumPy and rawpy')
        module = files.get(package + '__init__.py')
        if module:
            assignments = ast.parse(module).body
            declared = next((node.value.value for node in assignments if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
                             and isinstance(node.value, ast.Constant)), None)
            if declared != version:
                errors.append('package metadata and module versions differ')
    if entry_points in files:
        parser = configparser.ConfigParser()
        parser.read_string(files[entry_points].decode('utf-8'))
        if parser.get('console_scripts', 'orf2dng', fallback='') != 'colorpipe.cli:main':
            errors.append('missing orf2dng console entry point')
    return dict(path=str(path.resolve()), sha256=sha256(path), bytes=path.stat().st_size,
                kind='wheel' if wheel else 'sdist', version=version, files=len(files),
                runtime_dependencies=dependencies, status='FAIL' if errors else 'PASS', errors=errors)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifacts', nargs='+', type=Path)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    cases = [inspect_distribution(path) for path in args.artifacts]
    result = dict(schema='colorpipe-distribution-validation/v1',
                  status='PASS' if all(case['status'] == 'PASS' for case in cases) else 'FAIL', artifacts=cases)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    for case in cases:
        print(case['kind'], case['status'], case['errors'])
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
