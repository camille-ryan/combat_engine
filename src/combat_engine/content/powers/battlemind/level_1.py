"""Battlemind, level 1."""

from __future__ import annotations

from typing import Any

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
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Moved,
    MoveEnd,
    TurnEnd,
    UpTo,
    When,
    Window,
    power,
)
from combat_engine.engine.events import MoveStart

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
    """Base form. Augment 1 (fire resistance 5 + Wisdom instead) and Augment 2
    (2[W]) are dropped: no power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
    if c.first and c.wis_mod > 0:
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
)
def p11157(c: Cast) -> None:
    """Base form. Augment 1 (+1 reach) and Augment 2 (a blast against each
    enemy in it) are dropped: no power points."""
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
    """The aspect is a hold with no content of its own -- everything it grants
    is the Augment 1 clause (temporary hit points, and Wisdom extra damage on
    an augmented at-will), which is dropped for want of power points."""
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
)
def p12419(c: Cast) -> None:
    """Base form. Augment 1 (a burst, and only one enemy shoved) and Augment 2
    (prone as well) are dropped: no power points."""
    if not c.strike():
        return
    c.damage(c.w(), c.con_mod, dtype=DamageType.FORCE)
    blast = c.area()
    caught = c.in_squares(blast, side="enemy") if blast else c.within(3, side="enemy")
    for other in caught:
        if other != c.target:
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
    """Base form. Augment 1 (the same on a shift to a square beside an ally)
    and Augment 2 (2[W]) are dropped: no power points."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod, dtype=DamageType.LIGHTNING)

    def recoil(ev: Hit) -> None:
        if ev.attacker == victim and ev.target in c.allies():
            c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=victim)

    c.watch(Hit, recoil, until=When.SONT, on=victim)


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
)
def p13027(c: Cast) -> None:
    """Base form. Augment 1 (mark an enemy beside the target too) and Augment 2
    (a burst, with an attack penalty) are dropped: no power points."""
    if c.strike():
        alone = len(c.targets) == 1
        c.damage(c.w() if alone else 0, c.con_mod, dtype=DamageType.PSYCHIC)
        c.mark(until=When.EONT)


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
    """Base form. Augment 1 and 2 turn the step into a teleport; both are
    dropped for want of power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.shift(1)


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
    """The aspect's resist 5 cold is its whole unaugmented content; the
    Augment 1 clause (adjacent enemies slowed) is dropped."""
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
    """Base form. Augment 1 (use it for an opportunity attack) and Augment 2
    (blinded) are dropped. The penalty is counted when the blow lands rather
    than recounted per roll -- a modifier holds a number, not a sum."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
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
)
def p2622(c: Cast) -> None:
    """Base form. Augment 1 (extra damage on a later mind spike) and Augment 2
    (a burst) are dropped: no power points."""
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
    """The stance's own attack shares this row's id, so it cannot be a second
    `@power`; it is armed as a subscription hung on the stance, which ends
    with it. `MoveStart.kind_` tells a walk from a shift, and it is
    the right end of the move: an opportunity attack interrupts, and by
    `MoveEnd` the enemy is no longer adjacent, so the check would be false
    exactly when the row should fire. The fold costs no opportunity action,
    which is the one thing it loses."""
    if c.strike():
        c.damage(c.w(3), c.con_mod)
    else:
        c.half_damage(c.w(3), c.con_mod)
    if not c.last:
        return
    held = c.stance()

    def riposte(ev: MoveStart) -> None:
        who = ev.actor
        if ev.kind_ != "walk" or c.turn_of() != who:
            return
        if not c.adjacent(who) or not c.marked(on=who):
            return
        if c.strike(on=who):
            c.damage(c.w(2), c.con_mod, on=who)

    held.subs.append(
        c.world.bus.on(MoveStart, riposte, owner=c.me, window=Window.BEFORE)
    )


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
    """Base form. Augment 1 (loses threatening reach) and Augment 2 (no
    opportunity attacks at all) are dropped: no power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 5, until=When.EONT, when=_vs_opportunity)
