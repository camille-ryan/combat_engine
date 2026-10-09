"""Monster abilities, level 8: the brutes, second wave.

`brutes.py` holds the earlier sweep of this level and is not touched here;
the split is by *when* the work was done. 42 stat blocks, 145 rows.

Conventions, inherited from the levels below and from `brutes.py`'s own
docstring:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms what holds it;
* a card with no printed range is melee 1;
* a close burst or blast whose card names no target set takes enemies,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- the Miss branch is written by
  hand every time it is declared;
* several stat blocks here print this spec tool's own extraction noise
  leaking one ability's attack line into the next ("+9 vs ; 2d6+5
  damage.."), which is not a printed sentence and is read past;
* five blocks in this wave ("minion" in their own type tags despite being
  assigned as brutes) are minion-brutes: `Damage("", n, kind=MINION)`,
  same as any other minion;
* "Requirement: must be in beast/hybrid form" is a gate now. It had no
  checker when this file was written -- there was no way to ask what shape a
  creature was currently in, only to put it in one -- and
  `combat_engine.content.monsters.forms` answers it: `c.form(name=)` records
  the shape and `_shapes`/`_not_in` read it back, so these rows carry a
  `requires=` and no marker.
  `c.contract(ref)` is still the marker for "contracts a curse/disease",
  which has no mechanism.

Helpers are imported from `level_08/brutes.py` rather than written twice:
`_struck_by`, `_struck_in_melee`, `_felled_by_me`, `_crowded`, `_melee_ctx`,
`_aura`, `_is_bloodied`. `_recharge_when_bloodied` comes from the level-1
artillery file and `_secondary` from level-3 soldiers, the levels that
first needed them. `_ridden_by_seventh_level` is level 7's name for asking
a mount's rider's level live rather than through `requires=`; the two
mounts here that need the same question at one level higher get their own
copy rather than a parameter bent to take two numbers.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.forms import _not_in, _shapechange, _shapes
from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_07.brutes_sa import _ridden_by_seventh_level
from combat_engine.content.monsters.level_08.brutes import (
    _aura,
    _crowded,
    _felled_by_me,
    _melee_ctx,
    _struck_by,
    _struck_in_melee,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
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
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Escaped,
    Hit,
    Moved,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, enemies, team
from combat_engine.engine.triggers import Trigger, about_me, ally_within, both, by_keyword, by_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _kin_adjacent(c: Cast, ref: str) -> bool:
    for who in c.within(1, side="any"):
        if who == c.me:
            continue
        ident = c.world.get(who, Ident)
        if ident is not None and ident.ref == ref:
            return True
    return False


def _enemy_closed_on_me(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    return (
        actor is not None
        and actor in enemies(world, me)
        and distance_between(world, me, actor) <= 1
    )


def _ridden_by(world: World, me: int, level: int) -> bool:
    """"While mounted by a friendly rider of Nth level or higher," asked
    live -- nobody is in the saddle when a trait of this shape arms, so a
    `requires=` here would be refused once and never checked again."""
    for rider in world.relations.targets(Relation.RIDDEN_BY, me):
        if team(world, rider) is team(world, me):
            stats = world.get(rider, Stats)
            if stats is not None and stats.level >= level:
                return True
    return False


def _revives_once(c: Cast, hp: int, *, reroll: bool = False) -> None:
    """A body that rises once, with no excluded damage type -- the
    `m3533a3` troll shape, minus the exclusion that creature has and this
    one does not. Rises immediately, inside the `Dropped` window, rather
    than waiting a move action on its next turn: nothing in the engine
    owes a corpse an action, and a body that waits a round is a body
    `threat_removed` has already written off.

    Guarded by hand against a second rise: `Trigger` takes no `once=`, and
    an `AT_WILL` usage on a row that is only ever answering its own
    `Dropped` would otherwise fire every time this creature falls again.
    """
    me = c.me
    label = f"{c.ref} risen"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    c.effect(label, until=When.ENCOUNTER, on=me)
    c.revives_unless(on=me)
    if reroll:
        c.reroll_initiative(on=me)
    c.reanimate(on=me, hp=hp)


# ==========================================================================
# m1037
# ==========================================================================


@power(
    "m1037a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m1037a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1037a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM, label="Medium or smaller"),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m1037a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M1037_DOWN = "the m1037 drops to 0 hit points"


@power(
    "m1037a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M1037_DOWN,
    on=Trigger(Dropped, about_me, _M1037_DOWN),
)
def m1037a2(c: Cast) -> None:
    _revives_once(c, 44, reroll=True)


# ==========================================================================
# m1064
# ==========================================================================


@power(
    "m1064a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m1064a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1064a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
)
def m1064a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1064a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.overrun(during_charge=)",),
)
def m1064a2(c: Cast) -> None:
    """The rider still attacking at the end of the mount's movement is the
    ordinary charge sequence and needs nothing here. The stamp itself --
    trampling through one Medium-or-smaller creature's space mid-charge --
    has nowhere to attach: a charge is resolved by the engine's own action
    handling before this trait ever sees it, and `c.overrun` only works as
    the row making the move, which this trait is not."""


# ==========================================================================
# m1080
# ==========================================================================


@power(
    "m1080a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 8),
)
def m1080a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1080a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m1080a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1080a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 8),
)
def m1080a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


# ==========================================================================
# m115841
# ==========================================================================


@power(
    "m115841a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115841a0(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m115841a0")


@power(
    "m115841a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 8, dtype=DamageType.NECROTIC),
)
def m115841a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(until=When.EONT)


@power(
    "m115841a2",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
)
def m115841a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    me = c.me
    label = f"{me}:m115841a2"
    for eff in list(c.world.effects.of(me)):
        if eff.label == label:
            c.world.effects.end(eff, "used again")

    def toll(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=victim)

    c.watch(AttackDeclared, toll, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m115865
# ==========================================================================


@power(
    "m115865a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m115865a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115865a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m115865a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m115865a0", on=victim)
        if c.landed:
            hits += 1
    if hits == 2 and len(c.grabbing()) < 2:
        c.grab(on=victim)


@power(
    "m115865a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("2d8", 11),
)
def m115865a2(c: Cast) -> None:
    victim = c.target
    if victim is None or victim not in c.grabbing():
        return
    c.hit()


@power(
    "m115865a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=11),
)
def m115865a3(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m115879
# ==========================================================================


@power(
    "m115879a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.decay(magic=False)",),
)
def m115879a0(c: Cast) -> None:
    """`c.decay` only ever touches an item's enhancement bonus, so a
    mundane weapon -- which every attacker here starts as -- has nothing
    for it to take away, and the stacking -1 this card prints has no other
    hook in the engine."""


@power(
    "m115879a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 3),
    dropped=("c.decay(magic=False)",),
)
def m115879a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115879a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    dropped=("c.decay(magic=False)",),
)
def m115879a2(c: Cast) -> None:
    """Recharges on a miss rather than a roll -- `_recharge_when_bloodied`'s
    sibling shape, just armed off `Miss` instead of `Bloodied`. The target
    line and the destroy both depend on an item already being tracked as
    rusting, which is the same gap `m115879a0/a1/a3` carry -- nothing here
    is ever marked rusting, so `c.destroy` never has anything to take."""
    me = c.me
    label = "m115879a2 recharge"
    if not any(e.label == label for e in c.world.effects.of(me)):
        def back(ev: Any) -> None:
            if getattr(ev, "attacker", None) == me and getattr(ev, "power", None) == c.ref:
                known = c.world.get(me, Powers)
                if known is not None:
                    known.restore(c.ref)

        from combat_engine.engine.events import Miss

        c.watch(Miss, back, until=When.ENCOUNTER, on=me, label=label)
    if c.strike():
        c.destroy(on=c.target)


@power(
    "m115879a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d10", 8, kind=LIMITED),
    dropped=("c.decay(magic=False)",),
)
def m115879a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1453
# ==========================================================================


@power(
    "m1453a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC),
)
def m1453a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1453a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=2, label="two different targets"),
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m1453a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1453a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d10", 10, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1453a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return

    def worsen(eff: Any) -> None:
        c.world.effects.end(eff, "first failed save")
        c.ongoing(10, DamageType.NECROTIC, on=victim)

    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        ongoing=(5, DamageType.NECROTIC), escalate=worsen,
    )


@power(
    "m1453a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
)
def m1453a3(c: Cast) -> None:
    if c.strike():
        c.push(3)
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m1521
# ==========================================================================


@power(
    "m1521a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m1521a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1521a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d10", 5),
)
def m1521a1(c: Cast) -> None:
    """Two bites at one target, each at the -2 the card prints -- read as
    two separate rolls rather than the engine's own "two attacks" helper,
    since only one of the two carries this block's own damage line."""
    _recharge_when_bloodied(c)
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        if c.strike(plus=-2):
            c.hit()


@power(
    "m1521a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m1521a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1521a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.counts_as(group=)",),
)
def m1521a3(c: Cast) -> None:
    """Nothing lets another row's "if bloodied" ask treat a creature as
    bloodied on account of a condition rather than its own hit points --
    `Health.bloodied` is read directly everywhere that matters."""


# ==========================================================================
# m1739
# ==========================================================================


@power(
    "m1739a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m1739a0(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d6", 7 if c.bloodied(c.me) else 5)
    if c.bloodied(on=c.target):
        c.prone()


_M1739_DOUBLE = "m1739a2"


@power(
    "m1739a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1739a1(c: Cast) -> None:
    me = c.me
    label = f"{me}:{_M1739_DOUBLE}"

    def retaliate(ev: Bloodied) -> None:
        if _struck_by(c.world, ev, ev.actor) != me or not _struck_in_melee(c.world, ev, ev.actor):
            return
        doubled = next((e for e in c.world.effects.of(me) if e.label == label), None)
        n = 1
        if doubled is not None:
            n = 2
            c.world.effects.end(doubled, "spent")
        mates = [a for a in c.allies() if c.adjacent_to(ev.actor, a)][:n]
        for mate in mates:
            c.grant_attack(mate, on=ev.actor)

    c.watch(Bloodied, retaliate, until=When.ENCOUNTER, on=me, label="m1739a1")


@power(
    "m1739a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1739a2(c: Cast) -> None:
    c.effect(f"{c.me}:{_M1739_DOUBLE}", until=When.ENCOUNTER, on=c.me)


@power(
    "m1739a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1739a3(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and ctx.get("target") is not None
        and _crowded(c, ctx["target"], 2),
    )


# ==========================================================================
# m1820
# ==========================================================================


@power(
    "m1820a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 8),
)
def m1820a0(c: Cast) -> None:
    if not c.strike():
        return
    hurt = c.bloodied(c.me)
    if c.crit:
        c.flat(c.roll("3d8") + (26 if hurt else 24))
    else:
        c.damage("2d8", 10 if hurt else 8)


@power(
    "m1820a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d8", 8, kind=LIMITED),
)
def m1820a1(c: Cast) -> None:
    """"Allies within the aura" with no aura of its own size printed on
    this block -- read as every gnoll ally it has, the only set this line
    could mean without one."""
    if not c.strike():
        return
    victim = c.target
    hurt = c.bloodied(c.me)
    if c.crit:
        c.flat(c.roll("3d8") + (42 if hurt else 40))
    else:
        c.damage("4d8", 10 if hurt else 8)
    for mate in c.allies():
        if c.is_kind("gnoll", on=mate) and victim is not None:
            c.basic(on=victim, who=mate)


@power(
    "m1820a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1820a2(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and ctx.get("target") is not None
        and _crowded(c, ctx["target"], 2),
    )


_M1820_WEAPON_HIT = "an attack with the weapon keyword hits"


@power(
    "m1820a3",
    level=8,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1820_WEAPON_HIT,
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.WEAPON)), _M1820_WEAPON_HIT),
)
def m1820a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.ongoing(13, on=victim)


# ==========================================================================
# m2246
# ==========================================================================


@power(
    "m2246a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 3),
)
def m2246a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2246a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=2, max_size=Size.MEDIUM, label="adjacent Medium or smaller"),
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=11),
)
def m2246a1(c: Cast) -> None:
    """"Automatically hits an immobilized creature" substitutes for the
    roll only then; the acid keeps burning until the grab itself ends
    rather than on a save -- there is no `When` for that, so the ongoing
    is ended by hand when the creature escapes."""
    victim = c.target
    if victim is None:
        return
    landed = c.is_(Condition.IMMOBILIZED, on=victim) or bool(c.strike())
    if not landed:
        return
    c.grab(on=victim)
    c.shares_space(on=victim, until=When.ENCOUNTER)
    c.dazed(until=When.EONT)
    burn = c.ongoing(11, DamageType.ACID, on=victim, until=When.ENCOUNTER)
    me = c.me

    def freed(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim and ev.success and burn is not None:
            c.world.effects.end(burn, "the grab ends")

    c.watch(Escaped, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


@power(
    "m2246a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2246a2(c: Cast) -> None:
    me = c.me
    c.hide(until=When.ENCOUNTER)

    def seen(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            c.unhide()

    c.watch(AttackDeclared, seen, until=When.ENCOUNTER, on=me, label="m2246a2")


# ==========================================================================
# m2248
# ==========================================================================


@power(
    "m2248a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m2248a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2248a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2248a1(c: Cast) -> None:
    """Granted to the roster present when the trait arms, which is
    everyone this block fights beside -- allies arriving mid-fight are a
    gap no card of this shape in the tree has closed either."""
    me = c.me

    def flanking(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and team(c.world, who) is not team(c.world, me) and any(
            c.world.get(k, Ident) is not None
            and c.world.get(k, Ident).ref == "m2248"
            and distance_between(c.world, k, who) <= 1
            for k in [me, *c.allies()]
        )

    for who in [me, *c.allies()]:
        c.bonus("damage", 0, dice="1d6", on=who, until=When.ENCOUNTER, when=flanking)


@power(
    "m2248a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2248a2(c: Cast) -> None:
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m2248a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2248a3(c: Cast) -> None:
    me = c.me

    def reward(victim: int) -> None:
        for who in [me, *c.allies()]:
            if distance_between(c.world, me, who) <= 5:
                c.temp_hp(5, on=who)

    def bled(ev: Bloodied) -> None:
        if _struck_by(c.world, ev, ev.actor) == me:
            reward(ev.actor)

    def felled(ev: Dropped) -> None:
        if _felled_by_me(c.world, me, ev):
            reward(ev.actor)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label="m2248a3 bloody")
    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, label="m2248a3 drop")


@power(
    "m2248a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2248a4(c: Cast) -> None:
    me = c.me

    def strike_after(ev: Moved) -> None:
        if ev.actor != me or ev.kind_ != "charge":
            return
        for foe in list(c.enemies()):
            if distance_between(c.world, me, foe) <= 1:
                c.use_power("m2248a0", on=foe)

    c.watch(Moved, strike_after, until=When.ENCOUNTER, on=me, label="m2248a4")


# ==========================================================================
# m2303
# ==========================================================================


@power(
    "m2303a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 5),
)
def m2303a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2303a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m2303a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m2303a0", on=victim)
    if c.landed:
        c.grab(on=victim)
        return
    c.use_power("m2303a0", on=victim)


@power(
    "m2303a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 5),
)
def m2303a2(c: Cast) -> None:
    victim = c.target
    if victim is None or victim not in c.grabbing():
        return
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.heal(25, on=c.me)


@power(
    "m2303a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m2303a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            mod = c.world.effects.apply(
                victim, c.me, When.SAVE_ENDS, label=f"{c.ref} attack-2",
                mods=[(victim, _m2303_mod(c))],
                ongoing=(5, DamageType.POISON),
            )
            _ = mod


def _m2303_mod(c: Cast) -> Any:
    from combat_engine.engine import Mod

    return Mod(what="attack", value=-2, kind="untyped", label=c.ref)


# ==========================================================================
# m3228
# ==========================================================================


@power(
    "m3228a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.reroll_initiative(keep=)",),
)
def m3228a0(c: Cast) -> None:
    """The Perception half plays. "Rolls initiative twice, uses the
    higher" is a different distribution from `c.reroll_initiative`, which
    replaces the roll outright rather than keeping the better of two, so
    it is not substituted here."""
    me = c.me
    given: set[int] = set()

    def check(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        rider = c.rider()
        if rider is None or rider in given or not _ridden_by(c.world, me, 8):
            return
        given.add(rider)
        c.bonus("perception", 2, on=rider, until=When.ENCOUNTER, kind="power")

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label="m3228a0")


@power(
    "m3228a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 10),
)
def m3228a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


# ==========================================================================
# m3320
# ==========================================================================


@power(
    "m3320a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d6", 5),
)
def m3320a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3320a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3320a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone(held=When.EONT)


@power(
    "m3320a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="bloodied, living enemy",
        bloodied=True,
        # "Living" is not a negative set. Excluding `construct` as well
        # refuses the 25 blocks that carry *both* `living` and `construct`,
        # which the card calls living; excluding only `undead` admits a
        # non-living construct. The exact test is "not undead, and not
        # construct unless it carries living", which no any-of negative can
        # say. This is the faithful half -- what the body asked before the
        # conversion -- and the exception is marked. #411.
        kinds_without=frozenset({"undead"}),
    ),
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("6d6", 5, dtype=DamageType.NECROTIC),
    dropped=("Target.living",),
)
def m3320a2(c: Cast) -> None:
    """Both halves of the target line are the header's now -- `bloodied=` and
    `kinds_without=`, "living" being the absence of the two type words that
    deny it -- so the redirect that asked them by hand came out."""
    if c.strike():
        c.hit()


@power(
    "m3320a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3320a3(c: Cast) -> None:
    def riled(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return (
            c.is_(Condition.SLOWED, on=who)
            or c.is_(Condition.IMMOBILIZED, on=who)
            or bool(ctx.get("advantage"))
        )

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=riled)


# ==========================================================================
# m3463
# ==========================================================================


@power(
    "m3463a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m3463a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


_M3463_DAMAGED = "it is damaged by an attack"


@power(
    "m3463a1",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M3463_DAMAGED,
    on=Trigger(DamageApplied, lambda w, me, ev: ev.target == me, _M3463_DAMAGED),
)
def m3463a1(c: Cast) -> None:
    """"A random enemy within its reach" -- picked as the nearest, which is
    the only ordering a board without a dice-for-targeting primitive can
    give consistently."""
    foe = next(iter(sorted(c.enemies(), key=lambda f: c.distance(f))), None)
    if foe is not None and c.distance(foe) <= 2:
        c.use_power("m3463a0", on=foe)


@power(
    "m3463a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m3463a2(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)


# ==========================================================================
# m3829
# ==========================================================================


@power(
    "m3829a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m3829a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3829a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM, label="Medium or smaller"),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m3829a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M3829_BASIC_HIT = "it hits with a melee basic attack during its turn"


@power(
    "m3829a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M3829_BASIC_HIT,
    on=Trigger(Hit, by_me, _M3829_BASIC_HIT),
)
def m3829a2(c: Cast) -> None:
    """"A melee basic attack" is read as any melee hit it lands -- there
    is no predicate that distinguishes a basic attack from any other."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.ongoing(6, DamageType.NECROTIC, on=victim)


_M3829_DOWN = "the first time the m3829 drops to 0 hit points"


@power(
    "m3829a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M3829_DOWN,
    on=Trigger(Dropped, about_me, _M3829_DOWN),
)
def m3829a3(c: Cast) -> None:
    _revives_once(c, 44, reroll=True)


# ==========================================================================
# m3834
# ==========================================================================


@power(
    "m3834a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3834a0(c: Cast) -> None:
    me = c.me

    def boost(ev: Hit) -> None:
        if not bool(getattr(ev, "charge", False)):
            return
        if ev.attacker not in c.world.relations.targets(Relation.RIDDEN_BY, me):
            return
        if not _ridden_by_seventh_level(c.world, me):
            return
        c.flat(10, on=ev.target)

    c.watch(Hit, boost, until=When.ENCOUNTER, on=me, label="m3834a0")


@power(
    "m3834a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 7),
)
def m3834a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3834a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 7),
)
def m3834a2(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


# ==========================================================================
# m4006
# ==========================================================================


@power(
    "m4006a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
)
def m4006a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and _secondary(c, 9, FORT, victim):
        c.ongoing(5, DamageType.POISON, on=victim)


# ==========================================================================
# m4166
# ==========================================================================


@power(
    "m4166a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, dtype=DamageType.ACID, kind=MINION),
)
def m4166a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4263
# ==========================================================================


@power(
    "m4263a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m4263a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4263a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m4263a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.prone()


# ==========================================================================
# m4269
# ==========================================================================


@power(
    "m4269a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m4269a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4269a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m4269a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4269a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m4269a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.prone()


# ==========================================================================
# m5388
# ==========================================================================


@power(
    "m5388a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 6),
)
def m5388a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5388a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
)
def m5388a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.push(1)
        c.prone()
        c.shift(1)


@power(
    "m5388a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5388a2(c: Cast) -> None:
    c.resist(5, None, on=c.me, until=When.EONT)


_M5388_DOWN = "the m5388 drops to 0 hit points"


@power(
    "m5388a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M5388_DOWN,
    on=Trigger(Dropped, about_me, _M5388_DOWN),
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("4d6", 6),
)
def m5388a3(c: Cast) -> None:
    foe = next(iter(c.enemies()), None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m5466
# ==========================================================================


@power(
    "m5466a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 6),
    dropped=("Power.reach_alt",),
)
def m5466a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5466a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 6),
)
def m5466a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.pull(1, on=victim)
    if c.adjacent(victim) and not c.grabbing():
        c.grab(on=victim)


_M5466_ESCAPE_FAILED = "an adjacent enemy fails to escape its grab"


@power(
    "m5466a2",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M5466_ESCAPE_FAILED,
    on=Trigger(
        Escaped,
        lambda w, me, ev: getattr(ev, "holder", None) == me and not getattr(ev, "success", True),
        _M5466_ESCAPE_FAILED,
    ),
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d8", 7),
)
def m5466a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


_M5466_STARTS_TURN = "the m5466 starts its turn"


@power(
    "m5466a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5466_STARTS_TURN,
    on=Trigger(TurnStart, about_me, _M5466_STARTS_TURN),
)
def m5466a3(c: Cast) -> None:
    me = c.me
    for cond in (Condition.DAZED, Condition.SLOWED, Condition.STUNNED, Condition.WEAKENED):
        if c.is_(cond, on=me):
            c.cure(cond, on=me)
            return
    for eff in c.world.effects.of(me):
        if eff.ongoing:
            c.world.effects.end(eff, "m5466a3")
            return


# ==========================================================================
# m5494
# ==========================================================================


def _arm_m5494_claw_tracking(c: Cast) -> None:
    me = c.me
    label = "m5494 claw-tally"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    hit_this_turn: set[int] = set()
    bucket = getattr(c.world, "_m5494_claws", None)
    if bucket is None:
        bucket = {}
        c.world._m5494_claws = bucket  # type: ignore[attr-defined]
    bucket[me] = hit_this_turn

    def mark(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m5494a0":
            hit_this_turn.add(ev.target)

    def reset(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            hit_this_turn.clear()

    c.watch(Hit, mark, until=When.ENCOUNTER, on=me, label=label)
    c.watch(TurnStart, reset, until=When.ENCOUNTER, on=me, label=f"{label} reset")


@power(
    "m5494a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m5494a0(c: Cast) -> None:
    _arm_m5494_claw_tracking(c)
    if c.strike():
        c.hit()


@power(
    "m5494a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 5),
)
def m5494a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5494a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5494a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    for _ in range(3 if c.bloodied(c.me) else 2):
        c.use_power("m5494a0", on=victim)


@power(
    "m5494a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5494a3(c: Cast) -> None:
    _recharge_when_bloodied(c)
    victim = c.target
    c.no_provoke(on=c.me, until=When.EOT)
    # The leap is what brings the two claws into reach, so it is aimed at the
    # creature they are for; unaimed it landed at the board's low corner.
    c.jump(6, toward=victim)
    if victim is None:
        return
    c.bonus("attack", 1, on=c.me, until=When.EOT)
    c.bonus("damage", 4, on=c.me, until=When.EOT)
    c.use_power("m5494a0", on=victim)
    c.use_power("m5494a0", on=victim)


@power(
    "m5494a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5494a4(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(6)


@power(
    "m5494a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="bloodied, hit this turn by claw",
        bloodied=True,
    ),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=11),
    dropped=("c.hit_this_turn()",),
)
def m5494a5(c: Cast) -> None:
    """Bloodied is the target line now. The claw half is still the dropped
    clause, so the redirect stays -- and it keeps asking bloodied of what it
    scans, because `c.enemies()` is the unfiltered pool."""
    bucket = getattr(c.world, "_m5494_claws", {})
    clawed = bucket.get(c.me, set())
    victim = c.target
    if victim is None or victim not in clawed:
        victim = next(
            (f for f in c.enemies() if c.bloodied(on=f) and f in clawed and c.distance(f) <= 1),
            None,
        )
    if victim is None:
        return
    if c.strike(on=victim):
        c.ongoing(5, DamageType.PSYCHIC, on=victim)


# ==========================================================================
# m5553
# ==========================================================================


@power(
    "m5553a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()",),
)
def m5553a0(c: Cast) -> None:
    """"Two initiative checks, a full turn on each" is the solo's own
    second-turn shape, but `c.extra_turn` takes an exact count rather than
    rolling one of its own -- there is no way from here to produce the
    second, independent roll the card asks for. The immediate-action half
    rides on the ordinary once-per-turn limit, which already doubles for
    free with two turns a round."""


@power(
    "m5553a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 3),
)
def m5553a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5553a2",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
)
def m5553a2(c: Cast) -> None:
    if c.strike():
        c.push(2)
        c.move(max(1, c.speed_of() // 2))


# ==========================================================================
# m5778
# ==========================================================================


@power(
    "m5778a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5778a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER)

    def retaliate(ev: Dropped) -> None:
        if ev.actor == me or team(c.world, ev.actor) is not team(c.world, me):
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        foe = next(iter(c.enemies()), None)
        if foe is not None:
            c.grant_attack(ev.actor, on=foe)

    c.watch(Dropped, retaliate, until=When.ENCOUNTER, on=me, label="m5778a0")


@power(
    "m5778a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5778a1(c: Cast) -> None:
    """"A creature that also has m5778a1" has no identifiable partner
    without a name to resolve it to, so this reads as any adjacent ally --
    the only non-flavour-dependent set it could mean."""
    me = c.me

    def check(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if any(c.adjacent_to(me, a) for a in c.allies()):
            c.save(on=me)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label="m5778a1")


@power(
    "m5778a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 4),
)
def m5778a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5778a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5778a3(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m5778a2", on=victim)
        c.use_power("m5778a2", on=victim)


@power(
    "m5778a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d10", 4, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m5778a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)
        c.push(1)


def _ally_hit_no_crit(world: World, me: int, ev: AttackRolled) -> bool:
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me or team(world, attacker) is not team(world, me):
        return False
    if distance_between(world, me, attacker) > 10:
        return False
    result = getattr(ev, "result", None)
    return bool(result) and result.hit and not result.critical


_M5778_RALLY = "an ally within 10 squares hits with an attack that isn't a critical hit"


@power(
    "m5778a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5778_RALLY,
    on=Trigger(AttackRolled, _ally_hit_no_crit, _M5778_RALLY),
)
def m5778a5(c: Cast) -> None:
    """The live lever: `AttackRolled` carries the real `AttackResult`, and
    `resolve.attack` recomputes the outcome from that object after
    emitting it, so setting `natural` here before it returns upgrades the
    hit to a critical."""
    result = getattr(c.trigger, "result", None)
    if result is not None:
        result.natural = 20


# ==========================================================================
# m5921
# ==========================================================================


@power(
    "m5921a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, kind=MINION),
)
def m5921a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5921_DIES = "the m5921 dies"


@power(
    "m5921a1",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M5921_DIES,
    on=Trigger(Dropped, about_me, _M5921_DIES),
)
def m5921a1(c: Cast) -> None:
    for foe in c.within(1, side="enemy"):
        c.flat(5, dtype=DamageType.PSYCHIC, on=foe)


# ==========================================================================
# m5965
# ==========================================================================


@power(
    "m5965a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 4),
)
def m5965a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M5965_CLOSED = "an enemy enters a square adjacent to it"


@power(
    "m5965a1",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBlast(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    trigger=_M5965_CLOSED,
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, _M5965_CLOSED),
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 6, dtype=DamageType.FIRE),
)
def m5965a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m5975
# ==========================================================================


@power(
    "m5975a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 7),
)
def m5975a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5975a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 2, kind=LIMITED),
)
def m5975a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


# ==========================================================================
# m5982
# ==========================================================================


@power(
    "m5982a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5982a0(c: Cast) -> None:
    def hold(who: int) -> Any:
        return c.bonus(
            "damage", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx: _melee_ctx(ctx) and c.bloodied(on=who),
        )

    _aura(c, 5, lambda who: who in c.allies(), hold)


@power(
    "m5982a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 11),
)
def m5982a1(c: Cast) -> None:
    if not c.strike():
        return
    if c.crit:
        c.flat(c.roll("1d12") + 23)
    else:
        c.hit()


_M5982_ALLY_BLOODIED = "an ally within 10 squares of m5982 is first bloodied"


@power(
    "m5982a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5982_ALLY_BLOODIED,
    on=Trigger(Bloodied, ally_within(10), _M5982_ALLY_BLOODIED),
)
def m5982a2(c: Cast) -> None:
    mate = getattr(c.trigger, "actor", None)
    foe = next(iter(c.enemies()), None)
    if mate is not None and foe is not None:
        c.grant_attack(mate, on=foe)


_M5982_DRAW = "m5982 rolls initiative or is first bloodied"


@power(
    "m5982a3",
    level=8,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5982_DRAW,
    on=Trigger(Bloodied, about_me, _M5982_DRAW),
    todo=("c.draw_card()",),
)
def m5982a3(c: Cast) -> None:
    """Nothing plays: there is no deck of action-card powers to draw from,
    and which power each card names is beyond the mechanics this row is
    shown anyway."""


_M5982_DOWN = "m5982 drops to 0 hit points"


@power(
    "m5982a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5982_DOWN,
    on=Trigger(Dropped, about_me, _M5982_DOWN),
)
def m5982a4(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m6158 / m6160 / m6244
# ==========================================================================


@power(
    "m6158a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, kind=MINION),
)
def m6158a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6160a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, kind=MINION),
)
def m6160a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6244a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, kind=MINION),
)
def m6244a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m6168
# ==========================================================================


@power(
    "m6168a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
)
def m6168a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def extra(ev: Hit) -> None:
        victim = ev.target
        if victim == me or team(c.world, victim) is team(c.world, me):
            return
        if victim not in c.world.zones.occupants(ring) or not c.bloodied(on=victim):
            return
        c.flat(5, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=victim)

    c.watch(Hit, extra, until=When.ENCOUNTER, on=me, label="m6168a0")


@power(
    "m6168a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 4),
)
def m6168a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(1)
    if c.result is not None and c.result.advantage:
        c.ongoing(5, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=victim)


@power(
    "m6168a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6168a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m6168a1", on=victim)
        c.use_power("m6168a1", on=victim)


@power(
    "m6168a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FEAR, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d10", 8, kind=LIMITED),
)
def m6168a3(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d10", 8, dtypes=(DamageType.COLD, DamageType.NECROTIC))
    victim = c.target
    if victim is None:
        return
    c.push(3)
    burn = c.ongoing(10, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=victim)
    if burn is None:
        return

    def spread(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim or burn not in c.world.effects.of(victim):
            return
        for near in c.within(1, of=victim, side="any"):
            if near != victim:
                c.flat(5, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=near)

    c.watch(TurnStart, spread, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} {victim}")


@power(
    "m6168a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6168a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.conceal(on=c.me, until=When.EONT)


# ==========================================================================
# m6352
# ==========================================================================


@power(
    "m6352a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6352a0(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.NECROTIC in ev.types():
            c.bonus(
                "damage", 0, dice="2d8", dtype=DamageType.NECROTIC, on=me,
                until=When.EONT, when=_melee_ctx,
            )

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m6352a0")


@power(
    "m6352a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 8, dtype=DamageType.NECROTIC),
)
def m6352a1(c: Cast) -> None:
    if c.strike():
        dice = "2d8" if c.is_(Condition.WEAKENED) else "1d8"
        c.damage(dice, 8, dtype=DamageType.NECROTIC)


@power(
    "m6352a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
)
def m6352a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m6352a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2 and _secondary(c, 13, AC, victim):
        c.weakened(until=When.EONT, on=victim)


# ==========================================================================
# m6501
# ==========================================================================


@power(
    "m6501a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE),
)
def m6501a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6501a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 7),
)
def m6501a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6501a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6501a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    victim = c.target
    if victim is None:
        return
    c.use_power("m6501a0", on=victim)
    first = c.landed
    c.use_power("m6501a1", on=victim)
    if first and c.landed:
        c.prone(on=victim)


@power(
    "m6501a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:insight",),
)
def m6501a3(c: Cast) -> None:
    """The whole printed effect is a disguise and an Insight DC to see
    through it -- no combat number moves, so there is nothing else to
    hold."""
    c.form(until=When.ENCOUNTER, label=c.ref)


_M6501_FELLED = "the m6501 bloodies an enemy or reduces an enemy to 0 hit points"


@power(
    "m6501a4",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6501_FELLED,
    on=[
        Trigger(Bloodied, about_me, "the m6501 bloodies an enemy"),
        Trigger(Dropped, about_me, "or reduces an enemy to 0 hit points"),
    ],
)
def m6501a4(c: Cast) -> None:
    me = c.me
    label = "m6501a4 round"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    c.effect(label, until=When.EOT, on=me)
    triggering = getattr(c.trigger, "actor", None)
    foe = next((f for f in c.enemies() if f != triggering), None)
    if foe is not None:
        c.basic(on=foe)


_M6501_HAZARD = "the m6501 takes acid, cold, fire, lightning, or thunder damage"
_M6501_TYPES = (
    DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
)


def _hazard_damage(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and any(t in ev.types() for t in _M6501_TYPES)


@power(
    "m6501a5",
    level=8,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6501_HAZARD,
    on=Trigger(DamageApplied, _hazard_damage, _M6501_HAZARD),
)
def m6501a5(c: Cast) -> None:
    ev = c.trigger
    dtype = next((t for t in _M6501_TYPES if t in ev.types()), None) if ev is not None else None
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m6548
# ==========================================================================


@power(
    "m6548a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 8),
)
def m6548a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6548a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 4),
)
def m6548a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6548a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6548a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    ranged = c.choose(["battleaxe", "shortbow"], f"{c.ref}: which weapon") or "battleaxe"
    ref = "m6548a1" if ranged == "shortbow" else "m6548a0"
    c.use_power(ref, on=victim)
    c.use_power(ref, on=victim)


_M6548_DEALS = "the m6548's attack deals damage"


@power(
    "m6548a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6548_DEALS,
    on=Trigger(DamageApplied, lambda w, me, ev: ev.source == me, _M6548_DEALS),
)
def m6548a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.flat(c.roll("2d8"), on=victim)


# ==========================================================================
# m6619
# ==========================================================================


@power(
    "m6619a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m6619a0(c: Cast) -> None:
    c.regeneration(5, on=c.me)


@power(
    "m6619a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 9),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m6619a1(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", 14 if c.bloodied(on=c.target) else 9)
        c.prone()


@power(
    "m6619a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 9),
    dropped=("c.contract(ref)",),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m6619a2(c: Cast) -> None:
    """The curse of lycanthropy half -- `x5_34` -- has no contraction
    mechanism to call; the hit and the bloodying both play."""
    if c.strike():
        c.hit()


@power(
    "m6619a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_shapes("hybrid"),
    requires_text="it must be in hybrid form",
)
def m6619a3(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m6619a1", on=victim)
        c.use_power("m6619a2", on=victim)


@power(
    "m6619a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m6619a4(c: Cast) -> None:
    """It alters its physical form: humanoid, hybrid, beast.

    **Written now that a shape can be read.** This was appearance only,
    and correctly so while nothing could ask which form the creature was
    in -- its own note said the gated attacks carried the gap. Those
    Requirements are gates now, so the shape is what decides which of
    this creature's attacks it may use, and the row is no longer out of
    combat.

    `humanoid` leads the list because that is what the creature is before it
    changes anything, and one form replaces another -- which is what
    "until it uses this power again" means.
    """
    _shapechange(c, "humanoid", "hybrid", "beast")
# ==========================================================================
# m876
# ==========================================================================


@power(
    "m876a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 5),
)
def m876a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m876a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d10", 5, kind=LIMITED),
)
def m876a1(c: Cast) -> None:
    if c.strike(keep="best"):
        c.hit()


# ==========================================================================
# m920
# ==========================================================================


@power(
    "m920a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m920a0(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", 6) if c.bloodied(c.me) else c.hit()


@power(
    "m920a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m920a1(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m920a0", on=victim)
        c.use_power("m920a0", on=victim)


_M920_ATTACKED = "it is attacked by an adjacent enemy while bloodied"


def _attacked_by_adjacent_enemy(world: World, me: int, ev: AttackDeclared) -> bool:
    return (
        ev.target == me
        and ev.attacker in enemies(world, me)
        and distance_between(world, me, ev.attacker) <= 1
    )


@power(
    "m920a2",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M920_ATTACKED,
    on=Trigger(AttackDeclared, _attacked_by_adjacent_enemy, _M920_ATTACKED),
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 8),
)
def m920a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.bloodied(c.me) and c.strike(on=foe):
        c.hit(on=foe)


_M920_DOWN = "it is reduced to 0 hit points"


@power(
    "m920a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    trigger=_M920_DOWN,
    on=Trigger(Dropped, about_me, _M920_DOWN),
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE, half_on_miss=True),
)
def m920a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m920a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m920a4(c: Cast) -> None:
    for foe in c.within(5, side="enemy"):
        c.penalty("attack", 2, on=foe, until=When.EONT)


_M920_BLED = "the m920 is first bloodied"


@power(
    "m920a5",
    level=8,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M920_BLED,
    on=Trigger(Bloodied, about_me, _M920_BLED),
)
def m920a5(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m920a4")
    c.use_power("m920a4")


# ==========================================================================
# m957
# ==========================================================================


@power(
    "m957a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=2),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
    requires=_not_in("beast"),
    requires_text="it must not be in beast form",
)
def m957a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m957a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
    dropped=("c.contract(ref)",),
    requires=_not_in("humanoid"),
    requires_text="it must not be in humanoid form",
)
def m957a1(c: Cast) -> None:
    """The disease contraction (`x5_34`) has no mechanism to call; the hit
    and the ongoing both play."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m957a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m957a2(c: Cast) -> None:
    c.bonus(
        "damage", 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and ctx.get("target") is not None
        and c.bloodied(on=ctx["target"]),
    )


@power(
    "m957a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m957a3(c: Cast) -> None:
    me = c.me

    def rewarded(ev: Dropped) -> None:
        if _felled_by_me(c.world, me, ev):
            c.grant_action_point(1, on=me)

    c.watch(Dropped, rewarded, until=When.ENCOUNTER, on=me, label="m957a3")


_M957_HIT_MELEE = "the m957 is hit by a melee attack"


def _hit_me_in_melee(world: World, me: int, ev: Hit) -> bool:
    from combat_engine.engine import get

    if ev.target != me:
        return False
    row = get(ev.power or "")
    return row is not None and row.reach.kind == "melee"


@power(
    "m957a4",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M957_HIT_MELEE,
    on=Trigger(Hit, _hit_me_in_melee, _M957_HIT_MELEE),
)
def m957a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m957a0", on=foe)


@power(
    "m957a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m957a5(c: Cast) -> None:
    """It alters its physical form: beast, humanoid.

    **Which attacks each shape forbids is on the attack rows**, not here. The
    card states them as a loss ("it loses its bite attack in humanoid form"),
    which is a Requirement on the bite; putting it here as a `c.forbid` would
    have to be undone by hand every time the shape changed, and was not.

    `beast` leads the list because that is the shape the block describes it
    in, and one form replaces another -- which is what "until it uses this
    power again" means.
    """
    _shapechange(c, "beast", "humanoid")
