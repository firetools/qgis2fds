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

import os

from qgis.core import (
    QgsGeometry,
    QgsMapSettings,
    QgsPrintLayout,
    QgsMapSettings,
    QgsMapRendererParallelJob,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPolygon,
    QgsLayoutItemScaleBar,
    QgsLayoutExporter,
    QgsLayoutItem,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
    QgsProject,
    QgsFillSymbol,
)

from qgis.PyQt.QtGui import (
    QPolygonF,
    QColor,
)

from qgis.PyQt.QtCore import (
    QPointF,
    QRectF,
    QSize,
)

# from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsPoint,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorLayer,
    QgsProcessing,
    QgsProcessingException,
    # QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    # QgsProcessingParameterFeatureSource,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    # QgsProcessingParameterFileDestination,
    QgsExpressionContextUtils,
    QgsProcessingParameterEnum,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterPoint,
)
import qgis.utils
import processing
from qgis.utils import iface


from . import utm, utils, fds, geometry


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
            QgsProcessingParameterRasterLayer(
                "dem_layer", "DEM Layer", defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "origin", "Domain Origin", optional=True, defaultValue="",
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
                "Landuse Type",
                options=["Landfire FBFM13", "CIMA Propagator"],  # TODO auto
                allowMultiple=False,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "fire_origin", "Fire Origin", optional=True, defaultValue=""
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "devc_layer",
                "DEVCs layer [Not implemented]",  # TODO
                optional=True,
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
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
                defaultValue="",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "Final",
                "Final",
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        """
        Process algorithm.
        """
        feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
        results = {}
        outputs = {}

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Starting...")

        # Get input parameters
        dem_layer = self.parameterAsRasterLayer(parameters, "dem_layer", context)
        origin = self.parameterAsPoint(parameters, "origin", context)
        landuse_layer = self.parameterAsRasterLayer(
            parameters, "landuse_layer", context
        )
        landuse_type = self.parameterAsEnum(parameters, "landuse_type", context)
        fire_origin = self.parameterAsPoint(parameters, "fire_origin", context)
        devc_layer = self.parameterAsVectorLayer(parameters, "devc_layer", context)
        chid = self.parameterAsString(parameters, "chid", context)
        path = self.parameterAsFile(parameters, "path", context)

        # Check DEM layer type
        if dem_layer.providerType() != "gdal":
            raise QgsProcessingException(
                f"Bad DEM type: <{dem_layer.providerType()}>"
            )  # TODO other sources?

        # Prepare transformations
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dem_crs = dem_layer.crs()
        project_crs = QgsProject.instance().crs()

        dem_to_wgs84_tr = QgsCoordinateTransform(
            dem_crs, wgs84_crs, QgsProject.instance()
        )

        project_to_wgs84_tr = QgsCoordinateTransform(
            project_crs, wgs84_crs, QgsProject.instance()
        )

        # Get DEM layer extent
        dem_extent = dem_layer.extent()

        # Get origin in WGS84
        if parameters["origin"] is not None:
            origin = QgsPoint(origin)
            origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User origin: <{origin}>")
        else:
            origin = QgsPoint(
                (dem_extent.xMinimum() + dem_extent.xMaximum()) / 2.0,
                (dem_extent.yMinimum() + dem_extent.yMaximum()) / 2.0,
            )  # use DEM centroid as origin
            origin.transform(dem_to_wgs84_tr)
            feedback.pushInfo(f"DEM centroid origin: <{origin}>")
        utm_origin_py = utm.LonLat(origin.x(), origin.y()).to_UTM()
        origin_x, origin_y = utm_origin_py.x, utm_origin_py.y

        # Get fire origin in WGS84
        if parameters["fire_origin"] is not None:
            fire_origin = QgsPoint(fire_origin)
            fire_origin.transform(project_to_wgs84_tr)
            feedback.pushInfo(f"User fire origin: <{fire_origin}>")
        else:
            fire_origin = origin  # use origin
            feedback.pushInfo(f"DEM centroid fire origin: <{fire_origin}>")
        utm_fire_origin_py = utm.LonLat(fire_origin.x(), fire_origin.y()).to_UTM()
        fire_origin_x, fire_origin_y = (
            utm_fire_origin_py.x,
            utm_fire_origin_py.y,
        )

        # Get UTM CRS from origin
        utm_crs = QgsCoordinateReferenceSystem(utm_origin_py.epsg)
        feedback.pushInfo(f"Optimal UTM CRS: <{utm_crs.description()}>")

        # Save texture
        feedback.pushInfo("Saving texture image...")
        utils.write_image(
            destination_crs=utm_crs,
            extent=dem_extent,
            filepath=f"{path}/{chid}_texture.jpg",
            imagetype="jpg",
        )

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # QGIS geographic transformations

        feedback.pushInfo("Creating sampling grid layer from DEM...")
        alg_params = {
            "FIELD_NAME": "zcoord",
            "INPUT_RASTER": parameters["dem_layer"],
            "RASTER_BAND": 1,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["RasterPixelsToPoints"] = processing.run(
            "native:pixelstopoints",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Reprojecting sampling grid layer to UTM CRS...")
        alg_params = {
            "INPUT": outputs["RasterPixelsToPoints"]["OUTPUT"],
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

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

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

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Sampling landuse...")
        alg_params = {
            "COLUMN_PREFIX": "landuse",
            "INPUT": outputs["AddGeometryAttributes"]["OUTPUT"],
            "RASTERCOPY": parameters["landuse_layer"],
            "OUTPUT": parameters["Final"],
        }
        outputs["Final"] = processing.run(
            "qgis:rastersampling",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        results["Final"] = outputs["Final"]["OUTPUT"]

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Prepare geometry

        feedback.pushInfo("Building lists of vertices and faces with landuses...")

        point_layer = context.getMapLayer(outputs["Final"]["OUTPUT"])
        verts, faces, landuses = geometry.get_geometry(
            layer=point_layer, origin_x=origin_x, origin_y=origin_y
        )

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Writing the FDS case file...")

        # Prepare fire origin VENT

        x, y = fire_origin_x - origin_x, fire_origin_y - origin_y
        vent_str = "\n".join(
            (
                f"! Fire origin at <{utm_fire_origin_py}>",
                f"! Link: <{utm_fire_origin_py.to_url()}>",
                f"&SURF ID='Ignition' VEG_LSET_IGNITE_TIME=1800. COLOR='RED' /",
                f"&VENT XB={x-5:.3f},{x+5:.3f},{y-5:.3f},{y+5:.3f},-10.000,-10.000 SURF_ID='Ignition' GEOM=T /",
            )
        )

        # Prepare MESH

        mesh_str = "\n".join(
            (
                f"! Domain and its boundary conditions",
                f"&MESH IJK=50,50,50 XB=-500.000,500.000,-500.000,500.000,-10.000,1000.000 /",
                f"&TRNZ MESH_NUMBER=0 IDERIV=1 CC=0 PC=0.5 /",
                f"&VENT MB='XMIN' SURF_ID='OPEN' /",
                f"&VENT MB='XMAX' SURF_ID='OPEN' /",
                f"&VENT MB='YMIN' SURF_ID='OPEN' /",
                f"&VENT MB='YMAX' SURF_ID='OPEN' /",
                f"&VENT MB='ZMAX' SURF_ID='OPEN' /",
            )
        )

        # Prepare GEOM

        SURF_select = {
            0: {  # Landfire FBFM13
                0: 19,  # not available
                1: 1,
                2: 2,
                3: 3,
                4: 4,
                5: 5,
                6: 6,
                7: 7,
                8: 8,
                9: 9,
                10: 10,
                11: 11,
                12: 12,
                13: 13,
                91: 14,
                92: 15,
                93: 16,
                98: 17,
                99: 18,
            },
            1: {  # CIMA Propagator
                0: 19,  # not available
                1: 5,
                2: 4,
                3: 18,
                4: 10,
                5: 10,
                6: 1,
                7: 1,
            },
        }[landuse_type]

        surfid_str = "\n            ".join(
            (
                f"'A01','A02','A03','A04','A05','A06','A07','A08','A09','A10','A11','A12','A13',",
                f"'Urban','Snow-Ice','Agricolture','Water','Barren','NA'",
            )
        )

        verts_str = "\n            ".join(
            (f"{v[0]:.3f},{v[1]:.3f},{v[2]:.3f}," for v in verts)
        )

        faces_str = "\n            ".join(
            (
                f"{f[0]},{f[1]},{f[2]},{SURF_select.get(landuses[i], landuses[0])},"
                for i, f in enumerate(faces)
            )
        )

        geom_str = "\n".join(
            (
                f"! Terrain",
                f"&GEOM ID='Terrain' IS_TERRAIN=T EXTEND_TERRAIN=F",
                f"      SURF_ID={surfid_str}",
                f"      VERTS={verts_str}",
                f"      FACES={faces_str} /",
            )
        )

        # Prepare header
        import time

        # pv = qgis.utils.pluginMetadata("QGIS2FDS", "version")  # FIXME
        qv = QgsExpressionContextUtils.globalScope().variable("qgis_version")
        now = time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())
        filepath = QgsProject.instance().fileName()  # bpy.data.filepath or "not saved"
        if len(filepath) > 60:
            filepath = "..." + filepath[-57:]

        # Prepare FDS case

        case_str = "\n".join(
            (
                f"! Generated by QGIS2FDS plugin on QGIS <{qv}>",
                f"! File: <{filepath}>",
                f"! DEM layer: <{dem_layer.name()}>",
                f"! Landuse layer: <{landuse_layer.name()}>",
                f"! Landuse type: <{('Landfire FBFM13', 'CIMA Propagator')[landuse_type]}>",
                f"! CRS: <{utm_crs.description()}>",
                f"! Date: <{now}>",
                f" ",
                f"&HEAD CHID='{chid}' TITLE='Description of {chid}' /",
                f"&TIME T_END=0. /",
                f"&RADI RADIATION=F /",
                f" ",
                f"! Origin at <{utm_origin_py}>",
                f"! Link: <{utm_origin_py.to_url()}>",
                f" MISC ORIGIN_LAT={origin.y():.7f} ORIGIN_LON={origin.x():.7f} NORTH_BEARING=0. / ! New",
                f"&MISC TERRAIN_CASE=T SIMULATION_MODE='SVLES' TERRAIN_IMAGE='{chid}_texture.jpg' /",
                f" ",
                f"! Reaction",
                f"! from Karlsson, Quintiere 'Enclosure Fire Dyn', CRC Press, 2000",
                f"&REAC ID='Wood' FUEL='PROPANE', SOOT_YIELD=0.015 /",
                f" ",
                f"{mesh_str}",
                f" ",
                f"{vent_str}",
                f" ",
                f"! Output quantities",
                f"&BNDF QUANTITY='BURNING RATE' /",
                f"&SLCF DB='ZMID', QUANTITY='VELOCITY', VECTOR=T /",
                f"&SLCF AGL_SLICE=25., QUANTITY='VELOCITY', VECTOR=T /",
                f"&SLCF AGL_SLICE=1., QUANTITY='LEVEL SET VALUE' /",
                f" ",
                f"! Wind",
                f"&WIND SPEED=1., RAMP_SPEED='ws', RAMP_DIRECTION='wd', LATITUDE={origin.y():.7f}, DT_MEAN_FORCING=20. /",
                f"&RAMP ID='ws', T=0, F=0. /",
                f"&RAMP ID='ws', T=600, F=10. /",
                f"&RAMP ID='ws', T=1200, F=20. /",
                f"&RAMP ID='wd', T=0, F=330. /",
                f"&RAMP ID='wd', T=600, F=300. /",
                f"&RAMP ID='wd', T=1200, F=270. /",
                f" ",
                f"! Boundary conditions",
                f"! 13 Anderson Fire Behavior Fuel Models",  # FIXME
                # f"&SURF ID='A01' RGB=255,252,167 VEG_LSET_FUEL_INDEX= 1 HRRPUA=100. RAMP_Q='f01' /",  # FIXME RGB and other
                # f"&SURF ID='A02' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 2 HRRPUA=500. RAMP_Q='f02' /",
                # f"&SURF ID='A03' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 3 HRRPUA=500. RAMP_Q='f03' /",
                # f"&SURF ID='A04' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 4 HRRPUA=500. RAMP_Q='f04' /",
                # f"&SURF ID='A05' RGB=241,142, 27 VEG_LSET_FUEL_INDEX= 5 HRRPUA=500. RAMP_Q='f05' /",
                # f"&SURF ID='A06' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 6 HRRPUA=500. RAMP_Q='f06' /",
                # f"&SURF ID='A07' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 7 HRRPUA=500. RAMP_Q='f07' /",
                # f"&SURF ID='A08' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 8 HRRPUA=500. RAMP_Q='f08' /",
                # f"&SURF ID='A09' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 9 HRRPUA=500. RAMP_Q='f09' /",
                # f"&SURF ID='A10' RGB= 42, 82, 23 VEG_LSET_FUEL_INDEX=10 HRRPUA=500. RAMP_Q='f10' /",
                # f"&SURF ID='A11' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=11 HRRPUA=500. RAMP_Q='f11' /",
                # f"&SURF ID='A12' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=12 HRRPUA=500. RAMP_Q='f12' /",
                # f"&SURF ID='A13' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=13 HRRPUA=500. RAMP_Q='f13' /",
                f"&SURF ID='A01' RGB=255,252,167 HRRPUA=100. RAMP_Q='f01' /",  # FIXME RGB and other
                f"&SURF ID='A02' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f02' /",
                f"&SURF ID='A03' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f03' /",
                f"&SURF ID='A04' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f04' /",
                f"&SURF ID='A05' RGB=241,142, 27 HRRPUA=500. RAMP_Q='f05' /",
                f"&SURF ID='A06' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f06' /",
                f"&SURF ID='A07' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f07' /",
                f"&SURF ID='A08' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f08' /",
                f"&SURF ID='A09' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f09' /",
                f"&SURF ID='A10' RGB= 42, 82, 23 HRRPUA=500. RAMP_Q='f10' /",
                f"&SURF ID='A11' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f11' /",
                f"&SURF ID='A12' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f12' /",
                f"&SURF ID='A13' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f13' /",
                f"&SURF ID='Urban' RGB= 59, 81, 84 /",
                f"&SURF ID='Snow-Ice' RGB= 59, 81, 84 /",
                f"&SURF ID='Agricolture' RGB= 59, 81, 84 /",
                f"&SURF ID='Water' RGB= 59, 81, 84 /",
                f"&SURF ID='Barren' RGB= 59, 81, 84 /",
                f"&SURF ID='NA' RGB=204,204,204 /",
                f" ",
                f"&RAMP ID='f01', T= 0., F=0. /",
                f"&RAMP ID='f01', T= 5., F=1. /",
                f"&RAMP ID='f01', T=25., F=1. /",
                f"&RAMP ID='f01', T=30., F=0. /",
                f" ",
                f"&RAMP ID='f02', T=  0., F=0. /",
                f"&RAMP ID='f02', T=  5., F=1. /",
                f"&RAMP ID='f02', T=115., F=1. /",
                f"&RAMP ID='f02', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f03', T=  0., F=0. /",
                f"&RAMP ID='f03', T=  5., F=1. /",
                f"&RAMP ID='f03', T=115., F=1. /",
                f"&RAMP ID='f03', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f04', T=  0., F=0. /",
                f"&RAMP ID='f04', T=  5., F=1. /",
                f"&RAMP ID='f04', T=115., F=1. /",
                f"&RAMP ID='f04', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f05', T= 0., F=0. /",
                f"&RAMP ID='f05', T= 5., F=1. /",
                f"&RAMP ID='f05', T=35., F=1. /",
                f"&RAMP ID='f05', T=40., F=0. /",
                f" ",
                f"&RAMP ID='f06', T=  0., F=0. /",
                f"&RAMP ID='f06', T=  5., F=1. /",
                f"&RAMP ID='f06', T=115., F=1. /",
                f"&RAMP ID='f06', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f07', T=  0., F=0. /",
                f"&RAMP ID='f07', T=  5., F=1. /",
                f"&RAMP ID='f07', T=115., F=1. /",
                f"&RAMP ID='f07', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f08', T=  0., F=0. /",
                f"&RAMP ID='f08', T=  5., F=1. /",
                f"&RAMP ID='f08', T=115., F=1. /",
                f"&RAMP ID='f08', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f09', T=  0., F=0. /",
                f"&RAMP ID='f09', T=  5., F=1. /",
                f"&RAMP ID='f09', T=115., F=1. /",
                f"&RAMP ID='f09', T=120., F=0. /",
                f" ",
                f"&RAMP ID='f10', T= 0., F=0. /",
                f"&RAMP ID='f10', T= 5., F=1. /",
                f"&RAMP ID='f10', T=85., F=1. /",
                f"&RAMP ID='f10', T=90., F=0. /",
                f" ",
                f"&RAMP ID='f11', T= 0., F=0. /",
                f"&RAMP ID='f11', T= 5., F=1. /",
                f"&RAMP ID='f11', T=85., F=1. /",
                f"&RAMP ID='f11', T=90., F=0. /",
                f" ",
                f"&RAMP ID='f12', T= 0., F=0. /",
                f"&RAMP ID='f12', T= 5., F=1. /",
                f"&RAMP ID='f12', T=85., F=1. /",
                f"&RAMP ID='f12', T=90., F=0. /",
                f" ",
                f"&RAMP ID='f13', T= 0., F=0. /",
                f"&RAMP ID='f13', T= 5., F=1. /",
                f"&RAMP ID='f13', T=85., F=1. /",
                f"&RAMP ID='f13', T=90., F=0. /",
                f" ",
                f"{geom_str}",
            )
        )

        # Write FDS file
        utils.write_file(filepath=f"{path}/{chid}.fds", content=case_str)

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
