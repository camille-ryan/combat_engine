"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

All eight Player's Handbook classes, to level 10.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from random import Random
from typing import Any

from combat_engine.armour import ARMOUR, ARMOUR_SPEED
from combat_engine.engine import (
    AC,
    CHA,
    CON,
    DEX,
    FORT,
    INT,
    REF,
    STR,
    WILL,
    WIS,
    Ability,
    ActionPoints,
    Budget,
    Conditions,
    DamageType,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Magic,
    Mods,
    Movement,
    Position,
    PowerPoints,
    Powers,
    Side,
    Size,
    Skills,
    Stats,
    Team,
    Weapon,
    World,
)
from combat_engine.engine import Build as BuildState
from combat_engine.engine.equipment import equip
from combat_engine.engine.movement import place
from combat_engine.engine.types import Usage

#: The printed armour table lives **below** chargen now, in
#: `combat_engine/armour.py`. Five other readers wanted it and one was the
#: kernel, which made `engine -> chargen` the only edge of its kind in the
#: tree and a documented seam claim false transitively. #852.

#: Armour that lets you add a modifier to AC. Heavy armour does not.
LIGHT = {"cloth", "leather", "hide"}


@dataclass(frozen=True)
class ClassLine:
    """One class's chassis, as its page in the book prints it.

    Every number here was read off the compendium rather than remembered.
    `defences` is a dict because the paladin adds one to all three and a
    single field could not say so.
    """

    name: str
    hp_first: int
    hp_per_level: int
    surges: int
    #: Class bonus per defence: `{"fort": 2}`, or three entries for a paladin.
    defences: dict[str, int]
    armour: str
    #: 0 none, 1 light shield, 2 heavy shield.
    shield: int
    weapons: tuple[Weapon, ...]
    #: The ability most of its powers attack with.
    key: Ability
    scores: dict[Ability, int] = field(default_factory=dict)
    #: The printed proficiency line as bands -- `{"simple:melee",
    #: "military:melee"}`. `weapons` above is one representative weapon per
    #: entry, which answers what a character *holds*; this answers what it is
    #: allowed to hold, which is a different question and the one `#285` was
    #: about. Defaulted because the three hardcoded lines below predate it.
    bands: frozenset[str] = frozenset()
    #: The compendium's own id for this class -- `c3`. `class.ref` has carried
    #: it since `30e72c6`, which was step 1 of #339; this is what lets anything
    #: resolve a class *by* it, which is step 2.
    ref: str = ""
    #: Power points at first level, for a class that augments its powers.
    #: **Only the first-level number is settled.** `game.db` carries no
    #: power point column and the by-level table is not in it, so this does
    #: not grow with level; raising it is one number when the table lands.
    power_points: int = 0
    #: How many rows a slot holds in the spellbook -- what a wizard owns
    #: per prepared power. 0 for a class that prepares nothing.
    spellbook: int = 0
    #: What the class is *for*: defender, striker, leader or controller.
    #: Off the compendium, which carries it on every one of the 25 classes --
    #: 5 defenders, 8 strikers, 7 leaders, 5 controllers -- and `SELECT *`
    #: was already fetching the column and dropping it on the floor.
    #:
    #: The monster half of the same idea is `Monster.role` (artillery, brute,
    #: soldier and the rest), and the pair is what lets either side ask "which
    #: of them is dangerous" instead of only "which of them is hurt".
    role: str = ""

    @property
    def armour_bonus(self) -> int:
        return ARMOUR.get(self.armour, 0)

    @property
    def weapon(self) -> Weapon | None:
        return self.weapons[0] if self.weapons else None


# **No `slug` on any of these.** `_table` reads the slug off the `weapon`
# table, which is where the printed name belongs; writing it here would put
# one in tracked source for the sake of a fallback that only runs when there
# is no database at all. The cost is that `query.holding("<weapon>")` cannot
# match by name in that state, which is a luxury when the database is missing.
LONGSWORD = Weapon(ref="w3610", category="military", damage="1d8", proficiency=3,
                   group="heavy blade", hands="one-handed")
MACE = Weapon(ref="w3596",
              category="simple", damage="1d8", proficiency=2, group="mace",
              hands="one-handed")
DAGGER = Weapon(ref="w3594",
                category="simple", damage="1d4", proficiency=3, group="light blade",
                thrown=(5, 10), hands="one-handed",
                properties=frozenset({"light blade", "off-hand"}))
SHORTSWORD = Weapon(ref="w3611",
                    category="military", damage="1d6", proficiency=3,
                    group="light blade", hands="one-handed",
                    properties=frozenset({"light blade", "off-hand"}))
LONGBOW = Weapon(ref="w3631",
                 category="military", damage="1d10", proficiency=2, group="bow",
                 ranged=(20, 40), properties=frozenset({"two-handed"}))
CROSSBOW = Weapon(ref="w3629", category="simple", damage="1d8", proficiency=2,
                  group="crossbow", ranged=(15, 30),
                  properties=frozenset({"two-handed"}))
#: **No `hands=` on an implement, and that is the printed state rather than
#: an omission.** `Weapon.hands` must hold a word the printed weapon table
#: uses, and that table has **no row at all** for any of the eight
#: implements below, nor for the bare fist `w:unarmed` -- only for `w3678`,
#: which is a stat-blocked weapon and does record its grip. There is no
#: `implement` table in `game.db` either, so the number does not exist to
#: copy, and inventing one would be a fact this project did not get from
#: the page.
#:
#: The `w:` refs here are this project's own, for the things the compendium
#: prices as gear rather than tabulating as weapons. That is why the slugs
#: beside them are not lookups into anything.
#:
#: Nothing asks, either: the only reader that wants a hand count is
#: `Gear.suits`, matching a *weapon* proficiency band like the assassin's
#: "simple one-handed melee", and an implement carries no `category` to form
#: such a band from. #562, where the other 10 blanks were real and are now
#: filled.
ROD = Weapon(ref="w:rod", damage="1d4", proficiency=0, group="implement")
#: The two implements nobody was carrying. The class pages print one for
#: the wizard (orbs, staffs, wands, tomes) and one for the cleric and the
#: paladin (holy symbols), and neither chassis held anything -- the wizard
#: held nothing at all. That cost nothing while every implement was plain,
#: and costs an enhancement bonus per fight the moment one is magic, which
#: is the largest bucket of magic items there is.
ORB = Weapon(ref="w:orb", damage="1d4", proficiency=0, group="implement")
HOLY_SYMBOL = Weapon(ref="w:holy-symbol",
                     damage="1d4", proficiency=0, group="implement")

#: The three printed weapon categories, longest first so "simple one-handed
#: melee" is read as `simple` and not matched on a bare word.
_CATEGORIES = ("superior", "military", "simple")


def _bands(printed: str) -> frozenset[str]:
    """The printed proficiency line as **bands**, which is what it is.

    `_arms` below turns this same line into one representative weapon per
    entry, which is right for deciding what a character *holds* and wrong for
    deciding what it is *allowed* to hold -- so a fighter dealt a longsword and
    a greataxe was recorded as trained with those two and refused the bonus on
    a warhammer its page plainly grants. #285.

    **A band stays a band and is never expanded into the weapons it covers**,
    which is Camille's call on #436: "if a character has proficiency in all
    simple and military weapons, that should hold true and not be parsed into
    individual proficiencies." So this returns tokens, and
    `Gear.proficient_with` decides coverage against `Weapon`'s own columns.

    Nineteen distinct terms appear across the 25 classes, in three shapes:

        simple melee / military ranged      a category and a reach
        military light blade                a category and a weapon group
        dagger, sling, longsword            one weapon, by its slug

    A bare weapon word is a **slug**, not a name -- `weapon.slug` holds exactly
    these, thirty of them are in `sanitise.RULES_TERMS`, and none is in
    `names.json`. That is this project's own ruling that a weapon type is
    mechanics (#339), which is why matching on the word here is not a leak.

    `simple one-handed melee` is the assassin's and keeps its middle word: it
    is narrower than `simple melee` and reading it as that would hand the
    class two-handed weapons the page withholds.
    """
    out: set[str] = set()
    for part in re.split(r",|\band\b", printed.lower()):
        term = part.strip().rstrip(".")
        if not term:
            continue
        for cat in _CATEGORIES:
            if term.startswith(cat):
                rest = term[len(cat):].strip()
                # A category with nothing after it is every weapon in it.
                out.add(f"{cat}:{rest}" if rest else f"{cat}:")
                break
        else:
            # Not a category, so a single weapon by its printed word.
            out.add(f"weapon:{term.replace(' ', '-')}")
    return frozenset(out)


#: The eight Player's Handbook classes. Numbers off the class pages.
CLASSES: dict[str, ClassLine] = {
    "fighter": ClassLine(
        "fighter", 15, 6, 9, {"fort": 2}, "scale", 2, (LONGSWORD,), STR,
        {STR: 18, CON: 14, DEX: 13, INT: 10, WIS: 12, CHA: 8},
        # "Simple melee, military melee, simple ranged, military ranged"
        bands=_bands("simple melee, military melee, simple ranged, military ranged"),
        ref="c3",
        role="defender",
    ),
    "cleric": ClassLine(
        "cleric", 12, 5, 7, {"will": 2}, "chain", 0, (MACE, HOLY_SYMBOL), WIS,
        {STR: 14, CON: 13, DEX: 10, INT: 8, WIS: 18, CHA: 12},
        bands=_bands("simple melee, simple ranged"),
        ref="c2",
        role="leader",
    ),
    "rogue": ClassLine(
        "rogue", 12, 5, 6, {"ref": 2}, "leather", 0, (DAGGER, CROSSBOW), DEX,
        {STR: 12, CON: 13, DEX: 18, INT: 10, WIS: 8, CHA: 14},
        # "Dagger, hand crossbow, short sword, shuriken, sling" -- five
        # named weapons and no band, which is the rogue's whole list.
        bands=_bands("dagger, hand crossbow, short sword, shuriken, sling"),
        ref="c6",
        role="striker",
    ),
    "wizard": ClassLine(
        "wizard", 10, 4, 6, {"will": 2}, "cloth", 0, (ORB,), INT,
        {STR: 10, CON: 13, DEX: 14, INT: 18, WIS: 12, CHA: 8},
        bands=_bands("dagger, quarterstaff"),
        ref="c9",
        role="controller",
    ),
    "paladin": ClassLine(
        "paladin", 15, 6, 10, {"fort": 1, "ref": 1, "will": 1}, "plate", 2,
        (LONGSWORD, HOLY_SYMBOL), STR,
        {STR: 16, CON: 13, DEX: 10, INT: 8, WIS: 12, CHA: 16},
        bands=_bands("simple melee, military melee, simple ranged"),
        ref="c4",
        role="defender",
    ),
    # Two blades and a bow. The two-weapon build is the one several of its
    # level 1 rows require outright, and a ranger carrying one sword could
    # never use them.
    "ranger": ClassLine(
        "ranger", 12, 5, 6, {"fort": 1, "ref": 1}, "leather", 0,
        (SHORTSWORD, SHORTSWORD, LONGBOW), DEX,
        {STR: 14, CON: 13, DEX: 18, INT: 8, WIS: 12, CHA: 10},
        bands=_bands("simple melee, military melee, simple ranged, military ranged"),
        ref="c5",
        role="striker",
    ),
    "warlock": ClassLine(
        "warlock", 12, 5, 6, {"ref": 1, "will": 1}, "leather", 0, (ROD,), CHA,
        {STR: 10, CON: 14, DEX: 13, INT: 12, WIS: 8, CHA: 18},
        bands=_bands("simple melee, simple ranged"),
        ref="c7",
        role="striker",
    ),
    "warlord": ClassLine(
        "warlord", 12, 5, 7, {"fort": 1, "will": 1}, "chain", 1, (LONGSWORD,), STR,
        {STR: 18, CON: 12, DEX: 10, INT: 14, WIS: 8, CHA: 13},
        bands=_bands("simple melee, military melee, simple ranged"),
        ref="c8",
        role="leader",
    ),
}


#: A few more weapons, for the classes that arrived with phase C.
GREATAXE = Weapon(ref="w3612", category="military", damage="1d12", proficiency=2,
                  group="axe", properties=frozenset({"two-handed"}))
QUARTERSTAFF = Weapon(ref="w3601",
                      category="simple", damage="1d8", proficiency=2,
                      group="staff", properties=frozenset({"two-handed"}))
LONGSPEAR = Weapon(ref="w3617", category="military", damage="1d10", proficiency=2,
                   group="spear", properties=frozenset({"two-handed", "reach"}))
#: **The monk's strike, under the ref the database already has for it.** This was
#: `w:unarmed`, which `game.db` does not contain -- and its 1d8 and +3 are
#: `w3678`'s numbers exactly, so the two were always one weapon
#: under two spellings. Dealt only on the proficiency line that names the monk
#: strike, which is how the duplicate went unnoticed. #282.
MONK_STRIKE = Weapon(ref="w3678", category="simple", damage="1d8",
                     proficiency=3, group="unarmed", hands="one-handed",
                     properties=frozenset({"off-hand"}))
#: **A bare fist**, which the tree had none of: every row in the `unarmed` group is
#: a *better* fist than a bare one, so "the damage die of your unarmed attack
#: increases to 1d6" was a sentence about a weapon that did not exist -- and
#: aiming it at the group *lowered* the monk's d8.
#:
#: The numbers are the compendium's rather than mine. Its Improvised Weapons entry
#: gives a one-handed improvised melee attack as **Prof. --, Damage 1d4, Group
#: "None or unarmed"**, and its Basic Attack entry says a creature with no weapon
#: makes a melee basic "using an unarmed strike (such as a kick or punch) or
#: another improvised weapon". So: 1d4, no proficiency bonus, no properties.
#:
#: Keeps the `w:unarmed` ref, which is now what it says: the plain one. Nothing
#: in the database claims it.
UNARMED = Weapon(ref="w:unarmed", category="", damage="1d4", proficiency=0,
                 group="unarmed")
STAFF = Weapon(ref="w:staff", damage="1d8", proficiency=0, group="implement")
TOTEM = Weapon(ref="w:totem", damage="1d4", proficiency=0, group="implement")
#: The last two implements nothing was carrying. Declared rather than
#: derived for the reason the five above are: an implement prints no
#: damage die and no proficiency bonus, so there is no stat line to load.
WAND = Weapon(ref="w:wand", damage="1d4", proficiency=0, group="implement")
KI_FOCUS = Weapon(ref="w:ki-focus", damage="1d4", proficiency=0, group="implement")
#: The eighth, and the only one a feat asked for before anything carried
#: it: `f3736` narrows its accuracy to a tome and there was no tome to
#: narrow to. #517.
TOME = Weapon(ref="w:tome", damage="1d4", proficiency=0, group="implement")

IMPLEMENTS = {
    w.ref: w
    for w in (ROD, ORB, HOLY_SYMBOL, STAFF, TOTEM, TOME, WAND, KI_FOCUS)
}


def _printed_weapons() -> dict[str, Weapon]:
    """Every base weapon the book prints, by ref, off the `weapon` table.

    The sixteen constants above were transcribed by hand and are left
    alone: three chassis are built on their exact `properties`, and a
    `group` that moved underneath them would change what every gated row
    reads. Everything new is derived instead, for the reason the
    seventeen derived classes are -- a hand-typed damage die is a number
    nothing can check, and a wrong one leaves every power working and the
    character quietly weaker.

    A weapon filed under two printed groups keeps the first as its
    `group` and carries the rest as properties, which is where
    `_fits_base` already looks: a khopesh is an axe that a heavy-blade
    item may still be laid on.
    """
    from combat_engine.db import game

    out: dict[str, Weapon] = {}
    try:
        rows = list(game().execute("SELECT * FROM weapon"))
    except Exception:            # no database yet; the sixteen still work
        return out
    for row in rows:
        out[row["ref"]] = Weapon(
            ref=row["ref"],
            # The printed word a card can name this weapon by. The ref used to
            # be this string and three sites un-slugged it to ask; see
            # `Weapon.slug`. #339.
            slug=row["slug"] or "",
            category=row["category"],
            hands=row["hands"] or "",
            damage=row["damage"],
            proficiency=row["proficiency"],
            reach=row["reach"],
            # A thrown melee weapon is not a ranged one: a dagger has a
            # printed range and is still swung, and `Gear.ranged` picking
            # it up would hand a rogue a ranged basic attack it does not
            # have. `melee` is the page's own word for the difference.
            ranged=(
                (row["range_short"], row["range_long"])
                if row["range_short"] and not row["melee"]
                else None
            ),
            # **The other half of the same two columns, and it used to be
            # thrown away.** The comment above is still right -- a thrown melee
            # weapon is not a ranged one, and `Gear.ranged` must not pick it up
            # -- but "not a ranged weapon" was being read as "has no range",
            # so a dagger's printed 5/10 and a javelin's 10/20 reached nothing.
            # A row printing `Ranged weapon` then fell back to whatever number
            # the card happened to have, which over-threw a dagger and
            # under-threw a javelin. #214.
            thrown=(
                (row["range_short"], row["range_long"])
                if row["range_short"] and row["melee"]
                else None
            ),
            group=row["grp"],
            properties=frozenset([*json.loads(row["properties"] or "[]"), row["hands"]]),
        )
    return out


PRINTED: dict[str, Weapon] = _printed_weapons()


#: Every field of `Weapon` the compendium's own table is the authority on.
#: `ref` is the key and `slug` is handled separately below, because a slug has
#: to be derivable for the invented implement refs the table does not carry.
_FROM_TABLE = (
    "damage", "proficiency", "reach", "ranged", "thrown",
    "group", "category", "hands", "properties",
)
#: **`enhancement` and `item` are deliberately not in it.** Both are
#: per-character: `magic_for` writes them when a magic weapon is dealt, and
#: the table carries a plain weapon's zero. Copying them here would be a
#: no-op at import and a trap for any reader who takes the tuple to mean
#: "every field", so the exclusion is named rather than implied.


def _from_the_table() -> None:
    """Give the hand-written constants what the compendium's table says.

    **The constants are what a character actually carries**, not a fallback --
    `ClassLine.weapons` references them by name -- so they need every field a
    gate reads. `Weapon.slug` is the printed word a card can name a weapon by,
    and `chargen.meets`' `weapon_prof` test and `query.holding` both ask for it.

    Nothing is written beside the constants, because a slug is a printed name
    and the constants are tracked source. Read off the `weapon` table instead,
    which is where the name belongs and the only place it is kept.

    Measured when the slug was missing: four rows went from usable to *never
    usable here* -- `audit.py` read 776 against a watermark of 772 -- because
    their printed Requirement names one weapon and nothing on the character
    could answer which weapon it was holding. That is the whole reason this
    exists; a `slug=""` on a dealt weapon is a silently un-gateable row.

    **This was called `_with_slugs` and copied the slug alone**, while the
    paragraph above promised every field a gate reads. The hand-written values
    beside the constants disagreed with the table in **10 places across 8 of
    the 20 weapons `chargen` deals**, and six of those were a property the page
    prints and the constant omitted:

    ```
    w3612  properties  missing 'high crit'    <- the fighter's greataxe
    w3596  properties  missing 'versatile'
    w3610  properties  missing 'versatile'
    w3617  properties  missing 'spear'
    w3629  properties  missing 'load minor'
    w3631  properties  missing 'load free'
    w3594  properties  'light blade' for 'light thrown'
    w3611  properties  'light blade', which is its group
    w3617  reach       1, left at the default, where the table says 2
    w3617  group       'spear', where the table says 'polearm'
    ```

    None of it showed as a failure. `Cast._high_crit` is `if weapon is None or
    "high crit" not in weapon.properties: return 0`, so a critical hit through
    the only greataxe a fighter is dealt paid **no high-crit die at all** while
    `engine/expect.py` priced one. Ten content sites gate on `versatile` and
    five on `spear`. A gate that is never true lays its effect, audits green
    and does nothing.

    `group` is the one to read twice: the constant called `w3617` a spear and
    the table calls it a polearm with `spear` among its **properties**, so the
    five `c.wielding("spear")` gates matched through the group and keep
    matching through the property -- `wielding` tests both. Fixing one without
    the other would have broken them.

    **Set in place rather than rebound.** `CLASSES` and `IMPLEMENTS` are built
    above this and hold the constant *objects*, so replacing the module globals
    with copies left every one of those references on the original -- which
    looked fixed from the outside and was not. `Weapon` is not frozen, so one
    assignment reaches every holder. That was true of the slug and is true of
    all of it. #724.
    """
    for value in list(globals().values()):
        if not isinstance(value, Weapon):
            continue
        table = PRINTED.get(value.ref)
        if table is None:
            # **An implement, and the ref already is the word.** The compendium's
            # weapon table carries no implements -- an orb has no damage die and
            # no proficiency bonus -- so these refs were invented here, out of
            # words that are in `sanitise.RULES_TERMS` and are mechanics. Taking
            # the slug from the ref writes no new name down.
            if not value.slug and value.ref.startswith("w:"):
                value.slug = value.ref.removeprefix("w:")
            continue
        if table.slug and not value.slug:
            value.slug = table.slug
        # `column`, not `field`: `dataclasses.field` is imported at the top
        # of this module and a loop variable of that name shadows it.
        for column in _FROM_TABLE:
            setattr(value, column, getattr(table, column))


_from_the_table()

#: The arms the chassis dealt none of, and that a printed benefit names.
#:
#: Named for the **group** where the sentence is "you gain proficiency
#: with all hammers" and the engine needs one weapon to stand for the
#: line, and for the weapon where the card names a weapon. One per line,
#: the way `_arms` deals one per proficiency line: a character holds one
#: thing, and a second hammer would only be a second way to be the same.
HAMMER = PRINTED.get("w3607")
POLEARM = PRINTED.get("w3615")
FLAIL = PRINTED.get("w3605")
PICK = PRINTED.get("w3608")
AXE = PRINTED.get("w3603")
SPEAR = PRINTED.get("w3598")
FALCHION = PRINTED.get("w3633")
SHORTBOW = PRINTED.get("w3630")
SLING = PRINTED.get("w3628")
BASTARD_SWORD = PRINTED.get("w3621")
SPIKED_CHAIN = PRINTED.get("w3623")
SCIMITAR = PRINTED.get("w3609")
SICKLE = PRINTED.get("w3597")
SCYTHE = PRINTED.get("w3602")
BLOWGUN = PRINTED.get("w3662")
GARROTE = PRINTED.get("w3663")
BOLA = PRINTED.get("w3661")
NET = PRINTED.get("w3660")
WHIP = PRINTED.get("w3622")


def _from_the_book() -> dict[str, ClassLine]:
    """The classes phase C brought in, read off the `class` table.

    The eight above were transcribed by hand and are left alone -- they
    carry judgement the table cannot hold, like the ranger's two blades
    *and* a bow, which several of its rows require outright.

    These seventeen are derived instead. Seventeen chassis by hand is
    seventeen chances to mistype a number that nothing would catch: every
    power would work and the character would quietly be wrong. The
    derivation was checked against all eight hand-written lines first --
    hit points, per level and surges agree exactly -- which is the only
    reason to trust it for the rest.
    """
    from combat_engine.db import game

    picks = {
        "cloth": (), "leather": (), "hide": (),
    }
    del picks
    out: dict[str, ClassLine] = {}
    try:
        rows = list(game().execute("SELECT * FROM class ORDER BY name"))
    except Exception:            # no database yet; the eight still work
        return out

    for row in rows:
        name = row["name"].lower()
        if name in CLASSES or not row["hp_first"]:
            continue
        out[name] = ClassLine(
            name,
            row["hp_first"],
            row["hp_per_level"],
            row["surges"],
            _defences(row["defences"] or ""),
            _heaviest(row["armour"] or ""),
            0,                   # a shield is a build choice, not a chassis
            _arms(row["weapons"] or "", row["implements"] or ""),
            _abilities(row["abilities"] or "")[0],
            _spread(_abilities(row["abilities"] or "")),
            bands=_bands(row["weapons"] or ""),
            ref=row["ref"] or "",
            role=(row["role"] or "").lower(),
        )
    return out


def _defences(printed: str) -> dict[str, int]:
    """"+1 Reflex, +1 Will" -> {"ref": 1, "will": 1}."""
    short = {"fortitude": "fort", "reflex": "ref", "will": "will"}
    out: dict[str, int] = {}
    for m in re.finditer(r"\+(\d)\s*(Fortitude|Reflex|Will)", printed, re.I):
        out[short[m.group(2).lower()]] = int(m.group(1))
    return out


def armour_opened(feats: list[str]) -> tuple[frozenset[str], int]:
    """The armour categories and best shield this character's feats open up.

    **A build-time sentence, like the weapon half one function down.** "You
    gain proficiency with scale armor" has no moment in a fight to happen
    in -- the gear is already on when the first initiative is rolled -- so
    it is read off the feat's own `proficiency=` header here rather than
    being a verb nothing could call. `#568`.

    Split from `proficiency` rather than folded into it because that one
    returns `Weapon`s and an armour ref is not one: `PRINTED.get(want) or
    IMPLEMENTS.get(want)` are both weapon tables, so an `a...` ref yielded
    **nothing, silently**, which is the fault `#568` is filed on.

    A ref naming no armour row contributes nothing rather than raising --
    the same honest direction `proficiency` takes, where the row keeps its
    marker and `blocked.py` keeps saying so.
    """
    from combat_engine.armour import category_of, shield_weight
    from combat_engine.engine.dsl import REGISTRY

    words: set[str] = set()
    shield = 0
    for ref in feats:
        declared = REGISTRY.get(ref)
        for want in getattr(declared, "proficiency", ()) or ():
            if not want.startswith("a"):
                continue
            printed = category_of(want)
            if not printed:
                continue
            if printed.endswith("shields"):
                shield = max(shield, shield_weight(want))
            else:
                words.add(printed)
    return frozenset(words), shield


def grace_doubled(who: Character) -> frozenset[str]:
    """The deprivation purposes this character survives twice as long of.

    **Read off the rows' own `grace_doubled=` headers**, the way
    `armour_opened` one function up reads `proficiency=` -- a build-time
    sentence with no moment in a fight to happen in, and the campaign's
    clock asks about it hours later.

    Takes a `Character` rather than a ref list, because the rows that carry
    this are **racial traits**: a character's feats are a list it holds and
    its traits come from its race, so the caller cannot hand them over
    without knowing how to enumerate them. `_racial_trait_refs` is that,
    and it is the same question `spawn` already answers when it arms them.

    Empty for every character but the one race that prints it, so the
    caller's arithmetic is unchanged by default -- which is what keeps
    `#971`'s shared clock and shared DC ladder exactly as they were. #1140.
    """
    from combat_engine.engine.dsl import REGISTRY

    out: set[str] = set()
    for ref in _racial_trait_refs(who.race):
        declared = REGISTRY.get(ref)
        out |= {str(w).strip().lower()
                for w in (getattr(declared, "grace_doubled", ()) or ())}
    return frozenset(out)


@cache
def _racial_trait_refs(race: str) -> tuple[str, ...]:
    """Every declared racial-trait ref a race carries.

    Off the registry rather than the database, for `_declared_chassis`'s
    reason: a row the tree has not written cannot carry a header, so the
    database's wider list would only add refs with nothing to read.
    """
    if not race:
        return ()
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    want = f"rt:{race}-"
    return tuple(sorted(r for r in REGISTRY if r.startswith(want)))


def _heaviest(printed: str) -> str:
    """The best armour the class is trained in, which is what it wears."""
    for kind in ("plate", "scale", "chain", "hide", "leather", "cloth"):
        if kind in printed.lower():
            return kind
    return "cloth"


def _arms(weapons: str, implements: str) -> tuple[Weapon, ...]:
    """Something to fight with, and something to cast through.

    One representative weapon per proficiency line rather than the whole
    list: a character holds one thing, and `chargen.loadout` picks from
    what it is given.
    """
    text = weapons.lower()
    held: list[Weapon] = []
    if "monk unarmed" in text:
        held.append(MONK_STRIKE)
    elif "longspear" in text:
        held.append(LONGSPEAR)
    # Blades before the generic lines, because three classes print a
    # blade proficiency *and* a simple-melee one, and falling through to
    # the simple line handed them a mace. That made `warding()` -- which
    # needs "a light blade or a heavy blade" in hand -- read 0 on every
    # swordmage the tree deals, so a feature written today was inert
    # before it shipped. The assassin was worse: it prints "simple
    # **one-handed** melee", which the `simple melee` test does not
    # match, so it was dealt no melee weapon at all and swung a crossbow.
    #
    # A named weapon wins over a group, and a light blade over a heavy
    # one: the only rows in the tree that gate on a group want
    # `light blade`, and nothing yet asks for a heavy one specifically.
    elif "longsword" in text:
        held.append(LONGSWORD)
    elif "light blade" in text or "short sword" in text:
        held.append(SHORTSWORD)
    elif "heavy blade" in text or "military melee" in text:
        held.append(LONGSWORD)
    elif "simple melee" in text:
        held.append(MACE)
    # A longbow is *military* ranged and a crossbow is simple, so a class
    # printed with military ranged proficiency gets the bow. Handing every
    # ranged class a crossbow left the seeker -- a bow controller whose rows
    # say "Requirement: you must be wielding a bow" -- unable to use five of
    # its own powers, and the audit could only report them unusable.
    if "military ranged" in text:
        held.append(LONGBOW)
    elif "simple ranged" in text:
        held.append(CROSSBOW)
    if "staff" in implements.lower():
        held.append(STAFF)
    elif "totem" in implements.lower():
        held.append(TOTEM)
    elif implements.strip():
        held.append(ROD)
    return tuple(held)


def _abilities(printed: str) -> list[Ability]:
    """"Wisdom, Dexterity, Constitution" -> [WIS, DEX, CON], in that order.

    Matched on the first three letters: the enum's values are `str`, `con`,
    `dex` and the book prints the words in full, so an exact comparison
    found nothing at all and every class silently came out a Strength class.
    """
    by_name = {a.value.lower()[:3]: a for a in Ability}
    found = []
    for word in re.split(r"[,;]", printed):
        got = by_name.get(word.strip().lower()[:3])
        if got is not None and got not in found:
            found.append(got)
    return found or [STR]


#: The standard array, **before any racial bonus**. 16 is the top, and a race
#: raising the primary takes it to 18 for a +4.
#:
#: A class page prints its recommended array *after* the racial bonus -- an 18
#: at the top -- and those numbers were being used as the base while `spawn`
#: then added the racial +2 on top of them. A fighter of a Strength race came
#: out with **20**, a +5, one point of attack and one of damage above what the
#: game allows at first level, on every character that had ever been dealt.
#: **Camille's ruling, #992**, quoted because the placement below is not
#: derivable from the numbers alone:
#:
#:     "For now, just use 16, 14, 14, 13, 10, 10. The 16 should go in the
#:     primary ability score, a 14 should go in the secondary, and the other
#:     14 should shore up the last defense, if possible. For example, a
#:     swordmage with the assault option should put the 16 in intelligence,
#:     the 14 in strength, and the other 14 in wisdom or charisma to get a
#:     better will save. Might want to refine much later."
#:
#: What this replaced was `(16, 14, 14, 13, 10, 8)` -- a **maximal Method 2
#: point buy**, spending all 22 points to the point, which is a legal array
#: and is not the book's Method 1 (`16, 14, 13, 12, 11, 10`). The `8` was
#: the only part that made it maximal.
STANDARD_ARRAY = (16, 14, 14, 13, 10, 10)


def _spread(order: list[Ability]) -> dict[Ability, int]:
    """The standard array, best score to the class's first-named ability."""
    rest = [a for a in Ability if a not in order]
    return dict(zip([*order, *rest], STANDARD_ARRAY, strict=False))


#: A class's fork, as its own page draws it.
#:
#: Every PHB1 class arranges three ability scores in an **A** or a **V** and
#: asks you to take one leg. An A shares its primary -- a wizard is Int
#: whatever it does, and the fork is which secondary it leans on. A V shares
#: its secondary and forks on the *primary*, which is why a battle cleric and
#: a devoted cleric barely play the same class.
#:
#: A character takes **one leg and stays on it.** That is what makes the fork
#: mean anything: its powers come off that leg, its best score is that leg's
#: primary, and a row whose rider applies on the other side simply does not
#: apply.
@dataclass(frozen=True)
class Build:
    name: str
    primary: Ability
    secondary: Ability
    #: What it fights with, when the fork changes that. A ranger on the
    #: two-blade leg and one on the archer leg are not carrying the same
    #: things.
    weapons: tuple[Weapon, ...] = ()
    #: The damage type a leg is sworn to, for the one fork that is a
    #: choice of element rather than of ability. `c.element()` reads it.
    element: DamageType | None = None
    #: The beast companion category this leg comes with, by ref. One leg in
    #: the game has one, and it is part of the same single choice the way
    #: the element is: taking the style *is* gaining the creature.
    companion: str = ""


BUILDS: dict[str, tuple[Build, ...]] = {
    # A -- Strength either way, and the fork is what backs it up.
    # Six legs, which is what the class page lists. Each names one of the
    # six printed talents, so `cf:fighter-weaponmaster-f3` has something to ask about
    # and the two that are only a talent are no longer folded into a leg
    # that does not mean them. The scores are the page's own: where it
    # offers a choice of tertiary it is not recorded, and where it names no
    # secondary at all -- the brawling leg -- the second is the ability the
    # feature that leg is handed actually reads.
    # The first leg carries a two-handed weapon because its talent is about
    # holding one; without it the great-weapon half of `cf:fighter-weaponmaster-f3`
    # was unreachable and the leg was a great-weapon build holding a
    # longsword.
    "fighter": (
        Build("great-weapon", STR, CON, (GREATAXE,)),
        Build("guardian", STR, WIS),
        Build("arena", STR, DEX),
        Build("battlerager", STR, CON),
        Build("brawling", STR, DEX),
        Build("tempest", STR, WIS, (SHORTSWORD, SHORTSWORD)),
    ),
    # V -- the fork is the primary, and the two halves share Wisdom.
    "cleric": (Build("devoted", WIS, CHA), Build("battle", STR, WIS, (MACE,))),
    # A -- Dexterity either way, and five legs, which is what the class
    # page lists. Each names one of the four printed tactics, two of them
    # sharing one; the page gives a secondary for every leg but the one
    # that is about going unseen, which leans on Wisdom here because that
    # is the ability its own check keys off.
    # The tactic that trains the rogue in two heavier weapon groups carries
    # the mace, which is the one of the two `chargen` has a weapon for. It
    # is Charisma rather than Strength on the page, with Strength third --
    # Strength is what the tactic's own rider reads, not what the leg is.
    "rogue": (
        Build("brawny", DEX, STR),
        Build("trickster", DEX, CHA),
        Build("aerialist", DEX, CHA),
        Build("shadowy", DEX, WIS),
        Build("cutthroat", DEX, CHA, (MACE, CROSSBOW)),
    ),
    # A -- Intelligence either way.
    # **Two chassis, two sets of legs.** `control` and `war` are the
    # arcanist's printed build options (`b:c9-0`, `b:c9-3`), and
    # `cf:wizard-arcanist-f0` branches on both in its body. The six after
    # them are the **mage's** schools of magic, which is what its level-1
    # feature chooses among. `legs_for` keeps the two sets apart; without
    # that split a mage could be dealt `control` and get no school.
    #
    # **The school fixes no ability, so all six share the class's own
    # pair.** `class.abilities` for the wizard reads one primary and a
    # choice of three seconds, and `build_option` carries four printed
    # builds that are all the arcanist's -- none per school. So the second
    # is the first of the three the page offers, taken rather than derived,
    # and the leg is about which school's row is dealt. The same shape as
    # the sorcerer's four elemental legs, which also share Cha/Con.
    #
    # Six, which is `cf:wizard-mage-f0`'s own count: the refs are
    # zero-based `s0`..`s5`, and `#1085` records a session that read that
    # as five and was corrected. #1247.
    "wizard": (
        Build("control", INT, WIS),
        Build("war", INT, DEX),
        Build("enchantment", INT, CON),
        Build("evocation", INT, CON),
        Build("illusion", INT, CON),
        Build("necromancy", INT, CON),
        Build("nethermancy", INT, CON),
        Build("pyromancy", INT, CON),
    ),
    # V -- swinging or shining.
    #
    # The second leg's secondary is **Strength, off its own page** -- it says
    # "choose Strength for your second-best score, and Wisdom as your third".
    # It was Wisdom here, which is the third. #235.
    "paladin": (Build("avenging", STR, CHA), Build("protecting", CHA, STR)),
    # V -- two blades or a bow, and they are different weapons as well as
    # different scores.
    #
    # Four legs, one per printed fighting style that a row can ask about.
    # The page's own build sections name the style each one takes, and two
    # of the four were missing: the style that replaces the shared ranged
    # bonus with a bonus for running, and the one that trades a feat and a
    # step of speed for the off hand. Neither had a leg, so
    # `cf:ranger-f3` could only be kept apart from `cf:ranger-f2`
    # by sharing a bonus type, and `cf:ranger-f0` could not be written.
    #
    # The page gives no ability line for either of the two new ones -- it
    # says only which build each resembles -- so each takes the scores and
    # the arms of the leg it is described against. The fifth style is the
    # companion, and it now has one: the creature exists, its numbers load
    # from the `companion` table, and the leg carries the category so that
    # taking the style and gaining the beast stay one choice.
    #
    # The page offers eight categories and the leg names one, the way the
    # warlock's elemental leg names one damage type. It is last so that a
    # `Character` that names no build still takes the first leg and every
    # ranger already dealt stays the ranger it was.
    "ranger": (
        # **Wisdom is the ranger's third ability, not its second**, and the
        # first two legs had it as the second. Each page section names the
        # other of the pair: the melee leg leans on Dexterity for its AC and
        # the ranged one on Strength for the melee it still ends up in. The
        # three legs below were written against these two and are left alone
        # until their own sections are read. #235.
        Build("two-blade", STR, DEX, (SHORTSWORD, SHORTSWORD)),
        Build("archer", DEX, STR, (LONGBOW, SHORTSWORD)),
        Build("hunter", DEX, WIS, (LONGBOW, SHORTSWORD)),
        Build("marauder", STR, WIS, (SHORTSWORD, SHORTSWORD)),
        # Dexterity, off this leg's own section: "you count on Dexterity for
        # your AC and occasional ranged attacks, so your secondary focus is on
        # that ability score". Its page states no primary, so Strength stays.
        #
        # **Found by `legs.py`'s new check on its first run**, and missed
        # by the hand pass that found the other five: that pass only compared a
        # leg whose page stated *both* abilities, and this one states only the
        # secondary. 35 of the 90 entries state one or neither. #235.
        # **The beast is `comp:1`, and it is the only category implemented.**
        # The machinery is category-agnostic -- `loader.companion` reads any of
        # the eleven blocks and `call_companion` fields it -- so every category
        # would work the moment a ranger could choose one. **A ranger cannot.**
        # The category is one printed choice *with* the fighting style, and
        # `chargen` has no second axis to put it on, which is the same gap as
        # the warlock's pacts and the wizard's implements (#432). So the leg
        # names one, the way the warlock's elemental leg names one damage type.
        #
        # Camille's call: the bear, and only the bear. It is the toughest and
        # slowest printed category, and the numbers come off its own block
        # rather than from here -- measured against the wolf this used to name,
        # same seeds, nothing else changed:
        #
        #     bear comp:1   1d12   hp 16 + 10/level   speed 5   Str 16
        #     wolf comp:8   1d8    hp 14 +  8/level   speed 7   Str 14
        #     at level 10:  116 hp against 94, and 2d12 against 2d8 on a
        #                   beast power -- 17 against 7 on one shared seed
        #
        # So the category is genuinely exercised rather than nominally
        # present: swap the ref and every beast power swings differently.
        Build("companion", STR, DEX, (SHORTSWORD, SHORTSWORD), companion="comp:1"),
    ),
    # V -- which pact was made. Two more pacts arrived with the later books
    # and each prints a boon row of its own, so each needs a leg for the
    # row's Prerequisite to be answerable. The elemental one is the only
    # fork in the game that is a choice of *damage type* rather than of
    # ability, which is what `Build.element` is for.
    # The three the page lists by name. Derived legs gave this class two,
    # and it prints three wards -- so one ward could never belong to a leg
    # and all three were dealt to every swordmage, which is the opposite
    # of "choose one". Which ward goes with which leg is read off the
    # wards themselves and not guessed: one teleports *you* to the target
    # and swings, one reduces the damage, one teleports *the target* to
    # you. The scores are the derived pair, because the page prints build
    # names without ability lines.
    "swordmage": (
        Build("assault", INT, STR),
        Build("shielding", INT, CON),
        Build("ensnarement", INT, CON),
    ),
    # Six classes whose rows were written against legs nobody added, so
    # every `c.build(...)` in them answered False in every fight: 82
    # riders across the invoker's covenants, the warden's four, the
    # shaman's spirits, the avenger's censures, the warlord's commands
    # and two barbarian rages. `scripts/legs.py` is what found them and
    # what keeps them found.
    #
    # Named for what the **rows** ask about, which is the feature option
    # rather than the build headline -- a row says `c.build("wrath")`
    # where the page's build line prints a two-word title (`b:c127-2`). The
    # rows were
    # written first and are the consumers; renaming them to match the
    # headline would be churn for nothing.
    #
    # Scores are the derived pair reused: the pages print build names
    # without ability lines, so a third leg takes the secondary of
    # whichever printed option it sits closest to.
    "avenger": (
        Build("pursuit", WIS, DEX),
        Build("retribution", WIS, INT),
        Build("unity", WIS, INT),
    ),
    "invoker": (
        Build("wrath", WIS, CON),
        Build("preservation", WIS, INT),
        Build("malediction", WIS, INT),
    ),
    "shaman": (
        Build("protector", WIS, CON),
        Build("stalker", WIS, INT),
        Build("watcher", WIS, INT),
        Build("elemental", WIS, CON),
        Build("world speaker", WIS, CON),
    ),
    # Named `fNsM` like the other 29 sub-option legs, so the slug *is* the
    # suffix `wire.build` already resolves and no table has to pair the two.
    # These four carried the printed names instead, and the pairing written to
    # reconcile them had the middle two crossed: the page's options are
    # Constitution, **Wisdom**, **Constitution**, Wisdom, and the secondaries
    # here were Con, Con, Wis, Wis. #337.
    "warden": (
        Build("f1s0", STR, CON),
        Build("f1s1", STR, WIS),
        Build("f1s2", STR, CON),
        Build("f1s3", STR, WIS),
    ),
    # Seven pacts are printed and four had a leg, so three pact rows were
    # refused in play and their at-wills reached nobody. The three names
    # are the ones `features/warlock.py` was already written against.
    "warlock": (
        Build("infernal", CON, CHA),
        Build("fey", CHA, CON),
        Build("dark", CON, CHA),
        Build("elemental", CHA, CON, element=DamageType.FIRE),
        # Intelligence, not Constitution: this pact's own section says
        # "Intelligence is best as your secondary ability score". #235.
        Build("sorcerer-king", CHA, INT),
        Build("star", CHA, CON),
        Build("vestige", CHA, CON),
    ),
    # A -- Strength either way, and a third leg for the leader feature that
    # is a shield and a granted row rather than a score.
    "warlord": (
        Build("inspiring", STR, CHA),
        Build("tactical", STR, INT),
        Build("bravura", STR, CHA),
        Build("insightful", STR, INT),
        Build("resourceful", STR, INT),
        # **This key is not one of the six the page prints**, and it is the
        # printed name of a leg of a *different* class -- the swordmage's. So
        # `c.build()` resolves it against the character's own class, the gate
        # answers True, and the three rows that ask for it have never looked
        # wrong. `legs.py` cannot see it either: that check asks whether a
        # gated leg *exists*, and this one does.
        #
        # Left in place deliberately. Renaming it to the sixth printed option
        # moves three content gates, and `PRINTED_LEG` below is what records
        # that it has no entry until somebody does that work. #235.
        Build("shielding", STR, CHA),
    ),
    # V -- which soul. The two share Charisma and differ on the secondary
    # exactly as the derived `second-<ability>` pair did, so the order here
    # keeps the first leg the same character it always was.
    #
    # The page prints four sources and these are the two whose feature is
    # written. The other two have no leg on purpose: see
    # `cf:sorcerer-soul-rest` in `docs/blocked.json`.
    #
    # The four after them are the second feature set the class page prints,
    # which is a different pair of abilities -- Charisma over Constitution --
    # and one leg per elemental specialty, because the specialty is a single
    # choice that fixes the damage type the whole build is sworn to. They are
    # last so that a row leaning on Dexterity or Strength still audits on the
    # leg it always did. `features/sorcerer.py` reads them.
    "sorcerer": (
        Build("wild", CHA, DEX),
        Build("dragon", CHA, STR),
        Build("air", CHA, CON, element=DamageType.LIGHTNING),
        Build("earth", CHA, CON, element=DamageType.ACID),
        Build("fire", CHA, CON, element=DamageType.FIRE),
        Build("water", CHA, CON, element=DamageType.COLD),
        # **All four printed sources now, and the third and fourth are
        # named rather than spelled as a ref.** This was `Build("f0s2",
        # CHA, DEX)` plus nothing for the fourth, with a comment saying
        # Dexterity was chosen "because that is the modifier its own
        # damage clause spends" -- a derived pair, where the page prints
        # one. `build_option` carries all four with their abilities, and
        # the two added here are read off it rather than reasoned to.
        #
        # They matter now because `#1191` made the original sorcerer a
        # dealable chassis. While it was unreachable an ungated soul row
        # cost nothing; dealt, a base sorcerer held **two** sources at
        # once -- `cf:sorcerer-f0s0` and `-f0s2` together -- which is
        # `#851`'s "one character being two sub-classes" inside one
        # chassis. A leg per source is what stops that, and it is the
        # same arrangement the elementalist's four already use.
        Build("storm", CHA, DEX),
        Build("cosmic", CHA, STR),
    ),
    # A -- Strength either way, and the fork is which second ability the
    # rages lean on. The derivation had already found the right pair off
    # the ability line; what it could not find is what each leg is called,
    # and the page's build sections name both along with the class feature
    # each one takes. Two of the four printed builds are here: the other
    # two give no ability order at all, so a leg for either would be an
    # invented pair of scores.
    # Four printed rages plus the Essentials one, which its own rows name.
    "barbarian": (
        Build("rageblood", STR, CON),
        Build("thaneborn", STR, CHA),
        Build("thunderborn", STR, CON),
        Build("whirling", STR, CHA),
        Build("berserker", STR, CON),
    ),
    # Eight more classes whose page prints more options than the class had
    # legs, so every option armed for every character of the class and the
    # printed word *one* meant nothing. One leg per option.
    #
    # **Named for the ref of the option each leg takes**, not for what the
    # page calls it: `f0s1` is the leg that takes `cf:<class>-f0s1`. The
    # eleven classes above are named for the word their rows were already
    # written against, and renaming those would be churn; these are new, so
    # they are named the way a ref is and `leaks.py` stays honest.
    #
    # The secondary is the ability the **option's own text** spends -- a
    # mantle that pays a Wisdom modifier is the Wisdom leg. Where the
    # option names no ability, the leg keeps the class's first derived
    # secondary, which is the one every character of that class already
    # had; that keeps a leg from inventing an ability line the page does
    # not print.
    "ardent": (
        Build("f0s0", CHA, WIS),
        Build("f0s1", CHA, CON),
        Build("f0s2", CHA, CON),
    ),
    "assassin": (
        Build("f1s0", DEX, CON),
        Build("f1s1", DEX, CHA),
        Build("f1s2", DEX, CHA),
    ),
    "bard": (
        Build("f1s0", CHA, INT),
        Build("f1s1", CHA, WIS),
        Build("f1s2", CHA, CON),
    ),
    "battlemind": (
        Build("f2s0", CON, WIS),
        Build("f2s1", CON, WIS),
        Build("f2s2", CON, CHA),
        Build("f2s3", CON, CHA),
    ),
    "druid": (
        Build("f1s0", WIS, CON),
        Build("f1s1", WIS, DEX),
        Build("f1s2", WIS, CON),
        Build("f1s3", WIS, DEX),
    ),
    "monk": (
        Build("f0s0", DEX, STR),
        Build("f0s1", DEX, STR),
        Build("f0s2", DEX, STR),
        Build("f0s3", DEX, STR),
        Build("f0s4", DEX, STR),
    ),
    # Three legs, and the middle one's secondary is **Wisdom off its own
    # page** -- the other two are Charisma and it was given theirs. #235.
    "psion": (
        Build("f0s0", INT, CHA),
        Build("f0s1", INT, WIS),
        Build("f0s2", INT, CHA),
    ),
    # The second leg is the one that trades the chassis's armour for a
    # heavier blade, so it carries the blade. The armour half is not a
    # field a `Build` has -- `cf:runepriest-tradition-rest` records it.
    "runepriest": (
        Build("f2s0", STR, WIS),
        Build("f2s1", STR, WIS, (LONGSWORD, CROSSBOW)),
        Build("f2s2", STR, CON),
    ),
}
#: Which printed entry each leg is, by the `b:` ref `build_option` holds (#438).
#:
#: **A ledger beside `BUILDS` rather than a field on `Build`, because what is
#: missing from it is the point.** 70 of the 97 legs map to an entry on their
#: class's own page; the 27 that do not are four shapes and not 27 oversights:
#:
#: * **~17 are a second, orthogonal choice folded into the build field** -- a
#:   warlock's pacts, a shaman's spirits, a sorcerer's elements (which are a
#:   variant page's, not the base class's) and an avenger's censures. Content
#:   rows gate on every one of them, so none can simply go: dropping a leg does
#:   not break a build, it makes `c.build(...)` answer False forever.
#: * **5 are sub-options their page does not list as builds at all.** The monk
#:   prints three legs naming sub-options 0, 3 and 4; the assassin two naming 0
#:   and 2; the druid three naming 0, 1 and 2; the runepriest two naming 0 and
#:   2. The rest are sub-options of the feature and not legs.
#: * **4 are the derived `second-<ability>` fallback** on two classes whose
#:   pages have printed legs all along.
#: * **1 is a key the book does not have.** See `BUILDS["warlord"]`.
#:
#: A field defaulting to `""` on 97 rows would hide all four. A dict of 70
#: states them, and `scripts/legs.py` fails if a mapped leg's fork disagrees
#: with the page or if the mapping shrinks. #235.
PRINTED_LEG: dict[str, dict[str, str]] = {
    "ardent": {
        "f0s0": "b:c529-0",
        "f0s1": "b:c529-1",
        "f0s2": "b:c529-2",
    },
    "assassin": {
        "f1s0": "b:c466-0",
        "f1s2": "b:c466-1",
    },
    "avenger": {
        "pursuit": "b:c129-2",
    },
    "barbarian": {
        "rageblood": "b:c148-0",
        "thaneborn": "b:c148-1",
        "thunderborn": "b:c148-2",
        "whirling": "b:c148-3",
    },
    "bard": {
        "f1s0": "b:c104-0",
        "f1s1": "b:c104-1",
        "f1s2": "b:c104-2",
    },
    "battlemind": {
        "f2s0": "b:c124-2",
        "f2s1": "b:c124-0",
        "f2s2": "b:c124-1",
        "f2s3": "b:c124-3",
    },
    "cleric": {
        "devoted": "b:c2-1",
        "battle": "b:c2-0",
    },
    "druid": {
        "f1s0": "b:c126-0",
        "f1s1": "b:c126-1",
        "f1s2": "b:c126-2",
    },
    "fighter": {
        "great-weapon": "b:c3-3",
        "guardian": "b:c3-4",
        "arena": "b:c3-0",
        "battlerager": "b:c3-1",
        "brawling": "b:c3-2",
        "tempest": "b:c3-5",
    },
    "invoker": {
        "wrath": "b:c127-2",
        "preservation": "b:c127-1",
        "malediction": "b:c127-0",
    },
    "monk": {
        "f0s0": "b:c362-0",
        "f0s3": "b:c362-1",
        "f0s4": "b:c362-2",
    },
    "paladin": {
        "avenging": "b:c4-1",
        "protecting": "b:c4-2",
    },
    "psion": {
        "f0s0": "b:c437-0",
        "f0s1": "b:c437-1",
        "f0s2": "b:c437-2",
    },
    "ranger": {
        "two-blade": "b:c5-4",
        "archer": "b:c5-0",
        "hunter": "b:c5-2",
        "marauder": "b:c5-3",
        "companion": "b:c5-1",
    },
    "rogue": {
        "brawny": "b:c6-1",
        "trickster": "b:c6-4",
        "aerialist": "b:c6-0",
        "shadowy": "b:c6-3",
        "cutthroat": "b:c6-2",
    },
    "runepriest": {
        "f2s0": "b:c602-0",
        "f2s2": "b:c602-1",
    },
    "shaman": {
        "world speaker": "b:c147-4",
    },
    "sorcerer": {
        "wild": "b:c128-0",
        "cosmic": "b:c128-1",
        "dragon": "b:c128-2",
        "storm": "b:c128-3",
    },
    "swordmage": {
        "assault": "b:c53-0",
        "shielding": "b:c53-2",
        "ensnarement": "b:c53-1",
    },
    "warden": {
        "f1s0": "b:c134-0",
        "f1s1": "b:c134-1",
        "f1s2": "b:c134-2",
        "f1s3": "b:c134-3",
    },
    "warlock": {
        "sorcerer-king": "b:c7-2",
    },
    "warlord": {
        "inspiring": "b:c8-2",
        "tactical": "b:c8-5",
        "bravura": "b:c8-0",
        "insightful": "b:c8-1",
        "resourceful": "b:c8-3",
    },
    "wizard": {
        "control": "b:c9-0",
        "war": "b:c9-3",
    },
}


#: The classes phase C brought in, folded in beneath the eight.
#:
#: A derived line never overwrites a hand-written one: the eight above hold
#: judgement the table cannot, and a ranger carrying two blades *and* a bow
#: is the clearest case -- several of its level 1 rows require the pair
#: outright.
CLASSES.update(_from_the_book())

#: The classes that augment their powers with a pool of points. Named
#: rather than derived, because the psionic *keyword* is on the monk's rows
#: too and a monk has no points to spend.
PSIONIC = ("ardent", "battlemind", "psion")

for _psi in PSIONIC:
    if _psi in CLASSES:
        CLASSES[_psi] = replace(CLASSES[_psi], power_points=2)

#: The one class that holds more than it prepares. Two per slot, which is
#: what the printed feature gives.
CLASSES["wizard"] = replace(CLASSES["wizard"], spellbook=2)

#: A build per secondary, from the class's own ability line.
#:
#: Every class page names three abilities -- a primary and two seconds --
#: and the fork *is* the choice between those two: a Primal Predator druid
#: against a Primal Guardian, a dragon sorcerer against a wild one. The
#: names here are `second-<ability>` rather than the printed ones, because
#: the printed ones are prose and this file may not carry it.
#:
#: One build was not enough: three classes in a row reported rows whose
#: whole extra sentence is a fork rider, with no leg for `c.build(...)` to
#: answer about. A row gated on something finer than which secondary was
#: taken is still a real gap and belongs in `docs/blocked.json`.
for _name, _line in CLASSES.items():
    if _name in BUILDS:
        continue
    _order = [a for a, _ in sorted(_line.scores.items(), key=lambda kv: -kv[1])]
    _seconds = _order[1:3] or [CON]
    BUILDS[_name] = tuple(
        Build(f"second-{second.value}", _order[0], second) for second in _seconds
    )


#: Class ref -> the class word, built once from `CLASSES` itself so there is
#: no second list to go stale.
_BY_REF: dict[str, str] = {}


def class_word(key: str) -> str:
    """The class word for either spelling -- `"fighter"` or `"c3"`.

    **Step 2 of #339**, which is "teach `wire` and `chargen` to resolve either
    form". The migration rewrites 9,249 `cls=` sites from a word to a ref, and
    every one of them is only safe to change once both spellings answer.

    **Not aliases on `CLASSES`**, which is the obvious implementation and is
    wrong: four places iterate that dict as "the 25 class words" -- three of
    them in `etl/build.py`, matching compendium pages by name -- so adding
    `c3` as a key would have those match a page called `c3` and quietly change
    what the build reads.

    An unknown key comes back unchanged. That keeps this usable as a filter on
    a `cls` column that also holds `item`, a race ref and a theme ref, which
    is what `audit.py` and `show.py` already have to cope with.
    """
    if not _BY_REF:
        _BY_REF.update({line.ref: word for word, line in CLASSES.items() if line.ref})
    return _BY_REF.get(key, key)


def class_line(key: str) -> ClassLine | None:
    """One class's chassis, by word or by ref. `None` if it is neither."""
    return CLASSES.get(class_word(key))


def build_of(cls: str, name: str = "") -> Build:
    """One class's build, by name, or the first it lists.

    `cls` may be the word or the compendium ref -- see `class_word` (#339).
    """
    cls = class_word(cls)
    options = BUILDS.get(cls) or ()
    if not options:
        return Build("", CLASSES[cls].key, CON)
    for b in options:
        if b.name == name:
            return b
    return options[0]


@cache
def _chassis_map() -> dict[str, str]:
    """Every class-feature ref, beside the chassis it belongs to.

    Read off `class_feature.build`, which is the authority: the ETL mints
    `cf:{class}-{slug}` from exactly this column (`etl/build.py:1781`), so
    the column and the ref cannot disagree. Slugged here because the column
    holds the **printed** sub-class name with printed punctuation, and the
    ref spelling is the one the tree uses everywhere else.

    A blank means class-wide -- every character of the class has it,
    whatever chassis it took.

    **A ref absent from the table belongs to no chassis**, and that is not a
    gap. Four declared level-0 rows are hand-coined for features described
    only in the class's own page -- `cf:avenger-oath`, `cf:barbarian-aura`,
    `cf:rogue-tactic-club`, `cf:rogue-tactic-stealth` -- as
    `content/features/__init__.py` says of `cf:rogue-extra-damage` and its
    like. They are class-wide by the same rule as a blank.

    Cached on the database, which does not change inside a process. A
    rebuild is a new process.
    """
    from combat_engine.db import game

    return {row["ref"]: _slug_chassis(row["build"])
            for row in game().execute("SELECT ref, build FROM class_feature")}


@cache
def superseded_for(cls: str, chassis: str) -> frozenset[str]:
    """Class-wide feature refs a **named** chassis replaces. #1136.

    Camille, asked directly:

    > *"A character should only get what its class says, so for example the
    > hexblade should not get the features of the standard warlock and vice
    > versa. IIRC the major thing they share is just power selection."*

    `class_feature.build` is empty for the original ladder, and empty read
    as *"every character of this class"* -- so a character on an Essentials
    chassis held **both** ladders. Measured on the warlock: 69 rows of one
    chassis, 60 of another, and 29 class-wide ones that are the first
    book's own pact ladder, all seven pacts included. Twice the character.

    **The compendium is inconsistent about this rather than silent, which
    is the fact that decides the rule.** Of the 12 classes carrying more
    than one chassis, **4 name the base one** -- so for those every row
    already says which chassis it belongs to and nothing leaks. The other
    8 leave it blank. There is nothing to invent: the data names the base
    chassis where it bothered to.

    **The rule is level coverage, not a per-class table**, and that is
    measurable rather than a judgement. A chassis that *replaces* the
    ladder has a row at every `ord` the blank one occupies. Measured over
    all 12 pairings:

        blank ords a named chassis does NOT cover:  0, in 11 of 12
        the exception: bard -- Skald covers 0-5, the blank ladder has 6

    So a blank row applies only where the chosen chassis has no row at
    that `ord`. That drops **144** blank rows across the 12 pairings and
    keeps exactly **2** -- `cf:bard-f6` and `cf:bard-f6c0`, at the one
    uncovered level.

    **And those two are a power grant**, which is the one thing Camille
    named as shared -- `cf:bard-f6`'s whole spec is *"You gain the p2887
    power"*. So the rule and the ruling agree on the only case where a
    blanket "drop every blank" would have been wrong, which is why the
    coverage test is the rule rather than a carve-out beside it.

    **Empty when the chassis is blank**, deliberately: a class with no
    named chassis has the blank rows *as* its ladder, and dropping them
    would leave a character with no features at all. Half of the 26
    classes are in that state.
    """
    if not chassis:
        return frozenset()
    from combat_engine.db import game

    rows = game().execute(
        "SELECT ref, ord, build FROM class_feature WHERE lower(class) = ?",
        (cls.lower(),),
    ).fetchall()
    covered = {r["ord"] for r in rows
               if _slug_chassis(r["build"] or "") == chassis}
    return frozenset(r["ref"] for r in rows
                     if not (r["build"] or "").strip()
                     and r["ord"] in covered)


def _slug_chassis(name: str) -> str:
    """The ref spelling of a printed chassis name. Mirrors `etl/build._slug`."""
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


#: The name of a class's **original** ladder -- the rows whose
#: `class_feature.build` is blank, which is the first printing.
#:
#: Camille's ruling on `#1191`, asked whether the original should be a name
#: or a fallback, 2026-11-10, verbatim:
#:
#:   > *"make the original a named option."*
#:
#: The bug it settles: blank meant two things at once -- *"this row belongs
#: to every character of the class"* and *"this character took no named
#: chassis"* -- so once a class had one named chassis there was no way left
#: to ask for the plain one. Measured on the sorcerer: `elementalist` is its
#: only declared name, `superseded_for` drops all three of its class-wide
#: rows, and **every dealt sorcerer was an elementalist**.
#:
#: A generic English word rather than a printed one, because the compendium
#: prints no build name for a first printing: 8 of the 12 multi-chassis
#: classes leave the column blank, which is `superseded_for`'s own
#: measurement. The other 4 name theirs and need none of this.
#:
#: It is a **name for the blank**, not a third state: `loadout` resolves it
#: straight back to `""` before either filter reads it, so the rows a
#: character gets are identical to what the blank gave. What changes is
#: that it can be *asked for*, and that `Sheet.chassis` can record it.
ORIGINAL = "original"


#: A class feature that is one option *of* another -- `cf:X-f4s2`. The
#: distinction `ladder_row` turns on: a sub-option has siblings and so
#: must be chosen among, a parent does not.
#:
#: **Named `_FEATURE_` because `_SUB_OPTION` is taken**, by the racial-trait
#: one 230 lines down (`^rt:...-s(\d+)$`). Written as the bare name this
#: was silently shadowed by it, so the test answered **False for every
#: class feature** and `ladder_row` dealt all six Apprentice schools at
#: once -- `#851`'s exact bug, introduced by the guard against it.
_FEATURE_SUB_OPTION = re.compile(r"-f\d+s\d+$")


def ladder_row(p, level: int = 1) -> bool:  # noqa: ANN001
    """Is this class-feature row part of the chassis ladder a character of
    `level` is dealt?

    **`p.level == 0` was the whole test, and it left one written chassis
    undealable.** Every other chassis declares its ladder at level 0,
    which is this tree's spelling for "from the start". `cf:wizard-mage`
    declares its rows at their **printed** levels -- 1, 4, 5, 8, 10 -- so
    none was selected and a level-10 mage came out with **0** class
    features. 24 written, unmarked rows, reachable by nobody. #1247.

    Three clauses, and each one is load-bearing:

    * **at or below the character's level.** A level-1 mage gets the
      level-1 school and not the 10th-level one.
    * **not an attack power.** The other 4 rows above level 0 in the tree
      -- `cf:warlock-f1c10`..`c12` and `cf:barbarian-f2c0` -- are at-will
      and daily *attacks* (`is_attack=True`), and `loadout`'s `deal`
      already hands them out from the power gains: `cf:warlock-f1c11` is
      in a dealt vestige warlock's list today. Selecting one here would
      spend a **feature** on a card the attack line was going to deal, so
      the character comes out one attack power short with nothing failing.
      The split is exact: 24 traits, all the mage's, and 4 attacks, none
      of them.
    * **names a leg.** A row above level 0 is dealt only if the character's
      fork chose it. Without this, `p.level <= level` deals a level-5 mage
      all **six** Expert schools at once, which is `#851`'s "one character
      being two sub-classes" one level down and worse than dealing none --
      measured, and recorded on `declared_chassis` before this existed.
      The mage's later groups (`f3`, `f4`, `f5`, `f6`) are **dependent**
      choices -- *"a school different from the one you chose"*, *"one for
      which you have Apprentice"* -- which no leg can express, so they stay
      ungated and stay undealt. `#1247` holds that half.

    The caller still applies the leg *match* (`leg_named_by(p) in ("",
    build.name)`), so this only asks whether a leg was named at all.
    """
    # **A sub-option whose parent CHOOSES among them is not dealt**, at any
    # level, because the parent grants the one it chose. Without this a
    # level-0 sub-option with no leg gate is dealt to every character of
    # the chassis -- measured on the witch, whose two covens both arrived
    # at level 1, which is `#851` exactly.
    #
    # The leg is the other way of choosing and is tested below; this is the
    # `BUILD_OPTIONS` way, for a fork the legs cannot carry because they
    # are already spent. #642.
    if _FEATURE_SUB_OPTION.search(p.ref):
        parent = _FEATURE_SUB_OPTION.sub(
            lambda m: m.group(0).split("s")[0], p.ref)
        if parent in BUILD_OPTIONS:
            return False
    if p.level == 0:
        return True
    if p.level > level or p.is_attack:
        return False
    # **A PARENT feature above level 0 is dealt without naming a leg**, and
    # the leg clause was about sub-options all along. The risk it guards is
    # `#851`'s -- six Apprentice schools at once -- and that needs
    # *siblings*: a parent has none, so dealing one cannot over-grant. It
    # is then free to read a build-time choice and grant among its own
    # options, which is what `cf:wizard-mage-f3` does for the second
    # school a leg cannot express.
    #
    # Measured before relaxing it: of the 28 declared rows above level 0,
    # **24 are sub-options and the other 4 are attack powers** already
    # refused by the clause above. So this moved nothing on the day it
    # landed and opens the one shape that was stuck. #1247.
    return bool(leg_named_by(p)) or not _FEATURE_SUB_OPTION.search(p.ref)


def chassis_of(cls: str, named: str = "") -> str:
    """The chassis a character of this class has, defaulting to its first.

    **Only chassis the tree has actually declared are candidates, and
    getting that wrong broke eight classes in the first draft.** The
    database lists every chassis the books print, including the 17 nobody
    has written (#642). Choosing the first of *those* gave a fighter
    `knight`, which has no declared row at all, so the filter in `loadout`
    excluded the eight `weaponmaster` features it does have and the fighter
    came out with no class features whatsoever. Same for the assassin,
    barbarian, bard, druid, paladin, ranger and warlock. A wizard-only test
    could not see it; only the whole-corpus control could.

    So the candidates are chassis with a declared level-0 row, which also
    makes this self-correcting as #642 lands: a chassis becomes choosable
    exactly when it becomes real.

    **First in ref order, deliberate rather than arbitrary.** 23 of the 25
    classes declare exactly one chassis, so "first" and "only" are the same
    string and nothing is being chosen. The sorcerer declares one name plus
    class-wide rows, which is also unambiguous.

    The wizard is the single class where this is a real choice -- it declares
    `arcanist` (ten rows) and `sha-ir` (three) and has been dealt **both**,
    so every wizard carried two sub-classes' features. Ref order picks
    `arcanist`, which is right on the merits too: the class's main chassis
    and the larger ladder. `sha-ir` stays reachable by naming it, and
    `scripts/fight.py` does.

    An unknown name is returned as given rather than corrected. A caller
    asking for a chassis this class has not got gets a character with no
    chassis rows, which is louder than silently substituting the default.
    """
    if named:
        return named
    return _declared_chassis().get(cls, "")


@cache
def _declared_chassis() -> dict[str, str]:
    """Each class's default chassis: the first it has a declared row for.

    Keyed on the registry rather than the database, for the reason
    `chassis_of` gives at length. Cached on both, neither of which changes
    inside a process.
    """
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    belongs = _chassis_map()
    found: dict[str, set[str]] = {}
    for ref, power in REGISTRY.items():
        if not ref.startswith("cf:") or power.level != 0:
            continue
        chassis = belongs.get(ref, "")
        if chassis:
            found.setdefault(power.cls, set()).add(chassis)
    return {cls: sorted(names)[0] for cls, names in found.items()}


def scores_for(line: ClassLine, build: Build) -> dict[Ability, int]:
    """The class's own numbers, rearranged so the build's leg is the good one.

    What the build changes is *which ability gets which*. A battle cleric and
    a devoted cleric are the same six numbers in a different order, which is
    exactly what picking a leg means.

    **The class page's own numbers give the order, not the values.** The page
    prints its recommendation with the racial bonus already in it -- an 18 at
    the top -- so using them as a base and then adding the race again made a
    20. The ranking is what the page is really saying, and `STANDARD_ARRAY`
    supplies the values a character actually buys.
    """
    values = list(STANDARD_ARRAY)
    out: dict[Ability, int] = {}

    # 16 to the primary, the first 14 to the secondary.
    head: list[Ability] = []
    for ability in (build.primary, build.secondary):
        if ability is not None and ability not in head:
            head.append(ability)
    for ability, value in zip(head, values, strict=False):
        out[ability] = value

    # **The second 14 shores up the weakest defence**, which is the half of
    # Camille's ruling the old code could not express: it handed the third
    # value to the class page's third-ranked ability instead, so a build
    # whose page ranks a third attack stat got nothing for its worst save.
    spent = len(head)
    if spent < len(values):
        shore = _shores_up(line, out)
        if shore is not None:
            out[shore] = values[spent]
            spent += 1

    # The rest in the page's own ranking, then printed order for anything it
    # does not name. **A fixed order, never a random one** -- Camille left
    # this open ("either assigning ability scores 3 to 6 randomly, or always
    # doing it on a particular order are fine") and determinism decides it:
    # `dealt_hand` keys on `seed:cls:build.name` and the replay fixtures pin
    # the party, so a random tiebreak would add a second source of variation
    # to something that has to replay identically, and would need a
    # distribution to gate where a fixed order needs one expected sheet.
    rest = [a for a in line.scores if a not in out]
    rest += [a for a in Ability if a not in out and a not in rest]
    for ability, value in zip(rest, values[spent:], strict=False):
        out[ability] = value
    return out


def _shores_up(line: ClassLine, placed: dict[Ability, int]) -> Ability | None:
    """Which unplaced ability most needs the second 14. `#992`.

    *"the other 14 should shore up the last defense, if possible"* -- so this
    finds the weakest of the three ability defences given what is placed so
    far, and returns a free ability backing it.

    **Asked of `defences` rather than re-derived**, which matters: a class
    adds `+2` to the defence it is good at and a shield adds to Reflex, so
    the weakest defence is not simply the pair with the lowest scores.
    Re-computing `max(mod(STR), mod(CON))` here would have ignored both and
    picked the wrong save for every class with a defence bonus.

    Unplaced abilities read as 10 through `defences`' own `.get(a, 10)`,
    which is the floor the remaining `13, 10, 10` cannot go below.

    Ties broken by a fixed order and never randomly -- see `scores_for`.
    Between the two abilities backing a defence, the class page's own ranking
    wins, because that is the class stating which of the pair it would
    rather have; printed order settles what the page does not name.
    """
    pairs: dict[object, tuple[Ability, ...]] = {
        FORT: (STR, CON),
        REF: (DEX, INT),
        WILL: (WIS, CHA),
    }
    standing = defences(line, placed, 1)
    # **Will first, and Camille's own worked example is why.** The ruling's
    # swordmage puts its second 14 "in wisdom or charisma to get a better
    # will save" -- and measured, that build's Fortitude and Will are
    # **tied at 12**, because the swordmage already carries a printed +2
    # Will that the example does not mention. So the example is not a
    # statement about which defence is lowest; it is the one piece of
    # evidence about which way a *tie* should go, and it says Will.
    #
    # Fortitude before Reflex for the rest of the order, on the one asymmetry
    # this engine has: `defences` adds the shield to Reflex and to nothing
    # else, so Reflex is the least likely of the three to be the real weak
    # point. No evidence either way beyond that, and a fixed order is the
    # delegated decision.
    order = [WILL, FORT, REF]
    weakest = min(order, key=lambda d: (standing[d], order.index(d)))
    free = [a for a in pairs[weakest] if a not in placed]
    if not free:
        return None
    ranked = [a for a in line.scores if a in free]
    return ranked[0] if ranked else free[0]


#: A race's page, the way `ClassLine` is a class's.
#:
#: Every number is read off the `race` table -- the size and the ability
#: scores are columns, and the speed, the fly speed, the skill bonuses and
#: the healing-surge step are parsed out of the printed block the way
#: `content/loader.py` parses a companion's. Nothing here is transcribed:
#: a hand-typed +2 is a number nothing can check, and a wrong one leaves
#: every power working and the character quietly wrong.
#: A race's "choose one" sub-option row: `rt:<race>-s<N>`, as
#: `etl.item.sub_options` mints them. Distinct from a plain trait's
#: `rt:<race>-t<N>`, and the distinction is load-bearing -- see
#: `RaceLine.manifestations` for what collecting both together would cost.
_SUB_OPTION = re.compile(r"^rt:[a-z0-9]+-s(\d+)$")


def _sub_option_order(ref: str) -> int:
    """Printed order, from the ref. `-s10` sorts after `-s9`, not before.

    A plain `sorted()` is alphabetical, which puts `-s10` between `-s1` and
    `-s2`. One race prints thirteen of these, so the wrong order is not
    hypothetical -- and the number is the page's order, which is the only
    thing the ref carries.
    """
    found = _SUB_OPTION.match(ref)
    return int(found.group(1)) if found else -1


@dataclass(frozen=True)
class RaceLine:
    ref: str
    size: Size
    speed: int
    #: Extra movement modes and their speeds, e.g. `{"fly": 6}`.
    modes: dict[str, int]
    #: The printed word -- "Normal", "Low-light", "Darkvision". **Carried,
    #: not applied.** This engine keeps no light level and no senses, so
    #: `c.darkvision()` and `c.low_light()` are symbols several rows in the
    #: tree are already waiting on. The word is here so the day one lands
    #: there is somewhere to read it from.
    vision: str
    #: The +2s the page always gives.
    fixed: tuple[Ability, ...]
    #: The "+2 X **or** +2 Y" pair, of which one is taken. Empty for a race
    #: whose two bonuses are both fixed.
    choices: tuple[Ability, ...]
    #: "+2 History, +2 Intimidate" -> (("history", 2), ("intimidate", 2)).
    skills: tuple[tuple[str, int], ...]
    #: The healing surges the race adds or takes away, and it is usually 0.
    surges: int
    #: "+2 racial bonus to initiative checks", which three races print.
    #:
    #: A **number on the sheet**, not a trait row, because a trait cannot
    #: reach it: `Encounter.start` rolls initiative and *then* arms traits,
    #: so a row laying this bonus would lay it on a roll already made. It
    #: is the same reason the skill bonuses are laid in `spawn`.
    initiative: int
    #: The race's own racial powers, by ref.
    #:
    #: Read off the `power` table -- `kind='Racial'`, `class=<this race>`,
    #: `level=0` -- and **not** off the block's prose. Fifteen races name
    #: their power in words the importer stripped, so a spec-only reading
    #: found nothing for a third of them; the higher levels are the racial
    #: *utility* powers a character takes at 2, 6 and 10, which are slots
    #: and not something the race hands over. The ones the block does name
    #: come first, because that is the order the page offers them in.
    powers: tuple[str, ...]
    #: **Which refs the printed fork offers**, or `()` when the block
    #: prints no choice at all. `granted` picks one of these.
    #:
    #: A `bool` until #914, and the boolean could say *that* a race chooses
    #: without saying *what between* -- so for three races whose other leg
    #: is a **trait** rather than a power the candidate list held one
    #: option, and 40 seeds dealt 40 identical characters. A member may be
    #: a trait ref or a power ref; `_fork_members` derives it and carries
    #: the three rules.
    #:
    #: For the five races whose alternatives are all racial powers this is
    #: exactly `powers`, which is what keeps them dealing the same
    #: characters they dealt before.
    one_of: tuple[str, ...]
    #: The race this one is a **variant of**, or `""` for a race of its own.
    #:
    #: Nine of the 55 imported races carry no sheet numbers at all --
    #: `size=''` and `scores='{}'` -- and were skipped outright, so none of
    #: them could be named or dealt. They are not thin imports: **all 21 of
    #: their traits print a "replaces" clause**, so they are variants by
    #: construction and the page expects them to inherit.
    #:
    #: Derived rather than imported, because the clause names its target by
    #: **ref** in the stored spec and every one of the nine resolves to
    #: exactly one parent:
    #:
    #:     r54 r55 -> r2      r56 r57 r64 -> r3
    #:     r58 r59 -> r4      r67 r68     -> r1
    #:
    #: so no ETL change and no rebuild was needed for it. #896.
    parent: str = ""
    #: What this variant's traits say they **replace**, by ref, in three
    #: forms the pages actually use: a trait (`rt:r1-t0`), the ability-score
    #: pair (a bare `r1` -- "replaces the normal racial ability score
    #: bonuses for r1"), and a granted power (`p1448`).
    #:
    #: **Carried, not applied.** Nothing drops the named piece yet, which is
    #: why a variant is kept out of the *deal* below: with its own 21 traits
    #: undeclared, a dealt variant would wear its parent's traits under
    #: another name. `#813` is the issue that writes them, and this field is
    #: what it reads. #896.
    replaces: tuple[str, ...] = ()

    @property
    def traits(self) -> list[str]:
        """The trait rows written for this race, by ref.

        Found by naming rather than listed, for the reason `loadout` draws
        from the registry: a list beside the rows goes stale the moment one
        lands. A racial trait is `rt:<race>-<what it does>`, and the dash is
        part of the prefix so that `r1` does not collect `r10`'s.
        """
        # Imported for the side effect: this is what registers the rows.
        import combat_engine.content
        from combat_engine.engine.dsl import REGISTRY

        return sorted(
            r for r in REGISTRY
            if r.startswith(f"rt:{self.ref}-") and not _SUB_OPTION.match(r)
        )

    @property
    def manifestations(self) -> list[str]:
        """The race's "choose one" trait rows, by ref, in printed order.

        **Kept out of `traits` deliberately, and this is a guard rather
        than tidiness.** `traits` collects by prefix, so the moment a
        `rt:<race>-s<N>` row is declared it would be picked up with the
        rest -- and these are *alternatives*. One race prints thirteen, so
        a character would carry +1 Reflex **and** +1 Fortitude, resist 5
        fire **and** resist 5 lightning, and breathe underwater. That is
        `m5808a0`'s rule at the scale of a whole race: a row stronger than
        its printed line is worse than an absent one.

        Empty today -- none of the 18 is declared, #548 -- which is why
        this lands before them rather than after.
        """
        import combat_engine.content
        from combat_engine.engine.dsl import REGISTRY

        return sorted(
            (r for r in REGISTRY if _SUB_OPTION.match(r)
             and r.startswith(f"rt:{self.ref}-")),
            key=_sub_option_order,
        )

    def granted(self, pick: Random | None = None) -> list[str]:
        """The rows a character of this race carries into a fight.

        Its traits, and its racial powers -- or **one** of them where the
        block says to choose, which is the difference between a race that
        prints two powers and one that prints thirteen manifestations and
        asks for one.

        **A manifestation is one choice with two halves**, so the chosen
        sub-option *trait* comes in beside the chosen *power* rather than
        being picked separately. The pairing is read off the sub-option's
        own spec, which names its card -- that is what
        `etl.item.sub_options` identifies the family *by*, "the power each
        one grants, not a list of headings" -- so there is nothing to
        record and no second decision to get out of step.
        """
        from combat_engine.engine.dsl import REGISTRY

        written = [p for p in self.powers if p in REGISTRY]
        if not self.one_of:
            return [*self.traits, *written]
        # **`pick` makes the choice a choice.** Without one this answered
        # `written[:1]` for every character of the race, so a half-elf
        # always borrowed the same power of two, an `r33` always the same
        # manifestation of thirteen, and an `r44` always the same aspect of
        # three. Nothing dealt it and nothing recorded it, which is what
        # left nine feats keyed to the borrowed row unreachable: the row
        # they key on was never the one dealt.
        #
        # Seeded and uniform rather than scored. Every other build decision
        # goes through `choices.sample` against a scored option list, and
        # there is no scorer for a racial power yet -- so this is the same
        # fallback `deal_race` takes when `SCORED_CHOICES` is off, which is
        # honest about being a draw rather than a judgement. A scorer is
        # `race_options`-shaped work and can replace this without moving
        # the signature.
        #
        # `pick=None` keeps the old answer exactly, which is what lets
        # `choices.race_options` go on ranking a **race** without a
        # particular pick entering the ranking. #680.
        # **The options are `one_of`, which may name a trait.** This read
        # `self.powers`, so a fork whose other leg is a trait offered one
        # option and chose it every time -- `r6` gave the same answer for
        # 40 seeds, and nine feats keyed to the trait it never chose. #914.
        #
        # Only declared refs are offered: `r6`'s second leg is an entry
        # reading "you have the <power> power" and carries no row, so the
        # power is the playable half and the entry drops out here.
        options = [m for m in self.one_of if m in REGISTRY]
        if not options:
            return [*self.traits, *written]
        chosen = options[:1] if pick is None else [pick.choice(options)]
        # **And the legs not taken come off.** A trait leg is in `traits`
        # and would otherwise be handed over beside the power that was
        # chosen instead -- which is what the tree works around today, with
        # `rt:r6-t3` opening `if _holds(c, "p13689"): return` because the
        # dealer gave it both. That guard is now belt as well as braces.
        spurned = set(self.one_of) - set(chosen)
        kept = [t for t in self.traits if t not in spurned]
        taken = [p for p in chosen if p in self.powers]
        return [*kept, *self._manifestation_for(taken), *taken]

    def _manifestation_for(self, chosen: list[str]) -> list[str]:
        """The sub-option trait that goes with the power picked, if any.

        Returns at most one. An unwritten sub-option, or a power no
        sub-option names, gives nothing -- which is the state today and
        leaves `granted` exactly as it was.
        """
        if not chosen:
            return []
        mine = self.manifestations
        if not mine:
            return []
        from combat_engine.db import game

        held = {
            ref: spec or ""
            for ref, spec in game().execute(
                "SELECT ref, spec FROM racial_trait WHERE race = ?",
                (self.ref,),
            )
        }
        want = chosen[0]
        for ref in mine:
            if re.search(rf"\b{re.escape(want)}\b", held.get(ref, "")):
                return [ref]
        return []

    def taken(self, build: Build) -> list[Ability]:
        """Which abilities actually go up, for a character on this leg.

        The fixed ones always, plus the one of the printed pair that the
        build is built on -- which is the choice a player makes and the
        only part of the line that is not already decided. A race whose
        whole line is "+2 to one ability score of your choice" puts it on
        the primary, for the same reason.
        """
        out = list(self.fixed)
        if self.choices:
            out.append(
                next(
                    (a for a in (build.primary, build.secondary) if a in self.choices),
                    self.choices[0],
                )
            )
        elif not out:
            out.append(build.primary)
        return out


_SPEED_LINE = re.compile(r"^Speed\s*:\s*(.+)$", re.M)
_MODE = re.compile(r"\b(fly|swim|climb|burrow)\s+(\d+)\s+squares", re.I)
_VISION_LINE = re.compile(r"^Vision\s*:\s*(.+)$", re.M)
_SKILL_LINE = re.compile(r"^Skill Bonuses\s*:\s*(.+)$", re.M)
_SKILL = re.compile(r"\+(\d+)\s+([A-Z][a-z]+)")
#: A power's id, in a sentence that calls it a power. The qualifier is what
#: keeps a **trait's** label out: a block heading is a bare id on its own
#: line -- "x_m1031a4 : You gain a +1 racial bonus to attack rolls" -- and
#: collecting those would deal every character a row that does not exist.
_RACIAL_POWER = re.compile(r"\b(p\d+|x_m\d+a\d+)\b")
_MORE_SURGES = re.compile(r"one additional healing surge|healing surges by one", re.I)
_FEWER_SURGES = re.compile(r"one fewer healing surge", re.I)
_INITIATIVE = re.compile(r"\+(\d+)\s+racial bonus to initiative", re.I)
#: "Choose one", in the four spellings the blocks that mean it use. The
#: wording matters: it separates the race that prints two powers and
#: means both from the one that prints thirteen and means one.
_ONE_OF = ("choose one", "your choice of either",
           "select an option", "choose an option")

#: One `<ref> : <text>` entry in a race block, which is how the importer
#: lays a block's traits and racial powers out.
_RACE_ENTRY = re.compile(r"^\s*((?:rt:)?r\d+(?:-[ts]\d+)?|p\d+)\s*:\s*(.*)$")


def _racial_powers(spec: str, carded: list[str]) -> tuple[str, ...]:
    """The race's own racial powers, in the order the block offers them.

    Lifted out of the `RaceLine(...)` literal by #914 so that `one_of` can
    be derived from the same answer rather than from a second copy of this
    expression -- two readings of "which powers does this race print" that
    could drift apart is exactly the shape that made `one_of` wrong.

    The block's own order first, because that is the order the page offers
    them in, then anything the power table has that the prose did not name.
    """
    named = [
        ref
        for ln in spec.splitlines()
        if "power" in ln.lower()
        for ref in _RACIAL_POWER.findall(ln)
        if ref in carded
    ]
    return tuple(dict.fromkeys([*named, *carded]))


def _variant_powers(row: Mapping[str, Any], cards: Mapping[str, list[str]],
                    stock: RaceLine) -> tuple[str, ...]:
    """A variant's own racial powers, falling back to the race it varies.

    The same expression the `powers=` field uses, named so that the fork
    derivation beside it cannot read a different answer. See #914 for why
    two readings of this question is the shape that goes wrong.
    """
    return tuple(cards.get(row["ref"], ())) or stock.powers


def _fork_members(spec: str, powers: tuple[str, ...]) -> tuple[str, ...]:
    """The refs a race's printed fork offers a character, or `()` for none.

    **This replaced a boolean, and the boolean could not say what the fork
    was between.** `one_of` used to be `any(word in spec)`, which is enough
    while every alternative is a racial *power* -- `granted` then chose from
    `powers`. Three races print a fork whose other leg is a **trait**, so
    the candidate list held one option and 40 seeds gave 40 identical
    characters. #914, and #743's comment had named it first.

    Three rules, in order, and the ordering is what keeps the five working
    races byte-identical:

    1. **No choice phrase in the block, no fork.** This is what finally
       stops `r67` claiming one: it is a *variant*, it inherited the flag
       from its parent through `replace()`, and its own block prints no
       choice at all -- its entries are benefit swaps.
    2. **More than one racial power: the fork is those powers.** The five
       races that already worked, unchanged, which is #914's own prescription
       -- *"the flag becomes a list, and for five races that list is just
       `powers`"*. Load-bearing: `r44` prints three sub-option traits after
       its heading, so rule 3 would offer six options where the card offers
       three, and re-roll a race nobody asked to re-roll.
    3. **Otherwise: the entries printed after the heading, plus the
       powers.** The genuine mixed fork. The union matters because the
       heading's legs are not all declared rows -- `r6`'s second leg is an
       entry reading "you have the <power> power", which carries no row of
       its own, so the *power* is the playable half and has to come in from
       `powers`.

    Returns refs in printed order with duplicates dropped, so a seeded
    `choice` over it is stable.
    """
    low = spec.lower()
    if not any(word in low for word in _ONE_OF):
        return ()
    if len(powers) > 1:
        return powers
    after: list[str] = []
    seen_heading = False
    for line in spec.splitlines():
        found = _RACE_ENTRY.match(line)
        if found is None:
            continue
        ref, text = found.group(1), found.group(2).lower()
        if seen_heading:
            # **An entry that names its own ref is scaffolding, not an
            # option.** `rt:r6-t4`'s whole text is *"You have the rt:r6-t4
            # power"* -- it restates its sibling power rather than offering
            # anything, and the self-reference is an artefact of the name
            # scrub: the trait and the power share a printed name, so the
            # substitution matched the trait's own ref for both.
            #
            # Dropped here rather than filtered later, because `one_of` is
            # what a reader of the fork sees. `chargen.granted` already
            # discards it -- silently, on `m in REGISTRY` -- so a printed
            # three-way choice was *dealt* two-way while `one_of` reported
            # three. `lint._narrowed_forks` existed to report exactly that
            # gap and this closes it at the source.
            #
            # **Derived, not listed.** Exactly one row in the whole
            # `racial_trait` table has this shape today, and a hard-coded
            # ref would not catch the next one. Measured: of all 29 fork
            # options across 7 races, `rt:r6-t4` is the only entry whose
            # text mentions its own ref. #1084.
            if ref.lower() not in text:
                after.append(ref)
        elif any(word in text for word in _ONE_OF):
            # The heading itself is not one of its own options.
            seen_heading = True
    return tuple(dict.fromkeys([*after, *powers]))


def _races_from_the_book() -> dict[str, RaceLine]:
    """The playable races, read off the `race` table.

    Nine of the 55 rows carry no size and no ability scores: they are the
    **sub-race trait packages** -- "this benefit replaces that one" -- and
    not races anybody can be. A row with no size is skipped rather than
    dealt as a race with no numbers at all.
    """
    from combat_engine.db import game

    out: dict[str, RaceLine] = {}
    try:
        rows = list(game().execute("SELECT * FROM race ORDER BY id"))
        cards: dict[str, list[str]] = {}
        for card in game().execute(
            "SELECT ref, class FROM power "
            "WHERE kind = 'Racial' AND level = 0 ORDER BY ref"
        ):
            cards.setdefault(card["class"], []).append(card["ref"])
    except Exception:            # no database yet; a character is raceless
        return out

    for row in rows:
        if not row["size"]:
            continue
        spec = row["spec"] or ""
        named = [Ability(a) for a in json.loads(row["scores"] or "{}")]
        # Three scores is always "+2 A, +2 B **or** +2 C" and two is always
        # both -- checked across all 46 rows, and the JSON keeps the
        # printed order, so the first of three is the one that is not a
        # choice.
        fixed = tuple(named[:1] if len(named) == 3 else named)
        choices = tuple(named[1:] if len(named) == 3 else ())
        line = _SPEED_LINE.search(spec)
        printed = line.group(1) if line else ""
        found = re.match(r"\s*(\d+)", printed)
        vision = _VISION_LINE.search(spec)
        skills = _SKILL_LINE.search(spec)
        out[row["ref"]] = RaceLine(
            ref=row["ref"],
            size=Size(row["size"]),
            speed=int(found.group(1)) if found else 6,
            modes={m.lower(): int(n) for m, n in _MODE.findall(printed)},
            vision=(vision.group(1).strip() if vision else "").removesuffix(" vision"),
            fixed=fixed,
            choices=choices,
            skills=tuple(
                (name.lower(), int(value))
                for value, name in _SKILL.findall(skills.group(1) if skills else "")
            ),
            surges=sum(
                1 if _MORE_SURGES.search(ln) else -1
                for ln in spec.splitlines()
                if _MORE_SURGES.search(ln) or _FEWER_SURGES.search(ln)
            ),
            # Only the character's own. One sub-race grants the bonus to
            # *allies within 10 squares*, which is a different sentence
            # and belongs to a row rather than to the sheet.
            initiative=max(
                (
                    int(m.group(1))
                    for ln in spec.splitlines()
                    if "allies" not in ln.lower() and (m := _INITIATIVE.search(ln))
                ),
                default=0,
            ),
            powers=_racial_powers(spec, cards.get(row["ref"], [])),
            one_of=_fork_members(
                spec, _racial_powers(spec, cards.get(row["ref"], []))
            ),
        )

    # **The nine variants, inheriting the parent their own traits name.**
    # They carry no sheet numbers, so the loop above skipped them and none
    # could be named or dealt. All 21 of their traits print a "replaces"
    # clause naming a ref, which is what makes the parent derivable here
    # instead of needing a column: every one resolves to exactly one.
    #
    # Second pass rather than inline, because a variant needs its parent
    # already built and `ORDER BY id` is not a promise about that. #896.
    for row in rows:
        if row["size"] or row["ref"] in out:
            continue
        kin, swapped = _variant_of(row["ref"])
        stock = out.get(kin)
        if stock is None:
            continue
        out[row["ref"]] = replace(
            stock, ref=row["ref"], parent=kin, replaces=swapped,
            # **Its own racial powers, not the parent's.** The power table
            # keys on the race, so a variant that prints one has it; one
            # that prints none inherits nothing here on purpose -- the
            # clause that would hand it the parent's is a `replaces` entry
            # and belongs to the reader #813 writes.
            powers=tuple(cards.get(row["ref"], ())) or stock.powers,
            # **Its own fork, and the parent's only where the parent's
            # heading is what offers it.** `replace()` used to carry
            # `one_of` straight down as a flag, which made `r67` claim a
            # choice it does not print.
            #
            # The two variants of `r1` are the whole argument for not just
            # re-deriving, either. Neither prints a choice phrase -- the
            # heading is on the parent's block -- so a plain re-derivation
            # takes the fork off **both**, and `r68` really does have one:
            # it prints *two* racial powers, and two alternatives under an
            # inherited heading is a choice. `r67` prints one, which is a
            # replacement and not a fork.
            #
            # So: its own block first, then the parent's fork-ness over its
            # own powers, and only when there is more than one to choose
            # between. #914.
            one_of=_fork_members(row["spec"] or "", _variant_powers(
                row, cards, stock,
            )) or (
                _variant_powers(row, cards, stock)
                if stock.one_of and len(_variant_powers(row, cards, stock)) > 1
                else ()
            ),
        )
    return out


#: Which ref a `replaces` clause points at: a trait, a race, or a power.
_REPLACED = re.compile(
    r"replaces?\s+(?:the\s+)?(?:normal\s+)?[^.]*?\b((?:rt:)?r\d+(?:-t\d+)?|p\d+)\b",
    re.I,
)


def _variant_of(ref: str) -> tuple[str, tuple[str, ...]]:
    """The race this one varies, and every ref its traits say it replaces.

    Read off `racial_trait.spec`, because that is where the compendium puts
    it: *"This benefit replaces rt:r1-t1."* The parent is whichever `rN` the
    clauses name, and all nine variants name exactly one -- checked, which
    is the only reason this is a derivation rather than a guess.

    Returns `("", ())` for anything that names none, so a genuinely thin
    import stays skipped rather than being adopted by the first race it
    happens to mention.
    """
    from combat_engine.db import game

    swapped: list[str] = []
    try:
        rows = game().execute(
            "SELECT spec FROM racial_trait WHERE ref LIKE ? ORDER BY ref",
            (f"rt:{ref}-%",),
        )
    except Exception:            # no database yet
        return "", ()
    for row in rows:
        swapped += _REPLACED.findall(row["spec"] or "")
    kin = {
        m.group(1)
        for named in swapped
        if (m := re.match(r"(?:rt:)?(r\d+)$|(?:rt:)?(r\d+)-t\d+$", named))
        and (m := re.match(r"(?:rt:)?(r\d+)", named))
    }
    # **One parent or none.** Two would mean the derivation is reading
    # something it should not, and adopting the lower-numbered one would be
    # a guess dressed as a rule.
    return (next(iter(kin)) if len(kin) == 1 else ""), tuple(dict.fromkeys(swapped))


#: The 46 races a character can be, by ref.
RACES: dict[str, RaceLine] = _races_from_the_book()

#: Deal a race to a `Character` that names none.
#:
#: **On.** A race is +2 to two ability scores, a size, a speed and a
#: handful of traits, so dealing one moves every number on every sheet and
#: with them every roll in every fight. The six fixtures were re-recorded
#: in the commit that flipped this, on purpose and with nothing else in
#: it, because that divergence is indistinguishable from a real regression
#: and re-recording under it in a mixed commit would hide one.
DEAL_RACES = True

#: The one race whose printed trait grants a second race. #1029.
#:
#: Held as a ref rather than a name, like `HUMAN` above it and for the
#: same reason. `rt:r47-t1` is the trait and its text is quoted on
#: `Character.race2`; no other race in the 46 prints anything of the
#: shape, which is why this is a constant and not a column.
SECOND_RACE_FROM = "r47"

#: Deal every character a deity. `#454`, on Camille's option B.
#:
#: **A flag for the same reason `DEAL_RACES` is one**, and a much smaller
#: one: a deity is not a number on the sheet, so it changes no score and no
#: roll. What it changes is which **feats** a character may take -- 194 of
#: them carry a worship prerequisite -- so the feat pool moves and with it
#: the draw.
#:
#: The eight `replay` fixtures pin `feats` and `powers`, so a pool change
#: cannot reach them; that is checked rather than assumed in the commit
#: that turns this on.
#:
#: **Every class, not only the divine ones.** The book lets anyone worship,
#: and the feats that care already carry `{"source": "divine"}` beside the
#: worship clause -- so gating the deal on the class as well would be the
#: same test twice and would wrongly refuse a non-divine character the few
#: feats that ask for worship alone.
DEAL_DEITY = True

#: Score the build choices instead of drawing them uniformly. `choices.py`
#: holds the terms and the weights.
#:
#: A flag for the same reason `DEAL_RACES` is one: it changes what every dealt
#: character is, so all six `fixtures/` move and are re-recorded in a commit
#: with nothing else in it. That divergence is indistinguishable from a real
#: regression and re-recording under it in a mixed commit would hide one.
#: The six fixtures were re-recorded in the commit that flipped this, with
#: nothing else in it and with `--redraw`, for the reason `DEAL_RACES` gives
#: above: every dealt character changes, so every roll after the first changes
#: with it, and that divergence is indistinguishable from a real regression.
#: **Annotated `bool`, not left to infer `Literal[True]`.** Three instruments
#: write it -- `audit.py` at import time, `expect.py` from a flag, and
#: `drivers.py`'s own board helper -- and without the annotation every one of
#: those assignments is a type error. #721.
SCORED_CHOICES: bool = True

#: Deal the **build leg** instead of always taking the first one listed.
#:
#: `build_of(cls, "")` returns `options[0]`, and every dealer asked for that
#: -- so a dealt character took the first leg of its class, always. Measured
#: before this flag existed, over 26 classes x 8 seeds:
#:
#:     classes with more than one leg              26
#:     of those, where only ONE leg was ever dealt 26
#:     legs never dealt                            73
#:     declared rows gated on a leg                50
#:     of those, unreachable                       42   (84%)
#:
#: Six of the warlock's seven pacts were unreachable; every dealt warlock was
#: infernal. **40 of those 42 rows are written** -- only two still carry a
#: marker -- so this is not new content, it is content that existed and could
#: not be reached. `#1244` holds the measurement and `#235` the modelling.
#:
#: **Uniform, not scored.** No scorer for legs exists -- `SCORED_CHOICES`
#: above is about the choices made *within* a build, and `choices._build_of`
#: is a one-line call to the default. `deal_race`'s own argument applies
#: here unchanged: *"a player picks for flavour at least as often as for the
#: numbers, and a draw that always took the best pair would make every
#: fighter the same two races."*
#:
#: A flag for the reason `DEAL_RACES` is one -- it changes what a dealt
#: character **is** -- but **not** with the same blast radius, and I wrote
#: the opposite here before measuring it. `replay verify` is 8 of 8
#: identical across this change.
#:
#: The reason is worth knowing, because it also says what this flag does
#: *not* reach. Two party paths exist:
#:
#:     story.Party.of              deals the leg        <- this flag
#:     story.field_encounter's     Character(key, level, ...) with no
#:     no-party fallback           `build=`, so the resolver's first leg
#:
#: The fallback is what `fight.build` uses, and `replay` and `winrate`
#: both go through that -- so the fixtures are pinned to the first leg and
#: stay pinned, which is what a fixture is for. `fight.py`'s own CLI uses
#: `Party.of`, so playing a fight does vary the leg.
#:
#: **The cost of that split is that `winrate` measures one leg per class.**
#: Balance is read off `fight.build`, so the 73 legs this flag opened are
#: not in that number. Changing the fallback would move all eight fixtures
#: and belongs in its own commit, with `--redraw`, for the reason
#: `SCORED_CHOICES` gives.
DEAL_BUILDS: bool = True

#: Whether the draw also consults `ratings.py` -- the community guides' colour
#: ratings for 5,240 options. Separate from `SCORED_CHOICES` so the two can be
#: measured apart: `scripts/winrate.py --draw scored` against `--draw rated` is
#: the comparison, and a fixture movement can be attributed to one of them
#: rather than to both at once.
#:
#: **On**, and it was off because turning it on cost win rate. That is no
#: longer true, and both reasons it was true have been fixed:
#:
#: * #234 was the dominant confound -- `loadout` dealt one level's worth of
#:   powers, so a quarter of the party swung a 1d4 whip and no feat term could
#:   be read over it. Characters hold full hands now and the weapon choice is
#:   scored.
#: * #256 was costing this seven points on its own. 1,529 (ref, class) pairs
#:   were contested -- one class, two answers -- and the table kept the better
#:   of the two, which is wrong for both builds. `rating()` declines for those
#:   now, and the rated draw went +3% to +10% against the chassis purely from
#:   withdrawing them.
#:
#: Re-measured at 100 seeds, level 5, which is the power #257's own comment
#: says this needs (about 80 for the effect it was arguing about):
#:
#:     draw      win   rounds  party hit%  moved-away provocations
#:     chassis   81%     7.0      61%            177
#:     scored    89%     6.0      60%            122
#:     rated     93%     6.0      63%            159
#:
#: So three of #257's findings invert: the rated draw is **best** rather than
#: worst, it is a round **shorter** rather than longer, and the scored draw
#: walks away from adjacent enemies **least** rather than most. Only "hit rate
#: does not move" survives, which it does -- 61/60/63.
#:
#: Still separate from `SCORED_CHOICES` so the two can be measured apart, which
#: is how the seven points above were attributed to one of them.
USE_RATINGS = True

#: The rated average on the community six-colour scale. An item a guide put
#: below this is refused outright; see `_pick_item`.
BLACK = 3.0


def deal_race(rng: Random, cls: str = "", build: Build | None = None,
              *, other_than: str = "") -> str:
    """A race, drawn like a hand of powers is.

    **Weighted towards the ones whose scores suit the class, and not decided
    by them.** This used to be uniform over all 46, and its own docstring gave
    the reason to keep some of that: a player picks for flavour at least as
    often as for the numbers, and a draw that always took the best pair would
    make every fighter the same two races. So the score ranks and `sample`
    draws -- a Strength race is likelier for a fighter and never certain.

    `cls` is optional so the old one-argument call still answers; without it
    there is no build to score against and the draw stays uniform.

    `other_than` drops one ref from the pool **before** the draw, for
    `rt:r47-t1`'s printed *"Select a race other than r47"*. See the note
    at the sample below for why it is not a filter applied afterwards.
    """
    # **Variants are selectable and not dealt**, which is what keeps this
    # change from moving every sheet in the game. A variant's own 21 traits
    # are undeclared (`#813`), so a dealt one would wear its **parent's**
    # traits under another name -- wrong in a way no instrument would
    # report, because the row that should have replaced them does not
    # exist to be missing.
    #
    # Right on the merits rather than convenient: a race whose every trait
    # is unwritten is not a race a dealer should hand out. When `#813`
    # writes them and something reads `RaceLine.replaces`, dropping this
    # filter is a one-line change -- and it belongs in a commit with
    # nothing else in it, for the reason `DEAL_RACES` records below: it
    # moves every number on every sheet and all seven fixtures with them.
    pool = sorted(r for r, line in RACES.items()
                  if not line.parent and r != other_than)
    if not pool:
        return ""
    if not SCORED_CHOICES or not cls:
        return rng.choice(pool)
    from .choices import race_options, sample

    # **`other_than` is excluded before the draw, never after it.** #1029.
    # `rt:r47-t1` prints *"Select a race other than r47"*, and a result
    # discarded afterwards would spend a different number of values from
    # the stream depending on what came out -- so the same seed would
    # deal a different character depending on a race it did not take.
    # The same hazard `_trained_skills` records about drawing for a pinned
    # set and throwing the answer away.
    offered = [o for o in race_options(cls, build=build)
               if getattr(o, "ref", "") != other_than]
    drawn = sample(offered, rng)
    return drawn.ref if drawn is not None else rng.choice(pool)


@cache
def declared_chassis(cls: str) -> tuple[str, ...]:
    """Every chassis of this class a character can actually be dealt.

    **A row `ladder_row` would deal at level 1** is the test, and it is
    the same function `loadout` selects with -- so the two cannot drift
    into disagreeing about what a chassis *is*. It still excludes the
    chassis nobody has written, which is the hazard `chassis_of` records
    at length: choosing `knight` gave a fighter no class features at all,
    because it has no declared row.

    **It used to be `p.level == 0`, and `cf:wizard-mage` was the chassis
    that cost.** The mage has 24 written, unmarked rows and not one at
    level 0 -- its school choice is printed at level 1, with later
    benefits at 4, 5, 8 and 10 -- so it was offered to nobody and a
    level-10 mage came out with **0** class features.

    **Widening the test to "any declared row" was my first answer and was
    wrong**, and the reason is why `ladder_row`'s third clause exists: an
    ungated sub-option row dealt by level alone gives a level-1 mage all
    **six** Apprentice schools at once, which is `#851`'s "one character
    being two sub-classes" one level down and worse than dealing none. The
    six carry `on_leg` headers now, one per school, so the leg picks one --
    the same arrangement the sorcerer's elemental specialties use. The
    mage's *later* groups are dependent choices (*"a school different from
    the one you chose"*) that no leg can express; they stay ungated and
    undealt, and `#1247` holds that half.

    A chassis whose ladder starts **above** level 1 would need a level
    argument here. None does -- measured over every declared `cf:` row --
    so this asks at level 1 and says so rather than taking one.

    **And `ORIGINAL` is among them when the class has one**, which is
    `#1191`'s ruling. The test for that is *not* "has a blank level-0 row",
    and the rogue is why: `cf:rogue-tactic-club` and `cf:rogue-tactic-stealth`
    are hand-coined rows for features the class page describes and the
    `class_feature` table does not list, so they are blank for
    `_chassis_map`'s *absent* reason rather than because they are a chassis.
    Offering the rogue an `original` would have dealt a character **two**
    class features where the scoundrel gets nine.

    The test is **`superseded_for`'s printed coverage**: a blank ladder is a
    chassis exactly when some named chassis of the class covers the `ord`s
    it occupies, because that coverage is the page saying the two are
    alternatives. Measured:

        sorcerer   3 blank rows, elementalist covers all 3   -> ORIGINAL
        rogue      2 blank rows, scoundrel covers 0          -> no
        warlock   12 blank rows, no named chassis declared   -> ORIGINAL

    The warlock is the third case and the one `#1191` was filed for: with no
    named chassis declared, the blank ladder is the only ladder, so naming
    it costs nothing today and the name is already there when `#642`'s
    Essentials wave lands. Without it, declaring Hexblade makes
    `superseded_for` drop all **12** of the plain warlock's rows and the
    plain warlock stops existing -- silently, which is what Camille asked
    not to happen on `#730`:

        > *"But the other warlocks getting weaker? This shouldn't affect
        > non hexblade warlocks"*

    So: 6 classes have a written chassis and **three** have a dealable
    choice -- cleric (templar, warpriest), sorcerer (elementalist,
    original) and wizard (arcanist, mage, sha-ir).
    """
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    belongs = _chassis_map()
    mine = [(ref, belongs.get(ref, ""))
            for ref, power in REGISTRY.items()
            if ref.startswith("cf:") and power.cls == class_word(cls)
            and ladder_row(power, 1)]
    named = tuple(sorted({c for _, c in mine if c}))
    blank = [ref for ref, c in mine if not c]
    if blank and (not named
                  or any(set(blank) & superseded_for(cls, c) for c in named)):
        return tuple(sorted((*named, ORIGINAL)))
    return named


def deal_chassis(rng: Random, cls: str = "") -> str:
    """Which written chassis this character is, drawn rather than defaulted.

    `chassis_of(cls, "")` answers `_declared_chassis()[cls]` -- the first
    in sorted order -- so every dealt cleric was a templar and every dealt
    wizard an arcanist. Measured: **36 declared rows** sat on a chassis
    that was never dealt, 9 on `warpriest`, 24 on `mage` and 3 on
    `sha-ir`.

    Uniform over `declared_chassis`, for `deal_build`'s reason: a chassis
    is a way of being the class rather than a better or worse one, and
    nothing scores one. A class with one written chassis, or none, answers
    what the resolver would -- so this is safe for any class and only moves
    the two that had a choice nobody was making.

    **`chassis_of` is left alone**, exactly as `build_of` was: it is the
    resolver `audit.board` and `loadout` need to answer the same way every
    time for a given ref. See `DEAL_BUILDS`.
    """
    options = declared_chassis(cls)
    if not options:
        return chassis_of(cls)
    # **One option answers that option, not the resolver.** `chassis_of`
    # resolves a blank to the first *named* chassis, so for a class whose
    # only option is `ORIGINAL` -- the warlock, and 12 others -- it would
    # hand back `""` and `Sheet.chassis` would record nothing. That is the
    # ambiguity `#1191`'s ruling removes, so the dealer must not reintroduce
    # it. For a class with one named chassis the two agree, which is 23 of
    # the 25.
    if len(options) == 1:
        return options[0]
    return rng.choice(list(options))


#: How much likelier a leg is when the race's ability bonuses line up with
#: it. Camille's ruling on `#1244`, 2026-11-11, verbatim:
#:
#:   > *"For class/race combos, prefer legs which align with the selected
#:   > race's ability score bonuses. 3x chance if both ability scores
#:   > match. 2x chance if the primary only. 1.5x if secondary only. 1x if
#:   > neither."*
#:
#: `1x if neither` is as load-bearing as the `3x`: every leg keeps a
#: non-zero weight, so this cannot make one unreachable and `#1244`'s
#: reachability result survives it.
LEG_WEIGHTS = {(True, True): 3.0, (True, False): 2.0,
               (False, True): 1.5, (False, False): 1.0}


def deal_build(rng: Random, cls: str = "", chassis: str = "",
               race: str = "") -> Build:
    """One leg of a class's fork, drawn rather than defaulted.

    `build_of(cls, "")` answers `options[0]`, which is the right answer for
    a **resolver** -- `audit.board` and `_build_for` both want a fixed leg
    for a fixed ref -- and the wrong one for a **dealer**. Every dealer
    asked the resolver, so every dealt character took the first leg and 73
    legs were never dealt at all. See `DEAL_BUILDS`.

    Uniform over the class's own list, for `deal_race`'s stated reason: a
    leg is a way of playing the class rather than a better or worse set of
    numbers, and nothing scores one. A class with one leg, or none, answers
    exactly what the resolver would -- so this is safe to call for any
    class and only changes the ones that had a choice nobody was making.

    Its own `Random`, keyed like every other deal in `Party.of`
    (`f"{seed}:{key}:build"`), so drawing a leg moves neither the hand nor
    the feats nor the fight's dice.

    **`chassis` narrows the pool, and without it the two draws contradict
    each other.** `BUILDS` is keyed by **class**, so a class whose chassis
    print different forks had one pool for both and the leg draw could not
    see which chassis the chassis draw had just made. Camille, 2026-11-11,
    on the sorcerer:

      > *"Elementalist Sorcerer Chassis: this should be separate from teh
      > base sorcerer. Air, water, earth, fire"*

    Measured after `#1191` made the original sorcerer dealable: of 8 legs,
    4 are the elementalist's specialties and 4 are the base sorcerer's
    printed sources, and either chassis could draw any of them. A base
    sorcerer on `fire` got **no** source and an elementalist on `cosmic`
    got **no** specialty -- a character missing the one feature its fork
    exists to choose.

    See `legs_for` for how a leg is attributed and what falls open.

    **`race` weights the draw rather than filtering it**, which is
    Camille's ruling -- see `LEG_WEIGHTS` for the quote and the numbers.

    **What counts as a match is the race's *possible* bonuses, not the one
    it ended up with**, and that is her call too. Asked whether "the
    race's ability score bonuses" meant the bonus a race grants outright
    or that plus the one it lets you choose, 2026-11-11:

      > *"the free plus one of the two. I guess this requires choose race,
      > then choose class, then choose race bonuses."*

    It matters: measured over the 46 dealable races, only **8** grant two
    bonuses outright while **37** grant one plus a choice of two. On the
    narrow reading **53 of 106 legs** could never reach the 3x tier from
    any race; on hers, all 106 can.

    Reading what the race *can* give also removes the circularity her
    ordering sentence is about: the weight never consults the bonus
    actually chosen, so nothing has to be decided twice.
    `RaceLine.taken(build)` then puts the choosable bonus on whichever of
    the leg's two abilities is among the options -- her third step, which
    was already implemented.

    **A pool of exactly one leg answers that leg, and this used to answer
    the wrong one.** The short-circuit was `len(options) <= 1 ->
    build_of(cls, "")`, which is `options[0]` of the **whole class pool**
    and not of the narrowed one -- so a chassis whose pool narrows to a
    single leg was dealt the base class's first leg instead. Silent until
    `#642`'s berserker, the first chassis with one leg of its own: a dealt
    berserker took `rageblood`, every one of its eight rows refused itself
    on `on_leg("berserker")`, and the character came out with **one**
    class feature. The sorcerer could not show it -- both its pools hold
    four.

    The no-leg case still defers to the resolver, which is what it is
    for: `build_of` invents a `Build` for a class `BUILDS` has no entry
    for, and there is nothing here to choose.
    """
    options = legs_for(cls, chassis)
    if len(options) == 1:
        return options[0]
    if not options:
        return build_of(cls, "")
    if not race:
        return rng.choice(list(options))
    line = RACES.get(race)
    if line is None:
        return rng.choice(list(options))
    have = set(line.fixed) | set(line.choices)
    weights = [LEG_WEIGHTS[(b.primary in have, b.secondary in have)]
               for b in options]
    return rng.choices(list(options), weights=weights, k=1)[0]


@cache
def legs_for(cls: str, chassis: str = "") -> tuple[Build, ...]:
    """The legs a character on this chassis can be dealt.

    A leg belongs to a chassis when a declared row **of that chassis**
    names it in its header, which `leg_named_by` reads off `on_leg`. Where
    no row attributes a leg it stays in every pool -- **fail open**, for
    the same reason `impact.selection` does: a leg wrongly excluded is a
    character that cannot be built, where a leg wrongly included is the
    behaviour this function was added to improve on.

    Measured over all 26 classes: **100 legs, 42 attributed by a header,
    58 open.** Only **one** class narrows, and it narrows to exactly the
    two lists Camille gave:

        sorcerer  elementalist   air, earth, fire, water
        sorcerer  original       cosmic, dragon, storm, wild

    Every other class returns its whole pool, because `declared_chassis`
    gives it one option or none and the question does not arise. No pool
    is empty for any class on any of its chassis -- asserted, because an
    empty pool is a character that cannot be built and is the one way
    this can do real harm.

    **Two legs fall open where they should not, and the reason is worth
    naming because it bounds what this can ever see.** `wild` and `dragon`
    are the base sorcerer's other two sources and they are dispatched in a
    **body** -- `powers/sorcerer/souls.py` holds one row, `cf:sorcerer-f0`,
    that implements both and branches on `c.build("dragon")` /
    `c.build("wild")` inside itself. One row cannot carry two `on_leg`
    headers, so there is nothing for this to read. `LEG_CHASSIS` names
    them.

    **This used to claim `drivers.deal_legs` asserts that table covers
    exactly the legs inference misses, and it does not** -- that rule
    asserts the pools are disjoint, non-empty, and that no chassis is
    dealt a leg outside its own, which is a different and weaker thing.
    The table *cannot* cover every missed leg, and the druid is why: a leg
    shared by two chassis has no entry here, because this maps a leg to
    **one** chassis and the only way to say "both" is to leave it out and
    let the fail-open rule above carry it. `drivers.protector_circle`
    pins the druid's four, and `drivers.berserker_fury` the barbarian's
    five, by naming the pools outright.
    """
    pool = BUILDS.get(class_word(cls)) or ()
    if not pool or len(declared_chassis(cls)) <= 1:
        return tuple(pool)
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    belongs = _chassis_map()
    owner = dict(LEG_CHASSIS.get(class_word(cls), {}))
    for ref, power in REGISTRY.items():
        if not ref.startswith("cf:") or power.cls != class_word(cls):
            continue
        leg = leg_named_by(power)
        if not leg:
            continue
        mine_chassis = belongs.get(ref, "")
        # **A chassis-less row falls back to `ORIGINAL` only where
        # `ORIGINAL` is on offer**, and the rogue is why. `cf:rogue-tactic-
        # club` names the `cutthroat` leg and carries no chassis segment,
        # so the old `or ORIGINAL` handed that leg to a chassis the rogue
        # is **not** offered -- `declared_chassis("rogue")` is
        # `('scoundrel', 'thief')`, because its blank rows are hand-coined
        # extras rather than a ladder (`drivers.deal_legs` asserts exactly
        # that). The leg then belonged to nobody and `cutthroat` became
        # unreachable: 5 legs, 4 in each pool.
        #
        # Skipping instead leaves it **open**, which is the same answer the
        # druid's two shared circles get and for the same reason -- a leg
        # no declared chassis claims is a leg every chassis may draw. Found
        # by `deal_legs` the moment the thief landed, which is the rule
        # working: before the thief the rogue had one chassis and this loop
        # never ran.
        if not mine_chassis and ORIGINAL not in declared_chassis(cls):
            continue
        owner.setdefault(leg, mine_chassis or ORIGINAL)
    want = chassis or chassis_of(cls)
    mine = tuple(b for b in pool if owner.get(b.name, want) == want)
    # **A chassis every leg is attributed away from keeps the whole pool**,
    # which is the fail-open discipline above taken to its last case. The
    # sha'ir is it: once `control` and `war` went to the arcanist and the
    # six schools to the mage, nothing was left and `legs_for` returned
    # **nothing** -- a character nobody can be dealt, which is the one way
    # a narrowing selector does real harm and is what `drivers.deal_legs`
    # asserts against. A chassis with no fork of its own has no leg to be
    # wrong about: the leg still steers which powers are drawn, so any of
    # them is as good as another.
    return mine or tuple(pool)


#: Legs whose chassis `legs_for` cannot infer, because the row that
#: implements them gates in its **body** rather than in an `on_leg` header.
#: One row serving two legs cannot carry two headers, so this is a real
#: blind spot rather than a missing gate.
#:
#: Keyed `class -> leg -> chassis`, and `ORIGINAL` is spelled out rather
#: than left blank for `#1191`'s reason.
LEG_CHASSIS: dict[str, dict[str, str]] = {
    # `cf:sorcerer-f0` is one row implementing two of the four printed
    # sources, branching on `c.build("dragon")` / `c.build("wild")` in
    # `powers/sorcerer/souls.py`. The other two sources -- `cosmic` and
    # `storm` -- are rows of their own and carry `on_leg` headers, so
    # inference finds those without help.
    "sorcerer": {"dragon": ORIGINAL, "wild": ORIGINAL},
    # `cf:wizard-arcanist-f0` is one row implementing both of the
    # arcanist's printed build options, branching on `c.build("war")` and
    # `c.build("control")` in `content/features/controllers.py`. The
    # mage's six schools are rows of their own with `on_leg` headers, so
    # inference finds those without help -- and without this entry a mage
    # could be dealt the arcanist's legs and get no school.
    "wizard": {"control": "arcanist", "war": "arcanist"},
    # The berserker's own leg carries `on_leg` headers, so inference finds
    # it. These four are the base class's and are dispatched in the
    # **bodies** of `cf:barbarian-f1` and the rows beside it -- `c.build(
    # "rageblood")` and friends -- so there is no header to read and
    # without this entry a berserker could be dealt `thaneborn` and get
    # neither fork's feature.
    "barbarian": {"rageblood": ORIGINAL, "thaneborn": ORIGINAL,
                  "thunderborn": ORIGINAL, "whirling": ORIGINAL},
    # The druid's four aspects are all dispatched in one body,
    # `cf:druid-f1`, so inference sees none of them. Only the two the
    # protector does **not** have are named: its two circles are the other
    # two aspects, and a leg left out of this table falls open to every
    # chassis, which is the one way "belongs to both" can be said here.
    "druid": {"f1s2": ORIGINAL, "f1s3": ORIGINAL},
}


@dataclass
class Character:
    cls: str
    level: int = 1
    powers: list[str] = field(default_factory=list)
    team: Team = Team.PC
    #: Which leg of the fork. Empty takes the first the class lists.
    build: str = ""
    #: The feats taken, by ref. Empty means "deal me some", the same as
    #: `powers`. A feat is an ordinary row, so it lands in `Powers.known`
    #: with everything else and arms itself at the top of the fight.
    feats: list[str] = field(default_factory=list)
    #: The race, by ref -- `r3`. Empty means raceless, which is what every
    #: character was before `RACES` existed and is still the default.
    #:
    #: Naming one is now the whole of it: `spawn` reads its size, speed,
    #: movement modes, ability scores, skill bonuses and healing surges off
    #: `RaceLine`, puts its trait rows and its racial power in
    #: `Powers.known`, and carries `race:<ref>` on `Build.choices` the way
    #: it carries the warlock's element. `meets` answers a race
    #: prerequisite off this field, which is 690 of the heroic feats.
    #:
    #: **A character that names none is dealt one**, because `DEAL_RACES`
    #: is on -- see `spawn`, which `replace`s this field before anything
    #: below reads it. This comment said the opposite ("why one is not
    #: dealt to a character that names none"), which is what the flag meant
    #: while it was off, and it cost a real confusion: a `drivers.py` rule
    #: used `race=""` as its raceless control and the control had a race.
    #: #688.
    race: str = ""
    #: **A second race, counted for prerequisites only.** #1029.
    #:
    #: One printed trait asks for this and no other does. `rt:r47-t1`:
    #:
    #:     "Select a race other than r47. You are also considered a member
    #:      of that race for the purpose of meeting prerequisites, such as
    #:      feat or paragon path prerequisites."
    #:
    #: Camille, asked directly: *"This is a special case for revenants.
    #: Read the revenant race. I think it should make sense then."* It
    #: does -- the printed clause is **scoped to prerequisites** and to
    #: nothing else, so this is one scalar read by `meets` and not a
    #: second `RaceLine`.
    #:
    #: **Deliberately NOT read by `spawn`.** A second race does not bring
    #: its size, its speed, its scores, its skill bonuses, its surges, its
    #: trait rows or its racial power -- the trait grants none of those,
    #: and `f3568` exists precisely because the **power** needs a separate
    #: feat to come across. Widening this to the rest of `RaceLine` would
    #: hand every revenant a second race's whole chassis, which is the
    #: drawable-and-inert fault pointed the other way: a field doing more
    #: than its card says.
    #:
    #: Empty for every character but a revenant, and empty is what every
    #: reader already answers for.
    race2: str = ""
    #: The magic items this character arrives wearing, as `Magic` records.
    #: Empty means "deal me a kit", the same as `powers` and `feats` above
    #: and read at the same place in `spawn`.
    #:
    #: **A record and not a request, which is why it holds `Magic` and not
    #: refs.** `treasure` settles four things per item -- the slot, the
    #: enhancement, the critical dice and *which power rows the item grants*
    #: -- and `magic_for(ref, plus=...)` re-derives only the first three.
    #: Measured over 4 classes x 3 levels: a refs-only pin brings every item
    #: back with `powers=()` and an implement back as a `weapon`, so the
    #: character keeps the enhancement bonus and silently loses every item
    #: power. That is the version of this fix that looks right and removes
    #: the thing it was built for. #1101.
    gear: tuple[Magic, ...] = ()
    #: One-use items on this character's person, by ref -- the entry, not
    #: the block. Empty deals two, which is Camille's ruling on `#1233`.
    #:
    #: **Refs and not `Magic`, which is the opposite of `gear` above and
    #: for the reason that docstring gives.** `treasure` settles four
    #: things per worn item and `magic_for` re-derives only three, so a
    #: refs-only pin silently loses an item's powers. A consumable has
    #: none of those four: no slot, no enhancement, no critical dice, and
    #: its power rows come from `item_block` by ref. There is nothing a
    #: `Magic` record would carry that the ref does not, so a ref is the
    #: whole of it.
    #:
    #: **A pin and not only a request**, which is what `#1101` is about
    #: one field over. Dealt per fight off `world.rng.seed` a party walks
    #: into every encounter with different potions -- and worse than for
    #: worn items, because a drunk one would come back. `story.Party.of`
    #: deals them once onto `Sheet.carried` and `harvest` writes back what
    #: survived, so a spent potion stays spent for the rest of the day.
    carried: tuple[str, ...] = ()
    #: What this character is trained in. Empty deals it, which is what
    #: every character got before this and still gets. #793.
    #:
    #: **The whole trained set, not the pool picks**, which is the same
    #: shape `gear` above takes and for the same reason: a pin has to
    #: reproduce what the deal produced, and a class's granted skills, a
    #: feat's training and a racial trait's all arrive through the same
    #: `_trained_skills` call. Pinning only the choices would need the
    #: stream re-walked to recover the rest, and recovering it means
    #: re-dealing it.
    #:
    #: The *question* layer composes this -- ask for `skill_choices` picks,
    #: add what the class and race grant, pin the union. That is the step-4
    #: order the book prints and the reason `#793` calls skills the piece
    #: that unblocks the others.
    #:
    #: **And it is a bug fix, not only a field.** `_trained_skills` is
    #: called from `spawn`, keyed on `world.rng.seed` -- the **fight's**
    #: seed -- so a campaign character re-rolled its training every
    #: encounter. Measured on four fully-pinned characters across four
    #: fight seeds: **4 of 4 differed**, with only the granted skills
    #: stable. Exactly `#1101`'s kit bug one field over, and `Party.of`
    #: now pins this the way it pins the kit.
    skills: tuple[str, ...] = ()
    #: Which deity this character worships, as the deity's **ref**. `#454`.
    #:
    #: Camille's ruling was option B -- the mechanical half lands and the
    #: flavour stays for campaign data:
    #:
    #:   > *"B is fine. I looked at the deities though and I think the most
    #:   > mechanical portion is their domains."*
    #:
    #: A **ref and not a name**, which is what makes her next sentence
    #: cheap: *"eventually [I] want some kind of mapping from domain to
    #: [feat] prereq instead of them having deity specific."* A ref reaches
    #: `deity.domains`, so the domain test is a lookup -- and it is needed
    #: **now**, because 34 of the 90 printed prerequisites already name a
    #: domain instead of a god.
    #:
    #: Empty means "worships nobody", which is the honest default: 54 of
    #: the clauses name a specific god and a character with none meets none
    #: of them.
    worships: str = ''
    #: The background this character was dealt, as a ref. `#1078`.
    #:
    #: A ref because the printed name is campaign flavour and the
    #: mechanical half is the **associated skills**, which `background`
    #: already carries as a JSON column -- so a ref reaches the benefit by
    #: lookup, exactly as `worships` reaches `deity.domains`.
    #:
    #: Empty means none was dealt, which is what every pinned character
    #: and every monster has.
    background: str = ''
    #: Which **feature chassis** this character has, as the ref spells it --
    #: `arcanist`, `templar`, `warpriest`. Empty takes the class's first,
    #: which is `chassis_of`'s business and is the only chassis for 23 of
    #: the 25 classes.
    #:
    #: **A different question from `build` above, and conflating them cost a
    #: wrong issue.** A build is the ability-score leg a class's own page
    #: prints -- `two-blade`, `archer` -- and it decides which powers get
    #: drawn. A chassis is a whole second feature ladder for the same class,
    #: which is what the Essentials line added. `class_feature.build` is
    #: where the database keeps it, and the two namespaces share words
    #: without sharing meaning: a ranger can take the `hunter` *build* and
    #: the `hunter` *chassis* is a different thing it has never had.
    #:
    #: Needed because `loadout` deals every level-0 row of a class to every
    #: character of it, so a class with two declared chassis deals both at
    #: once -- one character being two sub-classes. #851, and #319 is the
    #: same fault at six rows. `legs.chassis_clash` is the gate.
    chassis: str = ""

    @property
    def chosen(self) -> Build:
        return build_of(self.cls, self.build)

    @property
    def choices(self) -> set[str]:
        """What a power's `c.build(...)` rider asks about.

        The element goes in beside the name rather than in a component of
        its own: it is part of the same single choice, and `c.element()`
        reads it back out.
        """
        leg = self.chosen
        out = {leg.name} - {""}
        # **The ability the class attacks with**, for a row whose printed
        # line is "Primary ability vs. AC" rather than a named one. A theme
        # does not know which class took it, so `dsl.Pick.PRIMARY` reads
        # this back out -- the same arrangement as the element, and for the
        # same reason: the choice belongs to the build, and a header cannot
        # know the holder.
        out.add(f"primary:{leg.primary.value}")
        if leg.element is not None:
            out.add(f"element:{leg.element.value}")
        if leg.companion:
            out.add(f"beast:{leg.companion}")
        if self.race:
            out.add(f"race:{self.race}")
        # **The second race, under its own key.** #1029. `race2:<ref>`
        # rather than a second `race:<ref>`, because a reader asking "is
        # this character an r3" and a reader asking "which race did the
        # revenant trait pick" are different questions -- and folding them
        # would make `Cast.chosen_option`-style reads answer the first
        # with the second. `chargen.meets` is what unites them, and only
        # for a prerequisite.
        #
        # Carried at all because `f3568` has to read it from the board:
        # *"You gain the racial power of the race you chose with your
        # rt:r47-t1 racial feature"*. Written here rather than left on
        # `Character` alone, since a `Character` does not outlive the
        # deal and a `Build` does.
        if self.race2:
            out.add(f"race2:{self.race2}")
        return out

    @property
    def line(self) -> ClassLine:
        return CLASSES[class_word(self.cls)]

    @property
    def ref(self) -> str:
        return f"c:{self.cls}"


#: **The level at which each power is gained, because a character keeps every
#: one it has ever gained.** This replaced a single table of level-1 slot counts
#: used with a `p.level == level` filter, which kept one year's worth of powers
#: and threw away the rest -- including the at-wills, gained at first level and
#: swung every round for the whole of a career. Level 10 prints no attack rows
#: for any class, so a level-10 character was dealt nothing to attack with at
#: all. See #244.
#:
#: A repeated level means two powers are chosen there: two at-wills at first.
#: Heroic tier only, which is as far as the tree goes.
ATTACK_GAINS: dict[Usage, tuple[int, ...]] = {
    Usage.AT_WILL: (1, 1),
    Usage.ENCOUNTER: (1, 3, 7),
    Usage.DAILY: (1, 5, 9),
}

#: Extra power gains a **class feature** prints, beyond the table above.
#:
#: `cf:sorcerer-elementalist-f1` ends *"you gain an extra at-will attack
#: power of your choice at 9th level and again at 19th"*, which is a gain
#: and not a pick from a named list -- so it is neither `BUILD_OPTIONS`
#: nor anything a body can do. The row carried
#: `dropped=("chargen.power_choice()",)` and its note said so: *"a pick
#: made when the character is built, and no body can make it."*
#:
#: Keyed by the **feature's ref**, read against the features already in
#: the hand, so a character gets the extra gain exactly when it has the
#: row -- an elementalist and nobody else. 19th is past where the tree
#: goes; `ATTACK_GAINS` above says "heroic tier only" for the same reason
#: and this follows it.
#:
#: **Three numbers, not two, and two was a silent no-op.** The entry says
#: *(usage, the level the gain happens at, the level of the pool it comes
#: from)*. Written as `(AT_WILL, 9)` -- reading the second as both -- it
#: dealt **nothing**: `deal` filters `p.level == at`, and no at-will
#: attack power is printed at 9th level in this corpus. An extra at-will
#: comes from the **1st-level** list, which is what the card means by *"of
#: your choice"*. Measured by A/B-ing the entry: 28 refs either way, and
#: the difference an empty set. #1112.
EXTRA_GAINS: dict[str, tuple[tuple[Usage, int, int], ...]] = {
    "cf:sorcerer-elementalist-f1": ((Usage.AT_WILL, 9, 1),),
}

#: Utility powers are gained on their own levels and are not attack powers, so
#: they are drawn without regard to usage -- a utility may be at-will,
#: encounter or daily, and the level is what says it is a utility. These were
#: dealt to nobody before, for the same reason the attack rows above were lost.
UTILITY_GAINS = (2, 6, 10)


def second_card(ref: str) -> str:
    """The row this one is printed beside, or "" if it is not a second card.

    Three hundred and seventy-five compendium entries print two stat blocks
    under one id, and the importer mints the second a ref of its own with a
    letter on the end -- `p5106b` -- because the parent's columns are wrong
    for it. Those are not separate choices: the card comes whole, so the
    second block rides along with the first rather than competing with it
    for a slot. Dealt from the pool instead, a monk could be handed two
    movement techniques and nothing to attack with.
    """
    from combat_engine.engine.dsl import REGISTRY

    return ref[:-1] if ref[-1:].isalpha() and ref[:-1] in REGISTRY else ""


def loadout(
    cls: str, level: int = 1, build: Build | None = None, rng: Random | None = None,
    who_chassis: str = "", trained: Iterable[str] = (),
) -> list[str]:
    """What one character knows, drawn from the leg of the fork it took.

    Worked out from the registry rather than listed. A hand-written list of
    ids goes stale the moment a row lands -- and did, twice, in two files
    that had drifted apart: the party the web server dealt out had no class
    features at all, so its rogue had no extra damage and its fighter could
    not mark.

    Powers are filtered to the ones that attack with **this build's primary
    ability**, which is what taking one leg and staying on it means. A row
    with no attack line at all -- a heal, a buff, a zone -- belongs to any
    build and is always in the pool. If a leg turns out to be too thin to
    fill a slot, the rest of the class makes up the difference rather than
    the character going short.

    `trained` is the skills this character is trained in, and it widens the
    **utility** pool with the skill powers those skills open. Empty is the
    honest default for a caller that has not settled training yet: it deals
    a class-only hand, which is what every caller got before `#1162`.
    """
    # Imported for the side effect: this is what registers the rows.
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    pick = rng or Random(0)
    build = build or build_of(cls)
    mine = [p for p in REGISTRY.values() if p.cls == cls]
    # **Skill powers, whose `cls` is a skill rather than a class.** `#999`'s
    # import decision and the only thing that makes one identifiable, so it
    # is also what selects them here. A character holds none unless it is
    # trained in the skill, which is the printed gate and the first of the
    # four clauses on PHB3 p164.
    opened = {s.lower() for s in trained}
    by_skill = [p for p in REGISTRY.values() if p.cls.lower() in opened] if opened else []
    riders: dict[str, list[str]] = {}
    for p in list(mine):
        printed_beside = second_card(p.ref)
        if printed_beside:
            riders.setdefault(printed_beside, []).append(p.ref)
            mine.remove(p)

    # **A subclass's rows are not every character's.** #319. A level-0 row carries
    # the *base* class in `cls`, so `loadout` dealt six bladespells to every wizard
    # -- rows whose printed trigger is "you hit with a one-handed melee basic attack
    # while your other hand holds no weapon or shield", which is one subclass's whole
    # premise and something no build here can do. They were never usable, they padded
    # the pool so the rows a wizard *can* use were less likely to be drawn, and they
    # sat in the policy's menu to be scored and chosen.
    #
    # Excluded outright rather than gated on a build, because the subclass these
    # belong to has no leg to gate on: `BUILDS["wizard"]` holds two, and neither is
    # it. When one is added this becomes "unless the build is that one", and the
    # keyword is what it will ask.
    # **And the general form of the same fault, which the keyword test above
    # is one hand-cut instance of.** A class's level-0 rows are its *feature
    # chassis*, and the Essentials line gave most classes a second one --
    # 529 rows of it, #642. Dealing every level-0 row deals every chassis, so
    # a cleric would hold the templar's four features and the warpriest's
    # 101 at once, being two sub-classes. Harmless-looking: nothing fails, the
    # character simply has twice what it should.
    #
    # It was already live for the wizard, which held the arcanist's ten *and*
    # the sha'ir's three. `legs.chassis_clash` is the gate that catches the
    # next one; this is the fix. #851.
    #
    # A blank chassis, or a ref the `class_feature` table does not list, is
    # class-wide and belongs to every character of the class -- see
    # `_chassis_map`.
    from combat_engine.engine.types import Keyword as _Kw

    # **And a level-0 row that names a leg belongs to that leg only.** This
    # path does not go through `_fits`, so it was unconditional: measured
    # before `#1051`, every one of the warlock's seven pact features sat in
    # **84 of 84** warlock hands -- all seven legs at once -- and the same
    # held for every class whose chassis carries a gated feature. Harmless
    # in play, because `Power.requires` refuses them mid-fight, and wrong
    # everywhere it is read: the sheet, the page, and the policy's menu.
    chassis = chassis_of(cls, who_chassis)
    # **`ORIGINAL` resolves to the blank here**, so neither filter below
    # has to know about it, and asking for the original is then exactly as
    # expressive as asking for a named chassis -- `#1191`'s ruling.
    #
    # **It does NOT deal what `who_chassis=""` deals, and saying so was my
    # first version of this comment.** A blank *argument* means "the
    # default", which `chassis_of` answers with the first named chassis, so
    # the two differ for all 6 classes that have one -- measured, every
    # leg, every class. That difference is the whole bug: there was one
    # spelling for "the usual one" and none for "the plain one". What is
    # identical is the filter's behaviour on the resolved value.
    if chassis == ORIGINAL:
        chassis = ""
    belongs = _chassis_map()
    # **And a named chassis REPLACES the class-wide ladder rather than
    # adding to it**, which `in ("", chassis)` above does not say.
    # Camille's ruling on `#1136`:
    #
    #   > *"A character should only get what its class says, so for example
    #   > the hexblade should not get the features of the standard warlock
    #   > and vice versa."*
    #
    # It was worth twice the character: a warlock on either Essentials
    # chassis held its own 60-or-69 rows **and** the first book's 29,
    # all seven pacts among them. `superseded_for` is the rule and the
    # measurement behind it -- level coverage, 144 rows dropped across the
    # 12 pairings, 2 kept.
    replaced = superseded_for(cls, chassis)
    out = sorted(p.ref for p in mine
                 if ladder_row(p, level)
                 and _Kw.BLADESPELL not in (p.keywords or ())
                 and leg_named_by(p) in ("", build.name)
                 and belongs.get(p.ref, "") in ("", chassis)
                 and p.ref not in replaced)
    # Not already dealt: a class whose heal is itself a level-0 row was
    # handed it twice, so `Powers.known` carried the ref twice over. The
    # bard and the ardent are the two.
    out += sorted(p.ref for p in mine if _is_class_heal(p) and p.ref not in out)

    def deal(at: int, usage: Usage | None, count: int) -> list[str]:
        """`count` rows printed at level `at`, on this build's leg if it can be.

        `usage` of None means "whatever is printed here", which is what a utility
        level wants: a utility may be at-will, encounter or daily and the level is
        what makes it a utility.
        """
        here = [p for p in mine
                if p.level == at and (usage is None or p.usage is usage)]
        # **"of the same level as or lower in level than the class power you
        # would have gained"** -- the third of the four printed clauses, and
        # the one a level-equality filter silently drops. At level 10 a
        # trained character may take a level-2 or level-6 skill power, so the
        # pool is every opened row **at or below** this level, not at it.
        #
        # Only at a utility level, which is what `usage is None` says here:
        # a skill power is a utility power by print, so it never competes for
        # an attack slot. `UTILITY_GAINS` is the only caller passing None.
        if usage is None:
            here = here + [p for p in by_skill if p.level <= at]
        on_leg = [p for p in here if _fits(p, build)]
        pool = sorted(p.ref for p in (on_leg or here) if p.ref not in out)
        spare = sorted(p.ref for p in here if p.ref not in out and p.ref not in pool)
        chosen = _best_of(pool, count, cls, build, pick)
        # A thin leg is topped up from the rest of the class rather than
        # leaving the character with one at-will.
        while len(chosen) < count and spare:
            chosen.append(spare.pop(0))
        return sorted(chosen)

    for usage, gains in ATTACK_GAINS.items():
        for at in sorted(set(gains)):
            if at > level:
                continue
            out += deal(at, usage, sum(1 for g in gains if g == at))
    # **And the extra gains a dealt class feature prints.** Read against
    # `out`, which already holds this character's features by here, so the
    # gain lands on the character that has the row and on nobody else.
    # `deal` skips anything already dealt, so "an extra at-will of your
    # choice" is a different one rather than a second copy. #1112.
    for ref in list(out):
        for usage, when, from_level in EXTRA_GAINS.get(ref, ()):
            if when <= level:
                out += deal(from_level, usage, 1)
    for at in UTILITY_GAINS:
        if at <= level:
            out += deal(at, None, 1)
    return out + sorted(r for ref in out for r in riders.get(ref, []))


def dealt_hand(seed: int | str, cls: str, level: int,
               build: Build, who_chassis: str = "", race: str = "",
               trained: Iterable[str] | None = None) -> list[str]:
    """The hand a seed deals this class, **before** `power_swap` takes its
    card back. One derivation, for everybody who needs to predict it.

    `build` is **required**, where `loadout`'s is optional: the key this
    derives is `f"{seed}:{cls}:{build.name}"`, so there is no honest answer
    without one and inventing a name for the `None` case would mint a key no
    caller wants. All three callers already hold a `Build`.

    `spawn` and `Party.of` each wrote `Random(f"{seed}:{cls}:{build.name}")`
    out by hand, which is two copies of a key that has to agree or a party
    changes shape between the sheet and the board -- the drift `Party.of`'s
    own comment is about. `replay.py` needs a third copy to pin a fixture's
    powers (#783), so the derivation moves here instead of being written a
    third time.

    **Pre-swap on purpose.** `power_swap` is not idempotent -- it removes the
    lowest qualifying row once per feat that trades one -- so a hand recorded
    *after* the swap and then fed back through `spawn` would lose another row
    every time. Pinning the pre-swap hand lets the single swap in `spawn` run
    exactly as it always has, which is what makes the pin behaviour-neutral.

    **`trained` defaults rather than being required, and that is what stops
    the dealers diverging.** A skill power is drawn from the character's
    trained skills (`#1162`), so the hand now depends on a third fact about
    the character -- and three dealers plus `replay.py` would each have had
    to derive it. `None` means "derive it here", on the same key and from the
    same helper `Party.of` and `maker.dealt` already use for the pre-feat
    set, so a caller that passes nothing gets the answer they would compute.
    `spawn` passes its own, because it must honour a pinned `Character.skills`
    over any derivation.

    The set is the **pre-feat** one, which is a stated narrowing: a feat that
    trains a skill cannot open that skill's powers, because feats are drawn
    after the hand (`feats_for` reads it) and the printed step order puts
    skills before feats and powers after both. Reordering that is a draw move
    of its own and is not this.
    """
    if trained is None:
        trained = class_training(cls, race, Random(f"{seed}:{cls}:skills"))
    return loadout(cls, level, build, Random(f"{seed}:{cls}:{build.name}"),
                   who_chassis=who_chassis, trained=trained)


def _best_of(
    pool: list[str], count: int, cls: str, build: Build, pick: Random
) -> list[str]:
    """`count` powers out of `pool`, ranked and then sampled.

    **The sixth and last of the build choices to be scored**, and the largest by
    volume: a level-10 character takes about ten cards and took all of them with
    `rng.sample` over whatever passed `_fits`, which is a boolean. #234.

    `choices.sample` draws one at a time, so this draws repeatedly and drops
    what it has taken -- the same thing `rng.sample` was doing, with the odds
    weighted. Falls back to the uniform draw when `SCORED_CHOICES` is off, which
    is what that flag is for.
    """
    if not SCORED_CHOICES:
        return pick.sample(pool, min(count, len(pool)))

    from .choices import POWER_TOP, power_options, sample

    left = list(pool)
    taken: list[str] = []
    while len(taken) < count and left:
        drawn = sample(power_options(left, cls, build), pick, top=POWER_TOP)
        if drawn is None:
            break
        taken.append(drawn.ref)
        left.remove(drawn.ref)
    return taken


def feat_slots(level: int, race: str = "") -> int:
    """How many feats a character of this level has taken.

    One at first level and one more at every even level after, which is
    six by level 10. A human takes one more at first level, and that is
    the one printed exception -- named by ref, because a name would be
    prose and this file is tracked.
    """
    return 1 + level // 2 + (1 if race == HUMAN else 0)


#: The one race whose extra first-level feat is a rule rather than a
#: trait. Held as a ref for the same reason everything else is.
HUMAN = "r7"


def meets(node: dict | None, who: Character, powers: list[str]) -> bool:
    """Does this character satisfy a printed prerequisite?

    A **build-time** question, which is why it is here and not a
    `Power.requires`: that one is asked mid-fight of a creature on a
    board, and "you must be a fighter" is not a thing that changes
    between rounds.

    The tree is `etl/feat.py`'s, and every atom it cannot answer is
    answered **False**. That is the honest direction: a feat whose gate
    the engine cannot read is one nobody can be shown to qualify for, and
    handing it out anyway would give characters feats they have not
    earned and hide the gap. 690 of the 1,675 heroic feats gate on a race
    and are unreachable this way until there is one -- which is the
    number that makes a race worth building, and it should stay visible.
    """
    if not node:
        return True
    if "all" in node:
        return all(meets(n, who, powers) for n in node["all"])
    if "any" in node:
        return any(meets(n, who, powers) for n in node["any"])
    if "class" in node:
        return node["class"] == who.cls
    if "level" in node:
        return who.level >= node["level"]
    if "ability" in node:
        scores = scores_for(who.line, who.chosen)
        return scores.get(Ability(node["ability"]), 10) >= node["min"]
    if "race" in node:
        # **Either race answers, and only here.** #1029. `rt:r47-t1` is
        # the one printed trait that grants a second race, and its clause
        # is scoped to exactly this question:
        #
        #     "You are also considered a member of that race for the
        #      purpose of meeting prerequisites, such as feat or paragon
        #      path prerequisites."
        #
        # So the widening belongs in `meets` and nowhere else -- `spawn`
        # must keep reading `race` alone, or a revenant would arrive
        # wearing a second race's size, speed, scores and traits, none of
        # which the trait grants.
        #
        # `race2` is `""` for every character but a revenant, and `""`
        # never equals a prerequisite's named ref, so this costs nothing
        # for the other 45 races.
        return node["race"] in (who.race, who.race2)
    if "ref" in node:
        return node["ref"] in powers
    # **Armour and shields, which used to arrive as `weapon_prof` and be
    # answered against weapons.** `#568`. A class's printed Armor
    # Proficiencies line is cumulative -- *"Cloth, leather, hide,
    # chainmail"* -- so one word is enough to answer any rung at or below
    # it, which is what `armour.trains_in` does and why the ETL's collapse
    # to a single word costs nothing here.
    # **The chassis line *and* what a feat opened up**, which this read in
    # one half only. `armour_opened` has existed since `045878ee` and
    # `spawn` consults it; `meets` did not, so a feat granting plate could
    # not satisfy a feat gated on plate. `#568`'s own plan said *"meets
    # answers `armour_prof` off `line.armour` + armour_opened"* and only the
    # first half shipped.
    #
    # **Composed exactly as `spawn` composes it** -- `_heaviest` over the
    # line and the opened categories joined -- rather than comparing a
    # category against the ladder directly. That is not tidiness: the two
    # vocabularies differ. `category_of` answers `chainmail` where `LADDER`
    # holds `chain`, so `trains_in("chain", "chainmail")` is **False**, and
    # a second composition here would have refused every chain feat while
    # looking right. `_heaviest` matches as a substring, which is what makes
    # the one reading work for both. #1014's rule: one reading, not two.
    #
    # `powers` is every ref the character holds, feats included -- see the
    # `ref` atom above -- and `feats_for` takes feats one at a time
    # precisely so a feat can satisfy another taken in the same career.
    if "armour_prof" in node:
        from combat_engine.armour import trains_in

        opened, _shield = armour_opened(list(powers))
        best = _heaviest(" ".join([who.line.armour or "", *sorted(opened)]))
        return trains_in(best, str(node["armour_prof"]).lower())
    # `ClassLine.shield` is already 0, 1 or 2 -- see `Gear.shield`, which
    # records the kind and not merely whether -- so a printed *"heavy
    # shields"* is a comparison and not a lookup. The feat half goes through
    # `max` the same way `spawn` does it.
    if "shield_prof" in node:
        try:
            want = int(node["shield_prof"])
        except (TypeError, ValueError):
            return False
        _opened, opened_shield = armour_opened(list(powers))
        return max(int(getattr(who.line, "shield", 0) or 0),
                   opened_shield) >= want
    if "weapon_prof" in node:
        wanted = node["weapon_prof"].lower()
        return any(
            # `slug`, not the ref -- see `Weapon.slug`. The ref is the
            # compendium id now and un-slugging it would match nothing. #339.
            wanted in (w.group, w.category, w.slug.replace("-", " "))
            for w in who.line.weapons
        )
    # **The power source**, which 300 feat prerequisites ask about.
    # Camille's call on `#1094`, option C.
    #
    # `class.power` since the same issue -- *arcane*, *martial*, *divine*,
    # *primal*, *psionic*, *shadow*. `#1094`'s body said this data
    # *"exists nowhere"* and the reason it looked that way is a column
    # collision: `class.source` has always been populated and holds the
    # **book**. One column in one SELECT, not a hand-written table.
    #
    # Derivable from `cls` alone, which is what makes it safe to answer
    # here: `choices._legal_feats` is memoised on a key that already holds
    # `cls`, so this cannot give two answers for one key.
    if "source" in node:
        return str(node["source"]).strip().lower() == power_source(who.cls)
    # **A trained skill, on the set that is DERIVABLE and not on the pool
    # picks.** `#1113`, and the narrowing is deliberate and measured.
    #
    # The set is class-granted (`class_skill.granted = 1`) plus the one
    # racial trait that trains a skill **outright** -- measured, and not
    # the three `_trained_skills` names: `r3` and `r7` both *choose* one,
    # which needs a stream. That is the **non-circular** reading
    # `#1113` argued for, minus the explicit request, and the minus is
    # forced by where this function is called from:
    #
    # * `choices._legal_feats` builds its own
    #   `Character(cls=, level=, build=, race=)` with **no `skills=`**, so
    #   `who.skills` is empty on that path whatever the caller pinned;
    # * and it is memoised on `(cls, level, leg_name, race, taken)`. A
    #   reader that consulted `who.skills` would make the pool depend on
    #   something absent from the key, which is the order-dependent cache
    #   bug where the first caller's answer freezes for the process.
    #
    # Granted-plus-race depends only on `cls` and `race`, both in that
    # key, so it is answerable without touching the cache.
    #
    # **What that reaches, measured: 39 of the 87 feats**, on six skills
    # -- arcana, dungeoneering, nature, religion, stealth, thievery. The
    # other 48 ask for skills no class is *given* (intimidate alone is 18)
    # and so need the pool picks, which needs them computed before the
    # feats are dealt and threaded into `legal_feats`. That is the book's
    # own step order and it is `#1113`'s remaining half.
    #
    # A feat-trained skill deliberately does **not** count toward another
    # feat's prerequisite: `meets` is asked *while* feats are being chosen,
    # so reading them would be circular, and the book puts skills at step
    # 4, before feats, for that reason.
    if "skill" in node:
        # **A pinned character answers off its own training.** `#1113`.
        #
        # `who.skills` is the union a previous deal produced -- granted,
        # pool picks, race and feat-granted -- so for a campaign party or
        # the advisor this is the real answer and reaches the 67 feats the
        # granted set cannot. `choices.legal_feats` carries it into the
        # cache key, which is what makes reading it here safe.
        #
        # Empty is the **dealer's** path and keeps the old answer exactly: a
        # character mid-build does not know its pool picks yet, so the
        # derivable half is all there is. The remaining half of `#1113` is
        # the draw-order change that would give the dealer them too, and it
        # is not free -- see the issue.
        wanted = str(node["skill"]).strip().lower()
        if who.skills:
            return wanted in {s.strip().lower() for s in who.skills}
        return wanted in given_skills(who.cls, who.race)
    # **Worship, as a ref and as a domain.** `#454`, and both read through
    # `domains_of` so Camille's eventual *"mapping from domain to prereq"*
    # is a change of atom rather than of reader.
    #
    # 54 clauses name a god and 34 name a domain, measured -- so the second
    # is not a refinement of the first, it is a third of the family.
    if "deity" in node:
        return bool(who.worships) and who.worships == node["deity"]
    if "deity_domain" in node:
        return str(node["deity_domain"]).strip().lower() in domains_of(
            who.worships)
    # **term: still answered False, and it is now `#1160` and nothing
    # else.** This said *"586 feats ... `#1094`/`#1044` carry what each kind
    # would need"* and both halves were wrong:
    #
    # * **both issues are closed.** `#1094` fixed `source` and `skill` --
    #   the two atoms that were in this same state -- and `term` stayed
    #   behind, so the sentence sent a reader to two dead issues. The
    #   in-code variant of the stale-pointer problem the root `CLAUDE.md`
    #   opens with, and exactly as hard to notice.
    # * **586 is not the count.** Measured: **392 feats** carry a `term`
    #   atom, 430 atoms, 230 distinct values, and **0** are satisfied for
    #   any of ten classes.
    #
    # Failing closed is still right, and the docstring above says why. The
    # work is an ETL one rather than a `chargen` one: every value is a `q…`
    # glossary ref -- a printed *phrase* and not a structured fact -- so it
    # wants the treatment `#279` gave the Glossary. A handful name a thing
    # the engine already holds -- one is a racial trait, by ref, and would
    # resolve mechanically -- and most of the rest carry only a
    # description, which is prose.
    #
    # **No example quoted here, deliberately.** The first draft of this
    # note gave the resolvable one as a phrase to make the point concrete,
    # and the phrase *is* that trait's printed name: `hooks/commit-msg`
    # refused the commit and HEAD did not move. Describe the shape and cite
    # the ref -- the same correction this tree's own notes record twice, in
    # the paragraphs that explain the rule.
    return False


@cache
def _all_deities() -> tuple[str, ...]:
    """Every deity ref, sorted. `#454`.

    Sorted so a seed picks the same one every time -- the ordering a
    database returns is not a promise, and `_trained_skills` records the
    same reasoning about its own pool.
    """
    from combat_engine.db import game

    try:
        return tuple(sorted(
            r["ref"] for r in game().execute("SELECT ref FROM deity")))
    except Exception:
        return ()


def deal_deity(rng: Random, cls: str = "") -> str:
    """Pick a deity for a character that names none. `#454`.

    Uniform over the 134, which is the honest default: **which** god a
    character follows is campaign flavour, and Camille's ruling put that
    half in campaign data -- *"Deities are campaign specific and should go
    in the graphrag for a campaign."* What the mechanics need is only that
    a character **has** one, so 194 worship prerequisites become answerable
    either way.

    `cls` is taken and deliberately unused: a class's own page restricts
    which gods suit it, and that restriction is campaign-and-flavour rather
    than mechanical. Named in the signature so the one place to add it
    later is obvious, and said here so the next reader does not take its
    absence for an oversight.
    """
    pool = _all_deities()
    return rng.choice(list(pool)) if pool else ""


#: Deal a background, like `DEAL_DEITY`. Separate so the two can be
#: measured apart -- a background grants a **skill bonus**, so turning it
#: on moves every character's skill numbers where a deity moves only which
#: prerequisites are answerable.
DEAL_BACKGROUND = True

#: What the printed background benefit is worth, and which one of the four
#: this takes. PHB2 p178, verbatim:
#:
#: > *"Regardless of how many background elements you use, when you create
#: > a character you can (with your DM's consent) select **one** of the
#: > following background benefits:*
#: > * *Gain a +2 bonus to checks with a skill associated with your
#: >   background.*
#: > * *Add a skill associated with your background to your class's skills
#: >   list before you choose your trained skills.*
#: > * *Choose one language connected to your background [...]*
#: > * *If you are using a campaign setting that offers regional benefits
#: >   [...] gain a regional benefit."*
#:
#: **The +2, and the choice is Camille's ruling on `#456`** -- *"If they
#: give skill bonuses, then they are eventually consumed in skill
#: challenges."*
#:
#: It is also the only one of the four this project can take cleanly. The
#: second has an ordering in its own sentence -- *"before you choose your
#: trained skills"* -- so it widens the pool the trained-skill draw reads
#: and would have to land ahead of that draw. A language has no combat or
#: challenge meaning. A regional benefit needs a campaign setting, and
#: `general` is this project's default, so there is nothing to grant.
BACKGROUND_BONUS = 2


@cache
def _background_pool() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Backgrounds a character with no setting may be dealt, with skills.

    Camille's ruling on `#456` is *"drawn at random from **valid options
    for the character**"*, and three filters are what "valid" can honestly
    mean off this table:

    ```
    general = 1           not tied to a published setting -- 516
    skills != '[]'        names at least one engine skill -- 711
    kind != 'Racial'      209 of the 511 that pass both
    ```

    **The racial exclusion is the one that needs saying.** A racial
    background belongs to one race, and `background` has **no race
    column** -- so there is no way to tell whether a given one is valid
    for a given character. Dealing them anyway would hand a dwarf an
    elf's history, so they are out until the table can say. That leaves
    **302**.

    `kind` is NULL on 123 of the 302 and they are kept: a missing category
    is the importer not classifying the page, not a claim that the
    background is race-specific.
    """
    import json as _json

    from combat_engine import db as _db

    got: list[tuple[str, tuple[str, ...]]] = []
    for row in _db.game().execute(
            "SELECT ref, skills FROM background"
            " WHERE general = 1 AND skills IS NOT NULL AND skills != '[]'"
            " AND (kind IS NULL OR kind != 'Racial') ORDER BY ref"):
        try:
            skills = tuple(_json.loads(row["skills"]) or ())
        except Exception:
            continue
        if skills:
            got.append((row["ref"], skills))
    return tuple(got)


def deal_background(rng: Random) -> str:
    """Pick a background for a character that has none. `#1078`.

    Uniform over `_background_pool`, which is the honest default for the
    same reason `deal_deity` is: **which** history a character has is
    campaign flavour, and what the mechanics need is that it has one so
    the skill bonus exists to be consumed in a challenge.

    Ordered by ref inside the pool, so the same seed deals the same
    background twice.
    """
    pool = _background_pool()
    return rng.choice(pool)[0] if pool else ""


def background_skill(ref: str) -> str:
    """The associated skill the +2 lands on, or `""`.

    **The first printed, which is `_build_options`' precedent and the same
    reasoning**: the card says *"a skill associated with your
    background"*, so it is a choice among the two the page lists, and
    taking the first is reproducible and needs no scoring. Choosing the
    better of the two is a draw change of its own and would move every
    character holding a background, so it is not smuggled in here.
    """
    for got, skills in _background_pool():
        if got == ref:
            return skills[0] if skills else ""
    return ""


@cache
def domains_of(deity: str) -> frozenset[str]:
    """The domains this deity carries, lower-cased. `#454`.

    Off `deity.domains`, which the importer already fills as a JSON list on
    every one of the 134 rows -- so the domain half of the worship
    prerequisites needs no new import at all. That is the measurement
    behind Camille's *"the most mechanical portion is their domains"*.

    Empty for a character who worships nobody, and for a ref the table does
    not carry: a prerequisite then matches nothing rather than raising,
    which is the direction every other atom in `meets` takes.
    """
    if not deity:
        return frozenset()
    import json

    from combat_engine.db import game

    try:
        row = game().execute(
            "SELECT domains FROM deity WHERE ref = ?", (deity,)).fetchone()
    except Exception:
        return frozenset()
    if row is None:
        return frozenset()
    return frozenset(str(w).strip().lower()
                     for w in json.loads(row["domains"] or "[]"))


@cache
def power_source(cls: str) -> str:
    """Which power source a class draws on, or `""`. `#1094`.

    Off `class.power`, which is the compendium's `Class.Power` -- **not**
    `class.source`, which is the book citation and is the collision that
    made this data look absent.

    Matched case-insensitively for the same `#339` reason `_trained_skills`
    gives: `Character.cls` is a slug and the table's key is the printed
    word. An unknown class answers `""`, which matches no prerequisite
    rather than raising -- a monster has no entry here and is not meant to.
    """
    from combat_engine.db import game

    want = (cls or "").strip().lower()
    if not want:
        return ""
    for row in game().execute("SELECT name, power FROM class"):
        if (row["name"] or "").strip().lower() == want:
            return (row["power"] or "").strip().lower()
    return ""


@cache
def given_skills(cls: str, race: str = "") -> frozenset[str]:
    """The skills this class and race are **given**, never the pool picks.

    The derivable half of `_trained_skills`, split out because `meets`
    needs exactly this half and cannot have the other -- see the `skill`
    branch of `meets` for why the pool picks are out of reach there.

    Lower-cased on both sides, like every other class lookup here.

    **Not a second copy of `_trained_skills`' granted branch**: that
    function calls this one, so the two cannot drift. Measured over the 25
    dealt classes: 17 of them are given at least one skill, and six
    distinct skills are given by some class.
    """
    from combat_engine.db import game

    want = (cls or "").strip().lower()
    out: set[str] = set()
    if want:
        for row in game().execute(
                "SELECT class, skill FROM class_skill WHERE granted = 1"):
            if (row["class"] or "").strip().lower() == want:
                out.add((row["skill"] or "").strip().lower())
    out |= {s.lower() for s in _race_skills(race)}
    return frozenset(out)


#: Sub-choices a row's card asks the player to make **when it is taken**,
#: by ref, in the order the card prints them.
#:
#: Hand-written, one entry per row, like every other table here: the card
#: says which options there are and no column records it, so there is
#: nothing to derive this from. `_build_options` deals the **first** one,
#: which is what the rows named on #758 were already assuming in prose --
#: so filling this in records the choice without moving a single number,
#: and the recorded value is what a row reads instead of guessing.
#:
#: Only the one family so far, deliberately. #758 asks for the key and the
#: dealer to prove themselves on one kind before the other twelve proxies
#: are switched over, because each switch changes what a character does.
BUILD_OPTIONS: dict[str, tuple[str, ...]] = {
    "f2743": ("necrotic", "cold"),
    # **Refs rather than printed words, which this table had not held
    # before.** `f2694` says *"choose one of the monk's Flurry of Blows
    # powers"* and there are five; the choice is between **rows**, not
    # between values, and `Cast.chosen_option` hands back whatever string
    # is here -- so `c.grant_row` takes it directly.
    #
    # **A copy of `content.powers.monk.level_0.FLURRIES`, deliberately.**
    # `chargen` cannot import `content` -- content imports chargen, so the
    # edge would be a cycle -- which is the same bind `etl.feat._ARMOUR_RUNG`
    # is in against `armour.LADDER`. Same answer: copy it, and gate the copy.
    # `drivers.build_options_mirror` asserts the two are equal, so a sixth
    # flurry landing in the monk file reddens here rather than being
    # silently unavailable to this feat.
    #
    # Which of the five is a **scoring** question, not a printed one, and
    # `_build_options` below takes the first by design -- see its docstring.
    # `#314` is where choosing well lives.
    "f2694": ("p7448", "p11207", "p13123", "p16131", "p16132"),
    # **`cf:artificer-f2` is here now, and what unblocked it was the
    # chooser rather than the scorer.** The note this replaces said the
    # entry could not be added because *"`_build_options` records the
    # first option unconditionally and by design, so an exclusion written
    # in either direction fires for every dealt artificer and the other
    # card of the pair is unreachable by anybody"* -- measured, with
    # `audit.py` moving `p10187` and `f3023` to UNUSED.
    #
    # Every word of that was true and the conclusion -- *"`#314` is where
    # choosing well lives and is what unblocks it"* -- pointed one issue
    # too far. **Choosing well is not needed; choosing at all is.**
    # `deal_build_option` below draws, so each half of the pair is the
    # dealt answer for some artificer and neither card is unreachable.
    # `#1085`, which is retitled to exactly that gap.
    #
    # Printed default first, which is what `rng=None` answers and what
    # `audit.board` therefore fields: the card reads *"you can choose to
    # take `p10187` **in place of** `p7635`"*, so `p7635` is the one a
    # character has unless it swaps.
    "cf:artificer-f2": ("p7635", "p10187"),
    # **The mage's SECOND school**, which is the one choice a leg cannot
    # carry: *"Choose a school of magic **different** from the one you
    # chose at 1st level"*, where the first is the leg. A character takes
    # one leg and stays on it, so the second school needs the other axis
    # -- which is this table. `#1247`, and `cf:warlord-marshal-f0`'s
    # `chargen.second_fork()` is the same gap from the other end.
    #
    # Three and not six: the compendium declares `Apprentice (Secondary)`
    # rows for three of the schools only, so those are the three a second
    # school can be. The *exclusion* is enforced by the row rather than
    # here -- this table has no idea what leg the character took, and
    # `cf:wizard-mage-f3` does.
    "cf:wizard-mage-f3": ("cf:wizard-mage-f3s0", "cf:wizard-mage-f3s1",
                          "cf:wizard-mage-f3s2"),
    # **The witch's coven**, `cf:wizard-witch-f1`'s own fork. Same reason
    # it is here and not a leg as the mage's second school: the wizard's
    # legs are spent on the arcanist's two and the mage's six schools, and
    # a character takes one leg. #642.
    "cf:wizard-witch-f1": ("cf:wizard-witch-f1s0", "cf:wizard-witch-f1s1"),
    # **The berserker's heartland.** Here for the same reason as the two
    # above and arrived at from the other side: `berserker` *is* the
    # chassis, so the leg is spent on the chassis itself and the fork
    # inside it has nowhere else to go. #642.
    "cf:barbarian-berserker-f4": ("cf:barbarian-berserker-f4s0",
                                  "cf:barbarian-berserker-f4s1",
                                  "cf:barbarian-berserker-f4s2"),
}


def _build_options(taken: list[str], rng: Random | None = None) -> set[str]:
    """`option:<ref>:<value>` for every row the build took that asks one.

    **`taken`, not `feats`, because a feat is not the only kind of row that
    asks.** This read only the feat list, so a **class feature** or an
    **item power** with a `BUILD_OPTIONS` entry got no option and the row
    could never read one -- measured on `#1112`'s ten claimants, three of
    them are not feats (`cf:artificer-f2`,
    `cf:sorcerer-elementalist-f1`, `i2345p1`).
    `Powers.known` holds `cf:` rows and item powers alike, so the caller
    passes the hand as well and the dict decides what is asked.

    **`rng` draws; without one the first printed option is taken.** The
    old note said a stream was *"on purpose"* because taking the first
    *"is the reading the rows already had, so the character is unchanged
    and `replay` is the proof of it"*. That was the right default while
    nothing could act on the answer, and it is what made
    `cf:artificer-f2` unwritable: its card prints an **exclusion** --
    *"if you choose it you cannot create [the other] at all"* -- and an
    exclusion written against an option recorded unconditionally fires for
    **every** dealt artificer, which `audit.py` measured by moving both
    `p10187` and `f3023`, the feat whose whole subject is the other card.

    So the fault was never the exclusion; it was a chooser that never
    chose. `#1085`, retitled to exactly that.

    Uniform, for `deal_build`'s stated reason: these are ways of playing a
    row rather than better or worse ones, and nothing scores them.
    Scoring is still a separate change and still moves every character
    holding one of these rows.

    **The caller passes its own keyed stream**, like every other dealer
    here, so drawing an option cannot move the dice the fight is about to
    roll. Omitting it keeps the old answer, which is what the two callers
    that have no seed do.
    """
    return {
        f"option:{ref}:{deal_build_option(rng, ref)}"
        for ref in taken if ref in BUILD_OPTIONS
    }


def deal_build_option(rng: Random | None, ref: str) -> str:
    """Which of a row's printed build-time options this character took.

    The draw `#1085` is about. `BUILD_OPTIONS[ref]` is the printed pair or
    list, `Cast.chosen_option` is the reader, and this is the half that was
    missing: the value was recorded as `options[0]` unconditionally, so a
    row could read the answer and every character gave the same one.

    `rng` of `None` answers the first, which is what the resolver wants and
    what every caller without a seed had before. Same split as
    `build_of`/`deal_build` and `chassis_of`/`deal_chassis`, and for the
    same reason: `audit.board` needs one fixed answer per ref or the sweep
    wobbles.
    """
    options = BUILD_OPTIONS[ref]
    if rng is None or len(options) <= 1:
        return options[0]
    return rng.choice(list(options))


def feats_for(
    cls: str, level: int = 1, build: Build | None = None,
    rng: Random | None = None, powers: list[str] | None = None,
    race: str = "", skills: Sequence[str] = (), worships: str = "",
) -> list[str]:
    """The feats this character has taken, drawn like its powers are.

    Only feats that are **written**, that are not a card some other feat hands
    over, and whose prerequisite this character **meets** -- so the draw cannot
    hand out a row that does nothing, one the book would not allow, or one that
    is not a choice at all. `choices.legal_feats` is that pool and is shared
    with the advisor; see its docstring for what the "not a card" clause cost
    before it existed.

    Taken one at a time rather than sampled, so that a feat naming another feat
    as its prerequisite can be taken in the same career as the one it needs.
    """
    # Imported for the side effect: this is what registers the rows.
    import combat_engine.content

    from .choices import legal_feats

    pick = rng or Random(0)
    race_ref = race
    held = list(powers or [])

    taken: list[str] = []
    for _ in range(feat_slots(level, race_ref)):
        legal = legal_feats(cls, level, build, race_ref, taken=held + taken,
                            skills=skills, worships=worships)
        if not legal:
            break
        taken.append(_one_feat(legal, cls, build, pick))
    return sorted(taken)


def _one_feat(
    legal: list[str], cls: str, build: Build | None, pick: Random
) -> str:
    """One feat from the legal pool -- scored and sampled, or uniform.

    Drawn one slot at a time rather than all at once, which is what
    `feats_for` was already doing and what lets a feat naming another as its
    prerequisite be taken in the same career: the pool is re-scored after each
    pick, so `unlocks_other_feats` pays out and then the feat it unlocked
    becomes legal.
    """
    if not SCORED_CHOICES:
        return pick.choice(legal)
    from .choices import FEAT_TOP, feat_options, sample

    drawn = sample(feat_options(legal, cls, build), pick, top=FEAT_TOP)
    return drawn.ref if drawn is not None else pick.choice(legal)


def proficiency(feats: list[str]) -> list[Weapon]:
    """The arms a character's feats let it carry, beyond its chassis.

    "You gain proficiency with all spears" is a **build-time** sentence
    and nothing a `Cast` can answer: the fight opens with the gear
    already in hand, so the clause has no moment to happen in. The feat
    says which base items it opens up in its own header --
    `proficiency=("w3607",)` -- and this is what reads them, the
    way `feats_for` reads the registry rather than keeping a list beside
    it that would go stale.

    A ref nothing carries yields nothing rather than raising. That is the
    honest direction: the row keeps its marker and `blocked.py` keeps
    saying so, where a silent invention would look finished.

    **A copy, and this handed out the module-level object for its whole
    life.** `PRINTED` and `IMPLEMENTS` are process-wide dicts, so a
    character armed from one held the *same* `Weapon` every other character
    in the process held -- and `c.weapon_range`, `c.gains_property` and
    `c.weapon_dice` all edit the weapon in place. Those three say in their
    own docstrings that they need no reader because "`Gear.weapons` holds
    `replace(w)` copies made per character by `chargen.spawn`, never the
    module-level weapons". True of the chassis; false of everything this
    function added.

    What it cost: `f1277` rewrites `w3662`'s range and gives it high crit,
    and it is the *only* row the audit board equips that weapon for.
    Audited three times in one process:

        audit #1: fired= 1 silent=False events=[... 'WeaponChanged']
        audit #2: fired=48 silent=True  events=['PowerResolved']
        audit #3: fired=48 silent=True  events=['PowerResolved']

    The first run rewrote the shared weapon; every later board found the
    rewrite already done, so the verbs announced nothing and the row read
    silent. In a wide sweep that is a coin flip on whether the worker had
    already touched the weapon -- which is #652, 4 silent of 9 sweeps, and
    the reason it was never reproducible narrow. #662.
    """
    from combat_engine.engine.dsl import REGISTRY

    out: dict[str, Weapon] = {}
    for ref in feats:
        declared = REGISTRY.get(ref)
        for want in getattr(declared, "proficiency", ()) or ():
            arm = PRINTED.get(want) or IMPLEMENTS.get(want)
            if arm is not None:
                out.setdefault(arm.ref, replace(arm))
    return list(out.values())


def _role(w: Weapon) -> str:
    """What job a weapon is carried for: casting, shooting or swinging."""
    if w.group == "implement":
        return "implement"
    return "ranged" if w.ranged else "melee"


def outfit(
    carried: list[Weapon],
    granted: list[Weapon],
    known: Sequence[str] = (),
    *,
    spent: set[str] | None = None,
) -> list[Weapon]:
    """What the character ends up holding, and what goes on its belt.

    **This is the build choice that used to have nowhere to live.** A granted
    arm was taken in hand only when the character had nothing at all for that
    job, and benched otherwise -- so a fighter that spent its one feat on a
    spiked chain owned the chain, swung the greataxe, and every row gated on a
    flail was dead. The reason given here was that "which of the weapons a
    character *may* carry it actually wields is a build choice, and nothing
    records one". `choices.wield_options` records one.

    The tempting rule is still wrong and is still not what this does. Swing
    whichever hits hardest and a rogue puts its dagger away for the chain,
    taking every light-blade Requirement its own class rows are written against
    with it. So the score counts those rows -- `keeps_class_rows` -- and a
    weapon has to beat them, not ignore them. `known` is what makes that
    possible.

    `spent` names the arms a **feat** opened, which is not the same as
    `granted`: a race trains a character in weapons through the same header
    field, and pricing a racial longsword as a spent feat slot was enough to
    take a ranger's second short sword out of its hand. Defaults to all of
    `granted`, which is right for a caller that has only one kind.

    **The number of arms per job is preserved, and only which ones changes.**
    A ranger carries two short swords -- the same ref twice -- and collapsing
    that to one would turn `Gear.two_weapon` false and every "wielding two
    melee weapons" Requirement with it. `_shield_for` counts the same list to
    decide whether a hand is free, so the count is load-bearing twice over.

    Returns the belt; `carried` is edited in place.
    """
    belt: list[Weapon] = []
    if not SCORED_CHOICES:
        for arm in granted:
            if any(w.ref == arm.ref for w in carried):
                continue
            if any(_role(w) == _role(arm) for w in carried):
                belt.append(arm)
            else:
                carried.append(arm)
        return belt

    from .choices import wield_options

    bought = {w.ref for w in granted} if spent is None else set(spent)
    # Every arm the character may use, by the job it does. Duplicates inside
    # `carried` are kept -- see the docstring; a granted one that duplicates
    # something already owned is not a second option.
    pool: dict[str, list[Weapon]] = {}
    for arm in carried:
        pool.setdefault(_role(arm), []).append(arm)
    owned = {w.ref for w in carried}
    for arm in granted:
        if arm.ref in owned:
            continue
        owned.add(arm.ref)
        job = _role(arm)
        # **Only a weapon a feat bought competes for a hand that is full.**
        # Camille's rule is about the feat -- "if the character has taken the
        # feat, it should almost certainly be taking that weapon as well" --
        # and a race costs nothing, so its weapon has no claim on a hand the
        # chassis already filled. Left competing, a racial longsword displaced
        # a ranger's short sword on score alone and took **36 ranger rows**
        # out of the audit's reach with it. It still fills an empty job, which
        # is what this function always did with a granted arm.
        if job in pool and arm.ref not in bought:
            belt.append(arm)
            continue
        pool.setdefault(job, []).append(arm)

    # Hands per job: what the chassis already filled, and one for a job it had
    # nothing for -- which is the old behaviour for that case, kept.
    hands = {
        role: max(1, sum(1 for w in carried if _role(w) == role)) for role in pool
    }
    # **A declared matching pair is not displaced.** Camille's call on
    # `#727`, asked twice and reaffirmed after the measurement below:
    #
    #   > *"A"* -- keep a matching pair over a single better weapon, for
    #   > the builds whose whole premise is two weapons.
    #
    # Four legs declare the **same ref twice** -- the tempest fighter and
    # the ranger's two-blade, marauder and companion -- and that duplicate
    # is the leg saying what it is for. The ranking did not know: at level
    # 10 a marauder carries three feat-bought arms, the two best of them
    # outrank a short sword, and **both** twins went on the belt. The
    # build whose premise is two matching blades held a whip and a
    # garrote.
    #
    # Measured through `outfit` at the two levels:
    #
    #     L1   carried=[w3611, w3611]  granted=[whip]
    #          held=[whip, w3611]                 one twin survives
    #     L10  carried=[w3611, w3611]  granted=[garrote, flail, whip]
    #          held=[whip, garrote]               neither does
    #
    # **Read off `carried`, not off the `Build`.** `outfit` is handed the
    # list rather than the leg, and a duplicated ref in it *is* the
    # declaration -- the same fact, one layer nearer the decision, and it
    # keeps this function taking no new argument.
    pairs = {
        role: ref
        for role in pool
        for ref in {w.ref for w in carried if _role(w) == role}
        if sum(1 for w in carried if w.ref == ref and _role(w) == role) > 1
    }
    held: list[Weapon] = []
    for role, arms in sorted(pool.items()):
        ranked = wield_options(arms, bought, list(known))
        order = {choice.ref: i for i, choice in enumerate(ranked)}
        # The pair first, then the ranking. A leg that declared no pair is
        # untouched, which is 95 of the 99 legs.
        pair = pairs.get(role, "")
        arms.sort(key=lambda w: (w.ref != pair,
                                 order.get(w.ref, len(order)), w.ref))
        keep = hands[role]
        held.extend(arms[:keep])
        belt.extend(arms[keep:])
    # **A ref cannot be held and stowed at once.** `Gear.stowed` is a set of
    # refs, so a ranger's second short sword going on the belt stowed the twin
    # in its hand as well -- two arms became one and `two_weapon` went false.
    # Anything already in hand is simply not on the belt.
    in_hand = {w.ref for w in held}
    carried[:] = held
    return [w for w in belt if w.ref not in in_hand]


def _stock_quiver(gear: Gear | None) -> None:
    """Put ordinary ammunition in the quiver for each launcher owned.

    Camille's ruling on `#520`, 2026-10-28: a character with mundane
    ammunition has **50** of it. The number is supplied rather than printed
    and `ammunition.MUNDANE` carries the quote.

    **One entry per *kind*, not per weapon.** A character holding two bows
    does not carry two separate bundles of arrows, and `loaded` walks the
    quiver looking for something that `fits` the launcher's group -- so a
    second entry of the same kind would simply never be reached. Keyed off
    `FIRES`, the printed launcher-to-ammunition table.

    **Weapons, not `held`.** A stowed crossbow still has bolts; what decides
    whether ammunition is carried is owning the launcher, not having it in
    hand this second.

    Does nothing for a character that fires nothing, which is most of them:
    `FIRES` has three entries and every melee weapon and implement is absent
    from it.
    """
    from combat_engine.engine.ammunition import FIRES, MUNDANE
    from combat_engine.engine.components import Ammo

    if gear is None:
        return
    kinds = {FIRES[w.group] for w in gear.weapons if w.group in FIRES}
    have = {a.kind for a in gear.quiver}
    for kind in sorted(kinds - have):
        gear.quiver.append(Ammo(ref="", kind=kind, count=MUNDANE))


#: How many consumables a dealt character carries. Camille's ruling on
#: `#1233`, 2026-11-10, verbatim:
#:
#:   > *"For characters generated automatically, for now let's just give
#:   > them two random potions of their level or lower. For player
#:   > generated characters don't do that. We'll actually have item
#:   > shopping."*
#:
#: So this is the **automatic** path only. There is no player-driven path to
#: exclude yet (`#793`), which is why nothing here tests for one -- the
#: second half of the ruling constrains whoever builds that.
DEALT_CONSUMABLES = 2


def _stock_consumables(
    gear: Gear | None,
    powers: Powers | None,
    level: int,
    rng: Random,
    pinned: tuple[str, ...] = (),
) -> None:
    """Put two consumables of this character's level or lower on its person.

    **Why this exists at all.** `treasure` deals the three enhancement
    categories -- `attack_damage`, `ac`, `defences` -- because its job is to
    stop a character running its own numbers cold. A consumable carries no
    `enh_to`, so all 118 of them sat outside that pool by construction and
    **nobody was ever dealt one**, which left `c.consume_item()`'s ten rows
    and `chargen.deals_consumables`' rows with no character who could hold
    what they are about. `#877` asked whether that should change and was
    closed without an answer; `#1233` is the answer.

    **Carried, not worn.** `Gear.carried` is a list of refs rather than
    `Magic` objects in `worn`: a slot holds one thing for the whole fight
    and a potion occupies no slot, there can be two of the same kind, and it
    is spent rather than taken off. That is the second of `#877`'s two
    questions, which was mine rather than Camille's.

    **Both one-use categories, which took a second ruling.** The first said
    "potions" and this drew `Consumable` alone, 118 items. Measured against
    the ten rows the change was for, **seven of them are explicitly about
    *alchemical* items** -- "an alchemical item in hand", "+2 to attack
    rolls with alchemical items" -- so the narrow reading unblocked three at
    most. Camille, asked again with that count, 2026-11-10:

      > *"ah, random from any consumable"*

    So the pool is `Consumable` **and** `Alchemical Item`: 193 items, still
    two of them per character, so nobody is stronger than the first ruling
    intended.

    **Level or lower, off `item_step`.** An item's level lives there and not
    on `item`, so the join is the same one `treasure` makes. Measured over
    the corpus: 18 of the 193 are available at level 1, 103 by level 5, all
    193 by level 10 -- so the pool is never empty, and **every one of the
    193 has at least one declared block**, meaning a dealt item is never an
    inert object.

    **Sampled without replacement, and never two of a kind.** This first
    fell back to `rng.choice` repeats on a pool smaller than two, reasoning
    that two of the same potion is a legitimate hand. **It is not a hand
    this engine can play**: a block's budget is its printed `usage=`, so
    `i3309p1` is `daily` and `usable` returns `(False, 'expended')` after
    the first drink -- the second copy sits in `carried` undrinkable. The
    object ought to be the budget for a consumable rather than the power
    line, and that is a ruling and a wider change, so `#1238` holds it.

    Measured, the branch was also dead: the pool is **18 at level 1**, 26 at
    2, 49 at 3, all 193 by level 10 -- never below two. So it was dead code
    whose only possible output was a broken hand, which is worse than no
    fallback. `min(DEALT_CONSUMABLES, len(pool))` deals fewer instead, and
    no path can now mint a copy that cannot be drunk.

    **And its blocks go into `Powers.known`, which is what makes it an item
    rather than a souvenir.** Carrying a potion that cannot be drunk was the
    first half of this ruling and it moved no row: the ten rows are about
    *using* an alchemical item, so the facility they name is a usable one.
    `equipment.equip` does the same three lines for a worn item and
    `_blocks_of` is the same declared-only filter `treasure` uses -- a
    `Powers.known` holding an undeclared ref is a card the engine cannot
    resolve.

    **Not through `equip`,** deliberately. That lays enhancement, defence
    mods and a crit rider off the item's columns and files it in a `worn`
    slot, all four of which are wrong for a thing on your belt. The powers
    loop is the only part of it a carried item wants.

    Takes `rng` rather than reaching for module state, so a dealt character
    stays reproducible from its seed. That is the same contract
    `_pick_item` keeps.
    """
    from combat_engine.db import game

    if gear is None:
        return
    # **A pin is a record, so it is put back rather than re-dealt.** The
    # `#1101` argument, one field over: a party dealt fresh potions each
    # fight walks into every encounter with different ones, and a drunk
    # one comes back. An empty pin means nobody is tracking this character
    # across a day, which is every single-encounter caller.
    if pinned:
        gear.carried.extend(pinned)
        _offer_carried(gear, powers, pinned)
        return
    picks = deal_consumables(level, rng)
    gear.carried.extend(picks)
    _offer_carried(gear, powers, picks)


def deal_consumables(level: int, rng: Random) -> tuple[str, ...]:
    """Two one-use items of this level or lower, by entry ref.

    **Public and separate from `_stock_consumables`, because there are two
    callers and one pool.** This one puts them straight onto a board;
    `story.Party.of` pins them on a `Sheet` instead, so a party holds the
    same potions all day and a drunk one stays drunk. Both need the same
    query and the same ruling, and a second copy of the SQL is the drift
    fault this tree keeps paying for.

    The pool, the sampling and the levels are documented on
    `_stock_consumables`, which is where the ruling is quoted.
    """
    from combat_engine.db import game

    pool = [
        row["ref"]
        for row in game().execute(
            "SELECT DISTINCT i.ref FROM item i JOIN item_step s ON s.ref = i.ref "
            "WHERE i.category IN ('Consumable', 'Alchemical Item') "
            "AND s.level <= ? ORDER BY i.ref",
            (level,),
        )
    ]
    if not pool:
        return ()
    return tuple(rng.sample(pool, min(DEALT_CONSUMABLES, len(pool))))


def _offer_carried(
    gear: Gear, powers: Powers | None, items: Sequence[str]
) -> None:
    """Put each carried item's own rows into `Powers.known`.

    The three lines `equipment.equip` does for a worn item, and what makes
    a carried one an item rather than a souvenir: the ten rows `#1233`
    unblocks are about *using* an alchemical item, so a list of refs no
    menu offers moves none of them.

    Its own function because both arms of `_stock_consumables` need it --
    the dealt one and the pinned one -- and a second copy is the drift
    fault this tree keeps paying for.

    **Not through `equip`,** deliberately: that lays enhancement, defence
    mods and a crit rider off the item's columns and files it in a `worn`
    slot, all four wrong for something on your belt. The powers loop is
    the only part of it a carried item wants.

    `_blocks_of` is the declared-only filter `treasure` uses -- a
    `Powers.known` holding an undeclared ref is a card the engine cannot
    resolve.
    """
    if powers is None:
        return
    for item in items:
        for block in _blocks_of(item):
            if block not in powers.known:
                powers.known.append(block)


def _stock_thrown(gear: Gear | None) -> None:
    """Record how many copies of each throwable weapon the character has.

    Camille's ruling on `#520`, 2026-10-28: **5**, where mundane ammunition
    is 50. `ammunition.THROWN` carries the quote and the reason the two
    numbers differ.

    **Keyed by weapon ref, one entry per throwable owned** -- unlike the
    quiver, which is one entry per *kind*, because two bows draw on one
    bundle of arrows and two throwables are two different weapons with two
    separate counts.

    `Weapon.thrown` is the test and it is the printed field: 17 weapons
    carry a thrown range and the rest carry `None`, so no vocabulary is
    invented here either. `weapons` rather than `held` for the same reason
    as the quiver -- a stowed javelin is still carried.

    Never overwrites a count that is already there, so a character rebuilt
    mid-fight does not get a refilled set of spares.
    """
    from combat_engine.engine.ammunition import THROWN

    if gear is None:
        return
    for arm in gear.weapons:
        if arm.thrown is not None:
            gear.thrown_left.setdefault(arm.ref, THROWN)


def power_swap(powers: list[str], feats: list[str], *,
               cls: str = "", level: int = 0,
               record: set[str] | None = None) -> list[str]:
    """The hand that is left after the feats that trade a card for one.

    "You can swap one of your 3rd-level or higher encounter attack powers
    for this one" is an exchange made when the character is built. The
    card arrives with the feat -- its body hands it over -- and this is
    the other half: something goes back.

    The **lowest** qualifying power goes, which is the one a player gives
    up, and ties break by ref so that the same seed deals the same
    character twice. A feat whose trade finds nothing to take costs
    nothing, which is what happens to a character too junior to have one.

    **And for `Swap.pool`, something also comes in.** `#1114`'s four rows
    print no card of their own -- *"choose one martial daily attack power
    of your level or lower from your class"* -- so the incoming power is
    drawn from the class list rather than handed over by the feat. Drawn
    at the **same level and usage** as the power going out, which is the
    printed *"of the same level"*, and excluding what the character
    already knows, because a trade for a card already in hand is not a
    trade.

    **No stream, and the pick is the highest-rated rather than random.**
    Every other dealer here takes an rng of its own so that dealing a
    character cannot move the dice the fight is about to roll. This needs
    none: `ratings.score` is a static table, so the choice is
    deterministic for a given hand and the character is reproducible
    without one. It also answers the printed *"you **can** swap"* the way
    the removal half already does -- by making the beneficial trade -- and
    a default of "do not swap" would leave four drawable feats inert,
    which this repo treats as a fault rather than a safe no-op.

    `cls` and `level` are keyword-only and default to nothing, so a caller
    that does not pass them gets exactly the old behaviour and a `pool`
    row finds no pool to draw from. That is the honest direction and the
    same one `chargen.proficiency` takes about itself: the row does nothing
    and keeps its marker, where an invention would look finished.
    """
    from combat_engine import ratings
    from combat_engine.engine.dsl import REGISTRY

    out = list(powers)
    for ref in feats:
        trade = getattr(REGISTRY.get(ref), "swap", None)
        if trade is None:
            continue
        pool = [
            p
            for p in out
            if (row := REGISTRY.get(p)) is not None
            and row.level >= trade.level
            and (trade.usage is None or row.usage is trade.usage)
            # A utility is a row with nothing to attack with, which is how
            # `spellbook` tells the two apart as well.
            and (row.attack is None) is trade.utility
        ]
        if not pool:
            continue
        gone = min(pool, key=lambda p: (REGISTRY[p].level, p))
        out.remove(gone)
        if trade.pool != "class" or not cls:
            continue
        # **The incoming half.** Same level as the one that went, same
        # usage, this character's class, and not already in hand.
        want = REGISTRY[gone].level
        offer = [
            p
            for p, row in REGISTRY.items()
            if p not in out
            and getattr(row, "cls", "") == cls
            and row.level == want
            and row.level <= (level or want)
            and (trade.usage is None or row.usage is trade.usage)
            and (row.attack is None) is trade.utility
        ]
        if not offer:
            # Nothing to draw is not a reason to lose the power as well:
            # put it back, so a class with no alternative at that level is
            # left exactly as it was rather than a card down.
            out.append(gone)
            continue
        took = max(offer, key=lambda p: (ratings.score(p, cls), p))
        # **Recorded, not put in the hand, and that is what makes the row
        # writable.** The hand is the wrong place: a row whose whole
        # effect is a header field has an empty body, and **0 of the
        # 23,000 rows in this tree are drawable with an empty body** --
        # every one carries a marker. So a silent hand edit would leave
        # four feats drawable and inert, which `lint` refuses outright and
        # is right to.
        #
        # Written as `option:<feat>:<power>` instead, which is the
        # convention `#758` established and `Cast.chosen_option` already
        # reads. The feat's body then hands the card over with
        # `c.grant_row`, exactly as `_granted` does for the rows whose
        # card arrives with the feat -- same shape, same verb, and
        # observable, where a hand edit is not.
        if record is not None:
            record.add(f"option:{ref}:{took}")
    return out


def retrain(who: Character, drop: str, take: str) -> Character:
    """Change one feat, power or skill the character already chose. #991.

    > *"Every time you gain a level, you can retrain your character: change
    > one feat, power, or skill selection you made previously. You can make
    > only one change at each level. When your class table tells you to
    > replace a power you know with a different power of a higher level,
    > that doesn't count as retraining."*

    Returns a **new** `Character`; the one handed in is untouched, so a
    caller can offer the swap, show it, and keep the old sheet if the player
    declines.

    **The allowance is not spent here**, deliberately. *"Only one change at
    each level"* is a fact about levelling, and nothing applies a level yet
    -- `#1013`, where `xp.ready()` says a character has earned one and
    `story/run.py:1893` only narrates it. So the caller that grants the
    level is the thing that may call this once, and putting a counter here
    would be a second place recording what a level is.

    **Which of the three it is, is read off `drop` rather than passed in.**
    A ref is a feat, a power or a skill word and cannot be two of them, so
    an argument saying which could only ever disagree with the ref -- and
    `power_swap`'s neighbours in this file take the same view.

    ## Every refusal below is printed, and raises rather than returning

    A silent no-op would hand back a character that looks retrained and is
    not, which is the failure this component's notes keep naming. The
    message quotes the reason.

    **A feat** may be swapped for one whose prerequisites are met, and not
    if it is itself a prerequisite for something the character has.
    `choices.legal_feats` is the pool -- written, not marked, gate met,
    not a second card -- asked with the dropped feat **already removed**, so
    a feat that only qualified because of the one being dropped is refused
    by construction rather than by a second rule.

    *"A feature of the class rather than a choice"* needs no check: a class
    feature is a `cf:` ref and lands in `Powers.known` through the chassis,
    never in `Character.feats`, so it cannot be named here. Said rather than
    coded, because a check that can never fire reads as a guarantee.

    **A power** may be swapped for one of the **same usage**, the **same
    level or lower**, and the **same class**. Three columns -- `power.usage`,
    `power.level`, `power.class` -- and a fourth refusal that is not a
    column: a `cf:` ref is a class feature and not a known power.

    **Lower is allowed and higher is not**, which is the asymmetry worth
    stating: the printed words are *"of the same level or lower"*, and the
    higher-level case is the class table's own replacement, which the rule
    says explicitly *"doesn't count as retraining"*. Two mechanisms that
    look like one.

    **A skill** may be swapped for another on the class list, and not if the
    one dropped is *granted*. `class_skill.granted` is that distinction --
    the first printed sentence against the second -- and a granted skill is
    *"predetermined by the class"* in the rule's words.

    A skill required by a held feat is also refused, read off `feat.prereq`
    directly rather than through `meets`: that function answers every
    `skill` atom False today (`#1113`), so asking it would refuse nothing.
    """
    import json

    from combat_engine.db import game

    from .choices import legal_feats

    db = game()

    if drop in who.feats:
        if take in who.feats:
            raise ValueError(f"{take} is already taken")
        # **What depends on it**, read straight off the prerequisite trees of
        # everything else held. `meets` evaluates a tree against a
        # character; this is the reverse question and the same data.
        for other in who.feats:
            if other == drop:
                continue
            row = db.execute(
                "SELECT prereq FROM feat WHERE ref = ?", (other,)).fetchone()
            if row is None or not row["prereq"]:
                continue
            try:
                node = json.loads(row["prereq"])
            except (TypeError, ValueError):
                continue
            if drop in _refs_named(node):
                raise ValueError(
                    f"{drop} cannot be retrained: {other} requires it")
        kept = [f for f in who.feats if f != drop]
        if take not in legal_feats(
                who.cls, who.level, build_of(who.cls, who.build),
                who.race, taken=[*who.powers, *kept]):
            raise ValueError(
                f"{take} is not a feat this character may take")
        return replace(who, feats=[*kept, take])

    if drop in who.powers:
        if take in who.powers:
            raise ValueError(f"{take} is already known")
        if drop.startswith("cf:") or take.startswith("cf:"):
            raise ValueError(
                "a class feature is not a power selection and cannot be "
                "retrained")
        was = db.execute(
            "SELECT class, level, usage FROM power WHERE ref = ?",
            (drop,)).fetchone()
        now = db.execute(
            "SELECT class, level, usage FROM power WHERE ref = ?",
            (take,)).fetchone()
        if was is None or now is None:
            raise ValueError(
                f"{drop if was is None else take} is not a printed power")
        if (now["usage"] or "").lower() != (was["usage"] or "").lower():
            raise ValueError(
                f"{take} is {now['usage']} and {drop} is {was['usage']}: a "
                "power is replaced by one of the same type")
        if (now["class"] or "").lower() != (was["class"] or "").lower():
            raise ValueError(
                f"{take} is a {now['class']} power and {drop} is a "
                f"{was['class']} one: a power is replaced from the same class")
        if int(now["level"] or 0) > int(was["level"] or 0):
            raise ValueError(
                f"{take} is level {now['level']} and {drop} is level "
                f"{was['level']}: a power is replaced by one of the same "
                "level or lower")
        return replace(who, powers=[p for p in who.powers if p != drop]
                       + [take])

    if drop in who.skills:
        if take in who.skills:
            raise ValueError(f"{take} is already trained")
        rows = db.execute(
            "SELECT skill, granted FROM class_skill WHERE lower(class) = ?",
            (who.cls.lower(),)).fetchall()
        if not rows:
            raise ValueError(f"{who.cls} prints no skill list to retrain in")
        if any(r["skill"] == drop and r["granted"] for r in rows):
            raise ValueError(
                f"{drop} is trained by the class itself and is not a "
                "selection")
        if take not in {r["skill"] for r in rows if not r["granted"]}:
            raise ValueError(
                f"{take} is not on the {who.cls} skill list")
        for ref in who.feats:
            row = db.execute(
                "SELECT prereq FROM feat WHERE ref = ?", (ref,)).fetchone()
            if row is None or not row["prereq"]:
                continue
            try:
                node = json.loads(row["prereq"])
            except (TypeError, ValueError):
                continue
            if drop.lower() in _skills_named(node):
                raise ValueError(
                    f"{drop} cannot be retrained: {ref} requires it")
        return replace(
            who,
            skills=(*(s for s in who.skills if s != drop), take))

    raise ValueError(
        f"{drop} is not a feat, power or skill this character chose")


def _refs_named(node: object) -> set[str]:
    """Every `ref` a prerequisite tree names, at any depth."""
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("all", "any"):
                for child in value or ():
                    out |= _refs_named(child)
            elif key == "ref" and isinstance(value, str):
                out.add(value)
    return out


def _skills_named(node: object) -> set[str]:
    """Every `skill` a prerequisite tree names, case-folded, at any depth.

    Read here rather than through `meets` because that function answers
    every `skill` atom False (`#1113`), so it would refuse nothing.
    """
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("all", "any"):
                for child in value or ():
                    out |= _skills_named(child)
            elif key == "skill" and isinstance(value, str):
                out.add(value.strip().lower())
    return out


#: What the printed maths assumes you are holding. Enhancement runs in
#: five-level bands, and 4e's own advice is blunt about the floor: by the
#: end of level 5 everyone needs a +1 weapon, +1 armour and a +1 neck
#: item, and a +2 of each by level 10. Monster defences are set against
#: exactly that, so a party without it runs one to two points cold all
#: through heroic -- which `engine/scaling.py` cannot see, because it
#: models the *level* term on both sides and the *item* term on neither.
def band(level: int) -> int:
    """The enhancement bonus a character of this level is assumed to have."""
    return max(1, min(6, (level + 4) // 5))


def treasure(who: Character, rng: Random) -> list:
    """The three items the maths assumes, as `Magic` records.

    A weapon or an implement depending on what the class attacks with, a
    suit of armour, and something round the neck. Not a parcel table: the
    parcel rule is about what a party *finds* over a level of play, and
    what the arithmetic depends on is much simpler and much tighter.

    The base-item restriction is honoured rather than ignored, which is
    the owner's rule in force -- an item that says "Weapon: heavy blade
    or light blade" may only be laid on a heavy or light blade the
    character is actually carrying.
    """
    from combat_engine.db import game

    plus = band(who.level)
    carried = list(who.chosen.weapons or who.line.weapons)
    swung = next((w for w in carried if w.group != "implement"), None)
    held = next((w for w in carried if w.group == "implement"), None)
    # **Both, for a class that carries both.** A cleric attacks with a
    # mace on some rows and a holy symbol on most, and giving it only one
    # magic arm leaves half its card running a band cold -- which is
    # exactly the invisible shortfall this whole function exists to close.
    # The printed advice agrees: a weapon *and* an implement are separate
    # lines on the same list of what everybody needs.
    wanted = [("ac", None), ("defences", None)]
    for arm in (held, swung):
        if arm is not None:
            wanted.insert(0, ("attack_damage", arm))

    out = []
    for enh_to, arm in wanted:
        pool = [
            row
            for row in game().execute(
                "SELECT i.ref, i.slot, i.base, i.crit, s.plus FROM item i "
                "JOIN item_step s ON s.ref = i.ref "
                "WHERE i.enh_to = ? AND s.plus = ? AND s.level <= ? "
                "ORDER BY i.ref",
                (enh_to, plus, who.level + 1),
            )
            if _fits_base(row["base"], arm, who.line.armour)
        ]
        if not pool:
            continue
        row = _pick_item(pool, who.cls, rng)
        if row is None:
            continue
        magic = magic_for(
            row["ref"], plus=row["plus"], powers=_blocks_of(row["ref"])
        )
        if magic is None:
            continue
        if arm is held and arm is not None:
            magic = replace(magic, slot="implement")
        out.append(magic)
    return out


def _blocks_of(ref: str) -> tuple[str, ...]:
    """An item's own rows -- its Properties and its Powers -- in printed order.

    `Magic.powers` has always been documented as "the item's own rows ... which
    go into `Powers.known` while it is worn", and `equipment.equip` has read it
    since it was written. Nothing filled it: `treasure` called `magic_for` with
    no `powers=`, so every character was dealt the *numbers* of three magic
    items -- enhancement, critical rider, defence bonus, all columns `equip`
    reads directly -- and none of their text. 285 declared blocks across 64
    dealt characters, 0 of them in a power list. #448.

    **Only rows the tree declares.** `item_block` lists every printed Property
    and Power including the ones nobody has written, and a `Powers.known`
    holding a ref with no declared row is a card the engine cannot resolve.
    A declared row carrying a marker is granted and then refused by `usable`,
    which is right: the character does own that property, and the reason it
    does nothing is the marker rather than the grant.
    """
    from combat_engine.db import game
    from combat_engine.engine.dsl import REGISTRY

    rows = game().execute(
        "SELECT ref FROM item_block WHERE item_ref = ? ORDER BY idx", (ref,)
    )
    return tuple(r["ref"] for r in rows if r["ref"] in REGISTRY)


def _pick_item(pool: list, cls: str, rng: Random):  # noqa: ANN202
    """One item from the pool, weighted by what a guide thought of it.

    Camille's rule: **nothing rated below black**, and unrated items stay in the
    pool. Rated items are weighted by their score and unrated ones at `UNRATED`,
    so a recommendation is preferred without a slot ever emptying.

    **The effect today is very nearly nothing, and that is worth saying rather
    than discovering.** Item coverage is the thinnest part of `ratings.py`: a
    fighter's level-1 weapon slot is 124 candidates of which *one* is rated, and
    a warden has no rated item in any slot. Every rated item in those pools is
    already black or better, so the floor currently excludes nothing at all. One
    rated blue against 123 unrated is a 1.3% draw. This is scaffolding for when
    the guides' item coverage grows, not a lever that moves anything now.
    """
    if not USE_RATINGS:
        return pool[rng.randrange(len(pool))]
    from combat_engine.ratings import UNRATED, rating

    weighted = []
    for row in pool:
        got = rating(row["ref"], cls)
        if got is not None and got < BLACK:
            continue                     # a guide said not to take this
        weighted.append((row, UNRATED if got is None else got))
    if not weighted:
        # Every candidate was rated below black. Refusing outright would leave
        # the character a band cold, which is the shortfall `treasure` exists to
        # close, so the least-bad rated item is taken and nothing is silent.
        return max(pool, key=lambda r: rating(r["ref"], cls) or 0.0)
    total = sum(w for _r, w in weighted)
    cut = rng.random() * total
    for row, w in weighted:
        cut -= w
        if cut <= 0:
            return row
    return weighted[-1][0]


def magic_for(ref: str, *, plus: int = 0, powers: tuple[str, ...] = ()) -> Magic | None:
    """One **named** item, as a `Magic` record read off its own columns.

    The same columns `treasure` selects, asked of a ref instead of a slot.
    Split out because there are two callers now and only one of them is
    dealing treasure: anything that already knows which item it wants --
    a power body picking a thing off the floor, `scripts/audit.py`
    fielding the item a row belongs to -- needs the *printed* slot,
    `enh_to` and critical rider rather than a guess. Guessing them is not
    a small error: `enh_to="attack_damage"` on an item whose column says
    `ac` routes it through `_onto_weapon` instead of `_defence_mods`, so
    the armour bonus the item exists for is never laid at all.

    `plus` defaults to the bottom rung of the item's ladder, which is the
    heroic floor, and to 1 for an item with no ladder -- a body reading
    "equal to the enhancement bonus" wants a number either way.
    """
    from combat_engine.db import game

    row = game().execute(
        "SELECT i.ref, i.slot, i.crit, i.enh_to, i.base, "
        "(SELECT MIN(s.plus) FROM item_step s WHERE s.ref = i.ref) AS plus "
        "FROM item i WHERE i.ref = ?",
        (ref,),
    ).fetchone()
    if row is None:
        return None
    return Magic(
        ref=row["ref"],
        slot=row["slot"] or "",
        plus=plus or row["plus"] or 1,
        enh_to=row["enh_to"] or "",
        crit=_crit_dice(row["crit"]),
        powers=tuple(powers),
        base=_base_items(row["base"]),
    )


def _base_items(column: str | None) -> tuple[str, ...]:
    """The base-item restriction as a tuple. `["any"]` is no restriction."""
    import json

    try:
        names = json.loads(column or "[]")
    except ValueError:
        return ()
    return tuple(n for n in names if isinstance(n, str) and n != "any")


def _fits_base(printed: str, arm: Weapon | None, armour: str) -> bool:
    """Does this item go on what the character is actually carrying?

    An empty restriction goes on anything. Otherwise the printed line
    names base items -- "Heavy blade or light blade", "Chain, scale or
    plate" -- and the answer is whether one of them is the group, the
    category or the armour the character has. This is the whole of what
    makes a magic weapon "a longsword with properties" rather than a new
    weapon: the item says which longswords it may be.
    """
    named = [n.lower() for n in json.loads(printed or "[]")]
    if not named or "any" in named:
        return True
    if arm is not None:
        mine = {arm.group, arm.category, *arm.properties}
        return any(n in mine for n in named)
    return armour.lower() in named or any(armour.lower() in n for n in named)


def _crit_dice(printed: str) -> str:
    """The dice out of "+1d6 damage per plus".

    Only the dice: "per plus" is the multiplier and `equipment` applies
    it, and the damage type is dropped because a crit rider that types
    its damage is rare enough to be an item's own written block rather
    than something read off a column.
    """
    found = re.search(r"(\d+d\d+)", printed or "")
    return found.group(1) if found else ""


def spellbook(cls: str, level: int, prepared: list[str], held: int = 2) -> list[str]:
    """What a character owns and has not prepared.

    The same pool `loadout` drew from, minus what it dealt. A spellbook
    holds dailies and utilities -- an at-will is not prepared and a class
    feature is not a choice -- and `held` is how many per slot the chassis
    says, so the book is that many levels' worth of the ones left over.

    Drawn from the registry for the same reason the loadout is: a written
    list of ids goes stale the moment a row lands.
    """
    # Imported for the side effect: this is what registers the rows.
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    out: list[str] = []
    for slot in (Usage.DAILY, Usage.ENCOUNTER):
        spare = [
            p
            for p in REGISTRY.values()
            if p.cls == cls
            and 0 < p.level <= level
            and p.usage is slot
            and p.ref not in prepared
            # A utility is a row with nothing to attack with; an encounter
            # *attack* power is a slot the book has no say over.
            and (slot is Usage.DAILY or p.attack is None)
            # A second stat block is not a power to prepare on its own.
            and not second_card(p.ref)
        ]
        # The character's own level first. A swap is "another power of the
        # same level", so a book stocked from the bottom of the list has
        # nothing the top slot can trade for.
        spare.sort(key=lambda p: (-p.level, p.ref))
        out += [p.ref for p in spare[: max(0, held - 1)]]
    return out


def leg_named_by(p) -> str:  # noqa: ANN001
    """The build leg this row's own `requires=` names, or `""`.

    `features.on_leg` records the name on the gate it returns, so the leg
    is readable **without a character to ask** -- which is the whole point
    here, because the draw has no world and `Power.requires` is a
    mid-fight question. `audit._class_of_leg` already relies on the same
    field.

    Read rather than called, deliberately. Calling the gate needs a
    `World` and an entity id; the name is a string sitting on it.
    """
    gate = getattr(p, "requires", None)
    return getattr(gate, "leg", "") if gate is not None else ""


def _fits(p, build: Build) -> bool:  # noqa: ANN001
    """Is this power on the build's leg?

    **A declared leg wins over ability fit, and until `#1051` this function
    only asked about the ability** -- which is what its own first line has
    always claimed to be doing and was not. The gap was not academic:
    `cf:warlock-f1c10` declares `requires=on_leg("star")` and
    `requires_text="needs the pact that prints it"`, and it was dealt to
    19% of infernal and 14% of dark hands and **0%** of star ones, because
    it is a Constitution attack and those are the Constitution legs. The
    pact's own at-will went to six legs and never to its own.

    `Power.requires` is asked mid-fight, so the card was dealt and then
    refused in play -- a dead at-will in the hand, and for the ungated twin
    a card whose augment lines key off a remnant its holder cannot have.
    49 declared rows across 8 classes carry such a gate, so this is not a
    warlock problem.

    No attack line means no ability to be wrong about -- those are open to
    everybody, which is how a cleric of either leg still gets its heals.
    """
    leg = leg_named_by(p)
    if leg:
        # The row says which fork it belongs to, which is a stronger
        # statement than which ability it rolls: a pact's own card is for
        # that pact whether or not the ability happens to line up.
        return leg == build.name
    if p.attack is None or p.attack.ability is None:
        return True
    return p.attack.ability is build.primary


def _leans_on(declared, build: Build) -> int:  # noqa: ANN001
    """Does this row name the ability this build is good at?

    Read off the row's own source, which is the only place the dependency
    is written down -- a body saying `c.int_mod` needs Intelligence and no
    header field says so.
    """
    import inspect

    try:
        body = inspect.getsource(declared.body)
    except (OSError, TypeError):
        return 0
    return sum(f"c.{a.value}_mod" in body for a in (build.primary, build.secondary))


def launcher_for(kind: str) -> Weapon | None:
    """Something that looses that kind of ammunition, from the printed list.

    The cheapest proficiency band that fires it, so a character handed a
    quiver is not also handed a superior weapon it could not use. An
    empty kind -- the two ammunition items that name no base item -- gets
    a bow, which is what the commonest launcher is.
    """
    from combat_engine.engine.ammunition import FIRES

    wanted = {g for g, k in FIRES.items() if k == kind} or {"bow"}
    order = {"simple": 0, "military": 1, "superior": 2}
    pool = sorted(
        (w for w in PRINTED.values() if w.group in wanted),
        key=lambda w: (order.get(w.category, 3), w.ref),
    )
    return pool[0] if pool else None


@cache
def _build_for(cls: str, ref: str, scored: bool) -> str:
    """The build whose gear can actually hold this row.

    A class's builds carry different weapons -- a ranger on the two-blade leg
    owns no bow at all -- so a ranged row fielded on the wrong one is refused for a
    reason that has nothing to do with the row. Lives here rather than in a
    script because choosing a build is character creation, and two scripts
    were about to want it.

    **Cached, and it is the cheapest 13% in the sweep.** This probes each of
    the class's builds by spawning a throwaway character into a throwaway
    `World`, so one call is ~15ms, and `audit.board` calls it **once per
    board**. A row that never fires pays 48 boards -- `_attempts` only stops
    when something fires -- with the *same* `(cls, ref)` every time, so the
    answer was recomputed 48 times for one row. Measured: 144 calls and 2.23s
    over three silent rows, 13% of their total.

    Safe to memoise because it is a pure function of two strings **and the
    draw flag**: `BUILDS` is a module constant, `REGISTRY` is fixed once
    content has imported, the probe `World` is built with a fixed `Rng(1)`
    and discarded, and the return is a `str`.

    **`scored` is in the key and is otherwise unused, which is `#1082`.**
    This list used to end at "two strings", and the omission was not
    academic: `spawn` below is character creation, which reads
    `SCORED_CHOICES`, so the answer depends on it -- measured,
    `("ranger", "p1758")` is `hunter` scored and `marauder` unscored. With
    the flag outside the key, whichever draw mode asked a pair first won for
    the whole process and a caller in the other mode was answered from it.

    **And the old verification could not have caught it**: *"60 pairs, 0
    disagreements between two calls"* compared two calls in the **same**
    mode, and a cache insensitive to the mode agrees with itself perfectly.
    `drivers.draw_cache_key` asserts across the two modes now.

    **The parameter DRIVES the body, it is not only a key.** A first version
    left it key-only, reasoning that `spawn` reads the live global and
    `build_for` always passes that same value, so the two agree by
    construction. A plant refuted it: with the parameter inert,
    `_build_for(cls, ref, False)` called while the global is `True` computes
    the **scored** answer and files it under the unscored key -- the cache
    poisoned through its own front door, and invisible to any assertion that
    reads `build_for` alone. So the flag is pinned for the body and put
    back, which makes the key and the answer one claim.

    The pin is a **no-op in production**: `build_for` passes the live value,
    so it sets the flag to what it already is. It exists for a direct
    caller, which today is `drivers.draw_cache_key` asserting exactly this.
    `try/finally` covers every exit, including the early `return`.

    **Never cache a board or a `World`** -- `audit._run_all` requires each row
    to share nothing with any other, and a shared mutable world is the sweep
    flake that is hardest to find. This caches the *answer*, not the probe.
    """
    global SCORED_CHOICES

    was_drawn, SCORED_CHOICES = SCORED_CHOICES, scored
    try:
        from combat_engine.engine import Bus, Grid, Rng, World, usable
        from combat_engine.engine.dsl import get, unmet_requirement

        declared = get(ref)
        if declared is None:
            return ""
        # The build whose *secondary* ability the row leans on, first. Several
        # rows read "a number of squares equal to your Intelligence modifier",
        # and a warlord who took the other leg has Intelligence 10 -- so the row
        # does nothing, correctly, and reads as broken. The fork is exactly the
        # choice of which secondary is good; picking the wrong leg to test on
        # says nothing about the row.
        options = sorted(
            BUILDS.get(cls, ()),
            key=lambda b: -_leans_on(declared, b),
        )
        for build in options:
            probe = World(Grid(8, 8), Rng(1), Bus())
            who = spawn(
                probe, Character(cls, max(1, declared.level), [ref], build=build.name), (1, 1)
            )
            ok, _why = usable(probe, who, declared)
            if ok or not unmet_requirement(probe, who, declared):
                return build.name
        return ""
    finally:
        SCORED_CHOICES = was_drawn


def build_for(cls: str, ref: str) -> str:
    """The build whose gear can hold this row, under the live draw. #1082.

    **The public signature is unchanged on purpose.** Six callers across
    four layers ask `build_for(cls, ref)` and none of them knows or should
    know about `SCORED_CHOICES` -- it is a module global that
    `scripts/audit.py` sets and `drivers._board` pins and restores. So the
    flag is read here, at the boundary, and passed into the key; no call
    site moves and no `Cast` surface changes.

    See `_build_for` for why it has to be in the key at all.
    """
    return _build_for(cls, ref, SCORED_CHOICES)


def _is_class_heal(p) -> bool:  # noqa: ANN001
    """The leader's signature heal: a minor action, healing, twice a fight.

    It is a class feature printed at level 1 and does not spend a slot. A
    cleric choosing between healing the party and attacking anything is not
    a choice the book asks it to make.
    """
    from combat_engine.engine.types import ActionType, Keyword

    return (
        p.level <= 1
        and Keyword.HEALING in p.keywords
        and p.action is ActionType.MINOR
        and p.uses > 1
    )



def _shield_for(line: ClassLine, weapons: list[Weapon]) -> int:
    """A shield, unless what the build carries makes one impossible.

    `shield` is on the chassis, and the chassis is right about a class --
    a fighter is trained with one. It is wrong about a *build*: the
    great-weapon leg carries a greataxe and the tempest leg carries two
    blades, and neither of them has a hand left. Both were being given a
    heavy shield's +2 to AC and Reflex anyway, and the tempest leg was
    worse off than that -- `Gear.two_weapon` reads
    `len(melee) > 1 and not shield`, so a shield it could not be holding
    made every "wielding two melee weapons" Requirement false.

    Derived rather than declared: a new `Build.shield` field would have
    to be remembered on every future leg, and this cannot be forgotten.
    """
    melee = [w for w in weapons if not w.ranged and w.group != "implement"]
    if any("two-handed" in w.properties for w in melee) or len(melee) > 1:
        return 0
    return line.shield

def defences(line: ClassLine, scores: dict[Ability, int], level: int) -> dict:
    """The four defences, worked out rather than recorded.

    Light armour adds the better of Dexterity and Intelligence to AC; heavy
    armour adds neither. The other three take the better of their pair, and
    the class adds two to the one it is good at.

    **The level term is not here.** `engine/scaling.py` supplies it, so that
    turning the treadmill down turns it down for defences as well as attacks,
    from one place. `level` is still a parameter because retraining and
    score bumps depend on it.
    """
    from combat_engine.engine.types import modifier

    def mod(a: Ability) -> int:
        return modifier(scores.get(a, 10))

    shield = line.shield
    ac = 10 + line.armour_bonus + shield
    if line.armour in LIGHT:
        ac += max(mod(DEX), mod(INT))
    return {
        AC: ac,
        FORT: 10 + max(mod(STR), mod(CON)) + line.defences.get("fort", 0),
        REF: 10 + max(mod(DEX), mod(INT)) + shield + line.defences.get("ref", 0),
        WILL: 10 + max(mod(WIS), mod(CHA)) + line.defences.get("will", 0),
    }


def _from_class_list(db: sqlite3.Connection, printed: str,
                     rng: Random) -> set[str]:
    """One skill from the class list a feat names. 32 feats print this.

    `feat.trains_from` holds the printed words, unresolved, because four of
    the 32 name a **build** rather than a class -- "executioner assassin",
    "blackguard paladin", "cavalier paladin", "binder warlock". Deciding
    what to do about that is this function's job and not the extractor's.

    **The build case is deliberately refused, not approximated.** Taking
    the last word gives the parent class, whose list is a *superset* of the
    build's, so a character could be trained in a skill the card does not
    offer. One printed sentence silently becoming a wider one is the fault
    this repo keeps finding, so those four train nothing here and the rows
    keep a marker naming the sub-option gap. #548, #575.

    Matched case-insensitively against `class_skill.class`, like
    `_trained_skills` below and for the same #339 reason: the table's key
    is the printed word and `Character.cls` is a slug.
    """
    pool = sorted(_class_skill_pool(db, printed))
    return {rng.choice(pool)} if pool else set()


def _class_skill_pool(db: sqlite3.Connection, printed: str) -> set[str]:
    """Every skill on the class list a page names, by printed class word.

    Split out of `_from_class_list` so `_plus_race` can read the pool
    without also taking the draw: a race picking from the character's own
    list has to exclude what it already has, which means seeing the pool
    rather than one sample of it. #688.

    Empty for a build ("executioner assassin") or a class this build does
    not import -- never the parent's wider list, which is the narrowing
    `_from_class_list`'s docstring argues for.
    """
    rows = db.execute(
        "SELECT skill FROM class_skill WHERE lower(class) = ? ORDER BY skill",
        (printed.lower(),),
    ).fetchall()
    return {r["skill"] for r in rows}


def _trained_skills(cls: str, feats: list[str], rng: Random,
                    race: str = "",
                    wanted: Sequence[str] = ()) -> frozenset[str]:
    """Which skills this character is trained in: the given, plus the chosen.

    Off `class_skill`, which `etl/build.py` fills from the two sentences
    every class page prints -- "Trained Skills: Stealth, Thievery." and
    "Class Skills: ...". `granted=1` is the first sentence, `granted=0` the
    pool, and `class.skill_choices` is how many of the pool to take. #565.

    **And off the race, which was missing entirely.** Three racial traits
    print skill training -- `rt:r3-t0`, `rt:r7-t1`, `rt:r52-t3` -- and this
    was the only writer of `Skills.trained` with no race among its sources,
    so every character of those races was short one trained skill. That is
    **+5** on it (`skills.TRAINING`), and for `rt:r52-t3` it is +5 to
    Stealth, which `query.hidden_from` consumes inside a fight. #688.

    The three rows themselves stay inert and are not at fault: where
    training is granted is chargen and not a body, because the sheet is
    made before the board is.

    **Matched case-insensitively on purpose.** `Character.cls` is a slug
    (`"fighter"`) and the table's key is the printed word (`"Fighter"`),
    which is the same mismatch #339 is about. Asking `lower()` of both is
    what keeps this working either side of that rename.

    Ordered before it is sampled, and sampled from its own stream, so a
    character's training is settled by its seed and not by how many dice
    the fight has rolled. An unknown class trains in nothing rather than
    raising -- a monster has no entry here and is not meant to.
    """
    # **A pinned set is returned whole and the stream is not touched.**
    # `Character.skills` records what a previous deal produced, so there is
    # nothing left to draw -- and drawing anyway would be worse than
    # pointless here, because this function is the *last* reader of its own
    # `Random`: it is constructed per character in `spawn`
    # (`"{seed}:{ref}:{level}:skills"`) and nothing else reads it after.
    # So short-circuiting moves no other decision, which is the opposite of
    # the pool sample below -- see the note there.
    if wanted:
        return frozenset(wanted)

    from combat_engine.db import game

    db = game()
    # **The class and the race are settled first, which is the printed step
    # order and is what `#1135` moved.** Skills are step 4 of building a
    # character and feats are step 5, in that order precisely so that a
    # feat asking *"are you trained in Thievery"* has something to read.
    # Drawn through the same helper `spawn` calls before it picks the
    # feats, so the two cannot disagree about what the pool handed out:
    # same key, same stream, same prefix of draws.
    before = class_training(cls, race, rng, db=db)
    # **And the feats apply even to a class with no entry.** A multiclass
    # feat's "you gain training in Nature" is training the character has
    # however it was built, so this is not inside any class guard.
    from_feats: set[str] = set()
    for ref in feats:
        got = db.execute(
            "SELECT trains, trains_choice, trains_from FROM feat WHERE ref = ?",
            (ref,),
        ).fetchone()
        if got is None:
            continue
        # **Granted, chosen and chosen-from-a-list are three different
        # sentences**, and reading them all as the first would train one
        # character in every option a card offers a choice between --
        # three skills off `f1222`. #574.
        if got["trains"]:
            from_feats |= {s for s in got["trains"].split(",") if s}
        if got["trains_choice"]:
            offered = [s for s in got["trains_choice"].split(",") if s]
            if offered:
                # Its own draw from the same stream as the class pool
                # below, so a character's training stays settled by its
                # seed rather than by how many dice the fight has rolled.
                from_feats.add(rng.choice(sorted(offered)))
        if got["trains_from"]:
            from_feats |= _from_class_list(db, got["trains_from"], rng)
    # A feat training a skill the class also offers is one training, not
    # two -- the set does that for free -- and it does **not** buy a free
    # pick in exchange, which is the printed rule and is why the union
    # happens here rather than the pool being sampled from
    # `pool - from_feats`.
    return frozenset(before | from_feats)


def class_training(cls: str, race: str, rng: Random,
                   db: sqlite3.Connection | None = None) -> frozenset[str]:
    """The skills a character has **before it picks a feat**. #1135.

    Steps 2 and 4 of building a character: what the race trains it in, what
    the class grants outright, and what it chooses from the class's own
    list. Feats are step 5 and are added by `_trained_skills`.

    **Split out so one draw can serve two readers.** `spawn` needs this set
    *before* `feats_for`, because 67 of the 87 feats that say *"you must be
    trained in X"* name a skill a character **chooses** rather than one it
    is given -- so with the feats drawn first the question was unanswerable
    and those rows could never be dealt. Camille's call on `#1135`:

    > *"At first level, skills should be chosen before feats."*

    It is the same function and the same stream key both times, so the
    pre-feat answer and the final one cannot disagree about the pool: this
    is the identical prefix of draws off `"{seed}:{ref}:{level}:skills"`,
    and `_trained_skills` simply carries on from where this stopped.

    **What moved, and it is the cost Camille accepted when she called it.**
    The feat branch used to draw first, so putting the class sample ahead of
    it changes what the stream hands out and **every dealt character's
    skills change** -- not only the gated ones. A campaign party is
    unaffected: `Party.of` pins its training and the pinned path returns
    whole without touching the stream (`#1113`).

    **And `_plus_race` can no longer see the feats**, which is correct
    rather than a loss. Its *"one additional skill"* reading picks from what
    is left, and at step 2 a character has no feats to collide with -- so a
    feat that trains the same skill now wastes the feat's training rather
    than the race's. That is the direction the two cards already disagree
    in: the feat branch's own rule is that overlap buys no free pick, and
    the race's is that it does.
    """
    if db is None:
        from combat_engine.db import game

        db = game()
    rows = db.execute(
        "SELECT skill, granted FROM class_skill WHERE lower(class) = ?"
        " ORDER BY skill",
        (cls.lower(),),
    ).fetchall()
    if not rows:
        # An unknown class trains in nothing and takes no race pick either
        # -- which is what this did before the split, and is not a
        # behaviour worth changing here: the only caller with no
        # `class_skill` row is a monster, and a monster has no `race` ref,
        # so `_plus_race` would return the empty set regardless.
        return frozenset()
    row = db.execute(
        "SELECT skill_choices FROM class WHERE lower(name) = ?", (cls.lower(),)
    ).fetchone()
    picks = int((row["skill_choices"] if row else 0) or 0)
    given = {r["skill"] for r in rows if r["granted"]}
    pool = sorted({r["skill"] for r in rows if not r["granted"]} - given)
    chosen = set(rng.sample(pool, min(picks, len(pool))))
    # **The race last within this half**, which is `_plus_race`'s own first
    # reason and still holds: a draw taken before `rng.sample` would shift
    # the class picks.
    return frozenset(_plus_race(db, cls, race, given | chosen, rng))


@cache
def _race_skills(race: str) -> frozenset[str]:
    """The skills a race is **given** outright. No choice, so no rng.

    `race.trains` only, and **measured: one race, not the three that train
    anything.** `_trained_skills`' docstring names three racial traits and
    all three are real, but only `rt:r52-t3` is a *grant* -- `r52.trains`
    is `stealth`. The other two are picks: `r3` chooses one of seventeen
    skills and `r7` chooses from the character's own class list. A pick
    needs a stream, which is exactly the half `meets` cannot have, so a
    character of either answers on its class alone.

    Said at this length because "three racial traits train a skill" is
    true, and reading it as "three races contribute here" is wrong -- the
    first draft of this function did exactly that.

    **One reader, called by both `given_skills` and `_plus_race`'s granted
    branch**, so the two cannot answer differently about the same column.
    """
    from combat_engine.db import game

    if not race:
        return frozenset()
    got = game().execute(
        "SELECT trains FROM race WHERE ref = ?", (race,)).fetchone()
    if got is None or not got["trains"]:
        return frozenset()
    return frozenset(s for s in got["trains"].split(",") if s)


def _plus_race(db: sqlite3.Connection, cls: str, race: str,
               already: set[str], rng: Random) -> set[str]:
    """Add the race's printed training to a set already holding the rest.

    The same three branches `_trained_skills` reads a feat with, because
    `race.trains` / `trains_choice` / `trains_from` are the same three
    columns: granted, chosen-from-a-pool and chosen-from-a-class-list are
    three different sentences, and folding them would train one character in
    every option a page offers between -- #574 measured that on the feat
    side. #688.

    **Last, and the two reasons are different.**

    *It must not perturb the class sample.* A draw taken before
    `rng.sample` shifts it, so adding this moved which skills every elf and
    human got from their class list -- a second change, hidden inside the
    first. Taken here, the class picks are what they always were.

    *"One additional skill" means additional.* `rt:r7-t1` picks from the
    character's own class list, which is the pool the class just sampled, so
    a collision is the common case rather than the rare one -- and reading
    it as "no extra skill" would make the trait worth nothing to a human
    about half the time. So the choice is made from what is left.

    That is **not** how the feat branch behaves, deliberately: a feat
    training a skill the class also offers is one training and does not buy
    a free pick, which is the printed rule there and is documented where it
    happens. The difference is in the two cards, not in the two readers.
    """
    if not race:
        return already
    got = db.execute(
        "SELECT trains, trains_choice, trains_from FROM race WHERE ref = ?",
        (race,),
    ).fetchone()
    if got is None:
        return already
    out = set(already)
    # Granted outright: no choice to make, so a collision is just one
    # training rather than a wasted pick.
    #
    # Through `_race_skills` rather than re-splitting the column, so this
    # and `given_skills` -- which `chargen.meets` reads for the `skill`
    # prerequisite -- cannot disagree about what a race is *given*. #1113.
    out |= set(_race_skills(race))
    offered = [s for s in (got["trains_choice"] or "").split(",") if s]
    if got["trains_from"]:
        # `"class"` is the one value of that column which is not a printed
        # class: the page says "your class skills list" and names none,
        # because the character supplies it. See `race.trains_from`.
        printed = cls if got["trains_from"] == "class" else got["trains_from"]
        offered = sorted(_class_skill_pool(db, printed))
    left = sorted(set(offered) - out)
    if left:
        out.add(rng.choice(left))
    return out


def spawn(world: World, who: Character, square: tuple[int, int]) -> int:
    """Put a character on the board and return its entity id."""
    from combat_engine.engine.types import modifier

    line = who.line
    build = who.chosen
    # Its own stream, like the loadout's and the feats', and settled first
    # because everything below reads it: a race is two ability scores, a
    # size, a speed, a surge or two and a handful of rows.
    if DEAL_RACES and not who.race:
        who = replace(
            who,
            race=deal_race(
                Random(f"{world.rng.seed}:{who.cls}:{build.name}:race"),
                who.cls,
                build,
            ),
        )
    # **A revenant picks its second race, and only a revenant.** #1029.
    # `rt:r47-t1` prints *"Select a race other than r47"*, so the choice
    # is the trait's and has to be made for it: a field nothing fills is
    # the drawable-and-inert fault, and the trait would stay as dead as
    # the `_inert` marker it carries today.
    #
    # **Its own stream**, like the race's above and the deity's below, so
    # adding this draw moves no other decision's dice -- and keyed on the
    # race rather than on the class, because it exists only for one race
    # and a key naming the class would shift if the class list moved.
    #
    # `other_than=` rather than filtering afterwards: `deal_race`'s own
    # sample is weighted, and dropping a result after the draw would spend
    # a different number of values from the stream depending on what came
    # out, which is the hazard `_trained_skills` records about a pinned
    # set.
    if DEAL_RACES and who.race == SECOND_RACE_FROM and not who.race2:
        who = replace(
            who,
            race2=deal_race(
                Random(f"{world.rng.seed}:{who.race}:second-race"),
                who.cls,
                build,
                other_than=who.race,
            ),
        )
    # Its own stream, like the race's above and for the same reason: adding
    # this draw must not move the dice every other decision reads. `#454`.
    if DEAL_DEITY and not who.worships:
        who = replace(
            who,
            worships=deal_deity(
                Random(f"{world.rng.seed}:{who.cls}:{build.name}:deity"),
                who.cls,
            ),
        )
    # Its own stream again, for the third time and the same reason. `#1078`.
    if DEAL_BACKGROUND and not who.background:
        who = replace(
            who,
            background=deal_background(
                Random(f"{world.rng.seed}:{who.cls}:{build.name}:background"),
            ),
        )
    race = RACES.get(who.race)
    # **A copy each, always.** `LONGSWORD` and its siblings are module-level
    # singletons, so every fighter ever built shared one object -- and
    # `Cast.decay` reduces a magic weapon's enhancement *in place*. The
    # moment treasure exists, one character's sword rusting rusts every
    # sword in the game, in this fight and every later one, and nothing
    # anywhere would say so.
    carried = [replace(w) for w in (build.weapons or line.weapons)]
    scores = scores_for(line, build)
    if race is not None:
        for ability in race.taken(build):
            scores[ability] = scores.get(ability, 10) + 2
    # Level 4, 8 and so on raise two scores by one. Applied here rather than
    # recorded, so a level 8 character is derivable from its class and level.
    #
    # **Primary and secondary, which is Camille's ruling on `#1013`:**
    #
    #   > *"Almost always, the character should be improving their primary
    #   > and secondary abilities. The primary would be what their attack
    #   > rolls key off and the secondary is what their riders key off.
    #   > Adjust that for autogen."*
    #
    # This was `primary` and **CON**, which is a defensible house pick -- it
    # buys hit points and surges -- and not what the autogen should want: a
    # character's riders key off the secondary, so raising CON instead left
    # every rider a point behind for the whole paragon tier.
    #
    # No fallback needed and that was checked rather than assumed:
    # `Build.secondary` is not optional, and across all **99** declared
    # builds it is never unset and never equal to the primary.
    #
    # The printed rule lets a *player* pick any two; that half is the level-up
    # screen Camille also asked for, and it is `#1013`'s own remaining body.
    for step in (4, 8):
        if who.level >= step:
            scores[build.primary] += 1
            scores[build.secondary] += 1

    # Its own stream, like the loadout's and for the same reason: dealing
    # a character's feats must not move the dice the fight is about to
    # roll, or adding one would change every later roll in the game.
    # **Skills before feats, which is the book's own step order.** Steps 4
    # and 5, in that order precisely so a feat reading *"you must be
    # trained in Thievery"* has an answer. `#1135`, on Camille's call:
    #
    #   > *"At first level, skills should be chosen before feats."*
    #
    # The same key and the same helper `_trained_skills` uses below, so the
    # set the feats are judged against is the set the character ends up
    # with -- plus whatever the feats themselves train, which is additive.
    # A pinned character skips this: its training is already decided and
    # `Party.of` recorded it (`#1113`).
    #
    # **And it is settled before the hand now, not after it**, because a
    # skill power is drawn from the trained set (`#1162`). The book agrees --
    # skills are step 4 and powers step 7 -- and it costs no draw movement
    # of its own: this is a stream of its own on a key of its own, so
    # hoisting the call above the deal changes neither set.
    skills_key = f"{world.rng.seed}:{who.ref}:{who.level}:skills"
    before_feats = who.skills or sorted(
        class_training(who.cls, who.race, Random(skills_key))
    )
    # An empty power list means "deal me a hand", which is what both callers
    # want and what neither of them used to do: each kept its own list of
    # ids and both had gone stale. The draw is seeded off the fight, so the
    # same seed deals the same character, and off a stream of its own, so
    # dealing one does not move the dice the fight is about to roll.
    #
    # `trained` is passed rather than left to `dealt_hand`'s own derivation
    # because a **pinned** `Character.skills` has to win: a sheet dealt by
    # `Party.of` recorded its training, and re-deriving it here would hand
    # the board a character trained in one set and holding powers opened by
    # another.
    powers = who.powers or dealt_hand(
        world.rng.seed, who.cls, who.level, build, who_chassis=who.chassis,
        race=who.race, trained=before_feats,
    )
    feats = who.feats or feats_for(
        who.cls, who.level, build,
        Random(f"{world.rng.seed}:{who.cls}:{build.name}:feats"),
        list(powers), who.race,
        # **The pin when there is one, and the fresh draw otherwise.**
        # `#1113` answered this off a pinned set only, so a character dealt
        # from scratch passed nothing and 67 skill-gated feats could never
        # be dealt to one. `#1135` is the other half.
        skills=before_feats,
        # **Unlike skills, this one was always known by now**: the deal four
        # lines up settles it before the feats are drawn, which is the step
        # order skills now have too. `#454`.
        worships=who.worships,
    )
    # A feat that hands over a card takes one back, and both halves happen
    # here: a `Cast` opens on a board with the hand already dealt.
    #
    # `cls` and `level` because `Swap.pool` rows draw the **incoming**
    # power from the class list rather than being handed one. Passing them
    # cannot move an existing draw: every row that shipped before `#1114`
    # has `pool=""` and never reaches the branch that reads them.
    #: `option:<feat>:<power>` for each `Swap.pool` row, filled by the
    #: call below and spliced into `BuildState.choices` further down so
    #: the feat's body can read what it drew. #1114.
    swapped_in: set[str] = set()
    powers = power_swap(list(powers), list(feats), cls=who.cls,
                        level=who.level, record=swapped_in)
    # A race's traits and its one racial power are known rows like any
    # other: a trait arms itself at the top of the fight and a racial
    # power goes on the action menu, with no machinery of their own.
    # **Its own stream**, like the loadout's and the feats' above and for
    # the same reason: choosing which racial power a character carries must
    # not move the dice the fight is about to roll. The character still
    # changes -- that is the point, and #680 accepts the fixture re-record
    # it costs -- but it changes through the hand rather than through the
    # roll order. #680.
    racial = race.granted(
        Random(f"{world.rng.seed}:{who.race}:racial")
    ) if race is not None else []
    # Proficiency is the same kind of sentence, and it has to be settled
    # before the shield is, because what is in the other hand decides
    # whether there is room for one. A race trains a character in weapons
    # exactly as a feat does, and says so in the same header field.
    # A feat and a race both open weapons up through the same header field, and
    # only the feat cost a slot -- see `outfit`'s `spent`.
    #
    # **And a class feature does too, which this read two of the three lists
    # for.** A `cf:` row lands in `powers`, so `cf:rogue-scoundrel-f1s3`'s
    # `proficiency=("w3593", "w3596")` was dropped on the floor -- the reader
    # worked and was never reached. Priced like a race rather than a feat and
    # for the reason `outfit`'s `spent=` gives: only a feat costs a slot, so
    # only a feat's weapon may displace one the chassis already chose. #718.
    from_feats = proficiency(feats)
    from_race = proficiency([*racial, *powers])
    belt = outfit(
        carried,
        [*from_feats, *from_race],
        powers,
        spent={w.ref for w in from_feats},
    )
    # **A feat's armour proficiency widens the chassis's, and this is where
    # it lands.** `#568`: two rows are dealt with the clause inert because
    # nothing read it. The shield goes through `_shield_for` on a widened
    # line rather than past it, so a feat cannot hand a shield to a
    # character whose hands are full -- that rule stays in one place.
    opened_armour, opened_shield = armour_opened(list(feats))
    carried_shield = _shield_for(
        replace(line, shield=max(line.shield, opened_shield)), carried
    )

    # First level takes the whole Constitution *score*; every level after
    # takes the class's flat step. Surges take the modifier, not the score.
    con = modifier(scores[CON])
    max_hp = line.hp_first + scores[CON] + line.hp_per_level * (who.level - 1)
    # Heavy armour costs a square whatever the character is, so the race's
    # printed speed is what the penalty comes off -- a 5-square race in
    # scale walks 4. Raceless is the 6 it has always been.
    speed = race.speed if race is not None else 6

    eid = world.spawn(
        Ident(ref=who.ref, role=line.role),
        Position(square=square, size=race.size if race is not None else Size.MEDIUM),
        Side(team=who.team),
        Stats(level=who.level, scores=scores),
        Defenses(values=defences(replace(line, shield=carried_shield), scores, who.level)),
        Health(
            max_hp=max_hp,
            surges=line.surges + con + (race.surges if race is not None else 0),
        ),
        Movement(
            # **Off the table, not a pair of names.** This read
            # `in ("scale", "plate")` and the page gives chainmail a -1 as
            # well, so every chainmail-wearing character has been moving one
            # square too fast. #452.
            speed=speed + ARMOUR_SPEED.get(line.armour, 0),
            modes=dict(race.modes) if race is not None else {},
        ),
        # Level term via scaling.
        Initiative(
            bonus=modifier(scores[DEX]) + (race.initiative if race is not None else 0)
        ),
        Conditions(),
        Mods(),
        Budget(),
        # Every character can make a ranged basic attack if it is holding
        # something to make it with; `can_branch` refuses the row to anyone
        # who is not. A monster leaves this empty -- its ranged attacks are
        # its own printed rows.
        Powers(
            known=[*powers, *feats, *racial],
            ranged="rba",
            owned=spellbook(who.cls, who.level, list(powers), line.spellbook)
            if line.spellbook
            else [],
        ),
        # Everybody has one action point and may spend one a fight. A row
        # that hands out a second says so; the pool is not a class feature.
        ActionPoints(points=1),
        # **Plus the arms the build settled on**, as `chose:<ref>`, beside the
        # leg's name the way `element:` and `beast:` sit there -- a build-time
        # choice with a `Cast` reader and no component of its own.
        #
        # "You select two weapons as your X weapons" is the printed sentence,
        # and it cannot be answered in a fight: the gear is already in hand
        # when the first round opens. What is *held at spawn* is the
        # selection, and deliberately not `Gear.weapons` read live --
        # `c.draw` takes a stowed weapon up mid-fight, so a reader over the
        # hand would be a gate that cannot be false.
        #
        # **`chose:` and not `weapon:`**, which was the first spelling:
        # `Gear.bands` already uses `weapon:<slug>` for a class whose page
        # names weapons one at a time, and two keys that differ only in which
        # identifier they carry is the kind of near-collision that gets read
        # as the same fact. #719.
        # **And the sub-choices the taken rows ask for**, as
        # `option:<ref>:<value>`, from the same reasoning one step on: a
        # feat printing "choose necrotic or cold" asks a question that has
        # no moment in a fight either, because the feat was taken before
        # the character walked in. #758.
        BuildState(
            choices={
                *who.choices,
                *(f"chose:{w.ref}" for w in carried),
                # The hand as well as the feats: a class feature or an
                # item power may ask a build-time question too, and
                # reading only `feats` meant three of `#1112`'s ten
                # claimants could never be answered.
                # **Its own keyed stream**, so a drawn option cannot move
                # the dice the fight is about to roll -- the rule every
                # dealer above follows. Without it `_build_options` takes
                # the first printed option, which is what it did before
                # anything could act on the answer. #1085.
                *_build_options(
                    [*feats, *powers],
                    Random(f"{world.rng.seed}:{who.cls}:build-option"),
                ),
                # The pool draw above, under the same `option:` key, so
                # one reader (`Cast.chosen_option`) answers both. #1114.
                *swapped_in,
            }
        ),
        # **Training, which nothing recorded until #565.** Its own stream,
        # like the loadout's and the gear's, so which skills a character is
        # trained in is a property of its seed rather than of how many dice
        # the fight has rolled by the time it is spawned.
        Skills(
            trained=_trained_skills(
                who.cls,
                feats,
                # **A fresh stream on the same key as the pre-feat draw
                # above.** Both start from the same place and the class
                # half is the same prefix of draws, so the set the feats
                # were judged against is the set the character keeps.
                # #1135.
                Random(skills_key),
                who.race,
                # **The pin, and it is why this seed no longer decides a
                # campaign character's training.** The stream above is keyed
                # on `world.rng.seed` -- the *fight's* seed -- so without a
                # pinned set a party re-rolled its skills every encounter.
                # Measured: 4 of 4 fully-pinned characters differed across
                # four fight seeds. `Party.of` deals this once and
                # `Sheet.character` hands it back, exactly as `#1101` did
                # for the kit.
                who.skills,
            )
        ),
        Gear(
            weapons=carried,
            # **The kind, not merely whether.** `_shield_for` already
            # returns 0, 1 or 2 and this used to `bool()` it, which is where
            # nine rows' "your shield bonus" went missing. See `Gear.shield`.
            shield=carried_shield,
            # The heaviest of what the chassis trains in and what the
            # feats opened up. `_heaviest` picks by printed word, so
            # joining them is the whole of the comparison. `#568`.
            armour=_heaviest(" ".join([line.armour, *sorted(opened_armour)])),
            # **What this character is trained with**, which nothing recorded
            # before: the chassis's printed lines, plus what its feats and its
            # race opened up. `_attack_bonus` was awarding a weapon's
            # proficiency for merely holding it, so a superior weapon -- whose
            # entire cost is a feat -- was free. #242.
            trained=frozenset(
                w.ref for w in (*line.weapons, *carried, *belt,
                                *from_feats, *from_race)
            ),
            # **And what the page allows, not just what was dealt.** The two
            # answer different questions and #285 is the gap between them:
            # `trained` is this character's own weapons, `bands` is its
            # class's printed proficiency line, so a human picking a
            # different military weapon gets the bonus the book grants.
            bands=line.bands,
        ),
    )
    # Owned, not held. `Gear.__post_init__` works the grip out from an
    # empty `stowed`, so what a feat let the character carry but not swing
    # is added afterwards -- adding it above would have it counted as a
    # hand in use.
    if belt:
        gear = world.get(eid, Gear)
        gear.weapons += [replace(w) for w in belt]
        gear.stowed |= {w.ref for w in belt}
    # **Ordinary ammunition for whatever launcher it owns.** Camille's
    # ruling on #520, 2026-10-28 -- 50 pieces, a supplied number because the
    # page prints none for a character. `ammunition.MUNDANE` carries the
    # quote and the reasoning.
    #
    # **Owned, not held**, and after the belt for the same reason the belt
    # is: a crossbow a feat bought and stowed still has bolts for it, and a
    # character that fires nothing gets nothing. Keyed off the launcher's
    # own group through `FIRES`, which is the printed table -- a bow takes
    # arrows and a crossbow does not -- so no vocabulary is invented here.
    #
    # `ref=""` is what makes a mundane piece mundane: `nock` returns the
    # drawn piece's ref onto `ev.ammo`, and an empty one is the honest
    # answer that no *item* rode the shot, which is what `fired_with`
    # already reads. The count still comes down, which is the whole of #520.
    _stock_quiver(world.get(eid, Gear))
    # The thrown half of the same ruling, 5 rather than 50. Not folded into
    # the call above: the quiver is one entry per kind of ammunition and
    # this is one count per weapon, which are different keys for the reason
    # `_stock_thrown` gives.
    _stock_thrown(world.get(eid, Gear))
    # Two consumables on the person, Camille's ruling on #1233. **Its own
    # stream**, like the race's and the feats' above, and that is not
    # decoration: a shared stream would move every draw downstream of it,
    # so dealing potions would silently re-roll the skills and the feats of
    # every character in the tree and cost a replay re-record for a change
    # that adds to the margin. A dedicated key means this adds a hand and
    # moves nothing else.
    #
    # **`who.carried` wins when it is given**, which is `#1101`'s rule one
    # field over: a pinned list is a record of what the party is holding
    # and must not be re-dealt, or a party walks into every encounter with
    # different potions and a drunk one comes back. `story.Party.of` is
    # what pins it. Dealt here only when nothing pinned it, which is every
    # single-encounter caller -- the audit board, `fight.py`, `winrate`.
    _stock_consumables(
        world.get(eid, Gear),
        world.get(eid, Powers),
        who.level,
        Random(f"{world.rng.seed}:{who.cls}:{build.name}:consumables"),
        pinned=who.carried,
    )
    # A racial skill bonus is a sheet number and not a thing that happens
    # in a fight, so it is laid straight into `Mods` where the armour
    # penalty and the enhancement bonus already live -- `engine/skills.py`
    # reads `skill:<name>` off exactly this list. A trait row could not say
    # it: a row is armed at the top of an encounter and a skill check is
    # rolled outside one.
    #
    # **Still `Mods` now that `Skills` exists, and deliberately.** That
    # component is *training* -- a yes or no worth a flat 5 -- and a racial
    # +2 is a bonus on top of it. They add, so they are different stores;
    # folding the race in would have made a trained dwarf and an untrained
    # one indistinguishable.
    if race is not None and race.skills:
        from combat_engine.engine.components import Mod

        mods = world.get(eid, Mods)
        for skill, value in race.skills:
            mods.items.append(
                Mod(what=f"skill:{skill}", value=value, kind="racial", label=race.ref)
            )
    # **The background's +2, in `Mods` for every reason the racial bonus
    # is**: it is a sheet number rather than a thing that happens in a
    # fight, `engine/skills.py` reads `skill:<name>` off exactly this list,
    # and a row could not say it because a row arms at the top of an
    # encounter while a skill check is rolled outside one. `#1078`.
    #
    # `kind="background"` and not `"racial"`, so the two are
    # distinguishable on a sheet and so a later house rule can switch one
    # off without the other.
    if who.background:
        from combat_engine.engine.components import Mod as _Mod

        skill = background_skill(who.background)
        if skill:
            # `need`, not `get`: the latter is `Mods | None` and the
            # attribute read is a `types` diagnostic the baseline does not
            # hold. `spawn` added `Mods()` above, so there is one.
            world.need(eid, Mods).items.append(
                _Mod(what=f"skill:{skill}", value=BACKGROUND_BONUS,
                     kind="background", label=who.background)
            )
    if line.power_points:
        world.add(eid, PowerPoints(points=line.power_points, maximum=line.power_points))
    # Gear last, so it has a `Gear` and a `Mods` to write into. Its own
    # stream again -- dealing treasure must not move the fight's dice.
    # **The pinned kit if the caller brought one, dealt here if not.** Exactly
    # the shape of `who.powers or dealt_hand(...)` above, and for the identical
    # reason -- `Party.of`'s own docstring says it about the hand:
    #
    #     The hand is dealt once, now, off `seed` rather than off whichever
    #     fight the party walks into [...] so leaving it to the fight meant a
    #     party that changed shape between two encounters.
    #
    # Gear was left out of that fix. `world.rng.seed` is the FIGHT's seed, so
    # a party walked into every encounter with a different kit -- measured
    # over four fights in one day, **zero item overlap** -- which silently
    # refreshed every item daily and made `story._wear`'s `spent` filter drop
    # every item spend as belonging to a row the character no longer held.
    # #1101.
    for magic in (who.gear or treasure(
            who, Random(f"{world.rng.seed}:{who.ref}:{who.level}:gear"))):
        equip(world, eid, magic)
    place(world, eid, square)
    return eid


def sheet(who: Character) -> str:
    """Every number a player would have written down. For reading, not play.

    **The scores are built the way `spawn` builds them, and this used to
    read `dict(line.scores)` raw.** That is the class page's own
    recommendation, which is three transformations short of what a dealt
    character actually has: `scores_for` re-ranks it onto the build's leg
    and swaps in `STANDARD_ARRAY`'s values, the race adds its +2, and
    levels 4 and 8 each raise two scores. So the sheet a human reads
    disagreed with the character the engine fields -- every ability, its
    modifier, the hit points off CON, the surges off CON and all four
    defences.

    `#793`'s item 6, and the only plain bug in that issue. The three steps
    are copied from `spawn` rather than factored out of it deliberately:
    extracting them would put a second caller on a path the fixtures pin,
    and this function fields nothing. If they drift, `drivers.chargen_sheet`
    is what says so -- it asserts this against a really-spawned creature
    rather than against a second copy of the arithmetic, because a
    comparison against a re-derivation would pass while both halves were
    wrong together.

    **The skills line prints `-` for a character whose skills are not
    pinned, and that is correct rather than missing.** `Character.skills` is
    an input: `spawn` writes the dealt set into the creature's `Skills`
    component and never writes back to the `Character`. Deriving them here
    is not available either -- `_trained_skills` takes the fight's `Random`,
    so the *chosen* half of a character's training is only decided at spawn.
    So a pinned character -- the `maker.interview` path, which is what this
    function is for -- names its skills, and a dealt one says `-`.
    """
    from combat_engine.engine.types import modifier

    line = who.line
    build = build_of(who.cls, who.build)
    race = RACES.get(who.race) if who.race else None
    scores = scores_for(line, build)
    if race is not None:
        for ability in race.taken(build):
            scores[ability] = scores.get(ability, 10) + 2
    # Primary and secondary, the same as `spawn` -- Camille's `#1013` ruling,
    # quoted in full there. The two have to agree or the sheet a human reads
    # describes a different character from the one on the board.
    for step in (4, 8):
        if who.level >= step:
            scores[build.primary] += 1
            scores[build.secondary] += 1
    con = modifier(scores[CON])
    d = defences(line, scores, who.level)
    step = who.level // 2  # what scaling adds at full strength
    return "\n".join(
        [
            f"{who.ref}  level {who.level}",
            "  " + "  ".join(f"{a.value.upper()} {v} ({modifier(v):+d})"
                             for a, v in scores.items()),
            f"  HP {line.hp_first + scores[CON] + line.hp_per_level * (who.level - 1)}"
            f"   surges {line.surges + con}",
            f"  AC {d[AC] + step}  Fort {d[FORT] + step}  "
            f"Ref {d[REF] + step}  Will {d[WILL] + step}"
            + (f"   (level adds {step:+d}, off under bounded scaling)" if step else ""),
            f"  {line.armour}"
            + ("  heavy shield" if line.shield == 2 else "  light shield" if line.shield else "")
            + (f"  {line.weapon.damage} weapon (+{line.weapon.proficiency} prof)"
               if line.weapon else "  implement"),
            f"  powers: {', '.join(who.powers) or '-'}",
            # **Both of these were missing, and both are things a player
            # writes down.** `#793` item 2 is about choosing skills and
            # this is the half that only had to be printed.
            f"  feats: {', '.join(who.feats) or '-'}",
            f"  skills: {', '.join(sorted(who.skills)) or '-'}",
        ]
    )
