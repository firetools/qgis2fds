import processing
from qgis.core import (
    QgsProcessing,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsProject,
)


def get_pixel_center_aligned_grid_layer(
    context,
    feedback,
    raster_layer,
    extent,
    extent_crs,
    larger,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Get center aligned sampling grid..."
    feedback.pushInfo(text)

    aligned_extent = get_pixel_aligned_extent(
        context,
        feedback,
        raster_layer=raster_layer,
        extent=extent,
        extent_crs=extent_crs,
        to_centers=True,
        larger=larger,
    )

    if feedback.isCanceled():
        return {}

    return get_grid_layer(
        context,
        feedback,
        extent=aligned_extent,
        extent_crs=raster_layer.crs(),
        xres=raster_layer.rasterUnitsPerPixelX(),
        yres=raster_layer.rasterUnitsPerPixelY(),
        output=output,
    )


def get_pixel_aligned_extent(
    context,
    feedback,
    raster_layer,
    extent,
    extent_crs,
    larger,
    to_centers,
) -> QgsRectangle:
    text = f"Align extent to raster layer pixels..."
    feedback.pushInfo(text)

    if feedback.isCanceled():
        return {}

    # Get raster_extent
    if not extent:  # FIXME check if extent has CRS
        raster_extent = raster_layer.extent()
    else:
        tr = QgsCoordinateTransform(
            extent_crs, raster_layer.crs(), QgsProject.instance()
        )
        raster_extent = tr.transformBoundingBox(extent)

    # Get raster_layer resolution
    xres = raster_layer.rasterUnitsPerPixelX()
    yres = raster_layer.rasterUnitsPerPixelY()
    feedback.pushInfo(f"Raster layer res: {xres}, {yres}")

    # Get top left extent corner coordinates,
    # because raster grid starts from top left corner of raster_layer extent
    lx0, ly1 = (
        raster_layer.extent().xMinimum(),
        raster_layer.extent().yMaximum(),
    )
    feedback.pushInfo(f"Raster layer extent: {lx0}, {ly1}")

    # Aligning raster_extent top left corner to raster_layer resolution,
    # never reduce its size
    x0, y0, x1, y1 = (
        raster_extent.xMinimum(),
        raster_extent.yMinimum(),
        raster_extent.xMaximum(),
        raster_extent.yMaximum(),
    )

    x0 = lx0 + (round((x0 - lx0) / xres) * xres)
    x1 = lx0 + (round((x1 - lx0) / xres) * xres)
    y0 = ly1 - (round((ly1 - y0) / yres) * yres)
    y1 = ly1 - (round((ly1 - y1) / yres) * yres)

    if to_centers:
        x0 += xres / 2.0
        x1 += -xres / 2.0 + 0.001
        y0 += yres / 2.0 - 0.001
        y1 += -yres / 2.0

    if larger:
        x0 -= xres * larger
        x1 += xres * larger
        y0 -= yres * larger
        y1 += yres * larger

    return QgsRectangle(x0, y0, x1, y1)


def get_grid_layer(
    context,
    feedback,
    extent,
    extent_crs,
    xres,
    yres,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Get grid..."
    feedback.pushInfo(text)

    alg_params = {
        "CRS": extent_crs,
        "EXTENT": extent,
        "HOVERLAY": 0,
        "HSPACING": xres,
        "TYPE": 0,  # Points
        "VOVERLAY": 0,
        "VSPACING": yres,
        "OUTPUT": output,
    }
    return processing.run(
        "native:creategrid",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def set_grid_layer_z(
    context,
    feedback,
    grid_layer,
    raster_layer,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    # It works when grid and raster share the same crs
    text = f"Set grid elevation..."
    feedback.pushInfo(text)

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
    grid_layer,
    raster_layer,
    column_prefix,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Set grid value ({column_prefix})..."
    feedback.pushInfo(text)

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


def get_reprojected_raster_layer(
    context,
    feedback,
    raster_layer,
    destination_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Reproject <{raster_layer}> raster layer to <{destination_crs}> crs..."
    feedback.pushInfo(text)

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


def get_reprojected_vector_layer(
    context,
    feedback,
    vector_layer,
    destination_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Reproject <{vector_layer}> vector layer to <{destination_crs}> crs..."
    feedback.pushInfo(text)

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


def get_buffered_vector_layer(
    context,
    feedback,
    vector_layer,
    distance,
    dissolve=False,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Buffer <{vector_layer}> vector layer..."
    feedback.pushInfo(text)

    alg_params = {
        "INPUT": vector_layer,
        "DISTANCE": distance,
        "SEGMENTS": 5,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": dissolve,
        "OUTPUT": output,
    }
    return processing.run(
        "native:buffer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def get_extent_layer(
    context,
    feedback,
    extent,
    extent_crs,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Get extent layer..."
    feedback.pushInfo(text)

    x0, y0, x1, y1 = (
        extent.xMinimum(),
        extent.yMinimum(),
        extent.xMaximum(),
        extent.yMaximum(),
    )
    alg_params = {
        "INPUT": f"{x0}, {x1}, {y0}, {y1} [{extent_crs.authid()}]",
        "OUTPUT": output,
    }
    return processing.run(
        "native:extenttolayer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
