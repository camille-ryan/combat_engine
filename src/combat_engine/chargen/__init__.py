"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

All eight Player's Handbook classes, to level 10.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from random import Random

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
    Stats,
    Team,
    Weapon,
    World,
)
from combat_engine.engine import Build as BuildState
from combat_engine.engine.equipment import equip
from combat_engine.engine.movement import place
from combat_engine.engine.types import Usage

#: Armour, by the bonus it gives. Light armour also takes a modifier.
ARMOUR = {"cloth": 0, "leather": 2, "hide": 3, "chain": 6, "scale": 7, "plate": 8}

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
                   group="heavy blade")
MACE = Weapon(ref="w3596",
              category="simple", damage="1d8", proficiency=2, group="mace")
DAGGER = Weapon(ref="w3594",
                category="simple", damage="1d4", proficiency=3, group="light blade",
                thrown=(5, 10),
                properties=frozenset({"light blade", "off-hand"}))
SHORTSWORD = Weapon(ref="w3611",
                    category="military", damage="1d6", proficiency=3,
                    group="light blade",
                    properties=frozenset({"light blade", "off-hand"}))
LONGBOW = Weapon(ref="w3631",
                 category="military", damage="1d10", proficiency=2, group="bow",
                 ranged=(20, 40), properties=frozenset({"two-handed"}))
CROSSBOW = Weapon(ref="w3629", category="simple", damage="1d8", proficiency=2,
                  group="crossbow", ranged=(15, 30),
                  properties=frozenset({"two-handed"}))
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
                     proficiency=3, group="unarmed",
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

IMPLEMENTS = {w.ref: w for w in (ROD, ORB, HOLY_SYMBOL, STAFF, TOTEM, WAND, KI_FOCUS)}


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


def _with_slugs() -> None:
    """Give the hand-written constants the slug the table holds for them.

    **The constants are what a character actually carries**, not a fallback --
    `ClassLine.weapons` references them by name -- so they need every field a
    gate reads. `Weapon.slug` is the printed word a card can name a weapon by,
    and `chargen.meets`' `weapon_prof` test and `query.holding` both ask for it.

    It is **not written beside them**, because a slug is a printed name and the
    constants are tracked source. Read off the `weapon` table instead, which is
    where the name belongs and the only place it is kept.

    Measured when it was missing: four rows went from usable to *never usable
    here* -- `audit.py` read 776 against a watermark of 772 -- because their
    printed Requirement names one weapon and nothing on the character could
    answer which weapon it was holding. That is the whole reason this exists; a
    `slug=""` on a dealt weapon is a silently un-gateable row.

    **Set in place rather than rebound.** `CLASSES` and `IMPLEMENTS` are built
    above this and hold the constant *objects*, so replacing the module globals
    with copies left every one of those references on the slugless original --
    which looked fixed from the outside and was not. `Weapon` is not frozen, so
    one assignment reaches every holder.
    """
    for value in list(globals().values()):
        if not isinstance(value, Weapon) or value.slug:
            continue
        table = PRINTED.get(value.ref)
        if table is not None and table.slug:
            value.slug = table.slug
        elif value.ref.startswith("w:"):
            # **An implement, and the ref already is the word.** The compendium's
            # weapon table carries no implements -- an orb has no damage die and
            # no proficiency bonus -- so these refs were invented here, out of
            # words that are in `sanitise.RULES_TERMS` and are mechanics. Taking
            # the slug from the ref writes no new name down.
            value.slug = value.ref.removeprefix("w:")


_with_slugs()

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
STANDARD_ARRAY = (16, 14, 14, 13, 10, 8)


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
    "wizard": (Build("control", INT, WIS), Build("war", INT, DEX)),
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
        # The third of the four printed sources, and the last to get a
        # leg: two of the four had one and the fourth still has none --
        # `cf:sorcerer-soul-rest` says why. Dexterity because that is the
        # modifier its own damage clause spends. Last, so that a sorcerer
        # that names no build is the one it has always been.
        Build("f0s2", CHA, DEX),
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
        "dragon": "b:c128-2",
        "f0s2": "b:c128-3",
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
    ordered = [build.primary, build.secondary]
    ordered += [a for a in line.scores if a not in ordered]
    for ability, value in zip(ordered, values, strict=False):
        out[ability] = value
    return out


#: A race's page, the way `ClassLine` is a class's.
#:
#: Every number is read off the `race` table -- the size and the ability
#: scores are columns, and the speed, the fly speed, the skill bonuses and
#: the healing-surge step are parsed out of the printed block the way
#: `content/loader.py` parses a companion's. Nothing here is transcribed:
#: a hand-typed +2 is a number nothing can check, and a wrong one leaves
#: every power working and the character quietly wrong.
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
    #: Is that list a **choice**? Six races print more than one and four of
    #: those say "choose one of the following" -- and the difference
    #: matters: one race gets two powers and one gets one of thirteen.
    one_of: bool

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

        return sorted(r for r in REGISTRY if r.startswith(f"rt:{self.ref}-"))

    def granted(self) -> list[str]:
        """The rows a character of this race carries into a fight.

        Its traits, and its racial powers -- or **one** of them where the
        block says to choose, which is the difference between a race that
        prints two powers and one that prints thirteen manifestations and
        asks for one.
        """
        from combat_engine.engine.dsl import REGISTRY

        written = [p for p in self.powers if p in REGISTRY]
        return [*self.traits, *(written[:1] if self.one_of else written)]

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
            powers=tuple(
                dict.fromkeys(
                    [
                        ref
                        for ln in spec.splitlines()
                        if "power" in ln.lower()
                        for ref in _RACIAL_POWER.findall(ln)
                        if ref in cards.get(row["ref"], ())
                    ]
                    + cards.get(row["ref"], [])
                )
            ),
            one_of=any(word in spec.lower() for word in _ONE_OF),
        )
    return out


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
SCORED_CHOICES = True

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


def deal_race(rng: Random, cls: str = "", build: Build | None = None) -> str:
    """A race, drawn like a hand of powers is.

    **Weighted towards the ones whose scores suit the class, and not decided
    by them.** This used to be uniform over all 46, and its own docstring gave
    the reason to keep some of that: a player picks for flavour at least as
    often as for the numbers, and a draw that always took the best pair would
    make every fighter the same two races. So the score ranks and `sample`
    draws -- a Strength race is likelier for a fighter and never certain.

    `cls` is optional so the old one-argument call still answers; without it
    there is no build to score against and the draw stays uniform.
    """
    pool = sorted(RACES)
    if not pool:
        return ""
    if not SCORED_CHOICES or not cls:
        return rng.choice(pool)
    from .choices import race_options, sample

    drawn = sample(race_options(cls, build=build), rng)
    return drawn.ref if drawn is not None else rng.choice(pool)


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
    #: See `DEAL_RACES` for why one is not dealt to a character that names
    #: none.
    race: str = ""

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
    cls: str, level: int = 1, build: Build | None = None, rng: Random | None = None
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
    """
    # Imported for the side effect: this is what registers the rows.
    import combat_engine.content
    from combat_engine.engine.dsl import REGISTRY

    pick = rng or Random(0)
    build = build or build_of(cls)
    mine = [p for p in REGISTRY.values() if p.cls == cls]
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
    from combat_engine.engine.types import Keyword as _Kw

    out = sorted(p.ref for p in mine
                 if p.level == 0 and _Kw.BLADESPELL not in (p.keywords or ()))
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
    for at in UTILITY_GAINS:
        if at <= level:
            out += deal(at, None, 1)
    return out + sorted(r for ref in out for r in riders.get(ref, []))


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
        return node["race"] == who.race
    if "ref" in node:
        return node["ref"] in powers
    if "weapon_prof" in node:
        wanted = node["weapon_prof"].lower()
        return any(
            # `slug`, not the ref -- see `Weapon.slug`. The ref is the
            # compendium id now and un-slugging it would match nothing. #339.
            wanted in (w.group, w.category, w.slug.replace("-", " "))
            for w in who.line.weapons
        )
    # term, skill, source: nothing on a character answers them yet.
    return False


def feats_for(
    cls: str, level: int = 1, build: Build | None = None,
    rng: Random | None = None, powers: list[str] | None = None,
    race: str = "",
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
        legal = legal_feats(cls, level, build, race_ref, taken=held + taken)
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
    """
    from combat_engine.engine.dsl import REGISTRY

    out: dict[str, Weapon] = {}
    for ref in feats:
        declared = REGISTRY.get(ref)
        for want in getattr(declared, "proficiency", ()) or ():
            arm = PRINTED.get(want) or IMPLEMENTS.get(want)
            if arm is not None:
                out.setdefault(arm.ref, arm)
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
    held: list[Weapon] = []
    for role, arms in sorted(pool.items()):
        ranked = wield_options(arms, bought, list(known))
        order = {choice.ref: i for i, choice in enumerate(ranked)}
        arms.sort(key=lambda w: (order.get(w.ref, len(order)), w.ref))
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


def power_swap(powers: list[str], feats: list[str]) -> list[str]:
    """The hand that is left after the feats that trade a card for one.

    "You can swap one of your 3rd-level or higher encounter attack powers
    for this one" is an exchange made when the character is built. The
    card arrives with the feat -- its body hands it over -- and this is
    the other half: something goes back.

    The **lowest** qualifying power goes, which is the one a player gives
    up, and ties break by ref so that the same seed deals the same
    character twice. A feat whose trade finds nothing to take costs
    nothing, which is what happens to a character too junior to have one.
    """
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
        if pool:
            out.remove(min(pool, key=lambda p: (REGISTRY[p].level, p)))
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


def _fits(p, build: Build) -> bool:  # noqa: ANN001
    """Is this power on the build's leg?

    No attack line means no ability to be wrong about -- those are open to
    everybody, which is how a cleric of either leg still gets its heals.
    """
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


def build_for(cls: str, ref: str) -> str:
    """The build whose gear can actually hold this row.

    A class's builds carry different weapons -- a ranger on the two-blade leg
    owns no bow at all -- so a ranged row fielded on the wrong one is refused for a
    reason that has nothing to do with the row. Lives here rather than in a
    script because choosing a build is character creation, and two scripts
    were about to want it.
    """
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
    for step in (4, 8):
        if who.level >= step:
            scores[build.primary] += 1
            scores[CON] += 1

    # An empty power list means "deal me a hand", which is what both callers
    # want and what neither of them used to do: each kept its own list of
    # ids and both had gone stale. The draw is seeded off the fight, so the
    # same seed deals the same character, and off a stream of its own, so
    # dealing one does not move the dice the fight is about to roll.
    powers = who.powers or loadout(
        who.cls, who.level, build, Random(f"{world.rng.seed}:{who.cls}:{build.name}")
    )
    # Its own stream, like the loadout's and for the same reason: dealing
    # a character's feats must not move the dice the fight is about to
    # roll, or adding one would change every later roll in the game.
    feats = who.feats or feats_for(
        who.cls, who.level, build,
        Random(f"{world.rng.seed}:{who.cls}:{build.name}:feats"),
        list(powers), who.race,
    )
    # A feat that hands over a card takes one back, and both halves happen
    # here: a `Cast` opens on a board with the hand already dealt.
    powers = power_swap(list(powers), list(feats))
    # A race's traits and its one racial power are known rows like any
    # other: a trait arms itself at the top of the fight and a racial
    # power goes on the action menu, with no machinery of their own.
    racial = race.granted() if race is not None else []
    # Proficiency is the same kind of sentence, and it has to be settled
    # before the shield is, because what is in the other hand decides
    # whether there is room for one. A race trains a character in weapons
    # exactly as a feat does, and says so in the same header field.
    # A feat and a race both open weapons up through the same header field, and
    # only the feat cost a slot -- see `outfit`'s `spent`.
    from_feats = proficiency(feats)
    from_race = proficiency(racial)
    belt = outfit(
        carried,
        [*from_feats, *from_race],
        powers,
        spent={w.ref for w in from_feats},
    )
    carried_shield = _shield_for(line, carried)

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
            speed=speed - 1 if line.armour in ("scale", "plate") else speed,
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
        BuildState(choices=set(who.choices)),
        Gear(
            weapons=carried,
            shield=bool(carried_shield),
            armour=line.armour,
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
    # A racial skill bonus is a sheet number and not a thing that happens
    # in a fight, so it is laid straight into `Mods` where the armour
    # penalty and the enhancement bonus already live -- there is no
    # `Skills` component and `engine/skills.py` reads `skill:<name>` off
    # exactly this list. A trait row could not say it: a row is armed at
    # the top of an encounter and a skill check is rolled outside one.
    if race is not None and race.skills:
        from combat_engine.engine.components import Mod

        mods = world.get(eid, Mods)
        for skill, value in race.skills:
            mods.items.append(
                Mod(what=f"skill:{skill}", value=value, kind="racial", label=race.ref)
            )
    if line.power_points:
        world.add(eid, PowerPoints(points=line.power_points, maximum=line.power_points))
    # Gear last, so it has a `Gear` and a `Mods` to write into. Its own
    # stream again -- dealing treasure must not move the fight's dice.
    for magic in treasure(who, Random(f"{world.rng.seed}:{who.ref}:{who.level}:gear")):
        equip(world, eid, magic)
    place(world, eid, square)
    return eid


def sheet(who: Character) -> str:
    """Every number a player would have written down. For reading, not play."""
    from combat_engine.engine.types import modifier

    line = who.line
    scores = dict(line.scores)
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
        ]
    )
