"""No cloud code path may reach yfinance.

Why this is a test and not a note in the README: a cloud session's only durable output is
commits. A datacentre IP was reported rate-limited across every yfinance endpoint with no
recovery in 48 hours, so a cloud session built on yfinance burns credit, commits nothing, and
cannot tell anyone — it has no conversational channel back. The constraint has to live in code.

The test walks the import graph outward from every module under src/market_monitor/cloud/,
following intra-package imports, and fails if the banned module is reachable. yfinance stays
legal under src/market_monitor/local/ and in recovered/, which is reference code nothing imports.
"""
import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PKG = REPO / "src" / "market_monitor"
CLOUD = PKG / "cloud"

BANNED = {"yfinance"}
PKG_NAME = "market_monitor"


def dotted_name(file: pathlib.Path) -> str:
    """market_monitor/cloud/foo.py -> 'market_monitor.cloud.foo'"""
    rel = file.relative_to(PKG.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def package_of(file: pathlib.Path) -> str:
    """The package a relative import inside `file` resolves against."""
    name = dotted_name(file)
    if file.name == "__init__.py":
        return name
    return name.rsplit(".", 1)[0] if "." in name else ""


def file_for(module: str) -> pathlib.Path | None:
    """Resolve a dotted module name to a file inside this package, or None if external."""
    parts = module.split(".")
    if not parts or parts[0] != PKG_NAME:
        return None
    base = PKG.joinpath(*parts[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def imported_modules(file: pathlib.Path) -> list[str]:
    """Absolute dotted names of everything `file` imports, relative imports resolved."""
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    found: list[str] = []
    pkg = package_of(file)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # `from .. import x` — climb `level - 1` packages from this module's package
                base = pkg.split(".") if pkg else []
                climb = node.level - 1
                base = base[: len(base) - climb] if climb else base
                target = ".".join(base + ([node.module] if node.module else []))
                found.append(target)
                # also record submodule imports: from . import sibling
                for alias in node.names:
                    found.append(".".join(filter(None, [target, alias.name])))
            elif node.module:
                found.append(node.module)
                for alias in node.names:
                    found.append(f"{node.module}.{alias.name}")
    return found


def test_cloud_paths_cannot_reach_banned_modules():
    if not CLOUD.is_dir():
        # Nothing to check yet. Stated rather than silently passing.
        return
    entry_points = sorted(CLOUD.rglob("*.py"))
    seen: set[pathlib.Path] = set()
    queue = list(entry_points)
    violations: list[str] = []

    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for module in imported_modules(current):
            root = module.split(".")[0]
            if root in BANNED:
                violations.append(
                    f"{current.relative_to(REPO).as_posix()} imports {module}"
                )
            nxt = file_for(module)
            if nxt is not None and nxt not in seen:
                queue.append(nxt)

    assert not violations, (
        "A cloud code path can reach a banned module:\n"
        + "\n".join("  " + v for v in violations)
        + "\n\nMove the fetch into src/market_monitor/local/ and have the cloud path read a "
          "committed artefact instead."
    )


def test_cloud_package_exists_so_this_test_is_not_vacuous():
    """A guard on the guard: if cloud/ is renamed away, this suite must say so loudly."""
    assert CLOUD.is_dir(), (
        f"{CLOUD} is missing, so the no-yfinance check is scanning nothing. Either restore the "
        "directory or update BANNED/CLOUD in this test deliberately."
    )
