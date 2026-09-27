"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

All eight Player's Handbook classes, to level 10.
"""

from __future__ import annotations

import json
import re
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
    #: Power points at first level, for a class that augments its powers.
    #: **Only the first-level number is settled.** `game.db` carries no
    #: power point column and the by-level table is not in it, so this does
    #: not grow with level; raising it is one number when the table lands.
    power_points: int = 0
    #: How many rows a slot holds in the spellbook -- what a wizard owns
    #: per prepared power. 0 for a class that prepares nothing.
    spellbook: int = 0

    @property
    def armour_bonus(self) -> int:
        return ARMOUR.get(self.armour, 0)

    @property
    def weapon(self) -> Weapon | None:
        return self.weapons[0] if self.weapons else None


LONGSWORD = Weapon(ref="w:longsword", category="military", damage="1d8", proficiency=3,
                   group="heavy blade")
MACE = Weapon(ref="w:mace", category="simple", damage="1d8", proficiency=2, group="mace")
DAGGER = Weapon(ref="w:dagger", category="simple", damage="1d4", proficiency=3, group="light blade",
                properties=frozenset({"light blade", "off-hand"}))
SHORTSWORD = Weapon(ref="w:short-sword", category="military", damage="1d6", proficiency=3,
                    group="light blade",
                    properties=frozenset({"light blade", "off-hand"}))
LONGBOW = Weapon(ref="w:longbow", category="military", damage="1d10", proficiency=2, group="bow",
                 ranged=(20, 40), properties=frozenset({"two-handed"}))
CROSSBOW = Weapon(ref="w:crossbow", category="simple", damage="1d8", proficiency=2,
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
HOLY_SYMBOL = Weapon(ref="w:holy-symbol", damage="1d4", proficiency=0, group="implement")

#: The eight Player's Handbook classes. Numbers off the class pages.
CLASSES: dict[str, ClassLine] = {
    "fighter": ClassLine(
        "fighter", 15, 6, 9, {"fort": 2}, "scale", 2, (LONGSWORD,), STR,
        {STR: 18, CON: 14, DEX: 13, INT: 10, WIS: 12, CHA: 8},
    ),
    "cleric": ClassLine(
        "cleric", 12, 5, 7, {"will": 2}, "chain", 0, (MACE, HOLY_SYMBOL), WIS,
        {STR: 14, CON: 13, DEX: 10, INT: 8, WIS: 18, CHA: 12},
    ),
    "rogue": ClassLine(
        "rogue", 12, 5, 6, {"ref": 2}, "leather", 0, (DAGGER, CROSSBOW), DEX,
        {STR: 12, CON: 13, DEX: 18, INT: 10, WIS: 8, CHA: 14},
    ),
    "wizard": ClassLine(
        "wizard", 10, 4, 6, {"will": 2}, "cloth", 0, (ORB,), INT,
        {STR: 10, CON: 13, DEX: 14, INT: 18, WIS: 12, CHA: 8},
    ),
    "paladin": ClassLine(
        "paladin", 15, 6, 10, {"fort": 1, "ref": 1, "will": 1}, "plate", 2,
        (LONGSWORD, HOLY_SYMBOL), STR,
        {STR: 16, CON: 13, DEX: 10, INT: 8, WIS: 12, CHA: 16},
    ),
    # Two blades and a bow. The two-weapon build is the one several of its
    # level 1 rows require outright, and a ranger carrying one sword could
    # never use them.
    "ranger": ClassLine(
        "ranger", 12, 5, 6, {"fort": 1, "ref": 1}, "leather", 0,
        (SHORTSWORD, SHORTSWORD, LONGBOW), DEX,
        {STR: 14, CON: 13, DEX: 18, INT: 8, WIS: 12, CHA: 10},
    ),
    "warlock": ClassLine(
        "warlock", 12, 5, 6, {"ref": 1, "will": 1}, "leather", 0, (ROD,), CHA,
        {STR: 10, CON: 14, DEX: 13, INT: 12, WIS: 8, CHA: 18},
    ),
    "warlord": ClassLine(
        "warlord", 12, 5, 7, {"fort": 1, "will": 1}, "chain", 1, (LONGSWORD,), STR,
        {STR: 18, CON: 12, DEX: 10, INT: 14, WIS: 8, CHA: 13},
    ),
}


#: A few more weapons, for the classes that arrived with phase C.
GREATAXE = Weapon(ref="w:greataxe", category="military", damage="1d12", proficiency=2,
                  group="axe", properties=frozenset({"two-handed"}))
QUARTERSTAFF = Weapon(ref="w:quarterstaff", category="simple", damage="1d8", proficiency=2,
                      group="staff", properties=frozenset({"two-handed"}))
LONGSPEAR = Weapon(ref="w:longspear", category="military", damage="1d10", proficiency=2,
                   group="spear", properties=frozenset({"two-handed", "reach"}))
UNARMED = Weapon(ref="w:unarmed", category="simple", damage="1d8", proficiency=3, group="unarmed")
STAFF = Weapon(ref="w:staff", damage="1d8", proficiency=0, group="implement")
TOTEM = Weapon(ref="w:totem", damage="1d4", proficiency=0, group="implement")


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
    from combat_engine.etl.build import game

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
        held.append(UNARMED)
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


def _spread(order: list[Ability]) -> dict[Ability, int]:
    """The standard array, best score to the class's first-named ability."""
    array = [18, 14, 13, 12, 10, 8]
    rest = [a for a in Ability if a not in order]
    return dict(zip([*order, *rest], array, strict=False))


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
    #: What it fights with, when the fork changes that. A two-blade ranger
    #: and an archer are not carrying the same things.
    weapons: tuple[Weapon, ...] = ()
    #: The damage type a leg is sworn to, for the one fork that is a
    #: choice of element rather than of ability. `c.element()` reads it.
    element: DamageType | None = None


BUILDS: dict[str, tuple[Build, ...]] = {
    # A -- Strength either way, and the fork is what backs it up.
    # Six legs, which is what the class page lists. Each names one of the
    # six printed talents, so `cf:fighter-grip` has something to ask about
    # and the two that are only a talent are no longer folded into a leg
    # that does not mean them. The scores are the page's own: where it
    # offers a choice of tertiary it is not recorded, and where it names no
    # secondary at all -- the brawling leg -- the second is the ability the
    # feature that leg is handed actually reads.
    # The first leg carries a two-handed weapon because its talent is about
    # holding one; without it the great-weapon half of `cf:fighter-grip`
    # was unreachable and the leg was a great-weapon fighter with a
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
    "paladin": (Build("avenging", STR, CHA), Build("protecting", CHA, WIS)),
    # V -- two blades or a bow, and they are different weapons as well as
    # different scores.
    #
    # Four legs, one per printed fighting style that a row can ask about.
    # The page's own build sections name the style each one takes, and two
    # of the four were missing: the style that replaces the shared ranged
    # bonus with a bonus for running, and the one that trades a feat and a
    # step of speed for the off hand. Neither had a leg, so
    # `cf:ranger-running` could only be kept apart from `cf:ranger-nearest`
    # by sharing a bonus type, and `cf:ranger-style` could not be written.
    #
    # The page gives no ability line for either of the two new ones -- it
    # says only which build each resembles -- so each takes the scores and
    # the arms of the leg it is described against. The fifth style is the
    # companion and has no leg: it is blocked on a creature the tree does
    # not have, and a leg for it would deal a ranger missing its feature.
    "ranger": (
        Build("two-blade", STR, WIS, (SHORTSWORD, SHORTSWORD)),
        Build("archer", DEX, WIS, (LONGBOW, SHORTSWORD)),
        Build("hunter", DEX, WIS, (LONGBOW, SHORTSWORD)),
        Build("marauder", STR, WIS, (SHORTSWORD, SHORTSWORD)),
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
    # where the page's build line says "Wrathful Invoker". The rows were
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
    "warden": (
        Build("earthstrength", STR, CON),
        Build("lifespirit", STR, CON),
        Build("stormheart", STR, WIS),
        Build("wildblood", STR, WIS),
    ),
    "warlock": (
        Build("infernal", CON, CHA),
        Build("fey", CHA, CON),
        Build("dark", CON, CHA),
        Build("elemental", CHA, CON, element=DamageType.FIRE),
    ),
    # A -- Strength either way, and a third leg for the leader feature that
    # is a shield and a granted row rather than a score.
    "warlord": (
        Build("inspiring", STR, CHA),
        Build("tactical", STR, INT),
        Build("bravura", STR, CHA),
        Build("insightful", STR, INT),
        Build("resourceful", STR, INT),
        Build("shielding", STR, CHA),
    ),
    # V -- which soul. The two share Charisma and differ on the secondary
    # exactly as the derived `second-<ability>` pair did, so the order here
    # keeps the first leg the same character it always was.
    #
    # The page prints four sources and these are the two whose feature is
    # written. The other two have no leg on purpose: see
    # `cf:sorcerer-soul-rest` in `docs/blocked.json`.
    "sorcerer": (Build("wild", CHA, DEX), Build("dragon", CHA, STR)),
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


def build_of(cls: str, name: str = "") -> Build:
    """One class's build, by name, or the first it lists."""
    options = BUILDS.get(cls) or ()
    if not options:
        return Build("", CLASSES[cls].key, CON)
    for b in options:
        if b.name == name:
            return b
    return options[0]


def scores_for(line: ClassLine, build: Build) -> dict[Ability, int]:
    """The class's own numbers, rearranged so the build's leg is the good one.

    The values are the ones read off the class page and are not invented
    here; what the build changes is *which ability gets which*. A battle
    cleric and a devoted cleric are the same six numbers in a different
    order, which is exactly what picking a leg means.
    """
    values = sorted(line.scores.values(), reverse=True)
    out: dict[Ability, int] = {}
    ordered = [build.primary, build.secondary]
    ordered += [a for a in line.scores if a not in ordered]
    for ability, value in zip(ordered, values, strict=False):
        out[ability] = value
    return out


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
        if leg.element is not None:
            out.add(f"element:{leg.element.value}")
        return out

    @property
    def line(self) -> ClassLine:
        return CLASSES[self.cls]

    @property
    def ref(self) -> str:
        return f"c:{self.cls}"


#: A character's slots at level 1: two at-wills, one encounter power, one
#: daily. Class features and the leader's heal are on top of these, because
#: neither is a choice the book asks you to spend a slot on.
SLOTS = ((Usage.AT_WILL, 2), (Usage.ENCOUNTER, 1), (Usage.DAILY, 1))


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
    import combat_engine.content  # noqa: F401  (registers the rows)
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

    out = sorted(p.ref for p in mine if p.level == 0)
    # Not already dealt: a class whose heal is itself a level-0 row was
    # handed it twice, so `Powers.known` carried the ref twice over. The
    # bard and the ardent are the two.
    out += sorted(p.ref for p in mine if _is_class_heal(p) and p.ref not in out)

    for usage, count in SLOTS:
        at_level = [p for p in mine if p.level == level and p.usage is usage]
        on_leg = [p for p in at_level if _fits(p, build)]
        pool = sorted(p.ref for p in (on_leg or at_level) if p.ref not in out)
        spare = sorted(p.ref for p in at_level if p.ref not in out and p.ref not in pool)
        chosen = pick.sample(pool, min(count, len(pool)))
        # A thin leg is topped up from the rest of the class rather than
        # leaving the character with one at-will.
        while len(chosen) < count and spare:
            chosen.append(spare.pop(0))
        out += sorted(chosen)
    return out + sorted(r for ref in out for r in riders.get(ref, []))


def feat_slots(level: int) -> int:
    """How many feats a character of this level has taken.

    One at first level and one more at every even level after, which is
    six by level 10. A human takes one more at first level; there is no
    race in the engine yet, so there is no human to give it to, and the
    line is not written until there is.
    """
    return 1 + level // 2


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
    if "ref" in node:
        return node["ref"] in powers
    if "weapon_prof" in node:
        wanted = node["weapon_prof"].lower()
        return any(
            wanted in (w.group, w.category, w.ref.removeprefix("w:").replace("-", " "))
            for w in who.line.weapons
        )
    # race, term, skill, source: nothing on a character answers them yet.
    return False


def feats_for(
    cls: str, level: int = 1, build: Build | None = None,
    rng: Random | None = None, powers: list[str] | None = None,
) -> list[str]:
    """The feats this character has taken, drawn like its powers are.

    Only feats that are **written** and whose prerequisite this character
    **meets**, so the draw cannot hand out a row that does nothing or one
    the book would not allow. Taken one at a time rather than sampled, so
    that a feat naming another feat as its prerequisite can be taken in
    the same career as the one it needs.
    """
    import combat_engine.content  # noqa: F401  (registers the rows)
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.etl.build import game

    pick = rng or Random(0)
    who = Character(cls=cls, level=level, build=(build.name if build else ""))
    held = list(powers or [])
    gates = {
        r["ref"]: json.loads(r["prereq"]) if r["prereq"] else None
        for r in game().execute("SELECT ref, prereq FROM feat")
    }
    pool = sorted(ref for ref in gates if ref in REGISTRY and not REGISTRY[ref].todo)

    taken: list[str] = []
    for _ in range(feat_slots(level)):
        legal = [r for r in pool if r not in taken and meets(gates[r], who, held + taken)]
        if not legal:
            break
        taken.append(pick.choice(legal))
    return sorted(taken)


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
    from combat_engine.engine import Magic
    from combat_engine.etl.build import game

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
        row = pool[rng.randrange(len(pool))]
        out.append(
            Magic(
                ref=row["ref"],
                slot="implement" if arm is held and arm is not None else row["slot"],
                plus=row["plus"],
                enh_to=enh_to,
                crit=_crit_dice(row["crit"]),
                powers=(),
            )
        )
    return out


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
    import combat_engine.content  # noqa: F401  (registers the rows)
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


def build_for(cls: str, ref: str) -> str:
    """The build whose gear can actually hold this row.

    A class's builds carry different weapons -- a two-blade ranger owns no
    bow at all -- so a ranged row fielded on the wrong one is refused for a
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
    # **A copy each, always.** `LONGSWORD` and its siblings are module-level
    # singletons, so every fighter ever built shared one object -- and
    # `Cast.decay` reduces a magic weapon's enhancement *in place*. The
    # moment treasure exists, one character's sword rusting rusts every
    # sword in the game, in this fight and every later one, and nothing
    # anywhere would say so.
    carried = [replace(w) for w in (build.weapons or line.weapons)]
    carried_shield = _shield_for(line, carried)
    scores = scores_for(line, build)
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
        list(powers),
    )

    # First level takes the whole Constitution *score*; every level after
    # takes the class's flat step. Surges take the modifier, not the score.
    con = modifier(scores[CON])
    max_hp = line.hp_first + scores[CON] + line.hp_per_level * (who.level - 1)

    eid = world.spawn(
        Ident(ref=who.ref),
        Position(square=square, size=Size.MEDIUM),
        Side(team=who.team),
        Stats(level=who.level, scores=scores),
        Defenses(values=defences(replace(line, shield=carried_shield), scores, who.level)),
        Health(max_hp=max_hp, surges=line.surges + con),
        Movement(speed=5 if line.armour in ("scale", "plate") else 6),
        Initiative(bonus=modifier(scores[DEX])),  # level term via scaling
        Conditions(),
        Mods(),
        Budget(),
        # Every character can make a ranged basic attack if it is holding
        # something to make it with; `can_branch` refuses the row to anyone
        # who is not. A monster leaves this empty -- its ranged attacks are
        # its own printed rows.
        Powers(
            known=[*powers, *feats],
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
        ),
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
