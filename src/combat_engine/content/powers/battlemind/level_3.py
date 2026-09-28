"""Battlemind, level 3."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Augment,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    TurnEnd,
    TurnStart,
    When,
    distance,
    get,
    power,
)
from combat_engine.engine.events import AdjacencyGained

from . import PSIONIC_WEAPON, shift_beside, teleport_beside


@power(
    "p11163",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p11163(c: Cast) -> None:
    """"Until the target is adjacent to him" is the `AdjacencyGained` half,
    and Augment 1 is simply not arming it. Augment 2 hides every ally rather
    than one; the printed "while they aren't adjacent to it" would let an
    ally's invisibility come back when it stepped away again, and an
    invisibility is a relation rather than a gated modifier, so here it ends
    for good on the first time that ally is reached -- the same rule the
    unaugmented row applies to its one ally."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    if not mates:
        return
    if spent == 2:
        chosen = mates
    else:
        one = c.choose(mates, "who goes unseen")
        if one is None:
            return
        chosen = [one]
    hidden = {mate: c.invisible(to=victim, on=mate, until=When.EONT) for mate in chosen}

    def closed(ev: AdjacencyGained) -> None:
        for mate, held in hidden.items():
            if held is not None and {ev.actor, ev.other} == {mate, victim}:
                c.world.effects.end(held, "the target is adjacent")

    if spent != 1:
        c.watch(AdjacencyGained, closed, until=When.EONT, on=c.me)


@power(
    "p11164",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=REF),
)
def p11164(c: Cast) -> None:
    """The unaugmented form is the bare attack. Both augments defeat
    insubstantiality: Augment 1 for this blow only, which is
    `c.ignore_condition` -- the quality is suppressed rather than cured, so
    it is still there afterwards -- and Augment 2 for the turn."""
    spent = augment(c)
    ghostly = c.is_(Condition.INSUBSTANTIAL)
    lifted = None
    if spent:
        lifted = c.ignore_condition(
            Condition.INSUBSTANTIAL, until=When.EOT if spent == 1 else When.EONT
        )
    if c.strike():
        extra = c.wis_mod if spent == 1 and ghostly else 0
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod + extra)
    # "Against this attack" and no longer: Augment 1's suppression is ended
    # here rather than left on a clock, which would cover the rest of the
    # turn as well.
    if spent == 1 and lifted is not None:
        c.world.effects.end(lifted, "the attack is over")


@power(
    "p12422",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE],
    attack=Attack(CON, vs=AC),
    augments=(Augment(1, reach=Melee(2)),),
    dropped=("dsl.Range.by_ability",),
)
def p12422(c: Cast) -> None:
    """Augment 1 is a square of extra reach for that attack, which is the
    header and is declared there.

    Augment 2 is the `dropped` clause and its hold is not the augment
    machinery: it lengthens the reach by *your Charisma modifier*, and a
    `Range` holds a number that is read off the card before any creature
    is in hand. Its stronger Hit line is not written alone, because half a
    clause is worse than none. The slide is anchored on the caster's
    square, which is what "to a square adjacent to you" means."""
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.FORCE)
        c.slide(1, anchor=c.here)


@power(
    "p13039",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1, reach=Melee(2)),
        Augment(2),
    ),
)
def p13039(c: Cast) -> None:
    """Augment 2 is 2[W] and a second recall if the target runs -- "more than
    2 squares on its next turn" measured from where its turn began, so the
    square it started in is caught on the move itself.

    Augment 1 is a square of extra reach, which is the header, so it is
    declared there and the spend is settled before the target is chosen."""
    spent = augment(c, 1, 2) == 2
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent else c.w(), c.con_mod)
    teleport_beside(c, victim, c.me)
    if not spent:
        return
    began: dict[str, Any] = {}

    def began_turn(ev: TurnStart) -> None:
        at = c.world.get(victim, Position) if ev.actor == victim else None
        if at is not None:
            began["at"] = at.square

    def ran(ev: MoveEnd) -> None:
        start = began.get("at")
        if ev.actor == victim and start is not None and distance(start, ev.at) > 2:
            began.pop("at")
            teleport_beside(c, victim, c.me)

    c.watch(TurnStart, began_turn, until=When.EOTNT, on=victim, label=c.ref)
    c.watch(MoveEnd, ran, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p13040",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13040(c: Cast) -> None:
    """Augment 1 adds the modifier to the damage. Augment 2 also widens the
    blink: any damage at all sets it off, from anywhere, and it goes 3
    squares rather than 2."""
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod if spent else 0)

    def blink(ev: DamageApplied) -> None:
        if ev.target != c.me:
            return
        if spent == 2:
            c.teleport(3)
            return
        if ev.source is not None and ev.source in c.enemies() and not c.adjacent(ev.source):
            c.teleport(2)

    c.watch(DamageApplied, blink, until=When.SONT, on=c.me)


@power(
    "p13041",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=WILL),
    augments=(
        Augment(1, reach=Melee(5)),
        Augment(2, reach=Melee(5)),
    ),
    dropped=("c.confine(to=)",),
)
def p13041(c: Cast) -> None:
    """Both augments print Melee 5, which is the header's reach and is
    measured before the body runs, so both are declared there -- and with
    the reach declared, the longer pull and the prone that come with them
    are writable below.

    "The target can move only to squares adjacent to you" is the `dropped`
    clause and is printed on all three forms: nothing on `Cast` constrains
    where a creature may walk."""
    spent = augment(c, 1, 2)
    if not c.strike():
        return
    c.damage(c.w() if spent == 2 else 0, c.con_mod)
    c.pull(4 if spent else 1)
    if spent == 2:
        c.prone()


@power(
    "p13042",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13042(c: Cast) -> None:
    """Augment 1 lengthens the step to your speed. Augment 2 replaces it with
    a charge at somebody else; the charge's own move not provoking is the one
    part left out, since `c.charge_at` walks the ordinary way."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.con_mod)
    if not c.last:
        return
    others = [e for e in c.enemies() if e != victim]
    if not others:
        return
    prey = min(others, key=c.distance)
    if spent == 2:
        c.charge_at(prey)
    else:
        shift_beside(c, c.speed_of() if spent else 2, prey)


@power(
    "p13466",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13466(c: Cast) -> None:
    """This row prints no Augment 1, only an Augment 2, which raises the dice
    and extends the concealment to the allies beside you.

    The concealment is `c.conceal` on whoever has it, gated on the attacker
    being the target. "Until you end your turn in a square not adjacent to
    the target" is the end condition, so it is checked at `TurnEnd` rather
    than held on a clock."""
    spent = augment(c, 2)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent else c.w(), c.con_mod)
    if victim is None:
        return

    def theirs(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") == victim

    hidden = [c.conceal(on=c.me, until=When.ENCOUNTER, when=theirs)]
    if spent:
        hidden += [
            c.conceal(on=a, until=When.ENCOUNTER, when=theirs)
            for a in c.within(1, side="ally") if a != c.me
        ]

    def checked(ev: TurnEnd) -> None:
        if ev.actor != c.me or c.adjacent(victim):
            return
        for held in hidden:
            if held is not None:
                c.world.effects.end(held, "you ended your turn away from it")

    c.watch(TurnEnd, checked, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p2626",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p2626(c: Cast) -> None:
    """Augment 1 adds a Charisma-sized penalty to the target's melee and
    close attacks, which is a gate on the reach of whatever row it swings --
    the attack context carries the ref and `get` does the rest. Augment 2
    raises the dice and immobilises."""
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
    c.grants_advantage(until=When.EONT, to="team")
    if spent == 2:
        c.immobilized(until=When.EONT)
        return

    def up_close(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return p is not None and p.reach.kind in ("melee", "close_burst", "close_blast")

    if spent:
        c.penalty("attack", c.cha_mod, until=When.EONT, when=up_close)


@power(
    "p2627",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=AC),
)
def p2627(c: Cast) -> None:
    """Augment 1 pushes by Charisma and lengthens every later shove of the
    target by a square. That last is a **negative** `"forced"` modifier on
    the target, because the shove reads resistance off the creature being
    moved and the gate it is handed carries only `how` and `power` -- so it
    lengthens an enemy's shove of the target too, where the card says you or
    your allies. Augment 2 pushes by Charisma and then slides everybody the
    target was left standing next to."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    c.push(c.cha_mod if spent else 2)
    if spent == 1:
        c.penalty("forced", 1, until=When.EONT)
    elif spent == 2 and victim is not None:
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.slide(1, on=foe)
