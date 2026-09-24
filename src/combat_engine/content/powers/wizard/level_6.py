"""Wizard, level 6: utility.

Two of these keep themselves alive on a printed Sustain line, so both are
`When.SUSTAIN` with the named action on them; `p1229`'s sustain also has a
*condition* -- the target must still be within 5 squares -- and that half
goes through `c.on_sustain`.

`p1548` prints an area **wall**, which is not one of the shapes a `Range`
can be. Its distance is declared as the ranged 10 the printed line gives
and the run of squares is laid in the body, perpendicular to the line from
the wizard to the square it was pointed at. Its height has nowhere to go:
the board is flat.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Keyword,
    Ranged,
    Relation,
    When,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.dsl import ANY_CREATURE
from combat_engine.engine.zones import Zone

ARCANE = [Keyword.ARCANE]


@power(
    "p1208",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p1208(c: Cast) -> None:
    c.teleport(10)


@power(
    "p1209",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    out_of_combat=True,
)
def p1209(c: Cast) -> None:
    c.note("p1209: you look like somebody else for an hour; touch gives it away")


@power(
    "p1229",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ANY_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p1229(c: Cast) -> None:
    """Unseen by everybody, which is a `HIDDEN_FROM` per enemy.

    Built by hand rather than with `c.invisible`, which always hides the
    caster and takes no sustain cost -- this row hides whoever it was aimed
    at and is kept going with a standard action.

    Attacking already breaks the relations inside `resolve.attack`; the
    effect is ended as well, because the printed line ends the *power*.
    """
    who = c.target
    if who is None:
        return
    watchers = [w for w in c.enemies() if w != who]
    if not watchers:
        return
    veil = c.world.effects.apply(
        who,
        c.me,
        When.SUSTAIN,
        label=f"{c.ref} unseen",
        relations=[(Relation.HIDDEN_FROM, who, w) for w in watchers],
        sustain_cost=STANDARD,
    )

    def gave_itself_away(ev: object) -> None:
        c.world.effects.end(veil, "the target attacked")

    watching = c.on_attack(
        gave_itself_away, by=who, until=When.ENCOUNTER, once=True, label=f"{c.ref} watch"
    )
    veil.on_end.append(lambda: c.world.effects.end(watching, "the power ended"))

    def still_close() -> None:
        if c.distance(to=who) > 5:
            c.world.effects.end(veil, "out of range to sustain")

    c.on_sustain(veil, still_close)


@power(
    "p1548",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p1548(c: Cast) -> None:
    """Eight squares of fog that nothing sees through.

    `blocks_sight` is the whole of "heavily obscured and blocks line of
    sight" -- `cover_between` reads it for every attack across the squares.
    """
    anchors = sorted(
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, "where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    # Laid across the wizard's line of sight to the square it was aimed at,
    # which is the only placement the caller is not being asked to describe
    # square by square.
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [
        (anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-3, 5)
    ]
    wall = [sq for sq in run if c.world.grid.inside(sq)]
    if wall:
        c.zone(wall, label=c.ref, until=When.SUSTAIN, sustain=MINOR, blocks_sight=True)


@power(
    "p2273",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=WILL),
)
def p2273(c: Cast) -> None:
    """A zone or a conjuration is not a creature, so it cannot be a printed
    target here -- the row aims at one itself and rolls against whoever made
    it, which is what the printed Attack line says anyway.

    "All its effects end, including those that normally last until a target
    saves" is read as every live effect the same caster laid under the same
    label: that is how a zone's riders are named, and nothing else ties a
    save-ends effect back to the ground it came from.
    """
    reach = spread({c.here}, 10)
    found: list[tuple[int, int, str, str]] = []
    for zid, zone in c.world.zones.all():
        if zone.squares & reach:
            found.append((zid, zone.owner, zone.label, "zone"))
    for eid, conj in c.world.each(Conjuration):
        if c.distance(to=eid) <= 10:
            found.append((eid, conj.by, conj.ref, "conjuration"))
    picked = c.choose(sorted(found), "what to unmake")
    if picked is None:
        return
    which, owner, label, kind = picked
    if not c.strike(on=owner):
        return
    for effect in list(c.world.effects.live.values()):
        if effect.source == owner and label and label in effect.label:
            c.world.effects.end(effect, c.ref)
    if kind == "zone" and c.world.get(which, Zone) is not None:
        c.world.zones.end(which, c.ref)
    c.note(f"p2273: the {kind} is unmade")
