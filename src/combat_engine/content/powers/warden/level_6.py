"""Warden, level 6: the utilities.

The interesting one is the stance that pins enemies in place: `MoveStart`
is the only cancellable movement event and it fires before a step, so it
can refuse a shift out of the warden's reach but knows nothing about where
a shift would land.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import MoveStart
from combat_engine.engine.query import team

from . import while_in

PRIMAL = [Keyword.PRIMAL]


@power(
    "p5119",
    level=6,
    cls="warden",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    trigger="you drop to 0 hit points or fewer",
    on=Trigger(Dropped, about_me, "you drop to 0 hit points or fewer"),
)
def p5119(c: Cast) -> None:
    """"As if you had spent a healing surge" -- the hit points, not the
    surge, so this heals a surge's worth without taking one."""
    c.heal(c.surge_value(c.me), on=c.me)


@power(
    "p5120",
    level=6,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.STANCE],
)
def p5120(c: Cast) -> None:
    held = c.stance(label=c.ref)
    while_in(
        c,
        held,
        *[
            c.bonus(d, 1, on=c.me, until=When.ENCOUNTER)
            for d in (AC, FORT, REF, WILL)
        ],
    )


@power(
    "p5121",
    level=6,
    cls="warden",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p5121(c: Cast) -> None:
    c.mode("swim", c.speed_of(), on=c.me, until=When.EOT)


@power(
    "p5122",
    level=6,
    cls="warden",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p5122(c: Cast) -> None:
    """The sure-footedness is for the shift and nothing longer, so it is put
    down again the moment the shift is over."""
    eased = c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(2)
    if eased is not None:
        c.world.effects.end(eased, "the shift is over")


@power(
    "p5592",
    level=6,
    cls="warden",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="an enemy's attack hits you and damages you",
    on=Trigger(Hit, hits_me, "an enemy's attack hits you"),
)
def p5592(c: Cast) -> None:
    """The printed trigger wants the hit *and* the damage; `Hit` is the only
    event an immediate reaction can answer while the attack is still the
    "triggering attack", so the damage half is assumed."""
    c.flat(c.level // 2, on=c.me)

    def against_a_mark(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and c.marked(who)

    c.bonus(
        "attack", c.con_mod, on=c.me, until=When.ENCOUNTER,
        kind="untyped", when=against_a_mark, once=True,
    )
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        kind="untyped", when=against_a_mark, once=True,
    )


@power(
    "p9848",
    level=6,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p9848(c: Cast) -> None:
    """Using a second wind is spending the surge and taking the defensive
    bonus that comes with it; the 2d6 rides on the same surge."""
    c.surge(on=c.me, bonus=c.roll("2d6"))
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.SONT)


@power(
    "p9849",
    level=6,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.STANCE],
)
def p9849(c: Cast) -> None:
    """Only half the printed sentence. `MoveStart` is cancellable and so can
    stop an enemy shifting out of the squares beside the warden; nothing
    cancellable knows where a move is going, so shifting *into* them is not
    refused."""
    held = c.stance(label=c.ref)

    def refuse(ev: MoveStart) -> None:
        if ev.kind_ != "shift" or ev.actor == c.me:
            return
        if team(c.world, ev.actor) is team(c.world, c.me):
            return
        if c.adjacent(ev.actor):
            ev.cancel("held in place")

    while_in(
        c,
        held,
        c.watch(
            MoveStart, refuse, until=When.ENCOUNTER, window=Window.BEFORE
        ),
    )
