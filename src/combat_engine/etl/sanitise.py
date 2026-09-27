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

import re
from functools import lru_cache

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

    * A **stat block refers to itself by a fragment of its own name.** It
      writes "the goblin shifts 1 square" and "the blackblade's previous
      space", never the full name, so a monster's name has to come apart.
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
