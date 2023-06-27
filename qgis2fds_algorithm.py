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
    QgsRaster,
    QgsRasterPipe,
    QgsRasterFileWriter,
    QgsProcessing
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
import processing

DEFAULTS = {
    "chid": "terrain",
    "fds_path": "./",
    "extent": None,
    "pixel_size": 10.0,
    "origin": None,
    "dem_layer": None,
    "landuse_layer": None,
    "landuse_type_filepath": "",
    "fire_layer": None,
    "wind_filepath": "",
    "tex_layer": None,
    "tex_pixel_size": 5.0,
    "nmesh": 1,
    "cell_size": None,
    "export_obst": True,
}


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

        # Define parameter: chid

        defaultValue, _ = project.readEntry("qgis2fds", "chid", DEFAULTS["chid"])
        self.addParameter(
            QgsProcessingParameterString(
                "chid",
                "FDS case identificator (CHID)",
                multiLine=False,
                defaultValue=defaultValue,
            )
        )

        # Define parameter: fds_path

        defaultValue, _ = project.readEntry(
            "qgis2fds", "fds_path", DEFAULTS["fds_path"]
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

        # Define parameter: extent

        defaultValue, _ = project.readEntry("qgis2fds", "extent", DEFAULTS["extent"])
        self.addParameter(
            QgsProcessingParameterExtent(
                "extent",
                "Domain extent",
                defaultValue=defaultValue,
            )
        )

        # Define parameter: pixel_size

        defaultValue, _ = project.readDoubleEntry(
            "qgis2fds", "pixel_size", DEFAULTS["pixel_size"]
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "pixel_size",
                "Desired resolution (in meters)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=defaultValue,
                minValue=0.1,
            )
        )

        # Define parameter: origin [optional]

        if is_project_crs_changed:
            defaultValue = DEFAULTS["origin"]
        else:
            defaultValue, _ = project.readEntry(
                "qgis2fds", "origin", DEFAULTS["origin"]
            )
        param = QgsProcessingParameterPoint(
            "origin",
            "Domain origin (if not set, use domain extent centroid)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Define parameter: dem_layer

        defaultValue, _ = project.readEntry(
            "qgis2fds", "dem_layer", DEFAULTS["dem_layer"]
        )
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

        # Define parameter: landuse_layer [optional]

        defaultValue, _ = project.readEntry(
            "qgis2fds", "landuse_layer", DEFAULTS["landuse_layer"]
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse_layer",
                "Landuse layer (if not set, landuse is not exported)",
                optional=True,
                defaultValue=defaultValue,
            )
        )

        # Define parameter: landuse_type_filepath [optional]

        defaultValue, _ = project.readEntry(
            "qgis2fds", "landuse_type_filepath", DEFAULTS["landuse_type_filepath"]
        )
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

        # Define parameters: fire_layer [optional]

        defaultValue, _ = project.readEntry(
            "qgis2fds", "fire_layer", DEFAULTS["fire_layer"]
        )
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

        # Define parameters: devc_layer  # FIXME implement
        #
        # defaultValue, _ = project.readEntry("qgis2fds", "devc_layer", None)
        # if not defaultValue:
        #     try:  # first layer name containing "devc"
        #         defaultValue = [
        #             layer.name()
        #             for layer in QgsProject.instance().mapLayers().values()
        #             if "DEVC" in layer.name() or "devc" in layer.name()
        #         ][0]
        #     except IndexError:
        #         pass
        # self.addParameter(
        #     QgsProcessingParameterVectorLayer(
        #         "devc_layer",
        #         "FDS DEVCs layer",
        #         optional=True,
        #         defaultValue=defaultValue,
        #     )
        # )

        # Define parameters: wind_filepath [optional]

        defaultValue, _ = project.readEntry(
            "qgis2fds", "wind_filepath", DEFAULTS["wind_filepath"]
        )
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

        # Define parameter: tex_layer [optional]

        defaultValue, _ = project.readEntry(
            "qgis2fds", "tex_layer", DEFAULTS["tex_layer"]
        )
        param = QgsProcessingParameterRasterLayer(
            "tex_layer",
            "Texture layer (if not set, export current view)",
            optional=True,
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Define parameter: tex_pixel_size [optional]

        defaultValue, _ = project.readDoubleEntry(
            "qgis2fds", "tex_pixel_size", DEFAULTS["tex_pixel_size"]
        )
        param = QgsProcessingParameterNumber(
            "tex_pixel_size",
            "Texture layer pixel size (in meters)",
            type=QgsProcessingParameterNumber.Double,
            defaultValue=defaultValue,
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Define parameter: nmesh

        defaultValue, _ = project.readNumEntry("qgis2fds", "nmesh", DEFAULTS["nmesh"])
        param = QgsProcessingParameterNumber(
            "nmesh",
            "Max number of FDS MESHes",
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=defaultValue,
            minValue=1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Define parameter: cell_size

        defaultValue, _ = project.readDoubleEntry("qgis2fds", "cell_size")
        param = QgsProcessingParameterNumber(
            "cell_size",
            "FDS MESH cell size (in meters; if not set, use desired resolution)",
            type=QgsProcessingParameterNumber.Double,
            optional=True,
            defaultValue=defaultValue or None,  # protect
            minValue=0.1,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Define parameter: export_obst

        defaultValue, _ = project.readBoolEntry(
            "qgis2fds", "export_obst", DEFAULTS["export_obst"]
        )
        param = QgsProcessingParameterBoolean(
            "export_obst",
            "Export FDS OBSTs",
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)

        # Output

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

        results, outputs, project = {}, {}, QgsProject.instance()

        # Check project crs and save it

        if not project.crs().isValid():
            raise QgsProcessingException(
                f"Project CRS <{project.crs().description()}> is not valid, cannot proceed."
            )
        project.writeEntry("qgis2fds", "project_crs", project.crs().description())

        # Get parameter: chid

        chid = self.parameterAsString(parameters, "chid", context)
        if not chid:
            raise QgsProcessingException(self.invalidSourceError(parameters, "chid"))
        project.writeEntry("qgis2fds", "chid", chid)

        # Get parameter: fds_path

        project_path = project.readPath("./")
        if not project_path:
            raise QgsProcessingException(
                "Save the qgis project to disk, cannot proceed."
            )

        fds_path = self.parameterAsFile(parameters, "fds_path", context)
        if not fds_path:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "fds_path")
            )
        project.writeEntry("qgis2fds", "fds_path", fds_path)
        fds_path = os.path.join(project_path, fds_path)  # make abs

        # Get parameter: pixel_size

        pixel_size = self.parameterAsDouble(parameters, "pixel_size", context)
        if not pixel_size or pixel_size <= 0.0:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "pixel_size")
            )
        project.writeEntryDouble("qgis2fds", "pixel_size", pixel_size)

        # Get parameter: nmesh

        nmesh = self.parameterAsInt(parameters, "nmesh", context)
        if not nmesh or nmesh < 1:
            raise QgsProcessingException(self.invalidSourceError(parameters, "nmesh"))
        project.writeEntry("qgis2fds", "nmesh", nmesh)

        # Get parameter: cell_size

        cell_size = self.parameterAsDouble(parameters, "cell_size", context)
        if not cell_size:
            cell_size = pixel_size
            project.writeEntry("qgis2fds", "cell_size", "")
        elif cell_size <= 0.0:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "cell_size")
            )
        else:
            project.writeEntryDouble("qgis2fds", "cell_size", cell_size)

        # Get parameter: extent (and wgs84_extent)

        extent = self.parameterAsExtent(parameters, "extent", context)
        if not extent:
            raise QgsProcessingException(self.invalidSourceError(parameters, "extent"))
        project.writeEntry("qgis2fds", "extent", parameters["extent"])  # as str

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )

        # Get parameter: origin

        wgs84_origin = QgsPoint(wgs84_extent.center())
        origin = parameters.get("origin") or ""
        project.writeEntry("qgis2fds", "origin", origin)  # as str
        if origin:
            # prevent a QGIS bug when using parameterAsPoint with crs=wgs84_crs
            # the point is exported in project crs
            origin = self.parameterAsPoint(parameters, "origin", context)
            wgs84_origin = QgsPoint(origin)
            project_to_wgs84_tr = QgsCoordinateTransform(
                project.crs(), wgs84_crs, project
            )
            wgs84_origin.transform(project_to_wgs84_tr)

        # Get applicable UTM crs, then UTM origin and extent

        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        wgs84_to_utm_tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin = wgs84_origin.clone()
        utm_origin.transform(wgs84_to_utm_tr)

        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)

        # Get parameters: landuse_layer and landuse_type (optional)

        landuse_layer, landuse_type_filepath = None, None
        if "landuse_layer" in parameters and "landuse_type_filepath" in parameters:
            landuse_type_filepath = self.parameterAsFile(
                parameters, "landuse_type_filepath", context
            )
            landuse_layer = self.parameterAsRasterLayer(
                parameters, "landuse_layer", context
            )
            if landuse_layer and not landuse_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{landuse_layer.crs().description()}> is not valid, cannot proceed."
                )
            project.writeEntry(
                "qgis2fds", "landuse_layer", parameters.get("landuse_layer")
            )  # as str
            project.writeEntry(
                "qgis2fds", "landuse_type_filepath", landuse_type_filepath
            )

        landuse_type = LanduseType(
            feedback=feedback,
            project_path=project_path,
            filepath=landuse_type_filepath,
        )

        # Get parameter: fire_layer (optional)

        fire_layer, utm_fire_layer, utm_b_fire_layer = None, None, None
        if "fire_layer" in parameters:
            fire_layer = self.parameterAsVectorLayer(parameters, "fire_layer", context)
            if fire_layer:
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
            project.writeEntry(
                "qgis2fds", "fire_layer", parameters.get("fire_layer")
            )  # as str

        # Get devc_layer (optional)
        # devc_layer = None
        # if parameters["devc_layer"]:
        #     devc_layer = self.parameterAsVectorLayer(parameters, "devc_layer", context)
        #     if not devc_layer.crs().isValid():
        #         raise QgsProcessingException(
        #             f"DEVCs layer CRS <{devc_layer.crs().description()}> is not valid, cannot proceed."
        #         )
        # project.writeEntry("qgis2fds", "devc_layer", parameters["devc_layer"])

        # Get parameter: wind_filepath (optional)

        wind_filepath = self.parameterAsFile(parameters, "wind_filepath", context)
        project.writeEntry("qgis2fds", "wind_filepath", wind_filepath)

        wind = Wind(
            feedback=feedback, project_path=project_path, filepath=wind_filepath
        )

        # Get parameter: tex_layer (optional)

        tex_layer, texture = None, None
        if "tex_layer" in parameters:
            tex_layer = self.parameterAsRasterLayer(parameters, "tex_layer", context)
            if tex_layer and not tex_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Texture layer CRS <{tex_layer.crs().description()}> is not valid, cannot proceed."
                )
            project.writeEntry("qgis2fds", "tex_layer", parameters.get("tex_layer"))

        # Get parameter: tex_pixel_size

        tex_pixel_size = float(
            self.parameterAsDouble(parameters, "tex_pixel_size", context)
        )
        if not tex_pixel_size or tex_pixel_size <= 0.0:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "tex_pixel_size")
            )
        project.writeEntryDouble("qgis2fds", "tex_pixel_size", tex_pixel_size)

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
        # utm_devc_layer = None
        # if devc_layer:
        #     pass

        #     if feedback.isCanceled():
        #         return {}

        # Get parameter: export_obst

        export_obst = self.parameterAsBool(parameters, "export_obst", context)
        project.writeEntryBool("qgis2fds", "export_obst", export_obst)

        # Get parameter: dem_layer

        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        if not dem_layer:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "dem_layer")
            )
        if not dem_layer.crs().isValid():
            raise QgsProcessingException(
                f"DEM layer CRS <{dem_layer.crs().description()}> is not valid, cannot proceed."
            )
        project.writeEntry("qgis2fds", "dem_layer", parameters.get("dem_layer"))
        
        # Download WCS data and save as a geoTiff for processing with gdal
        epsg5070_extent = self.parameterAsExtent(parameters, "extent", context, crs=dem_layer.crs())
        algos.wcsToRaster(dem_layer, epsg5070_extent, os.path.join(os.environ['TMP'],'TEMPORARY_OUTPUT_DEM_CLIPPED.tif'))
        
        # Fill empty values in DEM layer with interpolation
        outputs['filled_dem_layer'] = algos.fill_dem_nan(
            context,
            feedback,
            raster_layer=os.path.join(os.environ['TMP'],'TEMPORARY_OUTPUT_DEM_CLIPPED.tif'),
            output=os.path.join(os.environ['TMP'],'TEMPORARY_OUTPUT_DEM_CLIPPED_FILLED.tif'),
        )
        filled_dem_layer = QgsRasterLayer(outputs['filled_dem_layer']['OUTPUT'],"filled_dem_layer")
        
        # Calc the interpolated DEM layer
        outputs["utm_dem_layer"] = algos.clip_and_interpolate_dem(
            context,
            feedback,
            dem_layer=filled_dem_layer,
            extent=utm_extent,
            extent_crs=utm_crs,
            pixel_size=pixel_size,
            # output=parameters["utm_dem_layer"],  # DEBUG
        )

        if feedback.isCanceled():
            return {}
        
        # This allows us to visualize the state of the variable in a python display
        #from osgeo import gdal
        #gd = gdal.Open(str(outputs["utm_dem_layer"]['OUTPUT']))
        #d = gd.ReadAsArray()
        #from PIL import Image
        #img = Image.fromarray(d, 'I;16')
        #img.show()
        
        # This allows us to add a generated file to QGIS GUI display as a layer
        #layer = QgsRasterLayer(out_file, "result")
        #QgsProject.instance().addMapLayer(layer)

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

        # Prepare terrain, domain, and fds_case
        if export_obst:
            Terrain = OBSTTerrain
        else:
            Terrain = GEOMTerrain
        terrain = Terrain(
            feedback=feedback,
            sampling_layer=sampling_layer,
            utm_origin=utm_origin,
            landuse_layer=landuse_layer,
            landuse_type=landuse_type,
            fire_layer=fire_layer,
            path=fds_path,
            name=chid,
        )

        if feedback.isCanceled():
            return {}

        domain = Domain(
            feedback=feedback,
            utm_crs=utm_crs,
            utm_extent=utm_extent,
            utm_origin=utm_origin,
            wgs84_origin=wgs84_origin,
            min_z=terrain.min_z,
            max_z=terrain.max_z,
            cell_size=cell_size,
            nmesh=nmesh,
        )

        fds_case = FDSCase(
            feedback=feedback,
            path=fds_path,
            name=chid,
            utm_crs=utm_crs,
            wgs84_origin=wgs84_origin,
            pixel_size=pixel_size,
            dem_layer=dem_layer,
            domain=domain,
            terrain=terrain,
            texture=texture,
            wind=wind,
        )
        fds_case.save()

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
