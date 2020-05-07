# -*- coding: utf-8 -*-

"""
 QGIS2FDS
                                 A QGIS plugin
 Export terrain in NIST FDS notation
                              -------------------
        begin                : 2020-05-04
        copyright            : (C) 2020 by Emanuele Gissi
        email                : emanuele.gissi@gmail.com
"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = "$Format:%H$"

# from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsVectorLayer,
    QgsProcessing,
    # QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    # QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterPoint,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    # QgsProcessingParameterFileDestination,
)
import processing


class QGIS2FDSAlgorithm(QgsProcessingAlgorithm):
    """
    TODO
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    def initAlgorithm(self, config=None):
        """!
        Inputs and output of the algorithm
        """
        self.addParameter(
            QgsProcessingParameterRasterLayer("DEM", "Layer: DEM", defaultValue=None)
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "Landuse", "Layer: Landuse", defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "fdscaseorigin", "FDS origin: point", optional=True, defaultValue=""
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "Result",
                "Result",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
                defaultValue=None,
            )
        )

        # # FDS output file
        # self.addParameter(
        #     QgsProcessingParameterFileDestination(
        #         self.OUTPUT, self.tr("Output File"), "NIST FDS (*.fds)",
        #     )
        # )

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(2, model_feedback)
        results = {}
        outputs = {}

        # Check DEM layer
        # print(parameters["DEM"])
        # print("DEM layer provider type:", parameters["DEM"].providerType())
        dem_layer = self.parameterAsRasterLayer(parameters, "DEM", context)
        feedback.pushInfo(f"DEM: <{dem_layer.providerType()}>")
        if dem_layer.providerType() != "gdal":
            feedback.reportError("Bad DEM type")
            return {}

        # DEM raster pixels to points
        feedback.pushInfo("Creating grid of points from DEM")
        alg_params = {
            "FIELD_NAME": "Z",
            "INPUT_RASTER": parameters["DEM"],
            "RASTER_BAND": 1,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["RasterPixelsToPoints"] = processing.run(
            "native:pixelstopoints",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Sample raster values
        feedback.pushInfo("Sampling landuse to points")
        alg_params = {
            "COLUMN_PREFIX": "landuse",
            "INPUT": outputs["RasterPixelsToPoints"]["OUTPUT"],
            "RASTERCOPY": parameters["Landuse"],
            "OUTPUT": parameters["Result"],
        }
        outputs["SampleRasterValues"] = processing.run(
            "qgis:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )
        results["Result"] = outputs["SampleRasterValues"]["OUTPUT"]
        return results

    def name(self):
        """!
        Returns the algorithm name.
        """
        return "Export terrain to NIST FDS"

    def displayName(self):
        """!
        Returns the translated algorithm name.
        """
        return self.name()

    def group(self):
        """!
        Returns the name of the group this algorithm belongs to.
        """
        return self.groupId()

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to.
        """
        return ""

    def createInstance(self):
        return QGIS2FDSAlgorithm()
