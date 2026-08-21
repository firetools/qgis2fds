"""End-to-end regression tests for the CERN Meyrin QGIS project."""

import pytest

from cern_meyrin_case import SUITE
from qgis_case import QgisProcessUnavailable, compare_with_reference


@pytest.mark.integration
@pytest.mark.parametrize(
    "case", SUITE["cases"], ids=[case["name"] for case in SUITE["cases"]]
)
def test_cern_meyrin_export_matches_reference(case):
    try:
        actual, expected = compare_with_reference(SUITE, case)
    except QgisProcessUnavailable as error:
        pytest.skip(str(error))

    assert actual == expected
