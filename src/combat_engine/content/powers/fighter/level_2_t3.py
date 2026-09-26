"""Fighter, level 2: one more square of reach.

The spec entry said the `reach` modifier is read only by `movement._threat`
and that `dsl.area_of` takes the printed size and nothing else. The second
half is stale -- `area_of` has called `_stretched`, which reads `"reach"`,
since the sentence was written. The gate is what is new, so the extra square
belongs to a melee weapon attack and not to everything.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    get,
    power,
)


def _melee_weapon(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.WEAPON in p.keywords


@power(
    "p10484",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
)
def p10484(c: Cast) -> None:
    """"The **next** melee weapon attack" is written as "until the end of
    your turn" rather than with `once=True`. A one-shot bonus is spent by
    watching the attack roll, and this one is consulted long before that --
    `actions.legal` measures reach to decide what may be aimed at, so the
    bonus has to still be standing when the target is picked. A fighter gets
    one standard action, so on the board the two are the same sentence.

    The gate names only the weapon keyword: `_stretched` is asked for
    `"reach"` on melee lines and nothing else, so the "melee" half is
    already the question being answered.
    """
    c.bonus("reach", 1, on=c.me, until=When.EOT, when=_melee_weapon)
