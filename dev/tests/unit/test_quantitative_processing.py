"""Quantitative generated-layer tests for the production Processing algorithm.

Every case is created from scratch in a temporary directory. The test invokes
the installed qgis2fds provider through ``qgis_process``, then reads the OBST
terrain cells from the resulting FDS file. This exercises real QGIS layer
loading, GDAL reprojection/resampling, fire rasterization, and FDS generation
without maintaining opaque binary fixtures or reference hashes.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
import pytest

from qgis_case import QgisProcessUnavailable, _configured_qgis_process_command


# Flatpak can access this repository but not the host's normal /tmp directory.
REPOSITORY_DIRECTORY = Path(__file__).resolve().parents[3]

# Use a metric CRS whose central meridian is close to the small synthetic
# domain. The large-looking coordinates are ordinary UTM coordinates and avoid
# testing special behavior around the false easting or equator.
CRS_AUTHID = "EPSG:32632"
DOMAIN_X_MIN = 500_000.0
DOMAIN_Y_MIN = 5_000_000.0

# ESRI ASCII grids have no embedded CRS, so every generated raster receives a
# matching .prj sidecar containing this WKT definition.
CRS_WKT = (
    'PROJCS["WGS 84 / UTM zone 32N",GEOGCS["WGS 84",'
    'DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",9],PARAMETER["scale_factor",0.9996],'
    'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],'
    'UNIT["metre",1],AUTHORITY["EPSG","32632"]]'
)

# OBST is selected for these tests because every sampled terrain cell is then
# directly readable as one text record: XB contains its bounds and elevation,
# while SURF_ID exposes the resolved landuse or fire classification.
OBST_PATTERN = re.compile(
    r"^&OBST XB="
    r"([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+), "
    r"SURF_ID='([^']+)' /$"
)


@dataclass(frozen=True)
class GeneratedRaster:
    """Generated source raster plus the numeric grid used to create it."""

    filepath: Path
    values: np.ndarray
    x_min: float
    y_min: float
    pixel_size: float


@dataclass(frozen=True)
class ExportedTerrain:
    """Core terrain cells reconstructed from the generated FDS input."""

    elevations: np.ndarray
    surfaces: np.ndarray
    x_centers: np.ndarray
    y_centers: np.ndarray


@pytest.fixture
def generated_case_directory(request, quantitative_case_run_directory):
    """Provide one automatically removed workspace visible to QGIS Flatpak."""

    if quantitative_case_run_directory is not None:
        # Parameter IDs become readable folder names such as
        # test_generated_uniform_slope_finer.
        case_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name).strip("_")
        case_directory = quantitative_case_run_directory / case_name
        case_directory.mkdir()
        yield case_directory
        return

    # QGIS Flatpak has a private /tmp, so place ephemeral cases below the
    # repository where both the host test process and QGIS can access them.
    with tempfile.TemporaryDirectory(
        prefix=".qgis2fds-test-quantitative-",
        dir=REPOSITORY_DIRECTORY,
    ) as temporary:
        yield Path(temporary)


@pytest.fixture(scope="session")
def quantitative_case_run_directory(pytestconfig):
    """Create one retained run directory when pytest.ini requests it."""

    configured = pytestconfig.getini("quantitative_cases_directory").strip()
    if not configured:
        return None

    storage_directory = Path(configured).expanduser()
    if not storage_directory.is_absolute():
        storage_directory = REPOSITORY_DIRECTORY / storage_directory
    storage_directory.mkdir(parents=True, exist_ok=True)

    # A timestamp keeps runs ordered for humans; the process ID prevents a
    # collision between simultaneous or same-second pytest invocations.
    run_name = "run-{}-{}".format(
        datetime.now().strftime("%Y%m%d-%H%M%S"),
        os.getpid(),
    )
    run_directory = storage_directory / run_name
    run_directory.mkdir()

    reporter = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            "Retaining generated quantitative cases in {}".format(run_directory)
        )
    return run_directory


def _write_project(directory):
    """Write the smallest saved QGIS project needed by the exporter."""
    # Input layers are supplied as Processing parameters, so they do not need
    # entries in the project layer tree. The project supplies a saved path and
    # an explicit metric CRS while keeping texture rendering out of these tests.
    project = directory / "quantitative.qgs"
    project.write_text(
        """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname="quantitative" version="4.2.0">
  <homePath path=""/>
  <projectCrs>
    <spatialrefsys nativeFormat="Wkt">
      <wkt>{wkt}</wkt>
      <proj4>+proj=utm +zone=32 +datum=WGS84 +units=m +no_defs</proj4>
      <srsid>32632</srsid>
      <srid>32632</srid>
      <authid>{authid}</authid>
      <description>WGS 84 / UTM zone 32N</description>
      <projectionacronym>utm</projectionacronym>
      <ellipsoidacronym>EPSG:7030</ellipsoidacronym>
      <geographicflag>false</geographicflag>
    </spatialrefsys>
  </projectCrs>
  <layer-tree-group>
    <customproperties><Option/></customproperties>
    <custom-order enabled="0"/>
  </layer-tree-group>
  <projectlayers/>
  <properties/>
</qgis>
""".format(wkt=CRS_WKT, authid=CRS_AUTHID),
        encoding="utf-8",
    )
    return project


def _write_polygon(directory, name, bounds):
    """Write one rectangular GeoJSON feature in the common UTM CRS."""
    x_min, y_min, x_max, y_max = bounds
    polygon = {
        "type": "FeatureCollection",
        "name": name,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::32632"},
        },
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x_min, y_min],
                            [x_max, y_min],
                            [x_max, y_max],
                            [x_min, y_max],
                            [x_min, y_min],
                        ]
                    ],
                },
            }
        ],
    }
    filepath = directory / (name + ".geojson")
    filepath.write_text(json.dumps(polygon), encoding="utf-8")
    return filepath


def _write_ascii_raster(
    directory,
    name,
    values,
    x_min,
    y_min,
    pixel_size=1.0,
):
    """Write a numeric ESRI ASCII grid and its matching projection sidecar."""
    values = np.asarray(values)
    rows, columns = values.shape
    filepath = directory / (name + ".asc")
    header = (
        "ncols {columns}\n"
        "nrows {rows}\n"
        "xllcorner {x_min:.9f}\n"
        "yllcorner {y_min:.9f}\n"
        "cellsize {pixel_size:.9f}\n"
        "NODATA_value -9999\n"
    ).format(
        columns=columns,
        rows=rows,
        x_min=x_min,
        y_min=y_min,
        pixel_size=pixel_size,
    )
    # ESRI ASCII grids are written north-to-south; qgis2fds arrays are
    # south-to-north, so reverse the generated rows on disk.
    body = "\n".join(
        " ".join("{:.12g}".format(float(value)) for value in row)
        for row in values[::-1]
    )
    filepath.write_text(header + body + "\n", encoding="ascii")
    filepath.with_suffix(".prj").write_text(CRS_WKT + "\n", encoding="ascii")
    return GeneratedRaster(filepath, values, x_min, y_min, pixel_size)


def _write_function_dem(directory, width, height, function, margin=2.5):
    """Evaluate an analytic elevation function on a buffered native 1 m DEM."""
    # The native DEM is 1 m. The default margin puts the valley on a source-cell
    # center; a 2 m margin aligns its centers with the 1 m terrain/landuse grid.
    # Both margins provide neighbors around the requested domain.
    x_min = DOMAIN_X_MIN - margin
    y_min = DOMAIN_Y_MIN - margin
    columns = int(width + 2.0 * margin)
    rows = int(height + 2.0 * margin)
    x = x_min + np.arange(columns) + 0.5 - (DOMAIN_X_MIN + width / 2.0)
    y = y_min + np.arange(rows) + 0.5 - (DOMAIN_Y_MIN + height / 2.0)
    # Analytic functions use local coordinates centered on the requested
    # extent, matching the horizontal coordinates written to the FDS file.
    x_grid, y_grid = np.meshgrid(x, y)
    return _write_ascii_raster(
        directory,
        "dem",
        function(x_grid, y_grid),
        x_min,
        y_min,
    )


def _write_landuse(directory, size, offset):
    """Create an aligned or deliberately three-quarter-cell-offset landuse grid."""
    if offset:
        # The extra border keeps the shifted raster covering the full domain.
        source_size = size + 2
        row, column = np.indices((source_size, source_size))
        values = 1 + (2 * row + column) % 4
        x_min = DOMAIN_X_MIN - 0.75
        y_min = DOMAIN_Y_MIN - 0.75
        name = "landuse_offset"
    else:
        row, column = np.indices((size, size))
        values = 1 + (2 * row + column) % 4
        x_min = DOMAIN_X_MIN
        y_min = DOMAIN_Y_MIN
        name = "landuse_aligned"
    # Vary codes in both axes. This asymmetric pattern detects row reversal,
    # column shifts, and accidental use of continuous interpolation.
    return _write_ascii_raster(directory, name, values, x_min, y_min)


def _write_catalog(directory):
    """Write surface IDs that make every categorical result easy to inspect."""
    catalog = directory / "landuse.csv"
    # The final two rows intentionally follow the current fire convention:
    # perimeter first (Ignition), then polygon interior (Burned).
    catalog.write_text(
        "landuse,SURF\n"
        '1,"&SURF ID=\'Class1\' /"\n'
        '2,"&SURF ID=\'Class2\' /"\n'
        '3,"&SURF ID=\'Class3\' /"\n'
        '4,"&SURF ID=\'Class4\' /"\n'
        '1000,"&SURF ID=\'Ignition\', VEG_LSET_IGNITE_TIME=0. /"\n'
        '1001,"&SURF ID=\'Burned\' /"\n',
        encoding="utf-8",
    )
    return catalog


def _run_export(
    directory,
    chid,
    width,
    height,
    pixel_size,
    dem,
    landuse=None,
    fire_bounds=None,
):
    """Generate the remaining inputs and execute the production exporter."""
    try:
        command = _configured_qgis_process_command()
    except QgisProcessUnavailable as error:
        pytest.skip(str(error))

    project = _write_project(directory)
    # The extent is an exact multiple of every tested pixel size. Therefore any
    # unexpected row or column in the output is a grid-alignment regression.
    extent = _write_polygon(
        directory,
        "extent",
        (
            DOMAIN_X_MIN,
            DOMAIN_Y_MIN,
            DOMAIN_X_MIN + width,
            DOMAIN_Y_MIN + height,
        ),
    )
    output = directory / "FDS"
    output.mkdir()
    parameters = {
        "project_path": project,
        "distance_units": "meters",
        "area_units": "m2",
        "chid": chid,
        "fds_path": output,
        "extent_layer": extent,
        "pixel_size": pixel_size,
        "dem_layer": dem.filepath,
        "tex_pixel_size": 1,
        "nmesh": 1,
        "cell_size": 1,
        "t_begin": 0,
        "t_end": 1,
        "export_obst": True,
    }
    if landuse is not None:
        parameters["landuse_layer"] = landuse.filepath
        parameters["landuse_type_filepath"] = _write_catalog(directory)
    if fire_bounds is not None:
        # Test expectations use local FDS coordinates centered on the extent;
        # GeoJSON needs the corresponding absolute UTM coordinates.
        parameters["fire_layer"] = _write_polygon(
            directory,
            "fire",
            tuple(
                value + origin
                for value, origin in zip(
                    fire_bounds,
                    (
                        DOMAIN_X_MIN + width / 2.0,
                        DOMAIN_Y_MIN + height / 2.0,
                        DOMAIN_X_MIN + width / 2.0,
                        DOMAIN_Y_MIN + height / 2.0,
                    ),
                )
            ),
        )

    command.extend(("run", "NIST FDS:Export FDS case"))
    # Match qgis_process's documented --name=value form and avoid a shell, so
    # spaces and paths cannot acquire a second round of shell interpretation.
    for name, value in parameters.items():
        if isinstance(value, bool):
            value = str(value).lower()
        command.append("--{}={}".format(name, value))
    completed = subprocess.run(
        command,
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "qgis_process failed with exit code {}\nSTDOUT:\n{}\nSTDERR:\n{}".format(
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )
        )
    return _read_exported_terrain(output / (chid + ".fds"))


def _read_exported_terrain(filepath):
    """Parse the core, row-major terrain OBST cells from one FDS case."""
    content = filepath.read_text(encoding="utf-8")
    dimensions = re.search(r"^! Terrain: (\d+) x (\d+) cells", content, re.M)
    if dimensions is None:
        raise AssertionError("Generated FDS file has no terrain dimensions")
    columns, rows = (int(value) for value in dimensions.groups())
    cells = []
    for line in content.splitlines():
        match = OBST_PATTERN.match(line)
        if match is not None:
            coordinates = tuple(float(value) for value in match.groups()[:6])
            cells.append((coordinates, match.group(7)))
    # terrain_namelists writes the sampled cells first and any padded-domain
    # edge/corner OBST records afterward. Only the first rows*columns records
    # represent the quantitative raster under test.
    cells = cells[: columns * rows]
    if len(cells) != columns * rows:
        raise AssertionError(
            "Generated FDS file has {} core OBST cells; expected {}".format(
                len(cells), columns * rows
            )
        )

    elevations = np.array([cell[0][5] for cell in cells]).reshape(rows, columns)
    surfaces = np.array([cell[1] for cell in cells], dtype=object).reshape(
        rows, columns
    )
    x_centers = np.array(
        [0.5 * (cell[0][0] + cell[0][1]) for cell in cells]
    ).reshape(rows, columns)
    y_centers = np.array(
        [0.5 * (cell[0][2] + cell[0][3]) for cell in cells]
    ).reshape(rows, columns)
    return ExportedTerrain(elevations, surfaces, x_centers, y_centers)


def _expected_landuse(exported, source, width, height):
    """Resolve target cell centers through independent nearest-neighbor math."""
    # FDS coordinates are local to the extent centroid; source raster indexes
    # are based on absolute UTM coordinates.
    center_x = DOMAIN_X_MIN + width / 2.0
    center_y = DOMAIN_Y_MIN + height / 2.0
    global_x = center_x + exported.x_centers
    global_y = center_y + exported.y_centers
    columns = np.floor((global_x - source.x_min) / source.pixel_size).astype(int)
    rows = np.floor((global_y - source.y_min) / source.pixel_size).astype(int)
    codes = source.values[rows, columns]
    return np.vectorize(
        lambda code: "Class{}".format(int(code)), otypes=[object]
    )(codes)


def _assert_exported_grid(exported, width, height, pixel_size):
    """Check exact square-grid dimensions and centroid-relative cell centers."""
    columns = int(round(width / pixel_size))
    rows = int(round(height / pixel_size))
    assert exported.elevations.shape == (rows, columns)
    expected_x = -width / 2.0 + (np.arange(columns) + 0.5) * pixel_size
    expected_y = -height / 2.0 + (np.arange(rows) + 0.5) * pixel_size
    # OBST coordinates are serialized to three decimal places, hence the small
    # half-millimeter tolerance used for their reconstructed centers.
    np.testing.assert_allclose(
        exported.x_centers,
        np.broadcast_to(expected_x, (rows, columns)),
        atol=5.1e-4,
    )
    np.testing.assert_allclose(
        exported.y_centers,
        np.broadcast_to(expected_y[:, None], (rows, columns)),
        atol=5.1e-4,
    )


@pytest.mark.qgis
@pytest.mark.parametrize(
    "pixel_size",
    (
        pytest.param(0.5, id="finer"),
        pytest.param(1.0, id="native"),
        pytest.param(2.0, id="coarser"),
    ),
)
def test_generated_uniform_slope(generated_case_directory, pixel_size):
    """A 20% east and 10% north plane survives production DEM sampling."""
    dem = _write_function_dem(
        generated_case_directory,
        6.0,
        4.0,
        lambda x, y: 100.0 + 0.20 * x + 0.10 * y,
    )
    exported = _run_export(
        generated_case_directory,
        "uniform_slope_{}".format(str(pixel_size).replace(".", "_")),
        6.0,
        4.0,
        pixel_size,
        dem,
    )

    _assert_exported_grid(exported, 6.0, 4.0, pixel_size)
    # A bilinear resampler must preserve a plane at every resolution. Check both
    # absolute elevations and the directional rise/run values.
    expected = 100.0 + 0.20 * exported.x_centers + 0.10 * exported.y_centers
    np.testing.assert_allclose(exported.elevations, expected, atol=1.1e-3)
    np.testing.assert_allclose(
        np.diff(exported.elevations, axis=1) / pixel_size,
        0.20,
        atol=2.1e-3,
    )
    np.testing.assert_allclose(
        np.diff(exported.elevations, axis=0) / pixel_size,
        0.10,
        atol=2.1e-3,
    )


@pytest.mark.qgis
@pytest.mark.parametrize(
    "pixel_size",
    (
        pytest.param(0.5, id="finer"),
        pytest.param(1.0, id="native"),
        pytest.param(2.0, id="coarser"),
    ),
)
def test_generated_two_slope_valley(generated_case_directory, pixel_size):
    """Specified 40% west and 80% east slopes meet at the valley center."""

    def valley(x, y):
        del y
        return 50.0 + np.where(x <= 0.0, -0.40 * x, 0.80 * x)

    dem = _write_function_dem(generated_case_directory, 10.0, 4.0, valley)
    exported = _run_export(
        generated_case_directory,
        "valley_{}".format(str(pixel_size).replace(".", "_")),
        10.0,
        4.0,
        pixel_size,
        dem,
    )

    _assert_exported_grid(exported, 10.0, 4.0, pixel_size)
    expected = 50.0 + np.where(
        exported.x_centers <= 0.0,
        -0.40 * exported.x_centers,
        0.80 * exported.x_centers,
    )
    if pixel_size > dem.pixel_size:
        # A 2 m GDAL bilinear sample centered on the sharp 1 m valley combines
        # values from both specified slopes. This is the expected coarsening,
        # not a loss of the valley in the source DEM.
        expected[np.isclose(exported.x_centers, 0.0)] = 50.3
    np.testing.assert_allclose(exported.elevations, expected, atol=1.1e-3)
    x_midpoints = 0.5 * (
        exported.x_centers[0, :-1] + exported.x_centers[0, 1:]
    )
    slopes = np.diff(exported.elevations, axis=1) / pixel_size
    # Ignore intervals touching the sharp valley when measuring each constant
    # side slope; coarse bilinear sampling legitimately smooths that kink.
    np.testing.assert_allclose(
        slopes[:, x_midpoints <= -pixel_size], -0.40, atol=2.1e-3
    )
    np.testing.assert_allclose(
        slopes[:, x_midpoints >= pixel_size], 0.80, atol=2.1e-3
    )


@pytest.mark.qgis
@pytest.mark.parametrize("offset", (False, True), ids=("aligned", "offset"))
def test_generated_dem_and_landuse(generated_case_directory, offset):
    """Check continuous DEM and categorical landuse sampling on two alignments."""
    dem = _write_function_dem(
        generated_case_directory,
        4.0,
        4.0,
        lambda x, y: 10.0 + 0.5 * x - 0.25 * y,
        margin=2.0,
    )
    landuse = _write_landuse(generated_case_directory, 4, offset)
    exported = _run_export(
        generated_case_directory,
        "dem_landuse_{}".format("offset" if offset else "aligned"),
        4.0,
        4.0,
        1.0,
        dem,
        landuse=landuse,
    )

    _assert_exported_grid(exported, 4.0, 4.0, 1.0)
    np.testing.assert_allclose(
        exported.elevations,
        10.0 + 0.5 * exported.x_centers - 0.25 * exported.y_centers,
        atol=1.1e-3,
    )
    # Surface IDs are compared cell by cell instead of using an output hash, so
    # a failure shows the exact categorical displacement.
    np.testing.assert_array_equal(
        exported.surfaces,
        _expected_landuse(exported, landuse, 4.0, 4.0),
    )


@pytest.mark.qgis
@pytest.mark.parametrize(
    ("offset", "fire_bounds", "inside_count", "perimeter_count"),
    (
        (False, (-1.0, -1.0, 1.0, 1.0), 4, 12),
        (True, (-0.75, -1.75, 0.75, 1.75), 8, 12),
    ),
    ids=("aligned", "offset"),
)
def test_generated_dem_landuse_and_fire(
    generated_case_directory,
    offset,
    fire_bounds,
    inside_count,
    perimeter_count,
):
    """Check landuse plus exact fire perimeter/interior cells on two alignments."""
    dem = _write_function_dem(
        generated_case_directory,
        6.0,
        6.0,
        lambda x, y: 25.0 + 0.1 * x + 0.2 * y,
        margin=2.0,
    )
    landuse = _write_landuse(generated_case_directory, 6, offset)
    exported = _run_export(
        generated_case_directory,
        "dem_landuse_fire_{}".format("offset" if offset else "aligned"),
        6.0,
        6.0,
        1.0,
        dem,
        landuse=landuse,
        fire_bounds=fire_bounds,
    )

    _assert_exported_grid(exported, 6.0, 6.0, 1.0)
    expected = _expected_landuse(exported, landuse, 6.0, 6.0)
    x_min, y_min, x_max, y_max = fire_bounds
    inside = (
        (exported.x_centers > x_min)
        & (exported.x_centers < x_max)
        & (exported.y_centers > y_min)
        & (exported.y_centers < y_max)
    )
    # QGIS buffers the fire polygon by one terrain pixel. For these rectangles,
    # Euclidean point-to-rectangle distance independently identifies cell
    # centers inside that rounded buffer.
    dx = np.maximum.reduce(
        (
            x_min - exported.x_centers,
            np.zeros_like(exported.x_centers),
            exported.x_centers - x_max,
        )
    )
    dy = np.maximum.reduce(
        (
            y_min - exported.y_centers,
            np.zeros_like(exported.y_centers),
            exported.y_centers - y_max,
        )
    )
    perimeter = (np.hypot(dx, dy) < 1.0) & ~inside
    # Production applies the perimeter first and the original polygon second,
    # so Burned must overwrite Ignition for every interior cell.
    expected[perimeter] = "Ignition"
    expected[inside] = "Burned"

    np.testing.assert_array_equal(exported.surfaces, expected)
    assert np.count_nonzero(exported.surfaces == "Burned") == inside_count
    assert np.count_nonzero(exported.surfaces == "Ignition") == perimeter_count
