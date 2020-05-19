# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from qgis.core import QgsExpressionContextUtils, QgsProject
from qgis.utils import pluginMetadata
import time
from . import utils

# Config

landuse_types = "Landfire FBFM13", "CIMA Propagator"

landuse_types_selections = {
    0: {  # "Landfire FBFM13"
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
    1: {  # "CIMA Propagator"
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
            f"&SURF ID='A01' RGB=255,254,212 VEG_LSET_FUEL_INDEX= 1 HRRPUA=100. RAMP_Q='f01' /",
            f"&SURF ID='A02' RGB=255,253,102 VEG_LSET_FUEL_INDEX= 2 HRRPUA=500. RAMP_Q='f02' /",
            f"&SURF ID='A03' RGB=236,212, 99 VEG_LSET_FUEL_INDEX= 3 HRRPUA=500. RAMP_Q='f03' /",
            f"&SURF ID='A04' RGB=254,193,119 VEG_LSET_FUEL_INDEX= 4 HRRPUA=500. RAMP_Q='f04' /",
            f"&SURF ID='A05' RGB=249,197, 92 VEG_LSET_FUEL_INDEX= 5 HRRPUA=500. RAMP_Q='f05' /",
            f"&SURF ID='A06' RGB=217,196,152 VEG_LSET_FUEL_INDEX= 6 HRRPUA=500. RAMP_Q='f06' /",
            f"&SURF ID='A07' RGB=170,155,127 VEG_LSET_FUEL_INDEX= 7 HRRPUA=500. RAMP_Q='f07' /",
            f"&SURF ID='A08' RGB=229,253,214 VEG_LSET_FUEL_INDEX= 8 HRRPUA=500. RAMP_Q='f08' /",
            f"&SURF ID='A09' RGB=162,191, 90 VEG_LSET_FUEL_INDEX= 9 HRRPUA=500. RAMP_Q='f09' /",
            f"&SURF ID='A10' RGB=114,154, 85 VEG_LSET_FUEL_INDEX=10 HRRPUA=500. RAMP_Q='f10' /",
            f"&SURF ID='A11' RGB=235,212,253 VEG_LSET_FUEL_INDEX=11 HRRPUA=500. RAMP_Q='f11' /",
            f"&SURF ID='A12' RGB=163,177,243 VEG_LSET_FUEL_INDEX=12 HRRPUA=500. RAMP_Q='f12' /",
            f"&SURF ID='A13' RGB=  0,  0,  0 VEG_LSET_FUEL_INDEX=13 HRRPUA=500. RAMP_Q='f13' /",
            f"&SURF ID='Urban' RGB=186,119, 80 /",
            f"&SURF ID='Snow-Ice' RGB=234,234,234 /",
            f"&SURF ID='Agricolture' RGB=253,242,242 /",
            f"&SURF ID='Water' RGB=137,183,221 /",
            f"&SURF ID='Barren' RGB=133,153,156 /",
            f"&SURF ID='NA' RGB=255,255,255 /",
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
    landuse_select = landuse_types_selections[landuse_type]
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
            f"{f[0]},{f[1]},{f[2]},{landuse_select.get(landuses[i], landuses[0])},"  # on error, choose NA
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
    wgs84_origin,
    utm_origin,
    wgs84_fire_origin,
    utm_fire_origin,
    utm_crs,
    verts,
    faces,
    landuses,
    landuse_type,
    landuses_set,
    utm_extent,
):
    """
    Get FDS case.
    """
    # Calc header
    pv = pluginMetadata("qgis2fds", "version")
    qv = QgsExpressionContextUtils.globalScope().variable("qgis_version")
    now = time.strftime("%a, %d %b %Y, %H:%M:%S", time.localtime())
    filepath = QgsProject.instance().fileName() or "not saved"
    if len(filepath) > 60:
        filepath = "..." + filepath[-57:]

    # Calc MESH XB
    mesh_xb = (
        utm_extent.xMinimum() - utm_origin.x(),
        utm_extent.xMaximum() - utm_origin.x(),
        utm_extent.yMinimum() - utm_origin.y(),
        utm_extent.yMaximum() - utm_origin.y(),
        min(v[2] for v in verts) - 1.0,
        max(v[2] for v in verts) + 100.0,
    )
    # Calc center of VENT patch
    fire_x, fire_y = (
        utm_fire_origin.x() - utm_origin.x(),  # relative to origin
        utm_fire_origin.y() - utm_origin.y(),
    )

    return "\n".join(
        (
            f"! Generated by qgis2fds <{pv}> on QGIS <{qv}>",
            f"! QGIS file: <{filepath}>",
            f"! Selected UTM CRS: <{utm_crs.description()}>",
            f"! Terrain extent: <{utm_extent.toString(precision=1)}>",
            f"! DEM layer: <{dem_layer.name()}>",
            f"! Landuse layer: <{landuse_layer and landuse_layer.name() or 'None'}>",
            f"! Landuse type: <{landuse_layer and ('Landfire FBFM13', 'CIMA Propagator')[landuse_type] or 'None'}>",
            f"! Domain Origin: <{utm_origin.x():.1f}, {utm_origin.y():.1f}>",
            f"! Domain Origin Link: <{utils.get_lonlat_url(wgs84_origin)}>",
            f"! Fire Origin: <{utm_fire_origin.x():.1f}, {utm_fire_origin.y():.1f}>",
            f"! Fire Origin Link: <{utils.get_lonlat_url(wgs84_fire_origin)}>",
            f"! Date: <{now}>",
            f" ",
            f"&HEAD CHID='{chid}' TITLE='Description of {chid}' /",
            f"&TIME T_END=1. /",
            f"&RADI RADIATION=F /",
            f" ",
            f" MISC ORIGIN_LAT={wgs84_origin.y():.7f} ORIGIN_LON={wgs84_origin.x():.7f} NORTH_BEARING=0. / ! New",
            f"&MISC TERRAIN_CASE=T SIMULATION_MODE='SVLES' TERRAIN_IMAGE='{chid}_texture.png' /",
            f" ",
            f"! Reaction",
            f"! from Karlsson, Quintiere 'Enclosure Fire Dyn', CRC Press, 2000",
            f"&REAC ID='Wood' FUEL='PROPANE', SOOT_YIELD=0.015 /",
            f" ",
            f"! Domain and its boundary conditions",
            f"&MESH IJK=50,50,50 XB={mesh_xb[0]:.3f},{mesh_xb[1]:.3f},{mesh_xb[2]:.3f},{mesh_xb[3]:.3f},{mesh_xb[4]:.3f},{mesh_xb[5]:.3f} /",
            f"&TRNZ MESH_NUMBER=0 IDERIV=1 CC=0 PC=0.5 /",
            f"&VENT MB='XMIN' SURF_ID='OPEN' /",
            f"&VENT MB='XMAX' SURF_ID='OPEN' /",
            f"&VENT MB='YMIN' SURF_ID='OPEN' /",
            f"&VENT MB='YMAX' SURF_ID='OPEN' /",
            f"&VENT MB='ZMAX' SURF_ID='OPEN' /",
            f" ",
            f"! Fire origin",
            f"&SURF ID='Ignition' VEG_LSET_IGNITE_TIME=1800. COLOR='RED' /",
            f"&VENT XB={fire_x-5:.3f},{fire_x+5:.3f},{fire_y-5:.3f},{fire_y+5:.3f},-10.000,-10.000 SURF_ID='Ignition' GEOM=T /",
            f" ",
            f"! Output quantities",
            f"&BNDF QUANTITY='BURNING RATE' /",
            f"&SLCF DB='ZMID', QUANTITY='VELOCITY', VECTOR=T /",
            f"&SLCF AGL_SLICE=25., QUANTITY='VELOCITY', VECTOR=T /",
            f"&SLCF AGL_SLICE=1., QUANTITY='LEVEL SET VALUE' /",
            f" ",
            f"! Wind",
            f"&WIND SPEED=1., RAMP_SPEED='ws', RAMP_DIRECTION='wd', LATITUDE={wgs84_origin.y():.7f}, DT_MEAN_FORCING=20. /",
            f"&RAMP ID='ws', T=0, F=0. /",
            f"&RAMP ID='ws', T=600, F=10. /",
            f"&RAMP ID='ws', T=1200, F=20. /",
            f"&RAMP ID='wd', T=0, F=330. /",
            f"&RAMP ID='wd', T=600, F=300. /",
            f"&RAMP ID='wd', T=1200, F=270. /",
            f" ",
            _get_surf_str(),  # TODO should send the right ones
            f" ",
            _get_geom_str(
                verts, faces, landuses, landuse_type
            ),  # TODO should receive surfid
            f" ",
            f"&TAIL /\n",
        )
    )
