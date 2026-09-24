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
from .sanitise import power_spec


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
    spec: str = ""
    #: For the localisation table only. Never stored in game.db.
    name: str = ""
    flavour: str = ""

    @property
    def ref(self) -> str:
        return f"p{self.id}"

    @property
    def score(self) -> float:
        checks = [bool(self.spec), bool(self.reach), "\n" in self.spec]
        return sum(checks) / len(checks)


_RANGES = (
    "melee touch", "melee weapon", "melee", "ranged weapon", "ranged",
    "close burst", "close blast", "area burst", "area wall", "personal",
)  # fmt: skip

_KEYWORDS = [
    "martial", "arcane", "divine", "primal", "psionic", "shadow", "weapon", "implement",
    "fire", "cold", "lightning", "thunder", "necrotic", "radiant", "poison", "psychic",
    "acid", "force", "healing", "charm", "fear", "illusion", "teleportation", "conjuration",
    "zone", "stance", "reliable", "invigorating", "rattling", "beast", "form", "polymorph",
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
    )
    body = detail(document)
    p.spec = power_spec(document, p.ref, [p.name])
    p.flavour = read_flavour(document)
    _shape(p, body)
    return p


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
            break

    p.keywords = tuple(w for w in _KEYWORDS if re.search(rf"\b{w}\b", low))
