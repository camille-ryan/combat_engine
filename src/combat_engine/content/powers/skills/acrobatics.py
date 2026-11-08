"""Acrobatics, all nine of its skill powers.

`cls` is the skill rather than a class -- see the package docstring. Every
row here is Personal, so each `Cast` call that defaults to `c.target` is
aimed back with `on=c.me`; six of the nine do nothing but move the
character a square or three out of trouble.

Five print a Trigger and all five declare it with `on=`, since `trigger=`
on its own is prose nothing reads.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    Condition,
    Trigger,
    When,
    World,
    both,
    by_melee,
    enemy_within,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Cushioned,
    Fell,
    Hit,
    TurnEnd,
)
from combat_engine.engine.falling import SQUARES_PER_DIE
from combat_engine.engine.query import held_by, is_

SKILL = "acrobatics"

_HIT_BY_MELEE = "a melee attack hits you"
_TARGETED = "an enemy targets you with an attack"
_ENEMY_ENDS_TURN = "an enemy ends its turn adjacent to you"
_UNHURT_FALL = "you fall and take no damage"


def _is_grabbed(world: World, eid: int) -> bool:
    """The printed Requirement, asked where `usable` asks it.

    A column rather than a line in the body: this is an active minor
    action, so `dsl.use` re-reads it every time the row is offered -- the
    trait trap in `docs/AUTHORING.md` is about `action=NONE` rows, which
    are asked once at arming and refused for the rest of the fight.
    """
    return bool(held_by(world, eid))


def _is_prone(world: World, eid: int) -> bool:
    """There is something to stand up from.

    Not an invented Requirement: `actions._recovery` gates the ordinary
    stand on exactly this, so a creature that is not prone has no stand
    action at all and this row is the same action for a cheaper cost.
    Without the gate the row is offered to anybody, spends a minor action
    and ends no effect -- drawable and inert, which is a fault.
    """
    return is_(world, eid, Condition.PRONE)


def _softened_to_nothing(world: World, me: int, ev: Cushioned) -> bool:
    """Something took the whole of a fall off, which is one half of the line.

    `Cushioned.all_of_it` exists for exactly this sentence -- "takes no
    damage from the fall" -- so the row does not have to re-derive it from
    a `Fell` it cannot see the damage of.
    """
    return ev.actor == me and ev.all_of_it


def _too_short_to_hurt(world: World, me: int, ev: Fell) -> bool:
    """The other way to fall and take nothing: not far enough for a die.

    `falling.drop` rolls `squares // SQUARES_PER_DIE` dice, so a shorter
    drop rolls none and costs nothing. Read off the event rather than off
    the damage, because `Fell` is announced before the roll and no event
    afterwards says a fall hurt nobody.
    """
    return ev.actor == me and ev.squares < SQUARES_PER_DIE


@power(
    "p9295",
    level=2,
    cls=SKILL,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_prone,
)
def p9295(c: Cast) -> None:
    """Standing up is the end of the prone effect and nothing else --
    `actions.legal`'s own `stand` branch is the same two lines. What this
    row buys is the cheaper action, which is header data, so the body is
    the ordinary stand."""
    c.cure(Condition.PRONE, on=c.me)


@power(
    "p11527",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11527(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p11528",
    level=6,
    cls=SKILL,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    narrative=("skill:acrobatics",),
)
def p11528(c: Cast) -> None:
    """The move and the rough ground are exact.

    The remaining clause waives an acrobatics check for walking along a
    hand's-breadth of horizontal surface, and that is narrative: no board
    presents a ledge or a rope to balance along, so there is no check to
    waive. The claim is about the circumstance and not about the skill --
    acrobatics is rolled in this tree, and this row rolls it nowhere.
    """
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.move(max(0, c.speed_of() - 2))


@power(
    "p11529",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_HIT_BY_MELEE,
    on=Trigger(Hit, both(targets_me, by_melee), _HIT_BY_MELEE),
)
def p11529(c: Cast) -> None:
    """The bonus goes on the comparison, not on as a modifier.

    An immediate interrupt answers a `Hit` in `Window.BEFORE`, which is
    inside `resolve.roll` and before its confirm callback -- so raising the
    defence the blow was measured against and re-settling turns a hit that
    cleared by one into a `Miss`, announced as one. A `c.bonus` cannot do
    it: the sum was taken when the die landed. `p12245` is the same shape,
    and `c.settle_attack` is what keeps a critical from surviving a verdict
    it no longer reaches.

    "All defences" comes to the one the attack rolled against, which is the
    only one the outcome reads.
    """
    ev = c.trigger
    result = getattr(ev, "result", None)
    if result is None:
        return
    got = c.check(SKILL)
    result.target_defence += got.total // 10
    c.settle_attack()
    if not result.hit:
        c.shift(1)


@power(
    "p16502",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_TARGETED,
    on=Trigger(AttackDeclared, targets_me, _TARGETED),
    dropped=("c.retarget()",),
)
def p16502(c: Cast) -> None:
    """The shift is exact and is the whole of what plays.

    The dropped clause hands the *attacker* a fresh choice of target when
    the shift has carried this creature out of range. `c.redirect` is the
    wrong half of it -- that one moves the blow where the interrupting row
    says, which is a different permission -- and nothing lets the creature
    that declared an attack pick again.
    """
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p9296",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_ENEMY_ENDS_TURN,
    on=Trigger(TurnEnd, enemy_within(1), _ENEMY_ENDS_TURN),
)
def p9296(c: Cast) -> None:
    """`enemy_within(1)` is the whole of the printed line: `TurnEnd` names
    the creature whose turn ended in `actor`, and adjacency is a distance of
    one."""
    c.shift(1)


@power(
    "p11530",
    level=10,
    cls=SKILL,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_UNHURT_FALL,
    on=(
        Trigger(Cushioned, _softened_to_nothing, _UNHURT_FALL),
        Trigger(Fell, _too_short_to_hurt, _UNHURT_FALL),
    ),
)
def p11530(c: Cast) -> None:
    """Two triggers for one printed sentence, because the engine has two
    ways for a fall to cost nothing and neither event says the other: a
    listener taking all of it off announces `Cushioned`, and a drop too
    short for a damage die announces only the `Fell`."""
    c.shift(3)


@power(
    "p16506",
    level=10,
    cls=SKILL,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16506(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "p9297",
    level=10,
    cls=SKILL,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_grabbed,
    requires_text="you must be grabbed",
)
def p9297(c: Cast) -> None:
    """The grabbers are read **before** the attempt.

    A successful escape clears the relation, so asking afterwards finds
    nobody and the second clause would pay out never. Both of the printed
    halves are here: the skill is named, so the check is measured against
    Reflex rather than against whichever of the two this creature is
    better at.
    """
    holders = c.grabbed_by(on=c.me)
    if not c.escape(on=c.me, skill=SKILL):
        return
    for who in holders:
        c.grants_advantage(on=who, to="me", until=When.EOT)
