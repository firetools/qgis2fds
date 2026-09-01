"""Build and persist georeferenced QGIS mesh layers from FDS result arrays."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
import re

import numpy as np

from qgis.core import (
    QgsMesh,
    QgsMeshDataBlock,
    QgsMeshDatasetGroupMetadata,
    QgsMeshLayer,
    QgsProcessingException,
    QgsProviderRegistry,
)


@dataclass(frozen=True)
class FrameLayout:
    """One mesh frame in FDS coordinates and source-to-output spans."""

    vertices: np.ndarray
    faces: tuple
    data_on_faces: bool
    # Spans map mesh IDs (and optionally patch IDs) to the output value array.
    spans: dict


@dataclass(frozen=True)
class TemporalGroup:
    """One scalar or horizontal-vector temporal dataset group."""

    name: str
    unit: str
    times: np.ndarray
    values: tuple
    vector: bool = False


# FDS output times are relative simulation seconds, not calendar times.  A
# stable UTC epoch gives UGRID a valid CF reference without inventing a case
# date; QGIS still presents the original relative elapsed times.
TEMPORAL_REFERENCE = datetime(1970, 1, 1, tzinfo=timezone.utc)


def slice_frame_layout(entries, meshes, height):
    """Create a horizontal quad frame for one AGL height."""
    vertices = []
    faces = []
    spans = {}
    for entry in sorted(entries, key=lambda item: item.mesh_id):
        grid = meshes[entry.mesh_id]
        i1, i2, j1, j2, _k1, _k2 = entry.bounds
        if not (0 <= i1 <= i2 < len(grid.x) and 0 <= j1 <= j2 < len(grid.y)):
            raise QgsProcessingException(
                "SLCT bounds fall outside FDS mesh {}.".format(entry.mesh_id)
            )
        width = i2 - i1 + 1
        height_count = j2 - j1 + 1
        start = len(vertices)
        for j in range(j1, j2 + 1):
            for i in range(i1, i2 + 1):
                vertices.append((grid.x[i], grid.y[j], float(height)))
        spans[entry.mesh_id] = (start, width * height_count, entry.bounds)
        for j in range(height_count - 1):
            row = start + j * width
            for i in range(width - 1):
                lower = row + i
                faces.append((lower, lower + 1, lower + width + 1, lower + width))
    if not faces:
        raise QgsProcessingException("The AGL slice does not form any mesh faces.")
    return FrameLayout(
        np.asarray(vertices, dtype=np.float64), tuple(faces), False, spans
    )


def geometry_frame_layout(topologies):
    """Combine per-mesh GCF triangles into one face-centered frame."""
    vertices = []
    faces = []
    spans = {}
    for mesh_id in sorted(topologies):
        topology = topologies[mesh_id]
        vertex_offset = len(vertices)
        face_start = len(faces)
        vertices.extend(topology.vertices.tolist())
        faces.extend(
            tuple(int(index) + vertex_offset for index in face)
            for face in topology.faces
        )
        spans[mesh_id] = (face_start, len(topology.faces))
    if not faces:
        raise QgsProcessingException("The GCF files contain no terrain faces.")
    return FrameLayout(
        np.asarray(vertices, dtype=np.float64), tuple(faces), True, spans
    )


def structured_boundary_frame_layout(series_by_mesh, meshes):
    """Build quad faces for horizontal patches in structured BF files.

    Vertical boundary patches collapse to lines in the QGIS map plane, so they
    are intentionally omitted.  The wildfire quantities emitted by qgis2fds are
    attached to horizontal terrain/floor patches.
    """
    vertices = []
    faces = []
    spans = {}
    for mesh_id in sorted(series_by_mesh):
        grid = meshes[mesh_id]
        series = series_by_mesh[mesh_id]
        for patch_index, patch in enumerate(series.patches):
            i1, i2, j1, j2, k1, k2 = patch.bounds
            if k1 != k2:
                continue
            if not (
                0 <= i1 <= i2 < len(grid.x)
                and 0 <= j1 <= j2 < len(grid.y)
                and 0 <= k1 < len(grid.z)
            ):
                raise QgsProcessingException(
                    "BNDF patch bounds fall outside FDS mesh {}.".format(mesh_id)
                )
            width = i2 - i1 + 1
            height = j2 - j1 + 1
            start = len(vertices)
            for j in range(j1, j2 + 1):
                for i in range(i1, i2 + 1):
                    vertices.append((grid.x[i], grid.y[j], grid.z[k1]))
            spans[(mesh_id, patch_index)] = (start, width * height)
            for j in range(height - 1):
                row = start + j * width
                for i in range(width - 1):
                    lower = row + i
                    faces.append(
                        (lower, lower + 1, lower + width + 1, lower + width)
                    )
    if not faces:
        raise QgsProcessingException(
            "The structured boundary files contain no horizontal patches."
        )
    return FrameLayout(
        np.asarray(vertices, dtype=np.float64), tuple(faces), False, spans
    )


def transform_frame(layout, origin_easting, origin_northing, rotation_degrees):
    """Translate and rotate an FDS frame into the selected local UTM CRS."""
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    transformed = layout.vertices.copy()
    x_values = transformed[:, 0].copy()
    y_values = transformed[:, 1].copy()
    transformed[:, 0] = origin_easting + x_values * cosine - y_values * sine
    transformed[:, 1] = origin_northing + x_values * sine + y_values * cosine
    return FrameLayout(
        transformed, layout.faces, layout.data_on_faces, layout.spans
    )


def rotate_vectors(values_x, values_y, rotation_degrees):
    """Rotate horizontal FDS vector components into UTM east/north components."""
    angle = math.radians(rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    x_values = np.asarray(values_x, dtype=np.float64)
    y_values = np.asarray(values_y, dtype=np.float64)
    return (
        x_values * cosine - y_values * sine,
        x_values * sine + y_values * cosine,
    )


def write_mesh_layers(filepath, layer_name, crs, layout, groups):
    """Write one standalone temporal UGRID mesh layer per dataset group.

    The 2DM file is a common intermediate frame.  MDAL copies that frame and
    one temporal group into each UGRID file, so every returned layer is
    self-contained and can be reopened without attaching companion datasets.
    """
    # 2DM is a convenient intermediate writer but cannot store a CRS.  Convert
    # its populated frame to a temporary UGRID through the QGIS provider API;
    # that API accepts the CRS explicitly, and MDAL then carries it into every
    # final dataset file.
    ugrid_frame = os.path.splitext(filepath)[0] + "_frame.nc"
    try:
        _write_2dm(filepath, layer_name, layout.vertices, layout.faces)
        source_layer = QgsMeshLayer(filepath, layer_name, "mdal")
        if not source_layer.isValid():
            raise QgsProcessingException(
                "QGIS could not load generated mesh frame: {}".format(filepath)
            )
        mesh = QgsMesh()
        source_layer.dataProvider().populateMesh(mesh)
        metadata = QgsProviderRegistry.instance().providerMetadata("mdal")
        if metadata is None or not metadata.createMeshData(
            mesh, ugrid_frame, "Ugrid", crs
        ):
            raise QgsProcessingException(
                "QGIS could not create a georeferenced UGRID frame."
            )
        frame_layer = QgsMeshLayer(ugrid_frame, layer_name, "mdal")
        if not frame_layer.isValid() or not frame_layer.crs().isValid():
            raise QgsProcessingException(
                "QGIS could not reload the georeferenced UGRID frame."
            )

        layers = []
        dataset_paths = []
        for group_index, group in enumerate(groups, start=1):
            dataset_path = os.path.join(
                os.path.dirname(filepath),
                "{}_{}.nc".format(
                    os.path.splitext(os.path.basename(filepath))[0],
                    _slug(group.name, group_index),
                ),
            )
            _persist_group(
                frame_layer, dataset_path, layout, group, driver="Ugrid"
            )
            dataset_layer = QgsMeshLayer(
                dataset_path,
                "{} — {}".format(layer_name, group.name),
                "mdal",
            )
            if not dataset_layer.isValid() or not dataset_layer.crs().isValid():
                raise QgsProcessingException(
                    "QGIS could not reload generated georeferenced UGRID mesh: "
                    "{}".format(dataset_path)
                )
            _configure_dataset_layer(dataset_layer, group)
            layers.append(dataset_layer)
            dataset_paths.append(dataset_path)
        return tuple(layers), tuple(dataset_paths)
    finally:
        for intermediate in (filepath, ugrid_frame):
            try:
                os.unlink(intermediate)
            except FileNotFoundError:
                pass


def _persist_group(layer, filepath, layout, group, driver):
    expected = len(layout.faces) if layout.data_on_faces else len(layout.vertices)
    data_type = (
        QgsMeshDatasetGroupMetadata.DataType.DataOnFaces
        if layout.data_on_faces
        else QgsMeshDatasetGroupMetadata.DataType.DataOnVertices
    )
    finite_values = []
    blocks = []
    block_type = (
        QgsMeshDataBlock.DataType.Vector2DDouble
        if group.vector
        else QgsMeshDataBlock.DataType.ScalarDouble
    )
    for values in group.values:
        array = np.asarray(values, dtype=np.float64)
        required_shape = (expected, 2) if group.vector else (expected,)
        if array.shape != required_shape:
            raise QgsProcessingException(
                "Dataset '{}' has shape {}; expected {}.".format(
                    group.name, array.shape, required_shape
                )
            )
        magnitudes = np.linalg.norm(array, axis=1) if group.vector else array
        finite_values.append(magnitudes[np.isfinite(magnitudes)])
        block = QgsMeshDataBlock(block_type, expected)
        block.setValues(array.reshape(-1).tolist())
        block.setValid(True)
        blocks.append(block)

    finite = np.concatenate(finite_values) if finite_values else np.asarray([])
    minimum = float(np.min(finite)) if finite.size else math.nan
    maximum = float(np.max(finite)) if finite.size else math.nan
    metadata = QgsMeshDatasetGroupMetadata(
        group.name,
        filepath,
        not group.vector,
        data_type,
        minimum,
        maximum,
        0,
        TEMPORAL_REFERENCE,
        True,
        {"units": group.unit, "TIMEUNITS": "hours"},
    )
    times_hours = (np.asarray(group.times, dtype=np.float64) / 3600.0).tolist()
    failed = layer.dataProvider().persistDatasetGroup(
        filepath, driver, metadata, blocks, [], times_hours
    )
    # This older provider method follows MDAL's convention and returns True on
    # failure (the inverse of most QGIS methods).
    if failed:
        raise QgsProcessingException(
            "QGIS could not persist dataset '{}' to {}.".format(group.name, filepath)
        )


def _configure_dataset_layer(layer, group):
    """Activate the imported group and initialize its temporal properties."""
    provider = layer.dataProvider()
    group_index = next(
        (
            index
            for index in range(provider.datasetGroupCount())
            if provider.datasetGroupMetadata(index).name() == group.name
        ),
        -1,
    )
    if group_index < 0:
        raise QgsProcessingException(
            "Generated mesh does not contain dataset '{}'.".format(group.name)
        )

    renderer = layer.rendererSettings()
    if group.vector:
        renderer.setActiveScalarDatasetGroup(-1)
        renderer.setActiveVectorDatasetGroup(group_index)
    else:
        renderer.setActiveScalarDatasetGroup(group_index)
        renderer.setActiveVectorDatasetGroup(-1)
    layer.setRendererSettings(renderer)

    temporal = layer.temporalProperties()
    temporal.setDefaultsFromDataProviderTemporalCapabilities(
        provider.temporalCapabilities()
    )
    temporal.setIsActive(True)
    layer.triggerRepaint()


def _write_2dm(filepath, name, vertices, faces):
    temporary = filepath + ".tmp"
    try:
        with open(temporary, "w", encoding="ascii", newline="\n") as handle:
            handle.write("MESH2D\n")
            handle.write("MESHNAME \"{}\"\n".format(name.replace('"', "'")))
            for index, (x_value, y_value, z_value) in enumerate(vertices, start=1):
                handle.write(
                    "ND {} {:.12g} {:.12g} {:.12g}\n".format(
                        index, x_value, y_value, z_value
                    )
                )
            for index, face in enumerate(faces, start=1):
                if len(face) == 3:
                    record = "E3T"
                elif len(face) == 4:
                    record = "E4Q"
                else:
                    raise QgsProcessingException(
                        "2DM output supports only triangular and quadrilateral faces."
                    )
                nodes = " ".join(str(node + 1) for node in face)
                handle.write("{} {} {} 1\n".format(record, index, nodes))
        os.replace(temporary, filepath)
    except OSError as error:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise QgsProcessingException(
            "Cannot write mesh frame '{}': {}".format(filepath, error)
        )


def _slug(value, fallback):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "dataset_{}".format(fallback)
