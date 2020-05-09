# -*- coding: utf-8 -*-

# FIXME
# MISC: export image
# SURF: RGB and name from from style? ready for anderson
# SURF: fix SURF_ID can be 99! &SURF lines
# GEOM ID
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
            QgsProcessingParameterRasterLayer("DEM", "DEM Layer", defaultValue=None)
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse", "Landuse Layer", defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "DEVCs",
                "DEVCs layer",
                optional=True,
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
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

        # Check DEM layer
        dem_layer = self.parameterAsRasterLayer(parameters, "DEM", context)
        if dem_layer.providerType() != "gdal":
            raise QgsProcessingException(f"Bad DEM type: <{dem_layer.providerType()}>")

        # Check landuse layer
        landuse_layer = self.parameterAsRasterLayer(parameters, "landuse", context)

        # Get origin fron DEM layer in WGS84 and get UTM CRS
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        dem_to_wgs84_tr = QgsCoordinateTransform(
            dem_layer.crs(), wgs84_crs, QgsProject.instance()
        )
        extent = dem_layer.extent()
        origin = QgsPoint(
            (extent.xMinimum() + extent.xMaximum()) / 2.0,
            (extent.yMinimum() + extent.yMaximum()) / 2.0,
        )
        origin.transform(dem_to_wgs84_tr)

        utm_origin_py = utm.LonLat(origin.x(), origin.y()).to_UTM()
        origin_x, origin_y = utm_origin_py.easting, utm_origin_py.northing
        feedback.pushInfo(f"Origin: {origin_x, origin_y}")
        utm_crs = QgsCoordinateReferenceSystem(utm_origin_py.epsg)

        # DEM raster pixels to points
        feedback.pushInfo("Creating grid of points from DEM")
        alg_params = {
            "FIELD_NAME": "zcoord",
            "INPUT_RASTER": parameters["DEM"],
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
            "RASTERCOPY": parameters["landuse"],
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

        # Build the connectivity into the face list: fds_faces_surfs

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

        faces, surfs = list(), list()
        len_vrow = len(matrix[0]) + 1
        for i, row in enumerate(matrix):
            for j, p in enumerate(row):
                faces.extend((get_f1(i, j, len_vrow), get_f2(i, j, len_vrow)))
                surfs.extend((p[3], p[3]))  # landuse  # FIXME index!

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

        # Prepare FDS header
        import time

        # pv = qgis.utils.pluginMetadata("QGIS2FDS", "version")  # FIXME
        qv = QgsExpressionContextUtils.globalScope().variable("qgis_version")
        now = time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())
        filepath = QgsProject.instance().fileName()  # bpy.data.filepath or "not saved"
        if len(filepath) > 60:
            filepath = "..." + filepath[-57:]
        header_str = "\n".join(
            (
                f"! Generated by QGIS2FDS plugin on QGIS <{qv}>",
                f"! File: <{filepath}>",
                f"! DEM layer: <{dem_layer.name()}>",
                f"! Landuse layer: <{landuse_layer.name()}>",
                f"! CRS: <{utm_crs.description()}>",
                f"! Date: <{now}>\n\n",
            )
        )

        # Prepare FDS MISC namelist
        misc_str = "\n".join(
            (
                f"! Origin at <{utm_origin_py}>",
                f"! Link: <{utm_origin_py.to_url()}>",
                f"&MISC ORIGIN_LAT={origin.y():.7f} ORIGIN_LON={origin.x():.7f} /\n",
            )
        )

        # Prepare VERTS and FACES

        def get_verts_str(verts):
            return "            ".join(
                (f"{v[0]:.3f},{v[1]:.3f},{v[2]:.3f},\n" for v in verts)
            )

        def get_faces_str(faces, surfs):
            return "            ".join(
                (
                    f"{f[0]},{f[1]},{f[2]},{int(surfs[i])},\n"
                    for i, f in enumerate(faces)
                )
            )

        # Write FDS file

        with open("/home/egissi/test.fds", "w") as f:
            f.write(header_str)
            f.write(misc_str)
            f.write("&SURF ID='P01-A05' RGB=249,197,92 /\n")
            f.write("&SURF ID='P02-A04' RGB=254,193,119 /\n")
            f.write("&SURF ID='P03-Barren' RGB=133,153,156 /\n")
            f.write("&SURF ID='P04-A03' RGB=236,212,99 /\n")
            f.write("&SURF ID='P05-A10' RGB=114,154,85 /\n")
            f.write("&SURF ID='P06-A01' RGB=255,254,212 /\n")
            f.write("&SURF ID='P07-A08' RGB=229,253,214 /\n")
            f.write(
                f"&GEOM ID='Terrain'\n      SURF_ID='P01-A05','P02-A04','P03-Barren','P04-A03','P05-A10','P06-A01','P07-A08'\n      VERTS={get_verts_str(verts)}      FACES={get_faces_str(faces, surfs)} /\n"
            )

        return {}

    def name(self):
        """!
        Returns the algorithm name.
        """
        return "Export terrain to NIST FDS"

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
