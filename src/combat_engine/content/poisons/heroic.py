"""The seven heroic doses. See the package docstring for the shape,
the delivery test that keeps four of the eleven out, and the two
clause shapes. #1452.
"""
from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    FORT,
    ONE_CREATURE,
    WILL,
    ActionType,
    Attack,
    Cast,
    Condition,
    DamageType,
    Effect,
    Melee,
    When,
    power,
)

#: The printed ongoing damage every level-5 dose here deals, as the pair
#: `c.condition(ongoing=)` takes. Named once because four rows print it.
_VENOM_5 = (5, DamageType.POISON)
#: The level-10 doses' ongoing poison. Same number, different band.
_VENOM_10 = (5, DamageType.POISON)


def _poisoned(c: Cast, *conditions: Condition,
              ongoing: tuple[int, DamageType] | None = None) -> Effect | None:
    """Lay the dose's hold on whoever the coated weapon hit.

    `on=c.target` rather than a bare call, so the hold lands on the
    creature the dose attacked whichever way the row was reached -- aimed
    by `dsl.use` on a board, or named by `i2061p2`'s bite, which sets the
    target on the `Cast` it builds.
    """
    if c.target is None:
        return None
    return c.condition(*conditions, until=When.SAVE_ENDS, on=c.target,
                       ongoing=ongoing)


@power("x4_1", cls="poison", level=5, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=5))
def x4_1(c: Cast) -> None:
    """*"+5 vs. Fortitude; ongoing 5 poison damage and immobilized (save
    ends both). Aftereffect: The target is immobilized (save ends)."*

    `+5` and not `+8`: this is the one level-5 dose whose printed bonus is
    three lower than its five siblings', which is exactly the sort of
    number a careless copy would even out. Read off the page.
    """
    if not c.strike():
        return
    held = _poisoned(c, Condition.IMMOBILIZED, ongoing=_VENOM_5)
    victim = c.target
    if held is not None and victim is not None:
        c.aftereffect(
            held,
            lambda: c.condition(Condition.IMMOBILIZED,
                                until=When.SAVE_ENDS, on=victim),
        )


@power("x4_2", cls="poison", level=5, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=8))
def x4_2(c: Cast) -> None:
    """*"+8 vs. Fortitude; ongoing 5 poison damage and slowed (save ends
    both)."* The whole card, with no escalation and no aftereffect."""
    if c.strike():
        _poisoned(c, Condition.SLOWED, ongoing=_VENOM_5)


@power("x4_3", cls="poison", level=5, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=8))
def x4_3(c: Cast) -> None:
    """*"ongoing 5 poison damage and slowed (save ends both). First Failed
    Saving Throw: immobilized instead of slowed. Second Failed Saving
    Throw: stunned instead of immobilized."*

    `x4_2`'s card with a two-step escalation on top, and the steps
    **replace** -- "instead of" -- so each ends the standing hold and
    re-lays it carrying the ongoing damage forward. `m108a0` prints the
    same structure and is where this shape comes from.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def stun(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.STUNNED, until=When.SAVE_ENDS, on=eff.owner,
                    ongoing=_VENOM_5)

    def pin(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS,
                    on=eff.owner, ongoing=_VENOM_5, escalate=stun)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
                ongoing=_VENOM_5, escalate=pin)


@power("x4_4", cls="poison", level=10, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=WILL, printed=13))
def x4_4(c: Cast) -> None:
    """*"+13 vs. **Will**; the target is weakened (save ends). First Failed
    Saving Throw: The target is also dominated (save ends both). Second
    Failed Saving Throw: The target also takes ongoing 10 fire damage
    (save ends all)."*

    **Against Will, and the only dose here that is.** Six of the seven
    attack Fortitude, which is what a copied header would have given it.

    *"Also"* in both escalations, not *"instead of"* -- so this is
    `c.worsen`, which adds a condition to the standing hold and keeps one
    saving throw against the whole sentence. `x4_3` is the opposite shape
    and the two are a square foot apart in this file on purpose.

    The ongoing fire is hung on the same effect by the second step, for
    the reason the module docstring gives: *"save ends all"* is one throw.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def burn(eff: Effect) -> None:
        # The third step adds damage rather than a condition, so it goes
        # on the effect directly -- `c.worsen` carries conditions only.
        eff.ongoing = (10, DamageType.FIRE)

    def dominate(eff: Effect) -> None:
        c.worsen(eff, Condition.DOMINATED)
        eff.escalate = burn

    c.condition(Condition.WEAKENED, until=When.SAVE_ENDS, on=victim,
                escalate=dominate)


@power("x4_6", cls="poison", level=10, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=13))
def x4_6(c: Cast) -> None:
    """*"+13 vs. Fortitude; ongoing 5 poison damage (save ends)."* The
    whole card: no condition, no escalation, no aftereffect."""
    if c.strike() and c.target is not None:
        c.ongoing(5, DamageType.POISON, on=c.target, until=When.SAVE_ENDS)


@power("x4_7", cls="poison", level=10, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=13))
def x4_7(c: Cast) -> None:
    """*"+13 vs. Fortitude; the target takes a -2 penalty to attack rolls
    (save ends). First Failed Saving Throw: The target is also weakened
    (save ends). Second Failed Saving Throw: The target falls unconscious
    until the end of the encounter."*

    The first clause is a **penalty**, not a condition, so the hold it
    hangs on is `c.penalty(..., until=When.SAVE_ENDS)` and the escalation
    worsens that hold -- which is what keeps *"also weakened"* on one
    saving throw.

    The last step leaves the chain: unconsciousness runs *until the end of
    the encounter* rather than save-ends, so it is a fresh hold on a
    different clock and the poison's own hold is ended rather than
    escalated again.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def collapse(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.UNCONSCIOUS, until=When.ENCOUNTER,
                    on=eff.owner)

    def weaken(eff: Effect) -> None:
        c.worsen(eff, Condition.WEAKENED)
        eff.escalate = collapse

    # **`escalate` is set on the returned hold, not passed in.**
    # `c.penalty` forwards `**kw` to `c.bonus` and neither declares the
    # parameter -- only `c.condition` does -- so passing it here would be
    # swallowed as a bonus keyword and the chain would silently never
    # fire. `lint.py` cannot see that: it reads the row's shape and does
    # not call the body. Measured on a board instead.
    held = c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)
    if held is not None:
        held.escalate = weaken


@power("x4_15", cls="poison", level=10, usage=AT_WILL,
       action=ActionType.NONE, reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=13))
def x4_15(c: Cast) -> None:
    """*"+13 vs. Fortitude; ongoing 5 **acid** damage (save ends). First
    Failed Saving Throw: The target is blinded (save ends)."*

    Acid, not poison, which is the one number-and-type pair in this file
    that does not follow its neighbours. The blindness is *not* prefixed
    "also" on the page, and it adds rather than replaces -- there is no
    condition standing to replace -- so `c.worsen` is right either way.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return

    def blind(eff: Effect) -> None:
        c.worsen(eff, Condition.BLINDED)

    c.condition(ongoing=(5, DamageType.ACID), until=When.SAVE_ENDS,
                on=victim, escalate=blind)
