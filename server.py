#!/usr/bin/env python3

import math
import random
import select
import shutil
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

TARGET_FPS = 20
PLAYER_SPEED = 4


class Color(Enum):
    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7


@dataclass
class Char:
    char: str
    fg: Optional[Color] = None
    bg: Optional[Color] = None
    bold: bool = False
    inverse: bool = False
    bright: bool = False

    def __str__(self) -> str:
        res = ''
        if self.fg:
            if self.bright:
                res += f'\033[9{self.fg.value}m'
            else:
                res += f'\033[3{self.fg.value}m'
        if self.bg:
            if self.bright:
                res += f'\033[10{self.bg.value}m'
            else:
                res += f'\033[4{self.bg.value}m'
        if self.bold:
            res += '\033[1m'
        if self.inverse:
            res += '\033[7m'
        res += self.char
        res += '\033[0m'
        return res


class Display:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.buffer = [Char(' ') for _ in range(width * height)]

    def draw(self, x: int, y: int, char: Char) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.buffer[y * self.width + x] = char

    def render(self) -> str:
        rows = []
        for y in range(self.height):
            row = ''
            for x in range(self.width):
                row += str(self.buffer[y * self.width + x])
            rows.append(row)
        return '\033[H' + '\n'.join(rows)


@dataclass
class Cell:
    char: Char

    @staticmethod
    def blank() -> 'Cell':
        return Cell(Char(' '))

    @staticmethod
    def colored(color: Color) -> 'Cell':
        return Cell(Char(' ', bg=color))


class Grid:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells = [Cell.blank() for _ in range(width * height)]

    def get(self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y * self.width + x]
        return None

    def set(self, x: int, y: int, cell: Cell) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y * self.width + x] = cell

    def render(self, display: Display) -> None:
        for y in range(self.height):
            for x in range(self.width * 2):
                cell = self.get(x // 2, y)
                assert cell
                display.draw(x, y, cell.char)

    def fill_enclosed_area(self, player_color: Color) -> None:
        visited = [False] * (self.width * self.height)
        queue: deque[tuple[int, int]] = deque()

        for x in range(self.width):
            for y in (0, self.height - 1):
                cell = self.get(x, y)
                if (
                    cell
                    and cell.char.bg != player_color
                    and not visited[y * self.width + x]
                ):
                    visited[y * self.width + x] = True
                    queue.append((x, y))
        for y in range(self.height):
            for x in (0, self.width - 1):
                cell = self.get(x, y)
                if (
                    cell
                    and cell.char.bg != player_color
                    and not visited[y * self.width + x]
                ):
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
                        and cell.char.bg != player_color
                    ):
                        visited[ny * self.width + nx] = True
                        queue.append((nx, ny))

        for y in range(self.height):
            for x in range(self.width):
                if not visited[y * self.width + x]:
                    self.set(x, y, Cell.colored(player_color))


class Key(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


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

    def add_player(self, player_id: int, player: Player) -> None:
        with self.lock:
            self.players[player_id] = player

    def remove_player(self, player_id: int) -> None:
        with self.lock:
            if player_id in self.players:
                del self.players[player_id]

    def update(self, frame_time: float) -> None:
        with self.lock:
            for player in self.players.values():
                player.update(frame_time)
                new_x, new_y = player.grid_position()
                if new_x < 0:
                    player.x = self.grid.width - 1
                if new_x >= self.grid.width:
                    player.x = 0
                if new_y < 0:
                    player.y = self.grid.height - 1
                if new_y >= self.grid.height:
                    player.y = 0

                cell = self.grid.get(new_x, new_y)
                if cell and cell.char.bg == player.color:
                    if player.trail:
                        self.grid.fill_enclosed_area(player.color)
                        player.trail = []
                else:
                    player.trail.append((new_x, new_y))
                    self.grid.set(new_x, new_y, Cell.colored(player.color))

    def render(self, display: Display) -> str:
        self.grid.render(display)
        with self.lock:
            for player in self.players.values():
                px, py = player.grid_position()
                char = Char(' ', bg=player.color, bold=True, bright=True)
                display.draw(px * 2, py, char)
                display.draw(px * 2 + 1, py, char)
        status = ' Arrow keys: move | Ctrl+C: quit '
        status_bar = status.ljust(display.width)
        for i, ch in enumerate(status_bar):
            display.draw(i, display.height - 1, Char(ch, inverse=True))
        return display.render()


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
    term_size = shutil.get_terminal_size()
    display = Display(term_size.columns, term_size.lines)
    while game.running:
        start = time.time()
        game.update(frame_time)
        frame = game.render(display)
        remove_ids = []
        for pid, conn in clients.items():
            try:
                conn.sendall(frame.encode())
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
                    Color.RED,
                    Color.GREEN,
                    Color.YELLOW,
                    Color.BLUE,
                    Color.MAGENTA,
                    Color.CYAN,
                ]
            )
            player = Player(
                x=game.grid.width // 2,
                y=game.grid.height // 2,
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

# TODO: make the map scrollable so clients can have different screen sizes than the server
