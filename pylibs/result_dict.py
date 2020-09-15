# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the LICENSE.txt file.

import collections
import os
from typing import Optional

INFINITE_TIME = 0  # it means effectively infinite time required by timer

# exit type: Sync with EXPLANATION_STRING
EXIT_TYPE_TO_FLAKINESS_ERR = {
    # key: exit type in timer report
    # val: possible flakiness error type in flakiness declaration file
    "return": "WrongExitCode",
    "timeout": "Timeout",
    "signal": "Signal",
    "quit": "Others",
    "unknown": "Others"
}


# NOTE this function is called ONLY IF there is an error
def check_if_error_is_flaky(expected_errs: list, actual_exit_type: str,
                            has_stdout_diff: bool) -> bool:
    if len(expected_errs) == 0:
        return False
    # NOTE expected_errs might only cover one of the errors
    if has_stdout_diff == True and ("StdoutDiff" not in expected_errs):
        return False
    return EXIT_TYPE_TO_FLAKINESS_ERR[actual_exit_type] in expected_errs


# Used by did_run_one()
def generate_result_dict(metadata: dict, ctimer_reports: dict, match_exit: bool,
                         write_golden: bool, start_abs_time: float,
                         end_abs_time: float, stdout_filename: Optional[str],
                         diff_filename: Optional[str],
                         exceptions: list) -> collections.OrderedDict:
    all_ok = match_exit and diff_filename == None
    golden_filename = os.path.abspath(
        metadata["golden"]) if metadata["golden"] else None
    error_is_flaky = None
    if not all_ok:
        error_is_flaky = check_if_error_is_flaky(metadata["flaky_errors"],
                                                 ctimer_reports["exit"]["type"],
                                                 diff_filename != None)
    return collections.OrderedDict([
        # success
        ("ok", all_ok),  # boolean
        ("error_is_flaky",
         error_is_flaky),  # boolean, or None for all_ok == True
        # metadata
        ("desc", metadata["desc"]),  # str
        ("path", metadata["path"]),  # str
        ("args", metadata["args"]),  # list
        ("envs", metadata["envs"]),  # dict or None
        ("prefix", metadata["prefix"]),  # list
        ("hashed_id", metadata["hashed_id"]),
        ("flaky_errors",
         metadata["flaky_errors"]),  # list of str, the expected errors
        ("repeat", metadata["repeat"]),  # dict { "count": int, "all": int }
        # memory usage measurements
        ("maxrss_kb", ctimer_reports["maxrss_kb"]),
        # time measurements
        ("timeout_ms", metadata["timeout_ms"]
         if metadata["timeout_ms"] != None else INFINITE_TIME),  # int
        ("times_ms",
         collections.OrderedDict([
             ("proc", ctimer_reports["times_ms"]["total"]),
             ("abs_start", start_abs_time * 1000.0),
             ("abs_end", end_abs_time * 1000.0),
         ])),
        # details:
        (
            "exit",
            collections.OrderedDict([
                ("ok", match_exit
                 ),  # boolean: exit type and repr both match with expected
                # "type"  : string - "return", "timeout", "signal", "quit", "unknown"
                # "repr"  : integer, indicating the exit code for "return" exit, timeout
                #     value (millisec, processor time) for "timeout" exit, signal
                #     value "signal" exit, and null for others (timer errors)
                (
                    "expected",
                    collections.OrderedDict([
                        ("type", metadata["exit"]["type"]),  # str
                        ("repr", metadata["exit"]["repr"])  # int
                    ])),
                (
                    "real",
                    collections.OrderedDict([
                        ("type", ctimer_reports["exit"]["type"]),  # str
                        ("repr", ctimer_reports["exit"]["repr"])  # int
                    ])),
            ])),
        (
            "stdout",
            collections.OrderedDict([
                # boolean, or None for '--write-golden' NOTE it is True if there's no need to compare
                ("ok", None if write_golden else (diff_filename == None)),
                # abs path (str), or None meaning no need to compare
                ("golden_file", golden_filename),
                # abs path (str), or None meaning no stdout or written to golden file
                ("actual_file", stdout_filename),
                # abs path (str), or None meaning 1) if "golden_file" == None: no need to compare
                #                              or 2) if "golden_file" != None: no diff found
                (
                    "diff_file", diff_filename
                )  # str, or None if there's no need to compare or no diff found
            ])),
        (
            "exceptions", exceptions
        )  # list of str, describe errors encountered in run_one() (not in test)
    ])  # NOTE any changes (key, value, meaning) made in this data structure must be honored in view.py
