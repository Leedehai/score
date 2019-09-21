#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: runtest.py
# ---------------------------
# The script runs test driver(s).

import os, sys
import json
import time
import argparse
import difflib
import multiprocessing
import subprocess
import signal
import hashlib

DELIMITER_STR = "#####"
DEFAULT_TIMEOUT = 1500

# Set signal handlers
def sighandler(sig, frame):
    if sig == signal.SIGINT:
        sys.stderr.write("[SIGNAL] SIGINT sent to script %s\n" % os.path.basename(__file__))
    elif sig == signal.SIGTERM:
        sys.stderr.write("[SIGNAL] SIGTERM sent to script %s\n" % os.path.basename(__file__))
    else:
        sys.stderr.write("[SIGNAL] Signal %d sent to script %s\n" % (sig, os.path.basename(__file__)))
    sys.exit(1)
signal.signal(signal.SIGINT, sighandler)
signal.signal(signal.SIGTERM, sighandler)

# NOTE not a class, due to a flaw in multiprocessing.Pool.map() in Python2
def get_metadata_from_path(path):
    # docs: see EXPLAINATION_STRING below
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
def pool_map(pool, func, inputs):
    try:
        res = pool.map(func, inputs)
    except KeyboardInterrupt:
        pool.terminate()
        pool.join()
        sys.exit("Process pool terminated and child processes joined")
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
    if len(metadata["args"]):
        # 5 digit hash should be enough
        args_hash = hashlib.sha1(' '.join(metadata["args"])).hexdigest()[:5]
        return "%s-%s" % (path_repr, args_hash)
    else:
        return path_repr

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

def write_stdout_file(stdout_filename, stdout_string):
    assert(stdout_string != None and stdout_string != "")
    create_dir_if_needed(os.path.dirname(stdout_filename))
    with open(stdout_filename, 'w') as f:
        f.write(stdout_string)

def write_diff_file(diff_filename, diff_string):
    assert(diff_string != None and diff_string != "")
    create_dir_if_needed(os.path.dirname(diff_filename))
    with open(diff_filename, 'w') as f:
        f.write(diff_string)

def get_diff_str(actual_str, expected_file):
    with open(expect_file, 'r') as f:
        expected_str = f.read()
    # TODO, because GoogleTest executables don't need output comparison
    return None # same

def generate_result_dict(metadata, ctimer_reports, stdout_filename, diff_filename):
    match_exit = (metadata["exit"]["type"] == ctimer_reports["exit"]["type"]
                   and metadata["exit"]["repr"] == ctimer_reports["exit"]["repr"])
    no_comparison_or_no_diff = diff_filename == None
    all_ok = match_exit and no_comparison_or_no_diff
    return {
        "desc": metadata["desc"], # str
        "path": metadata["path"], # str
        "args": metadata["args"], # list
        "timeout_ms": metadata["timeout_ms"] if metadata["timeout_ms"] != None else DEFAULT_TIMEOUT, # int
        "ok": all_ok, # boolean
        # details:
        "exit": {
            "ok": match_exit, # boolean
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
            "ok": no_comparison_or_no_diff, # boolean
            "actual_file": stdout_filename,    # path (str), or None meaning no stdout
            "expect_file": metadata["golden"], # path (str), or None meaning no need to compare
            "diff_file":   diff_filename       # path (str), or None meaning 1) if "expect_file" == None: no need to compare
                                               #                          or 2) if "expect_file" != None: no diff found
        },
        "times_ms" : {
            "total": ctimer_reports["times_ms"]["total"],
        }
    }

def run_one(input_args):
    signal.signal(signal.SIGINT, signal.SIG_IGN) # ignore SIGINT, required by pool_map()
    timer, log_dirname, metadata = input_args
    command = [ timer, metadata["path"] ] + metadata["args"]
    env_values = {
        "CTIMER_DELIMITER": DELIMITER_STR,
        "CTIMER_TIMEOUT"  : str(metadata["timeout_ms"] if metadata["timeout_ms"] != None else DEFAULT_TIMEOUT)
    }
    with open(os.devnull, 'w') as devnull:
        # the return code of ctimer is guaranteed to be 0 unless ctimer itself has errors
        stdout = subprocess.check_output(
            command, stderr=devnull, env=env_values).decode().rstrip()
    inspectee_stdout, ctimer_stdout = split_ctimer_out(stdout)
    filepath_stem = get_logfile_path_stem(log_dirname, metadata)
    stdout_filename, diff_filename = None, None
    if len(inspectee_stdout): # write only if stdout is not empty
        stdout_filename = filepath_stem + ".stdout"
        write_stdout_file(stdout_filename, inspectee_stdout)
    if metadata["golden"] != None: # compare only if golden exists
        stdout_comparison_diff = get_diff_str(inspectee_stdout, metadata["golden"])
        if stdout_comparison_diff != None: # write only if diff is not empty
            diff_filename = filepath_stem + ".diff"
            write_diff_file(diff_filename, stdout_comparison_diff)
    return generate_result_dict(
        metadata, json.loads(ctimer_stdout), stdout_filename, diff_filename)

NUM_WORKERS_MAX = 2 * multiprocessing.cpu_count()
def run_all(timer, is_sequential, log_filename, metadata_list):
    num_tests = len(metadata_list)
    log_dirname = os.path.dirname(log_filename)
    num_workers = 1 if is_sequential else min(num_tests, NUM_WORKERS_MAX)
    sys.stderr.write("Start running %d tests, worker count: %d ...\n" % (
        num_tests, num_workers))
    pool = multiprocessing.Pool(num_workers)
    start_time = time.time()
    result_list = pool_map(pool, run_one, [
        (timer, log_dirname, metadata) for metadata in metadata_list
    ])
    assert(len(result_list) == num_tests)
    error_results = [ result for result in result_list if result["ok"] == False ]
    for result in error_results:
        rerun_command = ' '.join([ timer, result["path"] ] + result["args"])
        sys.stderr.write("\x1b[33m[logged error] %s\x1b[0m\n\tas expected: { \"exit\": %s, \"stdout\": %s }\n\t%s\n" % (
            result["desc"], str(result["exit"]["ok"]).lower(), str(result["stdout"]["ok"]).lower(), rerun_command))
    error_count = len(error_results)
    color_head = "\x1b[32m" if error_count == 0 else "\x1b[31m"
    sys.stderr.write("%sDone: %.2f sec, passed: %d/%d, log: %s\x1b[0m\n" % (
        color_head, time.time() - start_time, num_tests - error_count, num_tests, log_filename))
    create_dir_if_needed(log_dirname)
    with open(log_filename, 'w') as f:
        json.dump(result_list, f, indent=2, sort_keys=True)
    return 0 if error_count == 0 else 1

EXPLAINATION_STRING = """Explanations:

'--timer' passes the path of a timer program that measures a program's
    processor time (not wall time) with timeout, and its interface satisfies:
    [example] https://github.com/Leedehai/ctimer (mine)
    inputs:
        commandline arguments:
            the invocation of the inspected program
        environment variable CTIMER_TIMEOUT:
            timeout value (ms); if not given, use the default value
        environment variable CTIMER_STATS:
            file path to write stats report; if not given, print to stdout
        environment variable CTIMER_DELIMITER:
            delimiter string at the beginning and end of the stats report
            string; if not given, use empty string
        note: the script will set the environment variables as needed locally
            when invoking the timer program
    outputs: the inspected program's outputs (stdout, stderr), with stats
        report in stdout if CTIMER_STATS is unspecified; if CTIMER_STATS
        is specified, the stats report will be written to that file
    the stats report is a JSON string, representing an object:
        "exit"     : exit status object (see below), inspectee's exit status
        "times_ms" : object:
            "total" : integer, inspectee's total processor time

'--meta' passes the path of a file containing the metadata of tests.
    the file content is a JSON string representing an array of objects, each
    of which has keys:
        "desc"    : string
            description of test
        "path"    : string
            path to the test executable
        "args"    : array of strings
            the commandline arguments
        "golden"  : string or null
            path to the stdout's expected output file; null: not needed
        "timeout_ms" : integer or null
            the max processor time (ms); null: using default (%d)
        "exit"    : exit status object (see below), the expected exit status

Using '--paths' to pass executables' paths is equivalent to setting metadata:
    desc = "", path = (path), args = [], out = null, timeout = null
    exit = { "type": "normal", "repr": 0 }

Exit status object is a JSON object with keys:
    "type"  : string - "normal", "timeout", "signal", "quit", "unknown"
    "repr"  : integer, indicating the exit code for "normal" exit, timeout
              value (millisec, processor time) for "timeout" exit, signal
              value "signal" exit, and null for others (timer errors)

Exactly one of '--paths' and '--meta' is needed.""" % DEFAULT_TIMEOUT

def main():
    parser = argparse.ArgumentParser(description="Test runner with timer and logging",
                                     epilog="Unless '--explain' is given, exactly one of '--paths' and '--meta' is needed.")
    parser.add_argument("--timer", metavar="TIMER", type=str, default=None,
                        help="path to the timer program (required)")
    parser.add_argument("--paths", metavar="T", nargs='+', default=[],
                        help="paths to test executables")
    parser.add_argument("--meta", metavar="PATH", default=None,
                        help="JSON file of tests' metadata")
    parser.add_argument("-1", "--sequential", action="store_true",
                        help="run sequentially instead concurrently")
    parser.add_argument("-g", "--log", metavar="LOG", type=str, default="logs/test.log",
                        help="file to write logs, default: logs/test.log")
    parser.add_argument("-e", "--explain", action="store_true",
                        help="explain '--timer', '--paths' and '--meta'")
    args = parser.parse_args()

    if args.explain:
        print(EXPLAINATION_STRING)
        return 0

    if args.timer == None:
        sys.exit("[Error] '--timer' is not given; use '-h' for help")
    elif not os.path.isfile(args.timer):
        sys.exit("[Error] timer program not found: %s" % args.timer)

    if ((len(args.paths) == 0 and args.meta == None)
     or (len(args.paths) > 0 and args.meta != None)):
        sys.exit("[Error] exactly one of '--paths' and '--meta' should be given.")

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
            metadata_list = json.load(f)

    return run_all(args.timer, args.sequential, args.log, metadata_list)

if __name__ == "__main__":
    sys.exit(main())
