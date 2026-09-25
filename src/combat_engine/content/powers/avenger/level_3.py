"""Avenger, level 3: the eleven encounter attacks that print a Prerequisite.

They are one row written eleven ways: Wisdom against Reflex at range 5 for
2d10 and a modifier, and then an Effect line that does something for one
ally. The Prerequisite names a class feature the engine does not model, so
each is written as the ordinary power it otherwise is, ungated.

Two judgements recur.

* **"One ally you can see"** is a choice among the allies there is line of
  effect to, and the Effect line is unconditional -- it pays out whether
  the attack landed or not, which is what the printed order says.
* **"Deals extra force damage equal to ... on his or her next melee
  attack"** is a watcher rather than `c.bonus("damage", ...)`. A damage
  bonus is a number folded into the packet being rolled and therefore
  untyped; these four lines each name a type, and a creature resistant to
  it should shrug it off. The die is spent on the ally's next melee attack
  **that hits**, because extra damage on a miss has nothing to attach to.

The remaining ten rows of this level are in `level_3_b.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Miss,
    Ranged,
    Square,
    When,
    by_melee,
    distance,
    power,
    spread,
)
from combat_engine.engine.query import alive, squares

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT]


def _an_ally(c: Cast, prompt: str) -> int | None:
    """"One ally you can see"."""
    pool = sorted(a for a in c.allies() if alive(c.world, a) and c.can_see(a))
    return c.choose(pool, prompt) if pool else None


def beside(c: Cast, thing: int, mover: int) -> Square | None:
    """An empty square next to `thing`, the nearest one to `mover`."""
    here = squares(c.world, thing)
    open_ = [
        sq
        for sq in spread(here, 1) - here
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    if not open_:
        return None
    from_ = squares(c.world, mover)
    if not from_:
        return None
    return min(open_, key=lambda sq: (min(distance(sq, s) for s in from_), sq))


def _next_swing(c: Cast, friend: int | None, victim: int | None, dtype: DamageType) -> None:
    """Extra damage of one type on that ally's next melee attack at the target."""
    amount = max(c.dex_mod, c.int_mod)
    if friend is None or victim is None or amount <= 0:
        return
    spent: list[bool] = []

    def paid(ev: Hit) -> None:
        if spent or ev.attacker != friend or ev.target != victim:
            return
        if not by_melee(c.world, friend, ev):
            return
        spent.append(True)
        c.flat(amount, dtype=dtype, on=victim)

    c.watch(Hit, paid, until=When.EONT, on=c.me, label=f"{c.ref} gift")


def _bolt(c: Cast, dtype: DamageType = DamageType.RADIANT) -> None:
    """The half every one of these eleven rows shares."""
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=dtype)


@power(
    "p11635",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11635(c: Cast) -> None:
    _bolt(c)
    for friend in c.within(1, side="ally"):
        if friend != c.me and c.may("shift 1 square", who=friend):
            c.shift(1, who=friend)


@power(
    "p11639",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11639(c: Cast) -> None:
    _bolt(c)
    friend = _an_ally(c, "who is shielded")
    if friend is None:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=friend, until=When.SONT, kind="power")


@power(
    "p11642",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(WIS, vs=REF),
)
def p11642(c: Cast) -> None:
    victim = c.target
    _bolt(c, c.choose([DamageType.RADIANT, DamageType.FORCE], "which damage"))
    _next_swing(c, _an_ally(c, "who is lent the blow"), victim, DamageType.FORCE)


@power(
    "p11645",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11645(c: Cast) -> None:
    _bolt(c)
    friend = _an_ally(c, "whose aim is steadied")
    if friend is not None:
        c.bonus("attack", 1, on=friend, until=When.SONT, kind="power")


@power(
    "p11648",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=REF),
)
def p11648(c: Cast) -> None:
    victim = c.target
    _bolt(c, c.choose([DamageType.PSYCHIC, DamageType.RADIANT], "which damage"))
    _next_swing(c, _an_ally(c, "who is lent the blow"), victim, DamageType.PSYCHIC)


@power(
    "p11651",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11651(c: Cast) -> None:
    _bolt(c)
    friend = _an_ally(c, "whose arm is strengthened")
    if friend is not None:
        c.bonus("damage", 2, on=friend, until=When.SONT, kind="power")


@power(
    "p11655",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11655(c: Cast) -> None:
    """The slide names its destination: "to a square adjacent to the target"
    is an instruction, not a direction to be chosen."""
    victim = c.target
    _bolt(c)
    friend = _an_ally(c, "who is drawn in")
    if friend is None or victim is None:
        return
    landing = beside(c, victim, friend)
    if landing is not None:
        c.slide(5, on=friend, to=landing)


@power(
    "p11656",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11656(c: Cast) -> None:
    _bolt(c)
    friend = _an_ally(c, "who shakes it off")
    if friend is not None:
        c.save(on=friend, bonus=2)


@power(
    "p11662",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11662(c: Cast) -> None:
    victim = c.target
    _bolt(c)
    _next_swing(c, _an_ally(c, "who is lent the blow"), victim, DamageType.RADIANT)


@power(
    "p11665",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(WIS, vs=REF),
)
def p11665(c: Cast) -> None:
    victim = c.target
    _bolt(c, c.choose([DamageType.RADIANT, DamageType.NECROTIC], "which damage"))
    _next_swing(c, _an_ally(c, "who is lent the blow"), victim, DamageType.NECROTIC)


@power(
    "p11668",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ILLUSION],
    attack=Attack(WIS, vs=REF),
)
def p11668(c: Cast) -> None:
    """"Until he or she hits or misses" is a second ending on a duration,
    so the hold is raised with the clock and taken down by hand when the
    ally swings at anything.
    """
    _bolt(c)
    friend = _an_ally(c, "who goes unseen")
    if friend is None:
        return
    veil = c.invisible(on=friend, until=When.SONT)
    if veil is None:
        return

    def swung(ev: Hit | Miss) -> None:
        if ev.attacker == friend:
            c.world.effects.end(veil, "swung")

    for event in (Hit, Miss):
        c.watch(event, swung, until=When.SONT, on=c.me, label=f"{c.ref} veil")
