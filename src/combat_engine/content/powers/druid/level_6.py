"""Druid, level 6: the utilities, first half.

Three rows of this level are absent and all three want the same missing
thing in different words -- a row for wild shape to extend, an object to
step inside, a named row to hand back a use of. See the report.

**"+1 to Charisma attack rolls" is a gate on the row that is rolling**, read
off its printed attack line: the attack context carries the ref and nothing
else about which ability is being used.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    Ability,
    Cast,
    CloseBurst,
    Event,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.query import distance_between, team

from .forms import ends_with, in_beast_form

PRIMAL = [Keyword.PRIMAL]
BEAST_FORM = "you must be in beast form"


def _attacks_with(ability: Ability) -> Any:
    """"A Charisma attack roll", read off the row being rolled."""

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", "") or "")
        line = p.attack if p is not None else None
        return line is not None and line.ability is ability

    return gate


def _ally_crit_within_10(world: World, me: int, ev: Event) -> bool:
    """An ally -- not you -- within 10 squares scored a critical hit."""
    who = getattr(ev, "attacker", None)
    if who is None or who == me or not getattr(ev, "critical", False):
        return False
    if team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "p10371",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
)
def p10371(c: Cast) -> None:
    """A polymorph rather than a beast form, so it wears its own label and
    the beast form rows stay shut while it is on. Stealth is a check and
    nothing in this engine falls.
    """
    shape = c.form(modes={"climb": c.speed_of()}, until=When.ENCOUNTER, revert=FREE,
                   label=c.ref)
    ends_with(c, shape, c.cannot_attack(on=c.me, until=When.ENCOUNTER))
    c.note(f"{c.ref}: +5 to Stealth, and twenty feet off any fall")


@power(
    "p12834",
    level=6,
    cls="druid",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=PRIMAL,
    trigger="an ally in the burst scores a critical hit",
    on=Trigger(
        Hit, when=_ally_crit_within_10, text="an ally scores a critical hit"
    ),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p12834(c: Cast) -> None:
    """The critical is read off the event -- `Hit.critical` -- rather than
    asked about afterwards, which is too late to know."""
    c.temp_hp(5 + max(0, c.con_mod))


@power(
    "p13520",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13520(c: Cast) -> None:
    c.bonus("attack", 1, until=When.ENCOUNTER, kind="power", when=_attacks_with(Ability.CHA))
    c.bonus(WILL, 1, until=When.ENCOUNTER, kind="power")
    c.note(f"{c.ref}: +2 to Charisma-based checks")


@power(
    "p13521",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13521(c: Cast) -> None:
    """Low-light vision has nothing to read it: there is no light level and
    concealment is not modelled."""
    c.bonus(WILL, 1, until=When.ENCOUNTER, kind="power")
    c.note(f"{c.ref}: low-light vision, and +2 to Wisdom-based checks")


@power(
    "p13522",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13522(c: Cast) -> None:
    c.bonus("attack", 1, until=When.ENCOUNTER, kind="power", when=_attacks_with(Ability.INT))
    c.note(f"{c.ref}: training in one skill, and +2 to Intelligence-based checks")


@power(
    "p14509",
    level=6,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p14509(c: Cast) -> None:
    who = c.target
    if who is None:
        return
    c.bonus("speed", 2, until=When.ENCOUNTER, kind="power")
    c.ignores_difficult(on=who, until=When.ENCOUNTER)


@power(
    "p16121",
    level=6,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=SELF,
    keywords=PRIMAL,
)
def p16121(c: Cast) -> None:
    """Six pillars, as conjurations: a conjuration occupies its square and
    nothing walks through it, which is what blocking terrain means here.

    Their defences and hit points have nowhere to go -- a conjuration is not
    a creature and cannot be attacked -- so neither has the rubble that a
    felled one would leave. The squares they stand in are the whole of what
    a board can say.
    """
    room = [
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and sq != c.here
    ]
    if not room:
        return
    # Ranked by what each square would pen in. With nobody playing, the
    # first option is the answer, and sorted plainly that is the low corner
    # of the board ten squares away.
    room.sort(key=lambda sq: (-len(c.in_squares(spread({sq}, 1), side="enemy")), sq))
    for where in room[:6]:
        c.conjure(where, label=c.ref, until=When.ENCOUNTER, sustain=None)
    c.note(f"{c.ref}: each pillar has 30 hit points, and nothing here can attack one")


@power(
    "p2730",
    level=6,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p2730(c: Cast) -> None:
    """"Until he or she moves" is the shorter of the two clocks and has to be
    watched for; `c.invisible` holds only the longer one."""
    who = c.target
    if who is None:
        return
    hidden = c.invisible(on=who, until=When.EONT)
    if hidden is None:
        return

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == who and not hidden.ended:
            c.world.effects.end(hidden, "the target moved")

    c.watch(MoveEnd, stirred, until=When.EONT, on=c.me, once=True, label=c.ref)
