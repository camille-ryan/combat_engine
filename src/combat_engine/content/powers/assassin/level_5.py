"""Assassin, level 5."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
    spread,
)
from combat_engine.engine.query import squares


@power(
    "p9423",
    level=5,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9423(c: Cast) -> None:
    """The splash watches the ongoing damage landing rather than the save, so
    it fires on exactly the beats the printed line names."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)

        def splash(ev: DamageApplied) -> None:
            if ev.target != victim or "ongoing" not in ev.detail:
                return
            for foe in c.within(2, of=victim, side="enemy"):
                if foe != victim:
                    c.flat(5, dtype=DamageType.POISON, on=foe)

        c.watch(DamageApplied, splash, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        for foe in c.within(2, of=victim, side="enemy"):
            if foe != victim:
                c.flat(3, dtype=DamageType.POISON, on=foe)


@power(
    "p9424",
    level=5,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9424(c: Cast) -> None:
    """The Perception bonus is a skill check nothing rolls; the sustained
    teleport is the mechanical half and is what the hold exists for. "Not
    hidden from you" is asked as `c.can_see`, which is the same question."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)

    def close_in() -> None:
        if not c.can_see(victim):
            return
        free = [s for s in spread(squares(c.world, victim), 1) if not c.in_squares([s])]
        if free:
            c.teleport(20, to=sorted(free)[0])

    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR), close_in)


@power(
    "p9425",
    level=5,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9425(c: Cast) -> None:
    """The second sentence -- enemies grant combat advantage while adjacent to
    the target -- is a standing property of a square rather than of a
    creature, and there is nothing to hold it on. Dropped."""
    if c.strike():
        c.damage("2d6", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")
    else:
        c.half_damage("2d6", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "p9426",
    level=5,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p9426(c: Cast) -> None:
    """The duplicate is a conjuration because the printed line insists it
    occupies its space and can be flanked with. Its own minor-action attack
    is `p9426b`, which reads the standing duplicate as its Requirement; the
    "allies cannot flank with it" clause has no field."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.dex_mod)
    free = [s for s in spread({c.there}, 1) if not c.in_squares([s])]
    if free:
        c.conjure(
            at=sorted(free)[0],
            label=c.ref,
            until=When.ENCOUNTER,
            sustain=None,
            speed=5,
        )
