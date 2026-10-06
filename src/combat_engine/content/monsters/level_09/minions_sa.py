"""Monster abilities, level 9, minions.

Seven stat blocks, thirteen rows; two of the seven (`m3114`, `m362`) print no
abilities at all and have nothing to decorate.

Conventions, inherited from the level-1 to level-8 minion sweeps:

* numbers load from `game.db` -- a minion's own flat damage is
  `Damage("", n, kind=MINION)`, and its 1 hp is a database column, never
  written here;
* a printed range band like "15/30" takes the short number;
* a card with no printed range at all is melee 1;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims;
* "+N per ally, up to a cap" is written as a ladder of same-shaped gated
  bonuses, one per step up to the cap -- untyped ones add, so the ladder's
  sum is the count capped at the top step; a typed one instead takes the
  largest active step, since same-kind bonuses do not add and the larger
  wins, which is the same ladder read the other way.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    World,
    power,
)
from combat_engine.engine.events import Dropped, Hit, TurnStart
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import flanked_by, team
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _killed_by_enemy(world: World, me: int, ev: Dropped) -> bool:
    return (
        ev.actor == me
        and ev.source is not None
        and team(world, ev.source) is not None
        and team(world, ev.source) is not team(world, me)
    )


# ==========================================================================
# m2062
# ==========================================================================


@power(
    "m2062a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 6, kind=MINION),
)
def m2062a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2062a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m2062a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2062a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2062a2(c: Cast) -> None:
    """Untyped, so the four steps of the ladder add rather than take the
    largest -- their sum is the adjacent-ally count capped at 4, which is
    what "1 extra point per ally, to a maximum of +4" means."""
    me = c.me

    def flanking_with(ctx: dict, n: int) -> bool:
        victim = ctx.get("target")
        if victim is None or not flanked_by(c.world, victim, me):
            return False
        return sum(1 for a in c.within(1, of=victim, side="ally")) >= n

    for n in range(1, 5):
        c.bonus(
            "damage", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx, n=n: flanking_with(ctx, n),
        )


# ==========================================================================
# m5905
# ==========================================================================


@power(
    "m5905a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5905a0(c: Cast) -> None:
    me = c.me

    def shrug(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            c.cure(Condition.IMMOBILIZED, Condition.MARKED, Condition.SLOWED, on=me)

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=f"{c.ref} shrug")


@power(
    "m5905a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 8, kind=MINION),
)
def m5905a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5905_KILLED = "an enemy kills the m5905"


@power(
    "m5905a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5905_KILLED,
    on=Trigger(Dropped, _killed_by_enemy, _M5905_KILLED),
)
def m5905a2(c: Cast) -> None:
    killer = getattr(c.trigger, "source", None)
    if killer is not None:
        c.vulnerable(5, DamageType.POISON, on=killer, until=When.ENCOUNTER)


# ==========================================================================
# m5984
# ==========================================================================


@power(
    "m5984a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5984a0(c: Cast) -> None:
    me = c.me

    def dazing(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and c.distance(ev.actor) <= 1:
            c.dazed(on=ev.actor, until=When.SONT)

    c.watch(TurnStart, dazing, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5984a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 8, kind=MINION, dtype=DamageType.PSYCHIC),
)
def m5984a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5984_HIT = "an attack hits the m5984"


@power(
    "m5984a2",
    level=9,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5984_HIT,
    on=Trigger(Hit, targets_me, _M5984_HIT),
)
def m5984a2(c: Cast) -> None:
    c.teleport(3)


_M5984_DOWN = "the m5984 drops to 0 hit points"


@power(
    "m5984a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5984_DOWN,
    on=Trigger(Dropped, about_me, _M5984_DOWN),
)
def m5984a3(c: Cast) -> None:
    me = c.me
    for who in c.within(1, side="enemy", of=me):
        c.dazed(on=who, until=When.SAVE_ENDS)


# ==========================================================================
# m6641
# ==========================================================================


@power(
    "m6641a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 8, kind=MINION),
)
def m6641a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6641a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6641a1(c: Cast) -> None:
    """"Uses bite at any point during that movement" has no finer unit than
    move-then-strike; the attack and damage are `m6641a0`'s own, so this row
    carries none of its own. So the flight is aimed at the creature the bite
    is for -- it is the half that has to close."""
    me = c.me
    victim = c.target
    c.no_provoke(on=me, until=When.EOT)
    c.move(c.speed_of(), at="fly", toward=victim)
    if victim is not None:
        c.use_power("m6641a0", on=victim)


# ==========================================================================
# m6684
# ==========================================================================


@power(
    "m6684a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("", 8, kind=MINION),
    dropped=("c.grab(until=)",),
)
def m6684a0(c: Cast) -> None:
    """Capping the grab at "until the start of its next turn, unless
    sustained" has no counterweight -- `c.grab` takes no duration and
    always runs to escape or the end of the fight. The sustain half, paying
    out fresh damage and dragging the grabbed creature along, plays."""
    victim = c.target
    if c.strike():
        c.hit()
        if not c.grabbing(of=c.me):
            c.grab(dc=17)
    if victim is None or victim not in c.grabbing(of=c.me):
        return

    def sustained() -> None:
        c.flat(8, on=victim)
        c.shift(1)
        c.pull(1, on=victim)

    held = c.effect(f"{c.ref} grip", until=When.SUSTAIN, on=c.me, sustain=ActionType.STANDARD)
    c.on_sustain(held, sustained)
