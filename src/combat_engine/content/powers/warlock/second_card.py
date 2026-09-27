"""Warlock: the second stat block a card prints beside its own.

Five rows, and four of them were already written inside their parents as
hand-armed watchers, because a stanza with no ref could not be a row. They
have refs now, so each parent keeps only what it puts on the board and the
stanza is declared with the action and the trigger the card prints.

Two things the `active` helper cannot see, and this file works round both
rather than gating on something false:

* **A zone's hold hangs on the zone, not on its caster.** `Zones._spawn`
  applies it to the zone entity and labels it `zone <ref>`, so
  `world.effects.of(caster)` never carries the parent's name. `_zoned`
  looks the zone up instead.
* **A conjuration is the same.** `_conjured` asks whether the thing is
  still standing, which is what "while the shadow persists" means.

`p13642` and `p13650` leave a real hold on the caster, so those two use
`active` as printed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.cards import active
from combat_engine.engine import (
    CHA,
    DAILY,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    Attack,
    AttackDeclared,
    Cast,
    Condition,
    DamageType,
    Effect,
    Keyword,
    Melee,
    MoveStart,
    Position,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    World,
    ZoneEntered,
    both,
    enemy_within,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The move kinds a creature chooses for itself. A push, a pull or a slide
#: is somebody else's doing, and "willingly" is the word that excludes them.
WILLING = ("walk", "run", "shift", "teleport", "charge", "climb", "swim", "fly")


def _my_conjuration(world: World, eid: int, ref: str) -> int | None:
    """The conjuration that creature's `ref` left standing, if any.

    Matched on a prefix as well as outright, because a row conjuring more
    than one thing labels them `<ref> 0`, `<ref> 1`.
    """
    for who, conj in world.each(Conjuration):
        if conj.by != eid:
            continue
        if conj.ref != ref and not conj.ref.startswith(f"{ref} "):
            continue
        if world.get(who, Position) is not None:
            return who
    return None


def _my_zone(world: World, eid: int, ref: str) -> int | None:
    for who, zone in world.each(Zone):
        if zone.owner == eid and zone.label == ref:
            return who
    return None


def _conjured(ref: str) -> Any:
    def check(world: World, eid: int) -> bool:
        return _my_conjuration(world, eid, ref) is not None

    return check


def _zoned(ref: str) -> Any:
    def check(world: World, eid: int) -> bool:
        return _my_zone(world, eid, ref) is not None

    return check


def _foe(world: World, me: int, who: int | None) -> bool:
    return who is not None and who != me and team(world, who) is not team(world, me)


def _by_a_foe(world: World, me: int, ev: Any) -> bool:
    return _foe(world, me, getattr(ev, "attacker", None))


def _leaves_the_shadow(ref: str) -> Any:
    """"An enemy willingly leaves a square adjacent to the shadow."

    `MoveStart`, not `MoveEnd`: the enemy has to still be beside the shadow
    for the sentence to be true, and by `MoveEnd` it has gone -- which is
    the reading `docs/AUTHORING.md` records. It is also the window an
    interrupt belongs in.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if not _foe(world, me, who) or getattr(ev, "kind_", "") not in WILLING:
            return False
        thing = _my_conjuration(world, me, ref)
        pos = world.get(thing, Position) if thing else None
        if pos is None:
            return False
        return bool(squares_of(world, who) & spread(pos.squares, 1))

    return check


def _enters_the_zone(ref: str) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        zone = _my_zone(world, me, ref)
        return zone is not None and getattr(ev, "zone", None) == zone and _foe(
            world, me, getattr(ev, "actor", None)
        )

    return check


def _ends_turn_in_zone(ref: str) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "ghost", False):
            return False
        who = getattr(ev, "actor", None)
        if not _foe(world, me, who):
            return False
        zone = _my_zone(world, me, ref)
        standing = world.get(zone, Zone) if zone else None
        if standing is None:
            return False
        return bool(squares_of(world, who) & standing.squares)

    return check


@power(
    "p13952b",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF),
    requires=_conjured("p13952"),
    requires_text="the p13952 power must be active",
    trigger="an enemy willingly leaves a square adjacent to the shadow on its turn",
    on=Trigger(
        MoveStart,
        _leaves_the_shadow("p13952"),
        "an enemy willingly leaves a square adjacent to the shadow",
    ),
)
def p13952b(c: Cast) -> None:
    """Printed "Melee 1", and the square it is measured from is the shadow's
    rather than the caster's -- which no `reach` can say. So the header takes
    no target and the triggering enemy is read off the event, with the roll
    made from the shadow.

    "Cold and necrotic" is one blow of two types and `c.damage` carries one,
    so it lands as cold, the way the parent's own line does.
    """
    shade = _my_conjuration(c.world, c.me, "p13952")
    who = getattr(c.trigger, "actor", None)
    if shade is None or who is None:
        return
    if c.strike(on=who, from_=shade):
        c.flat(10, dtype=DamageType.COLD, on=who)
        c.immobilized(on=who, until=When.EOT)


@power(
    "p13642b",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.RADIANT],
    requires=active("p13642"),
    requires_text="the p13642 power must be active",
    trigger="an adjacent enemy attacks you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, enemy_within(1)),
        "an adjacent enemy attacks you",
    ),
)
def p13642b(c: Cast) -> None:
    """No attack roll: the printed line is an Effect, so the damage lands
    whether the enemy's own swing does or not."""
    c.flat(5 + c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p13883b",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF),
    requires=_zoned("p13883"),
    requires_text="the p13883 power must be active",
    trigger="an enemy enters the zone willingly or ends its turn there",
    on=(
        Trigger(ZoneEntered, _enters_the_zone("p13883"), "an enemy enters the zone"),
        Trigger(TurnEnd, _ends_turn_in_zone("p13883"), "an enemy ends its turn there"),
    ),
)
def p13883b(c: Cast) -> None:
    """Both halves of the printed trigger are declared. The second one --
    "or ends its turn there" -- was the half the parent recorded as unwritten
    for want of an event; `TurnEnd` is that event, and the occupants are
    found by intersecting the zone's squares with the creature's.

    "Willingly" is not asked of the entry: `ZoneEntered` carries no move
    kind, so a shoved enemy sets it off too.
    """
    if not c.strike():
        return
    c.flat(5 + c.cha_mod, dtype=DamageType.NECROTIC)
    if c.is_(Condition.SLOWED):
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.NECROTIC),
        )
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p16263b",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ELEMENTAL],
    attack=Attack(CHA, vs=REF),
    requires=_conjured("p16263"),
    requires_text="the p16263 power must be active",
)
def p16263b(c: Cast) -> None:
    """Reached "through" a tentacle, so the two squares are measured from the
    conjuration and the header cannot say so -- hence no target line and a
    victim picked out of what the tentacle can hold.

    "Each Failed Saving Throw: 5 cold" is the `escalate` hook on the grab,
    which is the one place a failed save can pay out.
    """
    arm = _my_conjuration(c.world, c.me, "p16263")
    pos = c.world.get(arm, Position) if arm else None
    if pos is None:
        return
    reachable = sorted(c.in_squares(spread(pos.squares, 2), side="enemy"))
    if not reachable:
        return
    victim = c.choose(reachable, f"{c.ref}: who the tentacle takes")
    if victim is None:
        return

    def bite(eff: Effect) -> None:
        c.flat(5, dtype=DamageType.COLD, on=eff.owner)

    if c.strike(on=victim, from_=arm):
        c.damage("3d6", c.cha_mod, dtype=DamageType.COLD, on=victim)
        c.pull(1, on=victim, anchor=min(pos.squares))
        c.condition(
            Condition.GRABBED, until=When.SAVE_ENDS, on=victim, escalate=bite
        )
    else:
        c.half_damage("3d6", c.cha_mod, dtype=DamageType.COLD, on=victim)


@power(
    "p13650b",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    requires=active("p13650"),
    requires_text="the p13650 power must be active",
    trigger="an enemy attacks you",
    on=Trigger(AttackDeclared, both(targets_me, _by_a_foe), "an enemy attacks you"),
)
def p13650b(c: Cast) -> None:
    c.teleport(3)
