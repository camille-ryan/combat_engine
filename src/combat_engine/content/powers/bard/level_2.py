"""Bard, level 2: the utilities.

Four of these are skill checks and nothing else, so they carry
`out_of_combat=True` rather than an invented mechanic. The two songs are
auras -- "the zone moves with you, remaining centered on you" is what an aura
already is -- and the bonus they hand out is a held modifier gated on standing
inside, which is the only way it can follow creatures walking in and out.
"""

from __future__ import annotations

from combat_engine.engine import *

DEFENCES = (AC, FORT, REF, WILL)


def _enemy_hits_ally(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "attacker", None)
    mate = getattr(ev, "target", None)
    if foe is None or mate is None or mate == me:
        return False
    mine = query.team(world, me)
    return query.team(world, foe) is not mine and query.team(world, mate) is mine


def _ward(c: Cast, mate: int) -> None:
    """+2 to every defence, sustained, and handed to somebody else on sustain.

    One effect carrying four modifiers rather than four calls to `c.bonus`:
    the transfer has to move all of it or none, and `c.bonus` cannot name a
    sustain cost, so a hold written with it would simply lapse after a round.
    """
    mods = [(mate, Mod(what=d.value, value=2, kind="power", label=c.ref)) for d in DEFENCES]
    held = c.world.effects.apply(
        mate, c.me, When.SUSTAIN, label=c.ref, mods=mods, sustain_cost=MINOR
    )

    def hand_on() -> None:
        others = [a for a in c.within(10, side="ally") if a != mate]
        pick = c.choose(others, "hand the ward to another ally", optional=True)
        if pick is None:
            return
        c.world.effects.end(held, "handed to another ally")
        _ward(c, pick)

    c.on_sustain(held, hand_on)


@power(
    "p12512",
    level=2,
    cls="bard",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION, Keyword.TELEPORTATION],
    trigger="an enemy in the burst hits an ally",
    on=Trigger(Hit, _enemy_hits_ally, "an enemy in the burst hits an ally"),
)
def p12512(c: Cast) -> None:
    mate = getattr(c.trigger, "target", None)
    if mate is None:
        return
    c.invisible(to=c.target, on=mate, until=When.SAVE_ENDS)
    c.teleport(5, who=mate)


@power(
    "p14457",
    level=2,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p14457(c: Cast) -> None:
    c.note("p14457: a knowledge check resolves as though the d20 had come up 20")


@power(
    "p2358",
    level=2,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p2358(c: Cast) -> None:
    """An aura, not a zone: the printed line says it stays centred on you."""
    ring = c.aura(5, until=When.SUSTAIN, sustain=MINOR)
    for mate in c.allies():
        c.bonus(
            AC, 1, on=mate, until=When.ENCOUNTER,
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring),
        )


@power(
    "p2359",
    level=2,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p2359(c: Cast) -> None:
    ring = c.aura(5, until=When.SUSTAIN, sustain=MINOR)
    for mate in c.allies():
        c.bonus(
            "attack", 1, on=mate, until=When.ENCOUNTER,
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring),
        )


@power(
    "p2360",
    level=2,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p2360(c: Cast) -> None:
    c.note("p2360: +5 to the target's Stealth, and no penalty for moving fast")


@power(
    "p2990",
    level=2,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p2990(c: Cast) -> None:
    """The critical is taken off the `Hit` and off the live result together:
    the body reads the result when it rolls damage, and the event is what
    every crit rider watches."""
    mate = c.target
    if mate is None:
        return

    def soften(ev: Hit) -> None:
        if ev.target != mate or not ev.critical:
            return
        if c.roll("1d20") < 10:
            return
        ev.critical = False
        res = getattr(ev, "result", None)
        if res is not None:
            res.critical = False

    c.watch(Hit, soften, until=When.ENCOUNTER, on=mate, label="p2990")


@power(
    "p2991",
    level=2,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p2991(c: Cast) -> None:
    """The escalating half -- "+1 more for each target whose turn has not yet
    started" -- is left off: it needs the initiative order read at the moment
    of a hit, and nothing exposes who has already acted this round."""
    c.bonus("attack", 1, until=When.EONT)


@power(
    "p3116",
    level=2,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p3116(c: Cast) -> None:
    if c.target is not None:
        _ward(c, c.target)


@power(
    "p3117",
    level=2,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p3117(c: Cast) -> None:
    c.note("p3117: +2 to aid another, and aiding grants +3 instead of +2")


@power(
    "p4990",
    level=2,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p4990(c: Cast) -> None:
    c.note("p4990: +2 to each target's next check with one chosen skill")


@power(
    "p6610",
    level=2,
    cls="bard",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p6610(c: Cast) -> None:
    c.slide(4)
