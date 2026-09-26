"""Assassin, level 2: the utilities.

Most of this tier is concealment. `c.conceal` now says it -- a -2 on
attacks against you that `resolve.attack` weighs against cover and takes
the larger of -- so a row whose Effect is "you gain concealment" is
written. What is still absent is *obscured terrain*: "the burst is lightly
obscured" is a zone that carries concealment for whoever stands in it,
which `c.grants_in` now says; `c.zone(..., blocks_sight=True)` is the
*totally* obscured one and is a different printed word.
"""

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
    STANDARD,
    AdjacencyGained,
    AttackDeclared,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Miss,
    Trigger,
    When,
    World,
    power,
    spread,
    targets_me,
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
    """Lightly obscured is concealment for whoever stands in it, which
    `c.grants_in` now says; the note here used to claim it could not be
    written, and that stopped being true when `c.conceal` landed."""
    patch = c.zone(c.area(), label=c.ref, until=When.EONT)
    c.grants_in(patch, "concealment", 2, side="any", kind="concealment")
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


_TARGETED = "you are targeted by a melee or ranged attack"


@power(
    "p12563",
    level=2,
    cls="assassin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger=_TARGETED,
    on=Trigger(AttackDeclared, targets_me, _TARGETED),
)
def p12563(c: Cast) -> None:
    """`AttackDeclared` is the window an interrupt owns, and it is the only
    one where the -2 is still read: by `Hit` the defence has been compared.
    The Stealth check is not rolled -- there are no skills here -- so the
    hiding it buys is applied outright when the blow goes wide."""
    foe = getattr(c.trigger, "attacker", None)
    c.conceal(on=c.me, until=When.EONT)

    def went_wide(ev: Miss) -> None:
        if ev.target == c.me and (foe is None or ev.attacker == foe):
            c.hide(from_=foe)

    c.watch(Miss, went_wide, until=When.EOT, once=True)


@power(
    "p13802",
    level=2,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.ZONE],
)
def p13802(c: Cast) -> None:
    """Lightly obscured, so concealment rather than `blocks_sight`, and
    `side="any"` because the printed line makes no distinction: the murk
    covers whoever is standing in it."""
    murk = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
    c.grants_in(murk, "concealment", 2, side="any", kind="concealment")
