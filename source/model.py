"""Small data objects shared by the exporter modules."""

from dataclasses import dataclass
from typing import List


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
    longitude: float
    latitude: float

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
    """Elevation and surface codes, with rows ordered south to north."""

    grid: SpatialGrid
    elevations: List[List[float]]
    landuse: List[List[int]]

    @property
    def min_elevation(self):
        return min(min(row) for row in self.elevations)

    @property
    def max_elevation(self):
        return max(max(row) for row in self.elevations)

    def corner_elevation(self, row, column):
        """Average the adjacent cell centers at a grid corner."""
        values = []
        for cell_row in (row - 1, row):
            if not 0 <= cell_row < self.grid.rows:
                continue
            for cell_column in (column - 1, column):
                if 0 <= cell_column < self.grid.columns:
                    values.append(self.elevations[cell_row][cell_column])
        return sum(values) / len(values)
