"""Assassin, level 2: the utilities.

Most of this tier is concealment, and there is no concealment verb. Where a
row's whole printed Effect is "you gain concealment" or "the burst is lightly
obscured", the row is absent rather than approximated -- `c.zone(...,
blocks_sight=True)` is the wrong shape, because it blinds the caster too.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    AdjacencyGained,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Trigger,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.query import enemies, hidden_from


def must_be_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


def enemy_stepped_adjacent(world: World, me: int, ev: Event) -> bool:
    """An enemy moved into a square next to me -- not me closing on it.

    `AdjacencyGained` is emitted mirrored, so the copy worth answering is the
    one whose `actor` is me, and `mover` is what tells the two halves of
    "somebody became adjacent" apart.
    """
    return ev.actor == me and ev.mover == ev.other and ev.other in enemies(world, me)


@power(
    "p13800",
    level=2,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW],
)
def p13800(c: Cast) -> None:
    """The illusion is a conjuration, which is the only thing that occupies a
    square and can be walked around. The Insight-against-Bluff contest is a
    skill check and has nothing to roll against here."""
    free = [s for s in spread({c.here}, 2) if s != c.here and not c.in_squares([s])]
    if free:
        c.conjure(
            at=sorted(free)[0],
            label=c.ref,
            until=When.SUSTAIN,
            sustain=MINOR,
            speed=6,
        )


@power(
    "p13801",
    level=2,
    cls="assassin",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    requires=must_be_hidden,
    requires_text="must be hidden",
)
def p13801(c: Cast) -> None:
    """Where the move ends is the world's choice; "to a square within 2 of an
    enemy" is a destination constraint `c.move` does not take. Staying hidden
    is the half that carries the mechanics, and attacking breaks it already."""
    c.move(c.speed_of())
    c.hide(until=When.EOT)


@power(
    "p15914",
    level=2,
    cls="assassin",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.ZONE],
    trigger="an enemy enters a square adjacent to you",
    on=Trigger(
        AdjacencyGained, enemy_stepped_adjacent, "an enemy enters a square adjacent to you"
    ),
)
def p15914(c: Cast) -> None:
    """The lightly obscured burst cannot be said -- no concealment verb -- so
    only the escape is written."""
    c.shift(c.speed_of())


@power(
    "p9415",
    level=2,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    out_of_combat=True,
)
def p9415(c: Cast) -> None:
    c.note("p9415: darkvision until the end of your next turn, and one small light goes out")


@power(
    "p9416",
    level=2,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9416(c: Cast) -> None:
    """The concealment against everybody is dropped for want of a verb; being
    unseen by anything further off than 5 squares is written as it reads."""
    for foe in c.enemies():
        if c.distance(foe) > 5:
            c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "p9417",
    level=2,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9417(c: Cast) -> None:
    """The Requirement (dim light or darkness), the silence, and all three
    ways the effect ends early -- moving far, bright light, somebody walking
    into your space -- need a lighting model the engine has not got."""
    c.invisible(on=c.me, until=When.EONT)


@power(
    "p9418",
    level=2,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
    out_of_combat=True,
)
def p9418(c: Cast) -> None:
    c.note("p9418: allies within 5 squares roll Stealth with your modifier")
