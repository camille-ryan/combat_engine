"""Warlock, level 6: utility. The first four are personal, and none attacks.

`p1368` walks the path itself rather than calling `c.move`, because the
whole of its printed line is *how* the warlock is moving: `mode_of` never
picks "climb" on its own, so a granted climb speed alone would have left it
walking, and `c.moving_as("climb")` -- which is what a climbing rider reads
-- would have stayed false.

`p1402` puts its three modifiers on one effect so that the printed "you can
end this effect as a minor action" ends all three together, which is what
`drop_cost` is for.

The rows from the later books follow. Four of them are immediate actions
answering a miss, a wound or a surge, and each declares its Trigger with
`on=` rather than quoting it. `p10383` answers `DamageRolled` rather than
the `Hit` its Trigger names, the seam `level_10.py`'s `p1328` settled:
`c.absorb` reads the amount off that event and moves it, and there is no
number to move before it is rolled.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackRolled,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Ranged,
    Trigger,
    When,
    World,
    by_me,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import ConditionApplied, DamageRolled, SurgeSpent
from combat_engine.engine.movement import walk
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

ARCANE = [Keyword.ARCANE]

_A_ROLL_I_DISLIKE = "you make a roll you dislike"
_MISSED_ME = "an enemy misses you with an attack"
_DAMAGED_BY_AN_ATTACK = "you are damaged by an attack"
_ALLY_HURT = "an ally within 10 squares takes damage"
_SOMEBODY_SPENDS_A_SURGE = "a creature within 10 squares spends a healing surge"


def _ally_damaged_near(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    return (
        who is not None
        and who != me
        and getattr(ev, "amount", 0) > 0
        and team(world, who) is team(world, me)
        and distance_between(world, who, me) <= 10
    )


def _surge_near(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return who is not None and distance_between(world, who, me) <= 10


def _damaged_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "amount", 0) > 0


@power(
    "p1326",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_A_ROLL_I_DISLIKE,
    on=Trigger(AttackRolled, when=by_me, text=_A_ROLL_I_DISLIKE),
)
def p1326(c: Cast) -> None:
    """"Using the higher of the two results" is `keep="best"`.

    Declared on the attack roll only. The printed line also offers a skill
    check, an ability check and a saving throw: the first two are not rolled
    by this engine at all, and `SavingThrow` is announced after the effect
    has already been judged, so there is nothing left to reroll.
    """
    if c.reroll_attack(keep="best"):
        c.note("p1326: the die is thrown again and the better face stands")


@power(
    "p1368",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p1368(c: Cast) -> None:
    pace = c.speed_of()
    c.mode("climb", pace, until=When.EOT)
    paths = c.world.reachable_paths(c.me, pace)
    if not paths:
        return
    dest = c.world.decide(c.me, "move", sorted(paths), f"{c.ref}: climb {pace}")
    walk(c.world, c.me, paths[dest], mode="climb")


@power(
    "p1402",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p1402(c: Cast) -> None:
    c.world.effects.apply(
        c.me,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        mods=[
            (c.me, Mod(what=AC.value, value=2, kind="power", label=c.ref)),
            (c.me, Mod(what=FORT.value, value=2, kind="power", label=c.ref)),
            (c.me, Mod(what="speed", value=-2, kind="untyped", label=c.ref)),
        ],
        drop_cost=MINOR,
    )


@power(
    "p2264",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p2264(c: Cast) -> None:
    """"Willing" is why the ally is asked before the two of them move."""
    friend = c.target
    if friend is not None and c.may("trade places", who=friend):
        c.swap(friend)


@power(
    "p10352",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=targets_me, text=_MISSED_ME),
)
def p10352(c: Cast) -> None:
    """The penalty is spent only on attacks aimed at the warlock, which is
    what the attack context's `target` key is for."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.curse(on=foe)
    c.penalty(
        "attack",
        2,
        on=foe,
        until=When.EONT,
        when=lambda ctx: ctx.get("target") == c.me,
    )
    c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p10383",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    trigger=_DAMAGED_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_damaged_me, text=_DAMAGED_BY_AN_ATTACK),
)
def p10383(c: Cast) -> None:
    """"You still take any other effects from the attack" needs no saying:
    only the number moves, and the conditions the attack carries are applied
    by the row that rolled it, to whoever it named."""
    friend = c.target
    if friend is None or not c.may("take the blow"):
        return
    c.absorb(on=friend)
    c.bonus("attack", 2, on=friend, kind="power", until=When.EONT)
    c.bonus("damage", 5, on=friend, kind="power", until=When.EONT)
    if c.build("infernal"):
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 2, on=friend, kind="power", until=When.EONT)


@power(
    "p12893",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p12893(c: Cast) -> None:
    """Both halves ride one sustained hold so that keeping the shape keeps
    the price with it. Slipping through a keyhole has no board to do it on."""
    thin = c.world.effects.apply(
        c.me,
        c.me,
        When.SUSTAIN,
        label=c.ref,
        sustain_cost=MINOR,
        conditions=(Condition.INSUBSTANTIAL,),
    )
    barred = c.cannot_attack(on=c.me, until=When.SUSTAIN)
    if barred is not None:
        thin.on_end.append(lambda: c.world.effects.end(barred, "the shape ended"))


@power(
    "p13646",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p13646(c: Cast) -> None:
    # Darkvision and two skill bonuses: no light model and no checks, so
    # there is nothing here for a fight to notice.
    c.note("p13646: darkvision, and a +2 power bonus to noticing things")


@power(
    "p13648",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p13648(c: Cast) -> None:
    c.resist(5, on=c.me, until=When.EONT)
    c.immovable(on=c.me, until=When.EONT)


@power(
    "p13885",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p13885(c: Cast) -> None:
    """Ending the step inside an enemy's space is `share=True`, and being
    carried along when it moves is the mount relation -- which is what
    `c.ride` does and is the only thing on the surface that says it.

    "At the start of your next turn you appear in the nearest unoccupied
    square" is not written: nothing evicts a rider on a clock.
    """
    c.no_provoke(until=When.EOT)
    c.shift(2, share=True)
    here = c.here
    inside = [f for f in c.enemies() if here in squares_of(c.world, f)]
    if inside:
        c.ride(on=inside[0])


@power(
    "p13886",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p13886(c: Cast) -> None:
    """Both states are put up before the step and clocked to the end of this
    turn, which is the nearest thing to "during this shift"."""
    c.phasing(on=c.me, until=When.EOT)
    c.insubstantial(on=c.me, until=When.EOT)
    c.shift(10)


@power(
    "p13956",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION, Keyword.TELEPORTATION],
)
def p13956(c: Cast) -> None:
    """The shade occupies its square, which is the clause only a conjuration
    can say. Attacking from its space is not written -- nothing on the
    surface moves a row's origin -- and neither is the aftereffect
    teleport, which waits on the shade being destroyed."""
    room = sorted(
        sq
        for sq in spread({c.here}, 5)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not room:
        return
    c.conjure(at=room[0], label=c.ref, until=When.EONT, sustain=None)
    c.insubstantial(on=c.me, until=When.EONT)


@power(
    "p16265",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p16265(c: Cast) -> None:
    """One type, chosen when the row is used, and the lash reads the same
    choice. "During your turn" is asked of whose turn it is when the blow
    lands, which `c.turn_of` answers."""
    kinds = [
        DamageType.ACID,
        DamageType.COLD,
        DamageType.FIRE,
        DamageType.LIGHTNING,
        DamageType.THUNDER,
    ]
    dtype = c.choose(kinds, f"{c.ref}: which element") or DamageType.FIRE
    c.resist(10, dtype, on=c.me, until=When.ENCOUNTER)

    def lash(ev: Hit) -> None:
        if ev.target != c.me or c.turn_of() != c.me:
            return
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 5)
        mark = c.choose(pool, f"{c.ref}: who the element finds") if pool else None
        if mark is not None:
            c.flat(c.con_mod, dtype=dtype, on=mark)

    c.watch(Hit, lash, until=When.ENCOUNTER)


@power(
    "p1924",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=targets_me, text=_MISSED_ME),
)
def p1924(c: Cast) -> None:
    # Printed for a melee *or* a ranged miss, which between them is every
    # attack the engine has a reach for, so the pair is left unsplit.
    c.teleport(max(1, c.cha_mod))


@power(
    "p4083",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p4083(c: Cast) -> None:
    # The Stealth half has nothing to modify, and the dark pact rider is
    # about a class feature's distance rather than anything a row holds.
    c.bonus("save", 2, on=c.me, kind="power", until=When.ENCOUNTER)


@power(
    "p4085",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p4085(c: Cast) -> None:
    """"Cannot be marked" and "escapes a grab automatically" are written as
    one watch that undoes either the moment it lands, which is the same
    thing from the far side. Counting as Tiny for squeezing has no number.
    """

    def slip(ev: ConditionApplied) -> None:
        if ev.target != c.me or ev.condition not in (Condition.MARKED, Condition.GRABBED):
            return
        for held in list(c.world.effects.of(c.me)):
            if ev.condition in held.conditions:
                c.world.effects.end(held, "it does not hold")

    c.watch(ConditionApplied, slip, until=When.ENCOUNTER)


@power(
    "p4087",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    trigger=_ALLY_HURT,
    on=Trigger(DamageApplied, when=_ally_damaged_near, text=_ALLY_HURT),
)
def p4087(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, kind="power", until=When.EONT, once=True)
    # The dark pact leg would heal the warlock for its Charisma modifier.


@power(
    "p4283",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(10),
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    trigger=_SOMEBODY_SPENDS_A_SURGE,
    on=Trigger(SurgeSpent, when=_surge_near, text=_SOMEBODY_SPENDS_A_SURGE),
)
def p4283(c: Cast) -> None:
    """Declared on the surge alone: an action point is not a thing the
    engine spends, so the other half of the printed Trigger has no event.
    A second wind heals a surge's worth, which is what `c.surge_value` is."""
    c.temp_hp(c.surge_value(), on=c.me)


@power(
    "p4284",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.FEAR, Keyword.IMPLEMENT],
    out_of_combat=True,
)
def p4284(c: Cast) -> None:
    # Questions put to a helpless prisoner. Nothing here is a fight.
    c.note(f"p4284: {1 + c.cha_mod} questions answered truthfully, while it stays helpless")


@power(
    "p5918",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5918(c: Cast) -> None:
    c.move(2 * c.speed_of())
