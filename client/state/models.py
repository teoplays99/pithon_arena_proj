"""Serializable client-side state containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    last_error: str | None = None
    disconnected_player: str | None = None
    selected_lobby_index: int = 0
    snake_color_name: str = "pink"
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
