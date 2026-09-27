#!/usr/bin/env python
"""Has a printed name got into the repository?

    uv run scripts/leaks.py            every tracked file
    uv run scripts/leaks.py --specs    every spec an author is shown

The engine holds ids. Names live in `localization/names.json`, which is built
from your own copy of the compendium and is not committed. This is what holds
the repository to that -- it reads every name the compendium has and looks for
each one in every tracked file.

Exits non-zero on a find, so it can gate a commit.

**`--specs` checks the other half, and for a long time nothing did.** The
tracked files are what ships; the `spec` columns in `game.db` are what an
authoring agent is actually *shown*, and a name reaching one of those has
gone exactly where this whole arrangement exists to keep it from going.
Nothing caught it because `game.db` is gitignored and so is not a tracked
file. It was invisible until items and feats arrived -- a feat's Special
line is usually about another feat, and a set names its members -- and
then it was 143 rows at once.

`etl/build.py`'s two cross-reference passes are the fix; this is what
says whether they worked.

Matching is by whole word sequence, longest first. Two words or more is
reported outright: "stone hurler" turning up in a source file is never a
coincidence.

One-word names are the hard part, and a hand-kept list of exceptions is the
wrong answer -- abilities are called `Turn`, `Move`, `Split` and `Shift`, and
that list would need feeding forever. So the rule comes out of the data
instead: **a word used as a name by many different rows is vocabulary, not a
name.** `Bite` names hundreds of stat blocks and identifies none of them; an
invented-sounding one names a single row. Nothing to maintain, and it adapts on its own to
whichever build of the compendium you have.

**A race's name is the exception to that**, and needs the line it sits on
to be told apart. `Elf`, `Human`, `Drow` and `Goblin` are races, are
dictionary words, and are also the type word a stat block prints -- so the
rule above waives all of them, and 82 racial cards printed their race's
name to authors with nothing saying so. See `names_a_race` in
`etl/sanitise.py` for where the line decides.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from combat_engine.etl.build import ROOT, game, localisation
from combat_engine.etl.sanitise import (
    RULES_TERMS,
)
from combat_engine.etl.sanitise import (
    identifies as _identifies,
)
from combat_engine.etl.sanitise import (
    vocabulary as vocabulary,
)

#: Rules terms the engine is entitled to say. A game system cannot be
#: trademarked, so the words that *are* the mechanics -- dazed, combat
#: advantage, saving throw -- are not what this script is protecting. Proper
#: names are. Somebody published an ability called "Bloodied", which is why
#: this list has to exist at all.
#:
#: Most of it is generated from the engine's own enumerations, so a condition
#: added to `types.py` is allowed here the moment it exists and this file
#: never needs editing for it.
CORE = set(RULES_TERMS)


SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", "localization"}
TEXT_SUFFIXES = {".py", ".md", ".js", ".css", ".html", ".json", ".toml", ".txt", ".sql"}


def tracked() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split()
        return [ROOT / p for p in out]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [
            p
            for p in ROOT.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
        ]


def specs() -> int:
    """Every spec column, checked the way a tracked file is.

    Reported per row rather than per line, because a spec is one document
    and a row that prints a neighbour's name four times is one thing to
    fix, not four.
    """
    names = localisation()
    if not names:
        print("localization/names.json is missing.", file=sys.stderr)
        return 0

    index: dict[str, list[str]] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip().lower()
        if len(name) > 2:
            index.setdefault(name, []).append(ref)
    rules = vocabulary()

    db = game()
    found: list[tuple[str, str, str, list[str]]] = []
    for table in ("power", "monster_power", "class_feature", "companion",
                  "item", "item_block", "feat", "race"):
        for ref, spec in db.execute(f"SELECT ref, spec FROM {table}"):
            for line in (spec or "").splitlines():
                for name, refs in _hits(line, index):
                    # Its own name, or a card printed inside it -- `p289b`
                    # belongs to `p289` and may say so.
                    if any(r.startswith(ref) or ref.startswith(r) for r in refs):
                        continue
                    if _identifies(name, refs, rules, line):
                        found.append((table, ref, name, refs))
                        break
                else:
                    continue
                break

    for table, ref, _name, refs in found[:40]:
        print(f"{table}.{ref}: prints the name of {', '.join(refs[:3])}")
    if found:
        extra = " (showing 40)" if len(found) > 40 else ""
        print(f"\n{len(found)} specs print another row's printed name{extra}.")
        print("Every one of them is shown to an author verbatim. "
              "See `_cross_reference` in etl/build.py.")
        return 1
    print("no printed names in any spec")
    return 0


def main() -> int:
    if "--specs" in sys.argv:
        return specs()
    names = localisation()
    if not names:
        print(
            "localization/names.json is missing, so there is nothing to check "
            "against. Run: uv run scripts/build.py",
            file=sys.stderr,
        )
        return 0

    index: dict[str, list[str]] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip().lower()
        if len(name) > 2:
            index.setdefault(name, []).append(ref)

    rules = vocabulary()
    findings: list[tuple[Path, int, str, list[str]]] = []
    quiet: list[tuple[Path, int, str, list[str]]] = []

    for path in tracked():
        if path.suffix not in TEXT_SUFFIXES or not path.exists():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            for name, refs in _hits(line, index):
                where = findings if _identifies(name, refs, rules, line) else quiet
                where.append((path.relative_to(ROOT), n, name, refs))

    for path, n, name, refs in findings:
        print(f"{path}:{n}: {name!r} is the printed name of {', '.join(refs[:3])}")

    if quiet:
        words = sorted({name for _, _, name, _ in quiet})
        print(
            f"\n{len(quiet)} matches on {len(words)} common words, not reported: "
            + ", ".join(words[:12])
            + (" ..." if len(words) > 12 else "")
        )

    if findings:
        print(f"\n{len(findings)} leaks. Names belong in localization/, not in the tree.")
        return 1
    print("no printed names in tracked files")
    return 0


def _hits(line: str, index: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    """Every name appearing in this line, as a whole word sequence.

    Built from the line's own word n-grams rather than by trying 17,000
    regexes -- one pass over the line instead of one pass per name.
    """
    out: list[tuple[str, list[str]]] = []
    # Within runs of prose only. Punctuation is a boundary -- a method
    # signature is not a sentence, and reading across the opening bracket
    # made every `def <verb>(self` pair look like a two-word name.
    for run in re.findall(r"[a-z'](?:[a-z' -]*[a-z'])?", line.lower()):
        words = re.findall(r"[a-z']+", run)
        for size in range(min(6, len(words)), 0, -1):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size])
                if phrase in index:
                    out.append((phrase, index[phrase]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
