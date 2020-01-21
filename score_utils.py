# Copyright: see README and LICENSE under the project root directory.
# Author: @Leedehai
#
# File: score_utils.py
# ---------------------------
# Utilities.

import os, sys
import platform
import textwrap
from typing import Optional

INFINITE_TIME = 0 # it means effectively infinite time required by timer
def get_timeout(timeout: int) -> str:
    return str(timeout if timeout != None else INFINITE_TIME)

CTIMER_TIMEOUT_ENVKEY = "CTIMER_TIMEOUT"
def make_command_invocation_str(
    timer_path: str, params: dict, indent: int = 0,
    working_directory: Optional[str] = None) -> str:
    """
    params is a dict containing the following key-value pairs:
    "envs" (dict), "timeout_ms" (int or None), "path" (str), "args" (str[])
    """
    indents = ' ' * indent # str
    strs = []
    # Environment variables.
    if params["envs"] != None:
        strs += [
            "{0}{1}={2}".format(indents, k, v)
            for k, v in params["envs"].items()
        ]
    # Timer
    strs.append("{0}{1}={2} {3}".format(
        indents, CTIMER_TIMEOUT_ENVKEY,
        get_timeout(params["timeout_ms"]), timer_path
    ))
    # Driver and arguments.
    strs += textwrap.wrap(
        text = "%s %s" % (params["path"], ' '.join(params["args"])),
        width = 70,
        initial_indent = indents * 2,
        subsequent_indent = indents * 3,
        break_long_words = False, break_on_hyphens = False,
    )
    invocation = " \\\n".join(strs)
    # Add working directory comment, if specified.
    if working_directory:
        invocation = (indents + "# cwd: %s\n" % working_directory) + invocation
    return invocation

def guess_emulator_supports_hyperlink() -> bool:
    if (("SSH_CLIENT" in os.environ)
        or ("SSH_CONNECTION" in os.environ)
        or ("SSH_TTY" in os.environ)):
        return False
    if platform.system().lower() == "linux":
        return True # VTE terminals (GNOME, Guake, Tilix, ...) are fine
    elif platform.system().lower() == "darwin": # macOS
        if os.environ.get("TERM_PROGRAM", "").lower().startswith("apple"):
            return False # Apple's default Terminal.app is lame, recommend iTerm2.app
        return True
    return False

# Make a hyperlink in terminal without displaying the lengthy URL
# https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda
# Compatible with GNOME, iTerm2, Guake, hTerm, etc.
# NOTE the URL should not contain ';' or ':' or ASCII code outside 32-126.
IS_ATTY = sys.stdin.isatty() and sys.stdout.isatty()
def hyperlink_str(url: str, description : str = "link") -> str:
    if (not IS_ATTY) or (not guess_emulator_supports_hyperlink()):
        return url
    url = url if "://" in url else ("file://" + os.path.abspath(url))
    return "\x1b]8;;%s\x1b\\%s\x1b]8;;\x1b\\" % (url, description)
