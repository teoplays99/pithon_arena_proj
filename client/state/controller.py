"""Client-side message reducer."""

from __future__ import annotations

from typing import Any

from client.state.models import ClientAppState
from common import message_types


def apply_server_message(state: ClientAppState, message: dict[str, Any]) -> ClientAppState:
    """Mutate the lightweight app state according to one server message."""
    message_type = message["type"]
    payload = message["payload"]

    if message_type == message_types.LOGIN_OK:
        state.username = str(payload.get("username")) if payload.get("username") is not None else state.username
        state.phase = "lobby"
        state.last_error = None
        return state

    if message_type == message_types.LOGIN_REJECT:
        state.last_error = str(payload.get("message", "Login rejected"))
        state.phase = "login"
        return state

    if message_type == message_types.ONLINE_USERS:
        state.online_users = list(payload.get("users", []))
        state.waiting_players = list(payload.get("waiting_players", []))
        return state

    if message_type == message_types.WAITING:
        state.phase = "lobby"
        return state

    if message_type == message_types.CHALLENGE_RECEIVED:
        state.challenger_username = str(payload.get("challenger_username", ""))
        return state

    if message_type == message_types.CHALLENGE_PLAYER:
        state.outgoing_challenge_target = str(payload.get("target_username", ""))
        return state

    if message_type == message_types.MATCH_START:
        state.phase = "match"
        state.match_state = dict(payload.get("state", {}))
        state.spectator = bool(payload.get("spectator", False))
        state.game_over = None
        state.last_error = None
        return state

    if message_type == message_types.STATE_UPDATE:
        state.match_state = dict(payload)
        return state

    if message_type == message_types.GAME_OVER:
        state.game_over = dict(payload)
        state.phase = "game_over"
        return state

    if message_type == message_types.PLAYER_DISCONNECTED:
        state.disconnected_player = str(payload.get("username", ""))
        return state

    if message_type == message_types.CHAT_PEER_INFO:
        state.peer_chat_info = dict(payload)
        return state

    if message_type == message_types.ERROR:
        state.last_error = str(payload.get("message", "Unknown server error"))
        return state

    return state
