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
    dropped=("c.object_target()",),
)
def p11273(c: Cast) -> None:
    """Held aloft: the immobilisation is refreshed each time the hold is
    sustained, which is what the printed Sustain Minor line does. The
    free-action and minor-action ways of letting go are dropped -- ending an
    effect early is not in `Cast`.

    **"One ally, helpless enemy, or object", declared as the ally half.**
    A `Target` carries one `side` and `candidates` builds the pool from it
    before any filter runs, so the other two cannot be alternatives today.
    The helpless-enemy half is reachable -- `"any"` plus a conditions filter
    -- and the object half is not, for the reason `c.object_target()` names,
    so that is the symbol this waits on rather than a second one for the
    pool. Marked rather than left admitting it in prose, which is what it
    did: `scripts/targets.py` is what surfaced the declaration. #855.
    """
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
        c.bonus(chosen, c.cha_mod, on=c.me, until=When.EONT, kind="power")


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
