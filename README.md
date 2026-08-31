

# **qgis2fds** repository

[**qgis2fds**](https://firetools.org/qgis2fds) is the open source plugin
to export terrains and landuse from the [QGIS](http://www.qgis.org)
geographic information system to the [NIST Fire Dynamics Simulator (FDS)](https://pages.nist.gov/fds-smv/)
for wildfire simulation and atmospheric dispersion of fire pollutants.

Visit the [qgis2fds website](https://firetools.org/qgis2fds) for further info.

The plugin provides two QGIS Processing algorithms:

- **Export FDS case** creates a georeferenced wildfire case from QGIS data.
- **Import FDS results** reads a completed case using the same `chid` and
  `fds_path` project settings. It imports every AGL slice found in the
  Smokeview manifest, plus `FIRE ARRIVAL TIME`, `FIRE RESIDENCE TIME`, and
  `LS SPREAD RATE` boundary output. Results are added as georeferenced temporal
  mesh layers; horizontal velocity is a vector dataset. Each quantity is put
  in a separate temporal mesh layer.

The importer requires the `.fds` input and the `.smv` manifest produced by FDS,
then reads the result and topology files referenced by that manifest. It writes
persistent standalone UGRID layers into a new `<chid>_qgis_results` directory
below the FDS case folder. Existing result directories are not overwritten,
remote input files are not accessed, and the QGIS project is not saved
automatically.
