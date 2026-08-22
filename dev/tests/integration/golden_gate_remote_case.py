"""Parameter table for the Golden Gate Remote QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
QGIS_DIRECTORY = (
    CASE_DIRECTORY.parents[2]
    / "assets"
    / "cases"
    / "golden_gate_remote"
    / "QGIS"
)

# One row is sufficient here: the purpose of this network-backed suite is to
# exercise fresh WCS downloads for both terrain rasters before a GEOM export.
CASES = (
    {
        "name": "geom_project",
        "chid": "golden_gate_remote_geom_project",
        "settings": {
            "pixel_size": 10.0,
            "tex_pixel_size": 2.0,
            "nmesh": 4,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 30.0,
            "export_obst": False,
        },
    },
)

SUITE = {
    "name": "golden_gate_remote",
    "project_file": QGIS_DIRECTORY / "golden_gate_remote.qgs",
    "reference_file": CASE_DIRECTORY / "golden_gate_remote_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7019",
        "origin": "-2279359.733937,1963331.421795 [EPSG:5070]",
        "extent_layer": "Extent_0642b0c8_932e_418f_9e94_a1a555ee0f05",
        "dem_layer": "_5294a749_25fa_4861_990a_283ddf87dccd",
        "landuse_layer": "_f805e8d6_196e_4707_83da_e16f9fbf0e9e",
        "landuse_type_filepath": "./sheets/Landfire F13 landuse type.csv",
        "fire_layer": "Fire_b0dc7bbb_6702_4e71_9afe_8048e4f66b7c",
        "wind_filepath": "./sheets/wind.csv",
    },
    "cases": CASES,
}
