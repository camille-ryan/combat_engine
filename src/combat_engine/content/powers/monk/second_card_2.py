"""Monk, the second stat block printed beside levels 5, 7, 9 and 10.

The level 7 rows are the move half of a Full Discipline: its own action,
bought separately, so the parent no longer takes it for free at the end of
its own body. The level 5, 9 and 10 rows are the attack or the reaction a
stance, a form or a hold lets you make while it stands.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine import query

IMPLEMENT_PSIONIC = [Keyword.IMPLEMENT, Keyword.PSIONIC]
PSIONIC = [Keyword.PSIONIC]


def _fire(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.FIRE in p.keywords


def _end_hold(c: Cast, ref: str) -> None:
    """"Effect: the stance ends" -- the hold the parent left labelled itself."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == ref:
            c.world.effects.end(eff, "the stance ends")


def _wears(world: World, me: int, who: int, ref: str) -> bool:
    """Is `who` carrying a hold this creature laid with `ref`?

    `cards.active` reads the caster's own effects, and these two parents
    leave their hold on the *victim* instead -- a mark, or a named hold
    naming the creature the follow-up is allowed against.
    """
    return any(
        e.source == me and (e.label == ref or e.label.startswith(f"{ref} "))
        for e in world.effects.of(who)
    )


def _laid(ref: str) -> Callable[[World, int], bool]:
    def check(world: World, eid: int) -> bool:
        return any(
            e.source == eid and (e.label == ref or e.label.startswith(f"{ref} "))
            for e in world.effects.live.values()
        )

    return check


def _its_turn(world: World, who: int) -> bool:
    """Whose turn it is. Permissive off the clock: a board with no order
    running would otherwise make "on its turn" false forever."""
    enc = getattr(world, "encounter", None)
    order = getattr(enc, "order", None) if enc is not None else None
    if not order:
        return True
    return order[enc.index % len(order)] == who


def _beside(c: Cast, who: int) -> Square | None:
    pos = c.world.get(who, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq == pos.square:
            continue
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _hit_this_turn(c: Cast) -> list[int]:
    """Everyone this creature has landed a blow on since its turn began.
    Read back off the log, which is the only record of it."""
    out: list[int] = []
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == c.me:
            break
        if isinstance(ev, Hit) and ev.attacker == c.me and ev.target not in out:
            out.append(ev.target)
    return out


# -- level 5 -----------------------------------------------------------------


@power(
    "p13154b",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT_PSIONIC, Keyword.STANCE],
    attack=Attack(DEX, vs=FORT),
    requires=active("p13154"),
    requires_text="the p13154 power must be active",
)
def p13154b(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.dex_mod)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.dex_mod)
        c.dazed(until=When.EONT)
    _end_hold(c, "p13154")


def _adjacent_foe_swings(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "attacker", None)
    return (
        foe is not None
        and foe != me
        and foe in query.enemies(world, me)
        and query.adjacent(world, me, foe)
    )


@power(
    "p16156b",
    level=5,
    cls="monk",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT_PSIONIC,
    attack=Attack(DEX, vs=REF),
    requires=active("p16156"),
    requires_text="the p16156 power must be active",
    trigger="an enemy adjacent to you makes an attack",
    on=Trigger(AttackDeclared, _adjacent_foe_swings, "an adjacent enemy attacks"),
)
def p16156b(c: Cast) -> None:
    """At-will rather than daily: the parent's printed Effect says the stance
    lets you use this one at will, and the frequency line on the second block
    is the parent's own."""
    if c.strike():
        c.damage("1d8", c.dex_mod)
        c.prone()
    elif c.target is not None:
        c.grants_advantage(on=c.me, to=c.target, until=When.SONT)


# -- level 7: the move half of a Full Discipline -----------------------------


@power(
    "p11224b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p11224b(c: Cast) -> None:
    """Two one-square shifts rather than one of two, because the printed
    clause is about the squares you leave *during* the shift and a shift
    resolved as a single displacement leaves only the one you started in."""
    victims = _hit_this_turn(c)
    for _ in range(2):
        vacated = c.here
        if not c.shift(1):
            break
        if c.world.grid.occupant(vacated) is not None:
            continue
        near = [
            f
            for f in victims
            if (pos := c.world.get(f, Position)) is not None
            and distance(pos.square, vacated) <= 1
        ]
        if not near:
            continue
        foe = c.choose(near, "slide into the square you left", optional=True)
        if foe is not None:
            c.slide(1, on=foe, to=vacated)


@power(
    "p11226b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p11226b(c: Cast) -> None:
    """A running start is the whole of the difference between dividing the
    Athletics result by ten and halving it again, so the +5 and the running
    start both land as distance rather than as prose."""
    covered = int(c.check("athletics", bonus=5)) // 10
    if covered > 0:
        c.jump(covered)
    c.zone(spread({c.here}, 1), difficult=True, until=When.EONT)


@power(
    "p13163b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PSIONIC, Keyword.LIGHTNING, Keyword.TELEPORTATION],
)
def p13163b(c: Cast) -> None:
    c.teleport(c.speed_of())


@power(
    "p13165b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13165b(c: Cast) -> None:
    """"During this movement" -- the rough going is ignored for the length of
    the move and no longer."""
    rough = c.ignores_difficult(until=When.EOT)
    try:
        c.move(c.speed_of() + 2)
    finally:
        if rough is not None:
            c.world.effects.end(rough, "the move ended")


@power(
    "p13167b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13167b(c: Cast) -> None:
    c.shift(1)
    c.zone(spread({c.here}, 1), difficult=True, until=When.SONT)


@power(
    "p13169b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13169b(c: Cast) -> None:
    mates = [a for a in c.within(1, side="ally") if a != c.me]
    if not mates:
        return
    partner = c.choose(mates, "swap places with")
    if partner is not None:
        c.swap(partner)


@power(
    "p13225b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13225b(c: Cast) -> None:
    walk = "move 3 squares"
    if c.choose(["shift 1 square", walk], "how to go") == walk:
        c.move(3)
    else:
        c.shift(1)


@power(
    "p15987b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p15987b(c: Cast) -> None:
    """A grab and a mark are held as relations, not as conditions, so
    shedding one is ending the effect that carries the relation -- looking
    for `Condition.GRABBED` in an effect's conditions finds nothing, ever."""
    mine = list(c.world.effects.of(c.me))
    grabs = [
        e for e in mine
        if any(rel is Relation.GRABBED_BY and who == c.me for rel, _, who in e.relations)
    ]
    marks = [
        e for e in mine
        if any(rel is Relation.MARKED_BY and who == c.me for rel, _, who in e.relations)
    ]
    options = [*(["escape the grab"] if grabs else []), *(["shed a mark"] if marks else [])]
    picked = c.choose(options, "what to shake off") if options else None
    if picked == "escape the grab":
        c.world.effects.end(grabs[0], c.ref)
    elif picked == "shed a mark":
        c.world.effects.end(marks[0], c.ref)
    c.shift(2)


@power(
    "p16163b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PSIONIC, Keyword.ELEMENTAL, Keyword.THUNDER],
)
def p16163b(c: Cast) -> None:
    """The monk has no fly speed of its own, so the flight is lent for the
    turn -- the creature is put down again by the end of it."""
    c.mode("fly", c.speed_of(), until=When.EOT)
    c.move(c.speed_of(), at="fly")


@power(
    "p16166b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PSIONIC, Keyword.ELEMENTAL, Keyword.FIRE],
)
def p16166b(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))
    c.bonus("damage", 2, on=c.me, until=When.EONT, when=_fire, kind="power")


@power(
    "p16168b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p16168b(c: Cast) -> None:
    """"The creature moves with you" is a square-by-square drag: whatever is
    held is slid into the square the grabber has just left, which is the only
    way it stays adjacent across a move of several squares."""
    for held in c.grabbing():
        c.no_provoke(from_=held, until=When.EOT)
    budget = c.speed_of()
    while budget > 0:
        vacated = c.here
        spent = c.move(1)
        if spent <= 0:
            break
        budget -= spent
        for held in c.grabbing():
            if c.distance(held) > 1 and c.world.grid.occupant(vacated) is None:
                c.slide(1, on=held, to=vacated)


@power(
    "p7465b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p7465b(c: Cast) -> None:
    c.shift(2)


@power(
    "p7466b",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p7466b(c: Cast) -> None:
    """Every prone enemy, not only the adjacent ones: the opening the printed
    line closes is one you would give walking *past* a body."""
    for foe in c.enemies():
        if c.is_(Condition.PRONE, on=foe):
            c.no_provoke(from_=foe, until=When.EOT)
    c.move(c.speed_of() + 2)


# -- level 9 -----------------------------------------------------------------


def _the_quarry_swings(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "attacker", None)
    return foe is not None and _wears(world, me, foe, "p11229")


@power(
    "p11229b",
    level=9,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT_PSIONIC,
    attack=Attack(DEX, vs=REF),
    requires=_laid("p11229"),
    requires_text="the p11229 power must have named a target",
    trigger="the target makes an attack",
    on=Trigger(AttackDeclared, _the_quarry_swings, "the target attacks"),
)
def p11229b(c: Cast) -> None:
    """Encounter rather than daily: the parent's printed Effect grants this
    one use before the end of the encounter, and the frequency line on the
    second block is the parent's own."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
    else:
        c.half_damage("2d10", c.dex_mod)


@power(
    "p13173b",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT_PSIONIC, Keyword.FIRE, Keyword.STANCE],
    attack=Attack(DEX, vs=REF),
    requires=active("p13173"),
    requires_text="the p13173 power must be active",
)
def p13173b(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("1d8", c.dex_mod)
        c.damage("1d12", 0, dtype=DamageType.FIRE)
        if victim is not None:
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.damage(0, 5, dtype=DamageType.FIRE, on=foe)
    else:
        c.half_damage("1d8", c.dex_mod)
        c.half_damage("1d12", 0, dtype=DamageType.FIRE)
    _end_hold(c, "p13173")


@power(
    "p16171b",
    level=9,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT_PSIONIC,
    attack=Attack(DEX, vs=REF),
    requires=active("p16171"),
    requires_text="the p16171 power must be active",
)
def p16171b(c: Cast) -> None:
    """At-will rather than daily: the form's printed Effect says it lets you
    use this one at will."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.prone()


# -- level 10 ----------------------------------------------------------------


def _quarry_moves(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "actor", None)
    if foe is None or getattr(ev, "kind_", "") == "forced":
        return False
    return _wears(world, me, foe, "p16176") and _its_turn(world, foe)


@power(
    "p16176b",
    level=10,
    cls="monk",
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    requires=_laid("p16176"),
    requires_text="the p16176 power must be active",
    trigger="the marked enemy moves willingly on its turn",
    on=Trigger(MoveEnd, _quarry_moves, "the marked enemy moves"),
)
def p16176b(c: Cast) -> None:
    """Forfeiting next turn's move action is written against the budget the
    turn hands out: `Budget.refresh` runs before `TurnStart` is announced, so
    a watch armed here takes the move back off before anything is spent."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    landing = _beside(c, foe)
    if landing is not None and distance(c.here, landing) <= c.speed_of():
        c.shift(c.speed_of(), to=landing)
    held: list[Effect] = []

    def forfeit(ev: TurnStart) -> None:
        if ev.actor != c.me or ev.ghost:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.move = 0
        if held:
            c.world.effects.end(held[0], "the move action is forfeit")

    held.append(c.watch(TurnStart, forfeit, until=When.EONT))
