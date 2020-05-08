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
    QgsProcessingException,
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
                "Final",
                "Final",
                type=QgsProcessing.TypeVectorPoint,
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
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        # Check DEM layer
        dem_layer = self.parameterAsRasterLayer(parameters, "DEM", context)
        if dem_layer.providerType() != "gdal":
            raise QgsProcessingException(f"Bad DEM type: <{dem_layer.providerType()}>")

        # DEM raster pixels to points
        feedback.pushInfo("Creating grid of points from DEM")
        alg_params = {
            "FIELD_NAME": "zcoord",
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

        # Add x, y geometry attributes
        alg_params = {
            "CALC_METHOD": 1,  # Project CRS
            "INPUT": outputs["RasterPixelsToPoints"]["OUTPUT"],
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["AddGeometryAttributes"] = processing.run(
            "qgis:exportaddgeometrycolumns",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Sample raster values
        alg_params = {
            "COLUMN_PREFIX": "landuse",
            "INPUT": outputs["AddGeometryAttributes"]["OUTPUT"],
            "RASTERCOPY": parameters["Landuse"],
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["SampleRasterValues"] = processing.run(
            "qgis:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Prepare points
        point_layer = context.getMapLayer(outputs["SampleRasterValues"]["OUTPUT"])
        features = point_layer.getFeatures()

        # Build the matrix of center faces
        first_point = None
        previous_point = None
        for f in features:
            a = f.attributes()
            current_point = a[1], a[2], a[0], a[3]  # centroid x, y, z, and landuse
            if first_point is None:
                # current_point is the first point of the matrix
                matrix = [[current_point,]]
                first_point = current_point
                continue
            elif previous_point is None:
                # current_point is the second point of the matrix row
                matrix[-1].append(current_point)
                previous_point = current_point
                continue
            # current point is another point, check alignment in 2D
            v1 = (  # first 2D vector
                previous_point[0] - first_point[0],
                previous_point[1] - first_point[1],
            )
            v2 = (  # second 2D vector
                first_point[0] - current_point[0],
                first_point[1] - current_point[1],
            )
            dot = sum((v1[i] * v2[i] for i in range(2)))  # dot product
            if dot < 0.1:
                # current_point is on the same matrix row
                matrix[-1].append(current_point)
                previous_point = current_point
                continue
            # current_point is on the next row
            matrix.append(
                [current_point,]
            )
            first_point = current_point
            previous_point = None

        # Build the VERTS
        # FIXME
        available_points = []
        p00 = matrix[r0][c0]
        p01 = matrix[r0][c1]
        p10 = matrix[r1][c0]
        p11 = matrix[r1][c1]

        feedback.pushInfo(f"feature count: <{point_layer.featureCount()}>")

        return {}  # results

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
