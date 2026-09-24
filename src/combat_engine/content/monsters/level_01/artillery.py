"""Monster abilities, level 1: the artillery.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=6)` and `Damage("1d6", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Two things recur across the role and are settled once, here.

A printed range of "10/20" is a normal range and a long range, and `Range`
holds one number. Every such row below takes the **normal** range, so the
creature shoots inside the band where it has no penalty rather than out to
a distance at a -2 the engine has no way to apply.

"Makes three attacks" is `c.strike()` called more than once in the body.
The body is per-target, so a row whose attacks may be spread over several
creatures asks `c.first and c.last` whether it is the only target and takes
all the shots if it is -- the idiom the ranger's file already uses.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    Damage,
    DamageType,
    Health,
    Keyword,
    Melee,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.events import Hit, Miss, RelationCleared
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, has_combat_advantage
from combat_engine.engine.triggers import Trigger, both, enemy_within, targets_me

from . import settle

# --------------------------------------------------------------------------
# m264
# --------------------------------------------------------------------------


@power(
    "m264a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d4", 4),
)
def m264a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m264a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m264a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m264a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m264a2(c: Cast) -> None:
    """Three shots at -2, over one to three creatures.

    The header repeats m264a1's line, which is the weapon this fires. Sole
    target and all three shots go into it; more than one and each gets a
    shot, so two targets cost the third shot -- the only reading a per-target
    body can give a row that does not say how the attacks are shared out.
    """
    shots = 3 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike(plus=-2):
            c.hit()


@power(
    "m264a3",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RANGED],
)
def m264a3(c: Cast) -> None:
    """Extra damage on a ranged hit against a creature it has the drop on.

    Unlike the strikers' version this has no once-a-round latch, so it is a
    plain watch rather than `features.strikers.extra_damage`. Combat
    advantage is asked of the board at the moment of the hit: flanking ends
    the instant an ally steps away and a stored flag would not notice.
    """
    me = c.me

    def on_hit(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind != "ranged":
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.damage("1d6", on=ev.target, detail="m264a3")

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "m264a4",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m264a4(c: Cast) -> None:
    """Harder to catch on the way past.

    A gate rather than an effect put on and taken off around every move: the
    attack context carries `opportunity`, so the modifier is asked whether it
    applies at the moment the defence is read.
    """
    c.bonus(
        AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


_HIT_BY_AN_ATTACK = "the m264 is hit by an attack"


@power(
    "m264a5",
    level=1,
    usage=ENCOUNTER,
    action=INTERRUPT,
    trigger=_HIT_BY_AN_ATTACK,
    on=Trigger(Hit, when=targets_me, text=_HIT_BY_AN_ATTACK),
    reach=PERSONAL,
    target=SELF,
)
def m264a5(c: Cast) -> None:
    """The new roll stands whatever it is, so `keep="new"` rather than "worst".

    An interrupt: the reroll has to land before the hit is acted on, because
    what it is for is the hit turning into a miss.
    """
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m2940
# --------------------------------------------------------------------------


@power(
    "m2940a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d4", 3, dtype=DamageType.PSYCHIC),
)
def m2940a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2940a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d4", 3, dtype=DamageType.PSYCHIC),
)
def m2940a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2940a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d4", 1, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2940a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2940a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MELEE, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d4", 3, dtype=DamageType.PSYCHIC),
)
def m2940a3(c: Cast) -> None:
    """Settling on something helpless and finishing it, for a full meal.

    The header repeats m2940a0's line because a coup de grace is made with a
    melee basic attack and `c.coup_de_grace` rolls whatever the header
    declares. It also does the checking -- helpless or unconscious -- so the
    printed restriction on the target is not restated here.
    """
    settle(c)
    if not c.coup_de_grace():
        return
    c.hit()
    health = c.world.get(c.me, Health)
    if health is not None and not alive(c.world, c.target):
        c.heal(health.max_hp, on=c.me)


# --------------------------------------------------------------------------
# m302
# --------------------------------------------------------------------------


@power(
    "m302a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 3),
)
def m302a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m302a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m302a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m302a2",
    level=1,
    usage=ENCOUNTER,
    uses=3,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m302a2(c: Cast) -> None:
    """A pot off the belt: which one is a d6 rolled on the hit.

    Printed "At-Will (3/encounter)", which is three uses and not at-will --
    `usage=ENCOUNTER, uses=3` is what the budget actually is. Fire is a
    keyword on one branch out of three, so it stays off the header and is
    carried by the ongoing damage's type instead.
    """
    if not c.strike():
        return
    c.hit()
    pot = c.roll("1d6")
    if pot <= 2:
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    elif pot <= 4:
        c.ongoing(2, DamageType.FIRE)
    else:
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m302a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m302a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5029
# --------------------------------------------------------------------------

_HIT_BY_ADJACENT = "an enemy adjacent to the m5029 hits it"


@power(
    "m5029a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 3),
)
def m5029a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5029a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 3),
)
def m5029a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5029a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 3),
)
def m5029a2(c: Cast) -> None:
    """m5029a1 twice, spread over one or two creatures."""
    shots = 2 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike():
            c.hit()


@power(
    "m5029a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED, Keyword.POISON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 3, kind=LIMITED),
)
def m5029a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5029a4",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    trigger=_HIT_BY_ADJACENT,
    on=Trigger(Hit, when=both(targets_me, enemy_within(1)), text=_HIT_BY_ADJACENT),
    reach=PERSONAL,
    target=SELF,
)
def m5029a4(c: Cast) -> None:
    """The printed effect line reads Immediate Reaction, so that is the action
    type, whatever the stat block's own header says."""
    c.teleport(2)


@power(
    "m264a6",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m264a6(c: Cast) -> None:
    """Shooting from cover and missing does not give it away.

    Attacking normally breaks hidden -- `resolve.attack` clears it for
    whoever swung -- so this is written as the exemption it is printed as
    rather than as a special case inside the engine. The miss is noted while
    the creature is still unseen, and the break is undone as it happens: the
    `Miss` listener runs before the relation is cleared, and the
    `RelationCleared` listener puts it back.
    """
    me = c.me
    spared: set[int] = set()

    def missed(ev: Miss) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind != "ranged":
            return
        if c.is_hidden(from_=ev.target):
            spared.add(ev.target)

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in spared:
            spared.discard(ev.target)
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label="m264a6")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label="m264a6 keep")
