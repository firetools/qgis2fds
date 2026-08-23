"""Parameter table for the Golden Gate Local QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
CASE_ASSETS_DIRECTORY = (
    CASE_DIRECTORY.parents[2]
    / "assets"
    / "cases"
    / "golden_gate_local"
)

# Exercise the saved project resolution, a coarser GEOM export, and explicit
# OBST terrain cells. Every row uses the local DEM, landuse, ignition, and wind
# inputs so failures cannot be hidden by remote layer availability.
CASES = (
    {
        "name": "geom_project",
        "chid": "golden_gate_local_geom_project",
        "settings": {
            "pixel_size": 10.0,
            "tex_pixel_size": 2.0,
            "nmesh": 4,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": False,
        },
    },
    {
        "name": "geom_coarse",
        "chid": "golden_gate_local_geom_coarse",
        "settings": {
            "pixel_size": 20.0,
            "tex_pixel_size": 4.0,
            "nmesh": 2,
            "cell_size": 20.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": False,
        },
    },
    {
        "name": "obst_project",
        "chid": "golden_gate_local_obst_project",
        "settings": {
            "pixel_size": 10.0,
            "tex_pixel_size": 2.0,
            "nmesh": 4,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": True,
        },
    },
)

SUITE = {
    "name": "golden_gate_local",
    "project_file": CASE_ASSETS_DIRECTORY / "golden_gate.qgs",
    "reference_file": CASE_DIRECTORY / "golden_gate_local_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7019",
        "origin": "-2279359.733937,1963331.421795 [EPSG:5070]",
        "extent_layer": "Extent_0642b0c8_932e_418f_9e94_a1a555ee0f05",
        "dem_layer": "US_DEM2016_local_ec8fe444_644d_4f3a_a065_e211b15dbea3",
        "landuse_layer": "US_200F13_20_local_2c3fbb52_c886_43b9_a912_89e08e7884b3",
        "landuse_type_filepath": "./sheets/Landfire F13 landuse type.csv",
        "fire_layer": "Fire_b0dc7bbb_6702_4e71_9afe_8048e4f66b7c",
        "wind_filepath": "./sheets/wind.csv",
    },
    "cases": CASES,
}
