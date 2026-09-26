"""Wizard level 6: the row that reaches into the spellbook mid-fight."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    PERSONAL,
    Cast,
    Keyword,
    Powers,
    Usage,
    When,
    get,
    power,
)


@power(
    "p7377",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def p7377(c: Cast) -> None:
    """Swap an unexpended daily or utility for one of the same level in the
    book, and attack better with it until the end of your next turn.

    Unexpended is `Powers.times(ref) == 0`: a power already spent is not a
    power you are holding, and swapping one away would hand back a use the
    card does not give. The +1 is gated on the ref of the row that came in,
    because it is a bonus to that power and not to attacking generally.
    """
    known = c.world.get(c.me, Powers)
    if known is None:
        return
    for ref in known.known:
        p = get(ref)
        if (
            p is None
            or p.level <= 0
            or p.usage not in (Usage.DAILY, Usage.ENCOUNTER)
            or ref == c.ref
            or known.times(ref)
        ):
            continue
        swap = next(
            (
                held
                for held in c.spellbook()
                if (q := get(held)) is not None
                and q.level == p.level
                and q.usage is p.usage
            ),
            "",
        )
        if not swap or not c.prepare(swap, instead_of=ref):
            continue

        def with_it(ctx: dict[str, Any], ref_: str = swap) -> bool:
            return ctx.get("power") == ref_

        c.bonus("attack", 1, kind="power", on=c.me, until=When.EONT, when=with_it)
        return
