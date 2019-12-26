#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: runtest.py
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

import os, sys
py = sys.version_info
if py.major == 2 or (py.major == 3 and py.minor < 5):
   sys.exit("[Error] mininum Python version is 3.5")
import argparse
import collections
import copy
import hashlib
import json
import multiprocessing
import platform
import random
import re
import shutil
import signal
import subprocess
import time

# custom modules
from diff_html_str import get_diff_html_str
from flakiness import parse_flakiness_decls

# avoid *.pyc of imported modules
sys.dont_write_bytecode = True

LOG_FILE_BASE = "run_log.json"
CTIMER_DELIMITER_ENVKEY = "CTIMER_DELIMITER"
CTIMER_TIMEOUT_ENVKEY = "CTIMER_TIMEOUT"
DELIMITER_STR = "#####"
INFINITE_TIME = 0 # it means effectively infinite time required by timer

IS_ATTY = sys.stdin.isatty() and sys.stdout.isatty() # testing might not be in a terminal
TERMINAL_COLS = int(os.popen('stty size', 'r').read().split()[1]) if IS_ATTY else 70
if (TERMINAL_COLS <= 25):
    sys.exit("[Error] terminal width (%d) is rediculously small" % TERMINAL_COLS)

# function named differently: nasty python
irange = range if sys.version_info.major >= 3 else xrange

# used by did_run_one()
def generate_result_dict(
    metadata: dict, ctimer_reports: dict, match_exit: bool, write_golden: bool,
    start_abs_time: float, end_abs_time: float,
    stdout_filename: str, diff_filename: str,
    exceptions: list) -> collections.OrderedDict:
    all_ok = match_exit and diff_filename == None
    golden_filename = os.path.abspath(metadata["golden"]) if metadata["golden"] else None
    error_is_flaky = None
    if not all_ok:
        error_is_flaky = check_if_error_is_flaky(
            metadata["flaky_errors"],
            ctimer_reports["exit"]["type"],
            diff_filename != None
        )
    return collections.OrderedDict([
        # success
        ("ok", all_ok), # boolean
        ("error_is_flaky", error_is_flaky), # boolean, or None for all_ok == True
        # metadata
        ("desc", metadata["desc"]), # str
        ("path", metadata["path"]), # str
        ("args", metadata["args"]), # list
        ("comb_id", metadata["comb_id"]), # unique for every (path, args) combination
        ("flaky_errors", metadata["flaky_errors"]), # list of str, the expected errors
        ("repeat", metadata["repeat"]), # dict { "count": int, "all": int }
        # time measurements
        ("timeout_ms", metadata["timeout_ms"] if metadata["timeout_ms"] != None else INFINITE_TIME), # int
        ("times_ms", collections.OrderedDict([
            ("proc", ctimer_reports["times_ms"]["total"]),
            ("abs_start", start_abs_time * 1000.0),
            ("abs_end", end_abs_time * 1000.0),
        ])),
        # details:
        ("exit", collections.OrderedDict([
            ("ok", match_exit), # boolean: exit type and repr both match with expected
            # "type"  : string - "return", "timeout", "signal", "quit", "unknown"
            # "repr"  : integer, indicating the exit code for "return" exit, timeout
            #     value (millisec, processor time) for "timeout" exit, signal
            #     value "signal" exit, and null for others (timer errors)
            ("expected", collections.OrderedDict([
                ("type", metadata["exit"]["type"]), # str
                ("repr", metadata["exit"]["repr"])  # int
            ])),
            ("real", collections.OrderedDict([
                ("type", ctimer_reports["exit"]["type"]), # str
                ("repr", ctimer_reports["exit"]["repr"])  # int
            ])),
        ])),
        ("stdout", collections.OrderedDict([
            # boolean, or None for '--write-golden' NOTE it is True if there's no need to compare
            ("ok", None if write_golden else (diff_filename == None)),
            # abs path (str), or None meaning no need to compare
            ("golden_file", golden_filename),
            # abs path (str), or None meaning no stdout or written to golden file
            ("actual_file", stdout_filename),
            # abs path (str), or None meaning 1) if "golden_file" == None: no need to compare
            #                              or 2) if "golden_file" != None: no diff found
            ("diff_file",   diff_filename) # str, or None if there's no need to compare or no diff found
        ])),
        ("exceptions", exceptions) # list of str, describe errors encountered in run_one() (not in test)
    ]) # NOTE any changes (key, value, meaning) made in this data structure must be honored in view.py

# handle nasty Python's str v.s. bytes v.s. unicode mess
def ensure_str(s) -> str:
    if type(s) == bytes:
        return s.decode()
    elif type(s) == str:
        return s
    raise TypeError("param 's' is not bytes or str")

def guess_emulator_supports_hyperlink() -> bool:
    if (("SSH_CLIENT" in os.environ)
        or ("SSH_CONNECTION" in os.environ)
        or ("SSH_TTY" in os.environ)):
        return False
    if platform.system().lower() == "linux":
        return True # VTE terminals (GNOME, Guake, Tilix, ...) are fine
    elif platform.system().lower() == "darwin": # macOS
        if os.environ.get("TERM_PROGRAM", "").lower().startswith("apple"):
            return False # Apple's default Terminal.app is lame, recommend iTerm2.app
        return True
    return False

# Make a hyperlink in terminal without displaying the lengthy URL
# https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda
# Compatible with GNOME, iTerm2, Guake, hTerm, etc.
# NOTE the URL should not contain ';' or ':' or ASCII code outside 32-126.
def hyperlink_str(url: str, description : str = "link") -> str:
    if "://" not in url:
        url = "file://" + os.path.abspath(url)
    if (not IS_ATTY) or (not guess_emulator_supports_hyperlink()):
        return url
    return "\x1b]8;;%s\x1b\\%s\x1b]8;;\x1b\\" % (url, description)

def get_num_workers(env_var: str) -> int:
    env_num_workers = os.environ.get(env_var, "")
    if len(env_num_workers):
        try:
            env_num_workers_number = int(env_num_workers)
        except ValueError:
            sys.exit("[Error] env vairable '%s' is not an integer" % env_var)
        if env_num_workers_number <= 0:
            sys.exit("[Error] env variable '%s' is not positive" % env_var)
        return env_num_workers_number
    else:
        return multiprocessing.cpu_count() + 2
NUM_WORKERS_MAX = get_num_workers(env_var="NUM_WORKERS") # not "NUM_WORKERS_MAX", to be consistent

# possible exceptions (not Python's Exceptions) for user inputs
GOLDEN_NOT_WRITTEN_PREFIX = "golden file not written"
GOLDEN_NOT_WRITTEN_SAME_CONTENT  = "%s: content is the same" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_NOT_WRITTEN_WRONG_EXIT = "%s: the test's exit is not as expected" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_FILE_MISSING = "golden file missing"

# Set signal handlers
def sighandler(sig: int, frame):
    # do not print: it's ugly for all workers to print together
    sys.exit(1)
signal.signal(signal.SIGINT, sighandler)
signal.signal(signal.SIGTERM, sighandler)
signal.signal(signal.SIGABRT, sighandler)
signal.signal(signal.SIGSEGV, sighandler)

def cap_width(s: str, width: int = TERMINAL_COLS) -> str:
    extra_space = width - len(s)
    return s if extra_space >= 0 else (s[:12] + "..." + s[len(s) - width - 15:])

# NOTE not a class, due to a flaw in multiprocessing.Pool.map() in Python2
def get_metadata_from_path(path: str) -> dict:
    # docs: see EXPLANATION_STRING below
    return {
        "desc": "",
        "path": path,
        "args": [],
        "golden": None,
        "timeout_ms": None,
        "setenv": {},
        "exit": { "type": "return", "repr": 0 }
    }

# run multiprocessing.Pool.map()
# NOTE the try-except block is to handle KeyboardInterrupt cleanly to fix a flaw in Python:
# KeyboardInterrupt cannot cleanly kill a multiprocessing.Pool()'s child processes, printing verbosely
# https://stackoverflow.com/a/6191991/8385554
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
    l = multiprocessing.Lock()
    # On macOS, a multiprocessing queue must be instantiated from
    # multiprocessing.Manager().Queue() instead of directory from
    # multiprocessing.Queue(). Otherwise, its qsize() method will
    # raise a NotImplementedError.. nasty Python. This is a known
    # bug: https://github.com/vterron/lemon/issues/11
    # Another solution: https://github.com/keras-team/autokeras/issues/368#issuecomment-461625748
    mgr = multiprocessing.Manager() # creates a server process
    q, c = mgr.Queue(5), mgr.Value('i', 0)
    pool = multiprocessing.Pool(
        num_workers, initializer=init_shared_mem, initargs=(l, q, c))
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
    ctimer_stdout = s[ctimer_begin_index + len(DELIMITER_STR) : report_end_index]
    return inspectee_stdout.rstrip(), ctimer_stdout.rstrip()

def get_timeout(timeout: int) -> str:
    return str(timeout if timeout != None else INFINITE_TIME)

# Pick a hash length
# N = 16^8 = 2^32 => ~N^(1/2) = ~2^16 values produces a collision with P=50%
ARGS_HASH_LEN = 8 # NOTE value should sync with EXPLANATION_STRING below
# This "ID" is made of the last two path components and the hashcode of args, e.g.
# prog = "foo", args = []              => return: "foo-00000000"
# prog = "baz/bar/foo", args = []      => return: "bar/foo-00000000"
# prog = "baz/bar/foo", args = [ '9' ] => return: "bar/foo-0ade7c2c"
def compute_comb_id(prog: str, args: list) -> str:
    assert(type(args) == list)
    prog_basename = os.path.basename(prog)
    prog_dir_basename = os.path.basename(os.path.dirname(prog)) # "" if prog doesn't contain '/'
    path_repr = os.path.join(prog_dir_basename, prog_basename)
    args_hash = '0' * ARGS_HASH_LEN
    if len(args):
        args_hash = hashlib.sha1(' '.join(args).encode()).hexdigest()[:ARGS_HASH_LEN]
    return "%s-%s" % (path_repr, args_hash.lower())

# This path stem (meaning there is no extension such as ".diff") is made of the
# comb_id, repeat count, log_dirname. E.g.
# comb_id = "bar/foo-0ade7c2c", repeat 3 out of 1~10, log_dirname = "./out/foo/logs"
#   => return: "./out/foo/logs/bar/foo-0ade7c2c-3"
def get_logfile_path_stem(
    comb_id: str, repeat_count: int,
    log_dirname: str) -> str: # "stem" means no extension name such as ".diff"
    return "%s-%s" % (os.path.join(log_dirname, comb_id), repeat_count)

UNEXPECTED_ERROR_FORMAT = """\x1b[33m[unexpected error] {desc}\x1b[0m{repeat}
{error_summary}
  \x1b[2m{rerun_command}\x1b[0m
"""
# when not using '--write-golden'
def print_test_running_result_to_stderr(result: dict, timer: str) -> None:
    timeout_env = "%s=%s" % (
        CTIMER_TIMEOUT_ENVKEY, get_timeout(result["timeout_ms"]))
    rerun_command = "{timeout_env} {timer} \\\n    {path} {args}".format(
        timeout_env = timeout_env, timer = timer, path = result["path"],
        args = ' '.join(result["args"])
    )
    if result["ok"] == True or result["error_is_flaky"] == True:
        pass
    else:
        assert(result["ok"] == False)
        result_exceptions = result["exceptions"]
        if len(result_exceptions):
            assert(len(result_exceptions) == 1
                and result_exceptions[0] == GOLDEN_FILE_MISSING)
            error_summary = "%s: %s" % (
                GOLDEN_FILE_MISSING, result["stdout"]["golden_file"])
        else:
            error_summary = get_error_summary(result)
            error_summary = '\n'.join([
                "  %s: %s" % (k, error_summary[k])
                for k in error_summary["error_keys"]
            ])
        if result["repeat"]["all"] > 1:
            repeat_report = " (repeat %d/%d)" % (
                result["repeat"]["count"], result["repeat"]["all"])
        else:
            repeat_report = ""
        sys.stderr.write(UNEXPECTED_ERROR_FORMAT.format(
            desc = result["desc"],
            repeat = repeat_report,
            error_summary = error_summary,
            rerun_command = rerun_command
        ))

# when using '--write-golden'
def print_golden_overwriting_result_to_stderr(result: dict, timer: str):
    attempted_golden_file = result["stdout"]["golden_file"]
    not_written_exceptions = [
        e for e in result["exceptions"]
        if e.startswith(GOLDEN_NOT_WRITTEN_PREFIX)
    ]
    timeout_env = "%s=%s" % (
        CTIMER_TIMEOUT_ENVKEY, get_timeout(result["timeout_ms"]))
    rerun_command = "{timeout_env} {timer} \\\n    {path} {args}".format(
        timeout_env = timeout_env, timer = timer, path = result["path"],
        args = ' '.join(result["args"])
    )
    assert(len(not_written_exceptions) <= 1)
    if len(not_written_exceptions) == 0:
        sys.stderr.write(
            "\x1b[36m[ok: content changed] %s\x1b[0m\n"
            "  written: %s (%d B)\n  \x1b[2m%s\x1b[0m\n" % (
                result["desc"], attempted_golden_file,
                os.path.getsize(attempted_golden_file), rerun_command
        ))
        return None
    assert(len(not_written_exceptions) == 1)
    if GOLDEN_NOT_WRITTEN_SAME_CONTENT in not_written_exceptions:
        sys.stderr.write(
            "\x1b[36m[ok: same content] %s\x1b[0m\n"
            "  skipped: %s\n  \x1b[2m%s\x1b[0m\n" % (
            result["desc"], attempted_golden_file, rerun_command))
        return GOLDEN_NOT_WRITTEN_SAME_CONTENT
    elif GOLDEN_NOT_WRITTEN_WRONG_EXIT in not_written_exceptions:
        sys.stderr.write(
            "\x1b[33m[error: unexpected exit status] %s\x1b[0m\n"
            "  skipped: %s\n  \x1b[2m%s\x1b[0m\n" % (
            result["desc"], attempted_golden_file, rerun_command))
        return GOLDEN_NOT_WRITTEN_WRONG_EXIT # the only one item
    else:
        assert(False)

def create_dir_if_needed(dirname: str) -> None:
    # NOTE use EAFP (Easier to Ask for Forgiveness than Permission) principle here, i.e.
    # use try-catch to handle the situation where the directory was already created by
    # another process.
    # EAFP can avoid the race condition caused by LBYL (Look Before You Leap): use a
    # if-statement to check the absence of the target directory before creating it.
    # Using lock can also avoid the race condition, but it is cumbersome in Python.
    # Unlike other languages, try-catch doesn't add a noticeable overhead in Python.
    try:
        os.makedirs(dirname) # create intermediate dirs if necessary
    except OSError: # Python2 throws OSError, Python3 throws its subclass FileExistsError
        pass        # dir already exists (due to multiprocessing)

# can be used concurrently
def write_file(
    filename: str, s: str, assert_str_non_empty: bool = False) -> None:
    assert(s != None)
    if assert_str_non_empty:
        assert(s != "")
    create_dir_if_needed(os.path.dirname(filename))
    with open(filename, 'w') as f:
        f.write(s)

def process_inspectee_stdout(s: str) -> str:
    # remove color sequences
    s = re.sub(r"\x1b\[.*?m", "", s)
    # do not use textwrap: unstable
    new_lines, cur_line, cnt = [], "", 0
    for c in s: # for each character
        cur_line += c
        cnt += 1
        if c == '\n':
            new_lines.append(cur_line) # ends with '\n'
            cur_line, cnt = "", 0
        elif cnt == 90: # this limit is used by diff.html and diff_html_str.py
            new_lines.append(cur_line + '\n') # force linebreak
            cur_line, cnt = "", 0
    return ''.join(new_lines)

# exit type: Sync with EXPLANATION_STRING
EXIT_TYPE_TO_FLAKINESS_ERR = {
    # key: exit type in timer report
    # val: possible flakiness error type in flakiness declaration file
    "return":  "WrongExitCode",
    "timeout": "Timeout",
    "signal":  "Signal",
    "quit":    "Others",
    "unknown": "Others"
}
# used by generate_result_dict()
# NOTE this function is called ONLY IF there is an error
def check_if_error_is_flaky(
    expected_errs: list, actual_exit_type: str, has_stdout_diff: bool) -> bool:
    if len(expected_errs) == 0:
        return False
    # NOTE expected_errs might only cover one of the errors
    if has_stdout_diff == True and ("StdoutDiff" not in expected_errs):
        return False
    return EXIT_TYPE_TO_FLAKINESS_ERR[actual_exit_type] in expected_errs

def get_error_summary(result_obj: dict) -> dict:
    error_keys = []
    exit_error = None
    if result_obj["exit"]["ok"] == False:
        error_keys.append("exit")
        # do not use str(dir(..)): have ugly 'u' prefixes for unicode strings
        real_exit = result_obj["exit"]["real"]
        exit_error = "{ type: %s, repr: %s }" % (real_exit["type"], real_exit["repr"])
    diff_file = result_obj["stdout"]["diff_file"]
    if diff_file != None:
        error_keys.append("diff")
    return {
        "error_keys": error_keys,
        "exit": exit_error, # str, or None if exit is ok
        "diff": diff_file   # str, or None if no need to compare or no diff found
    }

# used by run_one_impl()
def did_run_one(log_dirname: str, write_golden: bool, metadata: dict,
                inspectee_stdout: str, ctimer_stdout: str,
                start_abs_time: float, end_abs_time: float) -> collections.OrderedDict:
    assert(len(ctimer_stdout))
    ctimer_dict = json.loads(ctimer_stdout)
    match_exit = (metadata["exit"]["type"] == ctimer_dict["exit"]["type"]
                  and metadata["exit"]["repr"] == ctimer_dict["exit"]["repr"])
    exceptions = [] # list of str, describe misc errors in run_one() itself (not in test)
    filepath_stem = get_logfile_path_stem( # "stem" means no extension name
        metadata["comb_id"], metadata["repeat"]["count"], log_dirname)
    stdout_filename = None if write_golden else os.path.abspath(filepath_stem + ".stdout")
    diff_filename = None # will be given a str if there is need to compare and diff is found
    if not write_golden:
        write_file(stdout_filename, inspectee_stdout) # stdout could be ""
    if metadata["golden"] != None: # write or compare only if "golden" is not None
        golden_filename = metadata["golden"]
        if write_golden: # write stdout to golden
            if match_exit:
                golden_exists_and_same = False
                if os.path.isfile(golden_filename):
                    with open(golden_filename, 'r') as f:
                        if f.read() == inspectee_stdout:
                            golden_exists_and_same = True
                            exceptions.append(GOLDEN_NOT_WRITTEN_SAME_CONTENT)
                if not golden_exists_and_same:
                    write_file(golden_filename, inspectee_stdout) # stdout could be ""
            else:
                exceptions.append(GOLDEN_NOT_WRITTEN_WRONG_EXIT)
        else: # compare stdout with golden
            found_golden, stdout_comparison_diff = get_diff_html_str(
                filepath_stem.split(os.sep)[-1], # title of HTML
                metadata["desc"], metadata["setenv"],
                ' '.join([ metadata["path"] ] + metadata["args"]),
                golden_filename, stdout_filename
            )
            if not found_golden:
                exceptions.append(GOLDEN_FILE_MISSING)
            if stdout_comparison_diff != None: # write only if diff is not empty
                diff_filename = os.path.abspath(filepath_stem + ".diff.html")
                write_file(diff_filename, stdout_comparison_diff, assert_str_non_empty=True)
    return generate_result_dict(
        metadata, ctimer_dict, match_exit, write_golden,
        start_abs_time, end_abs_time,
        stdout_filename, diff_filename, exceptions
    )

# used by run_one_impl()
def print_one_on_the_fly(metadata: dict, run_one_single_result: dict) -> None:
    # below is printing on the fly
    if metadata["repeat"]["all"] > 1:
        metadata_desc = "%d/%d %s" % (
            metadata["repeat"]["count"], metadata["repeat"]["all"], metadata["desc"])
    else:
        metadata_desc = metadata["desc"]
    is_ok = run_one_single_result["ok"] # successful run
    should_stay_on_console = False
    if is_ok:
        if len(run_one_single_result["flaky_errors"]):
            status_head = "\x1b[36mflaky success\x1b[0m"
        else: # definite success
            status_head = "\x1b[36msuccess\x1b[0m"
    else: # test error
        if run_one_single_result["error_is_flaky"]:
            status_head = "\x1b[36mflaky error\x1b[0m"
        else: # definite error
            should_stay_on_console = True
            status_head = "\x1b[33;1merror\x1b[0m"
    with global_lock():
        # keep runtime overhead here as simple as possible
        g_count.value += 1
        error_summary = get_error_summary(run_one_single_result)
        if should_stay_on_console: # definite error, details will be printed after all execution
            logline = "%s %3s %s\n\x1b[2m%s\x1b[0m\n" % (
                status_head, g_count.value, metadata_desc,
                '\n'.join([
                    "  %s: %s" % (k, error_summary[k])
                    for k in error_summary["error_keys"]
                ])
            )
            clear_rotating_log(g_queue)
            sys.stderr.write(logline)
        else: # definite success, flaky success, flaky error
            logline = cap_width("%s %3s %s" % (
                status_head, g_count.value, metadata_desc)) + '\n'
            add_rotating_log(g_queue, logline)
            time.sleep(0.05) # let the line stay for a while: prettier, though adding overhead
        sys.stderr.flush()

# used by run_all()
def remove_prev_log(log_dir: str) -> None:
    if os.path.isdir(log_dir):
        # to prevent perplexing cases e.g. master log says all is good, but *.diff files
        # from a previous run exist
        shutil.rmtree(log_dir)
    elif os.path.exists(log_dir):
        sys.exit("[Error] path exists as a non-directory: %s" % log_dir)

# used by run_all()
def print_summar_and_write_master_log(
    args: list, num_tasks: int,
    run_tests_start_time: float, result_list: list) -> tuple:
    assert(len(result_list) == num_tasks)
    log_filename = os.path.join(args.log, LOG_FILE_BASE)
    if args.write_golden:
        error_count, unique_error_count = count_and_print_for_golden_writing(
            log_filename, result_list, args.timer)
    else:
        error_count, unique_error_count = count_and_print_for_test_running(
            log_filename, result_list, args.timer)
    assert(unique_error_count <= error_count)
    create_dir_if_needed(args.log)
    with open(log_filename, 'w') as f:
        json.dump(result_list, f, indent=2) # no "sort_keys=True", due to OrderedDict
    color = "\x1b[38;5;155m" if error_count == 0 else "\x1b[38;5;203m"
    sys.stderr.write("%sDone: %s tasks, definite error %d%s, %.2f sec, log: %s\x1b[0m\n" % (
        color, num_tasks,
        error_count,
        "" if error_count == 0 else (" (unique: %d)" % unique_error_count),
        time.time() - run_tests_start_time,
        hyperlink_str(log_filename)
    ))
    return error_count, unique_error_count

# used by print_summar_and_write_master_log(), returns error count and unique
# error count (unique error count <= error count, because of args.repeat)
def count_and_print_for_golden_writing(
    log_filename: str, result_list: list, timer_prog: str) -> tuple:
    error_result_count = 0
    golden_written_count = 0
    golden_same_content_count, golden_wrong_exit_count = 0, 0
    for result in result_list:
        assert(result["stdout"]["golden_file"] != None)
        if result["ok"] == False:
            error_result_count += 1
        written_or_not = print_golden_overwriting_result_to_stderr(result, timer_prog)
        if written_or_not == GOLDEN_NOT_WRITTEN_SAME_CONTENT:
            golden_same_content_count += 1
        elif written_or_not == GOLDEN_NOT_WRITTEN_WRONG_EXIT:
            golden_wrong_exit_count += 1
        elif not written_or_not:
            golden_written_count += 1
    sys.stderr.write("Golden file writing:\n")
    sys.stderr.write("\t%d written, %d skipped (same content: %d, error: %d)\n" % (
        golden_written_count,
        golden_same_content_count + golden_wrong_exit_count,
        golden_same_content_count, golden_wrong_exit_count))
    return error_result_count, error_result_count

# used by print_summar_and_write_master_log(), returns error count and unique error count
def count_and_print_for_test_running(
    log_filename: str, result_list: list, timer_prog: str) -> tuple:
    error_result_count, unique_error_tests = 0, set()
    for result in result_list:
        if result["ok"] == False and result["error_is_flaky"] == False:
            error_result_count += 1
            unique_error_tests.add(result["comb_id"])
        print_test_running_result_to_stderr(result, timer_prog)
    return error_result_count, len(unique_error_tests)

class global_lock: # across child processes
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
        while q.qsize() > 0: # empty() is unreliable: nasty Python
            e = q.get()
            temp_arr.append(e)
        sys.stderr.write( # cursor moves up and clear entire line
            "\x1b[1A\x1b[2K" * original_qsize + "\x1b[?25l" # hide cursor
            + ''.join(temp_arr + [ s ]) + "\x1b[?25h" # show cursor
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
        for _ in irange(cur_size):
            sys.stderr.write("\x1b[1A\x1b[2K") # cursor moves up and clears entire line
            q.get()
    except (IOError, OSError): # see reason in add_rotating_log()
        pass

# used by run_one()
def run_one_impl(
    timer: str, log_dirname: str, write_golden: bool,
    env_values: dict, metadata: dict) -> dict:
    with open(os.devnull, 'w') as devnull:
        # the return code of the timer program is guaranteed to be 0
        # unless the timer itself has errors
        try:
            start_abs_time = time.time()
            stdout = ensure_str(subprocess.check_output(
                [ timer, metadata["path"] ] + metadata["args"],
                stderr=devnull, env=env_values)).rstrip()
            end_abs_time = time.time()
        except subprocess.CalledProcessError as e:
            # the code path signals an internal error of the timer program (see '--docs')
            raise RuntimeError(
                "Internal error (exit %d): %s" % (e.returncode, e.cmd))
    inspectee_stdout_raw, ctimer_stdout = split_ctimer_out(stdout)
    inspectee_stdout = process_inspectee_stdout(inspectee_stdout_raw)
    run_one_single_result = did_run_one( # return a dict
        log_dirname, write_golden, metadata,
        inspectee_stdout, ctimer_stdout,
        start_abs_time, end_abs_time
    )
    print_one_on_the_fly(metadata, run_one_single_result)
    return run_one_single_result

def run_one(input_args: list) -> dict:
    timer, log_dirname, write_golden, metadata = input_args
    env_values = {
        CTIMER_DELIMITER_ENVKEY : DELIMITER_STR,
        CTIMER_TIMEOUT_ENVKEY   : get_timeout(metadata["timeout_ms"])
    }
    env_values.update(metadata["setenv"])
    return run_one_impl(timer, log_dirname, write_golden, env_values, metadata)

def run_all(args: list, metadata_list: list, unique_count: int) -> int:
    remove_prev_log(args.log)
    num_tasks = len(metadata_list) # >= unique_count, because of repeating
    num_workers = 1 if args.sequential else min(num_tasks, NUM_WORKERS_MAX)
    sys.stderr.write("Found %d tasks (unique: %d), worker count: %d ...\n" % (
        num_tasks, unique_count, num_workers))
    run_tests_start_time = time.time()
    result_list = pool_map(num_workers, run_one, [
        (args.timer, args.log, args.write_golden, metadata)
        for metadata in metadata_list
    ])
    sys.stderr.write(cap_width("Completed, writing logs ...\r"))
    sys.stderr.flush()
    error_count, _ = print_summar_and_write_master_log(
        args, num_tasks, run_tests_start_time, result_list)
    return 0 if error_count == 0 else 1

NEEDED_METADATA_OBJECT_FIELD = [ # sync with EXPLANATION_STRING's spec
    "desc", "path", "args", "golden", "timeout_ms", "setenv", "exit"
]
NEEDED_EXIT_STATUS_OBJECT_FILED = [ # sync with EXPLANATION_STRING's spec
    "type", "repr"
]
VALID_ARG_SPECIAL_CHARS = "._+-*/=^@#" # sync with EXPLANATION_STRING's spec
def valid_arg(arg: str) -> bool:
    return all(
        (c.isalnum() or c in VALID_ARG_SPECIAL_CHARS)
        for c in arg
    )
def check_metadata_list_format(metadata_list: list) -> list: # not comprehensive
    if type(metadata_list) != list:
        return [ "matadata file does not store a JSON array " ]
    errors = []
    for i, metadata in enumerate(metadata_list):
        if type(metadata) != dict:
            errors.append("metadata #%-2d is not a JSON object" % (i + 1))
            continue
        for needed_metadata_field in NEEDED_METADATA_OBJECT_FIELD:
            if needed_metadata_field not in metadata:
                errors.append(
                    "metadata #%-2d does not contain field \"%s\"" % (
                        i + 1, needed_metadata_field))
        if "args" in metadata:
            args = metadata["args"]
            if type(args) != list:
                errors.append(
                    "metadata #%-2d field \"args\" is not an array" % (i + 1))
            elif next((e for e in args if (not valid_arg(e))), None) != None:
                errors.append("metadata #%-2d field \"args\" contains "
                              "invalid character" % (i + 1))
        if "timeout_ms" in metadata:
            timeout_ms = metadata["timeout_ms"]
            if type(timeout_ms) != int or timeout_ms <= 0:
                errors.append("metadata #%-2d field \"timeout_ms\" "
                              "is not a positive number" % (i + 1))
        if "setenv" in metadata:
            setenv = metadata["setenv"]
            if type(metadata["setenv"]) != dict:
                errors.append(
                    "metadata #%-2d field \"setenv\" is not a dict" % (i + 1))
            else:
                if any((type(k) != str) or ' ' in k for k in setenv.keys()):
                    errors.append("metadata #%-2d field \"setenv\" requires "
                                  "keys to be strings without spaces" % (i + 1))
                if any((type(v) != str) or ' ' in v for v in setenv.values()):
                    errors.append("metadata #%-2d field \"setenv\" requires "
                                  "values to be strings without spaces" % (i + 1))
        if "exit" in metadata:
            for needed_exit_status_field in NEEDED_EXIT_STATUS_OBJECT_FILED:
                if needed_exit_status_field not in metadata["exit"]:
                    errors.append("metadata #%-2d's \"exit\" object "
                                  "does not contain field \"%s\"" % (
                                      (i + 1), needed_exit_status_field))
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
        "path"    : string
            path to the test executable binary
        "args"    : array of strings
            the commandline arguments, all characters are alphanumeric or
            one of "._+-*/=^@#"
        "golden"  : string or null
            path to the golden file (see below); null: not needed
            * if '--write-golden' is given, stdout is written to this file
            * tests with the same expected stdout should not share the same
              file, to avoid race condition when '--write-golden' is given
        "timeout_ms" : integer or null
            the max processor time (ms); null: effectively infinite
        "setenv"  : dict
            environment variables provided when running the test executable
            * each entry's key and value are strings without spaces
        "exit"    : exit status object (see below), the expected exit status
    * all paths are relative to the current working directory
    * mutually exclusive: --meta, --paths

\x1b[33m'--paths':\x1b[0m
    In cases where only the paths of the test executables matter, prefer this
    option over '--meta', as it can be invoked with a list of space-separated
    test executable paths in commandline. Other fields required by a metadata
    object (see above) of each test will automatically get these values:
        desc = "", path = (the path provided with this option),
        args = [], golden = null, timeout_ms = null, setenv = {},
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
        2. argument hash string computed: (1) joining args with single blank
           spaces, and then (2) compute its SHA1 base16 representation (as a
           special case, all-zeros if there's no argument), then finally (3)
           take the first 8 digits
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
    The master log is human-readable, but is more suited to be loaded by
    another automation script to render it.

\x1b[33mMore on concepts:\x1b[0m
    metadata        (self-evident) description of a test
    golden file     the file storing the expected stdout output
    master log      a JSON file run_log.json under the log directory
    log directory   specified by '--log', which stores the master log
                    and tests' stdout and diff, if any, among others

\x1b[33mMore on options:\x1b[0m
    Concurrency is enabled, unless '--sequential' is given.
    Unless '--help' or '--docs' is given:
        * '--timer' is needed, and
        * exactly one of '--paths' and '--meta' is needed."""

def main():
    parser = argparse.ArgumentParser(
        description = "Test runner: with timer, logging, diff in HTML",
        epilog = "Unless '--docs' is given, exactly one of '--paths' "
                 "and '--meta' is needed."
    )
    parser.add_argument("--timer", metavar="TIMER", type=str, default=None,
                        help="path to the timer program")
    parser.add_argument("--meta", metavar="PATH", default=None,
                        help="JSON file of tests' metadata")
    parser.add_argument("--paths", metavar="T", nargs='+', default=[],
                        help="paths to test executables")
    parser.add_argument("-g", "--log", metavar="DIR", type=str, default="./logs",
                        help="directory to write logs, default: ./logs")
    parser.add_argument("-n", "--repeat", metavar="N", type=int, default=1,
                        help="run each test N times, default: 1")
    parser.add_argument("-1", "--sequential", action="store_true",
                        help="run sequentially instead concurrently")
    parser.add_argument("-s", "--seed", metavar="S", type=int, default=None,
                        help="set the seed for the random number generator")
    # In order to accommodate child projects, allow loading multiple declaration files
    # in a directory instead of loading one file.
    parser.add_argument("--flakiness", metavar="DIR", type=str, default=None,
                        help="load flakiness declaration files *.flaky under DIR")
    parser.add_argument("-w", "--write-golden", action="store_true",
                        help="write stdout to golden files instead of checking")
    parser.add_argument("--docs", action="store_true",
                        help="self-documentation in more details")
    args = parser.parse_args()

    if args.docs:
        print(EXPLANATION_STRING)
        return 0

    if args.timer == None:
        sys.exit("[Error] '--timer' is not given; use '-h' for help")
    elif not os.path.isfile(args.timer):
        sys.exit("[Error] timer program not found: %s" % args.timer)

    if ((len(args.paths) == 0 and args.meta == None)
     or (len(args.paths) > 0 and args.meta != None)):
        sys.exit("[Error] exactly one of '--paths' and '--meta' should be given.")
    if args.seed != None and args.write_golden:
        sys.exit("[Error] '--seed' and '--write-golden' cannot be used together.")
    if args.repeat != 1 and args.write_golden:
        sys.exit("[Error] '--repeat' and '--write-golden' cannot be used together.")
    if args.flakiness and not os.path.isdir(args.flakiness):
        sys.exit("[Error] directory not found: %s" % args.flakiness)

    metadata_list = None
    if len(args.paths):
        missing_executables = [ e for e in args.paths if not os.path.isfile(e) ]
        if len(missing_executables) > 0:
            sys.exit("[Error] the following executable(s) "
                     "are not found: %s" % str(missing_executables))
        metadata_list = [ get_metadata_from_path(path) for path in args.paths ]
    elif args.meta != None:
        if not os.path.isfile(args.meta):
            sys.exit("[Error] '--meta' file not found: %s" % args.meta)
        with open(args.meta, 'r') as f:
            try:
                metadata_list = json.load(f)
            except ValueError:
                sys.exit("[Error] not a valid JSON file: %s" % args.meta)
            errors = check_metadata_list_format(metadata_list) # sanity check
            if errors and len(errors):
                sys.exit("[Error] metadata is bad, checkout '--docs' "
                         "for requirements:\n\t" + "\n\t".join(errors))
    else: # Should not reach here; already checked by option filtering above
        raise RuntimeError("Should not reach here")

    if args.write_golden:
        prompt = ("About to overwrite golden files of tests with their stdout.\n"
                  "Are you sure? [y/N] >> ")
        consent = input(prompt)
        if not IS_ATTY:
            print("%s" % consent)
        if consent.lower() == "y":
            old_metadata_list_len = len(metadata_list)
            metadata_list = [ m for m in metadata_list if m["golden"] != None ]
            ignored_tests_count = old_metadata_list_len - len(metadata_list)
            if ignored_tests_count > 0:
                print("[Info] tests with no golden file specified "
                      "are ignored: %d" % ignored_tests_count)
        else:
            sys.exit("Aborted.")

    if len(metadata_list) == 0:
        sys.exit("[Error] no test found.")
    # here we add more fields to the metadata list:
    # 1. take care of args.repeat
    # 2. take care of args.flakiness
    metadata_list_new = []
    flakiness_dict = parse_flakiness_decls(args.flakiness)
    unique_count = len(metadata_list)
    for metadata in metadata_list:
        # case id is unique for every (path, args) combination
        comb_id = compute_comb_id(metadata["path"], metadata["args"]) # str
        metadata["comb_id"] = comb_id # str
        metadata["flaky_errors"] = flakiness_dict.get(comb_id, []) # list of str
        for i in irange(args.repeat): # if args.repeat != 1, then args.write_golden is False
            metadata_copy = copy.deepcopy(metadata)
            metadata_copy["repeat"] = { "count": i + 1, "all": args.repeat }
            metadata_list_new.append(metadata_copy)
    if not args.write_golden:
        random.seed(args.seed) # if args.seed == None, use a system-provided randomness source
        random.shuffle(metadata_list_new)
    run_all(args, metadata_list_new, unique_count)
    return 0 # regardless of whether all tests succeeded

if __name__ == "__main__":
    sys.exit(main())
