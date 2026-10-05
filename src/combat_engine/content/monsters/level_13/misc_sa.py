"""Monster abilities, level 13: the two blocks that carry no role.

A stat block's numbers load from `game.db`; this is only its behaviour. These
two appear in no role listing -- m4027 prints a role the role sweeps do not
split on, and m4624 prints none at all -- so they are filed here rather than
left out.

Neither is a minion, so the damage lines are ordinary `Damage("1d10", 10)`
expressions and not the flat `kind=MINION` number the minion files carry.

Three things this file had to settle.

**"One ally" is a choice and has to be offered as one.** m4027a0, m4027a1,
m4027a2 and m4027a3 each pick a single beneficiary out of a group, so each
goes through `c.choose` rather than taking the nearest -- and m4027a3's list
has this creature itself at the head of it, because the card offers itself as
one of the answers.

**A bonus "against the target" is gated, not snapshotted.** m4027a1's +3
belongs to the ally's swings at the creature just hit and to no others, so it
is laid with a `when=` that reads the attack's own target. Laid plain it
would be +3 against everybody.

**Several bodies acting as one is a mirror with a guard.** m4624a4 answers
`PowerResolved` and has every other copy use the same row, which is what the
printed sentence does. Each copy runs that same trait, so the echo has to be
able to tell that it *is* an echo -- without a guard the second copy's use
bounces back to the first and each command resolves twice. The guard is per
world and is cleared in a `finally`, so an exception in one copy's body
cannot wedge the rest of the fight.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
    ENCOUNTER,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    Health,
    Keyword,
    Melee,
    PowerResolved,
    When,
    power,
)

#: How far a copy may stand from the one being commanded and still be part of
#: the set. The card puts no distance on it at all -- they are one creature in
#: several bodies -- so this is the width of the board rather than a printed
#: number.
_TOGETHER = 20

#: Which worlds are mid-echo, so a copy can tell a command from the echo of
#: one. Keyed by world, because every copy arms its own trait and a flag held
#: in one closure is invisible to the others.
_ECHOING: set[int] = set()


# ==========================================================================
# m4027
# ==========================================================================


def _an_ally_within(c: Cast, radius: int) -> int | None:
    """"One ally within N squares", offered as the choice the card prints."""
    me = c.me
    mates = [a for a in c.within(radius, side="ally") if a != me]
    return c.choose(mates, "which ally") if mates else None


@power(
    "m4027a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 10),
)
def m4027a0(c: Cast) -> None:
    """A printed "Reach 2" is the melee range. Both halves of the shield are
    the same sentence and the same bonus, so both are `kind="power"` -- the
    word the card prints in front of "bonus" and the reason two uses in a
    row do not stack into +2."""
    if not c.strike():
        return
    c.hit()
    c.bonus(AC, 1, kind="power", until=When.EONT, on=c.me)
    friend = _an_ally_within(c, 1)
    if friend is not None:
        c.bonus(AC, 1, kind="power", until=When.EONT, on=friend)


@power(
    "m4027a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d10", 10),
)
def m4027a1(c: Cast) -> None:
    """The +3 is good against the creature just hit and nobody else, so it is
    gated on the attack's own target rather than laid plain: the attack
    context carries `target`, and a bonus asking it is re-read on every swing
    the ally makes."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    friend = _an_ally_within(c, 5)
    if friend is None:
        return

    def at_the_same_one(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    c.bonus(
        "attack", 3, kind="power", until=When.EONT, on=friend,
        when=at_the_same_one,
    )


@power(
    "m4027a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("3d10", 10),
)
def m4027a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    friend = _an_ally_within(c, 5)
    if friend is not None:
        c.temp_hp(10, on=friend)


@power(
    "m4027a3",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=ActionType.MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4027a3(c: Cast) -> None:
    """"Twice per encounter" is `uses=2` on an encounter row, not two rows.

    This creature is one of the answers, so it heads the list handed to
    `c.choose`. `c.surge` is the printed line: the chosen creature spends a
    surge of its own and heals by it, which is why a monster carries one.
    """
    who = c.choose([c.me, *(a for a in c.within(5, side="ally") if a != c.me)])
    if who is not None:
        c.surge(on=who)


@power(
    "m4027a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.counts_as(feat=)",),
)
def m4027a4(c: Cast) -> None:
    """Counting as having a feat one does not have, which nothing says.

    `c.feat(ref)` asks whether a character took one and there is no way to
    answer yes on a creature that did not -- `c.counts_as(...)` is the family
    the tree already uses for "is considered to be X for the purpose of Y",
    and there is no `feat=` on it.

    The brief is also malformed: it names the feat by **this row's own ref**,
    so even with the verb there would be nothing to point it at. Reported
    rather than guessed at. The mount half needs nothing new -- `c.ride`,
    `c.mount` and `c.rider` already exist.
    """


# ==========================================================================
# m4624
# ==========================================================================


def _copies(c: Cast) -> list[int]:
    """The other bodies this creature is one of, counted by `Ident.ref`.

    Every creature in a fight may share a type word, and these are several
    bodies off one stat block, so the ref is the only thing on the board that
    says so.
    """
    me = c.me
    mine = _ref_of(c, me)
    return [
        other
        for other in c.within(_TOGETHER, side="ally")
        if other != me and _ref_of(c, other) == mine
    ]


@power(
    "m4624a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 2),
)
def m4624a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m4624a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m4624a1(c: Cast) -> None:
    """No damage on the hit line, so the header declares none and the body
    never calls `c.hit()`.

    "Loses line of sight to any creature not adjacent to it" is a cap on
    sight at one square, which is what `c.sight_range` holds -- and
    everything past the cap is unseen, so the target also starts granting
    combat advantage to whoever is further off. That is the printed
    consequence of losing sight, not an extra clause.
    """
    if not c.strike():
        return
    c.penalty("attack", 2, until=When.EONT)
    c.sight_range(1, until=When.EONT)


@power(
    "m4624a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.MINOR,
    reach=CloseBurst(1),
    target=EACH_OTHER,
)
def m4624a2(c: Cast) -> None:
    """"All creatures in the burst" catches friend and foe alike, which is
    `EACH_OTHER`; the side "any" would also catch the creature setting it
    off, and a close burst does not include its own origin."""
    c.condition(Condition.DEAFENED, until=When.EONT)


@power(
    "m4624a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4624a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m4624a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.spend_action(who, cost)",),
)
def m4624a4(c: Cast) -> None:
    """One command, every body: the row the commanded copy used is used again
    by each of the others.

    Answered on `PowerResolved` rather than `PowerUsed`: the second half of
    the sentence is about the consequence, and `PowerUsed` is announced
    before the body runs, so the echo would resolve ahead of the thing it is
    echoing.

    The guard is the whole difficulty. Every copy arms this same trait, so
    the echo's own `PowerResolved` reaches the first copy's watch and bounces
    back; `_ECHOING` is per world so that one copy can see another's echo,
    which a flag in a closure cannot.

    The action economy is the gap: nothing charges one creature for another's
    action, so each copy still has its own turn to spend rather than the one
    complement the card gives the set.
    """
    me = c.me
    board = id(c.world)

    def echo(ev: PowerResolved) -> None:
        if ev.actor != me or board in _ECHOING or not ev.power.startswith("m4624a"):
            return
        twins = _copies(c)
        if not twins:
            return
        _ECHOING.add(board)
        try:
            for twin in twins:
                c.use_power(ev.power, who=twin)
        finally:
            _ECHOING.discard(board)

    c.watch(PowerResolved, echo, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4624a5",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.share_health(who)",),
)
def m4624a5(c: Cast) -> None:
    """Bodies leave play as the pool runs down.

    `Condition.REMOVED` is "removed from play": still standing where it was,
    out of the fight, taking no actions. Each threshold pays once, which is
    what the list of spent ones is for -- a second blow that leaves the hit
    points at the same number must not take a second body.

    The printed 18 and 9 are read against this creature's own hit points,
    because one pool shared between several is the clause the engine is
    missing: nothing ties two creatures' `Health` together. The maximum here
    happens to be the pool's, so the thresholds fall where the card puts them
    for the body being hit -- it is the *other* bodies that do not feel the
    blow. The last of them dropping at 0 needs nothing written: a creature at
    0 hit points is already out.
    """
    me = c.me
    spent: list[int] = []

    def thin(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        health = c.world.get(me, Health)
        if health is None:
            return
        for threshold in (18, 9):
            if health.hp > threshold or threshold in spent:
                continue
            spent.append(threshold)
            twin = next(
                (t for t in _copies(c) if not c.is_(Condition.REMOVED, on=t)), None
            )
            if twin is not None:
                c.condition(Condition.REMOVED, on=twin, until=When.ENCOUNTER)

    c.watch(DamageApplied, thin, until=When.ENCOUNTER, on=me, label=c.ref)
