"""Rogue, level 6: utility, and every row of it printed behind a skill.

The Prerequisite lines gate *taking* these at character creation rather
than using them, so none is declared as a `requires` -- the reading
`level_2.py` settled.

Two rows are their check and nothing else and carry `out_of_combat=True`.
`p1506` is one of them for a second reason as well: nothing announces the
loss of cover or concealment, so its printed Trigger has no event to hang
`on=` from and is kept as prose for the card, the way `p922` is.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MOVE,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    AttackRolled,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Relation,
    Trigger,
    When,
    World,
    power,
    would_hit_me,
)

MARTIAL = [Keyword.MARTIAL]

_HIT_AGAINST_WILL = "you are hit by an attack against your Will"


def _would_hit_my_will(world: World, me: int, ev: Event) -> bool:
    return would_hit_me(world, me, ev) and getattr(ev, "vs", None) is WILL


@power(
    "p1042",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1042(c: Cast) -> None:
    """A mark is a relation, not a condition somebody applied, so shaking it
    off is clearing whatever is holding it -- from every marker at once,
    since the row names the condition rather than one enemy's claim."""
    for marker in c.world.relations.sources(Relation.MARKED_BY, c.me):
        c.world.relations.clear(Relation.MARKED_BY, marker, c.me, c.ref)
    c.shift(c.speed_of())


@power(
    "p1043",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HIT_AGAINST_WILL,
    on=Trigger(AttackRolled, when=_would_hit_my_will, text=_HIT_AGAINST_WILL),
)
def p1043(c: Cast) -> None:
    """Raised on the roll, which is the window where the defence is read
    again -- so the +2 applies to the very attack that triggered it. `Hit`
    would be too late: by then the comparison has been made."""
    c.bonus(WILL, 2, on=c.me, until=When.EONT)


@power(
    "p365",
    level=6,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p365(c: Cast) -> None:
    """The move is the climb. The check is not rolled, so what is left is
    the +4, and it is granted only while the rogue is actually on a wall --
    `c.moving_as` asks what it is doing, where `Movement.modes` only ever
    said what it could do."""
    if c.moving_as("climb"):
        c.bonus("speed", 4, on=c.me, until=When.EOT)
    c.move(c.speed_of())


@power(
    "p1397",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1397(c: Cast) -> None:
    c.note("p1397: +2 to Charisma checks for each target until your next turn ends")


@power(
    "p1506",
    level=6,
    cls="rogue",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you are hidden and lose cover or concealment against an enemy",
    out_of_combat=True,
)
def p1506(c: Cast) -> None:
    c.note("p1506: stay hidden from that enemy, and need no cover to stay so")
