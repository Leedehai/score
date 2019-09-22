#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: diffhtmlstr.py
# ---------------------------
# Returns a valid HTML string to render a diff view.

import os
import difflib

MISSING_EXPECTED_FILE_FORMAT = "<div style='text-align:center'><b style='font-size:32px;color:red'>\
!!!!!! Error: DO NOT COMMIT !!!!!!</b><br>\
<span style='font-family:Courier'>Golden file missing: %s</span><br><br></div>"

# Use "str % (..)" to substitute placeholders, instead of "str.format(..)", because
# escaping '{' and '}' in the HTML format distorts the CSS definitions.
with open(os.path.join(os.path.dirname(__file__), "diff.html")) as f:
    DIFF_HTML_FORMAT = f.read()

def get_size_str(filename):
    return "%d B" % os.path.getsize(filename)

# return: (golden_file_found, html_string)
def get_diff_html_str(html_title, desc, command, expected_filename, actual_filename):
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
             MISSING_EXPECTED_FILE_FORMAT % expected_filename
             + diff_str_as_html_table
        ]) # missing golden file, diff str
    if actual_lines == expected_lines:
        return True, None # has golden file, same content
    return True, DIFF_HTML_FORMAT % tuple(feed_collection + [ diff_str_as_html_table ]) # has golden file, diff str
