"""Skill powers for `cls="thievery"`: fingers, and getting past somebody.

Seven rows, levels 2/6/10, and they split cleanly in three. Three are board
work and are written -- an opposed check that sets up an ally, a swap with
an ally, and a walk through an enemy's space. Two are the circumstance no
board presents: a lock and a pocket, which is `f3447`'s split on `#735`
(`actions._picking` offers the lock as a standard action and `Grid.locked`
is empty on every board; sleight of hand went to the story engine on
`#787`). Two are held by the engine -- nothing reaches the picking-up path
from a body, and nothing announces a trap going off.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Cast,
    Melee,
    When,
    power,
)
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import squares


@power(
    "p11598",
    level=2,
    cls="thievery",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def p11598(c: Cast) -> None:
    """Inert on the **circumstance**, not on the skill.

    Thievery is rolled in this tree and opening a lock is a real action --
    `actions._picking` offers it, with a DC off `Grid.locked` and a key of
    its own for the bonuses that raise it. What no board has is a lock:
    `Grid.locked` is empty on every square of every board, and the map's
    own note says so. There is nothing for the minor action to be spent on,
    and writing the executor's three lines again in a body would be a
    second reader of a map nothing fills."""


@power(
    "p11599",
    level=2,
    cls="thievery",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def p11599(c: Cast) -> None:
    """Both halves are off the board, and the split is Camille's on `#735`.

    A pocket is somebody's unattended property and sleight of hand is judged
    by onlookers; neither is a thing a square carries, and the second was
    scoped to the story engine on `#787`. `f3447` is the worked case and
    this is the same pair of clauses with no combat half beside them."""


@power(
    "p9344",
    level=2,
    cls="thievery",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    once_per_round=True,
    todo=("c.pick_up()",),
)
def p9344(c: Cast) -> None:
    """Half of the card is already free here and the other half is shut.

    Drawing and sheathing cost no action in this engine -- `f157` records
    it -- so that clause is the engine's behaviour rather than a benefit.
    Picking something up is `actions._picking_up`, which is offered in the
    action menu for a minor out of the actor's **own** square and has no
    `Cast` verb at all, so a body cannot reach the path to do it for free or
    from the square next door. `cf:swordmage-f0` waits on the same door.

    `once_per_round=True` is the printed Special and is header data, so it
    holds whatever the body eventually says."""


@power(
    "p11600",
    level=6,
    cls="thievery",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="your thievery check triggers a trap",
    todo=("events.TrapSprung",),
)
def p11600(c: Cast) -> None:
    """The shift is one line; the trigger cannot be declared at all.

    A trap is an entity the board knows -- `query.is_trap` finds one -- and
    nothing anywhere announces one going off, least of all off the back of a
    skill check: there is no event between `SkillCheck` and the damage for a
    trigger to name. `trigger=` is left as the printed prose and carries no
    `on=`, deliberately, because prose with no predicate is a row that never
    fires and the marker is what says so."""


@power(
    "p11601",
    level=6,
    cls="thievery",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=ONE_ALLY,
)
def p11601(c: Cast) -> None:
    """The two steps are taken in the other order, and the board ends the
    same.

    Printed, the ally slides into the caster's space and the caster then
    steps out of it -- a moment of two creatures in one square, which
    `c.slide` has no `share=` for. Stepping out first and sliding the ally
    into the vacated square reaches the same two positions by the same two
    moves. The one destination it gives up is the ally's own starting
    square, since the ally is still standing in it when the shift is
    offered; every other square the card allows is still offered."""
    ally = c.target
    if ally is None:
        return
    was = c.here
    if not c.shift(1):
        return
    c.slide(1, on=ally, to=was)


@power(
    "p9345",
    level=6,
    cls="thievery",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p9345(c: Cast) -> None:
    """"Melee touch" is `Melee(1)`, which is how the other rows printing it
    are written.

    `c.passive` is the opposed number the card asks for rather than an
    invented DC, and `to="ally"` with `once=True` is "the next ally who
    attacks it" exactly: `"ally"` leaves the caster out, which is what the
    printed sentence does."""
    if c.check("thievery", c.passive("perception", of=c.target)):
        c.grants_advantage(on=c.target, to="ally", once=True, until=When.EONT)


@power(
    "p9346",
    level=10,
    cls="thievery",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p9346(c: Cast) -> None:
    """The permission is narrowed to the one creature the card names.

    `c.may_enter(side="enemy")` would open every enemy's square; the gate
    reads `ctx["occupant"]` instead, which is who is standing in the square
    being entered, so only this target is walked through. Both the
    permission and the opportunity-attack waiver are handed back when the
    move is over, because the card gives them for the movement.

    **The landing square is named, and it has to be.** `movement._clear`
    consults `may_enter` on every square of the route including the last,
    so `c.move(toward=victim)` ends the walk *on top of* the target --
    driven, caster and target both on one square. The card names the
    landing ("a square adjacent to it"), so choosing one is the printed
    instruction rather than a narrowing, and the far side is picked because
    that is what passing through its space comes to. See the batch report:
    `shift`'s own docstring says the final square is a melding power's
    business, and `_clear` does not draw that line."""
    victim = c.target
    if victim is None:
        return
    body = squares(c.world, victim)
    start = c.here
    ring = [
        sq
        for sq in sorted(spread(body, 1) - body)
        if c.world.grid.passable(sq) and not c.in_squares([sq])
    ]
    if not ring:
        return
    ring.sort(key=lambda sq: (-distance(start, sq), sq))
    through = c.may_enter(
        on=c.me,
        until=When.EOT,
        when=lambda ctx: ctx.get("occupant") == victim,
    )
    opening = c.no_provoke(from_=victim, on=c.me, until=When.EOT)
    c.walk_toward(ring[0], c.speed_of(), on=c.me)
    c.end_effect(through, why="the move is over")
    c.end_effect(opening, why="the move is over")
    c.penalty("attack", 2, on=victim, until=When.SONT)
