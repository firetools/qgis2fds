# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import (
    QgsProject,
    QgsPoint,
    QgsRectangle,
    QgsField,
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
    QgsProcessingParameterNumber,
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant

import processing

from . import utils, fds, geometry


class qgis2fdsAlgorithm(QgsProcessingAlgorithm):
    """
    qgis2fds algorithm.
    """

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    def initAlgorithm(self, config=None):
        """!
        Inputs and output of the algorithm
        """
        project = QgsProject.instance()

        # Get project crs, and see if it is ok
        project_crs = project.crs()
        if project_crs == QgsCoordinateReferenceSystem("EPSG:3857"):  # Web Mercator
            QgsProject.instance().setCrs(
                QgsCoordinateReferenceSystem("EPSG:4326")
            )  # WGS84

        # Check if project crs changed
        prev_project_crs_desc, _ = project.readEntry("qgis2fds", "project_crs", None)
        project_crs_changed = False
        if prev_project_crs_desc != project_crs.description():
            project_crs_changed = True

        defaultValue, _ = project.readEntry("qgis2fds", "chid", "terrain")
        self.addParameter(
            QgsProcessingParameterString(
                "chid",
                "FDS Case identificator (CHID)",
                multiLine=False,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry(
            "qgis2fds", "path", QgsProject.instance().readPath("./")
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "path",
                "Save in folder",
                behavior=QgsProcessingParameterFile.Folder,
                fileFilter="All files (*.*)",
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "extent", None)
        self.addParameter(
            QgsProcessingParameterExtent(
                "extent", "Terrain Extent", defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "dem_layer", None)
        if not defaultValue:
            try:  # first layer name containing "dem"
                defaultValue = [
                    layer.name()
                    for layer in QgsProject.instance().mapLayers().values()
                    if "DEM" in layer.name() or "dem" in layer.name()
                ][0]
            except IndexError:
                pass
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "dem_layer", "DEM Layer", defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "dem_sampling", "1")
        self.addParameter(
            QgsProcessingParameterNumber(
                "dem_sampling",
                "DEM Layer sampling rate",
                defaultValue=defaultValue,
                minValue=1,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "landuse_layer", None)
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse_layer",
                "Landuse Layer (if not set, landuse is not exported)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readNumEntry("qgis2fds", "landuse_type", 0)
        self.addParameter(
            QgsProcessingParameterEnum(
                "landuse_type",
                "Landuse Layer Type",
                options=fds.landuse_types,
                allowMultiple=False,
                defaultValue=defaultValue,
            )
        )

        if project_crs_changed:
            defaultValue = None
        else:
            defaultValue, _ = project.readEntry("qgis2fds", "origin", None)
        self.addParameter(
            QgsProcessingParameterPoint(
                "origin",
                "Domain Origin (if not set, use Terrain Extent centroid)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        if project_crs_changed:
            defaultValue = None
        else:
            defaultValue, _ = project.readEntry("qgis2fds", "fire_origin", None)
        self.addParameter(
            QgsProcessingParameterPoint(
                "fire_origin",
                "Fire Origin (if not set, use Domain Origin)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "tex_layer", None)
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "tex_layer",
                "Texture Layer (if not set, current view is exported)",
                optional=True,
                defaultValue=defaultValue,
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
        project = QgsProject.instance()

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Starting...")

        # Get some parameters
        chid = self.parameterAsString(parameters, "chid", context)
        project.writeEntry("qgis2fds", "chid", parameters["chid"])
        path = self.parameterAsFile(parameters, "path", context)
        project.writeEntry("qgis2fds", "path", parameters["path"])
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)
        project.writeEntry("qgis2fds", "landuse_type", parameters["landuse_type"])
        dem_sampling = self.parameterAsInt(parameters, "dem_sampling", context)
        project.writeEntry("qgis2fds", "dem_sampling", parameters["dem_sampling"])

        # Get layers in their respective crs
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        project.writeEntry("qgis2fds", "dem_layer", parameters["dem_layer"])
        if not parameters["landuse_layer"]:  # it is optional
            landuse_layer = None
        else:
            landuse_layer = self.parameterAsRasterLayer(
                parameters, "landuse_layer", context
            )
        project.writeEntry("qgis2fds", "landuse_layer", parameters["landuse_layer"])
        if not parameters["tex_layer"]:  # it is optional
            tex_layer = None
        else:
            tex_layer = self.parameterAsRasterLayer(parameters, "tex_layer", context)
        project.writeEntry("qgis2fds", "tex_layer", parameters["tex_layer"])

        # Prepare CRS and their transformations
        project_crs = QgsProject.instance().crs()
        project.writeEntry(
            "qgis2fds", "project_crs", project_crs.description()
        )  # save to check if changed
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dem_crs = dem_layer.crs()

        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )

        # Get extent in WGS84 CRS
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )
        project.writeEntry("qgis2fds", "extent", parameters["extent"])

        # Get origin in WGS84 CRS
        if parameters["origin"] is not None:
            wgs84_origin = QgsPoint(
                self.parameterAsPoint(parameters, "origin", context)
            )
            wgs84_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"Using user origin: <{wgs84_origin}> WGS84")
        else:
            wgs84_origin = QgsPoint(
                (wgs84_extent.xMinimum() + wgs84_extent.xMaximum()) / 2.0,
                (wgs84_extent.yMinimum() + wgs84_extent.yMaximum()) / 2.0,
            )
            feedback.pushInfo(
                f"Using terrain extent centroid as origin: <{wgs84_origin}> WGS84"
            )
        project.writeEntry("qgis2fds", "origin", parameters["origin"])

        # Get fire origin in WGS84 CRS
        if parameters["fire_origin"] is not None:
            wgs84_fire_origin = QgsPoint(
                self.parameterAsPoint(parameters, "fire_origin", context)
            )
            wgs84_fire_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"Using user fire origin: <{wgs84_fire_origin}> WGS84")
        else:
            wgs84_fire_origin = QgsPoint(wgs84_origin.x(), wgs84_origin.y())
            feedback.pushInfo(
                f"Using origin as fire origin: <{wgs84_fire_origin}> WGS84"
            )
        project.writeEntry("qgis2fds", "fire_origin", parameters["fire_origin"])

        # Get UTM CRS from origin
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        feedback.pushInfo(f"Using UTM CRS: <{utm_crs.description()}>")

        # Get extent in UTM CRS and DEM CRS
        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs,)
        dem_extent = self.parameterAsExtent(parameters, "extent", context, crs=dem_crs)

        # Get origin in UTM CRS
        wgs84_to_utm_tr = QgsCoordinateTransform(
            wgs84_crs, utm_crs, QgsProject.instance()
        )
        utm_origin = QgsPoint(wgs84_origin.x(), wgs84_origin.y())
        utm_origin.transform(wgs84_to_utm_tr)

        if utm_origin == wgs84_origin:  # check for QGIS bug
            raise QgsProcessingException(
                f"QGIS bug: UTM Origin <{utm_origin} and WGS84 Origin <{wgs84_origin}> cannot be the same!"
            )

        # Get fire origin in UTM CRS
        utm_fire_origin = QgsPoint(wgs84_fire_origin.x(), wgs84_fire_origin.y())
        utm_fire_origin.transform(wgs84_to_utm_tr)

        # Save texture

        feedback.pushInfo("Saving texture image...")

        utils.write_image(
            feedback=feedback,
            tex_layer=tex_layer,
            destination_crs=utm_crs,
            destination_extent=utm_extent,
            filepath=f"{path}/{chid}_tex.png",
            imagetype="png",
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations
        # Creating sampling grid in DEM crs

        feedback.pushInfo("Creating sampling grid layer from DEM...")

        xspacing = dem_layer.rasterUnitsPerPixelX() * dem_sampling
        yspacing = dem_layer.rasterUnitsPerPixelY() * dem_sampling
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

        feedback.pushInfo(
            f"Estimated number of vertices: {int((x1-x0)/xspacing * (y1-y0)/xspacing)}"
        )

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

        feedback.pushInfo("Setting Z values from DEM...")
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
            "OUTPUT": landuse_layer
            and QgsProcessing.TEMPORARY_OUTPUT
            or parameters["sampling_layer"],
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
        # Sampling landuse layer with sampling grid in UTM CRS

        if landuse_layer:
            feedback.pushInfo("Sampling landuse...")
            alg_params = {
                "COLUMN_PREFIX": "landuse",
                "INPUT": outputs["ReprojectLayer"]["OUTPUT"],
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
            point_layer = context.getMapLayer(results["sampling_layer"])
        else:
            feedback.pushInfo("No landuse sampling.")
            results["sampling_layer"] = outputs["ReprojectLayer"]["OUTPUT"]
            point_layer = context.getMapLayer(results["sampling_layer"])
            # add fake landuse
            point_layer.dataProvider().addAttributes(
                (QgsField("landuse", QVariant.Int),)
            )
            point_layer.updateFields()

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Prepare geometry

        feedback.pushInfo("Building lists of vertices and faces with landuses...")

        verts, faces, landuses, landuses_set = geometry.get_geometry(
            feedback=feedback, layer=point_layer, utm_origin=utm_origin,
        )

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Write the FDS case file

        feedback.pushInfo("Writing the FDS case file...")

        content = fds.get_case(
            feedback=feedback,
            dem_layer=dem_layer,
            landuse_layer=landuse_layer,
            chid=chid,
            wgs84_origin=wgs84_origin,
            utm_origin=utm_origin,
            wgs84_fire_origin=wgs84_fire_origin,
            utm_fire_origin=utm_fire_origin,
            utm_crs=utm_crs,
            verts=verts,
            faces=faces,
            landuses=landuses,
            landuse_type=landuse_type,
            landuses_set=landuses_set,
            utm_extent=utm_extent,
        )
        utils.write_file(
            feedback=feedback, filepath=f"{path}/{chid}.fds", content=content
        )

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
        return qgis2fdsAlgorithm()
