"""Processing provider exposed by the plugin."""

from qgis.core import QgsProcessingProvider

from .algorithm import ExportFdsAlgorithm
from .import_algorithm import ImportFdsAlgorithm


class FdsProvider(QgsProcessingProvider):
    """Provide the FDS export and result-import algorithms."""

    def loadAlgorithms(self):
        # Keep the export ID unchanged for existing Processing models and add
        # result import as a separate operation sharing the project settings.
        self.addAlgorithm(ExportFdsAlgorithm())
        self.addAlgorithm(ImportFdsAlgorithm())

    def id(self):
        # Kept verbatim for compatibility with existing qgis_process calls.
        return "NIST FDS"

    def name(self):
        return "NIST FDS"

    def longName(self):
        return self.name()
