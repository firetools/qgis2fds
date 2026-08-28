"""The single qgis2fds processing algorithm."""

import os
import time

import numpy as np

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProject,
)

from .bingeom import write_binary_geometry
from .fds import (
    CHID,
    SurfaceCatalog,
    build_assumptions,
    build_mesh_layout,
    read_wind,
    render_case,
    write_text,
)
from .parameters import add_parameters, read_parameters
from .spatial import (
    apply_fire_layer,
    prepare_grid,
    render_texture,
    sample_terrain,
)


PLUGIN_VERSION = "2.0.0"
EXPORT_STAGE_COUNT = 6


class ExportFdsAlgorithm(QgsProcessingAlgorithm):
    """Export DEM, landuse, and ignition data as an FDS wildfire case."""

    OUTPUT_FDS = "fds_file"

    def flags(self):
        """Run on QGIS's main thread because the export updates the project."""
        return (
            super().flags()
            | QgsProcessingAlgorithm.FlagNoThreading
            | QgsProcessingAlgorithm.FlagRequiresProject
        )

    def initAlgorithm(self, config=None):
        add_parameters(self, QgsProject.instance())
        self.addOutput(QgsProcessingOutputFile(self.OUTPUT_FDS, "FDS input file"))

    def processAlgorithm(self, parameters, context, model_feedback):
        """Run the export with enough context to diagnose failures from logs."""
        # Keep using the caller-owned feedback throughout the run. A Python-owned
        # QgsProcessingMultiStepFeedback can receive queued progress events after
        # its wrapped qgis_process feedback has been destroyed, causing SIGSEGV.
        feedback = model_feedback
        project = QgsProject.instance()
        stage = "initialization"
        _diagnostic(
            feedback,
            "Starting export with qgis2fds {} on QGIS {}.".format(
                PLUGIN_VERSION, Qgis.QGIS_VERSION
            ),
        )
        _diagnostic(
            feedback,
            "Project: {}; project CRS: {}.".format(
                project.fileName() or "unsaved",
                project.crs().authid() or "unset",
            ),
        )
        try:
            stage = "reading and validating parameters"
            # Reading also persists values under the current project keys so saved
            # projects keep supplying their configured defaults.
            values = read_parameters(self, parameters, context, project, feedback)
            chid = values["chid"].strip()
            if not CHID.fullmatch(chid):
                raise QgsProcessingException(
                    "CHID may contain only letters, digits, underscores, periods, "
                    "and hyphens."
                )
            if values["t_end"] < values["t_begin"]:
                raise QgsProcessingException(
                    "t_end must be greater than or equal to t_begin."
                )
            if (
                values["landuse_layer"] is not None
                and not values["landuse_type_filepath"]
            ):
                raise QgsProcessingException(
                    "landuse_type_filepath is required when landuse_layer is set."
                )
            if (
                values["fire_layer"] is not None
                and not values["landuse_type_filepath"]
            ):
                raise QgsProcessingException(
                    "landuse_type_filepath is required when fire_layer is set."
                )

            stage = "preparing the output directory"
            output_directory = _resolve_path(values["fds_path"], project)
            os.makedirs(output_directory, exist_ok=True)
            fds_filepath = os.path.join(output_directory, chid + ".fds")
            # Auxiliary files use basenames in the FDS input, keeping the generated
            # case portable as one directory.
            binary_filename = chid + "_terrain.bingeom"
            binary_filepath = os.path.join(output_directory, binary_filename)
            texture_filename = chid + "_tex.png"
            texture_filepath = os.path.join(output_directory, texture_filename)
            _diagnostic(
                feedback,
                "Parameters validated for CHID '{}'; output directory: {}; terrain "
                "representation: {}.".format(
                    chid,
                    output_directory,
                    "OBST" if values["export_obst"] else "GEOM",
                ),
            )

            _set_stage_progress(feedback, 0)
            _check_canceled(feedback)
            stage = "loading support files"
            _diagnostic(feedback, "Stage 1/6: loading surface, wind, and text files.")
            landuse_filepath = _resolve_optional_file(
                values["landuse_type_filepath"], project
            )
            wind_filepath = _resolve_optional_file(values["wind_filepath"], project)
            text_filepath = _resolve_optional_file(values["text_filepath"], project)
            catalog = SurfaceCatalog.load(landuse_filepath)
            if values["fire_layer"] is not None:
                catalog.require_fire_surfaces()
            wind = read_wind(wind_filepath)
            extra_text = _read_extra_text(text_filepath)
            _diagnostic(
                feedback,
                "Support files loaded: {} surfaces; {} wind samples; {} bytes of "
                "appended FDS text.".format(
                    len(catalog.surfaces),
                    len(wind),
                    len(extra_text.encode("utf-8")),
                ),
            )

            _set_stage_progress(feedback, 1)
            _check_canceled(feedback)
            stage = "preparing the terrain grid"
            _diagnostic(feedback, "Stage 2/6: preparing the metric terrain grid.")
            grid, utm_crs = prepare_grid(
                values["extent_layer"],
                values["origin"],
                project.crs(),
                values["pixel_size"],
            )
            _diagnostic(
                feedback,
                "Grid ready: {} x {} cells at {:.6g} m in {} ({}); bounds "
                "X={:.3f}:{:.3f}, Y={:.3f}:{:.3f}; origin={:.3f},{:.3f}; "
                "NORTH_BEARING={:.6f}.".format(
                    grid.columns,
                    grid.rows,
                    grid.pixel_size,
                    grid.crs_description,
                    grid.crs_authid,
                    grid.x_min,
                    grid.x_max,
                    grid.y_min,
                    grid.y_max,
                    grid.origin_x,
                    grid.origin_y,
                    grid.north_bearing,
                ),
            )

            _set_stage_progress(feedback, 2)
            _check_canceled(feedback)
            stage = "sampling terrain rasters"
            _diagnostic(
                feedback,
                "Stage 3/6: sampling DEM {} and landuse {}.".format(
                    _raster_description(values["dem_layer"]),
                    _raster_description(values["landuse_layer"]),
                ),
            )
            terrain = sample_terrain(
                values["dem_layer"],
                values["landuse_layer"],
                grid,
                utm_crs,
                context,
                feedback,
            )
            observed_codes = np.unique(terrain.landuse)
            _diagnostic(
                feedback,
                "Raster sampling complete: elevations {:.3f}:{:.3f} m; {} landuse "
                "classes {}.".format(
                    terrain.min_elevation,
                    terrain.max_elevation,
                    observed_codes.size,
                    _code_preview(observed_codes),
                ),
            )

            _set_stage_progress(feedback, 3)
            _check_canceled(feedback)
            stage = "applying fire polygons"
            if values["fire_layer"] is None:
                _diagnostic(
                    feedback,
                    "Stage 4/6: no fire layer supplied; skipping ignition polygons.",
                )
            else:
                _diagnostic(
                    feedback,
                    "Stage 4/6: applying {} features from fire layer '{}' with "
                    "perimeter/interior defaults {}/{}.".format(
                        values["fire_layer"].featureCount(),
                        values["fire_layer"].name(),
                        catalog.outside_fire_code,
                        catalog.inside_fire_code,
                    ),
                )
            apply_fire_layer(
                terrain,
                values["fire_layer"],
                utm_crs,
                catalog.outside_fire_code,
                catalog.inside_fire_code,
                feedback,
            )
            unknown = catalog.unknown_codes(terrain)
            if unknown:
                feedback.pushWarning(
                    "Unknown landuse codes use the fallback surface: {}".format(
                        ", ".join(str(code) for code in unknown)
                    )
                )
            _diagnostic(
                feedback,
                "Fire processing complete; {} unknown landuse codes use the fallback "
                "surface.".format(len(unknown)),
            )

            _set_stage_progress(feedback, 4)
            _check_canceled(feedback)
            stage = "building the FDS domain"
            _diagnostic(feedback, "Stage 5/6: building meshes, assumptions, and texture.")
            cell_size = values["cell_size"] or values["pixel_size"]
            layout = build_mesh_layout(terrain, cell_size, values["nmesh"])
            _diagnostic(
                feedback,
                "Mesh layout ready: {} meshes ({} x {}), {} x {} x {} cells each; "
                "domain XB={:.3f}:{:.3f}, {:.3f}:{:.3f}, {:.3f}:{:.3f}.".format(
                    layout.count,
                    layout.count_x,
                    layout.count_y,
                    layout.cells_x,
                    layout.cells_y,
                    layout.cells_z,
                    layout.x_min,
                    layout.x_max,
                    layout.y_min,
                    layout.y_max,
                    layout.z_min,
                    layout.z_max,
                ),
            )
            provenance = "{} on QGIS {}".format(
                PLUGIN_VERSION, Qgis.QGIS_VERSION
            )
            dem_name = values["dem_layer"].name()
            landuse_name = (
                values["landuse_layer"].name()
                if values["landuse_layer"] is not None
                else ""
            )
            fire_name = (
                values["fire_layer"].name()
                if values["fire_layer"] is not None
                else ""
            )
            assumptions = build_assumptions(
                terrain=terrain,
                catalog=catalog,
                layout=layout,
                wind_filepath=wind_filepath,
                provenance=provenance,
                qgis_filepath=project.fileName() or "not saved",
                generated_at=time.strftime(
                    "%a, %d %b %Y, %H:%M:%S", time.localtime()
                ),
                dem_name=dem_name,
                landuse_name=landuse_name,
                fire_name=fire_name,
            )
            _diagnostic(
                feedback,
                "Prepared {} assumptions.".format(len(assumptions)),
            )
            _report_assumptions(feedback, assumptions)

            stage = "rendering the terrain texture"
            _diagnostic(
                feedback,
                "Rendering terrain texture at {:.6g} m per pixel.".format(
                    values["tex_pixel_size"]
                ),
            )
            rendered_texture = render_texture(
                grid,
                utm_crs,
                texture_filepath,
                values["tex_pixel_size"],
                feedback,
            )
            if rendered_texture is None:
                texture_filename_for_fds = ""
                _diagnostic(
                    feedback,
                    "Terrain texture was not generated; continuing without it.",
                )
            else:
                texture_filename_for_fds = texture_filename
                _diagnostic(
                    feedback,
                    "Terrain texture written: {} ({}).".format(
                        rendered_texture, _file_size(rendered_texture)
                    ),
                )

            _set_stage_progress(feedback, 5)
            _check_canceled(feedback)
            stage = "writing generated files"
            _diagnostic(feedback, "Stage 6/6: serializing the FDS case.")
            if not values["export_obst"]:
                stage = "writing BINGEOM terrain"
                _diagnostic(
                    feedback,
                    "Writing BINGEOM terrain: {}.".format(binary_filepath),
                )
                write_binary_geometry(binary_filepath, terrain, catalog)
                _diagnostic(
                    feedback,
                    "BINGEOM terrain written successfully ({}).".format(
                        _file_size(binary_filepath)
                    ),
                )
            else:
                _diagnostic(feedback, "Writing terrain directly as OBST namelists.")

            stage = "rendering the FDS input"
            case = render_case(
                chid=chid,
                t_begin=values["t_begin"],
                t_end=values["t_end"],
                terrain=terrain,
                catalog=catalog,
                layout=layout,
                wind=wind,
                export_obst=values["export_obst"],
                binary_filename=binary_filename,
                texture_filename=texture_filename_for_fds,
                extra_text=extra_text,
                assumptions=assumptions,
            )
            _diagnostic(
                feedback,
                "Rendered FDS input in memory: {} lines, {} bytes.".format(
                    len(case.splitlines()), len(case.encode("utf-8"))
                ),
            )
            stage = "writing the FDS input"
            write_text(fds_filepath, case)
            _diagnostic(
                feedback,
                "FDS input written successfully: {} ({}).".format(
                    fds_filepath, _file_size(fds_filepath)
                ),
            )
        except QgsProcessingException as error:
            _report_failure(feedback, stage, error)
            raise
        except (OSError, UnicodeError, ValueError) as error:
            _report_failure(feedback, stage, error)
            raise QgsProcessingException(
                "Export failed while {}: {}".format(stage, error)
            ) from error
        except Exception as error:
            # Include the stage and exception type for unexpected plugin or provider
            # failures while retaining the original exception as the cause.
            _report_failure(feedback, stage, error)
            raise QgsProcessingException(
                "Export failed while {}: {}: {}".format(
                    stage, type(error).__name__, error
                )
            ) from error

        _set_stage_progress(feedback, EXPORT_STAGE_COUNT)
        _diagnostic(
            feedback,
            "Export completed, FDS case: <{}>.".format(fds_filepath),
        )
        return {self.OUTPUT_FDS: fds_filepath}

    def name(self):
        # Kept verbatim for existing `qgis_process run` invocations.
        return "Export FDS case"

    def displayName(self):
        return self.name()

    def group(self):
        return self.groupId()

    def groupId(self):
        return ""

    def shortHelpString(self):
        return (
            "Exports a georeferenced DEM, optional landuse, ignition polygons, "
            "and wind schedule as an FDS wildfire case."
        )

    def createInstance(self):
        return ExportFdsAlgorithm()


def _resolve_path(path, project):
    # QGIS projects commonly store portable relative paths with either slash style.
    normalized = os.path.normpath(str(path).replace("\\", os.sep))
    if os.path.isabs(normalized):
        return normalized
    base = project.absolutePath()
    if not base:
        raise QgsProcessingException(
            "Relative paths require the QGIS project to be saved to disk."
        )
    return os.path.normpath(os.path.join(base, normalized))


def _resolve_optional_file(path, project):
    if not path:
        return ""
    resolved = _resolve_path(path, project)
    if not os.path.isfile(resolved):
        raise QgsProcessingException("File not found: {}".format(resolved))
    return resolved


def _read_extra_text(filepath):
    if not filepath:
        return ""
    with open(filepath, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _check_canceled(feedback):
    if feedback.isCanceled():
        raise QgsProcessingException("Export canceled.")


def _set_stage_progress(feedback, completed_stages):
    """Report coarse export progress without introducing a feedback wrapper."""
    feedback.setProgress(100.0 * completed_stages / EXPORT_STAGE_COUNT)


def _diagnostic(feedback, message):
    """Emit a searchable runtime message in GUI and qgis_process logs."""
    feedback.pushInfo("[qgis2fds] " + message)


def _report_failure(feedback, stage, error):
    """Record the failed stage before QGIS presents the exception to the user."""
    feedback.pushWarning(
        "[qgis2fds] Export failed while {}: {}: {}".format(
            stage, type(error).__name__, error
        )
    )


def _raster_description(layer):
    """Describe a raster without exposing its possibly credentialed source URI."""
    if layer is None:
        return "none"
    return "'{}' (provider={}, CRS={}, source={}x{})".format(
        layer.name(),
        layer.providerType() or "unknown",
        layer.crs().authid() or "unset",
        layer.width(),
        layer.height(),
    )


def _code_preview(codes, limit=12):
    """Show a bounded landuse-code preview suitable for Processing logs."""
    values = [str(int(code)) for code in codes[:limit]]
    if len(codes) > limit:
        values.append("...")
    return "[{}]".format(", ".join(values))


def _file_size(filepath):
    """Format a generated file size without introducing another dependency."""
    size = os.path.getsize(filepath)
    if size < 1024:
        return "{} B".format(size)
    if size < 1024 * 1024:
        return "{:.1f} KiB".format(size / 1024.0)
    return "{:.1f} MiB".format(size / (1024.0 * 1024.0))


def _report_assumptions(feedback, assumptions):
    """Show exactly the assumptions written as comments in the FDS file."""
    feedback.pushInfo("Assumptions:")
    for assumption in assumptions:
        feedback.pushInfo("  " + assumption)
