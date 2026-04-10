# AGENTS.md

## Purpose

This repository contains the EECE 350 network programming project: `Python Arena`, a Python + Pygame online two-player snake battle game built around a client-server architecture.

This file is the working contract for future implementation work in this repo. It consolidates:

- the formal project requirements extracted from `EECE350_project_Spring2025.pdf`
- the implementation direction proposed in `plan.txt`
- the engineering rules we should follow while building the project
- the regression-testing rule centered on `unit tests.ipynb`

Any future agent working on this repository should read this file first.

## Project Summary

The project requires building a centralized multiplayer game where:

- players connect to a TCP server using a username
- the server verifies username uniqueness
- the server maintains the authoritative game state
- the client sends input commands and renders received state
- the game supports one active match between two players
- additional features include peer-to-peer text chat, fans/spectators, and one creative feature

## Confirmed Requirements From The PDF

The following requirements were recovered from the project brief and should be treated as mandatory unless the instructor says otherwise:

- implement the project in Python
- use Pygame for the graphical client
- design the protocol between client and server
- build both the client and the server
- connect clients to a centralized server
- require a username on connection
- validate that usernames are unique
- show online players and allow a player to select an opponent
- if only one player is connected, that player waits for another player
- during gameplay, the client sends movement commands to the server
- the client renders game state updates received from the server
- the client displays both snakes, pie items, obstacles, and health scores
- the client displays the final result and winner at the end of the match
- the server takes a listening port as a command-line argument
- the server accepts multiple client connections
- the server tracks online users
- the server supports one active game session between two players
- the server generates pie items
- the server generates static obstacles at fixed locations
- the server maintains snake positions, pie locations, obstacles, and health
- the server receives player actions and updates the game state accordingly
- the server detects collisions with walls, snake bodies, and obstacles
- the server determines when the game ends and announces the winner
- the server broadcasts updated game state to both players
- advanced feature 1: peer-to-peer text chat between players
- advanced feature 2: fans/spectators can watch the ongoing battle and cheer
- advanced feature 3: implement one creative feature of our choice

## Chosen Architecture

The current plan in `plan.txt` is sound and should be our default direction.

### Networking

- main gameplay uses TCP
- application messages use JSON
- framing should be explicit: prefer length-prefixed messages over ad hoc parsing
- server is authoritative for game rules and state
- peer-to-peer chat is a separate TCP connection between the two matched players

### Concurrency

- server:
  - one accept loop on the main socket
  - one handler thread per client connection
  - one match/game-loop thread for the active game
- client:
  - main thread for Pygame rendering and input
  - one network receive thread for server messages
  - optional peer-chat listener thread

### Core State Ownership

The server is the source of truth for:

- usernames and online presence
- lobby state and matchmaking
- snake positions and directions
- pies and obstacles
- health values
- match timer
- collision detection
- winner determination
- spectator updates

Clients should not decide the real game outcome locally.

## Current Build Direction

Unless the user explicitly redirects the design, build the following version:

- main game: centralized TCP server, JSON protocol, authoritative game loop
- chat: separate peer-to-peer TCP chat socket between the two active players
- GUI: Pygame client
- creative feature: replay system based on recorded game events or state snapshots

## Recommended Initial Repository Layout

As implementation begins, prefer this structure:

```text
client/
  main.py
  ui/
  networking/
  rendering/
  state/
server/
  main.py
  networking/
  lobby/
  game/
  models/
  persistence/
common/
  protocol.py
  constants.py
  message_types.py
assets/
docs/
tests/
```

This layout is not mandatory, but new code should stay modular and avoid mixing server logic, client rendering, and shared protocol definitions in one file.

## Suggested Shared Data Model

Keep the design object-oriented but not overengineered. The following types are likely enough:

- `UserSession`
- `LobbyManager`
- `Match`
- `Snake`
- `Pie`
- `Obstacle`
- `ReplayRecorder`
- `ProtocolCodec`

Useful server-side collections:

- `connected_clients: dict[str, UserSession]`
- `waiting_players: list[str]`
- `active_match: Match | None`
- `spectators: set[str]`
- per-player input queues or latest pending command

## Protocol Direction

Use a message envelope shaped like:

```json
{
  "type": "LOGIN",
  "payload": {
    "username": "Teo"
  }
}
```

Expected message families:

- connection/login: `LOGIN`, `LOGIN_OK`, `LOGIN_REJECT`, `ERROR`
- lobby: `ONLINE_USERS`, `WAITING`, `CHALLENGE_PLAYER`, `CHALLENGE_ACCEPT`
- match lifecycle: `MATCH_START`, `STATE_UPDATE`, `GAME_OVER`, `PLAYER_DISCONNECTED`
- gameplay: `INPUT`
- spectators: `WATCH_MATCH`, `CHEER`
- peer chat bootstrap: `CHAT_PEER_INFO`

Keep protocol definitions centralized in `common/` so client and server do not drift.

## Gameplay Rules To Implement First

Baseline rules to prioritize:

- two players in one active match
- both start with equal health
- snakes move on a grid
- static obstacles exist on the board
- pies spawn on the board
- collecting pies increases health
- collisions decrease health
- game ends when:
  - one player reaches zero health, or
  - the timer expires
- if the timer expires, higher health wins

Additional polish such as multiple pie types can come after the basic loop works.

## Persistence

SQLite is not explicitly required by the brief, but the user wants the project to include SQLite and course materials include it. The most defensible use is match persistence, not live game state.

Use SQLite for:

- match history
- players in a finished match
- winner
- duration
- pie collection stats
- collision stats
- cheer count

Do not make SQLite a blocking dependency for the real-time game loop.

## Implementation Order

Build in this sequence:

1. shared protocol/constants module
2. TCP server startup and client connection handling
3. unique username validation
4. online user tracking and lobby updates
5. matchmaking flow for two players
6. authoritative game loop on the server
7. Pygame client rendering of server state
8. collision, health, timer, and winner logic
9. spectators/fans
10. peer-to-peer chat
11. replay feature
12. SQLite match history
13. testing, fault handling, cleanup

## Notebook Test Policy

`unit tests.ipynb` is the required regression notebook for this repository.

Rules:

- run `unit tests.ipynb` after every code change
- when a feature is implemented, add or extend notebook tests for that feature in the same task
- do not treat a feature as complete until the notebook passes
- if Jupyter is unavailable, run the notebook with:

```bash
python3 tools/run_notebook.py "unit tests.ipynb"
```

- keep the notebook focused on automated checks, not manual notes
- start with smoke tests when a module is first created, then replace or extend them with more specific behavioral tests as the codebase grows
- mention notebook test results in task summaries

## Engineering Rules For Future Work

- keep server logic authoritative; never move winner logic into the client
- avoid blocking socket reads on the Pygame render thread
- prefer small modules over large monolithic scripts
- every protocol change must update both client and server shared definitions
- every feature change must update and rerun `unit tests.ipynb`
- when adding a feature, keep the basic two-player match stable first
- do not add advanced UI polish before the networking path is reliable
- use thread-safe handoff between network threads and UI/game state
- prefer deterministic server tick updates over frame-dependent game logic
- make networking errors visible and debuggable with clear logs

## Definition Of Done

The project is in acceptable shape when all of the following are true:

- two clients can connect to the server by IP and port
- duplicate usernames are rejected
- online users can be listed
- two users can start a match
- client input reaches the server and changes authoritative state
- both clients receive synchronized state updates
- pies, obstacles, health, timer, and collisions work correctly
- winner selection is correct
- spectators can watch
- players can chat peer-to-peer
- at least one creative feature is complete
- `unit tests.ipynb` passes after the final change set
- the codebase is documented enough for report/demo preparation

## Notes For Agents

- before major coding starts, keep this file aligned with any clarified professor requirements
- if the PDF and `plan.txt` ever conflict, prefer the PDF for grading-related behavior
- if a requirement is ambiguous, implement the simplest version that clearly satisfies the brief and document the assumption
- do not delete this file; update it as the source of truth for repo-level execution
