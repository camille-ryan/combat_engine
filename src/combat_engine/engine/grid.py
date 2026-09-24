"""The board: distance, line of effect, cover, flanking, and area templates.

Square `(x, y)` covers the unit area from `(x, y)` to `(x+1, y+1)`, so its
centre is `(x+0.5, y+0.5)` and its corners are the four integer points
around it. Every geometric question below is asked in that continuous space
and answered back in squares, which is the only way the corner-to-corner
rules come out right.

Diagonals cost one square, so distance is Chebyshev.

**This file is the shape of the board, and it is meant to be the only one.**
Nothing else in the engine measures a distance, enumerates a step, or does
arithmetic on a coordinate -- `distance` and `neighbours` exist so that the
pathfinder, the forced-movement rules and the scorer can all ask instead.

A board of a different shape -- hexes, most obviously -- replaces what is
here and nothing above it. What it would have to answer:

* `distance` and `neighbours`: six steps rather than eight, and no diagonal.
* `spread`, `burst`, `area_burst`: rings, which come out simpler on hexes.
* `line_of_effect` and `cover`: the `_trace` machinery below walks a segment
  through unit squares and is the most square-specific thing here. A hex
  board needs its own, and it is the real work.
* `flanks`: "opposite sides" is *easier* on hexes -- three opposing pairs,
  no corner cases.
* `footprint`: the genuine modelling question rather than a port. A Large
  creature is two squares on a side here; hexes have no such tiling, so what
  Large means has to be decided rather than translated.
* `blast_placements`: a blast is a square block adjacent to the caster. The
  hex equivalent is a cone, which is a different shape and not a port.

What does **not** change is worth saying too. No hand-written power names a
coordinate -- bodies reach the board through `c.within`, `c.area`, `c.push`
and the like, all of which are shape-agnostic -- so the content carries over
untouched. The interface has its own copy of this seam in `web/coords.js`,
which says the same thing about itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from itertools import pairwise, product

from .types import Cover, Size

Square = tuple[int, int]
Point = tuple[float, float]

#: All eight steps. Ordered so iteration is deterministic.
STEPS: tuple[Square, ...] = (
    (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1),
)  # fmt: skip


def distance(a: Square, b: Square) -> int:
    """Chebyshev: a diagonal step costs the same as a straight one.

    The **only** place the engine measures a distance. Anything that wants to
    know how far apart two squares are calls this rather than doing the
    arithmetic, which is what keeps the shape of the board in one file.
    """
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def neighbours(sq: Square) -> tuple[Square, ...]:
    """The squares one step from this one.

    Eight here, because diagonals are steps. The **only** place the engine
    enumerates a step, so a board with a different number of sides changes
    this and not the pathfinder, the forced-movement rules or anything else
    that walks.
    """
    x, y = sq
    return tuple((x + dx, y + dy) for dx, dy in STEPS)


def footprint(origin: Square, size: Size) -> frozenset[Square]:
    """The squares a creature of `size` standing at `origin` occupies.

    `origin` is the low corner of the footprint, so a Large creature at
    (3, 3) fills (3,3), (4,3), (3,4) and (4,4).
    """
    n = size.squares
    x, y = origin
    return frozenset((x + dx, y + dy) for dx, dy in product(range(n), range(n)))


def spread(squares: frozenset[Square] | set[Square], radius: int) -> frozenset[Square]:
    """Every square within `radius` of any square in `squares`, inclusive.

    This is how reach works for a creature bigger than one square, and how a
    close burst measures from a body rather than from a point.
    """
    out: set[Square] = set()
    for sx, sy in squares:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                out.add((sx + dx, sy + dy))
    return frozenset(out)


def between(a: frozenset[Square] | set[Square], b: frozenset[Square] | set[Square]) -> int:
    """Distance between two footprints: the closest pair of squares."""
    return min(distance(p, q) for p in a for q in b)


# --------------------------------------------------------------------------
# Segment tracing
# --------------------------------------------------------------------------


@lru_cache(maxsize=1 << 16)
def _trace(p0: Point, p1: Point) -> list[frozenset[Square]]:
    """What the segment `p0`-`p1` would have to get past, as square groups.

    Cached, because it is pure geometry -- two points in, the same answer
    every time, whatever is standing where. Cover and line of effect between
    them ask for this tens of thousands of times when a board is drawn.

    Collect every parameter where the segment crosses a grid line, then walk
    the midpoints of consecutive pairs. Each midpoint yields one group, and
    the segment is stopped there only if **every** square in that group is an
    obstacle.

    A midpoint inside a square gives a group of one -- pass through it and you
    are through the square. A midpoint sitting on a grid line means the
    segment is running along the line rather than through either side, so the
    group is the two squares that share the line, or the four around a
    lattice point. That is the whole of the corner rule: a line grazing one
    pillar's corner is clear, because the other three squares are open, while
    a line sliding down the seam between two wall squares is not.
    """
    x0, y0 = p0
    x1, y1 = p1
    ts = {0.0, 1.0}
    for start, delta in ((x0, x1 - x0), (y0, y1 - y0)):
        if delta == 0:
            continue
        first, last = sorted((start, start + delta))
        for n in range(int(first) - 1, int(last) + 2):
            t = (n - start) / delta
            if 0.0 < t < 1.0:
                ts.add(t)

    out: list[frozenset[Square]] = []
    for t0, t1 in pairwise(sorted(ts)):
        t = (t0 + t1) / 2
        mx = x0 + (x1 - x0) * t
        my = y0 + (y1 - y0) * t
        xs = _straddle(mx)
        ys = _straddle(my)
        out.append(frozenset((x, y) for x in xs for y in ys))
    return out


def _straddle(v: float) -> tuple[int, ...]:
    """The column (or row) a coordinate is in, or both it straddles."""
    n = round(v)
    if abs(v - n) < 1e-9:
        return (int(n) - 1, int(n))
    return (int(v // 1),)


def _stopped(trace: list[frozenset[Square]], obstacles: set[Square] | frozenset[Square]) -> bool:
    return any(group <= obstacles for group in trace)


def _corners(sq: Square) -> tuple[Point, Point, Point, Point]:
    x, y = sq
    return ((x, y), (x + 1.0, y), (x, y + 1.0), (x + 1.0, y + 1.0))


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------


@dataclass
class Grid:
    """Terrain, plus an index of who is standing where.

    Positions live on the `Position` component; `occupants` is an index the
    movement system keeps in step with it. Geometry needs to ask "what is in
    this square" constantly and scanning every entity to answer would make
    cover and pathing quadratic in creatures.
    """

    width: int
    height: int
    #: Squares that stop movement and block line of effect. Walls, pillars.
    blocking: set[Square] = field(default_factory=set)
    #: Squares that cost an extra square to enter, and what sort of going
    #: they are -- "mud", "rubble", "ice". A bare set could not say, so a
    #: creature that wades through mud but not through rubble had nothing to
    #: test. An empty label means rough ground of no particular kind.
    difficult: dict[Square, str] = field(default_factory=dict)
    occupants: dict[Square, int] = field(default_factory=dict)

    def inside(self, sq: Square) -> bool:
        return 0 <= sq[0] < self.width and 0 <= sq[1] < self.height

    def passable(self, sq: Square) -> bool:
        return self.inside(sq) and sq not in self.blocking

    def occupant(self, sq: Square) -> int | None:
        return self.occupants.get(sq)

    def place(self, eid: int, squares: frozenset[Square]) -> None:
        """Index a creature's squares. **Never overwrites somebody else.**

        The index holds one occupant per square, and `lift` only deletes
        squares mapping to the entity being lifted. So overwriting did not
        replace the old occupant, it *unindexed* it: `squares_of` went empty
        while `Position` still named the square, and cover, blocking and
        occupancy all read the wrong answer until that creature next moved.

        Two things legitimately share a square -- a flyer directly above
        somebody, and a creature melded with its target -- and both already
        rely on the second one staying out of the index until it settles.
        Refusing the write here makes that the rule rather than a habit.
        """
        for sq in squares:
            if self.occupants.get(sq, eid) == eid:
                self.occupants[sq] = eid

    def lift(self, eid: int) -> None:
        for sq in [s for s, who in self.occupants.items() if who == eid]:
            del self.occupants[sq]

    def squares_of(self, eid: int) -> frozenset[Square]:
        return frozenset(s for s, who in self.occupants.items() if who == eid)

    # -- line of effect ----------------------------------------------------

    def line_of_effect(self, src: Square, dst: Square) -> bool:
        """True when at least one corner-to-corner line is unobstructed.

        Creatures never block line of effect in 4e -- they grant cover
        instead -- so only terrain is consulted here.
        """
        if src == dst:
            return True
        obstacles = self.blocking - {src, dst}
        return any(
            not _stopped(_trace(a, b), obstacles)
            for a in _corners(src)
            for b in _corners(dst)
        )

    def cover(
        self,
        src: Square,
        dst: Square,
        *,
        blockers: set[Square] = frozenset(),
    ) -> Cover:
        """Cover the target at `dst` has from an attacker at `src`.

        Pick the corner of the attacker's square that traces the most clear
        lines to the target's four corners. No line blocked is no cover; some
        blocked is cover; all four blocked, with line of effect surviving from
        somewhere, is superior cover.
        """
        if src == dst:
            return Cover.NONE
        obstacles = (self.blocking | set(blockers)) - {src, dst}
        best = 0
        for a in _corners(src):
            clear = sum(1 for b in _corners(dst) if not _stopped(_trace(a, b), obstacles))
            best = max(best, clear)
        if best == 4:
            return Cover.NONE
        if best == 0:
            return Cover.SUPERIOR
        return Cover.PARTIAL

    # -- flanking ----------------------------------------------------------

    def flanks(self, a: Square, b: Square, target: frozenset[Square]) -> bool:
        """Do squares `a` and `b` flank a creature occupying `target`?

        Both must be adjacent to it, and the line between their centres must
        enter and leave the creature's space through opposite sides or
        opposite corners. Clipping the segment against the target's bounding
        rectangle gives those two crossing points directly, so this holds for
        a Large creature as written rather than only for a Medium one.
        """
        if not (spread(target, 1) & {a} and spread(target, 1) & {b}):
            return False
        xs = [s[0] for s in target]
        ys = [s[1] for s in target]
        rect = (min(xs), min(ys), max(xs) + 1.0, max(ys) + 1.0)
        hit = _clip((a[0] + 0.5, a[1] + 0.5), (b[0] + 0.5, b[1] + 0.5), rect)
        if hit is None:
            return False
        enter, leave = hit
        out = _side(leave, rect)
        return out is not None and _opposite(enter, rect) == out


Rect = tuple[float, float, float, float]


def _clip(p0: Point, p1: Point, rect: Rect) -> tuple[Point, Point] | None:
    """Liang-Barsky. Returns where the segment enters and leaves `rect`."""
    x0, y0 = p0
    dx, dy = p1[0] - x0, p1[1] - y0
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x0 - rect[0]), (dx, rect[2] - x0), (-dy, y0 - rect[1]), (dy, rect[3] - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
    if lo > hi:
        return None
    return (x0 + dx * lo, y0 + dy * lo), (x0 + dx * hi, y0 + dy * hi)


def _side(p: Point, rect: Rect) -> str | None:
    """Which edge of `rect` the point lies on. A corner names both edges."""
    x, y = p
    x0, y0, x1, y1 = rect
    parts = []
    if abs(x - x0) < 1e-9:
        parts.append("w")
    if abs(x - x1) < 1e-9:
        parts.append("e")
    if abs(y - y0) < 1e-9:
        parts.append("s")
    if abs(y - y1) < 1e-9:
        parts.append("n")
    return "".join(parts) or None


_FLIP = {"w": "e", "e": "w", "n": "s", "s": "n"}


def _opposite(p: Point, rect: Rect) -> str | None:
    s = _side(p, rect)
    if s is None:
        return None
    return "".join(_FLIP[c] for c in s)


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


def burst(centre: frozenset[Square] | set[Square], radius: int) -> frozenset[Square]:
    """A close burst: every square within `radius` of the origin's space."""
    return spread(centre, radius)


def area_burst(centre: Square, radius: int) -> frozenset[Square]:
    """An area burst, which originates from a point rather than a creature."""
    return spread({centre}, radius)


def blast_placements(
    origin: frozenset[Square] | set[Square], size: int
) -> dict[Square, frozenset[Square]]:
    """Every way a close blast `size` can be laid down, keyed by its centre.

    A close blast is a `size`x`size` block that touches the caster's space
    without covering any of it. Enumerating the placements directly, rather
    than picking one of eight compass directions, is both the printed rule
    and the thing that makes aiming easy: **the key is the square you point
    at**, so a player clicks a square and the interface has the area.

    For a Medium caster and a blast 3 the keys come out as exactly the ring
    of squares two away -- which is the shape worth knowing, and it falls out
    of the general rule rather than being special-cased. Even sizes have no
    true centre square, so the key is the lower-left of the middle four; it
    is still one square per placement, which is all a caller needs.
    """
    xs = [s[0] for s in origin]
    ys = [s[1] for s in origin]
    reach = spread(origin, 1)
    off = (size - 1) // 2
    out: dict[Square, frozenset[Square]] = {}
    for x0 in range(min(xs) - size, max(xs) + 2):
        for y0 in range(min(ys) - size, max(ys) + 2):
            area = frozenset(
                (x0 + dx, y0 + dy) for dx, dy in product(range(size), range(size))
            )
            if area & set(origin):
                continue  # a blast never covers the creature it comes from
            if not (area & reach):
                continue  # and it has to touch it
            out[(x0 + off, y0 + off)] = area
    return out


def blast(origin: frozenset[Square] | set[Square], size: int, aim: Square) -> frozenset[Square]:
    """The close blast `size` aimed at `aim`, or the nearest legal placement."""
    places = blast_placements(origin, size)
    if not places:
        return frozenset()
    if aim in places:
        return places[aim]
    nearest = min(places, key=lambda c: (distance(c, aim), c))
    return places[nearest]


def wall(squares: list[Square]) -> frozenset[Square]:
    """A wall is whatever contiguous squares the caster picked."""
    return frozenset(squares)
