"""Ardent, level 3: the at-will that stops the target walking.

The spec entry wanted the mirror of `c.rooted`: `c.immobilized` bars the
shift as well, which is a stronger card than this row prints. `c.no_walk` is
that mirror, read by `query.can_walk` in `movement.walk` and in the menu
`actions.legal` builds, so a policy is not offered a move it may not take.
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Keyword,
    Melee,
    MoveEnd,
    When,
    Window,
    power,
)
from combat_engine.engine.events import MoveStart


@power(
    "p12945",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p12945(c: Cast) -> None:
    """"On its next turn" is `When.EOTNT`: the bar has to survive the
    ardent's own turn ending to still be there when the target acts.

    Augment 1 pays your neighbours a defence bonus if the target shifts
    anyway. Augment 2 answers a willing move with a free swing, and it is an
    interrupt, so it watches `MoveStart` -- by `MoveEnd` the target has gone
    and the ally it was meant to be beside is out of reach.
    """
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    c.no_walk(until=When.EOTNT)
    if victim is None or not spent:
        return

    def slipped(ev: MoveEnd) -> None:
        if ev.actor != victim or ev.kind_ != "shift":
            return
        for ally in c.within(1, side="ally"):
            if ally != c.me:
                for d in (AC, FORT, REF, WILL):
                    c.bonus(d, 2, on=ally, until=When.EONT, kind="power")

    def answered(ev: MoveStart) -> None:
        if ev.actor != victim or ev.kind_ == "forced":
            return
        pool = [a for a in c.within(1, side="ally") if a != c.me]
        pool += [a for a in c.within(1, of=victim, side="ally") if a != c.me]
        ally = c.choose(sorted(set(pool)), "who takes the swing") if pool else None
        if ally is not None:
            c.grant_attack(ally, on=victim)

    if spent == 1:
        c.watch(MoveEnd, slipped, until=When.SONT, once=True)
    else:
        c.watch(MoveStart, answered, window=Window.BEFORE, until=When.SONT, once=True)
