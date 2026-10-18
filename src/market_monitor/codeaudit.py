"""Does a forbidden string reach RUNNING CODE, as opposed to being discussed in prose?

This exists because the same bug was written twice in one afternoon. Two guards —
"the desk page must not read holdings.json" and "no cloud module may reference the
personal folder" — were both implemented as a text search over the source, and both
failed on documentation that named the forbidden thing precisely in order to explain why
it must not be used:

    cloud/__init__.py:  "Nothing here reads C:/Users/valer/Investing."
    desk/ledger.py:     "holdings.json was stamped as_of 2026-10-08 and was wrong..."

A guard that fires on its own rationale gets deleted, and then it guards nothing. So the
check parses instead: a string literal counts only when it is not a docstring, which is
the difference between code that opens a file and a sentence about not opening it.

Comments are excluded for free — the parser never sees them.
"""
from __future__ import annotations

import ast
import pathlib


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Identities of the Constant nodes that are docstrings, not data."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                found.add(id(body[0].value))
    return found


def literal_hits(path: pathlib.Path, needle: str) -> list[int]:
    """Line numbers where `needle` appears in a non-docstring string literal."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    skip = _docstring_ids(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and needle in node.value
        and id(node) not in skip
    )


def scan(paths, needle: str, exclude_names: set[str] | None = None) -> list[str]:
    """"file.py:12" for every place `needle` reaches running code. Empty means clean."""
    exclude_names = exclude_names or set()
    out: list[str] = []
    for path in sorted(paths):
        if path.name in exclude_names:
            continue
        for line in literal_hits(path, needle):
            out.append(f"{path.name}:{line}")
    return out
