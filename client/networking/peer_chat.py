"""Peer-to-peer chat transport used from the lobby."""

from __future__ import annotations

import queue
import socket
import threading
from typing import Any

from common.protocol import make_message, receive_message, send_message


PEER_CHAT_MESSAGE = "PEER_CHAT_MESSAGE"
PEER_CHAT_CONNECTED = "PEER_CHAT_CONNECTED"


class PeerChatService:
    """Owns one temporary listener and one active peer connection."""

    def __init__(self, inbound: queue.Queue[dict[str, Any]]) -> None:
        self._inbound = inbound
        self._listener: socket.socket | None = None
        self._listener_thread: threading.Thread | None = None
        self._peer_socket: socket.socket | None = None
        self._peer_lock = threading.Lock()
        self._running = threading.Event()
        self._running.set()
        self._listen_port: int | None = None

    @property
    def listen_port(self) -> int | None:
        return self._listen_port

    def start_listener(self, port: int = 0) -> int:
        if self._listener is not None and self._listen_port is not None:
            return self._listen_port
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self._listen_port = int(listener.getsockname()[1])
        self._running.set()
        self._listener_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._listener_thread.start()
        return self._listen_port

    def stop_listener(self) -> None:
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        self._listen_port = None

    def close_chat(self) -> None:
        with self._peer_lock:
            peer_socket = self._peer_socket
            self._peer_socket = None
        if peer_socket is not None:
            try:
                peer_socket.close()
            except OSError:
                pass

    def shutdown(self) -> None:
        self._running.clear()
        self.close_chat()
        self.stop_listener()

    def has_active_chat(self) -> bool:
        with self._peer_lock:
            return self._peer_socket is not None

    def connect_to(self, host: str, port: int) -> None:
        self._running.set()
        peer_socket = socket.create_connection((host, port), timeout=2.0)
        peer_socket.settimeout(None)
        self._adopt_peer_socket(peer_socket)

    def send_text(self, from_username: str, text: str) -> bool:
        with self._peer_lock:
            peer_socket = self._peer_socket
        if peer_socket is None:
            return False
        try:
            send_message(
                peer_socket,
                make_message(
                    PEER_CHAT_MESSAGE,
                    {
                        "from_username": from_username,
                        "text": text,
                    },
                ),
            )
            return True
        except OSError:
            self.close_chat()
            return False

    def _accept_loop(self) -> None:
        while self._running.is_set():
            listener = self._listener
            if listener is None:
                return
            try:
                peer_socket, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._adopt_peer_socket(peer_socket)

    def _adopt_peer_socket(self, peer_socket: socket.socket) -> None:
        peer_socket.settimeout(None)
        with self._peer_lock:
            old_peer = self._peer_socket
            self._peer_socket = peer_socket
        if old_peer is not None:
            try:
                old_peer.close()
            except OSError:
                pass
        self._inbound.put(make_message(PEER_CHAT_CONNECTED, {}))
        threading.Thread(target=self._receive_loop, args=(peer_socket,), daemon=True).start()

    def _receive_loop(self, peer_socket: socket.socket) -> None:
        try:
            while self._running.is_set():
                message = receive_message(peer_socket)
                if message.get("type") == PEER_CHAT_MESSAGE:
                    self._inbound.put(message)
        except Exception:
            pass
        finally:
            with self._peer_lock:
                if self._peer_socket is peer_socket:
                    self._peer_socket = None
            try:
                peer_socket.close()
            except OSError:
                pass
