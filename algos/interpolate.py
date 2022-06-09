import processing
from qgis.core import QgsProcessing
from .utils import (
    get_pixel_center_aligned_grid_layer,
    set_grid_layer_z,
    get_reprojected_vector_layer,
)


def clip_and_interpolate_dem(
    context,
    feedback,
    dem_layer,
    extent,
    extent_crs,
    pixel_size,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"\nInterpolate <{dem_layer}> layer at <{pixel_size}> pixel size..."
    feedback.setProgressText(text)

    tmp = get_pixel_center_aligned_grid_layer(
        context,
        feedback,
        raster_layer=dem_layer,
        extent=extent,
        extent_crs=extent_crs,
        larger=2.0,  # FIXME what if downsampling as in CERN?
    )

    if feedback.isCanceled():
        return {}

    tmp = set_grid_layer_z(
        context,
        feedback,
        grid_layer=tmp["OUTPUT"],
        raster_layer=dem_layer,
    )

    if feedback.isCanceled():
        return {}

    tmp = get_reprojected_vector_layer(
        context,
        feedback,
        vector_layer=tmp["OUTPUT"],
        destination_crs=extent_crs,
    )

    if feedback.isCanceled():
        return {}

    return _create_raster_from_grid(
        context,
        feedback,
        grid_layer=tmp["OUTPUT"],
        extent=extent,
        pixel_size=pixel_size,
        output=output,
    )


def _create_raster_from_grid(
    context,
    feedback,
    grid_layer,
    extent,
    pixel_size,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"Interpolate elevation..."
    feedback.pushInfo(text)

    layer_source = context.getMapLayer(grid_layer).source()
    interpolation_source = 1  # elevation
    field_index = -1  # elevation
    input_type = 0  # points
    interpolation_data = (
        f"{layer_source}::~::{interpolation_source}::~::{field_index}::~::{input_type}"
    )
    feedback.pushInfo(f"interpolation_data: {interpolation_data}")  # FIXME
    alg_params = {
        "INTERPOLATION_DATA": interpolation_data,
        "METHOD": 0,  # linear
        "EXTENT": extent,
        "PIXEL_SIZE": pixel_size,
        "OUTPUT": output,
    }
    return processing.run(
        "qgis:tininterpolation",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
