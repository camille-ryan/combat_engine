"""Avenger feats, the second batch.

`avenger.py` holds the first and this one runs on the same rail: every
row turns on "your oath of enmity target", and `oath.sworn` is the
question the oath itself asks, imported rather than re-derived.

This list is unusually writable for a race-gated one, because the
avenger's racial feats name their power by ref -- `p1450`, `p1831`,
`p7548`, `p8278`, `p1628`, `p2483`, `p2484`, `p1448`, `p6189` -- rather
than in prose. Only change shape still arrives as a name.

The class's own second feature is `p5331`, and all three rows that ride
on it are written: it is an interrupt, so `PowerUsed.trigger` carries
the ally and the enemy it was played for, and nothing has to be handed
over for them to be found.

`oath.py` exports `better_of_two` as well as `sworn`, which is what
makes the four rows lending the oath's double roll writable -- the roll
is made in the feat's own `AttackRolled` watcher under the feat's own
printed gates, rather than borrowed out of the oath.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.content.powers.avenger.oath import (
    OATH as OATH_LABEL,
)
from combat_engine.content.powers.avenger.oath import (
    better_of_two,
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
    AttackRolled,
    Cast,
    DamageType,
    Hit,
    PowerResolved,
    PowerUsed,
    SurgeSpent,
    Trigger,
    When,
    power,
)
from combat_engine.engine.basic import RANGED
from combat_engine.engine.components import Position
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    squares,
)

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


def _oath_hits_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and sworn(world, me, ev.attacker)


def _alone_with(c: Cast, victim: int) -> bool:
    """"No other enemy adjacent to you", the oath's own condition."""
    return not any(
        foe != victim and c.adjacent(foe) for foe in enemies(c.world, c.me)
    )


def _guided(ev: Any) -> tuple[int | None, int | None]:
    """The ally and the enemy `p5331` was played for.

    That card is an interrupt on the ally's `AttackRolled`, and
    `PowerUsed.trigger` carries the event it answered -- `ev.targets`
    names the ally it was aimed at and not the enemy being swung at.
    """
    rolled = getattr(ev, "trigger", None)
    return getattr(rolled, "attacker", None), getattr(rolled, "target", None)


def _on_guided_hit(c: Cast, pay: Callable[[Hit], None]) -> None:
    """Pay out on the swing `p5331` just rerolled, if it lands.

    `resolve.attack` re-reads the result after announcing the roll, so the
    `Hit` for that same swing is the next one this pair produces. Latched
    rather than `c.watch(once=True)`, which spends itself on the first
    `Hit` of any kind and would pay for somebody else's.
    """
    ally, foe = _guided(c.trigger)
    if ally is None or foe is None:
        return
    done: list[bool] = []

    def landed(ev: Hit) -> None:
        if done or ev.attacker != ally or ev.target != foe:
            return
        done.append(True)
        pay(ev)

    c.watch(Hit, landed, until=When.EOT, on=c.me, label=c.ref)


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
       reach=PERSONAL, target=SELF)
def f2163(c: Cast) -> None:
    """The oath's double roll, widened to ranged basic attacks.

    Re-read: nothing has to be borrowed from `oath.py`. `better_of_two`
    is that module's own function and is exported -- it raises the die in
    the `AttackRolled` window, which `resolve.attack` re-reads -- so the
    feat arms a second watcher of its own carrying the printed gates:
    within 10 squares of the sworn enemy, nothing else adjacent to you,
    and a ranged basic attack aimed at it.
    """
    me = c.me

    def twice(ev: AttackRolled) -> None:
        if ev.attacker != me or ev.power != RANGED:
            return
        if not sworn(c.world, me, ev.target):
            return
        if distance_between(c.world, me, ev.target) > 10:
            return
        if _alone_with(c, ev.target):
            better_of_two(c, ev)

    c.watch(AttackRolled, twice, until=When.ENCOUNTER, on=me, label=c.ref)


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


@power("f2289", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628 on your oath target",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f2289(c: Cast) -> None:
    """Extra damage on melee blows against the sworn enemy.

    The extra is fire and says so, so a creature that resists fire
    shrugs it off and takes the sword.
    """
    me = c.me
    if not any(sworn(c.world, me, f) for f in c.trigger.targets):
        return
    c.bonus(
        "damage", c.int_mod, on=me, until=When.EONT, dtype=DamageType.FIRE,
        when=lambda ctx: (
            not ctx.get("ranged", False)
            and sworn(c.world, me, ctx.get("target"))
        ),
    )


@power("f1527", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449",
       on=Trigger(PowerResolved, _used("p1449"), "you use that racial power"))
def f1527(c: Cast) -> None:
    """Five squares further on the racial teleport, ending beside the
    sworn enemy.

    Re-read: `c.extend_move` is the wrong shape for a *teleport*. A
    blink is point to point and ignores everything between, so a second
    hop of 5 from where the first one ended reaches exactly what a
    single hop of 10 would -- which is what "an extra 5 squares" comes
    to here, and it needs nothing the engine has not got.
    `PowerResolved` rather than `PowerUsed`, because the first hop has
    to have happened. The destination is not left to the decider: "as
    long as you end adjacent to your p3069 target" fixes it, so the
    nearest free square beside the sworn enemy is tried first.
    """
    foe = oath_target(c)
    here = c.world.get(c.me, Position)
    if foe is None or here is None:
        return
    occupied = squares(c.world, foe)
    beside = sorted(spread(occupied, 1) - occupied, key=lambda s: distance(s, here.square))
    for sq in beside:
        if distance(sq, here.square) <= 5 and c.teleport(5, to=sq):
            return


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


@power("f1556", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="your p3069 target hits you",
       on=Trigger(Hit, _oath_hits_me, "your oath target hits you"))
def f1556(c: Cast) -> None:
    """Uses one of two named racial powers when the sworn enemy's blow
    leaves you bloodied. `c.use_power` is the verb, and the choice
    between the two is made among the ones the character actually has.

    The bloodied half is checked after the hit rather than declared on
    `Bloodied`, because the card asks whether you *are* bloodied once
    the blow has landed, which is the board `Hit` leaves behind.

    Re-read: "your p3069 target" was dropped on the grounds that nothing
    on `Cast` reads the oath. `oath.sworn` does, this file imports it and
    every other row here asks it, so it is an ordinary trigger predicate
    and the row no longer answers every hit in the fight."""
    if not c.bloodied(on=c.me):
        return
    mine = [ref for ref in ("p2483", "p2484") if c.knows(ref) is not None]
    if not mine:
        return
    chosen = c.choose(mine, "which racial power to use") or mine[0]
    c.use_power(chosen)


@power("f2181", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2181(c: Cast) -> None:
    """The oath's double roll on a named racial power, when the sworn
    enemy is its only target.

    Re-read with f2163 and for the same reason. "The only target" is not
    a field on `AttackRolled`, so the use is caught one event earlier:
    targets are chosen before the body runs, so `PowerUsed.targets` is
    the whole set and the roll is judged against it.
    """
    me = c.me
    aimed: list[int] = []

    def declared(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "p1448":
            aimed[:] = list(ev.targets)

    def twice(ev: AttackRolled) -> None:
        if ev.attacker != me or ev.power != "p1448":
            return
        if aimed == [ev.target] and sworn(c.world, me, ev.target):
            better_of_two(c, ev)

    c.watch(PowerUsed, declared, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(AttackRolled, twice, until=When.ENCOUNTER, on=me, label=c.ref)


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
       reach=PERSONAL, target=SELF, todo=("c.in_form()",))
def f1555(c: Cast) -> None:
    """Re-aimed: the racial power is `p2472` and it is declared, so the
    naming gap is closed. What it is declared as is the problem --
    `out_of_combat=True`, because its whole printed effect is an
    appearance and a Bluff check, so it is never offered in a fight and
    never announces a use. And the clause is not "you use it" but
    "whose face you are wearing", which is the shape question 14 other
    rows want."""


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


@power("f2015", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p5331",
       on=Trigger(PowerUsed, _used("p5331"), "you guide an ally's swing"))
def f2015(c: Cast) -> None:
    """Extra necrotic on the swing `p5331` helped.

    Re-read: `c.on_granted_attack` was the wrong symbol. Nothing grants
    an attack here -- `p5331` is an interrupt that rerolls an ally's own
    swing -- and the pair it was played for is on the card's use, in
    `PowerUsed.trigger`. The die is credited to the avenger rather than
    to the ally, which is the one thing `c.flat` cannot say.
    """
    _on_guided_hit(
        c, lambda ev: c.flat(c.wis_mod, dtype=DamageType.NECROTIC, on=ev.target)
    )


@power("f1716", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p5331",
       on=Trigger(PowerUsed, _used("p5331"), "you guide an ally's swing"))
def f1716(c: Cast) -> None:
    """The same shape as f2015, paying a flat 5 radiant. The 21st-level
    step is epic and out of scope."""
    _on_guided_hit(
        c, lambda ev: c.flat(5, dtype=DamageType.RADIANT, on=ev.target)
    )


@power("f1724", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.pre_empt(ref, clause)",))
def f1724(c: Cast) -> None:
    """Swaps the pull `p5330` prints for a slide. The row is a ref and is
    declared; the pull happens inside its own body and nothing declines
    one clause of a row that is already running."""


# -- the granted card ------------------------------------------------------


@power("f2164", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2164(c: Cast) -> None:
    """A feat whose whole printed benefit is "you gain the f2164b
    power", which `c.grant_row` says in one line."""
    c.grant_row("f2164b", on=c.me, until=When.ENCOUNTER)


@power("f2164b", level=1, cls="", usage=ENCOUNTER, action=ActionType.MINOR,
       reach=PERSONAL, target=SELF, group=CHANNEL_DIVINITY)
def f2164b(c: Cast) -> None:
    """Drops the oath and takes it again, as the card of f2164.

    Re-read: letting go is `world.effects.end` on the hold `swear` lays,
    which is the same end `swear` performs itself when it re-swears --
    nothing new was needed. `c.restore_use` hands `p3069` back and
    `c.use_power` spends it again at this row's cost, which is the
    printed free action.

    What also has to go is the reroll watcher the earlier `p3069` left
    on the avenger: it closes over the creature it was sworn against, so
    a second use would leave two of them running and roll three dice.

    The channel divinity budget is the header's `group=`, which is what
    "only one such power per encounter" is.
    """
    me = c.me
    for who in list(c.suffering(OATH_LABEL, include_self=True)):
        for effect in list(c.world.effects.of(who)):
            if effect.source == me and OATH_LABEL in effect.label:
                c.world.effects.end(effect, c.ref)
    for effect in list(c.world.effects.of(me)):
        if effect.label.startswith(OATH):
            c.world.effects.end(effect, c.ref)
    c.restore_use(OATH, on=me)
    foes = [f for f in enemies(c.world, me) if c.can_see(f)]
    if foes:
        c.use_power(OATH, on=c.choose(foes, "swear against which enemy") or foes[0])


@power("f2028", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2028(c: Cast) -> None:
    """Three riders on another feat's card, `f2023b`, against the sworn
    enemy.

    Re-read: all three are sayable and none of them wants a granted
    attack. `c.no_provoke(from_=)` names the one creature the swing is
    safe from and is laid on the declaration, which is where "when you
    use" puts it; `better_of_two` is `oath.py`'s own roll and is
    exported, so the double roll is made here rather than borrowed; and
    the radiant die is paid on the hit, flat so that a critical does not
    maximise a die the card rolls separately.
    """
    me = c.me
    aimed: list[int] = []

    def declared(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != "f2023b":
            return
        aimed[:] = [f for f in ev.targets if sworn(c.world, me, f)]
        for foe in aimed:
            c.no_provoke(from_=foe, on=me, until=When.EOT)

    def twice(ev: AttackRolled) -> None:
        if ev.attacker != me or ev.power != "f2023b" or ev.target not in aimed:
            return
        if _alone_with(c, ev.target):
            better_of_two(c, ev)

    def landed(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "f2023b" and ev.target in aimed:
            c.flat(c.roll("1d6"), dtype=DamageType.RADIANT, on=ev.target)

    c.watch(PowerUsed, declared, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(AttackRolled, twice, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=c.ref)


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
