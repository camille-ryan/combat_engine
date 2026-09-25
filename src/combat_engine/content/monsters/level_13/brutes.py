"""Monster abilities, level 13: the brutes, and the minion one of them makes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("2d12", 13)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the twelve levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; a stat block printing no range at all means melee 1;
a printed "crit NdX + n" *replaces* the damage and is a roll, so `_crit_line`
deals it flat past the engine's own rule that a critical maxes the declared
dice; and a helper written for an earlier level is imported rather than
copied.

Five things this file had to settle.

**"Whenever its attack bloodies an enemy" is a crossing, and `Bloodied` is
emitted after `DamageApplied`.** So the rider rides the damage and works the
crossing out from the packet: `ev.hp` is what is left and `ev.amount` is what
came off, so `ev.hp + ev.amount` is what the creature had, and the enemy was
above the halfway mark before this blow and is not now. Watching `Bloodied`
instead would have said nothing about who caused it -- the event carries
only the creature that bled.

**A shapechanger whose basic attack belongs to one of its two shapes.**
m3034's `Powers.basic` is the humanoid weapon row, because that is the first
standard melee attack on the card, and that row prints a Requirement naming
the shape. So in wolf form "makes two melee basic attacks" finds its own
basic refused, and the bite stands in -- which is what a melee basic attack
*is* for a creature whose shape has changed what it swings with. Neither
Requirement is read as false for a creature that has not changed shape yet:
the card does not say which form it was found in, which is the reading
`_in_shape` settled on at level 4.

**A corpse that gets up as something else.** m5057a2 names the minion below
it by ref, which is exactly what `c.summon` takes -- and the summoning waits
for the m5057's own turn to begin, because that is the moment the printed
line names. The square is the one the body fell in, noted when it fell,
since by the time the turn comes round the entity has been lifted off the
board.

**A death throe that cannot read what killed it.** m5058a1 triggers on "a
melee or a ranged attack drops the m5058", and `Dropped` carries the
creature and nothing about the blow. The row is declared on the half that
can be read and the rest is in the report.

**None of these rows spends a healing surge.** Each carries two at this
tier, for a leader line to spend, and none of them prints one -- so none is
spent and none takes a second wind.

The brutes in ref order, then the minion the last of them raises.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_04.brutes import _change_shape, _in_shape
from combat_engine.content.monsters.level_06.controllers import _is_humanoid, _living
from combat_engine.content.monsters.level_07.brutes import _aura, _crit_line
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_13.soldiers import _burn_and_hold
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Health,
    Keyword,
    Melee,
    Moved,
    Position,
    Powers,
    Ranged,
    Square,
    TurnStart,
    UpTo,
    Usage,
    When,
    power,
    use,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, team
from combat_engine.engine.triggers import Trigger, about_me

#: m3034's two shapes and the prefix its hold is labelled with, so the three
#: gated rows can read which one is in force.
_M3034_SHAPE = "m3034a5 "
_M3034_SHAPES = ("humanoid", "wolf")


def _bleeds_when_it_moves(c: Cast, victim: int, amount: int) -> Effect:
    """"The target takes N damage for each square it moves on its turn."

    `Moved` is one step with both ends of it, which is the only event in the
    engine that counts squares -- `MoveEnd` fires once however far the
    creature went. Whose turn it is, is asked as well, because the printed
    line names a turn rather than a duration.
    """

    def step(ev: Moved) -> None:
        if ev.actor == victim and c.turn_of() == victim:
            c.flat(amount, on=victim)

    return c.watch(Moved, step, until=When.SAVE_ENDS, on=victim, label=c.ref)


# ==========================================================================
# m254
# ==========================================================================


@power(
    "m254a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m254a0(c: Cast) -> None:
    """Blood in the water is worth ten hit points to it.

    Ridden on the damage rather than on `Bloodied`, which is emitted after
    the packet lands and names only the creature that bled -- nothing on it
    says whose blow did it. The crossing is worked out from the packet:
    `ev.hp` is what is left, `ev.amount` is what came off, and the two added
    together are what the creature had a moment ago.
    """
    me, ref = c.me, c.ref

    def drew_blood(ev: DamageApplied) -> None:
        if ev.source != me or ev.amount <= 0 or ev.hp <= 0:
            return
        if team(c.world, ev.target) is team(c.world, me):
            return
        health = c.world.get(ev.target, Health)
        if health is None or not health.bloodied:
            return
        if ev.hp + ev.amount > health.max_hp // 2:
            c.temp_hp(10, on=me)

    c.watch(DamageApplied, drew_blood, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m254a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 13),
)
def m254a1(c: Cast) -> None:
    """The printed "crit 2d12 + 37" replaces the damage and is a roll."""
    if c.strike():
        _crit_line(c, "2d12", 37)


@power(
    "m254a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 19),
)
def m254a2(c: Cast) -> None:
    """The heavier swing: two less to hit and six more when it lands."""
    if c.strike():
        _crit_line(c, "2d12", 43)


def _a_bloodied_enemy(world: Any, eid: int) -> bool:
    from combat_engine.engine.query import enemies

    for foe in enemies(world, eid):
        health = world.get(foe, Health)
        if health is not None and health.bloodied and health.hp > 0:
            return True
    return False


@power(
    "m254a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    requires=_a_bloodied_enemy,
    requires_text="the m254 must have a bloodied enemy to swing at",
)
def m254a3(c: Cast) -> None:
    """Twice at whatever is already hurt.

    Which of the two swings above is "greataxe" is not a question a stripped
    card can answer, so the row swings what the board says this creature's
    basic attack is -- `Powers.basic`, which is the first standard melee
    attack on the stat block. `c.basic` is the one call that reads it.

    Declared with no target: "a bloodied enemy" is narrower than any
    `Target` can say, so the Requirement carries whether there is one and
    the body picks.
    """
    hurt = sorted(
        foe
        for foe in c.enemies()
        if c.adjacent(foe) and c.bloodied(on=foe) and alive(c.world, foe)
    )
    victim = c.choose(hurt, "m254a3: which of them it finishes") if hurt else None
    if victim is None:
        return
    for _ in range(2):
        if not alive(c.world, victim):
            return
        c.basic(on=victim)


# ==========================================================================
# m271
# ==========================================================================


@power(
    "m271a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 11),
)
def m271a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m271a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 11, kind=LIMITED),
)
def m271a1(c: Cast) -> None:
    """"One or two creatures" is `UpTo(2)`, and the body is called once for
    each of them."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m271a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 8),
)
def m271a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2809
# ==========================================================================


@power(
    "m2809a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 3),
)
def m2809a0(c: Cast) -> None:
    """"Until the end of its next turn" is the *target's* next turn, which is
    `When.EOTNT` -- the one duration clocked on whoever carries it."""
    if c.strike():
        c.hit()
        c.penalty(AC, 2, until=When.EOTNT)


@power(
    "m2809a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m2809a1(c: Cast) -> None:
    """"Pulls the target adjacent to it" names the destination by distance
    rather than by square, so the pull is exactly as far as the gap: a pull
    is the forced move that ends nearer whoever is doing it."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.pull(max(0, c.distance(victim) - 1), on=victim)


@power(
    "m2809a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5, kind=LIMITED, half_on_miss=True),
)
def m2809a2(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to give the row back sooner.

    Hit and miss both leave the same clause behind at different strengths,
    so the miss branch is not a bare `half=True` -- it carries its own
    lighter hold.
    """
    me, victim = c.me, c.target
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if victim is None:
        return
    if c.strike():
        c.hit()
        _bleeds_when_it_moves(c, victim, 2)
    else:
        c.hit(half=True)
        _bleeds_when_it_moves(c, victim, 1)


# ==========================================================================
# m3034
# ==========================================================================


@power(
    "m3034a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d4", 6),
    requires=_in_shape(_M3034_SHAPE, "humanoid"),
    requires_text="the m3034 must be in its humanoid form",
)
def m3034a0(c: Cast) -> None:
    """The printed "crit 8d4 + 22" replaces the damage and is a roll."""
    if c.strike():
        _crit_line(c, "8d4", 22)


@power(
    "m3034a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 3),
    requires=_in_shape(_M3034_SHAPE, "wolf"),
    requires_text="the m3034 must be in its wolf form",
)
def m3034a1(c: Cast) -> None:
    """The engine holds no diseases and no track to move along, so being
    exposed to one is noted rather than invented."""
    if c.strike():
        c.hit()
        c.note("m3034a1: the target is exposed to the m3034's frenzy")


@power(
    "m3034a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m3034a2(c: Cast) -> None:
    """Two swings, at one creature or at two.

    The printed Effect does not say, so the header takes up to two and a
    single target is struck twice -- the reading that loses nothing.

    `c.basic` is what a "melee basic attack" is, and for this creature it is
    the humanoid weapon row, because that is the first standard melee attack
    on the card. In wolf form that row refuses itself by its own
    Requirement, and the bite is what the creature is swinging with, so it
    stands in.
    """
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        if not c.basic(on=victim):
            use(c.world, c.me, "m3034a1", targets=[victim], spend=False)


@power(
    "m3034a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_in_shape(_M3034_SHAPE, "wolf"),
    requires_text="the m3034 must be in its wolf form",
)
def m3034a3(c: Cast) -> None:
    """The step comes before the bite, against the usual order, because here
    it is the thing that brings the target into reach."""
    victim = c.target
    if victim is None:
        return
    c.shift(6)
    use(c.world, c.me, "m3034a1", targets=[victim], spend=False)


@power(
    "m3034a4",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
)
def m3034a4(c: Cast) -> None:
    """It howls, and the pack takes heart and bites.

    "Each ally that has a m3034a1 attack" is read literally, off what each
    ally knows: the card names the row by ref and that is the only thing on
    the board that answers to it. The swing is the ally's own free action,
    so nothing is spent for it.

    Declared with no target: the printed burst catches allies and
    `EACH_ALLY` would put the m3034 itself in the temporary hit points,
    which "each ally in the burst" does not mean.
    """
    me = c.me
    for friend in sorted(c.within(10, side="ally")):
        if friend == me or not alive(c.world, friend):
            continue
        c.temp_hp(15, on=friend)
        known = c.world.get(friend, Powers)
        if known is None or "m3034a1" not in known.all:
            continue
        near = sorted(
            (foe for foe in c.enemies() if c.adjacent_to(foe, friend)),
            key=lambda foe: (c.distance(foe), foe),
        )
        if near:
            use(c.world, friend, "m3034a1", targets=[near[0]], spend=False)


@power(
    "m3034a5",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m3034a5(c: Cast) -> None:
    """Two shapes and nothing else: the statistics do not change, so all the
    form is for is the Requirement on the three rows above it.

    A polymorph is not a stance, so the shape worn before is ended by hand.
    """
    _change_shape(c, _M3034_SHAPE, _M3034_SHAPES)


# ==========================================================================
# m327
# ==========================================================================


@power(
    "m327a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m327a0(c: Cast) -> None:
    """Only the burn is printed as fire; the declared line is untyped, so the
    header carries no type and the ongoing names one."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m5057
# ==========================================================================


@power(
    "m5057a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5057a0(c: Cast) -> None:
    """Living things flinch from it.

    The penalty is to attacks *against the m5057* rather than to every
    attack the neighbour makes, which is a much heavier card than the one
    printed -- and the attack context carries `target`, so that is the gate.

    The aura helper is the right one here: the hold is carried for exactly
    as long as its owner stands inside, and `ZoneEntered` and `ZoneExited`
    are the two moments it should go on and come off.
    """
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and _living(c, who)

    def hold(who: int) -> Effect | None:
        def at_me(ctx: dict[str, Any]) -> bool:
            return ctx.get("target") == me

        return c.penalty(
            "attack", 2, on=who, until=When.ENCOUNTER, kind="untyped", when=at_me
        )

    _aura(c, 1, eligible, hold)


@power(
    "m5057a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5057a1(c: Cast) -> None:
    """The disease it carries is a row on another stat block, and the engine
    holds no diseases and no track to move along, so being exposed to it is
    noted."""
    if c.strike():
        c.hit()
        c.note("m5057a1: the target is exposed to the m5057's rot")


def _a_living_enemy_adjacent(world: Any, eid: int) -> bool:
    from combat_engine.engine import Cast as _Cast
    from combat_engine.engine.query import adjacent, enemies

    ask = _Cast(world=world, me=eid, ref="m5057a2")
    return any(
        adjacent(world, eid, foe) and _living(ask, foe) for foe in enemies(world, eid)
    )


@power(
    "m5057a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    requires=_a_living_enemy_adjacent,
    requires_text="the m5057 must have a living enemy beside it",
)
def m5057a2(c: Cast) -> None:
    """No damage on the hit at all: the burn is the whole of it, and it gets
    worse twice.

    "One living enemy in the burst" is narrower than any `Target` can say,
    so the Requirement carries whether there is one and the body picks.

    The two failed saves are a chain of `escalate`, each step ending the one
    before it, so the victim never carries two of these and never gets two
    saving throws against one bite.

    The corpse is raised at the start of the m5057's next turn, which is the
    moment the printed line names -- so the square is noted when the body
    falls, because by then the entity has been lifted off the board and
    there is nowhere to ask. "The wretch must be destroyed first" is a
    condition on raising the creature properly afterwards, which the engine
    holds nothing about, and is noted.
    """
    me = c.me
    near = sorted(
        foe for foe in c.enemies() if c.adjacent(foe) and _living(c, foe)
    )
    victim = c.choose(near, "m5057a2: which of them it breathes on") if near else None
    if victim is None or not c.strike(on=victim):
        return
    c.note("m5057a2: the target is exposed to the m5057's rot")

    def stunned(eff: Effect) -> None:
        c.world.effects.end(eff, "the second save failed")
        _burn_and_hold(
            c, eff.owner, 20, DamageType.NECROTIC, conditions=(Condition.STUNNED,)
        )

    def worse(eff: Effect) -> None:
        c.world.effects.end(eff, "the first save failed")
        _burn_and_hold(c, eff.owner, 15, DamageType.NECROTIC, escalate=stunned)

    _burn_and_hold(c, victim, 10, DamageType.NECROTIC, escalate=worse)

    grave: list[Square] = []

    def fell(ev: Dropped) -> None:
        if ev.actor != victim or not _is_humanoid(c, victim):
            return
        here = c.world.get(victim, Position)
        if here is not None:
            grave.append(here.square)

    def rises(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not grave:
            return
        c.summon("m5058", at=grave.pop(0))

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=f"{c.ref} corpse")
    c.watch(TurnStart, rises, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


# ==========================================================================
# m5058. A minion deals its printed number on a hit and its single hit point
# is in the database; `kind=MINION` is what says the number is flat because
# the creature is one, which is how it rescales.
# ==========================================================================


@power(
    "m5058a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=13, dtype=DamageType.NECROTIC, kind=MINION),
)
def m5058a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5058_FELLED = "the m5058 drops to 0 hit points"


@power(
    "m5058a1",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage(bonus=10, dtype=DamageType.NECROTIC, kind=MINION),
    trigger=_M5058_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M5058_FELLED),
)
def m5058a1(c: Cast) -> None:
    """It bursts as it falls.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. Declared `FREE` because the printed
    line is "No Action", which is nearer a free action than any immediate
    one.

    "A melee or a ranged attack drops the m5058" is only half declared:
    `Dropped` carries the creature and nothing about what felled it, so the
    trigger is the dropping and the rest is in the report. The burst catches
    everybody, which is what "creatures in the burst" prints.
    """
    if c.strike():
        c.hit()
        c.note("m5058a1: the target is exposed to the m5058's rot")
