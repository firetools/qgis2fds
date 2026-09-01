"""Persistent local copies of remote numeric rasters, downloaded via WCS."""

import math
import os
import re
import shutil
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import numpy as np
from qgis.PyQt.QtCore import QXmlStreamReader
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingException,
    QgsProject,
    QgsRasterFileWriter,
    QgsRasterLayer,
    QgsRasterPipe,
    QgsRectangle,
)

from .parameters import PROJECT_GROUP


LOCAL_COPY_SUFFIX = "qgis2fds_local"
REMOTE_DOWNLOAD_TIMEOUT = 120
REMOTE_BUFFER_PIXELS = 1
REMOTE_METADATA_MAXIMUM_BYTES = 8_000_000
REMOTE_XML_MAXIMUM_DEPTH = 128
REMOTE_XML_MAXIMUM_ELEMENTS = 100_000
REMOTE_URL_SCHEMES = frozenset(("http", "https"))
RASTER_NUMPY_DTYPES = {
    Qgis.DataType.Byte: np.dtype("u1"),
    Qgis.DataType.Int8: np.dtype("i1"),
    Qgis.DataType.UInt16: np.dtype("=u2"),
    Qgis.DataType.Int16: np.dtype("=i2"),
    Qgis.DataType.UInt32: np.dtype("=u4"),
    Qgis.DataType.Int32: np.dtype("=i4"),
    Qgis.DataType.Float32: np.dtype("=f4"),
    Qgis.DataType.Float64: np.dtype("=f8"),
}


class RemoteXmlError(ValueError):
    """Raised when remote WCS XML is unsafe or malformed."""


def _validate_remote_url(url):
    """Reject local and custom URL schemes before opening a remote resource."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        parts.port
    except (TypeError, ValueError) as error:
        raise URLError("Remote WCS URL is invalid") from error
    if parts.scheme.lower() not in REMOTE_URL_SCHEMES or hostname is None:
        raise URLError("Remote WCS URLs must use HTTP or HTTPS")


class _RemoteRedirectHandler(HTTPRedirectHandler):
    """Allow redirects only when their destination is also HTTP(S)."""

    def redirect_request(self, request, file_pointer, code, message, headers, url):
        _validate_remote_url(url)
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            url,
        )


_REMOTE_OPENER = build_opener(_RemoteRedirectHandler())


def _open_remote_request(request):
    """Open one validated HTTP(S) request with a bounded timeout."""
    _validate_remote_url(request.full_url)
    return _REMOTE_OPENER.open(request, timeout=REMOTE_DOWNLOAD_TIMEOUT)


def ensure_local_raster(
    layer,
    grid,
    utm_crs,
    label,
    parameter_name,
    interpolation,
    feedback,
):
    """Download, add, and select a buffered native-resolution local copy."""
    if not _requires_local_copy(layer):
        return layer

    project = QgsProject.instance()
    project_directory = project.absolutePath()
    if not project_directory:
        raise QgsProcessingException(
            "{} remote layer requires the QGIS project to be saved before a "
            "local copy can be created.".format(label)
        )

    wcs = None
    if (
        layer.providerType().lower() in ("wms", "wcs")
        or _is_rendered_color_provider(layer)
    ):
        feedback.pushInfo(
            "[qgis2fds] Reading native WCS grid for remote {} '{}'.".format(
                label, layer.name()
            )
        )
        wcs = _describe_coverage(layer)
        copy_crs = wcs["crs"]
        coverage_extent = wcs["extent"]
        resolution_x = wcs["resolution_x"]
        resolution_y = wcs["resolution_y"]
    else:
        copy_crs = layer.crs()
        coverage_extent = layer.extent()
        resolution_x, resolution_y = _provider_native_resolution(layer)

    try:
        to_source = QgsCoordinateTransform(utm_crs, copy_crs, project)
        required_extent = to_source.transformBoundingBox(_grid_rectangle(grid))
    except Exception as error:
        raise QgsProcessingException(
            "Cannot calculate the local-copy extent for {} layer '{}': {}".format(
                label, layer.name(), error
            )
        )
    if required_extent.isEmpty():
        raise QgsProcessingException(
            "The local-copy extent for {} layer '{}' is empty.".format(
                label, layer.name()
            )
        )

    source_extent, columns, rows = _buffered_native_grid(
        required_extent,
        coverage_extent,
        resolution_x,
        resolution_y,
    )
    layers_directory = os.path.join(project_directory, "layers")
    os.makedirs(layers_directory, exist_ok=True)
    local_path = os.path.join(layers_directory, _local_copy_filename(layer))
    temporary_path = local_path + ".part.tif"
    _remove_incomplete_copy(temporary_path)

    download_method = "WCS" if wcs is not None else "its numeric provider"
    feedback.pushInfo(
        "[qgis2fds] Downloading remote {} '{}' through {} at native "
        "resolution {:.6g} x {:.6g}, with a {}-pixel buffer ({} x {} cells): "
        "{}.".format(
            label,
            layer.name(),
            download_method,
            resolution_x,
            resolution_y,
            REMOTE_BUFFER_PIXELS,
            columns,
            rows,
            local_path,
        )
    )

    try:
        if wcs is not None:
            _download_coverage(
                wcs,
                source_extent,
                resolution_x,
                resolution_y,
                interpolation,
                temporary_path,
            )
        else:
            _write_numeric_provider(
                layer,
                source_extent,
                columns,
                rows,
                temporary_path,
                project,
                copy_crs,
            )

        local = _numeric_raster_layer(temporary_path, layer.name())
        if local is None:
            raise QgsProcessingException(
                "The downloaded {} layer '{}' is not a single-band numeric "
                "raster.".format(label, layer.name())
            )
        _validate_local_grid(
            local,
            copy_crs,
            source_extent,
            columns,
            rows,
            resolution_x,
            resolution_y,
            label,
        )
        # Release the validation layer before publishing the completed file.
        del local
        os.replace(temporary_path, local_path)
    except QgsProcessingException:
        raise
    except (HTTPError, URLError, OSError) as error:
        raise QgsProcessingException(
            "Cannot create the local copy for {} layer '{}': {}".format(
                label, layer.name(), error
            )
        )
    finally:
        _remove_incomplete_copy(temporary_path)

    local = _numeric_raster_layer(local_path, layer.name())
    if local is None:  # pragma: no cover - guarded before the atomic rename
        raise QgsProcessingException(
            "The local copy for {} layer '{}' cannot be opened.".format(
                label, layer.name()
            )
        )
    return _link_local_raster(local, layer, parameter_name, label, feedback)


def _requires_local_copy(layer):
    """Return whether the raster source is not a normal local GDAL dataset."""
    if layer.providerType() != "gdal":
        return True
    source = layer.source().split("|", 1)[0].lower()
    return source.startswith(
        ("http://", "https://", "ftp://", "/vsicurl/", "/vsis3/")
    )


def _provider_native_resolution(layer):
    """Read the native pixel size reported by a numeric raster provider."""
    provider = layer.dataProvider()
    if provider.xSize() > 0 and provider.ySize() > 0:
        return (
            layer.extent().width() / provider.xSize(),
            layer.extent().height() / provider.ySize(),
        )
    resolutions = [value for value in provider.nativeResolutions() if value > 0]
    if resolutions:
        finest = min(resolutions)
        return finest, finest
    raise QgsProcessingException(
        "Remote numeric layer '{}' does not report a native resolution.".format(
            layer.name()
        )
    )


def _buffered_native_grid(required, coverage, resolution_x, resolution_y):
    """Align the requested extent to the native grid plus one pixel around it."""
    tolerance_x = resolution_x * 1e-6
    tolerance_y = resolution_y * 1e-6
    if (
        required.xMinimum() < coverage.xMinimum() - tolerance_x
        or required.xMaximum() > coverage.xMaximum() + tolerance_x
        or required.yMinimum() < coverage.yMinimum() - tolerance_y
        or required.yMaximum() > coverage.yMaximum() + tolerance_y
    ):
        raise QgsProcessingException(
            "The remote raster does not cover the complete requested extent."
        )

    first_column = math.floor(
        (required.xMinimum() - coverage.xMinimum()) / resolution_x
    ) - REMOTE_BUFFER_PIXELS
    last_column = math.ceil(
        (required.xMaximum() - coverage.xMinimum()) / resolution_x
    ) + REMOTE_BUFFER_PIXELS
    first_row = math.floor(
        (required.yMinimum() - coverage.yMinimum()) / resolution_y
    ) - REMOTE_BUFFER_PIXELS
    last_row = math.ceil(
        (required.yMaximum() - coverage.yMinimum()) / resolution_y
    ) + REMOTE_BUFFER_PIXELS

    maximum_columns = int(round(coverage.width() / resolution_x))
    maximum_rows = int(round(coverage.height() / resolution_y))
    first_column = max(0, first_column)
    first_row = max(0, first_row)
    last_column = min(maximum_columns, last_column)
    last_row = min(maximum_rows, last_row)
    columns = last_column - first_column
    rows = last_row - first_row
    if columns < 1 or rows < 1:
        raise QgsProcessingException("The buffered remote raster extent is empty.")

    extent = QgsRectangle(
        coverage.xMinimum() + first_column * resolution_x,
        coverage.yMinimum() + first_row * resolution_y,
        coverage.xMinimum() + last_column * resolution_x,
        coverage.yMinimum() + last_row * resolution_y,
    )
    return extent, columns, rows


def _local_copy_filename(layer):
    """Build a unique filename for every explicitly requested download."""
    basename = re.sub(r"[^A-Za-z0-9_.-]+", "_", layer.name()).strip("._")
    basename = (basename or "remote_raster")[:80]
    return "{}_{}_{}.tif".format(
        basename, LOCAL_COPY_SUFFIX, uuid.uuid4().hex[:12]
    )


def _link_local_raster(
    local,
    remote,
    parameter_name,
    label,
    feedback,
):
    """Add the local copy to the layer tree and select it for qgis2fds."""
    project = QgsProject.instance()
    filename = os.path.splitext(os.path.basename(local.source()))[0]
    unique_id = filename.rsplit("_", 1)[-1]
    local.setName("{} (local {})".format(remote.name(), unique_id))
    local.setCustomProperty("qgis2fds/remote_layer_id", remote.id())
    local.setCustomProperty("qgis2fds/parameter", parameter_name)
    project.addMapLayer(local, False)
    node = project.layerTreeRoot().addLayer(local)
    node.setItemVisibilityChecked(False)

    project.writeEntry(PROJECT_GROUP, parameter_name, local.id())
    project.setDirty(True)
    feedback.pushInfo(
        "[qgis2fds] Added local {} layer '{}' in the Layers panel; {} now uses "
        "this layer. Remote layer '{}' was not changed. Save the QGIS project "
        "to persist this selection.".format(
            label,
            local.name(),
            parameter_name,
            remote.name(),
        )
    )
    return local


def _numeric_raster_layer(filepath, name):
    """Open a usable one-band numeric local copy, or return None."""
    if not os.path.isfile(filepath):
        return None
    layer = QgsRasterLayer(filepath, name)
    if (
        not layer.isValid()
        or layer.bandCount() != 1
        or layer.dataProvider().dataType(1) not in RASTER_NUMPY_DTYPES
    ):
        return None
    return layer


def _validate_local_grid(
    layer,
    expected_crs,
    expected_extent,
    expected_columns,
    expected_rows,
    expected_resolution_x,
    expected_resolution_y,
    label,
):
    """Verify that WCS returned the requested native, buffered grid."""
    provider = layer.dataProvider()
    actual_columns = provider.xSize()
    actual_rows = provider.ySize()
    actual_extent = layer.extent()
    actual_resolution_x = actual_extent.width() / actual_columns
    actual_resolution_y = actual_extent.height() / actual_rows
    # The WCS request serializes large projected coordinates as decimal text.
    # Allow sub-millimetre rounding while still rejecting a shifted pixel grid.
    tolerance_x = max(abs(expected_resolution_x) * 1e-5, 1e-8)
    tolerance_y = max(abs(expected_resolution_y) * 1e-5, 1e-8)
    extent_matches = (
        abs(actual_extent.xMinimum() - expected_extent.xMinimum()) <= tolerance_x
        and abs(actual_extent.xMaximum() - expected_extent.xMaximum())
        <= tolerance_x
        and abs(actual_extent.yMinimum() - expected_extent.yMinimum())
        <= tolerance_y
        and abs(actual_extent.yMaximum() - expected_extent.yMaximum())
        <= tolerance_y
    )
    if (
        layer.crs().authid() != expected_crs.authid()
        or actual_columns != expected_columns
        or actual_rows != expected_rows
        or abs(actual_resolution_x - expected_resolution_x) > tolerance_x
        or abs(actual_resolution_y - expected_resolution_y) > tolerance_y
        or not extent_matches
    ):
        raise QgsProcessingException(
            "The local {} raster does not match the requested native WCS "
            "grid (expected {} x {} cells at {:.6g} x {:.6g} in {}; got "
            "{} x {} at {:.6g} x {:.6g} in {}). Expected extent "
            "{:.12g},{:.12g}:{:.12g},{:.12g}; got "
            "{:.12g},{:.12g}:{:.12g},{:.12g}.".format(
                label,
                expected_columns,
                expected_rows,
                expected_resolution_x,
                expected_resolution_y,
                expected_crs.authid(),
                actual_columns,
                actual_rows,
                actual_resolution_x,
                actual_resolution_y,
                layer.crs().authid(),
                expected_extent.xMinimum(),
                expected_extent.yMinimum(),
                expected_extent.xMaximum(),
                expected_extent.yMaximum(),
                actual_extent.xMinimum(),
                actual_extent.yMinimum(),
                actual_extent.xMaximum(),
                actual_extent.yMaximum(),
            )
        )


def _remove_incomplete_copy(filepath):
    """Remove only temporary files from an interrupted local-copy write."""
    for candidate in (filepath, filepath + ".aux.xml"):
        if os.path.exists(candidate):
            os.remove(candidate)


def _is_rendered_color_provider(layer):
    return layer.dataProvider().dataType(1) in (
        Qgis.DataType.ARGB32,
        Qgis.DataType.ARGB32_Premultiplied,
    )


def _write_numeric_provider(
    layer,
    extent,
    columns,
    rows,
    filepath,
    project,
    copy_crs,
):
    """Write raw samples from a numeric remote provider as GeoTIFF."""
    pipe = QgsRasterPipe()
    if not pipe.set(layer.dataProvider().clone()):
        raise QgsProcessingException(
            "Cannot create a raw raster pipe for remote layer '{}'.".format(
                layer.name()
            )
        )
    writer = QgsRasterFileWriter(filepath)
    writer.setOutputFormat("GTiff")
    result = writer.writeRaster(
        pipe,
        columns,
        rows,
        extent,
        copy_crs,
        project.transformContext(),
    )
    if result != Qgis.RasterFileWriterResult.Success:
        raise QgsProcessingException(
            "QGIS could not save remote layer '{}' (writer result {}).".format(
                layer.name(), int(result)
            )
        )


def _xml_numbers(text, element_name):
    """Parse finite numeric XML element content."""
    try:
        values = [float(value) for value in text.split()]
    except ValueError as error:
        raise RemoteXmlError(
            "WCS {} contains invalid numeric data".format(element_name)
        ) from error
    if any(not math.isfinite(value) for value in values):
        raise RemoteXmlError(
            "WCS {} contains non-finite numeric data".format(element_name)
        )
    return values


def _parse_coverage_xml(data):
    """Extract required WCS fields with Qt's non-DOM streaming parser."""
    reader = QXmlStreamReader(data)
    elements = []
    element_count = 0
    rectified_found = False
    rectified_depth = None
    rectified_crs = ""
    vectors = []
    envelope_stack = []
    envelopes = []

    while not reader.atEnd():
        token = reader.readNext()
        if token in (
            QXmlStreamReader.TokenType.DTD,
            QXmlStreamReader.TokenType.EntityReference,
        ):
            raise RemoteXmlError("WCS XML must not contain DTDs or entities")

        if reader.isStartElement():
            element_count += 1
            if element_count > REMOTE_XML_MAXIMUM_ELEMENTS:
                raise RemoteXmlError("WCS XML contains too many elements")
            name = str(reader.name())
            elements.append([name, []])
            depth = len(elements)
            if depth > REMOTE_XML_MAXIMUM_DEPTH:
                raise RemoteXmlError("WCS XML nesting is too deep")
            if name == "RectifiedGrid" and not rectified_found:
                rectified_found = True
                rectified_depth = depth
                rectified_crs = str(reader.attributes().value("srsName"))
            elif name == "Envelope":
                envelope_stack.append(
                    {
                        "depth": depth,
                        "crs": str(reader.attributes().value("srsName")),
                        "positions": [],
                    }
                )
        elif token == QXmlStreamReader.TokenType.Characters and elements:
            elements[-1][1].append(str(reader.text()))
        elif reader.isEndElement():
            if not elements:
                raise RemoteXmlError("WCS XML has an unexpected closing element")
            name, text_parts = elements.pop()
            depth = len(elements) + 1
            if name != str(reader.name()):
                raise RemoteXmlError("WCS XML elements are not balanced")
            text = "".join(text_parts)
            if (
                name == "offsetVector"
                and rectified_depth is not None
                and depth > rectified_depth
            ):
                vectors.append(_xml_numbers(text, name))
            elif (
                name == "pos"
                and envelope_stack
                and depth > envelope_stack[-1]["depth"]
            ):
                envelope_stack[-1]["positions"].append(
                    _xml_numbers(text, name)
                )
            elif (
                name == "Envelope"
                and envelope_stack
                and depth == envelope_stack[-1]["depth"]
            ):
                envelope = envelope_stack.pop()
                envelopes.append((envelope["crs"], envelope["positions"]))
            elif name == "RectifiedGrid" and depth == rectified_depth:
                rectified_depth = None

    if reader.hasError():
        raise RemoteXmlError("Invalid WCS XML: {}".format(reader.errorString()))
    if elements:
        raise RemoteXmlError("WCS XML contains unclosed elements")
    return rectified_found, rectified_crs, vectors, envelopes


def _describe_coverage(layer):
    """Read the native grid of the WCS coverage represented by a layer."""
    parts, coverage = _coverage_service(layer)
    url = _wcs_url(
        parts,
        (
            ("service", "WCS"),
            ("version", "1.0.0"),
            ("request", "DescribeCoverage"),
            ("coverage", coverage),
        ),
    )
    request = Request(url, headers={"User-Agent": "qgis2fds/2.0"})
    try:
        with _open_remote_request(request) as response:
            data = response.read(REMOTE_METADATA_MAXIMUM_BYTES + 1)
        if len(data) > REMOTE_METADATA_MAXIMUM_BYTES:
            raise RemoteXmlError("WCS metadata response is too large")
        rectified_found, crs_name, vectors, envelopes = _parse_coverage_xml(data)
    except (RemoteXmlError, HTTPError, URLError, OSError) as error:
        raise QgsProcessingException(
            "Cannot read WCS metadata for remote layer '{}': {}".format(
                layer.name(), error
            )
        )

    if not rectified_found:
        raise QgsProcessingException(
            "WCS layer '{}' does not describe a native rectified grid.".format(
                layer.name()
            )
        )
    crs = QgsCoordinateReferenceSystem(crs_name)
    if not crs.isValid():
        raise QgsProcessingException(
            "WCS layer '{}' has no valid native CRS.".format(layer.name())
        )

    resolution_x = max(
        (abs(vector[0]) for vector in vectors if len(vector) >= 2), default=0.0
    )
    resolution_y = max(
        (abs(vector[1]) for vector in vectors if len(vector) >= 2), default=0.0
    )
    if resolution_x <= 0 or resolution_y <= 0:
        raise QgsProcessingException(
            "WCS layer '{}' has no usable native resolution.".format(layer.name())
        )

    coverage_extent = None
    for envelope_crs, positions in envelopes:
        if envelope_crs != crs_name:
            continue
        if (
            len(positions) >= 2
            and len(positions[0]) >= 2
            and len(positions[1]) >= 2
        ):
            coverage_extent = QgsRectangle(
                positions[0][0],
                positions[0][1],
                positions[1][0],
                positions[1][1],
            )
            break
    if coverage_extent is None or coverage_extent.isEmpty():
        raise QgsProcessingException(
            "WCS layer '{}' has no usable native extent.".format(layer.name())
        )

    return {
        "parts": parts,
        "coverage": coverage,
        "crs": crs,
        "crs_name": crs_name,
        "extent": coverage_extent,
        "resolution_x": resolution_x,
        "resolution_y": resolution_y,
    }


def _download_coverage(
    wcs,
    extent,
    resolution_x,
    resolution_y,
    interpolation,
    filepath,
):
    """Download a buffered native-resolution WCS subset as GeoTIFF."""
    url = _wcs_url(
        wcs["parts"],
        (
            ("service", "WCS"),
            ("version", "1.0.0"),
            ("request", "GetCoverage"),
            ("coverage", wcs["coverage"]),
            ("crs", wcs["crs_name"]),
            (
                "bbox",
                "{:.12g},{:.12g},{:.12g},{:.12g}".format(
                    extent.xMinimum(),
                    extent.yMinimum(),
                    extent.xMaximum(),
                    extent.yMaximum(),
                ),
            ),
            ("resx", "{:.12g}".format(resolution_x)),
            ("resy", "{:.12g}".format(resolution_y)),
            ("interpolation", interpolation),
            ("format", "GeoTIFF"),
        ),
    )
    request = Request(url, headers={"User-Agent": "qgis2fds/2.0"})
    try:
        with _open_remote_request(request) as response:
            with open(filepath, "wb") as output:
                shutil.copyfileobj(response, output)
    except (HTTPError, URLError, OSError) as error:
        raise QgsProcessingException(
            "The WCS download for remote layer '{}' failed: {}".format(
                wcs["coverage"], error
            )
        )


def _coverage_service(layer):
    """Return the service URL and coverage name from a WMS or WCS URI."""
    source_options = {
        key.lower(): values
        for key, values in parse_qs(
            layer.source(), keep_blank_values=True
        ).items()
    }
    endpoint_values = source_options.get("url", ())
    coverage_values = next(
        (
            source_options[key]
            for key in ("coverage", "identifier", "layers")
            if source_options.get(key)
        ),
        (),
    )
    if (
        not endpoint_values
        or not coverage_values
        or "," in coverage_values[0]
    ):
        raise QgsProcessingException(
            "Remote layer '{}' cannot be converted to a raw numeric "
            "coverage. Use a numeric WCS or file-backed raster.".format(layer.name())
        )

    endpoint = endpoint_values[0]
    try:
        _validate_remote_url(endpoint)
    except URLError as error:
        raise QgsProcessingException(
            "Remote layer '{}' does not use a valid HTTP service.".format(
                layer.name()
            )
        ) from error
    parts = urlsplit(endpoint)
    return parts, _wcs_coverage_name(parts.path, coverage_values[0])


def _wcs_url(parts, parameters):
    """Build a WCS request while retaining non-service endpoint options."""
    existing_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower()
        not in {
            "bbox",
            "coverage",
            "crs",
            "format",
            "height",
            "interpolation",
            "resx",
            "resy",
            "request",
            "service",
            "version",
            "width",
        }
    ]
    query = existing_query + list(parameters)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), "")
    )


def _wcs_coverage_name(service_path, layer_name):
    """Convert a GeoServer WMS layer name to its WCS 1.0 coverage name."""
    if ":" in layer_name:
        return layer_name
    segments = [segment for segment in service_path.split("/") if segment]
    lowered = [segment.lower() for segment in segments]
    try:
        candidate = segments[lowered.index("geoserver") + 1]
    except (ValueError, IndexError):
        return layer_name
    if candidate.lower() in ("ows", "wcs", "wms"):
        return layer_name
    return "{}:{}".format(candidate, layer_name)


def _grid_rectangle(grid):
    """Return the terrain grid bounds as a QGIS rectangle."""
    return QgsRectangle(grid.x_min, grid.y_min, grid.x_max, grid.y_max)
