"""Druid, level 1: the encounter attacks.

Two shapes here are new to the package.

**An area wall is not a `Range`.** `p14502` declares the printed ten squares
as its distance and lays the run of squares in the body, which is what
`cleric/level_9.py:p60` does; its targets are then found inside the wall and
struck one at a time with `c.strike(on=...)`, since a `target=` line cannot
name squares that do not exist until the body runs.

**Four rows print a build rider** -- Primal Predator, Primal Guardian,
Primal Swarm. `chargen.BUILDS["druid"]` has one build, `standard`, so there
is no leg for `c.build(...)` to answer about and the rider is left off each
of them rather than folded into the base line. The base line is what is
written; each docstring says which rider is missing, and the report lists
them.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    When,
    Window,
    get,
    power,
    spread,
)
from combat_engine.engine.query import squares

from .forms import burns_at_end, hit_anybody, in_beast_form

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p14500",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
)
def p14500(c: Cast) -> None:
    """The push is an Effect line, so it happens to a target the blast missed
    as well as to one it caught."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.prone()
    c.push(2)


@power(
    "p14501",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
)
def p14501(c: Cast) -> None:
    """Lightly obscured is partial concealment and there is none in this
    engine -- `blocks_sight` is a wall you cannot see through, which is a
    different thing. The patch of ground is real, so it is laid; what it does
    to an attack roll is noted.
    """
    if c.strike():
        c.damage("2d8", c.wis_mod)
    if not c.first:
        return
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.EONT)
        c.note(f"{c.ref}: the burst is lightly obscured for enemies, and there is none here")


@power(
    "p14502",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.POISON, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p14502(c: Cast) -> None:
    """A wall of five squares, laid in the body; see the module note.

    "Constitution or Dexterity modifier" is the fork with no leg to stand
    on, so the larger is taken -- `forms.fork_mod` -- and the poison it does
    is the ending-your-turn kind, which `c.burns` cannot say.
    """
    from .forms import fork_mod

    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-2, 3)]
    blades = [sq for sq in run if c.world.grid.inside(sq)]
    if not blades:
        return
    wall = c.zone(blades, label=c.ref, until=When.EONT)
    burns_at_end(c, wall, fork_mod(c), DamageType.POISON, until=When.EONT)
    c.note(f"{c.ref}: the wall's squares are lightly obscured, and there is no concealment here")
    for who in sorted(c.in_squares(blades)):
        if who == c.me:
            continue
        if c.strike(on=who):
            c.damage("1d10", c.wis_mod, dtype=DamageType.POISON, on=who)
            if c.may("slide the target", who=c.me):
                c.slide(1, on=who)


@power(
    "p2671",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2671(c: Cast) -> None:
    """"If at least one of the attacks hits" is read off the log: the body
    runs once per target against one `Cast` and a local cannot count across
    the calls.

    The Primal Predator rider -- the shift is your Dexterity modifier instead
    of two squares -- is a build the class table does not have.
    """
    landed = bool(c.strike())
    if landed:
        c.damage("1d10", c.wis_mod)
    if c.last and (landed or hit_anybody(c)):
        c.shift(2)


@power(
    "p2688",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        *PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.CHARM, Keyword.PSYCHIC,
    ],
    attack=Attack(WIS, vs=WILL),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2688(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.pull(3)


@power(
    "p2790",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2790(c: Cast) -> None:
    """Half the druid's level, which is nothing at all at this one -- printed,
    and not an omission. The Primal Guardian rider would add Constitution to
    it and there is no such build.

    "Reduced to 0 hit points by this attack" is asked after the damage: a
    creature that is down is no longer bloodied, so the two halves of the
    printed sentence have to be asked in that order.
    """
    if not c.strike():
        return
    c.damage("1d12", c.wis_mod)
    victim = c.target
    from combat_engine.engine.query import alive

    felled = victim is not None and not alive(c.world, victim)
    if (felled or (victim is not None and c.bloodied(victim))) and c.level // 2:
        c.temp_hp(c.level // 2, on=c.me)


@power(
    "p4866",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.POISON, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p4866(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.POISON)
    if not c.first:
        return
    area = c.area()
    if area:
        zone = c.zone(area, label=c.ref, until=When.EONT)
        burns_at_end(c, zone, 5, DamageType.POISON, until=When.EONT)


@power(
    "p4870",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4870(c: Cast) -> None:
    """"Half damage from the **next** attack that damages you" is one blow,
    not a duration, so it is a watch on the roll that spends itself. It is
    not `c.insubstantial`: that halves everything, including the burst this
    row is meant to leave out.

    The Primal Swarm rider -- half damage from every melee and ranged attack
    until the end of your next turn -- is a build the class table lacks.
    """
    if c.strike():
        c.damage("2d6", c.wis_mod)
    if not c.first:
        return
    me = c.me
    spent: list[bool] = []

    def soften(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0 or spent:
            return
        p = get(ev.detail)
        if p is None or p.reach.kind not in ("melee", "ranged"):
            return
        spent.append(True)
        ev.amount //= 2

    c.watch(
        DamageRolled, soften, until=When.EONT, window=Window.BEFORE,
        on=me, label=f"{c.ref} half",
    )


@power(
    "p5041",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p5041(c: Cast) -> None:
    """The Primal Guardian rider -- extra damage equal to Constitution -- is
    a build the class table does not have."""
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.COLD)
        c.immobilized()


@power(
    "p5042",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA],
    attack=Attack(WIS, vs=REF),
)
def p5042(c: Cast) -> None:
    """The rough ground is per target -- "each square adjacent to the target"
    -- so it is laid once for each creature the burst catches rather than
    once for the burst."""
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    c.zone(
        spread(squares(c.world, victim), 1),
        label=c.ref, until=When.EONT, difficult=True,
    )


@power(
    "p9637",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=UpTo(2, "any"),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=REF),
)
def p9637(c: Cast) -> None:
    """"Marked by one of your allies" asks the relation per ally: `c.marked`
    answers for the caster unless told whose mark to look for."""
    if not c.strike():
        return
    c.damage("1d6", c.wis_mod)
    c.prone()
    victim = c.target
    if victim is not None and any(
        c.marked(on=victim, by=friend) for friend in c.allies()
    ):
        c.damage("1d6", on=victim)


@power(
    "p9640",
    level=1,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
)
def p9640(c: Cast) -> None:
    """The Primal Predator rider -- the penalty is 1 + Dexterity instead of
    2 -- is a build the class table does not have."""
    if not c.strike():
        return
    c.damage("1d6", c.wis_mod)
    for d in (AC, FORT, REF, WILL):
        c.penalty(d, 2, until=When.EONT, kind="power")
