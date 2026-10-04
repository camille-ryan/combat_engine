"""Monster abilities, level 10: the blocks that print no role.

Eight stat blocks, twenty-five rows -- the level-10 role-less blocks, each
cut by one of the seven named roles. As at the lower levels, a role-less
block here reads like a mount's or a companion's card rather than an
encounter monster, which is a fact about the card and not an error.

Conventions, inherited from the sweeps below this level:

* numbers load from `game.db`; the attack line is `Attack(vs=AC,
  printed=N)` exactly as the card prints it, and the damage line goes in
  the header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims;
* a card printing no range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**;
* "while mounted by a friendly rider of Nth level or higher" is asked live,
  off `c.rider()`, rather than through `requires=` -- a rider can mount
  after the fight starts, and `requires=` on a trait only ever gets asked
  once, at the moment it arms (`docs/AUTHORING.md`'s warning about traits).

One block (`m790`) is a solo whose own attack line prints "+13 vs. Any" --
no single named defence -- so the body reads the target's four defence
scores and rolls once against whichever is lowest, which is mechanically
the same question the card asks. The header can only ever name one
defence, so it is marked `dropped=("Attack.vs",)`.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.components import Defenses, Stats
from combat_engine.engine.events import Hit, MoveStart
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.triggers import Trigger, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_M5543_CONDS = frozenset(
    {
        Condition.DAZED,
        Condition.DOMINATED,
        Condition.IMMOBILIZED,
        Condition.SLOWED,
        Condition.STUNNED,
    }
)


# ==========================================================================
# m1455
# ==========================================================================


@power(
    "m1455a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m1455a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1455a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m1455a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m1456
# ==========================================================================


@power(
    "m1456a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m1456a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1456a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1456a1(c: Cast) -> None:
    me = c.me

    def shielded(ctx: dict) -> bool:
        rider = c.rider()
        if rider is None or ctx.get("target") != rider:
            return False
        stats = c.world.get(rider, Stats)
        return stats is not None and stats.level >= 9 and c.moving_as("fly", on=me)

    for d in ALL_DEFENCES:
        c.bonus(d, 1, on=me, until=When.ENCOUNTER, when=shielded)


# ==========================================================================
# m1458
# ==========================================================================


@power(
    "m1458a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m1458a0(c: Cast) -> None:
    """"Can be used as part of a charge" names an eligibility, not a
    different shape of attack -- any basic attack already can be."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m1458a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
)
def m1458a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    was = c.here
    c.push(1)
    c.shift(1, to=was)


# ==========================================================================
# m1460
# ==========================================================================


@power(
    "m1460a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
)
def m1460a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1460a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.overrun(during_charge=)",),
)
def m1460a1(c: Cast) -> None:
    """A charge's own movement is a straight run to the target, with no seam
    for a mount to swap in trampling through an occupied square instead --
    nothing in `Cast` lets a trait rewrite how a charge moves. `c.rider()`
    and the level gate would be trivial; there is nothing for them to arm."""


# ==========================================================================
# m4259
# ==========================================================================


@power(
    "m4259a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6, dtype=DamageType.POISON),
)
def m4259a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4259a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4259a1(c: Cast) -> None:
    me = c.me

    def guard(ev: MoveStart) -> None:
        rider = c.rider()
        if rider is None or ev.actor not in (me, rider):
            return
        stats = c.world.get(rider, Stats)
        if stats is None or stats.level < 10:
            return
        if c.moving_as("swim", on=ev.actor):
            c.no_provoke(on=ev.actor, until=When.EOT)

    c.watch(MoveStart, guard, until=When.ENCOUNTER, on=me, label=f"{c.ref} wake")


# ==========================================================================
# m5543
# ==========================================================================


@power(
    "m5543a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 4),
)
def m5543a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5543a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
)
def m5543a1(c: Cast) -> None:
    """No "+N vs X" at all -- the printed Effect simply deals the damage."""
    victim = c.target
    if victim is not None:
        c.flat(10, dtype=DamageType.FORCE, on=victim)


@power(
    "m5543a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 8, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5543a2(c: Cast) -> None:
    primary = c.target
    if c.strike():
        c.hit()
    if primary is None:
        return
    others = [f for f in c.within(10, of=primary, side="enemy") if f != primary][:2]
    for foe in others:
        if _secondary(c, 16, REF, foe):
            c.damage("1d6", 8, dtype=DamageType.LIGHTNING, on=foe)


@power(
    "m5543a3",
    level=10,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=Target(side="any", everyone=True, label="creatures in the burst"),
    keywords=[Keyword.ZONE],
)
def m5543a3(c: Cast) -> None:
    """The zone follows the caster, so it is an aura rather than a fixed
    `c.zone` -- the one shape in `Cast` that already moves with its owner.
    "Only against attacks from outside it" is asked of the ring's own
    occupants rather than left unsaid."""
    ring = c.aura(1, until=When.ENCOUNTER, sustain=MINOR)

    def outside(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        return attacker is not None and attacker not in c.world.zones.occupants(ring)

    for d in ALL_DEFENCES:
        c.grants_in(ring, d, 2, side="team", kind="power", when=outside)


@power(
    "m5543a4",
    level=10,
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def m5543a4(c: Cast) -> None:
    """"A saving throw against one of these conditions" picks the ally's own
    held effect rather than filtering `c.save` by name -- a condition's
    label is the row that caused it, not the condition word, so a text
    match on "dazed" would never find anything."""
    for ally in c.within(5, side="ally"):
        for eff in c.world.effects.of(ally):
            if eff.when is When.SAVE_ENDS and set(eff.conditions) & _M5543_CONDS:
                c.world.effects.save(eff)
                return


_M5543_HIT = "m5543 is hit by an attack"


@power(
    "m5543a5",
    level=10,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5543_HIT,
    on=Trigger(Hit, targets_me, _M5543_HIT),
)
def m5543a5(c: Cast) -> None:
    c.invisible(until=When.EONT)
    c.shift(3)


# ==========================================================================
# m6280
# ==========================================================================


def _m6280_free(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m6280a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 10),
    requires=_m6280_free,
    requires_text="m6280 must not have a creature grabbed",
)
def m6280a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6280a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 10, kind=LIMITED),
    dropped=("c.grab(dc=)",),
)
def m6280a1(c: Cast) -> None:
    victim = c.target
    hits = 0
    for _ in range(2):
        if c.strike(on=victim):
            c.hit(on=victim)
            hits += 1
    if hits == 2 and victim is not None and not c.grabbing(of=c.me):
        c.grab(on=victim)


@power(
    "m6280a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=Target(side="enemy", everyone=True, label="enemies in the blast"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d8", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6280a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)
        c.pull(3)


# ==========================================================================
# m790
# ==========================================================================


@power(
    "m790a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m790a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m790a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
    dropped=("Attack.vs",),
)
def m790a1(c: Cast) -> None:
    """"+13 vs. Any ... the beam hits if it hits any defence" is one roll
    against whichever defence is weakest, which is the same question as
    rolling against each and taking the best outcome. The header can only
    ever name one defence."""
    victim = c.target
    if victim is None:
        return
    defs = c.world.get(victim, Defenses)
    weakest = AC if defs is None else min(ALL_DEFENCES, key=defs.base)
    bonus = c.world.scaling.trim(13, c.level)
    if c.attack(bonus, weakest, on=victim):
        c.damage(
            "1d8", 6,
            dtypes=(DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING),
            on=victim,
        )


@power(
    "m790a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m790a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m790a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m790a3(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


_M790_HIT = "it is hit by an attack"


@power(
    "m790a4",
    level=10,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M790_HIT,
    on=Trigger(Hit, targets_me, _M790_HIT),
)
def m790a4(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        c.teleport(3, who=attacker)


@power(
    "m790a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.initiative(fixed=)",),
)
def m790a5(c: Cast) -> None:
    """Acting a second and third time at fixed counts is `c.extra_turn(at=)`,
    which takes an absolute count and fits exactly. Pinning its *own* roll
    to exactly 25 instead of whatever initiative gave it has no counterpart:
    `c.initiative` only ever adds a bonus. "Cannot delay or ready" gates
    nothing the engine offers either way -- there is no delay or ready
    action here to take."""
    c.extra_turn(at=15)
    c.extra_turn(at=5)
