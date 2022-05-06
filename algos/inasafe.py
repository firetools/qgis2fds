from qgis.core import QgsRasterLayer, QgsRasterFileWriter, QgsRasterPipe, QgsRectangle
import tempfile
import processing


def align_clip_raster(raster_layer, extent):
    """Align raster extent and the given extent.

    Both layers should be in the same projection.

    .. versionadded:: 3.4
    .. note:: Delegates to clip_raster()

    :param hazard_layer: The raster layer.
    :type hazard_layer: QgsRasterLayer

    :param extent: The extent in the form [xmin, ymin, xmax, ymax]
    :type extent: list

    :returns: Clipped region of the raster
    :rtype: QgsRasterLayer
    """
    raster_extent = raster_layer.dataProvider().extent()
    clip_xmin = raster_extent.xMinimum()
    clip_ymin = raster_extent.yMinimum()

    if extent[0] > clip_xmin:
        clip_xmin = extent[0]
    if extent[1] > clip_ymin:
        clip_ymin = extent[1]

    height = (extent[3] - extent[1]) / raster_layer.rasterUnitsPerPixelY()
    height = int(height)

    width = (extent[2] - extent[0]) / raster_layer.rasterUnitsPerPixelX()
    width = int(width)

    raster_extent = raster_layer.dataProvider().extent()
    xmin = raster_extent.xMinimum()
    xmax = raster_extent.xMaximum()
    ymin = raster_extent.yMinimum()
    ymax = raster_extent.yMaximum()

    x_delta = (xmax - xmin) / raster_layer.width()
    x = xmin
    for i in range(raster_layer.width()):
        if abs(x - clip_xmin) < x_delta:
            # We have found the aligned raster boundary
            break
        x += x_delta
        _ = i

    y_delta = (ymax - ymin) / raster_layer.height()
    y = ymin
    for i in range(raster_layer.width()):
        if abs(y - clip_ymin) < y_delta:
            # We have found the aligned raster boundary
            break
        y += y_delta

    clip_extent = [x, y, x + width * x_delta, y + height * y_delta]

    small_raster = clip_raster(raster_layer, width, height, QgsRectangle(*clip_extent))
    return small_raster


def clip_raster(raster, column_count, row_count, output_extent):
    """Clip raster to specified extent, width and height.

    Note there is similar utility in safe_qgis.utilities.clipper, but it uses
    gdal whereas this one uses native QGIS.

    :param raster: Raster
    :type raster: QgsRasterLayer

    :param column_count: Desired width in pixels of new raster
    :type column_count: Int

    :param row_count: Desired height in pixels of new raster
    :type row_count: Int

    :param output_extent: Extent of the clipped region
    :type output_extent: QgsRectangle

    :returns: Clipped region of the raster
    :rtype: QgsRasterLayer
    """
    provider = raster.dataProvider()
    pipe = QgsRasterPipe()
    pipe.set(provider.clone())

    with tempfile.NamedTemporaryFile(delete=True) as temp:
        # Write tmp file
        filepath = str(temp.name)
        fw = QgsRasterFileWriter(filepath)
        fw.writeRaster(pipe, column_count, row_count, output_extent, raster.crs())
        # FIXME FIXME FIXME
        # do something with the layer to have a real tmp layer
        return processing.run(
            "native:fillnodata",
            {
                "INPUT": filepath,  # FIXME test on Win and MacOS
                "BAND": 1,
                "FILL_VALUE": -9999,
                "OUTPUT": "TEMPORARY_OUTPUT",  # FIXME
            },
        )
    # return QgsRasterLayer(filepath, "clipped_raster")

    # We make one pixel size buffer on the extent to cover every pixels.
    # See https://github.com/inasafe/inasafe/issues/3655
    pixel_size_x = layer.rasterUnitsPerPixelX()
    pixel_size_y = layer.rasterUnitsPerPixelY()
    buffer_size = max(pixel_size_x, pixel_size_y)
    extent = extent.buffer(buffer_size)
