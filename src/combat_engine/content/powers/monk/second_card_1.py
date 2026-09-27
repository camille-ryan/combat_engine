"""Monk second cards, levels 1 to 3.

Nearly every one of these is the second stat block printed beside a monk
attack power: its own action -- a move, sometimes a minor -- which the
parent row used to take for free at the end of its own body. The parents no
longer do them.

Full Discipline and Psionic have no engine keyword, so most of these headers
carry none at all.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine.query import team


def _enemy_stepped_up(world: World, me: int, ev: Event) -> bool:
    """An enemy entered a square adjacent to me.

    `AdjacencyGained` is emitted mirrored, so the copy addressed to me names
    the newcomer in `other`; comparing it against `mover` is what keeps my
    own advance from reading as the enemy's.
    """
    mover = getattr(ev, "mover", 0)
    if mover in (0, me) or getattr(ev, "actor", None) != me:
        return False
    if getattr(ev, "other", None) != mover:
        return False
    side = team(world, mover)
    return side is not None and side is not team(world, me)


def _drop(c: Cast, holds: list) -> None:
    """End the effects that were printed as lasting only for a movement."""
    for held in holds:
        if held is not None:
            c.world.effects.end(held, "the movement ended")


def _step_or_run(c: Cast) -> None:
    """"You shift 1 square or move 3 squares" -- a real choice, so it is
    offered as one rather than settled here."""
    if c.may("move 3 squares rather than shift 1", who=c.me):
        c.move(3)
    else:
        c.shift(1)


def _running_jump(c: Cast) -> None:
    """An Athletics jump with a running start: the check in squares, and
    deliberately uncapped by speed, which is the printed difference from an
    ordinary run. The +5 is a bonus to the check, not to anything in combat.
    """
    c.jump(c.check("athletics", bonus=5).total // 10)


@power(
    "p11208b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11208b(c: Cast) -> None:
    """Nothing can refuse a creature an immediate action, so only the
    opportunity half of "can't attack you with opportunity actions or
    immediate actions" is written."""
    holds = [
        c.no_provoke(from_=foe, until=When.EOT)
        for foe in c.enemies()
        if c.bloodied(on=foe)
    ]
    c.move(c.speed_of())
    _drop(c, holds)


@power(
    "p11210b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11210b(c: Cast) -> None:
    """Falling is not modelled, so "if you don't land, you fall" is dropped."""
    c.mode("fly", c.speed_of(), until=When.EOT)
    c.move(c.speed_of())


@power(
    "p13124b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13124b(c: Cast) -> None:
    c.shift(1)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=c.me, until=When.SONT, kind="power")


@power(
    "p13126b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13126b(c: Cast) -> None:
    """"You are no longer marked" has no method of its own, so the marks
    standing on the monk are ended one by one. A mark is a **relation** held
    up by an effect -- `c.mark` sets no condition -- so asking
    `Condition.MARKED in eff.conditions` finds nothing, ever."""
    for eff in list(c.world.effects.of(c.me)):
        if any(kind is Relation.MARKED_BY for kind, _s, _t in eff.relations):
            c.world.effects.end(eff, c.ref)
    c.move(c.speed_of() + 2)


@power(
    "p13128b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13128b(c: Cast) -> None:
    """Falling is not modelled, so "if you don't land, you fall" is dropped."""
    c.mode("fly", c.speed_of(), until=When.EOT)
    c.move(c.speed_of())


@power(
    "p13130b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13130b(c: Cast) -> None:
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.SONT, kind="power",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )
    c.move(c.speed_of())


@power(
    "p13132b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13132b(c: Cast) -> None:
    _running_jump(c)


@power(
    "p13134b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13134b(c: Cast) -> None:
    near = c.within(1, side="other")
    if near:
        partner = c.choose(near, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p13136b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13136b(c: Cast) -> None:
    c.shift(2)


@power(
    "p13141b",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.STANCE],
    attack=Attack(DEX, vs=FORT),
    requires=active("p13141"),
    requires_text="the p13141 power must be active",
)
def p13141b(c: Cast) -> None:
    """The stance ending is an Effect, so it happens whether or not the blow
    lands; it is the stance standing on the monk, whichever one that is."""
    if c.strike():
        c.damage(0, c.dex_mod)
        c.stunned(until=When.SAVE_ENDS)
    else:
        c.damage("2d8", c.dex_mod)
    posture = c.world.effects.stance_of(c.me)
    if posture is not None:
        c.world.effects.end(posture, c.ref)


@power(
    "p13219b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p13219b(c: Cast) -> None:
    _step_or_run(c)


@power(
    "p13221b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p13221b(c: Cast) -> None:
    _step_or_run(c)


@power(
    "p16133b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def p16133b(c: Cast) -> None:
    """The riposte is provoked by this movement, so it lives exactly as long
    as the movement does."""

    def scald(ev: Hit) -> None:
        if ev.target == c.me and getattr(ev, "opportunity", False):
            c.flat(2 + c.cha_mod, dtype=DamageType.FIRE, on=ev.attacker)

    hold = c.watch(Hit, scald, until=When.EOT)
    c.move(c.speed_of())
    _drop(c, [hold])


@power(
    "p16135b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16135b(c: Cast) -> None:
    """Shifting through enemy squares is phasing, granted for the turn."""
    steps = max(0, c.str_mod // 2)
    if steps:
        c.phasing(until=When.EOT)
        c.shift(steps)


@power(
    "p16137b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16137b(c: Cast) -> None:
    c.shift(1)

    def floor(ev: Hit) -> None:
        if ev.target == c.me and c.adjacent(ev.attacker):
            c.prone(on=ev.attacker)

    c.watch(Hit, floor, until=When.SONT, once=True)


@power(
    "p16139b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16139b(c: Cast) -> None:
    c.ignores_difficult(until=When.EOT)
    c.move(c.speed_of())


@power(
    "p16141b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def p16141b(c: Cast) -> None:
    c.shift(2)


@power(
    "p7449b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7449b(c: Cast) -> None:
    c.move(c.speed_of() + 2)


@power(
    "p7450b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7450b(c: Cast) -> None:
    """The printed target -- "one ally or one prone enemy" -- has no header
    expression, so the pool is built in the body and offered as a choice."""
    options = [a for a in c.within(1, side="ally") if a != c.me]
    options += [f for f in c.within(1, side="enemy") if c.is_(Condition.PRONE, on=f)]
    if options:
        partner = c.choose(options, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p7452b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7452b(c: Cast) -> None:
    c.shift(2)


@power(
    "p7453b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7453b(c: Cast) -> None:
    holds = [c.ignores_difficult(until=When.EOT)]
    for defence in (AC, FORT, REF, WILL):
        holds.append(
            c.bonus(
                defence, c.wis_mod, on=c.me, until=When.EOT, kind="power",
                when=lambda ctx: bool(ctx.get("opportunity")),
            )
        )
    c.move(c.speed_of() + 2)
    _drop(c, holds)


@power(
    "p7454b",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7454b(c: Cast) -> None:
    """"The first enemy you move away from" is read as the one you are
    standing next to when the movement begins."""
    near = c.within(1, side="enemy")
    hold = c.no_provoke(from_=near[0], until=When.EOT) if near else None
    c.move(c.speed_of() + 2)
    _drop(c, [hold])


@power(
    "p7535b",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7535b(c: Cast) -> None:
    _running_jump(c)


@power(
    "p16147b",
    level=2,
    cls="monk",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    requires=active("p16147"),
    requires_text="the p16147 power must be active",
    trigger="an enemy enters a square adjacent to you",
    on=Trigger(
        AdjacencyGained, _enemy_stepped_up, "an enemy enters a square adjacent to you"
    ),
)
def p16147b(c: Cast) -> None:
    """"You can shift" is optional, and the square has to touch the enemy
    that stepped up, so the destination is picked rather than left loose."""
    foe = getattr(c.trigger, "mover", 0)
    spot = c.world.get(foe, Position) if foe else None
    if spot is not None:
        beside = [
            s
            for s in c.world.reachable_squares(c.me, 1)
            if s in spread({spot.square}, 1)
        ]
        if beside and c.may("shift to a square beside the enemy", who=c.me):
            dest = c.choose(beside, "shift beside the enemy")
            if dest is not None:
                c.shift(to=dest)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.EOT, kind="power",
            when=lambda ctx, f=foe: ctx.get("attacker") == f,
        )


@power(
    "p11216b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11216b(c: Cast) -> None:
    """"Each time" means the bonuses add, so they are left untyped; the
    counting only runs for the length of the movement."""

    def quicken(ev: AttackDeclared) -> None:
        if ev.target == c.me:
            c.bonus("speed", 1, on=c.me, until=When.EONT)

    hold = c.watch(AttackDeclared, quicken, until=When.EOT)
    c.move(c.speed_of() + 2)
    _drop(c, [hold])


@power(
    "p11218b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11218b(c: Cast) -> None:
    if c.str_mod > 0:
        c.resist(c.str_mod, until=When.EONT)
    c.shift(2)


@power(
    "p13146b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
)
def p13146b(c: Cast) -> None:
    near = c.within(1, side="other")
    if near:
        partner = c.choose(near, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p13148b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.THUNDER],
)
def p13148b(c: Cast) -> None:
    c.move(c.speed_of() + 2)


@power(
    "p13150b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=Target("other", 1),
)
def p13150b(c: Cast) -> None:
    """A jump to a square beside the target, which `c.run_at` is: it closes
    to contact rather than walking a chosen path."""
    anchor = c.target
    if anchor is None:
        return
    hold = c.no_provoke(until=When.EOT)
    c.run_at(anchor)
    _drop(c, [hold])


@power(
    "p13152b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13152b(c: Cast) -> None:
    """The immunity is only from the enemies adjacent when the movement
    starts, so it is armed per enemy rather than against everybody."""
    holds = [c.no_provoke(from_=foe, until=When.EOT) for foe in c.within(1, side="enemy")]
    c.move(c.speed_of())
    _drop(c, holds)


@power(
    "p13223b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p13223b(c: Cast) -> None:
    _step_or_run(c)


@power(
    "p15984b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=Target("other", 1),
)
def p15984b(c: Cast) -> None:
    """"Shift 1 and slide the target 1, swapping places" is one exchange."""
    partner = c.target
    if partner is not None:
        c.swap(partner)


@power(
    "p16150b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16150b(c: Cast) -> None:
    c.shift(1)
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
    c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p16152b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def p16152b(c: Cast) -> None:
    """Partial concealment is written as the +2 it is worth to the monk's
    defences, for the length of the movement it is printed on."""
    holds = [
        c.bonus(defence, 2, on=c.me, until=When.EOT, kind="concealment")
        for defence in (AC, FORT, REF, WILL)
    ]
    c.move(c.speed_of() + 2)
    _drop(c, holds)


@power(
    "p16154b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
)
def p16154b(c: Cast) -> None:
    c.immobilized(on=c.me, until=When.SONT)
    c.resist(3 + c.str_mod, until=When.SONT)


@power(
    "p7459b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p7459b(c: Cast) -> None:
    """Only the misses made during the movement count, so the watch is taken
    down again once the monk has stopped."""

    def fumbled(ev: Miss) -> None:
        if ev.target == c.me and getattr(ev, "opportunity", False):
            c.grants_advantage(on=ev.attacker, to="me", until=When.EOT)

    hold = c.watch(Miss, fumbled, until=When.EOT)
    c.move(c.speed_of() + 2)
    _drop(c, [hold])


@power(
    "p7460b",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.THUNDER],
)
def p7460b(c: Cast) -> None:
    near = c.within(1, side="enemy")
    hold = None
    if near:
        ignored = c.choose(near, "whose reach to slip")
        if ignored is not None:
            hold = c.no_provoke(from_=ignored, until=When.EOT)
    c.move(c.speed_of() + 2)
    _drop(c, [hold])
