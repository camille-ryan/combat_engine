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
    AREA_OR_CLOSE,
    DAILY,
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
    YOU_AND_EACH_ALLY,
    AreaBurst,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Event,
    Hit,
    Keyword,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    ZoneEntered,
    ally_within,
    both,
    get,
    hits_me,
    not_me,
    power,
    targets_my_side,
)

from . import has_familiar
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
    return p is not None and p.reach.kind in AREA_OR_CLOSE


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
        when=lambda ctx: victim is None or ctx.get("target") == victim, kind="power")


@power(
    "p16242",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, within=10),
    target=NO_TARGET,
    keywords=[*ARCANE, Keyword.ELEMENTAL],
)
def p16242(c: Cast) -> None:
    """What survives is the ice: difficult terrain over the burst, until the
    fight ends.

    **The DC 11 Acrobatics check is written now.** The old note said
    "nothing here rolls a skill check"; `c.check(skill, dc)` is "roll a
    skill check, truthy when it beat the DC", and `combat_engine/dc.py`
    holds 90 printed numbers for the ones that are not stated outright.
    This card states its own, so the 11 is the card's and not a band's.
    #1341.

    Both halves of "enters a square of this ice **or starts its turn
    there**", which is two events and one clause.

    Still not written: the requirement that there be water to freeze.
    That is a question about the map rather than about the engine, and
    the old note had it right.
    """
    area = c.area()
    if not area:
        return
    ice = c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult="ice")

    def slip(who: int) -> None:
        if not c.check("acrobatics", 11, who=who):
            c.prone(on=who)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == ice:
            slip(ev.actor)

    def stood_there(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ice):
            slip(ev.actor)

    c.watch(ZoneEntered, walked_in, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} underfoot")
    c.watch(TurnStart, stood_there, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} still underfoot")


@power(
    "p16243",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*ARCANE, Keyword.ELEMENTAL],
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
    target=YOU_AND_EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def p3056(c: Cast) -> None:
    """**The attack half is written, and every verb it needed already
    existed.** The old note said "a zone is not a creature, nothing targets
    one, and there is no dispel", and all three clauses were false:
    `c.conjurations` is the pool -- its own docstring says it is "the pool a
    target line reading 'one conjuration or zone' picks from" -- `c.made_by`
    answers whose it is, and `c.dispel` is *"destroy a zone or a
    conjuration, and unwind what it was holding"*, which is this card's "the
    target is destroyed, all its effects end" in one call.

    `sorcerer/level_10_sd.py` had the whole shape already: pool, choose,
    `c.made_by`, strike the maker, dispel the thing. So this was a marker
    standing where a sibling row was working.

    **`Zone.defences` was also the wrong symbol**, which is worth saying
    because two other rows wait on it and should not now be read as waiting
    on this. The card attacks *"the Will of the target's **creator**"* -- a
    creature's defence, which has always existed. `x2_129` is the row that
    genuinely wants a zone to have defences of its own ("a ranged attack
    against the thing itself, whose defences are level + 5"); that gap is
    untouched and keeps its symbol.

    The keyword filter needs the row that laid the thing rather than the
    thing itself, which is `c.made_with` -- `Zone.power` and
    `Conjuration.ref` keep the ref in different fields, so a filter reading
    one would silently skip half the pool.

    Close burst 10, so `within=10`. Nothing excludes the caster's own
    fire: the card says "one conjuration or zone that has the fire
    keyword" and names no side, where the sibling row above prints
    "created by an enemy" and filters on it."""
    if c.first:
        c.resist(c.cha_mod, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    friend = c.target
    if friend is not None and friend != c.me:
        c.resist(c.cha_mod, DamageType.FIRE, on=friend, until=When.ENCOUNTER)
    if not c.first:
        return
    burning = [
        thing
        for thing in c.conjurations(within=10)
        if (row := get(c.made_with(thing))) is not None
        and Keyword.FIRE in c.keywords_of(row)
    ]
    if not burning:
        return
    pick = c.choose(burning, f"{c.ref}: which fire to put out")
    if pick is None:
        return
    maker = c.made_by(pick)
    if maker is None:
        return
    # "Charisma + 2 vs. the Will of the target's creator". Longhand
    # through `c.attack` rather than `c.strike`, because the header
    # declares no attack -- the first target line is the resistance,
    # which rolls nothing, and this is the card's second one.
    if c.attack(c.cha_ + 2, WILL, on=maker):
        c.dispel(pick)


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
            c.bonus(d, 2, on=me, until=When.ENCOUNTER, kind="power")

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
    lands on is the attack that provoked it.

    **The Dragon Magic clause is written now** and "goes with the fork"
    was the premise `#1303` refuted for `wild`: a missing class-feature
    row read as a missing build. `BUILDS["sorcerer"]` carries all four
    sources, and the printed ref maps to its leg off its own spec text.
    #1351.

    It **replaces** the 4 rather than adding to it -- "the bonus to all
    defenses **equals** 3 + your Strength modifier" -- so it is one
    number chosen before the loop, not a second bonus laid on top.
    """
    amount = 3 + c.str_mod if c.build("dragon") else 4
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, amount, on=c.me, until=When.EOT, kind="untyped", once=True)


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


@power(
    "p12471",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    requires=has_familiar,
    requires_text="your familiar must be in its active mode",
    trigger="an attack hits an ally you can see",
    on=Trigger(Hit, both(targets_my_side, not_me), "an attack hits an ally"),
)
def p12471(c: Cast) -> None:
    """`targets_my_side` takes in the caster too, so `not_me` is the other half
    of "an ally". The redirect is conditional on where the shift ended, which is
    the printed rule and not a formality; the damage to the caster is an Effect
    line and is paid either way."""
    fam = c.companion()
    ally = getattr(c.trigger, "target", None)
    if fam is None or ally is None:
        return
    c.shift(c.speed_of(fam), who=fam)
    if ally in c.within(1, of=fam):
        c.redirect(to=fam)
    c.flat(c.level, on=c.me, from_attack=False)
