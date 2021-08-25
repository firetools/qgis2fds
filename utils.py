# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import time

from qgis.core import (
    QgsProcessingException,
    QgsMapSettings,
    QgsMapRendererParallelJob,
    QgsMapRendererSequentialJob,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsProject,
    QgsDistanceArea,
    QgsPointXY,
)
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize, QCoreApplication


# Write to file


def write_file(feedback, filepath, content):
    """
    Write a text to filepath.
    """
    try:
        with open(filepath, "w") as f:
            f.write(content)
    except IOError:
        raise QgsProcessingException(
            f"File not writable to <{filepath}>, cannot proceed."
        )
    feedback.pushInfo(f"Saved: <{filepath}>")


def write_texture(
    feedback,
    tex_layer,
    tex_extent,
    tex_pixel_size,
    utm_crs,  # destination_crs
    filepath,
    imagetype,
):
    """
    Crop and save texture to image file.
    """

    # Calc tex_extent size in meters (it is in utm)
    tex_extent_xm = tex_extent.xMaximum() - tex_extent.xMinimum()
    tex_extent_ym = tex_extent.yMaximum() - tex_extent.yMinimum()

    # Calc tex_extent size in pixels
    tex_extent_xpix = int(tex_extent_xm / tex_pixel_size)
    tex_extent_ypix = int(tex_extent_ym / tex_pixel_size)

    # Choose exporting layers
    if tex_layer:  # use user tex layer
        layers = (tex_layer,)
    else:  # no user tex layer, use map canvas
        canvas = iface.mapCanvas()
        layers = canvas.layers()

    # Image settings and texture layer choice
    settings = QgsMapSettings()  # build settings
    settings.setDestinationCrs(utm_crs)  # set output crs
    settings.setExtent(tex_extent)  # in utm_crs
    settings.setOutputSize(QSize(tex_extent_xpix, tex_extent_ypix))
    settings.setLayers(layers)

    feedback.pushInfo(
        f"Texture size: {tex_extent_xpix} x {tex_extent_ypix} pixels, {tex_extent_xm:.1f} x {tex_extent_ym:.1f} meters"
    )

    # Render and save image
    render = QgsMapRendererParallelJob(settings)
    render.start()
    t0 = time.time()
    while render.isActive():
        dt = time.time() - t0
        QCoreApplication.processEvents()
        if feedback.isCanceled():
            render.cancelWithoutBlocking()
            return
        if dt >= 30.0:
            render.cancelWithoutBlocking()
            feedback.reportError("Texture render timed out, no texture saved.")
            return
    image = render.renderedImage()
    try:
        image.save(filepath, imagetype)
    except IOError:
        raise QgsProcessingException(
            f"Texture not writable to <{filepath}>, cannot proceed."
        )
    feedback.pushInfo(f"Saved (in {dt:.2f} s): <{filepath}>")


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
    feedback, geom_type, n_surf_id, fds_verts, fds_faces, fds_surfs, fds_volus, filepath
):
    """!
    Write FDS bingeom file.
    @param feedback: pyqgis feedback
    @param geom_type: GEOM type (eg. 1 is manifold, 2 is terrain)
    @param n_surf_id: number of referred boundary conditions
    @param fds_verts: vertices coordinates in FDS flat format, eg. (x0, y0, z0, x1, y1, ...)
    @param fds_faces: faces connectivity in FDS flat format, eg. (i0, j0, k0, i1, ...)
    @param fds_surfs: boundary condition indexes, eg. (i0, i1, ...)
    @param fds_volus: volumes connectivity in FDS flat format, eg. (i0, j0, k0, w0, i1, ...)
    @param filepath: destination filepath
    """

    try:
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
    except IOError:
        raise QgsProcessingException(
            f"Bingeom file not writable to <{filepath}>, cannot proceed."
        )
    feedback.pushInfo(f"Saved: <{filepath}>")


# Geographic operations


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
