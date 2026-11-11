"""Unit tests for the monitor (B1-B16 in docs/enhancement-plan.md).

Importing this package makes the repository root importable and, only when the
real packages are not installed, registers tiny stand-ins for third-party
modules that ``env.audit`` imports at module load (``croniter``, ``codetiming``,
``yaml``).  When the real packages are installed they are used untouched.
"""
import importlib
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _missing(name):
    try:
        importlib.import_module(name)
        return False
    except ImportError:
        return True


if _missing("croniter"):
    mod = types.ModuleType("croniter")

    class croniter:  # noqa: N801 - mimic the real name
        def __init__(self, *a, **k):
            raise RuntimeError("croniter stub: install croniter to test cron schedules")

    mod.croniter = croniter
    sys.modules["croniter"] = mod

if _missing("codetiming"):
    mod = types.ModuleType("codetiming")

    class Timer:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    mod.Timer = Timer
    sys.modules["codetiming"] = mod

if _missing("yaml"):
    sys.modules["yaml"] = types.ModuleType("yaml")
