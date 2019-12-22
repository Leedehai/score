#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: flakiness.py
# ---------------------------
# Parse flakiness declaration files under a given directory.

import sys, os
import re

EXPECTED_ERRS = { # Sync with EXPLANATION_STRING in runtest.py
    "WrongExitCode", "Timeout", "Signal", "StdoutDiff", "Others"
}
def _valid_expected_errs(s):
    return all(e in EXPECTED_ERRS for e in s.split('|'))

def _parse_file(filename, flakiness_dict, errors):
    with open(filename, 'r') as f:
        raw_lines = f.readlines()
    for i, line in enumerate(raw_lines):
        line = line.strip()
        if len(line) == 0 or line.startswith('#'):
            continue
        if line.startswith("ignored"):
            continue
        line = line[:line.index('#')] if ('#' in line) else line
        parts = line.split()
        if len(parts) != 3:
            errors.append("[Error] malformed entry at %s:%s" % (filename, i + 1))
            continue
        if any(c not in '01234567890abcdef' for c in parts[1]): # not 'int(parts[1], 16)' to avoid negative sign
            errors.append("[Error] invalid lowercase base16 string '%s' at %s:%s" % (
                parts[1], filename, i + 1))
            continue
        if not _valid_expected_errs(parts[2]):
            errors.append(
                "[Error] invalid error '%s' at %s:%s\n" % (parts[2], filename, i + 1)
              + "        should be one or more (joined with '|': nonexclusive 'or') of %s" % ", ".join(EXPECTED_ERRS))
            continue
        case_id = "%s-%s" % (parts[0], parts[1]) # test path and args
        if case_id in flakiness_dict:
            errors.append("[Error] duplicate test (path, args) combination at %s:%s" % (
                filename, i + 1))
            continue
        flakiness_dict[case_id] = parts[2].split('|') # the expected errors

# export
# @param dirpath: str - directory that stores flakiness declaration files
# @return dict - key: str - test case_id, value: list of str - expected errors
def parse_flakiness_decls(dirpath):
    if (dirpath == None) or (dirpath == "") or (not os.path.isdir(dirpath)):
        return {} # empty instead of reporting an error
    file_count, flakiness_dict, errors = 0, {}, []
    for item in [ e for e in os.listdir(dirpath) if e.endswith(".flaky") ]:
        pathname = os.path.join(dirpath, item)
        if not os.path.isfile(pathname):
            continue
        file_count += 1
        _parse_file(pathname, flakiness_dict, errors)
    if len(errors):
        sys.exit('\n'.join(errors))
    if file_count == 0:
        sys.stderr.write(
            "[Warning] no file is named *.flaky under %s\n" % dirpath)
    return flakiness_dict

if __name__ == "__main__":
    print(parse_flakiness_decls(sys.argv[1]))
