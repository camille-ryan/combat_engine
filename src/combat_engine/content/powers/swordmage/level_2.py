"""Swordmage, level 2: the utilities.

Three of these are immediate interrupts, and an interrupt is the only thing
that can get in front of a blow: `p5740` reaches the damage before it is
rolled, and `p5741` raises a defence in the window between the roll and the
comparison, which is the one moment a bonus can still turn a hit into a miss.

A stance's riders are `When.ENCOUNTER` and ended from `stance.on_end`; a
second `When.STANCE` effect would confuse `Effects.stance_of`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    MoveEnd,
    Trigger,
    When,
    Window,
    both,
    by_melee,
    either,
    get,
    power,
    targets_me,
    would_hit_me,
)

from . import ally_target_within, beside, by_my_mark, i_teleported

_ELEMENTS = [
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
]


@power(
    "p10434",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p10434(c: Cast) -> None:
    me = c.me
    stance = c.stance(label=c.ref)

    def hobbled(ctx: dict) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return c.is_(Condition.SLOWED, on=who) or c.is_(Condition.IMMOBILIZED, on=who)

    riders = [c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=hobbled, kind="power")]
    if c.build("ensnarement"):
        riders.append(c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=hobbled, kind="power"))
    for rider in riders:
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


@power(
    "p12218",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def p12218(c: Cast) -> None:
    """The printed targets are weapons, which the board does not carry, so
    the effect is written where a weapon's damage is actually decided:
    `DamageRolled.dtype` is mutable and every reader downstream uses it."""
    kind = c.choose(
        [DamageType.FIRE, DamageType.COLD, DamageType.LIGHTNING, DamageType.FORCE],
        "the blades take on",
    )
    if kind is None:
        return
    folks = set(c.within(5, side="ally"))
    hold = c.effect(f"{c.ref} keen", until=When.SUSTAIN, on=c.me, sustain=MINOR)

    def recolour(ev: DamageRolled) -> None:
        if ev.source not in folks:
            return
        p = get(ev.detail or "")
        if p is not None and Keyword.WEAPON in p.keywords:
            ev.dtype = kind

    rider = c.watch(
        DamageRolled, recolour, until=When.ENCOUNTER, on=c.me,
        window=Window.BEFORE, label=c.ref,
    )
    if hold is not None:
        hold.on_end.append(lambda: c.world.effects.end(rider, "the edge dulls"))


@power(
    "p3332",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3332(c: Cast) -> None:
    kind = c.choose(_ELEMENTS, "you ward yourself against")
    if kind is not None:
        c.resist(5 + c.con_mod, kind, until=When.ENCOUNTER, on=c.me)


@power(
    "p3333",
    level=2,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3333(c: Cast) -> None:
    """`c.save` follows the target, and this row has none -- so it is named."""
    c.save(on=c.me)


@power(
    "p3900",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p3900(c: Cast) -> None:
    """The extra square is itself a shift, so the latch keeps it from
    answering its own `MoveEnd` for the rest of the encounter."""
    me = c.me
    stance = c.stance(label=c.ref)
    busy: dict[str, bool] = {}

    def further(ev: MoveEnd) -> None:
        if ev.actor != me or ev.kind_ != "shift" or busy.get("in"):
            return
        busy["in"] = True
        try:
            c.shift(1, who=me)
        finally:
            busy["in"] = False

    rider = c.watch(MoveEnd, further, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))


@power(
    "p3903",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p3903(c: Cast) -> None:
    me = c.me
    stance = c.stance(label=c.ref)
    for rider in (
        c.bonus(AC, 2, on=me, until=When.ENCOUNTER, kind="power"),
        c.bonus(REF, 2, on=me, until=When.ENCOUNTER, kind="power"),
    ):
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


@power(
    "p4276",
    level=2,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p4276(c: Cast) -> None:
    """Two named creatures change places, which `c.swap` does atomically --
    either both move or neither, which is the "or the power fails" clause."""
    pool = [w for w in c.within(3, side="ally") if w != c.me]
    if not pool:
        return
    mate = c.choose(sorted(pool), "you change places with")
    if mate is not None:
        c.swap(mate)


@power(
    "p4797",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="an enemy you have marked attacks an ally",
    on=Trigger(
        AttackRolled,
        both(by_my_mark, ally_target_within(10)),
        "an enemy you have marked attacks an ally",
    ),
)
def p4797(c: Cast) -> None:
    """The printed target is "one ally in the burst" and the one that wants
    it is the one being swung at, which the triggering event names."""
    ev = c.trigger
    mate = getattr(ev, "target", None)
    if mate is None or mate == c.me:
        return
    kind = c.choose(_ELEMENTS, "you ward your ally against")
    if kind is not None:
        c.resist(5 + c.con_mod, kind, until=When.EONT, on=mate)


@power(
    "p5739",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="you teleport using a swordmage power",
    on=Trigger(MoveEnd, i_teleported, "you teleport using a swordmage power"),
)
def p5739(c: Cast) -> None:
    """Measured after the blink, which is what `MoveEnd` guarantees: the
    ally arrives beside where I ended up, not where I set off from."""
    pool = [w for w in c.within(2, side="ally") if w != c.me]
    if not pool:
        return
    mate = c.choose(sorted(pool), "comes with you")
    spot = beside(c) if mate is not None else None
    if mate is not None and spot is not None:
        c.teleport(c.distance(mate) + 1, who=mate, to=spot)


@power(
    "p5740",
    level=2,
    cls="swordmage",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="an attack hits you or an ally within 10 squares of you",
    on=Trigger(
        Hit,
        either(targets_me, ally_target_within(10)),
        "an attack hits you or an ally within 10 squares of you",
    ),
)
def p5740(c: Cast) -> None:
    """`Hit` is announced before the body rolls anything, so the reduction
    is armed on the damage rather than applied to a number that does not
    exist yet. The latch spends it on the first roll it actually softens."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    cut = 5 + c.con_mod
    spent: dict[str, bool] = {}

    def soften(ev: DamageRolled) -> None:
        if ev.target != victim or spent.get("done"):
            return
        spent["done"] = True
        ev.amount = max(0, ev.amount - cut)

    c.watch(
        DamageRolled, soften, until=When.EOT, on=c.me,
        window=Window.BEFORE, label=c.ref,
    )
    if c.build("shielding"):
        c.bonus("damage", c.con_mod, on=c.me, until=When.EONT, once=True)


@power(
    "p5741",
    level=2,
    cls="swordmage",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="an enemy marked by you hits you with a melee attack",
    on=Trigger(
        AttackRolled,
        both(would_hit_me, by_melee, by_my_mark),
        "an enemy marked by you hits you with a melee attack",
    ),
)
def p5741(c: Cast) -> None:
    """Declared on `AttackRolled`, not `Hit`: the defence is read again once
    this window closes, which is the only way "+4 to AC" can still turn the
    blow aside. `Hit` would be too late to do anything but watch."""
    me = c.me
    foe = getattr(c.trigger, "attacker", None)
    c.bonus(AC, 4, on=me, until=When.EONT, kind="power")
    c.bonus(REF, 4, on=me, until=When.EONT, kind="power")
    if foe is None:
        return

    def anyway(ev: Hit) -> None:
        if ev.attacker == foe and ev.target == me:
            c.blinded(on=foe, until=When.EONT)

    c.watch(Hit, anyway, until=When.EOT, on=me, once=True, label=c.ref)
