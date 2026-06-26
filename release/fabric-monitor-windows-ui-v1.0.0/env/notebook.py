from collections.abc import Mapping
from typing import Any

from env.config import build_audit, run_monitor


async def run(settings: Mapping[str, Any] | None = None) -> None:
    await run_monitor(settings=settings, load_env_file=False)


__all__ = ["build_audit", "run", "run_monitor"]
