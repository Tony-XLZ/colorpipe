import json
from pathlib import Path
import runpy

import pytest


@pytest.mark.parametrize("kind", ["20mp_orf", "20mp_ori", "50mp_orf"])
def test_real_raw_matches_sensor_and_metadata_oracles(request, kind):
    config_path = request.config.getoption("--fixture-config")
    reference_root = request.config.getoption("--reference-root")
    if not config_path or not reference_root:
        pytest.skip("set --fixture-config and --reference-root to run local RAW acceptance")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    matches = [row for row in config["fixtures"] if row["kind"] == kind]
    assert len(matches) == 1
    tool = Path(__file__).resolve().parents[2] / "tools" / "validate_m0.py"
    validate_case = runpy.run_path(str(tool))["validate_case"]
    result = validate_case(matches[0], Path(reference_root))
    assert result["status"] == "PASS", result
