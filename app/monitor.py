import argparse
import asyncio
import logging
import os
from collections.abc import Sequence


async def main(settings: dict | None = None, *, env_file: str | None = None):
    from env.config import build_audit

    audit = build_audit(settings=settings, load_env_file=True, env_file=env_file)

    logging.info("Starting Fabric Monitor run")
    await audit.run()
    logging.info("Fabric Monitor run complete")


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
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    asyncio.run(main(settings=overrides, env_file=args.env_file))


if __name__ == "__main__":
    cli()
