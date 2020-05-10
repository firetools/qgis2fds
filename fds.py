# -*- coding: utf-8 -*-

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


from qgis.core import QgsExpressionContextUtils, QgsProject

import time
from . import utils


SURF_selections = {
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
}


def _get_surf_str():
    return "\n".join(
        (
            f"! Boundary conditions",
            f"! 13 Anderson Fire Behavior Fuel Models",  # FIXME
            # f"&SURF ID='A01' RGB=255,252,167 VEG_LSET_FUEL_INDEX= 1 HRRPUA=100. RAMP_Q='f01' /",  # FIXME RGB and other
            # f"&SURF ID='A02' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 2 HRRPUA=500. RAMP_Q='f02' /",
            # f"&SURF ID='A03' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 3 HRRPUA=500. RAMP_Q='f03' /",
            # f"&SURF ID='A04' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 4 HRRPUA=500. RAMP_Q='f04' /",
            # f"&SURF ID='A05' RGB=241,142, 27 VEG_LSET_FUEL_INDEX= 5 HRRPUA=500. RAMP_Q='f05' /",
            # f"&SURF ID='A06' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 6 HRRPUA=500. RAMP_Q='f06' /",
            # f"&SURF ID='A07' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 7 HRRPUA=500. RAMP_Q='f07' /",
            # f"&SURF ID='A08' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 8 HRRPUA=500. RAMP_Q='f08' /",
            # f"&SURF ID='A09' RGB=252,135, 47 VEG_LSET_FUEL_INDEX= 9 HRRPUA=500. RAMP_Q='f09' /",
            # f"&SURF ID='A10' RGB= 42, 82, 23 VEG_LSET_FUEL_INDEX=10 HRRPUA=500. RAMP_Q='f10' /",
            # f"&SURF ID='A11' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=11 HRRPUA=500. RAMP_Q='f11' /",
            # f"&SURF ID='A12' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=12 HRRPUA=500. RAMP_Q='f12' /",
            # f"&SURF ID='A13' RGB=252,135, 47 VEG_LSET_FUEL_INDEX=13 HRRPUA=500. RAMP_Q='f13' /",
            f"&SURF ID='A01' RGB=255,252,167 HRRPUA=100. RAMP_Q='f01' /",  # FIXME RGB and other
            f"&SURF ID='A02' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f02' /",
            f"&SURF ID='A03' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f03' /",
            f"&SURF ID='A04' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f04' /",
            f"&SURF ID='A05' RGB=241,142, 27 HRRPUA=500. RAMP_Q='f05' /",
            f"&SURF ID='A06' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f06' /",
            f"&SURF ID='A07' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f07' /",
            f"&SURF ID='A08' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f08' /",
            f"&SURF ID='A09' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f09' /",
            f"&SURF ID='A10' RGB= 42, 82, 23 HRRPUA=500. RAMP_Q='f10' /",
            f"&SURF ID='A11' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f11' /",
            f"&SURF ID='A12' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f12' /",
            f"&SURF ID='A13' RGB=252,135, 47 HRRPUA=500. RAMP_Q='f13' /",
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
        )
    )


def _get_geom_str(verts, faces, landuses, landuse_type):
    SURF_select = SURF_selections[landuse_type]
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
            f"{f[0]},{f[1]},{f[2]},{SURF_select.get(landuses[i], landuses[0])},"  # on error, choose NA
            for i, f in enumerate(faces)
        )
    )
    return "\n".join(
        (
            f"! Terrain",
            f"&GEOM ID='Terrain' IS_TERRAIN=T EXTEND_TERRAIN=F",
            f"      SURF_ID={surfid_str}",
            f"      VERTS={verts_str}",
            f"      FACES={faces_str} /",
        )
    )


def get_case(
    dem_layer,
    landuse_layer,
    chid,
    origin,
    utm_origin,
    fire_origin,
    utm_fire_origin,
    utm_crs,
    verts,
    faces,
    landuses,
    landuse_type,
):
    """
    Get FDS case.
    """
    # Header
    # pv = qgis.utils.pluginMetadata("QGIS2FDS", "version")  # TODO
    qv = QgsExpressionContextUtils.globalScope().variable("qgis_version")
    now = time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())
    filepath = QgsProject.instance().fileName() or "not saved"
    if len(filepath) > 60:
        filepath = "..." + filepath[-57:]

    # VENT
    x, y = (
        utm_fire_origin.x() - utm_origin.x(),  # relative to origin
        utm_fire_origin.y() - utm_origin.y(),
    )  # center of VENT patch

    return "\n".join(
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
            f"! Origin at <{utils.get_utm_str(utm_origin, utm_crs)}>",
            f"! Link: <{utils.get_lonlat_url(origin)}>",
            f" MISC ORIGIN_LAT={origin.y():.7f} ORIGIN_LON={origin.x():.7f} NORTH_BEARING=0. / ! New",
            f"&MISC TERRAIN_CASE=T SIMULATION_MODE='SVLES' TERRAIN_IMAGE='{chid}_texture.jpg' /",
            f" ",
            f"! Reaction",
            f"! from Karlsson, Quintiere 'Enclosure Fire Dyn', CRC Press, 2000",
            f"&REAC ID='Wood' FUEL='PROPANE', SOOT_YIELD=0.015 /",
            f" ",
            f"! Domain and its boundary conditions",
            f"&MESH IJK=50,50,50 XB=-500.000,500.000,-500.000,500.000,-10.000,1000.000 /",
            f"&TRNZ MESH_NUMBER=0 IDERIV=1 CC=0 PC=0.5 /",
            f"&VENT MB='XMIN' SURF_ID='OPEN' /",
            f"&VENT MB='XMAX' SURF_ID='OPEN' /",
            f"&VENT MB='YMIN' SURF_ID='OPEN' /",
            f"&VENT MB='YMAX' SURF_ID='OPEN' /",
            f"&VENT MB='ZMAX' SURF_ID='OPEN' /",
            f" ",
            f"! Fire origin at <{utils.get_utm_str(utm_fire_origin, utm_crs)}>",
            f"! Link: <{utils.get_lonlat_url(fire_origin)}>",
            f"&SURF ID='Ignition' VEG_LSET_IGNITE_TIME=1800. COLOR='RED' /",
            f"&VENT XB={x-5:.3f},{x+5:.3f},{y-5:.3f},{y+5:.3f},-10.000,-10.000 SURF_ID='Ignition' GEOM=T /",
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
            _get_surf_str(),
            f" ",
            _get_geom_str(verts, faces, landuses, landuse_type),
            f" ",
            f"&TAIL /\n",
        )
    )
