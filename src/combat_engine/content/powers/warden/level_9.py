"""Warden, level 9: the guardian forms.

As at level 1, each id is the form and not the attack the form unlocks --
those attacks carry no id of their own in the spec. Several forms also
grant an action ("you can use your second wind as a minor action", "you
can fly your speed as a move action"), which is a row being handed out and
so needs a ref to hand out; those clauses are left rather than guessed at.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import ForcedMove

from . import assume, while_in

POLYMORPH = [Keyword.PRIMAL, Keyword.POLYMORPH]


def _burning(c: Cast, who: int) -> bool:
    return any(eff.ongoing for eff in c.world.effects.of(who))


@power(
    "p11078",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.THUNDER, Keyword.POLYMORPH],
)
def p11078(c: Cast) -> None:
    """The altitude limit and the hover have nowhere to go; `c.mode` knows
    how fast a creature flies and nothing else about it."""
    form = assume(c)

    def buffet(ev: TurnStart) -> None:
        if ev.actor != c.me and c.adjacent(ev.actor) and c.may("shove it", who=c.me):
            c.slide(1, on=ev.actor)

    while_in(
        c,
        form,
        c.mode("fly", 4, on=c.me, until=When.ENCOUNTER),
        c.watch(TurnStart, buffet, until=When.ENCOUNTER),
    )


@power(
    "p5126",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5126(c: Cast) -> None:
    form = assume(c)
    thorns = 2 * c.str_mod if c.level >= 21 else c.str_mod

    def gore(ev: Hit) -> None:
        if ev.target != c.me or ev.attacker == c.me:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind == "melee":
            c.flat(thorns, on=ev.attacker)

    while_in(
        c,
        form,
        c.bonus("reach", 1, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.watch(Hit, gore, until=When.ENCOUNTER),
    )


@power(
    "p5127",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5127(c: Cast) -> None:
    form = assume(c)

    def hunting(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and (c.bloodied(who) or _burning(c, who))

    while_in(
        c,
        form,
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER,
            kind="untyped", when=hunting,
        ),
    )


@power(
    "p5128",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.POLYMORPH],
)
def p5128(c: Cast) -> None:
    """"As if you had spent a healing surge" is the hit points without the
    surge. Regeneration is a heal at the start of each of the warden's
    turns, which is what the rule is."""
    c.heal(c.surge_value(c.me), on=c.me)
    form = assume(c)
    mending = c.con_mod

    def regenerate(ev: TurnStart) -> None:
        if ev.actor == c.me and mending > 0:
            c.heal(mending, on=c.me)

    while_in(c, form, c.watch(TurnStart, regenerate, until=When.ENCOUNTER))


@power(
    "p5129",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.LIGHTNING, Keyword.POLYMORPH],
)
def p5129(c: Cast) -> None:
    """The flight is a move action that must end on the ground; `c.mode`
    grants a speed and nothing that has to be landed, so giving it would be
    granting more than the line does."""
    form = assume(c)
    while_in(c, form, c.resist(5, DamageType.LIGHTNING))


@power(
    "p5579",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.POLYMORPH],
)
def p5579(c: Cast) -> None:
    form = assume(c)
    while_in(
        c,
        form,
        c.resist(10, DamageType.FIRE),
        c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="untyped"),
    )


@power(
    "p9855",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p9855(c: Cast) -> None:
    """Moving through enemies' spaces *while shifting* is phasing with a
    condition on it, and `c.phasing` has no condition."""
    form = assume(c)
    while_in(c, form, c.resist(5))


@power(
    "p9858",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p9858(c: Cast) -> None:
    """Deepening the flanking bonus from +2 to +4 is a change to what combat
    advantage is worth, which is in the resolver rather than in any
    modifier a row can hang."""
    form = assume(c)
    while_in(c, form, c.mode("swim", c.speed_of(), on=c.me, until=When.ENCOUNTER))


@power(
    "p9859",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.POLYMORPH],
)
def p9859(c: Cast) -> None:
    form = assume(c)

    def share(ev: SurgeSpent) -> None:
        if ev.actor != c.me:
            return
        for a in c.within(2, side="ally"):
            if a != c.me:
                c.heal(5, on=a)

    while_in(
        c,
        form,
        c.resist(5, DamageType.NECROTIC),
        c.bonus(FORT, 2, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.watch(SurgeSpent, share, until=When.ENCOUNTER),
    )


@power(
    "p9860",
    level=9,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p9860(c: Cast) -> None:
    """A shove is negotiated on `ForcedMove` before it happens, and the
    distance is read back off the event, so lengthening one is a listener in
    the interrupt window rather than a modifier."""
    form = assume(c)

    def harder(ev: ForcedMove) -> None:
        if ev.source == c.me and ev.how in (Forced.PUSH, Forced.SLIDE):
            ev.squares += 1

    while_in(
        c,
        form,
        *[
            c.bonus(
                d, 2, on=c.me, until=When.ENCOUNTER, kind="untyped",
                when=lambda _ctx: c.bloodied(c.me),
            )
            for d in (AC, FORT, REF, WILL)
        ],
        c.watch(ForcedMove, harder, until=When.ENCOUNTER, window=Window.BEFORE),
    )
