#!/usr/bin/env bash

has_error=0

printf "\033[32;1m# run tests that are all good\n\033[0m"
printf "\033[32;1m./runtest.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1\n\033[0m"
./runtest.py --timer mocks/timer.py --meta mocks/meta-all-good.json -g logs1   || true

if [ ! -f logs1/run.log ] ; then
    printf "\033[32;1mmissing: logs1/run.log\n\033[0m"
    has_error=1
fi
if [ $(ls logs1/*.stdout | wc -l) -ne 2 ] ; then
    printf "\033[32;1m*.stdout count incorrect (expect 2):\n\033[0m"
    ls logs1/*.stdout
    has_error=1
fi
if [ $(ls logs1/*.diff.html | wc -l) -ne 0 ] ; then
    printf "\033[32;1m*.stdout count incorrect (expect 0):\n\033[0m"
    ls logs1/*.diff.html
    has_error=1
fi

# run tests, some of them being bad
printf "\033[32;1m\n# run tests, some of them being bad\n\033[0m"
printf "\033[32;1m./runtest.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2\n\033[0m"
./runtest.py --timer mocks/timer.py --meta mocks/meta-with-error.json -g logs2 || true

if [ ! -f logs2/run.log ] ; then
    printf "\033[32;1mmissing: logs1/run.log\n\033[0m"
    has_error=1
fi
if [ $(ls logs2/*.stdout | wc -l) -ne 4 ] ; then
    printf "\033[32;1m*.stdout count incorrect (expect 4):\n\033[0m"
    ls logs2/*.stdout
    has_error=1
fi
if [ $(ls logs2/*.diff.html | wc -l) -ne 3 ] ; then
    printf "\033[32;1m*.stdout count incorrect (expect 3):\n\033[0m"
    ls logs2/*.diff.html
    has_error=1
fi

printf "\033[32;1m\n# write golden files (expected stdout), with some tests being bad\n\033[0m"
printf "\033[32;1m./runtest.py --timer mocks/timer.py --meta mocks/meta-write-golden.json -g logs3 -w\n\033[0m"
if [ -f delete_me.gold ] ; then rm delete_me.gold; fi
./runtest.py --timer mocks/timer.py --meta mocks/meta-write-golden.json -g logs3 -w <<< "y" || true

if [ ! -f logs2/run.log ] ; then
    printf "\033[32;1mmissing: logs1/run.log\n\033[0m"
    has_error=1
fi
if [ $(ls logs3 | wc -l) -ne 1 ] ; then
    printf "\033[32;1mlogs3 file count incorrect (expect 1):\n\033[0m"
    ls logs3
    has_error=1
fi
if [ -f delete_me.gold ] ; then
    rm delete_me.gold
else
    printf "\033[32;1mmissing: delete_me.gold\n\033[0m"
    has_error=1
fi

if [ $has_error -ne 1 ] ; then
    printf "\033[32;1m\nSummary: All is fine\n\033[0m"
else
    printf "\033[31;1m\nSummary: Error found\n\033[0m"
fi

exit $has_error
