"""Warlock feats, the second batch: the curse's damage, the shadow and
the pacts.

Three things decide almost every row here.

**The curse itself is fully modelled and fully nameable.** `c.curse` lays
it, `c.cursed(on=)` reads it back, `cursed_by_me` is the same question
asked of an event, and the relation is *relational* -- two warlocks on a
board read their own curse and not each other's. So "against a creature
you have cursed" is an ordinary gate.

**The curse's extra damage is a different thing, and it is half open.**
`cf:warlock-f4` pays through `features/strikers.py:extra_damage`,
which adds `c.total("cf:warlock-f4 damage")` on top of the dice. A
feat that *adds* to the curse's damage therefore has a hook and is
written. A feat that changes the **dice** (`c.change_dice()`), rerolls
them (`c.reroll_ones()`) or deals the curse's damage a second time in a
turn (`c.curse_damage()`) has none: the die string and the once-a-round
latch both live inside that closure.

**The pact boon is the hole.** `cf:warlock-f1` pays out on a `Dropped`,
and nothing announces the payout, so every feat reading "when your pact
boon is triggered" carries `c.on_pact_boon()`. The one exception is
f2193, which *replaces* the boon rather than riding on it -- and a watch
armed by `c.watch` is owned by its effect, so ending that effect
disarms the feature. That is the whole of "replace your pact boon".
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
    ActionType,
    AttackDeclared,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Dropped,
    EffectApplied,
    Hit,
    Keyword,
    PowerUsed,
    SavingThrow,
    SurgeSpent,
    Trigger,
    When,
    about_me,
    cursed_by_me,
    power,
)
from combat_engine.engine.components import Health, Position
from combat_engine.engine.dsl import get

#: The class feature that lays the curse, and the name its extra damage
#: reads its bonus under. `extra_damage` pays
#: `c.total(f"{label} damage")`, so a modifier under that key is the one
#: way into the curse's payout.
CURSE = "cf:warlock-f4"
CURSE_DAMAGE = f"{CURSE} damage"

#: The pact boon, and the class feature that grants concealment.
PACT = "cf:warlock-f1"
SHADOW = "cf:warlock-f3"

#: Nothing announces a pact boon paying out, and nothing invokes one on
#: purpose. Four rows here turn on that moment.
PACT_BOON = ("c.on_pact_boon()",)
#: A class feature named in prose with no ref -- the vestiges, which are
#: a whole subsystem the engine has never heard of.
FEATURE = ("c.class_feature()",)

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


@power("f1124", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.curse_damage()",))
def f1124(c: Cast) -> None:
    """A second helping of curse damage in a turn bought with an action
    point. `ActionPointSpent` is a real event, so the trigger is
    sayable; the payout is not. The once-a-round latch and the dice both
    live inside `extra_damage`'s closure and nothing reaches either, so
    there is no way to deal the curse's damage on purpose."""


@power("f2036", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.curse_damage()",))
def f2036(c: Cast) -> None:
    """The same gap as f1124, hung on another feat's granted card.
    `f2023b` is a ref and `Hit` names it, so only the paying half is
    missing."""


@power("f2760", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.reroll_ones()", "c.curse_damage()"))
def f2760(c: Cast) -> None:
    """Rerolls a 1 on the curse's damage dice. Two rows already want
    `c.reroll_ones()`; what is particular here is that the dice are the
    class feature's, rolled inside `extra_damage`, so even a general
    reroll would have nothing to attach to."""


@power("f2764", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f2764(c: Cast) -> None:
    """d6s to d8s for the curse. The die is a string literal closed over
    by `extra_damage`; three feats elsewhere name the same gap."""


@power("f2766", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_extra_damage()",))
def f2766(c: Cast) -> None:
    """Raises ongoing damage by one per curse die rolled. Word for word
    the rogue's f763 with the other striker feature in it: it needs both
    the announcement that the extra damage happened and the count of
    dice it rolled, and `extra_damage` publishes neither."""


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
       reach=PERSONAL, target=SELF, dropped=("c.bonus(dtype=)",))
def f2085(c: Cast) -> None:
    """Extra damage to whatever is already burning, whoever set it
    alight. The tier ladder is read off the level rather than written as
    three rows.

    The *type* is dropped: the extra is printed as poison and `c.bonus`
    carries `dice` but no `dtype`, so it rolls in as whatever the blow
    already was. Against a creature that resists poison that is a number
    too large, which is a whole word of the card and not a rounding.
    `c.flat` takes a type and is not usable here -- it pays at once
    rather than riding on the power's own damage.
    """
    me = c.me
    step = 2 + (c.level >= 11) + (c.level >= 21)
    c.bonus(
        "damage", step, on=me, until=When.ENCOUNTER,
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
       reach=PERSONAL, target=SELF, todo=("DamageType.pair()",))
def f2083(c: Cast) -> None:
    """Necrotic *or* poison becomes necrotic *and* poison. A blow carries
    one `DamageType` and resistance is read per type, so a blow that is
    both cannot be expressed -- the whole of this row is that pairing,
    which is why it is a `todo` and not a dropped clause."""


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
       reach=PERSONAL, target=SELF, todo=("c.on_pact_boon()",))
def f1166(c: Cast) -> None:
    """Swaps the active vestige when the pact boon fires.
    `cf:warlock-f1s6` is declared, so the feature is not the hold -- the
    boon is, as it is for the eight other rows naming it."""


@power("f2035", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_pact_boon()", "cf:warlock-f4c0"))
def f2035(c: Cast) -> None:
    """Adds a vestige with its own pact boon and augment. The boon hook is
    the standing gap; the curse the boon reads, `cf:warlock-f4c0`, has a
    ref and no row."""


@power("f1358", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PACT_BOON)
def f1358(c: Cast) -> None:
    """Leaves difficult ground behind a pact teleport. The ground is
    sayable -- `c.zone(difficult=True)` over the square and its
    neighbours, with `c.ignores_difficult` on the caster for the "to
    everyone but you" -- but the teleport it hangs on is a pact boon and
    nothing announces one."""


@power("f2759", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PACT_BOON)
def f2759(c: Cast) -> None:
    """Takes the boon early, when a cursed enemy is first bloodied,
    and pays for it with the curse.

    The trigger is declarable -- `Bloodied` plus `cursed_by_me` -- and
    the price is too, since the curse is a labelled effect that
    `Effects.end` would lift. What is missing is the benefit: nothing
    invokes a pact boon on purpose, so writing this would be the cost
    with nothing bought.
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


@power("f2191", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Dropped.power",),
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

    "With a warlock attack" is dropped. `Dropped` names its `source` --
    who landed the blow -- and not the row that did, so the narrowing
    cannot be said. It costs the feat only the warlock's own basic
    attack, which is the blast and a warlock power anyway.
    """
    if c.trigger.source != c.me:
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
    can instead increase that resistance by 5" -- is never the better of
    the two here, because `c.resist` **adds** to the flat pool rather
    than taking the larger, so the first branch is already worth
    `5 + half your level` on top of whatever was there. The choice is
    not offered because one arm of it is strictly worse.
    """
    c.resist(5 + c.level // 2, DamageType.FIRE, on=c.me, until=When.EONT)
    _next_save(c, c.me, 2)


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


@power("f2081", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_temp_hp()",))
def f2081(c: Cast) -> None:
    """Trades the temporary hit points a named row pays for damage on the
    next attack.

    `p2095` is a ref and `PowerUsed` names it, so the trigger is ready
    and the damage half is one `c.bonus(once=True)`. The word the row
    turns on is "instead": nothing declines a benefit another row is
    about to hand out, and writing the upside without the trade would be
    a strictly better feat than the printed one.
    """


@power("f2194", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.forgo_healing()",))
def f2194(c: Cast) -> None:
    """Regain nothing from a second wind and take a +2 to attacks, saves
    and damage instead. `SecondWind` is the moment; declining the healing
    is the same gap f2081 names, and it is the whole row. The errata's
    deletion of defences from the list is already reflected: they are not
    written."""


@power("f2195", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("DamageApplied.from_attack",))
def f2195(c: Cast) -> None:
    """A second creature burns whenever a named row's fire lands.

    `p1458` is a ref and `DamageApplied.detail` is the ref of whatever
    dealt the blow, so "takes damage from that power, dealt by me" is an
    ordinary watch. `c.flat` here carries this feat's own ref, so the
    splash cannot feed itself.

    "Because you took damage" is dropped. That row pays twice -- once on
    the hit and once more when the warlock is hurt -- and both arrive as
    the same event with the same `detail`. Nothing on `DamageApplied`
    says which half of a row dealt it, so the splash also fires on the
    first payment, which is one extra 5 fire damage per use.
    """
    me = c.me

    def splash(ev: DamageApplied) -> None:
        if ev.source != me or ev.detail != "p1458" or ev.amount <= 0:
            return
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
       reach=PERSONAL, target=SELF,
       dropped=("c.change_dice()", "spec.power_ref()"))
def f2127(c: Cast) -> None:
    """Grants the card beside it, `f2127b`.

    Two clauses are dropped and neither stops the row playing. The d8s
    are `c.change_dice()`, the same gap f2764 is entirely made of. The
    racial power this replaces arrives as a printed name rather than a
    ref, so there is nothing for `c.forbid` to take away -- the warlock
    keeps both, which is a use it should not have.
    """
    c.grant_row("f2127b", on=c.me, until=When.ENCOUNTER)


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


@power("f2293", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.deals(implement=)",),
       trigger="you use p1333",
       on=Trigger(PowerUsed, _used("p1333"), "you use that at-will"))
def f2293(c: Cast) -> None:
    """Fire on the class's own at-will, for a bonus to the damage.

    `PowerUsed` is announced before the body runs, which is right here:
    the modifier has to be standing before the damage is rolled.
    `once=True` on a damage bonus is spent by `DamageRolled`, so it
    rides exactly the one blow.

    The type change is dropped. `c.deals` overrides only *untyped*
    damage and only on a `WEAPON` power, and `p1333` is an implement
    row -- so the blast would stay untyped and would not gain the fire
    keyword, which is the half of the sentence that matters against
    anything resistant.
    """
    step = 1 + (c.level >= 11) + (c.level >= 21)
    if not c.may("make the blast burn", who=c.me):
        return
    c.bonus(
        "damage", step, on=c.me, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("power") == "p1333",
    )


@power("f2084", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("spec.power_ref()",))
def f2084(c: Cast) -> None:
    """Extra damage and an attack penalty on a named at-will, while you
    are concealed from its target. Every piece is ready -- `Hit`,
    `_shadow_concealed`, `c.penalty` -- except the row it rides on,
    which the brief prints as a name and never as a ref."""
