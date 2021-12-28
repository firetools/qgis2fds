# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

DEBUG = False

from qgis.core import (
    QgsProject,
    QgsPoint,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterPoint,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterBoolean,
)

import processing, os
from math import ceil

from . import utils
from .fds import FDSCase
from .domain import Domain
from .terrain import OBSTTerrain, GEOMTerrain
from .landuse import LanduseType
from .texture import Texture
from .wind import Wind


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

        # Check if project crs has changed
        project_crs = project.crs()
        prev_project_crs_desc, _ = project.readEntry("qgis2fds", "project_crs", None)
        project_crs_changed = False
        if prev_project_crs_desc != project_crs.description():
            project_crs_changed = True

        # Define parameters

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
            "qgis2fds", "fds_path", QgsProject.instance().readPath("./")
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "fds_path",
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

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "dem_sampling", 1.0)
        param = QgsProcessingParameterNumber(
            "dem_sampling",
            "DEM layer sampling factor",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
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

        defaultValue, _ = project.readEntry("qgis2fds", "landuse_type_filepath", "")
        self.addParameter(
            QgsProcessingParameterFile(
                "landuse_type_filepath",
                "Landuse type *.csv file (if not set, landuse is not exported)",
                behavior=QgsProcessingParameterFile.File,
                fileFilter="CSV files (*.csv)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "fire_layer", None)
        if not defaultValue:
            try:  # first layer name containing "fire"
                defaultValue = [
                    layer.name()
                    for layer in QgsProject.instance().mapLayers().values()
                    if "Fire" in layer.name() or "fire" in layer.name()
                ][0]
            except IndexError:
                pass
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "fire_layer",
                "Fire layer",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "wind_filepath", "")
        self.addParameter(
            QgsProcessingParameterFile(
                "wind_filepath",
                "Wind *.csv file",
                behavior=QgsProcessingParameterFile.File,
                fileFilter="CSV files (*.csv)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "tex_layer", None)
        param = QgsProcessingParameterRasterLayer(
            "tex_layer",
            "Texture layer (if not set, current view is exported)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "tex_pixel_size", 5.0)
        param = QgsProcessingParameterNumber(
            "tex_pixel_size",
            "Texture layer pixel size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readNumEntry("qgis2fds", "nmesh", 4)
        param = QgsProcessingParameterNumber(
            "nmesh",
            "Max number of FDS MESHes",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=defaultValue,
            minValue=1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "cell_size", 10.0)
        param = QgsProcessingParameterNumber(
            "cell_size",
            "Desired FDS MESH cell size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        param = QgsProcessingParameterVectorDestination(
            "sampling_layer",
            "Sampling grid layer [Result]",
            type=QgsProcessing.TypeVectorPoint,
            createByDefault=True,
            defaultValue=None,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readBoolEntry("qgis2fds", "export_obst", False)
        param = QgsProcessingParameterBoolean(
            "export_obst",
            "Export FDS OBSTs",
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        if DEBUG:
            param = QgsProcessingParameterVectorDestination(
                "dem_extent_layer",  # Name
                "FDS terrain extent layer [Debug]",  # Description
                type=QgsProcessing.TypeVectorPolygon,
                createByDefault=True,
                defaultValue=None,
            )
            self.addParameter(param)

            param = QgsProcessingParameterVectorDestination(
                "utm_extent_layer",  # Name
                "FDS domain extent layer [Debug]",  # Description
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
        #  wgs84_origin: origin point in wgs84 crs, used for choosing utm_crs
        #  utm_origin: origin point in utm crs

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

        # Get qgis file path
        project_path = QgsProject.instance().readPath("./")
        if not project_path:
            raise QgsProcessingException(
                "The qgis project is not saved to disk, cannot proceed."
            )

        # Get the main parameters, save them to the qgis file
        chid = self.parameterAsString(parameters, "chid", context)
        project.writeEntry("qgis2fds", "chid", parameters["chid"])

        fds_path = self.parameterAsFile(parameters, "fds_path", context)
        project.writeEntry("qgis2fds", "fds_path", parameters["fds_path"])
        fds_path = os.path.join(project_path, fds_path)  # abs

        extent = self.parameterAsExtent(parameters, "extent", context)
        project.writeEntry("qgis2fds", "extent", parameters["extent"])

        nmesh = self.parameterAsInt(parameters, "nmesh", context)
        project.writeEntry("qgis2fds", "nmesh", parameters["nmesh"])

        cell_size = self.parameterAsDouble(parameters, "cell_size", context)
        project.writeEntryDouble("qgis2fds", "cell_size", parameters["cell_size"])

        # Get DEM layer and DEM sampling
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        project.writeEntry("qgis2fds", "dem_layer", parameters["dem_layer"])

        dem_sampling = self.parameterAsDouble(parameters, "dem_sampling", context)
        project.writeEntryDouble("qgis2fds", "dem_sampling", parameters["dem_sampling"])

        # Get landuse (optional)
        landuse_layer, landuse_type_filepath = None, None
        if parameters["landuse_layer"] and parameters["landuse_type_filepath"]:
            landuse_layer = self.parameterAsRasterLayer(
                parameters, "landuse_layer", context
            )
            landuse_type_filepath = self.parameterAsFile(
                parameters, "landuse_type_filepath", context
            )
        project.writeEntry("qgis2fds", "landuse_layer", parameters["landuse_layer"])
        project.writeEntry(
            "qgis2fds",
            "landuse_type_filepath",
            parameters["landuse_type_filepath"] or "",
        )

        # Get fire_layer (optional)
        if parameters["fire_layer"]:
            fire_layer = self.parameterAsVectorLayer(parameters, "fire_layer", context)
        else:
            fire_layer = None
        project.writeEntry("qgis2fds", "fire_layer", parameters["fire_layer"])

        # Get wind .csv filepath (optional)
        wind_filepath = self.parameterAsFile(parameters, "wind_filepath", context)
        project.writeEntry(
            "qgis2fds", "wind_filepath", parameters["wind_filepath"] or ""
        )

        # Get tex_layer (optional) and tex_pixel_size
        tex_layer = None
        if parameters["tex_layer"]:
            tex_layer = self.parameterAsRasterLayer(parameters, "tex_layer", context)
        project.writeEntry("qgis2fds", "tex_layer", parameters["tex_layer"])
        tex_pixel_size = self.parameterAsDouble(parameters, "tex_pixel_size", context)
        project.writeEntryDouble(
            "qgis2fds", "tex_pixel_size", parameters["tex_pixel_size"]
        )

        # Get type of export (FDS GEOM or OBSTs)
        export_obst = False
        if parameters["export_obst"]:
            export_obst = True
        project.writeEntryBool("qgis2fds", "export_obst", parameters["export_obst"])

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

        if fire_layer:
            fire_crs = fire_layer.crs()
            if not fire_crs.isValid():
                raise QgsProcessingException(
                    f"Fire layer CRS <{fire_crs.description()}> is not valid, cannot proceed."
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
            # prevent a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            origin = self.parameterAsPoint(parameters, "origin", context)
            project.writeEntry("qgis2fds", "origin", parameters["origin"])
            wgs84_origin = QgsPoint(origin)
            wgs84_origin.transform(project_to_wgs84_tr)
        else:  # no origin
            wgs84_origin = QgsPoint(extent.center())
            wgs84_origin.transform(project_to_wgs84_tr)

        # Calc utm_crs from wgs84_origin
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        # Feedback on origin and CRSs
        feedback.pushInfo(
            f"""
        Domain origin: {wgs84_origin.x():.6f}, {wgs84_origin.y():.6f} (WGS 84)
        Project CRS: <{project_crs.description()}>
        DEM layer CRS: <{dem_crs.description()}>
        Landuse layer CRS: <{landuse_layer and landuse_crs.description() or 'No landuse'}>
        Fire layer CRS: <{fire_layer and fire_crs.description() or 'No fire'}>
        Texture layer CRS: <{tex_layer and tex_crs.description() or 'No texture'}>
        FDS case CRS: <{utm_crs.description()}>

        Press <Cancel> to interrupt the execution."""
        )

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

        # Calc and check dem_sampling
        dem_layer_res = max(dem_layer_xres, dem_layer_yres)
        if dem_layer_res < cell_size:
            feedback.reportError(
                f"\nDEM layer resolution {dem_layer_res:.1f}m is smaller than FDS MESH cell size {cell_size:.1f}m."
            )

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

        # Get FDS domain size in meters
        utm_extent_xm = utm_extent.xMaximum() - utm_extent.xMinimum()
        utm_extent_ym = utm_extent.yMaximum() - utm_extent.yMinimum()

        # Feedback on FDS domain
        feedback.pushInfo(
            f"""
        FDS domain
        overall size: {utm_extent_xm:.1f} x {utm_extent_ym:.1f} meters
        cell size: {cell_size} meters

        DEM layer sampling for FDS terrain
        resolution: {dem_layer_xres:.1f} x {dem_layer_yres:.1f} meters
        geometry: {nverts} verts, {nfaces} faces

        Press <Cancel> to interrupt the execution."""
        )

        if DEBUG:
            # Show utm_extent layer
            feedback.pushInfo(f"\n[DEBUG] Draw utm_extent...")
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
            feedback.pushInfo(f"[DEBUG] Draw dem_extent...")
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

        # QGIS geographic transformations
        # Create sampling grid in DEM crs

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(1/6) Create sampling grid from DEM layer...")

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

        # QGIS geographic transformations
        # Drape Z values to sampling grid in DEM crs

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(2/6) Drape elevations from DEM layer to sampling grid..."
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
        # Sampling landuse layer with sampling grid in UTM CRS

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(3/6) Sample landuse layer...")

        if landuse_layer:
            alg_params = {
                "COLUMN_PREFIX": "landuse",
                "INPUT": outputs["DrapeSetZValueFromRaster"]["OUTPUT"],
                "RASTERCOPY": parameters["landuse_layer"],
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["RasterSampling"] = processing.run(
                "qgis:rastersampling",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
        else:
            feedback.pushInfo("No landuse layer provided, no sampling.")

        # QGIS geographic transformations
        # Reproject sampling grid to UTM CRS

        if feedback.isCanceled():
            return {}
        feedback.setProgressText("\n(4/6) Reproject sampling grid layer to UTM CRS...")

        alg_params = {
            "INPUT": landuse_layer
            and outputs["RasterSampling"]["OUTPUT"]
            or outputs["DrapeSetZValueFromRaster"]["OUTPUT"],
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
        results["sampling_layer"] = outputs["ReprojectLayer"]["OUTPUT"]

        # Get point_layer and check it

        point_layer = context.getMapLayer(results["sampling_layer"])
        if point_layer.featureCount() < 9:
            raise QgsProcessingException(
                f"[QGIS bug] Too few features in sampling layer, cannot proceed.\n{point_layer.featureCount()}"
            )

        # QGIS geographic transformations
        # Reproject fire_layer to UTM CRS
        # and sample fire_layer for ignition lines and burned areas

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(5/6) Reproject fire layer to UTM CRS and set bcs..."
        )

        if fire_layer:
            # Reproject fire_layer to UTM CRS
            alg_params = {
                "INPUT": fire_layer,
                "TARGET_CRS": utm_crs,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ReprojectFireLayer"] = processing.run(
                "native:reprojectlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            fire_layer_utm = context.getMapLayer(
                outputs["ReprojectFireLayer"]["OUTPUT"]
            )
        else:
            fire_layer_utm = None
            feedback.pushInfo("No fire layer provided, no fire in the domain.")

        # Build the classes and write the FDS case file

        if feedback.isCanceled():
            return {}
        feedback.setProgressText(
            "\n(6/6) Prepare geometry and write the FDS case file..."
        )

        landuse_type = LanduseType(
            feedback=feedback, project_path=project_path, filepath=landuse_type_filepath
        )

        wind = Wind(
            feedback=feedback, project_path=project_path, filepath=wind_filepath
        )

        texture = Texture(
            feedback=feedback,
            path=fds_path,
            name=chid,
            image_type="png",
            pixel_size=tex_pixel_size,
            layer=tex_layer,
            utm_extent=utm_extent,
            utm_crs=utm_crs,
            dem_extent=dem_extent,
            dem_crs=dem_crs,
            export_obst=export_obst,
        )

        if export_obst:
            Terrain = OBSTTerrain
        else:
            Terrain = GEOMTerrain

        terrain = Terrain(
            feedback=feedback,
            path=fds_path,
            name=chid,
            dem_layer=dem_layer,
            dem_layer_res=dem_layer_res,
            point_layer=point_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
            fire_layer=fire_layer,
            fire_layer_utm=fire_layer_utm,
        )

        domain = Domain(
            feedback=feedback,
            wgs84_origin=wgs84_origin,
            utm_crs=utm_crs,
            utm_extent=utm_extent,
            utm_origin=utm_origin,
            min_z=terrain.min_z,
            max_z=terrain.max_z,
            cell_size=cell_size,
            nmesh=nmesh,
        )

        FDSCase(
            feedback=feedback,
            path=fds_path,
            name=chid,
            domain=domain,
            terrain=terrain,
            texture=texture,
            wind=wind,
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
