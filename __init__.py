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

__author__ = 'Emanuele Gissi'
__date__ = '2020-05-04'
__copyright__ = '(C) 2020 by Emanuele Gissi'


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load QGIS2FDS class from file QGIS2FDS.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .QGIS2FDS import QGIS2FDSPlugin
    return QGIS2FDSPlugin()
