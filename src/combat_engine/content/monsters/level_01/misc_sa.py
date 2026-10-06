"""Monster abilities, level 1, the blocks whose type line prints no role.

Four stat blocks, 17 rows. A role-less block is usually not an encounter
monster, and these four are three different things:

* **one is a conjured servant.** Every number on its block is 0 and its two
  attack lines are printed as *the master's* ability modifier -- "+Intelligence
  +2 vs. AC". `Attack(by=)` knows only `"companion"`, so those two cannot be
  stated in the header at all and the body rolls them with `c.attack`; see
  `_master_mod`. Its leash is the one row here refused in play.
* **two are ordinary creatures with a role missing from the line**, and are
  written exactly as any other monster: numbers from `game.db`, the attack
  bonus as printed, the damage line in the header as data.
* **one is an aura creature** whose own trait halves almost everything it
  takes, which is not resistance as the engine holds it -- resistance is per
  damage type -- so it comes off the roll in the interrupt window, the one
  moment the number exists and has not yet reached hit points. `c.halve` is
  that op.

Two judgement calls worth naming:

* **"willingly enters a square in the aura" is `Moved.kind_`.** Walk, charge,
  run, shift and teleport are the creature going; push, pull and slide are it
  being shoved, and the step the engine files as `place` is being put
  somewhere. Reading the word off the event is the whole of the printed
  "willingly", so nothing is missing here.
* **a printed range band -- "10/20" -- takes the normal range.** One of the
  four rows reading one is filed as a melee line by the importer and is
  plainly a ranged one; it is written as ranged.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.minions_sa import _by_a_trap
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_06.brutes import DEFENCES
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    Ability,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import (
    DamageRolled,
    Miss,
    Moved,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.query import adjacent, distance_between, team
from combat_engine.engine.triggers import Trigger, targets_me

#: The kinds of step a creature takes of its own accord. The rest -- push,
#: pull, slide, place -- are it being moved, which is what "willingly" rules
#: out.
_WILLING = frozenset({"walk", "charge", "run", "shift", "teleport"})


def _master_mod(c: Cast, a: Ability) -> int | None:
    """The master's ability modifier, which is what one block's attack lines
    are printed as.

    None when nothing has been made this thing's master, in which case the
    printed line has no number in it and the row cannot roll.
    """
    boss = c.master()
    stats = c.world.get(boss, Stats) if boss is not None else None
    return None if stats is None else stats.mod(a)


# --------------------------------------------------------------------------
# m5452 -- a conjured servant: every number it rolls is somebody else's
# --------------------------------------------------------------------------


_M5452_STRAY = "its master ends a turn more than 10 squares away"


def _master_ended_turn(world: World, me: int, ev: TurnEnd) -> bool:
    boss = world.relations.sources(Relation.MASTER_OF, me)
    if not boss or ev.actor != boss[0]:
        return False
    return distance_between(world, me, boss[0]) > 10


@power(
    "m5452a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 6),
)
def m5452a0(c: Cast) -> None:
    """No `attack=` in the header: the printed bonus is the master's
    Intelligence modifier plus two, and a header cannot say whose numbers it
    rolls unless they belong to a companion. The damage line stays in the
    header, where it is still data."""
    bonus = _master_mod(c, Ability.INT)
    if bonus is None:
        return
    if c.attack(bonus + 2, AC):
        c.hit()


@power(
    "m5452a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 3),
    dropped=("c.grab(dc_from=)",),
)
def m5452a1(c: Cast) -> None:
    """As m5452a0, and the grab's escape DC is the master's Will rather than
    the holder's own defence -- which `c.grab` cannot be told.

    **Re-aimed off `c.grab(dc=)`**, which is the 58-row group wanting a flat
    printed number. This wants a *defence read off a named creature*, and a
    `dc=int` would never satisfy it: `escape.py` offers REF or FORT with
    `grab_vs_fort` the only override, and neither is somebody else's Will. One
    symbol, one gap."""
    bonus = _master_mod(c, Ability.INT)
    if bonus is None:
        return
    if c.attack(bonus, REF):
        c.hit()
        c.grab()


@power(
    "m5452a2",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.run()",),
)
def m5452a2(c: Cast) -> None:
    """A conjuration's whole move action, printed out because it has none of
    its own by default. Walking its speed is the widest of the listed choices
    and the only one worth offering a policy; standing, crawling and shifting
    are already in the action menu for anything that can move at all.

    "It cannot run" is the clause with nothing to say it: nothing forbids a
    run.
    """
    c.move(c.speed_of())


@power(
    "m5452a3",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5452_STRAY,
    on=Trigger(TurnEnd, when=_master_ended_turn, text=_M5452_STRAY),
    todo=("c.leash()", "c.kill()"),
)
def m5452a3(c: Cast) -> None:
    """A leash, and both of its halves are absent.

    Nothing moves a creature *towards* a named square by the most direct
    route -- `c.move` picks its own destination through the decider and
    `c.flee` goes the other way -- and nothing drops a creature to 0 hit
    points outright, which is the price of failing to get there. The trigger
    is declared, so the row goes live the day either arrives.
    """


# --------------------------------------------------------------------------
# m6277
# --------------------------------------------------------------------------


_M6277_MISSED = "an enemy misses this creature with an attack"


@power(
    "m6277a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6277a0(c: Cast) -> None:
    """A rolled rider, so it is `dice=` rather than a flat value: the die is
    rolled afresh for every blow, which is what the sentence says."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m6277a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6277a1(c: Cast) -> None:
    for defence in DEFENCES:
        c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, when=_by_a_trap(c))


@power(
    "m6277a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m6277a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6277a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m6277a3(c: Cast) -> None:
    """Filed as "Melee 10/20", which is a range band and not a reach. Written
    as the normal half of the band, where there is no penalty."""
    if c.strike():
        c.hit()


@power(
    "m6277a4",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    group="m6277",
)
def m6277a4(c: Cast) -> None:
    """The burst takes in this creature as well as its allies, and `EACH_ALLY`
    leaves the caster out -- so the step for itself is the once-per-power line
    and goes behind `c.first`."""
    c.shift(1, who=c.target)
    if c.first and c.me not in c.targets:
        c.shift(1, who=c.me)


@power(
    "m6277a5",
    level=1,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6277_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M6277_MISSED),
)
def m6277a5(c: Cast) -> None:
    """The riposte is m6277a2 itself rather than a copy of it, so one damage
    line serves both. The grant is laid on the creature that missed and spent
    by the first attack that reads it, which is this one."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, once=True, until=When.EOT)
    c.use_power("m6277a2", on=foe, spend=False)


# --------------------------------------------------------------------------
# m6533
# --------------------------------------------------------------------------


@power(
    "m6533a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m6533a0(c: Cast) -> None:
    """An aura that burns whoever steps into it of their own accord.

    The ring is made so the board can draw it; the damage hangs off `Moved`
    rather than off `ZoneEntered`, because that event says nothing about how
    the creature got there and "willingly" is the whole difference. Moving
    from one square of the aura to another counts, which is what "enters a
    square in the aura" says.

    The once-per-turn limit is cleared as the creature's own turn opens.
    """
    me = c.me
    burned: set[int] = set()
    c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def stepped(ev: Moved) -> None:
        if ev.actor == me or getattr(ev, "kind_", "") not in _WILLING:
            return
        if ev.actor in burned or team(c.world, ev.actor) is team(c.world, me):
            return
        if not adjacent(c.world, me, ev.actor):
            return
        burned.add(ev.actor)
        c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

    def opens(ev: TurnStart) -> None:
        burned.discard(ev.actor)

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref}:turn")


@power(
    "m6533a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6533a1(c: Cast) -> None:
    """"Half damage from any source" is not resistance, which the engine holds
    per damage type; it comes off the roll in the interrupt window, the one
    moment the number exists and has not reached hit points yet.

    Psychic is both an exception to the halving and what switches it off, so
    the two clauses are the same branch. A blow of several types counts as
    psychic if any part of it is.
    """
    me = c.me
    state = {"off": False}

    def soften(ev: DamageRolled) -> None:
        if ev.target != me:
            return
        types = ev.types()
        if DamageType.PSYCHIC in types:
            state["off"] = True
            return
        if state["off"] or DamageType.FORCE in types:
            return
        c.halve(ev)

    def opens(ev: TurnStart) -> None:
        if ev.actor == me:
            state["off"] = False

    c.watch(
        DamageRolled,
        soften,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=c.ref,
    )
    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref}:turn")


@power(
    "m6533a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6533a2(c: Cast) -> None:
    """Half speed, the -5 to attacks and the combat advantage handed out are
    the *whole* of what the squeezing condition is, and the printed line
    waives all three -- so the hold comes off as it lands rather than three
    counterweights being written against it. Level 3 settled this shape."""
    _squeezes_freely(c)


@power(
    "m6533a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING),
)
def m6533a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6559
# --------------------------------------------------------------------------


@power(
    "m6559a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6559a0(c: Cast) -> None:
    """A punishment aura that costs the creature its own composure: the daze
    is part of the printed clause and goes on itself, not on the attacker.

    Hung on `Miss` rather than on the aura's own membership, because the
    trigger is the swing and not the standing: an enemy adjacent at the moment
    it misses is the whole sentence.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def missed(ev: Miss) -> None:
        if ev.attacker == me or not adjacent(c.world, me, ev.attacker):
            return
        if team(c.world, ev.attacker) is team(c.world, me):
            return
        if ev.target != me and team(c.world, ev.target) is not team(c.world, me):
            return
        c.flat(4, on=ev.attacker)
        c.dazed(on=me, until=When.SONT)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6559a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m6559a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6559a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m6559a2(c: Cast) -> None:
    """The Effect line runs whether or not the blow lands and names one ally,
    so it is outside the hit branch and behind `c.first`."""
    if c.strike():
        c.hit()
        c.push(1)
    if c.first:
        mates = sorted(a for a in c.allies() if c.adjacent(a))
        if mates:
            mate = c.choose(mates, "m6559a2: which ally steps")
            if mate is not None:
                c.shift(1, who=mate)
