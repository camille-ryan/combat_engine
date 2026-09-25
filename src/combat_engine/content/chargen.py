"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

All eight Player's Handbook classes, to level 10.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    Budget,
    Conditions,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Mods,
    Movement,
    Position,
    Powers,
    Side,
    Size,
    Stats,
    Team,
    Weapon,
    World,
)
from combat_engine.engine import Build as BuildState
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

    @property
    def armour_bonus(self) -> int:
        return ARMOUR.get(self.armour, 0)

    @property
    def weapon(self) -> Weapon | None:
        return self.weapons[0] if self.weapons else None


LONGSWORD = Weapon(ref="w:longsword", damage="1d8", proficiency=3, group="heavy blade")
MACE = Weapon(ref="w:mace", damage="1d8", proficiency=2, group="mace")
DAGGER = Weapon(ref="w:dagger", damage="1d4", proficiency=3, group="light blade",
                properties=frozenset({"light blade", "off-hand"}))
SHORTSWORD = Weapon(ref="w:short-sword", damage="1d6", proficiency=3, group="light blade",
                    properties=frozenset({"light blade", "off-hand"}))
LONGBOW = Weapon(ref="w:longbow", damage="1d10", proficiency=2, group="bow",
                 ranged=(20, 40), properties=frozenset({"two-handed"}))
CROSSBOW = Weapon(ref="w:crossbow", damage="1d8", proficiency=2, group="crossbow",
                  ranged=(15, 30), properties=frozenset({"two-handed"}))
ROD = Weapon(ref="w:rod", damage="1d4", proficiency=0, group="implement")

#: The eight Player's Handbook classes. Numbers off the class pages.
CLASSES: dict[str, ClassLine] = {
    "fighter": ClassLine(
        "fighter", 15, 6, 9, {"fort": 2}, "scale", 2, (LONGSWORD,), STR,
        {STR: 18, CON: 14, DEX: 13, INT: 10, WIS: 12, CHA: 8},
    ),
    "cleric": ClassLine(
        "cleric", 12, 5, 7, {"will": 2}, "chain", 0, (MACE,), WIS,
        {STR: 14, CON: 13, DEX: 10, INT: 8, WIS: 18, CHA: 12},
    ),
    "rogue": ClassLine(
        "rogue", 12, 5, 6, {"ref": 2}, "leather", 0, (DAGGER, CROSSBOW), DEX,
        {STR: 12, CON: 13, DEX: 18, INT: 10, WIS: 8, CHA: 14},
    ),
    "wizard": ClassLine(
        "wizard", 10, 4, 6, {"will": 2}, "cloth", 0, (), INT,
        {STR: 10, CON: 13, DEX: 14, INT: 18, WIS: 12, CHA: 8},
    ),
    "paladin": ClassLine(
        "paladin", 15, 6, 10, {"fort": 1, "ref": 1, "will": 1}, "plate", 2,
        (LONGSWORD,), STR,
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
GREATAXE = Weapon(ref="w:greataxe", damage="1d12", proficiency=2, group="axe",
                  properties=frozenset({"two-handed"}))
QUARTERSTAFF = Weapon(ref="w:quarterstaff", damage="1d8", proficiency=2, group="staff",
                      properties=frozenset({"two-handed"}))
LONGSPEAR = Weapon(ref="w:longspear", damage="1d10", proficiency=2, group="spear",
                   properties=frozenset({"two-handed", "reach"}))
UNARMED = Weapon(ref="w:unarmed", damage="1d8", proficiency=3, group="unarmed")
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
    elif "military melee" in text:
        held.append(LONGSWORD)
    elif "simple melee" in text:
        held.append(MACE)
    if "military ranged" in text or "simple ranged" in text:
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


BUILDS: dict[str, tuple[Build, ...]] = {
    # A -- Strength either way, and the fork is what backs it up.
    "fighter": (Build("great-weapon", STR, CON), Build("guardian", STR, WIS)),
    # V -- the fork is the primary, and the two halves share Wisdom.
    "cleric": (Build("devoted", WIS, CHA), Build("battle", STR, WIS, (MACE,))),
    # A -- Dexterity either way.
    "rogue": (Build("brawny", DEX, STR), Build("trickster", DEX, CHA)),
    # A -- Intelligence either way.
    "wizard": (Build("control", INT, WIS), Build("war", INT, DEX)),
    # V -- swinging or shining.
    "paladin": (Build("avenging", STR, CHA), Build("protecting", CHA, WIS)),
    # V -- two blades or a bow, and they are different weapons as well as
    # different scores.
    "ranger": (
        Build("two-blade", STR, WIS, (SHORTSWORD, SHORTSWORD)),
        Build("archer", DEX, WIS, (LONGBOW, SHORTSWORD)),
    ),
    # V -- which pact was made.
    "warlock": (Build("infernal", CON, CHA), Build("fey", CHA, CON)),
    # A -- Strength either way.
    "warlord": (Build("inspiring", STR, CHA), Build("tactical", STR, INT)),
}


#: The classes phase C brought in, folded in beneath the eight.
#:
#: A derived line never overwrites a hand-written one: the eight above hold
#: judgement the table cannot, and a ranger carrying two blades *and* a bow
#: is the clearest case -- several of its level 1 rows require the pair
#: outright.
CLASSES.update(_from_the_book())

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

    @property
    def chosen(self) -> Build:
        return build_of(self.cls, self.build)

    @property
    def choices(self) -> set[str]:
        """What a power's `c.build(...)` rider asks about."""
        return {self.chosen.name} - {""}

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

    out = sorted(p.ref for p in mine if p.level == 0)
    out += sorted(p.ref for p in mine if _is_class_heal(p))

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

    # First level takes the whole Constitution *score*; every level after
    # takes the class's flat step. Surges take the modifier, not the score.
    con = modifier(scores[CON])
    max_hp = line.hp_first + scores[CON] + line.hp_per_level * (who.level - 1)

    eid = world.spawn(
        Ident(ref=who.ref),
        Position(square=square, size=Size.MEDIUM),
        Side(team=who.team),
        Stats(level=who.level, scores=scores),
        Defenses(values=defences(line, scores, who.level)),
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
        Powers(known=list(powers), ranged="rba"),
        BuildState(choices=set(who.choices)),
        Gear(
            weapons=list(build.weapons or line.weapons),
            shield=bool(line.shield),
            armour=line.armour,
        ),
    )
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
