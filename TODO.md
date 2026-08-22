- wiki documentation: document the algorithm, rewrite the quickstart
- put the examples in a separate verification or examples directory
- new devc layer
- new github actions
- Inspect 139 error in qgis
- release and upload new plugin
- import data from fds case with fdsreader
- create fdswriter

- tests:
Measured line coverage from the six in-process unit tests:
Module	Coverage
bingeom.py	89.2%
model.py	86.2%
fds.py	55.1%
Combined measured source	63.6%


The 11 QGIS integration cases exercise algorithm.py, parameters.py, spatial.py, remote.py, GEOM, OBST, texture rendering, and WCS downloads, but their line coverage is not measured.
Largest unit-test gaps:
Surface catalog CSV loading and validation.
OBST edge-cell generation.
Invalid and empty wind files.
Terrain array shape errors.
Remote WCS failure and validation paths.
Optional missing land-use/fire/wind inputs.
BINGEOM write-failure cleanup.
Recommendation: configure coverage.py inside the QGIS Flatpak subprocess and combine its data with host pytest coverage. This is needed before setting a meaningful project-wide coverage threshold.