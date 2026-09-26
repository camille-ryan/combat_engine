"""Warden, level 1: the guardian forms.

Each of these ids is the *form* -- a minor action that holds until the
encounter ends. Every one of them also prints a second stat block, an
attack usable once while the form is up, and **none of those attacks has an
id of its own in the spec**, so none is written here. `in_form` is their
Requirement line, ready for when they do.

A form is written as a stance: being in one is being in no other, which is
the only part of "polymorph" the engine has to know, and `c.form` cannot
say it. What the form grants is bound to the stance by `while_in`, so
taking another shape puts the old shape's bonuses down.
"""

from __future__ import annotations

from combat_engine.engine import *

from . import assume, while_in

POLYMORPH = [Keyword.PRIMAL, Keyword.POLYMORPH]


@power(
    "p11072",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.POLYMORPH],
)
def p11072(c: Cast) -> None:
    """"Until the mark ends" has no duration to name, and a warden's mark
    runs to the end of its next turn, so that is what the vulnerability
    gets. The class feature that lays the mark has no ref on the chassis,
    so the watch answers any mark this warden lays."""
    form = assume(c)

    def on_mark(ev: ConditionApplied) -> None:
        if ev.source == c.me and ev.condition is Condition.MARKED:
            c.vulnerable(3, DamageType.FIRE, on=ev.target, until=When.EONT)

    while_in(
        c,
        form,
        c.resist(5, DamageType.FIRE),
        c.watch(ConditionApplied, on_mark, until=When.ENCOUNTER),
    )


@power(
    "p5103",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5103(c: Cast) -> None:
    """"If the attack already pushes, the distance increases by 1" comes out
    as a second push of 1 rather than a longer one: the shove has already
    resolved by the time the hit is announced."""
    form = assume(c)

    def on_hit(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker == c.me and p is not None and p.usage is Usage.AT_WILL:
            c.push(1, on=ev.target)

    while_in(
        c,
        form,
        c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER),
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: bool(ctx.get("charge")),
        ),
        c.watch(Hit, on_hit, until=When.ENCOUNTER),
    )


@power(
    "p5104",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5104(c: Cast) -> None:
    """"You can shift 2 squares as a move action" is a granted row and the
    form's shift has no id, so it is left out rather than approximated."""
    form = assume(c)
    while_in(
        c,
        form,
        c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.bonus(
            "attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: ctx.get("target") is not None and c.marked(ctx["target"]),
        ),
    )


@power(
    "p5105",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5105(c: Cast) -> None:
    """The second half -- "any ally gains +2 Fortitude while adjacent to
    you" -- is an aura that carries a modifier, and an aura carries none."""
    form = assume(c)
    while_in(c, form, c.immovable(on=c.me, until=When.ENCOUNTER))


@power(
    "p5106",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.COLD, Keyword.POLYMORPH],
)
def p5106(c: Cast) -> None:
    """The rough ground within 2 squares moves with the warden, which is an
    aura; `c.aura` takes no `difficult`, and a fixed `c.zone` would be a
    different power."""
    form = assume(c)
    while_in(
        c,
        form,
        c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.resist(5, DamageType.COLD),
    )


@power(
    "p5532",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.POISON, Keyword.POLYMORPH],
)
def p5532(c: Cast) -> None:
    form = assume(c)
    while_in(
        c,
        form,
        c.resist(5, DamageType.POISON),
        c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="untyped"),
    )


@power(
    "p5575",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5575(c: Cast) -> None:
    """Swamp walk is the printed "ignores difficult terrain that is mud or
    shallow water", said once per word."""
    form = assume(c)

    def on_drop(ev: Dropped) -> None:
        if ev.source != c.me or not c.marked(ev.actor):
            return
        near = [e for e in c.within(5, side="enemy") if e != ev.actor]
        if near:
            c.mark(on=c.choose(near, "who the mark moves to"), until=When.EONT)

    while_in(
        c,
        form,
        c.ignores_difficult("mud", on=c.me, until=When.ENCOUNTER),
        c.ignores_difficult("water", on=c.me, until=When.ENCOUNTER),
        c.mode("swim", c.speed_of(), until=When.ENCOUNTER),
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx: ctx.get("target") is not None
            and c.is_(Condition.IMMOBILIZED, ctx["target"]),
        ),
        c.watch(Dropped, on_drop, until=When.ENCOUNTER),
    )


@power(
    "p5576",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p5576(c: Cast) -> None:
    """Two of the three clauses have nowhere to go: a saving-throw bonus
    cannot be told which kind of effect it is saving against, and "allies
    have combat advantage against any enemy adjacent to you" is a grant that
    follows the warden around rather than one made when the form is taken."""
    form = assume(c)
    while_in(c, form, c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="untyped"))


@power(
    "p9822",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=POLYMORPH,
)
def p9822(c: Cast) -> None:
    """The flanking clause is granted to whoever is within 2 when the form is
    taken; it is printed as a radius that keeps being asked, and there is no
    aura that carries an effect."""
    form = assume(c)
    held = [c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)]
    held += [
        c.cannot_be_flanked(on=a, until=When.ENCOUNTER)
        for a in c.within(2, side="ally")
        if a != c.me
    ]
    while_in(c, form, *held)


@power(
    "p9825",
    level=1,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.LIGHTNING, Keyword.THUNDER, Keyword.POLYMORPH],
)
def p9825(c: Cast) -> None:
    form = assume(c)
    spent = {"round": -1}

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or spent["round"] == c.world.round:
            return
        p = get(ev.power)
        if p is None or p.reach_of().kind != "melee":
            return
        if ev.target in c.enemies():
            spent["round"] = c.world.round
            for e in c.enemies():
                if c.marked(e):
                    c.flat(c.str_mod, dtype=DamageType.THUNDER, on=e)

    while_in(
        c,
        form,
        c.resist(3),
        c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.watch(Hit, on_hit, until=When.ENCOUNTER),
    )
