"""Wizard, level 10: utility. Nothing here rolls an attack.

`p1231`'s bonus is one `Mod` that is written down rather than a stack of
three: the printed line reduces it by 2 at a time and ends the power when it
reaches 0, and three separate +2s of the same kind would come to +2 rather
than +6 -- same-named bonuses do not add, the larger wins.

`p513` maintains its relations rather than setting them once. Being unseen
is `HIDDEN_FROM` per enemy, and which enemies qualify changes every time
anybody walks, so the set is recomputed on `MoveEnd` and torn down with the
effect. Only the pairs this row laid are cleared, so a rogue hiding in the
same fight keeps its own.

The level's fourth row is left out; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Cast,
    DamageType,
    Keyword,
    Miss,
    Mod,
    MoveEnd,
    Ranged,
    Relation,
    Target,
    When,
    power,
)

ARCANE = [Keyword.ARCANE]
ARCANE_ILLUSION = [Keyword.ARCANE, Keyword.ILLUSION]


@power(
    "p1231",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_ILLUSION,
)
def p1231(c: Cast) -> None:
    """"Otherwise the effect lasts for 1 hour" is the encounter: there is no
    longer clock on this board, and the images are gone before it in any
    fight where three attacks miss."""
    images = Mod(what=AC.value, value=6, kind="power", label=c.ref)
    veil = c.world.effects.apply(
        c.me, c.me, When.ENCOUNTER, label=c.ref, mods=[(c.me, images)]
    )

    def popped(ev: Miss) -> None:
        if ev.target != c.me or veil.ended:
            return
        images.value -= 2
        if images.value <= 0:
            c.world.effects.end(veil, "the last image is gone")

    veil.subs.append(c.world.bus.on(Miss, popped, owner=c.me))


@power(
    "p2274",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=Target("any", 1, label="You or one creature"),
    keywords=ARCANE,
)
def p2274(c: Cast) -> None:
    """The printed list is every damage type there is bar untyped, which is
    not one a creature can be resistant to."""
    kinds = [d for d in DamageType if d is not DamageType.UNTYPED]
    kind = c.choose(kinds, "p2274: which damage type")
    if kind is not None:
        c.resist(c.level + c.int_mod, kind, until=When.ENCOUNTER, on=c.target)


@power(
    "p513",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_ILLUSION,
)
def p513(c: Cast) -> None:
    me = c.me
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, kind="power")

    unseeing: set[int] = set()
    veil = c.world.effects.apply(me, me, When.ENCOUNTER, label=f"{c.ref} unseen")

    def lift() -> None:
        for watcher in sorted(unseeing):
            c.world.relations.clear(Relation.HIDDEN_FROM, me, watcher, "the veil lifted")
        unseeing.clear()

    def redraw(_ev: object = None) -> None:
        if veil.ended:
            return
        for foe in c.enemies():
            far = c.distance(to=foe) >= 5
            if far and foe not in unseeing:
                c.world.relations.set(Relation.HIDDEN_FROM, me, foe)
                unseeing.add(foe)
            elif not far and foe in unseeing:
                c.world.relations.clear(
                    Relation.HIDDEN_FROM, me, foe, "close enough to see"
                )
                unseeing.discard(foe)

    veil.subs.append(c.world.bus.on(MoveEnd, redraw, owner=me))
    veil.on_end.append(lift)
    redraw()
