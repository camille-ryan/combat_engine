"""Warlock, level 2: the utilities.

The first four are personal, and none attacks. `p380` and `p1299` print a
skill bonus and nothing else, and this engine has no checks for them to
modify, so they are declared inert with `out_of_combat=True` -- the cantrips
in `wizard/level_0.py` are the same shape -- rather than given a combat
effect they do not have.

The rows from the later books follow. Two of them turn on a saving throw
being made to come out a particular way: `SavingThrow` is announced before
it is acted on and `saved` is read back, which is the seam `c.unsave` uses,
and setting it the other way is how "you automatically succeed" is said.

`p5907` is declared on `DamageRolled` rather than on the `Hit` its printed
Trigger names, the seam `level_10.py`'s `p1328` settled: the amount is on
that event and still mutable, and a reaction on the hit itself resolves
before there is a number to reduce.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Event,
    Hit,
    Keyword,
    Mod,
    Relation,
    SavingThrow,
    Trigger,
    When,
    World,
    ZoneEntered,
    get,
    power,
)
from combat_engine.engine.events import DamageRolled

ARCANE = [Keyword.ARCANE]

_CURSED_HITS_ME = "an enemy you have cursed hits you with a melee attack"


def _melee_row(ev: Event) -> bool:
    """Was the row that dealt this a melee one? Read off `detail`."""
    p = get(getattr(ev, "detail", "") or "")
    return p is not None and p.reach.kind == "melee"


def _cursed_melee_on_me(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "target", None) != me or getattr(ev, "amount", 0) <= 0:
        return False
    source = getattr(ev, "source", None)
    if source is None or not _melee_row(ev):
        return False
    return world.relations.holds(Relation.CURSED_BY, me, source)


@power(
    "p1299",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p1299(c: Cast) -> None:
    c.note("p1299: a +5 power bonus to one social check this encounter")


@power(
    "p380",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p380(c: Cast) -> None:
    # Printed with the Illusion keyword, which the engine's list does not
    # carry; the Arcane keyword is the whole of what can be declared.
    c.note("p380: a +5 power bonus to going unnoticed, until your next turn ends")


@power(
    "p729",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p729(c: Cast) -> None:
    c.temp_hp(5 + c.con_mod, on=c.me)


@power(
    "p750",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p750(c: Cast) -> None:
    # Printed with the Teleportation keyword, which the engine's list does
    # not carry. "All defenses" is the four of them, one bonus each.
    c.teleport(3)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)


@power(
    "p10351",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.CHARM],
)
def p10351(c: Cast) -> None:
    """The four defences ride one effect so that sustaining keeps them all.

    The openings are closed again each time it is sustained rather than
    clocked to the encounter: `c.no_provoke` is a watch on the opportunity
    window, and one held past the effect would outlive it.
    """

    def shroud() -> None:
        c.no_provoke(until=When.EONT)

    hold = c.world.effects.apply(
        c.me,
        c.me,
        When.SUSTAIN,
        label=c.ref,
        sustain_cost=MINOR,
        mods=[
            (c.me, Mod(what=d.value, value=2, kind="power", label=c.ref))
            for d in (AC, FORT, REF, WILL)
        ],
    )
    shroud()
    c.on_sustain(hold, shroud)


@power(
    "p10380",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=ARCANE,
    out_of_combat=True,
)
def p10380(c: Cast) -> None:
    # Unattended objects are not on the board and carry no hit points, so
    # there is nothing here to destroy. The infernal pact raises the
    # threshold, which is a number about a thing that does not exist.
    c.note(f"p10380: an unattended object of {20 + c.level} hit points or fewer is gone")


@power(
    "p12890",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p12890(c: Cast) -> None:
    """Only the "cannot shift" half is written.

    `c.rooted` is exactly that clause. Barring teleportation and stripping
    concealment have no method, so neither is approximated -- and the
    rooting is laid on whoever is standing in the zone when it goes up and
    on anybody who walks in afterwards.
    """
    area = c.area()
    if not area:
        return
    ring = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    for foe in c.in_squares(area, side="enemy"):
        c.rooted(on=foe)

    def caught(ev: ZoneEntered) -> None:
        if ev.zone == ring and ev.actor in c.enemies():
            c.rooted(on=ev.actor)

    c.watch(ZoneEntered, caught, until=When.ENCOUNTER)


@power(
    "p13638",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p13638(c: Cast) -> None:
    c.invisible(on=c.me, until=When.EOT)


@power(
    "p13640",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.FEAR],
)
def p13640(c: Cast) -> None:
    """The Intimidate bonus has nothing to modify and is only noted; the
    scald is the half with teeth. The reach is read off the row that hit,
    because a damage context carries no such thing."""

    def scald(ev: Hit) -> None:
        if ev.target != c.me:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind == "melee":
            c.flat(5, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, scald, until=When.EONT)
    c.note(f"{c.ref}: a +5 power bonus to going in hard, which nothing rolls")


@power(
    "p13880",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION, Keyword.PSYCHIC],
)
def p13880(c: Cast) -> None:
    """The likeness itself is a named hold -- nobody here is fooled by a
    face -- and what it is for is the wound it shares back."""
    victim = c.target
    if victim is None:
        return
    guise = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=MINOR
    )

    def shared(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.amount <= 0:
            return
        c.flat(ev.amount // 2, dtype=DamageType.PSYCHIC, on=victim)
        if c.roll("1d20") >= 10:
            c.world.effects.end(guise, "the likeness broke")

    guise.subs.append(c.world.bus.on(DamageApplied, shared))


@power(
    "p16262",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p16262(c: Cast) -> None:
    """"Ignore forced movement" is `c.immovable`. The second half -- a save
    against being knocked prone -- has no shape: `c.save` answers a
    save-ends hold and nothing offers one against an attack's rider."""
    c.immovable(on=c.me, until=When.ENCOUNTER)


@power(
    "p1923",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p1923(c: Cast) -> None:
    # "You can move at that speed when you crawl" is prone movement, which
    # the engine has no separate rate for.
    c.mode("climb", c.speed_of(), until=When.EONT, on=c.me)


@power(
    "p4063",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p4063(c: Cast) -> None:
    """The free save is `SavingThrow` read back the other way from `c.unsave`.

    The window closes at the end of this turn, as printed: this buys one
    throw at the end of the turn it was spent on, not a standing exemption.
    """
    c.vulnerable(5, until=When.EONT, on=c.me)
    spent = [False]

    def stands(ev: SavingThrow) -> None:
        if spent[0] or ev.actor != c.me:
            return
        spent[0] = True
        ev.saved = True

    c.watch(SavingThrow, stands, until=When.EOT)


@power(
    "p4280",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def p4280(c: Cast) -> None:
    """The price is real and the bargain is not: there are no skill checks
    for the bonus to land on, so only the penalty is written."""
    c.penalty(WILL, 2, on=c.me, until=When.EONT)
    c.note(f"{c.ref}: a +5 power bonus to every skill check, which nothing rolls")


@power(
    "p5907",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger=_CURSED_HITS_ME,
    on=Trigger(DamageRolled, when=_cursed_melee_on_me, text=_CURSED_HITS_ME),
)
def p5907(c: Cast) -> None:
    ev = c.trigger
    if ev is not None:
        ev.amount = max(0, ev.amount - c.cha_mod)
    c.teleport(2)


@power(
    "p5909",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5909(c: Cast) -> None:
    """The bonus is spent on the next roll and the debt on the next throw,
    and neither waits for the other -- which is why they carry separate
    latches rather than one."""
    c.bonus("attack", 2, on=c.me, kind="power", until=When.ENCOUNTER, once=True)
    owed = [True]

    def falters(ev: SavingThrow) -> None:
        if not owed[0] or ev.actor != c.me:
            return
        owed[0] = False
        c.unsave(ev)

    c.watch(SavingThrow, falters, until=When.ENCOUNTER)
