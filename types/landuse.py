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
        self.surf_dict = dict()
        self.surf_id_dict = dict()
        if not filepath:
            self.feedback.pushInfo(f"No landuse type *.csv file.")
            self.surf_id_dict[0] = "INERT"
            return
        self._import()

    def _import(self) -> None:
        self.feedback.pushInfo(f"Import landuse type *.csv file: <{self.filepath}>")
        try:
            with open(self.filepath) as csv_file:
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
                    self.surf_dict[key] = value_surf
                    self.surf_id_dict[key] = value_id
        except IOError as err:
            raise QgsProcessingException(
                f"Error importing landuse type *.csv file from <{self.filepath}>:\n{err}"
            )
        if len(self.surf_id_dict) < 2:
            raise QgsProcessingException(
                f"At least two lines required in landuse type file <{self.filepath}>."
            )
        if len(set(self.surf_id_dict.values())) != len(self.surf_id_dict):
            raise QgsProcessingException(
                f"Duplicated FDS ID in landuse type *.csv file not allowed."
            )
        self.feedback.pushInfo(
            f"Default boundary conditions for the fire layer: bc_in=<{self.bc_in_default}>, bc_out=<{self.bc_out_default}>."
        )

    def get_comment(self) -> str:
        return f"! Landuse type file: <{utils.shorten(self.filepath)}>"

    def get_fds(self) -> str:
        result = "\n".join(self.surf_dict.values())
        return f"""
! Landuse boundary conditions
{result}"""

    @property
    def surf_id_str(self):
        return ",".join((f"'{s}'" for s in self.surf_id_dict.values()))

    @property
    def bc_out_default(self) -> str:
        return list(self.surf_id_dict)[-2]

    @property
    def bc_in_default(self) -> str:
        return list(self.surf_id_dict)[-1]
