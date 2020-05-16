# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1


def classFactory(iface):
    """!
    Load qgis2fds class from file qgis2fds.

    @param iface: A QGIS interface instance.
    @type iface: QgsInterface
    """
    #
    from .qgis2fds import qgis2fdsPlugin

    return qgis2fdsPlugin()
