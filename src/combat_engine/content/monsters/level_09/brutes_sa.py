"""Monster abilities, level 9, brutes.

143 rows across 39 stat blocks. `brutes.py` holds the earlier sweep of this
level and is not touched here. Eight blocks in the brief print no abilities
at all (m251, m412, m47, m4805, m487, m723, m92) and so have nothing to
decorate.

Conventions, inherited from the earlier sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a card with no printed range at all is melee 1;
* a close burst or blast naming no target set takes enemies, except where
  the card says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- the Miss branch is written by
  hand every time it is declared;
* a range band "X/Y" takes the larger number as the single `Ranged`/
  `MeleeOrRanged` value, matching the one precedent already in the tree
  (`m6492a0`'s "normal ranged 5/10" is written `MeleeOrRanged(1, 10)`);
* "Requirement: must be in <form>" is a gate now. It had no checker when
  this file was written -- there was no way to ask what shape a creature was
  in, only to put it in one -- and `combat_engine.content.monsters.forms`
  answers it: `c.form(name=)` records the shape and `_shapes`/`_not_in` read
  it back, so these rows carry a `requires=` and no marker.;
* several cards in this brief carry a flavour name where another entry's
  own ref happens to sit (a ray "launches a m1164", two trolls each
  printed as "m5798 or m5798") -- read as the spec tool's own extraction
  noise substituting a redacted name with whatever ref looked nearby, not
  as a cross-reference to another stat block, and treated as this row's
  own attack throughout.

Two rows in this brief print an Effect that summons a fresh ally the spec
never gave a ref for. Summoning it would mean going and finding the
printed name, which is the one thing never allowed -- both are
`todo=("Cast.summon(ref=)",)`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.forms import _shapes, _strictly
from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.skirmishers_sa import _aura_holds, _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import _missed_me_in_melee, _ref_of
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_05.artillery_sa import (
    _one_save_for_both,
    _shot_me_from_afar,
)
from combat_engine.content.monsters.level_07.brutes_sa import _ridden_by_seventh_level
from combat_engine.content.monsters.level_08.artillery_sa import (
    _minus_all_defences,
    _two_allies_flank,
)
from combat_engine.content.monsters.level_08.brutes import _squeezes_freely
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
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
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Health,
    Ident,
    Initiative,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Position,
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Died,
    Dropped,
    Escaped,
    ForcedMove,
    Hit,
    Miss,
    Moved,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    distance_between,
    flanked_by,
    has_combat_advantage,
    team,
)
from combat_engine.engine.query import (
    is_ as query_is,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_me, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _sturdy_footing(c: Cast) -> None:
    """The printed "moves 1 square fewer / can save against falling prone"
    racial trait, repeated whole on two blocks this wave."""
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


def _recharge_when_no_damage_dealt(c: Cast) -> None:
    """"Recharges when it ends its turn having dealt no damage to an
    enemy" -- read off its own `Hit`s rather than `DamageApplied`, since a
    hit is what the card means and what every other recharge clause in
    this file already keys from."""
    me, ref = c.me, c.ref
    dealt = {"any": False}

    def hit(ev: Hit) -> None:
        if ev.attacker == me:
            dealt["any"] = True

    def reset(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            dealt["any"] = False

    def check(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor == me and not dealt["any"]:
            c.restore_use(ref, on=me)

    c.watch(Hit, hit, until=When.ENCOUNTER, on=me, label=f"{ref} dealt")
    c.watch(TurnStart, reset, until=When.ENCOUNTER, on=me, label=f"{ref} reset")
    c.watch(TurnEnd, check, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")


def _ridden_by_ninth_level(world: World, me: int) -> bool:
    """A ninth-level copy of `_ridden_by_seventh_level` -- its own docstring
    already explains why this is a fresh function rather than a parameter
    bent to take two numbers: the question is asked live, since nobody is
    mounted when a trait of this shape arms."""
    for rider in world.relations.targets(Relation.RIDDEN_BY, me):
        if team(world, rider) is team(world, me):
            stats = world.get(rider, Stats)
            if stats is not None and stats.level >= 9:
                return True
    return False


def _rider_hit_by_ranged_oa(world: World, me: int, ev: Any) -> bool:
    """"A friendly rider of 9th level or higher is hit by an opportunity
    attack provoked by a ranged or an area attack." Both halves asked
    live: who the rider is changes over the fight, and the reach kind is
    read off the row that struck rather than guessed."""
    riders = world.relations.targets(Relation.RIDDEN_BY, me)
    target = getattr(ev, "target", None)
    if target not in riders or not getattr(ev, "opportunity", False):
        return False
    if not _ridden_by_ninth_level(world, me):
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in ("ranged", "area_burst")


def _m1515_pack_trigger(world: World, me: int, ev: Any) -> bool:
    """"An enemy attacks an ally, and this creature is within 5 squares of
    at least one other of its own kind." Both halves asked of the board at
    the trigger, since nothing here could be snapshotted and stay honest."""
    from combat_engine.engine import Ident
    from combat_engine.engine.query import creatures

    target = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if target is None or attacker is None or target == me:
        return False
    if team(world, target) is not team(world, me) or team(world, attacker) is team(world, me):
        return False
    return any(
        k != me
        and world.get(k, Ident) is not None
        and world.get(k, Ident).ref == "m1515"
        and distance_between(world, me, k) <= 5
        for k in creatures(world)
    )


def _enemy_bloodied_nearby(radius: int) -> Any:
    """"An enemy within N squares is bloodied" -- the trigger fires on the
    transition, which is what `Bloodied` already announces once for."""

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


def _targets_my_ally(ref: str) -> Any:
    """"Triggers when <this creature's warded ally> is targeted by an
    attack" -- the ally is named by its own ref, which the spec hands over
    as a stand-in for its printed name."""

    def check(world: World, me: int, ev: Any) -> bool:
        from combat_engine.engine import Ident

        target = getattr(ev, "target", None)
        if target is None or team(world, target) is not team(world, me):
            return False
        ident = world.get(target, Ident)
        return ident is not None and ident.ref == ref


    return check


def _ally_down(ref: str) -> Any:
    """"Usable when <ally> drops to 0 or fewer hit points" -- same
    stand-in-ref shape as `_targets_my_ally`, read off `Dropped` instead
    of an attack."""

    def check(world: World, me: int, ev: Any) -> bool:
        from combat_engine.engine import Ident

        actor = getattr(ev, "actor", None)
        if actor is None or team(world, actor) is not team(world, me):
            return False
        ident = world.get(actor, Ident)
        return ident is not None and ident.ref == ref

    return check


def _recharge_when_m2330_kills(c: Cast) -> None:
    """"Recharges when a <this kind> reduces an enemy to 0 hit points" --
    any ally of the same ref, not only this one, so `Dropped.source` is
    checked against the whole kin rather than against `me`."""
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def felled(ev: Dropped) -> None:
        attacker = ev.source
        if attacker is not None and _ref_of(c, attacker) == "m2330":
            c.restore_use(ref, on=me)

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, label=label)


def _adjacent_enemy_excludes_me(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy makes an attack that does not include it" --
    `among` is the whole target list of the triggering use, set at
    emission and absent from the dataclass itself."""
    attacker = getattr(ev, "attacker", None)
    if attacker is None or team(world, attacker) is team(world, me):
        return False
    if distance_between(world, me, attacker) > 1:
        return False
    among = getattr(ev, "among", ())
    return me not in among


def _forced_move_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me


def _adjacent_enemy_starts_prone(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or ev.ghost or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1 and query_is(world, who, Condition.PRONE)


def _revives_once(c: Cast, hp: int, *excluded: DamageType, delayed: bool = False) -> None:
    """A body that rises once, on the strength of what killed it.

    Immediate (`delayed=False`) is `m3533a3`'s own troll shape: it stands
    up inside the `Dropped` window. `delayed=True` waits one more beat, for
    the printed lines that say it rises on its *own next turn* instead.
    """
    me = c.me
    label = f"{c.ref} risen"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    c.effect(label, until=When.ENCOUNTER, on=me)
    c.revives_unless(*excluded, on=me)
    clean = {"ok": True}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            clean["ok"] = not any(t in ev.types() for t in excluded)

    if delayed:
        pending = {"down": False}

        def marked(ev: Dropped) -> None:
            if ev.actor == me and clean["ok"]:
                pending["down"] = True

        def rise(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor == me and pending["down"]:
                pending["down"] = False
                c.reanimate(on=me, hp=hp)

        c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
        c.watch(Dropped, marked, until=When.ENCOUNTER, on=me, label=f"{c.ref} falls")
        c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")
    else:

        def rise(ev: Dropped) -> None:
            if ev.actor == me and clean["ok"]:
                c.reanimate(on=me, hp=hp)

        c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
        c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


_M6614_AURA: dict[int, int] = {}


def _m6614_make_aura(c: Cast, radius: int) -> None:
    me = c.me
    # **"The aura is difficult terrain"**, with no side named -- so the flag
    # is laid flat and nothing is waived, unlike the three theme powers that
    # print "for enemies". `Zones.aura` not passing `difficult` on was the
    # whole gap; `triage.py` found it.
    ring = c.aura(radius, label="m6614a0 aura", until=When.ENCOUNTER, on=me,
                  difficult=True)
    _aura_holds(c, ring, lambda who: c.cannot_shift(on=who, until=When.ENCOUNTER))


def _lightning_or_thunder(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and bool({DamageType.LIGHTNING, DamageType.THUNDER} & set(ev.types()))


_M5638_RUNES: dict[int, int] = {}


# ==========================================================================
# m1004
# ==========================================================================


@power(
    "m1004a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.FORCE),
)
def m1004a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1004a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.FORCE),
)
def m1004a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.surge(on=c.me)


_M1004_MISSED = "it is missed by a melee attack from an adjacent attacker"


@power(
    "m1004a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    trigger=_M1004_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M1004_MISSED),
)
def m1004a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.no_provoke(on=c.me, until=When.EOT)
        c.use_power("m1004a1", on=foe)


# ==========================================================================
# m115776
# ==========================================================================


@power(
    "m115776a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115776a0(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=_two_allies_flank(c))


@power(
    "m115776a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d10", 5),
)
def m115776a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115776a2",
    level=9,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m115776a2(c: Cast) -> None:
    """Requirement: bloodied, asked in the body -- an active row is offered
    fresh each turn, so there is nothing for a stale `requires=` to kill."""
    if not c.bloodied(c.me):
        return
    if c.strike():
        c.hit()
        c.temp_hp(5, on=c.me)


# ==========================================================================
# m1471
# ==========================================================================


@power(
    "m1471a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(side="enemy", count=1, max_size=Size.LARGE, label="Large or smaller"),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d4", 6),
)
def m1471a0(c: Cast) -> None:
    """"It can't make other attacks while grabbing a target" needs nothing
    of its own: a creature under this engine's turn structure already
    spends one standard action a turn."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    grabbed = c.grab(on=victim)
    pinned = c.immobilized(on=victim, until=When.ENCOUNTER)
    me = c.me

    def freed(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim and ev.success and pinned is not None:
            c.world.effects.end(pinned, "the grab ends")

    c.watch(Escaped, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")
    if grabbed is not None:
        c.on_sustain(grabbed, lambda v=victim: c.flat(c.roll("4d4") + 6, on=v))


@power(
    "m1471a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m1471a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m1471a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 6, dtype=[DamageType.ACID, DamageType.NECROTIC], kind=LIMITED),
    dropped=("Cast.condition(ongoing_dtypes=)",),
)
def m1471a2(c: Cast) -> None:
    """The hit roll is one blow of two types and the ongoing burn is the
    same pair -- `Damage` and `c.condition`'s own `ongoing=` each take one
    type, so the necrotic half of both is the part left out.

    **Re-aimed from `Cast.condition(ongoing=)`**, which resolves: the
    keyword exists, so the old marker read ARRIVED the day it was written.
    What is absent is a `dtypes` form of it. `c.ongoing` already takes
    `dtypes=`, but on a second clock -- and "save ends both" is one."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.ACID))


# ==========================================================================
# m1515
# ==========================================================================


@power(
    "m1515a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 5),
)
def m1515a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1515a1",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1515a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M1515_ALLY_HIT = "an enemy attacks an ally and it is within 5 squares of another of its kind"


@power(
    "m1515a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(6),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    trigger=_M1515_ALLY_HIT,
    on=Trigger(AttackDeclared, _m1515_pack_trigger, _M1515_ALLY_HIT),
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 3, dtype=DamageType.LIGHTNING),
)
def m1515a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m1828
# ==========================================================================


@power(
    "m1828a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m1828a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1828a1",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="the target must be prone",
        conditions=frozenset({Condition.PRONE}),
    ),
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5),
)
def m1828a1(c: Cast) -> None:
    """"Cannot stand until the end of its next turn" is `Condition.PINNED` laid
    beside the prone it already has. The printed restriction is the target line,
    so nothing but a prone creature is ever offered."""
    if c.strike():
        c.hit()
        c.condition(Condition.PINNED, until=When.EONT)


_M1828_BLOODIED_NEARBY = "an enemy within 6 squares is bloodied"


@power(
    "m1828a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1828_BLOODIED_NEARBY,
    on=Trigger(Bloodied, _enemy_bloodied_nearby(6), _M1828_BLOODIED_NEARBY),
)
def m1828a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        _M1828_CHARGE_TARGET[c.me] = foe
        c.charge_at(foe, "m1828a0")


_M1828_CHARGE_TARGET: dict[int, int] = {}


@power(
    "m1828a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1828a3(c: Cast) -> None:
    """Gated on this creature's own last recorded charge target being
    bloodied -- the opportunity window carries who would swing and why,
    never who the charger is bearing down on, so that fact is kept here
    from the one row (`a2`) that ever starts a charge."""
    me = c.me

    def gate(ctx: dict[str, Any]) -> bool:
        if ctx.get("kind") != "charge":
            return False
        foe = _M1828_CHARGE_TARGET.get(me)
        return foe is not None and c.bloodied(on=foe)

    c.no_provoke(on=me, until=When.ENCOUNTER, when=gate)


@power(
    "m1828a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1828a4(c: Cast) -> None:
    flanked = _two_allies_flank(c)
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_only(ctx) and flanked(ctx),
    )


@power(
    "m1828a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:perception",),
)
def m1828a5(c: Cast) -> None:
    """The Perception bonus plays; the printed narrowing to a specific
    creature it has bitten before has no combat meaning -- nothing on a
    board rolls Perception to track by scent, so there is nowhere for
    the narrowing to go."""
    c.bonus("perception", 10, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m1873
# ==========================================================================


@power(
    "m1873a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m1873a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1873a1",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1873a1(c: Cast) -> None:
    c.shift(4)


_M1873_BLOODIED = "it is first bloodied"


def _onto_my_count(c: Cast, made: int) -> None:
    """Move a creature just summoned onto the summoner's initiative count.

    `Encounter.join` rolls the newcomer an initiative of its own and splices
    by it, so "acts on the m1873's initiative count" has to undo that: the
    slot comes out, `Initiative.rolled` is set to the summoner's, and
    `extra_turn` puts it back at that count. `_acts_after_its_creator` is the
    same splice written on the clone's side, a count lower, for the card that
    says "immediately after" instead of "on".
    """
    enc = c.world.encounter
    mine = c.world.get(c.me, Initiative)
    theirs = c.world.get(made, Initiative)
    if enc is None or mine is None or theirs is None or made not in enc.order:
        return
    was = enc.order.index(made)
    enc.order.pop(was)
    if was < enc.index:
        enc.index -= 1
    theirs.rolled = mine.rolled
    enc.extra_turn(made, mine.rolled)


@power(
    "m1873a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1873_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1873_BLOODIED),
)
def m1873a2(c: Cast) -> None:
    """It comes apart into two of itself, each with half of what the original
    had left, both acting on the original's count.

    **`c.summon(hp=)` was the wrong gap.** The verb hands back the new eid,
    and a content body may write a component directly -- which is how
    `_strips_resistance` and `_take_resistances` edit `Defences` -- so
    "hit points equal to one-half the original's current" is two writes to
    `Health.hp` and needs no parameter. `max_hp` is left where the stat block
    put it, because the card halves the hit points and not the creature.

    The shared count is the same splice `_acts_after_its_creator` does from
    the clone's side: `Encounter.join` has already rolled the newcomer an
    initiative of its own, so the slot comes back out and goes in at this
    creature's count, with `Initiative.rolled` moved to match so anything
    spliced in later sorts against a count it can see.

    "Effects applied to the original do not apply to either of the
    individuals" is read as the ones somebody *else* put there: the clone is
    born clean, and the original's are ended by source, which leaves its own
    standing holds alone. The printed refusal while at 0 hit points is the
    `hp <= 0` guard -- `Bloodied` is announced whether or not the blow that
    crossed the line also finished the creature.

    The halves recombining after five minutes out of combat has no horizon
    here: this engine has no clock between fights.
    """
    me = c.me
    health = c.world.get(me, Health)
    if health is None or health.hp <= 0:
        return
    half = max(1, health.hp // 2)
    twin = c.summon(_ref_of(c, me))
    if not twin:
        return
    health.hp = half
    theirs = c.world.get(twin, Health)
    if theirs is not None:
        theirs.hp = half
    for eff in list(c.world.effects.of(me)):
        if eff.source != me:
            c.world.effects.end(eff, f"{c.ref} split")
    _onto_my_count(c, twin)


# ==========================================================================
# m2029
# ==========================================================================


@power(
    "m2029a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m2029a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2029a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
)
def m2029a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.grab()
    me = c.me
    c.penalty(
        "escape", 5, on=victim, until=When.ENCOUNTER,
        when=lambda ctx, v=victim: v in c.grabbing(of=me),
    )


@power(
    "m2029a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=10),
)
def m2029a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.grab()
    me = c.me
    c.penalty(
        "escape", 5, on=victim, until=When.ENCOUNTER,
        when=lambda ctx, v=victim: v in c.grabbing(of=me),
    )


# ==========================================================================
# m2236
# ==========================================================================


@power(
    "m2236a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
)
def m2236a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2236a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m2236a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _one_save_for_both(c, FORT, 2, 5, DamageType.POISON)


@power(
    "m2236a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2236a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m2321
# ==========================================================================


@power(
    "m2321a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 6, kind=MINION),
)
def m2321a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2324
# ==========================================================================


@power(
    "m2324a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 5, kind=MINION),
)
def m2324a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2324_DOWN = "it is reduced to 0 hit points"


@power(
    "m2324a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    trigger=_M2324_DOWN,
    on=Trigger(Dropped, about_me, _M2324_DOWN),
    attack=Attack(vs=REF, printed=10),
    damage=Damage("", 5, dtype=DamageType.ACID, kind=MINION),
)
def m2324a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2330
# ==========================================================================


@power(
    "m2330a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m2330a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me

    def moved(ev: Moved) -> None:
        if ev.actor != victim:
            return
        c.flat(5, on=victim)

    c.watch(Moved, moved, until=When.SONT, on=me, once=True, label=f"{c.ref} {victim}")


@power(
    "m2330a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    damage=Damage("4d6", 5, kind=LIMITED),
    attack=Attack(vs=AC, printed=12),
)
def m2330a1(c: Cast) -> None:
    """Recharges whenever any creature of this kind fells an enemy, on
    top of the die every round.

    **The marker came off; the clause was never missing.** It read
    `Usage.RECHARGE(when=)`, and `Power.recharge_when` has taken a
    `Trigger` for some time -- but the helper below is the *more* faithful
    of the two here, because the card says "a <this kind>" and not "this
    creature", and a declared `Trigger(Dropped, by_me, ...)` would narrow
    it to the one that swung."""
    _recharge_when_m2330_kills(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.ongoing(5, on=victim)
    if held is not None:
        held.on_end.append(lambda v=victim: c.dazed(on=v, until=When.EONT))


_M2330_KILL = "it reduces an enemy to 0 hit points"


@power(
    "m2330a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2330_KILL,
    on=Trigger(Dropped, by_me, _M2330_KILL),
)
def m2330a2(c: Cast) -> None:
    c.temp_hp(20, on=c.me)
    c.grants_advantage(to="team", until=When.SONT)


# ==========================================================================
# m2613
# ==========================================================================


@power(
    "m2613a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 6),
)
def m2613a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2613a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2613a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m2613a0", on=victim)
    c.use_power("m2613a0", on=victim)


_M2613_BLOODIED = "its attack bloodies an enemy"


@power(
    "m2613a2",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2613_BLOODIED,
    on=Trigger(Bloodied, by_me, _M2613_BLOODIED),
)
def m2613a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m2613a0", on=foe)


@power(
    "m2613a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m2613a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m2613a4",
    level=9,
    uses=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def m2613a4(c: Cast) -> None:
    c.summon("m2612", at=c.here)


def _flanks_with(c: Cast, me: int) -> Any:
    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and _melee_only(ctx) and flanked_by(c.world, who, me)

    return gate


@power(
    "m2613a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2613a5(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_flanks_with(c, c.me))


@power(
    "m2613a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2613a6(c: Cast) -> None:
    """Rises on its own next turn rather than inside the `Dropped` window
    itself -- the troll shape, timed to a turn boundary instead."""
    _revives_once(c, 10, DamageType.ACID, DamageType.FIRE, delayed=True)


# ==========================================================================
# m3336
# ==========================================================================


@power(
    "m3336a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m3336a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3336a1",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 5, dtype=DamageType.LIGHTNING),
)
def m3336a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3608
# ==========================================================================


@power(
    "m3608a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 6),
)
def m3608a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3608a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d10", 6),
)
def m3608a1(c: Cast) -> None:
    """"Requires combat advantage against the target" is asked of the
    board before the swing, not read off the attack roll -- that is too
    late, since the one-shot kind is already spent by the time `Hit`
    announces it. "Usable only while wielding a rapier" is equipment,
    which a monster carries none of, and is not gated."""
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


_M3608_HIT = "it is hit by a melee attack"


@power(
    "m3608a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3608_HIT,
    on=Trigger(Hit, both(targets_me, by_melee), _M3608_HIT),
)
def m3608a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


@power(
    "m3608a3",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3608a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m3768
# ==========================================================================


@power(
    "m3768a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m3768a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    vpos = c.world.get(victim, Position)
    if vpos is not None:
        c.shift(1, to=vpos.square, share=True)


# ==========================================================================
# m3786
# ==========================================================================


@power(
    "m3786a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 9),
)
def m3786a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "4d4", 17)


_M3786_GUARD = "an enemy targets its warded ally with an attack"


@power(
    "m3786a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M3786_GUARD,
    on=Trigger(AttackDeclared, _targets_my_ally("m3787"), _M3786_GUARD),
)
def m3786a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.charge_at(foe, "m3786a0")
    if c.landed:
        c.flat(c.roll("1d10"))
        c.mark(on=foe, until=When.EONT)


_M3786_ALLY_DOWN = "its warded ally drops to 0 or fewer hit points"


@power(
    "m3786a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3786_ALLY_DOWN,
    on=Trigger(Dropped, _ally_down("m3787"), _M3786_ALLY_DOWN),
)
def m3786a2(c: Cast) -> None:
    me = c.me
    c.bonus("attack", 2, on=me, until=When.ENCOUNTER)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER)
    for which in ALL_DEFENCES:
        c.penalty(which, 2, on=me, until=When.ENCOUNTER)
    c.vulnerable(5, None, on=me, until=When.ENCOUNTER)


@power(
    "m3786a3",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m3786a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m3786a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m3786a4(c: Cast) -> None:
    """Growing Large, the longer reach and the +5 damage bonus all play.

    **The reach half wanted a modifier, not a second header field.** This
    was marked `Power.reach_alt`, and `Range.alt` is a *branch* -- the half
    of "Melee or Ranged" a chooser picks -- so it could never have carried a
    state-gated number. `dsl._stretched` reads a `"reach"` modifier inside
    `_reach_of`, which is the same arithmetic `c.reach` and the targeting
    both go through, so one square laid here is one square further this row
    may be aimed. Gated on the size rather than evaluated once, for
    `m3786a5`'s reason: the creature reverts as a free action and a gate
    taken at growth time would be wrong for the rest of the fight.

    The printed push of whoever stood in the three new squares is
    `c.resize`'s own: its docstring says the push is the consequence of
    growing rather than a separate line, so it happens there and this
    body must not do it twice. `m3783a3` is the same card at level 7 and
    says so.

    Reverting "as a free action" is `c.endable`, as `m3783a3` has it. Both
    modifiers are gated on the size rather than on the hold, so they lift
    themselves when the revert comes and nothing has to be unwound."""
    me = c.me

    def grown(_ctx: Any) -> bool:
        return c.size_of(me) is Size.LARGE

    held = c.resize(Size.LARGE, on=me, until=When.ENCOUNTER)
    if held is None:
        return
    c.bonus("reach", 1, on=me, until=When.ENCOUNTER, when=grown)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=_melee_only)
    c.endable(held, cost=ActionType.FREE)


@power(
    "m3786a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3786a5(c: Cast) -> None:
    """"( usable when large-sized ) ... opportunity attacks against all enemies
    within his reach (2 squares)."

    **The size clause is a condition on the ability, not flavour**, and this
    went in bare -- so the creature held a two-square threat zone from the
    start of the encounter, which its card grants only while grown.
    `m3786a4` beside it is what lays `Size.LARGE`, and `c.threatens(when=)`
    carries the gate onto both modifiers. #425.

    Read at the moment the zone is consulted rather than at the moment it is
    laid, which is the whole point: the creature grows and shrinks within one
    encounter and a gate evaluated once would be wrong for half of it.
    """
    me = c.me
    c.threatens(
        2, on=me, until=When.ENCOUNTER,
        when=lambda _ctx: c.size_of(me) is Size.LARGE,
    )


# ==========================================================================
# m4123
# ==========================================================================


@power(
    "m4123a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 10, dtype=DamageType.ACID, kind=MINION),
)
def m4123a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4205
# ==========================================================================


@power(
    "m4205a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m4205a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m4205a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m4205a1(c: Cast) -> None:
    """While it is holding a grab, this is the only attack the printed
    card lets it make, and `a0` never says the same, so the restriction is
    redirected here -- the held target, not whoever the chooser offers."""
    held = c.grabbing()
    victim = c.target
    if held and victim not in held:
        victim = next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)


@power(
    "m4205a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m4205a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m4205a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.prone(on=victim)


_M4205A3_HIT = "it takes damage"


@power(
    "m4205a3",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.THUNDER],
    trigger=_M4205A3_HIT,
    on=Trigger(DamageApplied, targets_me, _M4205A3_HIT),
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d8", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4205a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mods = [
        (victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref)),
        (victim, Mod(what="save", value=-2, kind="untyped", label=c.ref)),
    ]
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, mods=mods, ongoing=(5, DamageType.NECROTIC)
    )


@power(
    "m4205a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4205a4(c: Cast) -> None:
    def affected(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and any(
            eff.ongoing and eff.ongoing[1] is DamageType.NECROTIC
            for eff in c.world.effects.of(who)
        )

    c.ignore_cover(on=c.me, until=When.ENCOUNTER, when=affected)


@power(
    "m4205a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4205a5(c: Cast) -> None:
    me = c.me
    given: set[int] = set()

    def check(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        rider = c.rider()
        if rider is None or rider in given or not _ridden_by_seventh_level(c.world, me):
            return
        given.add(rider)
        c.resist(10, DamageType.NECROTIC, on=rider, until=When.ENCOUNTER)
        c.bonus(
            "save", 4, on=rider, until=When.ENCOUNTER,
            when=lambda ctx: Keyword.FEAR in ctx.get("keywords", ()),
        )

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} rider")


# ==========================================================================
# m4397
# ==========================================================================


@power(
    "m4397a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m4397a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.flat(c.roll("1d8") + 2, dtype=DamageType.ACID)
    victim = c.target
    if victim is not None and (
        c.is_(Condition.IMMOBILIZED, on=victim) or c.is_(Condition.PRONE, on=victim)
    ):
        c.flat(c.roll("1d8"))


@power(
    "m4397a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 5),
)
def m4397a1(c: Cast) -> None:
    """While it has a target grabbed, this is the only attack the card
    lets it make against anyone else -- redirected to the held creature
    rather than refused."""
    held = c.grabbing()
    victim = c.target
    if held and victim not in held:
        victim = next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.ongoing(5, on=victim)


@power(
    "m4397a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m4397a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    mode = c.choose(["bite+claw", "claw+claw"], f"{c.ref}: attack mode") or "bite+claw"
    if mode == "bite+claw":
        c.use_power("m4397a0", on=victim)
        c.use_power("m4397a1", on=victim)
    else:
        c.use_power("m4397a1", on=victim)
        c.use_power("m4397a1", on=victim)


@power(
    "m4397a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m4397a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m4397a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.prone(on=victim)
        c.grab(on=victim)


@power(
    "m4397a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4397a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


# ==========================================================================
# m4449
# ==========================================================================


@power(
    "m4449a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 4),
)
def m4449a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4449a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 7, dtype=DamageType.THUNDER),
)
def m4449a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)
        c.push(2)


@power(
    "m4449a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=UpTo(2),
)
def m4449a2(c: Cast) -> None:
    """Each half against a different enemy, which `UpTo(2)` offers and
    the body enforces by sending the two swings at the two chosen
    targets rather than both at one."""
    targets = c.targets[:2]
    if len(targets) < 2:
        return
    c.use_power("m4449a0", on=targets[0])
    c.use_power("m4449a1", on=targets[1])


_M4449_EXCLUDED = "an adjacent enemy attacks without including it"


@power(
    "m4449a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4449_EXCLUDED,
    on=Trigger(AttackDeclared, _adjacent_enemy_excludes_me, _M4449_EXCLUDED),
)
def m4449a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m4449a1", on=foe)


@power(
    "m4449a4",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4449a4(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "m4449a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4449a5(c: Cast) -> None:
    _sturdy_footing(c)


# ==========================================================================
# m4487
# ==========================================================================


@power(
    "m4487a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m4487a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.bonus("attack", 2, on=c.me, until=When.EONT)
        c.bonus("damage", 2, on=c.me, until=When.EONT)


_M4487_HIT = "it hits with an attack"


@power(
    "m4487a1",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4487_HIT,
    on=Trigger(Hit, by_me, _M4487_HIT),
)
def m4487a1(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.flat(5, on=c.me)
    c.flat(c.roll("3d6"), on=victim)


# ==========================================================================
# m5425
# ==========================================================================


@power(
    "m5425a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 6),
)
def m5425a0(c: Cast) -> None:
    held = c.grabbing()
    victim = c.target
    if held and victim not in held:
        victim = next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    if c.is_(Condition.PRONE, on=victim):
        c.flat(c.roll("1d8"), on=victim)
        c.grab(on=victim)
        pinned = c.condition(Condition.PINNED, until=When.ENCOUNTER, on=victim)
        me = c.me

        def freed(ev: Escaped) -> None:
            if ev.holder == me and ev.actor == victim and ev.success and pinned is not None:
                c.world.effects.end(pinned, "the grab ends")

        c.watch(Escaped, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


@power(
    "m5425a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=3,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m5425a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


_M5425_RIDER_HIT = (
    "a friendly rider of 9th level or higher is hit by an opportunity attack "
    "from a ranged or an area attack"
)


@power(
    "m5425a2",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5425_RIDER_HIT,
    on=Trigger(Hit, _rider_hit_by_ranged_oa, _M5425_RIDER_HIT),
)
def m5425a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m5425a1", on=foe)


# ==========================================================================
# m5468
# ==========================================================================


@power(
    "m5468a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5468a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def bloodied(ev: Bloodied) -> None:
        mate = ev.actor
        if mate == me or mate not in c.world.zones.occupants(ring):
            return
        foe = min(c.enemies(), key=lambda f: distance_between(c.world, mate, f), default=None)
        if foe is not None:
            c.basic(on=foe, who=mate)

    c.watch(Bloodied, bloodied, until=When.ENCOUNTER, on=me, label=f"{c.ref} rally")


@power(
    "m5468a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("4d6", 7),
)
def m5468a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M5468_BLOODIED = "it is first bloodied"


@power(
    "m5468a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    trigger=_M5468_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5468_BLOODIED),
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d6", 7, kind=LIMITED),
)
def m5468a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


_M5468_START = "it starts its turn"


@power(
    "m5468a3",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5468_START,
    on=Trigger(TurnStart, about_me, _M5468_START),
)
def m5468a3(c: Cast) -> None:
    me = c.me
    for cond in (Condition.DAZED, Condition.SLOWED, Condition.STUNNED, Condition.WEAKENED):
        if c.is_(cond, on=me):
            c.cure(cond, on=me)
            return
    for eff in c.world.effects.of(me):
        if eff.ongoing:
            c.world.effects.end(eff, "m5468a3")
            return


# ==========================================================================
# m5616
# ==========================================================================


@power(
    "m5616a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 7, kind=MINION),
)
def m5616a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5619
# ==========================================================================


@power(
    "m5619a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5619a0(c: Cast) -> None:
    _sturdy_footing(c)


@power(
    "m5619a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 10),
)
def m5619a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5619a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5),
)
def m5619a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    choice = c.choose(["push", "prone"], f"{c.ref}: push or knock prone") or "push"
    if choice == "push":
        c.push(1)
    else:
        c.prone()


_M5619_FORCED = "it is hit by an attack that pulls, pushes, or slides it"


@power(
    "m5619a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M5619_FORCED,
    on=Trigger(ForcedMove, _forced_move_on_me, _M5619_FORCED),
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 15),
)
def m5619a3(c: Cast) -> None:
    """"Gains a +5 bonus to the damage roll" is folded into this use's own
    damage line rather than a standing bonus -- the card means this one
    swing."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m5625
# ==========================================================================


@power(
    "m5625a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5625a0(c: Cast) -> None:
    """Already true without a line of code: a creature's own square is
    not enterable by anything else on this board, no `c.shares_space` and
    no exception involved."""


@power(
    "m5625a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 10),
)
def m5625a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5625a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5625a2(c: Cast) -> None:
    """An already-present minion ally, not one this row creates.

    **Re-aimed off `Cast.destroy(creature=)`, which was looking at the
    wrong verb.** `c.destroy` does only remove equipment, and the old
    docstring was right about that -- but `c.kill(on=)` is the one that
    takes a creature off the board, so the printed "it is destroyed" was
    sayable all along and the clause is no longer dropped. Killed before
    the 15 damage lands, which is the printed order."""
    minion = next(
        (a for a in c.allies() if c.is_minion(on=a) and c.is_kind("modron", on=a)), None
    )
    if minion is None:
        return
    foe = next(iter(c.enemies()), None)
    if foe is None:
        return
    c.slide(5, on=minion, anchor=foe)
    if not c.adjacent_to(minion, foe):
        return
    c.kill(on=minion)
    c.flat(15, on=foe)


@power(
    "m5625a3",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5625a3(c: Cast) -> None:
    me = c.me
    c.cure(Condition.SLOWED, Condition.IMMOBILIZED, on=me)
    c.ignores_difficult(on=me, until=When.EOT)
    c.shift(5)


_M5625_DOWN = "it drops to 0 hit points"


@power(
    "m5625a4",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5625_DOWN,
    on=Trigger(Dropped, about_me, _M5625_DOWN),
)
def m5625a4(c: Cast) -> None:
    """Four of its lesser kin stand up where it fell, on its own count.

    **The marker was wrong about the spec.** It said the printed name had
    been stripped and left nothing to summon; the card names the arrival by
    **ref**, which is exactly what `c.summon` takes, so nothing had to be
    read to write this.

    `at=None` lets `c.summon` take a free adjacent square, which is the
    printed "in unoccupied squares adjacent to it". The other half of that
    placement line -- "in its space" -- is unreachable rather than dropped: a
    creature at 0 hit points still occupies its square here, so the space is
    never unoccupied, and only as many appear as there is room for. Team
    follows the summoner's, which is the only reading of allies arriving.

    "Act on the m5625's initiative" is the splice `_onto_my_count` does.
    "Worth no experience points" has no combat meaning and nothing to hold
    it: there is no experience in this engine.
    """
    for _ in range(4):
        made = c.summon("m5623")
        if not made:
            break
        _onto_my_count(c, made)


# ==========================================================================
# m5638
# ==========================================================================


@power(
    "m5638a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5638a0(c: Cast) -> None:
    me = c.me
    _M5638_RUNES[me] = 1

    def extra(ev: Hit) -> None:
        if ev.attacker != me:
            return
        n = _M5638_RUNES.get(me, 1) - 1
        if n > 0:
            c.flat(c.roll(f"{n}d12"), on=ev.target)

    c.watch(Hit, extra, until=When.ENCOUNTER, on=me, label=f"{c.ref} runes")


@power(
    "m5638a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 8),
)
def m5638a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and any(c.adjacent_to(victim, a) for a in c.allies()):
        c.prone()


_M5638_DOWN = "it drops to 0 hit points"


@power(
    "m5638a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5638_DOWN,
    on=Trigger(Dropped, about_me, _M5638_DOWN),
)
def m5638a2(c: Cast) -> None:
    me = c.me
    for mate in c.allies():
        if mate in _M5638_RUNES and distance_between(c.world, me, mate) <= 5:
            _M5638_RUNES[mate] += 1


# ==========================================================================
# m5667
# ==========================================================================


@power(
    "m5667a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5667a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(ev: TurnEnd) -> None:
        if (
            not ev.ghost
            and ev.actor in c.world.zones.occupants(ring)
            and team(c.world, ev.actor) is not team(c.world, me)
        ):
            c.flat(4, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura toll")


@power(
    "m5667a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5667a1(c: Cast) -> None:
    me = c.me
    c.shares_space(on=me, until=When.ENCOUNTER, difficult=True)

    def guard(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("power") or ""))
        return row is not None and row.reach.kind in ("melee", "ranged")

    c.resist_forced(99, on=me, until=When.ENCOUNTER, when=guard)


@power(
    "m5667a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 4),
)
def m5667a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5667a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 8, kind=LIMITED, half_on_miss=True),
)
def m5667a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5667a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 5, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5667a4(c: Cast) -> None:
    """Recharges early the first time it is bloodied, on top of the die
    every round."""
    _recharge_when_bloodied(c)
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


# ==========================================================================
# m5734
# ==========================================================================


@power(
    "m5734a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5734a0(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=me, label=f"{c.ref} tally")
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") not in acted,
    )


@power(
    "m5734a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5734a1(c: Cast) -> None:
    me = c.me

    def missed(ev: Miss) -> None:
        if ev.target != me or not by_melee(c.world, me, ev):
            return
        foe = ev.attacker
        c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, until=When.EONT, on=me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} riposte")


@power(
    "m5734a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 10),
)
def m5734a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5734a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 10),
)
def m5734a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.dazed(until=When.SAVE_ENDS)


@power(
    "m5734a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5734a4(c: Cast) -> None:
    _recharge_when_no_damage_dealt(c)
    victim = c.target
    if victim is None:
        return
    c.use_power("m5734a2", on=victim)
    first_hit = c.landed
    c.use_power("m5734a3", on=victim)
    if first_hit and c.landed:
        c.dazed(on=victim, until=When.EONT)


@power(
    "m5734a5",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=12),
)
def m5734a5(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None:
            _minus_all_defences(c, victim, 2)


# ==========================================================================
# m5798
# ==========================================================================


@power(
    "m5798a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5798a0(c: Cast) -> None:
    """Falls unconscious instead of dying to anything but acid or fire,
    and rises on its own next turn with 30 hit points -- the troll shape,
    timed to a turn boundary. Both remaining clauses play as well.

    `c.revives_unless` was never where the reach was missing: it writes
    `Undying` for the policy to read and implements none of the rising.
    The rising is `_revives_once`'s own three watchers, and every one of
    them is laid with a label opening on this row's ref -- so "he does not
    return to life in this way" and "the other loses this trait" are the
    same operation, ending those holds, and the clock they were given
    never comes round.

    The twin is findable because the two brothers share one stat block:
    the other creature on the board whose `Ident.ref` is this one's, which
    is how `m3997a1`'s block asks the same question. `Died` is the
    moment -- not `Dropped`, which is what this trait exists to stop
    being fatal."""
    me = c.me
    kind = _ref_of(c, me)
    _revives_once(c, 30, DamageType.ACID, DamageType.FIRE, delayed=True)

    def brother() -> int | None:
        if not kind:
            return None
        for other, ident in c.world.each(Ident):
            if other != me and ident.ref == kind:
                return other
        return None

    def lose_the_trait(why: str) -> None:
        from combat_engine.engine.components import Undying

        for held in list(c.world.effects.of(me)):
            if held.label.startswith(c.ref):
                c.world.effects.end(held, why)
        # `c.revives_unless` writes a **component**, not an effect, so the
        # sweep above cannot reach it -- and leaving it would tell the
        # policy a body on the floor is still going to stand up.
        c.world.drop(me, Undying)

    def burned_while_down(ev: DamageApplied) -> None:
        if ev.target != me or not c.is_(Condition.UNCONSCIOUS, on=me):
            return
        if not {DamageType.ACID, DamageType.FIRE} & set(ev.types()):
            return
        twin = brother()
        if twin is not None and distance_between(c.world, me, twin) <= 5:
            lose_the_trait("burned while down, within 5 of its brother")

    def brother_died(ev: Died) -> None:
        if ev.actor == me or not kind:
            return
        ident = c.world.get(ev.actor, Ident)
        if ident is not None and ident.ref == kind:
            lose_the_trait("its brother is dead")

    c.watch(
        DamageApplied, burned_while_down, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} burned down",
    )
    c.watch(Died, brother_died, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} twin died")


@power(
    "m5798a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5798a1(c: Cast) -> None:
    """Regeneration, suspended for the turn after acid or fire damage.

    **`c.regeneration` already took the hook, under another name.** The
    marker said `suspended_by=`; the parameter is `unless=`, a callable
    asked each time the heal would pay, which is exactly the right moment
    -- the window is "his next turn", so a flag set at the moment of the
    damage would have to be cleared by something, and asking instead
    needs nothing to clear.

    The flag is **consumed** by the one tick it suppresses rather than
    cleared on a clock. `unless` is asked from inside the `TurnStart`
    tick, so a second watch counting turns would race it; consuming says
    "the next tick, whenever it comes" with nothing to order.

    **That shape is the verb's now**, and this row is one line because of
    it. `unless_damaged_by=` carries the same consumed flag that
    `unless_struck_by=` feeds, which is the point: four spellings had
    grown for one idea -- a damage type here, a weapon's material on the
    silvered rows, `suspended_by=`, `suppressed_by=`, `when=` -- and the
    mechanism under all of them is this one. `ev.types()` rather than
    `ev.dtype`, or "acid **or** fire" reads only the first type of a blow
    that is both (#420)."""
    c.regeneration(
        10, on=c.me, until=When.ENCOUNTER,
        unless_damaged_by=(DamageType.ACID, DamageType.FIRE),
    )


@power(
    "m5798a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 12),
)
def m5798a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5798a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 7),
)
def m5798a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


# ==========================================================================
# m5913
# ==========================================================================


@power(
    "m5913a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 10, kind=MINION),
    requires=_shapes("humanoid"),
    requires_text="it must be in humanoid form",
)
def m5913a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5913a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 15, dtype=DamageType.FIRE, kind=MINION, half_on_miss=True),
    requires=_strictly("transformed"),
    requires_text="it must have transformed",
)
def m5913a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M5913_DIES = "it dies"


@power(
    "m5913a2",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    trigger=_M5913_DIES,
    on=Trigger(Dropped, about_me, _M5913_DIES),
)
def m5913a2(c: Cast) -> None:
    """A minion's `Dropped` is always both dying and dead at once, so
    this fires on the hit that would otherwise remove it."""
    me = c.me
    c.revives_unless(on=me)
    c.form(label=f"{c.ref} form", until=When.ENCOUNTER, revert=None,
           name="transformed")
    c.reanimate(on=me, hp=1)


# ==========================================================================
# m6013
# ==========================================================================


@power(
    "m6013a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6013a0(c: Cast) -> None:
    """Only matters outside a fight, which this board never simulates."""


@power(
    "m6013a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 8, dtype=DamageType.NECROTIC),
)
def m6013a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6013a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 8),
)
def m6013a2(c: Cast) -> None:
    if c.grabbing():
        return
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 12, FORT, victim):
        c.grab(on=victim)
        burn = c.ongoing(10, DamageType.NECROTIC, on=victim, until=When.ENCOUNTER)
        me = c.me

        def freed(ev: Escaped) -> None:
            if ev.holder == me and ev.actor == victim and ev.success and burn is not None:
                c.world.effects.end(burn, "the grab ends")

        c.watch(Escaped, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


# ==========================================================================
# m6145
# ==========================================================================


@power(
    "m6145a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 10, kind=MINION),
)
def m6145a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    extra = sum(1 for a in c.allies() if c.adjacent_to(a, c.me) and c.adjacent_to(a, victim))
    if extra:
        c.flat(extra)


# ==========================================================================
# m6174
# ==========================================================================


@power(
    "m6174a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d10", 5),
)
def m6174a0(c: Cast) -> None:
    held = c.grabbing()
    victim = c.target
    if held and victim not in held:
        victim = next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    if c.is_(Condition.PRONE, on=victim):
        c.damage("3d10", 10, on=victim)
    else:
        c.hit(on=victim)
    c.grab(on=victim)


@power(
    "m6174a1",
    level=9,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=12),
)
def m6174a1(c: Cast) -> None:
    if c.strike():
        c.prone()
    else:
        c.escape(auto=True)


# ==========================================================================
# m6281
# ==========================================================================


@power(
    "m6281a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6281a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m6281a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6281a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6281a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("4d6", 8),
)
def m6281a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6281a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 4),
)
def m6281a3(c: Cast) -> None:
    """The one printed recharge in #489's ten that genuinely is a **moment**
    -- "ends its turn having dealt no damage" happens at a turn boundary and
    needs a per-turn tally, so it stays a watch rather than becoming a
    `recharge_while=` predicate. The marker was stale: the clause was already
    written and the symbol named a gap this row does not have."""
    _recharge_when_no_damage_dealt(c)
    if c.strike():
        c.hit()
        c.ongoing(5)


def _hit_with_my_maul(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "power", None) == "m6281a2"


_M6281_MAUL_HIT = "it hits with its main weapon during its turn"


@power(
    "m6281a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6281_MAUL_HIT,
    on=Trigger(Hit, _hit_with_my_maul, _M6281_MAUL_HIT),
)
def m6281a4(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.push(4, on=victim)
        c.prone(on=victim)


_M6281_RANGED_HIT = "an enemy within 5 squares hits it with a ranged or an area attack"


@power(
    "m6281a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6281_RANGED_HIT,
    on=Trigger(Hit, _shot_me_from_afar(5), _M6281_RANGED_HIT),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6281a5(c: Cast) -> None:
    _recharge_when_bloodied(c)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.charge_at(foe, "m6281a2")


# ==========================================================================
# m6448
# ==========================================================================


@power(
    "m6448a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6448a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def spared(ev: Dropped) -> None:
        mate = ev.actor
        if mate == me or mate not in c.world.zones.occupants(ring):
            return
        c.immune(Condition.UNCONSCIOUS, Condition.DYING, until=When.EONT, on=mate)

    c.watch(Dropped, spared, until=When.ENCOUNTER, on=me, label=f"{c.ref} grace")


@power(
    "m6448a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 9),
)
def m6448a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6448a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 6),
)
def m6448a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.pull(1)


@power(
    "m6448a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6448a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    choice = c.choose(["m6448a1", "m6448a2"], f"{c.ref}: which weapon") or "m6448a1"
    c.use_power(choice, on=victim)
    c.use_power(choice, on=victim)


_M6448_PRONE_START = "an enemy adjacent to it starts its turn prone"


@power(
    "m6448a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6448_PRONE_START,
    on=Trigger(TurnStart, _adjacent_enemy_starts_prone, _M6448_PRONE_START),
)
def m6448a4(c: Cast) -> None:
    """"But it cannot slide or pull the target with this attack" needs no
    argument on `c.use_power`.

    `c.push`, `c.pull` and `c.slide` all hand `movement.forced` the
    shoving row's own ref, which stamps it onto the `ForcedMove` -- and
    that event is a `Decision`, which is how `c.immovable` refuses a shove
    at all. So the ban is a refusal standing only for the length of this
    one borrowed use, narrowed by the borrowed row's ref and by the
    triggering enemy.

    **Push is deliberately left alone**: the card names slide and pull,
    and the two rows this borrows from do one each -- `a1` slides, `a2`
    pulls -- so a blanket refusal would be a stronger line than printed
    and the narrowing is what makes it worth writing."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    choice = c.choose(["m6448a1", "m6448a2"], f"{c.ref}: which weapon") or "m6448a1"

    def refuse(ev: ForcedMove) -> None:
        if (
            ev.target == foe
            and ev.power == choice
            and ev.how.value in ("pull", "slide")
        ):
            ev.cancel(f"{c.ref} cannot slide or pull with this attack")

    hold = c.watch(
        ForcedMove, refuse, until=When.ENCOUNTER, window=Window.BEFORE,
        on=c.me, label=f"{c.ref} no shove",
    )
    try:
        c.use_power(choice, on=foe)
    finally:
        c.world.effects.end(hold, "the borrowed attack is over")


# ==========================================================================
# m6614
# ==========================================================================


@power(
    "m6614a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6614a0(c: Cast) -> None:
    """The cannot-shift half plays, laid and lifted as the aura's own
    membership changes. The terrain half has nowhere to live -- `c.zone`
    takes `difficult=` and an aura does not, so there is no difficult
    ground to go with it."""
    _M6614_AURA[c.me] = 1
    _m6614_make_aura(c, 1)


@power(
    "m6614a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 9, dtype=DamageType.LIGHTNING),
)
def m6614a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)


@power(
    "m6614a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 9),
)
def m6614a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6614a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6614a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    choice = c.choose(["bite+claw", "claw+claw"], f"{c.ref}: attack mode") or "bite+claw"
    if choice == "bite+claw":
        c.use_power("m6614a1", on=victim)
        c.use_power("m6614a2", on=victim)
    else:
        c.use_power("m6614a2", on=victim)
        c.use_power("m6614a2", on=victim)


@power(
    "m6614a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6614a4(c: Cast) -> None:
    me = c.me
    current = _M6614_AURA.get(me, 1)
    if current < 5:

        def tick(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor == me and _M6614_AURA.get(me, 1) < 5:
                c.restore_use(c.ref, on=me)

        c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} recharge")
    if current >= 5:
        return
    grown = current + 2
    _M6614_AURA[me] = grown
    _m6614_make_aura(c, grown)


@power(
    "m6614a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 8, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m6614a5(c: Cast) -> None:
    me = c.me

    def tick(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me and _M6614_AURA.get(me, 1) >= 5:
            c.restore_use(c.ref, on=me)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} recharge")
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)
        c.slide(2)
    if c.first:
        _M6614_AURA[me] = 1
        _m6614_make_aura(c, 1)


_M6614_ELEMENTAL_HIT = "it takes lightning or thunder damage"


@power(
    "m6614a6",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    trigger=_M6614_ELEMENTAL_HIT,
    on=Trigger(DamageApplied, _lightning_or_thunder, _M6614_ELEMENTAL_HIT),
)
def m6614a6(c: Cast) -> None:
    kind = DamageType.LIGHTNING if DamageType.LIGHTNING in c.trigger.types() else DamageType.THUNDER
    for foe in c.enemies():
        if c.in_my_aura(foe):
            c.flat(5, dtype=kind, on=foe)
            c.grants_advantage(on=foe, to="team", until=When.EONT)


# ==========================================================================
# m6645
# ==========================================================================


@power(
    "m6645a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 10, kind=MINION),
)
def m6645a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m6663
# ==========================================================================


@power(
    "m6663a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6663a0(c: Cast) -> None:
    me = c.me
    given: set[int] = set()

    def check(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        rider = c.rider()
        if rider is None or rider in given:
            return
        given.add(rider)

        def gate(ctx: dict[str, Any]) -> bool:
            who = ctx.get("target")
            return who is not None and not any(
                a != me and c.adjacent_to(a, who) for a in c.allies()
            )

        c.gains_advantage(gate, until=When.ENCOUNTER, on=rider)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} escort")


@power(
    "m6663a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 10),
)
def m6663a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6663a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 15),
)
def m6663a2(c: Cast) -> None:
    victim = c.target
    before = c.bloodied(on=victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        if before or c.bloodied(on=victim):
            c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m6685
# ==========================================================================


@power(
    "m6685a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6685a0(c: Cast) -> None:
    me = c.me
    c.shares_space(on=me, until=When.ENCOUNTER, difficult=True)
    _squeezes_freely(c)

    def guard(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("power") or ""))
        return row is not None and row.reach.kind in ("melee", "ranged")

    c.resist_forced(99, on=me, until=When.ENCOUNTER, when=guard)


@power(
    "m6685a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6685a1(c: Cast) -> None:
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.ghost:
            return
        who = ev.actor
        if who == me:
            return
        mypos = c.world.get(me, Position)
        theirpos = c.world.get(who, Position)
        if mypos is None or theirpos is None or mypos.square != theirpos.square:
            return
        if c.is_(Condition.PRONE, on=who):
            c.flat(5, on=who)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} squash")


@power(
    "m6685a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 9),
)
def m6685a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6685a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 9, kind=LIMITED),
)
def m6685a3(c: Cast) -> None:
    c.jump(c.speed_of())
    for foe in c.in_squares({c.here}, side="enemy"):
        if c.strike(on=foe):
            c.hit(on=foe)
            c.prone(on=foe)
