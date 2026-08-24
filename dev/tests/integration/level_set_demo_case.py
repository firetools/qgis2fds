"""Parameter table for the Level Set Demo QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
CASE_ASSETS_DIRECTORY = (
    CASE_DIRECTORY.parents[2]
    / "assets"
    / "cases"
    / "level_set_demo"
)

# Exercise both terrain representations with the supplied project parameters.
# The blank origin intentionally uses the domain extent centroid.
CASES = (
    {
        "name": "geom",
        "chid": "level_set_demo_geom",
        "settings": {
            "pixel_size": 30.0,
            "tex_pixel_size": 1.0,
            "nmesh": 100,
            "cell_size": 30.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": False,
        },
    },
    {
        "name": "obst",
        "chid": "level_set_demo_obst",
        "settings": {
            "pixel_size": 30.0,
            "tex_pixel_size": 1.0,
            "nmesh": 100,
            "cell_size": 30.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": True,
        },
    },
)

SUITE = {
    "name": "level_set_demo",
    "project_file": CASE_ASSETS_DIRECTORY / "Level_Set_Demo.qgs",
    "reference_file": CASE_DIRECTORY / "level_set_demo_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7030",
        "extent_layer": "Domain_Extent_8a348d62_eebd_4f32_8e80_6f4237784cc9",
        "dem_layer": "clipped_dem_layer_1c3770e8_249f_49a7_ad02_ab23b165a9be",
        "landuse_layer": "land_use_layer_3d5239fd_064c_469c_9e6b_a1290415a285",
        "landuse_type_filepath": "./sheets/Landfire.gov_F13.csv",
        "fire_layer": "Ignition_Area_1edacf04_da62_47fd_9ee3_fbab5e378fd3",
        "wind_filepath": "./sheets/Level_Set_Demo_Wind.csv",
    },
    "cases": CASES,
}
