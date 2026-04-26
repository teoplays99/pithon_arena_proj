"""Serializable client-side state containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from common.constants import DEFAULT_CHAT_PORT


@dataclass
class ClientAppState:
    """Small state container for the minimal client UI."""

    username: str | None = None
    online_users: list[str] = field(default_factory=list)
    waiting_players: list[str] = field(default_factory=list)
    phase: str = "login"
    match_state: dict[str, Any] | None = None
    game_over: dict[str, Any] | None = None
    challenger_username: str | None = None
    outgoing_challenge_target: str | None = None
    spectator: bool = False
    peer_chat_info: dict[str, Any] | None = None
    incoming_chat_request: dict[str, Any] | None = None
    outgoing_chat_request: dict[str, Any] | None = None
    active_chat_peer: str | None = None
    chat_messages: list[dict[str, str]] = field(default_factory=list)
    chat_input_text: str = ""
    chat_input_active: bool = False
    chat_scroll_offset: int = 0
    chat_port: int = DEFAULT_CHAT_PORT
    last_error: str | None = None
    disconnected_player: str | None = None
    selected_lobby_index: int = 0
    snake_color_name: str = "pink"
    countdown_end_ms: int | None = None
    countdown_seconds: int = 0
    last_cheer_sent_ms: int | None = None
    movement_keys: dict[str, int] = field(
        default_factory=lambda: {
            "UP": 1073741906,
            "DOWN": 1073741905,
            "LEFT": 1073741904,
            "RIGHT": 1073741903,
        }
    )
    settings_field_index: int = 0
    rebinding_direction: str | None = None
    preview_body: list[tuple[int, int]] = field(default_factory=lambda: [(6, 4), (5, 4), (4, 4)])
    preview_direction: str = "RIGHT"
