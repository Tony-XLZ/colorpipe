from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from validate_distribution import inspect_distribution


def make_wheel(path, *, extra=None, rawpy_default=True, notice=True):
    root = Path(__file__).resolve().parents[1]
    prefix = 'colorpipe-0.1.0.dist-info/'
    metadata = ('Metadata-Version: 2.4\nName: colorpipe\nVersion: 0.1.0\n'
                'License-Expression: MIT\nDescription-Content-Type: text/markdown\n'
                'Requires-Dist: numpy>=2.0\nRequires-Dist: rawpy>=0.20'
                + ('' if rawpy_default else '; extra == "decode"') + '\n\n# colorpipe\n')
    with zipfile.ZipFile(path, 'w') as archive:
        for source in (root / 'src/colorpipe').glob('*.py'):
            archive.write(source, 'colorpipe/' + source.name)
        archive.writestr(prefix + 'METADATA', metadata)
        archive.writestr(prefix + 'entry_points.txt', '[console_scripts]\norf2dng = colorpipe.cli:main\n')
        archive.write(root / 'LICENSE', prefix + 'licenses/LICENSE')
        if notice:
            archive.write(root / 'THIRD_PARTY_NOTICES.md', prefix + 'licenses/THIRD_PARTY_NOTICES.md')
        if extra:
            archive.writestr(extra, 'excluded test payload')
    return path


def test_wheel_metadata_and_source_only_asset_policy(tmp_path):
    result = inspect_distribution(make_wheel(tmp_path / 'colorpipe.whl'))
    assert result['status'] == 'PASS', result['errors']
    assert set(result['runtime_dependencies']) == {'numpy', 'rawpy'}


@pytest.mark.parametrize('extra', ['colorpipe/vendor.dcp', 'colorpipe/sample.ORF',
                                  'colorpipe/native.dll', '../escape.py', 'out/capture.py'])
def test_distribution_audit_rejects_private_assets_and_unsafe_paths(tmp_path, extra):
    result = inspect_distribution(make_wheel(tmp_path / 'colorpipe.whl', extra=extra))
    assert result['status'] == 'FAIL'
    assert 'unexpected distribution member: ' + extra in result['errors']


def test_default_install_must_have_the_decoder(tmp_path):
    result = inspect_distribution(make_wheel(tmp_path / 'colorpipe.whl', rawpy_default=False))
    assert result['status'] == 'FAIL'
    assert 'default installation must include NumPy and rawpy' in result['errors']


def test_wheel_must_carry_dependency_notices(tmp_path):
    result = inspect_distribution(make_wheel(tmp_path / 'colorpipe.whl', notice=False))
    assert result['status'] == 'FAIL'
    assert any('missing distribution member:' in error and 'THIRD_PARTY_NOTICES' in error
               for error in result['errors'])
