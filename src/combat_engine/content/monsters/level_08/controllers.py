"""Monster abilities, level 8: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=13)` and `Damage("2d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **blast or burst whose target line reads "creatures in the blast"** is
`EACH_CREATURE`; one that prints "enemies" is `EACH_ENEMY`. Both spellings
appear here and they are not the same row.

Seven readings this file had to settle.

**Seven rows print no range at all** -- the line is "+13 vs AC" and nothing
else. A weapon attack against AC is read as `Melee(1)`; an attack against a
non-AC defence is read at the reach the same creature's other ranged row
prints. Each one says so where it stands.

**"Recharges when ..."** is `Powers.restore`, armed by the row itself, so a
creature that met the condition before the row ever fired gets nothing --
which is what "when it is *first* bloodied" means. Where the database also
files a die, both are honoured: the die in the header, the printed sentence
as a watch.

**A gate on a `"save"` modifier is consulted with a context now** --
`actor`, `effect`, `label` -- so a penalty to saving throws no longer has to
be tracked by hand through `ZoneEntered`/`ZoneExited`. Nothing here needed
it in the end; the two save-ends holds that carry a second penalty put it on
the same effect instead, which is the printed "(save ends both)".

**`until=When.SUSTAIN` only works on something that can be sustained.**
`c.zone`, `c.aura`, `c.hazard` and `c.conjure` pass a sustain cost; `c.form`,
`c.watch` and `c.bonus` have no argument for one, and an effect with none
lapses after a round with the engine saying so out loud. The one Sustain
Standard row here is therefore applied through `Effects.apply` directly,
with the flight and the phasing hung on it.

**A zone that bites when a creature *ends* its turn in it is not
`c.burns`**, which bites on entering and on *starting* a turn. Two rows here
print the other clock and write both watches out, hung on the zone's own
effect rather than on a `c.watch` -- which is what carries them for the rest
of the encounter.

**Whoever is already standing in a new zone** has its `ZoneEntered`
announced by `Zones.create` before there is an id to subscribe with. Both
zone rows here handle those explicitly: one deliberately leaves them alone,
because the printed line bites on entering and on ending a turn there and a
creature caught in the burst has done neither yet; the other puts its traps
in unoccupied squares, so there are none.

**"First Failed Saving Throw"** is `Effect.escalate`, which runs on a failed
save -- as against `on_end`, which is what an Aftereffect wants. Both shapes
appear here and they are a turn apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
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
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
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
    Powers,
    Ranged,
    Relation,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    World,
    distance,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageRolled,
    Dropped,
    Event,
    Hit,
    Miss,
    SavingThrow,
    TurnEnd,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, alive, is_
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_melee,
    by_ranged,
    either,
    hits_me,
    targets_me,
)


def _hands_the_use_back(
    c: Cast, event: type[Event], matches: Callable[[Any], bool]
) -> None:
    """"Recharges when ...", as a use handed straight back.

    `Powers.restore` is the only thing that gives a spent row back. The
    watch is armed by the row, so a creature that already met the condition
    when it first fired gets nothing -- which is what the printed "first"
    means, and what the rows with no printed "first" want anyway, since
    neither of theirs can have happened before the attack that causes it.
    """
    known = c.world.get(c.me, Powers)
    ref = c.ref

    def again(ev: Any) -> None:
        if known is not None and matches(ev):
            known.restore(ref)

    c.watch(event, again, until=When.ENCOUNTER, on=c.me, label=ref)


def _rearms_when_bloodied(c: Cast) -> None:
    me = c.me
    _hands_the_use_back(c, Bloodied, lambda ev: ev.actor == me)


def _slower(c: Cast) -> None:
    """"Slowed, or dazed instead if it is already slowed."

    Asked of the creature at the moment of the hit, and of the condition
    rather than of this row's own effect: the printed line says "already
    slowed", by anything, not "already slowed by this".
    """
    if c.is_(Condition.SLOWED):
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


def _free_squares_near(c: Cast, radius: int, how_many: int) -> list[Square]:
    """Empty, passable squares within `radius`, nearest first.

    For a row that names a distance and no square. Ties break on the square
    itself so a replay of the same seed puts them in the same places.
    """
    mine = squares_of(c.world, c.me)
    here = c.here
    free = [
        sq
        for sq in spread(mine, radius) - mine
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    free.sort(key=lambda sq: (distance(here, sq), sq))
    return free[:how_many]


# --------------------------------------------------------------------------
# m179
# --------------------------------------------------------------------------


@power(
    "m179a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 4),
)
def m179a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m179a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 7, dtype=DamageType.FORCE, kind=LIMITED),
)
def m179a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.slowed(until=When.EONT)


@power(
    "m179a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d10", 5, dtype=DamageType.FORCE),
)
def m179a2(c: Cast) -> None:
    """The miss line reads "can", which is a real choice and is asked of the
    caster -- `c.may` asks `c.target` unless told otherwise, and the one
    deciding here is the m179."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.teleport(3, who=victim)
    elif c.may("teleport it 1 square", who=c.me):
        c.teleport(1, who=victim)


@power(
    "m179a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("4d6", 2, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m179a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m179a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m179a4(c: Cast) -> None:
    c.teleport(5)


# --------------------------------------------------------------------------
# m2851
# --------------------------------------------------------------------------


@power(
    "m2851a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 7),
)
def m2851a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m2851a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d8", 4),
)
def m2851a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2851a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2851a2(c: Cast) -> None:
    """The Effect line is not part of the hit: it pays out once for the whole
    use, which is `c.first`, and to allies rather than to the targets.

    "Until the end of its next turn" is the *ally's* clock, which is EOTNT.
    The m2851 is left out -- "any ally" is the other people on its side.
    """
    if c.first:
        for friend in sorted(c.within(3, side="ally")):
            if friend != c.me:
                c.bonus("attack", 2, on=friend, until=When.EOTNT)
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


# --------------------------------------------------------------------------
# m2960
# --------------------------------------------------------------------------


@power(
    "m2960a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 4),
)
def m2960a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`.

    "Crit 1d8 + 20" is the ordinary critical plus a high-crit die: 2d8 + 4
    maxed is 20 already, so the printed number says what the engine already
    does and the 1d8 is the part it does not add for itself.

    Rolled and applied flat rather than through `c.damage`, which maxes its
    dice on a critical -- correct for the printed line and wrong for the
    extra die, which the rule says is rolled.
    """
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d8"))


@power(
    "m2960a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m2960a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m2960a2",
    level=8,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
)
def m2960a2(c: Cast) -> None:
    """No range printed; read at the reach the m2960's other ranged row
    prints, which is 5.

    The database files this as a recharge power with **no die**, which is
    the printed line exactly: it never comes back on a roll, only when the
    burn is saved against or the victim goes down. Both of those are watched
    off the one effect the attack leaves behind -- the daze and the burn
    ride together, so "(save ends both)" is one saving throw and the throw
    that ends it is the one the recharge reads.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    hold = c.condition(
        Condition.DAZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED)
    )
    if hold is None:
        return
    mark = str(hold)
    _hands_the_use_back(
        c, SavingThrow, lambda ev: ev.saved and ev.actor == victim and ev.against == mark
    )
    _hands_the_use_back(c, Dropped, lambda ev: ev.actor == victim)


@power(
    "m2960a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m2960a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


_M2960_STRUCK = "an enemy's attack hits the m2960"


@power(
    "m2960a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2960_STRUCK,
    on=Trigger(Hit, when=hits_me, text=_M2960_STRUCK),
)
def m2960a4(c: Cast) -> None:
    """Half damage from **one** blow, so this is not `c.insubstantial`: that
    is a property of the creature and halves everything that reaches it
    until its duration runs out. The printed line halves the triggering
    attack and nothing else, so the number is halved on the `DamageRolled`
    that carries this attack's ref, and the listener goes as it fires.

    `DamageRolled` is a `Decision` its emitter reads back, which is what
    makes changing `amount` from here mean anything.

    The spec line prints a recharge die and the printed sentence says it
    comes back when the m2960 is first bloodied; both are honoured.
    """
    _rearms_when_bloodied(c)
    me, from_ = c.me, getattr(c.trigger, "power", "")
    spent: list[bool] = []

    def halve(ev: DamageRolled) -> None:
        if spent or ev.target != me or ev.detail != from_:
            return
        spent.append(True)
        ev.amount //= 2
        c.world.effects.end(shield, "the blow is turned")

    shield = c.watch(DamageRolled, halve, until=When.EOT, on=me, label=c.ref)


@power(
    "m2960a5",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2960a5(c: Cast) -> None:
    """The three freedoms are one mode and one waiver, both held to the end
    of the turn so they cover the shift and nothing after it.

    "Through enemy-occupied spaces" and "across liquid" are both phasing:
    `movement._clear` lets a phasing creature past a blocked square and past
    an occupant, and it still has to stop somewhere legal, which is the
    printed rule. "Hazardous terrain effects" is the other half of
    `c.ignores_difficult`, which takes every sort of going when given none.
    """
    c.phasing(until=When.EOT)
    c.ignores_difficult(until=When.EOT)
    c.shift(6)


# --------------------------------------------------------------------------
# m3105
# --------------------------------------------------------------------------


@power(
    "m3105a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 4),
)
def m3105a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`.

    "Plus 1d6 fire" is a second blow of a second type: `Damage` carries one
    type, so the weapon half stays in the header where it can be rescaled
    and the fire is rolled in the body.
    """
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)
        c.penalty(AC, 2, until=When.EONT)


@power(
    "m3105a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 4, kind=LIMITED),
)
def m3105a1(c: Cast) -> None:
    """The burn's duration is a sentence rather than a clock -- it ends when
    the victim ends a turn away from the m3105 -- so it is held to the end
    of the encounter and torn down by a `TurnEnd` watch hung on its own
    effect, which is what carries it for that long.

    `TurnEnd` rather than `MoveEnd`: the printed line asks where the
    creature *finishes*, and stepping away and back is not enough.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    c.damage("1d6", dtype=DamageType.FIRE)
    burn = c.ongoing(5, DamageType.FIRE, until=When.ENCOUNTER)
    if burn is None:
        return
    me = c.me

    def cools(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor == victim and not adjacent(c.world, victim, me):
            c.world.effects.end(burn, "it ended its turn away from the m3105")

    burn.subs.append(c.world.bus.on(TurnEnd, cools, owner=me))


@power(
    "m3105a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3105a2(c: Cast) -> None:
    """The Effect pays out once for the whole use, so it hangs on `c.first`,
    and it names the m3105 itself as well as its allies.

    "Uses m474a3" is that row off the ally's own sheet rather than a copy of
    what it does: `use` refuses it for an ally that does not have it or
    cannot meet its printed Requirement, which is the reading the page
    intends and a copy would quietly ignore.
    """
    if c.first:
        c.temp_hp(5, on=c.me)
        for friend in sorted(c.within(5, side="ally")):
            if friend == c.me:
                continue
            c.temp_hp(5, on=friend)
            use(c.world, friend, "m474a3")
    if c.strike():
        c.hit()


@power(
    "m3105a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[
        Keyword.ILLUSION,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.AREA,
    ],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3105a3(c: Cast) -> None:
    """Both penalties ride on **one** effect, so the victim gets one saving
    throw and not two and cannot shake off half of what the page calls one
    thing.

    The Aftereffect hangs on `on_end`: `escalate` is the other clock and
    runs on a *failed* save, which is the opposite moment.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    hold = c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[
            (victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref)),
            (victim, Mod(what="damage", value=-4, kind="untyped", label=c.ref)),
        ],
    )

    def afterwards() -> None:
        if alive(c.world, victim):
            c.penalty("damage", 2, on=victim, until=When.SAVE_ENDS)

    hold.on_end.append(afterwards)


@power(
    "m3105a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m3105a4(c: Cast) -> None:
    """`c.save` and `c.bloodied` both default to the caster, which is who
    this row is about throughout. `against="ongoing"` picks the burn rather
    than whichever save-ends effect is found first -- the printed line names
    an ongoing damage effect and nothing else.
    """
    c.temp_hp(7, on=c.me)
    if c.may("make a saving throw against an ongoing damage effect", who=c.me):
        c.save(on=c.me, against="ongoing")
    if c.bloodied(on=c.me):
        c.heal(7, on=c.me)


# --------------------------------------------------------------------------
# m346
# --------------------------------------------------------------------------


def _somebody_is_unconscious(world: World, eid: int) -> bool:
    """A printed "one unconscious creature", asked of the board.

    `Target` carries a side and a count and no condition, so the restriction
    is a requirement here and a guard in the body: the row is not offered
    while nobody is down, and never lands on somebody standing.
    """
    from combat_engine.engine.query import creatures

    return any(
        other != eid and alive(world, other) and is_(world, other, Condition.UNCONSCIOUS)
        for other in creatures(world)
    )


@power(
    "m346a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 9),
)
def m346a0(c: Cast) -> None:
    """"Can push" is a real choice, and it is the m346's."""
    if c.strike():
        c.hit()
        if c.may("push it 1 square", who=c.me):
            c.push(1)


@power(
    "m346a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m346a1(c: Cast) -> None:
    """Two swings of the row that prints them, aimed one at a time: the
    second is chosen after the first has resolved, which is the printed
    order and matters when the first one kills."""
    for _ in range(2):
        reachable = sorted(f for f in c.within(2, side="enemy") if alive(c.world, f))
        foe = c.choose(reachable, "who it swings at") if reachable else None
        if foe is None:
            return
        use(c.world, c.me, "m346a0", targets=[foe], spend=False)


@power(
    "m346a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1, label="One unconscious creature"),
    keywords=[Keyword.HEALING, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d10", 13, dtype=DamageType.PSYCHIC),
    requires=_somebody_is_unconscious,
    requires_text="a creature must be unconscious",
)
def m346a2(c: Cast) -> None:
    """"Regains 10 hit points, or 10 temporary ones if it is at full" is
    read off `c.missing` rather than from a stored maximum: the two are the
    same question and only one of them is always current."""
    victim = c.target
    if victim is None or not is_(c.world, victim, Condition.UNCONSCIOUS):
        return
    if not c.strike():
        return
    c.hit()
    if c.missing(on=c.me):
        c.heal(10, on=c.me)
    else:
        c.temp_hp(10, on=c.me)


@power(
    "m346a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m346a3(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold.

    "First Failed Saving Throw" is `escalate`: the daze ends and the
    unconsciousness replaces it, carrying no escalation of its own so it
    cannot fire twice.

    The spec line prints a recharge die and the printed sentence says it
    comes back when the m346 is first bloodied; both are honoured.
    """
    if c.first:
        _rearms_when_bloodied(c)

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.unconscious(until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m346a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m346a4(c: Cast) -> None:
    """Sustain Standard is a `sustain_cost` on the effect, and `c.form` has
    no argument for one -- a `When.SUSTAIN` effect with no cost is one
    nobody can sustain, which lapses after a round and which the engine now
    says out loud. So the shape is applied directly and the flight and the
    phasing hang on it and end with it.

    "A porous obstacle that would otherwise prevent movement" is phasing:
    `movement._clear` lets it past, and it still has to stop somewhere
    legal. Hovering is the half of "fly 8 (hover)" that nothing in the
    engine reads, so the mode carries the speed and nothing else.
    """
    shape = c.world.effects.apply(
        c.me,
        c.me,
        When.SUSTAIN,
        label=c.ref,
        conditions=[Condition.INSUBSTANTIAL],
        sustain_cost=STANDARD,
    )
    granted = (c.mode("fly", 8, until=When.ENCOUNTER), c.phasing(until=When.ENCOUNTER))
    for held in granted:
        if held is not None:
            shape.on_end.append(
                lambda h=held: c.world.effects.end(h, "the form is over")
            )


@power(
    "m346a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m346a5(c: Cast) -> None:
    """A disguise and nothing else: the shape carries no statistics and
    gates no other row, and the way through it is an Insight check, which
    the engine has no skills to roll. Deliberately inert."""
    c.note("m346a5: appears as a Medium or Large humanoid")


# --------------------------------------------------------------------------
# m456
# --------------------------------------------------------------------------


def _has_a_bloodied_ally(world: World, eid: int) -> bool:
    """A printed "bloodied allies in the burst", asked of the board.

    `Target` carries a side and a count and no condition, so the same shape
    as m346a2: a requirement, so the row is not offered when there is
    nobody to heal, and a guard in the body so it never heals anybody else.
    """
    from combat_engine.engine.components import Health
    from combat_engine.engine.query import allies

    return any(
        alive(world, friend) and (held := world.get(friend, Health)) and held.bloodied
        for friend in allies(world, eid)
    )


@power(
    "m456a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 2),
)
def m456a0(c: Cast) -> None:
    """No range printed; a weapon attack against AC is `Melee(1)`."""
    if c.strike():
        c.hit()


@power(
    "m456a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 2),
)
def m456a1(c: Cast) -> None:
    """No range printed; an attack against AC is `Melee(1)`."""
    if c.strike():
        c.hit()


@power(
    "m456a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 5, dtype=DamageType.POISON),
)
def m456a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m456a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
)
def m456a3(c: Cast) -> None:
    """No damage on the hit at all -- the whole of it is the burning and the
    slow, and they ride on one effect so "(save ends both)" is one throw."""
    if c.strike():
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m456a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    once_per_round=True,
)
def m456a4(c: Cast) -> None:
    """`EACH_ALLY` includes the caster -- the "ally" pool is the side, not
    the side minus you -- and the printed line says allies, so the m456 is
    left out here."""
    if c.target != c.me:
        c.bonus("speed", 5, until=When.EONT)


@power(
    "m456a5",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING, Keyword.CLOSE],
    requires=_has_a_bloodied_ally,
    requires_text="one of the m456's allies must be bloodied",
)
def m456a5(c: Cast) -> None:
    """Bloodied allies only, asked per target as the burst reaches it."""
    if c.target != c.me and c.bloodied():
        c.heal(15)


# --------------------------------------------------------------------------
# m4796
# --------------------------------------------------------------------------


def _webs(c: Cast) -> None:
    """The zone m4796a3 leaves behind.

    The bite is on **entering** and on **ending** a turn there, which is not
    what `c.burns` does -- it bites on entering and on *starting* -- and it
    is enemies only, which `c.burns` does not ask. So both watches are
    written out and hung on the zone's own effect, which is what carries
    them to the end of the encounter.

    Whoever is standing in the burst as it goes up is deliberately left
    alone: `Zones.create` announces their entry before there is an id to
    subscribe with, and the printed line does not bite them anyway -- they
    have not entered, and the end of their turn is when it catches them.
    """
    ring = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    held = dict(c.world.zones.all()).get(ring)
    if held is None or held.effect is None:
        return
    me = c.me
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == me or who not in c.enemies() or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(5, dtype=DamageType.POISON, on=who)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def lingered(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    held.effect.subs.append(c.world.bus.on(ZoneEntered, walked_in, owner=me))
    held.effect.subs.append(c.world.bus.on(TurnEnd, lingered, owner=me))


@power(
    "m4796a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7, dtype=DamageType.POISON),
)
def m4796a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4796a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 7),
)
def m4796a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m4796a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d10", 5, dtype=DamageType.POISON),
)
def m4796a2(c: Cast) -> None:
    """"To spiders" is not a side, and `c.grants_advantage` names one
    beneficiary or a whole side. So the relation is laid once per spider and
    all of them ride on one effect: one saving throw ends the lot, which is
    what "(save ends)" says.

    Who counts is asked of the type line -- `c.is_kind` strips the
    parentheses the block prints its subtype in.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    spiders = sorted(
        {
            s
            for s in (c.me, *c.allies())
            if alive(c.world, s) and c.is_kind("spider", on=s)
        }
    )
    if spiders:
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=f"{c.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, victim, s) for s in spiders],
        )


@power(
    "m4796a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m4796a3(c: Cast) -> None:
    """The zone is the Effect line, so it goes up once for the whole use --
    `c.first` -- and whether or not anything was hit."""
    if c.first:
        _webs(c)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


_M4796_ALLY_MISSED = "an ally within 5 squares of the m4796 misses with an attack"


@power(
    "m4796a4",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4796_ALLY_MISSED,
    on=Trigger(Miss, when=ally_within(5), text=_M4796_ALLY_MISSED),
)
def m4796a4(c: Cast) -> None:
    """Filed as a free action and printed as an immediate interrupt, which
    is the window that matters: `resolve.attack` re-reads the result after
    it closes and turns the `Miss` into a `Hit` if the new number lands.

    `ally_within` reads the attacker on an event with no actor, so the
    creature measured to is the one that *missed* rather than the one that
    was missed.

    The damage is dealt before the reroll and whether or not it helps: the
    ally pays for the second swing, not for landing it.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    c.flat(5, on=who)
    c.reroll_attack()


_M4796_AIMED_AT = "a melee or a ranged attack is aimed at the m4796"


@power(
    "m4796a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4796_AIMED_AT,
    on=Trigger(
        AttackDeclared,
        when=both(targets_me, either(by_melee, by_ranged)),
        text=_M4796_AIMED_AT,
    ),
)
def m4796a5(c: Cast) -> None:
    """The printed trigger reads "hits", and `c.redirect` only works on the
    declaration: after the die is down there is a result that would have to
    be thrown out and rolled again against another creature's defences. So
    the declaration is the window, which is the one the printed effect
    actually needs.

    The spec line prints a recharge die and the printed sentence says it
    comes back when the m4796 is first bloodied; both are honoured.
    """
    _rearms_when_bloodied(c)
    beside = sorted(
        a for a in c.allies() if a != c.me and alive(c.world, a) and c.adjacent(to=a)
    )
    if beside:
        c.redirect(to=c.choose(beside, "which ally takes it") or beside[0])


# --------------------------------------------------------------------------
# m4974
# --------------------------------------------------------------------------


@power(
    "m4974a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=8, kind=MINION),
)
def m4974a0(c: Cast) -> None:
    """A minion's flat damage: `kind=MINION` is what says the number does
    not scale, and its single hit point is in the database."""
    if c.strike():
        c.hit()


_M4974_DOWN = "the m4974 drops to 0 hit points"


@power(
    "m4974a1",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    trigger=_M4974_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4974_DOWN),
)
def m4974a1(c: Cast) -> None:
    """A death throe. The dispatcher offers it to a creature that is no
    longer alive, which is the only way a row of this shape ever fires, and
    `Dropped` names its subject `actor` -- so `about_me` is the right
    predicate here where `targets_me` is the right one on a condition.

    "First Failed Saving Throw" is `escalate`: the slow ends and the
    petrification replaces it, carrying no escalation of its own so it
    cannot fire twice.
    """

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.SAVE_ENDS, on=eff.owner)

    for foe in sorted(c.within(1, side="enemy")):
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=foe, escalate=worsen)


# --------------------------------------------------------------------------
# m4989
# --------------------------------------------------------------------------


def _pull_of(c: Cast) -> None:
    """The zone m4989a3 leaves behind.

    Ending a turn in it is neither of the two moments `c.burns` bites at, so
    this is a `TurnEnd` watch, hung on the zone's own effect rather than on
    a `c.watch` -- the zone outlives any duration a watch could be given
    that the caster is able to keep going.

    "The m4989 can slide it" is a real choice and it is the m4989's.
    """
    ring = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    held = dict(c.world.zones.all()).get(ring)
    if held is None or held.effect is None:
        return
    me = c.me

    def tug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        if c.may("slide it 3 squares", who=me):
            c.slide(3, on=ev.actor)

    held.effect.subs.append(c.world.bus.on(TurnEnd, tug, owner=me))


@power(
    "m4989a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 9),
)
def m4989a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4989a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
)
def m4989a1(c: Cast) -> None:
    """"One creature within 5 squares" is any creature, not an enemy, so the
    row declares no target and picks from the board: `Target` carries a side
    and this line names none.

    `c.grant_attack` rolls whatever that creature's own basic attack is,
    which is the printed "melee or a ranged basic attack", and returns
    whether the swing was *made*. Whether it landed is a different question,
    so a `Hit` is watched for while the borrowed attack is in flight and the
    listener comes off again straight after.
    """
    near = sorted(x for x in c.within(5) if x != c.me and alive(c.world, x))
    who = c.choose(near, "who it compels") if near else None
    if who is None:
        return
    reachable = sorted(
        f for f in c.within(10, of=who) if f != who and alive(c.world, f)
    )
    foe = c.choose(reachable, "who it is made to strike") if reachable else None
    if foe is None:
        return
    landed: list[bool] = []

    def watch_hit(ev: Hit) -> None:
        if ev.attacker == who:
            landed.append(True)

    sub = c.world.bus.on(Hit, watch_hit, owner=c.me)
    try:
        c.grant_attack(who, on=foe)
    finally:
        c.world.bus.off(sub)
    if landed:
        c.slide(3, on=who)


@power(
    "m4989a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m4989a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the domination."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m4989a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d10", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4989a3(c: Cast) -> None:
    """The zone is the Effect line, so it goes up once for the whole use and
    whether or not anything was hit."""
    if c.first:
        _pull_of(c)
    if c.strike():
        c.hit()


@power(
    "m4989a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4989a4(c: Cast) -> None:
    """"Grants combat advantage" names nobody, and the relation needs a
    beneficiary, so it is granted to the m4989's whole side -- which is
    everyone the grant can possibly matter to, since the creatures granting
    it are the m4989's enemies.

    Who is adjacent is read before the teleport, as printed: the m4989
    leaves them behind and they stay exposed.
    """
    for foe in sorted(c.within(1, side="enemy")):
        c.grants_advantage(on=foe, until=When.EONT, to="allies")
    c.teleport(3)


# --------------------------------------------------------------------------
# m5010
# --------------------------------------------------------------------------

#: The label every trap m5010a5 lays carries. The row's own recharge reads
#: it, which is the only thing that can say whether they have all gone.
_M5010_TRAP = "m5010a5 trap"


def _no_traps_left(world: World, eid: int) -> bool:
    """The printed recharge condition, on top of the die the database files.

    The two only ever agree to make the row available *later*: the die can
    come up and the traps still be standing, and the printed sentence is the
    one that says so.
    """
    return not any(
        zone.label == _M5010_TRAP and zone.owner == eid for _, zone in world.zones.all()
    )


def _sand_trap(c: Cast, square: Square) -> None:
    """One trap, in one square, which goes as it catches somebody.

    Three one-square zones rather than one zone of three squares: each ends
    on its own, and a single zone could only end all three at once -- which
    is neither what the printed line says nor what its recharge condition
    could then ever mean.
    """
    pit = c.zone({square}, until=When.ENCOUNTER, label=_M5010_TRAP)
    held = dict(c.world.zones.all()).get(pit)
    if held is None or held.effect is None:
        return
    me = c.me

    def caught(ev: ZoneEntered) -> None:
        if ev.zone != pit or ev.actor == me or ev.actor not in c.enemies():
            return
        c.condition(Condition.RESTRAINED, until=When.EOTNT, on=ev.actor)
        c.world.zones.end(pit, "the trap is spent")

    held.effect.subs.append(c.world.bus.on(ZoneEntered, caught, owner=me))


@power(
    "m5010a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6),
)
def m5010a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5010a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 4),
)
def m5010a1(c: Cast) -> None:
    """"Ranged 10/20" is a normal and a long range; `Range` carries one
    number, so the row is written at the normal one and a shot past it takes
    no penalty because there is nowhere to record that it should."""
    if c.strike():
        c.hit()


@power(
    "m5010a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
)
def m5010a2(c: Cast) -> None:
    """No damage at all, and the Effect line is per target and runs whether
    or not the attack landed -- so the slide sits outside the hit."""
    if c.strike():
        c.prone()
    c.slide(2)


@power(
    "m5010a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m5010a3(c: Cast) -> None:
    """The spec line prints a recharge die and the printed sentence says it
    comes back when the m5010 is first bloodied; both are honoured."""
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(2)
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m5010a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5010a4(c: Cast) -> None:
    """A jump is a walk the engine has no separate mode for, so the row is
    the ground covered plus the waiver -- which is the whole of what makes
    it different from walking. The header's `no_provoke` is about *using*
    the power and says nothing about the movement inside it.
    """
    c.no_provoke(until=When.EOT)
    c.move(c.speed_of())


@power(
    "m5010a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_no_traps_left,
    requires_text="every trap this row made must have ended",
)
def m5010a5(c: Cast) -> None:
    """The squares are printed as unoccupied, so nobody is standing in one
    as it spawns -- which is the case `Zones.create` announces before there
    is an id to subscribe with, and this row never meets it.

    "Within 10 squares" names a distance and no square, so the traps go in
    the nearest free ones, ties broken on the square itself so a replay of
    the same seed lays them in the same places.
    """
    for square in _free_squares_near(c, 10, 3):
        _sand_trap(c, square)


# --------------------------------------------------------------------------
# m657
# --------------------------------------------------------------------------


@power(
    "m657a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 9),
)
def m657a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _slower(c)


@power(
    "m657a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=Target("enemy", 1, label="One nondeafened creature"),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("4d6", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m657a1(c: Cast) -> None:
    """"Nondeafened" lives in the `Target` label, which is prose, and as a
    guard here: `Target` carries a side and a count and no condition."""
    if c.target is not None and c.is_(Condition.DEAFENED):
        return
    if c.strike():
        c.hit()
        _slower(c)


@power(
    "m657a2",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m657a2(c: Cast) -> None:
    c.teleport(4)


@power(
    "m657a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=11),
)
def m657a3(c: Cast) -> None:
    """No damage at all. The slow and the penalty ride on one effect, so
    "(save ends both)" is one saving throw -- and that same throw is what
    hands the row back, which is why the recharge watch reads the effect by
    name rather than taking whichever save it sees first.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    hold = c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.SLOWED],
        mods=[(victim, Mod(what=WILL.value, value=-2, kind="untyped", label=c.ref))],
    )
    mark = str(hold)
    _hands_the_use_back(
        c, SavingThrow, lambda ev: ev.saved and ev.actor == victim and ev.against == mark
    )


# --------------------------------------------------------------------------
# m702
# --------------------------------------------------------------------------

#: The four things m702a2 chooses between, written as what each does rather
#: than by the ids the spec prints for them -- those belong to another stat
#: block and are not in the registry, so each is written out here.
_M702_CALLS = (
    "daze the enemies in the burst",
    "a bonus to its allies' attack and damage rolls",
    "a free shift for its allies",
    "a saving throw for its allies",
)


@power(
    "m702a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 8),
)
def m702a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m702a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 10),
)
def m702a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m702a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m702a2(c: Cast) -> None:
    """Four printed options, one of which attacks. That one's line is in the
    header, so the numbers stay data, and `c.strike(on=...)` rolls it even
    though the row declares no targets of its own -- which is what lets the
    other three aim at allies instead.

    The ids the spec prints for the four belong to another stat block and
    are not in the registry, so each is written out rather than used.

    "Nondeafened" is asked of each creature as the burst reaches it, and the
    three ally lines leave the m702 out: `c.within(..., side="ally")`
    returns the side, and the printed word is allies.
    """
    picked = c.choose(list(_M702_CALLS), "which call") or _M702_CALLS[0]
    if picked == _M702_CALLS[0]:
        for foe in sorted(c.within(5, side="enemy")):
            if c.is_(Condition.DEAFENED, on=foe):
                continue
            if c.strike(on=foe):
                c.dazed(on=foe, until=When.EONT)
        return
    for friend in sorted(c.within(5, side="ally")):
        if friend == c.me or c.is_(Condition.DEAFENED, on=friend):
            continue
        if picked == _M702_CALLS[1]:
            c.bonus("attack", 1, on=friend, until=When.EONT)
            c.bonus("damage", 2, on=friend, until=When.EONT)
        elif picked == _M702_CALLS[2]:
            if c.may("shift 2 squares", who=friend):
                c.shift(2, who=friend)
        elif c.may("make a saving throw", who=friend):
            c.save(on=friend)
