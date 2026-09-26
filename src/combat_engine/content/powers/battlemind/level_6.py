"""Battlemind, level 6."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MOVE,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    AttackDeclared,
    Cast,
    DamageRolled,
    Dropped,
    Event,
    Keyword,
    Ranged,
    Trigger,
    When,
    Window,
    World,
    both,
    by_me,
    power,
    targets_me,
)

from . import PSIONIC, beside, shift_beside


def _on_my_turn(world: World, me: int, ev: Event) -> bool:
    """"During your turn". `by_me` alone also catches a kill made with an
    opportunity attack on somebody else's."""
    return world.turn == me


@power(
    "p11167",
    level=6,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p11167(c: Cast) -> None:
    """"One creature marked by you" is not a target side the header can name,
    so the mark is checked here."""
    victim = c.target
    if victim is None or not c.marked(on=victim):
        return
    spot = beside(c, victim)
    if spot is not None:
        c.teleport(c.distance(victim) + 2, to=spot)
    c.grants_advantage(on=victim, until=When.EOT)


@power(
    "p13047",
    level=6,
    cls="battlemind",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="you take damage from an attack",
    on=Trigger(
        DamageRolled,
        targets_me,
        "you take damage from an attack",
        window=Window.BEFORE,
    ),
)
def p13047(c: Cast) -> None:
    """Half damage is the roll refused and half of it dealt back: `DamageRolled`
    is a proposal, so this has to answer in the interrupt window even though
    the printed action is a free one. The light it sheds afterwards is
    fiction, and dropped."""
    ev = c.trigger
    if ev is None:
        return
    amount = getattr(ev, "amount", 0)
    c.cancel()
    if amount > 1:
        c.flat(amount // 2, dtype=ev.dtype, on=c.me)


@power(
    "p13049",
    level=6,
    cls="battlemind",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    once_per_round=True,
    trigger="you reduce an enemy to 0 hit points during your turn",
    on=Trigger(
        Dropped,
        both(by_me, _on_my_turn),
        "you reduce an enemy to 0 hit points during your turn",
    ),
)
def p13049(c: Cast) -> None:
    c.shift(1)


@power(
    "p13468",
    level=6,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.ILLUSION],
)
def p13468(c: Cast) -> None:
    """The invisibility ends on the caster's own attack as well as at the end
    of the turn, which `c.invisible` alone does not say."""
    victim = c.target
    if victim is None or not c.marked(on=victim):
        return
    hidden = c.invisible(to=victim, on=c.me, until=When.EOT)

    def swung(ev: AttackDeclared) -> None:
        if hidden is not None and ev.attacker == c.me:
            c.world.effects.end(hidden, "you attacked")

    if hidden is not None:
        hidden.subs.append(c.world.bus.on(AttackDeclared, swung, owner=c.me))
    shift_beside(c, 5, victim)


@power(
    "p2632",
    level=6,
    cls="battlemind",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p2632(c: Cast) -> None:
    c.note("p2632: an Athletics jump at +5, counted as having a running start")
