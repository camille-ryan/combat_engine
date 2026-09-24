"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

All eight Player's Handbook classes, to level 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
from combat_engine.engine.movement import place

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
    "ranger": ClassLine(
        "ranger", 12, 5, 6, {"fort": 1, "ref": 1}, "leather", 0,
        (SHORTSWORD, LONGBOW), DEX,
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


@dataclass
class Character:
    cls: str
    level: int = 1
    powers: list[str] = field(default_factory=list)
    team: Team = Team.PC

    @property
    def line(self) -> ClassLine:
        return CLASSES[self.cls]

    @property
    def ref(self) -> str:
        return f"c:{self.cls}"


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
    scores = dict(line.scores)
    # Level 4, 8 and so on raise two scores by one. Applied here rather than
    # recorded, so a level 8 character is derivable from its class and level.
    for step in (4, 8):
        if who.level >= step:
            scores[line.key] += 1
            scores[CON] += 1

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
        Powers(known=list(who.powers)),
        Gear(
            weapons=list(line.weapons),
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
