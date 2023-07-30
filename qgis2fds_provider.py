# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import QgsProcessingProvider
from .qgis2fds_export_algo import qgis2fdsExportAlgo


class qgis2fdsProvider(QgsProcessingProvider):
    def __init__(self):
        """
        Default constructor.
        """
        QgsProcessingProvider.__init__(self)

    def unload(self):
        """
        Unloads the provider.
        """
        pass

    def loadAlgorithms(self):
        """
        Loads all algorithms belonging to this provider.
        """
        self.addAlgorithm(qgis2fdsExportAlgo())

    def id(self):
        """
        Returns the unique provider id.
        """
        return "NIST FDS"

    def name(self):
        """
        Returns the provider name.
        """
        return "NIST FDS"

    def icon(self):
        """
        Returns a QIcon which is used for your provider inside
        the Processing toolbox.
        """
        return QgsProcessingProvider.icon(self)

    def longName(self):
        """
        Returns the a longer version of the provider name.
        """
        return self.name()
