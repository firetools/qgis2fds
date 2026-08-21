#!/usr/bin/env python3
"""Rebuild references for the Golden Gate Remote integration case."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from golden_gate_remote_case import SUITE  # noqa: E402
from qgis_case import QgisProcessUnavailable, rebuild_references  # noqa: E402


def main():
    try:
        rebuild_references(SUITE)
    except QgisProcessUnavailable as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
