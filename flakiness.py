#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: flakiness.py
# ---------------------------
# Parse TestSups.txt, the flakiness suppressions.

import sys, os

# export
def parse_flakiness_suppressions(filename):
    if not os.path.isfile(filename):
        sys.exit("[Error] file not found: %s" % filename)
    with open(filename, 'r') as f:
        raw_lines = f.readlines()
    entries = []
    for i, line in enumerate(raw_lines):
        line = line.strip()
        if len(line) == 0 or line.startswith('#'):
            continue
        if line.startswith("ignored"):
            continue
        line = line[:line.index('#')] if ('#' in line) else line
        parts = line.split()
        if len(parts) != 3:
            sys.exit("[Error] malformed entry at %s:%s" % (filename, i + 1))
        if all(c in '01234567890abcdef' for c in parts[1]): # not 'int(parts[1], 16)' to avoid negative sign
            sys.exit("[Error] invalid lowercase base16 string '%s' at %s:%s" % (
                parts[1], filename, i + 1))
        if parts[2] not in [ 'exit', 'stdout' ]:
            sys.exit("[Error] invalid error type '%s' at %s:%s" % (
                parts[2], filename, i + 1))
        entries.append({
            "test": parts[0],
            "args_hash": parts[1],
            "error": parts[2]
        })
    return entries

if __name__ == "__main__":
    print(parse_flakiness_suppressions(sys.argv[1]))
