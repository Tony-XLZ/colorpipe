import struct

import pytest

from orf_factory import make_orf


def test_metadata_comes_from_source_tags(tmp_path):
    from colorpipe.metadata import read_orf_metadata

    meta = read_orf_metadata(make_orf(tmp_path))
    assert meta["make"] == "OM Digital Solutions"
    assert meta["model"] == "OM-1MarkII"
    assert meta["iso"] == 800
    assert meta["black"] == (40, 80, 120, 160)
    assert meta["white"] == (16383,) * 4
    assert meta["wb"] == pytest.approx((600 / 256, 1, 400 / 256))
    assert meta["pixel_scale"] == pytest.approx(2.4)
    assert meta["focal_plane_diagonal"] == (1800, 100)
    assert meta["camera_crop"] == (2, 2, 6, 4)
    assert meta["orientation"] == 6


@pytest.mark.parametrize("kwargs,match", [
    ({"iso": 0}, "ISO"), ({"bits": 10}, "12/14"),
    ({"model": "UNKNOWN"}, "camera"), ({"diagonal": (1800, 0)}, "diagonal"),
    ({"wb": (600, 400, 0, 0)}, "white balance"),
    ({"pair_tail": 1}, "second component"),
    ({"pattern": b"\x02\x00\x02\x00\x02\x01\x01\x00"}, "RGGB"),
])
def test_invalid_required_metadata_is_rejected(tmp_path, kwargs, match):
    from colorpipe.metadata import read_orf_metadata

    with pytest.raises(ValueError, match=match):
        read_orf_metadata(make_orf(tmp_path, **kwargs))


@pytest.mark.parametrize("mutation", ["header", "root_offset", "missing_iso", "maker_offset", "truncated"])
def test_corrupt_metadata_is_rejected(tmp_path, mutation):
    from colorpipe.metadata import read_orf_metadata

    path = make_orf(tmp_path)
    data = bytearray(path.read_bytes())
    if mutation == "header":
        data[:4] = b"II*\0"
    elif mutation == "root_offset":
        struct.pack_into("<I", data, 4, len(data) + 1)
    elif mutation == "missing_iso":
        struct.pack_into("<H", data, 258, 0x9999)
    elif mutation == "maker_offset":
        struct.pack_into("<I", data, 256 + 2 + 2 * 12 + 8, len(data) - 1)
    else:
        data = data[:270]
    path.write_bytes(data)
    with pytest.raises(ValueError):
        read_orf_metadata(path)
