"""Building `data/game.db` from the compendium.

Destructive and idempotent: the database is recreated from scratch every
run, so the only way to change what is in it is to change a parser.

Two files come out, and **neither is redistributable**. Both are built from
your own copy of the compendium and both are gitignored:

* `data/game.db` -- every row's numbers, plus the mechanical text each was
  written from. The numbers are facts about a game system and not protectable;
  the text is the publisher's sentences, which is why this file does not ship.
  An earlier version of this docstring called it distributable, which was
  wrong the moment the specs went into it.
* `localization/names.json` -- ids to printed names and flavour.

What *is* distributable is `src/` -- the engine and the hand-written content,
which hold ids and mechanics and no prose at all. `scripts/leaks.py` is what
holds them to it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from html import unescape
from pathlib import Path

from . import feat, item, sanitise
from . import monster as monster_parser
from . import power as power_parser

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "compendium.sqlite"
GAME = ROOT / "data" / "game.db"
NAMES = ROOT / "localization" / "names.json"

#: The project's scope, from the README: characters to 10, monsters to 13.
MAX_POWER_LEVEL = 10
MAX_MONSTER_LEVEL = 13
#: The eight Player's Handbook classes. Powers from later books are
#: still ingested for these classes -- the `source` column says which
#: book a row came from, so narrowing to PHB1 is a query and not a
#: rebuild.
#:
#: Every class except the hybrids. The eight Player's Handbook ones came
#: first and were the whole list for a long while; the rest are here so
#: their powers are in the database at all -- a class still needs a
#: `chargen.ClassLine` before any of its rows mean anything.
CLASSES = (
    "Cleric", "Fighter", "Paladin", "Ranger",
    "Rogue", "Warlock", "Warlord", "Wizard",
    "Ardent", "Artificer", "Assassin", "Avenger", "Barbarian", "Bard",
    "Battlemind", "Druid", "Invoker", "Monk", "Psion", "Runepriest",
    "Seeker", "Shaman", "Sorcerer", "Swordmage", "Warden",
)  # fmt: skip

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE monster (
  ref TEXT PRIMARY KEY, id INTEGER, level INTEGER, role TEXT,
  minion INTEGER, leader INTEGER, elite INTEGER, solo INTEGER,
  size TEXT, origin TEXT, kind TEXT, keywords TEXT, xp INTEGER,
  hp INTEGER, ac INTEGER, fort INTEGER, ref_def INTEGER, will INTEGER,
  initiative INTEGER, speed INTEGER, modes TEXT, scores TEXT,
  resist TEXT, vulnerable TEXT, immune TEXT, senses TEXT,
  book TEXT, rank TEXT,
  dialect TEXT, score REAL
);
CREATE INDEX monster_book ON monster(book, level);
CREATE INDEX monster_level ON monster(level, role);

CREATE TABLE monster_power (
  ref TEXT PRIMARY KEY, monster_ref TEXT, idx INTEGER, section TEXT,
  usage TEXT, action TEXT, recharge INTEGER, keywords TEXT, spec TEXT
);
CREATE INDEX monster_power_owner ON monster_power(monster_ref);

CREATE TABLE common_word (
  word TEXT PRIMARY KEY, documents INTEGER
);

CREATE TABLE power (
  ref TEXT PRIMARY KEY, id INTEGER, class TEXT, level INTEGER,
  usage TEXT, action TEXT, kind TEXT, reach TEXT, keywords TEXT,
  books TEXT, spec TEXT, score REAL
);
CREATE INDEX power_class ON power(class, level);

CREATE TABLE class (
  name TEXT PRIMARY KEY, role TEXT, source TEXT,
  hp_first INTEGER, hp_per_level INTEGER, surges INTEGER,
  defences TEXT, armour TEXT, weapons TEXT, implements TEXT,
  abilities TEXT
);

-- The features themselves, which `class` above never carried. Only the
-- chassis numbers were read off the page, so every `cf:` ref in the tree
-- was written from a paraphrase or guessed outright -- and `spec.py`
-- answered "no such row" for all of them, which read as "this feature
-- has no printed text" rather than "nobody imported it".
--
-- Keyed by page order rather than by name: the name is trademarked and
-- lives in `localization/names.json` with every other printed name, so a
-- ref can be written into tracked source and `leaks.py` stays honest.
-- Familiars and beast companions, never imported. `c.familiar()` and the
-- three rows that call it were written against no text at all, and the
-- eleven beast companions carry the full stat block -- ability scores,
-- defences, hit points, attack bonus -- that the ranger's beast rows and
-- `cf:ranger-style-beast` were blocked on.
CREATE TABLE companion (
  ref TEXT PRIMARY KEY, kind TEXT, spec TEXT
);

-- Which powers a build's own page lists. The Essentials builds print
-- their whole set on the class page and mark almost none of it as a
-- feature -- only 2 of 24 pages use a "Feature" card at all -- so this
-- is deliberately a build-to-power map and NOT a feature list. It is
-- what `chargen.BUILDS` has been guessing at.
CREATE TABLE build_power (
  class TEXT, build TEXT, ref TEXT, PRIMARY KEY (class, build, ref)
);

CREATE TABLE class_feature (
  ref TEXT PRIMARY KEY, class TEXT, ord INTEGER, build TEXT, spec TEXT
);
CREATE INDEX class_feature_class ON class_feature(class, ord);

-- Magic items. **One row per compendium entry, not per rung of its
-- ladder.** Most heroic items are printed as a family -- `Lvl 1 +1 / Lvl 6
-- +2 / Lvl 11 +3` -- and 863 of them have two rungs inside heroic alone.
-- Their rules text is identical at every rung, so a row per rung would
-- mean 863 duplicated hand-written functions, a work list half again as
-- long with nothing new in it, and two refs that must never disagree.
-- Which rung you are holding is three numbers, and numbers load from the
-- database by standing rule.
--
-- `base` is the printed base-item restriction, `Weapon: Heavy blade or
-- light blade`. It is the whole reason a magic item is not a new weapon:
-- the item says which existing weapons it may be laid on top of.
CREATE TABLE item (
  ref TEXT PRIMARY KEY, id INTEGER, category TEXT, slot TEXT, rarity TEXT,
  base_level INTEGER, scaling INTEGER, base TEXT, enh_to TEXT, crit TEXT,
  books TEXT, spec TEXT, score REAL
);
CREATE INDEX item_level ON item(base_level, category);

-- Every rung the ladder prints: which level it appears at, what plus it
-- is, what it costs. This is what treasure-by-level queries.
CREATE TABLE item_step (
  ref TEXT, level INTEGER, plus INTEGER, cost INTEGER,
  PRIMARY KEY (ref, level)
);
CREATE INDEX item_step_level ON item_step(level);

-- One Property or one Power off an item's page. **This is the unit of
-- work**, not the item: 1,877 heroic items carry 2,294 of these between
-- them and 106 items have more than one Power. Without a ref each,
-- `coverage.py` cannot see a half-written item.
CREATE TABLE item_block (
  ref TEXT PRIMARY KEY, item_ref TEXT, idx INTEGER, kind TEXT,
  usage TEXT, action TEXT, keywords TEXT, spec TEXT
);
CREATE INDEX item_block_owner ON item_block(item_ref);

-- Feats. `prereq` is a JSON expression tree of atoms and never prose --
-- see `feat.py`, and note that `unparsed` counts the atoms that could not
-- be structured rather than keeping their text, because the text is a
-- deity's name as often as not.
CREATE TABLE feat (
  ref TEXT PRIMARY KEY, id INTEGER, tier TEXT, min_level INTEGER,
  prereq TEXT, unparsed INTEGER, books TEXT, spec TEXT
);
CREATE INDEX feat_tier ON feat(tier, min_level);

-- Races, which nothing in the engine has ever had. 690 of 1,675 heroic
-- feats gate on one, and the racial powers are already in `power` -- the
-- compendium files them under the race in its Class column.
CREATE TABLE race (
  ref TEXT PRIMARY KEY, id INTEGER, size TEXT, scores TEXT, spec TEXT
);

-- A prerequisite clause that is a printed name rather than a mechanic: a
-- race, a deity, a regional background. Keyed on a **global** dictionary
-- of clause texts rather than per feat, so that answering "must worship
-- <name>" once answers all ten feats that ask it.
CREATE TABLE prereq_term (
  ref TEXT PRIMARY KEY, kind TEXT, uses INTEGER
);
"""


@dataclass
class Report:
    monsters: int = 0
    abilities: int = 0
    powers: int = 0
    classes: int = 0
    features: int = 0
    seconds: int = 0
    crossed: int = 0
    companions: int = 0
    build_powers: int = 0
    items: int = 0
    item_blocks: int = 0
    item_steps: int = 0
    sets_skipped: int = 0
    feats: int = 0
    feat_cards: int = 0
    races: int = 0
    racial: int = 0
    terms: int = 0
    aliases: int = 0
    unparsed: int = 0
    names: int = 0
    common: int = 0
    scores: dict[str, float] = field(default_factory=dict)
    worst: list[tuple[str, float]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"monsters      {self.monsters:6d}",
            f"  abilities   {self.abilities:6d}",
            f"powers        {self.powers:6d}",
            f"classes       {self.classes:6d}",
            f"features      {self.features:6d}  (class features, new)",
            f"second cards  {self.seconds:6d}  (a card printed inside another entry)",
            f"cross-refs    {self.crossed:6d}  (specs naming another power, now by ref)",
            f"companions    {self.companions:6d}  (familiars and beasts, new)",
            f"build powers  {self.build_powers:6d}  (which build lists which row)",
            f"items         {self.items:6d}  (heroic magic items)",
            f"  blocks      {self.item_blocks:6d}  (a Property or a Power: the work unit)",
            f"  ladder rungs{self.item_steps:6d}  (level, plus and price)",
            f"  sets skipped{self.sets_skipped:6d}  (their members are their own rows)",
            f"feats         {self.feats:6d}",
            f"  power cards {self.feat_cards:6d}  (a feat that prints a whole power)",
            f"  unparsed    {self.unparsed:6d}  (prerequisite clauses left opaque)",
            f"races         {self.races:6d}",
            f"  racial rows {self.racial:6d}  (a power a race grants, never imported)",
            f"prereq terms  {self.terms:6d}  (a printed name a prerequisite asks for)",
            f"other names   {self.aliases:6d}  (rituals, deities: indexed, never content)",
            f"names         {self.names:6d}  (localization/names.json, gitignored)",
            f"common words  {self.common:6d}  (what leaks.py treats as English)",
            "",
            "parse coverage",
        ]
        for k, v in sorted(self.scores.items()):
            lines.append(f"  {k:<12s} {v:6.3f}")
        if self.worst:
            lines += ["", "worst-parsed rows, look here first"]
            lines += [f"  {ref:<12s} {score:.2f}" for ref, score in self.worst]
        return "\n".join(lines)


def connect() -> sqlite3.Connection:
    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} is missing.\n"
            "It is ~140MB of copyrighted content and is not distributed with "
            "this repository. Put your own copy at the project root."
        )
    db = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def build() -> Report:
    source = connect()
    GAME.parent.mkdir(parents=True, exist_ok=True)
    NAMES.parent.mkdir(parents=True, exist_ok=True)
    GAME.unlink(missing_ok=True)

    out = sqlite3.connect(GAME)
    out.executescript(SCHEMA)
    report = Report()
    names: dict[str, dict[str, str]] = {}

    # **First**, because the monster and power passes both consult it to
    # decide whether a one-word name is a name or just a word. It used to
    # run last, and `_COMMON()` read the table the build was in the
    # middle of writing -- so a clean build saw an empty table and a
    # rebuild saw the *previous* run's. The output depended on what was
    # already on disk, which is the one thing a build must not do.
    monster_parser.set_common(_common_words(source, out, report))
    _monsters(source, out, report, names)
    _powers(source, out, report, names)
    report.classes = _classes(source, out)
    report.features = _features(source, out, names)
    report.companions = _companions(source, out, names)
    report.build_powers = _build_powers(source, out, names)
    # Every other name the compendium prints, so the scrubber can see
    # them. These tables are not imported as content and never will be --
    # the engine has no rituals and no deities -- but their *names* turn
    # up constantly in the text of things that are imported, and a name
    # the index has never heard of is a name the scrubber cannot swap and
    # `leaks.py` cannot report. One wondrous-item wave counted more than
    # twenty of them reaching an author verbatim.
    report.aliases = _other_names(source, out, names)
    # Races first: a feat's prerequisite names one and must store a ref.
    # Items before feats for the same reason, one step further out.
    item.races(source, out, report, names)
    item.items(source, out, report, names)
    feat.feats(source, out, report, names)
    # After both, because a feat's Special line names items and
    # a set's benefit names feats. Neither index exists earlier.
    report.crossed += _cross_reference_rest(out, names)

    out.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("source_sha256", _digest(SOURCE)),
    )
    out.commit()
    out.close()

    NAMES.write_text(json.dumps(names, indent=1, sort_keys=True))
    localisation.cache_clear()
    report.names = len(names)
    return report


def _monsters(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Report,
    names: dict[str, dict[str, str]],
) -> None:
    scores: list[float] = []
    rows = list(source.execute(
        "SELECT ID, Txt, Source FROM Monster WHERE Level <= ? ORDER BY ID",
        (MAX_MONSTER_LEVEL,),
    ))
    # One pass to learn every creature's name, then the real one. A stat
    # block that names a *different* creature could not be scrubbed before,
    # because the scrubber only knew the one it was working on -- so 233
    # specs carried somebody else's printed name straight through to an
    # author who is not allowed to see one.
    index = _creature_names(rows)
    for row in rows:
        m = monster_parser.parse(row["ID"], row["Txt"], row["Source"], others=index)
        scores.append(m.score)
        report.monsters += 1
        report.worst.append((m.ref_id, m.score))
        out.execute(
            "INSERT INTO monster VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.ref_id, m.id, m.level, m.role,
                int(m.minion), int(m.leader), int(m.elite), int(m.solo),
                m.size, m.origin, m.kind, json.dumps(m.keywords), m.xp,
                m.hp, m.ac, m.fort, m.ref, m.will,
                m.initiative, m.speed, json.dumps(m.modes), json.dumps(m.scores),
                json.dumps(m.resist), json.dumps(m.vulnerable), json.dumps(m.immune),
                m.senses, m.book, m.rank, m.dialect, m.score,
            ),
        )
        names[m.ref_id] = {"name": m.name, "flavour": m.flavour}
        for a in m.abilities:
            ref = f"{m.ref_id}a{a.index}"
            out.execute(
                "INSERT INTO monster_power VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    ref, m.ref_id, a.index, a.section, a.usage, a.action,
                    a.recharge, json.dumps(a.keywords), a.spec,
                ),
            )
            names[ref] = {"name": a.name}
            report.abilities += 1
    report.scores["monster"] = sum(scores) / max(1, len(scores))
    report.worst = sorted(report.worst, key=lambda p: p[1])[:10]


def _creature_names(rows: list) -> dict[str, str]:
    """Every creature's printed name, mapped to its ref.

    Names made entirely of words the engine already has are left out -- the
    ones built from a damage type and a keyword are the common case. Replacing those would
    corrupt a spec that merely used the words, which is worse than the leak:
    an author would be handed mechanics with rules terms swapped for ids.
    """
    from .monster import _COMMON
    from .sanitise import mechanical

    def worth_swapping(name: str) -> bool:
        words = re.findall(r"[A-Za-z']+", name.lower())
        if not words or len(name) < 5:
            return False
        # A one-word creature name that is ordinary English is a word
        # before it is a name. Swapping it turned "begins to sprout" and
        # "attacks from hiding" into references to whichever creature
        # happens to be called that, in somebody else's rules.
        if len(words) == 1 and words[0] in _COMMON():
            return False
        return not all(w in mechanical() for w in words)

    out: dict[str, str] = {}
    for row in rows:
        m = monster_parser.parse(row["ID"], row["Txt"], row["Source"])
        if worth_swapping((m.name or "").strip()):
            out.setdefault(m.name.strip(), m.ref_id)
        # Ability names too. A stat block saying "recharges after the use of
        # <another creature's power>" leaks that power's name exactly as a
        # creature's name leaked, and its ref is just as usable.
        for a in m.abilities:
            nm = (a.name or "").strip()
            if worth_swapping(nm):
                out.setdefault(nm, f"{m.ref_id}a{a.index}")
    return out


#: The chassis lines every class page prints, in the order they appear.
#: Read out of the compendium rather than transcribed: seventeen classes
#: are too many to copy by hand without a mistake, and a number nobody can
#: trace back to a page is a number nobody can check.
_CHASSIS = {
    "hp_first": r"Hit Points at 1st Level\s*:?\s*(\d+)",
    "hp_per_level": r"Hit Points per Level Gained\s*:?\s*(\d+)",
    "surges": r"Healing Surges(?: per Day)?\s*:?\s*(\d+)",
    "armour": r"Armor Proficiencies\s*:?\s*([^.]+)",
    "weapons": r"Weapon Proficiencies\s*:?\s*([^.]+)",
    "implements": r"Implements?\s*:?\s*([^.]+)",
    "defences": r"Bonus to Defenses?\s*:?\s*([^.]+)",
}


def _classes(source: sqlite3.Connection, out: sqlite3.Connection) -> int:
    """Every non-hybrid class's chassis, off its own page.

    `chargen` needs hit points, surges, defence bonuses and proficiencies
    before a class's powers mean anything, and the eight that exist were
    hand-written. Seventeen more by hand is seventeen chances to mistype a
    number that nothing would catch -- the powers would all work and the
    character would quietly be wrong.
    """
    # Matched on the bare name, because the compendium files a class under
    # its *build*: "Cleric (Templar)", "Fighter (Weaponmaster)", and six
    # separate wizards. Asking for exact names found the twenty classes
    # that have only one build and missed the five that were here first.
    #
    # Hybrids are excluded by name -- they are a way of combining two
    # classes rather than a class, and the goal says so.
    written = 0
    wanted = {c.lower() for c in CLASSES}
    rows = [
        r
        for r in source.execute(
            "SELECT Name, Role, Source, Abilities, PlainTxt, Txt FROM Class"
        )
        if not r["Name"].lower().startswith("hybrid")
        and r["Name"].split("(")[0].strip().lower() in wanted
    ]
    # One row per class: the earliest printing, which is the one the other
    # books amend rather than replace.
    seen: set[str] = set()
    for row in rows:
        bare = row["Name"].split("(")[0].strip()
        if bare in seen:
            continue
        seen.add(bare)
        plain = row["PlainTxt"] or re.sub(r"<[^>]+>", " ", row["Txt"] or "")
        found: dict[str, str] = {}
        for field_, pattern in _CHASSIS.items():
            m = re.search(pattern, plain, re.I)
            if m:
                found[field_] = m.group(1).strip()
        out.execute(
            "INSERT OR REPLACE INTO class VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                bare, row["Role"] or "", row["Source"] or "",
                int(found.get("hp_first", 0) or 0),
                int(found.get("hp_per_level", 0) or 0),
                int(found.get("surges", 0) or 0),
                found.get("defences", ""), found.get("armour", ""),
                found.get("weapons", ""), found.get("implements", ""),
                row["Abilities"] or "",
            ),
        )
        written += 1
    return written



#: A feature heading inside the class-features section: the page sets each
#: in bold capitals. Lower-case bold is a *sub-option* of the feature above
#: it ("Centered Breath" under MONASTIC TRADITION), which is why the case
#: matters and a bare `<b>` would run them together.
_TRAILING_ESSAY = re.compile(
    r"<br\s*/?>\s*<br\s*/?>\s*[A-Z][A-Z0-9 \u2019'&/-]{6,}\s*<br"
)

_FEATURE_HEAD = re.compile(r"<b>\s*([A-Z][A-Z0-9 \u2019'&/-]{3,60}?)\s*</b>")


def _features(source: sqlite3.Connection, out: sqlite3.Connection,
              names: dict[str, dict[str, str]]) -> int:
    """Every class feature's printed rules text, off the class page.

    `_classes` above reads the same pages and keeps only the chassis
    numbers, so the features were dropped on the floor -- and because
    `spec.py` had nothing to answer with, every `cf:` ref in the tree was
    written from a paraphrase in `docs/blocked.json` or guessed. Five
    classes have no `Feature` power row at all, so for those it was
    guesswork all the way down.

    **Every build, not just the earliest printing.** `_classes` keeps one
    row per class on the grounds that later books amend rather than
    replace; that is right for hit points and wrong for features, because
    a build *is* a different set of them.
    """
    written = 0
    wanted = {c.lower() for c in CLASSES}
    for row in source.execute(
        "SELECT Name, Txt FROM Class ORDER BY Name"
    ):
        name = row["Name"] or ""
        bare = name.split("(")[0].strip()
        if name.lower().startswith("hybrid") or bare.lower() not in wanted:
            continue
        build = name.partition("(")[2].rstrip(")").strip()
        html = row["Txt"] or ""
        # The section is its own heading. Anything before it is the
        # chassis and the build summaries; anything after is prose about
        # deities and party role.
        start = re.search(r"<h3[^>]*>[^<]*CLASS FEATURES[^<]*</h3>", html, re.I)
        if start is None:
            continue
        rest = html[start.end():]
        end = re.search(r"<h3[^>]*>", rest)
        section = rest[: end.start()] if end else rest
        heads = list(_FEATURE_HEAD.finditer(section))
        for i, m in enumerate(heads):
            stop = heads[i + 1].start() if i + 1 < len(heads) else len(section)
            body = section[m.end(): stop]
            # A feature that *is* a power is already a `Feature` row in
            # `power`, embedded here as its own card. Keep the prose that
            # introduces it and drop the card, so the two do not disagree.
            body = re.sub(r"<h1\b.*", "", body, flags=re.S)
            # The page ends the feature list with a bare uppercase run --
            # no tag at all, just `<br/><br/>SWORDMAGE OVERVIEW<br/>` --
            # so the last feature of every class swallowed the essay about
            # deities and party role that follows it.
            body = _TRAILING_ESSAY.split(body, 1)[0]
            from .html import text as _text

            spec = " ".join(_text(body).split())
            if len(spec) < 20:
                continue
            ref = f"cf:{bare.lower()}-f{i}" if not build else (
                f"cf:{bare.lower()}-{_slug(build)}-f{i}"
            )
            out.execute(
                "INSERT OR REPLACE INTO class_feature VALUES (?,?,?,?,?)",
                (ref, bare, i, build, spec),
            )
            names[ref] = {"name": m.group(1).title()}
            written += 1
    return written


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

def _powers(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Report,
    names: dict[str, dict[str, str]],
) -> None:
    scores: list[float] = []
    marks = ",".join("?" * len(CLASSES))
    rows = source.execute(
        f"SELECT * FROM Power WHERE Level <= ? AND Class IN ({marks}) ORDER BY ID",
        (MAX_POWER_LEVEL, *CLASSES),
    )
    def keep(p: power_parser.Power) -> None:
        out.execute(
            "INSERT INTO power VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                p.ref, p.id, p.cls, p.level, p.usage, p.action, p.kind,
                p.reach, json.dumps(p.keywords), json.dumps(p.books),
                p.spec, p.score,
            ),
        )
        names[p.ref] = {"name": p.name, "flavour": p.flavour}

    for row in rows:
        p = power_parser.parse(dict(row), row["Txt"])
        scores.append(p.score)
        report.powers += 1
        keep(p)
        # A second card printed inside the same entry. The compendium files
        # both under one id, so a row that must *name* the second -- "you
        # regain the use of that form's attack" -- had nothing to point at,
        # and three rows were recorded unwritable for want of an id that
        # could simply be derived from the parent's.
        for extra in power_parser.parse_extra(dict(row), row["Txt"]):
            report.seconds += 1
            keep(extra)
    report.racial = _racial_powers(source, out, keep)
    report.scores["power"] = sum(scores) / max(1, len(scores))
    report.crossed = _cross_reference(out, names)


def _racial_powers(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    keep: Callable[[power_parser.Power], None],
) -> int:
    """The powers a race grants, which the class filter threw away.

    The compendium files a racial power under the **race** in the same
    `Class` column a class power uses its class for, so `Class IN
    (CLASSES)` dropped every one of them. Nothing noticed for a long
    while, because no character had a race -- but the feat corpus did:
    about 411 of the feats that are riders on a named power name a
    racial one, and four of the ten commonest unresolvable prerequisite
    clauses are racial powers and traits with nothing to point at.

    `cls` is set to the race's **ref**, not its name. Two reasons, and
    both matter: a name in that column would be a printed name in a
    tracked-readable table, and `chargen.loadout` filters on
    `p.cls == cls`, so anything spelled like a class would be dealt to
    every character of it.
    """
    # Read from the source rather than from `race`, which is the only
    # place the name and the id are both held -- the built table keeps
    # ids alone, on purpose.
    races = {
        (r["Name"] or "").strip().lower(): f"r{r['ID']}"
        for r in source.execute("SELECT ID, Name FROM Race")
    }
    if not races:
        return 0
    marks = ",".join("?" * len(races))
    rows = source.execute(
        f"SELECT * FROM Power WHERE Level <= ? AND lower(Class) IN ({marks}) ORDER BY ID",
        (MAX_POWER_LEVEL, *races),
    )
    written = 0
    for row in rows:
        p = power_parser.parse(dict(row), row["Txt"])
        p.cls = races[(row["Class"] or "").strip().lower()]
        keep(p)
        written += 1
    return written



def _companions(source: sqlite3.Connection, out: sqlite3.Connection,
                names: dict[str, dict[str, str]]) -> int:
    """Every familiar and beast companion's printed block.

    Not read until now, so `c.familiar()` was written against nothing and
    the ranger's beast had no statistics to take. The eleven of type
    `Companion` are the beasts and carry a whole stat block; the
    ninety-four familiars carry Constant and Active Benefits.
    """
    written = 0
    for cid, name, kind, plain in source.execute(
        "SELECT ID, Name, Type, PlainTxt FROM Companion ORDER BY ID"
    ):
        spec = " ".join((plain or "").split())
        # ...and closes with the publication line.
        # The page opens `<name> <type> <name>`, so the type word sits
        # between the two copies and stops a plain repeat-strip.
        for _ in range(3):
            for lead in (name, (kind or "").strip()):
                if lead and spec.startswith(lead):
                    spec = spec[len(lead):].lstrip()
        spec = re.split(r"\s*Published in\b", spec)[0].strip()
        if len(spec) < 20:
            continue
        ref = f"comp:{cid}"
        out.execute(
            "INSERT OR REPLACE INTO companion VALUES (?,?,?)",
            (ref, (kind or "").strip().lower(), sanitise.scrub(spec, {name: ref})),
        )
        names[ref] = {"name": name}
        written += 1
    return written


def _build_powers(source: sqlite3.Connection, out: sqlite3.Connection,
                  names: dict[str, dict[str, str]]) -> int:
    """The powers each build's page lists, resolved to refs by name.

    A build page names its powers and gives no ids, so they are matched
    against the names already collected for this class. Same class only:
    two classes share a power name often enough that a global match would
    put a wizard row on a warlock build.
    """
    by_name: dict[tuple[str, str], str] = {}
    for ref, cls in out.execute("SELECT ref, class FROM power"):
        name = (names.get(ref) or {}).get("name", "")
        if name:
            by_name.setdefault((cls.lower(), name.lower()), ref)

    written = 0
    wanted = {c.lower() for c in CLASSES}
    for name, txt in source.execute("SELECT Name, Txt FROM Class"):
        bare = name.split("(")[0].strip()
        build = name.partition("(")[2].rstrip(")").strip()
        if name.lower().startswith("hybrid") or bare.lower() not in wanted or not build:
            continue
        seen: set[str] = set()
        for card in re.findall(
            r'<span class="level">[^<]*</span>([^<]*)</h1>', txt
        ):
            ref = by_name.get((bare.lower(), unescape(card).strip().lower()))
            if ref and ref not in seen:
                seen.add(ref)
                out.execute(
                    "INSERT OR IGNORE INTO build_power VALUES (?,?,?)",
                    (bare, build, ref),
                )
                written += 1
    return written

def _cross_reference(out: sqlite3.Connection, names: dict[str, dict[str, str]]) -> int:
    """Swap one power's name for its ref wherever another power prints it.

    Monsters have had this since they were imported (`etl/monster.py`);
    powers never did, so a row whose whole Effect is "you regain the use
    of <another power>" printed that name to anyone reading the spec --
    and, worse, gave the person writing it **no ref to name**. Two rows
    were recorded as unwritable on exactly that.

    Same class and two words minimum. A cross-class reference is
    vanishingly rare and a one-word power name is very often an ordinary
    verb; both would trade a real leak for a lot of false ones.
    """
    from .sanitise import scrub

    by_class: dict[str, dict[str, str]] = {}
    for ref, cls in out.execute("SELECT ref, class FROM power"):
        name = (names.get(ref) or {}).get("name", "")
        if len(name.split()) > 1:
            by_class.setdefault(cls, {})[name] = ref

    changed = 0
    for ref, cls, spec in out.execute("SELECT ref, class, spec FROM power").fetchall():
        others = {n: r for n, r in by_class.get(cls, {}).items() if r != ref}
        if not others:
            continue
        fixed = scrub(spec, others)
        if fixed != spec:
            out.execute("UPDATE power SET spec=? WHERE ref=?", (fixed, ref))
            changed += 1
    return changed


#: Compendium tables whose rows are never content but whose names are
#: printed inside things that are. The prefix is what their ref is built
#: from -- `x12` for a ritual, `x4` for a deity -- and it is deliberately
#: one letter for all of them: an author is told only that a name was
#: here, never what kind of thing it named.
_ALIAS_TABLES = (
    "Ritual", "Deity", "Terrain", "Trap", "Poison", "Disease",
    "Background", "Theme", "ParagonPath", "EpicDestiny", "Associate",
)

#: **`Glossary` is the opposite of these and belongs with the rules
#: vocabulary.** Its 518 entries are the game's own index of mechanical
#: terms -- "Action Points", "Aid Another", "Coup de Grace", "Once Per
#: Turn" -- which is precisely what a system is and precisely what this
#: project is entitled to say out loud. Indexed as names it reported
#: fourteen perfectly good comments as leaks, including one in the
#: README, and would have had the scrubber replacing "once per turn"
#: with an id in the middle of a rules sentence.
_VOCABULARY_TABLE = "Glossary"


def _other_names(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    names: dict[str, dict[str, str]],
) -> int:
    """Index every printed name the project does not import as content.

    `leaks.py` and `scrub` both work off `localization/names.json`, so a
    name that is in the compendium and not in that file is invisible to
    both -- it cannot be swapped out of a spec and cannot be reported if
    it reaches the tree. Rituals, deities, paragon paths and the rest are
    exactly that: nothing here will ever be a row, and all of them are
    named inside rows that are.

    They go in with a ref and no table of their own, because nothing will
    ever look one up -- the ref exists so that a spec can say "a name was
    here" without saying which.
    """
    seen = 0
    for n, table in enumerate(_ALIAS_TABLES):
        for row in source.execute(f"SELECT ID, Name FROM {table}"):
            name = (row["Name"] or "").strip()
            if len(name) < 3:
                continue
            ref = f"x{n}_{row['ID']}"
            names.setdefault(ref, {"name": name})
            seen += 1
    return seen


def _cross_reference_rest(
    out: sqlite3.Connection, names: dict[str, dict[str, str]]
) -> int:
    """The same swap for items and feats, which name each other constantly.

    `_cross_reference` above is scoped to one class, because a power
    naming a power from another class is vanishingly rare. Items and
    feats are the opposite: a feat's Special line is *usually* about
    another feat, an item set names its members, and an Associated
    Powers list is nothing but other people's names. Scoped narrowly,
    almost nothing would be caught.

    So the scope is everything, and the safety comes from the other side:
    a name is only swapped if it **identifies** -- two words or more, and
    at least one of them a word the corpus does not treat as ordinary
    English. That is the same test `scripts/leaks.py` applies, which is
    what keeps the two halves of this arrangement from drifting apart.

    Indexed by first word rather than tried one at a time. There are
    twenty-six thousand names and six thousand specs, and the honest
    version of this loop is a hundred and fifty million substitutions.

    **The test is `sanitise.identifies`, which is the one `leaks.py`
    reports with.** It used to be a stricter home-made version -- two
    words and one of them uncommon -- and being stricter is exactly the
    wrong direction: it skipped the names the checker then found, so 124
    specs shipped a neighbour's printed name while both halves believed
    they agreed.
    """
    from .sanitise import identifies, scrub, vocabulary

    rules = vocabulary()
    by_word: dict[str, list[tuple[str, str]]] = {}
    # Every name, whether or not it "identifies" -- `_label_refs` needs
    # the ones the general test waives.
    #
    # **A power wins a tie.** Several class powers share a name with a
    # monster ability, and the monsters are imported first, so taking
    # whichever ref arrived first pointed five of a feat's Associated
    # Powers clauses at a stat block. A feat modifies the powers a
    # character has; it has never modified a monster's claw.
    by_name: dict[str, str] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip()
        low = name.lower()
        if len(low) < 3:
            continue
        if low not in by_name or (ref[:1] == "p" and by_name[low][:1] != "p"):
            by_name[low] = ref
        if not identifies(low, [ref], rules):
            continue
        words = re.findall(r"[A-Za-z']+", low)
        if words:
            by_word.setdefault(words[0], []).append((name, ref))

    changed = 0
    for table in ("power", "monster_power", "class_feature",
                  "companion", "item", "item_block", "feat", "race"):
        rows = out.execute(f"SELECT ref, spec FROM {table}").fetchall()
        for ref, spec in rows:
            if not spec:
                continue
            here = set(re.findall(r"[a-z']+", spec.lower()))
            # **A monster's ability never belongs in a character's
            # spec.** `by_word` holds every name, and several monster
            # abilities share a name with a class power that this build
            # does not import -- so "you don't expend the use of <name>"
            # on a feat was resolving onto a stat block. A feat modifies
            # what a character has; it has never modified a claw. The
            # same guard `_named_powers`, `_label_refs` and
            # `_associated_refs` each carry, here for the general swap.
            monsters_ok = table in ("monster_power",)
            others = {
                name: other
                for word in here & by_word.keys()
                for name, other in by_word[word]
                if other != ref and not other.startswith(ref)
                and (monsters_ok or other[:1] != "m")
            }
            if not others:
                continue
            fixed = scrub(spec, others)
            if table == "feat":
                fixed = _label_refs(fixed, by_name)
                fixed = _associated_refs(fixed, by_name)
            fixed = _named_powers(fixed, by_name, ref)
            if fixed != spec:
                out.execute(f"UPDATE {table} SET spec=? WHERE ref=?", (fixed, ref))
                changed += 1
    return changed


#: `Sly Flourish : If you score a critical hit ...` -- a feat's Associated
#: Powers list, one clause per power, keyed by the power's printed name.
_LABEL = re.compile(r"^([A-Z][\w' ]{2,40}?)\s*:\s", re.M)


#: "the wizard's **scorching burst** power", "you regain the use of your
#: **fell might**". A phrase immediately before the word `power` is a
#: power's name, whatever `identifies` thinks of the phrase on its own.
#:
#: **The qualifier is part of the match, not part of the name.** A card
#: writes "your *fade away* **racial** power" and "your *Combat
#: Challenge* **class feature**, and the old pattern captured "your fade
#: away racial" and then looked up its tails -- "racial", "away racial",
#: "fade away racial" -- never "fade away". So 111 racial powers and 81
#: class features that `by_name` could resolve were reaching authors as
#: prose, and 134 rows across the corpus carry a marker for want of a
#: name the database had all along. Measured before the verbs they
#: wanted were built, which is what `plans/` said to do.
_NAMED = re.compile(
    r"\b([A-Za-z][\w']*(?:\s+[A-Za-z][\w']*){0,3}?)"
    r"(\s+(?:racial|encounter|daily|at-will|utility|attack))*"
    r"\s+(power|class feature)\b"
)


def _named_powers(spec: str, by_name: dict[str, str], own: str) -> str:
    """Swap `<name> power` for `<ref> power`.

    The other half of the same hole `_label_refs` closes. `identifies`
    waives a two-word phrase built of two ordinary words -- "magic
    missile", "fell might" -- because in running prose such a phrase is
    usually a coincidence. Immediately before the word *power* it is not
    a coincidence, and 33 of one item wave's 174 blocks were refused for
    no reason but this: the row was writable, the engine had every verb
    it needed, and there was nothing to name.

    Longest match first, so a three-word name is not left as a fragment
    of a two-word one.
    """

    def swap(m: re.Match) -> str:
        phrase, quals, noun = m.group(1), m.group(2) or "", m.group(3)
        words = phrase.split()
        for size in range(len(words), 0, -1):
            tail = " ".join(words[-size:])
            ref = by_name.get(tail.lower())
            # **Only a `p` or a `cf:`.** `by_name` prefers a power on a
            # tie, but a name with no character-side counterpart resolves
            # onto a monster's stat block -- 112 specs were pointing a
            # feat at a claw. A feat modifies what a character has; it
            # has never modified a monster's ability.
            if ref and ref[:1] not in ("p", "c"):
                continue
            if ref and not ref.startswith(own):
                head = " ".join(words[:-size])
                return f"{head} {ref}{quals} {noun}".strip()
        return m.group(0)

    return _NAMED.sub(swap, spec)


def _label_refs(spec: str, by_name: dict[str, str]) -> str:
    """Swap the label of an Associated-Powers clause for its ref.

    Done outside `identifies` on purpose, and this is the one place that
    is right. That test waives a two-word phrase built of two ordinary
    words -- "sly flourish", "careful attack" -- because in running prose
    such a phrase is usually a coincidence, and the docstring says out
    loud that the cost is missing a real name of that shape.

    **In this position it is never a coincidence.** A capitalised phrase
    at the start of a line, followed by a colon, inside a list a feat
    prints of the powers it modifies, is a power's name by construction.
    158 feats print such a list and 79 of their clause labels were
    reaching authors as prose -- the single largest hole left, and
    invisible to `leaks.py --specs` for exactly the reason above.
    """

    def swap(m: re.Match) -> str:
        ref = by_name.get(m.group(1).lower())
        # **Only a `p` or a `cf:`.** `by_name` prefers a power on a tie,
        # but a name with no character-side counterpart resolves onto a
        # monster's stat block -- and a feat modifies the powers a
        # character has, never a monster's claw. The same guard
        # `_named_powers` and `_associated_refs` carry.
        if ref and ref[:1] not in ("p", "c"):
            return m.group(0)
        return f"{ref} : " if ref else m.group(0)

    return _LABEL.sub(swap, spec)


#: The whole `Associated Powers:` line, to the end of the spec or the next
#: blank line. Comma-separated, and a member may carry its own clause
#: after a colon -- `Sly Flourish : only when used as a melee attack`.
_ASSOCIATED = re.compile(r"^Associated Powers\s*:\s*(.+)$", re.M | re.S)

#: A ref as `_named_powers` and `_label_refs` leave it.
_IS_REF = re.compile(r"^[pmifr]\d+[a-z]*\d*$")


def _associated_refs(spec: str, by_name: dict[str, str]) -> str:
    """Turn a feat's Associated-Powers list into refs.

    **This is the single largest gap in the feat corpus and it was never
    an engine gap.** Sixty-odd weapon-style feats across the fighter, the
    ranger, the rogue and the warlord print a benefit gated on "a power
    associated with this feat", and the list naming those powers reached
    authors as printed names -- which this project may not read. So the
    set was unknowable and every one of those clauses was marked
    `feat.associated_powers`.

    The same argument as `_label_refs`, one step further along. A
    comma-separated list under the heading *Associated Powers* is a list
    of power names by construction, so `identifies` is rightly waived:
    "Sure Strike" and "Crushing Blow" are two ordinary words each and
    would never pass it in running prose.

    **A name that does not resolve is not a failure and is not dropped
    silently.** 213 of the 497 members are paragon or epic rows -- level
    13 to 27 -- and this build imports heroic only, so they are powers no
    character here can hold. The resolved subset therefore *is* the whole
    associated set as far as the engine is concerned, and that is the
    thing an author needs to be told. The count of the rest is printed
    beside it so the author can see the list was trimmed rather than
    guess.
    """

    def swap(m: re.Match) -> str:
        refs: list[str] = []
        above = 0
        for part in m.group(1).split(","):
            head = part.strip().split(":")[0].strip()
            if not head:
                continue
            if _IS_REF.match(head):
                refs.append(head)
                continue
            ref = by_name.get(head.lower())
            # **Only a `p`.** `by_name` prefers a power on a tie, but a
            # paragon power that shares its name with a monster ability
            # has no heroic `p` to prefer -- so the tie-break silently
            # handed two of these lists an `m` ref. A feat modifies the
            # powers a character has; it has never modified a claw. Those
            # count as out of scope, which is what they are.
            if ref and ref[:1] == "p":
                refs.append(ref)
            else:
                above += 1
        if not refs and not above:
            return m.group(0)
        seen: list[str] = []
        for r in refs:
            if r not in seen:
                seen.append(r)
        tail = f"  (+{above} above heroic)" if above else ""
        return f"Associated Powers: {', '.join(seen)}{tail}"

    return _ASSOCIATED.sub(swap, spec)


#: A word used on the pages of at least this many rows is ordinary English.
#: `retreat` and `skeleton` turn up all over; a proper name turns up in its
#: own entry and its few variants.
COMMON_IN = 8


def _vocabulary(texts) -> set[str]:  # noqa: ANN001
    """The distinct words one row uses. A set, so this counts rows not uses."""
    import re

    out: set[str] = set()
    for chunk in texts:
        out.update(re.findall(r"[a-z]{2,}", (chunk or "").lower()))
    return out


def _common_words(
    source: sqlite3.Connection, out: sqlite3.Connection, report: Report
) -> frozenset[str]:
    """Record which words are ordinary English, measured by how widely used.

    `scripts/leaks.py` needs to tell a proper name from a word that merely
    happens to be one -- somebody published abilities called `Retreat` and
    `Stable`, and a power called `Not It`. Counting how many different rows
    use a word answers that from the data, so no hand-kept list of exceptions
    has to be fed forever.

    The corpus is every monster, power, item and feat page in full, names
    and prose included, and not the sanitised specs -- a stat block's
    mechanics almost never say "skeleton", while the pages plainly do.

    **Items and feats are in the corpus for the same reason monsters are.**
    Their vocabulary -- scabbard, bracers, baldric, reliquary, gauntlets --
    appears nowhere in the monster and power pages, so without them not one
    of those words is "ordinary English" and `leaks.py` reports every
    occurrence anywhere in the tree as a printed name.
    """
    seen: Counter[str] = Counter()
    # The glossary first, as whole phrases: it *is* the rules vocabulary,
    # and every entry counts as ordinary however rare its words are.
    for row in source.execute(f"SELECT Name FROM {_VOCABULARY_TABLE}"):
        term = (row[0] or "").strip().lower()
        if len(term) > 2:
            seen[term] = COMMON_IN
            seen.update({w: COMMON_IN for w in term.split()})
    for table in ("Monster", "Power", "Item", "Feat"):
        for row in source.execute(f"SELECT PlainTxt FROM {table}"):
            seen.update(_vocabulary([row[0]]))
    rows = [(w, n) for w, n in seen.items() if n >= COMMON_IN]
    out.executemany("INSERT INTO common_word VALUES (?, ?)", rows)
    report.common = len(rows)
    return frozenset(w for w, _ in rows)


def _digest(path: Path) -> str:
    """A hash of the source, so a different community build is detectable."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=1)
def _open_game() -> sqlite3.Connection:
    if not GAME.exists():
        raise SystemExit(f"{GAME} is missing. Run: uv run scripts/build.py")
    db = sqlite3.connect(f"file:{GAME}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def game() -> sqlite3.Connection:
    """The built database. The engine reads this, never the compendium.

    One connection per process. It used to open a fresh one on every call,
    and `loader.spawn` calls it several times per creature -- so building an
    audit board opened six connections, and an audit builds a hundred
    thousand boards. Read-only, so sharing it is safe; `check_same_thread`
    is off because the API serves its blocking handlers from a threadpool.
    """
    return _open_game()


@lru_cache(maxsize=1)
def localisation() -> dict[str, dict[str, str]]:
    """Printed names, if this machine has them. The engine never calls this.

    Cached: it is seventeen thousand entries, it is read once per name looked
    up, and re-parsing it each time was a quarter of the time taken to draw
    the board. Call `localisation.cache_clear()` after a rebuild.
    """
    if not NAMES.exists():
        return {}
    return json.loads(NAMES.read_text())


if __name__ == "__main__":
    print(build().render())
