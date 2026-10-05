"""Monster abilities, level 4, lurkers.

Twenty blocks, eighty rows. Four of the twenty print nothing the database has
filed, so they appear here only as a heading-free absence; the rest are written
to the conventions the level-1 to level-3 sweeps settled:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=9)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold it
  for the rest of the fight. A trait's `requires=` is never consulted, so a
  printed Requirement is asked again in the body;
* a recharge or encounter attack says `kind=LIMITED`, and a printed
  "Miss: Half damage" is `half_on_miss=True` rather than a second branch;
* a printed range of "15/30" takes the **normal** number;
* a row that recharges on a printed condition keeps the die in the header,
  because that is what `actions.recharge` rolls and what the card shows, and
  arms the condition on top of it;
* "Aftereffect" is the hold's `on_end` and "Each Failed Saving Throw" is
  `escalate=`; neither is a gap;
* a target line narrowed by what a creature *is* or cannot *see* has nowhere
  to live -- `Target` filters on side, count and size -- so `label=` records
  it for the card, the body redirects to a creature in reach that qualifies
  rather than returning, a `requires=` keeps the row from being offered when
  none does, and the gap is `Target.creature_kind` for the type word and
  `Target.relation` for what the creature can see of the attacker (#361).

This role is mostly one printed sentence in six variants -- "becomes invisible
until it attacks" -- and the variants are not interchangeable: three say *until
the end of its next turn*, two say *or until it is hit*, one says *until
immediately after* it swings. `_vanish_until_it_swings` covers the common half
and `_vanish_until_struck` is the one of them that also ends on being hit.

Nineteen helpers are imported rather than rewritten.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.skirmishers_sa import (
    _adjacent_foes,
    _mobile_attack,
    _moved_far,
)
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _edge_damage,
    _reach_kind,
    _recharge_when_using,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import _blinding_cloud
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.brutes_sa import _recharge_and_fire
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _vanish_until_it_swings,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _reachable,
    _while_bloodied,
)
from combat_engine.content.monsters.level_04.brutes import _has_hold, _holding
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    AreaBurst,
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
    Size,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Dropped,
    Hit,
    Miss,
    Moved,
    MoveStart,
    PowerUsed,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import has_combat_advantage, hidden_from, team
from combat_engine.engine.triggers import Trigger, about_me, hits_me, targets_me
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _vanish_until_struck(c: Cast) -> None:
    """Unseen until it attacks **or** until an attack lands on it.

    `_vanish_until_it_swings` next door is the commoner half of this sentence
    and ends only on the swing. The second clause wants a watch of its own, and
    both are torn down with the veil so a later vanishing does not inherit the
    listeners of an earlier one.
    """
    me = c.me
    veil = c.invisible(on=me, until=When.ENCOUNTER)
    if veil is None:
        return

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.world.effects.end(veil, "it was hit")

    for event, fn in ((AttackRolled, swung), (Hit, struck)):
        seen = c.watch(
            event, fn, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} unseen"
        )
        veil.on_end.append(lambda s=seen: c.world.effects.end(s, "no longer unseen"))


def _unseen(world: World, eid: int) -> bool:
    """"Requirement: it must be invisible", as a gate. Being unseen is held as
    `HIDDEN_FROM`, so the question is whether anything has lost sight of it."""
    return bool(hidden_from(world, eid))


def _blind_to_me(c: Cast, reach: int) -> int | None:
    """The target if it cannot see this creature, else another in reach that
    cannot. Returning early instead would spend a standard action on nothing."""
    blind = hidden_from(c.world, c.me)
    if c.target is not None and c.target in blind:
        return c.target
    return next(
        (foe for foe in sorted(_adjacent_foes(c, reach), key=c.distance) if foe in blind),
        None,
    )


def _cannot_see_me_in_reach(world: World, eid: int) -> bool:
    return _reachable(world, eid, 1, lambda foe: foe in hidden_from(world, eid))


def _exposed(c: Cast, reach: int) -> int | None:
    """The target if it is granting this creature combat advantage, else the
    nearest creature in reach that is."""
    if c.target is not None and has_combat_advantage(c.world, c.me, c.target):
        return c.target
    return next(
        (
            foe
            for foe in sorted(_adjacent_foes(c, reach), key=c.distance)
            if has_combat_advantage(c.world, c.me, foe)
        ),
        None,
    )


def _opening_in_reach(world: World, eid: int) -> bool:
    return _reachable(world, eid, 1, lambda foe: has_combat_advantage(world, eid, foe))


def _ridden_by(least: int):  # noqa: ANN202
    """"While mounted by a friendly rider of Nth level or higher".

    **`targets`, not `sources`.** The relation is stored
    `set(RIDDEN_BY, mount, rider)`, so a mount's riders are its `targets`; its
    `sources` are whatever it is itself riding, which for a mount is nothing.
    """

    def gate(world: World, eid: int) -> bool:
        for rider in world.relations.targets(Relation.RIDDEN_BY, eid):
            stats = world.get(rider, Stats)
            if stats is not None and stats.level >= least:
                return True
        return False

    return gate


def _recharge_when_nobody_blinded(c: Cast) -> None:
    """Put the row back up at the top of its turn when no enemy is blinded.

    The second half of a two-clause printed recharge, and it has to be asked
    rather than watched: the condition is the *absence* of something, which no
    event announces. The die stays in the header either way.
    """
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(effect.label == label for effect in c.world.effects.of(me)):
        return

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if not any(c.is_(Condition.BLINDED, on=foe) for foe in c.enemies()):
            c.restore_use(ref, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=label)


def _recharge_on_melee_miss(c: Cast) -> None:
    """"Recharge when it misses with a melee attack" -- any melee attack, which
    is why this cannot be `_recharge_on_miss`: that one asks whether the row
    that missed was this one."""
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(effect.label == label for effect in c.world.effects.of(me)):
        return

    def missed(ev: Miss) -> None:
        if ev.attacker == me and _reach_kind(ev.power) == "melee":
            c.restore_use(ref, on=me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=label)


def _drags_its_catch(c: Cast) -> None:
    """Whoever it has hold of travels with it and stays held.

    The captive is placed rather than pushed: the printed line names the
    destination -- a square of the creature's choice adjacent to it -- and a
    bare distance would ask the controller to pick, which on a quiet board
    walks the other way.
    """
    me = c.me

    def along(ev: Moved) -> None:
        if ev.actor != me:
            return
        for victim in _holding(c):
            sq = _free_square_beside(c, me)
            if sq is not None:
                c.teleport(1, who=victim, to=sq)
                c.grab(on=victim, by=me)

    c.watch(Moved, along, until=When.ENCOUNTER, on=me, label=f"{c.ref} drag")


def _hit_me_since_my_turn(c: Cast) -> set[int]:
    """Who has landed a blow on this creature since its last turn began.

    Read off the log, which is the only record of it: nothing on a creature
    remembers who hurt it, and the question is asked as the next attack rolls
    rather than when the row was used.
    """
    me = c.me
    recent: set[int] = set()
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == me and not ev.ghost:
            break
        if isinstance(ev, Hit) and ev.target == me:
            recent.add(ev.attacker)
    return recent


def _shoved_me(world: World, me: int, ev: Any) -> bool:
    """Forced movement of this creature. `MoveStart` is the interrupt window --
    by `MoveEnd` the creature has already been moved -- and it carries `kind_`
    on every emission."""
    return getattr(ev, "actor", None) == me and getattr(ev, "kind_", "") in (
        "push",
        "pull",
        "slide",
    )


def _in_my_zone(c: Cast) -> Zone | None:
    """The body of whichever of its own zones this creature is standing in.

    The `Zone` itself and not its id: `Zones` records who is inside but keeps
    the squares on the component, and "another square in the zone" needs them.
    """
    for zone in c.my_zones():
        if c.me in c.world.zones.occupants(zone):
            return c.world.get(zone, Zone)
    return None


# ==========================================================================
# m1447
# ==========================================================================


@power(
    "m1447a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 2),
)
def m1447a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1447a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.ILLUSION, Keyword.RADIANT, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 2, dtype=DamageType.RADIANT, kind=LIMITED, half_on_miss=True),
)
def m1447a1(c: Cast) -> None:
    """"Caught in the blast" is read as targeted rather than as hit, which is
    what the word means -- a creature in the area is caught by it whether the
    roll lands. Counted on the last target, because it is a fact about the
    whole use and not about any one of them."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if c.last and len([t for t in c.targets if t in c.enemies()]) >= 2:
        c.invisible(on=c.me, until=When.SONT)


@power(
    "m1447a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1447a2(c: Cast) -> None:
    _vanish_until_struck(c)


# ==========================================================================
# m3131
# ==========================================================================


@power(
    "m3131a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m3131a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3131a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3131a1(c: Cast) -> None:
    """The printed "recharge when bloodied" is armed on top of the die, not
    instead of it: the die is what `actions.recharge` rolls and what the card
    shows, and the two only ever agree to make the row available sooner."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3131a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m3131a2(c: Cast) -> None:
    _vanish_until_struck(c)


# ==========================================================================
# m3567
# ==========================================================================


@power(
    "m3567a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 5, dtype=DamageType.NECROTIC),
    narrative=("skill:thievery",),
)
def m3567a0(c: Cast) -> None:
    """Whether it was unseen is read **before** the swing: `resolve.attack`
    clears `HIDDEN_FROM` for whoever attacked, so asking afterwards answers
    about a world that no longer exists.

    The alternative half of the printed rider is a Thievery check to pick the
    target's pocket, with a bonus for not being spotted. Nothing on a board
    rolls Thievery and no square holds a purse, so the circumstance has no
    combat meaning and there is no verb missing -- only the ongoing damage,
    which is the branch that plays.
    """
    victim = c.target
    unseen = victim is not None and victim in hidden_from(c.world, c.me)
    if c.strike():
        c.hit()
        if unseen:
            c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3567a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3567a1(c: Cast) -> None:
    """"Until the end of its next turn **or** until it attacks" is the clock and
    the catch; `_vanish_until_it_swings` is both, and it watches the roll rather
    than the hit because swinging gives it away whether or not it lands."""
    _vanish_until_it_swings(c, When.EONT)
    c.shift(1)


@power(
    "m3567a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    out_of_combat=True,
)
def m3567a2(c: Cast) -> None:
    """Deliberately inert. What is teleported is an object the creature is
    carrying, to a place it knows of -- nothing a fight contains, and no
    creature, square or hold changes as a result."""


# ==========================================================================
# m4115
# ==========================================================================


@power(
    "m4115a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m4115a0(c: Cast) -> None:
    """Two damage expressions of different types, so the second is rolled in
    the body: the header carries one `dtype` and `Damage(dtypes=)` would make
    the whole line both types rather than one line of each."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.LIGHTNING)


@power(
    "m4115a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 3),
)
def m4115a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4115a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m4115a2(c: Cast) -> None:
    _twice(c, "m4115a1")


@power(
    "m4115a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=5),
    damage=Damage(
        "2d8", 3, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True
    ),
)
def m4115a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)
    else:
        c.hit(half=True)


@power(
    "m4115a4",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4115a4(c: Cast) -> None:
    """"Recharges, and it uses it" -- the use is handed the row directly rather
    than waiting for the die, which is what "and uses it" means. `Bloodied` is
    announced once, so the trigger needs no "first" of its own."""
    _recharge_and_fire(c, "m4115a3")


@power(
    "m4115a5",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=5),
)
def m4115a5(c: Cast) -> None:
    """No damage line at all: the stun is the whole of the Hit. "Aftereffect"
    is the hold's `on_end` -- laid now as a second save-ends effect it would
    start running while the victim was still stunned."""
    victim = c.target
    if victim is None or not c.strike():
        return
    held = c.stunned(until=When.EONT)
    if held is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)
        )


@power(
    "m4115a6",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FEAR],
)
def m4115a6(c: Cast) -> None:
    """"Grant combat advantage" with nobody named is to everybody, which is
    `to="team"` -- the creature and its allies. Who is adjacent is asked after
    the step, because the printed line measures at the end of the movement."""
    c.conceal(on=c.me, until=When.EONT)
    c.shift(3)
    for foe in _adjacent_foes(c):
        c.grants_advantage(on=foe, until=When.EONT, to="team")


# ==========================================================================
# m4185
# ==========================================================================


@power(
    "m4185a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m4185a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4185a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4185a1(c: Cast) -> None:
    _twice(c, "m4185a0")


@power(
    "m4185a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d12", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m4185a2(c: Cast) -> None:
    """"Save ends **both**" is one saving throw, so the veil is hung on the
    burn's own hold rather than given a clock of its own -- two save-ends
    effects would hand the victim two throws against one printed sentence.
    Invisibility is held as a relation and not as a condition, which is why it
    cannot simply join `Effect.conditions` here."""
    _recharge_when_bloodied(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = c.ongoing(5, DamageType.POISON, on=victim)
    veil = c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)
    if burn is not None and veil is not None:
        burn.on_end.append(lambda: c.world.effects.end(veil, "it saved"))


@power(
    "m4185a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4185a3(c: Cast) -> None:
    _edge_damage(c)


@power(
    "m4185a4",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.no_mode(name)", "c.move_through()"),
)
def m4185a4(c: Cast) -> None:
    """Everything the shape installs is tied to the form's own hold, or the
    bans outlive it; the free action out is `revert=FREE`, and what happens on
    the way out is hung on the same hold.

    Two clauses are dropped. Nothing takes a movement mode **away** --
    `c.mode` keeps the larger of the old and new speeds, by design -- so
    "cannot fly" has no expression. Nor has folding through an aperture a Tiny
    creature could manage: the grid has no apertures.
    """
    me = c.me
    shape = c.form(modes={"climb": 6}, until=When.EONT, revert=FREE, label=c.ref)
    c.shift(4)
    for held in (
        c.cannot_attack(on=me, until=When.EONT),
        c.ignores_difficult(on=me, until=When.EONT),
        c.no_provoke(on=me, until=When.EONT),
    ):
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "form ended"))

    def resurfaces() -> None:
        for near in c.within(2, side="enemy"):
            c.grants_advantage(on=near, until=When.EONT, to=me)

    shape.on_end.append(resurfaces)


# ==========================================================================
# m4201
# ==========================================================================


@power(
    "m4201a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m4201a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4201a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4201a1(c: Cast) -> None:
    """A printed "15/30" takes the normal range, so the creature shoots inside
    the band where it has no penalty."""
    if c.strike():
        c.hit()


@power(
    "m4201a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.ACID, Keyword.ZONE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 4, dtype=DamageType.ACID),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4201a2(c: Cast) -> None:
    """The zone takes in the creature's own square as well as the burst, which
    `c.area()` does not: an area is measured *from* the origin square and need
    not contain it. `c.burns` is the right teeth here and not a `TurnEnd`
    toll -- the card charges for entering **and** for starting a turn there,
    which is exactly the pair it fires on."""
    if c.strike():
        c.hit()
    if c.first:
        zone = c.zone(c.area() | {c.here}, until=When.ENCOUNTER, label=c.ref)
        c.burns(zone, 5, DamageType.ACID)


@power(
    "m4201a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
)
def m4201a3(c: Cast) -> None:
    """The Stealth half is a real bonus and not a narrative one: `c.bonus`
    takes a `skill:` key, so there is nothing here to drop. The poison rides
    on the weapon rather than on the creature, which is what makes it the
    *next* attack with that weapon and not the next attack at all."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.SONT)
    c.bonus("skill:stealth", 4, on=c.me, until=When.SONT)
    c.apply_poison(lambda ev: c.damage("2d6", dtype=DamageType.POISON, on=ev.target))


@power(
    "m4201a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4201a4(c: Cast) -> None:
    """Whether it was hidden has to be recorded before the roll, because
    `resolve.attack` breaks the hiding of whoever swung -- by the time `Miss`
    is announced the state the row is about is already gone. `AttackDeclared`
    is the window in which it is still true."""
    me = c.me
    was = [False]

    def before(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            was[0] = bool(hidden_from(c.world, me))

    def missed(ev: Miss) -> None:
        if ev.attacker == me and was[0] and _reach_kind(ev.power) == "ranged":
            c.hide()

    c.watch(AttackDeclared, before, until=When.ENCOUNTER, on=me, label=f"{c.ref} seen")
    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m4737
# ==========================================================================


@power(
    "m4737a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
    dropped=("query.light_level(world, square)",),
)
def m4737a0(c: Cast) -> None:
    """The blow lands. How dark the square is has no reader: the grid holds
    terrain and cover and no light level, so the +2 and the extra 6 damage
    the card pays in dim light or darkness have nothing to ask."""
    if c.strike():
        c.hit()


@power(
    "m4737a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=False,
)
def m4737a1(c: Cast) -> None:
    """The flight is spent in two halves rather than all at once, because "at
    any point during that movement" is what puts a creature in reach that one
    step to one destination would not. The waiver of the opening is laid
    against the victim only, as printed."""
    _mobile_attack(c, 8)


@power(
    "m4737a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by(3),
    requires_text="it must be carrying a rider of 3rd level or higher",
    trigger="it uses m4737a1",
    on=Trigger(PowerUsed, about_me, "it uses m4737a1"),
)
def m4737a2(c: Cast) -> None:
    """A trait's `requires=` is never consulted and a triggered row's is read
    only when it is offered, so the Requirement is asked again here. The
    rider's swing is a basic attack of its own, which is why it is granted
    rather than rolled: `c.strike` always rolls for the caster."""
    ev = c.trigger
    if getattr(ev, "power", "") != "m4737a1":
        return
    who = c.rider()
    if who is None:
        return
    foe = next((f for f in c.enemies() if c.adjacent_to(f, who)), None)
    if foe is None:
        return
    c.no_provoke(from_=foe, on=who, until=When.EOT)
    c.grant_attack(who, on=foe)


@power(
    "m4737a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.altitude_limit()",),
)
def m4737a3(c: Cast) -> None:
    """Refused in play: the whole of this row is a ceiling on how high the
    creature may fly while carrying a rider, and nothing caps a height.
    `c.hover` holds a creature up and `c.rise` puts it there; neither refuses
    to go further, so there is nothing here to write half of."""


# ==========================================================================
# m5485
# ==========================================================================


@power(
    "m5485a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5485a0(c: Cast) -> None:
    """"At least 5 squares during its turn" is a tally of the whole turn and
    not of one step, which is what `_moved_far` keeps."""
    me = c.me
    _moved_far(c, me, 5, lambda: c.conceal(on=me, until=When.EONT))


@power(
    "m5485a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5485a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5485a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature that cannot see it",
        relation=Relation.HIDDEN_FROM,
    ),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 1, dtype=DamageType.POISON),
)
def m5485a2(c: Cast) -> None:
    """The restriction is the target line now, routed through
    `query.unseen_by` -- so the `requires=` that kept the row off the offer and
    the body's redirect both came out, and the pool is narrower than
    `_blind_to_me` was: `unseen_by` folds in a capped sight range, which
    `query.hidden_from` on its own does not. #401."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m5485a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=5),
)
def m5485a3(c: Cast) -> None:
    """No damage line: the shove and the blind are the whole of the Hit. Both
    printed recharge conditions are armed -- one is an event and one is the
    absence of a state, so they are asked in different places -- and the die
    stays in the header, which is what the card shows."""
    if c.first:
        _recharge_when_using(c, "m5485a1")
        _recharge_when_nobody_blinded(c)
    if c.strike():
        c.push(3)
        c.blinded(until=When.EONT)


@power(
    "m5485a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("4d6", 4, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m5485a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


# ==========================================================================
# m5805
# ==========================================================================


@power(
    "m5805a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5805a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5805a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d4", 7, dtype=DamageType.FIRE),
)
def m5805a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5805a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("4d6", 10, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m5805a2(c: Cast) -> None:
    _recharge_when_using(c, "m5805a3")
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5805a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m5805a3(c: Cast) -> None:
    """The cloud is laid and blinds whoever is standing in it, held per
    occupant and lifted on the way out -- "while entirely within" is geometry
    rather than a duration. What is dropped is the exemption: the zone blocks
    sight for every creature **except** this one, and `c.zone(blocks_sight=)`
    is terrain with nothing to carve out."""
    _recharge_when_using(c, "m5805a2")
    _blinding_cloud(c, 1)


@power(
    "m5805a4",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy pushes, pulls or slides it while it stands in its own zone",
    on=Trigger(
        MoveStart, _shoved_me, "it is pushed, pulled or slid while in its own zone"
    ),
    dropped=("MoveStart.by",),
)
def m5805a4(c: Cast) -> None:
    """`MoveStart` is the interrupt window -- by `MoveEnd` the creature has
    already been moved and is no longer in the zone the row is about -- and it
    carries `kind_` on every emission, which is how the three printed kinds of
    shove are told from a walk.

    What it does not carry is who did the shoving, so "the triggering enemy"
    cannot be named and the swing goes to whoever is in reach instead. The
    shift is exact: it stays inside the zone, which is what the card says.
    """
    body = _in_my_zone(c)
    if body is None:
        return
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.basic(on=foe)
    here = c.here
    inside = sorted(
        sq
        for sq in body.squares
        if sq != here
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )
    if inside:
        c.shift(2, to=inside[0])


# ==========================================================================
# m5885
# ==========================================================================


@power(
    "m5885a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 7, dtype=DamageType.POISON),
)
def m5885a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(AC, 2, until=When.EONT)
        c.penalty(REF, 2, until=When.EONT)


@power(
    "m5885a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 8, dtype=DamageType.RADIANT, half_on_miss=True),
    requires=_unseen,
    requires_text="it must be invisible",
)
def m5885a1(c: Cast) -> None:
    """The Requirement is asked twice -- once as the gate that keeps the row
    off the menu and once here, because a gate is read by `dsl.usable` alone
    and several routes into a row never call it. The two halves of the Miss
    line are a different blind from the Hit's: until the end of the *target's*
    next turn, and not save ends."""
    if not _unseen(c.world, c.me):
        return
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.RADIANT)
    else:
        c.hit(half=True)
        c.blinded(until=When.EOTNT)


@power(
    "m5885a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5885a2(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m6038
# ==========================================================================


@power(
    "m6038a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6038a0(c: Cast) -> None:
    """A named kind of difficult terrain, not all of it: `c.ignores_difficult`
    takes the word, and a bare call would waive rubble and ice as well."""
    c.ignores_difficult("web", on=c.me)


@power(
    "m6038a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3, dtype=DamageType.POISON),
)
def m6038a1(c: Cast) -> None:
    """"Or 2d8 + 10" replaces the printed damage rather than adding to it, so
    it is one expression or the other and the header's line is skipped."""
    if not c.strike():
        return
    if c.target in hidden_from(c.world, c.me):
        c.damage("2d8", 10, dtype=DamageType.POISON)
    else:
        c.hit()


@power(
    "m6038a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 1, dtype=DamageType.RADIANT),
)
def m6038a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying two conditions -- that is what
    makes one throw end both of them. The Effect line is once for the whole
    use, which is what `c.first` is for."""
    if c.strike():
        c.hit()
        c.condition(Condition.BLINDED, Condition.RESTRAINED, until=When.SAVE_ENDS)
    if c.first:
        c.invisible(on=c.me, until=When.EONT)


@power(
    "m6038a3",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is hit by an attack",
    on=Trigger(Hit, hits_me, "it is hit by an attack"),
)
def m6038a3(c: Cast) -> None:
    c.teleport(6)


# ==========================================================================
# m6345
# ==========================================================================


@power(
    "m6345a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6345a0(c: Cast) -> None:
    """Deliberately inert, and whole rather than per clause: the entire printed
    trait is a check to notice the creature is a creature, which no fight
    rolls -- a board that has it on it has already been told what it is."""


@power(
    "m6345a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=Target("any", 1, everyone=True, label="nonplant creatures in the burst"),
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 2, dtype=DamageType.THUNDER),
    dropped=("Target.creature_kind",),
)
def m6345a1(c: Cast) -> None:
    """"Special: this is a basic attack" is filed with `c.as_basic`, so a row
    elsewhere granting this creature a basic swing offers this one.

    The exclusion is by creature type, which `Target` cannot say: it is
    recorded in the label and enforced here. A creature of the excluded kind
    is skipped rather than redirected -- this is a burst and every other
    target is still hit, so there is nothing to redirect to.
    """
    if c.first:
        c.as_basic(c.ref, on=c.me, until=When.ENCOUNTER)
    if c.target is not None and c.is_kind("plant", on=c.target):
        return
    if c.strike():
        c.hit()


@power(
    "m6345a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6345a2(c: Cast) -> None:
    """Deliberately inert. The whole effect is a noise audible 20 squares off;
    nothing on a board hears, and no creature, square or hold changes. The
    trigger is left undeclared for the same reason -- there is nothing for it
    to fire into, and a declared one would make the row look like a reaction
    that does something."""


# ==========================================================================
# m6395
# ==========================================================================


@power(
    "m6395a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6395a0(c: Cast) -> None:
    _drags_its_catch(c)


@power(
    "m6395a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6395a1(c: Cast) -> None:
    """Asked as each roll is looked up rather than armed and disarmed on the
    grab: the hold can end in a dozen ways and a bonus laid once when it began
    would never come off."""
    me = c.me
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence,
            5,
            on=me,
            until=When.ENCOUNTER,
            when=lambda _ctx: _has_hold(c.world, me),
        )


@power(
    "m6395a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m6395a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6395a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature granting combat advantage to it",
        grants_ca=True,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 3),
    dropped=("c.grab(dc=)",),
)
def m6395a3(c: Cast) -> None:
    """"Sustain Standard" has a payout as well as a clock, and the clock alone
    is what this shape used to carry -- without `c.on_sustain` the damage half
    of the printed Sustain line goes nowhere. The hold is separate from the
    grab because `c.grab` takes no duration of its own: re-laying it each time
    the row is sustained is what "the grab persists" means.

    The printed escape DC is the dropped half; `c.grab` takes no number.

    "Granting combat advantage to it" is the target line now, so the `requires=`
    gate and the body's re-pick both came out. #401.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    c.grab(by=c.me)
    held = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=STANDARD)

    def again() -> None:
        c.damage("2d8", 3, on=victim)
        c.grab(on=victim, by=c.me)

    c.on_sustain(held, again)


@power(
    "m6395a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m6395a4(c: Cast) -> None:
    """As its sibling elsewhere: the cloud and the blind play, and the
    exemption the card prints -- every creature except this one loses sight --
    is the half `c.zone(blocks_sight=)` has nothing to carve out of."""
    _blinding_cloud(c, 1)


# ==========================================================================
# m6582
# ==========================================================================


@power(
    "m6582a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6582a0(c: Cast) -> None:
    """The healing works; the pause two damage types are printed as causing
    has no hold to live on."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m6582a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 6),
)
def m6582a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d10", dtype=DamageType.FIRE)


@power(
    "m6582a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m6582a2(c: Cast) -> None:
    _recharge_when_using(c, "m6582a3")
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


@power(
    "m6582a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.POISON, Keyword.POLYMORPH],
)
def m6582a3(c: Cast) -> None:
    """A polymorph rather than a stance -- it is in the shape and may step out
    of it -- so `revert=MINOR` is what leaving costs, and everything the shape
    installs hangs on the form's hold or outlives it.

    Squeezing at full speed and without granting the drop for it is written
    rather than dropped: half speed, the attack penalty and the advantage are
    the *whole* of what `Condition.SQUEEZING` is, and `_squeezes_freely` takes
    the hold off as it lands. Nine rows in the tree carry a marker saying this
    cannot be said; it can, and the report says so.
    """
    me, ref = c.me, c.ref
    shape = c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{ref} pool")
    for held in (
        c.resize(Size.LARGE, on=me, until=When.ENCOUNTER),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
        c.shares_space(on=me, difficult=False),
        c.phasing(on=me, until=When.ENCOUNTER),
    ):
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "form ended"))
    _squeezes_freely(c)

    def scald(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or shape not in c.world.effects.of(me):
            return
        if c.distance(ev.actor) == 0:
            c.damage(
                "2d6",
                dtypes=(DamageType.FIRE, DamageType.POISON),
                on=ev.actor,
            )

    c.watch(TurnStart, scald, until=When.ENCOUNTER, on=me, label=f"{ref} pool")


# ==========================================================================
# m6584
# ==========================================================================


@power(
    "m6584a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6584a0(c: Cast) -> None:
    """As its sibling: the healing works, the type-triggered pause does not."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m6584a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m6584a1(c: Cast) -> None:
    """The extra die is added to the printed line rather than replacing it,
    which is what "plus" says -- the sibling block's card says "or" and is
    written the other way."""
    if c.strike():
        c.hit()
        if c.target in hidden_from(c.world, c.me):
            c.damage("1d8")


@power(
    "m6584a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 5),
)
def m6584a2(c: Cast) -> None:
    """The burn is fire and the blow is not: the card types only the ongoing
    half, so the header stays untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6584a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m6584a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


@power(
    "m6584a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6584a4(c: Cast) -> None:
    """"Until it hits or misses with an attack" is the roll and not the
    outcome, which is the watch `_vanish_until_it_swings` keeps."""
    _recharge_on_melee_miss(c)
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m6628
# ==========================================================================


@power(
    "m6628a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6628a0(c: Cast) -> None:
    """`team` is compared directly rather than asking `c.allies`: `query`
    filters out the dead, so a creature that has just been reduced to 0 hit
    points is no longer in the list -- which is precisely when this fires.

    The swing is granted rather than rolled, because it is the ally's attack
    with the ally's numbers.
    """
    me = c.me
    c.aura(2, until=When.ENCOUNTER, on=me)

    def felled(ev: Dropped) -> None:
        mate = ev.actor
        if mate == me or team(c.world, mate) is not team(c.world, me):
            return
        if c.distance(mate) > 2:
            return
        foe = next((f for f in c.enemies() if c.adjacent_to(f, mate)), None)
        if foe is not None:
            c.grant_attack(mate, on=foe)

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6628a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6628a1(c: Cast) -> None:
    c.grant_action_point(1, on=c.me)


@power(
    "m6628a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m6628a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6628a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6628a3(c: Cast) -> None:
    """Three things last exactly as long as the hold the victim saves against,
    so all three are hung on it -- a second save-ends effect would give the
    victim a second throw against one printed sentence.

    "Recharge when no creature is affected by this power" is the same hold
    ending, which is why it is the hold that hands the use back rather than a
    watch asking each round whether anybody still is.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.conceal(on=c.me, until=When.EONT)
        return
    c.hit()
    held = c.grants_advantage(on=victim, until=When.SAVE_ENDS)
    if held is None:
        return
    extra = [
        c.invisible(to=foe, on=c.me, until=When.SAVE_ENDS)
        for foe in c.enemies()
        if foe != victim
    ]
    extra.append(
        c.bonus(
            "damage",
            0,
            dice="1d6",
            on=c.me,
            until=When.SAVE_ENDS,
            when=lambda ctx: ctx.get("target") == victim
            and ctx.get("power") == "m6628a2",
        )
    )
    for one in extra:
        if one is not None:
            held.on_end.append(lambda h=one: c.world.effects.end(h, "it saved"))
    held.on_end.append(lambda: c.restore_use(c.ref, on=c.me))


@power(
    "m6628a4",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m6628a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)
        c.push(1)


# ==========================================================================
# m815
# ==========================================================================


@power(
    "m815a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
)
def m815a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m815a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m815a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m815a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m815a2(c: Cast) -> None:
    """Both keys are read off the damage context as the blow is rolled rather
    than asked of the board afterwards: a one-shot grant of the advantage is
    already spent by then, and `ranged` is a fact about the attack and not
    about the creature."""
    c.bonus(
        "damage",
        0,
        dice="2d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and bool(ctx.get("ranged")),
    )


@power(
    "m815a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("etl.monster.attack_line()",),
)
def m815a3(c: Cast) -> None:
    """The two holds play and are exact. What is missing is the attack line
    itself: the database filed this row with no roll, no defence and no
    damage, so the Hit has nothing to be conditional on and the conditions are
    laid outright. The same ETL defect as the 98 rows of #360, one step
    worse -- there the defence alone is gone.

    "Speed becomes 2" is what `c.slowed` is; the opportunity-attack penalty is
    gated on the attack context, which carries `opportunity`.
    """
    victim = c.target
    if victim is None:
        return
    c.slowed(until=When.EONT)
    c.penalty(
        "attack",
        2,
        on=victim,
        until=When.EONT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m815a4",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    todo=("etl.monster.trigger_text()",),
)
def m815a4(c: Cast) -> None:
    """Refused in play, and the gap is in the data rather than in the engine:
    the row is filed as an immediate reaction with **no trigger line at all**,
    so there is nothing to declare and a reaction with no trigger can never
    fire. Two other blocks in this wave print the sentence this one is missing;
    guessing which it is would be inventing a rule. The shift itself is one
    line and waits on the trigger, not the other way round.
    """


@power(
    "m815a5",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m815a5(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m915
# ==========================================================================


@power(
    "m915a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m915a0(c: Cast) -> None:
    """The parenthetical "+10 against a bloodied target" is paid as
    `c.strike(plus=1)` rather than as a standing bonus: three rows on this
    block print it, and three untyped +1s would stack.

    The secondary attack has its own line and only the primary fits in the
    header, so its total is rolled with the level term taken back out by hand
    -- `world.scaling.trim` is the same arithmetic the header does.
    """
    victim = c.target
    if victim is None:
        return
    plus = 1 if c.bloodied(on=victim) else 0
    if not c.strike(plus=plus):
        return
    c.hit()
    if c.attack(c.world.scaling.trim(10, c.level), FORT, on=victim):
        c.ongoing(10, DamageType.POISON, on=victim)


@power(
    "m915a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m915a1(c: Cast) -> None:
    """"Cannot make both attacks against the same target" is why this is
    `UpTo(2)` and not `_twice`: the body runs once per chosen creature, so two
    creatures take one swing each and the second swing is never added back."""
    c.use_power("m915a0")


@power(
    "m915a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_while_bloodied,
    requires_text="it must be bloodied",
    trigger="an adjacent enemy attacks it while it is bloodied",
    on=Trigger(AttackDeclared, targets_me, "an adjacent enemy attacks it"),
)
def m915a2(c: Cast) -> None:
    """The adjacency and the bloodied half are asked here rather than in the
    predicate: `targets_me` is the part a ready-made predicate says, and a
    `requires=` is read only when the row is offered.

    The swing is m915a0 itself, secondary attack and all, which is why it is
    used rather than rewritten.
    """
    foe = _triggering_enemy(c)
    if foe is None or not c.adjacent(foe) or not c.bloodied(on=c.me):
        return
    c.use_power("m915a0", on=foe)


@power(
    "m915a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m915a3(c: Cast) -> None:
    """Plainly "becomes invisible until the end of its next turn" and not
    "until it attacks", so the veil takes a clock and no watch."""
    c.teleport(5)
    c.invisible(on=c.me, until=When.EONT)


@power(
    "m915a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m915a4(c: Cast) -> None:
    """Who has hurt it lately is asked as the next attack rolls, not now:
    "since his last turn" is a window that is still open while the bonus
    stands, and a list taken here would be stale the moment anybody else
    swung. Both halves are `once=True`, because the card pays for one attack.
    """
    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    _recharge_when_bloodied(c)
    c.bonus(
        "attack", 1, on=me, kind="power", until=When.ENCOUNTER, once=True,
        when=paid_back,
    )
    c.bonus("damage", 3, on=me, until=When.ENCOUNTER, once=True, when=paid_back)
