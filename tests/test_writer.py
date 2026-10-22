import numpy as np
import pytest
import tifffile

from colorpipe.types import RawImage, Settings
from colorpipe.writer import write_dng
from dcp_helpers import profile_file


def raw_for_writer():
    return RawImage(np.zeros((20, 24), np.uint16), (254,) * 4, (4095,) * 4,
                    iso=200, wb=(2., 1., 1.5), pixel_scale=2., camera_crop=(4, 5, 16, 10),
                    metadata=dict(make='OM Digital Solutions', model='OM-1MarkII', orientation=6,
                                  datetime='2025:07:26 19:50:58', daylight_wb=(2.3, 1., 1.7),
                                  exif={'ExposureTime': (1, 800), 'FNumber': (4, 1),
                                        'FocalLength': (40, 1), 'DateTimeOriginal': '2025:07:26 19:50:58'}))


def test_linear_dng_roundtrip_profile_crop_and_exif(tmp_path):
    raw = raw_for_writer()
    pixels = np.random.default_rng(30).integers(0, 65536, (16, 20, 3), dtype=np.uint16)
    before = pixels.copy()
    dcp = profile_file(tmp_path / 'synthetic.dcp')
    result = write_dng(pixels, raw, Settings(), tmp_path / 'image.dng', dcp=dcp)
    np.testing.assert_array_equal(tifffile.imread(result), before)
    np.testing.assert_array_equal(pixels, before)
    with tifffile.TiffFile(result) as tf:
        tags = tf.pages[0].tags
        assert int(tags[262].value) == 34892
        assert tags[258].value == (16, 16, 16)
        assert tags[274].value == 6
        assert tags[50829].value == (0, 0, 16, 20)
        crop = np.array(tags[50719].value).reshape(-1, 2)
        np.testing.assert_array_equal(crop[:, 0] / crop[:, 1], (2, 3))
        assert tags[50934].value == tags[50936].value == 'Synthetic Test'
        assert tags[34665].value['ExposureTime'] == (1, 800)
        assert tags[34665].value['PixelXDimension'] == 20
        for key in (50706, 50707, 50708, 50721, 50723, 50724, 50727, 50728, 50778):
            assert key in tags


def test_writer_fails_before_output_and_never_overwrites(tmp_path):
    raw = raw_for_writer()
    pixels = np.zeros((16, 20, 3), np.uint16)
    profile = profile_file(tmp_path / 'p.dcp')
    path = tmp_path / 'existing.dng'
    path.write_bytes(b'keep this')
    with pytest.raises(FileExistsError):
        write_dng(pixels, raw, Settings(), path, dcp=profile)
    assert path.read_bytes() == b'keep this'
    for wrong in (pixels.astype(np.float32), pixels[:, :-1], pixels[..., 0]):
        new = tmp_path / 'bad.dng'
        with pytest.raises(ValueError):
            write_dng(wrong, raw, Settings(), new, dcp=profile)
        assert not new.exists()


def test_profile_required_and_embed_never_is_respected(tmp_path):
    raw = raw_for_writer()
    pixels = np.zeros((16, 20, 3), np.uint16)
    output = tmp_path / 'out.dng'
    with pytest.raises(ValueError, match='DCP|profile'):
        write_dng(pixels, raw, Settings(), output)
    blocked = profile_file(tmp_path / 'never.dcp', {50941: (4, [2])})
    with pytest.raises(ValueError, match='embed'):
        write_dng(pixels, raw, Settings(), output, dcp=blocked)
    assert not output.exists()


def test_source_daylight_calibration_and_profile_payload_are_preserved(tmp_path):
    raw = raw_for_writer()
    raw.metadata['daylight_wb'] = (582 / 256, 1., 440 / 256)
    profile = profile_file(tmp_path / 'adobe-signature.dcp', {50932: (2, 'com.adobe')})
    output = write_dng(np.zeros((16, 20, 3), np.uint16), raw, Settings(profile=str(profile)), tmp_path / 'x.dng')
    with tifffile.TiffFile(output) as tf:
        tags = tf.pages[0].tags
        c = np.array(tags[50723].value).reshape(-1, 2)
        np.testing.assert_array_equal((c[:, 0] / c[:, 1]).reshape(3, 3), np.diag([.9691, 1., 1.0591]))
        assert tags[50730].value == (37, 100)
        assert tags[50931].value == 'com.adobe'
        assert 50740 not in tags and 34853 not in tags


def test_destination_race_keeps_competing_file(tmp_path, monkeypatch):
    import os
    raw = raw_for_writer()
    profile = profile_file(tmp_path / 'p.dcp')
    output = tmp_path / 'race.dng'
    real_link = os.link

    def competing_link(source, destination):
        output.write_bytes(b'concurrent owner')
        return real_link(source, destination)

    monkeypatch.setattr(os, 'link', competing_link)
    with pytest.raises(FileExistsError):
        write_dng(np.zeros((16, 20, 3), np.uint16), raw, Settings(), output, dcp=profile)
    assert output.read_bytes() == b'concurrent owner'
    assert not list(tmp_path.glob('*.partial'))


def test_writer_rejects_a_dangling_output_symlink(tmp_path, monkeypatch):
    from pathlib import Path
    output = tmp_path / 'link.dng'
    target = tmp_path / 'target.dng'
    # Model the two filesystem queries without requiring Windows symlink privilege.
    resolve, is_symlink = Path.resolve, Path.is_symlink
    monkeypatch.setattr(Path, 'resolve', lambda p, *a, **kw: target if p == output else resolve(p, *a, **kw))
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == output or is_symlink(p))
    profile = profile_file(tmp_path / 'p.dcp')
    with pytest.raises(FileExistsError):
        write_dng(np.zeros((16, 20, 3), np.uint16), raw_for_writer(), Settings(), output, dcp=profile)
    assert output.is_symlink() and not target.exists()


def test_as_shot_neutral_uses_the_camera_metadata_six_decimal_scale(tmp_path):
    raw = raw_for_writer()
    raw.wb = (2.75, 1., 1.4296875)
    profile = profile_file(tmp_path / 'user.dcp')
    output = write_dng(np.zeros((16, 20, 3), np.uint16), raw, Settings(), tmp_path / 'image.dng', dcp=profile)
    with tifffile.TiffFile(output) as tf:
        assert tf.pages[0].tags[50728].value == (363636, 1000000, 1000000, 1000000, 699454, 1000000)


def test_metadata_validator_checks_payloads_and_rejects_missing_required_tags(tmp_path):
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    from colorpipe.dcp import load_dcp
    from validate_m3 import metadata_comparison
    profile = profile_file(tmp_path / 'user.dcp')
    output = write_dng(np.zeros((16, 20, 3), np.uint16), raw_for_writer(), Settings(), tmp_path / 'image.dng', dcp=profile)
    result = metadata_comparison(output, output, load_dcp(profile))
    assert all(p['exact'] for p in result['dcp_payloads'])
    assert not result['container_differences']
    assert not next(t for t in result['critical_tags'] if t['tag'] == 50722)['equal']


def test_classic_tiff_size_limit_is_rejected_before_pixel_access(tmp_path):
    raw = raw_for_writer()
    raw.cfa = np.broadcast_to(np.uint16(0), (30004, 30004))
    raw.width = raw.height = 30004
    pixels = np.broadcast_to(np.zeros((1, 1, 3), np.uint16), (30000, 30000, 3))
    profile = profile_file(tmp_path / 'user.dcp')
    with pytest.raises(ValueError, match='classic TIFF'):
        write_dng(pixels, raw, Settings(), tmp_path / 'too-big.dng', dcp=profile)
    assert not (tmp_path / 'too-big.dng').exists()
