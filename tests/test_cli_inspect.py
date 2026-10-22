import json

import pytest

from colorpipe.cli import main
from test_decode import fake_rawpy  # noqa: F401
from orf_factory import make_orf


def test_inspect_decodes_and_prints_real_metadata(tmp_path, capsys, fake_rawpy):
    assert main([str(make_orf(tmp_path)), "--inspect"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cfa"]["size_wh"] == [10, 8]
    assert result["geometry"]["processing_size_wh"] == [6, 4]
    assert result["iso"] == 800
    assert result["wb_rgb"] == [600 / 256, 1, 400 / 256]
    assert not list(tmp_path.glob("*.dng"))


def test_inspect_invalid_metadata_returns_clean_error(tmp_path, capsys):
    assert main([str(make_orf(tmp_path, model="UNKNOWN")), "--inspect"]) == 2
    assert "unsupported camera" in capsys.readouterr().err


@pytest.mark.parametrize("args", [[], ["in.orf"], ["in.orf", "out.dng", "--inspect"],
                                  ["in.orf", "--inspect", "--plan"],
                                  ["in.orf", "out.dng", "--threads", "2"]])
def test_inspect_and_conversion_arguments_are_unambiguous(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
