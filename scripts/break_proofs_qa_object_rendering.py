#!/usr/bin/env python3
"""Can the Q&A object-rendering guards fail? Mutate a mirror, require RED.

Same discipline as `break_proofs_run_durability.py`: mutations are applied to
a COPY of the tree, never to shared `src/`, and the originals' digests are
compared afterwards.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_founder_qa_renders_objects.py",)
QA = "src/intent_engine/founder_brief/qa.py"

MUTATIONS = [
    ("A. dataclasses are not normalised", QA,
     "    if dataclasses.is_dataclass(row) and not isinstance(row, type):",
     "    if False:",
     "MarketBelief and Link reach the reader as repr() again"),

    ("B. the repr refusal is removed", QA,
     '    return "" if _LOOKS_LIKE_A_REPR.match(body) else body',
     "    return body",
     "a type nobody normalised prints its repr at a board"),

    ("C. the list branch decides shape before normalising", QA,
     "            value = [_as_row(v) for v in value]\n"
     "            if value and any(isinstance(v, dict) for v in value):",
     "            if value and any(isinstance(v, dict) for v in value):",
     "a list of dataclasses goes back to the str()-join that leaked"),

    ("D. the belief's own words are dropped again", QA,
     '                     "proposition", "strongest_support", "frm")',
     '                     )',
     "the leak becomes an absence: nothing renderable, so the answer is the "
     "absent copy while the belief sits in the object"),

    ("E. the basis is dropped", QA,
     '                    "basis_detail", "because", "to")',
     "                    )",
     "the belief renders without what it rests on"),

    ("F. a plain object is not normalised", QA,
     "    if hasattr(row, \"__dict__\") and not isinstance(\n"
     "            row, (str, bytes, int, float, bool)):",
     "    if False:",
     "the next producer shape leaks"),

    ("J. the READ branch str()s its rows again", QA,
     "        rendered = [t for t in (_render_row(r) for r in rows) if t]\n"
     "        return \"; \".join(rendered)",
     "        return \"; \".join(\n"
     "            str(getattr(r, \"statement\", \"\") or getattr(r, \"text\", \"\") "
     "or r)\n            for r in rows)",
     "the leak that SHIPPED: the decision branch was repaired and these three "
     "questions answer from the canonical read instead"),

    ("K. the weakest link falls back to the object", QA,
     "            return _printable(str(getattr(weakest, \"text\", \"\") or \"\")) \\\n"
     "                or _render_row(weakest)",
     "            return str(getattr(weakest, \"text\", \"\") or weakest)",
     "Link() prints its repr on 'what is the weakest assumption?'"),

    ("G. a scalar object field is str()'d", QA,
     "        if not isinstance(value, (str, bytes)):\n"
     "            rendered = _render_row(value)\n"
     "            if rendered:\n"
     "                return rendered, name",
     "        if False:\n"
     "            rendered = _render_row(value)\n"
     "            if rendered:\n"
     "                return rendered, name",
     "key_risk carrying a row prints its repr"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before = {name: digest(ROOT / name) for name in (QA,)}
    results = []
    for name, rel, find, replace, meaning in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            mirror = pathlib.Path(tmp) / "tree"
            shutil.copytree(ROOT, mirror, symlinks=True,
                            ignore=shutil.ignore_patterns(
                                ".git", ".venv", "node_modules", "__pycache__",
                                "reports", "data", "docs"))
            target = mirror / rel
            source = target.read_text()
            if find not in source:
                results.append((name, "ANCHOR_MISSING", meaning))
                continue
            mutated = source.replace(find, replace, 1)
            if mutated == source:
                results.append((name, "NO_OP", meaning))
                continue
            target.write_text(mutated)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *SUITE, "-q", "-x",
                 "--no-header", "-p", "no:cacheprovider"],
                cwd=mirror, capture_output=True, text=True)
            results.append((name, "CAUGHT" if proc.returncode
                            else "NOT_CAUGHT", meaning))
    intact = {name: digest(ROOT / name) for name in (QA,)} == before
    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; "
          f"source tree {'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
