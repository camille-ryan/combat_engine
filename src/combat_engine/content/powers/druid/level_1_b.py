"""Druid, level 1: the at-will attacks, second half.

The beast form rows begin here, and they are the shortest in the package:
three of them are a die, a modifier and one rider, and the whole of what
makes them beast form rows is the `requires=` gate in the header.

Two of them print "Special: this power can be used as a melee basic attack",
which has nowhere to go -- see the note in `level_1.py`.

`p9634` prints a second stanza: an opportunity action at range 10 against a
target that takes a provoking action. It is folded in here rather than
declared as a second ref, the way `wizard/level_3.py:p4020` folds its own.
The engine opens an opportunity window only for creatures standing in reach,
so a window ten squares away never opens; what the row watches instead is
**somebody else's** window opening against the target, which is the board's
own record that the target did something provoking.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    EACH_CREATURE,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Melee,
    Moved,
    MoveEnd,
    OpportunityWindow,
    Ranged,
    When,
    power,
    spread,
)
from combat_engine.engine.query import squares

from .forms import (
    at_end_of_its_next_turn,
    burns_if,
    in_beast_form,
    zone_hold,
)

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p5034",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p5034(c: Cast) -> None:
    """No ability modifier on the damage line, which is printed and not an
    omission: this is the one at-will of the set that trades it for an area."""
    if c.strike():
        c.damage("1d6", dtype=DamageType.COLD)
        c.slide(1)


@power(
    "p5036",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5036(c: Cast) -> None:
    """Melee touch is reach 1. The printed Special -- usable as a melee basic
    attack -- has no header field to go in; see `level_1.py`."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.slowed()


@power(
    "p5037",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5037(c: Cast) -> None:
    """"The next creature that attacks it" is as wide as the relation goes in
    one direction: `GRANTS_CA_TO` names beneficiaries, and `to="allies"` is
    the whole of the druid's side. An enemy swinging at its own would not
    benefit, which the printed line would allow.
    """
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.grants_advantage(until=When.EONT, to="allies", once=True)


@power(
    "p5038",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5038(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.slide(1)


@power(
    "p5039",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p5039(c: Cast) -> None:
    """"Doesn't move at least 2 squares" is counted in steps: `Moved` is one
    step with both ends of it, where `MoveEnd` says only that a move finished
    and a creature that shuffles one square has finished one."""
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.LIGHTNING)
    victim = c.target
    if victim is None:
        return
    steps = [0]

    def stepped(ev: Moved) -> None:
        if ev.actor == victim:
            steps[0] += 1

    counting = c.watch(
        Moved, stepped, until=When.ENCOUNTER, on=victim, label=f"{c.ref} steps"
    )

    def judge() -> None:
        if steps[0] < 2:
            c.flat(c.wis_mod, dtype=DamageType.LIGHTNING, on=victim)
        c.world.effects.end(counting, "its turn ended")

    at_end_of_its_next_turn(c, victim, judge)


@power(
    "p5505",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p5505(c: Cast) -> None:
    """The fire bites enemies only, which `c.burns` cannot say -- it bites
    whoever is standing there. `forms.burns_if` is that method with the
    printed filter and the same once-a-turn latch."""
    if not c.strike():
        return
    c.damage("1d6", dtype=DamageType.FIRE)
    victim = c.target
    if victim is None:
        return
    around = spread(squares(c.world, victim), 1)
    zone = c.zone(around, label=c.ref, until=When.EONT)
    foes = set(c.enemies())
    burns_if(
        c, zone, c.wis_mod, DamageType.FIRE,
        ok=lambda who: who in foes, until=When.EONT,
    )


@power(
    "p7411",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA],
    attack=Attack(WIS, vs=FORT),
)
def p7411(c: Cast) -> None:
    """The secondary is printed as an opportunity action and is written as a
    watch on the target's own move: no window opens for a caster ten squares
    off, and the printed trigger is the leaving rather than the provoking.

    Rolled against Reflex through `c.attack`, since `c.strike` rolls the one
    line the header declares.
    """
    area = c.area()
    if c.strike():
        c.damage("1d6", c.wis_mod)
    victim = c.target
    if victim is None or not area:
        return

    def wandered(ev: MoveEnd) -> None:
        if ev.actor != victim or squares(c.world, victim) & area:
            return
        if not c.may("take the opportunity", who=c.me):
            return
        if c.attack(c.wis_, REF, on=victim):
            c.prone(on=victim)

    c.watch(MoveEnd, wandered, until=When.EONT, on=c.me, once=True, label=c.ref)


@power(
    "p9634",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p9634(c: Cast) -> None:
    """The second stanza is folded in; see the module note for why it hangs
    on somebody else's opportunity window rather than on the druid's own.

    Latched to one swing per round, which is what "an opportunity action"
    costs and what a watch does not otherwise charge.
    """
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.FIRE)
    victim = c.target
    if victim is None:
        return
    swung: list[int] = []

    def opening(ev: OpportunityWindow) -> None:
        if ev.provoker != victim or swung[-1:] == [c.world.round]:
            return
        swung.append(c.world.round)
        if c.attack(c.wis_, REF, on=victim):
            c.damage("1d8", c.wis_mod, dtype=DamageType.FIRE, on=victim)

    c.watch(
        OpportunityWindow, opening, until=When.SONT, on=c.me, label=f"{c.ref} again"
    )


@power(
    "p9636",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p9636(c: Cast) -> None:
    """The zone is laid once for the whole blast rather than once per target,
    and its riders follow the enemies walking in and out of it."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    foes = set(c.enemies())
    zone_hold(
        c, zone,
        lambda who: who in foes,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
        until=When.EONT,
    )
