"""Bard, level 1 continued: the rows that hang a watch on somebody else's swing.

Several of these change a die that has already been rolled. `resolve.attack`
re-reads the result after `AttackRolled` is announced, so a handler in that
window still decides the outcome -- `_shared.reroll` and `_shared.use_roll`
are that, and reading `Miss` instead would be too late.
"""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import reroll
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


def _enemy_attacks_ally(world: World, me: int, ev: Event) -> bool:
    """An enemy is swinging at one of my allies -- not at me."""
    foe = getattr(ev, "attacker", None)
    mate = getattr(ev, "target", None)
    if foe is None or mate is None or mate == me:
        return False
    mine = query.team(world, me)
    return query.team(world, foe) is not mine and query.team(world, mate) is mine


@power(
    "p2365",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p2365(c: Cast) -> None:
    """The mark is the ally's, which is what `by=` on `c.mark` is for."""
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally marks the target", optional=True)
    if pick is not None:
        c.mark(on=c.target, by=pick)


@power(
    "p2780",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p2780(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p2784",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.CHARM],
    attack=Attack(CHA, vs=AC),
)
def p2784(c: Cast) -> None:
    """"Any ally within 5 squares" is taken at the moment the row goes off --
    the party it names is the party standing there now."""
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    for mate in c.within(5, side="team"):
        c.bonus("damage", 1, on=mate, until=When.ENCOUNTER, kind="power")
        c.bonus("save", 1, on=mate, until=When.ENCOUNTER, kind="power")

    def scatter(ev: Dropped) -> None:
        for mate in c.within(5, of=ev.actor, side="team"):
            c.shift(1, who=mate)

    c.watch(Dropped, scatter, until=When.ENCOUNTER, on=c.me, label="p2784")


@power(
    "p2846",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p2846(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)

    def stumble(ev: Miss) -> None:
        if ev.attacker == victim:
            c.prone(on=victim)

    c.watch(Miss, stumble, until=When.EONT, on=c.me, once=True, label="p2846")


@power(
    "p2946",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p2946(c: Cast) -> None:
    """"Rolls a d20 twice and uses either result" is the better of two, taken
    on the announced roll while the outcome is still open."""
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)
    spent: list[int] = []

    def twice(ev: AttackRolled) -> None:
        if spent or ev.target != victim:
            return
        if ev.attacker != c.me and ev.attacker not in c.allies():
            return
        spent.append(1)
        reroll(c, ev, keep="best")

    c.watch(AttackRolled, twice, until=When.EONT, on=c.me, label="p2946")


@power(
    "p2947",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p2947(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    step = max(1, c.wis_mod)

    def duck(ev: Miss) -> None:
        if ev.attacker != victim:
            return
        if ev.target == c.me or ev.target in c.allies():
            c.shift(step, who=ev.target)

    c.watch(Miss, duck, until=When.EONT, on=c.me, once=True, label="p2947")


@power(
    "p2970",
    level=1,
    cls="bard",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=REF),
    trigger="an enemy within range makes an attack roll against an ally",
    on=Trigger(AttackDeclared, _enemy_attacks_ally, "an enemy attacks an ally"),
)
def p2970(c: Cast) -> None:
    """The ally's answering swing is a basic attack: "an at-will attack" is
    whichever row that creature actually leads with, and `c.grant_attack`
    already reaches for its own."""
    mate = getattr(c.trigger, "target", None)
    if c.strike():
        c.damage(c.w(3), c.cha_mod)
    else:
        c.half_damage(c.w(3), c.cha_mod)
    if mate is not None:
        c.grant_attack(mate, on=c.target, attack_bonus=max(1, c.wis_mod))


@power(
    "p2971",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p2971(c: Cast) -> None:
    """"The next time an ally misses" is judged on the announced roll, not on
    `Miss`: by then the comparison has been made and a replacement roll would
    change nothing."""
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    spent: list[int] = []

    def stand_in(ev: AttackRolled) -> None:
        res = getattr(ev, "result", None)
        if spent or res is None or res.hit:
            return
        if ev.target != victim or ev.attacker not in c.allies():
            return
        spent.append(1)
        reroll(c, ev, keep="new")

    c.watch(AttackRolled, stand_in, until=When.ENCOUNTER, on=c.me, label="p2971")


@power(
    "p3075",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE],
    attack=Attack(CHA, vs=AC),
)
def p3075(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)
    extra = c.int_mod

    def burn(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.flat(extra, dtype=DamageType.FIRE, on=victim)

    if extra > 0:
        c.watch(Hit, burn, until=When.EONT, on=c.me, label="p3075")


@power(
    "p3099",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p3099(c: Cast) -> None:
    """The hold and the watch are separate, so the watch outlives the save by a
    moment; it checks `ended` rather than carrying a save-ends clock of its
    own, which would give the target a second saving throw."""
    victim = c.target
    if c.strike():
        c.damage("3d8", c.cha_mod)
    else:
        c.half_damage("3d8", c.cha_mod)
    held = c.effect("p3099 ill luck", on=victim, until=When.SAVE_ENDS)
    if held is None:
        return

    def falter(ev: Hit) -> None:
        if held.ended or ev.target != victim:
            return
        if ev.attacker == c.me or ev.attacker in c.allies():
            c.slowed(on=victim, until=When.EOTNT)

    c.watch(Hit, falter, until=When.ENCOUNTER, on=c.me, label="p3099")
