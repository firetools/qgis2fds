# -*- coding: utf-8 -*-

"""qgis2fds utils"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import (
    QgsCoordinateTransform,
    QgsProject,
    QgsPointXY,
    QgsRectangle,
    QgsRasterFileWriter,
    QgsRasterPipe,
    QgsProcessing,
    QgsProcessingException,
    QgsRasterLayer,
)
import processing
import os, time, math


def transform_extent(extent, source_crs, dest_crs):
    _tr = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
    return _tr.transformBoundingBox(extent)


def transform_point(point, source_crs, dest_crs):
    _tr = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
    return _tr.transform(QgsPointXY(point))


def get_extent_aligned_to_raster(layer, extent, nlarger=10):
    """Get extent aligned to raster pixels, in the same CRS."""
    # Get raster resolution
    xres, yres = layer.rasterUnitsPerPixelX(), layer.rasterUnitsPerPixelY()
    # Get top left extent corner coordinates,
    # because raster grid starts from top left corner of raster_layer extent
    lx0, ly1 = layer.extent().xMinimum(), layer.extent().yMaximum()
    # Aligning raster_extent top left corner to raster_layer resolution,
    # never reduce its size
    x0, y0, x1, y1 = (
        extent.xMinimum(),
        extent.yMinimum(),
        extent.xMaximum(),
        extent.yMaximum(),
    )
    x0 = lx0 + (round((x0 - lx0) / xres) * xres) - xres * nlarger
    x1 = lx0 + (round((x1 - lx0) / xres) * xres) + xres * nlarger
    y0 = ly1 - (round((ly1 - y0) / yres) * yres) - xres * nlarger
    y1 = ly1 - (round((ly1 - y1) / yres) * yres) + xres * nlarger
    return QgsRectangle(x0, y0, x1, y1)


def get_extent_multiple_of_pixels(extent, pixel_size, epsilon):
    """Get extent that has sizes exactly multiples of pixel size."""
    epsilon = 1e-6  # epsilon used to nudge the native:creategrid algo
    width = math.ceil(extent.width() / pixel_size) * pixel_size + epsilon
    height = math.ceil(extent.height() / pixel_size) * pixel_size + epsilon
    x0, x1, y0, y1 = (
        extent.xMinimum(),
        extent.xMaximum(),
        extent.yMinimum(),
        extent.yMaximum(),
    )
    x1 = x0 + width
    y0 = y1 - height
    return QgsRectangle(x0, y0, x1, y1)


def save_raster_layer(layer, extent, filepath):
    """Save aligned extent of layer in path."""
    # Prepare filepath and machinery
    file_writer = QgsRasterFileWriter(filepath)
    pipe = QgsRasterPipe()
    provider = layer.dataProvider()
    ok = pipe.set(provider.clone())
    if not ok:
        msg = f"Error saving layer data, cannot proceed.\n(pipe, ok: {ok}) {filepath}"
        raise QgsProcessingException(msg)
    # Get aligned extent and set resolution
    extent = get_extent_aligned_to_raster(layer=layer, extent=extent)
    xres, yres = layer.rasterUnitsPerPixelX(), layer.rasterUnitsPerPixelY()
    nCols = round(extent.width() / xres)
    nRows = round(extent.height() / yres)
    # Save and check
    err = file_writer.writeRaster(
        pipe=pipe, nCols=nCols, nRows=nRows, outputExtent=extent, crs=layer.crs()
    )
    if err:
        msg = (
            f"Error saving layer data, cannot proceed.\n(write, err: {err}) {filepath}"
        )
        raise QgsProcessingException(msg)
    return filepath


def show_extent(context, feedback, extent, extent_crs, name, style=None):
    """Show extent as vector layer."""
    x0, x1, y0, y1 = (
        extent.xMinimum(),
        extent.xMaximum(),
        extent.yMinimum(),
        extent.yMaximum(),
    )
    extent_str = f"{x0}, {x1}, {y0}, {y1} [{extent_crs.authid()}]"
    feedback.setProgressText(f"Extent to layer {name}: {extent_str} ...")
    alg_params = {
        "INPUT": extent_str,
        "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
    }
    output = processing.run(
        "native:extenttolayer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    show_layer(
        context=context,
        feedback=feedback,
        layer=context.getMapLayer(output["OUTPUT"]),
        name=name,
        style=style,
    )


def show_layer(context, feedback, layer, name=None, style=None):
    """Show layer."""
    feedback.setProgressText(f"Show layer {name}: {layer} ...")
    if name:
        layer.setName(name)
    QgsProject.instance().addMapLayer(layer)
    if style:
        style_pathfile = os.path.join(get_plugin_path(), "styles", style)
        layer.loadNamedStyle(style_pathfile)
        layer.triggerRepaint()


def get_plugin_path():
    """Get current plugin path."""
    return os.path.dirname(os.path.realpath(__file__))


def run_create_spatial_index(parameters, context, feedback, layer):
    """Create spatial index of a vector layer to speed up the next process."""
    feedback.setProgressText("\nCreate spatial index...")
    t0 = time.time()
    alg_params = {"INPUT": layer}
    output = processing.run(
        "native:createspatialindex",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
    return output
