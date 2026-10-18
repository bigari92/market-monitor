"""Run the desk page. `python desk.py` renders it; `python desk.py check` verifies it.

A three-line runner rather than a console-script entry point: this has to work from a
plain checkout with no `pip install -e .`, and the owner should be able to read the whole
launcher at a glance.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from market_monitor.local.desk import digest, selfcheck  # noqa: E402

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "render"
    if action == "check":
        raise SystemExit(selfcheck.main())
    if action == "render":
        raise SystemExit(digest.main())
    raise SystemExit(f"unknown action {action!r}; use 'render' or 'check'")
