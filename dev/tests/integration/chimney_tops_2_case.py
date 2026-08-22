"""Parameter table for the Chimney Tops 2 QGIS integration case."""

from pathlib import Path


CASE_DIRECTORY = Path(__file__).resolve().parent
QGIS_DIRECTORY = (
    CASE_DIRECTORY.parents[2]
    / "assets"
    / "cases"
    / "chimney_tops_2"
    / "QGIS"
)

# The first row retains the project's 30 m terrain sampling and 10 m FDS cell
# size. Coarser GEOM and OBST rows keep the suite practical while exercising
# both terrain serialization paths with land use, ignition, and wind enabled.
CASES = (
    {
        "name": "geom_project",
        "chid": "chimney_tops_2_geom_project",
        "settings": {
            "pixel_size": 30.0,
            "tex_pixel_size": 10.0,
            "nmesh": 264,
            "cell_size": 10.0,
            "t_begin": 0.0,
            "t_end": 0.0,
            "export_obst": False,
        },
    },
    {
        "name": "geom_coarse",
        "chid": "chimney_tops_2_geom_coarse",
        "settings": {
            "pixel_size": 90.0,
            "tex_pixel_size": 90.0,
            "nmesh": 6,
            "cell_size": 30.0,
            "t_begin": 0.0,
            "t_end": 86400.0,
            "export_obst": False,
        },
    },
    {
        "name": "obst_coarse",
        "chid": "chimney_tops_2_obst_coarse",
        "settings": {
            "pixel_size": 90.0,
            "tex_pixel_size": 90.0,
            "nmesh": 6,
            "cell_size": 30.0,
            "t_begin": 0.0,
            "t_end": 86400.0,
            "export_obst": True,
        },
    },
)

SUITE = {
    "name": "chimney_tops_2",
    "project_file": QGIS_DIRECTORY / "Chimney_Tops_2.qgs",
    "reference_file": CASE_DIRECTORY / "chimney_tops_2_references.json",
    "base_settings": {
        "ellipsoid": "EPSG:7019",
        "extent_layer": "fds_extent_0496da50_b04e_436f_8bc9_9f33135b1d88",
        "dem_layer": "LC20_Elav_220_Abrev_18e22c72_95f1_48d2_a258_01f996ac98ff",
        "landuse_layer": "LC22_F13_220_Abrev_0e9ab1c8_e284_40b9_86bb_5c1e1fa12c55",
        "landuse_type_filepath": "./sheets/Landfire.gov_F13.csv",
        "fire_layer": "init_fire_210d472e_7a2b_41eb_a9ff_aaa853d323e6",
        "wind_filepath": "./sheets/Chimney_Tops_2_Wind.csv",
    },
    "cases": CASES,
}
