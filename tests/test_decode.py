import sys
from types import SimpleNamespace

import numpy as np
import pytest

from colorpipe.decode import load_raw
from colorpipe.types import RawImage
from colorpipe.normalize import channel_black_white
from orf_factory import make_orf


class FakeRaw:
    def __init__(self):
        self.raw_image = np.arange(80, dtype=np.uint16).reshape(8, 10)
        self.raw_image_visible = self.raw_image[2:-2, 2:-2]
        self.raw_pattern = np.array([[0, 1], [3, 2]], dtype=np.uint8)
        self.color_desc = b"RGBG"
        self.black_level_per_channel = [40, 80, 160, 120]
        self.white_level = 16383
        self.camera_white_level_per_channel = [16380] * 4
        self.camera_whitebalance = [600 / 256, 1.0, 400 / 256, 0.0]
        self.sizes = SimpleNamespace(raw_height=8, raw_width=10, height=4, width=6,
                                     top_margin=2, left_margin=2)

    def raw_color(self, row, col):
        return self.raw_pattern[row % 2, col % 2]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.raw_image[:] = 0


@pytest.fixture
def fake_rawpy(monkeypatch):
    raw = FakeRaw()
    monkeypatch.setitem(sys.modules, "rawpy", SimpleNamespace(imread=lambda _: raw))
    return raw


def test_decode_keeps_sensor_domain_and_all_metadata(tmp_path, fake_rawpy):
    raw = load_raw(make_orf(tmp_path))
    assert raw.cfa.shape == (8, 10)
    assert raw.cfa.dtype == np.uint16
    assert raw.cfa[-1, -1] == 79  # The result must outlive LibRaw's buffer.
    assert (raw.width, raw.height) == (10, 8)
    assert raw.processing_size == (6, 4)
    assert raw.crop == (2, 2, 2, 2)
    assert raw.camera_crop == (2, 2, 6, 4)
    assert raw.pattern == "RGGB"
    assert raw.black == (40, 80, 120, 160)  # R,G1,G2,B, not RGBG.
    assert raw.white == (16383,) * 4  # Sensor maximum, not camera clipping point.
    assert raw.wb == pytest.approx((600 / 256, 1.0, 400 / 256))
    assert raw.iso == 800
    assert raw.pixel_scale == pytest.approx(2.4)
    assert raw.valid_bits == 14
    assert raw.metadata["visible_area_xywh"] == [2, 2, 6, 4]
    assert raw.metadata["camera_white_level_per_channel"] == [16380] * 4


def test_decode_rejects_non_rggb_instead_of_assuming_layout(tmp_path, fake_rawpy):
    fake_rawpy.raw_pattern = np.array([[2, 3], [1, 0]], dtype=np.uint8)
    with pytest.raises(ValueError, match="RGGB"):
        load_raw(make_orf(tmp_path))


def test_visible_margin_parity_does_not_change_sensor_phase(tmp_path, fake_rawpy):
    full_pattern = fake_rawpy.raw_pattern.copy()
    fake_rawpy.sizes.top_margin = 1
    fake_rawpy.sizes.left_margin = 1
    fake_rawpy.raw_pattern = full_pattern[::-1, ::-1]
    fake_rawpy.raw_color = lambda y, x: int(full_pattern[y % 2, x % 2])
    raw = load_raw(make_orf(tmp_path))
    assert raw.pattern == "RGGB"
    assert raw.black == (40, 80, 120, 160)
    assert raw.metadata["visible_area_xywh"] == [1, 1, 6, 4]


def test_white_balance_follows_channel_indices(tmp_path, fake_rawpy):
    fake_rawpy.color_desc = b"RGGB"
    fake_rawpy.raw_pattern = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    fake_rawpy.black_level_per_channel = [40, 80, 120, 160]
    fake_rawpy.camera_whitebalance = [600 / 256, 1.0, 0.0, 400 / 256]
    raw = load_raw(make_orf(tmp_path))
    assert raw.wb == pytest.approx((600 / 256, 1, 400 / 256))


def test_phase_levels_match_normalization_contract(tmp_path, fake_rawpy):
    black, white = channel_black_white(load_raw(make_orf(tmp_path)))
    np.testing.assert_array_equal(black, [40, 100, 160])
    np.testing.assert_array_equal(white, [16383] * 3)


def test_libraw_failure_is_reported_as_format_error(tmp_path, fake_rawpy, monkeypatch):
    class DecodeError(Exception):
        pass

    def fail_decode(_):
        raise DecodeError("corrupt compressed stream")

    module = sys.modules["rawpy"]
    monkeypatch.setattr(module, "LibRawError", DecodeError, raising=False)
    monkeypatch.setattr(module, "imread", fail_decode)
    with pytest.raises(ValueError, match="LibRaw could not decode"):
        load_raw(make_orf(tmp_path))


@pytest.mark.parametrize("field,value,match", [
    ("black_level_per_channel", [0] * 4, "black"),
    ("white_level", 4095, "white"),
    ("camera_whitebalance", [0, 0, 0, 0], "white balance"),
    ("raw_image", np.zeros((8, 10, 3), dtype=np.uint16), "2-D"),
])
def test_decode_rejects_inconsistent_libraw_data(tmp_path, fake_rawpy, field, value, match):
    setattr(fake_rawpy, field, value)
    with pytest.raises(ValueError, match=match):
        load_raw(make_orf(tmp_path))


def test_rawimage_does_not_invent_metadata():
    raw = RawImage(cfa=np.zeros((6, 6), dtype=np.uint16), black=(0,) * 4, white=(1,) * 4)
    assert raw.iso is None
    assert raw.pixel_scale is None
    assert raw.wb is None
    assert (raw.width, raw.height) == (6, 6)


@pytest.mark.parametrize("changes,match", [
    ({"cfa": np.zeros((8, 10), dtype=np.float32)}, "uint16"),
    ({"width": 9}, "dimensions"),
    ({"black": (-1, 0, 0, 0)}, "black/white"),
    ({"white": (70000,) * 4}, "black/white"),
    ({"wb": (1, float("nan"), 1)}, "wb"),
    ({"iso": 0}, "iso"),
    ({"pixel_scale": -1}, "pixel_scale"),
    ({"crop": (4, 4, 4, 4)}, "crop"),
    ({"camera_crop": (9, 0, 6, 4)}, "camera_crop"),
])
def test_rawimage_rejects_invalid_contract(changes, match):
    args = dict(cfa=np.zeros((8, 10), dtype=np.uint16), black=(0,) * 4, white=(100,) * 4)
    args.update(changes)
    with pytest.raises(ValueError, match=match):
        RawImage(**args)
