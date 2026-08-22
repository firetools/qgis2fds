# qgis2fds

qgis2fds is a QGIS Processing plugin that exports a georeferenced terrain as a
working [NIST Fire Dynamics Simulator](https://pages.nist.gov/fds-smv/) input
for wildfire propagation. It writes either
cell-aligned `OBST` terrain or a compact triangulated binary `GEOM` terrain.

The Processing algorithm remains `NIST FDS:Export FDS case`. Its public input
keys are unchanged so existing QGIS projects and `qgis_process` commands can be
reused:

`chid`, `origin`, `nmesh`, `pixel_size`, `tex_pixel_size`, `cell_size`,
`t_begin`, `t_end`, `fds_path`, `landuse_type_filepath`, `text_filepath`,
`wind_filepath`, `dem_layer`, `landuse_layer`, `extent_layer`, `fire_layer`,
and `export_obst`.

The implementation is in `source/`. Reusable landuse catalogs and QGIS styles
remain in `landuse_types/` and `styles/`.

## Inputs

- `dem_layer` and `extent_layer` are required and must have valid CRSs.
- `landuse_layer` requires a two-column landuse/SURF CSV file.
- `fire_layer` may contain optional integer `bc_in` and `bc_out` fields. When
  absent, the last and penultimate landuse codes are used for the ignition area
  and its one-pixel outer ring.
- The wind CSV columns are time in seconds, speed in m/s, and direction in
  degrees. With no wind file, the generated case uses zero wind.
- `text_filepath` is appended before `&TAIL`, allowing case-specific FDS
  namelists without modifying the plugin.

Mode 1 applies the global wind uniformly and runs empirical surface fire
propagation without terrain-modified flow, active heat release, or a fluid
solve.

## Tests

Run all tests from the `dev` directory by default:

```sh
cd dev
pytest
```

Run the fast unit tests independently:

```sh
pytest -c dev/pytest.ini dev/tests/unit
```

Run the QGIS integration tests independently:

```sh
pytest -c dev/pytest.ini dev/tests/integration
```

Integration case tables, reference manifests, shared support code, and the
reference rebuild command are kept together in `dev/tests/integration/`.
The `qgis_process` command is explicit in `dev/pytest.ini`; change that setting
when testing against a native QGIS installation or a different Flatpak setup.

## Temporary reminder

~/.var/app/org.qgis.qgis/data/QGIS/QGIS4/profiles/default/python/plugins/qgis2fds
→ /var/home/egissi/Documenti/Git/qgis2fds/source
