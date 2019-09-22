# testtools

Utilities to run tests.

## Prerequsites:
- Python2.7+ or Python3
- (to view the HTML diff) a web browser

## Files

### [runtest.py](runtest.py)

Run tests in parallel with designated timer.
- loads from a JSON file tests' metadata: programs, args, timeout values, expected exit and stdout, ...
- generates a log file in JSON,
- multiprocessing,
- runs each test with a timer,
- checks each test's exit status and stdout,
- if stdout is not as expected, generates a HTML for the diff

```sh
$ ./runtest.py --help
usage: runtest.py [-h] [--timer TIMER] [--paths T [T ...]] [--meta PATH] [-1]
                  [-g LOGDIR] [-w] [-e]

Test runner, with timer and logging and HTML diff view

optional arguments:
  -h, --help            show this help message and exit
  --timer TIMER         path to the timer program (required)
  --paths T [T ...]     paths to test executables
  --meta PATH           JSON file of tests' metadata
  -1, --sequential      run sequentially instead concurrently
  -g LOGDIR, --log LOGDIR
                        directory to write logs, default: ./logs
  -w, --write-golden    write stdout to golden files
  -e, --explain         explain more concepts

Unless '--explain' is given, exactly one of '--paths' and '--meta' is needed.
```

The timer program is compiled from [ctimer](https://github.com/Leedehai/ctimer), a project of mine.

Check:
```sh
# run tests that are all good
./runtest.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1
# view the log as text file
open -t logs1/run.log

# run tests, some of them being bad
./runtest.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2
# view the log as text file
open -t logs2/run.log
# view the diff files in browser (these diff files' paths are recorded in the log)
open logs2/normal.exe-00000.diff.html
open logs2/normal.exe-fcea8.diff.html
open logs2/normal.exe-6a39d.diff.html
```

### [view.py](view.py)

View the tests from browser. It is a single page web application, without third-party libraries.
> It needs [view.html](view.html), [view.css](view.css), and [view.js](view.js).

### [diffhtmlstr.py](diffhtmlstr.py)

Returns a valid HTML string that contains a table to render the diff view. Used by [runtest.py](runtest.py).
> The HTML format is [diff.html](diff.html) - the placeholders are `%s` instead of `{slot_name}` because escaping `{` and `}` will hinder parsing CSS definitions.

###### EOF