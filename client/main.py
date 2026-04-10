"""Minimal client CLI for early connectivity testing."""

from __future__ import annotations

import argparse

from client.networking.client import ArenaClient
from client.ui.pygame_client import run_pygame_client
from common.constants import DEFAULT_HOST, DEFAULT_PORT
from common.protocol import ProtocolError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect a Python Arena client.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Server port.")
    parser.add_argument("--username", help="Username to register.")
    parser.add_argument(
        "--mode",
        choices=("cli", "pygame"),
        default="pygame",
        help="Run the simple CLI smoke client or the minimal pygame frontend.",
    )
    parser.add_argument(
        "--chat-port",
        type=int,
        default=None,
        help="Local peer-chat listener port to advertise to the server.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "pygame":
        run_pygame_client(args.host, args.port, args.username, chat_port=args.chat_port)
        return
    if not args.username:
        parser.error("--username is required in cli mode")

    client = ArenaClient()
    try:
        client.connect(args.host, args.port)
        login_response = client.login(args.username, chat_port=args.chat_port)
        print(login_response)
        try:
            print(client.receive())
        except (ConnectionError, ProtocolError):
            pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
