"""Ardent, level 6: the utilities.

One printed row is absent: the one whose whole effect is "neither grants combat
advantage for being flanked unless both are flanked", which needs a gate
`c.cannot_be_flanked` does not take.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    ally_within,
    both,
    by_me,
    by_opportunity,
    either,
    power,
    spread,
    targets_me,
    targets_my_side,
)
from combat_engine.engine.events import InitiativeRolled
from combat_engine.engine.triggers import about_me

PSIONIC = [Keyword.PSIONIC]


def _friends(c: Cast, radius: int, *, mine: bool = False) -> list[int]:
    return [a for a in c.within(radius, side="ally") if mine or a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10285",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(20),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    trigger="an ally is hit by an opportunity attack",
    on=Trigger(
        Hit,
        both(targets_my_side, by_opportunity),
        "an ally is hit by an opportunity attack",
    ),
)
def p10285(c: Cast) -> None:
    """`ally_within` reads the attacker on a `Hit`, which here is the enemy, so
    the predicate is `targets_my_side` -- the one that reads the victim."""
    who = getattr(c.trigger, "target", None)
    if who is not None and c.first:
        c.teleport(c.cha_mod, who=who)


@power(
    "p10286",
    level=6,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.HEALING],
)
def p10286(c: Cast) -> None:
    if c.target is not None:
        c.heal(c.surge_value(c.target))


@power(
    "p11102",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p11102(c: Cast) -> None:
    c.temp_hp(c.roll("1d12") + c.cha_mod)


@power(
    "p11103",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ZONE],
)
def p11103(c: Cast) -> None:
    """Neither `c.resist` nor a save bonus takes a positional gate, so the two
    benefits go to whoever is standing in the zone when it is laid."""
    area = spread({c.here}, 1)
    c.zone(area, until=When.EONT)
    for who in c.in_squares(area, side="ally"):
        c.resist(3, on=who, until=When.EONT)
        c.bonus("save", 2, on=who, until=When.EONT, kind="untyped")


@power(
    "p12952",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="you take damage from an attack",
    on=Trigger(DamageApplied, targets_me, "you take damage from an attack"),
)
def p12952(c: Cast) -> None:
    if c.target is not None and c.target != c.me:
        c.temp_hp(3 + c.cha_mod)


@power(
    "p12953",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="you or one ally in the burst misses with an opportunity attack",
    on=Trigger(
        Miss,
        both(by_opportunity, either(by_me, ally_within(3))),
        "you or an ally misses with an opportunity attack",
    ),
)
def p12953(c: Cast) -> None:
    ev = c.trigger
    who = getattr(ev, "attacker", None)
    foe = getattr(ev, "target", None)
    if who is not None and foe is not None and c.first:
        c.grant_attack(who, on=foe)


@power(
    "p12954",
    level=6,
    cls="ardent",
    usage=DAILY,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p12954(c: Cast) -> None:
    """"Until it takes its first action" is the start of that creature's next
    turn, which is the nearest clock the engine keeps."""
    c.slide(3)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, until=When.SOTNT)


@power(
    "p12955",
    level=6,
    cls="ardent",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_OTHER_ALLY,
    keywords=PSIONIC,
    trigger="an ally within 5 squares of you moves or shifts",
    on=Trigger(MoveEnd, ally_within(5), "an ally within 5 squares moves"),
)
def p12955(c: Cast) -> None:
    """`MoveEnd`, not `MoveStart`: the printed line is answered once the ally
    has actually gone somewhere."""
    if getattr(c.trigger, "kind_", "") not in ("walk", "shift", "run"):
        return
    mover = getattr(c.trigger, "actor", None)
    pool = [a for a in _friends(c, 5) if a != mover]
    who = _pick(c, pool, "who shifts")
    if who is not None and c.first:
        c.shift(c.wis_mod, who=who)


@power(
    "p13782",
    level=6,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13782(c: Cast) -> None:
    """Dismissing the aura as a minor action is dropped -- an aura has no drop
    cost -- and so is "that can't be reduced in any way": `c.flat` goes through
    the caster's own resistances like any other damage."""
    c.aura(5, until=When.ENCOUNTER)

    def payout(ev: DamageApplied) -> None:
        foe = ev.target
        if foe not in c.within(5, side="enemy"):
            return
        if not c.may("take 5 psychic damage to open the enemy up", who=c.me):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=c.me)
        c.grants_advantage(on=foe, until=When.SAVE_ENDS, to="allies")

    c.watch(DamageApplied, payout, until=When.ENCOUNTER)
