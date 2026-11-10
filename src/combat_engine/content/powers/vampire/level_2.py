"""Vampire, level 2: the two minor-action utilities.

Both are a close blast 5 aimed at one creature in it, both lay a condition on
that creature until a turn boundary, and both end with "+4 bonus to the next
<skill> check you make against the target before the end of the encounter" --
which is `next_check` in this package, for the reason its docstring gives.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    Cast,
    CloseBlast,
    Keyword,
    OpportunityWindow,
    When,
    Window,
    power,
)

from . import next_check


@power(
    "p13855",
    level=2,
    cls="vampire",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.SHADOW],
    dropped=("c.no_immediate()",),
)
def p13855(c: Cast) -> None:
    """Half of the first clause lands and half of it has no gate.

    An opportunity attack is refused by cancelling `OpportunityWindow` before
    it opens, which is what `wizard/level_3.py`'s `p12743` does for the same
    printed sentence. Taking an *immediate* action is the half with nowhere
    to say it: `query.can_react` reads `Rules.no_reactions`, which is
    reachable only through daze and stun, and both of those carry a great
    deal this card does not print. `p5857` and `p12743` each say so in their
    own docstrings, so the symbol names the flag rather than a verb.

    The second clause is whole. One +4 between the two skills, spent by
    whichever check comes first, and only against this creature.
    

    **The marker is `c.no_immediate()` and not `Rules.no_reactions`, which
    is the field it needs.** That field exists, so naming it made
    `todo.py` report ARRIVED and go red -- the gate is built to fire when a
    wanted symbol lands, and a marker naming something already present can
    never be satisfied by anybody. The gap is a **writer**: `no_reactions`
    is set by `Condition.DAZED`, `DOMINATED` and `STUNNED` and by nothing
    else, so there is no way to deny one creature its immediate actions
    without also taking away its action or granting combat advantage,
    neither of which this card says.

    Checked and rejected: `c.immediate_actions()`, which `m3471a4` carries,
    is the opposite question -- making an action *cheaper* and twice a
    round -- so reusing it would have put two different gaps under one
    symbol. Spelled after `c.no_provoke` / `c.no_basic`, the convention for
    a denial in this tree. #1225.
    """
    victim = c.target
    if victim is None:
        return

    def refuse(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            ev.cancel("cannot take opportunity actions")

    c.watch(
        OpportunityWindow,
        refuse,
        until=When.EONT,
        window=Window.BEFORE,
        on=victim,
        label=f"{c.ref} refuses openings",
    )
    next_check(
        c, 4, "skill:bluff", "skill:diplomacy",
        until=When.ENCOUNTER, against=victim,
    )
    if c.first:
        c.note(f"{c.ref}: immediate actions are also barred, and nothing gates those")


@power(
    "p13856",
    level=2,
    cls="vampire",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.SHADOW],
)
def p13856(c: Cast) -> None:
    """"While you are adjacent to it" is a live question rather than a
    duration, so this is the gated form of `c.grants_advantage`: a `Relation`
    carries no predicate and `query.advantage` short-circuits True the moment
    one holds, so the condition goes in a `Mod` the combat-advantage context
    is read against. The method's own docstring names 15 rows of this shape.

    The predicate asks the board rather than the context, because the printed
    clause is about where the two of them are standing now and not about the
    attack being rolled.
    """
    victim = c.target
    if victim is None:
        return
    c.grants_advantage(
        on=victim,
        to=c.me,
        until=When.SONT,
        when=lambda ctx: c.adjacent(victim),
    )
    next_check(c, 4, "skill:intimidate", until=When.ENCOUNTER, against=victim)
