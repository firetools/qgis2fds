"""Parameter table for the CERN Meyrin QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
CASE_ASSETS_DIRECTORY = (
    CASE_DIRECTORY.parents[2] / "assets" / "cases" / "cern_meyrin"
)

# Exercise both terrain representations with the parameters stored in the QGIS
# project. Layer IDs make project loading itself part of the behavior under test.
CASES = (
    {
        "name": "geom",
        "chid": "cern_meyrin_geom",
        "settings": {
            "pixel_size": 0.5,
            "tex_pixel_size": 0.5,
            "nmesh": 4,
            "cell_size": 0.5,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": False,
        },
    },
    {
        "name": "obst",
        "chid": "cern_meyrin_obst",
        "settings": {
            "pixel_size": 0.5,
            "tex_pixel_size": 0.5,
            "nmesh": 4,
            "cell_size": 0.5,
            "t_begin": 0.0,
            "t_end": 1.0,
            "export_obst": True,
        },
    },
)

SUITE = {
    "name": "cern_meyrin",
    "project_file": CASE_ASSETS_DIRECTORY / "cern_meyrin.qgs",
    "reference_file": CASE_DIRECTORY / "cern_meyrin_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7004",
        "extent_layer": "Extent_aecca660_0811_44d7_9f24_f7f364999b60",
        "dem_layer": "dem_layer_90178e14_1fe5_40d2_8bd3_2721c14f8b0c",
    },
    "cases": CASES,
}
