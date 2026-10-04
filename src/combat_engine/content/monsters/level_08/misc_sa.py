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


@power(
    "m1463a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.has_swim_speed",),
)
def m1463a1(c: Cast) -> None:
    """"While mounted by a friendly rider of 9th level or higher" is asked
    at the moment the bonus would pay, not when the trait arms, since a
    rider can mount after the fight starts. "Without a swim speed" has
    nothing to ask: no query reads a creature's movement modes for one."""

    def charge_bonus(ctx: dict) -> bool:
        rider = c.rider()
        return rider is not None and ctx.get("target") is not None and bool(ctx.get("charge"))

    rider_now = c.rider()
    if rider_now is not None:
        c.bonus("damage", 0, dice="1d10", on=rider_now, until=When.ENCOUNTER, when=charge_bonus)


@power(
    "m1463a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.has_swim_speed",),
)
def m1463a2(c: Cast) -> None:
    """"While in water" is askable; "against creatures without a swim
    speed" is not -- nothing reads another creature's movement modes."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.terrain("water"))


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
    todo=("c.blocks_entry()",),
)
def m6404a1(c: Cast) -> None:
    """"An enemy cannot enter its space by any means." No verb refuses
    entry into a specific creature's square -- ordinary occupancy already
    blocks walking into one, but nothing here distinguishes that default
    from the printed, absolute line, so there is nothing to demonstrate
    either way."""


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
