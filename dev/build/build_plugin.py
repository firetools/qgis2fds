#!/usr/bin/env python3
"""Build an uploadable qgis2fds package for the QGIS plugin repository."""

import argparse
import configparser
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile


PLUGIN_DIRECTORY = "qgis2fds"
MAXIMUM_PACKAGE_SIZE = 25_000_000
REQUIRED_METADATA = (
    "name",
    "qgisMinimumVersion",
    "description",
    "about",
    "version",
    "author",
    "email",
    "repository",
)
IGNORED_SUFFIXES = {".pyc", ".pyo"}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_DIRECTORY = SCRIPT_DIRECTORY.parents[1]


class BuildError(ValueError):
    """Raised when the repository cannot produce a valid plugin package."""


def build_plugin(repository_directory, output_file=None):
    """Validate the plugin and build its deterministic ZIP package."""
    repository_directory = Path(repository_directory).resolve()
    source_directory = repository_directory / "source"
    metadata = _read_metadata(source_directory / "metadata.txt")
    _validate_plugin(source_directory, repository_directory, metadata)

    version = metadata["version"].strip()
    if output_file is None:
        output_file = (
            repository_directory
            / "dev"
            / "build"
            / "qgis2fds-{}.zip".format(version)
        )
    else:
        output_file = Path(output_file)
        if not output_file.is_absolute():
            output_file = Path.cwd() / output_file
    output_file = output_file.resolve()
    if output_file.suffix.lower() != ".zip":
        raise BuildError("The output filename must end in .zip.")

    try:
        output_file.relative_to(source_directory)
    except ValueError:
        pass
    else:
        raise BuildError("The output ZIP cannot be inside source/.")

    files = _package_files(source_directory, repository_directory)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = _temporary_path(output_file)
    try:
        _write_archive(temporary_file, files)
        _validate_archive(temporary_file, len(files))
        os.replace(temporary_file, output_file)
    finally:
        temporary_file.unlink(missing_ok=True)

    return output_file


def _read_metadata(metadata_file):
    """Read and validate fields required by the QGIS plugin repository."""
    if not metadata_file.is_file():
        raise BuildError("Missing source/metadata.txt.")

    configuration = configparser.ConfigParser(interpolation=None)
    try:
        configuration.read_string(
            metadata_file.read_text(encoding="utf-8"),
            source=str(metadata_file),
        )
    except (UnicodeError, configparser.Error) as error:
        raise BuildError("Invalid metadata.txt: {}".format(error)) from error

    if not configuration.has_section("general"):
        raise BuildError("metadata.txt must contain a [general] section.")
    metadata = configuration["general"]
    missing = [
        field
        for field in REQUIRED_METADATA
        if not metadata.get(field, "").strip()
    ]
    if missing:
        raise BuildError(
            "metadata.txt is missing required fields: {}".format(
                ", ".join(missing)
            )
        )

    version = metadata["version"].strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version) is None:
        raise BuildError("metadata version is not safe for a package filename.")
    return metadata


def _validate_plugin(source_directory, repository_directory, metadata):
    """Check files required for installation and publication."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", PLUGIN_DIRECTORY):
        raise BuildError("The plugin directory name is not valid for QGIS.")

    for filename in ("__init__.py", "metadata.txt"):
        if not (source_directory / filename).is_file():
            raise BuildError("Missing source/{}.".format(filename))
    for filename in ("LICENSE", "README.md"):
        if not (repository_directory / filename).is_file():
            raise BuildError("Missing repository {}.".format(filename))

    icon = metadata.get("icon", "").strip()
    if icon:
        icon_path = PurePosixPath(icon)
        if icon_path.is_absolute() or ".." in icon_path.parts:
            raise BuildError("metadata icon must be relative to source/.")
        if not (source_directory / Path(*icon_path.parts)).is_file():
            raise BuildError("metadata icon does not exist: {}".format(icon))


def _package_files(source_directory, repository_directory):
    """Return source and archive paths for every distributable file."""
    files = []
    for source_file in sorted(source_directory.rglob("*")):
        relative_path = source_file.relative_to(source_directory)
        if source_file.is_symlink():
            raise BuildError(
                "Symlinks are not allowed in source/: {}".format(relative_path)
            )
        if not source_file.is_file() or _ignore(relative_path):
            continue
        files.append(
            (
                source_file,
                PurePosixPath(PLUGIN_DIRECTORY, *relative_path.parts),
            )
        )

    for filename in ("LICENSE", "README.md"):
        files.append(
            (
                repository_directory / filename,
                PurePosixPath(PLUGIN_DIRECTORY, filename),
            )
        )
    return sorted(files, key=lambda item: str(item[1]))


def _ignore(relative_path):
    """Exclude local caches and hidden/generated files from the upload."""
    return (
        relative_path.suffix.lower() in IGNORED_SUFFIXES
        or "__pycache__" in relative_path.parts
        or any(part.startswith(".") for part in relative_path.parts)
    )


def _temporary_path(output_file):
    descriptor, filename = tempfile.mkstemp(
        prefix=".{}-".format(output_file.stem),
        suffix=".tmp",
        dir=output_file.parent,
    )
    os.close(descriptor)
    return Path(filename)


def _write_archive(archive_file, files):
    """Write stable entries so unchanged sources produce identical packages."""
    with zipfile.ZipFile(archive_file, "w") as archive:
        for source_file, archive_path in files:
            information = zipfile.ZipInfo(str(archive_path), ZIP_TIMESTAMP)
            information.compress_type = zipfile.ZIP_DEFLATED
            information.external_attr = 0o100644 << 16
            archive.writestr(
                information,
                source_file.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def _validate_archive(archive_file, expected_file_count):
    """Check the completed package before replacing the requested output."""
    package_size = archive_file.stat().st_size
    if package_size > MAXIMUM_PACKAGE_SIZE:
        raise BuildError(
            "Package is {} bytes; QGIS limits uploads to {} bytes.".format(
                package_size, MAXIMUM_PACKAGE_SIZE
            )
        )

    with zipfile.ZipFile(archive_file) as archive:
        names = archive.namelist()
        if len(names) != expected_file_count or archive.testzip() is not None:
            raise BuildError("The generated ZIP archive failed validation.")
        required = {
            "{}/__init__.py".format(PLUGIN_DIRECTORY),
            "{}/metadata.txt".format(PLUGIN_DIRECTORY),
            "{}/LICENSE".format(PLUGIN_DIRECTORY),
        }
        if not required.issubset(names):
            raise BuildError("The generated ZIP is missing required plugin files.")
        if any(not name.startswith(PLUGIN_DIRECTORY + "/") for name in names):
            raise BuildError("Every archive entry must be inside qgis2fds/.")


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description="Build a qgis2fds ZIP for manual upload to plugins.qgis.org."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output ZIP path (default: dev/build/qgis2fds-VERSION.zip)",
    )
    return parser.parse_args()


def main():
    arguments = _parse_arguments()
    try:
        output_file = build_plugin(REPOSITORY_DIRECTORY, arguments.output)
    except BuildError as error:
        raise SystemExit("Build failed: {}".format(error)) from error

    with zipfile.ZipFile(output_file) as archive:
        file_count = len(archive.infolist())
    print("Built {}".format(output_file))
    print("Archive root: {}/".format(PLUGIN_DIRECTORY))
    print("Files: {}; size: {} bytes".format(file_count, output_file.stat().st_size))
    print("Upload is intentionally not performed.")


if __name__ == "__main__":
    main()
