#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: diff_html_str.py
# ---------------------------
# Returns a valid HTML string to render a diff view.

import os
import difflib
from pathlib import Path
from typing import Dict, Optional, Tuple

from pylibs.score_utils import maybe_start_with_home_prefix

_MISSING_EXPECTED_FILE_HTML_FORMAT = """
<div style='width:80ch; padding:1ch'>
    <b style='font-family:Courier;font-size:24px;color:red;text-align:center'>
        Error: do not commit.
    </b><br>
    <span style='font-family:Courier;text-align:center;overflow-wrap:break-word'>
        &nbsp;&nbsp;Expected output file missing:<br>
        &nbsp;&nbsp;{filename}
    </span>
</div>"""

with open(Path(__file__).parent.joinpath("diff_head.html"), 'r') as diff_head_f:
    _DIFF_HEAD = diff_head_f.read()

_DIFF_HTML_FORMAT = """
<html>
<head>
    <title>{title}</title>
    {diff_head}
</head>
<body>
    {error_box}
    <div class="info_div">
        <span class="info_key">description</span><br>
        <span class="info_value">
            &nbsp;&nbsp;{description}
        </span>
    </div>
    <div class="info_div">
        <span class="info_key">expected stdout ({expected_filesize})</span><br> <!-- size string or "not found" -->
        <span class="info_value">
            &nbsp;&nbsp;{expected_filepath}
            (<a href='{expected_filepath}' target="_blank">link</a>)
        </span>
    </div>
    <div class="info_div">
        <span class="info_key">actual stdout ({actual_filesize})</span><br> <!-- size string -->
        <span class="info_value">
            &nbsp;&nbsp;{actual_filepath}
            (<a href='{actual_filepath}' target="_blank">link</a>)
        </span>
    </div>
    <!-- table placeholder -->
    {diff_table}
</body>
</html>
"""


def _get_size_str(filename: str) -> str:
    return "%d B" % os.path.getsize(filename)


def _replace_outdated_html_bits(html_str: str) -> str:
    return html_str \
        .replace("cellspacing=\"0\" cellpadding=\"0\" rules=\"groups\"", "") \
        .replace("<colgroup></colgroup>", "") \
        .replace("nowrap=\"nowrap\"", "class=\"data\"")


# return: (golden_file_found, html_string)
def get_diff_html_str(
    html_title: str,
    desc: str,
    expected_filename: str,
    actual_filename: str,
) -> Tuple[bool, Optional[str]]:
    assert actual_filename != None and expected_filename != None
    assert os.path.isfile(actual_filename)
    found_expected = os.path.isfile(expected_filename)
    if found_expected:
        with open(expected_filename, 'r') as f:
            expected_lines = list(f)
    else:
        expected_lines = []
    with open(actual_filename, 'r') as f:
        actual_lines = list(f)
    if actual_lines == expected_lines:
        return True, None  # has golden file, same content
    diff_table_str = _replace_outdated_html_bits(
        difflib.HtmlDiff(tabsize=4).make_table(expected_lines,
                                               actual_lines,
                                               fromdesc='expected',
                                               todesc='actual',
                                               context=False,
                                               numlines=5))
    slot_contents: Dict[str, str] = {
        "title": html_title,
        "diff_head": _DIFF_HEAD,
        "description": desc,
        "expected_filepath": maybe_start_with_home_prefix(
            Path(expected_filename).absolute()),
        "expected_filesize": _get_size_str(expected_filename)
        if found_expected else "not found",
        "actual_filepath": maybe_start_with_home_prefix(
            Path(actual_filename).absolute()),
        "actual_filesize": _get_size_str(actual_filename),
        "error_box": "",
        "diff_table": diff_table_str,
    }
    if not found_expected:
        slot_contents["error_box"] = _MISSING_EXPECTED_FILE_HTML_FORMAT.format(
            filename=expected_filename)
        return False, _DIFF_HTML_FORMAT.format(**slot_contents)
    return True, _DIFF_HTML_FORMAT.format(**slot_contents)
