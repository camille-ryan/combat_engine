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

from .html import labelled, paragraphs, text

#: Paragraph labels that carry mechanics. Anything else in a `flavor`
#: paragraph is prose and is dropped.
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
}  # fmt: skip


#: Words that appear inside printed names and carry no identity of their own.
#: Scrubbing them would only make a spec harder to read.
_NOISE = {"the", "of", "and", "a", "an", "in", "on", "to", "with", "its", "it"}


def scrub(body: str, replacements: dict[str, str], keep: set[str] | None = None) -> str:
    """Swap each printed name for the id of whatever it names.

    An ability's name maps to that ability's own id rather than the stat
    block's, so "makes three <name> attacks" still says *which* attack -- the
    first version pointed every cross-reference at the monster and threw that
    away.

    Longest first, so a three-word disease name is caught before the two-word
    monster name inside it leaves a fragment behind. Possessives look after
    themselves: the trailing `'s` simply survives the substitution.

    **Single words of a name count as the name.** A stat block does not repeat
    itself in full -- it writes "the goblin shifts 1 square" and "the
    blackblade's previous space", and matching only the whole name left both
    of those standing. Every word is therefore swapped as well, except the
    ones in `keep`: a monster's own role, size, origin and type are printed
    beside its numbers because they are mechanical, and a creature whose name
    contains its type should not have the type scrubbed out of its rules.
    """
    out = body
    # A rules term protects its own words too. "Combat advantage" was safe as
    # a phrase and both halves of it were not, so an ability *named* Combat
    # Advantage turned the sentence describing it into "it has m237a1 m237a1
    # against" -- and a power named after a shield made its own requirement
    # line read "you must be using a p289".
    kept = {w.lower() for w in (keep or set())} | _NOISE
    for term in RULES_TERMS:
        kept.add(term)
        kept.update(term.split())
    usable: dict[str, str] = {}
    for name, ref in replacements.items():
        if not name:
            continue
        for token in {name, *re.findall(r"[A-Za-z]+", name)}:
            if len(token) > 2 and token.lower() not in kept:
                usable.setdefault(token, ref)
    for name in sorted(usable, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(name)}\b", usable[name], out, flags=re.I)
    return out


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
        mechanical = pair is not None and pair[0].lower().strip() in MECHANICAL
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
