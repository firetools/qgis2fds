# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import csv, re

from qgis.core import QgsProcessingException, NULL, edit, QgsFeatureRequest

_scan_id = re.compile(  # search ID value in SURF
    r"""
        [,\s\t]+   # 1+ separator
        ID
        [,\s\t]*   # 0+ separator
        =
        [,\s\t]*   # 0+ separator
        (?:'(.+?)'|"(.+?)")  # protected string
        [,\s\t]+   # 1+ separator
        """,
    re.VERBOSE | re.DOTALL | re.IGNORECASE,
)  # no MULTILINE, so that $ is the end of the file


def get_surf_id_str(feedback, landuse_dict):
    if landuse_dict:
        surf_id = list()
        for l in landuse_dict.values():
            surf_id.append(re.search(_scan_id, l).groups()[0])
        return ",".join((f"'{s}'" for s in surf_id))
    else:
        return "'INERT'"


def get_surfs_str(feedback, landuse_dict):
    if landuse_dict:
        return "\n".join(landuse_dict.values())


def get_landuse_dict(feedback, landuse_type_filepath):
    landuse_dict = dict()
    feedback.pushInfo(f"Read landuse type *.csv file: <{landuse_type_filepath}>")
    try:
        with open(landuse_type_filepath) as csv_file:
            # landuse csv file has an header line and two columns:
            # landuse integer number and corresponding FDS SURF str
            csv_reader = csv.reader(csv_file, delimiter=",")
            next(csv_reader)  # skip header linelanduse_path
            for i, r in enumerate(csv_reader):
                # Example: {98: "&SURF ID='A04' ... /"}
                landuse_dict[int(r[0])] = str(r[1])
    except Exception as err:
        raise QgsProcessingException(
            f"Error importing landuse type *.csv file from <{landuse_type_filepath}>:\n{err}"
        )
    if len(landuse_dict) < 2:
        raise QgsProcessingException(
            f"At least two lines required in landuse type file <{landuse_type_filepath}>."
        )
    return landuse_dict


def apply_fire_layer_bcs_to_point_layer(
    feedback, point_layer, fire_layer_utm, dem_layer_res, landuse_dict
):
    # Sample fire_layer for ignition lines and burned areas
    landuse_idx = point_layer.fields().indexOf("landuse1")
    border_distance = dem_layer_res  # size of border
    # Get bcs to be set
    # default for Ignition and Burned
    bc_out_default, bc_in_default = list(landuse_dict)[-2:]
    bc_in_idx = fire_layer_utm.fields().indexOf("bc_in")
    bc_out_idx = fire_layer_utm.fields().indexOf("bc_out")
    with edit(point_layer):
        for fire_feat in fire_layer_utm.getFeatures():
            # Get fire feature geometry and bbox
            fire_geom = fire_feat.geometry()
            fire_geom_bbox = fire_geom.boundingBox()
            # Check if user specified bcs available
            if bc_in_idx != -1:  # found
                bc_in = fire_feat[bc_in_idx]
            else:
                bc_in = bc_in_default
            if bc_out_idx != -1:  # found
                bc_out = fire_feat[bc_out_idx]
            else:
                bc_out = bc_out_default
            # Check bbox min size
            if (
                fire_geom_bbox.height() < border_distance
                and fire_geom_bbox.width() < border_distance
            ):
                # Replaced by its centroid
                fire_geom = fire_geom.centroid()
            # Feedback
            feedback.pushInfo(
                f"Set <bc_in={bc_in}> and <bc_out={bc_out}> bcs to the terrain from fire layer <{fire_feat.id()}> feature"
            )
            # Set new bcs in point layer
            # for speed, preselect points with grown bbox
            fire_geom_bbox.grow(delta=border_distance * 2.0)
            for point_feat in point_layer.getFeatures(
                QgsFeatureRequest(fire_geom_bbox)
            ):
                point_geom = point_feat.geometry()
                if fire_geom.contains(point_geom):
                    if bc_in != NULL:
                        # Set inside bc
                        point_layer.changeAttributeValue(
                            point_feat.id(), landuse_idx, bc_in
                        )
                else:
                    if (
                        bc_out != NULL
                        and point_geom.distance(fire_geom) < border_distance
                    ):
                        # Set border bc
                        point_layer.changeAttributeValue(
                            point_feat.id(), landuse_idx, bc_out
                        )
    point_layer.updateFields()
