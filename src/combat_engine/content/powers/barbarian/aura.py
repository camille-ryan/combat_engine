"""Barbarian: the defender aura, and the two rows that reach into it.

The class page prints a defender aura and the compendium gives it no row of
its own, so it is a `cf:` feature like every other class-page sentence. It
had to exist before anything could ask about it: `p15848` has answered "an
enemy subject to your defender aura" since it was written and there was
never an aura for an enemy to be subject to, so the row read as working and
was inert on every board.

The shape is the one the fighter's `p12660` lays -- an aura 1 whose enemies
take -2 to any attack that leaves its owner out, and which a marked enemy
is outside -- because it is the same printed feature on a different class
page. `aura_ring` is imported rather than copied for the same reason.

`c.in_my_aura(who, label=AURA)` is how the two rows ask who is inside. The
narrower question `p12660`'s file asks -- and its exemption for a marked
enemy -- stays in the penalty's own gate, where it belongs: a row aimed at
somebody in the aura is aimed at them whoever else has marked them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.fighter.footwork import aura_ring
from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    STR,
    ActionType,
    Attack,
    Cast,
    Effect,
    Keyword,
    Melee,
    Relation,
    When,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.events import Hit, ZoneExited
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team

#: The label the aura's own zone wears, and what the rows below look for.
AURA = "cf:barbarian-aura"

#: The opportunity row the aura already had. `p14428` names it beside the
#: opportunity attack, and it is not one -- it is an opportunity *action*
#: with a trigger of its own -- so the two are asked separately.
GUARDIAN = "p15848"


@power(
    "cf:barbarian-aura",
    level=0,
    cls="barbarian",
    # A trait: the aura is up from the moment the fight starts and nobody
    # takes an action to raise it.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def barbarian_aura(c: Cast) -> None:
    """An aura 1 that costs an enemy inside it 2 to attack anybody else.

    "Until you end it" is dropped for the same reason `p12660` drops it:
    nothing takes an aura down early and no barbarian would.
    """
    me = c.me
    hold = c.effect(AURA, until=When.ENCOUNTER, on=me)
    if hold is None:
        return

    def give(who: int) -> list[Effect | None]:
        def gate(ctx: dict[str, Any]) -> bool:
            if ctx.get("target") == me:
                return False
            return not c.world.relations.sources(Relation.MARKED_BY, who)

        return [c.penalty("attack", 2, on=who, until=When.ENCOUNTER, when=gate)]

    aura_ring(c, hold, side="enemy", give=give)


def _dress_the_aura(c: Cast, give: Any) -> bool:
    """Hang a modifier on whoever is in the aura the barbarian *already* has.

    `aura_ring` lays a new aura; these rows change the standing one, so the
    watching half is repeated here and the zone is found by label. Returns
    whether there was an aura to change.
    """
    ring = c.my_aura(AURA)
    if not ring:
        return False
    me = c.me
    given: dict[int, list[Effect]] = {}

    def cover(who: int) -> None:
        if who in given or who == me or team(c.world, who) is team(c.world, me):
            return
        given[who] = [e for e in give(who) if e is not None]

    def uncover(who: int) -> None:
        for effect in given.pop(who, []):
            c.world.effects.end(effect, "left the aura")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            cover(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == ring:
            uncover(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(ZoneExited, exited, until=When.ENCOUNTER, on=me, label=c.ref)
    for who in c.world.zones.occupants(ring):
        cover(who)
    return True


@power(
    "p14420",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p14420(c: Cast) -> None:
    """The Effect line is not conditional on the swing, so it runs either way.

    "Enemies grant combat advantage while subject to your defender aura" is
    a standing property of the aura rather than a grant to one creature, so
    it is given on the way in and taken back on the way out.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if c.first:
        _dress_the_aura(
            c,
            lambda who: [
                c.grants_advantage(on=who, to="team", until=When.ENCOUNTER)
            ],
        )


def _step_clear(c: Cast, mate: int, victim: int) -> None:
    """"Shift up to 2 squares to a square that is not adjacent to the target."

    A filter on the destination, so the squares are picked here and named
    outright; handed to the decider the ally would happily stay put.
    """
    beside = spread(squares_of(c.world, victim), 1)
    options = sorted(
        sq for sq in c.world.reachable_squares(mate, 2) if sq not in beside
    )
    if not options:
        return
    where = c.choose(options, f"{c.ref}: where to step", optional=True)
    if where is not None:
        c.shift(2, who=mate, to=where)


@power(
    "p14428",
    level=10,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
)
def p14428(c: Cast) -> None:
    """"One enemy subject to your defender aura" is a filter on the target
    the header cannot say, so it is asked here and the row declines rather
    than landing on somebody standing outside the ring.

    `Hit` carries `opportunity` as a plain attribute, which is the first of
    the two ways the printed rider pays; the second is the aura's own
    opportunity row, asked by ref.
    """
    victim = c.target
    if victim is None or not c.in_my_aura(victim, label=AURA):
        return
    for mate in c.allies():
        if c.adjacent_to(victim, mate):
            _step_clear(c, mate, victim)

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or ev.target != victim:
            return
        if getattr(ev, "opportunity", False) or ev.power == GUARDIAN:
            c.immobilized(on=victim, until=When.EOTNT)

    c.watch(Hit, on_hit, until=When.SONT, on=c.me, label=c.ref)
