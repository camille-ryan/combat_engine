"""Monster abilities, level 4, artillery.

Thirty-eight stat blocks, a hundred and fifty-two rows. `artillery.py` holds
the earlier sweep of this level and is not touched here; the split is by
*when* the work was done rather than by what the creatures are, and the
conventions are the ones the level-1 to level-3 sweeps settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=9)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight -- whatever action the
  compendium's column claims for it;
* a printed range band of "20/40" takes the **normal** range;
* a card that prints no range at all is melee 1;
* a blow of two types rolled once keeps the **first** in the header and
  carries the rest as keywords, which is all one `Damage` can say
  (`dropped=("Damage(dtypes=)",)`); a blow printed as "1d6 + 4 **plus** 1d6
  lightning" is two rolls and needs no marker -- the second is a `c.damage`
  in the body;
* a close burst or blast whose card names no target set takes **enemies**,
  except where the card says "creatures in the burst" outright;
* "N damage (N+1 if it has combat advantage)" keeps the base in the header
  and adds the difference with `c.flat`, so the rescale still has a number
  to read;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a
  minion's flat damage `kind=MINION`.

Twenty helpers are imported rather than written again, from the level-1 to
level-3 sweeps and from `level_08/skirmishers.py`. The eight written here are
the shapes this batch is the first to need: three dragons whose multi-attack
lines name their own rows, a spirit that runs a line and attacks what it
passes through, and two "half damage" clauses that are facts about the
*incoming* blow rather than about a resistance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
    _sure_footed_shift,
    _uncovered,
)
from combat_engine.content.monsters.level_01.skirmishers_sa import _moved_far
from combat_engine.content.monsters.level_02.artillery_sa import (
    ALL_DEFENCES,
    _saves_off_prone,
)
from combat_engine.content.monsters.level_02.controllers_sa import _recharge_on_miss
from combat_engine.content.monsters.level_02.skirmishers_sa import _high_crit
from combat_engine.content.monsters.level_02.soldiers_sa import _missed_me_in_melee
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes import _taking_ongoing
from combat_engine.content.monsters.level_03.brutes_sa import (
    _enemy_closed_on_me,
    _recharge_and_fire,
)
from combat_engine.content.monsters.level_03.controllers_sa import _hold_while_inside
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _vanish_until_it_swings,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _adjacent_foes,
    _armed,
    _per_round_rider,
    _shift_up_to,
    _step_beside,
)
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
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
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
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
    Cover,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
)
from combat_engine.engine.components import Health
from combat_engine.engine.dsl import Range, get
from combat_engine.engine.events import (
    AdjacencyGained,
    AdjacencyLost,
    AttackRolled,
    Bloodied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    MoveEnd,
    PowerUsed,
    SurgeSpent,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    concealment_of,
    cover_between,
    distance_between,
    enemies,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    targets_me,
    would_hit_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _one_then_two(c: Cast, single: str, pair: str) -> None:
    """"It makes a gore attack and two claw attacks."

    The three dragons in this batch each print a multi-attack whose content is
    entirely two named rows, and whose own attack line did not survive
    extraction -- "+9 vs or (whichever is lower);" with no defence and no
    damage. So there is nothing here to roll: the row spends the action and
    the named rows do the work. `c.use_power` rather than `c.basic`, because
    the card names *which* rows and a monster's basic is only one of them.
    """
    first = _adjacent_foe(c, c.ref)
    if first is not None:
        c.use_power(single, on=first)
    for _ in range(2):
        victim = _adjacent_foe(c, c.ref)
        if victim is not None:
            c.use_power(pair, on=victim)


def _two_or_one(c: Cast, pair: str, single: str, *, step: int = 0) -> None:
    """"It makes two claw attacks **or** one bite attack, and then shifts 1."

    The choice is offered rather than decided: `World.decide` takes the head
    of the list when nobody is playing, and two swings is the line a policy
    should default to.
    """
    which = c.choose(["two", "one"], f"{c.ref}: how many swings") or "two"
    for _ in range(2 if which == "two" else 1):
        victim = _adjacent_foe(c, c.ref)
        if victim is not None:
            c.use_power(pair if which == "two" else single, on=victim)
    if step:
        c.shift(step)


def _shoot_on_the_move(c: Cast, ref: str, total: int) -> None:
    """Move, loose one shot at any point along the way, move on.

    The distance is spent in two halves rather than all at once, because "at
    any point during the movement" is what brings a target into range that one
    step to one destination would not. The printed exemption is from the
    *target's* opportunity attack alone, so it is laid against that creature
    and not against the board.
    """
    half = max(1, total // 2)
    c.move(half)
    victim = min(c.enemies(), key=c.distance, default=None)
    if victim is not None:
        c.no_provoke(from_=victim, on=c.me, until=When.EOT)
        c.use_power(ref, on=victim)
    rest = total - half
    if rest > 0:
        c.move(rest)


def _half_from_hand(c: Cast, until: When) -> None:
    """"Takes half damage from melee and ranged attacks until ..."

    Not a resistance: a resistance takes a flat number off every blow of a
    type, and this halves whatever arrives from two particular reaches. The
    reach is on the row that dealt it, which `DamageRolled` names in `detail`
    -- it carries no `power` -- and the window has to be BEFORE or the blow
    has already come off hit points.
    """
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target != me:
            return
        row = get(str(getattr(ev, "detail", "") or ""))
        if row is not None and row.reach_of(0).kind in ("melee", "ranged"):
            c.halve(ev)

    c.watch(
        DamageRolled, soften, until=until, on=me, window=Window.BEFORE,
        label=f"{c.ref} guard",
    )


def _half_when_hidden(c: Cast) -> None:
    """"Takes only half damage from attacks it has cover or concealment from."

    Both halves are askable and neither is a modifier the creature can carry:
    cover is traced between two squares at the moment of the blow, and
    concealment is a modifier on the creature that `concealment_of` reads.
    """
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target != me:
            return
        who = getattr(ev, "source", None)
        if not isinstance(who, int):
            return
        hidden = cover_between(c.world, who, me, ranged=True) is not Cover.NONE
        if hidden or concealment_of(c.world, me) is not Cover.NONE:
            c.halve(ev)

    c.watch(
        DamageRolled, soften, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
        label=f"{c.ref} shelter",
    )


def _caltrops(c: Cast, area: Any, amount: int) -> None:
    """A patch that bites on entry **and** as a turn closes there, and slows.

    `c.hazard` covers entering and starting a turn, which are not the two
    moments this card names, and it damages without laying anything -- so the
    zone is made plainly and both doors are watched here.
    """
    zone = c.zone(area, until=When.ENCOUNTER, label=c.ref, difficult=True)
    me = c.me

    def bite(who: int) -> None:
        if who == me or team(c.world, who) is team(c.world, me):
            return
        c.flat(amount, on=who)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def closed(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(TurnEnd, closed, until=When.ENCOUNTER, on=me, label=f"{c.ref} lingers")


def _spirit_run(c: Cast, within: int, far: int) -> None:
    """A conjuration that appears, runs a line, strikes what it passes through.

    "Each creature whose space it enters" is read off the line it travels
    rather than off a burst: `c.line` is the path and `c.in_squares` is who is
    standing in it. The destination is sorted by how many enemies the path
    crosses, so `World.decide` taking the head of the list picks the run the
    card is for.
    """
    here = c.here
    pool = sorted(
        sq
        for sq in spread({here}, within) - {here}
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not pool:
        return
    start = c.choose(pool, f"{c.ref}: where it appears") or pool[0]
    sphere = c.conjure(start, label=c.ref, until=When.EOT, sustain=None)
    if not sphere:
        return
    ring = [
        sq
        for sq in spread({start}, far) - spread({start}, far - 1)
        if c.world.grid.passable(sq)
    ]
    ring.sort(key=lambda sq: (-len(c.in_squares(c.line(start, sq), side="enemy")), sq))
    dest = (c.choose(ring, f"{c.ref}: where it goes") or ring[0]) if ring else start
    for victim in c.in_squares(c.line(start, dest), side="enemy"):
        if c.strike(on=victim, from_=sphere):
            c.hit(on=victim)
            c.prone(on=victim)
    c.dispel(sphere)


def _hit_me_from_within(reach: int) -> Callable[[World, int, Any], bool]:
    """"An enemy within N squares of it hits it with an attack."

    `enemy_within` reads the event's `actor`, which an attack does not carry
    -- the attacker is in `attacker` -- so the distance is measured here.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or getattr(ev, "target", None) != me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= reach

    return check


def _foe_finished_beside_me(world: World, me: int, ev: MoveEnd) -> bool:
    """"An enemy ends its movement adjacent to it." `MoveEnd` and not
    `MoveStart`: the question is where the creature stopped."""
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "ghost", False):
        return False
    return who in enemies(world, me) and distance_between(world, me, who) <= 1


def _foe_left_my_side(world: World, me: int, ev: AdjacencyLost) -> bool:
    """"An enemy leaves a square adjacent to it." Half the printed sentence --
    see the row's `dropped`: `AdjacencyLost` carries no `mover`."""
    if getattr(ev, "actor", None) != me:
        return False
    other = getattr(ev, "other", None)
    return other is not None and other in enemies(world, me)


def _ally_went_down(world: World, me: int, ev: Dropped) -> bool:
    """"An ally it can see drops to 0 hit points." `query.enemies` filters the
    dead out, so the side is compared with `team` directly."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    return team(world, who) is team(world, me)


def _implement(ref: str) -> bool:
    """Does that row carry the implement keyword? Two traits ask it."""
    row = get(str(ref or ""))
    return row is not None and Keyword.IMPLEMENT in row.keywords


def _has_a_quarry(world: World, eid: int) -> bool:
    """A Requirement that there is a quarry to shoot at.

    `Target` filters on side, count and size and says nothing about a
    relation, so the restriction is asked here as well as in the body:
    without it the row is offered every turn, aimed at whoever is nearest,
    and comes back having done nothing.
    """
    me = Cast(world=world, me=eid, ref="")
    return any(me.is_quarry(on=foe) for foe in enemies(world, eid))


def _has_cursed_somebody(world: World, eid: int) -> bool:
    """The same gate for a curse rather than a quarry."""
    me = Cast(world=world, me=eid, ref="")
    return any(me.cursed(on=foe) for foe in enemies(world, eid))


def _burning_nearby(world: World, eid: int) -> bool:
    """A Requirement that somebody within 10 squares is alight, which is the
    only creature the printed teleport has to swap with."""
    me = Cast(world=world, me=eid, ref="")
    return any(
        _taking_ongoing(me, who, DamageType.FIRE)
        for who in me.within(10, of=eid, side="any")
        if who != eid
    )


def _swing_or_charge(c: Cast, mate: int, ward: int) -> None:
    """"Each ally in the burst can charge or make a basic attack as a free
    action; if it hits, it gains N temporary hit points."

    `c.basic` returns "was it used" and not "did it hit", so the reward is
    armed as a one-shot watch on the ally's own `Hit` before the swing rather
    than read back afterwards.
    """
    def warded(ev: Hit) -> None:
        if getattr(ev, "attacker", None) == mate:
            c.temp_hp(ward, on=mate)

    c.watch(
        Hit, warded, until=When.EOT, on=c.me, once=True, label=f"{c.ref} ward {mate}"
    )
    beside = [foe for foe in c.enemies() if c.adjacent_to(foe, mate)]
    if beside:
        c.basic(who=mate, on=beside[0])
        return
    victim = min(c.enemies(), key=lambda f: distance_between(c.world, mate, f), default=None)
    if victim is not None:
        c.charge_at(victim, who=mate)


# ==========================================================================
# m115788
# ==========================================================================


@power(
    "m115788a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
)
def m115788a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115788a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
)
def m115788a1(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is the whole side, so
    `to="team"` rather than the method's default of the caster alone."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SONT, to="team")


@power(
    "m115788a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
)
def m115788a2(c: Cast) -> None:
    """The card prints "Recharge when first bloodied" where the database files
    a plain 6+; the die stays in the header and the sentence is armed on top.

    The Hit line turns a victim on its own side -- "a creature of the
    creature's choice" is chosen from *its* enemies, which are the victim's
    allies -- and the Effect line is once per use, not once per target.
    """
    if c.first:
        _recharge_when_bloodied(c)
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                _swing_or_charge(c, mate, 5)
    victim = c.target
    if victim is None or not c.strike():
        return
    beside = [foe for foe in c.enemies() if foe != victim and c.adjacent_to(foe, victim)]
    prey = beside[0] if beside else next(
        (foe for foe in c.enemies() if foe != victim), None
    )
    if prey is not None:
        c.grant_attack(victim, on=prey)


@power(
    "m115788a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=EACH_ALLY,
)
def m115788a3(c: Cast) -> None:
    """`EACH_ALLY` includes the caster in the targeting path (#364), which is
    right here -- the card moves the creature too -- so the only branch is
    whose step has a destination named for it. "The allies must end adjacent"
    is a square rather than a distance, which is what `to=` is for."""
    if c.target == c.me:
        c.shift(1)
        return
    mate = c.target
    if mate is None:
        return
    sq = _step_beside(c, mate, c.me)
    if sq is not None:
        c.shift(1, who=mate, to=sq)
    else:
        c.shift(1, who=mate)


# ==========================================================================
# m1431
# ==========================================================================


@power(
    "m1431a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.LIGHTNING),
)
def m1431a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1431a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m1431a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1431a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m1431a2(c: Cast) -> None:
    _one_then_two(c, "m1431a0", "m1431a1")


@power(
    "m1431a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
    no_provoke=True,
)
def m1431a3(c: Cast) -> None:
    """The range line did not survive extraction -- only the roll, the half on
    a miss and "does not provoke opportunity attacks" came through, and the
    last two only ever print on something thrown rather than swung, so it is
    written as a ranged attack. The recharge sentence is the printed one on
    top of the die."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m1431a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, half_on_miss=True),
)
def m1431a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m1495
# ==========================================================================


@power(
    "m1495a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 2),
)
def m1495a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1495a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
)
def m1495a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1495a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 1, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1495a2(c: Cast) -> None:
    """`on=` is *who* is unseen and `to=` is who cannot see them, so the
    caster has to be named on both counts: the default would hide the
    target from itself."""
    if c.strike():
        c.hit()
        c.invisible(to=c.target, on=c.me, until=When.SONT)


@power(
    "m1495a3",
    level=4,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m1495a3(c: Cast) -> None:
    """"Slowed and takes ongoing 5 damage (save ends)" is one hold and one
    saving throw, so the burn rides on the condition rather than beside it --
    laid separately the victim gets two throws and shakes off half of what the
    card calls one thing.

    The requirement the compendium prints names the weapon rather than a
    board state, and the creature is holding it, so there is nothing to gate.
    """
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED)
        )


@power(
    "m1495a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
)
def m1495a4(c: Cast) -> None:
    """"Before or after she attacks" is one step either side of the swing;
    taken first, which is the half that can bring a target into range."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m1495a5",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=Target(
        side="enemy", count=1,
        label="its quarry",
        relation=Relation.QUARRY_OF,
    ),
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m1495a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1495a6",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m1495a6(c: Cast) -> None:
    """Two clauses: naming the quarry, which costs the minor action in the
    header, and the once-a-round rider, which is armed the first time and must
    not be armed twice -- a second copy pays out twice for one sentence."""
    nearest = min(c.enemies(), key=c.distance, default=None)
    if nearest is not None:
        c.quarry(on=nearest)
    if not _armed(c, c.ref):
        _per_round_rider(c, "1d6", lambda ev: c.is_quarry(on=ev.target))


_M1495_MISSED = "an enemy misses it with a melee attack"


@power(
    "m1495a7",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1495_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M1495_MISSED),
)
def m1495a7(c: Cast) -> None:
    """The slide names a destination rather than a distance, so the square is
    picked first and the distance is however far the enemy actually is."""
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    sq = _free_square_beside(c, c.me)
    if sq is not None:
        c.slide(max(1, c.distance(who)), on=who, to=sq)
    c.grants_advantage(on=who, until=When.EONT)


@power(
    "m1495a8",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1495a8(c: Cast) -> None:
    """A bonus to one skill check for creatures within 10 squares, and nothing
    else. Nothing on a board rolls it, so the row is finished and inert."""


# ==========================================================================
# m1509
# ==========================================================================


@power(
    "m1509a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d4", 0),
)
def m1509a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1509a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 5, dtype=DamageType.THUNDER),
)
def m1509a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m1509a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1509a2(c: Cast) -> None:
    """"A separate attack against three different targets" is `UpTo(3)` with
    the body running once per target, which is what rolls three times."""
    if c.strike():
        c.hit()


# ==========================================================================
# m2540
# ==========================================================================


@power(
    "m2540a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 1),
)
def m2540a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2540a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.POISON),
)
def m2540a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2540a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2540a2(c: Cast) -> None:
    """"Save ends both" is one hold carrying the slow and the burn together."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.PSYCHIC)
        )


@power(
    "m2540a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m2540a3(c: Cast) -> None:
    """Two basic attacks, and a step only if the *first* was the melee one and
    it landed. The named rows are used rather than `c.basic`, because
    `c.use_power` leaves its roll in `c.result` and `c.basic` answers only
    "was it used" -- which cannot tell the printed condition."""
    beside = _adjacent_foes(c)
    if beside:
        c.use_power("m2540a0", on=beside[0])
        if c.landed:
            c.shift(1)
    else:
        far = min(c.enemies(), key=c.distance, default=None)
        if far is not None:
            c.use_power("m2540a1", on=far)
    second = min(c.enemies(), key=c.distance, default=None)
    if second is not None:
        c.use_power(
            "m2540a0" if c.adjacent(second) else "m2540a1", on=second
        )


_M2540_HIT = "a melee attack hits it"


@power(
    "m2540a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2540_HIT,
    on=Trigger(Hit, both(targets_me, by_melee), _M2540_HIT),
)
def m2540a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.shift(3)
    _half_from_hand(c, When.SONT)


# ==========================================================================
# m3132
# ==========================================================================


@power(
    "m3132a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m3132a0(c: Cast) -> None:
    """The printed "+9 while bloodied" is the racial trait on `m3132a4`, not a
    second number on this line, so the header holds the plain +8 -- writing 9
    here and arming the trait as well would count it twice."""
    if c.strike():
        c.hit()


@power(
    "m3132a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
    dropped=("etl.monster.secondary_line()",),
)
def m3132a1(c: Cast) -> None:
    """The second attack line -- a separate roll against Fortitude on the
    weapon's first hit, carrying a burn -- arrives in the brief as a reference
    to an item block rather than as a line of this row, and a second printed
    bonus has nowhere in the header to live: `Attack` holds one."""
    if c.strike():
        c.hit()


@power(
    "m3132a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
)
def m3132a2(c: Cast) -> None:
    """The opening is given to the whole side rather than to the shooter --
    the printed sentence is about the creature's allies standing next to the
    target -- so `to="team"`."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m3132a3",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Range("area_burst", 2, 10, alt=CloseBlast(3)),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m3132a3(c: Cast) -> None:
    """"Area burst 2 within 10 **or** close blast 3" is two shapes of one row,
    which is what `Range(alt=)` says -- each is enumerated as its own option,
    so picking one is a decision rather than something fixed at declaration."""
    if c.strike():
        c.hit()


@power(
    "m3132a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3132a4(c: Cast) -> None:
    """The bonus the three attack lines print as their bloodied number. A
    gate rather than a watch armed and disarmed around the half-hit-point
    line, and `kind="racial"` because that is the word the card prints in
    front of "bonus"."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="racial",
        when=lambda _ctx: c.bloodied(on=c.me),
    )


# ==========================================================================
# m3307
# ==========================================================================


@power(
    "m3307a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m3307a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3307a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m3307a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3307a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
    once_per_round=True,
)
def m3307a2(c: Cast) -> None:
    """`c.save` follows `c.target`, which is the printed "the target makes a
    saving throw" -- the ally, not the creature handing out the hit points."""
    c.heal(5)
    c.save()


@power(
    "m3307a3",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m3307a3(c: Cast) -> None:
    """`c.surge` follows the target, because the surge spent is the ally's;
    `bonus=` is the printed "and regains an additional 1d6"."""
    c.surge(bonus=c.roll("1d6"))


@power(
    "m3307a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3307a4(c: Cast) -> None:
    """`opportunity` is a key the attack context carries and `query.defence`
    is handed that same context, so this is a gate rather than a watch armed
    and disarmed around every swing."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


_M3307_HIT = "an attack would hit it"


@power(
    "m3307a5",
    level=4,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3307_HIT,
    on=Trigger(AttackRolled, would_hit_me, _M3307_HIT),
)
def m3307a5(c: Cast) -> None:
    """Declared on `AttackRolled` and not on `Hit`: the die is down and the
    total is known, which is the only window an interrupt can change it in.
    `keep="new"` is the printed "use the new result"."""
    c.reroll_attack(keep="new")


# ==========================================================================
# m3501
# ==========================================================================


@power(
    "m3501a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m3501a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3501a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m3501a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3501a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3501a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m3524
# ==========================================================================


@power(
    "m3524a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m3524a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3524a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
)
def m3524a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


_M3524_DOWN = "it drops to 0 hit points"


@power(
    "m3524a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
    trigger=_M3524_DOWN,
    on=Trigger(Dropped, about_me, _M3524_DOWN),
)
def m3524a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3565
# ==========================================================================


@power(
    "m3565a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 0),
)
def m3565a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3565a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
)
def m3565a1(c: Cast) -> None:
    """"At full normal hit points" is `c.missing() == 0`, asked of the victim
    before the blow lands. The bigger dice replace the header's rather than
    adding to it, which is the one case `c.damage` in the body is for."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.missing(on=victim) == 0:
        c.damage("2d6", 4, dtype=DamageType.NECROTIC)
    else:
        c.hit()


@power(
    "m3565a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(20),
    target=Target(
        side="enemy", count=99, everyone=True,
        label="cursed enemies",
        relation=Relation.CURSED_BY,
    ),
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3565a2(c: Cast) -> None:
    """Cursed **by it** is not cursed, which is why the relation and not a
    condition narrows the burst."""
    if c.strike():
        c.hit()


@power(
    "m3565a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m3565a3(c: Cast) -> None:
    """Two clauses: the curse itself, and a once-a-round rider that must be
    armed exactly once -- a second copy pays out twice for one sentence."""
    loose = [foe for foe in c.enemies() if not c.cursed(on=foe)]
    nearest = min(loose, key=c.distance, default=None)
    if nearest is not None:
        c.curse(on=nearest)
    if not _armed(c, c.ref):
        _per_round_rider(c, "1d6", lambda ev: c.cursed(on=ev.target))


_M3565_DOWN = "it drops to 0 hit points"


@power(
    "m3565a4",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3565_DOWN,
    on=Trigger(Dropped, about_me, _M3565_DOWN),
)
def m3565a4(c: Cast) -> None:
    _death_throe(c)


@power(
    "m3565a5",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3565a5(c: Cast) -> None:
    """Taking on the appearance of another creature of the same size. Nothing
    on a board is decided by what a creature looks like, so the row is
    finished and deliberately inert rather than unwritten."""


# ==========================================================================
# m3571
# ==========================================================================


@power(
    "m3571a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m3571a0(c: Cast) -> None:
    """"1d6 + 4 **plus** 1d6 lightning" is two rolls, not one blow of two
    types, so the second is a `c.damage` and the header keeps the first."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.LIGHTNING)


@power(
    "m3571a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 4),
)
def m3571a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3571a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m3571a2(c: Cast) -> None:
    _one_then_two(c, "m3571a0", "m3571a1")


@power(
    "m3571a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d12", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
    no_provoke=True,
    dropped=("Target.spacing",),
)
def m3571a3(c: Cast) -> None:
    """The printed chain -- the first target within 10 squares of the creature,
    the second within 10 of the first, the third within 10 of the second -- is
    a distance measured *between* the chosen targets, and `Target` measures
    only from the caster. Everything in range is offered instead, which is the
    looser set."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M3571_BLOODIED = "it is first bloodied"


@power(
    "m3571a4",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    trigger=_M3571_BLOODIED,
    on=Trigger(Bloodied, about_me, _M3571_BLOODIED),
)
def m3571a4(c: Cast) -> None:
    _recharge_and_fire(c, "m3571a3")


@power(
    "m3571a5",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
    dropped=("c.aftereffect()",),
)
def m3571a5(c: Cast) -> None:
    """The stun lands; the Aftereffect -- a penalty that arrives when the stun
    is saved off, not beside it -- has nothing to hang on. `Effect.on_end`
    could run it, but "aftereffect" is a named printed concept that eight rows
    now want and one symbol should serve."""
    if c.strike():
        c.stunned(until=When.EONT)


@power(
    "m3571a6",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING, half_on_miss=True),
)
def m3571a6(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3571a7",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("etl.monster.ability_text()",),
)
def m3571a7(c: Cast) -> None:
    """Nothing of this block's text survived extraction -- no range, no
    defence, no damage, no effect line, only the action and the usage. There
    is a ref and a card, so the row exists; there is nothing to write."""


# ==========================================================================
# m4116
# ==========================================================================


@power(
    "m4116a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2),
)
def m4116a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4116a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m4116a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4116a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(15),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m4116a2(c: Cast) -> None:
    """"Attacks against two different targets" is `UpTo(2)` and the body
    running once per target, rather than two calls to the at-will row: this
    way the two rolls are this row's, so a rider reading "when it hits with
    this power" finds the right ref."""
    if c.strike():
        c.hit()


# ==========================================================================
# m4142
# ==========================================================================


@power(
    "m4142a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m4142a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m4142a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 3),
)
def m4142a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4142a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m4142a2(c: Cast) -> None:
    _two_or_one(c, "m4142a1", "m4142a0", step=1)


_M4142_MOVED = "an enemy enters or leaves a square adjacent to it"


@power(
    "m4142a3",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 3),
    trigger=_M4142_MOVED,
    on=(
        Trigger(AdjacencyGained, _enemy_closed_on_me, _M4142_MOVED),
        Trigger(AdjacencyLost, _foe_left_my_side, _M4142_MOVED),
    ),
    dropped=("AdjacencyLost.mover",),
)
def m4142a3(c: Cast) -> None:
    """"Enters **or** leaves" is two events, so both are declared -- half of
    it declared looks finished and fires on one of the two.

    The dropped half is which creature moved. `AdjacencyGained` carries
    `mover` and `AdjacencyLost` does not, so the "leaves" branch also fires
    when the dragon itself walked away, which is not the printed sentence.
    """
    who = getattr(c.trigger, "other", None) or getattr(c.trigger, "mover", None)
    if who is None or who == c.me:
        return
    if c.strike(on=who):
        c.hit(on=who)
        c.prone(on=who)
    c.shift(2)


@power(
    "m4142a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 3, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m4142a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
    else:
        c.hit(half=True)


_M4142_BLOODIED = "it is first bloodied"


@power(
    "m4142a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4142_BLOODIED,
    on=Trigger(Bloodied, about_me, _M4142_BLOODIED),
)
def m4142a5(c: Cast) -> None:
    _recharge_and_fire(c, "m4142a4")


@power(
    "m4142a6",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m4142a6(c: Cast) -> None:
    """The splash is an Effect line and so lands whether the shot hit or
    missed, and it catches allies too -- the card says "each creature"."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    for who in c.within(1, of=victim, side="any"):
        if who not in (victim, c.me):
            c.damage("1d8", dtype=DamageType.FIRE, on=who)


@power(
    "m4142a7",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
    dropped=("c.aftereffect()",),
)
def m4142a7(c: Cast) -> None:
    """The stun lands; the Aftereffect has nothing to hang on -- see
    `m3571a5`, which prints the same two sentences."""
    if c.strike():
        c.stunned(until=When.EONT)


# ==========================================================================
# m4621
# ==========================================================================


@power(
    "m4621a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m4621a0(c: Cast) -> None:
    """"Crit 1d8 + 11" is the maximum of the ordinary line plus one more die.
    `c.damage` maxes its dice on a critical, so the extra one is rolled with
    `c.flat(c.roll(...))` or it comes out at its highest face every time."""
    if c.strike():
        c.hit()
        _high_crit(c, "1d8")


@power(
    "m4621a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m4621a1(c: Cast) -> None:
    """The arc jumps to "one creature within 5 squares of the target", either
    side, so an ally standing near the victim is a legal second."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    near = [w for w in c.within(5, of=victim, side="any") if w not in (victim, c.me)]
    if near:
        c.flat(5, dtype=DamageType.LIGHTNING, on=near[0])


@power(
    "m4621a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m4621a2(c: Cast) -> None:
    _spirit_run(c, 5, 6)


_M4621_BLOODIED = "it is first bloodied"


@power(
    "m4621a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4621_BLOODIED,
    on=Trigger(Bloodied, about_me, _M4621_BLOODIED),
)
def m4621a3(c: Cast) -> None:
    """The exemption is narrowed the way the card narrows it -- only against
    the creatures it was standing next to when the turn opened -- which is a
    set that changes every round, so it is rebuilt at each `TurnStart` and
    laid per creature rather than granted against the board."""
    me = c.me

    def opens(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for foe in c.enemies():
            if c.adjacent(foe):
                c.no_provoke(from_=foe, on=me, until=When.EOT)

    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref} free step")
    _recharge_and_fire(c, "m4621a2")


_M4621_DOWN = "it drops to 0 hit points"


@power(
    "m4621a4",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4621_DOWN,
    on=Trigger(Dropped, about_me, _M4621_DOWN),
)
def m4621a4(c: Cast) -> None:
    _death_throe(c)


# ==========================================================================
# m5080
# ==========================================================================


@power(
    "m5080a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 2),
)
def m5080a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5080a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 5),
)
def m5080a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


# ==========================================================================
# m5088
# ==========================================================================


@power(
    "m5088a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m5088a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5088a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 6),
)
def m5088a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5088a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 6),
)
def m5088a2(c: Cast) -> None:
    """"Creatures in the burst" and not "enemies": the card says so, so the
    creature's own side is in the template too."""
    if c.strike():
        c.hit()


_M5088_DOWN = "it drops to 0 hit points"


@power(
    "m5088a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5088_DOWN,
    on=Trigger(Dropped, about_me, _M5088_DOWN),
)
def m5088a3(c: Cast) -> None:
    """`c.extra_action` drops one action into the budget the turn is already
    spending; `c.extra_turn` is the other thing and hands out a whole slot in
    the initiative order, which is a solo's line rather than this one."""
    c.extra_action(cost=STANDARD, on=c.me)


# ==========================================================================
# m5214
# ==========================================================================


@power(
    "m5214a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5214a0(c: Cast) -> None:
    """Nothing records how far a creature has travelled, so where it opened
    its turn is kept and compared when the turn closes. The payout is gated on
    `ranged`, which the damage context carries."""

    def pay() -> None:
        c.bonus(
            "damage", 0, dice="1d6", on=c.me, until=When.SONT,
            when=lambda ctx: bool(ctx.get("ranged")),
        )

    _moved_far(c, c.me, 4, pay)


@power(
    "m5214a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m5214a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5214a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 7),
)
def m5214a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5214a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5214a3(c: Cast) -> None:
    _shoot_on_the_move(c, "m5214a2", max(1, c.speed_of() // 2))


_M5214_MISSED = "a melee attack misses it"


@power(
    "m5214a4",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5214_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M5214_MISSED),
)
def m5214a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5309
# ==========================================================================


@power(
    "m5309a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5309a0(c: Cast) -> None:
    """`PowerUsed` is announced before the body runs, which is harmless here:
    the toll is about the declaration and not about anything the row does."""
    me = c.me

    def flared(ev: PowerUsed) -> None:
        if ev.actor != me or not _implement(ev.power):
            return
        for foe in c.within(3, of=me, side="enemy"):
            c.flat(2, dtype=DamageType.NECROTIC, on=foe)

    c.watch(PowerUsed, flared, until=When.ENCOUNTER, on=me, label=f"{c.ref} backlash")


@power(
    "m5309a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5309a1(c: Cast) -> None:
    """Both halves are keys the damage context carries -- `advantage`, and
    `power`, which on the damage side is the ref of whatever rolled the blow
    -- so this is a gate rather than a watch."""

    def opening(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("advantage")) and _implement(str(ctx.get("power") or ""))

    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=opening
    )


@power(
    "m5309a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 1),
)
def m5309a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5309a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m5309a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m5309a4",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5309a4(c: Cast) -> None:
    """"Save ends **both**" is one saving throw, so the opening hangs off the
    burn rather than beside it -- laid separately the victim gets two throws
    and shakes off half of what the card calls one thing."""
    if not c.strike():
        return
    c.hit()
    burn = c.ongoing(5, DamageType.NECROTIC, until=When.SAVE_ENDS)
    opening = c.grants_advantage(until=When.SAVE_ENDS, to="team")
    if burn is not None and opening is not None:
        burn.on_end.append(lambda: c.world.effects.end(opening, "the hold ended"))


_M5309_SURGE = "an enemy within 10 squares spends a healing surge"


def _enemy_surged_within(world: World, me: int, ev: SurgeSpent) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "m5309a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M5309_SURGE,
    on=Trigger(SurgeSpent, _enemy_surged_within, _M5309_SURGE),
)
def m5309a5(c: Cast) -> None:
    """The surge's value is the *triggering* creature's, which is a different
    number from the caster's, so it is asked of that creature."""
    who = getattr(c.trigger, "actor", None)
    c.heal(max(1, c.surge_value(of=who) // 2), on=c.me)
    c.restore_use("m5309a4", on=c.me)


# ==========================================================================
# m5382
# ==========================================================================


@power(
    "m5382a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5382a0(c: Cast) -> None:
    """Two holds with one lifetime, so the aura's membership is diffed rather
    than recomputed: entering and leaving the zone are exactly the two moments
    they should arrive and go."""
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    _hold_while_inside(
        c,
        ring,
        lambda who: who in c.enemies(),
        lambda who: [
            c.penalty("attack", 2, on=who, until=When.ENCOUNTER),
            c.penalty("damage", 2, on=who, until=When.ENCOUNTER),
        ],
    )


@power(
    "m5382a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
)
def m5382a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5382a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 5),
)
def m5382a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5382a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m5382a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5382a4",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5382a4(c: Cast) -> None:
    """The flight is lent for the length of the move: the block has no fly
    mode of its own and `c.move(at="fly")` measures the mode."""
    c.mode("fly", 5, until=When.EOT, on=c.me)
    c.move(5, at="fly")


# ==========================================================================
# m5408
# ==========================================================================


@power(
    "m5408a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 4, kind=MINION),
)
def m5408a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5408a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 5, kind=MINION),
)
def m5408a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5408_ALLY_DOWN = "an ally it can see drops to 0 hit points"


@power(
    "m5408a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5408_ALLY_DOWN,
    on=Trigger(Dropped, _ally_went_down, _M5408_ALLY_DOWN),
)
def m5408a2(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5649
# ==========================================================================


@power(
    "m5649a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5649a0(c: Cast) -> None:
    """The reach at which it can make one particular skill check. Nothing on
    a board rolls that check, so the row is finished and inert."""


@power(
    "m5649a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m5649a1(c: Cast) -> None:
    """The card prints "Melee 10", which is a reach and not a range: it
    provokes, it is a melee attack for every rider that asks, and only the
    distance is unusual."""
    if c.strike():
        c.hit()


@power(
    "m5649a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(10),
    target=NO_TARGET,
)
def m5649a2(c: Cast) -> None:
    """The card prints "Recharge when first bloodied" where the database files
    a plain 6+; the die stays in the header and the sentence is armed here."""
    _recharge_when_bloodied(c)
    for _ in range(2):
        victim = min(
            (f for f in c.enemies() if c.distance(f) <= 10), key=c.distance, default=None
        )
        if victim is not None:
            c.use_power("m5649a1", on=victim)


@power(
    "m5649a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5649a3(c: Cast) -> None:
    c.teleport(3)


_M5649_HURT = "a melee attack damages it"


@power(
    "m5649a4",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5649_HURT,
    on=Trigger(Hit, both(targets_me, by_melee), _M5649_HURT),
)
def m5649a4(c: Cast) -> None:
    """Declared on `Hit` rather than on a damage event: `by_melee` reads the
    reach off the row that swung, and only the attack events carry one."""
    c.teleport(3)


# ==========================================================================
# m5659
# ==========================================================================


@power(
    "m5659a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 9),
)
def m5659a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5659a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 9),
)
def m5659a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5659a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m5659a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5659_DOWN = "it drops to 0 hit points"


@power(
    "m5659a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M5659_DOWN,
    on=Trigger(Dropped, about_me, _M5659_DOWN),
)
def m5659a3(c: Cast) -> None:
    """"Each creature adjacent" takes in its own side as well, which is what
    the card says; the burst that follows is the row's own."""
    for who in c.within(1, of=c.me, side="any"):
        if who != c.me:
            c.flat(5, dtype=DamageType.FIRE, on=who)
    c.use_power("m5659a2")


_M5659_CLOSED = "an enemy ends its movement adjacent to it"


@power(
    "m5659a4",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5659_CLOSED,
    on=Trigger(MoveEnd, _foe_finished_beside_me, _M5659_CLOSED),
)
def m5659a4(c: Cast) -> None:
    """The blast "must include the enemy's space", which pins the template to
    the enemy rather than to the creature -- so the area is built around the
    enemy's own squares, which is the one footprint satisfying the sentence
    however far the step took the creature."""
    who = getattr(c.trigger, "actor", None)
    if who is None:
        return
    taken = squares(c.world, who)
    _shift_up_to(c, 2)
    _caltrops(c, spread(taken, 1), 5)


# ==========================================================================
# m5751
# ==========================================================================


@power(
    "m5751a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5751a0(c: Cast) -> None:
    """Who is inside is asked when the turn opens rather than kept as a list:
    the aura moves with the creature, so a membership snapshot goes stale the
    moment either of them walks."""
    ring = c.aura(3, label=c.ref, until=When.ENCOUNTER)
    me = c.me

    def tick(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == me or who not in c.world.zones.occupants(ring):
            return
        if team(c.world, who) is not team(c.world, me):
            return
        if not c.is_kind("drake", on=who) or not c.bloodied(on=who):
            return
        # "If it has at least 1 hit point": `Health.bloodied` is true at
        # zero as well, so the floor has to be asked separately or the aura
        # heals a creature that has already gone down.
        hp = c.world.get(who, Health)
        if hp is not None and hp.hp >= 1:
            c.heal(5, on=who)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} mend")


@power(
    "m5751a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 7),
)
def m5751a1(c: Cast) -> None:
    """The "+1 to hit a bloodied target" is a condition of the swing rather
    than a standing modifier, so it rides on `c.strike(plus=)`."""
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()


@power(
    "m5751a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
    dropped=("Damage(dtypes=)",),
)
def m5751a2(c: Cast) -> None:
    """Fire *and* radiant on one roll, which resistance reads as a unit.
    `c.ongoing` takes `dtypes=` so the burn says both; keeping the blow's
    number in the header where a rescale can find it costs the radiant half
    of its type."""
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()
        c.ongoing(
            5,
            DamageType.FIRE,
            dtypes=(DamageType.FIRE, DamageType.RADIANT),
        )


_M5751_HIT = "an enemy within 10 squares hits it"


@power(
    "m5751a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M5751_HIT,
    on=Trigger(Hit, _hit_me_from_within(10), _M5751_HIT),
)
def m5751a3(c: Cast) -> None:
    who = getattr(c.trigger, "attacker", None)
    if who is not None:
        c.damage("1d6", 5, dtype=DamageType.FIRE, on=who)


_M5751_DOWN = "it drops to 0 hit points"


@power(
    "m5751a4",
    level=4,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5751_DOWN,
    on=Trigger(Dropped, about_me, _M5751_DOWN),
)
def m5751a4(c: Cast) -> None:
    """The exemption is laid against whoever is in reach before the shot goes,
    because an opportunity attack is answered by the creature standing next to
    the shooter and not by the shot's target."""
    for foe in _adjacent_foes(c):
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
    c.use_power("m5751a2")


# ==========================================================================
# m5945
# ==========================================================================


@power(
    "m5945a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5945a0(c: Cast) -> None:
    """`attacker` is a key the attack context carries and the damage context
    does not, which is right: this is a bonus to defences, so it is only ever
    read while an attack is being resolved."""

    def alight(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and _taking_ongoing(c, who, DamageType.FIRE)

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER, when=alight)


@power(
    "m5945a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 5),
)
def m5945a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5945a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
)
def m5945a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5945a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 2, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    dropped=("Damage(dtypes=)",),
)
def m5945a3(c: Cast) -> None:
    """The Miss line pushes as well, which is why the else branch exists --
    `half_on_miss` deals the damage and says nothing about the shove."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
    else:
        c.push(2)


@power(
    "m5945a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_burning_nearby,
    requires_text="a creature within 10 squares must be taking ongoing fire damage",
)
def m5945a4(c: Cast) -> None:
    """`c.swap` and not two teleports: either both move or neither does, which
    is what the printed exchange of places means. Without the Requirement the
    row is offered every turn and comes back having done nothing."""
    alight = [
        who
        for who in c.within(10, of=c.me, side="any")
        if who != c.me and _taking_ongoing(c, who, DamageType.FIRE)
    ]
    if alight:
        c.swap(alight[0])


# ==========================================================================
# m6045
# ==========================================================================


@power(
    "m6045a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m6045a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6045a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    damage=Damage("", 6, dtype=DamageType.ACID),
)
def m6045a1(c: Cast) -> None:
    """The card prints an Effect line and no attack roll, so there is nothing
    to hit: `c.hit()` with no strike above it applies the header's damage."""
    c.hit()


@power(
    "m6045a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6045a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6045a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 7, kind=LIMITED),
)
def m6045a3(c: Cast) -> None:
    """"Dazed and deafened (save ends both)" is one hold carrying two
    conditions, so one throw ends both."""
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, Condition.DEAFENED, until=When.SAVE_ENDS)


# ==========================================================================
# m6411
# ==========================================================================


@power(
    "m6411a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6411a0(c: Cast) -> None:
    _half_when_hidden(c)


@power(
    "m6411a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m6411a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6411a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6411a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6411a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 4, kind=LIMITED),
)
def m6411a3(c: Cast) -> None:
    """"Recharge when the attack misses" is the printed sentence on top of the
    die the database files; the number stays in the header because that is
    what `actions.recharge` rolls and what the card shows."""
    _recharge_on_miss(c)
    if c.strike():
        c.hit()
        c.prone()


_M6411_MISSED = "a melee or ranged attack misses it"


@power(
    "m6411a4",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6411_MISSED,
    on=(
        Trigger(Miss, both(targets_me, by_melee), _M6411_MISSED),
        Trigger(Miss, both(targets_me, by_ranged), _M6411_MISSED),
    ),
)
def m6411a4(c: Cast) -> None:
    """"Melee **or** ranged" is two declarations: `on=` takes a sequence, and
    declaring half of it looks finished and answers half the sentence."""
    c.shift(1)


# ==========================================================================
# m6452
# ==========================================================================


@power(
    "m6452a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 2),
)
def m6452a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6452a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6452a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6452a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4, kind=LIMITED),
    dropped=("Target.spacing",),
)
def m6452a2(c: Cast) -> None:
    """The printed "two different targets **within 5 squares of each other**"
    is a distance measured between the chosen targets, and `Target` measures
    only from the caster."""
    if c.strike():
        c.hit()


@power(
    "m6452a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("etl.monster.ability_text()",),
)
def m6452a3(c: Cast) -> None:
    """"At the start of its turn, if an enemy is in its ..." -- the thing the
    enemy has to be inside arrives in the brief as a bare monster ref, which
    is not an ability of this block and names nothing an author can read. The
    recharge is armed on the loosest reading the sentence can carry, an enemy
    it can see; the narrowing is the dropped half."""
    me = c.me

    def opens(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if any(c.can_see(foe) for foe in c.enemies()):
            c.restore_use("m6452a2", on=me)

    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref} reload")


# ==========================================================================
# m6509
# ==========================================================================


@power(
    "m6509a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m6509a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.LIGHTNING)


@power(
    "m6509a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d4", 4, dtype=DamageType.LIGHTNING),
)
def m6509a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6509a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 6, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6509a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


_M6509_ARCANE = "an arcane attack hits it"


def _arcane_hit(world: World, me: int, ev: Hit) -> bool:
    """The keyword is on the row that swung, not on the event."""
    if getattr(ev, "target", None) != me:
        return False
    row = get(str(getattr(ev, "power", "") or ""))
    return row is not None and Keyword.ARCANE in row.keywords


@power(
    "m6509a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6509_ARCANE,
    on=Trigger(Hit, _arcane_hit, _M6509_ARCANE),
)
def m6509a3(c: Cast) -> None:
    _recharge_and_fire(c, "m6509a2")


# ==========================================================================
# m6561
# ==========================================================================


@power(
    "m6561a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 8),
)
def m6561a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6561a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 5),
)
def m6561a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(5)
        c.prone()


@power(
    "m6561a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=Target(
        "enemy", 99,
        everyone=True,
        label="surprised",
        conditions=frozenset({Condition.SURPRISED}),
    ),
    attack=Attack(vs=WILL, printed=9),
)
def m6561a2(c: Cast) -> None:
    """"Surprised enemies in the burst" is the target line now. The gate came
    out with the body's check: the pool is filtered before the area, so a quiet
    board leaves nothing to aim at and the row is not offered."""
    if c.strike():
        c.unconscious(until=When.SAVE_ENDS)


@power(
    "m6561a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    once_per_round=True,
)
def m6561a3(c: Cast) -> None:
    """"Until the end of its next turn **or** it hits or misses with an
    attack": the veil comes off on the roll rather than on the hit, because
    missing gives it away too."""
    c.end_turn()
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m6581
# ==========================================================================


@power(
    "m6581a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6581a0(c: Cast) -> None:
    """The healing is exact. The suspension -- two damage types that switch it
    off for one turn -- is the clause with nowhere to live: `c.regeneration`
    takes an amount and a bloodied gate and nothing about what stops it."""
    c.regeneration(5, on=c.me)


@power(
    "m6581a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m6581a1(c: Cast) -> None:
    """"Cannot take actions until the start of its next turn" is a stun, and
    the window is measured against the **target's** turn rather than the
    caster's -- `When.SOTNT`, not `SONT`."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.COLD)
        c.stunned(until=When.SOTNT)


@power(
    "m6581a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 6, dtype=DamageType.COLD),
)
def m6581a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6581a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.ZONE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
    dropped=("c.zone(exempt=)",),
)
def m6581a3(c: Cast) -> None:
    """The zone is laid once for the whole use, which is what `c.first` is for.
    The exemption -- creatures with one particular movement mode cross it
    freely -- is the dropped half: `c.zone` takes `difficult` for everybody or
    for nobody."""
    if c.first:
        c.zone(c.area(), difficult=True, until=When.EONT, label=c.ref)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.COLD)
    else:
        c.hit(half=True)


# ==========================================================================
# m818
# ==========================================================================


@power(
    "m818a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m818a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m818a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 5),
)
def m818a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m818a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m818a2(c: Cast) -> None:
    """Nothing records how far a creature has travelled, so where it opened
    its turn is kept and compared when the turn closes. `ranged` is a key the
    attack context carries, which is what narrows the bonus."""

    def pay() -> None:
        c.bonus(
            "attack", 2, on=c.me, until=When.SONT,
            when=lambda ctx: bool(ctx.get("ranged")),
        )

    _moved_far(c, c.me, 4, pay)


_M818_ROLLED = "it makes an attack roll"


@power(
    "m818a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M818_ROLLED,
    on=Trigger(AttackRolled, by_me, _M818_ROLLED),
)
def m818a3(c: Cast) -> None:
    """"It must use the second roll, even if it is lower" is `keep="new"` --
    not "best", which is a different printed sentence on other cards."""
    c.reroll_attack(keep="new")


@power(
    "m818a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m818a4(c: Cast) -> None:
    """The exemption is switched on for the length of the shift and off again
    at the end of it: `Movement.ignores` has no move-kind gate, so a plain
    `c.ignores_difficult()` would let the creature *walk* through rough ground
    for free, which the card does not say."""
    _sure_footed_shift(c)


# ==========================================================================
# m972
# ==========================================================================


@power(
    "m972a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 2),
)
def m972a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m972a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m972a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m972a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m972a2(c: Cast) -> None:
    """Cover is a fact about two positions and both of them move, so it is
    traced at the moment of the blow rather than asked of a modifier. The
    attack and the damage context both carry `ranged` and `target`, which is
    what lets one gate serve both halves of the printed sentence."""

    def clear(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return bool(ctx.get("ranged")) and _uncovered(c, who if isinstance(who, int) else None)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=clear)
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=clear)


@power(
    "m972a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m972a3(c: Cast) -> None:
    """Two clauses, both standing modifiers rather than an action: a shove
    shortened by one square, and a saving throw against being floored. The
    compendium files this as a standard action, and the action is the half
    that is wrong -- there is nothing here to spend, so it is armed once like
    any other trait. The usage the card prints is kept, because `cards.py`
    reads that column and the row has no reason to disagree with it."""
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)
