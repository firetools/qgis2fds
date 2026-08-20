"""QGIS entry point for qgis2fds."""


def classFactory(iface):
    """Create the QGIS plugin instance."""
    from .plugin import Qgis2FdsPlugin

    return Qgis2FdsPlugin(iface)
