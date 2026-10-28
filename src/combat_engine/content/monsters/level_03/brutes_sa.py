"""Monster abilities, level 3, brutes: the second sweep.

`brutes.py` beside this file holds the first sweep of this level; the split is
by *when* the work was done rather than by what the creatures are. The
conventions are that file's and the level-1 and level-2 sweeps':

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=8)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold it
  for the rest of the fight;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`;
* a secondary attack is rolled with `c.attack(world.scaling.trim(n, level), ...)`
  because only the primary line fits in the header.

Fourteen helpers are imported rather than copied. Six printed sentences on
these cards are word for word ones already written for another role or another
level -- an aura that tolls as a turn closes, a swarm's shared square, "it
makes two X attacks", "an ally adjacent to the target may swing", a reaction
shift when a melee attack misses, and the underwater trait.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_01.artillery_sa import (
    _is_bloodied,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.minions_sa import _MISSED_ME_MELEE
from combat_engine.content.monsters.level_01.skirmishers_sa import _elemental_hurt
from combat_engine.content.monsters.level_02.controllers_sa import (
    _let_it_swing_without_moving,
)
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _has_an_opening,
    _twice,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import (
    _ends_turn_in_aura,
    _melee_only,
    _until_escape,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _free_square_beside,
    _holding_nobody,
)
from combat_engine.content.monsters.level_03.brutes import _holding, _same_row
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _ongoing_of,
    _shoved_by_hand,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Health,
    Ident,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Size,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Healed,
    Hit,
    Miss,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_keyword,
    by_melee,
    hits_me,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

#: "When missed by a melee attack, it shifts 1 square." Three blocks here.
_MISSED_IN_MELEE = _MISSED_ME_MELEE


def _while_bloodied(c: Cast):  # noqa: ANN202
    """A gate on the caster's own bloodied state, for a standing modifier.

    Asked as the roll is looked up rather than armed and disarmed by a pair of
    watches: the creature can be healed back above the line, and a bonus laid
    once on `Bloodied` would never come off again.
    """
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return _is_bloodied(c.world, me)

    return hurt


def _kin_beside(c: Cast, victim: int | None, ref: str) -> list[int]:
    """Others off the same stat block standing next to that creature.

    `_kin` in `brutes.py` measures from the caster; several cards here count
    around the *target* instead, which is a different question.
    """
    if victim is None:
        return []
    return [
        a
        for a in c.within(1, of=victim, side="ally")
        if a != c.me and _same_row(c, a, ref)
    ]


def _press(c: Cast, reach: int = 1) -> list[int]:
    """Enemies within `reach` of the caster."""
    return [foe for foe in c.enemies() if c.distance(foe) <= reach]


def _claws_then_bite(c: Cast, claw: str, bite: str) -> None:
    """"It makes two claw attacks. If it hits a single target with both, it
    makes a bite attack against the same target."

    `ONE_CREATURE` rather than `UpTo(2)`: the rider is the whole content of the
    card and it only exists when both swings went to one creature, so letting
    the chooser spread them would be offering a line that can never pay out.
    """
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power(claw, on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        c.use_power(bite, on=victim)


def _both_hit(c: Cast, first: str, second: str) -> bool:
    """Two named rows at one creature; True when both landed."""
    victim = c.target
    if victim is None:
        return False
    landed = 0
    for ref in (first, second):
        c.use_power(ref, on=victim)
        if c.landed:
            landed += 1
    return landed == 2


def _recharge_and_fire(c: Cast, ref: str) -> None:
    """"That power recharges, and the creature uses it immediately."

    The use is handed the row directly rather than waiting for the die, which
    is what "immediately" means; `c.restore_use` first, because the row has
    been spent and `dsl.use` would refuse it.
    """
    c.restore_use(ref, on=c.me)
    c.use_power(ref)


def _breath(c: Cast) -> None:
    """A cold blast that slows and weakens on one saving throw.

    One effect carrying both conditions: applied separately the victim gets
    two saves and shakes off half of what the card calls one thing.
    """
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS
        )


def _my_crit(world: World, me: int, ev: Hit) -> bool:
    """This creature scored a critical hit -- and not with the swing this very
    row handed it, which would answer its own trigger forever."""
    if getattr(ev, "attacker", None) != me:
        return False
    if getattr(ev, "granted_via", "") in ("m3547a2",):
        return False
    result = getattr(ev, "result", None)
    return result is not None and result.critical


def _struck_me_from_within_two(world: World, me: int, ev: Hit) -> bool:
    """"An enemy within 2 squares of it hits it with an attack."

    `enemy_within` reads the event's `actor`, which an attack does not carry --
    the attacker is in `attacker` -- so the distance is measured here.
    """
    who = getattr(ev, "attacker", None)
    if who is None or getattr(ev, "target", None) != me:
        return False
    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 2


def _enemy_closed_on_me(world: World, me: int, ev: AdjacencyGained) -> bool:
    """"When an enemy moves adjacent to it." `mover` is the half that matters:
    without it the row also fires when the creature closed the gap itself,
    which is not the printed sentence and is true about half the time."""
    if ev.actor != me or ev.mover != ev.other:
        return False
    return team(world, ev.other) is not team(world, me)


# --------------------------------------------------------------------------
# m1048
# --------------------------------------------------------------------------


@power(
    "m1048a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 8),
)
def m1048a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1048a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 8),
)
def m1048a1(c: Cast) -> None:
    """"Prior to the attack, one can shift 1 square."

    Read as an ally, not as the creature itself: the sibling row below spells
    "one ally adjacent to the target" out in full, and this block's whole
    character is moving its own side around. The step is taken before the
    swing because that is the order printed, and once for the use rather than
    once per target.
    """
    if c.first:
        mates = [a for a in c.within(5, side="ally") if a != c.me]
        if mates:
            c.shift(1, who=mates[0])
    if c.strike():
        c.hit()


@power(
    "m1048a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d10", 8, kind=LIMITED),
)
def m1048a2(c: Cast) -> None:
    """`c.grant_attack` rather than `c.basic`: the +2 belongs to the swing being
    handed over, and nothing else can put a bonus on somebody else's roll."""
    if c.strike():
        c.hit()
        victim = c.target
        mates = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
        if victim is not None and mates:
            c.grant_attack(mates[0], on=victim, attack_bonus=2)


# --------------------------------------------------------------------------
# m115817
# --------------------------------------------------------------------------


@power(
    "m115817a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 7),
)
def m115817a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115817a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("3d6", 7, half_on_miss=True),
)
def m115817a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m115817a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature that is not grabbed",
        conditions_without=frozenset({Condition.GRABBED}),
    ),
    attack=Attack(vs=REF, printed=6),
    # Stays: this is about the **caster** not already holding somebody, which
    # is a different sentence from the target restriction above.
    requires=_holding_nobody,
    requires_text="it must not be grabbing a creature",
)
def m115817a2(c: Cast) -> None:
    """"One creature that isn't grabbed" is `conditions_without`, and
    deliberately **not** `relation=GRABBED_BY, without=True`: that spells "not
    grabbed *by it*", which a creature held by somebody else passes. The
    printed escape DC is a fixed number the grab does not carry."""
    if c.strike():
        c.grab(dc=13)


# --------------------------------------------------------------------------
# m1402
# --------------------------------------------------------------------------


@power(
    "m1402a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m1402a0(c: Cast) -> None:
    """Two damage expressions, so only the untyped one fits in the header; the
    cold die is rolled beside it. `c.charge` has a sibling in `c.opportunity`
    and it is the printed condition on the third die."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)
        if c.opportunity:
            c.damage("1d6", dtype=DamageType.COLD)


@power(
    "m1402a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m1402a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1402a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1402a2(c: Cast) -> None:
    _claws_then_bite(c, "m1402a1", "m1402a0")


@power(
    "m1402a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("3d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m1402a3(c: Cast) -> None:
    _breath(c)


@power(
    "m1402a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1402a4(c: Cast) -> None:
    _recharge_and_fire(c, "m1402a3")


@power(
    "m1402a5",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=4),
)
def m1402a5(c: Cast) -> None:
    """The stun plays. An Aftereffect fires when the save *succeeds* and the
    condition ends, which is the one moment nothing announces: `escalate` is
    the opposite half -- it answers a save that failed."""
    if c.strike():
        victim = c.target
        held = c.stunned(until=When.EONT)
        c.aftereffect(held, lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))

# --------------------------------------------------------------------------
# m1659
# --------------------------------------------------------------------------


@power(
    "m1659a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
    dropped=("spec.ref",),
)
def m1659a0(c: Cast) -> None:
    """The third damage die is conditional on a creature being "under the
    effects of" another card, and the extraction prints that card as prose
    where every other block in this file prints a ref -- so there is no ref to
    ask about and guessing one would read a different power's effect."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)


@power(
    "m1659a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.COLD],
)
def m1659a1(c: Cast) -> None:
    _twice(c, "m1659a0")


@power(
    "m1659a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d8", 1, dtype=DamageType.COLD),
    no_provoke=True,
)
def m1659a2(c: Cast) -> None:
    """The printed range is measured from the object, and the body says
    nothing because the header and `m1659a5` between them already do.

    **The marker came off without this row gaining a line, which is the
    part worth recording.** It waited on `c.conjure(defences_of=)` and the
    reasoning was that the object this range is taken from did not exist.
    It does now -- `m1659a5` puts it there -- and the *origin* half needed
    no new facility at all: `c.cast_from` has lent a square to a ranged
    line since #614, and `dsl.measured_from` reads it before `legal()`
    decides what may be aimed at. So the relation is established by the row
    that creates the object, and this row is an ordinary ranged attack.

    Two things that follow from `measured_from` rather than from here, so
    nobody looks for them in this body: the distance falls back to the
    creature's own square whenever the object has left the board, which is
    the honest reading of a range whose origin is gone; and only a ranged,
    burst or wall line borrows, so the block's close burst is untouched.

    The earlier note here said marking this with the sibling's ref was
    tried and is wrong -- `todo.py` reads a declared ref as a symbol that
    has **arrived**, and `m1659a5` was declared as a marked row. That is
    still true and is still the reason this carried a verb's name instead."""
    if c.strike():
        c.hit()


@power(
    "m1659a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m1659a3(c: Cast) -> None:
    """The Miss line is a shorter shove rather than half the damage, so it is
    written out instead of declared with `half_on_miss`."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
    else:
        c.push(1)


@power(
    "m1659a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1659a4(c: Cast) -> None:
    _recharge_and_fire(c, "m1659a3")


@power(
    "m1659a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1659a5(c: Cast) -> None:
    """The creature shares its hit points with an object: attacking either hurts
    the creature, the object's defences copy the creature's, it resists 5 of
    everything, and it is destroyed when the creature falls.

    **One symbol, not two, and the one that went is the interesting half.**
    `c.conjure(defences=)` puts an attackable thing on the board (#714) and
    `c.resist` gives it the 5 -- but `defences=` takes one flat number for
    all four, and this card copies the **creature's** four, which differ
    from each other. That is `defences_of=`, a distinct symbol because
    `blocked.py` resolves a parameter name it can see on the signature as
    existing and would report this row ready.

    **`Health.shared_with` is retired: the routing it names exists.** This
    said *"nothing routes damage that landed on one creature into another's
    `Health`"*, and `m3039a4` does exactly that, one directory away --

        ev.amount -= share
        c.flat(share, dtype=ev.dtype, on=friend)

    off a `c.watch(DamageRolled, ...)`, with its own docstring explaining
    why it works: `Hit` is announced before the damage is rolled and
    `DamageRolled` carries a **mutable `amount`**. `m3039a5` goes further
    and takes the remainder over with `c.absorb`.

    That row **splits** -- half here, half there -- where this card
    **mirrors**: the blow lands in full on whichever was aimed at and in
    full in the other pool. Same watcher with the decrement left out. So
    the symbol named a *field* when what this clause needs is a watch it
    can already write, which is the shape #780's
    `c.pre_empt(damage_of=)` turned out to have as well. #846.

    **Written. `c.conjure(defences_of=)` is the half that landed** (#846):
    it copies a creature's four defences where `defences=` takes one flat
    number for all of them.

    **It redirects rather than mirrors, which corrects the paragraph
    above.** That argued the clause "mirrors -- the blow lands in full on
    whichever was aimed at and in full in the other pool". The card names
    **one** pool: *"attacking either damages the m1659"*, and the object is
    given no hit points of its own -- it is "also destroyed" when the
    creature falls rather than when it runs out. So damage aimed at the
    object moves onto the creature and is zeroed where it landed, which is
    `m3039a4`'s watcher with the share set to the whole amount.

    `c.conjure`'s one hit point is therefore never spent: the watch empties
    `ev.amount` before anything can take it off the object, which is why
    the object does not simply die to the first blow.

    The destruction half is its own watch on the creature's `Dropped`, and
    `c.dispel` serves it: *"destroy a zone or a conjuration, and unwind
    what it was holding."*

    **A note on proving this, because two probes of mine said it was
    broken.** The creature carries **cold resist 15**, so a 12-point cold
    test blow is absorbed whole and nothing reaches it -- the redirect
    looks dead and is not. `c.flat` is also *"damage that is not rolled"*
    and emits no `DamageRolled`, so using it as the incoming blow misses
    the watch entirely. Measure with `resolve.deal_damage` and an
    **untyped** blow."""
    me = c.me
    anchor = c.conjure(defences_of=me, label=c.ref,
                    until=When.ENCOUNTER, sustain=None)
    # "resist 5 all" -- `dtype=None` is every type, which is the default
    # and what the card says.
    c.resist(5, on=anchor, until=When.ENCOUNTER)

    def onto_the_creature(ev: Any) -> None:
        if getattr(ev, "target", None) != anchor or ev.amount <= 0:
            return
        # **The object's own resistance has to be applied here.**
        # `DamageRolled` is announced *before* resistance is taken off, so
        # moving the raw amount hands the creature the unreduced blow --
        # measured at 12 where the card gives 7. Read off the object
        # rather than written as a 5 twice: `c.resist` above is the one
        # place the number lives, and an all-types resist is expanded to
        # every member, so a plain lookup finds it.
        soak = c.resistances(on=anchor).get(ev.dtype, 0)
        moved, ev.amount = max(0, ev.amount - soak), 0
        if moved:
            c.flat(moved, dtype=ev.dtype, on=me)

    c.watch(DamageRolled, onto_the_creature, until=When.ENCOUNTER, on=anchor,
            label=c.ref)

    def falls(ev: Any) -> None:
        c.dispel(anchor)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, once=True,
            label=c.ref)

    # **`m1659a2` is measured from this thing, so the square is lent here.**
    # Its printed range names this object as the origin, and
    # `dsl.measured_from` already reads a lent square for a ranged line --
    # so the sibling needs no body of its own, and the relation belongs to
    # the row that puts the object on the board rather than to the row that
    # aims from it. Falls back to this creature's own square whenever the
    # object is gone, which is the proviso `cast_from` carries.
    c.cast_from(anchor, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m3192
# --------------------------------------------------------------------------


def _kin_m2598_landed(world: World, me: int, ev: Hit) -> bool:
    """An adjacent ally off the stat block the card names landed a blow.

    The card also names a power, and names one belonging to *this* block
    rather than to that one, which is extraction noise -- so the trigger is
    narrowed to who swung and not to what with.
    """
    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    ident = world.get(who, Ident)
    if ident is None or ident.ref != "m2598":
        return False
    return distance_between(world, me, who) <= 1


@power(
    "m3192a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m3192a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3192a1",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an adjacent ally of its own sort lands a blow",
    on=Trigger(Hit, _kin_m2598_landed, "an adjacent ally of its own sort hits"),
)
def m3192a1(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.basic(on=victim)


@power(
    "m3192a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    requires=_has_an_opening,
    requires_text="it must have combat advantage against a creature",
)
def m3192a2(c: Cast) -> None:
    """The Requirement is combat advantage, which is about the board rather than
    about the target line, so it is a `requires=` and not a marker."""
    if c.strike():
        c.ongoing(5)


@power(
    "m3192a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3192a3(c: Cast) -> None:
    """Untyped: a stat block prints a bare "+2 bonus", and two untyped bonuses
    stack where two of a kind would not."""
    hurt = _while_bloodied(c)
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=hurt)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=hurt)


# --------------------------------------------------------------------------
# m3534
# --------------------------------------------------------------------------


@power(
    "m3534a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3534a0(c: Cast) -> None:
    _ends_turn_in_aura(c, 1, 2)


@power(
    "m3534a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3534a1(c: Cast) -> None:
    """Four clauses, and the fourth is already true of the grid.

    Sharing its square lives on the creature being entered rather than on the
    mover. The shove immunity is gated: `c.immovable` would refuse a push from
    anywhere and the printed line refuses only melee and ranged attacks, so it
    is written as a shortening large enough to swallow any of them, with the
    reach read off the row that shoved. Squeezing through a Tiny opening needs
    nothing -- the narrowest gap the grid has is one square.
    """
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand, on=c.me)


@power(
    "m3534a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 3),
)
def m3534a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3547
# --------------------------------------------------------------------------


@power(
    "m3547a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 3),
)
def m3547a0(c: Cast) -> None:
    """One expression or the other, not a bonus on top of the first: written as
    a gated +1d12 the two would be read as one modifier and the larger would
    win in the wrong direction."""
    if c.strike():
        if _is_bloodied(c.world, c.me):
            c.damage("2d12", 3)
        else:
            c.hit()


@power(
    "m3547a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 3),
    instead_of_basic="charge",
    dropped=("Power.standing",),
)
def m3547a1(c: Cast) -> None:
    """The swing is exact, and one of the two loose clauses is written.

    **`c.as_basic(charge=)` was never the gap, and the parameter was not
    either.** `c.as_basic(window="charge")` has always existed and
    `Cast.charge_at` asks `dsl.basic_options(world, runner, "charge", ref)`,
    so the filing works. What was wrong was the **door**: the verb files the
    substitution from a *body*, which runs when the row is used -- after the
    charge menu has been built -- and this clause is a standing property of
    the row's own card. `instead_of_basic="charge"` is the header twin, the
    same shape `basic=` is in, read by `basic_options` off the registry.
    Three rows carried the marker; #677's split is what surfaced them.

    **`c.as_basic(charge=)` was never a gap.** `c.as_basic(window=)` is the
    parameter, `"charge"` is one of the four words its own docstring lists,
    and `Cast.charge_at` asks `dsl.basic_options(world, runner, "charge",
    ref)` -- so a stand-in filed under that window is offered on the charge
    menu and nowhere else. Three rows carried the marker; found by #677's
    split, which put all three in the "wants an ARGUMENT on a verb that
    exists" bucket.

    "While bloodied its movement during a charge does not provoke" is sayable
    now -- `c.no_provoke(when=)` is handed `ctx["move_kind"]`, `"charge"`
    for a charge step, so the gate is one lambda. What it has nowhere to be
    *armed* from: the clause is standing, and `turns.arm_traits` arms only
    `action=NONE` rows. This stat block has none, and laying it from this
    body is too late by construction -- a charge's movement happens before
    the attack it ends in, so the very charge the clause is about has already
    provoked. Hence a header field rather than a verb.

    The printed Requirement is a particular weapon. It is left unmarked: the
    stat block always has it, so the gate is true in every fight.
    """
    if c.strike():
        c.hit()
        c.damage("1d8")


@power(
    "m3547a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it scores a critical hit",
    on=Trigger(Hit, _my_crit, "it scores a critical hit"),
    defect="the printed attack line names no defence",
)
def m3547a2(c: Cast) -> None:
    """The swing is the whole of what the card does. The attack line above it
    extracted as a bonus against no defence at all -- a compendium defect, not
    a defence to invent."""
    near = _press(c)
    if near:
        c.basic(on=near[0])


@power(
    "m3547a3",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_IN_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_IN_MELEE),
)
def m3547a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4200
# --------------------------------------------------------------------------


@power(
    "m4200a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m4200a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4200a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4200a1(c: Cast) -> None:
    _twice(c, "m4200a0")


@power(
    "m4200a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("2d6", 3, kind=LIMITED),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4200a2(c: Cast) -> None:
    """The burst plays and the zone is laid. What the zone *is* -- lightly
    obscured -- has nowhere to live: `c.zone` carries difficult terrain and a
    sight block, and an obscurement is neither."""
    if c.first:
        c.zone(spread({c.here}, 2), until=When.ENCOUNTER, label=c.ref,
               obscured="dim")
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4226
# --------------------------------------------------------------------------


def _hit_a_bloodied_foe_in_melee(world: World, me: int, ev: Hit) -> bool:
    """"When it hits a bloodied enemy with a melee attack."

    The bite this fires is itself a melee attack on a bloodied enemy, so the
    row is excluded from its own trigger; otherwise one hit feeds itself
    forever.
    """
    if getattr(ev, "attacker", None) != me:
        return False
    if getattr(ev, "power", "") == "m4226a1":
        return False
    victim = getattr(ev, "target", None)
    if victim is None or not _is_bloodied(world, victim):
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind == "melee"


@power(
    "m4226a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m4226a0(c: Cast) -> None:
    if c.strike():
        if _is_bloodied(c.world, c.me):
            c.damage("1d8", 8)
        else:
            c.hit()


@power(
    "m4226a1",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d6", 1),
    trigger="it hits a bloodied enemy with a melee attack",
    on=Trigger(
        Hit, _hit_a_bloodied_foe_in_melee, "it hits a bloodied enemy in melee"
    ),
)
def m4226a1(c: Cast) -> None:
    """Aimed off the trigger rather than off `c.target`: "the same target" is
    whoever the triggering blow landed on, and an immediate action's own target
    list names somebody it never touched."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    if c.strike(on=victim):
        if _is_bloodied(c.world, c.me):
            c.damage("1d6", 4, on=victim)
        else:
            c.hit(on=victim)


@power(
    "m4226a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4226a2(c: Cast) -> None:
    """Who is standing next to it changes whenever anybody moves, so this is a
    gated modifier read as the blow is rolled rather than a bonus put on and
    taken off by a pair of adjacency watches."""

    def pressed(ctx: dict[str, Any]) -> bool:
        return _melee_only(ctx) and len(_press(c)) >= 2

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=pressed)


# --------------------------------------------------------------------------
# m4247
# --------------------------------------------------------------------------


@power(
    "m4247a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("", 5, kind=MINION),
)
def m4247a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if _kin_beside(c, c.target, "m4247"):
            c.prone()


@power(
    "m4247a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 4, kind=MINION),
)
def m4247a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4247a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4247a2(c: Cast) -> None:
    """Read off the damage context, which carries `advantage`: asking the board
    again is too late, because a one-shot grant has already been spent by the
    time the blow is rolled."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# --------------------------------------------------------------------------
# m4312
# --------------------------------------------------------------------------


@power(
    "m4312a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m4312a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4312a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m4312a1(c: Cast) -> None:
    """`charges=True` or the engine measures reach before the run and refuses
    the row whenever the target is further off than an arm -- which is every
    situation a charge is for. The run carries the first claw; the second is an
    ordinary use of the same row."""
    victim = c.target
    if victim is None:
        return
    c.charge_at(victim, "m4312a0")
    c.use_power("m4312a0", on=victim)


@power(
    "m4312a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3),
)
def m4312a2(c: Cast) -> None:
    """The secondary attack is rolled with the level taken back out by hand --
    only the primary line fits in the header -- and its payload is written.

    **It was a parameter rather than a mechanism, which the old shared
    symbol hid.** `c.forbid` already took `ref=`, `keyword=`, `lacking=`,
    `usage=` and `attacks_only=`; *"the target can only make a melee basic
    attack"* needs **"all but this one"**, which none of them said.
    `only=` is that, and it bars every other **attack** row while leaving a
    heal or a buff alone -- which is what the card says and not a word more.

    `Condition.SHAPED` is not it, and it is the near miss: that is
    `no_standard=True` and nothing else, so it would take away the melee
    basic attack this card explicitly leaves. Nor is a veto at
    `AttackDeclared` -- the printed line narrows the *choice*, and refusing
    after the fact spends the action and throws it away. The bar belongs
    where the menu is built, which is `dsl.usable`.

    "Until the end of its next turn" is the target's clock, so
    `When.EOTNT`. #733."""
    if c.strike():
        c.hit()
        if c.attack(c.world.scaling.trim(5, c.level), WILL):
            c.forbid(only="mba", until=When.EOTNT)


@power(
    "m4312a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("spec.ref",),
)
def m4312a3(c: Cast) -> None:
    """The bonus plays. The parenthetical half sets off another stat block's
    attack, and the extraction prints that block as prose where a ref belongs,
    so there is nothing to reach for."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=_while_bloodied(c))


# --------------------------------------------------------------------------
# m4684
# --------------------------------------------------------------------------


@power(
    "m4684a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 6),
)
def m4684a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4684a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 6),
)
def m4684a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m4684a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("1d10", 6, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m4684a2(c: Cast) -> None:
    """"Any at-will melee attack power", which is wider than a basic attack, so
    the ally's own rows are read and one of them is used; the basic is the
    fallback for an ally that has none.

    The printed "Recharge when first bloodied" is armed on top of the die in
    the header: the number is what `actions.recharge` rolls and what the card
    shows, and the two only ever agree to make the row available sooner.
    """
    _recharge_when_bloodied(c)
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(3)
    mates = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    if not mates:
        return
    ally = mates[0]
    rows = c.borrowed_rows(ally, at_will=True, melee=True)
    if rows:
        c.use_power(rows[0], who=ally, on=victim)
    else:
        _let_it_swing_without_moving(c, ally)


@power(
    "m4684a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d10", 5, kind=LIMITED),
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m4684a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


# --------------------------------------------------------------------------
# m4738
# --------------------------------------------------------------------------


@power(
    "m4738a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 5),
)
def m4738a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4738a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m4738a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4738a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=6),
)
def m4738a2(c: Cast) -> None:
    """The header's attack line is the *secondary* one, because that is the
    only roll this row makes itself: the two primaries are the other two rows,
    used in turn.

    What a landed secondary does is written now -- `x5_23` is a row since
    #389, and `c.strike()` has to be *tested* rather than called for its own
    sake, which is what hid the clause here."""
    if _both_hit(c, "m4738a0", "m4738a1") and c.strike():
        c.contract("x5_23")


@power(
    "m4738a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m4738a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4738a4",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_IN_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_IN_MELEE),
)
def m4738a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4744
# --------------------------------------------------------------------------


@power(
    "m4744a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 3, dtype=DamageType.NECROTIC, kind=MINION),
)
def m4744a0(c: Cast) -> None:
    """Ongoing damage of one type does not stack -- the highest applies -- so
    "if it is already taking ongoing necrotic damage, increase it by 2" is one
    burn computed from the standing one, not two burns laid side by side."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    standing = _ongoing_of(c, victim, DamageType.NECROTIC)
    c.ongoing(standing + 2 if standing else 2, DamageType.NECROTIC)


@power(
    "m4744a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4744a1(c: Cast) -> None:
    """"Double damage" written as a gated +3, which is what doubling is for a
    creature whose damage is the flat 3 in its own header. Nothing multiplies a
    blow, and a multiplier would be the wrong shape anyway: the printed number
    is fixed and so is its double."""

    def crowded(ctx: dict[str, Any]) -> bool:
        return len(_kin_beside(c, ctx.get("target"), "m4744")) >= 3

    c.bonus(
        "damage",
        3,
        on=c.me,
        until=When.ENCOUNTER,
        dtype=DamageType.NECROTIC,
        when=crowded,
    )


# --------------------------------------------------------------------------
# m5064
# --------------------------------------------------------------------------


@power(
    "m5064a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5064a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m5064a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m5064a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5064a2",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d6", 4, kind=LIMITED),
    trigger="an enemy within 2 squares hits it",
    on=Trigger(Hit, _struck_me_from_within_two, "an enemy within 2 hits it"),
)
def m5064a2(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.strike(on=attacker):
        c.hit(on=attacker)


# --------------------------------------------------------------------------
# m5068
# --------------------------------------------------------------------------


@power(
    "m5068a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 5, kind=MINION),
)
def m5068a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EOTNT)


@power(
    "m5068a1",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=6),
    trigger="an enemy moves adjacent to it",
    on=Trigger(
        AdjacencyGained, _enemy_closed_on_me, "an enemy moves adjacent to it"
    ),
)
def m5068a1(c: Cast) -> None:
    """Aimed at the creature the event is about. The card names a different
    block in its trigger line, which is extraction noise -- the sentence is
    about whoever closed on *this* creature."""
    victim = getattr(c.trigger, "other", None)
    if victim is not None and c.strike(on=victim):
        c.teleport(1, who=victim)


# --------------------------------------------------------------------------
# m5140
# --------------------------------------------------------------------------


@power(
    "m5140a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 5, kind=MINION),
)
def m5140a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5140a1",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("", 10, dtype=DamageType.ACID, kind=MINION),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5140a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5140a2",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it takes acid, cold, fire, lightning or thunder damage",
    on=Trigger(
        DamageApplied, _elemental_hurt, "it takes damage of an elemental kind"
    ),
)
def m5140a2(c: Cast) -> None:
    """The resistance is to whichever type arrived, read off the event rather
    than guessed: the predicate has already made sure it is one of the five."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(10, dtype, until=When.ENCOUNTER, on=c.me)


# --------------------------------------------------------------------------
# m5308
# --------------------------------------------------------------------------


@power(
    "m5308a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m5308a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5308a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m5308a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5308a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5308a2(c: Cast) -> None:
    """"Whether or not it moves" -- the walk is offered and the two swings
    happen regardless, so the move is not guarded by its own success."""
    c.move(c.speed_of())
    if _both_hit(c, "m5308a0", "m5308a1"):
        c.prone()


# --------------------------------------------------------------------------
# m5400
# --------------------------------------------------------------------------


@power(
    "m5400a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 7),
)
def m5400a0(c: Cast) -> None:
    if c.strike():
        if c.bloodied():
            c.damage("3d6", 7)
        else:
            c.hit()


@power(
    "m5400a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m5400a1(c: Cast) -> None:
    _twice(c, "m5400a0")


@power(
    "m5400a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 3, dtype=DamageType.LIGHTNING),
)
def m5400a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5400a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 7, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5400a3(c: Cast) -> None:
    """The heal is a plain number rather than a surge: a monster spends one
    only when its own card says so, and this one does not."""
    if c.strike():
        c.hit()
        if c.bloodied():
            c.heal(5, on=c.me)


@power(
    "m5400a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=5),
)
def m5400a4(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is the whole of this side,
    which is `to="team"` -- the caster and its allies, where `"ally"` would
    leave the creature that did it out."""
    if c.strike():
        c.push(2)
        c.slowed(until=When.EONT)
        c.grants_advantage(until=When.EONT, to="team")


# --------------------------------------------------------------------------
# m5803
# --------------------------------------------------------------------------


@power(
    "m5803a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5803a0(c: Cast) -> None:
    """Who is inside is asked as each turn opens rather than kept as a list:
    the aura travels with the creature and a stored membership would be stale
    the moment either of them moved. `When.EOT` is "during that turn"."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def pinned(ev: TurnStart) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > 1:
            return
        c.cannot_shift(on=ev.actor, until=When.EOT)

    c.watch(TurnStart, pinned, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5803a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 7, dtype=DamageType.FIRE),
)
def m5803a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5803a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5803a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the condition and the burn, not
    two: separately the victim gets two saves for one printed sentence."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.FIRE),
        )


# --------------------------------------------------------------------------
# m5847
# --------------------------------------------------------------------------


@power(
    "m5847a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5847a0(c: Cast) -> None:
    """A standing grant read as the attack is looked up: who is adjacent to
    whom changes every time anybody moves."""

    def beside_a_friend(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(a != c.me for a in c.within(1, of=victim, side="ally"))

    c.gains_advantage(beside_a_friend, until=When.ENCOUNTER, on=c.me)


@power(
    "m5847a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 7),
)
def m5847a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5847a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d6", 10, kind=LIMITED, half_on_miss=True),
)
def m5847a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5847a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m5847a3(c: Cast) -> None:
    """The whole card is another row plus a rider on its outcome, so it rolls
    nothing of its own: `c.use_power` leaves the borrowed row's attack in
    `c.result`, which is what `c.landed` reads."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m5847a1", on=victim)
    if c.landed:
        c.damage("2d6", on=victim)
    else:
        c.flat(c.roll("1d6"), on=c.me)


# --------------------------------------------------------------------------
# m6494
# --------------------------------------------------------------------------


@power(
    "m6494a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 5),
)
def m6494a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6494a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
)
def m6494a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6494a2",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    )
def m6494a2(c: Cast) -> None:
    """"To a square adjacent to it" is a destination rather than a direction, so
    the step is given one: `c.shift(to=)` takes a square and an empty one beside
    the caster is found per ally, which also keeps two of them out of the same
    square.

    `EACH_ALLY` puts the caster in its own target list, so the creature is
    skipped explicitly -- otherwise its own step is taken twice and the printed
    "each target" moves the one creature that is not a target."""
    if c.first:
        c.shift(1)
    if c.target == c.me:
        return
    spot = _free_square_beside(c, c.me)
    if spot is not None:
        c.shift(1, who=c.target, to=spot)


@power(
    "m6494a3",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6494a3(c: Cast) -> None:
    c.use_power("m6494a1")


@power(
    "m6494a4",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it suffers an effect that a save can end",
    on=Trigger(
        ConditionApplied,
        lambda world, me, ev: ev.target == me
        and ev.duration == When.SAVE_ENDS.value,
        "it suffers an effect a save can end",
    ),
)
def m6494a4(c: Cast) -> None:
    """`ConditionApplied` is the only announcement an effect makes, so this
    catches the save-ends effects carrying a condition and misses a bare
    ongoing-damage one, which announces nothing at all."""
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m6508
# --------------------------------------------------------------------------

#: The label the third row leaves behind, which widens the first row's limit.
_SPARE_LIMB = "m6508a2"


@power(
    "m6508a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 7),
)
def m6508a0(c: Cast) -> None:
    """How many it may hold at once is two, or three once the block's last row
    has fired -- read off the hold that row leaves rather than stored anywhere
    else. "Until the grab ends" is not a `When`, so the burn is hung on the
    encounter clock and ended by the escape."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    limit = 3 if any(e.label == _SPARE_LIMB for e in c.world.effects.of(c.me)) else 2
    if len(_holding(c.world, c.me)) >= limit:
        return
    c.grab(dc=13)
    burn = c.ongoing(5, DamageType.ACID, until=When.ENCOUNTER)
    _until_escape(c, victim, burn)


@power(
    "m6508a1",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(4),
    target=Target(
        side="enemy", count=99, everyone=True,
        label="creatures grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=6),
)
def m6508a1(c: Cast) -> None:
    """Plural target line, so every creature it holds inside reach 4 is hit --
    `everyone=True` beside the relation, rather than one pick."""
    if c.strike():
        spot = _free_square_beside(c, c.me)
        if spot is not None:
            c.pull(4, to=spot)


@power(
    "m6508a2",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an arcane attack hits it",
    on=Trigger(
        Hit, both(hits_me, by_keyword(Keyword.ARCANE)), "an arcane attack hits it"
    ),
)
def m6508a2(c: Cast) -> None:
    c.effect(_SPARE_LIMB, until=When.ENCOUNTER, on=c.me)


# --------------------------------------------------------------------------
# m6515
# --------------------------------------------------------------------------


@power(
    "m6515a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 5),
)
def m6515a0(c: Cast) -> None:
    """One expression or the other, and the dice differ rather than the bonus,
    so the better line is rolled outright. `c.result.advantage` rather than
    asking the board again: a one-shot grant is already spent by now."""
    if c.strike():
        if c.result is not None and c.result.advantage:
            c.damage("3d6", 5)
        else:
            c.hit()


@power(
    "m6515a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d10", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m6515a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


# --------------------------------------------------------------------------
# m6560
# --------------------------------------------------------------------------


@power(
    "m6560a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3),
)
def m6560a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6560a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3),
)
def m6560a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
        c.shift(1)


@power(
    "m6560a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6560a2(c: Cast) -> None:
    _twice(c, "m6560a1")


# --------------------------------------------------------------------------
# m6579
# --------------------------------------------------------------------------


@power(
    "m6579a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6579a0(c: Cast) -> None:
    """Three printed clauses, and the two that look alike are different
    mechanisms:

    * in the air it heals nothing *that* turn -- state, read at the tick, so
      `unless=`, which also carries the printed "has at least 1 hit point"
      that `c.regeneration` does not ask for itself;
    * psychic switches the trait off for the whole of its next turn -- an
      event with a clock, so `c.suspend_when` with `When.EONT`. `SONT` would
      resume it just before the start-of-turn tick it is meant to miss.

    The marker here named `c.regeneration(suspended_by=)`; `c.suspend_when`
    is that facility and its own docstring says it is one verb rather than a
    kwarg on each trait. m6577a0 is the same pair with the air clause
    inverted."""
    me = c.me

    def off() -> bool:
        health = c.world.get(me, Health)
        return health is None or health.hp < 1 or c.height(on=me) > 0

    heals = c.regeneration(5, until=When.ENCOUNTER, on=me, unless=off)
    c.suspend_when(
        heals,
        DamageApplied,
        lambda ev: ev.target == me
        and DamageType.PSYCHIC in {ev.dtype, *ev.dtypes},
        for_=When.EONT,
    )


@power(
    "m6579a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4),
)
def m6579a1(c: Cast) -> None:
    """Both damage expressions are written out, because the bigger one replaces
    the smaller rather than adding to it.

    **"Melee 2 while Large" is written, and it is written on m6579a3**, the
    row that does the growing. A modifier has to be standing before the area
    is taken and an at-will attack cannot put one up for its own use, which
    the old note on that row already said -- what it gave as the reason not
    to is now false. `dsl._within_reach` no longer reads `p.reach_of(...)`
    raw: #533 moved the stretch into `dsl._reach_of`, which it and
    `actions.perform` and the policy readers all call, so the square that is
    offered is the square that may be swung at.

    `Range(alt=)` is still not the tool, for the reason the old note gave:
    that is a *choice* between two shapes, not a reach that follows a
    state."""
    if c.strike():
        if c.size_of(c.me) is Size.LARGE:
            c.damage("2d10", 9)
        else:
            c.hit()


@power(
    "m6579a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6579a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6579a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6579a3(c: Cast) -> None:
    """`c.resize` shoves whoever is standing in the squares it comes to occupy,
    because that is the printed consequence of growing rather than a separate
    line -- so the second sentence needs nothing of its own.

    The square of reach m6579a1 prints while Large belongs here, gated to that
    row by `ctx["power"]` -- a modifier has to be standing before the area is
    taken and an at-will attack cannot put one up for its own use. The reason
    it was not written is gone: #533 moved the stretch into `dsl._reach_of`,
    so `_within_reach` reads the same number `area_of` does.

    The size is asked **inside the gate** as well as bounded by `EONT`,
    because the two clocks are not the same thing: `c.resize` can be undone
    by another card, and a reach standing on a creature that is no longer
    Large is a square the print does not give it. #737."""
    me = c.me
    c.resize(Size.LARGE, until=When.EONT, on=me)
    c.bonus(
        "reach", 1, on=me, until=When.EONT,
        when=lambda ctx: ctx.get("power") == "m6579a1"
        and c.size_of(me) is Size.LARGE,
    )


# --------------------------------------------------------------------------
# m6631
# --------------------------------------------------------------------------


def _hurt_already(world: World, eid: int) -> bool:
    """"It must have taken damage during the encounter", asked of its wounds.

    Not a perfect reading -- a creature healed all the way back answers False
    -- but it is the question `dsl.usable` can ask with only `(world, eid)`,
    and a brute that has been hit and healed to full is not a board state this
    level produces.
    """
    health = world.get(eid, Health)
    return health is not None and health.hp < health.max_hp


def _my_basic_landed(world: World, me: int, ev: Hit) -> bool:
    """"When it hits with a melee basic attack." Which row that *is* comes off
    `Powers.basic`, so a block whose basic has been replaced is read right."""
    if getattr(ev, "attacker", None) != me:
        return False
    known = world.get(me, Powers)
    basic = (known.basic if known else "") or "m6631a1"
    return getattr(ev, "power", "") == basic


@power(
    "m6631a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6631a0(c: Cast) -> None:
    """Flanking is geometry that changes whenever anybody moves, so it is a
    gate on the damage context rather than a bonus put on and taken off."""

    def flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, c.me)

    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=flanking
    )


@power(
    "m6631a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3),
)
def m6631a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6631a2",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_hurt_already,
    requires_text="it must have taken damage during the encounter",
    trigger="it hits with a melee basic attack",
    on=Trigger(Hit, _my_basic_landed, "it hits with a melee basic attack"),
)
def m6631a2(c: Cast) -> None:
    """The extra damage is dealt to whoever the triggering blow landed on, read
    off the event: an immediate action's own target list names somebody it never
    touched."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("1d10", on=victim)


@power(
    "m6631a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m6631a3(c: Cast) -> None:
    """A creature that is down still has `Health`, so the heal reaches it. The
    heal goes first: knocking a corpse prone is not the printed order and the
    prone has to land on something standing back up."""
    c.heal(19, on=c.me)
    c.prone(on=c.me)
    c.restore_use("m6631a2", on=c.me)


# --------------------------------------------------------------------------
# m784
# --------------------------------------------------------------------------


@power(
    "m784a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m784a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m784a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    defect="the printed attack line names no defence",
)
def m784a1(c: Cast) -> None:
    """Two basic attacks against two adjacent creatures, which plays. The
    Requirement -- that it did not move this turn -- cannot be asked: nothing
    records what a creature has already done with its turn. The attack line
    above it extracted against no defence at all, which is a compendium defect
    and not a defence to invent."""
    c.basic(on=c.target)


@power(
    "m784a2",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_IN_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_IN_MELEE),
)
def m784a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m784a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    dropped=("c.must_attack(on=, against=)",),
)
def m784a3(c: Cast) -> None:
    """Three of four clauses play: the extra die, the row it loses, and the
    heal as its turn closes.

    Losing the row is a hold rather than a question, because `c.forbid` takes
    no gate -- so it is laid as the creature crosses the line and lifted again
    if it climbs back over it, which this card can do: the same trait heals it
    five a turn. Laid once and left, the row would stay gone after a heal that
    the printed "while" gives it back.

    What it must do with its turns is the gap. That is a policy instruction --
    attack the nearest, charge where possible -- and nothing constrains what
    the AI chooses, only what the rules allow."""
    me = c.me
    hold: list[Any] = []
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=_while_bloodied(c),
    )

    def bled(ev: Bloodied) -> None:
        if ev.actor != me or hold:
            return
        lost = c.forbid("m784a2", on=me, until=When.ENCOUNTER)
        if lost is not None:
            hold.append(lost)

    def mended(ev: Healed) -> None:
        if ev.target != me or not hold or _is_bloodied(c.world, me):
            return
        c.world.effects.end(hold.pop(), c.ref)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{c.ref} cost")
    c.watch(Healed, mended, until=When.ENCOUNTER, on=me, label=f"{c.ref} restored")

    def closes(ev: TurnEnd) -> None:
        if ev.actor != me or ev.ghost:
            return
        if alive(c.world, me) and _is_bloodied(c.world, me):
            c.heal(5, on=me)

    c.watch(TurnEnd, closes, until=When.ENCOUNTER, on=me, label=f"{c.ref} mending")


# --------------------------------------------------------------------------
# m813
# --------------------------------------------------------------------------


@power(
    "m813a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE),
)
def m813a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(2, DamageType.FIRE)


@power(
    "m813a1",
    level=3,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m813a1(c: Cast) -> None:
    """"Resist all 10" is `c.resist` with no type named, which is what the bare
    call means -- a per-type loop would be ten effects for one sentence."""
    c.resist(10, until=When.EONT, on=c.me)


# --------------------------------------------------------------------------
# m817
# --------------------------------------------------------------------------


@power(
    "m817a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m817a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m817a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    defect="the printed attack line names no defence",
)
def m817a1(c: Cast) -> None:
    """Two basic attacks, spread or doubled up as the chooser likes. The attack
    line above them extracted against no defence, which is a compendium defect
    rather than a number to guess."""
    c.basic(on=c.target)
    if c.last and len(c.targets) < 2:
        c.basic(on=c.target)


@power(
    "m817a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 6, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m817a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m817a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_OTHER,
    attack=Attack(vs=WILL, printed=6),
)
def m817a3(c: Cast) -> None:
    if c.strike():
        c.condition(
            Condition.DAZED, Condition.WEAKENED, until=When.SAVE_ENDS
        )


@power(
    "m817a4",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m817a4(c: Cast) -> None:
    """"Regardless of whether the power has recharged" is the use handed the row
    outright: `c.restore_use` first, because a spent row is refused."""
    _recharge_and_fire(c, "m817a2")


# --------------------------------------------------------------------------
# m907
# --------------------------------------------------------------------------


@power(
    "m907a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4, dtype=DamageType.COLD),
)
def m907a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.opportunity:
            c.damage("1d6", dtype=DamageType.COLD)


@power(
    "m907a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m907a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m907a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m907a2(c: Cast) -> None:
    _claws_then_bite(c, "m907a1", "m907a0")


@power(
    "m907a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("3d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m907a3(c: Cast) -> None:
    _breath(c)


@power(
    "m907a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m907a4(c: Cast) -> None:
    _recharge_and_fire(c, "m907a3")


@power(
    "m907a5",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=4),
)
def m907a5(c: Cast) -> None:
    """The stun plays; the Aftereffect does not. It fires when the save
    *succeeds*, and `escalate` is the opposite half -- it answers a save that
    failed."""
    if c.strike():
        victim = c.target
        held = c.stunned(until=When.EONT)
        c.aftereffect(held, lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))