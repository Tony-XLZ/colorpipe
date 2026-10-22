import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from validate_m2 import validate_case


@pytest.mark.parametrize('kind', ['20mp_orf', '20mp_ori', '50mp_orf'])
def test_real_raw_default_tail_acceptance(request, tmp_path, kind):
    fixture_path = request.config.getoption('--fixture-config')
    acceptance = request.config.getoption('--m2-acceptance')
    oracles = request.config.getoption('--m2-oracles')
    if not all((fixture_path, acceptance, oracles)):
        pytest.skip('set --fixture-config, --m2-acceptance and --m2-oracles for M2')
    fixture = next(f for f in json.loads(Path(fixture_path).read_text(encoding='utf-8'))['fixtures'] if f['kind'] == kind)
    result = validate_case(fixture, acceptance, oracles, tmp_path / 'prediction',
                           native_stages=request.config.getoption('--m2-native-stages'))
    (tmp_path / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    assert result['gates']['upstream_max_error_lt_200'], result['m1_pre_tail']
    assert result['gates']['final_psnr_gt_40'], result['final_rgb']
    assert result['gates']['final_ssim_gt_098'], result['final_ssim']
    assert result['gates']['delta_e_mean_lt_2'], result['delta_e00']
    assert result['gates']['delta_e_p95_lt_4'], result['delta_e00']
