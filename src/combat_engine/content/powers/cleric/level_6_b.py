"""Cleric, level 6: the utilities printed after the first book.

`level_6.py` holds the four that came first; these are the rest, and there
is still not an attack roll in the level.

Three notes apply across the batch.

**Skill bonuses are not content.** Two of these rows spend a clause on
Insight, Perception or a conversation with a corpse, and the engine has no
skills and no conversation. Those clauses are dropped rather than
approximated; in each case the row has combat content besides, so none of
them is `out_of_combat`.

**"+1, or +2 if bloodied" is one bonus at two sizes.** `p7409` works the
size out before it applies anything, because two power bonuses of the same
kind do not add -- a +1 and a gated +1 would come to +1 forever and look
exactly like an aura that worked.

**`p9985` names a class feature.** What that feature leaves behind is a
standing save modifier on the cleric lasting exactly the turn the printed
line asks about, so the row reads the modifier off the caster rather than
reaching for an id.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    DamageType,
    Died,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Moved,
    Position,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    When,
    Window,
    distance,
    enemy_within,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import DamageApplied
from combat_engine.engine.query import team
from combat_engine.engine.zones import Zone

DIVINE = [Keyword.DIVINE]
DIVINE_HEALING = [Keyword.DIVINE, Keyword.HEALING]

_ENEMY_DIES = "an enemy dies within 5 squares of you"


@power(
    "p10089",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p10089(c: Cast) -> None:
    c.temp_hp(5 + c.wis_mod)
    c.bonus(WILL, 2, until=When.ENCOUNTER, kind="power")


@power(
    "p12612",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.ZONE],
)
def p12612(c: Cast) -> None:
    """The light is the whole of the row here: the +5 to two skill checks
    has nowhere to go.

    The burn answers the declaration, which is what "when any enemy in the
    zone makes an attack" reads -- an enemy that steps out and swings from
    outside pays nothing, and one that swings and then leaves has already
    paid.
    """
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def glare(ev: AttackDeclared) -> None:
        if ev.attacker in c.world.zones.occupants(zone) and ev.attacker in c.enemies():
            c.flat(5, dtype=DamageType.RADIANT, on=ev.attacker)

    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.append(c.world.bus.on(AttackDeclared, glare, owner=c.me))


@power(
    "p12613",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=DIVINE,
)
def p12613(c: Cast) -> None:
    """Two different things granted, so two modifiers: an attack bonus and a
    damage bonus are different `what`s and do not contend."""
    victim = c.target
    if victim is None:
        return

    def at_the_target(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    for friend in sorted({c.me, *c.allies()}):
        for what in ("attack", "damage"):
            c.bonus(
                what,
                2,
                on=friend,
                until=When.ENCOUNTER,
                kind="power",
                when=at_the_target,
            )


@power(
    "p13926",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.ZONE],
)
def p13926(c: Cast) -> None:
    """The damage bonus is gated on where the *victim* is standing at the
    moment the blow lands, not on where it stood when the zone was laid.

    `query.enemies` leaves the dead out, so the creature that just dropped
    can never be found in it; the side is compared directly instead.
    """
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
    mine = team(c.world, c.me)

    def inside(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who in c.world.zones.occupants(zone)

    for friend in sorted({c.me, *c.allies()}):
        c.bonus("damage", 2, on=friend, until=When.ENCOUNTER, kind="power", when=inside)

    def fell(ev: Dropped) -> None:
        here = c.world.zones.occupants(zone)
        if ev.actor not in here or team(c.world, ev.actor) is mine:
            return
        for friend in here:
            if team(c.world, friend) is mine:
                c.heal(5, on=friend)

    c.watch(Dropped, fell, until=When.ENCOUNTER, label=c.ref)


@power(
    "p13927",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    trigger=_ENEMY_DIES,
    on=Trigger(Died, when=enemy_within(5), text=_ENEMY_DIES),
)
def p13927(c: Cast) -> None:
    """Three benefits, of which two are conversation and scenery.

    The printed line banks the choice against a later minor action and an
    extended rest, neither of which a fight has a clock for, so it is taken
    now. The one benefit with combat content is offered first: `World.decide`
    takes the head of the list when nobody is playing, so the order of the
    options is the decision for every headless fight.
    """
    boon = c.choose(
        ["a bonus to your next attack roll", "an answer", "a place it saw"],
        "what the dead enemy gives up",
    )
    if boon == "a bonus to your next attack roll":
        c.bonus("attack", 5, on=c.me, until=When.ENCOUNTER, kind="power", once=True)
    else:
        c.note(f"{c.ref}: {boon}")


@power(
    "p2834",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=[Keyword.DIVINE, Keyword.FIRE, Keyword.RADIANT],
)
def p2834(c: Cast) -> None:
    """"Fire and radiant damage" is one roll of two types and a damage type
    holds one, so the first printed is kept and both keywords are declared
    -- which is what a row reading "resistance to fire" looks at.

    The die is rolled when the blow lands rather than now: `c.bonus` carries
    a number, and rolling it at cast time would give the same extra on every
    seed.
    """
    friend = c.target
    if friend is None:
        return

    def flares(ev: Hit) -> None:
        if ev.attacker == friend:
            c.flat(c.roll("1d6"), dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, flares, until=When.ENCOUNTER, on=friend, once=True, label=c.ref)


@power(
    "p3468",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, *DIVINE_HEALING],
)
def p3468(c: Cast) -> None:
    """`speed=4` is the printed move action: `actions` offers a
    conjuration's creator the walk, and four squares is what the line
    allows.

    The watch hangs on the spirit's own effect, so sustaining keeps it and
    letting the spirit go takes it with it. `c.adjacent_to` counts the
    spirit's own square as adjacent to itself, which is the other half of
    the printed "in the spirit's square or adjacent to it".

    The squares are offered closest to somebody it can mend first, because
    `World.decide` takes the head of the list when nobody is playing and the
    plain sorted order put the spirit in a corner every time.
    """
    friends = [
        standing.square
        for standing in (c.world.get(f, Position) for f in (c.me, *c.allies()))
        if standing is not None
    ]
    free = [
        sq
        for sq in spread({c.here}, 10) - {c.here}
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    room = sorted(
        free, key=lambda sq: (min((distance(sq, f) for f in friends), default=0), sq)
    )
    where = c.choose(room, "where the spirit stands") if room else None
    if where is None:
        return
    spirit = c.conjure(where, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=4)
    if not spirit:
        return

    def mends(ev: Hit) -> None:
        if ev.attacker != c.me and ev.attacker not in c.allies():
            return
        if ev.target in c.enemies() and c.adjacent_to(spirit, ev.attacker):
            c.heal(c.wis_mod, on=ev.attacker)

    conj = c.world.get(spirit, Conjuration)
    held = c.world.effects.live.get(conj.effect) if conj is not None else None
    if held is not None:
        held.subs.append(c.world.bus.on(Hit, mends, owner=c.me))


@power(
    "p488",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=DIVINE_HEALING,
)
def p488(c: Cast) -> None:
    """A printed "can" for the surge, so the target is asked when the moment
    comes rather than now."""
    friend = c.target
    if friend is None:
        return
    c.bonus("attack", 2, until=When.ENCOUNTER, kind="power")
    c.bonus("damage", 2, until=When.ENCOUNTER, kind="power")

    def first_blood(ev: Bloodied) -> None:
        if ev.actor == friend and c.may("spend a healing surge", who=friend):
            c.surge(on=friend)

    c.watch(Bloodied, first_blood, until=When.ENCOUNTER, on=friend, once=True,
            label=c.ref)


@power(
    "p7092",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE_HEALING,
)
def p7092(c: Cast) -> None:
    """A wound the cleric keeps open on purpose.

    The burn is built here rather than through `c.ongoing` for one reason:
    `c.ongoing` labels the hold by its size, and both listeners below have
    to tell *this* burn from any other the cleric might be carrying. The
    label goes into the effect's `str`, which is what a saving throw is
    announced against and what the ongoing damage carries as its detail.

    Declining the saving throw is the default answer, because that is what
    the row is for: a cleric who saves has stopped paying out.

    "This damage can't be reduced in any way" has no spelling -- resistance
    is subtracted inside `deal_damage`, below anything a row can reach -- so
    a cleric with resistance would bleed for less than the printed 5.
    """
    me = c.me
    burn = c.world.effects.apply(
        me, me, When.SAVE_ENDS, label=c.ref, ongoing=(5, DamageType.UNTYPED)
    )

    def refuse(ev: SavingThrow) -> None:
        if ev.actor == me and c.ref in ev.against and c.may("keep the wound open", who=me):
            ev.cancel(c.ref)

    def pays(ev: DamageApplied) -> None:
        if ev.target != me or c.ref not in (ev.detail or ""):
            return
        friends = sorted(f for f in c.within(5, side="ally") if f != me)
        who = c.choose(friends, "who the wound mends") if friends else None
        if who is not None:
            c.heal(15, on=who)

    burn.subs.append(
        c.world.bus.on(SavingThrow, refuse, window=Window.BEFORE, owner=me)
    )
    burn.subs.append(c.world.bus.on(DamageApplied, pays, owner=me))


@power(
    "p7409",
    level=6,
    cls="cleric",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p7409(c: Cast) -> None:
    """"At any point during this move" is read off every step, not off where
    the cleric stops: the neighbours are collected before the walk and again
    after each `Moved`, and the bonus is handed out at the end."""
    amount = 2 if c.bloodied(on=c.me) else 1
    beside = {a for a in c.within(1, side="ally") if a != c.me}

    def passing(ev: Moved) -> None:
        if ev.actor == c.me:
            beside.update(a for a in c.within(1, side="ally") if a != c.me)

    sub = c.world.bus.on(Moved, passing, owner=c.me)
    try:
        c.move(c.speed_of())
    finally:
        c.world.bus.off(sub)
    for friend in sorted(beside):
        c.bonus(AC, amount, on=friend, until=When.EONT, kind="power")


@power(
    "p9985",
    level=6,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE,
)
def p9985(c: Cast) -> None:
    """"The bonus your <feature> grants" is read off the caster, not off an
    id: what that feature leaves behind is a standing save modifier on the
    cleric whose duration is the same turn the printed line asks about, so
    the modifier and the condition are the same question."""
    c.save(on=c.target, bonus=max(0, c.total("save", on=c.me)))
