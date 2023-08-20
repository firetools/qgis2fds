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
    QgsCoordinateTransform,
    QgsPoint,
    QgsField,
    NULL,
    edit,
    QgsFeatureRequest,
)
from qgis.PyQt.QtCore import QVariant

import processing
import math, time
from .qgis2fds_params import *
from .types import (
    utils,
    FDSCase,
    Domain,
    OBSTTerrain,
    GEOMTerrain,
    LanduseType,
    Texture,
    Wind,
)

DEBUG = True


class qgis2fdsExportAlgo(QgsProcessingAlgorithm):
    """
    Export to FDS case algorithm.
    """

    def initAlgorithm(self, config=None):
        project = QgsProject.instance()

        # Define parameters

        # Basic
        kwargs = {"algo": self, "config": config, "project": project}
        ChidParam.set(**kwargs)
        FDSPathParam.set(**kwargs)
        ExtentParam.set(**kwargs)
        PixelSizeParam.set(**kwargs)
        OriginParam.set(**kwargs)
        DEMLayerParam.set(**kwargs)
        LanduseLayerParam.set(**kwargs)
        LanduseTypeFilepathParam.set(**kwargs)
        FireLayer.set(**kwargs)
        # Advanced
        TexLayerParam.set(**kwargs)
        TexPixelSizeParam.set(**kwargs)
        NMeshParam.set(**kwargs)
        CellSizeParam.set(**kwargs)
        StartTimeParam.set(**kwargs)
        EndTimeParam.set(**kwargs)
        WindFilepathParam.set(**kwargs)
        TextFilepathParam.set(**kwargs)
        ExportOBSTParam.set(**kwargs)

        # Define destination layers

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                "UtmGrid",
                "UTM sampling grid",
                type=QgsProcessing.TypeVectorPoint,
                optional=True,
            )
        )

        if DEBUG:
            self.addParameter(
                QgsProcessingParameterVectorDestination(
                    "UtmDemPoints",
                    "UTM DEM points",
                    type=QgsProcessing.TypeVectorPoint,
                    optional=True,
                )
            )
            self.addParameter(
                QgsProcessingParameterRasterDestination(
                    "UtmInterpolatedDemLayer",
                    "UTM interpolated DEM layer",
                    optional=True,
                )
            )
            self.addParameter(
                QgsProcessingParameterVectorDestination(
                    "ExtentDebug",
                    "Extent debug",
                    optional=True,
                )
            )

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(8, model_feedback)
        results, outputs, project = {}, {}, QgsProject.instance()

        # Load parameter values

        kwargs = {
            "algo": self,
            "parameters": parameters,
            "context": context,
            "feedback": feedback,
            "project": project,
        }
        chid = ChidParam.get(**kwargs)
        fds_path = FDSPathParam.get(**kwargs)
        extent = ExtentParam.get(**kwargs)  # in project crs
        pixel_size = PixelSizeParam.get(**kwargs)
        origin = OriginParam.get(**kwargs)  # in project crs
        dem_layer = DEMLayerParam.get(**kwargs)
        landuse_layer = LanduseLayerParam.get(**kwargs)
        landuse_type_filepath = LanduseTypeFilepathParam.get(**kwargs)
        fire_layer = FireLayer.get(**kwargs)
        tex_layer = TexLayerParam.get(**kwargs)
        tex_pixel_size = TexPixelSizeParam.get(**kwargs)
        nmesh = NMeshParam.get(**kwargs)
        cell_size = CellSizeParam.get(**kwargs)
        export_obst = ExportOBSTParam.get(**kwargs)
        t_begin = StartTimeParam.get(**kwargs)
        t_end = EndTimeParam.get(**kwargs)
        wind_filepath = WindFilepathParam.get(**kwargs)
        text_filepath = TextFilepathParam.get(**kwargs)

        # Check parameter values

        text = ""
        if not origin:
            origin = QgsPoint(extent.center())  # in project crs
            text += "\nDomain extent centroid used as origin"
        if not landuse_layer or not landuse_type_filepath:
            landuse_layer, landuse_type_filepath = None, None
            text += "\nLanduse not exported"
        if not tex_layer:
            text += "\nCurrent canvas view exported as texture"
        if not tex_pixel_size:
            tex_pixel_size = pixel_size
            text += "\nTerrain resolution used as texture resolution"
        if not cell_size:
            cell_size = pixel_size
            text += "\nTerrain resolution used as FDS MESH cell size"
        feedback.setProgressText(text)

        # Calc wgs84_origin, origin in WGS84 crs

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_origin = origin.clone()
        _tr = QgsCoordinateTransform(project.crs(), wgs84_crs, project)
        wgs84_origin.transform(_tr)
        feedback.setProgressText(f"WGS84 origin: {wgs84_origin}")

        # Calc applicable UTM crs at the origin

        _epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(_epsg)
        feedback.setProgressText(f"Applicable UTM CRS: {utm_crs.authid()}")

        # Calc utm_origin, origin in UTM crs

        utm_origin = wgs84_origin.clone()
        _tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin.transform(_tr)
        feedback.setProgressText(f"UTM origin: {wgs84_origin}")

        # Calc utm_extent, the terrain extent in UTM crs

        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)
        e = 1e-6  # epsilon used to nudge the native:creategrid algo
        w = math.ceil(utm_extent.width() / pixel_size) * pixel_size + e
        h = math.ceil(utm_extent.height() / pixel_size) * pixel_size + e
        x_min, x_max, y_min, y_max = (
            utm_extent.xMinimum(),
            utm_extent.xMaximum(),
            utm_extent.yMinimum(),
            utm_extent.yMaximum(),
        )
        utm_extent.setXMaximum(x_min + w)
        utm_extent.setYMinimum(y_max - h)
        feedback.setProgressText(f"Extent size: {x_max-x_min:.1f}x{y_max-y_min:.1f}m")

        if DEBUG:
            _run_extent_to_layer(
                parameters=parameters,
                context=context,
                feedback=feedback,
                extent=utm_extent,
                extent_crs=utm_crs,
            )

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
            "OUTPUT": DEBUG and parameters["UtmGrid"] or QgsProcessing.TEMPORARY_OUTPUT,
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
            raise QgsProcessingException(
                f"Too few features in sampling layer ({utm_grid_layer.featureCount()}), cannot proceed.\n"
            )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Calc the extent for the interpolated DEM
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
            _run_extent_to_layer(
                parameters=parameters,
                context=context,
                feedback=feedback,
                extent=utm_idem_extent,
                extent_crs=utm_crs,
            )

        # Calc clipping extent of the original DEM in DEM crs,
        # two pixels larger than what is strictly needed
        # to facilitate interpolation

        _tr = QgsCoordinateTransform(utm_crs, dem_layer.crs(), project)
        clipped_dem_extent = _tr.transformBoundingBox(utm_idem_extent)
        dem_resolution = max(
            (
                abs(dem_layer.rasterUnitsPerPixelX()),
                abs(dem_layer.rasterUnitsPerPixelY()),
            )
        )
        clipped_dem_extent.grow(delta=dem_resolution * 2.0)

        if DEBUG:
            _run_extent_to_layer(
                parameters=parameters,
                context=context,
                feedback=feedback,
                extent=clipped_dem_extent,
                extent_crs=dem_layer.crs(),
            )

        # Transform DEM pixels to points

        feedback.setProgressText("\nTransform DEM pixels to points...")
        t0 = time.time()
        alg_params = {
            "FIELD_NAME": "DEM",
            "INPUT_RASTER": dem_layer,
            "RASTER_BAND": 1,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["DemPixelsToPoints"] = processing.run(
            "native:pixelstopoints",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Clip DEM points by requested extent
        # (the previous raster clipping had issues with certain CRSs)
        # Pre-generating the spatial index does not improve the performance here

        feedback.setProgressText("\nClip DEM points by requested extent...")
        t0 = time.time()
        alg_params = {
            "INPUT": outputs["DemPixelsToPoints"]["OUTPUT"],
            "EXTENT": clipped_dem_extent,
            "CLIP": False,
            "OUTPUT": DEBUG
            and parameters["UtmDemPoints"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["DemPixelsToPoints"] = processing.run(
            "native:extractbyextent",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Reproject DEM points to UTM

        feedback.setProgressText("\nReproject DEM points to UTM...")
        t0 = time.time()
        alg_params = {
            "CONVERT_CURVED_GEOMETRIES": False,
            "INPUT": outputs["DemPixelsToPoints"]["OUTPUT"],
            "OPERATION": "",
            "TARGET_CRS": utm_crs,
            "OUTPUT": DEBUG
            and parameters["UtmDemPoints"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["UtmDemPoints"] = processing.run(
            "native:reprojectlayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Interpolate UTM DEM points to DEM raster layer (Grid, IDW with nearest neighbor searching)
        # aligned to UTM sampling grid
        # Pre-generating the spatial index does not improve the performance here

        feedback.setProgressText("\nInterpolate UTM DEM points (IDW)...")
        t0 = time.time()
        e = utm_idem_extent
        extra = f"-txe {e.xMinimum()} {e.xMaximum()} -tye {e.yMinimum()} {e.yMaximum()} -tr {pixel_size} {pixel_size}"
        alg_params = {
            "INPUT": outputs["UtmDemPoints"]["OUTPUT"],
            "Z_FIELD": "DEM",
            "POWER": 2,
            "SMOOTHING": 0,
            "RADIUS": dem_resolution,  # FIXME what if original DEM not metric? here is UTM
            "MAX_POINTS": 4,
            "MIN_POINTS": 1,
            "NODATA": -999,
            "OPTIONS": "",
            "EXTRA": extra,
            "DATA_TYPE": 5,
            "OUTPUT": DEBUG
            and parameters["UtmInterpolatedDemLayer"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["Interpolation"] = processing.run(
            "gdal:gridinversedistancenearestneighbor",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(5)
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
            "OUTPUT": DEBUG and parameters["UtmGrid"] or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["SetZFromDem"] = processing.run(
            "native:setzfromraster",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        feedback.setProgressText(f"time: {time.time()-t0:.1f}s")

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Sample landuse values from landuse layer
        # The new data column name is bc1

        if landuse_layer and landuse_type_filepath:
            feedback.setProgressText("\nSample landuse values from landuse layer...")
            t0 = time.time()
            alg_params = {
                "COLUMN_PREFIX": "bc",  # creates the bc1 field from landuse
                "INPUT": outputs["SetZFromDem"]["OUTPUT"],
                "RASTERCOPY": landuse_layer,
                "OUTPUT": parameters["UtmGrid"],
            }
            outputs["SampleRasterValues"] = processing.run(
                "native:rastersampling",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            # results["UtmGrid"] = outputs["SampleRasterValues"]["OUTPUT"]
            sampling_layer = context.getMapLayer(
                outputs["SampleRasterValues"]["OUTPUT"]
            )
            feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
        else:
            feedback.setProgressText("\nNo landuse layer or type.")
            sampling_layer = context.getMapLayer(outputs["SetZFromDem"]["OUTPUT"])
            with edit(sampling_layer):  # create an empty bc1 field
                attributes = list((QgsField("bc1", QVariant.Int),))
                sampling_layer.dataProvider().addAttributes(attributes)
                sampling_layer.updateFields()

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

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

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Get texture

        texture = Texture(
            feedback=feedback,
            path=fds_path,
            name=chid,
            image_type="png",
            pixel_size=tex_pixel_size,
            tex_layer=tex_layer,
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


def _run_create_spatial_index(parameters, context, feedback, vector_layer):
    """Create spatial index of vector layer to speed up the next process."""
    feedback.setProgressText("\nCreate spatial index...")
    t0 = time.time()
    alg_params = {
        "INPUT": vector_layer,
    }
    output = processing.run(
        "native:createspatialindex",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
    return output


def _run_extent_to_layer(parameters, context, feedback, extent, extent_crs):
    """Show extent as vector layer."""
    x_min, x_max, y_min, y_max = (
        extent.xMinimum(),
        extent.xMaximum(),
        extent.yMinimum(),
        extent.yMaximum(),
    )
    extent_str = f"{x_min}, {x_max}, {y_min}, {y_max} [{extent_crs.authid()}]"
    feedback.setProgressText(f"Extent to layer: {extent_str} ...")
    alg_params = {
        "INPUT": extent_str,
        "OUTPUT": parameters["ExtentDebug"],  # FIXME how to make it unlinked?
    }
    return processing.run(
        "native:extenttolayer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )


def _load_fire_layer_bc(
    parameters, context, feedback, sampling_layer, fire_layer, bc_field, bc_default
):
    """Load fire layer boundary condition from feature field to sampling layer."""
    feedback.pushInfo(
        f"Load fire layer boundary condition (feature field: <{bc_field}>)..."
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
        feedback.pushInfo(
            f"Set bc <{bc}> from fire layer feature <{fire_feat.id()}>..."
        )
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


# # Interpolate UTM DEM points to DEM raster layer (TIN interpolation)
# # aligned to UTM sampling grid
# feedback.setProgressText(
#     "\nInterpolate UTM DEM points to DEM raster layer (TIN)..."
# )
# t0 = time.time()
# utm_dem_layer = outputs["UtmDemPoints"]["OUTPUT"]
# layer_source = context.getMapLayer(utm_dem_layer).source()
# interpolation_source = 0
# field_index = 0
# input_type = 0  # points
# interpolation_data = f"{layer_source}::~::{interpolation_source}::~::{field_index}::~::{input_type}"
# alg_params = {
#     "EXTENT": idem_utm_extent,
#     "INTERPOLATION_DATA": interpolation_data,
#     "METHOD": 0,  # Linear
#     "PIXEL_SIZE": pixel_size,  # interpolated DEM resolution
#     "OUTPUT": DEBUG
#     and parameters["UtmInterpolatedDemLayer"]
#     or QgsProcessing.TEMPORARY_OUTPUT,
# }
# outputs["Interpolation"] = processing.run(
#     "qgis:tininterpolation",
#     alg_params,
#     context=context,
#     feedback=feedback,
#     is_child_algorithm=True,
# )
# feedback.setProgressText(f"time: {time.time()-t0:.1f}s")
