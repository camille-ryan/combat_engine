"""Druid, level 6: the utilities, second half.

`p5507` is a Perception bonus and low-light vision and nothing else, so it
is declared inert rather than given an invented effect -- the same call
`wizard/level_0.py` makes for its cantrips.

`p5052` moves the druid's own zones about, which is a thing no `Cast` method
does: a zone's squares are read straight off the `Zone` and written back,
and `Zones.refresh` is what notices who is now standing in one.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    SELF,
    Cast,
    CloseBurst,
    DamageRolled,
    Event,
    Hit,
    Keyword,
    Ranged,
    Square,
    Trigger,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.zones import Zone

from .forms import fork_mod, zone_hold

PRIMAL = [Keyword.PRIMAL]


def _struck_by_a_swing(world: World, me: int, ev: Event) -> bool:
    """"You take damage from a melee or a ranged attack."

    Declared on `DamageRolled`, which is the window an interrupt gets: the
    resistances are read after it, so resist 10 raised here counts against
    the blow that raised it. The reach comes off the row that is rolling,
    since the damage event carries the ref in `detail` and nothing else.
    """
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    p = get(getattr(ev, "detail", "") or "")
    return p is not None and p.reach.kind in ("melee", "ranged")


@power(
    "p4893",
    level=6,
    cls="druid",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you take damage from a melee or a ranged attack",
    on=Trigger(
        DamageRolled,
        when=_struck_by_a_swing,
        text="you take damage from a melee or a ranged attack",
    ),
)
def p4893(c: Cast) -> None:
    """The Prerequisite is having wild shape, which every druid does and
    which no row in this batch is."""
    c.resist(10, until=When.EONT, on=c.me)


@power(
    "p5052",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=SELF,
    keywords=PRIMAL,
)
def p5052(c: Cast) -> None:
    """The second sentence is a duration being lengthened, which nothing in
    `Cast` does: a zone due to end at the end of this turn is moved onto the
    end-of-next-turn clock by writing the clock, and `latch` is what keeps
    an effect on that clock alive through the turn it was made in.

    Each zone is offered the shift that would cover the most enemies, since
    with nobody playing the first option on the list is the answer.
    """
    area = spread({c.here}, 10)
    steps: list[Square] = sorted(
        (dx, dy)
        for dx in range(-5, 6)
        for dy in range(-5, 6)
        if max(abs(dx), abs(dy)) <= 5 and (dx or dy)
    )
    moved = 0
    for eid, zone in list(c.world.zones.all()):
        if zone.owner != c.me or zone.aura is not None or not (zone.squares & area):
            continue
        best = min(
            steps,
            key=lambda s: (
                -len(c.in_squares({(x + s[0], y + s[1]) for x, y in zone.squares},
                                  side="enemy")),
                s,
            ),
        )
        shifted = {(x + best[0], y + best[1]) for x, y in zone.squares}
        if not all(c.world.grid.inside(sq) for sq in shifted):
            continue
        zone.squares = frozenset(shifted)
        moved += 1
        held = c.world.get(eid, Zone)
        effect = held.effect if held is not None else None
        if effect is not None and effect.when is When.EOT and c.may("hold it a turn longer"):
            effect.when = When.EONT
            effect.clock = c.me
            effect.latch = True
    if moved:
        c.world.zones.refresh()
    # Moving a zone emits nothing of its own -- `refresh` only announces who
    # walked in or out -- so the log would otherwise show the row doing
    # nothing at all on a board where the zones are standing empty.
    c.note(f"{c.ref}: {moved} of your zones move five squares")


@power(
    "p5507",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p5507(c: Cast) -> None:
    c.note(f"{c.ref}: low-light vision and +4 to Perception until the fight ends")


@power(
    "p7393",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=SELF,
    keywords=[*PRIMAL, Keyword.CONJURATION],
)
def p7393(c: Cast) -> None:
    """A wall of five squares, laid in the body. Its concealment half has
    nothing to read it; the combat advantage half is real, and it reaches
    one square further than the wall itself -- "while in the wall **or
    adjacent to it**" -- so the hold is hung on a zone a square wider than
    the leaves.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the leaves grow")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-2, 3)]
    leaves = [sq for sq in run if c.world.grid.inside(sq)]
    if not leaves:
        return
    c.zone(leaves, label=c.ref, until=When.ENCOUNTER)
    near = c.zone(spread(leaves, 1), label=f"{c.ref} edge", until=When.ENCOUNTER)
    foes = set(c.enemies())
    zone_hold(
        c, near,
        lambda who: who in foes,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
    )
    c.note(f"{c.ref}: partial concealment inside it, and there is none here")


@power(
    "p9657",
    level=6,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=SELF,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p9657(c: Cast) -> None:
    """"Each square must be adjacent to a vertical surface" is a real
    condition on a real board: blocking terrain is what a wall is here, so
    the run is drawn along one.
    """
    walls = c.world.grid.blocking
    room = sorted(
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.inside(sq) and sq not in walls and spread({sq}, 1) & walls
    )
    if not room:
        return
    zone = c.zone(room[:10], label=c.ref, until=When.EONT)
    friends = {c.me, *c.allies()}
    zone_hold(
        c, zone,
        lambda who: who in friends,
        lambda who: c.mode("climb", 5, on=who, until=When.EONT),
        until=When.EONT,
    )


@power(
    "p9658",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9658(c: Cast) -> None:
    """"Constitution or Dexterity modifier" is the fork with no leg to stand
    on; `forms.fork_mod` takes the larger."""
    me = c.me
    foes = set(c.enemies())

    def thorns(ev: Hit) -> None:
        if ev.target != me or ev.attacker not in foes:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind == "melee":
            c.flat(fork_mod(c), on=ev.attacker)

    c.watch(Hit, thorns, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p9659",
    level=6,
    cls="druid",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9659(c: Cast) -> None:
    """Walking through an enemy's space has no lever: `c.phasing` is earth
    and rock, and `share=True` on a shift or a teleport is about where a
    move *ends*. The five squares and the safe passage are both real.
    """
    c.no_provoke(until=When.EOT)
    c.move(5)
    c.note(f"{c.ref}: the move passes through enemies' spaces, and nothing here allows it")
