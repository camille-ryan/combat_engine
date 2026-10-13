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
    return out + _armour_penalty(world, eid, skill)


def ability_check(
    world: World, eid: int, ability: Ability, dc: int = 0, *, bonus: int = 0
) -> CheckResult:
    """A raw ability check: d20 + ability modifier + half level.

    **Not a skill check**, and fourteen rows said so before this existed --
    `i1385x1`'s note was "a raw ability check is not a skill check and
    nothing rolls one". The cards keep the two apart deliberately, and one
    of them prints "ability check or skill check" as two things, so folding
    this into `check()` with an invented skill name would have made every
    rider that watches for a *skill* fire on it.

    So it announces the same `SkillCheck` event -- a row answering "you
    would make a check" has to be able to hear this one -- but under the key
    `ability:<name>`, which no skill key can collide with. `my_check
    ("stealth")` does not match it; a rider wanting any check can look at
    the prefix.

    The ability modifier is added in the resolve callback rather than before
    the emit, for the reason `check()` gives: the interrupt window runs
    first, so "when you would make the check" can still lay a bonus, and
    `skills.modifier` cannot be reused because its `SKILLS` lookup has no
    entry for a bare ability and would silently contribute half level only.
    """
    fixed = 0
    stats = world.get(eid, Stats)
    if stats is not None:
        fixed = stats.half_level + stats.mod(ability)
    key = f"ability:{ability.value}"
    natural = world.rng.d20().total
    announced = SkillCheck(
        actor=eid,
        skill=key,
        dc=dc,
        natural=natural,
        bonus=bonus,
        total=natural + bonus,
        success=False,
    )

    def finish(ev: SkillCheck) -> None:
        extra = 0
        mods = world.get(eid, Mods)
        if mods is not None:
            ctx = {"actor": eid, "skill": ev.skill, "ability": ability.value}
            # Both keys are read here, which is what keeps them off
            # `lint.py`'s unread-modifier list: the narrow one for "+2 to
            # Strength checks" and the wide one for "+1 to ability checks".
            extra = mods.total(ev.skill, ctx) + mods.total("ability_check", ctx)
        ev.bonus += fixed + extra
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


#: The four skills an armour check penalty applies to. The printed list, and
#: it is short because the penalty is about moving in the stuff rather than
#: about being encumbered generally -- a Diplomacy check is not harder in
#: plate.
ENCUMBERED = ("acrobatics", "athletics", "stealth", "thievery")


def _armour_penalty(world: World, eid: int, skill: str) -> int:
    """What the armour and shield cost this check. Zero for most of them.

    **Nothing applied this.** `armour.check_penalty` has been in the database
    since #452 built the table and no reader outside `etl/` ever asked for
    it, so hide, chainmail, plate and a heavy shield were all free: a
    plate-wearing character rolled Stealth at the same number as one in
    cloth.

    Armour and shield **both** count and they add, which is the printed rule
    -- plate and a heavy shield is -2 and -2.

    Monsters are skipped. A stat block prints its skills as finished totals
    with whatever its gear costs already inside them, so subtracting again
    would charge it twice; `Gear.armour` is `"cloth"` for every creature
    `loader.spawn` makes anyway, which is the same answer by accident and
    not one to rely on. #452.
    """
    from .components import Defenses, Gear

    if skill.lower() not in ENCUMBERED:
        return 0
    # `Defenses.scale` is the discriminator, not `Stats` -- that is where
    # `loader.spawn` records a creature as a monster.
    defences = world.get(eid, Defenses)
    if defences is not None and defences.scale == "monster":
        return 0
    gear = world.get(eid, Gear)
    if gear is None:
        return 0
    from combat_engine.chargen import ARMOUR_CHECK, SHIELD_CHECK

    out = ARMOUR_CHECK.get(gear.armour, 0)
    if gear.shield:
        out += SHIELD_CHECK.get("heavy" if gear.shield == 2 else "light", 0)
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
