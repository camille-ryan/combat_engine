"""Monster abilities, level 10: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=13)` and `Damage("2d10", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the nine levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits and are written as such; a stat block printing no range at
all means melee 1; and a helper written for an earlier level is imported
rather than copied.

Five things this file had to settle.

**A monster spends a healing surge only when its row says so.** None of
these rows says so, and none of them takes a second wind either -- the
surge each monster carries is there for a leader line to spend, and m396a0
is a leader whose printed aura heals a flat five rather than a surge. It is
written as the flat five.

**An aura that grows and then goes off.** m3450a4 widens m3450a0 over three
of its own turns, the shape level 9 settled: `Zone.aura` is the radius and
`Zones.refresh` recomputes the footprint from it, so the ring is resized in
place and keeps the id the trait's watch is holding.

**Ongoing damage that gets worse on every failed save** is `escalate`, which
runs on a failed save and is handed the effect. m4982a3 steps 10 to 15 to
20 by ending the hold it came from and applying the next one, so the victim
never carries two burns for one printed sentence.

**"An enemy adjacent to it shifts" is an interrupt on `MoveStart`.** That is
the one event emitted while the creature is still in the square it is
leaving, which is where the printed adjacency is measured; `MoveEnd` would
answer from after the step, by which time the shift has already carried it
out of reach. The warning that `MoveStart` is too early is about reactions
that need the move to have happened -- this one needs the opposite.

**`Bloodied` about itself cannot fire on the audit board**, which sets the
caster to half hit points before the fight starts. m2931a1 and m3043a2 are
both such rows and report UNUSED however correct they are; both were driven
by hand, at full health, to check. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import (
    _has_hold,
    _holding,
    _is_bloodied,
)
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.content.monsters.level_09.soldiers import _refuses_the_shove, _ring_of
from combat_engine.content.monsters.level_10.soldiers import _qualified_rider
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Budget,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Dropped,
    Effect,
    Health,
    Hit,
    Ident,
    Keyword,
    Melee,
    Movement,
    PowerUsed,
    Ranged,
    Relation,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    both,
    by_keyword,
    get,
    power,
    targets_me,
    use,
)
from combat_engine.engine.events import MoveStart, TurnEnd
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between
from combat_engine.engine.triggers import Trigger, about_me
from combat_engine.engine.zones import Zone

#: The label m3450a0's ring is filed under, and what m3450a4 and m3450a6
#: look it up by. Auras are found by label rather than kept in a closure,
#: because three rows on one stat block have to agree which ring is meant
#: and only one of them made it.
_M3450_RING = "m3450a0"

#: m2931a1's temporary hit points, and the label of the hold that watches
#: for them still being there a turn later.
_M2931_TEMP = 20
_M2931_SURGE = "m2931a1 surge"


def _bloodied_target(c: Cast, ctx: dict[str, Any]) -> bool:
    """Is the creature this modifier is being read for a bloodied one?

    Both the attack and the damage context carry `target`, which is the only
    place the creature being swung at appears -- a gate on a key the context
    does not carry is silently false rather than an error.
    """
    victim = ctx.get("target")
    return victim is not None and _is_bloodied(c.world, victim)


def _same_stock(world: World, me: int, other: int) -> bool:
    """Is that another creature off this one's own stat block?

    `Ident.ref` is the compendium id the loader spawned it from, and the
    only thing on the board that says two creatures are the same sort.
    """
    mine, theirs = world.get(me, Ident), world.get(other, Ident)
    return mine is not None and theirs is not None and mine.ref == theirs.ref


def _worsening_burn(c: Cast, who: int, amount: int) -> None:
    """Ongoing damage that steps up on each failed save.

    `escalate` runs on a *failed* save and is handed the effect, so the step
    ends the hold it came from and applies the next one. Two holds would be
    two saving throws against one printed sentence, and the last step
    carries no escalation of its own, so the chain stops where the card
    stops.
    """
    nxt = {10: 15, 15: 20}.get(amount)

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        if nxt is not None:
            _worsening_burn(c, eff.owner, nxt)

    c.condition(
        until=When.SAVE_ENDS,
        on=who,
        ongoing=(amount, DamageType.UNTYPED),
        escalate=worsen if nxt is not None else None,
    )


# ==========================================================================
# m2931
# ==========================================================================


_M2931_BLED = "the m2931 is first bloodied"


@power(
    "m2931a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 6),
)
def m2931a0(c: Cast) -> None:
    """Bloodied is asked after the blow, not before: a hit that bloodies the
    target is a hit on a bloodied target by the time the rider applies."""
    if c.strike():
        c.hit()
        if c.bloodied():
            c.prone()


@power(
    "m2931a1",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2931_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2931_BLED),
)
def m2931a1(c: Cast) -> None:
    """Stone closes over the wound, and then it comes off in a rush.

    "First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.

    An action point is an extra action taken on the turn it is spent, and
    `Budget` is where a turn's actions live -- so the point is a standard
    added to the budget of the turn that starts with the stone still on. It
    does not carry: the printed line says it must be used that turn, and the
    next turn's `refresh` takes it away whether or not it was.
    """
    me = c.me
    c.temp_hp(_M2931_TEMP, on=me)

    def crack(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is None or health.temp <= 0:
            return
        health.temp = 0
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard += 1

    c.watch(TurnStart, crack, until=When.ENCOUNTER, on=me, label=_M2931_SURGE)


# ==========================================================================
# m3043
# ==========================================================================


_M3043_BLED = "the m3043 is first bloodied"


@power(
    "m3043a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m3043a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and a toll for starting a turn in it.

    Not the aura helper, whose hold is carried for as long as its owner
    stands inside: this one bites once at a boundary, so membership is
    measured at that moment.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def sting(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(5, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnStart, sting, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3043a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m3043a1(c: Cast) -> None:
    """"Ongoing 5 poison and slowed (save ends both)" is one effect carrying
    both: applied separately the victim gets two saving throws and can shake
    off half of a thing the card prints as one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m3043a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger=_M3043_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M3043_BLED),
)
def m3043a2(c: Cast) -> None:
    """A triggered burst picks its own targets: the dispatcher only aims a
    row that takes a single enemy, which this does not."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m3069
# ==========================================================================
#
# Most of this card's sentences spell the creature's id as one belonging to
# a different stat block. This creature is the one they plainly mean.


def _hands_empty(world: World, eid: int) -> bool:
    """The printed Requirement on m3069a1: not already holding somebody."""
    return not _has_hold(world, eid)


@power(
    "m3069a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m3069a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3069a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 7),
    requires=_hands_empty,
    requires_text="the m3069 must not be grabbing a creature",
)
def m3069a1(c: Cast) -> None:
    """A charge whose blow is this row's own line.

    `c.charge_at` reaches the swing through `use`, and `use` refuses to
    re-enter a row already in flight -- which a row that *is* the charge
    always is. So the flag goes up by hand and comes back down after, since
    it is what puts `charge` on the attack events and in the modifier
    contexts every charge rider reads.

    "When the grab ends, the target takes ongoing 5" is a clock no duration
    names, so the burn is hung on the hold's own ending: whatever lets go --
    a save, an escape, m3069a3, a death -- starts it.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    try:
        c.run_at(victim)
        if not c.strike(on=victim):
            return
        c.hit(on=victim)
        hold = c.grab(on=victim)
    finally:
        c.charge = False
    if hold is not None:
        hold.on_end.append(lambda: c.ongoing(5, on=victim))


@power(
    "m3069a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    damage=Damage("3d8", 7),
    requires=_has_hold,
    requires_text="the m3069 must be grabbing a creature",
)
def m3069a2(c: Cast) -> None:
    """No attack roll is printed: it already has hold of the thing. "A
    creature grabbed by the m3069" is narrower than any `Target` can say, so
    the Requirement carries the caster's half and the body picks."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m3069a2: which of them it tears at") if held else None
    if victim is not None:
        c.hit(on=victim)


@power(
    "m3069a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3069a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: nobody chooses it.

    A compulsion rather than an offer -- the printed line says *must* -- so
    it is a watch on its own turn beginning rather than a declared trigger,
    which the dispatcher would properly offer as a choice and allow it to
    decline.

    The grab ends by ending the hold that carries it, so the ongoing damage
    m3069a1 hung on that hold starts, which is what the two sentences
    together say.
    """
    me = c.me

    def frenzy(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if not any(c.bloodied(foe) and c.distance(foe) <= 5 for foe in c.enemies()):
            return
        for who in sorted(_holding(c.world, me)):
            for eff in list(c.world.effects.of(who)):
                if any(
                    kind is Relation.GRABBED_BY and source == me
                    for kind, source, _target in eff.relations
                ):
                    c.world.effects.end(eff, c.ref)
        near = sorted(foe for foe in c.enemies() if c.adjacent(foe))
        if near:
            use(c.world, me, "m3069a0", targets=[near[0]], spend=False)

    c.watch(TurnStart, frenzy, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3069a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3069a4(c: Cast) -> None:
    """Whether the fight is being had in water is asked inside the gate
    rather than once when the trait arms: it answers False in an ordinary
    fight, which is the whole reason the check is written out."""
    me = c.me

    def out_of_its_element(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not c.terrain("aquatic"):
            return False
        swims = c.world.get(who, Movement)
        return swims is None or "swim" not in swims.modes

    c.bonus("damage", 2, until=When.ENCOUNTER, on=me, when=out_of_its_element)


# ==========================================================================
# m3450
# ==========================================================================


_M3450_BURNED = "the m3450 is hit by a fire attack"


@power(
    "m3450a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m3450a0(c: Cast) -> None:
    """The ring the other two rows are about.

    Membership is read off the zone rather than measured, because m3450a4
    widens this same ring to three and then to five and a hard-coded one
    square would have ignored it.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def sting(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, sting, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3450a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 4),
)
def m3450a1(c: Cast) -> None:
    """Only the burn is printed as fire; the declared line is untyped, so the
    header carries no type and the ongoing names one."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m3450a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m3450a2(c: Cast) -> None:
    """Losing a resistance is gaining its negative for a while.

    `c.resist` adds to `Defences.resist` and puts back exactly what it took
    when the hold runs out, so how much the victim had is read first and
    handed back as a negative of the same size. Nothing happens to a
    creature that had none, which is the printed outcome.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    shield = c.world.get(victim, Defences)
    had = shield.resist.get(DamageType.FIRE, 0) if shield is not None else 0
    if had > 0:
        c.resist(-had, DamageType.FIRE, until=When.EONT, on=victim)


@power(
    "m3450a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m3450a3(c: Cast) -> None:
    """One of each or two of the second -- the printed line offers a choice,
    and the rows that print the blows are used rather than copied. Declared
    with no target: each blow picks its own, and nothing says they are the
    same creature."""
    pair = ("m3450a1", "m3450a2") if c.may("open with the burning claw") else (
        "m3450a2",
        "m3450a2",
    )
    for ref in pair:
        use(c.world, c.me, ref, spend=False)


@power(
    "m3450a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=1,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3450a4(c: Cast) -> None:
    """The ring widens over two turns and then goes off.

    `Zone.aura` is the radius and `Zones.refresh` recomputes the footprint
    from it, so the ring is resized in place: the id stays the one m3450a0's
    watch is holding, and the entering and leaving diffs stay honest. A
    second zone would leave the trait reading the old one and the board
    drawing both.

    Declared with no target because the burst goes off two turns after the
    row is used, and a header's target list is chosen when the row runs -- it
    would have caught whoever was standing there at the start.

    "Recharge at the start of any turn when the ring is back to aura 1" is
    the header's 1, which recharges on any roll: the ring is only ever back
    at one when this has finished, and the row cannot be started again while
    it is running because it is already spent.
    """
    me = c.me
    found = _ring_of(c.world, me, _M3450_RING)
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
                c.ongoing(5, DamageType.FIRE, on=foe)
        ring.aura = 1
        c.world.zones.refresh()
        for watcher in held:
            c.world.effects.end(watcher, "the fire settles")

    held.append(c.watch(TurnStart, grows, until=When.ENCOUNTER, on=me, label=c.ref))


@power(
    "m3450a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE],
)
def m3450a5(c: Cast) -> None:
    """Burning ground. `c.burns` is exactly the printed toll -- enter it or
    start a turn in it -- and it bites once a turn, which a zone plus two
    hand-written watches would have had to get right by itself.

    "Recharge when first bloodied" is a board state rather than a die. The
    number stays in the header, because that is what the card shows and what
    `actions.recharge` rolls; this is the printed sentence on top of it, and
    the two only ever agree to give the row back sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: getattr(ev, "actor", None) == me)
    zid = c.zone(c.area(), until=When.ENCOUNTER)
    c.burns(zid, 5, DamageType.FIRE)


@power(
    "m3450a6",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M3450_BURNED,
    on=Trigger(Hit, when=both(targets_me, by_keyword(Keyword.FIRE)), text=_M3450_BURNED),
)
def m3450a6(c: Cast) -> None:
    """Whoever is standing in the cloud pays for hitting it with fire.

    The ring is found by label rather than measured, because m3450a4 may
    have it out at three or five squares when this fires.
    """
    found = _ring_of(c.world, c.me, _M3450_RING)
    if found is None:
        return
    for foe in c.world.zones.occupants(found):
        if foe in c.enemies():
            c.flat(5, dtype=DamageType.FIRE, on=foe)


# ==========================================================================
# m396
# ==========================================================================


@power(
    "m396a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m396a0(c: Cast) -> None:
    """A flat five rather than a healing surge: the printed line says the
    number, and a monster spends a surge only when its row says surge.

    Membership is read off the zone the aura made, so the ring the board
    draws and the ring the toll is paid in are the same object.
    """
    me = c.me
    ring = c.aura(10, until=When.ENCOUNTER)

    def mend(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.allies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        if any(
            c.bloodied(foe) and distance_between(c.world, ev.actor, foe) <= 1
            for foe in c.enemies()
        ):
            c.heal(5, on=ev.actor)

    c.watch(TurnStart, mend, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m396a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m396a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m396a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m396a2(c: Cast) -> None:
    """Two gated modifiers rather than two holds put on and taken off as
    creatures bleed: being bloodied changes both ways, and the gate is asked
    as the roll is made. Attack and damage are different `what`s, so the two
    never contend."""
    me = c.me
    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=lambda ctx: _bloodied_target(c, ctx))
    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=lambda ctx: _bloodied_target(c, ctx))


@power(
    "m396a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 6),
)
def m396a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m396a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4),
)
def m396a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m396a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 6),
)
def m396a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m396a6",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m396a6(c: Cast) -> None:
    """The card names the first of the three blows by a word rather than an
    id. Two of this creature's rows carry that keyword and the same line;
    the one this routine plainly means is the melee half, because the other
    two blows are melee and a routine that opened at five squares could not
    reach with either of them.

    Declared with no target: each blow picks its own, and nothing says they
    are the same creature.
    """
    for ref in ("m396a3", "m396a4", "m396a4"):
        use(c.world, c.me, ref, spend=False)


# ==========================================================================
# m4982
# ==========================================================================
#
# The aura sentence spells the creature's id as a shorter one belonging to a
# different stat block. This creature is the one it plainly means.


@power(
    "m4982a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4982a0(c: Cast) -> None:
    """Ten, and two more for every other one of these pressed against you.

    "Additional" counts the swarms beside the victim other than this one, so
    the toll rises as they close in. Two creatures are the same sort when
    `Ident.ref` says so, which is the only thing on the board that does.
    """
    me = c.me

    def swarm(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) > 1:
            return
        crowd = sum(
            1
            for other in c.within(1, of=ev.actor, side="any")
            if other != me and _same_stock(c.world, me, other)
        )
        c.flat(10 + 2 * crowd, on=ev.actor)

    c.watch(TurnStart, swarm, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4982a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4982a1(c: Cast) -> None:
    """Only the shove half of the swarm trait.

    Not written: sharing a square with another creature, an enemy entering
    that square and finding it difficult, and squeezing through gaps. All
    three are facts about occupancy that the grid decides, and no `Cast`
    method reaches them -- the same three left out of every swarm below.
    """
    _refuses_the_shove(c)


@power(
    "m4982a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4982a2(c: Cast) -> None:
    """`c.no_basic` takes away what this creature's basic attack *is* rather
    than its ability to use the row -- which is the printed sentence, and is
    what an opportunity attack and a granted swing both reach for."""
    c.no_basic()


@power(
    "m4982a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
)
def m4982a3(c: Cast) -> None:
    """No damage on the hit at all: the burn is the whole of it, which is why
    the header carries no damage line."""
    victim = c.target
    if victim is not None and c.strike():
        _worsening_burn(c, victim, 10)


@power(
    "m4982a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=13),
)
def m4982a4(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.EONT)


@power(
    "m4982a5",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    once_per_round=True,
)
def m4982a5(c: Cast) -> None:
    if c.strike():
        c.pull(4)


# ==========================================================================
# m4983
# ==========================================================================


_M4983_FELLED = "the m4983 drops to 0 hit points"


@power(
    "m4983a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 11, kind=MINION),
)
def m4983a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4983a1",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.ZONE],
    trigger=_M4983_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4983_FELLED),
)
def m4983a1(c: Cast) -> None:
    """A death throe: the cloud is what is left where it stood.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape -- and the squares are read while the
    body is still on the board, which is the only moment there are any.

    Not `c.burns`, which bites on entering and at the start of a turn: the
    printed toll is at the *end* of a turn, so the watch is written out.

    Lightly obscured is not written. `blocks_sight` is the only thing a zone
    has and it is total concealment, which is two steps heavier than the
    printed line. See the report.
    """
    here = c.area()
    if not here:
        return
    zid = c.zone(here, until=When.ENCOUNTER)

    def linger(ev: TurnEnd) -> None:
        if ev.ghost:
            return
        if ev.actor in c.world.zones.occupants(zid):
            c.flat(10, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, linger, until=When.ENCOUNTER, on=c.me, label=c.ref)
    c.note("m4983a1: the cloud is lightly obscured")


# ==========================================================================
# m707
# ==========================================================================


_M707_SHIFTED = "an enemy adjacent to the m707 shifts"


def _neighbour_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """`MoveStart`, because this one is an interrupt.

    It is the only event emitted while the creature is still standing in the
    square it is leaving, which is where the printed adjacency is measured.
    `MoveEnd` answers from after the step, by which time the shift has
    carried it out of reach and the row would fire on nobody.
    """
    from combat_engine.engine.query import team

    if ev.kind_ != "shift" or ev.actor == me:
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    return distance_between(world, me, ev.actor) <= 1


@power(
    "m707a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 2),
)
def m707a0(c: Cast) -> None:
    """Two swings at the same creature, and a critical that pays differently.

    The printed "1d8 + 10 if it scores a critical hit" is not the ordinary
    crit: `c.damage` already maxes the die, so the eight the bonus grows by
    is added on top rather than the line being rolled again -- rolling it
    again inside the crit branch would max a second die and pay eighteen
    twice over.
    """
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        if not alive(c.world, victim):
            return
        if c.strike(on=victim):
            c.hit(on=victim)
            if c.crit:
                c.flat(8, on=victim)


@power(
    "m707a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m707a1(c: Cast) -> None:
    """Nothing rides on whether either landed, so the row that prints the
    blows is simply used twice rather than counted off the bus."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m707a0", targets=[victim], spend=False)


@power(
    "m707a2",
    level=10,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 2),
    trigger=_M707_SHIFTED,
    on=Trigger(MoveStart, when=_neighbour_shifts, text=_M707_SHIFTED),
)
def m707a2(c: Cast) -> None:
    """The swing is this row's own line rather than m707a0 used again.

    m707a0 swings twice by itself and this printed line is one use of it, so
    reaching through `use` would double the interrupt as well -- and the
    interrupt resolves before the shift, which is what makes the target
    still be standing there.
    """
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        if c.crit:
            c.flat(8, on=victim)


# ==========================================================================
# m87
# ==========================================================================


@power(
    "m87a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m87a0(c: Cast) -> None:
    """"Ongoing 5 poison and weakened (save ends both)" is one effect
    carrying both, or the victim gets two saving throws against one printed
    sentence."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.WEAKENED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m87a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.POISON],
)
def m87a1(c: Cast) -> None:
    """The printed Effect does not say whether the two land on one creature
    or two, so the header takes up to two and a single target is bitten
    twice -- the only reading that loses nothing."""
    if c.target is not None:
        _volley(c, "m87a0", c.target)


@power(
    "m87a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
    requires_text="the m87 must be carrying a friendly rider of 10th level or higher",
)
def m87a2(c: Cast) -> None:
    """Filed as an encounter attack and plainly a trait: nobody chooses it,
    it answers a blow the rider has already struck.

    The bite is declared here rather than reached through m87a0, for two
    reasons. The printed line replaces that row's rider with a heavier burn,
    so it is not the same attack; and `use` refuses to re-enter a row already
    in flight, which m87a0 is whenever the rider's blow happens to be one the
    mount is also carrying.

    Off `PowerUsed` rather than `Hit`: the printed moment is the rider
    *making* a melee attack, which happens whether or not it lands, and
    `PowerUsed` fires once per use where an attack is announced once per
    target.

    "Instead of its normal effect" is read as replacing the rider on the
    bite -- the ongoing five and the weakness -- and not the damage, which is
    the attack rather than its effect.
    """
    me = c.me

    def follow(ev: PowerUsed) -> None:
        if ev.actor != _qualified_rider(c) or not ev.targets:
            return
        p = get(ev.power)
        if p is None or not p.is_attack or p.reach.kind != "melee":
            return
        victim = ev.targets[0]
        if c.distance(victim) > 1 or not alive(c.world, victim):
            return
        if c.strike(on=victim):
            c.hit(on=victim)
            c.ongoing(10, DamageType.POISON, on=victim)

    c.watch(PowerUsed, follow, until=When.ENCOUNTER, on=me, label=c.ref)
