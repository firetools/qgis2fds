"""Shared end-to-end QGIS project regression-test support."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile


TESTS_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_DIRECTORY = TESTS_DIRECTORY.parents[1]


class QgisProcessUnavailable(RuntimeError):
    """Raised when no QGIS Processing command can be found."""


def compare_with_reference(suite, case):
    """Export one case and return its actual and stored signatures."""
    references = json.loads(suite["reference_file"].read_text(encoding="utf-8"))

    # Flatpak has a private /tmp. A directory below the repository is visible
    # to both the host pytest process and the sandboxed QGIS process.
    with tempfile.TemporaryDirectory(
        prefix=".qgis2fds-test-{}-".format(suite["name"]),
        dir=REPOSITORY_DIRECTORY,
    ) as temporary:
        project_file, output_directory = _prepare_case_copy(
            suite, Path(temporary), case["name"]
        )
        run_export(suite, case, project_file, output_directory)
        return result_signature(case, output_directory), references[case["name"]]


def rebuild_references(suite):
    """Re-export all table rows and replace a suite's reference manifest."""
    references = {}
    with tempfile.TemporaryDirectory(
        prefix=".qgis2fds-test-{}-".format(suite["name"]),
        dir=REPOSITORY_DIRECTORY,
    ) as temporary:
        root = Path(temporary)
        for case in suite["cases"]:
            print("Rebuilding {}...".format(case["name"]), flush=True)
            project_file, output_directory = _prepare_case_copy(
                suite, root, case["name"]
            )
            run_export(suite, case, project_file, output_directory)
            references[case["name"]] = result_signature(case, output_directory)

    content = json.dumps(references, indent=2, sort_keys=True) + "\n"
    suite["reference_file"].write_text(content, encoding="utf-8")
    print("Wrote {}".format(suite["reference_file"]))


def _prepare_case_copy(suite, root, case_name):
    """Copy one QGIS case so an integration run cannot modify its source."""
    source_project = Path(suite["project_file"])
    workspace = root / case_name
    qgis_directory = workspace / "QGIS"
    shutil.copytree(source_project.parent, qgis_directory)
    project_file = qgis_directory / source_project.name
    if not project_file.is_file():
        raise FileNotFoundError(
            "Copied QGIS project is missing: {}".format(project_file)
        )
    output_directory = workspace / "output"
    output_directory.mkdir()
    return project_file, output_directory


def run_export(suite, case, project_file, output_directory):
    """Run one table row through the installed qgis2fds provider."""
    command = _qgis_process_command()
    parameters = {
        "project_path": project_file,
        "distance_units": "meters",
        "area_units": "m2",
        "chid": case["chid"],
        "fds_path": output_directory,
    }
    parameters.update(suite.get("base_settings", {}))
    parameters.update(case["settings"])

    command.extend(("run", "NIST FDS:Export FDS case"))
    for name, value in parameters.items():
        if isinstance(value, bool):
            value = str(value).lower()
        command.append("--{}={}".format(name, value))

    completed = subprocess.run(
        command,
        cwd=project_file.parent,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    # QGIS 4.2 Flatpak currently exits its qgis_process wrapper with 139 during
    # shutdown after some projects have produced complete output files. Accept
    # only that exact Flatpak condition; signature checks verify serialization.
    recoverable_flatpak_shutdown = (
        Path(command[0]).name == "flatpak"
        and completed.returncode == 139
        and (output_directory / (case["chid"] + ".fds")).is_file()
    )
    if completed.returncode == 0 or recoverable_flatpak_shutdown:
        return

    raise RuntimeError(
        "qgis_process failed with exit code {}\nSTDOUT:\n{}\nSTDERR:\n{}".format(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
    )


def result_signature(case, output_directory):
    """Summarize generated files into stable, reviewable reference values."""
    chid = case["chid"]
    fds_file = output_directory / (chid + ".fds")
    bingeom_file = output_directory / (chid + "_terrain.bingeom")
    texture_file = output_directory / (chid + "_tex.png")
    normalized_fds = _normalize_fds(fds_file.read_text(encoding="utf-8"))

    if not case["settings"]["export_obst"] and not bingeom_file.is_file():
        raise FileNotFoundError("GEOM export did not create {}".format(bingeom_file))

    return {
        "normalized_fds_sha256": _sha256(normalized_fds.encode("utf-8")),
        "fds_line_count": len(normalized_fds.splitlines()),
        "geom_count": normalized_fds.count("&GEOM "),
        "obst_count": normalized_fds.count("&OBST "),
        "bingeom_sha256": (
            _sha256(bingeom_file.read_bytes()) if bingeom_file.exists() else None
        ),
        "texture_dimensions": _png_dimensions(texture_file),
    }


def _qgis_process_command():
    configured = os.environ.get("QGIS_PROCESS")
    if configured:
        return shlex.split(configured)

    executable = shutil.which("qgis_process")
    if executable:
        return [executable]

    if shutil.which("flatpak"):
        return ["flatpak", "run", "--command=qgis_process", "org.qgis.qgis"]

    raise QgisProcessUnavailable(
        "qgis_process is unavailable; set QGIS_PROCESS to its command"
    )


def _normalize_fds(content):
    replacements = {
        "! Generated by qgis2fds ": "! Generated by qgis2fds <VERSION>",
        "! QGIS file: ": "! QGIS file: <PROJECT>",
        "! Date: ": "! Date: <DATE>",
    }
    file_replacements = {
        "! Landuse type file: ": "! Landuse type file: <LANDUSE_TYPES>",
        "! Wind file: ": "! Wind file: <WIND>",
    }
    lines = []
    for line in content.splitlines():
        replacement = next(
            (
                value
                for prefix, value in replacements.items()
                if line.startswith(prefix)
            ),
            None,
        )
        if replacement is None:
            replacement = next(
                (
                    value
                    for prefix, value in file_replacements.items()
                    if line.startswith(prefix) and line != prefix + "none"
                ),
                None,
            )
        lines.append(replacement if replacement is not None else line)
    return "\n".join(lines) + "\n"


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _png_dimensions(filepath):
    data = filepath.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("Generated texture is not a valid PNG: {}".format(filepath))
    return list(struct.unpack(">II", data[16:24]))
