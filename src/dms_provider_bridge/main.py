from __future__ import annotations

import argparse

import uvicorn

from dms_provider_bridge.core.config_loader import load_config

HOST = "127.0.0.1"
PORT = 8765


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start edocat-bridge service")
    parser.add_argument("--host", default=None, help="Override host")
    parser.add_argument("--port", type=int, default=None, help="Override port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    host = args.host or config.get("server", {}).get("host", HOST)
    port = args.port or config.get("server", {}).get("port", PORT)
    uvicorn.run("dms_provider_bridge.app.server:app", host=host, port=int(port), reload=False)


if __name__ == "__main__":
    main()

