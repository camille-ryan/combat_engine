"""Battlemind, level 1."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Augment,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Moved,
    MoveEnd,
    Position,
    TurnEnd,
    UpTo,
    When,
    power,
    spread,
)
from combat_engine.engine.query import creatures

from . import PSIONIC_WEAPON, teleport_beside


def _vs_opportunity(ctx: dict[str, Any]) -> bool:
    """"Against opportunity attacks". The attack context carries the flag and
    `query.defence` is handed that same context, so it gates a defence too."""
    return bool(ctx.get("opportunity"))


@power(
    "p10442",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CON, vs=AC),
)
def p10442(c: Cast) -> None:
    """The free swing is handed to the target through `c.grant_attack`, so a
    creature whose basic attack has been replaced uses its own."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.con_mod, dtype=DamageType.PSYCHIC)
        reachable = [o for o in c.within(1, of=victim) if o != victim]
        if reachable:
            picked = c.choose(reachable, "who it swings at")
            if picked is not None:
                c.grant_attack(victim, on=picked)
    else:
        c.half_damage(c.w(2), c.con_mod, dtype=DamageType.PSYCHIC)


@power(
    "p11156",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p11156(c: Cast) -> None:
    """Augment 1 trades resistance to everything for a larger one to fire
    alone; Augment 2 raises the dice and leaves the Effect as printed."""
    spent = augment(c)
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
    if not c.first:
        return
    if spent == 1:
        c.resist(5 + c.wis_mod, DamageType.FIRE, until=When.EONT)
    elif c.wis_mod > 0:
        c.resist(c.wis_mod, until=When.EONT)


@power(
    "p11157",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1, reach=Melee(2)),
        Augment(2, reach=CloseBlast(3), target=EACH_ENEMY),
    ),
)
def p11157(c: Cast) -> None:
    """Both augments are the header and neither is a body clause: Augment 1
    lengthens the reach by a square for that attack, Augment 2 swaps the
    swing for a close blast against each enemy in it. Reach and the target
    line are both measured before the body is called, so both are declared
    and the spend is settled above targeting. Neither prints a Hit line of
    its own, so the swing below is the whole of all three forms."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.push(1)


@power(
    "p11158",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.HEALING, Keyword.POLYMORPH],
    attack=Attack(CON, vs=AC),
)
def p11158(c: Cast) -> None:
    """The aspect is a hold with no content of its own: everything it grants
    is its Augment 1, and that clause is bought when some *other* row is
    augmented -- "while in this aspect you can use the following augmentation
    with your at-will attack powers". Nothing lets one row add an offer to
    another row's augment, so it is left out."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        if c.may("spend a healing surge", who=c.me):
            c.surge(on=c.me)
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)


@power(
    "p11160",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p11160(c: Cast) -> None:
    """The recall is armed on the target's own turn end, so the save-ends hold
    sits on the target and it is the one that rolls out of it."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.con_mod)
        hold = When.SAVE_ENDS
    else:
        c.half_damage(c.w(2), c.con_mod)
        hold = When.EOTNT

    def recall(ev: TurnEnd) -> None:
        if ev.actor == victim and c.may("teleport it back", who=c.me):
            teleport_beside(c, victim, c.me)

    c.watch(TurnEnd, recall, until=hold, on=victim)


@power(
    "p12419",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE],
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1, reach=CloseBurst(3)),
        Augment(2),
    ),
)
def p12419(c: Cast) -> None:
    """Augment 2 knocks the target prone and leaves the blast alone.

    Augment 1 swaps the blast for a close burst 3, which is the header, so
    it is declared there -- and it also shoves **one** enemy rather than
    each, which is the one place the two forms disagree below."""
    spent = augment(c, 1, 2)
    if not c.strike():
        return
    c.damage(c.w(), c.con_mod, dtype=DamageType.FORCE)
    if spent == 2:
        c.prone()
    area = c.area()
    caught = c.in_squares(area, side="enemy") if area else c.within(3, side="enemy")
    others = [o for o in caught if o != c.target]
    if spent == 1:
        one = c.choose(sorted(others), "who is shoved") if others else None
        others = [one] if one is not None else []
    for other in others:
        c.push(1 + c.cha_mod, on=other)


@power(
    "p12420",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p12420(c: Cast) -> None:
    """"Take no damage from hindering terrain or terrain hazards" is dropped:
    `c.resist` cannot be aimed at a source rather than a damage type."""
    if c.strike():
        c.damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.push(c.cha_mod)
    else:
        c.half_damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.push(1)
    if c.first:
        c.stance()
        c.ignores_difficult()


@power(
    "p13025",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(CON, vs=REF),
)
def p13025(c: Cast) -> None:
    """Augment 1 adds a second way to set the recoil off -- shifting to a
    square beside one of your allies, which is `MoveEnd.kind_` and a
    position read where the shift ended. Augment 2 only raises the dice."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod, dtype=DamageType.LIGHTNING)

    def recoil(ev: Hit) -> None:
        if ev.attacker == victim and ev.target in c.allies():
            c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=victim)

    def sidled(ev: MoveEnd) -> None:
        if ev.actor != victim or ev.kind_ != "shift":
            return
        if any(c.adjacent_to(a, victim) for a in c.allies() if a != c.me):
            c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=victim)

    c.watch(Hit, recoil, until=When.SONT, on=victim)
    if spent == 1:
        c.watch(MoveEnd, sidled, until=When.SONT, on=victim)


@power(
    "p13027",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1),
        Augment(2, reach=CloseBurst(1), target=EACH_ENEMY),
    ),
)
def p13027(c: Cast) -> None:
    """Augment 1 marks one enemy standing beside the target as well.

    Augment 2 is a close burst against each enemy, which is a target line
    and is therefore declared in the header. Its Hit is a full 1[W]
    whatever the burst caught -- the base card's "1[W] extra if you target
    only one creature" is a rule about the base card's *two* targets and is
    not printed under Augment 2 -- and it adds a -2 to attack rolls beside
    the mark."""
    spent = augment(c, 1, 2)
    victim = c.target
    if c.strike():
        alone = len(c.targets) == 1 or spent == 2
        c.damage(c.w() if alone else 0, c.con_mod, dtype=DamageType.PSYCHIC)
        c.mark(until=When.EONT)
        if spent == 2:
            c.penalty("attack", 2, until=When.EONT)
        if spent == 1 and victim is not None:
            beside = [
                f for f in c.within(1, of=victim, side="enemy")
                if f != victim and f not in c.targets
            ]
            other = c.choose(sorted(beside), "who else is marked") if beside else None
            if other is not None:
                c.mark(until=When.EONT, on=other)


@power(
    "p13028",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13028(c: Cast) -> None:
    """Both augments turn the step into a teleport -- Augment 1 of one square,
    Augment 2 of any distance, so long as it ends beside the target. The
    Teleportation keyword both augments add is not declared: the header is
    data read before the augment is bought, so it would be on the row for
    the unaugmented use too."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
    if not spent or victim is None:
        c.shift(1)
        return
    if spent == 2:
        teleport_beside(c, c.me, victim)
        return
    at = c.world.get(victim, Position)
    if at is not None:
        for sq in sorted(spread({at.square}, 1)):
            if c.teleport(1, to=sq):
                break


@power(
    "p13029",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13029(c: Cast) -> None:
    """Two clauses are dropped: moving through enemies' spaces during the
    opening shift, and the extra square on every later shift -- `c.bonus`
    names speed but nothing names a shift's length."""
    if c.first:
        c.shift(c.speed_of())
    if c.strike(advantage=True):
        c.damage(c.w(2), c.con_mod)
        c.no_provoke(from_=c.target, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.last:
        c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p13030",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.COLD, Keyword.POLYMORPH],
    attack=Attack(CON, vs=FORT),
)
def p13030(c: Cast) -> None:
    """The aspect's resist 5 cold is its whole unaugmented content. Its
    Augment 1 is not an augment of *this* row at all: it is an extra clause
    the aspect lends to any augmented battlemind at-will, and nothing hangs
    a clause on another row's augment."""
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.COLD)
        c.push(1)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.con_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
    if c.first:
        c.resist(5, DamageType.COLD, until=When.ENCOUNTER)


@power(
    "p13031",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13031(c: Cast) -> None:
    """The whole Effect is dropped: nothing on `Cast` grants cover, and the
    minor action that trades the cover away for resist 5 needs the first half
    to exist before it can be written."""
    if c.strike():
        c.damage(c.w(3), c.con_mod)
    else:
        c.half_damage(c.w(3), c.con_mod)


@power(
    "p13032",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.STANCE],
    attack=Attack(CON, vs=REF),
)
def p13032(c: Cast) -> None:
    """"If it moves more than half its speed" has to be counted: `MoveEnd`
    says where a move finished and not how long it was, so the steps are
    tallied off `Moved` and read when the move ends. Both subscriptions hang
    on the one save-ends hold so one save clears both."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.con_mod)
        steps = [0]

        def stepped(ev: Moved) -> None:
            if ev.actor == victim:
                steps[0] += 1

        def landed(ev: MoveEnd) -> None:
            if ev.actor != victim:
                return
            if steps[0] * 2 > c.speed_of(victim):
                c.flat(5, dtype=DamageType.PSYCHIC, on=victim)
            steps[0] = 0

        held = c.watch(Moved, stepped, until=When.SAVE_ENDS, on=victim)
        held.subs.append(c.world.bus.on(MoveEnd, landed, owner=c.me))
    else:
        c.half_damage(c.w(2), c.con_mod)
        c.slowed(until=When.EONT)
    if c.last:
        c.stance()
        c.bonus(AC, 4, on=c.me, until=When.ENCOUNTER, when=_vs_opportunity, kind="power")
        c.bonus(REF, 4, on=c.me, until=When.ENCOUNTER, when=_vs_opportunity, kind="power")
        c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=_vs_opportunity, kind="power")


@power(
    "p2621",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p2621(c: Cast) -> None:
    """Augment 2 blinds instead of penalising. The penalty is counted when the
    blow lands rather than recounted per roll -- a modifier holds a number,
    not a sum.

    Augment 1 is not offered, and not because of anything here: the imported
    card has no Hit line under its Augment 1 heading, only the Special that
    belongs to the whole power, so there is no clause to write."""
    spent = augment(c, 2)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    if spent:
        c.blinded(until=When.EONT)
        return
    crowd = len([a for a in c.within(1, of=victim, side="ally") if a != c.me])
    if crowd:
        c.penalty("attack", crowd, until=When.EONT)


@power(
    "p2622",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    augments=(
        Augment(1),
        Augment(2, reach=CloseBurst(1), target=EACH_ENEMY),
    ),
)
def p2622(c: Cast) -> None:
    """Augment 2 is a close burst against each enemy you can see, which is a
    header line, so it is declared as one and the swing below is the whole
    of both forms.

    Augment 1 is an Effect, so it is armed whether or not the swing lands,
    and it waits on a **later** use of the class-feature attack the card
    names by ref. It is hung on `Hit` rather than `PowerUsed` because the
    payment is extra damage to whoever that attack hits, and `PowerUsed` is
    announced before the body has chosen anything."""
    spent = augment(c, 1, 2)
    if spent == 1 and c.first:
        me = c.me

        def rider(ev: Hit) -> None:
            if ev.attacker == me and getattr(ev, "power", "") == "p10440":
                c.flat(c.cha_mod, on=ev.target)

        c.watch(Hit, rider, until=When.EONT, label=c.ref)
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.mark(until=When.EONT)


@power(
    "p2623",
    level=1,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p2623(c: Cast) -> None:
    """The stance's own attack is `p2623b`, which has an id of its own now
    that the importer mints one per printed block. It is declared there and
    gated on this stance standing, rather than folded in here as a
    subscription -- folded, it cost no opportunity action, which is the whole
    price the card puts on it."""
    if c.strike():
        c.damage(c.w(3), c.con_mod)
    else:
        c.half_damage(c.w(3), c.con_mod)
    if c.last:
        c.stance()


@power(
    "p2628",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CON, vs=AC),
)
def p2628(c: Cast) -> None:
    """Augment 1 takes the target's threatening reach away, which is a
    penalty cancelling whatever `"reach"` it is carrying -- `c.threatens` can
    only raise it. Augment 2 stops its opportunity attacks outright, which is
    the immunity handed to every creature on the board, the caster included:
    nobody's move gives it an opening."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
    if spent == 2:
        if victim is not None:
            for other in creatures(c.world):
                c.no_provoke(from_=victim, on=other, until=When.EONT)
        return
    c.penalty("attack", 5, until=When.EONT, when=_vs_opportunity)
    if spent and victim is not None:
        held = c.total("reach", victim)
        if held:
            c.penalty("reach", held, until=When.EONT)
