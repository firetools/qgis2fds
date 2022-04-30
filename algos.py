import processing, math
from qgis.core import (
    QgsProcessing,
    QgsRectangle,
    QgsProcessingException,
    QgsRasterPipe,
    QgsRasterFileWriter,
    QgsRasterLayer,
    QgsCoordinateTransform,
    QgsProject,
)


def get_grid_layer(
    context,
    feedback,
    text,
    crs,
    extent,
    xres,
    yres,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Create grid of points in a new layer."""
    feedback.setProgressText(text)
    alg_params = {
        "CRS": crs,
        "EXTENT": extent,
        "HOVERLAY": 0,
        "HSPACING": xres,
        "TYPE": 0,  # Points
        "VOVERLAY": 0,
        "VSPACING": yres,
        "OUTPUT": output,
    }
    feedback.pushInfo("Create grid layer...")
    return processing.run(
        "native:creategrid",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def get_pixel_aligned_extent(
    context,
    feedback,
    text,
    raster_layer,
    extent,
    extent_crs,
    larger=True,
) -> QgsRectangle:
    """Return extent aligned to raster pixels in raster crs."""
    feedback.setProgressText(text)

    # Transform extent to raster crs
    tr = QgsCoordinateTransform(extent_crs, raster_layer.crs(), QgsProject.instance())
    raster_extent = tr.transformBoundingBox(extent)

    # Get raster_layer resolution
    raster_layer_xres = raster_layer.rasterUnitsPerPixelX()
    raster_layer_yres = raster_layer.rasterUnitsPerPixelY()

    # Get top left extent corner coordinates,
    # because raster grid starts from top left corner of raster_layer extent
    raster_layer_x0, raster_layer_y1 = (
        raster_layer.extent().xMinimum(),
        raster_layer.extent().yMaximum(),
    )

    # Aligning raster_extent top left corner to raster_layer resolution,
    # never reduce its size
    x0, y0, x1, y1 = (
        raster_extent.xMinimum(),
        raster_extent.yMinimum(),
        raster_extent.xMaximum(),
        raster_extent.yMaximum(),
    )
    x0 = (
        raster_layer_x0  # start at lower raster bound # FIXME finqui finqui finqui
        + int((x0 - raster_layer_x0) / raster_layer_xres) * raster_layer_xres  # align
        - raster_layer_xres / 2.0  # to previous raster pixel center
        - raster_layer_xres  # to previous raster pixel center (ghost)
    )
    y1 = (
        raster_layer_y1  # start upper
        - int((raster_layer_y1 - y1) / raster_layer_yres) * raster_layer_yres  # align
        + raster_layer_yres / 2.0  # to following raster pixel center
        + raster_layer_yres  # to following raster pixel center (ghost)
    )
    x1 = (
        x0  # start lower
        + (
            math.ceil((x1 - x0) / raster_layer_xres) + 0.000001
        )  # prevent rounding errors
        * raster_layer_xres  # ceil multiple of xres
        + raster_layer_xres  # to following raster pixel center (ghost)
    )
    y0 = (
        y1  # start upper
        - (
            math.ceil((y1 - y0) / raster_layer_yres) + 0.000001
        )  # prevent rounding errors
        * raster_layer_yres  # ceil multiple of yres
        - raster_layer_yres  # to previous raster pixel center (ghost)
    )
    return QgsRectangle(x0, y0, x1, y1)


def get_raster_sampling_grid_layer(
    context,
    feedback,
    text,
    raster_layer,
    extent,
    extent_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Create new raster layer sampling grid layer on desired extent."""

    # This algo replaces the qgis "raster_to_points" one,
    # that has no extent

    raster_extent = get_pixel_aligned_extent(
        context,
        feedback,
        text="Align",
        raster_layer=raster_layer,
        extent=extent,
        extent_crs=extent_crs,
    )

    # Check raster_layer contains updated raster_extent
    if not raster_layer.extent().contains(raster_extent):
        feedback.reportError("Grid extent is larger than raster layer extent.")

    # Calc and check number of dem sampling point
    raster_layer_xres = raster_layer.rasterUnitsPerPixelX()
    raster_layer_yres = raster_layer.rasterUnitsPerPixelY()
    x0, y0, x1, y1 = (
        raster_extent.xMinimum(),
        raster_extent.yMinimum(),
        raster_extent.xMaximum(),
        raster_extent.yMaximum(),
    )
    raster_sampling_xn = int((x1 - x0) / raster_layer_xres) + 1
    raster_sampling_yn = int((y1 - y0) / raster_layer_yres) + 1
    if raster_sampling_xn < 3:
        raise QgsProcessingException(
            f"Too few sampling points <{raster_sampling_xn}> along x axis, cannot proceed."
        )
    if raster_sampling_yn < 3:
        raise QgsProcessingException(
            f"Too few sampling points <{raster_sampling_yn}> along y axis, cannot proceed."
        )

    # Create grid
    return get_grid_layer(
        context,
        feedback,
        text=text,
        crs=raster_layer.crs(),
        extent=raster_extent,
        xres=raster_layer_xres,
        yres=raster_layer_yres,
        output=output,
    )


def set_grid_layer_z(
    context,
    feedback,
    text,
    grid_layer,
    raster_layer,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Set point grid elevation from raster layer first band."""
    # It works when grid and raster share the same crs
    feedback.setProgressText(text)
    alg_params = {
        "BAND": 1,
        "INPUT": grid_layer,
        "NODATA": -999.0,
        "RASTER": raster_layer,
        "SCALE": 1,
        "OUTPUT": output,
    }
    return processing.run(
        "native:setzfromraster",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def set_grid_layer_value(
    context,
    feedback,
    text,
    grid_layer,
    raster_layer,
    column_prefix,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Set point grid value from raster layer bands."""
    feedback.setProgressText(text)
    alg_params = {
        "COLUMN_PREFIX": column_prefix,
        "INPUT": grid_layer,
        "RASTERCOPY": raster_layer,
        "OUTPUT": output,
    }
    return processing.run(
        "qgis:rastersampling",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def reproject_raster_layer(
    context,
    feedback,
    text,
    raster_layer,
    destination_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Reproject grid layer to a new crs."""
    feedback.setProgressText(text)
    alg_params = {
        "INPUT": raster_layer,
        "TARGET_CRS": destination_crs,
        "RESAMPLING": 0,
        "NODATA": None,
        "TARGET_RESOLUTION": None,
        "OPTIONS": "",
        "DATA_TYPE": 0,
        "TARGET_EXTENT": None,
        "TARGET_EXTENT_CRS": None,
        "MULTITHREADING": False,
        "EXTRA": "",
        "OUTPUT": output,
    }
    return processing.run(
        "gdal:warpreproject",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def reproject_vector_layer(
    context,
    feedback,
    text,
    vector_layer,
    destination_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Reproject vector layer to a new crs."""
    feedback.setProgressText(text)
    alg_params = {
        "INPUT": vector_layer,
        "TARGET_CRS": destination_crs,
        "OUTPUT": output,
    }
    return processing.run(
        "native:reprojectlayer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def create_buffer_vector_layer(
    context,
    feedback,
    text,
    vector_layer,
    distance,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Create buffer in vector layer."""
    feedback.setProgressText(text)
    alg_params = {
        "INPUT": vector_layer,
        "DISTANCE": distance,
        "SEGMENTS": 5,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": True,
        "OUTPUT": output,
    }
    return processing.run(
        "native:buffer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def create_raster_from_grid(
    context,
    feedback,
    text,
    grid_layer,
    extent,
    pixel_size,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    """Create elevation raster layer by interpolating grid z on desired extent."""
    feedback.setProgressText(text)
    layer_source = context.getMapLayer(grid_layer).source()
    interpolation_source = 1  # elevation
    field_index = -1  # elevation
    input_type = 0  # points
    interpolation_data = (
        f"{layer_source}::~::{interpolation_source}::~::{field_index}::~::{input_type}"
    )
    feedback.pushInfo(f"interpolation_data: {interpolation_data}")  # FIXME
    alg_params = {
        "INTERPOLATION_DATA": interpolation_data,
        "METHOD": 0,  # linear
        "EXTENT": extent,
        "PIXEL_SIZE": pixel_size,
        "OUTPUT": output,
    }
    return processing.run(
        "qgis:tininterpolation",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


# FIXME
def clip_raster(
    context,
    feedback,
    text,
    raster,
    column_count,
    row_count,
    output_extent,
):
    """Clip raster to specified extent, width and height.

    Note there is similar utility in safe_qgis.utilities.clipper, but it uses
    gdal whereas this one uses native QGIS.

    :param raster: Raster
    :type raster: QgsRasterLayer

    :param column_count: Desired width in pixels of new raster
    :type column_count: Int

    :param row_count: Desired height in pixels of new raster
    :type row_count: Int

    :param output_extent: Extent of the clipped region
    :type output_extent: QgsRectangle

    :returns: Clipped region of the raster
    :rtype: QgsRasterLayer
    """
    provider = raster.dataProvider()
    pipe = QgsRasterPipe()
    pipe.set(provider.clone())

    base_name = unique_filename()
    file_name = base_name + ".tif"
    file_writer = QgsRasterFileWriter(file_name)
    file_writer.writeRaster(pipe, column_count, row_count, output_extent, raster.crs())

    return QgsRasterLayer(file_name, "clipped_raster")


# writeRaster(self, pipe: QgsRasterPipe, nCols: int, nRows: int, outputExtent: QgsRectangle, crs: QgsCoordinateReferenceSystem, transformContext: QgsCoordinateTransformContext, feedback: QgsRasterBlockFeedback = None) -> QgsRasterFileWriter.WriterError Write raster file
# Parameters
# pipe – raster pipe
# nCols – number of output columns
# nRows – number of output rows (or -1 to automatically calculate row number to have square pixels)
# outputExtent – extent to output
# crs – crs to reproject to
# transformContext – coordinate transform context
# feedback – optional feedback object for progress reports

# Code for QQIS 3.xx - QgsCoordinateTransform is different in v 2.xx #
# crsSrc = QgsCoordinateReferenceSystem(rlayer.crs())
# crsDest = QgsCoordinateReferenceSystem(4326) #epsg of target crs
# xform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())
# projected_extent = xform.transformBoundingBox(provider.extent())
# Then use this projected extent in the QgsRasterFileWriter.write_raster function:

# file_writer.writeRaster(pipe, provider.xSize(), provider.ySize(), projected_extent, provider.crs())

# processing.run(
#     "gdal:cliprasterbyextent",
#     {
#         "INPUT": "dpiMode=7&identifier=US_DEM2020&url=https://landfire.cr.usgs.gov/arcgis/services/Landfire/US_other/MapServer/WCSServer",
#         "PROJWIN": "-122.507197845,-122.454419819,37.821415768,37.842042623 [EPSG:4326]",
#         "OVERCRS": False,
#         "NODATA": None,
#         "OPTIONS": "",
#         "DATA_TYPE": 0,
#         "EXTRA": "",
#         "OUTPUT": "TEMPORARY_OUTPUT",
#     },
# )
