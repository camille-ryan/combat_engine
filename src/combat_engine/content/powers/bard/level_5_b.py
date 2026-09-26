"""Bard, level 5: the dailies that hang an effect on the caster's own aura."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.bard._shared import aura_allies, in_aura, reroll
from combat_engine.engine import *

ARCANE_FEAR = [Keyword.ARCANE, Keyword.FEAR]


@power(
    "p14461",
    level=5,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.PSYCHIC, Keyword.FEAR],
)
def p14461(c: Cast) -> None:
    """`TurnEnd` rather than `c.burns`: the card says ends its turn in the
    aura, where a zone's teeth are "enters it or starts its turn in it".

    Hit points are read first so the damage can be trimmed to leave the
    enemy on 1; the run happens exactly when the untrimmed 3 would have
    dropped it. `c.flee` is movement under the creature's own power away
    from the caster, which is the printed free action.
    """

    def bite(ev: Any) -> None:
        if ev.actor not in c.enemies() or not in_aura(c, ev.actor):
            return
        health = c.world.get(ev.actor, Health)
        if health is None:
            return
        room = health.hp - 1
        c.flat(min(3, max(0, room)), dtype=DamageType.PSYCHIC, on=ev.actor)
        if room < 3:
            c.flee(c.speed_of(ev.actor), on=ev.actor)

    c.watch(TurnEnd, bite, until=When.ENCOUNTER)


@power(
    "p14462",
    level=5,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_FEAR,
)
def p14462(c: Cast) -> None:
    """`c.cannot_attack` cannot say this: it is a standing per-creature bar,
    and the printed condition is geometric and re-checked at every swing. So
    the bar is a listener on `AttackDeclared`, which `resolve.attack` honours
    through `declared.cancelled`.

    **Dropped clause:** "or in your defender's aura" -- nothing marks another
    character's aura as a defender's.
    """

    def bar(ev: Any) -> None:
        if ev.target != c.me or ev.attacker not in c.enemies():
            return
        if not in_aura(c, ev.attacker) or c.marked(on=ev.attacker):
            return
        if query.defence(c.world, ev.attacker, Defense.WILL) <= 12 + c.level:
            ev.cancel(f"{c.ref}: cannot attack the caster")

    c.watch(AttackDeclared, bar, until=When.ENCOUNTER)


@power(
    "p14463",
    level=5,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
)
def p14463(c: Cast) -> None:
    """**Dropped clause:** the +2 power bonus to skill checks -- there are no
    skill checks in the engine and no `"skill"` key is read anywhere, so
    writing it would install a modifier nothing consults.

    "Roll twice and use either result" is `_shared.reroll(keep="best")`,
    which is live in the `AttackRolled` window because `resolve.attack`
    re-reads the result after the emit. The `c.note` is what spends the
    `once` hold, since a reroll only mutates a field.
    """

    def twice(ev: Any) -> None:
        if ev.attacker not in aura_allies(c):
            return
        if c.may("roll that attack twice") and reroll(c, ev, keep="best"):
            c.note(f"{c.ref}: that ally rolls twice and keeps either result")

    c.watch(AttackRolled, twice, until=When.ENCOUNTER, once=True)
