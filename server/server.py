"""Threaded TCP server with login validation."""

from __future__ import annotations

import socket
import threading
import time

from common import message_types
from common.constants import SERVER_TICK_RATE
from common.protocol import ProtocolError, make_message, receive_message, send_message
from server.game import Match
from server.lobby_manager import LobbyManager
from server.persistence import MatchHistoryStore
from server.session import UserSession
from server.user_registry import UserRegistry


class PythonArenaServer:
    """Minimal server bootstrap for login and lobby presence."""

    def __init__(self, host: str, port: int, db_path: str = "python_arena.db") -> None:
        self.host = host
        self.port = port
        self.user_registry = UserRegistry()
        self.lobby_manager = LobbyManager()
        self.match_history = MatchHistoryStore(db_path=db_path)
        self.active_match: Match | None = None
        self._spectators: set[str] = set()
        self._spectator_lock = threading.Lock()
        self._match_thread: threading.Thread | None = None
        self._match_lock = threading.Lock()
        self._server_socket: socket.socket | None = None
        self._running = threading.Event()

    def start(self) -> None:
        """Bind and start accepting clients forever."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen()
        self._running.set()
        print(f"PythonArenaServer listening on {self.host}:{self.port}")

        try:
            while self._running.is_set():
                client_socket, address = self._server_socket.accept()
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address),
                    daemon=True,
                )
                thread.start()
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the server and close the listening socket."""
        self._running.clear()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            finally:
                self._server_socket = None

    def _safe_send(self, session: UserSession | None, message: dict[str, object]) -> bool:
        """Best-effort send that tolerates already-closed sockets."""
        if session is None:
            return False
        try:
            send_message(session.socket, message)
            return True
        except OSError:
            return False

    def add_spectator(self, username: str) -> None:
        with self._spectator_lock:
            self._spectators.add(username)

    def remove_spectator(self, username: str) -> None:
        with self._spectator_lock:
            self._spectators.discard(username)

    def get_spectators(self) -> list[str]:
        with self._spectator_lock:
            return sorted(self._spectators)

    def get_match_recipients(self, match: Match) -> list[str]:
        recipients = list(match.players)
        recipients.extend(username for username in self.get_spectators() if username not in match.players)
        return recipients

    def handle_client(self, client_socket: socket.socket, address: tuple[str, int]) -> None:
        """Handle the initial login flow for a client."""
        session = UserSession(address=address, socket=client_socket)
        try:
            login_message = receive_message(client_socket)
            if login_message["type"] != message_types.LOGIN:
                send_message(
                    client_socket,
                    make_message(
                        message_types.ERROR,
                        {"message": "Expected LOGIN as the first message."},
                    ),
                )
                return

            username = str(login_message["payload"].get("username", "")).strip()
            chat_port_raw = login_message["payload"].get("chat_port")
            if not self.user_registry.register(username, session):
                send_message(
                    client_socket,
                    make_message(
                        message_types.LOGIN_REJECT,
                        {"message": "Username is invalid or already in use."},
                    ),
                )
                return

            session.username = username
            if isinstance(chat_port_raw, int) and 1 <= chat_port_raw <= 65535:
                session.chat_port = chat_port_raw
            send_message(
                client_socket,
                make_message(
                    message_types.LOGIN_OK,
                    {
                        "username": username,
                        "online_users": self.user_registry.list_usernames(),
                        "chat_port": session.chat_port,
                    },
                ),
            )
            self.broadcast_online_users()

            while self._running.is_set():
                try:
                    message = receive_message(client_socket)
                except ConnectionError:
                    break
                except ProtocolError:
                    send_message(
                        client_socket,
                        make_message(message_types.ERROR, {"message": "Malformed request."}),
                    )
                    break

                if message["type"] == message_types.WAITING:
                    self.lobby_manager.set_waiting(username)
                    send_message(
                        client_socket,
                        make_message(
                            message_types.WAITING,
                            {
                                "message": "You are waiting for an opponent.",
                                "waiting_players": self.lobby_manager.waiting_players(),
                            },
                        ),
                    )
                    self.broadcast_online_users()
                elif message["type"] == message_types.CHALLENGE_PLAYER:
                    self.handle_challenge_player(session, message["payload"])
                elif message["type"] == message_types.CHALLENGE_ACCEPT:
                    self.handle_challenge_accept(session, message["payload"])
                elif message["type"] == message_types.INPUT:
                    self.handle_input(session, message["payload"])
                elif message["type"] == message_types.WATCH_MATCH:
                    self.handle_watch_match(session)
                elif message["type"] == message_types.CHEER:
                    self.handle_cheer(session, message["payload"])
                else:
                    send_message(
                        client_socket,
                        make_message(
                            message_types.ERROR,
                            {"message": f"Unsupported message type: {message['type']}"},
                        ),
                    )
        except (ConnectionError, ProtocolError):
            pass
        finally:
            if session.username:
                self.handle_player_disconnect(session.username)
                self.remove_spectator(session.username)
                self.lobby_manager.clear_player(session.username)
                self.user_registry.unregister(session.username)
                self.broadcast_online_users()
            client_socket.close()

    def broadcast_online_users(self) -> None:
        """Broadcast the current online/waiting list to all connected sessions."""
        usernames = self.user_registry.list_usernames()
        waiting_players = self.lobby_manager.waiting_players()
        for username in usernames:
            session = self.user_registry.get_session(username)
            if session is None:
                continue
            try:
                send_message(
                    session.socket,
                    make_message(
                        message_types.ONLINE_USERS,
                        {
                            "users": usernames,
                            "waiting_players": waiting_players,
                            "active_match": self.active_match.to_state_payload() if self.active_match else None,
                        },
                    ),
                )
            except OSError:
                continue

    def handle_challenge_player(self, session: UserSession, payload: dict[str, object]) -> None:
        """Handle a challenge request from one player to another."""
        if session.username is None:
            return

        target = str(payload.get("target_username", "")).strip()
        was_waiting = self.lobby_manager.is_waiting(session.username)
        success, message = self.lobby_manager.issue_challenge(
            session.username,
            target,
            set(self.user_registry.list_usernames()),
        )
        if not success:
            send_message(session.socket, make_message(message_types.ERROR, {"message": message}))
            return

        target_session = self.user_registry.get_session(target)
        delivered = self._safe_send(
            target_session,
            make_message(
                message_types.CHALLENGE_RECEIVED,
                {"challenger_username": session.username},
            ),
        )
        if not delivered:
            self.lobby_manager.cancel_challenge(target, session.username)
            if was_waiting:
                self.lobby_manager.set_waiting(session.username)
            send_message(
                session.socket,
                make_message(
                    message_types.ERROR,
                    {"message": "Target player is no longer reachable. Challenge was canceled."},
                ),
            )
            self.broadcast_online_users()
            return

        send_message(
            session.socket,
            make_message(
                message_types.CHALLENGE_PLAYER,
                {"target_username": target, "message": message},
            ),
        )
        self.broadcast_online_users()

    def handle_challenge_accept(self, session: UserSession, payload: dict[str, object]) -> None:
        """Handle challenge acceptance and announce the match start."""
        if session.username is None:
            return

        challenger = str(payload.get("challenger_username", "")).strip()
        with self._match_lock:
            match_running = self.active_match is not None and not self.active_match.game_over
        if match_running:
            error_message = "A match is already running. Wait for it to finish."
            self._safe_send(session, make_message(message_types.ERROR, {"message": error_message}))
            self._safe_send(
                self.user_registry.get_session(challenger),
                make_message(message_types.ERROR, {"message": error_message}),
            )
            return

        success, message = self.lobby_manager.accept_challenge(session.username, challenger)
        if not success:
            send_message(session.socket, make_message(message_types.ERROR, {"message": message}))
            return

        players = sorted([session.username, challenger])
        started, reason = self.start_match(players)
        if not started:
            if reason == "busy":
                self.lobby_manager.restore_challenge(session.username, challenger)
                error_message = "A match is already running. Wait for it to finish."
            else:
                error_message = "Both players must still be online to start the match."
            self._safe_send(session, make_message(message_types.ERROR, {"message": error_message}))
            self._safe_send(
                self.user_registry.get_session(challenger),
                make_message(message_types.ERROR, {"message": error_message}),
            )
        self.broadcast_online_users()

    def handle_input(self, session: UserSession, payload: dict[str, object]) -> None:
        """Queue a player's movement input for the active match."""
        if session.username is None:
            return
        with self._match_lock:
            match = self.active_match
            if match is None or session.username not in match.snakes:
                send_message(
                    session.socket,
                    make_message(message_types.ERROR, {"message": "You are not in an active match."}),
                )
                return
            direction = str(payload.get("direction", "")).strip().upper()
            if not match.queue_input(session.username, direction):
                send_message(
                    session.socket,
                    make_message(message_types.ERROR, {"message": "Invalid movement input."}),
                )
                return

    def handle_watch_match(self, session: UserSession) -> None:
        """Subscribe a user to the current active match as a spectator."""
        if session.username is None:
            return
        self.add_spectator(session.username)
        with self._match_lock:
            match = self.active_match
            state = match.to_state_payload() if match is not None else None

        self._safe_send(
            session,
            make_message(message_types.WATCH_MATCH, {"status": "subscribed"}),
        )
        if state is not None:
            self._safe_send(
                session,
                make_message(
                    message_types.MATCH_START,
                    {"players": state["players"], "state": state, "spectator": True},
                ),
            )

    def handle_cheer(self, session: UserSession, payload: dict[str, object]) -> None:
        """Append a cheer to the active match and broadcast the updated state."""
        if session.username is None:
            return
        text = str(payload.get("text", "")).strip()
        if not text:
            self._safe_send(session, make_message(message_types.ERROR, {"message": "Cheer text is required."}))
            return

        with self._match_lock:
            match = self.active_match
            if match is None:
                self._safe_send(session, make_message(message_types.ERROR, {"message": "No active match to cheer for."}))
                return
            match.add_cheer(session.username, text)
            state = match.to_state_payload()

        for username in self.get_match_recipients(match):
            self._safe_send(
                self.user_registry.get_session(username),
                make_message(message_types.STATE_UPDATE, state),
            )

    def start_match(self, players: list[str]) -> tuple[bool, str | None]:
        """Create and begin the single active match."""
        with self._match_lock:
            if self.active_match is not None and not self.active_match.game_over:
                return False, "busy"
            if any(self.user_registry.get_session(username) is None for username in players):
                return False, "offline"
            match = Match(players=players)
            self.active_match = match
            initial_state = match.to_state_payload()

        for username in players:
            target_session = self.user_registry.get_session(username)
            self.remove_spectator(username)
            self._safe_send(
                target_session,
                make_message(
                    message_types.MATCH_START,
                    {"players": players, "state": initial_state, "spectator": False},
                ),
            )
        self._send_chat_peer_info(players)
        for spectator in self.get_spectators():
            if spectator in players:
                continue
            self._safe_send(
                self.user_registry.get_session(spectator),
                make_message(
                    message_types.MATCH_START,
                    {"players": players, "state": initial_state, "spectator": True},
                ),
            )

        self._match_thread = threading.Thread(target=self.run_match_loop, args=(match,), daemon=True)
        self._match_thread.start()
        return True, None

    def _send_chat_peer_info(self, players: list[str]) -> None:
        if len(players) != 2:
            return
        first = self.user_registry.get_session(players[0])
        second = self.user_registry.get_session(players[1])
        if first is None or second is None:
            return
        if first.chat_port is None or second.chat_port is None:
            return
        self._safe_send(
            first,
            make_message(
                message_types.CHAT_PEER_INFO,
                {
                    "peer_username": players[1],
                    "peer_host": second.address[0],
                    "peer_port": second.chat_port,
                },
            ),
        )
        self._safe_send(
            second,
            make_message(
                message_types.CHAT_PEER_INFO,
                {
                    "peer_username": players[0],
                    "peer_host": first.address[0],
                    "peer_port": first.chat_port,
                },
            ),
        )

    def run_match_loop(self, owned_match: Match) -> None:
        """Run the authoritative state update loop for the active match."""
        tick_interval = 1 / SERVER_TICK_RATE
        while self._running.is_set():
            with self._match_lock:
                match = self.active_match
                if match is None or match is not owned_match:
                    return
                state = match.tick()
                players = list(match.players)
                game_over = match.game_over

            for username in players:
                self._safe_send(self.user_registry.get_session(username), make_message(message_types.STATE_UPDATE, state))
            for spectator in self.get_spectators():
                if spectator in players:
                    continue
                self._safe_send(self.user_registry.get_session(spectator), make_message(message_types.STATE_UPDATE, state))

            if game_over:
                for username in players:
                    self._safe_send(
                        self.user_registry.get_session(username),
                        make_message(
                            message_types.GAME_OVER,
                            {"winner": state["winner"], "state": state},
                        ),
                    )
                for spectator in self.get_spectators():
                    if spectator in players:
                        continue
                    self._safe_send(
                        self.user_registry.get_session(spectator),
                        make_message(
                            message_types.GAME_OVER,
                            {"winner": state["winner"], "state": state},
                        ),
                    )
                self.match_history.save_match(state)
                with self._match_lock:
                    if self.active_match is owned_match:
                        self.active_match = None
                self.broadcast_online_users()
                return

            time.sleep(tick_interval)

    def handle_player_disconnect(self, username: str) -> None:
        """Terminate the active match if one of its players disconnects."""
        with self._match_lock:
            match = self.active_match
            if match is None or username not in match.players or match.game_over:
                return
            state = match.end_due_to_disconnect(username)
            players = list(match.players)
            self.active_match = None

        remaining_players = [player for player in players if player != username]
        spectator_names = [spectator for spectator in self.get_spectators() if spectator not in players]

        for remaining_username in remaining_players:
            session = self.user_registry.get_session(remaining_username)
            self._safe_send(
                session,
                make_message(
                    message_types.PLAYER_DISCONNECTED,
                    {"username": username, "winner": state["winner"]},
                ),
            )
            self._safe_send(
                session,
                make_message(
                    message_types.GAME_OVER,
                    {"winner": state["winner"], "state": state},
                ),
            )
        for spectator in spectator_names:
            session = self.user_registry.get_session(spectator)
            self._safe_send(
                session,
                make_message(
                    message_types.PLAYER_DISCONNECTED,
                    {"username": username, "winner": state["winner"]},
                ),
            )
            self._safe_send(
                session,
                make_message(
                    message_types.GAME_OVER,
                    {"winner": state["winner"], "state": state},
                ),
            )
        self.match_history.save_match(state)
