# -*- coding: utf-8 -*-

"""debug_algorithms"""

__author__ = "Jonathan Hodges"
__date__ = "2023-07-17"
__copyright__ = "(C) 2023 by Jonathan Hodges"
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
    QgsRasterProjector,
    QgsRasterFileWriter,
    QgsRectangle,
    QgsProcessing,
    QgsVectorLayer
)

import os, sys, gc
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
    "export_obst": False,
    "addIntermediateLayersToQgis": False,
    "debug": False,
    "sampling_layer": ""
}

try:
    import git
    systemdir = os.sep.join(__file__.split(os.sep)[:-1])
    repo = git.Repo(systemdir)
    sha = repo.head.object.hexsha
    githash = sha[:7]
    if repo.is_dirty():
        githash = githash + '-dirty'
except:
    githash = ''

class debug_terrain(QgsProcessingAlgorithm):
    """
    Reextract terrain algorithm.
    """

    def initAlgorithm(self, config=None):
        """!
        Inputs and outputs of the algorithm.
        """
        
        project = QgsProject.instance()
        
        # Define parameter: chid
        defaultValue, _ = project.readEntry("debug_terrain", "chid", DEFAULTS["chid"])
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
            "debug_terrain", "fds_path", DEFAULTS["fds_path"]
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

        defaultValue, _ = project.readEntry("debug_terrain", "extent", DEFAULTS["extent"])
        self.addParameter(
            QgsProcessingParameterExtent(
                "extent",
                "Domain extent",
                defaultValue=defaultValue,
                optional=True,
            )
        )
        
        # Define parameter: landuse_layer [optional]

        defaultValue, _ = project.readEntry(
            "debug_terrain", "landuse_layer", DEFAULTS["landuse_layer"]
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
            "debug_terrain", "landuse_type_filepath", DEFAULTS["landuse_type_filepath"]
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

        # Define parameter: export_obst

        defaultValue, _ = project.readBoolEntry(
            "debug_terrain", "export_obst", DEFAULTS["export_obst"]
        )
        param = QgsProcessingParameterBoolean(
            "export_obst",
            "Export FDS OBSTs",
            defaultValue=defaultValue,
        )
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        

    def processAlgorithm(self, parameters, context, feedback):
        """
        Process algorithm.
        """
        
        results, project = {}, QgsProject.instance()

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
        
        # Establish os specific parameters directory
        
        if sys.platform.startswith('linux'):
            pass
        elif sys.platform == 'darwin':
            os.environ["PROJ_LIB"]="/Applications/QGIS.app/Contents/Resources/proj"
        elif (sys.platform == 'win32') or (sys.platform == 'cygwin'):
            pass
        
        # Get sampling layer
        sampling_layer_file = self.parameterAsString(parameters, "sampling_layer", context)
        if sampling_layer_file == "":
            sampling_layer_file = os.path.join(project_path,"debug_%s_Sampled.gpkg"%(chid))
            sampling_layer = QgsVectorLayer(sampling_layer_file, "sampling_layer")
        elif type(sampling_layer_file) == QgsVectorLayer:
            sampling_layer = sampling_layer_file
        else:
            sampling_layer = QgsVectorLayer(sampling_layer_file, "sampling_layer")
        
        # Get landuse layer
        landuse_layer_file = self.parameterAsString(parameters, "landuse_layer", context)
        if landuse_layer_file == "":
            landuse_layer_file = os.path.join(project_path,"%s_LAND_CLIPPED.tif"%(chid))
            landuse_layer = QgsRasterLayer(landuse_layer_file, "land_use_layer")
        elif type(landuse_layer_file) == QgsVectorLayer:
            landuse_layer = landuse_layer_file
        else:
            landuse_layer = QgsRasterLayer(landuse_layer_file, "land_use_layer")
        
        # Get fire layer
        fire_layer_file = self.parameterAsString(parameters, "fire_layer", context)
        fire_layer = False
        if fire_layer_file == "":
            fire_layer_file = os.path.join(project_path,"%s_FIRE_CLIPPED.gpkg"%(chid))
            if os.path.exists(fire_layer_file):
                fire_layer = QgsVectorLayer(fire_layer_file, "fire_layer")
        elif type(fire_layer_file) == QgsVectorLayer:
            fire_layer = fire_layer_file
        else:
            if os.path.exists(fire_layer_file):
                fire_layer = QgsVectorLayer(fire_layer_file, "fire_layer")
        
        # Get parameter: extent (and wgs84_extent)
        extent = sampling_layer.extent()
        if not extent:
            raise QgsProcessingException(self.invalidSourceError(parameters, "extent"))
        project.writeEntry("debug_terrain", "extent", parameters["extent"])  # as str
        
        # Get parameter: origin
        
        extent_origin = QgsPoint(extent.center())
        extent_crs = sampling_layer.crs()
        
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        extent_to_wgs84 = QgsCoordinateTransform(extent_crs, wgs84_crs, project)
        wgs84_extent = extent_to_wgs84.transformBoundingBox(extent)
        wgs84_origin = QgsPoint(wgs84_extent.center())
        #wgs84_extent = self.parameterAsExtent(parameters, "extent", context, crs=wgs84_crs)
        
        # Get applicable UTM crs, then UTM origin and extent

        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)

        extent_to_utm_tr = QgsCoordinateTransform(extent_crs, utm_crs, project)
        utm_origin = extent_origin.clone()
        utm_origin.transform(extent_to_utm_tr)
        
        export_obst = self.parameterAsBool(parameters, "export_obst", context)
        
        landuse_type_filepath = self.parameterAsFile(parameters, "landuse_type_filepath", context)
        project.writeEntry("debug_terrain", "landuse_type_filepath", landuse_type_filepath
            )
        landuse_type = LanduseType(
            feedback=feedback,
            project_path=project_path,
            filepath=landuse_type_filepath,
        )
        
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
        
        if export_obst:
            pass
        else:
            terrain.get_fds()
        return results

    def name(self):
        """!
        Returns the algorithm name.
        """
        return "(Debug) Re-Export terrain"

    def displayName(self):
        """!
        Returns the translated algorithm name.
        """
        if githash != '':
            return "%s (%s)"%(self.name(), githash)
        else:
            return "(Debug) Re-Export terrain"

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
        return debug_terrain()
