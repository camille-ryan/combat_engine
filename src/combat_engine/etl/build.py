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

from . import feat, item, sanitise, wields
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
  dialect TEXT, score REAL, conjuration INTEGER
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
  books TEXT, spec TEXT, score REAL,
  -- Which weapons this power's own text is about, as JSON: the groups and
  -- shapes its Requirement **gates** on, and the ones a rider merely **rewards**.
  -- Two axes because they are two relationships, and NULL for the great majority
  -- of rows that mention no weapon at all. `etl/wields.py` fills it; three
  -- consumers were asking this by substring match before it existed. #237.
  wields TEXT
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
  ref TEXT PRIMARY KEY, class TEXT, ord INTEGER, build TEXT, spec TEXT,
  -- The `power` row this card **reprints**, where it reprints one.
  --
  -- A class-feature section prints the full card of the power the feature
  -- grants, and `_card_row` reads it with the same `sanitise.power_spec` the
  -- `power` table uses -- so the output is byte-identical and 74 of the 94
  -- cards are a second ref for a row that already had one.
  -- `cf:ardent-f1` says "You gain the p10273 power" and `cf:ardent-f1c0`
  -- **is** p10273.
  --
  -- Recorded rather than skipped, and the refs are never renumbered: 25
  -- `cf:...c<N>` refs are cited across the tree and docs, and
  -- `_sub_features` already records that renumbering once "moved
  -- `cf:rogue-scoundrel-f4` under somebody else's feet". The 20 cards with
  -- no match are the genuine feature powers -- Hunter's Quarry, Wild Shape,
  -- Lay On Hands, Oath of Enmity, Warlock's Curse -- and they keep theirs.
  --
  -- NULL means "this card is its own row". Authors should write the `p` ref
  -- where one is named here.
  duplicate_of TEXT
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

-- The base weapons. Every `Weapon` constant in `chargen` was transcribed
-- by hand off a page, and a hand-typed damage die or proficiency bonus is
-- a number nothing can check -- every power would still work and the
-- character would quietly be wrong. Seventeen printed weapon groups are
-- in here, of which `chargen` used to deal ten, so "you gain proficiency
-- with all flails" was false because the engine had no flail rather than
-- because it had no rule.
--
-- `ref` is `w:<slug>`, which is what `Weapon.ref` already carried and what
-- a printed base-item restriction is matched against.
CREATE TABLE weapon (
  ref TEXT PRIMARY KEY, id INTEGER, category TEXT, hands TEXT,
  melee INTEGER, damage TEXT, proficiency INTEGER, grp TEXT,
  reach INTEGER, range_short INTEGER, range_long INTEGER, properties TEXT
);
CREATE INDEX weapon_group ON weapon(grp, category);

-- Traps and hazards. **631 of these were never read**, and `terrain.arm`
-- said so in a docstring that read as a design choice: "the numbers come
-- off the monster curve because there is no row to read them from: the ETL
-- keeps traps as names only, so a trap has a level and nothing else." There
-- is a row, and it carries the attack line, the damage, the trigger and the
-- target.
--
-- `perception_dc` is the number that matters most and the one that cannot
-- be derived. 356 of the rows print `Perception DC N`; across them the DC
-- is **not** a function of level -- level-1 traps print anything from 9 to
-- 22, and the per-level median wanders from level+3.5 to level+18. So a
-- formula would be wrong by ten either way on the number that decides
-- whether a player is shown a hazard at all.
--
-- **NULL means "cannot be noticed in advance"**, which is the honest
-- reading of a block that prints no DC. Not 0, which would mean everybody
-- notices it.
CREATE TABLE trap (
  ref TEXT PRIMARY KEY, id INTEGER, level INTEGER, role TEXT, kind TEXT,
  perception_dc INTEGER, attack INTEGER, defence TEXT, damage TEXT, spec TEXT
);
CREATE INDEX trap_level ON trap(level);
"""


@dataclass
class Report:
    monsters: int = 0
    abilities: int = 0
    powers: int = 0
    classes: int = 0
    weapons: int = 0
    features: int = 0
    seconds: int = 0
    crossed: int = 0
    companions: int = 0
    traps: int = 0
    links_found: int = 0
    links_total: int = 0
    #: Rows whose text says something about a weapon, gate or rider. #237.
    wields: int = 0
    build_powers: int = 0
    items: int = 0
    item_blocks: int = 0
    item_steps: int = 0
    sets_skipped: int = 0
    feats: int = 0
    feat_cards: int = 0
    races: int = 0
    racial: int = 0
    themed: int = 0
    talents: int = 0
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
            f"weapons       {self.weapons:6d}  (base weapons, numbers off the page)",
            f"features      {self.features:6d}  (class features, new)",
            f"second cards  {self.seconds:6d}  (a card printed inside another entry)",
            f"cross-refs    {self.crossed:6d}  (specs naming another power, now by ref)",
            f"companions    {self.companions:6d}  (familiars and beasts, new)",
            f"traps         {self.traps:6d}  (with a printed Perception DC where one is given)",
            f"weapon rows   {self.wields:6d}  (what each power's text says it needs)",
            f"assoc links   {self.links_found:6d}/{self.links_total}"
            "  (linked Associated members resolved; see _links_resolve)"
            + ("   <-- A MISS. The name resolver has regressed."
               if self.links_found != self.links_total else ""),
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
            f"theme rows    {self.themed:6d}  (a power a theme grants, never imported)",
            f"  wild talents{self.talents:6d}  (the cantrips no owner is printed for)",
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
    report.weapons = _weapons(source, out)
    report.features = _features(source, out, names)
    report.companions = _companions(source, out, names)
    report.traps = _traps(source, out, names)
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
    report.links_found, report.links_total = _links_resolve(source, out)
    # **Last, and it has to be.** The vocabulary is the `weapon` table and the
    # text is `power.spec`, so this runs once both are finished; earlier it would
    # read an empty vocabulary and quietly write nothing.
    report.wields = wields.record(out)

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


#: Stat lines the local compendium has wrong, and what the published block
#: actually prints. **Per ref and never a formula**, for a reason that was
#: measured: `m3561`'s corruption is every number with the monster-maths
#: constant added on top -- AC 18 + 14 = 32, Fortitude 15 + 12 = 27, the
#: attack +8 + 5 = +13 -- and nine monsters in the corpus carry an AC twenty
#: or more above their level, so a rule suggested itself. Undoing that rule on
#: the other eight produces nonsense: `m1107` would come out with Will 0.
#: Whatever is wrong with those is a different fault and is not this one.
#:
#: So an entry goes here only when the published block has been read and
#: compared. `m3640` is **not** here for exactly that reason -- its numbers are
#: wrong and nobody has checked what they should be, so it is refused in
#: `loader.UNUSABLE` instead of guessed at.
CORRECTED: dict[str, dict[str, int]] = {
    # Level 4 minion. Local rows: AC 32, Fort 27, Ref 29, Will 26, attacks +13.
    "m3561": {"ac": 18, "fort": 15, "ref": 17, "will": 14, "attack": 8},
}


def _int_or_none(value: object) -> int | None:
    """The compendium's own column, when it is a number."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _correct(m: object, ref: str) -> None:
    """Put a checked stat line back, in place, before the row is written."""
    fix = CORRECTED.get(ref)
    if not fix:
        return
    for name in ("ac", "fort", "ref", "will"):
        if name in fix:
            setattr(m, name, fix[name])
    # The attack bonus lives in the ability's own spec text, which is what an
    # author is shown and transcribes into `Attack(printed=)`. Left alone, the
    # corrected creature would still hit like a paragon one.
    now = fix.get("attack")
    if now is None:
        return
    for ability in getattr(m, "abilities", ()):
        if ability.spec:
            ability.spec = re.sub(
                r"\+\d+(?= vs )", f"+{now}", ability.spec
            )


def _monsters(
    source: sqlite3.Connection,
    out: sqlite3.Connection,
    report: Report,
    names: dict[str, dict[str, str]],
) -> None:
    scores: list[float] = []
    rows = list(source.execute(
        "SELECT ID, Txt, Source, Level, Role FROM Monster "
        "WHERE Level <= ? ORDER BY ID",
        (MAX_MONSTER_LEVEL,),
    ))
    # One pass to learn every creature's name, then the real one. A stat
    # block that names a *different* creature could not be scrubbed before,
    # because the scrubber only knew the one it was working on -- so 233
    # specs carried somebody else's printed name straight through to an
    # author who is not allowed to see one.
    index = _creature_names(rows)
    for row in rows:
        m = monster_parser.parse(
            row["ID"], row["Txt"], row["Source"], others=index,
            printed_level=_int_or_none(row["Level"]),
            printed_role=row["Role"] or "",
        )
        _correct(m, m.ref_id)
        scores.append(m.score)
        report.monsters += 1
        report.worst.append((m.ref_id, m.score))
        out.execute(
            "INSERT INTO monster VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.ref_id, m.id, m.level, m.role,
                int(m.minion), int(m.leader), int(m.elite), int(m.solo),
                m.size, m.origin, m.kind, json.dumps(m.keywords), m.xp,
                m.hp, m.ac, m.fort, m.ref, m.will,
                m.initiative, m.speed, json.dumps(m.modes), json.dumps(m.scores),
                json.dumps(m.resist), json.dumps(m.vulnerable), json.dumps(m.immune),
                m.senses, m.book, m.rank, m.dialect, m.score,
                int(m.conjuration),
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


#: "Military two-handed melee weapon", and the shapes the double weapons
#: and the garrote print instead -- "Superior double melee weapon",
#: "Superior two-handed weapon". The middle word is how many hands, which
#: is not always one of the two obvious answers.
_ARM = re.compile(
    r"^(Simple|Military|Superior|Improvised)\s+([\w-]+)"
    r"(?:\s+(melee|ranged))?\s+weapon\s*$",
    re.I | re.M,
)
_DAMAGE = re.compile(r"^Damage\s*:\s*(\d+d\d+)", re.M)
_PROFICIENT = re.compile(r"^Proficient\s*:\s*\+?(\d+)", re.M)
_RANGE = re.compile(r"^Range\s*:\s*(\d+)\s*/\s*(\d+)", re.M)
_SECTION = re.compile(
    r"^(Properties|Group)\s*:\s*\n(.*?)(?=\n(?:Properties|Group)\s*:|\nPublished|\Z)",
    re.S | re.M,
)
#: An entry inside one of those two sections: the term, then its glossary
#: paragraph in brackets. The paragraph is the publisher's prose and is
#: thrown away -- only the term is a mechanical fact.
_TERM = re.compile(r"([A-Z][A-Za-z\u2019' -]*?)\s*\(", re.M)


def _slug(name: str) -> str:
    """"Short sword" -> "short-sword", which is the ref `chargen` already used."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _weapons(source: sqlite3.Connection, out: sqlite3.Connection) -> int:
    """The base weapons, off the equipment pages.

    A base weapon is four numbers and two lists -- damage die, proficiency
    bonus, reach, range, properties, group -- and `chargen` had sixteen of
    them typed in by hand. That was tolerable while the ten groups it dealt
    were the only ones any row asked about, and stopped being so the moment
    a feat said "you gain proficiency with all flails": the clause was
    false because nothing in the engine was a flail, which reads exactly
    like a rule that does not work.

    Identified by the Proficient line, which every weapon prints and no
    other piece of equipment does. Implements are deliberately not here:
    an orb has no damage die and no proficiency bonus, so there is no stat
    line to load and `chargen` declares them itself.
    """
    written = 0
    for row in source.execute(
        "SELECT ID, Name, PlainTxt FROM Item "
        "WHERE Category IN ('Weapon', 'Equipment') ORDER BY ID"
    ):
        text = row["PlainTxt"] or ""
        arm = _ARM.search(text)
        damage = _DAMAGE.search(text)
        proficient = _PROFICIENT.search(text)
        if not (arm and damage and proficient):
            continue
        sections = {kind.lower(): body for kind, body in _SECTION.findall(text)}
        groups = [g.strip().lower() for g in _TERM.findall(sections.get("group", ""))]
        properties = [
            p.strip().lower() for p in _TERM.findall(sections.get("properties", ""))
        ]
        ranged = _RANGE.search(text)
        out.execute(
            "INSERT OR REPLACE INTO weapon VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"w:{_slug(row['Name'])}",
                row["ID"],
                arm.group(1).lower(),
                arm.group(2).lower(),
                int((arm.group(3) or "melee").lower() == "melee"),
                damage.group(1),
                int(proficient.group(1)),
                groups[0] if groups else "",
                2 if "reach" in properties else 1,
                int(ranged.group(1)) if ranged else None,
                int(ranged.group(2)) if ranged else None,
                json.dumps(properties + groups[1:]),
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

#: A **sub-option** of the feature above it, set in title case: the
#: fighter's talents, the rogue's tactics, the wizard's implement
#: masteries, one bold line each under the capitalised heading.
#:
#: Dropping them was the largest hole in the feat corpus. A feat that
#: riders on a build choice names the *sub-option* -- no feat is gated on
#: the heading, which is only "choose one of the following" -- so 97 of
#: the names the tree's `c.class_feature()` rows cite had no row to point
#: at, while the heading above each one did.
#:
#: **What tells a heading from the bold run inside a power card is the
#: page's own punctuation, not the case.** A heading has a `<br/>` on
#: both sides of it; `<b>Martial</b>, <b>Weapon</b><br/>` inside a card
#: has a comma on the left and `<b>At-Will</b>&nbsp;` a space on the
#: right. Matching bare title-case `<b>` instead found 848 of these, most
#: of them the word "Encounter".
_SUB_HEAD = re.compile(
    r"<br\s*/?>\s*<b>\s*([A-Z][A-Za-z0-9\u2019'&/ .:-]{2,60}?)\s*</b>\s*<br\s*/?>"
)

#: A whole power card printed inside a feature section -- the same shape
#: `feat._CARD` reads, and for the same reason. The warlock's curse and
#: the ranger's quarry are printed nowhere else, so deleting the card
#: left the two most-cited class features in the corpus with no ref.
_FEATURE_CARD = re.compile(r'<h1[^>]*class="[a-z-]*power"', re.I)
_H1 = re.compile(r"<h1\b")
_CARD_NAME = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_CARD_LEVEL = re.compile(r'<span class="level">(.*?)</span>', re.S)


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
        stem = f"cf:{bare.lower()}" if not build else (
            f"cf:{bare.lower()}-{_slug(build)}"
        )
        heads = list(_FEATURE_HEAD.finditer(section))
        for i, m in enumerate(heads):
            stop = heads[i + 1].start() if i + 1 < len(heads) else len(section)
            body = section[m.end(): stop]
            # The page ends the feature list with a bare uppercase run --
            # no tag at all, just `<br/><br/>SWORDMAGE OVERVIEW<br/>` --
            # so the last feature of every class swallowed the essay about
            # deities and party role that follows it.
            body = _TRAILING_ESSAY.split(body, 1)[0]
            # A feature that *is* a power is already a `Feature` row in
            # `power`, embedded here as its own card. Keep the prose that
            # introduces it and drop the card from the *parent's* spec, so
            # the two do not disagree -- and file the card as a row of its
            # own below rather than deleting it, which is what left
            # "Warlock's Curse" unnameable.
            #
            # The same cut serves the sub-options: everything from the
            # first of them belongs to *it* and not to the heading above.
            # Leaving it on both put a sub-option's printed name in the
            # parent's spec as prose, where the `own` guard in
            # `_named_powers` rightly refuses to swap a child's ref into
            # its parent -- and a name the scrubber will not touch is a
            # leak.
            marks = _sub_marks(body)
            head = body[: marks[0][0]] if marks else body
            ref = f"{stem}-f{i}"
            written += _feature_row(out, names, ref, bare, i, build,
                                    head, m.group(1).title())
            written += _sub_features(out, names, ref, bare, i, build,
                                     body, marks)
    return written


def _feature_row(
    out: sqlite3.Connection, names: dict[str, dict[str, str]],
    ref: str, cls: str, ord_: int, build: str, body: str, name: str,
) -> int:
    from .html import text as _text

    spec = " ".join(_text(body).split())
    if len(spec) < 20:
        return 0
    # `duplicate_of` is NULL here on purpose: this is the prose branch --
    # a feature or sub-option read with the flattener -- and only a *card*,
    # read in the power dialect by `_card_row`, can be byte-identical to a
    # `power` row.
    out.execute(
        "INSERT OR REPLACE INTO class_feature VALUES (?,?,?,?,?,NULL)",
        (ref, cls, ord_, build, spec),
    )
    names[ref] = {"name": name}
    return 1


def _sub_marks(body: str) -> list[tuple[int, int, str, str]]:
    """Where a feature section stops being about the heading above it."""
    marks: list[tuple[int, int, str, str]] = []
    for m in _SUB_HEAD.finditer(body):
        marks.append((m.start(), m.end(), "s", m.group(1)))
    for m in _H1.finditer(body):
        if _FEATURE_CARD.match(body, m.start()):
            marks.append((m.start(), m.start(), "c", ""))
    marks.sort()
    return marks


def _sub_features(
    out: sqlite3.Connection, names: dict[str, dict[str, str]],
    parent: str, cls: str, ord_: int, build: str, body: str,
    marks: list[tuple[int, int, str, str]],
) -> int:
    """The named things printed *inside* one feature's section.

    Two shapes, both of which the caps-only import dropped on the floor,
    and between them they hold every name the tree's `c.class_feature()`
    rows were citing in prose:

    * a title-case sub-option, one of the build choices listed under the
      capitalised heading, which is the thing a feat is actually gated on;
    * a power card, which for the warlock's curse and the ranger's quarry
      is the only place the name is printed at all.

    Suffixed off the parent (`...-f3s0`, `...-f3c0`) exactly as
    `feat._card` suffixes a card off its feat, so the caps headings keep
    the ordinals every `cf:` ref already written into the tree depends on.
    Numbering the sub-options into the same sequence would have been
    tidier and would have moved `cf:rogue-scoundrel-f4` under somebody
    else's feet.
    """
    written = 0
    per: Counter[str] = Counter()
    for n, (_, after, kind, name) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(body)
        fragment = body[after:stop]
        ref = f"{parent}{kind}{per[kind]}"
        per[kind] += 1
        if kind == "c":
            written += _card_row(out, names, ref, cls, ord_, build, fragment)
        else:
            written += _feature_row(out, names, ref, cls, ord_, build,
                                    fragment, name)
    return written


def _card_row(
    out: sqlite3.Connection, names: dict[str, dict[str, str]],
    ref: str, cls: str, ord_: int, build: str, fragment: str,
) -> int:
    """One power card inside a feature section, read in the power dialect.

    `sanitise.power_spec` is what reads a card everywhere else, so it
    reads this one too rather than the prose flattener above: the card is
    the power dialect exactly, and flattening it would file the keyword
    line and the flavour as rules text.
    """
    name = ""
    heading = _CARD_NAME.search(fragment)
    if heading:
        name = _plain(heading.group(1))
        level = _CARD_LEVEL.search(fragment)
        if level:
            name = name.replace(_plain(level.group(1)), "").strip()
    if not name:
        return 0
    spec = sanitise.power_spec(fragment, ref, name)
    if len(spec) < 20:
        return 0
    out.execute(
        "INSERT OR REPLACE INTO class_feature VALUES (?,?,?,?,?,?)",
        (ref, cls, ord_, build, spec, _reprint_of(out, spec)),
    )
    names[ref] = {"name": name, "flavour": sanitise.flavour(fragment)}
    return 1


#: `spec` -> `power.ref`, built once. Rebuilt per connection, because the
#: build makes a fresh one.
_BY_SPEC: dict[int, dict[str, str]] = {}


def _reprint_of(out: sqlite3.Connection, spec: str) -> str | None:
    """The `power` row this card is byte-identical to, if any.

    **Exact match only.** Nine more cards agree with a power row on their
    first eighty characters and diverge after; those are a tail for somebody
    to read, not to alias automatically -- a card that has been edited is a
    different card. Matching on *name* would be worse still, since a feature
    and the power it grants routinely share one.
    """
    table = _BY_SPEC.get(id(out))
    if table is None:
        table = {}
        for pref, pspec in out.execute("SELECT ref, spec FROM power"):
            key = (pspec or "").strip()
            if key:
                table.setdefault(key, pref)
        _BY_SPEC[id(out)] = table
    return table.get((spec or "").strip())


def _plain(fragment: str) -> str:
    from .html import text as _text

    return _text(fragment)


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
        # **Columns named rather than counted.** `VALUES (?,?,...)` broke the
        # moment a column was added -- "table power has 13 columns but 12 values
        # were supplied" -- and the next person to add one should not have to
        # find this line. `wields` is filled by a late pass, not here.
        out.execute(
            "INSERT INTO power (ref, id, class, level, usage, action, kind,"
            " reach, keywords, books, spec, score)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
    report.themed, report.talents = _theme_powers(source, keep)
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
        # The same argument as `cls`, one column over. `Kind` is copied
        # verbatim from the compendium, and for thirteen rows it holds
        # the **race's printed name** where every other racial power
        # holds "Racial" -- so the name this function exists to keep out
        # of the table walked in beside it. Every row here is a racial
        # power by construction, which is what the column should say.
        p.kind = "Racial"
        keep(p)
        written += 1
        # **A second card inside a racial entry needs its ref too.** The class pass
        # has called `parse_extra` all along and neither rescuer did, so a racial or
        # theme power printing two cards lost the suffixed ref for the second one --
        # 232 of the 375 the parser finds. That is what put `spec.power_ref()` on 37
        # rows: the card says "you can use the secondary power at will" and there was
        # nothing in the database to point at.
        for extra in power_parser.parse_extra(dict(row), row["Txt"]):
            extra.kind = "Racial"
            keep(extra)
            written += 1
    return written


#: The two `Class` values that name no class and no race. The class pass
#: takes `Class IN (CLASSES)` and the racial pass takes the races beside
#: it; these were taken by neither, so 499 theme powers and 10 wild
#: talents were absent from the build and from the registry -- and the
#: eighteen feats that ride on nine of those theme powers read as "named
#: in prose with no ref anywhere", which sent a sweep looking for the
#: fault in the spec extractor, where it is not.
_THEME_CLASS = "Theme Power"
_TALENT_CLASS = "Wild Talent Power"

#: What `cls` says when a power's owner is not a class. Lower case, so it
#: cannot be read as one of the 25 capitalised class names and cannot be
#: dealt by `chargen.loadout`, and a category rather than a name: nothing
#: in the compendium is *called* either of these.
_THEME = "theme"
_TALENT = "wild talent"

#: The values `Kind` is supposed to hold. A theme power's is copied
#: verbatim from the compendium and for 304 of them it is a word off the
#: **theme's printed name** -- "Minstrel", "Nomad", "Adept" -- and
#: `scripts/spec.py` prints that column to an author.
_POWER_KINDS = ("Attack", "Utility", "Feature")


def _theme_powers(
    source: sqlite3.Connection,
    keep: Callable[[power_parser.Power], None],
) -> tuple[int, int]:
    """The powers a theme grants, and the wild talents beside them.

    `cls` is the theme's **alias ref** -- the `x7_642` that
    `_other_names` already mints for every row of the `Theme` table --
    for the reasons `_racial_powers` gives one column over: the theme's
    printed name in a readable column is a leak, and anything spelled
    like a class would be dealt by `chargen.loadout` to every character
    of it. A theme is not a class, and unlike a race it has no table of
    its own here; the alias ref is the one handle the project already
    has for it, so the same theme is the same string in both places.

    Nothing deals a theme, so no character gains a row from this. The
    import exists because the **feats** name these powers: without a ref
    the name reaches the author as prose, which is the thing this
    project may not do.

    Wild talents get a plain `wild talent` instead. They are the one
    group with no owner printed anywhere -- no table, no entry, nothing
    to point at -- and one of the feats here chooses three of them, so
    they need a handle that can be queried as a set.
    """
    themes = {
        (r["Name"] or "").strip(): f"x{_ALIAS_TABLES.index('Theme')}_{r['ID']}"
        for r in source.execute("SELECT ID, Name FROM Theme")
        if (r["Name"] or "").strip()
    }
    # Longest first. Two pairs of themes share the first two words of
    # their names, and 46 cards name a theme whose name contains a
    # shorter theme's -- shortest first would file both under the stub.
    longest = sorted(themes, key=len, reverse=True)
    themed = talents = 0
    rows = source.execute(
        "SELECT * FROM Power WHERE Level <= ? AND Class IN (?, ?) ORDER BY ID",
        (MAX_POWER_LEVEL, _THEME_CLASS, _TALENT_CLASS),
    )
    for row in rows:
        p = power_parser.parse(dict(row), row["Txt"])
        if (row["Class"] or "").strip() == _TALENT_CLASS:
            p.cls = _TALENT
            talents += 1
        else:
            name = _theme_of(row["PlainTxt"], longest)
            p.cls = themes.get(name, _THEME)
            # **The theme's name opens the spec**, the way the race's
            # opens a racial card's -- `<theme> Utility 2` where a class
            # power prints `Fighter Utility 2`. That is the first line
            # an author is shown, so all 499 of them would have handed
            # over a printed name, and `leaks.py --specs` would not have
            # said so: most theme names are two ordinary English words
            # and `identifies` waives those. Swapped here, where the
            # theme is already known by name, rather than by position
            # the way `_racial_labels` has to guess it.
            if name:
                p.spec = sanitise.scrub(p.spec, {name: p.cls})
            themed += 1
        if p.kind not in _POWER_KINDS:
            p.kind = "Theme"
        keep(p)
        # The same second card the racial pass above was losing, for the same
        # reason: `parse_extra` was only ever called by the class pass.
        for extra in power_parser.parse_extra(dict(row), row["Txt"]):
            extra.cls = p.cls
            if extra.kind not in _POWER_KINDS:
                extra.kind = p.kind
            keep(extra)
    return themed, talents


def _theme_of(plain: str, longest: list[str]) -> str:
    """Which theme printed this card, off its own page.

    The `Class` column says only "Theme Power" and `Kind` holds a single
    word of the name, so neither identifies the theme. The card's second
    line does: every one of the 499 opens `<theme> Feature <name>`, and
    matching the whole printed name against the head of that line is
    exact for all of them.
    """
    lines = [ln.strip() for ln in (plain or "").split("\n") if ln.strip()]
    head = lines[1] if len(lines) > 1 else ""
    for name in longest:
        if head.startswith(name):
            return name
    return ""


#: `Perception DC 22: The character notices the false stonework.` 356 of the
#: 631 trap blocks carry one; the rest print none and are unnoticeable in
#: advance by construction.
_TRAP_DC = re.compile(r"Perception\s+DC\s+(\d+)", re.I)
#: `Attack: +4 vs. Reflex`. The bonus is printed as a finished total the way a
#: monster's is, so `world.scaling` takes the level back out of it.
_TRAP_ATTACK = re.compile(r"Attack:?\s*([+-]\s*\d+)\s*vs\.?\s*(\w+)", re.I)
#: `Hit: ... takes 3d10 damage`. The dice only -- the rest of the Hit line is
#: rules text for somebody to write as code, like a monster's.
_TRAP_DAMAGE = re.compile(r"(\d+d\d+(?:\s*\+\s*\d+)?)\s+damage", re.I)


def _traps(source: sqlite3.Connection, out: sqlite3.Connection,
           names: dict[str, dict[str, str]]) -> int:
    """Every trap and hazard block, which nothing had ever read.

    `content/terrain.py` puts traps on real boards and invents their numbers
    off the monster curve -- `level + 5` to hit, `1d10 + level` damage --
    because it had nothing to read. This is the row it needed.

    Four numbers are parsed and the rest is kept as a sanitised block, which
    is the split `monster.py` makes between a stat block and its abilities.
    The attack bonus is stored **as printed**, level included, for the same
    reason a monster's is: `world.scaling` takes the level back out, so the
    two sides of a fight move together when the treadmill is turned down.
    """
    written = 0
    for tid, name, level, role, kind, plain in source.execute(
        "SELECT ID, Name, Level, Role, Type, PlainTxt FROM Trap ORDER BY ID"
    ):
        spec = " ".join((plain or "").split())
        # The page opens by repeating its own name, sometimes twice, the way
        # a companion's does.
        for _ in range(3):
            if name and spec.startswith(name):
                spec = spec[len(name):].lstrip()
        spec = re.split(r"\s*Published in\b", spec)[0].strip()
        if len(spec) < 20:
            continue
        ref = f"t:{tid}"
        dc = _TRAP_DC.search(spec)
        hit = _TRAP_ATTACK.search(spec)
        dmg = _TRAP_DAMAGE.search(spec)
        out.execute(
            "INSERT OR REPLACE INTO trap VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ref,
                tid,
                int(m.group()) if (m := re.search(r'\d+', str(level or ''))) else None,
                (role or "").strip().lower(),
                (kind or "").strip().lower(),
                int(dc.group(1)) if dc else None,
                int(hit.group(1).replace(" ", "")) if hit else None,
                hit.group(2).strip().lower() if hit else None,
                dmg.group(1).replace(" ", "") if dmg else None,
                sanitise.scrub(spec, {name: ref}),
            ),
        )
        names[ref] = {"name": name}
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


#: `href="power.php?id=NNNN"` inside a feat's Associated Powers block. The id
#: is the compendium's own `Power.ID`, which is exactly the engine's `pNNNN`.
_HREF = re.compile(r'href="power\.php\?id=(\d+)"')


def _links_resolve(source: sqlite3.Connection, out: sqlite3.Connection) -> tuple[int, int]:
    """How many linked Associated Powers members resolved, out of how many.

    **Ground truth the resolver does not use.** `_associated_refs` matches
    members by *name* -- normalising apostrophes, ranking a power over a
    class feature, un-gluing members the page wrote without a separator --
    and a name that fails to resolve looks exactly like prose, so the only
    signal was a `(+N above heroic)` tail that conflates "correctly trimmed
    because it is paragon" with "the resolver missed".

    The source HTML **links** every member, so the ids are the answer sheet.
    #221 proposed reading them instead of the names; measured, the resolver
    is already perfect -- 478 of 478 members with a heroic row -- so
    rewriting the parse would risk a record it cannot improve. This asserts
    the record instead, which is the cheap half of that issue and the half
    worth having: a regression in the name path now shows up as a number.

    Counted only where a heroic `power` row exists. The rest are above the
    project's level ceiling and there is nothing for them to point at.
    """
    # Index access: `out` carries no `row_factory`, unlike `source`.
    heroic = {r[0] for r in out.execute("SELECT ref FROM power")}
    specs = {r[0]: (r[1] or "") for r in out.execute("SELECT ref, spec FROM feat")}
    total = found = 0
    for row in source.execute("SELECT ID, Txt FROM Feat WHERE Txt LIKE '%Associated%'"):
        for wanted in _HREF.findall(row["Txt"] or ""):
            ref = f"p{wanted}"
            if ref not in heroic:
                continue
            total += 1
            found += ref in specs.get(f"f{row['ID']}", "")
    return found, total


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
    from .sanitise import identifies, scrub, set_races, vocabulary

    rules = vocabulary()
    # Which names are races', for `identifies` and for `_racial_labels`
    # below -- one set, so the checker and the scrubber cannot hold
    # different opinions about what a race is called. Handed over rather
    # than read back, because the table it would read is the one this
    # build is in the middle of writing.
    by_race: dict[str, str] = {}
    for (ref,) in out.execute("SELECT ref FROM race"):
        name = ((names.get(ref) or {}).get("name") or "").strip()
        if len(name) > 2:
            by_race[name.lower()] = ref
    set_races(frozenset(by_race))
    by_word: dict[str, list[tuple[str, str]]] = {}
    # Every name, whether or not it "identifies" -- `_label_refs` needs
    # the ones the general test waives.
    #
    # **A power wins a tie, and a class feature beats a stat block.**
    # Several class powers share a name with a monster ability, and the
    # monsters are imported first, so taking whichever ref arrived first
    # pointed five of a feat's Associated Powers clauses at a stat
    # block. A feat modifies the powers a character has; it has never
    # modified a monster's claw.
    #
    # **Preferring only a `p` was half of that.** Where no power held
    # the name the monster still arrived first and still won, and every
    # caller then threw the answer away for not being character-side --
    # so a class feature the index could have named was refused
    # instead. `Inspiring Presence` is a warlord build and also an
    # ability of one stat block, and that is why four warlord powers
    # printed the build's name to an author.
    # **Every power row this build holds**, which is not the same set as
    # `by_name`'s values and was briefly mistaken for it. `by_name` is keyed by
    # *name* and `_rank` keeps one ref per key, so a power sharing its name with
    # another is absent from the values -- and reading "absent" as "above the
    # ceiling" moved three of `f2712`'s usable members into its trimmed tail.
    # Asked of the table instead, so the answer cannot drift from what imported.
    imported = {r for (r,) in out.execute("SELECT ref FROM power")}

    by_name: dict[str, str] = {}
    by_feature: dict[str, str] = {}
    held: dict[str, list[str]] = {}
    for ref, entry in names.items():
        name = (entry.get("name") or "").strip()
        low = name.lower()
        if len(low) < 3:
            continue
        # Both spellings of the possessive. The pages set it as a curly
        # apostrophe and a spec quotes it the same way, but a lookup and a
        # printed-name key must meet somewhere, and half the callers here
        # normalise to `'`.
        keys = {low, low.replace("\u2019", "'")}
        for key in keys:
            if _rank(ref) > _rank(by_name.get(key, "")):
                by_name[key] = ref
        # **A name can be a power for one class and a feature for
        # another.** "Arcane Empowerment" is a sorcerer daily *and* the
        # artificer's class feature, and preferring a `p` on a tie sent
        # two artificer feats at the sorcerer's spell. Names are unique
        # within a kind, so the card's own noun decides -- keep a second
        # index of the `cf:` side and let `_named_powers` pick by it.
        #
        # **And a name can be a feature of several classes at once.**
        # Four divine classes print `Channel Divinity`, five classes
        # print `Ritual Casting`, three print `Psionic Augmentation`.
        # Both indexes are single-valued, so whichever class was
        # imported first won, and 213 rows that are not avenger rows --
        # cleric, paladin, invoker, runepriest -- were told they use
        # the avenger's feature. `cf:invoker-f1s0`'s own spec said "you
        # gain the `cf:avenger-f2` power". Keep every holder and let
        # `_pick` choose by the citing row's class.
        if ref.startswith("cf:"):
            for key in keys:
                held.setdefault(key, []).append(ref)
        if not identifies(low, [ref], rules):
            continue
        words = re.findall(r"[A-Za-z']+", low)
        if words:
            by_word.setdefault(words[0], []).append((name, ref))

    # A name one class holds resolves as it always did. A name several
    # hold becomes an **alternatives list**, `a/b/c`, which `_pick`
    # narrows to one using the citing row's class and otherwise leaves
    # whole. Leaving it whole is the honest answer and not a fallback:
    # `Channel Divinity` on a divine feat any of four classes may take
    # really does mean any of the four, which is exactly what those
    # feats' own `prereq` already says.
    for key, refs in held.items():
        # **Only a cross-class tie is a tie.** A class that offers the
        # same feature to two of its builds has it in the index twice --
        # `cf:warlock-f4` and `cf:warlock-f4c0` -- and that is one
        # feature, not a choice: the shortest ref is the undivided one
        # the builds share. Listing both would make 34 specs read as
        # though the warlock's curse were two different things.
        classes: dict[str, str] = {}
        for one in sorted(set(refs), key=lambda r: (len(r), r)):
            classes.setdefault(re.sub(r"-f\d.*$", "", one[3:]), one)
        ref = ("/".join(sorted(classes.values())) if len(classes) > 1
               else next(iter(classes.values())))
        by_feature[key] = ref
        # `by_name` prefers a `p` on a tie and is right to; but where it
        # settled on one of several `cf:` rows it made the same wrong
        # choice, so it takes the list too.
        if by_name.get(key, "").startswith("cf:"):
            by_name[key] = ref

    # **The feats' own index.** Kept apart from `by_name` on purpose:
    # see `_NAMED_FEAT`. The shortest ref wins a tie, which is always
    # the parent -- 139 feat names are shared by a feat and the power
    # card it prints, `f1091` and `f1091b`, and "the <name> feat" means
    # the feat.
    by_feat: dict[str, str] = {}
    for (ref,) in out.execute("SELECT ref FROM feat"):
        name = _low(((names.get(ref) or {}).get("name") or "").strip())
        if len(name) < 3:
            continue
        held_by = by_feat.get(name, "")
        if not held_by or (len(ref), ref) < (len(held_by), held_by):
            by_feat[name] = ref

    # **Which class is speaking.** The disambiguator was there all
    # along: a class feature's ref names its class, a power's row
    # stores it, and a feat's gate usually states it. A feat's sub-rows
    # -- `f278b`, the power a feat grants -- inherit their parent's.
    speaker: dict[str, str] = {}
    for table in ("power", "class_feature"):
        for ref, cls in out.execute(f"SELECT ref, class FROM {table}"):
            if cls:
                speaker[ref] = cls.lower()
    for ref, prereq in out.execute("SELECT ref, prereq FROM feat"):
        found = re.findall(r'"class"\s*:\s*"([a-z-]+)"', prereq or "")
        if len(set(found)) == 1:
            speaker[ref] = found[0]

    changed = 0
    for table in ("power", "monster_power", "class_feature",
                  "companion", "item", "item_block", "feat", "race"):
        rows = out.execute(f"SELECT ref, spec FROM {table}").fetchall()
        for ref, spec in rows:
            if not spec:
                continue
            here = set(re.findall(r"[a-z']+", spec.lower()))
            # The race a racial card names, **before anything else and
            # outside the `others` guard below**: that guard skips a row
            # naming nothing, and a racial card's level line is usually
            # the only printed name it has.
            fixed = _racial_labels(spec, by_race)
            # **A monster's ability never belongs in a character's
            # spec.** `by_word` holds every name, and several monster
            # abilities share a name with a class power this build does
            # not import -- so "you don't expend the use of <name>" on a
            # feat was resolving onto a stat block, and 112 specs told
            # an author that a feat modifies a claw.
            #
            # **Refusing the swap is not the fix**, which I learned by
            # doing it: the name then stays in the spec as prose and
            # `leaks.py --specs` goes red. Ten specs printed a
            # monster's name that way, and a leak is worse than a bad
            # pointer -- it is the thing this project may not do.
            #
            # So the name is swapped for an *opaque* token instead, the
            # `x`-ref convention `_other_names` already uses for a name
            # that will never be a row: it says a name was here without
            # saying which, and without offering an author something to
            # point a row at.
            monsters_ok = table in ("monster_power",)
            # **The creature this row belongs to**, for the guard below.
            # `m1107a0` belongs to `m1107`; a character's row has none.
            mine = re.match(r"^(m\d+)a\d+$", ref)
            own_creature = mine.group(1) if mine else ""
            others = {}
            for word in here & by_word.keys():
                for name, other in by_word[word]:
                    if other == ref or other.startswith(ref):
                        continue
                    # **A monster's ability never belongs to another
                    # monster.** #175, and the same argument the power
                    # cross-reference already makes about classes: "a
                    # cross-class reference is vanishingly rare and a
                    # one-word name is very often an ordinary verb".
                    #
                    # It is vanishingly rare across creatures too, and the
                    # 103 rows that had one were all ordinary nouns
                    # colliding with somebody's ability name -- "with its
                    # tentacles", "must be in ooze form", "makes one
                    # fullblade attack". A *sibling* ability of the same
                    # creature is kept, because that is the common and
                    # correct case.
                    #
                    # Opaque rather than refused, for the reason the note
                    # above records: refusing leaves the name in the spec as
                    # prose and `leaks.py --specs` goes red, and a leak is
                    # worse than a bad pointer.
                    # **Ask the ranked index before giving up on a name.**
                    # `by_word` is keyed on a name's first word, and that word
                    # is cut with `[A-Za-z']+` -- so `Stone's Endurance` indexes
                    # under `stone's` and `Stone\u2019s Endurance`, the same name
                    # with the curly apostrophe the pages actually set, indexes
                    # under `stone`. Different buckets for one name. The spec's
                    # own words are cut the same way, so a feat printing the
                    # curly form reached only the holders of the curly
                    # spelling -- and where that was a monster's ability and the
                    # character-side row spelt it straight, the loop never saw
                    # the row it wanted and opaqued the name below.
                    #
                    # `by_name` already normalises both spellings and already
                    # ranks a power over a feature over a stat block. Consulting
                    # it here is what makes that ranking reach this decision.
                    # 25 names are written both ways and 10 of those split a
                    # monster from a character: `Stone's Endurance` on a warden
                    # feat, and `Hunter's Quarry`, `Nature's Wrath` and
                    # `Warlock's Curse` over core class features.
                    ranked = by_name.get(_low(name), "")
                    if _rank(ranked) > _rank(other):
                        other = ranked
                    foreign = re.match(r"^(m\d+)a\d+$", other)
                    stranger = bool(
                        foreign and own_creature
                        and foreign.group(1) != own_creature
                    )
                    if stranger or (other[:1] == "m" and not monsters_ok):
                        other = f"x_{other}"
                        names.setdefault(other, {"name": name})
                    others[name] = other
            cls = speaker.get(ref) or speaker.get(re.sub(r"[a-z]\d*$", "", ref), "")
            # **The clause label is not a feat's construction.** It was
            # found on a feat and the pass was written where it was
            # found, and so 331 rows kept a printed name for want of
            # being asked. A power's build riders -- `Star Pact:`,
            # `Brutal Scoundrel:`, `Covenant of Wrath:` -- are the same
            # thing exactly: one clause per build, keyed by the build's
            # printed name, in a list the card prints. So are a race's
            # traits and a zone's modes.
            #
            # **Outside the `others` guard**, for the reason
            # `_racial_labels` is: that guard skips a row whose spec
            # names nothing `identifies` believes, and a build name is
            # two ordinary words -- `star pact`, `iron soul` -- which is
            # precisely what `identifies` waives. The rows this serves
            # are the ones it was skipping.
            # **A racial card's labelled trait names that race's own
            # row.** Same guard as the monster one above and for the
            # same reason: a label is proof of *a* name and not of
            # whose. The gnoll's `Pack Attack` is also the printed name
            # of a theme power imported by `_theme_powers`, and with
            # every name in one index the label resolved onto it -- a
            # ref an author would read as settled and write a race's
            # trait against a wolf's utility power. Narrowed by owner:
            # `speaker` holds each power's class, and a racial power's
            # class is the race's ref.
            #
            # **Refusing the swap is not the fix, here either.** Left
            # alone the label stays in the spec as the printed name --
            # three racial cards did that, and two of them had been
            # pointing at another owner's power since long before the
            # themes arrived: one at a class's feature, one at a
            # different race's card. So the name goes to the same
            # opaque `x_` token the monster arm above uses: the author
            # is told a name was here and is offered nothing false to
            # write against.
            index = by_name
            if table == "race":
                index = dict(by_name)
                # Only the names this card could be printing, so the
                # token is minted for the three that need one and not
                # for four thousand that do not.
                for n in (n for n in by_name if _spelt_out(n, here)):
                    r = by_name[n]
                    if r[:1] == "p" and speaker.get(r) != ref:
                        index[n] = f"x_{r}"
                        names.setdefault(index[n], {"name": n})
            fixed = _label_refs(fixed, index, cls, lone=table == "feat")
            # **Outside the `others` guard**, for the same reason
            # `_label_refs` is: that guard skips a row whose spec names
            # nothing `identifies` believes, and a feat name is two
            # ordinary words -- `quick draw`, `ritual caster` -- which
            # is precisely what `identifies` waives.
            fixed = _named_feats(fixed, by_feat, ref)
            if others:
                fixed = scrub(fixed, others)
                if table == "feat":
                    fixed = _associated_refs(fixed, by_name, imported)
                fixed = _named_powers(fixed, by_name, ref, by_feature, rules, cls)
            if fixed != spec:
                out.execute(f"UPDATE {table} SET spec=? WHERE ref=?", (fixed, ref))
                changed += 1
    return changed


def _spelt_out(name: str, words: set[str]) -> bool:
    """Is every word of this name somewhere in that spec?

    A cheap sieve, not a match: it says which of the thirty thousand
    indexed names a row could possibly be printing, so the work that
    follows is done on three of them.
    """
    return all(w in words for w in re.findall(r"[a-z']+", name))


def _racial_labels(spec: str, by_race: dict[str, str]) -> str:
    """Swap the race named on a racial card's level line for its ref.

    Every racial power prints one -- `<r20> Racial Power` where a class
    power prints `Fighter Attack 1` -- and 82 of them reached authors
    with the race's printed name in them. Not all of them: a race whose
    name is invented and long was already swapped by the general pass
    above, because `identifies` believes a one-word name that is in no
    dictionary. The races named after an ordinary English word are in
    the dictionary and were waived, so the same line read two different
    ways depending on what the race happened to be called.

    Position is what settles it, as it does in `_label_refs`: directly
    before the word *racial* the word is a race and not a creature type.
    Everywhere else it **must not be swapped** -- `is_kind("<type>")` is
    a sentence the engine has to be able to write, and a monster's own
    type word is deliberately kept out of the scrubber.

    Which positions those are is `sanitise.named_races`, and it is asked
    rather than repeated here: `identifies` reads the same function to
    decide whether to report one, and a checker that disagrees with the
    scrubber is how 124 specs shipped a printed name the last time.

    An `r` ref, which the guards in `_named_powers` and `_label_refs`
    would refuse. They refuse it rightly: those two positions name a
    *power*, and only a `p` or a `cf:` is one. This position names a
    race.
    """
    if not by_race:
        return spec
    out: list[str] = []
    last = 0
    for start, end, name in sanitise.named_races(spec):
        ref = by_race.get(name.lower())
        if not ref:
            continue
        out.append(spec[last:start])
        out.append(ref)
        last = end
    if not out:
        return spec
    out.append(spec[last:])
    return "".join(out)


#: `Sly Flourish : If you score a critical hit ...` -- a feat's Associated
#: Powers list, one clause per power, keyed by the power's printed name.
#: **And the same label with its class in brackets.** `Deft Strike
#: (rogue): If you move into an obscured space...` is the identical
#: construction -- a feat listing the powers it modifies, one clause
#: each -- and the bracket was all that stopped the pattern matching.
#: 39 of the 41 such labels resolve, and the 82 rows carrying
#: `spec.power_ref()` were waiting on exactly this.
#: **The curly apostrophe is in neither `\w` nor `[']`**, the same hole
#: `_NAMED`'s docstring calls out and fixes there. The pages set every
#: possessive with it, so this pattern stopped dead in the middle of
#: `Hunter's Quarry :` and every other label whose name owns something,
#: and those are among the most-cited names in the corpus.
#:
#: **And a pattern that can cross it is only half the fix.** `by_name`'s
#: keys come from `names.json`, which stores the ASCII apostrophe, so the
#: curly-to-ASCII normalisation only ever ran on the key side. The lookup
#: side has to run it too, which is what `_low` is for -- `_named_powers`
#: has always called it and this pass called a bare `.lower()`, so the
#: two spellings never met.
_LABEL = re.compile(
    r"^([A-Z][\w'\u2019 ]{2,40}?)\s*(?:\([A-Za-z]+\)\s*)?:\s", re.M
)


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
#:
#: **The curly apostrophe is in neither `\w` nor `[']`.** The pages set
#: every possessive with it, so `[\w']` stopped dead in
#: the middle of the most-cited names in the corpus -- the warlock's
#: curse, the ranger's quarry, the cleric's lore -- and matched their
#: second word alone.
#:
#: **And the noun is not always "class feature".** The pages write plain
#: "feature" and, for a race's, "trait"; three words of a four-word
#: vocabulary were being read.
_NAMED = re.compile(
    r"\b([A-Za-z][\w'\u2019]*(?:\s+[A-Za-z][\w'\u2019]*){0,3}?)"
    r"(\s+(?:racial|encounter|daily|at-will|utility|attack))*"
    r"\s+(power|class feature|feature|trait)\b"
)

#: **"the <name> feat".** The same construction one noun along from
#: `_NAMED`, and `feat` was the one noun missing from its vocabulary --
#: so the commonest cross-reference a feat page makes had no pattern at
#: all and 67 of them reached authors as printed names, on rows whose
#: only remaining gap was the name.
#:
#: The position is the whole of the argument, exactly as it is for
#: *power* and *class feature*: a run of words immediately before the
#: word *feat* is a feat's name. `identifies` is waived here for the
#: reason it is waived before a colon -- "Quick Draw" and "Ritual
#: Caster" are two ordinary words each and would never pass it in
#: running prose.
#:
#: **Its own index, never `by_name`.** `_rank` prefers a `p` and then a
#: `cf:`, so a feat sharing its name with the power it grants -- and
#: hundreds do, `f1091` prints `f1091b` -- would lose the tie and this
#: pattern would point "the <name> feat" at a power card. A feat-only
#: index cannot do that, and it is also why the character-side guard the
#: other passes carry is not needed here: every ref it can return is an
#: `f`, and an `f` is character-side by construction. There is no path
#: from here to a stat block.
_NAMED_FEAT = re.compile(
    r"\b([A-Za-z][\w'\u2019-]*(?:\s+[A-Za-z][\w'\u2019-]*){0,4}?)\s+feat\b"
)


#: The same name on the other side of the noun: "you gain the barbarian
#: **class feature** *<name>*". Rare -- one row in the corpus asks for it
#: -- and a name by construction in that position, exactly as a label
#: before a colon is.
_AFTER_NOUN = re.compile(
    r"\b(?:class feature|feature|power)\s+"
    r"([A-Z][\w'\u2019-]*(?:\s+[A-Z][\w'\u2019-]*){0,3})"
)

#: A word that may sit inside a title-case name without being capitalised.
_JOINER = r"(?:of|the|and|is|in|to|a|an)"

#: **A class feature named with no noun after it at all.** "When you use
#: your *<name>*, you and each ally adjacent to you can shift 1 square"
#: -- the largest single shape in the `c.class_feature()` queue, and
#: invisible to every pattern above because there is no *power* and no
#: *class feature* behind it to anchor on.
#:
#: Three things have to hold at once, because none of them is proof by
#: itself. The run must be **title case throughout** -- the page also
#: writes "your Charisma modifier", and the lower-case second word is
#: what says that phrase is not a name. It must be a **whole-phrase
#: match against the `cf:` index alone**, never `by_name`: the only
#: thing being claimed here is that a character has a class feature, so
#: a name whose sole holder is a power or a stat block is not a
#: candidate. And the run must be believable as a name at all, which is
#: `sanitise.identifies` -- see `_believable` for where its answer is
#: taken and the one place it is not.
_BARE_NAMED = re.compile(
    rf"\b(?:your|the)\s+"
    rf"([A-Z][\w'\u2019-]*(?:\s+(?:[A-Z][\w'\u2019-]*|{_JOINER})){{0,4}})"
)


#: The verbs that take a power for an object. A closed list, because the
#: whole of the guard below is the position and a position is only
#: evidence if the word that makes it is one of a few.
#:
#: Every one of these says *do the thing the row is named after*: you
#: **use** a power, **cast** it, **augment** it, **expend** it, **deal**
#: its damage, **replace** it with another. None of them takes an
#: abstract noun for an object in this corpus's register.
_CITES = (
    r"use[sd]?|using|cast|casts|casting|augment[s]?|augmented|augmenting"
    r"|invoke[sd]?|invoking|expend[s]?|expended|expending"
    r"|replace[sd]?|replacing|regain[s]?|regained|regaining"
    r"|deal[s]?|dealt|dealing|sustain[s]?|sustained|sustaining"
    r"|activate[sd]?|activating|trigger[s]?|triggered"
)

#: A determiner may stand between the verb and the name -- "use **your**
#: fey step", "augment **the** hand of blight" -- and is not part of it.
_THE = r"(?:your|the|a|an|this|that|its|his|her|their|each|one)"

#: **A power named as the object of a verb, with no noun behind it.** The
#: commonest citation form in the corpus and the one none of the three
#: patterns above can see: "when you cast *magic missile*", "whenever you
#: deal *sneak attack* damage", "when you augment *hand of blight*",
#: "Trigger: You use *shadow step*". Lower case, so `_BARE_NAMED`'s
#: title-case test refuses it; no *power* or *class feature* behind it, so
#: `_NAMED` never starts.
#:
#: **And the bare possessive**, which is the same claim with the verb left
#: out: "your *oath of enmity* ends", "the bonus your *inspiring presence*
#: grants". `your` is taken and `the` is not: a character's possessive
#: says the thing belongs to them, which is what a power does, while
#: `the` in running prose introduces an ordinary noun phrase far more
#: often than it introduces a name.
#:
#: **And the two prepositions that take one.** "when you hit a creature
#: with *dire radiance*", "a bonus from *divine fortune*" -- the power is
#: the instrument rather than the object, and the sentence is saying the
#: same thing. No other preposition is here: *with* and *from* name what
#: an effect came out of, where *to*, *of*, *on* and *in* take an
#: ordinary noun far more often than they take a power.
#:
#: **Case-insensitive on the trigger and only there.** A sentence
#: beginning "Your divine challenge remains in effect" is the commonest
#: single miss this pattern had, because `your` is capitalised at a full
#: stop. The name itself is matched case-blind either way -- the index is
#: keyed on lower case -- so nothing is loosened by it.
_CITED = re.compile(
    rf"\b(?i:(?:{_CITES})\s+(?:{_THE}\s+)?|(?:with|from)\s+(?:{_THE}\s+)?|your\s+)"
    rf"([A-Za-z][\w'\u2019-]*(?:\s+[A-Za-z][\w'\u2019-]*){{0,4}})"
)


def _named_powers(
    spec: str,
    by_name: dict[str, str],
    own: str,
    by_feature: dict[str, str] | None = None,
    rules: set[str] | None = None,
    cls: str = "",
) -> str:
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
        qual = quals.split()
        # **A qualifier word can also be the last word of the name**, and
        # nothing was trying it. "the sneak attack class feature" parsed
        # as the phrase "the sneak" plus the qualifier "attack", so the
        # lookup saw "sneak", "the sneak" and never "sneak attack" -- the
        # mirror image of the bug the qualifier group was added to fix.
        # Fold them in from the right, most first, and fall back to the
        # plain reading.
        for take in range(len(qual), -1, -1):
            body = words + qual[:take]
            rest = " ".join(qual[take:])
            for size in range(len(body), 0, -1):
                tail = " ".join(body[-size:])
                # The card's own noun picks the kind. "Arcane
                # Empowerment" is a sorcerer daily and the artificer's
                # class feature, so a `p`-first tie-break sent two
                # artificer feats at a spell.
                ref = None
                if noun != "power" and by_feature:
                    ref = by_feature.get(_low(tail))
                ref = _pick(ref or by_name.get(_low(tail)) or "", cls)
                # **Only a `p` or a `cf:`.** `by_name` prefers a power on
                # a tie, but a name with no character-side counterpart
                # resolves onto a monster's stat block -- 112 specs were
                # pointing a feat at a claw. A feat modifies what a
                # character has; it has never modified a monster's
                # ability.
                if ref and ref[:1] not in ("p", "c"):
                    continue
                if ref and not ref.startswith(own):
                    head = " ".join(body[:-size])
                    return " ".join(
                        w for w in (head, ref, rest, noun) if w
                    )
        return m.group(0)

    def after(m: re.Match) -> str:
        ref = _longest(m.group(1), by_feature or {}, own, cls, prefix=True)
        return m.group(0).replace(m.group(1), ref, 1) if ref else m.group(0)

    def bare(m: re.Match) -> str:
        ref = _longest(m.group(1), by_feature or {}, own, cls, prefix=True,
                       rules=rules)
        return m.group(0).replace(m.group(1), ref, 1) if ref else m.group(0)

    def cited(m: re.Match) -> str:
        ref = _cited_name(m.group(1), by_name, own, rules or set(), cls)
        return m.group(0).replace(m.group(1), ref, 1) if ref else m.group(0)

    spec = _NAMED.sub(swap, spec)
    spec = _AFTER_NOUN.sub(after, spec)
    spec = _BARE_NAMED.sub(bare, spec)
    return _CITED.sub(cited, spec)


def _cited_name(
    phrase: str, by_name: dict[str, str], own: str, rules: set[str],
    cls: str = "",
) -> str:
    """The longest prefix of `phrase` that is a cited power's printed name.

    **The guard is the position plus two words, and nothing else is
    waived.** `sanitise.identifies` would refuse most of what this
    resolves, for the reason its own docstring gives: two ordinary
    English words in a row are a coincidence in running prose. Directly
    after *cast*, *augment*, *expend* or *deal* they are not running
    prose -- they are that verb's object, and the only objects these
    verbs take are powers. It is the same argument `_label_refs` makes
    for a colon and `_believable` makes for title case, one position
    along.

    The rest of `identifies` still applies, because its other clauses
    are about the phrase and not about where it was found:
    `sanitise.cited` is those clauses, asked rather than restated here.

    **Only a `p` or a `cf:`.** `by_name` prefers a power on a tie, but a
    name with no character-side holder resolves onto a stat block, and a
    character does not cast a monster's claw -- the guard the other three
    paths carry.
    """
    words = phrase.split()
    for size in range(len(words), 1, -1):
        name = _low(" ".join(words[:size]))
        ref = _pick(by_name.get(name) or "", cls)
        if not ref or ref[:1] not in ("p", "c"):
            continue
        if ref.startswith(own) or own.startswith(ref):
            continue
        if not sanitise.cited(name, rules):
            continue
        return " ".join([ref, *words[size:]])
    return ""


def _rank(ref: str) -> int:
    """How much `by_name` wants this row when several share a name.

    A power first, then a class feature, then anything else. The
    callers all refuse a row that is neither, so the order is not a
    preference but the difference between an answer and none.
    """
    if ref[:1] == "p":
        return 3
    if ref.startswith("cf:"):
        return 2
    return 1 if ref else 0


def _low(name: str) -> str:
    return name.lower().replace("\u2019", "'")


def _pick(ref: str, cls: str) -> str:
    """One holder out of an alternatives list, by who is speaking.

    A class-feature name held by several classes is indexed as `a/b/c`
    rather than as whichever class happened to be imported first --
    see `crossref`. This is where the list is narrowed.

    **The citing row's own class is the disambiguator and it was there
    all along.** A cleric feat that says "your Channel Divinity" means
    the cleric's, and the row knows it is a cleric row. A build's slug
    is a prefix of its class's -- `cf:cleric-templar-f0` for a row whose
    class reads `cleric` -- so one test covers both.

    **A list that cannot be narrowed stays a list.** It is not a
    failure: a divine feat any of four classes may take really does
    cite any of the four, and those feats' own `prereq` already says so
    in as many words. A single ref there would be a wrong one, and a
    wrong ref is worse than a wide one -- it looks settled, and an
    author writes against it.
    """
    if "/" not in ref:
        return ref
    if cls:
        for one in ref.split("/"):
            if one == f"cf:{cls}" or one.startswith(f"cf:{cls}-"):
                return one
    return ref


def _believable(run: list[str], name: str, ref: str, rules: set[str]) -> bool:
    """Is a bare title-case run naming a class feature, or is it words?

    `sanitise.identifies` answers this, and it is asked rather than
    re-implemented, because a checker that disagrees with the scrubber is
    how 124 specs shipped a printed name the last time.

    **One clause of its answer is overridden and it is worth saying
    which.** `identifies` waives a two-word phrase built of two ordinary
    words, and its own docstring says out loud that the cost is missing a
    real name of that shape. The class features most cited in the corpus
    are exactly that shape -- two plain English words, one of them often
    the class's own noun -- so taking that clause here would refuse the
    warlock's curse, the paladin's challenge and the rogue's attack,
    which between them are most of what the queue is asking for.

    What replaces it is the position, and it is the same argument
    `_label_refs` makes for a colon: a run that is **capitalised
    throughout** and matches a printed class-feature name **whole** is
    not a coincidence, because ordinary prose does not capitalise both
    halves of "your charisma modifier".

    The first clause is kept unchanged: a run that is itself a rules
    term is mechanics, never a name. And a **single** word gets the full
    test, because one capitalised word after "your" really is an ability
    score or a keyword more often than it is a feature.
    """
    if len(run) == 1:
        return sanitise.identifies(name, [ref], rules)
    return name not in rules


def _longest(
    phrase: str,
    by_feature: dict[str, str],
    own: str,
    cls: str = "",
    prefix: bool = False,
    rules: set[str] | None = None,
) -> str:
    """The longest run of `phrase` that is a class feature's printed name.

    `cf:` only, and that is the monster guard rather than a narrower one:
    the two positions this serves name a *class feature*, so a name whose
    only holder is a stat block is not a candidate at all. The other
    paths reach `by_name`, where a monster can win a tie, and have to
    refuse an `m` afterwards.

    `rules` turns `sanitise.identifies` on. The caller passes it for the
    position where the phrase is the whole of the evidence, and omits it
    where the surrounding words are already proof.
    """
    words = phrase.split()
    for size in range(len(words), 0, -1):
        run = words[:size] if prefix else words[-size:]
        if run[-1].islower():
            continue
        name = _low(" ".join(run))
        ref = _pick(by_feature.get(name) or "", cls)
        if not ref or ref.startswith(own) or own.startswith(ref):
            continue
        if rules is not None and not _believable(run, name, ref, rules):
            continue
        rest = words[size:] if prefix else words[:-size]
        return " ".join([ref, *rest] if prefix else [*rest, ref])
    return ""


def _named_feats(spec: str, by_feat: dict[str, str], own: str) -> str:
    """Swap `<name> feat` for `<ref> feat`.

    See `_NAMED_FEAT` for why the position is proof and why the index is
    the feats' own. Longest match first, so a three-word name is not
    left as a fragment of a two-word one -- `Student of the Plague`
    rather than `the Plague`.

    **The row's own name is not a reference to itself.** A feat page
    says "this feat" and never its own name, but a feat that prints a
    power card has the card filed under `f1091b` with the parent's name
    on it, so the pair share a name and the child would otherwise
    resolve onto the parent and back.
    """
    base = re.sub(r"[a-z]\d*$", "", own)

    def swap(m: re.Match) -> str:
        words = m.group(1).split()
        for size in range(len(words), 0, -1):
            ref = by_feat.get(_low(" ".join(words[-size:])))
            if not ref or ref in (own, base):
                continue
            head = " ".join(words[:-size])
            return " ".join(w for w in (head, ref, "feat") if w)
        return m.group(0)

    return _NAMED_FEAT.sub(swap, spec)


def _label_refs(
    spec: str, by_name: dict[str, str], cls: str = "", lone: bool = True
) -> str:
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
        label = _low(m.group(1))
        # **One word is not enough outside a feat's list.** That list
        # has a heading saying its members are powers; a power card, a
        # race and an item block print their labelled clauses with no
        # such heading, and a one-word label there is a mode rather than
        # a name far more often than not -- `Darkness:` naming what a
        # zone does, `Badger:` naming a shape. Both resolve, and both
        # would be a lie. Two words is where the position starts to be
        # proof, which is the line `sanitise.cited` draws.
        if not lone and len([w for w in label.split()
                             if w not in sanitise.STOPWORDS]) < 2:
            return m.group(0)
        ref = _pick(by_name.get(label) or "", cls)
        # **Only a `p` or a `cf:`.** `by_name` prefers a power on a tie,
        # but a name with no character-side counterpart resolves onto a
        # monster's stat block -- and a feat modifies the powers a
        # character has, never a monster's claw. The same guard
        # `_named_powers` and `_associated_refs` carry.
        #
        # **`x_` is the exception**, and it is the same guard rather
        # than a hole in it: the caller has already decided this name
        # may not be pointed at and has handed over the opaque token
        # instead, exactly as the monster arm of `_cross_reference_rest`
        # does. Refusing it here would put the printed name back.
        if ref and ref[:1] not in ("p", "c") and not ref.startswith("x_"):
            return m.group(0)
        return f"{ref} : " if ref else m.group(0)

    return _LABEL.sub(swap, spec)


#: The whole `Associated Powers:` line, to the end of the spec or the next
#: blank line. Comma-separated, and a member may carry its own clause
#: after a colon -- `Sly Flourish : only when used as a melee attack`.
_ASSOCIATED = re.compile(r"^Associated Powers\s*:\s*(.+)$", re.M | re.S)

#: A ref as `_named_powers` and `_label_refs` leave it.
_IS_REF = re.compile(r"^[pmifr]\d+[a-z]*\d*$")


def _members(body: str) -> list[tuple[str, str]]:
    """The list's members as `(name, clause)`, in printed order.

    **A line first, a comma second.** The list has two shapes on the
    page and only one of them was being read. A domain or a channel
    feat prints its members on one line, comma-separated and bare --
    `Bolstering Strike, Grasping Shards, Radiant Vengeance`. A weapon
    style feat prints **one member per line**, each with a sentence of
    its own attached after a colon, and splitting that on commas
    shreds the sentences: the first member survived because its name
    is in front of the first comma, and every member after it was a
    fragment of somebody's clause. Those fragments then resolved to
    nothing and were counted as "above heroic", so the count an author
    was shown as the size of the trimmed remainder was really the
    number of commas in the prose.

    **A sentence ends with a full stop and a list does not.** That is
    what tells the two shapes apart when a line has a colon in it, and
    it has to be asked rather than assumed: a few pages print a short
    parenthetical clause on the *first* member and then run the rest of
    the members on after it, commas and all, with no line break --
    `<name>: (Only when used as a ranged attack)<name>, <name>, <name>`.
    Reading that line as one member swallows the four that follow. So a
    line whose clause is a sentence is one member, and any other line is
    a comma-separated run in which a part may still carry a short clause
    of its own.
    """
    out: list[tuple[str, str]] = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        parts = [line] if ":" in line and line.endswith(".") else line.split(",")
        for part in parts:
            head, _, clause = part.partition(":")
            head, clause, tail = head.strip(), clause.strip(), ""
            # **A parenthetical clause is not followed by a separator.**
            # The page writes `<a>name</a>: (Only when used as a melee
            # attack)<a>name</a>`, and the tags are gone by the time
            # this runs, so the next member is simply stuck to the back
            # of the clause -- and kept there it would be a printed
            # name sitting in a spec, which is the one thing this
            # project may not do. The bracket closes the clause.
            run_on = re.match(r"^(\([^)]*\))\s*(.+)$", clause)
            if run_on:
                clause, tail = run_on.group(1), run_on.group(2)
            # **A bare clause has no bracket to close it.** The same page
            # shape without the parentheses -- `<a>name</a>: only when
            # used as a melee attack<a>name</a>` -- glued the next member
            # to the end of a sentence with nothing to split on, and
            # splitting on title case is wrong on every clause that ends
            # in a proper noun. A **ref** is an exact separator, and by
            # the time this runs the glued name is one: either the general
            # name pass resolved it (`f1309`), or `feat._trimmed` put the
            # id there because the member is above the level ceiling and
            # has no name to resolve (`f2712`). Both were losing the
            # member from the list entirely. #232.
            glued = re.match(r"^(.*?[^\s,])[\s,]+((?:p\d+[\s,]*)+)$", clause)
            if glued and not tail:
                clause, tail = glued.group(1), glued.group(2)
            if head:
                out.append((head, clause))
            for extra in tail.split(","):
                if extra.strip():
                    out.append((extra.strip(), ""))
    return out


def _associated_refs(spec: str, by_name: dict[str, str], imported: set[str]) -> str:
    """Turn a feat's Associated-Powers list into refs.

    **This is the single largest gap in the feat corpus and it was never
    an engine gap.** Sixty-odd weapon-style feats across the fighter, the
    ranger, the rogue and the warlord print a benefit gated on "a power
    associated with this feat", and the list naming those powers reached
    authors as printed names -- which this project may not read. So the
    set was unknowable and every one of those clauses was marked
    `feat.associated_powers`.

    The same argument as `_label_refs`, one step further along. A
    list under the heading *Associated Powers* is a list
    of power names by construction, so `identifies` is rightly waived:
    "Sure Strike" and "Crushing Blow" are two ordinary words each and
    would never pass it in running prose.

    **A name that does not resolve is not a failure and is not dropped
    silently.** 259 of the 737 members are paragon or epic rows -- level
    13 to 27 -- and this build imports heroic only, so they are powers no
    character here can hold. The resolved subset therefore *is* the whole
    associated set as far as the engine is concerned, and that is the
    thing an author needs to be told.

    **Those 259 are now named, not merely counted.** The count was all that
    could be said while the only handle on them was a printed name; the page
    links every member by **id**, so `feat._trimmed` puts the ref there
    instead and they are listed after the count. Every one of the 737 is
    therefore accounted for, where the bare-run-on defect was dropping some
    of them from the list entirely (#232), and a feat that will matter at
    paragon already points at the right rows (#281).

    They are listed apart from the usable ones and never folded in. A row
    must not gate on one: nothing is behind the ref until those tiers are
    imported, and a gate on an absent power is the silently-false shape this
    repo spends most of its instruments catching.
    """

    def swap(m: re.Match) -> str:
        refs: list[str] = []
        beyond: list[str] = []
        clauses: dict[str, str] = {}
        above = 0
        for head, clause in _members(m.group(1)):
            if _IS_REF.match(head):
                (refs if head in imported else beyond).append(head)
                if clause:
                    clauses.setdefault(head, clause)
                continue
            # `_low`, not `.lower()`: the list prints `Hunter's Quarry`
            # with a curly apostrophe and `by_name`'s keys carry the
            # ASCII one, so the two spellings only meet if the lookup
            # side normalises as well as the key side.
            ref = by_name.get(_low(head))
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
        if not refs and not above and not beyond:
            return m.group(0)
        seen: list[str] = []
        for r in refs:
            if r not in seen:
                seen.append(r)
        # **An above-heroic member is named, not merely counted, when the page
        # gave an id for it.** The count alone was all that could be said while
        # the only handle on those members was a name this project may not
        # print; `feat._trimmed` now resolves them by id, so the ones it reached
        # are listed. They are kept out of `seen` deliberately -- a row must not
        # gate on one, because nothing is behind it until paragon and epic are
        # imported. #281.
        rest = [r for r in dict.fromkeys(beyond) if r not in seen]
        over = above + len(rest)
        tail = f"  (+{over} above heroic{': ' + ', '.join(rest) if rest else ''})" if over else ""
        # **The member's clause is the feat.** Eleven of these feats say
        # no more in their Benefit than "you gain a benefit with any of
        # the following", and the benefit itself is written once per
        # member in the list -- so discarding the clause, as this pass
        # did, threw away the whole of the rule and left the row with a
        # set of refs and nothing to do with them.
        lines = [f"Associated Powers: {', '.join(seen)}{tail}"]
        lines += [f"{r} : {clauses[r]}" for r in seen if clauses.get(r)]
        return "\n".join(lines)

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
