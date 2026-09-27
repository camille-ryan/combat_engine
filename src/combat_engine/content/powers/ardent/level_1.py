"""Ardent, level 1.

Every at-will here prints an Augment 1 and an Augment 2 line, bought with
power points through `augment`. A clause that rewrites the **header** -- the
burst two of these turn into -- cannot be written in a body, because targets
are picked before the body runs; those are named per row and recorded in
`docs/blocked.json`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
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
    Condition,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Position,
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

    `side="ally"` leaves the caster out, which is "one ally"; `mine=True`
    is the half of the fork printing "you or one ally", and `"team"` is the
    same pool with the caster in it.
    """
    return c.within(radius, of=of, side="team" if mine else "ally")


def _pick(c: Cast, pool: list[int], prompt: str) -> int | None:
    return c.choose(sorted(pool), prompt) if pool else None


def _vs_opportunity(ctx: dict[str, Any]) -> bool:
    """"To opportunity attack rolls and damage rolls". Both contexts carry the
    flag, which is what lets one predicate gate both halves."""
    return bool(ctx.get("opportunity"))


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
    """Augment 1 pulls a *dying* ally back instead of handing out temporary
    hit points, so with nobody down it heals nobody -- that is the clause, not
    a hole. Augment 2 is 2[W] and a healing surge, whosever it is."""
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    if spent == 2:
        who = _pick(c, _friends(c, 5, mine=True), "who spends a healing surge")
        if who is not None and c.may("spend a healing surge", who=who):
            c.surge(on=who)
    elif spent == 1:
        down = [a for a in _friends(c, 5) if c.is_(Condition.DYING, on=a)]
        ally = _pick(c, down, "which dying ally is pulled back")
        if ally is not None:
            c.heal(c.cha_mod, on=ally)
    else:
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
    """Augment 2 is 2[W] and a save for everybody within 5.

    Augment 1 is not offered: its bonus applies only when the save is against
    a charm or a fear effect, and an `Effect` carries a label and no keywords
    -- `c.save(against=)` matches the label by substring, which for every one
    of these is the ref of the row that laid it. The gate would be false for
    every charm in the game."""
    spent = augment(c, 2)
    if not c.strike():
        return
    c.damage(c.w(2) if spent else c.w(), c.cha_mod)
    if spent:
        for who in _friends(c, 5, mine=True):
            c.save(on=who)
        return
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
    """Augment 1 swaps the +1 on everything for a Wisdom-sized bonus to Will
    alone; Augment 2 is 2[W] and +2 to every ally within 5."""
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    if spent == 2:
        for ally in _friends(c, 5):
            for d in DEFENCES:
                c.bonus(d, 2, on=ally, until=When.EONT, kind="power")
        return
    ally = _pick(c, _friends(c, 5), "who is shielded")
    if ally is None:
        return
    if spent:
        c.bonus(WILL, c.wis_mod, on=ally, until=When.EONT, kind="power")
    else:
        for d in DEFENCES:
            c.bonus(d, 1, on=ally, until=When.EONT, kind="power")


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
    """Augment 1 narrows the penalty to Will and sizes it off Constitution.
    Augment 2 makes the row a close burst and is left out."""
    spent = augment(c, 1)
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        if spent:
            c.penalty(WILL, 1 + c.con_mod, until=When.EONT)
        else:
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
    it landed. Augment 1 narrows the vulnerability to psychic and sizes it off
    Charisma. Augment 2 takes the swing from anyone within 5 and shifts them
    in first: the printed shift names its destination rather than a distance,
    so it is allowed the ally's speed to get there."""
    spent = augment(c)
    victim = c.target
    ally = _pick(c, _friends(c, 5 if spent == 2 else 1), "who swings")
    if victim is None or ally is None:
        return
    if spent == 2:
        beside = c.world.get(victim, Position)
        if beside is not None:
            near = spread({beside.square}, 1)
            reach = c.world.reachable_squares(ally, c.speed_of(ally))
            spots = sorted(sq for sq in reach if sq in near)
            if spots:
                c.shift(c.speed_of(ally), who=ally, to=spots[0])

    def opening(ev: Hit) -> None:
        if ev.attacker != ally or ev.target != victim:
            return
        if spent == 1:
            c.vulnerable(1 + c.cha_mod, DamageType.PSYCHIC, on=victim, until=When.EONT)
        elif spent == 2:
            c.vulnerable(1 + c.cha_mod, on=victim, until=When.EONT)
        else:
            c.vulnerable(2, on=victim, until=When.EONT)

    c.watch(Hit, opening, until=When.EOT, once=True)
    c.grant_attack(ally, on=victim, damage_bonus=c.roll("1d8") if spent == 2 else 0)


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
                when=lambda _ctx, a=ally: c.adjacent(to=a), kind="power")
            if c.con_mod:
                c.bonus(
                    "damage", c.con_mod, on=ally, until=When.EONT,
                    when=lambda _ctx, a=ally: c.adjacent(to=a), kind="power")

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
    """Augment 1 hands an ally a save each time the target saves -- read off
    `SavingThrow.saved`, which is the only place a successful save is visible.
    Augment 2 is 2[W] and charges *every* hit rather than the next one, which
    is the same watch without the latch."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)

    def punish(ev: Hit) -> None:
        if ev.target == victim:
            c.flat(c.con_mod, on=victim)

    def armed(ev: DamageRolled) -> None:
        if ev.source == victim:
            c.watch(Hit, punish, until=When.EONT, once=spent != 2)

    c.watch(DamageRolled, armed, until=When.SONT, once=True)
    if spent != 1:
        return

    def relieved(ev: SavingThrow) -> None:
        if ev.actor != victim or not ev.saved:
            return
        who = _pick(c, _friends(c, 5), "who else shakes something off")
        if who is not None:
            c.save(on=who, bonus=c.con_mod)

    c.watch(SavingThrow, relieved, until=When.SONT)


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
    """Neither augment is written. Augment 1 strips concealment *and*
    invisibility: `c.no_cover` says the first, and the second is a
    `HIDDEN_FROM` relation that only `c.see_invisible` answers -- and that
    sits on whoever is looking, not on the creature being looked at, so half
    the clause has no subject. Augment 2 hands an ally a reroll from inside a
    watcher, and `c.reroll_attack` reads the attack off `c.trigger`, which a
    watcher does not have."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    pool = set(_friends(c, 1)) | set(_friends(c, 1, of=victim))
    ally = _pick(c, list(pool), "who gains the opening")
    if ally is not None:
        c.bonus(
            "attack", 2, on=ally, until=When.SONT,
            when=lambda ctx: ctx.get("target") == victim, kind="power")


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
    """Augment 1 adds -2 to the target's opportunity attack and damage rolls;
    both contexts carry `opportunity`, so both halves are a gate rather than
    an approximation. Augment 2 is a close burst and is left out."""
    spent = augment(c, 1)
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.slowed(until=When.EONT)
        if spent:
            c.penalty("attack", 2, until=When.EONT, when=_vs_opportunity)
            c.penalty("damage", 2, until=When.EONT, when=_vs_opportunity)


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
    hold = c.grants_advantage(until=When.SAVE_ENDS, to="team")
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
            when=lambda _ctx, a=ally: live(a), kind="power")
        c.bonus(
            "damage", 2, on=ally, until=When.ENCOUNTER,
            when=lambda _ctx, a=ally: live(a), kind="power")


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
    Augment 1 adds -2 on any attack that includes you as a target, gated on
    the attack context's `target`. Augment 2 is 2[W] and pays somebody a shift
    each time the target moves."""
    spent = augment(c)
    me = c.me
    victim = c.target
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
        c.rooted(until=When.EONT)
        if spent == 1:
            c.penalty(
                "attack", 2, until=When.EONT,
                when=lambda ctx: ctx.get("target") == me,
            )
        elif spent == 2 and victim is not None:

            def followed(ev: MoveEnd) -> None:
                if ev.actor != victim:
                    return
                who = _pick(c, _friends(c, 5, mine=True), "who slips a square")
                if who is not None:
                    c.shift(1, who=who)

            c.watch(MoveEnd, followed, until=When.EONT, on=victim, label=c.ref)
    if c.first:
        c.note(f"{c.ref}: telepathic contact with the target out to 5 squares")
