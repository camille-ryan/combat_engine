"""Rogue, level 2.

The whole level is skill utilities, and the model has no skills: no
training, no checks, no rerolling one. Two of the five rows still land on
the battlefield -- a move and a hide, and a shift -- and are written out.
The other three *are* their check and nothing else, so they carry
`out_of_combat=True` and a note rather than an invented mechanic.

The Prerequisite lines gate *taking* these at character creation rather
than using them, so none of them is declared as a `requires`. A
**Requirement** is a different thing and is declared: it is checked every
time the row is used.

The rows printed in the later books follow below. Two of those are their
check and nothing else as well; the rest land on the board.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_OTHER_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Cover,
    Event,
    Hit,
    Keyword,
    Relation,
    Trigger,
    TurnEnd,
    When,
    World,
    enemy_within,
    power,
)
from combat_engine.engine.query import adjacent, allies, cover_between, enemies, team

MARTIAL = [Keyword.MARTIAL]


@power(
    "p1038",
    level=2,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1038(c: Cast) -> None:
    """Move your speed, then go unseen.

    The printed row waives the movement penalty on the check and keeps the
    normal requirements to hide; neither is rolled here, so what is left is
    the walk and the concealment `c.hide()` holds until something breaks it.
    """
    c.move(c.speed_of())
    c.hide()


@power(
    "p1395",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1395(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "p1039",
    level=2,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1039(c: Cast) -> None:
    c.note("p1039: a jump with a running start, its distance uncapped by speed")


@power(
    "p1040",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you dislike the result of a check you just made",
    out_of_combat=True,
)
def p1040(c: Cast) -> None:
    c.note("p1040: reroll that check, and the second result is the one that counts")


@power(
    "p1394",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1394(c: Cast) -> None:
    c.note("p1394: a check that normally costs a standard action, made as a minor")


def _is_marked(world: World, eid: int) -> bool:
    return bool(world.relations.sources(Relation.MARKED_BY, eid))


def _pincered(world: World, eid: int) -> list[int]:
    """Enemies this creature and one of its allies have between them."""
    return [
        foe
        for foe in enemies(world, eid)
        if adjacent(world, eid, foe)
        and any(adjacent(world, mate, foe) for mate in allies(world, eid))
    ]


def _has_a_pincer(world: World, eid: int) -> bool:
    return bool(_pincered(world, eid))


def _i_bloodied_it(world: World, me: int, ev: Event) -> bool:
    """"Your attack bloodies an enemy."

    `Bloodied` names only the creature that crossed the line -- no source --
    so who did it is read off the `DamageApplied` that caused it, which is
    the event immediately before it in the log.
    """
    who = getattr(ev, "actor", None)
    if who is None or team(world, who) is team(world, me):
        return False
    for e in reversed(world.bus.log):
        if e.kind == "DamageApplied" and getattr(e, "target", None) == who:
            return getattr(e, "source", None) == me
    return False


def _my_critical(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "attacker", None) == me and bool(getattr(ev, "critical", False))


def _prone_on_me(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "condition", None) is Condition.PRONE
    )


@power(
    "p10169",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy ends its turn adjacent to you",
    on=Trigger(TurnEnd, enemy_within(1), "an enemy ends its turn adjacent to you"),
)
def p10169(c: Cast) -> None:
    c.shift(3)


@power(
    "p10745",
    level=2,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10745(c: Cast) -> None:
    """The bonus hangs on `When.STANCE` so it goes when another stance is
    taken, which is the whole of what makes a stance a stance."""
    c.stance()
    c.bonus("speed", c.int_mod // 2, on=c.me, until=When.STANCE)


@power(
    "p10746",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="your attack bloodies an enemy or scores a critical hit",
    on=[
        Trigger(Bloodied, _i_bloodied_it, "your attack bloodies an enemy"),
        Trigger(Hit, _my_critical, "your attack scores a critical hit"),
    ],
)
def p10746(c: Cast) -> None:
    """Both printed triggers are declared: one is the `Bloodied` and the
    other is the `Hit` that carries `critical`, and declaring half of it
    would look finished."""
    ev = c.trigger
    who = getattr(ev, "target", None) or getattr(ev, "actor", None)
    if who is not None:
        c.flat(c.int_mod, on=who)


@power(
    "p10747",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10747(c: Cast) -> None:
    """The gate is asked of the attack rather than stored: cover is a fact
    about two positions and both of them move, so it is read at the moment
    the defence is."""
    me, world = c.me, c.world

    def sheltered(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        if attacker is None:
            return False
        shelter = cover_between(world, attacker, me, ranged=bool(ctx.get("ranged")))
        return shelter is not Cover.NONE

    for wall in (AC, FORT, REF, WILL):
        c.bonus(wall, 2, on=c.me, when=sheltered)


@power(
    "p10748",
    level=2,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
)
def p10748(c: Cast) -> None:
    if c.target is not None:
        c.swap(c.target)


@power(
    "p12510",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_is_marked,
    requires_text="must be marked",
)
def p12510(c: Cast) -> None:
    """A mark is a relation, not a condition somebody applied, so ending it
    is clearing whatever is holding it -- from every marker at once, since
    the row names the condition rather than one enemy's claim."""
    for marker in list(c.world.relations.sources(Relation.MARKED_BY, c.me)):
        c.world.relations.clear(Relation.MARKED_BY, marker, c.me, c.ref)


@power(
    "p12721",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p12721(c: Cast) -> None:
    c.note("p12721: a jump of up to half your speed, as a minor action")


@power(
    "p2495",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p2495(c: Cast) -> None:
    c.note("p2495: a Perception check with a bonus equal to your Charisma modifier")


@power(
    "p4474",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_has_a_pincer,
    requires_text="you and an ally must be adjacent to the same enemy",
)
def p4474(c: Cast) -> None:
    foe = c.choose(sorted(_pincered(c.world, c.me)), "who you have between you")
    if foe is not None:
        c.grants_advantage(on=foe, until=When.SONT)


@power(
    "p4475",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are knocked prone",
    on=Trigger(ConditionApplied, _prone_on_me, "you are knocked prone"),
)
def p4475(c: Cast) -> None:
    """Standing up is ending whatever is holding the creature down: prone
    hangs on the encounter clock rather than on a turn boundary, so nothing
    else would ever take it off."""
    for effect in list(c.world.effects.of(c.me)):
        if Condition.PRONE in effect.conditions:
            c.world.effects.end(effect, c.ref)
    c.shift(1)
