#!/usr/bin/env python3
from __future__ import annotations

import signal
import time


def _ignore_termination(_signum, _frame) -> None:
    return None


signal.signal(signal.SIGTERM, _ignore_termination)
while True:
    time.sleep(1)
