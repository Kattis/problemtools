#!/usr/bin/python
from sys import stdin
import sys
import re

integer = "(0|-?[1-9]\d*)"
pat = "(fixed|random|adaptive) " + integer + "\n"

line = stdin.readline()
assert re.match(pat, line)

line = stdin.readline()
assert len(line) == 0

# Nothing to report
sys.exit(42)
