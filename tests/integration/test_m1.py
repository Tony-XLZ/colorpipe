import json
from pathlib import Path
import runpy

import pytest


@pytest.mark.parametrize("kind", ["20mp_orf", "20mp_ori", "50mp_orf"])
def test_real_raw_m1_stage_acceptance(request, tmp_path, kind):
    config_path = request.config.getoption("--fixture-config")
    stage_index = request.config.getoption("--m1-stage-index")
    if not config_path or not stage_index:
        pytest.skip("set --fixture-config and --m1-stage-index for real M1 acceptance")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    fixture = next(row for row in config["fixtures"] if row["kind"] == kind)
    tool = Path(__file__).resolve().parents[2] / "tools" / "validate_m1.py"
    validate_case = runpy.run_path(str(tool))["validate_case"]
    result = validate_case(fixture, Path(stage_index), tmp_path / "prediction")
    (tmp_path / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    assert result["psnr_gate"], result["stages"]
    assert result["max_error_gate_lt_200"], result["stages"]["pass4"]
