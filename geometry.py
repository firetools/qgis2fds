# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import QgsProcessingException

import math
import numpy as np

# Get verts, faces, landuses


def get_geometry(feedback, layer, utm_origin):
    """!
    Get verts, faces, and landuses from sampling point layer.
    @feedback: pyqgis feedback obj
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return verts, faces, landuses
    """
    feedback.pushInfo("Point matrix...")
    matrix = _get_matrix(feedback, layer=layer, utm_origin=utm_origin)
    if feedback.isCanceled():
        return {}
    feedback.pushInfo("Faces and landuses...")
    faces, landuses = _get_faces(feedback=feedback, m=matrix)
    if feedback.isCanceled():
        return {}
    feedback.pushInfo("Verts...")
    verts = _get_verts(feedback=feedback, m=matrix)
    feedback.pushInfo(f"Geometry ready: {len(verts)} verts, {len(faces)} faces.")
    return verts, faces, landuses


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


def _get_matrix(feedback, layer, utm_origin):
    """
    Return the matrix of quad faces center points with landuse.
    @param layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @return matrix of quad faces center points with landuse.
    """
    feedback.setProgress(0)
    # Allocate and fill np array, points are listed by column
    ox, oy = utm_origin.x(), utm_origin.y()  # get origin
    nfeatures = layer.featureCount()
    partial_progress = nfeatures // 100 or 1
    m = np.empty((nfeatures, 4))  # allocate array
    for i, f in enumerate(layer.getFeatures()):
        g, a = f.geometry().get(), f.attributes()  # QgsPoint, landuse
        m[i] = (  # fill array
            g.x() - ox,  # x, relative to origin
            g.y() - oy,  # y, relative to origin
            g.z(),  # z absolute
            a[5] or 0,  # landuse, protect from None
        )
        if i % partial_progress == 0:
            feedback.setProgress(int(i / nfeatures * 100))
    # Get point column length and split matrix
    column_len = 2
    p0, p1 = m[0, :2], m[1, :2]
    v0 = p1 - p0
    for p2 in m[2:, :2]:
        v1 = p2 - p1
        if abs(np.dot(v0, v1) / np.linalg.norm(v0) / np.linalg.norm(v1)) < 0.9:
            break  # end of point column
        column_len += 1
    # Split into columns list, get np array, and transpose
    # Now points are by row
    return np.array(np.split(m, nfeatures // column_len)).transpose(1, 0, 2)


# Getting face connectivity and landuse

#        j   j  j+1
#        *<------* i
#        | f1 // |
# faces  |  /·/  | i
#        | // f2 |
#        *------>* i+1


def _get_vert_index(i, j, len_vcol):
    """
    Get vert index in fds_vert vector notation.
    """
    return i * len_vcol + j + 1  # F90 indexes start from 1


def _get_faces(feedback, m):
    """
    Get face connectivity and landuses.
    @param m: matrix of quad faces center points with landuse.
    @return faces and landuses
    """
    feedback.setProgress(0)
    faces, landuses = list(), list()
    if m.shape[0] < 3 or m.shape[1] < 3:
        raise QgsProcessingException(
            f"[QGIS bug] Too small point matrix, cannot proceed with face building: {m.shape[0]}x{m.shape[1]}\nm: {m}"
        )
    len_vrow = m.shape[0]
    len_vcol = m.shape[1] + 1  # vert matrix is larger
    for i, row in enumerate(m):
        for j, p in enumerate(row):
            faces.extend(
                (
                    (
                        _get_vert_index(i, j, len_vcol),  # 1st face
                        _get_vert_index(i + 1, j, len_vcol),
                        _get_vert_index(i, j + 1, len_vcol),
                    ),
                    (
                        _get_vert_index(i + 1, j + 1, len_vcol),  # 2nd tri face
                        _get_vert_index(i, j + 1, len_vcol),
                        _get_vert_index(i + 1, j, len_vcol),
                    ),
                )
            )
            lu = int(p[3])  # landuse idx
            landuses.extend((lu, lu))
        feedback.setProgress(int(i / len_vrow * 100))
    return faces, landuses


# Getting vertices

# First inject ghost centers all around the vertices
# then extract the vertices by averaging the neighbour centers coordinates

# · centers of quad faces  + ghost centers
# o verts  * cs  x vert
#
#           dx       j
#          + > +   +   +   +   +  first ghost row
#       dy v o---o---o---o---o
#          + | · | · | · | · | +  i center
#            o---o---x---o---o    i vert
#          + | · | · | · | · | +  i+1 center
#            o---o---o---o---o
#          +   +   +   +   +   +  last ghost row (skipped)


def _get_verts(feedback, m):
    """
    Get vertices from the center matrix.
    @param m: matrix of quad faces center points with landuse, and ghost cells.
    @return verts
    """
    feedback.setProgress(0)
    # Inject ghost centers
    dx, dy = m[0, 1] - m[0, 0], m[1, 0] - m[0, 0]  # displacements
    dx[2], dy[2] = 0.0, 0.0  # no z displacement
    dx[3], dy[3] = 0.0, 0.0  # no landuse change

    row = tuple(c - dy for c in m[0, :])  # first ghost center row
    m = np.insert(m, 0, row, axis=0)

    row = tuple((tuple(c + dy for c in m[-1, :]),))  # last ghost center row
    m = np.append(m, row, axis=0)

    col = tuple(c - dx for c in m[:, 0])  # new first ghost center col
    m = np.insert(m, 0, col, axis=1)

    col = tuple(
        tuple((c + dx,) for c in m[:, -1]),
    )  # last ghost center col
    m = np.append(m, col, axis=1)

    # Average center coordinates to obtain verts
    verts = list()
    ncenters = m.shape[0] * m.shape[1]
    partial_progress = ncenters // 100 or 1
    for ip, idxs in enumerate(
        np.ndindex(m.shape[0] - 1, m.shape[1] - 1)
    ):  # skip last row and col
        i, j = idxs
        verts.append(
            (m[i, j, :3] + m[i + 1, j, :3] + m[i, j + 1, :3] + m[i + 1, j + 1, :3])
            / 4.0
        )
        if ip % partial_progress == 0:
            feedback.setProgress(int(ip / ncenters * 100))
    return verts
