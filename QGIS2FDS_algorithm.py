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

from qgis.core import (
    QgsProject,
    QgsPoint,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorLayer,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterPoint,
)
import processing

from . import utils, fds, geometry


class QGIS2FDSAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS2FDS algorithm.
    """

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    def initAlgorithm(self, config=None):
        """!
        Inputs and output of the algorithm
        """
        self.addParameter(
            QgsProcessingParameterString(
                "chid",
                "FDS Case identificator (CHID)",
                multiLine=False,
                defaultValue="terrain",
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "path",
                "Save in folder",
                behavior=QgsProcessingParameterFile.Folder,
                fileFilter="All files (*.*)",
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "dem_layer",
                "DEM Layer (also used as extent of terrain)",
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse_layer", "Landuse Layer", defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                "landuse_type",
                "Landuse Layer Type",
                options=fds.landuse_types,
                allowMultiple=False,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "origin",
                "Domain Origin (if not set, use DEM layer centroid)",
                optional=True,
                defaultValue="",
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "fire_origin",
                "Fire Origin (if not set, use Domain Origin)",
                optional=True,
                defaultValue="",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "sampling_layer",
                "Sampling grid output layer",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        """
        Process algorithm.
        """
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        results = {}
        outputs = {}

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Starting...")

        # Get input parameters
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        origin = self.parameterAsPoint(parameters, "origin", context)
        landuse_layer = self.parameterAsRasterLayer(
            parameters, "landuse_layer", context
        )
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)
        fire_origin = self.parameterAsPoint(parameters, "fire_origin", context)
        chid = self.parameterAsString(parameters, "chid", context)
        path = self.parameterAsFile(parameters, "path", context)

        # Check DEM layer type
        if dem_layer.providerType() != "gdal":
            raise QgsProcessingException(
                f"Bad DEM type: <{dem_layer.providerType()}>"
            )  # TODO other sources?

        # Prepare some transformations of CRS
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dem_crs = dem_layer.crs()
        project_crs = QgsProject.instance().crs()

        dem_to_wgs84_tr = QgsCoordinateTransform(
            dem_crs, wgs84_crs, QgsProject.instance()
        )

        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )

        # Get origin in WGS84
        if parameters["origin"] is not None:
            origin = QgsPoint(origin.x(), origin.y())
            origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User origin: <{origin}> WGS84")
        else:
            e = dem_layer.extent()
            origin = QgsPoint(
                (e.xMinimum() + e.xMaximum()) / 2.0,
                (e.yMinimum() + e.yMaximum()) / 2.0,
            )
            origin.transform(dem_to_wgs84_tr)
            feedback.pushInfo(f"Origin at DEM centroid: <{origin}> WGS84")

        # Get UTM CRS from origin
        utm_epsg = utils.lonlat_to_epsg(lon=origin.x(), lat=origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        feedback.pushInfo(f"Optimal UTM CRS: <{utm_crs.description()}>")

        # Get origin in UTM
        wgs84_to_utm_tr = QgsCoordinateTransform(
            wgs84_crs, utm_crs, QgsProject.instance()
        )
        utm_origin = QgsPoint(origin.x(), origin.y())
        utm_origin.transform(wgs84_to_utm_tr)
        feedback.pushInfo(
            f"Origin, UTM: <{utm_origin}, WGS84: <{origin}>"
        )  # FIXME check

        # Get fire origin in WGS84
        if parameters["fire_origin"] is not None:
            fire_origin = QgsPoint(fire_origin.x(), fire_origin.y())
            fire_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User fire origin: <{fire_origin}> WGS84")
        else:
            fire_origin = QgsPoint(origin.x(), origin.y())
            feedback.pushInfo(f"Fire origin at DEM centroid: <{fire_origin}> WGS84")

        # Get fire origin in UTM
        utm_fire_origin = QgsPoint(fire_origin.x(), fire_origin.y())
        utm_fire_origin.transform(wgs84_to_utm_tr)

        # Save texture
        feedback.pushInfo("Saving texture image...")
        utils.write_image(
            destination_crs=utm_crs,
            extent=dem_layer.extent(),
            filepath=f"{path}/{chid}_texture.png",
            imagetype="png",
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations

        feedback.pushInfo("Creating sampling grid layer from DEM...")
        alg_params = {
            "FIELD_NAME": "zcoord",
            "INPUT_RASTER": parameters["dem_layer"],
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

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Reprojecting sampling grid layer to UTM CRS...")
        alg_params = {
            "INPUT": outputs["RasterPixelsToPoints"]["OUTPUT"],
            "TARGET_CRS": utm_crs,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["ReprojectLayer"] = processing.run(
            "native:reprojectlayer",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Adding geometry attributes to sampling grid layer...")
        alg_params = {
            "CALC_METHOD": 0,  # Layer CRS
            "INPUT": outputs["ReprojectLayer"]["OUTPUT"],
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["AddGeometryAttributes"] = processing.run(
            "qgis:exportaddgeometrycolumns",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Sampling landuse...")
        alg_params = {
            "COLUMN_PREFIX": "landuse",
            "INPUT": outputs["AddGeometryAttributes"]["OUTPUT"],
            "RASTERCOPY": parameters["landuse_layer"],
            "OUTPUT": parameters["sampling_layer"],
        }
        outputs["sampling_layer"] = processing.run(
            "qgis:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        results["sampling_layer"] = outputs["sampling_layer"]["OUTPUT"]

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Prepare geometry

        feedback.pushInfo("Building lists of vertices and faces with landuses...")

        point_layer = context.getMapLayer(outputs["sampling_layer"]["OUTPUT"])
        verts, faces, landuses, landuses_set = geometry.get_geometry(
            layer=point_layer, utm_origin=utm_origin,
        )

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Write the FDS case file

        feedback.pushInfo("Writing the FDS case file...")

        content = fds.get_case(
            dem_layer=dem_layer,
            landuse_layer=landuse_layer,
            chid=chid,
            origin=origin,
            utm_origin=utm_origin,
            fire_origin=fire_origin,
            utm_fire_origin=utm_fire_origin,
            utm_crs=utm_crs,
            verts=verts,
            faces=faces,
            landuses=landuses,
            landuse_type=landuse_type,
            landuses_set=landuses_set,
        )
        utils.write_file(filepath=f"{path}/{chid}.fds", content=content)

        return results

    def name(self):
        """!
        Returns the algorithm name.
        """
        return "Export terrain"

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
