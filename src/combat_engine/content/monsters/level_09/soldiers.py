"""Monster abilities, level 9: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("1d10", 7)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the eight levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE` and
armed once when the fight starts; a mark punished for being ignored watches
`PowerUsed` rather than `AttackDeclared`, because an attack is announced once
per target and a burst that left the marker out would otherwise have read as
several attacks that all did; and a helper written for an earlier level is
imported rather than copied.

Four things this file had to settle.

**An attack whose target is chosen for it.** m659a0 makes every melee swing
inside its aura pick at random. `AttackDeclared.vs` and `AttackDeclared.
target` are both read back now -- `resolve.attack` takes the attacker, the
target and the defence off the event after the interrupt window rather than
off its own parameters -- so a `Window.BEFORE` listener that assigns
`ev.target` genuinely moves the blow. Before that it was decoration.

**An aura that grows and then goes off.** m4846a5 widens m4846a0 over three
of its own turns. `Zone.aura` is the radius and `Zones.refresh` recomputes
the footprint from it, so the ring is resized in place rather than torn down
and rebuilt -- which keeps the zone id the trait's watch is holding, and
keeps the entering and leaving diffs honest.

**Rust.** `_worsen` was written at level 6 for m3063a3's printed sentence
and caps the stack at five one-point penalties, read back off the live
effects rather than counted: the cap is on the item, and a second creature
of this kind eats the same armour. Its companion sentence, the one about a
metal weapon, is already on the blocked list under m3062a0 and is left out
here for the same reason.

**A saving throw against being knocked down.** m4975a5 answers
`ConditionApplied` -- a condition event names its subject `target`, so
`about_me` is false on it forever -- and rolls through `Effects.save`, which
announces the throw and ends the hold. A bare d20 would not have been a
saving throw that anything else could see or change.

Three rows are left out: m2988a3, m3063a1 and m5050a0. See the report.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_06.skirmishers import _in_heavy_armour, _worsen
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import (
    _aura,
    _has_hold,
    _holding,
    _living,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    Usage,
    When,
    Window,
    World,
    candidates,
    get,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    ConditionApplied,
    ForcedMove,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, is_
from combat_engine.engine.triggers import Trigger
from combat_engine.engine.zones import Zone

#: A rusting item is kept as a stack of one-point penalties under a shared
#: label. m3063a3 puts them on and m3063a0 asks whether a creature has any.
_RUST = "rust"


def _ring_of(world: World, owner: int, label: str) -> int | None:
    """The id of a named aura belonging to a creature.

    Auras are looked up by label rather than kept in a closure, because two
    rows on the same stat block have to agree about which ring is meant and
    only one of them created it.
    """
    for eid, zone in world.zones.all():
        if zone.owner == owner and zone.label == label:
            return eid
    return None


def _rusting(c: Cast, who: int) -> bool:
    return any(_RUST in eff.label for eff in c.world.effects.of(who))


def _refuses_the_shove(c: Cast) -> None:
    """Only the shove half of the swarm trait.

    `c.immovable` refuses every kind of forced movement and the printed line
    refuses two of them, so the refusal is written against `ForcedMove`
    itself, which carries the row doing the shoving and can therefore tell a
    sword from a burst. The arrangement m4980a1 and m717a1 settled on.
    """
    me = c.me

    def refuse(ev: ForcedMove) -> None:
        if ev.target != me:
            return
        p = get(getattr(ev, "power", "") or "")
        if p is not None and p.reach.kind in ("melee", "ranged"):
            ev.cancel("a swarm is not shoved by a sword or an arrow")

    c.watch(
        ForcedMove,
        refuse,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


# ==========================================================================
# m122
# ==========================================================================


@power(
    "m122a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m122a0(c: Cast) -> None:
    """The escape DC is the grab's own, worked out from the creature rather
    than printed on the card, so the hold is all there is to write."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m122a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d12", 8),
    requires=_has_hold,
    requires_text="the m122 must be grabbing a creature",
)
def m122a1(c: Cast) -> None:
    """"One creature grabbed by the m122" is narrower than any target line
    the header can say, so the Requirement carries the half of it that is
    about the caster and the body picks from what it actually has hold of --
    rather than letting `_auto_targets` choose whoever is nearest."""
    held = sorted(_holding(c))
    victim = c.choose(held, "m122a1: which of them it crushes") if held else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(until=When.EONT, on=victim)


# ==========================================================================
# m2988
# ==========================================================================


@power(
    "m2988a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 7),
)
def m2988a0(c: Cast) -> None:
    """"It cannot stand up" is `Condition.PINNED`, which is what `c.prone`
    hangs on its `held` argument: the creature is prone for as long as prone
    normally lasts and may not do the one thing that ends it. Here the target
    is already down, so only the second half is applied."""
    if c.strike():
        c.hit()
        c.mark()
        if c.is_(Condition.PRONE):
            c.condition(Condition.PINNED, until=When.EONT)


@power(
    "m2988a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d6", 3, kind=LIMITED),
)
def m2988a1(c: Cast) -> None:
    """A shove, and then it follows the falling body and hits it again.

    The step is `_shift_beside` rather than `c.shift`, which picks its own
    destination through the decider: the printed line says it closes on the
    creature it just pushed two squares away, and a step that went anywhere
    else would put the second blow out of reach. The second blow is the row
    that prints it, so its damage line stays in one place.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(2)
    c.prone()
    _shift_beside(c, victim, 2)
    use(c.world, c.me, "m2988a0", targets=[victim], spend=False)
    c.note("m2988a1: when charging, it may swing this in place of a melee basic attack")


@power(
    "m2988a2",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2988a2(c: Cast) -> None:
    """`c.resist` with no damage type is resist-all, which is the printed
    line; before it existed this had to be written as a negative
    vulnerability against each of the eleven types in turn."""
    c.resist(5, until=When.EONT)


# ==========================================================================
# m3063
# ==========================================================================


@power(
    "m3063a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3063a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and a toll for ending a turn in it.

    Not the aura helper, whose hold is carried for as long as its owner is
    standing inside: this one bites once at a boundary, so membership is
    measured at that moment. Whether the victim has anything rusting is read
    off its live effects, which is where m3063a1 and m3063a3 leave it.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def gnaw(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) > 1:
            return
        c.flat(5, on=ev.actor)
        if _rusting(c, ev.actor):
            c.slowed(until=When.EOT, on=ev.actor)

    c.watch(TurnEnd, gnaw, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3063a2",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3063a2(c: Cast) -> None:
    """Only the shove half of the swarm trait.

    Not written: sharing a square with another creature, an enemy entering
    that square and finding it difficult, and squeezing through gaps. All
    three are facts about occupancy that the grid decides, and no `Cast`
    method reaches them. See the report.
    """
    _refuses_the_shove(c)


@power(
    "m3063a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d8", 4),
)
def m3063a3(c: Cast) -> None:
    """Heavy armour is chain, scale or plate -- `chargen.LIGHT` names the
    other three, and `Gear.armour` is the only place a creature says which
    it wears."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and _in_heavy_armour(c, victim):
            _worsen(c, victim, AC, f"{c.ref} {_RUST}")


# ==========================================================================
# m3095
# ==========================================================================


@power(
    "m3095a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3095a0(c: Cast) -> None:
    """An aura whose occupants carry the penalty while they stand in it, so
    the aura helper is the right one here: membership is diffed by the zone
    and the hold goes on and comes off with it."""
    me = c.me
    _aura(
        c,
        1,
        lambda who: who != me and who in c.enemies() and _living(c, who),
        lambda who: c.penalty("attack", 2, on=who, until=When.ENCOUNTER),
    )


@power(
    "m3095a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m3095a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3095a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6),
)
def m3095a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3095a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d10", 6),
)
def m3095a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3095a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d10", 9, kind=LIMITED, half_on_miss=True),
)
def m3095a4(c: Cast) -> None:
    """"Creatures in the burst" is everything caught, not only enemies."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m4846
# ==========================================================================
#
# The card names the aura by a shorter id belonging to a different stat
# block in two of its rows. The ring every sentence plainly means is
# m4846a0's, and that is the one written.


#: The label m4846a0's ring is filed under, and what m4846a5 and m4846a6
#: look it up by.
_M4846_RING = "m4846a0"


@power(
    "m4846a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4846a0(c: Cast) -> None:
    """Look away from it inside the ring and the ground takes your feet.

    Off `PowerUsed` rather than `AttackDeclared`: an attack is announced
    once per target, so a burst that caught three allies and not this
    creature would have read as three attacks that all left it out, and the
    toll would have been paid three times. `PowerUsed` fires once per use
    and carries the whole target list, which is the printed question.

    Membership is read off the zone rather than measured, because m4846a5
    widens this same ring to three and then to five and a hard-coded one
    square would have ignored it.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def looked_away(ev: PowerUsed) -> None:
        if ev.actor == me or me in ev.targets:
            return
        p = get(ev.power)
        if p is None or not p.is_attack:
            return
        if ev.actor not in c.enemies() or ev.actor not in c.world.zones.occupants(ring):
            return
        c.prone(on=ev.actor)
        c.flat(5, on=ev.actor)

    c.watch(PowerUsed, looked_away, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4846a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m4846a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4846a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m4846a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4846a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m4846a3(c: Cast) -> None:
    """One of each or two of the second -- the printed line offers a choice,
    and the rows that print the blows are used rather than copied. Declared
    with no target: each blow picks its own, and nothing says they are the
    same creature."""
    pair = ("m4846a1", "m4846a2") if c.may("open with the heavier blow") else (
        "m4846a2",
        "m4846a2",
    )
    for ref in pair:
        use(c.world, c.me, ref, spend=False)


@power(
    "m4846a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m4846a4(c: Cast) -> None:
    """Stone closes round it, and turns to stone on the first failed save.

    "First Failed Saving Throw" is `escalate`, which runs on every failed
    save -- so the step ends the hold it came from and applies one carrying
    no escalation of its own, and the chain can only ever fire once. The new
    condition *replaces* the old, which is what "instead" says; two holds
    would be two saving throws against one grip.
    """

    def petrify(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, escalate=petrify)


@power(
    "m4846a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=1,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m4846a5(c: Cast) -> None:
    """The ring widens over two turns and then the ground goes.

    `Zone.aura` is the radius and `Zones.refresh` recomputes the footprint
    from it, so the ring is resized in place: the id stays the one
    m4846a0's watch is holding, and the entering and leaving diffs stay
    honest. Making a second zone would have left the trait reading the old
    one and the board drawing both.

    Declared with no target because the burst goes off two turns after the
    row is used, and a header's target list is chosen when the row runs --
    it would have caught whoever was standing there at the start.

    "Recharge at the start of any turn when the ring is back to aura 1" is
    the header's 1, which recharges on any roll: the ring is only ever back
    at one when this has finished, and the row cannot be started again
    while it is running because it is already spent.
    """
    me = c.me
    found = _ring_of(c.world, me, _M4846_RING)
    if found is None:
        return
    ring = c.world.get(found, Zone)
    if ring is None:
        return
    ring.aura = 3
    c.world.zones.refresh()
    beats: list[int] = []
    held: list[Effect] = []

    def grows(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        beats.append(1)
        if len(beats) == 1:
            ring.aura = 5
            c.world.zones.refresh()
            return
        for foe in list(c.world.zones.occupants(found)):
            if foe not in c.enemies():
                continue
            if c.strike(on=foe):
                c.hit(on=foe)
                c.prone(on=foe, held=When.SAVE_ENDS)
        ring.aura = 1
        c.world.zones.refresh()
        for watcher in held:
            c.world.effects.end(watcher, "the ground settles")

    held.append(c.watch(TurnStart, grows, until=When.ENCOUNTER, on=me, label=c.ref))


_M4846_SHOVED = "the m4846 is pulled, pushed, slid, or knocked prone"


def _shoved(world: World, me: int, ev: ForcedMove) -> bool:
    return ev.target == me


def _floored(world: World, me: int, ev: ConditionApplied) -> bool:
    """`ev.target`, not `ev.actor`: a condition event names its subject
    `target` and a predicate reading `actor` here is false forever."""
    return ev.target == me and ev.condition is Condition.PRONE


@power(
    "m4846a6",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4846_SHOVED,
    on=[
        Trigger(ForcedMove, when=_shoved, text="the m4846 is pulled, pushed or slid"),
        Trigger(ConditionApplied, when=_floored, text="the m4846 is knocked prone"),
    ],
)
def m4846a6(c: Cast) -> None:
    """A printed line naming four things declares all four: `on=` takes a
    sequence, and half of it would have looked finished."""
    found = _ring_of(c.world, c.me, _M4846_RING)
    if found is None:
        return
    for foe in c.world.zones.occupants(found):
        if foe in c.enemies():
            c.prone(on=foe)


# ==========================================================================
# m4975
# ==========================================================================


@power(
    "m4975a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4975a0(c: Cast) -> None:
    """The ring that bogs enemies down, and the one m4975a4 watches the edge
    of. Its label is this row's ref, which is how the other row finds it."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def mire(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, mire, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4975a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4975a1(c: Cast) -> None:
    """Two bonuses on one effect, because the printed line gives them one
    ending. `kind="power"` because the card says power bonus, and two
    bonuses of one kind do not add -- the larger wins -- so naming the kind
    is what makes this behave beside somebody else's."""
    me, ref = c.me, c.ref

    def banner(who: int) -> Effect | None:
        return c.world.effects.apply(
            who,
            me,
            When.ENCOUNTER,
            label=f"{ref} banner",
            mods=[
                (who, Mod(what=AC.value, value=2, kind="power", label=ref)),
                (who, Mod(what=FORT.value, value=2, kind="power", label=ref)),
            ],
        )

    _aura(c, 1, lambda who: who != me and who in c.allies(), banner)


@power(
    "m4975a2",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4975a2(c: Cast) -> None:
    """One square less of every shove, which is exactly `c.resist_forced`."""
    c.resist_forced(1)


@power(
    "m4975a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 7),
)
def m4975a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


_M4975_ESCAPED = "an enemy marked by the m4975 leaves its aura"


def _marked_leaves_the_ring(world: World, me: int, ev: ZoneExited) -> bool:
    ring = _ring_of(world, me, "m4975a0")
    return (
        ring is not None
        and ev.zone == ring
        and ev.actor != me
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
    )


@power(
    "m4975a4",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
    trigger=_M4975_ESCAPED,
    on=Trigger(ZoneExited, when=_marked_leaves_the_ring, text=_M4975_ESCAPED),
)
def m4975a4(c: Cast) -> None:
    """It follows whoever tried to walk out of its shadow.

    `ZoneExited` names the ring as well as the creature, so "leaves the
    m4975a0 aura" is asked of the zone the other row made rather than
    approximated as a distance. Declared with no target: the step comes
    first and the creature is out of reach until it has been taken, so a
    header target line would have been refused before the row ever ran.

    Filed as a free action and printed as an immediate reaction; the Effect
    line is what says which it is.
    """
    prey = getattr(c.trigger, "actor", None)
    if prey is None:
        return
    _shift_beside(c, prey, 1)
    if c.strike(on=prey):
        c.hit(on=prey)
        c.flat(5, dtype=DamageType.NECROTIC, on=prey)
        c.immobilized(until=When.EONT, on=prey)


_M4975_FLOORED = "an effect knocks the m4975 prone"


@power(
    "m4975a5",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4975_FLOORED,
    on=Trigger(ConditionApplied, when=_floored, text=_M4975_FLOORED),
)
def m4975a5(c: Cast) -> None:
    """A real saving throw, through `Effects.save`, which announces it and
    ends the hold on a success -- a bare d20 would be a throw nothing else
    could see or change.

    `c.save` is not the door here: it looks for a save-ends effect, and
    prone hangs on the encounter clock because it lasts until the creature
    stands rather than until a turn boundary.
    """
    for held in list(c.world.effects.of(c.me)):
        if Condition.PRONE in held.conditions:
            c.world.effects.save(held)
            return


# ==========================================================================
# m5050
# ==========================================================================


@power(
    "m5050a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5050a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


_M5050_IGNORED = "an enemy marked by the m5050 attacks without including it"


def _marked_looks_away(world: World, me: int, ev: PowerUsed) -> bool:
    """A use of an attack that left this creature out.

    Off `PowerUsed` rather than `AttackDeclared`, for the reason m4918a4
    settled one level down: an attack is announced once per target, so a
    burst that caught three allies and not the marker read as three attacks
    that all left it out.
    """
    p = get(ev.power)
    return (
        ev.actor != me
        and p is not None
        and p.is_attack
        and me not in ev.targets
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 2
    )


@power(
    "m5050a2",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
    trigger=_M5050_IGNORED,
    on=Trigger(PowerUsed, when=_marked_looks_away, text=_M5050_IGNORED),
)
def m5050a2(c: Cast) -> None:
    """Declared with no target, so the aim is the event's and only the
    event's: the printed target is the triggering enemy and nobody else in
    reach."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.push(1, on=foe)
    c.prone(on=foe)


# ==========================================================================
# m659
# ==========================================================================


@power(
    "m659a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m659a0(c: Cast) -> None:
    """Nobody beside it can tell what they are swinging at.

    `AttackDeclared.target` is read back by `resolve.attack` after the
    interrupt window closes, so assigning it here genuinely moves the blow;
    that field was announced and ignored until this month. The new target is
    drawn from `candidates`, which is the engine's own answer to "what could
    this row be aimed at from here" -- the printed "potential targets in
    range".

    Melee only, and read through the branch, because a `MeleeOrRanged` row's
    range line says melee whichever half swung.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def scramble(ev: AttackDeclared) -> None:
        if ev.attacker == me or ev.attacker not in c.world.zones.occupants(ring):
            return
        if _reach_kind(ev) != "melee":
            return
        p = get(ev.power)
        if p is None:
            return
        pool = sorted(
            candidates(c.world, ev.attacker, p, branch=getattr(ev, "branch", 0))
        )
        if len(pool) > 1:
            ev.target = c.world.rng.choice(pool)

    c.watch(
        AttackDeclared,
        scramble,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


@power(
    "m659a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m659a1(c: Cast) -> None:
    """Reaching into this mind hurts both of them.

    On the declaration rather than on the hit: the printed line is
    "whenever a creature **targets** it", which happens whether or not the
    charm lands.
    """
    me = c.me

    def backlash(ev: AttackDeclared) -> None:
        if ev.target != me:
            return
        p = get(ev.power)
        if p is None or Keyword.CHARM not in p.keywords:
            return
        c.flat(10, dtype=DamageType.PSYCHIC, on=ev.attacker)
        c.flat(10, dtype=DamageType.PSYCHIC, on=me)

    c.watch(AttackDeclared, backlash, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m659a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m659a2(c: Cast) -> None:
    """"+14, or +16 while bloodied" as one roll with two bonuses, not a
    modifier: `c.bonus` of the same kind does not add -- the larger wins --
    and the two-point difference written as a gated bonus beside the
    header's own would have been invisible. `c.strike(plus=...)` is the
    printed arithmetic, and the four extra damage is a second packet on top
    of the header's line, which is what keeps the header rescalable.
    """
    hard = c.bloodied(c.me)
    if c.strike(plus=2 if hard else 0):
        c.hit()
        if hard:
            c.flat(4)


@power(
    "m659a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m659a3(c: Cast) -> None:
    """A charge with five more damage on it.

    `c.charge_at` marks the swing as a charge, which is what puts `charge`
    in the damage context -- so the rider is a gated modifier rather than
    something put on and taken off around the blow. Lifted afterwards all
    the same, because the printed five is this row's and not every charge's.

    The nearest enemy is offered first: a charge that cannot reach is no
    charge at all.
    """
    me = c.me
    near = sorted(c.enemies(), key=lambda foe: (c.distance(foe), foe))
    victim = c.choose(near, "m659a3: which enemy it charges") if near else None
    if victim is None:
        return
    rider = c.bonus(
        "damage",
        5,
        until=When.EOT,
        on=me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("charge")),
    )
    try:
        c.charge_at(victim)
    finally:
        if rider is not None:
            c.world.effects.end(rider, "the charge is over")


# ==========================================================================
# m731
# ==========================================================================


@power(
    "m731a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 2),
)
def m731a0(c: Cast) -> None:
    """Two packets of different types, so the second is rolled here: the
    header keeps the printed line that rescales, and fire that a resistance
    can read cannot ride along inside an untyped one."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.FIRE)


@power(
    "m731a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d10", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m731a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


# ==========================================================================
# m80
# ==========================================================================
#
# Two of this card's sentences spell the creature's id as a shorter one
# belonging to a different stat block. This creature is the one they plainly
# mean, and is the one written.


@power(
    "m80a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m80a0(c: Cast) -> None:
    """"Loses a healing surge" is `c.spend_surge`, which takes one and hands
    nothing back -- `c.surge` would heal the victim for it."""
    if c.strike():
        c.hit()
        c.spend_surge()
        c.immobilized(until=When.EONT)


def _an_immobilized_enemy(world: World, eid: int) -> bool:
    return any(
        is_(world, foe, Condition.IMMOBILIZED) and distance_between(world, eid, foe) <= 5
        for foe in enemies(world, eid)
    )


@power(
    "m80a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d8", 9, dtype=DamageType.NECROTIC, kind=LIMITED),
    requires=_an_immobilized_enemy,
    requires_text="an immobilized creature must be within 5 squares",
)
def m80a1(c: Cast) -> None:
    """"One immobilized creature" is narrower than the header's target line
    can say, so the Requirement carries whether there is one at all and the
    body picks from the ones there are -- rather than letting
    `_auto_targets` choose whoever is nearest and miss the point of the
    row."""
    held = sorted(
        foe
        for foe in c.enemies()
        if c.is_(Condition.IMMOBILIZED, on=foe) and c.distance(foe) <= 5
    )
    victim = c.choose(held, "m80a1: which held creature") if held else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(10, on=c.me)
