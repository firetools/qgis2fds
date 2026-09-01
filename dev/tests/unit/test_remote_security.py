"""Security boundaries for remote WCS input."""

import importlib
from pathlib import Path
import sys
from types import ModuleType
from urllib.error import URLError
from urllib.request import Request

import pytest


REMOTE_SOURCE = Path(__file__).resolve().parents[3] / "source" / "remote.py"


@pytest.fixture
def remote_module(monkeypatch):
    """Import the remote module with the small QGIS surface it needs."""

    class DataType:
        Byte = 1
        Int8 = 2
        UInt16 = 3
        Int16 = 4
        UInt32 = 5
        Int32 = 6
        Float32 = 7
        Float64 = 8
        ARGB32 = 9
        ARGB32_Premultiplied = 10

    class Qgis:
        pass

    Qgis.DataType = DataType

    class QgsProcessingException(Exception):
        pass

    class QXmlStreamReader:
        class TokenType:
            Characters = "characters"
            DTD = "dtd"
            EntityReference = "entity"

    core = ModuleType("qgis.core")
    core.Qgis = Qgis
    core.QgsProcessingException = QgsProcessingException
    core.__getattr__ = lambda _name: object
    qt_core = ModuleType("qgis.PyQt.QtCore")
    qt_core.QXmlStreamReader = QXmlStreamReader
    pyqt = ModuleType("qgis.PyQt")
    pyqt.QtCore = qt_core
    qgis = ModuleType("qgis")
    qgis.PyQt = pyqt
    qgis.core = core
    monkeypatch.setitem(sys.modules, "qgis", qgis)
    monkeypatch.setitem(sys.modules, "qgis.PyQt", pyqt)
    monkeypatch.setitem(sys.modules, "qgis.PyQt.QtCore", qt_core)
    monkeypatch.setitem(sys.modules, "qgis.core", core)
    sys.modules.pop("source.remote", None)
    module = importlib.import_module("source.remote")
    yield module
    sys.modules.pop("source.remote", None)


def _fake_reader(events, error=""):
    """Build a scripted QXmlStreamReader replacement."""

    class Attributes(dict):
        def value(self, name):
            return self.get(name, "")

    class Reader:
        class TokenType:
            Characters = "characters"
            DTD = "dtd"
            EntityReference = "entity"

        def __init__(self, _data):
            self.index = 0
            self.event = (None, "", "", {})

        def atEnd(self):
            return self.index >= len(events)

        def readNext(self):
            self.event = events[self.index]
            self.index += 1
            return self.event[0]

        def isStartElement(self):
            return self.event[0] == "start"

        def isEndElement(self):
            return self.event[0] == "end"

        def name(self):
            return self.event[1]

        def text(self):
            return self.event[2]

        def attributes(self):
            return Attributes(self.event[3])

        def hasError(self):
            return bool(error)

        def errorString(self):
            return error

    return Reader


def test_remote_source_uses_qt_streaming_xml():
    source = REMOTE_SOURCE.read_text(encoding="utf-8")

    assert "QXmlStreamReader" in source


def test_streaming_parser_extracts_required_wcs_fields(remote_module, monkeypatch):
    events = [
        ("start", "Envelope", "", {"srsName": "EPSG:32610"}),
        ("start", "pos", "", {}),
        ("characters", "", "500000 4100000", {}),
        ("end", "pos", "", {}),
        ("start", "pos", "", {}),
        ("characters", "", "500200 4100100", {}),
        ("end", "pos", "", {}),
        ("end", "Envelope", "", {}),
        ("start", "RectifiedGrid", "", {"srsName": "EPSG:32610"}),
        ("start", "offsetVector", "", {}),
        ("characters", "", "10 0", {}),
        ("end", "offsetVector", "", {}),
        ("start", "offsetVector", "", {}),
        ("characters", "", "0 -10", {}),
        ("end", "offsetVector", "", {}),
        ("end", "RectifiedGrid", "", {}),
    ]
    monkeypatch.setattr(remote_module, "QXmlStreamReader", _fake_reader(events))

    assert remote_module._parse_coverage_xml(b"ignored") == (
        True,
        "EPSG:32610",
        [[10.0, 0.0], [0.0, -10.0]],
        [
            (
                "EPSG:32610",
                [[500000.0, 4100000.0], [500200.0, 4100100.0]],
            )
        ],
    )


@pytest.mark.parametrize("token", ("dtd", "entity"))
def test_streaming_parser_rejects_dtds_and_entities(
    remote_module,
    monkeypatch,
    token,
):
    monkeypatch.setattr(
        remote_module,
        "QXmlStreamReader",
        _fake_reader([(token, "", "", {})]),
    )

    with pytest.raises(remote_module.RemoteXmlError, match="DTDs or entities"):
        remote_module._parse_coverage_xml(b"ignored")


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/passwd",
        "ftp://example.test/coverage",
        "custom://example.test/coverage",
        "//example.test/coverage",
        "https:///missing-host",
        "http://@/missing-host",
    ),
)
def test_remote_url_rejects_non_http_or_incomplete_urls(remote_module, url):
    with pytest.raises(URLError, match="HTTP or HTTPS"):
        remote_module._validate_remote_url(url)


@pytest.mark.parametrize(
    "url",
    ("http://example.test/coverage", "https://example.test/coverage"),
)
def test_remote_url_allows_http_and_https(remote_module, url):
    remote_module._validate_remote_url(url)


def test_remote_redirect_rejects_file_scheme(remote_module):
    handler = remote_module._RemoteRedirectHandler()

    with pytest.raises(URLError, match="HTTP or HTTPS"):
        handler.redirect_request(
            Request("https://example.test/coverage"),
            None,
            302,
            "Found",
            {},
            "file:///etc/passwd",
        )
