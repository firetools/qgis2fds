# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from math import sqrt
from qgis.core import QgsProcessingException

from . import utils
import os
import numpy as np


def write_geom_terrain(
    feedback,
    fds_path,
    chid,
    point_layer,
    utm_origin,
    landuse_layer,
    landuse_type,
):
    feedback.pushInfo("Point and landuse matrix...")
    matrix = _get_matrix(
        feedback,
        point_layer=point_layer,
        utm_origin=utm_origin,
        landuse_layer=landuse_layer,
    )
    if feedback.isCanceled():
        return {}
    feedback.pushInfo("Faces with landuse...")
    faces, landuses = _get_faces(feedback=feedback, m=matrix)
    if feedback.isCanceled():
        return {}
    feedback.pushInfo("Verts...")
    verts, min_z, max_z = _get_verts(feedback=feedback, m=matrix)
    # Format in fds notation
    fds_verts = tuple(v for vs in verts for v in vs)
    fds_faces = tuple(f for fs in faces for f in fs)
    fds_surfs = list()
    if landuse_type:
        # Translate landuse_layer landuses into FDS SURF index
        surf_dict = landuse_type.surf_dict
        surf_list = list(surf_dict)
        n_surf_id = len(surf_list)
        for i, _ in enumerate(faces):
            try:
                fds_surfs.append(surf_list.index(landuses[i]) + 1)
            except ValueError:
                # Not available, set FDS default
                feedback.reportError(
                    f"Landuse <{landuses[i]}> value unknown, setting FDS default <0>."
                )
                fds_surfs.append(0)
        fds_surfs = tuple(fds_surfs)
    else:
        # No landuse, set FDS INERT as landuse
        n_surf_id = 1
        fds_surfs = (1,) * len(faces)
    # Write bingeom
    utils.write_bingeom(
        feedback=feedback,
        filepath=os.path.join(fds_path, f"{chid}_terrain.bingeom"),
        geom_type=2,
        n_surf_id=n_surf_id,
        fds_verts=fds_verts,
        fds_faces=fds_faces,
        fds_surfs=fds_surfs,
        fds_volus=list(),
    )
    feedback.pushInfo(f"GEOM terrain ready: {len(verts)} verts, {len(faces)} faces.")
    return min_z, max_z


def get_obst_str(
    feedback,
    point_layer,
    utm_origin,
    landuse_layer,
    landuse_type,
):
    feedback.pushInfo("Point and landuse matrix...")
    matrix = _get_matrix(
        feedback,
        point_layer=point_layer,
        utm_origin=utm_origin,
        landuse_layer=landuse_layer,
    )
    if feedback.isCanceled():
        return {}
    feedback.pushInfo("Building OBSTs...")
    xbs, landuses = _get_obst_params(feedback=feedback, m=matrix)
    obsts = list()
    id_dict = landuse_type.id_dict
    for i, xb in enumerate(xbs):
        id_str = id_dict[landuses[i]]
        obsts.append(
            f"&OBST XB={xb[0]:.6f},{xb[1]:.6f},{xb[2]:.6f},{xb[3]:.6f},{xb[4]:.6f},{xb[5]:.6f} SURF_ID='{id_str}' /"
        )
    feedback.pushInfo(f"OBST terrain ready: {len(xbs)} OBST lines.")
    return "\n".join(obsts)


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


def _get_matrix(feedback, point_layer, utm_origin, landuse_layer):
    """
    Return the matrix of quad faces center points with landuse.
    @feedback: pyqgis feedback obj
    @param point_layer: QGIS vector layer of quad faces center points with landuse.
    @param utm_origin: domain origin in UTM CRS.
    @param landuse_layer: landuse layer.
    @return matrix of quad faces center points with landuse.
    """
    feedback.setProgress(0)
    # Allocate the np array
    nfeatures = point_layer.featureCount()
    partial_progress = nfeatures // 100 or 1
    m = np.empty((nfeatures, 4))
    # Fill the array with point coordinates, points are listed by column
    ox, oy = utm_origin.x(), utm_origin.y()  # get origin
    for i, f in enumerate(point_layer.getFeatures()):
        g = f.geometry().get()  # QgsPoint
        m[i] = (
            g.x() - ox,  # x, relative to origin
            g.y() - oy,  # y, relative to origin
            g.z(),  # z absolute
            0,  # for landuse
        )
        if i % partial_progress == 0:
            feedback.setProgress(int(i / nfeatures * 100))
    # Fill the array with the landuse
    if landuse_layer:
        attr_idx = point_layer.fields().indexOf("landuse1")
        for i, f in enumerate(point_layer.getFeatures()):
            a = f.attributes()
            m[i][3] = a[attr_idx] or 0
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
    @feedback: pyqgis feedback obj
    @param m: matrix of quad faces center points with landuse.
    @return faces and landuses
    """
    feedback.setProgress(0)
    faces, landuses = list(), list()
    if m.shape[0] < 3 or m.shape[1] < 3:
        raise QgsProcessingException(
            f"[QGIS bug] Too small point matrix, cannot proceed with face building: {m.shape[0]}x{m.shape[1]}\nMatrix m: {m}"
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
            lu = int(p[3])
            landuses.extend((lu, lu))
        feedback.setProgress(int(i / len_vrow * 100))
    return faces, landuses


# Getting OBST XBs and their landuse

#        j   j  j+1
#        *-------* i
#        |       |
# xb     |       | i
#        |       |
#        *-------* i+1


def _get_obst_params(feedback, m):
    """
    Get xbs and landuses.
    @feedback: pyqgis feedback obj
    @param m: matrix of quad faces center points with landuse.
    @return faces and landuses
    """
    feedback.setProgress(0)
    xbs, landuses = list(), list()
    if m.shape[0] < 3 or m.shape[1] < 3:
        raise QgsProcessingException(
            f"[QGIS bug] Too small point matrix, cannot proceed with xbs building: {m.shape[0]}x{m.shape[1]}\nMatrix m: {m}"
        )
    len_vrow = m.shape[0]
    dx = (m[1, 1][0] - m[1, 0][0]) / sqrt(2)  # / 2.0 # overlapping FIXME
    dy = (m[1, 1][1] - m[0, 1][1]) / sqrt(2)  # / 2.0 # overlapping FIXME
    for i, row in enumerate(m):
        for p in row:
            xbs.append(
                (
                    p[0] - dx,
                    p[0] + dx,
                    p[1] - dy,
                    p[1] + dy,
                    0.0,
                    p[2],
                )
            )
            landuses.append(int(p[3]))
            # feedback.pushInfo(f"p: {p}")  # FIXME remove
            # feedback.pushInfo(f"xbs[-1]: {xbs[-1]}")
        feedback.setProgress(int(i / len_vrow * 100))
    return xbs, landuses


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

    # Calc min and max z for domain
    min_z = min(v[2] for v in verts)
    max_z = max(v[2] for v in verts)
    return verts, min_z, max_z
