"""SQLite persistence for finished match summaries."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class MatchHistoryStore:
    """Persist finished matches for demos and reports."""

    def __init__(self, db_path: str = "python_arena.db") -> None:
        self.db_path = Path(db_path)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS match_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_one TEXT NOT NULL,
                    player_two TEXT NOT NULL,
                    winner TEXT,
                    reason TEXT,
                    remaining_ticks INTEGER NOT NULL,
                    cheer_count INTEGER NOT NULL,
                    player_one_health INTEGER NOT NULL,
                    player_two_health INTEGER NOT NULL
                )
                """
            )
            connection.commit()

    def save_match(self, state: dict[str, object]) -> None:
        players = list(state["players"])
        snakes = dict(state["snakes"])
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO match_history (
                    player_one, player_two, winner, reason, remaining_ticks,
                    cheer_count, player_one_health, player_two_health
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    players[0],
                    players[1],
                    state.get("winner"),
                    state.get("reason"),
                    int(state["remaining_ticks"]),
                    len(list(state.get("cheers", []))),
                    int(snakes[players[0]]["health"]),
                    int(snakes[players[1]]["health"]),
                ),
            )
            connection.commit()

    def list_recent_matches(self, limit: int = 10) -> list[dict[str, object]]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT player_one, player_two, winner, reason, remaining_ticks,
                       cheer_count, player_one_health, player_two_health
                FROM match_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "player_one": row[0],
                "player_two": row[1],
                "winner": row[2],
                "reason": row[3],
                "remaining_ticks": row[4],
                "cheer_count": row[5],
                "player_one_health": row[6],
                "player_two_health": row[7],
            }
            for row in rows
        ]
