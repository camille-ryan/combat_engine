"""Taking the prose out.

Game systems cannot be trademarked; the words they are printed in can. So
the engine holds mechanics and ids, and the names live only in a
localisation file built from whoever's copy of the compendium.

This module is the seam. Everything an authoring agent is shown passes
through it, and it does two jobs:

* **drop the flavour.** A power's page has a name in its `<h1>` and a line
  of italics under it. Both go. What is left is the lines that carry a
  mechanical label, which is exactly what needs coding.
* **scrub self-reference.** A stat block names itself in its own rules --
  "the target contracts <name> filth fever" -- and a power's name turns up
  inside its own Effect line often enough to matter. Those become the row's
  id, so the spec reads "contracts m145 filth fever" and the author learns
  nothing they should not have.
"""

from __future__ import annotations

import contextlib
import re
from functools import lru_cache
from pathlib import Path

from .html import labelled, paragraphs, text

#: Paragraph labels that carry mechanics. Anything else in a `flavor`
#: paragraph is prose and is dropped.
#: Labels that are publication furniture rather than rules.
_FOOTERS = ("published in", "update", "updated", "errata")

MECHANICAL = {
    "requirement", "prerequisite", "trigger", "target", "targets", "attack",
    "hit", "miss", "effect", "special", "sustain", "aftereffect",
    "secondary target", "secondary attack", "primary target", "primary attack",
    "tertiary target", "tertiary attack", "first failed saving throw",
    "second failed saving throw", "failed saving throw", "level", "increase",
    "attack technique", "hit or miss", "opportunity attack",
}  # fmt: skip


#: Rules terms that are also, unhelpfully, printed names. A monster ability
#: called "Combat Advantage" must not turn the words *combat advantage* into
#: an id wherever they appear -- the sentence "against any target it has
#: combat advantage against" becomes unreadable, and the term is mechanics
#: rather than prose, so it was never at risk. `scripts/leaks.py` reads this
#: same set, so the two halves cannot drift apart.
RULES_TERMS = {
    "combat advantage", "second wind", "healing surge", "opportunity attack",
    "saving throw", "basic attack", "melee basic attack", "ranged basic attack",
    "difficult terrain", "line of effect", "line of sight", "action point",
    "temporary hit points", "hit points", "bloodied", "resistance",
    "vulnerability", "short rest", "extended rest", "death save", "aura",
    "zone", "burst", "blast", "reach", "cover", "concealment", "flanking",
    "mark", "shift", "charge", "grab", "escape", "stand", "initiative",
    "target", "trigger", "effect", "attack", "damage", "heal", "push",
    "pull", "slide", "teleport", "prone", "move", "turn", "split", "level",
    "speed", "range", "hit", "miss", "special", "requirement", "sustain",
    # Equipment. A sword is a sword; several monsters have an ability named
    # after the one they are holding, which does not make the word theirs.
    "short sword", "shortsword", "long sword", "longsword", "greatsword",
    "bastard sword", "scimitar", "rapier", "dagger", "mace", "club",
    "greatclub", "quarterstaff", "staff", "spear", "longspear", "javelin",
    "halberd", "glaive", "battleaxe", "handaxe", "greataxe", "warhammer",
    "maul", "flail", "pick", "sickle", "longbow", "shortbow", "crossbow",
    "hand crossbow", "sling", "shuriken", "dart", "net", "whip", "trident",
    "morningstar", "falchion", "waraxe", "khopesh", "katar", "garrote",
    "holy symbol", "orb", "rod", "wand", "tome", "totem",
    "leather armor", "hide armor", "chainmail", "scale armor", "plate armor",
    "light shield", "heavy shield", "bow", "sword", "axe",
    # Magic items. A slot is printed beside the price because it is
    # mechanics, and several items are named after the slot they fill --
    # so without these, scrubbing takes the word "neck" out of a neck
    # item's own rules and the line stops meaning anything.
    # Mechanics a stat block is routinely *named after*, which is the same
    # argument the weapons above make. **205 refs carry one of these as their
    # printed name** -- 55 "Regeneration", 45 "Threatening Reach", 38
    # "All-Around Vision", 31 "Insubstantial" -- and without them here the
    # words were turned into an id wherever they appeared: a feat reading
    # "You gain regeneration 5 until the end of the encounter" was handed
    # "You gain x_m5087a1 until the end of the encounter", which says nothing
    # at all. Camille's rule, and the arithmetic agrees with it: a character
    # option never references a monster's ability by name.
    "regeneration", "threatening reach", "all-around vision", "all around vision",
    "insubstantial", "phasing", "tremorsense", "darkvision", "blindsight",
    "truesight", "low-light vision", "ongoing damage", "immunity",
    # Two more weapons, for the reason the list above already gives.
    "fullblade", "repeating crossbow",
    "enhancement bonus", "item bonus", "critical", "property", "consumable",
    "head slot", "neck slot", "arms slot", "hands slot", "waist slot",
    "feet slot", "ring slot", "wondrous item", "alchemical item",
    "head", "neck", "arms", "hands", "waist", "feet", "ring", "wondrous",
    "ammunition", "implement", "armor", "armour", "weapon", "gp",
    # Feats. The tier and the two labels every feat page prints.
    "heroic tier", "paragon tier", "epic tier", "prerequisite", "benefit",
}  # fmt: skip


#: Words that appear inside printed names and carry no identity of their own.
#: Scrubbing them would only make a spec harder to read.
_NOISE = {"the", "of", "and", "a", "an", "in", "on", "to", "with", "its", "it"}


@lru_cache(maxsize=1)
def _MECHANICAL_WORDS() -> frozenset[str]:
    """Every word the engine itself has a name for. Never scrubbed.

    Read off the enums rather than listed here, so the two cannot drift: if
    the engine gains a damage type, the sanitiser knows about it the same
    day. A single-word ability name that *is* a rules word is the case this
    exists for -- a trait called "Aquatic" whose text reads "in aquatic
    combat", or one called "Cold" that explains what cold does. Matching the
    name took out the only word the row was about.
    """
    from combat_engine.engine.types import (
        Condition,
        DamageType,
        Defense,
        Keyword,
        Size,
        Speed,
    )

    words: set[str] = set(RULES_TERMS)
    for enum in (DamageType, Condition, Keyword, Defense, Size, Speed):
        for member in enum:
            words.add(str(member.value).lower())
    # Terrain and the creature vocabulary a stat block's type line prints.
    words |= {
        "aquatic", "underwater", "underground", "difficult", "terrain",
        "natural", "elemental", "fey", "shadow", "immortal", "aberrant",
        "beast", "humanoid", "animate", "magical", "living", "undead",
        "construct", "swarm", "insubstantial", "phasing", "regeneration",
        "tiny", "small", "medium", "large", "huge", "gargantuan",
        "artillery", "brute", "controller", "lurker", "skirmisher",
        "soldier", "minion", "elite", "solo", "leader",
    }  # fmt: skip
    for term in list(words):
        words.update(term.split())
    return frozenset(words)


def mechanical() -> frozenset[str]:
    """Every word the engine itself has a name for. Public for the ETL,
    which needs it to decide whether a creature's *name* is really just
    rules terms and must not be swapped for an id."""
    return _MECHANICAL_WORDS()


def scrub(
    body: str,
    replacements: dict[str, str],
    keep: set[str] | None = None,
    *,
    by_word: dict[str, str] | None = None,
) -> str:
    """Swap each printed name for the id of whatever it names.

    An ability's name maps to that ability's own id rather than the stat
    block's, so "makes three <name> attacks" still says *which* attack -- the
    first version pointed every cross-reference at the monster and threw that
    away.

    Longest first, so a three-word disease name is caught before the two-word
    monster name inside it leaves a fragment behind. Possessives look after
    themselves: the trailing `'s` simply survives the substitution.

    `replacements` are swapped **as whole phrases only**. `by_word` are
    swapped a word at a time as well, and the distinction matters:

    * A **stat block refers to itself by a fragment of its own name.** A
      two-word monster whose first word is its type writes "the <type>
      shifts 1 square" using that half, and "the <other half>'s previous
      space" using the other -- never the full name. So a monster's name has
      to come apart. `m237` is the worked example: both halves appear alone
      in its own rules text and neither is the whole name.
    * An **ability never refers to itself by a fragment.** A trait whose
      name ends in a damage type is not written as "the cold" anywhere --
      but its rules text says *"whenever it takes cold damage"*, and taking
      the name apart deleted the one word the row was about. Ability and
      power names are therefore matched whole and left alone otherwise.

    Words in `keep` are never swapped even out of a name: a monster's role,
    size, origin and type are printed beside its numbers because they are
    mechanical, and a creature named after its own type should not have the
    type scrubbed out of its rules.
    """
    out = body
    kept = {w.lower() for w in (keep or set())} | _NOISE | _MECHANICAL_WORDS()
    usable: dict[str, str] = {
        name: ref
        for name, ref in replacements.items()
        if name and len(name) > 2 and name.lower() not in kept
    }
    for name, ref in (by_word or {}).items():
        if not name:
            continue
        for token in {name, *re.findall(r"[A-Za-z]+", name)}:
            if len(token) > 2 and token.lower() not in kept:
                usable.setdefault(token, ref)
    # Only the names that are actually in this text. The index of every
    # creature in the compendium is four thousand entries, and running a
    # regex for each against every spec is twenty-four million
    # substitutions -- a two-second build became minutes. A lowercase
    # substring test rejects all but a handful first.
    # **Either apostrophe.** The index holds a straight one and the printed
    # prose a curly one, so a two-word name with an apostrophe in it never
    # matched at all -- the name survived into what an agent is shown, and the
    # row that wanted to *name* that power was recorded as unwritable for
    # want of a ref it could have had. The pre-filter and the pattern both
    # have to be flexible or the cheap test rejects it before the regex
    # ever runs.
    here = _straight(out.lower())
    for name in sorted(usable, key=len, reverse=True):
        if _straight(name.lower()) not in here:
            continue
        out = re.sub(_apostrophes(name), usable[name], out, flags=re.I)
        here = _straight(out.lower())
    return out


def _straight(text: str) -> str:
    return text.replace("\u2019", "'")


def _apostrophes(name: str) -> str:
    """One name as a pattern that accepts either apostrophe.

    One pass, not two chained replaces: the second rewrote the curly
    quote **inside the character class the first had just inserted** and
    produced a nested one, which matches nothing.
    """
    return r"\b" + re.sub(r"['\u2019]", "['\u2019]", re.escape(name)) + r"\b"


def flavour(document: str) -> str:
    """The prose `power_spec` throws away.

    The two halves are cut from the same page and neither should be derived
    twice, so what one keeps the other drops: any paragraph *without* a
    mechanical label, plus the italic line under the title. It goes to the
    localisation file, beside the name, and the engine never sees either.
    """
    from .html import detail

    body = detail(document)
    lines: list[str] = []
    for cls, para in paragraphs(body):
        if "publishedIn" in cls or "powerstat" in cls:
            continue
        pair = labelled(para)
        if pair is not None and pair[0].lower().strip() in MECHANICAL:
            continue
        flat = text(para)
        # Stat-block furniture reuses the flavour class. None of it is prose.
        if flat and not re.match(
            r"^(alignment|skills|equipment|str |dex |con |int |wis |cha |hp |ac |initiative)",
            flat,
            re.I,
        ):
            lines.append(flat)
    return "\n".join(lines).strip()


#: An item head line whose label is read straight into a column of `item`.
#: The **base-item line is not here**, and cannot be: its label is a
#: different phrase on every page -- `Weapon`, `Neck Slot`, `Divine Boon`,
#: 32 of them in the heroic tier -- and one of those phrases is also the
#: printed name of an item, so writing the list into tracked source would be
#: a leak as well as a thing to keep feeding. It is found by position below.
_ITEM_COLUMNS = ("enhancement bonus", "critical")


def item_spec(document: str, ref: str, name: str) -> str:
    """One item's mechanical lines, or one Property or Power block of one.

    The same routine does both, because an item's head and its blocks are
    written in the same dialect and only differ in what has to come out. It
    is therefore called on a fragment as often as on a page; `detail()`
    hands back whatever it was given when there is no page furniture.

    **The base-item line is dropped by position, not by label** -- it is
    always the first labelled line on a *page*, and a block never has an
    `<h1>` because the caller cuts at the second one. Matching it by label
    would mean listing every phrase the books use for "what this goes on",
    which is 32 phrases and one printed name.

    Labels are read with `<i>` allowed as well as `<b>`: the item dialect
    writes `<i>Trigger:</i>`, and reading it with the default dropped every
    line of every Power block as flavour.
    """
    from .html import detail

    body = detail(document)
    page = "<h1" in body
    body = re.sub(r"<h1\b.*?</h1>", " ", body, flags=re.S)
    body = re.sub(r'<table class="magicitem">.*?</table>', " ", body, flags=re.S)
    # A Properties block lists its entries as `<li>`, which `paragraphs` does
    # not look for at all -- 103 blocks came out empty until these were made
    # paragraphs first.
    body = re.sub(r"<li\b[^>]*>", '<p class="mistat">', body)

    lines: list[str] = []
    labels = 0
    for cls, para in paragraphs(body):
        if "publishedIn" in cls or "miflavor" in cls:
            continue
        pair = labelled(para, ("b", "i"))
        if pair is None:
            flat = text(para)
            if flat:
                lines.append(flat)
            continue
        labels += 1
        label = pair[0].lower().strip()
        if (page and labels == 1) or label in _ITEM_COLUMNS:
            continue
        lines.append(f"{pair[0]}: {pair[1]}".strip())
    kept = [line for line in lines if line.strip()]
    return scrub("\n".join(kept), {name: ref})


def power_spec(document: str, ref: str, name: str) -> str:
    """One power's mechanical lines, with nothing an agent must not see.

    Keeps `powerstat` paragraphs outright -- they are the usage, keywords,
    action and range -- plus any paragraph carrying a mechanical label. Drops
    the heading, the italic flavour line, and the publication footer.
    """
    from .html import detail

    body = detail(document)
    lines: list[str] = []

    # The `<h1>` holds "Fighter Attack 1" beside the name. The span is worth
    # keeping; everything outside it is the name.
    level = re.search(r'<h1[^>]*>.*?<span class="level">(.*?)</span>', body, re.S)
    if level:
        lines.append(text(level.group(1)))

    for cls, para in paragraphs(body):
        if "publishedIn" in cls:
            continue
        pair = labelled(para)
        # **A bold label is itself the signal.** The allow-list only held
        # the labels somebody had thought of, and a card's build-specific
        # riders are open-ended -- every class names its own. So the
        # swordmage's three aegis riders, the runepriest's runes, the
        # warlock's five pacts, 28 sustain lines and 9 instinctive
        # effects were all dropped as flavour: roughly a hundred printed
        # clauses across ninety rows, on rows already written.
        #
        # Real flavour carries no label; it is unlabelled italic prose.
        # `MECHANICAL` stays because `leaks.py` reads it and because it
        # still answers "is this word mechanics" elsewhere.
        label = pair[0].lower().strip() if pair else ""
        mechanical = bool(pair) and not any(label.startswith(x) for x in _FOOTERS)
        if "powerstat" in cls and not mechanical:
            # The usage, keywords, action and range, which carry no label of
            # their own -- `Encounter Martial / Standard Action / Melee 1`.
            # This block opens with a bold word, so a label test throws it
            # away, which cost every power its range line until it was caught.
            flat = text(para)
            if flat:
                lines.append(flat)
            continue
        if mechanical:
            lines.append(f"{pair[0]}: {pair[1]}".strip())

    # The compendium appends its own errata notes -- "Update (1/24/2012)",
    # "Updated in Class Compendium". They are about the page, not the power.
    kept = [
        line
        for line in lines
        if line.strip() and not re.match(r"^\s*Update", line, re.I)
    ]
    return scrub("\n".join(kept), {name: ref})


# --------------------------------------------------------------------------
# Is a phrase a *name*, or is it just words?
#
# This lives here rather than in `scripts/leaks.py`, where it was written,
# because two things need the same answer and they must not drift: the
# checker that reports a leak, and the ETL scrubber that prevents one. They
# disagreed exactly once, and the disagreement was silent -- the scrubber's
# test was the stricter, so it skipped the names the checker then reported,
# and 124 specs went to authors with somebody else's printed name in them.
# --------------------------------------------------------------------------

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
#:
#: **Two closed compounds back in it**, for the component-word pass (#338).
#: Each is the whole printed name of one row *and* an everyday compound, and
#: the rule that would clear them automatically -- two dictionary halves --
#: also clears five printed names, so `ordinary` refuses to make it. Both have
#: been read:
#:
#: * `shortcut`: used in `scripts/audit.py` about the harness, and in one feat
#:   docstring about the clause it skips. Neither is about the row it collides
#:   with.
#: * `lockdown`: used in one plan file about a tactical pattern.
#: * `spellbook`: the object a wizard's rows read and write, in 14 files. It is
#:   part of three printed names and is itself the mechanical noun -- the same
#:   case as a creature's type word, which `_type_words` excuses for the same
#:   reason.
#: * `campsite`: part of three printed names and an everyday word; used once,
#:   about where a rest happens.
#:
#: This list goes wrong by staying quiet, which is why each entry names where
#: it is used and why -- the same argument `REVIEWED` in `scripts/leaks.py`
#: makes for itself.
ALLOWED: set[str] = {"shortcut", "lockdown", "spellbook", "campsite"}


#: The system word list, where there is one. `builder`, `dispatch` and
#: `stable` are all published ability names and all ordinary English, and no
#: amount of counting tells those apart from an invented name -- a
#: dictionary does it in one lookup. Absent on some machines, hence the fallbacks.
DICTIONARY = Path("/usr/share/dict/words")

#: Webster's hyphenated and multi-word entries, beside the single words above.
#: `low-light` is in here and in no stat block's vocabulary, so without it a
#: perfectly ordinary compound reads as invented. 76,205 entries.
DICTIONARY_PHRASES = Path("/usr/share/dict/web2a")


@lru_cache(maxsize=1)
def english() -> frozenset[str]:
    """Every word the system lists, both files, lowered."""
    out: set[str] = set()
    for path in (DICTIONARY, DICTIONARY_PHRASES):
        if path.exists():
            out.update(
                w.strip().lower()
                for w in path.read_text(errors="ignore").splitlines()
                if w.strip()
            )
    return frozenset(out)


#: Suffix pairs: strip the first, add the second, look the result up.
_INFLECTIONS = (
    ("s", ""), ("es", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
    ("d", ""), ("er", ""), ("ers", ""), ("est", ""), ("ly", ""),
    ("ies", "y"), ("ied", "y"), ("iest", "y"), ("ier", "y"),
)

#: A consonant that doubles before `-ed`, `-ing`, `-er`: planning, rigged.
_DOUBLED = re.compile(r"^(.*?)([bdfglmnprt])\2(ed|ing|er|est)$")


def ordinary(word: str) -> bool:
    """Is this an ordinary English word -- **inflections and all**?

    `word in english()` is not enough and the gap is not academic. The system
    list is Webster's Second: it holds `create` and `shake` and not `created`
    or `shakes`, holds `plan` and not `planning`, `rig` and not `rigged`. Each
    of those inflections is also some row's printed name, and each is a word
    anybody writing a docstring will use -- so a bare membership test reports
    twenty coincidences for every real find. Measured when the `common_word`
    guard first went in: **20 of its first 25 findings were that mistake.**

    `_stem` below is not this. It is crudely singular, for the possessive
    inside a phrase, and deliberately does not reach a participle.

    **A closed compound is not tested**, and the reason is worth keeping:
    splitting a word into two dictionary halves does clear `shortcut` and
    `lockdown`, and it equally clears `runepriest`, `swordmage`,
    `battlemind`, `weaponmaster` and `winterkin` -- every one of which is a
    printed name, because an invented name in this corpus is very often two
    ordinary words joined. A rule that cannot tell those apart is worse than
    the two coincidences it would fix, so the coincidences go in `ALLOWED`
    having been read, and this stays strict. A hyphen *is* honoured, because
    `web2a` lists hyphenated entries and the hyphen is the author's own signal
    that the parts are separate words.
    """
    words = english()
    if word in words:
        return True
    for suffix in ("'s", "s'", "n't", "'"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return ordinary(word[: -len(suffix)])
    parts = [p for p in word.split("-") if p]
    if len(parts) > 1 and all(_inflected(p, words) for p in parts):
        return True
    return _inflected(word, words)


def _inflected(word: str, words: frozenset[str]) -> bool:
    if word in words:
        return True
    for suffix, add in _INFLECTIONS:
        if (word.endswith(suffix) and len(word) > len(suffix) + 2
                and word[: -len(suffix)] + add in words):
            return True
    doubled = _DOUBLED.match(word)
    return bool(doubled and doubled.group(1) + doubled.group(2) in words)


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

    out = set(RULES_TERMS)
    if DICTIONARY.exists():
        out.update(
            w.strip().lower()
            for w in DICTIONARY.read_text(errors="ignore").splitlines()
            if w.strip()
        )
    # An older game.db has no such table.
    with contextlib.suppress(Exception):
        from .build import game

        out.update(r["word"] for r in game().execute("SELECT word FROM common_word"))
    for name in dir(types):
        member = getattr(types, name)
        if isinstance(member, EnumMeta):
            for item in member:
                if isinstance(item.value, str):
                    out.add(item.value.lower().replace("_", " "))
                out.add(item.name.lower().replace("_", " "))
    return out

#: Every name a race holds, lowercased.
#:
#: A race's name is the one printed name that is also a **type word**. The
#: engine asks `is_kind("<type>")`, a monster's own kind is kept out of the
#: scrubber on purpose (`etl/monster.py`), and "the <type> shifts 1 square"
#: is a rules sentence rather than a name. So the set cannot simply be
#: reported wherever it appears -- see `names_a_race` for the one position
#: where the word is a name rather than a type.
#:
#: Injected by the build, which is writing the very table a reader would
#: otherwise have to read -- the same reason `monster.set_common` exists.
#: `scripts/leaks.py` reads it off the finished database instead.
_RACES: frozenset[str] | None = None


def set_races(names: frozenset[str]) -> None:
    """Tell the sanitiser which names are races', during a build."""
    global _RACES
    _RACES = frozenset(n.strip().lower() for n in names if len(n.strip()) > 2)


def races() -> frozenset[str]:
    """Every race's printed name, from the build or from `game.db`."""
    if _RACES is not None:
        return _RACES
    found: set[str] = set()
    # No database, no names file, or an older one with no `race` table.
    with contextlib.suppress(Exception):
        from .build import game, localisation

        names = localisation()
        for (ref,) in game().execute("SELECT ref FROM race"):
            name = (names.get(ref, {}).get("name") or "").strip().lower()
            if len(name) > 2:
                found.add(name)
    return frozenset(found)


#: What follows a race's name when the name is a *name*: the level line
#: every racial card prints above its keywords -- `<r20> Racial Power`,
#: `<r52> Racial Utility 6` -- and the same phrase inside a feat, "you use
#: your <r2> racial power".
_RACIAL = re.compile(r"\s+racial\s+[a-z]", re.I)

#: And a prerequisite clause that is nothing but a race: `Requirement:
#: <r16>, cf:paladin-f0 class feature`. A whole clause, so "you must be
#: an <r4>" -- prose that happens to sit on the same line -- is not one.
_CLAUSE = re.compile(
    r"(?i)^\s*(?:requirements?|prerequisites?)\s*:\s*(?:[^,;]*[,;]\s*)*$"
)
_CLAUSE_END = re.compile(r"\s*(?:[,;.]|$)")

#: And the object of "if you are a ...", which is the third position and reaches
#: prose where the two above only reach a level line and a Requirement.
#:
#: **Second person only, and that is what makes it safe.** Half the races are named
#: after an ordinary English word and every one of those words is also the *type* a
#: stat block prints -- the word `is_kind` is given, which the engine has to be able
#: to say. But nothing on a card ever tells a creature what type it is, so the word
#: after "if you are a" is a race every time. "If the <monster> is a <type>" would
#: not be, and is deliberately not matched.
#:
#: Both apostrophes, because the compendium prints the curly one.
_YOU_ARE = re.compile(r"(?i)\bif\s+you(?:\s+are|\s+were|['\u2019]re)\s+an?\s+$")


@lru_cache(maxsize=4)
def _race_pattern(names: frozenset[str]) -> re.Pattern[str] | None:
    """Every race's name as one alternation, longest first.

    Longest first so a two-word race is matched whole rather than left as
    its second word with the first still standing in front of it. Hyphens
    count as word characters at the edges, so the second half of a
    hyphenated race is not matched on its own.
    """
    if not names:
        return None
    alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w'-])(?:{alts})(?![\w'-])", re.I)


def named_races(context: str) -> list[tuple[int, int, str]]:
    """Every span of this text where a race's name is being used as a name.

    **One rule with one implementation, because two things ask it.**
    `identifies` asks whether a match is worth reporting and
    `build._racial_labels` asks what to replace; if they ever answered
    differently the checker would report a leak the scrubber refuses to
    fix, or -- far worse -- stay quiet about one it never fixed.

    The word alone cannot answer it. Half the races are named after an
    ordinary English word, and every one of those words is also the type
    a stat block prints beside its numbers -- the word `is_kind` is
    given, which the engine has to be able to say. Reporting the set flat
    cost 91 findings across the tree and 358 spec rows, and not one of
    them was a leak.

    **Three** positions admit nothing but a name, which is `_named_powers`'
    argument one step over: directly before the word *racial*, alone in a
    prerequisite clause, and as the object of "if you are a".

    The third was added for #311, where nine rows reached authors with a race
    printed in words while nine more carried the ref in the *same* sentence
    shape -- split by nothing but whether the race happened to be named after a
    dictionary word, since the general scrubber only swaps a one-word name it
    cannot find in a dictionary. `build._racial_labels`' docstring had already
    recorded that consequence for the level line and treated it as settled
    there; prose was not.
    """
    pattern = _race_pattern(races())
    if pattern is None or not context:
        return []
    found: list[tuple[int, int, str]] = []
    for m in pattern.finditer(context):
        if _RACIAL.match(context, m.end()):
            found.append((m.start(), m.end(), m.group(0)))
            continue
        start = context.rfind("\n", 0, m.start()) + 1
        end = context.find("\n", m.end())
        line = context[start:] if end < 0 else context[start:end]
        before = line[: m.start() - start]
        if _YOU_ARE.search(before):
            found.append((m.start(), m.end(), m.group(0)))
            continue
        if _CLAUSE.match(before) and _CLAUSE_END.match(line[m.end() - start :]):
            found.append((m.start(), m.end(), m.group(0)))
    return found


def names_a_race(name: str, context: str) -> bool:
    """Is this word naming a race, or is it a creature's type?"""
    low = name.lower()
    return any(text.lower() == low for _, _, text in named_races(context))


def identifies(
    name: str, refs: list[str], rules: set[str], context: str = ""
) -> bool:
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

    **Except a race's, where the line says it is one.** A race's name is
    one word and usually an ordinary one, so every test below waves it
    through -- and 82 racial cards were printing `<r20> Racial Power`
    with the race spelled out, and nothing reporting it. `context` is the line the name was
    found on, and `names_a_race` is what reads it.
    """
    if names_a_race(name, context):
        return True
    if name in rules or name in ALLOWED or _stem(name) in rules:
        return False
    # **A mechanic with its value is still a mechanic.** `Regeneration` is in
    # `RULES_TERMS` and `Regeneration 5` was not, so the words kept being read as
    # a name: a feat printing "You gain regeneration 5 until the end of the
    # encounter" was handed "You gain x_m5087a1 ...", which says nothing. The
    # same shape covers `Resist 10`, `Aura 2` and anything else the books write
    # as a term followed by a number.
    bare = re.sub(r"\s+\d+$", "", name)
    if bare != name and (bare in rules or bare in ALLOWED or _stem(bare) in rules):
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


def cited(name: str, rules: set[str] | frozenset[str]) -> bool:
    """Can this phrase be a power's name where the position already says
    one is?

    `identifies` asks whether a phrase found in running prose is a name.
    The callers of this one have already answered that from the
    *position* -- a label before a colon, a run in title case, the object
    of *cast* -- and need only the clauses of `identifies` that are about
    the phrase itself, because those hold wherever it was found:

    * a phrase that is itself a rules term is mechanics, never a name;
    * a phrase of nothing but function words is a coincidence, which is
      what the stop list is for -- there is a power called `Not It` and
      "whether or not it has" is not a citation of it;
    * one word is not enough. `identifies` is strictest about a lone
      word for good reason, and no position in this corpus is strong
      enough to overrule it.

    What is deliberately **not** asked is the length clause: two
    ordinary English words in a row are a coincidence in running prose
    and are not a coincidence in these positions, which is the whole
    reason the callers exist.

    Kept beside `identifies` rather than in the ETL so that the checker
    and the scrubber cannot come to hold different opinions.
    """
    if name in rules or _stem(name) in rules:
        return False
    return len([w for w in name.split() if w not in STOPWORDS]) >= 2


def _stem(word: str) -> str:
    """Crudely singular. The dictionary has "narrow", not "narrows", and
    "hunter", not "hunter's" -- and a possessive inside an ordinary phrase
    is what "another hunter's quarry" is."""
    for suffix in ("'s", "s'", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)]
    return word


