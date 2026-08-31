"""Tests for the QGIS-independent FDS and Smokeview result readers."""

import struct

import numpy as np
import pytest

from source.fds_results import (
    FdsResultError,
    read_boundary,
    read_fds_reference,
    read_geometry_boundary,
    read_geometry_topology,
    read_slice,
    read_smokeview_manifest,
)


def _record(payload):
    """Wrap bytes as one little-endian Fortran unformatted record."""
    return struct.pack("<i", len(payload)) + payload + struct.pack("<i", len(payload))


def _text(value):
    return _record(value.encode("ascii").ljust(30))


def _write_records(filepath, records):
    filepath.write_bytes(b"".join(records))


def test_read_fds_reference_uses_active_misc_values(tmp_path):
    filepath = tmp_path / "case.fds"
    filepath.write_text(
        "! &MISC ORIGIN_LAT=0, ORIGIN_LON=0, NORTH_BEARING=0 /\n"
        "&MISC ORIGIN_LAT=46.25,\n"
        "      ORIGIN_LON=6.125D0, NORTH_BEARING=-0.42 /\n",
        encoding="utf-8",
    )

    reference = read_fds_reference(filepath)

    assert reference.latitude == 46.25
    assert reference.longitude == 6.125
    assert reference.north_bearing == -0.42


def test_read_fds_reference_requires_georeferencing(tmp_path):
    filepath = tmp_path / "case.fds"
    filepath.write_text("&MISC LEVEL_SET_MODE=1 /\n", encoding="utf-8")

    with pytest.raises(FdsResultError, match="ORIGIN_LAT"):
        read_fds_reference(filepath)


def test_read_smokeview_manifest_resolves_agl_and_geom_forward_reference(tmp_path):
    filepath = tmp_path / "case.smv"
    filepath.write_text(
        "GRID MESH_0000001\n"
        " 1 1 1 0 0 0\n"
        "TRNX\n 0\n 0 -5.0\n 1 5.0\n"
        "TRNY\n 0\n 0 -10.0\n 1 10.0\n"
        "TRNZ\n 0\n 0 0.0\n 1 20.0\n"
        "SLCT 1 2.0000 & 0 1 0 1 0 0 ! 1\n"
        " case_1_1.sf\n TEMPERATURE\n temp\n C\n"
        "BNDE 1 1\n case_1_1.be\n -\n FIRE ARRIVAL TIME\n t_a\n s\n"
        "CGEOM 0\n case_1.gcf\n",
        encoding="utf-8",
    )

    manifest = read_smokeview_manifest(filepath)

    assert manifest.meshes[1].x.tolist() == [-5.0, 5.0]
    assert manifest.meshes[1].y.tolist() == [-10.0, 10.0]
    assert manifest.slices[0].agl == 2.0
    assert manifest.slices[0].bounds == (0, 1, 0, 1, 0, 0)
    assert manifest.boundaries[0].topology_filename == "case_1.gcf"


def test_read_slice_keeps_only_complete_frames(tmp_path):
    filepath = tmp_path / "case.sf"
    complete = [
        _text("TEMPERATURE"),
        _text("temp"),
        _text("C"),
        _record(struct.pack("<6i", 0, 1, 0, 1, 0, 0)),
        _record(struct.pack("<f", 0.0)),
        _record(struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)),
    ]
    # Simulate FDS being interrupted while writing the second values record.
    incomplete = _record(struct.pack("<f", 1.0)) + struct.pack("<i", 16) + b"\0\0"
    filepath.write_bytes(b"".join(complete) + incomplete)

    result = read_slice(filepath)

    assert result.times.tolist() == [0.0]
    assert result.values.tolist() == [[1.0, 2.0, 3.0, 4.0]]
    assert result.incomplete_tail


def test_read_structured_boundary_patches(tmp_path):
    filepath = tmp_path / "case.bf"
    _write_records(
        filepath,
        [
            _text("LS SPREAD RATE"),
            _text("r"),
            _text("m/s"),
            _record(struct.pack("<i", 1)),
            _record(struct.pack("<9i", 0, 1, 0, 1, 0, 0, 3, 0, 1)),
            _record(struct.pack("<f", 2.0)),
            _record(struct.pack("<4f", 0.1, 0.2, 0.3, 0.4)),
        ],
    )

    result = read_boundary(filepath)

    assert result.quantity == "LS SPREAD RATE"
    assert result.patches[0].bounds == (0, 1, 0, 1, 0, 0)
    assert result.times.tolist() == [2.0]
    assert np.allclose(result.values[0][0], [0.1, 0.2, 0.3, 0.4])


def test_read_geometry_topology_and_face_values(tmp_path):
    topology_path = tmp_path / "case.gcf"
    vertices = np.asarray(
        [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 1.0]],
        dtype="<f4",
    )
    faces = np.asarray([[1, 2, 3]], dtype="<i4")
    _write_records(
        topology_path,
        [
            _record(struct.pack("<i", 1)),
            _record(struct.pack("<i", 2)),
            _record(struct.pack("<3i", 0, 0, 1)),
            _record(struct.pack("<f", 0.0)),
            _record(struct.pack("<3i", 3, 1, 0)),
            _record(vertices.tobytes()),
            _record(faces.tobytes()),
        ],
    )
    values_path = tmp_path / "case.be"
    _write_records(
        values_path,
        [
            _record(struct.pack("<i", 1)),
            _record(struct.pack("<i", 2)),
            _record(struct.pack("<f", 5.0)),
            _record(struct.pack("<4i", 0, 0, 0, 1)),
            _record(struct.pack("<f", 12.5)),
        ],
    )

    topology = read_geometry_topology(topology_path)
    result = read_geometry_boundary(values_path, expected_faces=1)

    assert topology.vertices.tolist() == vertices.tolist()
    assert topology.faces.tolist() == [[0, 1, 2]]
    assert result.times.tolist() == [5.0]
    assert result.values.tolist() == [[12.5]]
