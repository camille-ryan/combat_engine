"""Ardent, level 2: the utilities.

None of these is augmentable. Two printed rows are absent: one whose whole
effect is transferring power points, and one whose whole effect is a reach and
range increase.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    MOVE,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    REACTION,
    REF,
    WILL,
    Cast,
    CloseBurst,
    DamageRolled,
    Keyword,
    Melee,
    Ranged,
    SurgeSpent,
    Trigger,
    TurnStart,
    When,
    ally_within,
    power,
)

PSIONIC = [Keyword.PSIONIC]


def _friends(c: Cast, radius: int, *, mine: bool = False) -> list[int]:
    return [a for a in c.within(radius, side="ally") if mine or a != c.me]


@power(
    "p10279",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p10279(c: Cast) -> None:
    if c.target is not None:
        c.swap(c.target)


@power(
    "p10280",
    level=2,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p10280(c: Cast) -> None:
    """The surge value is the *target's*, so `c.surge_value` -- which defaults
    to the caster -- is told whose."""
    if c.target is not None:
        c.temp_hp(c.surge_value(c.target))


@power(
    "p11068",
    level=2,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p11068(c: Cast) -> None:
    who = c.target
    if who is None:
        return

    def tick(ev: TurnStart) -> None:
        if ev.actor == who and not c.bloodied(on=who):
            c.temp_hp(1 + c.con_mod, on=who)

    c.watch(TurnStart, tick, on=who, until=When.ENCOUNTER)


@power(
    "p12940",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p12940(c: Cast) -> None:
    """The printed target is a *bloodied* ally. Nothing in `Target` can narrow
    a target by its own state, so the body carries the restriction."""
    who = c.target
    if who is not None and c.bloodied(on=who):
        c.temp_hp(c.cha_mod, on=who)


@power(
    "p12941",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an ally within 5 squares of you takes damage from an attack",
    on=Trigger(
        DamageRolled, ally_within(5), "an ally within 5 squares takes damage"
    ),
)
def p12941(c: Cast) -> None:
    """The printed target is the triggering ally, which the dispatcher only
    supplies for enemy-side rows -- so it is read off the event. `DamageRolled`
    is a decision and is answered before the damage lands, which is what
    reducing it means."""
    ev = c.trigger
    who = getattr(ev, "target", None)
    if who is None or not c.first:
        return
    ev.amount = max(0, ev.amount - c.wis_mod)
    c.bonus("save", 2, on=who, until=When.EOTNT)


@power(
    "p12942",
    level=2,
    cls="ardent",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.HEALING],
    trigger="an ally within 5 squares of you spends a healing surge",
    on=Trigger(
        SurgeSpent, ally_within(5), "an ally within 5 squares spends a surge"
    ),
)
def p12942(c: Cast) -> None:
    """"As if he or she had spent a healing surge" heals the surge value without
    spending one, so this is `c.heal`, not `c.surge`."""
    spender = getattr(c.trigger, "actor", None)
    pool = [a for a in _friends(c, 5) if a != spender]
    who = c.choose(sorted(pool), "who is mended") if pool else None
    if who is not None:
        c.heal(c.surge_value(who), on=who)


@power(
    "p12943",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p12943(c: Cast) -> None:
    """The damage bonus is gated on the charge; the speed bonus cannot be,
    because `query.speed` reads speed modifiers with no context at all."""
    who = c.target
    if who is None:
        return
    c.bonus("speed", 2, on=who, until=When.EOTNT)
    amount = max(c.wis_mod, c.con_mod)
    if amount:
        c.bonus(
            "damage", amount, on=who, until=When.EOTNT,
            when=lambda ctx: bool(ctx.get("charge")),
        )


@power(
    "p13781",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an ally within 5 squares of you takes damage from an attack",
    on=Trigger(
        DamageRolled, ally_within(5), "an ally within 5 squares takes damage"
    ),
)
def p13781(c: Cast) -> None:
    """The middle sentence -- taking a save-ends effect onto yourself instead of
    the ally -- is dropped: nothing can intercept an effect before it lands."""
    ev = c.trigger
    who = getattr(ev, "target", None)
    if who is None or not c.first:
        return
    ev.amount = ev.amount // 2

    def close(_ctx: dict) -> bool:
        return c.distance(to=who) <= 5

    for holder in (c.me, who):
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 2, on=holder, until=When.EONT, when=close)
