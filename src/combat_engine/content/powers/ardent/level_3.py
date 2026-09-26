"""Ardent, level 3.

All at-will and all augmentable; the base form is written and each docstring
names the augment clauses dropped with it. One printed row is absent: the one
whose whole rider is "cannot use move actions to walk or run", which is neither
`c.rooted` (cannot shift) nor `c.immobilized` (cannot move at all).
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    FORT,
    MELEE,
    ONE_CREATURE,
    RANGED,
    REACTION,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Budget,
    Cast,
    Keyword,
    Melee,
    Powers,
    Trigger,
    TurnStart,
    When,
    Window,
    both,
    by_melee,
    power,
    targets_me,
)

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    return [a for a in c.within(radius, of=of, side="ally") if a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10281",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10281(c: Cast) -> None:
    """Dropped augments: Augment 1 clears marks off adjacent allies and shifts
    them; Augment 2 makes it a burst."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    marker = _pick(c, [c.me, *_friends(c, 1, of=victim)], "who marks it")
    if marker is not None:
        c.mark(until=When.EONT, by=marker)


@power(
    "p10282",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10282(c: Cast) -> None:
    """The secondary attack is a different defence from the header's, so it is
    rolled with `c.attack` off an `Attack` line built here. It fires in the
    `BEFORE` window, which is what "as an immediate interrupt" means, and the
    penalty is spent on the roll it interrupts. Dropped augments: Augment 1
    narrows it to attacks on Will and adds a Wisdom bonus; Augment 2 is 2[W]
    and widens it to any ally you can see."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    secondary = Attack(CHA, vs=WILL)

    def riposte(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        if ev.target != c.me and not c.adjacent(to=ev.target):
            return
        bonus = secondary.bonus_for(c.world, c.me, c.ref, c.branch)
        if c.attack(bonus, WILL, on=victim).hit:
            c.penalty("attack", c.wis_mod, on=victim, until=When.EOT, once=True)

    c.watch(
        AttackDeclared, riposte, window=Window.BEFORE, until=When.EOTNT, once=True
    )


@power(
    "p11069",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p11069(c: Cast) -> None:
    """Dropped augments: Augment 1 stands adjacent allies up; Augment 2 is 2[W]
    and a standing Constitution-sized damage bonus while adjacent to you."""
    victim = c.target
    if c.first:
        c.shift(1)
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    ally = _pick(c, _friends(c, 1, of=victim), "who presses the attack")
    if ally is not None:
        c.bonus(
            "damage", 2, on=ally, until=When.SONT,
            when=lambda ctx: ctx.get("target") == victim, kind="power")


@power(
    "p11070",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CHA, vs=FORT),
)
def p11070(c: Cast) -> None:
    """Dropped augments: Augment 1 pushes 2 further if the target is dazed;
    Augment 2 is 2[W], pushes one further, and grants combat advantage."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.push(c.con_mod)


@power(
    "p12944",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12944(c: Cast) -> None:
    """Dropped augments: Augment 1 grants combat advantage instead; Augment 2 is
    2[W] and gives distant allies concealment."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    pool = set(_friends(c, 1)) | set(_friends(c, 1, of=victim))
    ally = _pick(c, list(pool), "who shifts")
    if ally is not None:
        c.shift(1, who=ally)


@power(
    "p12946",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
    trigger="an enemy targets you with a melee attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_melee),
        "an enemy targets you with a melee attack",
    ),
)
def p12946(c: Cast) -> None:
    """"Slide the target 1 square to a square adjacent to you" is a pull. The
    printed cost -- losing your standard action next turn -- is the budget
    itself: `Encounter.begin_turn` refreshes it and then announces the turn, so
    a `TurnStart` listener is after the refresh. Dropped augments: Augment 1
    shifts an ally to the new flank; Augment 2 slides further, slides everyone
    now adjacent, and waives the cost."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.pull(1)

    def tax(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.standard = 0

    c.watch(TurnStart, tax, until=When.SONT, once=True)


@power(
    "p12947",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12947(c: Cast) -> None:
    """"Any attack that is not a basic attack" is read off what the creature's
    basic actually *is*, since a monster points `Powers.basic` at one of its own
    rows. Dropped augments: Augment 1 slides it instead; Augment 2 is 2[W] and
    halves the damage of anything but a basic."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)

    def not_basic(ctx: dict) -> bool:
        known = c.world.get(victim, Powers)
        basics = {MELEE, RANGED}
        if known is not None:
            basics |= {known.basic, known.opportunity}
        return ctx.get("power") not in basics

    c.penalty("attack", 2, until=When.EONT, when=not_basic)
