import numpy as np
import pytest

from colorpipe.tone import tone_luts


@pytest.mark.parametrize('wb', [1., 2.3046875, 2.75, 8.])
def test_formula_tables_are_monotone_and_inverse_roundtrip_is_bounded(wb):
    forward, inverse = tone_luts(wb)
    for table in (forward, inverse):
        assert table.shape == (65536,) and table.dtype == np.uint16
        assert table[0] == 0 and table[-1] == 65535
        assert np.all(np.diff(table.astype(int)) >= 0)
        assert not table.flags.writeable
    error = abs(inverse[forward].astype(int) - np.arange(65536))
    assert error.max() < 32


@pytest.mark.parametrize('wb', [0, -1, float('nan'), float('inf')])
def test_tone_rejects_invalid_gain(wb):
    with pytest.raises(ValueError):
        tone_luts(wb)
