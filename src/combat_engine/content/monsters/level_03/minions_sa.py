"""Monster abilities, level 3, minions: the second sweep.

Eleven of the fifteen stat blocks in this role print rows; the other four
print none at all and have nothing to decorate.

The conventions are the ones the level 1 and 2 minion sweeps settled:

* a minion's damage is a flat number in the header with `kind=MINION`, and
  its one hit point is in the database;
* "adjacent to three or more of these" counts by `Ident.ref` and not by
  `c.is_kind` -- every creature in the fight may share a type word, and the
  printed sentence is about this stat block;
* the pack sentence pays out **once**, so the lowest-numbered of whoever is
  standing there is the one that lays it. Every member arms the watch.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _prone_save
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    When,
    World,
    power,
)
from combat_engine.engine.events import DamageRolled, Dropped, Hit, Miss, TurnStart
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import adjacent, enemies, flanked_by
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me

# -- what these blocks share -----------------------------------------------


def _kin_beside(c: Cast, foe: int, least: int) -> bool:
    """Are `least` or more creatures off this stat block standing next to `foe`?

    Counted by ref, and the caster counts itself in: the printed line reads
    "three or more", and the one swinging is one of them.
    """
    kin = _ref_of(c, c.me)
    return (
        sum(
            1
            for a in (c.me, *c.allies())
            if _ref_of(c, a) == kin and c.adjacent_to(a, foe)
        )
        >= least
    )


def _mobbed(c: Cast, least: int, apply: Callable[[int], None]) -> None:
    """One payout when an enemy starts its turn surrounded by this many kin.

    Every member of the swarm arms the watch, so the effect is laid by the
    lowest-numbered of whoever is actually adjacent -- the card prints one
    consequence, not one per creature standing there.
    """
    me = c.me
    kin = _ref_of(c, me)

    def at_the_top(ev: TurnStart) -> None:
        foe = ev.actor
        if ev.ghost or foe == me or foe not in c.enemies():
            return
        pack = [
            a for a in (me, *c.allies())
            if _ref_of(c, a) == kin and c.adjacent_to(a, foe)
        ]
        if len(pack) >= least and min(pack) == me:
            apply(foe)

    c.watch(TurnStart, at_the_top, until=When.ENCOUNTER, on=me, label=f"{c.ref} pack")


def _hurt_by_a_neighbour(world: World, me: int, ev: Any) -> bool:
    """"Takes damage from an attack by an enemy adjacent to it."

    `DamageRolled` carries `source` and no power, so the "by an attack" half
    is read off the source being a creature on the other side rather than off
    a reach: ongoing damage and a hazard both arrive with no enemy source.
    """
    who = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and isinstance(who, int)
        and who in enemies(world, me)
        and adjacent(world, me, who)
    )


# --------------------------------------------------------------------------
# m1923
# --------------------------------------------------------------------------


@power(
    "m1923a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=3),
    damage=Damage(bonus=6, kind=MINION),
)
def m1923a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1923a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1923a1(c: Cast) -> None:
    """Held until the *start* of the victim's next turn, which is the printed
    duration and not `EOTNT`: it is pinned for the turn it starts surrounded
    and free again the moment the next one begins."""
    _mobbed(c, 3, lambda foe: c.immobilized(on=foe, until=When.SOTNT))


@power(
    "m1923a2",
    level=3,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1923a2(c: Cast) -> None:
    c.shift(8)


# --------------------------------------------------------------------------
# m1928
# --------------------------------------------------------------------------


@power(
    "m1928a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=3, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1928a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(2, DamageType.NECROTIC)


@power(
    "m1928a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m1928a1(c: Cast) -> None:
    """"Instead deals 6 and ongoing 5" written as the difference, twice over.

    The three extra points are added to the blow the other row already dealt,
    and the bigger burn is simply applied: `c.ongoing` keeps the highest of a
    type and discards the weaker, so laying 5 over the row's own 2 is the
    printed "instead" without anything having to be taken back.
    """
    me, ref = c.me, c.ref

    def harder(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m1928a0":
            return
        if not _kin_beside(c, ev.target, 3):
            return
        c.flat(3, dtype=DamageType.NECROTIC, on=ev.target)
        c.ongoing(5, DamageType.NECROTIC, on=ev.target)

    c.watch(Hit, harder, until=When.ENCOUNTER, on=me, label=ref)


# --------------------------------------------------------------------------
# m3210
# --------------------------------------------------------------------------


@power(
    "m3210a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m3210a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3210a1",
    level=3,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m3210a1(c: Cast) -> None:
    """Declared on `Hit` from an interrupt, which is the only window that can
    refuse one -- "avoid damage from the attack" is the hit not landing at all.
    `bare=True` because the throw is against nothing in particular."""
    if c.save(on=c.me, bare=True, against=f"{c.ref} dodge"):
        c.cancel()
        c.shift(2)


@power(
    "m3210a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3210a2(c: Cast) -> None:
    """Both halves of a slippery trait: one square off every shove, and a save
    against being floored."""
    c.resist_forced(1, on=c.me)
    _prone_save(c)


# --------------------------------------------------------------------------
# m3523
# --------------------------------------------------------------------------


@power(
    "m3523a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage(bonus=3, dtype=DamageType.NECROTIC, kind=MINION),
)
def m3523a0(c: Cast) -> None:
    """The crowd is counted **before** the swing, because the swing may be what
    kills one of the pack holding the count up."""
    foe = c.target
    mobbed = foe is not None and _kin_beside(c, foe, 3)
    if c.strike():
        if mobbed:
            c.flat(6, dtype=DamageType.NECROTIC)
            c.ongoing(5, DamageType.NECROTIC)
        else:
            c.hit()
            c.ongoing(2, DamageType.NECROTIC)


# --------------------------------------------------------------------------
# m3769
# --------------------------------------------------------------------------


@power(
    "m3769a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m3769a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3769a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m3769a1(c: Cast) -> None:
    """The block's second weapon line, printed with the same numbers and no
    range of its own, so it is written as the first one is."""
    if c.strike():
        c.hit()


@power(
    "m3769a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aid_another()",),
)
def m3769a2(c: Cast) -> None:
    """"+3 instead of +2 while flanking" is written as the *difference*: the
    engine already pays the +2, so a second +2 of the same kind would not
    stack and the row would be worth nothing.

    The aid-another half is dropped -- nothing grants a bonus to one.
    """
    me = c.me

    def while_flanking(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return isinstance(foe, int) and flanked_by(c.world, foe, me)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=while_flanking)


@power(
    "m3769a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3769a3(c: Cast) -> None:
    """Mimicry, opposed by an Insight check. Nothing on a board listens, so
    the whole printed trait is inert rather than missing."""


# --------------------------------------------------------------------------
# m5069
# --------------------------------------------------------------------------


@power(
    "m5069a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=3, kind=MINION),
)
def m5069a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5069a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5069a1(c: Cast) -> None:
    """Four defences, one gate. The attacker is in the defence context -- which
    is where `+2 against a creature it is grabbing` has to be asked, because
    whom it holds changes between attacks."""
    me = c.me

    def by_my_captive(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return isinstance(who, int) and who in c.world.relations.targets(
            Relation.GRABBED_BY, me
        )

    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=me, until=When.ENCOUNTER, when=by_my_captive)


# --------------------------------------------------------------------------
# m5217
# --------------------------------------------------------------------------


@power(
    "m5217a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m5217a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SONT)


@power(
    "m5217a1",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes damage from an attack by an adjacent enemy",
    on=Trigger(
        DamageRolled,
        _hurt_by_a_neighbour,
        "it takes damage from an attack by an adjacent enemy",
    ),
)
def m5217a1(c: Cast) -> None:
    """Resist 5 against this one blow, and the attacker is burned for 5 only if
    nothing at all got through -- which is why the reduction is measured rather
    than assumed: `c.reduce` returns what it actually took off, and the blow may
    have been smaller than 5 or larger."""
    ev = c.trigger
    if ev is None:
        return
    c.reduce(5, ev)
    if getattr(ev, "amount", 0) <= 0:
        who = getattr(ev, "source", None)
        if isinstance(who, int):
            c.flat(5, on=who)


# --------------------------------------------------------------------------
# m5477
# --------------------------------------------------------------------------


@power(
    "m5477a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_cover(concealment_only=True)",),
)
def m5477a0(c: Cast) -> None:
    """Its attacks see past *concealment* and only concealment, and only
    against a bloodied creature. `c.ignore_cover` waives cover and concealment
    together -- `resolve.situational` takes the larger of the two and there is
    nothing to carve out -- so the whole trait waits on the narrower verb."""


@power(
    "m5477a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, dtype=DamageType.POISON, kind=MINION),
)
def m5477a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5477a2",
    level=3,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=6),
    damage=Damage(bonus=3, dtype=DamageType.ACID, kind=MINION),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5477a2(c: Cast) -> None:
    """An interrupt on its own death, so the burst goes off before it is gone.
    `ONE_CREATURE` and not `NO_TARGET`: the card chooses a victim rather than
    answering whoever struck the blow."""
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5750
# --------------------------------------------------------------------------


@power(
    "m5750a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m5750a0(c: Cast) -> None:
    """"Until the end of its **current** turn" is `EOT`, not `EONT` -- the daze
    is gone before the victim has had a turn to lose, and all it costs is the
    chance to answer anything in between."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EOT)


@power(
    "m5750a1",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="an enemy's melee attack misses it",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy's melee attack misses it"),
)
def m5750a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(3, dtype=DamageType.FIRE, on=foe)
    c.shift(1)


# --------------------------------------------------------------------------
# m5852
# --------------------------------------------------------------------------


@power(
    "m5852a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m5852a0(c: Cast) -> None:
    """A high-crit line on a minion: the widened range is laid for the swing
    and the critical's 7 is a flat number rather than the header's 4 maximised,
    because the card prints a different total and not a bigger die.

    `stacks=False` so using the row twice in a turn does not widen it twice.
    """
    c.bonus("crit_range", 2, on=c.me, until=When.EOT, stacks=False)
    if c.strike():
        if c.crit:
            c.flat(7)
        else:
            c.hit()


# --------------------------------------------------------------------------
# m5883
# --------------------------------------------------------------------------


@power(
    "m5883a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m5883a0(c: Cast) -> None:
    """The step is an Effect line, so it is taken whether the swing landed or
    not -- outside the `if`, deliberately."""
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m5883a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage(bonus=5, dtype=DamageType.RADIANT, kind=MINION),
)
def m5883a1(c: Cast) -> None:
    if c.strike():
        c.hit()
