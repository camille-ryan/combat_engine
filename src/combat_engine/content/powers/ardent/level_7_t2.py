"""Ardent, level 7: a strike that strips the target's partial cover.

The printed Special -- usable as a melee basic attack -- is not declared:
`basic.MELEE` is chosen per creature and nothing rewrites which row that is.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)


def _finding_hidden(ctx: dict[str, Any]) -> bool:
    """Is this check the one `p13783`'s Augment 1 pays for?

    Keyed on the **purpose**, not the skill: the engine makes active
    Perception checks for two different things -- finding a trap
    (`actions._searching`) and finding a hidden creature
    (`actions._spotting`) -- and the card names only the second.

    Imported by value rather than compared to a literal so the two cannot
    drift apart.
    """
    from combat_engine.engine.actions import SPOT_PURPOSE

    return ctx.get("purpose") == SPOT_PURPOSE


@power(
    "p13783",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.AUGMENTABLE],
    attack=Attack(CHA, vs=AC),
)
def p13783(c: Cast) -> None:
    """`c.no_cover` sits on the creature being looked at, which is the end the
    card writes from, and its `when` is handed the attack context -- so "on
    attacks made by you or allies adjacent to you" is a gate on `attacker`
    rather than a waiver granted to the whole party. `partial=True` leaves
    superior cover standing, as printed.

    Augment 2 trades the per-attacker waiver for an aura that strips it from
    every enemy standing inside, and hands you combat advantage when the
    target is already beside an ally. The aura's membership is asked when
    the attack is made, so an enemy that walks out of it gets its cover
    back.

    **Augment 1 is offered now, and its own note was the thing blocking
    it.** That note read *"a skill check carries no such purpose to gate on
    -- the bonus would apply to every Perception check the ardent makes"*,
    and `#1111` had already made it false: `purpose` is in the modifier
    context, and that change's comment names this row as one of the two
    markers it exists to unblock. So nothing had to be built here.

    What *was* missing is a Perception check to attach the bonus to. The
    engine made none against a hidden creature -- hiding is contested
    against a **passive** number -- so the only active Perception check in
    the tree was against a trap. `actions._spotting` is the printed minor
    action that fills it, `#1088`, on Camille's correction that the minor
    action is the one for spotting a creature.

    The gate is the purpose and not the skill: a Perception check made to
    find a trap is the same skill and is **not** what this card pays for.

    `augment(c, 1, 2)` rather than two calls -- the helper takes every
    affordable cost at once and answers which was bought, so the decision
    is still taken once per use."""
    spent = augment(c, 1, 2)
    victim = c.target
    if spent == 2 and victim is not None:
        beside = any(a != c.me and c.adjacent_to(victim, a) for a in c.allies())
        if c.strike(advantage=True if beside else None):
            c.damage(c.w(2), c.cha_mod)
    elif c.strike():
        c.damage(c.w(), c.cha_mod)

    def mine_or_a_neighbour(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        if who is None:
            return False
        return who == c.me or (who in c.allies() and c.adjacent(who))

    if spent != 2:
        # "As above" -- Augment 1 keeps the base clause, so this runs for
        # both the unaugmented form and the one-point one.
        c.no_cover(partial=True, until=When.EONT, when=mine_or_a_neighbour)
        if spent == 1:
            # "+5 power bonus to Perception checks made to find hidden
            # creatures until the end of your next turn." The `when=` is
            # what makes it the printed clause rather than a standing
            # bonus to every Perception check -- #1111 put `purpose` in
            # the context and `actions.SPOT_PURPOSE` is what a spot sets.
            c.bonus("skill:perception", 5, kind="power", on=c.me,
                    until=When.EONT, when=_finding_hidden)
        return
    if c.first:
        c.aura(5, label=c.ref, until=When.EONT)
        for foe in c.within(5, side="enemy"):
            c.no_cover(
                partial=True, on=foe, until=When.EONT,
                when=lambda ctx, f=foe: c.in_my_aura(f, label=c.ref),
            )
