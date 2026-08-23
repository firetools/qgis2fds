# qgis2fds development

This directory contains the pytest configuration, automated tests, reference
rebuilding tools, and the QGIS plugin package builder. Run the commands below
from the repository root unless a section explicitly changes directory.

## Prerequisites

### Python tests and package builds

Install a recent Python 3 release with these Python packages:

- `pytest`, which discovers and runs the tests;
- `numpy`, which is used by qgis2fds and its unit tests.

For example, install them in the active Python environment with:

```sh
python3 -m pip install pytest numpy
```

Check that the expected interpreter and packages are available:

```sh
python3 --version
python3 -c "import numpy, pytest; print(numpy.__version__, pytest.__version__)"
```

The package builder uses only the Python standard library. It does not need
QGIS and does not require additional build packages.

The repository contains `dev/pytest.ini`. This is a pytest configuration file,, it defines test discovery, Python import
paths, the integration marker, and the command used to start `qgis_process`.

`pytest-qgis` is not required. The integration tests launch `qgis_process` as a
separate process and exercise the installed qgis2fds Processing provider.

### QGIS integration tests

The integration tests additionally require:

- QGIS 4.2 or a compatible later QGIS 4 release;
- the qgis2fds plugin installed and enabled in the QGIS profile used by
  `qgis_process`;
- access to the case data under `assets/cases/`;
- internet access for the `golden_gate_remote` test, which downloads its DEM
  and landuse coverage from remote WCS services.

FDS is optional. It is required only when `run_fds = true` in
`dev/pytest.ini`. The configured FDS integration currently targets FDS 6.11.1.

The reference environment uses the QGIS Flatpak application:

```sh
flatpak run org.qgis.qgis
```

During development, the Flatpak profile can load the working tree through this
symbolic link:

```text
~/.var/app/org.qgis.qgis/data/QGIS/QGIS4/profiles/default/python/plugins/qgis2fds
  -> /absolute/path/to/qgis2fds/source
```

The link name must be `qgis2fds`, even though the repository directory that it
targets is named `source`. Inspect the plugins visible to the configured
Flatpak installation with:

```sh
flatpak run --command=qgis_process org.qgis.qgis plugins list
```

The list must contain qgis2fds. If it does not, check the profile path, the
symbolic link, and whether the plugin is enabled in that profile.

## Configure external executables

### QGIS Processing

The QGIS process is read from the
`qgis_process` setting in `dev/pytest.ini` and executed exactly as
configured, without a shell.

The Flatpak configuration is:

```ini
qgis_process = flatpak run --command=qgis_process org.qgis.qgis
```

For a native QGIS installation, replace it with the appropriate executable:

```ini
qgis_process = /usr/bin/qgis_process
```

An absolute path is preferable because it makes the selected QGIS installation
unambiguous. Quote paths containing spaces:

```ini
qgis_process = "/path containing spaces/qgis_process"
```

Arguments may follow the executable. The value is split into an argument list
and passed directly to Python's subprocess API, so shell pipelines,
redirections, aliases, and shell variable expansion are not supported.

The same setting is used by both the integration tests and the reference
rebuild script. If the first executable in the command is unavailable, pytest
reports the integration tests as skipped with the reason shown in its summary.
If the executable starts but QGIS or the plugin is misconfigured, the
integration tests fail and include the captured standard output and error.

### FDS

The FDS executable and its optional execution flag are also explicit in
`dev/pytest.ini`:

```ini
fds = /var/home/egissi/.local/opt/FDS/FDS6/bin/fds
run_fds = false
```

Change `fds` to the absolute path of the FDS installation being tested. Confirm
the selected version independently, for example:

```sh
/path/to/fds -v
```

FDS validation is disabled by default because initialization of the terrain
and meshes can take minutes even for a short simulation. Enable it explicitly:

```ini
run_fds = true
```

When enabled, every integration parameter row is exported with
`t_end = t_begin + 1` second and the resulting `.fds` file is executed from its
temporary output directory. A case passes FDS validation only when the process
returns exit status zero and no line beginning with `ERROR` appears in FDS
standard output, standard error, or the generated `.out` file. FDS warnings do
not fail the test. Each FDS process has a five-minute timeout.

## Run tests

### Complete test suite

By default pytest runs both the fast unit tests and the QGIS integration tests.
Optional FDS execution follows the `run_fds` setting described above.
Run it from `dev/` so `pytest.ini` and its relative test paths are applied
directly:

```sh
cd dev
pytest
```

The default test paths are:

- `tests/unit/` for tests that run entirely in the host Python process;
- `tests/integration/` for end-to-end QGIS project exports.

### Unit tests only

From the repository root:

```sh
pytest -c dev/pytest.ini dev/tests/unit
```

These tests cover FDS text generation, binary geometry generation, and the
plugin package builder. They do not start QGIS and should complete quickly.

### Integration tests only

From the repository root:

```sh
pytest -c dev/pytest.ini dev/tests/integration
```

The integration suite loads the QGIS projects stored in `assets/cases/`, runs
the installed `NIST FDS:Export FDS case` Processing algorithm, and compares
stable signatures of the generated files with the JSON references in
`dev/tests/integration/`. If enabled, FDS then validates every generated case.

Each parameter row operates on a fresh temporary copy of its complete QGIS
case. The copy is created below the repository root because the Flatpak has a
private `/tmp` directory. FDS output, downloaded remote rasters, and project
changes therefore affect only the temporary copy. The workspace is removed at
the end of the test, while the canonical data under `assets/cases/` remain
unchanged.

Run a subset by matching its pytest identifier, for example:

```sh
pytest -c dev/pytest.ini dev/tests/integration -k golden_gate_local
pytest -c dev/pytest.ini dev/tests/integration -k cern_meyrin
```

Use `-vv` to display every parameterized case name:

```sh
pytest -c dev/pytest.ini dev/tests/integration -vv
```

### Rebuild integration references

Only rebuild references after confirming that changed output is intentional.
Rebuild one or more named suites from the repository root:

```sh
dev/tests/integration/rebuild_references.py cern_meyrin
dev/tests/integration/rebuild_references.py cern_meyrin golden_gate_local
```

Rebuild every registered suite with:

```sh
dev/tests/integration/rebuild_references.py --all
```

The script uses the same temporary-case mechanism and the same `qgis_process`
setting as pytest. It replaces the selected JSON reference manifests in
`dev/tests/integration/`; review their version-control diff before accepting
the new references. Reference rebuilding exports cases but does not run FDS.

## Build the QGIS plugin package

The builder creates a ZIP suitable for manual upload to the
[QGIS plugin repository](https://plugins.qgis.org/). It never logs in, connects
to the repository, or uploads anything.

The package layout and validation follow the official
[QGIS 4.2 plugin structure requirements](https://docs.qgis.org/4.2/en/docs/pyqgis_developer_cookbook/plugins/plugins.html)
and [QGIS plugin publishing guidelines](https://plugins.qgis.org/docs/publish).

Run the builder from the repository root:

```sh
python3 dev/build/build_plugin.py
```

The package version is read from `source/metadata.txt`. With version `2.0.0`,
the default output is:

```text
dev/build/qgis2fds-2.0.0.zip
```

Choose another output path with `--output`; the filename must end in `.zip`:

```sh
python3 dev/build/build_plugin.py --output /tmp/qgis2fds-2.0.0.zip
```

The builder:

1. validates the required metadata fields and version string;
2. checks `source/__init__.py`, `source/metadata.txt`, the configured icon,
   the repository `LICENSE`, and the repository `README.md`;
3. packages the contents of `source/` below a single `qgis2fds/` directory;
4. adds `LICENSE` and `README.md` to that plugin directory;
5. excludes hidden files, Python bytecode, and `__pycache__` directories;
6. produces deterministic ZIP entries, so unchanged inputs produce identical
   archives;
7. checks ZIP integrity, required archive entries, and the 25 MB upload limit;
8. replaces an existing output package only after the new archive validates.

The final archive has this general layout:

```text
qgis2fds-VERSION.zip
└── qgis2fds/
    ├── __init__.py
    ├── metadata.txt
    ├── LICENSE
    ├── README.md
    ├── firetools-logo_64.png
    └── plugin source modules
```

Inspect the completed package without extracting it:

```sh
python3 -m zipfile -l dev/build/qgis2fds-2.0.0.zip
```

After inspection and testing, upload the ZIP manually through the QGIS plugin
repository website at https://plugins.qgis.org/

## Common failures

- `Configured qgis_process executable is unavailable`: correct the
  `qgis_process` value in `dev/pytest.ini`.
- `Algorithm NIST FDS:Export FDS case not found`: install or enable qgis2fds in
  the profile used by the configured QGIS command.
- `Configured fds executable is unavailable`: correct the `fds` path or set
  `run_fds = false` in `dev/pytest.ini`.
- FDS validation failure: inspect the reported FDS errors and the generated
  case diagnostics. The test preserves stdout and stderr in its failure report.
- Remote Golden Gate failures: verify network access and availability of the
  configured WCS services.
- Reference mismatch: inspect the generated-output change before rebuilding
  references; do not treat rebuilding as an automatic fix.
- Package build failure: read the reported missing metadata or file, correct
  the repository input, and run the builder again.
