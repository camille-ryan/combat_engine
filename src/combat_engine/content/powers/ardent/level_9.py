"""Ardent, level 9: the dailies. None of these is augmentable."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    When,
    power,
)

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    return [a for a in c.within(radius, of=of, side="ally") if a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10289",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10289(c: Cast) -> None:
    """"It worsens by 2" -- and the old note had this exactly backwards.

    It said *"penalties are untyped and stack, so the sum is the printed
    number"*. They do not. `Mods.total` buckets penalties by `Mod.label`
    and takes the **worse of a bucket** -- 4e's "two from the same source do
    not add" -- and `c.bonus` defaults that label to the laying row's ref.
    So every worsening carried the label `p10289` and collapsed into the
    first -2.

    Measured on a board before the fix: a speed-6 creature given four
    successive -2 holds had **speed 4**, with four `Mod` entries all
    labelled `p10289`. So the whole second half of this card was
    unreachable -- speed never fell past the first step, "when the target's
    speed reaches 0" never came true, and the restrained-and-stunned
    finisher could not land on anything with a speed above 2.

    **The step number goes in the `Mod` label**, which is
    `monsters.level_06.skirmishers._worsen`'s settled answer to the same
    question -- and that helper's docstring says in as many words that this
    bug class *will recur*. It names four rows after `m238a3`; this is the
    fifth site and the first outside `monsters/`.

    **One save, not one per step**, which is the other half the stack got
    wrong. The card prints a single "(save ends)", so the first hold carries
    the throw and every worsening runs to the end of the encounter gated on
    that hold still standing -- `races.powers_c.p27`'s idiom for "save ends
    both" over two clauses. Ending the first one therefore drops the whole
    staircase, which is what *"the penalty ends, but the target is restrained
    and stunned"* says. The old note claimed the speed penalties "are left
    to run out with their own save", and the card ends them outright.

    #555."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        first = c.penalty("speed", 2, until=When.SAVE_ENDS)
        steps = [0]

        def worsen(ev: AttackDeclared) -> None:
            if ev.attacker != victim or first is None or first.ended:
                return
            if c.speed_of(victim) <= 0:
                return
            steps[0] += 1
            c.penalty(
                "speed", 2, on=victim, until=When.ENCOUNTER,
                label=f"{c.ref} worsening {steps[0]}",
                when=lambda _ctx, e=first: not e.ended,
            )
            if c.speed_of(victim) <= 0:
                # "The penalty ends" -- and ending the hold that carries the
                # save takes every worsening with it, since each is gated on
                # this one standing.
                c.end_effect(first)
                c.condition(
                    Condition.RESTRAINED,
                    Condition.STUNNED,
                    until=When.SAVE_ENDS,
                    on=victim,
                )

        c.watch(AttackDeclared, worsen, on=victim, until=When.SAVE_ENDS)

    def crowd(ev: TurnStart) -> None:
        if ev.actor in c.enemies() and c.adjacent_to(victim, ev.actor):
            c.slowed(until=When.SAVE_ENDS, on=ev.actor)

    c.watch(TurnStart, crowd, until=When.ENCOUNTER)


@power(
    "p10290",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10290(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.cha_mod)

    def feed(ev: DamageApplied) -> None:
        if ev.target != victim:
            return
        for who in (c.me, *_friends(c, 1)):
            c.temp_hp(3 + c.wis_mod, on=who)

    c.watch(DamageApplied, feed, until=When.ENCOUNTER)


@power(
    "p11107",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.WEAPON,
        Keyword.PSYCHIC,
        Keyword.ZONE,
    ],
    attack=Attack(CHA, vs=WILL),
)
def p11107(c: Cast) -> None:
    """A zone that stays centred on you is an aura. The hold carries the sustain
    cost and the watch reads it, since `c.watch` takes no sustain of its own."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.ongoing(5, DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(), c.cha_mod)
    if not c.last:
        return
    hold = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    c.aura(1, until=When.SUSTAIN, sustain=MINOR)

    def lash(ev: DamageApplied) -> None:
        if ev.target != c.me or hold is None or hold.ended:
            return
        for foe in c.within(1, side="enemy"):
            c.flat(5, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(DamageApplied, lash, until=When.ENCOUNTER)


@power(
    "p11118",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p11118(c: Cast) -> None:
    """The second half of the Effect refunds a power point, and there are no
    power points, so that clause is dropped."""
    if c.strike():
        c.damage(c.w(3), c.cha_mod, dtype=DamageType.PSYCHIC)
    for d in (AC, FORT, REF, WILL):
        c.penalty(d, 2, until=When.ENCOUNTER)


@power(
    "p11119",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=FORT),
)
def p11119(c: Cast) -> None:
    """"During this slide" cannot be asked -- a slide reports where it ended,
    not what it passed -- so the swings go to whoever is adjacent at the end."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)
    c.slide(5)
    for ally in _friends(c, 1, of=victim):
        c.grant_attack(ally, on=victim, damage_bonus=c.cha_mod)


@power(
    "p12960",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=FORT),
)
def p12960(c: Cast) -> None:
    """The choice is the target's, so `c.may` is asked of the target. Rerolling
    reads the attack off `c.trigger`, so the event being answered is put there
    first -- this is a watch, not a declared trigger, and nothing else sets it."""
    victim = c.target
    if victim is None:
        return
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(2), c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(2), c.cha_mod, dtype=DamageType.PSYCHIC)

    seen: dict[int, int] = {}

    def gnaw(ev: AttackRolled) -> None:
        if ev.attacker != victim:
            return
        if landed and seen.get(0) == c.world.round:
            return
        seen[0] = c.world.round
        if c.may("take 10 psychic damage", who=victim):
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)
        elif landed:
            c.trigger = ev
            c.reroll_attack(keep="worst")

    c.watch(
        AttackRolled,
        gnaw,
        on=victim,
        until=When.SAVE_ENDS if landed else When.EONT,
        once=not landed,
    )


@power(
    "p12961",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p12961(c: Cast) -> None:
    """The reward runs on the burn's own clock, which is the later of the two
    the printed line names."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    c.ongoing(5, DamageType.PSYCHIC)

    def reward(ev: Hit) -> None:
        if ev.target != victim or ev.attacker not in c.allies():
            return
        if c.may("gain temporary hit points rather than a saving throw", who=ev.attacker):
            c.temp_hp(c.cha_mod, on=ev.attacker)
        else:
            c.save(on=ev.attacker, bonus=4)

    c.watch(Hit, reward, on=victim, until=When.SAVE_ENDS)


@power(
    "p12962",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p12962(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.teleport(5, who=victim)

    def paid(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.temp_hp(c.cha_mod, on=ev.attacker)

    c.watch(Hit, paid, until=When.EOT)
    for ally in _friends(c, 1, of=victim)[:2]:
        c.grant_attack(ally, on=victim)


@power(
    "p12963",
    level=9,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12963(c: Cast) -> None:
    if c.first:
        c.shift(1)
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    if not c.last:
        return
    for ally in _friends(c, 1):
        if c.may("run rather than shift", who=ally):
            c.move(c.speed_of(ally), who=ally)
        else:
            c.shift(1, who=ally)
