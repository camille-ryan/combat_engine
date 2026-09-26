"""Psion, level 2: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Cast,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    When,
    power,
    targets_me,
)

PSIONIC = [Keyword.PSIONIC]


@power(
    "p11273",
    level=2,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p11273(c: Cast) -> None:
    """Held aloft: the immobilisation is refreshed each time the hold is
    sustained, which is what the printed Sustain Minor line does. Objects and
    helpless enemies are also legal targets in print; the header can only say
    one side, so it says ally. The free-action and minor-action ways of
    letting go are dropped -- ending an effect early is not in `Cast`."""
    victim = c.target
    if victim is None:
        return
    c.slide(3)
    c.immobilized(until=When.EONT)

    def aloft() -> None:
        c.immobilized(on=victim, until=When.EONT)
        c.slide(3, on=victim)

    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR), aloft)


@power(
    "p11274",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p11274(c: Cast) -> None:
    c.teleport(1 + c.wis_mod)


@power(
    "p13313",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p13313(c: Cast) -> None:
    c.note("p13313: +5 to checks with one skill the ally is trained in")


@power(
    "p13316",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13316(c: Cast) -> None:
    """Superior cover is written as the +5 to AC and Reflex it grants: `Cast`
    has no way to hand a creature cover as a geometric property."""
    c.bonus(AC, 5, on=c.me, until=When.EONT, kind="cover")
    c.bonus(REF, 5, on=c.me, until=When.EONT, kind="cover")
    c.slowed(on=c.me, until=When.EONT)


@power(
    "p8231",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p8231(c: Cast) -> None:
    chosen = c.choose([AC, FORT, REF, WILL], f"{c.ref}: which defence")
    if chosen is not None:
        c.bonus(chosen, c.cha_mod, on=c.me, until=When.EONT)


@power(
    "p8232",
    level=2,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p8232(c: Cast) -> None:
    c.note("p8232: +3 to checks with one chosen skill, until the fight ends")
