"""Ardent, level 7.

All at-will and all augmentable; the base form is written and each docstring
names the augment clauses dropped with it. Two printed rows are absent: one
whose rider is "rolls damage twice and uses the lower roll", and one whose
Effect is "does not benefit from partial cover or partial concealment".
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    When,
    power,
)

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    return [a for a in c.within(radius, of=of, side="ally") if a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10287",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10287(c: Cast) -> None:
    """"Against the target's attacks" is a gate on the defence modifier, which
    `query.defence` is handed the attack context for. Dropped augments: Augment
    1 widens the bonus to all defences; Augment 2 is a burst with a zone."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    ally = _pick(c, _friends(c, 1), "who shares the guard")

    def theirs(ctx: dict) -> bool:
        return ctx.get("attacker") == victim

    for who in (c.me, ally):
        if who is not None:
            c.bonus(AC, 2, on=who, until=When.EONT, when=theirs, kind="power")


@power(
    "p10288",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
)
def p10288(c: Cast) -> None:
    """No attack line of its own -- the ally swings. Dropped augments: Augment 1
    adds +3 damage if the ally has the target marked; Augment 2 makes it a burst
    with an attack of your own."""
    victim = c.target
    ally = _pick(c, _friends(c, 1), "who swings")
    if victim is None or ally is None:
        return

    def landed(ev: Hit) -> None:
        if ev.attacker == ally and ev.target == victim:
            c.shift(1)
            c.shift(1, who=ally)

    c.watch(Hit, landed, until=When.EOT, once=True)
    c.grant_attack(ally, on=victim)


@power(
    "p11104",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p11104(c: Cast) -> None:
    """Dropped augments: Augment 1 lets you shift and then charge with this;
    Augment 2 sends one or two allies charging."""
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    if c.first:
        for ally in _friends(c, 1):
            c.bonus("attack", 1, on=ally, until=When.SONT, kind="power")


@power(
    "p11105",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=AC),
)
def p11105(c: Cast) -> None:
    """Dropped augments: Augment 1 pays a healing surge for a hit on Will;
    Augment 2 is 2[W] and pays every ally who hits, not just the next."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)

    def mend(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.heal(c.con_mod, on=ev.attacker)

    c.watch(Hit, mend, until=When.SONT, once=True)


@power(
    "p11106",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.WEAPON,
        Keyword.PSYCHIC,
        Keyword.CHARM,
    ],
    attack=Attack(CHA, vs=WILL),
)
def p11106(c: Cast) -> None:
    """The damage line carries no weapon dice at all -- just the modifier.
    Dropped augments: Augment 1 forces the target to take opportunity attacks;
    Augment 2 is 1[W] and buys two swings instead of one."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(0, c.cha_mod, dtype=DamageType.PSYCHIC)
    pool = [x for x in c.within(1, of=victim) if x != victim]
    who = _pick(c, pool, "whom it turns on")
    if who is not None:
        c.grant_attack(victim, on=who)


@power(
    "p12956",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12956(c: Cast) -> None:
    """The Effect is printed before the attack, so it runs before the roll --
    once, not once per target. Dropped augments: Augment 1 lengthens the shift
    to your Wisdom modifier; Augment 2 is 2[W] with a standing speed bonus."""
    if c.first:
        ally = _pick(c, _friends(c, 1), "who shifts first")
        if ally is not None:
            c.shift(1, who=ally)
    if c.strike():
        c.damage(c.w(), c.cha_mod)


@power(
    "p12957",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12957(c: Cast) -> None:
    """Dropped augments: Augment 1 adds psychic damage the first time the target
    hits an ally; Augment 2 is 2[W] and grants combat advantage."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.mark(until=When.EONT)


@power(
    "p12959",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12959(c: Cast) -> None:
    """Dropped augments: Augment 1 heals the ally if it hits with a charge;
    Augment 2 sends an ally charging outright."""
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    ally = _pick(c, _friends(c, 5), "who quickens")
    if ally is not None:
        c.bonus("speed", 2, on=ally, until=When.EONT, kind="power")
