"""Seeker level 6."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.seeker import PRIMAL, bloodied_or_weakened, has_bow
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Keyword,
    Position,
    Trigger,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.events import Hit, Miss, MoveEnd, MoveStart


@power(
    "p11479",
    level=6,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p11479(c: Cast) -> None:
    """`Hit` carries the opportunity flag as a plain attribute rather than a
    field, which is what `by_opportunity` reads."""

    def spite(ev: Hit) -> None:
        if (
            ev.target == c.me
            and getattr(ev, "opportunity", False)
            and c.adjacent(ev.attacker)
        ):
            c.flat(c.str_mod, on=ev.attacker)

    c.watch(Hit, spite, until=When.EONT)


@power(
    "p9518",
    level=6,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=bloodied_or_weakened,
    requires_text="must be bloodied or weakened",
)
def p9518(c: Cast) -> None:
    c.temp_hp(2 * c.wis_mod, on=c.me)
    if c.is_(Condition.WEAKENED, on=c.me):
        c.save(on=c.me, against="weakened")


@power(
    "p9517",
    level=6,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.ILLUSION],
)
def p9517(c: Cast) -> None:
    """The form itself carries nothing, so it is a named hold with the two
    watches clocked on the encounter and taken down when it ends -- a second
    effect on `When.SUSTAIN` would confuse the sustain bookkeeping.

    "At least 3 squares from where you started" is measured, not counted:
    where the move began is remembered on `MoveStart`, which fires before
    the first step.
    """
    me, world = c.me, c.world
    form = c.effect(c.ref, until=When.SUSTAIN, on=me, sustain=MINOR)
    run: dict[str, Any] = {"from": None}

    def on_start(ev: MoveStart) -> None:
        if ev.actor == me:
            pos = world.get(me, Position)
            run["from"] = pos.square if pos else None

    def on_end(ev: MoveEnd) -> None:
        began = run["from"]
        if ev.actor == me and began is not None and distance(began, ev.at) >= 3:
            c.conceal(on=me, until=When.EONT)

    for kind, fn in ((MoveStart, on_start), (MoveEnd, on_end)):
        held = c.watch(kind, fn, until=When.ENCOUNTER, on=me)
        if form is not None:
            form.on_end.append(
                lambda h=held: world.effects.end(h, "the form ended")
            )


#: The class feature this row hands back and fires again. It is a declared
#: level 0 row, so every seeker `chargen` deals already knows it.
_THE_FEATURE = "p9501"


def _granted_by_the_feature(world: World, me: int, ev: Any) -> bool:
    """Is this a miss with the swing that `_THE_FEATURE` granted?

    Not any miss of mine, which is what the printed Trigger would come to
    if it were read as "you miss with a ranged basic attack" -- a seeker
    shooting on its own turn would hand itself a second shot every time.

    A granted swing is a use running *inside* the use that granted it, and
    `dsl.running_below` is the one way to see that from here. The stack is
    walked rather than peeked at: the swing is one use down and the feature
    is the next, and an interrupt between them would add a third.
    """
    from combat_engine.engine.dsl import running_below

    if getattr(ev, "attacker", None) != me:
        return False
    seen = None
    while True:
        below = running_below(seen)
        if below is None or below is seen:
            return False
        if below.ref == _THE_FEATURE:
            return True
        seen = below


@power(
    "p12792",
    level=6,
    cls="seeker",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=has_bow,
    requires_text="must be wielding a bow",
    trigger="you miss with the ranged basic attack the class feature granted",
    on=Trigger(
        Miss,
        _granted_by_the_feature,
        "you miss with the ranged basic attack the class feature granted",
    ),
)
def p12792(c: Cast) -> None:
    """Hand the feature's use back and spend it again, at once.

    Refused for a long while for naming a class feature nothing had
    declared. It is declared -- `p9501`, a level 0 row -- and the two
    halves are `c.restore_use` and a second `use`.

    `reentrant=True` on the second use is not optional and is not a
    loosening. The feature is still on the stack: the swing that just
    missed is running inside it, so the in-flight guard would refuse the
    repeat, and the use it has already spent would refuse it again. This
    row is once a fight, so the repeat cannot chain.
    """
    from combat_engine.engine.dsl import use

    if not c.restore_use(_THE_FEATURE):
        return
    use(
        c.world, c.me, _THE_FEATURE,
        trigger=c.trigger, reentrant=True,
    )
