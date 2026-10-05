"""Monster abilities, level 13: the controllers the stat-block sweep left.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=17)`, `Damage("2d8", 4)` -- and the engine takes the level back out
of the attack and rescales the damage.

The conventions the twelve levels below settled are kept, and they are the
ones that decide most rows here:

* a row the database files under an action heading that is plainly a
  **trait** is `ActionType.NONE`, armed once at the start of the fight;
* a card with no printed range at all is melee 1, and a printed band like
  "5/10" takes the short number;
* a close burst or blast whose card names no target set takes **enemies**;
  one reading "creatures in the blast" is `EACH_OTHER`, because
  `EACH_CREATURE` is side "any" and catches the creature using the power;
* "Target: a creature it has grabbed", "a dazed enemy", "a creature granting
  combat advantage" is the target's own state and not the chooser's
  business -- `Target` filters side, count and size and nothing else, so
  `_restricted_to` redirects and every use is `dropped=("Target.kind",)`;
* a two-type damage line has nowhere to live in the header, since `Damage`
  holds one `dtype`, so it is rolled in the body as one blow of two types
  and marked `dropped=("Damage(dtypes=)",)`;
* an Aftereffect is `dropped=("c.aftereffect()",)`: it is a second hold that
  lands when the first one *ends by a save*, and `on_end` fires for the
  encounter teardown too, so writing it there would pay out on a creature
  that never saved;
* "contracts a disease" is `dropped=("c.contract(ref)",)`, the symbol 38
  rows already wait on;
* "alters its physical form" with no mechanical change is
  `out_of_combat=True`.

Eight readings this file had to settle.

**A grab cap that bans the row that made it.** m1096a0 and m1596a0 each
grab up to two, and m1096's card adds that holding two stops it slamming at
all. The ban is `c.forbid` aimed at this row's own ref and lifted from a
`RelationCleared` watch the moment the count drops back under the cap --
hanging it on one grab's ending would leave it standing when the *other*
prisoner got away.

**"The m5221's victim rises as another of its kind" needs no name.** The
creature summoned is this one, read off `Ident.ref`, so the sentence is
structural and the printed word never has to be looked at.

**An extra saving throw is `Effects.save`, which does not care about
`When`.** m5332a0 saves against daze and stun at both ends of its turn
"including effects that don't normally end on a save", and that reads as the
method it already has: the roll is made and a success ends the hold whatever
duration it was carrying.

**A printed "would end on her current turn, instead ends later" is the
latch.** `Effects._on_turn_end` lets an `EONT` effect through once when
`eff.latch` is set, which is exactly one extra round. m6276a6 sets it at the
top of her turn, which is the only moment the engine can see which of her
effects are about to run out.

**A secondary attack line has no ref to live in**, so its printed total goes
through `_secondary`, which takes the level term back out the way the
header's `Attack(printed=)` does.

**Two cards are printed twice.** m115753 and m6141 carry the same three
rows, and m1176 carries m166's five; each is written out rather than
aliased, because a row is identified by its ref and `audit.py` fires it by
ref. Where such a card cross-references another block's id the row every
sentence plainly means is this creature's own, which is how the twelve
levels below read the same slip.

**Falling exists now.** `c.fall` and `c.height` are both real, so
m115753a1's "if the target is flying, it falls" is written rather than
noted -- the level-13 controller file's docstring still says there is no
falling and no height, and that sentence is stale.

**One brief printed no Trigger line at all.** m2327a3 is filed as an
immediate reaction with an encounter usage and an acid blast, and the
sentence that would say when it fires is simply absent. It is declared on
being hit, which is the only shape a close blast reaction can have, and the
gap is in the report.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import (
    _grabbing as _holding_someone,
)
from combat_engine.content.monsters.level_03.skirmishers import (
    _is_bloodied,
)
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_06.controllers import _killer_of
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.skirmishers import (
    _beside_a_great_plant,
    _free_square_within,
    _great_plants,
)
from combat_engine.content.monsters.level_11.controllers import (
    EVERY_DEFENCE,
    _ends_its_turn_in,
    _held_and_softened,
    _softened,
)
from combat_engine.content.monsters.level_13.controllers import _reach_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    ActionPointSpent,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Event,
    ForcedMove,
    Hit,
    Ident,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Moved,
    MoveEnd,
    Position,
    Powers,
    Ranged,
    Relation,
    RelationCleared,
    Size,
    SurgeSpent,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    hits_me,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    distance_between,
    has_combat_advantage,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, by_ranged
from combat_engine.engine.zones import Zone

#: The sizes m1096a0 may slide or grab: its card says Large or smaller, and
#: `Size` is ordered the way the book orders it.
_LARGE_OR_SMALLER = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE)

#: What m5332a0 shakes off at both ends of its turn.
_HELD_FAST = (Condition.DAZED, Condition.STUNNED)

#: The damage types m5332a5 answers.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _cap_grabs(c: Cast, cap: int) -> None:
    """Hold no more than `cap` creatures, and ban this row while it is full.

    Two cards here print a grab limit and one of them adds that reaching the
    limit stops the creature slamming at all. The ban is aimed at this row's
    own ref and lifted from a `RelationCleared` watch, because the printed
    sentence is "until it releases **at least one**" -- hanging the release
    on one prisoner's hold would leave the ban standing when the other got
    away.
    """
    me, ref = c.me, c.ref
    if len(c.grabbing(of=me)) < cap:
        return
    ban = c.forbid(ref, on=me, until=When.ENCOUNTER)
    if ban is None:
        return

    def released(ev: RelationCleared) -> None:
        if (
            ev.kind_ is Relation.GRABBED_BY
            and ev.source == me
            and not ban.ended
            and len(c.grabbing(of=me)) < cap
        ):
            c.world.effects.end(ban, "it let one go")

    watch = c.watch(
        RelationCleared, released, until=When.ENCOUNTER, on=me, label=f"{ref} cap"
    )
    ban.on_end.append(lambda: c.world.effects.end(watch, "the ban lifted"))


def _bar_rows(c: Cast, victim: int, hold: Effect | None, test: Any) -> None:
    """Take every row matching `test` away from a creature under one hold.

    There is no switch for a usage class or for a keyword, so the victim's
    rows are walked and each qualifying one is forbidden by name. Every one
    of those holds is ended when the printed sentence's *single* saving throw
    ends, which is what keeps the clause on one save instead of a dozen.
    """
    known = c.world.get(victim, Powers)
    if known is None or hold is None:
        return
    barred = []
    for ref in known.all:
        p = get(ref)
        if p is not None and test(p):
            taken = c.forbid(ref, on=victim, until=When.ENCOUNTER)
            if taken is not None:
                barred.append(taken)

    def give_back() -> None:
        for eff in barred:
            if not eff.ended:
                c.world.effects.end(eff, "the hold ended")

    hold.on_end.append(give_back)


def _is_limited_attack(p: Any) -> bool:
    """A daily or encounter attack power, which is what the silence names."""
    return p.attack is not None and p.usage is not Usage.AT_WILL


def _is_gear_power(p: Any) -> bool:
    """A weapon or implement power, which is what the illusion takes away."""
    return Keyword.WEAPON in p.keywords or Keyword.IMPLEMENT in p.keywords


def _dark_cloud(c: Cast, *, until: When) -> int:
    """A cloud nobody sees through and nobody inside sees out of.

    `blocks_sight` is what `cover_between` reads and it applies to everybody;
    the caster's own exemption has no primitive, which is the
    `c.zone(exempt=)` gap. The blinding is held per occupant and diffed by
    the two events that say who is standing in it, because a zone's fields
    make squares rough or dark and carry no conditions.
    """
    from combat_engine.engine.events import ZoneEntered, ZoneExited

    me = c.me
    area = c.area() or {c.here}
    dark = c.zone(area, label=c.ref, until=until, blocks_sight=True)
    held: dict[int, Effect] = {}

    def swallow(who: int) -> None:
        if who == me or who in held:
            return
        blinded = c.blinded(until=When.ENCOUNTER, on=who)
        if blinded is not None:
            held[who] = blinded

    for standing in c.world.zones.occupants(dark):
        swallow(standing)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == dark:
            swallow(ev.actor)

    def left(ev: ZoneExited) -> None:
        blinded = held.pop(ev.actor, None) if ev.zone == dark else None
        if blinded is not None:
            c.world.effects.end(blinded, "out of the dark")

    watches = (
        c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in"),
        c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out"),
    )
    live = c.world.get(dark, Zone)
    if live is not None and live.effect is not None:
        for watch in watches:
            live.effect.on_end.append(
                lambda w=watch: c.world.effects.end(w, "the dark is gone")
            )
    return dark


def _foe_in_reach(
    c: Cast, span: int, *, apart_from: set[int] | None = None
) -> int | None:
    """Somebody to swing at, for a row that attacks more than once."""
    skip = apart_from or set()
    near = sorted(
        foe for foe in c.enemies() if foe not in skip and c.distance(foe) <= span
    )
    return c.choose(near, f"{c.ref}: which enemy") if near else None


def _grant_melee_basic(c: Cast, mate: int, *, at: int | None = None) -> bool:
    """"An ally makes a melee basic attack against an enemy within reach."

    The enemy is picked from what *that* creature could actually reach: a
    granted swing across the room is not a swing at all. `on=` is named
    every time, because `c.basic` and `c.grant_attack` both aim at the
    row's own target otherwise.
    """
    if at is not None:
        return c.grant_attack(mate, on=at)
    span = _reach_of(c, mate)
    prey = sorted(
        foe for foe in c.enemies() if distance_between(c.world, mate, foe) <= span
    )
    if not prey:
        return False
    return c.grant_attack(mate, on=c.choose(prey, f"{c.ref}: who it swings at"))


def _meditative(c: Cast, *, resist: int, then: Any) -> None:
    """A stance that armours the creature and pays its allies, until it moves.

    Two blocks print the same shape. `c.stance` is what displaces whatever it
    was in before; the resistance and the payout share the stance's clock,
    and a `Moved` of the creature's own ends all of it, which is the printed
    "if it moves, the effect ends".
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    armour = c.resist(resist, until=When.EONT, on=me)
    extra = then(stance)

    def broke(ev: Moved) -> None:
        if ev.actor != me:
            return
        for eff in (stance, armour, extra):
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "it moved")

    watch = c.watch(Moved, broke, until=When.EONT, on=me, label=f"{c.ref} broken")
    stance.on_end.append(lambda: c.world.effects.end(watch, "the stance is over"))


def _enemy_ends_turn_within(radius: int) -> Any:
    """"An enemy ends its turn within N squares of it."""

    def check(world: World, me: int, ev: Event) -> bool:
        from combat_engine.engine.query import enemies

        who = getattr(ev, "actor", None)
        return (
            who is not None
            and not getattr(ev, "ghost", False)
            and who in enemies(world, me)
            and distance_between(world, me, who) <= radius
        )

    return check


def _anyone_moves_within(radius: int) -> Any:
    """"A creature moves or shifts within N squares of it."

    Neither `ally_within` nor `enemy_within` will say it -- each rules out
    half the board and the printed line reads "a creature". Asked on
    `MoveEnd`, where the creature has arrived: on `MoveStart` nothing has
    moved yet and the distance would be measured from where it set off.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", None)
        return (
            who is not None
            and who != me
            and getattr(ev, "kind_", "") in ("walk", "shift")
            and distance_between(world, me, who) <= radius
        )

    return check


def _has_a_hold_about_to_go(world: World, eid: int) -> bool:
    """Is one of this creature's own effects going to run out on its turn?

    Asked as a Requirement rather than in the body: the row is a once-an-
    encounter free action, and offering it on the first turn of the fight --
    when the creature has laid nothing yet -- would spend it on nothing. A
    trigger's `requires` is re-read every time the trigger fires, so a false
    answer now costs nothing later.
    """
    return any(
        eff.source == eid
        and eff.clock == eid
        and eff.when in (When.EOT, When.EONT)
        and not eff.latch
        for eff in world.effects.live.values()
    )


def _enemy_moves_adjacent(world: World, me: int, ev: Event) -> bool:
    """"An enemy moves adjacent to it." Asked on `MoveEnd`, where the
    creature has arrived -- on `MoveStart` nothing has happened yet."""
    from combat_engine.engine.query import enemies

    who = getattr(ev, "actor", None)
    return (
        who is not None
        and who in enemies(world, me)
        and distance_between(world, me, who) <= 1
    )


def _my_ally_was_killed(world: World, me: int, ev: Event) -> bool:
    """"An enemy kills one of its allies in its line of sight."

    `query.enemies` filters out the dead, so the fallen creature cannot be
    looked for there; its team is compared directly.
    """
    from combat_engine.engine.query import team

    fallen = getattr(ev, "actor", None)
    if fallen is None or fallen == me:
        return False
    return team(world, fallen) == team(world, me)


def _summon_square(c: Cast, where: Any) -> Any:
    """The square a spawn comes up in: where it died, or the nearest free
    one, which is the printed fallback."""
    if c.world.grid.passable(where) and c.world.grid.occupant(where) is None:
        return where
    for sq in sorted(spread({where}, 2) - {where}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _felled_by(c: Cast, types: tuple[DamageType, ...]) -> bool:
    """Was the blow that put this creature down of one of these types?

    `Dropped` says who struck and not what with, so the type comes off the
    `DamageApplied` immediately before it -- the same arrangement
    `c.revives_unless` needs, and the only record there is.
    """
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, DamageApplied) and ev.target == c.me and ev.amount > 0:
            return ev.dtype in types or any(d in types for d in getattr(ev, "dtypes", ()))
    return False


def _stat_block(c: Cast) -> str:
    """This creature's own ref, for a row that puts another of its kind on
    the board. Read off `Ident`, so the printed word is never involved."""
    tag = c.world.get(c.me, Ident)
    return tag.ref if tag is not None else ""


# ==========================================================================
# m1096
# ==========================================================================


@power(
    "m1096a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 5),
)
def m1096a0(c: Cast) -> None:
    """Either a shove or a hold, at its option, and only on something it can
    pick up.

    The size restriction is on the rider and not on the attack: it can slam
    a Huge creature and simply cannot move or hold one, so the test is in
    the body rather than `Target(max_size=)`. The escape penalty is a
    modifier on the victim's check, which is where `escape.attempt` reads
    its bonuses from. Holding the second prisoner bans this row until one is
    let go -- see `_cap_grabs`.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None or c.size_of(on=victim) not in _LARGE_OR_SMALLER:
        return
    if len(c.grabbing()) >= 2 or not c.may("hold it instead of shoving it"):
        c.slide(1, on=victim)
        return
    c.grab(on=victim)
    c.penalty("escape", 4, on=victim, until=When.ENCOUNTER)
    _cap_grabs(c, 2)


@power(
    "m1096a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1096a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: how far the creature
    threatens is a standing fact about it, not something it spends a turn
    on."""
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m1148
# ==========================================================================


@power(
    "m1148a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 3),
)
def m1148a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1148a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=17),
)
def m1148a1(c: Cast) -> None:
    """Two targets measured in a chain: the first off the caster, the second
    off the first.

    The header's `Ranged(10)` is the first half and the chain is the second,
    which no `Target` field says -- so the second target is checked against
    the first in the body and dropped if it is too far. No damage is printed
    on the hit line, so there is no `damage=` and no `c.hit()`: the burn is
    the whole consequence.
    """
    victim = c.target
    if victim is None:
        return
    first = c.targets[0] if c.targets else None
    if (
        not c.first
        and first is not None
        and distance_between(c.world, first, victim) > 5
    ):
        return
    if c.strike():
        c.ongoing(10, DamageType.NECROTIC)


@power(
    "m1148a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1148a2(c: Cast) -> None:
    """The blast and the silence are one printed sentence and one saving
    throw, so the rows taken away are all ended by the hold that carries
    the save."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} silence"
    )
    _bar_rows(c, victim, hold, _is_limited_attack)


@power(
    "m1148a3",
    level=13,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m1148a3(c: Cast) -> None:
    """`c.resist` is the caster's, so it needs no `on=`; the printed clock is
    the end of its own next turn."""
    c.resist(10, until=When.EONT)


@power(
    "m1148a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def m1148a4(c: Cast) -> None:
    """Declared with no target: the dispatcher aims a row at an enemy and
    this one is about allies. Each one swings at something *it* can reach,
    which is what "within reach" measures."""
    for mate in sorted(mate for mate in c.allies() if c.distance(mate) <= 5):
        _grant_melee_basic(c, mate)


# ==========================================================================
# m115753
# ==========================================================================


@power(
    "m115753a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 10),
)
def m115753a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m115753a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m115753a1(c: Cast) -> None:
    """Three clauses on one hit: a hold, a fall, and a payout to whichever
    ally lands the next blow.

    The payout is watched rather than handed out now, because the printed
    line pays the *first* ally to hit while the stun is standing -- so the
    watch is torn down with the stun and spends itself on the first match.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    stun = c.stunned(until=When.SAVE_ENDS, on=victim)
    if c.height(on=victim) > 0:
        c.fall(on=victim)
    if stun is None:
        return
    me, paid = c.me, [False]

    def reward(ev: Hit) -> None:
        if paid[0] or ev.target != victim or stun.ended:
            return
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        paid[0] = True
        c.heal(15, on=ev.attacker)

    watch = c.watch(Hit, reward, until=When.ENCOUNTER, on=me, label=f"{c.ref} bounty")
    stun.on_end.append(lambda: c.world.effects.end(watch, "the hold broke"))


@power(
    "m115753a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d10", 4, kind=LIMITED),
)
def m115753a2(c: Cast) -> None:
    """The Effect line lands whether the blow did or not, which is why the
    prone is outside the hit branch; the allies' free action is spent once
    for the whole blast and each of them swings at something it can reach."""
    if c.strike():
        c.hit()
        c.push(2)
    c.prone()
    if not c.first:
        return
    for mate in sorted(c.in_squares(c.area(), side="ally")):
        if mate == c.me:
            continue
        c.shift(3, who=mate)
        _grant_melee_basic(c, mate)


# ==========================================================================
# m115832
# ==========================================================================

_M115832_GAZE = "an enemy ends its turn within 2 squares of it"


@power(
    "m115832a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6, dtype=DamageType.POISON),
)
def m115832a0(c: Cast) -> None:
    """A penalty to saving throws is the `"save"` modifier, which is what
    `Effects.save` adds in before it compares against 10."""
    if c.strike():
        c.hit()
        c.penalty("save", 2, until=When.EONT)


@power(
    "m115832a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d6", 6, dtype=DamageType.PSYCHIC),
)
def m115832a1(c: Cast) -> None:
    """A compulsion priced in damage: close the distance or pay.

    The distance is measured now and asked again as the victim's turn
    closes, which is the only moment "must end its next turn 2 squares
    closer" can be judged. Adjacency satisfies it outright, as printed, and
    the watch spends itself either way so a second use does not inherit it.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    was = c.distance(victim)

    def judge(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        now = distance_between(c.world, me, victim)
        if now > 1 and now > was - 2:
            c.damage("3d6", dtype=DamageType.PSYCHIC, on=victim, detail=c.ref)

    c.watch(
        TurnEnd, judge, until=When.EOTNT, on=victim, label=f"{c.ref} compulsion",
        once=True,
    )


@power(
    "m115832a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=16),
)
def m115832a2(c: Cast) -> None:
    """No damage is printed, so there is no `damage=` and no `c.hit()`: what
    the hit does is take the victim's gear powers away for one saving
    throw."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.world.effects.apply(victim, c.me, When.SAVE_ENDS, label=f"{c.ref} snakes")
    _bar_rows(c, victim, hold, _is_gear_power)


@power(
    "m115832a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=16),
    trigger=_M115832_GAZE,
    on=Trigger(TurnEnd, _enemy_ends_turn_within(2), _M115832_GAZE),
)
def m115832a3(c: Cast) -> None:
    """The gaze, and a third failed save that stops being a fight.

    `escalate` runs on **every** failed save, so the count is kept in the
    closure and only the third one does anything. What it does is end the
    save-ends hold and lay a petrification on the encounter's clock: the
    printed ways out are a ritual, a kiss and a killing, none of which is
    something a board does, so the stone stays and the outs are noted rather
    than invented.
    """
    victim = getattr(c.trigger, "actor", None)
    if victim is None or not c.strike(on=victim):
        return
    failures = [0]

    def worsen(eff: Effect) -> None:
        failures[0] += 1
        if failures[0] < 3:
            return
        c.world.effects.end(eff, "the third failure")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)
        c.note(f"{c.ref}: the stone lifts only outside a fight")

    c.condition(
        Condition.PETRIFIED, until=When.SAVE_ENDS, on=victim, escalate=worsen
    )


# ==========================================================================
# m1169
# ==========================================================================


@power(
    "m1169a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 6),
)
def m1169a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1169a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.COLD),
)
def m1169a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.COLD)


@power(
    "m1169a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=17),
)
def m1169a2(c: Cast) -> None:
    """No damage at all: the five squares are the whole of the hit line."""
    if c.strike():
        c.slide(5)


@power(
    "m1169a3",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m1169a3(c: Cast) -> None:
    """One call, not two: `c.surge` spends the target's surge and `bonus`
    is the printed "and regain an additional 2d6", so the extra arrives as
    part of the same heal rather than as a second one."""
    if c.may("spend a healing surge"):
        c.surge(bonus=c.roll("2d6"))


@power(
    "m1169a4",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1169a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1176 -- the same card as m166, printed twice. Its own refs, so its own
# rows: `audit.py` fires a row by ref and an alias has none.
# ==========================================================================


@power(
    "m1176a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 3),
)
def m1176a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1176a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d6", 4),
)
def m1176a1(c: Cast) -> None:
    """The cage, which holds and bleeds under one saving throw.

    "Save ends both" is one effect carrying the hold and the burn; applied
    separately the victim would get two throws against a thing the card says
    it saves against once. The cage itself has hit points and gives cover,
    and there is no destructible terrain -- `c.zone` has no hit points and a
    conjuration cannot be attacked -- so both are noted rather than
    invented.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    _held_and_softened(
        c, victim, conditions=(Condition.RESTRAINED,), ongoing=(5, DamageType.UNTYPED)
    )
    c.note(f"{c.ref}: the cage gives cover and can be cut down (25 hit points, resist 10)")


@power(
    "m1176a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1176a2(c: Cast) -> None:
    """Narrative only: the whole printed Effect is a disguise and a skill
    check against a skill check, and the engine has neither."""
    c.note(f"{c.ref}: it looks like some Medium humanoid; an Insight check beats its Bluff")


@power(
    "m1176a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1176a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: whoever holds it pays
    for it every turn they go on holding it. The relation runs from the
    grabber to the grabbed, and it is read as the turn begins because a grab
    can end between one turn and the next."""
    me = c.me

    def thorns(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if me in c.world.relations.targets(Relation.GRABBED_BY, ev.actor):
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, thorns, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m1176a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_beside_a_great_plant,
    requires_text="it must begin and end adjacent to a Large or larger plant",
)
def m1176a4(c: Cast) -> None:
    """Eight squares, and it has to come out beside another great plant.

    A tree is scenery, which the grid does not hold; a plant creature is what
    remains of the printed list, which is the reading m165a2 settled on four
    levels down. The destinations are gathered by hand: `c.teleport` with no
    `to` offers every square in range, and the printed line says where the
    jump has to end.
    """
    me = c.me
    beside = sorted(
        {
            sq
            for plant in _great_plants(c.world, me)
            for sq in _free_square_within(c, plant, 1)
            if c.distance(plant) <= 8
        }
    )
    if not beside:
        return
    where = c.world.decide(me, "teleport", beside, f"{c.ref}: which plant it steps to")
    c.teleport(8, to=where)


# ==========================================================================
# m1427
# ==========================================================================

_M1427_BLOODIED = "it is first bloodied"


@power(
    "m1427a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 3),
)
def m1427a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.PSYCHIC)


@power(
    "m1427a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 3),
)
def m1427a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1427a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m1427a2(c: Cast) -> None:
    """Two claws, which may fall on two creatures: the printed line caps
    nothing, so each swing picks its own target from what is in reach and the
    damage line stays in m1427a1 rather than being copied."""
    for _ in range(2):
        prey = _foe_in_reach(c, 2)
        if prey is None:
            return
        c.use_power("m1427a1", on=prey, spend=False)


@power(
    "m1427a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 7, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m1427a3(c: Cast) -> None:
    """The breath, and a shove paid out on every failed save.

    "Save ends both" is one effect carrying the daze and the burn, so there
    is one throw against one printed sentence -- and `escalate` runs on each
    failure, which is exactly what "each time the target fails the saving
    throw" asks for. The miss line is written out: `half_on_miss=True` is
    declared data and no line of the engine reads it.
    """
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    victim = c.target
    if victim is None:
        return

    def shove(eff: Effect) -> None:
        c.slide(3, on=eff.owner)

    c.condition(
        Condition.DAZED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.PSYCHIC),
        escalate=shove,
    )


@power(
    "m1427a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M1427_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1427_BLOODIED),
)
def m1427a4(c: Cast) -> None:
    """`c.restore_use` hands the breath back and `c.use_power` spends it
    again at once, which is the whole of the printed line."""
    c.restore_use("m1427a3")
    c.use_power("m1427a3")


@power(
    "m1427a5",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=Target(side="enemy", count=1, label="stunned or dazed"),
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=17),
    dropped=("Target.kind",),
)
def m1427a5(c: Cast) -> None:
    """Only on something already reeling, and only one at a time.

    The target restriction is the creature's own state, which `Target`
    cannot filter on, so the chooser's answer is redirected rather than
    thrown away. "On only one creature at a time" is the previous hold being
    ended before the new one lands -- two would be two dominations.
    """
    victim = _restricted_to(
        c,
        10,
        lambda f: c.is_(Condition.STUNNED, on=f) or c.is_(Condition.DAZED, on=f),
    )
    if victim is None or not c.strike(on=victim):
        return
    for eff in list(c.world.effects.live.values()):
        if eff.label.startswith(c.ref) and Condition.DOMINATED in eff.conditions:
            c.world.effects.end(eff, "it looked elsewhere")
    c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


@power(
    "m1427a6",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=17),
    dropped=("c.aftereffect()",),
)
def m1427a6(c: Cast) -> None:
    """No damage is printed, so there is no `damage=` and no `c.hit()`: the
    stun is the whole consequence. The Aftereffect is dropped -- it is a hold
    that lands when the first one ends **by a save**, and `on_end` fires for
    the encounter teardown too."""
    if c.strike():
        c.stunned(until=When.EONT)


@power(
    "m1427a7",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1427a7(c: Cast) -> None:
    """Until the end of its turn, which is `When.EOT` and not `EONT`."""
    c.phasing(until=When.EOT, on=c.me)


@power(
    "m1427a8",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1427a8(c: Cast) -> None:
    """Sunlight is a property of the fight rather than of anybody in it,
    which is what `c.terrain` asks -- and it is asked at both ends of each of
    its turns rather than now, because a fight can move into the open.

    "Only a single standard action" is the budget itself: the move and the
    minor are taken and the standard is left, which is the opposite of the
    level-5 row that leaves only the move.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = 1
            budget.move = 0
            budget.minor = 0
        c.note(f"{c.ref}: sunlight leaves it a single standard action")

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        c.flat(160, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} dawn")
    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label=f"{c.ref} dusk")


# ==========================================================================
# m1570
# ==========================================================================

_M1570_BLOODIED = "it is first bloodied"
_M1570_HURT = "it is damaged by an attack"


@power(
    "m1570a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d10", 7, dtype=DamageType.NECROTIC),
)
def m1570a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1570a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=17),
)
def m1570a1(c: Cast) -> None:
    """One creature's blindness rather than a general veil, so `to=` names
    it. "If it uses this against a new target the previous one is no longer
    affected" is the old veil being ended, which is also what keeps a second
    use from stacking two listeners on the same creature."""
    victim = c.target
    if victim is None or not c.strike():
        return
    for eff in list(c.world.effects.live.values()):
        if eff.label.startswith(c.ref) and eff.source == c.me:
            c.world.effects.end(eff, "it turned to somebody else")
    c.invisible(to=victim, on=c.me, until=When.SONT)


@power(
    "m1570a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=17),
    dropped=("Damage(dtypes=)",),
)
def m1570a2(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two
    types, which is what resistance reads as a unit. An area burst with no
    printed target set catches everybody standing in it."""
    if c.strike():
        c.damage(
            "2d8", 7,
            dtypes=(DamageType.FIRE, DamageType.NECROTIC),
            detail=c.ref,
        )


@power(
    "m1570a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC),
)
def m1570a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1570a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1570a4(c: Cast) -> None:
    """Two named rows at this row's action cost. `spend=False` because
    neither of them is being used up on its own account -- this row is what
    was spent."""
    c.use_power("m1570a2", spend=False)
    c.use_power("m1570a3", spend=False)


@power(
    "m1570a5",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("1d10", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1570a5(c: Cast) -> None:
    """It blinks away and can drag the burst into the hole it left.

    The squares it occupied are read **before** the jump -- afterwards they
    are simply where it is not -- and the prisoners are teleported into them
    one at a time, each offered only squares its own footprint fits. A Huge
    creature's old space will hold anything, which is why this is the one
    direction that always works.
    """
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    if not c.last:
        return
    caught = [who for who in c.targets if who is not None]
    was = sorted(squares(c.world, c.me))
    if not c.teleport(10):
        return
    for who in caught:
        free = [sq for sq in was if c.world.grid.occupant(sq) is None]
        landing = [sq for sq in free if sq in _free_square_within(c, c.me, 20, mover=who)]
        if not landing:
            continue
        c.teleport(20, who=who, to=landing[0])


@power(
    "m1570a6",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger=_M1570_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1570_BLOODIED),
)
def m1570a6(c: Cast) -> None:
    c.teleport(10)
    c.invisible(on=c.me, until=When.EONT)


@power(
    "m1570a7",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.NECROTIC],
    trigger=_M1570_HURT,
    on=Trigger(DamageApplied, targets_me, _M1570_HURT),
)
def m1570a7(c: Cast) -> None:
    """"The triggering attacker" is read off the event rather than off
    `c.targets`: this row is declared `NO_TARGET` and `DamageApplied` names
    who dealt it in `source`, which is also how a burn tick is told from a
    swing."""
    ev = c.trigger
    if ev is None or not getattr(ev, "from_attack", True):
        return
    attacker = getattr(ev, "source", None)
    if attacker is None or attacker == c.me:
        return
    c.teleport(3, who=attacker)
    c.ongoing(5, DamageType.NECROTIC, on=attacker)


# ==========================================================================
# m1596
# ==========================================================================

_M1596_STRUCK = "it is struck by a melee attack"
_M1596_FELLED = "it is reduced to 0 hit points"


@power(
    "m1596a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5),
)
def m1596a0(c: Cast) -> None:
    """The cap is two, and no escape DC is printed, so the grab takes no
    marker -- `c.grab` is the whole of "grabbed (until escape)"."""
    if not c.strike():
        return
    c.hit()
    if len(c.grabbing()) < 2:
        c.grab()


@power(
    "m1596a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5),
    requires=_holding_someone,
    requires_text="it must currently have an opponent grabbed",
)
def m1596a1(c: Cast) -> None:
    """The prisoner is the weapon, so it takes the blow as well.

    One attack roll and one damage expression, paid out twice: `c.hit(on=)`
    is the same declared line landing on a second creature, which is what
    "damage to the target and the grabbed opponent" says. The Requirement is
    asked of the creature by `requires` and the club is chosen here, because
    the gate is handed `(world, eid)` and cannot pick.
    """
    held = sorted(c.grabbing())
    if not held:
        return
    club = c.choose(held, f"{c.ref}: which prisoner it swings")
    if club is None or club == c.target:
        return
    if c.strike():
        c.hit()
        c.hit(on=club)


@power(
    "m1596a2",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=18),
    trigger=_M1596_STRUCK,
    on=Trigger(Hit, both(hits_me, by_melee), _M1596_STRUCK),
)
def m1596a2(c: Cast) -> None:
    """No damage is printed: the hold is the whole hit line. The attacker is
    read off the trigger, which is what a `NO_TARGET` reaction has."""
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    if attacker is None or not c.strike(on=attacker):
        return
    c.immobilized(until=When.SAVE_ENDS, on=attacker)


@power(
    "m1596a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=19),
    trigger=_M1596_FELLED,
    on=Trigger(Dropped, about_me, _M1596_FELLED),
)
def m1596a3(c: Cast) -> None:
    """A death throe. No damage is printed, so the slow is the hit line."""
    if c.strike():
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1596a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1596a4(c: Cast) -> None:
    """It walks and its prisoners come with it.

    `Condition.GRABBED` stops the victim moving and asks nothing of the
    grabber, so the prisoners do not follow of their own accord: they are
    placed afterwards, which is the printed "at the end of its movement it
    places the grabbed creatures in any squares adjacent to it". Each is
    offered a square its own footprint fits in.
    """
    held = sorted(c.grabbing())
    c.move(c.speed_of())
    for who in held:
        beside = [
            sq
            for sq in _free_square_within(c, c.me, 1, mover=who)
            if sq not in squares(c.world, c.me)
        ]
        if beside:
            c.slide(20, on=who, to=beside[0])


# ==========================================================================
# m1637
# ==========================================================================

_M1637_STANCE = "m1637a4 stance"
_M1637_SHOT_AT = "an enemy attacks it while its stance is up"
_M1637_AVENGED = "an enemy kills one of its allies in its line of sight"


@power(
    "m1637a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 6),
)
def m1637a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1637a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m1637a1(c: Cast) -> None:
    """Two slams, and a burst only if they both land on the same creature.

    The Secondary Attack has no ref of its own, so its printed total goes
    through `_secondary`, which takes the level term back out the way the
    header's `Attack(printed=)` does. The count is kept per creature rather
    than per swing, because the printed condition is "both against the same
    target" and the two swings may well go to two.
    """
    landed: dict[int, int] = {}
    for _ in range(2):
        prey = _foe_in_reach(c, 2)
        if prey is None:
            break
        c.use_power("m1637a0", on=prey, spend=False)
        if c.landed:
            landed[prey] = landed.get(prey, 0) + 1
    if not any(count >= 2 for count in landed.values()):
        return
    for who in sorted(c.in_squares(spread(squares(c.world, c.me), 1), side="enemy")):
        if _secondary(c, 17, FORT, who):
            c.damage("1d8", 3, dtype=DamageType.POISON, on=who, detail=c.ref)
            c.slowed(until=When.SAVE_ENDS, on=who)


@power(
    "m1637a2",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 5, dtype=DamageType.POISON, half_on_miss=True),
    no_provoke=True,
    trigger=_M1637_SHOT_AT,
    on=Trigger(AttackDeclared, targets_me, _M1637_SHOT_AT),
)
def m1637a2(c: Cast) -> None:
    """The stance is asked **here**, not in a `requires=`: a trait or a
    trigger gated on something that starts false is refused once and never
    offered again, and this row's condition comes and goes every round. The
    miss line is written out, because `half_on_miss=True` is declared data
    nothing in the engine reads."""
    if not any(eff.label == _M1637_STANCE for eff in c.world.effects.of(c.me)):
        return
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
    else:
        c.hit(on=attacker, half=True)


@power(
    "m1637a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
    no_provoke=True,
    trigger=_M1637_AVENGED,
    on=Trigger(Dropped, _my_ally_was_killed, _M1637_AVENGED),
)
def m1637a3(c: Cast) -> None:
    """Who struck the killing blow is not on `Dropped`, so it comes off the
    `DamageApplied` immediately before it -- which is what `_killer_of` is
    for. "Save ends both" is one effect carrying the blindness and the
    burn."""
    fallen = getattr(c.trigger, "actor", None)
    if fallen is None:
        return
    killer = _killer_of(c, fallen)
    if killer is None or killer not in c.enemies() or not c.can_see(killer):
        return
    if not c.strike(on=killer):
        return
    c.hit(on=killer)
    _held_and_softened(
        c, killer, conditions=(Condition.BLINDED,), ongoing=(5, DamageType.NECROTIC)
    )


@power(
    "m1637a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
)
def m1637a4(c: Cast) -> None:
    """Armour for itself and teeth for its allies, until it moves.

    The allies' extra damage is a rider on their melee swings rather than a
    bonus laid on each of them: line of sight is read at the moment the blow
    lands, so somebody who walks out of view stops being paid, and an ally
    arriving later is paid. m1637a2 reads the stance's label to know whether
    it may answer at all.
    """
    me = c.me

    def teeth(stance: Effect) -> Effect | None:
        def bite(ev: Hit) -> None:
            if ev.attacker == me or ev.attacker not in c.allies():
                return
            if not c.can_see(ev.attacker):
                return
            p = get(getattr(ev, "power", "") or "")
            if p is not None and p.reach.kind == "melee":
                c.damage("1d8", dtype=DamageType.POISON, on=ev.target, detail=c.ref)

        return c.watch(Hit, bite, until=When.EONT, on=me, label=_M1637_STANCE)

    _meditative(c, resist=20, then=teeth)
    c.effect(_M1637_STANCE, on=me, until=When.EONT)


# ==========================================================================
# m1874
# ==========================================================================

_M1874_FED = "an adjacent creature becomes bloodied"


@power(
    "m1874a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m1874a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1874a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("1d12", 8, kind=LIMITED),
)
def m1874a1(c: Cast) -> None:
    """Only into something already off balance, and it feeds on the wound.

    The Requirement is about *this* target rather than about the creature, so
    it is asked in the body: a `requires=` gate is handed `(world, eid)` and
    has no target to ask about. The printed "recharges when an adjacent
    creature becomes bloodied" is armed on top of the die the header rolls --
    the two only ever agree to make the row available sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: distance_between(c.world, me, ev.actor) <= 1)
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, me, victim, c.ref):
        return
    if not c.strike():
        return
    c.hit()
    c.weakened(until=When.SAVE_ENDS)
    c.heal(63, on=me)


@power(
    "m1874a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=17),
)
def m1874a2(c: Cast) -> None:
    """No damage: the betrayal is the whole hit line.

    "An adjacent ally of the m1874's choice" is an ally *of the target*,
    which from this creature's side of the board is one of its own enemies --
    so the pool is the enemy list with the victim taken out, and `on=` is
    named because `c.grant_attack` would otherwise aim at this row's target,
    which is the creature swinging.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    mates = sorted(
        foe
        for foe in c.enemies()
        if foe != victim and distance_between(c.world, victim, foe) <= 1
    )
    if mates:
        c.grant_attack(victim, on=c.choose(mates, f"{c.ref}: who it turns on"))


@power(
    "m1874a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("1d6", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1874a3(c: Cast) -> None:
    """The healing half names a type rather than a side, so it is read off
    the squares the burst covers and not off the target list -- an undead
    standing in it is paid whether it was a target or not, and the caster is
    one of them."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    if not c.first:
        return
    for who in sorted(c.in_squares(c.area(), side="any")):
        if c.is_kind("undead", on=who):
            c.heal(15, on=who)


@power(
    "m1874a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1874a4(c: Cast) -> None:
    """A shape that trades attacking for flight and for taking half of
    everything. The hour is not a fight's clock, so the hold runs to the end
    of the encounter; `c.endable` is the printed minor action out of it, and
    it takes the three holds down together."""
    me = c.me
    thin = c.insubstantial(until=When.ENCOUNTER, on=me)
    wings = c.mode("fly", 12, until=When.ENCOUNTER, on=me)
    quiet = c.cannot_attack(on=me, until=When.ENCOUNTER)

    def revert() -> None:
        for eff in (thin, wings, quiet):
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "it took its own shape back")

    c.endable(thin, MINOR, then=revert)


# ==========================================================================
# m1882
# ==========================================================================


@power(
    "m1882a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=22),
    damage=Damage("1d4", 6),
)
def m1882a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1882a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=20),
    damage=Damage("2d6", 9, dtype=DamageType.NECROTIC),
)
def m1882a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1882a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=20),
    damage=Damage("2d6", 9, dtype=DamageType.COLD),
)
def m1882a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1882a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=20),
    damage=Damage("3d10", 9, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1882a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)
        c.heal(15, on=c.me)


@power(
    "m1882a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=20),
    damage=Damage("2d8", 9, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.no_surges()",),
)
def m1882a4(c: Cast) -> None:
    """The burn is exact. "Cannot spend healing surges while taking it" is
    narrower than `c.no_healing`, which stops every sort of healing -- using
    that would take away a leader's word as well as the victim's own second
    wind, so the clause waits on a verb of its own."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)


@power(
    "m1882a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=20),
    damage=Damage("2d8", 12, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1882a5(c: Cast) -> None:
    """The blow is necrotic and the burn is fire: two sentences, two types,
    and no `dtypes` needed because they never share one roll."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)


@power(
    "m1882a6",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1882a6(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1969
# ==========================================================================

_M1969_AIMED_AT = "an enemy would target it with an attack"
_M1969_FELLED = "it is reduced to 0 hit points"


@power(
    "m1969a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC),
)
def m1969a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1969a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m1969a1(c: Cast) -> None:
    """"Each one against a different target" is the cap the body enforces:
    the second swing is offered only what the first did not take."""
    struck: set[int] = set()
    for _ in range(2):
        prey = _foe_in_reach(c, 2, apart_from=struck)
        if prey is None:
            return
        struck.add(prey)
        c.use_power("m1969a0", on=prey, spend=False)


@power(
    "m1969a2",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    trigger=_M1969_AIMED_AT,
    on=Trigger(AttackDeclared, targets_me, _M1969_AIMED_AT, window=Window.BEFORE),
)
def m1969a2(c: Cast) -> None:
    """Either the blow goes somewhere else or it does not happen.

    An interrupt is the only action that can do either, which is why this is
    declared one whatever the compendium's column says: `c.redirect` moves
    the live event and `c.cancel` stops it, and both are read back by
    `resolve.attack` on the far side of the window. "A negated daily or
    encounter power is expended" needs nothing -- the use was spent at
    declaration, before this row ever saw it.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None or not c.strike(on=attacker):
        return
    others = sorted(
        who
        for who in (c.me, *c.allies())
        if who != c.me and distance_between(c.world, attacker, who) <= 20
    )
    picked = c.choose(others, f"{c.ref}: who it points the blow at") if others else None
    if picked is not None:
        c.redirect(to=picked)
    else:
        c.cancel()


@power(
    "m1969a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
    dropped=("c.aftereffect()",),
)
def m1969a3(c: Cast) -> None:
    """A toll on every attack power the victim spends, under one save.

    `c.on_attack` is the watch, hung on the hold so the two end together --
    laid separately the listener would outlive the saving throw that is
    supposed to stop it. The Aftereffect is dropped: a hold that lands when
    the first ends **by a save** has nowhere to go, since `on_end` fires for
    the teardown as well.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = c.world.effects.apply(victim, c.me, When.SAVE_ENDS, label=f"{c.ref} toll")

    def toll(ev: Any) -> None:
        if not hold.ended:
            c.flat(5, dtype=DamageType.PSYCHIC, on=victim)

    watch = c.on_attack(toll, by=victim, until=When.ENCOUNTER, label=f"{c.ref} toll")
    hold.on_end.append(lambda: c.world.effects.end(watch, "the toll is paid"))


@power(
    "m1969a4",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=WILL, printed=17),
    trigger=_M1969_FELLED,
    on=Trigger(Dropped, about_me, _M1969_FELLED),
    todo=("c.contract(ref)",),
)
def m1969a4(c: Cast) -> None:
    """A death throe whose only printed consequence is a disease, and there
    is no contraction mechanism -- so nothing at all works here and the
    marker is `todo` rather than `dropped`, which would count a row that does
    nothing inside the audit's `ok`."""
    if c.strike():
        c.note(f"{c.ref}: the target would contract this stat block's disease")


@power(
    "m1969a5",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1969a5(c: Cast) -> None:
    """The same stance m1637a4 takes, paying a flat attack bonus instead of
    extra damage. The bonus is untyped: the card prints "+2 bonus to attack
    rolls" with no type word in front of it, and writing `kind="power"` there
    would stop two bonuses stacking where the rule stacks them."""

    def rally(stance: Effect) -> Effect | None:
        mates = sorted(mate for mate in c.allies() if c.can_see(mate))
        held = None
        for mate in mates:
            held = c.bonus("attack", 2, on=mate, until=When.EONT) or held
        return held

    _meditative(c, resist=20, then=rally)


# ==========================================================================
# m1970
# ==========================================================================

_M1970_FELLED = "it is reduced to 0 hit points"


@power(
    "m1970a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m1970a0(c: Cast) -> None:
    """"Plus 1d6 necrotic damage" is a second expression and a second type,
    so it is a second roll rather than something `Damage` can hold."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC, detail=c.ref)


@power(
    "m1970a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m1970a1(c: Cast) -> None:
    """`charges=True` or the engine measures the weapon's reach before the
    run and refuses the row whenever the target is further off than a sword,
    which is every situation a charge is for."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1970a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 3, dtype=DamageType.FORCE),
)
def m1970a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m1970a3",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON, Keyword.DISEASE],
    trigger=_M1970_FELLED,
    on=Trigger(Dropped, about_me, _M1970_FELLED),
    dropped=("c.contract(ref)",),
)
def m1970a3(c: Cast) -> None:
    """A death throe in two halves. The swing is whichever row this
    creature's basic attack actually is, which is the printed "makes a melee
    basic attack"; the Secondary Attack has no ref of its own, so its printed
    total goes through `_secondary`. The disease is the dropped half -- the
    swing is real, so the row plays."""
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        c.basic(on=prey)
    for who in sorted(foe for foe in c.enemies() if c.distance(foe) <= 10):
        if _secondary(c, 18, WILL, who):
            c.note(f"{c.ref}: the target would contract this stat block's disease")


@power(
    "m1970a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m1970a4(c: Cast) -> None:
    """Declared with no target: the dispatcher aims a row at an enemy and
    this one is about an ally, and a bloodied one at that. The enemy is
    picked from what that creature could actually reach."""
    bloodied = sorted(
        mate for mate in c.allies() if c.bloodied(mate) and c.distance(mate) <= 10
    )
    if not bloodied:
        return
    mate = c.choose(bloodied, f"{c.ref}: which wounded ally swings")
    if mate is not None:
        _grant_melee_basic(c, mate)


# ==========================================================================
# m2327
# ==========================================================================

_M2327_HIT = "it is hit by an attack"


@power(
    "m2327a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d4", 2),
)
def m2327a0(c: Cast) -> None:
    """The Secondary Attack goes at the same creature and has no ref of its
    own, so its printed total goes through `_secondary`."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 17, WILL, victim):
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


@power(
    "m2327a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m2327a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m2327a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m2327a2(c: Cast) -> None:
    """"Grants combat advantage to any enemy" is the whole of the victim's
    enemy side, which from this creature's own side of the board is `team` --
    `to="ally"` would leave the caster out and `to="me"` would leave
    everybody else out."""
    if c.strike():
        c.hit()
        c.slide(3)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")


@power(
    "m2327a3",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.ACID, kind=LIMITED),
    trigger=_M2327_HIT,
    on=Trigger(Hit, hits_me, _M2327_HIT),
)
def m2327a3(c: Cast) -> None:
    """**The brief prints no Trigger line for this row at all** -- only
    "immediate reaction, encounter" and the attack. Being hit is the only
    shape a close blast reaction of this kind takes, so that is what is
    declared; the gap is named in the report rather than left as a row that
    can never fire."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.ACID)


# ==========================================================================
# m2329
# ==========================================================================

_M2329_ZONE = "m2329a2 zone"
_M2329_BLOODIED = "it is first bloodied"


@power(
    "m2329a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d4", 3),
)
def m2329a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


@power(
    "m2329a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.POISON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d6", 5, dtype=DamageType.ACID),
)
def m2329a1(c: Cast) -> None:
    """A printed band of "5/10" takes the short number. The cost to itself is
    paid whether or not the throw lands, which is why it is outside the hit
    branch, and the splash is read off the squares beside the target rather
    than off a second target line."""
    c.flat(5, on=c.me)
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    for who in sorted(c.in_squares(spread(squares(c.world, victim), 1), side="any")):
        if who not in (victim, c.me):
            c.flat(5, dtype=DamageType.ACID, on=who)


@power(
    "m2329a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=WILL, printed=17),
    dropped=("c.grant_action(move_zone)",),
)
def m2329a2(c: Cast) -> None:
    """A zone that attacks again every time somebody starts a turn in it.

    No damage is printed, so there is no `damage=` and no `c.hit()`: the daze
    and the betrayal are the hit line, and the Miss line is the daze alone,
    which is written out. The repeat is the same consequence aimed again, so
    it goes through one function rather than through `c.use_power`, which
    would lay a second zone every time.

    Sustaining it is the printed Sustain Minor. Moving it 3 squares costs a
    **move** action, and `actions._granted` is only ever read for five words,
    so laying a sixth lays something nothing consults -- that is the dropped
    clause.
    """
    victim = c.target
    hit = c.strike()
    if victim is not None:
        c.dazed(until=When.SAVE_ENDS, on=victim)
        if hit:
            mates = sorted(
                foe
                for foe in c.enemies()
                if foe != victim and distance_between(c.world, victim, foe) <= 1
            )
            if mates:
                c.grant_attack(
                    victim, on=c.choose(mates, f"{c.ref}: who it turns on")
                )
    if not c.first:
        return
    me = c.me
    zone = c.zone(c.area(), label=_M2329_ZONE, until=When.EONT, sustain=MINOR)

    def again(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(zone):
            return
        if _secondary(c, 17, WILL, ev.actor):
            c.dazed(until=When.SAVE_ENDS, on=ev.actor)
            mates = sorted(
                foe
                for foe in c.enemies()
                if foe != ev.actor and distance_between(c.world, ev.actor, foe) <= 1
            )
            if mates:
                c.grant_attack(ev.actor, on=mates[0])
        else:
            c.dazed(until=When.SAVE_ENDS, on=ev.actor)

    c.watch(TurnStart, again, until=When.ENCOUNTER, on=me, label=f"{c.ref} again")


@power(
    "m2329a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 6, kind=LIMITED),
    dropped=("c.aftereffect()",),
)
def m2329a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS, to="team")


@power(
    "m2329a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m2329a4(c: Cast) -> None:
    """Three attacks, one per target, which is what the header's `UpTo(3)`
    and the body being called once per target already say. The destination is
    named rather than measured: `c.teleport` with no `to` offers every square
    in range, and the printed line says whose choice it is and how far from
    whom."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    landing = _free_square_within(c, c.me, 5, mover=victim)
    if not landing:
        return
    where = c.world.decide(c.me, "teleport", landing, f"{c.ref}: where it puts them")
    c.teleport(20, who=victim, to=where)


@power(
    "m2329a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m2329a5(c: Cast) -> None:
    """The jump is one square per enemy hit, so it is counted across the
    whole burst and taken on the last target rather than once per creature.
    The recharge sentence is armed on top of the die the header rolls."""
    me = c.me
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    if not c.last:
        return
    hits = sum(
        1
        for who in c.targets
        if who is not None and c.is_(Condition.DAZED, on=who)
    )
    if hits:
        c.teleport(hits)


# ==========================================================================
# m2335
# ==========================================================================

_M2335_AIMED_AT = "it is targeted by a melee or ranged attack"


@power(
    "m2335a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 6),
)
def m2335a0(c: Cast) -> None:
    """Three at a time, and no escape DC is printed, so the grab takes no
    marker."""
    if not c.strike():
        return
    c.hit()
    if len(c.grabbing()) < 3:
        c.grab()


@power(
    "m2335a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="grabbed by it"),
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d6", 6),
    dropped=("Target.kind",),
)
def m2335a1(c: Cast) -> None:
    """"A creature it has grabbed" is the target's own state, which `Target`
    cannot filter on -- so the chooser's answer is redirected rather than
    thrown away, which would waste the row while a prisoner was in hand."""
    victim = _restricted_to(c, 2, lambda f: f in c.grabbing())
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.ongoing(5, DamageType.POISON, on=victim)


@power(
    "m2335a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="grabbed by it"),
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("5d6", 6, kind=LIMITED),
    dropped=("Target.kind",),
)
def m2335a2(c: Cast) -> None:
    """It throws what it was holding. The grab is ended by hand, before the
    push: a creature still held cannot be moved away, so the order is the
    printed one and not a matter of taste."""
    victim = _restricted_to(c, 2, lambda f: f in c.grabbing())
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    for eff in list(c.world.effects.of(victim)):
        if (Relation.GRABBED_BY, c.me, victim) in eff.relations:
            c.world.effects.end(eff, "it let go")
    c.push(3, on=victim)
    c.prone(on=victim)


@power(
    "m2335a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 6),
)
def m2335a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
        c.prone()


@power(
    "m2335a4",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_holding_someone,
    requires_text="it must have a creature grabbed",
    trigger=_M2335_AIMED_AT,
    on=Trigger(AttackDeclared, targets_me, _M2335_AIMED_AT, window=Window.BEFORE),
)
def m2335a4(c: Cast) -> None:
    """A prisoner used as a shield.

    Declared an interrupt whatever the compendium's column says: `c.redirect`
    moves the live event and only an interrupt runs before
    `resolve.attack` reads the target back. The attacker is excluded by the
    printed line -- "other than the attacker" -- which matters when the
    creature has hold of the one swinging at it.
    """
    attacker = getattr(c.trigger, "attacker", None)
    shields = sorted(who for who in c.grabbing() if who != attacker)
    if not shields:
        return
    picked = c.choose(shields, f"{c.ref}: which prisoner it holds up")
    if picked is not None:
        c.redirect(to=picked)


@power(
    "m2335a5",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2335a5(c: Cast) -> None:
    c.shift(2)


# ==========================================================================
# m2350
# ==========================================================================

_M2350_PASSED = "a creature moves or shifts within 2 squares of it"


@power(
    "m2350a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.ACID),
)
def m2350a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.ACID)


@power(
    "m2350a1",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.ACID),
    trigger=_M2350_PASSED,
    on=Trigger(MoveEnd, _anyone_moves_within(2), _M2350_PASSED),
    dropped=("c.halt()",),
)
def m2350a1(c: Cast) -> None:
    """Asked on `MoveEnd`, where the creature has arrived: on `MoveStart`
    nothing has happened yet and the distance would be measured from where it
    set off.

    "And the target stops moving" is the dropped clause. Nothing cuts a move
    short -- `c.immobilized` stops the *next* one and `c.no_walk` takes the
    action away rather than the remaining squares -- and a reaction has in any
    case already let the move finish, so the two halves that do work are the
    bite and the burn.
    """
    who = getattr(c.trigger, "actor", None)
    if who is None or who == c.me or c.distance(who) > 2:
        return
    if c.strike(on=who):
        c.hit(on=who)
        c.ongoing(10, DamageType.ACID, on=who)


@power(
    "m2350a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4, dtype=DamageType.ACID),
)
def m2350a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m2350a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d6", 6, dtype=DamageType.ACID, kind=LIMITED),
)
def m2350a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m2350a4",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
)
def m2350a4(c: Cast) -> None:
    """A wail the deaf do not hear, which worsens on the first failed save.

    No damage is printed, so there is no `damage=` and no `c.hit()`. "Save
    ends both" is one effect carrying the attack penalty and the defence
    penalty; `escalate` runs on every failure, so the step ends the hold it
    came from and lays one with no escalation of its own, which is what makes
    "First Failed Save" fire once rather than every round.
    """
    victim = c.target
    if victim is None or c.is_(Condition.DEAFENED, on=victim):
        return
    if not c.strike():
        return

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.world.effects.apply(
            eff.owner, c.me, When.SAVE_ENDS, label=f"{c.ref} worse",
            conditions=(Condition.DAZED,),
            mods=[(eff.owner, m) for m in _softened(c, attack=2)],
        )

    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        mods=[(victim, m) for m in _softened(c, attack=2, defences=2)],
        escalate=worsen,
    )


# ==========================================================================
# m3754
# ==========================================================================


@power(
    "m3754a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 8),
)
def m3754a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3754a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 9, dtype=DamageType.POISON),
)
def m3754a1(c: Cast) -> None:
    """"A +2 power bonus to attack rolls **against the target**" is a gated
    modifier rather than a flat one: the gate is asked every time the ally
    puts a roll together, so it pays only on the creature the card names.
    `kind="power"` because the card prints the word."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mates = sorted(mate for mate in c.allies() if c.can_see(mate))
    if not mates:
        return
    mate = c.choose(mates, f"{c.ref}: which ally it marks the way for")
    if mate is not None:
        c.bonus(
            "attack",
            2,
            on=mate,
            until=When.EONT,
            kind="power",
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "m3754a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    once_per_round=True,
)
def m3754a2(c: Cast) -> None:
    """No damage: the slide and the borrowed swing are the hit line. The
    basic attack is aimed with `on=` because `c.grant_attack` would otherwise
    point it at this row's own target, which is the creature swinging."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.slide(5, on=victim)
    span = _reach_of(c, victim)
    prey = sorted(
        foe
        for foe in (c.me, *c.allies())
        if foe != victim and distance_between(c.world, victim, foe) <= span
    )
    if prey:
        c.grant_attack(victim, on=c.choose(prey, f"{c.ref}: who it swings at"))


@power(
    "m3754a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 4, kind=LIMITED),
)
def m3754a3(c: Cast) -> None:
    """The printed "recharges when bloodied" is armed on top of the die the
    header rolls; the two only ever agree to make the row available sooner.
    A -2 to all defences is four modifiers on one hold, which is one saving
    throw against one printed sentence."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _held_and_softened(c, victim, defences=2)


@power(
    "m3754a4",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m3754a4(c: Cast) -> None:
    """Darkness nobody sees through and nobody inside sees out of. The
    caster's own exemption is the dropped clause: `blocks_sight` is what
    `cover_between` reads and it applies to everybody, with no way to leave
    one creature out."""
    _dark_cloud(c, until=When.EONT)


@power(
    "m3754a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    dropped=("c.no_invisibility()",),
)
def m3754a5(c: Cast) -> None:
    """No damage: the two exposures are the hit line.

    "Grants combat advantage to all attackers" is the victim's whole enemy
    side, which from this creature's side of the board is `team`. `c.no_cover`
    is cover and concealment; being unable to benefit from **invisibility** is
    a third thing it does not cover, and nothing says it -- the veil is a hold
    on the invisible creature and there is no switch that reads "this one does
    not get to use it".
    """
    if not c.strike():
        return
    c.grants_advantage(until=When.EONT, to="team")
    c.no_cover(until=When.EONT)


# ==========================================================================
# m3848
# ==========================================================================


@power(
    "m3848a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("1d10", 6),
)
def m3848a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3848a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 4),
)
def m3848a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3848a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=15),
)
def m3848a2(c: Cast) -> None:
    """No damage is printed: the shove and the hold are the whole hit line.
    The push is taken first, because a creature held still cannot then be
    moved."""
    if c.strike():
        c.push(3)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3848a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3848a3(c: Cast) -> None:
    """Narrative only: a disguise with no mechanical change, which is the
    reading the level-10 lurkers settled."""
    c.note(f"{c.ref}: it takes the shape of some Medium humanoid")


@power(
    "m3848a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def m3848a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and narrative with it:
    squeezing through a small opening is navigation and nothing on a board
    ever asks for it. `Condition.SQUEEZING` is the penalty for being wedged
    in, which is the opposite of what this card grants."""
    c.note(f"{c.ref}: it fits through a gap a Tiny creature would")


# ==========================================================================
# m3902
# ==========================================================================


@power(
    "m3902a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5),
)
def m3902a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3902a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d10", 6, kind=LIMITED),
    requires_text="requires a quarterstaff",
)
def m3902a1(c: Cast) -> None:
    """The printed Requirement names the creature's own kit, which is not a
    gate: `Gear` is empty on every monster, so a `c.wielding` test would be
    false in every fight rather than only on a bare board -- the reading #366
    settled. `requires_text` is what the card shows."""
    if c.strike():
        c.hit()
        c.push(1)
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3902a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d10", 6),
)
def m3902a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.FIRE, until=When.SAVE_ENDS)


# ==========================================================================
# m3919
# ==========================================================================

_M3919_BLOODIED = "it is first bloodied"


@power(
    "m3919a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m3919a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3919a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m3919a1(c: Cast) -> None:
    """"(hit or miss)" puts the payout outside the hit branch. The bonus is
    untyped -- the card prints "+2 bonus to attacks" with no type word -- and
    the allies are read off the board rather than declared `EACH_ALLY`,
    because the header's target is the creature being hit."""
    if c.strike():
        c.hit()
    for mate in sorted(mate for mate in c.allies() if c.distance(mate) <= 5):
        c.heal(10, on=mate)
        c.bonus("attack", 2, on=mate, until=When.EONT)


@power(
    "m3919a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m3919a2(c: Cast) -> None:
    """No damage is printed: the shove and the hold are the hit line, and the
    push is taken before the hold for the same reason m3848a2 does."""
    if c.strike():
        c.push(3)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3919a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
    once_per_round=True,
)
def m3919a3(c: Cast) -> None:
    """One call: `c.surge` spends the ally's own surge and `bonus` is the
    printed "and regain an additional 3d6". The recharge sentence is armed on
    top of the die the header rolls."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.may("spend a healing surge"):
        c.surge(bonus=c.roll("3d6"))


@power(
    "m3919a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3919a4(c: Cast) -> None:
    """Four defences, one clock. The bonus is untyped: the card prints "+2
    bonus to all defenses" with no type word in front of it."""
    me = c.me
    c.heal(10, on=me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, on=me, until=When.EONT)


# ==========================================================================
# m3929
# ==========================================================================

_M3929_HALVED = "it is reduced to half its hit points or fewer"


@power(
    "m3929a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d10", 6, dtype=DamageType.FIRE),
)
def m3929a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m3929a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.COLD),
)
def m3929a1(c: Cast) -> None:
    """The slow and the four penalties share the printed clock, so they are
    laid on it rather than under a saving throw this card never asks for."""
    if not c.strike():
        return
    c.hit()
    c.slowed(until=When.EONT)
    for defended in EVERY_DEFENCE:
        c.penalty(defended, 2, until=When.EONT)


@power(
    "m3929a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.FIRE],
    attack=Attack(vs=FORT, printed=16),
    dropped=("Damage(dtypes=)",),
)
def m3929a2(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header -- `Damage`
    holds one `dtype` -- so it is rolled in the body as one blow of two
    types, which is what resistance reads as a unit."""
    if not c.strike():
        return
    c.damage(
        "1d10", 6,
        dtypes=(DamageType.COLD, DamageType.FIRE),
        detail=c.ref,
    )
    c.slide(3)
    c.dazed(until=When.SAVE_ENDS)


@power(
    "m3929a3",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=16),
    trigger=_M3929_HALVED,
    on=Trigger(Bloodied, about_me, _M3929_HALVED),
    dropped=("Damage(dtypes=)",),
)
def m3929a3(c: Cast) -> None:
    """"Reduced to 132 hit points or fewer" is half of the 264 the database
    holds, which is what `Bloodied` announces -- so the printed number is read
    as the condition it describes rather than hand-written.

    The blast lands and then it is gone: the teleport is once for the whole
    burst, which is what `c.last` guards.
    """
    if c.strike():
        c.damage(
            "3d10", 6,
            dtypes=(DamageType.COLD, DamageType.FIRE),
            detail=c.ref,
        )
    if c.last:
        c.teleport(20)


# ==========================================================================
# m3935
# ==========================================================================


@power(
    "m3935a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5),
)
def m3935a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3935a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d10", 6),
)
def m3935a1(c: Cast) -> None:
    """The card spells this creature's own id as another block's; the row
    every sentence plainly means is this one's.

    "It **and** its allies" is `team`, so the caster is in the list, and each
    of them gets its own gated +1 -- two bonuses of one kind do not add, so
    saying it twice on one creature would be a +1 forever. The bonus is
    untyped: the card prints no type word.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    for who in (c.me, *sorted(c.allies())):
        c.bonus(
            "attack",
            1,
            on=who,
            until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "m3935a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d10", 6),
)
def m3935a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3935a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d10", 6, kind=LIMITED),
    requires_text="requires a quarterstaff",
)
def m3935a3(c: Cast) -> None:
    """The printed Requirement names the creature's own kit and is shown
    rather than gated, for the reason m3902a1 gives."""
    if c.strike():
        c.hit()
        c.push(1)
        c.blinded(until=When.SAVE_ENDS)


# ==========================================================================
# m3940
# ==========================================================================


@power(
    "m3940a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m3940a0(c: Cast) -> None:
    """"Plus 1d8 fire damage" is a second expression and a second type, so it
    is a second roll rather than something `Damage` can hold."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.FIRE, detail=c.ref)
        c.penalty(AC, 2, until=When.EONT)


@power(
    "m3940a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m3940a1(c: Cast) -> None:
    """A burn with a duration no `When` holds: it lasts until the victim ends
    a turn somewhere that is not beside this creature.

    So the hold runs to the end of the encounter and a `TurnEnd` watch ends
    it when the printed condition comes true. Adjacency is measured as the
    turn closes, which is the moment the card names -- stepping away and back
    inside one turn does not put it out.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.damage("1d8", dtype=DamageType.FIRE, detail=c.ref)
    burn = c.ongoing(5, DamageType.FIRE, on=victim, until=When.ENCOUNTER)
    if burn is None:
        return
    me = c.me

    def smothered(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or burn.ended:
            return
        if distance_between(c.world, me, victim) > 1:
            c.world.effects.end(burn, "it got clear")

    watch = c.watch(
        TurnEnd, smothered, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn"
    )
    burn.on_end.append(lambda: c.world.effects.end(watch, "the burn is out"))


@power(
    "m3940a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE),
)
def m3940a2(c: Cast) -> None:
    """The Effect line pays its own side and lands whether anything was hit
    or not, so it sits outside the hit branch and behind `c.first`. The
    allies' reaction is m3940a4 used by **them**, which `who=` names --
    without it the row would be spent by the caster."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    c.temp_hp(10, on=c.me)
    for mate in sorted(c.in_squares(c.area(), side="ally")):
        if mate == c.me:
            continue
        c.temp_hp(10, on=mate)
        c.use_power("m3940a4", who=mate, spend=False)


@power(
    "m3940a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m3940a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying both penalties. `_softened`
    knows attack and defences and not damage, so the damage modifier is built
    beside it and laid on the same hold -- two effects would be two saving
    throws against one printed sentence."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        mods=[
            *[(victim, m) for m in _softened(c, attack=2)],
            (victim, Mod(what="damage", value=-4, kind="untyped", label=c.ref)),
        ],
    )


@power(
    "m3940a4",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m3940a4(c: Cast) -> None:
    """`against="ongoing"` picks the burn rather than whichever save-ends
    effect the table happens to hand back first, which is the printed "a
    saving throw against an ongoing damage effect"."""
    me = c.me
    c.temp_hp(9, on=me)
    c.save(on=me, against="ongoing")
    if c.bloodied(me):
        c.heal(9, on=me)


# ==========================================================================
# m4033
# ==========================================================================

_M4033_ZONE = "m4033a2 zone"


@power(
    "m4033a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("1d10", 6, dtype=DamageType.PSYCHIC),
)
def m4033a0(c: Cast) -> None:
    """"Ranged 5 or melee" is `MeleeOrRanged`, which is one row with two
    reaches rather than two rows. "An ally of its choice" is one beneficiary,
    which is what `to=<id>` names."""
    if not c.strike():
        return
    c.hit()
    mates = sorted(c.allies())
    if not mates:
        return
    mate = c.choose(mates, f"{c.ref}: which ally sees the opening")
    if mate is not None:
        c.grants_advantage(until=When.EONT, to=mate)


@power(
    "m4033a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 7, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4033a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4033a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(5, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("3d6", 7, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4033a2(c: Cast) -> None:
    """A zone that pays its own side for hitting anybody standing in it.

    The occupancy is asked at the moment the blow lands rather than when the
    zone goes up: the printed line is about where the enemy is when it is hit,
    and anybody can walk in or out between rounds. "It **and** any ally" is
    `team`, so the caster's own blows pay too.
    """
    if c.strike():
        c.hit()
    if not c.first:
        return
    me = c.me
    zone = c.zone(c.area(), label=_M4033_ZONE, until=When.ENCOUNTER)

    def rider(ev: Hit) -> None:
        if ev.attacker != me and ev.attacker not in c.allies():
            return
        if ev.target not in c.world.zones.occupants(zone):
            return
        c.damage("1d6", dtype=DamageType.THUNDER, on=ev.target, detail=c.ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=f"{c.ref} storm")


# ==========================================================================
# m4038
# ==========================================================================

_M4038_BLOODIED = "it is first bloodied"
_M4038_SURGE = "an enemy within 5 squares spends a healing surge"
_M4038_SHOVED = "it is subjected to forced movement"


@power(
    "m4038a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m4038a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m4038a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.COLD],
    attack=Attack(vs=FORT, printed=17),
    dropped=("Damage(dtypes=)",),
)
def m4038a1(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header, so it is
    rolled in the body as one blow of two types."""
    if c.strike():
        c.damage(
            "2d8", 6,
            dtypes=(DamageType.PSYCHIC, DamageType.COLD),
            detail=c.ref,
        )
        c.push(2)


@power(
    "m4038a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.FORCE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("3d10", 6, dtype=DamageType.FORCE, kind=LIMITED),
)
def m4038a2(c: Cast) -> None:
    """The printed "recharges when first bloodied" is armed on top of the die
    the header rolls."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


@power(
    "m4038a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("3d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4038a3(c: Cast) -> None:
    """`SurgeSpent` is emitted from every place a surge is decremented, which
    is the only way "when an enemy within 5 squares spends a healing surge"
    can be seen happening."""
    me = c.me
    _recharge_on(
        c,
        SurgeSpent,
        lambda ev: ev.actor != me and distance_between(c.world, me, ev.actor) <= 5,
    )
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4038a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6, kind=LIMITED),
    trigger=_M4038_SHOVED,
    on=Trigger(ForcedMove, targets_me, _M4038_SHOVED),
)
def m4038a4(c: Cast) -> None:
    """`ForcedMove` is the one event a push, a pull and a slide all go
    through, so declaring it answers all three -- which is what "subjected to
    forced movement" means. The recharge sentence is armed on top of the die
    the header rolls."""
    me = c.me
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


@power(
    "m4038a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("3d6", 0, dtype=DamageType.COLD, kind=LIMITED),
)
def m4038a5(c: Cast) -> None:
    """The card prints dice and no flat bonus, which is a bonus of zero
    rather than an omission."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


# ==========================================================================
# m4329
# ==========================================================================

_M4329_CLOSED_IN = "an enemy moves adjacent to it"


@power(
    "m4329a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5),
    dropped=("c.contract(ref)",),
)
def m4329a0(c: Cast) -> None:
    """The blow is exact. There is no contraction mechanism for the disease,
    so that clause waits; the row plays."""
    if c.strike():
        c.hit()
        c.note(f"{c.ref}: the target would be exposed to this stat block's disease")


@power(
    "m4329a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d12", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.stand_costs(ActionType)",),
)
def m4329a1(c: Cast) -> None:
    """Two recharge sentences, both armed on top of the die the header rolls.

    "Until the end of its next turn the target must take a **standard**
    action to stand up" is the dropped clause: `c.grant_action` makes an
    ordinary thing cost *less*, and nothing makes one cost more -- standing
    is priced in `actions.legal` and there is no modifier on it.
    """
    me = c.me
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
        _recharge_on(c, ActionPointSpent, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


@power(
    "m4329a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
    once_per_round=True,
)
def m4329a2(c: Cast) -> None:
    """No damage: the borrowed swing is the hit line. "The m4329 chooses the
    attack and the target ally" is `c.grant_attack(ref=)` plus `on=`, and the
    row offered is one of the victim's own at-will melee attacks -- which is
    what `c.borrowed_rows` lists."""
    victim = c.target
    if victim is None or not c.strike():
        return
    span = _reach_of(c, victim)
    prey = sorted(
        who
        for who in (c.me, *c.allies())
        if who != victim and distance_between(c.world, victim, who) <= span
    )
    if not prey:
        return
    aimed = c.choose(prey, f"{c.ref}: who it turns on")
    rows = c.borrowed_rows(victim, at_will=True, melee=True)
    pick = c.choose(sorted(rows), f"{c.ref}: which attack it uses") if rows else None
    c.grant_attack(victim, on=aimed, ref=pick or "")


@power(
    "m4329a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
    trigger=_M4329_CLOSED_IN,
    on=Trigger(MoveEnd, _enemy_moves_adjacent, _M4329_CLOSED_IN),
)
def m4329a3(c: Cast) -> None:
    """Asked on `MoveEnd`, where the creature has arrived: on `MoveStart` it
    has not moved yet and the adjacency would be false exactly when the row
    should fire. The daze is only for the creature that walked in, which is
    read off the trigger rather than off the target list."""
    walked_in = getattr(c.trigger, "actor", None)
    if not c.strike():
        return
    c.hit()
    if c.target is not None and c.target == walked_in:
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m5100
# ==========================================================================


@power(
    "m5100a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.contract(ref)",),
)
def m5100a0(c: Cast) -> None:
    """The whole trait is about disease, and there is no disease.

    Both halves -- a saving throw against infection and an Endurance check as
    though a rest had been taken -- ask after a state nothing can be in, so
    nothing here works and the marker is `todo` rather than `dropped`. The
    aura itself is laid, because it is what the trait's range *is* and a
    later contraction mechanism would have somewhere to pay out.
    """
    c.aura(2, label=c.ref, until=When.ENCOUNTER)


@power(
    "m5100a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 7),
)
def m5100a1(c: Cast) -> None:
    """The growth bleeds its host and anybody of its host's side who lingers
    beside it.

    One effect carries the burn so there is one saving throw, and the splash
    is a `TurnEnd` watch hung on that effect: "any ally of the target" is the
    victim's own side, which from this creature's side of the board is the
    enemy list with the victim taken out.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    growth = c.ongoing(5, on=victim)
    if growth is None:
        return
    me = c.me

    def spill(ev: TurnEnd) -> None:
        if ev.ghost or growth.ended or ev.actor in (me, victim):
            return
        if ev.actor not in c.enemies():
            return
        if distance_between(c.world, victim, ev.actor) <= 2:
            c.flat(5, on=ev.actor)

    watch = c.watch(TurnEnd, spill, until=When.ENCOUNTER, on=me, label=f"{c.ref} spill")
    growth.on_end.append(lambda: c.world.effects.end(watch, "the growth withered"))


@power(
    "m5100a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.DISEASE, Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 10, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("c.contract(ref)",),
)
def m5100a2(c: Cast) -> None:
    """The poison is exact. Which of four diseases the d4 picks does not
    matter while none of them can be caught, so the roll is not made -- a
    choice with no consequence is not a mechanic."""
    if c.strike():
        c.hit()
        c.note(f"{c.ref}: the target would be exposed to one of this card's diseases")


@power(
    "m5100a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
)
def m5100a3(c: Cast) -> None:
    """No damage at all: the three squares are the whole of the hit line."""
    if c.strike():
        c.slide(3)


# ==========================================================================
# m5221
# ==========================================================================

_M5221_SPAWNED = "m5221a0 spawn"


@power(
    "m5221a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5221a0(c: Cast) -> None:
    """Whatever it kills gets up on its side at the top of its next turn.

    The creature put on the board is **this** one, read off `Ident.ref`, so
    the sentence needs no printed word at all. `Dropped` says who fell and
    not who felled it, which is what `_killer_of` reads off the blow before
    it; the square is where the body lies, or the nearest free one, which is
    the printed fallback. The rising is deferred to its creator's next turn,
    as the card says, and a character has no type words at all -- so
    "humanoid" reads as "nothing else in particular".
    """
    me = c.me
    waiting: list[Any] = []

    def fell(ev: Dropped) -> None:
        if ev.actor == me or _killer_of(c, ev.actor) != me:
            return
        words = c.kinds_of(ev.actor)
        if words and "humanoid" not in words:
            return
        here = c.world.get(ev.actor, Position)
        if here is not None:
            waiting.append(here.square)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not waiting:
            return
        ref = _stat_block(c)
        for where in list(waiting):
            waiting.remove(where)
            landing = _summon_square(c, where)
            if ref and landing is not None:
                c.summon(ref, at=landing)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=_M5221_SPAWNED)
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rising")


@power(
    "m5221a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    dropped=("Damage(dtypes=)",),
)
def m5221a1(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header. "Until the end
    of **its** next turn" is the victim's clock, which is `When.EOTNT` and not
    `EONT`."""
    if c.strike():
        c.damage(
            "2d10", 10,
            dtypes=(DamageType.COLD, DamageType.NECROTIC),
            detail=c.ref,
        )
        c.slowed(until=When.EOTNT)


@power(
    "m5221a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    dropped=("Damage(dtypes=)",),
)
def m5221a2(c: Cast) -> None:
    """"Living creatures in the blast" rules out the undead, which is a type
    word rather than a side, so it is asked of each target.

    The hold worsens on a creature already slowed, which is a fresh condition
    and not a rewrite of a live effect's `conditions` -- that field is read
    once when the effect lands and once when it ends, and never in between.
    What it heals is half of what it actually dealt, paid out as each blow
    lands -- the body runs once per target and the sum is the same.
    """
    victim = c.target
    if victim is None or c.is_kind("undead", on=victim):
        return
    if not c.strike():
        return
    dealt = c.damage(
        "1d10", 3,
        dtypes=(DamageType.COLD, DamageType.NECROTIC),
        detail=c.ref,
    )
    if c.is_(Condition.SLOWED, on=victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)
    else:
        c.slowed(until=When.SAVE_ENDS, on=victim)
    if dealt:
        c.heal(dealt // 2, on=c.me)


# ==========================================================================
# m5332
# ==========================================================================

_M5332_ELEMENT = "it takes acid, cold, fire, lightning or thunder damage"
_M5332_CAUGHT = "it is hit by an enemy that has combat advantage against it"
_M5332_BLOODIED = "it is first bloodied"
_M5332_WARDS = "m5332a5 ward"


@power(
    "m5332a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5332a0(c: Cast) -> None:
    """Two extra saving throws a turn against being held, and they work on
    holds that have no save of their own.

    `Effects.save` does not look at `When`: it rolls, announces the throw, and
    ends the effect on a success -- which is exactly "including effects that
    don't normally end on a save". Both ends of the turn are watched, because
    the card names both and an ordinary save-ends tick only happens at one.
    """
    me = c.me

    def shrug(ev: Any) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if any(cond in _HELD_FAST for cond in eff.conditions):
                c.world.effects.save(eff)

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=f"{c.ref} dawn")
    c.watch(TurnEnd, shrug, until=When.ENCOUNTER, on=me, label=f"{c.ref} dusk")


@power(
    "m5332a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d10", 10, dtype=DamageType.PSYCHIC),
)
def m5332a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m5332a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=Target(side="enemy", count=99, everyone=True, label="dazed"),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d10", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("Target.kind",),
)
def m5332a2(c: Cast) -> None:
    """The card prints its damage on the **miss** line, which is the only
    place `c.hit()` belongs here: a hit lays the fall and the weakness and
    nothing else.

    "Dazed enemies in the burst" is each target's own state, which `Target`
    cannot filter on, so an undazed one is passed over rather than the whole
    row being thrown away. The temporary hit points count the creatures hit
    across the burst, so they are paid once, on the last target.
    """
    victim = c.target
    if victim is None or not c.is_(Condition.DAZED, on=victim):
        return
    if c.strike():
        c.prone()
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.hit()
    if not c.last:
        return
    hit = sum(
        1
        for who in c.targets
        if who is not None and c.is_(Condition.WEAKENED, on=who)
    )
    if hit:
        c.temp_hp(5 * hit, on=c.me)


@power(
    "m5332a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d10", 6, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m5332a3(c: Cast) -> None:
    """The daze pays the caster while it stands, which is a gated bonus rather
    than a flat one: the gate is asked every time a damage roll is put
    together, so the +4 is there exactly while somebody is still dazed by
    *this* row and needs no second place to remember to take it away. The miss
    line is written out, because `half_on_miss=True` is declared data."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
    if not c.last:
        return
    me, ref = c.me, c.ref

    def still_held(_ctx: dict[str, Any]) -> bool:
        return any(
            eff.label.startswith(ref)
            and Condition.DAZED in eff.conditions
            and not eff.ended
            for eff in c.world.effects.live.values()
        )

    c.bonus("damage", 4, on=me, until=When.ENCOUNTER, when=still_held)


@power(
    "m5332a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d6", 7),
)
def m5332a4(c: Cast) -> None:
    """A toll for staying close, judged as the victim's next turn closes --
    which is the only moment "does not end its next turn at least 2 squares
    away" can be asked. The watch spends itself, so a second blow on the same
    creature does not leave two listeners behind."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if distance_between(c.world, me, victim) < 2:
            c.flat(6, dtype=DamageType.FORCE, on=victim)

    c.watch(
        TurnEnd, toll, until=When.EOTNT, on=victim, label=f"{c.ref} toll", once=True
    )


@power(
    "m5332a5",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5332_ELEMENT,
    on=Trigger(DamageApplied, targets_me, _M5332_ELEMENT),
)
def m5332a5(c: Cast) -> None:
    """It learns whatever just burned it, and forgets the last lesson.

    The type is read off the event, which is the only place it is: `Hit` does
    not carry one and the resistance is against a type rather than against an
    attack. "Until it uses this again" is the previous ward being ended, which
    is also why one label is used for all of them.
    """
    ev = c.trigger
    dtype = getattr(ev, "dtype", None)
    if dtype not in _ELEMENTS:
        return
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M5332_WARDS:
            c.world.effects.end(eff, "it learned something else")
    ward = c.resist(10, dtype, until=When.ENCOUNTER, on=c.me)
    if ward is not None:
        ward.label = _M5332_WARDS


@power(
    "m5332a6",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d6", 6, dtype=DamageType.FORCE),
    trigger=_M5332_CAUGHT,
    on=Trigger(Hit, hits_me, _M5332_CAUGHT),
)
def m5332a6(c: Cast) -> None:
    """"Did that attack have combat advantage" is read off the `Hit`'s live
    `AttackResult`; asking the board again is too late, because a one-shot
    grant has already been spent. The triggering enemy comes off the event,
    which is what a `NO_TARGET` reaction has instead of a target."""
    ev = c.trigger
    if ev is None or not c.had_advantage(ev):
        return
    attacker = getattr(ev, "attacker", None)
    if attacker is None or c.distance(attacker) > 1:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.push(2, on=attacker)
        c.prone(on=attacker)


@power(
    "m5332a7",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5332_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5332_BLOODIED),
)
def m5332a7(c: Cast) -> None:
    c.restore_use("m5332a3")
    c.use_power("m5332a3")


# ==========================================================================
# m5369
# ==========================================================================

_M5369_BLOODIED = "it is first bloodied"
_M5369_BURNED_DOWN = "it is reduced to 0 hit points by fire or lightning damage"


@power(
    "m5369a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 6, dtype=DamageType.POISON),
)
def m5369a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5369a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="granting combat advantage to it"),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("1d8", 6, dtype=DamageType.POISON),
    once_per_round=True,
    dropped=("Target.kind",),
)
def m5369a1(c: Cast) -> None:
    """"One creature granting combat advantage to it" is the target's own
    state, which `Target` cannot filter on, so the chooser's answer is
    redirected rather than thrown away. "Save ends both" is one effect
    carrying the daze and the hold."""
    victim = _restricted_to(c, 2, lambda f: has_combat_advantage(c.world, c.me, f, c.ref))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    _held_and_softened(
        c, victim, conditions=(Condition.DAZED, Condition.IMMOBILIZED)
    )
    c.temp_hp(10, on=c.me)


@power(
    "m5369a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5369a2(c: Cast) -> None:
    """The printed "recharge when first bloodied" is armed on top of the die
    the header rolls."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.shift(c.speed_of())


@power(
    "m5369a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger=_M5369_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5369_BLOODIED),
)
def m5369a3(c: Cast) -> None:
    """"Creatures in the burst other than it" is exactly `EACH_OTHER`:
    `EACH_CREATURE` is side "any" and would catch the creature at the centre.

    The toll is a watch on the victim's own attacks, narrowed to the ones
    aimed at this creature, and hung on the hold so the two end together. The
    veil is the Effect line and is taken once, whatever the blast did.
    """
    victim = c.target
    me = c.me
    if victim is not None and c.strike():
        c.hit()
        hold = c.world.effects.apply(victim, me, When.SAVE_ENDS, label=f"{c.ref} toll")

        def toll(ev: AttackDeclared) -> None:
            if not hold.ended and getattr(ev, "target", None) == me:
                c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

        watch = c.on_attack(
            toll, by=victim, until=When.ENCOUNTER, label=f"{c.ref} toll"
        )
        hold.on_end.append(lambda: c.world.effects.end(watch, "the toll is paid"))
    if c.last:
        c.invisible(on=me, until=When.EONT)


@power(
    "m5369a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 8, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    trigger=_M5369_BURNED_DOWN,
    on=Trigger(Dropped, about_me, _M5369_BURNED_DOWN),
)
def m5369a4(c: Cast) -> None:
    """A death throe, and only when the blow that finished it was fire or
    lightning. `Dropped` says who struck and not what with, so the type comes
    off the `DamageApplied` immediately before it -- the same arrangement
    `c.revives_unless` needs. The miss line is written out."""
    if c.first and not _felled_by(c, (DamageType.FIRE, DamageType.LIGHTNING)):
        return
    if c.strike():
        c.hit()
        c.push(c.roll("1d4"))
    else:
        c.hit(half=True)


# ==========================================================================
# m5698
# ==========================================================================

_M5698_SCORCHED = "it takes fire damage"
_M5698_SLAM_BURN = "m5698a5 burning slam"


@power(
    "m5698a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5698a0(c: Cast) -> None:
    """"Ends its turn in the aura" is the one zone clause `c.burns` does not
    cover -- that one bites on entering and on starting a turn, which are the
    other two moments."""
    ring = c.aura(2, label=c.ref, until=When.ENCOUNTER)

    def scorch(who: int) -> None:
        if who in c.enemies():
            c.flat(5, dtype=DamageType.FIRE, on=who)

    _ends_its_turn_in(c, ring, scorch)


@power(
    "m5698a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def m5698a1(c: Cast) -> None:
    """`c.cannot_shift` and not `c.immobilized`: it still walks, which is the
    whole distinction between the two."""
    c.cannot_shift(on=c.me, until=When.ENCOUNTER)


@power(
    "m5698a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE),
)
def m5698a2(c: Cast) -> None:
    """m5698a5 can make this slam carry a burn for a round; the hold it lays
    is read here rather than written into that row, because this is the row
    that swings."""
    if not c.strike():
        return
    c.hit()
    c.vulnerable(5, DamageType.FIRE, until=When.EONT)
    if any(eff.label == _M5698_SLAM_BURN for eff in c.world.effects.of(c.me)):
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5698a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m5698a3(c: Cast) -> None:
    """Two slams, each picking its own target from what is in reach: the
    printed line caps nothing and the damage stays in m5698a2."""
    for _ in range(2):
        prey = _foe_in_reach(c, 1)
        if prey is None:
            return
        c.use_power("m5698a2", on=prey, spend=False)


@power(
    "m5698a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 10, dtype=DamageType.FIRE),
)
def m5698a4(c: Cast) -> None:
    """"Creatures in the blast" is `EACH_OTHER`: it takes in the creature's
    own side, which `EACH_ENEMY` would not, and leaves out the creature at the
    blast's origin, which `EACH_CREATURE` would catch."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m5698a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5698a5(c: Cast) -> None:
    """The Effect half arms m5698a2 rather than being written into it: a hold
    with this row's own label, which that row reads when it swings. The
    recharge sentence is armed on top of the die the header rolls."""
    me = c.me
    if c.first:
        _recharge_on(
            c,
            DamageApplied,
            lambda ev: ev.target == me and ev.dtype is DamageType.FIRE,
        )
        c.effect(_M5698_SLAM_BURN, on=me, until=When.EONT)
    if c.strike():
        c.hit()


# ==========================================================================
# m5711
# ==========================================================================


@power(
    "m5711a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5711a0(c: Cast) -> None:
    """Only the cursed pay, and "dazed until the end of **its** next turn" is
    the victim's clock, which is `When.EOTNT`. The curse is asked as the turn
    closes rather than when the aura goes up, because a curse laid later has
    to count."""
    ring = c.aura(3, label=c.ref, until=When.ENCOUNTER)

    def daze(who: int) -> None:
        if who in c.enemies() and c.cursed(who):
            c.dazed(until=When.EOTNT, on=who)

    _ends_its_turn_in(c, ring, daze)


@power(
    "m5711a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 4),
)
def m5711a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5711a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 7),
)
def m5711a2(c: Cast) -> None:
    """`c.cursed` asks whether **this** caster cursed that creature, which is
    what the printed line means by "if the target is cursed"."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and c.cursed(victim):
        c.damage("1d10", dtype=DamageType.PSYCHIC, detail=c.ref)
    c.immobilized(until=When.EONT)


@power(
    "m5711a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("4d8", 7, kind=LIMITED),
)
def m5711a3(c: Cast) -> None:
    """"Instead" replaces the pull: a creature already dazed is stunned where
    it stands rather than hauled in. The new condition is applied on its own
    hold, not written over the daze's `conditions` -- that field is read once
    when an effect lands and once when it ends, and never in between."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.is_(Condition.DAZED, on=victim):
        c.stunned(until=When.EOTNT, on=victim)
    else:
        c.pull(5, on=victim)


@power(
    "m5711a4",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5711a4(c: Cast) -> None:
    c.shift(c.speed_of() + 2)


@power(
    "m5711a5",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    once_per_round=True,
)
def m5711a5(c: Cast) -> None:
    """No attack roll is printed, so there is no `attack=` and no
    `c.strike()`: the curse simply lands, and it is this caster's, which is
    what m5711a0 and m5711a2 read back."""
    c.curse(until=When.SAVE_ENDS)


@power(
    "m5711a6",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5711a6(c: Cast) -> None:
    """Narrative only: a disguise with no mechanical change, and an Insight
    check nothing on a board rolls."""
    c.note(f"{c.ref}: it takes the shape of some Medium humanoid")


# ==========================================================================
# m6088
# ==========================================================================

_M6088_STRUCK = "an adjacent enemy hits it with a melee attack"


@power(
    "m6088a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 12),
)
def m6088a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6088a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
    dropped=("c.aftereffect()",),
)
def m6088a1(c: Cast) -> None:
    """A borrowed swing, and domination only if that swing lands.

    `c.grant_attack` leaves its result in `c.landed`, which is what "if this
    attack hits" asks -- so the domination hangs on the borrowed blow and not
    on this row's own. "Charge or make a basic attack" is the victim's
    choice; the creature struck is this card's choice, which `on=` names.

    The Aftereffect is dropped twice over: it is a hold that lands when the
    first ends by a save, and "treats its allies as enemies for the purpose of
    opportunity attacks" has no switch -- `c.provoke` opens one window for one
    named creature and nothing turns a side around.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    span = _reach_of(c, victim)
    prey = sorted(
        who
        for who in (c.me, *c.allies())
        if who != victim and distance_between(c.world, victim, who) <= max(span, 1)
    )
    if not prey:
        return
    aimed = c.choose(prey, f"{c.ref}: who it is sent at")
    if aimed is None:
        return
    if c.may("charge rather than swing where it stands", who=victim):
        c.charge_at(aimed, who=victim)
    else:
        c.grant_attack(victim, on=aimed)
    if c.landed:
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


@power(
    "m6088a2",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=Ranged(5),
    target=Target(side="enemy", count=1, label="dominated by it"),
    keywords=[Keyword.CHARM],
    dropped=("Target.kind",),
)
def m6088a2(c: Cast) -> None:
    """No attack roll is printed: the slide is the whole Effect line. Being
    dominated is the target's own state, which `Target` cannot filter on."""
    victim = _restricted_to(c, 5, lambda f: c.is_(Condition.DOMINATED, on=f))
    if victim is not None:
        c.slide(3, on=victim)


@power(
    "m6088a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d6", 7, dtype=DamageType.FIRE),
    trigger=_M6088_STRUCK,
    on=Trigger(Hit, both(hits_me, by_melee), _M6088_STRUCK),
)
def m6088a3(c: Cast) -> None:
    """The Effect line is taken whether the riposte landed or not, and it is
    one jump or the other -- "itself **or** the target" is a choice, and
    taking both would move two creatures where the card moves one."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None or c.distance(attacker) > 1:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
    if c.may("send the enemy away rather than leave itself"):
        c.teleport(6, who=attacker)
    else:
        c.teleport(6)


# ==========================================================================
# m6141 -- the same card as m115753, printed twice. Its own refs, so its own
# rows.
# ==========================================================================


@power(
    "m6141a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 10),
)
def m6141a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m6141a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m6141a1(c: Cast) -> None:
    """The payout is watched rather than handed out now, because the printed
    line pays the *first* ally to hit while the stun is standing."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    stun = c.stunned(until=When.SAVE_ENDS, on=victim)
    if c.height(on=victim) > 0:
        c.fall(on=victim)
    if stun is None:
        return
    me, paid = c.me, [False]

    def reward(ev: Hit) -> None:
        if paid[0] or ev.target != victim or stun.ended:
            return
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        paid[0] = True
        c.heal(15, on=ev.attacker)

    watch = c.watch(Hit, reward, until=When.ENCOUNTER, on=me, label=f"{c.ref} bounty")
    stun.on_end.append(lambda: c.world.effects.end(watch, "the hold broke"))


@power(
    "m6141a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d10", 4, kind=LIMITED),
)
def m6141a2(c: Cast) -> None:
    """The Effect line lands whether the blow did or not, which is why the
    prone is outside the hit branch."""
    if c.strike():
        c.hit()
        c.push(2)
    c.prone()
    if not c.first:
        return
    for mate in sorted(c.in_squares(c.area(), side="ally")):
        if mate == c.me:
            continue
        c.shift(3, who=mate)
        _grant_melee_basic(c, mate)


# ==========================================================================
# m6186 -- a minion. Its single hit point is in the database, and
# `kind=MINION` is what says the damage number is flat because the creature
# is one, which is how it rescales.
# ==========================================================================


@power(
    "m6186a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("", 10, kind=MINION),
)
def m6186a0(c: Cast) -> None:
    """The Effect line is taken whether the bite landed or not."""
    if c.strike():
        c.hit()
    c.slide(2)


# ==========================================================================
# m6276
# ==========================================================================

_M6276_OUTLASTS = "an effect caused by one of her powers would end on her turn"


@power(
    "m6276a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d4", 9),
)
def m6276a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6276a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d8", 9, dtype=DamageType.PSYCHIC),
)
def m6276a1(c: Cast) -> None:
    """"Cannot make opportunity attacks against her" is the immunity sitting
    on **her**, narrowed to one attacker: `on=` is who never provokes and
    `from_=` is who is denied the opening, which is the one shape of
    `c.no_provoke` that can say a sentence like this."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.no_provoke(from_=victim, on=c.me, until=When.EONT)


@power(
    "m6276a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d10", 9, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.zone(obscured=)",),
)
def m6276a2(c: Cast) -> None:
    """"In the origin square of the burst" is `c.origin`, which is the square
    the area was aimed at and the only record of it.

    "Heavily obscured to enemies" is the dropped clause: `blocks_sight` is the
    one thing a zone says about seeing and it applies to everybody, with no
    degree and no side.
    """
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
        victim = c.target
        if victim is not None and c.origin in squares(c.world, victim):
            c.blinded(until=When.EONT, on=victim)
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.EONT)


@power(
    "m6276a3",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6276a3(c: Cast) -> None:
    """`at=` names the mode travelled at, which is what turns a walk into a
    climb -- and `c.moving_as` reads it back for anything that cares."""
    c.move(c.speed_of(), at="climb")


@power(
    "m6276a4",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m6276a4(c: Cast) -> None:
    """Her own exemption from the cloud is the dropped clause: `blocks_sight`
    applies to everybody and there is no way to leave one creature out."""
    _dark_cloud(c, until=When.EONT)


@power(
    "m6276a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires_text="she must be in a square of dim light or darkness",
    dropped=("query.light_level(world, square)",),
)
def m6276a5(c: Cast) -> None:
    """The jump is exact; both ends of the printed Requirement are the dropped
    clause. There is no light model, so neither where she stands nor where she
    lands can be asked -- which is also why the Requirement is not written as
    a `requires=`: a gate that is false when the row arms refuses it once and
    for good."""
    c.teleport(10)


@power(
    "m6276a6",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_has_a_hold_about_to_go,
    requires_text="one of her own effects must be about to run out",
    trigger=_M6276_OUTLASTS,
    on=Trigger(TurnStart, about_me, _M6276_OUTLASTS),
)
def m6276a6(c: Cast) -> None:
    """One of her holds lasts a round longer, and the latch is how.

    `Effects._on_turn_end` lets an `EONT` or `EOT` effect through once when
    `eff.latch` is set and clears the flag, which is exactly one extra round
    -- the same mechanism that stops a freshly applied hold expiring on the
    turn it landed. The start of her turn is the only moment the engine can
    see *which* of her effects are about to run out, which is why the trigger
    is declared there rather than on `EffectExpired`: that event carries a
    label and a reason and no effect to extend, and fires when it is already
    too late.
    """
    me = c.me
    about_to_go = [
        eff
        for eff in c.world.effects.live.values()
        if eff.source == me
        and eff.clock == me
        and eff.when in (When.EOT, When.EONT)
        and not eff.latch
    ]
    if not about_to_go:
        return
    about_to_go[0].latch = True
    c.note(f"{c.ref}: one of her effects lasts until the end of her next turn")


# ==========================================================================
# m6587
# ==========================================================================

_M6587_SHOT_AT = "an enemy makes a ranged attack against it"


@power(
    "m6587a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 9, dtype=DamageType.COLD),
)
def m6587a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m6587a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FORCE],
    attack=Attack(vs=REF, printed=16),
    dropped=("Damage(dtypes=)",),
)
def m6587a1(c: Cast) -> None:
    """A two-type damage line has nowhere to go in the header. "Vulnerable 5
    to all damage" is `c.vulnerable` with no type, and the opening is the
    whole enemy side of the victim, which from this creature's side is
    `team`."""
    if not c.strike():
        return
    c.damage(
        "2d8", 6,
        dtypes=(DamageType.COLD, DamageType.FORCE),
        detail=c.ref,
    )
    c.grants_advantage(until=When.EONT, to="team")
    c.vulnerable(5, until=When.EONT)


@power(
    "m6587a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 15, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
    dropped=("c.zone(obscured=)",),
)
def m6587a2(c: Cast) -> None:
    """The miss line is written out, because `half_on_miss=True` is declared
    data nothing in the engine reads. The zone's rough going is exact;
    "heavily obscured to enemies" is the dropped clause -- `blocks_sight` is
    all a zone says about seeing, and it has no side."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)


@power(
    "m6587a3",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6587_SHOT_AT,
    on=Trigger(AttackDeclared, both(targets_me, by_ranged), _M6587_SHOT_AT),
)
def m6587a3(c: Cast) -> None:
    """"Make the attack roll twice and use the lower result" is
    `c.reroll_attack(keep="worst")`, which reads the attack off `c.trigger`.
    Declared an interrupt, which is the only action that runs before the roll
    is read back."""
    c.reroll_attack(keep="worst")
