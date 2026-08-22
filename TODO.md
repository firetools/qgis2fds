- wiki documentation: document the algorithm, rewrite the quickstart
- new devc layer
- new github actions
- Inspect 139 error in qgis
- release and upload new plugin
- import data from fds case with fdsreader
- create fdswriter
- add unit tests
Largest unit-test gaps:
Surface catalog CSV loading and validation.
OBST edge-cell generation.
Invalid and empty wind files.
Terrain array shape errors.
Remote WCS failure and validation paths.
Optional missing land-use/fire/wind inputs.
BINGEOM write-failure cleanup.
Recommendation: configure coverage.py inside the QGIS Flatpak subprocess and combine its data with host pytest coverage. This is needed before setting a meaningful project-wide coverage threshold.