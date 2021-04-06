#!/usr/bin/env python3
from sys import stdin
import sys
import re

pat = "p[12]"

line = stdin.readline()
assert re.match(pat, line)

line = stdin.readline()
assert len(line) == 0

# Nothing to report
sys.exit(42)
