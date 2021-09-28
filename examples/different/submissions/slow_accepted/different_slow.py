#! /usr/bin/python3

import sys

for line in sys.stdin:
    ab = line.split()
    a = int(ab[0])
    b = int(ab[1])
    # needless loop just to be slow
    x = a
    for _ in range(100000000):
        x += 1
    diff = abs(a-b) + x - x

    print(diff)
