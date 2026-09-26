"""Monk, level 10: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    DamageType,
    Effect,
    Keyword,
    Position,
    Square,
    Trigger,
    When,
    about_me,
    both,
    by_me,
    by_melee,
    get,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import DamageRolled, Dropped, Hit, MoveEnd, TurnStart

STANCE_KW = [Keyword.STANCE]

ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _fire(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.FIRE in p.keywords


def _beside(c: Cast, who: int) -> Square | None:
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
    "p11231",
    level=10,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def p11231(c: Cast) -> None:
    c.surge(on=c.me, bonus=c.roll("2d6"))


@power(
    "p11232",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are prone at the start of your turn",
    on=Trigger(TurnStart, about_me, "your turn starts"),
)
def p11232(c: Cast) -> None:
    """Standing up is ending whatever is holding the monk down; the prone
    half of the printed trigger is asked here, since no predicate reads a
    condition off the creature being offered the row."""
    for eff in list(c.world.effects.of(c.me)):
        if Condition.PRONE in eff.conditions:
            c.world.effects.end(eff, "stood up")


@power(
    "p13176",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an attack that deals a specific damage type hits you",
    on=Trigger(DamageRolled, targets_me, "you are about to take typed damage"),
)
def p13176(c: Cast) -> None:
    """Declared on the damage rather than on the hit: the type is not known
    until the damage is rolled, and this row is entirely about the type."""
    kind = getattr(c.trigger, "dtype", None)
    if kind is None or kind is DamageType.UNTYPED:
        return
    c.resist(3 + c.wis_mod, kind, until=When.EONT)


@power(
    "p13177",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p13177(c: Cast) -> None:
    c.resist(5, until=When.EONT)


@power(
    "p13178",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you hit an enemy with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit an enemy with a melee attack"),
)
def p13178(c: Cast) -> None:
    c.heal(5 + c.wis_mod, on=c.me)


@power(
    "p13179",
    level=10,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p13179(c: Cast) -> None:
    posture = c.stance()

    def early(ev: TurnStart) -> None:
        if ev.actor == c.me and not ev.ghost:
            c.save(on=c.me, bonus=-3)

    _ends_with(c, posture, c.watch(TurnStart, early, until=When.ENCOUNTER))


@power(
    "p16174",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take acid, cold, fire, lightning, or thunder damage",
    on=Trigger(DamageRolled, targets_me, "you are about to take elemental damage"),
)
def p16174(c: Cast) -> None:
    """The aftereffect hangs off the first resistance ending, which is the
    only moment "afterwards" happens."""
    kind = getattr(c.trigger, "dtype", None)
    if kind not in ELEMENTS:
        return
    held = c.resist(5, kind, until=When.SONT)
    if held is not None:
        held.on_end.append(
            lambda: c.resist(3, kind, until=When.ENCOUNTER)
        )


@power(
    "p16175",
    level=10,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p16175(c: Cast) -> None:
    posture = c.stance()
    _ends_with(c, posture, c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power"))
    _ends_with(
        c, posture,
        c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_fire, kind="power"),
    )


@power(
    "p16176",
    level=10,
    cls="monk",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit an enemy with a melee attack"),
)
def p16176(c: Cast) -> None:
    """The second stat block is an at-will reaction for as long as the mark
    holds, so it is written into this row as a watch on the marked enemy
    moving under its own power. Forfeiting next turn's move action has
    nothing to write to and is dropped."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    held = c.mark(on=foe, until=When.ENCOUNTER)

    def chase(ev: MoveEnd) -> None:
        if ev.actor != foe or ev.kind_ == "forced":
            return
        landing = _beside(c, foe)
        if landing is not None:
            c.shift(c.speed_of(), to=landing)

    watcher = c.watch(MoveEnd, chase, until=When.ENCOUNTER)
    if held is None:
        return
    held.on_end.append(lambda: c.world.effects.end(watcher, "mark ended"))

    def gone(ev: Dropped) -> None:
        if ev.actor == foe:
            c.world.effects.end(held, "dropped to 0")

    c.watch(Dropped, gone, until=When.ENCOUNTER, once=True)


@power(
    "p7469",
    level=10,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage",
    on=Trigger(DamageRolled, targets_me, "you are about to take damage"),
)
def p7469(c: Cast) -> None:
    """`DamageRolled` carries a mutable amount, which is where "the damage
    is reduced by N" is written."""
    ev = c.trigger
    if ev is None:
        return
    ev.amount = max(0, ev.amount - (10 + c.wis_mod))


@power(
    "p7470",
    level=10,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7470(c: Cast) -> None:
    """Climbing is a mode, granted for the turn the climb happens in."""
    c.mode("climb", c.speed_of(), until=When.EOT)
    c.move(c.speed_of())
