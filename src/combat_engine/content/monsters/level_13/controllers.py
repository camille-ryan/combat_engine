"""Monster abilities, level 13: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=17)` and `Damage("2d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the twelve levels below are kept: a row the database files
under an action heading that is plainly a **trait** is declared
`ActionType.NONE`; a stat block printing no range at all means melee 1; a
blast reading "creatures in the blast" is `EACH_CREATURE` and one reading
"enemies" is `EACH_ENEMY`; a helper written for an earlier level is imported
rather than copied; and a cross-referenced id is read as the row every
sentence plainly means, which is this creature's own.

Six readings this file had to settle.

**One attack roll against two defences.** m2827a3 prints "+14 vs Fortitude
and Will (one attack roll against both defences)", and the header can only
declare one. So the header declares the Fortitude half, `c.strike` returns the
live `AttackResult`, and the same total is compared against Will with
`query.defence` -- which is the function `resolve.attack` itself uses, so the
second comparison sees the same modifiers the first did.

**`EACH_ALLY` includes the caster.** "The m2827 and each ally it can see" is
therefore not `EACH_ALLY` with a burst: the printed line is bounded by sight
rather than by range, and the caster would be counted twice if both halves
were written. The row walks the board instead.

**Two bonuses of one kind do not add.** m289a0's +1 lands on the m289 and on
one adjacent ally; said twice on the same creature it stays +1, which is the
printed stacking rule and why the second is aimed at somebody else.

**"Multiple curses do not stack" is a hold that refuses to be laid twice.**
m4939a0 spreads from the cursed creature to its neighbours, so without the
guard the aura would lay a fresh -2 on top of every standing one each round.

**A sustained zone pays out through its own effect.** `Zones._spawn` hangs
the zone on an `Effect` carrying the sustain cost, and that effect is what
`c.on_sustain` takes -- so "Sustain Standard: the zone persists and it can
move the zone 3 squares" is written where the sustain actually happens
rather than being lost.

**There is no falling and no height.** m2936a3 lifts its target twenty feet
and drops it on a successful save; the restraint is written and the altitude
is noted. `c.fall` is what the printed line wants and blocked.json has been
carrying the same sentence for three other rows.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.skirmishers import _not_grabbing
from combat_engine.content.monsters.level_05.skirmishers import _MELEE_KINDS, _reach_kind
from combat_engine.content.monsters.level_06.controllers import _killer_of
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.skirmishers import (
    _beside_a_great_plant,
    _free_square_within,
    _great_plants,
)
from combat_engine.content.monsters.level_11.controllers import (
    EVERY_DEFENCE,
    _ends_its_turn_in,
    _held_and_softened,
    _softened,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
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
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Ranged,
    Relation,
    Size,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    targets_me,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    creatures,
    defence,
    distance_between,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_ranged, hits_me

#: The sizes m229a3 can shuffle about: the printed line says Medium or
#: smaller, and `Size` is ordered the way the book orders it.
_SMALL_ENOUGH = (Size.TINY, Size.SMALL, Size.MEDIUM)


def _visible_allies(c: Cast) -> list[int]:
    """Everybody on this creature's side it can actually see, itself apart.

    `EACH_ALLY` would do it with a range on the front, and the printed line
    is bounded by sight instead -- and `EACH_ALLY` includes the caster,
    which "the m2827 **and** each ally it can see" already names separately.
    """
    return sorted(mate for mate in c.allies() if c.can_see(mate))


def _grabbing(c: Cast, who: int) -> bool:
    """Has that creature got hold of the caster? The relation runs from the
    grabber to the grabbed, which is the direction `c.grab` sets it in."""
    return c.me in c.world.relations.targets(Relation.GRABBED_BY, who)


def _drift(c: Cast, zone: int, squares_: int) -> bool:
    """Move a zone, as a printed "it can move the zone N squares" asks.

    A zone is squares and nothing else, so moving it is offsetting every one
    of them and letting `Zones.refresh` diff who is standing in the new
    place -- which emits the entered and exited events the holds are hung
    on. Ranked by how many enemies the new footprint covers, because
    `World.decide` takes the head of the list when nobody is playing the
    monster and an unranked list drifts it into a corner.
    """
    placed = dict(c.world.zones.all()).get(zone)
    if placed is None:
        return False
    theirs = {sq for foe in c.enemies() for sq in squares(c.world, foe)}
    steps = [
        (dx, dy)
        for dx in range(-squares_, squares_ + 1)
        for dy in range(-squares_, squares_ + 1)
        if (dx, dy) != (0, 0)
    ]

    def covered(step: tuple[int, int]) -> int:
        dx, dy = step
        return len({(x + dx, y + dy) for x, y in placed.squares} & theirs)

    ranked = sorted(steps, key=lambda step: (-covered(step), step))
    dx, dy = c.world.decide(c.me, "zone", ranked, f"{c.ref}: where the zone drifts")
    placed.squares = frozenset(
        (x + dx, y + dy)
        for x, y in placed.squares
        if c.world.grid.inside((x + dx, y + dy))
    )
    c.world.zones.refresh()
    return True


def _teleport_beside(c: Cast, anchor: int, span: int) -> bool:
    """Blink into a square next to that creature, from wherever this one is.

    `c.teleport` with no `to` offers every square in range to the decider,
    which is useless for a printed line that says where the jump ends.
    """
    beside = _free_square_within(c, anchor, 1)
    if not beside:
        return False
    where = c.world.decide(c.me, "teleport", beside, f"{c.ref}: where it arrives")
    return c.teleport(max(span, 1), to=where)


# ==========================================================================
# m166
# ==========================================================================


@power(
    "m166a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 3),
)
def m166a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m166a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d6", 4),
)
def m166a1(c: Cast) -> None:
    """The briars, which hold and bleed under one saving throw.

    "Save ends both" is one effect carrying the hold and the burn; applied
    separately the victim would get two throws against a thing the card says
    it saves against once.

    The cage itself is a thing on the board with hit points that can be cut
    down, and the engine has no destructible terrain -- `c.zone` has no hit
    points and a conjuration cannot be attacked -- so the cover it gives and
    the 25 hit points it has are noted rather than invented. See the report.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    _held_and_softened(
        c, victim, conditions=(Condition.RESTRAINED,), ongoing=(10, DamageType.UNTYPED)
    )
    c.note("m166a1: the cage gives cover and can be cut down (25 hit points, resist 10)")


@power(
    "m166a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m166a2(c: Cast) -> None:
    """Narrative only: the whole printed Effect is a disguise and a skill
    check against a skill check, and the engine has neither."""
    c.note("m166a2: it looks like some Medium humanoid; an Insight check beats its Bluff")


@power(
    "m166a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m166a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: whoever holds it pays
    for it every turn they go on holding it. The relation runs from the
    grabber to the grabbed, and it is read as the turn begins because a grab
    can end between one turn and the next."""
    me = c.me

    def thorns(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor != me and _grabbing(c, ev.actor):
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, thorns, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m166a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_beside_a_great_plant,
    requires_text="the m166 must begin and end adjacent to a Large or larger plant",
)
def m166a4(c: Cast) -> None:
    """Eight squares, and it has to come out beside another great plant.

    A tree is scenery, which the grid does not hold; a plant creature is what
    remains of the printed list, which is the reading m165a2 settled on four
    levels down. The destinations are gathered by hand: `c.teleport` with no
    `to` offers every square in range, and the printed line says where the
    jump has to end.
    """
    me = c.me
    beside = sorted(
        {
            sq
            for plant in _great_plants(c.world, me)
            for sq in _free_square_within(c, plant, 1)
            if distance_between(c.world, me, plant) <= 8 or c.distance(plant) <= 8
        }
    )
    if not beside:
        return
    where = c.world.decide(me, "teleport", beside, f"{c.ref}: which plant it steps to")
    c.teleport(8, to=where)


# ==========================================================================
# m229
# ==========================================================================

_M229_SHOT_AT = "the m229 is targeted by a ranged attack"
_M229_STRUCK = "an attack hits the m229"
_M229_SWAPPING = "m229a3 caught"
_M229_MARKED = "m229a6 opening"


@power(
    "m229a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 4),
)
def m229a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m229a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m229a1(c: Cast) -> None:
    """The m229 picks where the victim lands, which is what "of the m229's
    choosing" says -- `c.teleport` with no `to` asks the creature being
    moved, and that is a different sentence."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    where = _free_square_within(c, victim, 5, mover=victim)
    if where:
        c.teleport(
            5,
            who=victim,
            to=c.world.decide(c.me, "teleport", where, f"{c.ref}: where it puts them"),
        )


@power(
    "m229a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m229a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m229a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(4),
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=17),
)
def m229a3(c: Cast) -> None:
    """Everybody it catches changes places with somebody else it caught.

    No damage line at all: the shuffle is the whole of the hit. The body
    keeps nothing between its calls, so each creature that is caught carries
    a marker and the last pass reads them back and pairs them off -- an odd
    one out stays where it is, which is what a swap of pairs comes to.

    "Ranged sight" is the board: twenty squares is further than any map here
    and is what the range field can say.
    """
    victim = c.target
    if victim is not None and c.size_of(on=victim) in _SMALL_ENOUGH and c.strike():
        c.effect(_M229_SWAPPING, until=When.EOT, on=victim)
    if not c.last:
        return
    caught = c.suffering(_M229_SWAPPING)
    for first, second in zip(caught[::2], caught[1::2], strict=False):
        c.swap(second, who=first)
    for who in caught:
        for eff in list(c.world.effects.of(who)):
            if eff.label == _M229_SWAPPING:
                c.world.effects.end(eff, "the places are changed")


@power(
    "m229a4",
    level=13,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M229_SHOT_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_ranged), text=_M229_SHOT_AT),
)
def m229a4(c: Cast) -> None:
    """Somebody else takes the shot, and it appears beside the archer.

    `c.redirect` writes the new target onto `AttackDeclared`, which
    `resolve.roll` reads back -- the one window in which an attack can still
    be moved. The substitute is chosen from within five squares of the m229,
    which is the printed radius.
    """
    who = getattr(c.trigger, "attacker", None)
    instead = sorted(
        other
        for other in creatures(c.world)
        if other not in (c.me, who)
        and alive(c.world, other)
        and c.distance(other) <= 5
    )
    if instead:
        c.redirect(to=c.choose(instead, f"{c.ref}: who takes it instead"))
    if who is not None and alive(c.world, who):
        _teleport_beside(c, who, 10)


@power(
    "m229a5",
    level=13,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M229_STRUCK,
    on=Trigger(Hit, when=hits_me, text=_M229_STRUCK),
)
def m229a5(c: Cast) -> None:
    """Four defences, one at a time, because a defence is a modifier on the
    creature and there is no word for all of them."""
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me, kind="untyped")


@power(
    "m229a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
)
def m229a6(c: Cast) -> None:
    """It shows somebody where to cut, and the next blow lands perfectly.

    No attack roll, as printed. The +5 belongs to whoever swings, and neither
    the bonus nor the critical can be laid on the victim: both are read off
    the *attacker* as the roll is made. So the hold watches for the first
    melee attack declared against the target and fits them to that creature
    in the `AttackDeclared` window -- which is before `resolve.roll` totals
    the modifiers, the one moment either can still matter.

    An automatic critical is `crit_range`: the floor is twenty minus whatever
    modifiers say, so twenty off it makes every face a critical.

    Neither is `once=True`. A one-shot bonus that is neither a defence nor
    damage is spent on `AttackRolled`, and `resolve.attack` reads
    `crit_range` **again** after that window closes -- so a one-shot
    `crit_range` is taken off before the comparison it exists for and the
    critical never happens. Both are laid plain and both come down on the
    `Hit` or `Miss` instead, which is the moment the defence one-shots are
    already spent at. See the report.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    hold = c.effect(_M229_MARKED, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def against(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    def guide(ev: AttackDeclared) -> None:
        if hold.ended or ev.target != victim or _reach_kind(ev) not in _MELEE_KINDS:
            return
        who = ev.attacker
        lent = [
            c.bonus("attack", 5, until=When.ENCOUNTER, on=who, kind="power", when=against),
            c.bonus(
                "crit_range", 20, until=When.ENCOUNTER, on=who, kind="untyped", when=against
            ),
        ]

        def spend(later: Hit | Miss) -> None:
            if later.attacker != who or later.target != victim:
                return
            for eff in lent:
                if eff is not None and not eff.ended:
                    c.world.effects.end(eff, "the blow has been struck")

        for landed in (Hit, Miss):
            if lent[0] is not None:
                lent[0].subs.append(c.world.bus.on(landed, spend, owner=me))
        c.world.effects.end(hold, "the opening was taken")

    hold.subs.append(
        c.world.bus.on(AttackDeclared, guide, window=Window.BEFORE, owner=me)
    )


# ==========================================================================
# m2827
# ==========================================================================

_M2827_FLANKED = "a creature moves into a space where it flanks the m2827"
_M2827_SNARE = "m2827a4 snare"


def _moved_into_flank(world: World, me: int, ev: MoveEnd) -> bool:
    """`MoveEnd`, not `MoveStart`: the question is about the square the
    creature has arrived in, and `MoveStart` fires before the first step."""
    from combat_engine.engine.query import flanked_by

    return ev.actor != me and flanked_by(world, me, ev.actor)


@power(
    "m2827a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
)
def m2827a0(c: Cast) -> None:
    """The extra die is a charge rider, and `c.charge` is true on the swing a
    charge makes -- which is what puts `charge` in both modifier contexts and
    on the attack events."""
    if not c.strike():
        return
    c.hit()
    if c.charge:
        c.damage("1d6")


@power(
    "m2827a1",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 4),
    trigger=_M2827_FLANKED,
    on=Trigger(MoveEnd, when=_moved_into_flank, text=_M2827_FLANKED),
)
def m2827a1(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the printed line
    says the triggering creature, which is rarely the one a dispatcher would
    pick."""
    who = getattr(c.trigger, "actor", None)
    if who is not None and alive(c.world, who) and c.strike(on=who):
        c.hit(on=who)


@power(
    "m2827a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6),
)
def m2827a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m2827a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=1,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2827a3(c: Cast) -> None:
    """One roll, two defences, and a different half of the line for each.

    The header declares the Fortitude comparison because a header can only
    hold one; the same total is then measured against Will with
    `query.defence`, which is the function `resolve.attack` uses for the
    first comparison, so both see the same modifiers. A natural 1 misses
    whatever the total says, which is the rule and is why it is asked.

    The printed recharge is a sentence on top of the die the database files:
    it comes back when one of its own goes down within ten squares. "A m2827"
    is a creature off this stat block, which is `Ident.ref` and nothing else
    -- but the printed line is about an ally falling, so the side is compared
    directly: `query.enemies` filters out the dead and would be false on
    every `Dropped`.
    """
    me = c.me

    def one_of_ours_fell(ev: Dropped) -> bool:
        return (
            ev.actor != me
            and team(c.world, ev.actor) is team(c.world, me)
            and distance_between(c.world, me, ev.actor) <= 10
        )

    _recharge_on(c, Dropped, one_of_ours_fell)
    victim = c.target
    if victim is None:
        return
    result = c.strike()
    if result.natural != 1 and result.total >= defence(c.world, victim, WILL):
        c.hit()
    if result.hit:
        c.push(2)
        c.prone()


@power(
    "m2827a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m2827a4(c: Cast) -> None:
    """Ground that closes round whoever stops in it.

    "Ends its turn within the zone" is the one zone clause `c.burns` does not
    cover -- that one bites on entering and on starting a turn. The way out
    is a free action the printed line prices at 3d8, offered at the top of
    the held creature's turn, which is the only moment in the round a free
    action of that shape can be put to it.

    Sustaining moves it: the zone hangs on an `Effect` carrying the sustain
    cost, and that effect is what `c.on_sustain` takes.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    zone = c.zone(c.area(), label=_M2827_SNARE, until=When.SUSTAIN, sustain=STANDARD)

    def caught(who: int) -> None:
        if who in c.enemies():
            c.world.effects.apply(
                who, me, When.SAVE_ENDS, label=_M2827_SNARE,
                conditions=(Condition.IMMOBILIZED,),
            )

    def offer(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        for eff in list(c.world.effects.of(ev.actor)):
            if eff.label != _M2827_SNARE or eff.source != me:
                continue
            if c.may("take 3d8 damage to tear free", who=ev.actor):
                c.damage("3d8", on=ev.actor)
                c.world.effects.save(eff)
            return

    _ends_its_turn_in(c, zone, caught)
    c.watch(TurnStart, offer, until=When.ENCOUNTER, on=me, label=f"{c.ref} tearing free")
    placed = dict(c.world.zones.all()).get(zone)
    if placed is not None:
        c.on_sustain(placed.effect, lambda: _drift(c, zone, 3))


@power(
    "m2827a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2827a5(c: Cast) -> None:
    """Ten back and a throw each, itself included.

    Not `EACH_ALLY`: that includes the caster, which the printed line names
    separately, and it takes a range where the printed line takes sight.
    """
    for who in [c.me, *_visible_allies(c)]:
        c.heal(10, on=who)
        c.save(on=who)


# ==========================================================================
# m289
# ==========================================================================

_M289_FELLED = "the m289 drops to 0 hit points"
_M289_HELD = "a condition is laid on the m289"
_M289_ROT = "m289a3 rot"


@power(
    "m289a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 9),
)
def m289a0(c: Cast) -> None:
    """Both halves of the printed bonus are +1 and of one kind, so they have
    to land on two different creatures to come to anything: said twice on the
    m289 the larger wins and it is +1 either way."""
    if not c.strike():
        return
    c.hit()
    c.bonus(AC, 1, until=When.EONT, on=c.me, kind="power")
    mate = sorted(who for who in c.allies() if c.adjacent(who))
    if mate:
        c.bonus(
            AC, 1, until=When.EONT, kind="power",
            on=c.choose(mate, f"{c.ref}: which ally stands with it"),
        )


@power(
    "m289a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 9, kind=LIMITED),
)
def m289a1(c: Cast) -> None:
    """The printed "requires mace" is satisfied by construction: the weapon
    is part of this creature's stat block and the requirement names which of
    its arms the row swings, not a state it can be out of. A `Gear` gate
    would refuse the row forever -- a monster carries none."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m289a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d8", 9, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m289a2(c: Cast) -> None:
    """The penalty is not under a saving throw, so it is four modifiers on
    the clock rather than one hold carrying them."""
    if not c.strike():
        return
    c.hit()
    for defended in EVERY_DEFENCE:
        c.penalty(defended, 2, until=When.EONT, kind="untyped")


@power(
    "m289a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.FREE,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=WILL, printed=15),
    trigger=_M289_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M289_FELLED),
)
def m289a3(c: Cast) -> None:
    """A death throe, and the contagion is the whole of the hit.

    The dispatcher offers it to a creature that is no longer alive, which is
    the only way a row of this shape fires. A disease track is not something
    the engine models, so it is a named hold on the save-ends clock rather
    than an invented condition -- which is what `c.effect` is for, and what a
    row reading it would look for.
    """
    if c.strike():
        c.effect(_M289_ROT, until=When.SAVE_ENDS)


@power(
    "m289a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M289_HELD,
    on=Trigger(ConditionApplied, when=targets_me, text=_M289_HELD),
)
def m289a4(c: Cast) -> None:
    """It shrugs the thing off as it lands.

    `targets_me` rather than `about_me`: `ConditionApplied` names its subject
    `target` and `about_me` reads `ev.actor` and only that, so it would be
    false here forever. `Effects.apply` installs everything before it
    announces, which is what makes ending the effect from inside this window
    work at all -- the hold exists to be found.
    """
    me = c.me
    condition = getattr(c.trigger, "condition", None)
    if condition is None:
        return
    for eff in list(c.world.effects.of(me)):
        if condition in eff.conditions:
            c.world.effects.end(eff, c.ref)


@power(
    "m289a5",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m289a5(c: Cast) -> None:
    """A surge is a quarter of maximum hit points, which is the fifty-one the
    card prints -- so the printed number is the engine's own arithmetic and
    is not written out. `on=c.me` because `c.surge` falls to the target and
    this row spends its own.

    A monster spends a healing surge only where a row says so, and this one
    says so; it carries two at this tier.
    """
    c.surge(on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.SONT, on=c.me, kind="untyped")


# ==========================================================================
# m2936
# ==========================================================================


@power(
    "m2936a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2936a0(c: Cast) -> None:
    """Half of everything but force, and only while it is whole.

    `c.insubstantial` is the engine's "everything that reaches this creature
    is halved" and has no exemption in it, so the halving is done on
    `DamageRolled` -- which carries a mutable `amount` that `resolve` reads
    back, and which is the only place the type of a packet can be seen. The
    health is asked as each blow lands rather than watched for, because the
    crossing works both ways.

    The printed line says "from all attacks"; the event does not record
    whether a packet came from one, so a burn is halved too. Noted.
    """
    me = c.me

    def soak(ev: Any) -> None:
        if ev.target != me or ev.amount <= 0 or c.bloodied(me):
            return
        if ev.dtype is not DamageType.FORCE:
            ev.amount //= 2

    from combat_engine.engine.events import DamageRolled

    c.watch(DamageRolled, soak, until=When.ENCOUNTER, on=me, label=c.ref)
    c.note("m2936a0: the halving is printed for attacks and here covers every packet")


@power(
    "m2936a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 12),
)
def m2936a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2936a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d10", 10),
)
def m2936a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m2936a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
)
def m2936a3(c: Cast) -> None:
    """No damage line at all: the hold is the whole of the hit.

    There is no falling and no vertical position, so the twenty feet, the
    twenty more on each failed save and the drop on a successful one are
    noted rather than invented -- what is left, and what the printed line
    also says, is that the target is held until it saves. `c.fall` is what
    would finish it; see the report.
    """
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
        c.note("m2936a3: the target is lifted 20 feet, and falls when it saves")


# ==========================================================================
# m350
# ==========================================================================

_M350_FELLED = "the m350 drops to 0 hit points"


def _reach_of(c: Cast, who: int) -> int:
    """How far that creature's own basic attack goes.

    "One enemy within its reach" is measured off the swing it would make, not
    off one square: a creature with a polearm threatens two and the printed
    line means both.
    """
    from combat_engine.engine import Powers

    known = c.world.get(who, Powers)
    p = get(known.basic) if known and known.basic else None
    return p.reach.size if p is not None else 1


@power(
    "m350a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 6),
)
def m350a0(c: Cast) -> None:
    """The necrotic is a second packet rather than part of the declared line:
    the header's damage is untyped and only the rider is necrotic."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC)


@power(
    "m350a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m350a1(c: Cast) -> None:
    """A charge whose blow is this row's own line.

    `c.charge_at` cannot be used: it reaches the swing through `use` and the
    row it would reach for is this one, already in flight -- so the flag goes
    up by hand, `c.run_at` walks, and the header rolls. The flag is what puts
    `charge` on the attack events and in both modifier contexts.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    try:
        c.run_at(victim)
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)
    finally:
        c.charge = False


@power(
    "m350a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m350a2(c: Cast) -> None:
    """It sends a wounded one back in.

    Declared with no target: the dispatcher aims a row at an enemy and this
    one is about an ally, and a bloodied one at that. The enemy is picked
    from what that creature could actually reach -- a granted swing at
    somebody across the room is not a swing at all.
    """
    bloodied = sorted(
        mate for mate in c.allies() if c.bloodied(mate) and c.distance(mate) <= 10
    )
    if not bloodied:
        return
    mate = c.choose(bloodied, f"{c.ref}: which wounded ally swings")
    if mate is None:
        return
    span = _reach_of(c, mate)
    prey = sorted(
        foe for foe in c.enemies() if distance_between(c.world, mate, foe) <= span
    )
    if prey:
        c.grant_attack(mate, on=c.choose(prey, f"{c.ref}: who it swings at"))


@power(
    "m350a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 3, dtype=DamageType.FORCE),
)
def m350a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m350a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M350_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M350_FELLED),
)
def m350a4(c: Cast) -> None:
    """A death throe. `c.basic` swings whichever row this creature's basic
    attack actually is, which is the printed "makes a melee basic attack"."""
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        c.basic(on=prey)


# ==========================================================================
# m4939
# ==========================================================================

_M4939_CURSE = "m4939a0 curse"
_M4939_HOLD = "m4939a2 grip"


@power(
    "m4939a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4939a0(c: Cast) -> None:
    """An aura 1 whose curse walks outward from whoever caught it.

    Two ways in, both read at the top of a turn: standing in the aura, or
    standing beside one of your own who is already carrying it. "Multiple
    curses do not stack" is the hold refusing to be laid twice -- without it
    the aura would put a fresh -2 on top of every standing one each round.

    The vulnerability is held by the creature that has it and cannot ride the
    same effect, so it is tied to the curse by the curse's ending, which is
    what makes one clock end both.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def lay(who: int) -> None:
        if who == me or any(
            eff.label == _M4939_CURSE for eff in c.world.effects.of(who)
        ):
            return
        cursed = c.world.effects.apply(
            who, me, When.EOTNT, label=_M4939_CURSE,
            mods=[(who, mod) for mod in _softened(c, defences=2)],
        )
        exposed = c.vulnerable(5, until=When.EOTNT, on=who)
        if exposed is not None:
            cursed.on_end.append(
                lambda: c.world.effects.end(exposed, "the curse lifted")
            )

    def spread_it(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(ring):
            lay(ev.actor)
            return
        for other in c.within(1, of=ev.actor):
            if other == ev.actor or team(c.world, other) is not team(c.world, ev.actor):
                continue
            if any(eff.label == _M4939_CURSE for eff in c.world.effects.of(other)):
                lay(ev.actor)
                return

    c.watch(TurnStart, spread_it, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4939a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 10),
)
def m4939a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4939a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d10", 5),
    requires=_not_grabbing,
    requires_text="the m4939 must not have a creature grabbed",
)
def m4939a2(c: Cast) -> None:
    """It takes hold, and every turn it keeps hold costs the victim.

    The grab is a relation with no clock of its own, so the sustain is a hold
    laid beside it carrying the cost -- `c.on_sustain` is what pays out, and
    the grab is released when the hold goes, which is the printed "sustain
    the grab" read as what happens when it is not sustained.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    grip = c.grab(on=victim)
    if grip is None:
        return
    keeping = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=_M4939_HOLD, sustain_cost=STANDARD
    )
    keeping.on_end.append(lambda: c.world.effects.end(grip, "it let go"))

    def squeeze() -> None:
        if alive(c.world, victim):
            c.damage("3d10", 5, on=victim)

    c.on_sustain(keeping, squeeze)


@power(
    "m4939a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m4939a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying the blindness and the burn."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.BLINDED, until=When.SAVE_ENDS, ongoing=(5, DamageType.NECROTIC)
        )


@power(
    "m4939a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4939a4(c: Cast) -> None:
    """It walks off with whoever it is holding.

    `movement.step` carries a rider and nothing else, so the prisoner is put
    down beside the m4939 once the move is over -- which keeps the grab
    inside its own reach, and a grab is broken by distance and nothing else.
    The waiver is the printed "does not provoke an opportunity attack from
    the grabbed creature", named rather than blanket.

    "Opportunity attacks that miss the m4939 instead hit the grabbed
    creature" has nowhere to go: a miss carries no damage to move and
    `c.redirect` changes who is *rolled against*, which is a different
    sentence. Noted. See the report.
    """
    me = c.me
    held = sorted(c.world.relations.targets(Relation.GRABBED_BY, me))
    prisoner = held[0] if held else None
    waiver = c.no_provoke(from_=prisoner, until=When.EOT) if prisoner else None
    try:
        c.move(c.speed_of())
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the march is over")
    if prisoner is None or not alive(c.world, prisoner):
        return
    if not c.adjacent(prisoner):
        beside = _free_square_within(c, me, 1, mover=prisoner)
        if beside:
            where = c.world.decide(me, "slide", beside, f"{c.ref}: dragged along")
            c.slide(c.speed_of(), on=prisoner, to=where)
    c.note("m4939a4: an opportunity attack that misses it should hit the prisoner")


# ==========================================================================
# m806
# ==========================================================================

_M806_STANCE = "m806a3 stance"
_M806_SWUNG_AT = "an enemy attacks the m806 while m806a3 is active"
_M806_ALLY_KILLED = "an enemy kills an ally of the m806 in its line of sight"


def _in_the_stance(world: World, me: int) -> bool:
    return any(eff.label == _M806_STANCE for eff in world.effects.of(me))


def _swung_at_in_the_stance(world: World, me: int, ev: AttackDeclared) -> bool:
    return (
        ev.target == me
        and ev.attacker != me
        and team(world, ev.attacker) is not team(world, me)
        and _in_the_stance(world, me)
    )


def _my_ally_was_killed(world: World, me: int, ev: Dropped) -> bool:
    """`query.enemies` filters out the dead, so the side of whoever fell is
    compared directly -- the usual way this predicate is silently false."""
    if ev.actor == me or team(world, ev.actor) is not team(world, me):
        return False
    ask = Cast(world=world, me=me, ref="m806a2")
    killer = _killer_of(ask, ev.actor)
    return (
        killer is not None
        and killer != me
        and team(world, killer) is not team(world, me)
        and ask.can_see(killer)
    )


@power(
    "m806a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 6),
)
def m806a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m806a1",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    no_provoke=True,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 5, dtype=DamageType.RADIANT, half_on_miss=True),
    trigger=_M806_SWUNG_AT,
    on=Trigger(AttackDeclared, when=_swung_at_in_the_stance, text=_M806_SWUNG_AT),
)
def m806a1(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the printed line
    says the creature that attacked it. The stance is asked in the predicate
    rather than here, so the row is never offered while it is out of it."""
    who = getattr(c.trigger, "attacker", None)
    if who is None or not alive(c.world, who):
        return
    if c.strike(on=who):
        c.hit(on=who)
    else:
        c.hit(on=who, half=True)


@power(
    "m806a2",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    no_provoke=True,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
    trigger=_M806_ALLY_KILLED,
    on=Trigger(Dropped, when=_my_ally_was_killed, text=_M806_ALLY_KILLED),
)
def m806a2(c: Cast) -> None:
    """`Dropped` names only the creature that fell, so the killer is the last
    blow it took -- which is the only record there is of whose it was."""
    who = getattr(c.trigger, "actor", None)
    killer = _killer_of(c, who) if who is not None else None
    if killer is None or not alive(c.world, killer):
        return
    if c.strike(on=killer):
        c.hit(on=killer)
        c.ongoing(5, DamageType.FIRE, on=killer)


@power(
    "m806a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
)
def m806a3(c: Cast) -> None:
    """It stands still and everything around it burns brighter.

    `c.stance` is one at a time and lasts until another is taken, which is
    half of the printed clock; the other half is the end of its next turn and
    a step in any direction, so both are hung on the hold. Resistance is per
    damage type and this is all of them, which is what `c.resist` with no
    type named does.

    The allies' rider is asked as each blow lands -- line of sight changes as
    the fight moves, and the printed line says "in its line of sight" rather
    than "when this began".
    """
    me = c.me
    held = c.stance(label=_M806_STANCE)
    shield = c.resist(20, until=When.EONT, on=me)
    if shield is not None:
        held.on_end.append(lambda: c.world.effects.end(shield, "the stance broke"))

    def brighter(ev: Hit) -> None:
        if held.ended or ev.attacker == me or ev.attacker not in c.allies():
            return
        if _reach_kind(ev) in _MELEE_KINDS and c.can_see(ev.attacker):
            c.damage("1d8", dtype=DamageType.RADIANT, on=ev.target)

    def moved(ev: MoveEnd) -> None:
        if ev.actor == me and not held.ended:
            c.world.effects.end(held, "it moved")

    held.subs.append(c.world.bus.on(Hit, brighter, owner=me))
    held.subs.append(c.world.bus.on(MoveEnd, moved, owner=me))
    c.world.effects.apply(
        me, me, When.EONT, label=f"{_M806_STANCE} clock",
        on_end=[lambda: c.world.effects.end(held, "the stance ran out")],
    )
