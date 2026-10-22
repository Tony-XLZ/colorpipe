import json

import numpy as np
import pytest

from colorpipe import Settings, RawImage, __version__
from colorpipe.cli import main
from colorpipe.normalize import normalize_cfa


def test_version():
    assert __version__ == "0.1.0"


def test_settings_defaults():
    s = Settings()
    s.validate()
    assert s.algorithm == "hifi"
    assert s.bit_depth == 16
    assert s.compression == "none"


def test_settings_rejects_12bit():
    s = Settings(bit_depth=12)
    with pytest.raises(NotImplementedError):
        s.validate()


def test_raw_image_validation():
    cfa = np.zeros((4, 4), dtype=np.uint16)
    raw = RawImage(cfa=cfa, black=(0, 0, 0, 0), white=(65535, 65535, 65535, 65535), crop=(0,) * 4)
    assert raw.pattern == "RGGB"
    with pytest.raises(ValueError):
        RawImage(cfa=np.zeros((4, 4, 3), dtype=np.uint16), black=(0,) * 4, white=(1,) * 4)


def test_normalize_native_sites():
    cfa = np.arange(16, dtype=np.uint16).reshape(4, 4) * 100
    cfa[0, 0] = 1234
    raw = RawImage(cfa=cfa, black=(0, 0, 0, 0), white=(65535, 65535, 65535, 65535), crop=(0,) * 4)
    out = normalize_cfa(cfa, raw)
    assert out.shape == (4, 4, 3)
    assert out.dtype == np.float32
    # RGGB: (0,0) is R, (0,1)/(1,0) G, (1,1) B
    assert out[0, 0, 0] == pytest.approx(cfa[0, 0] / 65535.0)
    assert out[1, 1, 2] == pytest.approx(cfa[1, 1] / 65535.0)
    # missing sites stay zero
    assert out[0, 0, 1] == 0
    assert out[0, 0, 2] == 0


def test_cli_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_plan(tmp_path, capsys):
    src = tmp_path / "in.orf"
    src.write_bytes(b"not-a-real-raw")
    dst = tmp_path / "out.dng"
    rc = main(["--plan", str(src), str(dst)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["algorithm"] == "hifi"
    assert data["input"].endswith("in.orf")
