"""Fighter, level 1: the rows the later books added, second half.

See `level_1_b.py` for the four conventions this batch follows.

One more shows up here. **A printed Target line that narrows *which* creature
may be chosen** -- "one creature you're flanking", "one creature marked by
you" -- has no header field: `Target` carries a side and a count and a label
that is prose. Those rows take one enemy the ordinary way and the narrowing
is in the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Condition,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    UpTo,
    When,
    power,
)
from combat_engine.engine.events import AttackDeclared

from .grips import heavy_rider, two_handed, two_melee

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p2099",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2099(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)


@power(
    "p2104",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p2104(c: Cast) -> None:
    """The errata'd text, which drops the level 21 line from both halves."""
    if c.strike():
        c.damage(c.w(1))
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, "who the off-hand catches") if others else None
    if second is not None and c.attack(c.str_, AC, on=second):
        c.damage(c.w(1, hand="off"), on=second)


@power(
    "p2105",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2105(c: Cast) -> None:
    """The slide is into the square the fighter just left, so the square is
    read before the step and named to `c.slide` afterwards."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    vacated = c.here
    if c.shift(1) and vacated is not None:
        c.slide(1, to=vacated)


@power(
    "p2620",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=2),
)
def p2620(c: Cast) -> None:
    """The Effect line is the price: the opening is handed to the target
    whether the swing landed or not."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod + heavy_rider(c))
    if victim is not None:
        c.grants_advantage(on=c.me, to=victim, until=When.SONT)


@power(
    "p7400",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p7400(c: Cast) -> None:
    if c.strike():
        c.damage(0, c.str_mod)
        c.prone()


@power(
    "p9993",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=-2),
    requires=two_handed,
    requires_text="needs a two-handed weapon",
)
def p9993(c: Cast) -> None:
    """"One creature marked by you" is a narrowing of the Target line that
    the header cannot hold; see the report."""
    if c.strike():
        extra = 2 * c.con_mod if c.level >= 21 else c.con_mod
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod + extra)


# -- encounter --------------------------------------------------------------


@power(
    "p2102",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p2102(c: Cast) -> None:
    """No weapon dice at all: the daze is the whole of the hit, and the
    heavy groups add a flat modifier on top."""
    if not c.strike():
        return
    c.dazed(until=When.EONT)
    c.damage(0, heavy_rider(c))


@power(
    "p2107",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p2107(c: Cast) -> None:
    """One attack per target, and the second target takes the off-hand's
    dice -- which `c.first` is what tells them apart."""
    if c.strike():
        c.damage(c.w(1, hand="main" if c.first else "off"), c.str_mod)
        c.slide(1)


@power(
    "p2108",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2108(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + (c.dex_mod if c.wielding("two-weapon") else 0))
        c.grants_advantage(until=When.EONT)


@power(
    "p4312",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4312(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + (c.wis_mod if c.bloodied() else 0))


@power(
    "p4313",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=-1),
)
def p4313(c: Cast) -> None:
    """"Melee weapon +1 reach" is a reach of 2 for everything the fighter
    can hold -- every one of its weapon groups is reach 1."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p9991",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a two-handed weapon and a charge",
    charges=True,
)
def p9991(c: Cast) -> None:
    """A row whose printed Requirement *is* the charge.

    `c.charge_at` reaches its swing through `use`, which refuses to re-enter
    a row already in flight, so the flag goes up by hand and `c.run_at`
    walks. The riposte is armed only for the run: the opportunity attacks it
    punishes are the ones the charge provoked, so the watcher comes down
    before the swing.
    """
    victim = c.target
    if victim is None:
        return
    me = c.me

    def answer(ev: AttackDeclared) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            c.flat(c.con_mod, on=ev.attacker)

    guard = c.watch(AttackDeclared, answer, until=When.EOT, on=me, label=f"{c.ref} spines")
    c.charge = True
    try:
        c.run_at(victim)
        c.world.effects.end(guard, "the run is over")
        if c.strike(on=victim):
            c.damage(c.w(1), c.str_mod + c.con_mod, on=victim)
    finally:
        c.charge = False


# -- daily ------------------------------------------------------------------


@power(
    "p2119",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2119(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    me = c.me
    steps = max(0, c.dex_mod)

    def keep_up(ev: MoveEnd) -> None:
        if ev.actor == victim and steps and c.may("keep pace", who=me):
            c.shift(steps)

    c.watch(MoveEnd, keep_up, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p2124",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2124(c: Cast) -> None:
    """Already slowed, and it is pinned instead -- asked before the damage,
    because nothing here changes the answer and reading it after is a
    needless order dependency."""
    if not c.strike():
        c.half_damage(c.w(2), c.str_mod)
        return
    stuck = c.is_(Condition.SLOWED)
    c.damage(c.w(2), c.str_mod + heavy_rider(c))
    if stuck:
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p4314",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4314(c: Cast) -> None:
    """"One creature you're flanking" is a narrowing of the Target line the
    header cannot hold; see the report. The damage rider counts allies
    beside the target, which is a different question and is asked here."""
    victim = c.target
    if victim is None:
        return
    beside = len([a for a in c.within(1, of=victim, side="ally") if a != c.me])
    if c.strike():
        c.damage(c.w(3), c.str_mod + beside * c.dex_mod)
    else:
        c.half_damage(c.w(3), c.str_mod + beside * c.dex_mod)


@power(
    "p4315",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p4315(c: Cast) -> None:
    """"No mark can supersede this one" has no expression -- `MARKED_BY`
    allows a creature one marker and the newest wins -- and the clause about
    being knocked unconscious is a second ending on a duration that already
    runs to the end of the fight. Both are in the report.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.mark(until=When.ENCOUNTER)


@power(
    "p4316",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4316(c: Cast) -> None:
    """Three swings with a step between them. The second and third are an
    Effect line, so they happen whether the first landed or not, and each
    step is aimed at whoever the next swing is for."""
    struck = {c.target}
    result = c.strike()
    if result:
        c.damage(c.w(1), c.str_mod + (c.dex_mod if result.advantage else 0))
    for prompt in ("who the second swing catches", "who the third swing catches"):
        c.shift(1)
        pool = sorted(e for e in c.within(1, side="enemy") if e not in struck)
        nxt = c.choose(pool, prompt) if pool else None
        if nxt is None:
            return
        struck.add(nxt)
        again = c.attack(c.str_, AC, on=nxt)
        if again:
            c.damage(c.w(1), c.str_mod + (c.dex_mod if again.advantage else 0), on=nxt)


@power(
    "p9364",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p9364(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(1), c.str_mod)
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, "who the off-hand catches") if others else None
    if second is None:
        return
    if c.attack(c.str_, AC, on=second):
        c.damage(c.w(1, hand="off"), c.str_mod, on=second)
        c.ongoing(5, on=second)
    else:
        c.half_damage(c.w(1, hand="off"), c.str_mod, on=second)


@power(
    "p9992",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=-2),
    requires=two_handed,
    requires_text="needs a two-handed weapon",
)
def p9992(c: Cast) -> None:
    """The slide and the step come *before* the roll, which is what makes
    the -2 worth taking: the fighter ends up where the swing is best."""
    victim = c.target
    if victim is None:
        return
    pos = c.world.get(victim, Position)
    theirs = pos.square if pos is not None else None
    if c.slide(1) and theirs is not None:
        c.shift(1, to=theirs)
    if c.strike():
        c.damage(c.w(3), c.str_mod + c.con_mod)
    else:
        c.half_damage(c.w(3), c.str_mod + c.con_mod)
