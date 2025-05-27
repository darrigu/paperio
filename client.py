#!/usr/bin/env python3

import os
import pickle
import select
import shutil
import socket
import sys
import time
from typing import Optional

from server import Color, Game, GenericDisplay, Grid, Player  # noqa: F401


if os.name == 'nt':
    import msvcrt

    def get_key() -> Optional[str]:
        if msvcrt.kbhit():
            msvcrt.getch()
            c = msvcrt.getch()
            vals = [72, 77, 80, 75]
            key = vals.index(ord(c.decode('utf-8')))
            # TODO: use Key enum from server
            return {0: 'UP', 1: 'RIGHT', 2: 'DOWN', 3: 'LEFT'}[key]
        return None
else:
    import termios
    import tty

    def get_key() -> Optional[str]:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
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
                return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return None


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


def main() -> None:
    server_addr = ('localhost', 12345)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(server_addr)
    except Exception as e:
        print('[ERROR] Unable to connect to server: %s' % e, file=sys.stderr)
        return

    term_size = shutil.get_terminal_size()
    display = Display(term_size.columns, term_size.lines)

    try:
        while True:
            key = get_key()
            if key:
                try:
                    sock.sendall(key.encode())
                except Exception as e:
                    print('[ERROR] Unable to send data: %s' % e, file=sys.stderr)
                    exit(1)

            rlist, _, _ = select.select([sock], [], [], 0.05)
            if sock in rlist:
                data = sock.recv(65536)
                if not data:
                    break
                try:
                    game = pickle.loads(data)
                    game.render(display)
                    display.render()
                except (pickle.UnpicklingError, EOFError) as e: 
                    print('[ERROR] Failed to unpickle data: %s' % e, file=sys.stderr)
                    exit(1)

            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == '__main__':
    main()

# TODO: reimplement windows compatibility
