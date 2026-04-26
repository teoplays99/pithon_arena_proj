"""Lobby and matchmaking state for the single active match model."""

from __future__ import annotations

from time import monotonic
from threading import Lock


class LobbyManager:
    """Track waiting players and pending invites."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._waiting_players: set[str] = set()
        self._pending_challenges: dict[str, str] = {}
        self._pending_chat_requests: dict[str, dict[str, object]] = {}

    def set_waiting(self, username: str) -> None:
        """Mark a user as waiting for an opponent."""
        with self._lock:
            self._waiting_players.add(username)
            self._pending_challenges = {
                target: challenger
                for target, challenger in self._pending_challenges.items()
                if target != username and challenger != username
            }

    def clear_player(self, username: str) -> None:
        """Remove a player from waiting and invite state."""
        with self._lock:
            self._waiting_players.discard(username)
            self._pending_challenges.pop(username, None)
            self._pending_challenges = {
                target: challenger
                for target, challenger in self._pending_challenges.items()
                if challenger != username
            }
            self._pending_chat_requests.pop(username, None)
            self._pending_chat_requests = {
                target: request
                for target, request in self._pending_chat_requests.items()
                if request["requester_username"] != username
            }

    def clear_all_invites(self) -> None:
        """Remove every pending invite while leaving waiting players intact."""
        with self._lock:
            self._pending_challenges.clear()

    def _prune_expired_chat_requests_locked(self) -> list[dict[str, object]]:
        now = monotonic()
        expired: list[dict[str, object]] = []
        kept: dict[str, dict[str, object]] = {}
        for target, request in self._pending_chat_requests.items():
            if float(request["expires_at"]) <= now:
                expired.append(dict(request))
            else:
                kept[target] = request
        self._pending_chat_requests = kept
        return expired

    def issue_challenge(self, challenger: str, target: str, online_users: set[str]) -> tuple[bool, str]:
        """Create a pending invite between two online users."""
        with self._lock:
            if challenger == target:
                return False, "You cannot invite yourself."
            if target not in online_users:
                return False, "Target player is not online."
            if challenger not in online_users:
                return False, "Challenger is not online."
            if self._pending_challenges.get(challenger) == target:
                return False, "You already have a pending invite from this player."
            if target in self._pending_challenges:
                pending_challenger = self._pending_challenges[target]
                if pending_challenger == challenger:
                    return True, f"{challenger} invited {target}."
                return False, "Target player already has a pending invite."

            previous_target = None
            for pending_target, pending_challenger in self._pending_challenges.items():
                if pending_challenger == challenger:
                    previous_target = pending_target
                    break
            if previous_target is not None:
                self._pending_challenges.pop(previous_target, None)

            self._waiting_players.discard(challenger)
            self._pending_challenges[target] = challenger
            return True, f"{challenger} invited {target}."

    def accept_challenge(self, target: str, challenger: str) -> tuple[bool, str]:
        """Accept a pending invite if it matches the stored request."""
        with self._lock:
            pending_challenger = self._pending_challenges.get(target)
            if pending_challenger != challenger:
                return False, "No matching invite to accept."

            self._pending_challenges.pop(target, None)
            self._waiting_players.discard(target)
            self._waiting_players.discard(challenger)
            return True, "Invite accepted."

    def restore_challenge(self, target: str, challenger: str) -> None:
        """Restore an invite after a failed match start."""
        with self._lock:
            self._pending_challenges[target] = challenger

    def cancel_challenge(self, target: str, challenger: str) -> None:
        """Remove a specific pending invite if it still matches."""
        with self._lock:
            if self._pending_challenges.get(target) == challenger:
                self._pending_challenges.pop(target, None)

    def pending_challenger_for(self, target: str) -> str | None:
        """Return the pending challenger for a target player."""
        with self._lock:
            return self._pending_challenges.get(target)

    def pending_target_for(self, challenger: str) -> str | None:
        """Return the current pending target for a challenger, if any."""
        with self._lock:
            for target, pending_challenger in self._pending_challenges.items():
                if pending_challenger == challenger:
                    return target
            return None

    def is_waiting(self, username: str) -> bool:
        """Return whether a user is currently marked as waiting."""
        with self._lock:
            return username in self._waiting_players

    def waiting_players(self) -> list[str]:
        """Return waiting players sorted for display."""
        with self._lock:
            return sorted(self._waiting_players)

    def issue_chat_request(
        self,
        requester_username: str,
        target_username: str,
        requester_host: str,
        requester_port: int,
        online_users: set[str],
        ttl_seconds: int,
    ) -> tuple[bool, str, dict[str, object] | None]:
        """Store one pending chat request and replace any older outgoing one."""
        with self._lock:
            expired = self._prune_expired_chat_requests_locked()
            canceled: dict[str, object] | None = None
            if requester_username == target_username:
                return False, "You cannot chat with yourself.", None
            if requester_username not in online_users or target_username not in online_users:
                return False, "Both users must be online.", None
            if requester_port <= 0:
                return False, "Invalid chat port.", None
            existing_for_target = self._pending_chat_requests.get(target_username)
            if (
                existing_for_target is not None
                and existing_for_target["requester_username"] != requester_username
            ):
                return False, "Target player already has a pending chat request.", None

            for pending_target, request in list(self._pending_chat_requests.items()):
                if request["requester_username"] == requester_username:
                    canceled = dict(request)
                    self._pending_chat_requests.pop(pending_target, None)
                    break

            request = {
                "requester_username": requester_username,
                "target_username": target_username,
                "requester_host": requester_host,
                "requester_port": requester_port,
                "expires_at": monotonic() + ttl_seconds,
            }
            self._pending_chat_requests[target_username] = request
            if canceled is None and expired:
                canceled = expired[0]
            return True, "Chat request sent.", canceled

    def accept_chat_request(self, target_username: str, requester_username: str) -> tuple[bool, str, dict[str, object] | None]:
        """Accept a matching unexpired chat request."""
        with self._lock:
            self._prune_expired_chat_requests_locked()
            request = self._pending_chat_requests.get(target_username)
            if request is None or request["requester_username"] != requester_username:
                return False, "No matching chat request.", None
            self._pending_chat_requests.pop(target_username, None)
            return True, "Chat request accepted.", dict(request)

    def pending_chat_request_for(self, target_username: str) -> dict[str, object] | None:
        """Return the current pending chat request for one target."""
        with self._lock:
            self._prune_expired_chat_requests_locked()
            request = self._pending_chat_requests.get(target_username)
            return dict(request) if request is not None else None

    def expired_chat_requests(self) -> list[dict[str, object]]:
        """Remove and return all expired chat requests."""
        with self._lock:
            return self._prune_expired_chat_requests_locked()
