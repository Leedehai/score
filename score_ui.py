#!/usr/bin/env python3
# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the MIT LICENSE.txt file.
# -----
# Generate a static site to show the test results, read from the
# result log file.
# This is the second iteration; formerly score_view.py.

import argparse
import datetime
import itertools
import json
import os
import shutil
import statistics
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from pylibs import score_utils

UI_ASSETS_DIR: Path = Path(__file__).parent.joinpath("ui")

# Store data in native JS data structures. Alternatives and reasons of not
# using:
# 1. localStorage/sessionStorage: too restrictive on value types (strings only).
# 2. IndexedDB: we don't want data to be persistent across reloads, as the data
#    may change (if you want to update the DB with the changed data, you
#    need to use open() with a new version number, or you need to remove the
#    existing DB then create a new one with open()); we have no need for offline
#    operations (the site is on local machine anyway). Therefore, the gain does
#    not offset the complexity.
MODEL_JS_TEMPLATE: str = """\
// Generated file. Do not modify manually.
// clang-format off

// Type information are in types.d.ts.

/**
 * @type {{!DataStorage}}
 */
const dataStorage = {{
    testTitle: {test_title},
    masterLog: {master_log},
    testExecPath: {test_exec_path},
    testExecPathComponents: {test_exec_path_components},
    startTime: {start_time_min},
    endTime: {end_time_max},
    wholeTime: {whole_time},
    masterLogModificationTime: {master_log_mtime},
    taskErrorCount: {task_error_count},
    testErrorCount: {test_error_count},

    /**
     * @type {{?Array<string>}}
     */
    additionalInfo: {additional_info},

    /**
     * @type {{!Array<!TaskInfoStringified>}}
     */
    taskResults: {trimmed_task_results},

    /**
     * @type {{!Map<string, !TestAggregateInfo>}}
     */
    testData: new Map({test_task_mapping_list}),
}};
"""


def _produce_model_js(**kwargs) -> str:
    return MODEL_JS_TEMPLATE.format(**dict(
        (k, json.dumps(v, separators=(',', ':'))) for k, v in kwargs.items()))


def _jsify_dict(d: dict, stringify: Optional[bool] = False) -> Union[dict, str]:
    """
    JavaScript-ify Python dicts: use camelCase string keys.
    """
    def _snake2camel(s: str) -> str:
        s_split = s.split("_")
        return "".join([s_split[0]] + [e.capitalize() for e in s_split[1:]])

    d2 = dict(
        (_snake2camel(str(k)), _jsify_dict(v) if isinstance(v, dict) else v)
        for k, v in d.items())
    return d2 if not stringify else json.dumps(
        d2, separators=(',', ':')).replace("\"", "'")


# Getters of task result dicts. Sync with the log schema.
# NOTE If a test is repeated k times, there are k task results in the log.
class TaskResGetter:
    # The getters are incomplete, as some fields are not accessed by this script.
    test_id: Callable[[dict], str] = \
        lambda e: e["id"] # Multiple tasks may share the same test ID.
    ok: Callable[[dict], bool] = \
        lambda e: e["ok"]
    repeat: Callable[[dict], dict] = \
        lambda e: e["repeat"]
    repeat_count: Callable[[dict], int] = \
        lambda e: e["repeat"]["count"]
    timeout: Callable[[dict], float] = \
        lambda e: e["timeout_ms"]
    times: Callable[[dict], dict] = \
        lambda e: e["times_ms"]
    proc_time: Callable[[dict], float] = \
        lambda e: e["times_ms"]["proc"]
    start_time: Callable[[dict], float] = \
        lambda e: e["times_ms"]["abs_start"]
    end_time: Callable[[dict], float] = \
        lambda e: e["times_ms"]["abs_end"]
    maxrss: Callable[[dict], float] = \
        lambda e: e["maxrss_kb"]
    exit: Callable[[dict], dict] = \
        lambda e: e["exit"]
    real_stdout: Callable[[dict], tuple] = \
        lambda e: (e["stdout"]["ok"], e["stdout"]["actual_file"], e["stdout"]["diff_file"])
    golden_file: Callable[[dict], Optional[str]] = \
        lambda e: e["stdout"]["golden_file"]


class TestAggregateInfo:  # pylint: disable=too-many-instance-attributes
    """
    If a test is repeated k times, there will be k task result dicts in the log.
    This class stores data that conceptually belong to the test, not the tasks.
    """

    # yapf: disable
    def __init__(
        self,
        task_indexes: List[int],
        command: str,
        task_error_count: int,
        timeout: float,
        runtime: Tuple[float, float],  # mean, stddev (0 if single data point)
        maxrss: Tuple[float, float],  # mean, stddev (0 if single data point)
        expected_exit: Tuple[str, int], # type, repr
        golden_file: Optional[str],  # None if there's no need to check stdout
    ):
        # Names and types: sync with the JS code.
        self.task_indexes = task_indexes
        self.command = command
        self.task_error_count = task_error_count
        self.timeout = timeout
        self.runtime_stat = runtime # msec, processor time (not wall time)
        self.maxrss_stat = maxrss # KB, max resident set size
        self.golden_file = golden_file
        self.exit = expected_exit
        self.ok = self.task_error_count == 0
    # yapf: enable


BuildAggregateInfoParam = Tuple[Optional[str], str, int, int, List[dict]]


def _build_aggregate_info(inputs: BuildAggregateInfoParam):
    timer_path, test_exec_path, start_index, end_index, task_dicts = inputs
    # Test repeated k times <=> len(task_indexes) == k.
    task_indexes = list(range(start_index, end_index))  # [start, end)
    one_task = task_dicts[-1]  # Really, any valid index is acceptable, e.g. 0.
    command_invocation = score_utils.make_command_invocation_str(
        timer_path,
        one_task,
        indent=2,
        working_directory=str(test_exec_path),
    )
    task_error_count = sum(1 for e in task_dicts
                           if TaskResGetter.ok(e) == False)
    has_single_data_point = len(task_dicts) < 2
    timeout = TaskResGetter.timeout(one_task)
    runtime_average = statistics.mean(
        TaskResGetter.proc_time(e) for e in task_dicts)
    runtime_stddev = 0 if has_single_data_point else statistics.stdev(
        TaskResGetter.proc_time(e) for e in task_dicts)
    maxrss_average = statistics.mean(
        TaskResGetter.maxrss(e) for e in task_dicts)
    maxrss_stddev = 0 if has_single_data_point else statistics.stdev(
        TaskResGetter.maxrss(e) for e in task_dicts)
    expected_exit = TaskResGetter.exit(one_task)["expected"]
    golden_file = TaskResGetter.golden_file(one_task)
    return TestAggregateInfo(
        task_indexes=task_indexes,
        command=command_invocation,
        task_error_count=task_error_count,
        timeout=timeout,
        runtime=(runtime_average, runtime_stddev),
        maxrss=(maxrss_average, maxrss_stddev),
        expected_exit=(expected_exit["type"], expected_exit["repr"]),
        golden_file=golden_file,
    )


def _make_test_task_mapping(
        timer_path: Optional[str], test_exec_path: str,
        sorted_task_results: List[dict]) -> Dict[str, TestAggregateInfo]:
    # We can use groupby() here, because items that evaluate to the same
    # key value are consecutive in the input list.
    result_iter = itertools.groupby(sorted_task_results,
                                    key=TaskResGetter.test_id)
    next_group_start_index = 0
    test_ids: List[str] = []
    map_inputs: List[BuildAggregateInfoParam] = []
    for test_id, group_iter in result_iter:
        task_dicts: List[dict] = list(group_iter)  # Tasks for one test.
        group_start_index = next_group_start_index
        next_group_start_index = group_start_index + len(task_dicts)
        # Build aggregate info that don't depend on other groups.
        test_ids.append(test_id)
        map_inputs.append((
            timer_path,
            test_exec_path,
            group_start_index,
            next_group_start_index,
            task_dicts,
        ))
    # Not using multiprocessing.Pool(), because it causes deadlock in each
    # first-time run after almost every code change (Ubuntu 20.04, Pyhon 3.8.3).
    # It appears Python doesn't work well when the input data has a structure
    # that is relatively complicated.
    aggregate_info_list = [_build_aggregate_info(e) for e in map_inputs]
    assert len(test_ids) == len(aggregate_info_list)
    return dict((test_ids[i], aggregate_info_list[i])
                for i in range(len(aggregate_info_list)))


def _count_errors(
        test_task_mapping: Dict[str, TestAggregateInfo]) -> Tuple[int, int]:
    test_error_count, task_error_count = 0, 0
    for item in test_task_mapping.values():
        test_error_count += 0 if item.ok else 1
        task_error_count += item.task_error_count
    return test_error_count, task_error_count


def _generate_web_view_impl(
    *,
    sorted_task_results: List[dict],
    test_title: str,
    master_log: Path,
    test_exec_path: Path,
    timer_path: Optional[Path],
    additional_info: Optional[List[str]],
    generate_to_dir: Path,
) -> Path:
    # A task corresponds to a dict in sorted_task_results. A test corresponds
    # to k tasks, if the test is repeated k times, and these k dicts are
    # adjacent to each other (because they are sorted by the test description).
    error_task_count: int = 0
    # Earliest start time of all tasks, latest end time of all tasks.
    start_time_min, end_time_max = float("Infinity"), 0.0  # Unix epoch (msec)
    for e in sorted_task_results:  # One pass iteration.
        error_task_count += 0 if TaskResGetter.ok(e) else 1  # 1: False, None
        start_time_min = min(start_time_min, TaskResGetter.start_time(e))
        end_time_max = max(end_time_max, TaskResGetter.end_time(e))
    master_log_mtime: str = datetime.datetime.fromtimestamp(
        master_log.stat().st_mtime).strftime("%a, %b %d, %Y %H:%M:%S")

    # Key: test ID (string), Value: list of indexes into sorted_task_results
    test_task_mapping: Dict[str, TestAggregateInfo] = _make_test_task_mapping(
        str(timer_path) if timer_path else None, str(test_exec_path),
        sorted_task_results)

    test_error_count, task_error_count = _count_errors(test_task_mapping)

    model_js_content: str = _produce_model_js(
        # Originally existing params.
        test_title=test_title,
        master_log=str(master_log),
        additional_info=additional_info,  # None not the same as [] in JS code.
        # Added by this function.
        test_exec_path=str(test_exec_path),
        test_exec_path_components=test_exec_path.parts,
        error_task_count=error_task_count,
        start_time_min=start_time_min,  # Unix epoch (msec)
        end_time_max=end_time_max,  # Unix epoch (msec)
        whole_time=end_time_max - start_time_min,  # Time duration (msec)
        master_log_mtime=master_log_mtime,  # Human-friendly string
        task_count=len(sorted_task_results),
        task_error_count=task_error_count,
        test_count=len(test_task_mapping),
        test_error_count=test_error_count,
        trimmed_task_results=[
            _jsify_dict(
                {
                    # Use camelCase keys, as they are to be present in the JS file.
                    # Names and types: sync with the JS code.
                    "ok": TaskResGetter.ok(e),  # boolean
                    "timesMs": (TaskResGetter.times(e)["proc"],
                                TaskResGetter.times(e)["abs_start"],
                                TaskResGetter.times(e)["abs_end"]),  # tuple
                    "maxrssKb": TaskResGetter.maxrss(e),  # float
                    "exit": (TaskResGetter.exit(e)["ok"],
                             TaskResGetter.exit(e)["real"]["type"],
                             TaskResGetter.exit(e)["real"]["repr"]),  # tuple
                    "stdout": TaskResGetter.real_stdout(e),  # tuple
                },
                stringify=True) for e in sorted_task_results
        ],
        test_task_mapping_list=[
            (str(k), _jsify_dict(vars(v)))  # Sent to JS Map() constructor.
            for k, v in test_task_mapping.items()
        ])
    with open(generate_to_dir.joinpath("model.js"), 'w') as f:
        f.write(model_js_content)
    # The entry point. Point browser to this file to view the site. No server
    # is required.
    index_html_path: Path = generate_to_dir.joinpath("index.html")
    shutil.copyfile(
        src=UI_ASSETS_DIR.joinpath("index.html"),
        dst=index_html_path,
    )
    # Not used by browser, but useful for debugging.
    shutil.copyfile(
        src=UI_ASSETS_DIR.joinpath("types.d.ts"),
        dst=generate_to_dir.joinpath("types.d.ts"),
    )
    # Not used by browser, but useful if the generated dir is copied elsewhere.
    shutil.copyfile(
        src=UI_ASSETS_DIR.joinpath("README.md"),
        dst=generate_to_dir.joinpath("README.md"),
    )
    shutil.copytree(src=UI_ASSETS_DIR.joinpath("static"),
                    dst=generate_to_dir.joinpath("static"))
    return index_html_path


# export
def generate_web_view(
    *,
    test_title: str,
    master_log: Path,
    test_exec_path: Path,
    timer_path: Optional[Path],
    additional_info: Optional[List[str]],
    generate_to_dir: Path,
) -> Path:
    """
    Params:

    * num_jobs: Number of parallel workers to generate view.
    * test_title: The title you want to display on the page's tab and head.
    * master_log: Path to the JSON log produced by the test runner.
    * test_exec_path: The working directory at which all test commands were run.
    * timer_path: Path to the timer program used by the test runner, if one is
      used.
    * additional_info: Information you want to display additionally (list of
      lines). If None, the info area isn't shown (different from an empty list).
    * generate_to_dir: Where to write the files produced by this generator.

    Returns:

    The path to the index.html file. Point the browser to this URL to view it.
    """
    if generate_to_dir.exists():
        # Remove the existing directory entirely, so that files from a previous
        # run won't affect the UI.
        shutil.rmtree(generate_to_dir)
    os.makedirs(generate_to_dir)
    with open(master_log, 'r') as f:
        try:
            task_result_list: List[dict] = json.load(f)
            if not isinstance(task_result_list, list):
                raise TypeError("log data ought to be a list, but found %s" %
                                type(task_result_list).__name__)
            # In the log, the "id" key is shared by repeated tasks that
            # correspond to the same test. Sorting ensures:
            # 1. Tasks are sorted in ascending order alphabetically according
            #    to the "id" key.
            # 2. Tasks that correspond to the same test are put together, in
            #    ascending order according to the repeat count 1...k.
            compute_sort_key = lambda e: (TaskResGetter.test_id(e),
                                          TaskResGetter.repeat_count(e))
            sorted_task_results = sorted(task_result_list, key=compute_sort_key)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            sys.exit(
                score_utils.error_s("currupted log file %s: %s" %
                                    (master_log, e)))
    return _generate_web_view_impl(
        sorted_task_results=sorted_task_results,
        test_title=test_title,
        master_log=master_log,
        test_exec_path=test_exec_path,
        timer_path=timer_path,
        additional_info=additional_info,
        generate_to_dir=generate_to_dir,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Static site generator for test results",
        epilog="For requirements of the timer and log file: see score_run.py --docs"
    )
    parser.add_argument("--title",
                        type=str,
                        default="Tests",
                        help="title of tests, default: 'Tests'")
    parser.add_argument("--log",
                        metavar="LOG",
                        type=str,
                        required=True,
                        help="path to the master log, written by score_run.py")
    parser.add_argument("--timer",
                        metavar="PROG",
                        type=str,
                        default=None,
                        help="path to the timer program used to run the tests")
    parser.add_argument("--test-exec-path",
                        metavar="PATH",
                        type=str,
                        default=Path.cwd(),
                        help="working directory the tests ran at")
    parser.add_argument("--to-dir",
                        metavar="NEW_PATH",
                        type=str,
                        default="html",
                        help="directory to write results (if the directory "
                        "already exits, it will be replaced), default: ./html")
    args = parser.parse_args()
    if not Path(args.log).is_file():
        sys.exit(score_utils.error_s("file not found: %s" % args.log))
    test_exec_path = score_utils.maybe_start_with_home_prefix(
        Path(args.test_exec_path))
    html_file_path: Path = generate_web_view(
        test_title=args.title,
        master_log=Path(args.log),
        test_exec_path=test_exec_path,
        timer_path=Path(args.timer) if args.timer else None,
        additional_info=None,
        generate_to_dir=Path(args.to_dir),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
