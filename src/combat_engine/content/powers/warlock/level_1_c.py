"""Warlock, level 1: the rows from the books after the first, part two.

The conventions `level_1_b.py` sets out hold here too, and **all three
of the ones this sentence used to name were false** -- the class carries
eight pact legs rather than two, `c.damage` takes `dtypes` for a line
printing two, and `c.restore_use` is the refund for "you do not expend
this power". Read that header rather than this summary of it; the rows
below still carry the old premise in places. #1346.

Two shapes are new to this half.

`_missed_after` is how "the target makes a basic attack, and if it misses it
takes damage" is read: `c.grant_attack` returns whether the swing *happened*
and not whether it landed, so the `Miss` is caught off the bus for the
length of the call.

A curse is relational -- `c.cursed` asks whether *this* warlock cursed that
creature -- so a row whose printed Target is "each creature under your
curse" declares the restriction in the target's label, the reading
`level_1.py` uses for a target it cannot filter, rather than gating the body
on a state the board never reaches.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.query import distance_between, team

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_CRIT_OR_SAVE = "an enemy within 10 squares scores a critical hit or saves"


def _enemy_near(world: World, me: int, who: int | None) -> bool:
    return (
        who is not None
        and team(world, who) is not team(world, me)
        and distance_between(world, who, me) <= 10
    )


def _enemy_crit(world: World, me: int, ev: Event) -> bool:
    return bool(getattr(ev, "critical", False)) and _enemy_near(
        world, me, getattr(ev, "attacker", None)
    )


def _enemy_saved(world: World, me: int, ev: Event) -> bool:
    return bool(getattr(ev, "saved", False)) and _enemy_near(
        world, me, getattr(ev, "actor", None)
    )


def _missed_after(c: Cast, who: int, mark: int) -> bool:
    """Hand `who` a basic attack at `mark` and say whether it missed.

    `c.grant_attack` answers whether the swing was taken, which is a
    different question -- so the `Miss` is watched for over the one call.
    """
    missed = [False]

    def note(ev: Miss) -> None:
        if ev.attacker == who:
            missed[0] = True

    sub = c.world.bus.on(Miss, note)
    try:
        c.grant_attack(who, on=mark)
    finally:
        c.world.bus.off(sub)
    return missed[0]


@power(
    "p1868",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(20),
    target=Target("enemy", everyone=True, label="Each creature in the burst under your curse"),
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p1868(c: Cast) -> None:
    """No ability modifier on the damage, which is what the printed line
    says -- the base line, that is.

    **The dark rider is written now**, and the leg was always there:
    `BUILDS` carries eight, not the two the old header claimed. #1346.
    It adds Intelligence as *extra damage*, which is the same necrotic
    blow made larger rather than a second packet, so it rides the bonus
    argument of the one `c.damage` call.

    The body runs once per creature in the burst and `c.build` asks about
    the **caster**, so the rider is re-asked per target and answers the
    same each time, which is right: one pact, every target.
    """
    if c.target is not None and c.strike():
        extra = c.int_mod if c.build("dark") else 0
        c.damage("2d8", extra, dtype=DamageType.NECROTIC)


@power(
    "p1881",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p1881(c: Cast) -> None:
    """The ally is bled first, because the bonus it buys is on this roll."""
    friends = sorted(c.within(1, side="ally"))
    paid = False
    if friends and c.may("bleed an ally", who=c.me):
        who = c.choose(friends, f"{c.ref}: which ally pays")
        if who is not None:
            c.flat(c.cha_mod, on=who)
            paid = True
    if c.strike(plus=2 if paid else 0):
        c.damage("3d8", c.cha_mod)
        if paid and c.cha_mod > 0:
            c.ongoing(c.cha_mod, DamageType.POISON)
    else:
        c.half_damage("3d8", c.cha_mod)


@power(
    "p1918",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p1918(c: Cast) -> None:
    """The spread is hung off the target's first *failed* save.

    `SavingThrow` names who rolled and whether it stood, but not which of
    several holds was being answered, so the latch is on the first failure
    of any -- which for a creature carrying only this one is the printed
    line exactly.
    """
    victim = c.target
    if not c.strike():
        c.ongoing(5, DamageType.POISON)
        return
    burn = c.ongoing(10, DamageType.POISON)
    if victim is None or burn is None:
        return
    spread_ = [False]

    def failed(ev: SavingThrow) -> None:
        if spread_[0] or ev.actor != victim or ev.saved:
            return
        spread_[0] = True
        for foe in c.within(2, of=victim, side="enemy"):
            if foe != victim:
                c.ongoing(5, DamageType.POISON, on=foe)

    burn.subs.append(c.world.bus.on(SavingThrow, failed))


@power(
    "p3403",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p3403(c: Cast) -> None:
    # "At maximum hit points" is asked before the arrow lands, not after.
    dice = "1d12" if c.missing() == 0 else "1d8"
    if c.strike():
        c.damage(dice, c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p3404",
    level=1,
    dropped=("dsl.Power.range_from_build",),
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.POISON],
    attack=Attack(CHA, vs=REF),
)
def p3404(c: Cast) -> None:
    """The advantage is read off the roll that was made, not asked again: a
    one-shot grant has been spent by then.

    **The dark rider is marked rather than written, and the old reason was
    wrong.** "No leg" was false -- `c.build("dark")` answers. The real
    obstacle is *when*: "the range is 10 instead of 5" has to hold while
    the engine picks targets, and targeting is settled from the header
    before this body is entered. A `c.bonus("range", 5)` laid here would
    widen the **next** use of the row and not this one, which is a
    different card and a worse bug than the missing clause.

    So it waits for a way to say a range from a build at declaration
    time. #1346.
    """
    shot = c.strike()
    if not shot:
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.FORCE)
    if shot.advantage:
        c.flat(c.int_mod, dtype=DamageType.POISON)


@power(
    "p4051",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=WILL),
)
def p4051(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
        c.slowed()


@power(
    "p4052",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CON, vs=FORT),
)
def p4052(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage("2d6", c.con_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    gone = [False]

    def stepped(ev: MoveEnd) -> None:
        if gone[0] or ev.actor != victim:
            return
        gone[0] = True
        # Rolled rather than dealt through `c.damage`, which would take the
        # maximum if this row's own hit happened to be a critical.
        c.flat(c.roll("2d6"), dtype=DamageType.COLD, on=victim)
        if c.build("infernal"):
            c.bonus("attack", 2, on=c.me, kind="power", until=When.EONT, once=True)

    c.watch(MoveEnd, stepped, until=When.EONT)


@power(
    "p4055",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
    trigger=_CRIT_OR_SAVE,
    on=(
        Trigger(Hit, when=_enemy_crit, text="an enemy within 10 squares scores a critical hit"),
        Trigger(SavingThrow, when=_enemy_saved, text="an enemy within 10 squares saves"),
    ),
)
def p4055(c: Cast) -> None:
    """**"It cannot save against this until it has taken the ongoing damage
    at least once" is written now.** The old note said `c.unsave` "answers
    a save being rolled now, and nothing holds a saving throw back" --
    and answering the save being rolled now is enough: a save that cannot
    yet succeed is a save that automatically fails, which is what
    `c.unsave` is for ("it automatically fails"). #1341.

    So the clause is a latch rather than a gate. The ongoing damage
    landing once opens it; until then every save against this is failed
    for the creature. `"ongoing" in ev.detail` is how `p9411` tells its
    own tick from an ordinary blow.
    """
    victim = c.target
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.penalty("save", 2, until=When.SAVE_ENDS)
    c.ongoing(5, DamageType.PSYCHIC)
    if victim is None:
        return
    burned: list[bool] = []

    def tick(ev: DamageApplied, v: int = victim) -> None:
        if ev.target == v and "ongoing" in (ev.detail or ""):
            burned.append(True)

    def too_soon(ev: SavingThrow, v: int = victim) -> None:
        if getattr(ev, "actor", None) == v and not burned:
            c.unsave(ev)

    c.watch(DamageApplied, tick, until=When.ENCOUNTER)
    c.watch(SavingThrow, too_soon, until=When.ENCOUNTER)


@power(
    "p4062",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=WILL),
)
def p4062(c: Cast) -> None:
    """The fall is an Effect line and lands either way; the hit is what stops
    the target getting up again."""
    if c.strike():
        c.damage("3d6", c.con_mod, dtype=DamageType.FIRE)
        c.prone(held=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.con_mod, dtype=DamageType.FIRE)
        c.prone()


@power(
    "p4170",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CON, vs=FORT),
)
def p4170(c: Cast) -> None:
    """**The vestige rider is written now** -- `c.build("vestige")`, and
    the leg was always there. #1346.

    "**Cumulative**" is the whole difficulty and it is why this keeps its
    own running total. `c.temp_hp` takes the **larger** of what you have
    and what is offered, which is how temporary hit points normally work
    and the opposite of what this card says. Handing it 3 once per target
    would therefore leave 3 after three hits.

    So the tally is kept on the `Cast` and the *total* is offered each
    time -- 3, then 6, then 9, each larger than the last, so the max rule
    hands back exactly the sum. `shared.augmenting` keeps its own spend
    on the `Cast` for the same reason: `dsl.use` builds one per use, and
    a body that runs once per target has nowhere else to remember.

    What this does **not** do is add to temporary hit points from some
    other source, which a strict reading of "cumulative" might want. That
    is a question about the stacking rule rather than about this row, and
    it is not invented here.
    """
    if c.target is None or not c.strike():
        return
    c.damage("3d4", c.con_mod, dtype=DamageType.THUNDER)
    c.condition(Condition.DEAFENED)
    if c.build("vestige"):
        running = getattr(c, "vestige_temp", 0) + 3
        c.vestige_temp = running
        c.temp_hp(running)


@power(
    "p4277",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p4277(c: Cast) -> None:
    """**The star rider is written now** -- `c.build("star")`, and the leg
    was always there. #1346.

    "The **next** saving throw it makes **before the end of the
    encounter**" is two words doing two jobs: `once=True` spends the
    penalty on the first save attempted, and `When.ENCOUNTER` is how long
    it waits for one. Either alone is a different card -- without `once`
    it would dog every save of the fight, and without the long clock it
    would lapse before the target rolled.

    It hangs on the target rather than the caster, which `on=` has to say:
    `c.penalty` lays on the caster by default.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
    if c.build("star") and victim is not None:
        c.penalty("save", 2, on=victim, until=When.ENCOUNTER, once=True)


@power(
    "p4278",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p4278(c: Cast) -> None:
    """**"It treats all its enemies as concealed" is written now.** The old
    note said concealment "is a property of the creature being looked at,
    and there is nothing that grants it to a whole side from the looker's
    end". The first half is true and is exactly why this works: the
    concealment is laid on the lookers' *targets* -- the warlock's own side
    -- and `c.conceal(when=)` is handed the attack context, so it applies
    only when the dazed creature is the one attacking. #1341.

    "Until it saves from its dazed condition" is the same save-ends clock
    as the daze, so both carry `When.SAVE_ENDS` rather than the
    concealment being chained to the daze ending.
    """
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
        if victim is not None:
            for mine in [c.me, *(a for a in c.allies() if a != c.me)]:
                c.conceal(
                    on=mine,
                    until=When.SAVE_ENDS,
                    when=lambda ctx: ctx.get("attacker") == victim,
                )
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p4279",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p4279(c: Cast) -> None:
    """Sustaining shoots again, at anybody in range rather than at the one
    first hit, which is what "any target in range" says."""
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.RADIANT)
        if c.bloodied():
            c.blinded()

    def again() -> None:
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 10)
        mark = c.choose(pool, f"{c.ref}: who the light finds") if pool else None
        if mark is not None and c.attack(c.cha_, WILL, on=mark):
            c.flat(c.cha_mod, dtype=DamageType.RADIANT, on=mark)

    beam = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=MINOR
    )
    c.on_sustain(beam, again)


@power(
    "p5902",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p5902(c: Cast) -> None:
    # The star pact rider would make the push 1 + Intelligence modifier.
    if c.target is not None and c.strike():
        c.damage("1d8", c.con_mod)
        c.push(2)


@power(
    "p5903",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CON, vs=REF),
)
def p5903(c: Cast) -> None:
    """Only the penalty to saves is written. "Cannot regain hit points" and
    "cannot gain temporary hit points" have no method -- `c.half_healing` is
    the nearest and it halves rather than forbids, which is a different and
    much weaker card."""
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.NECROTIC)
        c.penalty("save", 2)


@power(
    "p5904",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p5904(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod)
        c.slowed()
        c.grants_advantage()


@power(
    "p5905",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p5905(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.slide(2)  # an Effect line, taken before the attack as printed
    if not c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        return
    near = sorted(w for w in c.within(1, of=victim) if w != victim)
    mark = c.choose(near, f"{c.ref}: who it swings at") if near else None
    if mark is not None and _missed_after(c, victim, mark):
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)


# `p6855` is **the same printed card** as `cf:warlock-f1c11`, and is declared
# there -- which is the leg's own ref, the one the vestige pact grants and the
# one `api/wire.py` reaches as `cf:{cls}-{leg}`. Camille's call, asked
# directly, 2026-11-01, choosing between this and a seventh marker:
#
#     "Declare one side only"
#
# **80 printed cards are reachable under two refs and 78 already declare one
# side only**, so this is the norm rather than a special case; declaring both
# was the anomaly. `twins.py --declared-twice` is the gate that found the two
# that did, and its waiver for this cluster is gone with the declaration --
# the cluster no longer forms.
#
# Why this side and not the other: the body here was the poorer of the two,
# and it declared **no pact gate**, so `chargen` dealt it to 52% of infernal
# and 58% of dark hands and **0%** of vestige hands -- the one leg whose
# remnant its augment lines are keyed to. The exclusion was backwards.
#
# It could not be fixed by declaring the prerequisite, which is the reading
# to resist: `chargen.meets` is build-time and reads an imported tree, while
# `Power.requires` is "asked mid-fight of a creature on a board", so a gate
# here would have refused the card in play to a warlock already holding it.
# Powers have no prerequisite column at all -- `#1044`. `#1043`.


@power(
    "p6856",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p6856(c: Cast) -> None:
    """**This row's pact boon is written now.** It was dropped as having "no
    leg to ask for", and the leg was always there -- `BUILDS` carries
    eight. The boon itself lives in `features.warlock._granted_boon`,
    with the other seven, because `cf:warlock-f1c12` is the card that
    asks which remnant is active and pays it, and a boon fires long
    after this body has finished. The leg offers this remnant to a
    warlock that `c.knows` this row. #1346.

    **The `p6855` augment this card also prints is NOT written.** That
    is a second clause with a second home -- `_vestige_augment`, keyed
    the same way -- and `p6855` is the same card as `cf:warlock-f1c11`
    under a second compendium id. #1348.
    """
    extra = c.int_mod * len(c.within(1, side="ally"))
    if c.strike():
        c.damage("1d8", c.con_mod + extra)
    else:
        c.half_damage("1d8", c.con_mod + extra)


@power(
    "p6857",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CON, vs=REF),
)
def p6857(c: Cast) -> None:
    """"Cannot walk or run" is written as immobilised, which is the nearest
    card: it also stops a shift, which the printed line leaves alone.

    **This row's pact boon is written now.** It was dropped as having "no
    leg to ask for", and the leg was always there -- `BUILDS` carries
    eight. The boon itself lives in `features.warlock._granted_boon`,
    with the other seven, because `cf:warlock-f1c12` is the card that
    asks which remnant is active and pays it, and a boon fires long
    after this body has finished. The leg offers this remnant to a
    warlock that `c.knows` this row. #1346.

    **The `p6855` augment this card also prints is NOT written.** That
    is a second clause with a second home -- `_vestige_augment`, keyed
    the same way -- and `p6855` is the same card as `cf:warlock-f1c11`
    under a second compendium id. #1348.
    """
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.THUNDER)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.con_mod, dtype=DamageType.THUNDER)
        c.immobilized()


@power(
    "p7402",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    basic="melee",
)
def p7402(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        c.slide(1)


@power(
    "p7428",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p7428(c: Cast) -> None:
    """Sustaining squeezes whatever is still held. The minor action the
    printed line offers *after* sustaining -- one more attack on a creature
    beside somebody already caught -- is a second action on the same turn
    and has nowhere to go here.

    "Use your Fortitude or Reflex to escape" is the grab's own arithmetic
    and is not reachable from a row.
    """
    if c.target is not None and c.strike():
        c.damage("1d6", c.cha_mod)
        c.grab()
    if not c.last:
        return

    def squeeze() -> None:
        for foe in c.enemies():
            if c.is_(Condition.GRABBED, foe):
                c.damage("1d6", c.cha_mod, on=foe)

    hold = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=STANDARD
    )
    c.on_sustain(hold, squeeze)
