# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the MIT LICENSE.txt file.

import os
from typing import Any, List, Optional, OrderedDict

INFINITE_TIME = 0  # it means effectively infinite time required by timer

TaskResult = OrderedDict[str, Any]  # i.e. collections.OrderedDict

# exit type: Sync with EXPLANATION_STRING
EXIT_TYPE_TO_FLAKINESS_ERR = {
    # key: exit type in timer report
    # val: possible flakiness error type in flakiness declaration file
    # NOTE No "stdout_diff" here.
    "return": "wrong_exit_code",
    "timeout": "timeout",
    "signal": "signal",
    "quit": "quit",
    "unknown": "unknown"
}


# NOTE this function is called ONLY IF there is an error
def check_if_error_is_flaky(
    expected_errs: List[str],
    actual_exit_type: str,
    has_stdout_diff: bool,
) -> bool:
    if len(expected_errs) == 0:
        return False
    # NOTE expected_errs might only cover one of the errors
    if has_stdout_diff == True and ("stdout_diff" not in expected_errs):
        return False
    return EXIT_TYPE_TO_FLAKINESS_ERR[actual_exit_type] in expected_errs


# Used by did_run_one()
def generate_result_dict(
    metadata: dict,
    ctimer_reports: dict,
    match_exit: bool,
    write_golden: bool,
    start_abs_time: float,
    end_abs_time: float,
    stdout_filename: Optional[str],
    diff_filename: Optional[str],
    exceptions: list,
) -> TaskResult:
    all_ok = match_exit and diff_filename == None
    golden_filename = os.path.abspath(
        metadata["golden"]) if metadata["golden"] else None
    error_is_flaky = None
    if not all_ok:
        error_is_flaky = check_if_error_is_flaky(metadata["flaky_errors"],
                                                 ctimer_reports["exit"]["type"],
                                                 diff_filename != None)
    return TaskResult([
        # Success.
        ("ok", all_ok),  # bool
        ("error_is_flaky", error_is_flaky),  # bool, or None if all_ok == True

        # Metadata.
        ("id", metadata["id"]),  # str
        ("path", metadata["path"]),  # str
        ("args", metadata["args"]),  # list of str
        ("envs", metadata["envs"]),  # dict or None
        ("prefix", metadata["prefix"]),  # list of str
        ("hashed_id", metadata["hashed_id"]),
        (
            "flaky_errors",
            metadata["flaky_errors"],  # list of str, the tolerable errors
        ),

        # Each test may be repeated k times (resulting in k task results).
        # dict { "count": int, "all": int }
        ("repeat", metadata["repeat"]),

        # Memory usage measurements.
        ("maxrss_kb", ctimer_reports["maxrss_kb"]),

        # Time measurements.
        (
            "timeout_ms",
            metadata["timeout_ms"]
            if metadata["timeout_ms"] != None else INFINITE_TIME,
        ),
        (
            "times_ms",
            OrderedDict([
                ("proc", ctimer_reports["times_ms"]["total"]),
                ("abs_start", start_abs_time * 1000.0),
                ("abs_end", end_abs_time * 1000.0),
            ]),
        ),

        # Details of exit status.
        (
            "exit",
            OrderedDict([
                ("ok", match_exit),  # bool
                # "type"  : string - "return", "timeout", "signal", "quit", "unknown"
                # "repr"  : integer, indicating the exit code for "return" exit, timeout
                #     value (millisec, processor time) for "timeout" exit, signal
                #     value "signal" exit, and null for others (timer errors)
                (
                    "expected",
                    OrderedDict([
                        ("type", metadata["exit"]["type"]),  # str
                        ("repr", metadata["exit"]["repr"])  # int
                    ]),
                ),
                (
                    "real",
                    OrderedDict([
                        ("type", ctimer_reports["exit"]["type"]),  # str
                        ("repr", ctimer_reports["exit"]["repr"])  # int
                    ]),
                ),
            ]),
        ),

        # Details of stdout.
        (
            "stdout",
            OrderedDict([
                # boolean, or None for '--write-golden' NOTE it is True if there's no need to compare
                ("ok", None if write_golden else (diff_filename == None)),
                # abs path (str), or None meaning no need to compare
                ("golden_file", golden_filename),
                # abs path (str), or None meaning 1) no stdout,
                #                              or 2) stdout written to golden file
                ("actual_file", stdout_filename),
                # abs path (str), or None meaning 1) if "golden_file" == None: no need to compare
                #                              or 2) if "golden_file" != None: no diff found
                ("diff_file", diff_filename),
            ]),
        ),

        # List of str, describe errors encountered in run_one() (not in test).
        ("exceptions", [e.value for e in exceptions])
    ])  # NOTE any changes (key, value, meaning) made in this data structure must be honored in score_ui.py
