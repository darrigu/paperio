import math
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import NoReturn, Optional

TARGET_FPS = 60
ROWS = 20
COLS = ROWS * 2
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

    def __str__(self) -> str:
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

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.buffer1 = [Char(' ')] * width * height
        self.buffer2 = [Char(' ')] * width * height
        self.current_buffer = self.buffer1

    def draw(self, x: int, y: int, char: Char):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.current_buffer[y * self.width + x] = char

    def draw_text(self, x, y, text):
        for i, char in enumerate(text):
            self.draw(x + i, y, Char(char))

    def swap_buffers(self):
        if self.current_buffer is self.buffer1:
            self.current_buffer = self.buffer2
        else:
            self.current_buffer = self.buffer1

    def render(self):
        sys.stdout.write('\033[H')
        for y in range(self.height):
            for x in range(self.width):
                char = self.current_buffer[y * self.width + x]
                sys.stdout.write(str(char))
            sys.stdout.write('\n')
        sys.stdout.flush()


class Cell(Enum):
    EMPTY = auto()

    @staticmethod
    def throw_bad(cell: NoReturn) -> NoReturn:
        assert False, f'Bad Cell type: {cell}'

    def render(self, display: Display, x: int, y: int) -> None:
        if self is Cell.EMPTY:
            display.draw(x, y, Char('.'))
        else:
            Cell.throw_bad(self)


class Grid:
    width: int
    height: int
    cells: list[Cell]

    def __init__(self, cells: list[list[Cell]]):
        self.width = len(cells[0])
        self.height = len(cells)
        self.cells = sum(cells, [])

    def get(self, x: int, y: int) -> Cell:
        return self.cells[y * self.width + x]

    def render(self, display: Display) -> None:
        for y in range(self.height):
            for x in range(self.width):
                self.get(x, y).render(display, x, y)


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

    def update(self, frame_time: int) -> None:
        self.x += self.dx * frame_time * PLAYER_SPEED
        self.y += self.dy * frame_time * PLAYER_SPEED

    def handle_key(self, key: Key) -> None:
        if key is Key.UP:
            self.dx, self.dy = 0, -1
        elif key is Key.DOWN:
            self.dx, self.dy = 0, 1
        elif key is Key.LEFT:
            self.dx, self.dy = -1, 0
        elif key is Key.RIGHT:
            self.dx, self.dy = 1, 0

    def render(self, display: Display) -> None:
        display.draw(math.floor(self.x), math.floor(self.y), Char('@', fg=self.color))


@dataclass
class Game:
    grid: Grid
    player: Player

    def update(self, frame_time: int) -> None:
        key = get_key()
        if key:
            self.player.handle_key(key)
        self.player.update(frame_time)

    def render(self, display: Display) -> None:
        self.grid.render(display)
        self.player.render(display)


def main():
    display = Display(COLS, ROWS + 1)

    game = Game(
        grid=Grid([[Cell.EMPTY] * COLS] * ROWS),
        player=Player(x=7, y=5, color=Color.RED),
    )

    start_time = time.time()
    frame_time = 1.0 / TARGET_FPS
    frame_count = 0
    fps = TARGET_FPS

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
            display.draw_text(0, ROWS, f'FPS: {fps}')
            display.render()

            frame_count += 1

            elapsed_time = time.time() - frame_start_time

            sleep_time = frame_time - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)

            if time.time() - start_time >= 1.0:
                fps = frame_count
                frame_count = 0
                start_time = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        print('\033[?25h', end='')
        if not sys.platform.startswith('win'):
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == '__main__':
    main()
