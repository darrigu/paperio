#!/usr/bin/env python3

import select
import socket
import sys
import termios
import time
import tty
from typing import Optional


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
                print('\033[2J' + data.decode(), end='')

            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sock.close()


if __name__ == '__main__':
    main()

# TODO: reimplement windows compatibility
