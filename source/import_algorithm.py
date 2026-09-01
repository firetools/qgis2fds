"""QGIS Processing algorithm for importing temporal FDS wildfire results."""

from collections import defaultdict
import os
import re

import numpy as np

from qgis.core import (
    Qgis,
    QgsBearingUtils,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFolder,
    QgsProcessingOutputMultipleLayers,
    QgsProject,
)

from .fds_mesh import (
    TemporalGroup,
    geometry_frame_layout,
    rotate_vectors,
    slice_frame_layout,
    structured_boundary_frame_layout,
    transform_frame,
    write_mesh_layers,
)
from .fds_results import (
    FdsResultError,
    WILDFIRE_BOUNDARY_QUANTITIES,
    read_boundary,
    read_fds_reference,
    read_geometry_boundary,
    read_geometry_topology,
    read_slice,
    read_smokeview_manifest,
    resolve_result_file,
)
from .parameters import SPECS, add_parameters, read_parameters
from .spatial import local_utm_crs
from .export_algorithm import PLUGIN_VERSION


IMPORT_SPECS = SPECS[:2]
IMPORT_STAGE_COUNT = 5


class ImportFdsAlgorithm(QgsProcessingAlgorithm):
    """Import AGL slices and wildfire boundary results as temporal mesh layers."""

    OUTPUT_LAYERS = "mesh_layers"
    OUTPUT_DIRECTORY = "output_directory"

    def flags(self):
        """Run on the main thread because the algorithm changes the layer tree."""
        return (
            super().flags()
            | QgsProcessingAlgorithm.FlagNoThreading
            | QgsProcessingAlgorithm.FlagRequiresProject
        )

    def initAlgorithm(self, config=None):
        add_parameters(self, QgsProject.instance(), IMPORT_SPECS)
        self.addOutput(
            QgsProcessingOutputMultipleLayers(
                self.OUTPUT_LAYERS, "Imported temporal mesh layers"
            )
        )
        self.addOutput(
            QgsProcessingOutputFolder(
                self.OUTPUT_DIRECTORY, "Persistent imported mesh data"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        project = QgsProject.instance()
        stage = "reading parameters"
        _diagnostic(
            feedback,
            "Starting FDS result import with qgis2fds {} on QGIS {}.".format(
                PLUGIN_VERSION, Qgis.QGIS_VERSION
            ),
        )
        try:
            values = read_parameters(
                self,
                parameters,
                context,
                project,
                feedback,
                IMPORT_SPECS,
            )
            chid = values["chid"].strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", chid):
                raise QgsProcessingException(
                    "CHID may contain only letters, digits, underscores, periods, "
                    "and hyphens."
                )
            case_directory = _resolve_path(values["fds_path"], project)
            fds_filepath = os.path.join(case_directory, chid + ".fds")
            smv_filepath = os.path.join(case_directory, chid + ".smv")
            required_files = (
                ("FDS input", fds_filepath),
                ("Smokeview manifest", smv_filepath),
            )
            for label, filepath in required_files:
                if not os.path.isfile(filepath):
                    raise QgsProcessingException("{} file not found: {}".format(label, filepath))
            output_directory = _unique_output_directory(case_directory, chid)
            _diagnostic(
                feedback,
                "Case files: {}; persistent QGIS outputs: {}.".format(
                    case_directory, output_directory
                ),
            )

            stage = "reading case georeferencing"
            _set_progress(feedback, 1)
            _check_canceled(feedback)
            reference = read_fds_reference(fds_filepath)
            manifest = read_smokeview_manifest(smv_filepath)
            utm_crs, origin_easting, origin_northing, rotation = _spatial_reference(
                reference, project
            )
            _diagnostic(
                feedback,
                "Georeferencing: origin {:.3f},{:.3f} in {} ({}); FDS-to-UTM "
                "rotation {:.6f} degrees.".format(
                    origin_easting,
                    origin_northing,
                    utm_crs.description(),
                    utm_crs.authid(),
                    rotation,
                ),
            )
            _diagnostic(
                feedback,
                "Smokeview manifest: {} meshes, {} AGL slice files, {} boundary "
                "files.".format(
                    len(manifest.meshes),
                    len(manifest.slices),
                    len(manifest.boundaries),
                ),
            )

            stage = "importing SLCF AGL results"
            _set_progress(feedback, 2)
            imported = []
            output_files = []
            slice_cache = {}
            heights = sorted({entry.agl for entry in manifest.slices})
            for height in heights:
                _check_canceled(feedback)
                entries = [entry for entry in manifest.slices if entry.agl == height]
                layers, files = _import_agl_height(
                    chid,
                    height,
                    entries,
                    manifest,
                    case_directory,
                    output_directory,
                    utm_crs,
                    origin_easting,
                    origin_northing,
                    rotation,
                    slice_cache,
                    feedback,
                )
                imported.extend(layers)
                output_files.extend(files)

            stage = "importing wildfire BNDF results"
            _set_progress(feedback, 3)
            _check_canceled(feedback)
            boundary_entries = [
                entry
                for entry in manifest.boundaries
                if entry.quantity.upper() in WILDFIRE_BOUNDARY_QUANTITIES
            ]
            if boundary_entries:
                layers, files = _import_boundaries(
                    chid,
                    boundary_entries,
                    manifest,
                    case_directory,
                    output_directory,
                    utm_crs,
                    origin_easting,
                    origin_northing,
                    rotation,
                    feedback,
                )
                imported.extend(layers)
                output_files.extend(files)
            else:
                _diagnostic(feedback, "No supported wildfire BNDF results were found.")

            stage = "finalizing imported layers"
            _set_progress(feedback, 4)
            if not imported:
                raise QgsProcessingException(
                    "No SLCF AGL or supported wildfire BNDF results were found."
                )
            # Delay project mutation until every requested result has been read
            # and persisted, so a late failure does not leave partial layers.
            for layer in imported:
                project.addMapLayer(layer)
            _diagnostic(
                feedback,
                "Added {} temporal mesh layer(s) to the current project. The "
                "project itself was not saved.".format(len(imported)),
            )
            _diagnostic(
                feedback,
                "Wrote {} persistent mesh/dataset files.".format(len(output_files)),
            )
        except QgsProcessingException as error:
            _report_failure(feedback, stage, error)
            raise
        except FdsResultError as error:
            _report_failure(feedback, stage, error)
            raise QgsProcessingException(
                "FDS result import failed while {}: {}".format(stage, error)
            ) from error
        except (OSError, UnicodeError, ValueError) as error:
            _report_failure(feedback, stage, error)
            raise QgsProcessingException(
                "FDS result import failed while {}: {}".format(stage, error)
            ) from error
        except Exception as error:
            _report_failure(feedback, stage, error)
            raise QgsProcessingException(
                "FDS result import failed while {}: {}: {}".format(
                    stage, type(error).__name__, error
                )
            ) from error

        _set_progress(feedback, IMPORT_STAGE_COUNT)
        return {
            self.OUTPUT_LAYERS: [layer.id() for layer in imported],
            self.OUTPUT_DIRECTORY: output_directory,
        }

    def name(self):
        return "Import FDS results"

    def displayName(self):
        return self.name()

    def group(self):
        return self.groupId()

    def groupId(self):
        return ""

    def shortHelpString(self):
        return (
            "Imports all calculated FDS SLCF AGL and wildfire BNDF results as "
            "persistent temporal QGIS mesh layers."
        )

    def createInstance(self):
        return ImportFdsAlgorithm()


def _import_agl_height(
    chid,
    height,
    entries,
    manifest,
    case_directory,
    output_directory,
    crs,
    origin_easting,
    origin_northing,
    rotation,
    cache,
    feedback,
):
    entries_by_quantity = _group_entries(entries)
    representatives = _representative_mesh_entries(entries)
    layout = slice_frame_layout(representatives, manifest.meshes, height)
    layout = transform_frame(
        layout, origin_easting, origin_northing, rotation
    )

    series_by_quantity = {}
    for quantity, quantity_entries in entries_by_quantity.items():
        by_mesh = {}
        for entry in quantity_entries:
            filepath = resolve_result_file(case_directory, entry.filename, "slice")
            series = cache.get(filepath)
            if series is None:
                series = read_slice(filepath)
                cache[filepath] = series
            if series.incomplete_tail:
                feedback.pushWarning(
                    "[qgis2fds] Ignored an incomplete final frame in {}.".format(filepath)
                )
            if series.quantity.upper() != quantity:
                raise QgsProcessingException(
                    "Slice quantity mismatch in {}.".format(filepath)
                )
            by_mesh[entry.mesh_id] = series
        series_by_quantity[quantity] = by_mesh

    groups = []
    consumed = set()
    if "U-VELOCITY" in series_by_quantity and "V-VELOCITY" in series_by_quantity:
        u_times, u_values, u_unit = _merge_slice_quantity(
            layout, series_by_quantity["U-VELOCITY"]
        )
        v_times, v_values, v_unit = _merge_slice_quantity(
            layout, series_by_quantity["V-VELOCITY"]
        )
        _require_same_times(u_times, v_times, "U/V velocity")
        vectors = []
        for u_frame, v_frame in zip(u_values, v_values):
            east, north = rotate_vectors(u_frame, v_frame, rotation)
            vectors.append(np.column_stack((east, north)))
        groups.append(
            TemporalGroup("VELOCITY", u_unit or v_unit, u_times, tuple(vectors), True)
        )
        consumed.update(("U-VELOCITY", "V-VELOCITY"))

    for quantity, by_mesh in series_by_quantity.items():
        if quantity in consumed:
            continue
        times, values, unit = _merge_slice_quantity(layout, by_mesh)
        groups.append(TemporalGroup(quantity, unit, times, tuple(values)))

    label = "{} SLCF AGL={}".format(chid, _format_height(height))
    filepath = os.path.join(
        output_directory,
        "{}_SLCF_AGL_{}.2dm".format(chid, _filename_height(height)),
    )
    layers, datasets = write_mesh_layers(filepath, label, crs, layout, groups)
    _diagnostic(
        feedback,
        "Imported SLCF AGL={}: {} mesh vertices, {} faces, {} separate dataset "
        "layers.".format(
            _format_height(height),
            len(layout.vertices),
            len(layout.faces),
            len(groups),
        ),
    )
    return layers, datasets


def _import_boundaries(
    chid,
    entries,
    manifest,
    case_directory,
    output_directory,
    crs,
    origin_easting,
    origin_northing,
    rotation,
    feedback,
):
    # GEOM boundary output represents the actual cut terrain.  FDS also lists
    # structured exterior boundary files for the same quantities; prefer BNDE
    # to avoid importing duplicate, less representative data.
    geom_entries = [entry for entry in entries if entry.kind == "BNDE"]
    structured_entries = [
        entry for entry in entries if entry.kind in ("BNDF", "BNDC")
    ]
    quantities = {entry.quantity.upper() for entry in entries}
    geom_quantities = {entry.quantity.upper() for entry in geom_entries}
    structured_quantities = {
        entry.quantity.upper() for entry in structured_entries
    }
    if geom_entries and geom_quantities == quantities:
        selected = geom_entries
    elif structured_entries and structured_quantities == quantities:
        selected = structured_entries
    else:
        raise QgsProcessingException(
            "Wildfire BNDF output is incomplete across GEOM and structured "
            "files."
        )
    if any(entry.kind == "BNDC" for entry in selected):
        raise QgsProcessingException(
            "Cell-centered BNDC boundary output is not yet supported. Use BNDF output."
        )
    if selected[0].kind == "BNDE":
        layout, groups = _geometry_boundary_groups(
            selected, case_directory, feedback
        )
        representation = "GEOM"
    else:
        layout, groups = _structured_boundary_groups(
            selected, manifest.meshes, case_directory, feedback
        )
        representation = "structured"
    layout = transform_frame(layout, origin_easting, origin_northing, rotation)
    filepath = os.path.join(output_directory, "{}_BNDF.2dm".format(chid))
    layers, datasets = write_mesh_layers(
        filepath, "{} BNDF".format(chid), crs, layout, groups
    )
    _diagnostic(
        feedback,
        "Imported {} wildfire BNDF results: {} vertices, {} faces, {} separate "
        "dataset layers.".format(
            representation, len(layout.vertices), len(layout.faces), len(groups)
        ),
    )
    return layers, datasets


def _geometry_boundary_groups(entries, case_directory, feedback):
    grouped = _group_entries(entries)
    first_entries = next(iter(grouped.values()))
    topologies = {}
    for entry in first_entries:
        if not entry.topology_filename:
            raise QgsProcessingException(
                "No GCF topology is associated with mesh {}.".format(entry.mesh_id)
            )
        filepath = resolve_result_file(
            case_directory, entry.topology_filename, "geometry topology"
        )
        topologies[entry.mesh_id] = read_geometry_topology(filepath)
    layout = geometry_frame_layout(topologies)
    groups = []
    for quantity, quantity_entries in grouped.items():
        per_mesh = {}
        for entry in quantity_entries:
            topology = topologies.get(entry.mesh_id)
            if topology is None:
                raise QgsProcessingException(
                    "Wildfire BNDF QUANTITY='{}' has an unexpected mesh {}.".format(
                        quantity, entry.mesh_id
                    )
                )
            filepath = resolve_result_file(
                case_directory, entry.filename, "geometry boundary"
            )
            series = read_geometry_boundary(filepath, len(topology.faces))
            if series.incomplete_tail:
                feedback.pushWarning(
                    "[qgis2fds] Ignored an incomplete final frame in {}.".format(filepath)
                )
            per_mesh[entry.mesh_id] = (entry, series)
        _require_mesh_set(per_mesh, topologies, quantity)
        times = _common_times([item[1] for item in per_mesh.values()], quantity)
        frames = []
        for time_index in range(len(times)):
            frames.append(
                np.concatenate(
                    [
                        per_mesh[mesh_id][1].values[time_index]
                        for mesh_id in sorted(topologies)
                    ]
                )
            )
        unit = next(iter(per_mesh.values()))[0].unit
        groups.append(TemporalGroup(quantity, unit, times, tuple(frames)))
    return layout, groups


def _structured_boundary_groups(entries, meshes, case_directory, feedback):
    grouped = _group_entries(entries)
    loaded = {}
    for quantity, quantity_entries in grouped.items():
        per_mesh = {}
        for entry in quantity_entries:
            filepath = resolve_result_file(case_directory, entry.filename, "boundary")
            series = read_boundary(filepath)
            if series.incomplete_tail:
                feedback.pushWarning(
                    "[qgis2fds] Ignored an incomplete final frame in {}.".format(filepath)
                )
            per_mesh[entry.mesh_id] = (entry, series)
        loaded[quantity] = per_mesh
    first = next(iter(loaded.values()))
    layout = structured_boundary_frame_layout(
        {mesh_id: item[1] for mesh_id, item in first.items()}, meshes
    )
    groups = []
    for quantity, per_mesh in loaded.items():
        _require_mesh_set(per_mesh, first, quantity)
        for mesh_id in first:
            if per_mesh[mesh_id][1].patches != first[mesh_id][1].patches:
                raise QgsProcessingException(
                    "Boundary patch topology differs between quantities."
                )
        times = _common_times([item[1] for item in per_mesh.values()], quantity)
        frames = []
        for time_index in range(len(times)):
            values = np.full(len(layout.vertices), np.nan, dtype=np.float64)
            for (mesh_id, patch_index), (start, count) in layout.spans.items():
                patch_values = per_mesh[mesh_id][1].values[time_index][patch_index]
                if len(patch_values) != count:
                    raise QgsProcessingException(
                        "Boundary patch topology differs between quantities."
                    )
                values[start : start + count] = patch_values
            frames.append(values)
        unit = next(iter(per_mesh.values()))[0].unit
        groups.append(TemporalGroup(quantity, unit, times, tuple(frames)))
    return layout, groups


def _merge_slice_quantity(layout, by_mesh):
    times = _common_times(list(by_mesh.values()), "slice quantity")
    frames = []
    for time_index in range(len(times)):
        values = np.full(len(layout.vertices), np.nan, dtype=np.float64)
        for mesh_id, (start, count, bounds) in layout.spans.items():
            series = by_mesh.get(mesh_id)
            if series is None:
                raise QgsProcessingException(
                    "Slice quantity is missing FDS mesh {}.".format(mesh_id)
                )
            if series.bounds != bounds or series.values.shape[1] != count:
                raise QgsProcessingException(
                    "Slice topology differs between quantities on mesh {}.".format(mesh_id)
                )
            values[start : start + count] = series.values[time_index]
        frames.append(values)
    unit = next(iter(by_mesh.values())).unit
    return times, frames, unit


def _group_entries(entries):
    grouped = defaultdict(list)
    for entry in entries:
        grouped[entry.quantity.upper()].append(entry)
    return dict(grouped)


def _representative_mesh_entries(entries):
    representatives = {}
    for entry in entries:
        existing = representatives.setdefault(entry.mesh_id, entry)
        if existing.bounds != entry.bounds:
            raise QgsProcessingException(
                "AGL slice bounds differ between quantities on mesh {}.".format(
                    entry.mesh_id
                )
            )
    return list(representatives.values())


def _common_times(series_values, label):
    if not series_values:
        raise QgsProcessingException("No files are available for {}.".format(label))
    times = series_values[0].times
    if times.size == 0:
        raise QgsProcessingException("No complete frames are available for {}.".format(label))
    for series in series_values[1:]:
        _require_same_times(times, series.times, label)
    return times


def _require_mesh_set(actual, expected, label):
    if set(actual) != set(expected):
        raise QgsProcessingException(
            "Wildfire BNDF QUANTITY='{}' is not available on the same FDS meshes as "
            "the other quantities.".format(label)
        )


def _require_same_times(first, second, label):
    if len(first) != len(second) or not np.allclose(
        first, second, rtol=0.0, atol=1.0e-5
    ):
        raise QgsProcessingException(
            "FDS files for {} do not contain matching time frames.".format(label)
        )


def _spatial_reference(reference, project):
    crs = local_utm_crs(reference.longitude, reference.latitude)
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    origin = QgsCoordinateTransform(wgs84, crs, project).transform(
        QgsPointXY(reference.longitude, reference.latitude)
    )
    try:
        true_north = QgsBearingUtils.bearingTrueNorth(
            crs, project.transformContext(), origin
        )
    except Exception as error:
        raise QgsProcessingException(
            "Cannot calculate true north at the FDS origin: {}".format(error)
        )
    if not np.isfinite(true_north):
        raise QgsProcessingException("Cannot calculate true north at the FDS origin.")
    # NORTH_BEARING and QgsBearingUtils are both clockwise bearings to true
    # north.  Their difference is the rotation from FDS x/y into UTM east/north.
    rotation = reference.north_bearing - true_north
    return crs, origin.x(), origin.y(), rotation


def _resolve_path(path, project):
    normalized = os.path.normpath(str(path).replace("\\", os.sep))
    if os.path.isabs(normalized):
        return normalized
    base = project.absolutePath()
    if not base:
        raise QgsProcessingException(
            "Relative paths require the QGIS project to be saved to disk."
        )
    return os.path.normpath(os.path.join(base, normalized))


def _unique_output_directory(case_directory, chid):
    base = os.path.join(case_directory, "{}_qgis_results".format(chid))
    candidate = base
    suffix = 2
    while os.path.exists(candidate):
        candidate = "{}_{}".format(base, suffix)
        suffix += 1
    os.makedirs(candidate)
    return candidate


def _format_height(value):
    return "{:.12g}".format(value)


def _filename_height(value):
    return _format_height(value).replace("-", "m").replace(".", "p")


def _check_canceled(feedback):
    if feedback.isCanceled():
        raise QgsProcessingException("FDS result import canceled.")


def _set_progress(feedback, completed):
    feedback.setProgress(100.0 * completed / IMPORT_STAGE_COUNT)


def _diagnostic(feedback, message):
    feedback.pushInfo("[qgis2fds] " + message)


def _report_failure(feedback, stage, error):
    feedback.pushWarning(
        "[qgis2fds] FDS result import failed while {}: {}: {}".format(
            stage, type(error).__name__, error
        )
    )
