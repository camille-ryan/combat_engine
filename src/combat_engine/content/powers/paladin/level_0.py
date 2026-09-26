"""Paladin, level 0: the smites, the interpose, and the two touch features.

The two smites answer `AttackDeclared`, which is the only window a Free
action triggered by "you target an enemy with an at-will weapon attack" can
resolve in -- and at that point the swing has not been rolled. So the
"if the triggering attack hits" half is armed as a watch on the same attack
rather than asked at once, which is what those rows would otherwise get
silently wrong.

"An enemy subject to your defender aura" has nothing to read: this engine
gives the paladin a mark, not an aura, and the mark is what the class's own
rows install. It is read as "marked by me" and said so here rather than in
three docstrings.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    SELF,
    STANDARD,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    MoveStart,
    Ranged,
    Relation,
    Square,
    Summon,
    Trigger,
    Usage,
    When,
    World,
    ally_within,
    get,
    leaves_me_out,
    power,
    spread,
)

from .marks import burning_mark

AT_WILL_WEAPON = "you target an enemy with an at-will weapon attack power"


def _tier(level: int) -> int:
    return 0 if level < 11 else (1 if level < 21 else 2)


def _smite(level: int) -> int:
    """2, then 4 at 7th, 7 at 17th, 10 at 27th -- both smites print it."""
    for step, floor in ((10, 27), (7, 17), (4, 7)):
        if level >= floor:
            return step
    return 2


def _my_at_will_weapon(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.usage is Usage.AT_WILL and Keyword.WEAPON in p.keywords


def _sanctioned_shift(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "kind_", "") != "shift":
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who)


def _sanctioned_attack_elsewhere(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, who):
        return False
    return leaves_me_out(world, me, ev)


def _on_the_triggering_hit(c: Cast, victim: int, fn: object) -> None:
    """The rider that only lands "if the triggering attack hits"."""

    def check(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            fn()  # type: ignore[operator]

    c.watch(Hit, check, until=When.EOT, on=c.me, once=True, label=f"{c.ref} rider")


def _free_square(c: Cast, radius: int) -> Square | None:
    for sq in sorted(spread({c.here}, radius)):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


@power(
    "p13553",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
    trigger=AT_WILL_WEAPON,
    on=Trigger(AttackDeclared, _my_at_will_weapon, AT_WILL_WEAPON),
)
def p13553(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.flat(_smite(c.level) + c.cha_mod, dtype=DamageType.RADIANT, on=victim)
    _on_the_triggering_hit(c, victim, lambda: c.dazed(on=victim, until=When.EONT))


@power(
    "p13815",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.SHADOW, Keyword.COLD, Keyword.NECROTIC],
    trigger=AT_WILL_WEAPON,
    on=Trigger(AttackDeclared, _my_at_will_weapon, AT_WILL_WEAPON),
)
def p13815(c: Cast) -> None:
    """"Cold and necrotic damage" is one number of two types, and both
    `c.flat` and `c.ongoing` take one; dealing it twice would double the
    row, so it lands as cold."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.flat(_smite(c.level) + c.cha_mod, dtype=DamageType.COLD, on=victim)
    burn = 5 + 5 * (c.level >= 17) + 5 * (c.level >= 27)
    _on_the_triggering_hit(
        c, victim, lambda: c.ongoing(burn, DamageType.COLD, on=victim)
    )


@power(
    "p13554",
    level=0,
    cls="paladin",
    usage=Usage.AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
    trigger="an enemy you have marked shifts, or attacks an ally and not you",
    on=[
        Trigger(MoveStart, _sanctioned_shift, "an enemy you have marked shifts"),
        Trigger(
            AttackDeclared,
            _sanctioned_attack_elsewhere,
            "an enemy you have marked attacks an ally and not you",
        ),
    ],
)
def p13554(c: Cast) -> None:
    """`MoveStart`, because the row has to be true where the enemy still is:
    by `MoveEnd` it has left and the aura it was standing in no longer
    covers it."""
    victim = c.target
    if victim is None:
        return
    c.flat(3 + 3 * _tier(c.level) + c.cha_mod, dtype=DamageType.RADIANT, on=victim)


@power(
    "p13555",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    trigger="an ally within 3 squares of you is damaged by an attack",
    on=Trigger(
        DamageRolled,
        ally_within(3),
        "an ally within 3 squares of you is damaged by an attack",
    ),
)
def p13555(c: Cast) -> None:
    """`DamageRolled` rather than `DamageApplied`: `c.absorb` moves a number
    that has been rolled and not yet dealt, which is the whole point of the
    interrupt. "Ignores your immunities and resistances" cannot be told to
    `deal_damage` and is dropped."""
    c.absorb(c.trigger)
    c.bonus("attack", 2, until=When.EONT, on=c.me, kind="power")


@power(
    "p13744",
    level=0,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.SUMMONING],
    summon=Summon(speed=8, size="large"),
    uses=2,
)
def p13744(c: Cast) -> None:
    """"Its checks use your statistics" is `Summon`'s default -- the block
    is an offset from the summoner's and this one prints none. The surge
    lost when the steed drops is not written: nothing here watches a
    summon's own `Dropped`."""
    spec = get(c.ref).summon
    steed = c.summon_inline(spec, at=c.origin or _free_square(c, 5))
    if steed:
        c.ride(on=steed)


@power(
    "p13816",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p13816(c: Cast) -> None:
    """Partial concealment is `c.conceal` without `total`, not a sight-
    blocking zone -- that is terrain and would blind both sides."""
    c.conceal(on=c.me, until=When.EONT)
    c.temp_hp(5 + 5 * _tier(c.level), on=c.me)


@power(
    "p13819",
    level=0,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.CONJURATION],
)
def p13819(c: Cast) -> None:
    """`solid=True` is the opt-in: the printed line says the servant occupies
    its square, and a conjuration is walked through by default. "Creatures
    other than you grant combat advantage while adjacent to it" is a
    standing rule about geometry rather than an effect on anybody, and no
    `Cast` method carries one, so it is dropped."""
    spot = _free_square(c, 2)
    if spot is None:
        return
    c.conjure(
        spot,
        until=When.ENCOUNTER,
        sustain=None,
        speed=6,
        solid=True,
        label=f"{c.ref} servant",
    )


@power(
    "p8097",
    level=0,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE],
    once_per_round=True,
)
def p8097(c: Cast) -> None:
    """The damage bonus is gated on the damage context's `target`, the one
    key that context does carry, and spent once. The sanction half is
    `burning_mark`, re-applied each time I attack that creature -- an
    encounter-long watch rather than a single mark, which is what "whenever
    you attack the target" says."""
    victim = c.target
    if victim is None:
        return
    c.bonus(
        "damage",
        5 + c.wis_mod,
        until=When.EONT,
        on=c.me,
        once=True,
        when=lambda ctx: ctx.get("target") == victim,
    )

    def sanction(ev: AttackDeclared) -> None:
        if ev.attacker == c.me and ev.target == victim:
            burning_mark(c, on=victim, until=When.EONT)

    c.watch(
        AttackDeclared,
        sanction,
        until=When.ENCOUNTER,
        on=c.me,
        label=f"{c.ref} sanction",
    )
