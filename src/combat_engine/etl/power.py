"""Reading a class power's page.

Almost nothing is derived here. The compendium already keeps a power's class,
level, action and usage in columns, and everything else about it -- what it
actually does -- is for somebody to write as code. So this pulls the few
facts worth indexing on and hands over the sanitised text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .html import detail, text
from .sanitise import flavour as read_flavour
from .sanitise import power_spec, scrub


@dataclass
class Power:
    id: int
    cls: str = ""
    level: int = 0
    usage: str = "at-will"
    action: str = "standard"
    kind: str = ""
    reach: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    #: Every book this power appears in. `Source` is a comma-separated list
    #: and a row often names several, so selecting "the Player's Handbook
    #: ones" is a membership test and not a LIKE.
    books: tuple[str, ...] = field(default_factory=tuple)
    spec: str = ""
    #: For the localisation table only. Never stored in game.db.
    name: str = ""
    flavour: str = ""
    #: Set on a **second card printed inside another power's entry**. The
    #: compendium gives such a card no id of its own, so a row that must
    #: *name* it -- "you regain the use of that form's attack", "the ally
    #: can use <the second stanza>" -- had nothing to point at, and three
    #: rows were recorded as unwritable for want of an id that could
    #: simply be derived.
    suffix: str = ""

    @property
    def ref(self) -> str:
        return f"p{self.id}{self.suffix}"

    @property
    def score(self) -> float:
        checks = [bool(self.spec), bool(self.reach), "\n" in self.spec]
        return sum(checks) / len(checks)


#: Longest first, because the search below takes the first that matches and
#: "melee" is a prefix of three of the others. `melee spirit` has to be here
#: for that reason: 80 cards print it, it means "N squares from the conjured
#: spirit" rather than anything a weapon reaches, and without an entry of its
#: own every one of them was recorded as a bare `melee` -- which then read as
#: a weapon row, so a spirit 5 squares away was swung at with a sword's reach.
_RANGES = (
    "melee touch", "melee weapon", "melee spirit", "melee", "ranged weapon",
    "ranged", "close burst", "close blast", "area burst", "area wall", "personal",
)  # fmt: skip

#: "Melee weapon +1 reach", printed on 10 cards. The bonus is part of the range
#: and was being dropped, so the row reached one square less than it prints.
_BONUS = re.compile(r"\+\s*(\d+)\s*reach")

_KEYWORDS = [
    "martial", "arcane", "divine", "primal", "psionic", "shadow", "weapon", "implement",
    "fire", "cold", "lightning", "thunder", "necrotic", "radiant", "poison", "psychic",
    "acid", "force", "healing", "charm", "fear", "illusion", "teleportation", "conjuration",
    "zone", "stance", "reliable", "invigorating", "rattling", "beast", "form", "polymorph",
    # **A subclass gate, not a mechanic.** Printed on six wizard rows whose trigger
    # only one subclass can meet, and dropped here until now -- so `chargen` had
    # nothing to exclude them by and dealt them to every wizard. #319.
    "bladespell",
]


def parse(row: dict, document: str) -> Power:
    """`row` is the compendium's own columns for this power."""
    p = Power(
        id=row["ID"],
        cls=(row.get("Class") or "").strip(),
        level=row.get("Level") or 0,
        usage=(row.get("Usage") or "at-will").strip().lower(),
        action=(row.get("Action") or "standard").strip().lower(),
        kind=(row.get("Kind") or "").strip(),
        name=(row.get("Name") or "").strip(),
        books=tuple(
            b.strip() for b in (row.get("Source") or "").split(",") if b.strip()
        ),
    )
    body = detail(document)
    p.spec = power_spec(document, p.ref, p.name)
    p.flavour = read_flavour(document)
    _shape(p, body)
    return p



#: Where one entry's cards are separated. 375 rows carry more than one.
_CARD = re.compile(r"<h1\b", re.I)

_USAGES = ("at-will", "encounter", "recharge", "daily")
_ACTION = re.compile(
    r"\b(standard|move|minor|free|opportunity|no)\s+action"
    r"|\b(immediate\s+(?:reaction|interrupt))\b",
    re.I,
)


def parse_extra(row: dict, document: str) -> list[Power]:
    """The second and later cards printed inside one entry.

    A power that grants another prints both on the same page, and the
    compendium files them under one id. The text of both was already
    imported -- what was missing was a **ref for the second**, so
    `c.restore_use` and `c.grant_row` had nothing to name.

    Suffixed `b`, `c`, ... off the parent, which keeps them sorted beside
    it and makes the relationship readable at a glance. The parent's own
    columns are wrong for these -- a standard-action power routinely
    grants a free-action one -- so usage and action are read off the
    card's own stat block instead.
    """
    body = detail(document)
    cuts = [m.start() for m in _CARD.finditer(body)]
    if len(cuts) < 2:
        return []
    out: list[Power] = []
    for n, start in enumerate(cuts[1:], start=1):
        stop = cuts[n + 1] if n + 1 < len(cuts) else len(body)
        card = body[start:stop]
        p = Power(
            id=row["ID"],
            cls=(row.get("Class") or "").strip(),
            level=row.get("Level") or 0,
            kind=(row.get("Kind") or "").strip(),
            books=tuple(
                b.strip() for b in (row.get("Source") or "").split(",") if b.strip()
            ),
            suffix=chr(ord("a") + n),
        )
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", card, re.S)
        whole = text(heading.group(1)) if heading else ""
        # The `<span class="level">` holds "Warden Attack 1"; the name is
        # whatever is left outside it.
        level_span = re.search(r'<span class="level">(.*?)</span>', card, re.S)
        p.name = whole.replace(text(level_span.group(1)), "").strip() if level_span else whole

        flat = text(card).lower()
        for usage in _USAGES:
            if usage in flat:
                p.usage = usage
                break
        act = _ACTION.search(flat)
        if act:
            p.action = (act.group(1) or act.group(2) or "standard").lower()
            p.action = re.sub(r"\s+", " ", p.action)
        p.spec = power_spec(card, p.ref, p.name)
        # And the **parent's** name, which `power_spec` does not know
        # about: a second card almost always names the first ("the
        # <parent> power must be active in order to use this"), and
        # leaving it printed would hand an agent the one thing it must
        # never see.
        parent = (row.get("Name") or "").strip()
        if parent:
            p.spec = scrub(p.spec, {parent: f"p{row['ID']}"})
            # And again allowing an inserted article. Several names are
            # indexed without a "the" that the prose then writes in the
            # middle of them, so a whole-phrase swap misses and the name
            # survives into what an agent is shown. (`leaks.py` caught
            # this comment naming one of them, which is the check doing
            # exactly its job.)
            loose = r"\s+(?:the\s+)?".join(re.escape(w) for w in parent.split())
            p.spec = re.sub(loose, f"p{row['ID']}", p.spec)
        _shape(p, card)
        out.append(p)
    return out

def _shape(p: Power, body: str) -> None:
    """The range line and the keyword list, off the first powerstat block."""
    # Not stopping at `<br>`: the range sits on the line after the usage,
    # separated by exactly one, so stopping there loses it.
    stat = re.search(r'<p class="powerstat">(.*?)(?=<p |$)', body, re.S)
    flat = text(stat.group(1)) if stat else ""
    low = flat.lower()

    for name in _RANGES:
        hit = re.search(rf"\b{name}\b\s*(\d*)", low)
        if hit:
            p.reach = f"{name} {hit.group(1)}".strip()
            if (plus := _BONUS.search(low[hit.end():hit.end() + 20])):
                p.reach += f" +{plus.group(1)} reach"
            break

    p.keywords = tuple(w for w in _KEYWORDS if re.search(rf"\b{w}\b", low))
