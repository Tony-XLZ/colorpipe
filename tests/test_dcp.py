import struct

import numpy as np
import pytest

from colorpipe.dcp import load_dcp
from dcp_helpers import profile_file


def test_little_and_big_endian_profiles_have_identical_value_bytes(tmp_path):
    little = load_dcp(profile_file(tmp_path / 'little.dcp'))
    big = load_dcp(profile_file(tmp_path / 'big.dcp', endian='>'))
    assert little.name == big.name == 'Synthetic Test'
    assert little.sha256 != big.sha256
    assert dict(little.fields) == dict(big.fields)


@pytest.mark.parametrize('updates', [
    {50721: None}, {50722: (10, [(1, 1)] * 9)},
    {50721: (2, 'invalid matrix type')},
    {50965: (10, [(1, 1)] * 9)},
    {50721: (10, [(0, 1)] * 9)},
    {50721: (10, [(1, 0)] * 9)},
    {50937: (4, [2, 2, 1])},
    {50937: (4, [2, 2, 1]), 50938: (11, [0, 1, 1])},
    {51107: (11, [.5])}, {51108: (4, [2])},
    {50940: (11, [0, 0, .5, .6, .4, .7, 1, 1])},
    {50940: (11, [0, 0, 1, float('nan')])},
    {52529: (3, [21])},
])
def test_invalid_or_unsupported_profile_is_rejected(tmp_path, updates):
    with pytest.raises(ValueError):
        load_dcp(profile_file(tmp_path / 'bad.dcp', updates))


@pytest.mark.parametrize('corruption', ['outside', 'duplicate', 'empty', 'truncated'])
def test_bounded_profile_reader_rejects_corruption(tmp_path, corruption):
    path = profile_file(tmp_path / 'bad.dcp')
    data = bytearray(path.read_bytes())
    if corruption == 'outside':
        struct.pack_into('<I', data, 18, 0xFFFFFFF0)
    elif corruption == 'duplicate':
        struct.pack_into('<H', data, 22, struct.unpack_from('<H', data, 10)[0])
    elif corruption == 'empty':
        struct.pack_into('<I', data, 14, 0)
    else:
        data = data[:20]
    path.write_bytes(data)
    with pytest.raises(ValueError):
        load_dcp(path)
