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
    QgsProcessingParameterFeatureSink,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPoint,
)
import processing, os
from .qgis2fds_params import *
from . import utilities


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
            QgsProcessingParameterRasterDestination(
                "ClippedDemLayer",
                "Clipped DEM layer",
                createByDefault=False,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "BufferedDomainExtent",
                "Buffered domain extent",
                type=QgsProcessing.TypeVectorPolygon,
                createByDefault=False,
                supportsAppend=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "UtmSamplingGrid",
                "UTM sampling grid",
                type=QgsProcessing.TypeVectorPoint,
                createByDefault=False,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "UtmDemPoints",
                "UTM DEM points",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=False,
                supportsAppend=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                "UtmInterpolatedDemLayer",
                "UTM interpolated DEM layer",
                createByDefault=False,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
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

        # Calc wgs84_origin, applicable UTM crs, utm_origin, utm_extent

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        prj_to_wgs84_tr = QgsCoordinateTransform(project.crs(), wgs84_crs, project)
        wgs84_origin = origin.clone()
        wgs84_origin.transform(prj_to_wgs84_tr)

        utm_epsg = utilities.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        wgs84_to_utm_tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin = wgs84_origin.clone()
        utm_origin.transform(wgs84_to_utm_tr)

        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)
        utm_extent.grow(delta=pixel_size)  # grow for full coverage of extent

        text = f"\nUTM CRS: {utm_crs}"
        text += f"\nWGS84 origin: {wgs84_origin}"
        text += f"\nUTM origin: {utm_origin}"
        text += f"\nUTM extent: {utm_extent}"
        feedback.setProgressText(text)

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
            "OUTPUT": parameters["UtmSamplingGrid"],
        }
        outputs["UtmSamplingGrid"] = processing.run(
            "native:creategrid",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["UtmSamplingGrid"] = outputs["UtmSamplingGrid"]["OUTPUT"]

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Extract UTM sampling grid extent
        alg_params = {
            "INPUT": outputs["UtmSamplingGrid"]["OUTPUT"],
            "ROUND_TO": 0,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["ExtractExtent"] = processing.run(
            "native:polygonfromlayerextent",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Buffer UTM sampling grid extent
        rx = abs(dem_layer.rasterUnitsPerPixelX())
        ry = abs(dem_layer.rasterUnitsPerPixelY())
        distance = max((rx, ry)) * 2.0  # FIXME check meters, not yards!
        # text = f"\nFIXME Buffer distance: <{distance}>, <{parameters['dem_layer']}>, <{dem_layer}>, <{dem_layer.rasterUnitsPerPixelX()}>"
        # feedback.setProgressText(text)

        alg_params = {
            "DISSOLVE": True,
            "DISTANCE": distance,
            "END_CAP_STYLE": 2,  # Square
            "INPUT": outputs["ExtractExtent"]["OUTPUT"],
            "JOIN_STYLE": 2,  # Bevel
            "MITER_LIMIT": 2,
            "SEGMENTS": 1,
            "SEPARATE_DISJOINT": False,
            "OUTPUT": parameters["BufferedDomainExtent"],
        }
        outputs["BufferExtent"] = processing.run(
            "native:buffer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["BufferedDomainExtent"] = outputs["BufferExtent"]["OUTPUT"]

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Clip DEM by buffered extent
        alg_params = {
            "DATA_TYPE": 0,  # Use Input Layer Data Type
            "EXTRA": "",
            "INPUT": dem_layer,
            "NODATA": None,
            "OPTIONS": "",
            "OVERCRS": True,
            "PROJWIN": outputs["BufferExtent"]["OUTPUT"],
            "OUTPUT": parameters["ClippedDemLayer"],
        }
        outputs["ClipDemByBufferedExtent"] = processing.run(
            "gdal:cliprasterbyextent",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["ClippedDemLayer"] = outputs["ClipDemByBufferedExtent"]["OUTPUT"]

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # DEM pixels to points
        alg_params = {
            "FIELD_NAME": "DEM",
            "INPUT_RASTER": outputs["ClipDemByBufferedExtent"]["OUTPUT"],
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
            "OUTPUT": parameters["UtmDemPoints"],
        }
        outputs["ReprojectToUtm"] = processing.run(
            "native:reprojectlayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["UtmDemPoints"] = outputs["ReprojectToUtm"]["OUTPUT"]

        # Interpolate UTM DEM points for denser DEM raster layer
        utm_dem_layer = outputs["ReprojectToUtm"]["OUTPUT"]
        layer_source = context.getMapLayer(utm_dem_layer).source()
        interpolation_source = 0
        field_index = 0
        input_type = 0  # points
        interpolation_data = f"{layer_source}::~::{interpolation_source}::~::{field_index}::~::{input_type}"
        dem_pixel_size = pixel_size / 2.0  # interpolated DEM resolution
        alg_params = {
            "EXTENT": outputs["BufferExtent"]["OUTPUT"],
            "INTERPOLATION_DATA": interpolation_data,
            "METHOD": 0,  # Linear
            "PIXEL_SIZE": dem_pixel_size,
            "OUTPUT": parameters["UtmInterpolatedDemLayer"],
        }
        outputs["TinInterpolation"] = processing.run(
            "qgis:tininterpolation",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["UtmInterpolatedDemLayer"] = outputs["TinInterpolation"]["OUTPUT"]

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Set UTM sampling grid Z from DEM
        alg_params = {
            "BAND": 1,
            "INPUT": outputs["UtmSamplingGrid"]["OUTPUT"],
            "NODATA": -999,
            "OFFSET": 0,
            "RASTER": outputs["TinInterpolation"]["OUTPUT"],
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

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Set UTM sampling grid landuse from landuse layer
        alg_params = {
            "COLUMN_PREFIX": "landuse",
            "INPUT": outputs["SetZFromDem"]["OUTPUT"],
            "RASTERCOPY": landuse_layer,
            "OUTPUT": parameters["UtmSamplingGrid"],
        }
        outputs["SampleRasterValues"] = processing.run(
            "native:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["UtmSamplingGrid"] = outputs["SampleRasterValues"]["OUTPUT"]

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

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
