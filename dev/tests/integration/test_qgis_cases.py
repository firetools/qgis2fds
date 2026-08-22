"""End-to-end regression tests for all registered QGIS projects."""

import pytest

from qgis_case import (
    FdsUnavailable,
    QgisProcessUnavailable,
    compare_with_reference,
)
from qgis_suites import QGIS_CASE_IDS, QGIS_CASES


@pytest.mark.integration
@pytest.mark.parametrize(("suite", "case"), QGIS_CASES, ids=QGIS_CASE_IDS)
def test_qgis_export_matches_reference(suite, case):
    try:
        actual, expected = compare_with_reference(suite, case)
    except (FdsUnavailable, QgisProcessUnavailable) as error:
        pytest.skip(str(error))

    assert actual == expected
