#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: view.py
# ---------------------------
# View the tests from browser.

import os, sys
import argparse
import json
import webbrowser

# avoid *.pyc of imported modules
sys.dont_write_bytecode = True

def run(args):
	# TODO
    webbrowser.open("file://" + os.path.abspath(os.path.join(os.path.dirname(__file__), "diff.html")))

def main():
    parser = argparse.ArgumentParser(description="View test logs in browser")
    parser.add_argument("logdirs", metavar="DIR", nargs='+',
                        help="paths to the logs directory")
    parser.add_argument("--root", metavar="PREFIX", default=".",
                        help="root prefix of the paths used in logs, default: .")
    args = parser.parse_args()

    missing_dirs = [ e for e in args.logdirs if not os.path.isdir(e) ]
    if len(missing_dirs):
        print("[Error] directory not found:\n\t" + "\n\t".join(missing_dirs))
        sys.exit(1)
    if not os.path.isdir(args.root):
        sys.exit("[Error] root prefix not a valid directory: %s" % args.root)
    print(args)
    return run(args)

if __name__ == "__main__":
    sys.exit(main())
