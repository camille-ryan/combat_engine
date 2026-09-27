"""Bard, level 7 continued: the standard-action encounter attacks."""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import free_near, square_of
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p2954",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.HEALING],
    attack=Attack(CHA, vs=WILL),
)
def p2954(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod)
    mates = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally spends a healing surge", optional=True)
    if pick is None:
        return
    if c.may("spend a healing surge", who=pick):
        c.surge(on=pick)
        c.temp_hp(c.int_mod, on=pick)


@power(
    "p2955",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=REF),
)
def p2955(c: Cast) -> None:
    """"All its defences equal its lowest" is worked out as penalties down to
    that number, and torn up the next time anything lands -- there is no way
    to overwrite a defence outright. The Virtue of Prescience line wants a
    Wisdom build the chassis does not offer."""
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(2), c.cha_mod)
    values = {d: query.defence(c.world, victim, d) for d in DEFENCES}
    floor = min(values.values())
    held = [
        c.penalty(d, values[d] - floor, on=victim, until=When.ENCOUNTER)
        for d in DEFENCES
        if values[d] > floor
    ]
    if not held:
        return

    def restore(ev: Hit) -> None:
        if ev.target != victim:
            return
        for effect in held:
            if effect is not None:
                c.world.effects.end(effect, "the target has been hit")

    c.watch(Hit, restore, until=When.ENCOUNTER, on=c.me, once=True, label="p2955")


@power(
    "p2956",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p2956(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)
    kept = c.roll("1d20")
    spent: list[int] = []

    def stand_in(ev: AttackRolled) -> None:
        if spent:
            return
        theirs = ev.attacker == victim
        ours = ev.target == victim and (ev.attacker == c.me or ev.attacker in c.allies())
        if not theirs and not ours:
            return
        res = getattr(ev, "result", None)
        if res is None or not c.may("use the kept roll", who=c.me):
            return
        spent.append(1)
        res.total += kept - res.natural
        res.natural = kept

    c.watch(AttackRolled, stand_in, until=When.EONT, on=c.me, label="p2956")


@power(
    "p3082",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p3082(c: Cast) -> None:
    """Whether the blow was a ranged one is read off the row that struck: the
    damage context carries no such key and the `Hit` carries no reach."""
    if not c.strike():
        return
    victim = c.target
    c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.pull(2, on=victim)

    def reel(ev: Hit) -> None:
        if ev.target != victim:
            return
        row = get(ev.power)
        if row is None:
            return
        if row.reach_of(getattr(ev, "branch", 0)).kind in ("ranged", "area_burst"):
            c.pull(1, on=victim)

    c.watch(Hit, reel, until=When.EONT, on=c.me, label="p3082")


@power(
    "p3083",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(CHA, vs=AC),
)
def p3083(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod, dtype=DamageType.COLD)
    c.slowed(until=When.EONT)
    mates = [a for a in c.within(3, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally shifts", optional=True)
    if pick is not None:
        c.shift(4, who=pick)


@power(
    "p3084",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p3084(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p4997",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=WILL),
)
def p4997(c: Cast) -> None:
    """`opportunity` is in the attack context, so the penalty is a gated one
    rather than a flat one that would also cost the target its turn."""
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.THUNDER)
    bite = 4 + c.int_mod if c.build("second-int") else 5
    c.penalty(
        "attack", bite, until=When.EONT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "p4998",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p4998(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(2), c.cha_mod)
    mates = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally is repositioned", optional=True)
    if pick is None:
        return
    spot = free_near(c, square_of(c, victim), skip=frozenset({square_of(c, pick) or (0, 0)}))
    if spot is not None:
        c.slide(2, on=pick, to=spot)
    if c.build("second-con") and c.con_mod > 0:
        c.bonus(AC, c.con_mod, on=pick, until=When.EONT, kind="power")
