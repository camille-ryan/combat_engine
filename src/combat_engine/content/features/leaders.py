"""The leaders' features: healing a friend, and the divine channels.

A leader's job is that the party is better with it than without, and the
heal is most of that. Both the cleric's and the warlord's are the same
printed row with a different keyword on it, so they are the same function
twice rather than one shared one -- they are separate rows in the book and a
later errata to one should not silently move the other.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    When,
    power,
)


def _worst_hurt(c: Cast) -> list[int]:
    """Who the heal offers, worst off first.

    Order is not cosmetic. `World.decide` takes the first option when
    nobody is playing, so the list *is* the decision for every headless
    fight -- and offering the whole party unsorted had the cleric healing
    whoever happened to be first, at full health, for nothing.

    Anybody untouched comes last, behind the option to keep the power.
    """
    allies = c.within(5, side="ally")
    hurt = sorted((a for a in allies if c.wounded(a)), key=lambda a: -c.missing(a))
    return hurt or []


def _heal_an_ally(c: Cast) -> None:
    """You or an ally spends a surge and gets a little more besides.

    The printed text lets it land on the leader itself, so `c.within(5,
    side="ally")` -- which includes the caster -- is exactly right here
    without filtering.

    Both halves are a printed **may**, and both are asked. Offering only the
    wounded meant that with nobody yet hurt the power fired, found an empty
    list, and was spent on nothing.
    """
    who = c.choose(_worst_hurt(c), "who is healed", optional=True,
                   decline="nobody -- keep the power")
    if who is None:
        return
    if not c.may("spend a healing surge", who=who):
        return
    if c.surge(on=who):
        c.heal(c.roll("1d6"), on=who)


@power(
    "p1590",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
    uses=2,
    once_per_round=True,
)
def p1590(c: Cast) -> None:
    """Twice a fight, but not twice in one round -- the Special line."""
    _heal_an_ally(c)


@power(
    "p1589",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p1589(c: Cast) -> None:
    """A small bonus to the cleric's next attack roll or saving throw.

    Applied to both, and the first one used consumes it, which is what
    "your next attack roll **or** saving throw" means.
    """
    c.bonus("attack", 1, until=When.EONT, on=c.me, once=True)
    c.bonus("save", 1, until=When.EONT, on=c.me)


@power(
    "p146",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p146(c: Cast) -> None:
    """Radiant light that only the undead feel.

    Its printed target line is "each undead creature in the burst", so
    everything else in the blast is simply not a target -- the body checks
    the creature's own type words rather than being handed a filtered list.
    """
    if not c.is_kind("undead"):
        return
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.push(3 + c.cha_mod)
        c.immobilized()
