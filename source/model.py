"""Small data objects shared by the exporter modules."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpatialGrid:
    """A regular, cell-centered terrain grid in a metric CRS."""

    crs_authid: str
    crs_description: str
    x_min: float
    y_min: float
    pixel_size: float
    columns: int
    rows: int
    origin_x: float
    origin_y: float
    # Geographic coordinates feed the FDS MISC origin declaration; origin_x and
    # origin_y are the corresponding coordinates in the metric grid CRS.
    longitude: float
    latitude: float
    # Clockwise angle from projected grid north (+y) to true north, matching FDS.
    north_bearing: float = 0.0

    @property
    def width(self):
        return self.columns * self.pixel_size

    @property
    def height(self):
        return self.rows * self.pixel_size

    @property
    def x_max(self):
        return self.x_min + self.width

    @property
    def y_max(self):
        return self.y_min + self.height

    def x_center(self, column):
        return self.x_min + (column + 0.5) * self.pixel_size

    def y_center(self, row):
        return self.y_min + (row + 0.5) * self.pixel_size


@dataclass
class TerrainData:
    """Dense terrain arrays, with rows ordered south to north."""

    grid: SpatialGrid
    elevations: np.ndarray
    landuse: np.ndarray

    def __post_init__(self):
        # Dense numeric arrays use substantially less memory than nested Python
        # lists and pass directly into the NumPy BINGEOM serializer.
        self.elevations = np.asarray(self.elevations, dtype="<f8")
        # Surface codes come from user CSV files, so retain the full Python-int
        # range normally encountered in practice instead of narrowing to int32.
        self.landuse = np.asarray(self.landuse, dtype="<i8")
        expected_shape = (self.grid.rows, self.grid.columns)
        if self.elevations.shape != expected_shape:
            raise ValueError(
                "Elevation grid has shape {}, expected {}.".format(
                    self.elevations.shape, expected_shape
                )
            )
        if self.landuse.shape != expected_shape:
            raise ValueError(
                "Landuse grid has shape {}, expected {}.".format(
                    self.landuse.shape, expected_shape
                )
            )

    @property
    def min_elevation(self):
        return float(np.min(self.elevations))

    @property
    def max_elevation(self):
        return float(np.max(self.elevations))
