"""Length-prefixed JSON protocol helpers."""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

from common.constants import MAX_MESSAGE_SIZE


class ProtocolError(ValueError):
    """Raised when a message violates the expected protocol."""


def make_message(message_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a normalized protocol message."""
    if not message_type:
        raise ProtocolError("Message type is required.")
    return {"type": message_type, "payload": payload or {}}


def encode_message(message: dict[str, Any]) -> bytes:
    """Serialize a message into a length-prefixed byte payload."""
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a dictionary.")
    if not message.get("type"):
        raise ProtocolError("Message must include a non-empty 'type'.")
    if "payload" not in message:
        raise ProtocolError("Message must include 'payload'.")

    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Message exceeds maximum allowed size.")
    return struct.pack("!I", len(body)) + body


def decode_message(data: bytes) -> dict[str, Any]:
    """Decode a JSON message body without the length prefix."""
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Invalid message encoding.") from exc

    if not isinstance(message, dict):
        raise ProtocolError("Decoded message must be a dictionary.")
    if not message.get("type"):
        raise ProtocolError("Decoded message must include a non-empty 'type'.")
    if "payload" not in message or not isinstance(message["payload"], dict):
        raise ProtocolError("Decoded message must include a dictionary 'payload'.")
    return message


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Receive exactly size bytes or raise ConnectionError."""
    buffer = bytearray()
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Socket closed during receive.")
        buffer.extend(chunk)
    return bytes(buffer)


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    """Encode and send a single protocol message."""
    sock.sendall(encode_message(message))


def receive_message(sock: socket.socket) -> dict[str, Any]:
    """Read one length-prefixed message from a socket."""
    header = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", header)
    if length <= 0 or length > MAX_MESSAGE_SIZE:
        raise ProtocolError("Invalid message length.")
    body = recv_exact(sock, length)
    return decode_message(body)
