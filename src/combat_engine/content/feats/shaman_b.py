"""Shaman feats.

Nearly every row here is a sentence about the spirit companion, and the
companion is real: `c.companion()` answers with it, it stands in a
square, it can be hit and it can be knocked down. So "each ally adjacent
to your spirit companion" is an ordinary list and the helpers in
`powers/shaman/_spirit.py` already build it -- `beside` for the allies
next to it, `send_spirit` for "teleport your spirit companion beside an
enemy". They read the companion fresh on every call, because it is
dismissed and called again all fight and an id captured once goes stale.

Two things the spirit does not have:

* **Nothing announces that it appeared.** `c.call_companion` places it
  and emits no event, and `PowerUsed` fires *before* a body runs -- so
  "an ally adjacent to it when it appears" is asked on `PowerResolved`,
  which is announced after. f3236 and f1862 both hang off that.
* **Nothing announces that it was dismissed.** `c.dismiss_companion`
  despawns it silently, so f3238 has no event to watch. Being *killed*
  is different: the spirit has hit points, so an attack that finishes it
  emits `Dropped`, and `Dropped.source` names who struck -- which is
  what the four "causes the spirit to disappear" feats need.

The p3773 riders are the easy half of the list: the power is a ref, the
rider only adds to what it did, and `PowerUsed.targets` names the ally
it healed.

`usage=AT_WILL` throughout bar f1877, which is the only one printing a
limit. This is not decoration: `dsl.usable` refuses an `ENCOUNTER` row
once it has been spent, so a "whenever" feat declared that way answers
its trigger once a fight and is silently inert for the rest of it --
f1030 was, and the turn it burned its use on was the one before the
spirit existed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.shaman._spirit import (
    beside,
    send_spirit,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionSpent,
    ActionType,
    Cast,
    Companion,
    Condition,
    Dropped,
    Effect,
    ForcedMove,
    Hit,
    Moved,
    MoveStart,
    PowerUsed,
    Relation,
    RelationSet,
    Trigger,
    TurnStart,
    When,
    World,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.grid import distance
from combat_engine.engine.query import adjacent, distance_between, team

#: The row that calls the spirit. Named in four prerequisites, and the
#: thing "until you next use it" in f3057-f3060 is measured against.
CALL = "p6515"
HEALING = "p3773"

#: The brief prints a power by name where a ref belongs.
NAMED = ("spec.power_ref()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)

DEFENCES = (AC, FORT, REF, WILL)


def _spirit_of(world: World, me: int) -> int | None:
    """The companion, read from a predicate where there is no `Cast`."""
    for eid in world.having(Companion):
        mine = world.get(eid, Companion)
        if mine is not None and mine.owner == me:
            return eid
    return None


def _no_spirit(world: World, eid: int) -> bool:
    """p6515's own Requirement, which a free-action use still has to meet."""
    return _spirit_of(world, eid) is None


def _used(ref: str):  # noqa: ANN202
    def when(world: World, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power == ref

    return when


def _hit_with(ref: str):  # noqa: ANN202
    def when(world: World, me: int, ev: Any) -> bool:
        return ev.attacker == me and ev.power == ref

    return when


def _spirit_felled(world: World, me: int, ev: Dropped) -> bool:
    """An attack finished the spirit off. `Dropped` is emitted before the
    body is taken off the board, so the spirit is still in its square and
    "one ally adjacent to it" can still be asked."""
    spirit = _spirit_of(world, me)
    return spirit is not None and ev.actor == spirit and ev.source is not None


def _mate_beside_spirit(world: World, me: int, ev: Any) -> bool:
    """`ev.actor` is an ally of mine standing next to my spirit."""
    spirit = _spirit_of(world, me)
    who = ev.actor
    return (
        spirit is not None
        and who not in (me, spirit)
        and team(world, who) is team(world, me)
        and adjacent(world, spirit, who)
    )


def _mates(c: Cast) -> list[int]:
    """The allies beside the spirit. `beside` counts the shaman, and an
    ally is never yourself."""
    return [a for a in beside(c) if a != c.me]


def _until_recalled(c: Cast, *held: Effect | None) -> None:
    """"...until the end of the encounter or until you next use p6515."

    The second half is the one that needs saying: the effects are laid to
    last the fight and this ends them early when the spirit is called
    back.
    """
    live = [e for e in held if e is not None]
    if not live:
        return

    def stop(ev: PowerUsed) -> None:
        if ev.actor == c.me and ev.power == CALL:
            for eff in live:
                c.world.effects.end(eff, "spirit called again")

    c.watch(PowerUsed, stop, until=When.ENCOUNTER)


# -- standing on the spirit's doorstep --------------------------------------


@power("f1020", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1020(c: Cast) -> None:
    """Untyped: the line prints "+1 bonus" with no type word. The gate is
    asked per defence roll rather than fixed now, because the spirit
    moves every round and so do the allies."""
    spirit_now = c.companion
    for friend in c.allies():
        for defence in (FORT, REF, WILL):
            c.bonus(
                defence, 1, on=friend, until=When.ENCOUNTER,
                when=lambda ctx, who=friend: (
                    (s := spirit_now()) is not None
                    and who != s
                    and c.adjacent_to(s, who)
                ),
            )


@power("f1882", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1882(c: Cast) -> None:
    """Two skill bonuses and nothing else."""


@power("f1887", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignores_difficult(when=)",))
def f1887(c: Cast) -> None:
    """Sure-footedness is a flag on a creature's `Movement`, held for a
    duration, with no gate on it -- so "while adjacent to your spirit
    companion" cannot be asked square by square as the creature crosses
    the rough ground. It is asked once, at the moment the move starts,
    and granted for that move: the closest true reading available. The
    per-square gate is the dropped clause.
    """
    def afoot(ev: MoveStart) -> None:
        spirit = c.companion()
        if spirit is None or ev.actor == spirit:
            return
        if ev.actor not in [c.me, *c.allies()]:
            return
        if c.adjacent_to(spirit, ev.actor):
            c.ignores_difficult(on=ev.actor, until=When.EOT)

    c.watch(MoveStart, afoot, until=When.ENCOUNTER)


@power("f1030", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally starts its turn adjacent to your spirit companion",
       on=Trigger(TurnStart, _mate_beside_spirit,
                  "an ally starts its turn beside the spirit"))
def f1030(c: Cast) -> None:
    """"As the first action during his or her turn" is an ordering rule
    the action menu has no way to express; the shift itself is granted
    for the turn it was earned in and expires with it."""
    c.grant_action("shift", FREE, on=c.trigger.actor, until=When.EOT)


@power("f1862", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1862(c: Cast) -> None:
    """The bonus sits on the spirit, so it has to be laid again every
    time a new one is called -- and nothing announces the call, so this
    hangs off `PowerResolved`, which is emitted after the body that
    placed it. The set of ids already seen is what stops an untyped +2
    being laid twice on a spirit that was only relocated.
    """
    done: set[int] = set()

    def bolster(who: int | None) -> None:
        if who is None or who in done:
            return
        done.add(who)
        for defence in DEFENCES:
            c.bonus(defence, 2, on=who, until=When.ENCOUNTER)

    bolster(c.companion())

    def called(ev: PowerResolved) -> None:
        if ev.actor == c.me and ev.power == CALL:
            bolster(c.companion())

    c.watch(PowerResolved, called, until=When.ENCOUNTER)


@power("f1777", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you shift",
       on=Trigger(Moved,
                  lambda w, me, ev: ev.actor == me and ev.kind_ == "shift",
                  "you shift"))
def f1777(c: Cast) -> None:
    """"The same number of squares" needs no arithmetic: `Moved` is one
    step, announced per square, so a shift of three fires this three
    times and the spirit keeps pace a square at a time."""
    spirit = c.companion()
    if spirit is not None:
        c.shift(1, who=spirit)


@power("f3055", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take a move action",
       on=Trigger(ActionSpent,
                  lambda w, me, ev: ev.actor == me and ev.cost is ActionType.MOVE,
                  "you take a move action"))
def f3055(c: Cast) -> None:
    """`c.move_companion` walks it, which is what the printed spirit does
    with your move action anyway; this only changes the distance."""
    c.move_companion(c.speed_of() + 4)


@power("f1833", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you become hidden from a creature",
       on=Trigger(RelationSet,
                  lambda w, me, ev: (
                      ev.kind_ is Relation.HIDDEN_FROM and ev.source == me
                  ),
                  "you become hidden from a creature"))
def f1833(c: Cast) -> None:
    """Being hidden is a relation from the hider to the one creature that
    cannot see, so mirroring it onto the spirit is the same relation laid
    a second time. `c.hide` has no `on=` -- it is always about the
    caster -- so this goes through `c.invisible`, which is the same held
    state and does take one."""
    spirit = c.companion()
    if spirit is not None:
        c.invisible(on=spirit, to=c.trigger.target, until=When.ENCOUNTER)


@power("f1877", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, requires=_no_spirit,
       requires_text="your spirit companion must not be present")
def f1877(c: Cast) -> None:
    """Not a trait: the whole benefit is that the call costs a free
    action once a fight, so the row is the call, at that cost, with
    `usage=AT_WILL` counting the once.

    It carries p6515's Requirement because it *is* p6515 -- the feat
    changes what the call costs and nothing else, and without the gate
    the row would be offered to a shaman who already has a spirit and
    would quietly shuffle it a square instead.
    """
    c.call_companion()


# -- the healing spirit riders ----------------------------------------------


@power("f1845", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3773",
       on=Trigger(PowerUsed, _used(HEALING), "you use p3773"))
def f1845(c: Cast) -> None:
    """`PowerUsed` fires before the body, but p3773's body neither moves
    the spirit nor moves anybody beside it, so the list is the same one
    the power itself would see."""
    for friend in _mates(c):
        c.grant_action("shift", FREE, on=friend, until=When.EOT)


@power("f1875", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3773",
       on=Trigger(PowerUsed, _used(HEALING), "you use p3773"))
def f1875(c: Cast) -> None:
    if c.wis_mod > 0:
        for friend in _mates(c):
            c.temp_hp(c.wis_mod, on=friend)


@power("f1881", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3773",
       on=Trigger(PowerUsed, _used(HEALING), "you use p3773"))
def f1881(c: Cast) -> None:
    """"Additional hit points" on top of the surge, so a plain heal on
    the power's own target."""
    if c.wis_mod > 0:
        for friend in c.trigger.targets:
            c.heal(c.wis_mod, on=friend)


@power("f1861", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p3773",
       on=Trigger(PowerUsed, _used(HEALING), "you use p3773"))
def f1861(c: Cast) -> None:
    """A free saving throw against whatever the target is carrying."""
    for friend in c.trigger.targets:
        c.save(on=friend)


@power("f1027", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget()",))
def f1027(c: Cast) -> None:
    """Moves p3773's second helping from an ally beside the spirit to one
    within 2 squares of the target. The choice is made inside that
    power's own body, and nothing lets a row outside it change who
    another row picks -- healing the wider ally from here would pay the
    hit points twice rather than instead."""


# -- speak with spirits, which is a skill check ------------------------------


@power("f1029", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1029(c: Cast) -> None:
    """Hands p3775's benefit to an ally instead of yourself. That benefit
    is a bonus to a skill check and nothing else -- p3775 is itself
    `out_of_combat` -- so moving it to another creature is still no
    combat consequence."""


@power("f1866", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1866(c: Cast) -> None:
    """Spreads the same skill bonus to the allies. Narrative for the same
    reason f1029 is."""


# -- riders on a power the brief names by ref --------------------------------


@power("f1856", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1235",
       on=Trigger(Hit, _hit_with("p1235"), "you hit with p1235"))
def f1856(c: Cast) -> None:
    """Paid with `c.flat` rather than as a damage bonus: the printed line
    is extra damage belonging to that attack, and a bonus would be
    rolled into every other one."""
    c.flat(c.roll("1d8"), on=c.trigger.target)


@power("f3053", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p9733",
       on=Trigger(Hit, _hit_with("p9733"), "you hit with p9733"))
def f3053(c: Cast) -> None:
    c.condition(Condition.DEAFENED, Condition.SLOWED,
                on=c.trigger.target, until=When.EONT)


@power("f3050", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7441",
       on=Trigger(PowerUsed, _used("p7441"), "you use that racial power"))
def f3050(c: Cast) -> None:
    """Combat advantage granted to a named list rather than to everybody,
    which is what `to=` on `c.grants_advantage` takes."""
    for foe in c.trigger.targets:
        for friend in _mates(c):
            c.grants_advantage(on=foe, to=friend, until=When.EONT)


@power("f3052", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2484",
       on=Trigger(PowerUsed, _used("p2484"), "you use that racial power"))
def f3052(c: Cast) -> None:
    """Two clocks: the standing offer lasts the encounter and each grant
    it makes lasts to the start of that ally's next turn, which is
    `When.SOTNT` -- target-clocked, so it ends on the ally's turn and not
    on the shaman's."""
    def each_turn(ev: TurnStart) -> None:
        spirit = c.companion()
        who = ev.actor
        if spirit is None or who in (c.me, spirit) or who not in c.allies():
            return
        if c.adjacent_to(spirit, who):
            c.bonus("speed", 1, on=who, until=When.SOTNT, kind="power")

    c.watch(TurnStart, each_turn, until=When.ENCOUNTER)


@power("f3054", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use that racial power"))
def f3054(c: Cast) -> None:
    """The telepathy half is wordless speech at a range -- no combat
    consequence, and nothing to write. The half that is a mechanic
    replaces that power's teleport with an exchange of places, which is
    `c.swap`: either both move or neither does."""
    spirit = c.companion()
    if spirit is not None:
        c.swap(spirit)


@power("f3049", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Dropped.power",),
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped,
                  lambda w, me, ev: (
                      ev.source == me
                      and ev.actor != me
                      and team(w, ev.actor) is not team(w, me)
                  ),
                  "you drop an enemy"))
def f3049(c: Cast) -> None:
    """"With a spirit attack power" is the dropped clause: `Dropped`
    carries who struck the blow but not the row that struck it, so this
    cannot tell a kill made from the spirit's square from any other.

    The teleport is to a free square beside an enemy within range, which
    is what `send_spirit` picks.
    """
    spirit = c.companion()
    if spirit is None:
        return
    foes = [
        f for f in c.enemies()
        if distance_between(c.world, spirit, f) <= 10
    ]
    if foes:
        send_spirit(c, min(
            foes, key=lambda f: distance_between(c.world, spirit, f)
        ))


# -- the spirit cut down -----------------------------------------------------


@power("f3057", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an attack destroys your spirit companion",
       on=Trigger(Dropped, _spirit_felled, "your spirit is destroyed"))
def f3057(c: Cast) -> None:
    friends = _mates(c)
    if not friends:
        return
    _until_recalled(c, *(
        c.bonus(defence, 2, on=friends[0], until=When.ENCOUNTER)
        for defence in DEFENCES
    ))


@power("f3058", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an attack destroys your spirit companion",
       on=Trigger(Dropped, _spirit_felled, "your spirit is destroyed"))
def f3058(c: Cast) -> None:
    """The advantage is against the killer alone and is held by one ally,
    so it is laid on the killer with `to=` naming who gets to use it."""
    friends = _mates(c)
    if friends:
        _until_recalled(c, c.grants_advantage(
            on=c.trigger.source, to=friends[0], until=When.ENCOUNTER
        ))


@power("f3059", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an attack destroys your spirit companion",
       on=Trigger(Dropped, _spirit_felled, "your spirit is destroyed"))
def f3059(c: Cast) -> None:
    _until_recalled(c, c.slowed(on=c.trigger.source, until=When.ENCOUNTER))


@power("f3060", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an attack destroys your spirit companion",
       on=Trigger(Dropped, _spirit_felled, "your spirit is destroyed"))
def f3060(c: Cast) -> None:
    killer = c.trigger.source
    friends = _mates(c)
    if friends:
        _until_recalled(c, c.bonus(
            "damage", 2, on=friends[0], until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") == killer,
        ))


@power("f3238", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Despawned.actor",))
def f3238(c: Cast) -> None:
    """A free shift for an ally when one of your own attack powers sends
    the spirit away. Being *killed* is `Dropped` and the four rows above
    answer it -- but being dismissed is `c.dismiss_companion`, which
    despawns the body and announces nothing at all, so there is no
    moment to hang this on and no "before it disappears" to read the
    adjacency at."""


@power("f3236", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p6515",
       on=Trigger(PowerResolved, _used(CALL), "you call your spirit"))
def f3236(c: Cast) -> None:
    """"Adjacent to it when it appears" has to be asked after the spirit
    is standing there, and `PowerUsed` is announced before the body runs
    -- so this answers `PowerResolved` instead. p6515 is a minor action
    on its own card, so the printed qualifier is the ordinary case; only
    f1877's free-action use is outside it, and nothing on the event says
    which action was spent."""
    friends = _mates(c)
    if friends and c.int_mod > 0:
        c.temp_hp(c.int_mod, on=friends[0])


@power("f3061", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an ally adjacent to your spirit is pushed, pulled or slid",
       on=Trigger(ForcedMove,
                  lambda w, me, ev: (
                      (s := _spirit_of(w, me)) is not None
                      and ev.target not in (me, s)
                      and team(w, ev.target) is team(w, me)
                      and adjacent(w, s, ev.target)
                  ),
                  "an ally beside your spirit is forced to move"))
def f3061(c: Cast) -> None:
    """Declared as an interrupt although the printed action is free: the
    distance a shove covers is agreed inside `ForcedMove`'s own resolve
    callback, which runs between the before and after windows, so a row
    answering in the after window would shorten a move that had already
    happened.

    `once=True` spends the reduction on this shove rather than on every
    one until the end of the turn.
    """
    if c.con_mod <= 0 or not c.dismiss_companion():
        return
    c.bonus("forced", c.con_mod, on=c.trigger.target, until=When.EOT,
            once=True)


# -- the ones with nothing to hang on ----------------------------------------


@power("f1851", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1851(c: Cast) -> None:
    """An attack bonus on one spirit power, whose ref the spec now
    carries. The attack context is handed `power`, so the gate is the
    declared row rather than a guess. No type word is printed, so the
    bonus is untyped."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p5388")


@power("f3051", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3051(c: Cast) -> None:
    """A damage bonus on the ranged basic attack `p9732` hands an ally.

    The hold was real and is closed: the shot `p9732` grants now carries
    the ref of the row that granted it, so the bonus gates on that
    rather than on `rba`, which would also have paid for every ordinary
    shot the ally took.

    A trait rather than an at-will, and the usage goes back to
    ENCOUNTER with it: nothing here is chosen on a turn.
    """
    def granted(ev: Any) -> None:
        if ev.granted_via != "p9732" or ev.granted_by != c.me:
            return
        c.bonus(
            "damage", 2, kind="power", on=ev.actor, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("granted_via") == "p9732",
        )

    c.watch(PowerUsed, granted, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} spirit shot")


@power("f1867", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449",
       on=Trigger(PowerUsed, _used("p1449"), "you use that racial power"))
def f1867(c: Cast) -> None:
    """Teleports the spirit alongside the racial teleport, as far as the
    shaman went.

    `PowerUsed` fires **before** the body, so the distance is not known
    here -- the shaman has not moved yet. `Moved` is the only event
    carrying both ends of a step and the word for how it was made, so
    the watch reads the distance off it the moment the teleport lands.
    """
    spirit = c.companion()
    if spirit is None:
        return

    def follow(ev: Any) -> None:
        if ev.actor != c.me or getattr(ev, "kind_", "") != "teleport":
            return
        c.teleport(distance(ev.from_, ev.to), who=spirit)

    c.watch(Moved, follow, until=When.EOT, once=True)


@power("f3056", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f3056(c: Cast) -> None:
    """An attack bonus for the allies beside the spirit when a racial
    reroll lands. `p1450` is a ref and the rest of the sentence is
    ordinary -- what is missing is that nothing announces that a roll was
    a reroll."""


@power("f2300", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.raise_bonus()",))
def f2300(c: Cast) -> None:
    """Doubles the bonus a racial trait grants while the spirit stands
    beside a bloodied enemy. Two things are absent: `m1031a4` is not in
    the tree, so there is no bonus standing to be raised, and nothing
    lets one row change the size of the modifier another row laid."""
