#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: flakiness.py
# ---------------------------
# Parse flakiness declaration files under a given directory.

import json
import os
import sys
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import Dict, List, Optional

from pylibs import schema

POSSIBLE_TEST_ERRORS = [  # sync with EXPLANATION_STRING's spec
    "wrong_exit_code", "timeout", "signal", "stdout_diff", "quit", "unknown"
]

FlakeDecls = Dict[str, List[str]]


def _parse_file(f: TextIOWrapper, path: Path, flaky_tests_decls: FlakeDecls,
                errors: List[str]) -> None:
    try:
        data = json.load(f)
    except json.JSONDecodeError:
        errors.append("not a JSON file: %s" % path)
        data = {}
    try:
        schema.Schema({  # sync with EXPLANATION_STRING's spec
            str: {
                "errors": [schema.Or(*POSSIBLE_TEST_ERRORS)],
                schema.Optional("reason"): str,
                schema.Optional(str): object,  # Allow more fields, if any.
            }
        }).validate(data)
        for test_id, tolerable_errors in data.items():
            if test_id in flaky_tests_decls:
                errors.append(
                    "test %s declared in file %s, but it was declared in a previous file."
                    % (test_id, path))
            flaky_tests_decls[test_id] = tolerable_errors
    except schema.SchemaError as e:  # Carries explanations.
        errors.append(str(e))


# Sync with EXPLANATION_STRING's spec
FLAKY_TEST_RECORD_FILE_SUFFIX = ".flakes.json"


# export
def maybe_parse_flakiness_decls_from_dir(
        dirpath: Optional[Path]) -> Dict[str, List[str]]:
    if (dirpath == None) or (not dirpath.is_dir()):
        return {}
    file_count: int = 0
    flaky_tests_decls: FlakeDecls = {}
    errors: List[str] = []
    for item in [
            e for e in os.listdir(dirpath)
            if e.endswith(FLAKY_TEST_RECORD_FILE_SUFFIX)
    ]:
        path = Path(dirpath, item)
        if not path.is_file():
            continue
        file_count += 1
        with open(path, 'r') as f:
            _parse_file(f, path, flaky_tests_decls, errors)
    if len(errors) > 0:
        sys.exit('\n'.join(errors))
    if file_count == 0:
        sys.stderr.write("[Warning] no file is named *%s under %s\n" %
                         (FLAKY_TEST_RECORD_FILE_SUFFIX, dirpath))
    return flaky_tests_decls


EXAMPLE_STRING_STREAM = StringIO("""{
  "lorem_1": {
    "errors": [
      "wrong_exit_code"
    ],
    "reason": "blah"
  },
  "lorem_2": {
    "errors": [
      "timeout",
      "signal"
    ]
  }
}""")


def smoke_test():
    decls = {}
    errors = []
    _parse_file(EXAMPLE_STRING_STREAM, Path("[smoketest]"), decls, errors)
    print(decls)
    print(errors)


if __name__ == "__main__":  # Smoke testing.
    sys.exit(smoke_test())
