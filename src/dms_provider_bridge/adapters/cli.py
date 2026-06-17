from __future__ import annotations

import argparse

from dms_provider_bridge.services.listing_service import list_connection_items


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple CLI adapter for dms-provider-bridge")
    parser.add_argument("path", nargs="?", default="/", help="Path to list")
    parser.add_argument("--connection", default=None, help="Connection name to use when path has no connection prefix")
    parser.add_argument("--provider", default=None, help="Legacy alias for --connection")
    args = parser.parse_args()
    if args.provider and args.connection and args.provider.strip().lower().rstrip(":") != args.connection.strip().lower().rstrip(":"):
        parser.error("--provider does not match --connection")

    result = list_connection_items(path=args.path, connection_name=args.connection or args.provider)
    print(result.model_dump_json(indent=2))

