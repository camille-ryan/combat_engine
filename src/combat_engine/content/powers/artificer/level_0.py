"""Artificer, level 0: the three infusions the class hands out.

All three print "the target can end the bonus as a free action to ...". That
is a standing option held open indefinitely, not an effect with a duration,
and nothing offers one: the row grants the bonus and the cash-in is dropped.
For the first of them the cash-in is damage immunity, which has no `Cast`
method either.

**The printed budget is two of these per encounter (three at 16th), one per
round -- and it is one budget for all three, which it was not.** Each row
held its own `usage=ENCOUNTER` use and its own `once_per_round`, so three
could be used in a fight and three in a single round. `group` is still not
the answer: `dsl._group_spent` asks whether a sibling was used at all, so a
group is one use shared where the page gives two. The pool lives on
`cf:artificer-f2` -- the feature that crafts the infusions -- and these rows
spend from it.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    MINOR,
    YOU_OR_ONE_ALLY,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    When,
    World,
    power,
)

#: The eight the row lets the target choose from, in printed order.
RESISTABLE = [
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.RADIANT,
    DamageType.THUNDER,
]


def _tier(level: int) -> int:
    """0 heroic, 1 paragon, 2 epic -- the 5/10/15 ladder these rows print."""
    return 0 if level < 11 else (1 if level < 21 else 2)


def _an_infusion_left(world: World, eid: int) -> bool:
    """"You can use two of these per encounter, but only one per round."

    **Asked where the card is offered, not in the body**, because a card
    whose budget is gone must not be chooseable: the action would be spent
    and nothing would happen, which is the drawable-and-inert fault wearing
    a resource. `requires=` is the gate `dsl.usable` consults, and these are
    minor-action cards rather than traits, so the warning about a
    Requirement that is false at arming does not reach them.

    Fails **open**, which is the direction that matters: `c.per_day_left`
    answers the full limit for a creature carrying no `Powers`, so a
    hand-built board is unaffected, and a build-time `usable` call -- which
    `chargen.build_for` makes -- sees an unspent day and keeps the card.
    """
    from combat_engine.content.features.martial_leaders import (
        INFUSION_ROUND,
        INFUSIONS_REF,
        infusions,
    )
    from combat_engine.engine.cast import Cast as _Ask

    ask = _Ask(world=world, me=eid, ref=INFUSIONS_REF)
    if ask.latched(INFUSION_ROUND):
        return False
    return ask.per_day_left(INFUSIONS_REF, infusions(ask)) > 0


def _spend_infusion(c: Cast) -> bool:
    """Take one from the shared pool and close the round's single hold.

    False when the day's infusions are gone, which `_an_infusion_left` has
    already refused at the menu -- kept because a row reached another way
    (`c.use_power`, `f1709b`'s familiar) must pay the same price.
    """
    from combat_engine.content.features.martial_leaders import (
        INFUSION_ROUND,
        INFUSIONS_REF,
        infusions,
    )

    if not c.spend_per_day(INFUSIONS_REF, infusions(c)):
        return False
    c.latch(INFUSION_ROUND)
    return True


@power(
    "p10187",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.ARCANE],
    once_per_round=True,
    requires=_an_infusion_left,
    requires_text="an infusion left, and none used this round",
)
def p10187(c: Cast) -> None:
    """The burst widens at 11th and 21st, which the header cannot say; the
    resistance ladder is read off `c.level` instead.

    The infusion is expended before the damage type is chosen, so a refusal
    costs the player no decision."""
    who = c.target
    if who is None:
        return
    if not _spend_infusion(c):
        return
    dtype = c.choose(RESISTABLE, "damage type to resist")
    if dtype is None:
        return
    c.resist(5 + 5 * _tier(c.level), dtype, until=When.ENCOUNTER, on=who)


@power(
    "p4128",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    once_per_round=True,
    requires=_an_infusion_left,
    requires_text="an infusion left, and none used this round",
)
def p4128(c: Cast) -> None:
    """Hit points equal to a surge value, without the surge being spent --
    so `c.heal` off `c.surge_value`, not `c.surge`."""
    who = c.target
    if who is None:
        return
    if not _spend_infusion(c):
        return
    extra = max(0, ((c.level - 1) // 5) * 2)
    c.heal(c.surge_value(of=who) + c.wis_mod + extra, on=who)


@power(
    "p7635",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.ARCANE],
    once_per_round=True,
    requires=_an_infusion_left,
    requires_text="an infusion left, and none used this round",
)
def p7635(c: Cast) -> None:
    """Only the bonus. Trading it in is the free action nothing holds open."""
    who = c.target
    if who is None:
        return
    if not _spend_infusion(c):
        return
    c.bonus(AC, 1, until=When.ENCOUNTER, on=who, kind="power")
