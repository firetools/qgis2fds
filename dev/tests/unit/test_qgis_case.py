"""Tests for optional external integration-test execution."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import qgis_case


def test_export_rejects_qgis_process_shutdown_crash(tmp_path, monkeypatch):
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    (output_directory / "case.fds").write_text("&TAIL /\n", encoding="utf-8")
    monkeypatch.setattr(
        qgis_case,
        "_configured_qgis_process_command",
        lambda: ["flatpak", "run", "org.qgis.qgis"],
    )
    monkeypatch.setattr(
        qgis_case.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=139,
            stdout="export completed",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="exit code 139"):
        qgis_case.run_export(
            {"base_settings": {}},
            {"chid": "case", "settings": {}},
            tmp_path / "case.qgs",
            output_directory,
        )


def test_fds_validation_rejects_reported_errors(tmp_path, monkeypatch):
    input_file = tmp_path / "case.fds"
    input_file.write_text("&TAIL /\n", encoding="utf-8")
    monkeypatch.setattr(
        qgis_case,
        "_configured_fds_command",
        lambda: [
            "/usr/bin/env",
            "python3",
            "-c",
            "print('ERROR(999): test failure')",
        ],
    )

    with pytest.raises(RuntimeError, match=r"ERROR\(999\)"):
        qgis_case.run_fds({"chid": "case"}, Path(tmp_path))
