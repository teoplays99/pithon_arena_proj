"""CLI entrypoint for the Python Arena server."""

from __future__ import annotations

import argparse

from common.constants import DEFAULT_HOST, DEFAULT_PORT
from server.server import PythonArenaServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Python Arena server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host/IP to bind the server to.")
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=int,
        help="Port to listen on.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = PythonArenaServer(host=args.host, port=args.port)
    server.start()


if __name__ == "__main__":
    main()
