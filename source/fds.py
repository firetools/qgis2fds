"""Pure-Python parsing and serialization of an FDS wildfire case."""

import csv
import math
import os
import re
from dataclasses import dataclass

import numpy as np


SURFACE_ID = re.compile(
    r"(?:^|[,\s])ID\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL
)
CHID = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class Surface:
    code: int
    fds_id: str
    namelist: str = ""


class SurfaceCatalog:
    """Map integer raster values to FDS SURF definitions."""

    def __init__(self, surfaces, filepath=""):
        self.surfaces = tuple(surfaces)
        self.filepath = filepath
        self._by_code = {surface.code: surface for surface in self.surfaces}
        # BINGEOM stores 1-based positions in its SURF_ID list, not the original
        # integer landuse codes found in the raster.
        self._index_by_code = {
            surface.code: index + 1 for index, surface in enumerate(self.surfaces)
        }

    @classmethod
    def load(cls, filepath):
        if not filepath:
            # A DEM-only export remains a valid inert terrain case.
            return cls((Surface(0, "INERT"),))

        surfaces = []
        seen_codes = set()
        seen_ids = set()
        try:
            with open(filepath, "r", encoding="utf-8-sig", newline="") as handle:
                rows = csv.reader(handle)
                header = next(rows, None)
                if header is None or len(header) < 2:
                    raise ValueError("the CSV file has no two-column header")
                for line_number, row in enumerate(rows, 2):
                    if not row or all(not item.strip() for item in row):
                        continue
                    if len(row) < 2:
                        raise ValueError(
                            "line {} does not contain a code and SURF".format(line_number)
                        )
                    code = int(row[0].strip())
                    namelist = row[1].strip()
                    match = SURFACE_ID.search(namelist)
                    if match is None:
                        raise ValueError(
                            "line {} has no SURF ID".format(line_number)
                        )
                    fds_id = match.group(2).strip()
                    if code in seen_codes:
                        raise ValueError("duplicate landuse code {}".format(code))
                    if fds_id.casefold() in seen_ids:
                        raise ValueError("duplicate SURF ID '{}'".format(fds_id))
                    seen_codes.add(code)
                    seen_ids.add(fds_id.casefold())
                    surfaces.append(Surface(code, fds_id, namelist))
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            raise ValueError(
                "Cannot read landuse type file '{}': {}".format(filepath, error)
            )

        if not surfaces:
            raise ValueError("The landuse type file contains no surfaces.")
        return cls(surfaces, filepath)

    @property
    def outside_fire_code(self):
        # Historical catalogs reserve their final two rows for the fire perimeter
        # ring and interior. Preserve that convention for existing projects.
        return self.surfaces[-2].code if len(self.surfaces) >= 2 else self.surfaces[0].code

    @property
    def inside_fire_code(self):
        return self.surfaces[-1].code

    @property
    def fds_ids(self):
        return tuple(surface.fds_id for surface in self.surfaces)

    @property
    def fds_definitions(self):
        return "\n".join(
            surface.namelist for surface in self.surfaces if surface.namelist
        )

    def fds_id(self, code):
        surface = self._by_code.get(code) or self._by_code.get(0)
        return surface.fds_id if surface else self.surfaces[0].fds_id

    def fds_index(self, code):
        return self._index_by_code.get(
            code, self._index_by_code.get(0, 1)
        )

    def unknown_codes(self, terrain):
        # NumPy finds distinct raster classes in compiled code; only the usually
        # small unique set needs Python dictionary lookups.
        observed = np.unique(terrain.landuse)
        return [int(code) for code in observed if int(code) not in self._by_code]


@dataclass(frozen=True)
class WindSample:
    time: float
    speed: float
    direction: float


def read_wind(filepath):
    """Read Time, Speed, Direction rows from a wind CSV file."""
    if not filepath:
        return ()
    samples = []
    try:
        with open(filepath, "r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle)
            header = next(rows, None)
            if header is None or len(header) < 3:
                raise ValueError("the CSV file has no three-column header")
            for line_number, row in enumerate(rows, 2):
                if not row or all(not item.strip() for item in row):
                    continue
                if len(row) < 3:
                    raise ValueError("line {} has fewer than three values".format(line_number))
                sample = WindSample(float(row[0]), float(row[1]), float(row[2]))
                if not all(
                    math.isfinite(value)
                    for value in (sample.time, sample.speed, sample.direction)
                ):
                    raise ValueError("line {} has a non-finite value".format(line_number))
                if sample.speed < 0.0:
                    raise ValueError("line {} has a negative wind speed".format(line_number))
                if samples and sample.time < samples[-1].time:
                    # FDS ramp points must be emitted in chronological order.
                    raise ValueError("wind times must be in ascending order")
                samples.append(sample)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        raise ValueError("Cannot read wind file '{}': {}".format(filepath, error))
    if not samples:
        raise ValueError("The wind file contains no samples.")
    return tuple(samples)


@dataclass(frozen=True)
class MeshLayout:
    count_x: int
    count_y: int
    cells_x: int
    cells_y: int
    cells_z: int
    x_min: float
    y_min: float
    z_min: float
    mesh_width: float
    mesh_height: float
    domain_height: float

    @property
    def count(self):
        return self.count_x * self.count_y

    @property
    def x_max(self):
        return self.x_min + self.count_x * self.mesh_width

    @property
    def y_max(self):
        return self.y_min + self.count_y * self.mesh_height

    @property
    def z_max(self):
        return self.z_min + self.domain_height


def build_mesh_layout(terrain, cell_size, maximum_meshes):
    """Build balanced equal-size meshes, never exceeding maximum_meshes."""
    grid = terrain.grid
    # Replicated meshes need identical dimensions for FDS MULT, so round each
    # axis up to a whole number of cells per mesh.
    count_x, count_y = _mesh_factors(grid.width, grid.height, maximum_meshes)
    cells_x = max(1, int(math.ceil(grid.width / (count_x * cell_size))))
    cells_y = max(1, int(math.ceil(grid.height / (count_y * cell_size))))
    mesh_width = cells_x * cell_size
    mesh_height = cells_y * cell_size
    # Put at least one cell below the lowest terrain point and retain clearance
    # above the highest point, even though Mode 1 does not solve atmospheric flow.
    z_min = math.floor((terrain.min_elevation - cell_size) / cell_size) * cell_size
    clearance = max(10.0 * cell_size, 0.1 * (terrain.max_elevation - z_min))
    cells_z = max(
        11,
        int(math.ceil((terrain.max_elevation + clearance - z_min) / cell_size)),
    )
    return MeshLayout(
        count_x=count_x,
        count_y=count_y,
        cells_x=cells_x,
        cells_y=cells_y,
        cells_z=cells_z,
        x_min=grid.x_min - grid.origin_x,
        y_min=grid.y_min - grid.origin_y,
        z_min=z_min,
        mesh_width=mesh_width,
        mesh_height=mesh_height,
        domain_height=cells_z * cell_size,
    )


def terrain_namelists(terrain, catalog, layout, export_obst, binary_filename):
    if not export_obst:
        # This order must match the 1-based surface indexes written for every
        # triangle in the companion BINGEOM file.
        surface_ids = ",".join(_quote(fds_id) for fds_id in catalog.fds_ids)
        return (
            "! Terrain: {} vertices, {} triangular faces\n"
            "&GEOM ID='Terrain', SURF_ID={}, BINARY_FILE={}, "
            "IS_TERRAIN=T, EXTEND_TERRAIN=F /"
        ).format(
            (terrain.grid.columns + 1) * (terrain.grid.rows + 1),
            2 * terrain.grid.columns * terrain.grid.rows,
            surface_ids,
            _quote(binary_filename),
        )

    lines = [
        "! Terrain: {} OBST cells".format(terrain.grid.columns * terrain.grid.rows)
    ]
    grid = terrain.grid
    for row in range(grid.rows):
        # Horizontal coordinates are local to the selected origin; elevations
        # remain in the vertical datum of the source DEM.
        y0 = grid.y_min + row * grid.pixel_size - grid.origin_y
        y1 = y0 + grid.pixel_size
        for column in range(grid.columns):
            x0 = grid.x_min + column * grid.pixel_size - grid.origin_x
            x1 = x0 + grid.pixel_size
            z1 = terrain.elevations[row][column]
            lines.append(
                "&OBST XB={:.3f},{:.3f},{:.3f},{:.3f},{:.3f},{:.3f}, SURF_ID={} /".format(
                    x0,
                    x1,
                    y0,
                    y1,
                    layout.z_min,
                    z1,
                    _quote(catalog.fds_id(terrain.landuse[row][column])),
                )
            )
    return "\n".join(lines)


def render_case(
    chid,
    t_begin,
    t_end,
    terrain,
    catalog,
    layout,
    wind,
    export_obst,
    binary_filename,
    texture_filename,
    extra_text,
    provenance,
    dem_name,
    landuse_name,
    fire_name,
):
    """Render a complete, surface-only FDS wildfire input file."""
    if not CHID.fullmatch(chid):
        raise ValueError(
            "CHID may contain only letters, digits, underscores, periods, and hyphens."
        )
    if t_end < t_begin:
        raise ValueError("t_end must be greater than or equal to t_begin.")

    grid = terrain.grid
    image_entry = (
        ",\n      TERRAIN_IMAGE={}".format(_quote(texture_filename))
        if texture_filename
        else ""
    )
    surfaces = catalog.fds_definitions or "! No custom SURF definitions"
    free_text = extra_text.strip()
    if free_text:
        free_text = "\n! User-supplied FDS text\n" + free_text + "\n"

    # LEVEL_SET_MODE is deliberately fixed at 1. Changing it would enable wind
    # field or atmosphere coupling and alter the meaning and cost of these cases.
    return """! Generated by qgis2fds {provenance}
! Coordinate system: {crs}
! Domain origin: {origin_x:.3f} E, {origin_y:.3f} N
! Geographic origin: {latitude:.7f}, {longitude:.7f}
! Terrain resolution: {pixel_size:.3f} m
! DEM layer: {dem_name}
! Landuse layer: {landuse_name}
! Landuse type file: {landuse_file}
! Fire layer: {fire_name}

&HEAD CHID={chid}, TITLE={title} /
&TIME T_BEGIN={t_begin:.6g}, T_END={t_end:.6g} /

! LEVEL_SET_MODE=1: empirical surface-only propagation with uniform global wind.
! No terrain-modified flow, active fire heat release, or fluid solve is computed.
&MISC ORIGIN_LAT={latitude:.7f}, ORIGIN_LON={longitude:.7f},
      NORTH_BEARING=0., LEVEL_SET_MODE=1{image_entry} /
&RADI RADIATION=F /

! {mesh_count} meshes; {cells_x} x {cells_y} x {cells_z} cells per mesh
&MULT ID='Meshes', DX={mesh_width:.3f}, I_LOWER=0, I_UPPER={mesh_x_max},
      DY={mesh_height:.3f}, J_LOWER=0, J_UPPER={mesh_y_max} /
&MESH MULT_ID='Meshes', IJK={cells_x},{cells_y},{cells_z},
      XB={x_min:.3f},{mesh_x_end:.3f},{y_min:.3f},{mesh_y_end:.3f},{z_min:.3f},{z_max:.3f} /
&VENT MB='XMIN', SURF_ID='OPEN' /
&VENT MB='XMAX', SURF_ID='OPEN' /
&VENT MB='YMIN', SURF_ID='OPEN' /
&VENT MB='YMAX', SURF_ID='OPEN' /
&VENT MB='ZMAX', SURF_ID='OPEN' /

! Landuse boundary conditions
{surfaces}

! Wind
{wind_text}

{terrain_text}

! Level-set output above ground
&SLCF AGL_SLICE=5., QUANTITY='LEVEL SET VALUE' /
{free_text}
&TAIL /
""".format(
        provenance=provenance,
        crs=grid.crs_description,
        origin_x=grid.origin_x,
        origin_y=grid.origin_y,
        latitude=grid.latitude,
        longitude=grid.longitude,
        pixel_size=grid.pixel_size,
        dem_name=dem_name,
        landuse_name=landuse_name or "none",
        landuse_file=catalog.filepath or "none",
        fire_name=fire_name or "none",
        chid=_quote(chid),
        title=_quote("Wildfire terrain {}".format(chid)),
        t_begin=t_begin,
        t_end=t_end,
        image_entry=image_entry,
        mesh_count=layout.count,
        cells_x=layout.cells_x,
        cells_y=layout.cells_y,
        cells_z=layout.cells_z,
        mesh_width=layout.mesh_width,
        mesh_height=layout.mesh_height,
        mesh_x_max=layout.count_x - 1,
        mesh_y_max=layout.count_y - 1,
        x_min=layout.x_min,
        mesh_x_end=layout.x_min + layout.mesh_width,
        y_min=layout.y_min,
        mesh_y_end=layout.y_min + layout.mesh_height,
        z_min=layout.z_min,
        z_max=layout.z_max,
        surfaces=surfaces,
        wind_text=_wind_namelists(wind),
        terrain_text=terrain_namelists(
            terrain, catalog, layout, export_obst, binary_filename
        ),
        free_text=free_text,
    )


def write_text(filepath, content):
    """Atomically write UTF-8 text."""
    temporary = filepath + ".tmp"
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, filepath)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def _mesh_factors(width, height, maximum):
    best = None
    for count_x in range(1, maximum + 1):
        for count_y in range(1, maximum // count_x + 1):
            used = count_x * count_y
            mesh_aspect = (width / count_x) / (height / count_y)
            # Favor nearly square meshes, then favor using more of the allowed
            # count. The tuple supplies deterministic tie-breaking.
            score = abs(math.log(mesh_aspect)) + 3.0 * (maximum - used) / maximum
            candidate = (score, -used, count_x, count_y)
            if best is None or candidate < best:
                best = candidate
    return best[2], best[3]


def _wind_namelists(samples):
    if not samples:
        return "&WIND SPEED=0., DIRECTION=0. /"
    # SPEED=1 makes ramp values physical speeds rather than fractions of a base.
    lines = ["&WIND SPEED=1., RAMP_SPEED_T='q2f_ws', RAMP_DIRECTION_T='q2f_wd' /"]
    for sample in samples:
        lines.append(
            "&RAMP ID='q2f_ws', T={:.6g}, F={:.6g} /".format(
                sample.time, sample.speed
            )
        )
    for sample in samples:
        lines.append(
            "&RAMP ID='q2f_wd', T={:.6g}, F={:.6g} /".format(
                sample.time, sample.direction
            )
        )
    return "\n".join(lines)


def _quote(value):
    # FDS follows Fortran escaping: apostrophes are doubled inside string literals.
    return "'{}'".format(str(value).replace("'", "''"))
