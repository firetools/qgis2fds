# qgis2fds

qgis2fds is a QGIS Processing plugin that exports a georeferenced terrain as a
working [NIST Fire Dynamics Simulator](https://pages.nist.gov/fds-smv/) input
for wildfire propagation. It writes either
cell-aligned `OBST` terrain or a compact triangulated binary `GEOM` terrain.

The complete installable plugin is in `source/`. Reusable landuse catalogs,
QGIS styles, and integration-test cases are stored under `assets/`.

## Documentation and support

The [qgis2fds wiki](https://github.com/firetools/qgis2fds/wiki) contains the
installation guide, quickstart, parameter reference, algorithms, and FAQ.
Questions and user support are handled in
[GitHub Discussions](https://github.com/firetools/qgis2fds/discussions).
