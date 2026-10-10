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
    #: The same lines as `spec`, with the names left in. Localisation only.
    rules_text: str = ""
    #: `{printed label: its own ref}` for a clause this ability names as one of
    #: several choices -- "uses one power chosen from the list below". Local to
    #: this ability, which is the whole point. Localisation only.
    sub_options: dict[str, str] = field(default_factory=dict)


@dataclass
class Monster:
    id: int
    level: int = 1
    role: str = ""
    #: The book gives this creature **no combat role**, which is how it marks
    #: something that is not an encounter monster -- an item's conjuration, a
    #: mount, a summoned servant. 222 stat blocks say so and nearly all of
    #: them come out of `Adventurer's Vault`.
    conjuration: bool = False
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
    #: Which of the Monster Manuals this row was printed in: MM1, MM2, MM3,
    #: or empty for anything else. `engine/monster_math.py` needs it to know
    #: what set of maths a row's numbers came from, and therefore what it is
    #: converting from.
    book: str = ""
    #: standard, elite, solo or minion.
    rank: str = "standard"
    #: Which labels were actually found in the source.
    found: set[str] = field(default_factory=set)
    #: For the localisation table only. Never stored in game.db.
    name: str = ""
    description: str = ""

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


#: A monster's `Source` lists every book it ever appeared in, oldest first
#: in practice but not reliably, so the *earliest* of these that is present
#: is the one whose maths its numbers are on.
MANUALS = (("Monster Manual", "MM1"), ("Monster Manual 2", "MM2"),
           ("Monster Manual 3", "MM3"))  # fmt: skip


def book_of(source: str) -> str:
    """Which Monster Manual printed this, if any.

    `Source` is a comma-separated list and a row often names five books, so
    a `LIKE '%Monster Manual%'` matches all three and is useless. The list is
    split and matched exactly.
    """
    listed = {b.strip() for b in (source or "").split(",")}
    for name, tag in MANUALS:
        if name in listed:
            return tag
    return ""


#: The one paragraph on a stat block that is prose: `<p class="flavor">
#: <b>Description</b>: ...`. 344 of 5,326 compendium rows carry it, 156 of them
#: imported, median 258 characters.
#:
#: Matched by its **label**, not its class. Every `<p>` on the page is `flavor`,
#: `flavor alt`, `flavorIndent` or `publishedIn`, so a class tells you nothing
#: here -- which is why `sanitise.description`'s class-based reader returns the
#: whole stat block and why a survey of classes alone concludes, wrongly, that
#: there is no prose.
_DESCRIPTION = re.compile(
    r'<p class="flavor"\s*>\s*<b>\s*Description\s*</b>\s*:?\s*(.*?)</p>',
    re.S | re.I,
)


def _description(body: str) -> str:
    """The stat block's own prose, or nothing.

    Nothing is the common case and the correct one: 2,974 of the 3,130 imported
    monsters print no description, so an empty field is the answer rather than a
    gap for `scripts/localise.py` to report.
    """
    found = _DESCRIPTION.search(body)
    return text(found.group(1)).strip() if found else ""


def parse(
    row_id: int,
    document: str,
    source: str = "",
    others: dict[str, str] | None = None,
    *,
    printed_level: int | None = None,
    printed_role: str = "",
) -> Monster:
    """Parse one stat block.

    `printed_level` and `printed_role` are the compendium's own **columns**,
    handed in because the stat block's text cannot always be trusted for
    either. The level is read out of a `<span class="level">`, and a
    conjuration's block does not carry one -- so fourteen creatures silently
    kept the default of 1 while the column said 4 to 13. A default that is
    also a legal value is invisible, which is why the column wins when the
    text yields nothing.

    `others` maps another creature's printed name to its ref. A stat block
    that references a different creature -- "any <kind> within 10 squares",
    "becomes a <creature>" -- leaked that name into the spec, because the
    scrubber only ever knew this monster's own. Handing the index in turns
    the reference into `m1234`, which is both scrubbed and *more* useful: an
    author can look the id up, where prose told them nothing they were
    allowed to act on.
    """
    body = detail(document)
    m = Monster(id=row_id)
    m.book = book_of(source)
    m.conjuration = printed_role.strip().lower() == "no role"
    _header(m, body, printed_level)
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
    from .sanitise import scrub

    # **A stat block's prose is one labelled paragraph, and the general reader
    # cannot find it.** `sanitise.description` keeps any paragraph without a
    # mechanical label and filters furniture by a list of line *prefixes* --
    # `alignment|skills|equipment|str |hp |ac |...`. That works on a power page
    # and cannot work here: a monster's whole page is `flavorIndent`,
    # `flavor alt` and `flavor`, its trait bodies start with none of those words,
    # and 33,588 of its paragraphs carry no label at all, so nothing filters
    # them.
    #
    # Measured: 2,662 of 3,129 monster entries (**85%**) held a mechanical label,
    # median 673 characters against a power's 94. `m217`'s was 1,005 characters
    # of its own stat block -- a **third** copy of text already held as columns
    # (`level`, `hp`, `ac`, `fort`) and as 973 characters of `monster_power.spec`,
    # sitting in the one field reserved for prose.
    #
    # **But the page does carry prose, on 344 of 5,326 rows:** a `<b>Description</b>`
    # label inside a `flavor` paragraph, median 258 characters, 156 of them
    # imported. I first wrote `m.description = ""` here on the strength of a
    # 120-page sample that showed four `<p>` classes and no lore class -- which
    # was true about *classes* and wrong about prose, because this is found by
    # its **label**. At 6% of rows a 120-page sample expects seven hits and I
    # had not looked for them. It would have discarded all 156.
    #
    # So: the labelled description, and nothing else. #348.
    m.description = _description(body)

    # Only the stat block's own name comes apart into words -- it is the one
    # thing that refers to itself by a fragment. An ability named "Sensitive
    # to Cold" is matched whole, so the word `cold` survives in the sentence
    # that explains what it does.
    # **Its own abilities first.** `others` is every creature's names, and
    # seeding it first meant `setdefault` refused to let a creature's own
    # ability win a name it shares -- so every dragon in the game had its
    # bloodied-breath trait rewritten to point at the *first* dragon's
    # breath weapon, because they are all called the same thing. A monster
    # interacting with another monster's ability should be vanishingly
    # rare; sharing a name is not the same as sharing an ability.
    swaps: dict[str, str] = {}
    for a in m.abilities:
        # **Not a one-word name that is ordinary English.** An ability
        # called "Squeeze" turned every printed *verb* squeeze into its
        # ref, so a swarm's trait read "it can m6685a0 through any
        # opening" -- the word the sentence was about, replaced by an id.
        # 3,313 single-word ability names are common English, so this is
        # not one creature being unlucky.
        if len(a.name.split()) == 1 and a.name.lower() in _COMMON():
            continue
        swaps.setdefault(a.name, f"{m.ref_id}a{a.index}")
    # And a word of this creature's **own name** beats another creature's
    # ability spelled the same. The Chain Devil's rules said "the
    # <another creature's Chain ability> chain devil", because `by_word`
    # takes the name apart and then loses to whatever `others` already
    # holds. Dropping the clash here is what lets the name win.
    #
    # **A contiguous run of my own name, not only a single word of it** --
    # which is the same widening `sanitise.scrub` needed for #379 and for the
    # same reason. A specialised creature's short form is usually *two* of its
    # words, and that run is frequently another creature's whole name: 262
    # names in the corpus contain another creature's full name, because the
    # corpus is full of "<adjective> <base creature>" and "<base creature>
    # <role>". With only the single words dropped, the run stayed in `others`
    # and won, so the card's self-reference came out as the **base creature's
    # ref** -- 147 rows across 82 creatures.
    #
    # `m148a3` is the proof, and it holds both answers in one sentence:
    # *"attacks have a 50% chance to miss the m148. The effect ends when the
    # m147 is hit by an attack"* -- one creature, one sentence, its own ref
    # and a stranger's. `m5584a1` is the inverted one: *"a m5585 can walk on
    # m5584 as though it were solid ground"*, where the creature's own ref
    # landed on the terrain and the stranger's on the creature.
    #
    # Every one of the 147 reads as the creature talking about itself, checked
    # including the 14 that sit beside a plural or an "ally" and so could have
    # been "others of my kind": `m2640a1` says *"the m2654 or an ally of the
    # m2640's choosing"*, which is one captain twice. Swarm counts like
    # `m3831a3`'s *"at least two other <my kind> within 5 squares"* mean others
    # of **this** stat block, so this ref is the right answer there too. #378.
    #
    # Letters rather than ASCII letters, because an accented name came apart at
    # the accent and the fragment matched nothing -- `scrub` carries the same
    # fix and the note explaining it.
    _mine = re.findall(r"[^\W\d_]+", m.name)
    mine = {w.lower() for w in _mine} | {
        " ".join(_mine[i:j]).lower()
        for i in range(len(_mine))
        for j in range(i + 2, len(_mine) + 1)
    }
    for name, ref in (others or {}).items():
        if name.lower() in mine:
            continue
        # **A stranger's ability is not something this creature's rules can
        # mean.** `others` carries ability names as well as creature names --
        # `build._creature_names` indexes both, on the sound grounds that an
        # ability's name leaks exactly as a creature's does. The unsound half
        # was the pointer: "with its tentacles", "must be in ooze form",
        # "makes one fullblade attack" are ordinary nouns, and each resolved
        # onto whichever creature happened to own an ability spelled that
        # way. 103 specs said a monster uses somebody else's power (#175).
        #
        # A **sibling** ability of this creature is kept -- that is the common
        # and correct case, and the whole reason the index holds abilities.
        #
        # A stranger's is demoted to that creature's own ref rather than
        # dropped, because dropping it leaves the printed name in the spec and
        # `leaks.py --specs` goes red: a leak is worse than a vague pointer.
        # A bare creature ref is the sanctioned form for exactly this -- "a
        # spec that names another creature names its id instead" -- so the
        # spec ends up saying a name was here and whose, without claiming a
        # power this creature does not have.
        stranger = re.match(r"^(m\d+)a\d+$", ref)
        if stranger and stranger.group(1) != m.ref_id:
            ref = stranger.group(1)
        swaps.setdefault(name, ref)
    # What is printed beside the numbers is mechanics, not prose, and several
    # creatures are named after their own type. Scrubbing "goblin" out of a
    # goblin's rules would hide a word the spec already prints in its tags.
    keep = {m.role, m.size, m.origin, m.kind, "minion", "elite", "solo", "leader"}
    for a in m.abilities:
        # **The printed lines, taken before the scrub.** This is the only place
        # the unscrubbed text exists, and the localisation wants it: `a.spec` is
        # about to become the same lines with this creature's name swapped for
        # its ref, so taking it here makes the two one extraction rather than
        # two readers that can come to disagree about the rules. #349.
        a.rules_text = a.spec
        # **This ability's own choices get refs inside this ability**, and they
        # win the scrub outright. A stat block never reaches for another
        # creature's power -- a monster power belongs hierarchically to the
        # monster printing it -- so a name labelling one of its clauses can only
        # be its own.
        #
        # Without this they fell to `others` and came out as a *stranger's* bare
        # creature ref: four distinct choices on one satyr's pipes all read
        # `m5592:`, which is another creature that happens to print the same
        # four, so an author could not tell which line was which. #353.
        a.sub_options = _sub_options(a, f"{m.ref_id}a{a.index}")
        a.spec = scrub(a.spec, {**swaps, m.name: m.ref_id, **a.sub_options}, keep,
                       by_word={m.name: m.ref_id})
        # The keywords too. A fifth of them are whole printed sentences --
        # "recharges after the use of <a power's name>", "when a melee
        # attack misses the <creature's name>" -- because the parenthesised
        # group they come from carries the trigger line as well as the
        # keywords. `spec.py` prints them verbatim, so every agent since
        # the project began has been shown names in that field while the
        # body beside it was scrubbed. That is the one rule the project
        # cannot break.
        a.keywords = tuple(
            scrub(k, {**swaps, m.name: m.ref_id, **a.sub_options}, keep,
                  by_word={m.name: m.ref_id})
            for k in a.keywords
        )
    return m


#: A clause label on its own line, with any trailing keyword group left out of
#: the name. A choice is sometimes printed `<its name> (Fire):`, and the
#: parenthesis holds the damage type rather than part of what it is called --
#: so keeping it would mint two refs for one choice on the pages that print it
#: and one on the pages that do not.
#:
#: (An earlier draft of this comment spelled such a name as the example, and
#: `leaks.py` reported it. That is the check working: the name belongs in
#: `localization/`, and it is there now, which is the whole point of #353.)
# `\u2019` spelled as an escape: the source uses a curly apostrophe and a
# literal one here trips ruff's ambiguous-character rule.
_SUB_LABEL = re.compile(
    "^([A-Z][\\w '\u2019/-]{1,40}?)\\s*(?:\\([^)]*\\))?\\s*:", re.M
)

#: The longest a choice's name runs. Four words covers every one in the corpus;
#: the thing on the other side of the line is a **sentence** -- one stat block
#: labels an attack with its own flavour, five words of it -- and a sentence is
#: not a name, so minting a ref for it would put an id where prose belongs.
_SUB_WORDS = 4


def _sub_options(a: Ability, ref: str) -> dict[str, str]:
    """`{printed label: its own ref}` for the choices this ability offers.

    **Structural, and it spells no printed name.** A choice is a labelled line
    whose label is not one of the rules' own labels, which `mechanical_label`
    answers from an allow-list for the reason `_slot`'s is one: writing down the
    names to refuse would be the leak.

    Numbered by order of appearance -- deterministic from the page -- and
    suffixed `s0`, `s1` the way a race's "choose one" family already is, because
    it is the same idea: option N of one entry.
    """
    from .sanitise import mechanical_label

    out: dict[str, str] = {}
    for found in _SUB_LABEL.finditer(a.rules_text or ""):
        label = found.group(1).strip()
        if mechanical_label(label) or len(label.split()) > _SUB_WORDS:
            continue
        if label == a.name:
            continue
        out.setdefault(label, f"{ref}s{len(out)}")
    return out



#: Words the corpus uses widely enough to be English rather than a name.
#: Injected by the build rather than read back off disk: the table lives
#: in the database the build is *writing*, so a reader saw an empty table
#: on a clean run and the previous run's on a rebuild -- the output
#: depended on what was already there, which is the one thing a build
#: must not do.
_COMMON_WORDS: frozenset[str] = frozenset()


def set_common(words: frozenset[str]) -> None:
    """Tell the parser which words are ordinary English."""
    global _COMMON_WORDS
    _COMMON_WORDS = words


def _COMMON() -> frozenset[str]:
    return _COMMON_WORDS


def _header(m: Monster, body: str, printed_level: int | None = None) -> None:
    """`<h1>` carries the name, the type line and the level line.

    `printed_level` is the compendium's own column, and it wins when the block
    carries no level line -- see `parse`.
    """
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

    # The column first, so a block with no level line keeps a real level
    # rather than the default. `first_int` then lets the text refine it.
    if printed_level:
        m.level = printed_level
    level_line = re.search(r'<span class="level">(.*?)</span>', inner, re.S)
    if level_line:
        line = text(level_line.group(1))
        m.level = first_int(line, printed_level or 1)
        low = line.lower()
        m.minion = "minion" in low
        m.leader = "leader" in low
        m.elite = "elite" in low
        m.solo = "solo" in low
        m.rank = ("solo" if m.solo else "elite" if m.elite
                  else "minion" if m.minion else "standard")
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
                # **A real damage type, or nothing.** A swarm prints
                # "Vulnerable 10 to close and area attacks" -- a
                # resistance conditioned on the *shape* of the attack
                # rather than on a type -- and the pattern happily read
                # the word "to" as the type, giving every such creature a
                # `{"to": 10}` that nothing could ever match. The
                # conditional half is not modelled; inventing a damage
                # type for it is worse than leaving it out, because the
                # spec then prints "Resist 10 to" to whoever reads it.
                if kind.lower() in _DAMAGE_TYPES():
                    into[kind.lower()] = int(amount)
    immune = re.search(r"\bImmune\b\s*(.+)", flat, re.I)
    if immune:
        m.immune = tuple(
            w.strip().lower() for w in immune.group(1).split("\n")[0].split(",") if w.strip()
        )
    senses = re.search(r"\bSenses\b\s*(.+)", flat, re.I)
    if senses:
        m.senses = senses.group(1).split("\n")[0].strip()



def _DAMAGE_TYPES() -> frozenset[str]:
    """Every damage type the engine has a name for."""
    from combat_engine.engine.types import DamageType

    return frozenset(d.value for d in DamageType)

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

#: `Recharge <img src="images/symbol/5a.gif">` -- the die faces as a picture,
#: with the threshold in the filename. Allows tags between the word and the
#: image, because the later dialect sometimes closes a `<b>` in between.
_RECHARGE_GLYPH = re.compile(
    r"recharge\s*(?:<[^>]*>\s*)*?<img[^>]*?/symbol/(\d)", re.I
)

#: `Recharge 5`, `Recharge on a 6`. **The digit must follow the word**, which
#: is the whole fix here: the pattern was `recharge\D*(\d)`, and `\D*` crosses
#: a whole sentence -- so "recharges when the aura is aura 1" parsed as
#: `recharge=1`, which on a d6 is *every turn*, and "recharges when it drops
#: to 0 hit points" parsed as `recharge=0`, which `actions.recharge` skips so
#: the power never returned. 81 rows were reading a digit out of their own
#: condition's prose. #335.
_RECHARGE_DIGIT = re.compile(r"recharge\s*(?:on\s+(?:a\s+)?)?(\d)\b", re.I)
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
    # **The threshold is a picture, and `text()` throws it away.** The
    # compendium prints "Recharge" followed by an `<img>` of the die faces,
    # and the filename is the number: `images/symbol/5a.gif` is "recharge on
    # a 5 or 6". 2,521 of those glyphs are in `Monster.Txt`. Read off `head`,
    # which is raw HTML, because `low` is the scrubbed text and the picture
    # is gone by then -- which is why this looked like a card that printed no
    # threshold rather than one this parser could not see.
    #
    # It matters more than a missing number usually would: the ETL supplied
    # **6** for every one of them, and 6 is 16% of the printed thresholds.
    # The commonest is 5, by four to one, so ~1,500 monster powers were
    # coming back one turn in six where the page says two. #335.
    glyph = _RECHARGE_GLYPH.search(head)
    printed = _RECHARGE_DIGIT.search(low)
    if glyph:
        a.recharge = int(glyph.group(1))
    elif printed:
        a.recharge = int(printed.group(1))
    elif "recharge" in low:
        # **A conditional recharge, and 6 is still invented here.** "Recharge
        # when first bloodied" prints no die at all, and `etl/CLAUDE.md`'s
        # rule says store nothing rather than guess -- but a conditional
        # recharge that parses to no die never comes back, which moves what
        # ~1,000 monsters can do. That is a balance change and wants its own
        # measurement, so it is deliberately left alone here and the glyph
        # half lands on its own.
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
