"""Monk, level 1 (first half).

Most of these print **two** stat blocks under one id: a standard-action
attack and a separate move-action Effect. One id is one row here, so the
body does both halves, in the printed order -- which for a few of them puts
the movement *first*. The move half is an Effect, so it happens whether or
not the attack landed, and it is guarded with `c.first`/`c.last` so a
multi-target row moves once rather than once per victim.

There is no `Keyword.PSIONIC`, so the discipline keyword is dropped from
every header; the implement and damage-type keywords are all that survive.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Defense,
    Keyword,
    Melee,
    OpportunityWindow,
    Position,
    Square,
    UpTo,
    When,
    Window,
    get,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    ConditionApplied,
    DamageApplied,
    Hit,
    TurnEnd,
    TurnStart,
)

IMPLEMENT = [Keyword.IMPLEMENT]


def _swing(c: Cast, vs: Defense, on: int) -> bool:
    """Roll this row's own attack line against a different defence.

    A secondary attack line with its own defence has nowhere to live in the
    header -- `attack_alt` is the other half of a melee-or-ranged row -- so
    the printed bonus is taken off the primary line and rolled by hand.
    """
    line = get(c.ref).attack
    if line is None:
        return False
    bonus = line.bonus_for(c.world, c.me, c.ref, c.branch)
    return bool(c.attack(bonus, vs, on=on).hit)


def _square_of(c: Cast, who: int) -> Square | None:
    pos = c.world.get(who, Position)
    return pos.square if pos is not None else None


@power(
    "p11208",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p11208(c: Cast) -> None:
    """Bloodied is read before the swing, because the extra damage is owed
    for the state the target was in when it was hit. The standing half is a
    one-shot damage bonus gated on that same creature."""
    was_bloodied = c.bloodied()
    if c.strike():
        c.damage("2d8", c.dex_mod)
        if was_bloodied and c.str_mod > 0:
            c.flat(c.str_mod)
            victim = c.target
            c.bonus(
                "damage", c.str_mod, on=c.me, until=When.EONT, once=True,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )
    if c.last:
        c.move(c.speed_of())


@power(
    "p11210",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=FORT),
)
def p11210(c: Cast) -> None:
    """Flight is granted for the turn and then walked; falling is not
    modelled, so the "if you don't land" clause is dropped."""
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.THUNDER)
        for foe in c.within(1, of=c.target, side="enemy"):
            if foe != c.target:
                c.flat(c.str_mod, dtype=DamageType.THUNDER, on=foe)
    if c.last:
        c.mode("fly", c.speed_of(), until=When.EOT)
        c.move(c.speed_of())


@power(
    "p11212",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=FORT),
)
def p11212(c: Cast) -> None:
    """The link only exists with two targets. A re-entry latch stops the
    echo bouncing between them forever, and the pair is read off
    `c.targets` because one body call only knows its own victim."""
    if c.strike():
        c.damage("3d6", c.dex_mod, dtype=DamageType.THUNDER)
    else:
        c.half_damage("3d6", c.dex_mod, dtype=DamageType.THUNDER)
    if not c.last or len(c.targets) != 2:
        return
    pair = list(c.targets)
    fired: dict[str, object] = {}
    busy: list[int] = []

    def echo(ev: DamageApplied) -> None:
        if busy or ev.target not in pair or ev.amount <= 0:
            return
        now = (c.world.round, c.turn_of())
        if fired.get("when") == now:
            return
        fired["when"] = now
        other = pair[0] if ev.target == pair[1] else pair[1]
        busy.append(1)
        try:
            c.flat(c.str_mod, dtype=DamageType.THUNDER, on=other)
        finally:
            busy.clear()

    c.watch(DamageApplied, echo, until=When.ENCOUNTER)


@power(
    "p11213",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11213(c: Cast) -> None:
    """The whole power is the shift: whoever the monk passes is attacked,
    so the victims are gathered from the move rather than chosen up front.
    The header's target is what makes the row legal to declare."""
    if not c.first:
        return
    met: list[int] = []

    def passed(ev: AdjacencyGained) -> None:
        if ev.actor != c.me or ev.mover in (0, c.me):
            return
        if ev.other in c.enemies() and ev.other not in met:
            met.append(ev.other)

    sub = c.world.bus.on(AdjacencyGained, passed)
    try:
        c.shift(c.speed_of())
    finally:
        c.world.bus.off(sub)
    for foe in met:
        if c.strike(on=foe):
            c.damage("2d6", c.dex_mod, on=foe)
        else:
            c.half_damage("2d6", c.dex_mod, on=foe)


@power(
    "p13124",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13124(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.dex_mod)
        struck: dict[int, int] = {}

        def nip(ev: AdjacencyGained) -> None:
            if ev.actor != c.me or ev.mover in (0, c.me):
                return
            if ev.other not in c.enemies() or struck.get(0) == c.world.round:
                return
            struck[0] = c.world.round
            c.flat(c.con_mod, on=ev.other)

        c.watch(AdjacencyGained, nip, until=When.SONT)
    if c.last:
        c.shift(1)
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 1, on=c.me, until=When.SONT, kind="power")


@power(
    "p13126",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13126(c: Cast) -> None:
    """"You are no longer marked" has no method of its own, so the marks
    standing on the monk are ended one by one."""
    if c.strike():
        c.damage("1d8", c.dex_mod)
    if c.last:
        for eff in list(c.world.effects.of(c.me)):
            if Condition.MARKED in eff.conditions:
                c.world.effects.end(eff, c.ref)
        c.move(c.speed_of() + 2)


@power(
    "p13128",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13128(c: Cast) -> None:
    """Unattended objects are not on the board, so the object clause is
    dropped and only the creature half is written."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        if c.str_mod > 0:
            c.penalty(AC, c.str_mod, until=When.EONT)
    if c.last:
        c.mode("fly", c.speed_of(), until=When.EOT)
        c.move(c.speed_of())


@power(
    "p13130",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13130(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)

        def shove(ev: TurnEnd) -> None:
            if ev.ghost or ev.actor == c.me or ev.actor not in c.enemies():
                return
            if c.adjacent(ev.actor):
                c.slide(c.wis_mod, on=ev.actor)

        c.watch(TurnEnd, shove, until=When.SONT)
    if c.last:
        for d in (AC, FORT, REF, WILL):
            c.bonus(
                d, 2, on=c.me, until=When.SONT, kind="power",
                when=lambda ctx: bool(ctx.get("opportunity")),
            )
        c.move(c.speed_of())


@power(
    "p13132",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13132(c: Cast) -> None:
    """The secondary attack is against a different defence, so it is rolled
    off the primary line by hand. The jump half is written as the movement
    it is; the Athletics check itself has no combat consequence."""
    if not c.first:
        return
    if c.strike():
        c.damage("1d10", c.dex_mod)
        c.push(1)
        c.shift(1)
        others = [f for f in c.enemies() if f != c.target and c.distance(f) <= 1]
        second = c.choose(others) if others else None
        if second is not None and _swing(c, FORT, second):
            c.damage("1d10", c.dex_mod, on=second)
            c.slide(1, on=second)
            anchor = _square_of(c, second)
            for foe in c.within(1, of=second, side="enemy"):
                if foe != second:
                    c.push(1, on=foe, anchor=anchor)
    c.move(c.speed_of())


@power(
    "p13134",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13134(c: Cast) -> None:
    """"Cannot make opportunity attacks" is written by refusing the
    creature's opportunity window, which is the one place an opportunity
    action is offered."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
        if c.wielding("light blade") or c.wielding("spear"):
            victim = c.target

            def mute(ev: OpportunityWindow) -> None:
                if ev.actor == victim:
                    ev.cancel(c.ref)

            c.watch(OpportunityWindow, mute, until=When.EONT, window=Window.BEFORE)

        def riposte(ev: Hit) -> None:
            if ev.target == c.me and c.adjacent(ev.attacker):
                c.flat(c.con_mod, on=ev.attacker)

        c.watch(Hit, riposte, until=When.SONT)
    if c.last:
        near = c.within(1, side="other")
        if near:
            partner = c.choose(near)
            if partner is not None:
                c.swap(partner)


@power(
    "p13136",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13136(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)
        if c.wielding("mace") or c.wielding("staff"):
            c.flat(c.con_mod)
        c.slowed(until=When.EONT)
    if c.last:
        c.shift(2)


@power(
    "p13138",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=FORT),
)
def p13138(c: Cast) -> None:
    """"To the nearest square outside the blast" is written as a push of the
    blast's own depth, which clears it from anywhere inside."""
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
        c.push(3)
        c.condition(Condition.DEAFENED, until=When.ENCOUNTER)
    else:
        c.half_damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
        c.push(1)


@power(
    "p13139",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.STANCE],
    attack=Attack(DEX, vs=FORT),
)
def p13139(c: Cast) -> None:
    """The stance's trigger hangs off the stance effect rather than taking a
    `When.STANCE` duration of its own -- two stance effects would end each
    other, which is the whole of what makes a stance a stance."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.slide(2)
    if not c.last:
        return
    posture = c.stance(conditions=[Condition.SLOWED])
    struck: dict[int, int] = {}

    def snap(ev: AdjacencyGained) -> None:
        if ev.actor != c.me or ev.mover in (0, c.me):
            return
        if ev.other not in c.enemies() or not c.can_see(ev.other):
            return
        if struck.get(0) == c.world.round:
            return
        struck[0] = c.world.round
        c.flat(5, on=ev.other)
        c.slide(2, on=ev.other)

    hold = c.watch(AdjacencyGained, snap, until=When.ENCOUNTER)
    posture.on_end.append(lambda: c.world.effects.end(hold, "stance ended"))


@power(
    "p13140",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13140(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.dex_mod)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.dex_mod)
        c.penalty("attack", 2, until=When.EONT)
    if c.last:
        c.shift(4)


@power(
    "p13141",
    level=1,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*IMPLEMENT, Keyword.STANCE],
)
def p13141(c: Cast) -> None:
    """There is no immunity method, so "cannot be dazed or stunned" is
    written as shrugging the condition off the instant it lands. The
    stance's second stat block -- a standard-action attack -- has no id of
    its own in the spec, so it is not written."""
    posture = c.stance()

    def shrug(ev: ConditionApplied) -> None:
        if ev.target != c.me or ev.condition not in (Condition.DAZED, Condition.STUNNED):
            return
        for eff in list(c.world.effects.of(c.me)):
            if ev.condition in eff.conditions:
                c.world.effects.end(eff, c.ref)

    hold = c.watch(ConditionApplied, shrug, until=When.ENCOUNTER)
    posture.on_end.append(lambda: c.world.effects.end(hold, "stance ended"))


@power(
    "p13219",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13219(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.dex_mod)
        c.penalty(
            "attack", 2, until=When.EONT,
            when=lambda ctx: ctx.get("target") == c.me,
        )
    if c.last:
        c.shift(1)


@power(
    "p13221",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13221(c: Cast) -> None:
    """The shift is one square per creature hit, so the whole burst is
    resolved in the first body call and the rest return."""
    if not c.first:
        return
    landed = 0
    for foe in c.targets:
        if not c.can_see(foe):
            continue
        if c.strike(on=foe):
            c.damage("1d10", c.dex_mod, on=foe)
            landed += 1
    if landed:
        c.shift(landed)
    c.shift(1)


@power(
    "p16141",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.FIRE],
    attack=Attack(DEX, vs=REF),
)
def p16141(c: Cast) -> None:
    """The aura's bite is written as a watch rather than `c.burns`, because
    the printed line burns enemies only and a zone bites whoever stands in
    it."""
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.FIRE)
    if not c.last:
        return
    c.aura(1, until=When.SONT)

    def sear(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(2 + c.cha_mod, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, sear, until=When.SONT)
    c.shift(2)
