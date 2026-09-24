"""Parsing a monster stat block out of HTML, in both dialects.

The compendium holds two layouts. The later one puts the numbers in a
`<table class="bodytable">` and groups abilities under `<h2>Standard
Actions</h2>` headings; the earlier one runs everything together in one
`<p class="flavor">`. Roughly half the heroic-tier monsters are in each, so
both are parsed and the row records which it came from.

A monster's **numbers** are parsed. A monster's **behaviour** is not -- each
ability comes out as sanitised mechanical text for somebody to hand-code,
and the name never comes with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .html import detail, first_int, headings, labelled, paragraphs, text

# --------------------------------------------------------------------------

_ROLES = (
    ["artillery", "brute", "controller", "lurker", "minion", "skirmisher", "soldier"]
)
_SIZES = ["tiny", "small", "medium", "large", "huge", "gargantuan"]
_ORIGINS = (
    ["aberrant", "elemental", "fey", "immortal", "natural", "shadow"]
)


@dataclass
class Ability:
    """One line off a stat block."""

    index: int
    section: str = "standard"
    usage: str = "at-will"
    action: str = "standard"
    recharge: int = 0
    keywords: tuple[str, ...] = ()
    spec: str = ""
    #: Carried only so the localisation table can be built. Never stored in
    #: `game.db` and never handed to anyone writing code.
    name: str = ""


@dataclass
class Monster:
    id: int
    level: int = 1
    role: str = ""
    minion: bool = False
    leader: bool = False
    elite: bool = False
    solo: bool = False
    size: str = "medium"
    origin: str = "natural"
    kind: str = ""
    keywords: tuple[str, ...] = ()
    xp: int = 0
    hp: int = 1
    ac: int = 10
    fort: int = 10
    ref: int = 10
    will: int = 10
    initiative: int = 0
    speed: int = 6
    modes: dict[str, int] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    resist: dict[str, int] = field(default_factory=dict)
    vulnerable: dict[str, int] = field(default_factory=dict)
    immune: tuple[str, ...] = ()
    senses: str = ""
    abilities: list[Ability] = field(default_factory=list)
    dialect: str = ""
    #: Which labels were actually found in the source.
    found: set[str] = field(default_factory=set)
    #: For the localisation table only. Never stored in game.db.
    name: str = ""
    flavour: str = ""

    @property
    def ref_id(self) -> str:
        return f"m{self.id}"

    @property
    def score(self) -> float:
        """How much of this row was found, 0 to 1.

        Measures whether a label was *located*, never whether its value looks
        sensible. A level 1 brute really does have Will 9 and a minion really
        does have 1 hit point, and the first version of this scored both as
        parse failures -- which buried the rows that had actually gone wrong
        under three hundred that had not.

        Not a pass mark. It sorts a coverage report so the worst rows are the
        first ones looked at.
        """
        wanted = {"hp", "ac", "fortitude", "reflex", "will", "speed"}
        checks = [
            *(label in self.found for label in sorted(wanted)),
            len(self.scores) == 6,
            bool(self.abilities),
            bool(self.role),
        ]
        return sum(checks) / len(checks)


# --------------------------------------------------------------------------


def parse(row_id: int, document: str) -> Monster:
    body = detail(document)
    m = Monster(id=row_id)
    _header(m, body)
    if '<h2>' in body and 'class="bodytable"' in body:
        m.dialect = "later"
        _later_stats(m, body)
    else:
        m.dialect = "earlier"
        _earlier_stats(m, body)
    _scores(m, body)
    _abilities(m, body)
    # A stat block names itself in its own rules text, so its name and its
    # abilities' names come out of every spec before anyone sees one.
    from .sanitise import flavour as read_flavour
    from .sanitise import scrub

    m.flavour = read_flavour(document)

    swaps = {m.name: m.ref_id}
    for a in m.abilities:
        swaps.setdefault(a.name, f"{m.ref_id}a{a.index}")
    for a in m.abilities:
        a.spec = scrub(a.spec, swaps)
    return m


def _header(m: Monster, body: str) -> None:
    """`<h1>` carries the name, the type line and the level line."""
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', body, re.S)
    if not h1:
        return
    inner = h1.group(1)
    m.name = text(re.sub(r"<span.*?</span>", "", inner, flags=re.S)).split("\n")[0].strip()

    type_line = re.search(r'<span class="type">(.*?)</span>', inner, re.S)
    if type_line:
        words = text(type_line.group(1)).lower().replace(",", " ").split()
        for w in words:
            if w in _SIZES:
                m.size = w
            elif w in _ORIGINS:
                m.origin = w
        m.keywords = tuple(words)
        if words:
            m.kind = words[-1]

    level_line = re.search(r'<span class="level">(.*?)</span>', inner, re.S)
    if level_line:
        line = text(level_line.group(1))
        m.level = first_int(line, 1)
        low = line.lower()
        m.minion = "minion" in low
        m.leader = "leader" in low
        m.elite = "elite" in low
        m.solo = "solo" in low
        for role in _ROLES:
            if role in low:
                m.role = role
                break
        xp = re.search(r"XP\s+([\d,]+)", line, re.I)
        if xp:
            m.xp = int(xp.group(1).replace(",", ""))


def _numbers(m: Monster, blob: str) -> None:
    """Pull the defences and speeds out of a run of `<b>Label</b> value` text."""
    flat = text(blob)

    def grab(label: str, default: int) -> int:
        hit = re.search(rf"\b{label}\b\s*:?\s*([+-]?\d+)", flat, re.I)
        if not hit:
            return default
        m.found.add(label.lower())
        return int(hit.group(1))

    m.hp = grab("HP", m.hp)
    m.ac = grab("AC", m.ac)
    m.fort = grab("Fortitude", m.fort)
    m.ref = grab("Reflex", m.ref)
    m.will = grab("Will", m.will)
    m.initiative = grab("Initiative", m.initiative)

    speed = re.search(r"\bSpeed\b\s*:?\s*(.+)", flat, re.I)
    if speed:
        line = speed.group(1).split("\n")[0]
        m.found.add("speed")
        m.speed = first_int(line, m.speed)
        for mode, value in re.findall(r"(fly|climb|swim|burrow|teleport)\s*(\d*)", line, re.I):
            m.modes[mode.lower()] = int(value) if value else m.speed

    for label, into in (("Resist", m.resist), ("Vulnerable", m.vulnerable)):
        hit = re.search(rf"\b{label}\b\s*(.+)", flat, re.I)
        if hit:
            for amount, kind in re.findall(r"(\d+)\s+([a-z]+)", hit.group(1).split("\n")[0], re.I):
                into[kind.lower()] = int(amount)
    immune = re.search(r"\bImmune\b\s*(.+)", flat, re.I)
    if immune:
        m.immune = tuple(
            w.strip().lower() for w in immune.group(1).split("\n")[0].split(",") if w.strip()
        )
    senses = re.search(r"\bSenses\b\s*(.+)", flat, re.I)
    if senses:
        m.senses = senses.group(1).split("\n")[0].strip()


def _later_stats(m: Monster, body: str) -> None:
    table = re.search(r'<table class="bodytable">(.*?)</table>', body, re.S)
    if table:
        _numbers(m, table.group(1))


def _earlier_stats(m: Monster, body: str) -> None:
    """The first `<p class="flavor">` holds everything in this dialect."""
    for cls, para in paragraphs(body):
        if "flavor" in cls and "alt" not in cls and re.search(r"<b>\s*HP\s*</b>", para, re.I):
            _numbers(m, para)
            return
    _numbers(m, body)


def _scores(m: Monster, body: str) -> None:
    flat = text(body)
    for ability in ("Str", "Con", "Dex", "Int", "Wis", "Cha"):
        hit = re.search(rf"\b{ability}\b\s*(\d+)", flat)
        if hit:
            m.scores[ability.lower()] = int(hit.group(1))


# --------------------------------------------------------------------------
# Abilities
# --------------------------------------------------------------------------

_USAGES = ("at-will", "encounter", "recharge", "daily")
_ACTIONS = (
    "standard", "move", "minor", "free", "immediate interrupt",
    "immediate reaction", "opportunity", "no action",
)  # fmt: skip

_SECTIONS = {
    "standard actions": "standard",
    "move actions": "move",
    "minor actions": "minor",
    "free actions": "free",
    "triggered actions": "triggered",
    "traits": "trait",
    "skills": None,
}


def _abilities(m: Monster, body: str) -> None:
    """Every `<p class="flavor alt">` names an ability; the indents follow it."""
    section = "standard" if m.dialect == "earlier" else "trait"
    marks = [(off, _SECTIONS.get(t.lower().strip(), section)) for lvl, t, off in headings(body)
             if lvl == 2]

    index = 0
    for match in re.finditer(r'<p class="flavor alt">(.*?)(?=<p |<h2|<br|$)', body, re.S):
        head = match.group(1)
        if _is_footer(head):
            continue
        for off, name in marks:
            if off < match.start() and name:
                section = name
        ability = _one_ability(head, index, section)
        if ability is None:
            continue
        ability.spec = _ability_spec(body, match.end(), head, ability)
        if ability.spec or ability.name:
            m.abilities.append(ability)
            index += 1


def _is_footer(head: str) -> bool:
    """The stat block's closing paragraphs reuse the same class."""
    flat = text(head).lower()
    return any(
        flat.startswith(w)
        for w in ("alignment", "skills", "equipment", "str ", "published", "description")
    )


def _one_ability(head: str, index: int, section: str) -> Ability | None:
    name = re.search(r"<b>(.*?)</b>", head, re.S)
    if not name:
        return None
    a = Ability(index=index, section=section)
    a.name = text(name.group(1)).strip()

    flat = text(head)
    after = flat[flat.find(a.name) + len(a.name):] if a.name in flat else flat
    low = after.lower()

    # "(standard, at-will)" in the earlier dialect; separate bold words in the
    # later one. Reading the whole tail covers both.
    for action in _ACTIONS:
        if action in low:
            a.action = action
            break
    else:
        a.action = {"trait": "none", "triggered": "free"}.get(section, section)
    for usage in _USAGES:
        if usage in low:
            a.usage = usage
            break
    else:
        a.usage = "none" if section == "trait" else "at-will"
    recharge = re.search(r"recharge\D*(\d)", low)
    if recharge:
        a.recharge = int(recharge.group(1))
    elif "recharge" in low:
        a.recharge = 6

    words: list[str] = []
    for group in re.findall(r"\(([^)]*)\)", after):
        for word in group.split(","):
            cleaned = word.strip().lower()
            if cleaned and cleaned not in _ACTIONS and cleaned not in _USAGES:
                words.append(cleaned)
    a.keywords = tuple(dict.fromkeys(words))
    return a


def _ability_spec(body: str, start: int, head: str, a: Ability) -> str:
    """The mechanical lines under one ability, with its name taken out."""
    chunk = body[start:]
    stop = re.search(r'<p class="flavor alt"|<h2', chunk)
    if stop:
        chunk = chunk[: stop.start()]

    lines: list[str] = []
    first = text(head)
    if a.name and first.startswith(a.name):
        first = first[len(a.name):].strip()
    first = first.strip(" -♦")
    if first:
        lines.append(first)

    for cls, para in paragraphs("<p>" + chunk if not chunk.lstrip().startswith("<p") else chunk):
        if "publishedIn" in cls:
            continue
        pair = labelled(para)
        line = f"{pair[0]}: {pair[1]}" if pair else text(para)
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines).strip()
