"""Session model for connected clients."""

from __future__ import annotations

from dataclasses import dataclass
import socket


@dataclass
class UserSession:
    """Represents one connected client."""

    address: tuple[str, int]
    socket: socket.socket
    username: str | None = None
    chat_host: str | None = None
    chat_port: int | None = None
    snake_color: str | None = None
