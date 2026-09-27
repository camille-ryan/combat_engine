"""Rogue, level 2: lending the sneak attack to somebody else.

`c.sneak_damage` is the number, the twin of `c.quarry_damage` and added for
the same reason: `cf:rogue-scoundrel-f4` closes over its dice and nothing could
read them back. The modifier half comes from `c.total("cf:rogue-scoundrel-f4
damage")`, which is what `extra_damage` adds on top of them, so a rogue whose
build raised the rider lends the raised figure.

The extra damage is credited to the rogue rather than to the ally that
swung. Nothing lets one creature deal damage in another's name, and the
alternative -- leaving it out -- is the whole row.

`c.had_advantage` reads the advantage off the `Hit` rather than asking the
board again: a one-shot grant has already been spent by then.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    Cast,
    Hit,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p4476",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
)
def p4476(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    dice, me = c.sneak_damage(), c.me
    paid: list[bool] = []

    def on_hit(ev: Hit) -> None:
        if paid or ev.target != victim or ev.attacker == me:
            return
        if ev.attacker not in c.allies() or not c.had_advantage(ev):
            return
        paid.append(True)
        c.damage(dice, c.total("cf:rogue-scoundrel-f4 damage"), on=victim, detail=c.ref)

    c.watch(Hit, on_hit, until=When.SONT, on=me, label="p4476")
