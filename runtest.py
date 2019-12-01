#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: runtest.py
# ---------------------------
# Run tests with timer, logging, and HTML diff view (if any).
# For more information, see README.md.
# For help: use '--help' and '--docs'.

import os, sys
import shutil
import copy
import json
import time
import argparse
import multiprocessing
import subprocess
import signal
import hashlib
import re
from diffhtmlstr import get_diff_html_str # mine

# avoid *.pyc of imported modules
sys.dont_write_bytecode = True

LOG_FILE_BASE = "run.log"
DELIMITER_STR = "#####"
INFINITE_TIME = 0 # it means effectively infinite time required by timer

IS_ATTY = sys.stdin.isatty() and sys.stdout.isatty() # testing might not be in a terminal
TERMINAL_COLS = int(os.popen('stty size', 'r').read().split()[1]) if IS_ATTY else 70
if (TERMINAL_COLS <= 25):
    sys.exit("[Error] terminal width (%d) is rediculously small" % TERMINAL_COLS)

def get_num_workers(env_var):
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
        return 2 * multiprocessing.cpu_count()
NUM_WORKERS_MAX = get_num_workers(env_var="NUM_WORKERS") # not "NUM_WORKERS_MAX", to be consistent

# possible exceptions (not Python's Exceptions) for user inputs
GOLDEN_NOT_WRITTEN_PREFIX = "golden file not written"
GOLDEN_NOT_WRITTEN_SAME_CONTENT  = "%s: content is the same" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_NOT_WRITTEN_WRONG_EXIT = "%s: the test's exit is not as expected" % GOLDEN_NOT_WRITTEN_PREFIX
GOLDEN_FILE_MISSING = "golden file missing"

# Set signal handlers
def sighandler(sig, frame):
    if sig == signal.SIGINT:
        sys.stderr.write("[SIGNAL] SIGINT sent to script %s\n" % os.path.basename(__file__))
    elif sig == signal.SIGTERM:
        sys.stderr.write("[SIGNAL] SIGTERM sent to script %s\n" % os.path.basename(__file__))
    elif sig == signal.SIGABRT:
        sys.stderr.write("[SIGNAL] SIGABRT sent to script %s\n" % os.path.basename(__file__))
    elif sig == signal.SIGSEGV:
        sys.stderr.write("[SIGNAL] SIGSEGV sent to script %s\n" % os.path.basename(__file__))
    else:
        sys.stderr.write("[SIGNAL] Signal %d sent to script %s\n" % (sig, os.path.basename(__file__)))
    sys.exit(1)
signal.signal(signal.SIGINT, sighandler)
signal.signal(signal.SIGTERM, sighandler)
signal.signal(signal.SIGABRT, sighandler)
signal.signal(signal.SIGSEGV, sighandler)

def fix_width(s, width=TERMINAL_COLS):
    extra_space = width - len(s)
    return (s + ' ' * extra_space) if extra_space >= 0 else (s[:12] + "..." + s[len(s) - width - 15:])

# NOTE not a class, due to a flaw in multiprocessing.Pool.map() in Python2
def get_metadata_from_path(path):
    # docs: see EXPLANATION_STRING below
    return {
        "desc": "",
        "path": path,
        "args": [],
        "golden": None,
        "timeout_ms": None,
        "exit": { "type": "normal", "repr": 0 }
    }

# run multiprocessing.Pool.map()
# NOTE the try-except block is to handle KeyboardInterrupt cleanly to fix a flaw in Python:
# KeyboardInterrupt cannot cleanly kill a multiprocessing.Pool()'s child processes, printing verbosely
# https://stackoverflow.com/a/6191991/8385554
# NOTE each 'func' has to ignore SIGINT for the aforementioned fix to work
def pool_map(num_workers, func, inputs):
    def init_lock(lock):
        global g_lock
        g_lock = lock
    l = multiprocessing.Lock()
    pool = multiprocessing.Pool(num_workers, initializer=init_lock, initargs=(l,))
    try:
        res = pool.map(func, inputs)
    except KeyboardInterrupt:
        pool.terminate()
        pool.join()
        sys.exit("Process pool terminated and child processes joined")
    pool.close()
    pool.join()
    return res

def split_ctimer_out(s):
    ctimer_begin_index = s.find(DELIMITER_STR)
    if ctimer_begin_index == -1:
        raise RuntimeError("beginning delimiter of ctimer stats not found")
    inspectee_stdout = s[:ctimer_begin_index]
    report_end_index = s.rfind(DELIMITER_STR)
    if report_end_index == -1:
        raise RuntimeError("end delimiter of ctimer stats not found")
    ctimer_stdout = s[ctimer_begin_index + len(DELIMITER_STR) : report_end_index]
    return inspectee_stdout.rstrip(), ctimer_stdout.rstrip()

def get_logfile_path_stem(log_dirname, metadata): # "stem" means no extension name such as ".diff"
    prog = metadata["path"]
    prog_basename = os.path.basename(prog)
    prog_dir_basename = os.path.basename(os.path.dirname(prog)) # "" if prog doesn't contain '/'
    path_repr = os.path.join(log_dirname, prog_dir_basename, prog_basename)
    args_hash = "00000"
    if len(metadata["args"]):
        args_hash = hashlib.sha1(' '.join(metadata["args"]).encode()).hexdigest()[:5]
    return "%s-%s-%s" % (path_repr, args_hash, metadata["repeat"]["count"])

# when not using '--write-golden'
def print_test_running_result_to_stderr(result, timer):
    rerun_command = ' '.join([ timer, result["path"] ] + result["args"])
    if result["ok"] == True:
        sys.stderr.write("\x1b[36m[ok]    %s\x1b[0m\n" % result["desc"])
    else:
        assert(result["ok"] == False)
        if len(result["exceptions"]):
            assert(result["exceptions"][0] == GOLDEN_FILE_MISSING)
            error_hint_string = "%s: %s" % (GOLDEN_FILE_MISSING, result["stdout"]["golden_file"])
        else:
            error_hint_string = "as expected: { \"exit\": %s, \"stdout\": %s }" % (
                str(result["exit"]["ok"]), str(result["stdout"]["ok"]))
        sys.stderr.write("\x1b[33m[error] %s\x1b[0m\n\t%s\n\t\x1b[2m%s\x1b[0m\n" % (
            result["desc"], error_hint_string, rerun_command))

# when using '--write-golden'
def print_golden_overwriting_result_to_stderr(result, timer):
    attempted_golden_file = result["stdout"]["golden_file"]
    not_written_exceptions = [ e for e in result["exceptions"] if e.startswith(GOLDEN_NOT_WRITTEN_PREFIX) ]
    rerun_command = ' '.join([ timer, result["path"] ] + result["args"])
    assert(len(not_written_exceptions) <= 1)
    if len(not_written_exceptions) == 0:
        sys.stderr.write("\x1b[36m[ok: content changed] %s\x1b[0m\n\twritten: %s (%d B)\n\t\x1b[2m%s\x1b[0m\n" % (
            result["desc"], attempted_golden_file, os.path.getsize(attempted_golden_file), rerun_command))
        return None
    assert(len(not_written_exceptions) == 1)
    if GOLDEN_NOT_WRITTEN_SAME_CONTENT in not_written_exceptions:
        sys.stderr.write("\x1b[36m[ok: same content] %s\x1b[0m\n\tskipped: %s\n\t\x1b[2m%s\x1b[0m\n" % (
            result["desc"], attempted_golden_file, rerun_command))
        return GOLDEN_NOT_WRITTEN_SAME_CONTENT
    elif GOLDEN_NOT_WRITTEN_WRONG_EXIT in not_written_exceptions:
        sys.stderr.write("\x1b[33m[error: unexpected exit status] %s\x1b[0m\n\tskipped: %s\n\t\x1b[2m%s\x1b[0m\n" % (
            result["desc"], attempted_golden_file, rerun_command))
        return GOLDEN_NOT_WRITTEN_WRONG_EXIT # the only one item
    else:
        assert(False)

def create_dir_if_needed(dirname):
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

def process_inspectee_stdout(s):
    # remove color sequences
    s = re.sub("\x1b\[.*?m", "", s)
    # do not use textwrap: unstable
    new_lines, cur_line, cnt = [], "", 0
    for c in s: # for each character
        cur_line += c
        cnt += 1
        if c == '\n':
            new_lines.append(cur_line) # ends with '\n'
            cur_line, cnt = "", 0
        elif cnt == 90: # this limit is used by diff.html and diffhtmlstr.py
            new_lines.append(cur_line + '\n') # force linebreak
            cur_line, cnt = "", 0
    return ''.join(new_lines)

def write_file(filename, s, assert_str_non_empty=False):
    assert(s != None)
    if assert_str_non_empty:
        assert(s != "")
    create_dir_if_needed(os.path.dirname(filename))
    with open(filename, 'w') as f:
        f.write(s)

# used by process_stdout()
def generate_result_dict(metadata, ctimer_reports, match_exit, write_golden, stdout_filename, diff_filename, exceptions):
    all_ok = match_exit and diff_filename == None
    return {
        "desc": metadata["desc"], # str
        "path": metadata["path"], # str
        "args": metadata["args"], # list
        "repeat": metadata["repeat"], # dict { "count": int, "all": int }
        "timeout_ms": metadata["timeout_ms"] if metadata["timeout_ms"] != None else INFINITE_TIME, # int
        "ok": all_ok, # boolean
        # details:
        "exit": {
            "ok": match_exit, # boolean: exit type and repr both match with expected
            # "type"  : string - "normal", "timeout", "signal", "quit", "unknown"
            # "repr"  : integer, indicating the exit code for "normal" exit, timeout
            #     value (millisec, processor time) for "timeout" exit, signal
            #     value "signal" exit, and null for others (timer errors)
            "expected": {
                "type": metadata["exit"]["type"], # str
                "repr": metadata["exit"]["repr"]  # int
            },
            "real": {
                "type": ctimer_reports["exit"]["type"], # str
                "repr": ctimer_reports["exit"]["repr"]  # int
            },
        },
        "stdout": {
            "ok": None if write_golden else (diff_filename == None), # boolean, or None for '--write-golden'
            "actual_file": stdout_filename,    # path (str), or None meaning no stdout or written to golden file
            "golden_file": metadata["golden"], # path (str), or None meaning no need to compare
            "diff_file":   diff_filename       # path (str), or None meaning 1) if "golden_file" == None: no need to compare
                                               #                          or 2) if "golden_file" != None: no diff found
        },
        "times_ms" : {
            "total": ctimer_reports["times_ms"]["total"],
        },
        "exceptions": exceptions # list of str, describe errors encountered in run_one() (not in test)
    } # NOTE any changes (key, value, meaning) made in this data structure must be honored in view.py

# used by run_one_impl()
def process_stdout(log_dirname, write_golden, metadata, inspectee_stdout, ctimer_stdout):
    assert(len(ctimer_stdout))
    ctimer_dict = json.loads(ctimer_stdout)
    match_exit = (metadata["exit"]["type"] == ctimer_dict["exit"]["type"]
                  and metadata["exit"]["repr"] == ctimer_dict["exit"]["repr"]) # metadata["exit"] may have more keys
    exceptions = [] # list of str, describe misc errors in run_one() itself (not in test)
    filepath_stem = get_logfile_path_stem(log_dirname, metadata)
    stdout_filename = None if write_golden else filepath_stem + ".stdout"
    diff_filename = None
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
                metadata["desc"], ' '.join([ metadata["path"] ] + metadata["args"]),
                golden_filename, stdout_filename
            )
            if not found_golden:
                exceptions.append(GOLDEN_FILE_MISSING)
            if stdout_comparison_diff != None: # write only if diff is not empty
                # use abspath(): easier to copy-paste to browser
                # ends with ".html": Chrome doesn't recognize mime, for various reasons
                diff_filename = os.path.abspath(filepath_stem + ".diff.html")
                write_file(diff_filename, stdout_comparison_diff, assert_str_non_empty=True)
    return generate_result_dict(
        metadata, ctimer_dict, match_exit, write_golden, stdout_filename, diff_filename, exceptions)

# used by run_all()
def remove_prev_log(args):
    if os.path.isdir(args.log):
        # to prevent perplexing cases e.g. master log says all is good, but *.diff files
        # from a previous run exist
        shutil.rmtree(args.log)
    elif os.path.exists(args.log):
        sys.exit("[Error] path exists as a non-directory: %s" % args.log)

# used by run_all()
def write_master_log(args, num_tests, start_time, result_list):
    assert(len(result_list) == num_tests)
    error_result_count = 0
    if args.write_golden:
        golden_written_count, golden_same_content_count, golden_wrong_exit_count = 0, 0, 0
    for result in result_list:
        wanted_to_write_this_golden = args.write_golden and result["stdout"]["golden_file"] != None
        if not wanted_to_write_this_golden:
            print_test_running_result_to_stderr(result, args.timer)
        if result["ok"] == False:
            error_result_count += 1
        if wanted_to_write_this_golden:
            not_written_reason = print_golden_overwriting_result_to_stderr(result, args.timer)
            if not_written_reason == GOLDEN_NOT_WRITTEN_SAME_CONTENT:
                golden_same_content_count += 1
            elif not_written_reason == GOLDEN_NOT_WRITTEN_WRONG_EXIT:
                golden_wrong_exit_count += 1
            elif not_written_reason == None:
                golden_written_count += 1
    color_head = "\x1b[32m" if error_result_count == 0 else "\x1b[31m"
    if args.write_golden:
        sys.stderr.write("Golden file writing:\n")
        sys.stderr.write("\t%d written, %d skipped (same content: %d, error: %d)\n" % (
            golden_written_count,
            golden_same_content_count + golden_wrong_exit_count,
            golden_same_content_count, golden_wrong_exit_count))
    create_dir_if_needed(args.log)
    log_filename = os.path.join(args.log, LOG_FILE_BASE)
    with open(log_filename, 'w') as f:
        json.dump(result_list, f, indent=2, sort_keys=True)
    sys.stderr.write("%sDone: %.2f sec, passed: %d/%d, log: %s\x1b[0m\n" % (
        color_head, time.time() - start_time, num_tests - error_result_count, num_tests, log_filename))
    return error_result_count

class global_lock: # across child processes
    def __init__(self):
        pass
    def __enter__(self):
        g_lock.acquire()
    def __exit__(self, etype, value, traceback):
        g_lock.release()

# used by run_one()
def run_one_impl(timer, log_dirname, write_golden, env_values, metadata):
    with open(os.devnull, 'w') as devnull:
        # the return code of ctimer is guaranteed to be 0 unless ctimer itself has errors
        try:
            stdout = subprocess.check_output(
                [ timer, metadata["path"] ] + metadata["args"], stderr=devnull, env=env_values).decode().rstrip()
        except subprocess.CalledProcessError as e:
            # the code path signals an internal error of the timer program (see '--docs')
            raise RuntimeError("Internal error (exit %d): %s" % (e.returncode, e.cmd))
    inspectee_stdout_raw, ctimer_stdout = split_ctimer_out(stdout)
    inspectee_stdout = process_inspectee_stdout(inspectee_stdout_raw)
    run_one_single_result = process_stdout( # return a dict
        log_dirname, write_golden, metadata, inspectee_stdout, ctimer_stdout)
    if metadata["repeat"]["all"] > 1:
        metadata_desc = "(repeat %d/%d) %s" % (
            metadata["repeat"]["count"], metadata["repeat"]["all"], metadata["desc"])
    else:
        metadata_desc = metadata["desc"]
    with global_lock():
        if run_one_single_result["ok"] == True:
            sys.stderr.write(fix_width("DONE %s" % metadata_desc) + '\r')
            time.sleep(0.05) # let the line stay for a while: prettier, though adding overhead
        else: # details or error will be printed after all execution
            sys.stderr.write(fix_width("\x1b[33;1merror\x1b[0m %s\n" % metadata_desc) + '\r') # has linebreak
        sys.stderr.flush()
    return run_one_single_result

def run_one(input_args):
    signal.signal(signal.SIGINT, signal.SIG_IGN) # ignore SIGINT, required by pool_map()
    timer, log_dirname, write_golden, metadata = input_args
    env_values = {
        "CTIMER_DELIMITER": DELIMITER_STR,
        "CTIMER_TIMEOUT"  : str(metadata["timeout_ms"] if metadata["timeout_ms"] != None else INFINITE_TIME)
    }
    return run_one_impl(timer, log_dirname, write_golden, env_values, metadata)

def run_all(args, metadata_list):
    remove_prev_log(args)
    num_tests = len(metadata_list)
    num_workers = 1 if args.sequential else min(num_tests, NUM_WORKERS_MAX)
    sys.stderr.write("Running %d tests, worker count: %d ...\n" % (
        num_tests, num_workers))
    start_time = time.time()
    result_list = pool_map(num_workers, run_one, [
        (args.timer, args.log, args.write_golden, metadata) for metadata in metadata_list
    ])
    sys.stderr.write(fix_width("Completed, writing logs ...") + '\n')
    sys.stderr.flush()
    error_count = write_master_log(args, num_tests, start_time, result_list)
    return 0 if error_count == 0 else 1

NEEDED_METADATA_OBJECT_FIELD = [ # sync with EXPLANATION_STRING's spec
    "desc", "path", "args", "golden", "timeout_ms", "exit"
]
NEEDED_EXIT_STATUS_OBJECT_FILED = [ # sync with EXPLANATION_STRING's spec
    "type", "repr"
]
def get_matadata_list_format_errors(metadata_list):
    if type(metadata_list) != list:
        return [ "matadata file does not store a JSON array " ]
    errors = []
    for i, metadata in enumerate(metadata_list):
        if type(metadata) != dict:
            errors.append("metadata #%d is not a JSON object" % (i + 1))
            continue
        for needed_metadata_field in NEEDED_METADATA_OBJECT_FIELD:
            if needed_metadata_field not in metadata:
                errors.append("metadata #%d does not contain field \"%s\"" % (
                    (i + 1), needed_metadata_field))
        if "exit" in metadata:
            for needed_exit_status_field in NEEDED_EXIT_STATUS_OBJECT_FILED:
                if needed_exit_status_field not in metadata["exit"]:
                    errors.append("metadata #%d's \"exit\" object does not contain field \"%s\"" % (
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
            "total" : integer, inspectee's total processor time
    note: the timer should always exit with 0 regardless of the inspected
          program's exit status; non-0 exit is reserved for internal error.

\x1b[33m'--meta':\x1b[0m
    This option passes the path of a file containing the metadata of tests.
    The metadata file could be either hand-written or script-generated; it
    stores a JSON string representing an array of objects, with keys:
        "desc"    : string
            description of the test
        "path"    : string
            path to the test executable
        "args"    : array of strings
            the commandline arguments
        "golden"  : string or null
            path to the golden file (see below); null: not needed
            * if '--write-golden' is given, stdout is written to this file
            * tests with the same expected stdout should not share the same
              file, to avoid race condition when '--write-golden' is given
        "timeout_ms" : integer or null
            the max processor time (ms); null: effectively infinite
        "exit"    : exit status object (see below), the expected exit status

\x1b[33m'--paths':\x1b[0m
    Using this option to pass executables' paths is convenient in some use
    cases, as it doesn't require a metadata file to be prepared ahead of time:
    it's equivalent to setting each test's metadata:
        desc = "", path = (path), args = [], golden = null, timeout_ms = null
        exit = { "type": "normal", "repr": 0 } (exit status, see below)

\x1b[33m'--write-golden':\x1b[0m
    Use this option to create or overwrite golden files of tests. Tests with
    golden file unspecified (i.e. metadata's "golden" field is null) will not
    be executed.
    A golden file will be written only if the exit status of that test is as
    expected, and if the file exists, the content will be different.
    You have to manually check the tests are correct before writing.

\x1b[33mExit status object:\x1b[0m
    A JSON object with keys:
    "type"  : string - "normal", "timeout", "signal", "quit", "unknown"
    "repr"  : integer, indicating the exit code for "normal" exit, timeout
              value (millisec, processor time) for "timeout" exit, signal
              value "signal" exit, and null for others (timer errors)

\x1b[33mMaster log and result object:\x1b[0m
    The master log is a JSON file containing an array of result objects. To
    see the specification of the result object, please refer to the in-line
    comments in function `generate_result_dict()`.
    The master log is human-readable, but is more suited to be loaded by
    another automation script to render it.

\x1b[33mMore on concepts:\x1b[0m
    metadata        (self-evident) description of a test
    golden file     the file storing the expected stdout output
    master log      a JSON file run.log under the log directory
    log directory   specified by '--log', which stores the master log
                    and tests' stdout and diff, if any, among others

\x1b[33mMore on options:\x1b[0m
    Concurrency is enabled, unless '--sequential' is given.
    Unless '--help' or '--docs' is given:
        * '--timer' is needed, and
        * exactly one of '--paths' and '--meta' is needed."""

def main():
    parser = argparse.ArgumentParser(description="Test runner: with timer, logging, diff in HTML",
                                     epilog="Unless '--docs' is given, exactly one of '--paths' and '--meta' is needed.")
    parser.add_argument("--timer", metavar="TIMER", type=str, default=None,
                        help="path to the timer program")
    parser.add_argument("--meta", metavar="PATH", default=None,
                        help="JSON file of tests' metadata")
    parser.add_argument("--paths", metavar="T", nargs='+', default=[],
                        help="paths to test executables")
    parser.add_argument("-g", "--log", metavar="DIR", type=str, default="./logs",
                        help="directory to write logs, default: ./logs")
    parser.add_argument("-n", "--times", metavar="N", type=int, default=1,
                        help="run each test N times, default: 1")
    parser.add_argument("-1", "--sequential", action="store_true",
                        help="run sequentially instead concurrently")
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
    if args.times != 1 and args.write_golden:
        sys.exit("[Error] '--times' and '--write-golden' cannot be used together.")

    metadata_list = None
    if len(args.paths):
        missing_executables = [ e for e in args.paths if not os.path.isfile(e) ]
        if len(missing_executables) > 0:
            sys.exit("[Error] the following executable(s) are not found: %s" % str(missing_executables))
        metadata_list = [ get_metadata_from_path(path) for path in args.paths ]
    if args.meta != None:
        if not os.path.isfile(args.meta):
            sys.exit("[Error] '--meta' file not found: %s" % args.meta)
        with open(args.meta, 'r') as f:
            try:
                metadata_list = json.load(f)
            except ValueError:
                sys.exit("[Error] not a valid JSON file: %s" % args.meta)
            errors = get_matadata_list_format_errors(metadata_list) # sanity check
            if errors and len(errors):
                sys.exit("[Error] metadata is bad, checkout '--docs' for requirements:\n\t" + "\n\t".join(errors))

    if args.write_golden:
        prompt = "About to overwrite golden files of tests with their stdout.\nAre you sure? [y/N] >> "
        consent = raw_input(prompt) if sys.version_info[0] == 2 else input(prompt)
        if not IS_ATTY:
            print("%s" % consent)
        if consent.lower() == "y":
            old_metadata_list_len = len(metadata_list)
            metadata_list = [ m for m in metadata_list if m["golden"] != None ]
            ignored_tests_count = old_metadata_list_len - len(metadata_list)
            if ignored_tests_count > 0:
                print("[Info] tests with no golden file specified are ignored: %d" % ignored_tests_count)
        else:
            sys.exit("Aborted.")

    if len(metadata_list) == 0:
        sys.exit("[Error] no test found.")
    metadata_list_with_times = []
    for metadata in metadata_list:
        for i in range(args.times): # not 'xrange()' to accommodate both Python2 and Python3, nasty Python
            metadata_copy = copy.deepcopy(metadata)
            metadata_copy["repeat"] = { "count": i + 1, "all": args.times }
            metadata_list_with_times.append(metadata_copy)
    return run_all(args, metadata_list_with_times)

if __name__ == "__main__":
    sys.exit(main())
