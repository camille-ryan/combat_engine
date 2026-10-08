#!/usr/bin/env python
"""Has a printed name got into the repository?

    uv run scripts/leaks.py             every tracked file
    uv run scripts/leaks.py --specs     every spec an author is shown
    uv run scripts/leaks.py --history   commit messages, and issue text

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
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from combat_engine.db import ROOT, SOURCE, game, localisation
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
    # Found by `_components` the moment it stopped deferring to a
    # `common_word` seat. The same shape as the entry above and the same fix:
    # it is a `BUILDS` key, `c.build(...)` gates content rows on it, and
    # renaming it is the re-model rather than an edit. #462 found it, #339
    # removes it.
    "thunderborn": "#339 -- a sub-option name used as a BUILDS key",
}

#: Read once each. `_components` asks them per candidate word.
_DICT: frozenset[str] | None = None
_TRUSTED: frozenset[str] | None = None

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
        key = " ".join(_fold(name).replace("-", " ").split())
        index.setdefault(key, []).append(ref)
        printed.setdefault(key, name)
    return index, printed


def _fold(text: str) -> str:
    """Letters outside ASCII, made matchable on both sides.

    **The hyphen bug again, and much larger.** `_hits` captures prose with
    `[a-z']`, which is ASCII, so a printed name holding any other letter was
    **unmatchable by construction** -- not missed through a judgement call. 332
    of 32,371 printed names hold one, and 323 of those are the *curly*
    apostrophe the compendium actually prints, U+2019, where this file's regex
    reads the straight one. Six hold `û` and five `é`.

    That is a hole in both halves of the check at once: neither a tracked file
    nor a spec could be caught printing any of those 332 names. Found by reading
    a monster ability brief that printed an accented name at a full `--specs`
    run reporting clean.

    Normalising is the same remedy the hyphen took, and for the same reason: a
    file writing the straight apostrophe where the compendium writes the curly
    one is just as much a leak, so folding catches that too.
    """
    import unicodedata

    # Escaped rather than written literally: ruff's RUF001 refuses an ambiguous
    # character in a string, and it is right to -- these are invisible in a diff.
    swapped = text.replace("\u2019", "'").replace("\u02bc", "'")
    flat = unicodedata.normalize("NFKD", swapped)
    return "".join(ch for ch in flat if not unicodedata.combining(ch))


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
                # **And the halves of a hyphenated one.** The regex above keeps
                # the hyphen, so a two-part slug went in whole and its parts did
                # not -- and a *part* is what the component pass reports, which
                # is the only reason this list exists. One such slug was still
                # being flagged after the whole value was added.
                for part in word.split("-"):
                    if len(part) >= 3:
                        out.add(part)
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

    # **`rules` does not get to overrule the three tests above it**, and that
    # was silencing this walk for exactly the words it exists to find.
    #
    # `vocabulary()`'s fourth source is "every word appearing on at least a
    # handful of compendium pages", and #337 already found that route hands
    # proper nouns to this script as English. The guard it added -- in
    # `build._common_words` -- asks whether a word is the **whole** printed
    # name of a few rows, so a word that only ever appears *inside* a longer
    # name is never tested and keeps its seat. Measured: 93 constituent words
    # are seated that way, and **26 of them pass every other test here** and
    # were excluded by `word not in rules` alone. All 26.
    #
    # So the seat is evidence about *frequency*, and by this point the walk has
    # already established the word is rare and not an ordinary word in any
    # inflection. Deferring to the seat lets the weaker test win. A word that
    # **is** in a dictionary keeps its exemption, which is what preserves the
    # cases `_common_words`' own comment is careful about -- an ordinary word
    # some row happens to be called.
    #
    # Load-bearing: it reports a sub-option name that has been a `BUILDS` key
    # with this check green since it was written. #462.
    return {
        word: sorted(refs)
        for word, refs in inside.items()
        if len(refs) <= COMMON_ENOUGH
        and word not in _trusted_vocabulary()
        and word not in ALLOWED
        and not excused(word)
        and not ordinary(word)
    }


def _trusted_vocabulary() -> frozenset[str]:
    """`vocabulary()` minus the one source that cannot be trusted here.

    Three of `vocabulary`'s four sources answer "is this ordinary or
    mechanical" honestly: the system dictionary, the engine's own enumerations,
    and the hand-written `RULES_TERMS`. The fourth is **word frequency across
    compendium pages**, and #337 already found that it hands proper nouns to
    this script as English -- a deity is named on every page that invokes it.
    `build._common_words` guards against that by refusing a word that is the
    **whole** printed name of a few rows, which is why a word appearing only
    *inside* longer names is never tested and keeps its seat.
    
    So this walk asks the three it can trust and ignores the fourth. Measured:
    93 constituent words are seated by frequency alone and 26 of them pass
    every other test here.

    **Not simply "is it in a dictionary"**, which was the first attempt and was
    too blunt: it overrode `RULES_TERMS` as well, and re-reported an armour
    band that is deliberately listed there. The corpus half is the untrusted
    one; the hand-written half is the most trusted thing in the file.
    """
    global _TRUSTED
    if _TRUSTED is None:
        from enum import EnumMeta

        from combat_engine.engine import types

        out = {w.lower() for w in RULES_TERMS} | {w.lower() for w in ALLOWED}
        for name in dir(types):
            member = getattr(types, name)
            if isinstance(member, EnumMeta):
                for item in member:
                    if isinstance(item.value, str):
                        out.add(item.value.lower().replace("_", " "))
                    out.add(item.name.lower().replace("_", " "))
        out |= set(_dictionary())
        _TRUSTED = frozenset(out)
    return _TRUSTED


def _dictionary() -> frozenset[str]:
    """The system word list, on its own.

    Deliberately **not** `vocabulary()`, which is this plus the corpus's own
    word frequencies plus the engine's enums -- and the corpus half is what
    seats a proper noun. The question `_components` asks is only "does a
    dictionary have this word", so only the dictionary is asked.

    Absent on a machine without one, in which case every word looks invented
    and the report gets noisier rather than wrong -- the same direction
    `vocabulary` takes for the same reason.
    """
    global _DICT
    if _DICT is None:
        from combat_engine.etl.sanitise import DICTIONARY

        words: set[str] = set()
        if DICTIONARY.exists():
            words = {
                line.strip().lower()
                for line in DICTIONARY.read_text(errors="ignore").splitlines()
                if line.strip()
            }
        _DICT = frozenset(words)
    return _DICT


def tracked() -> list[Path]:
    """Every file that ships -- **including the ones not committed yet.**

    This was a bare `git ls-files`, which lists the *index*, so a brand-new file
    was invisible until it had been committed. That is exactly backwards for the
    way this check is used: a wave writes new files, the session runs `leaks.py`
    before committing them, and the one thing it most needs to look at is the only
    thing it could not see. A printed race name shipped in a new file's docstring
    on that blind spot and only surfaced on the next round's run.

    `--cached --others --exclude-standard` is the index plus untracked files minus
    anything `.gitignore` covers -- so `data/` and `localization/` stay out, which
    they must.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
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
    # **Every table with a `spec` column, which this list was not.** `trap`
    # (631 specs) and `racial_trait` (151) were absent, so this walk printed
    # "no printed names in any spec" over 782 specs it had never read -- a
    # check that cannot fail, which `scripts/CLAUDE.md` names as the same fault
    # as a check that is too generous.
    #
    # Both are dormant rather than harmless: `spec.py:_render` has no `t:` or
    # `rt:` branch, so no author is handed either brief today. Adding those
    # branches before this walk was watching would have shipped names on the
    # first day. #415, #419.
    for table in ("power", "monster_power", "class_feature", "companion",
                  "item", "item_block", "feat", "race",
                  "trap", "racial_trait"):
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
    # **`weapon.slug` is deliberately absent, and `racial_trait` has no slug to
    # add.** The asymmetry is the point and is worth leaving written down: a
    # weapon's name is mechanics -- thirty are in `sanitise.RULES_TERMS` and
    # none has a `names.json` entry -- so that column cannot hold a name by
    # construction. A racial trait's label is an ordinary printed name, its slug
    # held it on 147 of 151 rows, and adding the column here duly went red on
    # 17 of them. Nothing read the column, so it was dropped rather than
    # exempted; see the note on the table in `etl/build.py`. #433.
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


def history() -> int:
    """The third walk: commit messages, and issue text with `--issues`.

    **The root `CLAUDE.md` names six places a printed name must not go** -- a
    comment, a docstring, a variable, a **commit message**, an **issue**, a
    column -- and said "`scripts/leaks.py` checks both halves" while checking
    four. Nothing read a message and nothing read an issue. Measured when this
    was filed, by the same `_hits` + `_identifies` pair the file walk uses:

        commit messages                665     names found    22
        issues (title, body, comments) 447     names found    45

    So the issue half is the larger one, and it is the only one of the six
    where a find has a **remedy**: a commit message is append-only, an issue
    is editable. (GitHub keeps edit history, so a scrub is a correction and
    not an erasure.)

    ## Why a historical find is information rather than a failure

    `#438` imported 90 printed build-option names into `names.json`, and
    commit messages written weeks earlier **became** findings the moment the
    index grew. A tracked file can be reworded -- that commit reworded 13
    comments -- and a message that is already pushed cannot. So this exits
    non-zero only on `--issues`, where something can be done, and reports the
    commit half as a count.

    **The gate that matters is pre-commit**, which is the one moment a message
    is editable, and that is what `--staged` is for.

    ## What this walk does not catch, stated because it bit twice today

    `identifies` waives a multi-word phrase unless it has three or more
    non-stopwords or one word that is not a dictionary word. So
    `<ordinary word> of <ordinary word>` is waived by design -- its own
    docstring says *"a genuine two-word name made of two ordinary words is now
    missed. That is the trade, and the ETL scrubber is the other line of
    defence."*

    **For a message or an issue there is no other line of defence.** Four
    printed item names of that exact shape passed this gate in a draft today
    and were caught only because somebody remembered reading them out of
    `localisation()` ten minutes earlier. This walk would have passed them
    too. It is a floor, not a ceiling. #447.
    """
    names = localisation()
    if not names:
        print("localization/names.json is missing.", file=sys.stderr)
        return 0
    index, _printed = _index(names)
    rules = vocabulary()

    def scan(text: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for line in text.splitlines():
            for name, refs in _hits(line, index):
                if _identifies(name, refs, rules, line):
                    out.append((name, refs[0]))
        return out

    staged = "--staged" in sys.argv
    if staged:
        # The pre-commit gate: the message being written, nothing else.
        path = ROOT / ".git" / "COMMIT_EDITMSG"
        text = path.read_text() if path.exists() else ""
        found = scan(text)
        for _name, ref in found:
            print(f"  the staged message names {ref}")
        print(f"\n{len(found)} name(s) in the staged commit message")
        return 1 if found else 0

    log = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x01"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    ).stdout
    messages = [m for m in log.split("\x01") if m.strip()]
    hits: dict[str, list[tuple[str, str]]] = {}
    for entry in messages:
        sha, _, body = entry.partition("\x00")
        found = scan(body)
        if found:
            hits[sha.strip()[:9]] = found
    print(f"  {len(messages)} commit message(s) read")
    for sha, found in list(hits.items())[:10]:
        refs = ", ".join(sorted({r for _n, r in found}))
        print(f"  {sha} names {refs}")
    print(
        f"\n{len(hits)} commit message(s) name something in the index"
        + ("  -- append-only, so this is a count rather than a gate"
           if hits else "")
    )

    if "--issues" not in sys.argv:
        print("  (pass --issues to read the tracker too; it needs the network)")
        return 0

    raw = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "600",
         "--json", "number,title,body,comments"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if raw.returncode:
        print("  gh could not read the tracker; skipped", file=sys.stderr)
        return 0
    issues = json.loads(raw.stdout or "[]")
    bad: dict[int, set[str]] = {}
    units = 0
    for issue in issues:
        spots = [issue.get("title") or "", issue.get("body") or ""]
        spots += [c.get("body") or "" for c in issue.get("comments") or []]
        for text in spots:
            units += 1
            for _name, ref in scan(text):
                bad.setdefault(issue["number"], set()).add(ref)
    print(f"\n  {len(issues)} issue(s), {units} text unit(s) read")
    for number, refs in sorted(bad.items()):
        print(f"  #{number} names {', '.join(sorted(refs))}")
    print(f"\n{len(bad)} issue(s) name something in the index")
    print("  an issue is editable, which is why this one exits non-zero")
    return 1 if bad else 0


def main() -> int:
    if "--specs" in sys.argv:
        return specs()
    if "--history" in sys.argv:
        return history()
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
    #: The quoted-position pass. Kept apart from `findings` so the two report
    #: separately: a name in running prose and a name in a quoted label are
    #: found by different tests and fixed by different edits.
    quoted_names: list[tuple[Path, int, str, list[str]]] = []
    #: (file, word) -> the first line it was seen on.
    components: dict[tuple[Path, str], int] = {}
    deferred_seen: set[str] = set()

    for path in tracked():
        if path.suffix not in TEXT_SUFFIXES or not path.exists():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        prose = _prose_lines(path, text)
        for n, line in enumerate(lines, 1):
            for name, refs in _hits(line, index):
                where = findings if _identifies(name, refs, rules, line) else quiet
                where.append((path.relative_to(ROOT), n, name, refs))
            if n in prose:
                for name, refs in _quoted(line, index, rules):
                    quoted_names.append((path.relative_to(ROOT), n, name, refs))
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

    for path, n, name, refs in quoted_names:
        shown = printed.get(name, name)
        print(f"{path}:{n}: quotes {shown!r}, the printed name of "
              f"{', '.join(refs[:3])}")

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

    if findings or components or quoted_names:
        whole = f"{len(findings)} whole" if findings else ""
        part = f"{len(components)} partial" if components else ""
        said = f"{len(quoted_names)} quoted" if quoted_names else ""
        print(f"\n{', '.join(x for x in (whole, part, said) if x)} leaks. "
              "Names belong in localization/, not in the tree.")
        if quoted_names:
            print("  A quoted run is a position: `sanitise.cited`, not "
                  "`identifies`. Rewrite the sentence -- most of these are "
                  "comments *about* a name, where a ref says nothing. #461.")
        return 1
    if stale:
        return 1
    print("no printed names in tracked files")
    return 0


#: A quoted or backticked run, which is a **position** rather than prose.
#:
#: **Single quotes are in, and they earned it.** The first version took only
#: backticks and double quotes, which is what this codebase writes -- and the
#: plant test exposed the gap, because `repr()` produces single quotes and the
#: planted name went straight through. Adding the alternation found exactly
#: **one** more real name, in a comment quoting a function call, and no false
#: positives: a stray apostrophe pair captures a phrase like `t matter. The
#: elf` and that is simply not an index key.
_QUOTED = re.compile(r"`([^`\n]{3,80})`|\"([^\"\n]{3,80})\"|'([^'\n]{3,80})'")

#: A backticked Python identifier is not a quoted name, and it was the largest
#: false-positive class -- 15 of the first 74 findings. `_fold` drops `_` and
#: `.`, which is right for prose and wrong for code: `_mobile_attack` folds to
#: a two-word phrase that really is a printed name, and so do `prime_shot` and
#: `Weapon.proficiency`.
_CODEY = re.compile(r"[_.(){}\[\]=<>]|::")

#: **The whole quoted run only, and the trade is stated because it is real.**
#:
#: A run *containing* a name is missed: `etl/feat.py` quotes a four-word phrase
#: whose first two words are a class feature, and no whole-run lookup resolves
#: that. Sub-spans were tried and measured:
#:
#:     whole run only   52 findings
#:     max 3 words      46      max 6 words   86
#:     max 4 words      53      max 8 words  105
#:
#: No knee in the curve, and reading the extra findings says why: **this
#: codebase quotes the card's printed rules text in docstrings constantly**,
#: and rules text contains mechanic phrases that collide with printed names.
#: Three of the four extra findings at a four-word cap were quoted *rules
#: text* -- a resistance line, a terrain line, a vulnerability line -- where
#: the colliding phrase is a mechanic and the quote is correct. So sub-spans
#: bought one real miss and three false accusations, and a word cap does not
#: separate a label from a sentence.
#:
#: The other fix tried and refused: waive a phrase whose every word is a rules
#: term rather than a dictionary word. It waives the resistance line correctly
#: and also waives two **confirmed** printed names, which is loosening an
#: instrument to make a number look better.
_WHOLE_RUN_ONLY = True


def _prose_lines(path: Path, text: str) -> set[int]:
    """Line numbers a human wrote *about* the code, rather than code.

    **Not every quoted run in a `.py` file**, and that restriction is measured:
    about seven of the findings were rules vocabulary used as a code literal --
    a zone's `difficult=` label, a `c.may()` prompt, an `OATH` constant -- and
    those are mechanics that must stay waived. A string literal is the engine
    saying a thing; a comment or a docstring is somebody explaining it, and
    only the second is a position that names a row.

    Markdown is prose throughout. Python is `tokenize` for comments plus `ast`
    for docstrings, because those are the two a human writes in and neither can
    be told from a literal by a regex that does not know about string nesting.
    """
    if path.suffix.lower() in {".md", ".txt"}:
        return set(range(1, text.count("\n") + 2))
    if path.suffix.lower() != ".py":
        return set()

    import ast
    import io
    import tokenize

    out: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                out.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def _quoted(
    line: str, index: dict[str, list[str]], rules: set[str]
) -> list[tuple[str, list[str]]]:
    """Printed names sitting in a quoted run, which `_identifies` waives.

    **The fourth walk, and it exists because `leaks.py` was green over about
    forty-five of them.** `identifies` waives a two-word name made of two
    ordinary words and says why -- *"two ordinary words in a row is chance
    [...] reporting them taught the reader to skim"* -- which is right for
    running prose. Inside quotes it is not chance: somebody is naming a thing.

    That is the distinction `sanitise.cited` is written from, and every caller
    of it was in the ETL reading compendium HTML. This is the first one pointed
    at our own text.

    `cited` omits the waivers `identifies` applies *first* -- a class's name, a
    base weapon's, a race's on a line that says it is one -- so they are
    applied here. Without them a base weapon came back as a finding by
    construction.
    """
    from combat_engine.etl.sanitise import (
        cited,
        class_names,
        names_a_race,
        weapon_names,
    )

    classes, weapons = class_names(), weapon_names()
    found: list[tuple[str, list[str]]] = []
    for match in _QUOTED.finditer(line):
        inner = next(g for g in match.groups() if g is not None)
        if _CODEY.search(inner):
            continue
        words = re.findall(r"[a-z']+", _fold(inner.lower()))
        if not words:
            continue
        # The whole run, never a span inside it -- see `_WHOLE_RUN_ONLY`. A
        # quoted sentence simply is not an index key, so no length cap is
        # needed to exclude one.
        phrase = " ".join(words)
        refs = index.get(phrase)
        if not refs or _identifies(phrase, refs, rules, line):
            continue
        if phrase in classes or phrase in weapons or phrase in ALLOWED:
            continue
        if names_a_race(phrase, line) or not cited(phrase, rules):
            continue
        found.append((phrase, refs))
    return found


def _hits(line: str, index: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    """Every name appearing in this line, as a whole word sequence.

    Built from the line's own word n-grams rather than by trying 17,000
    regexes -- one pass over the line instead of one pass per name.
    """
    out: list[tuple[str, list[str]]] = []
    # Within runs of prose only. Punctuation is a boundary -- a method
    # signature is not a sentence, and reading across the opening bracket
    # made every `def <verb>(self` pair look like a two-word name.
    # Folded the same way the index is, so an accented or curly-apostrophe
    # name is reachable at all. See `_fold`.
    for run in re.findall(r"[a-z'](?:[a-z' -]*[a-z'])?", _fold(line.lower())):
        words = re.findall(r"[a-z']+", run)
        for size in range(min(6, len(words)), 0, -1):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size])
                if phrase in index:
                    out.append((phrase, index[phrase]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
