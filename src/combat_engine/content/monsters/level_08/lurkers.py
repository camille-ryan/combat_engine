"""Monster abilities, level 8: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=13)` and `Damage("2d6", 8)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the seven levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a hold
that has to be paid for each turn goes on a `When.SUSTAIN` clock, because
*not* sustaining is what lets go; and a helper written for an earlier level
is imported rather than copied.

Four things this file had to settle.

**Dim light is a gated -2, not a wall.** m2844a0 dims a radius around
itself, and concealment is the whole of what that means in a fight:
`c.zone(..., blocks_sight=True)` is the near neighbour and the wrong one,
because `cover_between` deliberately excludes the squares either party is
standing in -- so a sight-blocking zone shelters what is *behind* it and
never what is inside it. The penalty rides on each enemy and asks about the
creature being shot at, which is where a -2 to attack rolls has to sit.

**An aura that can be switched off.** Two rows turn m2844a0 off for a
while, so being off is a labelled hold on the creature and the concealment
gate reads it. A zone that was ended and remade would lose the radius the
board is drawing.

**Unseen until it swings.** m149a2 hangs `HIDDEN_FROM` on a `When.SUSTAIN`
effect, one per target, and the watch that ends them all ignores the power
that made them -- the burst attacks each target in turn, and a watch that
did not would have had the second target's roll tear down the first
target's concealment.

**Being removed from play.** m727a3 rides inside its victim:
`Condition.REMOVED` is what the engine has for a creature that is on the
board and not in the fight, and the way back out is hung on the
domination's own ending rather than on a clock, because that is what the
printed line measures.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.skirmishers import _had_advantage
from combat_engine.content.monsters.level_03.skirmishers import _grabbing
from combat_engine.content.monsters.level_04.skirmishers import _until_the_grab_ends
from combat_engine.content.monsters.level_06.controllers import _is_humanoid
from combat_engine.content.monsters.level_07.soldiers import (
    _living,
    _recharge_on,
    _until_that_blow_lands,
)
from combat_engine.content.monsters.level_08.soldiers import _blink_to, _free_squares_near
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
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
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Position,
    Relation,
    Usage,
    When,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    Bloodied,
    DamageApplied,
    DamageRolled,
    MoveEnd,
    RelationCleared,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, squares
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_ranged,
    either,
    targets_me,
    would_hit_me,
)
from combat_engine.engine.types import Window

#: The four defences, for a printed "+4 bonus to all defenses".
EVERY_DEFENCE = (AC, FORT, REF, WILL)


def _sweep(c: Cast, label: str, why: str) -> None:
    """End every effect this creature is holding up under one label."""
    for eff in list(c.world.effects.live.values()):
        if eff.source == c.me and eff.label == label:
            c.world.effects.end(eff, why)


def _holding(c: Cast, label: str) -> bool:
    return any(eff.label == label for eff in c.world.effects.of(c.me))


def _drag_to(c: Cast, victim: int, squares_: int, within: int) -> bool:
    """Slide a creature `squares_`, ending within `within` of the caster.

    `c.slide` with no `to` offers every square in range to the decider,
    which is right for "slide 5" and useless for a line that says where the
    slide has to end.
    """
    near = spread(squares(c.world, c.me), within)
    options = sorted(
        sq
        for sq in spread(squares(c.world, victim), squares_)
        if sq in near and c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not options:
        return False
    where = c.world.decide(c.me, "slide", options, f"{c.ref}: drag it close")
    return bool(c.slide(squares_, on=victim, to=where))


def _appear_beside(c: Cast, victim: int) -> bool:
    """Arrive in a square next to that creature, from wherever it is."""
    near = _free_squares_near(c, victim, 1)
    if not near:
        return False
    return _blink_to(
        c, c.world.decide(c.me, "teleport", near, f"{c.ref}: beside it")
    )


# --------------------------------------------------------------------------
# m149
# --------------------------------------------------------------------------


@power(
    "m149a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 5),
)
def m149a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m149a1",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
)
def m149a1(c: Cast) -> None:
    """No damage at all: being caught out is the whole of the hit, and
    `c.grants_advantage` hands it to this creature alone."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


_M149_UNSEEN = "m149a2 unseen"


@power(
    "m149a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m149a2(c: Cast) -> None:
    """Gone from the sight of everybody it catches, for as long as it keeps
    paying for it.

    One hold per target, all under one label, each carrying the
    `HIDDEN_FROM` relation for its own watcher -- `c.invisible` would put
    every watcher on one effect and there is a sustain cost on this, which
    only the effects table takes.

    The two printed endings are one watch apiece, armed once for the whole
    power and *before* the first roll: the burst attacks each target in
    turn, so a watch armed afterwards would have been torn down by its own
    second target's roll. Both ignore this row's own attacks for the same
    reason, which is also what "until the m149 attacks" means -- the next
    attack, not this one.

    A third watch puts the relation back. `resolve.attack` clears
    `HIDDEN_FROM` for whoever swung -- the Stealth rule, and the right
    default -- which is not this printed line and which every roll of this
    burst was tripping, so the first target could see again by the time the
    second was caught. It is only put back while a live effect is still
    holding it up, so a veil that was ended stays ended.
    """
    me, ref = c.me, c.ref
    if c.first:
        _sweep(c, _M149_UNSEEN, "used again")

        def swung(ev: AttackRolled) -> None:
            if ev.attacker == me and ev.power != ref:
                _sweep(c, _M149_UNSEEN, "it attacked")

        def struck(ev: Hit) -> None:
            if ev.target == me and ev.attacker != me:
                _sweep(c, _M149_UNSEEN, "it was hit")

        def broke(ev: RelationCleared) -> None:
            if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
                return
            if ev.why == "attacked" and c.world.effects.carries(
                Relation.HIDDEN_FROM, me, ev.target
            ):
                c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

        c.watch(AttackRolled, swung, until=When.ENCOUNTER, on=me, label=f"{ref} swung")
        c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{ref} struck")
        c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label=f"{ref} veil")
    victim = c.target
    if victim is None or not c.strike():
        return
    c.world.effects.apply(
        me,
        me,
        When.SUSTAIN,
        label=_M149_UNSEEN,
        sustain_cost=MINOR,
        relations=[(Relation.HIDDEN_FROM, me, victim)],
    )


@power(
    "m149a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m149a3(c: Cast) -> None:
    """Whether the blow had combat advantage is read off its own result:
    asking the board again is too late, because attacking gives a hidden
    creature away and the relation is cleared the moment the attack is
    over -- which is precisely the creature this rider is written for."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _had_advantage(ev):
            c.damage("2d6", on=ev.target, detail="m149a3")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m149a3")


@power(
    "m149a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m149a4(c: Cast) -> None:
    """A change of face and nothing else -- no condition, no mode, no
    number. Declared inert rather than given an invented mechanic."""
    c.note("m149a4: it takes the shape of any Medium humanoid, a named one included")


# --------------------------------------------------------------------------
# m2844
# --------------------------------------------------------------------------


#: The hold that says the gloom is out. Two rows put it on.
_M2844_DOUSED = "m2844a0 doused"


def _douse(c: Cast, until: When) -> None:
    if not _holding(c, _M2844_DOUSED):
        c.effect(_M2844_DOUSED, until=until, on=c.me)


@power(
    "m2844a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2844a0(c: Cast) -> None:
    """Bright light dimmed for five squares around it, which in a fight is
    concealment and nothing else.

    A -2 to attack rolls against whoever is standing in the gloom: it rides
    on each enemy, because an attack modifier is read off the attacker, and
    asks about the *target*, because that is who the concealment belongs to.
    Not `blocks_sight`, which `cover_between` reads for every attack but
    measures between the two parties' squares and not inside them -- a
    sight-blocking zone shelters what is behind it and never what is in it.

    Radiant damage puts it out until the end of its next turn. That is a
    labelled hold rather than the aura being ended: the aura is what the
    board draws, and one remade a turn later would have lost its radius and
    its occupants.
    """
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER)

    def gloomy(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None
            and not _holding(c, _M2844_DOUSED)
            and victim in c.world.zones.occupants(ring)
        )

    for foe in c.enemies():
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=gloomy)

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT and ev.amount > 0:
            _douse(c, When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m2844a0 out")


@power(
    "m2844a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 8),
)
def m2844a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2844a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 8, kind=LIMITED),
)
def m2844a2(c: Cast) -> None:
    """The printed recharge is a board state rather than a die: it comes
    back the moment it is holding nobody. Any relation being cleared is
    worth re-asking on -- the answer is about the table, not about which
    relation just went -- and giving back a row that is already available
    costs nothing.

    The grab is applied on a `When.SUSTAIN` clock rather than through
    `c.grab`, whose hold runs to the end of the fight: "Sustain Minor" means
    that *not* sustaining is what lets go, and the cost is what puts the
    option in front of whoever is playing it. `c.on_sustain` carries the
    other half of the printed line, which the clock refreshing on its own
    would have dropped.

    The escape DC is not written: a grab is ended by the escape rules rather
    than by a number on the row that made it, and the engine has no contest
    to put one in.
    """
    _recharge_on(c, RelationCleared, lambda _ev: not _grabbing(c.world, c.me))
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    held = c.world.effects.apply(
        victim,
        c.me,
        When.SUSTAIN,
        label=f"{c.ref} grab",
        sustain_cost=MINOR,
        relations=[(Relation.GRABBED_BY, c.me, victim)],
    )
    c.on_sustain(held, lambda: c.flat(5, on=victim))
    _until_the_grab_ends(
        c, victim, c.blinded(until=When.ENCOUNTER, on=victim)
    )


@power(
    "m2844a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d4", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2844a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


_M2844_HURT = "the m2844 takes damage"


@power(
    "m2844a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M2844_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M2844_HURT),
)
def m2844a4(c: Cast) -> None:
    """Six squares away, unseen, and the gloom out until it moves again.

    "A space that is in darkness or dim light" is any square it lands in
    while its own gloom is up -- the aura travels with it, so the
    destination is dim by arriving in it. The one case the printed line
    guards against is landing in daylight with the gloom already out, and
    the engine has no light level to ask about; `c.terrain` answers for the
    fight as a whole and not for a square. See the report.
    """
    c.teleport(6)
    c.invisible(until=When.SONT)
    _douse(c, When.SONT)


# --------------------------------------------------------------------------
# m2862
# --------------------------------------------------------------------------


def _alone_with_it(world: World, eid: int) -> bool:
    """A printed Requirement of "only one enemy within 5 squares"."""
    return sum(
        1 for foe in enemies(world, eid) if distance_between(world, eid, foe) <= 5
    ) == 1


@power(
    "m2862a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m2862a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2862a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 5),
    requires=_alone_with_it,
    requires_text="only one enemy may be within 5 squares of the m2862",
)
def m2862a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2862a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("4d6", 5, kind=LIMITED),
)
def m2862a2(c: Cast) -> None:
    """It throws its victim across the room and is there waiting.

    The printed Effect and the printed Miss are two halves of one sentence
    rather than an Effect that always happens: the Miss says the m2862
    teleports 10 squares, which is what the Effect has it doing *with* its
    victim, and the two cannot both be true of one use. So the throw follows
    the hit and the lone jump follows the miss.

    Its own arrival names a square and no distance, so the distance is
    measured off the square.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.teleport(10)
        return
    c.hit()
    c.ongoing(5, on=victim)
    c.teleport(10, who=victim)
    _appear_beside(c, victim)


_M2862_BLED = "the m2862 is first bloodied"


@power(
    "m2862a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M2862_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2862_BLED),
)
def m2862a3(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the
    crossing and nowhere else. The enemy is chosen from those standing next
    to it, which is what the printed line names."""
    beside = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    if not beside:
        return
    victim = c.choose(beside, "m2862a3: which enemy") or beside[0]
    c.teleport(5, who=victim)
    _appear_beside(c, victim)


# --------------------------------------------------------------------------
# m4942
# --------------------------------------------------------------------------


@power(
    "m4942a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4942a0(c: Cast) -> None:
    """Dice rather than a flat number, so it is rolled as the blow lands
    instead of riding along as a damage modifier."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.is_(Condition.SURPRISED, on=ev.target):
            c.damage("2d6", on=ev.target, detail="m4942a0")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m4942a0")


@power(
    "m4942a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m4942a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4942a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m4942a2(c: Cast) -> None:
    """A hold that has to be paid for every turn to keep, and pays out when
    it is: the grab goes on a `When.SUSTAIN` clock with the printed cost, so
    not sustaining is what lets go, and `c.on_sustain` carries the acid.

    The -5 on getting out is not written: escaping is a skill check against
    a DC and the engine has neither, so there is nothing for the penalty to
    apply to. See the report.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    held = c.world.effects.apply(
        victim,
        c.me,
        When.SUSTAIN,
        label=f"{c.ref} grab",
        sustain_cost=STANDARD,
        relations=[(Relation.GRABBED_BY, c.me, victim)],
    )
    c.on_sustain(held, lambda: c.flat(15, dtype=DamageType.ACID, on=victim))


@power(
    "m4942a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 11, kind=LIMITED),
)
def m4942a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


#: Its own attacks, for the shape that cannot make one.
_M4942_ATTACKS = ("m4942a1", "m4942a2", "m4942a3")

#: The two shapes, by the ids the card prints for them.
_M4942_SHAPES = ("m4338a5", "m4942")


@power(
    "m4942a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m4942a4(c: Cast) -> None:
    """One shape at a time, held until it takes the other.

    "Until it uses this power again" is the previous shape ended by hand --
    `c.form` is not a stance and does not displace what came before -- and
    `revert=MINOR` is the printed way out of it.

    The first shape's whole content is how it squeezes: at full speed, with
    no penalty and granting nothing. `Condition.SQUEEZING` exists and what
    squeezing *costs* is not reachable from a row, so the shape is held and
    the three exemptions are noted.

    The second shape is immobilised and cannot attack, which is its own
    rows taken away for as long as it is held; they come back with the
    shape. Its resist 10 to all damage has nowhere to go -- resistance is
    kept per damage type and there is no all-damage entry -- and the
    Perception check that sees through it is a skill check. See the report.
    """
    shape = c.choose(list(_M4942_SHAPES), "m4942a4: which shape") or _M4942_SHAPES[0]
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.startswith(f"{c.ref} "):
            c.world.effects.end(eff, "it took another shape")
    if shape == _M4942_SHAPES[0]:
        c.form(
            conditions=(Condition.SQUEEZING,),
            until=When.ENCOUNTER,
            revert=MINOR,
            label=f"{c.ref} {shape}",
        )
        c.note("m4942a4: squeezing costs it no speed, no accuracy and no cover")
        return
    hold = c.form(
        conditions=(Condition.IMMOBILIZED,),
        until=When.ENCOUNTER,
        revert=MINOR,
        label=f"{c.ref} {shape}",
    )
    for ref in _M4942_ATTACKS:
        gone = c.forbid(ref, until=When.ENCOUNTER)
        if gone is not None:
            hold.on_end.append(lambda g=gone: c.world.effects.end(g, "it moved again"))
    c.note("m4942a4: a DC 24 Perception check notices that it is alive")


# --------------------------------------------------------------------------
# m5049
# --------------------------------------------------------------------------


@power(
    "m5049a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5049a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5049a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d8", 7),
)
def m5049a1(c: Cast) -> None:
    """The printed target is a dazed creature and the header's `target`
    field cannot say so, so the aim is narrowed here rather than refused:
    the creature the dispatcher chose is often not the one reeling."""
    victim = c.target
    if victim is None or not c.is_(Condition.DAZED, on=victim):
        victim = c.choose(
            [foe for foe in c.enemies() if c.is_(Condition.DAZED, on=foe)],
            "m5049a1: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)


@power(
    "m5049a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m5049a2(c: Cast) -> None:
    """The slide has a destination printed on it -- within 2 squares of the
    m5049 -- so the square is chosen rather than left to the decider, which
    would have offered every square within 5 of the victim."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.dazed(until=When.EONT, on=victim)
    _drag_to(c, victim, 5, 2)


_M5049_STRUCK = "the m5049 is hit by a melee or a ranged attack"


def _dazed_enemy_near(world: World, eid: int) -> bool:
    """A printed Requirement of "a dazed enemy within 2 squares"."""
    from combat_engine.engine.query import is_

    return any(
        distance_between(world, eid, foe) <= 2 and is_(world, foe, Condition.DAZED)
        for foe in enemies(world, eid)
    )


@power(
    "m5049a3",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_dazed_enemy_near,
    requires_text="a dazed enemy must be within 2 squares of the m5049",
    trigger=_M5049_STRUCK,
    on=Trigger(
        AttackRolled,
        when=both(would_hit_me, either(by_melee, by_ranged)),
        text=_M5049_STRUCK,
    ),
)
def m5049a3(c: Cast) -> None:
    """The guard goes up between the die landing and the blow arriving.

    `AttackRolled` rather than `Hit`: the defence is read **again** once
    that window closes, which is the only moment a bonus can turn a hit into
    a miss. `would_hit_me` is the printed "is hit by" asked there, off the
    provisional result.

    The bonus is gated on the attacker rather than given a duration, because
    the printed line is about one attack, and `_until_that_blow_lands` is
    what takes it away again.

    Not written: the dazed enemy taking the damage of an attack that missed.
    Nothing can roll a blow that did not land -- a `Miss` carries no damage
    and a PC's damage lives in its body rather than its header, so there is
    no expression to re-roll. The slide that follows it goes with it. See
    the report.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    for defence in EVERY_DEFENCE:
        guard = c.bonus(
            defence,
            4,
            until=When.EOT,
            on=c.me,
            kind="untyped",
            when=lambda ctx: ctx.get("attacker") == who,
        )
        _until_that_blow_lands(c, who, guard)


# --------------------------------------------------------------------------
# m727
# --------------------------------------------------------------------------


#: The hold that says its half-there-ness is out for a moment.
_M727_SOLID = "m727a0 solid"

#: How far it may go from where it fell.
_M727_TETHER = 20


@power(
    "m727a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m727a0(c: Cast) -> None:
    """Half of everything, except force, and nothing at all for a moment
    after radiant.

    Not `c.insubstantial`, which halves every packet that reaches the
    creature including the force the printed line excepts. So the halving is
    done on the damage itself, in the window before it is applied --
    `DamageRolled` is a proposal and carries both the type and the row that
    dealt it, which is what tells an attack from a zone or a burn.

    Radiant puts it out until the start of its next turn, as a labelled
    hold the halving reads.
    """
    me = c.me

    def halve(ev: DamageRolled) -> None:
        if ev.target != me or ev.dtype is DamageType.FORCE:
            return
        if _holding(c, _M727_SOLID):
            return
        p = get(ev.detail or "")
        if p is not None and p.is_attack:
            ev.amount = ev.amount // 2

    def scorched(ev: DamageApplied) -> None:
        radiant = ev.dtype is DamageType.RADIANT and ev.amount > 0
        if ev.target == me and radiant and not _holding(c, _M727_SOLID):
            c.effect(_M727_SOLID, until=When.SONT, on=me)

    c.watch(
        DamageRolled,
        halve,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m727a0",
    )
    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m727a0 burnt")


@power(
    "m727a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m727a1(c: Cast) -> None:
    """Tethered to the place it fell, which is where it is standing when the
    fight starts.

    Only the half that can be written. Refusing a *voluntary* move that
    would carry it past the tether is not sayable: `MoveStart` is the one
    cancellable movement event and it names no destination, so a row
    answering it cannot tell a step out from a step back. What can be
    written is the consequence of being carried out -- weakened, and unable
    to reach for m727a3 -- and its lifting when it is inside the tether
    again, which is checked at the end of every move anything makes it
    make. See the report.
    """
    me = c.me
    here = c.world.get(me, Position)
    grave = here.square if here is not None else None
    if grave is None:
        return
    held: list[Effect] = []

    def measure(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        far = distance(grave, ev.at) > _M727_TETHER
        if far and not held:
            for hold in (
                c.weakened(until=When.ENCOUNTER),
                c.forbid("m727a3", until=When.ENCOUNTER),
            ):
                if hold is not None:
                    held.append(hold)
        elif not far and held:
            for hold in held:
                c.world.effects.end(hold, "back within reach of its grave")
            held.clear()

    c.watch(MoveEnd, measure, until=When.ENCOUNTER, on=me, label="m727a1")


@power(
    "m727a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m727a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m727a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
)
def m727a3(c: Cast) -> None:
    """It climbs inside its victim and is gone until the victim shakes it.

    No damage at all: being worn is the whole of the hit. The printed target
    is a living humanoid, which no `Target` can say, so the aim is narrowed
    here -- "living" is asked of the type line, which is the only place the
    engine records anything about being alive.

    `Condition.REMOVED` is what the engine has for a creature that is on the
    board and not in the fight; the square is shared, because it is standing
    where its victim is. Both are hung on the domination's own ending rather
    than on a clock, which is what "when the target is no longer dominated"
    measures -- and the way out is a square next to the victim, chosen then
    rather than now.

    Two things are left out. Ending it early is printed as a free action and
    there is nothing for a creature that cannot act to spend one on. And
    "only one creature at a time" needs no guard: it is removed from play
    for as long as the possession lasts, so it cannot reach this row again
    while it is inside somebody.
    """
    me, victim = c.me, c.target
    if victim is None or not _living(c, victim) or not _is_humanoid(c, victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and _living(c, foe) and _is_humanoid(c, foe)
            ],
            "m727a3: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    ridden = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if ridden is None:
        return
    where = c.world.get(victim, Position)
    if where is not None:
        c.teleport(distance_between(c.world, me, victim), to=where.square, share=True)
    inside = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=me)

    def step_out() -> None:
        if inside is not None:
            c.world.effects.end(inside, "the possession is over")
        _appear_beside(c, victim)

    ridden.on_end.append(step_out)
