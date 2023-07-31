# -*- coding: utf-8 -*-

"""qgis2fds export algorithm"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterVectorDestination,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPoint,
)
import processing, math
from .qgis2fds_params import *
from . import utilities

DEBUG = True


class qgis2fdsExportAlgo(QgsProcessingAlgorithm):
    """
    Export to FDS case algorithm.
    """

    def initAlgorithm(self, config=None):
        project = QgsProject.instance()

        # Define parameters

        kwargs = {"algo": self, "config": config, "project": project}
        ChidParam.set(**kwargs)
        FDSPathParam.set(**kwargs)
        ExtentParam.set(**kwargs)
        PixelSizeParam.set(**kwargs)
        OriginParam.set(**kwargs)
        DEMLayerParam.set(**kwargs)
        LanduseLayerParam.set(**kwargs)
        LanduseTypeFilepathParam.set(**kwargs)
        TextFilepathParam.set(**kwargs)
        TexLayerParam.set(**kwargs)
        TexPixelSizeParam.set(**kwargs)
        NMeshParam.set(**kwargs)
        CellSizeParam.set(**kwargs)
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
                QgsProcessingParameterRasterDestination(
                    "ClippedDemLayer",
                    "Clipped DEM layer",
                    optional=True,
                )
            )
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
        feedback = QgsProcessingMultiStepFeedback(9, model_feedback)  # FIXME
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
        text_filepath = TextFilepathParam.get(**kwargs)
        tex_layer = TexLayerParam.get(**kwargs)
        tex_pixel_size = TexPixelSizeParam.get(**kwargs)
        nmesh = NMeshParam.get(**kwargs)
        cell_size = CellSizeParam.get(**kwargs)
        export_obst = ExportOBSTParam.get(**kwargs)

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

        # Calc wgs84_origin, applicable UTM crs, utm_origin

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        prj_to_wgs84_tr = QgsCoordinateTransform(project.crs(), wgs84_crs, project)
        wgs84_origin = origin.clone()
        wgs84_origin.transform(prj_to_wgs84_tr)

        utm_epsg = utilities.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        wgs84_to_utm_tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin = wgs84_origin.clone()  # FIXME better way?
        utm_origin.transform(wgs84_to_utm_tr)

        # Calc utm_extent, adjust dimensions as pixel_size multiples

        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)

        w = math.ceil(utm_extent.width() / pixel_size) * pixel_size + 0.000001
        h = math.ceil(utm_extent.height() / pixel_size) * pixel_size + 0.000001
        utm_extent.setXMaximum(utm_extent.xMinimum() + w)
        utm_extent.setYMinimum(utm_extent.yMaximum() - h)

        text = f"\nUTM CRS: {utm_crs.authid()}"
        text += f"\nWGS84 origin: {wgs84_origin}"
        text += f"\nUTM origin: {utm_origin}"
        text += f"\nUTM extent: {utm_extent}, size: {utm_extent.xMaximum()-utm_extent.xMinimum()}x{utm_extent.yMaximum()-utm_extent.yMinimum()}m"
        feedback.setProgressText(text)

        # Calc the interpolated DEM extent in UTM crs
        # so that the interpolation is aligned to the sampling grid

        idem_utm_extent = utm_extent.buffered(pixel_size / 2.0 - 0.000002)

        # Calc clipping extent of the original DEM in DEM crs
        # so that it is enough for interpolation

        utm_to_dem_tr = QgsCoordinateTransform(utm_crs, dem_layer.crs(), project)
        clipped_dem_extent = utm_to_dem_tr.transformBoundingBox(idem_utm_extent)
        rx = abs(dem_layer.rasterUnitsPerPixelX())
        ry = abs(dem_layer.rasterUnitsPerPixelY())
        delta = max((rx, ry)) * 2.0  # cover if larger dem resolution
        clipped_dem_extent.grow(delta=delta)

        text = f"\nidem_utm_extent: {idem_utm_extent}"
        text += f"\nclipped_dem_extent: {clipped_dem_extent}"
        feedback.setProgressText(text)

        self._show_extent(  # FIXME
            e=utm_extent,
            c=utm_crs,
            parameters=parameters,
            outputs=outputs,
            context=context,
            feedback=feedback,
        )

        self._show_extent(  # FIXME
            e=idem_utm_extent,
            c=utm_crs,
            parameters=parameters,
            outputs=outputs,
            context=context,
            feedback=feedback,
        )

        self._show_extent(  # FIXME
            e=clipped_dem_extent,
            c=dem_layer.crs(),
            parameters=parameters,
            outputs=outputs,
            context=context,
            feedback=feedback,
        )

        # Geographic transformations

        # Create UTM sampling grid
        spacing = pixel_size
        alg_params = {
            "CRS": utm_crs,
            "EXTENT": utm_extent,
            "TYPE": 0,  # Point
            "HSPACING": spacing,
            "VSPACING": spacing,
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

        # Check UTM sampling grid
        utm_grid_layer = context.getMapLayer(outputs["UtmGrid"]["OUTPUT"])
        if utm_grid_layer.featureCount() < 9:
            raise QgsProcessingException(
                f"Too few features in sampling layer ({utm_grid_layer.featureCount()}), cannot proceed.\n"
            )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Clip DEM by needed extent
        alg_params = {
            "DATA_TYPE": 0,  # use input layer data type
            "EXTRA": "",
            "INPUT": dem_layer,  # in PROJWIN crs
            "NODATA": -999.0,
            "OPTIONS": "",
            "OVERCRS": True,
            "PROJWIN": clipped_dem_extent,
            "OUTPUT": DEBUG
            and parameters["ClippedDemLayer"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["ClippedDemLayer"] = processing.run(
            "gdal:cliprasterbyextent",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Transform clipped DEM pixels to points
        alg_params = {
            "FIELD_NAME": "DEM",
            "INPUT_RASTER": outputs["ClippedDemLayer"]["OUTPUT"],
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

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Reproject DEM points to UTM
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

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Interpolate UTM DEM points to DEM raster layer
        # aligned to UTM sampling grid
        utm_dem_layer = outputs["UtmDemPoints"]["OUTPUT"]
        layer_source = context.getMapLayer(utm_dem_layer).source()
        interpolation_source = 0
        field_index = 0
        input_type = 0  # points
        interpolation_data = f"{layer_source}::~::{interpolation_source}::~::{field_index}::~::{input_type}"
        alg_params = {
            "EXTENT": idem_utm_extent,
            "INTERPOLATION_DATA": interpolation_data,
            "METHOD": 0,  # Linear
            "PIXEL_SIZE": pixel_size,  # interpolated DEM resolution
            "OUTPUT": DEBUG
            and parameters["UtmInterpolatedDemLayer"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["TinInterpolation"] = processing.run(
            "qgis:tininterpolation",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Sample Z values from interpolated DEM raster layer
        alg_params = {
            "BAND": 1,
            "INPUT": outputs["UtmGrid"]["OUTPUT"],
            "NODATA": -999,
            "OFFSET": 0,
            "RASTER": outputs["TinInterpolation"]["OUTPUT"],
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

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Sample landuse values from landuse layer
        if landuse_layer and landuse_type_filepath:
            alg_params = {
                "COLUMN_PREFIX": "landuse",
                "INPUT": outputs["SetZFromDem"]["OUTPUT"],
                "RASTERCOPY": landuse_layer,
                "OUTPUT": parameters[
                    "UtmGrid"
                ],  # FIXME DEBUG and parameters["UtmGrid"] or QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["SampleRasterValues"] = processing.run(
                "native:rastersampling",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            # results["UtmGrid"] = outputs["SampleRasterValues"]["OUTPUT"]

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        return results  # script end

        # Prepare terrain, domain, fds_case

        if export_obst:
            Terrain = OBSTTerrain
        else:
            Terrain = GEOMTerrain
        terrain = Terrain(
            feedback=feedback,
            sampling_layer=utm_grid_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
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

    def _show_extent(self, e, c, parameters, outputs, context, feedback):
        # Show debug utm_extent FIXME
        extent_str = f"{e.xMinimum()}, {e.xMaximum()}, {e.yMinimum()}, {e.yMaximum()} [{c.authid()}]"
        alg_params = {
            "INPUT": extent_str,
            "OUTPUT": DEBUG
            and parameters["ExtentDebug"]
            or QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["ExtentDebug"] = processing.run(
            "native:extenttolayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        text = f"\nextent: {extent_str}"
        feedback.setProgressText(text)
