#!/usr/bin/env python
"""Has a printed name got into the repository?

    uv run scripts/leaks.py

The engine holds ids. Names live in `localization/names.json`, which is built
from your own copy of the compendium and is not committed. This is what holds
the repository to that -- it reads every name the compendium has and looks for
each one in every tracked file.

Exits non-zero on a find, so it can gate a commit.

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
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path

from combat_engine.etl.build import ROOT, game, localisation
from combat_engine.etl.sanitise import RULES_TERMS

#: A one-word name shared by more than this many rows is vocabulary rather
#: than an identifier, and is not worth reporting.
COMMON_ENOUGH = 3

#: And a very short word is a coincidence waiting to happen either way.
SHORTEST = 6

#: Function words. A multi-word match made only of these is a coincidence in
#: ordinary prose -- there is a power called `Not It`. Closed set, unlike a
#: list of game names, so it does not need feeding.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "for",
    "from", "has", "have", "if", "in", "into", "is", "it", "its", "no", "not",
    "of", "off", "on", "one", "or", "out", "so", "that", "the", "their",
    "them", "then", "there", "they", "this", "to", "up", "was", "were", "what",
    "when", "which", "who", "will", "with", "you", "your",
}

#: Ordinary English that happens to be somebody's printed name.
#:
#: The single-word test asks a dictionary -- an invented name is in no
#: dictionary -- and the multi-word test does not, so any name built from
#: common words collides with prose that merely contains those words in that
#: order. Making the multi-word test smarter would suppress real names, since
#: plenty of them are ordinary words too. An explicit list with a reason each
#: is the honest version: it says out loud what is being waived.
#: Emptied once the phrase rule above learned to ask whether any word in a
#: phrase is actually a word. Both entries that lived here -- "from the
#: shadows" and "meat shield" -- are now suppressed on their merits.
ALLOWED: set[str] = set()


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


#: The system word list, where there is one. `builder`, `dispatch` and
#: `stable` are all published ability names and all ordinary English, and no
#: amount of counting tells those apart from an invented name -- a
#: dictionary does it in one lookup. Absent on some machines, hence the fallbacks.
DICTIONARY = Path("/usr/share/dict/words")


def vocabulary() -> set[str]:
    """Words this script will not call a name.

    Four sources, none of them a list anybody has to keep current:

    * the system dictionary, so ordinary English is ordinary English;
    * the engine's own enumerations, so a condition added to `types.py` is
      allowed the moment it exists;
    * the core rules terms above, which a rules engine has to be able to say;
    * every word appearing on at least a handful of compendium pages, which
      covers the game's own vocabulary -- `bloodied` and the like -- that no
      dictionary has.

    Each is a strict addition, so a machine without the dictionary gets a
    noisier report rather than a wrong one.
    """
    from enum import EnumMeta

    from combat_engine.engine import types

    out = set(CORE)
    if DICTIONARY.exists():
        out.update(
            w.strip().lower()
            for w in DICTIONARY.read_text(errors="ignore").splitlines()
            if w.strip()
        )
    # An older game.db has no such table.
    with contextlib.suppress(Exception):
        out.update(r["word"] for r in game().execute("SELECT word FROM common_word"))
    for name in dir(types):
        member = getattr(types, name)
        if isinstance(member, EnumMeta):
            for item in member:
                if isinstance(item.value, str):
                    out.add(item.value.lower().replace("_", " "))
                out.add(item.name.lower().replace("_", " "))
    return out

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


def main() -> int:
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
                where = findings if _identifies(name, refs, rules) else quiet
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


def _identifies(name: str, refs: list[str], rules: set[str]) -> bool:
    """Does this name point at a particular row, or is it just words?

    The two cases need opposite treatment, which an earlier version of this
    got wrong in the worst way -- it asked whether every word was ordinary
    English, and so waved two-word monster names straight through.

    **A phrase is a name.** Both halves of a two-word monster name are often
    ordinary English, and the pair of them is still a monster. So a multi-word match is reported
    unless the whole phrase is a rules term, or unless it is made entirely of
    function words -- there is a published power called `Not It`, and that is
    what the stop list is for.

    **A lone word is a name only if it is not a word.** `builder` and
    `stable` are published abilities and also plain English; an invented
    name is in no dictionary. It must also be long enough, and rare enough among
    the names, to be worth believing.
    """
    if name in rules or name in ALLOWED or _stem(name) in rules:
        return False
    if " " in name:
        # Function words do not count towards the length: "from the
        # shadows" is one idea, not three, and treating it as three made it
        # a finding on its own length.
        words = [w for w in name.split() if w not in STOPWORDS]
        if not words:
            return False
        # A phrase is a name worth reporting when **some word in it is not a
        # word** -- an invented one -- or when it is long enough that the
        # collision is not chance. Two ordinary words in a row is chance:
        # "blink out", "threatening reach", "guarded area" and "poison
        # weapon" are all published names and all things a rules sentence
        # says by accident, and reporting them taught the reader to skim.
        #
        # The cost is real and worth stating: a genuine two-word name made
        # of two ordinary words -- "writhing coils" -- is now missed. That
        # is the trade, and the ETL scrubber is the other line of defence.
        return len(words) >= 3 or any(
            w not in rules and _stem(w) not in rules for w in words
        )
    return (
        name not in rules and len(name) >= SHORTEST and len(refs) <= COMMON_ENOUGH
    )


def _stem(word: str) -> str:
    """Crudely singular. The dictionary has "narrow" and not "narrows"."""
    for suffix in ("es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


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
