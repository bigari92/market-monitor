"""The recovered pipeline must stay syntactically intact, and must stay unedited.

recovered/ holds the Sept-2026 research pipeline, pulled back out of a session transcript after
its scratch directory was deleted. It is evidence, not a library: nothing imports it, and it is
never edited in place. When a defect needs fixing, the fix goes in src/ with a note in
docs/RECOVERY.md saying what the original did.

This test exists so that a careless reformat, a line-ending change or a half-finished edit
cannot quietly corrupt the only surviving copy.
"""
import pathlib
import py_compile
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
RECOVERED = REPO / "recovered"

# Recovery, 2026-10-18: 36 scripts extracted from the transcript, all compiling. One
# (fix_tax_language.py) was then excluded from this repository because it embeds verbatim
# passages of the owner's private plan.md — see docs/RECOVERY.md. 35 remain here.
EXPECTED_MIN_SCRIPTS = 35


def test_recovered_directory_is_present():
    assert RECOVERED.is_dir(), (
        f"{RECOVERED} is missing. It is the only surviving copy of the Sept-2026 pipeline; "
        "regenerate it with tools/extract_from_transcript.py before doing anything else."
    )


def test_every_recovered_script_compiles():
    scripts = sorted(RECOVERED.glob("*.py"))
    assert len(scripts) >= EXPECTED_MIN_SCRIPTS, (
        f"only {len(scripts)} scripts in recovered/, expected at least "
        f"{EXPECTED_MIN_SCRIPTS}. Something was deleted."
    )
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for script in scripts:
            out = pathlib.Path(tmp) / (script.name + "c")
            try:
                py_compile.compile(str(script), cfile=str(out), doraise=True)
            except py_compile.PyCompileError as exc:
                failures.append(f"{script.name}: {exc.msg.strip()[:160]}")
    assert not failures, "recovered scripts no longer compile:\n" + "\n".join(
        "  " + f for f in failures
    )


def test_nothing_in_src_imports_the_recovered_code():
    """recovered/ is evidence. Importing it would make a deleted folder's defects load-bearing."""
    src = REPO / "src"
    if not src.is_dir():
        return
    offenders = [
        f.relative_to(REPO).as_posix()
        for f in src.rglob("*.py")
        if "import recovered" in f.read_text(encoding="utf-8")
        or "from recovered" in f.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "src/ imports recovered/: " + ", ".join(offenders)
        + "\nPort the logic deliberately instead, so the four known defects do not come with it."
    )
