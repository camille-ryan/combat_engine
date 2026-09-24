"""Monster abilities, level 2: the brutes and the soldiers beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=6)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
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
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Defense,
    Effect,
    Health,
    Ident,
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AdjacencyLost,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_melee,
    enemy_within,
    leaves_me_out,
)

#: The four defences, for the rows whose penalty is to all of them at once.
ALL_DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)


def _same_row(c: Cast, who: int, ref: str) -> bool:
    """Is that creature another of this stat block?

    By id. A body is never told what anything is called, and `c.is_kind`
    answers about type words -- beast, natural -- which several different
    stat blocks share.
    """
    ident = c.world.get(who, Ident)
    return ident is not None and ident.ref == ref


def _crowd(c: Cast, victim: int, ref: str) -> int:
    """How many *more* of this stat block are pressed against that creature.

    The caster is left out: every one of these lines reads "each additional",
    and the caster is the one the count is additional to.
    """
    return sum(
        1
        for other in c.within(1, of=victim, side="ally")
        if other != c.me and _same_row(c, other, ref)
    )


def _taking_ongoing(c: Cast, who: int, dtype: DamageType) -> bool:
    """Is that creature already carrying ongoing damage of this type?"""
    return any(
        eff.ongoing is not None and eff.ongoing[1] is dtype
        for eff in c.world.effects.of(who)
    )


def _resist(c: Cast, dtype: DamageType, amount: int, *, until: When) -> None:
    """Shrug off `amount` of one damage type for a while.

    `Cast` has `vulnerable` and no opposite number, so this is written the
    same way it is: `Defences.resist` is what `resolve.deal_damage` reads,
    and the effect carries the undo.
    """
    defences = c.world.get(c.me, Defences) or c.world.add(c.me, Defences())
    had = defences.resist.get(dtype, 0)
    if amount <= had:
        return
    defences.resist[dtype] = amount

    def undo() -> None:
        if had:
            defences.resist[dtype] = had
        else:
            defences.resist.pop(dtype, None)

    c.world.effects.apply(c.me, c.me, until, label=f"{c.ref} resist", on_end=[undo])


# -- m258 -------------------------------------------------------------------


@power(
    "m258a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3),
)
def m258a0(c: Cast) -> None:
    """"1d10 + 3, or 1d10 + 9 beside an ally" is one die and two bonuses, so
    the smaller goes in the header where it rescales and the extra six rides
    on top when the company is there to earn it."""
    if c.strike():
        c.hit()
        if [a for a in c.within(2, side="ally") if a != c.me]:
            c.damage(bonus=6)


# -- m2830 ------------------------------------------------------------------


@power(
    "m2830a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2830a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the bite hung off turn starts.

    How many more of its kind are crowding the victim is asked when the turn
    starts rather than stored with the aura: the count changes every time
    anything moves, and a membership worked out once would be stale
    immediately.
    """
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def swarm(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) > 1:
            return
        c.flat(3 + 2 * _crowd(c, ev.actor, "m2830"), on=ev.actor)

    c.watch(TurnStart, swarm, until=When.ENCOUNTER, on=me, label="m2830a0")


@power(
    "m2830a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6"),
)
def m2830a2(c: Cast) -> None:
    """The crowd bonus is a second expression, so it is rolled on top of the
    declared damage rather than folded into it. What the target was already
    carrying is read *before* this row's own poison goes on, or every hit
    after the first would weaken.
    """
    if not c.strike():
        return
    already = _taking_ongoing(c, c.target, DamageType.POISON)
    c.hit()
    extra = _crowd(c, c.target, "m2830")
    if extra:
        c.damage(bonus=extra)
    c.ongoing(5, DamageType.POISON)
    if already:
        c.weakened(until=When.SAVE_ENDS)


# -- m2858 ------------------------------------------------------------------


@power(
    "m2858a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6", 2),
)
def m2858a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2858_BLOODIED = "the m2858 is first bloodied"


@power(
    "m2858a2",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6", 2),
    trigger=_M2858_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2858_BLOODIED),
)
def m2858a2(c: Cast) -> None:
    """m2858a1 once or twice, and `UpTo(2)` is what lets the two swings land
    on different creatures. The line is repeated here rather than fired
    through that row so each target gets its own roll; the damage stays a
    normal one because that is the line being repeated. "First bloodied" needs
    no guard -- `Bloodied` is emitted on the crossing and nowhere else.
    """
    if c.strike():
        c.hit()


_M2858_DROPS = "the m2858 drops to 0 hit points"


@power(
    "m2858a3",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.ZONE],
    trigger=_M2858_DROPS,
    on=Trigger(Dropped, when=about_me, text=_M2858_DROPS),
)
def m2858a3(c: Cast) -> None:
    """What is left of it is a cloud, and its own kind walk through it.

    `c.hazard` would be the whole row but it bites everything standing in the
    zone and the printed line spares demons, so the zone is laid down bare
    and given its teeth here -- including `hazard`'s once-per-turn latch,
    which is a rule of zones rather than of this one.
    """
    zone = c.zone(c.area(), until=When.SONT)
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if c.is_kind("demon", on=who) or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(5, dtype=DamageType.POISON, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    c.watch(ZoneEntered, entered, until=When.SONT, on=c.me, label="m2858a3")
    c.watch(TurnStart, began, until=When.SONT, on=c.me, label="m2858a3 turn")


# -- m300 -------------------------------------------------------------------


@power(
    "m300a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 6),
)
def m300a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the swing did."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m300a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 7, kind=LIMITED, half_on_miss=True),
)
def m300a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()
    else:
        c.hit(half=True)
        c.slowed()


@power(
    "m300a2",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m300a2(c: Cast) -> None:
    c.shift(1)


_M300_CROWDED = "an enemy moves to a square adjacent to the m300"


@power(
    "m300a3",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    # The printed line is two halves joined by "or"; only the second one is
    # declarable. An adjacent enemy *shifting* announces `Moved`, which says
    # nothing about what kind of move it was, so the shift half cannot be
    # told from a walk and is left out rather than fired on both.
    trigger="an enemy adjacent to the m300 shifts, or an enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, when=enemy_within(1), text=_M300_CROWDED),
)
def m300a3(c: Cast) -> None:
    c.shift(1)


# -- m3028 ------------------------------------------------------------------


@power(
    "m3028a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m3028a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()


@power(
    "m3028a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3, kind=LIMITED),
)
def m3028a1(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +4 is trimmed by hand the way
    `Attack.bonus_for` trims the header's, or the row would ignore whatever
    scaling the fight is being played on.
    """
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(4, c.level), FORT):
        c.damage("2d6", 3, dtype=DamageType.POISON)


@power(
    "m3028a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3028a2(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line says.

    The gate is asked at the moment of the roll rather than when the trait is
    armed, because who it is standing beside is the whole condition and it
    changes every turn.
    """
    c.bonus(
        "attack",
        2,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda _ctx: bool([a for a in c.within(1, side="ally") if a != c.me]),
    )


# -- m3029 ------------------------------------------------------------------


@power(
    "m3029a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6", 3),
)
def m3029a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3029a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=4),
)
def m3029a1(c: Cast) -> None:
    """All of the damage is ongoing, so there is no declared line to hit with."""
    if c.strike():
        c.ongoing(5, DamageType.POISON)


@power(
    "m3029a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 3, kind=LIMITED),
)
def m3029a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# -- m308 -------------------------------------------------------------------


@power(
    "m308a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m308a0(c: Cast) -> None:
    """An aura 1, biting at the end of a turn rather than the start of one --
    `c.hazard` does both ends and entry besides, which this line does not."""
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def scour(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(2, on=ev.actor)

    c.watch(TurnEnd, scour, until=When.ENCOUNTER, on=me, label="m308a0")


@power(
    "m308a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d8", 2),
)
def m308a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# -- m3101 ------------------------------------------------------------------


@power(
    "m3101a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m3101a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3101a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m3101a1(c: Cast) -> None:
    """The Hit line only. The printed Sustain Standard -- crush the held
    creature and feed on it -- has no hook to hang on: an effect can carry a
    `sustain_cost` but nothing runs when the cost is paid, so there is
    nowhere to put the damage and the healing. See the report."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3101a2",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3101a2(c: Cast) -> None:
    """Whoever it is holding comes along: the shift leaves them a square
    behind it, and a pull of 1 puts them back against it."""
    held = c.world.relations.targets(Relation.GRABBED_BY, c.me)
    if not c.shift(1):
        return
    for victim in held:
        c.pull(1, on=victim)


# -- m4810 ------------------------------------------------------------------


@power(
    "m4810a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4810a0(c: Cast) -> None:
    """An aura 1, and inside it an enemy is open to the whole side.

    `c.grants_advantage` hands the advantage to the caster alone and the
    printed line gives it to everybody, so the relation is applied once per
    ally, all on one effect that is torn down when the enemy steps out.
    Membership is kept by the two adjacency events rather than rescanned,
    which is how everything else that cares about standing next to something
    is written.
    """
    c.aura(1, until=When.ENCOUNTER)
    me = c.me
    exposed: dict[int, Effect] = {}

    def open_up(foe: int) -> None:
        if foe in exposed or foe not in c.enemies():
            return
        exposed[foe] = c.world.effects.apply(
            foe,
            me,
            When.ENCOUNTER,
            label="m4810a0",
            relations=[
                (Relation.GRANTS_CA_TO, foe, friend) for friend in (me, *c.allies())
            ],
        )

    def close_up(foe: int) -> None:
        effect = exposed.pop(foe, None)
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    def arrived(ev: AdjacencyGained) -> None:
        if ev.other == me:
            open_up(ev.actor)

    def departed(ev: AdjacencyLost) -> None:
        if ev.other == me:
            close_up(ev.actor)

    for foe in c.within(1, side="enemy"):
        open_up(foe)
    c.watch(AdjacencyGained, arrived, until=When.ENCOUNTER, on=me, label="m4810a0 in")
    c.watch(AdjacencyLost, departed, until=When.ENCOUNTER, on=me, label="m4810a0 out")


@power(
    "m4810a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d12", 5),
)
def m4810a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4810a2",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4810a2(c: Cast) -> None:
    """Five squares of shift, ending beside the nearest bloodied enemy.

    The destination is named rather than left to the decider, because the
    printed line names it. When nothing it can reach is actually adjacent to
    that creature it takes the closest square it can, which is the only
    sensible reading of a rush that falls short.
    """
    hurt = [e for e in c.enemies() if c.bloodied(e)]
    if not hurt:
        return
    quarry = min(hurt, key=c.distance)
    where = c.world.get(quarry, Position)
    options = c.world.reachable_squares(c.me, 5)
    if where is None or not options:
        return
    c.shift(5, to=min(options, key=lambda sq: distance(sq, where.square)))


#: The five damage types this creature learns from.
_M4810_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)

_M4810_SCALDED = "the m4810 takes acid, cold, fire, lightning, or thunder damage"


def _scalded(world: World, me: int, ev: DamageApplied) -> bool:
    """None of the ready-made predicates reads a damage type, and this row is
    about nothing else."""
    return ev.target == me and ev.amount > 0 and ev.dtype in _M4810_ELEMENTS


@power(
    "m4810a3",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4810_SCALDED,
    on=Trigger(DamageApplied, when=_scalded, text=_M4810_SCALDED),
)
def m4810a3(c: Cast) -> None:
    """Which type it learns is read off the event, so the row is one line
    rather than five."""
    ev = c.trigger
    if ev is not None:
        _resist(c, ev.dtype, 10, until=When.ENCOUNTER)


# -- m4862 ------------------------------------------------------------------


@power(
    "m4862a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4862a1(c: Cast) -> None:
    """Thunder rattles it apart for a moment.

    Four penalties rather than one: a modifier names a single defence, and
    "all defenses" is the four of them. Untyped, so they stack with anything
    else going wrong at the same time -- which `c.penalty` already does.
    """
    me = c.me

    def rattle(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.THUNDER or not ev.amount:
            return
        for which in ALL_DEFENCES:
            c.penalty(which, 2, until=When.EONT, on=me)

    c.watch(DamageApplied, rattle, until=When.ENCOUNTER, on=me, label="m4862a1")


@power(
    "m4862a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m4862a2(c: Cast) -> None:
    """"Cannot shift" is `c.rooted`, not `c.immobilized`: it still walks, and
    walking away is what this is meant to cost it."""
    if c.strike():
        c.hit()
        c.rooted()


_M4862_ALLY_HIT = "an enemy hits one of the m4862's allies with a melee attack"


@power(
    "m4862a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M4862_ALLY_HIT,
    # `enemy_within(1)` is not in the printed line; it is the row's own melee
    # 1 reach, asked before the offer rather than after, so the creature is
    # not offered a reaction it cannot reach. The ally has no printed range at
    # all and 10 squares stands in for the board.
    on=Trigger(
        Hit,
        when=both(by_melee, ally_within(10), enemy_within(1)),
        text=_M4862_ALLY_HIT,
    ),
)
def m4862a3(c: Cast) -> None:
    """No attack roll is printed -- the target simply goes down."""
    c.prone()


# -- m497 -------------------------------------------------------------------


@power(
    "m497a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m497a0(c: Cast) -> None:
    """A critical takes it apart outright.

    `Hit` is announced before the damage is rolled, so answering it takes the
    rest of the hit points off first and the critical's own damage lands on a
    thing that is already down -- which is the printed order, and is why this
    watches the hit rather than the damage.
    """
    me = c.me

    def shatter(ev: Hit) -> None:
        if ev.target != me or not ev.critical:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(Hit, shatter, until=When.ENCOUNTER, on=me, label="m497a0")


@power(
    "m497a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
)
def m497a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m497a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
)
def m497a2(c: Cast) -> None:
    """A grab and nothing else; the printed escape DC has nowhere to go, and
    `c.grab` uses the standard one."""
    if c.strike():
        c.grab()


# -- m5025 ------------------------------------------------------------------


@power(
    "m5025a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5025a0(c: Cast) -> None:
    """Turning your back on it costs you.

    `leaves_me_out` is the predicate a mark wants and it reads the whole
    target list of one power use, so a burst that catches this creature does
    not count as ignoring it. The bonuses are gated on the offender rather
    than applied flat, because they are against that enemy alone.
    """
    me = c.me

    def slighted(ev: AttackDeclared) -> None:
        if ev.attacker == me or not c.marked(on=ev.attacker):
            return
        if not leaves_me_out(c.world, me, ev):
            return
        offender = ev.attacker
        for what in ("attack", "damage"):
            c.bonus(
                what,
                4,
                until=When.EONT,
                on=me,
                when=lambda ctx, foe=offender: ctx.get("target") == foe,
            )

    c.watch(AttackDeclared, slighted, until=When.ENCOUNTER, on=me, label="m5025a0")


@power(
    "m5025a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
)
def m5025a1(c: Cast) -> None:
    """The mark is an Effect line and lands whether or not the swing did."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5025a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m5025a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5025_OPENING = "a bloodied enemy attacks the m5025 or an adjacent ally of the m5025"


def _bloodied_enemy_swings(world: World, me: int, ev: AttackDeclared) -> bool:
    """Written out because no ready-made predicate reads the attacker's
    health, and being bloodied is half of this printed sentence."""
    if team(world, ev.attacker) is team(world, me):
        return False
    health = world.get(ev.attacker, Health)
    if health is None or not health.bloodied:
        return False
    if ev.target == me:
        return True
    return team(world, ev.target) is team(world, me) and adjacent(world, me, ev.target)


@power(
    "m5025a3",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
    trigger=_M5025_OPENING,
    on=Trigger(AttackDeclared, when=_bloodied_enemy_swings, text=_M5025_OPENING),
)
def m5025a3(c: Cast) -> None:
    """m5025a1, with a stun on top. The line is repeated rather than fired
    through that row because `use` reports whether the power went off and not
    whether it landed, and the stun needs to know. Its Effect line comes too:
    "uses" means the whole row, mark included.
    """
    if c.strike():
        c.hit()
        c.stunned(until=When.EOTNT)
    c.mark()


# -- m77 --------------------------------------------------------------------


@power(
    "m77a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m77a0(c: Cast) -> None:
    """The extra die against something already down is a second expression, so
    it is rolled in the body and the header keeps the line that rescales."""
    if c.strike():
        c.hit()
        if c.is_(Condition.PRONE):
            c.damage("1d6")


@power(
    "m77a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=3),
)
def m77a1(c: Cast) -> None:
    """Knocks down and does nothing else, which is what sets up m77a0."""
    if c.strike():
        c.prone()
