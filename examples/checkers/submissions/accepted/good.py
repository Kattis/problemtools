#!/usr/bin/env python3
import sys

board = [["", "", ""], ["", "", ""], ["", "", ""]]

token = input()

def handle_move():
    l = input()
    if l == "you win" or l == "you lose":
        sys.exit(0)
    x, y = map(int, l.split(" "))
    if token == "X":
        board[x][y] = "O"
    else:
        board[x][y] = "X"

def do_move():
    for x in range(3):
        for y in range(3):
            if board[x][y] == "":
                print(f"{x} {y}", flush=True)
                board[x][y] = token
                return
    return

if token == "O":
    handle_move()

while True:
    do_move()
    handle_move()
