"""Write FDS terrain geometry in the portable BINGEOM binary format.

This module intentionally has no QGIS dependencies. ``write_binary_geometry``
accepts any terrain and surface-catalog objects that provide the small interface
documented by the writer, so the serializer can be reused by other exporters.
"""

import os
import struct

import numpy as np


def write_binary_geometry(filepath, terrain, catalog):
    """Write a terrain BINGEOM file consumed by an FDS ``GEOM`` namelist.

    ``terrain`` must expose ``grid``, ``elevations``, and ``landuse``. Its grid
    supplies ``columns``, ``rows``, ``x_min``, ``y_min``, ``pixel_size``,
    ``origin_x``, and ``origin_y``. ``catalog`` must expose ``surfaces`` and
    ``fds_index(code)``.
    """
    grid = terrain.grid
    vertex_count = (grid.columns + 1) * (grid.rows + 1)
    face_count = 2 * grid.columns * grid.rows
    temporary = filepath + ".tmp"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(temporary, "wb") as handle:
            # Record order follows the FDS terrain reader: geometry type, counts,
            # vertices, triangular faces, face surfaces, and volume data.
            _write_record(handle, "i", ((2,),), 1)  # FDS terrain geometry type
            _write_record(
                handle,
                "i",
                ((vertex_count, face_count, len(catalog.surfaces), 0),),
                4,
            )
            _write_record(
                handle,
                "d",
                _vertices(terrain),
                3 * vertex_count,
            )
            _write_record(handle, "i", _faces(grid), 3 * face_count)
            _write_record(
                handle,
                "i",
                _face_surfaces(terrain, catalog),
                face_count,
            )
            _write_record(handle, "i", ((),), 0)
        os.replace(temporary, filepath)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def _vertices(terrain):
    """Yield one vectorized vertex row at a time."""
    grid = terrain.grid
    elevations = np.asarray(terrain.elevations, dtype="<f8")
    expected_shape = (grid.rows, grid.columns)
    if elevations.shape != expected_shape:
        raise ValueError(
            "Elevation grid has shape {}, expected {}.".format(
                elevations.shape, expected_shape
            )
        )

    columns = np.arange(grid.columns + 1, dtype="<f8")
    x_coordinates = grid.x_min + columns * grid.pixel_size - grid.origin_x

    for row in range(grid.rows + 1):
        # Accumulate neighbors in the same order as TerrainData.corner_elevation.
        corner_sum = np.zeros(grid.columns + 1, dtype="<f8")
        neighbor_count = np.zeros(grid.columns + 1, dtype="<i4")
        for cell_row in (row - 1, row):
            if not 0 <= cell_row < grid.rows:
                continue
            cell_values = elevations[cell_row]
            corner_sum[1:] += cell_values
            neighbor_count[1:] += 1
            corner_sum[:-1] += cell_values
            neighbor_count[:-1] += 1

        vertices = np.empty((grid.columns + 1, 3), dtype="<f8")
        vertices[:, 0] = x_coordinates
        vertices[:, 1] = (
            grid.y_min + row * grid.pixel_size - grid.origin_y
        )
        vertices[:, 2] = corner_sum / neighbor_count
        yield vertices.reshape(-1)


def _faces(grid):
    """Yield one vectorized triangle-index row at a time."""
    # BINGEOM vertex indexes are 1-based. Split every raster cell along the same
    # diagonal and use consistent winding for both triangles.
    stride = grid.columns + 1
    column_offsets = np.arange(grid.columns, dtype="<i4")
    for row in range(grid.rows):
        lower_left = row * stride + column_offsets + 1
        lower_right = lower_left + 1
        upper_left = lower_left + stride
        upper_right = upper_left + 1

        faces = np.empty((grid.columns, 6), dtype="<i4")
        faces[:, 0] = lower_left
        faces[:, 1] = lower_right
        faces[:, 2] = upper_left
        faces[:, 3] = upper_right
        faces[:, 4] = upper_left
        faces[:, 5] = lower_right
        yield faces.reshape(-1)


def _face_surfaces(terrain, catalog):
    """Yield vectorized pairs of surface indexes for each terrain row."""
    for row in terrain.landuse:
        # Landuse rows normally contain few distinct classes. Map each class once
        # and reconstruct the row through NumPy's inverse indexes.
        codes, inverse = np.unique(row, return_inverse=True)
        class_indexes = np.fromiter(
            (catalog.fds_index(int(code)) for code in codes),
            dtype="<i4",
            count=codes.size,
        )
        indexes = class_indexes[inverse]
        # Both triangles belonging to a terrain cell share its landuse.
        yield np.repeat(indexes, 2)


def _write_record(handle, code, chunks, count):
    # FDS reads Fortran unformatted sequential records: a little-endian byte
    # count precedes and follows each payload. Chunking bounds Python memory use.
    dtype = np.dtype("<i4" if code == "i" else "<f8")
    byte_count = count * dtype.itemsize
    handle.write(struct.pack("<i", byte_count))
    written = 0
    for chunk in chunks:
        array = np.asarray(chunk, dtype=dtype).reshape(-1)
        handle.write(array.tobytes(order="C"))
        written += int(array.size)
    if written != count:
        raise ValueError(
            "Binary record expected {} values, got {}.".format(count, written)
        )
    handle.write(struct.pack("<i", byte_count))
