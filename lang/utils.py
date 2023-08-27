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
)
import processing
import os, time, math


# Geographic utils


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


# UTM utils


def get_lonlat_url(wgs84_point):
    return f"http://www.openstreetmap.org/?mlat={wgs84_point.y()}&mlon={wgs84_point.x()}&zoom=12"


def lonlat_to_zn(lon, lat):
    """!
    Conversion from longitude/latitude to UTM zone number.
    @param lon: longitude in decimal degrees.
    @param lat: latitude in decimal degrees.
    @return the UTM zone number.
    """
    if lat < -90.0 or lat > 90.0:
        raise Exception(f"Latitude <{lat}> out of bounds.")
    if lon < -180.0 or lon > 180.0:
        raise Exception(f"Longitude <{lon}> out of bounds.")
    if 56 <= lat < 64 and 3 <= lon < 12:
        return 32
    if 72 <= lat <= 84 and lon >= 0:
        if lon < 9:
            return 31
        elif lon < 21:
            return 33
        elif lon < 33:
            return 35
        elif lon < 42:
            return 37
    return int((lon + 180) / 6) + 1


def lat_to_ne(lat):
    """!
    Detect if latitude is on the UTM north hemisphere.
    @param lat: latitude in decimal degrees.
    @return True if UTM north hemisphere. False otherwise.
    """
    if lat < -90.0 or lat > 90.0:
        raise Exception(f"Latitude <{lat}> out of bounds.")
    if lat >= -1e-6:
        return True
    else:
        return False


def lonlat_to_epsg(lon, lat):
    """!
    Conversion from longitude/latitude to EPSG.
    @param lon: longitude in decimal degrees.
    @param lat: latitude in decimal degrees.
    @return the EPSG.
    """
    if lat < -90.0 or lat > 90.0:
        raise Exception(f"Latitude <{lat}> out of bounds.")
    if lon < -180.0 or lon > 180.0:
        raise Exception(f"Longitude <{lon}> out of bounds.")
    zn = lonlat_to_zn(lon=lon, lat=lat)
    if lat_to_ne(lat):
        return "EPSG:326" + str(zn).zfill(2)
    else:
        return "EPSG:327" + str(zn).zfill(2)


# Text util


def shorten(text):
    return len(text) > 60 and f"...{text[-57:]}" or text or "none"


# Write to file


def get_plugin_path():
    """Get current plugin path."""
    return os.path.dirname(os.path.realpath(__file__))


def write_file(feedback, filepath, content):
    """
    Write a text to filepath.
    """
    feedback.pushInfo(f"Save file: <{filepath}>")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, "w") as f:
            f.write(content)
    except Exception as err:
        raise QgsProcessingException(
            f"File not writable to <{filepath}>, cannot proceed.\n{err}"
        )


# The FDS bingeom file is written from Fortran90 like this:
#      WRITE(731) INTEGER_ONE
#      WRITE(731) N_VERTS,N_FACES,N_SURF_ID,N_VOLUS
#      WRITE(731) VERTS(1:3*N_VERTS)
#      WRITE(731) FACES(1:3*N_FACES)
#      WRITE(731) SURFS(1:N_FACES)
#      WRITE(731) VOLUS(1:4*N_VOLUS)

import struct
import numpy as np


def _write_record(f, data):
    """!
    Write a record to a binary unformatted sequential Fortran90 file.
    @param f: open Python file object in 'wb' mode.
    @param data: np.array() of data.
    """
    # Calc start and end record tag
    tag = len(data) * data.dtype.itemsize
    # print(f"Write: record tag: {tag} dlen: {len(data)}\ndata: {data}")  # TODO log debug
    # Write start tag, data, and end tag
    f.write(struct.pack("i", tag))
    data.tofile(f)
    f.write(struct.pack("i", tag))


def write_bingeom(
    feedback,
    filepath,
    geom_type,
    n_surf_id,
    fds_verts,
    fds_faces,
    fds_surfs,
    fds_volus,
):
    """!
    Write FDS bingeom file.
    @param feedback: pyqgis feedback
    @param filepath: destination filepath
    @param geom_type: GEOM type (eg. 1 is manifold, 2 is terrain)
    @param n_surf_id: number of referred boundary conditions
    @param fds_verts: vertices coordinates in FDS flat format, eg. (x0, y0, z0, x1, y1, ...)
    @param fds_faces: faces connectivity in FDS flat format, eg. (i0, j0, k0, i1, ...)
    @param fds_surfs: boundary condition indexes, eg. (i0, i1, ...)
    @param fds_volus: volumes connectivity in FDS flat format, eg. (i0, j0, k0, w0, i1, ...)
    """
    feedback.pushInfo(f"Save bingeom file: <{filepath}>")
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            _write_record(f, np.array((geom_type,), dtype="int32"))  # was 1 only
            _write_record(
                f,
                np.array(
                    (
                        len(fds_verts) // 3,
                        len(fds_faces) // 3,
                        n_surf_id,
                        len(fds_volus) // 4,
                    ),
                    dtype="int32",
                ),
            )
            _write_record(f, np.array(fds_verts, dtype="float64"))
            _write_record(f, np.array(fds_faces, dtype="int32"))
            _write_record(f, np.array(fds_surfs, dtype="int32"))
            _write_record(f, np.array(fds_volus, dtype="int32"))
    except Exception as err:
        raise QgsProcessingException(
            f"Bingeom file not writable to <{filepath}>, cannot proceed.\n{err}"
        )
