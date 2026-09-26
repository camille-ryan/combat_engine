"""Warden, level 1: the swing that is rolled twice.

The spec entry asked for `keep=` on `c.strike` and for both results to be
readable off `AttackResult`. Both are here: `keep` belongs to the roll
rather than to the body, because by the time `c.strike` has returned the
first die has already been announced and answered; and `AttackResult.rolls`
keeps every face, which is what "if both of your attack rolls would hit"
reads. `natural` holds one face and anything that rolls again overwrites it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p9818",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p9818(c: Cast) -> None:
    """"Would hit" is asked of each face with the roll's own modifiers added
    back -- `total` minus `natural` is everything the situation and the
    character brought -- rather than re-rolling or re-reading the defence,
    which may have moved since.

    The penalty is gated on the attack not naming the warden. The attack
    context carries one `target`, so a burst that catches the warden and
    somebody else is still penalised on the other target; `among` is on the
    event and not in the context, which is the nearest this can get.
    """
    result = c.strike(keep="best")
    if not result:
        return
    c.damage(c.w(), c.str_mod)
    adjust = result.total - result.natural
    both = len(result.rolls) > 1 and all(
        face == 20 or (face != 1 and face + adjust >= result.target_defence)
        for face in result.rolls
    )
    size = (
        c.wis_mod + (1 if both else 0)
        if c.build("wildblood")
        else (5 if both else 2)
    )
    if size <= 0:
        return
    me = c.me

    def not_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") != me

    c.penalty("attack", size, until=When.EONT, when=not_me)
