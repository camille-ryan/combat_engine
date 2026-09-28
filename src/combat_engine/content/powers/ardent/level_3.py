"""Ardent, level 3.

All at-will and all augmentable; each row buys its augment with `augment` and
names in its docstring whatever is left out. One printed row is absent: the one
whose whole rider is "cannot use move actions to walk or run", which is neither
`c.rooted` (cannot shift) nor `c.immobilized` (cannot move at all).
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    EACH_ENEMY,
    FORT,
    MELEE,
    ONE_CREATURE,
    RANGED,
    REACTION,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Augment,
    Budget,
    Cast,
    CloseBurst,
    Condition,
    Keyword,
    Melee,
    Position,
    Powers,
    Square,
    Trigger,
    TurnStart,
    When,
    Window,
    both,
    by_melee,
    power,
    spread,
    targets_me,
)

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    return [a for a in c.within(radius, of=of, side="ally") if a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


def _beside(c: Cast, anchor: int, mover: int) -> Square | None:
    """An unoccupied square next to `anchor` that `mover` can shift into.

    The printed line names a destination rather than a distance -- "shift to
    a square adjacent to the target" -- so what limits it is where the mover
    can get, not one square."""
    pos = c.world.get(anchor, Position)
    if pos is None:
        return None
    near = spread({pos.square}, 1)
    reach = [sq for sq in c.world.reachable_squares(mover, c.speed_of(mover))
             if sq in near]
    return sorted(reach)[0] if reach else None


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
    augments=(
        Augment(1),
        Augment(2, reach=CloseBurst(1), target=EACH_ENEMY),
    ),
)
def p10281(c: Cast) -> None:
    """Augment 1 is an Effect, so it happens whether or not the swing lands:
    the marks come off your neighbours and each of them slips a square.

    Augment 2 rewrites the header -- a close burst against each enemy where
    the base is one swing -- so it is declared rather than said in the body,
    and everything under it is the same hit line against more creatures.
    The Effect of Augment 1 is not printed under Augment 2, so it is gated
    on the cheaper form exactly rather than on "augmented at all"."""
    spent = augment(c, 1, 2)
    victim = c.target
    if spent == 1 and c.first:
        for ally in _friends(c, 1):
            c.cure(Condition.MARKED, on=ally)
            c.shift(1, who=ally)
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
    penalty is spent on the roll it interrupts. Augment 1 narrows the window
    to attacks on Will -- `AttackDeclared` carries the defence -- and adds
    Wisdom to the riposte. Augment 2 is 2[W] and widens the window from an
    adjacent ally to any ally you can see."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    secondary = Attack(CHA, vs=WILL)

    def riposte(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        near = c.can_see(ev.target) if spent == 2 else c.adjacent(to=ev.target)
        if ev.target != c.me and not near:
            return
        if spent == 1 and ev.vs is not WILL:
            return
        bonus = secondary.bonus_for(c.world, c.me, c.ref, c.branch)
        if spent:
            bonus += c.wis_mod
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
    """Augment 1 stands your neighbours up, which is curing the condition
    rather than any kind of move. Augment 2 is 2[W] and replaces the one
    ally's bonus with a standing one for everybody beside you -- gated on a
    position read when the damage is dealt, since the damage context carries
    no attacker to ask about."""
    spent = augment(c)
    victim = c.target
    if c.first:
        c.shift(1)
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    if spent == 1:
        for ally in _friends(c, 1):
            c.cure(Condition.PRONE, on=ally)
    if spent == 2:
        for ally in _friends(c, 5):
            c.bonus(
                "damage", c.con_mod, on=ally, until=When.EONT, kind="power",
                when=lambda ctx, a=ally: c.adjacent_to(c.me, a))
        return
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
    """Augment 1 pushes further, and *only* if the target is dazed: its Hit
    line is printed in full and the plain push is not in it, so a target that
    is not dazed is not moved at all. Augment 2 is 2[W], one square further,
    and the target ends the push open to whoever is standing beside it."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    if spent == 1:
        if c.is_(Condition.DAZED):
            c.push(2 + c.con_mod)
        return
    c.push(1 + c.con_mod if spent == 2 else c.con_mod)
    if spent == 2 and victim is not None:
        for ally in _friends(c, 1, of=victim):
            c.grants_advantage(on=victim, to=ally, until=When.EONT)


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
    """Augment 1 hands one ally within 5 combat advantage instead of the
    shift. Augment 2 is 2[W] and conceals every ally that is not standing
    next to the target -- a gate on the attacker and on a distance read when
    the attack is made, so an ally who closes loses it."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    if spent == 1:
        ally = _pick(c, _friends(c, 5), "who gains the opening")
        if ally is not None:
            c.grants_advantage(on=victim, to=ally, until=When.EONT)
        return
    if spent == 2:
        for ally in _friends(c, 10):
            c.conceal(
                on=ally, until=When.EONT,
                when=lambda ctx, a=ally: (
                    ctx.get("attacker") == victim and not c.adjacent_to(victim, a)
                ),
            )
        return
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
    a `TurnStart` listener is after the refresh. Augment 1 shifts an ally onto
    the new flank. Augment 2 drags the target Wisdom squares, shoves everybody
    who ends up beside it, and waives the cost -- so the tax is only armed for
    the other two forms."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.pull(c.wis_mod if spent == 2 else 1)
        if victim is not None and spent == 1:
            ally = _pick(c, _friends(c, 1), "who takes the flank")
            spot = _beside(c, victim, ally) if ally is not None else None
            if ally is not None and spot is not None:
                c.shift(c.speed_of(ally), who=ally, to=spot)
        if victim is not None and spent == 2:
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.slide(1, on=foe)
    if spent == 2:
        return

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
    rows. Augment 1 answers the non-basic attack with a slide instead of
    penalising it.

    Augment 2 is left out: "deals half damage with any attack that is not a
    basic attack" is `Condition.WEAKENED`, which `query.deals_half` reads off
    the creature and not off the attack, so there is nothing to gate and the
    augmented form would halve its basic attacks too."""
    spent = augment(c, 1)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)

    def not_basic(ctx: dict) -> bool:
        known = c.world.get(victim, Powers)
        basics = {MELEE, RANGED}
        if known is not None:
            basics |= {known.basic, *known.instead_of_basic("opportunity")}
        return ctx.get("power") not in basics

    if not spent:
        c.penalty("attack", 2, until=When.EONT, when=not_basic)
        return

    def shove(ev: AttackDeclared) -> None:
        if ev.attacker == victim and not_basic({"power": ev.power}):
            c.slide(c.con_mod, on=victim)

    c.watch(AttackDeclared, shove, window=Window.BEFORE, until=When.SONT, once=True)
