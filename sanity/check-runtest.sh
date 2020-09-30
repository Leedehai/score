#!/usr/bin/env bash

has_error=0

if [ ! -d sanity ]; then
  echo "Your current working directory is not at the project root"
  exit 1
fi

printf "\033[32;1m# run tests that are all good\n\033[0m"
printf "\033[32;1m./score_run.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1\n\033[0m"
./score_run.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1 ; exit_code=$?

if [ $exit_code -ne 0 ]; then
    printf "\033[31;1mexit code is not 0\n\033[0m"
    has_error=1
fi
if [ ! -f logs1/log.json ] ; then
    printf "\033[31;1mmissing: logs1/log.json\n\033[0m"
    has_error=1
fi
if [ $(ls logs1/*/*.stdout | wc -l) -ne 2 ] ; then
    printf "\033[31;1m*.stdout count incorrect (expect 2):\n\033[0m"
    ls logs1/*.stdout
    has_error=1
fi
if [ $(ls logs1/*/*.diff.html 2> /dev/null | wc -l) -ne 0 ] ; then
    printf "\033[31;1m*.diff.html count incorrect (expect 0):\n\033[0m"
    ls logs1/*.diff.html
    has_error=1
fi

printf "\033[32;1m./score_ui.py --title \"Mock tests\" --timer mocks/timer.py --log logs1/log.json --to-dir logs1/html\n\033[0m"
./score_ui.py --title "Mock tests" --timer mocks/timer.py --log logs1/log.json --to-dir logs1/html ; exit_code=$?
if [ $exit_code -ne 0 ]; then
    printf "\033[31;1mexit code is not 0\n\033[0m"
    has_error=1
fi
if [ ! -f logs1/html/index.html ] ; then
    printf "\033[31;1mmissing: logs1/html/index.html\n\033[0m"
    has_error=1
fi

# run tests, some of them being bad
printf "\033[32;1m\n# run tests, some of them being bad\n\033[0m"
printf "\033[32;1m./score_run.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2\n\033[0m"
./score_run.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2 ; exit_code=$?

if [ $exit_code -ne 1 ]; then
    printf "\033[31;1mexit code is not 1\n\033[0m"
    has_error=1
fi
if [ ! -f logs2/log.json ] ; then
    printf "\033[31;1mmissing: logs1/log.json\n\033[0m"
    has_error=1
fi
if [ $(ls logs2/*/*.stdout | wc -l) -ne 5 ] ; then
    printf "\033[31;1m*.stdout count incorrect (expect 5):\n\033[0m"
    ls logs2/*.stdout
    has_error=1
fi
if [ $(ls logs2/*/*.diff.html | wc -l) -ne 3 ] ; then
    printf "\033[31;1m*.diff.html count incorrect (expect 3):\n\033[0m"
    ls logs2/*.diff.html
    has_error=1
fi

printf "\033[32;1m./score_ui.py --title \"Mock tests\" --timer mocks/timer.py --log logs2/log.json --to-dir logs2/html\n\033[0m"
./score_ui.py --title "Mock tests" --timer mocks/timer.py --log logs2/log.json --to-dir logs2/html ; exit_code=$?
if [ $exit_code -ne 0 ]; then
    printf "\033[31;1mexit code is not 0\n\033[0m"
    has_error=1
fi
if [ ! -f logs2/html/index.html ] ; then
    printf "\033[31;1mmissing: logs2/html/index.html\n\033[0m"
    has_error=1
fi

printf "\033[32;1m\n# write golden files (expected stdout), with some tests being bad\n\033[0m"
printf "\033[32;1m./score_run.py --timer mocks/timer.py --meta mocks/meta-write-golden.json -g logs3 -w\n\033[0m"
if [ -f delete_me.gold ] ; then rm delete_me.gold; fi
./score_run.py --timer mocks/timer.py --meta mocks/meta-write-golden.json -g logs3 -w <<< "y" ; exit_code=$?

if [ $exit_code -ne 1 ]; then
    printf "\033[31;1mexit code should be 1\n\033[0m"
    has_error=1
fi
if [ ! -f logs2/log.json ] ; then
    printf "\033[31;1mmissing: logs1/log.json\n\033[0m"
    has_error=1
fi
if [ $(ls logs3 | wc -l) -ne 1 ] ; then
    printf "\033[31;1mlogs3 file count incorrect (expect 1):\n\033[0m"
    ls logs3
    has_error=1
fi
if [ -f delete_me.gold ] ; then
    rm delete_me.gold
else
    printf "\033[31;1mmissing: delete_me.gold\n\033[0m"
    has_error=1
fi
if [ -f should_not_be_created.gold ] ; then
    printf "\033[31;1mshould not exist: should_not_be_created.gold\n\033[0m"
    has_error=1
fi

if [ $has_error -ne 1 ] ; then
    printf "\033[32;1m\nSummary: All is fine\n\033[0m"
else
    printf "\033[31;1m\nSummary: Error found\n\033[0m"
fi

exit $has_error
