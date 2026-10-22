import numpy as np
import pytest
import tifffile

from colorpipe import pipeline
from colorpipe.cli import main
from colorpipe.types import Settings
from dcp_helpers import profile_file
from test_writer import raw_for_writer


def test_conversion_runs_all_stages_and_publishes_a_readable_dng(tmp_path, monkeypatch, capsys):
    raw = raw_for_writer()
    before = raw.cfa.copy()
    monkeypatch.setattr(pipeline, 'load_raw', lambda p: raw)
    source = tmp_path / 'input.orf'
    source.write_bytes(b'synthetic decoder input')
    output = tmp_path / 'result.dng'
    profile = profile_file(tmp_path / 'user.dcp')
    assert main([str(source), str(output), '--profile', str(profile)]) == 0
    assert str(output.resolve()) in capsys.readouterr().out
    result = tifffile.imread(output)
    assert result.shape == (16, 20, 3) and result.dtype == np.uint16
    np.testing.assert_array_equal(raw.cfa, before)
    assert not result.any()


@pytest.mark.parametrize('problem', ['missing_profile', 'corrupt_profile', 'embed_never', 'extension', 'algorithm'])
def test_conversion_rejects_invalid_requests_before_decoding(tmp_path, monkeypatch, capsys, problem):
    def unexpected_decode(path):
        raise AssertionError('invalid requests must be rejected before RAW decoding')

    monkeypatch.setattr(pipeline, 'load_raw', unexpected_decode)
    source = tmp_path / 'input.orf'
    source.write_bytes(b'input')
    output = tmp_path / ('out.tif' if problem == 'extension' else 'out.dng')
    args = [str(source), str(output)]
    if problem != 'missing_profile':
        profile = profile_file(tmp_path / 'user.dcp', {50941: (4, [2])} if problem == 'embed_never' else None)
        if problem == 'corrupt_profile':
            profile.write_bytes(b'broken')
        args += ['--profile', str(profile)]
    if problem == 'algorithm':
        args += ['--algorithm', 'v3']
    assert main(args) == 2
    assert 'error:' in capsys.readouterr().err
    assert not output.exists()


def test_pipeline_callbacks_observe_the_actual_written_tail(tmp_path, monkeypatch):
    raw = raw_for_writer()
    raw.cfa[:] = np.random.default_rng(91).integers(254, 4096, raw.cfa.shape, dtype=np.uint16)
    monkeypatch.setattr(pipeline, 'load_raw', lambda p: raw)
    profile = profile_file(tmp_path / 'user.dcp')
    observed = {}
    output = pipeline.convert_raw('input.orf', tmp_path / 'result.dng', Settings(profile=str(profile)),
                                  stage_callback=lambda name, a: observed.update({name: a.copy()}))
    assert list(observed) == ['prepared_cfa', 'pass1', 'pass2', 'pass3', 'pass4',
                              'normalized', 'weighted_tone', 'filtered_rgb', 'default_diff',
                              'default_deconvolved', 'rgb_linear', 'quantized']
    np.testing.assert_array_equal(tifffile.imread(output), observed['quantized'])


@pytest.mark.parametrize('extra', [['--algorithm', 'v3'], ['--v3-mode', '1']])
def test_plan_rejects_unimplemented_settings(tmp_path, capsys, extra):
    source = tmp_path / 'input.orf'
    source.write_bytes(b'plan must not decode')
    assert main([str(source), str(tmp_path / 'out.dng'), '--plan', *extra]) == 2
    assert 'error:' in capsys.readouterr().err


@pytest.mark.parametrize('input_suffix,output_suffix', [('.jpg', '.dng'), ('.orf', '.tif')])
def test_plan_rejects_unsupported_file_domains(tmp_path, capsys, input_suffix, output_suffix):
    source = tmp_path / ('input' + input_suffix)
    source.write_bytes(b'plan must not decode')
    assert main([str(source), str(tmp_path / ('out' + output_suffix)), '--plan']) == 2
    assert 'error:' in capsys.readouterr().err


def test_plan_rejects_a_dangling_output_symlink(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    source, output = tmp_path / 'input.orf', tmp_path / 'out.dng'
    source.write_bytes(b'plan must not decode')
    is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == output or is_symlink(p))
    assert main([str(source), str(output), '--plan']) == 2
    assert 'overwrite' in capsys.readouterr().err
