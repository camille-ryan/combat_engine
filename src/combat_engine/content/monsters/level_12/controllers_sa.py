"""Monster abilities, level 12: the rest of the controllers.

`controllers.py` holds the fourteen stat blocks that were already written;
this is the other forty-six. Numbers load from `game.db` -- the attack line
goes in the header as `Attack(vs=AC, printed=17)` and the damage line as
`Damage("2d8", 5)`, both exactly as printed, so the engine takes the level
term back out and rescales.

The conventions of the eleven levels below are kept: a row filed under an
action heading that is plainly a trait is `ActionType.NONE`; a stat block
printing no range at all means melee 1; a **close** burst or blast with no
printed target line is `EACH_ENEMY` and an **area** one with none is
`EACH_CREATURE`; a printed "Effect (Immediate Reaction)" is a reaction
whatever the action column says; and a helper written for an earlier level
is imported rather than copied.

Eight readings this file had to settle.

**Three of these stat blocks are a second printing of one already written
in `controllers.py`** -- m2256 against m45, m3804 against m193, m1179
against m679. Same defences, same abilities, same order. Each ref is
written out in full rather than aliased, because the unit of work is a ref;
where the twin's body settled a reading, the same reading is taken here, so
the pairs cannot drift.

**"It can affect only one creature at a time"** is `_only_one`: the hold
sits on the creature it was laid on, so it is found from the caster's side
through `c.suffering` and ended before the new one is taken. Eleven rows
print it.

**A printed Effect that recharges another row and uses it** is
`_uses_again`: `Powers.restore` then `use(..., spend=True)`. Six rows print
it, all of them off "when first bloodied", and `Bloodied` is emitted on the
crossing and only then -- so the trigger needs nothing on top.

**A zone that charges for every square crossed** is `EnterSquare`, not
`c.burns`: burning bites on entering the zone and on starting a turn in it,
which is twice for a creature that walks four squares through it. m115796a2
is the shape.

**"Lightly obscured" is not written.** `blocks_sight` is a wall rather than
a haze and concealment is not a thing a zone can carry, so the squares are
plain and the obscurement is a note -- the reading m5020a5 settled a level
down.

**A secondary attack line has no ref to live in**, so its printed total goes
through `_secondary`, which takes the level term back out the way the
header's `Attack(printed=)` does.

**A creature that gets back up is stood up inside the blow that felled it.**
`c.revives_unless` is declaration only; `Dropped` says who struck and not
what with, so the damage type comes off the `DamageApplied` immediately
before it. The printed "on its next turn" is not waited for: nothing owes a
corpse an action and `threat_removed` has already written it off. m3533a3
settled that at level 2 and m1155a5 and m3796a4 follow it.

**Two briefs print a word that is not a ref.** m5641a1 and m6537a6 each
carry one. Neither is written here -- not in a body, not in a docstring --
and both are reported instead.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.skirmishers import _until_the_grab_ends
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_07.controllers import _rearms_when_bloodied
from combat_engine.content.monsters.level_07.soldiers import _aura, _recharge_on
from combat_engine.content.monsters.level_08.brutes import (
    _holding,
    _is_bloodied,
    _melee_ctx,
)
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.content.monsters.level_10.brutes import _same_stock
from combat_engine.content.monsters.level_11.controllers import (
    EVERY_DEFENCE,
    _ends_its_turn_in,
    _held_and_softened,
    _softened,
)
from combat_engine.content.monsters.level_12.controllers import _is_charm, _stood_still
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
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
    STANDARD,
    WILL,
    ActionType,
    AdjacencyGained,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Defences,
    Dropped,
    Effect,
    EnterSquare,
    Healed,
    Health,
    Hit,
    Initiative,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Mod,
    Moved,
    MoveEnd,
    MoveStart,
    Powers,
    PowerUsed,
    Ranged,
    Relation,
    Size,
    Stats,
    SurgeSpent,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    Wall,
    When,
    Window,
    World,
    ZoneEntered,
    ZoneExited,
    about_me,
    get,
    power,
    targets_me,
    use,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger
from combat_engine.engine.zones import Zone

#: The conditions a printed "any dazing, stunning, or dominating effect"
#: names, and nothing else on an effect says what sort of thing it is.
_MIND_HELD = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)

#: The `Moved.kind_` of a step a creature took of its own accord. A shove
#: emits none of these, which is what "willingly" turns on.
_WILLING = ("walk", "shift", "run", "teleport", "charge")


def _only_one(c: Cast, label: str) -> None:
    """"It can affect only one creature at a time" -- the standing hold goes.

    The hold sits on the creature it was laid on rather than on the caster,
    so it is found from the caster's side through `c.suffering` and matched
    on both the label and the source: two copies of one stat block each hold
    their own.
    """
    for held in c.suffering(label):
        for eff in list(c.world.effects.of(held)):
            if eff.label == label and eff.source == c.me:
                c.world.effects.end(eff, "it took hold of somebody else")


def _uses_again(c: Cast, ref: str) -> None:
    """"That power recharges, and it uses it immediately."

    The use is handed back through `Powers.restore` and then spent, which is
    the order the printed sentence reads in -- `use` would be refused while
    the row is still expended.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore(ref)
    use(c.world, c.me, ref, spend=True)


def _shrugs_off_the_mind(c: Cast, *, save_ends_only: bool = False) -> None:
    """"At the end of each of its turns it saves against ..." as an ending.

    `c.save` rolls a real saving throw and `c.unsave` fails one; neither says
    "it succeeds", and a success is what the printed line grants. So the hold
    is ended, which is the same outcome with nothing faked.
    """
    me = c.me

    def shrug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if save_ends_only and eff.when is not When.SAVE_ENDS:
                continue
            if set(eff.conditions) & set(_MIND_HELD):
                c.world.effects.end(eff, c.ref)

    c.watch(TurnEnd, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


def _rises_unless(c: Cast, hp: int, *types: DamageType) -> None:
    """It gets back up unless one of those types put it down.

    `Dropped` names who struck the blow and not what with, so the type is
    taken off the `DamageApplied` immediately before it -- the blow that
    crossed the line, and the only one that can be. `c.revives_unless` is
    the declaration that stops the policy writing the body off as finished;
    this watch is what actually stands it up.
    """
    me = c.me
    c.revives_unless(*types, on=me)
    last: dict[str, bool] = {"doused": False}
    risen: dict[str, int] = {"count": 0}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["doused"] = bool(set(ev.types()) & set(types))

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last["doused"] or risen["count"]:
            return
        risen["count"] += 1
        c.reanimate(on=me, hp=hp)
        c.prone(on=me)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


def _per_square(c: Cast, zone: int, amount: int, dtype: DamageType) -> Effect:
    """"Takes N damage for each square of movement in the zone."

    `c.burns` is the wrong instrument: it bites on entering and on starting a
    turn there, which is twice for a creature that crosses four squares. Every
    step is an `EnterSquare`, which is where the charge belongs.
    """
    me = c.me

    def toll(ev: EnterSquare) -> None:
        if ev.actor == me:
            return
        live = c.world.get(zone, Zone)
        if live is not None and ev.square in live.squares:
            c.flat(amount, dtype=dtype, on=ev.actor)

    return c.watch(EnterSquare, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _shift_closer(c: Cast, who: int, toward: int) -> bool:
    """One square of somebody *else's* shift, closing on a named creature.

    `_step_toward` moves the caster, which is the shape eleven levels of
    rows wanted; a leader line reading "each ally can shift 1 square closer
    to the target" needs the ally to be the one that moves.
    """
    theirs = squares(c.world, toward)
    mine = squares(c.world, who)
    if not theirs or not mine:
        return False
    here = next(iter(sorted(mine)))

    def gap(square: tuple[int, int]) -> int:
        return min(max(abs(square[0] - t[0]), abs(square[1] - t[1])) for t in theirs)

    nearer = sorted(
        (
            (x, y)
            for x in range(here[0] - 1, here[0] + 2)
            for y in range(here[1] - 1, here[1] + 2)
            if (x, y) != here and gap((x, y)) < gap(here)
        ),
        key=gap,
    )
    return any(c.shift(1, who=who, to=square) for square in nearer)


def _last_blow_on(world: World, who: int) -> DamageApplied | None:
    """The most recent damage that landed on that creature.

    A reaction answering "the target takes damage of the same type you took"
    has no type on its own trigger: `Hit` does not carry one and the blow has
    already been dealt by the time a reaction runs. The log does carry it.
    """
    for past in reversed(world.bus.log):
        if isinstance(past, DamageApplied) and past.target == who:
            return past
    return None


# ==========================================================================
# m1043
# ==========================================================================


@power(
    "m1043a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 5, dtype=DamageType.FIRE),
    dropped=("c.no_surges()",),
)
def m1043a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. "Cannot spend healing surges" is the dropped clause: `c.no_healing`
    stops healing outright, which is wider than the card, so the narrower
    sentence is named rather than approximated."""
    if c.strike():
        c.hit()


@power(
    "m1043a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m1043a1(c: Cast) -> None:
    """A blast that picks one enemy out of it, which is the printed target
    line and not the shape of the area."""
    if c.strike():
        c.hit()
        c.push(4)
        c.dazed(until=When.EONT)


@power(
    "m1043a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 6, dtype=DamageType.NECROTIC),
)
def m1043a2(c: Cast) -> None:
    """The keyword line says fire and the damage line says necrotic; both go
    in exactly as printed rather than reconciled.

    "Save ends both" is one effect carrying the burn and the hold, so the
    printed sentence gets the single saving throw it prints.
    """
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.FIRE),
        )


_M1043_KIN_FELL = "an undead ally within 10 squares drops to 0 hit points"


def _ally_fell_within_10(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    return team(world, who) is team(world, me) and distance_between(world, me, who) <= 10


@power(
    "m1043a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M1043_KIN_FELL,
    on=Trigger(Dropped, when=_ally_fell_within_10, text=_M1043_KIN_FELL),
)
def m1043a3(c: Cast) -> None:
    """The healing goes to the creature the trigger names, which is
    `c.trigger.actor` -- this row has no target line at all, so `c.target` is
    None and would have aimed it nowhere.

    "Undead" is asked in the body rather than in the predicate: the type
    words come off the stat block and `Cast` is the only thing that reads
    them.
    """
    ev = c.trigger
    ally = getattr(ev, "actor", None) if ev is not None else None
    if ally is None or not c.is_kind("undead", on=ally):
        return
    c.heal(15, on=ally)


# ==========================================================================
# m1145
# ==========================================================================


@power(
    "m1145a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 4),
)
def m1145a0(c: Cast) -> None:
    """The declared line is untyped: only the burn is named necrotic. The
    Aftereffect hangs on the burn's own ending, which follows it going
    whichever way it went."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.ongoing(5, DamageType.NECROTIC, on=victim)
    if hold is not None:
        hold.on_end.append(lambda: c.weakened(until=When.SAVE_ENDS, on=victim))


@power(
    "m1145a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m1145a1(c: Cast) -> None:
    """A blind creature is immune, so it is passed over before the roll
    rather than after it. The damage line only ever pays out against a target
    that was already dazed, which is what the printed "instead" means --
    asked before the attack, because the daze this row lays would otherwise
    make its own condition true."""
    victim = c.target
    if victim is None or c.is_(Condition.BLINDED, on=victim):
        return
    already = c.is_(Condition.DAZED, on=victim)
    if not c.strike():
        return
    if already:
        c.hit()
    else:
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m1155
# ==========================================================================


@power(
    "m1155a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 4),
)
def m1155a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1155a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
)
def m1155a1(c: Cast) -> None:
    """One point of damage is not a damage line -- it is flat, so the header
    declares none and `c.hit` is never called.

    The rider is read off `Hit` rather than `DamageApplied`, because `Hit`
    carries `power` and that is where the reach telling a melee swing from
    the rest is looked up. "A m1155" is any creature off this stat block,
    which is `Ident.ref` and nothing else.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.flat(1, on=victim)
    c.effect(c.ref, until=When.ENCOUNTER, on=victim)
    world, me = c.world, c.me

    def extra(ev: Hit) -> None:
        if ev.target != victim or not _same_stock(world, me, ev.attacker):
            return
        if _reach_kind(ev) != "melee":
            return
        c.flat(c.roll("1d6"), on=victim)

    c.watch(Hit, extra, until=When.ENCOUNTER, on=me, label=f"{c.ref} rider")


@power(
    "m1155a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.FEAR],
    attack=Attack(vs=WILL, printed=16),
)
def m1155a2(c: Cast) -> None:
    """"Targets an enemy affected by m1155a1" is a restriction `Target`
    cannot express, so the aim is moved to a creature that qualifies rather
    than thrown away -- `Target.kind` is the gap. One at a time: the standing
    domination is let go as the new one is taken."""
    marked = set(c.suffering("m1155a1"))
    victim = _restricted_to(c, 10, lambda who: who in marked)
    if victim is None:
        return
    if not c.strike(on=victim):
        return
    _only_one(c, c.ref)
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


@power(
    "m1155a3",
    level=12,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m1155a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1155a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    todo=("c.undouse()",),
)
def m1155a4(c: Cast) -> None:
    """Nothing can be said here at all, so the row is refused rather than
    half-written.

    The printed line turns a *suppressed* regeneration back on for its own
    kind nearby. Suppression is not a thing the engine holds: `_regenerates`
    takes a `doused` label chosen by whichever row lays it, so there is no
    way to ask "is this creature's regeneration switched off" and no way to
    switch it back on from another creature's trait. This stat block is also
    printed with no regeneration line of its own for the clause to point at.
    """


@power(
    "m1155a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1155a5(c: Cast) -> None:
    """It gets back up with 10 hit points unless acid or fire finished it.

    Stood up inside the blow that felled it rather than on its next turn:
    nothing in the engine owes a corpse an action, and a body that waits a
    round is one `threat_removed` has already written off. The reading
    m3533a3 settled at level 2.
    """
    _rises_unless(c, 10, DamageType.ACID, DamageType.FIRE)


# ==========================================================================
# m115683
# ==========================================================================


@power(
    "m115683a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115683a0(c: Cast) -> None:
    """Every such hold goes, not only the ones a save could have ended: the
    printed line names the conditions and says nothing about their clocks."""
    _shrugs_off_the_mind(c)


@power(
    "m115683a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.extra_turn(script=)",),
)
def m115683a1(c: Cast) -> None:
    """`c.extra_turn` hands back a whole ordinary turn at a count, not one
    scripted free action -- and a solo handed a free turn at initiative 10 +
    its check is a different creature from the one on the card. The second
    sentence is conditional on the first and goes with it; m115683a0 already
    ends a dominating or stunning hold at the end of each of its turns.
    """


@power(
    "m115683a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m115683a2(c: Cast) -> None:
    """The declared line is untyped -- only the burn is named necrotic."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)


@power(
    "m115683a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 9),
)
def m115683a3(c: Cast) -> None:
    """Twice against one creature, once each against two.

    The second swing cannot go through `use`, which refuses to re-enter a row
    already in flight -- and the row in flight is this one -- so it is a
    second `c.strike` in the same body. The slide is an Effect and lands
    whether or not either swing did.
    """
    for _ in range(2 if c.first and c.last else 1):
        if c.strike():
            c.hit()
    c.slide(2)


@power(
    "m115683a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d12", 8, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m115683a4(c: Cast) -> None:
    """`half_on_miss` is declared data nothing reads, so the Miss branch is
    written out -- and its weakening is on a turn clock rather than a saving
    throw, which is the difference the card draws."""
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.weakened(until=When.EOTNT)


@power(
    "m115683a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m115683a5(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit, and the Miss
    line's 15 points are flat.

    "Willingly moves to a square nearer" is asked on `Moved`, which is the
    only one of the three movement events carrying `from_` -- so the step can
    be compared with where it started. A shove emits no `kind_` this list
    holds, which is what "willingly" turns on. The slide is an Effect and
    happens either way.
    """
    victim = c.target
    if victim is None:
        return
    landed = c.strike(on=victim)
    if landed:
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    else:
        me, paid = c.me, {"done": False}

        def closing(ev: Moved) -> None:
            if paid["done"] or ev.actor != victim:
                return
            if getattr(ev, "kind_", "") not in _WILLING:
                return
            was = getattr(ev, "from_", None)
            now = distance_between(c.world, me, victim)
            mine = squares(c.world, me)
            before = (
                min(max(abs(was[0] - s[0]), abs(was[1] - s[1])) for s in mine)
                if was is not None and mine
                else now + 1
            )
            if now <= 1 or now < before:
                paid["done"] = True
                c.flat(15, dtype=DamageType.PSYCHIC, on=victim)

        c.watch(Moved, closing, until=When.EOTNT, on=me, label=f"{c.ref} drawn in")
    c.slide(2, on=victim)


_M115683_BLOODIED = "it is first bloodied"


@power(
    "m115683a6",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115683_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M115683_BLOODIED),
)
def m115683a6(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and only then, so "first" needs
    nothing on top of the trigger."""
    _uses_again(c, "m115683a4")


def _burns_others(
    c: Cast,
    zone: int,
    dice: str,
    dtype: DamageType = DamageType.UNTYPED,
    bonus: int = 0,
) -> None:
    """`c.burns`, with this creature's own kind excused.

    `c.burns` takes no side, and a printed "it is immune to its own zone" is
    about `Ident.ref` rather than about teams -- two copies of one stat block
    both walk through it. The two moments are the printed ones: entering, and
    starting a turn inside.
    """
    me = c.me

    def bite(who: int) -> None:
        if who == me or _same_stock(c.world, me, who):
            return
        c.damage(dice, bonus, dtype=dtype, on=who, detail=c.ref)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} stays")


def _held_inside(
    c: Cast,
    zone: int,
    hold: Callable[[int], Effect | None],
    *,
    eligible: Callable[[int], bool] | None = None,
) -> None:
    """A hold carried for as long as a creature stands in a named zone.

    `_aura` at level 7 does this for an aura it makes itself; a zone laid
    somewhere other than around the caster needs the same diffing against an
    id it is handed. Membership comes off `ZoneEntered`/`ZoneExited`, and
    whoever is already inside is caught at the end.
    """
    me = c.me
    inside: dict[int, Effect] = {}

    def take(who: int) -> None:
        if who in inside or who == me:
            return
        if eligible is not None and not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            inside[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = inside.pop(ev.actor, None) if ev.zone == zone else None
        if effect is not None:
            c.world.effects.end(effect, "left the zone")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enters")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} leaves")
    for who in c.world.zones.occupants(zone):
        take(who)


def _hits_this_use(c: Cast) -> int:
    """How many of this row's targets it has hit on this use.

    The body runs once per target, so a local cannot count across them and a
    closure armed on the first target is gone by the last. The bus is the one
    place the tally exists: everything since this row's own `PowerUsed` is
    this use, which is the same walk m45a4's predicate makes.
    """
    count = 0
    for past in reversed(c.world.bus.log):
        if past.kind == "PowerUsed" and getattr(past, "power", "") == c.ref:
            break
        if (
            past.kind == "Hit"
            and getattr(past, "attacker", None) == c.me
            and getattr(past, "power", "") == c.ref
        ):
            count += 1
    return count


def _dominated_by(c: Cast) -> list[int]:
    """Whoever this creature is dominating right now.

    Domination is an ordinary condition on an effect, and the effect's source
    is the dominator -- which is the only thing that tells one puppeteer's
    hold from another's.
    """
    out = []
    for who in c.enemies():
        for eff in c.world.effects.of(who):
            if Condition.DOMINATED in eff.conditions and eff.source == c.me:
                out.append(who)
                break
    return out


# ==========================================================================
# m115796
# ==========================================================================


@power(
    "m115796a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 9),
)
def m115796a0(c: Cast) -> None:
    """The teleport is an Effect and lands whether or not the blow did."""
    if c.strike():
        c.hit()
    if c.target is not None:
        c.teleport(3, who=c.target)


@power(
    "m115796a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=15),
)
def m115796a1(c: Cast) -> None:
    """No damage line at all: the restraint is the whole of the hit, and the
    Miss line is a slow on a turn clock."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.EONT)


@power(
    "m115796a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 8, kind=LIMITED),
    dropped=("c.aim(at=)",),
)
def m115796a2(c: Cast) -> None:
    """The damage and the zone play; the centring is the dropped clause.

    "Centred on a creature restrained by m115796a1" names the burst's origin
    square, and nothing lets a row name one: the chooser picks the origin
    before the body runs and `c.origin` can only be read back.

    Forest walk is the exemption the printed line gives, so the roughness
    carries that word -- `c.ignores_difficult("forest")` is what would
    excuse a creature from it, and nothing in the tree grants one yet. The
    toll is per square crossed, which is `EnterSquare` and not `c.burns`.
    """
    if c.strike():
        c.hit()
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult="forest")
    _per_square(c, zone, 5, DamageType.UNTYPED)


@power(
    "m115796a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 11, dtype=DamageType.POISON, kind=LIMITED),
)
def m115796a3(c: Cast) -> None:
    """"Lightly obscured" is concealment, which a zone cannot carry, and
    `blocks_sight` is a wall rather than a haze -- so the squares are plain
    and the obscurement is noted, the reading m5020a5 settled."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.EONT)
    _ends_its_turn_in(c, zone, lambda who: c.flat(10, dtype=DamageType.POISON, on=who))
    c.note(f"{c.ref}: the zone is lightly obscured")


_M115796_SHAPE = "m115796a4 shape"


@power(
    "m115796a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:insight",),
)
def m115796a4(c: Cast) -> None:
    """A shape with no mechanics inside it. `c.form` is what the engine holds
    a polymorph in, and the printed "until it uses this again" is the old
    shape being dropped first -- this is not a stance, so nothing ends it on
    its own.

    The Insight check is the narrative clause: discerning a disguise is a
    circumstance nothing on a board ever rolls for, so there is no symbol to
    wait on. Dropping to 0 hit points ends it anyway, with the creature.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M115796_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M115796_SHAPE)
    c.note(f"{c.ref}: it takes the shape of a Medium humanoid")


# ==========================================================================
# m115844
# ==========================================================================


@power(
    "m115844a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115844a0(c: Cast) -> None:
    """An aura that moves its own side about.

    The slide is the m115844's, not the ally's own move, so it is `c.slide`
    aimed at the ally and costs the ally nothing -- which is what the printed
    free action means on a creature that is not the one acting.
    """
    me = c.me
    ring = c.aura(5, label=c.ref, until=When.ENCOUNTER)

    def nudge(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is not team(c.world, me):
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slide(2, on=ev.actor)

    c.watch(TurnStart, nudge, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115844a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m115844a1(c: Cast) -> None:
    """A penalty that only applies to this creature's own attacks.

    `c.grants_in` hangs the modifier on the aura rather than on a clock, so
    it ends when the enemy walks out instead of at a turn boundary. The gate
    reads `attacker` off the attack context, which is where a defence is
    looked up -- the damage context has no such key and a gate on one it does
    not carry is silently false.

    The card prints "-2 penalty" with no type word, so it is untyped.
    """
    me = c.me
    ring = c.aura(5, label=c.ref, until=When.ENCOUNTER)
    for defended in EVERY_DEFENCE:
        c.grants_in(
            ring,
            defended,
            -2,
            side="enemy",
            kind="untyped",
            when=lambda ctx: ctx.get("attacker") == me,
        )


@power(
    "m115844a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115844a2(c: Cast) -> None:
    """Fire catches. Read off `DamageApplied` rather than `DamageRolled`,
    because the printed line is about damage it actually took and a blow its
    resistance ate whole is not one."""
    me = c.me

    def catches(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if DamageType.FIRE in ev.types():
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, catches, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115844a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 9),
)
def m115844a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115844a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m115844a4(c: Cast) -> None:
    """The splash is tied to the burn ticking, which is a `DamageApplied`
    whose `detail` carries the effect that dealt it -- `Effects._on_turn_start`
    stamps `str(eff)` there, and the label inside it is this row's ref. The
    listener hangs on the burn's own `subs`, so it dies with the burn rather
    than drifting on a clock of its own.

    "Each ally adjacent to it" is the *target's* side, not this creature's.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    burn = c.ongoing(5, DamageType.NECROTIC, on=victim)
    if burn is None:
        return
    ref, me = c.ref, c.me

    def splash(ev: DamageApplied) -> None:
        if ev.target != victim or ref not in ev.detail:
            return
        for mate in c.within(1, of=victim):
            if mate != victim and team(c.world, mate) is team(c.world, victim):
                c.flat(5, dtype=DamageType.NECROTIC, on=mate)

    burn.subs.append(c.world.bus.on(DamageApplied, splash, owner=me))


@power(
    "m115844a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d12", 9, dtype=DamageType.PSYCHIC),
)
def m115844a5(c: Cast) -> None:
    """Both halves run on the same turn clock and neither is a saving throw,
    so two effects cost nothing -- the reason to fold them into one is a
    printed "save ends both", and this card prints no save at all."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m115844a6",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115844a6(c: Cast) -> None:
    """Two rows at this row's action cost. Neither is aimed from here: left
    without `on=`, a borrowed row picks its own target exactly as it would on
    an ordinary turn, which is what both of these print."""
    c.use_power("m115844a4")
    c.use_power("m115844a5")


@power(
    "m115844a7",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d10", 13, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m115844a7(c: Cast) -> None:
    """`half_on_miss` is declared data nothing reads, so both branches are
    written -- and the Miss line pushes a shorter distance, which is the
    difference worth writing out."""
    if c.strike():
        c.hit()
        c.push(4)
    else:
        c.hit(half=True)
        c.push(2)


@power(
    "m115844a8",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
)
def m115844a8(c: Cast) -> None:
    """No attack roll: the printed line is all Effect.

    "Whenever the target spends a healing surge" is `SurgeSpent`, which is
    emitted from every site that decrements a pool -- so the clause can be
    said exactly rather than hung off a heal. The listener lives on the
    hold's own `subs`, and "until it uses this power again" is `_only_one`.
    The extended rest is not a thing a board has.
    """
    victim = c.target
    if victim is None:
        return
    _only_one(c, c.ref)
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def drained(ev: SurgeSpent) -> None:
        if ev.actor == victim:
            c.weakened(until=When.EOTNT, on=victim)

    hold.subs.append(c.world.bus.on(SurgeSpent, drained, owner=c.me))


# ==========================================================================
# m115876
# ==========================================================================


@power(
    "m115876a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115876a0(c: Cast) -> None:
    """A blow taken on a limb instead of on the creature.

    The choice is asked when the damage has been rolled and not yet dealt,
    which is the one moment the number exists -- and taking it costs the
    m115876 one of its grabs, so the protection is bounded by how many it
    holds, exactly as the card bounds it. An attack that misses never reaches
    here, which is the same outcome as striking a limb and missing it.

    The grab goes through `c.escape(auto=True)`, which is the engine's way
    out of one; ending the hold by hand would leave the relation standing.
    """
    me = c.me

    def shield(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        held = _holding(c.world, me)
        if not held or not c.may("strike a limb instead", who=ev.source):
            return
        ev.amount = 0
        c.escape(on=held[0], auto=True)

    c.watch(
        DamageRolled,
        shield,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


@power(
    "m115876a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m115876a1(c: Cast) -> None:
    """Narrative only. Sitting still to look like the floor is a Perception
    contest before the fight, and there is nothing on a board it changes once
    initiative is rolled."""
    c.note(f"{c.ref}: it can pass for a rock formation on horizontal stone")


@power(
    "m115876a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 9),
    requires=lambda world, eid: len(_holding(world, eid)) < 2,
    requires_text="it must have fewer than two creatures grabbed",
)
def m115876a2(c: Cast) -> None:
    """The Requirement is a fact about the board, asked before the row is
    offered -- safe here because this is a standard action and not a trait,
    which `turns.arm_traits_of` would refuse once and never arm again.

    "Until the grab ends, the target is weakened" is a hold on the grab's own
    clock rather than on a duration.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab(on=victim)
    _until_the_grab_ends(c, victim, c.weakened(until=When.ENCOUNTER, on=victim))


@power(
    "m115876a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=UpTo(2),
)
def m115876a3(c: Cast) -> None:
    """Two swings of the row that prints them. The printed Effect does not say
    whether they land on one creature or two, so the header takes up to two
    and a single target is reached for twice."""
    if c.target is not None:
        _volley(c, "m115876a2", c.target)


@power(
    "m115876a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d12", 12, half_on_miss=True),
)
def m115876a4(c: Cast) -> None:
    """Only something it already holds, which `Target` cannot filter on, so
    the aim is moved to a creature that qualifies rather than thrown away."""
    held = set(_holding(c.world, c.me))
    victim = _restricted_to(c, 1, lambda who: who in held)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


@power(
    "m115876a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(10),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=17),
)
def m115876a5(c: Cast) -> None:
    """No damage line: the pull is the whole of the hit, and it is measured to
    the m115876, which is where `c.pull` anchors by default."""
    victim = c.target
    if victim is None or victim not in _holding(c.world, c.me):
        return
    if c.strike(on=victim):
        c.pull(5, on=victim)


# ==========================================================================
# m1170
# ==========================================================================


@power(
    "m1170a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 3),
)
def m1170a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m1170a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 5),
)
def m1170a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m1170a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 4),
)
def m1170a2(c: Cast) -> None:
    """"Cannot be teleported into an unsafe space" is already how
    `c.teleport` picks a destination, so the sentence costs nothing."""
    if c.strike():
        c.hit()
        if c.target is not None:
            c.teleport(3, who=c.target)


@power(
    "m1170a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m1170a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m1170a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1170a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1179
# ==========================================================================


@power(
    "m1179a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 4),
)
def m1179a0(c: Cast) -> None:
    """It heals by what it dealt, so the number `c.hit` returns is the number
    -- what came off hit points after resistance, which is what "the amount
    of damage dealt" reads as."""
    if not c.strike():
        return
    dealt = c.hit()
    c.dazed(until=When.SAVE_ENDS)
    if dealt > 0:
        c.heal(dealt, on=c.me)


_M1179_DRAIN = "m1179a1 hold"


@power(
    "m1179a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 4),
)
def m1179a1(c: Cast) -> None:
    """A hold that pays out every time it is kept.

    The sustain cost goes on the effect itself -- `effects.apply` takes one
    and `c.watch` does not -- and `c.on_sustain` carries the payout half,
    which a clock refreshing on its own would drop. The printed range check
    is made at payout rather than now, because the target can walk out of it.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    for eff in list(c.world.effects.of(me)):
        if eff.label == _M1179_DRAIN:
            c.world.effects.end(eff, "it took hold of somebody else")
    held = c.world.effects.apply(
        me, me, When.SUSTAIN, label=_M1179_DRAIN, sustain_cost=MINOR
    )

    def again() -> None:
        if not alive(c.world, victim) or distance_between(c.world, me, victim) > 5:
            c.world.effects.end(held, "the target is out of reach")
            return
        c.damage("3d6", 4, on=victim, detail=ref)

    c.on_sustain(held, again)


@power(
    "m1179a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m1179a2(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


_M1179_SHAPE = "m1179a3 shape"


@power(
    "m1179a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1179a3(c: Cast) -> None:
    """A shape with no mechanics inside it: `c.form` is what the engine holds
    a polymorph in, and the minor action it cost is the printed way back. A
    shape already worn is dropped first -- this is not a stance, so nothing
    ends the old one on its own."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M1179_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M1179_SHAPE)
    c.note(f"{c.ref}: it takes the shape of a Medium humanoid of any race or gender")


@power(
    "m1179a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1179a4(c: Cast) -> None:
    """Narrative only. The board has no small openings to go through, and
    `Condition.SQUEEZING` is the opposite of what this line grants: it is the
    penalty for being somewhere too tight, not permission to be there."""
    c.note(f"{c.ref}: it fits through small openings as though it were Tiny")


# ==========================================================================
# m1450
# ==========================================================================


@power(
    "m1450a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 4),
)
def m1450a0(c: Cast) -> None:
    """The card prints no clock on the burn, and a saving throw is what an
    unqualified ongoing line means."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1450a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1450a1(c: Cast) -> None:
    """It heals by what it dealt, which is the number `c.hit` hands back."""
    if not c.strike():
        return
    dealt = c.hit()
    if dealt > 0:
        c.heal(dealt, on=c.me)


@power(
    "m1450a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(8),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d10", 7, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1450a2(c: Cast) -> None:
    """The blow is fire and the burn is necrotic, which is two packets and
    why the header declares only the first. The Aftereffect hangs on the
    burn's own ending rather than on `escalate`: escalation runs on a failed
    save and an aftereffect is what follows either way."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    burn = c.ongoing(10, DamageType.NECROTIC, on=victim)
    if burn is not None:
        burn.on_end.append(
            lambda: c.penalty("attack", 2, until=When.EONT, on=victim)
        )


@power(
    "m1450a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m1450a3(c: Cast) -> None:
    """The concealment is against the creatures this row dazed and nobody
    else, so it is one standing effect with a gate on `attacker` rather than
    one per victim -- the gate is read where concealment is read, which is
    the attack context.

    The card prints a recharge die *and* says it comes back when the m1450 is
    first bloodied; both are honoured.
    """
    if c.first:
        _rearms_when_bloodied(c)
        c.conceal(
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: bool(
                (who := ctx.get("attacker")) is not None
                and who in c.suffering(c.ref)
            ),
        )
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m1450a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=14),
)
def m1450a4(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit, and the Aftereffect
    follows it ending whichever way it ended."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m1573
# ==========================================================================


@power(
    "m1573a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
)
def m1573a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1573a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
)
def m1573a1(c: Cast) -> None:
    """"Before or after making this attack" is one shift either way, so it is
    taken before: a shift afterwards cannot bring the target into reach, and
    a row that shifts first can swing at somebody it could not have reached."""
    c.shift(2)
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m1573a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.ZONE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d4", 5, kind=LIMITED),
)
def m1573a2(c: Cast) -> None:
    """"A m1573 is immune to its own" is `Ident.ref` and nothing else, which
    `c.burns` has no side to say -- so the two printed moments are watched by
    hand with its own kind excused."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=True)
    _burns_others(c, zone, "1d4")


@power(
    "m1573a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d4", 5, kind=LIMITED),
)
def m1573a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


_M1573_SHAPE = "m1573a4 shape"


@power(
    "m1573a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1573a4(c: Cast) -> None:
    """A shape with no mechanics inside it; the minor action it cost is the
    printed way back out."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M1573_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M1573_SHAPE)
    c.note(f"{c.ref}: it takes the shape of a Medium humanoid")


# ==========================================================================
# m1599
# ==========================================================================


@power(
    "m1599a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4),
)
def m1599a0(c: Cast) -> None:
    """One burn, one saving throw, and each failure makes it worse.

    `escalate` runs on a *failed* save and is handed the effect, so each step
    ends the hold it came from before laying the next; two separate holds
    would be two saving throws against one printed bite. The last step
    carries no escalation, which is where the chain stops.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref

    def worse(condition: Condition, then: Any) -> Any:
        def step(eff: Effect) -> None:
            c.world.effects.end(eff, "the saving throw failed")
            c.world.effects.apply(
                eff.owner,
                me,
                When.SAVE_ENDS,
                label=ref,
                conditions=(condition,),
                ongoing=(5, DamageType.POISON),
                escalate=then,
            )

        return step

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=ref,
        ongoing=(5, DamageType.POISON),
        escalate=worse(Condition.SLOWED, worse(Condition.UNCONSCIOUS, None)),
    )


@power(
    "m1599a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d6", 6, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("c.grant_action(move_zone)",),
)
def m1599a1(c: Cast) -> None:
    """A zone that keeps attacking whoever walks into it.

    "Any enemy that enters or starts its turn inside is subject to attack" is
    this row swung again at that one creature, so the body re-enters itself
    through `use` -- which is legal once the first use is over -- and the zone
    is laid only when it is not already standing, or every re-entry would
    build another one.

    The dropped clause is moving the zone: `actions._granted` is read for
    five words and `move_zone` is not one of them, so granting it would lay
    something nothing consults. `c.move_zone` itself exists and does the
    work; what is missing is an action a creature can spend on it.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    if not c.first:
        return
    if any(z.label == c.ref and z.owner == c.me for _zid, z in c.world.zones.all()):
        return
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=True)
    me, ref = c.me, c.ref

    def sting(who: int) -> None:
        if who == me or team(c.world, who) is team(c.world, me):
            return
        use(c.world, me, ref, targets=[who], spend=False)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            sting(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            sting(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{ref} in")
    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{ref} stays")


@power(
    "m1599a2",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("Zone.sees_through",),
)
def m1599a2(c: Cast) -> None:
    """Darkness that blinds whoever is standing in it.

    `blocks_sight` is the field, and it blocks it for everybody -- there is
    nothing on a zone that excuses its maker and its own kind, which is the
    dropped clause. The blinding is a hold carried for as long as a creature
    is inside, diffed off the zone's own membership rather than hung on a
    clock: the printed line is about being there, not about arriving.
    """
    zone = c.zone(c.area(), label=c.ref, until=When.EONT, blocks_sight=True)
    _held_inside(
        c,
        zone,
        lambda who: c.blinded(until=When.ENCOUNTER, on=who),
        eligible=lambda who: not _same_stock(c.world, c.me, who),
    )


# ==========================================================================
# m1910
# ==========================================================================


@power(
    "m1910a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
    dropped=("c.prone(dc=)",),
)
def m1910a0(c: Cast) -> None:
    """The prone plays; what is dropped is the check standing in the way of
    getting up. `c.prone` lasts until the creature stands and takes a
    duration, not a difficulty -- standing up is a move action and nothing
    puts a roll in front of it."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1910a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=FORT, printed=16),
    dropped=("c.merge(on=)",),
)
def m1910a1(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    The burial is the dropped clause. `c.merge` puts a creature inside
    something solid and cuts line of effect both ways, which is exactly the
    printed sentence -- but it aims at the caster only and takes no `on=`, so
    there is no way to bury somebody else.

    The rest plays: stunned on a saving throw, and the first failure trades
    the stun for domination, which is `escalate` ending the hold it is handed
    before laying the next.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def dominate(eff: Effect) -> None:
        c.world.effects.end(eff, "the saving throw failed")
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=eff.owner)

    c.condition(
        Condition.STUNNED, until=When.SAVE_ENDS, on=victim, escalate=dominate
    )


@power(
    "m1910a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m1910a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(4)


_M1910_BLOODIED = "it is first bloodied"


@power(
    "m1910a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1910_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M1910_BLOODIED),
)
def m1910a3(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and only then, so "first" needs
    nothing on top of the trigger. The row it hands back is an encounter
    power, which `Powers.restore` gives a use to exactly as it does a
    recharge."""
    _uses_again(c, "m1910a1")


@power(
    "m1910a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1910a4(c: Cast) -> None:
    """The puppet acts, and the m1910 chooses which of the three it does.

    Domination is an ordinary condition whose effect carries its source, so
    "a creature dominated by it" is read off that and not off the condition
    alone -- two dominators on one board would otherwise share puppets.

    The basic attack is aimed explicitly: `c.basic(who=)` names who swings
    and the victim still defaults to `c.target`, which is None on a row with
    no target line, so the blow would simply not have happened.
    """
    puppets = _dominated_by(c)
    puppet = c.choose(puppets, f"{c.ref}: which puppet moves") if puppets else None
    if puppet is None:
        return
    doing = c.choose(["walk", "shift", "attack"], f"{c.ref}: what it is made to do")
    if doing == "walk":
        c.move(c.speed_of(puppet), who=puppet)
    elif doing == "shift":
        c.shift(1, who=puppet)
    else:
        prey = [f for f in c.enemies() if f != puppet and distance_between(c.world, puppet, f) <= 1]
        if prey:
            c.basic(who=puppet, on=prey[0])


@power(
    "m1910a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1910a5(c: Cast) -> None:
    """`at=` names the mode travelled at, which is what makes this a burrow
    and not a walk."""
    c.move(6, at="burrow")


# ==========================================================================
# m1921
# ==========================================================================


_M1921_STRUCK = "an enemy hits the m1921 with a melee attack"


def _hit_me_in_melee(world: World, me: int, ev: Any) -> bool:
    """`Hit` names its subject `target` and carries no `actor`, so `about_me`
    is false here forever; the reach comes off the row named in the event."""
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None or team(world, attacker) is team(world, me):
        return False
    return _reach_kind(ev) == "melee"


@power(
    "m1921a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=16),
    trigger=_M1921_STRUCK,
    on=Trigger(Hit, when=_hit_me_in_melee, text=_M1921_STRUCK),
)
def m1921a0(c: Cast) -> None:
    """The creature struck at is the one the trigger names and not whoever
    the chooser handed over: an immediate action routinely declares a target
    line and then aims itself off its own trigger.

    No damage line: the teleport is the whole of the hit.
    """
    ev = c.trigger
    victim = getattr(ev, "attacker", None) if ev is not None else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.teleport(8, who=victim)


@power(
    "m1921a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(8),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=14),
    dropped=("c.flee(avoid=)",),
)
def m1921a1(c: Cast) -> None:
    """No damage line: the flight is the whole of the hit, and it is the
    target's own movement, which is what `c.flee` is -- a push of that length
    would be forced movement and would go through walls of effect a walk
    cannot.

    What is dropped is the pathing: the printed line has the target pick its
    way round hazardous and difficult ground, and `c.flee` takes no
    preference to pass down.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.flee(c.speed_of(victim) + 4, on=victim)


@power(
    "m1921a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
)
def m1921a2(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1921a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d10", 8, dtype=DamageType.PSYCHIC),
)
def m1921a3(c: Cast) -> None:
    """The penalty is to one defence, so it is one modifier rather than the
    four a "-2 to all defenses" line wants, and the card prints no type word
    in front of it."""
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


# ==========================================================================
# m2070
# ==========================================================================


@power(
    "m2070a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m2070a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2070a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 6, dtype=DamageType.THUNDER),
)
def m2070a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m2070a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 6, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m2070a2(c: Cast) -> None:
    """Two numbers for one blow: the base stays in the header where a rescale
    can find it and the difference is added in the body, which is the reading
    the minion sweep settled. On a miss the difference is halved along with
    the rest, so it goes through `c.half_damage` rather than `c.flat`.

    `half_on_miss` is declared data nothing reads, so the Miss branch is
    written out. The recharge die and the printed "recharges when first
    bloodied" are both honoured.
    """
    if c.first:
        _rearms_when_bloodied(c)
    bloodied = _is_bloodied(c.world, c.me)
    if c.strike():
        c.hit()
        if bloodied:
            c.flat(5, dtype=DamageType.THUNDER)
    else:
        c.hit(half=True)
        if bloodied:
            c.half_damage(0, 5, dtype=DamageType.THUNDER)


_M2070_SHAPE = "m2070a3 shape"


@power(
    "m2070a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m2070a3(c: Cast) -> None:
    """A shape with no mechanics inside it; the minor action it cost is the
    printed way back out."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M2070_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M2070_SHAPE)
    c.note(f"{c.ref}: it takes the shape of a Medium humanoid")


@power(
    "m2070a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2070a4(c: Cast) -> None:
    c.teleport(10)


# ==========================================================================
# m2090
# ==========================================================================


@power(
    "m2090a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 0),
)
def m2090a0(c: Cast) -> None:
    """"1d8 damage plus 1d8 fire damage" is two packets, and resistance reads
    them separately -- so the untyped one is the declared line and the fire
    one is rolled beside it."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2090a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 0),
)
def m2090a1(c: Cast) -> None:
    """The Secondary Attack has no ref of its own, so its printed total goes
    through `_secondary`, which takes the level term back out the way the
    header's `Attack(printed=)` does. It reaches two enemies measured from the
    first target rather than from the m2090, which is what the printed line
    says, and the m2090's own side is not among them."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d8", dtype=DamageType.FIRE)
    c.ongoing(5, DamageType.FIRE)
    first = c.target
    if first is None:
        return
    nearby = [
        f
        for f in c.enemies()
        if f != first and distance_between(c.world, first, f) <= 5
    ]
    for extra in nearby[:2]:
        if _secondary(c, 15, REF, extra):
            c.damage("1d8", dtype=DamageType.FIRE, on=extra)
            c.ongoing(5, DamageType.FIRE, on=extra)


@power(
    "m2090a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d10", 6, dtype=DamageType.FIRE),
)
def m2090a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2090a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2090a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2090a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Wall(8, 10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.FIRE],
    dropped=("c.wall(cost=)",),
)
def m2090a4(c: Cast) -> None:
    """A wall of fire, and three different tolls.

    `c.wall(solid=False)` is a barrier a creature can step into, which is
    what this one is: the printed cost of entering is three extra squares and
    `difficult` is the only roughness a wall carries, so the exact price is
    the dropped clause.

    The three payouts are the three printed moments and are watched
    separately: adjacent at the start of a turn is the small one, inside at
    the start of a turn or on stepping in is the large one. "Four high" and
    "heavily obscured" are `blocks_sight`, which is the one thing a zone says
    about seeing.
    """
    me = c.me
    wall = c.wall(
        size=8,
        blocks_sight=True,
        solid=False,
        difficult=True,
        until=When.EONT,
        sustain=MINOR,
        label=c.ref,
    )
    if not wall:
        return

    def squares_of() -> frozenset[Any]:
        live = c.world.get(wall, Zone)
        return frozenset(live.squares) if live is not None else frozenset()

    def began(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(wall):
            c.damage("3d6", 5, dtype=DamageType.FIRE, on=ev.actor, detail=c.ref)
        elif any(
            max(abs(sq[0] - w[0]), abs(sq[1] - w[1])) <= 1
            for sq in squares(c.world, ev.actor)
            for w in squares_of()
        ):
            c.damage("1d6", 5, dtype=DamageType.FIRE, on=ev.actor, detail=c.ref)

    def stepped(ev: ZoneEntered) -> None:
        if ev.zone == wall and ev.actor != me:
            c.damage("3d6", 5, dtype=DamageType.FIRE, on=ev.actor, detail=c.ref)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} beside")
    c.watch(ZoneEntered, stepped, until=When.ENCOUNTER, on=me, label=f"{c.ref} inside")


@power(
    "m2090a5",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2090a5(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m2256
# ==========================================================================


@power(
    "m2256a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m2256a0(c: Cast) -> None:
    """The burn is a second packet and is poison; the declared line is not,
    because the printed damage is untyped and only the ongoing is named.

    This stat block is a second printing of m45 -- same defences, same nine
    abilities, same order -- so each row takes the reading its twin settled.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2256a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m2256a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2256a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2256a2(c: Cast) -> None:
    """Two swings of the row that prints them. The printed Effect does not say
    whether they land on one creature or two, so the header takes up to two
    and a single target is hit twice."""
    if c.target is not None:
        _volley(c, "m2256a1", c.target)


@power(
    "m2256a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2256a3(c: Cast) -> None:
    """It flies past and bites on the way.

    Declared with no target: the dispatcher aims a row before the body runs,
    and the creature bitten here is chosen from everything within the flight
    rather than from whatever is already in reach. `c.no_provoke(from_=)` is
    the printed exemption and it names the target and nobody else.
    """
    foes = sorted(f for f in c.enemies() if c.distance(f) <= 12)
    victim = c.choose(foes, f"{c.ref}: who it dives at") if foes else None
    if victim is None:
        return
    c.no_provoke(from_=victim, until=When.EOT)
    c.run_at(victim)
    use(c.world, c.me, "m2256a0", targets=[victim], spend=False)


_M2256_STILL = "an adjacent enemy does not move on its turn"


@power(
    "m2256a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6),
    trigger=_M2256_STILL,
    on=Trigger(TurnEnd, when=_stood_still, text=_M2256_STILL),
)
def m2256a4(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2256a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=15),
)
def m2256a5(c: Cast) -> None:
    """No damage line: the slide is the whole of the hit."""
    if c.strike():
        c.slide(2)


@power(
    "m2256a6",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d10", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2256a6(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the burn, so the
    printed sentence gets the one saving throw it prints. The Aftereffect
    hangs on that effect's ending rather than on `escalate`: escalation runs
    on a *failed* save, and an aftereffect is what follows either way."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.POISON),
    )
    if hold is not None:
        hold.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


_M2256_BLOODIED = "it is first bloodied"


@power(
    "m2256a7",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger=_M2256_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2256_BLOODIED),
)
def m2256a7(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and only then, so "when first
    bloodied" needs nothing on top of the trigger."""
    _uses_again(c, "m2256a6")


@power(
    "m2256a8",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m2256a8(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit, and the Aftereffect
    follows the stun ending whichever way it ended."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m2323
# ==========================================================================

_M2323_STANCE = "m2323a3 stance"


@power(
    "m2323a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m2323a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2323_DISTURBED = "an enemy attacks the m2323 while m2323a3 is standing"


def _attacked_while_still(world: World, me: int, ev: Any) -> bool:
    """The trigger has two halves and the second is a state, not an event, so
    it is asked here rather than assumed: `AttackDeclared` names its subject
    `target`, which is why `about_me` cannot be used."""
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None or team(world, attacker) is team(world, me):
        return False
    return any(eff.label == _M2323_STANCE for eff in world.effects.of(me))


@power(
    "m2323a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, half_on_miss=True),
    trigger=_M2323_DISTURBED,
    on=Trigger(AttackDeclared, when=_attacked_while_still, text=_M2323_DISTURBED),
)
def m2323a1(c: Cast) -> None:
    """The triggering enemy is read off the event rather than off `c.target`:
    an immediate action declares a target line and is then aimed at whoever
    its trigger names.

    `half_on_miss` is declared data nothing reads, so the Miss branch is
    written out -- and it lays a daze instead of the domination, which is the
    difference worth writing.
    """
    ev = c.trigger
    victim = getattr(ev, "attacker", None) if ev is not None else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)
    else:
        c.hit(on=victim, half=True)
        c.dazed(until=When.EONT, on=victim)


_M2323_BEREFT = "an enemy kills an ally of the m2323 in its line of sight"


def _ally_killed_in_sight(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    killer = getattr(ev, "source", None)
    return killer is not None and team(world, killer) is not team(world, me)


@power(
    "m2323a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.ACID),
    trigger=_M2323_BEREFT,
    on=Trigger(Dropped, when=_ally_killed_in_sight, text=_M2323_BEREFT),
)
def m2323a2(c: Cast) -> None:
    """"Killed by an enemy" is `Dropped.source`, which is who crossed the line
    and is None when nothing did -- a burn or a failed death save is not a
    kill. Line of sight is not asked: `Dropped` carries no position and the
    burst is measured from the m2323 anyway."""
    if c.strike():
        c.hit()


@power(
    "m2323a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m2323a3(c: Cast) -> None:
    """Three things on one clock, and a fourth that takes them all away.

    The resistance is the caster's, so it needs no `on=`; the extra psychic
    damage is the allies', gated on the swing being a melee one -- which is
    read off the row behind the modifier rather than off a `ranged` key the
    damage context does not carry.

    "If the m2323 moves, the effect ends" is `MoveEnd`, which is after the
    move has happened: the row is not trying to stop the move, only to notice
    it. Everything laid here is ended together, so the stance cannot half
    survive. The label is what m2323a1's trigger looks for.
    """
    me = c.me
    laid = [
        c.effect(_M2323_STANCE, until=When.EONT, on=me),
        c.resist(20, until=When.EONT),
    ]
    for mate in c.allies():
        if mate == me:
            continue
        laid.append(
            c.bonus(
                "damage",
                0,
                dice="1d6",
                dtype=DamageType.PSYCHIC,
                on=mate,
                until=When.EONT,
                when=_melee_ctx,
            )
        )

    def broken(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        for eff in laid:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "it moved")

    c.watch(MoveEnd, broken, until=When.EONT, on=me, label=f"{c.ref} broken")


# ==========================================================================
# m2347
# ==========================================================================


@power(
    "m2347a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d4", 6),
)
def m2347a0(c: Cast) -> None:
    """One hold, one saving throw at -2, and each failure trades up.

    The penalty to the save is a field on the effect, which is the only place
    a printed "save at -2" can live; `escalate` runs on a failed save and is
    handed the effect, so each step ends the hold it came from before laying
    the next.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref

    def worse(condition: Condition, then: Any) -> Any:
        def step(eff: Effect) -> None:
            c.world.effects.end(eff, "the saving throw failed")
            c.world.effects.apply(
                eff.owner,
                me,
                When.SAVE_ENDS,
                label=ref,
                conditions=(condition,),
                ongoing=(5, DamageType.POISON),
                save_mod=-2,
                escalate=then,
            )

        return step

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=ref,
        conditions=(Condition.SLOWED,),
        ongoing=(5, DamageType.POISON),
        save_mod=-2,
        escalate=worse(Condition.IMMOBILIZED, worse(Condition.STUNNED, None)),
    )


_M2347_HELD = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


@power(
    "m2347a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m2347a1(c: Cast) -> None:
    """`Target` filters on side, count and size and not on what a creature is
    suffering, so the aim is moved to one the printed line allows rather than
    thrown away -- `Target.kind` is the gap. The reach is the creature's own
    2, which is what a "melee" line with no number means on this block."""
    victim = _restricted_to(
        c, 2, lambda who: any(c.is_(cond, on=who) for cond in _M2347_HELD)
    )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


_M2347_BLOODIED = "it is first bloodied"


@power(
    "m2347a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2347_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2347_BLOODIED),
)
def m2347a2(c: Cast) -> None:
    """It walks and then swings twice, with both swings aimed at whoever drew
    the blood where that creature is in reach -- `Bloodied.source` is who
    crossed the line, which is exactly the preference the card prints.

    The two rows are reached through `c.use_power`, which never charges an
    action of its own: this row's header has already said what it costs.
    """
    ev = c.trigger
    culprit = getattr(ev, "source", None) if ev is not None else None
    c.move(6)
    prey = [f for f in c.enemies() if c.distance(f) <= 2]
    victim = culprit if culprit in prey else next(iter(prey), None)
    if victim is None:
        return
    c.use_power("m2347a0", on=victim)
    c.use_power("m2347a1", on=victim)


@power(
    "m2347a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2347a3(c: Cast) -> None:
    """How far it threatens is the whole of this line, and `c.threatens` is
    the field that says it -- an opportunity window is opened against
    everything inside that reach rather than only against adjacent squares."""
    c.threatens(2)


# ==========================================================================
# m2348
# ==========================================================================


@power(
    "m2348a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m2348a0(c: Cast) -> None:
    """Two at a time is a count, so a third grab is simply not taken -- the
    row still deals its damage, which is what the card does."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if len(_holding(c.world, c.me)) < 2:
        c.grab(on=victim)


@power(
    "m2348a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("1d10", 6),
)
def m2348a1(c: Cast) -> None:
    """Only something it already holds, which `Target` cannot filter on, so
    the aim is moved to a creature that qualifies."""
    held = set(_holding(c.world, c.me))
    victim = _restricted_to(c, 3, lambda who: who in held)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)


@power(
    "m2348a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m2348a2(c: Cast) -> None:
    """A burst with no "within", so it is measured from the m2348. Everybody
    in it takes the damage and the pull; only the first two are grabbed, which
    is the printed count."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.pull(2, on=victim)
    if len(_holding(c.world, c.me)) < 2:
        c.grab(on=victim)


@power(
    "m2348a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2348a3(c: Cast) -> None:
    c.threatens(3)


@power(
    "m2348a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2348a4(c: Cast) -> None:
    """Narrative only: a Stealth check made before initiative is rolled, with
    nothing on a board it changes once the fight has started."""
    c.note(f"{c.ref}: it can pass for the ordinary article until it moves")


@power(
    "m2348a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2348a5(c: Cast) -> None:
    """`kind` left empty is every sort of rough going, which is what an
    unqualified line means."""
    c.ignores_difficult()


# ==========================================================================
# m2522
# ==========================================================================


@power(
    "m2522a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    dropped=("Damage(dtypes=)",),
)
def m2522a0(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two types,
    which is what resistance reads as a unit.

    "Invisible to the target until she attacks" is one creature's blindness
    and not a general veil, so `to=` names it; the roll is what gives her
    away whether or not it lands, which is why the watch is on `AttackRolled`
    and is torn down with the veil.
    """
    if not c.strike():
        return
    c.damage(
        "2d6", 4,
        dtypes=(DamageType.FIRE, DamageType.NECROTIC),
        detail=c.ref,
    )
    victim = c.target
    if victim is None:
        return
    veil = c.invisible(to=victim, on=c.me, until=When.ENCOUNTER)
    if veil is None:
        return
    me = c.me

    def reveal(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(
        AttackRolled, reveal, until=When.ENCOUNTER, on=me, label=f"{c.ref} seen"
    )
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


@power(
    "m2522a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m2522a1(c: Cast) -> None:
    """"No line of sight to anything beyond 2 squares" is `c.sight_range`,
    which is the printed sentence exactly and is aimed at the target."""
    if c.strike():
        c.hit()
        if c.target is not None:
            c.sight_range(2, on=c.target, until=When.EONT)


@power(
    "m2522a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m2522a2(c: Cast) -> None:
    """Two basic attacks, not two uses of a named row -- `c.basic` swings
    whichever row this creature's basic attack actually is. One target is
    swung at twice, which is the only reading that loses nothing."""
    if not c.first:
        return
    picks = list(c.targets[:2]) if len(c.targets) > 1 else [c.target, c.target]
    for victim in picks:
        if victim is not None:
            c.basic(on=victim)


_M2522_SAW_BLOOD = "an enemy within sight of the m2522 becomes bloodied"


@power(
    "m2522a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("4d8", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.no_surges()",),
)
def m2522a3(c: Cast) -> None:
    """The printed recharge sentence is laid on top of the die: the number
    stays in the header, because that is what `actions.recharge` rolls and
    what the card shows, and the two only ever make the row available sooner.

    Barring healing surges is the dropped clause -- `c.no_healing` stops
    healing outright, which is wider than the card.
    """
    if c.first:
        _recharge_on(
            c,
            Bloodied,
            lambda ev: getattr(ev, "actor", None) in c.enemies()
            and c.can_see(getattr(ev, "actor", None)),
        )
    if c.strike():
        c.hit()


@power(
    "m2522a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2522a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m2522a5",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.NECROTIC],
)
def m2522a5(c: Cast) -> None:
    """"Enemies adjacent to her when she teleports" is the set before the
    blink, so it is taken first -- afterwards she is somewhere else and the
    sentence would name whoever she landed next to."""
    caught = [f for f in c.enemies() if c.adjacent(f)]
    c.teleport(6)
    c.insubstantial(until=When.SONT, on=c.me)
    for foe in caught:
        c.damage("1d10", 5, dtype=DamageType.NECROTIC, on=foe, detail=c.ref)
        c.prone(on=foe)


# ==========================================================================
# m2550
# ==========================================================================


@power(
    "m2550a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4),
)
def m2550a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2550a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 4),
)
def m2550a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2550a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 6, dtype=DamageType.POISON),
)
def m2550a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m2550a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
)
def m2550a3(c: Cast) -> None:
    """No damage line: the burn and the slow are the whole of the hit, and
    "save ends both" makes them one effect with one saving throw."""
    if c.strike():
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m2550a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(10),
    target=EACH_ALLY,
)
def m2550a4(c: Cast) -> None:
    """"All allies" does not include the creature granting it, so `EACH_ALLY`
    -- which does -- passes itself over. The card prints no type word in
    front of the number, so it is untyped."""
    if c.target is None or c.target == c.me:
        return
    c.bonus("speed", 5, on=c.target, until=When.EONT)


@power(
    "m2550a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING],
)
def m2550a5(c: Cast) -> None:
    """Bloodied allies only, and the creature itself is not one of its own
    allies on this card."""
    who = c.target
    if who is None or who == c.me or not _is_bloodied(c.world, who):
        return
    c.heal(15, on=who)


# ==========================================================================
# m2558
# ==========================================================================


@power(
    "m2558a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m2558a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The burn is a second packet and is the only acid in the line."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m2558a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
)
def m2558a1(c: Cast) -> None:
    """Three swings of the row that prints them. The printed Effect does not
    say whether they land on one creature or three, so the header takes up to
    three and a short list is padded with its last target -- which is the only
    reading under which a single enemy takes all three."""
    if not c.first:
        return
    picks = list(c.targets[:3])
    while picks and len(picks) < 3:
        picks.append(picks[-1])
    for victim in picks:
        if alive(c.world, victim):
            use(c.world, c.me, "m2558a0", targets=[victim], spend=False)


@power(
    "m2558a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2558a2(c: Cast) -> None:
    """Blink, swing, blink again. The swings go through `c.use_power`, which
    charges no action of its own -- this row's header has already said what it
    costs."""
    c.teleport(6)
    c.use_power("m2558a1")
    c.teleport(6)
    c.insubstantial(until=When.SONT, on=c.me)


@power(
    "m2558a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=16),
)
def m2558a3(c: Cast) -> None:
    """No damage line: the burn is the whole of the hit, and each failed save
    trades up. The last step is petrification with no save, which is where the
    chain stops -- so it carries no escalation of its own.

    Every step keeps the burn, because the printed sentence restates it; one
    effect means one saving throw against one printed sentence.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref

    def stone(eff: Effect) -> None:
        c.world.effects.end(eff, "the saving throw failed")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def slow(eff: Effect) -> None:
        c.world.effects.end(eff, "the saving throw failed")
        c.world.effects.apply(
            eff.owner,
            me,
            When.SAVE_ENDS,
            label=ref,
            conditions=(Condition.SLOWED,),
            ongoing=(10, DamageType.ACID),
            escalate=stone,
        )

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=ref,
        ongoing=(10, DamageType.ACID),
        escalate=slow,
    )


@power(
    "m2558a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d10", 5, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m2558a4(c: Cast) -> None:
    """`half_on_miss` is declared data nothing reads, so the Miss branch is
    written out."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M2558_BLOODIED = "it is first bloodied"


@power(
    "m2558a5",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    trigger=_M2558_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2558_BLOODIED),
)
def m2558a5(c: Cast) -> None:
    """The card names a row rather than a recharge, so nothing is handed back
    -- the row is at-will and `c.use_power` simply swings it."""
    c.use_power("m2558a3")


# ==========================================================================
# m2597
# ==========================================================================


@power(
    "m2597a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d10", 2, dtype=DamageType.NECROTIC),
)
def m2597a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2597a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC),
)
def m2597a1(c: Cast) -> None:
    """The card prints no clock on the penalty at all, and the end of the
    attacker's next turn is what an unqualified one means. Four modifiers on
    one effect rather than four effects, because there is one printed sentence
    to take off again."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.EONT,
        label=c.ref,
        mods=[(victim, m) for m in _softened(c, defences=2)],
    )


@power(
    "m2597a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2597a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m2607
# ==========================================================================


@power(
    "m2607a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m2607a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


_M2607_THRALL = "m2607a1 thrall"


@power(
    "m2607a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=AC, printed=17),
)
def m2607a1(c: Cast) -> None:
    """A thrall that will not strike him and steps in front of blows.

    No damage line at all: the primary's whole hit is the secondary attack,
    whose printed total goes through `_secondary` because a second attack line
    has no ref to live in.

    The interposition is written where `c.redirect` would be if this were an
    interrupt: `AttackDeclared` in the BEFORE window is the same moment, and
    setting `ev.target` there is exactly what `c.redirect` does -- it reads
    `c.trigger`, which a plain watch does not have.

    Three ways out, all of them hung on the one hold: his side attacking the
    thrall, him dropping, and the thrall dying. One at a time.
    """
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    if not _secondary(c, 16, WILL, victim):
        return
    me = c.me
    _only_one(c, _M2607_THRALL)
    hold = c.effect(_M2607_THRALL, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return
    c.cannot_attack(on=victim, against=me, until=When.ENCOUNTER)

    def interpose(ev: AttackDeclared) -> None:
        if hold.ended or ev.target != me or ev.attacker == victim:
            return
        if not alive(c.world, victim) or distance_between(c.world, me, victim) > 1:
            return
        if _reach_kind(ev) not in ("melee", "ranged"):
            return
        ev.target = victim
        result = getattr(ev, "result", None)
        if result is not None:
            result.target = victim

    def broken(ev: Any) -> None:
        if hold.ended:
            return
        attacker = getattr(ev, "attacker", None)
        if (
            attacker is not None
            and team(c.world, attacker) is team(c.world, me)
            and getattr(ev, "target", None) == victim
        ):
            c.world.effects.end(hold, "his own side struck the thrall")

    def gone(ev: Any) -> None:
        if not hold.ended and getattr(ev, "actor", None) in (me, victim):
            c.world.effects.end(hold, "the charm is over")

    hold.subs.append(
        c.world.bus.on(AttackDeclared, interpose, window=Window.BEFORE, owner=me)
    )
    hold.subs.append(c.world.bus.on(AttackDeclared, broken, owner=me))
    hold.subs.append(c.world.bus.on(Dropped, gone, owner=me))


@power(
    "m2607a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m2607a2(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit, and it runs on
    a turn clock rather than a saving throw."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


_M2607_AIMED_AT = "he is targeted by an attack"


def _aimed_at_me(world: World, me: int, ev: Any) -> bool:
    """`AttackDeclared` names its subject `target` and carries no `actor`, so
    `about_me` would be false here for the whole fight."""
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    return attacker is not None and team(world, attacker) is not team(world, me)


@power(
    "m2607a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
    trigger=_M2607_AIMED_AT,
    on=Trigger(AttackDeclared, when=_aimed_at_me, text=_M2607_AIMED_AT),
)
def m2607a3(c: Cast) -> None:
    """"Attacker only" names the creature off the trigger, not off the
    chooser. The domination lands inside the interrupt window, which is before
    the roll -- a dominated creature's attack is the dominator's to spend, so
    the blow stops being made rather than being cancelled."""
    ev = c.trigger
    victim = getattr(ev, "attacker", None) if ev is not None else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


_M2607_SHAPE = "m2607a4 shape"


@power(
    "m2607a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m2607a4(c: Cast) -> None:
    """A shape with no mechanics inside it; the minor action it cost is the
    printed way back out."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M2607_SHAPE:
            c.world.effects.end(eff, "he changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M2607_SHAPE)
    c.note(f"{c.ref}: he takes the shape of a Medium humanoid")


# ==========================================================================
# m3313
# ==========================================================================


@power(
    "m3313a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 5),
)
def m3313a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The defence is Reflex, which is unusual for a weapon line and is
    written as printed rather than corrected."""
    if c.strike():
        c.hit()


@power(
    "m3313a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 0, dtype=DamageType.PSYCHIC),
)
def m3313a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m3313a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m3313a2(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m3313a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3313a3(c: Cast) -> None:
    """Which holds are charms or fears is read off the keywords of the row
    that laid each one -- `keywords_of` takes the effect's label, which is
    that ref, because an effect carries no keywords of its own.

    `c.save(against=)` wants the label of the hold to roll against, so each
    qualifying hold gets its own throw rather than one throw taking whichever
    save-ends effect came first.
    """
    who = c.target
    if who is None:
        return
    for eff in list(c.world.effects.of(who)):
        if eff.when is not When.SAVE_ENDS:
            continue
        if keywords_of(eff.label) & {Keyword.CHARM, Keyword.FEAR}:
            c.save(on=who, bonus=3, against=eff.label)


_M3313_HURT = "the m3313 takes damage"


@power(
    "m3313a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M3313_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M3313_HURT),
)
def m3313a4(c: Cast) -> None:
    """Unseen until it attacks, and no later than the end of its next turn.

    The attack roll gives it away whether or not the blow lands, which is why
    the watch is on `AttackRolled`, and the watch is torn down with the veil
    -- a second vanishing would otherwise inherit the first one's listener.
    `DamageApplied` names its subject `target`, so `targets_me` and not
    `about_me`.
    """
    veil = c.invisible(on=c.me, until=When.EONT)
    if veil is None:
        return
    me = c.me

    def reveal(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(
        AttackRolled, reveal, until=When.EONT, on=me, label=f"{c.ref} seen"
    )
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


@power(
    "m3313a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3313a5(c: Cast) -> None:
    """Narrative only: a Stealth check taken at the moment initiative is
    rolled, which is before there is a board to hide on."""
    c.note(f"{c.ref}: with cover or concealment it starts the fight hidden")


# ==========================================================================
# m3753
# ==========================================================================


@power(
    "m3753a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 1),
)
def m3753a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m3753a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC),
)
def m3753a1(c: Cast) -> None:
    """"Save ends" covers all four defences at once, so it is one effect
    carrying four modifiers and one saving throw."""
    if not c.strike():
        return
    c.hit()
    if c.target is not None:
        _held_and_softened(c, c.target, defences=2)


@power(
    "m3753a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d8", 1, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3753a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m3796
# ==========================================================================


@power(
    "m3796a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 7),
)
def m3796a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3796a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 5),
)
def m3796a1(c: Cast) -> None:
    """The declared line is untyped: only the burn is named necrotic.

    The pack closes in when the burn bites, which is a `DamageApplied` whose
    `detail` carries the effect that dealt it -- `Effects._on_turn_start`
    stamps `str(eff)` there and the label inside it is this row's ref. The
    listener lives on the burn's own `subs` so it dies with the burn.

    Each ally steps for itself, which `c.shift(who=)` is; `_step_toward` moves
    the caster and would have walked the m3796 instead.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    burn = c.ongoing(5, DamageType.NECROTIC, on=victim)
    if burn is None:
        return
    me, ref = c.me, c.ref

    def close_in(ev: DamageApplied) -> None:
        if ev.target != victim or ref not in ev.detail:
            return
        for mate in c.allies():
            if distance_between(c.world, mate, victim) <= 3:
                _shift_closer(c, mate, victim)

    burn.subs.append(c.world.bus.on(DamageApplied, close_in, owner=me))


@power(
    "m3796a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=16),
)
def m3796a2(c: Cast) -> None:
    """No damage line: the burn and the daze are the whole of the hit, and
    "save ends" covers both on one throw. "Each Failed Save" is `escalate`,
    which runs on a failure and is handed the effect -- and here it pays out
    rather than worsening, so the hold is left standing."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def mend(eff: Effect) -> None:
        nearby = [
            a for a in c.allies() if distance_between(c.world, a, eff.owner) <= 5
        ]
        if nearby:
            c.heal(10, on=nearby[0])

    c.condition(
        Condition.DAZED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(10, DamageType.UNTYPED),
        escalate=mend,
    )


_M3796_ALLY_ROSE = "an ally within 10 squares regains hit points"


def _ally_healed_near(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    return team(world, who) is team(world, me) and distance_between(world, me, who) <= 10


@power(
    "m3796a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.IMPLEMENT],
    trigger=_M3796_ALLY_ROSE,
    on=Trigger(Healed, when=_ally_healed_near, text=_M3796_ALLY_ROSE),
    dropped=("Healed.detail",),
)
def m3796a3(c: Cast) -> None:
    """The healing goes to the ally the trigger names, which is
    `c.trigger.target` -- this row has no target line, so `c.target` is None.

    The dropped clause is the narrowing: the card fires only when the ally got
    back up through m3796a4, and `Healed` carries source, target, amount and
    hit points and nothing saying what did the healing. So this answers any
    ally's healing, which is wider than the card, and the gap is named rather
    than papered over.
    """
    ev = c.trigger
    ally = getattr(ev, "target", None) if ev is not None else None
    if ally is None:
        return
    c.heal(20, on=ally)


@power(
    "m3796a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3796a4(c: Cast) -> None:
    """It falls and gets back up with 10 hit points unless acid or fire
    finished it, and it is stood up inside the blow that felled it: nothing in
    the engine owes a corpse an action, and a body that waits a round is one
    `threat_removed` has already written off. The prone is the printed one."""
    _rises_unless(c, 10, DamageType.ACID, DamageType.FIRE)


# ==========================================================================
# m3804
# ==========================================================================


@power(
    "m3804a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 7),
)
def m3804a0(c: Cast) -> None:
    """This stat block is a second printing of m193 -- same defences, same
    five abilities, same order -- so each row takes the reading its twin
    settled."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3804a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m3804a1(c: Cast) -> None:
    """A blow marked before it is struck.

    No damage line: the mark is the whole of the hit. "Treated as a critical
    hit" is set on the live `AttackResult` in the `Hit` window, which is
    before the striking body rolls its damage and is where `c.damage` reads
    the question. `c.maximise` cannot say it: it reads the damage line of the
    row that applied it, and this row has none.

    The extra die is rolled and dealt flat rather than added to the declared
    line, because the declared line is about to be maximised and an extra
    *rolled* die inside a critical would come out maximum too.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    me = c.me
    hold = c.effect(f"{c.ref} marked", until=When.EONT, on=victim)
    if hold is None:
        return

    def confirm(ev: Hit) -> None:
        if hold.ended or ev.attacker != me or ev.target != victim:
            return
        if _reach_kind(ev) != "melee":
            return
        result = getattr(ev, "result", None)
        if result is None:
            return
        result.critical = True
        c.flat(c.roll("1d12"), on=victim)
        c.world.effects.end(hold, "the marked blow landed")

    hold.subs.append(c.world.bus.on(Hit, confirm, window=Window.BEFORE, owner=me))


@power(
    "m3804a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3804a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m3804a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3804a3(c: Cast) -> None:
    """Two turns a round, one set of actions to each head.

    "Makes two initiative checks" is a second slot in the order, which is all
    `c.extra_turn` says, and ten counts under its own is where the levels
    below put one.

    The last sentence is `Budget.immediate_round`: `Encounter.can_spend`
    refuses an immediate action while that stamp equals the round, so stamping
    it out of date at the top of each of its turns is exactly the printed
    refresh -- and it has to be done on `TurnStart`, which `_begin` emits
    after the budget is refreshed rather than before.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def refresh(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.immediate_round = -1

    c.watch(TurnStart, refresh, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3804a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3804a4(c: Cast) -> None:
    """An automatic save is a success, and there is no auto-success to roll.

    `c.save` rolls a real one and `c.unsave` fails it; neither says "it
    succeeds". So the hold is ended, which is the same outcome with nothing
    faked. Only save-ends holds: the printed line says it saves, and a daze on
    a turn clock is not something a save can end. Which holds are charms is
    read off the keywords of the row named in the effect's own label.
    """
    me = c.me
    shaken = {Condition.DAZED, Condition.STUNNED}

    def shrug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if effect.when is not When.SAVE_ENDS:
                continue
            if set(effect.conditions) & shaken or _is_charm(effect.label):
                c.world.effects.end(effect, c.ref)

    c.watch(TurnEnd, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3922
# ==========================================================================


@power(
    "m3922a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m3922a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m3922a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m3922a1(c: Cast) -> None:
    """The card prints no exemption for the creature that made the zone, so
    `c.burns` -- which bites on entering and on starting a turn inside, the
    two printed moments -- is exactly right and nothing is hand-rolled."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=True)
    c.burns(zone, 5, DamageType.FIRE)


# ==========================================================================
# m4153
# ==========================================================================


@power(
    "m4153a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6, dtype=DamageType.COLD),
)
def m4153a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4153a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m4153a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4153a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m4153a2(c: Cast) -> None:
    """Bite, step, and two claws at somebody else.

    "A different target" is enforced here rather than left to the chooser:
    with a single target the claws have nobody else to reach and simply do not
    land, which is what the printed sentence says. The shift goes between the
    two, which is the order the card prints and the reason it is written out
    rather than folded into one volley.
    """
    if not c.first:
        return
    bitten = c.target
    if bitten is None:
        return
    use(c.world, c.me, "m4153a0", targets=[bitten], spend=False)
    c.shift(2)
    others = [
        f for f in c.enemies() if f != bitten and c.distance(f) <= 2 and alive(c.world, f)
    ]
    if not others:
        return
    for _ in range(2):
        use(c.world, c.me, "m4153a1", targets=[others[0]], spend=False)


_M4153_MISSED = "an enemy misses the m4153 with a melee or close attack"


def _missed_me_up_close(world: World, me: int, ev: Any) -> bool:
    """`Miss` names its subject `target` and carries no `actor`, so `about_me`
    is false here forever; the reach comes off the row named in the event, and
    a close burst or blast counts as one of the printed kinds."""
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None or team(world, attacker) is team(world, me):
        return False
    return _reach_kind(ev) in ("melee", "close_burst", "close_blast")


@power(
    "m4153a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 6),
    trigger=_M4153_MISSED,
    on=Trigger(Miss, when=_missed_me_up_close, text=_M4153_MISSED),
)
def m4153a3(c: Cast) -> None:
    """A burst, so it catches everybody near rather than only the creature
    that missed -- the printed target line is the burst's and not the
    trigger's."""
    if c.strike():
        c.hit()
        c.push(2)


_M4153_HELD = (Condition.SLOWED, Condition.RESTRAINED)


@power(
    "m4153a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4153a4(c: Cast) -> None:
    """"Targets slowed or restrained creatures" is a restriction `Target`
    cannot express, so whoever does not qualify is passed over -- a burst
    already names everybody in it, so there is nothing to redirect to.

    The last printed sentence costs nothing: forced movement against a
    creature restrained by this creature's own m4153a5 is exactly what
    `c.push` already does, since nothing in the engine exempts a restrained
    creature from being shoved.
    """
    if c.first:
        _rearms_when_bloodied(c)
    victim = c.target
    if victim is None or not any(c.is_(cond, on=victim) for cond in _M4153_HELD):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(3, on=victim)
        c.prone(on=victim)


@power(
    "m4153a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 6, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m4153a5(c: Cast) -> None:
    """`half_on_miss` is declared data nothing reads, so the Miss branch is
    written out. The Aftereffect hangs on the restraint's own ending, which
    follows it going whichever way it went."""
    victim = c.target
    if c.strike():
        c.hit()
        hold = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
        if hold is not None and victim is not None:
            hold.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))
    else:
        c.hit(half=True)


_M4153_BLOODIED = "it is first bloodied"


@power(
    "m4153a6",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4153_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M4153_BLOODIED),
)
def m4153a6(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and only then."""
    _uses_again(c, "m4153a5")


@power(
    "m4153a7",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=14),
)
def m4153a7(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit, and the Aftereffect
    follows it ending whichever way it ended."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m4365
# ==========================================================================


def _saves_against_prone(c: Cast) -> None:
    """"He can make a saving throw to avoid being knocked prone."

    `ConditionApplied` is the moment the prone lands and names its subject
    `target`. There is no interrupt window on a condition, so the throw is
    rolled as the hold arrives and a success takes it straight back off --
    which is the same outcome with a real die behind it. `bare=True` is a
    saving throw against nothing in particular, which is what this is.
    """
    me = c.me

    def catch(ev: Any) -> None:
        if getattr(ev, "target", None) != me:
            return
        if getattr(ev, "condition", None) is not Condition.PRONE:
            return
        if c.save(on=me, bare=True, against=c.ref):
            c.cure(Condition.PRONE, on=me)

    c.watch(ConditionApplied, catch, until=When.ENCOUNTER, on=me, label=f"{c.ref} footing")


@power(
    "m4365a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 4),
)
def m4365a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.push(2)
        c.dazed(until=When.EONT)


@power(
    "m4365a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m4365a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4365a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=UpTo(2),
)
def m4365a2(c: Cast) -> None:
    """Two basic attacks, melee or ranged -- `c.basic` swings whichever row
    this creature's basic attack actually is, so the choice is the board's.
    One target is swung at twice, which is the only reading that loses
    nothing."""
    if not c.first:
        return
    picks = list(c.targets[:2]) if len(c.targets) > 1 else [c.target, c.target]
    for victim in picks:
        if victim is not None:
            c.basic(on=victim)


@power(
    "m4365a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m4365a3(c: Cast) -> None:
    """One at a time: the standing domination is let go as the new one is
    taken, which is what `_only_one` does from the caster's side."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    _only_one(c, c.ref)
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


_M4365_STRUCK = "m4365 is hit by an attack"


@power(
    "m4365a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m4365a4(c: Cast) -> None:
    """The wound is passed on, type and conditions together.

    `Hit` carries no damage type and a reaction runs after the blow has
    landed, so the type comes off the most recent `DamageApplied` on him --
    which is the log, and the only place it exists.

    The conditions shared are the ones he is carrying on a saving throw when
    this fires, which is what the triggering attack imposed. Linking the two
    endings is the last printed sentence: the shared hold's `on_end` ends his.
    """
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    me = c.me
    blow = _last_blow_on(c.world, me)
    kinds = blow.types() if blow is not None else (DamageType.UNTYPED,)
    c.damage("1d8", 5, dtypes=tuple(kinds), on=victim, detail=c.ref)
    for mine in list(c.world.effects.of(me)):
        if mine.when is not When.SAVE_ENDS or not mine.conditions:
            continue
        shared = c.world.effects.apply(
            victim, me, When.SAVE_ENDS, label=c.ref, conditions=mine.conditions
        )
        shared.on_end.append(
            lambda hold=mine: c.world.effects.end(hold, "the shared condition ended")
        )


def _hit_me(world: World, me: int, ev: Any) -> bool:
    """`Hit` names its subject `target` and carries no `actor`."""
    return getattr(ev, "target", None) == me


_M4365_WOUNDED = "an attack hits m4365"


@power(
    "m4365a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M4365_WOUNDED,
    on=Trigger(Hit, when=_hit_me, text=_M4365_WOUNDED),
)
def m4365a5(c: Cast) -> None:
    """"The triggering attack grants combat advantage to m4365" is read as the
    creature that swung granting it, which is the only thing on the board an
    advantage can hang on. The card prints a recharge die *and* a bloodied
    recharge, and both are honoured."""
    _rearms_when_bloodied(c)
    c.teleport(8)
    ev = c.trigger
    attacker = getattr(ev, "attacker", None) if ev is not None else None
    if attacker is not None:
        c.grants_advantage(on=attacker, to=c.me, until=When.EONT)


@power(
    "m4365a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4365a6(c: Cast) -> None:
    """The bonus is what combat advantage *is* on an attack roll, so refusing
    the bonus and refusing to grant it come to the same number -- and
    `c.no_advantage` is the one verb that says it."""
    c.no_advantage(on=c.me, until=When.ENCOUNTER)


@power(
    "m4365a7",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4365a7(c: Cast) -> None:
    """Two sentences, two instruments: `c.resist_forced` shortens every shove
    by a square, and the footing is a saving throw rolled as the prone
    arrives."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)
    _saves_against_prone(c)


# ==========================================================================
# m4374
# ==========================================================================


@power(
    "m4374a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m4374a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4374a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m4374a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4374a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 6),
)
def m4374a2(c: Cast) -> None:
    """A printed band of "3/6" takes the normal range, which is the reading
    every level below has used."""
    if c.strike():
        c.hit()


@power(
    "m4374a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 3),
    target=UpTo(2),
)
def m4374a3(c: Cast) -> None:
    """Two basic attacks, melee or ranged. One target is swung at twice, which
    is the only reading that loses nothing."""
    if not c.first:
        return
    picks = list(c.targets[:2]) if len(c.targets) > 1 else [c.target, c.target]
    for victim in picks:
        if victim is not None:
            c.basic(on=victim)


@power(
    "m4374a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m4374a4(c: Cast) -> None:
    """"Already slowed or immobilized" is asked before the slow this row lays,
    or the row would always find its own condition true and restrain
    everybody. A restraint supersedes the slow rather than standing beside
    it, which is what "is restrained" instead of "and is restrained" means."""
    victim = c.target
    if victim is None:
        return
    stuck = c.is_(Condition.SLOWED, on=victim) or c.is_(Condition.IMMOBILIZED, on=victim)
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    if stuck:
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    else:
        c.slowed(until=When.SAVE_ENDS, on=victim)
    c.push(3, on=victim)


@power(
    "m4374a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC),
)
def m4374a5(c: Cast) -> None:
    """"Save ends both" is one effect carrying the daze and the burn, so the
    printed sentence gets the one saving throw it prints."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )


@power(
    "m4374a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4374a6(c: Cast) -> None:
    """Two numbers in two sentences and neither prints a type word, so both
    are untyped. The gate reads `target`, which both the attack context and
    the damage context carry -- a gate on a key either one lacks is silently
    false."""
    world = c.world

    def softened(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        health = world.get(who, Health)
        if health is not None and health.bloodied:
            return True
        return any(
            eff.ongoing is not None
            and (tuple(eff.ongoing_types) or (eff.ongoing[1],)) == (DamageType.UNTYPED,)
            for eff in world.effects.of(who)
        )

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=softened)
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=softened)


_M4374_BLOODIED = "he is first bloodied"


@power(
    "m4374a7",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4374_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M4374_BLOODIED),
)
def m4374a7(c: Cast) -> None:
    """Three sentences: the mark goes, the concealment arrives, and the
    immunity holds the mark off for a turn. `c.cure` returns what actually
    went, and `c.immune` is the verb for "cannot be marked"."""
    c.cure(Condition.MARKED, on=c.me)
    c.conceal(on=c.me, until=When.ENCOUNTER)
    c.immune(Condition.MARKED, until=When.EONT, on=c.me)


# ==========================================================================
# m4641
# ==========================================================================


@power(
    "m4641a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 5),
)
def m4641a0(c: Cast) -> None:
    """"1d10+5 damage plus 1d6 cold damage" is two packets, and resistance
    reads them separately -- so the untyped one is the declared line and the
    cold one is rolled beside it."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)
        c.slowed(until=When.EONT)


@power(
    "m4641a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4),
)
def m4641a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m4641a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m4641a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.EONT)
    _ends_its_turn_in(c, zone, lambda who: c.flat(10, dtype=DamageType.FIRE, on=who))


@power(
    "m4641a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID, Keyword.THUNDER],
    attack=Attack(vs=REF, printed=16),
    dropped=("Damage(dtypes=)",),
)
def m4641a3(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two types,
    which is what resistance reads as a unit. The Miss line is the same blow
    halved, which is what `c.half_damage` is for."""
    kinds = (DamageType.ACID, DamageType.THUNDER)
    if c.strike():
        c.damage("2d8", 8, dtypes=kinds, detail=c.ref)
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", 8, dtypes=kinds)


@power(
    "m4641a4",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=16),
)
def m4641a4(c: Cast) -> None:
    """A shift that swings at whoever it passes.

    `AdjacencyGained` is emitted mirrored for both creatures and carries
    `mover`, which is how "each creature he moves adjacent to" is told from a
    creature that walked up to him. The watch is armed for the length of the
    shift and torn down afterwards, and each creature is attacked once --
    stepping away and back would otherwise pay twice.

    Declared with no target and `c.strike(on=)` aimed by hand, because the
    creatures attacked are not known until the movement has happened.
    """
    me, ref = c.me, c.ref
    struck: set[int] = set()

    def beside(ev: Any) -> None:
        if getattr(ev, "actor", None) != me or getattr(ev, "mover", 0) != me:
            return
        other = getattr(ev, "other", None)
        if other is None or other in struck or other not in c.enemies():
            return
        struck.add(other)
        if c.strike(on=other):
            c.prone(on=other)

    watcher = c.watch(
        AdjacencyGained, beside, until=When.EOT, on=me, label=f"{ref} passing"
    )
    try:
        c.shift(4)
    finally:
        c.world.effects.end(watcher, "the shift is over")


_M4641_SET = "m4641a5 braced"


@power(
    "m4641a5",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4641a5(c: Cast) -> None:
    """"Until he moves" is a watch rather than a duration, and `MoveEnd` is
    where it is answered: the row is not trying to stop the move, only to
    notice it. Three defences, not four, so three modifiers on one effect --
    and the card prints no type word, so they are untyped."""
    me = c.me
    guard = c.world.effects.apply(
        me,
        me,
        When.ENCOUNTER,
        label=_M4641_SET,
        mods=[
            (me, Mod(what=defended.value, value=2, kind="untyped", label=c.ref))
            for defended in (AC, FORT, REF)
        ],
    )

    def moved(ev: Any) -> None:
        if getattr(ev, "actor", None) == me and not guard.ended:
            c.world.effects.end(guard, "he moved")

    guard.subs.append(c.world.bus.on(MoveEnd, moved, owner=me))


@power(
    "m4641a6",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=lambda world, eid: _is_bloodied(world, eid),
    requires_text="usable only while bloodied",
)
def m4641a6(c: Cast) -> None:
    c.temp_hp(14, on=c.me)


# ==========================================================================
# m5189
# ==========================================================================


@power(
    "m5189a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5189a0(c: Cast) -> None:
    """An aura that bites whoever begins a turn inside it. `_ends_its_turn_in`
    is the other half of this shape and is the wrong one here -- the printed
    moment is the start of the turn."""
    me = c.me
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)

    def bite(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            c.flat(10, on=ev.actor)

    c.watch(TurnStart, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5189a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5189a1(c: Cast) -> None:
    """Narrative only. The board has no small openings to go through, and
    `Condition.SQUEEZING` is the opposite of what this line grants: it is the
    penalty for being somewhere too tight, not permission to be there."""
    c.note(f"{c.ref}: she fits through small openings as though she were Tiny")


@power(
    "m5189a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 4),
)
def m5189a2(c: Cast) -> None:
    """The ten points are flat and are hers whether or not the blow dealt its
    full damage, which is what a printed number rather than "equal to the
    damage dealt" means."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
        c.heal(10, on=c.me)


@power(
    "m5189a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=UpTo(3),
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 4),
)
def m5189a3(c: Cast) -> None:
    """The penalty to the saving throw is live, not fixed.

    "While within 5 squares of her" is a distance asked each time the throw is
    rolled, so it cannot be the effect's `save_mod` -- that is a number set
    once. It is a `Mod` on the same effect instead, with a gate reading the
    hold's own label, so there is still one effect and one saving throw per
    printed sentence.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, ref, world = c.me, c.ref, c.world
    near = Mod(
        what="save",
        value=-5,
        label=ref,
        when=lambda ctx: ctx.get("label") == ref
        and distance_between(world, me, victim) <= 5,
    )
    world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=ref,
        ongoing=(10, DamageType.UNTYPED),
        mods=[(victim, near)],
    )


@power(
    "m5189a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 4),
)
def m5189a4(c: Cast) -> None:
    """The Effect counts hits across the whole use, so it is paid on the last
    target rather than the first -- `c.first` would run before the rest had
    been rolled. The count comes off the bus rather than a local, because the
    body is called once per target and a local cannot outlive one call."""
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    if not c.last:
        return
    hits = _hits_this_use(c)
    if hits >= 1:
        c.heal(10, on=c.me)
    if hits >= 2:
        c.save(on=c.me)


@power(
    "m5189a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=15),
)
def m5189a5(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


_M5189_SHAPE = "m5189a6 shape"


@power(
    "m5189a6",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:insight",),
)
def m5189a6(c: Cast) -> None:
    """A shape with no mechanics inside it -- "she retains her statistics" is
    the card saying so. The Insight check is the narrative clause: discerning
    a disguise is a circumstance nothing on a board ever rolls for, so there
    is no symbol to wait on."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M5189_SHAPE:
            c.world.effects.end(eff, "she changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M5189_SHAPE)
    c.note(f"{c.ref}: she takes the shape of a Medium humanoid of any race or gender")


# ==========================================================================
# m5557
# ==========================================================================


@power(
    "m5557a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5557a0(c: Cast) -> None:
    """Slowed for attacking it from inside the aura.

    `AttackDeclared` names its subject `target` and carries no `actor`, so the
    gate is written out rather than handed `about_me`. The clock is the
    *enemy's* next turn, which is `When.EOTNT` and not `EONT`.
    """
    me = c.me
    ring = c.aura(5, label=c.ref, until=When.ENCOUNTER)

    def stiffen(ev: AttackDeclared) -> None:
        if ev.target != me:
            return
        if team(c.world, ev.attacker) is team(c.world, me):
            return
        if ev.attacker in c.world.zones.occupants(ring):
            c.slowed(until=When.EOTNT, on=ev.attacker)

    c.watch(AttackDeclared, stiffen, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5557a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 7),
)
def m5557a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5557a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=15),
)
def m5557a2(c: Cast) -> None:
    """No damage line at all: the hold is the whole of the hit, and each
    failed save trades up. The last step is petrification with no save, which
    is where the chain stops, so it carries no escalation of its own. The Miss
    line is a slow on a turn clock."""
    if not c.strike():
        c.slowed(until=When.EONT)
        return
    victim = c.target
    if victim is None:
        return

    def stone(eff: Effect) -> None:
        c.world.effects.end(eff, "the saving throw failed")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def bind(eff: Effect) -> None:
        c.world.effects.end(eff, "the saving throw failed")
        c.condition(
            Condition.RESTRAINED, until=When.SAVE_ENDS, on=eff.owner, escalate=stone
        )

    c.condition(
        Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=bind
    )


# ==========================================================================
# m5641
# ==========================================================================

#: The two printed Effect lines every attack row on this block carries, named
#: by the order they are printed in rather than by what the card calls them.
_M5641_FIRST = "m5641a0 first"
_M5641_SECOND = "m5641a0 second"

#: The rows that print a pair of Effect lines for m5641a0 to choose between.
_M5641_RUNED = ("m5641a5", "m5641a6", "m5641a7")


def _m5641_chose(c: Cast) -> str:
    """Which of the two printed Effect lines is live for this use."""
    for eff in c.world.effects.of(c.me):
        if eff.label in (_M5641_FIRST, _M5641_SECOND):
            return eff.label
    return ""


@power(
    "m5641a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5641a0(c: Cast) -> None:
    """The choice the other rows read, made before each of them runs.

    `PowerUsed` is announced *above* `p.body(cast)` in `dsl.use`, which is
    normally the trap -- a row watching it sees a world where the power has
    not happened. Here that is exactly what is wanted: the choice has to be
    recorded before the body that reads it runs. The previous choice is
    dropped first, so a use cannot inherit the last one.
    """
    me = c.me

    def pick(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power not in _M5641_RUNED:
            return
        for eff in list(c.world.effects.of(me)):
            if eff.label in (_M5641_FIRST, _M5641_SECOND):
                c.world.effects.end(eff, "another is chosen")
        which = c.choose(
            [_M5641_FIRST, _M5641_SECOND],
            f"{c.ref}: which of the two printed Effect lines",
        )
        if which:
            c.effect(which, until=When.EOT, on=me)

    c.watch(PowerUsed, pick, until=When.ENCOUNTER, on=me, label=c.ref)


_M5641_SEIZED = "m5641a1 seized"


@power(
    "m5641a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5641a1(c: Cast) -> None:
    """Something takes hold of him on a low roll, once m5641a7 has been spent.

    The card names the thing that does the taking; that word is not written
    anywhere here and is reported instead. What is left is structural and
    exact: after m5641a7, the **first** attack roll of each of his turns is
    watched, and a natural 5 or lower dominates him until the end of his next
    turn. "Commands him to attack" needs nothing of its own -- a dominated
    creature's actions are already somebody else's to spend.

    `AttackRolled` carries the live result, which is where the natural die
    is; the per-turn flag is a closure, because `Trigger` takes no `once=`
    and this is "the first roll during a turn" rather than once a fight.
    """
    me = c.me
    armed = {"on": False}
    rolled = {"round": -1}

    def spent(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m5641a7":
            armed["on"] = True

    def watch_roll(ev: Any) -> None:
        if not armed["on"] or getattr(ev, "attacker", None) != me:
            return
        if rolled["round"] == c.world.round:
            return
        rolled["round"] = c.world.round
        result = getattr(ev, "result", None)
        natural = getattr(result, "natural", 20) if result is not None else 20
        if natural <= 5:
            c.condition(Condition.DOMINATED, until=When.EONT, on=me)

    c.watch(PowerUsed, spent, until=When.ENCOUNTER, on=me, label=f"{c.ref} armed")
    c.watch(
        AttackRolled, watch_roll, until=When.ENCOUNTER, on=me, label=_M5641_SEIZED
    )


@power(
    "m5641a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.installed(ref)",),
)
def m5641a2(c: Cast) -> None:
    """Nothing here can be said, so the row is refused rather than granting
    its action point unconditionally.

    The printed Requirement is that a named installation somewhere off the
    board is running. Nothing on a board holds such a thing: `c.scenery` is
    map furniture inside the fight and `c.terrain` is what sort of place the
    fight is in, and neither answers "is that standing arrangement active".
    Granting the point without the gate would be strictly better than the
    card.

    The brief for this row also spells the installation as this row's own ref,
    which is reported.
    """


@power(
    "m5641a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5641a3(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m5641a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5641a4(c: Cast) -> None:
    _saves_against_prone(c)


@power(
    "m5641a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m5641a5(c: Cast) -> None:
    """Two printed Effect lines, one of them live -- m5641a0 records which
    before this body runs. The second line's bonus is a **power** bonus,
    which is the word the card prints, and it is four modifiers on one effect
    because there is one sentence to take off again."""
    landed = c.strike()
    if landed:
        c.hit()
    victim = c.target
    if victim is None:
        return
    chosen = _m5641_chose(c)
    if chosen == _M5641_FIRST:
        c.prone(on=victim)
    elif chosen == _M5641_SECOND:
        beside = [a for a in c.allies() if distance_between(c.world, a, victim) <= 1]
        who = beside[0] if beside else c.me
        c.world.effects.apply(
            who,
            c.me,
            When.EONT,
            label=c.ref,
            mods=[
                (who, Mod(what=d.value, value=2, kind="power", label=c.ref))
                for d in EVERY_DEFENCE
            ],
        )


@power(
    "m5641a6",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 11, dtype=DamageType.RADIANT),
)
def m5641a6(c: Cast) -> None:
    """The eight radiant points are flat, not rolled, and they land on the
    target's neighbours rather than on the target."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    victim = c.target
    if victim is None:
        return
    chosen = _m5641_chose(c)
    if chosen == _M5641_FIRST:
        for foe in c.enemies():
            if foe != victim and distance_between(c.world, foe, victim) <= 1:
                c.flat(8, dtype=DamageType.RADIANT, on=foe)
    elif chosen == _M5641_SECOND:
        beside = [a for a in c.allies() if distance_between(c.world, a, victim) <= 1]
        if beside:
            c.temp_hp(10, on=beside[0])


@power(
    "m5641a7",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    requires=lambda world, eid: _is_bloodied(world, eid),
    requires_text="he must be bloodied",
)
def m5641a7(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit. The first
    printed Effect line is paid once for the whole use, which is what
    `c.first` guards; the second is per target and only for the ones the
    attack missed."""
    landed = c.strike()
    if landed:
        c.condition(Condition.DOMINATED, until=When.EONT)
    chosen = _m5641_chose(c)
    if chosen == _M5641_FIRST and c.first:
        c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")
    elif chosen == _M5641_SECOND and not landed:
        c.weakened(until=When.EONT)


@power(
    "m5641a8",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.extra_action(must_attack=)",),
)
def m5641a8(c: Cast) -> None:
    """The extra standard action plays. What is dropped is the restriction on
    what it may be spent on: `c.extra_action` hands over an action of a named
    cost and has no way to say "an attack power only", so the policy may spend
    it on anything a standard action buys."""
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m5744
# ==========================================================================


@power(
    "m5744a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5744a0(c: Cast) -> None:
    """Only while it is carrying somebody, which is `c.mount()` asked inside
    the gate rather than once at arming -- a rider that climbs on later would
    otherwise never switch it on."""
    c.resist_forced(
        1, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.mount() is not None
    )


@power(
    "m5744a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 7),
)
def m5744a1(c: Cast) -> None:
    """The bloodied bonus rides on `c.strike(plus=)` rather than on a standing
    modifier: there is no trait row on this block that lays it, so the two
    rows that print it each carry their own, and two bonuses of one kind would
    not have added anyway."""
    plus = 2 if _is_bloodied(c.world, c.me) else 0
    if c.strike(plus=plus):
        c.hit()
        if c.mount() is not None:
            c.prone()


@power(
    "m5744a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
)
def m5744a2(c: Cast) -> None:
    """"Each target *can* shift" is permission, which is `c.grant_action` and
    not `c.shift` -- the shift is the ally's to take or leave. `shift` is one
    of the five words `actions.legal` actually reads."""
    who = c.target
    if who is None or who == c.me:
        return
    c.grant_action("shift", FREE, squares_=1, on=who, until=When.EOT)


@power(
    "m5744a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d6", 6, dtype=DamageType.ACID, kind=LIMITED),
)
def m5744a3(c: Cast) -> None:
    plus = 2 if _is_bloodied(c.world, c.me) else 0
    if c.strike(plus=plus):
        c.hit()


_M5744_HURT = "an enemy's attack damages the m5744 while it is mounted"


def _hurt_while_mounted(world: World, me: int, ev: Any) -> bool:
    """`DamageApplied` names its subject `target`. The mount is a relation and
    is asked here, because a trait gated in its header would be refused once
    and never armed again if nobody were riding at the start."""
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    source = getattr(ev, "source", None)
    if source is None or team(world, source) is team(world, me):
        return False
    return bool(world.relations.sources(Relation.RIDDEN_BY, me))


@power(
    "m5744a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5744_HURT,
    on=Trigger(DamageApplied, when=_hurt_while_mounted, text=_M5744_HURT),
)
def m5744a4(c: Cast) -> None:
    """The mount swings, not the rider: `c.grant_attack(who=)` names who
    attacks and `on=` names who is hit, and the triggering enemy comes off the
    event rather than off `c.target`, which is None on a row with no target
    line."""
    mount = c.mount()
    ev = c.trigger
    culprit = getattr(ev, "source", None) if ev is not None else None
    if mount is None or culprit is None:
        return
    c.grant_attack(mount, on=culprit)


# ==========================================================================
# m5758
# ==========================================================================


@power(
    "m5758a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5758a0(c: Cast) -> None:
    """Vulnerability held for as long as the enemy is inside, which is what
    `_aura` diffs -- a duration would outlast walking out of it."""
    _aura(
        c,
        2,
        lambda who: who in c.enemies(),
        lambda who: c.vulnerable(
            5, DamageType.COLD, on=who, until=When.ENCOUNTER
        ),
    )


@power(
    "m5758a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 4, dtype=DamageType.COLD),
)
def m5758a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5758a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.COLD],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 2, dtype=DamageType.COLD),
)
def m5758a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5758a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=15),
    dropped=("Damage(dtypes=)",),
)
def m5758a3(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two types,
    which is what resistance reads as a unit. The burn is only for a target
    already held, asked before this row lays nothing of the sort."""
    victim = c.target
    if victim is None:
        return
    stuck = c.is_(Condition.SLOWED, on=victim) or c.is_(
        Condition.IMMOBILIZED, on=victim
    )
    if not c.strike(on=victim):
        return
    c.damage(
        "4d8", 2,
        dtypes=(DamageType.COLD, DamageType.THUNDER),
        on=victim,
        detail=c.ref,
    )
    if stuck:
        c.ongoing(10, DamageType.COLD, on=victim)


# ==========================================================================
# m5807
# ==========================================================================


@power(
    "m5807a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 3),
)
def m5807a0(c: Cast) -> None:
    """The slide is an Effect and lands whether or not the blow did."""
    if c.strike():
        c.hit()
    if c.target is not None:
        c.slide(1)


@power(
    "m5807a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
)
def m5807a1(c: Cast) -> None:
    """All Effect and no attack roll, so there is no `attack=` in the header
    and the ten points are flat rather than rolled."""
    victim = c.target
    if victim is None:
        return
    c.flat(10, dtype=DamageType.FORCE, on=victim)
    c.push(2, on=victim)


@power(
    "m5807a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 6, dtype=DamageType.POISON),
)
def m5807a2(c: Cast) -> None:
    """"Save ends both" inside a zone clause is still one effect with one
    saving throw, laid on whoever ends a turn in it."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.EONT)
    _ends_its_turn_in(
        c,
        zone,
        lambda who: c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            on=who,
            ongoing=(5, DamageType.POISON),
        ),
    )


@power(
    "m5807a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d10", 9, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m5807a3(c: Cast) -> None:
    """The card prints the recharge as a bloodied one and the database files a
    6+; both are honoured, and they only ever make the row available sooner.
    `half_on_miss` is declared data nothing reads, so the branch is written."""
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.FIRE),
        )
    else:
        c.hit(half=True)


# ==========================================================================
# m5815
# ==========================================================================


@power(
    "m5815a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5815a0(c: Cast) -> None:
    """Whatever it holds comes along. Answered on `MoveEnd`, which is after the
    move: the row is not trying to change where it went, only to drag the
    captives after it. `c.pull` anchors on the caster by default, so the
    distance asked for is the gap and the pull stops when it closes."""
    me = c.me

    def drag(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        for caught in _holding(c.world, me):
            gap = distance_between(c.world, me, caught)
            if gap > 1:
                c.pull(gap, on=caught)

    c.watch(MoveEnd, drag, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5815a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(6),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 7),
)
def m5815a1(c: Cast) -> None:
    """"One creature not grabbed by it" is a restriction `Target` cannot
    express, so the aim is moved to one that qualifies rather than thrown
    away."""
    held = set(_holding(c.world, c.me))
    victim = _restricted_to(c, 6, lambda who: who not in held)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m5815a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(6),
    target=Target(side="enemy", count=1, max_size=Size.HUGE),
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d12", 4),
)
def m5815a2(c: Cast) -> None:
    """The size limit is a thing `Target` *can* say, so it is said in the
    header; "not grabbed by it" is not, so that half is enforced here.

    The burn runs on the grab's clock rather than on a saving throw, which is
    what `_until_the_grab_ends` hangs it on. Releasing as a free action and
    the escape DC are both outside what the engine holds: a grab is escaped
    with a check it sets itself, and letting go is not an action anybody
    spends.
    """
    held = set(_holding(c.world, c.me))
    victim = _restricted_to(c, 6, lambda who: who not in held)
    if victim is None or len(held) >= 2:
        return
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.pull(5, on=victim)
    c.grab(on=victim)
    _until_the_grab_ends(c, victim, c.ongoing(10, on=victim, until=When.ENCOUNTER))


@power(
    "m5815a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
    dropped=("c.no_surges()",),
)
def m5815a3(c: Cast) -> None:
    """Only something it already holds. Barring healing surges is the dropped
    clause -- `c.no_healing` stops healing outright, which is wider than the
    card."""
    held = set(_holding(c.world, c.me))
    victim = _restricted_to(c, 1, lambda who: who in held)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m5815a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(6),
    target=UpTo(2),
)
def m5815a4(c: Cast) -> None:
    """"Each against a different target" is enforced here: with only one
    creature in reach the second swing has nobody to land on, which is what
    the printed sentence says."""
    if not c.first:
        return
    for victim in list(c.targets[:2]):
        if alive(c.world, victim):
            use(c.world, c.me, "m5815a1", targets=[victim], spend=False)


@power(
    "m5815a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d8", 9, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5815a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5815a6",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
)
def m5815a6(c: Cast) -> None:
    """A burst that picks one creature out of it, which is the printed target
    line and not the shape of the area. No damage line: the pull is the whole
    of the hit."""
    if c.strike():
        c.pull(5)


_M5815_BLOODIED = "it is bloodied"


@power(
    "m5815a7",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    trigger=_M5815_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M5815_BLOODIED),
)
def m5815a7(c: Cast) -> None:
    """A blow of two types, which `c.flat(dtypes=)` takes where the header
    cannot -- and there is no header damage line here at all, because the aura
    rather than this row is what deals it."""
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    _ends_its_turn_in(
        c,
        ring,
        lambda who: c.flat(
            10, dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=who
        ),
    )


# ==========================================================================
# m5831
# ==========================================================================


@power(
    "m5831a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5831a0(c: Cast) -> None:
    """Half of everything but force.

    Not `c.insubstantial`: that condition halves force too, and the printed
    line excepts it. The halving comes off the damage in the interrupt window,
    which is the one moment the number exists and has not yet reached hit
    points.
    """
    me = c.me

    def half(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if DamageType.FORCE in ev.types():
            return
        ev.amount //= 2

    c.watch(
        DamageRolled,
        half,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


@power(
    "m5831a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5831a1(c: Cast) -> None:
    """"An ally who also has this trait" is an ally carrying this row, which
    is `Powers.known` and nothing else -- `Ident.ref` would be wrong here,
    since the printed line is about the trait rather than the stat block.

    The card prints the word "power" in front of the bonus, so it is a power
    bonus.
    """
    me, ref = c.me, c.ref

    def kin_fell(ev: Dropped) -> None:
        who = getattr(ev, "actor", None)
        if who is None or who == me:
            return
        if team(c.world, who) is not team(c.world, me):
            return
        if distance_between(c.world, me, who) > 5:
            return
        known = c.world.get(who, Powers)
        if known is None or ref not in known.all:
            return
        c.bonus("attack", 2, on=me, until=When.EONT, kind="power")

    c.watch(Dropped, kin_fell, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5831a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11, dtype=DamageType.PSYCHIC),
)
def m5831a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5831a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.COLD, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=15),
    dropped=("Damage(dtypes=)",),
)
def m5831a3(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two types,
    which is what resistance reads as a unit."""
    if not c.strike():
        return
    c.damage(
        "3d6", 5,
        dtypes=(DamageType.COLD, DamageType.RADIANT),
        detail=c.ref,
    )
    c.slowed(until=When.SAVE_ENDS)


@power(
    "m5831a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m5831a4(c: Cast) -> None:
    """No damage line: the daze is the whole of the hit. The push is an Effect
    and lands on every target whether or not the attack did -- which is what
    "Effect: it can push each target" says and why it is outside the branch.
    The database files a 6+ where the card prints a bloodied recharge; both
    are honoured."""
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.dazed(until=When.EONT)
    if c.target is not None:
        c.push(1)


# ==========================================================================
# m5933
# ==========================================================================


@power(
    "m5933a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5933a0(c: Cast) -> None:
    """A type word handed to whoever is riding it.

    `c.set_origin` is the verb for "is considered a <word> creature", which is
    exactly the printed sentence. The rider is looked up at the top of each
    turn rather than once at arming: a trait is armed before anybody has
    mounted, and `requires=` on a trait would have refused it once and never
    armed it again.
    """
    me, ref = c.me, c.ref
    tagged: set[int] = set()

    def carry(ev: TurnStart) -> None:
        if ev.ghost:
            return
        who = c.rider()
        if who is None or who in tagged:
            return
        if team(c.world, who) is not team(c.world, me):
            return
        stats = c.world.get(who, Stats)
        if stats is None or stats.level < 12:
            return
        tagged.add(who)
        c.set_origin("aquatic", on=who, until=When.ENCOUNTER)

    c.watch(TurnStart, carry, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5933a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5933a1(c: Cast) -> None:
    """Breathing underwater is already true of a board with no drowning
    mechanic to exempt it from; the attack bonus is the real half, and the
    card prints no type word in front of it."""
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("aquatic")
        and not c.is_kind("aquatic", on=ctx.get("target")),
    )


@power(
    "m5933a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5933a2(c: Cast) -> None:
    """The slide is an Effect and lands whether or not the blow did."""
    if c.strike():
        c.hit()
    if c.target is not None:
        c.slide(2)


@power(
    "m5933a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 4),
)
def m5933a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


# ==========================================================================
# m6537
# ==========================================================================


@power(
    "m6537a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6537a0(c: Cast) -> None:
    """Three extra points on an ally's blow, measured by where the ally is
    standing rather than by where the target is.

    The reach comes off the row named in the `Hit`, which is where a melee or
    ranged line is told from a close or area one. The three points are flat
    and are fire, so they meet the target's fire resistance on their own
    rather than joining the ally's blow.
    """
    me = c.me
    ring = c.aura(2, label=c.ref, until=When.ENCOUNTER)

    def flare(ev: Hit) -> None:
        if ev.attacker == me or ev.attacker not in c.world.zones.occupants(ring):
            return
        if team(c.world, ev.attacker) is not team(c.world, me):
            return
        if _reach_kind(ev) not in ("melee", "ranged"):
            return
        c.flat(3, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, flare, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6537a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6537a1(c: Cast) -> None:
    """"Scores a critical hit" is read off the live `AttackResult` riding on
    the `Hit`, not asked again afterwards. Which rows are implement powers is
    a keyword on the row behind the event."""
    me = c.me

    def burst(ev: Hit) -> None:
        if ev.attacker != me:
            return
        result = getattr(ev, "result", None)
        if result is None or not getattr(result, "critical", False):
            return
        p = get(getattr(ev, "power", "") or "")
        if p is None or Keyword.IMPLEMENT not in p.keywords:
            return
        c.flat(10, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, burst, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6537a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=AC, printed=17),
    dropped=("Damage(dtypes=)",),
)
def m6537a2(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two
    types."""
    if c.strike():
        c.damage(
            "2d8", 11,
            dtypes=(DamageType.COLD, DamageType.FIRE),
            detail=c.ref,
        )


@power(
    "m6537a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=15),
    dropped=("Damage(dtypes=)",),
)
def m6537a3(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header, so it is
    rolled in the body as one blow of two types."""
    if c.strike():
        c.damage(
            "2d8", 11,
            dtypes=(DamageType.COLD, DamageType.FIRE),
            detail=c.ref,
        )
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6537a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 8, kind=LIMITED),
)
def m6537a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m6537a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    dropped=("Damage(dtypes=)",),
)
def m6537a5(c: Cast) -> None:
    """Two numbers for one blow and both of them two types, so the whole line
    is rolled in the body: the header has one `dtype` to give and this needs
    two. The Miss line is the same blow halved, which is `c.half_damage`.

    The flight is an Effect and happens whatever the attack did, once for the
    whole use -- `c.first` is where a once-per-power line goes.
    """
    victim = c.target
    if victim is None:
        return
    kinds = (DamageType.COLD, DamageType.FIRE)
    stuck = c.is_(Condition.SLOWED, on=victim) or c.is_(
        Condition.IMMOBILIZED, on=victim
    )
    bonus = 15 if stuck else 8
    if c.strike(on=victim):
        c.damage("2d6", bonus, dtypes=kinds, on=victim, detail=c.ref)
    else:
        c.half_damage("2d6", bonus, dtypes=kinds, on=victim)
    if c.first:
        c.no_provoke(until=When.EOT, on=c.me)
        c.move(10, at="fly")


_M6537_BURNED = "it hits with a fire implement power"


def _fire_implement_hit(world: World, me: int, ev: Any) -> bool:
    """`Hit` names the attacker in `attacker` and carries no `actor`, and the
    keywords come off the row named in the event."""
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    if p is None:
        return False
    return Keyword.FIRE in p.keywords and Keyword.IMPLEMENT in p.keywords


@power(
    "m6537a6",
    level=12,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6537_BURNED,
    on=Trigger(
        Hit, when=_fire_implement_hit, text=_M6537_BURNED, window=Window.BEFORE
    ),
    dropped=("c.using(ref)",),
)
def m6537a6(c: Cast) -> None:
    """Maximised damage, taken in the `Hit` window because that is before the
    blow is rolled -- `c.maximise` sets the *next* roll, and a reaction after
    the damage would set one for some later swing.

    The dropped clause is the printed Requirement, which is that it is in a
    named state at the time. The brief spells that state as a printed title
    and gives no ref for it, and nothing on a board answers "is that row's
    state standing": `c.stance` and `c.form` are things a row lays on itself
    and neither is a question another row can ask by ref.
    """
    c.maximise(on=c.me)


# ==========================================================================
# m877
# ==========================================================================


@power(
    "m877a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
)
def m877a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m877a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d4", 6, dtype=DamageType.FORCE),
)
def m877a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m877a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d8", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m877a2(c: Cast) -> None:
    """A burst with no "within" is measured from the caster, which is a close
    burst."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m877a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d6", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m877a3(c: Cast) -> None:
    """A burst printed "within 20 squares" is an area burst, and an area burst
    with no target line catches everybody in it."""
    if c.strike():
        c.hit()


@power(
    "m877a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d12", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m877a4(c: Cast) -> None:
    """The keyword line was lost in extraction and the damage line names cold,
    so cold is what goes in."""
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m940
# ==========================================================================


@power(
    "m940a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 4),
)
def m940a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m940a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 5),
)
def m940a1(c: Cast) -> None:
    """"The m940 **or** another undead within 2 squares" is a choice, and the
    type words come off the stat block, which is what `c.is_kind` reads. With
    nobody else of the sort nearby it keeps the five points itself."""
    if not c.strike():
        return
    c.hit()
    me = c.me
    takers = [me] + [
        a
        for a in c.allies()
        if a != me and c.distance(a) <= 2 and c.is_kind("undead", on=a)
    ]
    who = c.choose(takers, f"{c.ref}: who the life goes to") or me
    c.heal(5, on=who)


_M940_STIRRED = "an enemy within 10 squares of the m940 moves"


def _enemy_moves_near(world: World, me: int, ev: Any) -> bool:
    """`MoveStart` is the interrupt window and is before the creature has gone
    anywhere, which is what an immobilizing interrupt wants: by `MoveEnd` the
    enemy has already arrived and the hold would stop nothing."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "m940a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    trigger=_M940_STIRRED,
    on=Trigger(MoveStart, when=_enemy_moves_near, text=_M940_STIRRED),
)
def m940a2(c: Cast) -> None:
    """Filed as a move action and printed as an immediate interrupt. No damage
    line: the hold is the whole of the hit, and the creature struck at is the
    one the trigger names rather than whoever the chooser handed over."""
    ev = c.trigger
    victim = getattr(ev, "actor", None) if ev is not None else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m940a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(6),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m940a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)


# ==========================================================================
# m983
# ==========================================================================


@power(
    "m983a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m983a0(c: Cast) -> None:
    """The extra dice against a stunned target are a second packet and are
    necrotic, so they are rolled beside the declared line rather than folded
    into it -- and the question is asked before the swing, since nothing here
    stuns."""
    stunned = c.target is not None and c.is_(Condition.STUNNED, on=c.target)
    if c.strike():
        c.hit()
        if stunned:
            c.damage("2d8", dtype=DamageType.NECROTIC)


def _strips_resistance(c: Cast, victim: int, dtype: DamageType) -> None:
    """"The target loses any necrotic resistance it has (save ends)."

    Resistance lives on `Defences.resist`, which `resolve.deal_damage` reads
    and `Mods` never consults -- so there is nothing to lay a modifier on.
    The number is taken off and put back by the hold's own `on_end`, which is
    the shape `_resist` settled at level 7 for the opposite direction.
    """
    shell = c.world.get(victim, Defences)
    had = shell.resist.get(dtype, 0) if shell is not None else 0
    if shell is None or not had:
        return
    shell.resist.pop(dtype, None)

    def give_back() -> None:
        shell.resist[dtype] = had

    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, on_end=[give_back]
    )


@power(
    "m983a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m983a1(c: Cast) -> None:
    """Three printed branches, and the third belongs to both of the others:
    "Hit or Miss" is outside the if. `half_on_miss` is declared data nothing
    reads, so the Miss branch is written out, and the Miss line says plainly
    that the stun does not land."""
    victim = c.target
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)
    else:
        c.hit(half=True)
    if victim is not None:
        _strips_resistance(c, victim, DamageType.NECROTIC)


_M983_BLOODIED = "it is first bloodied"


@power(
    "m983a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M983_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M983_BLOODIED),
)
def m983a2(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and only then."""
    _uses_again(c, "m983a1")


_M983_FLANKED = "an enemy moves into a position that flanks the m983"


def _flanked_me(world: World, me: int, ev: Any) -> bool:
    """`MoveEnd` and not `MoveStart`: the printed trigger is about where the
    creature has arrived, and `flanked_by` cannot be true before the step.
    `query.flanked_by` is the one thing on the board that answers it."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    return flanked_by(world, me, who)


@power(
    "m983a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d4", 6),
    trigger=_M983_FLANKED,
    on=Trigger(MoveEnd, when=_flanked_me, text=_M983_FLANKED),
)
def m983a3(c: Cast) -> None:
    """The card spells the swing as another stat block's id; the row every
    sentence here plainly means is the attack line printed beside it, which is
    this row's own. The triggering enemy comes off the event."""
    ev = c.trigger
    victim = getattr(ev, "actor", None) if ev is not None else c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(1, on=victim)


@power(
    "m983a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m983a4(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit. The Aftereffect runs
    to the end of the encounter rather than on a saving throw, which is what
    this card prints where its siblings print a save."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.ENCOUNTER, on=victim)
        )
