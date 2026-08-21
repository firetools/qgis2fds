"""Small regression tests for the pure-Python FDS case builder."""

import numpy as np
import pytest

from source.fds import (
    Surface,
    SurfaceCatalog,
    build_assumptions,
    build_mesh_layout,
    read_wind,
    render_case,
)
from source.model import SpatialGrid, TerrainData


def _terrain_and_catalog():
    grid = SpatialGrid(
        crs_authid="EPSG:32610",
        crs_description="WGS 84 / UTM zone 10N",
        x_min=100.0,
        y_min=200.0,
        pixel_size=10.0,
        columns=2,
        rows=2,
        origin_x=110.0,
        origin_y=210.0,
        longitude=-122.5,
        latitude=37.8,
        north_bearing=-0.3,
    )
    terrain = TerrainData(
        grid,
        elevations=[[100.0, 110.0], [120.0, 130.0]],
        landuse=[[1, 1000], [1000, 1001]],
    )
    catalog = SurfaceCatalog(
        (
            Surface(1, "Fuel", "&SURF ID='Fuel', VEG_LSET_FUEL_INDEX=1 /"),
            Surface(
                1000,
                "Ignition",
                "&SURF ID='Ignition', VEG_LSET_IGNITE_TIME=0. /",
            ),
            Surface(1001, "Burned", "&SURF ID='Burned' /"),
        ),
        filepath="landuse.csv",
    )
    return terrain, catalog


def test_read_wind_accepts_strictly_increasing_times(tmp_path):
    wind_file = tmp_path / "wind.csv"
    wind_file.write_text(
        "Time,Speed,Direction\n0,2,45\n60,5,90\n",
        encoding="utf-8",
    )

    samples = read_wind(str(wind_file))

    assert [(item.time, item.speed, item.direction) for item in samples] == [
        (0.0, 2.0, 45.0),
        (60.0, 5.0, 90.0),
    ]


def test_read_wind_rejects_duplicate_times(tmp_path):
    wind_file = tmp_path / "wind.csv"
    wind_file.write_text(
        "Time,Speed,Direction\n0,2,45\n0,5,90\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be greater than"):
        read_wind(str(wind_file))


def test_assumptions_count_only_ignition_cells():
    terrain, catalog = _terrain_and_catalog()
    layout = build_mesh_layout(terrain, cell_size=10.0, maximum_meshes=1)

    assumptions = build_assumptions(
        terrain=terrain,
        catalog=catalog,
        layout=layout,
        wind_filepath="wind.csv",
        provenance="test",
        qgis_filepath="case.qgz",
        generated_at="Thu, 01 Jan 2026, 00:00:00",
        dem_name="DEM",
        landuse_name="Landuse",
        fire_name="Fire",
    )

    assert "Ignition cells: 2" in assumptions
    assert not any("Fuel definitions" in item for item in assumptions)


def test_mesh_domain_strictly_contains_the_terrain():
    terrain, _ = _terrain_and_catalog()

    layout = build_mesh_layout(terrain, cell_size=10.0, maximum_meshes=1)
    grid = terrain.grid

    assert layout.x_min < grid.x_min - grid.origin_x
    assert layout.x_max > grid.x_max - grid.origin_x
    assert layout.y_min < grid.y_min - grid.origin_y
    assert layout.y_max > grid.y_max - grid.origin_y


def test_rendered_case_keeps_surface_only_wildfire_settings():
    terrain, catalog = _terrain_and_catalog()
    layout = build_mesh_layout(terrain, cell_size=10.0, maximum_meshes=1)

    case = render_case(
        chid="simple_case",
        t_begin=0.0,
        t_end=60.0,
        terrain=terrain,
        catalog=catalog,
        layout=layout,
        wind=(),
        export_obst=False,
        binary_filename="simple_case_terrain.bingeom",
        texture_filename="",
        extra_text="",
        assumptions=("Test assumption",),
    )

    assert case.startswith("! Test assumption\n")
    assert "NORTH_BEARING=-0.300000, LEVEL_SET_MODE=1" in case
    assert "&RADI RADIATION=F /" in case
    assert "IS_TERRAIN=T, EXTEND_TERRAIN=T" in case
    assert "QUANTITY='FIRE ARRIVAL TIME'" in case
    assert "QUANTITY='FIRE RESIDENCE TIME'" in case
    assert "QUANTITY='LS SPREAD RATE'" in case

