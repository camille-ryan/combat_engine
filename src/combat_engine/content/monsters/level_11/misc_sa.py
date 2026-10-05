"""Monster abilities, level 11: m6203, which carries no role.

A stat block with no role appears in no role listing, so it belongs in none
of the role files beside this one. Its numbers load from `game.db` like
everything else; this is only its behaviour.

Three things this block had to settle.

**An aura that hands out an initiative bonus pays once.** `c.bonus` cannot
say it -- `Initiative.bonus` is added before the d20 and the order is sorted
off the component rather than off any event -- so `c.initiative` moves each
ally in the order instead, and it is spent when the trait arms rather than
held and refreshed. An initiative check is rolled once a fight, so there is
nothing for a membership diff to do: a creature that wanders out of the ring
later does not un-roll its check.

**"A saving throw to avoid falling prone" is rolled after the condition
lands, not instead of it.** `ConditionApplied` is an announcement of
something that has already happened and carries no `cancel`, which
`c.cancel`'s own docstring says, so the save is rolled on the announcement
and a success takes the condition straight back off. The creature is prone
for no part of any turn either way.

**Its own melee attack is what its leader line grants.** m6203a6 hands an
ally a melee basic attack, and `c.grant_attack`'s `on=` is the victim where
`who` is the swinger -- on a `target=ONE_ALLY` row a bare call would aim the
ally's sword at the ally.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.monster_math import LIMITED

# ==========================================================================
# m6203
# ==========================================================================


@power(
    "m6203a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6203a0(c: Cast) -> None:
    """The ring is laid so the page and the AI can see it; the bonus itself is
    `c.initiative`, which moves a creature in the order. See the module
    docstring for why it is not a held modifier and is not refreshed."""
    c.aura(10, until=When.ENCOUNTER, label=c.ref)
    for ally in c.within(10, side="ally"):
        c.initiative(2, on=ally)


@power(
    "m6203a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6203a1(c: Cast) -> None:
    c.resist_forced(1, until=When.ENCOUNTER)


@power(
    "m6203a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6203a2(c: Cast) -> None:
    """`bare=True` is a saving throw against nothing in particular, which is
    what this one is -- there is no save-ends hold to name."""
    me = c.me

    def shoved(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if c.save(on=me, bare=True):
            c.cure(Condition.PRONE, on=me)

    c.watch(ConditionApplied, shoved, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6203a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 7),
)
def m6203a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6203a4",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 7, kind=LIMITED),
)
def m6203a4(c: Cast) -> None:
    """The Effect line is not gated on the hit. The ally offered the surge is
    the one that has lost the most, since the card lets it choose and nothing
    on the board chooses for it; `c.may` is the "can" in "can spend"."""
    if c.strike():
        c.hit()
    nearby = [a for a in c.within(5, side="ally") if c.wounded(on=a)]
    if not nearby:
        return
    ally = max(nearby, key=lambda a: c.missing(on=a))
    if c.may("spend a healing surge", who=ally):
        c.surge(on=ally)


@power(
    "m6203a5",
    level=11,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING],
)
def m6203a5(c: Cast) -> None:
    """The surge is optional and the saving throw is not -- "can spend a
    healing surge **and** make a saving throw" only hangs the "can" on the
    first half. `c.save` follows `c.target`, which is each ally in turn."""
    if c.target is None:
        return
    if c.may("spend a healing surge"):
        c.surge()
    c.save()


@power(
    "m6203a6",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.WEAPON],
)
def m6203a6(c: Cast) -> None:
    """`who` swings and `on=` is hit, so the victim is named outright: an
    enemy standing beside the ally, which is what a melee basic attack can
    reach without a move it is not granted."""
    ally = c.target
    if ally is None:
        return
    victim = next(iter(c.within(1, of=ally, side="enemy")), None)
    if victim is not None:
        c.grant_attack(ally, on=victim, damage_bonus=2)
