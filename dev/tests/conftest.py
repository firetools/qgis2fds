"""Shared pytest configuration for unit and integration tests."""


def pytest_addoption(parser):
    """Register qgis2fds-specific settings accepted by pytest.ini."""
    parser.addini(
        "qgis_process",
        "Command used to run the QGIS Processing integration tests",
    )
    parser.addini(
        "fds",
        "Command used to validate exported FDS integration cases",
    )
    parser.addini(
        "quantitative_cases_directory",
        "Optional directory in which generated quantitative cases are retained",
    )
