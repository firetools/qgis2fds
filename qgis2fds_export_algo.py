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
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterPoint,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterFeatureSink,
)
import processing, os
from .parameters import *


class qgis2fdsExportAlgo(QgsProcessingAlgorithm):
    """
    Export to FDS case algorithm.
    """

    def initAlgorithm(self, config=None):
        project = QgsProject.instance()

        # Define parameters

        ChidParam.set(algo=self, config=config, project=project)
        FDSPathParam.set(algo=self, config=config, project=project)
        ExtentParam.set(algo=self, config=config, project=project)
        PixelSizeParam.set(algo=self, config=config, project=project)
        OriginParam.set(algo=self, config=config, project=project)
        DEMLayerParam.set(algo=self, config=config, project=project)
        LanduseLayerParam.set(algo=self, config=config, project=project)
        LanduseTypeFilepathParam.set(algo=self, config=config, project=project)
        TextFilepathParam.set(algo=self, config=config, project=project)
        TexLayerParam.set(algo=self, config=config, project=project)
        TexPixelSizeParam.set(algo=self, config=config, project=project)
        NMeshParam.set(algo=self, config=config, project=project)
        CellSizeParam.set(algo=self, config=config, project=project)
        ExportOBSTParam.set(algo=self, config=config, project=project)

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
                "ValuedUtmSamplingGrid",
                "Valued UTM sampling grid",
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

        # Get parameter values

        chid = ChidParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )
        fds_path = FDSPathParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        extent = ExtentParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        pixel_size = PixelSizeParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        origin = OriginParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        dem_layer = DEMLayerParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        landuse_layer = LanduseLayerParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        landuse_type_filepath = LanduseTypeFilepathParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        text_filepath = TextFilepathParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        tex_layer = TexLayerParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        tex_pixel_size = TexPixelSizeParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        nmesh = NMeshParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        cell_size = CellSizeParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        export_obst = ExportOBSTParam.get(
            algo=self,
            parameters=parameters,
            context=context,
            feedback=feedback,
            project=project,
        )

        # Check parameter values

        text = f"\nFIXME chid: <{chid}> fds_path: <{fds_path}> extent: <{extent}> pixel_size: <{pixel_size}>"
        text += f"\nFIXME origin: <{origin}> dem_layer: <{dem_layer}> landuse_layer: <{landuse_layer}> landuse_type_filepath: <{landuse_type_filepath}>"
        text += f"\nFIXME text_filepath: <{text_filepath}> tex_layer: <{tex_layer}> tex_pixel_size: <{tex_pixel_size}> nmesh: <{nmesh}>"
        text += f"\nFIXME cell_size: <{cell_size}> export_obst: <{export_obst}>"

        feedback.setProgressText(text)

        return results  # FIXME script end

        # Create UTM sampling grid
        spacing = parameters["pixel_size"]
        overlay = spacing / 2.0
        alg_params = {
            "CRS": parameters["utm_crs"],
            "EXTENT": parameters["domain_extent"],
            "TYPE": 0,  # Point
            "HSPACING": spacing,
            "VSPACING": spacing,
            "HOVERLAY": overlay,
            "VOVERLAY": overlay,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["CreateUtmSamplingGrid"] = processing.run(
            "native:creategrid",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Extract UTM sampling grid extent
        alg_params = {
            "INPUT": outputs["CreateUtmSamplingGrid"]["OUTPUT"],
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
        dem_layer = self.parameterAsRasterLayer(
            parameters, "dem_layer", context
        )  # FIXME anticipate
        distance = (
            max(
                (
                    abs(dem_layer.rasterUnitsPerPixelX()),
                    abs(dem_layer.rasterUnitsPerPixelY()),
                )
            )
            * 2.0
        )  # FIXME check meters, not yards
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
            "INPUT": parameters["dem_layer"],
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
            "TARGET_CRS": parameters["utm_crs"],
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
        # interpolation_data = 'Point?crs=EPSG:32610&field=DEM:double(20,8)&uid={0a7f4ab4-8bac-4e7a-bced-e0dbdbeba9d1}::~::0::~::0::~::0'
        dem_pixel_size = parameters["pixel_size"] / 2.0  # interpolated DEM resolution
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
            "INPUT": outputs["CreateUtmSamplingGrid"]["OUTPUT"],
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
            "RASTERCOPY": parameters["landuse_layer"],
            "OUTPUT": parameters["ValuedUtmSamplingGrid"],
        }
        outputs["SampleRasterValues"] = processing.run(
            "native:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["ValuedUtmSamplingGrid"] = outputs["SampleRasterValues"]["OUTPUT"]

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
