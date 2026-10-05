"""Monster abilities, level 12: the one creature that carries no role.

A stat block's numbers load from `game.db`; this is only its behaviour. m1457
is filed under no role at all, so it appears in no role listing and has its
own file.

Two conventions of the levels below apply. A stat block printing no range at
all means melee 1, even for a Large creature -- its reach is a column and the
card's silence is not a reach 2. And a row whose printed Effect *is* a charge
declares `charges=True`: without it the engine measures a sword's reach
before the run and refuses the row whenever the target is further off than
one square, which is every situation a charge is for.

One thing this file had to settle. **A row that makes two of another row's
attacks declares neither an attack nor damage.** Both swings go through the
row the card points at, so its printed numbers stay in one header and
`c.landed` is what answers "if both attacks hit" -- the borrowed row leaves
its result behind for exactly that question.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Damage,
    Melee,
    power,
)

# ==========================================================================
# m1457
# ==========================================================================


@power(
    "m1457a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m1457a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1457a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m1457a1(c: Cast) -> None:
    """It runs in and swings twice, and two landing blows take hold.

    `c.run_at` is the printed move: "up to 8 squares" is this creature's own
    speed, which is a column, and the verb walks into reach of a named
    creature the way a charge's move does rather than wandering its speed in
    no particular direction.

    Both swings are m1457a0, used rather than copied, so the attack and damage
    lines live in one header and this row declares neither. The grab is
    conditional on both of them, which is what `c.landed` is read for after
    each use.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    landed = 0
    for _ in range(2):
        if c.use_power("m1457a0", on=victim, spend=False) and c.landed:
            landed += 1
    if landed >= 2:
        c.grab(on=victim)
