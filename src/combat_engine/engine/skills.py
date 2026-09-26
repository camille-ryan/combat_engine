"""Skill checks.

A check is d20 + the ability modifier + half level, which is the 4e floor,
plus whatever modifiers are standing. There is **no training model**:
`game.db` carries no skill list per class, so nothing here decides who is
trained and the +5 is not applied by default. It is still sayable --
`c.bonus("skill:stealth", 5)` is read like any other modifier -- and a
`Skills` component seeding it from the chassis is the one thing this file
is short of.

The modifier key is `skill:<name>`, and a blanket `skill` modifier applies
to every check, which is what an armour penalty or a racial bonus to all of
them would be.

Passive checks are 10 + the same modifier, and that is the whole of the
rule: a row that has to beat somebody's notice without an opposed roll --
going unseen after a move -- asks `passive` rather than inventing a DC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .components import Mods, Stats
from .events import SkillCheck
from .types import Ability

if TYPE_CHECKING:
    from .ecs import World


#: Which ability each skill keys off. The one piece of rules data here, and
#: it is the same table for every class.
SKILLS: dict[str, Ability] = {
    "acrobatics": Ability.DEX,
    "arcana": Ability.INT,
    "athletics": Ability.STR,
    "bluff": Ability.CHA,
    "diplomacy": Ability.CHA,
    "dungeoneering": Ability.WIS,
    "endurance": Ability.CON,
    "heal": Ability.WIS,
    "history": Ability.INT,
    "insight": Ability.WIS,
    "intimidate": Ability.CHA,
    "nature": Ability.WIS,
    "perception": Ability.WIS,
    "religion": Ability.INT,
    "stealth": Ability.DEX,
    "streetwise": Ability.CHA,
    "thievery": Ability.DEX,
}


@dataclass
class CheckResult:
    """What one check came to.

    `__bool__` is whether it beat the DC, so `if c.check("history", 25):`
    reads as the card does -- the same arrangement `AttackResult` makes for
    `c.strike()`. `total` is there because one printed row halves the
    result rather than comparing it to anything.
    """

    skill: str
    natural: int = 0
    bonus: int = 0
    total: int = 0
    dc: int = 0
    success: bool = False

    def __bool__(self) -> bool:
        return self.success

    def __int__(self) -> int:
        return self.total


def modifier(world: World, eid: int, skill: str) -> int:
    """The fixed part of a creature's check: ability, half level, modifiers."""
    stats = world.get(eid, Stats)
    ability = SKILLS.get(skill.lower())
    out = 0
    if stats is not None:
        out += stats.half_level
        if ability is not None:
            out += stats.mod(ability)
    mods = world.get(eid, Mods)
    if mods is not None:
        ctx = {"actor": eid, "skill": skill.lower()}
        out += mods.total(f"skill:{skill.lower()}", ctx) + mods.total("skill", ctx)
    return out


def passive(world: World, eid: int, skill: str) -> int:
    """10 plus the modifier -- what somebody notices without rolling."""
    return 10 + modifier(world, eid, skill)


def check(world: World, eid: int, skill: str, dc: int = 0, *, bonus: int = 0) -> CheckResult:
    """Roll one skill check and announce it.

    The die is rolled first and the modifiers are totalled **inside the
    resolve callback**, which runs after the interrupt window. That is what
    lets "Trigger: you would make an Athletics check" answer by laying a
    bonus: a row firing in that window is heard before the number is
    settled. A listener may also add to `ev.bonus` directly.
    """
    skill = skill.lower()
    natural = world.rng.d20().total
    announced = SkillCheck(
        actor=eid,
        skill=skill,
        dc=dc,
        natural=natural,
        bonus=bonus,
        total=natural + bonus,
        success=False,
    )

    def finish(ev: SkillCheck) -> None:
        ev.bonus += modifier(world, eid, ev.skill)
        ev.total = ev.natural + ev.bonus
        ev.success = ev.dc <= 0 or ev.total >= ev.dc

    rolled = world.bus.emit(announced, finish)
    return CheckResult(
        skill=rolled.skill,
        natural=rolled.natural,
        bonus=rolled.bonus,
        total=rolled.total,
        dc=rolled.dc,
        success=rolled.success and not rolled.cancelled,
    )
