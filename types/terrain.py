# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import os
import numpy as np
from qgis.core import QgsProcessingException, NULL
from . import utils


class GEOMTerrain:
    def __init__(
        self,
        feedback,
        path,
        name,
        dem_layer,
        pixel_size,
        sampling_layer,
        utm_origin,
        landuse_layer,
        landuse_type,
        fire_layer,
    ) -> None:
        self.feedback = feedback
        self.dem_layer = dem_layer
        self.pixel_size = pixel_size
        self.sampling_layer = sampling_layer
        self.utm_origin = utm_origin
        self.landuse_layer = landuse_layer
        self.landuse_type = landuse_type
        self.fire_layer = fire_layer

        self.filename = f"{name}_terrain.bingeom"
        self.filepath = os.path.join(path, self.filename)

        self._matrix = None
        self.min_z = 0.0
        self.max_z = 0.0

        self._init_matrix()

        if self.feedback.isCanceled():
            return {}

        self._faces = list()
        self._landuses = list()
        self._verts = list()

        self._init_faces_and_landuses()

        if self.feedback.isCanceled():
            return {}

        self._init_verts()

        if self.feedback.isCanceled():
            return {}

        self._save()

        self.feedback.pushInfo(
            f"GEOM terrain saved ({len(self._verts)} verts, {len(self._faces)} faces)."
        )

    def get_comment(self) -> str:
        return f"""\
DEM layer: <{self.dem_layer.name()}> with {self.pixel_size:.1f}m resolution
Landuse layer: <{self.landuse_layer and self.landuse_layer.name() or 'none'}>
Fire layer: <{self.fire_layer and self.fire_layer.name() or 'none'}>"""

    def get_fds(self) -> str:
        return f"""
Terrain ({len(self._verts)} verts, {len(self._faces)} faces)
&GEOM ID='Terrain'
      SURF_ID={self.landuse_type.surf_id_str}
      BINARY_FILE='{self.filename}'
      IS_TERRAIN=T EXTEND_TERRAIN=F /"""

    def _save(self) -> None:
        # Format in fds notation
        fds_verts = tuple(v for vs in self._verts for v in vs)
        fds_faces = tuple(f for fs in self._faces for f in fs)
        fds_surfs = list()
        # Translate landuse_layer landuses into FDS SURF index
        surf_id_list = list(self.landuse_type.surf_id_dict)
        n_surf_id = len(surf_id_list)
        for i, _ in enumerate(self._faces):
            try:
                fds_surfs.append(surf_id_list.index(self._landuses[i]) + 1)
            except ValueError:
                self.feedback.reportError(
                    f"Landuse <{self._landuses[i]}> value unknown, setting FDS default <0>."
                )
                fds_surfs.append(0)
        fds_surfs = tuple(fds_surfs)
        # Write bingeom
        utils.write_bingeom(
            feedback=self.feedback,
            filepath=self.filepath,
            geom_type=2,
            n_surf_id=n_surf_id,
            fds_verts=fds_verts,
            fds_faces=fds_faces,
            fds_surfs=fds_surfs,
            fds_volus=list(),
        )

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

    def _init_matrix(self) -> None:
        """Init the matrix from the sampling layer."""
        self.feedback.pushInfo("Init the matrix of sampling points...")
        self.feedback.setProgress(0)

        # Init
        sampling_layer = self.sampling_layer
        nfeatures = sampling_layer.featureCount()
        partial_progress = nfeatures // 100 or 1
        m = np.empty((nfeatures, 4))  # allocate the np array
        ox, oy = self.utm_origin.x(), self.utm_origin.y()  # get origin

        # Fill the array with point coordinates, points are listed by column
        # calc min and max z
        min_z, max_z = 1e6, -1e6
        for i, f in enumerate(self.sampling_layer.getFeatures()):
            g = f.geometry().get()  # QgsPoint
            z = g.z()
            if z > max_z:
                max_z = z
            if z < min_z:
                min_z = z
            m[i] = (
                g.x() - ox,  # x, relative to origin
                g.y() - oy,  # y, relative to origin
                g.z(),  # z absolute
                0,  # for landuse
            )
            if i % partial_progress == 0:
                self.feedback.setProgress(int(i / nfeatures * 100))
        self.max_z, self.min_z = max_z, min_z

        # Fill the array with the landuse
        if self.landuse_layer:
            landuse_idx = self.sampling_layer.fields().indexOf("landuse1")
            for i, f in enumerate(self.sampling_layer.getFeatures()):
                a = f.attributes()
                m[i][3] = a[landuse_idx] or 0
                if i % partial_progress == 0:
                    self.feedback.setProgress(int(i / nfeatures * 100))

        # Fill the array with the fire layer bcs
        if self.fire_layer:
            bc_idx = self.sampling_layer.fields().indexOf("bc")
            for i, f in enumerate(self.sampling_layer.getFeatures()):
                a = f.attributes()
                if a[bc_idx]:
                    m[i][3] = a[bc_idx]
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
                f"[QGIS bug] Sampling matrix is too small: {m.shape[0]}x{m.shape[1]}"
            )
        self._matrix = m

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
                            self._get_vert_index(i + 1, j + 1, len_vcol),  # 2nd face
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
        ):  # skip last row and last col
            i, j = idxs
            self._verts.append(
                (m[i, j, :3] + m[i + 1, j, :3] + m[i, j + 1, :3] + m[i + 1, j + 1, :3])
                / 4.0
            )
            if ip % partial_progress == 0:
                self.feedback.setProgress(int(ip / ncenters * 100))

    #        j   j  j+1
    #        *<------* i
    #        | f1 // |
    # faces  |  /·/  | i
    #        | // f2 |
    #        *------>* i+1

    def _get_vert_index(self, i, j, len_vcol):
        return i * len_vcol + j + 1  # F90 indexes start from 1


# OBST terrain


class OBSTTerrain(GEOMTerrain):
    def __init__(
        self,
        feedback,
        dem_layer,
        pixel_size,
        sampling_layer,
        utm_origin,
        landuse_layer,
        landuse_type,
        fire_layer,
    ) -> None:
        self.feedback = feedback
        self.dem_layer = dem_layer
        self.pixel_size = pixel_size
        self.sampling_layer = sampling_layer
        self.utm_origin = utm_origin
        self.landuse_layer = landuse_layer
        self.landuse_type = landuse_type
        self.fire_layer = fire_layer

        self.min_z = 0.0
        self.max_z = 0.0

        self._init_matrix()
        if self.feedback.isCanceled():
            return {}

        self._inject_ghost_centers()
        self._init_obsts()

        if self.feedback.isCanceled():
            return {}

        self.feedback.pushInfo(f"OBST terrain saved ({len(self._obsts)} OBSTs).")

    def get_comment(self) -> str:
        return f"""\
DEM layer: <{self.dem_layer.name()}> with {self.pixel_size:.1f}m resolution
Landuse layer: <{self.landuse_layer and self.landuse_layer.name() or 'none'}>
Fire layer: <{self.fire_layer and self.fire_layer.name() or 'none'}>"""

    def get_fds(self) -> str:
        obsts_str = "\n".join(self._obsts)
        return f"""
Terrain ({len(self._obsts)} OBSTs)
{obsts_str}
"""

    def _inject_ghost_centers(self):
        feedback = self.feedback
        feedback.pushInfo("Inject ghost centers in matrix...")
        feedback.setProgress(0)
        m = self._matrix

        # Init
        dx, dy = m[0, 1] - m[0, 0], m[1, 0] - m[0, 0]  # displacements
        dx[2], dy[2] = 0.0, 0.0  # correct, no z displacement
        dx[3], dy[3] = 0.0, 0.0  # correct, no landuse change

        # Inject first row
        row = tuple(c - dy for c in m[0, :])
        m = np.insert(m, 0, row, axis=0)

        # Append last row
        row = tuple((tuple(c + dy for c in m[-1, :]),))
        m = np.append(m, row, axis=0)

        # Inject first col
        col = tuple(c - dx for c in m[:, 0])
        m = np.insert(m, 0, col, axis=1)

        # Append last col
        col = tuple(
            tuple((c + dx,) for c in m[:, -1]),
        )
        m = np.append(m, col, axis=1)

        self._matrix = m

    def _init_obsts(self):
        """Get formatted OBSTs from sampling layer."""
        feedback = self.feedback
        feedback.pushInfo("Prepare OBSTs...")
        feedback.setProgress(0)
        m = self._matrix
        _obsts = list()

        # Init
        ncenters = m.shape[0] * m.shape[1]
        partial_progress = ncenters // 100 or 1
        surf_id_dict = self.landuse_type.surf_id_dict

        # Skip last two rows and last two cols
        min_z = self.min_z
        for ip, idxs in enumerate(np.ndindex(m.shape[0] - 2, m.shape[1] - 2)):
            i, j = idxs
            p0 = (m[i + 2, j, :2] + m[i + 1, j + 1, :2]) / 2.0
            p1 = (m[i + 1, j + 1, :2] + m[i, j + 2, :2]) / 2.0
            z = m[i + 1, j + 1, 2]
            lu = m[i + 1, j + 1, 3]
            xb = tuple((p0[0], p1[0], p0[1], p1[1], min_z, z))
            surf_id = surf_id_dict.get(lu, "INERT")  # FIXME protect and warn!
            _obsts.append(
                f"&OBST XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},{xb[4]:.2f},{xb[5]:.2f} SURF_ID='{surf_id}' /"
            )
            if ip % partial_progress == 0:
                self.feedback.setProgress(int(ip / ncenters * 100))

        self._obsts = _obsts

    # def _init_obsts_orig(self):
    #     """Get formatted OBSTs from sampling layer."""
    #     feedback = self.feedback
    #     feedback.pushInfo("Prepare OBSTs...")
    #     feedback.setProgress(0)

    #     # Init
    #     sampling_layer = self.sampling_layer
    #     nfeatures = sampling_layer.featureCount()
    #     partial_progress = nfeatures // 100 or 1

    #     left_idx = sampling_layer.fields().indexOf("left")
    #     right_idx = sampling_layer.fields().indexOf("right")
    #     top_idx = sampling_layer.fields().indexOf("top")
    #     bottom_idx = sampling_layer.fields().indexOf("bottom")
    #     landuse_idx = sampling_layer.fields().indexOf("landuse1")
    #     bc_idx = sampling_layer.fields().indexOf("bc")

    #     ox, oy = self.utm_origin.x(), self.utm_origin.y()
    #     overlap = 0.01

    #     # Read values
    #     xbs, lus, bcs = list(), list(), list()
    #     for i, f in enumerate(sampling_layer.getFeatures()):
    #         if i % partial_progress == 0:
    #             feedback.setProgress(int(i / nfeatures * 100))
    #         g, a = f.geometry().get(), f.attributes()
    #         xbs.append(
    #             tuple(
    #                 (
    #                     a[left_idx] - ox - overlap,
    #                     a[right_idx] - ox + overlap,
    #                     a[bottom_idx] - oy - overlap,
    #                     a[top_idx] - oy + overlap,
    #                     0.0,
    #                     g.z(),
    #                 )
    #             )
    #         )
    #         lus.append(a[landuse_idx])
    #         bcs.append(a[bc_idx])

    #     # Calc min and max z (also for MESH)
    #     self.min_z = min(xb[5] for xb in xbs) - self.pixel_size
    #     self.max_z = max(xb[5] for xb in xbs)

    #     # Prepare OBSTs
    #     self._obsts, surf_id_dict = list(), self.landuse_type.surf_id_dict
    #     min_z = self.min_z
    #     for i in range(len(xbs)):
    #         xb = xbs[i]
    #         if bcs[i] == NULL:
    #             surf_id = surf_id_dict.get(lus[i], 0)
    #         else:
    #             surf_id = surf_id_dict.get(
    #                 bcs[i],
    #             )
    #         self._obsts.append(
    #             f"&OBST XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},{min_z:.2f},{xb[5]:.2f} SURF_ID='{surf_id}' /"
    #         )
