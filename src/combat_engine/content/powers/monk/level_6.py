"""Monk, level 6: the utilities.

One row is missing -- see the batch report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    Effect,
    Health,
    Keyword,
    Position,
    Square,
    Trigger,
    When,
    Window,
    World,
    both,
    enemy_within,
    hits_me,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import ForcedMove, Hit, Miss, MoveEnd, MoveStart

STANCE_KW = [Keyword.STANCE]


def _bloodied(world: World, eid: int) -> bool:
    pool = world.get(eid, Health)
    return pool is not None and pool.bloodied


def _beside(c: Cast, who: int) -> Square | None:
    """A free square next to that creature, for a row that must land there."""
    pos = c.world.get(who, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq == pos.square:
            continue
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _ends_with(c: Cast, posture: Effect, held: Effect | None) -> None:
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p11223",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11223(c: Cast) -> None:
    """A running jump is written as the movement it is; the Athletics
    bonus itself has no combat consequence."""
    c.ignores_difficult(until=When.EOT)
    c.move(c.speed_of())


@power(
    "p13159",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="an adjacent enemy misses you with an attack",
    on=Trigger(
        Miss, both(targets_me, enemy_within(1)), "an adjacent enemy misses you"
    ),
)
def p13159(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    landing = _beside(c, foe)
    if landing is not None:
        c.teleport(c.speed_of(), to=landing)
    c.grants_advantage(on=foe, to="me", until=When.EONT, once=True)


@power(
    "p13160",
    level=6,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p13160(c: Cast) -> None:
    """"Insubstantial while moving" is only true during the move, so it is
    put on at the start of one and taken off at the end rather than left
    standing, which would halve every blow all fight."""
    posture = c.stance()
    _ends_with(c, posture, c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power"))
    _ends_with(c, posture, c.phasing(until=When.ENCOUNTER))
    ghost: list[Effect] = []

    def thin(ev: MoveStart) -> None:
        if ev.actor == c.me and not ghost:
            held = c.insubstantial(on=c.me, until=When.ENCOUNTER)
            if held is not None:
                ghost.append(held)

    def solid(ev: MoveEnd) -> None:
        if ev.actor == c.me and ghost:
            c.world.effects.end(ghost.pop(), "stopped moving")

    _ends_with(
        c, posture,
        c.watch(MoveStart, thin, until=When.ENCOUNTER, window=Window.BEFORE),
    )
    _ends_with(c, posture, c.watch(MoveEnd, solid, until=When.ENCOUNTER))


@power(
    "p13161",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p13161(c: Cast) -> None:
    c.temp_hp(2 * c.con_mod, on=c.me)


@power(
    "p13162",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def p13162(c: Cast) -> None:
    """"Only as the first or the last action of your turn" is a legality
    rule about action order, which nothing measures; the move is written."""
    c.move(c.speed_of())


@power(
    "p16160",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with an attack",
    on=Trigger(Hit, hits_me, "an enemy hits you with an attack"),
)
def p16160(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p16161",
    level=6,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def p16161(c: Cast) -> None:
    c.surge(on=c.me)
    c.shift(2)


@power(
    "p16162",
    level=6,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p16162(c: Cast) -> None:
    """The "forced" modifier is read off the creature being shoved, not the
    one shoving, so a longer push is written by widening the proposal
    itself in the interrupt window. The Strength-check bonus is narrative."""
    posture = c.stance()

    def widen(ev: ForcedMove) -> None:
        if ev.source == c.me:
            ev.squares += 2

    _ends_with(
        c, posture,
        c.watch(ForcedMove, widen, until=When.ENCOUNTER, window=Window.BEFORE),
    )


@power(
    "p7463",
    level=6,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p7463(c: Cast) -> None:
    posture = c.stance()
    for defence in (AC, FORT, REF, WILL):
        _ends_with(c, posture, c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, kind="power"))


@power(
    "p7464",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p7464(c: Cast) -> None:
    c.save(on=c.me, bonus=c.wis_mod)
