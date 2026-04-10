"""Minimal Pygame frontend for the backend demo protocol."""

from __future__ import annotations

import queue
import threading
from typing import Any

from client.networking.client import ArenaClient
from client.state.controller import apply_server_message
from client.state.models import ClientAppState
from common import message_types
from common.constants import DEFAULT_HOST, DEFAULT_PORT


WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
CELL_SIZE = 24
BOARD_OFFSET_X = 40
BOARD_OFFSET_Y = 80


def challengeable_users(state: ClientAppState) -> list[str]:
    """Return online users that can be challenged from the lobby."""
    return [username for username in state.online_users if username and username != state.username]


def default_login_form(
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    chat_port: int | None = None,
) -> dict[str, str]:
    """Build the initial login form values shown in the client UI."""
    return {
        "host": host or DEFAULT_HOST,
        "port": str(port if port is not None else DEFAULT_PORT),
        "username": username or "",
        "chat_port": "" if chat_port is None else str(chat_port),
    }


def run_pygame_client(
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    chat_port: int | None = None,
) -> None:
    """Run the minimal client UI. Pygame import is deferred for environments without it."""
    try:
        import pygame
    except ModuleNotFoundError as exc:
        raise RuntimeError("pygame is not installed in this environment.") from exc

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Python Arena Client")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    small_font = pygame.font.SysFont(None, 22)

    client = ArenaClient()
    state = ClientAppState()
    inbound: queue.Queue[dict[str, Any]] = queue.Queue()
    running = True
    receiver_thread: threading.Thread | None = None
    form = default_login_form(host, port, username, chat_port)
    login_stage = "connect"
    active_field_index = 0

    def receiver() -> None:
        while True:
            try:
                inbound.put(client.receive())
            except Exception:
                return

    def submit_login() -> None:
        nonlocal receiver_thread, login_stage, active_field_index
        state.last_error = None
        if login_stage == "connect":
            typed_host = form["host"].strip() or DEFAULT_HOST
            try:
                typed_port = int(form["port"].strip() or str(DEFAULT_PORT))
            except ValueError:
                state.last_error = "Port must be a number."
                return

            form["host"] = typed_host
            form["port"] = str(typed_port)
            client.close()
            try:
                client.connect(typed_host, typed_port)
            except Exception as exc:
                state.last_error = str(exc)
                client.close()
                return

            login_stage = "username"
            active_field_index = 0
            return

        typed_username = form["username"].strip()
        if not typed_username:
            state.last_error = "Username is required."
            return

        typed_chat_port: int | None = None
        if form["chat_port"].strip():
            try:
                typed_chat_port = int(form["chat_port"].strip())
            except ValueError:
                state.last_error = "Chat port must be a number."
                return

        try:
            response = client.login(typed_username, chat_port=typed_chat_port)
            apply_server_message(state, response)
        except Exception as exc:
            state.phase = "login"
            state.last_error = str(exc)
            client.close()
            login_stage = "connect"
            active_field_index = 0
            return

        if state.phase == "lobby":
            form["username"] = typed_username
            form["chat_port"] = "" if typed_chat_port is None else str(typed_chat_port)
            if receiver_thread is None or not receiver_thread.is_alive():
                receiver_thread = threading.Thread(target=receiver, daemon=True)
                receiver_thread.start()

    try:
        while running:
            while True:
                try:
                    message = inbound.get_nowait()
                except queue.Empty:
                    break
                apply_server_message(state, message)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    active_field_index = _handle_keydown(
                        client,
                        state,
                        pygame,
                        event,
                        form,
                        login_stage,
                        active_field_index,
                        submit_login,
                    )
                    if state.phase == "login" and not state.username and client._socket is None:
                        login_stage = "connect"

            screen.fill((20, 24, 32))
            _draw_ui(pygame, screen, font, small_font, state, form, login_stage, active_field_index)
            pygame.display.flip()
            clock.tick(30)
    finally:
        client.close()
        pygame.quit()


def _handle_keydown(
    client: ArenaClient,
    state: ClientAppState,
    pygame: Any,
    event: Any,
    form: dict[str, str],
    login_stage: str,
    active_field_index: int,
    submit_login: Any,
) -> int:
    """Map keys to protocol actions."""
    key = event.key
    if state.phase == "login":
        form_fields = ["host", "port"] if login_stage == "connect" else ["username"]
        if key == pygame.K_TAB:
            return (active_field_index + 1) % len(form_fields)
        if key == pygame.K_UP:
            return (active_field_index - 1) % len(form_fields)
        if key == pygame.K_DOWN:
            return (active_field_index + 1) % len(form_fields)
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            submit_login()
            return 0
        if key == pygame.K_ESCAPE and login_stage == "username":
            client.close()
            return 0
        field_name = form_fields[active_field_index]
        if key == pygame.K_BACKSPACE:
            form[field_name] = form[field_name][:-1]
            return active_field_index
        if event.unicode and event.unicode.isprintable():
            form[field_name] += event.unicode
        return active_field_index

    if state.phase == "match":
        key_map = {
            pygame.K_UP: "UP",
            pygame.K_DOWN: "DOWN",
            pygame.K_LEFT: "LEFT",
            pygame.K_RIGHT: "RIGHT",
        }
        direction = key_map.get(key)
        if direction is not None:
            client.send(message_types.INPUT, {"direction": direction})
            return

    if key == pygame.K_w and state.phase == "lobby":
        client.send(message_types.WAITING, {})
    elif key == pygame.K_a and state.phase == "lobby" and state.challenger_username:
        client.send(message_types.CHALLENGE_ACCEPT, {"challenger_username": state.challenger_username})
    elif key == pygame.K_s and state.phase == "lobby":
        client.send(message_types.WATCH_MATCH, {})
    elif key == pygame.K_c and state.phase in {"lobby", "match"}:
        client.send(message_types.CHEER, {"text": "Let's go!"})
    elif key in (pygame.K_UP, pygame.K_DOWN) and state.phase == "lobby":
        users = challengeable_users(state)
        if not users:
            state.selected_lobby_index = 0
            return
        step = -1 if key == pygame.K_UP else 1
        state.selected_lobby_index = (state.selected_lobby_index + step) % len(users)
    elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and state.phase == "lobby":
        users = challengeable_users(state)
        if not users:
            return active_field_index
        selected = users[state.selected_lobby_index % len(users)]
        client.send(message_types.CHALLENGE_PLAYER, {"target_username": selected})
    return active_field_index


def _draw_ui(
    pygame: Any,
    screen: Any,
    font: Any,
    small_font: Any,
    state: ClientAppState,
    form: dict[str, str],
    login_stage: str,
    active_field_index: int,
) -> None:
    """Render the current frontend state."""
    _draw_text(screen, font, f"User: {state.username or 'Not logged in'}", 20, 20)
    if state.last_error:
        _draw_text(screen, small_font, f"Error: {state.last_error}", 20, 48, color=(255, 120, 120))

    if state.phase == "login":
        _draw_login(screen, pygame, font, small_font, form, login_stage, active_field_index)
    elif state.phase == "lobby":
        _draw_lobby(screen, font, small_font, state)
    elif state.phase in {"match", "game_over"}:
        _draw_match(screen, pygame, font, small_font, state)
    else:
        _draw_text(screen, font, "Connecting...", 20, 90)


def _draw_login(
    screen: Any,
    pygame: Any,
    font: Any,
    small_font: Any,
    form: dict[str, str],
    login_stage: str,
    active_field_index: int,
) -> None:
    if login_stage == "connect":
        title = "Connect To Server"
        hint = "Tab or Up/Down changes field. Enter continues."
        form_fields = ["host", "port"]
        labels = {
            "host": "Host",
            "port": "Port",
        }
    else:
        title = "Choose Username"
        hint = "Type your username and press Enter. Esc goes back."
        form_fields = ["username"]
        labels = {
            "username": "Username",
        }

    _draw_text(screen, font, title, 20, 90)
    _draw_text(screen, small_font, hint, 20, 120)
    y = 180
    for index, field_name in enumerate(form_fields):
        is_active = index == active_field_index
        box = pygame.Rect(260, y - 6, 280, 34)
        border = (255, 220, 120) if is_active else (120, 126, 148)
        fill = (34, 38, 50) if is_active else (28, 32, 42)
        _draw_text(screen, small_font, labels[field_name], 40, y)
        pygame.draw.rect(screen, fill, box)
        pygame.draw.rect(screen, border, box, 2)
        _draw_text(screen, small_font, form[field_name] or "", 272, y)
        y += 60

    if login_stage == "connect":
        _draw_text(screen, small_font, "After connecting, the client will ask for your username.", 40, 360)
    else:
        _draw_text(screen, small_font, f"Connected to {form['host']}:{form['port']}", 40, 300)


def _draw_lobby(screen: Any, font: Any, small_font: Any, state: ClientAppState) -> None:
    _draw_text(screen, font, "Lobby", 20, 90)
    _draw_text(screen, small_font, "Keys: Up/Down select, Enter challenge, W wait, A accept, S spectate", 20, 120)
    y = 170
    _draw_text(screen, small_font, "Online users:", 20, y)
    users = challengeable_users(state)
    if not users:
        state.selected_lobby_index = 0
    for index, username in enumerate(users):
        y += 26
        waiting_tag = " (waiting)" if username in state.waiting_players else ""
        prefix = ">" if index == (state.selected_lobby_index % len(users)) else "-"
        _draw_text(screen, small_font, f"{prefix} {username}{waiting_tag}", 40, y)

    if not users:
        y += 26
        _draw_text(screen, small_font, "No other online players available yet.", 40, y)

    if state.challenger_username:
        _draw_text(screen, small_font, f"Incoming challenge from: {state.challenger_username}", 420, 170)
    if state.outgoing_challenge_target:
        _draw_text(screen, small_font, f"Outgoing challenge to: {state.outgoing_challenge_target}", 420, 200)


def _draw_match(screen: Any, pygame: Any, font: Any, small_font: Any, state: ClientAppState) -> None:
    match = state.match_state or {}
    board = match.get("board", {"width": 30, "height": 20})
    snakes = match.get("snakes", {})
    pies = match.get("pies", [])
    obstacles = match.get("obstacles", [])

    _draw_text(screen, font, "Spectator Mode" if state.spectator else "Match", 20, 90)
    _draw_text(screen, small_font, "Arrow keys move. C sends a cheer.", 20, 120)
    _draw_text(screen, small_font, f"Remaining ticks: {match.get('remaining_ticks', 0)}", 20, 148)

    board_rect = pygame.Rect(
        BOARD_OFFSET_X,
        BOARD_OFFSET_Y,
        int(board["width"]) * CELL_SIZE,
        int(board["height"]) * CELL_SIZE,
    )
    pygame.draw.rect(screen, (40, 44, 56), board_rect)
    pygame.draw.rect(screen, (120, 126, 148), board_rect, 2)

    for obstacle in obstacles:
        _draw_cell(pygame, screen, obstacle[0], obstacle[1], (110, 110, 110))
    for pie in pies:
        color = (80, 200, 120) if pie.get("kind") == "green" else (220, 190, 70)
        _draw_cell(pygame, screen, pie["x"], pie["y"], color)

    snake_colors = [(70, 160, 255), (255, 120, 120)]
    for color, (username, snake) in zip(snake_colors, snakes.items()):
        for segment in snake.get("body", []):
            _draw_cell(pygame, screen, segment[0], segment[1], color)

    info_y = 170
    for username, snake in snakes.items():
        _draw_text(screen, small_font, f"{username}: health {snake.get('health', 0)}", 780, info_y)
        info_y += 26

    cheers = match.get("cheers", [])
    if cheers:
        _draw_text(screen, small_font, "Cheers:", 780, 280)
        y = 306
        for cheer in cheers[-5:]:
            _draw_text(screen, small_font, f"{cheer['from']}: {cheer['text']}", 780, y)
            y += 22

    if state.phase == "game_over" and state.game_over:
        winner = state.game_over.get("winner")
        reason = state.game_over.get("state", {}).get("reason")
        _draw_text(screen, font, f"Game Over - Winner: {winner}", 20, 580, color=(255, 220, 120))
        if reason:
            _draw_text(screen, small_font, f"Reason: {reason}", 420, 580, color=(255, 220, 120))


def _draw_cell(pygame: Any, screen: Any, x: int, y: int, color: tuple[int, int, int]) -> None:
    rect = pygame.Rect(
        BOARD_OFFSET_X + x * CELL_SIZE,
        BOARD_OFFSET_Y + y * CELL_SIZE,
        CELL_SIZE - 1,
        CELL_SIZE - 1,
    )
    pygame.draw.rect(screen, color, rect)


def _draw_text(screen: Any, font: Any, text: str, x: int, y: int, color: tuple[int, int, int] = (230, 234, 244)) -> None:
    surface = font.render(text, True, color)
    screen.blit(surface, (x, y))
