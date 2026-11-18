"""Assassin, level 1.

The class's signature resource -- the shrouds it stacks on a victim -- has
no representation in the engine: nothing counts them, nothing applies them,
and no `Cast` method names them. Where a row's shroud clause is a rider on
top of a complete attack it is dropped and said so in the docstring; where
it is the whole of the row, the row is not here at all.

The two builds are the class table's two secondaries: `second-cha` is the
one whose rider keys off Charisma, `second-con` the one whose rider keys off
Constitution.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    When,
    power,
)
from combat_engine.engine.events import PowerUsed

SHADOW_WEAPON = [Keyword.SHADOW, Keyword.WEAPON]


@power(
    "p9403",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.IMPLEMENT, Keyword.FORCE],
    attack=Attack(DEX, vs=FORT),
)
def p9403(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.dex_mod, dtype=DamageType.FORCE)
        c.pull(2)
        c.slowed(until=When.EONT)


@power(
    "p9404",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9404(c: Cast) -> None:
    """"Melee weapon +2 reach" is written as a reach of 3 -- the header takes
    a number, not a weapon-relative offset. No ability modifier on the damage,
    as printed."""
    if c.strike(ignore_cover=True):
        c.damage(c.w())


@power(
    "p9405",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9405(c: Cast) -> None:
    """**The old note was wrong about the reason and the clause is still
    dropped, now with the marker and the real reason.**

    "Shrouds are not modelled, so there is no count to read" is false:
    `c.shroud` lays them, `c.shrouds` counts them, `c.spend_shrouds`
    invokes them. What is actually in the way is that **invoking is not
    optional here.** `p9400` watches every `Hit` and `Miss` by the assassin
    and calls `c.spend_shrouds()` unconditionally, so by the time this
    row's own clause could look, the count is always 0.

    Measured: four shrouds planted on the target, `c.shrouds` reads 4,
    `use(p9405)` lands, `c.shrouds` reads 0. A version of this clause that
    reads the count after the strike is dead code that always pays nothing
    -- which is what the first attempt at it was.

    **The clause is written, and the referral was the right call: the fix
    was in `p9400` rather than here.** That row invoked the shrouds on
    every attack and its note said the printed "all or none" choice
    *"is always taken -- declining wins nothing"*, which is true of that
    row alone and false of the class, because this row rewards declining.
    So the count was always 0 by the time this clause could look.

    `p9400` asks `c.may("invoke your shrouds")` before the roll now, as
    its card says, and the count survives a decline -- which is what makes
    this readable.

    **Read AFTER the strike, and a guard on "were they still there" would
    be dead code.** The first draft held the count before the attack and
    paid only if the shrouds survived it -- which reads as the careful
    version and is untestable: `p9400`'s watch clears the count *during*
    `c.strike()`, so by the time the clause looks, the count is 0 on the
    invoked arm whether or not anything guards it. Planting the guard away
    changed **nothing** -- blows `[7, 9, 6]` either way, measured -- which
    is the tell that it was belt-and-braces rather than a rule.

    So the count is simply read after the strike. It is the number of
    shrouds *still on the target*, which is zero exactly when they were
    invoked and the printed count when they were not -- the sentence "if
    you didn't invoke your shrouds ... 1 extra damage for each of your
    shrouds on it" stated once rather than twice.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        # Zero when `p9400`'s watch invoked them during the strike, the
        # printed count when the choice was declined. No guard needed --
        # see the docstring.
        left = c.shrouds(victim) if victim is not None else 0
        if victim is not None and left:
            c.flat(left, on=victim)


@power(
    "p9406",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9406(c: Cast) -> None:
    """"Each creature adjacent to the target" counts everybody but the target
    itself, the caster included -- which is the printed sentence."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        crowd = len([e for e in c.within(1, of=victim) if e != victim])
        c.damage(c.w(), c.dex_mod + crowd)


@power(
    "p9407",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9407(c: Cast) -> None:
    """The invisibility is unconditional here: "while within 2 squares of the
    target" would need a distance gate on `c.invisible`, which takes none."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.invisible(to=c.target, on=c.me, until=When.EONT)


@power(
    "p9408",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9408(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.EONT)
        if c.build("f1s2") and c.cha_mod > 0:
            c.bonus(
                "damage",
                c.cha_mod,
                on=c.me,
                until=When.EONT,
                when=lambda ctx: ctx.get("target") == victim, kind="power")


@power(
    "p9409",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p9409(c: Cast) -> None:
    """Three rolls resolved as one hit. Each roll goes through `c.strike`, so
    three attacks are announced against the one target; the damage is dealt
    once and sized by how many of them landed."""
    landed = sum(1 for _ in range(3) if c.strike())
    if landed:
        c.damage(f"{landed}d8", dtype=DamageType.COLD)


@power(
    "p9410",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9410(c: Cast) -> None:
    if c.strike():
        extra = c.con_mod if c.build("f1s0") else 0
        c.damage(c.w(2), c.dex_mod + extra)
        c.slowed(until=When.EONT)


@power(
    "p9411",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9411(c: Cast) -> None:
    """The prone rider watches for the ongoing damage landing rather than for
    the save, which is what "whenever the target takes this ongoing damage"
    says.

    **The Effect line is written now.** The old note called it "a bonus
    gated on shrouds" and dropped it for that; the gate is readable --
    `c.shrouds(on=)` is the count -- and `c.bonus(when=)` is handed the
    attack context, so "against the target" and "while your shrouds are on
    it" are both askable at the moment the roll happens. #1341.

    An Effect line, so it lands whether or not the attack did -- which is
    why it sits outside the `c.strike()` branch.
    """
    victim = c.target
    if victim is None:
        return
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER, kind="power",
        when=lambda ctx: (
            ctx.get("target") == victim and c.shrouds(on=victim) > 0
        ),
    )
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.ongoing(5, until=When.SAVE_ENDS)

        def tipped(ev: DamageApplied) -> None:
            if ev.target == victim and "ongoing" in ev.detail:
                c.prone(on=victim)

        c.watch(DamageApplied, tipped, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p9412",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=FORT),
)
def p9412(c: Cast) -> None:
    """"Until the target saves against this power" is read as "while it is
    still immobilized by it" -- the immobilisation is the save-ends hold, so
    the two end together."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )
    else:
        c.half_damage(c.w(), c.dex_mod)
        c.immobilized(until=When.SAVE_ENDS)

    def reel(ev: TurnStart) -> None:
        if ev.actor == c.me and c.is_(Condition.IMMOBILIZED, on=victim):
            c.pull(3, on=victim)

    c.watch(TurnStart, reel, until=When.ENCOUNTER)


@power(
    "p9413",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9413(c: Cast) -> None:
    """**The Effect line is written now.** The old note said "the feature
    does not exist here", and it does: `p9400` is declared, `c.shroud` lays
    a shroud and `c.shrouds` counts them. #1341.

    "Two instead of one" is laid as **one extra** rather than by rewriting
    what `p9400` does, which leaves the class feature's own row alone and
    is the same arithmetic.

    **On `PowerUsed`, not `PowerResolved`, and the difference is the whole
    clause.** `p9400` watches every `Hit` and `Miss` and calls
    `c.spend_shrouds()`, so a shroud added after resolution arrives *after*
    the invoke that was supposed to pay for it. Measured on the first
    attempt: the watcher fired with the right target and the count still
    came out 1, because p9400's own shroud had already been spent and mine
    was simply the next one. `PowerUsed` is before the body, so the pair is
    on the target when the invoke reads it. `c.shroud`'s cap keeps it
    honest at the top end.

    Measured with the shrouds zeroed first, so a board's own leftovers
    cannot be mistaken for the clause:

        p9400 alone                    lays 1
        p9400 with this row standing   lays 2

    True on all three boards of ten where the target survives p9413's own
    attack. On the other seven it dies, and a dead creature carries no
    shrouds -- which is the board, not the clause, and is why the count was
    measured on the survivors rather than averaged over all ten.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.dex_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("3d8", c.dex_mod, dtype=DamageType.COLD)
    if victim is None:
        return

    def doubled(ev: PowerUsed) -> None:
        if ev.power == "p9400" and victim in (ev.targets or ()):
            c.shroud(on=victim)

    c.watch(PowerUsed, doubled, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} doubles")


@power(
    "p9414",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9414(c: Cast) -> None:
    """One header target, so the primary is the declared one and the secondary
    attacks are rolled in the body with `c.strike(on=...)` -- the same attack
    line, which is what the printed secondary is. The primary's "adjacent to
    you" restriction has no header field and is not enforced."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.EONT)
    for other in c.in_squares(c.area(), side="enemy"):
        if other != victim:
            c.push(4 if c.strike(on=other) else 2, on=other)
