"""Assassin, level 6: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    CloseBurst,
    Event,
    Hit,
    Keyword,
    Relation,
    RelationCleared,
    Trigger,
    When,
    World,
    ZoneExited,
    hits_me,
    power,
)
from combat_engine.engine.query import hidden_from


def must_be_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


def stopped_being_hidden(world: World, me: int, ev: Event) -> bool:
    """The `HIDDEN_FROM` relation was cleared, and I am the one it hid.

    `relations.set(HIDDEN_FROM, who, watcher)` names the hidden creature as
    the source, so that is the end to test.
    """
    return ev.kind_ is Relation.HIDDEN_FROM and ev.source == me


@power(
    "p12454",
    level=6,
    cls="assassin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger="you are hidden and become no longer hidden from an enemy",
    on=Trigger(
        RelationCleared, stopped_being_hidden, "you stop being hidden from an enemy"
    ),
)
def p12454(c: Cast) -> None:
    """"A space where you have cover or concealment" is not a destination the
    mover can be asked for, so the teleport goes wherever it can and the hide
    follows -- which is the outcome the printed line is buying."""
    c.teleport(3)
    c.hide()


@power(
    "p13803",
    level=6,
    cls="assassin",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    once_per_round=True,
)
def p13803(c: Cast) -> None:
    """Climbing at full speed is a movement mode; the long jump is the same
    distance over flat ground and needs nothing granted."""
    c.mode("climb", c.speed_of(), until=When.EOT, on=c.me)
    c.move(c.speed_of())


@power(
    "p13805",
    level=6,
    cls="assassin",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
)
def p13805(c: Cast) -> None:
    c.invisible(on=c.me, until=When.SONT)
    c.teleport(c.speed_of())


@power(
    "p15915",
    level=6,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p15915(c: Cast) -> None:
    """Standing on water is terrain the engine does not have; ignoring rough
    ground is the half of the sentence it does."""
    c.ignores_difficult(on=c.me, until=When.SONT)


@power(
    "p9427",
    level=6,
    cls="assassin",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    requires=must_be_hidden,
    requires_text="must be hidden",
)
def p9427(c: Cast) -> None:
    """Which enemies you stay hidden from depends on cover and concealment at
    the far end, neither of which is asked here; the hide is reapplied whole."""
    c.move(c.speed_of())
    c.hide()


@power(
    "p9428",
    level=6,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW, Keyword.ZONE],
)
def p9428(c: Cast) -> None:
    """The concealment inside is `c.grants_in`, which did not exist when
    this was written -- the note said it could not be said and has been
    true only up to today. The zone also carries the other half of the
    printed line: going unseen the moment you step out of it."""
    patch = c.zone(c.area(), label=c.ref, until=When.EONT)
    c.grants_in(patch, "concealment", 2, side="any", kind="concealment")

    def slipped_out(ev: ZoneExited) -> None:
        if ev.zone == patch and ev.actor == c.me:
            c.invisible(on=c.me, until=When.EOT)

    c.watch(ZoneExited, slipped_out, until=When.EONT)


@power(
    "p9429",
    level=6,
    cls="assassin",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
)
def p9429(c: Cast) -> None:
    c.teleport(5)
    c.invisible(on=c.me, until=When.SONT)


@power(
    "p13804",
    level=6,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.ZONE],
)
def p13804(c: Cast) -> None:
    """Totally obscured, so `blocks_sight` rather than the concealment
    `p13802` lays -- `cover_between` reads the flag.

    "To creatures other than you" is dropped: the flag is a property of the
    ground and has no side, so the assassin is blinded by his own dark. The
    Sustain's "you must be in the zone" is dropped too -- sustaining asks
    for an action and never asks where the sustainer is standing.
    """
    c.zone(
        c.area(), label=c.ref, until=When.EONT, blocks_sight=True, sustain=MINOR
    )
