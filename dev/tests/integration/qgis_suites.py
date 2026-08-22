"""Registry of QGIS integration suites and their parameter rows."""

from cern_meyrin_case import SUITE as CERN_MEYRIN
from chimney_tops_2_case import SUITE as CHIMNEY_TOPS_2
from golden_gate_local_case import SUITE as GOLDEN_GATE_LOCAL
from golden_gate_remote_case import SUITE as GOLDEN_GATE_REMOTE
from level_set_demo_case import SUITE as LEVEL_SET_DEMO


SUITES = (
    CERN_MEYRIN,
    CHIMNEY_TOPS_2,
    GOLDEN_GATE_LOCAL,
    GOLDEN_GATE_REMOTE,
    LEVEL_SET_DEMO,
)
SUITES_BY_NAME = {suite["name"]: suite for suite in SUITES}
QGIS_CASES = tuple(
    (suite, case)
    for suite in SUITES
    for case in suite["cases"]
)
QGIS_CASE_IDS = tuple(
    "{}-{}".format(suite["name"], case["name"])
    for suite, case in QGIS_CASES
)

if len(SUITES_BY_NAME) != len(SUITES):
    raise RuntimeError("QGIS integration suite names must be unique.")
