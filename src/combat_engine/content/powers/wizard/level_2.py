"""Wizard, level 2: the utilities.

No attack rolls at this level. The one printed Trigger line is declared with
`on=` rather than quoted: prose alone is never read, and a row that only
quotes it can never fire.

`p1223` is a skill bonus and nothing else -- the whole of its Effect is a
+10 to one check, and this engine has no checks. It carries
`out_of_combat=True` for the same reason the cantrips in `level_0.py` do,
rather than an invented movement number.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MOVE,
    PERSONAL,
    REF,
    SELF,
    AttackRolled,
    Cast,
    Keyword,
    Ranged,
    Target,
    Trigger,
    When,
    power,
    would_hit_me,
)


@power(
    "p1212",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p1212(c: Cast) -> None:
    c.shift(c.speed_of() * 2)


@power(
    "p1223",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=Target("any", 1, label="You or one creature"),
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p1223(c: Cast) -> None:
    c.note("p1223: a +10 power bonus to one check, with a running start")


@power(
    "p1235",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, when=would_hit_me, text="you are hit by an attack"),
)
def p1235(c: Cast) -> None:
    """Raised in time to turn the blow aside, which is what an interrupt is.

    Offered on the roll rather than on the hit. `would_hit_me` reads the
    provisional result -- the die is down, the total is known, and the blow
    lands as things stand -- and the defence is read again once this window
    closes, so the +4 applies to the very attack that triggered it.
    """
    c.bonus(AC, 4, on=c.me, until=When.EONT)
    c.bonus(REF, 4, on=c.me, until=When.EONT)
