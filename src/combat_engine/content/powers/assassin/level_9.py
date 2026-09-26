"""Assassin, level 9."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    DEX,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Condition,
    ConditionEnded,
    DamageApplied,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p9435",
    level=9,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RELIABLE, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p9435(c: Cast) -> None:
    """Escapes are not rolled anywhere, so the -5 to them has nothing reading
    it and is dropped. The -2 is gated on the attack context's `target`, which
    is the caster -- the printed line is "against you". The Special (sustain
    as a minor and lose the effect) is a choice of action cost and has no
    field for it."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.grab()
        c.penalty(
            "attack",
            2,
            on=victim,
            kind="power",
            until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") == c.me,
        )

        def squeeze() -> None:
            c.damage("2d10", c.dex_mod, on=victim)

        c.on_sustain(
            c.effect(c.ref, until=When.SUSTAIN, on=victim, sustain=STANDARD), squeeze
        )

        def let_go(ev: ConditionEnded) -> None:
            if ev.target == victim and ev.condition is Condition.GRABBED:
                c.damage("1d10", c.dex_mod, on=victim)

        c.watch(ConditionEnded, let_go, until=When.ENCOUNTER, once=True)


@power(
    "p9436",
    level=9,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=FORT),
)
def p9436(c: Cast) -> None:
    """The Effect line stands whether the swing lands or not, so the watch is
    armed outside the branch."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)

    def backlash(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.source in c.enemies():
            c.flat(5, on=victim)

    c.watch(DamageApplied, backlash, until=When.ENCOUNTER)


@power(
    "p9437",
    level=9,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=WILL),
)
def p9437(c: Cast) -> None:
    """"The target cannot see you" is the same held state as being invisible,
    pointed at one creature and ended by a save."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)
    c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)
