#!/usr/bin/env python3
# usage: python3 validator.py input_file correct_output output_dir p1_output p1_input p2_output p2_input < contestants_output
import re
import sys

def draw(msg):
    exit(43)

def player1_win():
    exit(41)

def player2_win():
    exit(42)

def invert_turn(player):
    if player == "p1":
        return "p2"
    else:
        return "p1"


if len(sys.argv) < 8:
    exit(1)

in_file = sys.argv[1]
answer_file = sys.argv[2]
output_dir = sys.argv[3]
p1_output = open(sys.argv[4], "r")
p1_input = open(sys.argv[5], "w")
p2_output = open(sys.argv[6], "r")
p2_input = open(sys.argv[7], "w")

def player_win(player):
    if player == "p1":
        p1_input.write("you win")
        p2_input.write("you lose")
        player1_win()
    else:
        p2_input.write("you win")
        p1_input.write("you lose")
        player2_win()

with open(in_file) as f:
    starting_player = f.read().strip()

board = [["", "", ""], ["", "", ""], ["", "", ""]]

pos_validator = re.compile("^[012] [012]$")

def game_over(player_token):
    return (any(all(x[i]==player_token for x in board) for i in range(3))
        or any(all(e==player_token for e in row) for row in board)
        or board[0][0] == board[2][2] == board[2][2] == player_token
        or board[2][0] == board[1][1] == board[0][2] == player_token)

if starting_player == "p1":
    p1_input.write("X")
    p2_input.write("O")
    tokens = {"p1": "X", "p2": "O"}
else:
    p2_input.write("X")
    p1_input.write("O")
    tokens = {"p1": "O", "p2": "X"}

current_turn = starting_player

while True:
    if current_turn == "p1":
        move = p1_output.readline()
    else:
        move = p2_output.readline()
    if pos_validator.match(move) is None:
        player_win(invert_turn(current_turn))
    else:
        col, row = map(int, move.split())
        if board[row][col] == "":
            board[row][col] = tokens[current_turn]
            if current_turn == "p1":
                p2_input.write(move)
            else:
                p1_input.write(move)
        else:
            player_win(invert_turn(current_turn))
    if game_over(tokens[current_turn]):
        player_win(current_turn)
    elif all(all(e != "" for e in row) for row in board):
        draw()
    else:
        current_turn = invert_turn(current_turn)

