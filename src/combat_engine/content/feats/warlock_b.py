"""Warlock feats, the second batch: the curse's damage, the shadow and
the pacts.

Three things decide almost every row here.

**The curse itself is fully modelled and fully nameable.** `c.curse` lays
it, `c.cursed(on=)` reads it back, `cursed_by_me` is the same question
asked of an event, and the relation is *relational* -- two warlocks on a
board read their own curse and not each other's. So "against a creature
you have cursed" is an ordinary gate.

**The curse's extra damage is open, and used to read as closed.**
`cf:warlock-f4` pays through `features/strikers.py:extra_damage`, which
asks `c.dice_for` for the die and adds `c.total("cf:warlock-f4 damage")`
on top. So *adding* to the payout is a modifier (f1121), changing the
dice is `c.change_dice` (f2764), rerolling them is `c.reroll_ones(ref=)`
(f2760), and paying the damage a second time is those same two lines
written again (f1124, f2036). Only one thing in that closure is still
out of reach: the **once-a-round latch**, which is why f2036 settles at
`PowerResolved` rather than guessing whether the feature has paid.

**The pact boon is three holes, not one.** `c.on_pact_boon()` was
carrying all of them. Where the boon's card has a ref -- `p2094` -- the
rider is an ordinary declared trigger and `feats/warlock.py` already
writes three of them (f291, f292, f293); f1358 is the fourth. Where the
row turns on *which* remnant the warlock bargained with, it waits on
`c.active_vestige()` with `cf:warlock-f1s6` and its two cards. Where the
row has to **cause** a boon rather than watch one, it waits on
`c.pact_boon()` with `i698x1` and `i2305p1`. f2193 is the fourth case
and needs nothing: it *replaces* the boon, and a watch armed by
`c.watch` is owned by its effect, so ending that effect disarms the
feature.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    AttackDeclared,
    Cast,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    EffectApplied,
    Healed,
    Hit,
    Keyword,
    Moved,
    PowerResolved,
    PowerUsed,
    SavingThrow,
    SecondWind,
    SurgeSpent,
    Trigger,
    When,
    Window,
    about_me,
    cursed_by_me,
    get,
    power,
)
from combat_engine.engine.components import Health, Position
from combat_engine.engine.grid import spread

#: The class feature that lays the curse, and the name its extra damage
#: reads its bonus under. `extra_damage` pays
#: `c.total(f"{label} damage")`, so a modifier under that key is the one
#: way into the curse's payout.
CURSE = "cf:warlock-f4"
CURSE_DAMAGE = f"{CURSE} damage"

#: The pact boon, and the class feature that grants concealment.
PACT = "cf:warlock-f1"
SHADOW = "cf:warlock-f3"

#: Which remnant a vestige warlock is speaking for. Nothing holds it, so
#: neither the at-will nor the boon it gates can tell which one it is.
#: `cf:warlock-f1s6` and its two cards carry the same symbol.
VESTIGE = ("c.active_vestige()",)
#: A class feature named in prose with no ref -- the vestiges, which are
#: a whole subsystem the engine has never heard of.
FEATURE = ("c.class_feature()",)
#: "Instead of": a printed swap for half of what a class feature does
#: inside its own body. Declining that half is the operation nothing has.
INSTEAD = ("c.pre_empt(ref, clause)",)

#: "Allies who are helpless, stunned, dominated, unconscious, or
#: petrified" -- the list f2762 prints, as conditions.
_OUT_OF_IT = (
    Condition.HELPLESS,
    Condition.STUNNED,
    Condition.DOMINATED,
    Condition.UNCONSCIOUS,
    Condition.PETRIFIED,
)


def _cursed(c: Cast, who: int | None) -> bool:
    """`c.cursed` with the None guard written out.

    `c.cursed(None)` falls back to `c.target`, which on a trait armed at
    the start of a fight is the caster -- so an ungated call asks whether
    the warlock has cursed itself and is false forever.
    """
    return who is not None and c.cursed(who)


def _shadow_concealed(c: Cast) -> bool:
    """Concealment **from Shadow Walk**, not from anywhere.

    `query.concealment_of` answers the wider question and three of these
    feats print the narrower one. `c.conceal` is a modifier and
    `c.bonus` labels what it lays `"<ref> <key><amount>"`, so the class
    feature's own concealment is the one effect on the caster whose
    label opens that way. The bare ref will not do: `cf:warlock-f3`
    also arms two watches, and those are effects with the ref as their
    whole label and last the encounter.
    """
    return any(
        eff.label.startswith(f"{SHADOW} concealment")
        for eff in c.world.effects.of(c.me)
    )


def _warlock_attack(ctx: dict[str, Any]) -> bool:
    """Is the blow being rolled one of this class's attack powers?

    The damage context carries `power`, which is the ref, and the
    registry carries the class -- which is how "with a warlock power" is
    asked without naming any of them.
    """
    p = get(ctx.get("power", "") or "")
    return p is not None and p.cls == "warlock" and p.is_attack


def _burning(c: Cast, who: int | None) -> bool:
    """Is that creature taking ongoing damage, from anybody?

    `c.suffering` only finds holds *I* laid, and the printed sentence
    does not care whose burn it is. `Effect.ongoing` is the field, so
    the live list is read directly.
    """
    return who is not None and any(
        eff.ongoing is not None for eff in c.world.effects.of(who)
    )


def _has_temp_hp(c: Cast, who: int) -> bool:
    return (h := c.world.get(who, Health)) is not None and h.temp > 0


def _next_save(c: Cast, who: int, value: int) -> None:
    """"...to its next saving throw before the end of your next turn."

    `c.bonus(once=True)` is the wrong tool and quietly so. Its spending
    branch for any key that is not `damage`, `crit_range` or a defence
    watches `AttackRolled`, so a one-shot on `save` is spent by the next
    *attack roll* the owner makes and is still standing for the second
    save of the window. The spend is written here against the event that
    actually reads the modifier -- `durations` sums `"save"` and then
    announces `SavingThrow`, so the bonus is applied before this ends it.
    """
    lay = c.bonus if value > 0 else c.penalty
    effect = lay("save", abs(value), on=who, until=When.EONT)
    if effect is None:
        return

    def spent(ev: SavingThrow) -> None:
        if ev.actor == who:
            c.world.effects.end(effect, "spent on that save")

    c.watch(SavingThrow, spent, until=When.EONT, on=who, label=f"{c.ref} save")


def _hit_by_me(world: Any, me: int, ev: Any) -> bool:
    return ev.attacker == me


def _crit_by_me(world: Any, me: int, ev: Any) -> bool:
    return ev.attacker == me and ev.critical


def _melee_hit_on_me(world: Any, me: int, ev: Any) -> bool:
    from combat_engine.engine.triggers import by_melee

    return ev.target == me and ev.attacker != me and by_melee(world, me, ev)


def _used(ref: str):  # noqa: ANN202
    """That named row, used by me. `PowerUsed` is announced *before* the
    body runs, which is what f2293 wants -- it is setting up the blow the
    body is about to roll."""

    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power == ref

    return when


def _failed_my_warlock_effect(world: Any, me: int, ev: Any) -> bool:
    """An enemy failing a save against a hold one of my warlock powers laid.

    `SavingThrow` carries no source of its own, only `against=str(eff)` --
    and that rendering opens with `e<id>`, so it names the effect
    uniquely. Matching it back against the live list on the roller is
    what makes "bestowed by one of **your** powers" askable at all;
    without it the row would have to fire on every failed save in the
    fight. The effect is still live when this is asked, because a failed
    save does not end one.
    """
    from combat_engine.engine.query import team

    if ev.saved or team(world, ev.actor) is team(world, me):
        return False
    for eff in world.effects.of(ev.actor):
        if str(eff) != ev.against or eff.source != me:
            continue
        p = get(eff.label.split(" ")[0])
        return p is not None and p.cls == "warlock"
    return False


def _killed_by_warlock_power(c: Cast, ev: Dropped) -> bool:
    """Was the killing blow dealt by one of this class's rows?

    `Dropped` names its `source` -- who landed it -- and not the row that
    did, so the row is read back off the bus log. `deal_damage` sets
    `DamageApplied.detail` to the ref of whatever dealt the blow and the
    drop is announced from inside that same payment, so the nearest
    earlier `DamageApplied` on the body is the killing one.

    The curse's own extra damage carries `cf:warlock-f4`, which is a
    warlock row, so a kill made by the class feature counts -- it only
    ever rides a warlock attack anyway.
    """
    for past in reversed(c.world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == ev.actor:
            p = get(past.detail or "")
            return p is not None and p.cls == "warlock"
    return False


def _no_ally_nearer(c: Cast, target: int, *, widened: bool) -> bool:
    """Prime Shot's own comparison, said again.

    `features/strikers.py:prime_shot` keeps the rule in a closure and
    nothing reaches in, so the two feats that change it have to restate
    it. Each pays only where its own version is true and the printed one
    is not, so the shared `+1` is never collected twice -- both are
    untyped and would otherwise add.
    """
    from combat_engine.engine.query import alive, allies, distance_between

    world, me = c.world, c.me
    mine = distance_between(world, me, target)
    for mate in allies(world, me):
        if not alive(world, mate):
            continue
        if widened and (
            distance_between(world, me, mate) <= 1
            or any(c.is_(cond, on=mate) for cond in _OUT_OF_IT)
        ):
            continue
        if distance_between(world, mate, target) < mine:
            return False
    return True


# -- the curse's own damage -------------------------------------------------


@power("f1121", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1121(c: Cast) -> None:
    """Adds to the curse's payout while bloodied.

    `extra_damage` rolls the dice and adds `c.total(CURSE_DAMAGE)` on
    top, so a modifier under that key is how a feat reaches inside a
    class feature. It is read with an **empty** context, so a `when=`
    gate cannot narrow on anything the ctx carries -- which costs
    nothing here, because "while you are bloodied" is a question about
    the board and is asked of the board.

    Untyped: the card prints no word in front of "bonus", and it is an
    addition to a damage total rather than a bonus at all.
    """
    me = c.me
    c.bonus(
        CURSE_DAMAGE, 1 + c.str_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(me),
    )


def _pay_curse(c: Cast, victim: int) -> None:
    """The curse's extra damage, dealt on purpose.

    `extra_damage`'s own two lines said again: the die is asked for rather
    than written down, so f2764's d8s are honoured, and whatever f1121 is
    adding comes through `c.total`. Paid under the curse's own `detail`,
    so a rider watching the payout -- f2766's shape -- sees this helping
    too, and so does anything counting them.

    **One divergence, and it is in `_reroll_floor` rather than here.**
    `c.reroll_ones(ref=)` keys on the ref of the row doing the rolling, so
    f2760's reroll covers the class feature's helping and not a feat's.
    Narrowing a reroll by the damage's *label* is what would close that,
    and no card in this file prints it.
    """
    c.damage(
        c.dice_for(CURSE, "1d6", {"target": victim}),
        c.total(CURSE_DAMAGE), on=victim, detail=CURSE,
    )


@power("f1124", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1124(c: Cast) -> None:
    """A second helping of curse damage in a turn bought with an action point.

    A trait with two watches rather than a declared trigger, because the
    printed condition is "you have **already** dealt your curse damage
    during your current turn" -- which has to have been remembered before
    the point is spent, and a declared trigger's body runs only when it
    fires.

    **The once-a-round latch is not reached and does not have to be.** The
    card's own condition is what guarantees the class feature's hold is
    already closed for the round, so the helping armed here is the only one
    left to pay and the two never land on one blow. See `_pay_curse` for
    the payout.
    """
    me = c.me
    dealt: set[int] = set()

    def note(ev: DamageApplied) -> None:
        if ev.source == me and ev.detail == CURSE:
            dealt.add(c.world.round)

    def again(ev: ActionPointSpent) -> None:
        if ev.actor != me or c.world.round not in dealt:
            return
        paid: list[bool] = []

        def second(hit: Hit) -> None:
            if paid or hit.attacker != me or not _cursed(c, hit.target):
                return
            paid.append(True)
            _pay_curse(c, hit.target)

        c.watch(Hit, second, until=When.EOT, on=me, label=f"{c.ref} second")

    c.watch(DamageApplied, note, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} tally")
    c.watch(ActionPointSpent, again, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2036", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2036(c: Cast) -> None:
    """The curse's extra damage on a named card's hit, latch or no latch.

    **Settled at `PowerResolved` rather than on the `Hit`**, and that is
    the whole of why this is writable without reaching the latch. This row
    and `extra_damage` watch the same `Hit` in the same window and nothing
    decides which runs first, so paying blind would double the damage on
    every blow where the feature's hold was still open. Once `f2023b` has
    finished resolving the feature has either paid or not, and a
    `DamageApplied` under the curse's own `detail` is how that is read --
    by sequence, so a payment made *before* the blow cannot be mistaken for
    one made on it. "Even if you have already used your extra curse damage
    this turn" is then the only case left to pay.
    """
    me = c.me
    struck: list[tuple[int, int]] = []
    paid: list[tuple[int, int]] = []

    def landed(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "f2023b" and _cursed(c, ev.target):
            struck.append((ev.target, ev.seq))

    def noted(ev: DamageApplied) -> None:
        if ev.source == me and ev.detail == CURSE:
            paid.append((ev.target, ev.seq))

    def settle(ev: PowerResolved) -> None:
        if ev.actor != me or ev.power != "f2023b":
            return
        for foe, blow in struck:
            if not any(who == foe and at > blow for who, at in paid):
                _pay_curse(c, foe)
        struck.clear()
        paid.clear()

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} hit")
    c.watch(DamageApplied, noted, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} tally")
    c.watch(PowerResolved, settle, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2760", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2760(c: Cast) -> None:
    """Rerolls a 1 on the curse's damage dice.

    `c.reroll_ones` is the verb and `ref=` is the narrowing -- its own
    docstring names the curse damage as what that parameter is for. The
    objection this row carried was that the dice live inside
    `extra_damage`'s closure, which is true of the die *string* and not of
    the roll: the payout goes through `c.damage` on `cf:warlock-f4`'s own
    `Cast`, and `_reroll_floor` is read from there with the dice in hand.

    Default `below=2`, which is "a result of 2 or higher" exactly.
    """
    c.reroll_ones(ref=CURSE)


@power("f2764", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2764(c: Cast) -> None:
    """d8s instead of d6s for the curse.

    The third of the three strikers' identical feats; `extra_damage` reads
    its die through `c.dice_for` now, so all three are the same one line.
    f185 carries the note on why the count is written out."""
    c.change_dice("cf:warlock-f4", "1d8")


@power("f2766", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.raise_ongoing(by)",))
def f2766(c: Cast) -> None:
    """Raises ongoing damage by one per curse die rolled. Word for word
    the rogue's f763 with the other striker feature in it.

    The *announcement* is not the gap: `extra_damage` pays through
    `c.damage(..., detail=label)`, so the payout arrives as a
    `DamageRolled`/`DamageApplied` carrying `cf:warlock-f4`.

    **And the count is not the gap either, which this docstring used to
    say it was.** It read "the die string is a literal closed over inside
    `extra_damage` and nothing publishes how many were rolled" -- true when
    it was written and not since. `pay_extra` asks
    `c.dice_for(label, dice, ...)` for the string (#569 moved it there so a
    feat raising d6s to d8s would be read), and a feat can ask the same
    question and count the dice off the answer.

    What is actually left is raising an **ongoing** amount after it has been
    set, keyed on a payout in the same blow. #619."""


# -- the curse as a target, which is ordinary -------------------------------


@power("f1153", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1153(c: Cast) -> None:
    """A bargain: +1 against what you have cursed, +1 back from it.

    Both halves are asked per attack rather than latched, because a
    curse moves from creature to creature during a fight.

    The drawback is laid on each enemy standing on the board when this
    arms, gated on the curse being live and on the attack being aimed at
    the warlock. A creature that arrives later -- a summon -- misses it;
    that is the cost of a modifier having to live on the attacker, and
    it is said here rather than left to be found.
    """
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _cursed(c, ctx.get("target")),
    )
    for foe in c.enemies():
        c.bonus(
            "attack", 1, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                ctx.get("target") == me and _cursed(c, f)
            ),
        )


@power("f2080", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a bloodied enemy under your curse",
       on=Trigger(Hit, _hit_by_me, "you hit with an attack"))
def f2080(c: Cast) -> None:
    """Both halves of the condition are board questions, so they are
    asked after the blow rather than in the predicate -- a predicate is
    handed no `Cast` and neither `c.cursed` nor `c.bloodied` is a field
    on the event."""
    foe = c.trigger.target
    if _cursed(c, foe) and c.bloodied(foe):
        _next_save(c, foe, -2)


@power("f2761", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit against the target of your curse",
       on=Trigger(Hit, _crit_by_me, "you score a critical hit"))
def f2761(c: Cast) -> None:
    """`Hit.critical` is a declared field, so the crit is in the
    predicate and only the curse is left for the body."""
    foe = c.trigger.target
    if _cursed(c, foe):
        c.teleport(3, who=foe)


@power("f2763", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit against the target of your curse",
       on=Trigger(Hit, _crit_by_me, "you score a critical hit"))
def f2763(c: Cast) -> None:
    """f2761's sibling: the warlock goes rather than the target."""
    if _cursed(c, c.trigger.target):
        c.teleport(4, who=c.me)


@power("f2079", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy fails a saving throw against one of your warlock effects",
       on=Trigger(
           SavingThrow, _failed_my_warlock_effect,
           "an enemy fails a save against an effect of yours",
       ))
def f2079(c: Cast) -> None:
    """A free shift each time one of your holds sticks. See
    `_failed_my_warlock_effect` for how the event is tied back to the
    effect that was rolled against."""
    c.shift(1)


@power("f2085", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2085(c: Cast) -> None:
    """Extra damage to whatever is already burning, whoever set it
    alight. The tier ladder is read off the level rather than written as
    three rows.

    The extra is poison and is carried as poison, so a creature that
    resists poison shrugs it off while the warlock's own damage lands.
    """
    me = c.me
    step = 2 + (c.level >= 11) + (c.level >= 21)
    c.bonus(
        "damage", step, on=me, until=When.ENCOUNTER,
        dtype=DamageType.POISON,
        when=lambda ctx: _warlock_attack(ctx) and _burning(c, ctx.get("target")),
    )


@power("f2286", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2286(c: Cast) -> None:
    """"Any warlock power that uses Constitution for attack rolls" is the
    header's own `Attack.ability`, so the gate reads the registry rather
    than a build flag -- a Constitution warlock still carries the odd
    Charisma row and this must not pay on one."""
    me = c.me
    step = 2 + (c.level >= 11) + (c.level >= 21)

    def con_power(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", "") or "")
        return (
            p is not None
            and p.cls == "warlock"
            and p.attack is not None
            and p.attack.ability is CON
        )

    c.bonus("damage", step, on=me, until=When.ENCOUNTER, when=con_power)


@power("f2083", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2083(c: Cast) -> None:
    """Necrotic *or* poison becomes necrotic *and* poison. `DamageRolled`
    carries the whole type of a blow now, so the pairing is one
    assignment; the creature has to resist both to shrug off any of it,
    which is the point of the feat.

    Written on the roll rather than as a standing `c.deals`, because the
    card narrows to warlock powers and `deals:` is every weapon attack
    the creature makes.
    """
    me = c.me
    pair = (DamageType.NECROTIC, DamageType.POISON)

    def spread(ev: DamageRolled) -> None:
        if ev.source != me or ev.dtype not in pair:
            return
        p = get(ev.detail or "")
        if p is not None and p.cls == "warlock":
            ev.dtypes = pair

    c.watch(DamageRolled, spread, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


# -- the shadow, which is a labelled modifier and so readable ---------------


@power("f1126", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1126(c: Cast) -> None:
    """+1 damage while the class feature's own concealment holds. A plain
    "+1 bonus" with no type word, so untyped."""
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _shadow_concealed(c),
    )


@power("f2082", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2082(c: Cast) -> None:
    """Two skills chosen at training, +2 to checks with them while the
    class feature's concealment holds. The whole printed Benefit is a
    skill bonus, so this is deliberately inert rather than unwritten."""


@power("f2291", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy hits you with a melee attack",
       on=Trigger(Hit, _melee_hit_on_me, "an enemy hits you in melee"))
def f2291(c: Cast) -> None:
    """The reprisal for being caught in the dark.

    The concealment is asked in the body rather than the predicate --
    it is a modifier on the caster and a predicate gets no `Cast` -- and
    it is still standing when this runs, because the feature grants it
    until the end of the warlock's next turn.
    """
    if _shadow_concealed(c):
        c.grants_advantage(on=c.trigger.attacker, until=When.EONT)


# -- the pact boon: four rows and one hole ----------------------------------


@power("f1166", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=VESTIGE)
def f1166(c: Cast) -> None:
    """Swaps the active remnant when the pact boon fires.

    Re-aimed. The boon's moment is not what holds this: `cf:warlock-f1s6`
    is declared, every boon fires off `Dropped` under `cursed_by_me`, and
    `feats/warlock.py` writes three riders that way already. What is
    missing is the thing `cf:warlock-f1s6` and both its cards wait on --
    nothing holds which remnant is active, so there is no state to change
    and no record of the ones held earlier for the card to choose among.
    """


@power("f2035", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=VESTIGE)
def f2035(c: Cast) -> None:
    """Adds a remnant whose boon slides a second cursed creature.

    Re-aimed, and the payout is the half that *is* writable: `Dropped`
    plus `cursed_by_me` is the moment, `c.cursed` finds the others and
    `c.slide` moves one Intelligence modifier of squares. What cannot be
    said is **when** the warlock has it. The boon is printed as the one
    that pays while this remnant is active, so a row that paid it
    unconditionally would hand the warlock a second boon beside the one
    its own leg already pays -- which is `cf:warlock-f1c12`'s argument for
    the same symbol, word for word. The augment line is a clause of that
    remnant's at-will and waits on the same state.

    The old marker's second symbol, `cf:warlock-f4c0`, is stale: the spec
    names `cf:warlock-f4` here and that row is declared.
    """


@power("f1358", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2094",
       on=Trigger(PowerUsed, _used("p2094"), "your pact boon pays"))
def f1358(c: Cast) -> None:
    """Difficult ground left behind a pact teleport.

    **The boon this names is a card with a ref**, `p2094`, and
    `feats/warlock.py` already hangs f291, f292 and f293 off `p2094`,
    `p2095` and `p2263` exactly this way -- so "when your pact boon
    triggers" is an ordinary declared trigger and the symbol this row
    carried was answering a question it never asked.

    `PowerUsed` rather than `PowerResolved`, because the square wanted is
    the one *left*: a `Moved` watch armed before the hop reads `from_` off
    the step itself, which is both the printed words and proof the teleport
    happened at all. `kind_` is asked so that an ordinary walk later in the
    turn cannot spend the watch, and the hand latch is not needed --
    `c.watch(once=True)` means "fire once", measured by whether the handler
    did anything.

    "To everyone but you" is the zone's `difficult` **label** plus
    `c.ignores_difficult` under the same word: a bare `difficult=True`
    labels the squares with the empty string, and an exemption with no kind
    is every sort of rough ground on the board.
    """
    me = c.me

    def behind(ev: Moved) -> None:
        if ev.actor != me or getattr(ev, "kind_", "") != "teleport":
            return
        c.zone(spread({ev.from_}, 1), label=c.ref, difficult=c.ref,
               until=When.SONT)
        c.ignores_difficult(c.ref, on=me, until=When.SONT)

    c.watch(Moved, behind, until=When.EOT, on=me, once=True, label=c.ref)


@power("f2759", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("warlock.pay_boon()",))
def f2759(c: Cast) -> None:
    """Takes the boon early, when a cursed enemy is first bloodied,
    and pays for it with the curse.

    Re-aimed, and the re-aim is the finding. `Dropped` plus `cursed_by_me`
    is how a boon *announces itself*, and this row does not watch a boon --
    it **causes** one, off `Bloodied`, which is the opposite operation and
    was sitting under the same symbol. Both halves of the price are sayable
    (the curse is a labelled hold `Effects.end` would lift); the thing
    bought is not.

    **Re-pointed off `warlock.boon_instead_of()`, which was two gaps under
    one symbol.** That door landed -- each payout now offers itself as the
    clause `features.warlock.BOON` and `f3444` trades the boon away through
    it -- and it does nothing for this row. A substitution replaces a
    payout that is *already firing*; this card asks for the payout to fire
    from an event of its own, which is the opposite direction and needs no
    `c.pre_empt` anywhere in it.

    So: **the boon's payout has to be callable.** Three of the five refs in
    `features.warlock.BOONS` are rows (`c.use_power` would reach those),
    but `cf:warlock-f1` pays its three legs inline inside the watcher it
    installs, so using that row again installs a second watcher and pays
    nothing. A helper in `features/warlock.py` that pays whichever leg the
    character took is what both rows waiting on this want, and it cannot
    be written from here: `features/strikers.py` and
    `powers/warlock/pacts.py` hold the payouts it would have to reach.

    `todo=` rather than `dropped=`: writing only the price -- removing the
    curse -- would make the row strictly worse than not having it.

    `i698x1` is the same gap and carries the same symbol. `i2305p1` is a
    third thing again and carries `c.decline_boon()`. #641.
    """


@power("f2193", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2193(c: Cast) -> None:
    """A pact boon that **replaces** the one the class feature deals.

    Written as a trait rather than with a declared `on=`, because it has
    two jobs and a declared trigger would run the body only when the
    trigger fired -- so the replacing half would never happen at all.

    The replacing is real rather than dropped. `c.watch` hands its bus
    subscription to the effect it creates, and `Effects.end` unsubscribes
    everything an effect holds, so ending `cf:warlock-f1`'s own hold
    disarms the feature it armed. The order traits arm in is
    `Powers.all`'s and not guaranteed, so this both sweeps what is
    already there and watches for the feature arming afterwards.

    "Any enemy within 1 square" is read as each of them: the sentence
    names no chooser and the sibling boon that does say "a different
    creature" says so outright.
    """
    me = c.me

    def unpact() -> None:
        for eff in list(c.world.effects.of(me)):
            if eff.label.startswith(PACT):
                c.world.effects.end(eff, "replaced")

    def armed_late(ev: EffectApplied) -> None:
        if ev.target == me and ev.label.startswith(PACT):
            unpact()

    def payout(ev: Dropped) -> None:
        if ev.actor == me or not c.cursed(ev.actor):
            return
        for foe in c.within(1, of=ev.actor, side="enemy"):
            if foe != ev.actor:
                c.flat(5 + c.level // 2, dtype=DamageType.FIRE, on=foe)
        c.temp_hp(c.level // 2, on=me)

    unpact()
    c.watch(EffectApplied, armed_late, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} sweep")
    c.watch(Dropped, payout, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2192", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2192(c: Cast) -> None:
    """Skill checks for performing a ritual, scaled by milestones. A
    ritual is not a fight and a milestone is not a round, so the whole
    of this is narrative -- deliberately inert, not unwritten."""


@power("f2191", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop an enemy you have cursed",
       on=Trigger(Dropped, cursed_by_me,
                  "an enemy you have cursed drops to 0 hit points"))
def f2191(c: Cast) -> None:
    """Fire in the space where a cursed enemy fell.

    `Dropped` is announced before anything lifts the body off the grid,
    so the square is still readable. `x2_153` is a ref, so it is the
    label the hazard carries; `c.hazard` is the verb for "any creature
    that enters or starts its turn within the square takes damage", and
    the printed duration means it is not sustained.

    "With a warlock attack" is said after all, off the bus log -- see
    `_killed_by_warlock_power`. `Dropped` still carries no `power`, but
    the payment that caused it does, and it is two events back.
    """
    if c.trigger.source != c.me or not _killed_by_warlock_power(c, c.trigger):
        return
    pos = c.world.get(c.trigger.actor, Position)
    if pos is None:
        return
    c.hazard(
        [pos.square], 5 + c.level // 2, DamageType.FIRE,
        label="x2_153", until=When.EONT, sustain=None,
    )


# -- fire, surges and temporary hit points ----------------------------------


@power("f2196", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def f2196(c: Cast) -> None:
    """`resolve.spend_surge` is the one place a surge is decremented and
    it announces `SurgeSpent`, so this is an ordinary declared trigger.

    The printed alternative -- "if you already have fire resistance, you
    can instead increase that resistance by 5" -- is a real choice and is
    written as one. `c.resist` takes the **highest** of the flat pool
    rather than adding to it, so a warlock already resisting 10 gains
    nothing at all from the first arm at heroic and 5 more from the
    second; the old note here said the opposite and was left over from
    when resistances summed.

    `c.resistances` is the reader that makes the comparison possible, and
    the larger of the two arms is taken rather than offered, because
    "you can instead" with both numbers in hand is a choice with an
    answer.
    """
    me = c.me
    amount = 5 + c.level // 2
    already = c.resistances(on=me).get(DamageType.FIRE, 0)
    if already > 0:
        amount = max(amount, already + 5)
    c.resist(amount, DamageType.FIRE, on=me, until=When.EONT)
    _next_save(c, me, 2)


@power("f2197", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2197(c: Cast) -> None:
    """Resist 5 fire while you have temporary hit points.

    Gated, so it goes in as a modifier rather than onto `Defences` --
    `c.resist` routes a `when=` through `c.bonus` and `resolve.damage`
    reads it after the flat pool, which adds. That is also the second
    printed sentence: "if you already have fire resistance, add 5 to
    your resistance" is the same arithmetic this already does.
    """
    me = c.me
    c.resist(
        5, DamageType.FIRE, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _has_temp_hp(c, me),
    )


def _f2081_damage(using: Cast) -> None:
    """2/4/6 extra damage in place of `p2095`'s temporary hit points.

    The ladder is read off the *using* row's caster, which is the character
    whose level the card means. `once=True` because the printed bonus is
    for one attack, not for every attack until the turn ends.
    """
    step = 2 + 2 * (using.level >= 11) + 2 * (using.level >= 21)
    using.bonus("damage", step, once=True, until=When.EONT, kind="feat")


@power("f2081", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,)
def f2081(c: Cast) -> None:
    """Trades the temporary hit points `p2095` pays for extra damage.

    **The trade is the point of the row**, and it is what could not be said:
    writing the damage without giving up the temporary hit points would be a
    strictly better feat than the printed one. `c.pre_empt` is the word
    "instead" -- `p2095` reads it at its own `c.temp_hp` and lays this
    instead.

    Scales on the printed ladder, 2/4/6, read off the *using* row's caster
    because that is the character whose level the card means.
    """
    c.pre_empt("p2095", "temp_hp", _f2081_damage)


@power("f2194", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f2194(c: Cast) -> None:
    """Regain nothing from a second wind, for a bonus to three rolls instead.

    **Not the same gap as f2081.** That row suppresses a clause of another
    row's *body*; this one refuses hit points, and `Healed` is a `Decision`
    whose `amount` a listener may write -- which is how `c.half_healing`
    halves a heal rather than clawing it back afterwards. `Cast.second_wind`
    announces `SecondWind` **before** it spends the surge and before
    `world.heal`, so the watch armed here is in place for the heal it is
    about to zero. `c.no_surges` is the wrong lever: that stops the surge
    being spent at all, and this card spends it.

    The latch is written out rather than `once=True`, because `once` is
    spent only when the handler *did* something and writing a field on an
    event announces nothing -- so the hold would never come off.

    `SecondWind.healed` is the number about to come back, so the choice is
    put to the decider with it in hand; at full hit points it costs
    nothing.

    Untyped -- the card prints no word before "bonus" -- and the errata
    deletes defences from the list, so only the three rolls are laid.
    """
    me = c.me
    coming = getattr(c.trigger, "healed", 0)
    if not c.may(f"regain none of the {coming} hit points", who=me):
        return
    done: list[bool] = []

    def none(ev: Healed) -> None:
        if done or ev.target != me:
            return
        done.append(True)
        ev.amount = 0

    c.watch(Healed, none, until=When.EOT, on=me, window=Window.BEFORE,
            label=c.ref)
    for roll in ("attack", "save", "damage"):
        c.bonus(roll, 2, on=me, until=When.EONT)


@power("f2195", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       )
def f2195(c: Cast) -> None:
    """A second creature burns whenever a named row's fire lands.

    `p1458` is a ref and `DamageApplied.detail` is the ref of whatever
    dealt the blow, so "takes damage from that power, dealt by me" is an
    ordinary watch. `c.flat` here carries this feat's own ref, so the
    splash cannot feed itself.

    **"Because you took damage" is written now.** That row pays twice --
    once on the hit and once more when the warlock is hurt -- and both
    used to arrive as the same event with the same `detail`, so the splash
    fired on the first payment too: one extra 5 fire damage per use.

    **`c.by_attack()` is the fact, and it is not `from_attack`.** That flag
    means "offered damage modifiers": it is `True` by default and only
    `Cast.absorb` and `falling` pass `False`, so a trait's payout and an
    ongoing tick both arrive with it set. Widening the event with it would
    have exposed a field true for almost every blow in the game. #731.

    `p1458` deals its hit with `c.damage` and its rebound with `c.flat`,
    and `c.by_attack()` is False for the second -- which is why `c.flat`
    does **not** claim its cast's attack even inside an attack body. The
    rebound runs from a `c.watch` closure that captured the same `Cast`,
    so reading `self.result` there would have answered True for both
    blows and told these two rows apart not at all.

    `i1826x1` is the item side of the same pair and closes with it.
    """
    me = c.me

    def splash(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail != "p1458" or ev.amount <= 0:
            return
        if c.by_attack(ev=ev):
            return      # the hit itself, not the "because you took damage" half
        pool = [
            foe for foe in c.within(5, of=ev.target, side="enemy")
            if foe != ev.target
        ]
        if not pool:
            return
        other = c.choose(pool, f"{c.ref}: who else catches the fire")
        if other is not None:
            c.flat(5, dtype=DamageType.FIRE, on=other)

    c.watch(DamageApplied, splash, until=When.ENCOUNTER, on=me, label=c.ref)


# -- prime shot, restated ---------------------------------------------------


@power("f2762", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2762(c: Cast) -> None:
    """Widens who counts as "nearest" for the shared ranged feature.

    The feature's `+1` cannot be reached -- it is a modifier with a
    closure for a gate -- so this pays the same `+1` in exactly the
    cases the widened rule allows and the printed one does not. Both are
    untyped and would add, which is why the second half of the gate is
    there.
    """
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("ranged"))
            and ctx.get("target") is not None
            and _no_ally_nearer(c, ctx["target"], widened=True)
            and not _no_ally_nearer(c, ctx["target"], widened=False)
        ),
    )


@power("f2765", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2765(c: Cast) -> None:
    """"The bonus increases to +2" against a cursed target -- so a second
    untyped +1, laid only where the feature's own would already be
    paying. `_no_ally_nearer` restates that condition for the reason
    f2762 does."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("ranged"))
            and _cursed(c, ctx.get("target"))
            and _no_ally_nearer(c, ctx["target"], widened=False)
        ),
    )


# -- the racial rows --------------------------------------------------------


@power("f2127", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2127(c: Cast) -> None:
    """Grants the card beside it, `f2127b`, takes away the racial power that
    card replaces, and rolls the curse's damage as d8s.

    `p1628` is a ref, so `c.forbid` has something to name and the warlock no
    longer keeps both.

    The d8s were dropped for as long as the die was a literal closed over
    inside `extra_damage`. It is asked for now, so this is f2764's line with
    a different prerequisite in front of it.
    """
    c.grant_row("f2127b", on=c.me, until=When.ENCOUNTER)
    c.forbid("p1628", on=c.me, until=When.ENCOUNTER)
    c.change_dice("cf:warlock-f4", "1d8")


@power("f2127b", level=1, cls="", usage=ENCOUNTER, action=ActionType.MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ARCANE, Keyword.FIRE])
def f2127b(c: Cast) -> None:
    """The card of f2127: defences up and a burn on whoever swings.

    `AttackDeclared` rather than `Hit`, because the printed line is
    "each enemy that **attacks** you" and a miss is still an attack.
    Whirling fire filling the space is the flavour of those two
    sentences and not a third effect -- nothing is printed for entering
    the squares, so no zone is laid.

    The bonus is untyped: the card prints "a bonus to all defenses equal
    to your Charisma modifier" with no type word.
    """
    me = c.me
    burn = c.level // 2 + c.int_mod
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, c.cha_mod, on=me, until=When.EONT)

    def scorch(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me and burn > 0:
            c.flat(burn, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(AttackDeclared, scorch, until=When.EONT, on=me, label=c.ref)


@power("f2293", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1333",
       on=Trigger(PowerUsed, _used("p1333"), "you use that at-will"))
def f2293(c: Cast) -> None:
    """Fire on the class's own at-will, for a bonus to the damage.

    `PowerUsed` is announced before the body runs, which is right here:
    the modifier has to be standing before the damage is rolled.
    `once=True` on a damage bonus is spent by `DamageRolled`, so it
    rides exactly the one blow.

    The type change is `c.deals(implement=True)`: `p1333` is an implement
    row, and the override beats the type that row prints. Nothing scopes
    it to one use, so it is held to the end of the turn.
    """
    step = 1 + (c.level >= 11) + (c.level >= 21)
    if not c.may("make the blast burn", who=c.me):
        return
    c.deals(DamageType.FIRE, on=c.me, until=When.EOT, implement=True)
    c.bonus(
        "damage", step, on=c.me, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("power") == "p1333",
    )


@power("f2084", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2084(c: Cast) -> None:
    """`p1457` is a ref now, which was the only piece missing.

    A trait with `c.watch`, not a declared trigger, so the row is armed
    once at the start of the fight. The card prints plain "concealment or
    total concealment", which is the wide question `query.concealment_of`
    answers -- not the class feature's own, which `_shadow_concealed`
    narrows to and which three other feats in this file print instead.
    The 11th- and 21st-level rungs are paragon and out of scope.
    """
    from combat_engine.engine.query import concealment_of

    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "p1457":
            return
        if int(concealment_of(c.world, me)) <= 0:
            return
        c.flat(2, on=ev.target)
        c.penalty("attack", 2, on=ev.target, until=When.EONT)

    c.watch(Hit, rider, until=When.ENCOUNTER)
