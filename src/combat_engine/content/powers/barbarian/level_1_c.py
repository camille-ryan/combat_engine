"""Barbarian, level 1: the encounter attacks.

The at-wills are in `level_1.py` and the dailies in `level_1_b.py`; the six
conventions the whole batch follows are stated in the first of those, and
the three helpers these rows share with it are imported from there rather
than written twice.
"""

from __future__ import annotations

from combat_engine.content.powers.fighter.grips import two_melee
from combat_engine.engine import (
    AC,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Keyword,
    Melee,
    UpTo,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied

from .level_1 import (
    ALL_DEFENCES,
    MARTIAL_WEAPON,
    PRIMAL_WEAPON,
    _against_the_slowed,
    _howl,
    two_handed_reach,
)

# -- encounter --------------------------------------------------------------


@power(
    "p1020",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1020(c: Cast) -> None:
    """"1 damage for each enemy adjacent to you" is counted once, before any
    of them is knocked about, so every target of the burst takes the same
    number the printed line promises."""
    crowd = len(c.within(1, side="enemy"))
    if c.strike():
        c.damage(c.w(1), c.str_mod + crowd)


@power(
    "p11561",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed_reach,
    requires_text="needs a two-handed reach weapon",
)
def p11561(c: Cast) -> None:
    """The sweep is an Effect line: it clears the ring whether the swing that
    follows lands or not, and the reach weapon is what lets the barbarian
    still be in reach of the target afterwards."""
    if c.first:
        for foe in sorted(c.within(1, side="enemy")):
            c.push(1, on=foe)
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p12276",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p12276(c: Cast) -> None:
    """The rider is armed on the damage rather than on a hit: "the next time
    the target takes damage" is any damage from anybody. The watcher holds
    its own spent flag because the extra damage it deals is itself a
    `DamageApplied`, which would otherwise re-enter it before `once` has had
    a chance to take it down.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    steps = c.cha_mod if c.build("thaneborn") else 1
    spent: list[bool] = []

    def follow(ev: DamageApplied) -> None:
        if spent or ev.target != victim or ev.amount <= 0:
            return
        spent.append(True)
        c.flat(c.roll("1d6"), on=victim)
        if steps > 0:
            c.slide(steps, on=victim)

    c.watch(
        DamageApplied, follow, until=When.SONT, on=c.me, once=True,
        label=f"{c.ref} follows up",
    )


@power(
    "p14412",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14412(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.prone()


@power(
    "p14413",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14413(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.damage("1d8")


@power(
    "p4821",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4821(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod + (c.con_mod if c.build("rageblood") else 0))
    if c.first:
        for defence in ALL_DEFENCES:
            c.penalty(defence, 4, on=c.me, until=When.SONT)


@power(
    "p4908",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4908(c: Cast) -> None:
    """"Either ... or" is a choice the caster makes, and the second answer is
    only worth taking when there is something to shake off, so the hold is
    looked for first and the choice is offered over what is actually there.
    """
    if not c.strike():
        return
    shaking = [
        effect
        for effect in c.world.effects.of(c.me)
        if Condition.DAZED in effect.conditions or Condition.WEAKENED in effect.conditions
    ]
    pick = "temporary hit points"
    if shaking:
        pick = c.choose(
            [pick, "shake it off"], f"{c.ref}: which half"
        )
    if pick == "shake it off" and shaking:
        c.world.effects.end(shaking[0], c.ref)
    else:
        c.temp_hp(3 + c.con_mod, on=c.me)
    c.damage(c.w(2), c.str_mod)


@power(
    "p4933",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4933(c: Cast) -> None:
    bloody = c.bloodied()
    if c.strike():
        c.damage(c.w(2), c.str_mod + (c.con_mod if bloody else 0))


@power(
    "p4934",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4934(c: Cast) -> None:
    """The step is between the two swings, so it is taken on the first call
    and only when a second target was actually named."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.damage("1d6")
    if c.first and len(c.targets) > 1:
        c.shift(1)


@power(
    "p5213",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p5213(c: Cast) -> None:
    """The errata'd Miss line. The recoil is taken once for the whole swing
    rather than once per creature the burst missed: a ring of four would
    otherwise cost 4d6, which no printed burst does to its own user.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.damage(c.w(1, hand="off"))
    elif c.first:
        c.flat(c.roll("1d6"), on=c.me)


@power(
    "p9559",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9559(c: Cast) -> None:
    """`c.reroll_attack` reads the attack off `c.trigger` and there is no
    trigger here, so the second swing is rolled outright. The 5 damage is
    the price of a reroll that failed, which is what the printed Miss line
    charges for.
    """
    extra = c.con_mod if c.build("rageblood") else 0
    if c.strike():
        c.damage(c.w(2), c.str_mod + extra)
        return
    if not c.may("take 5 damage and swing again", who=c.me):
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod + extra)
    else:
        c.flat(5, on=c.me)


@power(
    "p9560",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9560(c: Cast) -> None:
    """"Your next attack" is one attack, so both halves of the reward carry
    `once` -- and they are two separate modifiers because the engine reads
    an attack bonus and a damage bonus in different places."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    me = c.me

    def repay(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        c.bonus("attack", 2, on=me, until=When.ENCOUNTER, once=True)
        c.bonus("damage", 2, on=me, until=When.ENCOUNTER, once=True)

    c.watch(
        DamageApplied, repay, until=When.SONT, on=me, once=True,
        label=f"{c.ref} answers a blow",
    )
    if c.build("thaneborn") and c.cha_mod > 0:
        friends = sorted(a for a in c.within(5, side="ally") if a != me)
        friend = c.choose(friends, f"{c.ref}: who is urged on") if friends else None
        if friend is not None:
            c.bonus(
                "damage", c.cha_mod, on=friend, until=When.EONT,
                when=lambda ctx: ctx.get("target") == victim,
            )


@power(
    "p9562",
    level=1,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p9562(c: Cast) -> None:
    """The blast slows whoever it catches *and* the target, which is the one
    place `_howl`'s "other than the target" does not apply -- the printed
    line says "each enemy in the blast" without the exception."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod)
    for foe in [*_howl(c, 0), victim]:
        c.slowed(until=When.EONT, on=foe)
    if c.build("thunderborn") and c.con_mod > 0:
        c.bonus(
            "damage", c.con_mod, on=c.me, until=When.EONT,
            when=_against_the_slowed(c),
        )
