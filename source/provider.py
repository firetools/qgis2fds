"""Processing provider exposed by the plugin."""

from qgis.core import QgsProcessingProvider

from .algorithm import ExportFdsAlgorithm


class FdsProvider(QgsProcessingProvider):
    """Provide the FDS export algorithm."""

    def loadAlgorithms(self):
        # There is one stable algorithm ID beneath this provider; keeping it here
        # preserves existing Processing models and qgis_process commands.
        self.addAlgorithm(ExportFdsAlgorithm())

    def id(self):
        # Kept verbatim for compatibility with existing qgis_process calls.
        return "NIST FDS"

    def name(self):
        return "NIST FDS"

    def longName(self):
        return self.name()
