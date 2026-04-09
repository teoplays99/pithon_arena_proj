"""Thread-safe username/session tracking."""

from __future__ import annotations

from threading import Lock


class UserRegistry:
    """Store connected usernames and their associated sessions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, object] = {}

    def register(self, username: str, session: object) -> bool:
        """Register a username if it is not already active."""
        cleaned = username.strip()
        if not cleaned:
            return False

        with self._lock:
            if cleaned in self._sessions:
                return False
            self._sessions[cleaned] = session
            return True

    def unregister(self, username: str) -> None:
        """Remove a username from the registry."""
        with self._lock:
            self._sessions.pop(username, None)

    def is_taken(self, username: str) -> bool:
        """Check whether a username is active."""
        with self._lock:
            return username in self._sessions

    def list_usernames(self) -> list[str]:
        """Return all online usernames in sorted order."""
        with self._lock:
            return sorted(self._sessions)

    def get_session(self, username: str) -> object | None:
        """Return the stored session for a username if present."""
        with self._lock:
            return self._sessions.get(username)
