#!/usr/bin/env python
# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: mock-timer.py
# ---------------------------
# Mocks the timer program's basic functionality.
# NOTE the real timer should be written in a compiled language for speed.

import os, sys

try:
    delimiter = os.environ["CTIMER_DELIMITER"]
except KeyError:
    delimiter = ""

INSPECTEE_STDOUT_RAW = """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut
labore et dolore magna aliqua. Dolor sed viverra ipsum nunc aliquet bibendum enim. In massa tempor nec feugiat. Nunc
aliquet bibendum enim facilisis gravida. Nisl nunc mi ipsum faucibus vitae aliquet nec ullamcorper. Amet luctus
venenatis lectus magna fringilla. Volutpat maecenas volutpat blandit aliquam etiam erat velit scelerisque in. Egestas
egestas fringilla phasellus faucibus scelerisque eleifend. Sagittis orci a scelerisque purus semper eget duis. Nulla
pharetra diam sit amet nisl suscipit. Sed adipiscing diam donec adipiscing tristique risus nec feugiat in. Fusce ut
placerat orci nulla. Pharetra vel turpis nunc eget lorem dolor. Tristique senectus et netus et malesuada.

Etiam tempor orci eu lobortis elementum nibh tellus molestie. Neque egestas congue quisque egestas. Egestas integer
eget aliquet nibh praesent tristique. Vulputate mi sit amet mauris. Sodales neque sodales ut etiam sit. Dignissim
suspendisse in est ante in. Volutpat commodo sed egestas egestas. Felis donec et odio pellentesque diam. Pharetra
vel turpis nunc eget lorem dolor sed viverra. Porta nibh venenatis cras sed felis eget. Aliquam ultrices sagittis
orci a. Dignissim diam quis enim lobortis. Aliquet porttitor lacus luctus accumsan. Dignissim convallis aenean et
tortor at risus viverra adipiscing at."""

INSPECTEE_STDOUT_RAW_TWEAKED = INSPECTEE_STDOUT_RAW\
.replace("malesuada.\n", "\nPrivacy is paramount to us, in everything we do. So today, we are announcing a new initiative to develop a set of open standards to fundamentally enhance privacy on the web. We're calling this a Privacy Sandbox.\n")

STATS_JSON = """{
    "pid" : 35871,
    "exit" : {
        "type" : "%s",
        "repr" : %d,
        "desc" : "exit code"
    },
    "times_ms" : {
        "total" : %f
    }
}"""

env_var = os.environ.get("ENV_VAR", None)
assert(env_var and env_var == "1")

args = sys.argv[1:]
assert(len(args) >= 1)
if args[0] == "timeout.exe":
    if len(args) == 2 and args[1] == "--print":
        print(INSPECTEE_STDOUT_RAW)
    if len(args) == 2 and args[1] == "--tweak-stdout":
        print(INSPECTEE_STDOUT_RAW_TWEAKED)
    stats = STATS_JSON % ("timeout", 1500, 1500.02)
    print(delimiter + stats + delimiter)
else:
    if len(args) == 2 and args[1] == "--print":
        print(INSPECTEE_STDOUT_RAW)
    if len(args) == 2 and args[1] == "--tweak-stdout":
        print(INSPECTEE_STDOUT_RAW_TWEAKED)
    stats = STATS_JSON % ("return", 0, 1.01)
    print(delimiter + stats + delimiter)
