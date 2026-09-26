"""Battlemind, level 9."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CON,
    DAILY,
    FORT,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    SavingThrow,
    UpTo,
    When,
    Window,
    by_melee,
    power,
    spread,
)
from combat_engine.engine.events import MoveStart

from . import PSIONIC_WEAPON, shift_beside, square_of

#: "If either attack hits" spans two calls of the body, which is once per
#: target, so the flag has to live outside it.
_LANDED: set[int] = set()


@power(
    "p11172",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.POLYMORPH],
    attack=Attack(CON, vs=FORT),
)
def p11172(c: Cast) -> None:
    """The second way the penalty ends -- the target finishing a turn without
    attacking -- is dropped; a duration is a `When` and there is no way to add
    a condition to one. The aspect's content is the Augment 1 clause."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
        c.penalty("attack", c.wis_mod, until=When.SAVE_ENDS)
        c.penalty("save", c.wis_mod, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)


@power(
    "p11173",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.POLYMORPH],
    attack=Attack(CON, vs=FORT),
)
def p11173(c: Cast) -> None:
    """"Immune to all damage but psychic" is dropped. `c.resist` takes one
    damage type at a time, so saying it would mean ten separate save-ends
    holds on one creature and ten separate saves to shed them."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)
    else:
        c.stunned(until=When.EONT)


@power(
    "p11174",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=FORT),
)
def p11174(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.con_mod)
        c.push(2)
    else:
        c.half_damage(c.w(3), c.con_mod)
        c.push(1)


@power(
    "p12426",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p12426(c: Cast) -> None:
    """The stance's move-action power shares this id, so it cannot be a second
    `@power`, and walking through a marked enemy's space is not something
    `c.shift` can be told to do. Dropped."""
    if c.strike():
        c.damage(c.w(3), c.con_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage(c.w(3), c.con_mod, dtype=DamageType.FORCE)
    if c.first:
        c.stance()


@power(
    "p13055",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=FORT),
)
def p13055(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.con_mod)
        c.teleport(5, who=c.target)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.con_mod)
        c.dazed(until=When.EONT)


@power(
    "p13056",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    charges=True,
)
def p13056(c: Cast) -> None:
    """The printed damage is 1[W] + 1d6 + Constitution. The dice parser takes
    one term, so the 1d6 is rolled and added as a bonus -- which costs it the
    maximising a critical would otherwise give it."""
    victim = c.target
    if victim is None:
        return
    if c.first:
        _LANDED.discard(c.me)
        c.run_at(victim)
        c.charge = True
    if c.strike():
        _LANDED.add(c.me)
        c.damage(c.w(), c.con_mod + c.roll("1d6"))
    else:
        c.half_damage(c.w(), c.con_mod + c.roll("1d6"))
    if not c.last:
        return
    if c.me in _LANDED:
        spare = [e for e in c.enemies() if e not in c.targets and c.distance(e) <= 1]
        third = c.choose(spare, "the third") if spare else None
        if third is not None:
            if c.strike(on=third, plus=2):
                c.damage(c.w(), c.con_mod + c.roll("1d6"), on=third)
            else:
                c.half_damage(c.w(), c.con_mod + c.roll("1d6"), on=third)
    _LANDED.discard(c.me)


@power(
    "p13057",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(CON, vs=AC),
)
def p13057(c: Cast) -> None:
    """The zone's opportunity attack shares this id and is folded in as a
    subscription. It answers in the interrupt window because the printed
    Effect is "*before* the attack, you shift". The fold loses two things: it
    costs no opportunity action, and the watch expires at the end of the next
    turn rather than following the sustained zone."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if not c.first:
        return
    field = frozenset(spread({c.here}, 2))
    c.zone(field, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def riposte(ev: AttackDeclared) -> None:
        foe = ev.attacker
        if foe == c.me or ev.target == c.me or foe not in c.enemies():
            return
        if square_of(c, foe) not in field or c.here not in field:
            return
        shift_beside(c, max(1, c.speed_of()), foe)
        if c.strike(on=foe):
            c.damage(c.w(), c.con_mod, on=foe)
            c.mark(on=foe, until=When.EONT)

    c.watch(AttackDeclared, riposte, until=When.EONT, on=c.me, window=Window.BEFORE)


@power(
    "p13059",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=FORT),
)
def p13059(c: Cast) -> None:
    """The 2d6 rides on the weakness rather than on a duration of its own, so
    it goes when the target saves. It is rolled per hit, which a `c.bonus`
    could not be."""
    if c.strike():
        c.damage(0, c.con_mod)
        held = c.weakened(until=When.SAVE_ENDS)
    else:
        held = c.weakened(until=When.EONT)
    if held is None:
        return

    def extra(ev: Hit) -> None:
        if ev.attacker == c.me and by_melee(c.world, c.me, ev):
            c.flat(c.roll("2d6"), on=ev.target)

    held.subs.append(c.world.bus.on(Hit, extra, owner=c.me))


@power(
    "p2636",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.STANCE],
    attack=Attack(CON, vs=WILL),
)
def p2636(c: Cast) -> None:
    """The stance's opportunity attack shares this id and is folded in. The
    forced failure answers `SavingThrow` in the interrupt window, since the
    event is announced before it is acted on."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
    else:
        c.half_damage(c.w(), c.con_mod)
    c.ongoing(5, DamageType.PSYCHIC, until=When.SAVE_ENDS)
    if not c.last:
        return
    held = c.stance()

    def riposte(ev: MoveStart) -> None:
        who = ev.actor
        if ev.kind_ != "walk" or c.turn_of() != who:
            return
        if not c.adjacent(who) or not c.marked(on=who):
            return
        if not c.strike(on=who):
            return
        c.damage(c.w(), on=who)

        def botch(sv: SavingThrow) -> None:
            if sv.actor == who:
                c.unsave(sv)

        c.watch(
            SavingThrow, botch, until=When.EOT, on=c.me, once=True, window=Window.BEFORE
        )

    held.subs.append(
        c.world.bus.on(MoveStart, riposte, owner=c.me, window=Window.BEFORE)
    )


@power(
    "p2638",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p2638(c: Cast) -> None:
    """The power points regained on a hit and on a miss are dropped: there is
    no pool to put them back into."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.dazed(until=When.EONT)
    else:
        c.half_damage(c.w(), c.con_mod)
