# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import os
import numpy as np
from qgis.core import QgsProcessingException
from . import utils


class GEOMTerrain:
    def __init__(
        self,
        feedback,
        sampling_layer,
        utm_origin,
        landuse_layer,
        landuse_type,
        fire_layer,
        path,
        name,
    ) -> None:
        self.feedback = feedback
        self.sampling_layer = sampling_layer
        self.utm_origin = utm_origin
        self.landuse_layer = landuse_layer
        self.landuse_type = landuse_type
        self.fire_layer = fire_layer

        self._filename = f"{name}_terrain.bingeom"
        self._filepath = os.path.join(path, self._filename)

        self._m = None
        self.min_z = 0.0
        self.max_z = 0.0
        self._init_matrix()

        if self.feedback.isCanceled():
            return {}

        self._faces = list()
        self._landuses = list()
        self._init_faces_and_landuses()

        if self.feedback.isCanceled():
            return {}

        self._verts = list()
        self._init_verts()

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
        """Init the matrix from the fds grid layer."""
        self.feedback.pushInfo("Init the matrix of sampling points...")
        self.feedback.setProgress(0)

        # Init
        nfeatures = self.sampling_layer.featureCount()
        partial_progress = nfeatures // 100 or 1
        m = np.empty((nfeatures, 4))  # allocate the np array
        ox, oy = self.utm_origin.x(), self.utm_origin.y()  # get origin

        # Fill the matrix with point coordinates and boundary conditions
        # Points are listed by column
        min_z, max_z = 1e6, -1e6
        output_bc_idx = self.sampling_layer.fields().indexOf("bc1")
        for i, f in enumerate(self.sampling_layer.getFeatures()):
            # Get elevation
            g = f.geometry().get()  # it is a QgsPoint
            z = g.z()
            # Calc max and min elevation
            if z > max_z:
                max_z = z
            if z < min_z:
                min_z = z
            # Get bc
            a = f.attributes()
            bc = a[output_bc_idx] or 0
            # Set elevation and bc in the matrix
            m[i] = (
                g.x() - ox,  # x, relative to origin
                g.y() - oy,  # y, relative to origin
                z,  # z absolute
                bc,  # boundary condition
            )
            if i % partial_progress == 0:
                self.feedback.setProgress(int(i / nfeatures * 100))
        self.max_z, self.min_z = max_z, min_z

        # Get point column length
        column_len = 2
        p0, p1 = m[0, :2], m[1, :2]
        v0 = p1 - p0
        for p2 in m[2:, :2]:
            v1 = p2 - p1
            if abs(np.dot(v0, v1) / np.linalg.norm(v0) / np.linalg.norm(v1)) < 0.9:
                break  # end of point column
            column_len += 1

        # Split matrix into columns list, get np array, and transpose
        # Now points are by row
        m = np.array(np.split(m, nfeatures // column_len)).transpose(1, 0, 2)

        # Check
        if m.shape[0] < 3 or m.shape[1] < 3:
            raise QgsProcessingException(
                f"[QGIS bug] Sampling matrix is too small: {m.shape[0]}x{m.shape[1]}"
            )
        self._m = m

    def _inject_ghost_centers(self):
        """Inject ghost centers into the matrix."""
        feedback = self.feedback
        feedback.pushInfo("Inject ghost centers in matrix...")
        feedback.setProgress(0)

        # Init displacements
        dx, dy = self._m[0, 1] - self._m[0, 0], self._m[1, 0] - self._m[0, 0]
        dx[2], dy[2] = 0.0, 0.0  # no z displacement
        dx[3], dy[3] = 0.0, 0.0  # no landuse change

        # Inject first row
        row = tuple(c - dy for c in self._m[0, :])
        self._m = np.insert(self._m, 0, row, axis=0)

        # Append last row
        row = tuple((tuple(c + dy for c in self._m[-1, :]),))
        self._m = np.append(self._m, row, axis=0)

        # Inject first col
        col = tuple(c - dx for c in self._m[:, 0])
        self._m = np.insert(self._m, 0, col, axis=1)

        # Append last col
        col = tuple(
            tuple((c + dx,) for c in self._m[:, -1]),
        )
        self._m = np.append(self._m, col, axis=1)

    def _init_faces_and_landuses(self):
        """Init GEOM faces and landuses."""
        self.feedback.pushInfo("Init GEOM faces and their landuses...")
        self.feedback.setProgress(0)
        m = self._m
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
        """Init verts as average of surrounding centers."""
        self.feedback.pushInfo("Init GEOM verts...")
        self.feedback.setProgress(0)

        self._inject_ghost_centers()
        m = self._m
        ncenters = m.shape[0] * m.shape[1]
        partial_progress = ncenters // 100 or 1
        # Skip last row and last col
        for ip, idxs in enumerate(np.ndindex(m.shape[0] - 1, m.shape[1] - 1)):
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
        """Get vert index in FDS notation."""
        return i * len_vcol + j + 1  # F90 indexes start from 1

    def _save_bingeom(self) -> None:
        """Save the bingeom file."""

        # Format in fds notation
        fds_verts = tuple(v for vs in self._verts for v in vs)
        fds_faces = tuple(f for fs in self._faces for f in fs)
        fds_surfs = list()

        # Translate landuse_layer landuses into FDS SURF index
        surf_id_list = list(self.landuse_type.surf_id_dict)
        n_surf_id = len(surf_id_list)
        for i, _ in enumerate(self._faces):
            lu = self._landuses[i]
            try:
                fds_surfs.append(surf_id_list.index(lu) + 1)  # +1 for F90
            except ValueError:
                self.feedback.reportError(f"Unknown landuse index <{lu}>, setting <0>.")
                fds_surfs.append(1)  # 0 + 1 for F90
        fds_surfs = tuple(fds_surfs)

        # Write bingeom
        utils.write_bingeom(
            feedback=self.feedback,
            filepath=self._filepath,
            geom_type=2,
            n_surf_id=n_surf_id,
            fds_verts=fds_verts,
            fds_faces=fds_faces,
            fds_surfs=fds_surfs,
            fds_volus=list(),
        )

    def get_fds(self) -> str:
        """Get the FDS text and save."""
        self._save_bingeom()
        self.feedback.pushInfo(f"GEOM terrain ready.")
        return f"""
Terrain ({len(self._verts)} verts, {len(self._faces)} faces)
&GEOM ID='Terrain'
      SURF_ID={self.landuse_type.surf_id_str}
      BINARY_FILE='{self._filename}'
      IS_TERRAIN=T EXTEND_TERRAIN=F /"""


# OBST terrain


class OBSTTerrain(GEOMTerrain):
    def __init__(
        self,
        feedback,
        sampling_layer,
        utm_origin,
        landuse_layer,
        landuse_type,
        fire_layer,
        path=None,  # unused
        name=None,  # unused
    ) -> None:
        self.feedback = feedback
        self.sampling_layer = sampling_layer
        self.utm_origin = utm_origin
        self.landuse_layer = landuse_layer
        self.landuse_type = landuse_type
        self.fire_layer = fire_layer

        # Init
        self.min_z = 0.0
        self.max_z = 0.0

        # Calc
        self._init_matrix()

        if self.feedback.isCanceled():
            return {}

        self._inject_ghost_centers()
        self._init_obsts()

    def _init_obsts(self):
        """Get the formatted OBSTs from sampling layer."""
        feedback = self.feedback
        feedback.pushInfo("Prepare OBSTs...")
        feedback.setProgress(0)
        m = self._m
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
            try:
                surf_id = surf_id_dict[lu]
            except ValueError:
                self.feedback.reportError(f"Unknown landuse index <{lu}>, setting <0>.")
                surf_id = surf_id_dict[0]
            _obsts.append(
                f"&OBST XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},{xb[4]:.2f},{xb[5]:.2f} SURF_ID='{surf_id}' /"
            )
            if ip % partial_progress == 0:
                self.feedback.setProgress(int(ip / ncenters * 100))

        self._obsts = _obsts

    def get_fds(self) -> str:
        """Get the FDS text."""
        self.feedback.pushInfo(f"OBST terrain ready.")
        obsts_str = "\n".join(self._obsts)
        return f"""
Terrain ({len(self._obsts)} OBSTs)
{obsts_str}
"""
