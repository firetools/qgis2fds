"""QGIS entry point for qgis2fds."""


def classFactory(iface):
    """Create the QGIS plugin instance."""
    # Delay QGIS-dependent imports until the plugin loader requests an instance.
    from .plugin import Qgis2FdsPlugin

    return Qgis2FdsPlugin(iface)
