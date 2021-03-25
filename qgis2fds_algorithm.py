# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import (
    QgsProject,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsField,
    QgsDistanceArea,
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
    QgsProcessingParameterDefinition,
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

        # Get project crs
        project_crs = project.crs()

        # Check if project crs changed
        prev_project_crs_desc, _ = project.readEntry("qgis2fds", "project_crs", None)
        project_crs_changed = False
        if prev_project_crs_desc != project_crs.description():
            project_crs_changed = True

        defaultValue, _ = project.readEntry("qgis2fds", "chid", "terrain")
        self.addParameter(
            QgsProcessingParameterString(
                "chid",
                "FDS case identificator (CHID)",
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

        # QGIS issue #37447, solved in QGIS 3.14.1
        defaultValue, _ = project.readEntry("qgis2fds", "extent", None)
        self.addParameter(
            QgsProcessingParameterExtent(
                "extent", "Terrain extent", defaultValue=defaultValue,
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
                "dem_layer", "DEM layer", defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "dem_sampling", "1")
        param = QgsProcessingParameterNumber(
            "dem_sampling",
            "DEM layer sampling factor",
            defaultValue=defaultValue,
            minValue=1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readEntry("qgis2fds", "landuse_layer", None)
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse_layer",
                "Landuse layer (if not set, landuse is not exported)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readNumEntry("qgis2fds", "landuse_type", 0)
        self.addParameter(
            QgsProcessingParameterEnum(
                "landuse_type",
                "Landuse layer type",
                options=fds.landuse_types,
                allowMultiple=False,
                defaultValue=defaultValue,
            )
        )

        if project_crs_changed:
            defaultValue = None
        else:
            defaultValue, _ = project.readEntry("qgis2fds", "origin", None)
        param = QgsProcessingParameterPoint(
            "origin",
            "Domain origin (if not set, use Terrain Extent centroid)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        if project_crs_changed:
            defaultValue = None
        else:
            defaultValue, _ = project.readEntry("qgis2fds", "fire_origin", None)
        param = QgsProcessingParameterPoint(
            "fire_origin",
            "Fire origin (if not set, use Domain Origin)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readEntry("qgis2fds", "tex_layer", None)
        param = QgsProcessingParameterRasterLayer(
            "tex_layer",
            "Texture layer (if not set, current view is exported)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readNumEntry("qgis2fds", "tex_pixel_size", 5)
        param = QgsProcessingParameterNumber(
            "tex_pixel_size",
            "Texture layer pixels size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        param = QgsProcessingParameterFeatureSink(
            "sampling_layer",
            "Sampling grid output layer",
            type=QgsProcessing.TypeVectorAnyGeometry,
            createByDefault=True,
            defaultValue=None,
        )
        self.addParameter(param)
        # param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

    def processAlgorithm(self, parameters, context, model_feedback):
        """
        Process algorithm.
        """
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        results = {}
        outputs = {}
        project = QgsProject.instance()

        # Points:
        #  origin:      user origin point in proj crs
        #  wgs84_origin: origin point in wgs84 crs, used for choosing utm zone
        #  utm_origin:  origin point in utm crs
        #  fire_origin: user fire point in proj crs
        #  wgs84_fire_origin: fire point in wgs84 crs
        #  utm_fire_origin: fire point in utm crs

        # CRSs:
        #  project_crs: project crs
        #  wgs84_crs:  wgs84 crs
        #  utm_crs:  utm crs, calculated from wgs84_origin
        #  dem_crs:  dem crs, used for grid alignment

        # Extents:
        #  extent:      user terrain extent in any crs
        #  mesh_extent: extent to utm crs, used for FDS MESH
        #               as it is always contained in the terrain
        #  dem_extent:  mesh_extent to dem crs, used for grid
        #               alignment with dem raster data
        #  tex_extent:  dem_extent to utm crs, used for texture,
        #               that should be oriented as utm and perfectly
        #               correspond to dem

        # Get some of the parameters
        chid = self.parameterAsString(parameters, "chid", context)
        project.writeEntry("qgis2fds", "chid", parameters["chid"])
        path = self.parameterAsFile(parameters, "path", context)
        project.writeEntry("qgis2fds", "path", parameters["path"])
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)
        project.writeEntry("qgis2fds", "landuse_type", parameters["landuse_type"])
        dem_sampling = self.parameterAsInt(parameters, "dem_sampling", context)
        project.writeEntry("qgis2fds", "dem_sampling", parameters["dem_sampling"])
        extent = self.parameterAsExtent(parameters, "extent", context)  # FIXME crs?
        project.writeEntry("qgis2fds", "extent", parameters["extent"])

        # Get layers in their respective crs: dem_layer, landuse_layer, tex_layer
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

        # Get tex_pixel_size
        tex_pixel_size = self.parameterAsDouble(parameters, "tex_pixel_size", context)
        project.writeEntryDouble(
            "qgis2fds", "tex_pixel_size", parameters["tex_pixel_size"]
        )

        # Prepare CRSs and check their validity
        project_crs = QgsProject.instance().crs()
        project.writeEntry("qgis2fds", "project_crs", project_crs.description())
        if not project_crs.isValid():
            raise QgsProcessingException(f"Project CRS <{project_crs.description()}> is not usable, cannot proceed.")
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        dem_crs = dem_layer.crs()
        if not dem_crs.isValid():
            raise QgsProcessingException(f"DEM layer CRS <{dem_crs.description()}> is not usable, cannot proceed.")

        if landuse_layer:
            landuse_crs = landuse_layer.crs()
            if not landuse_crs.isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{landuse_crs.description()}> is not usable, cannot proceed."
                )

        if tex_layer:
            tex_crs = tex_layer.crs()
            if not tex_crs.isValid():
                raise QgsProcessingException(
                    f"Texture layer CRS <{tex_crs.description()}> is not usable, cannot proceed."
                )

        # Get extent in WGS84 CRS
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )

        # Get origin in WGS84 CRS
        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )
        if parameters["origin"] is not None:
            # preventing a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            origin = self.parameterAsPoint(parameters, "origin", context)
            project.writeEntry("qgis2fds", "origin", parameters["origin"])
            wgs84_origin = QgsPoint(origin.x(), origin.y())
            wgs84_origin.transform(project_to_wgs84_tr)
        else:  # no origin
            wgs84_origin = wgs84_extent.center()
        feedback.pushInfo(f"Domain origin: {wgs84_origin.x():.6f}, {wgs84_origin.y():.6f} (WGS 84)")


        # Get fire origin in WGS84 CRS
        if parameters["fire_origin"] is not None:
            # preventing a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            fire_origin = self.parameterAsPoint(parameters, "fire_origin", context)
            project.writeEntry("qgis2fds", "fire_origin", parameters["fire_origin"])
            wgs84_fire_origin = QgsPoint(fire_origin.x(), fire_origin.y())
            wgs84_fire_origin.transform(project_to_wgs84_tr)
        else:
            wgs84_fire_origin = QgsPoint(wgs84_origin.x(), wgs84_origin.y())
        feedback.pushInfo(f"Fire origin: {wgs84_fire_origin.x():.6f}, {wgs84_fire_origin.y():.6f} (WGS 84)")

        # Calc UTM CRS from wgs84_origin
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        # Feedback on CRSs
        feedback.pushInfo(f"\nProject CRS: <{project_crs.description()}>")
        feedback.pushInfo(f"DEM layer CRS: <{dem_crs.description()}>")
        feedback.pushInfo(f"Landuse layer CRS: <{landuse_layer and landuse_crs.description() or 'no landuse'}>")
        feedback.pushInfo(f"Texture layer CRS: <{tex_layer and tex_crs.description() or 'no texture'}>")
        feedback.pushInfo(f"FDS CRS: <{utm_crs.description()}>")

        # Get origin in UTM CRS
        wgs84_to_utm_tr = QgsCoordinateTransform(
            wgs84_crs, utm_crs, QgsProject.instance()
        )
        utm_origin = QgsPoint(wgs84_origin.x(), wgs84_origin.y())
        utm_origin.transform(wgs84_to_utm_tr)

        # Check for QGIS bug
        if utm_origin == wgs84_origin:
            raise QgsProcessingException(
                f"[QGIS bug] UTM Origin <{utm_origin}> and WGS84 Origin <{wgs84_origin}> are identical, cannot proceed.\n{wgs84_to_utm_tr}\n{wgs84_crs} {utm_crs}"
            )

        # Get fire origin in UTM CRS
        utm_fire_origin = QgsPoint(wgs84_fire_origin.x(), wgs84_fire_origin.y())
        utm_fire_origin.transform(wgs84_to_utm_tr)

        # Get FDS MESH extent in UTM CRS, then obtain dem extent in DEM CRS
        mesh_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=utm_crs,
        )
        utm_to_dem_tr = QgsCoordinateTransform(utm_crs, dem_crs, QgsProject.instance())
        dem_extent = utm_to_dem_tr.transformBoundingBox(mesh_extent)

        # Check DEM contains dem_extent
        if not dem_layer.extent().contains(dem_extent):
            feedback.reportError("Terrain extent is larger than DEM data, unknown elevations will be set to zero.")

        # Extent and grid calculations
        # align terrain extent to DEM grid (gridding starts from top left corner)
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
        xspacing = dem_layer.rasterUnitsPerPixelX()
        yspacing = dem_layer.rasterUnitsPerPixelY()
        x0 = xd0 + round((x0 - xd0) / xspacing) * xspacing + xspacing / 2.0
        y1 = yd1 + round((y1 - yd1) / yspacing) * yspacing - yspacing / 2.0
        dem_extent = QgsRectangle(x0, y0, x1, y1)  # updated terrain extent in DEM CRS
        xspacing *= dem_sampling  # reduce sampling, if requested
        yspacing *= dem_sampling
        npoints = int((x1 - x0) / xspacing * (y1 - y0) / yspacing)  # sampling points
        if npoints < 9:
            raise QgsProcessingException(
                f"Too few sampling points <{npoints}>, cannot proceed."
            )

        # Get texture extent and its size in meters
        dem_to_utm_tr = QgsCoordinateTransform(dem_crs, utm_crs, QgsProject.instance())
        tex_extent = dem_to_utm_tr.transformBoundingBox(dem_extent)

        d = QgsDistanceArea()
        d.setSourceCrs(
            crs=utm_crs, context=QgsProject.instance().transformContext()
        )
        p00, p10, p01 = (
            QgsPointXY(tex_extent.xMinimum(), tex_extent.yMinimum()),
            QgsPointXY(tex_extent.xMaximum(), tex_extent.yMinimum()),
            QgsPointXY(tex_extent.xMinimum(), tex_extent.yMaximum()),
        )
        tex_extent_wm = d.measureLine(p00, p10)  # euclidean dist, extent width in m
        tex_extent_hm = d.measureLine(p00, p01)  # euclidean dist, extent height in m

        # Feedback
        feedback.pushInfo(f"\nTerrain size: {tex_extent_wm:.1f} x {tex_extent_hm:.1f} meters")
        feedback.pushInfo(f"Sampling resolution: {xspacing:.1f} x {yspacing:.1f} meters")
        feedback.pushInfo(f"Generated faces: {npoints*2}")

        feedback.pushInfo(f"\nPush <Cancel> to interrupt execution.")

        # QGIS geographic transformations
        # Creating sampling grid in DEM crs

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nCreating sampling grid layer from DEM...")

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

        # Save texture

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nRendering and saving texture image, timeout in 30s...")

        utils.write_image(
            feedback=feedback,
            tex_layer=tex_layer,
            tex_pixel_size=tex_pixel_size,  # pixel size in meters
            tex_extent_wm=tex_extent_wm,  # texture width in m
            tex_extent_hm=tex_extent_hm,  # texture height in m
            destination_crs=utm_crs,  # using UTM crs, texture aligned to axis in Smokeview
            destination_extent=tex_extent,
            filepath=f"{path}/{chid}_tex.png",
            imagetype="png",
        )

        # QGIS geographic transformations
        # Draping Z values to sampling grid in DEM crs

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nDraping Z values from DEM (takes time!)...")

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

        # QGIS geographic transformations
        # Reprojecting sampling grid to UTM CRS

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nReprojecting sampling grid layer to UTM CRS...")

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

        # QGIS geographic transformations
        # Sampling landuse layer with sampling grid in UTM CRS

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nSampling landuse (takes time!)...")

        if landuse_layer:
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
            feedback.pushInfo("No landuse layer provided, no sampling.")
            results["sampling_layer"] = outputs["ReprojectLayer"]["OUTPUT"]
            point_layer = context.getMapLayer(results["sampling_layer"])
            # add fake landuse
            point_layer.dataProvider().addAttributes(
                (QgsField("landuse", QVariant.Int),)
            )
            point_layer.updateFields()

        # Prepare geometry

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nBuilding FDS geometry...")

        verts, faces, landuses = geometry.get_geometry(
            feedback=feedback, layer=point_layer, utm_origin=utm_origin,
        )

        # Write the FDS case file

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\nWriting the FDS case file...")

        fds.write_case(
            feedback=feedback,
            dem_layer=dem_layer,
            landuse_layer=landuse_layer,
            path=path,
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
            mesh_extent=mesh_extent,
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
