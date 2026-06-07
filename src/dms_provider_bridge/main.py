from __future__ import annotations

import argparse
from copy import deepcopy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from dms_provider_bridge.core.config_loader import load_config

HOST = "127.0.0.1"
PORT = 8765


def _uvicorn_stdout_log_config() -> dict[str, object]:
    log_config = deepcopy(LOGGING_CONFIG)
    handlers = log_config.get("handlers", {})
    if isinstance(handlers, dict):
        for handler_name in ("default", "access"):
            handler = handlers.get(handler_name)
            if isinstance(handler, dict):
                handler["stream"] = "ext://sys.stdout"
    return log_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start dms-provider-bridge service")
    parser.add_argument("--host", default=None, help="Override host")
    parser.add_argument("--port", type=int, default=None, help="Override port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    host = args.host or config.get("server", {}).get("host", HOST)
    port = args.port or config.get("server", {}).get("port", PORT)
    advertised_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::"} else str(host)
    base_url = f"http://{advertised_host}:{int(port)}"
    print("Starting bridge service...")
    print(f"Health: {base_url}/health")
    print(f"Swagger UI: {base_url}/docs")
    print(f"OpenAPI: {base_url}/openapi.json")
    uvicorn.run(
        "dms_provider_bridge.app.server:app",
        host=host,
        port=int(port),
        reload=False,
        log_config=_uvicorn_stdout_log_config(),
    )


if __name__ == "__main__":
    main()

