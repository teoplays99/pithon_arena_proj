"""Minimal Pygame frontend for the backend demo protocol."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from client.networking.client import ArenaClient
from client.state.controller import apply_server_message, return_to_lobby
from client.state.models import ClientAppState
from common import message_types
from common.constants import DEFAULT_HOST, DEFAULT_PORT, SERVER_TICK_RATE, SNAKE_COLOR_PRESETS


WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
CELL_SIZE = 18
RIGHT_PANEL_WIDTH = 180
TOP_PANEL_HEIGHT = 120
BOARD_OFFSET_X = 20
BOARD_OFFSET_Y = TOP_PANEL_HEIGHT + 20
BACKGROUND_COLOR = (0, 0, 0)
PANEL_COLOR = (0, 0, 0)
BOARD_COLOR = (40, 44, 56)
BOARD_BORDER = (120, 126, 148)
NEON_BLUE = (0, 214, 255)
NEON_PINK = (255, 60, 190)
NEON_GREEN = (57, 255, 20)
NEON_ORANGE = (255, 140, 0)
NEON_PURPLE = (170, 0, 255)
NEON_YELLOW = (255, 240, 0)
NEON_RED = (255, 40, 40)
TEXT_COLOR = (236, 236, 236)
FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Monocraft.ttc"
LOBBY_TITLE_FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Geet-Regular.ttf"
LOBBY_LEFT_WIDTH = int(WINDOW_WIDTH * 0.67)
LOBBY_PADDING_X = 36
LOBBY_TITLE_Y = 54
LOBBY_LIST_Y = 154
LOBBY_BUTTON_Y = 420
LOBBY_BUTTON_WIDTH = 140
LOBBY_BUTTON_HEIGHT = 46
LOBBY_BUTTON_GAP = 18
INVITE_NOTICE_DURATION_MS = 1500
INVITE_NOTICE_FLICKER_INTERVAL_MS = 250
TITLE_FONT_SIZE = 52
SETTINGS_PREVIEW_CELL_SIZE = 28
SETTINGS_PREVIEW_COLS = 10
SETTINGS_PREVIEW_ROWS = 8
SETTINGS_LEFT_X = 40
SETTINGS_TOP_Y = 120
SETTINGS_PREVIEW_X = 560
SETTINGS_PREVIEW_Y = 150
SETTINGS_FIELDS = ["SNAKE_COLOR", "UP", "LEFT", "DOWN", "RIGHT", "BACK"]
CHEER_COOLDOWN_MS = 1000


def challengeable_users(state: ClientAppState) -> list[str]:
    """Return online users that can be challenged from the lobby."""
    return [username for username in state.online_users if username and username != state.username]


def snake_color_rgb(color_name: str) -> tuple[int, int, int]:
    """Map a preset snake color name to its neon RGB value."""
    palette = {
        "pink": NEON_PINK,
        "blue": NEON_BLUE,
        "green": NEON_GREEN,
        "orange": NEON_ORANGE,
        "purple": NEON_PURPLE,
        "yellow": NEON_YELLOW,
        "red": NEON_RED,
    }
    return palette.get(color_name, NEON_PINK)


def lighten_color(color: tuple[int, int, int], amount: int = 55) -> tuple[int, int, int]:
    """Return a lighter shade for snake heads."""
    return tuple(min(255, channel + amount) for channel in color)


def snake_head_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return a brighter head shade with stronger contrast for green/yellow snakes."""
    if color in {NEON_GREEN, NEON_YELLOW}:
        return lighten_color(color, 110)
    return lighten_color(color, 70)


def remaining_seconds(match_state: dict[str, Any]) -> int:
    """Convert server ticks into display seconds."""
    ticks = int(match_state.get("remaining_ticks", 0))
    return max(0, (ticks + SERVER_TICK_RATE - 1) // SERVER_TICK_RATE)


def should_render_snake(snake: dict[str, Any]) -> bool:
    """Blink stunned snakes twice during the collision freeze."""
    return int(snake.get("stun_ticks_remaining", 0)) not in {5, 3}


def invite_notice_color(elapsed_ms: int) -> tuple[int, int, int]:
    """Alternate invite error colors for the short-lived lobby notice."""
    return NEON_PINK if (elapsed_ms // INVITE_NOTICE_FLICKER_INTERVAL_MS) % 2 == 0 else NEON_BLUE


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


def key_name(key_code: int) -> str:
    """Return a readable label for a configured pygame key code."""
    key_labels = {
        1073741906: "UP",
        1073741905: "DOWN",
        1073741904: "LEFT",
        1073741903: "RIGHT",
    }
    return key_labels.get(key_code, chr(key_code).upper() if 32 <= key_code < 127 else str(key_code))


def move_preview_snake(state: ClientAppState, direction: str) -> None:
    """Move the settings preview snake one cell without damage."""
    offsets = {
        "UP": (0, -1),
        "DOWN": (0, 1),
        "LEFT": (-1, 0),
        "RIGHT": (1, 0),
    }
    dx, dy = offsets[direction]
    head_x, head_y = state.preview_body[0]
    next_head = ((head_x + dx) % SETTINGS_PREVIEW_COLS, (head_y + dy) % SETTINGS_PREVIEW_ROWS)
    state.preview_body = [next_head] + state.preview_body[:-1]
    state.preview_direction = direction


def cycle_snake_color(current: str, step: int) -> str:
    """Return the next configured snake color preset."""
    index = SNAKE_COLOR_PRESETS.index(current) if current in SNAKE_COLOR_PRESETS else 0
    return SNAKE_COLOR_PRESETS[(index + step) % len(SNAKE_COLOR_PRESETS)]


def cheer_allowed(last_sent_ms: int | None, now_ms: int, cooldown_ms: int = CHEER_COOLDOWN_MS) -> bool:
    """Return whether enough time has passed to send another cheer."""
    return last_sent_ms is None or (now_ms - last_sent_ms) >= cooldown_ms


def cheer_target_username(match_state: dict[str, Any] | None, player_index: int) -> str | None:
    """Return the username of the left/right displayed player."""
    snakes = list(((match_state or {}).get("snakes") or {}).keys())
    if 0 <= player_index < len(snakes):
        return str(snakes[player_index])
    return None


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
    font = pygame.font.Font(str(FONT_PATH), 24)
    small_font = pygame.font.Font(str(FONT_PATH), 18)
    lobby_title_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), TITLE_FONT_SIZE)
    lobby_button_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), 22)
    user_label_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), 16)
    player_name_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), 20)
    lobby_player_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), 22)
    settings_label_font = pygame.font.Font(str(LOBBY_TITLE_FONT_PATH), 24)

    client = ArenaClient()
    state = ClientAppState()
    inbound: queue.Queue[dict[str, Any]] = queue.Queue()
    running = True
    receiver_thread: threading.Thread | None = None
    lobby_notice: dict[str, object] = {"message": None, "started_ms": 0}
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
            client.send(message_types.SETTINGS_UPDATE, {"snake_color": state.snake_color_name})
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
                if message["type"] == message_types.MATCH_START:
                    if state.countdown_seconds > 0:
                        state.countdown_end_ms = pygame.time.get_ticks() + (state.countdown_seconds * 1000)
                if state.phase == "lobby" and state.last_error:
                    lobby_notice["message"] = state.last_error
                    lobby_notice["started_ms"] = pygame.time.get_ticks()
                    state.last_error = None

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
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    _handle_mouse_click(client, state, pygame, event.pos)

            screen.fill(BACKGROUND_COLOR)
            _draw_ui(
                pygame,
                screen,
                font,
                small_font,
                lobby_title_font,
                lobby_button_font,
                user_label_font,
                player_name_font,
                lobby_player_font,
                settings_label_font,
                state,
                form,
                login_stage,
                active_field_index,
                lobby_notice,
            )
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

    if state.phase == "settings":
        if state.rebinding_direction is not None:
            if key == pygame.K_ESCAPE:
                state.rebinding_direction = None
                return active_field_index
            state.movement_keys[state.rebinding_direction] = key
            state.rebinding_direction = None
            return active_field_index

        for direction, configured_key in state.movement_keys.items():
            if key == configured_key:
                move_preview_snake(state, direction)
                return active_field_index

        if key == pygame.K_ESCAPE:
            return_to_lobby(state)
            return active_field_index
        if key == pygame.K_UP:
            state.settings_field_index = (state.settings_field_index - 1) % len(SETTINGS_FIELDS)
            return active_field_index
        if key == pygame.K_DOWN:
            state.settings_field_index = (state.settings_field_index + 1) % len(SETTINGS_FIELDS)
            return active_field_index
        if SETTINGS_FIELDS[state.settings_field_index] == "SNAKE_COLOR" and key in (pygame.K_LEFT, pygame.K_RIGHT):
            step = -1 if key == pygame.K_LEFT else 1
            state.snake_color_name = cycle_snake_color(state.snake_color_name, step)
            client.send(message_types.SETTINGS_UPDATE, {"snake_color": state.snake_color_name})
            return active_field_index
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            field = SETTINGS_FIELDS[state.settings_field_index]
            if field == "BACK":
                return_to_lobby(state)
            elif field in {"UP", "LEFT", "DOWN", "RIGHT"}:
                state.rebinding_direction = field
            return active_field_index
        return active_field_index

    if state.phase == "match":
        for direction, configured_key in state.movement_keys.items():
            if key == configured_key:
                client.send(message_types.INPUT, {"direction": direction})
                return active_field_index
        if key == pygame.K_1:
            now_ms = pygame.time.get_ticks()
            if not cheer_allowed(state.last_cheer_sent_ms, now_ms):
                return active_field_index
            target = cheer_target_username(state.match_state, 0)
            if target is not None:
                client.send(message_types.CHEER, {"text": f"Cheer for {target}", "target_username": target})
                state.last_cheer_sent_ms = now_ms
            return active_field_index
        if key == pygame.K_2:
            now_ms = pygame.time.get_ticks()
            if not cheer_allowed(state.last_cheer_sent_ms, now_ms):
                return active_field_index
            target = cheer_target_username(state.match_state, 1)
            if target is not None:
                client.send(message_types.CHEER, {"text": f"Cheer for {target}", "target_username": target})
                state.last_cheer_sent_ms = now_ms
            return active_field_index

    if key == pygame.K_a and state.phase == "lobby" and state.challenger_username:
        client.send(message_types.CHALLENGE_ACCEPT, {"challenger_username": state.challenger_username})
    elif key == pygame.K_w and state.phase == "lobby":
        client.send(message_types.WATCH_MATCH, {})
    elif key == pygame.K_c and state.phase == "lobby":
        client.send(message_types.CHEER, {"text": "Let's go!"})
    elif key == pygame.K_s and state.phase == "lobby":
        state.phase = "settings"
    elif key == pygame.K_l and state.phase == "game_over":
        return_to_lobby(state)
    elif key in (pygame.K_UP, pygame.K_DOWN) and state.phase == "lobby":
        users = challengeable_users(state)
        if not users:
            state.selected_lobby_index = 0
            return active_field_index
        step = -1 if key == pygame.K_UP else 1
        state.selected_lobby_index = (state.selected_lobby_index + step) % len(users)
    elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and state.phase == "lobby":
        if not _invite_enabled(state):
            return active_field_index
        users = challengeable_users(state)
        selected = users[state.selected_lobby_index % len(users)]
        client.send(message_types.CHALLENGE_PLAYER, {"target_username": selected})
    return active_field_index


def _draw_ui(
    pygame: Any,
    screen: Any,
    font: Any,
    small_font: Any,
    lobby_title_font: Any,
    lobby_button_font: Any,
    user_label_font: Any,
    player_name_font: Any,
    lobby_player_font: Any,
    settings_label_font: Any,
    state: ClientAppState,
    form: dict[str, str],
    login_stage: str,
    active_field_index: int,
    lobby_notice: dict[str, object],
) -> None:
    """Render the current frontend state."""
    _draw_panels(pygame, screen)
    if state.last_error and state.phase != "lobby":
        _draw_text(screen, small_font, f"Error: {state.last_error}", 20, 50, color=(255, 120, 120))

    if state.phase == "login":
        _draw_login(screen, pygame, small_font, lobby_title_font, form, login_stage, active_field_index)
    elif state.phase == "lobby":
        _draw_lobby(screen, pygame, font, small_font, lobby_title_font, lobby_button_font, lobby_player_font, state, lobby_notice)
    elif state.phase == "settings":
        _draw_settings(screen, pygame, font, small_font, lobby_title_font, settings_label_font, lobby_button_font, state)
    elif state.phase == "match":
        _draw_match(screen, pygame, font, small_font, player_name_font, state)
    elif state.phase == "game_over":
        _draw_game_over(screen, lobby_title_font, font, small_font, state)
    else:
        _draw_text(screen, font, "Connecting...", 20, 90)
    _draw_user_label(screen, user_label_font, state)


def _draw_panels(pygame: Any, screen: Any) -> None:
    pygame.draw.rect(screen, PANEL_COLOR, pygame.Rect(0, 0, WINDOW_WIDTH - RIGHT_PANEL_WIDTH, TOP_PANEL_HEIGHT))
    pygame.draw.rect(screen, PANEL_COLOR, pygame.Rect(WINDOW_WIDTH - RIGHT_PANEL_WIDTH, 0, RIGHT_PANEL_WIDTH, WINDOW_HEIGHT))


def _draw_login(
    screen: Any,
    pygame: Any,
    small_font: Any,
    title_font: Any,
    form: dict[str, str],
    login_stage: str,
    active_field_index: int,
) -> None:
    if login_stage == "connect":
        title = "Connect To Server"
        hint = "Tab or Up/Down changes field. Enter continues."
        form_fields = ["host", "port"]
        labels = {"host": "Host", "port": "Port"}
    else:
        title = "Choose Username"
        hint = "Type your username and press Enter. Esc goes back."
        form_fields = ["username"]
        labels = {"username": "Username"}

    _draw_text(screen, title_font, title, 20, 74)
    _draw_text(screen, small_font, hint, 20, 134)
    y = 180
    for index, field_name in enumerate(form_fields):
        is_active = index == active_field_index
        box = pygame.Rect(260, y - 6, 280, 34)
        border = NEON_PINK if is_active else BOARD_BORDER
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


def _draw_lobby(
    screen: Any,
    pygame: Any,
    font: Any,
    small_font: Any,
    lobby_title_font: Any,
    lobby_button_font: Any,
    lobby_player_font: Any,
    state: ClientAppState,
    lobby_notice: dict[str, object],
) -> None:
    _draw_text(screen, lobby_title_font, "PITHON ARENA", LOBBY_PADDING_X, LOBBY_TITLE_Y)
    _draw_text(screen, font, "ONLINE PLAYERS", LOBBY_PADDING_X, LOBBY_LIST_Y - 44)
    y = LOBBY_LIST_Y
    users = challengeable_users(state)
    selected_y = LOBBY_LIST_Y + 30
    if not users:
        state.selected_lobby_index = 0
    for index, username in enumerate(users):
        y += 30
        waiting_tag = " (waiting)" if username in state.waiting_players else ""
        is_selected = index == (state.selected_lobby_index % len(users))
        prefix = ">" if is_selected else " "
        color = NEON_PINK if is_selected else TEXT_COLOR
        if index == (state.selected_lobby_index % len(users)):
            selected_y = y
        _draw_text(screen, small_font, prefix, LOBBY_PADDING_X, y + 2, color=color)
        _draw_text(screen, lobby_player_font, f"{username}{waiting_tag}", LOBBY_PADDING_X + 24, y, color=color)

    if not users:
        y += 30
        _draw_text(screen, small_font, "No other online players available yet.", LOBBY_PADDING_X, y)

    notice_message = lobby_notice.get("message")
    if isinstance(notice_message, str):
        elapsed_ms = int(pygame.time.get_ticks() - int(lobby_notice.get("started_ms", 0)))
        if elapsed_ms < INVITE_NOTICE_DURATION_MS:
            _draw_text(screen, small_font, notice_message, LOBBY_PADDING_X + 150, selected_y, color=invite_notice_color(elapsed_ms))
        else:
            lobby_notice["message"] = None

    if state.challenger_username:
        _draw_text(screen, small_font, f"Incoming invite from {state.challenger_username}", LOBBY_PADDING_X, y + 48)
    if state.outgoing_challenge_target:
        _draw_text(screen, small_font, f"Outgoing invite to {state.outgoing_challenge_target}", LOBBY_PADDING_X, y + 78)

    button_y = max(LOBBY_BUTTON_Y, y + 130)
    buttons = [
        ("INVITE", _invite_enabled(state)),
        ("ACCEPT", state.challenger_username is not None),
        ("WATCH", True),
        ("SETTINGS", True),
    ]
    button_x = LOBBY_PADDING_X
    for label, enabled in buttons:
        _draw_lobby_button(screen, pygame, lobby_button_font, label, button_x, button_y, enabled=enabled)
        button_x += LOBBY_BUTTON_WIDTH + LOBBY_BUTTON_GAP

    _draw_text(screen, small_font, "Up/Down select. Enter invite. A accept. W watch. S settings.", LOBBY_PADDING_X, button_y + LOBBY_BUTTON_HEIGHT + 28)


def _draw_settings(
    screen: Any,
    pygame: Any,
    font: Any,
    small_font: Any,
    title_font: Any,
    label_font: Any,
    button_font: Any,
    state: ClientAppState,
) -> None:
    _draw_text(screen, title_font, "GAME SETTINGS", SETTINGS_LEFT_X, 54)
    _draw_text(screen, small_font, "Esc or Back returns to lobby.", SETTINGS_LEFT_X, 92)
    color_selected = state.settings_field_index == 0
    _draw_text(screen, label_font, "SNAKE COLOR", SETTINGS_LEFT_X, SETTINGS_TOP_Y, color=NEON_PINK if color_selected else TEXT_COLOR)
    _draw_arrow_button(screen, pygame, font, "<", SETTINGS_LEFT_X, SETTINGS_TOP_Y + 42, color_selected)
    _draw_arrow_button(screen, pygame, font, ">", SETTINGS_LEFT_X + 250, SETTINGS_TOP_Y + 42, color_selected)
    color_name_surface = font.render(state.snake_color_name.upper(), True, snake_color_rgb(state.snake_color_name))
    color_name_x = SETTINGS_LEFT_X + 153 - (color_name_surface.get_width() // 2)
    screen.blit(color_name_surface, (color_name_x, SETTINGS_TOP_Y + 52))

    y = SETTINGS_TOP_Y + 120
    for index, direction in enumerate(["UP", "LEFT", "DOWN", "RIGHT"], start=1):
        selected = state.settings_field_index == index
        rebinding = state.rebinding_direction == direction
        _draw_setting_row(
            screen,
            pygame,
            label_font,
            small_font,
            direction,
            "PRESS KEY..." if rebinding else key_name(state.movement_keys[direction]),
            SETTINGS_LEFT_X,
            y,
            selected,
            rebinding,
        )
        y += 70

    back_selected = state.settings_field_index == len(SETTINGS_FIELDS) - 1
    _draw_lobby_button(screen, pygame, button_font, "BACK", SETTINGS_LEFT_X, y + 10, enabled=True)
    if back_selected:
        pygame.draw.rect(screen, NEON_BLUE, pygame.Rect(SETTINGS_LEFT_X - 4, y + 6, LOBBY_BUTTON_WIDTH + 8, LOBBY_BUTTON_HEIGHT + 8), 2)

    _draw_text(screen, label_font, "PREVIEW", SETTINGS_PREVIEW_X, SETTINGS_PREVIEW_Y - 42)
    _draw_preview_box(screen, pygame, state)
    _draw_text(screen, small_font, "Use your configured movement keys in the preview.", SETTINGS_PREVIEW_X, SETTINGS_PREVIEW_Y + SETTINGS_PREVIEW_ROWS * SETTINGS_PREVIEW_CELL_SIZE + 16)


def _draw_match(screen: Any, pygame: Any, font: Any, small_font: Any, player_name_font: Any, state: ClientAppState) -> None:
    match = state.match_state or {}
    board = match.get("board", {"width": 30, "height": 20})
    snakes = match.get("snakes", {})
    pies = match.get("pies", [])
    obstacles = match.get("obstacles", [])
    board_width_px = int(board["width"]) * CELL_SIZE

    board_rect = pygame.Rect(BOARD_OFFSET_X, BOARD_OFFSET_Y, board_width_px, int(board["height"]) * CELL_SIZE)
    pygame.draw.rect(screen, BOARD_COLOR, board_rect)
    pygame.draw.rect(screen, BOARD_BORDER, board_rect, 2)
    _draw_timer_display(screen, pygame, small_font, match, board_rect)

    for obstacle in obstacles:
        _draw_cell(pygame, screen, obstacle[0], obstacle[1], (110, 110, 110))
    for pie in pies:
        _draw_cell(pygame, screen, pie["x"], pie["y"], NEON_GREEN)

    for username, snake in snakes.items():
        fallback = "blue" if username != state.username else state.snake_color_name
        color = snake_color_rgb(str(snake.get("color") or fallback))
        if not should_render_snake(snake):
            continue
        body = snake.get("body", [])
        for segment in body[1:]:
            _draw_cell(pygame, screen, segment[0], segment[1], color)
        if body:
            _draw_cell(pygame, screen, body[0][0], body[0][1], snake_head_color(color))

    _draw_cheer_ripples(screen, pygame, match)

    players = list(snakes.items())
    if players:
        left_username, left_snake = players[0]
        _draw_player_status(screen, pygame, player_name_font, small_font, left_username, left_snake, BOARD_OFFSET_X, 22, snake_color_rgb(str(left_snake.get("color") or "blue")))
    if len(players) > 1:
        right_username, right_snake = players[1]
        _draw_player_status(screen, pygame, player_name_font, small_font, right_username, right_snake, BOARD_OFFSET_X + board_rect.width - 180, 22, snake_color_rgb(str(right_snake.get("color") or "pink")))

    cheers = match.get("cheers", [])
    _draw_text(screen, font, "Cheers", WINDOW_WIDTH - RIGHT_PANEL_WIDTH + 20, 20)
    if cheers:
        y = 60
        for cheer in cheers[-8:]:
            _draw_text(screen, small_font, f"{cheer['from']}: {cheer['text']}", WINDOW_WIDTH - RIGHT_PANEL_WIDTH + 20, y)
            y += 24
    else:
        _draw_text(screen, small_font, "No cheers yet.", WINDOW_WIDTH - RIGHT_PANEL_WIDTH + 20, 60)

    _draw_text(screen, small_font, "Move with your keys. 1 cheers left player. 2 cheers right player.", 20, WINDOW_HEIGHT - 40)
    _draw_match_countdown(screen, pygame, font, state)


def game_over_result_text(state: ClientAppState) -> str:
    """Return a personalized game-over headline."""
    game_over = state.game_over or {}
    winner = game_over.get("winner")
    if state.spectator:
        return f"{winner} won!" if winner else "It ended in a draw!"
    if winner is None:
        return "You tied."
    if winner == state.username:
        return "You won!"
    return "You lost."


def game_over_reason_text(reason: str | None) -> str:
    """Return a more human-friendly match-ending reason."""
    reason_map = {
        "health_zero": "Somebody ran out of snake juice.",
        "timer_end": "Time called. The healthier serpent survived.",
        "player_disconnected": "One snake vanished into the void.",
    }
    return reason_map.get(reason or "", "The arena has spoken.")


def _draw_game_over(screen: Any, title_font: Any, font: Any, small_font: Any, state: ClientAppState) -> None:
    game_over = state.game_over or {}
    winner = game_over.get("winner")
    reason = game_over.get("state", {}).get("reason") or game_over.get("reason")
    _draw_text(screen, title_font, "GAME OVER", 20, 96, color=NEON_PINK)
    _draw_text(screen, font, game_over_result_text(state), 20, 180, color=NEON_PINK)
    if state.spectator and winner is not None:
        _draw_text(screen, small_font, f"Winner: {winner}", 20, 228, color=TEXT_COLOR)
        reason_y = 268
    else:
        reason_y = 228
    _draw_text(screen, small_font, game_over_reason_text(reason), 20, reason_y, color=TEXT_COLOR)
    _draw_text(screen, small_font, "Press L to return to lobby.", 20, reason_y + 60, color=TEXT_COLOR)


def _draw_match_countdown(screen: Any, pygame: Any, font: Any, state: ClientAppState) -> None:
    if not state.countdown_end_ms:
        return
    remaining_ms = state.countdown_end_ms - pygame.time.get_ticks()
    if remaining_ms <= 0:
        state.countdown_end_ms = None
        return
    remaining = max(1, (remaining_ms + 999) // 1000)
    text_surface = font.render(str(remaining), True, NEON_PINK)
    x = BOARD_OFFSET_X + ((30 * CELL_SIZE) // 2) - (text_surface.get_width() // 2)
    y = BOARD_OFFSET_Y + ((20 * CELL_SIZE) // 2) - (text_surface.get_height() // 2)
    screen.blit(text_surface, (x, y))


def _draw_timer_display(screen: Any, pygame: Any, font: Any, match: dict[str, Any], board_rect: Any) -> None:
    total_ticks = max(1, int(match.get("duration_ticks", SERVER_TICK_RATE * 60)))
    remaining_ticks = int(match.get("remaining_ticks", 0))
    remaining = remaining_seconds(match)
    bar_width = 150
    bar_height = 14
    bar_x = BOARD_OFFSET_X + (board_rect.width // 2) - (bar_width // 2)
    bar_y = 28
    pygame.draw.rect(screen, (36, 36, 36), pygame.Rect(bar_x, bar_y, bar_width, bar_height))
    fill_width = max(0, min(bar_width, int(bar_width * (remaining_ticks / total_ticks))))
    pygame.draw.rect(screen, NEON_PINK, pygame.Rect(bar_x, bar_y, fill_width, bar_height))
    pygame.draw.rect(screen, BOARD_BORDER, pygame.Rect(bar_x, bar_y, bar_width, bar_height), 2)
    label = font.render(f"{remaining}s", True, TEXT_COLOR)
    label_x = BOARD_OFFSET_X + (board_rect.width // 2) - (label.get_width() // 2)
    screen.blit(label, (label_x, bar_y + bar_height + 6))


def _draw_cheer_ripples(screen: Any, pygame: Any, match: dict[str, Any]) -> None:
    ripples = match.get("cheer_ripples", [])
    if not ripples:
        return
    obstacle_cells = {tuple(cell) for cell in match.get("obstacles", [])}
    for ripple in ripples:
        color = snake_color_rgb(str(ripple.get("color") or "pink"))
        for cell_x, cell_y in ripple.get("cells", []):
            if (cell_x, cell_y) in obstacle_cells:
                continue
            _draw_cell(pygame, screen, int(cell_x), int(cell_y), color)


def _draw_player_status(
    screen: Any,
    pygame: Any,
    name_font: Any,
    font: Any,
    username: str,
    snake: dict[str, Any],
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    _draw_text(screen, name_font, username, x, y, color=color)
    _draw_health_bar(screen, pygame, x, y + 28, 160, 16, int(snake.get("health", 0)), color)
    _draw_text(screen, font, f"Health {snake.get('health', 0)}", x, y + 52)


def _draw_lobby_button(
    screen: Any,
    pygame: Any,
    font: Any,
    label: str,
    x: int,
    y: int,
    enabled: bool,
) -> None:
    rect = pygame.Rect(x, y, LOBBY_BUTTON_WIDTH, LOBBY_BUTTON_HEIGHT)
    border_color = NEON_PINK if enabled else (120, 80, 110)
    fill_color = (40, 8, 28) if enabled else (20, 20, 20)
    pygame.draw.rect(screen, fill_color, rect)
    pygame.draw.rect(screen, border_color, rect, 2)
    text_color = TEXT_COLOR if enabled else (150, 150, 150)
    text_surface = font.render(label, True, text_color)
    screen.blit(text_surface, text_surface.get_rect(center=rect.center))


def _draw_arrow_button(screen: Any, pygame: Any, font: Any, label: str, x: int, y: int, selected: bool) -> None:
    rect = pygame.Rect(x, y, 56, 44)
    pygame.draw.rect(screen, (40, 8, 28), rect)
    pygame.draw.rect(screen, NEON_PINK if selected else BOARD_BORDER, rect, 2)
    text_surface = font.render(label, True, TEXT_COLOR)
    screen.blit(text_surface, text_surface.get_rect(center=rect.center))


def _draw_setting_row(
    screen: Any,
    pygame: Any,
    label_font: Any,
    value_font: Any,
    direction: str,
    value_label: str,
    x: int,
    y: int,
    selected: bool,
    rebinding: bool,
) -> None:
    _draw_text(screen, label_font, direction, x, y, color=NEON_PINK if selected else TEXT_COLOR)
    box = pygame.Rect(x, y + 28, 230, 38)
    pygame.draw.rect(screen, (26, 26, 26), box)
    pygame.draw.rect(screen, NEON_BLUE if rebinding else (NEON_PINK if selected else BOARD_BORDER), box, 2)
    _draw_text(screen, value_font, value_label, x + 12, y + 36)


def _draw_preview_box(screen: Any, pygame: Any, state: ClientAppState) -> None:
    preview_rect = pygame.Rect(
        SETTINGS_PREVIEW_X,
        SETTINGS_PREVIEW_Y,
        SETTINGS_PREVIEW_COLS * SETTINGS_PREVIEW_CELL_SIZE,
        SETTINGS_PREVIEW_ROWS * SETTINGS_PREVIEW_CELL_SIZE,
    )
    pygame.draw.rect(screen, BOARD_COLOR, preview_rect)
    pygame.draw.rect(screen, BOARD_BORDER, preview_rect, 2)
    snake_color = snake_color_rgb(state.snake_color_name)
    for segment in state.preview_body[1:]:
        _draw_preview_cell(pygame, screen, segment[0], segment[1], snake_color)
    head = state.preview_body[0]
    _draw_preview_cell(pygame, screen, head[0], head[1], snake_head_color(snake_color))


def _draw_preview_cell(pygame: Any, screen: Any, x: int, y: int, color: tuple[int, int, int]) -> None:
    rect = pygame.Rect(
        SETTINGS_PREVIEW_X + x * SETTINGS_PREVIEW_CELL_SIZE,
        SETTINGS_PREVIEW_Y + y * SETTINGS_PREVIEW_CELL_SIZE,
        SETTINGS_PREVIEW_CELL_SIZE,
        SETTINGS_PREVIEW_CELL_SIZE,
    )
    pygame.draw.rect(screen, color, rect)


def _draw_user_label(screen: Any, font: Any, state: ClientAppState) -> None:
    username = state.username or "Not logged in"
    label_surface = font.render(f"USER {username}", True, snake_color_rgb(state.snake_color_name))
    x = WINDOW_WIDTH - 18 - label_surface.get_width()
    y = WINDOW_HEIGHT - 14 - label_surface.get_height()
    screen.blit(label_surface, (x, y))


def _invite_enabled(state: ClientAppState) -> bool:
    users = challengeable_users(state)
    if not users:
        return False
    selected = users[state.selected_lobby_index % len(users)]
    return state.challenger_username != selected


def _lobby_button_rect(label: str) -> tuple[int, int, int, int]:
    labels = ["INVITE", "ACCEPT", "WATCH", "SETTINGS"]
    index = labels.index(label)
    x = LOBBY_PADDING_X + index * (LOBBY_BUTTON_WIDTH + LOBBY_BUTTON_GAP)
    return (x, LOBBY_BUTTON_Y, LOBBY_BUTTON_WIDTH, LOBBY_BUTTON_HEIGHT)


def _handle_mouse_click(client: ArenaClient, state: ClientAppState, pygame: Any, position: tuple[int, int]) -> None:
    if state.phase == "lobby":
        x, y = position
        button_states = {
            "INVITE": _invite_enabled(state),
            "ACCEPT": state.challenger_username is not None,
            "WATCH": True,
            "SETTINGS": True,
        }
        for label, enabled in button_states.items():
            if not enabled:
                continue
            rect_x, rect_y, rect_w, rect_h = _lobby_button_rect(label)
            if rect_x <= x <= rect_x + rect_w and rect_y <= y <= rect_y + rect_h:
                if label == "INVITE":
                    users = challengeable_users(state)
                    if not users:
                        return
                    selected = users[state.selected_lobby_index % len(users)]
                    client.send(message_types.CHALLENGE_PLAYER, {"target_username": selected})
                elif label == "ACCEPT" and state.challenger_username:
                    client.send(message_types.CHALLENGE_ACCEPT, {"challenger_username": state.challenger_username})
                elif label == "WATCH":
                    client.send(message_types.WATCH_MATCH, {})
                elif label == "SETTINGS":
                    state.phase = "settings"
                return
        return

    if state.phase == "settings":
        _handle_settings_click(client, state, pygame, position)


def _handle_settings_click(client: ArenaClient, state: ClientAppState, pygame: Any, position: tuple[int, int]) -> None:
    x, y = position
    if SETTINGS_LEFT_X <= x <= SETTINGS_LEFT_X + 56 and SETTINGS_TOP_Y + 42 <= y <= SETTINGS_TOP_Y + 86:
        state.snake_color_name = cycle_snake_color(state.snake_color_name, -1)
        client.send(message_types.SETTINGS_UPDATE, {"snake_color": state.snake_color_name})
        state.settings_field_index = 0
        return
    if SETTINGS_LEFT_X + 250 <= x <= SETTINGS_LEFT_X + 306 and SETTINGS_TOP_Y + 42 <= y <= SETTINGS_TOP_Y + 86:
        state.snake_color_name = cycle_snake_color(state.snake_color_name, 1)
        client.send(message_types.SETTINGS_UPDATE, {"snake_color": state.snake_color_name})
        state.settings_field_index = 0
        return

    row_y = SETTINGS_TOP_Y + 120
    for index, direction in enumerate(["UP", "LEFT", "DOWN", "RIGHT"], start=1):
        rect = pygame.Rect(SETTINGS_LEFT_X, row_y + 28, 230, 38)
        if rect.collidepoint(x, y):
            state.settings_field_index = index
            state.rebinding_direction = direction
            return
        row_y += 70

    back_rect = pygame.Rect(SETTINGS_LEFT_X, row_y + 10, LOBBY_BUTTON_WIDTH, LOBBY_BUTTON_HEIGHT)
    if back_rect.collidepoint(x, y):
        state.settings_field_index = len(SETTINGS_FIELDS) - 1
        return_to_lobby(state)


def _draw_health_bar(
    screen: Any,
    pygame: Any,
    x: int,
    y: int,
    width: int,
    height: int,
    health: int,
    color: tuple[int, int, int],
) -> None:
    pygame.draw.rect(screen, (56, 60, 70), pygame.Rect(x, y, width, height))
    fill_width = max(0, min(width, int(width * (max(0, health) / 100))))
    pygame.draw.rect(screen, color, pygame.Rect(x, y, fill_width, height))
    pygame.draw.rect(screen, BOARD_BORDER, pygame.Rect(x, y, width, height), 2)


def _draw_cell(pygame: Any, screen: Any, x: int, y: int, color: tuple[int, int, int]) -> None:
    rect = pygame.Rect(BOARD_OFFSET_X + x * CELL_SIZE, BOARD_OFFSET_Y + y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
    pygame.draw.rect(screen, color, rect)


def _draw_text(screen: Any, font: Any, text: str, x: int, y: int, color: tuple[int, int, int] = TEXT_COLOR) -> None:
    surface = font.render(text, True, color)
    screen.blit(surface, (x, y))
