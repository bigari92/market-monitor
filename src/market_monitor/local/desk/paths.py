"""Where the personal folder is. The one place that knows.

The desk page's CODE lives in this repository; its DATA does not and never will. That
means the code cannot locate the data by walking up from __file__ the way a script
inside the personal folder could, so the location is named here once and overridable by
environment variable for anyone running this on another machine.

A cloud session has no such folder. `require()` therefore fails loudly rather than
returning an empty result that would render a confident, empty page.
"""
from __future__ import annotations

import os
import pathlib

DEFAULT = pathlib.Path("C:/Users/valer/Investing")
ENV_VAR = "MARKET_MONITOR_PERSONAL_ROOT"


def personal_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get(ENV_VAR, str(DEFAULT)))


def require() -> pathlib.Path:
    root = personal_root()
    if not root.is_dir():
        raise FileNotFoundError(
            f"personal folder not found at {root}. Set {ENV_VAR} to point at it. "
            f"This code reads the owner's ledger and cannot run anywhere else — a cloud "
            f"session will never have it, which is intended."
        )
    return root
