"""The leak test.

This repository may become a GitHub remote and is readable by cloud sessions. The owner's
financial history lives in C:\\Users\\valer\\Investing. This test is the layer that notices if
any of it arrives here — including via `git add -f`, which .gitignore cannot stop, and including
a file that was tracked before the pattern was added.

It checks TRACKED PATHS, never file contents, so documentation is free to mention these
filenames by name (RECOVERY.md and the README both do).
"""
import subprocess
import fnmatch
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Basenames that are personal financial records. Matched case-insensitively at any depth.
FORBIDDEN_BASENAMES = [
    "trade-journal.csv",
    "holdings.json",
    "funding-log.csv",
    "tax-record.csv",
    "nbu_rates.csv",
    "ledger_*.csv",
    "flex-*.xml",
    "secrets.env",
    ".env",
    "*.pbix",
]

# Nothing under these directories may ever be tracked.
FORBIDDEN_DIRS = ["data/"]

MAX_TRACKED_BYTES = 50 * 1024 * 1024  # GitHub warns at 50 MiB and rejects at 100 MiB


def tracked_files():
    """Paths git currently tracks, as posix-style strings relative to the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        pytest.skip("not a git repository yet — nothing can have leaked")
    return [p for p in out.stdout.split("\0") if p]


def test_no_personal_filenames_tracked():
    offenders = []
    for path in tracked_files():
        base = path.rsplit("/", 1)[-1].lower()
        for pattern in FORBIDDEN_BASENAMES:
            if fnmatch.fnmatch(base, pattern.lower()):
                offenders.append((path, pattern))
    assert not offenders, (
        "Personal financial data is tracked in this repository:\n"
        + "\n".join(f"  {p}  (matches {pat})" for p, pat in offenders)
        + "\n\nRemove it from history, do not merely delete the file: a push publishes every "
          "commit, not just the tip."
    )


def test_no_data_directory_tracked():
    offenders = [
        p for p in tracked_files()
        if any(p.lower().startswith(d) for d in FORBIDDEN_DIRS)
    ]
    assert not offenders, (
        "Files under data/ are tracked: " + ", ".join(offenders)
        + "\ndata/ holds raw downloads and the price panel. It is re-derivable and too large; "
          "only small, deliberately chosen derived artefacts belong in git."
    )


def test_no_tracked_file_is_huge():
    offenders = []
    for path in tracked_files():
        f = REPO / path
        if f.is_file() and f.stat().st_size > MAX_TRACKED_BYTES:
            offenders.append((path, f.stat().st_size))
    assert not offenders, (
        "Tracked files over 50 MiB:\n"
        + "\n".join(f"  {p}  {n / 1048576:.1f} MiB" for p, n in offenders)
        + "\nGit LFS is not the answer here: free-tier bandwidth is exhausted by ~20 clones, "
          "after which the repo looks healthy and serves pointers instead of data."
    )


def test_investing_folder_is_not_a_git_repo():
    """The personal folder must never become a repository — that is the whole separation."""
    investing = pathlib.Path("C:/Users/valer/Investing")
    if not investing.exists():
        pytest.skip("personal folder not present on this machine (e.g. a cloud session)")
    assert not (investing / ".git").exists(), (
        "C:\\Users\\valer\\Investing has become a git repository. Its .gitignore does not cover "
        "trade-journal.csv, holdings.json, tax-record.csv, funding-log.csv or data/ledger_*.csv, "
        "so a push from there would publish the owner's tax position."
    )
