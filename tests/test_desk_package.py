"""The desk package must stay importable where the personal folder does not exist.

This is not hypothetical. The first version resolved the personal folder at import time
with a hard existence check, which would have failed this whole suite the moment it ran
anywhere but the owner's laptop — a cloud session, CI, or a fresh clone. The requirement
belongs on the first READ, not on the import.

The package reads the owner's ledger, so it can only produce numbers on his machine. It
must still load, and fail with a sentence that says why, everywhere else.
"""
import importlib
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def test_package_imports_with_no_personal_folder(monkeypatch):
    monkeypatch.setenv(
        "MARKET_MONITOR_PERSONAL_ROOT",
        str(REPO / "tests" / "_a_folder_that_does_not_exist"),
    )
    for name in list(sys.modules):
        if name.startswith("market_monitor.local.desk"):
            del sys.modules[name]
    ledger = importlib.import_module("market_monitor.local.desk.ledger")
    digest = importlib.import_module("market_monitor.local.desk.digest")
    assert ledger.DATA.name == "data"
    assert callable(digest.build)


def test_reading_without_the_folder_fails_with_an_explanation(monkeypatch):
    missing = REPO / "tests" / "_a_folder_that_does_not_exist"
    monkeypatch.setenv("MARKET_MONITOR_PERSONAL_ROOT", str(missing))
    for name in list(sys.modules):
        if name.startswith("market_monitor.local.desk"):
            del sys.modules[name]
    ledger = importlib.import_module("market_monitor.local.desk.ledger")
    with pytest.raises(FileNotFoundError) as exc:
        ledger.nav_series()
    message = str(exc.value)
    assert "MARKET_MONITOR_PERSONAL_ROOT" in message, (
        "the error must name the environment variable that fixes it"
    )


def test_no_cloud_module_reads_the_personal_folder():
    """Structural, not stylistic: tests/test_no_yfinance_in_cloud_paths.py walks the
    import graph from cloud/ only, so anything touching personal data has to live under
    local/ for that guard to mean anything.

    Uses codeaudit rather than a text search. The first version of this test failed on
    cloud/__init__.py's own docstring, which names the personal folder in order to say
    that nothing there reads it — a guard that fires on its own rationale gets deleted.
    """
    from market_monitor import codeaudit

    cloud = REPO / "src" / "market_monitor" / "cloud"
    offenders = codeaudit.scan(cloud.rglob("*.py"), "Investing")
    assert not offenders, (
        "a cloud module has the personal folder in running code: " + ", ".join(offenders)
    )
