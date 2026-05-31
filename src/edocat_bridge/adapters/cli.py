from __future__ import annotations

import argparse

from edocat_bridge.services.listing_service import list_items


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple CLI adapter for edocat-bridge")
    parser.add_argument("path", nargs="?", default="/", help="Path to list")
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    result = list_items(path=args.path, provider_name=args.provider)
    print(result.model_dump_json(indent=2))
