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
