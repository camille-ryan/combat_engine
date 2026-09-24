"""Monster abilities, level 6: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=11)` and `Damage("1d8", 2)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **burst or blast whose target line reads "creatures in the burst"** is
everybody but the creature at its centre, which is `EACH_OTHER` for a close
burst and `EACH_CREATURE` for an area one -- an area burst is thrown
somewhere else and its caster is not standing in it.

Five readings this file had to settle.

**A "Sustain Minor:" line that does something** is an anchor effect on the
caster carrying the sustain cost, plus `c.on_sustain` for the payout. The
anchor is made once per power rather than once per target, and only if the
caster is not already holding one, or three victims would mean three minor
actions a round keeping one sentence alive.

**"Penalty to all defences (save ends)"** is one effect with four modifiers
on it, not four effects. Four would give the victim four saving throws and
let it shake off a quarter of a thing the page says is one.

**"Deals double damage"** and "takes half damage except from force" are both
`DamageRolled` in the interrupt window: the event carries the number, the
emitter reads it back, and nothing else in the engine multiplies.

**A trait filed as a standard action** is still a trait -- `ActionType.NONE`,
so `Encounter.start` arms it rather than the creature spending its turn on
it. Three of the rows here are printed that way.

**"An ally of its own sort"** is `_same_stock`: two creatures off the same
stat block. The printed line names a kind this file may not read, and the
`Ident.ref` pair says the same thing without saying the word.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.controllers import (
    _SAVE_ENDS_ON_ME,
    _same_stock,
    _save_ends_on_me,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
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
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Died,
    Dropped,
    Effect,
    Keyword,
    Melee,
    Mod,
    Movement,
    Position,
    Powers,
    Ranged,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import (
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Hit,
    OpportunityWindow,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.grid import Square, distance, spread
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, allies, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    hits_me,
)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (AC, FORT, REF, WILL)


def _all_defences(
    c: Cast, value: int, *, until: When, on: int | None = None
) -> Effect | None:
    """"A penalty to all defences", as **one** effect.

    `c.penalty` makes an effect per defence, which is four saving throws
    where the page prints one -- and a victim that shook off its Reflex
    penalty while keeping the other three.
    """
    who = c.target if on is None else on
    if who is None:
        return None
    mods = [
        (who, Mod(what=d.value, value=value, kind="untyped", label=c.ref))
        for d in DEFENCES
    ]
    return c.world.effects.apply(who, c.me, until, label=c.ref, mods=mods)


def _anchor(c: Cast, cost: ActionType = MINOR) -> Effect | None:
    """The hold a printed "Sustain Minor:" line hangs on.

    Nothing else on the caster carries a sustain cost, so the sustain action
    has nowhere to be spent; this is that somewhere. One per power use at
    most -- a second would charge the creature a second minor action a round
    to keep one sentence going.
    """
    label = f"{c.ref} sustain"
    for eff in c.world.effects.of(c.me):
        if eff.label == label and not eff.ended:
            return None
    return c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=label, sustain_cost=cost
    )


def _killer_of(c: Cast, victim: int) -> int | None:
    """Who struck the blow that put this creature down.

    `Dropped` and `Died` name only the creature that fell. The blow is the
    `DamageApplied` immediately before it, which is the only record of whose
    it was.
    """
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, DamageApplied) and ev.target == victim and ev.amount > 0:
            return ev.source
    return None


def _is_humanoid(c: Cast, who: int) -> bool:
    """A character has no type words at all -- `kinds_of` is empty for one --
    so "a humanoid" has to read as "anything that is not something else"."""
    words = c.kinds_of(who)
    return not words or "humanoid" in words


def _living(c: Cast, who: int) -> bool:
    return not c.is_kind("undead", on=who)


def _is_climbing(world: World, eid: int) -> bool:
    """A printed "Requirement: it must be climbing", asked of the creature.

    `Movement.using` is what it is doing now and is held past the end of the
    move; `Movement.modes` is only what it could do, and a gate on that is
    true whenever the creature has the speed at all.
    """
    mv = world.get(eid, Movement)
    return mv is not None and mv.using == "climb"


# --------------------------------------------------------------------------
# m267
# --------------------------------------------------------------------------


@power(
    "m267a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m267a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _m267_again(c: Cast) -> None:
    """The sustain half of m267a1: the same attack, against whoever is still
    held by it. `c.suffering` is what "has not yet saved against it" is --
    the hold is the effect, and anyone carrying it has failed so far.

    The m267 is left out by hand: `c.suffering` matches a label by substring
    and the anchor holding the sustain action is called after the row, so
    the creature was politely hauling itself about.
    """
    for victim in c.suffering("m267a1"):
        if victim == c.me:
            continue
        if not alive(c.world, victim) or c.is_(Condition.DEAFENED, on=victim):
            continue
        if not c.strike(on=victim):
            continue
        c.pull(3, on=victim)
        # The old hold ends first, or a repeat would leave two of them and
        # the victim would owe two saving throws for one printed sentence.
        for eff in c.world.effects.of(victim):
            if eff.label == "m267a1" and eff.source == c.me:
                c.world.effects.end(eff, "repeated")
        c.immobilized(on=victim, until=When.SAVE_ENDS)


@power(
    "m267a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_OTHER,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=9),
)
def m267a1(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the haul and the hold.

    "Deafened creatures are immune" is asked before the roll: an immune
    creature is not attacked, which is what immunity to *this effect* means
    for a row whose entire effect is the effect.
    """
    if c.first:
        c.on_sustain(_anchor(c), lambda: _m267_again(c))
    if c.is_(Condition.DEAFENED):
        return
    if c.strike():
        c.pull(3)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m267a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m267a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m2981
# --------------------------------------------------------------------------


def _beside_its_own(world: World, eid: int) -> bool:
    from combat_engine.engine.query import adjacent

    return any(
        _same_stock(world, a, eid) and adjacent(world, a, eid)
        for a in allies(world, eid)
    )


@power(
    "m2981a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 4),
)
def m2981a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2981a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.POISON),
)
def m2981a1(c: Cast) -> None:
    """"Ranged 6/12" is a thrown weapon's range increment. `Range` carries
    one number and the long increment costs an attack penalty nothing here
    applies, so the short one is the reach.

    Whether the target was already slowed is asked before the hold goes on,
    or the hold this row applies would satisfy its own condition.
    """
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.SLOWED):
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


_M2981_HIT_IN_MELEE = "the m2981 is hit by an enemy's melee attack"


@power(
    "m2981a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2981_HIT_IN_MELEE,
    on=Trigger(Hit, when=both(hits_me, by_melee), text=_M2981_HIT_IN_MELEE),
)
def m2981a2(c: Cast) -> None:
    """The step comes first, as printed, so the shot is taken from wherever
    it leaves the m2981 standing. The row that prints the shot is used
    rather than copied, so its numbers stay in one place."""
    c.shift(2)
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and alive(c.world, foe):
        use(c.world, c.me, "m2981a1", targets=[foe], spend=False)


@power(
    "m2981a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d4", 4),
)
def m2981a3(c: Cast) -> None:
    """"The target must end the slide within 3 squares" is a constraint on
    the destination, not on the distance, so the square is named outright
    rather than left to the decider -- an unconstrained slide walks people
    straight out of the three-square leash."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    here = c.here
    room = [
        sq
        for sq in spread({c.there}, 2)
        if distance(sq, here) <= 3
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) in (None, victim)
    ]
    dest = c.choose(sorted(room), "where the slide ends") if room else None
    if dest is not None:
        c.slide(2, to=dest)


_M2981_SUBJECTED = "the m2981 becomes subject to an effect"


@power(
    "m2981a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2981_SUBJECTED,
    on=Trigger(ConditionApplied, when=_save_ends_on_me, text=_SAVE_ENDS_ON_ME),
)
def m2981a4(c: Cast) -> None:
    """Narrowed to a save-ends effect, which is the only kind a saving throw
    can answer: an effect that ends on a turn boundary is not one a roll can
    shorten, so offering the row for it would spend the reaction for
    nothing.

    `c.save` takes the first save-ends effect it finds -- the triggering one
    in every case but a creature already carrying another, and the engine
    offers no way to name which.
    """
    c.save()


@power(
    "m2981a5",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2981a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Gated on who is
    standing where rather than put on and taken off as people move: the gate
    is asked when the defence is read, so nothing has to watch the board."""
    me = c.me

    def shoulder_to_shoulder(_ctx: dict[str, Any]) -> bool:
        return _beside_its_own(c.world, me)

    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, when=shoulder_to_shoulder)


# --------------------------------------------------------------------------
# m2996
# --------------------------------------------------------------------------


@power(
    "m2996a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m2996a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2996a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m2996a1(c: Cast) -> None:
    """"Loses necrotic resistance or immunity" reaches into `Defences` and
    takes the entries out, because nothing sums a resistance the way `Mods`
    sums a bonus -- `deal_damage` reads the dict directly.

    Both halves hang on one effect, so the victim gets one saving throw and
    its resistance comes back at the same moment the burning stops.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    shell = c.world.get(victim, Defences) if victim is not None else None
    if victim is None:
        return
    if shell is None:
        c.ongoing(5, DamageType.NECROTIC)
        return
    had_resist = shell.resist.pop(DamageType.NECROTIC, None)
    had_immune = DamageType.NECROTIC in shell.immune
    shell.immune.discard(DamageType.NECROTIC)

    def give_it_back() -> None:
        if had_resist is not None:
            shell.resist[DamageType.NECROTIC] = had_resist
        if had_immune:
            shell.immune.add(DamageType.NECROTIC)

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=(5, DamageType.NECROTIC),
        on_end=[give_it_back],
    )


@power(
    "m2996a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m2996a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        _all_defences(c, -5, until=When.EONT)


@power(
    "m2996a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m2996a3(c: Cast) -> None:
    """The swarm bites at the *start* of a turn only, where `c.hazard` also
    bites on entering, so the teeth are a `TurnStart` watch instead.

    `blocks_sight` is the nearest the engine has to the printed blindness:
    it is read by `cover_between` for every attack, so a line traced through
    the flies is obscured. The other half of that sentence -- a creature
    *inside* the zone seeing only three squares out -- has no vocabulary,
    and neither does the minor action that walks the zone about.
    """
    if c.first:
        me = c.me
        swarm = c.zone(
            c.area(), until=When.ENCOUNTER, blocks_sight=True, label=c.ref
        )

        def bite(ev: TurnStart) -> None:
            if ev.ghost or ev.actor == me:
                return
            if ev.actor in c.world.zones.occupants(swarm):
                c.flat(5, on=ev.actor)

        c.watch(TurnStart, bite, until=When.ENCOUNTER, on=me, label=c.ref)
    if c.strike():
        c.hit()


_M2996_DAMAGED = "the m2996 damages an enemy"


def _damaged_an_enemy(world: World, me: int, ev: DamageApplied) -> bool:
    return (
        ev.source == me
        and ev.amount > 0
        and ev.target != me
        and team(world, ev.target) is not team(world, me)
    )


@power(
    "m2996a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    damage=Damage("1d10", kind=LIMITED),
    trigger=_M2996_DAMAGED,
    on=Trigger(DamageApplied, when=_damaged_an_enemy, text=_M2996_DAMAGED),
)
def m2996a4(c: Cast) -> None:
    """A rider on a blow already landed, so it is more damage to whoever
    took it rather than a second attack. `DamageApplied` is what says an
    enemy was actually hurt; `Hit` would pay out on a blow a resistance ate
    whole."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None and alive(c.world, victim):
        c.hit(on=victim)


_M2996_FELLED = "an enemy reduces the m2996 to 0 hit points"


@power(
    "m2996a5",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    damage=Damage("2d10", 5, dtype=DamageType.NECROTIC),
    trigger=_M2996_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M2996_FELLED),
)
def m2996a5(c: Cast) -> None:
    """A death throe. `Dropped` names only who fell, so who felled them is
    read back off the blow immediately before it -- there is no other record
    of whose it was."""
    killer = _killer_of(c, c.me)
    if killer is None or killer == c.me:
        return
    if team(c.world, killer) is team(c.world, c.me):
        return
    c.hit(on=killer)


# --------------------------------------------------------------------------
# m307
# --------------------------------------------------------------------------


@power(
    "m307a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m307a0(c: Cast) -> None:
    """Doubling is `DamageRolled` in the interrupt window: the event carries
    the number, `deal_damage` reads it back, and nothing else in the engine
    multiplies -- `c.bonus` only ever adds.

    Which blows count is read off the striker's own `Powers.basic`, because
    a monster's basic attack is one of its own rows and there is no other
    way to tell it from the rest of them.
    """
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def redouble(ev: DamageRolled) -> None:
        if ev.source == me or ev.amount <= 0:
            return
        if ev.source not in c.world.zones.occupants(ring):
            return
        if not _same_stock(c.world, ev.source, me):
            return
        known = c.world.get(ev.source, Powers)
        if known is not None and ev.detail == known.basic:
            ev.amount *= 2

    c.watch(
        DamageRolled, redouble, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=c.ref,
    )


@power(
    "m307a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 8),
)
def m307a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m307a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m307a2(c: Cast) -> None:
    """Two swings of the row that prints them, chosen one at a time: the
    second is aimed after the first has resolved, which is the printed
    order and matters when the first one kills."""
    for _ in range(2):
        reachable = sorted(f for f in c.within(1, side="enemy") if alive(c.world, f))
        foe = c.choose(reachable, "who the jaws find") if reachable else None
        if foe is None:
            return
        use(c.world, c.me, "m307a1", targets=[foe], spend=False)


@power(
    "m307a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 7, dtype=DamageType.ACID),
)
def m307a3(c: Cast) -> None:
    """"Save ends both" wants the weakness and the burning on one effect, so
    the victim gets one saving throw and not two."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.WEAKENED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.ACID),
        )


# --------------------------------------------------------------------------
# m320
# --------------------------------------------------------------------------


@power(
    "m320a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m320a0(c: Cast) -> None:
    """Starting a turn in it, so a `TurnStart` watch rather than anything on
    the zone itself -- `c.burns` is the hostile half of the same shape and
    there is no kindly one."""
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def mend(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in allies(c.world, me):
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.heal(3, on=ev.actor)

    c.watch(TurnStart, mend, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m320a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m320a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m320a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.AREA],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m320a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m320a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=9),
)
def m320a3(c: Cast) -> None:
    """No damage at all -- the hit is the hold, and the rough ground is laid
    once for the whole power whether anything was hit or not."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, difficult=True, label=c.ref)
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m325
# --------------------------------------------------------------------------


@power(
    "m325a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m325a0(c: Cast) -> None:
    """Ending a turn in it, which is neither of the two moments `c.hazard`
    bites at, so this is a `TurnEnd` watch. Who is inside is asked of the
    aura as the turn ends rather than tracked."""
    me = c.me
    ring = c.aura(3, until=When.ENCOUNTER, label=c.ref)

    def press(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
        c.slide(2, on=ev.actor)

    c.watch(TurnEnd, press, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m325a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m325a1(c: Cast) -> None:
    """Not `c.insubstantial`: that condition halves everything, and the
    printed line exempts force damage and switches itself off.

    Halving is done on `DamageRolled` in the interrupt window, which is
    where the number still exists and can be changed. Radiant damage is read
    off `DamageApplied` -- after the halving, so the blow that puts the
    trait out is itself still halved, which is what "whenever it takes
    radiant damage, it loses this trait" means.
    """
    me = c.me
    #: Non-empty while the trait is out. A dict rather than a flag because a
    #: closure may not rebind a name in its enclosing scope.
    lapsed: dict[str, bool] = {}

    def soften(ev: DamageRolled) -> None:
        if ev.target != me or lapsed or ev.dtype is DamageType.FORCE:
            return
        ev.amount //= 2

    def seared(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            lapsed["out"] = True

    def mended(ev: TurnStart) -> None:
        if ev.actor == me:
            lapsed.clear()

    c.watch(
        DamageRolled, soften, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=c.ref,
    )
    c.watch(DamageApplied, seared, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, mended, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m325a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m325a2(c: Cast) -> None:
    """The new one arrives on the m325's own next turn, not at the moment of
    the kill, so the square is remembered and spent later.

    `c.summon` is both halves: `loader.spawn` alone leaves a creature
    standing outside the initiative order, never acting, and the printed
    line says outright that it rolls a new initiative check.
    """
    me = c.me
    graves: list[Square] = []

    def fell(ev: Died) -> None:
        if ev.actor == me or not _is_humanoid(c, ev.actor):
            return
        if _killer_of(c, ev.actor) != me:
            return
        pos = c.world.get(ev.actor, Position)
        if pos is not None:
            graves.append(pos.square)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not graves:
            return
        for square in list(graves):
            graves.remove(square)
            free = c.world.grid.occupant(square) is None
            c.summon("m325", at=square if free else None)

    c.watch(Died, fell, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m325a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC),
)
def m325a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        _all_defences(c, -2, until=When.SAVE_ENDS)


@power(
    "m325a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m325a4(c: Cast) -> None:
    """"Its nearest ally" is measured from the victim, not from the m325,
    and the swing is the victim's -- `c.grant_attack` rolls whatever that
    creature's own basic attack is, which is the printed "basic attack"."""
    victim = c.target
    if not c.strike():
        c.hit(half=True)
        c.slide(2)
        return
    c.hit()
    c.slide(5)
    if victim is None:
        return
    near = [a for a in allies(c.world, victim) if alive(c.world, a)]
    if not near:
        return
    from combat_engine.engine.query import distance_between

    friend = min(sorted(near), key=lambda a: distance_between(c.world, victim, a))
    c.grant_attack(victim, on=friend)


# --------------------------------------------------------------------------
# m4795
# --------------------------------------------------------------------------


@power(
    "m4795a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m4795a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4795a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3, dtype=DamageType.POISON),
)
def m4795a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4795a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m4795a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m4795a4",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_climbing,
    requires_text="the m4795 must be climbing",
)
def m4795a4(c: Cast) -> None:
    """It flings itself off the wall, so the flight is granted for the move
    and taken back at the end of the turn: `mode_of` picks flight over a
    walk when the creature has it, which is what makes `c.move` a flight
    rather than a run."""
    c.mode("fly", 5, until=When.EOT)
    c.move(5)


# --------------------------------------------------------------------------
# m4804
# --------------------------------------------------------------------------


@power(
    "m4804a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m4804a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4804a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m4804a1(c: Cast) -> None:
    """"Save ends both" -- so the watch that charges the victim for
    provoking rides on the *same* effect as the combat advantage, and one
    saving throw ends the pair. `OpportunityWindow` is what the engine emits
    when somebody gives an opening; `provoker` is the one that did."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hold = c.grants_advantage(until=When.SAVE_ENDS, to="allies")
    if victim is None or hold is None:
        return

    def tithe(ev: OpportunityWindow) -> None:
        if ev.provoker == victim and not hold.ended:
            c.flat(5, on=victim)

    hold.subs.append(c.world.bus.on(OpportunityWindow, tithe, owner=c.me))


@power(
    "m4804a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("3d6", 11, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4804a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4804a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4804a3(c: Cast) -> None:
    """The bonus goes on before the walk, because the openings it answers
    are taken during it, and it is clocked on this turn's end rather than
    the next one's -- "provoked by this movement" is over when the move is.

    `opportunity` is a key the attack context carries, so the gate is a
    one-liner; a gate on a key the context does not carry is silently false.
    """
    c.bonus(
        AC, 4, on=c.me, until=When.EOT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(4)
    for foe in sorted(c.within(1, side="enemy")):
        c.grants_advantage(on=foe, until=When.EONT)


_M4804_FELLED = "the m4804 drops to 0 hit points"


@power(
    "m4804a4",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    trigger=_M4804_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4804_FELLED),
)
def m4804a4(c: Cast) -> None:
    """A death throe, so the adjacency is asked as it falls. "The end of his
    or her next turn" is the *victim's* clock, which is `EOTNT`."""
    for foe in sorted(c.within(1, side="enemy")):
        c.blinded(on=foe, until=When.EOTNT)


# --------------------------------------------------------------------------
# m4887
# --------------------------------------------------------------------------


@power(
    "m4887a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m4887a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4887a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
)
def m4887a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m4887a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=9),
)
def m4887a3(c: Cast) -> None:
    """The swing is the ally's, granted rather than rolled here -- and which
    ally is the chooser's business, the printed line naming only that it be
    adjacent to the target."""
    if not c.strike():
        return
    c.immobilized(until=When.SAVE_ENDS)
    victim = c.target
    if victim is None:
        return
    near = sorted(
        a
        for a in c.within(1, of=victim, side="ally")
        if a != c.me and alive(c.world, a)
    )
    friend = c.choose(near, "which ally tears at it") if near else None
    if friend is not None:
        c.grant_attack(friend, on=victim)


@power(
    "m4887a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4887a4(c: Cast) -> None:
    """The zone bites on entering and on *ending* a turn there, and only the
    living: `c.hazard` bites on entering and on starting, and asks nothing
    about who it is biting, so both watches are written out.

    The Effect line lands whether anything was hit or not, which is why the
    zone is laid before the roll.
    """
    if c.first:
        me = c.me
        pall = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
        struck: dict[int, int] = {}

        def bite(who: int) -> None:
            if who == me or not _living(c, who) or struck.get(who) == c.world.round:
                return
            struck[who] = c.world.round
            c.flat(5, dtype=DamageType.NECROTIC, on=who)

        def on_enter(ev: ZoneEntered) -> None:
            if ev.zone == pall:
                bite(ev.actor)

        def on_end(ev: TurnEnd) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(pall):
                bite(ev.actor)

        c.watch(ZoneEntered, on_enter, until=When.ENCOUNTER, on=me, label=c.ref)
        c.watch(TurnEnd, on_end, until=When.ENCOUNTER, on=me, label=c.ref)
    if c.target is not None and not _living(c, c.target):
        return
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m885
# --------------------------------------------------------------------------

#: The label m885a4 leaves on its owner, and the thing m885a1 requires.
_M885_UNBOUND = "m885a4"


def _unbound(world: World, eid: int) -> bool:
    return any(
        eff.label == _M885_UNBOUND and not eff.ended for eff in world.effects.of(eid)
    )


@power(
    "m885a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 7),
)
def m885a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m885a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d12", 5),
    requires=_unbound,
    requires_text="the m885 must be affected by m885a4",
)
def m885a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m885a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m885a2(c: Cast) -> None:
    """"Cannot use encounter attack powers, daily attack powers, or utility
    powers" is read as every row that is not an at-will: an encounter or
    daily attack is one of those by usage, and a utility power of either
    usage is the rest of the sentence. An at-will is what it is left with.

    One effect holds the whole list, so it is one saving throw and the rows
    all come back together. The Aftereffect hangs on `on_end` rather than on
    `escalate`: escalation runs on a *failed* save and an aftereffect is
    what happens when the first effect finally ends.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    known = c.world.get(victim, Powers) if victim is not None else None
    if victim is None or known is None:
        return
    barred = {
        ref
        for ref in known.all
        if (p := get(ref)) is not None
        and p.usage in (Usage.ENCOUNTER, Usage.DAILY)
        and ref not in known.forbidden
    }

    def released() -> None:
        known.forbidden -= barred
        if alive(c.world, victim):
            c.dazed(on=victim, until=When.EOTNT)

    known.forbidden |= barred
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, on_end=[released]
    )


@power(
    "m885a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 5, dtype=DamageType.LIGHTNING),
)
def m885a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


_M885_BLOODIED = "the m885 is first bloodied"


@power(
    "m885a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger=_M885_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M885_BLOODIED),
)
def m885a4(c: Cast) -> None:
    """"First bloodied" needs no latch: `Bloodied` is emitted on the
    crossing and the row is an encounter power, so the second crossing finds
    it spent.

    The Effect line is `c.forbid` over everything else it owns -- the row
    stays in its list and cannot be reached, which is what "cannot use" is
    as against spending it. The named hold left behind is what m885a1 reads
    for its printed Requirement.
    """
    if c.first:
        c.effect(_M885_UNBOUND, until=When.ENCOUNTER, on=c.me)
        known = c.world.get(c.me, Powers)
        for ref in list(known.all) if known else []:
            if ref not in ("m885a1", c.ref):
                c.forbid(ref, on=c.me, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.push(3)
