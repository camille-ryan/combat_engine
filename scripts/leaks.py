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

import contextlib
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from combat_engine.etl.build import ROOT, SOURCE, game, localisation
from combat_engine.etl.sanitise import (
    ALLOWED,
    COMMON_ENOUGH,
    RULES_TERMS,
    SHORTEST,
    ordinary,
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


#: Component words that are a **ref slug today**, each waiting on the issue
#: that removes it. Not an allow-list of coincidences -- every one is a real
#: printed name sitting in a real identifier, and the entry records which piece
#: of work takes it out.
#:
#: Hand-kept on purpose, and the opposite way round from the lists `lint.py`
#: warns about. A *derived* exemption -- "excuse any word used as a ref slug" --
#: would be self-fulfilling: the next author to mint a ref from a printed name
#: would be excused by the act of doing it, which is precisely what this pass
#: exists to report. A named list cannot do that.
#:
#: **A stale entry is a failure.** If a word here stops appearing, the work
#: landed and the entry is dead weight, so `main` says so and exits non-zero --
#: the discipline `todo.py` applies to a marker whose symbol has arrived. It
#: earned its keep immediately: `weaponmaster` was in here until the first run
#: pointed out that build words already come off the source's own `Class` name,
#: parentheses included, so `_type_words` excuses it and the entry was dead.
DEFERRED = {
    "battlerager": "#339 -- a sub-option name used as a BUILDS key",
    "winterkin": "#341 -- one of 113 racial-trait refs minted from a label",
}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", "localization"}
TEXT_SUFFIXES = {".py", ".md", ".js", ".css", ".html", ".json", ".toml", ".txt", ".sql"}


def _index(names: dict) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Every printed name, keyed so `_hits` can actually find it.

    **Hyphens normalise to spaces, on both sides.** `_hits` captures a run of
    prose with `[a-z' -]` and then splits it into words with `[a-z']+`, so a
    hyphen is a letter to the first regex and a boundary to the second: the
    only thing it can ever produce is a space-joined n-gram. Keying on the
    printed spelling therefore made **578 hyphenated printed names unmatchable
    by construction** -- not missed through a judgement call, unreachable. #336.

    Normalising the key rather than teaching `_hits` about hyphens is the
    smaller change and loses nothing: a file that writes the name with a space
    where the compendium writes a hyphen is just as much a leak, and this
    catches that too.

    Returns the lookup, and beside it the printed spelling of each key, so a
    finding can quote what the compendium prints rather than the normalised
    form a reader would then go looking for in vain.
    """
    index: dict[str, list[str]] = {}
    printed: dict[str, str] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip().lower()
        if len(name) <= 2:
            continue
        key = " ".join(name.replace("-", " ").split())
        index.setdefault(key, []).append(ref)
        printed.setdefault(key, name)
    return index, printed


def _type_words() -> set[str]:
    """Words the engine asks a creature *by*, which are never a name here.

    A race's name, a creature's kind, its role and its origin are printed
    beside the numbers because they are mechanical -- `is_kind("<type>")` is a
    real query and "the <type> shifts 1 square" is a rules sentence. The
    single-word pass already waives all of these through `names_a_race`; the
    component pass below needs the same list, because the identifying half of a
    two-word creature name is very often its type.

    **Read off the database, never listed.** Nothing in this file should have to
    spell a name in order to excuse it, which is the trap `_slot`'s allow-list
    in the ETL was written to avoid.

    **Class and build names are in here, and that is a deferral rather than a
    decision.** Of 28 distinct class values only three are invented compounds
    this pass would report; the other 25 are ordinary English. A class name is
    also the content tree's primary mechanical key -- `cls=`, the `cf:` refs, 27
    directories, 6,070 sites -- so the fix is to give `class` the compendium id
    it already has and never uses, which is #339. Until that lands these are
    excused, because a permanently red `leaks.py` is a check nobody reads.
    """
    out: set[str] = set()
    # **The build the class page prints in parentheses** -- "Fighter
    # (Weaponmaster)" -- is a key in `chargen.BUILDS` and inside 76 `cf:` refs,
    # so it is load-bearing exactly as a class name is. Read from the source's
    # own Name column, which is where the slug came from in the first place.
    with (
        sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True) as src,
        contextlib.suppress(sqlite3.OperationalError),
    ):
        for (name,) in src.execute("SELECT Name FROM Class"):
            for word in re.findall(r"[a-z']{3,}", (name or "").lower()):
                out.add(word)
    db = game()
    # **A weapon's name is mechanics**, which this project settled long before
    # #339: thirty of them are in `sanitise.RULES_TERMS` and none has an entry
    # in `names.json` at all. So the `slug` column joins the type words -- and
    # that is only askable now that the slug is a column rather than the ref.
    for table, column in (("monster", "kind"), ("monster", "role"),
                          ("monster", "origin"), ("class", "name"),
                          ("weapon", "slug")):
        try:
            rows = db.execute(f"SELECT DISTINCT {column} FROM {table}").fetchall()
        except sqlite3.OperationalError:
            continue  # The table or column is absent from an older build.
        for (value,) in rows:
            low = (value or "").lower().strip()
            # **The whole value as well as its words.** The word split is what
            # takes the parentheses off a stat block's sub-type, and it also
            # takes a hyphen off -- so a hyphenated weapon slug went in as two
            # halves and the hyphenated word itself was still reported.
            if len(low) >= 3:
                out.add(low)
            for word in re.findall(r"[a-z'-]{3,}", low):
                out.add(word.strip("-"))
    for ref, entry in localisation().items():
        if ref.startswith("r") and ref[1:].isdigit():
            for word in re.findall(r"[a-z']{3,}", (entry.get("name") or "").lower()):
                out.add(word)
    return out


def _components(names: dict, rules: set[str]) -> dict[str, list[str]]:
    """Words that only ever appear *inside* a printed name, never as one.

    The whole-name index cannot reach these by construction -- `_hits` looks a
    phrase up and the phrase is never a key -- so a subclass, a build, a named
    entity or a hyphenated half is invisible to every other pass. **6,801 words
    of six characters or more are in this shape.** #338.

    Four tests, and the third is what makes it usable at all:

    * **long enough**, `SHORTEST`, as the lone-word rule already requires;
    * **rare enough**, naming at most `COMMON_ENOUGH` printed names, because a
      word inside hundreds of names identifies none of them;
    * **not an ordinary word**, inflections included -- `sanitise.ordinary`.
      Without the inflections this reports 141 words and nearly all of them are
      English that some printed name happens to contain;
    * **not a type word** the engine asks by -- `_type_words`.

    Measured on this corpus: 141 candidates present in the tree before the
    inflection test, 46 after it, 11 after the type words, and the remainder are
    the ref-naming issues #339 and #341 already describe, held in `DEFERRED`.
    """
    whole = {(e.get("name") or "").strip().lower() for e in names.values()}
    inside: dict[str, set[str]] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip().lower()
        for word in re.findall(r"[a-z][a-z'-]*", name):
            if len(word) >= SHORTEST and word not in whole:
                inside.setdefault(word, set()).add(ref)
    types = _type_words()

    def excused(word: str) -> bool:
        # **The possessive comes off before the comparison.** The type list
        # holds `battlemind`; the corpus writes `battlemind's`, which is the
        # form a two-word name leaves behind. Without this the exemption misses
        # every possessive and reports the class names it exists to excuse.
        bare = word
        for suffix in ("'s", "s'", "'"):
            if bare.endswith(suffix) and len(bare) > len(suffix) + 2:
                bare = bare[: -len(suffix)]
                break
        return bare in types or word in types or bare in ALLOWED

    return {
        word: sorted(refs)
        for word, refs in inside.items()
        if len(refs) <= COMMON_ENOUGH
        and word not in rules
        and word not in ALLOWED
        and not excused(word)
        and not ordinary(word)
    }


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

    index, _printed = _index(names)
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
    return columns(index)


#: Columns that hold a word from a small fixed vocabulary -- "Attack",
#: "heavy blade", "standard" -- rather than prose. Checked separately
#: from `spec` because the test can be much stricter: prose has to argue
#: about whether a two-word phrase is a coincidence, and a column whose
#: whole value *is* a printed name has nothing to argue about.
VOCABULARY_COLUMNS = (
    ("power", "kind"),
    ("power", "usage"),
    ("power", "action"),
    ("item", "slot"),
    ("item", "category"),
    ("feat", "tier"),
    ("monster", "role"),
    ("monster", "origin"),
)


#: Values in those columns that match a printed name **and are not one**.
#: Each has been read: it is the fixed word the column is for, and some
#: unrelated row happens to be called the same thing.
REVIEWED = {
    ("power", "action", "move"),      # a monster ability is called Move
    ("power", "kind", "pact"),        # the warlock's, and a card of that name
}


def columns(index: dict[str, list[str]]) -> int:
    """The other place a printed name can sit: a column, not a document.

    `power.kind` is copied verbatim from the compendium and for thirteen
    racial rows it held the **race's printed name** where every other
    one held "Racial". `--specs` never saw it, because it reads `spec`
    and nothing else, so the tracker was green the whole time.

    The test is exact and whole-value: the column's entire contents are
    a name in `names.json`. That still coincides sometimes -- an action
    really is called "move" and a monster ability is called Move, a
    warlock power's kind really is "pact" -- because a one-word printed
    name and a one-word vocabulary word are the same string.

    So the coincidences are listed rather than inferred. `REVIEWED` is
    hand-kept, which the stale lists in `lint.py` are a standing
    argument against -- but it fails the opposite way round. A list of
    things to *ignore* goes wrong by staying quiet; this one goes wrong
    by reporting a value nobody has looked at yet, which is the report
    we want. It only grows when the compendium puts a new word in one
    of these columns.
    """
    db = game()
    found: list[tuple[str, str, str, list[str]]] = []
    for table, column in VOCABULARY_COLUMNS:
        try:
            rows = db.execute(
                f"SELECT DISTINCT {column} FROM {table} WHERE {column} != ''"
            ).fetchall()
        except sqlite3.OperationalError:
            continue  # The column has been renamed or has not been built.
        for (value,) in rows:
            word = (value or "").strip().lower()
            if (table, column, word) in REVIEWED:
                continue
            refs = index.get(word)
            if refs:
                found.append((table, column, word, refs))

    for table, column, _value, refs in found[:40]:
        print(f"{table}.{column}: a value is the printed name of {', '.join(refs[:3])}")
    if found:
        print(f"\n{len(found)} column values are printed names.")
        print("A column is as readable as a spec. Map it to a ref or to "
              "the fixed word the column is supposed to hold.")
        return 1
    print("no printed names in any vocabulary column")
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

    index, printed = _index(names)

    rules = vocabulary()
    parts = _components(names, rules)
    inside = re.compile(r"\b(" + "|".join(
        sorted((re.escape(w) for w in parts), key=len, reverse=True)
    ) + r")\b") if parts else None
    findings: list[tuple[Path, int, str, list[str]]] = []
    quiet: list[tuple[Path, int, str, list[str]]] = []
    #: (file, word) -> the first line it was seen on.
    components: dict[tuple[Path, str], int] = {}
    deferred_seen: set[str] = set()

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
            # The component pass. One alternation over every candidate rather
            # than a pass per word: there are a few thousand and 2,800 files.
            # **Recorded per word and file, not per line** -- one fixture
            # mentions a build name on sixty lines and that is one thing to fix,
            # the same reason `specs` reports per row.
            if inside is not None:
                for found in set(inside.findall(line.lower())):
                    if found in DEFERRED:
                        deferred_seen.add(found)
                        continue
                    components.setdefault((path.relative_to(ROOT), found), n)

    for path, n, name, refs in findings:
        # The printed spelling, not the normalised key -- a reader told the name
        # has a space where the compendium prints a hyphen goes looking for the
        # wrong string.
        shown = printed.get(name, name)
        print(f"{path}:{n}: {shown!r} is the printed name of {', '.join(refs[:3])}")

    for (path, word), n in sorted(components.items()):
        # **"part of", not "is"** -- it is not a whole printed name, and a reader
        # sent looking for a row called that would not find one.
        print(f"{path}:{n}: {word!r} names part of {', '.join(parts[word][:3])}")

    if quiet:
        words = sorted({name for _, _, name, _ in quiet})
        print(
            f"\n{len(quiet)} matches on {len(words)} common words, not reported: "
            + ", ".join(words[:12])
            + (" ..." if len(words) > 12 else "")
        )

    if DEFERRED:
        print(f"\n{len(deferred_seen)} of {len(DEFERRED)} deferred slugs still present:")
        for word in sorted(deferred_seen):
            print(f"  {word}: {DEFERRED[word]}")

    stale = sorted(set(DEFERRED) - deferred_seen)
    if stale:
        print(
            f"\n{len(stale)} deferred slug(s) no longer appear, so the work landed "
            "and the entry should go: " + ", ".join(stale)
        )

    if findings or components:
        whole = f"{len(findings)} whole" if findings else ""
        part = f"{len(components)} partial" if components else ""
        print(f"\n{', '.join(x for x in (whole, part) if x)} leaks. "
              "Names belong in localization/, not in the tree.")
        return 1
    if stale:
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
