"""Shaman, level 2 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    ActionType,
    AdjacencyLost,
    AreaBurst,
    Cast,
    CloseBurst,
    Companion,
    DamageRolled,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnStart,
    When,
    about_me,
    power,
)
from combat_engine.engine.ecs import World
from combat_engine.engine.events import InitiativeRolled
from combat_engine.engine.query import distance_between, team

from ._spirit import beside_spirit, friends, send_spirit

PRIMAL = [Keyword.PRIMAL]


def ally_damaged_within_10(world: World, me: int, ev: Any) -> bool:
    """An ally -- not me -- within 10 squares is about to take damage."""
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if team(world, who) != team(world, me):
        return False
    return distance_between(world, me, who) <= 10


def stepped_away_from_spirit(world: World, me: int, ev: Any) -> bool:
    """An enemy stopped standing beside my spirit.

    The printed trigger also asks that the enemy *started its turn* there,
    and nothing records where a creature was when its turn began, so that
    half is dropped: this fires when the adjacency is lost, however it was
    gained.
    """
    who, other = getattr(ev, "actor", None), getattr(ev, "other", None)
    if who is None or other is None:
        return False
    held = world.get(other, Companion)
    if held is None or held.owner != me:
        return False
    return team(world, who) is not team(world, me)


@power(
    "p3832",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p3832(c: Cast) -> None:
    """"As if he or she had spent a healing surge" -- the hit points arrive,
    the surge stays in the pool, so this is a heal and not `c.surge`."""
    mate = c.target
    if mate is not None:
        c.heal(c.surge_value(of=mate), on=mate)


@power(
    "p3834",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PRIMAL,
    trigger="an ally within 10 squares of you takes damage",
    on=Trigger(
        DamageRolled,
        ally_damaged_within_10,
        "an ally within 10 squares of you takes damage",
    ),
)
def p3834(c: Cast) -> None:
    """Halving the blow in flight: the rolled amount is cut on the event
    itself -- an interrupt is before it lands -- and the other half is dealt
    to me. An odd number leaves the larger half with the ally."""
    ev = c.trigger
    amount = max(0, getattr(ev, "amount", 0))
    if amount <= 0:
        return
    mine = amount // 2
    ev.amount = amount - mine
    if mine:
        c.flat(mine, dtype=getattr(ev, "dtype", DamageType.UNTYPED), on=c.me)


@power(
    "p5394",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5394(c: Cast) -> None:
    ring = c.zone(c.area(), until=When.ENCOUNTER)
    for mate in c.allies():
        c.bonus(
            "attack", 1, on=mate, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring),
        )


@power(
    "p9748",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PRIMAL,
    trigger="you roll initiative at the beginning of an encounter",
    on=Trigger(
        InitiativeRolled, about_me, "you roll initiative at the start of a fight"
    ),
)
def p9748(c: Cast) -> None:
    """Drawing a weapon is not modelled -- everybody starts a fight armed --
    so the slide is the whole of it."""
    c.slide(3)


# -- the rows built round the spirit ----------------------------------------


@power(
    "p11358",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(20),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p11358(c: Cast) -> None:
    """The printed target is an ally *or a liftable object* standing by the
    spirit; objects are not creatures here, so the ally is all of it. The
    adjacency is a targeting restriction the header cannot state."""
    mate = c.target
    if mate is None or not beside_spirit(c, mate):
        return
    c.slide(max(1, c.speed_of() // 2), on=mate)
    send_spirit(c, mate)


@power(
    "p12527",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5, from_="companion"),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p12527(c: Cast) -> None:
    """"Makes a saving throw **or** gains temporary hit points" is a choice,
    and it is only a choice when there is something to save against -- so a
    save that finds nothing falls through to the hit points."""
    mate = c.target
    c.dismiss_companion()
    if mate is None:
        return
    if c.may("make a saving throw", who=mate) and c.save(on=mate):
        return
    c.temp_hp(c.wis_mod, on=mate)


@power(
    "p12869",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Melee(5, from_="companion"),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p12869(c: Cast) -> None:
    """Regeneration is a watch on the beneficiary's own turn start. The
    printed end condition -- calling the companion again -- is read as the
    spirit being back on the board, which is all that calling does."""
    mate = c.target
    c.dismiss_companion()
    if mate is None:
        return
    c.resist(10, DamageType.FIRE, on=mate, until=When.ENCOUNTER)
    if c.int_mod <= 0:
        return

    def mend(ev: Any) -> None:
        if getattr(ev, "actor", None) != mate or c.companion() is not None:
            return
        if c.wounded(on=mate):
            c.heal(c.int_mod, on=mate)

    c.watch(TurnStart, mend, until=When.ENCOUNTER, on=mate)


@power(
    "p9744",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=(
        "an enemy that started its turn adjacent to your spirit companion "
        "ends its movement no longer adjacent to it"
    ),
    on=Trigger(
        AdjacencyLost,
        stepped_away_from_spirit,
        "an enemy stops standing beside your spirit companion",
    ),
)
def p9744(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    send_spirit(c, foe)


@power(
    "p9745",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p9745(c: Cast) -> None:
    """"You and each ally in the burst" is two pools: the shaman is a
    target whether or not the spirit's burst reaches back to him."""
    mate = c.target
    if mate is not None and mate != c.companion():
        c.resist(c.con_mod, on=mate, until=When.ENCOUNTER)
    if c.first and c.me not in c.targets:
        c.resist(c.con_mod, on=c.me, until=When.ENCOUNTER)


@power(
    "p9747",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9747(c: Cast) -> None:
    """The second half spends a free action to end this power early, and
    there is no verb for spending one, so the standing bonus is the row."""
    for mate in friends(c, with_me=True):
        c.bonus(
            "attack", 1, on=mate, until=When.ENCOUNTER,
            when=lambda ctx: (
                bool(ctx.get("ranged")) and beside_spirit(c, ctx.get("target"))
            ),
        )
