# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

DEBUG = True

from qgis.core import (
    QgsProject,
    QgsPoint,
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
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterBoolean,
    QgsRasterLayer,
    QgsVectorLayer,
)

import processing, os
from .types import (
    utils,
    FDSCase,
    Domain,
    OBSTTerrain,
    GEOMTerrain,
    LanduseType,
    Texture,
    Wind,
)
from . import algos


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

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "dem_layer_res", 30.0)
        self.addParameter(
            QgsProcessingParameterNumber(
                "dem_layer_res",
                "Terrain resolution",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=defaultValue,
                minValue=0.1,
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

        defaultValue, _ = project.readBoolEntry("qgis2fds", "export_obst", True)
        param = QgsProcessingParameterBoolean(
            "export_obst",
            "Export FDS OBSTs",
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        param = QgsProcessingParameterVectorDestination(
            "grid",  # Name
            "Grid [Debug]",  # Description
            type=QgsProcessing.TypeVectorPoint,
            createByDefault=True,
            defaultValue=None,
        )
        self.addParameter(param)

        param = QgsProcessingParameterRasterDestination(
            "i_dem_layer",  # Name
            "Interpolated DEM Layer [Debug]",  # Description
            createByDefault=True,
            defaultValue=None,
        )
        self.addParameter(param)

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

        # Extents:
        #  extent:      user selected terrain extent in its own crs.
        #  utm_extent:  extent to utm crs, used for FDS domain (MESH),
        #               contains the extent, contained in the following dem_extent.

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

        dem_layer_res = self.parameterAsDouble(parameters, "dem_layer_res", context)
        project.writeEntryDouble(
            "qgis2fds",
            "dem_layer_res",
            parameters.get("dem_layer_res", 10.0),  # FIXME same with others
        )

        nmesh = self.parameterAsInt(parameters, "nmesh", context)
        project.writeEntry("qgis2fds", "nmesh", parameters["nmesh"])

        # Get DEM layer
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        project.writeEntry("qgis2fds", "dem_layer", parameters["dem_layer"])

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
        project_crs = QgsProject.instance().crs()  # FIXME it is project
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
        utm_extent = self.parameterAsExtent(
            parameters,
            "extent",
            context,
            crs=utm_crs,
        )

        # Interpolate dem to desired resolution:
        # - build sampling grid aligned to dem pixels
        # - drape z elevations to grid points
        # - reproject grid to utm
        # - build new interpolated dem at desired resolution in utm

        if feedback.isCanceled():
            return {}

        outputs["i_grid"] = algos.get_raster_sampling_grid_layer(
            context,
            feedback,
            text="Create DEM layer sampling grid...",
            raster_layer=dem_layer,
            extent=utm_extent,
            extent_crs=utm_crs,
        )

        if feedback.isCanceled():
            return {}

        outputs["i_draped_grid"] = algos.set_grid_layer_z(
            context,
            feedback,
            text="Drape DEM layer elevations to sampling grid...",
            grid_layer=outputs["i_grid"]["OUTPUT"],
            raster_layer=dem_layer,
        )

        if feedback.isCanceled():
            return {}

        outputs["iw_draped_grid"] = algos.reproject_vector_layer(
            context,
            feedback,
            text="Reproject sampling grid...",
            vector_layer=outputs["i_draped_grid"]["OUTPUT"],
            destination_crs=utm_crs,
        )

        if feedback.isCanceled():
            return {}

        outputs["iw_dem_layer"] = algos.create_raster_from_grid(
            context,
            feedback,
            text="Interpolate DEM layer sampling grid...",
            grid_layer=outputs["iw_draped_grid"]["OUTPUT"],
            extent=utm_extent,
            pixel_size=dem_layer_res,
        )

        if feedback.isCanceled():
            return {}

        utm_extent = algos.get_pixel_aligned_extent(
            context,
            feedback,
            text="Align UTM extent to interpolated raster pixels...",
            raster_layer=outputs["iw_dem_layer"]["OUTPUT"],
            extent=utm_extent,
            extent_crs=utm_crs,
        )

        # Build OBST/GEOM
        # - build utm grid at desired resolution
        # - drape z elevations to grid points
        # - sample landuse to grid points
        # - build OBST/GEOM

        if feedback.isCanceled():
            return {}

        outputs["grid"] = algos.get_grid_layer(
            context,
            feedback,
            text="Create terrain sampling grid...",
            crs=utm_crs,
            extent=utm_extent,
            xres=dem_layer_res,
            yres=dem_layer_res,
        )

        if feedback.isCanceled():
            return {}

        outputs["draped_grid"] = algos.set_grid_layer_z(
            context,
            feedback,
            text="Drape interpolated DEM layer elevations to terrain grid...",
            grid_layer=outputs["grid"]["OUTPUT"],
            raster_layer=outputs["iw_dem_layer"]["OUTPUT"],
        )

        if feedback.isCanceled():
            return {}

        if landuse_layer:
            outputs["draped_landused_grid"] = algos.set_grid_layer_value(
                context,
                feedback,
                text="Sample landuse layer to terrain grid...",
                grid_layer=outputs["draped_grid"]["OUTPUT"],
                raster_layer=parameters["landuse_layer"],
                column_prefix="landuse",
            )
            point_layer = context.getMapLayer(outputs["draped_landused_grid"]["OUTPUT"])
        else:
            feedback.pushInfo("No landuse layer provided.")
            point_layer = context.getMapLayer(outputs["draped_grid"]["OUTPUT"])

        if point_layer.featureCount() < 9:
            raise QgsProcessingException(
                f"[QGIS bug] Too few features in sampling layer, cannot proceed.\n{point_layer.featureCount()}"
            )

        # Reproject fire_layer to UTM CRS
        # FIXME FIXME FIXME How to put the fire layer bc on landuse raster?

        if feedback.isCanceled():
            return {}

        if fire_layer:
            outputs["ReprojectFireLayer"] = algos.reproject_vector_layer(
                context,
                feedback,
                text="Reproject fire layer...",
                vector_layer=fire_layer,
                destination_crs=utm_crs,
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

        feedback.setProgressText("Prepare geometry and write the FDS case file...")

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
            dem_extent=utm_extent,
            dem_crs=utm_crs,
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
            cell_size=dem_layer_res,  # FIXME
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

        # QgsProject.instance().removeMapLayer(dem_layer)

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
