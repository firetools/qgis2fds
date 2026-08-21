"""QGIS plugin lifecycle."""

from qgis.core import QgsApplication

from .provider import FdsProvider


class Qgis2FdsPlugin:
    """Register the qgis2fds processing provider."""

    def __init__(self, _iface):
        # QGIS supplies its interface object as part of the plugin contract. This
        # Processing-only plugin does not need to retain it.
        self.provider = None

    def initProcessing(self):
        # QGIS may reach this method through different startup paths; guard
        # against registering the provider twice.
        if self.provider is None:
            self.provider = FdsProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        # The plugin intentionally exposes Processing only, with no toolbar UI.
        self.initProcessing()

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
