"""Monster abilities, level 10, artillery.

132 rows across 27 stat blocks. `artillery.py` holds the earlier sweep of
this level and is not touched here. Two blocks in the brief (m417, m466)
print no abilities at all and so have nothing to decorate.

Conventions, inherited from the earlier sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a card with no printed range at all is melee 1;
* a close burst, blast or area naming no target set takes enemies, except
  where it says "creatures in the burst" outright;
* a printed range band "X/Y" takes the **first** number;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a blow of two damage types rolled once keeps the first in the header and
  is marked `dropped=("Damage(dtypes=)",)`; two separately named amounts of
  different types are a header blow plus a second `c.flat`, needing no
  marker;
* "Requirement: must be in <form>" is asked in the body, never `requires=`
  on a trait -- `turns.arm_traits_of` arms a trait once and a Requirement
  that starts false is refused for the whole fight.

Several cards carry a flavour name where this creature's own ref, or
nothing at all, sits -- read as the spec tool's own extraction noise and
treated as this row's own attack throughout, never as a cross-reference.
One card (`m1587a3`) is entirely self-referential ("As the c9 power
m1587a3") and so carries no information beyond a Conjuration keyword;
nothing identifies what it would summon.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.soldiers_sa import _missed_me_in_melee
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn
from combat_engine.content.monsters.level_05.artillery_sa import _shot_me_from_afar
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Movement,
    Ranged,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Healed,
    Hit,
    PowerResolved,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between, distance_between
from combat_engine.engine.triggers import Trigger, about_me, by_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

ALL_DEFS = (AC, FORT, REF, WILL)


def _bonus_while_bloodied(c: Cast, amount: int) -> None:
    """"+N to hit while bloodied" -- asked per attack, not laid once: the
    bonus has to vanish the instant the creature heals back past half."""
    c.bonus(
        "attack", amount, on=c.me, kind="power", until=When.ENCOUNTER,
        when=lambda _ctx: c.bloodied(on=c.me),
    )


def _adjacent_empty_square(c: Cast, who: int) -> Square | None:
    """A square next to `who` with nobody standing in it, for a shove that
    prints a destination rather than leaving it to the decider."""
    from combat_engine.engine.grid import neighbours
    from combat_engine.engine.query import squares as _squares

    theirs = _squares(c.world, who)
    if not theirs:
        return None
    for sq in neighbours(next(iter(theirs))):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _revive_as_undead(c: Cast, label: str) -> None:
    """"Remains standing, gains the undead keyword, continues to fight
    until the end of its next turn." Stood back up inside the `Dropped`
    window at 1 hit point, same shape as a troll's own rise, with the
    keyword granted through `c.set_origin` rather than invented. Guarded
    by a label so a second `Dropped` -- the one that finishes it for
    real -- finds the guard already spent and does nothing."""
    me = c.me
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    c.effect(label, until=When.ENCOUNTER, on=me)

    def rise(ev: Dropped) -> None:
        if ev.actor == me:
            c.reanimate(on=me, hp=1)
            c.set_origin("undead", on=me, until=When.EONT)

    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{label} rise")


# ==========================================================================
# m1142
# ==========================================================================


@power(
    "m1142a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 4),
)
def m1142a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1142a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.THUNDER),
)
def m1142a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1142a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m1142a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


_M1142_DOWN = "it drops to 0 hit points"


@power(
    "m1142a3",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBlast(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.POLYMORPH],
    trigger=_M1142_DOWN,
    on=Trigger(Dropped, about_me, _M1142_DOWN),
    attack=Attack(vs=WILL, printed=13),
)
def m1142a3(c: Cast) -> None:
    """The usage/action columns the spec gives this row are extraction
    noise -- the real header is the trigger line itself, a free action
    answering its own drop."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1142a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1142a4(c: Cast) -> None:
    """Sensing the distance and direction of a particular guarded
    creature or remains has no combat meaning -- nothing on a board rolls
    for it, and the thing sensed is never a fact a fight could ask about."""


# ==========================================================================
# m115739
# ==========================================================================


@power(
    "m115739a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()",),
)
def m115739a0(c: Cast) -> None:
    """"Two initiative checks, a full turn on each" wants a second,
    independent roll -- `c.extra_turn` only ever takes a count handed to
    it, never rolls one of its own. "Two immediate actions a round but
    only one between turns" is a second, separate budget nothing tracks
    either."""


@power(
    "m115739a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6),
)
def m115739a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115739a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m115739a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115739a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m115739a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.ENCOUNTER)


# ==========================================================================
# m1587
# ==========================================================================


@power(
    "m1587a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 0),
)
def m1587a0(c: Cast) -> None:
    """Two separately named amounts -- untyped in the header, fire as a
    second flat blow -- not one roll of two types, so no marker."""
    if c.strike():
        c.hit()
        c.flat(c.roll("1d8"), dtype=DamageType.FIRE)


@power(
    "m1587a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m1587a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1587a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d6", 6, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m1587a2(c: Cast) -> None:
    """No "creatures in the burst" phrase, so the default is enemies --
    which already leaves allies out, so "can exclude two allies" names
    nothing this row would otherwise catch."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m1587a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    todo=("Cast.summon(ref=)",),
)
def m1587a3(c: Cast) -> None:
    """The printed line names this row's own ref as what it conjures --
    extraction noise with nothing behind it. There is no second ref to
    summon with."""


@power(
    "m1587a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1587a4(c: Cast) -> None:
    """Light radius has no reader -- the grid holds terrain and cover and
    no light level -- and nothing else in the printed line has a combat
    consequence."""


# ==========================================================================
# m1740
# ==========================================================================


@power(
    "m1740a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m1740a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1740a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d6", 5, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m1740a1(c: Cast) -> None:
    """"All creatures adjacent to the target" catches its own side too --
    `side="any"`, the target itself left out since it was already paid."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for who in c.within(1, of=victim, side="any"):
                if who != victim and who != c.me:
                    c.flat(5, dtype=DamageType.LIGHTNING, on=who)
    else:
        c.hit(half=True)


@power(
    "m1740a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1740a2(c: Cast) -> None:
    """No range is printed for the "spear of electricity from its mouth"
    line -- the convention for a card with nothing printed is melee 1,
    flavour notwithstanding."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m1740a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=19),
    damage=Damage("2d8", 4, kind=LIMITED),
    dropped=("c.restrict_targets()",),
)
def m1740a3(c: Cast) -> None:
    """The grab, the pull into its own space and the restrained condition
    all play; `c.shares_space` is what "pulled into the m1740's space"
    asks for, used on the grabber's own square rather than invented.
    "Can only target the m1740" while held has nowhere to attach -- there
    is no way to narrow what a creature may choose to attack, only ways
    to forbid a row or an action outright."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    c.shares_space(on=c.me, until=When.ENCOUNTER)
    c.pull(1, on=victim, to=c.here)
    held = c.condition(Condition.RESTRAINED, until=When.ENCOUNTER, on=victim)
    me = c.me

    def sustained() -> None:
        c.flat(10, on=victim)

    if held is not None:
        c.on_sustain(held, sustained)
    del me


# ==========================================================================
# m2079
# ==========================================================================


@power(
    "m2079a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 2),
)
def m2079a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2079a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.RADIANT),
    dropped=("c.condition(cannot_approach=)",),
)
def m2079a1(c: Cast) -> None:
    """The burn plays, save ends. "Cannot move closer to m2079" has no
    condition to carry it -- the printed conditions are the fixed list in
    `scripts/vocab.py` and none of them narrows movement by direction."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.RADIANT)
        victim = c.target
        if victim is not None:
            other = next(
                (
                    f for f in c.enemies()
                    if f != victim and distance_between(c.world, victim, f) <= 5
                ),
                None,
            )
            if other is not None:
                c.flat(c.roll("1d6") + 5, dtype=DamageType.RADIANT, on=other)


@power(
    "m2079a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m2079a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m2079a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2079a3(c: Cast) -> None:
    """Requirement: bloodied, asked in the body -- offered fresh each
    turn, so there is nothing for a stale `requires=` to kill."""
    if not c.bloodied(c.me):
        return
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m2079a4",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2079a4(c: Cast) -> None:
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.curse(on=foe, until=When.ENCOUNTER)
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.cursed(on=ctx.get("target")),
    )


@power(
    "m2079a5",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2079a5(c: Cast) -> None:
    """Who hurt her lately is asked as the attack rolls, not snapshotted
    now -- the shape `m915a4` settled."""
    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    c.bonus("attack", 1, on=me, kind="power", until=When.ENCOUNTER, once=True, when=paid_back)
    c.bonus("damage", 7, on=me, until=When.ENCOUNTER, once=True, when=paid_back)


@power(
    "m2079a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2079a6(c: Cast) -> None:
    """Net displacement across the turn, not total squares moved -- the
    closer of the two readings available, matching `m4241a0`'s own call."""
    from combat_engine.engine import distance as square_distance

    me = c.me
    start: dict[str, Square | None] = {"square": None}

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            start["square"] = c.here

    def check(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or start["square"] is None:
            return
        if square_distance(start["square"], c.here) >= 3:
            c.conceal(on=me, until=When.EONT)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} dawn")
    c.watch(TurnEnd, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} check")


# ==========================================================================
# m3128
# ==========================================================================


@power(
    "m3128a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 4, dtype=DamageType.COLD),
    dropped=("c.cannot_attack(opportunity=)",),
)
def m3128a0(c: Cast) -> None:
    """The blow lands. "Cannot make opportunity attacks against m3128" is
    narrower than anything `c.cannot_attack` says -- that one bars every
    attack against a named creature, which would also refuse a plain
    ranged shot the card leaves open."""
    if c.strike():
        c.hit()


@power(
    "m3128a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.COLD),
)
def m3128a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.COLD, until=When.EONT)


@power(
    "m3128a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3128a2(c: Cast) -> None:
    victim = next(iter(c.enemies()), None)
    if victim is None:
        return
    c.basic(on=victim)
    c.basic(on=victim)


@power(
    "m3128a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m3128a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m3128a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m3128a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    if not c.first:
        return
    area = list(c.area())
    me = c.me
    dest = next(iter(area), c.here)
    c.teleport(1, to=dest)
    for mate in c.allies():
        if distance_between(c.world, me, mate) <= 5:
            c.teleport(1, who=mate, to=dest)


@power(
    "m3128a5",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.TELEPORTATION],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3128a5(c: Cast) -> None:
    c.restore_use("m3128a4", on=c.me)
    c.use_power("m3128a4", spend=False)


# ==========================================================================
# m3338
# ==========================================================================


@power(
    "m3338a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d10", 8, dtype=DamageType.LIGHTNING),
)
def m3338a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3338a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d4", 8, dtype=DamageType.LIGHTNING),
)
def m3338a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3338a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d4", 8, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3338a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


# ==========================================================================
# m3926
# ==========================================================================


@power(
    "m3926a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m3926a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3926a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 5),
)
def m3926a1(c: Cast) -> None:
    """"Creates shards to hurl when none are present" is unlimited
    ammunition -- which a monster already has by default, so there is
    nothing this clause adds."""
    if c.strike():
        c.hit()


@power(
    "m3926a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m3926a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    if c.first:
        for defence in ALL_DEFS:
            c.bonus(defence, 2, on=c.me, until=When.SONT)


# ==========================================================================
# m4010
# ==========================================================================


@power(
    "m4010a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 3),
)
def m4010a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m4010a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m4010a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m4010a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 2, dtype=DamageType.POISON, kind=LIMITED),
)
def m4010a2(c: Cast) -> None:
    """One save ends the burn and both penalties -- a second `Mod` beside
    the first, the way `m4205a3` lays an attack and a save penalty
    together."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mods = [
        (victim, Mod(what="fort", value=-2, kind="untyped", label=c.ref)),
        (victim, Mod(what="save", value=-2, kind="untyped", label=c.ref)),
    ]
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, mods=mods, ongoing=(5, DamageType.POISON),
    )


@power(
    "m4010a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 4, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m4010a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m4015
# ==========================================================================


@power(
    "m4015a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m4015a0(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), 4)
        if c.result is not None and c.result.critical:
            c.flat(c.roll("1d8") + 12)
        c.shift(2)


@power(
    "m4015a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 6),
)
def m4015a1(c: Cast) -> None:
    """A range band of "20/40" takes the first number."""
    if c.strike():
        c.hit()
    victim = c.target
    if victim is not None and _secondary(c, 13, FORT, victim):
        c.ongoing(5, DamageType.POISON, on=victim)


@power(
    "m4015a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
)
def m4015a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m4015a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.dazed(on=victim, until=When.SAVE_ENDS)


@power(
    "m4015a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4015a3(c: Cast) -> None:
    c.conceal(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (attacker := ctx.get("attacker")) is not None
            and distance_between(c.world, c.me, attacker) > 3
        ),
    )


# ==========================================================================
# m4214
# ==========================================================================


@power(
    "m4214a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 5),
)
def m4214a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4214a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.IMPLEMENT, Keyword.POISON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.POISON),
)
def m4214a1(c: Cast) -> None:
    """"Up to m4214 different targets" is the spec's own ref sitting where
    a number belongs -- read as "up to two", matching `UpTo(2)`."""
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m4214a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.FORCE, kind=LIMITED),
    dropped=("c.damage(ignore_temp_hp=)",),
)
def m4214a2(c: Cast) -> None:
    """The blow and the prone both play. Nothing lets a row's damage skip
    past temporary hit points -- `DamageApplied.absorbed` is a fact read
    afterwards, not a knob set beforehand."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4214a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4214a3(c: Cast) -> None:
    me = c.me

    def even_roll(ev: AttackRolled) -> None:
        if ev.attacker != me or ev.natural % 2 != 0:
            return
        row = get(ev.power)
        if row is not None and Keyword.IMPLEMENT in row.keywords:
            c.slide(1, on=ev.target)

    c.watch(AttackRolled, even_roll, until=When.ENCOUNTER, on=me, label=f"{c.ref} slide")


@power(
    "m4214a4",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.TELEPORTATION],
)
def m4214a4(c: Cast) -> None:
    c.teleport(2)
    c.heal(3, on=c.me)


@power(
    "m4214a5",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4214a5(c: Cast) -> None:
    c.teleport(10)


@power(
    "m4214a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4214a6(c: Cast) -> None:
    me = c.me
    for defence in ALL_DEFS:
        c.bonus(
            defence, 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# ==========================================================================
# m4381
# ==========================================================================


@power(
    "m4381a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m4381a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4381a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.FORCE),
)
def m4381a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m4381a2",
    level=10,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target(side="ally", count=2, label="ally"),
)
def m4381a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.shift(2, who=mate)
    foe = next((f for f in c.enemies() if c.adjacent_to(mate, f)), None)
    if foe is not None:
        c.basic(who=mate, on=foe)


@power(
    "m4381a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.FORCE, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m4381a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4381a4",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.ignores_difficult(hazardous=)",),
)
def m4381a4(c: Cast) -> None:
    """The shift through enemies' spaces plays, ignoring difficult terrain
    for its duration. Waiving hazardous terrain and the squeezing penalty
    specifically has nowhere further to attach -- neither is its own
    knob apart from the terrain word itself."""
    c.shift(6, share=True)
    c.ignores_difficult(on=c.me, until=When.EOT)


# ==========================================================================
# m4638
# ==========================================================================


@power(
    "m4638a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m4638a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4638a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 4),
)
def m4638a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4638a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
)
def m4638a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE, until=When.SAVE_ENDS)


@power(
    "m4638a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4638a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m4638a1", on=victim)
    c.use_power("m4638a1", on=victim)


@power(
    "m4638a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4638a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


_M4638_ROLLED = "it makes an attack roll"


@power(
    "m4638a5",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4638_ROLLED,
    on=Trigger(AttackRolled, by_me, _M4638_ROLLED),
)
def m4638a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m4638a6",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4638a6(c: Cast) -> None:
    c.shift(3)
    c.phasing(until=When.EOT)


# ==========================================================================
# m5193
# ==========================================================================


@power(
    "m5193a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m5193a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5193a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 11, dtype=DamageType.FIRE),
    dropped=("Damage(dtypes=)",),
)
def m5193a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5193a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 9, kind=LIMITED),
    dropped=("Power.reach_alt",),
)
def m5193a2(c: Cast) -> None:
    """The printed "or area burst 3 within 10" alternative has nowhere to
    sit: `reach_alt` is a numeric alternative, not a second reach kind, so
    this is written as the close blast and the area form is left off."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m5193a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m5193a3(c: Cast) -> None:
    """Requirement: bloodied, asked in the body."""
    if not c.bloodied(c.me):
        return
    if c.strike():
        c.hit()
        c.ongoing(5)
    if c.first:
        for mate in c.allies():
            if distance_between(c.world, c.me, mate) <= 2:
                c.temp_hp(5, on=mate)


_M5193_DOWN = "it drops to 0 hit points and is killed"


@power(
    "m5193a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5193_DOWN,
    on=Trigger(Dropped, about_me, _M5193_DOWN),
)
def m5193a4(c: Cast) -> None:
    _revive_as_undead(c, "m5193a4")


_M5193_LANDED = "it bloodies an enemy or reduces one to 0 hit points or fewer"


@power(
    "m5193a5",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5193_LANDED,
    on=(
        Trigger(Bloodied, by_me, _M5193_LANDED),
        Trigger(Dropped, by_me, _M5193_LANDED),
    ),
)
def m5193a5(c: Cast) -> None:
    c.temp_hp(c.roll("1d6") + 4, on=c.me)


# ==========================================================================
# m5330
# ==========================================================================


@power(
    "m5330a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m5330a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5330a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 6),
)
def m5330a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m5330a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 5),
)
def m5330a2(c: Cast) -> None:
    """Requirement: a creature grabbed, asked in the body. The shove picks
    whoever else is nearest the held creature to land it beside."""
    held = c.grabbing()
    if not held:
        return
    victim = next(iter(held))
    other = min(
        (f for f in c.enemies() if f != victim),
        key=lambda f: distance_between(c.world, victim, f),
        default=None,
    )
    if other is None:
        return
    dest = _adjacent_empty_square(c, other)
    c.push(10, on=victim, to=dest)
    c.prone(on=victim)
    c.flat(c.roll("2d10") + 5, on=victim)
    if c.strike(on=other):
        c.hit(on=other)
        c.push(3, on=other)
        c.prone(on=other)


_M5330_MISSED = "it is missed by a melee attack"


@power(
    "m5330a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5330_MISSED,
    on=Trigger(Hit, _missed_me_in_melee, _M5330_MISSED),
)
def m5330a3(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5703
# ==========================================================================


@power(
    "m5703a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5703a0(c: Cast) -> None:
    """The card names three kinds of rough ground; one representative
    word stands for the set, the same call `m6230a1` made."""
    c.ignores_difficult("rubble", on=c.me, until=When.ENCOUNTER)


@power(
    "m5703a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 8),
)
def m5703a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5703a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m5703a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            other = next(
                (
                    f for f in c.enemies()
                    if f != victim and distance_between(c.world, victim, f) <= 3
                ),
                None,
            )
            if other is not None:
                c.flat(5, on=other)


@power(
    "m5703a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5703a3(c: Cast) -> None:
    victim = c.target
    c.use_power("m5703a2", on=victim)
    c.use_power("m5703a2", on=victim)


_M5703_SHOT = "an enemy hits it with a ranged or an area attack"


@power(
    "m5703a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5703_SHOT,
    on=Trigger(Hit, _shot_me_from_afar(0), _M5703_SHOT),
)
def m5703a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m5703a2", on=foe)


# ==========================================================================
# m5724
# ==========================================================================


@power(
    "m5724a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5724a0(c: Cast) -> None:
    me = c.me
    state = {"shielded": False}

    def hurt(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        types = ev.types()
        if DamageType.RADIANT in types or DamageType.FORCE in types:
            state["shielded"] = True
            return
        if not state["shielded"]:
            c.halve(ev)

    def lift(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            state["shielded"] = False

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=f"{c.ref} half")
    c.watch(TurnStart, lift, until=When.ENCOUNTER, on=me, label=f"{c.ref} lift")


@power(
    "m5724a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m5724a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5724a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m5724a2(c: Cast) -> None:
    me = c.me
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.penalty(
                "attack", 5, on=victim, until=When.EONT,
                when=lambda ctx: ctx.get("target") == me,
            )


@power(
    "m5724a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("4d8", 4, kind=LIMITED),
)
def m5724a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SONT)


@power(
    "m5724a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    attack=Attack(vs=FORT, printed=14),
)
def m5724a4(c: Cast) -> None:
    if c.strike():
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.weakened(until=When.EONT)


@power(
    "m5724a5",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5724a5(c: Cast) -> None:
    c.phasing(until=When.EONT)


# ==========================================================================
# m5743
# ==========================================================================


@power(
    "m5743a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 8),
)
def m5743a0(c: Cast) -> None:
    _bonus_while_bloodied(c, 2)
    if c.strike():
        c.hit()


@power(
    "m5743a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 7),
)
def m5743a1(c: Cast) -> None:
    _bonus_while_bloodied(c, 2)
    if c.strike():
        c.hit()


@power(
    "m5743a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 8, kind=LIMITED),
)
def m5743a2(c: Cast) -> None:
    _bonus_while_bloodied(c, 2)
    if c.strike():
        c.hit()


@power(
    "m5743a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m5743a3(c: Cast) -> None:
    _bonus_while_bloodied(c, 2)
    if c.strike():
        c.hit()
        c.push(1)


# ==========================================================================
# m5786
# ==========================================================================

_M5786_LABEL = "m5786a5 beast"


def _in_beast_form(c: Cast) -> bool:
    return any(e.label == _M5786_LABEL for e in c.world.effects.of(c.me))


@power(
    "m5786a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5786a0(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.ENCOUNTER)


@power(
    "m5786a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5786a1(c: Cast) -> None:
    """Requirement: humanoid form, asked in the body."""
    if _in_beast_form(c):
        return
    if c.strike():
        c.hit()


@power(
    "m5786a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 9, kind=LIMITED),
)
def m5786a2(c: Cast) -> None:
    """Requirement: humanoid form, asked in the body."""
    if _in_beast_form(c):
        return
    res = c.strike()
    if res:
        c.hit()
        if res.critical:
            c.prone()


@power(
    "m5786a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d10", 12, kind=LIMITED),
)
def m5786a3(c: Cast) -> None:
    """Requirement: beast form, asked in the body."""
    if not _in_beast_form(c):
        return
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(10)
    if c.first:
        for defence in ALL_DEFS:
            c.bonus(defence, 4, kind="power", on=c.me, until=When.EOT)
        c.shift(c.speed_of())


@power(
    "m5786a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d8", 10, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5786a4(c: Cast) -> None:
    """Requirement: humanoid form, asked in the body."""
    if _in_beast_form(c):
        return
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.THUNDER)
    if not c.first:
        return
    me = c.me
    zone = c.zone(c.area(), until=When.EONT, label=c.ref)

    def toll(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            c.flat(10, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.EONT, on=me, label=f"{c.ref} zone")


@power(
    "m5786a5",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m5786a5(c: Cast) -> None:
    me = c.me
    existing = next((e for e in c.world.effects.of(me) if e.label == _M5786_LABEL), None)
    if existing is not None:
        c.world.effects.end(existing, "returns to humanoid form")
    else:
        c.form(until=When.ENCOUNTER, label=_M5786_LABEL)


@power(
    "m5786a6",
    level=10,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m5786a6(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    me = c.me
    mate = min(
        c.allies(),
        key=lambda a: distance_between(c.world, me, a),
        default=None,
    )
    if mate is not None:
        c.mark(on=victim, by=mate, until=When.SAVE_ENDS)


# ==========================================================================
# m5789
# ==========================================================================


@power(
    "m5789a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.immune(vs=)",),
)
def m5789a0(c: Cast) -> None:
    """"Takes damage as normal but ignores all other effects" of a Will
    attack has no general hook -- a rider is applied by the attacking
    row's own body right after `c.hit()`, not through anything this
    creature could intercept or cancel after the fact."""


@power(
    "m5789a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d4", 4),
)
def m5789a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5789a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 9),
)
def m5789a2(c: Cast) -> None:
    """"If adjacent to [this creature]" reads off itself, not a name --
    the only flavour-free reading the extraction left."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if victim is not None and c.adjacent(victim):
        c.flat(c.roll("4d8") + 9)
    else:
        c.hit()
    c.push(2)


_M5789_ADJACENT_END = "an enemy ends its turn adjacent to it"


def _enemy_ends_adjacent(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or ev.ghost:
        return False
    from combat_engine.engine.query import team

    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1


@power(
    "m5789a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M5789_ADJACENT_END,
    on=Trigger(TurnEnd, _enemy_ends_adjacent, _M5789_ADJACENT_END),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 9),
)
def m5789a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.shift(3)
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m5810
# ==========================================================================


@power(
    "m5810a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d4", 5),
)
def m5810a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5810a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 2, dtype=DamageType.FIRE),
    dropped=("Damage(dtypes=)",),
)
def m5810a1(c: Cast) -> None:
    c.bonus(
        "crit_range", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == c.ref,
    )
    res = c.strike()
    if res:
        c.hit()
        if res.critical:
            c.weakened(until=When.SAVE_ENDS)


@power(
    "m5810a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d8", 9, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m5810a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5810a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("resolve.deal_damage(area=)",),
)
def m5810a3(c: Cast) -> None:
    """The ranged half plays. The damage context carries `ranged` and
    nothing that marks a blow as an **area** attack on its own, so a
    close or area blow this creature takes cannot be told apart from a
    melee one here."""
    c.resist(1000, None, until=When.EONT, when=lambda ctx: bool(ctx.get("ranged")))


# ==========================================================================
# m5911
# ==========================================================================


@power(
    "m5911a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m5911a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5911a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 8),
)
def m5911a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)


@power(
    "m5911a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5911a2(c: Cast) -> None:
    victim = c.target
    c.use_power("m5911a1", on=victim)
    c.use_power("m5911a1", on=victim)


@power(
    "m5911a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m5911a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON, until=When.SAVE_ENDS)


@power(
    "m5911a4",
    level=10,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
)
def m5911a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    me = c.me

    def retaliate(ev: Any) -> None:
        if getattr(ev, "attacker", None) == victim and getattr(ev, "target", None) == me:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(AttackDeclared, retaliate, until=When.EONT, on=me, label=f"{c.ref} {victim}")


# ==========================================================================
# m5930
# ==========================================================================


@power(
    "m5930a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.ACID),
)
def m5930a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID, until=When.SAVE_ENDS)


@power(
    "m5930a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d4", 3, dtype=DamageType.ACID),
)
def m5930a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m5930a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=NO_TARGET,
)
def m5930a2(c: Cast) -> None:
    for mate in c.allies():
        if distance_between(c.world, c.me, mate) <= 3:
            c.temp_hp(10, on=mate)
            for eff in list(c.world.effects.of(mate)):
                if eff.when is When.SAVE_ENDS:
                    c.world.effects.save(eff)


@power(
    "m5930a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5930a3(c: Cast) -> None:
    zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def fall(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        move = c.world.get(ev.actor, Movement)
        if move is None or "climb" not in move.modes:
            c.prone(on=ev.actor)

    c.watch(TurnEnd, fall, until=When.ENCOUNTER, on=me, label=f"{c.ref} zone")


# ==========================================================================
# m6178
# ==========================================================================


@power(
    "m6178a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 7, kind=MINION),
)
def m6178a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6178a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 9, kind=MINION),
)
def m6178a1(c: Cast) -> None:
    if not c.strike():
        return
    me, victim = c.me, c.target
    cover = cover_between(c.world, victim, me) if victim is not None else Cover.NONE
    c.flat(11 if cover is not Cover.NONE else 9)


# ==========================================================================
# m6368
# ==========================================================================


@power(
    "m6368a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m6368a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "m6368a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m6368a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
        c.no_healing(on=c.target, until=When.SAVE_ENDS)


_M6368_HIT = "it hits with m6368a0"


@power(
    "m6368a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6368_HIT,
    on=Trigger(Hit, by_me, _M6368_HIT),
)
def m6368a2(c: Cast) -> None:
    row = get(getattr(c.trigger, "power", "") or "")
    if row is None or row.ref != "m6368a0":
        return
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    for eff in c.world.effects.of(victim):
        if eff.ongoing and eff.ongoing[1] is DamageType.NECROTIC:
            eff.ongoing = (20, DamageType.NECROTIC)
    from combat_engine.engine import spread

    area = spread({c.here}, 1)
    c.zone(area, difficult=True, until=When.ENCOUNTER, label=f"{c.ref} sand")


_M6368_HEALED_NEARBY = "an enemy within 10 squares regains hit points"


def _enemy_healed_nearby(world: Any, me: int, ev: Any) -> bool:
    from combat_engine.engine.query import team

    target = getattr(ev, "target", None)
    if target is None or team(world, target) is team(world, me):
        return False
    return distance_between(world, me, target) <= 10


@power(
    "m6368a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    trigger=_M6368_HEALED_NEARBY,
    on=Trigger(Healed, _enemy_healed_nearby, _M6368_HEALED_NEARBY),
)
def m6368a3(c: Cast) -> None:
    c.reduce(10, c.trigger)
    c.temp_hp(10, on=c.me)


# ==========================================================================
# m6372
# ==========================================================================


@power(
    "m6372a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 4),
)
def m6372a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6372a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 9, dtype=DamageType.LIGHTNING),
)
def m6372a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6372a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 8, dtype=DamageType.LIGHTNING, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m6372a2(c: Cast) -> None:
    """The hit roll is one blow of two types, which is all one `Damage`
    header can say. The ongoing burn is the *same* pair and does not need
    a marker: `Effects.apply` takes `ongoing_types` for exactly this, so
    the two-type burn is sayable even though the header's single roll is
    not."""
    label = f"{c.ref} burn"
    if c.strike():
        c.hit()
        c.world.effects.apply(
            c.target, c.me, When.SAVE_ENDS, label=label,
            ongoing=(5, DamageType.LIGHTNING),
            ongoing_types=(DamageType.LIGHTNING, DamageType.NECROTIC),
        )
    if not c.first:
        return
    me = c.me

    def still_burning(_ctx: dict[str, Any]) -> bool:
        from combat_engine.engine.query import creatures

        return any(
            any(e.label == label for e in c.world.effects.of(k)) for k in creatures(c.world)
        )

    c.bonus("attack", 2, kind="power", on=me, until=When.ENCOUNTER, when=still_burning)
    # The card types both: "+2 power bonus to attack rolls and a +5 power
    # bonus to damage rolls".
    c.bonus("damage", 5, on=me, kind="power", until=When.ENCOUNTER, when=still_burning)


_M6372_HIT = "it is hit by an attack"


@power(
    "m6372a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6372_HIT,
    on=Trigger(Hit, targets_me, _M6372_HIT),
)
def m6372a3(c: Cast) -> None:
    """No fly speed is on this stat block, so "flies" is read as the
    movement verb the extraction kept and written as a shift."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.push(2, on=foe)
    c.shift(6)


# ==========================================================================
# m958
# ==========================================================================


@power(
    "m958a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d4", 9, dtype=DamageType.FORCE),
)
def m958a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m958a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d6", 9, kind=LIMITED),
)
def m958a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m958a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 9, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m958a2(c: Cast) -> None:
    """The primary target is the row's own header; the two secondary
    targets roll separately near it, the `m1118a2` shape."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    near = [f for f in c.enemies() if f != victim and distance_between(c.world, victim, f) <= 10]
    near.sort(key=lambda f: distance_between(c.world, victim, f))
    for extra in near[:2]:
        if _secondary(c, 14, REF, extra):
            c.damage("1d6", 9, dtype=DamageType.LIGHTNING, on=extra)


@power(
    "m958a3",
    level=10,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 9, dtype=DamageType.FORCE, kind=LIMITED),
    dropped=("c.move_zone(conjuration=)",),
)
def m958a3(c: Cast) -> None:
    """The attack lands and sustains, re-rolling against the same target.
    "Move action: move the sword to a new target" has no mover -- a
    sustained attack has no conjured anchor on the board for `c.move_zone`
    to relocate."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    eff = c.effect(f"{c.ref} sword", until=When.SUSTAIN, sustain=MINOR, on=c.me)

    def again() -> None:
        c.use_power("m958a3", on=victim, again=True)

    c.on_sustain(eff, again)


@power(
    "m958a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m958a4(c: Cast) -> None:
    c.teleport(10)


@power(
    "m958a5",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m958a5(c: Cast) -> None:
    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    c.bonus("attack", 1, on=me, kind="power", until=When.ENCOUNTER, once=True, when=paid_back)

    def push_on_hit(ev: Hit) -> None:
        if ev.attacker != me:
            return
        c.push(1, on=ev.target)

    c.watch(Hit, push_on_hit, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} push")


@power(
    "m958a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m958a6(c: Cast) -> None:
    c.bonus(
        "attack", 1, kind="racial", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m958a7",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m958a7(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.heal(39, on=c.me)
    for defence in ALL_DEFS:
        c.bonus(defence, 2, on=c.me, until=When.SONT)


@power(
    "m958a8",
    level=10,
    usage=DAILY,
    action=FREE,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
)
def m958a8(c: Cast) -> None:
    me = c.me

    def after(ev: PowerResolved) -> None:
        if ev.actor != me:
            return
        row = get(ev.power)
        if row is None or not ({Keyword.LIGHTNING, Keyword.THUNDER} & set(row.keywords)):
            return
        for foe in c.enemies():
            if distance_between(c.world, me, foe) <= 3:
                c.flat(c.roll("1d8"), dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=foe)

    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} staff")
