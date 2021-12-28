# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import os, time

from qgis.core import (
    QgsProject,
    QgsProcessingException,
    QgsMapSettings,
    QgsMapRendererParallelJob,
    QgsCoordinateTransform,
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QSize, QCoreApplication

from . import utils


class Texture:

    timeout = 30.0

    def __init__(
        self,
        feedback,
        path,
        name,
        image_type,
        pixel_size,
        layer,
        utm_extent,
        utm_crs,  # destination_crs
        dem_extent,
        dem_crs,
        export_obst,
    ) -> None:
        self.feedback = feedback
        self.image_type = image_type
        self.pixel_size = pixel_size
        self.layer = layer
        self.utm_crs = utm_crs

        self.filename = f"{name}_tex.{self.image_type}"
        self.filepath = os.path.join(path, self.filename)
        if export_obst:
            # Get tex_extent in utm_crs from utm_extent,
            # texture shall be aligned to MESH, and exactly cover the OBST terrain
            self.tex_extent = utm_extent
        else:
            # Get tex_extent in utm_crs from dem_extent,
            # texture shall be aligned to MESH, and exactly cover the GEOM terrain
            dem_to_utm_tr = QgsCoordinateTransform(
                dem_crs, utm_crs, QgsProject.instance()
            )
            self.tex_extent = dem_to_utm_tr.transformBoundingBox(dem_extent)
        self._save()

    def get_comment(self):
        return f"! Terrain texture file: <{utils.shorten(self.filepath)}>"

    def get_fds(self):
        return f"TERRAIN_IMAGE='{self.filename}'"

    def _save(self):
        self.feedback.pushInfo(f"Save terrain texture file: <{self.filepath}>")
        # Calc tex_extent size in meters (it is in utm)
        tex_extent_xm = self.tex_extent.xMaximum() - self.tex_extent.xMinimum()
        tex_extent_ym = self.tex_extent.yMaximum() - self.tex_extent.yMinimum()
        # Calc tex_extent size in pixels
        tex_extent_xpix = int(tex_extent_xm / self.pixel_size)
        tex_extent_ypix = int(tex_extent_ym / self.pixel_size)
        # Choose exporting layers
        if self.layer:  # use user tex layer
            layers = (self.layer,)
        else:  # no user tex layer, use map canvas
            canvas = iface.mapCanvas()
            layers = canvas.layers()
        # Image settings and texture layer choice
        settings = QgsMapSettings()  # build settings
        settings.setDestinationCrs(self.utm_crs)  # set output crs
        settings.setExtent(self.tex_extent)  # in utm_crs
        settings.setOutputSize(QSize(tex_extent_xpix, tex_extent_ypix))
        settings.setLayers(layers)
        # Render and save image
        render = QgsMapRendererParallelJob(settings)
        render.start()
        t0 = time.time()
        while render.isActive():
            dt = time.time() - t0
            QCoreApplication.processEvents()
            if self.feedback.isCanceled():
                render.cancelWithoutBlocking()
                return
            if dt >= self.timeout:
                render.cancelWithoutBlocking()
                self.feedback.reportError("Texture render timed out, no texture saved.")
                return
        image = render.renderedImage()
        try:
            image.save(self.filepath, self.image_type)
        except IOError:
            raise QgsProcessingException(f"Texture not writable to <{self.filepath}>.")
        self.feedback.pushInfo(f"Texture saved in {dt:.2f} s")
