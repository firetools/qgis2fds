# -*- coding: utf-8 -*-

"""qgis2fds"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1

from dataclasses import dataclass
from typing import Collection

# FIXME not used yet

# Classes


@dataclass
class DataColl:
    collection = list()  # named collection of instances, redefine locally
    hid: str

    def __post_init__(self):
        if self.get_by_hid(self.hid):
            raise IndexError(f"Item <{self.hid}> already defined")
        self.coll[self.hid] = self  # add to named collection

    @classmethod
    def get_by_hid(cls, hid):
        for c in cls.coll:
            if hid == c.hid:
                return c


@dataclass
class LanduseType(DataColl):
    coll = dict()  # local dict
    desc: str
    surfs: tuple

    def to_fds(self):
        return "\n".join(self.surfs)


@dataclass
class LanduseChoice(DataColl):
    coll = dict()  # local dict
    landuse_type: LanduseType
    choice: dict
    default: int = 0

    def to_fds(self, value):
        try:
            return self.choice[value]
        except KeyError:
            raise KeyError(
                f"Landuse value <{value}> has no reference to SURF in <{self.landuse_type.hid}> landuse type"
            )


# Landuse types and choices


LanduseType(
    hid="Unspecified",
    desc="Unspecified",
    surfs=("&SURF ID='NA' RGB=255,255,255 /",),
)

LanduseType(
    hid="Landfire.gov F13",
    desc="Landfire.gov 13 Anderson Fire Behavior Fuel Models",
    surfs=(
        "&SURF ID='A01' RGB=255,254,212 VEG_LSET_FUEL_INDEX= 1 /",
        "&SURF ID='A02' RGB=255,253,102 VEG_LSET_FUEL_INDEX= 2 /",
        "&SURF ID='A03' RGB=236,212, 99 VEG_LSET_FUEL_INDEX= 3 /",
        "&SURF ID='A04' RGB=254,193,119 VEG_LSET_FUEL_INDEX= 4 /",
        "&SURF ID='A05' RGB=249,197, 92 VEG_LSET_FUEL_INDEX= 5 /",
        "&SURF ID='A06' RGB=217,196,152 VEG_LSET_FUEL_INDEX= 6 /",
        "&SURF ID='A07' RGB=170,155,127 VEG_LSET_FUEL_INDEX= 7 /",
        "&SURF ID='A08' RGB=229,253,214 VEG_LSET_FUEL_INDEX= 8 /",
        "&SURF ID='A09' RGB=162,191, 90 VEG_LSET_FUEL_INDEX= 9 /",
        "&SURF ID='A10' RGB=114,154, 85 VEG_LSET_FUEL_INDEX=10 /",
        "&SURF ID='A11' RGB=235,212,253 VEG_LSET_FUEL_INDEX=11 /",
        "&SURF ID='A12' RGB=163,177,243 VEG_LSET_FUEL_INDEX=12 /",
        "&SURF ID='A13' RGB=  0,  0,  0 VEG_LSET_FUEL_INDEX=13 /",
        "&SURF ID='Urban' RGB=186,119, 80 /",
        "&SURF ID='Snow-Ice' RGB=234,234,234 /",
        "&SURF ID='Agriculture' RGB=253,242,242 /",
        "&SURF ID='Water' RGB=137,183,221 /",
        "&SURF ID='Barren' RGB=133,153,156 /",
        "&SURF ID='NA' RGB=255,255,255 /",
    ),
)


LanduseChoice(
    hid="Unspecified",
    landuse_type=LanduseType.coll["Landfire F13"],
    choice=dict(),
)

LanduseChoice(
    hid="Landfire.gov F13",
    landuse_type=LanduseType.coll["Landfire F13"],
    choice={
        0: 19,
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
    default=0,
)

LanduseChoice(
    hid="CIMA Propagator",
    landuse_type=LanduseType.coll["Landfire F13"],
    choice={
        0: 19,
        1: 5,
        2: 4,
        3: 18,
        4: 10,
        5: 10,
        6: 1,
        7: 1,
    },
)
