"""Shared pytest configuration for unit and integration tests."""


def pytest_addoption(parser):
    """Register qgis2fds-specific settings accepted by pytest.ini."""
    parser.addini(
        "qgis_process",
        "Command used to run the QGIS Processing integration tests",
    )
