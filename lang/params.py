# -*- coding: utf-8 -*-

"""qgis2fds parameter classes"""

__author__ = "Emanuele Gissi"
__date__ = "2020-05-04"
__copyright__ = "(C) 2020 by Emanuele Gissi"
__revision__ = "$Format:%H$"  # replaced with git SHA1


from qgis.core import (
    QgsProcessingException,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterPoint,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterBoolean,
    QgsPoint,
    QgsRasterLayer,
)
import os
from . import utils


class _Param:
    name = "example"
    label = "Example"
    info = ""
    default = None
    optional = False
    kwargs = {}
    advanced = False


# String params


class ChidParam(_Param):
    name = "chid"
    label = "FDS HEAD CHID"
    info = "case identificator"
    default = "terrain"
    optional = False
    kwargs = {}
    advanced = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterString(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsString(parameters, cls.name, context)
        project.writeEntry("qgis2fds", cls.name, value)
        feedback.setProgressText(f"{cls.label}: {value}")
        return value


# Point param


class OriginParam(_Param):
    name = "origin"
    label = "Domain origin"
    info = "if not set, use domain extent centroid"
    default = None
    optional = True
    kwargs = {}
    advanced = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterPoint(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = parameters.get(cls.name)
        project.writeEntry("qgis2fds", cls.name, value)
        feedback.setProgressText(f"{cls.label}: {value}")
        if value:
            return QgsPoint(
                algo.parameterAsPoint(parameters, cls.name, context, crs=project.crs())
            )  # in project crs


# Int param


class NMeshParam(_Param):
    name = "nmesh"
    label = "Max number of FDS MESH namelists"
    default = 1
    optional = False
    kwargs = {
        "type": QgsProcessingParameterNumber.Integer,
        "minValue": 1,
    }
    advanced = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readNumEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterNumber(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsInt(parameters, cls.name, context)
        project.writeEntryDouble("qgis2fds", cls.name, value)
        feedback.setProgressText(f"{cls.label}: {value}")
        return value


# Float param


class _FloatParam(_Param):
    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readDoubleEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterNumber(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        if cls.name in parameters:
            value = algo.parameterAsDouble(parameters, cls.name, context)
            project.writeEntryDouble("qgis2fds", cls.name, value)
        else:
            value = cls.default
            project.writeEntry("qgis2fds", cls.name, None)
        feedback.setProgressText(f"{cls.label}: {value}")
        return value


class PixelSizeParam(_FloatParam):
    name = "pixel_size"
    label = "Terrain resolution"
    info = "in meters"
    default = 10.0
    optional = False
    kwargs = {
        "type": QgsProcessingParameterNumber.Double,
        "minValue": 0.01,
    }
    advanced = False


class TexPixelSizeParam(_FloatParam):
    name = "tex_pixel_size"
    label = "Texture resolution"
    info = "in meters"
    default = 10.0
    optional = False
    kwargs = {
        "type": QgsProcessingParameterNumber.Double,
        "minValue": 0.01,
    }
    advanced = True


class CellSizeParam(_FloatParam):
    name = "cell_size"
    label = "FDS MESH cell size"
    info = "in meters; if not set, use desired terrain resolution"
    default = 10.0
    optional = True
    kwargs = {
        "type": QgsProcessingParameterNumber.Double,
        "minValue": 0.01,
    }
    advanced = True


class StartTimeParam(_FloatParam):
    name = "t_begin"
    label = "FDS TIME T_BEGIN"
    info = "simulation start time"
    default = 0.0
    optional = False
    kwargs = {
        "type": QgsProcessingParameterNumber.Double,
    }
    advanced = True


class EndTimeParam(_FloatParam):
    name = "t_end"
    label = "FDS TIME T_END"
    info = "simulation end time"
    default = 0.0
    optional = False
    kwargs = {
        "type": QgsProcessingParameterNumber.Double,
    }
    advanced = True


# Path param


class _PathParam(_Param):
    kwargs = {
        "behavior": QgsProcessingParameterFile.Folder,
        "fileFilter": "All files (*.*)",
    }

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterFile(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = None
        if parameters.get(cls.name):
            value = algo.parameterAsFile(parameters, cls.name, context)
            value = os.path.join(*value.split("\\"))  # Windows safe
        project.writeEntry("qgis2fds", cls.name, value or "")  # protect
        if value:
            # Make and check absolute path
            project_path = project.absolutePath()
            if not project_path:
                msg = "QGIS project is not saved to disk, cannot proceed."
                raise QgsProcessingException(msg)
            value = os.path.join(project_path, value)
            # Check existance
            if cls.kwargs["behavior"] == QgsProcessingParameterFile.Folder:
                if not os.path.isdir(value):
                    raise QgsProcessingException(f"Folder {value} not found.")
            else:
                if not os.path.isfile(value):
                    raise QgsProcessingException(f"File {value} not found.")
        feedback.setProgressText(f"{cls.label}: {value}")
        return value


class FDSPathParam(_PathParam):
    name = "fds_path"
    label = "FDS case folder"
    default = "../FDS"
    optional = False
    kwargs = {
        "behavior": QgsProcessingParameterFile.Folder,
        "fileFilter": "All files (*.*)",
    }
    advanced = False


class LanduseTypeFilepathParam(_PathParam):
    name = "landuse_type_filepath"
    label = "Landuse type file"
    info = "*.csv"
    default = ""
    optional = True
    kwargs = {
        "behavior": QgsProcessingParameterFile.File,
        "fileFilter": "CSV files (*.csv)",
    }
    advanced = False


class TextFilepathParam(_PathParam):
    name = "text_filepath"
    label = "Free text file"
    info = "text appended to FDS case"
    default = ""
    optional = True
    kwargs = {
        "behavior": QgsProcessingParameterFile.File,
        # "fileFilter": "TXT files (*.txt)",
    }
    advanced = False


class WindFilepathParam(_PathParam):
    name = "wind_filepath"
    label = "Wind file"
    info = "*.csv"
    default = ""
    optional = True
    kwargs = {
        "behavior": QgsProcessingParameterFile.File,
        "fileFilter": "CSV files (*.csv)",
    }
    advanced = False


# Raster layer Params


class _RasterLayerParam(_Param):
    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterRasterLayer(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project, extent, extent_crs):
        layer = None
        if parameters.get(cls.name):
            layer = algo.parameterAsRasterLayer(parameters, cls.name, context)
        if layer:
            # Check validity
            if not layer.crs().isValid():
                msg = f"{cls.label} CRS {layer.crs().description()} not valid, cannot proceed."
                raise QgsProcessingException(msg)

            # Check local otherwise save it
            url = layer.source()
            if not os.path.isfile(url):
                # Make and check absolute path
                project_path = project.absolutePath()
                if not project_path:
                    msg = "QGIS project is not saved to disk, cannot proceed."
                    raise QgsProcessingException(msg)
                path = os.path.join(project_path, "layers")

                # Create layers directory
                if not os.path.isdir(path):
                    try:
                        os.makedirs(path, exist_ok=True)
                    except:
                        msg = "Error creating path {path}."
                        raise QgsProcessingException(msg)

                # Trasform extent to the layer crs
                extent = utils.transform_extent(
                    extent=extent,
                    source_crs=extent_crs,
                    dest_crs=layer.crs(),
                )

                # Save the layer
                filename = f"{layer.name()}_downloaded.tif"
                filepath = os.path.join(path, filename)
                utils.save_raster_layer(layer=layer, extent=extent, filepath=filepath)

                # Load the layer, but do not link
                layer = QgsRasterLayer(filepath, filename)
                if not layer.isValid():
                    msg = f"Layer {filename} is not valid, cannot proceed.\n{filepath}"
                    raise QgsProcessingException(msg)

                # Inform the user
                msg = f"""
\n{cls.label} is a link to a *remote data repository*.
The required layer data was just downloaded at:
{filepath}
To avoid downloading again, replace the remote repository with local data.
For help, see: https://github.com/firetools/qgis2fds/wiki/Save-remote-layers
"""
                feedback.pushWarning(msg)

        project.writeEntry("qgis2fds", cls.name, parameters.get(cls.name))  # protect
        feedback.setProgressText(f"{cls.label}: {layer}")
        return layer


class DEMLayerParam(_RasterLayerParam):
    name = "dem_layer"
    label = "DEM layer"
    default = None
    optional = False


class LanduseLayerParam(_RasterLayerParam):
    name = "landuse_layer"
    label = "Landuse layer"
    info = "if not set, landuse is not exported"
    default = None
    optional = True


# class TexLayerParam:
#     name = "tex_layer"
#     label = "Texture layer"
#     info = "if not set, export current canvas view"
#     default = None
#     optional = True

#     @classmethod
#     def set(cls, algo, config, project):
#         defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
#         label = cls.info and f"{cls.label} ({cls.info})" or cls.label
#         param = QgsProcessingParameterRasterLayer(
#             cls.name,
#             label,
#             defaultValue=defaultValue,
#             optional=cls.optional,
#         )
#         param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
#         algo.addParameter(param)

#     @classmethod
#     def get(cls, algo, parameters, context, feedback, project):
#         value = None
#         if parameters.get(cls.name):
#             value = algo.parameterAsRasterLayer(parameters, cls.name, context)
#         if value and not value.crs().isValid():
#             raise QgsProcessingException(
#                 f"Texture layer CRS {value.crs().description()} not valid, cannot proceed."
#             )
#         project.writeEntry("qgis2fds", cls.name, parameters.get(cls.name))  # protect
#         feedback.setProgressText(f"{cls.label}: {value}")
#         return value


# Vector layer param


class _VectorLayerParam(_Param):
    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterVectorLayer(
            cls.name,
            label,
            defaultValue=defaultValue,
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        layer = None
        if parameters.get(cls.name):
            layer = algo.parameterAsVectorLayer(parameters, cls.name, context)
        if layer:
            # Check validity
            if not layer.crs().isValid():
                msg = f"{cls.label} CRS {layer.crs().description()} not valid, cannot proceed."
                raise QgsProcessingException(msg)
        project.writeEntry("qgis2fds", cls.name, parameters.get(cls.name))  # protect
        feedback.setProgressText(f"{cls.label}: {layer}")
        return layer


class ExtentLayerParam(_VectorLayerParam):
    name = "extent_layer"
    label = "Domain extent layer"
    default = None
    optional = False


class FireLayer(_VectorLayerParam):
    name = "fire_layer"
    label = "Fire layer"
    info = "if not set, fire is not exported"
    default = None
    optional = True


# Bool param


class ExportOBSTParam(_Param):
    name = "export_obst"
    label = "Export FDS OBST namelists"
    default = True
    optional = False
    kwargs = {}
    advanced = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readBoolEntry("qgis2fds", cls.name, cls.default)
        label = cls.info and f"{cls.label} ({cls.info})" or cls.label
        param = QgsProcessingParameterBoolean(
            cls.name,
            label,
            defaultValue=defaultValue or None,  # protect
            optional=cls.optional,
            **cls.kwargs,
        )
        if cls.advanced:
            param.setFlags(
                param.flags() | QgsProcessingParameterDefinition.FlagAdvanced
            )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsBool(parameters, cls.name, context)
        project.writeEntryBool("qgis2fds", cls.name, value)
        feedback.setProgressText(f"{cls.label}: {value}")
        return value
