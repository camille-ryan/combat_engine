"""Warlord, level 10: utility. Nothing here rolls an attack of its own.

`p1146` has no ready-made predicate. `ally_within` reads the creature the
event is *about*, which on an attack is the one swinging, so it answers "an
ally attacks" rather than "an ally is hit"; and the printed line narrows it
to a melee or a ranged attack, which is read off the power the event names.
The dispatcher only re-aims a row whose printed target is a single enemy, so
the ally is read off the event as well.

`p1147` catches the burn in the `Window.BEFORE` half of `TurnStart`.
`Effects._on_turn_start` is an ordinary listener subscribed when the world
was built, so it is always ahead of anything a row arms later -- and a
watcher that worked out who was sheltered in the *after* half would have
worked it out a beat after the damage had already been dealt.

Its second clause, "nor making saving throws to end it", is written as the
save failing. Not rolling and rolling a failure come to the same board, and
`SavingThrow` is announced to be read back rather than to be refused --
`Effects.save` honours `saved` and ignores `cancelled`.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackRolled,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_melee,
    by_ranged,
    power,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.query import adjacent, distance_between, team

MARTIAL = [Keyword.MARTIAL]

_ALLY_IS_HIT = "an ally is hit by a melee or a ranged attack"


def _ally_about_to_be_hit(radius: int) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        result = getattr(ev, "result", None)
        if who is None or who == me or not (result and result.hit):
            return False
        if team(world, who) is not team(world, me):
            return False
        if distance_between(world, me, who) > radius:
            return False
        return by_melee(world, me, ev) or by_ranged(world, me, ev)

    return check


@power(
    "p1112",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
)
def p1112(c: Cast) -> None:
    """A printed "can": the surge is the target's, so the target is asked."""
    if c.may("spend a healing surge", who=c.target):
        c.surge()
    c.save(on=c.target)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, until=When.EONT, kind="power")


@power(
    "p1146",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_IS_HIT,
    on=Trigger(AttackRolled, when=_ally_about_to_be_hit(10), text=_ALLY_IS_HIT),
)
def p1146(c: Cast) -> None:
    """Interrupted before the blow arrives, so the shift can take the ally
    out of a close or area attack the way the printed line intends."""
    friend = getattr(c.trigger, "target", None) or c.target
    if friend is not None:
        c.shift(1 + c.int_mod, who=friend)


@power(
    "p1147",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1147(c: Cast) -> None:
    me = c.me
    sheltered: set[int] = set()

    def at_turn_start(ev: TurnStart) -> None:
        sheltered.discard(ev.actor)
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me) and adjacent(
            c.world, me, ev.actor
        ):
            sheltered.add(ev.actor)

    def no_burn(ev: DamageRolled) -> None:
        # `Effects._on_turn_start` names the burning effect itself as the
        # detail, and an effect's `str` carries the word only when it
        # actually has ongoing damage on it.
        if ev.target in sheltered and "ongoing" in getattr(ev, "detail", ""):
            ev.amount = 0
            ev.cancel(c.ref)

    def no_save(ev: SavingThrow) -> None:
        if ev.actor in sheltered and "ongoing" in ev.against:
            ev.saved = False

    hold = c.watch(
        TurnStart,
        at_turn_start,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )
    hold.subs.append(
        c.world.bus.on(DamageRolled, no_burn, window=Window.BEFORE, owner=me)
    )
    hold.subs.append(
        c.world.bus.on(SavingThrow, no_save, window=Window.BEFORE, owner=me)
    )
