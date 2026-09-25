"""Ranger, level 7: the encounter attacks.

Two of the four are the two-attack shape the level 1 file sets out, and both
print *different* dice for the two swings -- 2[W] then 1[W] -- so the hand
and the multiplier travel together rather than the loop rolling the same
line twice. One target takes both; two targets take one each, the first the
heavier.

`p920` prints "Ranged weapon" as its whole range line, which is a bow in
hand, so it is declared with a requirement of one: a two-blade ranger owns
none and would otherwise be offered the row and roll a short sword at twenty
squares.

The later books add the thrown rows, which are the opposite case: they reach
at range off the weapon already in the hand, so they carry
`thrown_by_hand=True` and the ranged gate asks for a melee weapon instead of
a bow. No weapon carries a thrown flag, so that field is the whole of what
the printed Requirement can be.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Trigger,
    UpTo,
    When,
    World,
    both,
    by_me,
    by_opportunity,
    power,
)
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.query import defence as defence_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_I_SWING_AN_OPENING = "you make an opportunity attack against an enemy"


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _two_swings(c: Cast, *, hands: bool) -> None:
    """2[W] then 1[W], spread over one or two creatures.

    `hands` is whether the second blow comes from the off-hand -- true for
    the pair of blades, false for two shots from the same bow.
    """
    heavy = (2, "main")
    light = (1, "off" if hands else "main")
    alone = c.first and c.last
    swings = [heavy, light] if alone else [heavy] if c.first else [light]
    for dice, hand in swings:
        if c.strike():
            c.damage(c.w(dice, hand=hand), c.attack_mod)


@power(
    "p1418",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p1418(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.push(max(0, c.wis_mod))
        c.prone()


@power(
    "p1419",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p1419(c: Cast) -> None:
    """"Ignore any penalties from cover or concealment (but not superior
    cover or total concealment)" -- the engine's cover penalty is the whole
    of what `ignore_cover` drops, and superior cover is not modelled apart
    from it, so the parenthesis has nothing left to exclude.
    """
    if c.strike(plus=c.wis_mod, ignore_cover=True):
        c.damage(c.w(2), c.attack_mod)


@power(
    "p848",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p848(c: Cast) -> None:
    _two_swings(c, hands=True)


@power(
    "p920",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p920(c: Cast) -> None:
    """No `requires_text`, deliberately: `chargen.build_for` picks the build
    that can hold a row by looking for the word "requirement" in the refusal,
    and a custom message hides it -- so spelling this one out handed the row
    to the two-blade ranger, who owns no bow."""
    _two_swings(c, hands=False)


@power(
    "p10625",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p10625(c: Cast) -> None:
    """Off-hand opens against Reflex, main weapon follows against AC.

    "You ignore any attack roll penalties to the secondary attack" has
    nothing to undo: a penalty is a held modifier read inside `resolve`, and
    a body cannot tell it to look the other way for one roll.
    """
    if not c.strike():
        return
    c.damage(c.w(1, hand="off"))
    if c.attack(c.str_, AC):
        c.damage(c.w(2, hand="main"), c.str_mod)


@power(
    "p10626",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
)
def p10626(c: Cast) -> None:
    """Both beast clauses are dropped: the printed Target is a creature
    standing next to the companion, and the second half of the Hit line is
    the companion's own attack. Neither has anything to read."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p10627",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p10627(c: Cast) -> None:
    """Whether the target was bloodied is asked before the damage lands, or
    a healthy creature that this blow bloodies would collect the rider."""
    soft = c.bloodied() or c.is_(Condition.PRONE)
    if c.strike():
        c.damage(c.w(4 if soft else 2), c.dex_mod)


@power(
    "p10628",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
)
def p10628(c: Cast) -> None:
    """"An ally of yours who can take free actions" is read as an ally still
    standing next to the target: whether a creature may take a free action
    is not a question the model holds, and being able to act at all is the
    nearest thing it does."""
    victim = c.target
    beside = victim is not None and any(
        c.adjacent_to(victim, friend) for friend in c.allies()
    )
    if c.strike(advantage=True if beside else None):
        c.damage(c.w(3), c.str_mod)


@power(
    "p10629",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10629(c: Cast) -> None:
    """The walk is aimed at the swing that follows it. `c.move` hands the
    destination to the decider, which is as happy to walk out of reach as
    into it; `c.run_at` closes on the named creature the way a charge's move
    does, and the row is not a charge, so no flag is raised."""
    victim = c.target
    if victim is not None and not c.adjacent():
        c.run_at(victim)
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.prone()


@power(
    "p10703",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10703(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod)
    c.immobilized()
    victim = c.target
    beside = [f for f in c.enemies() if f != victim and c.adjacent_to(victim, f)]
    second = c.choose(beside, f"{c.ref}: who else is pinned") if beside else None
    if second is not None:
        c.immobilized(on=second)


@power(
    "p11574",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
    trigger=_I_SWING_AN_OPENING,
    on=Trigger(
        AttackDeclared, when=both(by_me, by_opportunity), text=_I_SWING_AN_OPENING
    ),
)
def p11574(c: Cast) -> None:
    """The dispatcher aims a triggered row at whoever the event was about,
    and here that is the ranger itself, so it declines to choose and the
    usual target selection runs -- which with two enemies in reach may pick
    the wrong one. Left as written; the fix belongs in `Triggers._at`.

    The concealment half of the Hit line is dropped: concealment is not a
    state a creature can be put into, only a consequence of cover.
    """
    if not c.strike():
        return
    c.damage(c.w(2, hand="off"), c.str_mod)
    c.grants_advantage(until=When.EONT)


@power(
    "p4402",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=REF),
)
def p4402(c: Cast) -> None:
    """The widened critical range is a modifier read at the moment of the
    roll, so it has to be in place before the first shot and gated on this
    row -- otherwise every other attack this turn crits on an 18 too."""
    if c.first:
        c.bonus(
            "crit_range",
            2,
            on=c.me,
            until=When.EOT,
            when=lambda ctx: ctx.get("power") == c.ref,
        )
    shots = 2 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike():
            c.damage(c.w(1), c.dex_mod)


@power(
    "p4403",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4403(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    if c.is_quarry():
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p4404",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p4404(c: Cast) -> None:
    """"Two attack rolls, use the higher" is written as a second roll after a
    miss. Only whether it lands is ever read, and rolling again only when the
    first fell short reaches the same answer with one die fewer."""
    if not (c.strike() or c.strike()):
        return
    c.damage(c.w(1), c.str_mod)
    friends = c.allies()
    friend = c.choose(friends, f"{c.ref}: who it is opened up for") if friends else None
    c.grants_advantage(to=friend if friend is not None else "me", until=When.SONT)
    c.shift(c.wis_mod)


@power(
    "p4405",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p4405(c: Cast) -> None:
    """One penalty, sized by how many landed. Two of the same kind do not
    add -- the larger wins -- so applying a second -2 for the second hit
    would come to -2 and look exactly like a working rider."""
    landed = sum(1 for _ in range(2) if c.strike())
    if landed:
        me = c.me
        c.penalty(
            "attack",
            4 if landed == 2 else 2,
            until=When.SONT,
            when=lambda ctx: ctx.get("target") == me,
        )


@power(
    "p529",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p529(c: Cast) -> None:
    """"Hits if the roll hits AC **or** Reflex" is one roll against whichever
    of the two is lower, which is the same outcome and one die. Rolling twice
    would give the quarry two chances to be critically hit."""
    victim = c.target
    if victim is not None and c.is_quarry():
        soft = min((AC, REF), key=lambda d: defence_of(c.world, victim, d))
        landed = c.attack(c.dex_, soft)
    else:
        landed = c.strike()
    if landed:
        c.damage(c.w(2), c.dex_mod)


@power(
    "p9355",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p9355(c: Cast) -> None:
    """"Takes N extra damage whenever it is hit" is a vulnerability, and one
    of them, sized by how many of the two swings landed."""
    landed = 0
    for swing in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
    if landed:
        c.vulnerable(1 + c.wis_mod if landed == 2 else 2, until=When.EONT)
