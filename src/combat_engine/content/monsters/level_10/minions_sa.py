"""Monster abilities, level 10, minions.

Eighteen stat blocks, forty-two rows; one block (`m812`) prints no
abilities at all and has nothing to decorate.

Conventions, inherited from the level-1 to level-9 minion sweeps:

* numbers load from `game.db` -- a minion's own flat damage is
  `Damage("", n, kind=MINION)`, and its 1 hp is a database column, never
  written here;
* a printed range band like "5/10" takes the short number;
* a card with no printed range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims;
* "Target: a creature grabbed by it" is the target's own state, not the
  chooser's business -- `Target` filters side, count and size and not what
  a creature is suffering, so `_restricted_to` (level_03) is reused here
  and every use is marked `dropped=("Target.kind",)`;
* a printed escape DC has nowhere to go -- `c.grab` sets the hold and takes
  no number -- so every grab here is `dropped=("c.grab(dc=)",)`;
* self-destruction ("turns to ash and is destroyed") is a flat, unresisted
  amount of damage far past any plausible hit point total, the shape
  `level_08/minions_sa.py`'s `m6423a0` already settled.

Two new local helpers: `_kin_within` counts other creatures of the exact
same stat block in a radius (level-2's `_kin_adjacent` only asks at range
1), and `_adjacent_to_any_creature` is the world-level Requirement a
teleport-beside-a-creature trait needs.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import _free_square_beside
from combat_engine.content.monsters.level_08.brutes import _aura
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
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
    Health,
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
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Escaped,
    Hit,
    TurnEnd,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import adjacent, alive, creatures, distance_between, team
from combat_engine.engine.triggers import Trigger, about_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _kin_within(c: Cast, radius: int, ref: str) -> int:
    """How many other creatures of this exact stat block are within radius,
    the caster left out."""
    me = c.me
    return sum(
        1
        for a in c.within(radius, side="ally")
        if a != me and (ident := c.world.get(a, Ident)) is not None and ident.ref == ref
    )


def _adjacent_to_any_creature(world: World, eid: int) -> bool:
    """"Must be adjacent to a creature", asked of the board rather than one
    side -- a teleport that needs *anybody* next to it to have a place to
    aim from."""
    return any(o != eid and alive(world, o) and adjacent(world, eid, o) for o in creatures(world))


# ==========================================================================
# m1151
# ==========================================================================


@power(
    "m1151a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 10, kind=MINION),
)
def m1151a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1151_DOWN = "the m1151 drops to 0 hit points"


@power(
    "m1151a1",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    attack=Attack(vs=WILL, printed=12),
    trigger=_M1151_DOWN,
    on=Trigger(Dropped, about_me, _M1151_DOWN),
)
def m1151a1(c: Cast) -> None:
    """"Cursed with m1151 domination" reads as the condition it names rather
    than a flavour word -- a death burst that dominates whoever it catches."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1151a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1151a2(c: Cast) -> None:
    """A pure sense -- nothing on a board rolls for it and nothing it finds
    has a combat use."""


# ==========================================================================
# m115910
# ==========================================================================


@power(
    "m115910a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.restrict(only=)",),
)
def m115910a0(c: Cast) -> None:
    """The ash half plays; cutting the creature down to a single move action
    for the turn needs a way to take away every other action kind at once,
    which nothing in `Cast` does -- `c.no_basic` removes what a row is used
    *as*, not a whole category."""
    me = c.me

    def expire(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor == me and c.terrain("sunlight"):
            c.flat(999, on=me)

    c.watch(TurnEnd, expire, until=When.ENCOUNTER, on=me, label=f"{c.ref} ash")


@power(
    "m115910a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION),
    dropped=("c.grab(dc=)",),
)
def m115910a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if not c.grabbing(of=c.me):
            c.grab()


@power(
    "m115910a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 10, kind=MINION),
    dropped=("Target.kind",),
)
def m115910a2(c: Cast) -> None:
    """Restricted to the creature it is already holding; dazed "until the
    grab ends" is a duration the enum has no word for, so the hold is ended
    by hand on a successful escape."""
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.is_(Condition.DAZED, on=victim) or c.strike(on=victim):
        c.hit(on=victim)
    else:
        return
    me = c.me
    held = c.dazed(on=victim, until=When.ENCOUNTER)
    if held is None:
        return

    def freed(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim and ev.success:
            c.world.effects.end(held, "the grab ended")

    c.watch(Escaped, freed, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} dazed")


# ==========================================================================
# m2076
# ==========================================================================


@power(
    "m2076a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, kind=MINION),
)
def m2076a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2076a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 5, kind=MINION),
)
def m2076a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2094
# ==========================================================================


@power(
    "m2094a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 5, kind=MINION),
)
def m2094a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2230
# ==========================================================================


@power(
    "m2230a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, kind=MINION),
)
def m2230a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2230_DOWN = "the m2230 drops to 0 hit points"


@power(
    "m2230a1",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d8", 5),
    trigger=_M2230_DOWN,
    on=Trigger(Dropped, about_me, _M2230_DOWN),
)
def m2230a1(c: Cast) -> None:
    """The extraction lost the defence word on this one -- "+13 vs ;" --
    read as AC, the defence every other attack on this block names."""
    if c.strike():
        c.hit()


# ==========================================================================
# m2251
# ==========================================================================


@power(
    "m2251a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION),
)
def m2251a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2251a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2251a1(c: Cast) -> None:
    for d in (AC, "fort", "ref", "will"):
        c.bonus(
            d, 2, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda _ctx: _kin_within(c, 5, "m2251") >= 2,
        )


# ==========================================================================
# m2328
# ==========================================================================


@power(
    "m2328a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 6, kind=MINION),
)
def m2328a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m2328a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("", 6, kind=MINION, dtype=DamageType.POISON),
)
def m2328a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2598
# ==========================================================================


@power(
    "m2598a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("", 7, kind=MINION),
)
def m2598a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3799
# ==========================================================================


@power(
    "m3799a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION, dtype=DamageType.NECROTIC),
)
def m3799a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3799a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("", 8, kind=MINION, dtype=DamageType.NECROTIC),
)
def m3799a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4608
# ==========================================================================


@power(
    "m4608a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 8, kind=MINION),
)
def m4608a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4608a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 8, kind=MINION),
)
def m4608a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4608a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4608a2(c: Cast) -> None:
    me = c.me

    def proned(ev: Hit) -> None:
        if ev.attacker == me and bool(getattr(ev.result, "advantage", False)):
            c.prone(on=ev.target)

    c.watch(Hit, proned, until=When.ENCOUNTER, on=me, label=f"{c.ref} trip")


# ==========================================================================
# m5122
# ==========================================================================


@power(
    "m5122a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5122a0(c: Cast) -> None:
    """Telepathy among its own kind -- nothing on a board rolls for it and
    it has no combat meaning of its own."""


@power(
    "m5122a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION),
)
def m5122a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_ally_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    who = ev.actor
    if who == me or team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 1


_M5122_KIN_BLOODIED = "a creature adjacent to the m5122 becomes bloodied"


@power(
    "m5122a2",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5122_KIN_BLOODIED,
    on=Trigger(Bloodied, _adjacent_ally_bloodied, _M5122_KIN_BLOODIED),
)
def m5122a2(c: Cast) -> None:
    """Same stat block, same hit points, same powers by construction --
    `c.summon` joins the new copy to the initiative order on its own."""
    twin = c.summon("m5122")
    if not twin:
        return
    mine = c.world.get(c.me, Health)
    theirs = c.world.get(twin, Health)
    if mine is not None and theirs is not None:
        theirs.hp = mine.hp


_ELEMENTAL_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


@power(
    "m5122a3",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me and ev.dtype in _ELEMENTAL_TYPES,
        "it takes acid, cold, fire, lightning, or thunder damage",
    ),
)
def m5122a3(c: Cast) -> None:
    hit_type = getattr(c.trigger, "dtype", None)
    if hit_type is not None:
        c.resist(10, hit_type, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5187
# ==========================================================================


@power(
    "m5187a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 9, kind=MINION),
)
def m5187a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5187a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 2, kind=MINION),
)
def m5187a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


# ==========================================================================
# m5742
# ==========================================================================


@power(
    "m5742a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5742a0(c: Cast) -> None:
    """"+1 per adjacent ally, up to +4" written as four same-kind bonuses
    gated on a rising headcount -- same `kind` does not stack, the larger
    wins, so only the highest count that is actually true ever applies."""
    me = c.me
    for n in range(1, 5):
        c.bonus(
            AC, n, on=me, until=When.ENCOUNTER, kind="power",
            when=lambda _ctx, n=n: sum(1 for a in c.within(1, of=me, side="ally") if a != me) >= n,
        )


@power(
    "m5742a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION),
)
def m5742a1(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        dealt = 10 if bool(getattr(c.result, "advantage", False)) else 8
        c.flat(dealt)


@power(
    "m5742a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 8, kind=MINION),
)
def m5742a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5742a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.MINOR,
    reach=CloseBlast(3),
    target=Target(side="any", everyone=True, label="creatures in the blast"),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("", 9, kind=MINION, dtype=DamageType.LIGHTNING),
)
def m5742a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5811
# ==========================================================================


@power(
    "m5811a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5811a0(c: Cast) -> None:
    _aura(
        c, 1, lambda who: who in c.enemies(),
        lambda who: c.no_cover(on=who, until=When.ENCOUNTER),
    )


@power(
    "m5811a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("", 8, kind=MINION, dtype=DamageType.THUNDER),
)
def m5811a1(c: Cast) -> None:
    """The fly-and-strike-once shape is written as move-then-attack rather
    than an attack mid-flight, which the engine has no finer unit for."""
    c.no_provoke(on=c.me, until=When.EOT)
    c.move(c.speed_of(), at="fly")
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


def _ally_near_me_hurt(world: World, me: int, ev: DamageRolled) -> bool:
    victim = ev.target
    if victim == me or team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, victim) <= 1


_M5811_SHIELDED = "an attack damages an ally in the m5811's space or adjacent to it"


@power(
    "m5811a2",
    level=10,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5811_SHIELDED,
    on=Trigger(DamageRolled, _ally_near_me_hurt, _M5811_SHIELDED),
)
def m5811a2(c: Cast) -> None:
    c.halve()
    c.flat(999, on=c.me)


# ==========================================================================
# m6005
# ==========================================================================


@power(
    "m6005a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("", 9, kind=MINION, dtype=DamageType.NECROTIC),
)
def m6005a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6005a1",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_adjacent_to_any_creature,
    requires_text="the shadow must be adjacent to a creature",
)
def m6005a1(c: Cast) -> None:
    victim = next((f for f in c.within(6) if f != c.me), None)
    if victim is None:
        return
    spot = _free_square_beside(c, victim)
    if spot is not None:
        c.teleport(6, to=spot)


_M6005_DOWN = "the shadow drops to 0 hit points"


@power(
    "m6005a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6005_DOWN,
    on=Trigger(Dropped, about_me, _M6005_DOWN),
)
def m6005a2(c: Cast) -> None:
    for who in c.within(1, side="any"):
        if who != c.me:
            c.flat(9, dtype=DamageType.NECROTIC, on=who)


# ==========================================================================
# m6137
# ==========================================================================


@power(
    "m6137a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 9, kind=MINION),
)
def m6137a0(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        dealt = 12 if bool(getattr(c.result, "advantage", False)) else 9
        c.flat(dealt)


# ==========================================================================
# m6638
# ==========================================================================


@power(
    "m6638a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6638a0(c: Cast) -> None:
    """Breathing underwater has no suffocation rule to switch off, so only
    the attack-roll half needs a body."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("aquatic")
        and ctx.get("target") is not None
        and not c.is_kind("aquatic", on=ctx["target"]),
    )


@power(
    "m6638a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 9, kind=MINION),
    dropped=("c.grab(dc=)", "c.restrict(only=)"),
)
def m6638a1(c: Cast) -> None:
    """Keeping it to pincers against only the creature it holds is a
    restriction on its own options that nothing in `Cast` can lay; the
    combat-advantage half plays."""
    victim = c.target
    if c.strike():
        c.hit()
        if not c.grabbing(of=c.me):
            c.grab()
    if victim is not None:
        c.gains_advantage(
            lambda ctx: ctx.get("target") in c.grabbing(of=c.me), until=When.ENCOUNTER
        )


# ==========================================================================
# m966
# ==========================================================================


@power(
    "m966a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 3, kind=MINION),
)
def m966a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m966a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("", 6, kind=MINION, dtype=DamageType.FORCE),
)
def m966a1(c: Cast) -> None:
    if c.strike():
        c.hit()
