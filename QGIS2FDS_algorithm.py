# -*- coding: utf-8 -*-

# FIXME
# MISC: export image
# SURF: RGB and name from from style?
# Insert DEVCs

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

import math
from . import utm


class QGIS2FDSAlgorithm(QgsProcessingAlgorithm):
    """
    TODO
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

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
                "origin", "Domain origin point", optional=True, defaultValue="",
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
                "Landuse type",
                options=["Landfire FBFM13", "CIMA Propagator"],  # FIXME auto
                allowMultiple=False,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "fire_origin", "Fire origin point", optional=True, defaultValue=""
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "devc_layer",
                "DEVCs layer [Not implemented]",  # FIXME
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
                defaultValue="./",
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
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        # Get parameters
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

        # feedback.pushInfo(
        #     f"Input: {origin, landuse_type, fire_origin, devc_layer, chid, path}"
        # )  # FIXME

        # Check
        if dem_layer.providerType() != "gdal":
            raise QgsProcessingException(f"Bad DEM type: <{dem_layer.providerType()}>")
        if not chid:
            raise QgsProcessingException("CHID cannot be empty!")

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
        if origin:  # user
            origin = QgsPoint(origin)
            origin.transform(project_to_wgs84_tr)
        else:  # use DEM centroid
            origin = QgsPoint(
                (dem_extent.xMinimum() + dem_extent.xMaximum()) / 2.0,
                (dem_extent.yMinimum() + dem_extent.yMaximum()) / 2.0,
            )
            origin.transform(dem_to_wgs84_tr)
        utm_origin_py = utm.LonLat(origin.x(), origin.y()).to_UTM()
        origin_x, origin_y = utm_origin_py.easting, utm_origin_py.northing

        # Get fire origin in WGS84
        if fire_origin:  # user
            fire_origin = QgsPoint(fire_origin)
            fire_origin.transform(project_to_wgs84_tr)
        else:  # use origin
            fire_origin = origin
        utm_fire_origin_py = utm.LonLat(fire_origin.x(), fire_origin.y()).to_UTM()
        fire_origin_x, fire_origin_y = (
            utm_fire_origin_py.easting,
            utm_fire_origin_py.northing,
        )

        # Get UTM CRS from origin
        utm_crs = QgsCoordinateReferenceSystem(utm_origin_py.epsg)

        # QGIS geographic transformations

        # DEM raster pixels to points
        feedback.pushInfo("Creating grid of points from DEM")
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

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Reproject layer
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

        # Add x, y geometry attributes
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

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Sample raster values
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

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # FIXME
        # results["Final"] = outputs["Final"]["OUTPUT"]
        # return results

        # Build the matrix of quad faces center points

        # · center points of quad faces
        # o verts
        #            j
        #      o   o   o   o   o
        #        ·   ·   ·   ·
        #      o   *---*   o   o
        # row    · | · | ·   ·   i
        #      o   *---*   o   o
        #        ·   ·   ·   ·
        #      o   o   o   o   o

        point_layer = context.getMapLayer(outputs["Final"]["OUTPUT"])
        features = point_layer.getFeatures()

        def get_norm(vector):
            return math.sqrt(vector[0] ** 2 + vector[1] ** 2)

        def dot_product(p0, p1, p2):
            v0 = [p1[0] - p0[0], p1[1] - p0[1]]
            v1 = [p2[0] - p0[0], p2[1] - p0[1]]
            return (v0[0] * v1[0] + v0[1] * v1[1]) / (get_norm(v0) * get_norm(v1))

        first_point = None
        prev_point = None
        for f in features:
            a = f.attributes()  # order: z, x, y, landuse
            point = (
                a[1] - origin_x,  # x, relative to origin
                a[2] - origin_y,  # y, relative to origin
                a[0],  # z absolute
                a[3],  # landuse
            )
            if first_point is None:
                # point is the first point of the matrix
                matrix = [[point,]]
                first_point = point
                continue
            elif prev_point is None:
                # point is the second point of the matrix row
                matrix[-1].append(point)
                prev_point = point
                continue
            # current point is another point, check alignment in 2D
            if abs(dot_product(first_point, prev_point, point)) > 0.1:
                # point is on the same matrix row
                matrix[-1].append(point)
                prev_point = point
                continue
            # point is on the next row
            matrix.append(
                [point,]
            )
            first_point = point
            prev_point = None

        # Build the connectivity into the face list

        #        j   j  j+1
        #        *<------* i
        #        | f1 // |
        # faces  |  /·/  | i
        #        | // f2 |
        #        *------>* i+1

        def get_vert_index(i, j, len_vrow):
            # F90 indexes start from 1, so +1
            return i * len_vrow + j + 1

        def get_f1(i, j, len_vrow):
            return (
                get_vert_index(i, j, len_vrow),
                get_vert_index(i + 1, j, len_vrow),
                get_vert_index(i, j + 1, len_vrow),
            )

        def get_f2(i, j, len_vrow):
            return (
                get_vert_index(i + 1, j + 1, len_vrow),
                get_vert_index(i, j + 1, len_vrow),
                get_vert_index(i + 1, j, len_vrow),
            )

        faces, landuses = list(), list()
        len_vrow = len(matrix[0]) + 1
        for i, row in enumerate(matrix):
            for j, p in enumerate(row):
                faces.extend((get_f1(i, j, len_vrow), get_f2(i, j, len_vrow)))
                landuses.extend((p[3], p[3]))

        # Inject ghost centers in the point matrix (use a copy)

        # · centers of quad faces  + ghost centers
        # o verts  * cs  x vert
        #
        #           dx     j  j+1
        #          + > +   +   +   +   +
        #       dy v o   o   o   o   o
        #          +   *   *   ·   ·   +
        #            o   x   o   o   o
        # pres_row +   *   *   ·   ·   +  i-1
        #            o   o---o   o   o
        #      row +   · | · | ·   ·   +  i
        #            o   o---o   o   o
        #          +   +   +   +   +   +

        # Calc displacements for ghost centers
        fsub = lambda a: a[0] - a[1]
        fadd = lambda a: a[0] + a[1]
        dx = list(map(fsub, zip(matrix[0][1], matrix[0][0])))
        dy = list(map(fsub, zip(matrix[1][0], matrix[0][0])))
        dx[2], dy[2] = 0.0, 0.0  # no vertical displacement for ghost centers (smoother)

        # Insert new first ghost row
        row = list(tuple(map(fsub, zip(c, dy))) for c in matrix[0])
        matrix.insert(0, row)

        # Append new last ghost row
        row = list(tuple(map(fadd, zip(c, dy))) for c in matrix[-1])
        matrix.append(row)

        # Insert new first and last ghost col
        for row in matrix:
            # new first ghost col
            gc = tuple(map(fsub, zip(row[0], dx)))
            row.insert(0, gc)
            # new last ghost col
            gc = tuple(map(fadd, zip(row[-1], dx)))
            row.append(gc)

        # Build the vert list

        #              j      j+1
        # prev_row     *       * i-1
        #
        #          o-------x
        #          |       |
        #      row |   *   |   * i
        #          |       |
        #          o-------o

        def get_neighbour_centers(prev_row, row, j):
            return (
                prev_row[j][:-1],  # rm landuse from center (its last value)
                prev_row[j + 1][:-1],
                row[j][:-1],
                row[j + 1][:-1],
            )

        def avg(l):
            return sum(l) / len(l)

        def get_vert(neighbour_centers):
            return tuple(
                map(avg, zip(*neighbour_centers))
            )  # avg of centers coordinates

        verts = list()
        prev_row = matrix[0]
        for row in matrix[1:]:  # matrix[0] is prev_row
            for j, _ in enumerate(row[:-1]):
                verts.append(get_vert(get_neighbour_centers(prev_row, row, j)))
            prev_row = row

        # FDS file

        # Prepare fire origin VENT

        x, y = fire_origin_x - origin_x, fire_origin_y - origin_y
        vent_str = "\n".join(
            (
                f"! Fire origin at <{utm_fire_origin_py}>",
                f"! Link: <{utm_fire_origin_py.to_url()}>",
                f"&SURF ID='Ignition', VEG_LSET_IGNITE_TIME=1800, COLOR='RED' /",
                f"&VENT XB={x-5:.3f},{x+5:.3f},{y-5:.3f},{y+5:.3f},-10.000,-10.000, SURF_ID='Ignition', GEOM=T /",
            )
        )

        # Prepare MESH

        mesh_str = "\n".join(
            (
                f"! Domain and its boundary conditions",
                f"&MESH IJK=50,50,50 XB=-500.000,500.000,-500.000,500.000,-10.000,1000.000 /",  # FIXME
                f"&TRNZ MESH_NUMBER=0, IDERIV=1, CC=0, PC=0.5 /",
                f"&VENT MB='XMIN', SURF_ID='OPEN' /",
                f"&VENT MB='XMAX', SURF_ID='OPEN' /",
                f"&VENT MB='YMIN', SURF_ID='OPEN' /",
                f"&VENT MB='YMAX', SURF_ID='OPEN' /",
                f"&VENT MB='ZMAX', SURF_ID='OPEN' /",
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
                f"&GEOM ID='Terrain'",
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
                f"&MISC ORIGIN_LAT={origin.y():.7f} ORIGIN_LON={origin.x():.7f}",
                f"      TERRAIN_CASE=T TERRAIN_IMAGE='{chid}_texture.jpg' /",
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
                f"&SURF ID='A01' RGB=255,252,167 VEG_LSET_FUEL_INDEX= 1 HRRPUA=100. RAMP_Q='f01' /",  # FIXME RGB and other
                f"&SURF ID='A02' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 2 HRRPUA=500. RAMP_Q='f02' /",
                f"&SURF ID='A03' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 3 HRRPUA=500. RAMP_Q='f03' /",
                f"&SURF ID='A04' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 4 HRRPUA=500. RAMP_Q='f04' /",
                f"&SURF ID='A05' RGB=241,142, 27 VEG_LSET_FUEL_INDEX= 5 HRRPUA=500. RAMP_Q='f05' /",
                f"&SURF ID='A06' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 6 HRRPUA=500. RAMP_Q='f06' /",
                f"&SURF ID='A07' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 7 HRRPUA=500. RAMP_Q='f07' /",
                f"&SURF ID='A08' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 8 HRRPUA=500. RAMP_Q='f08' /",
                f"&SURF ID='A09' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 9 HRRPUA=500. RAMP_Q='f09' /",
                f"&SURF ID='A10' RGB= 42, 82, 23 VEG_LSET_FUEL_INDEX=10 HRRPUA=500. RAMP_Q='f10' /",
                f"&SURF ID='A11' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=11 HRRPUA=500. RAMP_Q='f11' /",
                f"&SURF ID='A12' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=12 HRRPUA=500. RAMP_Q='f12' /",
                f"&SURF ID='A13' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=13 HRRPUA=500. RAMP_Q='f13' /",
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

        try:
            with open(f"{path}/{chid}.fds", "w") as f:
                f.write(case_str)
        except IOError:
            raise QgsProcessingException(
                f"FDS file not writable at <{path}/{chid}.fds>"
            )

        return {}

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
