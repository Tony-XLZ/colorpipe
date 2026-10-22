"""Stage bytes recorded from m4 before changing parity-grid array access."""

import hashlib

import numpy as np
import pytest

from colorpipe.demosaic import demosaic_hifi
from colorpipe.normalize import normalize_cfa
from colorpipe.types import RawImage, Settings


@pytest.mark.parametrize('chunk_rows', [1, 3, 16, 64])
@pytest.mark.parametrize('shape,seed,expected', [
    ((8, 8), 71, (
        '5d89d11c3b2da54aeb7cb4f851108ab4ed950956b8eeb3dde82af0a942d2398b',
        '8340ff8cd873fd4f292eb9728546dc55c367a88036225c77a9e6d83781f076d8',
        '8340ff8cd873fd4f292eb9728546dc55c367a88036225c77a9e6d83781f076d8',
        '2df1828d7c54104e149de9a1b864fb112641761e272ca5701ca47b38858d1cc0',
        '98c234f31d7b4e49fd623df88c43d8161fcc8bd0f503098327d068056888a0be')),
    ((30, 36), 72, (
        'dc2b6eb34989761f5eafc866cc04300d200633e74a86b594a617f318e2e4ffed',
        '6c7dcd2f4925f1837fcc6b3dba6c6f7e80bdfc4bbe451419c2d33845c9e1605a',
        '4b1ff4bac89e1f4b5aafec3bebab6689e9258651ad52b260e560e61272a2d52b',
        '08540ddfca0f4a5b107f280777f4fbf2637a20ee4227c489e762f90d081ecde0',
        '957af3e1a2d57c4bff4acf98803a6c53fe8752f20ccf7958adbe689c006593ee')),
    ((70, 82), 73, (
        'd8a9e5bfe0ac1594988af45ad704c93f6a38bfa8f3b89755b86354670ec68a60',
        '54eb47b6dba28507e831e7855dde69527e1840d34c40fc294ee6949079021466',
        '82ec984d9018a683898298969ff4985d97645fb8a442798e9f1f1541580ffe6f',
        '6b524fac49ecae3ca826cb71d8b01d9e3d4f0936184b36beee528d6e948acc95',
        '7d7d500e054e9f070d1435d78c40d6fe4a8dc8317debdf7d8a8f5e13f44ba961')),
])
def test_all_hifi_stage_bytes_match_m4(shape, seed, expected, chunk_rows):
    cfa = np.random.default_rng(seed).integers(0, 65536, shape, dtype=np.uint16)
    raw = RawImage(cfa, black=(0,) * 4, white=(65535,) * 4)
    stages = {}
    demosaic_hifi(normalize_cfa(cfa, raw), raw, Settings(), chunk_rows=chunk_rows,
                  stage_callback=lambda name, array: stages.update({name: hashlib.sha256(
                      array.astype('<u2', copy=False).tobytes()).hexdigest()}))
    assert tuple(stages) == ('prepared_cfa', 'pass1', 'pass2', 'pass3', 'pass4')
    assert tuple(stages.values()) == expected
