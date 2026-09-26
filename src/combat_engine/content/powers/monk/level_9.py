"""Monk, level 9: the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_CREATURE,
    FORT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Defense,
    Health,
    Keyword,
    Melee,
    Trigger,
    UpTo,
    When,
    both,
    by_melee,
    get,
    hits_me,
    power,
    query,
)
from combat_engine.engine.events import AttackDeclared, Hit, MoveEnd, TurnStart

IMPLEMENT = [Keyword.IMPLEMENT]


def _swing(c: Cast, vs: Defense, on: int) -> bool:
    """This row's own attack line, rolled against a different defence."""
    line = get(c.ref).attack
    if line is None:
        return False
    bonus = line.bonus_for(c.world, c.me, c.ref, c.branch)
    return bool(c.attack(bonus, vs, on=on).hit)


@power(
    "p11228",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(4),
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11228(c: Cast) -> None:
    """The shift is printed per attack, so it is not guarded by `c.last`."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        c.prone()
    else:
        c.half_damage("2d8", c.dex_mod)
    c.shift(2)


@power(
    "p11229",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11229(c: Cast) -> None:
    """The follow-up attack has no id of its own, and it is a once-only
    interrupt on the target swinging, so it is written into this row as a
    one-shot watch rather than left unreachable."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
    else:
        c.half_damage("2d10", c.dex_mod)
    victim = c.target
    if victim is None:
        return

    def slipped(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.kind_ != "forced":
            c.shift(1)

    c.watch(MoveEnd, slipped, until=When.EONT)
    busy: list[int] = []

    def pounce(ev: AttackDeclared) -> None:
        if busy or ev.attacker != victim:
            return
        busy.append(1)
        try:
            if c.strike(on=victim):
                c.damage("2d10", c.dex_mod, on=victim)
            else:
                c.half_damage("2d10", c.dex_mod, on=victim)
        finally:
            busy.clear()

    c.watch(AttackDeclared, pounce, until=When.ENCOUNTER, once=True)


@power(
    "p13171",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13171(c: Cast) -> None:
    """The finisher is read off hit points after the damage has landed,
    which is what "after this attack is resolved" means."""
    if c.strike():
        c.damage("3d8", c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.dex_mod)
    pool = c.world.get(c.target, Health)
    if pool is None:
        return
    if 0 < pool.hp <= 10:
        c.flat(pool.hp)
    if pool.hp <= 0:
        for foe in c.within(5, side="enemy"):
            c.penalty(
                "attack", 2, on=foe, until=When.SAVE_ENDS,
                when=lambda ctx: ctx.get("target") == c.me,
            )


@power(
    "p13172",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13172(c: Cast) -> None:
    """The flight is printed before the attack and the shift after it."""
    if c.first:
        c.mode("fly", c.speed_of(), until=When.EOT)
        c.move(c.speed_of())
    if c.strike():
        c.damage("3d10", c.dex_mod)
        c.push(5)
    else:
        c.half_damage("3d10", c.dex_mod)
        c.push(2)
    if c.last:
        c.shift(1)


@power(
    "p13173",
    level=9,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*IMPLEMENT, Keyword.FIRE, Keyword.STANCE],
)
def p13173(c: Cast) -> None:
    """The stance's second stat block -- a standard-action attack that ends
    the stance -- has no id of its own in the spec, so only the stance is
    written. The extra fire damage is typed, so it is a watch rather than a
    `"damage"` modifier."""
    posture = c.stance()
    held = c.resist(5, DamageType.FIRE, until=When.ENCOUNTER)

    def scorch(ev: Hit) -> None:
        if ev.attacker == c.me and by_melee(c.world, c.me, ev):
            c.flat(5, dtype=DamageType.FIRE, on=ev.target)

    watcher = c.watch(Hit, scorch, until=When.ENCOUNTER)
    posture.on_end.append(lambda: c.world.effects.end(watcher, "stance ended"))
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p13175",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF, plus=2),
)
def p13175(c: Cast) -> None:
    """The header carries the printed +2, so the repeat is `plus=-4` to
    land on Dexterity -2. The widened crit range goes on before the roll,
    which is the only moment it is read."""
    c.bonus("crit_range", 1, on=c.me, until=When.EOT)
    if c.strike():
        c.damage("2d12", c.dex_mod)
        return
    if c.strike(plus=-4):
        c.damage("2d12", c.dex_mod)
    c.dazed(on=c.me, until=When.SONT)


@power(
    "p15989",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
)
def p15989(c: Cast) -> None:
    """Rests are not modelled, so the printed Requirement is not declared
    and the pact runs to the end of the encounter instead of to the next
    rest."""
    mate = c.target
    if mate is None:
        return

    def point(ev: Hit) -> None:
        if ev.attacker != c.me or ev.target == mate:
            return
        foe = ev.target
        c.bonus(
            "damage", c.str_mod, on=mate, until=When.ENCOUNTER, once=True,
            when=lambda ctx, f=foe: ctx.get("target") == f, kind="power")

    c.watch(Hit, point, until=When.ENCOUNTER)


@power(
    "p16170",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(DEX, vs=REF),
)
def p16170(c: Cast) -> None:
    """The second burst is thrown from wherever the jump ends, so the whole
    power resolves in the first body call and the second ring is found by
    range rather than off the declared target list."""
    if not c.first:
        return
    for foe in c.targets:
        if c.strike(on=foe):
            c.damage("1d8", c.dex_mod, dtype=DamageType.LIGHTNING, on=foe)
        else:
            c.half_damage("1d8", c.dex_mod, dtype=DamageType.LIGHTNING, on=foe)
    c.no_provoke(until=When.EOT)
    c.move(5)
    for other in c.within(1, side="other"):
        if _swing(c, FORT, other):
            c.damage("1d8", c.dex_mod, dtype=DamageType.THUNDER, on=other)
        else:
            c.half_damage("1d8", c.dex_mod, dtype=DamageType.THUNDER, on=other)


@power(
    "p16171",
    level=9,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def p16171(c: Cast) -> None:
    """The form's second stat block -- a standard-action attack usable while
    it holds -- has no id of its own in the spec. The extra saving throw is
    written as one save at the top of the turn; `c.save` cannot be pointed
    at a class of condition, so it takes whichever save-ends effect it
    finds."""
    shape = c.form(until=When.ENCOUNTER, label=c.ref)
    for defence in (AC, FORT, REF, WILL):
        held = c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, kind="power")
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "form ended"))
    rough = c.ignores_difficult(until=When.ENCOUNTER)
    if rough is not None:
        shape.on_end.append(lambda: c.world.effects.end(rough, "form ended"))

    def early(ev: TurnStart) -> None:
        if ev.actor == c.me and not ev.ghost:
            c.save(on=c.me)

    watcher = c.watch(TurnStart, early, until=When.ENCOUNTER)
    shape.on_end.append(lambda: c.world.effects.end(watcher, "form ended"))


@power(
    "p16173",
    level=9,
    cls="monk",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
    trigger="an adjacent enemy hits you with an attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an adjacent enemy hits you"),
)
def p16173(c: Cast) -> None:
    """The secondary burst has no printed size beyond "the burst", which for
    a melee reaction is the square around the monk."""
    victim = c.target
    if c.strike():
        c.damage("1d8", c.dex_mod)
    c.push(5)
    c.prone()
    for other in c.within(1, side="other"):
        if other == victim:
            continue
        if c.strike(on=other):
            c.damage("1d8", c.dex_mod, on=other)
            c.prone(on=other)


@power(
    "p7467",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p7467(c: Cast) -> None:
    """"Fortitude or Reflex" is a choice the header cannot hold two of, so
    the softer of the two is found and rolled against."""
    victim = c.target
    if victim is None:
        return
    softer = query.defence(c.world, victim, FORT) <= query.defence(c.world, victim, REF)
    vs = FORT if softer else REF
    if _swing(c, vs, victim):
        c.ongoing(15 + c.dex_mod, until=When.SAVE_ENDS)
    else:
        c.ongoing(10, until=When.SAVE_ENDS)


@power(
    "p7468",
    level=9,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=[*IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(DEX, vs=REF),
)
def p7468(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.blinded(until=When.EONT)
    else:
        c.half_damage("3d6", c.dex_mod, dtype=DamageType.PSYCHIC)
