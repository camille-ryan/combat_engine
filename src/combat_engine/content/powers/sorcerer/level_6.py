"""Sorcerer, level 6: utility.

**"You grant combat advantage"** names no beneficiary, so it cannot be the
relation on its own -- it is handed out from each attack's `AttackDeclared`
interrupt window, the last moment it can be given and still be read, which
is the arrangement `fighter/level_5_b.py` settled on.

**"+4 to all defences against the triggering attack"** is declared on the
announcement rather than on the landing. An interrupt runs before the roll
is judged, and that is the only window in which raising a defence can change
the attack that provoked it.

Five rows of this level are left out; see the report and `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Event,
    Keyword,
    Trigger,
    When,
    Window,
    World,
    ally_within,
    get,
    hits_me,
    power,
)

from .dice import face_of

ARCANE = [Keyword.ARCANE]

_ALLY_ATTACKS = "an ally within 5 squares makes an attack"
_HIT_BY_ANYTHING = "you are hit by an attack"
_HIT_BY_A_SPLASH = "you are hit by an area or a close attack"


def _splashed_me(world: World, me: int, ev: Event) -> bool:
    """"Hit by an **area or close** attack", read off the row that swung."""
    if not hits_me(world, me, ev):
        return False
    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach.kind in (
        "area_burst", "close_burst", "close_blast",
    )


def _open_to_everyone(c: Cast, *, until: When) -> None:
    """"You grant combat advantage" -- to whoever turns out to swing."""
    me = c.me

    def offer(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me:
            c.grants_advantage(on=me, to=ev.attacker, until=When.EOT)

    c.watch(
        AttackDeclared, offer, until=until, window=Window.BEFORE, on=me,
        label=f"{c.ref} exposed",
    )


@power(
    "p11833",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_ALLY_ATTACKS,
    on=Trigger(AttackDeclared, when=ally_within(5), text=_ALLY_ATTACKS),
)
def p11833(c: Cast) -> None:
    """"Against that target" is a gate on the damage context, which carries
    `target`. The ordering caveat is p11832's: a free action resolves after
    the attack it answers, so the face is read back off the log and only the
    choice is taken blind.
    """
    ev = c.trigger
    swinger = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    low = c.choose(["1-10", "11-20"], f"{c.ref}: which half of the die") == "1-10"
    face = face_of(c, swinger)
    if face is None:
        return
    if not (face <= 10 if low else face >= 11):
        return
    c.bonus(
        "damage", 5 + c.cha_mod, on=c.me, until=When.EONT,
        when=lambda ctx: victim is None or ctx.get("target") == victim,
    )


@power(
    "p16242",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, within=10),
    target=NO_TARGET,
    keywords=ARCANE,
)
def p16242(c: Cast) -> None:
    """What survives is the ice: difficult terrain over the burst, until the
    fight ends. The DC 11 Acrobatics check that follows it is not written --
    nothing here rolls a skill check -- and neither is the requirement that
    there be water to freeze, which is a question about the map.
    """
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult="ice")


@power(
    "p16243",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p16243(c: Cast) -> None:
    """The altitude limit is not modelled and neither is the Sustain line --
    `c.mode` takes no sustain cost, and sustaining only re-ups the same
    duration -- so what is written is the flight and its price."""
    c.mode("fly", c.speed_of(), on=c.me, until=When.EONT)
    _open_to_everyone(c, until=When.EONT)


@power(
    "p3056",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def p3056(c: Cast) -> None:
    """The attack half -- destroying a fire conjuration or zone by beating
    its creator's Will -- is not written: a zone is not a creature, nothing
    targets one, and there is no dispel. The resistance is the half that
    every use of this row gets."""
    if c.first:
        c.resist(c.cha_mod, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    friend = c.target
    if friend is not None and friend != c.me:
        c.resist(c.cha_mod, DamageType.FIRE, on=friend, until=When.ENCOUNTER)


@power(
    "p3202",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p3202(c: Cast) -> None:
    """A 4 is all three, so the three benefits are functions and the roll
    picks which of them run."""
    me = c.me

    def vigour() -> None:
        c.temp_hp(c.roll("2d6") + c.cha_mod, on=me)

    def guard() -> None:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 2, on=me, until=When.ENCOUNTER)

    def thorns() -> None:
        def sting(ev: AttackDeclared) -> None:
            if ev.target == me and ev.attacker != me:
                c.flat(c.roll("2d6"), on=ev.attacker)

        c.watch(
            AttackDeclared, sting, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} thorns",
        )

    face = c.roll("1d4")
    for i, effect in enumerate((vigour, guard, thorns), start=1):
        if face == 4 or face == i:
            effect()


@power(
    "p5276",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5276(c: Cast) -> None:
    c.mode("fly", c.speed_of(), on=c.me, until=When.EONT)


@power(
    "p5277",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HIT_BY_ANYTHING,
    on=Trigger(AttackDeclared, when=hits_me, text=_HIT_BY_ANYTHING),
)
def p5277(c: Cast) -> None:
    """`once=True` spends the bonus on the first roll made against the
    sorcerer, and an interrupt resolves before that roll -- so the one it
    lands on is the attack that provoked it. The Dragon Magic clause, which
    sizes the bonus off Strength, goes with the fork."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 4, on=c.me, until=When.EOT, kind="untyped", once=True)


@power(
    "p5511",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger=_HIT_BY_A_SPLASH,
    on=Trigger(AttackDeclared, when=_splashed_me, text=_HIT_BY_A_SPLASH),
)
def p5511(c: Cast) -> None:
    """The Wild Magic clause -- a distance off Dexterity -- goes with the
    fork, so the printed 3 stands."""
    c.teleport(3)


@power(
    "p5853",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5853(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(c.speed_of())


@power(
    "p5854",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p5854(c: Cast) -> None:
    c.note(f"{c.ref}: +5 to three social skills, none of which anything rolls")
