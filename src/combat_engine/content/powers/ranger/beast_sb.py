"""Ranger: the rows a beast companion swings for itself.

Every one of these prints "Beast's attack bonus vs. AC" and `N[B]`, and
neither was sayable. Three things close it, and all three are about *whose*
numbers are being used:

* `Attack(..., by="companion")` in the header rolls the beast's line. Its
  square comes with it -- `c.strike` takes `from_` off the same field -- so
  reach, cover and flanking are measured from the beast, which is what
  "Melee beast 1" means. `from_=` alone moved the square and left the
  numbers the ranger's, which is the shape that looks finished and is wrong.
* `c.b(n)` is `c.w(n)` for a beast, and `c.b_mod` is "beast's Strength
  modifier" asked of the beast.
* `Range(from_="companion")` was already here for the shaman and does the
  aiming.

**Where the beast's numbers come from, and this paragraph used to be wrong.**
It said the die "is the one number left open, and it is open because it
belongs to a *species*, which this engine does not model". That was true of a
**ref-less** companion -- built from a copy of its owner, with `c.b` falling
back to the `d4` that `c.w` gives empty hands -- and it is not true of a
ranger's beast. `chargen` records the category beside the leg as
`beast:comp:N`, `c.call_beast` reads it back, and `loader.companion` reads the
printed block. Measured on one seed, nothing changed but the category:

    bear comp:1   1d12   hp 16 + 10/level   116 at level 10   2d12 on a row
    wolf comp:8   1d8    hp 14 +  8/level    94 at level 10   2d8

So the species *is* modelled, and the sentence that followed from it --
"every `Beast:` rider that pays out only for a named species is dropped rather
than asked" -- was wrong too. `Companion.ref` answers the species exactly, and
`level_2_b._beast_is` is the gate. Nine rows there name a category; all nine
used to gate on "owns a companion", so fielding any beast made all nine usable
and eight were wrong.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    WILL,
    Ability,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    Melee,
    UpTo,
    When,
    World,
    power,
)
from combat_engine.engine.components import Companion, Health
from combat_engine.engine.events import AttackDeclared, DamageApplied, Moved
from combat_engine.engine.query import squares
from combat_engine.engine.triggers import Trigger, by_melee

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_BLOODIED_US = "an enemy bloodies you or your beast companion"


def _has_beast(world: World, eid: int) -> bool:
    """"Melee beast 1" cannot be swung without the beast.

    Not a printed Requirement -- it is the range line -- but a row whose
    attack is rolled `by="companion"` falls back to the ranger's own numbers
    when there is no companion, and rolling the ranger is precisely what
    these rows are here to stop.
    """
    return any(
        world.get(who, Companion).owner == eid for who in world.having(Companion)
    )


def _bloodied_beast(world: World, eid: int) -> bool:
    return _has_beast(world, eid) and world.need(eid, Health).bloodied


def _bloodied_by(world: World, me: int, ev: DamageApplied) -> bool:
    """Did that blow bloody the ranger or the beast?

    Asked off the event, because by the time anything else looks the
    creature is simply bloodied and there is no telling which hit did it.
    `Bloodied` itself carries only who it happened to, and this row's target
    is whoever did it.
    """
    victim = world.get(ev.target, Health)
    if victim is None or not victim.bloodied:
        return False
    if victim.hp + ev.amount <= victim.max_hp // 2:
        return False  # it was already bloodied before this one landed
    mine = world.get(ev.target, Companion)
    return ev.target == me or (mine is not None and mine.owner == me)


def _flanking(c: Cast) -> bool:
    """Are the ranger and the beast flanking the target between them?"""
    pet = c.companion()
    if pet is None or c.target is None:
        return False
    mine = sorted(squares(c.world, c.me))
    theirs = sorted(squares(c.world, pet))
    victim = squares(c.world, c.target)
    return any(
        c.world.grid.flanks(a, b, victim) for a in mine for b in theirs
    )


@power(
    "p4369",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p4369(c: Cast) -> None:
    """"One creature adjacent to you" is narrower than the beast's reach, so
    it is asked here: the range line aims from the beast and the target line
    wants the ranger beside it too."""
    if not c.adjacent():
        return
    if c.strike():
        c.damage(c.b(2 if c.level >= 21 else 1), c.b_mod(Ability.STR) + c.wis_mod)


@power(
    "p10594",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p10594(c: Cast) -> None:
    if c.strike():
        extra = 1 if _flanking(c) else 0
        c.damage(c.b(1 + extra), c.b_mod(Ability.STR))


@power(
    "p12500",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p12500(c: Cast) -> None:
    """The flanking rider is a one-shot watch on the target's own movement --
    `Moved` rather than `MoveStart`, because the printed line pays out after
    it has gone and both of the shifts are measured from where it ended."""
    if not c.strike():
        return
    c.damage(c.b(2), c.b_mod(Ability.STR))
    victim = c.target
    if victim is None or not _flanking(c):
        return
    pet = c.companion()

    def bolt(ev: Moved) -> None:
        if ev.actor != victim:
            return
        c.shift(3)
        if pet is not None:
            c.shift(3, who=pet)

    c.watch(Moved, bolt, until=When.EONT, once=True, label=c.ref)


@power(
    "p12503",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=UpTo(2),
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_bloodied_beast,
    requires_text="you must be bloodied",
)
def p12503(c: Cast) -> None:
    """The trailing Effect is a standing watch rather than `c.on_attack`: the
    creature it keys off is whoever is beside the beast at the time, not one
    named attacker, and `by=` wants that named in advance."""
    if c.strike():
        c.damage(c.b(2), c.b_mod(Ability.STR))
    else:
        c.half_damage(c.b(2), c.b_mod(Ability.STR))
    if not c.first:
        return
    c.temp_hp(10, on=c.me)
    pet = c.companion()
    if pet is None:
        return

    def bite(ev: AttackDeclared) -> None:
        if ev.target != c.me or ev.attacker == c.me:
            return
        if not by_melee(c.world, c.me, ev):
            return
        if c.adjacent_to(pet, ev.attacker):
            c.flat(c.b_mod(Ability.STR), on=ev.attacker)

    c.watch(AttackDeclared, bite, until=When.ENCOUNTER, label=c.ref)


@power(
    "p4373",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p4373(c: Cast) -> None:
    """Two attacks by two creatures: the beast's own line, then the ranger's
    own, which is `c.attack` because the header can only carry one."""
    if c.strike():
        c.damage(c.b(), c.b_mod(Ability.STR))
    if c.attack(c.str_, REF):
        c.damage(c.w(), c.str_mod)


@power(
    "p4378",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p4378(c: Cast) -> None:
    if c.strike():
        c.damage(c.b(2), c.b_mod(Ability.STR))
    else:
        c.half_damage(c.b(2), c.b_mod(Ability.STR))
    if c.is_quarry():
        c.shift(3)
        c.basic()


@power(
    "p4391",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
    trigger=_BLOODIED_US,
    on=Trigger(DamageApplied, _bloodied_by, _BLOODIED_US),
)
def p4391(c: Cast) -> None:
    """`Bloodied` carries only who became bloodied, and the row's target is
    who did it -- so the blow is what is answered, and the event is read for
    "this took it below half" rather than asking afterwards."""
    foe = c.target
    if foe is None:
        foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    pet = c.companion()
    if pet is not None:
        c.shift(5, who=pet)
    if c.strike(on=foe):
        c.damage(c.b(2), c.b_mod(Ability.STR), on=foe)
        c.immobilized(until=When.SAVE_ENDS, on=foe)
    else:
        c.half_damage(c.b(2), c.b_mod(Ability.STR), on=foe)


@power(
    "p4401",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p4401(c: Cast) -> None:
    pet = c.companion()
    if pet is not None and c.wis_mod > 0:
        c.shift(c.wis_mod, who=pet)
    if c.strike():
        c.damage(c.b(), c.b_mod(Ability.STR))
    if c.attack(c.str_, AC):
        c.damage(c.w(), c.str_mod)


@power(
    "p4408",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(STR, vs=WILL, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p4408(c: Cast) -> None:
    """A burst centred on the beast, rolled by the beast. "Beast's attack
    bonus" is one number whatever it is thrown at, so the line is the same
    one every other row here declares, against Will."""
    if c.strike():
        c.damage("1d8", c.b_mod(Ability.WIS), dtype=DamageType.PSYCHIC)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.half_damage("1d8", c.b_mod(Ability.WIS), dtype=DamageType.PSYCHIC)


@power(
    "p10630",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_has_beast,
    requires_text="you must have a beast companion",
)
def p10630(c: Cast) -> None:
    """The beast's charge is its own action and its own swing, so it goes
    through `c.charge_at(who=)` rather than being folded into this attack."""
    victim = c.target
    if c.strike():
        c.damage(c.b(2), c.b_mod(Ability.STR))
        c.push(1, by=c.companion())
    else:
        c.half_damage(c.b(2), c.b_mod(Ability.STR))
    pet = c.companion()
    if pet is None:
        return
    others = [foe for foe in c.enemies() if foe != victim]
    quarry = c.choose(others, f"{c.ref}: what the beast charges")
    if quarry is not None:
        c.charge_at(quarry, who=pet)
