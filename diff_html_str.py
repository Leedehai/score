#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: diff_html_str.py
# ---------------------------
# Returns a valid HTML string to render a diff view.
#
# Migrated from Python2.7; new features not all applied yet.

import os
import difflib

MISSING_EXPECTED_FILE_FORMAT = "<div style='border:solid red 3px; width:80ch; padding:1ch'>\
<b style='font-size:32px;color:red;text-align:center'>\
!!!!!! Error: DO NOT COMMIT !!!!!!</b><br>\
<span style='font-family:Courier;text-align:center;overflow-wrap:break-word'><b>Expected output file missing:</b><br>{filename}</span><br></div><br>"

# Use "str % (..)" to substitute placeholders, instead of "str.format(..)", because
# escaping '{' and '}' in the HTML format distorts the CSS definition statements.
with open(os.path.join(os.path.dirname(__file__), "diff.html")) as f:
    DIFF_HTML_FORMAT = f.read()

def get_size_str(filename: str) -> str:
    return "%d B" % os.path.getsize(filename)

# return: (golden_file_found, html_string)
def get_diff_html_str(
    html_title: str, desc: str, command: str,
    expected_filename: str, actual_filename: str):
    assert(actual_filename != None and expected_filename != None)
    assert(os.path.isfile(actual_filename))
    found_expected = os.path.isfile(expected_filename)
    expected_lines = list(open(expected_filename, 'r')) if found_expected else []
    actual_lines = list(open(actual_filename, 'r'))
    feed_collection = [
        html_title, desc, command,
        get_size_str(expected_filename) if found_expected else "not found",
        os.path.abspath(expected_filename), expected_filename,
        get_size_str(actual_filename),
        os.path.abspath(actual_filename), actual_filename
    ]
    html_differ = difflib.HtmlDiff(tabsize=4, wrapcolumn=93)
    diff_str_as_html_table = html_differ.make_table(
        expected_lines, actual_lines, context=False, numlines=5)
    if not found_expected:
        # do not raise RuntimeError, because this is user's input error
        return False, DIFF_HTML_FORMAT % tuple(feed_collection + [
             MISSING_EXPECTED_FILE_FORMAT.format(filename=expected_filename)
             + diff_str_as_html_table
        ]) # missing golden file, diff str
    if actual_lines == expected_lines:
        return True, None # has golden file, same content
    return True, DIFF_HTML_FORMAT % tuple(feed_collection + [ diff_str_as_html_table ]) # has golden file, diff str
