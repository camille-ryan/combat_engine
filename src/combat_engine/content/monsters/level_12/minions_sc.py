"""Monster abilities, level 12: the five rows that copy somebody else's power.

A stat block's numbers load from `game.db`; this is only its behaviour.

All five print the same sentence -- the creature rolls its own attack line
and the target "takes damage and is subject to effects as though it were hit
by the chosen attack", off the ability modifier of whoever the power was
taken from. `c.as_though_hit_by` is that sentence: the borrowed body runs
with its owner as the caster, so the owner's weapon and modifier are the ones
that pay, and the borrowed attack lands rather than being rolled again.

**The choice is remade each use.** The printed line chooses once, when the
creature first acts, and nothing on a creature holds a power ref between
uses of a row. With the same enemies in sight the decider answers the same
way, so the outcome is the printed one; if the chosen enemy dies the copy
moves on, which is the only place the two readings part.

**The second half of the Effect is dropped.** "If it was created by an
m4967, choose a power belonging to the enemy that creature hit" needs the
board to remember which blow made this creature, and nothing records it.
The first half -- any at-will of a visible enemy -- is what is written.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Melee,
    Ranged,
    power,
)


def _borrowed(c: Cast, *, melee: bool) -> str:
    """One at-will attack of a visible enemy, of the printed reach."""
    options: set[str] = set()
    for foe in c.enemies():
        if c.can_see(foe):
            options.update(c.borrowed_rows(foe, melee=melee))
    if not options:
        return ""
    return c.choose(sorted(options), "which power to copy") or ""


def _copies(c: Cast, *, melee: bool) -> None:
    """Swing with this creature's own line, then pay out the borrowed one.

    There is no damage in the header because the card prints none: every
    number the row deals belongs to the power it copied. A board with no
    enemy at-will of the right reach on it leaves the row with nothing to
    pay, which is what the printed sentence comes to there.
    """
    if not c.strike():
        return
    chosen = _borrowed(c, melee=melee)
    if chosen:
        c.as_though_hit_by(chosen)


@power(
    "m4968a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
)
def m4968a3(c: Cast) -> None:
    _copies(c, melee=True)


@power(
    "m4969a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
)
def m4969a3(c: Cast) -> None:
    _copies(c, melee=True)


@power(
    "m4970a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
)
def m4970a2(c: Cast) -> None:
    _copies(c, melee=False)


@power(
    "m4971a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
)
def m4971a3(c: Cast) -> None:
    _copies(c, melee=True)


@power(
    "m4972a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
)
def m4972a3(c: Cast) -> None:
    _copies(c, melee=False)
