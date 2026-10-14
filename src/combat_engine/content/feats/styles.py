"""The weapon-style feats' associated-power lists.

Sixty-odd feats across the fighter, the ranger, the rogue and the
warlord print a benefit gated on "a power associated with this feat",
and the set was unknowable right up until the ETL learned to resolve the
printed `Associated Powers:` list into refs. It was never an engine gap
-- the list was arriving as prose, which this project may not read.

Two things about these lists are worth knowing before using one.

**They are shorter than the page.** 213 of the 497 printed members are
paragon or epic rows, level 13 to 27, and this build imports heroic
only. The spec prints `(+3 above heroic)` beside a trimmed list so the
trimming is visible rather than silent, and the resolved subset *is* the
whole set as far as any character here is concerned.

**A feat's list is its own.** Two feats that look like a pair -- the
lesser naming a weapon group and the greater gated on the lesser --
almost never share members, so there is no "the spear list". Each is
written out beside the row that uses it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import DAILY, ENCOUNTER, Cast, Keyword, When
from combat_engine.engine.dsl import get
from combat_engine.engine.events import Hit


def martial_encounter_or_daily(ref: str) -> bool:
    """Is this row a martial encounter or daily power.

    Lives here rather than beside one of its callers because three
    `[Greater Style]` feats print the same sentence about it, one per
    class. Note the narrower `ranger_c._martial_encounter`, which is
    **encounter only** and stays separate: `f2803` says "a martial
    encounter power" where these say "encounter or daily", and widening
    one function to serve both would quietly pay `f2803` on dailies.
    Both readings were taken off the page.
    """
    p = get(ref)
    return (
        p is not None
        and Keyword.MARTIAL in p.keywords
        and p.usage in (ENCOUNTER, DAILY)
    )


def longer_shift_on_a_martial_hit(c: Cast, armed: Callable[[], bool]) -> None:
    """"Whenever you hit an enemy with a martial encounter or daily power
    during your turn, you increase the distance you shift by 1 square
    until the end of your turn."

    One card printed three times -- `fighter_c.f2360`, `ranger_b.f2361`
    and `rogue_b.f2362` -- so it is written once. `armed` is the only
    part that differs by row, and it carries the card's own opening
    gate: "when you are attacking with a melee light blade and you have
    proficiency with that weapon". Passed as a callable because
    `_holding` is rewritten per file on purpose.

    **Not a standing extension.** It is laid by a hit and expires at the
    end of that turn, which is why these rows could not simply name a
    distance: the docstring on `f2360` read as though the clause
    lengthened shifts outright, and the card says otherwise. Read the
    card, not the first line of the note beside it.

    **"During your turn" is `world.turn == me`, and it is load-bearing**
    -- an opportunity attack or an immediate interrupt is a hit of mine
    on somebody else's turn, and the clause does not pay there.

    **Laid at most once a turn.** The entries in `Powers.extra_squares`
    *add*, by design, so two hits in one turn would otherwise read as two
    extra squares where the card grants one. The live effect is held and
    re-checked rather than counted: it expires on its own at the end of
    the turn, so its absence is what says "a new turn" without this
    needing to watch for one.
    """
    me = c.me
    held: list[Any] = []

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or c.world.turn != me:
            return
        if not armed() or not martial_encounter_or_daily(ev.power):
            return
        if held and held[0] in c.world.effects.of(me):
            return
        laid = c.extend_every("shift", 1, until=When.EONT)
        held[:] = [laid] if laid is not None else []

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


def among(*refs: str):  # noqa: ANN201
    """A `when=` that asks whether the power being rolled is one of these.

    The attack and damage contexts both carry `power` as a ref, so this
    is one dictionary read -- the same shape every keyword gate in the
    corpus uses, with a set of refs in place of a keyword.
    """
    allowed = frozenset(refs)

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("power", "") in allowed

    return gate


def used_one_of(*refs: str):  # noqa: ANN201
    """A trigger predicate: I am using one of these rows.

    For the clauses that read "when you attack with a power associated
    with this feat, you can shift 2 squares **before** the attack".
    `PowerUsed` fires before the body, which is what makes "before the
    attack" sayable at all.
    """
    allowed = frozenset(refs)

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in allowed

    return when


def hit_with_one_of(*refs: str):  # noqa: ANN201
    """A trigger predicate: I hit with one of these rows."""
    allowed = frozenset(refs)

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power in allowed

    return when
