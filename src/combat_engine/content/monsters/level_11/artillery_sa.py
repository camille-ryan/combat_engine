"""Monster abilities, level 11: the rest of the artillery.

`artillery.py` holds the blocks the first pass reached; this is the remainder,
in ref order. A stat block's numbers load from `game.db` -- hp, defences,
speed, scores, resistances -- and only behaviour is written here. Attack and
damage lines go in the header exactly as printed (`Attack(vs=AC, printed=18)`,
`Damage("3d6", 9)`) and the engine takes the level term back out.

Conventions kept from the levels below: a stat block printing no range at all
means melee 1; a printed "Range 5/10" is a normal range and a long one and
only the normal one is held; a standing modifier is a **trait**
(`action=NONE`, `target=NO_TARGET`) whatever the database's action column
says; a printed "(Immediate Interrupt)" is `action=INTERRUPT` for the same
reason; and a helper written for an earlier level is imported rather than
copied.

Seven things this file had to settle.

**Resistance against distance is a gated modifier, not a flat one.**
m115743a0 shrugs off ten points only from attacks that started five squares
off, and `Defences.resist` is a flat number per type with nowhere to hang a
condition. `c.resist(when=)` is the gated form, and the gate reads `source`
off the damage context -- which carries it, and `from_attack` beside it, so
"an attack" can be told from a zone's burn.

**"Secondary Attack" has no ref to live in**, so `_secondary` rolls the
printed total through `scaling.trim` the way a header's `Attack(printed=)` is
rolled. Four rows here print one.

**A hit line with no damage on it gets no `c.hit()` and no `damage=`.**
Six rows here print a condition, a curse or a lost healing surge as the whole
consequence; declaring a damage line for them would invent one.

**"-2 to all defenses (save ends)" is one hold carrying four modifiers.**
Written as four penalties it would be four saving throws against one printed
sentence, so `_all_defences_down` applies them together. The same reasoning
puts "slowed and ongoing 10 (save ends both)" on `c.condition(ongoing=)`.

**A printed recharge condition rides on top of the die.** The database files a
plain 6+ where the block prints "Recharge when ...", so `_recharge_on` adds
the sentence and the two only ever agree to bring the row back sooner.
m1829a2's condition -- "recharges when no creature is immobilized by this
power" -- is hung on the hold's own `on_end` rather than on `ConditionEnded`,
because `Effects.end` drops the effect from `live` before it announces
anything, so by `on_end` the remaining-victims question has a correct answer.

**An effect handed to somebody else is `c.transfer`.** m1153a4 moves one of
its own holds onto a target, and rebuilding it by hand would lose the
conditions, the burn and the saving throw still owed. The hold is picked by
label, because a label is something the decider can render and an `Effect` is
not.

**m4143a3 answers two events, not one.** "An enemy enters or leaves an
adjacent square" is `AdjacencyGained` and `AdjacencyLost`, and `on=` takes
both. Only the first carries `mover`, which is what keeps the entry half from
firing when the m4143 closes the gap itself; the exit half has no such field
and fires when either side walks off.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_10.controllers import EVERY_DEFENCE
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
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
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Ranged,
    Size,
    Square,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    both,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AdjacencyLost,
    AttackDeclared,
    DamageApplied,
    SurgeSpent,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, is_, squares, team
from combat_engine.engine.triggers import Trigger, about_me, by_melee, by_ranged

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _all_defences_down(c: Cast, victim: int, amount: int = 2) -> Effect | None:
    """"A -2 penalty to all defenses (save ends)" as one hold.

    Four separate penalties would be four saving throws against one printed
    sentence, so the modifiers ride a single effect. Untyped, because the card
    prints no type word in front of "penalty" and penalties have none.
    """
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[
            (victim, Mod(what=AC.value, value=-amount, kind="untyped", label=c.ref)),
            (victim, Mod(what=FORT.value, value=-amount, kind="untyped", label=c.ref)),
            (victim, Mod(what=REF.value, value=-amount, kind="untyped", label=c.ref)),
            (victim, Mod(what=WILL.value, value=-amount, kind="untyped", label=c.ref)),
        ],
    )


def _enemies_near(c: Cast, of: int, radius: int) -> list[int]:
    """The enemies a secondary attack centred on somebody else can reach.

    The creature the burst is centred on is left out: it has already been
    attacked by the primary line and "creatures in the burst" beside a
    primary target means the rest of them.
    """
    return sorted(
        foe
        for foe in c.enemies()
        if foe != of and alive(c.world, foe) and distance_between(c.world, of, foe) <= radius
    )


# ==========================================================================
# m1001
# ==========================================================================


@power(
    "m1001a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8"),
)
def m1001a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The die rolls untyped: the keyword is on the row and the printed
    damage line names no type."""
    if c.strike():
        c.hit()


@power(
    "m1001a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.POLYMORPH, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 6, dtype=DamageType.FORCE),
)
def m1001a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m1001a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.POLYMORPH],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d4", 6, kind=LIMITED),
)
def m1001a2(c: Cast) -> None:
    """No target line is printed, so the blast catches its own side too.

    Slowed and weakened share one duration and neither is save-ends, so one
    `c.condition` call carries both.
    """
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.EONT)


@power(
    "m1001a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d12", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1001a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m1153
# ==========================================================================


_M1153_FELLED = "the m1153 drops to 0 hit points"
_M1153_STRUCK = "the m1153 would be hit by an attack"


@power(
    "m1153a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6),
)
def m1153a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1153a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m1153a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1153a2",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.CHARM, Keyword.POLYMORPH],
    attack=Attack(vs=WILL, printed=13),
    trigger=_M1153_FELLED,
    on=Trigger(Dropped, about_me, _M1153_FELLED),
)
def m1153a2(c: Cast) -> None:
    """One last reach as it goes down. A creature may answer its own
    downfall; the dispatcher makes the exception for exactly this shape.

    `EACH_OTHER` rather than `EACH_CREATURE`: the burst is centred on the
    m1153 and a creature at 0 hit points cursing itself is not the printed
    reading.

    The hit line prints no damage, so there is no `damage=` and no
    `c.hit()` -- the whole consequence is the curse, and what the curse then
    does is not on this block.
    """
    if c.strike():
        c.curse(until=When.ENCOUNTER)


@power(
    "m1153a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.POLYMORPH],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m1153a3(c: Cast) -> None:
    """"Recharges when first bloodied" is the printed sentence on top of the
    die the database files. `_recharge_on` is the guarded form -- it refuses
    to arm a second watch for the same row, which matters on a blast whose
    body runs once per target."""
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.curse(until=When.ENCOUNTER)


@power(
    "m1153a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1153a4(c: Cast) -> None:
    """It gives one of its own problems away.

    `c.transfer` is the whole printed sentence: it ends the hold here and
    rebuilds it there with the conditions, the ongoing damage and the saving
    throw intact, and because it is rebuilt a fixed duration starts again on
    the new owner -- which is the card's second sentence.

    The hold is chosen by **label**, not by handing the decider an `Effect`:
    a label is something an interface can show. Holds carrying a relation or
    a subscription are left out, because `c.transfer` refuses those rather
    than move half of one.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mine = [
        eff
        for eff in c.world.effects.of(c.me)
        if not eff.ended and not eff.relations and not eff.subs
    ]
    labels = sorted({eff.label for eff in mine if eff.label})
    picked = c.choose(labels, f"{c.ref}: which effect moves") if labels else None
    if picked is None:
        return
    chosen = next((eff for eff in mine if eff.label == picked), None)
    c.transfer(chosen, to=victim)


@power(
    "m1153a5",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M1153_STRUCK,
    on=Trigger(Hit, targets_me, _M1153_STRUCK),
)
def m1153a5(c: Cast) -> None:
    """It is somewhere else, and shooting back.

    "Makes a m1153a1 attack" is that row run with `c.use_power`, so its
    printed numbers stay in its own header; `spend=False` because the shot is
    this row's cost and not m1153a1's own encounter use.
    """
    foe = _triggering_enemy(c)
    c.teleport(2)
    if foe is not None:
        c.use_power("m1153a1", on=foe, spend=False)


@power(
    "m1153a6",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1153a6(c: Cast) -> None:
    """Knowing where one particular creature is, anywhere. Nothing on a board
    turns on it: the thing sensed is not a combatant and no roll is made for
    it, so this is deliberately inert rather than given an invented
    mechanic."""
    c.note("m1153a6: it senses the distance and direction of one creature")


# ==========================================================================
# m115743
# ==========================================================================


@power(
    "m115743a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("resolve.ctx(from_attack=)",),
)
def m115743a0(c: Cast) -> None:
    """Ten points off anything thrown from a distance.

    A flat `Defences.resist` entry has nowhere to hang the distance, so the
    gated form is used: `c.resist(when=)` lays a modifier that
    `resolve.deal_damage` reads after the flat ones. The dealer comes off that
    gate's `source`, and the distance is measured where it stands when the
    blow lands, which is the only position anything records.

    "From **attacks**" is the dropped half. The gated-resist reader builds its
    own smaller context -- `source`, `power`, `dtype`, `dtypes`,
    `opportunity`, `charge` -- and `from_attack` is not in it, so asking for
    it is silently false and shrugs off nothing at all. Without it a burn or a
    tick of ongoing damage whose owner happens to be standing five squares off
    is resisted too, which is a little stronger than print.
    """
    me = c.me

    def from_afar(ctx: dict[str, Any]) -> bool:
        source = ctx.get("source")
        if source is None or source < 0 or source == me:
            return False
        return distance_between(c.world, source, me) >= 5

    c.resist(10, until=When.ENCOUNTER, on=me, when=from_afar)


@power(
    "m115743a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 8),
)
def m115743a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115743a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 9),
)
def m115743a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115743a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7, half_on_miss=True),
)
def m115743a3(c: Cast) -> None:
    """Harder in the middle than at the edge.

    Two printed damage lines for one attack, so the heavier one is rolled in
    the body -- the header carries the ordinary one, which is what the card
    shows first and what `cards.py` checks. `c.origin` is the square the
    burst was aimed at, and a Large creature standing across it counts as in
    it if any of its squares is the origin.

    `half_on_miss` is declared data and no line of the engine reads it, so
    the Miss branch is written out as well, for both numbers.
    """
    victim = c.target
    middle = (
        victim is not None and c.origin is not None and c.origin in squares(c.world, victim)
    )
    if c.strike():
        if middle:
            c.damage("2d6", 12)
        else:
            c.hit()
    elif middle:
        c.half_damage("2d6", 12)
    else:
        c.hit(half=True)


# ==========================================================================
# m1574
# ==========================================================================


_M1574_STRUCK = "the m1574 is hit by a melee or close attack"


def _hit_me_up_close(world: Any, me: int, ev: Any) -> bool:
    return bool(both(targets_me, by_melee)(world, me, ev))


@power(
    "m1574a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 4),
)
def m1574a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1574a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d12", 5, dtype=DamageType.NECROTIC),
    requires=lambda world, eid: not is_(world, eid, Condition.BLINDED),
    requires_text="it loses this power while blinded",
)
def m1574a1(c: Cast) -> None:
    """"Slowed and a -2 penalty to attack rolls (save ends both)" is one hold
    carrying both, which is the only way the victim gets one saving throw
    rather than two.

    The blindness clause is a `requires=` and is safe as one: this row costs
    a standard action, so the Requirement is read when the row is offered
    rather than once at the start of the fight the way a trait's would be.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.SLOWED,),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "m1574a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1574_STRUCK,
    on=Trigger(Hit, _hit_me_up_close, _M1574_STRUCK),
)
def m1574a2(c: Cast) -> None:
    """A step back and a swing at whoever got in.

    `by_melee` already counts close bursts and blasts, so the printed "melee
    or close attack" is the one predicate rather than two.

    Declared with no target: the row picks off the trigger, because the
    dispatcher's aim would point at whoever this reaction's own target line
    found. Either printed row is offered; both carry their own numbers.

    **Only the ones that reach are offered.** `m1574a0` is Melee 1 and
    `m1574a1` is Ranged 10, and `c.use_power(on=)` applies no reach check of
    its own -- so a close attack from five squares away was answered with a
    melee swing at five. The step is aimed at the attacker, then whichever
    rows can still touch it are the choice. This is the printed ranged
    alternative doing its job: out of melee reach the row takes `m1574a1`
    rather than refusing."""
    foe = _triggering_enemy(c)
    if foe is None:
        c.shift(1)
        return
    c.shift(1, toward=foe)
    offered = [
        ref for ref in ("m1574a0", "m1574a1") if c.distance(foe) <= c.reach(ref)
    ]
    if not offered:
        return
    pick = c.choose(offered, f"{c.ref}: which attack") or offered[0]
    c.use_power(pick, on=foe, spend=False)


# ==========================================================================
# m1829
# ==========================================================================


@power(
    "m1829a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 5),
)
def m1829a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1829a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m1829a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m1829a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(4),
    target=Target("enemy", 1, max_size=Size.MEDIUM),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 5, kind=LIMITED),
    dropped=("When.ESCAPE",),
)
def m1829a2(c: Cast) -> None:
    """Floored and tangled.

    "Medium or smaller creature only" is a size cap the target line really
    does hold, so it is declared rather than filtered in the body.

    Prone, unable to stand and immobilized are one hold: three separate ones
    would be three things to shake off where the card prints one. `PINNED` is
    what "cannot stand" is, which is what `c.prone(held=)` hangs on.

    "(until escape)" has no door -- `When` has no escape-tied member -- so
    the hold is laid indefinite instead. The printed recharge condition rides
    on the hold rather than on `ConditionEnded`: `Effects.end` drops the
    effect from `live` before it announces anything, so by `on_end` the
    question "is anybody still caught" has a correct answer.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    ref, me = c.ref, c.me
    held = c.world.effects.apply(
        victim,
        me,
        When.ENCOUNTER,
        label=ref,
        conditions=(Condition.PRONE, Condition.PINNED, Condition.IMMOBILIZED),
    )
    if held is None:
        return

    def freed() -> None:
        if not c.suffering(ref):
            c.restore_use(ref, on=me)

    held.on_end.append(freed)


@power(
    "m1829a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1829a3(c: Cast) -> None:
    """The waiver is laid first and only for this turn, because "for this
    move" is the move about to be made and nothing later."""
    c.ignores_difficult(until=When.EOT)
    c.shift(3)


@power(
    "m1829a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("resolve.prone_penalty",),
)
def m1829a4(c: Cast) -> None:
    """An extra die against whatever m1829a2 is holding down.

    A gated modifier rather than a hold put on and taken off as victims come
    and go: the gate is asked as the damage is dealt, which is the moment the
    printed sentence is measured. `c.suffering` names everyone carrying an
    effect this creature applied under that row's label.

    The waiver half is dropped. `conditions.Rules` gives prone `grants_ca`
    and an attack penalty of its own and nothing that penalises *shooting* a
    prone creature, so there is no penalty here to waive.
    """
    me = c.me

    def tangled(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in c.suffering("m1829a2")

    c.bonus(
        "damage", 0, dice="1d6", until=When.ENCOUNTER, on=me, kind="untyped", when=tangled
    )


@power(
    "m1829a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1829a5(c: Cast) -> None:
    """Ten more when two of its friends already have the victim busy.

    Melee only, so the gate asks the damage context's `ranged` -- read off
    the row's own range line, which is right for every row this creature has.
    The two neighbours are counted from the board rather than from the
    context, which carries nothing about who is standing where.
    """
    me = c.me

    def outnumbered(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or ctx.get("ranged", False):
            return False
        near = [
            friend
            for friend in c.within(1, of=victim, side="ally")
            if friend != me and alive(c.world, friend)
        ]
        return len(near) >= 2

    c.bonus("damage", 10, until=When.ENCOUNTER, on=me, kind="untyped", when=outnumbered)


# ==========================================================================
# m1941
# ==========================================================================


@power(
    "m1941a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m1941a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1941a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d6", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1941a1(c: Cast) -> None:
    """The second line spreads out from whoever the first one hit.

    The primary's trailing sentence is the secondary's setup and carries no
    mechanic of its own, so nothing is written for it.

    "Ongoing 5 psychic and dazed (save ends both)" is one hold, which
    `c.condition(ongoing=)` is for -- two calls would be two saving throws.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    for foe in _enemies_near(c, victim, 3):
        if _secondary(c, 14, WILL, foe):
            c.condition(
                Condition.DAZED,
                until=When.SAVE_ENDS,
                on=foe,
                ongoing=(5, DamageType.PSYCHIC),
            )


@power(
    "m1941a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
)
def m1941a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2601
# ==========================================================================


_M2601_FELLED = "the m2601 drops to 0 hit points"


@power(
    "m2601a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m2601a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2601a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d6", 5),
)
def m2601a1(c: Cast) -> None:
    """"Slowed and ongoing 10 (save ends both)" is one hold."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED)
        )


@power(
    "m2601a2",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=16),
    trigger=_M2601_FELLED,
    on=Trigger(Dropped, about_me, _M2601_FELLED),
)
def m2601a2(c: Cast) -> None:
    """It comes apart, and the sight of it is the attack. No damage is
    printed on the hit line, so there is no `damage=` and no `c.hit()`."""
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2601a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2601a3(c: Cast) -> None:
    """Two gated penalties rather than two holds put on when it is hurt and
    taken off if it is healed past the line: the gate is asked when the
    defence is read, which is the moment the printed "while bloodied" is
    measured. Penalties carry no type, which is why neither names one."""
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=me)

    c.penalty(AC, 2, until=When.ENCOUNTER, on=me, when=hurt)
    c.penalty(FORT, 2, until=When.ENCOUNTER, on=me, when=hurt)


# ==========================================================================
# m3579
# ==========================================================================


@power(
    "m3579a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 5),
)
def m3579a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3579a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
)
def m3579a1(c: Cast) -> None:
    """"Until the end of its next turn" is the *target's* clock, which is
    `When.EOTNT` and not `EONT`."""
    if c.strike():
        c.hit()
        c.weakened(until=When.EOTNT)


@power(
    "m3579a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(0, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE, Keyword.AREA, Keyword.ZONE],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("1d6", 7, dtype=DamageType.FORCE),
)
def m3579a2(c: Cast) -> None:
    """A single square that then stays dangerous.

    "1 square within 10" is an area burst of nothing, which is what
    `AreaBurst(0, 10)` measures, and `c.area()` is the square itself.

    `c.hazard` is the whole of the lingering sentence -- entering, starting a
    turn there, and the once-per-turn latch -- and it is laid under `c.first`
    so one use makes one zone rather than one per creature caught. No sustain:
    the printed duration is a turn.
    """
    if c.first:
        c.hazard(
            c.area(),
            3,
            DamageType.FORCE,
            label=c.ref,
            until=When.EONT,
            sustain=None,
        )
    if c.strike():
        c.hit()


@power(
    "m3579a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3579a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "m3579a4",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    once_per_round=True,
)
def m3579a4(c: Cast) -> None:
    """"1/round" on an at-will row is `once_per_round`, which the action menu
    reads; it is not a usage."""
    c.shift(2)


# ==========================================================================
# m3591
# ==========================================================================


@power(
    "m3591a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 7),
)
def m3591a0(c: Cast) -> None:
    """The printed damage is untyped and only the burn is poison, so the
    header carries no damage type."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)


@power(
    "m3591a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 10, dtype=DamageType.PSYCHIC),
)
def m3591a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _all_defences_down(c, victim)


@power(
    "m3591a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3591a2(c: Cast) -> None:
    """Come closer or it hurts.

    Measured at the end of the victim's next turn against where it was
    standing when the blow landed, which is what "must move at least 2
    squares closer ... before the end of its next turn" compares. The watch
    is hung on the m3591 and spent by the turn it waits for.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    was = distance_between(c.world, me, victim)

    def measured(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if distance_between(c.world, me, victim) > was - 2:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(TurnEnd, measured, until=When.EOTNT, on=me, once=True, label=f"{c.ref} closer")


@power(
    "m3591a3",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True),
    keywords=[Keyword.CLOSE],
)
def m3591a3(c: Cast) -> None:
    """Goaded: easier to hit and hitting harder.

    "Allies that are not the m3591" is the `other_ally` pool, which excludes
    the caster -- `EACH_ALLY`'s does not, and the card says otherwise.

    The duration is the m3591's own next turn, which is what `When.EONT`
    clocks. The bonus prints no type word, so it is untyped.
    """
    for defence in EVERY_DEFENCE:
        c.penalty(defence, 2, until=When.EONT)
    c.bonus("attack", 2, until=When.EONT)


# ==========================================================================
# m4143
# ==========================================================================


_M4143_ADJACENCY = "an enemy enters or leaves a square adjacent to the m4143"
_M4143_BLED = "the m4143 is first bloodied"


def _enemy_stepped_in(world: Any, me: int, ev: Any) -> bool:
    """The entry half. `AdjacencyGained` carries `mover`, which is what keeps
    this from firing when the m4143 closes the gap itself."""
    other = getattr(ev, "other", None)
    if getattr(ev, "actor", None) != me or other is None:
        return False
    if getattr(ev, "mover", 0) != other:
        return False
    return team(world, other) is not team(world, me)


def _enemy_stepped_out(world: Any, me: int, ev: Any) -> bool:
    """The exit half. `AdjacencyLost` carries `mover` now (#368), so this
    fires only when the *enemy* walked off and not when the creature did --
    which is the printed sentence and was the hole recorded here before."""
    other = getattr(ev, "other", None)
    if getattr(ev, "actor", None) != me or other is None:
        return False
    if getattr(ev, "mover", 0) != other:
        return False
    return team(world, other) is not team(world, me)


@power(
    "m4143a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 5),
)
def m4143a0(c: Cast) -> None:
    """"1d10+5 damage plus 1d6 fire damage" is two rolls of two types, not one
    roll of both: the header's untyped line and a typed rider that meets the
    target's fire resistance on its own."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m4143a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m4143a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4143a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4143a2(c: Cast) -> None:
    """Two of one or one of the other, then a step.

    Declared with no target: each borrowed row picks its own, which is what
    `c.use_power` with no `on=` does, and the choice between the two is the
    m4143's. `spend=False` because the standard action is this row's.
    """
    pick = c.choose(["m4143a1", "m4143a0"], f"{c.ref}: two of one or one of the other")
    if pick == "m4143a0":
        c.use_power("m4143a0", spend=False)
    else:
        for _ in range(2):
            c.use_power("m4143a1", spend=False)
    c.shift(1)


@power(
    "m4143a3",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d10", 5),
    trigger=_M4143_ADJACENCY,
    on=(
        Trigger(AdjacencyGained, _enemy_stepped_in, _M4143_ADJACENCY),
        Trigger(AdjacencyLost, _enemy_stepped_out, _M4143_ADJACENCY),
    ),
)
def m4143a3(c: Cast) -> None:
    """Both halves of "enters or leaves" are declared; declaring one would
    look finished and be half a row.

    The enemy is read off the event's `other`, not off `attacker` or `actor`:
    an adjacency event is mirrored and names the m4143 in `actor`.
    """
    ev = c.trigger
    foe = getattr(ev, "other", None) if ev is not None else None
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)
    c.shift(2)


@power(
    "m4143a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d8", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m4143a4(c: Cast) -> None:
    """`half_on_miss` is declared data nothing in the engine reads, so the
    Miss branch is written out."""
    if c.strike():
        c.hit()
        c.push(3)
    else:
        c.hit(half=True)


@power(
    "m4143a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4143_BLED,
    on=Trigger(Bloodied, about_me, _M4143_BLED),
)
def m4143a5(c: Cast) -> None:
    """The breath comes back and is spent at once.

    `c.restore_use` first and then an ordinary `c.use_power` that *does*
    spend: the card recharges the row and then uses it, so the use it just
    got back is the one that goes.

    "If it is flying" is asked as being off the ground, which is the only
    thing recorded about height. The shift is up to 5, and `c.shift` offers
    everything within that.
    """
    c.restore_use("m4143a4", on=c.me)
    if c.height(on=c.me) > 0:
        c.shift(5)
    c.use_power("m4143a4")


@power(
    "m4143a6",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m4143a6(c: Cast) -> None:
    """The splash is an Effect line, so it lands whether or not the shot
    does -- which is why it sits outside the `c.strike` branch. "Each
    creature adjacent to the target" names no side, so its own allies burn
    too."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    for near in sorted(c.within(1, of=victim, side="any")):
        if near != victim and alive(c.world, near):
            c.damage("2d6", dtype=DamageType.FIRE, on=near)


@power(
    "m4143a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=16),
)
def m4143a7(c: Cast) -> None:
    """No damage is printed on the hit line, so there is no `damage=` and no
    `c.hit()` -- the stun is the whole consequence.

    The Aftereffect is dropped. An aftereffect is a second hold that lands
    when the first one *ends*, which nothing expresses: laying the penalty
    now would run the two durations together and give one saving throw where
    the card charges two.
    """
    if c.strike():
        victim = c.target
        held = c.stunned(until=When.EONT)
        c.aftereffect(held, lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))

# ==========================================================================
# m4482 -- a minion. Its single hit point is in the database and
# `kind=MINION` is what says the damage number is flat because the creature
# is one, which is how it rescales.
# ==========================================================================


@power(
    "m4482a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=5, kind=MINION),
)
def m4482a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4482a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=8, kind=MINION),
)
def m4482a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m4482a2",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4482a2(c: Cast) -> None:
    """It circles whoever it is already next to.

    Not a plain `c.shift(1)`: that offers every square within one and the
    printed line offers exactly the ones still adjacent to that enemy --
    which, round a Medium creature, includes squares two steps away. So the
    destinations are filtered out of `reachable_squares` and `c.shift(to=)`
    names the one chosen.

    Adjacency is measured against every square the enemy stands in, so a
    Large one is circled correctly.
    """
    me = c.me
    beside = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    foe = c.choose(beside, f"{c.ref}: which enemy to circle") if beside else None
    if foe is None:
        return
    theirs = squares(c.world, foe)
    here = c.here

    def still_beside(sq: Square) -> bool:
        return any(max(abs(sq[0] - t[0]), abs(sq[1] - t[1])) == 1 for t in theirs)

    options = sorted(
        sq for sq in c.world.reachable_squares(me, 2) if sq != here and still_beside(sq)
    )
    if not options:
        return
    dest = c.choose(options, f"{c.ref}: which square")
    if dest is not None:
        c.shift(to=dest)


# ==========================================================================
# m5161
# ==========================================================================


_M5161_FELLED = "the m5161 drops to 0 hit points"
_M5161_SCORCHED = "the m5161 takes acid, cold, fire, lightning or thunder damage"
_M5161_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _elemental_blow(world: Any, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return any(kind in _M5161_ELEMENTS for kind in ev.types())


@power(
    "m5161a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m5161a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5161a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 8),
)
def m5161a1(c: Cast) -> None:
    """The second line is a burst centred on whoever the first one hit, and
    catches one creature out of it -- so it is offered as a choice rather
    than swept across everybody in range."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _all_defences_down(c, victim)
    near = _enemies_near(c, victim, 2)
    caught = c.choose(near, f"{c.ref}: who else is caught") if near else None
    if caught is None:
        return
    if _secondary(c, 16, REF, caught):
        c.damage("2d6", 3, on=caught)
        _all_defences_down(c, caught)


@power(
    "m5161a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=16),
)
def m5161a2(c: Cast) -> None:
    """The hit line prints no damage of its own, only a burn and a hold, so
    there is no `damage=` and no `c.hit()`. The two ride one effect, which is
    what "(save ends both)" means.

    The printed range line gives a burst size and no "within", which every
    other area row of this kind prints as 10; that is what is declared.
    """
    if c.strike():
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED)
        )


@power(
    "m5161a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    trigger=_M5161_FELLED,
    on=Trigger(Dropped, about_me, _M5161_FELLED),
)
def m5161a3(c: Cast) -> None:
    """A creature may answer its own downfall; the dispatcher makes the
    exception for exactly this shape. Ongoing damage is the whole hit line,
    so no `damage=` and no `c.hit()`."""
    if c.strike():
        c.ongoing(10, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "m5161a4",
    level=11,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5161_SCORCHED,
    on=Trigger(DamageApplied, _elemental_blow, _M5161_SCORCHED),
)
def m5161a4(c: Cast) -> None:
    """It learns from whatever just burned it.

    "2/Encounter" is `uses=2` on an encounter row. The resistance is laid
    with no gate, so it goes into `Defences.resist` and comes back off when
    the hold ends; "or until it uses m5161a4 again" is that hold being ended
    by hand before the new one is laid, which is also what keeps the printed
    rule that resistances of one type do not stack from mattering here.

    The type is read off the blow rather than chosen: a blow of several types
    pays out for the first of them the card names.
    """
    ev = c.trigger
    if ev is None:
        return
    kind = next((k for k in ev.types() if k in _M5161_ELEMENTS), None)
    if kind is None:
        return
    label = f"{c.ref} resist"
    for standing in list(c.world.effects.of(c.me)):
        if standing.label == label and not standing.ended:
            c.world.effects.end(standing, "a different element now")
    c.resist(10, kind, until=When.ENCOUNTER, on=c.me)


# ==========================================================================
# m5517
# ==========================================================================


@power(
    "m5517a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 4),
)
def m5517a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5517a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d6", 5, dtype=DamageType.NECROTIC),
)
def m5517a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5517a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 10, dtype=DamageType.FORCE),
)
def m5517a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5517a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5517a3(c: Cast) -> None:
    """Shoved, and shoved again every turn until it shakes it off.

    The repeat is hung on the save-ends hold's own `subs` rather than written
    as a second watch: two effects would be two saving throws against one
    printed sentence, and ending the hold has to take the shoving with it.

    "The m5517 *can* push" is optional, so it is asked as a choice, and it is
    the m5517's choice rather than the victim's.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(3)
    hold = c.effect(f"{c.ref} shove", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def again(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim or hold.ended:
            return
        if c.may("shove it again", who=c.me):
            c.push(3, on=victim)

    hold.subs.append(c.world.bus.on(TurnStart, again, owner=c.me))


@power(
    "m5517a4",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(15),
    target=ONE_CREATURE,
)
def m5517a4(c: Cast) -> None:
    """Whatever it hurts, one creature elsewhere feels as well.

    `DamageApplied` is the right event: it carries what actually came off hit
    points, which is what "an equal amount" means after resistance. `detail`
    is what dealt it, which is what `by_melee` and `by_ranged` read to answer
    the printed "with a melee or a ranged attack".

    The echo cannot feed itself: the blow it deals names the cursed creature
    as its target, and that is the one case the watch skips.
    """
    victim = c.target
    if victim is None:
        return
    me = c.me
    c.curse(on=victim, until=When.ENCOUNTER)

    def echo(ev: DamageApplied) -> None:
        if ev.source != me or ev.target == victim or ev.amount <= 0:
            return
        if not (by_melee(c.world, me, ev) or by_ranged(c.world, me, ev)):
            return
        c.flat(ev.amount, on=victim)

    c.watch(DamageApplied, echo, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5765
# ==========================================================================


_M5765_SURGED = "an enemy within 10 squares of the m5765 spends a healing surge"


def _enemy_surged_nearby(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "m5765a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m5765a0(c: Cast) -> None:
    """Standing in it for a whole turn costs five.

    The ring is a real aura so the UI can draw it and `occupants` can be
    diffed; the toll is a `TurnEnd` watch asking membership at the moment the
    turn ends, which is when the printed sentence is measured rather than
    when anybody walked in.
    """
    me = c.me
    ring = c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(ev: TurnEnd) -> None:
        who = ev.actor
        if ev.ghost or who == me or who not in c.enemies():
            return
        if who in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.NECROTIC, on=who)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5765a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=UpTo(2),
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("4d6", 5, dtype=DamageType.FIRE),
)
def m5765a1(c: Cast) -> None:
    """"One or two creatures" is `UpTo(2)`, and the body runs once per
    target."""
    if c.strike():
        c.hit()


@power(
    "m5765a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE),
)
def m5765a2(c: Cast) -> None:
    """"Can push" is optional, so it is asked rather than assumed."""
    if c.strike():
        c.hit()
        if c.may("shove it back", who=c.me):
            c.push(1)


@power(
    "m5765a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=14),
    trigger=_M5765_SURGED,
    on=Trigger(SurgeSpent, _enemy_surged_nearby, _M5765_SURGED),
)
def m5765a3(c: Cast) -> None:
    """It takes the next one out of their pocket.

    Declared with no target: the burst's victim is the triggering enemy and
    nobody else, so aiming it from the event is correct where the
    dispatcher's own pick would not be.

    "Loses a healing surge" is `c.spend_surge`, which takes one and gives
    nothing back for it -- the printed sentence exactly. The temporary hit
    points are the *target's* surge value, so it is read before the surge
    goes rather than after.

    No damage is printed on the hit line, so there is no `damage=` and no
    `c.hit()`.
    """
    foe = _triggering_enemy(c)
    if foe is None or not c.strike(on=foe):
        return
    worth = c.surge_value(of=foe)
    if c.spend_surge(on=foe):
        c.temp_hp(worth, on=c.me)


# ==========================================================================
# m5966
# ==========================================================================


@power(
    "m5966a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 8, dtype=DamageType.FIRE),
)
def m5966a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5966a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.FIRE, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 5, dtype=DamageType.FIRE),
)
def m5966a1(c: Cast) -> None:
    """The splash is on the hit line, so it only lands when the shot does, and
    it names one creature rather than everybody in reach -- so it is
    offered as a choice. No side is named, so an ally beside the target is a
    legal pick."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    beside = sorted(
        other
        for other in c.within(1, of=victim, side="any")
        if other != victim and alive(c.world, other)
    )
    caught = c.choose(beside, f"{c.ref}: who else is singed") if beside else None
    if caught is not None:
        c.damage("1d6", dtype=DamageType.FIRE, on=caught)


# ==========================================================================
# m899
# ==========================================================================


_M899_AIMED_AT = "the m899 is targeted by an attack"


@power(
    "m899a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8),
)
def m899a0(c: Cast) -> None:
    """The printed "crit +2d6" is a rolled rider, so it is added with
    `c.flat(c.roll(...))`: `c.damage` maxes its dice on a critical, which
    would turn an extra roll into an extra 12."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("2d6"))


@power(
    "m899a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d4", 9, dtype=DamageType.FORCE),
)
def m899a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m899a2",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=MeleeOrRanged(1, 20),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=16),
    trigger=_M899_AIMED_AT,
    on=Trigger(AttackDeclared, targets_me, _M899_AIMED_AT),
)
def m899a2(c: Cast) -> None:
    """It is not there after all.

    `AttackDeclared` rather than `Hit`: the printed trigger is being *aimed
    at*, which is announced before the roll. The blow is not cancelled -- the
    card does not say so -- the m899 is simply unseeable afterwards.

    "Invisible to the attacker" is one-sided, which is what `to=` is for; the
    duration is the printed save-ends rather than `c.invisible`'s default.
    """
    foe = _triggering_enemy(c)
    if foe is None or not c.strike(on=foe):
        return
    c.invisible(to=foe, on=c.me, until=When.SAVE_ENDS)


@power(
    "m899a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("1d6", 9),
)
def m899a3(c: Cast) -> None:
    """The keyword is cold and the printed damage line names no type, so the
    header carries none."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m899a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d6", 9, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m899a4(c: Cast) -> None:
    """It jumps to two more whether or not the first shot landed, which is why
    the secondaries sit outside the `c.strike` branch."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    for extra in _enemies_near(c, victim, 10)[:2]:
        if _secondary(c, 16, REF, extra):
            c.damage("1d6", 9, dtype=DamageType.LIGHTNING, on=extra)


@power(
    "m899a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.AREA,
        Keyword.IMPLEMENT,
        Keyword.LIGHTNING,
    ],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d6", 9, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m899a5(c: Cast) -> None:
    if c.strike():
        c.hit()
