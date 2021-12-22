# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import csv, os

from qgis.core import QgsProcessingException


class WindRamp:
    def __init__(self, feedback, project_path, filepath) -> None:
        self._filepath = filepath and os.path.join(project_path, filepath) or str()
        self._ws, self._wd = list(), list()
        if not filepath:
            return
        feedback.pushInfo(f"Read wind *.csv file: <{filepath}>")
        try:
            with open(filepath) as csv_file:
                # wind csv file has an header line and three columns:
                # time in seconds, wind speed in m/s, and direction in degrees
                csv_reader = csv.reader(csv_file, delimiter=",")
                next(csv_reader)  # skip header line
                for r in csv_reader:
                    self._ws.append(
                        f"&RAMP ID='ws', T={float(r[0]):.1f}, F={float(r[1]):.1f} /"
                    )
                    self._wd.append(
                        f"&RAMP ID='wd', T={float(r[0]):.1f}, F={float(r[2]):.1f} /"
                    )
        except Exception as err:
            raise QgsProcessingException(
                f"Error importing wind *.csv file from <{filepath}>:\n{err}"
            )

    def __str__(self):
        example = f"""! example
&RAMP ID='ws', T=   0, F=10. /
&RAMP ID='ws', T= 600, F=10. /
&RAMP ID='ws', T=1200, F=20. /
&RAMP ID='wd', T=   0, F=315. /
&RAMP ID='wd', T= 600, F=270. /
&RAMP ID='wd', T=1200, F=360. /"""
        return "&WIND SPEED=1., RAMP_SPEED='ws', RAMP_DIRECTION='wd' /\n" + (
            ("\n".join(self._ws) + "\n".join(self._wd)) or example
        )

    @property
    def comment(self):
        c = (
            len(self._filepath) > 60
            and self._filepath[-57:] + "..."
            or self._filepath
            or "None"
        )
        return f"! Wind file: <{c}>"

    @property
    def filepath(self):
        return self._filepath
