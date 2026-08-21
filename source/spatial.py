"""QGIS-specific coordinate, raster, fire, and texture operations."""

import math
import os

import numpy as np
import processing
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsMapRendererSequentialJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingException,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

from .model import SpatialGrid, TerrainData


NODATA = -9999.0
MAX_TEXTURE_PIXELS = 100_000_000
MAX_TEXTURE_DIMENSION = 16_384
RASTER_NUMPY_DTYPES = {
    Qgis.DataType.Byte: np.dtype("u1"),
    Qgis.DataType.Int8: np.dtype("i1"),
    Qgis.DataType.UInt16: np.dtype("=u2"),
    Qgis.DataType.Int16: np.dtype("=i2"),
    Qgis.DataType.UInt32: np.dtype("=u4"),
    Qgis.DataType.Int32: np.dtype("=i4"),
    Qgis.DataType.Float32: np.dtype("=f4"),
    Qgis.DataType.Float64: np.dtype("=f8"),
}


def prepare_grid(extent_layer, origin, project_crs, pixel_size):
    """Choose a local UTM CRS and align the extent to complete pixels."""
    if not extent_layer.crs().isValid():
        raise QgsProcessingException("The domain extent layer has no valid CRS.")
    if extent_layer.extent().isEmpty():
        raise QgsProcessingException("The domain extent layer is empty.")

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    extent_to_wgs84 = QgsCoordinateTransform(
        extent_layer.crs(), wgs84, QgsProject.instance()
    )
    wgs84_extent = extent_to_wgs84.transformBoundingBox(extent_layer.extent())

    if origin is None:
        # The extent centroid preserves the historical default when a project has
        # no explicitly stored FDS origin.
        wgs84_origin = wgs84_extent.center()
    else:
        origin_to_wgs84 = QgsCoordinateTransform(
            project_crs, wgs84, QgsProject.instance()
        )
        wgs84_origin = origin_to_wgs84.transform(QgsPointXY(origin))

    # A local UTM CRS gives raster operations and FDS a metric coordinate system
    # selected from the requested origin instead of the layer's native CRS.
    utm_crs = _utm_crs(wgs84_origin.x(), wgs84_origin.y())
    extent_to_utm = QgsCoordinateTransform(
        extent_layer.crs(), utm_crs, QgsProject.instance()
    )
    utm_extent = extent_to_utm.transformBoundingBox(extent_layer.extent())
    origin_to_utm = QgsCoordinateTransform(wgs84, utm_crs, QgsProject.instance())
    utm_origin = origin_to_utm.transform(wgs84_origin)

    # Expand symmetrically to complete pixels. At least two cells per axis keeps
    # terrain triangulation and mesh generation meaningful.
    columns = max(2, int(math.ceil(utm_extent.width() / pixel_size)))
    rows = max(2, int(math.ceil(utm_extent.height() / pixel_size)))
    width = columns * pixel_size
    height = rows * pixel_size
    center = utm_extent.center()

    grid = SpatialGrid(
        crs_authid=utm_crs.authid(),
        crs_description=utm_crs.description(),
        x_min=center.x() - width / 2.0,
        y_min=center.y() - height / 2.0,
        pixel_size=pixel_size,
        columns=columns,
        rows=rows,
        origin_x=utm_origin.x(),
        origin_y=utm_origin.y(),
        longitude=wgs84_origin.x(),
        latitude=wgs84_origin.y(),
    )
    return grid, utm_crs


def sample_terrain(
    dem_layer,
    landuse_layer,
    grid,
    utm_crs,
    context,
    feedback,
):
    """Warp the source rasters once, then read aligned cell values."""
    _validate_raster(dem_layer, "DEM")
    # Elevation is continuous and uses bilinear resampling. Categorical landuse
    # below uses nearest-neighbor so class identifiers are never interpolated.
    dem = _warp_raster(
        dem_layer, grid, utm_crs, 1, "qgis2fds DEM", context, feedback
    )
    dem_values = _read_block(dem, grid, required=True)

    if landuse_layer is None:
        # Code zero resolves to INERT in the built-in terrain-only catalog.
        landuse_values = np.zeros((grid.rows, grid.columns), dtype="<i8")
    else:
        _validate_raster(landuse_layer, "Landuse")
        landuse = _warp_raster(
            landuse_layer,
            grid,
            utm_crs,
            0,
            "qgis2fds landuse",
            context,
            feedback,
        )
        raw_landuse = _read_block(landuse, grid, required=False)
        # Missing categorical cells use code zero; rint matches the historical
        # conversion of raster samples to the nearest integer class identifier.
        landuse_values = np.rint(
            np.nan_to_num(raw_landuse, nan=0.0, posinf=0.0, neginf=0.0)
        ).astype("<i8")

    return TerrainData(grid, dem_values, landuse_values)


def apply_fire_layer(
    terrain,
    fire_layer,
    utm_crs,
    outside_default,
    inside_default,
    feedback,
):
    """Apply buffered and interior fire surface codes directly to grid cells."""
    if fire_layer is None:
        return
    if not fire_layer.crs().isValid():
        raise QgsProcessingException("The fire layer has no valid CRS.")

    transform = QgsCoordinateTransform(
        fire_layer.crs(), utm_crs, QgsProject.instance()
    )
    inside_index = fire_layer.fields().indexOf("bc_in")
    outside_index = fire_layer.fields().indexOf("bc_out")
    records = []

    for feature in fire_layer.getFeatures():
        if feedback.isCanceled():
            raise QgsProcessingException("Export canceled.")
        geometry = QgsGeometry(feature.geometry())
        if geometry.isEmpty():
            continue
        try:
            geometry.transform(transform)
        except Exception as error:
            raise QgsProcessingException(
                "Cannot transform fire feature {}: {}".format(feature.id(), error)
            )
        if not geometry.isGeosValid():
            geometry = geometry.makeValid()
        outside_code = _feature_code(feature, outside_index, outside_default)
        inside_code = _feature_code(feature, inside_index, inside_default)
        records.append(
            (
                geometry,
                # This one-cell buffer implements the historical bc_out/bc_in
                # perimeter convention used by existing fire layers.
                geometry.buffer(terrain.grid.pixel_size, 8),
                inside_code,
                outside_code,
            )
        )

    # Rings are applied first so every actual ignition polygon takes precedence.
    for _, buffered, _, outside_code in records:
        _paint_geometry(terrain, buffered, outside_code, feedback)
    for geometry, _, inside_code, _ in records:
        _paint_geometry(terrain, geometry, inside_code, feedback)


def render_texture(grid, utm_crs, filepath, texture_pixel_size, feedback):
    """Render checked project layers into a Smokeview terrain texture."""
    width = max(1, int(math.ceil(grid.width / texture_pixel_size)))
    height = max(1, int(math.ceil(grid.height / texture_pixel_size)))
    # Refuse images likely to exceed renderer/GPU limits or consume excessive RAM.
    if (
        width > MAX_TEXTURE_DIMENSION
        or height > MAX_TEXTURE_DIMENSION
        or width * height > MAX_TEXTURE_PIXELS
    ):
        feedback.pushWarning(
            "Texture skipped: requested image is {} x {} pixels.".format(width, height)
        )
        return None

    project = QgsProject.instance()
    try:
        # Only visible project layers belong in the Smokeview terrain texture.
        layers = project.layerTreeRoot().checkedLayers()
    except AttributeError:
        # Retain a fallback for QGIS builds without checkedLayers().
        layers = list(project.mapLayers().values())
    layers = [layer for layer in layers if layer.isValid()]
    if not layers:
        feedback.pushWarning("Texture skipped: the project has no visible layers.")
        return None

    settings = QgsMapSettings()
    settings.setDestinationCrs(utm_crs)
    settings.setExtent(_grid_rectangle(grid))
    settings.setOutputSize(QSize(width, height))
    settings.setBackgroundColor(QColor(255, 255, 255))
    # Render order from QgsMapSettings is bottom to top.
    settings.setLayers(list(reversed(layers)))

    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if image.isNull() or not image.save(filepath, "PNG"):
        feedback.pushWarning("Texture rendering failed; no terrain image was written.")
        return None
    return filepath


def _utm_crs(longitude, latitude):
    if not -180.0 <= longitude <= 180.0:
        raise QgsProcessingException("Longitude is outside the valid range.")
    if not -80.0 <= latitude <= 84.0:
        raise QgsProcessingException(
            "The selected domain is outside the supported UTM latitude range."
        )
    zone = min(60, int((longitude + 180.0) // 6.0) + 1)
    # Standard UTM exceptions for western Norway and Svalbard.
    if 56.0 <= latitude < 64.0 and 3.0 <= longitude < 12.0:
        zone = 32
    elif 72.0 <= latitude <= 84.0 and longitude >= 0.0:
        if longitude < 9.0:
            zone = 31
        elif longitude < 21.0:
            zone = 33
        elif longitude < 33.0:
            zone = 35
        elif longitude < 42.0:
            zone = 37
    epsg = (32600 if latitude >= 0.0 else 32700) + zone
    crs = QgsCoordinateReferenceSystem("EPSG:{}".format(epsg))
    if not crs.isValid():
        raise QgsProcessingException("Cannot create the local UTM CRS.")
    return crs


def _validate_raster(layer, label):
    if layer is None or not layer.isValid():
        raise QgsProcessingException("{} layer is not valid.".format(label))
    if not layer.crs().isValid():
        raise QgsProcessingException("{} layer has no valid CRS.".format(label))


def _warp_raster(layer, grid, utm_crs, resampling, name, context, feedback):
    # Warping once into the common grid is faster and more reproducible than
    # transforming and sampling each terrain cell independently.
    parameters = {
        "INPUT": layer,
        "SOURCE_CRS": layer.crs(),
        "TARGET_CRS": utm_crs,
        "RESAMPLING": resampling,
        "NODATA": NODATA,
        "TARGET_RESOLUTION": grid.pixel_size,
        "OPTIONS": "",
        "DATA_TYPE": 0,
        "TARGET_EXTENT": _grid_rectangle(grid),
        "TARGET_EXTENT_CRS": utm_crs,
        "MULTITHREADING": True,
        "EXTRA": "",
        "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
    }
    try:
        result = processing.run(
            "gdal:warpreproject",
            parameters,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
    except Exception as error:
        raise QgsProcessingException(
            "Cannot prepare raster '{}': {}".format(layer.name(), error)
        )

    output = result["OUTPUT"]
    if isinstance(output, QgsRasterLayer):
        warped = output
    else:
        # Child algorithms may return either a context layer ID or a file path.
        warped = context.getMapLayer(output)
        if warped is None:
            warped = QgsRasterLayer(str(output), name)
    if not warped.isValid():
        raise QgsProcessingException(
            "Warped raster '{}' is not valid.".format(layer.name())
        )
    return warped


def _read_block(layer, grid, required):
    block = layer.dataProvider().block(
        1, _grid_rectangle(grid), grid.columns, grid.rows
    )
    if block is None or not block.isValid():
        raise QgsProcessingException("Cannot read the prepared raster.")

    dtype = RASTER_NUMPY_DTYPES.get(block.dataType())
    if dtype is None:
        raise QgsProcessingException(
            "Raster data type {} is not supported.".format(block.dataType())
        )

    # QGIS 4 exposes the contiguous raster payload as QByteArray. NumPy can read
    # it without per-cell Python calls; astype below makes the owned float copy.
    buffer = block.data()
    raw = np.frombuffer(buffer, dtype=dtype)
    expected_size = grid.rows * grid.columns
    if raw.size != expected_size:
        raise QgsProcessingException(
            "Raster block contains {} values; expected {}.".format(
                raw.size, expected_size
            )
        )
    # QgsRasterBlock rows run north to south; the model runs south to north.
    values = raw.reshape((grid.rows, grid.columns))[::-1].astype("<f8")

    missing = ~np.isfinite(values)
    if block.hasNoDataValue():
        nodata = float(block.noDataValue())
        if np.isfinite(nodata):
            missing |= values == nodata
    elif block.hasNoData():
        # Some providers use a separate no-data bitmap instead of a sentinel.
        bitmap = np.fromiter(
            (
                block.isNoData(row, column)
                for row in range(grid.rows)
                for column in range(grid.columns)
            ),
            dtype=bool,
            count=expected_size,
        ).reshape((grid.rows, grid.columns))
        missing |= bitmap[::-1]

    if required and np.any(missing):
        model_row, column = np.argwhere(missing)[0]
        raise QgsProcessingException(
            "DEM has no elevation at terrain cell ({}, {}).".format(
                int(column), int(model_row)
            )
        )
    values[missing] = np.nan
    return values


def _feature_code(feature, field_index, default):
    if field_index < 0:
        return default
    value = feature[field_index]
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _paint_geometry(terrain, geometry, code, feedback):
    grid = terrain.grid
    bounds = geometry.boundingBox()
    # Restrict point-in-polygon tests to cells touched by the feature bounds.
    first_column = max(
        0, int(math.floor((bounds.xMinimum() - grid.x_min) / grid.pixel_size))
    )
    last_column = min(
        grid.columns - 1,
        int(math.floor((bounds.xMaximum() - grid.x_min) / grid.pixel_size)),
    )
    first_row = max(
        0, int(math.floor((bounds.yMinimum() - grid.y_min) / grid.pixel_size))
    )
    last_row = min(
        grid.rows - 1,
        int(math.floor((bounds.yMaximum() - grid.y_min) / grid.pixel_size)),
    )
    if last_column < first_column or last_row < first_row:
        return
    for row in range(first_row, last_row + 1):
        if feedback.isCanceled():
            raise QgsProcessingException("Export canceled.")
        y = grid.y_center(row)
        for column in range(first_column, last_column + 1):
            # Cell-center classification matches the cell-centered raster model.
            point = QgsPointXY(grid.x_center(column), y)
            if geometry.contains(point):
                terrain.landuse[row][column] = code


def _grid_rectangle(grid):
    return QgsRectangle(grid.x_min, grid.y_min, grid.x_max, grid.y_max)
