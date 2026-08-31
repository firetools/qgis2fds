"""Read the FDS metadata and binary result files used by the importer.

FDS writes arrays as Fortran unformatted records.  The small reader below is
deliberately limited to the Smokeview records needed by qgis2fds: AGL slices,
structured boundary patches, and unstructured GEOM boundary faces.  Keeping
the format code independent from QGIS makes it reusable and straightforward to
test with synthetic files.
"""

from dataclasses import dataclass, replace
import os
import re
import struct

import numpy as np


WILDFIRE_BOUNDARY_QUANTITIES = frozenset(
    ("FIRE ARRIVAL TIME", "FIRE RESIDENCE TIME", "LS SPREAD RATE")
)


class FdsResultError(ValueError):
    """An input file is missing required metadata or has an invalid format."""


class _IncompleteRecordError(FdsResultError):
    """The last Fortran record was only partly written by a running FDS job."""


@dataclass(frozen=True)
class FdsReference:
    """Geographic reference stored in the FDS MISC namelist."""

    latitude: float
    longitude: float
    north_bearing: float


@dataclass(frozen=True)
class MeshGrid:
    """One structured FDS mesh and its node coordinates."""

    mesh_id: int
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray


@dataclass(frozen=True)
class ResultEntry:
    """One result file advertised by the Smokeview manifest."""

    kind: str
    mesh_id: int
    filename: str
    quantity: str
    short_name: str
    unit: str
    bounds: tuple = ()
    agl: float = None
    topology_filename: str = ""


@dataclass(frozen=True)
class SmokeviewManifest:
    """Subset of a Smokeview manifest needed to locate importable results."""

    meshes: dict
    slices: tuple
    boundaries: tuple


@dataclass(frozen=True)
class SliceSeries:
    """All complete time frames in one structured slice file."""

    quantity: str
    short_name: str
    unit: str
    bounds: tuple
    times: np.ndarray
    values: np.ndarray
    incomplete_tail: bool = False


@dataclass(frozen=True)
class BoundaryPatch:
    """Index bounds and orientation of one structured boundary patch."""

    bounds: tuple
    orientation: int
    obstruction: int


@dataclass(frozen=True)
class BoundarySeries:
    """All complete frames and patches in one structured boundary file."""

    quantity: str
    short_name: str
    unit: str
    patches: tuple
    times: np.ndarray
    # values[time_index][patch_index] is a flat FDS array (i varies fastest).
    values: tuple
    incomplete_tail: bool = False


@dataclass(frozen=True)
class GeometryTopology:
    """Unstructured vertices and triangular faces from an FDS GCF file."""

    vertices: np.ndarray
    faces: np.ndarray


@dataclass(frozen=True)
class GeometryBoundarySeries:
    """Face-centered values from an FDS geometry boundary file."""

    times: np.ndarray
    values: np.ndarray
    incomplete_tail: bool = False


def read_fds_reference(filepath):
    """Read ORIGIN_LAT, ORIGIN_LON, and NORTH_BEARING from ``filepath``."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError as error:
        raise FdsResultError("Cannot read FDS input '{}': {}".format(filepath, error))

    # Strip FDS comments before locating MISC so commented examples cannot be
    # mistaken for active georeferencing values.
    uncommented = "\n".join(line.split("!", 1)[0] for line in text.splitlines())
    match = re.search(r"&MISC\b(.*?)/", uncommented, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        raise FdsResultError("The FDS input has no MISC namelist.")
    misc = match.group(1)

    def number(name):
        value = re.search(
            r"\b{}\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EDed][-+]?\d+)?)".format(
                name
            ),
            misc,
            flags=re.IGNORECASE,
        )
        if value is None:
            raise FdsResultError("MISC does not define {}.".format(name))
        return float(value.group(1).replace("D", "E").replace("d", "e"))

    latitude = number("ORIGIN_LAT")
    longitude = number("ORIGIN_LON")
    north_bearing = number("NORTH_BEARING")
    if not -90.0 <= latitude <= 90.0:
        raise FdsResultError("ORIGIN_LAT is outside the valid latitude range.")
    if not -180.0 <= longitude <= 180.0:
        raise FdsResultError("ORIGIN_LON is outside the valid longitude range.")
    if not np.isfinite(north_bearing):
        raise FdsResultError("NORTH_BEARING is not finite.")
    return FdsReference(latitude, longitude, north_bearing)


def read_smokeview_manifest(filepath):
    """Parse grids and supported output declarations from an FDS SMV file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        raise FdsResultError(
            "Cannot read Smokeview manifest '{}': {}".format(filepath, error)
        )

    meshes = {}
    dimensions = {}
    coordinates = {}
    slices = []
    boundaries = []
    geometry_files = {}
    current_mesh = None
    geometry_mesh = 0
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        keyword = stripped.split(None, 1)[0] if stripped else ""

        if keyword == "GRID":
            current_mesh = len(dimensions) + 1
            dims = _integers(_required_line(lines, index + 1, "GRID dimensions"))
            if len(dims) < 3:
                raise FdsResultError("GRID {} has invalid dimensions.".format(current_mesh))
            dimensions[current_mesh] = tuple(dims[:3])
            coordinates[current_mesh] = {}
            index += 2
            continue

        if keyword in ("TRNX", "TRNY", "TRNZ") and current_mesh is not None:
            axis = keyword[-1].lower()
            expected = dimensions[current_mesh]["xyz".index(axis)] + 1
            values = []
            # The first line is an interpolation-count field, followed by an
            # explicit index/value pair for every grid node.
            for offset in range(expected):
                fields = _required_line(
                    lines, index + 2 + offset, "{} coordinates".format(keyword)
                ).split()
                if len(fields) < 2:
                    raise FdsResultError("{} contains an invalid coordinate.".format(keyword))
                values.append(float(fields[1].replace("D", "E")))
            coordinates[current_mesh][axis] = np.asarray(values, dtype=np.float64)
            index += expected + 2
            continue

        if keyword == "CGEOM":
            geometry_mesh += 1
            geometry_files[geometry_mesh] = _required_line(
                lines, index + 1, "CGEOM filename"
            ).strip()
            index += 2
            continue

        if keyword == "SLCT":
            fields = stripped.replace("&", " ").split("!", 1)[0].split()
            try:
                mesh_id = int(fields[1])
                agl = float(fields[2].replace("D", "E"))
                bounds = tuple(int(value) for value in fields[3:9])
            except (IndexError, ValueError) as error:
                raise FdsResultError("Invalid SLCT declaration: {}".format(stripped)) from error
            if len(bounds) != 6:
                raise FdsResultError("SLCT declaration has incomplete bounds.")
            slices.append(
                ResultEntry(
                    kind="SLCT",
                    mesh_id=mesh_id,
                    filename=_required_line(lines, index + 1, "SLCT filename").strip(),
                    quantity=_required_line(lines, index + 2, "SLCT quantity").strip(),
                    short_name=_required_line(lines, index + 3, "SLCT short name").strip(),
                    unit=_line_or_empty(lines, index + 4).strip(),
                    bounds=bounds,
                    agl=agl,
                )
            )
            index += 5
            continue

        if keyword in ("BNDF", "BNDC"):
            fields = stripped.split()
            try:
                mesh_id = int(fields[1])
            except (IndexError, ValueError) as error:
                raise FdsResultError("Invalid {} declaration.".format(keyword)) from error
            boundaries.append(
                ResultEntry(
                    kind=keyword,
                    mesh_id=mesh_id,
                    filename=_required_line(
                        lines, index + 1, "{} filename".format(keyword)
                    ).strip(),
                    quantity=_required_line(
                        lines, index + 2, "{} quantity".format(keyword)
                    ).strip(),
                    short_name=_required_line(
                        lines, index + 3, "{} short name".format(keyword)
                    ).strip(),
                    unit=_line_or_empty(lines, index + 4).strip(),
                )
            )
            index += 5
            continue

        if keyword == "BNDE":
            fields = stripped.split()
            try:
                mesh_id = int(fields[1])
            except (IndexError, ValueError) as error:
                raise FdsResultError("Invalid BNDE declaration.") from error
            topology = _required_line(lines, index + 2, "BNDE topology filename").strip()
            if topology == "-":
                topology = geometry_files.get(mesh_id, "")
            boundaries.append(
                ResultEntry(
                    kind="BNDE",
                    mesh_id=mesh_id,
                    filename=_required_line(lines, index + 1, "BNDE filename").strip(),
                    topology_filename=topology,
                    quantity=_required_line(lines, index + 3, "BNDE quantity").strip(),
                    short_name=_required_line(lines, index + 4, "BNDE short name").strip(),
                    unit=_line_or_empty(lines, index + 5).strip(),
                )
            )
            index += 6
            continue

        index += 1

    for mesh_id, dims in dimensions.items():
        axes = coordinates.get(mesh_id, {})
        if set(axes) != {"x", "y", "z"}:
            raise FdsResultError("GRID {} has incomplete coordinates.".format(mesh_id))
        if tuple(len(axes[axis]) - 1 for axis in "xyz") != dims:
            raise FdsResultError(
                "GRID {} coordinates do not match its dimensions.".format(mesh_id)
            )
        meshes[mesh_id] = MeshGrid(mesh_id, axes["x"], axes["y"], axes["z"])

    if not meshes:
        raise FdsResultError("The Smokeview manifest contains no mesh grids.")
    # Current FDS writes ``-`` on BNDE's topology line and lists one CGEOM/GCF
    # file per mesh later in the manifest.  Resolve that forward reference only
    # after the complete file has been scanned.
    boundaries = [
        replace(
            entry,
            topology_filename=geometry_files.get(entry.mesh_id, ""),
        )
        if entry.kind == "BNDE" and not entry.topology_filename
        else entry
        for entry in boundaries
    ]
    return SmokeviewManifest(meshes, tuple(slices), tuple(boundaries))


def read_slice(filepath):
    """Read every complete time frame from an FDS ``.sf`` file."""
    with _FortranReader(filepath) as reader:
        quantity = _text_record(reader, "slice quantity")
        short_name = _text_record(reader, "slice short name")
        unit = _text_record(reader, "slice unit")
        bounds = tuple(_array_record(reader, "<i4", "slice bounds").tolist())
        if len(bounds) != 6:
            raise FdsResultError("Slice bounds record must contain six integers.")
        shape = _bounds_shape(bounds)
        count = int(np.prod(shape))
        times = []
        frames = []
        incomplete = False
        while True:
            try:
                time_record = reader.read(optional=True)
                if time_record is None:
                    break
                time_values = np.frombuffer(time_record, dtype=reader.dtype("f4"))
                if time_values.size != 1:
                    raise FdsResultError("Slice time record must contain one value.")
                payload = reader.read()
            except _IncompleteRecordError:
                incomplete = True
                break
            values = np.frombuffer(payload, dtype=reader.dtype("f4"))
            if values.size != count:
                raise FdsResultError(
                    "Slice frame contains {} values; expected {}.".format(values.size, count)
                )
            times.append(float(time_values[0]))
            frames.append(values.astype(np.float32, copy=True))
    return SliceSeries(
        quantity,
        short_name,
        unit,
        bounds,
        np.asarray(times, dtype=np.float64),
        np.asarray(frames, dtype=np.float32).reshape((-1, count)),
        incomplete,
    )


def read_boundary(filepath):
    """Read every complete time frame from a structured FDS ``.bf`` file."""
    with _FortranReader(filepath) as reader:
        quantity = _text_record(reader, "boundary quantity")
        short_name = _text_record(reader, "boundary short name")
        unit = _text_record(reader, "boundary unit")
        patch_count_values = _array_record(reader, "<i4", "boundary patch count")
        if patch_count_values.size != 1:
            raise FdsResultError("Boundary patch count record is invalid.")
        patches = []
        for _ in range(int(patch_count_values[0])):
            fields = _array_record(reader, "<i4", "boundary patch metadata")
            if fields.size < 8:
                raise FdsResultError("Boundary patch metadata is incomplete.")
            patches.append(
                BoundaryPatch(
                    tuple(int(value) for value in fields[:6]),
                    int(fields[6]),
                    int(fields[7]),
                )
            )

        times = []
        frames = []
        incomplete = False
        while True:
            try:
                time_record = reader.read(optional=True)
                if time_record is None:
                    break
                time_values = np.frombuffer(time_record, dtype=reader.dtype("f4"))
                if time_values.size != 1:
                    raise FdsResultError("Boundary time record must contain one value.")
                patch_values = []
                for patch in patches:
                    payload = reader.read()
                    values = np.frombuffer(payload, dtype=reader.dtype("f4"))
                    expected = int(np.prod(_bounds_shape(patch.bounds)))
                    if values.size != expected:
                        raise FdsResultError(
                            "Boundary patch contains {} values; expected {}.".format(
                                values.size, expected
                            )
                        )
                    patch_values.append(values.astype(np.float32, copy=True))
            except _IncompleteRecordError:
                incomplete = True
                break
            times.append(float(time_values[0]))
            frames.append(tuple(patch_values))
    return BoundarySeries(
        quantity,
        short_name,
        unit,
        tuple(patches),
        np.asarray(times, dtype=np.float64),
        tuple(frames),
        incomplete,
    )


def read_geometry_topology(filepath):
    """Read the unstructured cut-face topology from an FDS ``.gcf`` file."""
    with _FortranReader(filepath) as reader:
        # Version, endianness, geometry index metadata, and time are not needed
        # for the static mesh frame but are part of every current GCF header.
        for label in ("GCF version", "GCF revision", "GCF geometry metadata", "GCF time"):
            reader.read(label=label)
        counts = np.frombuffer(reader.read(label="GCF counts"), dtype=reader.dtype("i4"))
        if counts.size < 2:
            raise FdsResultError("GCF counts record is invalid.")
        vertex_count, face_count = (int(counts[0]), int(counts[1]))
        vertices = np.frombuffer(
            reader.read(label="GCF vertices"), dtype=reader.dtype("f4")
        )
        faces = np.frombuffer(reader.read(label="GCF faces"), dtype=reader.dtype("i4"))
        if vertices.size != vertex_count * 3 or faces.size != face_count * 3:
            raise FdsResultError("GCF topology counts do not match its arrays.")
    return GeometryTopology(
        vertices.astype(np.float64).reshape((-1, 3)),
        faces.astype(np.int64).reshape((-1, 3)) - 1,
    )


def read_geometry_boundary(filepath, expected_faces=None):
    """Read complete face-value frames from an FDS ``.be`` file."""
    with _FortranReader(filepath) as reader:
        reader.read(label="BE version")
        reader.read(label="BE revision")
        times = []
        frames = []
        incomplete = False
        while True:
            try:
                time_record = reader.read(optional=True)
                if time_record is None:
                    break
                time_values = np.frombuffer(time_record, dtype=reader.dtype("f4"))
                metadata = np.frombuffer(reader.read(), dtype=reader.dtype("i4"))
                if time_values.size != 1 or metadata.size < 4:
                    raise FdsResultError("BE frame metadata is invalid.")
                face_count = int(metadata[3])
                values = np.frombuffer(reader.read(), dtype=reader.dtype("f4"))
            except _IncompleteRecordError:
                incomplete = True
                break
            if values.size != face_count:
                raise FdsResultError("BE face count does not match its values record.")
            if expected_faces is not None and face_count != expected_faces:
                raise FdsResultError(
                    "BE contains {} faces; its GCF topology contains {}.".format(
                        face_count, expected_faces
                    )
                )
            times.append(float(time_values[0]))
            frames.append(values.astype(np.float32, copy=True))
    count = int(expected_faces or (frames[0].size if frames else 0))
    return GeometryBoundarySeries(
        np.asarray(times, dtype=np.float64),
        np.asarray(frames, dtype=np.float32).reshape((-1, count)),
        incomplete,
    )


def resolve_result_file(directory, filename, label):
    """Resolve one manifest-relative path and require an ordinary file."""
    filepath = os.path.normpath(os.path.join(directory, filename))
    if not os.path.isfile(filepath):
        raise FdsResultError("{} file not found: {}".format(label, filepath))
    return filepath


def _bounds_shape(bounds):
    return tuple(bounds[index + 1] - bounds[index] + 1 for index in (0, 2, 4))


def _required_line(lines, index, label):
    if index >= len(lines):
        raise FdsResultError("Missing {} in Smokeview manifest.".format(label))
    return lines[index]


def _line_or_empty(lines, index):
    return lines[index] if index < len(lines) else ""


def _integers(line):
    try:
        return [int(value) for value in line.split()]
    except ValueError as error:
        raise FdsResultError("Expected integer fields in: {}".format(line)) from error


def _text_record(reader, label):
    return reader.read(label=label).decode("ascii", errors="replace").strip()


def _array_record(reader, dtype, label):
    return np.frombuffer(reader.read(label=label), dtype=reader.dtype(dtype[1:]))


class _FortranReader:
    """Validate and expose records from a little- or big-endian FDS file."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.handle = None
        self.endian = "<"

    def __enter__(self):
        try:
            self.handle = open(self.filepath, "rb")
        except OSError as error:
            raise FdsResultError("Cannot read '{}': {}".format(self.filepath, error))
        marker = self.handle.read(4)
        if len(marker) != 4:
            self.handle.close()
            raise FdsResultError(
                "File is empty or has no Fortran record marker: {}".format(
                    self.filepath
                )
            )
        filesize = os.fstat(self.handle.fileno()).st_size
        candidates = []
        for endian in ("<", ">"):
            size = struct.unpack(endian + "i", marker)[0]
            if 0 <= size <= max(0, filesize - 8):
                self.handle.seek(4 + size)
                trailer = self.handle.read(4)
                if (
                    len(trailer) == 4
                    and struct.unpack(endian + "i", trailer)[0] == size
                ):
                    candidates.append(endian)
        if not candidates:
            self.handle.close()
            raise FdsResultError(
                "Invalid Fortran record marker in {}".format(self.filepath)
            )
        self.endian = candidates[0]
        self.handle.seek(0)
        return self

    def __exit__(self, *_args):
        if self.handle is not None:
            self.handle.close()

    def dtype(self, code):
        return np.dtype(self.endian + code)

    def read(self, optional=False, label="record"):
        marker = self.handle.read(4)
        if marker == b"" and optional:
            return None
        if len(marker) != 4:
            raise _IncompleteRecordError("Incomplete {} marker in {}".format(label, self.filepath))
        size = struct.unpack(self.endian + "i", marker)[0]
        if size < 0:
            raise FdsResultError("Negative {} size in {}".format(label, self.filepath))
        payload = self.handle.read(size)
        trailer = self.handle.read(4)
        if len(payload) != size or len(trailer) != 4:
            raise _IncompleteRecordError("Incomplete {} in {}".format(label, self.filepath))
        if struct.unpack(self.endian + "i", trailer)[0] != size:
            raise FdsResultError("Mismatched {} markers in {}".format(label, self.filepath))
        return payload
