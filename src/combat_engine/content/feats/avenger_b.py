"""Avenger feats, the second batch.

`avenger.py` holds the first and this one runs on the same rail: every
row turns on "your oath of enmity target", and `oath.sworn` is the
question the oath itself asks, imported rather than re-derived.

This list is unusually writable for a race-gated one, because the
avenger's racial feats name their power by ref -- `p1450`, `p1831`,
`p7548`, `p8278`, `p1628`, `p2483`, `p2484`, `p1448`, `p6189` -- rather
than in prose. Only change shape still arrives as a name.

The class's own second feature, divine guidance, is `p5331` and is
named by ref in one prerequisite but not the other two rows that ride
on it -- so those carry `c.class_feature()` and the one that has the
ref does not.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.avenger.oath import (
    oath_target,
    swear,
    sworn,
)
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Hit,
    PowerUsed,
    SurgeSpent,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Position
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import distance
from combat_engine.engine.query import allies, distance_between

OATH = "p3069"
#: A racial power the benefit line names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)
#: A class feature named in prose with no ref.
FEATURE = ("c.class_feature()",)


def _hit_my_oath(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and sworn(world, me, ev.target)


def _ranged_hit_my_oath(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        _hit_my_oath(world, me, ev)
        and p is not None
        and p.reach.kind in ("ranged", "area_burst")
    )


def _crit_my_oath(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return _hit_my_oath(world, me, ev) and ev.critical


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hit_oath_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return (
            ev.attacker == me and ev.power == ref
            and sworn(world, me, ev.target)
        )

    return when


# -- the oath itself --------------------------------------------------------


@power("f1546", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3069",
       on=Trigger(PowerUsed, _used(OATH), "you swear an oath"))
def f1546(c: Cast) -> None:
    """A mark on top of the oath. `PowerUsed` fires before the body, so
    the oath has not landed yet -- but the mark is laid on the same
    creature either way and `PowerUsed.targets` names it."""
    for foe in c.trigger.targets:
        c.mark(on=foe, until=When.EONT)


@power("f1504", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit your oath target at range",
       on=Trigger(Hit, _ranged_hit_my_oath, "you hit your oath at range"))
def f1504(c: Cast) -> None:
    """"As long as you end that shift closer" -- so the destination is
    chosen here rather than left to the decider: `c.shift` takes a
    square, and the nearest reachable one to the target is the only
    reading of the clause that always satisfies it."""
    foe = c.trigger.target
    reach = 1 + c.dex_mod
    options = c.world.reachable_squares(c.me, reach)
    here = c.world.get(foe, Position)
    if not options or here is None:
        return
    closer = min(options, key=lambda sq: distance(sq, here.square))
    if distance(closer, here.square) < distance_between(c.world, c.me, foe):
        c.shift(reach, to=closer)


@power("f1515", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1515(c: Cast) -> None:
    """Allies hit harder while *you* stand beside the sworn enemy. Both
    the adjacency and the oath are asked per attack, because the oath
    moves and so does the avenger."""
    me = c.me
    step = 1 + (c.level >= 11) + (c.level >= 21)
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "damage", step, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("target") is not None
                and sworn(c.world, me, ctx["target"])
                and c.adjacent(to=ctx["target"])
            ),
        )


@power("f1749", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit your oath target",
       on=Trigger(Hit, _crit_my_oath, "you crit your oath"))
def f1749(c: Cast) -> None:
    """Only allies *adjacent to the target*, and that is asked when the
    blow lands rather than per attack: the printed line reads "all
    allies adjacent to the target gain", which fixes the set at the
    moment of the critical."""
    me, foe = c.me, c.trigger.target
    for friend in [a for a in allies(c.world, me) if a != me]:
        if not c.adjacent_to(friend, foe):
            continue
        c.bonus(
            "damage", 2, on=friend, until=When.SONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f2163", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.oath_on_ranged()",))
def f2163(c: Cast) -> None:
    """Extends the oath's benefit to ranged basic attacks. The oath's
    benefit is two attack rolls taking the better, worked out inside
    `oath.py` for melee only -- and widening it is that row's business,
    not something a modifier can add from outside."""


@power("f2162", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.floor_damage_dice()",))
def f2162(c: Cast) -> None:
    """Treats a 1 or 2 on a damage die as a 3. Reaching into the dice a
    row rolls, which `c.reroll_damage` does not substitute for -- that
    rolls the whole expression twice, a different and larger change."""


@power("f2165", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def f2165(c: Cast) -> None:
    """Cancels the run action's attack penalty against the sworn enemy.
    There is no run action: `actions.legal` offers a walk, a shift, a
    charge and the standard menu, and running is not on it."""


@power("f2009", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3069 on an undead creature",
       on=Trigger(PowerUsed, _used(OATH), "you swear an oath"))
def f2009(c: Cast) -> None:
    """`c.is_kind` reads a creature's printed type, which is what
    "undead" means here."""
    for foe in c.trigger.targets:
        if c.is_kind("undead", on=foe):
            c.grants_advantage(on=foe, until=When.EONT)


# -- riders on a racial power that is a ref ---------------------------------


@power("f1558", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit your oath target with p1831",
       on=Trigger(Hit, _hit_oath_with("p1831"), "you hit your oath"))
def f1558(c: Cast) -> None:
    """Vulnerability to *all* damage, which `c.vulnerable` says with no
    type at all rather than with a list of every type there is."""
    c.vulnerable(c.dex_mod, on=c.trigger.target, until=When.SONT)


@power("f1551", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7548",
       on=Trigger(PowerUsed, _used("p7548"), "you use that racial power"))
def f1551(c: Cast) -> None:
    """Moves the oath to whatever set the racial power off. "The
    triggering enemy" is the racial power's target, which
    `PowerUsed.targets` carries -- and `c.grant_row` is not needed,
    because swearing is what `p3069` does and this simply aims it."""
    for foe in c.trigger.targets:
        swear(c, foe)
        return


@power("f2011", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit your oath target with p8278",
       on=Trigger(Hit, _hit_oath_with("p8278"), "you hit your oath"))
def f2011(c: Cast) -> None:
    """The extra die is paid straight rather than as a bonus, because
    the printed total names it as part of that power's damage and
    `c.flat` takes the type `c.bonus` cannot."""
    c.flat(c.roll("1d8"), dtype=DamageType.NECROTIC, on=c.trigger.target)


@power("f2289", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus(dtype=)",),
       trigger="you use p1628 on your oath target",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f2289(c: Cast) -> None:
    """Extra damage on melee blows against the sworn enemy.

    The *type* is dropped: the printed extra is fire and `c.bonus`
    carries no damage type, so it rolls untyped -- wrong against
    anything that resists fire. The same gap the assassin's f1809
    named.
    """
    me = c.me
    if not any(sworn(c.world, me, f) for f in c.trigger.targets):
        return
    c.bonus(
        "damage", c.int_mod, on=me, until=When.EONT,
        when=lambda ctx: (
            not ctx.get("ranged", False)
            and sworn(c.world, me, ctx.get("target"))
        ),
    )


@power("f1527", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f1527(c: Cast) -> None:
    """Five squares further on a racial teleport, if it ends beside the
    sworn enemy. The power is a ref and the oath is readable; nothing
    adds to the distance a *particular* row moves, which is the symbol
    the ranger's f786 named."""


@power("f1524", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f1524(c: Cast) -> None:
    """A damage bonus when a racial reroll lands on the sworn enemy.
    `p1450` is a ref -- what is missing is that nothing announces a roll
    was a reroll."""


@power("f1522", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f1522(c: Cast) -> None:
    """The same gap as f1524, paying out on the reroll *missing*."""


@power("f1556", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f1556(c: Cast) -> None:
    """Uses one of two named racial powers as an immediate reaction when
    the sworn enemy bloodies you. Both are refs and `Bloodied` is a
    real event -- what is missing is a row using another row, which
    eleven item blocks also want."""


@power("f2181", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.oath_on_ranged()",))
def f2181(c: Cast) -> None:
    """Lends the oath's double roll to a named racial power. Same gap as
    f2163: the double roll is worked out inside `oath.py` and nothing
    borrows it from outside."""


@power("f1523", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p6189 on your oath target",
       on=Trigger(PowerUsed, _used("p6189"), "you use that racial power"))
def f1523(c: Cast) -> None:
    """"Used *against* your oath of enmity target" is who the power was
    aimed at rather than who it landed on, so this is `PowerUsed` and
    its `targets` rather than `Hit`: the penalty is printed off the
    declaration and arrives even when the attack misses."""
    me = c.me
    for foe in c.trigger.targets:
        if sworn(c.world, me, foe):
            c.penalty("attack", 1, on=foe, until=When.SONT)


@power("f1555", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1555(c: Cast) -> None:
    """Combat advantage from wearing the sworn enemy's face. Same naming
    gap as f1523, and nothing models a disguise either."""


@power("f1768", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, lambda w, me, ev: ev.actor == me,
                  "you spend a healing surge"))
def f1768(c: Cast) -> None:
    """A free shift on spending a surge, aimed at the sworn enemy if
    there is one. `SurgeSpent` fires from every site that decrements a
    pool, which is why this is declarable at all."""
    foe = oath_target(c)
    if foe is None:
        c.shift(1)
        return
    here = c.world.get(foe, Position)
    options = c.world.reachable_squares(c.me, 1)
    if here is None or not options:
        return
    closer = min(options, key=lambda sq: distance(sq, here.square))
    c.shift(1, to=closer)


# -- divine guidance, which has a ref in one place and not the others -------


@power("f2015", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_attack()",))
def f2015(c: Cast) -> None:
    """Extra damage on an ally's attack that a named class feature
    helped. `p5331` is a ref, so this is not a naming gap -- what is
    missing is that an attack made with somebody else's help is
    announced as an ordinary attack, with nothing recording the help."""


@power("f1716", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_attack()",))
def f1716(c: Cast) -> None:
    """Same gap as f2015, paying radiant damage instead."""


@power("f1724", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1724(c: Cast) -> None:
    """Swaps a pull for a slide inside a class feature's own body. The
    feature is named in prose with no ref, and even with one the forced
    movement is chosen inside it."""


# -- the granted card ------------------------------------------------------


@power("f2164", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2164(c: Cast) -> None:
    """A feat whose whole printed benefit is "you gain the f2164b
    power", which `c.grant_row` says in one line."""
    c.grant_row("f2164b", on=c.me, until=When.ENCOUNTER)


@power("f2164b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.unswear()",))
def f2164b(c: Cast) -> None:
    """Drops the oath and takes it again as a free action.

    The card of f2164. Half of it is ready -- `c.restore_use` hands
    `p3069` back -- and the half that is not is letting go: `oath.py`
    lays a labelled hold and nothing ends one early, so a row that
    restored the power without clearing the old oath would leave the
    avenger sworn to two creatures at once.
    """


@power("f2028", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_attack()",))
def f2028(c: Cast) -> None:
    """Three riders on another feat's granted card, `f2023b`, used
    against the sworn enemy. The card is a ref -- what is missing is
    the double roll, which is `oath.py`'s and not lendable, and the
    no-provoke, which is per attack rather than standing."""


# -- the godsworn boons ----------------------------------------------------


@power("f2738", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2738(c: Cast) -> None:
    """An ally's attack bonus on any critical hit. "Only one boon per
    critical" is what `usage=ENCOUNTER` cannot say and the single
    grant here does: the row hands out one bonus per firing."""
    me = c.me
    near = [a for a in allies(c.world, me) if a != me and c.can_see(a)]
    if near:
        c.bonus("attack", 1, on=near[0], until=When.EONT)


@power("f2739", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2739(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.EONT, kind="feat")
