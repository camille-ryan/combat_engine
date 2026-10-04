"""Monster abilities, level 8: the minions.

The first minion sweep at this level -- there is no `minions.py` to leave
alone. Twelve stat blocks, thirty-five rows.

Conventions, inherited from the brute and other role files at this level:

* numbers load from `game.db`; a minion's own flat damage is
  `Damage("", n, kind=MINION)`, and its 1 hp is a database column, never
  written here;
* a card with no printed range is melee 1;
* a close burst or blast whose card names no target set takes enemies,
  except where it says "creatures in the burst" outright;
* a **trait** costs no action, has no target, and arms what holds it;
* "Effect (No Action)" is written as `action=FREE` -- the engine has no
  separate no-action category and free is the nearest real one.

Two riders print a second, genuinely different ref beside the block's own
("m4267 or m4268") and are kept as refs, never resolved to a name.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.soldiers_sa import _save_ends_on_me
from combat_engine.content.monsters.level_08.brutes import (
    _aura,
    _melee_ctx,
    _struck_by,
    _struck_in_melee,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Target,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    Dropped,
    EffectApplied,
    Hit,
    PowerUsed,
    RoundStart,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.triggers import Trigger, about_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _kin_adjacent(c: Cast, ref: str) -> bool:
    """Is another creature of this exact stat block (not just any ally)
    next to the caster -- the "while an m1502 ally is adjacent" shape."""
    for who in c.within(1, side="ally"):
        ident = c.world.get(who, Ident)
        if ident is not None and ident.ref == ref:
            return True
    return False


def _kin_count(c: Cast, who: int, ref: str) -> int:
    """How many creatures of this exact block are adjacent to `who`,
    the caster left out -- "1 extra damage for each additional <kin>"."""
    me = c.me
    count = 0
    for a in c.within(1, of=who, side="ally"):
        if a == me:
            continue
        ident = c.world.get(a, Ident)
        if ident is not None and ident.ref == ref:
            count += 1
    return count


def _ongoing_amount(c: Cast, victim: int, dtype: DamageType) -> int:
    """The strongest ongoing burn of that type already on the creature, or 0."""
    best = 0
    for eff in c.world.effects.of(victim):
        if eff.ongoing and eff.ongoing[1] is dtype:
            best = max(best, eff.ongoing[0])
    return best


def _ignored_by_adjacent_enemy(world: World, me: int, ev: PowerUsed) -> bool:
    """"An enemy adjacent to it attacks without including it as a target."
    Read off `PowerUsed` rather than `AttackDeclared`, which fires once
    per target rolled against and so cannot say what the *whole* use left
    out; `PowerUsed.targets` is the complete list in one place."""
    actor = ev.actor
    if actor == me or team(world, actor) is team(world, me):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    return me not in ev.targets


def _second_kin_hit_slows(c: Cast, ref: str) -> None:
    """"If two or more <ref>s hit the same target in the same round, the
    second attack also slows it until the end of the second attacker's
    next turn."

    The tally lives on the world, because the second hit can land from a
    different creature of the same block than the first, and is cleared
    every round so last round's hits do not carry over. Each instance of
    the block arms its own copy, filtered to its own hits -- when a
    creature's own watch sees itself land the *second* hit of the round, it
    is that creature's own next turn `EONT` is read from, which is what the
    card means by "the second attacker's."
    """
    me = c.me
    tally = getattr(c.world, "_kin_round_hits", None)
    if tally is None:
        tally = {}
        c.world._kin_round_hits = tally  # type: ignore[attr-defined]

    def reset(ev: RoundStart) -> None:
        tally.clear()

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        ident = c.world.get(me, Ident)
        if ident is None or ident.ref != ref:
            return
        key = (ref, ev.target)
        seen = tally.get(key, 0)
        tally[key] = seen + 1
        if seen >= 1:
            c.slowed(until=When.EONT, on=ev.target)

    c.watch(RoundStart, reset, until=When.ENCOUNTER, on=me, label=f"{c.ref} round")
    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} tally")


# ==========================================================================
# m115929
# ==========================================================================


@power(
    "m115929a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115929a0(c: Cast) -> None:
    def hold(who: int) -> Any:
        return c.grants_advantage(on=who, to="team", until=When.ENCOUNTER)

    _aura(c, 1, lambda who: who in c.enemies(), hold)


@power(
    "m115929a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 8, kind=MINION),
)
def m115929a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M115929_IGNORED = "an enemy adjacent to it attacks without including it as a target"


@power(
    "m115929a2",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115929_IGNORED,
    on=Trigger(PowerUsed, _ignored_by_adjacent_enemy, _M115929_IGNORED),
)
def m115929a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m115929a1", on=foe)


# ==========================================================================
# m1502
# ==========================================================================


@power(
    "m1502a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m1502a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1502_SAVE = "it suffers an effect that a save can end"


@power(
    "m1502a1",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1502_SAVE,
    on=Trigger(EffectApplied, _save_ends_on_me, _M1502_SAVE),
)
def m1502a1(c: Cast) -> None:
    """Reuses the level-2 shape exactly: the most recent save-ends hold on
    this creature is the effect `EffectApplied`/`Hit` just put there."""
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


@power(
    "m1502a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1502a2(c: Cast) -> None:
    c.conceal(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: _kin_adjacent(c, "m1502"))


@power(
    "m1502a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1502a3(c: Cast) -> None:
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and bool(ctx.get("advantage")),
    )


# ==========================================================================
# m1821
# ==========================================================================


@power(
    "m1821a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 8, kind=MINION),
)
def m1821a0(c: Cast) -> None:
    if c.strike():
        c.flat(10 if c.bloodied(c.me) else 8)


@power(
    "m1821a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1821a1(c: Cast) -> None:
    me = c.me

    def extra(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return sum(1 for a in c.within(1, of=who, side="ally") if a != me) >= 2

    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=extra)


# ==========================================================================
# m2051
# ==========================================================================


@power(
    "m2051a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 5, kind=MINION),
)
def m2051a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2051a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
    dropped=("etl.monster.weapon()",),
)
def m2051a1(c: Cast) -> None:
    """"Requires battleaxe" cannot be asked of `c.wielding` -- a monster is
    spawned with a bare `Gear()`, and nothing in the ETL ever populates a
    monster's own weapon group onto it, so the check is false for every
    monster in the tree and not just this one. The attack plays; the
    Requirement does not gate it."""
    if c.strike():
        c.hit()


# ==========================================================================
# m3322
# ==========================================================================


@power(
    "m3322a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m3322a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3322a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3322a1(c: Cast) -> None:
    _second_kin_hit_slows(c, "m3322")


# ==========================================================================
# m4198
# ==========================================================================


@power(
    "m4198a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, kind=MINION),
)
def m4198a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M4198_DOWN = "the m4198 drops to 0 hit points"


@power(
    "m4198a1",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4198_DOWN,
    on=Trigger(Dropped, about_me, _M4198_DOWN),
    attack=Attack(vs=REF, printed=12),
    dropped=("c.disarm(magic=False)",),
)
def m4198a1(c: Cast) -> None:
    """The statue and its terrain play; the disarm half does not, on a
    killer wielding an ordinary weapon -- `c.disarm` with no `weapon=`
    falls back to `held(what="magic")`, which is only ever a weapon with
    an enhancement bonus. A mundane weapon is never found to disarm."""
    me = c.me
    c.zone(frozenset({c.here}), difficult=True, until=When.ENCOUNTER, label=c.ref)
    trig = c.trigger
    if trig is None:
        return
    killer = _struck_by(c.world, trig, me)
    if killer is None or not _struck_in_melee(c.world, trig, me):
        return
    if c.strike(on=killer):
        c.disarm(on=killer)


# ==========================================================================
# m4267
# ==========================================================================


@power(
    "m4267a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, kind=MINION),
)
def m4267a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4267a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m4267a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4267a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4267a2(c: Cast) -> None:
    """A second, genuinely different ref beside this block's own -- kept
    as a ref, not resolved to a name."""
    c.bonus(
        # Untyped: the card prints a bare "+2 bonus to AC".
        AC, 2, on=c.me, until=When.ENCOUNTER,
        when=lambda _ctx: _kin_adjacent(c, "m4267") or _kin_adjacent(c, "m4268"),
    )


# ==========================================================================
# m5623
# ==========================================================================


@power(
    "m5623a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5623a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER)
    c.cover_in(ring, side="team")


@power(
    "m5623a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.no_enter(zone)",),
)
def m5623a1(c: Cast) -> None:
    """Nothing bars a square to one side only -- `c.no_enter` blocks a
    zone for everyone, not "except its owner", which is what this trait
    needs and does not get."""


@power(
    "m5623a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m5623a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5623a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5623a3(c: Cast) -> None:
    c.immobilized(until=When.SONT, on=c.me)
    for which in (AC, FORT, REF, WILL):
        c.bonus(which, 5, on=c.me, until=When.SONT, kind="power")


# ==========================================================================
# m5793
# ==========================================================================


@power(
    "m5793a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5793a0(c: Cast) -> None:
    me = c.me

    def chill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and distance_between(c.world, me, ev.actor) <= 1:
            c.slowed(on=ev.actor, until=When.SONT)

    c.watch(TurnStart, chill, until=When.ENCOUNTER, on=me, label="m5793a0")


@power(
    "m5793a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m5793a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5793a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("", 6, kind=MINION, dtype=DamageType.PSYCHIC),
)
def m5793a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(4)


# ==========================================================================
# m5931
# ==========================================================================


@power(
    "m5931a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5931a0(c: Cast) -> None:
    """Breathing underwater has no suffocation rule to turn off, so only
    the attack-roll half of the trait needs a body."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("aquatic")
        and ctx.get("target") is not None
        and not c.is_kind("aquatic", on=ctx["target"]),
    )


@power(
    "m5931a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5931a1(c: Cast) -> None:
    me = c.me

    def extra(ev: Hit) -> None:
        if ev.attacker != me:
            return
        count = _kin_count(c, ev.target, "m5931")
        if count:
            c.flat(count, on=ev.target)

    c.watch(Hit, extra, until=When.ENCOUNTER, on=me, label="m5931a1")


@power(
    "m5931a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 8, kind=MINION),
)
def m5931a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5931_DOWN = "the m5931 drops to 0 hit points"


@power(
    "m5931a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    trigger=_M5931_DOWN,
    on=Trigger(Dropped, about_me, _M5931_DOWN),
)
def m5931a3(c: Cast) -> None:
    if c.strike():
        c.ongoing(10)


# ==========================================================================
# m6066
# ==========================================================================


@power(
    "m6066a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6066a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m6066a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6066a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6066a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 8, kind=MINION),
)
def m6066a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


# ==========================================================================
# m6423
# ==========================================================================


@power(
    "m6423a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.no_basic(scope=)",),
)
def m6423a0(c: Cast) -> None:
    """The ash-on-sunset half plays; the "only a single move action" half
    needs a way to strip a creature down to one action kind for a turn,
    which `c.no_basic` does not reach -- it takes away what a row is used
    *as*, not a whole category of action."""
    me = c.me

    def expire(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor == me and c.terrain("sunlight"):
            c.flat(999, on=me)

    c.watch(TurnEnd, expire, until=When.ENCOUNTER, on=me, label="m6423a0 ash")


@power(
    "m6423a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 5, kind=MINION, dtype=DamageType.NECROTIC),
)
def m6423a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    existing = _ongoing_amount(c, victim, DamageType.NECROTIC)
    c.ongoing(existing + 2 if existing else 5, DamageType.NECROTIC, on=victim)


@power(
    "m6423a2",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6423a2(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(6)
