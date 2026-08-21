"""End-to-end regression tests for the Chimney Tops 2 QGIS project."""

import pytest

from chimney_tops_2_case import SUITE
from qgis_case import QgisProcessUnavailable, compare_with_reference


@pytest.mark.integration
@pytest.mark.parametrize(
    "case", SUITE["cases"], ids=[case["name"] for case in SUITE["cases"]]
)
def test_chimney_tops_2_export_matches_reference(case):
    try:
        actual, expected = compare_with_reference(SUITE, case)
    except QgisProcessUnavailable as error:
        pytest.skip(str(error))

    assert actual == expected
