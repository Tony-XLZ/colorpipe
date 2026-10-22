import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from validate_m3 import validate_case


@pytest.mark.parametrize('kind', ['20mp_orf', '20mp_ori', '50mp_orf'])
def test_real_raw_dng_writer_acceptance(request, tmp_path, kind):
    fixture_path = request.config.getoption('--fixture-config')
    acceptance = request.config.getoption('--m2-acceptance')
    oracles = request.config.getoption('--m2-oracles')
    profile = request.config.getoption('--m3-profile')
    if not all((fixture_path, acceptance, oracles, profile)):
        pytest.skip('set fixtures, M2 acceptance/oracles, and --m3-profile for real M3 integration')
    fixture = next(f for f in json.loads(Path(fixture_path).read_text(encoding='utf-8'))['fixtures'] if f['kind'] == kind)
    result = validate_case(fixture, acceptance, oracles, profile, tmp_path / 'prediction')
    (tmp_path / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    assert result['status'] == 'PASS', result['gates']
