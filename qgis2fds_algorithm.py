# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

DEBUG = False

from qgis.core import (
    QgsProject,
    QgsPoint,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingException,
    QgsProcessingAlgorithm,
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
    QgsRasterLayer,
    NULL,
)

import os
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

    def initAlgorithm(self, config=None):
        """!
        Inputs and outputs of the algorithm.
        """
        project = QgsProject.instance()

        # Check if project crs has changed
        prev_project_crs_desc, _ = project.readEntry("qgis2fds", "project_crs", None)
        is_project_crs_changed = False
        if prev_project_crs_desc != project.crs().description():
            is_project_crs_changed = True

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

        # fds_path = QgsProject.instance().readPath("./")
        defaultValue, _ = project.readEntry("qgis2fds", "fds_path", "./")
        self.addParameter(
            QgsProcessingParameterFile(
                "fds_path",
                "Save in folder",
                behavior=QgsProcessingParameterFile.Folder,
                fileFilter="All files (*.*)",
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readEntry("qgis2fds", "extent", None)
        self.addParameter(
            QgsProcessingParameterExtent(
                "extent",
                "Domain extent",
                defaultValue=defaultValue,
            )
        )

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "pixel_size", 10.0)
        self.addParameter(
            QgsProcessingParameterNumber(
                "pixel_size",
                "Desired resolution (in meters)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=defaultValue,
                minValue=0.1,
            )
        )

        if is_project_crs_changed:
            defaultValue = None
        else:
            defaultValue, _ = project.readEntry("qgis2fds", "origin", None)
        param = QgsProcessingParameterPoint(
            "origin",
            "Domain origin (if not set, use domain extent centroid)",
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

        defaultValue, _ = project.readEntry("qgis2fds", "devc_layer", None)
        if not defaultValue:
            try:  # first layer name containing "devc"
                defaultValue = [
                    layer.name()
                    for layer in QgsProject.instance().mapLayers().values()
                    if "DEVC" in layer.name() or "devc" in layer.name()
                ][0]
            except IndexError:
                pass
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "devc_layer",
                "FDS DEVCs layer",
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

        defaultValue, _ = project.readNumEntry("qgis2fds", "nmesh", 1)
        param = QgsProcessingParameterNumber(
            "nmesh",
            "Max number of FDS MESHes",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=defaultValue,
            minValue=1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "cell_size")
        if not defaultValue:
            defaultValue = None
        param = QgsProcessingParameterNumber(
            "cell_size",
            "FDS MESH cell size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            optional=True,
            defaultValue=defaultValue,
            minValue=0.1,
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

        # param = QgsProcessingParameterFeatureSink(  # DEBUG FIXME
        #     "utm_dem_layer",  # Name
        #     "Interpolated DEM Layer",  # Description
        #     createByDefault=False,
        #     defaultValue=None,
        # )
        # self.addParameter(param)

        # param = QgsProcessingParameterFeatureSink(  # DEBUG FIXME
        #     "sampling_layer",  # Name
        #     "Sampling Layer",  # Description
        #     type=QgsProcessing.TypeVectorPoint,
        #     createByDefault=False,
        #     defaultValue=None,
        # )
        # self.addParameter(param)

    def processAlgorithm(self, parameters, context, feedback):
        """
        Process algorithm.
        """
        #  wgs84_origin: origin point in wgs84 crs, used for choosing utm_crs
        #  utm_origin: origin point in utm crs
        #  utm_crs: utm crs, calculated from wgs84_origin
        #  utm_extent: extent to utm crs, used for FDS domain (MESH).

        results, outputs, project = {}, {}, QgsProject.instance()

        # Get qgis file path
        project_path = project.readPath("./")
        if not project_path:
            raise QgsProcessingException(
                "The qgis project is not saved to disk, cannot proceed."
            )

        # Check project crs and save it
        if not project.crs().isValid():
            raise QgsProcessingException(
                f"Project CRS <{project.crs().description()}> is not valid, cannot proceed."
            )
        project.writeEntry("qgis2fds", "project_crs", project.crs().description())

        # Get the main parameters, save them to the qgis file
        chid = self.parameterAsString(parameters, "chid", context)
        project.writeEntry("qgis2fds", "chid", parameters["chid"])

        fds_path = self.parameterAsFile(parameters, "fds_path", context)
        project.writeEntry("qgis2fds", "fds_path", parameters["fds_path"])
        fds_path = os.path.join(project_path, fds_path)  # abs

        pixel_size = self.parameterAsDouble(parameters, "pixel_size", context)
        project.writeEntryDouble(
            "qgis2fds",
            "pixel_size",
            parameters.get("pixel_size", 10.0),  # FIXME others?
        )

        nmesh = self.parameterAsInt(parameters, "nmesh", context)
        project.writeEntry("qgis2fds", "nmesh", parameters["nmesh"])

        if parameters["cell_size"]:
            cell_size = self.parameterAsDouble(parameters, "cell_size", context)
            project.writeEntryDouble("qgis2fds", "cell_size", parameters["cell_size"])
        else:
            cell_size = pixel_size
            project.writeEntry("qgis2fds", "cell_size", "")

        # Get extent and origin WGS84 crs
        # (the extent is exported in its crs)
        extent = self.parameterAsExtent(parameters, "extent", context)
        feedback.pushInfo(f"extent: {extent} {parameters['extent']}")  # FIXME
        project.writeEntry("qgis2fds", "extent", parameters["extent"])

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )

        if parameters["origin"] is not None:
            # prevent a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            # the point is exported in project crs
            origin = self.parameterAsPoint(parameters, "origin", context)
            project.writeEntry("qgis2fds", "origin", parameters["origin"])
            wgs84_origin = QgsPoint(origin)
            project_to_wgs84_tr = QgsCoordinateTransform(
                project.crs(), wgs84_crs, project
            )
            wgs84_origin.transform(project_to_wgs84_tr)
        else:  # no origin
            wgs84_origin = QgsPoint(wgs84_extent.center())

        # Get applicable UTM crs, then UTM origin and extent
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        wgs84_to_utm_tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin = wgs84_origin.clone()
        utm_origin.transform(wgs84_to_utm_tr)

        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)

        # Get landuse_layer and landuse_type (optional)
        landuse_layer, landuse_type_filepath = None, None
        if parameters["landuse_layer"] and parameters["landuse_type_filepath"]:
            landuse_type_filepath = self.parameterAsFile(
                parameters, "landuse_type_filepath", context
            )
            landuse_layer = self.parameterAsRasterLayer(
                parameters, "landuse_layer", context
            )
            if not landuse_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{landuse_layer.crs().description()}> is not valid, cannot proceed."
                )
        landuse_type = LanduseType(
            feedback=feedback,
            project_path=project_path,
            filepath=landuse_type_filepath,
        )
        project.writeEntry("qgis2fds", "landuse_layer", parameters["landuse_layer"])
        project.writeEntry(
            "qgis2fds",
            "landuse_type_filepath",
            parameters["landuse_type_filepath"] or "",
        )

        # Get fire_layer (optional)
        fire_layer, utm_fire_layer, utm_b_fire_layer = None, None, None
        if parameters["fire_layer"]:
            fire_layer = self.parameterAsVectorLayer(parameters, "fire_layer", context)
            if not fire_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Fire layer CRS <{fire_layer.crs().description()}> is not valid, cannot proceed."
                )
            utm_fire_layer, utm_b_fire_layer = algos.get_utm_fire_layers(
                context,
                feedback,
                fire_layer=fire_layer,
                destination_crs=utm_crs,
                pixel_size=pixel_size,
            )
        project.writeEntry("qgis2fds", "fire_layer", parameters["fire_layer"])

        # Get devc_layer (optional)
        devc_layer = None
        if parameters["devc_layer"]:
            devc_layer = self.parameterAsVectorLayer(parameters, "devc_layer", context)
            if not devc_layer.crs().isValid():
                raise QgsProcessingException(
                    f"DEVCs layer CRS <{devc_layer.crs().description()}> is not valid, cannot proceed."
                )
        project.writeEntry("qgis2fds", "devc_layer", parameters["devc_layer"])

        # Get wind .csv filepath (optional)
        wind_filepath = self.parameterAsFile(parameters, "wind_filepath", context)
        project.writeEntry(
            "qgis2fds", "wind_filepath", parameters["wind_filepath"] or ""
        )
        wind = Wind(
            feedback=feedback, project_path=project_path, filepath=wind_filepath
        )

        # Get tex_layer (optional) and tex_pixel_size
        tex_layer, texture = None, None
        if parameters["tex_layer"]:
            tex_layer = self.parameterAsRasterLayer(parameters, "tex_layer", context)
            if not tex_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Texture layer CRS <{tex_layer.crs().description()}> is not valid, cannot proceed."
                )
        project.writeEntry("qgis2fds", "tex_layer", parameters["tex_layer"])

        tex_pixel_size = self.parameterAsDouble(parameters, "tex_pixel_size", context)
        project.writeEntryDouble(
            "qgis2fds", "tex_pixel_size", parameters["tex_pixel_size"]
        )

        texture = Texture(
            feedback=feedback,
            path=fds_path,
            name=chid,
            image_type="png",
            pixel_size=tex_pixel_size,
            tex_layer=tex_layer,
            utm_extent=utm_extent,
            utm_crs=utm_crs,
        )

        # Get DEVCs layer  # FIXME implement
        utm_devc_layer = None
        if devc_layer:
            pass

            if feedback.isCanceled():
                return {}

        # Get type of export (FDS GEOM or OBSTs)
        export_obst = False
        if parameters["export_obst"]:
            export_obst = True
        project.writeEntryBool("qgis2fds", "export_obst", parameters["export_obst"])

        # Get DEM layer
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        project.writeEntry("qgis2fds", "dem_layer", parameters["dem_layer"])
        if not dem_layer.crs().isValid():
            raise QgsProcessingException(
                f"DEM layer CRS <{dem_layer.crs().description()}> is not valid, cannot proceed."
            )

        # Get the interpolated DEM layer
        outputs["utm_dem_layer"] = algos.clip_and_interpolate_dem(
            context,
            feedback,
            dem_layer=dem_layer,
            extent=utm_extent,
            extent_crs=utm_crs,
            pixel_size=pixel_size,
            # output=parameters["utm_dem_layer"],  # DEBUG
        )

        if feedback.isCanceled():
            return {}

        # results["utm_dem_layer"] = outputs["utm_dem_layer"]["OUTPUT"] # DEBUG
        utm_dem_layer = QgsRasterLayer(outputs["utm_dem_layer"]["OUTPUT"])

        # Get the sampling grid
        outputs["sampling_layer"] = algos.get_sampling_point_grid_layer(
            context,
            feedback,
            utm_dem_layer=utm_dem_layer,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
            utm_fire_layer=utm_fire_layer,  # utm
            utm_b_fire_layer=utm_b_fire_layer,  # utm buffered
            # output=parameters["sampling_layer"],  # DEBUG
        )

        if feedback.isCanceled():
            return {}

        # if DEBUG:
        #     results["sampling_layer"] = outputs["sampling_layer"]["OUTPUT"]  # DEBUG FIXME
        sampling_layer = context.getMapLayer(outputs["sampling_layer"]["OUTPUT"])

        if sampling_layer.featureCount() < 9:
            raise QgsProcessingException(
                f"[QGIS bug] Too few features in sampling layer, cannot proceed.\n{sampling_layer.featureCount()}"
            )

        # Align utm_extent to the new interpolated dem
        utm_extent = algos.get_pixel_aligned_extent(
            context,
            feedback,
            raster_layer=utm_dem_layer,
            extent=None,
            extent_crs=None,
            to_centers=False,
            larger=0.0,
        )

        if feedback.isCanceled():
            return {}

        if export_obst:
            terrain = OBSTTerrain(
                feedback=feedback,
                dem_layer=dem_layer,
                pixel_size=pixel_size,
                sampling_layer=sampling_layer,
                utm_origin=utm_origin,
                landuse_layer=landuse_layer,
                landuse_type=landuse_type,
                fire_layer=fire_layer,
            )
        else:
            terrain = GEOMTerrain(
                feedback=feedback,
                dem_layer=dem_layer,
                pixel_size=pixel_size,
                sampling_layer=sampling_layer,
                utm_origin=utm_origin,
                landuse_layer=landuse_layer,
                landuse_type=landuse_type,
                fire_layer=fire_layer,
                path=fds_path,
                name=chid,
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
