#!/usr/bin/env python3

import math
import pickle
import random
import select
import shutil
import socket
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

TARGET_FPS = 20
PLAYER_SPEED = 4


class Key(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


@dataclass
class Color:
    r: float
    g: float
    b: float

    @staticmethod
    def default() -> 'Color':
        return Color(0, 0, 0)

    def brightness(self, factor: float) -> 'Color':
        return Color(self.r * factor, self.g * factor, self.b * factor)


class GenericDisplay(ABC):
    width: int
    height: int
    buffer: list[Color]

    @abstractmethod
    def draw(self, x: int, y: int, color: Color) -> None: ...

    @abstractmethod
    def render(self) -> None: ...


class Grid:
    width: int
    height: int
    cells: list[Color]

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells = [Color.default() for _ in range(width * height)]

    def get(self, x: int, y: int) -> Optional[Color]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y * self.width + x]
        return None

    def set(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y * self.width + x] = color

    def render(self, display: GenericDisplay) -> None:
        for y in range(self.height):
            for x in range(self.width * 2):
                cell = self.get(x // 2, y)
                assert cell
                display.draw(x, y, cell)

    def fill_enclosed_area(self, player_color: Color) -> None:
        visited = [False] * (self.width * self.height)
        queue: deque[tuple[int, int]] = deque()

        for x in range(self.width):
            for y in (0, self.height - 1):
                cell = self.get(x, y)
                if cell and cell != player_color and not visited[y * self.width + x]:
                    visited[y * self.width + x] = True
                    queue.append((x, y))
        for y in range(self.height):
            for x in (0, self.width - 1):
                cell = self.get(x, y)
                if cell and cell != player_color and not visited[y * self.width + x]:
                    visited[y * self.width + x] = True
                    queue.append((x, y))

        while queue:
            cx, cy = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    cell = self.get(nx, ny)
                    if (
                        cell
                        and (not visited[ny * self.width + nx])
                        and cell != player_color
                    ):
                        visited[ny * self.width + nx] = True
                        queue.append((nx, ny))

        for y in range(self.height):
            for x in range(self.width):
                if not visited[y * self.width + x]:
                    self.set(x, y, player_color)


@dataclass
class Player:
    x: float
    y: float
    color: Color
    dx: float = 0
    dy: float = 0
    trail: list[tuple[int, int]] = field(default_factory=list)

    def update(self, frame_time: float) -> None:
        self.x += self.dx * frame_time * PLAYER_SPEED
        self.y += self.dy * frame_time * PLAYER_SPEED

    def handle_key(self, key: Key) -> None:
        if key == Key.UP:
            self.dx, self.dy = 0, -1
        elif key == Key.DOWN:
            self.dx, self.dy = 0, 1
        elif key == Key.LEFT:
            self.dx, self.dy = -1, 0
        elif key == Key.RIGHT:
            self.dx, self.dy = 1, 0

    def grid_position(self) -> tuple[int, int]:
        return (int(math.floor(self.x)), int(math.floor(self.y)))


class Game:
    def __init__(self, width: int, height: int) -> None:
        self.grid = Grid(width, height)
        self.players: dict[int, Player] = {}
        self.lock = threading.Lock()
        self.running = True

    def __getstate__(self) -> Any:
        return (self.grid, self.players)

    def __setstate__(self, state: Any) -> None:
        self.grid, self.players = state

    def add_player(self, player_id: int, player: Player) -> None:
        with self.lock:
            self.players[player_id] = player

    def remove_player(self, player_id: int) -> None:
        with self.lock:
            if player_id in self.players:
                for i, cell in enumerate(self.grid.cells):
                    if cell == self.players[player_id].color:
                        self.grid.cells[i] = Color.default()
                del self.players[player_id]

    def update(self, frame_time: float) -> None:
        with self.lock:
            for player in self.players.values():
                player.update(frame_time)
                new_x, new_y = player.grid_position()
                if new_x < 0:
                    player.x = 0
                if new_x >= self.grid.width:
                    player.x = self.grid.width - 1
                if new_y < 0:
                    player.y = 0
                if new_y >= self.grid.height:
                    player.y = self.grid.height - 1

                cell = self.grid.get(new_x, new_y)
                if cell and cell == player.color:
                    if player.trail:
                        self.grid.fill_enclosed_area(player.color)
                        player.trail = []
                else:
                    player.trail.append((new_x, new_y))
                    self.grid.set(new_x, new_y, player.color)

    def render(self, display: GenericDisplay) -> None:
        self.grid.render(display)
        for player in self.players.values():
            px, py = player.grid_position()
            color = player.color.brightness(0.5)
            display.draw(px * 2, py, color)
            display.draw(px * 2 + 1, py, color)


def parse_command(cmd: str) -> Optional[Key]:
    mapping = {
        'UP': Key.UP,
        'DOWN': Key.DOWN,
        'LEFT': Key.LEFT,
        'RIGHT': Key.RIGHT,
    }
    return mapping.get(cmd.strip().upper())


def handle_client(
    conn: socket.socket,
    addr: tuple[str, int],
    game: Game,
    player_id: int,
) -> None:
    print('[INFO] Client %s connected with id %d' % (str(addr), player_id))
    try:
        while game.running:
            ready, _, _ = select.select([conn], [], [], 0.05)
            if ready:
                data = conn.recv(1024)
                if not data:
                    break
                command = data.decode().strip()
                key = parse_command(command)
                if key:
                    with game.lock:
                        if player_id in game.players:
                            game.players[player_id].handle_key(key)
    except Exception as e:
        print('[ERROR] Error with client %s: %s' % (str(addr), e), file=sys.stderr)
    finally:
        print('[INFO] Client %s disconnected' % str(addr))
        game.remove_player(player_id)
        conn.close()


def game_loop(game: Game, clients: dict[int, socket.socket]) -> None:
    frame_time = 1.0 / TARGET_FPS
    while game.running:
        start = time.time()
        game.update(frame_time)
        data = pickle.dumps(game)
        remove_ids = []
        for pid, conn in clients.items():
            try:
                conn.sendall(data)
            except Exception:
                remove_ids.append(pid)
        for pid in remove_ids:
            if pid in clients:
                del clients[pid]
        elapsed = time.time() - start
        time.sleep(max(0, frame_time - elapsed))


def main() -> None:
    term_size = shutil.get_terminal_size()
    grid_width = term_size.columns // 2
    grid_height = term_size.lines
    game = Game(grid_width, grid_height)
    clients: dict[int, socket.socket] = {}

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('', 12345))
    server.listen()
    print('[INFO] Server started on port 12345')

    threading.Thread(target=game_loop, args=(game, clients), daemon=True).start()

    try:
        while True:
            conn, addr = server.accept()
            player_id = id(conn)
            color = random.choice(
                [
                    Color(0, 0, 1),
                    Color(0, 1, 0),
                    Color(0, 1, 1),
                    Color(1, 0, 0),
                    Color(1, 0, 1),
                    Color(1, 1, 0),
                ]
            )
            player = Player(
                x=random.randint(0, game.grid.width - 1),
                y=random.randint(0, game.grid.height - 1),
                color=color,
            )
            game.add_player(player_id, player)
            clients[player_id] = conn
            threading.Thread(
                target=handle_client,
                args=(conn, addr, game, player_id),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print('[INFO] Server shutting down...')
    finally:
        game.running = False
        server.close()


if __name__ == '__main__':
    main()

# TODO: make players die if:
# - they go out of bounds
# - they collide outside of their areas
# TODO: game over screen
# TODO: start screen
# TODO: make the map scrollable so clients can have different screen sizes than the server
# TODO: friend system
# TODO: ability to create games
# TODO: multiple game modes
