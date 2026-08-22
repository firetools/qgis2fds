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
        "run_fds",
        "Whether each exported integration case is run through FDS",
        type="bool",
        default=False,
    )
