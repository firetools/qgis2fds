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
        raise QgsProcessingException(f"File not writable at <{filepath}>")


def write_image(
    feedback,
    tex_layer,
    tex_pixel_size,
    destination_crs,
    destination_extent,
    filepath,
    imagetype,
):
    """
    Save current QGIS canvas to image file.
    """
    project = QgsProject.instance()

    # Get extent size in meters
    d = QgsDistanceArea()
    d.setSourceCrs(
        crs=destination_crs, context=QgsProject.instance().transformContext()
    )
    p00, p10, p01 = (
        QgsPointXY(destination_extent.xMinimum(), destination_extent.yMinimum()),
        QgsPointXY(destination_extent.xMaximum(), destination_extent.yMinimum()),
        QgsPointXY(destination_extent.xMinimum(), destination_extent.yMaximum()),
    )
    wm = d.measureLine(p00, p10)  # euclidean dist, extent width in m
    hm = d.measureLine(p00, p01)  # euclidean dist, extent height in m
    feedback.pushInfo(f"Texture extent size: {wm:.2f}x{hm:.2f} m")

    # Image settings and texture layer choice
    settings = QgsMapSettings()  # build settings
    settings.setDestinationCrs(destination_crs)  # set output crs
    settings.setExtent(destination_extent)  # in destination_crs
    if tex_layer:
        layers = (tex_layer,)  # chosen texture layer
    else:
        canvas = iface.mapCanvas()
        layers = canvas.layers()  # get visible layers
    wpix = int(wm / tex_pixel_size)
    hpix = int(hm / tex_pixel_size)
    settings.setOutputSize(QSize(wpix, hpix))
    settings.setLayers(layers)

    # Render and save image
    render = QgsMapRendererParallelJob(settings)
    render.start()
    t0 = time.time()
    while render.isActive():
        dt = int(time.time() - t0)
        QCoreApplication.processEvents()
        feedback.pushInfo(f"Rendering texture ({dt} s/60 s)...")
        time.sleep(2)
        if feedback.isCanceled() or dt >= 60:
            render.cancelWithoutBlocking()
            feedback.pushInfo(
                "No texture saved: render cancelled or timed out due to unavailable server at this pixel size."
            )
            return
    image = render.renderedImage()
    try:
        image.save(filepath, imagetype)
    except IOError:
        raise QgsProcessingException(f"Texture not writable in <{filepath}>")
    feedback.pushInfo(f"Texture saved {wpix}x{hpix} pixels.")


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
    geom_type, n_surf_id, fds_verts, fds_faces, fds_surfs, fds_volus, filepath
):
    """!
    Write FDS bingeom file.
    @param geom_type: GEOM type (eg. 1 is manifold, 2 is terrain)
    @param n_surf_id: number of referred boundary conditions
    @param fds_verts: vertices coordinates in FDS flat format, eg. (x0, y0, z0, x1, y1, ...)
    @param fds_faces: faces connectivity in FDS flat format, eg. (i0, j0, k0, i1, ...)
    @param fds_surfs: boundary condition indexes, eg. (i0, i1, ...)
    @param fds_volus: volumes connectivity in FDS flat format, eg. (i0, j0, k0, w0, i1, ...)
    @param filepath: destination filepath
    """

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
    zn = lonlat_to_zn(lon=lon, lat=lat)
    if lat_to_ne(lat):
        return "EPSG:326" + str(zn).zfill(2)
    else:
        return "EPSG:327" + str(zn).zfill(2)
