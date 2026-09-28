"""Wizard: the second stat block a card prints beside its own.

Seven rows. Every one of them is the thing the wizard's parent left on the
board getting to act -- a zone underfoot, a pattern in the air, a fist, a
twin, five globes -- and each was written inside its parent as a hand-armed
listener because the stanza had no ref. They have refs now.

The recurring difficulty is the **origin**. Six of these print their range
from the conjuration or the zone rather than from the caster: "close blast 2
from the fist", "close burst 5 centered on the zone", "using the pattern's
square as the origin square". `Range.from_` knows one such word,
`"companion"`, and `dsl.measured_from` reads nothing else -- so a header
declaring `CloseBlast(2)` would be measured from the wizard and
`dsl.candidates` would refuse every enemy standing round the fist. Those
rows therefore take **no target line**: the reach stays as printed, the
victims are gathered from the conjuration in the body, and `c.strike(from_=)`
rolls from the right square. `Power.is_attack` is false for a targetless
row, so `usable` does not apply the reach gate it would otherwise fail.

`active` is likewise blind to both: a zone's hold hangs on the zone and is
labelled `zone <ref>`, and a conjuration's hangs on the conjuration. So
`_zoned` and `_conjured` ask whether the thing is still standing, which is
what "while it persists" means.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Moved,
    Position,
    Ranged,
    Trigger,
    TurnStart,
    When,
    World,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.movement import place
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _my_conjuration(world: World, eid: int, ref: str) -> int | None:
    for who, conj in world.each(Conjuration):
        if conj.by == eid and conj.ref == ref and world.get(who, Position) is not None:
            return who
    return None


def _my_zone(world: World, eid: int, ref: str) -> int | None:
    for who, zone in world.each(Zone):
        if zone.owner == eid and zone.label == ref:
            return who
    return None


def _carrier(world: World, eid: int, label: str) -> int | None:
    """Whoever is carrying a hold of that name that this creature applied."""
    for eff in world.effects.live.values():
        if eff.label == label and eff.source == eid and not eff.ended:
            return eff.owner
    return None


def _conjured(ref: str) -> Any:
    def check(world: World, eid: int) -> bool:
        return _my_conjuration(world, eid, ref) is not None

    return check


def _zoned(ref: str) -> Any:
    def check(world: World, eid: int) -> bool:
        return _my_zone(world, eid, ref) is not None

    return check


def _holds(label: str) -> Any:
    def check(world: World, eid: int) -> bool:
        return _carrier(world, eid, label) is not None

    return check


def _has_globe(world: World, eid: int) -> bool:
    return any(e.label.startswith("p16288 globe") for e in world.effects.of(eid))


def _foe(world: World, me: int, who: int | None) -> bool:
    return who is not None and who != me and team(world, who) is not team(world, me)


def _enters_the_zone(ref: str) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        zone = _my_zone(world, me, ref)
        return zone is not None and getattr(ev, "zone", None) == zone

    return check


def _starts_turn_near(ref: str, radius: int) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "ghost", False):
            return False
        who = getattr(ev, "actor", None)
        if not _foe(world, me, who):
            return False
        thing = _my_conjuration(world, me, ref)
        pos = world.get(thing, Position) if thing else None
        if pos is None:
            return False
        return bool(squares_of(world, who) & spread(pos.squares, radius))

    return check


def _left_the_twin(world: World, me: int, ev: Any) -> bool:
    """"The target leaves a square adjacent to the twin."

    Asked of `Moved`, which is the only movement event carrying `from_` --
    the square the creature came *from* is the whole sentence, and neither
    `MoveStart` nor `MoveEnd` knows it.
    """
    if getattr(ev, "actor", None) != _carrier(world, me, "p13988 twin"):
        return False
    twin = _my_conjuration(world, me, "p13988")
    pos = world.get(twin, Position) if twin else None
    if pos is None:
        return False
    return getattr(ev, "from_", None) in spread(pos.squares, 1)


def _twin_attacks(world: World, me: int, ev: Any) -> bool:
    who = _carrier(world, me, "p13988 twin")
    return who is not None and getattr(ev, "attacker", None) == who


@power(
    "p2351b",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
    requires=_zoned("p2351"),
    requires_text="the p2351 power must be active",
    trigger="a creature enters the zone",
    on=Trigger(ZoneEntered, _enters_the_zone("p2351"), "a creature enters the zone"),
)
def p2351b(c: Cast) -> None:
    """"This movement does not trigger this power's attack" needs no latch of
    its own: `dsl.use` holds (caster, ref) in flight for the length of the
    body, and `Triggers._answers` skips a row already in it -- so the slide
    below cannot set the row off again.
    """
    who = getattr(c.trigger, "actor", None)
    if who is None:
        return
    if c.strike(on=who):
        c.prone(on=who)
    else:
        c.slide(2, on=who)


@power(
    "p4020b",
    level=3,
    cls="wizard",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ILLUSION, Keyword.CONJURATION],
    attack=Attack(INT, vs=WILL),
    requires=_conjured("p4020"),
    requires_text="the p4020 power must be active",
    trigger="an enemy starts its turn within 3 squares of the pattern",
    on=Trigger(
        TurnStart,
        _starts_turn_near("p4020", 3),
        "an enemy starts its turn within 3 squares of the pattern",
    ),
)
def p4020b(c: Cast) -> None:
    """"It can move into the pattern's square" is already true: `c.conjure`
    leaves the square passable unless the row asked for `solid`, and this one
    did not."""
    pattern = _my_conjuration(c.world, c.me, "p4020")
    who = getattr(c.trigger, "actor", None)
    pos = c.world.get(pattern, Position) if pattern else None
    if who is None or pos is None:
        return
    if c.strike(on=who, from_=pattern):
        c.pull(3, on=who, anchor=pos.square)
        c.slowed(on=who, until=When.EONT)


@power(
    "p4074b",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ILLUSION, Keyword.ZONE],
    attack=Attack(INT, vs=WILL),
    requires=_zoned("p4074"),
    requires_text="the p4074 power must be active",
)
def p4074b(c: Cast) -> None:
    """The parent's zone is a single square, so it is both the centre of the
    burst and the thing everything is pulled toward."""
    zone = _my_zone(c.world, c.me, "p4074")
    standing = c.world.get(zone, Zone) if zone else None
    if standing is None or not standing.squares:
        return
    heart = min(standing.squares)
    for foe in sorted(c.in_squares(spread(standing.squares, 5), side="enemy")):
        if c.strike(on=foe):
            c.pull(4, on=foe, anchor=heart)


@power(
    "p13988b",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
    requires=_conjured("p13988"),
    requires_text="the p13988 power must be active",
    trigger="the target leaves a square adjacent to the twin or makes an attack",
    on=(
        Trigger(Moved, _left_the_twin, "the target leaves a square adjacent to the twin"),
        Trigger(AttackDeclared, _twin_attacks, "the target makes an attack"),
    ),
)
def p13988b(c: Cast) -> None:
    """"Once before the twin vanishes" is the encounter usage plus the last
    line: the conjuration is dispelled whether the swing landed or not, which
    is what "the twin vanishes" says.

    Which creature this is aimed at is not a choice -- it is the one the
    parent hung its hold on -- so the header takes no target line and the
    victim is looked up.
    """
    twin = _my_conjuration(c.world, c.me, "p13988")
    victim = _carrier(c.world, c.me, "p13988 twin")
    stands = c.world.get(victim, Position) if victim else None
    if twin is None or victim is None or stands is None:
        return
    beside = [
        sq
        for sq in sorted(spread(stands.squares, 1) - stands.squares)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if beside:
        place(c.world, twin, beside[0])
    if c.strike(on=victim, from_=twin):
        c.flat(5 + c.int_mod, dtype=DamageType.PSYCHIC, on=victim)
        c.dazed(on=victim, until=When.EOTNT)
    c.dispel(twin)


@power(
    "p12746b",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
    requires=_holds("p12746 haunted"),
    requires_text="the p12746 power must be active",
)
def p12746b(c: Cast) -> None:
    """Printed with no Target line at all: the only creature this can be
    aimed at is the one still carrying the haunting, so it is found rather
    than chosen, and the printed range is checked here because a targetless
    header cannot check it."""
    victim = _carrier(c.world, c.me, "p12746 haunted")
    if victim is None or c.distance(victim) > 20:
        return
    if c.strike(on=victim, ignore_cover=True):
        c.damage("3d10", c.int_mod, dtype=DamageType.PSYCHIC, on=victim)
    else:
        c.half_damage("3d10", c.int_mod, dtype=DamageType.PSYCHIC, on=victim)


@power(
    "p16286b",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(2),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT],
    attack=Attack(INT, vs=REF),
    requires=_conjured("p16286"),
    requires_text="the p16286 power must be active",
)
def p16286b(c: Cast) -> None:
    """The blast comes off the fist, so the enemies are gathered round the
    conjuration and the roll is made from it."""
    fist = _my_conjuration(c.world, c.me, "p16286")
    pos = c.world.get(fist, Position) if fist else None
    if pos is None:
        return
    for foe in sorted(c.in_squares(spread(pos.squares, 2), side="enemy")):
        if c.strike(on=foe, from_=fist):
            c.damage("3d6", c.int_mod, on=foe)
            c.prone(on=foe)


@power(
    "p16288b",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
    once_per_round=True,
    requires=_has_globe,
    requires_text="the p16288 power must be active",
)
def p16288b(c: Cast) -> None:
    """A globe is a hold of its own on the caster, so the number this spends
    and the number the parent's retaliation multiplies are the same one.

    "If the target is already taking ongoing fire damage, that damage
    increases by 5" has exactly one hold to find -- of a type, only the
    highest applies -- so the standing burn is read first and the new one is
    set to five more than it, which supersedes it.
    """
    if not c.strike():
        return
    standing = max(
        (
            eff.ongoing[0]
            for eff in c.world.effects.of(c.target)
            if eff.ongoing and eff.ongoing[1] is DamageType.FIRE
        ),
        default=0,
    )
    c.damage("2d4", c.int_mod, dtype=DamageType.FIRE)
    c.ongoing(standing + 5, DamageType.FIRE)
    for eff in c.world.effects.of(c.me):
        if eff.label.startswith("p16288 globe"):
            c.world.effects.end(eff, "a globe is spent")
            break


def _resolving(ref: str) -> Any:
    """"Secondary Target: each creature in the burst other than the primary."

    The block is the back half of one use of its parent and is never a choice
    of its own, so the gate is "the parent is running now": `dsl._IN_FLIGHT`
    holds `(caster, ref)` for exactly the length of the parent's body. True
    where `c.use_power` reaches for this row and false everywhere a menu is
    built -- and false at the start of a fight, which is what keeps a No
    Action row with no trigger from being armed out of nowhere.
    """

    def check(world: World, eid: int) -> bool:
        from combat_engine.engine.dsl import _IN_FLIGHT

        return (eid, ref) in _IN_FLIGHT

    return check


@power(
    "p464b",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(INT, vs=REF),
    requires=_resolving("p464"),
    requires_text="the p464 power must be resolving",
)
def p464b(c: Cast) -> None:
    """Aimed at the **primary** target and never striking it: the burst is
    centred there and the secondary target line is everything else in it,
    allies included, which is what the row says."""
    primary = c.target
    if primary is None:
        return
    for who in c.within(1, of=primary):
        if who == primary:
            continue
        if c.strike(on=who):
            c.damage("1d8", c.int_mod, dtype=DamageType.ACID, on=who)
            c.ongoing(5, DamageType.ACID, on=who)


@power(
    "p465b",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
    requires=_resolving("p465"),
    requires_text="the p465 power must be resolving",
)
def p465b(c: Cast) -> None:
    """Enemies only, where p464b beside it catches everything in the burst."""
    primary = c.target
    if primary is None:
        return
    for who in c.within(1, of=primary, side="enemy"):
        if who == primary:
            continue
        if c.strike(on=who):
            c.damage("1d10", c.int_mod, dtype=DamageType.FORCE, on=who)


@power(
    "p16281b",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
    requires=_resolving("p16281"),
    requires_text="the p16281 power must be resolving",
)
def p16281b(c: Cast) -> None:
    """Fortitude here where the parent rolled Reflex, which is why this is a
    block of its own rather than a second loop inside it."""
    primary = c.target
    if primary is None:
        return
    for who in sorted(c.within(2, of=primary)):
        if who == primary:
            continue
        if c.strike(on=who):
            c.flat(5, dtype=DamageType.COLD, on=who)
            c.penalty(AC, 2, on=who, until=When.SAVE_ENDS)
