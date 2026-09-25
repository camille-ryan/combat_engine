"""Cleric, level 1: the rows the later books added.

`level_1.py` and `level_1_encounter.py` were already full, so these sit
beside them. A row's level is what decides where it lives; nothing else
distinguishes the three files.

Five things recur here and are worth saying once.

**"Strength or Wisdom vs. Will"** is one printed attack line offering two
abilities, not a two-branch range line, so `attack_alt` cannot carry it --
that field is only read for a `MeleeOrRanged` reach. The header keeps the
first printed ability for the card and `_str_or_wis` rolls whichever the
character is actually better at.

**"You or one ally within 5 squares"** is exactly what the ally pool holds:
`c.within(..., side="ally")` counts the caster, so the caster is already one
of the answers and the choice is offered over the pool untouched. Where the
printed line says only "each ally", the caster comes back out.

**A printed reroll inside a watcher** goes through `_reroll`, which lends
`c.reroll_attack` the event the watcher is holding rather than copying the
arithmetic. It is armed in the `Window.BEFORE` half of the `Miss`, because
`resolve.attack` re-reads the outcome in the resolve callback that follows
that window -- a reroll landing after it would change the number and leave
the miss standing.

**`Keyword.SHADOW` does not exist** and p13922's fourth printed keyword is a
power source rather than a mechanic, so the row carries the other three.

The two Channel Divinity rows declare `group=`, which is the header field
for "only one of these per encounter".
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.grid import blast
from combat_engine.engine.query import distance_between, squares, team

DIVINE = [Keyword.DIVINE]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]




def _str_or_wis(c: Cast) -> tuple[int, int]:
    """The attack bonus and the damage modifier of the better of the two."""
    if c.wis_ > c.str_:
        return c.wis_, c.wis_mod
    return c.str_, c.str_mod


def _has_bow(world: World, eid: int) -> bool:
    """"Requirement: you must be wielding a bow"."""
    gear = world.get(eid, Gear)
    bow = gear.ranged if gear is not None else None
    return bow is not None and bow.group == "bow"


def _reroll(c: Cast, ev: Any) -> bool:
    """`c.reroll_attack` reads `c.trigger`; a watcher holds its event in hand."""
    was, c.trigger = c.trigger, ev
    try:
        return c.reroll_attack()
    finally:
        c.trigger = was


def _against(foe: int | None) -> Callable[[dict[str, Any]], bool]:
    return lambda ctx: ctx.get("target") == foe


_ENEMY_HITS_ALLY = "an enemy hits an ally with an attack"


def _hits_an_ally(world: World, me: int, ev: Event) -> bool:
    """An enemy within reach lands a blow on somebody other than you.

    `ally_within` reads the creature the event is *about*, which on an attack
    is the one swinging, so it answers "an ally attacks". The reach test is
    the printed range line: this is a melee weapon answer, and a row offered
    against an enemy across the room could never swing.
    """
    friend = getattr(ev, "target", None)
    result = getattr(ev, "result", None)
    foe = getattr(ev, "attacker", None)
    if friend is None or foe is None or friend == me or not (result and result.hit):
        return False
    if team(world, friend) is not team(world, me):
        return False
    if team(world, foe) is team(world, me):
        return False
    return distance_between(world, me, foe) <= 1


# -- at-will ---------------------------------------------------------------


@power(
    "p12205",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12205(c: Cast) -> None:
    """The penalty rides on the target, because the mods read for a damage
    roll are the dealer's. The Special line -- this row used as a melee basic
    attack -- has no header field; see the report.
    """
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.penalty("damage", c.cha_mod, until=When.EONT, once=True)


@power(
    "p12298",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(WIS, vs=AC),
    requires=_has_bow,
)
def p12298(c: Cast) -> None:
    """No `requires_text`, deliberately: `chargen.build_for` looks for the
    word "requirement" in the refusal to decide which build can hold a row,
    and a custom message hides it.

    "The next ally to hit" is one payout for the whole party rather than one
    each, so it is a latched watcher rather than a bonus handed round.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod)
    foe = c.target
    friends = set(c.allies())
    spent: list[bool] = []

    def blaze(ev: Hit) -> None:
        if spent or ev.target != foe or ev.attacker not in friends:
            return
        spent.append(True)
        c.flat(c.cha_mod, dtype=DamageType.RADIANT, on=foe)

    c.watch(Hit, blaze, until=When.EONT, on=c.me, label=f"{c.ref} radiance")


@power(
    "p12634",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12634(c: Cast) -> None:
    foe = c.target
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    # The Effect line lands whether or not the blow did.
    who = c.choose(c.within(5, side="ally"), "who gets the opening")
    if who is not None:
        c.bonus(
            "damage", c.con_mod, on=who, until=When.EONT, kind="power",
            once=True, when=_against(foe),
        )


@power(
    "p12635",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p12635(c: Cast) -> None:
    """Lightning *and* thunder: the damage carries the first of the two
    printed types, which is what a resistance check reads, and both keywords
    carry the rest. The Special line about charging is a note on how the row
    may be used, not an Effect that charges.
    """
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.LIGHTNING)


@power(
    "p12647",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12647(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    who = c.choose(c.within(5, side="ally"), "who is warded")
    if who is not None and c.con_mod > 0:
        c.resist(c.con_mod, until=When.EONT, on=who)


@power(
    "p12648",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12648(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    # Offered to whoever is actually carrying something to shake off; the
    # rest of the pool follows, because the printed line lets you pick.
    pool = c.within(5, side="ally")
    burdened = [a for a in pool if any(e.when is When.SAVE_ENDS for e in c.world.effects.of(a))]
    who = c.choose(burdened + [a for a in pool if a not in burdened], "who tries a save")
    if who is not None:
        c.save(on=who)


@power(
    "p13706",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13706(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    who = c.choose(c.within(5, side="ally"), "who is guarded")
    if who is not None:
        c.bonus(AC, 2, on=who, until=When.EONT, kind="power")


@power(
    "p13707",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13707(c: Cast) -> None:
    """"The next time you or an ally attacks" is one bonus for the whole
    party, so it is raised on the attack itself rather than handed to
    everybody. The declaration's `Window.BEFORE` runs ahead of the resolve
    callback that rolls, so a modifier raised there is still counted.
    """
    foe = c.target
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.push(1)
    if foe is None:
        return
    squad = {c.me, *c.allies()}
    spent: list[bool] = []

    def steady(ev: AttackDeclared) -> None:
        if spent or ev.target != foe or ev.attacker not in squad:
            return
        spent.append(True)
        c.bonus("attack", 1, on=ev.attacker, until=When.EOT, kind="power", once=True)

    c.watch(
        AttackDeclared, steady, until=When.EONT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} aim",
    )


# -- encounter --------------------------------------------------------------


@power(
    "p11041",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_ENEMY_HITS_ALLY,
    on=Trigger(AttackRolled, when=_hits_an_ally, text=_ENEMY_HITS_ALLY),
)
def p11041(c: Cast) -> None:
    """Interrupted before the blow arrives, so the halving is armed on
    `DamageRolled` -- a mutable amount, announced before hit points move.
    The latch is kept by hand: `once=` on a watch spends on the log growing,
    and editing a number logs nothing.
    """
    foe = getattr(c.trigger, "attacker", None) or c.target
    friend = getattr(c.trigger, "target", None)
    if foe is None or not c.strike(on=foe):
        return
    c.damage(c.w(2), c.str_mod, on=foe)
    if friend is None:
        return
    spent: list[bool] = []

    def halve(ev: DamageRolled) -> None:
        if spent or ev.source != foe or ev.target != friend:
            return
        spent.append(True)
        ev.amount //= 2

    c.watch(
        DamageRolled, halve, until=When.EOT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} half damage",
    )


@power(
    "p12410",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE,
)
def p12410(c: Cast) -> None:
    """No attack roll at all: three riders on one enemy."""
    foe = c.target
    if foe is None:
        return
    c.grants_advantage(until=When.EONT, to="allies")
    for friend in c.allies():
        c.bonus(
            "damage", c.wis_mod, on=friend, until=When.EONT, kind="power",
            when=_against(foe),
        )
    friends = set(c.allies())
    spent: list[bool] = []

    def again(ev: Miss) -> None:
        if spent or ev.target != foe or ev.attacker not in friends:
            return
        if not c.may("take the shot again", who=ev.attacker):
            return
        spent.append(True)
        _reroll(c, ev)

    c.watch(
        Miss, again, until=When.EONT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} second chance",
    )


@power(
    "p12637",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p12637(c: Cast) -> None:
    foe = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.THUNDER)
    if foe is None:
        return
    squad = {c.me, *c.allies()}
    spent: list[bool] = []

    def echo(ev: Hit) -> None:
        if spent or ev.target != foe or ev.attacker not in squad:
            return
        spent.append(True)
        c.flat(3, dtype=DamageType.THUNDER, on=foe)

    c.watch(Hit, echo, until=When.SONT, on=c.me, label=f"{c.ref} echo")


@power(
    "p12650",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p12650(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    for friend in c.within(5, side="ally"):
        c.temp_hp(5, on=friend)
        c.save(on=friend)


@power(
    "p12651",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=DIVINE,
    group=CHANNEL_DIVINITY,
)
def p12651(c: Cast) -> None:
    c.save(on=c.target, bonus=2)


@power(
    "p13709",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=FORT),
)
def p13709(c: Cast) -> None:
    """"A blast 3 that includes the target" is `grid.blast` aimed at the
    target's square, which is the nearest legal placement of the block. The
    target takes the same damage whether or not the block reached it.
    """
    foe = c.target
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        if foe is not None:
            area = blast(squares(c.world, c.me), 3, c.there)
            for who in {*c.in_squares(area, side="enemy"), foe}:
                c.flat(c.con_mod, on=who)
    for friend in c.within(3, side="ally"):
        c.bonus(AC, 2, on=friend, until=When.EONT, kind="power")
        c.bonus(FORT, 2, on=friend, until=When.EONT, kind="power")


@power(
    "p13710",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=DIVINE,
    group=CHANNEL_DIVINITY,
)
def p13710(c: Cast) -> None:
    """The paragon and epic steps of the resistance are for later tiers."""
    c.resist(5, until=When.EONT, on=c.target)


# -- daily ------------------------------------------------------------------


@power(
    "p10088",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(STR, vs=WILL),
)
def p10088(c: Cast) -> None:
    """Rolling twice and keeping the worse is written onto the live
    `AttackResult`: `resolve.attack` recomputes the outcome from it once the
    `AttackRolled` windows close, so lowering the die there still misses.

    The Aftereffect hangs on the hold's `on_end` rather than on `escalate`,
    which runs on a *failed* save. It therefore also pays out if the fight
    ends first, which is the closer of the two wrong answers.
    """
    victim = c.target
    bonus, _ = _str_or_wis(c)
    if victim is None:
        return
    if not c.attack(bonus, WILL):
        c.flat(10, dtype=DamageType.PSYCHIC)
        return

    def doubt(ev: AttackRolled) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker != victim or result is None:
            return
        fresh = c.world.rng.d20().total
        if fresh < result.natural:
            result.total += fresh - result.natural
            result.natural = fresh

    hold: Effect = c.watch(
        AttackRolled, doubt, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} doubt"
    )
    hold.on_end.append(lambda: c.flat(10, dtype=DamageType.PSYCHIC, on=victim))


@power(
    "p11042",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11042(c: Cast) -> None:
    """The Special line -- this row in place of a melee basic when charging --
    is a note on how it may be used; `charges=True` is for a row whose
    printed Effect is itself a charge.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.mark(until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(3), c.str_mod)
        c.mark(until=When.EONT)


@power(
    "p11617",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11617(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(1), c.str_mod)
        c.weakened(until=When.EONT)


@power(
    "p12603",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p12603(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    if c.first:
        # "Each ally within 2" leaves the caster out; the pool counts them in.
        for friend in c.within(2, side="ally"):
            if friend == c.me:
                continue
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 2, on=friend, until=When.ENCOUNTER, kind="power")


@power(
    "p12604",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p12604(c: Cast) -> None:
    """The Effect line lands hit or miss, and its third clause is a watcher
    rather than an aura: `c.aura` marks out squares and has nothing that
    fires at the end of a turn spent in them.
    """
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    c.temp_hp(10, on=c.me)
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="power")
    me = c.me

    def sear(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.adjacent(ev.actor):
            c.flat(c.con_mod, dtype=DamageType.RADIANT, on=ev.actor)

    c.watch(TurnEnd, sear, until=When.ENCOUNTER, on=me, label=f"{c.ref} halo")


@power(
    "p12605",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12605(c: Cast) -> None:
    """The free action is the caster's, so the caster is asked; the ally only
    supplies the roll being taken again.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    friends = set(c.allies())
    spent: list[bool] = []

    def again(ev: Miss) -> None:
        if spent or ev.target != victim or ev.attacker not in friends:
            return
        if not c.may("let the blow be struck again", who=c.me):
            return
        spent.append(True)
        _reroll(c, ev)

    c.watch(
        Miss, again, until=When.ENCOUNTER, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} second chance",
    )


@power(
    "p13922",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.NECROTIC],
)
def p13922(c: Cast) -> None:
    """No attack roll: the whole printed line is an Effect, so the damage is
    dealt outright.
    """
    c.damage("3d6", c.wis_mod, dtype=DamageType.NECROTIC)


# -- narrative only ---------------------------------------------------------


@power(
    "p12636",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=DIVINE,
    out_of_combat=True,
)
def p12636(c: Cast) -> None:
    c.note("p12636: a held container of up to a gallon fills with fresh water")


@power(
    "p12649",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=DIVINE,
    out_of_combat=True,
)
def p12649(c: Cast) -> None:
    c.note("p12649: bright light out to 4 squares, for an hour or until ended")


@power(
    "p13708",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    out_of_combat=True,
)
def p13708(c: Cast) -> None:
    c.note("p13708: +5 to one check to find what is hidden within 10 squares")
