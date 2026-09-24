"""Building a character.

Derived numbers, not stored ones. A level 1 fighter's AC is ten, plus half
its level, plus its armour, plus its shield, and writing that out is shorter
and more honest than recording an 18 that nothing can check.

Only the four base-set classes, and only to level 10 -- the README's scope.
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


#: What each class brings: hit points at first level and per level after,
#: healing surges, its armour and weapon, and the one defence it shores up.
@dataclass(frozen=True)
class ClassLine:
    name: str
    hp_first: int
    hp_per_level: int
    surges: int
    defence: str
    armour: str
    armour_bonus: int
    shield: bool
    weapon: Weapon | None
    #: The ability each of its powers attacks with, most of the time.
    key: Ability
    scores: dict[Ability, int] = field(default_factory=dict)


LONGSWORD = Weapon(ref="w:longsword", damage="1d8", proficiency=3, group="heavy blade")
MACE = Weapon(ref="w:mace", damage="1d8", proficiency=2, group="mace")
DAGGER = Weapon(ref="w:dagger", damage="1d4", proficiency=3, group="light blade",
                properties=frozenset({"light blade", "off-hand"}))

CLASSES: dict[str, ClassLine] = {
    "fighter": ClassLine(
        "fighter", 15, 6, 9, "fort", "scale", 7, True, LONGSWORD, STR,
        {STR: 18, CON: 14, DEX: 13, INT: 10, WIS: 12, CHA: 8},
    ),
    "cleric": ClassLine(
        "cleric", 12, 5, 7, "will", "chain", 6, False, MACE, WIS,
        {STR: 14, CON: 13, DEX: 10, INT: 8, WIS: 18, CHA: 12},
    ),
    "rogue": ClassLine(
        "rogue", 12, 5, 6, "ref", "leather", 2, False, DAGGER, DEX,
        {STR: 12, CON: 13, DEX: 18, INT: 10, WIS: 8, CHA: 14},
    ),
    "wizard": ClassLine(
        "wizard", 10, 4, 6, "will", "cloth", 0, False, None, INT,
        {STR: 10, CON: 13, DEX: 14, INT: 18, WIS: 12, CHA: 8},
    ),
}

#: Armour that lets you add a modifier to AC. Heavy armour does not.
LIGHT = {"cloth", "leather", "hide"}


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

    shield = 2 if line.shield else 0
    ac = 10 + line.armour_bonus + shield
    if line.armour in LIGHT:
        ac += max(mod(DEX), mod(INT))
    return {
        AC: ac,
        FORT: 10 + max(mod(STR), mod(CON)) + (2 if line.defence == "fort" else 0),
        REF: 10 + max(mod(DEX), mod(INT)) + shield + (2 if line.defence == "ref" else 0),
        WILL: 10 + max(mod(WIS), mod(CHA)) + (2 if line.defence == "will" else 0),
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
            weapons=[line.weapon] if line.weapon else [],
            shield=line.shield,
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
            f"  {line.armour}" + ("  shield" if line.shield else "")
            + (f"  {line.weapon.damage} weapon (+{line.weapon.proficiency} prof)"
               if line.weapon else "  implement"),
            f"  powers: {', '.join(who.powers) or '-'}",
        ]
    )
