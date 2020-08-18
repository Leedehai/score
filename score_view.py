#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: score_view.py
# ---------------------------
# Generate a static site on test results.
# We did not use HTML template engine like Jinja2 here, for
# no obvious reasons. I know how to use it, though.

import os, sys
import argparse
import datetime
import itertools
import json
import re
import shutil
import statistics
from pathlib import Path
from typing import List, Optional

from pylibs import score_utils

THIS_DIR = os.path.dirname(__file__)
TEMPLATES_BASENAME = "templates"
OUT_HTML_BASENAME = "view_log.html"
with open(os.path.join(THIS_DIR, TEMPLATES_BASENAME, "main.html"), 'r') as f:
    MAIN_HTML_TEMPLATE = f.read()  # str
with open(os.path.join(THIS_DIR, TEMPLATES_BASENAME, "entry_piece.html"),
          'r') as f:
    ENTRY_PIECE_TEMPLATE = f.read()  # str


class TableRowBuilder:
    def __init__(self, row_type: str):
        self.type = row_type  # "th" or "td"
        self.parts = ["<tr>"]

    def done(self) -> str:
        self.parts.append("</tr>")
        return "".join(self.parts)

    def add_data_cell(self, any_data, class_names="", tooltip=None):
        class_names = ("tooltip_owner " if tooltip else "") + class_names
        cell_inner_html = str(any_data)
        if tooltip:
            cell_inner_html += (" <span class=\"tooltip_text\">%s</span>" %
                                tooltip)
        self.parts.append("<{0}{2}>{1}</{0}>".format(
            self.type, cell_inner_html,
            (" class=\"%s\"" % class_names) if class_names else ""))
        return self

    def add_href_cell(self, url: str, text: str, comment: str, class_names=""):
        self.parts.append(
            "<{0}>"
            "<a href=\"{1}\" target=\"_blank\" {4}>{2}</a>"
            "&nbsp;<span class=\"comment\">({3})</span></{0}>".format(
                self.type, url, text, comment,
                (" class=\"%s\"" % class_names) if class_names else ""))
        return self


def _searialize_exit_object(exit_obj: dict) -> str:
    if exit_obj["type"] not in ["return", "signal"]:
        return exit_obj["type"]
    return "{exit_type} {exit_repr}".format(exit_type=exit_obj["type"],
                                            exit_repr=exit_obj["repr"])


def _result_cell_ternary(result: dict, on_success: str, on_error: str,
                         on_error_but_flaky: str) -> str:
    if result["ok"]:
        return on_success
    if result["error_is_flaky"]:
        return on_error_but_flaky
    return on_error


def _human_friendly_time_elapse(sec: int):
    h = int(sec / 3600)
    m = int((sec % 3600) / 60)
    s = (sec % 3600) % 60
    if h == 0:
        return "{} min, {} sec".format(m, s)
    return "{} hr {} min, {} sec".format(h, m, s)


MIN_PATH_LEN = 3


def _timeline_svg_html(result: dict, length: float, start_time_min: float,
                       whole_time: float) -> str:
    assert (length >= 20 and whole_time > 0)
    x_coords = [0]
    time_to_start = result["times_ms"]["abs_start"] - start_time_min
    start_x = time_to_start * 1.0 / whole_time * length
    start_x = min(start_x, length - MIN_PATH_LEN)
    x_coords.append(start_x)
    time_to_finish = result["times_ms"]["abs_end"] - start_time_min
    finish_x = time_to_finish * 1.0 / whole_time * length
    finish_x = finish_x if (finish_x - start_x >= MIN_PATH_LEN) else (
        start_x + MIN_PATH_LEN)
    x_coords.append(finish_x)
    x_coords.append(length)
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='{length}' height='20'>"
        "<path d='M{x0:.1f} 10 L{x1:.1f} 10' stroke='#cccccc' stroke-width='2'></path>"
        "<path d='M{x1:.1f} 10 L{x2:.1f} 10' stroke='#336bec' stroke-width='2'></path>"
        "<path d='M{x2:.1f} 10 L{x3:.1f} 10' stroke='#cccccc' stroke-width='2'></path>"
        "</path></svg>").format(
            length=length,
            x0=x_coords[0],
            x1=x_coords[1],
            x2=x_coords[2],
            x3=x_coords[3],
        )


def _disabled_case_html(disabled_cases: List[dict]):
    return "<pre class='disabled_case_html'>{disabled_case_list}</pre>".format(
        disabled_case_list='\n'.join(e["desc"] for e in disabled_cases))


def _populate_test_results_table(results: List[dict], start_time_min: float,
                                 whole_time: float, html_dir: Path,
                                 has_golden_file: bool) -> str:
    """
    Generate an HTML table for all results for one test.
    results: task results for this one test, length == the test's repeat times.
    start_time_min: min start time (msec since Epoch) of all tasks in log.
    end_time_max: max end time (msec since Epoch) of all tasks in log.
    """
    row_list = []  # list of str
    row_list.append(
        TableRowBuilder("th").add_data_cell("#").add_data_cell("result") \
            .add_data_cell("runtime", tooltip="time on processor") \
            .add_data_cell("max. rss.", tooltip="maximum resident set size") \
            .add_data_cell("exit", tooltip="how program exited") \
            .add_data_cell("exit ok").add_data_cell("stdout") \
            .add_data_cell("stdout diff") \
            .add_data_cell("stdout ok") \
            .add_data_cell("timeline", tooltip="start/end time vs all tests") \
            .done())
    file_size_str = lambda size: "0" if size == 0 else ("%.2f" % size)
    for result in results:
        half_baked_row = (
            TableRowBuilder("td").add_data_cell(
                result["repeat"]["count"]).add_data_cell(
                    _result_cell_ternary(result, "good", "bad",
                                         "bad, flaky"),  # content
                    class_names=_result_cell_ternary(result, "success", "error",
                                                     "error_but_flaky"),
                )  # result
            .add_data_cell("%d ms" % result["times_ms"]["proc"],
                           )  # runtime (processor time)
            .add_data_cell("%.1f MB" % (result["maxrss_kb"] / 1024.0),
                           )  # max. rss.
            .add_data_cell(_searialize_exit_object(
                result["exit"]["real"]))  # exit
            .add_data_cell(str(result["exit"]["ok"]).lower())  # exit ok
            .add_href_cell(  # stdout
                os.path.relpath(result["stdout"]["actual_file"], str(html_dir)),
                text="stdout",
                comment="%s KB" % file_size_str(
                    os.path.getsize(result["stdout"]["actual_file"]) / 1024.0),
                class_names="link_stdout"))
        if result["stdout"]["ok"]:
            half_baked_row = half_baked_row.add_data_cell("-")  # stdout diff
        else:
            half_baked_row = half_baked_row.add_href_cell(  # stdout diff
                os.path.relpath(result["stdout"]["diff_file"], str(html_dir)),
                text="diff",
                comment="%s KB" % file_size_str(
                    os.path.getsize(result["stdout"]["diff_file"]) / 1024.0))
        row_list.append(
            half_baked_row.add_data_cell(
                str(result["stdout"]["ok"]).lower()
                if has_golden_file else "-")  # stdout ok
            .add_data_cell(
                _timeline_svg_html(result, 160, start_time_min,
                                   whole_time))  # timeline
            .done())
    return "\n".join(row_list)


def _populate_entries_view(*,
                           sorted_test_results: List[dict],
                           timer_program: str,
                           start_time_min: float,
                           whole_time: float,
                           html_dir: Path,
                           working_directory: Optional[str] = None) -> str:
    """
    Generate HTML pice for each entry. Each entry is a test, potentially
    containing more than one run attempts.
    """
    entries_view_html_list = []  # list of str
    # Each test could have multiple attempts (tasks). We identify tasks for the
    # same test based on keys "comb_id" and "desc" ("desc" key alone is also good,
    # but it's error-prone as description are written by human whereas "comb_id"
    # is guaranteed to be unique among different tests).
    # Can use itertools.groupby() because the list is sorted.
    result_iter = itertools.groupby(sorted_test_results,
                                    lambda e: e["comb_id"] + e["desc"])
    for _, g in result_iter:
        results_for_one_test = sorted(list(g),
                                      key=lambda e: e["repeat"]["count"])
        command_invocation = score_utils.make_command_invocation_str(
            timer_path=timer_program,
            params=results_for_one_test[0],
            indent=2,
            working_directory=working_directory,
        )
        known_flaky_errors = "false"
        flaky_errors = results_for_one_test[0]["flaky_errors"]
        if len(flaky_errors) > 0:
            known_flaky_errors = ", ".join(flaky_errors)
        only_one_data_point = len(results_for_one_test) < 2
        runtime_ms_average = statistics.mean(e["times_ms"]["proc"]
                                             for e in results_for_one_test)
        runtime_ms_stddev = 0 if only_one_data_point else statistics.stdev(
            e["times_ms"]["proc"] for e in results_for_one_test)
        maxrss_kb_average = statistics.mean(e["maxrss_kb"]
                                            for e in results_for_one_test)
        maxrss_kb_stddev = 0 if only_one_data_point else statistics.stdev(
            e["maxrss_kb"] for e in results_for_one_test)
        golden_file_or_none = results_for_one_test[0]["stdout"]["golden_file"]
        results_table_html = _populate_test_results_table(
            results_for_one_test,
            start_time_min,
            whole_time,
            html_dir,
            has_golden_file=golden_file_or_none != None)
        test_entry_html = ENTRY_PIECE_TEMPLATE.format(
            test_description_with_ellipse_if_necessary=score_utils.ellipse_str(
                50, results_for_one_test[0]["desc"]),
            test_description=results_for_one_test[0]["desc"],
            command_invocation=command_invocation,
            expected_exit=_searialize_exit_object(
                results_for_one_test[0]["exit"]["expected"]),
            expected_stdout=golden_file_or_none,
            timeout_ms="%s ms" % (results_for_one_test[0]["timeout_ms"]),
            known_flaky=known_flaky_errors,
            attempt_count=len(results_for_one_test),
            success_count=sum(1 for e in results_for_one_test if e["ok"]),
            flaky_error_count=sum(1 for e in results_for_one_test
                                  if e["error_is_flaky"]),
            average_runtime="%.1f ± %.1f" %
            (runtime_ms_average, runtime_ms_stddev),
            average_maxrss_mb="%.1f ± %.1f" %
            (maxrss_kb_average / 1024.0, maxrss_kb_stddev / 1024.0),
            attempts_report_table=results_table_html,
        )
        entries_view_html_list.append(test_entry_html)
    return "\n".join(entries_view_html_list)


def _populate_html_template(*,
                            html_dir: Path,
                            test_dir: Path,
                            test_title: str,
                            master_log_path: Path,
                            error_task_count: int,
                            sorted_test_results: List[dict],
                            timer_program: str,
                            start_time_min: float,
                            whole_time: float,
                            disabled_cases: List[dict],
                            working_directory: Optional[str] = None) -> str:
    """Populate the HTML templates, starting from the main template"""
    main_html = MAIN_HTML_TEMPLATE.format(
        test_title=test_title,
        abs_test_directory=os.path.normpath(str(test_dir.absolute())),
        master_log=master_log_path.absolute(),
        master_log_mtime=datetime.datetime.fromtimestamp(
            master_log_path.stat().st_mtime).strftime("%a, %b %d, %Y %H:%M:%S"),
        whole_time_str=_human_friendly_time_elapse(sec=1 +
                                                   int(whole_time / 1000)),
        error_task_count=error_task_count,
        entries_view_html=_populate_entries_view(
            sorted_test_results=sorted_test_results,
            timer_program=timer_program,
            start_time_min=start_time_min,
            whole_time=whole_time,
            html_dir=html_dir,
            working_directory=working_directory,
        ),
        message_disabled_case_count="Disabled tests: %d" % len(disabled_cases),
        disabled_case_html=_disabled_case_html(disabled_cases=sorted(
            disabled_cases, key=lambda e: e["desc"]), ),
    )
    return main_html


def _generate_web_view_impl(*,
                            test_title: str,
                            sorted_test_results: List[dict],
                            disabled_cases: List[dict],
                            master_log_path: Path,
                            timer_program: str,
                            test_dir: Path,
                            html_dir: Path,
                            working_directory: Optional[str] = None) -> None:
    error_task_count, start_time_min, end_time_max = 0, float("Infinity"), 0
    for e in sorted_test_results:  # one pass iteration
        if e["ok"] == False:
            error_task_count += 1
        if e["times_ms"]["abs_start"] < start_time_min:
            start_time_min = e["times_ms"]["abs_start"]
        if e["times_ms"]["abs_end"] > end_time_max:
            end_time_max = e["times_ms"]["abs_end"]
    shutil.copyfile(
        src=os.path.join(THIS_DIR, TEMPLATES_BASENAME, "README"),
        dst=str(html_dir.joinpath("README")),
    )
    shutil.copytree(src=os.path.join(THIS_DIR, "static"),
                    dst=str(html_dir.joinpath("static")))
    html_str = _populate_html_template(
        html_dir=html_dir,
        test_dir=test_dir,
        test_title=test_title,
        master_log_path=master_log_path,
        error_task_count=error_task_count,
        sorted_test_results=sorted_test_results,
        timer_program=timer_program,
        start_time_min=start_time_min,
        whole_time=end_time_max - start_time_min,
        disabled_cases=disabled_cases,
        working_directory=working_directory,
    )
    with Path(html_dir, OUT_HTML_BASENAME).open('w') as f:
        f.write(minimize_html(html_str))


def minimize_html(s):
    # replace repeated blanks (not '\n', in case a "//" invalidates the next line)
    return re.sub(r" {2,}", " ",
                  s)  # Back-burner: JS, comments in HTML/JS, etc.


# export
def generate_web_view(*,
                      test_title: str,
                      test_master_log: str,
                      disabled_cases: List[dict],
                      timer_program: str,
                      to_dir: str,
                      working_directory: Optional[str] = None) -> str:
    test_dir = Path(test_master_log).parent.parent
    html_dir = Path(to_dir)
    if html_dir.is_dir():
        shutil.rmtree(str(html_dir))
    os.makedirs(str(html_dir))
    html_file_path = Path(html_dir, OUT_HTML_BASENAME)
    with open(test_master_log, 'r') as f:
        # Sort according to test desc:
        # 1) itertools.groupby() needs sorted list
        # 2) good looking in final view
        sorted_test_results = sorted(json.load(f), key=lambda e: e["desc"])
    _generate_web_view_impl(
        test_title=test_title,
        sorted_test_results=sorted_test_results,
        disabled_cases=disabled_cases,
        master_log_path=Path(test_master_log),
        timer_program=timer_program,
        test_dir=test_dir,
        html_dir=html_dir,
        working_directory=working_directory,
    )
    return str(html_file_path)


def main():
    parser = argparse.ArgumentParser(
        description="Static site generator for test results",
        epilog="For requirements of the timer and log file: see score_run.py --docs"
    )
    parser.add_argument("--title",
                        type=str,
                        default="Tests",
                        help="title of tests, default: 'Tests'")
    parser.add_argument("--timer",
                        metavar="PROG",
                        type=str,
                        required=True,
                        help="path to the timer program used to run the tests")
    parser.add_argument("--log",
                        metavar="LOG",
                        type=str,
                        required=True,
                        help="path to the master log, written by score_run.py")
    parser.add_argument(
        "--to-dir",
        metavar="NEW_PATH",
        type=str,
        default="html",
        help="directory to write results (if the directory already "
        "exits, it will be replaced), default: ./html")
    args = parser.parse_args()
    if not os.path.isfile(args.log):
        sys.exit("[Error] file not found: %s" % args.log)
    html_file_path = generate_web_view(
        test_title=args.title,
        test_master_log=args.log,
        disabled_cases=[],
        timer_program=args.timer,
        to_dir=args.to_dir,
    )
    print("Written: %s" % html_file_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
