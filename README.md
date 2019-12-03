# score
> Formerly "testtools"

[![Build Status](https://travis-ci.org/Leedehai/score.svg?branch=master)](https://travis-ci.org/Leedehai/score)

Utilities to run tests.

## Prerequsites:
- Linux or macOS (Windows not tested)
- Python2.7+ or Python3

## Files

### [runtest.py](runtest.py)

Run tests in parallel with designated timer.
- loads from a JSON file tests' metadata: programs, args, timeout values, expected exit and stdout, ...
- generates a log file in JSON,
- multiprocessing,
- runs each test with a timer,
- checks each test's exit status and stdout,
- if stdout is not as expected, generates a HTML for the diff
- program is self-documented
- print logs in realtime [with multiline rotation](img/multiline-rotation.md)

```sh
$ ./runtest.py --help
usage: runtest.py [-h] [--timer TIMER] [--meta PATH] [--paths T [T ...]]
                  [-g DIR] [-1] [-w] [--docs]

Test runner: with timer, logging, diff in HTML

optional arguments:
  -h, --help          show this help message and exit
  --timer TIMER       path to the timer program
  --meta PATH         JSON file of tests' metadata
  --paths T [T ...]   paths to test executables
  -g DIR, --log DIR   directory to write logs, default: ./logs
  -1, --sequential    run sequentially instead concurrently
  -w, --write-golden  write stdout to golden files instead of checking
  --docs              self-documentation in more details

Unless '--docs' is given, exactly one of '--paths' and '--meta' is needed.
```

The timer program can be compiled from [ctimer](https://github.com/Leedehai/ctimer), written in C++ with POSIX system calls, another project of mine. Of course, you can use your own timer program instead (e.g. one that can run on Windows), as long as its commandline interface meets what is laid out in `./runtest.py --docs`. 

#### Testing
```sh
sanity/check-runtest.sh
```

#### Examples
```sh
# run tests that are all good
./runtest.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1
# view the log as text file
vim logs1/run.log
# clear up
rm -rf logs1
```

```sh
# run tests, some of them being bad
./runtest.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2
# view the log as text file
vim logs2/run.log
# view the diff files in browser (their paths are found in the log)
#   on macOS, use 'open' to open files from terminal;
#   on Linux distributions, however, the most widely installed is 'xdg-open'
open logs2/normal.exe-00000.diff.html # stdout is empty
open logs2/normal.exe-fcea8.diff.html # golden file is not found
open logs2/normal.exe-6a39d.diff.html # stdout is not as expected
# clear up
rm -rf logs2
```

```sh
# write golden files (expected stdout), with some tests being bad
./runtest.py --timer mocks/timer.py --meta mocks/meta-write-golden.json -g logs3 -w
# clear up
rm -rf logs3 && rm -f delete_me.gold
```

### [view.py](view.py)

Result viewer, which generates a static website to view the tests' results in browser.

No third-party libraries needed.

```sh
./viwe.py --help
# TODO
```

#### Examples:
TODO

### [diffhtmlstr.py](diffhtmlstr.py)

Returns a valid HTML string that contains a table to render the diff view. Used by [runtest.py](runtest.py).
> The HTML format is [diff.html](diff.html) - the placeholders are `%s` instead of `{slot_name}` because escaping `{` and `}` distorts the CSS definition statements.

###### EOF
