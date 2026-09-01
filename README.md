

# **qgis2fds** repository

[**qgis2fds**](https://firetools.org/qgis2fds) is the open source plugin
to export terrains and landuse from the [QGIS](http://www.qgis.org)
geographic information system to the [NIST Fire Dynamics Simulator (FDS)](https://pages.nist.gov/fds-smv/)
for wildfire simulation and atmospheric dispersion of fire pollutants.

Visit the [qgis2fds website](https://firetools.org/qgis2fds) for further info.

The plugin provides two QGIS Processing algorithms:

- **Export FDS case** creates a georeferenced wildfire case from QGIS data.
- **Import FDS results** reads a calculated FDS case, imports every SLCF AGL results plus wildfire BNDFs. All imported results are added as georeferenced temporal mesh layers.
