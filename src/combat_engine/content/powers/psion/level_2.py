"""Psion, level 2: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Cast,
    Hit,
    Keyword,
    Ranged,
    Target,
    Trigger,
    When,
    power,
    targets_me,
)
from combat_engine.engine.events import TurnEnd
from combat_engine.engine.query import distance_between
from combat_engine.engine.types import Condition

PSIONIC = [Keyword.PSIONIC]


@power(
    "p11273",
    level=2,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(
        "any", 1, objects=True,
        any_of=(
            Target("ally"),
            Target("enemy", conditions={Condition.HELPLESS}),
            Target("object", loose=True, max_weight=400),
        ),
        label="One ally, helpless enemy, or object of 400 pounds or less",
    ),
    keywords=PSIONIC,
    dropped=("c.endable(also=)",),
)
def p11273(c: Cast) -> None:
    """Held aloft: the immobilisation is refreshed each time the hold is
    sustained, which is what the printed Sustain Minor line does. The
    free-action and minor-action ways of letting go are dropped -- ending an
    effect early is not in `Cast`.

    **"One ally, helpless enemy, or object": all three are aimed at now.**
    Three pools, one of them a narrowed enemy, which is the shape
    `objects=True` could not reach -- that field unions *one* extra pool.
    `#1313` made an alternative's own `side` the thing that is read, so the
    outer `side="any"` builds the pool and each alternative narrows it:

        any_of=(ally, helpless enemy, object <= 400lb and unattended)

    The clauses sit on the alternative they are printed against. "400
    pounds or less and isn't carried by another creature" qualifies the
    **object** and nothing else -- an ally is not weighed -- so they moved
    off the outer target, where they had been applying to all three. #1216,
    #1307, #1313.

    **"It ends if you end your turn out of range of the target" lands**, as
    a `TurnEnd` watch on the caster that measures against the printed
    Ranged 10 and ends the spine. Two wizard rows already read "out of
    range" this way. The watch outlives the hold by design -- it is keyed
    on the hold still being live, so it costs nothing once the effect is
    gone.

    **Marked for the one printed line that cannot be written: two creatures
    may end this effect, at two different costs.** *"You can end this
    effect as a free action ... If the target is a creature, it can end the
    effect as a minor action."* An `Effect` carries a single `drop_cost`
    and a single `drop_by`, so only one of the two can be declared. The
    hold sits on the **target** -- `c.effect` defaults `on` to `c.target`
    -- and `actions.legal` offers a `drop` to the owner, so the target's
    minor action is the half that comes for free and is written. The
    caster's free action is the half that is missing, and `c.endable(also=)`
    is what an author would reach for. #1327.

    **"400 pounds or less" is declared now**, as `max_weight=400` -- a
    printed number on this card, where `p11358`'s *"you can lift"* is a
    printed *phrase* and becomes `liftable=True`, read against
    `query.lift_limit`. Two fields for the two shapes.

    **No object is offered today and that is correct**, not a gap:
    `Scenery.weight` is `0` meaning *not recorded* and an unweighed thing
    passes neither clause. What a crate should weigh is the `question` on
    `#1307`.
    """
    victim = c.target
    if victim is None:
        return
    c.slide(3)
    c.immobilized(until=When.EONT)

    def aloft() -> None:
        c.immobilized(on=victim, until=When.EONT)
        c.slide(3, on=victim)

    spine = c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR)
    c.on_sustain(spine, aloft)
    # "If the target is a creature, it can end the effect as a minor
    # action." The hold sits on the target, and `actions.legal` offers the
    # drop to an effect's owner, so this needs no `by=`. The caster's
    # free-action half wants a second dropper at a second cost and is what
    # the marker names.
    c.endable(spine, MINOR)

    # "It ends if you end your turn out of range of the target." Measured
    # against the printed Ranged 10 at the moment the caster's turn ends,
    # which is what the line says -- not continuously, so carrying the
    # target out of range and back inside one turn does not break it.
    def strayed(ev: TurnEnd) -> None:
        if ev.actor != c.me or spine is None or spine.ended:
            return
        if distance_between(c.world, c.me, victim) > 10:
            c.world.effects.end(spine, "ended the turn out of range")

    c.watch(TurnEnd, strayed, until=When.SUSTAIN, label=f"{c.ref} in range")


@power(
    "p11274",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p11274(c: Cast) -> None:
    c.teleport(1 + c.wis_mod)


@power(
    "p13313",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p13313(c: Cast) -> None:
    c.note("p13313: +5 to checks with one skill the ally is trained in")


@power(
    "p13316",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13316(c: Cast) -> None:
    """Superior cover is written as the +5 to AC and Reflex it grants: `Cast`
    has no way to hand a creature cover as a geometric property."""
    c.bonus(AC, 5, on=c.me, until=When.EONT, kind="cover")
    c.bonus(REF, 5, on=c.me, until=When.EONT, kind="cover")
    c.slowed(on=c.me, until=When.EONT)


@power(
    "p8231",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p8231(c: Cast) -> None:
    chosen = c.choose([AC, FORT, REF, WILL], f"{c.ref}: which defence")
    if chosen is not None:
        c.bonus(chosen, c.cha_mod, on=c.me, until=When.EONT, kind="power")


@power(
    "p8232",
    level=2,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p8232(c: Cast) -> None:
    c.note("p8232: +3 to checks with one chosen skill, until the fight ends")
