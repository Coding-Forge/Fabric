"""Single source of truth for the Fabric Monitor version."""

from pathlib import Path

UNKNOWN_VERSION = "unknown"
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def get_version() -> str:
    """Return the monitor version from the ``VERSION`` file in the repo root.

    No network access is performed.

    :return: The version string with surrounding whitespace removed, or
        ``"unknown"`` if the file is missing, unreadable or empty.
    """
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return UNKNOWN_VERSION
    return text or UNKNOWN_VERSION
