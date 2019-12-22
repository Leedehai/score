#!/usr/bin/env python3
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: view.py
# ---------------------------
# View the tests from browser.
# For more information, see README.md.
# For help: use '--help'.
#
# Migrated from Python2.7; new features not all applied yet.

import os, sys
import argparse
import json
import shutil
import webbrowser

# avoid *.pyc of imported modules
sys.dont_write_bytecode = True

LOG_FILE_BASE      = "run_log.json"
WEBSITE_DIR_BASE   = "web"
WEBSITE_INDEX_HTML = "index.html"

def apply_root_to_stdout(root, stdout_dict):
    if stdout_dict["actual_file"] != None:
        stdout_dict["actual_file"] = os.path.normpath(
            os.path.join(root, stdout_dict["actual_file"]))
    if stdout_dict["golden_file"] != None:
        stdout_dict["golden_file"] = os.path.normpath(
            os.path.join(root, stdout_dict["golden_file"]))
    if stdout_dict["diff_file"] != None:
        stdout_dict["diff_file"] = os.path.normpath(
            os.path.join(root, stdout_dict["diff_file"]))

def generate_website(args, logdata_list):
    for logdata in logdata_list:
        apply_root_to_stdout(args.root, logdata["stdout"])
    web_dir = os.path.join(args.logdir, WEBSITE_DIR_BASE)
    shutil.rmtree(web_dir, ignore_errors=True) # path could be non-existent
    os.makedirs(web_dir)
	# TODO
    if not args.no_browser:
        webbrowser.open("file://" + os.path.abspath(
            os.path.join(web_dir, WEBSITE_INDEX_HTML)))

def main():
    parser = argparse.ArgumentParser(description="View tests in browser",
                                     epilog="Generated website is written to DIR/web")
    parser.add_argument("logdir", metavar="DIR",
                        help="paths to the log directory, which has %s" % LOG_FILE_BASE)
    parser.add_argument("-d", "--desc", metavar="DESC", default="unnamed tests",
                        help="description of tests, default: 'unnamed tests'")
    parser.add_argument("-r", "--root", metavar="PATH", default=".",
                        help="root prefix of paths used in logs, default: .")
    parser.add_argument("-n", "--no-browser", action="store_true",
                         help="do not open browser when generation is done")
    args = parser.parse_args()

    if not os.path.isdir(args.logdir):
        sys.exit("[Error] directory not found: %s" % args.logdir)
    master_log = os.path.join(args.logdir, LOG_FILE_BASE)
    if not os.path.isfile(master_log):
        sys.exit("[Error] log not found in the specified log directory: %s" % master_log)
    if not os.path.isdir(args.root):
        sys.exit("[Error] root prefix not a valid directory: %s" % args.root)

    with open(master_log, 'r') as f:
        try:
            logdata_list = json.load(f)
        except ValueError:
            sys.exit("[Error] not a valid JSON file: %s" % args.meta)

    return generate_website(args, logdata_list)

if __name__ == "__main__":
    sys.exit(main())
