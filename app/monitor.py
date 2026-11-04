import argparse
import asyncio
import logging
import os
from collections.abc import Sequence

from env import config
from env.audit import Audits
from env.version import get_version

logger = logging.getLogger(__name__)
_resolve_local_output_path = config._resolve_local_output_path
_COMMERCIAL_ALIASES = {
    "TENANT_ID": "COMMERCIAL_TENANT_ID",
    "CLIENT_ID": "COMMERCIAL_CLIENT_ID",
    "CLIENT_SECRET": "COMMERCIAL_CLIENT_SECRET",
}


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


def _get_env(*names: str) -> str:
    if (
        os.environ.get("LOCAL_OUTPUT_PATH")
        and names
        and names[0] in _COMMERCIAL_ALIASES
    ):
        names = (_COMMERCIAL_ALIASES[names[0]], *names)
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise KeyError(names[0])


async def main(settings: dict | None = None, *, env_file: str | None = None):
    audit = config.build_audit(
        settings=settings,
        load_env_file=settings is not None or env_file is not None,
        env_file=env_file,
        audit=Audits(),
    )

    logger.info("Starting Fabric Monitor run (version %s)", get_version())
    if await audit.run() is False:
        raise RuntimeError("Fabric Monitor run failed; see module and storage errors.")
    logger.info("Fabric Monitor run complete")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Fabric Monitor application.")
    parser.add_argument(
        "--base",
        action="store_true",
        help="Run catalog in full workspace scan mode for this execution.",
    )
    parser.add_argument(
        "--modules",
        help="Comma-separated module list to run for this execution.",
    )
    parser.add_argument(
        "--profile",
        help="Path to a JSON profile containing monitor configuration values.",
    )
    parser.add_argument(
        "--env-file",
        help="Path to a .env file. Defaults to .env in the current directory when omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print blob writes instead of writing to Blob Storage.",
    )
    parser.add_argument(
        "--cloud-environment",
        choices=("Commercial", "Gcc", "GccHigh", "Dod"),
        help="Cloud endpoint profile to use for this execution.",
    )
    return parser.parse_args(argv)


def cli(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    overrides = {}
    if args.profile:
        from env.config import load_profile

        overrides.update(load_profile(args.profile))
    if args.base:
        overrides["ALL_WORKSPACES"] = True
    if args.modules:
        overrides["APPLICATION_MODULES"] = args.modules
    if args.cloud_environment:
        overrides["CLOUD_ENVIRONMENT"] = args.cloud_environment
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    asyncio.run(main(settings=overrides, env_file=args.env_file))


if __name__ == "__main__":
    cli()
