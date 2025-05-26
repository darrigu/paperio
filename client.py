#!/usr/bin/env python3

import pickle
import select
import shutil
import socket
import sys
import termios
import time
import tty
from typing import Optional

from server import Color, Game, GenericDisplay, Grid, Player  # noqa: F401


class Display(GenericDisplay):
    width: int
    height: int
    buffer: list[Color]

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.buffer = [Color.default() for _ in range(width * height)]

    def draw(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.buffer[y * self.width + x] = color

    def render(self) -> str:
        rows = []
        for y in range(self.height):
            row = ''
            for x in range(self.width):
                color = self.buffer[y * self.width + x]
                from math import floor

                row += '\033[48;2;%d;%d;%dm ' % (
                    floor(color.r * 255),
                    floor(color.g * 255),
                    floor(color.b * 255),
                )
            rows.append(row)
        sys.stdout.write('\033[H' + '\n'.join(rows))


def get_key() -> Optional[str]:
    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr:
        ch = sys.stdin.read(1)
        if ch == '\033':
            ch += sys.stdin.read(2)
            if ch == '\033[A':
                return 'UP'
            elif ch == '\033[B':
                return 'DOWN'
            elif ch == '\033[C':
                return 'RIGHT'
            elif ch == '\033[D':
                return 'LEFT'
    return None


def main() -> None:
    server_addr = ('localhost', 12345)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(server_addr)
    except Exception as e:
        print('[ERROR] Unable to connect to server: %s' % e, file=sys.stderr)
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    term_size = shutil.get_terminal_size()
    display = Display(term_size.columns, term_size.lines)

    try:
        while True:
            key = get_key()
            if key:
                try:
                    sock.sendall(key.encode())
                except Exception:
                    break

            rlist, _, _ = select.select([sock], [], [], 0.05)
            if sock in rlist:
                data = sock.recv(65536)
                if not data:
                    break
                game = pickle.loads(data)
                game.render(display)
                display.render()

            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sock.close()


if __name__ == '__main__':
    main()

# TODO: reimplement windows compatibility
