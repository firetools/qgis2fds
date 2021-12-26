# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1


from . import utils
from math import sqrt


class Domain:
    def __init__(
        self,
        feedback,
        wgs84_origin,
        utm_crs,
        utm_extent,
        utm_origin,
        min_z,
        max_z,
        cell_size,
        nmesh,
    ) -> None:
        self.feedback = feedback
        self.wgs84_origin = wgs84_origin
        self.utm_crs = utm_crs
        self.utm_extent = utm_extent
        self.utm_origin = utm_origin
        self.min_z = min_z
        self.max_z = max_z
        self.mesh_xb = 0, 0, 0, 0, 0, 0
        self.cell_size = cell_size
        self.nmesh = nmesh

    def get_comment(self) -> str:
        return f"""! Domain:
!   Selected UTM CRS: <{self.utm_crs.description()}>
!   Origin: <{self.utm_origin.x():.1f}, {self.utm_origin.y():.1f}>
!           <{utils.get_lonlat_url(self.wgs84_origin)}>
!   Extent: <{self.utm_extent.toString(precision=1)}>"""

    def get_fds(self) -> str:
        self.feedback.pushInfo("Init MESHes...")
        # Calc domain XB, relative to origin
        domain_xb = (
            self.utm_extent.xMinimum() - self.utm_origin.x(),
            self.utm_extent.xMaximum() - self.utm_origin.x(),
            self.utm_extent.yMinimum() - self.utm_origin.y(),
            self.utm_extent.yMaximum() - self.utm_origin.y(),
            self.min_z - 2.0,
            self.max_z + self.cell_size * 10,  # 10 cells over max z
        )

        # Calc number of MESH along x and y
        domain_ratio = abs(
            (domain_xb[1] - domain_xb[0]) / (domain_xb[3] - domain_xb[2])
        )
        nmesh_y = round(sqrt(self.nmesh / domain_ratio))
        nmesh_x = int(self.nmesh / nmesh_y)
        self.feedback.pushInfo(
            f"Number of MESHes: {nmesh_x*nmesh_y} ={nmesh_x:d}x{nmesh_y:d}"
        )

        # Calc MESH XB
        self.mesh_xb = (
            domain_xb[0],
            domain_xb[0] + (domain_xb[1] - domain_xb[0]) / nmesh_x,
            domain_xb[2],
            domain_xb[2] + (domain_xb[3] - domain_xb[2]) / nmesh_y,
            domain_xb[4],
            domain_xb[5],
        )

        # Calc MESH IJK
        mesh_ijk = (
            int((self.mesh_xb[1] - self.mesh_xb[0]) / self.cell_size),
            int((self.mesh_xb[3] - self.mesh_xb[2]) / self.cell_size),
            int((self.mesh_xb[5] - self.mesh_xb[4]) / self.cell_size),
        )

        # Calc MESH MULT DX DY
        mult_dx, mult_dy = (
            self.mesh_xb[1] - self.mesh_xb[0],
            self.mesh_xb[3] - self.mesh_xb[2],
        )

        # Calc MESH size and cell number
        mesh_sizes = (
            round(self.mesh_xb[1] - self.mesh_xb[0]),
            round(self.mesh_xb[3] - self.mesh_xb[2]),
            round(self.mesh_xb[5] - self.mesh_xb[4]),
        )
        ncell = mesh_ijk[0] * mesh_ijk[1] * mesh_ijk[2]

        # Prepare str
        return f"""
! Domain and its boundary conditions
! {nmesh_x:d} x {nmesh_y:d} meshes of {mesh_sizes[0]}m x {mesh_sizes[1]}m x {mesh_sizes[2]}m size and {ncell} cells each
&MULT ID='Meshes'
    DX={mult_dx:.3f} I_LOWER=0 I_UPPER={nmesh_x-1:d}
    DY={mult_dy:.3f} J_LOWER=0 J_UPPER={nmesh_y-1:d} /
&MESH IJK={mesh_ijk[0]:d},{mesh_ijk[1]:d},{mesh_ijk[2]:d} MULT_ID='Meshes'
    XB={self.mesh_xb[0]:.3f},{self.mesh_xb[1]:.3f},{self.mesh_xb[2]:.3f},{self.mesh_xb[3]:.3f},{self.mesh_xb[4]:.3f},{self.mesh_xb[5]:.3f} /
&VENT ID='Domain BC XMIN' DB='XMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC XMAX' DB='XMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC YMIN' DB='YMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC YMAX' DB='YMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC ZMAX' DB='ZMAX' SURF_ID='OPEN' /"""
