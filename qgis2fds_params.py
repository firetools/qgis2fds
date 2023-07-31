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
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterBoolean,
    QgsPoint,
)
import os


class ChidParam:
    label = "chid"
    desc = "FDS case identificator (CHID)"
    default = "terrain"
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterString(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            multiLine=False,
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsString(parameters, cls.label, context)
        project.writeEntry("qgis2fds", cls.label, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class FDSPathParam:
    label = "fds_path"
    desc = "Save in folder"
    default = "./"
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterFile(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            behavior=QgsProcessingParameterFile.Folder,
            fileFilter="All files (*.*)",
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsFile(parameters, cls.label, context)
        project.writeEntry("qgis2fds", cls.label, value)
        # Make and check absolute path
        project_path = project.absolutePath()
        if not project_path:
            raise QgsProcessingException("Save QGIS project to disk, cannot proceed.")
        value = os.path.join(project_path, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class ExtentParam:
    label = "extent"
    desc = "Domain extent"
    default = None
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterExtent(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsExtent(
            parameters, cls.label, context, crs=project.crs()
        )  # in project crs
        project.writeEntry("qgis2fds", cls.label, parameters[cls.label])  # protect
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class PixelSizeParam:
    label = "pixel_size"
    desc = "Desired terrain resolution (in meters)"
    default = 10.0
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readDoubleEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterNumber(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            type=QgsProcessingParameterNumber.Double,
            minValue=0.01,
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsDouble(parameters, cls.label, context)
        project.writeEntryDouble("qgis2fds", cls.label, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class OriginParam:
    label = "origin"
    desc = "Domain origin (if not set, use domain extent centroid)"
    default = None
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterPoint(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = parameters.get(cls.label)
        project.writeEntry("qgis2fds", cls.label, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        if value:
            return QgsPoint(
                algo.parameterAsPoint(parameters, cls.label, context, crs=project.crs())
            )  # in project crs


class DEMLayerParam:
    label = "dem_layer"
    desc = "DEM layer"
    default = None
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        # Suggest first layer name containing "dem"
        if not defaultValue:
            try:
                defaultValue = [
                    layer.name()
                    for layer in project.mapLayers().values()
                    if "DEM" in layer.name() or "dem" in layer.name()
                ][0]
            except IndexError:
                pass
        param = QgsProcessingParameterRasterLayer(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsRasterLayer(parameters, cls.label, context)
        # Check local
        url = value.source()
        if not os.path.isfile(url):
            raise QgsProcessingException(
                "DEM layer data is not saved locally, cannot proceed."
            )
        # Check valid
        if not value.crs().isValid():
            raise QgsProcessingException(
                f"DEM layer CRS <{value.crs().description()}> not valid, cannot proceed."
            )
        project.writeEntry("qgis2fds", cls.label, parameters[cls.label])  # protect
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class LanduseLayerParam:
    label = "landuse_layer"
    desc = "Landuse layer (if not set, landuse is not exported)"
    default = None
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterRasterLayer(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = None
        if parameters[cls.label]:
            value = algo.parameterAsRasterLayer(parameters, cls.label, context)
        if value:
            # Check local
            url = value.source()
            if not os.path.isfile(url):
                raise QgsProcessingException(
                    "Landuse layer data is not saved locally, cannot proceed."
                )
            # Check valid
            if not value.crs().isValid():
                raise QgsProcessingException(
                    f"Landuse layer CRS <{value.crs().description()}> not valid, cannot proceed."
                )
        project.writeEntry("qgis2fds", cls.label, parameters[cls.label])  # protect
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class LanduseTypeFilepathParam:
    label = "landuse_type_filepath"
    desc = "Landuse type *.csv file (if not set, landuse is not exported)"
    default = ""
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterFile(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            behavior=QgsProcessingParameterFile.File,
            fileFilter="CSV files (*.csv)",
        )
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = None
        if parameters[cls.label]:
            value = algo.parameterAsFile(parameters, cls.label, context)
        project.writeEntry("qgis2fds", cls.label, value or "")  # protect
        if value:
            # Make and check absolute path
            project_path = project.absolutePath()
            if not project_path:
                raise QgsProcessingException(
                    "Save QGIS project to disk, cannot proceed."
                )
            value = os.path.join(project_path, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class TextFilepathParam:
    label = "text_filepath"
    desc = "Free text file"
    default = ""
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterFile(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            behavior=QgsProcessingParameterFile.File,
            # fileFilter="TXT files (*.txt)",
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = None
        if parameters[cls.label]:
            value = algo.parameterAsFile(parameters, cls.label, context)
        project.writeEntry("qgis2fds", cls.label, value or "")  # protect
        if value:
            # Make and check absolute path
            project_path = project.absolutePath()
            if not project_path:
                raise QgsProcessingException(
                    "Save QGIS project to disk, cannot proceed."
                )
            value = os.path.join(project_path, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class TexLayerParam:
    label = "tex_layer"
    desc = "Texture layer (if not set, export current canvas view)"
    default = None
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterRasterLayer(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = None
        if parameters[cls.label]:
            value = algo.parameterAsRasterLayer(parameters, cls.label, context)
        if value and not value.crs().isValid():
            raise QgsProcessingException(
                f"Texture layer CRS <{value.crs().description()}> not valid, cannot proceed."
            )
        project.writeEntry("qgis2fds", cls.label, parameters[cls.label])  # protect
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class TexPixelSizeParam:
    label = "tex_pixel_size"
    desc = "Desired texture resolution (in meters)"
    default = 10.0
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readDoubleEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterNumber(
            cls.label,
            cls.desc,
            defaultValue=defaultValue or None,  # protect
            optional=cls.optional,
            type=QgsProcessingParameterNumber.Double,
            minValue=0.01,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        if parameters[cls.label]:
            value = algo.parameterAsDouble(parameters, cls.label, context)
            project.writeEntryDouble("qgis2fds", cls.label, value)
        else:  # protect
            value = None
            project.writeEntry("qgis2fds", cls.label, None)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class NMeshParam:
    label = "nmesh"
    desc = "Max number of FDS MESH namelists"
    default = 1
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readNumEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterNumber(
            cls.label,
            cls.desc,
            defaultValue=defaultValue,
            optional=cls.optional,
            type=QgsProcessingParameterNumber.Integer,
            minValue=1,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsInt(parameters, cls.label, context)
        project.writeEntryDouble("qgis2fds", cls.label, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class CellSizeParam:
    label = "cell_size"
    desc = "Desired FDS MESH cell size (in meters; if not set, use desired terrain resolution)"
    default = 10.0
    optional = True

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readDoubleEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterNumber(
            cls.label,
            cls.desc,
            defaultValue=defaultValue or None,  # protect
            optional=cls.optional,
            type=QgsProcessingParameterNumber.Double,
            minValue=0.01,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        if parameters[cls.label]:
            value = algo.parameterAsDouble(parameters, cls.label, context)
            project.writeEntryDouble("qgis2fds", cls.label, value)
        else:  # protect
            value = None
            project.writeEntry("qgis2fds", cls.label, None)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value


class ExportOBSTParam:
    label = "export_obst"
    desc = "Export FDS OBST namelists"
    default = True
    optional = False

    @classmethod
    def set(cls, algo, config, project):
        defaultValue, _ = project.readBoolEntry("qgis2fds", cls.label, cls.default)
        param = QgsProcessingParameterBoolean(
            cls.label,
            cls.desc,
            defaultValue=defaultValue or None,  # protect, why?
            optional=cls.optional,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        algo.addParameter(param)

    @classmethod
    def get(cls, algo, parameters, context, feedback, project):
        value = algo.parameterAsBool(parameters, cls.label, context)
        project.writeEntryBool("qgis2fds", cls.label, value)
        feedback.setProgressText(f"{cls.desc}: <{value}>")
        return value
