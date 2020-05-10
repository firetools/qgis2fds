# -*- coding: utf-8 -*-

"""
 QGIS2FDS
                                 A QGIS plugin
 Export terrain in NIST FDS notation
                              -------------------
        begin                : 2020-05-04
        copyright            : (C) 2020 by Emanuele Gissi
        email                : emanuele.gissi@gmail.com
"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = "$Format:%H$"


from qgis.core import QgsProcessingException, QgsMapSettings, QgsMapRendererParallelJob
from qgis.utils import iface
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize


def write_file(filepath, content):
    """
    Write a text to filepath.
    """
    try:
        with open(filepath, "w") as f:
            f.write(content)
    except IOError:
        raise QgsProcessingException(f"File not writable at <{filepath}>")


def write_image(destination_crs, extent, filepath, imagetype):
    """
    Save current QGIS canvas to image file.
    """
    layers = iface.mapCanvas().layers()  # get visible layers
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setBackgroundColor(QColor(255, 255, 255))
    settings.setDestinationCrs(destination_crs)  # set output crs
    settings.setExtent(extent)

    dx = 1920 * 2
    dy = int(
        (extent.yMaximum() - extent.yMinimum())
        / (extent.xMaximum() - extent.xMinimum())
        * dx
    )
    settings.setOutputSize(QSize(dx, dy))

    render = QgsMapRendererParallelJob(settings)
    render.start()
    render.waitForFinished()
    image = render.renderedImage()
    try:
        image.save(filepath, imagetype)
    except IOError:
        raise QgsProcessingException(f"Image not writable at <{filepath}>")
