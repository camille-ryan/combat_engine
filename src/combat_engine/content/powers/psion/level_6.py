"""Psion, level 6: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AttackDeclared,
    Cast,
    DamageRolled,
    Effect,
    Healed,
    Hit,
    Keyword,
    Miss,
    Ranged,
    SavingThrow,
    Trigger,
    When,
    Window,
    World,
    ally_within,
    both,
    by_keyword,
    by_me,
    power,
    query,
)

PSIONIC = [Keyword.PSIONIC]


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and ev.critical


def _my_will(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and ev.vs == WILL


def _made_it(world: World, me: int, ev: Any) -> bool:
    return bool(ev.saved)


@power(
    "p11318",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an enemy scores a critical hit against you",
    on=Trigger(Hit, _crit_on_me, "an enemy scores a critical hit against you"),
)
def p11318(c: Cast) -> None:
    """Reducing *one* attack's damage is a one-shot listener on the damage
    roll, in the window before it lands -- `c.resist` would shave everything
    else that reached you in the same turn as well."""
    cut = 10 + c.wis_mod
    spent = [False]

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me and not spent[0]:
            spent[0] = True
            ev.amount = max(0, ev.amount - cut)

    c.watch(
        DamageRolled,
        soften,
        until=When.EOT,
        window=Window.BEFORE,
        on=c.me,
        label=c.ref,
    )


@power(
    "p13327",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you hit an enemy within 10 squares with a psionic force at-will",
    on=Trigger(
        Hit,
        both(by_me, by_keyword(Keyword.FORCE), by_keyword(Keyword.PSIONIC)),
        "you hit an enemy with a psionic force attack",
    ),
)
def p13327(c: Cast) -> None:
    """"Unaugmented" and "at-will" are not askable of an event, so the trigger
    is the force-and-psionic part of the sentence; with no power points every
    psion at-will is unaugmented anyway."""
    ev = c.trigger
    if ev is None:
        return
    for near in c.within(1, of=ev.target, side="any"):
        if near not in (ev.target, c.me):
            c.grants_advantage(on=near, until=When.EONT, to="allies")


@power(
    "p13328",
    level=6,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.CONJURATION],
)
def p13328(c: Cast) -> None:
    """The prism goes on the board and can be pushed about at Intelligence
    modifier squares a turn. Three clauses are dropped: attacking as though
    you stood in its space (there is no standing grant for `c.strike(from_=)`),
    its hit points and the daze when it is destroyed, and the Perception
    bonus, which is not a combat effect."""
    c.conjure(until=When.ENCOUNTER, sustain=None, speed=c.int_mod)


@power(
    "p13329",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an enemy attack targets your Will",
    on=Trigger(AttackDeclared, _my_will, "an enemy attack targets your Will"),
)
def p13329(c: Cast) -> None:
    """Declared on the attack rather than on the hit: the bonus has to be up
    before the roll is compared, and whether it missed is only known
    afterwards, so the second half of the line is a listener on `Miss`."""
    ev = c.trigger
    c.bonus(WILL, 4, on=c.me, until=When.EONT)
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return

    def missed(m: Miss) -> None:
        if m.attacker == foe and m.target == c.me:
            c.grants_advantage(on=foe, until=When.EONT, to="allies")

    c.watch(Miss, missed, until=When.EOT, on=c.me, label=c.ref)


@power(
    "p13330",
    level=6,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an ally within 5 squares regains hit points or saves",
    on=[
        Trigger(Healed, ally_within(5), "an ally within 5 squares regains hit points"),
        Trigger(
            SavingThrow,
            both(ally_within(5), _made_it),
            "an ally within 5 squares succeeds on a saving throw",
        ),
    ],
)
def p13330(c: Cast) -> None:
    c.temp_hp(2 * c.int_mod, on=c.me)


@power(
    "p8237",
    level=6,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p8237(c: Cast) -> None:
    """"If you are not their nearest enemy" is settled once, when the power is
    used, and per watcher: nothing in `Cast` re-asks a condition like that as
    the board moves. Hitting anything ends the whole thing, which is the other
    half of the printed duration."""
    ours = [c.me, *c.allies()]
    held: list[Effect] = []
    for foe in c.enemies():
        nearest = min(ours, key=lambda a, f=foe: query.distance_between(c.world, f, a))
        if nearest != c.me:
            hidden = c.invisible(to=foe, on=c.me, until=When.ENCOUNTER)
            if hidden is not None:
                held.append(hidden)

    def spend(ev: Hit) -> None:
        if ev.attacker == c.me:
            for hidden in held:
                c.world.effects.end(hidden, c.ref)

    c.watch(Hit, spend, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p8238",
    level=6,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p8238(c: Cast) -> None:
    """Who is within 5 squares is settled each time the effect is sustained,
    which is as often as the printed line can be re-read. "If you move, the
    effect ends" is dropped -- an effect cannot end itself here."""

    def steady() -> None:
        c.immovable(on=c.me, until=When.EONT)
        for friend in c.within(5, of=c.me, side="ally"):
            if friend != c.me:
                c.immovable(on=friend, until=When.EONT)

    steady()
    c.on_sustain(c.effect(c.ref, on=c.me, until=When.SUSTAIN, sustain=MINOR), steady)
