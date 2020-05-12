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
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorLayer,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterExtent,
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
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent("extent", "Terrain Extent", defaultValue=None,)
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "dem_layer", "DEM Layer", defaultValue=None,
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
                "Domain Origin (if not set, use Terrain Extent centroid)",
                optional=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "fire_origin",
                "Fire Origin (if not set, use Domain Origin)",
                optional=True,
                defaultValue=None,
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
        feedback = QgsProcessingMultiStepFeedback(8, model_feedback)
        results = {}
        outputs = {}

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Starting...")

        # Get some parameters
        chid = self.parameterAsString(parameters, "chid", context)
        path = self.parameterAsFile(parameters, "path", context)
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)

        # origin and fire_origin are in project_crs
        origin = self.parameterAsPoint(parameters, "origin", context)
        fire_origin = self.parameterAsPoint(parameters, "fire_origin", context)

        # layers in their respective crs
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        landuse_layer = self.parameterAsRasterLayer(
            parameters, "landuse_layer", context
        )

        # Prepare CRS and their transformations
        project_crs = QgsProject.instance().crs()
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dem_crs = dem_layer.crs()

        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )

        # Get extent in WGS84 CRS
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )

        # Get origin in WGS84 CRS
        if parameters["origin"] is not None:
            wgs84_origin = QgsPoint(origin.x(), origin.y())
            wgs84_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User origin: <{wgs84_origin}> WGS84")
        else:
            wgs84_origin = QgsPoint(
                (wgs84_extent.xMinimum() + wgs84_extent.xMaximum()) / 2.0,
                (wgs84_extent.yMinimum() + wgs84_extent.yMaximum()) / 2.0,
            )
            feedback.pushInfo(
                f"Origin at Terrain Extent centroid: <{wgs84_origin}> WGS84"
            )

        # Get fire origin in WGS84 CRS
        if parameters["fire_origin"] is not None:
            wgs84_fire_origin = QgsPoint(fire_origin.x(), fire_origin.y())
            wgs84_fire_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User fire origin: <{wgs84_fire_origin}> WGS84")
        else:
            wgs84_fire_origin = QgsPoint(origin.x(), origin.y())
            feedback.pushInfo(f"Fire origin at origin: <{wgs84_fire_origin}> WGS84")

        # Get UTM CRS from origin
        utm_epsg = utils.lonlat_to_epsg(lon=origin.x(), lat=origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        feedback.pushInfo(f"Optimal UTM CRS: <{utm_crs.description()}>")

        # Get extent in UTM CRS and DEM CRS
        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs,)
        dem_extent = self.parameterAsExtent(parameters, "extent", context, crs=dem_crs)

        # Get origin in UTM CRS
        wgs84_to_utm_tr = QgsCoordinateTransform(
            wgs84_crs, utm_crs, QgsProject.instance()
        )
        utm_origin = QgsPoint(origin.x(), origin.y())
        utm_origin.transform(wgs84_to_utm_tr)

        if utm_origin == wgs84_origin:  # check for QGIS bug
            raise QgsProcessingException(
                f"QGIS bug: UTM Origin <{utm_origin} and WGS84 Origin <{wgs84_origin}> cannot be the same!"
            )

        # Get fire origin in UTM CRS
        utm_fire_origin = QgsPoint(fire_origin.x(), fire_origin.y())
        utm_fire_origin.transform(wgs84_to_utm_tr)

        # Save texture

        feedback.pushInfo("Saving texture image...")

        utils.write_image(
            destination_crs=utm_crs,
            extent=utm_extent,
            filepath=f"{path}/{chid}_texture.png",
            imagetype="png",
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Creating sampling grid in DEM crs

        feedback.pushInfo("Creating sampling grid layer from DEM...")

        xspacing = dem_layer.rasterUnitsPerPixelX()
        yspacing = dem_layer.rasterUnitsPerPixelY()
        x0, y0, x1, y1 = (  # terrain extent in DEM CRS
            dem_extent.xMinimum(),
            dem_extent.yMinimum(),
            dem_extent.xMaximum(),
            dem_extent.yMaximum(),
        )
        xd0, yd1 = (  # DEM extent in DEM CRS
            dem_layer.extent().xMinimum(),
            dem_layer.extent().yMaximum(),
        )
        # align terrain extent to DEM grid (gridding starts from top left corner)
        x0 = xd0 + round((x0 - xd0) / xspacing) * xspacing + xspacing / 2.0
        y1 = yd1 + round((y1 - yd1) / yspacing) * yspacing - yspacing / 2.0
        dem_extent = QgsRectangle(x0, y0, x1, y1)  # terrain extent in DEM CRS

        alg_params = {
            "CRS": dem_crs,
            "EXTENT": dem_extent,
            "HOVERLAY": 0,
            "HSPACING": xspacing,
            "TYPE": 0,  # Points
            "VOVERLAY": 0,
            "VSPACING": yspacing,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["CreateGrid"] = processing.run(
            "native:creategrid",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Draping Z values to sampling grid in DEM crs

        feedback.pushInfo("Set Z values from DEM...")
        alg_params = {
            "BAND": 1,
            "INPUT": outputs["CreateGrid"]["OUTPUT"],
            "NODATA": 0,
            "RASTER": dem_layer,
            "SCALE": 1,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["DrapeSetZValueFromRaster"] = processing.run(
            "native:setzfromraster",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Reprojecting sampling grid to UTM CRS

        feedback.pushInfo("Reprojecting sampling grid layer to UTM CRS...")
        alg_params = {
            "INPUT": outputs["DrapeSetZValueFromRaster"]["OUTPUT"],
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

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Adding geom attributes (x, y, z) to sampling grid in UTM CRS

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

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Sampling landuse layer with sampling grid in UTM CRS

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

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Prepare geometry

        feedback.pushInfo("Building lists of vertices and faces with landuses...")

        point_layer = context.getMapLayer(outputs["sampling_layer"]["OUTPUT"])
        verts, faces, landuses, landuses_set = geometry.get_geometry(
            layer=point_layer, utm_origin=utm_origin,
        )

        feedback.setCurrentStep(8)
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
