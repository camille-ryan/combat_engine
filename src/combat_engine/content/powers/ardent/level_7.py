"""Ardent, level 7.

All at-will and all augmentable; each row buys its augment with `augment` and
names in its docstring whatever is left out. Two printed rows are absent: one
whose rider is "rolls damage twice and uses the lower roll", and one whose
Effect is "does not benefit from partial cover or partial concealment".
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    EACH_ENEMY,
    FORT,
    MOVE,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackRolled,
    Augment,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
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
    "p10287",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CHA, vs=AC),
    augments=(
        Augment(1),
        Augment(2, reach=CloseBurst(1), target=EACH_ENEMY),
    ),
    dropped=("c.bonus_in(zone)",),
)
def p10287(c: Cast) -> None:
    """"Against the target's attacks" is a gate on the defence modifier, which
    `query.defence` is handed the attack context for. Augment 1 widens the
    bonus to every defence.

    Augment 2 is a close burst against each enemy, which is a target line
    and so is declared rather than said in the body. Its hit hands an
    adjacent ally an opportunity swing at the creature. Its zone is laid --
    the squares are real and block nothing -- but the *bonus inside it* is
    the dropped clause: a modifier scoped to a footprint has no method,
    which is the same hold `p13318`'s Augment 1 names from the other side.
    The guard against the target's own attacks is not printed under
    Augment 2, so it is gated on the cheaper form exactly."""
    spent = augment(c, 1, 2)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    if spent == 2:
        helper = _pick(c, _friends(c, 1, of=victim), "who takes the opening")
        if helper is not None:
            c.grant_attack(helper, on=victim)
        if c.first:
            c.zone(c.area(), until=When.EONT, label="p10287")
        return
    ally = _pick(c, _friends(c, 1), "who shares the guard")

    def theirs(ctx: dict) -> bool:
        return ctx.get("attacker") == victim

    guarded = (AC, FORT, REF, WILL) if spent else (AC,)
    for who in (c.me, ally):
        if who is not None:
            for d in guarded:
                c.bonus(d, 2, on=who, until=When.EONT, when=theirs, kind="power")


@power(
    "p10288",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
    augments=(
        Augment(1),
        Augment(
            2,
            reach=CloseBurst(1),
            target=EACH_ENEMY,
            attack=Attack(CHA, vs=AC),
        ),
    ),
)
def p10288(c: Cast) -> None:
    """No attack line of its own -- the ally swings. Augment 1 pays +3 damage
    if that ally is the one marking the target, which `c.marked(by=)` answers.

    Augment 2 gives the row **an attack line the base card has not got**, on
    top of turning it into a close burst, so both are declared in the header
    where an attack line lives. `attack=` on the augment is what makes
    `c.strike` have something to roll; written in the body it would have to
    invent the line, which is the difference between a card and a guess."""
    spent = augment(c, 1, 2)
    victim = c.target
    if victim is None:
        return
    if spent == 2:
        if not c.strike():
            return
        c.damage(c.w(), c.cha_mod)
        helper = _pick(c, _friends(c, 1, of=victim), "who takes the opening")
        if helper is not None:
            c.grant_attack(helper, on=victim)
        return
    ally = _pick(c, _friends(c, 1), "who swings")
    if ally is None:
        return
    extra = 3 if spent and c.marked(on=victim, by=ally) else 0

    def landed(ev: Hit) -> None:
        if ev.attacker == ally and ev.target == victim:
            c.shift(1)
            c.shift(1, who=ally)

    c.watch(Hit, landed, until=When.EOT, once=True)
    c.grant_attack(ally, on=victim, damage_bonus=extra)


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
    augments=(
        Augment(1, charges=True),
        Augment(2),
    ),
)
def p11104(c: Cast) -> None:
    """Augment 2 sends one or two allies charging something else, paid a
    Constitution-sized damage bonus for it.

    Augment 1 makes the row itself a charge, and whether a row charges is a
    header field -- read *before* the body, to decide whether the target is
    in reach at all. So it is declared as one: `charges=True` on the
    augment, which is measured only when that form is the one being used. A
    body could not have said it. The shift is the body's half, and it
    happens before the run, which is the order the card prints.""" 
    spent = augment(c, 1, 2)
    if spent == 1 and c.first and c.target is not None:
        c.shift(1)
        c.run_at(c.target)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    if not c.first:
        return
    if not spent:
        for ally in _friends(c, 1):
            c.bonus("attack", 1, on=ally, until=When.SONT, kind="power")
        return
    quarry = [f for f in c.enemies() if f != victim]
    for ally in _friends(c, 10)[:2]:
        prey = _pick(c, quarry, "whom that ally charges")
        if prey is not None:
            c.bonus("damage", c.con_mod, on=ally, until=When.EOT, kind="power")
            c.charge_at(prey, who=ally)


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
    """Augment 1 pays a healing surge instead, and only for a hit on the
    target's Will -- which defence was attacked is on `AttackRolled` and
    nowhere else, so the surge is paid from there rather than from `Hit`.
    Augment 2 is 2[W] and pays every ally who hits, not just the next."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)

    def mend(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            if spent == 2:
                if c.may("spend a healing surge", who=ev.attacker):
                    c.surge(on=ev.attacker)
            else:
                c.heal(c.con_mod, on=ev.attacker)

    def mend_on_will(ev: AttackRolled) -> None:
        if ev.target != victim or ev.vs is not WILL or ev.total < ev.defence:
            return
        if ev.attacker in c.allies() and c.may("spend a healing surge", who=ev.attacker):
            c.surge(on=ev.attacker)

    if spent == 1:
        c.watch(AttackRolled, mend_on_will, until=When.SONT)
    else:
        c.watch(Hit, mend, until=When.EONT if spent else When.SONT, once=spent != 2)


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
    """The damage line carries no weapon dice at all -- just the modifier,
    until Augment 2 adds 1[W] and a second swing.

    Augment 1 is not offered: "enemies provoke opportunity attacks from the
    target, and it must make those attacks" needs both a provoking rule
    written from the target's own side and a compulsion to take the window.
    `c.provoke` opens one window for one named attacker and nothing obliges
    anybody to answer it."""
    spent = augment(c, 2)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w() if spent else 0, c.cha_mod, dtype=DamageType.PSYCHIC)
    pool = [x for x in c.within(1, of=victim) if x != victim]
    for _ in range(2 if spent else 1):
        who = _pick(c, pool, "whom it turns on")
        if who is None:
            return
        c.grant_attack(victim, on=who)
        pool = [x for x in pool if x != who]


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
    once, not once per target. Augment 1 lengthens that shift to your Wisdom
    modifier. Augment 2 is 2[W] and pays every ally who *starts* a turn near
    you a speed bonus and a two-square shift, which is why it is a watch on
    `TurnStart` rather than something handed out now."""
    spent = augment(c)
    if c.first:
        ally = _pick(c, _friends(c, 1), "who shifts first")
        if ally is not None:
            c.shift(c.wis_mod if spent == 1 else 1, who=ally)
        if spent == 2:

            def quickened(ev: TurnStart) -> None:
                if ev.actor == c.me or ev.actor not in _friends(c, 5):
                    return
                c.bonus("speed", 2, on=ev.actor, until=When.EOT, kind="power")
                c.shift_as(MOVE, 2, on=ev.actor, until=When.EOT)

            c.watch(TurnStart, quickened, until=When.EONT, label=c.ref)
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)


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
    """Augment 1 adds psychic damage the first time the target hits an ally;
    Augment 2 is 2[W] and opens the target up to whoever stands beside you."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.cha_mod)
    c.mark(until=When.EONT)
    if spent == 1 and victim is not None:

        def stung(ev: Hit) -> None:
            if ev.attacker == victim and ev.target in c.allies():
                c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=victim)

        c.watch(Hit, stung, until=When.EONT, once=True, label=c.ref)
    elif spent == 2 and victim is not None:
        for ally in c.within(1, side="ally"):
            if ally != c.me:
                c.grants_advantage(on=victim, to=ally, until=When.EONT)


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
    """Augment 1 pays the quickened ally hit points if its charge lands --
    `Hit` carries `charge` as a plain attribute, so the clause is that and
    not "any attack". Augment 2 sends an ally charging now instead, with the
    attack bonus laid as a one-shot modifier because `c.charge_at` takes no
    bonus of its own."""
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    ally = _pick(c, _friends(c, 5), "who quickens")
    if ally is None:
        return
    if spent == 2:
        prey = _pick(c, [f for f in c.enemies() if f != c.target], "whom it charges")
        if prey is None:
            return
        c.bonus("attack", c.con_mod, on=ally, until=When.EOT, kind="power", once=True)

        def rewarded(ev: Hit) -> None:
            if ev.attacker != ally or not getattr(ev, "charge", False):
                return
            for d in (AC, FORT, REF, WILL):
                c.bonus(d, 2, on=ally, until=When.SONT, kind="power")
            if c.may("spend a healing surge", who=ally):
                c.surge(on=ally)

        c.watch(Hit, rewarded, until=When.EOT, once=True, label=c.ref)
        c.charge_at(prey, who=ally)
        return
    c.bonus("speed", 2, on=ally, until=When.EONT, kind="power")
    if spent == 1:

        def mended(ev: Hit) -> None:
            if ev.attacker == ally and getattr(ev, "charge", False):
                c.heal(c.con_mod, on=ally)

        c.watch(Hit, mended, until=When.EONT, once=True, label=c.ref)
