"""Monster abilities, level 4, skirmishers.

Forty-three stat blocks, 169 rows. The conventions are the ones the level 1-3
sweeps settled and they are kept unchanged here:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=9)`) and the damage line goes in the header as data
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* a printed range of "5/10" takes the **normal** range, so the creature shoots
  inside the band where it has no penalty;
* combat advantage is read off the roll (`c.result.advantage`) rather than
  asked of the board afterwards, because `resolve.attack` clears
  `HIDDEN_FROM` the moment the attack is over.

Almost every shared shape here was written for levels 1-3 and is imported
rather than copied: this role prints the same six sentences over and over --
"shift 1 when a melee attack misses it", "extra damage against a target that
grants combat advantage", "move and swing once on the way" -- and eleven
helpers cover most of them. The four written below are the ones no earlier
level needed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import (
    _crit_line,
    _felled_by_a_crit,
    _shattered,
)
from combat_engine.content.monsters.level_01.minions_sa import (
    _MISSED_ME_MELEE,
    _by_a_trap,
)
from combat_engine.content.monsters.level_01.skirmishers_sa import (
    _advantage_rider as _typed_advantage_rider,
)
from combat_engine.content.monsters.level_01.skirmishers_sa import (
    _crowd_around,
    _i_rolled_one,
    _mounted,
    _moved_far,
)
from combat_engine.content.monsters.level_02.artillery_sa import (
    _extra_against_advantage,
)
from combat_engine.content.monsters.level_02.controllers_sa import _recharge_on_miss
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _conceal,
    _had_advantage,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import (
    _shift_and_swing,
    _until_escape,
)
from combat_engine.content.monsters.level_03.skirmishers import (
    _grabbing,
    _not_grabbing,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _adjacent_foes,
    _has_the_drop,
    _mobile_attack,
    _nearest,
    _per_round_rider,
    _reachable,
    _recharge_when_bloodied,
    _shift_up_to,
    _step_beside,
    _while_bloodied,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
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
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    Moved,
    OpportunityWindow,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    flanked_by,
    is_,
    squares,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_opportunity,
    targets_me,
)

#: "Trigger: An attack misses it" -- wider than the melee-only one, and three
#: blocks here print it.
_MISSED_ME = "an attack misses it"


# --------------------------------------------------------------------------
# Shared shapes new to this level
# --------------------------------------------------------------------------


def _run_and_strike(
    c: Cast, total: int, *, ref: str = "", times: int = 1, shifting: bool = False
) -> None:
    """Spend the movement in halves and swing on the way, once or twice.

    `_mobile_attack` is the one-basic-attack version; a *named* row and a
    second swing are what the dragons and the fliers here print instead, and
    neither could be passed to it. The distance goes in two halves rather than
    all at once because "at any point during that movement" is what puts a
    creature in reach that one step to one destination would not.
    """
    step = c.shift if shifting else c.move
    half = max(1, total // 2)
    step(half)
    for _ in range(times):
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is None:
            break
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
        if ref:
            c.use_power(ref, on=foe)
        else:
            c.basic(on=foe)
    rest = total - half
    if rest > 0:
        step(rest)


def _shift_into(c: Cast, total: int, pay: Callable[[int], None]) -> None:
    """Shift, let the step land in an occupied square, and pay out on whoever
    was standing there.

    `c.overrun` is the only verb that moves through a creature's space and it
    **walks**, so a printed shift resolved with it opens opportunity windows
    the card does not allow. `movement.shift` refuses an occupied square
    outright, so `share=True` is what makes the printed line mean anything.
    """
    for foe in _adjacent_foes(c, total):
        for sq in sorted(squares(c.world, foe)):
            if c.shift(total, to=sq, share=True):
                pay(foe)
                return
    c.shift(total)


def _step_into_flank(c: Cast) -> bool:
    """Shift one square, but only where the step lands in a flank.

    The printed condition is on the *destination* rather than on the creature,
    and `c.shift` with a bare distance asks the controller for a square -- which
    on a quiet board steps anywhere. So the eight neighbours are tested against
    the grid's own flanking test first and the step is aimed.
    """
    here = c.here
    mine = [sq for mate in c.allies() for sq in squares(c.world, mate)]
    for sq in sorted(spread({here}, 1) - {here}):
        if not c.world.grid.passable(sq) or c.world.grid.occupant(sq) is not None:
            continue
        for foe in c.enemies():
            space = squares(c.world, foe)
            if any(c.world.grid.flanks(sq, b, space) for b in mine):
                return c.shift(1, to=sq)
    return False


def _hauls_the_grabbed(c: Cast, victim: int) -> None:
    """Drag a grabbed creature along, and give it no opening for the trip.

    The destination is named rather than the distance -- the card says the
    creature ends adjacent -- so `_step_beside` picks the square and `c.slide`
    puts it there. The grab survives because nothing here ends it.
    """
    sq = _step_beside(c, victim, c.me)
    if sq is not None:
        c.slide(99, on=victim, to=sq)
    c.no_provoke(from_=victim, on=c.me, until=When.EOT)


def _ridden_by_fourth_level(world: World, eid: int) -> bool:
    """"While mounted by a friendly rider of 4th level or higher".

    **`targets`, not `sources`.** The relation is `set(RIDDEN_BY, mount, rider)`,
    so a mount's riders are its `targets`; its `sources` are whatever *it* rides,
    which for a mount is empty every time. `c.rider` and `c.mount` are those two
    directions.

    This asked `sources`, so the gate was false forever -- which also silently
    emptied the watch body it guards. The identical mistake was fixed in
    `level_02/skirmishers_sa.py` earlier in the same campaign; two files made it
    independently, which is the argument for `query` owning this question
    (#362).
    """
    for rider in world.relations.targets(Relation.RIDDEN_BY, eid):
        stats = world.get(rider, Stats)
        if stats is not None and stats.level >= 4:
            return True
    return False


def _ally_beside_the_target(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"If a target has an ally of it adjacent, it has combat advantage."

    The mirror of `grants_advantage`: the set is whatever happens to be beside
    one of its friends at the moment of the swing, which is not knowable when
    the trait arms, so it is a gate on the attack rather than a relation.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and _crowd_around(c, victim, least=1)

    return gate


def _hit_me_since_my_turn(c: Cast) -> set[int]:
    """Who has landed one on this creature since its own last turn began.

    Nothing records it, and the log is the only place the swings are. Read
    backwards and stopped at this creature's own turn, which is the window the
    card names.
    """
    out: set[int] = set()
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == c.me and not ev.ghost:
            break
        if isinstance(ev, Hit) and ev.target == c.me:
            out.add(ev.attacker)
    return out


def _dying_in_reach(world: World, eid: int) -> bool:
    """"Melee 1 (one dying humanoid)", as much of it as a gate can ask.

    The type word is not reachable from `(world, eid)` -- `c.kinds_of` reads a
    stat block through a `Cast` -- so the gate asks for a dying creature and the
    body asks the rest.
    """
    return _reachable(world, eid, 1, lambda foe: is_(world, foe, Condition.DYING))


def _enemy_flanked_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy ends its movement in a square where it flanks it."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me:
        return False
    from combat_engine.engine.query import team

    return (
        team(world, actor) is not team(world, me)
        and distance_between(world, me, actor) <= 1
        and flanked_by(world, me, actor)
    )


def _necrotic_hurt(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) is DamageType.NECROTIC
    )


def _doses_left(world: World, eid: int) -> bool:
    """"It has enough poison for three attacks", on a card printed at-will.

    `uses=` is an encounter row's allowance and putting it on an at-will makes
    the header disagree with the page, so the stock is counted off the log:
    `PowerUsed` is the only record of how often a row has been used, and the
    gate is asked with `(world, eid)` where no `Cast` exists to read a tally.
    """
    from combat_engine.engine.events import PowerUsed

    spent = sum(
        1
        for ev in world.bus.log
        if isinstance(ev, PowerUsed) and ev.actor == eid and ev.power == "m3214a1"
    )
    return spent < 3


def _against_opportunity(ctx: dict[str, Any]) -> bool:
    """"...against opportunity attacks", asked of the attack context."""
    return bool(ctx.get("opportunity"))


def _ends_move_beside(c: Cast) -> None:
    """"Gains combat advantage against any target it ends its move adjacent to."""
    for foe in _adjacent_foes(c):
        c.grants_advantage(on=foe, to=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m1010
# --------------------------------------------------------------------------


@power(
    "m1010a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 1),
)
def m1010a0(c: Cast) -> None:
    """The burn and the step are both bought by combat advantage, so they are
    one gate read off the roll."""
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.ongoing(5, DamageType.POISON)
            c.shift(1)


# --------------------------------------------------------------------------
# m1065
# --------------------------------------------------------------------------


@power(
    "m1065a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_mounted,
    requires_text="must be mounted by a friendly rider",
)
def m1065a0(c: Cast) -> None:
    """"It can shift 2 squares instead of 1" is a line in the action menu
    rather than a bonus: `actions.legal` reads a shift as one square and
    nothing else, and `c.shift_as` is the standing change that says otherwise."""
    c.shift_as(MOVE, 2, on=c.me, until=When.ENCOUNTER)


@power(
    "m1065a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 6),
)
def m1065a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m115821
# --------------------------------------------------------------------------


@power(
    "m115821a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
)
def m115821a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115821a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.WEAPON],
)
def m115821a1(c: Cast) -> None:
    """The step comes first and the swing is the other row, used at this row's
    action cost -- which is what `c.use_power` is for."""
    c.shift(1)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.use_power("m115821a0", on=foe)


@power(
    "m115821a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 0),
    requires=_while_bloodied,
    requires_text="must be bloodied",
)
def m115821a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


# --------------------------------------------------------------------------
# m115923
# --------------------------------------------------------------------------


@power(
    "m115923a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115923a0(c: Cast) -> None:
    """The window's own `kind` is what says the move was a charge -- `why`
    reads "moved away" for a walk, a charge and a flight alike."""
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("kind") == "charge",
    )


@power(
    "m115923a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115923a1(c: Cast) -> None:
    """Paid as damage equal to whatever it has left rather than by writing to
    `Health`, so `Dropped` is announced the one way everything else announces
    it -- which is what the other row on this block is listening for."""
    _shattered(c)


@power(
    "m115923a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
)
def m115923a2(c: Cast) -> None:
    """Two expressions, so the bigger one is rolled in the body; `c.charge`
    says whether this use is the charge's own swing."""
    if c.strike():
        if c.charge:
            c.damage("2d8", 6)
        else:
            c.hit()


@power(
    "m115923a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m115923a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m115923a4",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points, but not by a critical hit",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m115923a4(c: Cast) -> None:
    """"Not by a critical hit" is answered off the log: `Dropped` carries who
    struck the creature and not how, and the most recent `Hit` on it is the
    blow. `c.reanimate` is the only verb that puts a creature that has already
    gone down back on the board at a named hit point total."""
    if _felled_by_a_crit(c):
        return
    if c.roll("1d20") >= 15:
        c.reanimate(on=c.me, hp=1)


# --------------------------------------------------------------------------
# m1434
# --------------------------------------------------------------------------


@power(
    "m1434a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m1434a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1434a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m1434a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1434a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1434a2(c: Cast) -> None:
    """Two swings of the other row, which may land on the same creature --
    the card names no second target."""
    for _ in range(2):
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is None:
            break
        c.use_power("m1434a1", on=foe)


@power(
    "m1434a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=7),
)
def m1434a3(c: Cast) -> None:
    """No damage at all -- the whole hit is the square the creature ends in."""
    if c.strike():
        c.slide(1)


@power(
    "m1434a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 3, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("c.aftereffect()",),
)
def m1434a4(c: Cast) -> None:
    """The aftereffect is the one clause with nowhere to live: nothing fires
    when a save succeeds, so "slowed again (save ends)" cannot be hung on the
    save that ended the first slow. The printed recharge is the bloodied line
    on top of the die, and the two only ever agree to offer the row sooner."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
        c.slowed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m1446
# --------------------------------------------------------------------------


@power(
    "m1446a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 3),
)
def m1446a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1446a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("3d6", 3, dtype=DamageType.RADIANT, kind=LIMITED, half_on_miss=True),
)
def m1446a1(c: Cast) -> None:
    """"Teleports 1 square for each enemy caught in the blast", paid one
    square at a time inside the hit branch -- which is also the Miss line,
    since a target it missed buys it no step."""
    if c.strike():
        c.hit()
        c.teleport(1)
    else:
        c.hit(half=True)


@power(
    "m1446a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m1446a2(c: Cast) -> None:
    """A death throe. The light it goes out in has no combat meaning and is
    not written."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m1446a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1446a3(c: Cast) -> None:
    """The defence bonus is laid *before* the step, so the openings the move
    itself provokes are already covered by it."""
    c.bonus(AC, 4, on=c.me, until=When.EOT, when=_against_opportunity)
    c.move(4)
    _ends_move_beside(c)


@power(
    "m1446a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1446a4(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m1469
# --------------------------------------------------------------------------


@power(
    "m1469a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
)
def m1469a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m1469a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m1469a1(c: Cast) -> None:
    _typed_advantage_rider(c, "1d6", dtype=DamageType.NECROTIC)


@power(
    "m1469a2",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
)
def m1469a2(c: Cast) -> None:
    """A shift that may finish inside somebody, which is `share=True` and not
    `c.overrun`: the trample verb walks, and a walk opens the windows this
    card's shift does not."""

    def pay(foe: int) -> None:
        c.damage("1d6", dtype=DamageType.NECROTIC, on=foe)
        c.weakened(on=foe)

    _shift_into(c, 6, pay)


@power(
    "m1469a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.stat_block()",),
)
def m1469a3(c: Cast) -> None:
    """Everything this row does is put a *different* stat block on the board,
    and the brief gives no ref for it -- `c.summon` needs one and `c.reanimate`
    raises the corpse as itself, which is the wrong creature. The ritual
    clause is a note to a referee and has no combat half either."""


# --------------------------------------------------------------------------
# m1514
# --------------------------------------------------------------------------


@power(
    "m1514a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m1514a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1514a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m1514a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1514a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m1514a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1514a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1514a3(c: Cast) -> None:
    """Two halves and both are verbs: the use is handed back and then spent
    again at once, which is the printed "recharges, and the creature uses it
    immediately"."""
    c.restore_use("m1514a2", on=c.me)
    foe = _nearest(c)
    if foe is not None:
        c.use_power("m1514a2", on=foe)


@power(
    "m1514a4",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1514a4(c: Cast) -> None:
    """"It resumes its normal form at the end of this move" is the hold being
    ended by hand rather than a duration: no `When` measures the inside of one
    move, and `When.EOT` would leave the creature untouchable for the rest of
    its turn."""
    held = c.insubstantial(on=c.me, until=When.EOT)
    c.move(8)
    if held is not None:
        c.end_effect(held, why="the move is over")


# --------------------------------------------------------------------------
# m1525
# --------------------------------------------------------------------------


@power(
    "m1525a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m1525a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1525a1",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=7),
)
def m1525a1(c: Cast) -> None:
    if c.strike():
        c.pull(3)


@power(
    "m1525a2",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.spring_trap()",),
)
def m1525a2(c: Cast) -> None:
    """The move is the whole row and it works. Walking past a trap without
    setting it off is the clause with nothing to say it: nothing arms, trips
    or exempts a trap from a creature's step."""
    c.move(c.speed_of())


@power(
    "m1525a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1525a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m1525a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1525a4(c: Cast) -> None:
    """"All defences" is four modifiers, and the narrowing is a key on the
    attack context -- the attacker is there and nowhere else."""
    gate = _by_a_trap(c)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.ENCOUNTER, when=gate)


# --------------------------------------------------------------------------
# m1992
# --------------------------------------------------------------------------


@power(
    "m1992a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m1992a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m1992a1",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1992a1(c: Cast) -> None:
    """The waiver is laid first and lifted with the turn: it has to stand
    while the step is taken, not after it."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(4)


# --------------------------------------------------------------------------
# m3119
# --------------------------------------------------------------------------


@power(
    "m3119a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 4),
)
def m3119a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3119a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 4),
)
def m3119a1(c: Cast) -> None:
    """A printed range of "5/10" takes the normal band, where the creature
    shoots at no penalty."""
    if c.strike():
        c.hit()


@power(
    "m3119a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
)
def m3119a2(c: Cast) -> None:
    """Four outcomes off one die, so the damage cannot be header data: each
    branch is a different expression and one of them is a heal."""
    if not c.strike():
        return
    match c.roll("1d4"):
        case 1:
            c.damage("1d6", 4)
        case 2:
            c.damage("1d8", 4, dtype=DamageType.FIRE)
            for near in c.within(1, of=c.target):
                if near != c.target:
                    c.flat(5, dtype=DamageType.FIRE, on=near)
        case 3:
            c.damage("1d6", 4)
            c.slowed(until=When.SAVE_ENDS)
        case _:
            c.heal(5)


@power(
    "m3119a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3119a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m3119a4",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
    dropped=("c.draw()",),
)
def m3119a4(c: Cast) -> None:
    """The ground it leaves behind is a one-square zone and it works. What
    spills out of its pack is the other half: nothing puts a carried item on
    the floor, which is the same gap `c.draw()` names everywhere else."""
    c.zone({c.here}, difficult=True, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m3129
# --------------------------------------------------------------------------


@power(
    "m3129a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m3129a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3129a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m3129a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3129a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3129a2(c: Cast) -> None:
    _run_and_strike(c, 8, ref="m3129a1", times=2)


@power(
    "m3129a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3129a3(c: Cast) -> None:
    """"When the mount's movement provokes" is the opportunity window itself,
    which is the only place that knows a move opened it -- so the rider is put
    out of reach as the window opens rather than for the whole turn.

    Every condition the card prints is asked **inside** the watch rather than as
    a `requires=` gate: a trait arms once at the start of the fight, and who is
    in the saddle, how high the mount is and what level the rider is are all
    things that change between rounds. Gated at the door, the trait would be
    dead for the whole fight because of how the board happened to start.
    """
    me = c.me

    def shield(ev: OpportunityWindow) -> None:
        if ev.provoker != me or not ev.kind_ or c.height(on=me) <= 0:
            return
        if not _ridden_by_fourth_level(c.world, me):
            return
        for passenger in c.world.relations.targets(Relation.RIDDEN_BY, me):
            c.cannot_attack(on=ev.actor, against=passenger, until=When.EOT)

    c.watch(
        OpportunityWindow, shield, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} rider cover",
    )


# --------------------------------------------------------------------------
# m3214
# --------------------------------------------------------------------------


@power(
    "m3214a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m3214a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m3214a1",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
    requires=_doses_left,
    requires_text="must have poison left, three doses to a fight",
)
def m3214a1(c: Cast) -> None:
    """The card is at-will and the stock is three, which is not `uses=` -- that
    field is an encounter row's allowance and would make the header disagree
    with the page.

    `c.apply_poison` is the right verb for a character and the wrong one here:
    it keys the hold on a `Weapon` in hand so the dose cannot ride the wrong
    swing, and a monster carries no gear at all -- `c.held` is empty, the hold
    is refused, and the row is silently inert. The blade the card names is this
    creature's own melee row, so the rider is tied to **that ref** instead,
    which is the same guarantee by a different handle.
    """
    me, bonus = c.me, c.world.scaling.trim(7, c.level)

    def bite(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3214a0":
            return
        if c.attack(bonus, FORT, on=ev.target):
            c.ongoing(5, DamageType.POISON, on=ev.target)
            c.dazed(until=When.SAVE_ENDS, on=ev.target)

    c.watch(
        Hit, bite, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} coated",
    )


@power(
    "m3214a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is targeted by a melee or a ranged attack",
    on=Trigger(AttackDeclared, targets_me, "it is targeted by an attack"),
)
def m3214a2(c: Cast) -> None:
    """Two verbs for one sentence: `c.swap` exchanges the squares and
    `c.redirect` moves the blow. An interrupt, so the roll has not happened
    and the ally is attacked rather than merely hit."""
    _recharge_when_bloodied(c)
    mate = next(
        (a for a in c.allies() if distance_between(c.world, c.me, a) <= 2), None
    )
    if mate is None:
        return
    c.swap(mate)
    c.redirect(to=mate)


@power(
    "m3214a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3214a3(c: Cast) -> None:
    _advantage_rider(c, "2d6")


# --------------------------------------------------------------------------
# m3301
# --------------------------------------------------------------------------


@power(
    "m3301a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m3301a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3301a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 1),
)
def m3301a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3301a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3301a2(c: Cast) -> None:
    """"Two initiative checks" is the second check made here and handed to
    `c.extra_turn`, which is the slot a solo gets. The refresh of the
    immediate action falls out of having a second turn at all -- `Budget` is
    reset per turn and not per round."""
    c.extra_turn(c.roll("1d20") + c.dex_mod)


@power(
    "m3301a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3301a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m3301a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3301a4(c: Cast) -> None:
    _advantage_rider(c, "1d6")


# --------------------------------------------------------------------------
# m3502
# --------------------------------------------------------------------------


@power(
    "m3502a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m3502a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3502a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="a creature granting it combat advantage",
        grants_ca=True,
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m3502a1(c: Cast) -> None:
    """`c.spend_surge` is the whole of "the target loses a healing surge"."""
    if c.strike():
        c.hit()
        c.spend_surge(on=c.target)


@power(
    "m3502a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3502a2(c: Cast) -> None:
    _run_and_strike(c, 4, times=2, shifting=True)


@power(
    "m3502a3",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, both(_i_rolled_one, by_melee), "it hits with a melee attack"),
)
def m3502a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3505
# --------------------------------------------------------------------------


@power(
    "m3505a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m3505a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m3505a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3505a1(c: Cast) -> None:
    """A trait whatever the database files it as: nothing is spent on it. "On
    its turn" is the gate the window needs and `c.turn_of` is the only thing
    that answers it, so it is asked inside the watch rather than declared."""
    me = c.me

    def burn(ev: Hit) -> None:
        if ev.target != me or c.turn_of() != me:
            return
        from combat_engine.engine.triggers import _power_of

        row = _power_of(ev)
        if row is None or row.reach.kind not in ("melee", "close_burst", "close_blast"):
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.attacker)

    c.watch(Hit, burn, until=When.ENCOUNTER, on=me, label=f"{c.ref} recoil")


@power(
    "m3505a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3505a2(c: Cast) -> None:
    """Read off the roll: a one-shot grant of combat advantage is spent by the
    time the blow lands, so asking the board again answers about a world that
    no longer exists."""
    me = c.me

    def rot(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        c.ongoing(5, DamageType.NECROTIC, on=ev.target)

    c.watch(Hit, rot, until=When.ENCOUNTER, on=me, label=f"{c.ref} rot")


@power(
    "m3505a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3505a3(c: Cast) -> None:
    """The whole printed line is how the creature looks and one Insight check
    to see through it. Nothing in a fight rolls against an appearance, so the
    row is complete and deliberately inert rather than unwritten."""


# --------------------------------------------------------------------------
# m3536
# --------------------------------------------------------------------------


@power(
    "m3536a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m3536a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3536a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3536a1(c: Cast) -> None:
    """`charge` is a plain attribute on `Hit`, set after the fact, so it is
    read with `getattr`. The extra die is rolled flat -- `c.damage` maxes its
    dice on a critical and this one is an addition, not the blow."""
    me = c.me

    def bowl_over(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3536a0":
            return
        if not getattr(ev, "charge", False) or c.height(on=me) <= 0:
            return
        c.flat(c.roll("1d8"), on=ev.target)
        c.push(2, on=ev.target)

    c.watch(Hit, bowl_over, until=When.ENCOUNTER, on=me, label=f"{c.ref} dive")


@power(
    "m3536a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3536a2(c: Cast) -> None:
    _shattered(c)


# --------------------------------------------------------------------------
# m3548
# --------------------------------------------------------------------------


@power(
    "m3548a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
    dropped=("spec.weapon_ref()",),
)
def m3548a0(c: Cast) -> None:
    """The high-crit line *replaces* the damage rather than adding to it, and
    it is a roll -- so it is paid flat, past the engine's rule that a critical
    maxes the declared dice. The printed weapon requirement has no ref: a
    monster carries no named gear."""
    if c.strike():
        _crit_line(c, "1d6", 11)


@power(
    "m3548a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
    dropped=("spec.weapon_ref()",),
)
def m3548a1(c: Cast) -> None:
    """The extraction lost the range band for this one -- the card is a thrown
    weapon and the spec prints no number, so 6 is the ordinary thrown range
    rather than a figure read off the page."""
    if c.strike():
        c.hit()


@power(
    "m3548a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    dropped=("etl.monster.attack_defence()",),
)
def m3548a2(c: Cast) -> None:
    """The movement and the swing are the whole of what this does and both
    work. The attack line the extraction left behind reads "+7 vs <one> or
    <other> (whichever is lower)" with both names gone, so there is no defence
    to declare and none is invented."""
    _shift_and_swing(c, 3)


@power(
    "m3548a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5, kind=LIMITED),
    dropped=("spec.weapon_ref()",),
)
def m3548a3(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d6", 17)
        c.grants_advantage(to=c.me, until=When.EONT)


@power(
    "m3548a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3548a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m3548a5",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3548a5(c: Cast) -> None:
    """"Once per round" is the whole difference from the ordinary version of
    this trait, which is why it is a different helper rather than a flag."""
    _per_round_rider(c, "2d6", _had_advantage)


# --------------------------------------------------------------------------
# m3554
# --------------------------------------------------------------------------


@power(
    "m3554a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 2, dtype=DamageType.NECROTIC),
)
def m3554a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3554a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3554a1(c: Cast) -> None:
    _typed_advantage_rider(c, "1d8", dtype=DamageType.NECROTIC)


@power(
    "m3554a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3554a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m3554a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3554a3(c: Cast) -> None:
    c.gains_advantage(_ally_beside_the_target(c), until=When.ENCOUNTER, on=c.me)


# --------------------------------------------------------------------------
# m3558
# --------------------------------------------------------------------------


@power(
    "m3558a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
    dropped=("Damage(dtypes=)",),
)
def m3558a0(c: Cast) -> None:
    """The blow is fire *and* necrotic -- one roll of two types, which
    resistance has to see both of. `Damage` carries a single `dtype`, so the
    header declares the first and the second is named rather than faked."""
    if c.strike():
        c.hit()


@power(
    "m3558a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3558a1(c: Cast) -> None:
    c.shift(1)


@power(
    "m3558a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3558a2(c: Cast) -> None:
    c.gains_advantage(_ally_beside_the_target(c), until=When.ENCOUNTER, on=c.me)


@power(
    "m3558a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
)
def m3558a3(c: Cast) -> None:
    """The rider pays one type, as the attack it rides does: `c.damage` takes
    `dtypes` but the helper every one of these traits shares takes one, and a
    second copy of the rider would pay twice for one printed sentence."""
    _typed_advantage_rider(c, "1d8", dtype=DamageType.FIRE)


# --------------------------------------------------------------------------
# m3560
# --------------------------------------------------------------------------


@power(
    "m3560a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m3560a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3560a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    dropped=("etl.monster.attack_defence()",),
)
def m3560a1(c: Cast) -> None:
    """Both defences this attack names were lost in extraction, so there is no
    pair to compare and none is guessed. The move and the basic attack it
    carries are the printed Effect and they work."""
    _mobile_attack(c, max(1, c.speed_of() // 2))


@power(
    "m3560a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    dropped=("spec.weapon_ref()", "etl.monster.attack_defence()"),
)
def m3560a2(c: Cast) -> None:
    """A burst that swings the creature's own basic attack at everything
    inside it, which rolls its own attack -- so the mangled defence on this
    row's line never has to be read."""
    c.basic(on=c.target)


@power(
    "m3560a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3560a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m3560a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _MISSED_ME_MELEE),
)
def m3560a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3562
# --------------------------------------------------------------------------


@power(
    "m3562a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m3562a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 13)


@power(
    "m3562a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    charges=True,
    dropped=("spec.weapon_ref()", "etl.monster.attack_defence()"),
)
def m3562a1(c: Cast) -> None:
    """`charges=True` or the engine measures a sword's reach before the run
    and refuses the row for every distance a charge is for. The waiver is
    narrowed to the square it leaves, which is the window `kind` names."""
    foe = c.target
    if foe is None:
        return
    c.no_provoke(
        from_=foe, on=c.me, until=When.EOT,
        when=lambda ctx: ctx.get("kind") == "charge",
    )
    c.charge_at(foe)
    c.shift(1)


@power(
    "m3562a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3562a2(c: Cast) -> None:
    _shattered(c)


# --------------------------------------------------------------------------
# m3570
# --------------------------------------------------------------------------


@power(
    "m3570a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m3570a0(c: Cast) -> None:
    """The spec's prose names the other block's ref throughout; the rows are
    written for the block they belong to."""
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m3570a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3570a1(c: Cast) -> None:
    me = c.me

    def burn(ev: Hit) -> None:
        if ev.target != me or c.turn_of() != me:
            return
        from combat_engine.engine.triggers import _power_of

        row = _power_of(ev)
        if row is None or row.reach.kind not in ("melee", "close_burst", "close_blast"):
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.attacker)

    c.watch(Hit, burn, until=When.ENCOUNTER, on=me, label=f"{c.ref} recoil")


@power(
    "m3570a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3570a2(c: Cast) -> None:
    me = c.me

    def rot(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        c.ongoing(5, DamageType.NECROTIC, on=ev.target)

    c.watch(Hit, rot, until=When.ENCOUNTER, on=me, label=f"{c.ref} rot")


@power(
    "m3570a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3570a3(c: Cast) -> None:
    """How the creature looks, and one Insight check to see past it. Nothing
    in a fight rolls against an appearance, so this is finished and inert."""


# --------------------------------------------------------------------------
# m4009
# --------------------------------------------------------------------------


@power(
    "m4009a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 3),
)
def m4009a0(c: Cast) -> None:
    """The secondary attack is rolled in the body with the printed total put
    through `scaling.trim`, which is what the header's `printed=` does for the
    first one -- the engine takes the level term back out either way."""
    if c.strike():
        c.hit()
        if c.attack(c.world.scaling.trim(9, c.level), FORT):
            c.ongoing(5, DamageType.POISON)


@power(
    "m4009a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4009a1(c: Cast) -> None:
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.use_power("m4009a0", on=foe)
    c.shift(c.speed_of())


@power(
    "m4009a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4009a2(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4182
# --------------------------------------------------------------------------


@power(
    "m4182a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m4182a0(c: Cast) -> None:
    """The acid is a second expression and not a second type on the same roll,
    so it is rolled on its own rather than named as a gap."""
    c.shift(2)
    if c.strike():
        c.hit()
        c.damage("1d4", dtype=DamageType.ACID)
    c.shift(2)


@power(
    "m4182a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4182a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4182a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4182a2(c: Cast) -> None:
    for _ in range(2):
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is None:
            break
        c.use_power("m4182a1", on=foe)
    c.shift(2)


@power(
    "m4182a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4182a3(c: Cast) -> None:
    _mobile_attack(c, 8)


@power(
    "m4182a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m4182a4(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4507
# --------------------------------------------------------------------------


@power(
    "m4507a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 5),
)
def m4507a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(3)


@power(
    "m4507a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 5, kind=LIMITED),
)
def m4507a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4507a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
)
def m4507a2(c: Cast) -> None:
    """No damage of its own -- the whole hit is the swings it hands out, and
    `c.grant_attack` uses each ally's own basic attack rather than a
    hand-rolled copy of one."""
    if not c.strike():
        return
    victim = c.target
    for mate in c.allies():
        if victim is not None and distance_between(c.world, mate, victim) <= 1:
            c.grant_attack(mate, on=victim)


@power(
    "m4507a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(Hit, targets_me, "an enemy hits it with an attack"),
)
def m4507a3(c: Cast) -> None:
    """"Uses the new result" is `keep="new"` -- not the better of the two,
    which is what every other reroll in the tree prints."""
    c.reroll_attack(keep="new")


@power(
    "m4507a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4507a4(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m5216
# --------------------------------------------------------------------------


@power(
    "m5216a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5216a0(c: Cast) -> None:
    c.gains_advantage(_ally_beside_the_target(c), until=When.ENCOUNTER, on=c.me)


@power(
    "m5216a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5216a1(c: Cast) -> None:
    """Two expressions and two different questions: the bigger die is bought
    by the target already being prone, the knockdown by combat advantage."""
    if c.strike():
        if c.is_(Condition.PRONE):
            c.damage("3d6", 5)
        else:
            c.hit()
        if c.result is not None and c.result.advantage:
            c.prone()


# --------------------------------------------------------------------------
# m5318
# --------------------------------------------------------------------------


@power(
    "m5318a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m5318a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.ongoing(5)


@power(
    "m5318a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m5318a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5318a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3, kind=LIMITED),
    requires=_has_the_drop,
    requires_text="must have combat advantage against the target",
)
def m5318a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m5318a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5318a3(c: Cast) -> None:
    """"If the shift puts it into a flanking position" is a condition on the
    destination, so the squares are tested before the step is taken."""
    _step_into_flank(c)


# --------------------------------------------------------------------------
# m5367
# --------------------------------------------------------------------------


@power(
    "m5367a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5367a0(c: Cast) -> None:
    """"Provoked by its movement" is the narrowing the attack context cannot
    make -- `opportunity` is there and what opened the window is not. Every
    opening this creature gives is a move in practice, so the bonus is laid
    against opportunity attacks and no clause is lost."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 5, on=c.me, until=When.ENCOUNTER, when=_against_opportunity)


@power(
    "m5367a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_difficult(when=)",),
)
def m5367a1(c: Cast) -> None:
    """The waiver works; narrowing it to shifts does not. `Movement.ignores`
    is a set of terrain labels with no room for a condition on *how* the
    creature is moving, so the creature crosses rough ground freely whichever
    way it goes."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5367a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m5367a2(c: Cast) -> None:
    if c.strike():
        if c.charge:
            c.damage("2d8", 4)
        else:
            c.hit()


@power(
    "m5367a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 7),
)
def m5367a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5367a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5367a4(c: Cast) -> None:
    """Two named rows against two named targets, with the move spent in halves
    so "before, during, or after" has somewhere to put each swing."""
    _recharge_when_bloodied(c)
    total = c.speed_of() + 2
    half = max(1, total // 2)
    c.move(half)
    struck: set[int] = set()
    for ref in ("m5367a2", "m5367a3"):
        foe = next((f for f in _adjacent_foes(c) if f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        c.use_power(ref, on=foe)
    rest = total - half
    if rest > 0:
        c.move(rest)


@power(
    "m5367a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, _i_rolled_one, "it makes an attack roll"),
)
def m5367a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m5424
# --------------------------------------------------------------------------


@power(
    "m5424a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m5424a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m5424a1",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
)
def m5424a1(c: Cast) -> None:
    """No damage at all -- the whole hit is the step and the knockdown."""
    if c.strike():
        c.shift(1)
        c.prone()


# --------------------------------------------------------------------------
# m5515
# --------------------------------------------------------------------------


@power(
    "m5515a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5515a0(c: Cast) -> None:
    """A shift *is* a move action, so `Moved.kind_` is the whole of the
    printed condition and no action cost has to be read. `When.EOT` is "until
    the end of her turn" exactly, and it expires on its own."""
    me = c.me

    def quickened(ev: Moved) -> None:
        if ev.actor != me or getattr(ev, "kind_", "") != "shift":
            return
        c.bonus("damage", 0, dice="1d6", on=me, until=When.EOT)

    c.watch(Moved, quickened, until=When.ENCOUNTER, on=me, label=f"{c.ref} momentum")


@power(
    "m5515a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 7),
)
def m5515a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5515a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d4", 7),
)
def m5515a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.shift(2)


@power(
    "m5515a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes a melee attack against it",
    on=Trigger(
        AttackDeclared, both(targets_me, by_melee),
        "an enemy makes a melee attack against it",
    ),
)
def m5515a3(c: Cast) -> None:
    """The Stealth check has no roll to make -- there is no hiding requirement
    in the engine to lower and no skill contest on a board -- so what is
    written is the consequence: wherever the step left her out of sight, she
    is out of sight. `_conceal` hides her from each enemy whose line is
    actually blocked rather than from everyone."""
    _recharge_when_bloodied(c)
    c.shift(c.speed_of())
    _conceal(c)


# --------------------------------------------------------------------------
# m5652
# --------------------------------------------------------------------------


@power(
    "m5652a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5652a0(c: Cast) -> None:
    """The whole printed line is the range at which it can pick a pocket. No
    Thievery check is ever rolled on a board, so the row is complete and
    deliberately inert rather than unwritten."""


@power(
    "m5652a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5652a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5652a2",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5652a2(c: Cast) -> None:
    c.teleport(3)


@power(
    "m5652a3",
    level=4,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature flanked by it",
        flanked=True,
    ),
)
def m5652a3(c: Cast) -> None:
    """No attack roll: the whole row is a trap laid on the target's own next
    turn. `_moved_far` holds both halves for the encounter, because a duration
    that runs out *at* the end of a turn cannot be relied on to outlive the
    end of that turn -- which is the half that has to survive to be read."""
    victim = c.target
    c.effect("watched for a long stride", until=When.EOTNT, on=victim)
    _moved_far(c, victim, 4, lambda: c.prone(on=victim))


@power(
    "m5652a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger="a creature misses it with a melee attack",
    on=Trigger(
        Miss, both(targets_me, by_melee), "a creature misses it with a melee attack"
    ),
)
def m5652a4(c: Cast) -> None:
    """Three clauses and they run in order: the step, the haul, and the free
    swing the victim is owed if it arrived unhurt. "Its movement provokes
    opportunity attacks" is the clause with nothing to say it -- forced
    movement opens no window and `c.pull` has no flag for one -- so the hit
    points are read before and after and the free swing is granted on the
    honest answer rather than on nothing."""
    _recharge_when_bloodied(c)
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    _shift_up_to(c, 3, toward=foe)
    before = c.missing(foe)
    c.pull(99, on=foe)
    if c.missing(foe) <= before:
        c.grant_attack(foe, on=c.me)


# --------------------------------------------------------------------------
# m5824
# --------------------------------------------------------------------------


@power(
    "m5824a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5824a0(c: Cast) -> None:
    """"Until the start of its next turn" is measured against the creature
    carrying the mark, which is this one, so `When.SONT` says it exactly --
    and the choice is remade at the top of every turn whatever happened to the
    last one."""
    me = c.me

    def pick() -> None:
        prey = next((f for f in c.enemies() if c.can_see(f)), None)
        if prey is not None:
            c.quarry(on=prey, until=When.SONT)

    def choose(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            pick()

    pick()
    c.watch(TurnStart, choose, until=When.ENCOUNTER, on=me, label=f"{c.ref} prey")


@power(
    "m5824a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5824a1(c: Cast) -> None:
    """The card names a destination -- the creature ends adjacent -- rather
    than a distance, so the square is picked and `c.slide` aims at it. Lifting
    it off the ground is the same operation here: height is the mount's own and
    the passenger arrives wherever the mount is."""
    me = c.me

    def haul(ev: Moved) -> None:
        if ev.actor != me or c.turn_of() != me:
            return
        for victim in c.grabbing(of=me):
            _hauls_the_grabbed(c, victim)

    c.watch(Moved, haul, until=When.ENCOUNTER, on=me, label=f"{c.ref} carries")


@power(
    "m5824a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m5824a2(c: Cast) -> None:
    if c.strike():
        if c.is_quarry():
            c.damage("2d6", 8)
        else:
            c.hit()
        c.prone()


@power(
    "m5824a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5824a3(c: Cast) -> None:
    _run_and_strike(c, c.speed_of(), ref="m5824a2")


@power(
    "m5824a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1, max_size=Size.MEDIUM, label="its chosen prey"
    ),
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 6, kind=LIMITED),
    dropped=("c.grab(dc=)",),
)
def m5824a4(c: Cast) -> None:
    """`max_size` is a real `Target` field, so the size half of the target line
    is declared rather than gated. The escape DC is the clause with nowhere to
    go: `c.grab` sets the hold and the number is fixed by the creature's own
    maths. The flights are before and after, which is what the Effect says."""
    if c.first:
        _recharge_when_bloodied(c)
    half = max(1, c.speed_of() // 2)
    c.move(half)
    if c.strike():
        c.hit()
        c.grab()
    c.move(half)


@power(
    "m5824a5",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="a dying humanoid",
        kinds=frozenset({"humanoid"}),
    ),
    keywords=[Keyword.HEALING],
    requires=_dying_in_reach,
    requires_text="must have a dying humanoid in reach",
    dropped=("c.kill()",),
)
def m5824a5(c: Cast) -> None:
    """The heal is exact and it works. "The target dies" is the other half and
    nothing says it: a creature is put down by damage, and a blow large enough
    to be sure of it is a different sentence that resistance and temporary hit
    points would both read.

    The type word is the target line now. The gate stays because it asks the
    *dying* half, which is a different clause and not a restatement of this
    one."""
    c.heal(15, on=c.me)


# --------------------------------------------------------------------------
# m5834
# --------------------------------------------------------------------------


@power(
    "m5834a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5834a0(c: Cast) -> None:
    """"The target can't make opportunity attacks" is said from the other end:
    `c.no_provoke(from_=victim, on=mate)` is one creature's immunity to that
    victim's openings, and the whole side put out of its reach is the same
    sentence. Said per creature because the relation names one of each."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    for mate in [c.me, *c.allies()]:
        c.no_provoke(from_=victim, on=mate, until=When.EOTNT)


@power(
    "m5834a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5834a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5834a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5834a2(c: Cast) -> None:
    _run_and_strike(c, c.speed_of(), ref="m5834a0")


# --------------------------------------------------------------------------
# m5854
# --------------------------------------------------------------------------


@power(
    "m5854a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.act_after_charge()",),
)
def m5854a0(c: Cast) -> None:
    """The restriction this waives is in `actions.perform`, which zeroes the
    standard, move and minor slots the moment the charge resolves. Nothing a
    row can do reaches it: the zeroing happens after the charge's own attack
    has run, so a watch that hands the slot back is overwritten a line later.
    An action point is the engine's one printed exception and it already
    works."""


@power(
    "m5854a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5854a1(c: Cast) -> None:
    """"While bloodied" is a window with no `when=` to read it -- speed is not
    asked through an attack context -- so the bonuses are laid when the
    creature crosses the line, and at once if it is already across it."""
    me = c.me

    def arm() -> None:
        c.bonus("speed", 2, on=me, until=When.ENCOUNTER, kind="power")
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 4, on=me, until=When.ENCOUNTER, kind="power",
                when=_against_opportunity,
            )

    if _while_bloodied(c.world, me):
        arm()
        return

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            arm()

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} wrath")


@power(
    "m5854a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m5854a2(c: Cast) -> None:
    if c.strike():
        if c.charge:
            c.damage("3d6", 4)
        else:
            c.hit()


@power(
    "m5854a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m5854a3(c: Cast) -> None:
    """"Recharge if the power misses every target" is the printed sentence on
    top of the die in the header; the two only ever agree to offer the row
    sooner. The helper arms once, so a second target does not restore the use
    twice for one miss."""
    _recharge_on_miss(c)
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m5854a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy ends its move in a square where it flanks it",
    on=Trigger(
        Moved, _enemy_flanked_me,
        "an enemy ends its move in a square where it flanks it",
    ),
)
def m5854a4(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m5938
# --------------------------------------------------------------------------


@power(
    "m5938a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5938a0(c: Cast) -> None:
    _extra_against_advantage(c, "1d6")


@power(
    "m5938a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 7),
)
def m5938a1(c: Cast) -> None:
    """"The target grants combat advantage" with nobody named is the whole
    side, which is `to="team"` -- `to="ally"` would leave this creature out of
    the benefit its own card buys."""
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.EONT)


@power(
    "m5938a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 4, kind=LIMITED),
    requires=_not_grabbing,
    requires_text="must have no creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m5938a2(c: Cast) -> None:
    """"Until the grab ends" is measured by nothing in `When`: a grab ends
    when the relation is cleared, and `RelationCleared` is the only
    announcement of it -- which is what `_until_escape` listens for. The two
    riders share one lifetime, so they are ended together."""
    if c.first:
        c.shift(1)
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab()
    c.shift(1)
    c.pull(2)
    burn = c.ongoing(5, on=victim, until=When.ENCOUNTER)
    _until_escape(c, victim, burn)
    for mate in [c.me, *c.allies()]:
        _until_escape(c, victim, c.no_provoke(
            from_=victim, on=mate, until=When.ENCOUNTER
        ))


@power(
    "m5938a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    requires=_grabbing,
    requires_text="must have a Medium or smaller creature grabbed",
)
def m5938a3(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))
    for victim in c.grabbing(of=c.me):
        if c.size_of(victim) in (Size.TINY, Size.SMALL, Size.MEDIUM):
            _hauls_the_grabbed(c, victim)


# --------------------------------------------------------------------------
# m5991
# --------------------------------------------------------------------------


@power(
    "m5991a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5991a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5991a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5991a1(c: Cast) -> None:
    """Both steps are printed, one either side of the swing; the first is
    guarded by `c.first` so a second target does not buy a second step."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5991a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 9),
)
def m5991a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6398
# --------------------------------------------------------------------------


@power(
    "m6398a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6398a0(c: Cast) -> None:
    """"An odd roll misses, an even one hits and spends the trait" is
    `c.treat_roll_as`, which sets the parity on the result rather than faking
    the die -- `AttackResult.parity` is the only thing that should read either.
    The trait is re-laid at the top of each of its turns, which is the printed
    "until the start of its next turn"."""
    me = c.me

    def veil() -> None:
        c.treat_roll_as("even", on=me, until=When.SONT)

    def again(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            veil()

    veil()
    c.watch(TurnStart, again, until=When.ENCOUNTER, on=me, label=f"{c.ref} blur")


@power(
    "m6398a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6398a1(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6398a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m6398a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6398a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature granting combat advantage to it",
        grants_ca=True,
    ),
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d12", 5),
)
def m6398a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6398a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m6398a4(c: Cast) -> None:
    _run_and_strike(c, max(1, c.speed_of() // 2), times=2, shifting=True)


@power(
    "m6398a5",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISSED_ME,
    on=Trigger(Miss, targets_me, _MISSED_ME),
)
def m6398a5(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m969
# --------------------------------------------------------------------------


@power(
    "m969a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 4),
)
def m969a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m969a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 4, kind=LIMITED),
)
def m969a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m969a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m969a2(c: Cast) -> None:
    """A death throe: no attack roll, every enemy in the ring blinded."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m969a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m969a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee", "ranged"))


@power(
    "m969a4",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m969a4(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.EOT, when=_against_opportunity)
    c.move(4)
    _ends_move_beside(c)


# --------------------------------------------------------------------------
# m970
# --------------------------------------------------------------------------


@power(
    "m970a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 1),
)
def m970a0(c: Cast) -> None:
    """"+11 against a bloodied target" is the printed +10 plus one, passed to
    the roll rather than declared -- the header states the total the card
    prints and the engine takes the level back out of that one number."""
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()


@power(
    "m970a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m970a1(c: Cast) -> None:
    _advantage_rider(c, "2d6", ("melee",))


@power(
    "m970a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes an opportunity attack against it",
    on=Trigger(
        AttackDeclared, both(targets_me, by_opportunity),
        "an enemy makes an opportunity attack against it",
    ),
)
def m970a2(c: Cast) -> None:
    """An interrupt, so the attacker is blinded before it rolls -- which is
    the point of the card and not merely its flavour."""
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    if attacker is not None:
        c.blinded(on=attacker, until=When.SAVE_ENDS)


@power(
    "m970a3",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m970a3(c: Cast) -> None:
    """"An enemy that hit it since its last turn" is a set nothing records, so
    the log is read back to its own turn.

    Asked **at the moment of the swing** rather than when the minor action is
    spent: the window the card names runs from its last turn to its next
    attack, and a set snapshotted now is already wrong if something hits it in
    between. Both modifiers are `once=True` -- the card buys one attack roll,
    and the extra damage rides that same swing.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="power", once=True, when=gate)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, once=True, when=gate)


# --------------------------------------------------------------------------
# m977
# --------------------------------------------------------------------------


@power(
    "m977a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m977a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d4", dtype=DamageType.NECROTIC)


@power(
    "m977a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
    dropped=("etl.monster.attack_defence()",),
)
def m977a1(c: Cast) -> None:
    """The extraction lost the defence this attack rolls against, so the
    row's own swing cannot be made and none is invented. What is left is the
    printed Effect -- fly half its speed, swing the basic attack on the way,
    and give the victim no opening on the way out -- and that works."""
    _mobile_attack(c, max(1, c.speed_of() // 2))


@power(
    "m977a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m977a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m977a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m977a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m977a4",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is damaged by a necrotic attack",
    on=Trigger(DamageApplied, _necrotic_hurt, "it is damaged by a necrotic attack"),
)
def m977a4(c: Cast) -> None:
    c.heal(13, on=c.me)
