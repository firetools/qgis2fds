# -*- coding: utf-8 -*-

"""extractServerLayer"""

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
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsRasterLayer
)

import os, sys
from .types import utils
from . import algos

DEFAULTS = {
    "chid": "terrain",
    "fds_path": "./",
    "extent": None,
    "pixel_size": 10.0,
    "origin": None,
    "dem_layer": None,
    "landuse_layer": None,
    "landuse_type_filepath": "",
    "tex_layer": None,
    "tex_pixel_size": 5.0,
    "debug": False,
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


class extractServerLayerAlgorithm(QgsProcessingAlgorithm):
    """
    extractServerLayerAlgorithm algorithm.
    """

    def initAlgorithm(self, config=None):
        """!
        Inputs and outputs of the algorithm.
        """
        project = QgsProject.instance()
        
        # Define parameter: chid
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "chid", DEFAULTS["chid"])
        self.addParameter(QgsProcessingParameterString("chid","FDS case identificator (CHID)",multiLine=False,defaultValue=defaultValue))
        
        # Define parameter: fds_path
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "fds_path", DEFAULTS["fds_path"])
        self.addParameter(QgsProcessingParameterFile("fds_path","Save in folder",behavior=QgsProcessingParameterFile.Folder,fileFilter="All files (*.*)",defaultValue=defaultValue))
        
        # Define parameter: extent
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "extent", DEFAULTS["extent"])
        self.addParameter(QgsProcessingParameterExtent("extent","Domain extent",defaultValue=defaultValue))
        
        # Define parameter: pixel_size
        
        defaultValue, _ = project.readDoubleEntry("extractServerLayerAlgorithm", "pixel_size", DEFAULTS["pixel_size"])
        self.addParameter(QgsProcessingParameterNumber("pixel_size","Desired resolution (in meters)",type=QgsProcessingParameterNumber.Double,defaultValue=defaultValue,minValue=0.1))
        
        # Define parameter: dem_layer
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "dem_layer", DEFAULTS["dem_layer"])
        if not defaultValue:
            try:  # first layer name containing "dem"
                defaultValue = [
                    layer.name()
                    for layer in QgsProject.instance().mapLayers().values()
                    if "DEM" in layer.name() or "dem" in layer.name()
                ][0]
            except IndexError:
                pass
        self.addParameter(QgsProcessingParameterRasterLayer("dem_layer","DEM layer",defaultValue=defaultValue))
        
        # Define parameter: landuse_layer [optional]
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "landuse_layer", DEFAULTS["landuse_layer"])
        self.addParameter(QgsProcessingParameterRasterLayer("landuse_layer","Landuse layer (if not set, landuse is not exported)",optional=True,defaultValue=defaultValue))
        
        # Define parameter: tex_layer [optional]
        
        defaultValue, _ = project.readEntry("extractServerLayerAlgorithm", "tex_layer", DEFAULTS["tex_layer"])
        param = QgsProcessingParameterRasterLayer("tex_layer","Texture layer (if not set, export current view)",optional=True,defaultValue=defaultValue)
        self.addParameter(param)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        
        # Define parameter: tex_pixel_size [optional]
        
        defaultValue, _ = project.readDoubleEntry("extractServerLayerAlgorithm", "tex_pixel_size", DEFAULTS["tex_pixel_size"])
        param = QgsProcessingParameterNumber("tex_pixel_size","Texture layer pixel size (in meters)",type=QgsProcessingParameterNumber.Double,defaultValue=defaultValue,minValue=0.1)
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
        project.writeEntry("extractServerLayerAlgorithm", "chid", chid)
        
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
        project.writeEntry("extractServerLayerAlgorithm", "fds_path", fds_path)
        fds_path = os.path.join(project_path, fds_path)  # make abs
        
        # Establish os specific parameters directory
        
        if sys.platform.startswith('linux'):
            pass
        elif sys.platform == 'darwin':
            os.environ["PROJ_LIB"]="/Applications/QGIS.app/Contents/Resources/proj"
        elif (sys.platform == 'win32') or (sys.platform == 'cygwin'):
            pass
        
        # Get parameter: pixel_size

        pixel_size = self.parameterAsDouble(parameters, "pixel_size", context)
        if not pixel_size or pixel_size <= 0.0:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, "pixel_size")
            )
        project.writeEntryDouble("extractServerLayerAlgorithm", "pixel_size", pixel_size)

        # Get parameter: extent (and wgs84_extent)

        extent = self.parameterAsExtent(parameters, "extent", context)
        if not extent:
            raise QgsProcessingException(self.invalidSourceError(parameters, "extent"))
        project.writeEntry("extractServerLayerAlgorithm", "extent", parameters["extent"])  # as str

        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wgs84_extent = self.parameterAsExtent(
            parameters, "extent", context, crs=wgs84_crs
        )

        # Get parameter: origin

        wgs84_origin = QgsPoint(wgs84_extent.center())
        origin = parameters.get("origin") or ""
        project.writeEntry("qgis2fds", "origin", origin)  # as str
        
        # Get applicable UTM crs, then UTM origin and extent
        
        utm_epsg = utils.lonlat_to_epsg(lon=wgs84_origin.x(), lat=wgs84_origin.y())
        utm_crs = QgsCoordinateReferenceSystem(utm_epsg)
        
        wgs84_to_utm_tr = QgsCoordinateTransform(wgs84_crs, utm_crs, project)
        utm_origin = wgs84_origin.clone()
        utm_origin.transform(wgs84_to_utm_tr)
        
        utm_extent = self.parameterAsExtent(parameters, "extent", context, crs=utm_crs)
        
        # Get parameters: landuse_layer and landuse_type (optional)

        landuse_layer = None
        if "landuse_layer" in parameters:
            landuse_layer = self.parameterAsRasterLayer(parameters, "landuse_layer", context)
            if landuse_layer and not landuse_layer.crs().isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{landuse_layer.crs().description()}> is not valid, cannot proceed."
                )
            project.writeEntry("extractServerLayerAlgorithm", "landuse_layer", parameters.get("landuse_layer"))  # as str
        
        # Convert extents for terrain and texture
        
        fds_domain_extent = utm_extent
        if landuse_layer is not None:
            terrain_to_utm_transform = QgsCoordinateTransform(landuse_layer.crs(), utm_crs, project)
            utm_to_terrain_transform = QgsCoordinateTransform(utm_crs, landuse_layer.crs(), project)
            
            fds_terrain_extent_terrain = utm_to_terrain_transform.transformBoundingBox(fds_domain_extent)
            fds_terrain_extent_utm = terrain_to_utm_transform.transformBoundingBox(fds_terrain_extent_terrain)
        else:
            fds_terrain_extent_utm = utm_extent
        
        if ("tex_layer" in parameters) and (parameters['tex_layer'] is not None):
            tex_layer = self.parameterAsRasterLayer(parameters, "tex_layer", context)
            tex_to_utm_transform = QgsCoordinateTransform(tex_layer.crs(), utm_crs, project)
            utm_to_tex_transform = QgsCoordinateTransform(utm_crs, tex_layer.crs(), project)
            
            fds_texture_extent_tex = utm_to_tex_transform.transformBoundingBox(fds_terrain_extent_utm)
            fds_texture_extent_utm = tex_to_utm_transform.transformBoundingBox(fds_texture_extent_tex)
        else:
            fds_texture_extent_utm = fds_terrain_extent_utm
        
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
        project.writeEntry("extractServerLayerAlgorithm", "dem_layer", parameters.get("dem_layer"))
        
        # Convert extents for land use
        # Download WCS data and save as a geoTiff for processing with gdal
        if landuse_layer is not None:
            algos.wcsToRaster(landuse_layer, fds_terrain_extent_terrain, os.path.join(project_path,chid + '_LAND_CLIPPED.tif'))
            landuse_layer = QgsRasterLayer(os.path.join(project_path,chid + '_LAND_CLIPPED.tif'), "land_use_layer")
            QgsProject.instance().addMapLayer(landuse_layer)
            project.writeEntry("qgis2fds", "landuse_layer", landuse_layer.name())
        
        # Convert extents for DEM
        dem_to_utm_transform = QgsCoordinateTransform(dem_layer.crs(), utm_crs, project)
        utm_to_dem_transform = QgsCoordinateTransform(utm_crs, dem_layer.crs(), project)
        
        fds_dem_extent_dem = utm_to_dem_transform.transformBoundingBox(fds_texture_extent_utm)
        fds_dem_extent_utm = dem_to_utm_transform.transformBoundingBox(fds_dem_extent_dem)
        
        # Download WCS data and save as a geoTiff for processing with gdal
        algos.wcsToRaster(dem_layer, fds_dem_extent_dem, os.path.join(project_path, chid + '_DEM_CLIPPED.tif'))
        
        clipped_dem_layer = QgsRasterLayer(os.path.join(project_path, chid + '_DEM_CLIPPED.tif'), "clipped_dem_layer")
        QgsProject.instance().addMapLayer(clipped_dem_layer)
        
        # Update qgis2fds layers to extracted layers
        project.writeEntry("qgis2fds", "dem_layer", clipped_dem_layer.name())
        
        return results
        
    
    def name(self):
        """!
        Returns the algorithm name.
        """
        return "Extract server layer"

    def displayName(self):
        """!
        Returns the translated algorithm name.
        """
        if githash != '':
            return "%s (%s)"%(self.name(), githash)
        else:
            return "Extract server layer"

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
        return extractServerLayerAlgorithm()
