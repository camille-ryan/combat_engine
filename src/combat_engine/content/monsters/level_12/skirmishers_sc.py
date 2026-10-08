"""Monster abilities, level 12, skirmishers: the thirty-five stat blocks the
two files beside this one left.

Numbers load from `game.db`. The attack line is written exactly as printed --
`Attack(vs=AC, printed=17)` -- and the damage line goes in the header as
data, so the engine can take the level term back out and rescale a blow to
another edition's maths.

The conventions of the eleven levels below are kept:

* a **trait** costs no action, has no target and arms the watches that hold
  it for the rest of the fight, whatever the compendium's action column says;
* a card with no printed range at all is melee 1, and a printed band like
  "5/10" takes the short number;
* a close burst or blast naming no target set takes **enemies**; one that
  prints "creatures in the burst" takes creatures;
* a row that moves *and* swings takes the swing first where anything is
  already in reach, because the movement picks its own destination and one
  taken first can leave the target behind -- except where closing the
  distance is the whole point of the printed line, which is said in the row;
* a printed "shift" with no number is one square, which is the rule rather
  than a guess.

Eight things this file had to settle.

**"If it has combat advantage" is read off the result, never asked again.**
Six rows here pay out for having had the edge, and a one-shot grant has been
spent by the time the body runs. `c.strike()` hands back the `AttackResult`
and `.advantage` is the question, which is what m2257a0 and m2349a3 ask.

**An extra die for having the edge is a gated modifier, not a branch.** Seven
traits print "deals 2d6 extra damage against any target it has combat
advantage against", and the gate has to be read at damage time against the
creature actually being hit -- `_edge_on_target` is the settled shape, and
`_weapon_swing` narrows it to the melee and ranged attacks the cards name,
because a close burst is neither.

**"Each failed saving throw" and "first failed saving throw" are the same
hook with different bookkeeping.** `Effect.escalate` runs on **every** failed
save, so m5162a0's ongoing climb is the bare callback and m2337a0's and
m2608a3's one-step worsenings close over a list they pop. An Aftereffect is
`on_end`, which is the moment the first hold goes however it goes.

**Three briefs name a creature only by its printed name.** m1593a3, m1593a4
and m2341a5 each turn entirely on "another creature of a particular sort",
with no ref anywhere in the brief to write it from, so each carries
`spec.monster_ref()` and nothing is guessed. m4310a5 is the same gap in a row
that still plays: the shape it takes is real and its stat block is the
missing clause, so that one is `dropped=` and the rows gated on it work.

**Two briefs arrived malformed and are reported rather than guessed.**
m2341a1 and m2349a1 each print an attack line with no defence at all
("+15 vs ; 4d8+5 damage.") in front of an Effect line naming the attacks they
really make; the Effect line is what is written and the orphan line is
dropped as extraction noise. m2105a3 reads "if it is in the space of a
m2105 it teleports to the space of a m2105", which is the creature's own ref
standing in for something else, and is unwritable as it stands.

**A grab that has to be let go of is `c.escape(auto=True)`.** m5097a3's
printed Effect ends its own grab before the victim is taken off the board,
and there is no "release" verb -- the escape attempt that cannot fail is the
one thing that unwinds the relation and the effect together.

**An aura that grows cannot be resized.** `Zone.aura` is the radius and
`Zones.refresh` recomputes the footprint from it, but nothing widens a live
one -- so m6610a5 dispels the aura and lays a fresh one two squares wider
under the *same label*, which is what the trait's watch reads it by, and the
radius is read back off the zone so both recharge sentences have a number to
ask about.

**"Grants combat advantage to any enemy" has no single word.**
`c.grants_advantage`'s `to=` names one beneficiary, a side of the caster's or
an id, and the caster's *enemies* are none of those -- so m2322a1 lays one
grant per enemy on the one clock, which is the relation the method would have
laid anyway.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_05.skirmishers_sa import _edge_on_target
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import _is_bloodied
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.skirmishers import _underground
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.content.monsters.level_11.skirmishers_sc import (
    _foe_within,
    _through_them,
)
from combat_engine.content.monsters.level_12.skirmishers import _either_swing
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
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
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Mod,
    Moved,
    MoveStart,
    Powers,
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    by_melee,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import spread
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    enemies,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_me

# ==========================================================================
# Shared shapes
# ==========================================================================

#: What "a melee or a ranged attack" means as a `Range.kind`. A close burst
#: is neither, which is the whole reason the seven extra-damage traits here
#: cannot simply be an ungated damage modifier.
_WEAPON_RANGES = ("melee", "ranged")


def _weapon_swing(ctx: dict[str, Any]) -> bool:
    """Is the blow this modifier is being read for a melee or ranged one?

    The damage context carries no reach, and the attack context's `ranged`
    answers only half of it. Both carry the row that swung, so the reach is
    looked up from that.
    """
    row = get(str(ctx.get("power") or ""))
    return row is not None and row.reach_of(ctx.get("branch", 0)).kind in _WEAPON_RANGES


def _weapon_blow(ev: Any) -> bool:
    """Did that damage come off a melee or ranged attack? `DamageRolled`
    carries the row as `detail` rather than as `power`."""
    row = get(str(getattr(ev, "detail", "") or ""))
    return row is not None and row.reach_of(0).kind in _WEAPON_RANGES


def _extra_with_the_edge(c: Cast, dice: str, *, dtype: DamageType | None = None) -> None:
    """"Deals <dice> extra damage against any target it has combat advantage
    against", on its melee and ranged attacks only."""
    gate = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice=dice,
        dtype=dtype,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _weapon_swing(ctx) and gate(ctx),
    )


def _grabbing_something(world: World, eid: int) -> bool:
    """The printed Requirement "must have a creature grabbed"."""
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _my_captive(c: Cast) -> int | None:
    held = sorted(w for w in c.grabbing() if alive(c.world, w))
    return held[0] if held else None


def _pair_penalty(
    c: Cast, value: int, defences: tuple[Any, ...], *, until: When, on: int
) -> Effect | None:
    """A penalty to two named defences as **one** effect.

    `c.penalty` lays one per defence, which is two saving throws where the
    card prints one -- and a victim that shook off its Reflex penalty while
    keeping its AC one. `_all_defences` is the same argument for all four.
    """
    mods = [(on, Mod(what=d.value, value=value, kind="untyped", label=c.ref))
            for d in defences]
    return c.world.effects.apply(on, c.me, until, label=c.ref, mods=mods)


def _burning(world: World, who: int) -> bool:
    """Is that creature taking ongoing damage from anything at all?"""
    return any(e.ongoing and not e.ended for e in world.effects.of(who))


def _closest_of_its_own(c: Cast, victim: int) -> int | None:
    """The nearest creature on the victim's side, for "its closest ally".

    Asked of `team` rather than of `c.within(side=)`, whose words are the
    caster's: the victim's allies are the caster's enemies and the sides have
    to be compared from the victim's end.
    """
    mine = team(c.world, victim)
    near = sorted(
        (distance_between(c.world, victim, w), w)
        for w in (*c.allies(), *c.enemies(), c.me)
        if w != victim and alive(c.world, w) and team(c.world, w) is mine
    )
    return near[0][1] if near else None


def _moving_strike(
    c: Cast, span: int, swing: Callable[[], None], *, reach: int = 1
) -> None:
    """"Moves its speed and makes an attack at any point during the move."

    The swing goes first where anything is already in reach, because `c.move`
    picks its own destination and one taken first can leave every target
    behind; with nobody in reach it closes and then looks, which is the same
    printed sentence read the other way round. The waiver is blanket rather
    than the printed "away from the target of the attack", because
    `c.no_provoke` names a creature or everybody and cannot name a reason.
    """
    waiver = c.no_provoke(until=When.EOT)
    try:
        if any(c.distance(foe) <= reach for foe in c.enemies()):
            swing()
            c.move(span)
        else:
            c.move(span)
            swing()
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the run is over")


def _shift_among(c: Cast, span: int, radius: int) -> bool:
    """Shift that far and end where a burst of `radius` catches the most.

    `c.shift` with no `to` offers the decider every square in range, and with
    no decider installed `World.decide` takes the first in sorted order --
    the lowest square on the board, every time. A row that moves and *then*
    bursts where it lands has to name the square or it reliably arrives
    somewhere nobody is standing, which is the trap `c.overrun`'s own
    docstring records for the same reason.
    """
    foes = [foe for foe in c.enemies() if alive(c.world, foe)]
    options = sorted(c.world.reachable_squares(c.me, span))
    if not foes or not options:
        return c.shift(span)

    def caught(sq: tuple[int, int]) -> int:
        return sum(
            1
            for foe in foes
            if min(
                max(abs(sq[0] - s[0]), abs(sq[1] - s[1]))
                for s in squares(c.world, foe)
            )
            <= radius
        )

    best = max(caught(sq) for sq in options)
    ranked = [sq for sq in options if caught(sq) == best]
    return c.shift(
        span, to=c.world.decide(c.me, "shift", ranked, f"{c.ref}: where it comes up")
    )


def _aura_radius(c: Cast, label: str) -> int:
    """How wide a live aura of the caster's is now, read off the zone."""
    for zid, zone in c.world.zones.all():
        if zone.label == label and c.made_by(zid) == c.me:
            return int(getattr(zone, "aura", 0) or 0)
    return 0


def _hit_with_its_basic(world: World, me: int, ev: Hit) -> bool:
    """"Hits an enemy with a melee basic attack." `Powers.basic` is the ref a
    monster's basic attack points at, so the row that swung can be compared
    against it rather than guessed at from the reach."""
    known = world.get(me, Powers)
    return (
        getattr(ev, "attacker", None) == me
        and known is not None
        and str(getattr(ev, "power", "") or "") == known.basic
    )


# ==========================================================================
# m1102
# ==========================================================================


_M1102_FELL = "the m1102 drops to 0 hit points"
_M1102_ON_MY_ALLY = "an enemy moves within 2 squares of the m1102 and attacks an ally"


def _struck_my_ally_nearby(world: World, me: int, ev: AttackDeclared) -> bool:
    """Both halves of the printed trigger. The move is not asked about: an
    enemy that is within 2 squares and swinging at an ally got there
    somehow, and `AttackDeclared` is the only window the printed reaction
    can answer."""
    foe, victim = getattr(ev, "attacker", None), getattr(ev, "target", None)
    if foe is None or victim is None or victim == me:
        return False
    if team(world, foe) is team(world, me) or team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, foe) <= 2


@power(
    "m1102a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m1102a0(c: Cast) -> None:
    """The extra dice are owed for a hold the victim was *already* in, so the
    question is asked before this row's own immobilisation lands -- asked
    after, every living target qualifies and the clause pays every time."""
    if not c.strike():
        return
    already = (
        not c.is_kind("undead")
        and (
            c.is_(Condition.IMMOBILIZED)
            or c.is_(Condition.STUNNED)
            or c.is_(Condition.UNCONSCIOUS)
        )
    )
    c.hit()
    if already:
        c.damage("2d6")
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1102a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    trigger=_M1102_FELL,
    on=Trigger(Dropped, about_me, _M1102_FELL),
)
def m1102a1(c: Cast) -> None:
    """A death throe with no attack roll: ten points, flat, to each enemy in
    the burst. `Dropped` names its subject `actor`, which is what
    `about_me` reads."""
    c.flat(10, dtype=DamageType.NECROTIC)


@power(
    "m1102a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M1102_ON_MY_ALLY,
    on=Trigger(AttackDeclared, _struck_my_ally_nearby, _M1102_ON_MY_ALLY),
)
def m1102a2(c: Cast) -> None:
    """The step has to end beside the creature being answered, which a bare
    `c.shift` cannot say -- it offers the decider every square in range. The
    printed recharge sentence sits on top of the die the database files, and
    the two only ever agree to give the row back sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    _shift_beside(c, foe, 1)
    c.basic(on=foe)


# ==========================================================================
# m1140
# ==========================================================================


_M1140_FELL = "the m1140 drops to 0 hit points"


@power(
    "m1140a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m1140a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1140a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.POLYMORPH],
    attack=Attack(vs=WILL, printed=15),
    trigger=_M1140_FELL,
    on=Trigger(Dropped, about_me, _M1140_FELL),
    dropped=("c.contract(ref)",),
)
def m1140a1(c: Cast) -> None:
    """No damage line -- the hold the hit lays is the whole of the hit, so
    there is nothing for `c.hit()` to deal.

    The affliction the hit confers is a block of its own with its own stages
    and the brief gives no ref for it, so the curse relation is laid and the
    stages are the dropped clause.
    """
    if c.strike():
        c.curse()


@power(
    "m1140a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m1140a2(c: Cast) -> None:
    """The two halves are printed in the order they cannot happen in: nothing
    slides into an occupied square, and the square in question is this
    creature's own. So the step is taken first and the slide is aimed at the
    square it vacated, which is the only arrangement in which both sentences
    are true at the end of the action."""
    foe = c.target
    if foe is None:
        return
    was = c.here
    c.shift(2)
    if c.here != was:
        c.slide(1, on=foe, to=was)


@power(
    "m1140a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1140a3(c: Cast) -> None:
    """Deliberately inert: knowing where something is, at any distance, is not
    a thing a board can be asked and changes nothing in a fight."""
    c.note("m1140a3: it senses the distance and direction of what it guards")


# ==========================================================================
# m1593
# ==========================================================================


#: The two attacks m1593 chooses between, with how far each reaches.
_M1593_SWINGS = {"m1593a0": 3, "m1593a1": 2}

_M1593_BLOODIED_ONE = "the m1593's attack bloodied an enemy"
_M1593_FELL = "the m1593 drops to 0 hit points"


@power(
    "m1593a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 5),
)
def m1593a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1593a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m1593a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1593a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(3),
    target=NO_TARGET,
    trigger=_M1593_BLOODIED_ONE,
    on=Trigger(Bloodied, by_me, _M1593_BLOODIED_ONE),
)
def m1593a2(c: Cast) -> None:
    """Either of its two attacks, and which one is legal depends on who is
    being aimed at -- one reaches three squares and the other two. `by_me`
    reads `Bloodied.source`, which is what makes "its attack bloodied an
    enemy" a declared trigger rather than a derived one."""
    _either_swing(c, _M1593_SWINGS)


@power(
    "m1593a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m1593a3(c: Cast) -> None:
    """The whole clause is about allies of one particular sort, and the brief
    identifies that sort only by its printed name -- there is no ref anywhere
    in it to write the test from, and `c.is_kind` wants a word. Nothing here
    is writable without one, so nothing is written."""


@power(
    "m1593a4",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m1593a4(c: Cast) -> None:
    """Same gap as m1593a3, and the whole row turns on it: both the
    requirement and the creature that swaps into the vacated square are the
    one sort of ally the brief names only by name."""


@power(
    "m1593a5",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M1593_FELL,
)
def m1593a5(c: Cast) -> None:
    """It gets back up unless the blow was acid or fire.

    `c.revives_unless` implements nothing -- it records the fact so the AI
    policy stops writing off a body that is going to stand -- so the body
    does the work: a `DamageApplied` watch remembers what the last blow was,
    because `Dropped` says who struck it and not with what, and a `Dropped`
    watch heals inside that window.

    The printed "on its next turn" is not kept. `Effects.bereave` clears
    everything a corpse is the source of the instant `Dropped` is announced,
    so a hold waiting a turn on the dead creature is swept away before it can
    pay -- healing inside the window is the only moment there is.
    """
    me = c.me
    c.revives_unless(DamageType.ACID, DamageType.FIRE, on=me)
    last: list[bool] = []

    def struck(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0:
            last.append(ev.dtype in (DamageType.ACID, DamageType.FIRE))
            del last[:-1]

    def fell(ev: Dropped) -> None:
        if ev.actor != me or (last and last[-1]):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp < 10:
            c.heal(10 - max(0, health.hp), on=me)

    c.watch(DamageApplied, struck, until=When.ENCOUNTER, on=me, label=f"{c.ref} blow")
    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1623
# ==========================================================================


_M1623_SHIFTED_BESIDE = "an adjacent creature shifts"


def _shifted_beside_me(world: World, me: int, ev: MoveStart) -> bool:
    return (
        getattr(ev, "actor", None) != me
        and getattr(ev, "kind_", "") == "shift"
        and distance_between(world, me, ev.actor) <= 1
    )


@power(
    "m1623a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 6),
)
def m1623a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1623a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires_text="requires a longsword",
)
def m1623a1(c: Cast) -> None:
    """The printed Requirement is the weapon in its hand, which is what the
    card shows rather than something a board arranges; it is kept as text
    and not as a gate, because a gate that is false at the wrong moment
    refuses the row outright."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
        c.dazed(until=When.EONT)


@power(
    "m1623a2",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M1623_SHIFTED_BESIDE,
    on=Trigger(MoveStart, _shifted_beside_me, _M1623_SHIFTED_BESIDE),
)
def m1623a2(c: Cast) -> None:
    """`MoveStart` and not `MoveEnd`: the printed line is about an *adjacent*
    creature, and by the end of a shift it has gone -- adjacency is false
    exactly when the row should fire. `MoveStart` is a `Decision`, so
    refusing it is what "immediately ends its movement" means here, and the
    swing goes in first because the card prints it first."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.use_power("m1623a0", on=foe)
    c.cancel()


@power(
    "m1623a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=17),
    dropped=("c.no_invisibility()",),
)
def m1623a3(c: Cast) -> None:
    """No damage line: the two holds are the hit.

    "Grants combat advantage to all attackers" is wider than any one word
    `to=` takes, so it is laid once per enemy of the target's -- which is the
    relation the method lays anyway. Concealment is `c.no_cover`; not
    benefiting from *invisibility* is a third thing, and nothing takes that
    away from a creature for everybody at once.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.no_cover(until=When.EONT)
    for watcher in (c.me, *sorted(c.allies())):
        if watcher != victim:
            c.grants_advantage(on=victim, to=watcher, until=When.EONT)


@power(
    "m1623a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1623a4(c: Cast) -> None:
    _extra_with_the_edge(c, "2d6")


@power(
    "m1623a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m1623a5(c: Cast) -> None:
    """"Gains combat advantage against an adjacent creature" is the same
    relation read from the other end: nothing hangs a modifier on combat
    advantage, so the creature is made to grant it."""
    if c.target is not None:
        c.grants_advantage(to="me", until=When.EONT)


# ==========================================================================
# m1908
# ==========================================================================


_M1908_FELL = "the m1908 drops to 0 hit points"


@power(
    "m1908a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d4", 5),
)
def m1908a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1908a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d4", 5),
)
def m1908a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    `Range` holds and the one it can throw at without a penalty."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1908a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d4", 5, kind=LIMITED, half_on_miss=True),
)
def m1908a2(c: Cast) -> None:
    """`half_on_miss` is declared data and nothing in the engine reads it, so
    the Miss branch is written -- and the necrotic die beside the weapon
    damage is halved with it, because the printed Miss line is half of the
    whole blow."""
    if c.strike():
        c.hit()
        c.damage("1d12", dtype=DamageType.NECROTIC)
    else:
        c.hit(half=True)
        c.half_damage("1d12", dtype=DamageType.NECROTIC)


@power(
    "m1908a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m1908a3(c: Cast) -> None:
    """"Hit or Miss" means the step is owed once for the whole burst and
    however the rolls went, so it is taken on the last target rather than per
    target or inside the hit branch."""
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
    if c.last:
        c.shift(2)


@power(
    "m1908a4",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    trigger=_M1908_FELL,
    on=Trigger(Dropped, about_me, _M1908_FELL),
)
def m1908a4(c: Cast) -> None:
    """A death throe whose hit line is a burn and no damage, so there is
    nothing for `c.hit()` to deal."""
    if c.strike():
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1908a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1908a5(c: Cast) -> None:
    """Melee only, which the card says and the others of this shape do not."""
    gate = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="2d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: gate(ctx) and _weapon_swing(ctx) and not ctx.get("ranged"),
    )


# ==========================================================================
# m2007
# ==========================================================================


@power(
    "m2007a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d4", 6),
)
def m2007a0(c: Cast) -> None:
    """"Before or after the attack" is settled towards after: the step picks
    its own destination and one taken first can carry the creature out of
    reach of the target the row was handed."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
    c.shift(2)


@power(
    "m2007a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("5d4", 8, kind=LIMITED),
)
def m2007a1(c: Cast) -> None:
    """"Knocked prone and slowed (save ends)" is two clocks, not one: prone
    lasts until the creature stands and the save is the slow's."""
    if c.strike():
        c.hit()
        c.prone()
        c.slowed(until=When.SAVE_ENDS)
    c.shift(2)


# ==========================================================================
# m2053
# ==========================================================================


@power(
    "m2053a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
)
def m2053a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2053a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 6),
)
def m2053a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2053a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 6, kind=LIMITED),
    requires_text="requires a rapier",
)
def m2053a2(c: Cast) -> None:
    """`c.teleport`'s `who` is the creature that moves, so the victim is
    named there rather than in `on`. "Cannot be teleported into an unsafe
    space" is what the destination filter already enforces."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        c.teleport(5, who=victim)


@power(
    "m2053a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d8", 6, kind=LIMITED),
    requires_text="requires a rapier",
)
def m2053a3(c: Cast) -> None:
    """Declared with no target: the blink happens first and the printed
    target is "an adjacent creature", which is a different set once the
    creature has moved. A header target list is chosen before the body
    runs."""
    c.teleport(5)
    foe = _adjacent_foe(c, c.ref)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.dazed(until=When.SAVE_ENDS, on=foe)


@power(
    "m2053a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2053a4(c: Cast) -> None:
    _extra_with_the_edge(c, "2d6")


@power(
    "m2053a5",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2053a5(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m2105
# ==========================================================================


#: The two type words the card names beside "another of its own sort". Both
#: are creature types the tree already asks about; the third is read off this
#: creature's own type words so that it needs no word at all.
_M2105_KIN = ("drow", "demon")


@power(
    "m2105a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m2105a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2105a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m2105a1(c: Cast) -> None:
    """The printed recharge sentence is armed once for the whole burst, not
    once per target."""
    me = c.me
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2105a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2105a2(c: Cast) -> None:
    """Three squares, or beside one of the creatures the card lists. The third
    sort it names is itself, so that one is read off its own type words
    rather than spelled: `c.kinds_of` of the caster is exactly "another of
    this sort"."""
    wanted = set(_M2105_KIN) | c.kinds_of(on=c.me)
    beside = sorted(
        who
        for who in (*c.allies(), *c.enemies())
        if alive(c.world, who) and c.can_see(who) and (c.kinds_of(on=who) & wanted)
    )
    picked = (
        c.choose(beside, f"{c.ref}: blink beside one of them", optional=True)
        if beside
        else None
    )
    here = squares(c.world, c.me)
    free = (
        sorted(
            sq
            for sq in spread(squares(c.world, picked), 1) - here
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        )
        if picked is not None
        else []
    )
    where = (
        c.world.decide(c.me, "teleport", free, f"{c.ref}: beside it") if free else None
    )
    # A Large creature needs its whole footprint to fit, and a single square
    # beside a Medium one often will not take it -- so the blink is tried and
    # the three squares the card also offers are what it falls back to.
    if where is None or not c.teleport(99, to=where):
        c.teleport(3)


@power(
    "m2105a3",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    todo=("etl.monster.ability_text()",),
)
def m2105a3(c: Cast) -> None:
    """The brief reads "if it is in the space of a m2105 it teleports to any
    other square in the space of a m2105", which is this creature's own ref
    standing in for whatever the sentence is really about -- a creature
    cannot be inside itself and the row says nothing in that reading. There
    is no second ref in the brief to recover it from."""


# ==========================================================================
# m2257
# ==========================================================================


@power(
    "m2257a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m2257a0(c: Cast) -> None:
    """"If it has combat advantage" is read off the result. Asking
    `has_combat_advantage` again is too late -- a one-shot grant has been
    spent by the time the hit resolves."""
    swing = c.strike()
    if not swing:
        return
    c.hit()
    c.damage("1d6", dtype=DamageType.PSYCHIC)
    if swing.advantage:
        c.shift(3)


@power(
    "m2257a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 4, kind=LIMITED),
)
def m2257a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.PSYCHIC)
        c.dazed(until=When.EONT)
    c.shift(3)


@power(
    "m2257a2",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2257a2(c: Cast) -> None:
    """Declared with no target because the printed set is "itself or an ally",
    and `Target` has no word that holds both."""
    near = sorted(w for w in c.allies() if c.distance(w) <= 10 and alive(c.world, w))
    who = c.choose([c.me, *near], f"{c.ref}: who flies")
    if who is None:
        return
    c.mode("fly", 5, until=When.EOT, on=who)
    c.move(5, who=who, at="fly")


@power(
    "m2257a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2257a3(c: Cast) -> None:
    gate = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: gate(ctx) and _weapon_swing(ctx) and not ctx.get("ranged"),
    )


# ==========================================================================
# m2322
# ==========================================================================


_M2322_SPLIT = "the m2322 is first bloodied"
#: The hold a4 lays and that a2, a3 and a5 are printed as requiring.
_M2322_SHED = "m2322a4"


def _has_shed(world: World, eid: int) -> bool:
    return any(e.label == _M2322_SHED and not e.ended for e in world.effects.of(eid))


@power(
    "m2322a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m2322a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2322a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d6", 5, kind=LIMITED),
)
def m2322a1(c: Cast) -> None:
    """The Effect line is owed once however the rolls went, and "to any enemy"
    is wider than any word `to=` takes -- so it is one grant per enemy, on
    the one clock the printed sentence gives."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    for foe in sorted(c.enemies()):
        c.grants_advantage(on=c.me, to=foe, until=When.SONT)


@power(
    "m2322a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 5),
    requires=_has_shed,
    requires_text="usable only while affected by m2322a4",
    dropped=("c.contract(ref)",),
)
def m2322a2(c: Cast) -> None:
    """The secondary attack is rolled by hand because the header carries one
    attack line and this card prints two. What it confers is a block of its
    own with its own stages, and nothing applies one by ref."""
    if not c.strike():
        return
    c.hit()
    c.attack(c.world.scaling.trim(15, c.level), FORT, as_="secondary")


@power(
    "m2322a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_has_shed,
    requires_text="usable only while affected by m2322a4",
)
def m2322a3(c: Cast) -> None:
    """The Miss line is not half damage -- it is no damage and the same two
    riders on a shorter clock, which is why the branch is written out rather
    than left to `half_on_miss`."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.teleport(3, who=victim)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.teleport(3, who=victim)
        c.dazed(until=When.EONT)


@power(
    "m2322a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    trigger=_M2322_SPLIT,
    on=Trigger(Bloodied, about_me, _M2322_SPLIT),
    dropped=(),
)
def m2322a4(c: Cast) -> None:
    """What it sheds is flavour; what the row does is swap half its action
    list and put two points on every defence.

    Four bonuses rather than one, because the engine holds each defence
    separately and a bonus named "all defenses" would be a bonus to nothing.
    The hold the three gated rows read is laid under this row's own ref,
    which is what their Requirement names.
    """
    c.effect(_M2322_SHED, until=When.ENCOUNTER, on=c.me)
    for which in EVERY_DEFENCE:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER)
    for ref in ("m2322a2", "m2322a3", "m2322a5"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)
    for ref in ("m2322a0", "m2322a1"):
        c.forbid(ref, on=c.me, until=When.ENCOUNTER)
    c.low_light(until=When.ENCOUNTER)


@power(
    "m2322a5",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_has_shed,
    requires_text="usable only while affected by m2322a4",
)
def m2322a5(c: Cast) -> None:
    c.teleport(c.roll("1d6"))


# ==========================================================================
# m2337
# ==========================================================================


_M2337_FELL = "the m2337 drops to 0 hit points"


@power(
    "m2337a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m2337a0(c: Cast) -> None:
    """The burn and the condition are one effect with one saving throw at -2,
    which is what "save at -2 ends both" says; two calls would hand the
    victim two throws and let it shake off half of one thing.

    The two worsenings are `escalate`, which runs on **every** failed save --
    so the steps are popped off a list and the third failure changes nothing,
    which is the printed track.

    Each step ends the standing hold and lays a fresh one rather than
    rewriting `Effect.conditions`: `Conditions` is its own component, written
    when an effect is applied and when it ends, so a mutated tuple changes
    nothing a board can see. Driven by hand, the victim stayed slowed through
    three failures.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if not c.attack(c.world.scaling.trim(15, c.level), FORT, as_="secondary"):
        return
    steps = [Condition.IMMOBILIZED, Condition.STUNNED]

    def deepen(what: Condition) -> None:
        c.condition(
            what,
            until=When.SAVE_ENDS,
            on=victim,
            save_mod=-2,
            ongoing=(5, DamageType.POISON),
            escalate=worsen,
        )

    def worsen(eff: Effect) -> None:
        if not steps:
            return
        c.world.effects.end(eff, f"{c.ref}: the poison deepens")
        deepen(steps.pop(0))

    deepen(Condition.SLOWED)


@power(
    "m2337a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M2337_FELL,
    on=Trigger(Dropped, about_me, _M2337_FELL),
)
def m2337a1(c: Cast) -> None:
    """No attack roll printed: the blindness simply lands."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m2337a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2337a2(c: Cast) -> None:
    _extra_with_the_edge(c, "2d6")


@power(
    "m2337a3",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2337a3(c: Cast) -> None:
    """The card prints "+4 bonus to AC" with no type word in front of it, so
    it is untyped. The edge is taken after the move, against whoever it
    actually ended up beside."""
    c.bonus(
        AC,
        4,
        on=c.me,
        until=When.EOT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(4)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.grants_advantage(on=foe, to="me", until=When.EONT)


# ==========================================================================
# m2341
# ==========================================================================


@power(
    "m2341a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m2341a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2341a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m2341a1(c: Cast) -> None:
    """The brief prints an attack line with no defence at all in front of the
    Effect line that names the attacks it really makes. The Effect line is
    what is written and the orphan is dropped as extraction noise; see the
    report.

    Each swing picks its own target, because a step between them changes who
    is in reach.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    for _ in range(4):
        foe = _adjacent_foe(c, c.ref)
        if foe is None:
            break
        c.use_power("m2341a0", on=foe)
        c.shift(1)


@power(
    "m2341a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m2341a2(c: Cast) -> None:
    """The brief runs two cards together -- "makes two melee attacks" and a
    ranged line with its own numbers. The numbers are the ranged ones, so
    that is the row: two shots at the printed range, damage per hit. Range
    5/10 takes the short number."""
    for _ in range(2):
        foe = _foe_within(c, 5, c.ref)
        if foe is None:
            break
        if c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m2341a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2341a3(c: Cast) -> None:
    """The brief attributes this trait to another ref entirely; it is on this
    stat block and it is written for this creature. See the report."""
    _extra_with_the_edge(c, "3d6")


@power(
    "m2341a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.extend_move()",),
)
def m2341a4(c: Cast) -> None:
    """"A +5 racial bonus" -- the word in front of "bonus" is the type, and
    this one prints it. The extra square owed for a missed opportunity
    attack is the dropped clause: a move already under way cannot be
    lengthened."""
    c.bonus(
        AC,
        5,
        kind="racial",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m2341a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m2341a5(c: Cast) -> None:
    """The whole row says this creature counts as a particular sort of
    servant of a particular sort of master, and the brief names both only by
    printed name. `c.set_origin` wants a word and there is no ref to put in
    its place."""


# ==========================================================================
# m2349
# ==========================================================================


@power(
    "m2349a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m2349a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2349a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m2349a1(c: Cast) -> None:
    """Same malformed shape as m2341a1: an attack line with no defence in
    front of the Effect line that names the real attacks. The Effect line is
    written."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    for _ in range(4):
        foe = _adjacent_foe(c, c.ref)
        if foe is None:
            break
        c.use_power("m2349a0", on=foe)
        c.shift(1)


def _edge_on_somebody_close(world: World, eid: int) -> bool:
    """The printed Requirement: combat advantage against somebody in reach."""
    return any(
        distance_between(world, eid, foe) <= 1 and has_combat_advantage(world, eid, foe)
        for foe in enemies(world, eid)
    )


@power(
    "m2349a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    requires=_edge_on_somebody_close,
    requires_text="requires combat advantage",
)
def m2349a2(c: Cast) -> None:
    """Three things laid on one borrowed swing.

    The +2 is a held modifier rather than an argument, because `c.use_power`
    runs the other row's own `c.strike` and there is nowhere to pass one; it
    is ended again as soon as the swing is over so nothing else collects it.
    `c.maximise(critical=True)` is "a hit is treated as a critical hit".

    The doubled burn is not a second effect: m2349a3's rider has already laid
    ongoing 5 on the hit, and `c.ongoing` keeps only the highest of one type,
    so ongoing 10 supersedes it exactly as the printed sentence reads.
    """
    foe = _adjacent_foe(c, c.ref)
    if foe is None:
        return
    plus = c.bonus("attack", 2, on=c.me, until=When.EOT)
    try:
        c.maximise(on=c.me, ref="m2349a0", until=When.EOT, critical=True)
        c.use_power("m2349a0", on=foe)
    finally:
        if plus is not None:
            c.world.effects.end(plus, "the swing is over")
    if c.landed:
        c.ongoing(10, on=foe)
    c.shift(3)


@power(
    "m2349a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2349a3(c: Cast) -> None:
    """A burn on its own hits rather than a damage modifier: the printed line
    adds no damage to the blow, it leaves something behind on the creature
    that was hit. `ev.result.advantage` is the edge as the swing had it."""
    me = c.me

    def bite(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker != me or result is None or not result.advantage:
            return
        row = get(str(getattr(ev, "power", "") or ""))
        if row is not None and row.reach_of(0).kind == "melee":
            c.ongoing(5, on=ev.target)

    c.watch(Hit, bite, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2524
# ==========================================================================


_M2524_FELL = "the m2524 drops to 0 hit points"


@power(
    "m2524a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m2524a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2524a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m2524a1(c: Cast) -> None:
    """The second weapon's line, printed identically to the first. Two rows
    rather than one because the card has two, and the row that pairs them
    reads whether each of the two landed."""
    if c.strike():
        c.hit()


@power(
    "m2524a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
)
def m2524a2(c: Cast) -> None:
    """"If both attacks hit" is read off `c.landed` after each borrowed swing,
    which is what `c.use_power` leaves behind. The brief names another ref as
    the attacker here; the row is on this stat block. See the report.

    Each swing picks its own target, because the card does not say they share
    one and "one target" in the rider is then a choice.
    """
    landed: list[int] = []
    for ref in ("m2524a0", "m2524a1"):
        foe = _adjacent_foe(c, c.ref)
        if foe is None:
            continue
        c.use_power(ref, on=foe)
        if c.landed:
            landed.append(foe)
    if len(landed) < 2:
        return
    victim = c.choose(sorted(set(landed)), f"{c.ref}: which target burns")
    if victim is not None:
        c.ongoing(5, DamageType.PSYCHIC, on=victim)


@power(
    "m2524a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
    trigger=_M2524_FELL,
    on=Trigger(Dropped, about_me, _M2524_FELL),
)
def m2524a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2524a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2524a4(c: Cast) -> None:
    """Filed as a move action and plainly a trait: it is a standing waiver,
    not something spent.

    `ctx["actor"]` is whoever would swing at the opening, so the whole
    sentence fits one gate -- and the gate is re-read every time a window
    opens, which matters because who is burning changes constantly.
    """
    world = c.world
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            (who := ctx.get("actor")) is not None and _burning(world, int(who))
        ),
    )


# ==========================================================================
# m2594
# ==========================================================================


@power(
    "m2594a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m2594a0(c: Cast) -> None:
    """The Miss line is not half damage -- it is no damage and the step
    anyway, so the shift sits outside the branch."""
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m2594a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 6),
)
def m2594a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2594a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m2594a2(c: Cast) -> None:
    """No damage line: the pull and the edge are the hit."""
    if c.strike():
        c.pull(1)
        c.grants_advantage(to="me", until=When.SONT)


@power(
    "m2594a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2594a3(c: Cast) -> None:
    gate = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="3d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: gate(ctx) and _weapon_swing(ctx) and not ctx.get("ranged"),
    )


@power(
    "m2594a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2594a4(c: Cast) -> None:
    """`c.cure` follows `c.target`, and this row has none, so the mark being
    shaken off has to be named `on=c.me`."""
    c.cure(Condition.MARKED, on=c.me)
    c.shift(1)
    c.move(c.speed_of())


# ==========================================================================
# m2600
# ==========================================================================


@power(
    "m2600a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.ACID),
)
def m2600a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m2600a1",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2600a1(c: Cast) -> None:
    c.shift(3)


# ==========================================================================
# m2608
# ==========================================================================


@power(
    "m2608a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
)
def m2608a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.cure(Condition.MARKED, on=c.me)


@power(
    "m2608a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m2608a1(c: Cast) -> None:
    """No damage line: the daze is the hit, so there is nothing for `c.hit()`
    to deal. The clock is this creature's own next turn, which is `EONT`."""
    if c.strike():
        c.dazed(until=When.EONT)


@power(
    "m2608a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m2608a2(c: Cast) -> None:
    """Two swings of the printed weapon row, with a step between them, and the
    rider owed only if both land -- so the whole thing runs once for the use
    and `c.landed` is read after each borrowed swing. A printed "shift" with
    no number is one square. The step is `toward=` the creature about to be
    swung at: unranked it was free to walk out of reach between the two
    swings, and the explicit-target arm would have landed the hit anyway."""
    if not c.first:
        return
    landed: list[int] = []
    for victim in c.targets[:2]:
        c.shift(1, toward=victim)
        c.use_power("m2608a0", on=victim)
        if c.landed:
            landed.append(victim)
    if len(landed) == 2:
        for victim in landed:
            c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m2608a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m2608a3(c: Cast) -> None:
    """No damage line: the hold is the hit.

    The brief's worsening clause names a condition the Hit line never
    applied -- "dominated instead of stunned" where the hit lays dazed. The
    hit is believed and the worsening is read as replacing what is standing;
    see the report.

    The Aftereffect is `on_end`, which fires however a hold goes -- saved
    against or run out. But the worsening ends one hold to lay another, and
    an aftereffect owed for *finishing* the chain must not be paid for that
    swap, so the live hold is tracked and the payout asks whether the effect
    ending is still it.

    The swap itself is why `escalate` does not simply rewrite
    `Effect.conditions`: `Conditions` is its own component, written when an
    effect is applied and when it ends, so a mutated tuple is invisible.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    live: list[Effect] = []
    once: list[bool] = []

    def payout(eff: Effect) -> None:
        if live and live[-1] is eff:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    def hold_on(what: Condition) -> None:
        eff = c.condition(what, until=When.SAVE_ENDS, on=victim, escalate=worsen)
        if eff is None:
            return
        live.append(eff)
        eff.on_end.append(lambda standing=eff: payout(standing))

    def worsen(eff: Effect) -> None:
        if once:
            return
        once.append(True)
        live.clear()            # replaced, not finished -- no aftereffect yet
        c.world.effects.end(eff, f"{c.ref}: it takes hold")
        hold_on(Condition.DOMINATED)

    hold_on(Condition.DAZED)


@power(
    "m2608a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2608a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m3201
# ==========================================================================


@power(
    "m3201a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 5),
)
def m3201a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3201a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3201a1(c: Cast) -> None:
    """`c.mark(by=)` is the whole of this card: the mark belongs to an ally,
    not to the leader who laid it, and nothing else can say that. The step
    comes after, which is the printed order."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m3201a0", on=victim)
    if c.landed:
        helpers = sorted(
            w
            for w in c.allies()
            if alive(c.world, w) and distance_between(c.world, w, victim) <= 5
        )
        who = c.choose(helpers, f"{c.ref}: which ally takes the mark") if helpers else None
        if who is not None:
            c.mark(on=victim, by=who, until=When.EONT)
    c.shift(max(1, c.speed_of() // 2))


@power(
    "m3201a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_ALLY,
)
def m3201a2(c: Cast) -> None:
    """`c.basic(who=)` names who swings and `on=` names who is hit, and the
    victim still defaults to `c.target` -- which on this row is the **ally**.
    So the foe is named explicitly or the grant is friendly fire.

    The conditional +2 is laid as a gated modifier rather than chosen here,
    because whether the ally's own mark is on the creature it swings at is
    read when the swing happens.
    """
    ally = c.target
    if ally is None:
        return
    c.move(max(1, c.speed_of(ally) // 2), who=ally)
    world = c.world
    c.bonus(
        "attack",
        2,
        on=ally,
        until=When.EOT,
        when=lambda ctx: (
            (foe := ctx.get("target")) is not None
            and world.relations.holds(Relation.MARKED_BY, ally, int(foe))
        ),
    )
    near = sorted(foe for foe in c.enemies() if distance_between(world, ally, foe) <= 1)
    if near:
        c.basic(who=ally, on=near[0])


@power(
    "m3201a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.save_to_avoid(Condition.PRONE)",),
)
def m3201a3(c: Cast) -> None:
    """One square off every shove is exact. The saving throw against being
    knocked down is the dropped clause: a saving throw is rolled against a
    standing effect, and there is no hook that offers one *instead of* a
    condition landing."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3931
# ==========================================================================


@power(
    "m3931a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m3931a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)


@power(
    "m3931a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=NO_TARGET,
)
def m3931a1(c: Cast) -> None:
    """Each of the three swings picks its own target: the card does not share
    one and the pull it carries changes who is in reach."""
    for _ in range(3):
        foe = _foe_within(c, 3, c.ref)
        if foe is None:
            break
        c.use_power("m3931a0", on=foe)


@power(
    "m3931a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m3931a2(c: Cast) -> None:
    """Two defences on one effect, because the card prints one saving throw:
    two `c.penalty` calls would hand the victim two, and let it shake off its
    Reflex penalty while keeping its AC one."""
    victim = c.target
    if victim is not None and c.strike():
        _pair_penalty(c, -2, (AC, REF), until=When.SAVE_ENDS, on=victim)


@power(
    "m3931a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m3931a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3931a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m3931a4(c: Cast) -> None:
    """"Its closest ally" is asked of the victim's own side, which `c.within`
    cannot say -- its words are the caster's. The basic attack is handed the
    victim as the swinger and the ally as `on=`, because without `on=` it
    would aim at this row's own target, which is the swinger itself."""
    me, victim = c.me, c.target
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if victim is None or not c.strike():
        return
    c.hit()
    friend = _closest_of_its_own(c, victim)
    if friend is not None:
        c.basic(who=victim, on=friend)


@power(
    "m3931a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3931a5(c: Cast) -> None:
    """Four gated modifiers held for the fight rather than laid when it is
    first bloodied: a hold laid on a `Bloodied` would not come off again when
    it was healed above the line, and the printed line is a standing "while
    bloodied"."""
    me, world = c.me, c.world

    def hurt(_ctx: dict[str, Any]) -> bool:
        return _is_bloodied(world, me)

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.bonus("damage", 0, dice="1d6", on=me, until=When.ENCOUNTER, when=hurt)
    for which in (AC, REF):
        c.penalty(which, 2, on=me, until=When.ENCOUNTER, when=hurt)


# ==========================================================================
# m3936
# ==========================================================================


@power(
    "m3936a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 5),
)
def m3936a0(c: Cast) -> None:
    """The printed "crit 1d12 + 17" is the maximum of the ordinary line --
    which `c.damage` already deals on a critical -- plus a rolled 1d12 on
    top. `c.flat(c.roll(...))` is what rolls it; through `c.damage` it would
    be maximised too and the critical would come out flat."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d12"))


@power(
    "m3936a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m3936a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3936a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m3936a2(c: Cast) -> None:
    """The healing is owed whether the swing landed or not, which is why it
    sits outside any branch. A monster has its own hit points to put back and
    spends no surge unless the card says so; this one names a number."""
    foe = _adjacent_foe(c, c.ref)
    if foe is not None:
        c.basic(on=foe)
    c.heal(30, on=c.me)


@power(
    "m3936a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3936a3(c: Cast) -> None:
    """`partial=True` is the printed "but not total concealment". The gate is
    read off the attack context, which carries `ranged` and the creature
    being shot at, so both halves of the sentence are asked at the moment of
    the shot rather than when the trait is armed."""
    me, world = c.me, c.world
    c.ignore_cover(
        on=me,
        until=When.ENCOUNTER,
        partial=True,
        when=lambda ctx: (
            bool(ctx.get("ranged"))
            and (foe := ctx.get("target")) is not None
            and distance_between(world, me, int(foe)) <= 5
        ),
    )


# ==========================================================================
# m4204
# ==========================================================================


@power(
    "m4204a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m4204a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4204a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 3),
)
def m4204a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4204a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m4204a2(c: Cast) -> None:
    """The step comes first because the card prints it first and both swings
    reach two squares, so closing is what makes them legal."""
    c.shift(4)
    pair = c.choose([True, False], f"{c.ref}: two of the lesser attacks, or one big")
    if pair:
        for _ in range(2):
            foe = _foe_within(c, 2, c.ref)
            if foe is None:
                break
            c.use_power("m4204a1", on=foe)
        return
    foe = _foe_within(c, 2, c.ref)
    if foe is not None:
        c.use_power("m4204a0", on=foe)


@power(
    "m4204a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4204a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4204a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.charging()",),
)
def m4204a4(c: Cast) -> None:
    """The printed Requirement -- a rider of 12th level or better -- is asked
    inside the gate and not in `requires=`: a trait whose Requirement is
    false when it is armed is refused once and never armed again, and a
    rider mounting is exactly the thing that becomes true later.

    "A +4 to defense against opportunity attacks" names no defence and no
    bonus type. An opportunity attack is a basic attack against AC, so that
    is where the four goes, untyped. The rider's copy is renewed at the top
    of each of this creature's turns, because whoever is on its back changes.

    "When it makes charge attacks" is the dropped clause. The context an
    opportunity attack's modifier is read with carries that attacker's
    `charge`, not this creature's, and nothing asks whether a named creature
    is mid-charge -- so the waiver is wider than the card prints.
    """
    me, world = c.me, c.world

    def carried() -> bool:
        rider = c.rider()
        if rider is None:
            return False
        stats = world.get(rider, Stats)
        return stats is not None and stats.level >= 12

    def guard(_ctx: dict[str, Any]) -> bool:
        return bool(_ctx.get("opportunity")) and carried()

    c.bonus(AC, 4, on=me, until=When.ENCOUNTER, when=guard)
    held: list[Effect] = []

    def each_turn(ev: TurnStart) -> None:
        rider = c.rider()
        if ev.actor != me or rider is None:
            return
        _renew(
            c,
            held,
            lambda who=rider: c.bonus(AC, 4, on=who, until=When.ENCOUNTER, when=guard),
        )

    c.watch(TurnStart, each_turn, until=When.ENCOUNTER, on=me, label=f"{c.ref} rider")


# ==========================================================================
# m4310
# ==========================================================================


_M4310_DOWN = "the m4310 is reduced to 0 hit points"
#: The shape a4310a5 takes, which a0 and a1 are barred during and a2 needs.
_M4310_SWARM = "m4310a5"


def _in_its_own_shape(world: World, eid: int) -> bool:
    return not any(
        e.label == _M4310_SWARM and not e.ended for e in world.effects.of(eid)
    )


def _in_the_other_shape(world: World, eid: int) -> bool:
    return not _in_its_own_shape(world, eid)


@power(
    "m4310a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 7),
    requires=_in_its_own_shape,
    requires_text="normal form only",
)
def m4310a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4310a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    requires=_in_its_own_shape,
    requires_text="normal form only",
)
def m4310a1(c: Cast) -> None:
    """Two basic attacks against different creatures somewhere inside one
    move. The waiver is blanket rather than the printed "away from either
    target", because `c.no_provoke` names a creature or everybody and cannot
    name a reason."""
    waiver = c.no_provoke(until=When.EOT)
    struck: set[int] = set()
    try:
        for _ in range(2):
            near = sorted(
                foe for foe in c.enemies() if c.adjacent(foe) and foe not in struck
            )
            if not near:
                c.move(max(1, c.speed_of() // 2))
                near = sorted(
                    foe for foe in c.enemies() if c.adjacent(foe) and foe not in struck
                )
            if not near:
                break
            foe = c.choose(near, f"{c.ref}: which enemy") or near[0]
            struck.add(foe)
            c.basic(on=foe)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the run is over")


@power(
    "m4310a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 2, dtype=DamageType.NECROTIC),
    requires=_in_the_other_shape,
    requires_text="usable only in the m4310a5 form",
)
def m4310a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m4310a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 7, kind=LIMITED),
    requires=_edge_on_somebody_close,
    requires_text="requires combat advantage",
)
def m4310a3(c: Cast) -> None:
    """The printed recharge sentence watches an *adjacent* creature crossing
    its half-hit-point line, whoever struck the blow -- so the test is
    distance and not `by_me`."""
    me, world = c.me, c.world
    _recharge_on(
        c,
        Bloodied,
        lambda ev: alive(world, ev.actor) and distance_between(world, me, ev.actor) <= 1,
    )
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
        c.heal(48, on=me)


@power(
    "m4310a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4310a4(c: Cast) -> None:
    _extra_with_the_edge(c, "2d6")


@power(
    "m4310a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=("spec.monster_ref()",),
)
def m4310a5(c: Cast) -> None:
    """The change of shape is real and so is the resistance it prints, and the
    hold it lays under this row's ref is what the three gated rows read. What
    is missing is the shape itself: the brief names the stat block it becomes
    only by its printed name, with no ref to load it from, so the swarm's own
    numbers are the dropped clause.

    `revert=MINOR` is the printed "revert minor".
    """
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M4310_SWARM)
    c.effect(_M4310_SWARM, until=When.ENCOUNTER, on=c.me)
    c.resist(10, on=c.me, until=When.ENCOUNTER)


@power(
    "m4310a6",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def m4310a6(c: Cast) -> None:
    """Declared with no target: `Target` filters on side and count and not on
    what a creature *is*, and the printed set is one ally of a particular
    type."""
    kin = sorted(
        w
        for w in c.allies()
        if alive(c.world, w) and c.distance(w) <= 5 and c.is_kind("humanoid", on=w)
    )
    who = c.choose(kin, f"{c.ref}: which ally") if kin else None
    if who is None:
        return
    c.shift(1, who=who)
    c.bonus("damage", 0, dice="1d6", on=who, until=When.EONT)


@power(
    "m4310a7",
    level=12,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    trigger=_M4310_DOWN,
    on=Trigger(
        DamageRolled,
        lambda world, me, ev: (
            getattr(ev, "target", None) == me
            and (h := world.get(me, Health)) is not None
            and getattr(ev, "amount", 0) >= h.hp
        ),
        _M4310_DOWN,
    ),
)
def m4310a7(c: Cast) -> None:
    """Declared on `DamageRolled` rather than on `Dropped`, which is the only
    way "the triggering attack misses" can be said: `Dropped` is a plain
    announcement with no `cancel` and the creature is already down by then,
    where `DamageRolled` is a `Decision` an interrupt can refuse. The
    predicate is "this blow would finish it", which is the printed trigger
    read forwards.

    The flight lasts the encounter rather than the printed hour; there is no
    clock longer than the fight and nothing outside one to spend it on.
    """
    c.cancel()
    c.insubstantial(until=When.ENCOUNTER, on=c.me)
    c.shift(6)
    c.mode("fly", 12, until=When.ENCOUNTER, on=c.me)
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m4356
# ==========================================================================


@power(
    "m4356a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 3, dtype=DamageType.COLD),
)
def m4356a0(c: Cast) -> None:
    """Two packets rather than one of two types: the card prints two numbers
    and a resistance reads each separately.

    The knockdown is skipped where the swing had the edge, because m4356a3
    pays extra dice *instead of* knocking that creature down -- the trait
    does the paying and this row does the skipping, which is the only way
    round that does not have the trait reaching into somebody else's branch.
    """
    swing = c.strike()
    if not swing:
        return
    c.hit()
    c.damage("1d6", 3, dtype=DamageType.FIRE)
    if not swing.advantage:
        c.prone(held=When.EONT)


@power(
    "m4356a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m4356a1(c: Cast) -> None:
    def swing() -> None:
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m4356a0", on=foe)

    _moving_strike(c, c.speed_of(), swing)


@power(
    "m4356a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.FIRE],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m4356a2(c: Cast) -> None:
    """The printed sentence gives the row back when cold or fire reaches it,
    which `DamageApplied` is the announcement of -- and that event names its
    subject `target`, so `about_me` would be false here forever."""
    me = c.me
    if c.first:
        _recharge_on(
            c,
            DamageApplied,
            lambda ev: (
                getattr(ev, "target", None) == me
                and getattr(ev, "amount", 0) > 0
                and ev.dtype in (DamageType.COLD, DamageType.FIRE)
            ),
        )
    swing = c.strike()
    if not swing:
        return
    c.hit()
    c.damage("2d6", 3, dtype=DamageType.FIRE)
    if not swing.advantage:
        c.prone()


@power(
    "m4356a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4356a3(c: Cast) -> None:
    """Two rolled packets on its own hits rather than a damage modifier: the
    card names two types and a modifier adds to whatever packet is already
    being dealt, which would lose both. The "instead of knocking prone" half
    is the two attack rows' own branch."""
    me = c.me

    def extra(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker == me and result is not None and result.advantage:
            c.damage("1d8", on=ev.target, dtype=DamageType.COLD, detail=c.ref)
            c.damage("1d8", on=ev.target, dtype=DamageType.FIRE, detail=c.ref)

    c.watch(Hit, extra, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4356a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_squeeze_penalty()",),
)
def m4356a4(c: Cast) -> None:
    """Every clause of this row is a waiver on squeezing -- the speed, the
    openings and the attack penalty -- and the penalty is the one the engine
    applies, with nothing to hang a waiver on. Nothing here lands, so nothing
    is written."""


@power(
    "m4356a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.surface()",),
)
def m4356a5(c: Cast) -> None:
    """Rough ground is exact. Crossing liquid is the dropped clause: a board
    has no liquid surface, so there is nothing for a mode to be granted
    over."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m4514
# ==========================================================================


@power(
    "m4514a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 7),
)
def m4514a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4514a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.FIRE, Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d10", 3, dtype=DamageType.FIRE),
)
def m4514a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the condition, so
    the victim gets the one saving throw the card prints."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.POISON),
        )


# ==========================================================================
# m5097
# ==========================================================================


@power(
    "m5097a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5097a0(c: Cast) -> None:
    """`resolve.attack` reads the crit floor as `20 - crit_range`, so one more
    is the printed 19-20."""
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m5097a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5097a1(c: Cast) -> None:
    """Burrowing through stone is phasing: the mode that makes what is in the
    way not in the way. Shifting while burrowing needs nothing added -- a
    shift is a move and the mode is a property of the creature, not of the
    action -- and the printed "at full speed" is already true, because its
    burrow speed and its speed are the same number on this card."""
    c.phasing(until=When.ENCOUNTER, on=c.me)


@power(
    "m5097a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m5097a2(c: Cast) -> None:
    """The grab is real; the printed escape DC is the dropped clause, because
    `c.escape` rolls against the engine's own number."""
    if c.strike():
        c.hit()
        c.grab(dc=20)


@power(
    "m5097a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    requires=_grabbing_something,
    requires_text="the m5097 must have a creature grabbed",
)
def m5097a3(c: Cast) -> None:
    """It takes its captive down with it.

    The grab has to be let go of before the victim leaves the board, and
    there is no release verb: `c.escape(auto=True)` is the one call that
    unwinds the relation and the effect together, which is what the printed
    "the grab ends" asks for.

    "Takes ongoing 10 damage (save ends both)" is one effect carrying the
    removal and the burn, so there is one saving throw; coming back within 5
    squares of where it went is `on_end`, which fires however the hold goes.
    """
    victim = _my_captive(c)
    if victim is None:
        return
    c.shift(c.speed_of())
    c.escape(on=victim, auto=True)
    c.condition(
        Condition.REMOVED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(10, DamageType.UNTYPED),
    )


@power(
    "m5097a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d6", 6, kind=LIMITED),
    requires=_underground,
    requires_text="the m5097 must have started its turn underground",
)
def m5097a4(c: Cast) -> None:
    """Declared with no target: the burst is thrown from where the move
    *ends*, and a header target list is chosen before the body runs -- so the
    printed order would have caught whoever was standing round the hole it
    started in. The burst is gathered by hand afterwards instead.

    Where it comes up is named rather than left to the decider: a bare
    `c.shift` takes the lowest square on the board, so the row would surface
    in a corner and burst over nobody every time.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    _shift_among(c, c.speed_of(), 2)
    for who in sorted(c.within(2)):
        if who != me and c.strike(on=who):
            c.hit(on=who)
            c.blinded(until=When.EOTNT, on=who)


# ==========================================================================
# m5162
# ==========================================================================


@power(
    "m5162a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
)
def m5162a0(c: Cast) -> None:
    """No damage line at all -- the burn *is* the hit, so there is nothing for
    `c.hit()` to deal.

    "Each failed saving throw" is `escalate` without any bookkeeping:
    `Effects` calls it on every failure, so the burn climbs each time and the
    cap is read off the effect rather than counted.
    """
    if not c.strike():
        return

    def worsen(eff: Effect) -> None:
        standing = eff.ongoing[0] if eff.ongoing else 20
        eff.ongoing = (min(30, standing + 5), DamageType.POISON)

    c.condition(
        until=When.SAVE_ENDS,
        ongoing=(20, DamageType.POISON),
        escalate=worsen,
    )


@power(
    "m5162a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 5, dtype=DamageType.POISON),
)
def m5162a1(c: Cast) -> None:
    """The zone is the target's square and the ring round it, which is read
    off the grid rather than from `c.area()` -- the area this row covers is
    one square at range, and the printed zone is nine."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    zid = c.zone(
        spread(squares(c.world, victim), 1), label=c.ref, until=When.EONT
    )
    c.burns(zid, 5, DamageType.POISON)


@power(
    "m5162a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.POISON),
)
def m5162a2(c: Cast) -> None:
    """"Creatures in the burst" is creatures, not enemies. The zone is laid
    once for the whole use, which is what `c.first` is for."""
    if c.first:
        zid = c.zone(c.area(), label=c.ref, until=When.EONT)
        c.burns(zid, 10, DamageType.POISON)
    if c.strike():
        c.hit()


@power(
    "m5162a3",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5162a3(c: Cast) -> None:
    """All four holds are shaken off by name rather than by a blanket cure,
    because the card lists them and `c.cure` returns only what actually
    went."""
    c.cure(
        Condition.GRABBED,
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        Condition.SLOWED,
        on=c.me,
    )
    c.mode("fly", 6, until=When.EOT, on=c.me)
    c.phasing(until=When.EOT, on=c.me)
    c.insubstantial(until=When.EOT, on=c.me)
    c.move(6, at="fly")


_M5162_ELEMENT = "the m5162 takes acid, cold, fire, lightning or thunder damage"

#: The five types the two "resist the thing that just hurt me" rows answer.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _elemental_blow(world: World, me: int, ev: DamageApplied) -> bool:
    """`DamageApplied` names its subject `target`, so `about_me` -- which
    reads `actor` and only `actor` -- is false here forever."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _ELEMENTS
    )


@power(
    "m5162a4",
    level=12,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5162_ELEMENT,
    on=Trigger(DamageApplied, _elemental_blow, _M5162_ELEMENT),
)
def m5162a4(c: Cast) -> None:
    """"Or until it uses this again" is the earlier resistance being ended by
    hand: two resistances of different types would otherwise both stand, and
    the card says only the latest one does."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None:
        return
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == c.ref and not eff.ended:
            c.world.effects.end(eff, "it answers a new element")
    c.resist(10, dtype, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5201
# ==========================================================================


_M5201_FELL = "the m5201 drops to 0 hit points"


@power(
    "m5201a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5201a0(c: Cast) -> None:
    """The penalty belongs to the attackers, so it is laid on each of them
    with a gate naming this creature as the thing being swung at -- and
    renewed at the top of each of its turns, because an enemy that arrives
    later would otherwise never carry one.

    `c.penalty` takes no `kind` and that is the rule, which suits a card
    printing no type word.
    """
    me, world = c.me, c.world

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me and not _is_bloodied(world, me)

    seen: set[int] = set()

    def lay(_who: int) -> None:
        if _who in seen:
            return
        seen.add(_who)
        c.penalty("attack", 2, on=_who, until=When.ENCOUNTER, when=gate)

    for foe in sorted(c.enemies()):
        lay(foe)

    def again(ev: TurnStart) -> None:
        if ev.actor == me:
            for foe in sorted(c.enemies()):
                lay(foe)

    c.watch(TurnStart, again, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5201a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5201a1(c: Cast) -> None:
    _extra_with_the_edge(c, "2d6")


@power(
    "m5201a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5201a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5201a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m5201a3(c: Cast) -> None:
    """Two swings, one of them somewhere inside a half-speed move. The second
    is printed as "either before or after this movement", which is the same
    pair of orders `_moving_strike` already chooses between, so it is taken
    as the one in reach now."""
    def swing() -> None:
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.basic(on=foe)

    swing()
    _moving_strike(c, max(1, c.speed_of() // 2), swing)


@power(
    "m5201a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
)
def m5201a4(c: Cast) -> None:
    """No attack roll printed: both holds simply land, and they share the one
    saving throw the card gives them."""
    if c.target is None:
        return
    c.mark(until=When.SAVE_ENDS)
    c.grants_advantage(to="me", until=When.SAVE_ENDS)


@power(
    "m5201a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5201a5(c: Cast) -> None:
    """"Creatures in the burst" is creatures, which on this card means its own
    side too."""
    if c.strike():
        c.hit()


@power(
    "m5201a6",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 5, dtype=DamageType.NECROTIC),
    trigger=_M5201_FELL,
    on=Trigger(Dropped, about_me, _M5201_FELL),
)
def m5201a6(c: Cast) -> None:
    """A death throe the dispatcher offers to a creature that is no longer
    alive, which is the only way a row of this shape fires."""
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m5355
# ==========================================================================


_M5355_SWUNG_AT_ME = "an enemy makes a melee attack against the m5355"


def _melee_swing_at_me(world: World, me: int, ev: AttackDeclared) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


@power(
    "m5355a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 6),
)
def m5355a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m5355a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m5355a1(c: Cast) -> None:
    """`c.jump` is already a move with the bodies and the rough going ignored
    for its length, which is what "does not provoke" is the printed half
    of -- the waiver is laid anyway, because a jump still passes squares an
    enemy threatens."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    waiver = c.no_provoke(until=When.EOT)
    try:
        c.jump(4)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "it has landed")
    for _ in range(2):
        foe = _adjacent_foe(c, c.ref)
        if foe is None:
            break
        c.use_power("m5355a0", on=foe)


@power(
    "m5355a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature granting combat advantage to it",
        grants_ca=True,
    ),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 5),
)
def m5355a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5355a3",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5355_SWUNG_AT_ME,
    on=Trigger(AttackDeclared, _melee_swing_at_me, _M5355_SWUNG_AT_ME),
    dropped=("c.jump(to=)",),
)
def m5355a3(c: Cast) -> None:
    """The leap is real. Where it has to land is the dropped clause: `c.jump`
    passes the distance to `c.move`, which picks its own destination through
    the decider, and there is no way to name the square the printed line
    requires -- out of reach of the creature being answered."""
    waiver = c.no_provoke(until=When.EOT)
    try:
        c.jump(4)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "it has landed")


# ==========================================================================
# m5497
# ==========================================================================


@power(
    "m5497a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m5497a0(c: Cast) -> None:
    """"Ends a move at least 4 squares from where it started" is the straight
    distance between the two ends, not the squares covered -- a loop back to
    where it began earns nothing. `_after_moving` is handed both.

    The rider is renewed rather than stacked: said again on the next move it
    is one hold with a fresh clock, and two would pay out twice.
    """
    held: list[Effect] = []

    def arrived(_kind: str, was: Any, now: Any, _steps: int) -> None:
        if was is None:
            return
        far = max(abs(now[0] - was[0]), abs(now[1] - was[1]))
        if far < 4:
            return
        _renew(
            c,
            held,
            lambda: c.bonus(
                "damage",
                0,
                dice="1d8",
                dtype=DamageType.NECROTIC,
                on=c.me,
                until=When.SONT,
            ),
        )

    _after_moving(c, arrived)


@power(
    "m5497a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m5497a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5497a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m5497a2(c: Cast) -> None:
    def swing() -> None:
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m5497a1", on=foe)

    _moving_strike(c, c.speed_of(), swing)


@power(
    "m5497a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m5497a3(c: Cast) -> None:
    """No damage line on the hit: what lands is a standing demand, and the
    damage is the price of ignoring it.

    How far the victim has gone is counted off `Moved` -- nothing on the
    board remembers it -- reset at the top of each of its turns and read at
    the end of them, which is the window the printed "on its turn" closes in.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    walked = [0]
    hold = c.condition(until=When.SAVE_ENDS, on=victim)

    def stepped(ev: Moved) -> None:
        if ev.actor == victim:
            walked[0] += 1

    def restart(ev: TurnStart) -> None:
        if ev.actor == victim:
            walked[0] = 0

    def settle(ev: TurnEnd) -> None:
        if ev.actor == victim and walked[0] < 4:
            c.damage("1d10", on=victim, dtype=DamageType.PSYCHIC, detail=c.ref)

    for event, fn in ((Moved, stepped), (TurnStart, restart), (TurnEnd, settle)):
        watch = c.watch(
            event, fn, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} drive"
        )
        if hold is not None:
            hold.on_end.append(
                lambda w=watch: c.world.effects.end(w, "the demand is over")
            )


# ==========================================================================
# m5677
# ==========================================================================


_M5677_MASTER_HURT = "an enemy bloodies the m5677's master"


def _bloodied_my_master(world: World, me: int, ev: Bloodied) -> bool:
    served = world.relations.sources(Relation.MASTER_OF, me)
    foe = getattr(ev, "source", None)
    return (
        bool(served)
        and ev.actor == served[0]
        and foe is not None
        and team(world, foe) is not team(world, me)
    )


@power(
    "m5677a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5677a0(c: Cast) -> None:
    """The aura is laid once and the toll it carries is a listener, because
    `c.insubstantial` is a condition with no gate and the printed line is
    conditional on three things at once: whose damage it is, where the master
    is standing, and whether a weapon attack dealt it.

    `DamageRolled` is the window -- rolled but not yet dealt -- and it is a
    `Decision`, so `c.halve` has something to take off. `c.master()` is asked
    inside, because who it serves can change.
    """
    me = c.me
    c.aura(2, label=c.ref, until=When.ENCOUNTER)

    def shield(ev: DamageRolled) -> None:
        served = c.master()
        if served is None or getattr(ev, "target", None) != served:
            return
        if c.in_my_aura(served, label=c.ref) and _weapon_blow(ev):
            c.halve(ev)

    c.watch(
        DamageRolled,
        shield,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=c.ref,
    )


@power(
    "m5677a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 4, dtype=DamageType.FIRE),
)
def m5677a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5677a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5677a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)


@power(
    "m5677a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5677a3(c: Cast) -> None:
    """Where the step has to end is the whole of the decision, which a bare
    `c.shift` cannot say."""
    served = c.master()
    if served is not None:
        _shift_beside(c, served, max(1, c.speed_of() // 2))


@power(
    "m5677a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5677_MASTER_HURT,
    on=Trigger(Bloodied, _bloodied_my_master, _M5677_MASTER_HURT),
)
def m5677a4(c: Cast) -> None:
    """`Bloodied.source` is who crossed the line, which is what makes "an
    enemy bloodies" a declared trigger rather than one derived off
    `DamageApplied` with the threshold worked out by hand."""
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    _shift_beside(c, foe, c.speed_of())
    c.use_power("m5677a1", on=foe)


# ==========================================================================
# m5861
# ==========================================================================


_M5861_BURNED = "the m5861 takes fire damage"


def _fire_on_me(world: World, me: int, ev: DamageApplied) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) is DamageType.FIRE
    )


@power(
    "m5861a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5861a0(c: Cast) -> None:
    """A trait rather than a declared trigger: a row holding an `on=` runs
    only when it fires, and this one has a watch to arm. `DamageApplied`
    names its subject `target`, so `about_me` would be false forever here.

    `c.ongoing` keeps only the highest burn of one type, so a second scorch
    while the first is standing refuses rather than stacking -- which is the
    printed rule and not a shortcut.
    """
    me = c.me

    def scorch(ev: DamageApplied) -> None:
        if _fire_on_me(c.world, me, ev):
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, scorch, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5861a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 7),
)
def m5861a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5861a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m5861a2(c: Cast) -> None:
    """A shift through bodies is not a walk: `c.overrun` reads the legs and
    always walks, so the destination is picked the way a trample's is and the
    movement is run at the printed kind. Whoever it passed through is
    reported once each, which is who the swing can be aimed at."""
    through = _through_them(c, c.speed_of(), kind="shift")
    options = sorted({*through, *(f for f in c.enemies() if c.distance(f) <= 2)})
    foe = c.choose(options, f"{c.ref}: which enemy") if options else None
    if foe is None:
        return
    c.use_power("m5861a1", on=foe)
    if c.landed:
        c.prone(on=foe)


@power(
    "m5861a3",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 9, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5861a3(c: Cast) -> None:
    """Declared with no target: the blink comes first and the burst is thrown
    from wherever it lands, so a header target list chosen before the body
    runs would catch whoever it left behind. `half_on_miss` is declared data
    and nothing reads it, so the Miss branch is written."""
    c.teleport(5)
    for foe in sorted(c.within(2, side="enemy")):
        if c.strike(on=foe):
            c.hit(on=foe)
        else:
            c.hit(on=foe, half=True)


# ==========================================================================
# m5895
# ==========================================================================


_M5895_FIRST_BLOODIED = "the m5895 is first bloodied"
_M5895_FELL = "the m5895 drops to 0 hit points"


@power(
    "m5895a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5895a0(c: Cast) -> None:
    """`c.teleport(share=True)` is an argument to one blink, made by the row
    that blinks; this is the standing property, so it is a watch that brings
    the rider along after the fact. `Moved` carries `kind_` as a plain
    attribute set on every emission, which is how the blink is told from a
    walk."""
    me = c.me

    def carry(ev: Moved) -> None:
        rider = c.rider()
        if ev.actor != me or rider is None or getattr(ev, "kind_", "") != "teleport":
            return
        if distance_between(c.world, me, rider) > 1:
            c.teleport(99, who=rider, to=c.here)

    c.watch(Moved, carry, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5895a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m5895a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5895a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m5895a2(c: Cast) -> None:
    """Declared with no target: the blink comes before the swing and changes
    who is in reach.

    The dark is a sight-blocking zone, which is what "totally obscured"
    comes to on a board, and the blindness is laid on whoever is standing in
    it. Who is exempt -- a creature that can see in the dark -- is the
    dropped clause: nothing holds that sense, so the zone cannot ask.
    """
    c.teleport(7)
    foe = _foe_within(c, 2, c.ref)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    dark = squares(c.world, foe)
    c.zone(dark, label=c.ref, until=When.EONT, blocks_sight=True,
           obscured="dark")
    for who in sorted(c.in_squares(dark)):
        if not c.has_sense("darkvision", on=who):
            c.blinded(until=When.EONT, on=who)


@power(
    "m5895a3",
    level=12,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5895_FIRST_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5895_FIRST_BLOODIED),
)
def m5895a3(c: Cast) -> None:
    """`Bloodied` fires once per crossing of the line, so "first bloodied" is
    the encounter usage rather than a flag."""
    for _ in range(2):
        c.use_power("m5895a2")


@power(
    "m5895a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 9, dtype=DamageType.RADIANT, kind=LIMITED),
    trigger=_M5895_FELL,
    on=Trigger(Dropped, about_me, _M5895_FELL),
)
def m5895a4(c: Cast) -> None:
    """"No Action" is filed as a free one; there is no cheaper action type and
    a death throe is offered whatever the column says."""
    if c.strike():
        c.hit()
        c.blinded(until=When.EOTNT)


# ==========================================================================
# m6000
# ==========================================================================


@power(
    "m6000a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
)
def m6000a0(c: Cast) -> None:
    """One blow of two types rather than two blows: `dtypes` is what a
    resistance reads as a unit, and ten points that are both is not five and
    five."""
    me = c.me
    c.aura(1, label=c.ref, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or not alive(c.world, ev.actor):
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor, label=c.ref):
            c.flat(
                10,
                dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC),
                on=ev.actor,
            )

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6000a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.immovable(when=)", "c.squeeze_through()"),
)
def m6000a1(c: Cast) -> None:
    """The shared square is exact, and `difficult=True` is the printed cost of
    entering it. `c.shares_space` is the standing property; `c.shift(share=)`
    is an argument to one move made by the mover, which is the other way
    round.

    Two clauses are dropped. "Cannot be pushed, pulled or slid **by melee or
    ranged attacks**" is narrower than `c.immovable`, which takes no gate, and
    refusing every shove would be a stronger swarm than the card prints.
    Slipping through an opening a Tiny creature fits has no opening on a
    board to slip through.
    """
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)


@power(
    "m6000a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 10, dtype=DamageType.PSYCHIC),
)
def m6000a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m6000a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d8", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.contract(ref)",),
)
def m6000a3(c: Cast) -> None:
    """Three things hang on the domination ending, and `on_end` is the one
    hook that fires however it ends: the swarm comes back, the Aftereffect
    lands, and the removal it put on itself is lifted with it.

    The printed recharge is "when the attack misses", which is the row's own
    `Miss` and is read here rather than through a watch.

    The affliction a failed saving throw at the end of the fight confers is a
    block of its own, named only by ref in the brief and with no way to apply
    one, so that is the dropped clause.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.restore(c.ref)
        return
    c.hit()
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=c.me)
    if hold is None:
        return

    def returns() -> None:
        if gone is not None:
            c.world.effects.end(gone, "the domination is over")
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            on=victim,
            ongoing=(5, DamageType.PSYCHIC),
        )

    hold.on_end.append(returns)


# ==========================================================================
# m6192
# ==========================================================================


_M6192_STRUCK = "the m6192 hits an enemy with a melee basic attack"


@power(
    "m6192a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6192a0(c: Cast) -> None:
    """Only the flanking branch, which is what the printed line says: being
    dazed or granted the opening outright still works."""
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6192a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 9),
    requires_text="the m6192 must be in its humanlike form",
    dropped=("c.in_form()",),
)
def m6192a1(c: Cast) -> None:
    """Declared with no target: the leap comes first and changes who is in
    reach. Which shape it is in is the dropped clause -- `c.form` lays a hold
    with no name to ask about, so the printed Requirement cannot be
    tested."""
    waiver = c.no_provoke(until=When.EOT)
    try:
        c.jump(2)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "it has landed")
    foe = _adjacent_foe(c, c.ref)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m6192a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d8", 6, kind=LIMITED),
    requires_text="the m6192 must be in its humanlike form",
    dropped=("c.in_form()",),
)
def m6192a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m6192a3",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6192a3(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "m6192a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6192a4(c: Cast) -> None:
    """The card's two shapes print their sizes, and size is the one part of
    "appears as" a board reads -- a Tiny creature takes up less room and is
    reached over differently. `c.form` is the hold and `c.resize` is what it
    changes; `revert=MINOR` is the printed way back out."""
    small = c.choose([True, False], f"{c.ref}: the small shape, or the tall one")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    c.resize(Size.TINY if small else Size.MEDIUM, on=c.me, until=When.ENCOUNTER)


@power(
    "m6192a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6192a5(c: Cast) -> None:
    """Standing up is ordinarily a move action; the whole content of this card
    is that this creature does it for a minor one, so the row *is* the
    standing rather than a grant of it."""
    c.cure(Condition.PRONE, on=c.me)


@power(
    "m6192a6",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6192_STRUCK,
    on=Trigger(Hit, _hit_with_its_basic, _M6192_STRUCK),
)
def m6192a6(c: Cast) -> None:
    """"With a melee basic attack" is answered against `Powers.basic`, which
    is the ref a monster's basic attack points at -- gating on the reach
    alone would fire for its other two melee rows as well."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.stunned(until=When.EOTNT, on=victim)


# ==========================================================================
# m6610
# ==========================================================================


def _relay_aura(c: Cast, radius: int) -> int:
    """Lay the m6610's aura again at a new width, under the same label.

    `Zone.aura` is the radius and `Zones.refresh` recomputes the footprint
    from it, but nothing widens a live one -- so the old aura is dispelled and
    a fresh one takes its place. The label is what the trait's watch reads it
    by, so it has to be the same.
    """
    for zid, zone in c.world.zones.all():
        if zone.label == "m6610a0" and c.made_by(zid) == c.me:
            c.dispel(zid)
    return c.aura(radius, label="m6610a0", until=When.ENCOUNTER)


@power(
    "m6610a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6610a0(c: Cast) -> None:
    """The toll is armed on the caster and reads the aura by label, so it goes
    on paying after a5 has torn the zone down and laid a wider one."""
    me = c.me
    _relay_aura(c, 1)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or not alive(c.world, ev.actor):
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor, label="m6610a0"):
            c.flat(10, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6610a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.slowed(mode=)",),
)
def m6610a1(c: Cast) -> None:
    """The whole row narrows a condition to one way of moving. Being slowed
    caps a creature's speed outright and there is no per-mode form of it, so
    there is nothing here that half-lands."""


@power(
    "m6610a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 12),
)
def m6610a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6610a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m6610a3(c: Cast) -> None:
    """Two separate reasons to swing during one walk, and the second is a
    window that has to be open *while* the movement happens -- so the watch
    is armed, the walk is taken, and the watch is taken down again. Taken as a
    snapshot before the move it would be stale by the first step.

    Whoever it walked through is reported once each by `movement.overrun`,
    which is the printed "for the first time during this movement".
    """
    me = c.me
    answered: set[int] = set()

    def hit_me(ev: Hit) -> None:
        foe = getattr(ev, "attacker", None)
        if (
            getattr(ev, "target", None) != me
            or foe is None
            or foe in answered
            or distance_between(c.world, me, foe) > 2
        ):
            return
        answered.add(foe)
        c.use_power("m6610a2", on=foe)

    watch = c.watch(Hit, hit_me, until=When.EOT, on=me, label=f"{c.ref} answer")
    try:
        through = _through_them(c, c.speed_of(), kind="walk")
    finally:
        c.world.effects.end(watch, "the run is over")
    for foe in through:
        if foe not in answered and alive(c.world, foe):
            answered.add(foe)
            c.use_power("m6610a2", on=foe)


@power(
    "m6610a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m6610a4(c: Cast) -> None:
    """Blocking sight is what a board can be told; "heavily obscured" is a
    degree of it -- concealment to anybody inside as well as across -- and
    zones hold no such setting."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.zone(c.area(), label=c.ref, until=When.EONT, blocks_sight=True,
           obscured="dark")


@power(
    "m6610a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6610a5(c: Cast) -> None:
    """The printed recharge sentence reads the aura's own width, which is why
    a0 lays it under a label the radius can be read back off."""
    me = c.me

    def narrow(ev: TurnStart) -> bool:
        return ev.actor == me and 0 < _aura_radius(c, "m6610a0") < 5

    _recharge_on(c, TurnStart, narrow)
    _relay_aura(c, min(5, (_aura_radius(c, "m6610a0") or 1) + 2))


@power(
    "m6610a6",
    level=12,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d6", 11, kind=LIMITED),
)
def m6610a6(c: Cast) -> None:
    """"Ongoing 10 damage and cannot stand up (save ends both)" is one effect
    carrying both, so there is one saving throw -- and the knockdown itself
    is not on that clock, because prone lasts until the creature stands.

    "Cannot stand up" is `Condition.PINNED`, which is what `c.prone(held=)`
    lays for the same sentence -- said here directly so that the burn rides
    on the same effect and there is one saving throw.
    """
    me = c.me
    if c.first:
        _recharge_on(
            c,
            TurnStart,
            lambda ev: ev.actor == me and _aura_radius(c, "m6610a0") >= 5,
        )
    if c.strike():
        c.hit()
        c.prone()
        c.condition(
            Condition.PINNED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )
    if c.last:
        _relay_aura(c, 1)
