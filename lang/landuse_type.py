# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import csv, re, os
from qgis.core import QgsProcessingException
from . import utils


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

    def __init__(self, feedback, project_path, filepath) -> None:
        self.feedback = feedback
        self.filepath = filepath and os.path.join(project_path, filepath) or str()
        if filepath:
            msg = f"\nImport landuse type *.csv file: <{self.filepath}>"
            self.feedback.pushInfo(msg)
            self.surf_dict = dict()
            self.surf_id_dict = dict()
            self._import()
        else:
            self.feedback.pushInfo(f"\nNo landuse type *.csv file.")
            self.surf_dict = {}  # INERT is predefined, FDS SURF not needed
            self.surf_id_dict = {0: "INERT"}
        msg = f"Default bcs for the fire layer: bc_in=<{self.bc_in_default}>, bc_out=<{self.bc_out_default}>."
        self.feedback.pushInfo(msg)

    def _import(self) -> None:
        try:
            with open(self.filepath) as csv_file:
                # landuse csv file has an header line and two columns:
                # landuse integer number and corresponding FDS SURF str
                csv_reader = csv.reader(csv_file, delimiter=",")
                next(csv_reader)  # skip header linelanduse_path
                for r in csv_reader:
                    key, value_surf = int(r[0]), str(r[1])
                    found_id = re.search(self._scan_id, value_surf)
                    if not found_id:
                        msg = f"No FDS SURF ID found in <{value_surf}> from landuse type *.csv file."
                        raise QgsProcessingException(msg)
                    value_id = found_id.groups()[0]
                    self.surf_dict[key] = value_surf  # eg: {98: "&SURF ID='A04' ... /"}
                    self.surf_id_dict[key] = value_id  # eg: {98: 'A04'}
        except IOError as err:
            msg = f"Error importing landuse type *.csv file from <{self.filepath}>:\n{err}"
            raise QgsProcessingException(msg)
        if len(set(self.surf_id_dict.values())) != len(self.surf_id_dict):
            msg = f"Duplicated FDS ID in landuse type *.csv file not allowed."
            raise QgsProcessingException(msg)

    def get_comment(self) -> str:
        return f"Landuse type file: <{self.filepath and utils.shorten(self.filepath) or 'none'}>"

    def get_fds(self) -> str:
        res = "\n".join(self.surf_dict.values())
        return f"""
Landuse boundary conditions
{res or 'none'}"""

    @property
    def surf_id_str(self):
        return ",".join((f"'{s}'" for s in self.surf_id_dict.values()))

    @property
    def bc_out_default(self) -> str:
        try:
            return list(self.surf_id_dict)[-2]  # eg. Ignition
        except IndexError:
            return 0

    @property
    def bc_in_default(self) -> str:
        try:
            return list(self.surf_id_dict)[-1]  # eg. Burned
        except KeyError:
            return 0
