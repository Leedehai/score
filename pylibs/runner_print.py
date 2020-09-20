# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the LICENSE.txt file.

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pylibs import rotating_logger
from pylibs import score_utils
from pylibs.rotating_logger import (
    LogAction,
    LogMessage,
)
from pylibs.runner_common import (
    Args,
    TaskMetadata,
    TaskResult,
    TaskExceptions,
    GOLDEN_NOT_WRITTEN_PREFIX,
    LOG_FILE_BASE,
)

IS_ATTY = sys.stdin.isatty() and sys.stdout.isatty()
TERMINAL_COLS = int(os.popen('stty size',
                             'r').read().split()[1]) if IS_ATTY else 70
if TERMINAL_COLS <= 25:
    score_utils.err_exit(
        score_utils.error_s("terminal width (%d) is rediculously small" %
                            TERMINAL_COLS))


def cap_width(s: str, width: int = TERMINAL_COLS) -> str:
    extra_space = width - len(s)
    return s if extra_space >= 0 else (s[:12] + "..." + s[len(s) - width - 15:])


def get_error_summary(task_result: TaskResult) -> Dict[str, Optional[str]]:
    if task_result["exit"]["ok"] == False:
        # do not use str(dir(..)): have ugly 'u' prefixes for Unicode strings
        real_exit = task_result["exit"]["real"]
        exit_error = "{ type: %s, repr: %s }" % (real_exit["type"],
                                                 real_exit["repr"])
    else:
        exit_error = None
    diff_file = task_result["stdout"]["diff_file"]
    if diff_file != None:
        diff_file_hyperlink = score_utils.hyperlink_str(
            diff_file, description=os.path.basename(diff_file))
    else:
        diff_file_hyperlink = None
    return {
        # str, or None if exit is ok.
        "exit": exit_error,
        # str, or None if no need to compare or no diff found.
        "diff": diff_file_hyperlink,
    }


def print_one_task_realtime_log(
    metadata: TaskMetadata,
    run_one_single_result: TaskResult,
) -> None:
    # below is printing on the fly
    if metadata["repeat"]["all"] > 1:
        metadata_desc = "%d/%d %s" % (metadata["repeat"]["count"],
                                      metadata["repeat"]["all"], metadata["id"])
    else:
        metadata_desc = metadata["id"]
    is_ok = run_one_single_result["ok"]  # Successful run.
    should_stay_on_console = False
    if is_ok:
        status_head = "\x1b[36mok\x1b[0m"
    else:  # test error
        if run_one_single_result["error_is_flaky"]:
            status_head = "\x1b[36mflaky error\x1b[0m"
        else:  # definite error
            should_stay_on_console = True
            status_head = "\x1b[33;1merror\x1b[0m"
    error_summary = get_error_summary(run_one_single_result)
    if should_stay_on_console:  # definite error, details will be printed after all execution
        proper_text = "%s\n\x1b[2m%s\x1b[0m\n" % (metadata_desc, '\n'.join([
            "  %s: %s" % (k, v) for k, v in error_summary.items() if v != None
        ]))
        rotating_logger.send_log(
            LogMessage.serialize(LogAction.ADD_PERSISTENT, status_head,
                                 proper_text))
    else:  # definite success, flaky success, flaky error
        proper_text = cap_width(metadata_desc) + '\n'
        rotating_logger.send_log(
            LogMessage.serialize(LogAction.ADD_TRANSIENT, status_head,
                                 proper_text))


def count_and_print_for_test_running(
    result_list: List[TaskResult],
    timer_prog: str,
) -> Tuple[int, int]:
    error_task_count, unique_error_tests = 0, set()
    for result in result_list:
        if result["ok"] == False and result["error_is_flaky"] == False:
            error_task_count += 1
            unique_error_tests.add(result["hashed_id"])
        print_test_running_result_to_stderr(result, timer_prog)
    return error_task_count, len(unique_error_tests)


POST_PROCESSING_SUMMARY_TEMPLATE = """\
{color}{bold}{status}{no_color}{color} total {total_task_info}, time {time}
  summary: {error_count_info}
  raw log: {log_path}{no_color}"""


def print_summary_report(
    args: Args,
    num_tasks: int,
    result_list: List[TaskResult],
    master_log_filepath: Path,
    time_sec: float,
) -> Tuple[int, int]:
    assert len(result_list) == num_tasks
    if args.write_golden:
        error_task_count = count_and_print_for_golden_writing(
            result_list, args.timer)
        unique_error_task_count = error_task_count
    else:
        error_task_count, unique_error_task_count = \
            count_and_print_for_test_running(result_list, args.timer)
    assert unique_error_task_count <= error_task_count
    color = "" if not IS_ATTY else (
        "\x1b[32m" if error_task_count == 0 else "\x1b[38;5;203m")
    total_task_info = "%s (unique: %s)" % (num_tasks,
                                           int(num_tasks / args.repeat))
    error_count_info = ("all passed" if error_task_count == 0 else
                        ("unexpected error %s (unique: %s)" %
                         (error_task_count, unique_error_task_count)))
    sys.stderr.write(
        POST_PROCESSING_SUMMARY_TEMPLATE.format(
            color=color,
            bold="\x1b[1m" if IS_ATTY else "",
            no_color="\x1b[0m" if IS_ATTY else "",
            status="✓ SUCCESS" if error_task_count == 0 else "! ERROR",
            total_task_info=total_task_info,
            error_count_info=error_count_info,
            time="%.3f sec" % time_sec,
            log_path=score_utils.hyperlink_str(  # Clickable link if possible
                os.path.relpath(master_log_filepath),
                description=LOG_FILE_BASE)) + "\n")
    return error_task_count, unique_error_task_count


def count_and_print_for_golden_writing(
    result_list: List[TaskResult],
    timer_prog: str,
) -> int:
    error_task_count = 0
    golden_written_count = 0
    golden_same_content_count, golden_wrong_exit_count = 0, 0
    for result in result_list:
        assert result["stdout"]["golden_file"] != None
        if result["ok"] == False:
            error_task_count += 1
        written_or_not = print_golden_overwriting_result_to_stderr(
            result, timer_prog)
        if written_or_not == TaskExceptions.GOLDEN_NOT_WRITTEN_SAME_CONTENT:
            golden_same_content_count += 1
        elif written_or_not == TaskExceptions.GOLDEN_NOT_WRITTEN_WRONG_EXIT:
            golden_wrong_exit_count += 1
        elif not written_or_not:
            golden_written_count += 1
    sys.stderr.write("Golden file writing:\n")
    sys.stderr.write(
        "\t%d written, %d skipped (same content: %d, error: %d)\n" %
        (golden_written_count,
         golden_same_content_count + golden_wrong_exit_count,
         golden_same_content_count, golden_wrong_exit_count))
    return error_task_count


UNEXPECTED_ERROR_FORMAT = """\n\x1b[33m[unexpected error] {desc}\x1b[0m{repeat}
{error_summary}
\x1b[2m{rerun_command}\x1b[0m
"""


# when not using '--write-golden'
def print_test_running_result_to_stderr(result: TaskResult, timer: str) -> None:
    rerun_command = score_utils.make_command_invocation_str(timer,
                                                            result,
                                                            indent=2)
    if result["ok"] == True or result["error_is_flaky"] == True:
        return
    assert result["ok"] == False
    result_exceptions = [TaskExceptions(e) for e in result["exceptions"]]
    if len(result_exceptions) > 0:
        assert (len(result_exceptions) == 1
                and result_exceptions[0] == TaskExceptions.GOLDEN_FILE_MISSING)
        error_summary = "%s: %s" % (TaskExceptions.GOLDEN_FILE_MISSING,
                                    os.path.relpath(
                                        result["stdout"]["golden_file"]))
    else:
        error_summary = get_error_summary(result)
        error_summary = '\n'.join([
            "  %s: %s" % (k, v) for k, v in error_summary.items() if v != None
        ])
    if result["repeat"]["all"] > 1:
        repeat_report = " (repeat %d/%d)" % (result["repeat"]["count"],
                                             result["repeat"]["all"])
    else:
        repeat_report = ""
    sys.stderr.write(
        UNEXPECTED_ERROR_FORMAT.format(desc=result["id"],
                                       repeat=repeat_report,
                                       error_summary=error_summary,
                                       rerun_command=rerun_command))


# when using '--write-golden'
def print_golden_overwriting_result_to_stderr(
        result: TaskResult, timer: str) -> Optional[TaskExceptions]:
    attempted_golden_file: str = result["stdout"]["golden_file"]  # abs path
    not_written_exceptions = [
        TaskExceptions(e) for e in result["exceptions"]
        if e.startswith(GOLDEN_NOT_WRITTEN_PREFIX)
    ]
    assert len(not_written_exceptions) <= 1
    hyperlink_to_golden_file = score_utils.hyperlink_str(
        attempted_golden_file, os.path.relpath(attempted_golden_file))
    if len(not_written_exceptions) == 0:
        sys.stderr.write("\n\x1b[36m[ok: new or modified] %s\x1b[0m\n"
                         "  \x1b[2mwritten: %s (%d B)\x1b[0m\n" %
                         (result["id"], hyperlink_to_golden_file,
                          os.path.getsize(attempted_golden_file)))
        return None
    assert len(not_written_exceptions) == 1
    if TaskExceptions.GOLDEN_NOT_WRITTEN_SAME_CONTENT in not_written_exceptions:
        sys.stderr.write("\n\x1b[36m[ok: same content] %s\x1b[0m\n"
                         "  \x1b[2mskipped: %s\x1b[0m\n" %
                         (result["id"], hyperlink_to_golden_file))
        return TaskExceptions.GOLDEN_NOT_WRITTEN_SAME_CONTENT
    if TaskExceptions.GOLDEN_NOT_WRITTEN_WRONG_EXIT in not_written_exceptions:
        rerun_command = score_utils.make_command_invocation_str(timer,
                                                                result,
                                                                indent=2)
        sys.stderr.write(
            "\n\x1b[33m[error: unexpected exit status] %s\x1b[0m\n"
            "  \x1b[2mskipped: %s\n%s\x1b[0m\n" %
            (result["id"], hyperlink_to_golden_file, rerun_command))
        return TaskExceptions.GOLDEN_NOT_WRITTEN_WRONG_EXIT  # the only one item
    raise RuntimeError("should not reach here")
