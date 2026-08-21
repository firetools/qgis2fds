"""The single qgis2fds processing algorithm."""

import os

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingMultiStepFeedback,
    QgsProcessingOutputFile,
    QgsProject,
)

from .bingeom import write_binary_geometry
from .fds import (
    CHID,
    SurfaceCatalog,
    build_mesh_layout,
    read_wind,
    render_case,
    write_text,
)
from .parameters import add_parameters, read_parameters
from .spatial import apply_fire_layer, prepare_grid, render_texture, sample_terrain


PLUGIN_VERSION = "2.0.0"


class ExportFdsAlgorithm(QgsProcessingAlgorithm):
    """Export DEM, landuse, and ignition data as an FDS wildfire case."""

    OUTPUT_FDS = "fds_file"

    def initAlgorithm(self, config=None):
        add_parameters(self, QgsProject.instance())
        self.addOutput(QgsProcessingOutputFile(self.OUTPUT_FDS, "FDS input file"))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Keep the work split into coarse steps so QGIS can scale child-algorithm
        # progress (notably GDAL warping) into one progress bar.
        feedback = QgsProcessingMultiStepFeedback(6, model_feedback)
        project = QgsProject.instance()
        # Reading also persists the values under the historical project keys.
        # Existing .qgs/.qgz cases therefore keep supplying their saved defaults.
        values = read_parameters(self, parameters, context, project, feedback)

        chid = values["chid"].strip()
        if not CHID.fullmatch(chid):
            raise QgsProcessingException(
                "CHID may contain only letters, digits, underscores, periods, and hyphens."
            )
        if values["t_end"] < values["t_begin"]:
            raise QgsProcessingException("t_end must be greater than or equal to t_begin.")
        if values["landuse_layer"] is not None and not values["landuse_type_filepath"]:
            raise QgsProcessingException(
                "landuse_type_filepath is required when landuse_layer is set."
            )

        output_directory = _resolve_path(values["fds_path"], project)
        os.makedirs(output_directory, exist_ok=True)
        fds_filepath = os.path.join(output_directory, chid + ".fds")
        # Auxiliary files are referenced by basename in the FDS input, making the
        # whole case directory portable after it has been generated.
        binary_filename = chid + "_terrain.bingeom"
        binary_filepath = os.path.join(output_directory, binary_filename)
        texture_filename = chid + "_tex.png"
        texture_filepath = os.path.join(output_directory, texture_filename)

        try:
            landuse_filepath = _resolve_optional_file(
                values["landuse_type_filepath"], project
            )
            wind_filepath = _resolve_optional_file(values["wind_filepath"], project)
            text_filepath = _resolve_optional_file(values["text_filepath"], project)
            catalog = SurfaceCatalog.load(landuse_filepath)
            wind = read_wind(wind_filepath)
            extra_text = _read_extra_text(text_filepath)

            feedback.setCurrentStep(1)
            _check_canceled(feedback)
            grid, utm_crs = prepare_grid(
                values["extent_layer"],
                values["origin"],
                project.crs(),
                values["pixel_size"],
            )
            feedback.pushInfo(
                "Terrain grid: {} x {} cells in {}".format(
                    grid.columns, grid.rows, grid.crs_authid
                )
            )

            feedback.setCurrentStep(2)
            _check_canceled(feedback)
            terrain = sample_terrain(
                values["dem_layer"],
                values["landuse_layer"],
                grid,
                utm_crs,
                context,
                feedback,
            )

            feedback.setCurrentStep(3)
            _check_canceled(feedback)
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

            feedback.setCurrentStep(4)
            _check_canceled(feedback)
            cell_size = values["cell_size"] or values["pixel_size"]
            layout = build_mesh_layout(terrain, cell_size, values["nmesh"])
            feedback.pushInfo(
                "FDS domain: {} meshes ({} x {})".format(
                    layout.count, layout.count_x, layout.count_y
                )
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
            else:
                texture_filename_for_fds = texture_filename

            feedback.setCurrentStep(5)
            _check_canceled(feedback)
            if not values["export_obst"]:
                write_binary_geometry(binary_filepath, terrain, catalog)

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
                provenance="{} on QGIS {}".format(
                    PLUGIN_VERSION, Qgis.QGIS_VERSION
                ),
                dem_name=values["dem_layer"].name(),
                landuse_name=(
                    values["landuse_layer"].name()
                    if values["landuse_layer"] is not None
                    else ""
                ),
                fire_name=(
                    values["fire_layer"].name()
                    if values["fire_layer"] is not None
                    else ""
                ),
            )
            write_text(fds_filepath, case)
        except QgsProcessingException:
            # Preserve actionable QGIS errors raised by spatial operations.
            raise
        except (OSError, UnicodeError, ValueError) as error:
            # Present parser and filesystem failures consistently in Processing.
            raise QgsProcessingException(str(error))

        feedback.setCurrentStep(6)
        feedback.pushInfo("FDS case written to <{}>".format(fds_filepath))
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
