"""Monster abilities, level 13: the rest of the soldiers.

A second file beside `soldiers.py` for the same level and the same role; the
stat blocks here are the ones that file does not hold. Its conventions are
kept unchanged -- numbers load from `game.db`, a printed total goes into the
header verbatim, a row filed under an action heading that is plainly a trait
is `ActionType.NONE` and armed once, a stat block printing no range means
melee 1, and a helper written for a lower level is imported rather than
copied.

Nine things this file had to settle.

**"An enemy marked by it attacks without including it" is one predicate with
a distance on it.** Six blocks here print that sentence with four different
radii and one with none at all, so `_marked_swung_elsewhere(n)` is a factory
and `leaves_me_out` is declared beside it rather than folded in: the mark is
a relation, and only `among` -- the whole target list of the one use -- can
say the attack left the marker out. A per-target announcement cannot.

**A reroll belongs in the `AttackRolled` window, not on the `Miss`.**
m6017a5's printed trigger is "it misses an enemy", and `Miss` is announced
after the comparison has been made -- `c.reroll_attack` there changes a
number nothing reads again. `resolve.attack` sets `result.hit` *before*
emitting `AttackRolled` and then recomputes the outcome from the result
object after the window closes, so the honest reading of "misses" is a
provisional miss on `AttackRolled`, which is where the row is declared.

**A second opportunity attack in one turn needs the stamp cleared.**
`turns.can_spend` gates an opportunity action on `Budget.opportunity_turn`,
so m5212a0's printed "it can make another opportunity attack against the
same target" is two operations: reset the stamp, then open a window with
`c.provoke`. Opening a window alone was refused by the budget and the row
looked like a rule that never applies.

**An aura carrying two modifiers is one effect with two mods.** `_aura`
wants a single `Effect` per occupant so that leaving the ring takes the
whole thing off, and m115829a0 prints a bonus to two defences. Two `c.bonus`
calls are two effects and the helper can only hold one, so the pair goes
through `effects.apply` with a `Mod` each.

**"Save ends both" over two vulnerabilities is one save.** m5213a4 prints
two, and `c.vulnerable` returns an effect per type. The second is laid for
the encounter and ended off the first's `on_end`, which is the only shape
that rolls one saving throw for the printed sentence.

**Two identical stat blocks.** m2640 and m2654 are the same six rows, and
each block's prose names the *other* one -- the ETL has crossed them. Both
are written out in full rather than one delegating to the other: they are
two creatures with two ids, and a row that reached across would break the
moment one block was corrected.

**A grab that travels is `Moved` plus a pull.** m5386a1 reads its own
movement off the bus and pulls whatever it holds toward the square it
arrived in; `c.no_provoke(from_=held)` is the second half of the printed
sentence and was already a verb.

**A requirement naming gear is not written.** Several blocks print
"Requirement: it must be wielding <its weapon>". A monster's equipment is
not modelled, there is nothing on the board for a gate to read, and a
`requires=` that is false at arm time would refuse a trait for the whole
fight. The line is left off and said here once.

**The aura that is difficult terrain is still the one gap.**
`c.aura(difficult=)` does not exist, a zone would stay where it was made,
and m5386a0 is the only row here that prints it -- so that row carries the
marker and the stand-up saving throw beside it is implemented, which is why
the marker is `dropped=` and not `todo=`.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_06.controllers import _living
from combat_engine.content.monsters.level_07.brutes import _aura
from combat_engine.content.monsters.level_08.brutes import _has_hold, _holding
from combat_engine.content.monsters.level_09.brutes import _put_beside, _volley
from combat_engine.content.monsters.level_10.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_11.skirmishers import _release_earlier
from combat_engine.content.monsters.level_13.soldiers import _burn_and_hold
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
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionEnded,
    Damage,
    DamageApplied,
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
    Ranged,
    Relation,
    RelationSet,
    SavingThrow,
    Size,
    Summon,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    ZoneExited,
    both,
    by_me,
    by_opportunity,
    leaves_me_out,
    power,
    targets_me,
)
from combat_engine.engine.components import Budget
from combat_engine.engine.events import AdjacencyLost, MoveEnd
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me

#: "A Large or larger creature", which is what m2032's three weapon rows
#: raise their critical dice against.
LARGE_OR_BIGGER = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)

#: The four defences, for a printed "+2 bonus to all defences".
EVERY_DEFENCE = (AC, FORT, REF, WILL)


def _bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return bool(health and health.bloodied)


def _not_bloodied(world: World, eid: int) -> bool:
    return not _bloodied(world, eid)


def _marked_swung_elsewhere(within: int) -> Callable[[World, int, Any], bool]:
    """Somebody carrying my mark is swinging, and `within` squares away.

    The mark is read off the relation because `c.marked` needs a `Cast`, and
    `within=0` is the one block that prints no distance at all. The other
    half of the printed sentence -- that the attack leaves the marker out --
    is `leaves_me_out`, declared beside this in each `Trigger` so the walk
    can see both: it reads `among`, and a per-target announcement cannot
    answer "did the burst catch me too".
    """

    def check(world: World, me: int, ev: Any) -> bool:
        foe = getattr(ev, "attacker", None)
        if foe is None or foe == me:
            return False
        if not world.relations.holds(Relation.MARKED_BY, me, foe):
            return False
        return within == 0 or distance_between(world, me, foe) <= within

    return check


def _aura_mods(c: Cast, who: int, mods: list[Mod]) -> Effect | None:
    """One hold carrying several modifiers, for an aura that prints two.

    `_aura` keeps one `Effect` per occupant so that stepping out takes the
    whole of it off, and two `c.bonus` calls are two effects. This is the
    one door to a single hold with a modifier each.
    """
    return c.world.effects.apply(
        who, c.me, When.ENCOUNTER, label=c.ref, mods=[(who, m) for m in mods]
    )


def _big_crit(c: Cast, small: str, big: str) -> None:
    """The printed "crit N+4d6, or N+4d10 against a Large or larger
    creature". N is already the maxed dice `c.damage` rolls on a critical,
    so only the extra die is added -- and it is added with `c.flat` off a
    roll, because `c.damage` inside a crit branch would max it too."""
    victim = c.target
    if victim is None:
        return
    dice = big if c.size_of(victim) in LARGE_OR_BIGGER else small
    c.flat(c.roll(dice), on=victim)


# ==========================================================================
# m115829
# ==========================================================================


@power(
    "m115829a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115829a0(c: Cast) -> None:
    """Two untyped bonuses on one hold: the card prints no type word in
    front of "bonus", so `kind=` is left off both."""
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and alive(c.world, who) and team(c.world, who) is team(c.world, me)

    def hold(who: int) -> Effect | None:
        return _aura_mods(
            c,
            who,
            [
                Mod(what=AC.value, value=2, kind="untyped", label=c.ref),
                Mod(what=REF.value, value=2, kind="untyped", label=c.ref),
            ],
        )

    _aura(c, 1, eligible, hold)


@power(
    "m115829a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m115829a1(c: Cast) -> None:
    """"2d10 + 10, or 2d10 + 12 if the target is marked by it" is the header's
    number and two more, rather than a second `Damage`: the dice are the same
    and only the flat part moves."""
    if c.strike():
        c.hit()
        if c.marked():
            c.flat(2)


@power(
    "m115829a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 6),
)
def m115829a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115829a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
)
def m115829a3(c: Cast) -> None:
    """No attack roll: the mark is the whole of the printed Effect."""
    c.mark(until=When.EONT)


_M115829_LOOKED_AWAY = (
    "an enemy marked by it and within 5 squares attacks without including it"
)


@power(
    "m115829a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger=_M115829_LOOKED_AWAY,
    on=Trigger(
        AttackDeclared,
        when=both(_marked_swung_elsewhere(5), leaves_me_out),
        text=_M115829_LOOKED_AWAY,
    ),
)
def m115829a4(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher
    points a one-enemy row at whoever is nearest, and this row is about the
    creature that swung."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and alive(c.world, foe):
        c.use_power("m115829a2", on=foe, spend=False)


# ==========================================================================
# m1194
# ==========================================================================


@power(
    "m1194a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 4),
)
def m1194a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m1194a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1194a1(c: Cast) -> None:
    """Two swings against two different targets, each through the row that
    prints its own numbers.

    The spec's own attack line for this row is malformed -- a defence that
    is blank and a damage expression belonging to no printed attack here --
    so nothing is declared in the header and m1194a0 carries the numbers,
    which is what "it makes two of its attacks" means.
    """
    if not c.first:
        return
    for victim in c.targets[:2]:
        if alive(c.world, victim):
            c.use_power("m1194a0", on=victim, spend=False)


@power(
    "m1194a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.CHARM],
    attack=Attack(vs=WILL, printed=18),
)
def m1194a2(c: Cast) -> None:
    """No damage on the hit line: the pull is all of it, and the grab is a
    separate printed sentence about everybody rather than about the target.

    "Escape ends both" is the burn hung on the grab: the acid stops when the
    hold does, whichever way the hold ended, which is exactly what the
    printed pair says and what a save-ends duration would not.
    """
    if c.strike():
        c.pull(4 if c.marked() else 2)
    if not c.last:
        return
    for foe in sorted(c.enemies()):
        if not c.adjacent(foe) or not c.marked(foe):
            continue
        held = c.grab(on=foe)
        burn = c.ongoing(10, DamageType.ACID, on=foe, until=When.ENCOUNTER)
        if held is not None and burn is not None:
            held.on_end.append(lambda b=burn: c.world.effects.end(b, "it let go"))


@power(
    "m1194a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("1d10", 5, dtype=DamageType.RADIANT, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m1194a3(c: Cast) -> None:
    """The burst prints no target line, so it catches everybody standing in
    it and not the caster -- which is `EACH_OTHER`, where `EACH_CREATURE`
    would make the m1194 a target of its own burst."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


# ==========================================================================
# m1589
# ==========================================================================


@power(
    "m1589a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 7),
)
def m1589a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1589a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 7),
)
def m1589a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1589_BLED_SOMEBODY = "its attack bloodies an enemy"


@power(
    "m1589a2",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1589_BLED_SOMEBODY,
    on=Trigger(Bloodied, when=by_me, text=_M1589_BLED_SOMEBODY),
)
def m1589a2(c: Cast) -> None:
    """A free swing with either of its two at-wills. Which one is a choice
    the card leaves open, so it is put through the decider rather than
    settled here."""
    which = c.choose(["m1589a0", "m1589a1"], "m1589a2: which attack it follows up with")
    if which:
        c.use_power(which, spend=False)


@power(
    "m1589a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_OTHER,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m1589a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M1589_PINNED: dict[int, Effect] = {}


@power(
    "m1589a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=18),
    dropped=("c.no_teleport()",),
)
def m1589a4(c: Cast) -> None:
    """A gaze that pins one creature at a time.

    "Ranged sight" is written as the long range the level-03 blocks settled
    on; nothing on a board is further off than twenty squares.

    "The effect ends if it uses this on another target" is `_release_earlier`
    -- the printed sentence is about which creature is held, not about the
    row being unavailable while somebody is. The teleport half is dropped:
    nothing bars a teleport, and `c.immovable` is push, pull and slide.
    """
    if not c.strike():
        return
    _release_earlier(c, c.ref)
    c.slowed(until=When.SAVE_ENDS)


@power(
    "m1589a5",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("3d10", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1589a5(c: Cast) -> None:
    """The burn and the attack penalty are one printed "save ends both", so
    they are one hold -- `_burn_and_hold` is the door to that, and it is also
    what keeps a weaker standing fire from being laid beside a worse one.

    The ten it costs itself is spent once for the whole blast, not once per
    creature caught.
    """
    if c.first:
        c.flat(10, dtype=DamageType.PSYCHIC, on=c.me)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _burn_and_hold(c, victim, 10, DamageType.FIRE, attack=2)


@power(
    "m1589a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1589a6(c: Cast) -> None:
    """It gets back up unless acid or fire put it down.

    `c.revives_unless` implements nothing -- it is the declaration that stops
    the AI policy writing the body off -- so the watches below are what
    actually stand it up. `Dropped` says who struck the blow and not what
    with, so the type is taken off the `DamageApplied` immediately before it.
    The rise is taken in the same window rather than deferred to a move
    action on its next turn: nothing owes a body an action, and a body that
    waits a round has already been written off.
    """
    me = c.me
    c.revives_unless(DamageType.ACID, DamageType.FIRE, on=me)
    last: dict[str, bool] = {"finished": False}
    risen: dict[str, int] = {"count": 0}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            kinds = ev.types()
            last["finished"] = DamageType.ACID in kinds or DamageType.FIRE in kinds

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last["finished"] or risen["count"]:
            return
        risen["count"] += 1
        c.reanimate(on=me, hp=10)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


# ==========================================================================
# m1614
# ==========================================================================


@power(
    "m1614a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d12", 7),
)
def m1614a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)


@power(
    "m1614a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1614a1(c: Cast) -> None:
    """Two swings, and a creature caught on both of them.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is struck twice
    -- the only reading under which "if both hit the same target" can ever
    be true. The -2 is a modifier laid for the length of the swings rather
    than an argument, because the blows go through the row that prints them.
    """
    victim = c.target
    if victim is None:
        return
    worse = c.penalty("attack", 2, on=c.me, until=When.EOT)
    try:
        caught = _volley(c, "m1614a0", victim)
    finally:
        if worse is not None:
            c.world.effects.end(worse, "the swings are made")
    if caught:
        c.damage("1d12", on=victim)
        c.grab(on=victim)


@power(
    "m1614a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
    requires=_has_hold,
    requires_text="it must be grabbing a creature",
)
def m1614a2(c: Cast) -> None:
    """"Grabbed target only" is narrower than any `Target` can say, so the
    Requirement carries the caster's half and the body picks from what it is
    actually holding."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m1614a2: which of them it worries") if held else None
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)
        c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m1614a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=19),
    damage=Damage("2d12", 7, kind=LIMITED),
)
def m1614a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


# ==========================================================================
# m1616
# ==========================================================================


@power(
    "m1616a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 8),
)
def m1616a0(c: Cast) -> None:
    """The surge goes whether or not the hold is saved against, and the two
    conditions are one printed "save ends both" -- so one `c.condition` call
    carrying both, not two."""
    if not c.strike():
        return
    c.hit()
    c.spend_surge(on=c.target)
    c.condition(Condition.IMMOBILIZED, Condition.WEAKENED, until=When.SAVE_ENDS)


@power(
    "m1616a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 8, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1616a1(c: Cast) -> None:
    """"Affects an immobilized target only" is a restriction no `Target` can
    say, so the aim is narrowed here rather than thrown away: where another
    creature in range qualifies, the row goes there.

    The ten heals its own kind within two squares as well as itself, and it
    lands whether or not the blow did -- the printed Hit line is one sentence
    and the healing is the back half of it, so it is inside the branch.
    """
    victim = _restricted_to(c, 5, lambda who: c.is_(Condition.IMMOBILIZED, on=who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(10, on=c.me)
    for mate in sorted(c.within(2, side="ally")):
        if mate != c.me and c.is_kind("undead", on=mate):
            c.heal(10, on=mate)


# ==========================================================================
# m2032
# ==========================================================================


@power(
    "m2032a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 8),
)
def m2032a0(c: Cast) -> None:
    """The printed "crit 28" is the maxed dice `c.damage` already rolls on a
    critical, so only the extra die is added -- and which die it is depends
    on how big the creature struck is."""
    if c.strike():
        c.hit()
        if c.crit:
            _big_crit(c, "4d6", "4d10")


@power(
    "m2032a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d10", 7),
)
def m2032a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    `Range` holds and the one this shoots at without a penalty."""
    if c.strike():
        c.hit()
        if c.crit:
            _big_crit(c, "4d6", "4d10")


@power(
    "m2032a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m2032a2(c: Cast) -> None:
    """One swing at each of two creatures: the first is always the melee
    row, the second is either, so the choice goes through the decider."""
    if not c.first:
        return
    victims = [who for who in c.targets[:2] if alive(c.world, who)]
    if not victims:
        return
    c.use_power("m2032a0", on=victims[0], spend=False)
    if len(victims) < 2:
        return
    which = c.choose(["m2032a0", "m2032a1"], "m2032a2: which attack the second takes")
    if which:
        c.use_power(which, on=victims[1], spend=False)


@power(
    "m2032a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d12", kind=LIMITED),
    requires_text="it must have combat advantage against the target",
    dropped=("Usage.RECHARGE(when=)",),
)
def m2032a3(c: Cast) -> None:
    """"Requires combat advantage against the target" is about a pair, and
    `requires=` is handed one creature, so the restriction is asked here --
    and where another creature in reach qualifies the row goes there rather
    than being thrown away.

    "Regains 63 hit points" is a quarter of its maximum, which is what
    `c.surge_value` computes from the database. Writing 63 in would be
    hand-writing a number `game.db` already holds. No surge is spent: the
    card does not say one is.
    """
    victim = _restricted_to(c, 1, lambda who: has_combat_advantage(c.world, c.me, who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(c.surge_value(of=c.me), on=c.me)
    c.grant_action_point(1, on=c.me)


@power(
    "m2032a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 8, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2032a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            _big_crit(c, "4d6", "4d10")
        c.prone()


@power(
    "m2032a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m2032a5(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    "A -2 penalty to saving throws against being dominated" is `save_mod`,
    which is the one place a printed modifier to a save can live. The
    Aftereffect hangs on the hold ending rather than on `escalate`:
    escalation runs on a *failed* save, and an aftereffect is what follows
    the hold going, whichever way it went. One creature at a time, so the
    earlier hold is ended before a new one is laid.
    """
    if not c.strike():
        return
    victim = c.target
    _release_earlier(c, c.ref)
    held = c.condition(
        Condition.DOMINATED, until=When.SAVE_ENDS, save_mod=-2, on=victim
    )
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.dazed(until=When.SAVE_ENDS, on=victim))


@power(
    "m2032a6",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m2032a6(c: Cast) -> None:
    """A shape it can hold for as long as it keeps paying for it.

    The printed text says three durations at once -- end of its next turn,
    sustain minor, and an hour -- which cannot all be true. The sustain is
    taken as the operative one, because that is the only one the card asks
    an action for, and a single anchor effect carries it: everything else is
    laid for the encounter and ended off the anchor, so one saving throw's
    worth of bookkeeping becomes one duration rather than four.
    """
    anchor = c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR, on=c.me)
    parts = [
        c.insubstantial(until=When.ENCOUNTER, on=c.me),
        c.mode("fly", 12, until=When.ENCOUNTER, on=c.me),
        c.hover(until=When.ENCOUNTER, on=c.me),
        c.cannot_attack(on=c.me, until=When.ENCOUNTER),
    ]
    if anchor is None:
        return
    for part in parts:
        if part is not None:
            anchor.on_end.append(lambda p=part: c.world.effects.end(p, "it resumes"))


@power(
    "m2032a7",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m2032a7(c: Cast) -> None:
    """A surge is a quarter of maximum hit points, which is the 63 the card
    prints -- so the surge is spent and the number is not written down.
    "+2 bonus" with no type word in front of it is untyped."""
    c.surge(on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.SONT, on=c.me)


# ==========================================================================
# m2054
# ==========================================================================


@power(
    "m2054a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m2054a0(c: Cast) -> None:
    """The spec prints two durations for one hold -- "until the end of its
    next turn (save ends)" -- which cannot both be true. The saving throw is
    taken as the operative half here, because it is the only one that makes
    this row differ from m2054a1, which prints the same line without it.
    """
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2054a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m2054a1(c: Cast) -> None:
    """The shift is printed *before* the attack, so it happens whether or not
    the blow lands -- and it is one square for one ally, chosen from the two
    sets the card names: beside the m2054, or beside what it is swinging at.
    """
    victim = c.target
    movers = sorted(
        mate
        for mate in c.allies()
        if mate != c.me
        and (c.adjacent(mate) or (victim is not None and c.adjacent_to(victim, mate)))
    )
    chosen = c.choose(movers, "m2054a1: which ally it waves forward") if movers else None
    if chosen is not None:
        c.shift(1, who=chosen)
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m2054a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(20),
    target=NO_TARGET,
)
def m2054a2(c: Cast) -> None:
    """"One ally within line of sight" is not a target of this row -- the
    ally swings -- so the row declares no target and picks both the swinger
    and what it swings at. `c.basic(who=)` names the attacker and the victim
    still defaults to `c.target`, which is None here, so `on=` is explicit.
    """
    mates = sorted(
        mate for mate in c.allies() if mate != c.me and c.can_see(mate)
    )
    chosen = c.choose(mates, "m2054a2: which ally it orders forward") if mates else None
    if chosen is None:
        return
    victims = sorted(
        foe for foe in c.enemies() if distance_between(c.world, chosen, foe) <= 1
    )
    if not victims:
        return
    aim = c.choose(victims, "m2054a2: what the ally strikes at")
    if aim is not None:
        c.basic(who=chosen, on=aim)


@power(
    "m2054a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2054a3(c: Cast) -> None:
    """The burn rides on damage rather than on the hit: the printed sentence
    is "when it damages", and a hit that is wholly resisted has damaged
    nobody. `detail` is the row that dealt it, which is how the trait knows
    the blow came from one of the two attacks named."""
    me = c.me
    held = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)

    def eats(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail not in ("m2054a0", "m2054a1"):
            return
        if any(c.is_(cond, on=ev.target) for cond in held):
            c.ongoing(10, DamageType.ACID, on=ev.target)

    c.watch(DamageApplied, eats, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2056
# ==========================================================================


@power(
    "m2056a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m2056a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2056a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2056a1(c: Cast) -> None:
    """The same trait as m2054a3 with one attack named instead of two, so it
    is written out rather than shared: the two blocks are two creatures and
    the lists are not the same list."""
    me = c.me
    held = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)

    def eats(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail != "m2056a0":
            return
        if any(c.is_(cond, on=ev.target) for cond in held):
            c.ongoing(10, DamageType.ACID, on=ev.target)

    c.watch(DamageApplied, eats, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2098
# ==========================================================================


@power(
    "m2098a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 6),
)
def m2098a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2098a1",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    dropped=("c.no_invisibility()",),
)
def m2098a1(c: Cast) -> None:
    """No damage line: being easy to hit is the whole of it.

    "To all attackers" is `to="team"` read from the m2098's side -- every
    enemy of the target is on one side here, and the relation names one
    beneficiary at a time. Concealment is `c.no_cover`. Invisibility is
    dropped: nothing takes the *benefit* of being unseen away from a
    creature that is already invisible, and `c.truesight` grants a sense to
    one looker rather than stripping one from the target.
    """
    if not c.strike():
        return
    c.grants_advantage(until=When.EONT, to="team")
    c.no_cover(until=When.EONT)


_M2098_BLED = "it is first bloodied"


@power(
    "m2098a2",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(2),
    target=NO_TARGET,
    trigger=_M2098_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2098_BLED),
)
def m2098a2(c: Cast) -> None:
    """A zone rather than an aura: the printed line is about the squares and
    not about the creature, and it stays where it was made when the m2098
    walks off. It slows friend as well as foe, which is wider than the
    printed "for enemies" -- a zone carries no side and this is the reading
    every lower level settled on.

    "First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.
    """
    c.zone(c.area(), until=When.ENCOUNTER, difficult=True, label=c.ref)


@power(
    "m2098a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2098a3(c: Cast) -> None:
    """It sheds its guard and the guard fights for it.

    The card gives the creature it makes no stat block and no id of its own,
    which is exactly what `c.summon_inline` is for: one hit point, and a
    `Companion`, which takes no turn of its own and acts when its summoner
    spends an action commanding it -- the printed "acts on its initiative
    and must be directed".

    "Cannot recharge while that creature is active" is `c.forbid` on this
    row, lifted when the thing goes down; the -4 goes with it. Both ends
    hang off one `Dropped` watch, because they are one printed sentence.
    """
    me = c.me
    where = next(
        (
            sq
            for sq in sorted(c.world.reachable_squares(me, 1))
            if c.world.grid.occupant(sq) is None
        ),
        None,
    )
    made = c.summon_inline(Summon(hp=1), at=where)
    if not made:
        return
    softer = [
        c.penalty(AC, 4, on=me, until=When.ENCOUNTER),
        c.penalty(REF, 4, on=me, until=When.ENCOUNTER),
    ]
    locked = c.forbid(c.ref, on=me, until=When.ENCOUNTER)

    def returned(ev: Dropped) -> None:
        if ev.actor != made:
            return
        for part in (*softer, locked):
            if part is not None:
                c.world.effects.end(part, "it comes back to hand")

    c.watch(Dropped, returned, until=When.ENCOUNTER, on=me, label=f"{c.ref} back")


# ==========================================================================
# m2514
# ==========================================================================


@power(
    "m2514a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 6),
)
def m2514a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2514a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2514a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2514a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=NO_TARGET,
)
def m2514a2(c: Cast) -> None:
    """The ally swings, so this row has no target of its own and `on=` is
    passed explicitly. "An allied elemental beast" is two words off the type
    line, asked of each candidate rather than of the row."""
    mates = sorted(
        mate
        for mate in c.within(5, side="ally")
        if mate != c.me and c.is_kind("elemental", on=mate) and c.is_kind("beast", on=mate)
    )
    chosen = c.choose(mates, "m2514a2: which of them it sets on") if mates else None
    if chosen is None:
        return
    victims = sorted(
        foe for foe in c.enemies() if distance_between(c.world, chosen, foe) <= 1
    )
    if not victims:
        return
    aim = c.choose(victims, "m2514a2: what it is set on")
    if aim is not None:
        c.basic(who=chosen, on=aim)


# ==========================================================================
# m2518
# ==========================================================================


@power(
    "m2518a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 7, dtype=DamageType.COLD),
)
def m2518a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m2518a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d6", 7, dtype=DamageType.COLD),
)
def m2518a1(c: Cast) -> None:
    """"If it uses this on a target it has already grabbed" is asked before
    the new grab is laid, or the question answers itself every time."""
    victim = c.target
    if victim is None or not c.strike():
        return
    again = c.world.relations.holds(Relation.GRABBED_BY, c.me, victim)
    c.hit()
    c.grab(on=victim)
    if again:
        c.spend_surge(on=victim)


@power(
    "m2518a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("2d6", 7, dtype=DamageType.COLD),
    requires=_has_hold,
    requires_text="it must be grabbing a creature",
)
def m2518a2(c: Cast) -> None:
    """It throws down what it was holding.

    "Targets the creature it is grabbing" is narrower than any `Target` can
    say, so the Requirement carries the caster's half and the body picks from
    what it actually holds. The grab is released before the hold is laid --
    the printed line says "no longer grabbed but restrained" -- and the
    Aftereffect hangs on that hold ending, whichever way it ended.
    """
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m2518a2: which of them it throws down") if held else None
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.world.relations.clear(Relation.GRABBED_BY, c.me, victim)
    hold = _burn_and_hold(
        c, victim, 10, DamageType.COLD, conditions=(Condition.RESTRAINED,)
    )
    c.prone(on=victim)
    hold.on_end.append(
        lambda: _burn_and_hold(
            c, victim, 5, DamageType.COLD, conditions=(Condition.SLOWED,)
        )
    )


# ==========================================================================
# m2531
# ==========================================================================


@power(
    "m2531a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d12", 7),
)
def m2531a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)


@power(
    "m2531a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2531a1(c: Cast) -> None:
    """Two swings through the row that prints the numbers; the spec's own
    attack line for this row has a blank defence and a damage expression
    belonging to no printed attack here, so the header declares neither.

    "The target *can* be grabbed" rather than "is": the grab is offered
    rather than taken, which is what `c.may` is for.
    """
    victim = c.target
    if victim is None:
        return
    worse = c.penalty("attack", 2, on=c.me, until=When.EOT)
    try:
        caught = _volley(c, "m2531a0", victim)
    finally:
        if worse is not None:
            c.world.effects.end(worse, "the swings are made")
    if caught:
        c.damage("1d12", on=victim)
        if c.may("take hold of it", who=c.me):
            c.grab(on=victim)


@power(
    "m2531a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 7),
    requires=_has_hold,
    requires_text="it must be grabbing a creature",
)
def m2531a2(c: Cast) -> None:
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m2531a2: which of them it worries") if held else None
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m2531a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=19),
    damage=Damage("2d12", 7, kind=LIMITED),
)
def m2531a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


@power(
    "m2531a4",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m2531a4(c: Cast) -> None:
    """The printed Requirement is about the light in the square it is
    standing in, and light is not on the board at all -- there is nothing
    for a gate to read and nothing missing that a verb would supply, so the
    requirement is left off rather than approximated."""
    c.invisible(until=When.EONT, on=c.me)


# ==========================================================================
# m2603
# ==========================================================================


@power(
    "m2603a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 4),
)
def m2603a0(c: Cast) -> None:
    """"A -2 penalty to saving throws against this condition" is `save_mod`,
    which is the one place a printed modifier to a save can live."""
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, save_mod=-2)


@power(
    "m2603a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=18),
)
def m2603a1(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    "Slowed targets only" is narrower than `Target` can say, so the aim is
    narrowed here and redirected rather than thrown away. The Aftereffect
    hangs on the hold ending; the -2 rides on the hold it is printed under.
    """
    victim = _restricted_to(c, 1, lambda who: c.is_(Condition.SLOWED, on=who))
    if victim is None or not c.strike(on=victim):
        return
    held = c.condition(
        Condition.RESTRAINED, until=When.SAVE_ENDS, save_mod=-2, on=victim
    )
    if held is not None:
        held.on_end.append(
            lambda: c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim
            )
        )


@power(
    "m2603a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=NO_TARGET,
)
def m2603a2(c: Cast) -> None:
    """It picks a held creature up and carries it.

    The relation is set the long way round rather than through `c.ride`,
    which puts the *caster* on a mount: here the m2603 is the mount and the
    creature it has restrained is the passenger, so `RIDDEN_BY` points from
    the m2603 to the target and the engine's own movement carries it.

    The -2 is gated on who is being attacked rather than laid flat, because
    the printed penalty is only against the m2603 itself. The release hangs
    on the restraint ending, which is the printed condition for it.
    """
    me = c.me
    victim = _restricted_to(c, 1, lambda who: c.is_(Condition.RESTRAINED, on=who))
    if victim is None:
        return
    c.world.relations.set(Relation.RIDDEN_BY, me, victim)
    worse = c.penalty(
        "attack",
        2,
        on=victim,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == me,
    )

    def loosed(ev: ConditionEnded) -> None:
        if ev.target != victim or ev.condition is not Condition.RESTRAINED:
            return
        c.world.relations.clear(Relation.RIDDEN_BY, me, victim)
        if worse is not None:
            c.world.effects.end(worse, "it climbs down")
        _put_beside(c, victim, me)

    c.watch(ConditionEnded, loosed, until=When.ENCOUNTER, on=me, label=f"{c.ref} down")


# ==========================================================================
# m2640
# ==========================================================================


@power(
    "m2640a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m2640a0(c: Cast) -> None:
    """Three printed packets, one of them conditional: the header holds the
    untyped blow and the two psychic ones are rolled beside it, because a
    `Damage` holds one type."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d10", dtype=DamageType.PSYCHIC)
    if c.is_(Condition.IMMOBILIZED):
        c.damage("2d10", dtype=DamageType.PSYCHIC)


@power(
    "m2640a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m2640a1(c: Cast) -> None:
    """The mark can be laid for somebody else, which is what `by=` is for --
    "it or an ally of its choice marks the target"."""
    if not c.strike():
        return
    c.hit()
    markers = [c.me, *sorted(m for m in c.allies() if m != c.me)]
    who = c.choose(markers, "m2640a1: whose mark the target takes")
    c.mark(until=When.SAVE_ENDS, by=who if who is not None else c.me)


@power(
    "m2640a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m2640a2(c: Cast) -> None:
    """Two basic attacks, each picking its own target: the printed line names
    none, and after the first blow the second is rarely worth aiming at the
    same creature."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        if alive(c.world, victim):
            c.basic(on=victim)


@power(
    "m2640a3",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2640a3(c: Cast) -> None:
    """The flight is a move taken now, not a mode held afterwards -- but a
    creature with no fly speed cannot be walked through the air, so the mode
    is granted for this turn and the move is made at it."""
    movers = [c.me, *sorted(m for m in c.within(10, side="ally") if m != c.me)]
    who = c.choose(movers, "m2640a3: who takes to the air")
    if who is None:
        return
    c.mode("fly", 8, until=When.EOT, on=who)
    c.move(8, who=who, at="fly")


@power(
    "m2640a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m2640a4(c: Cast) -> None:
    """The temporary hit points are an Effect line about the area rather than
    about the targets, so they are handed out once for the whole burst --
    `c.last` is the first moment the sweep is resolved."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    if not c.last:
        return
    for mate in sorted(c.in_squares(c.area(), side="ally")):
        if mate != c.me:
            c.temp_hp(10, on=mate)


@power(
    "m2640a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2640a5(c: Cast) -> None:
    """It blinks in beside somebody and an ally runs at the same creature.

    "Within 5 squares of its start or end point" is measured before the
    teleport as well as after, so the start is taken first -- by the time the
    blink has happened the old square is gone and half the printed set with
    it.
    """
    me = c.me
    foes = sorted(foe for foe in c.enemies() if c.distance(foe) <= 10)
    victim = c.choose(foes, "m2640a5: which enemy it appears beside") if foes else None
    if victim is None:
        return
    near_start = {m for m in c.within(5, side="ally") if m != me}
    if not _put_beside(c, me, victim):
        return
    runners = sorted(near_start | {m for m in c.within(5, side="ally") if m != me})
    mate = c.choose(runners, "m2640a5: which ally runs in") if runners else None
    if mate is not None:
        c.charge_at(victim, who=mate)


# ==========================================================================
# m2643
# ==========================================================================


@power(
    "m2643a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 6),
)
def m2643a0(c: Cast) -> None:
    """"Crit 18 + 1d6": the 18 is the maxed dice `c.damage` already rolls on
    a critical, so only the extra die is added -- rolled through `c.flat`,
    because `c.damage` inside the crit branch would max that too."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d6"))
        c.slowed(until=When.EONT)


@power(
    "m2643a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d4", 4),
)
def m2643a1(c: Cast) -> None:
    """Range 6/12: the header carries the short range."""
    if c.strike():
        c.hit()


_M2643_SLIPPED = "a slowed enemy beside it leaves its square"


def _slowed_neighbour_moving(world: World, me: int, ev: MoveStart) -> bool:
    """A slowed enemy standing next to me is about to move.

    `MoveStart` rather than `MoveEnd`: the printed row ends the movement,
    and by the time a move has finished there is nothing left to stop --
    and the creature is no longer adjacent, which is precisely when the row
    should fire.
    """
    who = ev.actor
    if who == me or team(world, who) is team(world, me):
        return False
    if distance_between(world, me, who) > 1:
        return False
    from combat_engine.engine.query import is_

    return is_(world, who, Condition.SLOWED)


@power(
    "m2643a2",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 6),
    trigger=_M2643_SLIPPED,
    on=Trigger(MoveStart, when=_slowed_neighbour_moving, text=_M2643_SLIPPED),
)
def m2643a2(c: Cast) -> None:
    """Aimed off the trigger rather than at a declared target: the
    dispatcher would point a one-enemy row at whoever is nearest, and this
    row is about the creature that is leaving. "The target's movement ends"
    is the interrupt cancelling the step it is answering."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not alive(c.world, foe):
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.cancel()


@power(
    "m2643a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m2643a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m2654
# ==========================================================================


@power(
    "m2654a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m2654a0(c: Cast) -> None:
    """m2640's six rows printed a second time under a second id. Written out
    rather than delegated: two ids are two creatures, and a row reaching
    across would break the moment one block was corrected."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d10", dtype=DamageType.PSYCHIC)
    if c.is_(Condition.IMMOBILIZED):
        c.damage("2d10", dtype=DamageType.PSYCHIC)


@power(
    "m2654a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m2654a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    markers = [c.me, *sorted(m for m in c.allies() if m != c.me)]
    who = c.choose(markers, "m2654a1: whose mark the target takes")
    c.mark(until=When.SAVE_ENDS, by=who if who is not None else c.me)


@power(
    "m2654a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m2654a2(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if alive(c.world, victim):
            c.basic(on=victim)


@power(
    "m2654a3",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2654a3(c: Cast) -> None:
    movers = [c.me, *sorted(m for m in c.within(10, side="ally") if m != c.me)]
    who = c.choose(movers, "m2654a3: who takes to the air")
    if who is None:
        return
    c.mode("fly", 8, until=When.EOT, on=who)
    c.move(8, who=who, at="fly")


@power(
    "m2654a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m2654a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    if not c.last:
        return
    for mate in sorted(c.in_squares(c.area(), side="ally")):
        if mate != c.me:
            c.temp_hp(10, on=mate)


@power(
    "m2654a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2654a5(c: Cast) -> None:
    me = c.me
    foes = sorted(foe for foe in c.enemies() if c.distance(foe) <= 10)
    victim = c.choose(foes, "m2654a5: which enemy it appears beside") if foes else None
    if victim is None:
        return
    near_start = {m for m in c.within(5, side="ally") if m != me}
    if not _put_beside(c, me, victim):
        return
    runners = sorted(near_start | {m for m in c.within(5, side="ally") if m != me})
    mate = c.choose(runners, "m2654a5: which ally runs in") if runners else None
    if mate is not None:
        c.charge_at(victim, who=mate)


# ==========================================================================
# m3838
# ==========================================================================


@power(
    "m3838a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 4, dtype=DamageType.LIGHTNING),
)
def m3838a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3838a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=21),
    damage=Damage("3d10", 6, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3838a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3838a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8, dtype=DamageType.COLD),
)
def m3838a2(c: Cast) -> None:
    """Range 15/30: the header carries the short range."""
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m3920
# ==========================================================================


@power(
    "m3920a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 6),
)
def m3920a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3920a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m3920a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3920a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("3d6", 6, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m3920a2(c: Cast) -> None:
    """A penalty takes no `kind=` and that is the rule, so the four
    defences are four plain calls."""
    if not c.strike():
        return
    c.hit()
    for defended in EVERY_DEFENCE:
        c.penalty(defended, 2, until=When.EONT)


_M3920_WALKED_OFF = "an enemy moves or shifts out of a square beside it"


def _left_my_side(world: World, me: int, ev: AdjacencyLost) -> bool:
    """An enemy stopped being adjacent to me, and it was the one moving.

    `AdjacencyLost` is emitted mirrored, so `actor` is either creature, and
    `mover` says which one moved (#368). The turn test stays beside it and
    is not redundant: it is what keeps a *shove* out, which "moves or
    shifts" wants anyway. Together they also catch the case the turn test
    alone could not -- the enemy, on its own turn, pushing the m3920 away.
    """
    if me not in (ev.actor, ev.other):
        return False
    foe = ev.other if ev.actor == me else ev.actor
    if foe == me or team(world, foe) is team(world, me):
        return False
    if getattr(ev, "mover", 0) != foe:
        return False
    return world.turn == foe


@power(
    "m3920a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3920_WALKED_OFF,
    on=Trigger(AdjacencyLost, when=_left_my_side, text=_M3920_WALKED_OFF),
)
def m3920a3(c: Cast) -> None:
    ev, me = c.trigger, c.me
    actor = getattr(ev, "actor", None)
    foe = getattr(ev, "other", None) if actor == me else actor
    if foe is not None and alive(c.world, foe):
        c.use_power("m3920a0", on=foe, spend=False)


@power(
    "m3920a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3920a4(c: Cast) -> None:
    """"+2 bonus" with no type word in front of it is untyped."""
    c.heal(10, on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me)


# ==========================================================================
# m4167
# ==========================================================================


@power(
    "m4167a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 6),
)
def m4167a0(c: Cast) -> None:
    """Two printed packets: the header holds the untyped blow and the acid
    is rolled beside it, because a `Damage` holds one type."""
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.ACID)


@power(
    "m4167a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d12", 6),
)
def m4167a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4167a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m4167a2(c: Cast) -> None:
    """Three swings: two of one at-will and one of the other. The card names
    the two by the limbs that make them, which maps onto this block's two
    melee rows -- the marking one is the pair and the acid one is the
    single, which is the only reading under which a soldier's mark is the
    thing it does twice.
    """
    if not c.first:
        return
    victims = [who for who in c.targets[:2] if alive(c.world, who)]
    if not victims:
        return
    for victim in victims[:2]:
        c.use_power("m4167a1", on=victim, spend=False)
    if len(victims) == 1:
        c.use_power("m4167a1", on=victims[0], spend=False)
    c.use_power("m4167a0", on=victims[0], spend=False)


@power(
    "m4167a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 4, dtype=DamageType.ACID, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m4167a3(c: Cast) -> None:
    """The creature it leaves behind arrives once for the whole blast, not
    once per target, and `c.summon` is what puts something both on the board
    and in the initiative order -- which is the printed "it acts just after
    the m4167"."""
    if c.strike():
        c.hit()
    if not c.last:
        return
    free = sorted(sq for sq in c.area() if c.world.grid.occupant(sq) is None)
    if free:
        c.summon("m4168", at=c.world.decide(c.me, "summon", free, f"{c.ref}: where"))


_M4167_BLED = "it is first bloodied"


@power(
    "m4167a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4167_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M4167_BLED),
)
def m4167a4(c: Cast) -> None:
    """"It recharges, and it uses it" -- `c.restore_use` hands the use back
    and `c.use_power` spends it again. "First bloodied" needs no guard:
    `Bloodied` is emitted on the crossing and nowhere else."""
    c.restore_use("m4167a3", on=c.me)
    c.use_power("m4167a3")


@power(
    "m4167a5",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=18),
)
def m4167a5(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit, and the Aftereffect
    hangs on it ending, whichever way it ended."""
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT)
    if held is not None and victim is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m4463
# ==========================================================================


@power(
    "m4463a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 5),
)
def m4463a0(c: Cast) -> None:
    """"Crit 4d8 + 21": the 21 is the maxed dice plus the flat part, which
    `c.damage` already produces on a critical, so only the extra dice are
    added."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("4d8"))
        c.mark(until=When.EONT)


@power(
    "m4463a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d8", 5),
    dropped=("c.restrict_shift()",),
)
def m4463a1(c: Cast) -> None:
    """A mark that lasts until the target gets away from it.

    The duration is not one `When` can say -- "until it ends its turn in a
    square that is not adjacent" -- so the mark is laid for the encounter
    and a `TurnEnd` watch takes it off at exactly the printed moment.

    Dropped: nothing restricts *where* a shift may end. `c.cannot_shift`
    forbids the step outright, which is a different and harsher sentence,
    and would keep the target beside the m4463 rather than letting it leave
    the only way the card allows.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.mark(until=When.ENCOUNTER, on=victim)
    if held is None:
        return

    def away(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if not c.adjacent(victim):
            c.world.effects.end(held, "it got clear")

    c.watch(TurnEnd, away, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} clear")


@power(
    "m4463a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=18),
)
def m4463a2(c: Cast) -> None:
    """No damage line: the pull is the whole of the hit."""
    if c.strike():
        c.pull(4)


_M4463_HURT = "it takes damage"


@power(
    "m4463a3",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger=_M4463_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M4463_HURT),
)
def m4463a3(c: Cast) -> None:
    """"Until it attacks or until the end of its next turn" is two endings,
    and only the second is a duration -- so the first is a watch on its own
    swing, which takes the hold off before the attack resolves.

    `targets_me` rather than `about_me`: `DamageApplied` names its subject
    `target`, and `about_me` reads `actor` and only `actor`.
    """
    me = c.me
    hidden = c.invisible(until=When.EONT, on=me)
    if hidden is None:
        return

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            c.world.effects.end(hidden, "it gave itself away")

    c.watch(AttackDeclared, swung, until=When.EONT, on=me, label=f"{c.ref} seen")


@power(
    "m4463a4",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4463a4(c: Cast) -> None:
    """Into the stone and through it.

    `c.phasing` is the passage and `c.merge` is the printed half that
    follows it -- "it can end its movement in such a square, and cannot be
    seen or attacked". The restriction on what it may then do is `c.merge`'s
    own: there is no line of effect out of a solid square, so nothing but a
    step back into the open is available.
    """
    c.phasing(until=When.EOT, on=c.me)
    if c.may("walk rather than step", who=c.me):
        c.move(3)
    else:
        c.shift(1)
    if c.may("stay inside the stone", who=c.me):
        c.merge()


@power(
    "m4463a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4463a5(c: Cast) -> None:
    """A trait armed at the start of the fight, which is the printed moment
    -- "when it makes an initiative check at the start of an encounter".

    The check is rolled against the best passive Perception on the other
    side, which is what an opposed Stealth check comes to on a board. Cover
    and concealment are not asked: a trait whose Requirement is false at the
    moment of arming is refused once and never armed again, so the condition
    is read here, where it is re-read if it is ever re-armed.
    """
    watchers = [c.passive("perception", of=foe) for foe in c.enemies()]
    if not watchers:
        return
    if c.check("stealth", max(watchers)):
        c.hide()


# ==========================================================================
# m4491
# ==========================================================================


@power(
    "m4491a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 4),
)
def m4491a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4491a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("3d10", 4, kind=LIMITED),
)
def m4491a1(c: Cast) -> None:
    """The mark and the slow are one printed "save ends both", so they are
    one hold -- and a mark is a relation rather than a condition, so the
    two cannot share a `c.condition` call: the mark is laid for the
    encounter and ended off the hold it is printed under."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    held = c.slowed(until=When.SAVE_ENDS)
    marked = c.mark(until=When.ENCOUNTER, on=victim)
    if held is not None and marked is not None:
        held.on_end.append(lambda: c.world.effects.end(marked, "the hold ended"))


_M4491_SHOOK_IT = "an enemy beside it shakes something off"


def _neighbour_saved(world: World, me: int, ev: SavingThrow) -> bool:
    who = ev.actor
    if who == me or team(world, who) is team(world, me):
        return False
    return ev.saved and distance_between(world, me, who) <= 1


@power(
    "m4491a2",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4491_SHOOK_IT,
    on=Trigger(SavingThrow, when=_neighbour_saved, text=_M4491_SHOOK_IT),
)
def m4491a2(c: Cast) -> None:
    """It steps and swings at somebody else: "against a target other than
    the triggering enemy", so the creature that just saved is left out of the
    choice rather than aimed at."""
    spared = getattr(c.trigger, "actor", None)
    c.shift(c.speed_of())
    c.restore_use("m4491a1", on=c.me)
    others = sorted(
        foe for foe in c.enemies() if foe != spared and c.distance(foe) <= 1
    )
    victim = c.choose(others, "m4491a2: which of the others it turns on") if others else None
    if victim is not None:
        c.use_power("m4491a1", on=victim)


# ==========================================================================
# m4529
# ==========================================================================


@power(
    "m4529a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8),
)
def m4529a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow
    did."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m4529a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8),
)
def m4529a1(c: Cast) -> None:
    """Range 15/30: the header carries the short range. The mark is an
    Effect line and lands on a miss."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m4529a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4529a2(c: Cast) -> None:
    """"This effect ends when it moves" is a watch on its own movement, and
    not a duration -- nothing in `When` says it."""
    me = c.me
    held = c.threatens(2, on=me, until=When.ENCOUNTER)
    if held is None:
        return

    def stepped(ev: Moved) -> None:
        if ev.actor == me:
            c.world.effects.end(held, "it moved")

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=f"{c.ref} planted")


_M4529_CAUGHT = "it hits with an opportunity attack"


@power(
    "m4529a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4529_CAUGHT,
    on=Trigger(Hit, when=both(by_me, by_opportunity), text=_M4529_CAUGHT),
)
def m4529a3(c: Cast) -> None:
    """Aimed off the trigger: `Hit` carries `attacker` and `target` and no
    `actor`, and the creature knocked down is the one that was hit."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None and alive(c.world, foe):
        c.prone(on=foe)


@power(
    "m4529a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4529a4(c: Cast) -> None:
    """A mark arrives as a relation, so `RelationSet` is the moment it lands
    and `RelationCleared` is the moment it goes -- and the two together are
    what keeps the grant exactly as long as the mark, whatever duration the
    row that laid it chose.
    """
    me = c.me
    given: dict[int, Effect] = {}

    def marked(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.MARKED_BY or ev.source != me:
            return
        if ev.target in given:
            return
        held = c.grants_advantage(until=When.ENCOUNTER, on=ev.target, to="me")
        if held is not None:
            given[ev.target] = held

    def unmarked(ev: Any) -> None:
        if ev.kind_ is not Relation.MARKED_BY or ev.source != me:
            return
        held = given.pop(ev.target, None)
        if held is not None:
            c.world.effects.end(held, "the mark went")

    from combat_engine.engine.events import RelationCleared

    c.watch(RelationSet, marked, until=When.ENCOUNTER, on=me, label=f"{c.ref} on")
    c.watch(RelationCleared, unmarked, until=When.ENCOUNTER, on=me, label=f"{c.ref} off")
    for foe in sorted(c.enemies()):
        if c.marked(foe):
            marked(RelationSet(kind_=Relation.MARKED_BY, source=me, target=foe))


# ==========================================================================
# m4610
# ==========================================================================


@power(
    "m4610a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 6),
)
def m4610a0(c: Cast) -> None:
    """The extra die is asked *before* this row's own hold is laid, or the
    immobilize it applies makes its own condition true every time."""
    victim = c.target
    if victim is None or not c.strike():
        return
    already = _living(c, victim) and any(
        c.is_(cond, on=victim)
        for cond in (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)
    )
    c.hit()
    if already:
        c.damage("1d8")
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4610a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m4610a1(c: Cast) -> None:
    """"Targets an immobilized, stunned or unconscious creature" is narrower
    than any `Target` can say, so the aim is narrowed here and redirected
    rather than thrown away."""
    victim = _restricted_to(
        c,
        1,
        lambda who: any(
            c.is_(cond, on=who)
            for cond in (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)
        ),
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.spend_surge(on=victim)
    c.stunned(until=When.EONT, on=victim)


@power(
    "m4610a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4610a2(c: Cast) -> None:
    """Two swings of its at-will, each picking its own target: the printed
    line names none."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        if alive(c.world, victim):
            c.use_power("m4610a0", on=victim, spend=False)


@power(
    "m4610a3",
    level=13,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4610a3(c: Cast) -> None:
    """"Only on its own turn" is asked in the body rather than declared:
    a free action has no turn gate of its own, and `c.turn_of` is the
    question."""
    if c.turn_of() != c.me:
        return
    kin = sorted(
        who
        for who in c.within(10)
        if who != c.me and c.is_kind("undead", on=who) and alive(c.world, who)
    )
    chosen = c.choose(kin, "m4610a3: which of them it changes places with") if kin else None
    if chosen is not None:
        c.swap(chosen)


# ==========================================================================
# m5212
# ==========================================================================


@power(
    "m5212a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5212a0(c: Cast) -> None:
    """A second opportunity attack in the same turn, which takes two
    operations.

    `turns.can_spend` gates an opportunity action on `Budget.opportunity_turn`
    being something other than this turn's stamp, so clearing the stamp is
    what makes the second swing legal -- and `c.provoke` is what gives it
    something to answer. Opening a window alone was refused by the budget
    and read as a rule that never applies.

    "Another" is one more, so the grant is taken once a turn.
    """
    me = c.me
    spent: dict[str, int] = {"round": -1}

    def again(ev: Hit) -> None:
        if ev.attacker != me or not getattr(ev, "opportunity", False):
            return
        if spent["round"] == c.world.round:
            return
        spent["round"] = c.world.round
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.opportunity_turn = -1
        c.provoke(me, on=ev.target, why=c.ref)

    c.watch(Hit, again, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5212a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5212a1(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m5212a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 14),
)
def m5212a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5212a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 14, kind=LIMITED),
)
def m5212a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


_M5212_BLED = "it is first bloodied"


@power(
    "m5212a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger=_M5212_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M5212_BLED),
)
def m5212a4(c: Cast) -> None:
    """"No Action" is `ActionType.NONE` with a declared trigger: the row
    costs nothing and still waits for the crossing. "First bloodied" needs
    no guard -- `Bloodied` is emitted on the crossing and nowhere else."""
    for foe in sorted(c.enemies()):
        if c.distance(foe) <= 10:
            c.flat(10, dtype=DamageType.NECROTIC, on=foe)
    c.heal(10, on=c.me)


# ==========================================================================
# m5213
# ==========================================================================


@power(
    "m5213a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5213a0(c: Cast) -> None:
    """The aura is read at the moment a turn begins rather than held on
    whoever is standing inside it: the printed hold outlasts the aura --
    "until the start of its next turn" -- so stepping out of the ring does
    not shake it off."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def began(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} slow")


@power(
    "m5213a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
)
def m5213a1(c: Cast) -> None:
    """"Five extra cold and necrotic damage" is one packet of two types,
    which is what `dtypes` is for -- two `c.flat` calls would be two packets
    and would be resisted twice."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        victim = ev.target
        if not c.world.relations.holds(Relation.MARKED_BY, me, victim):
            return
        if any(
            mate != victim and team(c.world, mate) is team(c.world, victim)
            for mate in c.within(1, of=victim)
        ):
            return
        c.flat(5, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=victim)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5213a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 12, dtype=DamageType.NECROTIC),
)
def m5213a2(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow did.
    The cold is a second printed packet beside the header's."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.COLD)
    c.mark(until=When.EONT)


@power(
    "m5213a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=16),
)
def m5213a3(c: Cast) -> None:
    """No damage on either line, so the Miss branch is written out: the push
    happens whether or not the blow landed and only the hold turns on it.
    A bare `half_on_miss` would have been a flag nothing reads."""
    if c.strike():
        c.push(3)
        c.immobilized(until=When.EONT)
    else:
        c.push(3)


_M5213_STIRRED = "a creature beside it and marked by it moves or shifts"


def _marked_neighbour_moving(world: World, me: int, ev: MoveStart) -> bool:
    """One of my marked neighbours is about to move.

    `MoveStart` rather than `MoveEnd`: by the time the step has landed the
    creature is no longer beside me, which is precisely when the row should
    fire.
    """
    who = ev.actor
    if who == me or distance_between(world, me, who) > 1:
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who)


@power(
    "m5213a4",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=16),
    trigger=_M5213_STIRRED,
    on=Trigger(MoveStart, when=_marked_neighbour_moving, text=_M5213_STIRRED),
)
def m5213a4(c: Cast) -> None:
    """No damage line: the slide and the two vulnerabilities are the hit.

    "Save ends both" over two vulnerabilities is one saving throw, and
    `c.vulnerable` returns an effect per type -- so the second is laid for
    the encounter and ended off the first's `on_end`, which is the only
    shape that rolls one save for the printed sentence.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not alive(c.world, foe) or not c.strike(on=foe):
        return
    c.slide(1, on=foe)
    cold = c.vulnerable(5, DamageType.COLD, until=When.SAVE_ENDS, on=foe)
    rot = c.vulnerable(5, DamageType.NECROTIC, until=When.ENCOUNTER, on=foe)
    if cold is not None and rot is not None:
        cold.on_end.append(lambda: c.world.effects.end(rot, "the hold ended"))


# ==========================================================================
# m5386
# ==========================================================================


@power(
    "m5386a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aura(difficult=)",),
)
def m5386a0(c: Cast) -> None:
    """Getting up inside the ring takes a saving throw.

    Standing up is the prone condition ending, which is the only moment the
    engine announces; a failed save re-applies it, and the action the
    creature spent getting up is already gone -- which is the printed "it
    loses the action it used to try to stand".

    Dropped: `c.aura` takes no `difficult=`, and a zone would stay where it
    was made rather than travelling with the creature. That is the half this
    row cannot say; the saving throw above is the half it can, which is why
    the marker is `dropped=` and not `todo=`.
    """
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def rose(ev: ConditionEnded) -> None:
        if ev.condition is not Condition.PRONE or ev.target == me:
            return
        if team(c.world, ev.target) is team(c.world, me):
            return
        if ev.target not in c.world.zones.occupants(ring):
            return
        if not c.save(on=ev.target, bare=True, against=c.ref):
            c.prone(on=ev.target)

    c.watch(ConditionEnded, rose, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


@power(
    "m5386a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5386a1(c: Cast) -> None:
    """What it holds travels with it, and gets no parting swing.

    `Moved` rather than `MoveEnd`, because the pull is toward the square it
    has just arrived in and that is the field `Moved` carries. The grab is
    not re-laid: the relation was never cleared, which is the printed "the
    creature remains grabbed".
    """
    me = c.me

    def dragged(ev: Moved) -> None:
        if ev.actor != me:
            return
        for held in sorted(_holding(c.world, me)):
            c.no_provoke(from_=held, on=me, until=When.EOT)
            if distance_between(c.world, me, held) > 1:
                c.pull(2, on=held, anchor=ev.to)

    c.watch(Moved, dragged, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5386a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 8),
)
def m5386a2(c: Cast) -> None:
    """"If it has fewer than two creatures grabbed" is counted off the
    relation, which is where a grab lives.

    "Sustain Free: it sustains each of its grabs" needs nothing of its own:
    a grab here is a relation that stands until something clears it, so the
    printed line is already true and there is no hold waiting to lapse.
    """
    if not c.strike():
        return
    c.hit()
    if len(_holding(c.world, c.me)) < 2:
        c.grab()


@power(
    "m5386a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m5386a3(c: Cast) -> None:
    """Two swings, one or two creatures. "The target or targets of the
    attacks fall prone" is read off what actually landed, which is why the
    hits are counted off the bus rather than taken from `use`'s answer."""
    if not c.first:
        return
    me = c.me
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m5386a2":
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        victims = [who for who in c.targets[:2] if alive(c.world, who)]
        if not victims:
            return
        for index in range(2):
            victim = victims[index % len(victims)]
            if alive(c.world, victim):
                c.use_power("m5386a2", on=victim, spend=False)
    finally:
        c.world.effects.end(counter, "the swings are made")
    if len(landed) >= 2:
        for victim in sorted(set(landed)):
            c.prone(on=victim)


@power(
    "m5386a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5386a4(c: Cast) -> None:
    """Two readings of one printed Effect, and the card offers the choice.

    "Move through enemies' spaces" is `c.phasing` in both branches: nothing
    narrower exists, and a step through a creature is the thing phasing is
    for. The half-speed branch adds the printed passage through blocking
    terrain, which is the same verb for longer.
    """
    me = c.me
    c.ignores_difficult(on=me, until=When.EOT)
    c.phasing(until=When.EOT, on=me)
    speed = c.speed_of(me)
    if c.may("go through the wall instead", who=me):
        c.shift(max(1, speed // 2))
    else:
        c.shift(speed)


@power(
    "m5386a5",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d10", 6),
    requires=_has_hold,
    requires_text="it must be grabbing a creature",
)
def m5386a5(c: Cast) -> None:
    """"Ongoing 15 until the grab ends" is the burn hung on the grab rather
    than on a saving throw: it stops when the hold does, whichever way the
    hold ended."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m5386a5: which of them it crushes") if held else None
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    burn = c.ongoing(15, on=victim, until=When.ENCOUNTER)
    for eff in c.world.effects.of(victim):
        if eff.source == c.me and Condition.GRABBED in eff.conditions and burn is not None:
            eff.on_end.append(lambda b=burn: c.world.effects.end(b, "it let go"))
            break


# ==========================================================================
# m5465
# ==========================================================================


@power(
    "m5465a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5465a0(c: Cast) -> None:
    """"Willingly" is the creature's own turn: a shove out of the ring is
    somebody else's doing, and whose turn it is is the only thing on the
    board that tells the two apart."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def left(ev: ZoneExited) -> None:
        if ev.zone != ring or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.world.turn == ev.actor:
            c.flat(10, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5465a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5465a1(c: Cast) -> None:
    me = c.me

    def chilled(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        if DamageType.COLD in ev.types():
            c.slowed(until=When.EONT, on=me)

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5465a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5),
)
def m5465a2(c: Cast) -> None:
    """The Effect line turns the target's own attacks into openings.

    `c.provoke` is the door into the opportunity window, and the gate is
    `leaves_me_out` by hand: the attack is announced once per target, so
    `ev.target != me` only says *this* announcement missed me out, and
    `among` is the whole target list of the one use.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.FIRE)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        if me in getattr(ev, "among", (ev.target,)):
            return
        c.provoke(me, on=victim, why=c.ref)

    c.watch(AttackDeclared, swung, until=When.EONT, on=me, label=f"{c.ref} opening")


@power(
    "m5465a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE),
)
def m5465a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5465a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5465a4(c: Cast) -> None:
    """One or two allies swing, so this row declares no target and names the
    victim of each basic attack explicitly -- "against different targets" is
    the reason the second cannot be left to default."""
    mates = sorted(
        mate
        for mate in c.within(10, side="ally")
        if mate != c.me
        and (c.is_kind("earth", on=mate) or c.is_kind("fire", on=mate))
    )
    if not mates:
        return
    struck: set[int] = set()
    for mate in mates[:2]:
        victims = sorted(
            foe
            for foe in c.enemies()
            if foe not in struck and distance_between(c.world, mate, foe) <= 1
        )
        if not victims:
            continue
        aim = c.choose(victims, "m5465a4: what it is set on")
        if aim is not None:
            struck.add(aim)
            c.basic(who=mate, on=aim)


_M5465_SCORCHED = "it takes fire damage"


def _burnt_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and DamageType.FIRE in ev.types()


@power(
    "m5465a5",
    level=13,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.THUNDER],
    trigger=_M5465_SCORCHED,
    on=Trigger(DamageApplied, when=_burnt_me, text=_M5465_SCORCHED),
)
def m5465a5(c: Cast) -> None:
    """"Each creature adjacent to it" is everybody, friend as well as foe,
    and the ten is one packet of two types -- which is `dtypes`, not two
    calls that would each be resisted."""
    for who in sorted(c.within(1)):
        if who != c.me:
            c.flat(10, dtypes=(DamageType.FIRE, DamageType.THUNDER), on=who)


# ==========================================================================
# m5522
# ==========================================================================


@power(
    "m5522a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d6", 7),
)
def m5522a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5522a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m5522a1(c: Cast) -> None:
    """"Cold and necrotic damage" is one packet of two types and a `Damage`
    holds one, so the first printed type is kept -- the approximation the
    levels below settled on for this shape."""
    if c.strike():
        c.hit()


@power(
    "m5522a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(5),
    target=UpTo(2),
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("4d6", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5522a2(c: Cast) -> None:
    """"One or two creatures in the burst marked by it" is a count `Target`
    can say and a restriction it cannot, so the aim is narrowed here and
    redirected rather than thrown away."""
    victim = _restricted_to(c, 5, lambda who: c.marked(who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.pull(4, on=victim)
    c.prone(on=victim)


@power(
    "m5522a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5522a3(c: Cast) -> None:
    """No attack roll: the mark and the grant are the whole printed Effect.
    "A creature", not an enemy -- but the chooser hands back enemies first,
    so nothing is narrowed here."""
    c.mark(until=When.EONT)
    c.grants_advantage(until=When.EONT, to="me")


_M5522_LOOKED_AWAY = (
    "an enemy marked by it and within 6 squares attacks without including it"
)


@power(
    "m5522a4",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[
        Keyword.FIRE,
        Keyword.NECROTIC,
        Keyword.TELEPORTATION,
        Keyword.WEAPON,
    ],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("3d10", 3, dtype=DamageType.FIRE),
    trigger=_M5522_LOOKED_AWAY,
    on=Trigger(
        AttackDeclared,
        when=both(_marked_swung_elsewhere(6), leaves_me_out),
        text=_M5522_LOOKED_AWAY,
    ),
)
def m5522a4(c: Cast) -> None:
    """The step is a printed Effect and happens before the swing, so it is
    taken whether or not the blow lands. "Fire and necrotic damage" is one
    packet of two types and a `Damage` holds one, so the first is kept.

    An interrupt rather than a reaction: the card says so, and the step is
    what puts the m5522 in reach of a creature six squares off.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    _put_beside(c, c.me, foe)
    if c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m5547
# ==========================================================================


@power(
    "m5547a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5547a0(c: Cast) -> None:
    """The hold goes on when a creature comes in and off when it leaves,
    which is `_aura`'s whole shape -- and the printed line lasts exactly as
    long as the creature is inside."""
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and team(c.world, who) is not team(c.world, me)

    _aura(c, 2, eligible, lambda who: c.cannot_shift(until=When.ENCOUNTER, on=who))


@power(
    "m5547a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5547a1(c: Cast) -> None:
    """A penalty takes no `kind=`, so the four defences are four plain
    calls."""
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.FIRE not in ev.types():
            return
        for defended in EVERY_DEFENCE:
            c.penalty(defended, 2, until=When.EONT, on=me)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5547a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d6", 7, dtype=DamageType.COLD),
)
def m5547a2(c: Cast) -> None:
    """The Effect line marks a ring of enemies rather than the target, so it
    lands whether or not the blow did and it is not aimed at `c.target`."""
    if c.strike():
        c.hit()
    for foe in sorted(c.enemies()):
        if c.distance(foe) <= 2:
            c.mark(until=When.EONT, on=foe)


_M5547_LOOKED_AWAY = "an enemy marked by it attacks without including it"


@power(
    "m5547a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5),
    trigger=_M5547_LOOKED_AWAY,
    on=Trigger(
        AttackDeclared,
        when=both(_marked_swung_elsewhere(0), leaves_me_out),
        text=_M5547_LOOKED_AWAY,
    ),
)
def m5547a3(c: Cast) -> None:
    """The one block here that prints no distance on its mark, which is what
    `_marked_swung_elsewhere(0)` says."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.weakened(until=When.EOTNT, on=foe)


# ==========================================================================
# m5768
# ==========================================================================


@power(
    "m5768a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5768a0(c: Cast) -> None:
    """The printed hold outlasts the ring -- "until the end of its next
    turn" -- so it is laid at the moment a turn begins rather than held on
    whoever is standing inside."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def began(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.EOTNT, on=ev.actor)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} slow")


@power(
    "m5768a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5768a1(c: Cast) -> None:
    """Whatever it kills stays where it fell.

    `Dropped` carries `source` -- whoever crossed the line -- so "slain by
    it" is one field and needs no reconstruction from the log. The two ways
    the printed effect can be undone are both about a body after a fight,
    and a board has nothing for either of them to change, so nothing is
    missing here.
    """
    me = c.me

    def stilled(ev: Dropped) -> None:
        if getattr(ev, "source", None) != me or ev.actor == me:
            return
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=ev.actor)

    c.watch(Dropped, stilled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5768a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5768a2(c: Cast) -> None:
    """The mark is an Effect line and lands on a miss."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m5768a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 12, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5768a3(c: Cast) -> None:
    """The pull is the printed Effect and the swing is a second attack line
    against a different set -- "each enemy adjacent to him", which is who is
    standing there *after* the pull. So the drag happens per target and the
    attack is held back to the last one, when the whole burst has closed in.
    """
    victim = c.target
    if victim is not None:
        c.pull(2, on=victim)
    if not c.last:
        return
    for foe in sorted(c.enemies()):
        if c.adjacent(foe) and c.strike(on=foe):
            c.hit(on=foe)


_M5768_LOOKED_AWAY = (
    "an enemy marked by him and within 5 squares attacks without including him"
)


@power(
    "m5768a4",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M5768_LOOKED_AWAY,
    on=Trigger(
        AttackDeclared,
        when=both(_marked_swung_elsewhere(5), leaves_me_out),
        text=_M5768_LOOKED_AWAY,
    ),
)
def m5768a4(c: Cast) -> None:
    """"This damage ignores resistances and immunities" is `c.ignore_resistance`
    with `immunity=True`, laid on the dealer for the length of the blow and
    taken off again -- it is a property of this ten and not of everything the
    m5768 does afterwards."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    through = c.ignore_resistance(
        dtype=DamageType.NECROTIC, immunity=True, until=When.EOT, on=c.me
    )
    try:
        c.flat(10, dtype=DamageType.NECROTIC, on=foe)
    finally:
        if through is not None:
            c.world.effects.end(through, "the blow is dealt")


# ==========================================================================
# m5903
# ==========================================================================


@power(
    "m5903a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5903a0(c: Cast) -> None:
    """Insubstantial halves the damage a creature takes, so "full damage
    against insubstantial enemies" is the one flag `c.ignore_resistance`
    carries for it."""
    c.ignore_resistance(insubstantial=True, until=When.ENCOUNTER, on=c.me)


@power(
    "m5903a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m5903a1(c: Cast) -> None:
    """"Slowed and cannot shift" is two conditions on one duration, which is
    one `c.condition` call carrying both."""
    if not c.strike():
        return
    c.hit()
    c.flat(10, dtype=DamageType.COLD)
    c.condition(Condition.SLOWED, Condition.CANNOT_SHIFT, until=When.EONT)


_M5903_SWUNG_AT_A_FRIEND = "an enemy beside it attacks one of its allies"


def _neighbour_hit_my_side(world: World, me: int, ev: AttackDeclared) -> bool:
    """An enemy standing next to me is swinging at somebody on my side and
    not at me. `among` is the whole target list of the one use, which is what
    "does not include it as a target" asks and a per-target announcement
    cannot answer."""
    foe = ev.attacker
    if foe == me or team(world, foe) is team(world, me):
        return False
    if distance_between(world, me, foe) > 1:
        return False
    among = getattr(ev, "among", (ev.target,))
    if me in among:
        return False
    return any(
        who != me and team(world, who) is team(world, me) for who in among
    )


@power(
    "m5903a2",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5903_SWUNG_AT_A_FRIEND,
    on=Trigger(
        AttackDeclared, when=_neighbour_hit_my_side, text=_M5903_SWUNG_AT_A_FRIEND
    ),
)
def m5903a2(c: Cast) -> None:
    """`c.basic` with `on=` named: the victim defaults to `c.target`, which
    is None on a row that declares none, and the swing would simply not
    happen."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and alive(c.world, foe):
        c.basic(on=foe)


# ==========================================================================
# m5927
# ==========================================================================


@power(
    "m5927a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5927a0(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5927a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5927a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5927a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 3),
    charges=True,
)
def m5927a2(c: Cast) -> None:
    """A printed Effect that is a run and then a swing is a charge, and
    `charges=True` is what stops the engine measuring a sword's reach before
    the row has moved.

    "One prone creature" is narrower than any `Target` can say, so the aim
    is picked from what qualifies after the move -- which is the only moment
    it can be, because the move is what brings anybody into reach.
    """
    foes = sorted(
        foe for foe in c.enemies() if c.is_(Condition.PRONE, on=foe) and c.can_see(foe)
    )
    victim = c.choose(foes, "m5927a2: which of them it runs down") if foes else None
    if victim is None:
        return
    c.run_at(victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, on=victim)


@power(
    "m5927a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d10", 5),
)
def m5927a3(c: Cast) -> None:
    """"Creatures in the blast" is everybody standing in it and not the
    caster, which is `EACH_OTHER` -- `EACH_CREATURE` is side "any" and would
    catch the m5927 in its own blast."""
    if c.strike():
        c.hit()
        c.prone()


_M5927_BOLTED = "an enemy beside it moves more than 2 squares away"


def _bolted_from_me(world: World, me: int, ev: MoveEnd) -> bool:
    """It was beside me when it started and it is three or more away now.

    `MoveEnd` carries where the creature finished and not where it began, so
    "was adjacent" is read off the adjacency the engine announced breaking --
    which is `AdjacencyLost`, a different event. Here the gap alone is the
    test: anything that ends a move of its own three or more squares off was
    nearer than that when the move began, because a move is continuous.
    """
    who = ev.actor
    if who == me or team(world, who) is team(world, me):
        return False
    if world.turn != who:
        return False
    return distance_between(world, me, who) > 2


@power(
    "m5927a4",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5927_BOLTED,
    on=Trigger(MoveEnd, when=_bolted_from_me, text=_M5927_BOLTED),
)
def m5927a4(c: Cast) -> None:
    """m5927a2 picks its own prone target, so the triggering creature is
    knocked down first -- otherwise the row it is told to use has nobody it
    is allowed to aim at and the reaction is spent on nothing.

    That is wider than the printed line in one direction and narrower in
    none: the card says "uses m5927a2 against the triggering enemy", which
    only reads if that enemy is a legal target of it.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not alive(c.world, foe):
        return
    if not c.is_(Condition.PRONE, on=foe):
        c.prone(on=foe)
    c.use_power("m5927a2", on=foe, spend=False)


# ==========================================================================
# m6017
# ==========================================================================


@power(
    "m6017a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6017a0(c: Cast) -> None:
    """"Any living creature" is everybody not undead, friend as well as foe
    -- the printed line says creature and not enemy."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def finished(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        if _living(c, ev.actor):
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnEnd, finished, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6017a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6017a1(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if c.is_(Condition.IMMOBILIZED, on=ev.target) or c.is_(
            Condition.PRONE, on=ev.target
        ):
            c.damage("1d10", dtype=DamageType.NECROTIC, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6017a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d8", 3),
)
def m6017a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6017a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d8", 3),
)
def m6017a3(c: Cast) -> None:
    """The mark is an Effect line and lands on a miss; the vulnerability is
    a clause about what its mark *means*, so it rides on the mark's own
    duration and goes when the mark goes."""
    victim = c.target
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
    marked = c.mark(until=When.EONT, on=victim)
    weak = c.vulnerable(10, DamageType.NECROTIC, until=When.ENCOUNTER, on=victim)
    if marked is not None and weak is not None:
        marked.on_end.append(lambda: c.world.effects.end(weak, "the mark went"))


_M6017_LOOKED_AWAY = (
    "a creature marked by it and within 3 squares uses an attack power "
    "without including it"
)


@power(
    "m6017a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M6017_LOOKED_AWAY,
    on=Trigger(
        AttackDeclared,
        when=both(_marked_swung_elsewhere(3), leaves_me_out),
        text=_M6017_LOOKED_AWAY,
    ),
)
def m6017a4(c: Cast) -> None:
    """It blinks in and swings the row that lays its mark.

    The card names the attack by the weapon that makes it; this block has
    two weapon at-wills and the single-target one is the one taken, because
    it is the one whose Effect line is the mark this whole trigger is about.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    _put_beside(c, c.me, foe)
    c.use_power("m6017a3", on=foe, spend=False)


_M6017_FELL_SHORT = "its attack would miss an enemy"


def _my_attack_fell_short(world: World, me: int, ev: AttackRolled) -> bool:
    """The die is down and, as things stand, the blow misses.

    The printed trigger is "it misses an enemy", and `Miss` is announced
    after the comparison has been made -- a reroll there changes a number
    nothing reads again. `resolve.attack` sets `result.hit` *before* it
    emits `AttackRolled` and then recomputes the outcome **from the result
    object** once this window has closed, so this is the one place a reroll
    is real.
    """
    if ev.attacker != me:
        return False
    if team(world, ev.target) is team(world, me):
        return False
    result = getattr(ev, "result", None)
    return result is not None and not result.hit


@power(
    "m6017a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6017_FELL_SHORT,
    on=Trigger(AttackRolled, when=_my_attack_fell_short, text=_M6017_FELL_SHORT),
)
def m6017a5(c: Cast) -> None:
    """The Special line is a second way to get the use back, and it is a
    standing offer rather than part of this firing -- so it is armed on the
    first run and costs the m6017 thirty hit points when it is taken."""
    me = c.me
    for foe in sorted(c.enemies()):
        if c.distance(foe) <= 3:
            c.flat(15, dtype=DamageType.NECROTIC, on=foe)
    c.reroll_attack()

    def offered(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if c.ref not in c.expended(on=me):
            return
        if c.may("bleed for another", who=me):
            c.flat(30, on=me)
            c.restore_use(c.ref, on=me)

    c.watch(TurnStart, offered, until=When.ENCOUNTER, on=me, label=f"{c.ref} price")


# ==========================================================================
# m6083
# ==========================================================================


@power(
    "m6083a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6083a0(c: Cast) -> None:
    """A vulnerability is a number on the target's own `Defences` and takes
    no gate, so "while it is not bloodied" cannot be a `when=` the way a
    bonus's would be: the holds are laid while the condition is true and
    ended on the crossing, which `Bloodied` announces.

    One direction only. Healed back above half the m6083 does not get the
    aura back; nothing on a board emits the crossing in reverse, and the
    printed sentence is about a creature that has been hurt.
    """
    me = c.me
    whole: dict[str, bool] = {"yes": _not_bloodied(c.world, me)}

    def eligible(who: int) -> bool:
        return (
            whole["yes"]
            and who != me
            and team(c.world, who) is not team(c.world, me)
        )

    def hold(who: int) -> Effect | None:
        return c.vulnerable(5, DamageType.COLD, until=When.ENCOUNTER, on=who)

    _aura(c, 3, eligible, hold)

    def bled(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        whole["yes"] = False
        for who in sorted(c.enemies()):
            for eff in list(c.world.effects.of(who)):
                if eff.source == me and eff.label == c.ref:
                    c.world.effects.end(eff, "it is bloodied")

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{c.ref} wound")


@power(
    "m6083a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6083a1(c: Cast) -> None:
    """"-2 to attack rolls against it" covers every defence, so it is written
    as +2 to each -- and the gate is read when the blow arrives, because
    `resolve.attack` hands the attack context to `defence`, so a `when=` on a
    defence modifier is asked at exactly the right moment."""
    me = c.me
    for defended in EVERY_DEFENCE:
        c.bonus(
            defended,
            2,
            until=When.ENCOUNTER,
            on=me,
            when=lambda ctx: _not_bloodied(c.world, me),
        )


@power(
    "m6083a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7, dtype=DamageType.COLD),
)
def m6083a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m6083a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 4, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
    requires=_bloodied,
    requires_text="it must be bloodied",
)
def m6083a3(c: Cast) -> None:
    """Both branches written out: `half_on_miss` is declared data that no
    line of the engine reads, and the Miss line here carries a hold of its
    own as well as the half damage.

    The Aftereffect belongs to the Hit's hold and not to the Miss's, which
    is why it is appended inside that branch only.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        hold = _burn_and_hold(
            c, victim, 10, DamageType.COLD, conditions=(Condition.IMMOBILIZED,)
        )
        hold.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))
    else:
        c.hit(half=True)
        _burn_and_hold(
            c, victim, 5, DamageType.COLD, conditions=(Condition.SLOWED,)
        )
