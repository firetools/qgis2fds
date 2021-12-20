# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import csv, re

from qgis.core import QgsProcessingException, NULL, edit, QgsFeatureRequest


class LanduseType:

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

    def __init__(self, feedback, filepath) -> None:
        self._filepath = filepath or str()
        self._surf_dict = dict()
        self._id_dict = dict()
        if not filepath:
            return
        feedback.pushInfo(f"Read landuse type *.csv file: <{filepath}>")
        try:
            with open(filepath) as csv_file:
                # landuse csv file has an header line and two columns:
                # landuse integer number and corresponding FDS SURF str
                csv_reader = csv.reader(csv_file, delimiter=",")
                next(csv_reader)  # skip header linelanduse_path
                for i, r in enumerate(csv_reader):
                    # Example: {98: "&SURF ID='A04' ... /"}
                    key = int(r[0])
                    value_surf = str(r[1])
                    found_id = re.search(self._scan_id, value_surf)
                    if not found_id:
                        raise QgsProcessingException(
                            f"No FDS ID found in <{value_surf}> from landuse type *.csv file."
                        )
                    value_id = found_id.groups()[0]
                    self._surf_dict[key] = value_surf
                    self._id_dict[key] = value_id
        except IOError as err:
            raise QgsProcessingException(
                f"Error importing landuse type *.csv file from <{filepath}>:\n{err}"
            )
        if len(self._id_dict) < 2:
            raise QgsProcessingException(
                f"At least two lines required in landuse type file <{filepath}>."
            )
        if len(set(self._id_dict.values())) != len(self._id_dict):
            raise QgsProcessingException(
                f"Duplicated FDS ID in landuse type *.csv file not allowed."
            )
        try:
            if self._id_dict[1000] != "Ignition":
                raise QgsProcessingException(
                    f"Landuse type *.csv file <{filepath}> should FIXME"  # FIXME error msg
                )
            if self._id_dict[1001] != "Burned":
                raise QgsProcessingException(
                    f"Landuse type *.csv file <{filepath}> should FIXME"  # FIXME error msg
                )
        except KeyError:
            raise QgsProcessingException(
                f"Landuse type *.csv file <{filepath}> should contain index 1000 and 1001"  # FIXME error msg
            )

    @property
    def surf_dict(self):
        return self._surf_dict

    @property
    def surf_str(self):
        return "\n".join(self._surf_dict.values())

    @property
    def id_dict(self):
        return self._id_dict

    @property
    def id_str(self):
        return ",".join((f"'{s}'" for s in self._id_dict.values())) or "'INERT'"

    @property
    def filepath(self):
        return self._filepath

    @property
    def bc_out_default(self):
        return list(self._id_dict)[-2]

    @property
    def bc_in_default(self):
        return list(self._id_dict)[-1]

    def apply_fire_layer_bcs(
        self, feedback, point_layer, fire_layer_utm, dem_layer_res
    ):
        feedback.pushInfo(f"Applying fire_layer bcs to the terrain...")
        # Sample fire_layer for ignition lines and burned areas
        landuse_idx = point_layer.fields().indexOf("landuse1")
        distance = dem_layer_res  # size of border
        # Get bcs to be set
        # default for Ignition and Burned
        bc_out_default = self.bc_out_default
        bc_in_default = self.bc_in_default
        bc_in_idx = fire_layer_utm.fields().indexOf("bc_in")
        bc_out_idx = fire_layer_utm.fields().indexOf("bc_out")
        with edit(point_layer):
            for fire_feat in fire_layer_utm.getFeatures():
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
                distance = dem_layer_res
                h, w = fire_geom_bbox.height(), fire_geom_bbox.width()
                if h < dem_layer_res and w < dem_layer_res:
                    # if small, replaced by its centroid
                    # to simplify 1 cell ignition
                    fire_geom = fire_geom.centroid()
                    distance *= 0.6
                # Set new bcs in point layer
                # for speed, preselect points with grown bbox
                fire_geom_bbox.grow(delta=distance * 2.0)
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
                        if bc_out != NULL and point_geom.distance(fire_geom) < distance:
                            # Set border bc
                            point_layer.changeAttributeValue(
                                point_feat.id(), landuse_idx, bc_out
                            )
                feedback.pushInfo(
                    f"Applied <bc_in={bc_in}> and <bc_out={bc_out}> bcs to the terrain from fire layer <{fire_feat.id()}> feature"
                )
        point_layer.updateFields()
