import math
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Self

TARGET_FPS = 60
ROWS = 20
COLS = ROWS
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
    DEFAULT = 9


@dataclass
class Char:
    char: str
    fg: Optional[Color] = None
    bg: Optional[Color] = None
    bold: bool = False

    def __str__(self: Self) -> str:
        res = ''
        if self.fg:
            res += f'\033[3{self.fg.value}m'
        if self.bg:
            res += f'\033[4{self.bg.value}m'
        if self.bold:
            res += '\033[1m'
        res += self.char
        return res + '\033[0m'


class Display:
    width: int
    height: int
    buffer1: list[Char]
    buffer2: list[Char]
    current_buffer: list[Char]

    def __init__(self: Self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.buffer1 = [Char(' ')] * width * height
        self.buffer2 = [Char(' ')] * width * height
        self.current_buffer = self.buffer1

    def draw(self: Self, x: int, y: int, char: Char) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.current_buffer[y * self.width + x] = char

    def swap_buffers(self: Self) -> None:
        if self.current_buffer is self.buffer1:
            self.current_buffer = self.buffer2
        else:
            self.current_buffer = self.buffer1

    def render(self: Self) -> None:
        sys.stdout.write('\033[H')
        for y in range(self.height):
            for x in range(self.width * 2):
                char = self.current_buffer[y * self.width + x // 2]
                sys.stdout.write(str(char))
            sys.stdout.write('\n')
        sys.stdout.flush()


@dataclass
class Cell:
    char: Char

    @staticmethod
    def blank() -> 'Cell':
        return Cell(Char('.'))

    @staticmethod
    def colored(color: Color) -> 'Cell':
        return Cell(Char('.', bg=color))

    def render(self: Self, display: Display, x: int, y: int) -> None:
        display.draw(x, y, self.char)


class Grid:
    width: int
    height: int
    cells: list[Cell]

    def __init__(self: Self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells = [Cell.blank()] * width * height

    def get(self: Self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y * self.width + x]
        return None

    def set(self: Self, x: int, y: int, cell: Cell) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y * self.width + x] = cell

    def render(self: Self, display: Display) -> None:
        for y in range(self.height):
            for x in range(self.width):
                cell = self.get(x, y)
                assert cell is not None
                cell.render(display, x, y)


class Key(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


def get_key() -> Optional[Key]:
    if sys.platform.startswith('win'):
        import msvcrt

        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key == b'\xe0':
                key = msvcrt.getch()
                return {
                    b'H': Key.UP,
                    b'P': Key.DOWN,
                    b'K': Key.LEFT,
                    b'M': Key.RIGHT,
                }.get(key)
    else:
        import select

        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            key = sys.stdin.read(1)
            if key == '\033':
                key += sys.stdin.read(2)
                return {
                    '\033[A': Key.UP,
                    '\033[B': Key.DOWN,
                    '\033[D': Key.LEFT,
                    '\033[C': Key.RIGHT,
                }.get(key)
    return None


@dataclass
class Player:
    x: float
    y: float
    color: Color
    dx: float = 0
    dy: float = 0

    def update(self: Self, frame_time: int) -> None:
        self.x += self.dx * frame_time * PLAYER_SPEED
        self.y += self.dy * frame_time * PLAYER_SPEED

    def handle_key(self: Self, key: Key) -> None:
        if key is Key.UP:
            self.dx, self.dy = 0, -1
        elif key is Key.DOWN:
            self.dx, self.dy = 0, 1
        elif key is Key.LEFT:
            self.dx, self.dy = -1, 0
        elif key is Key.RIGHT:
            self.dx, self.dy = 1, 0

    def render(self: Self, display: Display) -> None:
        display.draw(math.floor(self.x), math.floor(self.y), Char('@', bg=self.color))


@dataclass
class Game:
    grid: Grid
    player: Player

    def update(self: Self, frame_time: int) -> None:
        key = get_key()
        if key:
            self.player.handle_key(key)
        self.player.update(frame_time)

        self.grid.set(
            math.floor(self.player.x),
            math.floor(self.player.y),
            Cell.colored(self.player.color),
        )

    def render(self: Self, display: Display) -> None:
        self.grid.render(display)
        self.player.render(display)


def main():
    display = Display(COLS, ROWS + 1)

    game = Game(
        grid=Grid(COLS, ROWS),
        player=Player(x=7, y=5, color=Color.RED),
    )

    frame_time = 1.0 / TARGET_FPS

    if not sys.platform.startswith('win'):
        import termios
        import tty

        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    print('\033c\033[?25l', end='')
    try:
        while True:
            frame_start_time = time.time()

            game.update(frame_time)
            game.render(display)
            display.render()

            elapsed_time = time.time() - frame_start_time

            sleep_time = frame_time - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass
    finally:
        print('\033[?25h', end='')
        if not sys.platform.startswith('win'):
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == '__main__':
    main()
