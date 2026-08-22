"""Tests for the QGIS plugin package builder."""

import importlib.util
from pathlib import Path
import shutil
import zipfile

import pytest


REPOSITORY_DIRECTORY = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPOSITORY_DIRECTORY / "dev" / "build" / "build_plugin.py"
SPECIFICATION = importlib.util.spec_from_file_location(
    "qgis2fds_build_plugin", BUILD_SCRIPT
)
build_plugin = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(build_plugin)


def test_package_has_uploadable_reproducible_layout(tmp_path):
    first = build_plugin.build_plugin(
        REPOSITORY_DIRECTORY, tmp_path / "first.zip"
    )
    second = build_plugin.build_plugin(
        REPOSITORY_DIRECTORY, tmp_path / "second.zip"
    )

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert "qgis2fds/__init__.py" in names
        assert "qgis2fds/metadata.txt" in names
        assert "qgis2fds/LICENSE" in names
        assert "qgis2fds/README.md" in names
        assert "qgis2fds/firetools-logo_64.png" in names
        assert all(name.startswith("qgis2fds/") for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_package_requires_license(tmp_path):
    repository = tmp_path / "repository"
    shutil.copytree(REPOSITORY_DIRECTORY / "source", repository / "source")
    shutil.copy2(REPOSITORY_DIRECTORY / "README.md", repository / "README.md")

    with pytest.raises(build_plugin.BuildError, match="LICENSE"):
        build_plugin.build_plugin(repository, tmp_path / "plugin.zip")
