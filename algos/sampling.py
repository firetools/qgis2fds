import processing
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingException,
    QgsField,
    NULL,
    edit,
    QgsFeatureRequest,
)
from .utils import (
    get_pixel_center_aligned_grid_layer,
    set_grid_layer_z,
    set_grid_layer_value,
    reproject_vector_layer,
    get_buffered_vector_layer,
)


def prepare_fire_layers(
    context,
    feedback,
    fire_layer,
    destination_crs,
    pixel_size,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"\nReproject and buffer <{fire_layer}> fire layer..."
    feedback.setProgressText(text)

    outputs = dict()

    if feedback.isCanceled():
        return {}

    # Internal (burned area)
    outputs["w_fire_layer"] = reproject_vector_layer(
        context,
        feedback,
        vector_layer=fire_layer,
        destination_crs=destination_crs,
    )

    if feedback.isCanceled():
        return {}

    # External (fire front)
    outputs["w_buffer_fire_layer"] = get_buffered_vector_layer(
        context,
        feedback,
        vector_layer=outputs["w_fire_layer"]["OUTPUT"],
        distance=pixel_size,
        dissolve=False,
    )

    return outputs["w_fire_layer"], outputs["w_buffer_fire_layer"]


def get_sampling_point_grid_layer(
    context,
    feedback,
    utm_dem_layer,
    landuse_layer,
    utm_fire_layer,
    utm_b_fire_layer,
    bc_in_default,
    bc_out_default,
    output=QgsProcessing.TEMPORARY_OUTPUT,
):
    text = f"\nCreate sampling grid layer for FDS geometry..."
    feedback.setProgressText(text)

    tmp = get_pixel_center_aligned_grid_layer(
        context,
        feedback,
        raster_layer=utm_dem_layer,
        extent=None,
        extent_crs=None,
        larger=0.0,
    )

    if feedback.isCanceled():
        return {}

    tmp = set_grid_layer_z(
        context,
        feedback,
        grid_layer=tmp["OUTPUT"],
        raster_layer=utm_dem_layer,
        output=output,
    )

    if feedback.isCanceled():
        return {}

    if landuse_layer:
        tmp = set_grid_layer_value(
            context,
            feedback,
            grid_layer=tmp["OUTPUT"],
            raster_layer=landuse_layer,
            column_prefix="landuse",
            output=output,
        )
    else:
        feedback.pushInfo("No landuse layer provided.")
        # Add NULL field
        tmp_layer = context.getMapLayer(tmp["OUTPUT"])
        with edit(tmp_layer):
            attributes = list((QgsField("landuse1", QVariant.Int),))
            tmp_layer.dataProvider().addAttributes(attributes)
            tmp_layer.updateFields()

    if feedback.isCanceled():
        return {}

    _load_fire_layer_bc(
        context,
        feedback,
        sampling_layer=tmp["OUTPUT"],
        fire_layer=utm_b_fire_layer,
        bc_field="bc_out",
        bc_default=bc_out_default,
    )

    if feedback.isCanceled():
        return {}

    _load_fire_layer_bc(
        context,
        feedback,
        sampling_layer=tmp["OUTPUT"],
        fire_layer=utm_fire_layer,
        bc_field="bc_in",
        bc_default=bc_in_default,
    )

    if feedback.isCanceled():
        return {}

    return tmp


def _load_fire_layer_bc(
    context,
    feedback,
    sampling_layer,
    fire_layer,
    bc_field,
    bc_default,
):
    text = f"Load fire layer bc ({bc_field})..."
    feedback.pushInfo(text)

    # Edit sampling layer
    sampling_layer = context.getMapLayer(sampling_layer)
    with edit(sampling_layer):

        # Add new data field
        if sampling_layer.dataProvider().fieldNameIndex("bc") == -1:
            attributes = list((QgsField("bc", QVariant.Int),))
            sampling_layer.dataProvider().addAttributes(attributes)
            sampling_layer.updateFields()
        output_bc_idx = sampling_layer.dataProvider().fieldNameIndex("bc")

        if fire_layer:
            # For all fire layer features
            bc_idx = fire_layer.fields().indexOf(bc_field)
            for fire_feat in fire_layer.getFeatures():

                # Check if user specified per feature bc available
                if bc_idx != -1:
                    bc = fire_feat[bc_idx]
                else:
                    bc = bc_default

                # Set bc in sampling layer
                # for speed, preselect points
                fire_geom = fire_feat.geometry()
                fire_geom_bbox = fire_geom.boundingBox()
                for f in sampling_layer.getFeatures(QgsFeatureRequest(fire_geom_bbox)):
                    g = f.geometry()
                    if fire_geom.contains(g):
                        if bc != NULL:
                            sampling_layer.changeAttributeValue(f.id(), output_bc_idx, bc)
                feedback.pushInfo(
                    f"<bc={bc}> applyed from fire layer <{fire_feat.id()}> feature"
                )
