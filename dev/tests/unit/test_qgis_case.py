"""Tests for optional external integration-test execution."""

from pathlib import Path

import pytest

import qgis_case


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
