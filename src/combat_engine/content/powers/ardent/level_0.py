"""Ardent, level 0: the class features.

Three of the four answer the same printed Trigger -- being bloodied -- with
`action=ActionType.NONE`, which the dispatcher treats as a reaction that
costs nothing.

Two numbers in these rows grow with tier and cannot: `p10273`'s burst goes
from 5 squares to 10 at 16th level and its `uses` from two to three, and the
header is data read before the body runs. The heroic printing is declared and
the growth is left here in prose.

None of these carries an Augment clause.
"""

from __future__ import annotations

from combat_engine.engine import *

PSIONIC = [Keyword.PSIONIC]
DEFENCES = (AC, FORT, REF, WILL)
BLOODIED = Trigger(Bloodied, about_me, "you are bloodied by an attack")


@power(
    "p10272",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="you are bloodied by an attack",
    on=BLOODIED,
)
def p10272(c: Cast) -> None:
    """The free action is the ally's, so which of the two it spends it on is
    asked of the ally rather than decided here."""
    who = c.target
    if who is None or who == c.me:
        return
    if c.may("move half your speed", who=who):
        c.move(max(1, c.speed_of(who) // 2), who=who)
    else:
        c.shift(1, who=who)


@power(
    "p10273",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.HEALING],
    uses=2,
    once_per_round=True,
)
def p10273(c: Cast) -> None:
    """The extra dice are the only part of the scaling the body can carry;
    the burst and the number of uses are header data. The defence bonus is
    not conditional -- this row is the one mantle's printing of the feature,
    so it always pays out."""
    who = c.target
    if who is None:
        return
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)
        dice = 1 + sum(lv <= c.level for lv in (6, 11, 16, 21, 26))
        c.heal(c.roll(f"{dice}d6"), on=who)
    for d in DEFENCES:
        c.bonus(d, 1, on=who, until=When.EONT)


@power(
    "p11060",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=PSIONIC,
    trigger="you are bloodied by an attack",
    on=BLOODIED,
)
def p11060(c: Cast) -> None:
    """"Grants combat advantage" with nobody named means everybody, which is
    `to="allies"` -- the caster and their side."""
    c.grants_advantage(until=When.SONT, to="allies")


@power(
    "p12931",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PSIONIC,
    trigger="you are bloodied by an attack",
    on=BLOODIED,
)
def p12931(c: Cast) -> None:
    if c.target is None or c.target == c.me:
        return
    c.bonus("damage", 2 + 2 * sum(lv <= c.level for lv in (11, 21)), until=When.SONT)
