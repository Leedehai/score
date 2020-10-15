# Copyright (c) 2020 Leedehai. All rights reserved.
# Use of this source code is governed under the MIT LICENSE.txt file.

import argparse
import multiprocessing
import os
import sys
from enum import Enum
from typing import Any, Dict, OrderedDict, Tuple

from pylibs.score_utils import error_s

# Types.

Args = argparse.Namespace
TaskMetadata = Dict[str, Any]
TaskResult = OrderedDict[str, Any]
TaskWorkerArgs = Tuple[str, bool, str, bool, TaskMetadata]

# Constants.

LOG_FILE_BASE = "log.json"
DELIMITER_STR = "#####"
GOLDEN_NOT_WRITTEN_PREFIX = "golden file not written"


class TaskExceptions(Enum):
    GOLDEN_NOT_WRITTEN_SAME_CONTENT = "%s: content is the same" % GOLDEN_NOT_WRITTEN_PREFIX
    GOLDEN_NOT_WRITTEN_WRONG_EXIT = "%s: the test's exit is not as expected" % GOLDEN_NOT_WRITTEN_PREFIX
    GOLDEN_FILE_MISSING = "golden file missing"


class TaskEnvKeys(Enum):
    CTIMER_DELIMITER_ENVKEY = "CTIMER_DELIMITER"
    CTIMER_TIMEOUT_ENVKEY = "CTIMER_TIMEOUT"


def get_num_workers(env_var: str) -> int:
    env_num_workers = os.environ.get(env_var, "")
    if len(env_num_workers) > 0:
        try:
            env_num_workers_number = int(env_num_workers)
        except ValueError:
            sys.exit(error_s("env vairable '%s' is not an integer" % env_var))
        if env_num_workers_number <= 0:
            sys.exit(error_s("env variable '%s' is not positive" % env_var))
        return env_num_workers_number
    return multiprocessing.cpu_count()


NUM_WORKERS_MAX = get_num_workers(
    env_var="NUM_WORKERS")  # not "NUM_WORKERS_MAX", to be consistent
