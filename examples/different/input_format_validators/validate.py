#!/usr/bin/python
from sys import stdin
import sys
import re

integer = "(0|-?[1-9]\d*)"

MAX = 10**15

cases = 0

while True:
    line = stdin.readline()
    if len(line) == 0:
        break
    assert re.match(integer + " " + integer + "\n", line), "'%s' is not a pair of integers" % line
    (n, m) = map(int, line.split())
    assert 0 <= n <= MAX, "%s  not in [0, %s]" % (n, MAX)
    assert 0 <= m <= MAX, "%s  not in [0, %s]" % (m, MAX)
    cases += 1

assert 1 <= cases <= 40, "invalid number of cases %d not in [1,40]" % cases

# Nothing to report
sys.exit(42)
