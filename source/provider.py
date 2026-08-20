"""Processing provider exposed by the plugin."""

from qgis.core import QgsProcessingProvider

from .algorithm import ExportFdsAlgorithm


class FdsProvider(QgsProcessingProvider):
    """Provide the FDS export algorithm."""

    def loadAlgorithms(self):
        self.addAlgorithm(ExportFdsAlgorithm())

    def id(self):
        # Kept verbatim for compatibility with existing qgis_process calls.
        return "NIST FDS"

    def name(self):
        return "NIST FDS"

    def longName(self):
        return self.name()
