import math
import shutil
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Self

TARGET_FPS = 60
ROWS = 20
COLS = 40
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

    def __str__(self: Self) -> str:
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

    def render(self) -> None:
        rows = []
        for y in range(self.height):
            row = ''
            for x in range(self.width):
                row += str(self.buffer[y * self.width + x])
            rows.append(row)
        print('\033[H' + '\n'.join(rows), end='')


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
        visited = [False for _ in range(self.width * self.height)]
        queue: deque[tuple[int, int]] = deque()

        for x in range(self.width):
            for y in (0, self.height - 1):
                cell = self.get(x, y)
                assert cell is not None
                if cell.char.bg != player_color and not visited[y * self.width + x]:
                    visited[y * self.width + x] = True
                    queue.append((x, y))
        for y in range(self.height):
            for x in (0, self.width - 1):
                cell = self.get(x, y)
                assert cell is not None
                if cell.char.bg != player_color and not visited[y * self.width + x]:
                    visited[y * self.width + x] = True
                    queue.append((x, y))

        while queue:
            cx, cy = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    cell = self.get(nx, ny)
                    assert cell is not None
                    if (
                        not visited[ny * self.width + nx]
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
    QUIT = auto()


def get_key() -> Optional[Key]:
    if sys.platform.startswith('win'):
        import msvcrt

        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key == b'\xe0':
                key = msvcrt.getch()
                mapping = {
                    b'H': Key.UP,
                    b'P': Key.DOWN,
                    b'K': Key.LEFT,
                    b'M': Key.RIGHT,
                }
                return mapping.get(key)
            elif key in (b'q', b'Q'):
                return Key.QUIT
    else:
        import select

        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            key = sys.stdin.read(1)
            if key == '\033':
                key += sys.stdin.read(2)
                mapping = {
                    '\033[A': Key.UP,
                    '\033[B': Key.DOWN,
                    '\033[D': Key.LEFT,
                    '\033[C': Key.RIGHT,
                }
                return mapping.get(key)
            elif key.lower() == 'q':
                return Key.QUIT
    return None


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
        return (math.floor(self.x), math.floor(self.y))


@dataclass
class Game:
    grid: Grid
    player: Player
    game_over: bool = False

    def update(self, frame_time: float) -> None:
        key = get_key()
        if key:
            if key == Key.QUIT:
                self.game_over = True
                return
            self.player.handle_key(key)

        self.player.update(frame_time)

        new_x, new_y = self.player.grid_position()
        if not (0 <= new_x < self.grid.width and 0 <= new_y < self.grid.height):
            self.game_over = True
            return

        cell = self.grid.get(new_x, new_y)
        if cell and cell.char.bg == self.player.color:
            if self.player.trail:
                self.grid.fill_enclosed_area(self.player.color)
                self.player.trail = []
        else:
            self.player.trail.append((new_x, new_y))
            self.grid.set(new_x, new_y, Cell.colored(self.player.color))

    def render(self, display: Display) -> None:
        self.grid.render(display)

        px, py = self.player.grid_position()
        char = Char(' ', bg=self.player.color, bold=True, bright=True)
        display.draw(px * 2, py, char)
        display.draw(px * 2 + 1, py, char)

        status = ' Arrow keys: move | Q: quit '
        status_bar = status.ljust(display.width)
        for i, ch in enumerate(status_bar):
            display.draw(i, display.height - 1, Char(ch, inverse=True))


def main() -> None:
    term_size = shutil.get_terminal_size()
    display = Display(term_size.columns, term_size.lines)
    # TODO: implement scroll for bigger grid
    grid = Grid(display.width // 2, display.height)
    player = Player(x=grid.width // 2, y=grid.height // 2, color=Color.RED)
    game = Game(grid=grid, player=player)

    frame_time = 1.0 / TARGET_FPS

    print('\033[2J\033[H\033[?25l', end='')

    if not sys.platform.startswith('win'):
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    try:
        while not game.game_over:
            start = time.time()
            game.update(frame_time)
            game.render(display)
            display.render()
            elapsed = time.time() - start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass
    finally:
        print('\033[?25h', end='')
        if not sys.platform.startswith('win'):
            import termios

            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        print('Game over')


if __name__ == '__main__':
    main()
