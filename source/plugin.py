"""QGIS plugin lifecycle."""

from qgis.core import QgsApplication

from .provider import FdsProvider


class Qgis2FdsPlugin:
    """Register the qgis2fds processing provider."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        if self.provider is None:
            self.provider = FdsProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
