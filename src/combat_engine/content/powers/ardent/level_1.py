"""Ardent, level 1.

Every at-will here prints an Augment 1 and an Augment 2 line. The engine has
no power points, so what is written is the **base form** -- the effect printed
before the first Augment line, which is a complete at-will on its own. Each
row's docstring names the augment clauses that were dropped.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
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
    Cast,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    SavingThrow,
    TurnStart,
    When,
    by_melee,
    power,
    spread,
)

PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)


def _friends(c: Cast, radius: int, *, of: int | None = None, mine: bool = False) -> list[int]:
    """Allies within `radius` of `of` (the caster by default).

    `c.within(side="ally")` counts the caster as one of his own allies, which
    is right for "you or one ally" and wrong for "one ally".
    """
    return [a for a in c.within(radius, of=of, side="ally") if mine or a != c.me]


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


@power(
    "p10274",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=AC),
)
def p10274(c: Cast) -> None:
    """Dropped augments: Augment 1 heals a dying ally within 5 for Charisma
    modifier instead; Augment 2 is 2[W] and lets you or an ally spend a surge."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        ally = _pick(c, _friends(c, 5), "who gains temporary hit points")
        if ally is not None:
            c.temp_hp(c.level // 2 + c.cha_mod, on=ally)


@power(
    "p10275",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10275(c: Cast) -> None:
    """Dropped augments: Augment 1 adds a Wisdom-modifier bonus when the save is
    against charm or fear; Augment 2 is 2[W] and every ally within 5 saves."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        who = _pick(c, _friends(c, 5, mine=True), "who makes a saving throw")
        if who is not None:
            c.save(on=who)


@power(
    "p10276",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p10276(c: Cast) -> None:
    """Dropped augments: Augment 1 swaps the +1 for a Wisdom-modifier bonus to
    Will alone; Augment 2 is 2[W] and +2 to every ally within 5."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        ally = _pick(c, _friends(c, 5), "who is shielded")
        if ally is not None:
            for d in DEFENCES:
                c.bonus(d, 1, on=ally, until=When.EONT)


@power(
    "p10277",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p10277(c: Cast) -> None:
    """The hold is the watch itself, owned by the target so the target rolls the
    save. The swing is offered after the trigger's own attack has resolved,
    which is what the `AFTER` window on `AttackDeclared` is."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.cha_mod)

    def riposte(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        ally = _pick(c, _friends(c, 1, of=victim), "who strikes back")
        if ally is not None:
            c.grant_attack(ally, on=victim)

    c.watch(AttackDeclared, riposte, on=victim, until=When.SAVE_ENDS)


@power(
    "p10278",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.WEAPON,
        Keyword.TELEPORTATION,
        Keyword.ZONE,
    ],
    attack=Attack(CHA, vs=AC),
)
def p10278(c: Cast) -> None:
    """The last printed sentence -- "once per round as a free action you can
    teleport a creature within the zone 3 squares" -- is an untriggered free
    action with no event behind it, so it is dropped."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.cha_mod)
    else:
        c.half_damage(c.w(), c.cha_mod)

    vacated = c.there
    c.teleport(c.wis_mod, who=victim)
    ally = _pick(c, _friends(c, 1, of=victim), "who strikes the vacated flank")
    if ally is not None:
        c.grant_attack(ally, on=victim)

    c.zone({vacated}, until=When.EONT)
    pull_range = spread({vacated}, 3)

    def tug(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(pull_range):
            c.pull(1, on=ev.actor, anchor=vacated)

    c.watch(TurnStart, tug, until=When.EONT)


@power(
    "p11061",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CHA, vs=AC),
)
def p11061(c: Cast) -> None:
    """Dropped augments: Augment 1 narrows the penalty to Will and sizes it off
    Constitution; Augment 2 makes it a burst."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        for d in DEFENCES:
            c.penalty(d, 2, until=When.EONT)


@power(
    "p11062",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
)
def p11062(c: Cast) -> None:
    """No attack line of its own -- the ally swings. The vulnerability hangs off
    a watch because `c.grant_attack` reports that the swing happened, not that
    it landed. Dropped augments: Augment 1 makes it psychic and Charisma-sized;
    Augment 2 lets the ally shift in first and adds 1d8."""
    victim = c.target
    ally = _pick(c, _friends(c, 1), "who swings")
    if victim is None or ally is None:
        return

    def opening(ev: Hit) -> None:
        if ev.attacker == ally and ev.target == victim:
            c.vulnerable(2, on=victim, until=When.EONT)

    c.watch(Hit, opening, until=When.EOT, once=True)
    c.grant_attack(ally, on=victim)


@power(
    "p11063",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p11063(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)

    def reward(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in (c.me, *c.allies()):
            c.shift(1, who=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER)


@power(
    "p11064",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p11064(c: Cast) -> None:
    """"While adjacent to you" is a gate on the modifier rather than an aura,
    since an aura cannot carry a bonus. `c.bonus` takes no sustain cost, so the
    hold carries it and re-lays the bonuses each time it is sustained."""
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    if not c.last:
        return

    def buff() -> None:
        for ally in c.allies():
            c.bonus(
                "attack", 1, on=ally, until=When.EONT,
                when=lambda _ctx, a=ally: c.adjacent(to=a),
            )
            if c.con_mod:
                c.bonus(
                    "damage", c.con_mod, on=ally, until=When.EONT,
                    when=lambda _ctx, a=ally: c.adjacent(to=a),
                )

    buff()
    hold = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    c.on_sustain(hold, buff)


@power(
    "p11065",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p11065(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.penalty("attack", c.wis_mod, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.cha_mod)
        if c.wis_mod // 2:
            c.penalty("attack", c.wis_mod // 2, until=When.SAVE_ENDS)

    def console(ev: Miss) -> None:
        if ev.attacker != victim or not by_melee(c.world, c.me, ev):
            return
        who = _pick(c, _friends(c, 1, mine=True), "who gains temporary hit points")
        if who is not None:
            c.temp_hp(5 + c.level // 2, on=who)

    c.watch(Miss, console, until=When.ENCOUNTER)


@power(
    "p12933",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12933(c: Cast) -> None:
    """Dropped augments: Augment 1 hands an ally a save when the target saves;
    Augment 2 is 2[W] and charges every hit rather than the next one."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)

    def punish(ev: Hit) -> None:
        if ev.target == victim:
            c.flat(c.con_mod, on=victim)

    def armed(ev: DamageRolled) -> None:
        if ev.source == victim:
            c.watch(Hit, punish, until=When.EONT, once=True)

    c.watch(DamageRolled, armed, until=When.SONT, once=True)


@power(
    "p12934",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12934(c: Cast) -> None:
    """Dropped augments: Augment 1 also strips concealment and invisibility;
    Augment 2 hands the next ally to miss a reroll instead."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    pool = set(_friends(c, 1)) | set(_friends(c, 1, of=victim))
    ally = _pick(c, list(pool), "who gains the opening")
    if ally is not None:
        c.bonus(
            "attack", 2, on=ally, until=When.SONT,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "p12935",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12935(c: Cast) -> None:
    """Dropped augments: Augment 1 adds -2 to opportunity attack and damage
    rolls; Augment 2 is a burst with a standing damage penalty and a slow."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.slowed(until=When.EONT)


@power(
    "p12936",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p12936(c: Cast) -> None:
    """"Whenever the target takes a move action" is `ActionSpent`, which is the
    only event that announces a plain walk."""
    from combat_engine.engine.events import ActionSpent
    from combat_engine.engine.types import ActionType as _A

    victim = c.target
    if victim is None:
        return

    def nudge() -> None:
        who = _pick(c, _friends(c, 20, mine=True), "who shifts")
        if who is not None and c.can_see(who):
            c.shift(2, who=who)

    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    nudge()

    def on_move(ev: ActionSpent) -> None:
        if ev.actor == victim and ev.cost is _A.MOVE:
            nudge()

    c.watch(ActionSpent, on_move, on=victim, until=When.SAVE_ENDS)


@power(
    "p12937",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.WEAPON,
        Keyword.PSYCHIC,
        Keyword.ILLUSION,
    ],
    attack=Attack(CHA, vs=AC),
)
def p12937(c: Cast) -> None:
    """Two of the four printed clauses are dropped: nothing bars a creature from
    *gaining* combat advantage, and `c.cannot_be_flanked` is about being flanked
    rather than flanking. The aftereffect rides on the hold's `on_end`."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.cha_mod)
    hold = c.grants_advantage(until=When.SAVE_ENDS, to="allies")
    if hold is not None:
        hold.on_end.append(lambda: c.flat(10, dtype=DamageType.PSYCHIC, on=victim))


@power(
    "p12938",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=AC),
)
def p12938(c: Cast) -> None:
    """The allies' bonuses run to the end of the encounter but read the hold,
    because a save-ends modifier parked on an ally would be the *ally's* save."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(1)
    else:
        c.half_damage(c.w(2), c.cha_mod, dtype=DamageType.PSYCHIC)
    hold = c.effect(c.ref, until=When.SAVE_ENDS)

    def live(ally: int) -> bool:
        return hold is not None and not hold.ended and c.adjacent_to(victim, ally)

    for ally in c.allies():
        c.bonus(
            "attack", 1, on=ally, until=When.ENCOUNTER,
            when=lambda _ctx, a=ally: live(a),
        )
        c.bonus(
            "damage", 2, on=ally, until=When.ENCOUNTER,
            when=lambda _ctx, a=ally: live(a),
        )


@power(
    "p12939",
    level=1,
    cls="ardent",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=AC),
)
def p12939(c: Cast) -> None:
    """"Your Wisdom or Constitution modifier" is a standing choice the character
    made once; the better of the two is taken."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(), c.cha_mod, dtype=DamageType.PSYCHIC)
    c.ongoing(5, DamageType.PSYCHIC)
    amount = max(c.wis_mod, c.con_mod)

    def payout(ev: SavingThrow) -> None:
        if ev.actor != victim or amount <= 0:
            return
        foe = _pick(c, c.enemies(), "who takes the backlash")
        if foe is not None:
            c.flat(amount, dtype=DamageType.PSYCHIC, on=foe)
        friend = _pick(c, _friends(c, 20, mine=True), "who is mended")
        if friend is not None:
            c.heal(amount, on=friend)

    c.watch(SavingThrow, payout, on=victim, until=When.SAVE_ENDS)


@power(
    "p13780",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p13780(c: Cast) -> None:
    """"Cannot shift" is `c.rooted`, not `c.immobilized`: the target still walks.
    Dropped augments: Augment 1 adds -2 on attacks including you; Augment 2 is
    2[W] and pays a shift whenever the target moves."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.rooted(until=When.EONT)
    if c.first:
        c.note(f"{c.ref}: telepathic contact with the target out to 5 squares")
