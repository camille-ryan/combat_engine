"""Where the party is standing when a fight starts.

Placement was `chargen.spawn` at `(2, 3 + i*2)` -- a column at x=2, two
squares apart, in whatever order `party.sheets` happened to be in. The
players never chose, and the rules say they should:

> **Marching Order.** It's a good idea for your group to establish a
> standard marching order [...] having it set out before you get into an
> encounter lets the DM know exactly where everyone is when the encounter
> begins.

The printed advice also names a real trade the engine can already feel
both sides of -- *"staying close ensures that everyone can get to the
action quickly [...] being bunched up leaves you vulnerable to area
attacks"* -- and `AreaBurst` and `CloseBurst` are modelled and used.

## An order and a spread, never coordinates

A player knows "front" and does not know the board is 16x12, which is the
same reasoning `objective.POSITIONS` is built on. So a formation is a band
per character plus one number for how far apart, and this module resolves
it against the real starting corner.

**The default reproduces today's placement exactly**, which is what keeps
the eight replay fixtures still: no order stated means one column at the
starting x, `SPREAD` apart. That is the same compatibility shape #990 used
for objectives, and it is load-bearing rather than polite -- a placement
change moves every fight.

## The printed advice is offered, not imposed

`by_role` arranges a party the way the page suggests -- defender front,
leader back, striker and controller in the middle -- and **nothing calls it
by default**. Making it the default would have been the obvious move and
would have changed where every existing party stands, which is a balance
change dressed as a fidelity fix. A player asks for it. #994.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Front to back, as the rules state it. `front` is nearest the opposition.
BANDS = ("front", "middle", "back")

#: How far apart, in squares, along the line the party forms. Two is what
#: the placement has always used, so it is the default that moves nothing.
SPREAD = 2

#: How far each band stands from the party's own starting column, toward
#: the enemy for `front` and away for `back`. One square, because the
#: printed advice is about *order* rather than distance and a wider offset
#: would start a fight closer to the opposition than any fixture expects.
OFFSET = {"front": 1, "middle": 0, "back": -1}

#: What the page suggests each role does, which `by_role` reads.
#:
#: > Danger in a dungeon environment often comes from the front, so it's a
#: > good idea to put a defender at the front [...] Leaders make a good
#: > choice for the back [...] Strikers might scout ahead, but most prefer
#: > to stay nearer to the middle.
#:
#: A controller is not named in that passage and is placed in the middle,
#: because the same sentence says a defender at the front is *"protecting
#: your controllers"* -- which puts them behind the defender and not at the
#: back where the leader is wanted.
BY_ROLE = {
    "defender": "front",
    "striker": "middle",
    "controller": "middle",
    "leader": "back",
}


@dataclass(frozen=True)
class Formation:
    """A standing arrangement: which band each character walks in.

    `bands` runs parallel to `party.sheets`, the same position-matching
    `harvest` and `Campaign.personas` use. Empty means "as dealt", which
    is today's single column.

    On the **campaign** rather than the scene, because the rules call it a
    standing arrangement -- *"the way your characters are normally
    arranged"*, changeable at any time -- so it is set once by a player
    rather than re-authored per fight.
    """

    bands: tuple[str, ...] = ()
    spread: int = SPREAD

    @classmethod
    def by_role(cls, roles: list[str], spread: int = SPREAD) -> Formation:
        """The arrangement the page suggests, from each character's role."""
        return cls(
            bands=tuple(BY_ROLE.get(r, "middle") for r in roles),
            spread=spread,
        )

    def band(self, slot: int) -> str:
        """Which band slot N walks in. `middle` when nothing was said."""
        if slot < len(self.bands):
            return self.bands[slot]
        return "middle"


def roles_of(classes: list[str]) -> list[str]:
    """Each class's printed role, for `by_role`.

    Read off `chargen.CLASSES` rather than written out here, so it cannot
    disagree with the class pages the rest of the build comes from.
    """
    from combat_engine import chargen

    out: list[str] = []
    for name in classes:
        line = chargen.CLASSES.get((name or "").strip().lower())
        out.append(getattr(line, "role", "") or "middle")
    return out


def squares(
    count: int, corner: tuple[int, int], formation: Formation | None = None,
) -> list[tuple[int, int]]:
    """Where each of `count` characters stands, in party order.

    `corner` is the party's own starting square -- `story.PARTY_AT`, which
    is where the column has always begun.

    **With no formation this is byte-identical to the old expression**,
    `(corner[0], corner[1] + i * SPREAD)`, and that is asserted rather than
    assumed: every replay fixture is a fight that starts from these
    squares, so a one-square drift re-records all eight.
    """
    plan = formation or Formation()
    # **Zero falls back to the printed default, not to one.** A spread of 0
    # would stack the party on one square, and it is an *unset* value
    # rather than a tight formation somebody asked for -- a player who
    # wants shoulder to shoulder writes 1. Same reading as an empty
    # `bands` meaning "as dealt".
    spread = max(1, int(plan.spread) or SPREAD)
    out: list[tuple[int, int]] = []
    for i in range(max(0, count)):
        # No `if plan.bands` guard: `band` already answers `middle`
        # for a slot nothing was said about, and middle is offset 0.
        # The guard was dead code -- a plant that removed it changed
        # nothing, which is how I found out.
        shift = OFFSET.get(plan.band(i), 0)
        out.append((corner[0] + shift, corner[1] + i * spread))
    return out
