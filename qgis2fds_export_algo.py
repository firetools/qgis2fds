# -*- coding: utf-8 -*-

"""qgis2fds export algorithm"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import (
    QgsProject,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterVectorDestination,
    QgsCoordinateReferenceSystem,
    QgsField,
    NULL,
    edit,
    QgsFeatureRequest,
)
from qgis.PyQt.QtCore import QVariant

import processing
import time

from .lang import *

DEBUG = False


class qgis2fdsExportAlgo(QgsProcessingAlgorithm):
    """
    Export to FDS case algorithm.
    """

    def initAlgorithm(self, config=None):
        # Define parameters
        kwargs = {"algo": self, "config": config, "project": QgsProject.instance()}
        ChidParam.set(**kwargs)
        FDSPathParam.set(**kwargs)
        ExtentLayerParam.set(**kwargs)
        PixelSizeParam.set(**kwargs)
        OriginParam.set(**kwargs)
        DEMLayerParam.set(**kwargs)
        LanduseLayerParam.set(**kwargs)
        LanduseTypeFilepathParam.set(**kwargs)
        FireLayer.set(**kwargs)
        # Advanced
        # TexLayerParam.set(**kwargs) # FIXME remove?
        TexPixelSizeParam.set(**kwargs)
        NMeshParam.set(**kwargs)
        CellSizeParam.set(**kwargs)
        StartTimeParam.set(**kwargs)
        EndTimeParam.set(**kwargs)
        WindFilepathParam.set(**kwargs)
        TextFilepathParam.set(**kwargs)
        ExportOBSTParam.set(**kwargs)

        # Define destination layers

        self.addParameter(  # FIXME currently not used
            QgsProcessingParameterVectorDestination(
                "UtmGrid",
                "UTM sampling grid",
                type=QgsProcessing.TypeVectorPoint,
                optional=True,
            )
        )

        if DEBUG:
            self.addParameter(
                QgsProcessingParameterRasterDestination(
                    "UtmInterpolatedDemLayer",
                    "UTM interpolated DEM layer",
                    optional=True,
                )
            )

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(6, model_feedback)
        results, outputs, project = {}, {}, QgsProject.instance()

        # Load parameter values

        kwargs = {
            "algo": self,
            "parameters": parameters,
            "context": context,
            "feedback": feedback,
            "project": project,
        }

        # FIXME move to required place

        chid = ChidParam.get(**kwargs)
        fds_path = FDSPathParam.get(**kwargs)

        fire_layer = FireLayer.get(**kwargs)
        # tex_layer = TexLayerParam.get(**kwargs) # FIXME remove?
        tex_pixel_size = TexPixelSizeParam.get(**kwargs)
        nmesh = NMeshParam.get(**kwargs)

        export_obst = ExportOBSTParam.get(**kwargs)
        t_begin = StartTimeParam.get(**kwargs)
        t_end = EndTimeParam.get(**kwargs)
        wind_filepath = WindFilepathParam.get(**kwargs)
        text_filepath = TextFilepathParam.get(**kwargs)  # FIXME develop!

        # Get extent_layer and origin
        # Calc wgs84_extent and wgs84_origin

        extent_layer = ExtentLayerParam.get(**kwargs)  # in project crs
        origin = OriginParam.get(**kwargs)  # in project crs

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_extent = utils.transform_extent(
            extent=extent_layer.extent(),
            source_crs=extent_layer.crs(),
            dest_crs=wgs84_crs,
        )

        if origin:
            wgs84_origin = utils.transform_point(
                point=origin,
                source_crs=project.crs(),
                dest_crs=wgs84_crs,
            )
        else:
            wgs84_origin = wgs84_extent.center()

        feedback.setProgressText(f"WGS84 origin: {wgs84_origin}")

        # Calc applicable UTM crs at the origin

        _epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(_epsg)
        feedback.setProgressText(f"Selected UTM CRS: {utm_crs.authid()}")

        # Calc utm_origin

        utm_origin = utils.transform_point(
            point=wgs84_origin,
            source_crs=wgs84_crs,
            dest_crs=utm_crs,
        )
        feedback.setProgressText(f"UTM origin: {utm_origin}")

        # Get pixel_size, calc and adapt utm_extent:
        # align it to the pixel_size, better for sampling grid and DEM interpolation

        pixel_size = PixelSizeParam.get(**kwargs)

        utm_extent = utils.transform_extent(
            extent=wgs84_extent,
            source_crs=wgs84_crs,
            dest_crs=utm_crs,
        )

        utm_extent = utils.get_extent_multiple_of_pixels(
            extent=utm_extent, pixel_size=pixel_size, epsilon=1e-6
        )  # epsilon used to nudge the native:creategrid algo

        msg = f"UTM extent size: {utm_extent.width():.1f}x{utm_extent.height():.1f}m"
        feedback.setProgressText(msg)

        if DEBUG:
            utils.show_extent(
                context=context,
                feedback=feedback,
                extent=utm_extent,
                extent_crs=utm_crs,
                name="DEBUG UTM extent",
                style="Extent layer style.qml",
            )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Create UTM sampling grid

        feedback.setProgressText("\nCreate UTM sampling grid...")
        t0 = time.time()
        alg_params = {
            "CRS": utm_crs,
            "EXTENT": utm_extent,
            "TYPE": 0,  # Point
            "HSPACING": pixel_size,
            "VSPACING": pixel_size,
            "HOVERLAY": 0.0,
            "VOVERLAY": 0.0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["UtmGrid"] = processing.run(
            "native:creategrid",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        utm_grid_layer = context.getMapLayer(outputs["UtmGrid"]["OUTPUT"])
        if utm_grid_layer.featureCount() < 9:
            msg = f"Too few features in sampling layer ({utm_grid_layer.featureCount()}), cannot proceed.\n"
            raise QgsProcessingException(msg)
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Calc utm_idem_extent, the extent for the interpolated DEM
        # The interpolated DEM pixels are centered on the sampling grid points
        #
        # ·---·---·---· interpolated DEM pixels
        # | * | * | * | sampling grid points
        # ·---·---·---·
        # | * | * | * |
        # ·---·---·---·

        e = 2e-6  # used to nudge the gdal:gridinversedistancenearestneighbor algo
        utm_idem_extent = utm_extent.buffered(pixel_size / 2.0 - e)

        if DEBUG:
            utils.show_extent(
                context=context,
                feedback=feedback,
                extent=utm_idem_extent,
                extent_crs=utm_crs,
                name="DEBUG UTM DEM extent",
                style="Extent layer style.qml",
            )

        # Clip, reproject, and interpolate the DEM

        dem_layer = DEMLayerParam.get(**kwargs, extent=utm_extent, extent_crs=utm_crs)

        feedback.setProgressText("\nClip, reproject, and interpolate the DEM...")
        t0 = time.time()
        alg_params = {
            "INPUT": dem_layer,
            "SOURCE_CRS": dem_layer.crs(),
            "TARGET_CRS": utm_crs,
            "RESAMPLING": 1,
            "NODATA": None,
            "TARGET_RESOLUTION": pixel_size,
            "OPTIONS": "",
            "DATA_TYPE": 0,
            "TARGET_EXTENT": utm_idem_extent,
            "TARGET_EXTENT_CRS": utm_crs,
            "MULTITHREADING": False,
            "EXTRA": "",
            "OUTPUT": DEBUG
            and parameters["UtmInterpolatedDemLayer"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["Interpolation"] = processing.run(
            "gdal:warpreproject",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Sample Z values from interpolated DEM raster layer

        feedback.setProgressText(
            "\nSample Z values from interpolated DEM raster layer..."
        )
        t0 = time.time()
        alg_params = {
            "BAND": 1,
            "INPUT": outputs["UtmGrid"]["OUTPUT"],
            "NODATA": -999,
            "OFFSET": 0,
            "RASTER": outputs["Interpolation"]["OUTPUT"],
            "SCALE": 1,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["SetZFromDem"] = processing.run(
            "native:setzfromraster",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Sample landuse values from landuse layer
        # The new data column name is bc1

        landuse_layer = LanduseLayerParam.get(
            **kwargs, extent=utm_extent, extent_crs=utm_crs
        )
        landuse_type_filepath = LanduseTypeFilepathParam.get(**kwargs)

        if landuse_layer:
            feedback.setProgressText("\nSample landuse values from landuse layer...")
            t0 = time.time()

            # Check landuse type exists

            if not landuse_type_filepath:
                msg = f"Landuse type not available, cannot proceed."
                raise QgsProcessingException(msg)

            # Sample
            alg_params = {
                "COLUMN_PREFIX": "bc",  # creates the bc1 field from landuse
                "INPUT": outputs["SetZFromDem"]["OUTPUT"],
                "RASTERCOPY": landuse_layer,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["SampleRasterValues"] = processing.run(
                "native:rastersampling",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            sampling_layer = context.getMapLayer(
                outputs["SampleRasterValues"]["OUTPUT"]
            )
            feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
        else:
            feedback.setProgressText("\nNo landuse layer.")
            sampling_layer = context.getMapLayer(outputs["SetZFromDem"]["OUTPUT"])
            with edit(sampling_layer):  # create an empty bc1 field
                attributes = list((QgsField("bc1", QVariant.Int),))
                sampling_layer.dataProvider().addAttributes(attributes)
                sampling_layer.updateFields()

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        if DEBUG:
            utils.show_layer(
                context=context,
                feedback=feedback,
                layer=sampling_layer,
                name="DEBUG Sampling layer",
            )

        # Get landuse type
        # (we need landuse_type.bc_out_default and .bc_in_default)

        landuse_type = LanduseType(
            feedback=feedback,
            project_path=fds_path,  # project_path,
            filepath=landuse_type_filepath,
        )

        # Get UTM fire layer and buffered UTM fire layer
        # and sample bc values from them

        utm_fire_layer, utm_b_fire_layer = None, None
        if fire_layer:
            feedback.setProgressText("\nGet UTM fire layer...")
            t0 = time.time()
            # Reproject fire layer to UTM
            alg_params = {
                "INPUT": fire_layer,
                "TARGET_CRS": utm_crs,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["UTMFireLayer"] = processing.run(
                "native:reprojectlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            utm_fire_layer = context.getMapLayer(outputs["UTMFireLayer"]["OUTPUT"])
            # Buffer UTM fire layer
            alg_params = {
                "INPUT": utm_fire_layer,
                "DISTANCE": pixel_size,
                "SEGMENTS": 5,
                "END_CAP_STYLE": 0,
                "JOIN_STYLE": 0,
                "MITER_LIMIT": 2,
                "DISSOLVE": False,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["UTMBufferedFireLayer"] = processing.run(
                "native:buffer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            utm_b_fire_layer = context.getMapLayer(
                outputs["UTMBufferedFireLayer"]["OUTPUT"]
            )
            # Sample them
            _load_fire_layer_bc(
                parameters=parameters,
                context=context,
                feedback=feedback,
                sampling_layer=sampling_layer,
                fire_layer=utm_b_fire_layer,
                bc_field="bc_out",
                bc_default=landuse_type.bc_out_default,
            )
            _load_fire_layer_bc(
                parameters=parameters,
                context=context,
                feedback=feedback,
                sampling_layer=sampling_layer,
                fire_layer=utm_fire_layer,
                bc_field="bc_in",
                bc_default=landuse_type.bc_in_default,
            )
            feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
        else:
            feedback.setProgressText("\nNo fire layer.")

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Get texture

        texture = Texture(
            feedback=feedback,
            path=fds_path,
            name=chid,
            image_type="png",
            pixel_size=tex_pixel_size,
            tex_layer=None,  # tex_layer, # FIXME remove?
            utm_extent=utm_extent,
            utm_crs=utm_crs,
        )

        # Add empty wind

        wind = Wind(feedback=feedback, project_path=fds_path, filepath=wind_filepath)

        # Prepare terrain, domain, fds_case

        if export_obst:
            Terrain = OBSTTerrain
        else:
            Terrain = GEOMTerrain
        terrain = Terrain(
            feedback=feedback,
            sampling_layer=sampling_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
            fire_layer=fire_layer,
            path=fds_path,
            name=chid,
        )

        if feedback.isCanceled():
            return {}

        # Get cell_size

        cell_size = CellSizeParam.get(**kwargs)
        if not cell_size:
            cell_size = pixel_size

        domain = Domain(
            feedback=feedback,
            utm_crs=utm_crs,
            utm_extent=utm_extent,
            utm_origin=utm_origin,
            wgs84_origin=wgs84_origin,
            min_z=terrain.min_z,
            max_z=terrain.max_z,
            cell_size=cell_size,
            nmesh=nmesh,
        )

        fds_case = FDSCase(
            feedback=feedback,
            path=fds_path,
            name=chid,
            utm_crs=utm_crs,
            wgs84_origin=wgs84_origin,
            pixel_size=pixel_size,
            dem_layer=dem_layer,
            domain=domain,
            terrain=terrain,
            texture=texture,
            wind=wind,
            t_begin=t_begin,
            t_end=t_end,
        )
        fds_case.save()

        feedback.setCurrentStep(6)
        return results  # script end

    def name(self):
        return "Export FDS case"

    def displayName(self):
        return self.name()

    def group(self):
        return self.groupId()

    def groupId(self):
        return ""

    def createInstance(self):
        return qgis2fdsExportAlgo()


# FIXME move elsewhere


def _load_fire_layer_bc(
    parameters, context, feedback, sampling_layer, fire_layer, bc_field, bc_default
):
    """Load fire layer boundary condition from feature field to sampling layer."""
    feedback.pushInfo(
        f"Load fire layer boundary condition (feature field: {bc_field})..."
    )

    # Get bc1 data field index
    output_bc_idx = sampling_layer.dataProvider().fieldNameIndex("bc1")
    if output_bc_idx == -1:
        raise QgsProcessingException("No bc1 data field, cannot proceed.")

    # For all fire layer features
    bc_idx = fire_layer.fields().indexOf(bc_field)
    for fire_feat in fire_layer.getFeatures():
        # Check if user specified per feature bc available
        if bc_idx != -1:
            bc = fire_feat[bc_idx]
        else:
            bc = bc_default
        feedback.pushInfo(f"Set bc {bc} from fire layer feature {fire_feat.id()}...")
        # Set bc in sampling layer
        # for speed, preselect points
        fire_geom = fire_feat.geometry()
        fire_geom_bbox = fire_geom.boundingBox()
        with edit(sampling_layer):
            for f in sampling_layer.getFeatures(QgsFeatureRequest(fire_geom_bbox)):
                g = f.geometry()
                if fire_geom.contains(g):
                    if bc != NULL:
                        sampling_layer.changeAttributeValue(f.id(), output_bc_idx, bc)
