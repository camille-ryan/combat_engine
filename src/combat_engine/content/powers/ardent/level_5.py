"""Ardent, level 5: the dailies. None of these is augmentable."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    EACH_ENEMY,
    ONE_ALLY,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    TurnStart,
    When,
    power,
    spread,
)
from combat_engine.engine.query import creatures

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    return [a for a in c.within(radius, of=of, side="ally") if a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10283",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(CHA, vs=AC),
)
def p10283(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.cha_mod)
    if not c.last:
        return
    area = spread({c.here}, 2)
    c.zone(area, until=When.EONT)

    def payout(ev: DamageApplied) -> None:
        if ev.source not in (c.me, *c.allies()):
            return
        if ev.target not in c.in_squares(area, side="enemy"):
            return
        who = _pick(c, c.in_squares(area, side="ally"), "who makes a saving throw")
        if who is not None:
            c.save(on=who, bonus=c.wis_mod)

    c.watch(DamageApplied, payout, until=When.EONT)


@power(
    "p10284",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.HEALING, Keyword.TELEPORTATION],
)
def p10284(c: Cast) -> None:
    """"You and one ally in the burst" is one printed target plus the caster, so
    the header names the ally.

    **"If both basic attacks miss, you regain the use of this power" is
    written now.** The old note said "nothing can refund a daily", and
    `c.restore_use` is exactly that -- *"you regain the use of your second
    wind"* is its own docstring's example. #1341.

    Counted off the `Hit` watch already here rather than by a second
    subscription: `reward` fires for every hit by either swinger, so a
    flag set there says whether anything landed. Both grants resolve inside
    this body, so the count is final by the time it is read.
    """
    friend = c.target
    if friend is None:
        return
    c.swap(friend)

    landed: list[int] = []

    def reward(ev: Hit) -> None:
        if ev.attacker not in (c.me, friend):
            return
        landed.append(ev.attacker)
        who = _pick(c, [c.me, *c.allies()], "who is mended")
        if who is not None:
            c.surge(on=who)
            c.save(on=who)

    c.watch(Hit, reward, until=When.EOT)
    swung = 0
    for swinger in (c.me, friend):
        foe = _pick(c, c.within(1, of=swinger, side="enemy"), "whom to strike")
        if foe is not None:
            swung += 1
            c.grant_attack(swinger, on=foe, attack_bonus=2)
    # "If both basic attacks miss" -- so only when both were actually made.
    if swung == 2 and not landed:
        c.restore_use(c.ref)


@power(
    "p11099",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(CHA, vs=AC),
)
def p11099(c: Cast) -> None:
    """A zone that stays centred on you is an aura. The insubstantial clause is
    dropped: nothing lets an attack ignore that quality."""
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    if not c.last or not c.con_mod:
        return
    c.aura(1, until=When.EONT)
    for ally in c.allies():
        c.bonus(
            "damage", c.con_mod, on=ally, until=When.EONT,
            when=lambda _ctx, a=ally: c.distance(to=a) <= 1, kind="power")


@power(
    "p11100",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.CHARM],
    attack=Attack(CHA, vs=AC),
)
def p11100(c: Cast) -> None:
    """**Both aftereffects are written now.** The old note said neither half
    "can be said", and both could: `c.conceal(when=)` is handed the attack
    context, so *against the target* is a gate rather than concealment from
    everybody, and a Perception penalty is `c.penalty("skill:perception")`,
    which five rows already use. #1341.

    An **aftereffect**, not a second clause beside the blindness: the card
    prints it under `Aftereffect:`, meaning it lands when the blindness
    ends. `c.aftereffect` hangs it off the effect the branch just laid.

    Both branches get one, which is what the card prints -- the Hit's
    blindness is save-ends and the Miss's runs to the start of the next
    turn, and the aftereffect itself is save-ends on either.
    """
    victim = c.target

    def blinkered(until: When) -> None:
        """Everyone is concealed from the target, and it sees badly."""
        if victim is None:
            return
        for other in creatures(c.world):
            if other == victim:
                continue
            c.conceal(
                on=other,
                until=until,
                when=lambda ctx: ctx.get("attacker") == victim,
            )
        c.penalty("skill:perception", 5, on=victim, until=until)

    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.aftereffect(
            c.blinded(until=When.SAVE_ENDS),
            lambda: blinkered(When.SAVE_ENDS),
        )
    else:
        c.half_damage(c.w(), c.cha_mod)
        c.aftereffect(
            c.blinded(until=When.SONT),
            lambda: blinkered(When.SAVE_ENDS),
        )


@power(
    "p12948",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12948(c: Cast) -> None:
    """`escalate` runs on every failed save, which is what "each failed saving
    throw" wants; the worsening to immobilized is latched to the first."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.cha_mod)
    worsened: list[int] = []

    def failed(_eff: Effect) -> None:
        if not worsened:
            worsened.append(1)
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)
        who = _pick(c, _friends(c, 20), "who shifts")
        if who is not None and c.can_see(who):
            c.shift(1, who=who)

    c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=failed
    )


@power(
    "p12949",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p12949(c: Cast) -> None:
    """"Enemies are weakened while adjacent to you" has no continuous form -- a
    condition cannot be gated on a distance -- so it is laid on whoever is
    adjacent now and re-laid on any enemy starting its turn adjacent."""
    if c.strike():
        c.pull(5)
        if c.adjacent():
            c.weakened(until=When.SAVE_ENDS)
    if not c.last:
        return

    def weaken(who: int) -> None:
        c.weakened(on=who, until=When.EONT)

    for foe in c.within(1, side="enemy"):
        weaken(foe)

    def tick(ev: TurnStart) -> None:
        if ev.actor in c.within(1, side="enemy"):
            weaken(ev.actor)

    c.watch(TurnStart, tick, until=When.EONT)

    struck: dict[int, int] = {}

    def lash(ev: DamageApplied) -> None:
        if ev.target not in c.within(1, side="enemy"):
            return
        if struck.get(ev.target) == c.world.round:
            return
        struck[ev.target] = c.world.round
        c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=ev.target, from_attack=False)

    c.watch(DamageApplied, lash, until=When.EONT)


@power(
    "p12950",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12950(c: Cast) -> None:
    """The Special -- standing in for a charge's basic attack, for +1 -- is the
    `plus` on the roll when this use is a charge."""
    if c.strike(plus=1 if c.charge else 0):
        c.damage(c.w(), c.cha_mod)
    else:
        c.half_damage(c.w(), c.cha_mod)
    if not c.last:
        return

    def tick(ev: TurnStart) -> None:
        who = ev.actor
        if who == c.me or who not in c.allies() or c.distance(to=who) > 5:
            return
        c.bonus(
            "attack", 2, on=who, until=When.EOT, kind="power",
            when=lambda ctx: bool(ctx.get("charge")),
        )
        if c.cha_mod:
            c.bonus(
                "damage", c.cha_mod, on=who, until=When.EOT, kind="power",
                when=lambda ctx: bool(ctx.get("charge")),
            )

    c.watch(TurnStart, tick, until=When.EONT)


@power(
    "p12951",
    level=5,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.WEAPON,
        Keyword.PSYCHIC,
        Keyword.FEAR,
    ],
    attack=Attack(CHA, vs=WILL),
)
def p12951(c: Cast) -> None:
    """The secondary attack is the same line as the primary, so `c.strike` rolls
    it at the second creature. The toll is 10 on a hit and 5 on a miss, and the
    hold is owned by the primary target so the primary target saves."""
    victim = c.target
    if victim is None:
        return
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(), c.cha_mod, dtype=DamageType.PSYCHIC)
    toll = 10 if landed else 5

    def burn(ev: AttackDeclared) -> None:
        if ev.attacker == victim:
            c.flat(toll, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(AttackDeclared, burn, on=victim, until=When.SAVE_ENDS)

    near = [e for e in c.within(3, of=victim, side="enemy") if e != victim]
    second = _pick(c, near, "the second mind")
    if second is not None and c.strike(on=second):
        c.dazed(until=When.SAVE_ENDS, on=second)
