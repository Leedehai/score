# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the LICENSE.txt file.

EXPLANATION_STRING = """\x1b[33mSupplementary docs\x1b[0m

\x1b[33m'--timer':\x1b[0m
    It passes the path of a timer program that measures a program's processor
    time (not wall time) with timeout. The program's interface satisfies:
    [example] https://github.com/Leedehai/ctimer (mine)
    inputs:
        commandline arguments:
            the invocation of the inspected program
        environment variable CTIMER_TIMEOUT:
            timeout value (ms); 0 means effectively infinite time
        environment variable CTIMER_STATS:
            file path to write stats report; if not given, print to stdout
        environment variable CTIMER_DELIMITER:
            delimiter string at the beginning and end of the stats report
            string (see below); if not given, use empty string
        * the script will set the environment variables as needed locally
          when invoking the timer program
    outputs: the inspected program's outputs (stdout, stderr), with stats
        report in stdout if CTIMER_STATS is unspecified; if CTIMER_STATS
        is specified, the stats report will be written to that file
    stats report: a JSON string, representing an object:
        "exit"     : exit status object (see below), inspectee's exit status
        "times_ms" : object:
            "proc"      : floating point, inspectee's time on processor
            "abs_start" : floating point, absolute start time since Epoch
            "abs_end"   : floating point, absolute end time since Epoch
    others:
        * the timer should always exit with 0 regardless of the inspected
          program's exit status; non-0 exit is reserved for internal error.
        * the timer should pass whatever environment variables it has to
          the inspected program.

\x1b[33m'--meta':\x1b[0m
    This option passes the path of a file containing the metadata of tests.
    The metadata file could be either hand-written or script-generated; it
    stores in JSON format an array of metadata objects. Each has keys:
        "desc"    : string
            description of the test
        \x1b[33m=== parameters contolling command invocation ===\x1b[0m
        "path"    : string
            path to the test executable binary
        "args"    : array of strings
            the commandline arguments
        "envs"  : dict or null
            environment variables provided when running the test executable
            * each entry's key and value are strings without spaces
        \x1b[33m=== parameters controlling test checking ===\x1b[0m
        "golden"  : string or null
            path to the golden file; null: not needed
            * if the golden file path is given, the inspectee's stdout
              will be compared with the golden file content
            * if '--write-golden' is given, inspectee's stdout is written
              to this file
            * different tests should have different golden files, even if
              their contents are the same, to avoid possible data racing
              when writing the files for '--write-golden'
        "timeout_ms" : integer or null
            the max processor time (ms) allowed; null: effectively infinite
        "exit"    : exit status object (see below), storing the expected exit
    * all paths are relative to the current working directory
    * mutually exclusive: --meta, --paths

\x1b[33m'--paths':\x1b[0m
    In cases where only the paths of the test executables matter, prefer this
    option over '--meta', as it can be invoked with a list of space-separated
    test executable paths in commandline. Other fields required by a metadata
    object (see above) of each test will automatically get these values:
        desc = "", path = (the path provided with this option),
        args = [], envs = null, golden = null, timeout_ms = null,
        exit = { "type": "return", "repr": 0 } (exit status, see below)
    * mutually exclusive: --meta, --paths

\x1b[33m'--flakiness':\x1b[0m
    Not unusually, some tests are flaky (e.g. due to CPU scheduling or a bug
    in language runtime). Use this option to specify a directory that stores
    all declaration files. Under this directory, all files whose names match
    the glob pattern "*.flaky" will be loaded.
    In a declaration file, characters following '#' in a line are treated as
    comments. Each non-comment line is a flakiness declaration entry with
    space-separated string fields in order:
        1. test executable path (last two path components joined with '/')
        2. case id hash string (computed from commandline arguments and
           alphabetically-sorted environment variables) as appeared on the
           corresponding result object.
        3. type of expected error: one or more (joined by '|': non-exclusive
           'or') of WrongExitCode, Timeout, Signal, StdoutDiff, Others
        * you should ensure the field 1 of each entry is unique across all
          flakiness declaration files
        * joining the fields 1 and 2 with '-' produces the 'comb_id' (the ID
          for each unique path + args combination) in each result object in
          the master log
        * e.g.: a line could be "foo/bar-test 00000000 Timeout|StdoutDiff",
          and its 'comb_id' in the master log is "foo/bar-test-00000000"

\x1b[33m'--write-golden':\x1b[0m
    Use this option to create or overwrite golden files of tests. Tests with
    golden file unspecified (i.e. metadata's "golden" field is null) won't
    be executed.
    A golden file will be written only if the exit status of that test is as
    expected, and if the file exists, the content will be different.
    You have to manually check the tests are correct before writing.

\x1b[33mExit status object:\x1b[0m
    A JSON object with keys:
    "type"  : string - "return", "timeout", "signal", "quit", "unknown"
    "repr"  : integer, indicating the exit code for "return" exit, timeout
              limit (millisec, processor time) for "timeout" exit, signal
              value for "signal" exit, and null for others (timer errors)

\x1b[33mMaster log and result object:\x1b[0m
    The master log is a JSON file containing an array of result objects. To
    see the specification of the result object, please refer to the in-line
    comments in function `generate_result_dict()`.
    The master log is human-readable, but is more suited to be loaded and
    rendered by a script.

\x1b[33mMore on concepts:\x1b[0m
    metadata        description of a test: program path, arguments, ...
    golden file     the file storing the expected stdout output, nullable
    master log      a JSON file log.json under the log directory
    log directory   specified by '--log', which stores the master log
                    and tests' stdout and diff, if any, among others

\x1b[33mMore on options:\x1b[0m
    Complete list of options: "--help".
    Concurrency is enabled, unless '--sequential' is given.
    Unless '--help' or '--docs' is given:
        * '--timer' is needed, and
        * exactly one of '--paths' and '--meta' is needed."""
