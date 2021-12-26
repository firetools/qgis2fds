# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from math import sqrt
from qgis.core import QgsProcessingException, NULL, edit, QgsFeatureRequest

from . import utils

import os
import numpy as np


class _Terrain:
    def __init__(
        self,
        feedback,
        chid,
        dem_layer,
        dem_layer_res,
        point_layer,
        utm_origin,
        landuse_layer,
        landuse_type,
        fire_layer,
        fire_layer_utm,
    ) -> None:
        self.feedback = feedback
        self.chid = chid
        self.dem_layer = dem_layer
        self.dem_layer_res = dem_layer_res
        self.point_layer = point_layer
        self.utm_origin = utm_origin
        self.landuse_layer = landuse_layer
        self.landuse_type = landuse_type
        self.fire_layer = fire_layer
        self.fire_layer_utm = fire_layer_utm

        self._matrix = None
        self.min_z = 0.0
        self.max_z = 0.0

        if fire_layer:
            self._apply_fire_layer_bcs()
            if self.feedback.isCanceled():
                return {}

        self._init_matrix()
        if self.feedback.isCanceled():
            return {}

    def get_comment(self) -> str:
        return f"""! Terrain:
!   DEM layer: <{self.dem_layer.name()}> with {self.dem_layer_res:.1f}m resolution
!   Landuse layer: <{self.landuse_layer and self.landuse_layer.name() or 'none'}>
!   Fire layer: <{self.fire_layer and self.fire_layer.name() or 'none'}>"""

    def _apply_fire_layer_bcs(self):
        self.feedback.pushInfo(f"Apply fire layer bcs to the terrain...")
        # Sample fire_layer for ignition lines and burned areas
        landuse_idx = self.point_layer.fields().indexOf("landuse1")
        distance = self.dem_layer_res  # size of border
        # Get bcs to be set
        # default for Ignition and Burned
        bc_out_default = self.landuse_type.bc_out_default
        bc_in_default = self.landuse_type.bc_in_default
        bc_in_idx = self.fire_layer_utm.fields().indexOf("bc_in")
        bc_out_idx = self.fire_layer_utm.fields().indexOf("bc_out")
        with edit(self.point_layer):
            for fire_feat in self.fire_layer_utm.getFeatures():
                # Check if user specified bcs available
                if bc_in_idx != -1:  # found user defined?
                    bc_in = fire_feat[bc_in_idx]  # yes
                else:
                    bc_in = bc_in_default  # set default
                if bc_out_idx != -1:  # found user defined?
                    bc_out = fire_feat[bc_out_idx]  # yes
                else:
                    bc_out = bc_out_default  # set default
                # Get fire feature geometry and bbox
                fire_geom = fire_feat.geometry()
                fire_geom_bbox = fire_geom.boundingBox()
                distance = self.dem_layer_res
                h, w = fire_geom_bbox.height(), fire_geom_bbox.width()
                if h < self.dem_layer_res and w < self.dem_layer_res:
                    # if small, replaced by its centroid
                    # to simplify 1 cell ignition
                    fire_geom = fire_geom.centroid()
                    distance *= 0.6
                # Set new bcs in point layer
                # for speed, preselect points with grown bbox
                fire_geom_bbox.grow(delta=distance * 2.0)
                for point_feat in self.point_layer.getFeatures(
                    QgsFeatureRequest(fire_geom_bbox)
                ):
                    point_geom = point_feat.geometry()
                    if fire_geom.contains(point_geom):
                        if bc_in != NULL:
                            # Set inside bc
                            self.point_layer.changeAttributeValue(
                                point_feat.id(), landuse_idx, bc_in
                            )
                    else:
                        if bc_out != NULL and point_geom.distance(fire_geom) < distance:
                            # Set border bc
                            self.point_layer.changeAttributeValue(
                                point_feat.id(), landuse_idx, bc_out
                            )
                self.feedback.pushInfo(
                    f"Applied <bc_in={bc_in}> and <bc_out={bc_out}> bcs to the terrain from fire layer <{fire_feat.id()}> feature"
                )
        self.point_layer.updateFields()

    # The layer is a flat list of quad faces center points (z, x, y, landuse)
    # ordered by column. The original flat list is cut in columns, when three consecutive points
    # form an angle < 180°.
    # The returned matrix is a topological 2D representation of them by row (when transposed).

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

    def _init_matrix(self):
        self.feedback.pushInfo(
            "Init the matrix of quad faces center points with landuse..."
        )
        self.feedback.setProgress(0)
        # Allocate the np array
        nfeatures = self.point_layer.featureCount()
        partial_progress = nfeatures // 100 or 1
        m = np.empty((nfeatures, 4))
        # Fill the array with point coordinates, points are listed by column
        ox, oy = self.utm_origin.x(), self.utm_origin.y()  # get origin
        for i, f in enumerate(self.point_layer.getFeatures()):
            g = f.geometry().get()  # QgsPoint
            m[i] = (
                g.x() - ox,  # x, relative to origin
                g.y() - oy,  # y, relative to origin
                g.z(),  # z absolute
                0,  # for landuse
            )
            if i % partial_progress == 0:
                self.feedback.setProgress(int(i / nfeatures * 100))
        # Fill the array with the landuse
        if self.landuse_layer:
            attr_idx = self.point_layer.fields().indexOf("landuse1")
            for i, f in enumerate(self.point_layer.getFeatures()):
                a = f.attributes()
                m[i][3] = a[attr_idx] or 0
                if i % partial_progress == 0:
                    self.feedback.setProgress(int(i / nfeatures * 100))
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
        m = np.array(np.split(m, nfeatures // column_len)).transpose(1, 0, 2)
        # Check
        if m.shape[0] < 3 or m.shape[1] < 3:
            raise QgsProcessingException(
                f"[QGIS bug] Point matrix is too small: {m.shape[0]}x{m.shape[1]}"
            )
        self._matrix = m


class GEOMTerrain(_Terrain):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._faces = list()
        self._landuses = list()
        self._verts = list()

        self._init_faces_and_landuses()
        if self.feedback.isCanceled():
            return {}

        self._init_verts()
        if self.feedback.isCanceled():
            return {}

        self.feedback.pushInfo(
            f"GEOM terrain ready: {len(self._verts)} verts, {len(self._faces)} faces."
        )

    def get_fds(self) -> str:
        return f"""
! Terrain
&GEOM ID='Terrain'
      SURF_ID={self.landuse_type.surf_id_str}
      BINARY_FILE='{self.chid}_terrain.bingeom'
      IS_TERRAIN=T EXTEND_TERRAIN=F /"""

    def write_bingeom(self, path) -> None:
        self.feedback.pushInfo("Write GEOM terrain bingeom...")
        # Format in fds notation
        fds_verts = tuple(v for vs in self._verts for v in vs)
        fds_faces = tuple(f for fs in self._faces for f in fs)
        fds_surfs = list()
        if self.landuse_type:
            # Translate landuse_layer landuses into FDS SURF index
            surf_dict = self.landuse_type.surf_dict
            surf_list = list(surf_dict)
            n_surf_id = len(surf_list)
            for i, _ in enumerate(self._faces):
                try:
                    fds_surfs.append(surf_list.index(self._landuses[i]) + 1)
                except ValueError:
                    # Not available, set FDS default
                    self.feedback.reportError(
                        f"Landuse <{self._landuses[i]}> value unknown, setting FDS default <0>."
                    )
                    fds_surfs.append(0)
            fds_surfs = tuple(fds_surfs)
        else:
            # No landuse, set default as landuse
            n_surf_id = 1
            fds_surfs = (1,) * len(self._faces)

        # Write bingeom
        utils.write_bingeom(
            feedback=self.feedback,
            filepath=os.path.join(path, f"{self.chid}_terrain.bingeom"),
            geom_type=2,
            n_surf_id=n_surf_id,
            fds_verts=fds_verts,
            fds_faces=fds_faces,
            fds_surfs=fds_surfs,
            fds_volus=list(),
        )

    #        j   j  j+1
    #        *<------* i
    #        | f1 // |
    # faces  |  /·/  | i
    #        | // f2 |
    #        *------>* i+1

    def _get_vert_index(self, i, j, len_vcol):
        """
        Get vert index in fds_vert vector notation.
        """
        return i * len_vcol + j + 1  # F90 indexes start from 1

    def _init_faces_and_landuses(self):
        self.feedback.pushInfo("Init GEOM faces and their landuses...")
        self.feedback.setProgress(0)
        m = self._matrix
        len_vrow = m.shape[0]
        len_vcol = m.shape[1] + 1  # vert matrix is larger
        for i, row in enumerate(m):
            for j, p in enumerate(row):
                self._faces.extend(
                    (
                        (
                            self._get_vert_index(i, j, len_vcol),  # 1st face
                            self._get_vert_index(i + 1, j, len_vcol),
                            self._get_vert_index(i, j + 1, len_vcol),
                        ),
                        (
                            self._get_vert_index(
                                i + 1, j + 1, len_vcol
                            ),  # 2nd tri face
                            self._get_vert_index(i, j + 1, len_vcol),
                            self._get_vert_index(i + 1, j, len_vcol),
                        ),
                    )
                )
                lu = int(p[3])
                self._landuses.extend((lu, lu))
            self.feedback.setProgress(int(i / len_vrow * 100))

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

    def _init_verts(self):
        self.feedback.pushInfo("Init GEOM verts...")
        self.feedback.setProgress(0)
        m = self._matrix

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
        ncenters = m.shape[0] * m.shape[1]
        partial_progress = ncenters // 100 or 1
        for ip, idxs in enumerate(
            np.ndindex(m.shape[0] - 1, m.shape[1] - 1)
        ):  # skip last row and col
            i, j = idxs
            self._verts.append(
                (m[i, j, :3] + m[i + 1, j, :3] + m[i, j + 1, :3] + m[i + 1, j + 1, :3])
                / 4.0
            )
            if ip % partial_progress == 0:
                self.feedback.setProgress(int(ip / ncenters * 100))

        # Calc min and max z for domain
        self.min_z = min(v[2] for v in self._verts)
        self.max_z = max(v[2] for v in self._verts)


class OBSTTerrain(_Terrain):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._xbs = list()
        self._landuses = list()

        self._init_xbs_and_landuses()
        if self.feedback.isCanceled():
            return {}
        self.feedback.pushInfo(f"OBST terrain ready: {len(self._xbs)} OBST lines.")

    def get_fds(self) -> str:
        obsts = list()
        surf_id_dict = self.landuse_type.surf_id_dict
        landuses = self._landuses
        for i, xb in enumerate(self._xbs):
            surf_id_str = surf_id_dict[landuses[i]]
            obsts.append(
                f"&OBST XB={xb[0]:.6f},{xb[1]:.6f},{xb[2]:.6f},{xb[3]:.6f},{xb[4]:.6f},{xb[5]:.6f} SURF_ID='{surf_id_str}' /"
            )
        obsts_str = "\n".join(obsts)
        return f"""
! Terrain
{obsts_str}"""

    #        j   j  j+1
    #        *-------* i
    #        |       |
    # xb     |       | i
    #        |       |
    #        *-------* i+1

    def _init_xbs_and_landuses(self):
        self.feedback.pushInfo("Init OBST XBs and their landuses...")
        self.feedback.setProgress(0)
        m = self._matrix
        xbs = self._xbs
        landuses = self._landuses
        len_vrow = m.shape[0]
        epsilon = 1.0e-6
        dx = (m[1, 1][0] - m[1, 0][0]) / 2.0  # overlapping
        dy = (m[1, 1][1] - m[0, 1][1]) / 2.0  # overlapping
        dxc = m[1, 0][0] - m[0, 0][0]
        # Create xbs
        for i, row in enumerate(m):
            for j, p in enumerate(row):
                xbs.append(
                    (
                        p[0] - dx - epsilon,
                        p[0] + dx + epsilon,
                        p[1] - dy - epsilon,
                        p[1] + dy + epsilon,
                        0.0,
                        p[2],
                    )
                )
                landuses.append(int(p[3]))
            self.feedback.setProgress(int(i / len_vrow * 100))
        # Fill the voids due to grid rotation
        if dxc < 0.0:
            epsilon *= -1
        for i, row in enumerate(m[:-1, :-1]):  # except last row and col
            for j, p in enumerate(row):
                xbs.append(
                    (
                        p[0] + dx - epsilon,
                        m[i + 1, j + 1][0] - dx + epsilon,
                        m[i + 1, j + 1][1] - dy + epsilon,
                        p[1] + dy - epsilon,
                        0.0,
                        p[2],
                    )
                )
                landuses.append(int(p[3]))
            self.feedback.setProgress(int(i / len_vrow * 100))
        # Calc min and max z for domain
        self.min_z = min(xb[5] for xb in xbs)
        self.max_z = max(xb[5] for xb in xbs)
