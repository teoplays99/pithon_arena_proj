"""Authoritative game state for a single Python Arena match."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from common.constants import BOARD_HEIGHT, BOARD_WIDTH, INITIAL_HEALTH, MATCH_DURATION_TICKS, MIN_PIE_COUNT

UP = "UP"
DOWN = "DOWN"
LEFT = "LEFT"
RIGHT = "RIGHT"

VECTORS = {
    UP: (0, -1),
    DOWN: (0, 1),
    LEFT: (-1, 0),
    RIGHT: (1, 0),
}

OPPOSITES = {
    UP: DOWN,
    DOWN: UP,
    LEFT: RIGHT,
    RIGHT: LEFT,
}

WALL_DAMAGE = 15
OBSTACLE_DAMAGE = 10
BODY_DAMAGE = 20
HEAD_ON_DAMAGE = 15
COLLISION_FREEZE_TICKS = 5
PIE_HEALTH = {
    "green": 10,
    "gold": 20,
}


@dataclass
class SnakeState:
    """State for a single player's snake."""

    username: str
    body: list[tuple[int, int]]
    direction: str
    health: int = INITIAL_HEALTH
    stun_ticks_remaining: int = 0
    recovery_direction: str | None = None


@dataclass
class Match:
    """Authoritative state and tick updates for one active match."""

    players: list[str]
    board_width: int = BOARD_WIDTH
    board_height: int = BOARD_HEIGHT
    remaining_ticks: int = MATCH_DURATION_TICKS
    obstacles: list[tuple[int, int]] = field(default_factory=list)
    pies: list[dict[str, int | str]] = field(default_factory=list)
    cheers: list[dict[str, str]] = field(default_factory=list)
    winner: str | None = None
    reason: str | None = None
    game_over: bool = False

    def __post_init__(self) -> None:
        if len(self.players) != 2:
            raise ValueError("A match requires exactly two players.")
        self.snakes = self._build_initial_snakes(self.players)
        self.pending_inputs: dict[str, str] = {}
        if not self.obstacles:
            self.obstacles = self._default_obstacles()
        if not self.pies:
            self._ensure_minimum_pies()

    def _build_initial_snakes(self, players: list[str]) -> dict[str, SnakeState]:
        center_y = self.board_height // 2
        left_start = [(4, center_y), (3, center_y), (2, center_y)]
        right_start = [
            (self.board_width - 5, center_y),
            (self.board_width - 4, center_y),
            (self.board_width - 3, center_y),
        ]
        return {
            players[0]: SnakeState(players[0], left_start, RIGHT),
            players[1]: SnakeState(players[1], right_start, LEFT),
        }

    def _default_obstacles(self) -> list[tuple[int, int]]:
        center_x = self.board_width // 2
        center_y = self.board_height // 2
        return [(center_x, center_y - 2), (center_x, center_y), (center_x, center_y + 2)]

    def queue_input(self, username: str, direction: str) -> bool:
        """Store the latest direction input for a player."""
        snake = self.snakes.get(username)
        if snake is None or direction not in VECTORS:
            return False
        self.pending_inputs[username] = direction
        return True

    def tick(self) -> dict[str, object]:
        """Advance the authoritative match state by one server tick."""
        if self.game_over:
            return self.to_state_payload()

        self._advance_collision_freeze()

        for username, snake in self.snakes.items():
            if snake.stun_ticks_remaining > 0:
                continue
            queued_direction = self.pending_inputs.get(username)
            if queued_direction and OPPOSITES[snake.direction] != queued_direction:
                snake.direction = queued_direction

        self.pending_inputs.clear()

        proposed_heads: dict[str, tuple[int, int]] = {}
        for username, snake in self.snakes.items():
            if snake.stun_ticks_remaining > 0:
                proposed_heads[username] = snake.body[0]
                continue
            dx, dy = VECTORS[snake.direction]
            head_x, head_y = snake.body[0]
            proposed_heads[username] = (head_x + dx, head_y + dy)

        future_bodies: dict[str, list[tuple[int, int]]] = {}
        for username, snake in self.snakes.items():
            if snake.stun_ticks_remaining > 0:
                future_bodies[username] = list(snake.body)
            else:
                future_bodies[username] = [proposed_heads[username]] + snake.body[:-1]

        collisions: dict[str, int] = {username: 0 for username in self.players}
        collided_players: set[str] = set()
        if proposed_heads[self.players[0]] == proposed_heads[self.players[1]]:
            for username in self.players:
                collisions[username] += HEAD_ON_DAMAGE
                collided_players.add(username)

        for username in self.players:
            snake = self.snakes[username]
            if snake.stun_ticks_remaining > 0:
                continue
            head = proposed_heads[username]
            if not self._is_in_bounds(head):
                collisions[username] += WALL_DAMAGE
                collided_players.add(username)
            if head in self.obstacles:
                collisions[username] += OBSTACLE_DAMAGE
                collided_players.add(username)

            own_future_body = future_bodies[username][1:]
            if head in own_future_body:
                collisions[username] += BODY_DAMAGE
                collided_players.add(username)

            for other_username, other_body in future_bodies.items():
                if other_username == username:
                    continue
                if head in other_body[1:]:
                    collisions[username] += BODY_DAMAGE
                    collided_players.add(username)
                    break

        for username, snake in self.snakes.items():
            if collisions[username] > 0:
                snake.health = max(0, snake.health - collisions[username])
                snake.stun_ticks_remaining = COLLISION_FREEZE_TICKS
                snake.recovery_direction = self._recovery_direction_for(snake.direction)
            else:
                snake.body = future_bodies[username]
                self._collect_pie_if_present(username)

        self._ensure_minimum_pies()

        self.remaining_ticks = max(0, self.remaining_ticks - 1)
        if any(snake.health <= 0 for snake in self.snakes.values()):
            self.game_over = True
            self.reason = "health_zero"
            self.winner = self._determine_winner()
        elif self.remaining_ticks == 0:
            self.game_over = True
            self.reason = "timer_end"
            self.winner = self._determine_winner()

        return self.to_state_payload()

    def end_due_to_disconnect(self, disconnected_username: str) -> dict[str, object]:
        """Terminate the match because one player disconnected."""
        self.game_over = True
        self.reason = "player_disconnected"
        remaining_players = [username for username in self.players if username != disconnected_username]
        self.winner = remaining_players[0] if remaining_players else None
        return self.to_state_payload()

    def add_cheer(self, username: str, text: str, limit: int = 30) -> None:
        """Append a cheer message and trim the history."""
        self.cheers.append({"from": username, "text": text})
        if len(self.cheers) > limit:
            self.cheers = self.cheers[-limit:]

    def _advance_collision_freeze(self) -> None:
        for snake in self.snakes.values():
            if snake.stun_ticks_remaining <= 0:
                continue
            snake.stun_ticks_remaining -= 1
            if snake.stun_ticks_remaining == 0 and snake.recovery_direction is not None:
                snake.direction = snake.recovery_direction
                snake.recovery_direction = None

    def _is_in_bounds(self, position: tuple[int, int]) -> bool:
        x, y = position
        return 0 <= x < self.board_width and 0 <= y < self.board_height

    def _occupied_positions(self) -> set[tuple[int, int]]:
        occupied = set(self.obstacles)
        for snake in self.snakes.values():
            occupied.update(snake.body)
        for pie in self.pies:
            occupied.add((int(pie["x"]), int(pie["y"])))
        return occupied

    def _collect_pie_if_present(self, username: str) -> None:
        snake = self.snakes[username]
        head = snake.body[0]
        for index, pie in enumerate(self.pies):
            if (int(pie["x"]), int(pie["y"])) != head:
                continue
            pie_type = str(pie["kind"])
            snake.health += PIE_HEALTH.get(pie_type, 0)
            self.pies.pop(index)
            return

    def _recovery_direction_for(self, direction: str) -> str:
        recovery_map = {
            UP: LEFT,
            DOWN: RIGHT,
            LEFT: DOWN,
            RIGHT: UP,
        }
        return recovery_map[direction]

    def _ensure_minimum_pies(self) -> None:
        while len(self.pies) < MIN_PIE_COUNT:
            occupied = self._occupied_positions()
            free_cells = [
                (x, y)
                for y in range(self.board_height)
                for x in range(self.board_width)
                if (x, y) not in occupied
            ]
            if not free_cells:
                return
            x, y = random.choice(free_cells)
            self.pies.append({"x": x, "y": y, "kind": "green"})

    def _determine_winner(self) -> str | None:
        sorted_snakes = sorted(
            self.snakes.values(),
            key=lambda snake: (-snake.health, snake.username),
        )
        if len(sorted_snakes) < 2:
            return None
        if sorted_snakes[0].health == sorted_snakes[1].health:
            return None
        return sorted_snakes[0].username

    def to_state_payload(self) -> dict[str, object]:
        """Serialize current match state for the client."""
        return {
            "players": self.players,
            "board": {"width": self.board_width, "height": self.board_height},
            "snakes": {
                username: {
                    "body": [list(segment) for segment in snake.body],
                    "direction": snake.direction,
                    "health": snake.health,
                    "stun_ticks_remaining": snake.stun_ticks_remaining,
                }
                for username, snake in self.snakes.items()
            },
            "obstacles": [list(position) for position in self.obstacles],
            "pies": self.pies,
            "remaining_ticks": self.remaining_ticks,
            "game_over": self.game_over,
            "winner": self.winner,
            "reason": self.reason,
            "cheers": list(self.cheers),
        }
