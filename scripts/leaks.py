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
import unicodedata
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

#: Specs whose hit is a **positional heading**, per `(table, ref)`, with the
#: reason. The same discipline as `DEFERRED` above and for the same reason: a
#: listed row that stops hitting is a failure, because the entry has gone
#: stale, and a row that is not listed is a failure because it is new.
#:
#: Why these are not leaks, which is the part worth not re-deriving. A build's
#: class page labels a "choose one of the following" group by **where it
#: falls** -- the heading over the nine domain features is the words *level 5
#: domain feature* -- so `identifies` sees a four-word phrase, finds no word
#: invented, and reports it on length alone. The feat below prints the same
#: four words meaning *whichever of the nine the character took*, so the
#: heading's ref is not what the sentence means: substituting it would be
#: **wrong**, not merely unnecessary. The group's ref names the heading; the
#: nine sub-options under it are the rows a feat is gated on.
#:
#: So the matcher is right to find them and the swap would be wrong, which is
#: why this is a baseline rather than a widening of `identifies`. #494 set a
#: budget ceiling on tuning the name search and this is the cheap side of it.
#: Found by #584, which imported the nineteen classes that had never had their
#: features read -- the headings did not exist to collide with before.
SPEC_KNOWN = {
    ("feat", "f3589"): "#584 -- a positional group heading, not the row meant",
    ("feat", "f3590"): "#584 -- a positional group heading, not the row meant",
    ("feat", "f3591"): "#584 -- a positional group heading, not the row meant",
}

#: Read once each. `_components` asks them per candidate word.
_DICT: frozenset[str] | None = None
_TRUSTED: frozenset[str] | None = None

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", "localization"}

# Longest printed name, in words, set by `_index`. Read by `_hits` to size
# its n-gram window. A literal here left every name above the literal
# unreachable, silently -- see `_index`.
_NGRAM_CAP = 1

#: Names holding punctuation, keyed by first segment -> (all segments, key).
#: Reported when every segment is on the line. Set by `_index`; see
#: `_segments` for why a name cannot simply be one phrase.
_SEGMENTED: dict[str, list[tuple[tuple[str, ...], str]]] = {}

#: The same names as a flat key set, and the longest of them in words.
#: `_hits`'s second pass needs a span across segments, not within one.
_SEGMENTED_KEYS: frozenset[str] = frozenset()
_NGRAM_SPAN = 1
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

    **And a third time, for every other punctuation mark.** A hyphen was not
    special: `_hits` builds its phrases with `[a-z']+` joined by single spaces,
    so *no* key holding a character outside that class could ever compare
    equal. 638 keys were unmatchable and **247 of them fired nothing at all**
    when planted verbatim in plain prose -- 150 because the printed name holds
    a comma or a parenthesis, the rest a colon, slash, ampersand, quote or
    bracket. Found by planting a name in a new table's spec and watching
    `--specs` report clean, which is the plant-test rule earning its keep: the
    plant was a bad one, and chasing why found a real gap rather than a bad
    plant. #493.

    So the key is now built the *same way `_hits` builds a phrase*, which is
    the invariant that was missing all three times. Collapses 11 keys onto 10
    and loses nothing -- both refs land on the one key.

    Returns the lookup, and beside it the printed spelling of each key, so a
    finding can quote what the compendium prints rather than the normalised
    form a reader would then go looking for in vain.
    """
    global _NGRAM_CAP, _SEGMENTED, _SEGMENTED_KEYS, _NGRAM_SPAN
    index: dict[str, list[str]] = {}
    printed: dict[str, str] = {}
    segmented: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    widest = 1
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip().lower()
        if len(name) <= 2:
            continue
        segments = _segments(name)
        if not segments:
            continue
        key = " ".join(segments)
        index.setdefault(key, []).append(ref)
        printed.setdefault(key, name)
        if len(segments) > 1:
            segmented.setdefault(segments[0], []).append((segments, key))
        widest = max(widest, *(len(seg.split()) for seg in segments))
    _SEGMENTED = segmented
    _SEGMENTED_KEYS = frozenset(key for segs in segmented.values() for _, key in segs)
    # Both derived, never literals. A fixed `6` left every 7-word name
    # unreachable -- the same by-construction hole as the hyphen, counted a
    # third time. `_NGRAM_CAP` sizes the within-a-run pass, so it is the
    # longest **segment**; `_NGRAM_SPAN` sizes the across-punctuation pass,
    # so it is the longest whole **name**.
    _NGRAM_CAP = widest
    _NGRAM_SPAN = max((len(k.split()) for k in _SEGMENTED_KEYS), default=1)
    return index, printed


def _segments(name: str) -> tuple[str, ...]:
    """A printed name as the word-runs `_hits` can actually match.

    **Punctuation is a boundary on the line and so has to be one here.**
    `_hits` captures runs with `[a-z' -]` precisely so it does not read across
    an opening bracket -- without that, every `def <verb>(self` pair looked
    like a two-word name. The consequence nobody drew: a *name* holding a
    comma, parenthesis, colon, slash or ampersand can never appear inside one
    run either, so no amount of normalising the key reaches it. Normalising
    the key alone moved the unreachable count 247 -> 229.

    So a name is a **tuple of segments**, and `_hits` reports it when every
    segment is on the line. That keeps the no-reading-across-brackets rule
    exactly as it was -- each segment still has to sit inside a single run --
    while making the whole name reachable. #493.
    """
    folded = _fold(name).replace("-", " ")
    return tuple(
        " ".join(words)
        for chunk in re.split(r"[^a-z' -]+", folded)
        if (words := re.findall(r"[a-z']+", chunk))
    )


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


#: Ref shapes, as `scripts/spec.py` writes them. Deliberately a second copy
#: rather than an import: `spec.py` is an instrument and this is an
#: instrument, and the one thing worse than two copies of a regex is a gate
#: that silently stops gating because the thing it watches changed shape.
#: `--cited` prints its own count of refs found, so a divergence shows up as
#: a number falling rather than as a clean run.
CITED_REF = re.compile(
    r"\b(?:cf|rt|comp|b|t|q):[A-Za-z0-9][A-Za-z0-9:_.-]*"
    r"|\b[pmifrax]\d+(?:[apx]\d+)?(?::augment\d+)?\b"
)

#: Below this many characters a name is not evidence of anything -- it is a
#: word. The multi-word rule below does the real work; this only keeps
#: three-letter names from matching inside other words.
CITED_MIN = 4


#: How many consecutive words of a module's prose, in a tracked file, count
#: as quoting the adventure.
#:
#: Eight. **This is not a vocabulary question**, which is what makes the
#: check different in kind from every other pass in this file: an eight-word
#: run is either copied or coincidence, and coincidence does not survive
#: eight words of somebody else's sentence. So it needs none of the waivers
#: the tree-wide walk needs, and has none of #494's blind spot.
MODULE_RUN = 8

#: A module name shorter than this is not evidence -- it is a word.
#:
#: Four, lowered from five after five was found to miss a four-letter
#: character name that was sitting in three tracked files. The guard
#: against a false positive is not the length on its own: the name has to
#: be capitalised in the module's own cast list *and* match on a word
#: boundary, so an ordinary lowercase word never reaches this test.
MODULE_NAME_MIN = 4


#: The typeset punctuation a page uses where the database uses ASCII.
#:
#: The same table and the same reason as `ingest._fold`: a book is typeset
#: and a database column is typed, so a run that is word-for-word identical
#: fails to match on punctuation alone.
#: Written as escapes rather than literals because `ruff`'s RUF001 refuses
#: an ambiguous quotation mark in source, which is the right call for every
#: other file and merely inconvenient here. Ligatures are left to NFKC
#: below, which already maps them.
_MODULE_CURLY = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2014": "-", "\u2013": "-", "\u00ad": "",
})


def _module_words(text: str) -> list[str]:
    """The words of a run, with the two corpora spelled the same way.

    **The fold is not cosmetic and leaving it out cost the rules filter most
    of its reach.** `[a-z']+` takes a straight apostrophe and not a curly
    one, and the pages are full of curly ones -- so a possessive tokenised
    as *two* words off a page and as *one* off the database, every shingle
    containing it came out different, and `_rules_runs` could not waive a
    rules formula it held verbatim. #917.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_MODULE_CURLY)
    return re.findall(r"[a-z']+", folded.lower())


def _module_runs(text: str) -> set[str]:
    words = _module_words(text)
    return {
        " ".join(words[i:i + MODULE_RUN])
        for i in range(max(0, len(words) - MODULE_RUN + 1))
    }


#: Runs that are mechanical vocabulary rather than an adventure's prose.
#:
#: **The premise "coincidence does not survive eight words" is true for
#: narrative and false for a rules formula**, which is the same correction
#: `--cited` needed: its first run reported 1,379 hits, 287 of them because
#: a monster ability's printed name is very often a generic combat phrase.
#: Here the first run reported four, three of them phrases like "hit points
#: equal to your healing surge value" -- in the adventure because
#: `importer.read_aloud` takes *all* italic text and a stat block's flavour
#: line is italic too.
#:
#: Most are removed by checking the run against the rules corpus in
#: `game.db`, which every contributor has.
#:
#: **The baseline that used to sit here is empty, and that is the result of
#: fixing #909 rather than a decision to trust the gate more.** Three runs
#: were waived: a generic action phrase and two halves of a rulebook title.
#: All three were in the module corpus only because `importer.read_aloud`
#: filtered italic blocks by length alone, so a publisher's credits line
#: and the pre-generated character sheets at the back of the book arrived
#: as the adventure's prose. The extractor now drops both -- 80 blocks to
#: 71 -- and with the waivers deleted this check is **clean on its own
#: terms**, verified by emptying the dict before removing it.
#:
#: Two things worth keeping from the old note, because both will come back:
#:
#: * the waived phrases are still in a tracked plan from 2026-10-07, so if
#:   an extractor regression ever puts a product name back in the corpus
#:   this check goes red *there*. That is the gate working. The fix is the
#:   extractor, which is what #909 was, and not a new waiver.
#: * a baseline here must be **matched as a substring, not as a whole
#:   run**. Keyed exactly, a neighbouring eight-word window of the same
#:   phrase slipped straight through: the title was caught one word along
#:   as a window containing neither title in full. Shingles overlap, so an
#:   exact key only ever silences one of them.
#: **#917 put two entries here and then took them out again, and why is
#: the useful part.** Adding `pages/*.txt` took the corpus from 6,493 runs
#: to 43,210 -- and the raw pages are not length-filtered the way
#: `read_aloud` is, so the material `#909` removed at the extractor came
#: back by the new route: the book reprints **pre-generated characters** at
#: the back, and their class-feature text is rules prose that five content
#: files state as a mechanic.
#:
#: Waiving it here would have meant **writing a printed class-feature name
#: into this file** -- the run is the feature's name followed by its
#: once-per-encounter limit, and there is no distinctive fragment that
#: omits the name. A baseline entry spelling it would have been the exact
#: leak this gate exists to catch, in the gate.
#:
#: So the filter was widened instead: `_rules_runs` now reads the
#: localisation's `rules_text` as well as `game.db`'s `spec`, which waives
#: all four runs by holding them verbatim and names nothing. That is the
#: same preference the note above states -- fix the corpus, not the
#: verdict -- reached from the other direction.
MODULE_BENIGN: dict[str, str] = {}


#: A trademark, registered-mark or copyright sign. **The mark and not the
#: publisher's name**, which is the whole point: keying this on the company
#: or the product would put that name in a tracked file to keep names out of
#: tracked files, which is the joke #447's own section keeps making about
#: itself. A glyph carries no name and generalises to any book.
_BOILERPLATE = re.compile(r"[\u2122\u00ae\u00a9]")


def _without_boilerplate(text: str) -> str:
    """The page with its publisher and legal lines dropped.

    `#917` added `pages/*.txt` and closed an 85% blind spot, but the raw
    pages are not filtered the way `read_aloud` is -- so what `#909` removed
    at the extractor came back by a new route. A product title or a credits
    line in the corpus means any tracked file naming it goes red, which is a
    false positive on a legitimate row, and this project treats that as
    worse than a miss.

    **By line and not by page**, which the measurement decided rather than
    taste. 29 of the one module's 154 pages carry a mark somewhere -- 19% of
    the book, including running prose that merely mentions a trademark -- so
    dropping pages would cut the adventure itself. By line it is 86 of
    10,297, 0.8%, for 486 runs.

    **Two things #921 asked for are not here to drop, measured.** Its
    "reprinted pre-generated characters, pages 130-141" is the back-cover
    blurb and the copyright notice on this module, not character sheets; and
    no stat-block source citation is findable at all -- not by any book
    title, nor by `First appeared`/`Source:`, while `Level N ... XP` finds
    the 20 stat-block pages themselves. So the category that *is* in the
    corpus is the publisher and legal copy, which is `#909`'s credits-line
    case arriving by the pages route exactly as that issue predicted.
    """
    return "\n".join(line for line in text.splitlines()
                      if not _BOILERPLATE.search(line))


def _rules_runs() -> set[str]:
    """Every eight-word run the rules themselves use.

    Two sources, and the second was added by #917 because the first is not
    enough. `spec` is the sanitised text column on the tables that carry
    prose -- about 268,000 runs. The localisation's `rules_text` is the
    *printed* wording of the same rules, which is a different corpus: 25,413
    fields and about 627,000 runs.

    **The gap between them was load-bearing.** An adventure reprints
    pre-generated characters, so a class feature's printed limit is in the
    module corpus -- and five content files state that same limit as a
    mechanic. `spec` does not hold it: measured, the phrase appears in **no
    column of any of the 25 tables** in `game.db`, because that feature's
    prose is not ingested. `rules_text` holds all four runs verbatim, so
    widening here waives them without a prose baseline -- which matters more
    than usual, since the only baseline key that could have matched would
    have had to spell the feature's printed name. See `MODULE_BENIGN`.

    `localisation()` answers `{}` when the file is absent, which costs
    nothing: `modules/` is git-ignored too, so a checkout without one has no
    module corpus to compare against and the caller says so.
    """
    out: set[str] = set()
    with contextlib.suppress(sqlite3.Error):
        db = game()
        for table in ("power", "monster_power", "class_feature", "item"):
            cols = [r[1] for r in db.execute(f"pragma table_info({table})")]
            if "spec" not in cols:
                continue
            for (spec,) in db.execute(f"select spec from {table}"):
                out |= _module_runs(spec or "")
    # The printed wording, which is what an adventure reprints and what the
    # sanitised `spec` above has had the flavour taken out of.
    for fields in localisation().values():
        for key in ("rules_text", "description"):
            text = (fields or {}).get(key)
            if isinstance(text, str) and len(text) > 40:
                out |= _module_runs(text)
    return out


def _module_material() -> tuple[set[str], dict[str, str], int]:
    """Every run of prose and every proper name the local modules hold.

    Read from `modules/`, which is git-ignored -- so this returns nothing on
    a fresh clone and the caller says so rather than passing.
    """
    runs: set[str] = set()
    names: dict[str, str] = {}
    seen = 0
    for module in sorted((ROOT / "modules").glob("*/module.json")):
        seen += 1
        raw = json.loads(module.read_text())
        for scene in raw.get("scenes", ()):
            for key in ("sets", "brief"):
                if scene.get(key):
                    runs |= _module_runs(str(scene[key]))
            people = [n.get("name", "") for n in scene.get("npcs", ())]
            for who in (*people, scene.get("name", "")):
                who = str(who).strip()
                # A proper noun rather than a role word: at least one
                # capitalised word. A cast entry written as "the halfling by
                # the door" is the module's own paraphrase and names nobody.
                caps = [w for w in who.split() if w[:1].isupper()]
                if caps and len(who) >= MODULE_NAME_MIN:
                    names[who] = module.parent.name
        aloud = module.parent / "read-aloud.json"
        if aloud.exists():
            for blocks in json.loads(aloud.read_text()).values():
                for block in blocks:
                    runs |= _module_runs(str(block))
        # **The book's own pages, which are most of it.** The two sources
        # above are what the *importer* chose to keep -- scene briefs and
        # italic read-aloud -- and `pages/` is the whole text it read them
        # out of. Leaving them out meant this gate held about 15% of the
        # material it exists to protect, so a session quoting a page into a
        # docstring was found by hand rather than by this. #917.
        #
        # Every page is filtered against `_rules_runs` exactly as the rest
        # is, which is what keeps the stat blocks printed in an adventure
        # from flagging the whole content tree that legitimately quotes
        # them.
        for page in sorted((module.parent / "pages").glob("*.txt")):
            runs |= _module_runs(_without_boilerplate(page.read_text(
                errors="replace")))
    # Mechanical vocabulary is not this adventure's prose. See
    # `MODULE_BENIGN` for why this is a filter and a short list rather
    # than a looser rule.
    rules = _rules_runs()
    keep = {
        run for run in runs
        if run not in rules
        and not any(benign in run for benign in MODULE_BENIGN)
    }
    return keep, names, seen


def modules() -> int:
    """Has a tracked file quoted an adventure the user owns? #902.

    **The gap this fills is not #494's.** The tree-wide walk compares a file
    against `localization/`, which holds the *compendium's* names -- monsters,
    powers, items, races. An adventure module's characters and places were
    never in the compendium, so a tracked file could carry a published
    adventure's cast and two paragraphs of its prose and every pass in this
    file would report clean. That is not a matcher wanting improvement;
    there was nothing to match against.

    It was found the way these always are. A design document written in this
    repository quoted a dozen character and place names and two paragraphs of
    read-aloud, and `leaks.py` passed it. I scrubbed it by hand, which is the
    work a gate exists to replace.

    Two tests, and the first is the one that matters:

    * **an eight-word run** of a module's own prose appearing in a tracked
      file. Copied or coincidence, and coincidence does not survive eight
      words. No waivers, no vocabulary, no blind spot.
    * **a proper name** out of a module's cast or its scene titles.

    `modules/` is git-ignored, so on a fresh clone there is nothing to check
    and this **skips and says so** -- `scripts/CLAUDE.md` is explicit that a
    quiet skip is not a check.
    """
    runs, names, count = _module_material()
    files = tracked()
    if not count:
        print(
            "no modules under modules/, so there is nothing to check "
            "against -- this machine holds no adventure. SKIPPED, not "
            "passed: a machine with one would have checked it."
        )
        return 0

    findings: list[tuple[Path, int, str]] = []
    for path in files:
        if path.suffix in {".png", ".jpg", ".pdf", ".sqlite", ".lock"}:
            continue
        try:
            text = path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT)
        lines = text.splitlines()
        # One finding per file for the run test: a file that quotes a page
        # usually quotes it more than once, and the fix is the same edit.
        for n, line in enumerate(lines, 1):
            if len(_module_words(line)) < MODULE_RUN:
                continue
            shared = _module_runs(line) & runs
            if shared:
                quote = sorted(shared)[0]
                findings.append((rel, n, f"quotes a module: {quote!r}"))
                break
        for name, where in names.items():
            if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text):
                continue
            at = next((i for i, ln in enumerate(lines, 1) if name in ln), 0)
            findings.append((rel, at, f"names {name!r}, from {where}"))

    for rel, at, what in findings:
        print(f"{rel}:{at}: {what}")
    print(
        f"\n{count} module(s) read: {len(runs):,} prose runs and "
        f"{len(names)} names, against {len(files):,} tracked files"
    )
    if findings:
        print(
            f"{len(findings)} leak(s). An adventure's prose and its cast "
            "belong in modules/, which is git-ignored, not in the tree."
        )
        return 1
    print("no tracked file quotes a module or names its cast")
    return 0


def _stem(word: str) -> str:
    """One word of a printed name, reduced for the mechanical-vocabulary test.

    **Two reductions, and the second was happening by accident.** The line
    this replaced was `w.strip("'s")`, with a comment that described only
    the possessive: *"a feature whose name is `<class>'s <mechanic>` is two
    mechanical words, and leaving the `'s` on made it look invented."*
    True, and `str.strip` does not do that -- it removes **any** run of `'`
    and `s` from both ends, so a plural came back singular too.

    That second effect is **load-bearing and is kept deliberately**.
    Measured before touching it: a strict possessive strip adds **34** hits
    to `--cited`, and all 34 are the *plural of a word already in the
    mechanical vocabulary* -- a monster ability called after the ordinary
    piece of equipment it scatters, a file that defines a helper named
    after it. That is precisely the class `--cited` was tuned to waive
    when its first run reported 1,379 hits, 287 of them monster abilities,
    and re-admitting it in plural form would undo that work. #476.

    So the rule is stated rather than inherited from `strip`'s behaviour:
    a trailing possessive goes, then a trailing plural `s`, and the result
    is only ever used to ask "is this word mechanical". It is **not** used
    to match text -- matching is exact, against the printed name.

    `4,791` of the printed names read differently under the two spellings
    and `1,871` are waived by this and not by a bare possessive strip, so
    the difference is not a corner case.
    """
    word = word.lower()
    if word.endswith("'s"):
        word = word[:-2]
    # A naive plural fold, which is all the vocabulary test needs: it asks
    # membership of a set, so a wrong singular simply fails to match and
    # the name is reported rather than waived -- the safe direction.
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


def cited() -> int:
    """A file may not print the name of a ref it also cites.

    **This is the gate that replaced the construction guarantee**, on
    2026-10-12. Until then an author was shown no name at all, so nothing
    needed checking at the row level; Camille's call was to show the name
    beside its ref so a row can tell when a clause means *itself*, which
    costs the guarantee and buys it back here. See `scripts/spec.py`.

    The question is narrower than the tree-wide walk in `main`, and the
    narrowness is the whole point: that walk compares every file against all
    36,060 names, so it **must** waive a two-ordinary-word name in running
    prose -- `f3`'s name is two words a rules file says all day -- and that
    waiver is #494's blind spot, which has hidden about 44 real names and two
    in the docstrings of the two files whose job is removing them.

    **This docstring instanced `f3`'s name in the clear for its first ten
    minutes, and this check caught it.** Nobody planted it; the sentence
    explaining the blind spot demonstrated the blind spot, which is the trap
    `scripts/CLAUDE.md` names -- the places that explain the rule are the
    places that instance a name to explain it. An unintentional plant is
    better evidence than a deliberate one, so this check is load-bearing on
    the strength of its own first run.

    Scoped to *the refs a file cites*, no waiver is needed. The coincidence
    rate collapses: a file that cites `f3` and also contains that exact
    phrase is not a coincidence worth protecting. So:

    * **a name whose every word is mechanical vocabulary is waived.** This is
      the one that had to be measured rather than reasoned: the first version
      waived nothing and reported **1,379** hits, 287 of them monster
      abilities, because a monster ability's printed name is *very often* a
      generic combat phrase. A file citing that ability and saying "makes a
      double attack" in prose is not leaking anything. So the premise
      "coincidence collapses once the search is scoped to cited refs" is
      **true for invented names and false for mechanical ones**, and the
      remedy is `_trusted_vocabulary()` -- the judgement the tree-wide walk
      already makes, reused rather than reinvented.
    * **everything else is matched exactly, one word or several**, which is
      the case the tree-wide walk cannot see.

    1,379 raw matches, 1,358 waived as mechanical, **21 left -- and every one
    of the 21 was a real leak**, hand-read: five feature names in one SQL
    comment in `etl/build.py`, four race names, two creature species words in
    docstrings that say they are writing around the name while writing it,
    and `cf:ranger-f1`'s name at five sites including `engine/cast.py`. The
    tree-wide walk reported "no printed names in tracked files" over all of
    them, on every run on record.

    One of the 21 was in a **`trigger=` string**, which is the surface the
    page renders -- tier 1 in Camille's #447 ordering, the only tier worth
    building an instrument for. The other 20 were tier 2. Writing the ref
    there is not a downgrade: `refs.py` already holds every ref in prose to
    resolving, so a ref in rendered text becomes the name when
    `localization/` is present and stays a ref when it is not, which is the
    behaviour wanted in both cases.

    **Plant-tested, and the plant is what proves the pair of them.**
    `cf:ranger-f1`'s name written into a content file beside its own ref:
    this goes red naming the file, and the tree-wide walk in `main` prints
    "no printed names in tracked files" in the same run. That is #494's blind
    spot shown twice over in one command, and it is why this is a separate
    instrument rather than more waiver-tuning on the other one.
    """
    names = localisation()
    if not names:
        print(
            "localization/names.json is missing, so there is nothing to check "
            "against. Run: uv run scripts/build.py",
            file=sys.stderr,
        )
        return 0

    mechanical = _trusted_vocabulary()
    hits: list[tuple[str, str, str]] = []
    files = 0
    refs_seen = 0
    for path in tracked():
        if path.suffix not in {".py", ".md", ".js", ".html", ".css", ".json", ".sh"}:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = set(CITED_REF.findall(text))
        if not found:
            continue
        files += 1
        refs_seen += len(found)
        folded = _fold(text).lower()
        for ref in sorted(found):
            name = (names.get(ref) or {}).get("name", "")
            if len(name) < CITED_MIN:
                continue
            if _fold(name).lower() not in folded:
                continue
            words = [_stem(w) for w in re.findall(r"[A-Za-z']+", name)]
            if words and all(w in mechanical for w in words):
                continue
            hits.append((str(path.relative_to(ROOT)), ref, name))

    print(f"  {files} file(s) cite {refs_seen} ref(s)")
    for where, ref, _name in hits:
        # **The name is not printed.** This is a tracked instrument whose
        # output lands in terminals, transcripts and commit messages, and a
        # leak detector that prints the leak to report it is the same
        # mistake one layer up. The ref and the file are enough to find it.
        print(f"  {where} prints the name of {ref}")
    if hits:
        print(f"\n{len(hits)} file(s) name a ref they cite -- fix the file")
        return 1
    print("\nno file prints the name of a ref it cites")
    return 0


#: Every table holding a `spec` column, in one place.
#:
#: **Three walks had their own copy of this list** and the duplication has
#: already cost a real miss: `trap` (631 specs) and `racial_trait` (151) were
#: absent from one of them, so that walk printed "no printed names in any
#: spec" over 782 specs it had never read -- a check that cannot fail. The
#: copies happened to agree when this was factored out; one list is what stops
#: them disagreeing again.
_SPEC_TABLES = (
    "power", "monster_power", "class_feature", "companion", "item",
    "item_block", "feat", "race", "racial_trait", "trap", "disease",
    "associate", "terrain", "build_option", "poison",
)

#: A table with a `spec` column that this walk deliberately does **not**
#: read, and why. Empty is the right state; an entry is a recorded decision
#: rather than an oversight, which is the whole difference #492 is about.
#:
#: The real case it exists for is `#457`'s themes: those specs average
#: 4,712 characters, 6-30x every other table, which makes a per-spec pass
#: impractical on them. A bare list could not say that, so a table left out
#: for a reason looked identical to one nobody had noticed.
_SPEC_EXCLUDED: dict[str, str] = {}


def _spec_columns() -> frozenset[str]:
    """Every table in the built database that actually has a `spec` column."""
    db = game()
    out = set()
    for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"):
        if any(col[1] == "spec" for col in db.execute(
                f"PRAGMA table_info({name})")):
            out.add(name)
    return frozenset(out)


#: The scrub passes in `etl/build.py` that claim to cover every spec table,
#: by the first line of their loop. Named rather than found by line number,
#: which has already gone stale three times in this repo's prose.
_BUILD_PASSES = ("_swap_sub_options", "_cross_reference_rest")


def _build_spec_tables() -> tuple[frozenset[str], list[str]]:
    """`etl/build.py`'s own spec-table tuple, and which passes read it.

    Read with `ast` rather than imported, because the question is what the
    **source** says and importing `etl` to ask it would pull the whole writer
    in for a string literal.

    Returns the tuple's contents and the names of the `_BUILD_PASSES` that
    actually loop over it. A pass that goes back to a literal list of its own
    is the fault this is here to catch, so it is reported as not reading it
    rather than quietly passing.
    """
    import ast

    src = (ROOT / "src" / "combat_engine" / "etl" / "build.py").read_text()
    tree = ast.parse(src)
    listed: frozenset[str] = frozenset()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(
                getattr(target, "id", "") == "SPEC_TABLES"
                for target in node.targets):
            continue
        # **Narrowed, and not only to satisfy `ty`.** `node.value` is any
        # expression: `SPEC_TABLES = _derive()` or a comprehension would make
        # `.elts` an `AttributeError` here, and an exception inside a leak
        # gate is the one way this walk could stop asking its question
        # without anybody choosing that. A non-literal leaves `listed` empty,
        # which the caller already reports as the lists disagreeing.
        if isinstance(node.value, ast.Tuple | ast.List):
            listed = frozenset(
                e.value for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str))
    reading = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in _BUILD_PASSES:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.For) and getattr(
                    inner.iter, "id", "") == "SPEC_TABLES":
                reading.append(node.name)
                break
    return listed, reading


def tables() -> int:
    """Do the lists that decide what gets scrubbed and checked agree?

    **A table with a `spec` column has to be registered in three
    hand-written places** -- two scrub passes in `etl/build.py` so
    `sanitise.scrub` runs over it at import, and `_SPEC_TABLES` here so the
    gate reads it afterwards -- and nothing connected them. The walk prints
    "no printed names in any spec" whether it read a table or not, so a
    missing entry looks exactly like a passing check: silent in both
    directions, which `scripts/CLAUDE.md` names as the same fault as a check
    that is too generous.

    **It had happened three times before this existed.** `trap` (631 specs)
    and `racial_trait` (151) were absent from one walk, which then printed
    its clean line over 782 specs it had never read. Then `disease`,
    `associate` and `terrain` were imported in one day and registered
    nowhere, so three commit messages claimed a clean gate. And
    `_sub_option_names`' own comment says *"every table that carries a
    spec"* and had gone stale against six of them -- in the loop whose note
    warns that a narrow scope "left the narrower scope to go stale against a
    later build".

    **A reconciliation, deliberately not a derivation.** Deriving the list
    from the schema would silently start scrubbing any column somebody names
    `spec`, including one that is not an authoring brief -- a gate that
    changes scope without anyone deciding to, which is how `item.slot`'s 15
    reward titles were missed. So the lists stay hand-written and this makes
    them *agree*, with any difference named. `_SPEC_EXCLUDED` is where a
    deliberate omission says so. #492.
    """
    live = _spec_columns()
    if not live:
        print("no built database to reconcile against", file=sys.stderr)
        return 0

    bad = 0
    covered = set(_SPEC_TABLES) | set(_SPEC_EXCLUDED)
    missing = sorted(live - covered)
    if missing:
        bad = 1
        print(f"{len(missing)} table(s) carry a `spec` column and are in no "
              f"list -- never scrubbed at import, never read by this walk:")
        for name in missing:
            n = game().execute(f"SELECT COUNT(*) FROM {name} "
                               "WHERE spec IS NOT NULL AND spec != ''").fetchone()[0]
            print(f"  {name}: {n} spec(s). Add it to `_SPEC_TABLES` and to "
                  f"both passes in `etl/build.py`, or to `_SPEC_EXCLUDED` "
                  f"with a reason.")

    gone = sorted(set(_SPEC_TABLES) - live)
    if gone:
        bad = 1
        print(f"\n{len(gone)} table(s) in `_SPEC_TABLES` have no `spec` "
              f"column: {', '.join(gone)}. A walk over a column that is not "
              f"there reads nothing and says it is clean.")

    stale = sorted(set(_SPEC_EXCLUDED) - live)
    if stale:
        bad = 1
        print(f"\n{len(stale)} `_SPEC_EXCLUDED` entries name a table that no "
              f"longer has a spec column -- delete them: {', '.join(stale)}")

    listed, reading = _build_spec_tables()
    # **A pass this cannot see is a check that cannot fail**, which is the
    # fault this whole function exists to close -- so it refuses rather than
    # reporting clean. Caught on the first run: `_BUILD_PASSES` named two
    # functions that do not exist, so the build half found nothing, said
    # nothing, and printed the reconciled line over lists it had never read.
    for want in _BUILD_PASSES:
        if want not in reading:
            bad = 1
            print(f"\n`etl/build.py:{want}` does not loop over its own "
                  f"`SPEC_TABLES` -- renamed, moved, or back to a literal "
                  f"list of its own. Until it does, this walk cannot see "
                  f"which tables that pass scrubs and would report the lists "
                  f"reconciled without having compared them.")
    short = sorted((live - set(_SPEC_EXCLUDED)) - listed)
    if short:
        bad = 1
        print(f"\n`etl/build.py:SPEC_TABLES` scrubs {len(listed)} of "
              f"{len(live - set(_SPEC_EXCLUDED))} spec tables. Absent, so "
              f"their specs keep every printed name their pages mention: "
              f"{', '.join(short)}")
    drifted = sorted(listed ^ set(_SPEC_TABLES))
    if drifted:
        bad = 1
        print(f"\n`etl/build.py:SPEC_TABLES` and `leaks._SPEC_TABLES` "
              f"disagree about {', '.join(drifted)} -- one scrubs what the "
              f"other does not read, or the reverse. These two lists are the "
              f"whole of #492 and they have to match.")

    if not bad:
        shown = f", {len(_SPEC_EXCLUDED)} excluded by name" if _SPEC_EXCLUDED else ""
        print(f"the spec tables reconcile: {len(live)} with a spec column, "
              f"all registered for scrubbing and for this walk{shown}")
    return bad


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

    # **Before the walk, not after it.** A walk that is missing a table says
    # "no printed names in any spec" over specs it never read, so the
    # reconciliation has to be able to fail *first* -- otherwise the clean
    # line is printed and the registration fault reads as a pass. #492.
    registered = tables()

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
    #
    # **And it happened again, to three tables in one day.** `disease`
    # (#389), `associate` (#459) and `terrain` (#458) were each imported with
    # a `spec` column and none was added here -- so three commit messages
    # claimed "`leaks.py --specs` clean" over specs this walk had never read,
    # which is the same false pass `trap` and `racial_trait` gave for 782.
    # Proven by planting a printed monster name in a new table's spec: the
    # walk reported clean.
    #
    # The list being hand-kept is the fault. It stays hand-written for the
    # reason `REVIEWED` does -- a derived "every table with a spec column"
    # would silently start checking a column that is not a brief -- but a new
    # table now has to appear in two places and the second is easy to miss.
    # `#492` is that gap, and what would close it: the two lists reconciled
    # against the set of tables that actually have a spec column, with any
    # exclusion named rather than silently allowed.
    for table in _SPEC_TABLES:
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

    seen = {(table, ref) for table, ref, _n, _r in found}
    found = [f for f in found if (f[0], f[1]) not in SPEC_KNOWN]
    for table, ref, _name, refs in found[:40]:
        print(f"{table}.{ref}: prints the name of {', '.join(refs[:3])}")
    if found:
        extra = " (showing 40)" if len(found) > 40 else ""
        print(f"\n{len(found)} specs print another row's printed name{extra}.")
        print("Every one of them is shown to an author verbatim. "
              "See `_cross_reference` in etl/build.py.")
        return 1
    # A baseline that cannot go stale quietly, which is the half a bare
    # allowance gets wrong: an entry whose row has stopped hitting is dead
    # weight and says so, the discipline `DEFERRED` and `todo.py` both apply.
    stale = sorted(k for k in SPEC_KNOWN if k not in seen)
    if stale:
        print("\nSPEC_KNOWN entries no longer hit -- delete them:")
        for table, ref in stale:
            print(f"  {table}.{ref}: {SPEC_KNOWN[(table, ref)]}")
        return 1
    if SPEC_KNOWN:
        print(f"{len(SPEC_KNOWN)} known positional headings, named:")
        for (table, ref), why in sorted(SPEC_KNOWN.items()):
            print(f"  {table}.{ref}: {why}")
    print("no printed names in any spec")
    bad = _self_named_clauses()
    return (registered or bad or _unresolved_citations()
            or _unswapped_names(index) or _entitled_names() or columns(index))


#: `<Head> (<class>, <book>, page <N>)` -- the compendium's inline citation,
#: used where a list of powers carries no `Associated Powers:` heading.
_CITATION = re.compile(
    r"(?m)^([^\n(]*?)\s+\(([a-z][a-z' ]*),[^)]*page\s+\d+\)"
)

#: Refs as this corpus spells them, for the citation walk. A head that is one
#: has been resolved; a head that is prose has not.
_CITED_REF = re.compile(r"^(?:[pmifrw]\d+[a-z]*\d*|cf:[\w-]+|rt:[\w:-]+|x\d*_?[\w]+)$")


def _unresolved_citations() -> int:
    """A printed citation whose head is still prose, in any spec.

    **The narrow question, and it needs no waiver at all** -- which is the
    whole reason it works where the tree-wide walk does not. A parenthetical
    carrying a class, a book and a page number is not prose, so whatever
    stands in front of it is a name the compendium is citing. There is no
    innocent reading in which it is a mechanic, and so nothing here consults
    `identifies`, `_trusted_vocabulary` or any other judgement about the
    words: the **position** has already answered.

    That is `--cited`'s shape, and `--cited` is the one that works -- 20 real
    leaks on its first run where the wide walk had been clean on every run on
    record, *because* a narrow question inherits none of the waivers' blind
    spots. `scripts/CLAUDE.md` states the general rule this is an instance
    of: "nothing tested the **positions** where a waiver does not apply".

    **It asks whether the head is a ref, not whether it resolves.** The
    earlier draft of this looked the head up in the localisation index and
    failed when it resolved -- which is strictly weaker, because a citation
    naming something the index cannot resolve is *still* a printed name in a
    spec and would have passed. Asking for a ref needs no index and catches
    both.

    Four hits in one spec when this was written -- `feat.f1239`, whose list
    prints no heading so `_associated_refs` never ran on it -- and zero after
    `build._cited_members`, which is why this lands as a gate rather than a
    baseline. #624, with #623 as the extraction half.
    """
    db = game()
    found: list[tuple[str, str]] = []
    for table in _SPEC_TABLES:
        try:
            rows = db.execute(
                f"SELECT ref, spec FROM {table} WHERE spec IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        for ref, spec in rows:
            for head, _cls in _CITATION.findall(spec or ""):
                head = head.strip()
                if not head or _CITED_REF.match(head):
                    continue
                found.append((table, ref))

    for table, ref in sorted(set(found)):
        print(f"{table}.{ref}: a printed citation's head is still prose,"
              f" so the name reached the spec")
    if found:
        print(f"\n{len(set(found))} spec(s) print an unresolved citation."
              f" The head of a `(<class>, <book>, page N)` citation is a"
              f" name by position -- resolve it in the extraction.")
        return 1
    print("every printed citation in a spec resolves to a ref")
    return 0


#: A spec that prints a name the scrub should have swapped, and the reason it
#: is allowed to. Keyed `(table, ref, the ref the name resolves to)`.
#:
#: Empty, deliberately, and it should stay empty: a hit here means a phrase
#: *coincides* with some row's printed name and means something else. A
#: genuine leak belongs in the baseline below, which is work owed, not in an
#: allowance, which is a judgement made.
UNSWAPPED_KNOWN: dict[tuple[str, str, str], str] = {}

#: **60 spec rows when this walk was written; 10 now.** A per-row baseline
#: that may shrink and must not grow -- `cards.KNOWN`'s contract and
#: `fixtures/audited.json`'s, for the reason `scripts/CLAUDE.md` gives: a
#: bare count cannot tell whether a run's hits are the known ones, and
#: cannot see ten healing while ten break.
#:
#: **Safe to write down because every key is a ref.** `(table, row, the ref
#: whose name the row prints)` names no printed text, which is why this can
#: be a list at all where a forbidden-name list could not.
#:
#: Not an allowance. Each one is the ETL's scrub failing to swap a name in a
#: spec an author reads, and the fix is in the extraction.
#:
#: **The 50 that went were one shape, and it was not the one guessed here.**
#: This used to say the split was "a plain Title-Case pair gets swapped and a
#: name holding a lowercase connective does not". The connective was a
#: symptom: `etl.sanitise.identifies` strips function words *before*
#: measuring and then refuses a phrase of fewer than three **content** words
#: whose every word is ordinary rules vocabulary, while this walk counts all
#: the words. So `<rules word> of the <rules word>` was three words to the
#: gate and two to the scrubber -- flagged by one, never offered to the
#: other. Measured across the 60: 51 were exactly that, 8 were a
#: `RULES_TERMS` hit and 1 a `weapon_names()` hit.
#:
#: `build._uniquely_owned` is the second door that closed it: a name printed
#: by exactly one row of twenty-six thousand is believed on its uniqueness
#: where `identifies` disbelieves it on its words. #628.
#:
#: **What is left is 10 and none of it is owed. Looked at, 2026-10-26.**
#: This used to read "correct in general and wrong for these eight", and
#: that is backwards -- the scrubber is right about all eight and the
#: baseline was mislabelling its own entries as debt.
#:
#: **The eight are a false attribution, not a missed swap.** They are feats
#: printing the phrase that is *also* the title of one cleric build's
#: feature, and every one of them means the **keyword category** rather
#: than that row. `f1355` is the plain case: *"Your <phrase> powers that
#: have a range of personal gain a range of close burst 5"* -- that is
#: every power of that keyword, in any divine class, and substituting the
#: warpriest's ref would name one build's feature where the card names a
#: category. All three words of the title are in the rules vocabulary, so
#: `identifies` refuses it, and refusing it is correct.
#:
#: The proof that nothing is missing is in the same specs: where the text
#: *does* mean the class feature, **the swap already happened** --
#: `cf:avenger-f2/cf:cleric-templar-f0/cf:invoker-f0/cf:paladin-f0`, the
#: four-class alternation, appears wherever the sentence is about the
#: feature. So both senses are handled, and the gate is flagging the one
#: that must not be touched.
#:
#: **The two traps print a power's and a feat's name into `trap.spec`**, a
#: table with no content rows: nothing in `content/` is authored from a
#: trap, so no author reads them and nothing renders them. Tier 3 at
#: worst (#447), and it would go the day traps are ingested as rows.
#:
#: So these 10 are **waived with a reason**, not work. The number can still
#: only shrink and a new one is still red, which is the half worth having.
#: #628.
UNSWAPPED_BASELINE: frozenset[tuple[str, str, str]] = frozenset({
    ("feat", "f1355", "cf:cleric-warpriest-f0"),
    ("feat", "f1432b", "cf:cleric-warpriest-f0"),
    ("feat", "f1557", "cf:cleric-warpriest-f0"),
    ("feat", "f1622", "cf:cleric-warpriest-f0"),
    ("feat", "f1623", "cf:cleric-warpriest-f0"),
    ("feat", "f1624", "cf:cleric-warpriest-f0"),
    ("feat", "f1625", "cf:cleric-warpriest-f0"),
    ("feat", "f1627", "cf:cleric-warpriest-f0"),
    ("trap", "t:30", "p11722"),
    ("trap", "t:337", "f2247"),
})


def _entitled_names() -> int:
    """A spec printing a racial trait's name where its own prereq names that
    race. The fourth waiver-free question.

    `--cited`, `--categories` and `_unswapped_names` are the other three, and
    this one's discriminator is new: not uniqueness, but **entitlement**. A
    feat whose prerequisite requires `r24` and whose spec prints a phrase
    equal to one of `r24`'s printed trait names is naming that trait -- there
    is nothing else on the page it could be -- so no word count and no
    vocabulary test is needed, and none may be applied.

    That matters because the names involved are exactly the shape every other
    gate waives. Measured when this was written, **21 specs** printed one and
    every single run of `leaks.py`, `--specs` and `--cited` on record had
    reported clean:

        4 races printing a parent's trait after "This benefit replaces"
       14 feats naming a required race's trait in running prose
        3 of those 14 a substring of a longer name in the same sentence

    `identifies` waives them because they are one or two ordinary words.
    `_uniquely_owned` cannot reach them either: it believes a name printed by
    exactly one row, but only above two words. Lowering that threshold is not
    available -- there are 11,680 uniquely-owned two-word names and 1,264
    one-word ones in this corpus, so believing them all would put a ref in
    the place of every coincidental pair.

    **Case-sensitive, for the same reason `build._required_race_traits` is,
    and the guard is load-bearing**: dropped, this gate reports 31 rows where
    11 are real. A printed name is Title Case and the ordinary word is not,
    so "your Ferocity" is a leak and "fought with ferocity" is prose. The
    checker and the scrubber have to count the same way or 124 specs ship a
    name while both halves believe they agree -- this file's own history.
    """
    db = game()
    traits: dict[str, dict[str, str]] = {}
    try:
        rows = db.execute("SELECT ref, race FROM racial_trait").fetchall()
    except sqlite3.OperationalError:
        return 0
    printed = localisation()
    for ref, race in rows:
        name = ((printed.get(ref) or {}).get("name") or "").strip()
        if len(name) >= 3:
            traits.setdefault(race, {})[name] = ref

    found: list[tuple[str, str, str, str]] = []
    want = re.compile(r'"race"\s*:\s*"(r\d+)"')
    for ref, prereq, spec in db.execute(
        "SELECT ref, prereq, spec FROM feat WHERE spec IS NOT NULL"
    ):
        for race in want.findall(prereq or ""):
            for name, owner in traits.get(race, {}).items():
                if owner.startswith(ref) or ref.startswith(owner):
                    continue
                if re.search(rf"\b{re.escape(name)}\b", spec):
                    found.append(("feat", ref, owner, name))

    if found:
        for table, ref, owner, _name in sorted(set(found))[:40]:
            print(f"{table}.{ref}: prints the name of {owner}, whose race"
                  f" its own prerequisite requires")
        print(f"\n{len(set(found))} spec(s) print a racial trait's name their"
              " own prerequisite entitles them to name.")
        print("Every one is shown to an author verbatim. The fix is"
              " `_required_race_traits` in etl/build.py -- there is no"
              " coincidence to waive here, because the prerequisite is the"
              " proof.")
        return 1
    print("no spec prints a trait name its own prerequisite names")
    return 0


def _unswapped_names(index: dict[str, list[str]]) -> int:
    """A spec printing a name it never cites. The waiver-free question.

    **The third position where `identifies` must not be consulted**, after
    `--cited` and `--categories`. The tree-wide walk waives a multi-word name
    made of ordinary words in running prose -- rightly, and that is #494's
    blind spot -- so `--specs` reports clean over a `Requirement:` line
    reading "you must use this power with your <three ordinary words>" where
    the sibling card two refs along correctly says `w3742`.

    **Uniqueness is the discriminator**, which is the insight `--cited` is
    built on. A phrase resolving to **one** ref, in a spec that never cites
    that ref, is not a coincidence worth waiving: the scrub was supposed to
    swap it and did not. A phrase resolving to *several* refs usually is a
    coincidence -- a printed monster ability very often is a generic combat
    phrase -- so those are left to the tree-wide walk and its waivers, the
    same split `--cited`'s `_trusted_vocabulary` makes.

    Measured when it was written: of 4,171 printed names holding a lowercase
    connective, 69 appear in a spec that never cites their ref -- and
    **17 of those resolve uniquely**, across 30 spec rows. Every one was
    reported clean by `--specs` on every run on record.

    Three or more words, because the two-word case is where coincidence
    lives and the two-word names are also the ones the scrub gets right:
    the observed pattern is that a name with a lowercase connective in the
    middle survives, and a plain Title-Case pair does not.
    """
    db = game()
    unique = {
        phrase: refs[0] for phrase, refs in index.items()
        if len(refs) == 1 and len(phrase.split()) > 2
    }
    found: list[tuple[str, str, str]] = []
    for table in _SPEC_TABLES:
        try:
            rows = db.execute(
                f"SELECT ref, spec FROM {table} WHERE spec IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        for ref, spec in rows:
            low = (spec or "").lower()
            for phrase, owner in unique.items():
                if phrase not in low:
                    continue
                # Its own name is its own business -- `p289b` belongs to
                # `p289` and may say so -- and a spec that *does* cite the
                # ref has been swapped and is merely repeating itself.
                if owner.startswith(ref) or ref.startswith(owner):
                    continue
                if owner in (spec or ""):
                    continue
                if (table, ref, owner) in UNSWAPPED_KNOWN:
                    continue
                found.append((table, ref, owner))

    # The baseline is subtracted *after* the walk, so the report can say
    # what healed as well as what is new -- a count alone could not.
    every = sorted(set(found))
    fresh = [k for k in every if k not in UNSWAPPED_BASELINE]
    healed = sorted(UNSWAPPED_BASELINE - set(every))

    for table, ref, owner in fresh[:40]:
        print(f"{table}.{ref}: prints the name of {owner} and never cites it")
    if fresh:
        extra = " (showing 40)" if len(fresh) > 40 else ""
        print()
        print(f"{len(fresh)} NEW spec(s) print a name the scrub left behind"
              f"{extra}.")
        print("Every one is shown to an author verbatim. Fix the extraction "
              "-- see `_cross_reference` in etl/build.py -- or, if the "
              "phrase genuinely means something else, name the coincidence "
              "in `UNSWAPPED_KNOWN`.")
        return 1
    if healed:
        print(f"{len(healed)} baseline entr"
              f"{'y' if len(healed) == 1 else 'ies'} no longer leak -- take "
              f"them out of `UNSWAPPED_BASELINE`:")
        for key in healed[:20]:
            print(f"  {key[0]}.{key[1]} no longer prints {key[2]}'s name")
        return 1
    print(f"no NEW spec prints a uniquely-resolving name it does not cite "
          f"({len(UNSWAPPED_BASELINE)} known and waived with a reason --"
          f" see UNSWAPPED_BASELINE, #628)")
    return 0


#: A labelled clause as the ETL leaves one: `<ref> : <sentence>`.
_CLAUSE = re.compile(r"^([A-Za-z0-9:_.-]+) : (.*)$")


def _self_named_clauses() -> int:
    """Does a labelled clause print the name of its own label? #528.

    **The walk above cannot answer this and must not be made to.** It runs
    every spec past `identifies`, which waives a two-word name built of two
    ordinary words -- and `p1458`'s name is two words that are *both* in the
    rules vocabulary. So the leak this catches sat in a brief under a
    reported-clean `--specs` for as long as the feat has been imported.

    Removing that waiver is not the fix and has been measured rather than
    argued: the same sweep with it off reports **3,885** hits across 3,130
    specs, nearly all innocent -- a monster ability named for a generic
    combat phrase, mentioned in prose that means the phrase. Vocabulary
    cannot separate the two cases at spec scale.

    **Position can, which is why this is a separate walk.** A labelled
    clause belongs to its label: in `p1458 : ...`, the sentence is about
    `p1458`, so `p1458`'s own name inside it is self-reference by
    construction and needs no waiver and no judgement. 733 such clauses
    exist and the honest count of leaks is 0 or it is a bug.

    The same argument `etl/build._label_refs` makes for the label itself --
    "in this position it is never a coincidence" -- one clause further
    along. `etl/build._self_named_clauses` is the pass that fixes it; this
    is the half that notices when it stops working.
    """
    names = localisation()
    own: dict[str, list[str]] = {}
    for ref, entry in names.items():
        name = _fold((entry or {}).get("name", "")).lower().strip()
        if len(name) >= 4:
            own.setdefault(ref, []).append(name)

    db = game()
    bad: list[tuple[str, str, str]] = []
    clauses = 0
    for table in _SPEC_TABLES:
        for ref, spec in db.execute(f"SELECT ref, spec FROM {table}"):
            for line in (spec or "").splitlines():
                m = _CLAUSE.match(line)
                if m is None or m.group(1) not in own:
                    continue
                clauses += 1
                flat = _fold(m.group(2)).lower()
                if any(n in flat for n in own[m.group(1)]):
                    bad.append((table, ref, m.group(1)))

    print(f"  {clauses} labelled clause(s) read")
    for table, ref, label in bad:
        print(f"  {table}.{ref}: its {label} clause prints {label}'s own name")
    if bad:
        print(f"\n{len(bad)} clause(s) name their own label -- "
              "see `_self_named_clauses` in etl/build.py")
        return 1
    print("no labelled clause prints the name of its own label")
    return 0


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
    # Armour's two mechanical words. The table has **no slug** for the reason
    # `racial_trait` has none -- all 408 rows are in `names.json`, so a slug
    # would hold a printed name on every one -- and these two columns are here
    # so that "a type is mechanics" is checked rather than asserted. #452.
    ("armour", "type"),
    ("armour", "base"),
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
    # Armour's two, found by adding the columns rather than by assuming the
    # claim. `chainmail` is the armour type word and also `a4`'s own printed
    # name -- the column holds the right word and the row is named after it.
    # `chain` is the printed restriction on an enchantment's `Armor:` line and
    # also what two unrelated monster abilities are called. #452.
    ("armour", "type", "chainmail"),
    ("armour", "base", "chain"),
}


#: Every `feat.category` that may appear in a tracked file, and why.
#:
#: **The allowed set is written down and the forbidden set is not**, which is
#: the whole design. A list of names-to-refuse would *be* the leak -- the same
#: reason `fixtures/localisation.json` holds digests rather than values -- so
#: this holds only the vocabulary, in plain text, and everything else the
#: column contains is treated as a name. A category the compendium adds
#: therefore defaults to **forbidden** and has to be argued onto this list,
#: which is the strict direction and the one `cards.KNOWN` gets right.
#:
#: Camille's ruling, 2026-10-16, on the three two-word descriptive labels that
#: prompted this: **mechanics.** The argument was consistency -- it would be
#: odd for a one-word label naming a rules category to be vocabulary and a
#: two-word one naming a category of the same kind not to be -- and the cost
#: of the other answer was real: those three are quoted in
#: `content/CLAUDE.md` and `docs/AUTHORING.md`, the two files that *teach* the
#: one-feat-per-category rule, which four of the first five migrated rows got
#: wrong. Scrubbing them would have made the instructions vaguer about exactly
#: the thing they exist to prevent.
#:
#: What is deliberately **not** here: every `<X> Bloodline`. Those resolve to
#: invented proper nouns and to race names, and a race's printed name in a
#: tracked file is already a leak -- `races/` holds `r33` and not the word.
#: One of them was sitting in `etl/feat.py`'s docstring until #622.
CATEGORY_VOCABULARY = {
    # Rules categories: a descriptive phrase naming a set of feats, where
    # the rule being named ("at most one of these per use of a power") is a
    # game system and not expression.
    "Arena Fighting": "a rules category; Camille, 2026-10-16",
    "Lesser Style": "a rules category; Camille, 2026-10-16",
    "Greater Style": "a rules category; Camille, 2026-10-16",
    "Lesser Pact": "a rules category, the same shape as the Style pair",
    "Greater Pact": "a rules category, the same shape as the Style pair",
    # One ordinary word, and this engine implements the mechanic under that
    # exact word -- so the word is its vocabulary, not a name it borrowed.
    "Augment": "the power-augmentation mechanic; `p…:augment1` markers",
    "Familiar": "`Companion.passive`, `c.familiar_mode`",
    "Rune": "the runepriest's rune state",
    "Divinity": "a divine class mechanic",
    "Domain": "a divine class mechanic",
    "Multiclass": "the multiclassing rule",
    "Guild": "an ordinary word; no mechanism of its own here",
    "Tribal": "an ordinary word; no mechanism of its own here",
    "Elemental Companion": "descriptive: a companion with an element",
}


def feat_categories() -> int:
    """Does a tracked file print a feat category that is not vocabulary? #622.

    The bracket after a feat's printed name -- `feat.category` -- is a
    column the name walks never looked at. `--specs` reads `spec` and
    nothing else; `columns` tests whole-value equality against the name
    index, which a category is not; and the tree-wide walk waives a
    two-word label of ordinary words in running prose, correctly, which is
    #494's blind spot.

    So this asks the narrow question instead, the way `--cited` does:
    **every category the compendium prints, minus the hand-kept
    vocabulary, must appear in no tracked file.** No waiver is applied, and
    none is needed -- the set being searched for is already known to be
    names rather than mechanics, because that is what `CATEGORY_VOCABULARY`
    not listing them means.

    Found by reading `drivers.py` output and asking, not by running
    anything. 72 categories, 12 reached tracked files, and one was an
    invented proper noun in `etl/feat.py` -- which every previous run of
    `leaks.py` and `leaks.py --cited` had called clean.
    """
    db = game()
    try:
        every = {c for (c,) in db.execute(
            "SELECT DISTINCT category FROM feat WHERE category != ''")}
    except sqlite3.OperationalError:
        print("feat.category has not been built; skipped")
        return 0
    if not every:
        print("feat.category is empty; skipped")
        return 0

    # **Whole cells, not split on the comma, and that is measured rather
    # than lazy.** Exactly two cells carry a comma -- `f3389`'s and
    # `f2025`'s -- and splitting them looked obviously right and was wrong:
    #
    # * `f3389` is **one** category naming three classes, joined by commas
    #   and an "or". Split, its tail becomes two labels that were never
    #   categories, and one of them is a bare class word this tree uses in
    #   `cls=` several hundred times -- so the check went red on 21 files
    #   for nothing on its first run.
    # * `f2025` is genuinely two categories in one bracket.
    #
    # Not splitting loses no coverage, which is what makes it the right
    # call rather than a retreat: **both** of `f2025`'s halves appear as
    # standalone categories elsewhere in the column, so each is watched on
    # its own account. `f3389`'s tail words appear nowhere else, because
    # they were never labels. Verified with
    # `select category from feat where category like '%,%'`.
    labels = set(every)
    watch = sorted(labels - set(CATEGORY_VOCABULARY))
    stale = sorted(set(CATEGORY_VOCABULARY) - labels)

    found: list[tuple[str, int]] = []
    for path in tracked():
        if path.suffix not in TEXT_SUFFIXES or not path.exists():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        hits = sum(1 for label in watch if label in text)
        if hits:
            found.append((str(path), hits))

    for path, hits in found[:40]:
        one = hits == 1
        print(f"{path}: prints {hits} feat categor{'y' if one else 'ies'}"
              f" that {'is' if one else 'are'} not vocabulary")
    if found:
        print()
        print(f"{len(found)} tracked file(s) print a feat category"
              f" that `CATEGORY_VOCABULARY` does not allow.")
        print("Either it is a name -- refer to the category by a feat ref "
              "instead -- or it is a mechanic and belongs on that list "
              "with a reason beside it.")
        return 1
    # The same discipline `SPEC_KNOWN` gets: an entry whose value has left
    # the column is dead weight and says so, rather than sitting there
    # looking like a considered allowance.
    if stale:
        print("CATEGORY_VOCABULARY entries no longer in feat.category "
              "-- delete them:")
        for label in stale:
            print(f"  {label}: {CATEGORY_VOCABULARY[label]}")
        return 1
    print(f"no tracked file prints a feat category outside the "
          f"{len(CATEGORY_VOCABULARY)} allowed, of {len(labels)} printed")
    return 0


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


#: Where the residue of the inverted check is baselined, as **digests**.
#:
#: Digests and never the phrases, for the reason `fixtures/localisation.json`
#: holds them: some unknown fraction of this residue is real printed names,
#: which is precisely why it is interesting -- so a committed file listing
#: them in plain text would *be* the leak this gate exists to catch. The
#: phrase behind a digest is recoverable only by re-running against a
#: database the reader already has, which is the same bargain the
#: localisation freeze makes. #493.
INGEST = Path(__file__).resolve().parent / "fixtures" / "ingest.json"

#: A printed name's shape, without needing to know any name: two or more
#: adjacent capitalised words.
#:
#: **This is the inverted question** -- `leaks.py`'s main walk searches for
#: the 22,343 names it has a copy of, and by construction can never report
#: one it has no copy of. #493 measured that blind spot and controlled it: of
#: the distinct phrases this finds, **0 are a known printed name and 0
#: contain one as a sub-phrase**, with a positive control proving the lookup
#: that produced those zeros works (4 of 5 real names resolve through the
#: same path). So this residue is not "names the matcher is too weak to
#: see". It is names the matcher has no copy of, and no amount of matcher
#: work reaches it.
_PHRASE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

#: A brief's structural heading, which must be cut **before** phrases are
#: extracted or the walk runs straight across the boundary and reports
#: `<Heading> <whatever follows>` as one phrase.
#:
#: Matched as a shape rather than listed, so a heading the extractor starts
#: printing tomorrow is handled without editing this.
#:
#: Measured, because #493's comment implies a bigger effect than this has:
#: 43% of occurrences *begin with* a heading, but cutting them drops only
#: **19%** -- 2,444 occurrences to 1,986, 506 distinct phrases to 416.
#: The gap is tails that are still a capitalised phrase once the heading is
#: gone, so they are findings in their own right rather than artifacts.
_HEADING = re.compile(r"\b[A-Z][a-z]+s?\s*:")


def _spec_phrases(spec: str, trusted: frozenset[str]) -> set[str]:
    """Capitalised multi-word phrases in one spec, refs and headings removed.

    A phrase every word of which is trusted vocabulary is waived -- the same
    judgement `--cited` makes, and for the same reason: "makes a double
    attack" is three capitalised words in a heading-adjacent position and
    leaks nothing.
    """
    text = _HEADING.sub(" | ", CITED_REF.sub(" ", spec))
    return {
        found.group() for found in _PHRASE.finditer(text)
        if not all(word.lower() in trusted for word in found.group().split())
    }


def ingest() -> int:
    """Ask whether a spec is reference-complete, instead of searching it.

    Camille, 2026-10-10: *"I don't understand why we aren't just, when
    ingesting a new row, checking to make sure that the code used
    localization."*

    Every hole `leaks.py`'s blocklist search has ever had -- a hyphen, a
    non-ASCII letter, a comma, a whole table missing from the walks list --
    was a consequence of its shape rather than a bug in its matcher. This is
    the other shape: find anything in a spec that **looks like** a name and
    is not vocabulary, and require it to have been seen before.

    Red on a phrase whose digest is not in the baseline. The baseline may
    shrink and never grow, which is the discipline `keywords.py` and
    `targets.py` already use -- so curating the residue down is recorded and
    a new one is a failure.
    """
    import hashlib

    db = game()
    trusted = _trusted_vocabulary()
    found: dict[str, list[str]] = {}
    shown: dict[str, str] = {}
    specs = 0
    for table in sorted(_spec_columns()):
        for (spec,) in db.execute(
                f"SELECT spec FROM {table} WHERE spec IS NOT NULL"):
            specs += 1
            for phrase in _spec_phrases(spec, trusted):
                digest = hashlib.sha256(
                    phrase.lower().encode("utf-8")).hexdigest()[:12]
                found.setdefault(digest, []).append(table)
                shown[digest] = phrase

    print(f"  {specs} spec(s) scanned, {len(found)} distinct phrase(s) that"
          f" look like a name and are not vocabulary")
    by_table: dict[str, int] = {}
    for tables in found.values():
        for table in tables:
            by_table[table] = by_table.get(table, 0) + 1
    for table, n in sorted(by_table.items(), key=lambda kv: -kv[1])[:6]:
        print(f"      {table:16} {n}")

    # `--show` prints the phrases to this terminal and writes none of them,
    # which is the one place a reader may see the residue. The main session
    # reading a name and telling Camille is explicitly allowed; a tracked
    # file holding it is not.
    if "--show" in sys.argv:
        print("\n  the residue, printed here and written nowhere:")
        for digest, phrase in sorted(shown.items(), key=lambda kv: kv[1]):
            print(f"      {digest}  {phrase!r}"
                  f"  [{', '.join(sorted(set(found[digest])))}]")

    if "--record" in sys.argv or not INGEST.exists():
        first = not INGEST.exists()
        INGEST.write_text(json.dumps(
            {"note": "digests only, never the phrases -- see leaks.INGEST",
             "specs": specs,
             "phrases": sorted(found)}, indent=2) + "\n")
        print(f"  {'wrote a first' if first else 're-recorded the'} baseline"
              f" in {INGEST.name}: {len(found)} digest(s)")
        return 0

    known = set(json.loads(INGEST.read_text()).get("phrases", []))
    fresh = sorted(set(found) - known)
    gone = sorted(known - set(found))
    if gone:
        print(f"  {len(gone)} digest(s) no longer present -- the residue"
              f" shrank, which is the good direction. Re-record with"
              f" `--ingest --record`.")
    if fresh:
        print(f"\n  {len(fresh)} phrase(s) in a spec that the baseline does"
              f" not hold. A spec gained something shaped like a printed"
              f" name:")
        for digest in fresh[:12]:
            print(f"      {digest}  in {', '.join(sorted(set(found[digest])))}")
        print("  The phrase itself is deliberately not printed -- see"
              " `leaks.INGEST`. Re-run with `--ingest --show` to see it"
              " locally, which never writes it anywhere.")
        return 1
    print("  no spec holds a name-shaped phrase the baseline does not know")
    return 0


def main() -> int:
    if "--ingest" in sys.argv:
        return ingest()
    if "--categories" in sys.argv:
        return feat_categories()
    if "--cited" in sys.argv:
        return cited()
    if "--modules" in sys.argv:
        return modules()
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

    The window is `_NGRAM_CAP`, which `_index` derives from the longest
    printed name. It was the literal `6` and 18 seven-word names were
    unreachable because of it -- the same by-construction hole the hyphen and
    the accent each cut, counted a third time. **Anything comparing a key
    against a phrase built here has to be built by the same rules**, which is
    the invariant `_index` now holds.
    """
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    # Within runs of prose only. Punctuation is a boundary -- a method
    # signature is not a sentence, and reading across the opening bracket
    # made every `def <verb>(self` pair look like a two-word name.
    # Folded the same way the index is, so an accented or curly-apostrophe
    # name is reachable at all. See `_fold`.
    for run in re.findall(r"[a-z'](?:[a-z' -]*[a-z'])?", _fold(line.lower())):
        words = re.findall(r"[a-z']+", run)
        for size in range(min(_NGRAM_CAP, len(words)), 0, -1):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size])
                seen.add(phrase)
                if phrase in index:
                    out.append((phrase, index[phrase]))
    # A name holding punctuation sits in no single run, so it needs a second
    # pass over the line with punctuation collapsed to a space.
    #
    # **"Every segment somewhere on the line" is not good enough**, and the
    # first version of this did that. A flattened spec is one line of up to
    # 3,300 characters, so on three trap specs the base segment appeared and
    # the one-word parenthesised qualifier turned up unrelated somewhere else
    # in the same line -- three findings that were artefacts of the test. It
    # was reproducing `build._spelt_out`, which that file's own docstring
    # calls "a cheap sieve, not a match".
    #
    # So the segments have to be **contiguous**: the name as printed, with
    # only non-letters between its parts. That is what collapsing gives. The
    # second pass reads across brackets, which the first deliberately does
    # not -- confined to names that genuinely hold punctuation, where the
    # alternative is not matching them at all.
    if _SEGMENTED:
        flat = re.sub(r"[^a-z' -]+", " ", _fold(line.lower()))
        words = re.findall(r"[a-z']+", flat)
        for size in range(min(_NGRAM_SPAN, len(words)), 1, -1):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size])
                if phrase in _SEGMENTED_KEYS and phrase in index:
                    out.append((phrase, index[phrase]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
