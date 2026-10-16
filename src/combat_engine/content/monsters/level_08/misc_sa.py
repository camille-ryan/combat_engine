"""Monster abilities, level 8: the blocks that print no role.

Five stat blocks, fifteen rows -- the handful of level-8 role-less blocks
an earlier round's briefs, each cut by one of the seven named roles,
stepped over because none of them claimed these. As at the lower levels, a
role-less block here reads like a companion's or a vermin's card rather
than an encounter monster, which is a fact about the card and not an
error.

Conventions, inherited from the sweeps below this level:

* numbers load from `game.db`; the attack line is `Attack(vs=AC,
  printed=N)` exactly as the card prints it, and the damage line goes in
  the header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims;
* a card printing no range at all is melee 1;
* a stance's payout rides a `Hit` watch torn down with the stance itself
  (`until=When.STANCE`), the shape every stance in the tree already uses.

Two helpers are written here because this file is the first to need them:
sizing a Medium-or-smaller condition the way `Target` cannot, and reading
off `ZoneEntered`/`ZoneExited` for an aura that only penalises attacks
against somebody *other* than the caster.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    Effect,
    Keyword,
    Melee,
    Position,
    Size,
    When,
    power,
)
from combat_engine.engine.components import Movement, Stats
from combat_engine.engine.events import Hit, MoveStart, ZoneEntered, ZoneExited
from combat_engine.engine.query import team
from combat_engine.engine.triggers import by_melee

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_SIZE_ORDER = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE, Size.HUGE, Size.GARGANTUAN)


def _medium_or_smaller(c: Cast, who: int) -> bool:
    size = c.size_of(who)
    return _SIZE_ORDER.index(size) <= _SIZE_ORDER.index(Size.MEDIUM)


def _melee_weapon_hit_by_me(c: Cast, ev: Hit) -> bool:
    """"A melee basic weapon attack" -- the narrower half of `by_melee`
    this file needs twice, read off the row behind the blow."""
    from combat_engine.engine import get

    if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and Keyword.WEAPON in row.keywords


# ==========================================================================
# m1459
# ==========================================================================


@power(
    "m1459a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 6),
)
def m1459a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1459a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 6),
)
def m1459a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if _medium_or_smaller(c, c.target):
            c.prone()


# ==========================================================================
# m1463
# ==========================================================================


@power(
    "m1463a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m1463a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _without_swim(c: Cast, who: int | None) -> bool:
    """"A creature without a swim speed", read off the component that holds it.

    The marker this replaces asked for a `query` helper. There is no helper,
    but the fact is not missing: `Movement.modes` is the dict a stat block's
    "(swim 10)" loads into, so the question is a lookup. A creature with no
    `Movement` at all has no swim speed either, which is the same answer.
    """
    if who is None:
        return False
    moves = c.world.get(who, Movement)
    return moves is None or not moves.modes.get("swim")


def _in_water_vs_landbound(c: Cast) -> Callable[[dict], bool]:
    """"While in water, ... against creatures without a swim speed."

    Two rows on this block print the sentence and one of them aims it at the
    rider, so the gate is written once. `c.terrain` is the fight's own word
    and the target comes off the attack context.
    """
    return lambda ctx: c.terrain("aquatic") and _without_swim(c, ctx.get("target"))


@power(
    "m1463a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1463a1(c: Cast) -> None:
    """Both of the rider's benefits, and both gated the way the card gates them.

    "Without a swim speed" was marked unaskable. It is a lookup -- see
    `_without_swim` -- so the water clause is written rather than left out.

    **The 9th-level half was not being asked at all.** The docstring claimed
    the Requirement was checked at payout time and the gate only tested that
    there was a rider, so a 1st-level one collected the extra 1d10. It is
    read off `Stats` now, inside the gate, because a rider's level cannot
    change mid-fight but *which* creature is riding can.

    The rider is still read when the trait arms, which is the one shortfall
    left and is not a marker: nothing announces mounting, so a creature that
    climbs on in round three is not covered. `f3777` records the same limit
    for the same reason.
    """
    rider_now = c.rider()
    if rider_now is None:
        return

    def mounted_by_a_veteran(ctx: dict) -> bool:
        rider = c.rider()
        if rider is None or rider not in c.allies():
            return False
        theirs = c.world.get(rider, Stats)
        return theirs is not None and theirs.level >= 9

    c.bonus(
        "damage", 0, dice="1d10", on=rider_now, until=When.ENCOUNTER,
        when=lambda ctx: (
            mounted_by_a_veteran(ctx)
            and ctx.get("target") is not None
            and bool(ctx.get("charge"))
        ),
    )
    in_water = _in_water_vs_landbound(c)
    c.bonus(
        "attack", 2, on=rider_now, until=When.ENCOUNTER,
        when=lambda ctx: mounted_by_a_veteran(ctx) and in_water(ctx),
    )


@power(
    "m1463a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1463a2(c: Cast) -> None:
    """"While in water" is the fight's own word and "against creatures
    without a swim speed" is a lookup on `Movement.modes` -- see
    `_without_swim`, which replaces the marker that called it unaskable."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER,
            when=_in_water_vs_landbound(c))


# ==========================================================================
# m1464
# ==========================================================================


@power(
    "m1464a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4),
)
def m1464a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5969
# ==========================================================================


@power(
    "m5969a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m5969a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5969a1",
    level=8,
    usage=ENCOUNTER,
    uses=2,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 7),
)
def m5969a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5969a2",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5969a2(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m6404
# ==========================================================================


@power(
    "m6404a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6404a0(c: Cast) -> None:
    """"Enemies take a -2 penalty to attack rolls against creatures other
    than it, while in the aura" -- membership diffed off `ZoneEntered` /
    `ZoneExited`, the shape `_sapping_aura` already settled below this
    level. Whoever is already standing inside when it arms is not caught;
    that gap is the one `_sapping_aura`'s own docstring already owns."""
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)
    held: dict[int, Effect] = {}

    def enter(ev: ZoneEntered) -> None:
        if ev.zone != ring or ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        held[ev.actor] = c.penalty(
            "attack", 2, on=ev.actor, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") != me,
        )

    def leave(ev: ZoneExited) -> None:
        eff = held.pop(ev.actor, None)
        if eff is not None:
            c.world.effects.end(eff, "left the aura")

    c.watch(ZoneEntered, enter, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, leave, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")


@power(
    "m6404a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6404a1(c: Cast) -> None:
    """"An enemy cannot enter this creature's space by any means."

    `c.blocks_entry()` is the whole clause. An occupied square is already
    closed to ordinary movement; what "by any means" adds is that the two
    things which normally open one -- phasing through the creature, and the
    creature having been made shareable -- do not work here. See
    `movement.blocks_entry` for what it deliberately does not beat.
    """
    c.blocks_entry()


@power(
    "m6404a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 7),
)
def m6404a2(c: Cast) -> None:
    """"If the target shifts before the start of its next turn, it can use
    this attack against it as an opportunity action" -- a watch on the
    shift itself, open for exactly that long and no longer."""
    me = c.me
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return

        def watch_shift(ev: MoveStart) -> None:
            if ev.actor != victim or ev.kind_ != "shift":
                return
            pos_me = c.world.get(me, Position)
            pos_them = c.world.get(victim, Position)
            if pos_me is not None and pos_them is not None:
                c.provoke(victim, on=me, why="it shifted")

        c.watch(MoveStart, watch_shift, until=When.SONT, on=me, label=f"{c.ref} watch")


@power(
    "m6404a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def m6404a3(c: Cast) -> None:
    me = c.me
    c.stance(on=me, label=c.ref)

    def splash(ev: Hit) -> None:
        if not _melee_weapon_hit_by_me(c, ev):
            return
        foe = next((f for f in c.enemies() if f != ev.target and c.adjacent(f)), None)
        if foe is not None:
            c.flat(4, on=foe)

    c.watch(Hit, splash, until=When.STANCE, on=me, label=f"{c.ref} cleave")


@power(
    "m6404a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def m6404a4(c: Cast) -> None:
    me = c.me
    c.stance(on=me, label=c.ref)

    def step(ev: Hit) -> None:
        if _melee_weapon_hit_by_me(c, ev):
            c.shift(1)

    c.watch(Hit, step, until=When.STANCE, on=me, label=f"{c.ref} step")


@power(
    "m6404a5",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6404a5(c: Cast) -> None:
    me = c.me
    for eff in list(c.world.effects.of(me)):
        if Condition.SLOWED in eff.conditions or Condition.IMMOBILIZED in eff.conditions:
            c.world.effects.end(eff, "shaken off")
    c.ignores_difficult(on=me, until=When.EOT)
    c.shift(5)
