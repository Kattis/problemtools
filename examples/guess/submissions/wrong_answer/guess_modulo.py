#!/usr/bin/env python3

import sys

# This submission exposes a bug in an older version of the output validator
# where the valid range of possible submissions becomes empty because the range
# of possible values was updated incorrectly.
# The expected verdict is WA, but with the bug present, it would give RTE.

min_hidden = 1
max_hidden = 1000

for guess in [400, 700, 1, 600]:
    print(guess)
    ans = input()
    if ans == 'correct':
        break
    elif ans == 'lower':
        max_hidden = min(max_hidden, guess-1)
    elif ans == 'higher':
        min_hidden = max(min_hidden, guess-1)
    else:
        assert False

    assert min_hidden <= max_hidden
