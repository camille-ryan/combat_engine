"""Seeker level 2."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.seeker import PRIMAL, has_bow, while_in
from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    AttackRolled,
    Cast,
    CloseBurst,
    Keyword,
    Trigger,
    When,
    both,
    by_melee,
    enemy_within,
    get,
    power,
    would_hit_me,
)
from combat_engine.engine.events import SavingThrow


@power(
    "p11471",
    level=2,
    cls="seeker",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=PRIMAL,
    trigger="an enemy you can see saves against an effect that a save can end",
    on=Trigger(
        SavingThrow,
        enemy_within(10),
        "an enemy you can see saves against an effect that a save can end",
    ),
)
def p11471(c: Cast) -> None:
    """A saving throw is only ever rolled against a save-ends effect, so the
    second half of the printed trigger is the event class itself."""
    victim = c.target
    trip = getattr(c.trigger, "actor", None)
    if victim is None or victim == trip:
        return

    def punished(ev: Any) -> None:
        if getattr(ev, "target", None) == c.me:
            c.grants_advantage(on=victim, until=When.EOTNT)

    c.on_attack(punished, by=victim, until=When.ENCOUNTER)


@power(
    "p11472",
    level=2,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p11472(c: Cast) -> None:
    c.resist(c.str_mod, on=c.me, until=When.EONT)


@power(
    "p12789",
    level=2,
    cls="seeker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=has_bow,
    requires_text="a bow",
    trigger="you would be hit by a melee attack",
    on=Trigger(
        AttackRolled, both(would_hit_me, by_melee), "you would be hit by a melee attack"
    ),
)
def p12789(c: Cast) -> None:
    """"If the triggering attack still hit you" is worked out here rather than
    read back: the defence is re-read after this window closes, so at this
    moment the recorded result is the one the bonus has not been applied to
    yet."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.SONT)
    ev = c.trigger
    if ev is None:
        return
    if ev.natural >= 20 or ev.total >= ev.defence + 2:
        c.grants_advantage(on=ev.attacker, until=When.SONT)


@power(
    "p9510",
    level=2,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.STANCE],
)
def p9510(c: Cast) -> None:
    """The widened crit range is gated on the attack context, which carries
    both whether the shot is a ranged one and who it is aimed at. It is hung
    off the stance so that taking another puts it away."""

    def close_shot(ctx: dict[str, Any]) -> bool:
        p = get(ctx["power"])
        if p is None or Keyword.WEAPON not in p.keywords or not ctx.get("ranged"):
            return False
        return c.distance(ctx["target"]) <= 2

    form = c.stance(label=c.ref)
    while_in(
        c,
        form,
        c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER, when=close_shot),
    )


@power(
    "p9511",
    level=2,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9511(c: Cast) -> None:
    seen = [e for e in c.enemies() if c.can_see(e)]
    foe = c.choose(seen) if seen else None
    if foe is not None:
        c.no_provoke(from_=foe, until=When.EONT)
