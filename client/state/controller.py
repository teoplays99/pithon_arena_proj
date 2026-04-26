"""Client-side message reducer."""

from __future__ import annotations

from typing import Any

from client.state.models import ClientAppState
from common import message_types


def return_to_lobby(state: ClientAppState) -> ClientAppState:
    """Reset transient match UI state and show the lobby again."""
    state.phase = "lobby"
    state.match_state = None
    state.game_over = None
    state.spectator = False
    state.disconnected_player = None
    state.last_error = None
    state.last_cheer_sent_ms = None
    state.peer_chat_info = None
    state.incoming_chat_request = None
    state.outgoing_chat_request = None
    state.active_chat_peer = None
    state.chat_messages.clear()
    state.chat_input_text = ""
    return state


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
        pending_challenger = payload.get("pending_challenger")
        outgoing_target = payload.get("outgoing_challenge_target")
        state.challenger_username = str(pending_challenger) if pending_challenger else None
        state.outgoing_challenge_target = str(outgoing_target) if outgoing_target else None
        return state

    if message_type == message_types.WAITING:
        state.phase = "lobby"
        return state

    if message_type == message_types.SETTINGS_UPDATE:
        snake_color = payload.get("snake_color")
        if snake_color:
            state.snake_color_name = str(snake_color)
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
        state.countdown_seconds = int(payload.get("countdown_seconds", 0) or 0)
        state.countdown_end_ms = None
        state.last_cheer_sent_ms = None
        state.peer_chat_info = None
        state.incoming_chat_request = None
        state.outgoing_chat_request = None
        state.active_chat_peer = None
        state.chat_messages.clear()
        state.chat_input_text = ""
        state.game_over = None
        state.challenger_username = None
        state.outgoing_challenge_target = None
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
        state.active_chat_peer = str(payload.get("peer_username", "") or "") or None
        state.outgoing_chat_request = None
        incoming = state.incoming_chat_request or {}
        if incoming.get("requester_username") == state.active_chat_peer:
            state.incoming_chat_request = None
        state.chat_messages.clear()
        state.chat_input_text = ""
        return state

    if message_type == message_types.CHAT_REQUEST_SENT:
        state.outgoing_chat_request = dict(payload)
        return state

    if message_type == message_types.CHAT_REQUEST_RECEIVED:
        state.incoming_chat_request = dict(payload)
        if state.active_chat_peer is not None:
            state.last_error = str(payload.get("message", "Incoming chat request."))
        return state

    if message_type == message_types.CHAT_REQUEST_CANCELED:
        requester = str(payload.get("requester_username", "") or "")
        target = str(payload.get("target_username", "") or "")
        incoming = state.incoming_chat_request or {}
        if incoming.get("requester_username") == requester:
            state.incoming_chat_request = None
        outgoing = state.outgoing_chat_request or {}
        if outgoing.get("target_username") == target:
            state.outgoing_chat_request = None
        return state

    if message_type == message_types.ERROR:
        state.last_error = str(payload.get("message", "Unknown server error"))
        return state

    return state
