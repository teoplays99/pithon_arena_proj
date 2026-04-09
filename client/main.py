"""Minimal client CLI for early connectivity testing."""

from __future__ import annotations

import argparse

from client.networking.client import ArenaClient
from common.constants import DEFAULT_HOST, DEFAULT_PORT
from common.protocol import ProtocolError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect a Python Arena client.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Server port.")
    parser.add_argument("--username", required=True, help="Username to register.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = ArenaClient()
    try:
        client.connect(args.host, args.port)
        login_response = client.login(args.username)
        print(login_response)
        try:
            print(client.receive())
        except (ConnectionError, ProtocolError):
            pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
