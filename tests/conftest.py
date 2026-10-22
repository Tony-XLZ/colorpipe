import sys
import os
from pathlib import Path

# Package validation must exercise the installed wheel, without a source override.
if os.environ.get("COLORPIPE_TEST_INSTALLED") != "1":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def pytest_addoption(parser):
    parser.addoption("--fixture-config", default=os.environ.get("COLORPIPE_FIXTURES"),
                     help="local fixture JSON; required for real RAW integration tests")
    parser.addoption("--reference-root", default=os.environ.get("COLORPIPE_REFERENCE_ROOT"),
                     help="read-only decoder_writer research artifact directory")
    parser.addoption("--m1-stage-index", default=os.environ.get("COLORPIPE_M1_STAGE_INDEX"),
                     help="read-only standalone_front three_raw_stages.json for M1 acceptance")
    parser.addoption("--m2-acceptance", default=os.environ.get("COLORPIPE_M2_ACCEPTANCE"),
                     help="read-only parent_acceptance.json with default-tail DNG identities")
    parser.addoption("--m2-oracles", default=os.environ.get("COLORPIPE_M2_ORACLES"),
                     help="local test-only portable stage reference directory")
    parser.addoption("--m2-native-stages", default=os.environ.get("COLORPIPE_M2_NATIVE_STAGES"),
                     help="optional index of existing native float stages")
    parser.addoption("--m3-profile", default=os.environ.get("COLORPIPE_M3_PROFILE"),
                     help="local user-supplied DCP for real M3 integration tests")
