"""Monk, level 2: the utilities.

Three rows are missing from this file and the omissions are deliberate --
see the batch report. Everything here that prints a Trigger declares it with
`on=`, since `trigger=` on its own is prose nothing reads.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    AttackDeclared,
    Cast,
    Health,
    Keyword,
    Trigger,
    When,
    both,
    by_me,
    by_melee,
    by_ranged,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    DamageApplied,
    ForcedMove,
    Hit,
    Miss,
)

STANCE_KW = [Keyword.STANCE]


def _melee(ctx: dict) -> bool:
    """Was the power that rolled this damage a melee one?

    The damage context carries no `attacker` and no `ranged`, so the reach
    has to be looked up off the row.
    """
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in ("melee", "close_burst", "close_blast")


@power(
    "p11214",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11214(c: Cast) -> None:
    """Standing on liquid is a way of moving, so it is granted as a mode
    for the turn alongside the free run over rough ground."""
    c.ignores_difficult(until=When.EOT)
    c.mode("swim", c.speed_of(), until=When.EOT)
    c.move(c.speed_of())


@power(
    "p13144",
    level=2,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p13144(c: Cast) -> None:
    """The damage context carries no weapon, so "unarmed" cannot be gated
    on; the modifier is melee-only and the unarmed half is dropped."""
    posture = c.stance()
    held = c.bonus(
        "damage", c.str_mod, on=c.me, until=When.ENCOUNTER, when=_melee
    )
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p13145",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p13145(c: Cast) -> None:
    far = c.speed_of() + c.wis_mod
    c.mode("fly", far, until=When.EOT)
    c.move(far)


@power(
    "p15983",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit by a ranged weapon attack",
    on=Trigger(Hit, both(targets_me, by_ranged), "you are hit by a ranged attack"),
)
def p15983(c: Cast) -> None:
    """Superior cover is +5 to AC and Reflex, gated on the attack being a
    ranged one -- which the attack context does carry."""
    for defence in (AC, REF):
        c.bonus(
            defence, 5, on=c.me, until=When.SONT, kind="cover",
            when=lambda ctx: bool(ctx.get("ranged")),
        )

    def sidestep(ev: Miss) -> None:
        if ev.target == c.me and by_ranged(c.world, c.me, ev):
            c.shift(1)

    c.watch(Miss, sidestep, until=When.SONT)


@power(
    "p16146",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit an enemy with a melee attack"),
)
def p16146(c: Cast) -> None:
    """Total concealment against one creature is written as being invisible
    to it; the printed line ends it on the first damage the monk takes."""
    foe = getattr(c.trigger, "target", None)
    c.shift(3)
    if foe is None:
        return
    veil = c.invisible(to=foe, on=c.me, until=When.SONT)

    def seen(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.amount > 0 and veil is not None:
            c.world.effects.end(veil, "took damage")

    c.watch(DamageApplied, seen, until=When.SONT, once=True)


@power(
    "p16147",
    level=2,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=STANCE_KW,
)
def p16147(c: Cast) -> None:
    """The stance's second stat block is an at-will interrupt on an enemy
    stepping up, so it is written into the stance as a standing watch
    rather than left as an unreachable second row. The Perception bonus is
    narrative and is not written."""
    posture = c.stance()

    def step_off(ev: AdjacencyGained) -> None:
        if ev.actor != c.me or ev.mover in (0, c.me):
            return
        foe = ev.other
        if foe not in c.enemies():
            return
        c.shift(1)
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 2, on=c.me, until=When.EOT,
                when=lambda ctx, f=foe: ctx.get("attacker") == f, kind="power")

    hold = c.watch(AdjacencyGained, step_off, until=When.ENCOUNTER)
    posture.on_end.append(lambda: c.world.effects.end(hold, "stance ended"))


@power(
    "p16149",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy attacks you",
    on=Trigger(AttackDeclared, targets_me, "an enemy attacks you"),
)
def p16149(c: Cast) -> None:
    c.temp_hp(c.dex_mod, on=c.me)
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power(
    "p7457",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are pulled, pushed, or slid",
    on=Trigger(ForcedMove, targets_me, "you are pulled, pushed, or slid"),
)
def p7457(c: Cast) -> None:
    """Refusing the shove is the whole power: the interrupt cancels the
    forced move and spends the same distance as a shift."""
    far = getattr(c.trigger, "squares", 0)
    c.cancel()
    if far > 0:
        c.shift(far)


@power(
    "p7458",
    level=2,
    cls="monk",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p7458(c: Cast) -> None:
    """The damage bonus is owed only once the temporary hit points are
    gone, so it waits on the damage that finishes them."""
    c.temp_hp(c.wis_mod, on=c.me)

    def emptied(ev: DamageApplied) -> None:
        if ev.target != c.me:
            return
        pool = c.world.get(c.me, Health)
        if pool is not None and pool.temp <= 0:
            c.bonus(
                "damage", c.wis_mod, on=c.me, until=When.EONT,
                once=True, when=_melee,
            )

    c.watch(DamageApplied, emptied, until=When.EONT, once=True)
