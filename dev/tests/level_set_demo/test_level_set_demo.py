"""End-to-end regression test for the Level Set Demo QGIS project."""

import pytest

from level_set_demo_case import SUITE
from qgis_case import QgisProcessUnavailable, compare_with_reference


@pytest.mark.integration
@pytest.mark.parametrize(
    "case", SUITE["cases"], ids=[case["name"] for case in SUITE["cases"]]
)
def test_level_set_demo_export_matches_reference(case):
    try:
        actual, expected = compare_with_reference(SUITE, case)
    except QgisProcessUnavailable as error:
        pytest.skip(str(error))

    assert actual == expected
