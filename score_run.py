#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: score_run.py
# ---------------------------
# Run tests with timer, logging, and HTML diff view (if any).
# For more information, see README.md.
# For help: use '--help' and '--docs'.
# NOTE all non-help messages are printed to stderr because stderr is
#      unbuffered by default so it works well with multiprocessing.
#
# Migrated from Python2.7; new features not all applied yet.
# Type hinting does not use the module 'typing', because importing it
# entails runtime overhead in early releases of Python3.

import sys
py = sys.version_info
if py.major == 2 or (py.major == 3 and py.minor < 5):
    sys.exit("[Error] mininum Python version is 3.5")

import argparse
import collections
import copy
import hashlib
import json
import multiprocessing
import multiprocessing.dummy as mp  # threading wrapped using multiprocessing API
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import time

import score_utils
from score_utils import info_s, error_s
from diff_html_str import get_diff_html_str
from flakiness import parse_flakiness_decls
from result_dict import generate_result_dict

# avoid *.pyc of imported modules
sys.dont_write_bytecode = True

LOG_FILE_BASE = "log.json"
CTIMER_DELIMITER_ENVKEY = "CTIMER_DELIMITER"
CTIMER_TIMEOUT_ENVKEY = "CTIMER_TIMEOUT"
DELIMITER_STR = "#####"

IS_ATTY = sys.stdin.isatty() and sys.stdout.isatty()
TERMINAL_COLS = int(os.popen('stty size',
                             'r').read().split()[1]) if IS_ATTY else 70
if TERMINAL_COLS <= 25:
    sys.exit(
        error_s("terminal width (%d) is rediculously small" % TERMINAL_COLS))

Args = argparse.Namespace


def get_num_workers(env_var: str) -> int:
    env_num_workers = os.environ.get(env_var, "")
    if len(env_num_workers) > 0:
        try:
            env_num_workers_number = int(env_num_workers)
        except ValueError:
            sys.exit(error_s("env vairable '%s' is not an integer" % env_var))
        if env_num_workers_number <= 0:
            sys.exit(error_s("env variable '%s' is not positive" % env_var))
        return env_num_workers_number
    return multiprocessing.cpu_count()


NUM_WORKERS_MAX = get_num_workers(
    env_var="NUM_WORKERS")  # not "NUM_WORKERS_MAX", to be consistent

# Possible exceptions (not Python's Exceptions) for user inputs
GOLDEN_NOT_WRITTEN_PREFIX = "golden file not written"
GOLDEN_NOT_WRITTEN_SAME_CONTENT = "%s: content is the same" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_NOT_WRITTEN_WRONG_EXIT = "%s: the test's exit is not as expected" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_FILE_MISSING = "golden file missing"


# Set signal handlers
def sighandler(sig, frame):
    # Do not print: it's ugly for all workers to print together
    sys.exit(1)


signal.signal(signal.SIGINT, sighandler)  # type: ignore
signal.signal(signal.SIGTERM, sighandler)  # type: ignore
signal.signal(signal.SIGABRT, sighandler)  # type: ignore
signal.signal(signal.SIGSEGV, sighandler)  # type: ignore


def cap_width(s: str, width: int = TERMINAL_COLS) -> str:
    extra_space = width - len(s)
    return s if extra_space >= 0 else (s[:12] + "..." + s[len(s) - width - 15:])


def get_metadata_from_path(path: str) -> dict:
    # docs: see EXPLANATION_STRING below
    return {
        "desc": "", "path": path, "args": [], "envs": None, "golden": None,
        "timeout_ms": None, "exit": {"type": "return", "repr": 0}
    }


# Run mp.Pool.map()
# NOTE the try-except block is to handle KeyboardInterrupt cleanly to fix a flaw
# in Python: KeyboardInterrupt cannot cleanly kill mp.Pool()'s child processes,
# printing verbosely: https://stackoverflow.com/a/6191991/8385554
# NOTE each 'func' has to ignore SIGINT for the aforementioned fix to work
# NOTE do not use 'threading' due to GIL (global interpreter lock)
def pool_map(num_workers: int, func, inputs: list) -> list:
    def init_shared_mem(lock, queue, count):
        global g_lock
        g_lock = lock
        global g_queue
        g_queue = queue
        global g_count
        g_count = count

    l = mp.Lock()
    q, c = mp.Queue(5), mp.Value('i', 0)
    pool = mp.Pool(num_workers, initializer=init_shared_mem, initargs=(l, q, c))
    try:
        res = pool.map(func, inputs)
        clear_rotating_log(q)
    except KeyboardInterrupt:
        pool.terminate()
        pool.join()
        sys.exit("Process pool terminated and child processes joined")
    pool.close()
    pool.join()
    return res


def split_ctimer_out(s: str) -> tuple:
    ctimer_begin_index = s.find(DELIMITER_STR)
    if ctimer_begin_index == -1:
        raise RuntimeError("beginning delimiter of ctimer stats not found")
    inspectee_stdout = s[:ctimer_begin_index]
    report_end_index = s.rfind(DELIMITER_STR)
    if report_end_index == -1:
        raise RuntimeError("end delimiter of ctimer stats not found")
    ctimer_stdout = s[ctimer_begin_index + len(DELIMITER_STR):report_end_index]
    return inspectee_stdout.rstrip(), ctimer_stdout.rstrip()


# N = 16^8 = 2^32 => ~N^(1/2) = ~2^16 values produces a collision with P=50%
# Here we ignore SHA1's hash collision vulnerabilities, because we are not doing
# cryptography and we don't expect users to try to break their own tests.
CASE_ID_HASH_LEN = 8  # NOTE value should sync with EXPLANATION_STRING below


# prog = "foo", args = [], envs = {}              => return: "foo-00000000"
# prog = "baz/bar/foo", args = [], envs = {}      => return: "bar/foo-00000000"
# prog = "baz/bar/foo", args = [ '9' ], envs = {} => return: "bar/foo-0ade7c2c"
def compute_comb_id(prog: str, args: list, envs: dict) -> str:
    prog_basename = os.path.basename(prog)
    prog_dir_basename = os.path.basename(
        os.path.dirname(prog))  # "" if prog doesn't contain '/'
    path_repr = os.path.join(prog_dir_basename, prog_basename)
    case_hash = '0' * CASE_ID_HASH_LEN
    if len(args) > 0 or len(envs) > 0:
        items_to_hash = args + [("$%s=%s" % (k, envs[k]))
                                for k in sorted(envs.keys())]
        case_hash = hashlib.sha1(
            ' '.join(items_to_hash).encode()).hexdigest()[:CASE_ID_HASH_LEN]
    return "%s-%s" % (path_repr, case_hash.lower())


# This path stem (meaning there is no extension such as ".diff") is made of the
# comb_id, repeat count, log_dirname. E.g.
# comb_id = "bar/foo-0ade7c2c", repeat 3 out of 1~10, log_dirname = "./out/foo/logs"
#   => return: "./out/foo/logs/bar/foo-0ade7c2c-3"
def get_logfile_path_stem(
        comb_id: str, repeat_count: int, log_dirname: str
) -> str:  # "stem" means no extension name such as ".diff"
    return "%s-%s" % (os.path.join(log_dirname, comb_id), repeat_count)


UNEXPECTED_ERROR_FORMAT = """\n\x1b[33m[unexpected error] {desc}\x1b[0m{repeat}
{error_summary}
\x1b[2m{rerun_command}\x1b[0m
"""


# when not using '--write-golden'
def print_test_running_result_to_stderr(result: dict, timer: str) -> None:
    rerun_command = score_utils.make_command_invocation_str(timer,
                                                            result,
                                                            indent=2)
    if result["ok"] == True or result["error_is_flaky"] == True:
        pass
    else:
        assert result["ok"] == False
        result_exceptions = result["exceptions"]
        if len(result_exceptions) > 0:
            assert (len(result_exceptions) == 1
                    and result_exceptions[0] == GOLDEN_FILE_MISSING)
            error_summary = "%s: %s" % (GOLDEN_FILE_MISSING,
                                        os.path.relpath(
                                            result["stdout"]["golden_file"]))
        else:
            error_summary = get_error_summary(result)
            error_summary = '\n'.join([
                "  %s: %s" % (k, v) for k, v in error_summary.items()
                if v != None
            ])
        if result["repeat"]["all"] > 1:
            repeat_report = " (repeat %d/%d)" % (result["repeat"]["count"],
                                                 result["repeat"]["all"])
        else:
            repeat_report = ""
        sys.stderr.write(
            UNEXPECTED_ERROR_FORMAT.format(desc=result["desc"],
                                           repeat=repeat_report,
                                           error_summary=error_summary,
                                           rerun_command=rerun_command))


# when using '--write-golden'
def print_golden_overwriting_result_to_stderr(result: dict, timer: str):
    attempted_golden_file: str = result["stdout"]["golden_file"]  # abs path
    not_written_exceptions = [
        e for e in result["exceptions"]
        if e.startswith(GOLDEN_NOT_WRITTEN_PREFIX)
    ]
    assert len(not_written_exceptions) <= 1
    hyperlink_to_golden_file = score_utils.hyperlink_str(
        attempted_golden_file, os.path.relpath(attempted_golden_file))
    if len(not_written_exceptions) == 0:
        sys.stderr.write("\n\x1b[36m[ok: new or modified] %s\x1b[0m\n"
                         "  \x1b[2mwritten: %s (%d B)\x1b[0m\n" %
                         (result["desc"], hyperlink_to_golden_file,
                          os.path.getsize(attempted_golden_file)))
        return None
    assert len(not_written_exceptions) == 1
    if GOLDEN_NOT_WRITTEN_SAME_CONTENT in not_written_exceptions:
        sys.stderr.write("\n\x1b[36m[ok: same content] %s\x1b[0m\n"
                         "  \x1b[2mskipped: %s\x1b[0m\n" %
                         (result["desc"], hyperlink_to_golden_file))
        return GOLDEN_NOT_WRITTEN_SAME_CONTENT
    if GOLDEN_NOT_WRITTEN_WRONG_EXIT in not_written_exceptions:
        rerun_command = score_utils.make_command_invocation_str(timer,
                                                                result,
                                                                indent=2)
        sys.stderr.write(
            "\n\x1b[33m[error: unexpected exit status] %s\x1b[0m\n"
            "  \x1b[2mskipped: %s\n%s\x1b[0m\n" %
            (result["desc"], hyperlink_to_golden_file, rerun_command))
        return GOLDEN_NOT_WRITTEN_WRONG_EXIT  # the only one item
    raise RuntimeError("should not reach here")


def create_dir_if_needed(dirname: str) -> None:
    # NOTE use EAFP (Easier to Ask for Forgiveness than Permission) principle here, i.e.
    # use try-catch to handle the situation where the directory was already created by
    # another process.
    # EAFP can avoid the race condition caused by LBYL (Look Before You Leap): use a
    # if-statement to check the absence of the target directory before creating it.
    # Using lock can also avoid the race condition, but it is cumbersome in Python.
    # Unlike other languages, try-catch doesn't add a noticeable overhead in Python.
    try:
        os.makedirs(dirname)  # create intermediate dirs if necessary
    except OSError:  # Python2 throws OSError, Python3 throws its subclass FileExistsError
        pass  # dir already exists (due to multiprocessing)


# can be used concurrently
def write_file(filename: str,
               s: str,
               assert_str_non_empty: bool = False) -> None:
    assert s != None
    if assert_str_non_empty:
        assert s != ""
    create_dir_if_needed(os.path.dirname(filename))
    with open(filename, 'w') as f:
        f.write(s)


def process_inspectee_stdout(s: str) -> str:
    return re.sub(r"\x1b\[.*?m", "", s)  # remove color sequences


def get_error_summary(result_obj: dict) -> dict:
    if result_obj["exit"]["ok"] == False:
        # do not use str(dir(..)): have ugly 'u' prefixes for unicode strings
        real_exit = result_obj["exit"]["real"]
        exit_error = "{ type: %s, repr: %s }" % (real_exit["type"],
                                                 real_exit["repr"])
    else:
        exit_error = None
    diff_file = result_obj["stdout"]["diff_file"]
    if diff_file != None:
        diff_file_hyperlink = score_utils.hyperlink_str(
            diff_file, description=os.path.basename(diff_file))
    else:
        diff_file_hyperlink = None
    return {
        "exit": exit_error,  # str, or None if exit is ok
        "diff": diff_file_hyperlink,  # str, or None if no need to compare or no diff found
    }


# Used by run_one_impl()
PLATFORM_INFO = {
    "os": "%s %s" %
    (platform.system().lower(), platform.machine().replace("x86_64", "x64")),
    "python": platform.python_version(),
    "cwd": os.getcwd(),  # abs path
}


def did_run_one(log_dirname: str, write_golden: bool, metadata: dict,
                inspectee_stdout: str, ctimer_stdout: str,
                start_abs_time: float, end_abs_time: float,
                timer: str) -> collections.OrderedDict:
    assert len(ctimer_stdout) > 0
    ctimer_dict = json.loads(ctimer_stdout)
    match_exit = (metadata["exit"]["type"] == ctimer_dict["exit"]["type"]
                  and metadata["exit"]["repr"] == ctimer_dict["exit"]["repr"])
    exceptions = [
    ]  # list of str, describe misc errors in run_one() itself (not in test)
    filepath_stem = get_logfile_path_stem(  # "stem" means no extension name
        metadata["comb_id"], metadata["repeat"]["count"], log_dirname)
    stdout_filename = None if write_golden else os.path.abspath(filepath_stem +
                                                                ".stdout")
    diff_filename = None  # will be given a str if there is need to compare and diff is found
    if stdout_filename:
        assert not write_golden
        write_file(stdout_filename, inspectee_stdout)  # stdout could be ""
    if metadata["golden"] != None:  # write golden or compare stdout with golden
        golden_filename = metadata["golden"]
        if write_golden:  # write stdout to golden
            if match_exit:
                golden_exists_and_same = False
                if os.path.isfile(golden_filename):
                    with open(golden_filename, 'r') as f:
                        if f.read() == inspectee_stdout:
                            golden_exists_and_same = True
                            exceptions.append(GOLDEN_NOT_WRITTEN_SAME_CONTENT)
                if not golden_exists_and_same:
                    write_file(golden_filename,
                               inspectee_stdout)  # stdout could be ""
            else:
                exceptions.append(GOLDEN_NOT_WRITTEN_WRONG_EXIT)
        else:  # compare stdout with golden
            assert stdout_filename
            found_golden, stdout_comparison_diff = get_diff_html_str(
                html_title=filepath_stem.split(os.sep)[-1],
                platform_info=PLATFORM_INFO,
                desc=metadata["desc"],
                driver=metadata["path"],
                command_invocation=score_utils.make_command_invocation_str(
                    timer, metadata, indent=2),
                expected_filename=golden_filename,
                actual_filename=stdout_filename,
            )
            if not found_golden:
                exceptions.append(GOLDEN_FILE_MISSING)
            if stdout_comparison_diff != None:  # write only if diff is not empty
                diff_filename = os.path.abspath(filepath_stem + ".diff.html")
                write_file(diff_filename,
                           stdout_comparison_diff,
                           assert_str_non_empty=True)
    return generate_result_dict(metadata, ctimer_dict, match_exit, write_golden,
                                start_abs_time, end_abs_time, stdout_filename,
                                diff_filename, exceptions)


# Used by run_one_impl()
def print_one_on_the_fly(metadata: dict, run_one_single_result: dict) -> None:
    # below is printing on the fly
    if metadata["repeat"]["all"] > 1:
        metadata_desc = "%d/%d %s" % (metadata["repeat"]["count"],
                                      metadata["repeat"]["all"],
                                      metadata["desc"])
    else:
        metadata_desc = metadata["desc"]
    is_ok = run_one_single_result["ok"]  # successful run
    should_stay_on_console = False
    if is_ok:
        if len(run_one_single_result["flaky_errors"]) > 0:
            status_head = "\x1b[36mflaky ok\x1b[0m"
        else:  # definite success
            status_head = "\x1b[36mok\x1b[0m"
    else:  # test error
        if run_one_single_result["error_is_flaky"]:
            status_head = "\x1b[36mflaky error\x1b[0m"
        else:  # definite error
            should_stay_on_console = True
            status_head = "\x1b[33;1merror\x1b[0m"
    with global_lock():
        # keep runtime overhead here as small as possible
        g_count.value += 1
        error_summary = get_error_summary(run_one_single_result)
        if should_stay_on_console:  # definite error, details will be printed after all execution
            logline = "%s %3s %s\n\x1b[2m%s\x1b[0m\n" % (
                status_head, g_count.value, metadata_desc, '\n'.join([
                    "  %s: %s" % (k, v)
                    for k, v in error_summary.items() if v != None
                ]))
            clear_rotating_log(g_queue)
            sys.stderr.write(logline)
        else:  # definite success, flaky success, flaky error
            logline = cap_width(
                "%s %3s %s" %
                (status_head, g_count.value, metadata_desc)) + '\n'
            add_rotating_log(g_queue, logline)
            time.sleep(
                0.05
            )  # let the line stay for a while: prettier, though adding overhead
        sys.stderr.flush()


# Used by run_all()
def remove_prev_log(log_dir: str) -> None:
    if os.path.isdir(log_dir):
        # to prevent perplexing cases e.g. master log says all is good, but *.diff files
        # from a previous run exist
        shutil.rmtree(log_dir)
    elif os.path.exists(log_dir):
        sys.exit(error_s("path exists as a non-directory: %s" % log_dir))


POST_PROCESSING_SUMMARY_TEMPLATE = """\
{color}{bold}{status}{no_color}{color} total {total_task_info}, time {time}
  summary: {error_count_info}
  raw log: {log_path}{no_color}"""


# Used by run_all()
def print_post_processing_summary(args: Args, num_tasks: int, result_list: list,
                                  master_log_filepath: str,
                                  time_sec: float) -> tuple:
    assert len(result_list) == num_tasks
    if args.write_golden:
        error_count, unique_error_count = count_and_print_for_golden_writing(
            result_list, args.timer)
    else:
        error_count, unique_error_count = count_and_print_for_test_running(
            result_list, args.timer)
    assert unique_error_count <= error_count
    color = "" if not IS_ATTY else (
        "\x1b[32m" if error_count == 0 else "\x1b[38;5;203m")
    total_task_info = "%s (unique: %s)" % (num_tasks,
                                           int(num_tasks / args.repeat))
    error_count_info = ("all passed" if error_count == 0 else
                        ("unexpected error %s (unique: %s)" %
                         (error_count, unique_error_count)))
    sys.stderr.write(
        POST_PROCESSING_SUMMARY_TEMPLATE.format(
            color=color,
            bold="\x1b[1m" if IS_ATTY else "",
            no_color="\x1b[0m" if IS_ATTY else "",
            status="✓ SUCCESS" if error_count == 0 else "! ERROR",
            total_task_info=total_task_info,
            error_count_info=error_count_info,
            time="%.3f sec" % time_sec,
            log_path=score_utils.hyperlink_str(  # Clickable link if possible
                os.path.relpath(master_log_filepath),
                description=LOG_FILE_BASE)) + "\n")
    return error_count, unique_error_count


# Used by print_post_processing_summary(), returns error count and unique
# error count (unique error count <= error count, because of args.repeat)
def count_and_print_for_golden_writing(result_list: list,
                                       timer_prog: str) -> tuple:
    error_result_count = 0
    golden_written_count = 0
    golden_same_content_count, golden_wrong_exit_count = 0, 0
    for result in result_list:
        assert result["stdout"]["golden_file"] != None
        if result["ok"] == False:
            error_result_count += 1
        written_or_not = print_golden_overwriting_result_to_stderr(
            result, timer_prog)
        if written_or_not == GOLDEN_NOT_WRITTEN_SAME_CONTENT:
            golden_same_content_count += 1
        elif written_or_not == GOLDEN_NOT_WRITTEN_WRONG_EXIT:
            golden_wrong_exit_count += 1
        elif not written_or_not:
            golden_written_count += 1
    sys.stderr.write("Golden file writing:\n")
    sys.stderr.write(
        "\t%d written, %d skipped (same content: %d, error: %d)\n" %
        (golden_written_count,
         golden_same_content_count + golden_wrong_exit_count,
         golden_same_content_count, golden_wrong_exit_count))
    return error_result_count, error_result_count


# Used by print_post_processing_summary(), returns error count and unique error count
def count_and_print_for_test_running(result_list: list,
                                     timer_prog: str) -> tuple:
    error_result_count, unique_error_tests = 0, set()
    for result in result_list:
        if result["ok"] == False and result["error_is_flaky"] == False:
            error_result_count += 1
            unique_error_tests.add(result["comb_id"])
        print_test_running_result_to_stderr(result, timer_prog)
    return error_result_count, len(unique_error_tests)


class global_lock:  # across child processes
    def __init__(self):
        pass

    def __enter__(self):
        g_lock.acquire()

    def __exit__(self, etype, value, traceback):
        g_lock.release()


# http://ascii-table.com/ansi-escape-sequences.php
# must be protected by a lock: make qsize() reliable
def add_rotating_log(q, s: str) -> None:
    try:
        temp_arr, original_qsize = [], q.qsize()
        if q.full():
            q.get()
        while q.qsize() > 0:  # empty() is unreliable: nasty Python
            e = q.get()
            temp_arr.append(e)
        sys.stderr.write(  # cursor moves up and clear entire line
            "\x1b[1A\x1b[2K" * original_qsize + "\x1b[?25l"  # hide cursor
            + ''.join(temp_arr + [s]) + "\x1b[?25h"  # show cursor
        )
        for e in temp_arr:
            q.put(e)
        q.put(s)
    # To prevent a broken pipe error. This error is raised when the queue
    # is garbage-collected by the process that created it, while the current
    # process still has a thread that wants to access it. We just use the
    # queue to print logs to console for prettiness, so it is fine to just
    # ignore the error without compromising the program's correctness.
    # https://stackoverflow.com/questions/36359528/broken-pipe-error-with-multiprocessing-queue
    # Python2 uses IOError, but Python3 uses BrokenPipeError which is a
    # subclass of OSError not IOError (in Python3 IOError is merged into
    # OSError), and BrokenPipeError does not exist in Python2. Nasty Python.
    except (IOError, OSError):
        pass


def clear_rotating_log(q):
    try:
        cur_size = q.qsize()
        for _ in range(cur_size):
            sys.stderr.write(
                "\x1b[1A\x1b[2K")  # cursor moves up and clears entire line
            q.get()
    except (IOError, OSError):  # see reason in add_rotating_log()
        pass


# Used by run_one()
def run_one_impl(timer: str, log_dirname: str, write_golden: bool,
                 env_values: dict, metadata: dict) -> dict:
    # The return code of the timer program is guaranteed to be 0
    # unless the timer itself has errors.
    try:
        start_abs_time = time.time()
        # NOTE We have to spawn timer and let timer spawn the program,
        # instead of directly spawning the program while using preexec_fn
        # to set the timeout, because (1) Python's signal.setitimer() and
        # resource.getrusage() do not measure time as accurate as the timer
        # written in C++ [1], (2) moreover, preexec_fn is not thread-safe:
        # https://docs.python.org/3/library/subprocess.html
        # [1] I wrote a Python program to verify this. I set the timeout
        #     to be 10 msec and give it a infinite-loop program, when it
        #     times out the reported time usage is 14 msec, way over 10.
        stdout = subprocess.check_output([timer, metadata["path"]] +
                                         metadata["args"],
                                         stderr=subprocess.DEVNULL,
                                         env=env_values)
        stdout = stdout.decode().rstrip()
        end_abs_time = time.time()
    except subprocess.CalledProcessError as e:
        # The code path signals an internal error of the timer (see '--docs').
        raise RuntimeError("Internal error (exit %d): %s" %
                           (e.returncode, e.cmd))
    inspectee_stdout_raw, ctimer_stdout = split_ctimer_out(stdout)
    inspectee_stdout = process_inspectee_stdout(inspectee_stdout_raw)
    run_one_single_result = did_run_one(  # return a dict
        log_dirname,
        write_golden,
        metadata,
        inspectee_stdout,
        ctimer_stdout,
        start_abs_time,
        end_abs_time,
        timer,
    )
    print_one_on_the_fly(metadata, run_one_single_result)
    return run_one_single_result


def run_one(input_args: list) -> dict:
    timer, log_dirname, write_golden, metadata = input_args
    env_values = {
        CTIMER_DELIMITER_ENVKEY: DELIMITER_STR,
        CTIMER_TIMEOUT_ENVKEY: score_utils.get_timeout(metadata["timeout_ms"])
    }
    if metadata["envs"] != None:
        env_values.update(metadata["envs"])
    return run_one_impl(timer, log_dirname, write_golden, env_values, metadata)


def run_all(args: Args, metadata_list: list, unique_count: int) -> int:
    remove_prev_log(args.log)
    num_tasks = len(metadata_list)  # >= unique_count, because of repeating
    num_workers = 1 if args.sequential else min(num_tasks, NUM_WORKERS_MAX)
    sys.stderr.write(
        info_s("task count: %d (unique: %d), worker count: %d" %
               (num_tasks, unique_count, num_workers)))
    run_tests_start_time = time.time()
    result_list = pool_map(num_workers, run_one,
                           [(args.timer, args.log, args.write_golden, metadata)
                            for metadata in metadata_list])
    create_dir_if_needed(args.log)
    master_log_filepath = os.path.join(args.log, LOG_FILE_BASE)
    with open(master_log_filepath, 'w') as f:
        json.dump(result_list, f, indent=2,
                  separators=(",", ": "))  # sorted already
    error_count, _ = print_post_processing_summary(
        args, num_tasks, result_list, master_log_filepath,
        time.time() - run_tests_start_time)
    return 0 if error_count == 0 else 1


NEEDED_METADATA_OBJECT_FIELD = [
    # sync with EXPLANATION_STRING's spec
    "desc",
    "path",
    "args",
    "golden",
    "timeout_ms",
    "envs",
    "exit"
]
NEEDED_EXIT_STATUS_OBJECT_FILED = [
    # sync with EXPLANATION_STRING's spec
    "type",
    "repr"
]
VALID_ARG_SPECIAL_CHARS = "._+-*/=^@#"  # sync with EXPLANATION_STRING's spec


def valid_arg(arg: str) -> bool:
    return all((c.isalnum() or c in VALID_ARG_SPECIAL_CHARS) for c in arg)


def check_metadata_list_format(
        metadata_list: list) -> list:  # not comprehensive
    if not isinstance(metadata_list, list):
        return ["matadata file does not store a JSON array "]
    errors = []
    for i, metadata in enumerate(metadata_list):
        if not isinstance(metadata, dict):
            errors.append("metadata #%-2d is not a JSON object" % (i + 1))
            continue
        for needed_metadata_field in NEEDED_METADATA_OBJECT_FIELD:
            if needed_metadata_field not in metadata:
                errors.append("metadata #%-2d does not contain field \"%s\"" %
                              (i + 1, needed_metadata_field))
        if "args" in metadata:
            args = metadata["args"]
            if not isinstance(args, list):
                errors.append("metadata #%-2d field \"args\" is not an array" %
                              (i + 1))
            elif next((e for e in args if not valid_arg(e)), None) != None:
                errors.append("metadata #%-2d field \"args\" contains "
                              "invalid character" % (i + 1))
        if "timeout_ms" in metadata:
            timeout_ms = metadata["timeout_ms"]
            if timeout_ms == None:
                pass
            else:
                if (not isinstance(timeout_ms, int)) or timeout_ms <= 0:
                    errors.append("metadata #%-2d field \"timeout_ms\" "
                                  "is not a positive number" % (i + 1))
        if "envs" in metadata:
            envs = metadata["envs"]
            if envs == None:
                pass
            else:
                if not isinstance(metadata["envs"], dict):
                    errors.append(
                        "metadata #%-2d field \"envs\" is not a dict" % (i + 1))
                else:
                    if any((not isinstance(k, str)) or ' ' in k
                           for k in envs.keys()):
                        errors.append("metadata #%-2d field \"envs\" requires "
                                      "keys to be strings without spaces" %
                                      (i + 1))
                    if any((not isinstance(v, str)) or ' ' in v
                           for v in envs.values()):
                        errors.append("metadata #%-2d field \"envs\" requires "
                                      "values to be strings without spaces" %
                                      (i + 1))
        if "exit" in metadata:
            for needed_exit_status_field in NEEDED_EXIT_STATUS_OBJECT_FILED:
                if needed_exit_status_field not in metadata["exit"]:
                    errors.append("metadata #%-2d's \"exit\" object "
                                  "does not contain field \"%s\"" %
                                  ((i + 1), needed_exit_status_field))
    return errors


EXPLANATION_STRING = """\x1b[33mSupplementary docs\x1b[0m

\x1b[33m'--timer':\x1b[0m
    It passes the path of a timer program that measures a program's processor
    time (not wall time) with timeout. The program's interface satisfies:
    [example] https://github.com/Leedehai/ctimer (mine)
    inputs:
        commandline arguments:
            the invocation of the inspected program
        environment variable CTIMER_TIMEOUT:
            timeout value (ms); 0 means effectively infinite time
        environment variable CTIMER_STATS:
            file path to write stats report; if not given, print to stdout
        environment variable CTIMER_DELIMITER:
            delimiter string at the beginning and end of the stats report
            string (see below); if not given, use empty string
        * the script will set the environment variables as needed locally
          when invoking the timer program
    outputs: the inspected program's outputs (stdout, stderr), with stats
        report in stdout if CTIMER_STATS is unspecified; if CTIMER_STATS
        is specified, the stats report will be written to that file
    stats report: a JSON string, representing an object:
        "exit"     : exit status object (see below), inspectee's exit status
        "times_ms" : object:
            "proc"      : floating point, inspectee's time on processor
            "abs_start" : floating point, absolute start time since Epoch
            "abs_end"   : floating point, absolute end time since Epoch
    others:
        * the timer should always exit with 0 regardless of the inspected
          program's exit status; non-0 exit is reserved for internal error.
        * the timer should pass whatever environment variables it has to
          the inspected program.

\x1b[33m'--meta':\x1b[0m
    This option passes the path of a file containing the metadata of tests.
    The metadata file could be either hand-written or script-generated; it
    stores in JSON format an array of metadata objects. Each has keys:
        "desc"    : string
            description of the test
        \x1b[33m=== parameters contolling command invocation ===\x1b[0m
        "path"    : string
            path to the test executable binary
        "args"    : array of strings
            the commandline arguments, all characters are alphanumeric or
            one of "._+-*/=^@#"
        "envs"  : dict or null
            environment variables provided when running the test executable
            * each entry's key and value are strings without spaces
        \x1b[33m=== parameters controlling test checking ===\x1b[0m
        "golden"  : string or null
            path to the golden file; null: not needed
            * if the golden file path is given, the inspectee's stdout
              will be compared with the golden file content
            * if '--write-golden' is given, inspectee's stdout is written
              to this file
            * different tests should have different golden files, even if
              their contents are the same, to avoid possible data racing
              when writing the files for '--write-golden'
        "timeout_ms" : integer or null
            the max processor time (ms) allowed; null: effectively infinite
        "exit"    : exit status object (see below), storing the expected exit
    * all paths are relative to the current working directory
    * mutually exclusive: --meta, --paths

\x1b[33m'--paths':\x1b[0m
    In cases where only the paths of the test executables matter, prefer this
    option over '--meta', as it can be invoked with a list of space-separated
    test executable paths in commandline. Other fields required by a metadata
    object (see above) of each test will automatically get these values:
        desc = "", path = (the path provided with this option),
        args = [], envs = null, golden = null, timeout_ms = null,
        exit = { "type": "return", "repr": 0 } (exit status, see below)
    * mutually exclusive: --meta, --paths

\x1b[33m'--flakiness':\x1b[0m
    Not unusually, some tests are flaky (e.g. due to CPU scheduling or a bug
    in language runtime). Use this option to specify a directory that stores
    all declaration files. Under this directory, all files whose names match
    the glob pattern "*.flaky" will be loaded.
    In a declaration file, characters following '#' in a line are treated as
    comments. Each non-comment line is a flakiness declaration entry with
    space-separated string fields in order:
        1. test executable path (last two path components joined with '/')
        2. case id hash string (computed from commandline arguments and
           alphabetically-sorted environment variables) as appeared on the
           corresponding result object.
        3. type of expected error: one or more (joined by '|': non-exclusive
           'or') of WrongExitCode, Timeout, Signal, StdoutDiff, Others
        * you should ensure the field 1 of each entry is unique across all
          flakiness declaration files
        * joining the fields 1 and 2 with '-' produces the 'comb_id' (the ID
          for each unique path + args combination) in each result object in
          the master log
        * e.g.: a line could be "foo/bar-test 00000000 Timeout|StdoutDiff",
          and its 'comb_id' in the master log is "foo/bar-test-00000000"

\x1b[33m'--write-golden':\x1b[0m
    Use this option to create or overwrite golden files of tests. Tests with
    golden file unspecified (i.e. metadata's "golden" field is null) won't
    be executed.
    A golden file will be written only if the exit status of that test is as
    expected, and if the file exists, the content will be different.
    You have to manually check the tests are correct before writing.

\x1b[33mExit status object:\x1b[0m
    A JSON object with keys:
    "type"  : string - "return", "timeout", "signal", "quit", "unknown"
    "repr"  : integer, indicating the exit code for "return" exit, timeout
              limit (millisec, processor time) for "timeout" exit, signal
              value for "signal" exit, and null for others (timer errors)

\x1b[33mMaster log and result object:\x1b[0m
    The master log is a JSON file containing an array of result objects. To
    see the specification of the result object, please refer to the in-line
    comments in function `generate_result_dict()`.
    The master log is human-readable, but is more suited to be loaded and
    rendered by a script.

\x1b[33mMore on concepts:\x1b[0m
    metadata        description of a test: program path, arguments, ...
    golden file     the file storing the expected stdout output, nullable
    master log      a JSON file log.json under the log directory
    log directory   specified by '--log', which stores the master log
                    and tests' stdout and diff, if any, among others

\x1b[33mMore on options:\x1b[0m
    Complete list of options: "--help".
    Concurrency is enabled, unless '--sequential' is given.
    Unless '--help' or '--docs' is given:
        * '--timer' is needed, and
        * exactly one of '--paths' and '--meta' is needed."""


def main():
    parser = argparse.ArgumentParser(
        description="Test runner: with timer, logging, diff in HTML",
        epilog="Unless '--docs' is given, exactly one of '--paths' "
        "and '--meta' is needed.\n"
        "Program exit code is 0 on success, 1 otherwise.")
    parser.add_argument("--timer",
                        metavar="TIMER",
                        type=str,
                        default=None,
                        help="path to the timer program")
    parser.add_argument("--meta",
                        metavar="PATH",
                        default=None,
                        help="JSON file of tests' metadata")
    parser.add_argument("--paths",
                        metavar="T",
                        nargs='+',
                        default=[],
                        help="paths to test executables")
    parser.add_argument("-g",
                        "--log",
                        metavar="DIR",
                        type=str,
                        default="./logs",
                        help="directory to write logs, default: ./logs")
    parser.add_argument("-n",
                        "--repeat",
                        metavar="N",
                        type=int,
                        default=1,
                        help="run each test N times, default: 1")
    parser.add_argument("-1",
                        "--sequential",
                        action="store_true",
                        help="run sequentially instead concurrently")
    parser.add_argument("-s",
                        "--seed",
                        metavar="S",
                        type=int,
                        default=None,
                        help="set the seed for the random number generator")
    parser.add_argument(
        "--flakiness",
        metavar="DIR",
        type=str,
        default=None,
        help="load flakiness declaration files *.flaky under DIR")
    parser.add_argument("-w",
                        "--write-golden",
                        action="store_true",
                        help="write stdout to golden files instead of checking")
    parser.add_argument("--docs",
                        action="store_true",
                        help="self-documentation in more details")
    args = parser.parse_args()

    if args.docs:
        print(EXPLANATION_STRING)
        return 0

    if args.timer == None:
        sys.exit(error_s("'--timer' is not given; use '-h' for help"))
    elif not os.path.isfile(args.timer):
        sys.exit(error_s("timer program not found: %s" % args.timer))
    args.timer = os.path.relpath(args.timer)

    if ((len(args.paths) == 0 and args.meta == None)
            or (len(args.paths) > 0 and args.meta != None)):
        sys.exit(
            error_s("exactly one of '--paths' and '--meta' should be given."))
    if args.seed != None and args.write_golden:
        sys.exit(
            error_s("'--seed' and '--write-golden' cannot be used together."))
    if args.repeat != 1 and args.write_golden:
        sys.exit(
            error_s("'--repeat' and '--write-golden' cannot be used together."))
    if args.flakiness and not os.path.isdir(args.flakiness):
        sys.exit(error_s("directory not found: %s" % args.flakiness))

    metadata_list = None
    if len(args.paths) > 0:
        missing_executables = [e for e in args.paths if not os.path.isfile(e)]
        if len(missing_executables) > 0:
            sys.exit(
                error_s("the following executable(s) "
                        "are not found: %s" % str(missing_executables)))
        metadata_list = [get_metadata_from_path(path) for path in args.paths]
    elif args.meta != None:
        if not os.path.isfile(args.meta):
            sys.exit(error_s("'--meta' file not found: %s" % args.meta))
        with open(args.meta, 'r') as f:
            try:
                metadata_list = json.load(f)
            except ValueError:
                sys.exit(error_s("not a valid JSON file: %s" % args.meta))
            errors = check_metadata_list_format(metadata_list)  # sanity check
            if errors and len(errors) > 0:
                sys.exit(
                    error_s("metadata is bad, checkout '--docs' "
                            "for requirements:\n\t" + "\n\t".join(errors)))
    else:  # Should not reach here; already checked by option filtering above
        raise RuntimeError("Should not reach here")

    if len(metadata_list) == 0:
        sys.exit(error_s("no test found."))

    # If args.write_golden == True, ignore tests that do not have a golden file;
    # this step produces metadata_list_2
    ignore_metadata_indexes = []
    if args.write_golden:
        prompt = (
            "About to overwrite golden files of tests with their stdout.\n"
            "Are you sure? [y/N] >> ")
        consent = input(prompt)
        if not IS_ATTY:
            print("%s" % consent)
        if consent.lower() != "y":
            sys.exit("Aborted.")
        ignore_metadata_indexes = [
            i for (i, m) in enumerate(metadata_list) if m["golden"] == None
        ]
        if len(ignore_metadata_indexes) > 0:
            print(
                info_s("%d tests are ignored because they specified "
                       "no golden file to write" %
                       len(ignore_metadata_indexes)))

    # Process the raw matadata list:
    # 1. take care of args.repeat; 2. take care of args.flakiness
    metadata_list_processed = []
    flakiness_dict = parse_flakiness_decls(args.flakiness)
    unique_count = len(metadata_list)
    for i, metadata in enumerate(metadata_list):
        if i in ignore_metadata_indexes:
            continue
        # case id is unique for every (path, args) combination
        comb_id = compute_comb_id(
            prog=metadata["path"],
            args=metadata["args"],
            envs=metadata["envs"] if metadata["envs"] != None else {})  # str
        metadata["comb_id"] = comb_id  # str
        metadata["flaky_errors"] = flakiness_dict.get(comb_id, [])
        for repeat_cnt in range(args.repeat):
            metadata_copy = copy.deepcopy(metadata)
            metadata_copy["repeat"] = {
                "count": repeat_cnt + 1,
                "all": args.repeat,
            }
            metadata_list_processed.append(metadata_copy)

    # Shuffle the tests randomly.
    if not args.write_golden:
        # if args.seed == None, use a system-provided randomness source
        random.seed(args.seed)
        random.shuffle(metadata_list_processed)

    return run_all(args, metadata_list_processed, unique_count)


if __name__ == "__main__":
    sys.exit(main())
