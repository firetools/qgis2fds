# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi, Ruggero Poletto"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

import csv

wind_ramp_example_str = f"""! example ramp
&RAMP ID='ws', T=   0, F=10. /
&RAMP ID='ws', T= 600, F=10. /
&RAMP ID='ws', T=1200, F=20. /
&RAMP ID='wd', T=   0, F=315. /
&RAMP ID='wd', T= 600, F=270. /
&RAMP ID='wd', T=1200, F=360. /"""


def get_wind_ramp_str(feedback, wind_filepath):
    if not wind_filepath:
        return wind_ramp_example_str
    ws, wd = list(), list()
    try:
        with open(wind_filepath) as csv_file:
            # wind csv file has an header line and three columns:
            # time in seconds, wind speed in m/s, and direction in degrees
            csv_reader = csv.reader(csv_file, delimiter=",")
            next(csv_reader)  # skip header line
            for r in csv_reader:
                ws.append(f"&RAMP ID='ws', T={float(r[0]):.1f}, F={float(r[1]):.1f} /")
                wd.append(f"&RAMP ID='wd', T={float(r[0]):.1f}, F={float(r[2]):.1f} /")
        ws.extend(wd)
        feedback.pushInfo(f"Read wind from <{wind_filepath}>")
        return "\n".join(ws)
    except Exception as err:
        feedback.reportError(f"Error importing wind *.csv file: {err}")
        return f"! Wind *.csv file import ERROR: {err}"