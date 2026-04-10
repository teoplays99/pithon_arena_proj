"""CLI entrypoint for the Python Arena server."""

from __future__ import annotations

import argparse

from common.constants import DEFAULT_PORT
from server.server import PythonArenaServer


DEFAULT_BIND_HOST = "0.0.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Python Arena server.")
    parser.add_argument(
        "port",
        nargs="?",
        default=None,
        type=int,
        help="Port to listen on.",
    )
    parser.add_argument("--host", default=DEFAULT_BIND_HOST, help="Host/IP to bind the server to.")
    parser.add_argument(
        "--port",
        dest="port_flag",
        default=None,
        type=int,
        help="Port to listen on.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    port = args.port if args.port is not None else args.port_flag
    if port is None:
        port = DEFAULT_PORT
    server = PythonArenaServer(host=args.host, port=port)
    server.start()


if __name__ == "__main__":
    main()
