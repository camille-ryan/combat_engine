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

from typing import Any


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
