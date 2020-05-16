# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import math


# Get verts, faces, landuses


def get_geometry(layer, utm_origin):
    """!
    Get verts, faces, and landuses from sampling point layer.
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return verts, faces, landuses
    """
    matrix = _get_matrix(layer=layer, utm_origin=utm_origin)
    faces, landuses = _get_faces(matrix=matrix)
    landuses_set = set(landuses)
    verts = _get_verts(matrix=matrix)
    return verts, faces, landuses, landuses_set


# Prepare the matrix of quad faces center points with landuse

# The layer is a flat list of quad faces center points (z, x, y, landuse)
# ordered by column. The original flat list is cut in columns, when three consecutive points
# form an angle < 180°.
# The returned matrix is a topological 2D representation of them by row (transposed).

# Same column:  following column:
#      first ·            first · · current
#            |                  | ^
#            |                  | |
#       prev ·                  | |
#            |                  |/
#    current ·             prev ·


# matrix:    j
#      o   o   o   o   o
#        ·   ·   ·   ·
#      o   *---*   o   o
# row    · | · | ·   ·   i
#      o   *---*   o   o
#        ·   ·   ·   ·
#      o   o   o   o   o
#
# · center points of quad faces
# o verts


def _norm(vector):
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def _dot_product(p0, p1, p2):
    v0 = [p1[0] - p0[0], p1[1] - p0[1]]
    v1 = [p2[0] - p0[0], p2[1] - p0[1]]
    return (v0[0] * v1[0] + v0[1] * v1[1]) / (_norm(v0) * _norm(v1))


def _get_matrix(layer, utm_origin):
    """
    Return the matrix of quad faces center points with landuse.
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return matrix of quad faces center points with landuse.
    """

    features = layer.getFeatures()  # get the points
    first_point, prev_point = None, None
    # Loop on points
    ox, oy = utm_origin.x(), utm_origin.y()
    for f in features:
        a = f.attributes()  # order: z, x, y, landuse
        point = (
            a[5] - ox,  # x, relative to origin
            a[6] - oy,  # y, relative to origin
            a[7],  # z absolute
            a[8] or 0,  # landuse, protect from None
        )
        if first_point is None:
            # point is the first point of the matrix
            m = [[point,]]
            first_point = point
            continue
        elif prev_point is None:
            # point is the second point of the matrix column
            m[-1].append(point)
            prev_point = point
            continue
        # current point is another point, check alignment in 2D
        if abs(_dot_product(first_point, prev_point, point)) > 0.1:
            # point is on the same matrix column
            m[-1].append(point)
            prev_point = point
            continue
        # point is on the next column
        m.append(
            [point,]
        )
        first_point = point
        prev_point = None
    return list(map(list, zip(*m)))  # transpose


# Getting face connectivity and landuse

#        j   j  j+1
#        *<------* i
#        | f1 // |
# faces  |  /·/  | i
#        | // f2 |
#        *------>* i+1


def _get_vert_index(i, j, len_vrow):
    # F90 indexes start from 1, so +1
    return i * len_vrow + j + 1


def _get_f1(i, j, len_vrow):
    return (
        _get_vert_index(i, j, len_vrow),
        _get_vert_index(i + 1, j, len_vrow),
        _get_vert_index(i, j + 1, len_vrow),
    )


def _get_f2(i, j, len_vrow):
    return (
        _get_vert_index(i + 1, j + 1, len_vrow),
        _get_vert_index(i, j + 1, len_vrow),
        _get_vert_index(i + 1, j, len_vrow),
    )


def _get_faces(matrix):
    """
    Get face connectivity and landuses.
    @param matrix: matrix of quad faces center points with landuse.
    @return faces and landuses
    """
    faces, landuses = list(), list()
    len_vrow = len(matrix[0]) + 1
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            faces.extend((_get_f1(i, j, len_vrow), _get_f2(i, j, len_vrow)))
            landuses.extend((p[3], p[3]))
    return faces, landuses


# Getting vertices

# First inject ghost centers all around the vertices
# then extract the vertices by averaging the neighbour centers coordinates

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

#              j      j+1
# prev_row     *       * i-1
#
#          o-------x
#          |       |
#      row |   *   |   * i
#          |       |
#          o-------o


def _inject_ghost_centers(matrix):
    """
    Inject ghost centers into the matrix.
    """

    # Calc displacements for ghost centers
    fsub = lambda a: a[0] - a[1]
    fadd = lambda a: a[0] + a[1]
    dx = list(map(fsub, zip(matrix[0][1], matrix[0][0])))
    dy = list(map(fsub, zip(matrix[1][0], matrix[0][0])))
    # no vertical displacement for ghost centers (smoother)
    dx[2], dy[2] = 0.0, 0.0

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

    return matrix


def _get_neighbour_centers(prev_row, row, j):
    return (
        prev_row[j][:-1],  # rm landuse from center (its last value)
        prev_row[j + 1][:-1],
        row[j][:-1],
        row[j + 1][:-1],
    )


def _avg(l):
    return sum(l) / len(l)


def _get_vert(neighbour_centers):
    return tuple(map(_avg, zip(*neighbour_centers)))  # avg of centers coordinates


def _get_verts(matrix):
    """
    Get vertices from the center matrix.
    @param matrix: matrix of quad faces center points with landuse.
    @return verts
    """

    matrix = _inject_ghost_centers(matrix)  # FIXME modification in place

    verts = list()
    prev_row = matrix[0]
    for row in matrix[1:]:  # matrix[0] is prev_row
        for j, _ in enumerate(row[:-1]):
            verts.append(_get_vert(_get_neighbour_centers(prev_row, row, j)))
        prev_row = row

    return verts
