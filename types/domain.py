# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from math import sqrt
from . import utils


class Domain:
    def __init__(
        self,
        feedback,
        utm_crs,
        utm_extent,
        utm_origin,
        wgs84_origin,
        min_z,
        max_z,
        cell_size,
        nmesh,
    ) -> None:
        feedback.pushInfo("Init MESH...")

        self.feedback = feedback
        self.utm_extent = utm_extent
        self.utm_origin = utm_origin

        # Calc domain XB, relative to origin
        dom_xb = (
            utm_extent.xMinimum() - utm_origin.x(),
            utm_extent.xMaximum() - utm_origin.x(),
            utm_extent.yMinimum() - utm_origin.y(),
            utm_extent.yMaximum() - utm_origin.y(),
            min_z,
            max_z + cell_size * 10,  # 10 cells over max z
        )

        # Calc number of MESH along x and y
        ratio = abs((dom_xb[1] - dom_xb[0]) / (dom_xb[3] - dom_xb[2]))
        nmesh_y = round(sqrt(nmesh / ratio))
        nmesh_x = int(nmesh / nmesh_y)

        # Calc MESH XB
        m_xb = (
            dom_xb[0],
            dom_xb[0] + (dom_xb[1] - dom_xb[0]) / nmesh_x,
            dom_xb[2],
            dom_xb[2] + (dom_xb[3] - dom_xb[2]) / nmesh_y,
            dom_xb[4],
            dom_xb[5],
        )

        # Calc MESH IJK
        m_ijk = (
            int((m_xb[1] - m_xb[0]) / cell_size),
            int((m_xb[3] - m_xb[2]) / cell_size),
            int((m_xb[5] - m_xb[4]) / cell_size),
        )

        # Calc MESH MULT DX DY
        mult_dx, mult_dy = m_xb[1] - m_xb[0], m_xb[3] - m_xb[2]

        # Calc MESH size and cell number
        mesh_sizes = [m_xb[1] - m_xb[0], m_xb[3] - m_xb[2], m_xb[5] - m_xb[4]]
        ncell = m_ijk[0] * m_ijk[1] * m_ijk[2]

        # Prepare comment string
        utm_crs_desc = utm_crs.description()
        utm_origin_desc = f"{utm_origin.x():.1f}E {utm_origin.y():.1f}N"
        e = utm_extent
        domain_extent_desc = f"{e.xMinimum():.1f}-{e.xMaximum():.1f}E {e.yMinimum():.1f}-{e.yMaximum():.1f}N"

        self._comment = f"""
Selected UTM CRS: {utm_crs_desc}
Domain origin: {utm_origin_desc}
  <{utils.get_lonlat_url(wgs84_origin)}>
Domain extent: {domain_extent_desc}
"""

        # Prepare fds string
        self._fds = f"""
Domain and its boundary conditions
{nmesh_x:d} · {nmesh_y:d} meshes of {mesh_sizes[0]:.1f}m · {mesh_sizes[1]:.1f}m · {mesh_sizes[2]:.1f}m size and {ncell:d} cells each
&MULT ID='Meshes'
      DX={mult_dx:.2f} I_LOWER=0 I_UPPER={nmesh_x-1:d}
      DY={mult_dy:.2f} J_LOWER=0 J_UPPER={nmesh_y-1:d} /
&MESH IJK={m_ijk[0]:d},{m_ijk[1]:d},{m_ijk[2]:d} MULT_ID='Meshes'
      XB={m_xb[0]:.2f},{m_xb[1]:.2f},{m_xb[2]:.2f},{m_xb[3]:.2f},{m_xb[4]:.2f},{m_xb[5]:.2f} /
&VENT ID='Domain BC XMIN' DB='XMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC XMAX' DB='XMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC YMIN' DB='YMIN' SURF_ID='OPEN' /
&VENT ID='Domain BC YMAX' DB='YMAX' SURF_ID='OPEN' /
&VENT ID='Domain BC ZMAX' DB='ZMAX' SURF_ID='OPEN' /

Wind rose at domain origin
&DEVC ID='Origin_UV' XYZ=0.,0.,{(m_xb[5]-.1):.2f} QUANTITY='U-VELOCITY' /
&DEVC ID='Origin_VV' XYZ=0.,0.,{(m_xb[5]-.1):.2f} QUANTITY='V-VELOCITY' /
&DEVC ID='Origin_WV' XYZ=0.,0.,{(m_xb[5]-.1):.2f} QUANTITY='W-VELOCITY' /"""

    def get_comment(self) -> str:
        return self._comment

    def get_fds(self) -> str:
        return self._fds
