#!/usr/bin/env python3
"""Rebuild golden references for selected QGIS integration suites."""

import argparse

from qgis_case import QgisProcessUnavailable, rebuild_references
from qgis_suites import SUITES, SUITES_BY_NAME


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description="Rebuild qgis2fds integration-test references."
    )
    parser.add_argument(
        "suites",
        metavar="SUITE",
        nargs="*",
        choices=tuple(SUITES_BY_NAME),
        help="suite to rebuild; more than one may be supplied",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="rebuild every registered suite",
    )
    arguments = parser.parse_args()
    if arguments.all and arguments.suites:
        parser.error("suite names cannot be combined with --all")
    if not arguments.all and not arguments.suites:
        parser.error("specify at least one suite or use --all")
    return arguments


def main():
    arguments = _parse_arguments()
    selected = (
        SUITES
        if arguments.all
        else tuple(SUITES_BY_NAME[name] for name in arguments.suites)
    )
    try:
        for suite in selected:
            rebuild_references(suite)
    except QgisProcessUnavailable as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
