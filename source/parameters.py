"""Declarative definition and loading of the public processing parameters."""

from dataclasses import dataclass

from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)


PROJECT_GROUP = "qgis2fds"


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    kind: str
    default: object = None
    optional: bool = False
    advanced: bool = False
    minimum: float = None
    file_filter: str = "All files (*.*)"


# Names, defaults, and order are part of the compatibility contract with saved
# QGIS projects, Processing models, and existing qgis_process command lines.
SPECS = (
    ParameterSpec("chid", "FDS case identifier (CHID)", "string", "terrain"),
    ParameterSpec("fds_path", "FDS case folder", "folder", "./FDS"),
    ParameterSpec("extent_layer", "Domain extent layer", "vector"),
    ParameterSpec("pixel_size", "Terrain resolution (m)", "float", 10.0, minimum=0.01),
    ParameterSpec(
        "origin",
        "FDS domain origin (defaults to extent centroid)",
        "point",
        optional=True,
        advanced=True,
    ),
    ParameterSpec("dem_layer", "DEM layer", "raster"),
    ParameterSpec(
        "landuse_layer",
        "Landuse layer",
        "raster",
        optional=True,
    ),
    ParameterSpec(
        "landuse_type_filepath",
        "Landuse type file (*.csv)",
        "file",
        "",
        optional=True,
        file_filter="CSV files (*.csv)",
    ),
    ParameterSpec("fire_layer", "Fire layer", "vector", optional=True),
    ParameterSpec(
        "tex_pixel_size",
        "Texture resolution (m)",
        "float",
        10.0,
        advanced=True,
        minimum=0.01,
    ),
    ParameterSpec(
        "nmesh",
        "Maximum number of FDS meshes",
        "integer",
        1,
        advanced=True,
        minimum=1,
    ),
    ParameterSpec(
        "cell_size",
        "FDS mesh cell size (m)",
        "float",
        10.0,
        optional=True,
        advanced=True,
        minimum=0.01,
    ),
    ParameterSpec("t_begin", "FDS TIME T_BEGIN (s)", "float", 0.0, advanced=True),
    ParameterSpec("t_end", "FDS TIME T_END (s)", "float", 0.0, advanced=True),
    ParameterSpec(
        "wind_filepath",
        "Wind file (*.csv)",
        "file",
        "",
        optional=True,
        file_filter="CSV files (*.csv)",
    ),
    ParameterSpec(
        "text_filepath",
        "Free text appended to the FDS case",
        "file",
        "",
        optional=True,
        file_filter="Text files (*.txt *.fds);;All files (*.*)",
    ),
    ParameterSpec(
        "export_obst",
        "Export terrain as FDS OBST namelists",
        "boolean",
        False,
        advanced=True,
    ),
)


def add_parameters(algorithm, project):
    """Add all public inputs, using values stored in the QGIS project."""
    for spec in SPECS:
        default = _stored_default(project, spec)
        if spec.kind == "string":
            parameter = QgsProcessingParameterString(
                spec.name, spec.label, defaultValue=default, optional=spec.optional
            )
        elif spec.kind == "point":
            parameter = QgsProcessingParameterPoint(
                spec.name, spec.label, defaultValue=default, optional=spec.optional
            )
        elif spec.kind in ("float", "integer"):
            number_type = (
                QgsProcessingParameterNumber.Integer
                if spec.kind == "integer"
                else QgsProcessingParameterNumber.Double
            )
            number_options = {}
            if spec.minimum is not None:
                number_options["minValue"] = spec.minimum
            parameter = QgsProcessingParameterNumber(
                spec.name,
                spec.label,
                type=number_type,
                defaultValue=default,
                optional=spec.optional,
                **number_options,
            )
        elif spec.kind in ("file", "folder"):
            behavior = (
                QgsProcessingParameterFile.Folder
                if spec.kind == "folder"
                else QgsProcessingParameterFile.File
            )
            parameter = QgsProcessingParameterFile(
                spec.name,
                spec.label,
                behavior=behavior,
                extension="",
                defaultValue=default,
                optional=spec.optional,
                fileFilter=spec.file_filter,
            )
        elif spec.kind == "raster":
            parameter = QgsProcessingParameterRasterLayer(
                spec.name, spec.label, defaultValue=default, optional=spec.optional
            )
        elif spec.kind == "vector":
            parameter = QgsProcessingParameterVectorLayer(
                spec.name, spec.label, defaultValue=default, optional=spec.optional
            )
        elif spec.kind == "boolean":
            parameter = QgsProcessingParameterBoolean(
                spec.name, spec.label, defaultValue=default, optional=spec.optional
            )
        else:  # pragma: no cover - guarded by the static table above
            raise ValueError("Unsupported parameter kind: {}".format(spec.kind))

        if spec.advanced:
            parameter.setFlags(
                parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algorithm.addParameter(parameter)


def read_parameters(algorithm, parameters, context, project, feedback):
    """Read typed values and persist them under the qgis2fds project keys."""
    values = {}
    for spec in SPECS:
        # Keep both forms: QGIS supplies the typed value to the exporter, while
        # the raw value may preserve a relative path or a CRS-qualified point.
        raw = parameters.get(spec.name)
        if spec.kind == "string":
            value = algorithm.parameterAsString(parameters, spec.name, context)
        elif spec.kind == "point":
            value = None
            if raw not in (None, ""):
                value = algorithm.parameterAsPoint(
                    parameters, spec.name, context, project.crs()
                )
        elif spec.kind == "integer":
            value = algorithm.parameterAsInt(parameters, spec.name, context)
        elif spec.kind == "float":
            value = algorithm.parameterAsDouble(parameters, spec.name, context)
        elif spec.kind in ("file", "folder"):
            value = ""
            if raw not in (None, ""):
                value = algorithm.parameterAsFile(parameters, spec.name, context)
        elif spec.kind == "raster":
            value = None
            if raw not in (None, ""):
                value = algorithm.parameterAsRasterLayer(parameters, spec.name, context)
        elif spec.kind == "vector":
            value = None
            if raw not in (None, ""):
                value = algorithm.parameterAsVectorLayer(parameters, spec.name, context)
        elif spec.kind == "boolean":
            value = algorithm.parameterAsBool(parameters, spec.name, context)

        if not spec.optional and value in (None, ""):
            raise QgsProcessingException("{} is required.".format(spec.label))
        values[spec.name] = value
        _store_value(project, spec, raw, value)
        feedback.pushInfo("{}: {}".format(spec.name, _describe(value)))
    return values


def _stored_default(project, spec):
    # QGIS custom properties have separate typed readers; numeric properties use
    # the double reader even when the Processing parameter itself is integral.
    if spec.kind in ("float", "integer"):
        value, found = project.readDoubleEntry(PROJECT_GROUP, spec.name, spec.default)
        return int(value) if found and spec.kind == "integer" else value
    if spec.kind == "boolean":
        value, _ = project.readBoolEntry(PROJECT_GROUP, spec.name, spec.default)
        return value
    value, _ = project.readEntry(PROJECT_GROUP, spec.name, spec.default)
    return value


def _store_value(project, spec, raw, value):
    if spec.kind in ("float", "integer"):
        project.writeEntryDouble(PROJECT_GROUP, spec.name, float(value))
    elif spec.kind == "boolean":
        project.writeEntryBool(PROJECT_GROUP, spec.name, bool(value))
    elif spec.kind in ("raster", "vector"):
        # Layer IDs are stable within a saved project and are the values stored
        # under the qgis2fds property group.
        project.writeEntry(PROJECT_GROUP, spec.name, value.id() if value else "")
    elif spec.kind == "point":
        if value is None:
            stored = ""
        elif isinstance(raw, str):
            # parameterAsPoint resolves the point, but the raw representation also
            # carries the input CRS and is the safest value to restore later.
            stored = raw
        else:
            stored = "{:.12g},{:.12g} [{}]".format(
                value.x(), value.y(), project.crs().authid()
            )
        project.writeEntry(PROJECT_GROUP, spec.name, stored)
    else:
        # Preserve relative paths exactly when possible.
        stored = raw if isinstance(raw, str) else value
        project.writeEntry(PROJECT_GROUP, spec.name, stored or "")


def _describe(value):
    if value is None or value == "":
        return "none"
    if hasattr(value, "name"):
        return value.name()
    return value
