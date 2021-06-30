# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

DEBUG = True

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
    QgsProcessingParameterVectorDestination,
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant

import processing
from math import ceil

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

        # Check if project crs has changed
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
                "extent",
                "Terrain extent",
                defaultValue=defaultValue,
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
                "dem_layer",
                "DEM layer",
                defaultValue=defaultValue,
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
            "Domain origin (if not set, use terrain extent centroid)",
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
            "Fire origin (if not set, use domain origin)",
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
            "Texture layer pixel size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        param = QgsProcessingParameterVectorDestination(
            "sampling_layer",
            "Sampling grid layer",
            type=QgsProcessing.TypeVectorPoint,
            createByDefault=True,
            defaultValue=None,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        if DEBUG:
            param = QgsProcessingParameterVectorDestination(
                "tex_extent_layer",  # Name
                "FDS texture",  # Description
                type=QgsProcessing.TypeVectorPolygon,
                createByDefault=True,
                defaultValue=None,
            )
            self.addParameter(param)

            param = QgsProcessingParameterVectorDestination(
                "dem_extent_layer",  # Name
                "FDS terrain extent layer",  # Description
                type=QgsProcessing.TypeVectorPolygon,
                createByDefault=True,
                defaultValue=None,
            )
            self.addParameter(param)

            param = QgsProcessingParameterVectorDestination(
                "utm_extent_layer",  # Name
                "FDS domain extent layer",  # Description
                type=QgsProcessing.TypeVectorPolygon,
                createByDefault=True,
                defaultValue=None,
            )
            self.addParameter(param)

    def processAlgorithm(self, parameters, context, feedback):
        """
        Process algorithm.
        """
        # Points:
        #  origin: user origin point in proj crs
        #  fire_origin: user fire origin point in proj crs
        #  wgs84_origin: origin point in wgs84 crs, used for choosing utm_crs
        #  wgs84_fire_origin: fire origin point in wgs84 crs
        #  utm_origin: origin point in utm crs
        #  utm_fire_origin: fire origin point in utm crs

        # CRSs:
        #  project_crs: project crs
        #  wgs84_crs:  wgs84 crs
        #  utm_crs:  utm crs, calculated from wgs84_origin
        #  dem_crs:  dem crs, used for grid alignment

        # Extents:
        #  extent:      user selected terrain extent in its own crs.
        #  utm_extent:  extent to utm crs, used for FDS domain (MESH),
        #               contains the extent, contained in the following dem_extent.
        #  dem_extent:  utm_extent to dem crs, used for FDS terrain (GEOM),
        #               contains the utm_extent, contained in the following tex_extent.
        #               Required for sampling grid alignment with dem raster data.
        #  tex_extent:  dem_extent to utm crs, used for FDS terrain texture crop,
        #               contains dem_extent.
        #               Required because the texture should be oriented as utm and
        #               perfectly overlapping to dem_extent

        results, outputs, project = {}, {}, QgsProject.instance()

        # Get some of the parameters
        chid = self.parameterAsString(parameters, "chid", context)
        project.writeEntry("qgis2fds", "chid", parameters["chid"])
        path = self.parameterAsFile(parameters, "path", context)
        project.writeEntry("qgis2fds", "path", parameters["path"])
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)
        project.writeEntry("qgis2fds", "landuse_type", parameters["landuse_type"])
        dem_sampling = self.parameterAsInt(parameters, "dem_sampling", context)
        project.writeEntry("qgis2fds", "dem_sampling", parameters["dem_sampling"])
        extent = self.parameterAsExtent(parameters, "extent", context)
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
            raise QgsProcessingException(
                f"Project CRS <{project_crs.description()}> is not valid, cannot proceed."
            )

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        dem_crs = dem_layer.crs()
        if not dem_crs.isValid():
            raise QgsProcessingException(
                f"DEM layer CRS <{dem_crs.description()}> is not valid, cannot proceed."
            )

        if landuse_layer:
            landuse_crs = landuse_layer.crs()
            if not landuse_crs.isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{landuse_crs.description()}> is not valid, cannot proceed."
                )

        if tex_layer:
            tex_crs = tex_layer.crs()
            if not tex_crs.isValid():
                raise QgsProcessingException(
                    f"Texture layer CRS <{tex_crs.description()}> is not valid, cannot proceed."
                )

        # Get origin in WGS84 CRS
        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )
        if parameters["origin"] is not None:
            # preventing a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            origin = self.parameterAsPoint(parameters, "origin", context)
            project.writeEntry("qgis2fds", "origin", parameters["origin"])
            wgs84_origin = QgsPoint(origin)
            wgs84_origin.transform(project_to_wgs84_tr)
        else:  # no origin
            wgs84_origin = QgsPoint(extent.center())
            wgs84_origin.transform(project_to_wgs84_tr)
        feedback.pushInfo(
            f"Domain origin: {wgs84_origin.x():.6f}, {wgs84_origin.y():.6f} (WGS 84)"
        )

        # Get fire origin in WGS84 CRS
        if parameters["fire_origin"] is not None:
            # preventing a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            fire_origin = self.parameterAsPoint(parameters, "fire_origin", context)
            project.writeEntry("qgis2fds", "fire_origin", parameters["fire_origin"])
            wgs84_fire_origin = QgsPoint(fire_origin)
            wgs84_fire_origin.transform(project_to_wgs84_tr)
        else:  # no fire origin
            wgs84_fire_origin = wgs84_origin.clone()
        feedback.pushInfo(
            f"Fire origin: {wgs84_fire_origin.x():.6f}, {wgs84_fire_origin.y():.6f} (WGS 84)"
        )

        # Calc utm_crs from wgs84_origin
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        # Feedback on CRSs
        feedback.pushInfo(f"\nProject CRS: <{project_crs.description()}>")
        feedback.pushInfo(f"DEM layer CRS: <{dem_crs.description()}>")
        feedback.pushInfo(
            f"Landuse layer CRS: <{landuse_layer and landuse_crs.description() or 'no landuse'}>"
        )
        feedback.pushInfo(
            f"Texture layer CRS: <{tex_layer and tex_crs.description() or 'no texture'}>"
        )
        feedback.pushInfo(f"FDS CRS: <{utm_crs.description()}>")

        # Get origin in utm_crs
        wgs84_to_utm_tr = QgsCoordinateTransform(
            wgs84_crs, utm_crs, QgsProject.instance()
        )
        utm_origin = wgs84_origin.clone()
        utm_origin.transform(wgs84_to_utm_tr)

        # Check for QGIS bug
        if utm_origin == wgs84_origin:
            raise QgsProcessingException(
                f"[QGIS bug] UTM Origin <{utm_origin}> and WGS84 Origin <{wgs84_origin}> are identical, cannot proceed.\n{wgs84_to_utm_tr}\n{wgs84_crs} {utm_crs}"
            )

        # Get fire origin in utm_crs
        utm_fire_origin = wgs84_fire_origin.clone()
        utm_fire_origin.transform(wgs84_to_utm_tr)

        # Get utm_extent in utm_crs from extent (for MESH)
        # and dem_extent in dem_crs from utm_extent (for dem_layer sampling to GEOM)
        utm_extent = self.parameterAsExtent(
            parameters,
            "extent",
            context,
            crs=utm_crs,
        )
        utm_to_dem_tr = QgsCoordinateTransform(utm_crs, dem_crs, QgsProject.instance())
        dem_extent = utm_to_dem_tr.transformBoundingBox(utm_extent)

        # Get dem_layer resolution and top left extent corner coordinates,
        # because raster grid starts from top left corner of dem_layer extent
        dem_layer_xres = dem_layer.rasterUnitsPerPixelX()
        dem_layer_yres = dem_layer.rasterUnitsPerPixelY()
        dem_layer_x0, dem_layer_y1 = (
            dem_layer.extent().xMinimum(),
            dem_layer.extent().yMaximum(),
        )

        # Aligning dem_extent top left corner to dem_layer resolution,
        # never reduce its size
        x0, y0, x1, y1 = (
            dem_extent.xMinimum(),
            dem_extent.yMinimum(),
            dem_extent.xMaximum(),
            dem_extent.yMaximum(),
        )
        x0 = (
            dem_layer_x0  # start lower
            + int((x0 - dem_layer_x0) / dem_layer_xres) * dem_layer_xres  # align
            - dem_layer_xres / 2.0  # to previous raster pixel center
        )
        y1 = (
            dem_layer_y1  # start upper
            - int((dem_layer_y1 - y1) / dem_layer_yres) * dem_layer_yres  # align
            + dem_layer_yres / 2.0  # to following raster pixel center
        )
        dem_layer_xres *= dem_sampling  # down sampling, if requested
        dem_layer_yres *= dem_sampling
        x1 = (
            x0  # start lower
            + (ceil((x1 - x0) / dem_layer_xres) + 0.000001)  # prevent rounding errors
            * dem_layer_xres  # ceil multiple of xres
        )
        y0 = (
            y1  # start upper
            - (ceil((y1 - y0) / dem_layer_yres) + 0.000001)  # prevent rounding errors
            * dem_layer_yres  # ceil multiple of yres
        )
        dem_extent = QgsRectangle(x0, y0, x1, y1)

        # Check dem_layer contains updated dem_extent
        if not dem_layer.extent().contains(dem_extent):
            feedback.reportError(
                "Terrain extent (GEOM) is larger than DEM layer extent, unknown elevations will be set to zero."
            )

        # Calc and check number of dem sampling point
        dem_sampling_xn = int((x1 - x0) / dem_layer_xres) + 1
        dem_sampling_yn = int((y1 - y0) / dem_layer_yres) + 1
        if dem_sampling_xn < 3:
            raise QgsProcessingException(
                f"Too few sampling points <{dem_sampling_xn}> along x axis, cannot proceed."
            )
        if dem_sampling_yn < 3:
            raise QgsProcessingException(
                f"Too few sampling points <{dem_sampling_yn}> along y axis, cannot proceed."
            )
        nverts = (dem_sampling_xn + 1) * (dem_sampling_yn + 1)
        nfaces = dem_sampling_xn * dem_sampling_yn * 2

        # Get tex_extent in utm_crs from dem_crs,
        # texture shall be aligned to MESH, and exactly cover the GEOM terrain
        dem_to_utm_tr = QgsCoordinateTransform(dem_crs, utm_crs, QgsProject.instance())
        tex_extent = dem_to_utm_tr.transformBoundingBox(dem_extent)

        # Get FDS domain size in meters
        utm_extent_xm = utm_extent.xMaximum() - utm_extent.xMinimum()
        utm_extent_ym = utm_extent.yMaximum() - utm_extent.yMinimum()

        # Feedback
        feedback.pushInfo(f"\nFDS domain (MESH)")
        feedback.pushInfo(f"size: {utm_extent_xm:.1f} x {utm_extent_ym:.1f} meters")
        feedback.pushInfo(f"\nDEM layer sampling for FDS terrain (GEOM)")
        feedback.pushInfo(
            f"resolution: {dem_layer_xres:.1f} x {dem_layer_yres:.1f} meters"
        )
        feedback.pushInfo(f"geometry: {nverts} verts, {nfaces} faces")
        feedback.pushInfo(f"\nPress <Cancel> to interrupt the execution.")

        if DEBUG:
            # Show utm_extent layer
            feedback.pushInfo(f"\n[DEBUG] Drawing utm_extent...")
            x0, y0, x1, y1 = (
                utm_extent.xMinimum(),
                utm_extent.yMinimum(),
                utm_extent.xMaximum(),
                utm_extent.yMaximum(),
            )
            alg_params = {
                "INPUT": f"{x0}, {x1}, {y0}, {y1} [{utm_crs.authid()}]",
                "OUTPUT": parameters["utm_extent_layer"],
            }
            outputs["CreateLayerFromExtent"] = processing.run(
                "native:extenttolayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            results["utm_extent_layer"] = outputs["CreateLayerFromExtent"]["OUTPUT"]

            # Show dem_extent layer
            feedback.pushInfo(f"[DEBUG] Drawing dem_extent...")
            x0, y0, x1, y1 = (
                dem_extent.xMinimum(),
                dem_extent.yMinimum(),
                dem_extent.xMaximum(),
                dem_extent.yMaximum(),
            )
            alg_params = {
                "INPUT": f"{x0}, {x1}, {y0}, {y1} [{dem_crs.authid()}]",
                "OUTPUT": parameters["dem_extent_layer"],
            }
            outputs["CreateLayerFromExtent"] = processing.run(
                "native:extenttolayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            results["dem_extent_layer"] = outputs["CreateLayerFromExtent"]["OUTPUT"]

            # Show tex_extent layer
            feedback.pushInfo(f"[DEBUG] Drawing tex_extent...")
            x0, y0, x1, y1 = (
                tex_extent.xMinimum(),
                tex_extent.yMinimum(),
                tex_extent.xMaximum(),
                tex_extent.yMaximum(),
            )
            alg_params = {
                "INPUT": f"{x0}, {x1}, {y0}, {y1} [{utm_crs.authid()}]",
                "OUTPUT": parameters["tex_extent_layer"],
            }
            outputs["CreateLayerFromExtent"] = processing.run(
                "native:extenttolayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            results["tex_extent_layer"] = outputs["CreateLayerFromExtent"]["OUTPUT"]

        # QGIS geographic transformations
        # Creating sampling grid in DEM crs

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(1/7) Creating sampling grid from DEM layer...")

        alg_params = {
            "CRS": dem_crs,
            "EXTENT": dem_extent,
            "HOVERLAY": 0,
            "HSPACING": dem_layer_xres,
            "TYPE": 0,  # Points
            "VOVERLAY": 0,
            "VSPACING": dem_layer_yres,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["CreateGrid"] = processing.run(
            "native:creategrid",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        # Writing texture image to disk

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(2/7) Rendering, cropping, and writing texture image, timeout in 30s..."
        )

        utils.write_texture(
            feedback=feedback,
            tex_layer=tex_layer,
            tex_extent=tex_extent,
            tex_pixel_size=tex_pixel_size,
            utm_crs=utm_crs,
            filepath=f"{path}/{chid}_tex.png",
            imagetype="png",
        )

        # QGIS geographic transformations
        # Draping Z values to sampling grid in DEM crs

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(3/7) Draping elevations from DEM layer to sampling grid..."
        )

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

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(4/7) Reprojecting sampling grid layer to UTM CRS..."
        )

        alg_params = {
            "INPUT": outputs["DrapeSetZValueFromRaster"]["OUTPUT"],
            "TARGET_CRS": utm_crs,
            "OUTPUT": parameters["sampling_layer"],
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

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(5/7) Sampling landuse layer...")

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

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(6/7) Building FDS geometry...")

        if point_layer.featureCount() < 9:
            raise QgsProcessingException(
                f"[QGIS bug] Too few features in sampling layer, cannot proceed.\n{point_layer.featureCount()}"
            )

        verts, faces, landuses = geometry.get_geometry(
            feedback=feedback,
            layer=point_layer,
            utm_origin=utm_origin,
        )

        # Write the FDS case file

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(7/7) Writing the FDS case file...")

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
            utm_extent=utm_extent,
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
