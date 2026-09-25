"""Warlock, level 10: utility. Four personal rows, no attack.

`p1328` is declared on `DamageRolled` rather than on the printed `Hit`, the
same seam `fighter/level_6.py` uses: the amount is on the event and mutable,
and the emitter reads it back once the window closes, so a reaction can
empty it. `targets_me` alone would also answer ongoing damage and a hazard,
and the line says "by an attack".

`p95` is the level's polymorph. "Can't take standard actions" is
`Condition.SHAPED`, the one card in the table that means exactly that, and
`revert=MINOR` is the printed way out.

`p1296` is a message carried a hundred miles and brought back. The board has
no distance like that and no conversation, so it is declared inert.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
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
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Event,
    Healed,
    Hit,
    Keyword,
    Miss,
    Mod,
    Movement,
    Ranged,
    Trigger,
    TurnStart,
    When,
    World,
    ZoneEntered,
    by_me,
    cursed_by_me,
    distance,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import DamageRolled, MoveEnd, SurgeSpent
from combat_engine.engine.query import distance_between, team

ARCANE = [Keyword.ARCANE]

_HURT_BY_AN_ATTACK = "you are hit and damaged by an attack"
_MISSED_ME = "an enemy misses you with an attack"
_I_MISSED = "you miss an enemy with an attack"
_ALLY_SPENDS_A_SURGE = "an ally within 10 squares spends a healing surge"
_AN_ALLY_HEALS_ME = "an ally grants you the use of a healing surge"
_CURSED_DROPS = "an enemy you have cursed drops to 0 hit points or fewer"


def _attack_damaged_me(world: World, me: int, ev: Event) -> bool:
    """Damage aimed at me that a declared row dealt."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and get(getattr(ev, "detail", "")) is not None
    )


def _ally_surge_near(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return (
        who is not None
        and who != me
        and team(world, who) is team(world, me)
        and distance_between(world, who, me) <= 10
    )


def _ally_healed_me(world: World, me: int, ev: Event) -> bool:
    source = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and source is not None
        and source != me
        and getattr(ev, "amount", 0) > 0
    )


@power(
    "p1296",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(100),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p1296(c: Cast) -> None:
    c.note("p1296: a spoken message delivered far off, and the reply brought back")


@power(
    "p1328",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HURT_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_attack_damaged_me, text=_HURT_BY_AN_ATTACK),
)
def p1328(c: Cast) -> None:
    ev = c.trigger
    if ev is None:
        return
    spared = getattr(ev, "amount", 0)
    ev.amount = 0
    c.note(f"p1328: {spared} damage comes to nothing")


@power(
    "p662",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p662(c: Cast) -> None:
    """"You do not need line of sight" needs no saying: `c.teleport` offers
    every square within range that the warlock would fit in, and checks
    nothing about seeing it. "If you attempt to teleport to a space you
    can't occupy, you don't move" is the same filter from the other side."""
    c.teleport(6)


@power(
    "p95",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p95(c: Cast) -> None:
    """"Until the end of the encounter or for 5 minutes" is one duration on
    this board: the encounter is the only clock there is."""
    c.form(
        conditions=(Condition.INSUBSTANTIAL, Condition.SHAPED),
        modes={"fly": 6},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )


@power(
    "p10385",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.TELEPORTATION],
)
def p10385(c: Cast) -> None:
    # The infernal rider is concealment, which the board does not model.
    friend = c.target
    if friend is None:
        return
    c.flat(c.level // 2, dtype=DamageType.FIRE, on=friend)
    c.teleport(5, who=friend)


@power(
    "p12896",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=targets_me, text=_MISSED_ME),
)
def p12896(c: Cast) -> None:
    """The flight is a granted mode and an ordinary move: `mode_of` picks the
    way a creature travels and nothing forces it into the air, so what is
    guaranteed here is the speed and the insubstantiality, not the altitude.
    """
    pace = c.speed_of()
    c.mode("fly", pace, on=c.me, until=When.EOT)
    c.insubstantial(on=c.me, until=When.EOT)
    c.move(pace)
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.curse(on=foe)


@power(
    "p13650",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p13650(c: Cast) -> None:
    """The secondary carries no id of its own in the spec, so there is no row
    to hand over with `c.grant_row`: it is armed here instead, and fires
    rather than being offered. Once a round, which is what an immediate
    action costs however at-will it is.
    """
    spent = [-1]

    def blink(ev: AttackDeclared) -> None:
        if ev.target != c.me or spent[0] == c.world.round:
            return
        spent[0] = c.world.round
        c.teleport(3)

    c.watch(AttackDeclared, blink, until=When.ENCOUNTER)


@power(
    "p13652",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p13652(c: Cast) -> None:
    """A zone blocks sight for everybody or for nobody, so "for all creatures
    except you" is the half that is not written; the darkvision has nothing
    to be dark for."""
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.SUSTAIN, blocks_sight=True, sustain=MINOR)


@power(
    "p13653",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p13653(c: Cast) -> None:
    """The reach is read off the row that hit, because a damage context
    carries no such thing."""
    c.mode("fly", 6, on=c.me, until=When.ENCOUNTER)

    def sting(ev: Hit) -> None:
        if ev.target != c.me:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind == "melee":
            c.flat(5, on=ev.attacker)

    c.watch(Hit, sting, until=When.ENCOUNTER)


@power(
    "p13888",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p13888(c: Cast) -> None:
    """The way out is `drop_cost`, and what follows it hangs on `on_end`.

    Going unseen is `c.hide` rather than `c.invisible`: the printed line ends
    it on the next attack roll as well as on a clock, and being hidden is
    the state that attacking breaks.
    """

    def slip() -> None:
        c.teleport(5)
        c.hide(until=When.EONT)

    c.world.effects.apply(
        c.me,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        mods=[
            (c.me, Mod(what=d.value, value=2, kind="power", label=c.ref))
            for d in (AC, FORT, REF, WILL)
        ],
        drop_cost=MINOR,
        on_end=[slip],
    )
    c.note(f"{c.ref}: a +2 power bonus to going unnoticed, which nothing rolls")


@power(
    "p13957",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p13957(c: Cast) -> None:
    """"A move of at least 3 squares" is measured from where the turn began.

    `MoveEnd` says where the creature stopped and not how far it came, so
    the mark is reset at the start of each turn and again every time the
    offer is taken -- which is what makes a second move on the same turn
    have to cover the ground again.
    """
    mark = {"at": c.here}

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == c.me:
            mark["at"] = c.here

    def stepped(ev: MoveEnd) -> None:
        if ev.actor != c.me or c.turn_of() != c.me:
            return
        if distance(ev.at, mark["at"]) >= 3 and c.may("fade", who=c.me):
            c.insubstantial(on=c.me, until=When.SONT)
            mark["at"] = ev.at

    c.watch(TurnStart, began, until=When.ENCOUNTER)
    c.watch(MoveEnd, stepped, until=When.ENCOUNTER)


@power(
    "p16266",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p16266(c: Cast) -> None:
    """The extra squares of shift are not written: `actions.legal` offers a
    shift from a ring fixed at one square and nothing reads a modifier
    there, so there is no number to raise -- the same gap `ranger/level_10.py`
    records. A swimmer is exempt, which is a question about `Movement.modes`
    rather than about how it happens to be travelling.
    """
    area = c.area()
    if not area:
        return
    mist = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def clings(who: int) -> None:
        swim = c.world.get(who, Movement)
        if swim is not None and swim.modes.get("swim"):
            return
        c.slowed(on=who, until=When.SOTNT)

    for foe in c.in_squares(area, side="enemy"):
        clings(foe)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == mist and ev.actor in c.enemies():
            clings(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)


@power(
    "p4120",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HURT_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_attack_damaged_me, text=_HURT_BY_AN_ATTACK),
)
def p4120(c: Cast) -> None:
    """The same seam `p1328` uses: the amount rides the event and is still
    mutable, so the blow is emptied and half of it comes back slowly."""
    ev = c.trigger
    if ev is None:
        return
    spared = getattr(ev, "amount", 0)
    if spared <= 0:
        return
    ev.amount = 0
    c.ongoing(
        max(1, spared // 2), getattr(ev, "dtype", DamageType.UNTYPED), on=c.me
    )


@power(
    "p4125",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE,
    trigger=_I_MISSED,
    on=Trigger(Miss, when=by_me, text=_I_MISSED),
)
def p4125(c: Cast) -> None:
    """The one that was missed, off the event -- the header's target line is
    what the card prints and the dispatcher aims this wherever it likes."""
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is not None:
        c.penalty("save", 5, on=foe, until=When.EONT)


@power(
    "p4126",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    trigger=_ALLY_SPENDS_A_SURGE,
    on=Trigger(SurgeSpent, when=_ally_surge_near, text=_ALLY_SPENDS_A_SURGE),
)
def p4126(c: Cast) -> None:
    """"The amount the triggering ally regains" is that ally's surge value:
    `SurgeSpent` carries who spent it and how many are left, not what it
    healed, and a surge is a quarter of a maximum either way."""
    who = getattr(c.trigger, "actor", None)
    c.heal(c.surge_value(of=who) if who is not None else c.surge_value(), on=c.me)


@power(
    "p4288",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    trigger=_AN_ALLY_HEALS_ME,
    on=Trigger(Healed, when=_ally_healed_me, text=_AN_ALLY_HEALS_ME),
)
def p4288(c: Cast) -> None:
    """The price -- dying on the second failed death save rather than the
    third -- is not written: `Health.failures` is counted against a constant
    and no row can move it."""
    c.heal(c.surge_value(), on=c.me)


@power(
    "p5922",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5922(c: Cast) -> None:
    step = max(1, c.int_mod)
    c.bonus("speed", step, on=c.me, until=When.ENCOUNTER)
    c.bonus("save", step, on=c.me, until=When.ENCOUNTER)


@power(
    "p6956",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC],
    trigger=_CURSED_DROPS,
    on=Trigger(Dropped, when=cursed_by_me, text=_CURSED_DROPS),
)
def p6956(c: Cast) -> None:
    """The standing effect begins now; the drop that armed it is the trigger
    and is not paid out twice."""

    def wash(ev: Dropped) -> None:
        if not c.cursed(ev.actor):
            return
        for foe in c.within(1, of=ev.actor, side="enemy"):
            if foe != ev.actor:
                c.flat(10, dtype=DamageType.NECROTIC, on=foe)

    c.watch(Dropped, wash, until=When.ENCOUNTER)


@power(
    "p7404",
    level=10,
    cls="warlock",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p7404(c: Cast) -> None:
    c.teleport(1)
