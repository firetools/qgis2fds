"""Parameter table for the Golden Gate Remote QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
CASE_ASSETS_DIRECTORY = (
    CASE_DIRECTORY.parents[2]
    / "assets"
    / "cases"
    / "golden_gate_remote"
)

# Each row downloads fresh WCS copies before exercising one terrain format.
CASES = (
    {
        "name": "geom",
        "chid": "golden_gate_remote_geom",
        "settings": {
            "pixel_size": 10.0,
            "tex_pixel_size": 1.0,
            "nmesh": 4,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": False,
        },
    },
    {
        "name": "obst",
        "chid": "golden_gate_remote_obst",
        "settings": {
            "pixel_size": 10.0,
            "tex_pixel_size": 1.0,
            "nmesh": 4,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": True,
        },
    },
)

SUITE = {
    "name": "golden_gate_remote",
    "project_file": CASE_ASSETS_DIRECTORY / "golden_gate_remote.qgs",
    "reference_file": CASE_DIRECTORY / "golden_gate_remote_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7019",
        "origin": "-2279359.733937,1963331.421795 [EPSG:5070]",
        "extent_layer": "Extent_0642b0c8_932e_418f_9e94_a1a555ee0f05",
        "dem_layer": "LF2020_Elev_CONUS_1362afda_95af_4bf3_a906_68535cdb48fc",
        "landuse_layer": "LF2025_FBFM13_CONUS_ecbcf54b_b570_4151_ba4b_61221a6973f9",
        "landuse_type_filepath": "./sheets/Landfire F13 landuse type.csv",
        "fire_layer": "Fire_b0dc7bbb_6702_4e71_9afe_8048e4f66b7c",
        "wind_filepath": "./sheets/wind.csv",
    },
    "cases": CASES,
}
