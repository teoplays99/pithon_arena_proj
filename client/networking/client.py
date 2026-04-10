"""Minimal TCP client for initial server integration."""

from __future__ import annotations

import socket
from typing import Any

from common import message_types
from common.protocol import make_message, receive_message, send_message


class ArenaClient:
    """Small client wrapper around the shared protocol."""

    def __init__(self) -> None:
        self._socket: socket.socket | None = None

    def connect(self, host: str, port: int) -> None:
        self._socket = socket.create_connection((host, port))

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def login(self, username: str, chat_port: int | None = None) -> dict[str, Any]:
        if self._socket is None:
            raise RuntimeError("Client is not connected.")
        payload: dict[str, Any] = {"username": username}
        if chat_port is not None:
            payload["chat_port"] = chat_port
        send_message(self._socket, make_message(message_types.LOGIN, payload))
        return receive_message(self._socket)

    def receive(self) -> dict[str, Any]:
        if self._socket is None:
            raise RuntimeError("Client is not connected.")
        return receive_message(self._socket)

    def send(self, message_type: str, payload: dict[str, Any] | None = None) -> None:
        if self._socket is None:
            raise RuntimeError("Client is not connected.")
        send_message(self._socket, make_message(message_type, payload or {}))
