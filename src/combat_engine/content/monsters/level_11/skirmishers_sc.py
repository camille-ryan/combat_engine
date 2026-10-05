"""Monster abilities, level 11, skirmishers: the twenty-two stat blocks the
first two files of this level left.

Numbers load from `game.db`. The attack line is written exactly as printed --
`Attack(vs=AC, printed=16)` -- and the damage line goes in the header as data,
so the engine can take the level back out and rescale a blow to another
edition's maths.

The conventions of the eleven levels below are kept:

* a **trait** costs no action, has no target and arms the watches that hold
  it for the rest of the fight, whatever the compendium's action column says;
* a card with no printed range at all is melee 1, and a printed band like
  "5/10" takes the short number;
* a close burst or blast naming no target set takes **enemies**; one that
  prints "creatures in the blast" takes creatures;
* a row that moves *and* swings takes the swing first where anything is
  already in reach, because the movement picks its own destination and one
  taken first can leave the target behind -- except where closing the
  distance is the whole point of the printed line, which is said in the row.

Seven things this file had to settle.

**A printed critical line is the extra dice, not the total.** "2d8 + 4
damage (crit 1d8 + 20)" is the maximum of the ordinary line -- 20, which
`c.damage` already deals on a critical -- plus 1d8 rolled on top. The header
keeps the ordinary line and the body adds the difference through
`c.flat(c.roll(...))`, because rolling it through `c.damage` would maximise
that too and a critical would come out flat. m255a0 settled this in the file
beside this one.

**A shift through bodies is not a walk.** Five rows here print "shifts N
squares and can move through enemies' spaces", and `c.overrun` reads the legs
and always walks. So the destination is picked with `_trample_to` and
`movement.overrun` is called with the kind the card prints. It reports each
creature entered exactly once, which is also the printed "cannot attack a
target more than once in this fashion".

**An aura that grows cannot be resized.** `Zone.aura` is the radius and
`Zones.refresh` recomputes the footprint from it, but nothing widens a live
one -- so m6656a5 dispels the aura and lays a fresh one two squares wider
under the *same label*, which is what the trait's watch reads it by. The
radius is read back off the zone, so the two recharge sentences ("smaller
than 5", "is 5") have a number to ask about.

**An interrupt that raises a defence belongs on `AttackRolled`.** The die is
down but the defence is read again once the window closes, so m4160a8's +4
can still turn the blow aside; `would_hit_me` is the printed "when it is
hit". On `Hit` the comparison has already been made and only the damage is
left to change.

**An Aftereffect is `on_end`.** It begins when the first hold goes, whichever
way it goes, which is what the printed word means. `escalate` is the other
sentence -- "each failed saving throw" -- and neither is the other.

**One at a time.** m1104a4 dominates one creature and m1162a3 restrains one,
and both cards say so. `_release_earlier` ends this row's own earlier hold
rather than refusing the new use, because the printed sentence is about which
creature is held.

**Two briefs arrived malformed and are reported rather than guessed.**
m1162a1 and m2096a1 each print an attack line with no defence at all
("+14 vs ; 4d8+5 damage.") in front of an Effect line that names the attacks
it really makes; the Effect line is what is written and the orphan line is
dropped as extraction noise. m6656a2 prints "+16 vs. Reflex and AC", which
`Attack` cannot say; the first defence is taken.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.skirmishers import _trample_to
from combat_engine.content.monsters.level_05.skirmishers_sa import _edge_on_target
from combat_engine.content.monsters.level_06.controllers import _all_defences
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.soldiers import (
    _recharge_on,
    _until_that_blow_lands,
)
from combat_engine.content.monsters.level_08.brutes import _melee_ctx
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_11.skirmishers import (
    _has_the_drop,
    _release_earlier,
)
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
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
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
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    Position,
    PowerUsed,
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
    by_me,
    by_melee,
    distance,
    leaves_me_out,
    power,
    targets_me,
    use,
    would_hit_me,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.movement import overrun
from combat_engine.engine.query import (
    alive,
    distance_between,
    is_,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both
from combat_engine.engine.zones import Zone

# ==========================================================================
# Shared shapes
# ==========================================================================

#: Which reaches the engine calls melee, ranged and close, for the rows that
#: gate on one. The words are `Range.kind`'s, not the card's.
_CLOSE_KINDS = ("close_burst", "close_blast")


def _foe_within(c: Cast, reach: int, ref: str) -> int | None:
    """Somebody in reach to swing at, for a row that attacks more than once.

    `_adjacent_foe` asks for one square and half the rows here reach two or
    three, so the distance is a parameter rather than adjacency.
    """
    near = sorted(foe for foe in c.enemies() if c.distance(foe) <= reach)
    return c.choose(near, f"{ref}: which enemy") if near else None


def _through_them(c: Cast, squares_: int, *, kind: str = "walk") -> list[int]:
    """Cover `squares_` squares straight through whoever is in the way.

    `c.overrun` takes no distance and no kind -- it reads the legs and walks.
    Five cards here print a *shift* of a stated length through enemies'
    spaces, so the destination is picked the way a trample's is and
    `movement.overrun` is called with the printed kind. Each creature entered
    is reported once and in order, which is the printed "cannot attack a
    target more than once in this fashion", and the shuffle into a free
    square at the end is the printed "must end its movement in an unoccupied
    square".
    """
    dest = _trample_to(c, squares_)
    if dest is None:
        return []
    return overrun(c.world, c.me, dest, kind=kind)


def _con_bonus_of(c: Cast, who: int) -> int:
    """That creature's own Constitution modifier.

    `c.con_mod` is the caster's and nothing on `Cast` asks another
    creature's, so `Stats` is read directly -- it is where the number lives
    and `c.mod` is the same call against `self.me`.
    """
    stats = c.world.get(who, Stats)
    return stats.mod(Ability.CON) if stats is not None else 0


def _by_melee_or_close(world: World, me: int, ev: Any) -> bool:
    """"When hit by a melee or close attack." The reach is on the row that
    swung, which the attack events carry as `power`; `by_melee` answers only
    half of it and there is no predicate for the other half."""
    if getattr(ev, "target", None) != me:
        return False
    row = get(str(getattr(ev, "power", "") or ""))
    return row is not None and row.reach_of(0).kind in ("melee", *_CLOSE_KINDS)


def _burned_me(world: World, me: int, ev: DamageRolled | DamageApplied) -> bool:
    """"When it takes fire damage." `DamageApplied` names its subject
    `target`, so `about_me` -- which reads `actor` and only `actor` -- is
    false here forever."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) is DamageType.FIRE
    )


def _guard_against(c: Cast, value: int, who: int) -> list[Effect]:
    """`value` more on every defence, against one creature's blow only.

    Four bonuses rather than one effect carrying four mods, because the gate
    is per-attacker and `c.bonus` is the only public way to carry one. None
    of them is save-ends, so the four-saving-throws objection that
    `_all_defences` exists for does not arise.
    """
    held: list[Effect] = []
    for which in (AC, FORT, REF, WILL):
        eff = c.bonus(
            which,
            value,
            until=When.EOT,
            on=c.me,
            when=lambda ctx, w=who: ctx.get("attacker") == w,
        )
        if eff is not None:
            held.append(eff)
    return held


def _marked_by_me(world: World, me: int, who: int | None) -> bool:
    """Is that creature carrying *my* mark? `query` has no such function and
    `c.is_(Condition.MARKED)` is true of anybody's."""
    if who is None:
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who)


# ==========================================================================
# m1002
# ==========================================================================


@power(
    "m1002a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d4", 6, dtype=DamageType.FORCE),
)
def m1002a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FORCE)


@power(
    "m1002a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d4", 6, dtype=DamageType.FORCE),
)
def m1002a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FORCE)


@power(
    "m1002a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FORCE, Keyword.POLYMORPH],
)
def m1002a2(c: Cast) -> None:
    """A shape it keeps by spending a standard action on it, and a toll on
    anybody it walks through while it is in it.

    `c.form` carries no sustain of its own, so the hold that does is a
    `c.effect` and the two halves of the shape hang on the same clock. The
    swing is armed off `Moved` rather than taken here: the shape is standing
    and the walking is done on later turns, which is a different moment from
    the one that lays it. The set of creatures already struck is cleared at
    the start of each move, because "in this fashion" is about one pass.

    Who was in the square is asked of positions rather than of the grid: a
    creature standing in an enemy's space is the square's occupant by then,
    which would hide the enemy from `c.in_squares`.
    """
    me = c.me
    hold = c.effect(c.ref, until=When.SUSTAIN, on=me, sustain=STANDARD)
    c.insubstantial(until=When.SUSTAIN, on=me)
    c.phasing(until=When.SUSTAIN, on=me)
    struck: set[int] = set()

    def began(ev: MoveStart) -> None:
        if ev.actor == me:
            struck.clear()

    def through(ev: Moved) -> None:
        if ev.actor != me or hold is None or hold.ended:
            return
        for who in sorted(foe for foe in c.enemies() if c.distance(foe) == 0):
            if who not in struck:
                struck.add(who)
                c.basic(on=who)

    c.watch(MoveStart, began, until=When.SUSTAIN, on=me, label=f"{c.ref} pass")
    c.watch(Moved, through, until=When.SUSTAIN, on=me, label=c.ref)


@power(
    "m1002a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m1002a3(c: Cast) -> None:
    """The parenthetical narrowing is a creature type, which `c.is_kind`
    asks of the database's own type words -- so it pays out for a creature
    that is one and is quietly false for one that is not, which is the
    printed line. The temporary hit points are rolled; the engine has no
    notion of what they look like."""
    friend = c.target
    if friend is None:
        return
    extra = (
        _con_bonus_of(c, friend)
        if c.is_kind("spellscarred", on=friend) or c.is_kind("plaguechanged", on=friend)
        else 0
    )
    c.heal(11 + extra, on=friend)
    c.temp_hp(c.roll("1d6"), on=friend)


@power(
    "m1002a4",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1002a4(c: Cast) -> None:
    """"Until the end of this movement" is not a duration the engine has, so
    both halves are lent for the step and taken back afterwards -- the
    arrangement `_flies` uses one file over."""
    me = c.me
    ghost = c.phasing(until=When.EOT, on=me)
    thin = c.insubstantial(until=When.EOT, on=me)
    try:
        c.shift(2)
    finally:
        for lent in (ghost, thin):
            if lent is not None:
                c.world.effects.end(lent, "the step is over")


# ==========================================================================
# m1104
# ==========================================================================


@power(
    "m1104a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 8),
)
def m1104a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1104a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 10),
)
def m1104a1(c: Cast) -> None:
    """Here the movement comes first, against the file's usual order: closing
    two squares is the whole of what this row adds to the basic attack beside
    it, and a swing taken first would be a swing at whoever was already in
    reach. Declared with no target for the same reason -- a target list is
    chosen before the body runs, and the creature it ends up beside is often
    not the nearest one now."""
    c.move(2)
    victim = _adjacent_foe(c, c.ref)
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m1104a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 10, kind=LIMITED),
)
def m1104a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.penalty(AC, 3, until=When.EONT)
    c.penalty(REF, 3, until=When.EONT)


@power(
    "m1104a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d12", 8, kind=LIMITED),
    requires=_has_the_drop,
    requires_text="the m1104 must have combat advantage against an adjacent enemy",
)
def m1104a3(c: Cast) -> None:
    """The printed recharge sentence sits on top of the die the database
    files, and the two only ever agree to give the row back sooner. It is
    about *an adjacent creature* crossing its own half-way line, so the
    distance is measured on the `Bloodied` rather than taken now."""
    me = c.me
    _recharge_on(
        c,
        Bloodied,
        lambda ev: ev.actor != me and distance_between(c.world, me, ev.actor) <= 1,
    )
    if not c.strike():
        return
    c.hit()
    c.weakened(until=When.SAVE_ENDS)
    c.heal(46, on=me)


@power(
    "m1104a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
)
def m1104a4(c: Cast) -> None:
    """One creature held at a time, so the earlier hold goes first. The
    Aftereffect hangs on `on_end`, which fires whichever way the domination
    ends -- a save, a cure, the end of the fight -- and is what the printed
    word means. `escalate` would be the other sentence, "each failed saving
    throw", which this card does not print."""
    victim = c.target
    if victim is None or not c.strike():
        return
    _release_earlier(c, c.ref)
    held = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, save_mod=-2)
    if held is not None:
        held.on_end.append(lambda: c.dazed(until=When.SAVE_ENDS, on=victim))


@power(
    "m1104a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1104a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Held as a damage
    modifier gated at damage time, so the question is asked of the creature
    the blow is landing on rather than of whoever this row started with."""
    c.bonus(
        "damage",
        0,
        dice="3d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=_edge_on_target(c),
    )


@power(
    "m1104a6",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1104a6(c: Cast) -> None:
    """An hour is the rest of the fight. The bar on attacking is a separate
    hold, because `c.form` carries conditions and movement modes and nothing
    else -- so it is hung on the form's ending, which is the printed "or end
    the effect as a minor action"."""
    me = c.me
    shape = c.form(
        conditions=(Condition.INSUBSTANTIAL,),
        modes={"fly": 12},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    barred = c.cannot_attack(on=me, until=When.ENCOUNTER)
    if barred is not None:
        shape.on_end.append(
            lambda: c.world.effects.end(barred, "the shape is dropped")
        )


@power(
    "m1104a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m1104a7(c: Cast) -> None:
    """`c.spend_surge` plus the printed number, not `c.surge`: the card says
    what the surge is worth here and a quarter of maximum is a different
    figure. A monster carries one surge per tier so that a line like this has
    something to spend."""
    me = c.me
    c.spend_surge(on=me)
    c.heal(46, on=me)
    _all_defences(c, 2, until=When.SONT, on=me)


# ==========================================================================
# m1162
# ==========================================================================


@power(
    "m1162a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 7),
)
def m1162a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1162a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m1162a1(c: Cast) -> None:
    """Both swings, each picking its own target.

    The brief prints an orphan attack line with no defence in front of the
    Effect line; the Effect line is what the row does and the orphan is
    extraction noise -- see the report. The printed row is used rather than
    copied, so its numbers stay in one place.
    """
    for _ in range(2):
        use(c.world, c.me, "m1162a0", spend=False)


_M1162_BLED = "the m1162 is first bloodied"


@power(
    "m1162a2",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M1162_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M1162_BLED),
)
def m1162a2(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else."""
    for _ in range(2):
        use(c.world, c.me, "m1162a0", spend=False)


@power(
    "m1162a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
)
def m1162a3(c: Cast) -> None:
    """No damage line at all: the printed hit is the hold. One creature at a
    time, so the earlier hold is ended rather than this use refused -- the
    sentence is about which creature is held."""
    if not c.strike():
        return
    _release_earlier(c, c.ref)
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1162a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1162a4(c: Cast) -> None:
    c.shift(1)


_M1162_SWUNG_AT = "a melee attack is made against the m1162"


@power(
    "m1162a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1162_SWUNG_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M1162_SWUNG_AT),
)
def m1162a5(c: Cast) -> None:
    """`AttackDeclared` is announced before the die, which is the whole of an
    interrupt that steps out of reach. The printed recharge is a sentence on
    top of the die the database files."""
    me = c.me
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m1162a2"
    )
    c.shift(1)


# ==========================================================================
# m1575
# ==========================================================================


def _not_blinded(world: World, eid: int) -> bool:
    """The printed "it loses this power while blinded"."""
    return not is_(world, eid, Condition.BLINDED)


@power(
    "m1575a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m1575a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1575a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
    requires=_not_blinded,
    requires_text="the m1575 must not be blinded",
)
def m1575a1(c: Cast) -> None:
    """A blast naming no target set takes enemies. The Requirement is a fact
    that can change inside a fight, but this is an ordinary standard action
    and not a trait -- `usable` asks it each time the row is offered, which
    is the printed line."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m1575a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1575a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Two gates, because the
    card prints two: the blow has to be a melee one, which `_melee_ctx` reads
    off the row that is swinging, and the victim has to be granting combat
    advantage, which is asked of the board at damage time."""
    edge = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="2d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and edge(ctx),
    )


_M1575_STRUCK = "the m1575 is hit by a melee or close attack"


@power(
    "m1575a3",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBlast(3),
    target=NO_TARGET,
    trigger=_M1575_STRUCK,
    on=Trigger(Hit, when=_by_melee_or_close, text=_M1575_STRUCK),
)
def m1575a3(c: Cast) -> None:
    """A step and a swing back, with the choice of swing the card offers.

    Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about the creature
    that swung. "Shifts" with no number is one square.
    """
    me = c.me
    c.shift(1)
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    which = c.choose(["m1575a0", "m1575a1"], f"{c.ref}: which attack") or "m1575a0"
    use(c.world, me, which, targets=[foe], spend=False)


# ==========================================================================
# m1600
# ==========================================================================


def _held_fast(c: Cast, who: int) -> bool:
    return c.is_(Condition.IMMOBILIZED, on=who)


@power(
    "m1600a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m1600a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1600a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
)
def m1600a1(c: Cast) -> None:
    """No damage line: the printed hit is the hold."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1600a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=Target(
        "enemy", 1,
        label="immobilized targets only",
        conditions=frozenset({Condition.IMMOBILIZED}),
    ),
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 6),
)
def m1600a2(c: Cast) -> None:
    """The minor-action half is `c.recast`: the row is already known and what
    the card grants is a cheaper action for the rest of this turn."""
    if not c.strike():
        return
    c.hit()
    c.pull(4)
    c.recast("m1600a3", action=MINOR, per_turn=1, until=When.EOT, on=c.me)


@power(
    "m1600a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="immobilized targets only",
        conditions=frozenset({Condition.IMMOBILIZED}),
    ),
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 6),
)
def m1600a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.ongoing(10, DamageType.POISON)


# ==========================================================================
# m1687
# ==========================================================================

_M1687_BLADES = ("m1687a0", "m1687a3")


@power(
    "m1687a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m1687a0(c: Cast) -> None:
    """The printed "crit 1d8 + 20" is the maximum of the ordinary line, which
    a critical already deals, plus 1d8 on top."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d8"))


@power(
    "m1687a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m1687a1(c: Cast) -> None:
    for _ in range(2):
        use(c.world, c.me, "m1687a0", spend=False)


@power(
    "m1687a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=14),
)
def m1687a2(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.EONT, to="me")


@power(
    "m1687a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="bloodied target only", bloodied=True),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m1687a3(c: Cast) -> None:
    """Two swings at one bloodied creature; the burn is laid once however many
    of the two land, because ongoing damage of one type does not stack."""
    for _ in range(2):
        if not c.strike():
            continue
        c.hit()
        if c.crit:
            c.flat(c.roll("1d8"))
        c.ongoing(5)


@power(
    "m1687a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1687a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Gated on the row that
    is swinging as well as on the victim's state, because the card names one
    weapon and this creature has more than one attack."""
    edge = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="3d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in _M1687_BLADES and edge(ctx),
    )


@power(
    "m1687a5",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1687a5(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(3)


# ==========================================================================
# m2096
# ==========================================================================


@power(
    "m2096a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 3, dtype=DamageType.POISON),
)
def m2096a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2096a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    requires_text="the m2096 must be wielding a longsword",
)
def m2096a1(c: Cast) -> None:
    """The brief prints an orphan attack line with no defence in front of the
    Effect line -- see the report. What the row does is the Effect: a charge,
    whose blow is this creature's own basic attack and not a line of this
    row's, so there is no attack or damage in the header and `c.charge_at`
    is what rolls it.

    The Requirement is text only. It is a fact about what is in the
    creature's hands, which the engine models for characters and not for a
    stat block, and `Power.requires` asked of a monster would refuse the row
    for ever.
    """
    victim = c.target
    if victim is None:
        return
    if c.charge_at(victim):
        c.damage("2d8", 0, dtype=DamageType.POISON, on=victim)
        c.shift(3)


@power(
    "m2096a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    dropped=("c.no_invisibility()",),
)
def m2096a2(c: Cast) -> None:
    """"Grants combat advantage to all attackers" is `to="team"`: the only
    creatures that ever attack this row's target are this creature and its
    allies, and the relation names beneficiaries one at a time.

    Concealment is `c.no_cover`, which is both halves of that printed pair.
    Invisibility is the dropped clause -- `c.see_invisible` and `c.truesight`
    both hand the sight to *one* watcher, and nothing takes the benefit away
    from the creature carrying it.
    """
    if not c.strike():
        return
    c.grants_advantage(until=When.EONT, to="team")
    c.no_cover(until=When.EONT)


@power(
    "m2096a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 3, dtype=DamageType.FIRE, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m2096a3(c: Cast) -> None:
    """The Miss line is a smaller roll of one type, not half of the hit, so
    it is written out rather than declared with `half_on_miss`. The step is
    the printed Effect and comes after every attack, which is `c.last`."""
    if c.strike():
        c.hit()
    else:
        c.damage("2d8", 0, dtype=DamageType.FIRE)
    if c.last:
        c.shift(4)


@power(
    "m2096a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.kill()",),
)
def m2096a4(c: Cast) -> None:
    """Ten of its own hit points for a row back.

    The near-death branch is the printed "instead": the damage is not taken
    and the creature steps away, which is what makes this row safe to spend
    at one hit point. What it does to whatever is carrying it is the dropped
    clause -- nothing finishes a named creature outright, and the relation
    that would say which creature that is (`c.master`) is not set by any
    board the engine fields.
    """
    me = c.me
    health = c.world.get(me, Health)
    doomed = health is not None and health.hp <= 10
    which = c.choose(["m2096a1", "m2096a3"], f"{c.ref}: which row comes back")
    if which:
        c.restore_use(which, on=me)
    if doomed:
        c.shift(3)
    else:
        c.flat(10, on=me)


@power(
    "m2096a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2096a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    `c.ignore_condition` rather than `c.cure`: the printed line is that the
    creature does not suffer the condition, not that the condition has gone
    -- a cured save-ends daze would never be saved against. It is asked each
    turn, inside the watch, because a Requirement that starts false and
    becomes true is exactly what a trait's `requires=` cannot express.
    """
    me = c.me

    def berserk(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if not (c.is_(Condition.DAZED, on=me) or c.is_(Condition.STUNNED, on=me)):
            return
        c.ignore_condition(Condition.DAZED, Condition.STUNNED, on=me, until=When.EOT)
        c.forbid("m2096a4", on=me, until=When.EOT)
        friend = min(
            (a for a in c.allies() if alive(c.world, a)), key=c.distance, default=None
        )
        if friend is not None:
            c.basic(on=friend)

    c.watch(TurnStart, berserk, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3241
# ==========================================================================


@power(
    "m3241a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 9),
)
def m3241a0(c: Cast) -> None:
    """The printed "1d8 + 17 on a critical hit" is the maximum of the
    ordinary line plus 1d8 rolled on top."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d8"))
    c.mark(until=When.EONT)


@power(
    "m3241a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m3241a1(c: Cast) -> None:
    """One step, taken between the two swings. The card offers three places
    for it and this is the one that changes who the second swing can reach,
    which is the only reason the clause is printed."""
    use(c.world, c.me, "m3241a0", spend=False)
    c.shift(1)
    use(c.world, c.me, "m3241a0", spend=False)


@power(
    "m3241a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 9, kind=LIMITED),
)
def m3241a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d8"))
    c.ongoing(10)


_M3241_SLIGHTED = "an enemy marked by the m3241 leaves its side or attacks elsewhere"

#: A move the creature chose. A push, a pull or a slide is not "willingly".
_WILLING = ("walk", "shift", "teleport", "run", "charge", "climb", "fly", "swim")


def _my_mark_walks_off(world: World, me: int, ev: MoveStart) -> bool:
    """Asked on `MoveStart`, not `MoveEnd`: by the time the move has finished
    the enemy has left and `adjacent` is false exactly when the row should
    fire."""
    who = getattr(ev, "actor", None)
    if not _marked_by_me(world, me, who) or who is None:
        return False
    if getattr(ev, "kind_", "") not in _WILLING:
        return False
    return distance_between(world, me, who) <= 1


def _my_mark_swings_elsewhere(world: World, me: int, ev: AttackDeclared) -> bool:
    return _marked_by_me(world, me, getattr(ev, "attacker", None)) and leaves_me_out(
        world, me, ev
    )


@power(
    "m3241a3",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M3241_SLIGHTED,
    on=(
        Trigger(MoveStart, when=_my_mark_walks_off, text=_M3241_SLIGHTED),
        Trigger(AttackDeclared, when=_my_mark_swings_elsewhere, text=_M3241_SLIGHTED),
    ),
)
def m3241a3(c: Cast) -> None:
    """Both printed triggers are declared. Half of them would look finished
    and answer only half the card."""
    me = c.me
    c.shift(1)
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        foe = getattr(ev, "actor", None)
    if foe is None or not alive(c.world, foe):
        return
    use(c.world, me, "m3241a0", targets=[foe], spend=False)


# ==========================================================================
# m3323
# ==========================================================================


@power(
    "m3323a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m3323a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3323a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m3323a1(c: Cast) -> None:
    """A shift of five straight through whoever is standing in the way.

    A shift and not a walk, which is the difference between this row and a
    trample: `movement.overrun` takes the kind and `c.overrun` does not.
    Declared with no target, because the route is what decides whom it
    catches, and the swing is whatever this creature's basic attack actually
    is -- which is what the printed line names.
    """
    for who in _through_them(c, 5, kind="shift"):
        c.basic(on=who)


# ==========================================================================
# m3749
# ==========================================================================

_M3749_BOLTS = ("m3749a1", "m3749a2", "m3749a3")


@power(
    "m3749a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6),
)
def m3749a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3749a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 8),
)
def m3749a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3749a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d6", 8),
)
def m3749a2(c: Cast) -> None:
    """"If the target moves nearer on its next turn" is read off `Moved`,
    which is the only move event carrying both ends of a step -- `MoveEnd`
    says where it finished and nothing about where it began. Paid once, which
    is a flag the watch closes over, because `Trigger` and `c.watch` measure
    a duration and not a count of steps."""
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    paid = [False]

    def closed(ev: Moved) -> None:
        if ev.actor != victim or paid[0]:
            return
        if distance(ev.to, c.here) < distance(ev.from_, c.here):
            paid[0] = True
            c.damage("1d6", 8, on=victim, detail=c.ref)

    c.watch(Moved, closed, until=When.EOTNT, on=me, label=c.ref)


@power(
    "m3749a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3749a3(c: Cast) -> None:
    """The brief prints the bonus twice ("2d8 + 8 8"); one of them is
    extraction noise. The shared pain is hung on the caster's own
    `DamageApplied` and gated on a save-ends hold laid on the victim, so one
    saving throw ends both halves of the printed sentence."""
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)

    def shared(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if hold is None or hold.ended or not alive(c.world, victim):
            return
        c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(DamageApplied, shared, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3749a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
)
def m3749a4(c: Cast) -> None:
    """"Targets closest enemy" and "automatically hits": no attack is rolled,
    and the nearest creature is picked here because `Target` does not sort.
    The rider is a modifier on the caster gated on the victim and on which
    row is swinging, not a hold on the victim -- the printed extra is this
    creature's damage and nobody else's.

    No marker: the printed line asks nothing of the target that the engine
    cannot answer. A sort is not a filter, and picking the nearest enemy in
    the body plays the card exactly as written."""
    victim = min(c.enemies(), key=c.distance, default=None)
    if victim is None:
        return
    c.bonus(
        "damage",
        0,
        dice="1d8",
        dtype=DamageType.NECROTIC,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim
        and ctx.get("power") in _M3749_BOLTS,
    )


@power(
    "m3749a5",
    level=11,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION],
)
def m3749a5(c: Cast) -> None:
    """"Before or after" is both sets, so the neighbours are taken on each
    side of the blink and the union is what pays."""
    before = set(c.within(1, side="enemy"))
    c.teleport(6)
    for foe in sorted(before | set(c.within(1, side="enemy"))):
        if alive(c.world, foe):
            c.grants_advantage(on=foe, until=When.EONT, to="me")


# ==========================================================================
# m3934
# ==========================================================================


@power(
    "m3934a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m3934a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3934a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m3934a1(c: Cast) -> None:
    """A printed band takes the short number."""
    if c.strike():
        c.hit()


@power(
    "m3934a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m3934a2(c: Cast) -> None:
    """A throw and then a run at somebody.

    Declared with no target: the two halves want different creatures and the
    charge picks its own once the throw has gone. `c.charge_at` is what marks
    the swing as a charge, which is what every charge rider reads.
    """
    me = c.me
    shot = min(
        (foe for foe in c.enemies() if c.distance(foe) <= 10),
        key=c.distance,
        default=None,
    )
    if shot is not None:
        use(c.world, me, "m3934a1", targets=[shot], spend=False)
    victim = min(
        (foe for foe in c.enemies() if alive(c.world, foe)), key=c.distance, default=None
    )
    if victim is not None:
        c.charge_at(victim)


@power(
    "m3934a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3934a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Measured the way the printed line measures it -- where the move ended
    against where it began, not how many squares were walked -- and read at
    the end of each move, which is the only moment both ends are known. The
    hold is replaced each time it is re-earned rather than laid beside its
    predecessor, which for a damage rider would pay out twice.
    """
    me = c.me
    held: list[Effect] = []

    def far_enough(_kind: str, start: Any, end: Any, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.bonus(
                "damage", 0, dice="1d10", until=When.SONT, on=me, when=_melee_ctx
            ),
        )

    _after_moving(c, far_enough)


# ==========================================================================
# m4160
# ==========================================================================


@power(
    "m4160a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m4160a0(c: Cast) -> None:
    """Only the burn is radiant; the blow itself prints no type."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.RADIANT)


@power(
    "m4160a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m4160a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4160a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4160a2(c: Cast) -> None:
    """Blink, swing, blink, swing somewhere else.

    Declared with no target: the second creature is chosen after the second
    blink, which is usually a different answer from choosing it before, and
    the card says the two must differ.
    """
    me = c.me
    already: list[int] = []
    for _ in range(2):
        c.teleport(5)
        options = sorted(
            foe for foe in c.enemies() if c.distance(foe) <= 2 and foe not in already
        )
        prey = c.choose(options, f"{c.ref}: which target") if options else None
        if prey is None:
            continue
        already.append(prey)
        use(c.world, me, "m4160a1", targets=[prey], spend=False)


@power(
    "m4160a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4160a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m4160a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.RADIANT, kind=LIMITED, half_on_miss=True),
)
def m4160a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M4160_BLED = "the m4160 is first bloodied"


@power(
    "m4160a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4160_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M4160_BLED),
)
def m4160a5(c: Cast) -> None:
    """The use is spent, because the card gives the row back and then spends
    it -- a second free use would be a breath weapon twice a round for the
    rest of the fight."""
    c.restore_use("m4160a4", on=c.me)
    use(c.world, c.me, "m4160a4")


@power(
    "m4160a6",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=UpTo(4),
    keywords=[Keyword.RADIANT, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m4160a6(c: Cast) -> None:
    """"Save ends both" is one hold carrying the daze and the burn, which is
    what `c.condition(ongoing=)` is for -- applied separately the victim gets
    two saving throws where the card prints one. The blink is the printed
    Effect and happens once, after the last target."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.RADIANT),
        )
    if c.last:
        c.teleport(10)


@power(
    "m4160a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=14),
)
def m4160a7(c: Cast) -> None:
    """No damage line at all. The Aftereffect hangs on `on_end`, which fires
    whichever way the stun goes."""
    victim = c.target
    if victim is None or not c.strike():
        return
    held = c.condition(Condition.STUNNED, until=When.EONT)
    if held is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)
        )


_M4160_STRUCK = "the m4160 is hit by an attack"


@power(
    "m4160a8",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M4160_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M4160_STRUCK),
)
def m4160a8(c: Cast) -> None:
    """`AttackRolled` with `would_hit_me` is the printed "when it is hit":
    the die is down, so the row knows the blow is landing, and the defence is
    read again once this window closes -- so four more can still turn it
    aside. On `Hit` the comparison is already made.

    The bonus is gated on the attacker rather than given a duration, because
    the printed line is about one attack, and `_until_that_blow_lands` takes
    it away again. The blink is hung on the `Miss` that the bonus may have
    just created.
    """
    me = c.me
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    for guard in _guard_against(c, 4, who):
        _until_that_blow_lands(c, who, guard)

    def slipped(ev: Any) -> None:
        if ev.attacker == who and ev.target == me:
            c.teleport(6)

    c.watch(Miss, slipped, until=When.EOT, on=me, once=True, label=f"{c.ref} slipped")


# ==========================================================================
# m4322
# ==========================================================================


def _puppet_of(world: World, eid: int) -> int | None:
    """The second body this creature keeps, if it has one standing."""
    return next(
        (
            s
            for s in sorted(world.relations.targets(Relation.MASTER_OF, eid))
            if alive(world, s)
        ),
        None,
    )


def _puppet_gone(world: World, eid: int) -> bool:
    """The printed "only while it is destroyed"."""
    return _puppet_of(world, eid) is None


@power(
    "m4322a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 7),
)
def m4322a0(c: Cast) -> None:
    """The step is its own printed sentence rather than part of the hit, so
    it is taken whether the blow lands or not."""
    if c.strike():
        c.hit()
        c.slide(1)
    c.shift(1)


@power(
    "m4322a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d10", 5, dtype=DamageType.PSYCHIC),
)
def m4322a1(c: Cast) -> None:
    """The card names nobody the advantage is granted to, which means
    everybody -- and the only creatures that attack this row's target are
    this one and its allies, which is `to="team"`."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m4322a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m4322a2(c: Cast) -> None:
    """"Melee or ranged" is the choice the card offers, taken once for the
    pair. `c.basic` swings whichever row this creature's basic attack
    actually is, melee or ranged, which is what the printed line names."""
    far = (c.choose(["near", "far"], f"{c.ref}: melee or ranged") or "near") == "far"
    for _ in range(2):
        prey = (
            min(c.enemies(), key=c.distance, default=None)
            if far
            else _adjacent_foe(c, c.ref)
        )
        if prey is not None:
            c.basic(on=prey, ranged=far)


@power(
    "m4322a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    requires=_puppet_gone,
    requires_text="the m4322's m4323 must be destroyed",
    narrative=("skill:perception",),
)
def m4322a3(c: Cast) -> None:
    """The second body is bound as a servant, which is what lets the rows
    below find it: `c.summon` puts it on the board and in the initiative
    order and says nothing about whose it is.

    The leash is a watch rather than a hold: "if forced beyond this range it
    teleports back" is a thing that happens at the end of a move, and
    `MoveEnd` is where both positions are known.

    Speaking and hearing through it is the narrative clause. Nothing on a
    board rolls Perception on this creature's behalf from twenty squares
    away, so there is no mechanism to build and nothing is missing.
    """
    me = c.me
    made = c.summon("m4323")
    if not made:
        return
    c.bind(on=made)

    def leashed(ev: Any) -> None:
        if ev.actor not in (me, made) or not alive(c.world, made):
            return
        if distance_between(c.world, me, made) > 20:
            here = c.world.get(me, Position)
            if here is not None:
                c.teleport(0, who=made, to=here.square)

    c.watch(MoveEnd, leashed, until=When.ENCOUNTER, on=me, label=f"{c.ref} leash")


@power(
    "m4322a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4322a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    c.bonus(
        "damage",
        0,
        dice="2d8",
        on=c.me,
        until=When.ENCOUNTER,
        when=_edge_on_target(c),
    )


@power(
    "m4322a5",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4322a5(c: Cast) -> None:
    """A step that has to end nearer the second body than it began.

    `c.shift` with no destination offers the decider every square in range,
    which is useless for a printed line that says where the step has to
    finish, so the destinations are gathered by hand -- the arrangement
    m2924a4 settled one file over.
    """
    me = c.me
    puppet = _puppet_of(c.world, me)
    if puppet is None or c.distance(puppet) <= 1:
        return
    was = c.distance(puppet)
    theirs = squares(c.world, puppet)
    mine = squares(c.world, me)
    closer = sorted(
        sq
        for sq in c.world.reachable_squares(me, c.speed_of())
        if sq not in mine and min(distance(sq, s) for s in theirs) < was
    )
    if not closer:
        return
    c.shift(to=c.world.decide(me, "shift", closer, f"{c.ref}: nearer to it"))
    for foe in sorted(c.enemies()):
        if c.adjacent(foe) and c.adjacent_to(puppet, foe):
            c.grants_advantage(on=foe, until=When.EONT, to="me")


_M4322_SHIELDED = "an attack damages the m4322 while its m4323 is beside it"


def _damaged_me_beside_puppet(world: World, me: int, ev: DamageRolled) -> bool:
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    puppet = _puppet_of(world, me)
    return puppet is not None and distance_between(world, me, puppet) <= 1


@power(
    "m4322a6",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4322_SHIELDED,
    on=Trigger(
        DamageRolled, when=_damaged_me_beside_puppet, text=_M4322_SHIELDED
    ),
)
def m4322a6(c: Cast) -> None:
    """`c.absorb` moves the whole blow, which is the printed "takes the
    damage from the triggering attack". It reads `DamageRolled`, which is why
    the trigger is declared on that event and not on `Hit`: by the time the
    damage has been applied there is nothing left to move."""
    puppet = _puppet_of(c.world, c.me)
    if puppet is not None:
        c.absorb(c.trigger, on=puppet)


# ==========================================================================
# m4751
# ==========================================================================


@power(
    "m4751a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m4751a0(c: Cast) -> None:
    """The follow-up is gated on the victim granting combat advantage, asked
    of the board rather than of the roll: the printed clause is about the
    creature's state, not about whether this swing had the edge."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        use(c.world, c.me, "m4751a1", targets=[victim], spend=False)


@power(
    "m4751a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 0),
)
def m4751a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


_M4751_STUNG = "an enemy hits the m4751 with a melee attack"


@power(
    "m4751a2",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    trigger=_M4751_STUNG,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M4751_STUNG),
)
def m4751a2(c: Cast) -> None:
    """No damage line: the printed hit is the vulnerability. Declared with no
    target and aimed off the trigger, because the row is about the creature
    that swung."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    if c.strike(on=foe):
        c.vulnerable(5, DamageType.POISON, until=When.ENCOUNTER, on=foe)


@power(
    "m4751a3",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4751a3(c: Cast) -> None:
    """Small enough to get through, and large again when it stops. The size
    is lent for the move and taken back, because `c.resize` has a duration
    and the printed line has an event -- the end of this movement."""
    me = c.me
    small = c.resize(Size.TINY, on=me, until=When.EOT)
    try:
        c.move(c.speed_of())
    finally:
        if small is not None:
            c.world.effects.end(small, "it fills out again")


@power(
    "m4751a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4751a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Untyped: the card
    prints no word in front of "bonus"."""
    c.bonus(
        AC,
        4,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


# ==========================================================================
# m5396
# ==========================================================================


@power(
    "m5396a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5396a0(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus"."""
    c.bonus(
        AC,
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m5396a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5396a1(c: Cast) -> None:
    edge = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and edge(ctx),
    )


@power(
    "m5396a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 5),
)
def m5396a2(c: Cast) -> None:
    """The venom is a second packet of a different type rather than part of
    the blow, so it is rolled in the body -- through `c.damage`, which maxes
    with the rest of the line on a critical as the rule reads."""
    if c.strike():
        c.hit()
        c.damage("2d8", 0, dtype=DamageType.POISON)


@power(
    "m5396a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m5396a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("2d8", 0, dtype=DamageType.POISON)
        c.slowed(until=When.EONT)


@power(
    "m5396a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m5396a4(c: Cast) -> None:
    """Declared with no target: the second creature is chosen after the step
    and the card says the two must differ."""
    me = c.me
    first = _adjacent_foe(c, c.ref)
    if first is not None:
        use(c.world, me, "m5396a2", targets=[first], spend=False)
    c.shift(3)
    others = sorted(foe for foe in c.enemies() if foe != first and c.adjacent(foe))
    second = c.choose(others, f"{c.ref}: which other target") if others else None
    if second is not None:
        use(c.world, me, "m5396a2", targets=[second], spend=False)


# ==========================================================================
# m5585
# ==========================================================================


@power(
    "m5585a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5585a0(c: Cast) -> None:
    """Half from two reaches, and nothing off the one type the card excepts.

    Not a resistance and not `c.insubstantial`: a resistance takes a flat
    number off every blow and insubstantiality halves all of them, where this
    halves whatever arrives from two particular reaches. The reach is on the
    row that dealt it, which `DamageRolled` names in `detail` -- it carries no
    `power` -- and the window has to be BEFORE or the blow has already come
    off hit points.
    """
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target != me or ev.dtype is DamageType.FORCE:
            return
        row = get(str(getattr(ev, "detail", "") or ""))
        if row is not None and row.reach_of(0).kind in ("melee", "ranged"):
            c.halve(ev)

    c.watch(
        DamageRolled,
        soften,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=c.ref,
    )


@power(
    "m5585a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5585a1(c: Cast) -> None:
    """The brief gives this row's printed noun as the creature's own ref, so
    which footing it is at home on cannot be read off it -- see the report.
    What is left is the half the engine has: the going costs it nothing,
    which is what "as though it were solid ground" buys on a board carrying
    no such terrain."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5585a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5585a2(c: Cast) -> None:
    """The extra is a second expression gated on the victim's state, which is
    why it is in the body and not in the header."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.is_(Condition.SLOWED, on=victim) or c.is_(Condition.IMMOBILIZED, on=victim):
        c.damage("2d6", 0)


@power(
    "m5585a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d8", 11, kind=LIMITED, half_on_miss=True),
)
def m5585a3(c: Cast) -> None:
    """Prone is not on the save-ends clock -- it lasts until the creature
    stands -- so the printed "(save ends)" belongs to the immobilisation
    alone."""
    if c.strike():
        c.hit()
        c.prone()
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.prone()


@power(
    "m5585a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10, kind=LIMITED),
)
def m5585a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m5585a5",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5585a5(c: Cast) -> None:
    """"The first time during this shift" is the first creature the route
    reports, which comes back in the order they were entered."""
    entered = _through_them(c, 3, kind="shift")
    if not entered:
        return
    who = entered[0]
    c.flat(5, on=who)
    c.slowed(until=When.EONT, on=who)


# ==========================================================================
# m6148
# ==========================================================================


@power(
    "m6148a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6148a0(c: Cast) -> None:
    """Gated on what the creature is doing *now* rather than on what it can
    do: `Movement.modes` only ever says a climb is possible, and the
    exemption is owed only while one is under way."""
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda _ctx: c.moving_as("climb", on=c.me),
    )


@power(
    "m6148a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 9),
)
def m6148a1(c: Cast) -> None:
    """"Or 3d8 + 9 if it has combat advantage" is a second dice line, not a
    rider, so it is rolled in the body. Read off the result of the swing that
    just happened -- asking the board again is too late, because a one-shot
    grant has already been spent."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("3d8", 9)
    else:
        c.hit()


@power(
    "m6148a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m6148a2(c: Cast) -> None:
    """Half its speed, through bodies, and then the bite.

    Declared with no target: the creature it bites is chosen after the step.
    Passing through enemies' spaces is lent for the step and taken back,
    because the printed permission is about this movement.
    """
    me = c.me
    ghost = c.phasing(until=When.EOT, on=me)
    try:
        c.shift(max(1, c.speed_of() // 2))
    finally:
        if ghost is not None:
            c.world.effects.end(ghost, "the move is over")
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        use(c.world, me, "m6148a1", targets=[prey], spend=False)


# ==========================================================================
# m6157
# ==========================================================================


@power(
    "m6157a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 8),
)
def m6157a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6157a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d6", 15, kind=LIMITED),
)
def m6157a1(c: Cast) -> None:
    """"Before or after" -- the step is taken after, so the swing is rolled
    while the target is still the one the chooser handed over. Taken first it
    would pick its own destination and could leave the target out of
    reach."""
    if c.strike():
        c.hit()
    c.shift(2)


_M6157_STRUCK = "the m6157 is hit by an attack"
_M6157_BLED = "the m6157 is first bloodied"


@power(
    "m6157a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6157_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M6157_STRUCK),
)
def m6157a2(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to give the row back sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.temp_hp(10, on=me)
    c.shift(3)


# ==========================================================================
# m6202
# ==========================================================================


@power(
    "m6202a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m6202a0(c: Cast) -> None:
    """A typed damage rider, so the type goes on the modifier: a plain
    `c.bonus("damage", ...)` adds to whatever packet is already being dealt
    and the printed cold would be lost to the victim's resistance."""

    def chilled(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            _melee_ctx(ctx)
            and victim is not None
            and is_(c.world, victim, Condition.SLOWED)
        )

    c.bonus(
        "damage",
        0,
        dice="2d8",
        dtype=DamageType.COLD,
        on=c.me,
        until=When.ENCOUNTER,
        when=chilled,
    )


@power(
    "m6202a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 3),
)
def m6202a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d10", 0, dtype=DamageType.COLD)


@power(
    "m6202a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m6202a2(c: Cast) -> None:
    """A pass: the flight is spent in two halves, because "at any point
    during the move" is what brings a creature into reach that one run to one
    destination would not.

    The distance is flown rather than walked -- `c.move(at=)` names the mode,
    and this creature's legs are slower than its wings. The printed exemption
    is from the *target's* opportunity attack alone, so it is laid against
    that creature and not against the board.
    """
    me = c.me
    total = c.speed_of()
    half = max(1, total // 2)
    c.move(half, at="fly")
    victim = min(c.enemies(), key=c.distance, default=None)
    if victim is not None:
        c.no_provoke(from_=victim, on=me, until=When.EOT)
        use(c.world, me, "m6202a1", targets=[victim], spend=False)
    rest = total - half
    if rest > 0:
        c.move(rest, at="fly")


@power(
    "m6202a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 9, dtype=DamageType.COLD, kind=LIMITED),
)
def m6202a3(c: Cast) -> None:
    """"Creatures in the blast" is everybody, not only enemies. The printed
    recharge sentence sits on top of the die the database files."""
    me = c.me
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m6202a1")
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m6656
# ==========================================================================

#: The aura's label. m6656a5 lays a wider one under the same label, because
#: nothing resizes a live aura, and the trait's watch reads it by this.
_M6656_AURA = "m6656a0"


def _aura_radius(c: Cast) -> int:
    """How wide the standing aura is. `Zone.aura` is the radius and
    `Zones.refresh` recomputes the footprint from it."""
    zid = c.my_aura(_M6656_AURA)
    zone = c.world.get(zid, Zone) if zid else None
    if zone is None or not zone.aura:
        return 0
    return zone.aura


@power(
    "m6656a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6656a0(c: Cast) -> None:
    """Read at the end of each turn, which is when the printed line asks.

    Sides are compared directly rather than through `query.enemies`, which
    filters out the dead. "Can take no actions until the start of its next
    turn" is a stun measured on the *target's* clock, which is what
    `When.SOTNT` is.
    """
    me = c.me
    c.aura(1, label=_M6656_AURA, until=When.ENCOUNTER)

    def scorched(ev: TurnEnd) -> None:
        who = ev.actor
        if who == me or ev.ghost or not alive(c.world, who):
            return
        if team(c.world, who) is team(c.world, me):
            return
        if not c.in_my_aura(who, label=_M6656_AURA):
            return
        c.flat(5, dtype=DamageType.FIRE, on=who)
        c.stunned(until=When.SOTNT, on=who)

    c.watch(TurnEnd, scorched, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6656a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6656a1(c: Cast) -> None:
    """`c.phasing` is the engine's only switch for moving through what is in
    the way, and it is wider than the printed line -- which names enemies'
    spaces and not walls. See the report."""
    c.phasing(on=c.me, until=When.ENCOUNTER)


@power(
    "m6656a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d12", 12, dtype=DamageType.FIRE),
)
def m6656a2(c: Cast) -> None:
    """The brief prints "+16 vs. Reflex and AC", which `Attack` cannot say --
    it carries one defence. The first is taken; see the report."""
    if c.strike():
        c.hit()


@power(
    "m6656a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 12, dtype=DamageType.FIRE),
)
def m6656a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m6656a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=NO_TARGET,
)
def m6656a4(c: Cast) -> None:
    """The pairing the card offers, chosen once. Declared with no target:
    the two swings have different reaches and rarely want the same
    creature."""
    me = c.me
    both_ = (c.choose(["both", "claws"], f"{c.ref}: which pair") or "both") == "both"
    plan = ("m6656a2", "m6656a3") if both_ else ("m6656a3", "m6656a3")
    for ref in plan:
        prey = _foe_within(c, 3 if ref == "m6656a2" else 1, c.ref)
        if prey is not None:
            use(c.world, me, ref, targets=[prey], spend=False)


@power(
    "m6656a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6656a5(c: Cast) -> None:
    """Nothing widens a live aura, so the old one is dispelled and a new one
    laid two squares further out under the same label -- which is what the
    trait's watch reads it by, so its teeth come along."""
    me = c.me
    _recharge_on(c, TurnStart, lambda ev: ev.actor == me and _aura_radius(c) < 5)
    was = _aura_radius(c)
    zid = c.my_aura(_M6656_AURA)
    if zid:
        c.dispel(zid)
    c.aura(was + 2, label=_M6656_AURA, until=When.ENCOUNTER)


@power(
    "m6656a6",
    level=11,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6656a6(c: Cast) -> None:
    """A run through everybody, with a claw at each creature entered.

    `c.use_power` rather than `use`, because the printed "on a hit" needs the
    borrowed row's result and only that one leaves it in `c.result`.
    """
    me = c.me
    _recharge_on(c, TurnStart, lambda ev: ev.actor == me and _aura_radius(c) >= 5)
    c.cure(Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED, on=me)
    for who in _through_them(c, c.speed_of(), kind="shift"):
        if not alive(c.world, who):
            continue
        c.use_power("m6656a3", on=who)
        if c.landed:
            c.ongoing(10, DamageType.FIRE, on=who)


_M6656_BURNED = "the m6656 takes fire damage"


@power(
    "m6656a7",
    level=11,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M6656_BURNED,
    on=Trigger(DamageApplied, when=_burned_me, text=_M6656_BURNED),
)
def m6656a7(c: Cast) -> None:
    """Ten flat, not a damage line: the toll is the same for every creature
    whose space it enters and no attack is rolled for it. Creatures, not
    enemies -- the card says so."""
    for who in _through_them(c, c.speed_of(), kind="shift"):
        if alive(c.world, who):
            c.flat(10, dtype=DamageType.FIRE, on=who)


# ==========================================================================
# m991
# ==========================================================================


@power(
    "m991a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 8),
)
def m991a0(c: Cast) -> None:
    """Two printed critical lines, both of them the maximum of the ordinary
    line -- 12, which a critical already deals -- plus dice on top. Which
    dice depends on whether *that* swing had the edge, read off the result."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        edge = c.result is not None and c.result.advantage
        c.flat(c.roll("2d8" if edge else "2d6"))


@power(
    "m991a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 8),
)
def m991a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m991a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 8),
)
def m991a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m991a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m991a3(c: Cast) -> None:
    """Three swings, each with its own step. Declared with no target: after a
    step the next swing is rarely the same creature."""
    for _ in range(3):
        prey = _adjacent_foe(c, c.ref)
        if prey is not None:
            use(c.world, c.me, "m991a0", targets=[prey], spend=False)
        c.shift(1)


@power(
    "m991a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m991a4(c: Cast) -> None:
    """Both halves of the printed rider need to know *which* creature each
    blow landed on, so the hits are counted per victim rather than as a
    tally: one hit slows, two on the same creature also knock it down.
    `c.use_power` is what leaves the result where `c.landed` can read it."""
    landed: dict[int, int] = {}
    for i in range(2):
        prey = _adjacent_foe(c, c.ref)
        if prey is not None:
            c.use_power("m991a0", on=prey, again=bool(i))
            if c.landed:
                landed[prey] = landed.get(prey, 0) + 1
        c.shift(1)
    for who, count in sorted(landed.items()):
        c.slowed(until=When.SAVE_ENDS, on=who)
        if count >= 2:
            c.prone(on=who)


@power(
    "m991a5",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m991a5(c: Cast) -> None:
    c.shift(3)


@power(
    "m991a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m991a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    edge = _edge_on_target(c)
    c.bonus(
        "damage",
        0,
        dice="2d8",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _melee_ctx(ctx) and edge(ctx),
    )


_M991_STRUCK = "the m991 is hit by an attack"


@power(
    "m991a7",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M991_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M991_STRUCK),
)
def m991a7(c: Cast) -> None:
    """`keep="new"` is the printed "take the new result", lower or not."""
    c.reroll_attack(keep="new")


# ==========================================================================
# m997
# ==========================================================================


@power(
    "m997a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 7),
)
def m997a0(c: Cast) -> None:
    """The printed "crit 1d6 + 17" is the maximum of the ordinary line plus
    1d6 rolled on top."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d6"))


@power(
    "m997a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE),
)
def m997a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m997a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m997a2(c: Cast) -> None:
    """The step is between the swings, which is where the card puts it."""
    for i in range(2):
        prey = _adjacent_foe(c, c.ref)
        if prey is not None:
            use(c.world, c.me, "m997a0", targets=[prey], spend=False)
        if not i:
            c.shift(1)


@power(
    "m997a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 7, kind=LIMITED),
)
def m997a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FORCE)


_M997_OPENING = "the m997 scores a critical hit or drops an enemy"


def _my_critical(world: World, me: int, ev: Hit) -> bool:
    return getattr(ev, "attacker", None) == me and bool(getattr(ev, "critical", False))


@power(
    "m997a4",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M997_OPENING,
    on=(
        Trigger(Hit, when=_my_critical, text=_M997_OPENING),
        Trigger(Dropped, when=by_me, text=_M997_OPENING),
    ),
)
def m997a4(c: Cast) -> None:
    """Either printed trigger. The swing is handed over with the victim named
    explicitly: `c.grant_attack` aims at `c.target`, which on a row declared
    with no target is None and so no attack at all."""
    me = c.me
    pack = [me, *[a for a in c.allies() if c.distance(a) <= 20 and alive(c.world, a)]]
    who = c.choose(sorted(pack), f"{c.ref}: who swings")
    if who is None:
        return
    victim = min(
        (f for f in c.enemies() if alive(c.world, f)),
        key=lambda f: distance_between(c.world, who, f),
        default=None,
    )
    if victim is None:
        return
    if who == me:
        c.basic(on=victim)
    else:
        c.grant_attack(who, on=victim)


@power(
    "m997a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    dropped=("query.light_level(world, square)",),
)
def m997a5(c: Cast) -> None:
    """The blink plays; where it has to end does not. Nothing on a square
    says how brightly it is lit, so "must end in dim light or darkness" has
    nothing to ask -- the same gap ten other rows wait on."""
    c.teleport(20)


@power(
    "m997a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m997a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    "Three or more squares by any means" is squares covered, not distance
    gained, so it is the step count that is read -- a creature pushed in a
    circle has still been moved. The hold is replaced each time it is
    re-earned rather than stacked.
    """
    me = c.me
    held: list[Effect] = []

    def cloaked(_kind: str, _start: Any, _end: Any, steps: int) -> None:
        if steps < 3:
            return
        _renew(c, held, lambda: c.conceal(total=True, on=me, until=When.EONT))

    _after_moving(c, cloaked)
