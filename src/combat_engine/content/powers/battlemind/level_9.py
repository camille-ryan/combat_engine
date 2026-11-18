"""Battlemind, level 9."""

from __future__ import annotations

from combat_engine.content.powers.augment import one_hit_rider
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
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    UpTo,
    When,
    by_melee,
    power,
    spread,
)

from . import PSIONIC_WEAPON

#: "If either attack hits" spans two calls of the body, which is once per
#: target, so the flag has to live outside it.
_LANDED: set[int] = set()


@power(
    "p11172",
    dropped=("Effect.ends_on_a_quiet_turn",),
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
    attacking -- is dropped; a duration is a `When` and there is no way to
    add a condition to one.

    **The marker was renamed rather than retired.** It read
    `c.offer_augment()`, which named the aspect half, and that half is
    written now: `every=True` lends the Augment 1 to every augmentable
    battlemind at-will, which is what the card describes. What is still
    missing is the quiet-turn ender, so the marker says that instead -- one
    symbol, one gap.

    The shift is "before or after the attack", and the clause runs at the
    moment the points are spent, which is before. That is one of the two
    printed orders and the row takes it rather than asking, because the
    choice is only visible when the shift would change what is in reach --
    and a row that asks on every augmented swing is noise on the other 90%.
    """
    if c.strike():
        c.damage(c.w(2), c.con_mod)
        c.penalty("attack", c.wis_mod, until=When.SAVE_ENDS)
        c.penalty("save", c.wis_mod, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)

        wis = c.wis_mod

        def aspect(use: Cast) -> None:
            # **The permission is exactly as long as the shift**, which
            # is what the card says and what `f3224b` could not do: that
            # row phases until the end of the turn and argues no wall is
            # in reach of a close burst 1. Half a speed is three or four
            # squares, so the same argument does not hold here, and
            # `c.may_enter` waives bodies without waiving walls.
            through = use.may_enter(side="enemy", on=use.me)
            use.shift(max(1, use.speed_of() // 2), who=use.me)
            use.end_effect(through)
            one_hit_rider(use, wis, "p11172")

        c.lend_augment("battlemind", 1, aspect, every=True, on=c.me,
                       until=When.ENCOUNTER)


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
    dropped=("c.resist(onto=)",),
)
def p11173(c: Cast) -> None:
    """**"Immune to all damage but psychic" is written now, as ONE hold.**

    The old note said `c.resist` "takes one damage type at a time, so
    saying it would mean ten separate save-ends holds on one creature and
    ten separate saves to shed them". It does not: `c.resist(amount,
    None)` "shrugs off `amount` of **every** hit", and its `when=` is
    handed the damage context -- `source`, `power`, `dtype` -- so "but
    psychic" is a gate on the type rather than nine separate holds.

    `9999` is the tree's immunity idiom, as `monsters/level_10` uses it.
    `c.resist(immunity=)` is the accurate symbol a warlock row's marker
    names, and this does not wait for it: the number says the same thing
    and the gate is what the card actually turns on. #1341.

    **"(save ends both)" is two saves here, not one, and that is the half
    still owed.** `c.bonus` takes `onto=` to add a modifier to an existing
    hold and `c.resist` does not, so the stun and the immunity are two
    effects on the same clock rather than one effect with two clauses. The
    marker names it. A creature could therefore shed one and keep the
    other, which is a real divergence from the card and is why it is
    recorded rather than left to be noticed.
    """
    victim = c.target
    clock = When.SAVE_ENDS if c.strike() else When.EONT
    c.stunned(until=clock)
    # **`on=victim` and not the default.** `c.resist` defaults to the
    # CASTER, like `c.conceal` -- so written without it this row made the
    # battlemind immune and left the target untouched, which measured as
    # 10 fire damage landing on a creature the card says cannot be hurt
    # by it.
    c.resist(
        9999, None, on=victim, until=clock,
        # **The resist context carries the type as a STRING**, where the
        # damage context carries the enum: `resolve.py` builds
        # `{**dmg_ctx, "dtype": dtype.value, "dtypes": types}` for this
        # read. So `is not DamageType.PSYCHIC` is true of every string and
        # resisted psychic too -- measured, 10 psychic landing for 0 on a
        # creature the card says it should hurt.
        #
        # `dtypes` and not `dtype`, for the reason `themes/batch_e.py`
        # records: a fire-and-radiant burn is both, and asking the single
        # key would miss one of them.
        when=lambda ctx: DamageType.PSYCHIC.value not in (
            ctx.get("dtypes") or (ctx.get("dtype"),)
        ),
    )


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
    """The stance's move-action power is `p12426b`, and it is **declared,
    written and firing** -- `second_card.py`, reached through
    `requires=active("p12426")` like the other five of its family, so the
    stance hands it over by standing rather than by `c.grant_row`.

    This used to admit a dropped clause here, because the force damage is
    owed for a square the shift passes *through* and a shift was one `step`
    to its destination. That was true when written; `#684` made
    `movement.shift` walk its path, and the note outlived the fix by long
    enough to be counted as a dropped clause twice -- here and in that
    file's header.

    **The admission is described rather than quoted**, which is the second
    correction this needed: `blocked.py --prose` matches a substring, so a
    note reproducing the phrase in order to say it no longer applies reads
    exactly like a row that still admits it. `p10291` and `p13126b` each
    needed the same edit twice over. #1341.
    """
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
    """The zone's opportunity attack is `p13057b`, declared on its own now
    that the second printed block has an id and gated on the battlemind
    standing inside this zone. Folded in here it cost no opportunity action
    and expired with the next turn rather than following the sustain."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        c.zone(
            frozenset(spread({c.here}, 2)),
            label=c.ref,
            until=When.SUSTAIN,
            sustain=MINOR,
        )


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
    could not be.

    The dice-free Hit line stays `c.damage` -- it is the attack's own damage
    roll, so the weapon's enhancement belongs to it. The 2d6 below is a rider
    on somebody else's attack and is `c.flat`, which is the distinction. #1225."""
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
    """The stance's opportunity attack is `p2636b`, declared on its own now
    that the second printed block has an id."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
    else:
        c.half_damage(c.w(), c.con_mod)
    c.ongoing(5, DamageType.PSYCHIC, until=When.SAVE_ENDS)
    if c.last:
        c.stance()


@power(
    "p2638",
    dropped=("c.gain_points()",),
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
    """The regained power points are still dropped, and **the old reason
    was false**: there is a pool. `PowerPoints` carries `points` and
    `maximum`, `c.spend_points` takes from it and `pool.refresh()` fills
    it. #1341.

    What is missing is the giving-back half. `PowerPoints.spend` clamps
    at `max(0, ...)`, so `c.spend_points(-2)` is not a loophole, and
    content reaching into the component to add to `points` by hand would
    be the one row in the tree doing its own bookkeeping on a pool five
    other readers share.

    So this wants `c.gain_points`, the mirror of the verb already there.
    """
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.dazed(until=When.EONT)
    else:
        c.half_damage(c.w(), c.con_mod)
