#!/usr/bin/env python3
# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the MIT LICENSE.txt file.
# -----
# For more information, see README.md.
# For help: use '--help' and '--docs'.

import sys
py = sys.version_info
if py.major == 2 or (py.major == 3 and py.minor < 7):
    sys.exit("[Error] mininum Python version is 3.7")

import argparse
import copy
import hashlib
import json
import multiprocessing.dummy as mp  # threading wrapped using multiprocessing API
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from pylibs import score_utils
from pylibs.docs import EXPLANATION_STRING
from pylibs.differ import get_diff_html_str
from pylibs.flakiness import maybe_parse_flakiness_decls_from_dir
from pylibs.runner_task_res import generate_result_dict
from pylibs import rotating_logger
from pylibs.runner_common import (
    Args,
    TaskMetadata,
    TaskResult,
    TaskWorkerArgs,
    TaskEnvKeys,
    TaskExceptions,
    DELIMITER_STR,
    LOG_FILE_BASE,
    NUM_WORKERS_MAX,
)
from pylibs.runner_print import (
    print_one_task_realtime_log,
    print_summary_report,
)
from pylibs.score_utils import SYS_NAME, err_exit, info_s, error_s
from pylibs import schema


def sighandler(sig, frame):  # pylint: disable=unused-argument
    sys.exit(2)  # Do not print: it's ugly if all workers print simultaneously.


signal.signal(signal.SIGINT, sighandler)  # type: ignore
signal.signal(signal.SIGTERM, sighandler)  # type: ignore
signal.signal(signal.SIGABRT, sighandler)  # type: ignore
signal.signal(signal.SIGSEGV, sighandler)  # type: ignore


def get_metadata_from_path(test_id: str, path: str) -> Dict[str, Any]:
    return {  # Docs: see pylibs.docs.EXPLANATION_STRING.
        "id": test_id, "path": path, "args": [], "envs": None, "prefix": [],
        "golden": None, "timeout_ms": None,
        "exit": {"type": "return", "repr": 0}
    }


# Run mp.Pool.map()
# NOTE The try-except block is to handle KeyboardInterrupt cleanly to fix a flaw
# in Python: KeyboardInterrupt cannot cleanly kill mp.Pool()'s child processes,
# printing verbosely: https://stackoverflow.com/a/6191991/8385554
# NOTE Each 'func' has to ignore SIGINT for the aforementioned fix to work.
def pool_map(
    num_workers: int,
    func: Callable[[TaskWorkerArgs], TaskResult],
    inputs: List[TaskWorkerArgs],
) -> List[TaskResult]:
    with rotating_logger.logging_server():
        pool = mp.Pool(num_workers)
        try:
            results: List[TaskResult] = pool.map(func, inputs)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            err_exit("Process pool terminated and child processes joined")
        pool.close()
        pool.join()
        # This should be called after worker threads are joined to avoid
        # race condition. We don't send a clear command via socket, because
        # that may arrive at the socket after the logging server is closed.
        rotating_logger.clear_all_transient_logs()
        return results


def split_ctimer_out(s: str) -> Tuple[str, str]:
    ctimer_begin_index = s.find(DELIMITER_STR)
    if ctimer_begin_index == -1:
        raise RuntimeError("beginning delimiter of ctimer stats not found")
    inspectee_stdout = s[:ctimer_begin_index]
    report_end_index = s.rfind(DELIMITER_STR)
    if report_end_index == -1:
        raise RuntimeError("end delimiter of ctimer stats not found")
    ctimer_stdout = s[ctimer_begin_index + len(DELIMITER_STR):report_end_index]
    return inspectee_stdout.rstrip(), ctimer_stdout.rstrip()


def compute_hashed_id(prog: Path, id_name: str) -> str:
    """
    id_name, though already unique among tests, may contain characters
    like ":", "/". This function returns a hashed version of id_name.
    """
    # In fact, id_name alone can uniquely identify a test, but prefixing it with
    # prog.name makes the returned string human-friendly.
    id_name_hashed = hashlib.sha1(id_name.encode()).hexdigest()
    return "%s-%s" % (prog.name, id_name_hashed.lower())


# This path stem (meaning there is no extension such as ".diff"), e.g.
# hashed_id = "hello-0ade7", repeat 3 out of 10, log_dirname = "./out/foo/logs"
#   => return: "./out/foo/logs/_he-0a/hello-0ade7-3"
def get_logfile_path_stem(
    hashed_id: str,
    repeat_count: int,
    log_dirname: str,
) -> str:
    hashed_e1, hashed_e2 = hashed_id.split('-', 1)
    log_subname = "_" + hashed_e1[:2] + hashed_e2[:2]
    return "%s-%s" % (Path(log_dirname, log_subname, hashed_id), repeat_count)


def create_dir_if_needed(dirname: str) -> None:
    # It appears try-catch can avoid race conditions when multiple threads want
    # to create the same directory: https://stackoverflow.com/a/12468091/8385554
    try:
        os.makedirs(dirname)  # Create intermediate dirs if necessary.
    except OSError:
        pass


# Can be used concurrently.
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
    return re.sub(r"\x1b\[.*?m", "", s)  # Remove color sequences.


def did_run_one_task(
    log_dirname: str,
    write_golden: bool,
    metadata: TaskMetadata,
    inspectee_stdout: str,
    ctimer_stdout: str,
    start_abs_time: float,
    end_abs_time: float,
) -> TaskResult:
    assert len(ctimer_stdout) > 0
    ctimer_dict: Dict[str, Any] = json.loads(ctimer_stdout)
    match_exit: bool = \
        (metadata["exit"]["type"] == ctimer_dict["exit"]["type"]
         and metadata["exit"]["repr"] == ctimer_dict["exit"]["repr"])
    exceptions: List[TaskExceptions] = []
    filepath_stem = get_logfile_path_stem(  # "stem" means no extension name
        metadata["hashed_id"], metadata["repeat"]["count"], log_dirname)
    stdout_filename = None
    if not write_golden:
        stdout_filename = os.path.abspath(filepath_stem + ".stdout")
    # diff_filename will be set with a str later if there is need to compare
    # and diff is found.
    diff_filename = None
    if stdout_filename:
        assert not write_golden
        write_file(stdout_filename, inspectee_stdout)  # stdout could be ""
    if metadata["golden"] != None:  # Write golden or compare stdout with it.
        golden_filename = metadata["golden"]
        if write_golden:  # Write stdout to golden.
            if not match_exit:
                exceptions.append(TaskExceptions.GOLDEN_NOT_WRITTEN_WRONG_EXIT)
            else:
                golden_exists_and_same = False
                if os.path.isfile(golden_filename):
                    with open(golden_filename, 'r') as f:
                        if f.read() == inspectee_stdout:
                            golden_exists_and_same = True
                            exceptions.append(
                                TaskExceptions.GOLDEN_NOT_WRITTEN_SAME_CONTENT)
                if not golden_exists_and_same:
                    write_file(golden_filename,
                               inspectee_stdout)  # The stdout could be "".
        else:  # Compare stdout with golden.
            assert stdout_filename
            found_golden, stdout_comparison_diff = get_diff_html_str(
                html_title=filepath_stem.split(os.sep)[-1],
                desc=metadata["id"],
                expected_filename=golden_filename,
                actual_filename=stdout_filename,
            )
            if not found_golden:
                exceptions.append(TaskExceptions.GOLDEN_FILE_MISSING)
            if stdout_comparison_diff != None:  # Write if diff is non-empty.
                diff_filename = os.path.abspath(filepath_stem + ".diff.html")
                write_file(diff_filename,
                           stdout_comparison_diff,
                           assert_str_non_empty=True)
    return generate_result_dict(metadata, ctimer_dict, match_exit, write_golden,
                                start_abs_time, end_abs_time, stdout_filename,
                                diff_filename, exceptions)


# Used by run_all()
def remove_prev_log(log_dir: str) -> None:
    if os.path.isdir(log_dir):
        # To prevent perplexing cases e.g. master log says all is good, but
        # *.diff files from a previous run exist.
        shutil.rmtree(log_dir)
    elif os.path.exists(log_dir):
        err_exit(error_s("path exists as a non-directory: %s" % log_dir))


# Used by run_one()
def run_one_task_impl(timer: str, also_stderr: bool, log_dirname: str,
                      write_golden: bool, env_values: Dict[str, str],
                      metadata: TaskMetadata) -> TaskResult:
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
        o = subprocess.check_output(
            [timer] + metadata["prefix"] + [metadata["path"]] +
            metadata["args"],
            stderr=subprocess.STDOUT if also_stderr else subprocess.DEVNULL,
            env=env_values)
        stdout = o.decode(errors="backslashreplace").rstrip()
        end_abs_time = time.time()
    except subprocess.CalledProcessError as e:
        # The code path signals an internal error of the timer (see '--docs').
        raise RuntimeError("Internal error (exit %d): %s" %
                           (e.returncode, e.cmd))
    inspectee_stdout_raw, ctimer_stdout = split_ctimer_out(stdout)
    inspectee_stdout = process_inspectee_stdout(inspectee_stdout_raw)
    one_task_result: TaskResult = did_run_one_task(
        log_dirname,
        write_golden,
        metadata,
        inspectee_stdout,
        ctimer_stdout,
        start_abs_time,
        end_abs_time,
    )
    return one_task_result


def get_platform_dependent_envs():
    res = {}
    library_path_envkey = None
    if SYS_NAME == "mac":
        library_path_envkey = "DYLD_LIBRARY_PATH"
        # Required by timer. Linux reports max resident set size in KB, but
        # macOS reports it in B, but we need the result in KB universally,
        # and this environment variable is used to tell the timer it should
        # convert the number: https://github.com/leedehai/ctimer/README.md.
        res.update({"RUSAGE_SIZE_BYTES": "1"})
    elif SYS_NAME == "linux":
        library_path_envkey = "LD_LIBRARY_PATH"
    if library_path_envkey != None and library_path_envkey in os.environ:
        res.update({library_path_envkey: os.environ[library_path_envkey]})
    return res


PLATFORM_DEPENDENT_ENVS = get_platform_dependent_envs()


def run_one_task(input_args: TaskWorkerArgs) -> TaskResult:
    timer, also_stderr, log_dirname, write_golden, metadata = input_args
    env_values = PLATFORM_DEPENDENT_ENVS
    env_values.update({
        TaskEnvKeys.CTIMER_DELIMITER_ENVKEY.value: DELIMITER_STR,
        TaskEnvKeys.CTIMER_TIMEOUT_ENVKEY.value: score_utils.get_timeout(
            metadata["timeout_ms"]),
    })
    if metadata["envs"] != None:
        env_values.update(metadata["envs"])
    one_task_result = run_one_task_impl(
        timer,
        also_stderr,
        log_dirname,
        write_golden,
        env_values,
        metadata,
    )
    print_one_task_realtime_log(metadata, one_task_result)
    return one_task_result


def run_all(
    args: Args,
    metadata_list: List[TaskMetadata],
    unique_count: int,
) -> int:
    remove_prev_log(args.log)
    num_tasks = len(metadata_list)  # >= unique_count, because of repeating
    num_workers = 1 if args.sequential else min(num_tasks, NUM_WORKERS_MAX)
    sys.stderr.write(
        info_s("task count: %d (unique: %d), worker count: %d" %
               (num_tasks, unique_count, num_workers)))
    run_tests_start_time = time.time()
    result_list: List[TaskResult] = pool_map(
        num_workers, run_one_task,
        [(args.timer, args.also_stderr, args.log, args.write_golden, metadata)
         for metadata in metadata_list])
    create_dir_if_needed(args.log)
    create_dir_if_needed(str(Path(args.log, "tmp")))  # Tests may write stuff.
    master_log_filepath = Path(args.log, LOG_FILE_BASE)
    with open(master_log_filepath, 'w') as f:
        json.dump(result_list, f, indent=2, separators=(",", ": "))  # Sorted.
    error_count, _ = print_summary_report(args, num_tasks, result_list,
                                          master_log_filepath,
                                          time.time() - run_tests_start_time)
    return 0 if error_count == 0 else 1


def find_repeated_test_id(test_ids: Iterator[str]) -> List[str]:
    ids_seen, ids_repeated = set(), []
    for test_id in test_ids:
        if test_id in ids_seen:
            ids_repeated.append(test_id)
        ids_seen.add(test_id)
    return ids_repeated


def make_metadata_list(args: Args) -> List[TaskMetadata]:
    metadata_list = None
    if len(args.paths) > 0:
        missing_executables = [e for e in args.paths if not os.path.isfile(e)]
        if len(missing_executables) > 0:
            err_exit(
                error_s("the following executable(s) "
                        "are not found: %s" % str(missing_executables)))
        metadata_list = [
            get_metadata_from_path(str(i + 1), path)
            for i, path in enumerate(args.paths)
        ]
    elif args.meta != None:
        if not os.path.isfile(args.meta):
            err_exit(error_s("'--meta' file not found: %s" % args.meta))
        with open(args.meta, 'r') as f:
            try:
                metadata_list = json.load(f)
            except ValueError:
                err_exit(error_s("not a valid JSON file: %s" % args.meta))
        error_str = validate_metadata_schema_noexcept(metadata_list)
        if error_str:
            err_exit(
                error_s("metadata format is bad; check out '--docs'\n\t%s" %
                        error_str))
        repeated_ids = find_repeated_test_id(e["id"] for e in metadata_list)
        if len(repeated_ids) > 0:
            err_exit(error_s("test ID repeated: %s" % ", ".join(repeated_ids)))
    else:
        raise RuntimeError("Should not reach here")
    return metadata_list


def process_metadata_list(
    metadata_list: List[TaskMetadata],
    args: Args,
) -> Tuple[List[TaskMetadata], int]:
    # If args.write_golden == True, ignore tests that do not have a golden file
    # path, because there is no need to run these tests.
    ignore_metadata_indexes = []
    if args.write_golden:
        prompt = (
            "About to overwrite golden files of tests with their stdout.\n"
            "Are you sure? [y/N] >> ")
        consent = input(prompt)
        if consent.lower() != "y":
            err_exit("Aborted.")
        ignore_metadata_indexes = [
            i for (i, m) in enumerate(metadata_list) if m["golden"] == None
        ]
        if len(ignore_metadata_indexes) > 0:
            print(
                info_s("%d tests are ignored because they specified "
                       "no golden file to write" %
                       len(ignore_metadata_indexes)))
    # Process the raw metadata list:
    # 1. take care of args.repeat; 2. take care of args.read_flakes
    metadata_list_processed = []
    flaky_tests_decl: Dict[
        str, List[str]] = maybe_parse_flakiness_decls_from_dir(
            Path(args.read_flakes) if args.read_flakes else None)
    unique_count = len(metadata_list)
    for i, metadata in enumerate(metadata_list):
        if i in ignore_metadata_indexes:
            continue
        metadata["hashed_id"] = compute_hashed_id(prog=Path(metadata["path"]),
                                                  id_name=metadata["id"])  # str
        metadata["flaky_errors"] = flaky_tests_decl.get(metadata["id"], [])
        for repeat_cnt in range(args.repeat):
            metadata_copy = copy.deepcopy(metadata)
            metadata_copy["repeat"] = {
                "count": repeat_cnt + 1,
                "all": args.repeat,
            }
            metadata_list_processed.append(metadata_copy)
    return metadata_list_processed, unique_count


def validate_metadata_schema_noexcept(
    metadata_list: List[TaskMetadata]
) -> Optional[str]:  # Error explanation, None if OK.
    try:
        schema.Schema([{  # sync with EXPLANATION_STRING's spec
            "id": str,
            "path": str,
            "args": [str],
            "prefix": [str],
            "golden": schema.Or(str, None),
            "timeout_ms": schema.And(int, lambda v: v > 0),
            "envs": schema.Or({schema.Optional(str): str}, None),
            "exit": {
                "type": schema.Or("return", "timeout", "signal", "quit",
                                  "unknown"),
                "repr": int,
                schema.Optional(str): object,  # Allow more fields, if any.
            },
            schema.Optional(str): object,  # Allow more fields, if any.
        }]).validate(metadata_list)
        return None
    except schema.SchemaError as e:  # Carries explanations.
        return str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Test runner: with timer, logging, diff in HTML",
        epilog="Unless '--docs' is given, exactly one of '--paths' "
        "and '--meta' is needed.\n"
        "Program exits with 0 on success, 1 on test errors, "
        "2 on internal errors.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
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
    parser.add_argument("--also-stderr",
                        action="store_true",
                        help="redirect stderr to stdout")
    parser.add_argument(
        "--read-flakes",
        metavar="DIR",
        type=str,
        default=None,
        help="load flaky tests declaration files *.flaky under DIR")
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
        err_exit(error_s("'--timer' is not given; use '-h' for help"))
    elif not os.path.isfile(args.timer):
        err_exit(error_s("timer program not found: %s" % args.timer))
    args.timer = os.path.relpath(args.timer)

    if ((len(args.paths) == 0 and args.meta == None)
            or (len(args.paths) > 0 and args.meta != None)):
        err_exit(
            error_s("exactly one of '--paths' and '--meta' should be given."))
    if args.repeat != 1 and args.write_golden:
        err_exit(
            error_s("'--repeat' and '--write-golden' cannot be used together."))
    if args.read_flakes and not os.path.isdir(args.read_flakes):
        err_exit(error_s("directory not found: %s" % args.read_flakes))

    metadata_list = make_metadata_list(args)
    if metadata_list == None or len(metadata_list) == 0:
        err_exit(error_s("no test found."))

    metadata_list_processed, unique_test_count = process_metadata_list(
        metadata_list, args)

    return run_all(args, metadata_list_processed, unique_test_count)


if __name__ == "__main__":
    sys.exit(main())
