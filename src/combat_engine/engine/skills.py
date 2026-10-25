"""Skill checks.

A check is d20 + the ability modifier + half level + **5 if trained** +
whatever modifiers are standing.

**That +5 is new, and this file used to say it could not be had.** The old
note read: *"There is no training model: `game.db` carries no skill list
per class, so nothing here decides who is trained and the +5 is not
applied by default ... a `Skills` component seeding it from the chassis is
the one thing this file is short of."* Both halves are now built --
`class_skill` in `game.db` carries 205 rows across all 25 classes, and
`components.Skills` is the set `chargen` fills from it. #565.

Training is **not** a `Mods` entry, and the distinction is load-bearing: it
is a property of the creature rather than an effect laid on it, so it must
not be ended, suspended, stacked with itself or scoped by a `when=`. It
also has to add to a card's own bonus rather than replace it --
`c.bonus("skill:stealth", 5)` and being trained in stealth are different
facts, and one key for both would have made the second quietly win.

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

from .components import Mods, Skills, Stats
from .events import CheckDeclared, SkillCheck
from .types import Ability

if TYPE_CHECKING:
    from .ecs import World


#: What being trained in a skill is worth. The 4e number, and the only
#: reason it is a constant rather than a literal is that two places ask
#: -- the sum here, and `drivers.py` asserting it.
TRAINING = 5

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


def modifier(
    world: World,
    eid: int,
    skill: str,
    target: int | None = None,
    natural: int | None = None,
) -> int:
    """The fixed part of a creature's check: ability, half level, modifiers.

    `target` is who the check is *about*, and it goes into the context so
    a modifier can be gated on it: "allies gain a +5 bonus to Heal checks
    to administer first aid **to you**" is a bonus on the ally's roll that
    only applies when the patient is the wearer. Without the key such a
    gate is silently false, which is this component's named failure mode.

    `natural` is **the die face, when this is a real check resolving** --
    `check()` and `ability_check()` pass it from inside their resolve
    callbacks and every other caller leaves it None. It is the other half
    of `CheckDeclared`: a row that called odd or even before the roll lays
    its bonus then and gates it on the face here, which is the only
    arrangement where the call is made in ignorance and the payment is
    made on the result. `f2804` is the row. #693.

    A standalone read -- `drivers.py` measuring what a check would come to,
    the page showing a skill list -- passes nothing, so a parity gate is
    **silently false** there rather than silently true. That is the right
    way round: the bonus is a contingency on a die that has not been
    thrown.
    """
    stats = world.get(eid, Stats)
    ability = SKILLS.get(skill.lower())
    out = 0
    if stats is not None:
        out += stats.half_level
        if ability is not None:
            out += stats.mod(ability)
    # **The +5 this file said it was missing.** Read off `Skills.trained`,
    # which `chargen` fills from `class_skill` -- the table that did not
    # exist when the module docstring above was written.
    #
    # Not a `Mods` entry. Training is a property of the creature and not an
    # effect laid on it, so it must not be ended, suspended, stacked with
    # itself, or scoped by a `when=` -- and a `skill:<name>` modifier is all
    # four of those things. It also has to be distinguishable from a card's
    # own +5: `c.bonus("skill:stealth", 5)` and being trained in stealth are
    # different facts that add, and bucketing both under one key would make
    # the second silently replace the first.
    trained = world.get(eid, Skills)
    if trained is not None and skill.lower() in trained.trained:
        out += TRAINING

    mods = world.get(eid, Mods)
    if mods is not None:
        ctx: dict[str, object] = {
            "actor": eid, "skill": skill.lower(), "target": target,
        }
        if natural is not None:
            ctx["natural"] = natural
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
    # Announced here too, under the same `ability:<name>` key: a row that
    # wants "any check you are about to make" must hear this one, and
    # `f2804`'s own predicate is what narrows to a skill. #693.
    world.bus.emit(CheckDeclared(actor=eid, skill=key, dc=dc))
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
            ctx = {"actor": eid, "skill": ev.skill,
                   "ability": ability.value, "natural": ev.natural}
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
    from combat_engine.armour import ARMOUR_CHECK, SHIELD_CHECK

    out = ARMOUR_CHECK.get(gear.armour, 0)
    if gear.shield:
        out += SHIELD_CHECK.get("heavy" if gear.shield == 2 else "light", 0)
    return out


def passive(world: World, eid: int, skill: str) -> int:
    """10 plus the modifier -- what somebody notices without rolling."""
    return 10 + modifier(world, eid, skill)


def check(
    world: World, eid: int, skill: str, dc: int = 0, *, bonus: int = 0,
    target: int | None = None, purpose: str = "",
) -> CheckResult:
    """Roll one skill check and announce it.

    The die is rolled first and the modifiers are totalled **inside the
    resolve callback**, which runs after the interrupt window. That is what
    lets "Trigger: you would make an Athletics check" answer by laying a
    bonus: a row firing in that window is heard before the number is
    settled. A listener may also add to `ev.bonus` directly.
    """
    skill = skill.lower()
    # **Before the die, which is the whole point of the event.** A row that
    # has to call odd or even cannot be offered the choice by `SkillCheck`:
    # that one carries `natural` already. #693.
    world.bus.emit(CheckDeclared(actor=eid, skill=skill, dc=dc, target=target))
    natural = world.rng.d20().total
    announced = SkillCheck(
        actor=eid,
        skill=skill,
        dc=dc,
        natural=natural,
        bonus=bonus,
        total=natural + bonus,
        success=False,
        target=target,
    )
    # **What the check was *for*, as a plain attribute and not a field.**
    # `#735` is the general version of this and is a scope call; this is the
    # narrow half Camille ruled in -- the printed in-combat circumstances.
    # A card can say "a Bluff check to gain combat advantage", which is a
    # *named action* rather than a vague intent, and without this a row
    # keyed to it fires on any successful Bluff check against anybody.
    #
    # An attribute for the reason `Effect.by` and `Hit.result` are: a
    # declared field reaches `Event.wire()` and so the page and every
    # replay fixture, and what the check was for is not a change in how a
    # fight resolves. Empty for every caller that does not say, which is
    # all but one today.
    announced.purpose = purpose  # ty: ignore[unresolved-attribute]

    def finish(ev: SkillCheck) -> None:
        ev.bonus += modifier(world, eid, ev.skill, ev.target, ev.natural)
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
