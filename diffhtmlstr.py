#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: diffhtmlstr.py
# ---------------------------
# Returns a valid HTML string to render a diff view.

import os
import difflib

with open(os.path.join(os.path.dirname(__file__), "diff.html")) as f:
    DIFF_HTML_FORMAT = f.read()

# return: (golden_file_found, html_string)
def get_diff_html_str(html_title, desc, command, expected_filename, actual_filename):
    assert(actual_filename != None and expected_filename != None)
    feed_collection = [
        html_title, desc, command,
        os.path.abspath(expected_filename), expected_filename,
        os.path.abspath(actual_filename), actual_filename
    ]
    if not os.path.isfile(expected_filename):
        # do not raise RuntimeError, because this is user's input error
        return False, DIFF_HTML_FORMAT % tuple(feed_collection + [
            "<b>!!!!!! Error: DO NOT COMMIT !!!!!!</b><br>Golden file missing: %s" % expected_filename
        ])
    expected_lines, actual_lines = list(open(expected_filename, 'r')), list(open(actual_filename, 'r'))
    if actual_lines == expected_lines:
        return True, None # has golden file, same content
    html_differ = difflib.HtmlDiff(tabsize=4, wrapcolumn=93)
    diff_str_as_html_table = html_differ.make_table(
        expected_lines, actual_lines, context=False, numlines=5)
    return True, DIFF_HTML_FORMAT % tuple(feed_collection + [ diff_str_as_html_table ]) # has golden file, diff str
