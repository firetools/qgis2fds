"""Regression test for the reusable BINGEOM writer."""

import struct

import numpy as np

from source.bingeom import write_binary_geometry
from source.fds import Surface, SurfaceCatalog
from source.model import SpatialGrid, TerrainData


def _read_records(filepath):
    records = []
    data = filepath.read_bytes()
    offset = 0
    while offset < len(data):
        size = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        payload = data[offset : offset + size]
        offset += size
        trailer = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        assert trailer == size
        records.append(payload)
    return records


def test_write_binary_geometry_records(tmp_path):
    grid = SpatialGrid(
        crs_authid="EPSG:32610",
        crs_description="UTM test grid",
        x_min=0.0,
        y_min=0.0,
        pixel_size=10.0,
        columns=2,
        rows=2,
        origin_x=0.0,
        origin_y=0.0,
        longitude=0.0,
        latitude=0.0,
    )
    terrain = TerrainData(
        grid,
        elevations=[[10.0, 20.0], [30.0, 40.0]],
        landuse=[[0, 1], [1, 2]],
    )
    catalog = SurfaceCatalog(
        (
            Surface(0, "Inert"),
            Surface(1, "Fuel"),
            Surface(2, "Burned"),
        )
    )
    output = tmp_path / "terrain.bingeom"

    write_binary_geometry(str(output), terrain, catalog)
    records = _read_records(output)

    assert len(records) == 6
    assert np.frombuffer(records[0], dtype="<i4").tolist() == [2]
    assert np.frombuffer(records[1], dtype="<i4").tolist() == [9, 8, 3, 0]
    assert np.frombuffer(records[2], dtype="<f8").size == 27
    assert np.frombuffer(records[3], dtype="<i4").size == 24
    assert np.frombuffer(records[4], dtype="<i4").tolist() == [
        1,
        1,
        2,
        2,
        2,
        2,
        3,
        3,
    ]
    assert records[5] == b""
    assert not (tmp_path / "terrain.bingeom.tmp").exists()

