import pathlib
from importlib.metadata import version

import xmlstreamer_ng

# The surface the README documents: it must stay exported.
DOCUMENTED_API = {
    "ApiKeyAuth",
    "BasicAuth",
    "BearerAuth",
    "DigestAuth",
    "FeedInterruptedError",
    "FeedRun",
    "Nested",
    "Raw",
    "Sections",
    "StreamInterpreter",
    "Transport",
    "UnsupportedSchemeError",
    "XMLStreamerError",
    "to_nested",
}


def test_version_matches_distribution_metadata():
    assert xmlstreamer_ng.__version__ == version("xmlstreamer-ng")


def test_all_names_exist():
    for name in xmlstreamer_ng.__all__:
        assert hasattr(xmlstreamer_ng, name), name


def test_documented_api_is_exported():
    assert DOCUMENTED_API <= set(xmlstreamer_ng.__all__)


def test_py_typed_marker_ships_with_the_package():
    package_dir = pathlib.Path(xmlstreamer_ng.__file__).parent
    assert (package_dir / "py.typed").is_file()
