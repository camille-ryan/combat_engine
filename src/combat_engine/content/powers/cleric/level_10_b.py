"""Cleric, level 10: the rest of the utilities. Nothing here rolls an attack.

`p12412` puts the penalty on the live result rather than on the enemy.
`c.reroll_attack` throws a fresh die and shifts the total by the difference;
a modifier hung on the attacker is not read again, because `resolve.attack`
recomputes the outcome from `result.natural` and `result.total` alone once
the roll's window closes. So the number is taken off the total, and the
critical is left to that recomputation -- a fresh 20 still crits, penalty or
no, which is the printed rule.

`p12619` and `p9987` are both declared on `DamageRolled`: that is the one
moment the number exists and has not yet come off anybody, and by the time a
`Hit` is announced there is nothing left to reduce.

`p12620`'s wall is laid square by square as `p60`'s is -- `Range` has no
wall shape -- and its four-square height has nowhere to go, the board being
flat. Its bonus is refreshed on `MoveEnd` rather than on `ZoneEntered`,
because the printed line shelters the squares *beside* the wall too and a
zone only announces its own.

`p7101` moves each save-ends hold across by ending it on the ally and laying
an equivalent on the cleric, carrying the conditions, the burn and the
modifiers. Relations and armed triggers stay behind with the original: those
name the creature they were set against, and re-pointing them would be
inventing rather than transferring.

`p11621`'s advisor reaches the board as a conjuration in its square; the
knowledge-check half of the printed line has no skills to hang on.
`p13930`'s Athletics and Acrobatics bonuses are the same, so only the surge,
the temporary hit points and the speed are written. Neither shadow row
carries its printed shadow keyword: `Keyword` has no such word.

`p9987`'s Special -- regaining the row when a Channel Divinity power is used
-- has nothing to key off: there is no header field that marks a row as one.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    STANDARD,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    Effect,
    Event,
    Health,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Trigger,
    TurnStart,
    When,
    World,
    ZoneEntered,
    get,
    power,
    spread,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone

DIVINE = [Keyword.DIVINE]
DIVINE_CONJURATION = [Keyword.CONJURATION, Keyword.DIVINE]
DIVINE_HEALING = [Keyword.DIVINE, Keyword.HEALING]

_CRIT_ON_MY_SIDE = "an enemy within 5 squares scores a critical hit on you or an ally"
_MY_SIDE_HURT = "you or an ally within 5 squares takes damage"
_ALLY_HURT_BY_AN_ATTACK = "an ally within 5 squares takes damage from an attack"


def _crit_on_my_side(radius: int) -> Callable[[World, int, Event], bool]:
    """An enemy within `radius` has just rolled a critical on my side.

    The burst measures the *enemy*, which is what "an enemy in the burst"
    says, while the creature struck only has to be one of mine.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        struck = getattr(ev, "target", None)
        foe = getattr(ev, "attacker", None)
        result = getattr(ev, "result", None)
        if struck is None or foe is None or not (result and result.critical):
            return False
        if team(world, struck) is not team(world, me):
            return False
        if team(world, foe) is team(world, me):
            return False
        return distance_between(world, me, foe) <= radius

    return check


def _my_side_hurt(
    radius: int, *, others_only: bool = False, by_attack: bool = False
) -> Callable[[World, int, Event], bool]:
    """Somebody on my side, within `radius`, is about to take damage."""

    def check(world: World, me: int, ev: Event) -> bool:
        struck = getattr(ev, "target", None)
        if struck is None or getattr(ev, "amount", 0) <= 0:
            return False
        if others_only and struck == me:
            return False
        if team(world, struck) is not team(world, me):
            return False
        if by_attack and get(getattr(ev, "detail", "")) is None:
            return False
        return distance_between(world, me, struck) <= radius

    return check


def _not_bloodied(world: World, me: int) -> bool:
    health = world.get(me, Health)
    return health is not None and not health.bloodied


@power(
    "p11621",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=DIVINE_CONJURATION,
)
def p11621(c: Cast) -> None:
    """One square of advisor. What it advises on is a knowledge check, and
    there are no skills for it to help with."""
    free = sorted(
        sq
        for sq in spread({c.here}, 5)
        if sq != c.here
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )
    where = c.choose(free, f"{c.ref}: where the advisor stands")
    if where is not None:
        c.conjure(where, label=c.ref, until=When.SUSTAIN, sustain=MINOR)


@power(
    "p12412",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_CRIT_ON_MY_SIDE,
    on=Trigger(AttackRolled, when=_crit_on_my_side(5), text=_CRIT_ON_MY_SIDE),
)
def p12412(c: Cast) -> None:
    """The penalty is taken off the total the reroll left behind; the hit
    and the critical are settled from it after this window closes."""
    result = getattr(c.trigger, "result", None)
    if result is not None and c.reroll_attack():
        result.total -= c.cha_mod
        c.note(f"{c.ref}: rolled again at -{c.cha_mod}")


@power(
    "p12618",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=DIVINE_HEALING,
)
def p12618(c: Cast) -> None:
    """"As if he or she had spent a healing surge" -- the target's own
    quarter, and no surge leaves anybody's pool."""
    c.heal(c.surge_value(of=c.target))
    c.bonus("attack", 2, until=When.EONT, kind="power")


@power(
    "p12619",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
    trigger=_MY_SIDE_HURT,
    on=Trigger(DamageRolled, when=_my_side_hurt(5), text=_MY_SIDE_HURT),
)
def p12619(c: Cast) -> None:
    """The blow lands and arrives empty. Cancelling the damage rather than
    the attack is what "any other effects still apply" asks for."""
    ev = c.trigger
    if ev is None:
        return
    spared = getattr(ev, "amount", 0)
    ev.amount = 0
    ev.cancel(c.ref)
    c.note(f"{c.ref}: {spared} damage turned aside")


@power(
    "p12620",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=DIVINE_CONJURATION,
)
def p12620(c: Cast) -> None:
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(8)]
    run = [sq for sq in run if c.world.grid.inside(sq)]
    if not run:
        return
    wall = c.zone(run, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    shelter = spread(set(run), 1)
    held = c.world.get(wall, Zone)
    given: dict[int, Effect] = {}

    def refresh(who: int) -> None:
        near = bool(squares_of(c.world, who) & shelter)
        if near and who not in given:
            got = c.bonus(AC, 2, on=who, until=When.ENCOUNTER, kind="power")
            if got is not None:
                given[who] = got
        elif not near and who in given:
            c.world.effects.end(given.pop(who), "stepped away from the wall")

    def moved(ev: MoveEnd) -> None:
        if ev.actor == c.me or ev.actor in c.allies():
            refresh(ev.actor)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == wall and ev.actor in c.enemies():
            c.immobilized(on=ev.actor, until=When.SOTNT)

    def cleanup() -> None:
        for who in list(given):
            c.world.effects.end(given.pop(who), "the wall went out")

    subs = [
        c.world.bus.on(MoveEnd, moved),
        c.world.bus.on(ZoneEntered, entered),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        held.effect.on_end.append(cleanup)
    for friend in (c.me, *c.allies()):
        refresh(friend)


@power(
    "p13930",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p13930(c: Cast) -> None:
    """"Loses a healing surge" is not a heal: the surge is spent and pays
    out as temporary hit points instead."""
    friend = c.target
    if friend is None:
        return
    if c.spend_surge(on=friend):
        c.temp_hp(c.surge_value(of=friend), on=friend)
    c.bonus("speed", 2, on=friend, until=When.ENCOUNTER, kind="power")


@power(
    "p13931",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p13931(c: Cast) -> None:
    """Both halves are one hold, so sustaining keeps them together and the
    weakness cannot be shaken off while the protection stays."""
    friend = c.target
    if friend is None:
        return
    c.world.effects.apply(
        friend,
        c.me,
        When.SUSTAIN,
        label=c.ref,
        conditions=(Condition.INSUBSTANTIAL, Condition.WEAKENED),
        sustain_cost=MINOR,
    )


@power(
    "p3683",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(20),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
)
def p3683(c: Cast) -> None:
    friend = c.target
    if friend is None:
        return
    mine = squares_of(c.world, c.me)
    landing = sorted(
        sq
        for sq in spread(mine, 1) - mine
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    dest = c.choose(landing, f"{c.ref}: where the ally arrives")
    if dest is not None:
        c.teleport(c.distance(friend), who=friend, to=dest)


@power(
    "p7101",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE,
)
def p7101(c: Cast) -> None:
    """Each hold is ended on the ally and laid again on the cleric, which is
    the only way an effect changes hands: `Effect.owner` is read when the
    thing is installed and when it is taken off, not while it stands.

    The +4 goes on as each new hold's own `save_mod`, so it applies to
    exactly the effects that were transferred and to nothing else.
    """
    friend = c.target
    if friend is None:
        return
    for eff in list(c.world.effects.of(friend)):
        if eff.when is not When.SAVE_ENDS:
            continue
        c.world.effects.end(eff, c.ref)
        c.world.effects.apply(
            c.me,
            eff.source,
            When.SAVE_ENDS,
            label=eff.label,
            conditions=eff.conditions,
            mods=[(c.me if eid == friend else eid, mod) for eid, mod in eff.mods],
            ongoing=eff.ongoing,
            save_mod=eff.save_mod + 4,
            escalate=eff.escalate,
        )


@power(
    "p7888",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE_HEALING,
    requires=_not_bloodied,
    requires_text="you must not be bloodied",
)
def p7888(c: Cast) -> None:
    """Regeneration is not something the engine holds, so it is written out
    as healing at the start of the ally's turns. The cleric being bloodied
    is read there rather than on `Bloodied`: the pay-out is the only moment
    the hold does anything, so ending it then is the same board and one
    watcher instead of two.
    """
    friend = c.target
    if friend is None:
        return
    me = c.me
    hold: list[Effect] = []

    def regenerate(ev: TurnStart) -> None:
        if ev.actor != friend or ev.ghost:
            return
        if c.bloodied(on=me):
            if hold:
                c.world.effects.end(hold[0], "the cleric was bloodied")
            return
        c.heal(10, on=friend)

    hold.append(
        c.watch(
            TurnStart,
            regenerate,
            until=When.ENCOUNTER,
            on=friend,
            label=f"{c.ref} regeneration",
        )
    )


@power(
    "p7889",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=DIVINE_HEALING,
)
def p7889(c: Cast) -> None:
    """A printed "can": the surge is the target's, so the target is asked."""
    if c.may("spend a healing surge", who=c.target):
        c.surge(bonus=c.roll("2d6"))


@power(
    "p9987",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
    trigger=_ALLY_HURT_BY_AN_ATTACK,
    on=Trigger(
        DamageRolled,
        when=_my_side_hurt(5, others_only=True, by_attack=True),
        text=_ALLY_HURT_BY_AN_ATTACK,
    ),
)
def p9987(c: Cast) -> None:
    ev = c.trigger
    if ev is None:
        return
    spared = min(getattr(ev, "amount", 0), 5 + c.cha_mod)
    ev.amount -= spared
    c.note(f"{c.ref}: {spared} damage turned aside")
