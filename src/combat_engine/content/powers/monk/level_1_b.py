"""Monk, level 1 (second half).

Same shape as `level_1.py`: one id, two printed stat blocks. Only the
attack half is here -- the move half costs its own action and lives in
`second_card_1.py` under its own ref.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    DEX,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Effect,
    Keyword,
    Melee,
    UpTo,
    When,
    by_melee,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    Hit,
    Miss,
    SavingThrow,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)

IMPLEMENT = [Keyword.IMPLEMENT]


def _ends_with(c: Cast, posture: Effect, held: Effect | None) -> None:
    """Tie a held modifier to a stance, so taking another stance drops it."""
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p16133",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.FIRE],
    attack=Attack(DEX, vs=REF),
)
def p16133(c: Cast) -> None:
    """The extra fire damage is typed, which a `"damage"` modifier cannot
    be, so it is a watch on the monk's own melee hits."""
    if c.strike():
        c.damage("1d8", c.dex_mod)

        def burn(ev: Hit) -> None:
            if ev.attacker == c.me and by_melee(c.world, c.me, ev):
                c.flat(c.cha_mod, dtype=DamageType.FIRE, on=ev.target)

        c.watch(Hit, burn, until=When.EONT)


@power(
    "p16135",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16135(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.dex_mod)
        if c.may("slide the target 1 square", who=c.me):
            c.slide(1)


@power(
    "p16137",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16137(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.dex_mod)
        c.push(max(0, c.str_mod // 2))


@power(
    "p16139",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16139(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.dex_mod)
    if c.may("slide the target 1 square", who=c.me):
        c.slide(1)


@power(
    "p16143",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.ZONE],
    attack=Attack(DEX, vs=REF),
)
def p16143(c: Cast) -> None:
    """The flight is printed *before* the attack, so it runs first even
    though the blast's targets were picked from where the monk started.
    Moving the zone as a move action is not written -- a zone has no way to
    be walked around once it is down."""
    if c.first:
        c.mode("fly", c.speed_of(), until=When.EOT)
        foes = c.enemies()
        if foes:
            quarry = c.choose(foes, "fly adjacent to an enemy")
            if quarry is not None:
                c.run_at(quarry)
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.dex_mod)
    if not c.last:
        return
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    herded: dict[int, int] = {}

    def nudge(ev: ZoneEntered) -> None:
        if ev.zone != zone or ev.actor == c.me:
            return
        if herded.get(0) == c.world.round:
            return
        herded[0] = c.world.round
        c.slide(2, on=ev.actor)

    c.watch(ZoneEntered, nudge, until=When.SUSTAIN)


@power(
    "p16144",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.STANCE],
    attack=Attack(DEX, vs=REF),
)
def p16144(c: Cast) -> None:
    """"Combat advantage against any enemy adjacent to an ally" is a
    standing question, so it is answered again at the top of each of the
    monk's turns rather than once when the stance is taken."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
    else:
        c.half_damage("2d6", c.dex_mod)
    if not c.last:
        return
    posture = c.stance()

    def flank() -> None:
        for foe in c.enemies():
            if any(c.adjacent_to(foe, mate) for mate in c.allies()):
                c.grants_advantage(on=foe, to="me", until=When.EOT)

    def refresh(ev: TurnStart) -> None:
        if ev.actor == c.me and not ev.ghost:
            flank()

    def trade(ev: Miss) -> None:
        if ev.target == c.me and c.adjacent(ev.attacker):
            c.swap(ev.attacker)

    flank()
    _ends_with(c, posture, c.watch(TurnStart, refresh, until=When.ENCOUNTER))
    _ends_with(c, posture, c.watch(Miss, trade, until=When.ENCOUNTER))


@power(
    "p16145",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*IMPLEMENT, Keyword.FIRE],
    attack=Attack(DEX, vs=REF),
)
def p16145(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.dex_mod)
        burn = c.ongoing(5, DamageType.FIRE, until=When.SAVE_ENDS)
        victim = c.target

        def failed(ev: SavingThrow) -> None:
            if ev.actor == victim and not ev.saved:
                c.slide(1, on=victim)

        nudge = c.watch(SavingThrow, failed, until=When.ENCOUNTER)
        if burn is not None:
            burn.on_end.append(lambda: c.world.effects.end(nudge, "burn ended"))
    if not c.last:
        return
    bitten: dict[int, int] = {}

    def sear(who: int) -> None:
        if who not in c.enemies() or bitten.get(who) == c.world.round:
            return
        bitten[who] = c.world.round
        c.flat(c.dex_mod, dtype=DamageType.FIRE, on=who)

    def on_close(ev: AdjacencyGained) -> None:
        if ev.actor == c.me and ev.mover not in (0, c.me):
            sear(ev.other)

    def on_end(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor != c.me and c.distance(ev.actor) <= 1:
            sear(ev.actor)

    c.watch(AdjacencyGained, on_close, until=When.EONT)
    c.watch(TurnEnd, on_end, until=When.EONT)


@power(
    "p7449",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7449(c: Cast) -> None:
    """"Has made an opportunity attack against you this turn" is history,
    not state, so it is read back off the log from the last turn boundary."""
    log = c.world.bus.log
    start = 0
    for i in range(len(log) - 1, -1, -1):
        if isinstance(log[i], TurnStart):
            start = i
            break
    owed = any(
        getattr(ev, "attacker", None) == c.target
        and getattr(ev, "target", None) == c.me
        and getattr(ev, "opportunity", False)
        for ev in log[start:]
    )
    if c.strike():
        c.damage("1d10", c.dex_mod)
        if owed:
            c.flat(c.wis_mod)


@power(
    "p7450",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p7450(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.dex_mod)
        c.prone()


@power(
    "p7452",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7452(c: Cast) -> None:
    if c.can_see() and c.strike():
        c.damage("1d8", c.dex_mod)


@power(
    "p7453",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=WILL),
)
def p7453(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.dex_mod)
        c.slide(1)
        victims = [f for f in c.enemies() if f != c.target]
        if victims:
            mark = c.choose(victims, "whom the target swings at")
            if mark is not None:
                c.grant_attack(c.target, on=mark, attack_bonus=c.wis_mod)


@power(
    "p7454",
    level=1,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7454(c: Cast) -> None:
    """Full hit points is read before the swing. The extra die is rolled
    rather than added inside the crit branch, which would max it."""
    untouched = not c.wounded()
    if c.strike():
        c.damage("2d10", c.dex_mod)
        if untouched:
            c.flat(c.roll("1d10"))


@power(
    "p7455",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*IMPLEMENT, Keyword.FORCE, Keyword.STANCE],
    attack=Attack(DEX, vs=REF),
)
def p7455(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.dex_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("3d8", c.dex_mod, dtype=DamageType.FORCE)
    if not c.last:
        return
    posture = c.stance()
    _ends_with(c, posture, c.bonus("reach", 1, on=c.me, until=When.ENCOUNTER))


@power(
    "p7456",
    level=1,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p7456(c: Cast) -> None:
    """The shift is printed before the attack, and each enemy the monk
    brushes past is slid once -- gathered from the move itself."""
    if c.first:
        nudged: list[int] = []

        def brush(ev: AdjacencyGained) -> None:
            if ev.actor != c.me or ev.mover != c.me:
                return
            if ev.other in c.enemies() and ev.other not in nudged:
                nudged.append(ev.other)
                c.slide(1, on=ev.other)

        sub = c.world.bus.on(AdjacencyGained, brush)
        try:
            c.shift(c.speed_of())
        finally:
            c.world.bus.off(sub)
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d10", c.dex_mod)
        c.slowed(until=When.EONT)


@power(
    "p7535",
    level=1,
    cls="monk",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p7535(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.dex_mod)
        c.push(1)
