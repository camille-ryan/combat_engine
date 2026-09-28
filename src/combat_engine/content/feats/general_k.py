"""General feats: the no-class slice, offset 400.

Three shapes carry most of this batch.

**Racial riders.** There is still no race and it does not matter for the
benefit -- the prerequisite is a column `chargen.meets` enforces at build
time. What decides a row is whether the racial power it rides on arrives
as a **ref** or as a **name**. `p2475`, `p2483`, `p2484`, `p1448`,
`p1449`, `p1452`, `p1628`, `m5139a3` and `m4421a6` are refs, so a rider
on one is an ordinary `PowerUsed` trigger. What is still a name is a
racial *trait* rather than a power, and those keep
`c.on_racial_power()` -- there is nothing for a trigger to watch.

**The granted pair.** A feat whose printed benefit is "you gain the fNNNb
power" is a trait that hands over the card beside it. Six of these are
printed as a *swap* -- "you can swap one 9th-level or higher daily attack
power you know for ..." -- and the swap half is `chargen`'s business, so
those hand the card over and drop the exchange.

**The f2023b family.** Eleven rows hang off one encounter attack. So
`f2023b` lays a named hold, `c.effect(c.ref)`, on everything it hits;
`c.suffering("f2023b")` is then how f2024, f2029, f2037 and f2041 find
"a target currently affected by your f2023b". Without the hold none of
the four has a question it can ask.

"Your highest ability modifier" is eight cards in this batch and the
header can only name one ability, so `_best` computes it and the roll
carries the difference as `plus=`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    WIS,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageType,
    Dropped,
    EffectApplied,
    Fell,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerResolved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    Swap,
    Trigger,
    TurnStart,
    Usage,
    Wall,
    When,
    about_me,
    get,
    power,
)
from combat_engine.engine.query import allies, distance_between, enemies, team

#: A racial power or trait the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one of them.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
#: Nothing announces that a roll was a reroll, so a rider on one cannot
#: find its moment.
REROLL = ("c.on_reroll()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: A class feature named in prose with no ref behind it.
FEATURE = ("c.class_feature()",)
#: "You can swap one N-level power you know for this one." The card is
#: handed over; giving a power *up* is a build-time exchange.
SWAP = ("chargen.power_swap()",)

DIVINE = [Keyword.DIVINE]
ALL_DEFENCES = (AC, FORT, REF, WILL)
MELEE_REACH = ("melee", "close_burst", "close_blast")


def _best(c: Cast) -> int:
    """"Your highest ability modifier". The header names one ability, so
    the roll carries the difference as `plus=` and the damage line reads
    this directly."""
    return max(
        c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod
    )


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _used_any(*refs: str):  # noqa: ANN202
    """"A <race> racial power", where the race prints more than one."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return when


def _resolved(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _wielding_group(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.melee)


def _near_allies(c: Cast, radius: int) -> list[int]:
    me = c.me
    return [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= radius
    ]


def _granted(ref: str, card: str, **kw: Any):  # noqa: ANN202
    """The parent half of a feat whose benefit is "you gain <card>"."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, **kw)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _melee_power(ctx: dict[str, Any]) -> bool:
    """The damage context carries no `ranged` key, so "melee or close"
    has to be asked of the row that is rolling."""
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in MELEE_REACH


# -- riders on a racial power that arrives as a ref -------------------------


def _primal(ctx: dict[str, Any]) -> bool:
    """A primal power, read off the row the attack context names."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.PRIMAL in p.keywords


@power("f1675", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       trigger="you are subjected to an effect that a save can end",
       on=Trigger(EffectApplied, lambda w, me, ev: (
           ev.target == me and ev.save_ends
       ), "you are subjected to a save-ends effect"),
       )
def f1675(c: Cast) -> None:
    """Buys an immediate saving throw at +5 by spending p2475.
    `c.expend_row` charges it: the use goes and p2475's own body never
    runs, which is the printed "instead of gaining the normal effect".

    The cap is therefore p2475's single use rather than a stand-in on
    this row, so the header is `AT_WILL`."""
    if c.expend_row("p2475"):
        c.save(on=c.me, bonus=5)


@power("f1676", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1676(c: Cast) -> None:
    """Asked per throw: a power point pool is spent down mid-fight and
    the bonus is meant to go with it."""
    me = c.me
    c.bonus("save", 2, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: c.points(of=me) >= 1)


@power("f1677", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1677(c: Cast) -> None:
    """"A creature that has not yet acted" is not a state anything holds,
    so the row keeps its own roll of who has had a turn. `ev.ghost` is
    the guard: a ghost turn is the policy looking ahead, and counting one
    would retire the whole encounter's worth of victims before the first
    real turn."""
    me = c.me
    acted: set[int] = set()

    def note_turn(ev: Any) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, note_turn, on=me, until=When.ENCOUNTER)

    def sting(ev: Any) -> None:
        if ev.attacker == me and ev.target not in acted:
            c.flat(1 + max(c.dex_mod, c.wis_mod),
                   dtype=DamageType.PSYCHIC, on=ev.target)

    c.watch(Hit, sting, on=me, until=When.ENCOUNTER, once=True)


@power("f1678", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.no_provoke(when=)",))
def f1678(c: Cast) -> None:
    """A trait is armed before anybody has taken a turn, so every enemy
    on the board qualifies at arming and the grant is laid one enemy at a
    time. It expires with the caster's first turn, which is the only
    window in which walking away from somebody matters. What is dropped
    is an enemy *losing* the exemption by acting inside that window."""
    me = c.me
    for foe in enemies(c.world, me):
        c.no_provoke(from_=foe, on=me, until=When.EONT)


@power("f1774", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2475",
       on=Trigger(PowerUsed, _used("p2475"), "you use that racial power"))
def f1774(c: Cast) -> None:
    """The standing half is a shift each time an enemy connects, which is
    a watch rather than a grant: `c.shift_as` would hand over an action
    the printed line does not make the character spend."""
    me = c.me
    c.shift(2)

    def sidestep(ev: Any) -> None:
        if ev.target == me and ev.attacker != me:
            c.shift(1)

    c.watch(Hit, sidestep, on=me, until=When.EONT)


@power("f1776", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2475",
       on=Trigger(PowerUsed, _used("p2475"), "you use that racial power"))
def f1776(c: Cast) -> None:
    """A mark's own penalty already covers attacks that leave you out;
    this is a second, separate one, so it is laid on each marked enemy
    rather than folded into the mark."""
    me = c.me
    for foe in enemies(c.world, me):
        if c.marked(on=foe):
            c.penalty("attack", c.wis_mod, on=foe, until=When.EONT,
                      when=lambda ctx: ctx.get("target") != me)


@power("f1847", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2483",
       on=Trigger(PowerResolved, _resolved("p2483"), "you use that power"),
       dropped=("Effect.duration_of()",))
def f1847(c: Cast) -> None:
    """Declared on `PowerResolved` rather than `PowerUsed`: the racial
    power's own regeneration is laid in its body, and `PowerUsed` is
    announced above it. A second regeneration effect is what "increases
    by 2" comes to. Its duration is dropped -- nothing can read how long
    the power it rides on holds for, so this one runs to the end."""
    c.regeneration(2, on=c.me, until=When.ENCOUNTER)


@power("f1849", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use m5139a3",
       on=Trigger(PowerResolved, _resolved("m5139a3"), "you use that power"),
       dropped=("c.resist(replace=)",))
def f1849(c: Cast) -> None:
    """The +5 plays. Trading the racial power's resist-all *for* the
    typed one does not: the amount it granted is inside its own effect
    and nothing can read it back out, so the two stand together."""
    pick = c.choose(
        [DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING,
         DamageType.POISON, DamageType.RADIANT, DamageType.THUNDER],
        "which damage type", optional=True,
    )
    if pick is not None:
        c.resist(5, pick, on=c.me, until=When.ENCOUNTER)


@power("f1859", level=1, cls="", usage=AT_WILL, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy damages you",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.target == me and ev.source != me and ev.amount > 0
       ), "an enemy damages you"),
       dropped=("DamageApplied.vs",))
def f1859(c: Cast) -> None:
    """"While you're under the effect of p2484" is askable --
    `c.suffering` with `include_self` finds a hold this caster laid on
    itself. Which defence the attack went against is not: `Hit` and
    `DamageApplied` both drop the `vs` that `AttackRolled` carried."""
    if c.me not in c.suffering("p2484", include_self=True):
        return
    c.shift(1)


# -- racial powers and traits named only in prose ---------------------------


@power("f1670", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your p8278 racial power",
       on=Trigger(PowerUsed,
                  lambda w, me, ev: ev.actor == me and ev.power == "p8278",
                  "you use that racial power"))
def f1670(c: Cast) -> None:
    """Insubstantial is the halving sibling of resistance, read a few
    lines above it and off the same attacker now.

    "An attack with which you deal the necrotic damage from p8278" is
    that power's own rider, which is a one-shot laid until the end of
    your next turn -- so this rides for the same window rather than
    trying to spot the blow it lands on. AT_WILL because a triggered
    trait spends a use each firing and no limit is printed."""
    c.ignore_resistance(0, on=c.me, until=When.EONT, insubstantial=True)


@power("f1674", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_shift()",))
def f1674(c: Cast) -> None:
    """Re-aimed: the row it rides on is `rt:r18-shifting-fortunes`, which
    is declared, so the naming gap is closed. What is left is that
    nothing lengthens the shift *another named row* makes -- `c.shift`
    here would be a second, separate shift. Same hold `f2600` carries."""


@power("f1697", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f1697(c: Cast) -> None:
    """Pays out on a reroll, in both directions. Nothing announces that a
    roll is a second one, so neither half has a moment."""


@power("f1704", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("SkillCheck.target",), proficiency=("w:short-sword",))
def f1704(c: Cast) -> None:
    """The grant and the damage half are both writable now -- the weapon
    table keys on the ref -- but the advantage half is the whole reason
    the row is offered, and `SkillCheck` says who rolled and against what
    skill without saying who it was aimed at. "That enemy" has no
    referent, so the row stays refused rather than paying half."""


@power("f1751", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.deals(ref=)", "DamageType.pair()"))
def f1751(c: Cast) -> None:
    """Adds a second damage type to the one already chosen for p1448.
    The ref is no longer the gap; the two that remain are. `c.deals`
    retypes this creature's *weapon* attacks rather than one named row,
    and `c.damage` rolls one type at a time, so nothing can say "radiant
    as well as whatever it already was"."""


@power("f1773", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Moved.power",))
def f1773(c: Cast) -> None:
    """Re-aimed: `rt:r18-shifting-fortunes` is the row and it is
    declared. The mark is laid "at the end of your shift", and the shift
    is that row's -- but `Moved` carries `actor`, `from_`, `to` and
    `kind_` and never says which row moved the creature, so there is no
    way to tell the trait's shift from any other. Arming on `SecondWind`
    beside the trait would fire in an undefined order against the shift
    the mark is measured from."""


@power("f1832", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.ignore_concealment()",))
def f1832(c: Cast) -> None:
    """Re-aimed: `rt:r4-group-perception` is declared and lays an aura,
    so "each ally affected by it" is now the creatures standing in that
    aura. What is missing is the benefit -- nothing waives the -2 for
    attacking a concealed enemy, and `c.grants_in` takes no `when=` to
    gate one on concealment. `p1831` and `f3671` want the same verb."""


@power("f1835", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="the first time you are bloodied",
       on=Trigger(Bloodied, lambda w, me, ev: ev.actor == me,
                  "you are bloodied"))
def f1835(c: Cast) -> None:
    """Uses p1449 on being bloodied. `usage=ENCOUNTER` is the printed
    "first time during an encounter": a triggered trait spends a use
    each firing, so the limit is the header rather than a counter.

    `again=True` is the printed "even if you have already used it during
    this encounter" -- and it is a *use*, not a restore: the card lends
    one extra firing here and does not hand the power back for later,
    which `c.restore_use` would have done.
    """
    c.use_power("p1449", again=True)


@power("f1836", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f1836(c: Cast) -> None:
    """Swaps the die a racial power adds to a roll. The power is a ref;
    what is missing is any way to say which dice another row rolls."""


@power("f1848", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       dropped=("chargen.race_choice()",),
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed, _used_any(*R33), "you use a r33 racial power"))
def f1848(c: Cast) -> None:
    """The race's thirteen powers are declared, so "a r33 racial power"
    is a list of refs. Dropped: the extra 5 for a second elemental
    manifestation, which is a build choice nothing records. The 11th and
    21st level steps are out of scope."""
    c.temp_hp(5, on=c.me)


@power("f1854", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1452",
       on=Trigger(PowerUsed, _used("p1452"), "you use that racial power"))
def f1854(c: Cast) -> None:
    """"The creature that attacked you" is p1452's own target -- it
    answers an attack and is aimed at whoever made it -- which
    `PowerUsed.targets` carries, chosen before the body runs. Untyped:
    the card prints no word in front of "bonus"."""
    foes = list(c.trigger.targets)
    if not foes:
        return
    foe = foes[0]
    step = 4 + 2 * (c.level >= 11) + 2 * (c.level >= 21)
    c.bonus("damage", step, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("target") == foe)


@power("f1855", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("TempHP.power",))
def f1855(c: Cast) -> None:
    """Adds to the temporary hit points one named racial trait hands out.
    `TempHP` carries source, target and amount and never says which row
    paid, so a watcher cannot tell that batch from any other."""


@power("f1863", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_racial_bonus()",),
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f1863(c: Cast) -> None:
    """The p1628 half plays: "the target" is what `PowerUsed.targets`
    carries. Dropped: raising the attack bonus a racial *trait* already
    grants -- the trait is prose, and nothing reaches into a bonus some
    other row laid to make it bigger."""
    foes = list(c.trigger.targets)
    if not foes:
        return
    foe = foes[0]
    c.bonus("damage", 2, on=c.me, until=When.EONT, kind="power",
            when=lambda ctx: ctx.get("target") == foe)


@power("f1869", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1869(c: Cast) -> None:
    """"Your next attack roll" is `once=True`; the attack context carries
    the row, which is where the primal keyword is read."""
    c.bonus("attack", 2, on=c.me, until=When.EONT, once=True, when=_primal)


@power("f2092", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.hide(diversion=)",),
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f2092(c: Cast) -> None:
    """The combat-advantage half is the one with a consequence on the
    board, and Bluff against the target's passive Insight is the printed
    contest. The diversion to hide is dropped: hiding wants a check
    against every watcher and `c.hide` takes one."""
    foe = c.choose(c.enemies())
    if foe is None:
        return
    if c.check("bluff", c.passive("insight", of=foe)):
        c.grants_advantage(on=foe, to=c.me, once=True, until=When.EONT)


@power("f1938", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("feat.associated_powers",))
def f1938(c: Cast) -> None:
    """Grants another class's power, named in prose. `c.grant_row` is the
    verb and the ref is what is missing."""


@power("f1939", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1939(c: Cast) -> None:
    """A trait handed to somebody who does not have it. Armed now that
    `turns.arm_traits_of` re-reads `Powers.all` between passes; same
    shape as f1628."""
    c.grant_row("cf:barbarian-f3")


@power("f1839", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.armour_ability()",))
def f1839(c: Cast) -> None:
    """Replaces the ability term in the armour-class formula with a flat
    +2. AC is computed before any row runs and nothing reaches the term
    it is built from -- `c.bonus(AC, 2)` would add to it instead."""


@power("f1873", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.ignores_difficult(when=)", "c.ignores_difficult(squares=)"))
def f1873(c: Cast) -> None:
    """Both halves are narrower than the verb. `c.ignores_difficult`
    waives *all* rough ground for a duration; this waives one square of
    it, and all of it only on a charge. Writing the verb plain is a
    strictly stronger feat than the one printed."""


@power("f1983", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.restore_use(item=)",))
def f1983(c: Cast) -> None:
    """Hands back a consumable on a missed attack. Rows can be handed
    back; an expended item cannot."""


@power("f1986", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.resistance()",))
def f1986(c: Cast) -> None:
    """Reflects damage equal to the caster's own psychic resistance.
    `c.resist` writes a resistance and nothing reads one back."""


@power("f1988", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def f1988(c: Cast) -> None:
    """Darkvision. Light levels are not modelled, so neither sight grant
    has anything to be an exception to."""


@power("f2029", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.cannot_attack(opportunity=)",))
def f2029(c: Cast) -> None:
    """Bars opportunity and immediate attacks only. `c.cannot_attack`
    bars every attack the creature has, which is a different and much
    heavier card than the one printed."""


# -- the standing bonuses ---------------------------------------------------


@power("f1698", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1698(c: Cast) -> None:
    """The ritual half is not a fight and is left alone; the resistance
    is the whole of the row in combat."""
    c.resist(2, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power("f1699", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignore_squeeze_penalty()",))
def f1699(c: Cast) -> None:
    """Squeezing is a condition whose rules carry `attack=-5` and
    `halve_speed`, so the printed "-2 instead of -5" is a +3 laid against
    the standing penalty rather than a replacement.

    `conditions.Rules.halve_speed` is not the gap -- it is the field that
    imposes the penalty, and it is read in `query.speed`. The gap is the
    lifting of it: `query.speed` halves *after* it totals the `speed`
    modifiers, so no bonus a row can lay survives the division, and there
    is no way to waive one clause of a condition's rules. That is what
    i942x1 and i2541x1 are already waiting on under the same name."""
    me = c.me
    c.bonus("attack", 3, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_(Condition.SQUEEZING, on=me))
    c.bonus("skill:dungeoneering", 2, on=me, until=When.ENCOUNTER,
            kind="feat")


@power("f1702", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.reroll_check(standing=)",))
def f1702(c: Cast) -> None:
    """A trait with a watch, not a triggered row: the skill bonus is a
    standing modifier and would never be laid from inside a trigger.
    `c.reroll_check` answers a check that has already been rolled and
    needs `c.trigger`, so a standing "reroll each such check once" has
    nowhere to live."""
    me = c.me
    c.bonus("skill:bluff", 3, on=me, until=When.ENCOUNTER)

    def slip(ev: Any) -> None:
        if ev.actor == me and ev.skill == "bluff" and ev.success:
            c.shift(1)

    c.watch(SkillCheck, slip, on=me, until=When.ENCOUNTER)


@power("f1715", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1715(c: Cast) -> None:
    """The damage context carries `opportunity`, which is the one thing
    it does carry about how the attack was made."""
    me = c.me

    def beside_a_hurt_friend(ctx: dict[str, Any]) -> bool:
        if not ctx.get("opportunity", False):
            return False
        return any(
            c.adjacent(to=a) and c.bloodied(on=a)
            for a in allies(c.world, me) if a != me
        )

    c.bonus("damage", c.cha_mod, on=me, until=When.ENCOUNTER,
            when=beside_a_hurt_friend)


@power("f1721", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.rattling(when=)",))
def f1721(c: Cast) -> None:
    """The trade is per-attack and nothing offers it per-attack, so both
    halves stand for the encounter and are narrowed to melee, which is
    as close as the printed line gets.

    Not `c.as_basic`, which this carried: that verb *installs* a stand-in
    for the basic attack and this row asks after one. The narrowing it
    wants is `c.rattling(when=)` -- `c.penalty` already takes a gate and
    `c.rattling` does not, so the penalty can be held to the basic
    attack and the keyword cannot, and gating only one half would make
    the two disagree."""
    me = c.me
    c.rattling(on=me, until=When.ENCOUNTER, melee=True)
    c.penalty("attack", 2, on=me, until=When.ENCOUNTER, when=_melee_power)


@power("f1772", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:bastard-sword",))
def f1772(c: Cast) -> None:
    """The damage half plays and the grant is header data. One superior
    heavy blade stands for the printed list, which is that group plus
    two weapons already in it."""
    me = c.me
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _wielding_group(c, "heavy blade"))


@power("f1865", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Keyword.RAGE",))
def f1865(c: Cast) -> None:
    """The flat +1 plays. The increase to +2 turns on standing inside a
    polymorph or a rage, and rage is not a keyword the tree has, so
    there is no set of rows to ask about."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f1868", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1868(c: Cast) -> None:
    me = c.me

    def unseen_and_hurt(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            who is not None
            and c.bloodied(on=who)
            and c.is_hidden(from_=who)
        )

    c.bonus("damage", 3, on=me, until=When.ENCOUNTER, kind="feat",
            when=unseen_and_hurt)


@power("f1937", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1937(c: Cast) -> None:
    """Beast form is a live shape rather than a condition, so the gate is
    `forms.in_beast_form` -- the same question the druid's own rows are
    gated on. Imported inside the body: `content.feats` is loaded before
    `content.powers` and a module-level import would invert that."""
    from combat_engine.content.powers.druid.forms import in_beast_form

    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: in_beast_form(c.world, me))


@power("f1973", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1973(c: Cast) -> None:
    """"In two hands" is not recorded, but it is implied: a versatile
    weapon is in two hands exactly when the other hand is free, so no
    shield and no second weapon is the same question asked from the
    only side `Gear` answers."""
    me = c.me
    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            c.wielding("versatile")
            and not c.wielding("shield")
            and not c.wielding("two-weapon")
        ),
    )


@power("f2012", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2012(c: Cast) -> None:
    """At or below 0 and still up, which only a character can be --
    `Health.dies_at_zero` is what keeps a monster from ever qualifying,
    so this reads the hit points directly rather than `c.bloodied`."""
    me = c.me

    def down_but_up(ctx: dict[str, Any]) -> bool:
        health = c.world.get(me, Health)
        return health is not None and health.hp <= 0

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=down_but_up)
    for defence in ALL_DEFENCES:
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, when=down_but_up)


@power("f2037", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2037(c: Cast) -> None:
    """"Currently affected by your f2023b" is the named hold that row
    lays, found through `c.suffering`. An untyped +4: the card prints no
    word in front of "bonus"."""
    me = c.me

    def charmed_and_bladed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or who not in c.suffering("f2023b"):
            return False
        if not _melee_power(ctx):
            return False
        return c.wielding("light blade") or c.wielding("heavy blade")

    c.bonus("damage", 4, on=me, until=When.ENCOUNTER,
            when=charmed_and_bladed)


@power("f2095", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2095(c: Cast) -> None:
    """The widening half is writable now: `rt:r5-fear-save` is declared
    and lays +5 `kind="racial"` on saves whose effect carries the fear
    keyword, so the same bonus under the same kind covers the two extra
    cases the card adds. Two of a kind do not stack and the larger wins,
    which is right -- one save is never both.

    The save context carries `keywords`, `ongoing` and `dtype`, which is
    the whole of "charm effects and ongoing psychic damage".
    """
    me = c.me
    c.bonus(WILL, 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: c.bloodied(on=me))

    def charm_or_psychic(ctx: dict[str, Any]) -> bool:
        if Keyword.CHARM in ctx.get("keywords", frozenset()):
            return True
        return bool(ctx.get("ongoing")) and ctx.get("dtype") is DamageType.PSYCHIC

    c.bonus("save", 5, on=me, until=When.ENCOUNTER, kind="racial",
            when=charm_or_psychic)


@power("f1771", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1771(c: Cast) -> None:
    """The saving throw context carries `conditions`, which is what the
    printed narrowing is actually about -- gating on the effect's label
    would match whatever string the row that laid it chose.

    The second wind's half is a watcher rather than a declared trigger,
    because the saving throw bonus has to be standing from the start of
    the fight and a triggered row is not armed until it fires."""
    me = c.me
    pet = c.companion()
    if pet is None:
        return
    guarded = {Condition.DAZED, Condition.DOMINATED, Condition.STUNNED}
    c.bonus(
        "save", 2, on=pet, until=When.ENCOUNTER,
        when=lambda ctx: bool(guarded & set(ctx.get("conditions", ()))),
    )

    def winded(ev: SecondWind) -> None:
        beast = c.companion()
        if ev.actor == me and beast is not None:
            c.shift(3, who=beast)

    c.watch(SecondWind, winded, on=me, until=When.ENCOUNTER)


@power("f1860", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1860(c: Cast) -> None:
    """A trait with a watch. The bonus has to be a standing modifier so
    it is in place when the charge is rolled; the penalty it is paid for
    can only be laid once a charge has been declared, and
    `AttackDeclared` carries `charge` as a plain attribute."""
    me = c.me
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("charge", False))

    def expose(ev: Any) -> None:
        if ev.attacker == me and getattr(ev, "charge", False):
            c.penalty(AC, 2, on=me, until=When.SONT)

    c.watch(AttackDeclared, expose, on=me, until=When.ENCOUNTER)


# -- triggered rows ---------------------------------------------------------


@power("f1703", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally within 3 squares drops to 0 hit points or fewer",
       on=Trigger(Dropped, lambda w, me, ev: (
           ev.actor != me
           and team(w, ev.actor) == team(w, me)
           and distance_between(w, me, ev.actor) <= 3
       ), "an ally within 3 squares drops"))
def f1703(c: Cast) -> None:
    """`team` directly rather than `query.allies`: a dropped creature is
    filtered out of the live lists, so the obvious spelling is false
    exactly when this row should fire."""
    c.temp_hp(5, on=c.me)


@power("f1714", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you succeed on a saving throw",
       on=Trigger(SavingThrow, lambda w, me, ev: (
           ev.actor == me and ev.saved
       ), "you succeed on a saving throw"),
       dropped=("Effect.first_only",))
def f1714(c: Cast) -> None:
    """"The next ally to make a saving throw" is one grant shared by
    everybody in range, and `once=` is per effect rather than per set --
    so each ally within 5 gets their own one-shot instead of the first
    of them spending it for the rest."""
    for friend in _near_allies(c, 5):
        c.bonus("save", 4, on=friend, until=When.SONT, once=True)


@power("f1717", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, lambda w, me, ev: (
           ev.actor == me and ev.cost is ActionType.STANDARD
       ), "you spend an action point for a standard action"))
def f1717(c: Cast) -> None:
    """"To make an attack" is read as the standard action a point buys:
    `ActionPointSpent` carries the cost and nothing about what the extra
    action was then spent on."""
    c.temp_hp(3 + c.cha_mod, on=c.me)


@power("f1837", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1837(c: Cast) -> None:
    """A trait with a watch rather than a declared trigger. "The first
    time you are bloodied during an encounter" is `once=True` on the
    watch, which is spent only when the handler actually does something;
    a declared `ENCOUNTER` trigger would be spent by the first firing
    whether it paid out or not. The skill half is not a fight."""
    me = c.me

    def rally(ev: Any) -> None:
        if ev.actor != me:
            return
        for who in (me, *_near_allies(c, 10)):
            for defence in ALL_DEFENCES:
                c.bonus(defence, 1, on=who, until=When.EONT)

    c.watch(Bloodied, rally, on=me, until=When.ENCOUNTER, once=True)


@power("f1850", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you bloody a creature",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.source == me
           and (h := w.get(ev.target, Health)) is not None
           and ev.hp <= h.max_hp // 2 < ev.hp + ev.amount
       ), "you bloody a creature"))
def f1850(c: Cast) -> None:
    """`Bloodied` announces the crossing but not who caused it, so the
    question is asked of `DamageApplied`, which carries both the source
    and the hit points either side of the blow."""
    for defence in ALL_DEFENCES:
        c.bonus(defence, 1, on=c.me, until=When.EONT)


@power("f1870", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1870(c: Cast) -> None:
    """Same shape as f1837: a trait whose once-per-encounter half is
    `once=True` on the watch. `dice=` on a bonus is the extra-damage-die
    shape.

    "The type you initially chose for your p1448 racial power" is the
    build's own element, which `c.element` is the reader for. A character
    whose build recorded none leaves the die untyped, which is what it
    was before there was anywhere to put a type."""
    me = c.me
    element = c.element(on=me)

    def flare(ev: Any) -> None:
        if ev.actor == me:
            c.bonus("damage", 0, dice="1d8", on=me, until=When.EONT,
                    dtype=element)

    c.watch(Bloodied, flare, on=me, until=When.ENCOUNTER, once=True)


@power("f1871", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you daze or stun an enemy",
       on=Trigger(ConditionApplied, lambda w, me, ev: (
           ev.source == me
           and ev.condition in (Condition.DAZED, Condition.STUNNED)
       ), "you daze or stun an enemy"),
       dropped=("ConditionApplied.power",))
def f1871(c: Cast) -> None:
    """`ConditionApplied` names the source, the target and the condition
    and never the row that applied it, so "with a primal power" cannot be
    asked -- the push follows any daze or stun of the caster's."""
    c.push(1, on=c.trigger.target)


@power("f1940", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="the start of your turn",
       on=Trigger(TurnStart, lambda w, me, ev: (
           ev.actor == me and not ev.ghost
       ), "your turn starts"))
def f1940(c: Cast) -> None:
    """An early saving throw. The end-of-turn throw the effect gets
    anyway is the durations clock's and is untouched, which is exactly
    the printed "you still make a saving throw at the end of your
    turn"."""
    c.save(on=c.me)


@power("f1979", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you fall",
       on=Trigger(Fell, lambda w, me, ev: ev.actor == me, "you fall"))
def f1979(c: Cast) -> None:
    """Ten feet is two squares, and `Fell.soften` is the field the rule
    is subtracted from -- `c.cushion` adds to it."""
    c.cushion(2)


# -- the granted pairs ------------------------------------------------------


_granted("f1706", "f1706b")


@power("f1706b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you roll damage for a melee attack",
       dropped=("c.reroll_damage(melee=)",))
def f1706b(c: Cast) -> None:
    """The printed trigger is deliberately **not** declared. A damage
    reroll is read where the dice are rolled, not off `DamageRolled` --
    that event carries a total with no dice behind it, as
    `c.reroll_damage` says outright -- so a row declared on it would
    answer after the only moment it could act. Used as the free action
    it is, ahead of the swing, the effect is in place for the roll.
    Narrowing it to melee is the half that is dropped."""
    c.reroll_damage(on=c.me, until=When.EOT)


_granted("f2010", "f2010b")


@power("f2010b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(1), target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.ZONE], group=CHANNEL_DIVINITY,
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me,
                  "you hit an enemy"))
def f2010b(c: Cast) -> None:
    """"Heavily obscured" is `blocks_sight`: the squares stop sight
    through them, which is the whole mechanical content of the phrase."""
    c.zone(c.area(), until=When.SONT, blocks_sight=True)


_granted("f2014", "f2014b")


@power("f2014b", level=1, cls="", usage=ENCOUNTER, action=REACTION,
       reach=Ranged(10), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
       group=CHANNEL_DIVINITY,
       trigger="an attack bloodies an ally within range",
       on=Trigger(Bloodied, lambda w, me, ev: (
           ev.actor != me
           and team(w, ev.actor) == team(w, me)
           and distance_between(w, me, ev.actor) <= 10
       ), "an ally within range is bloodied"))
def f2014b(c: Cast) -> None:
    """The target is the triggering ally, read off the event rather than
    chosen: `Bloodied` carries `actor` and it is the only creature this
    row may aim at."""
    friend = c.trigger.actor
    pick = c.choose(["teleport", "insubstantial"], "which half")
    if pick == "insubstantial":
        c.insubstantial(on=friend, until=When.SONT)
    else:
        c.teleport(3, who=friend)


_granted("f1713", "f1713b", swap=Swap(16, utility=True))


@power("f1713b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Wall(8, 20), target=NO_TARGET,
       keywords=[Keyword.ARCANE, Keyword.CONJURATION],
       dropped=("c.destroy(familiar=)", "c.penalty(through_zone=)"))
def f1713b(c: Cast) -> None:
    """A wall that herds rather than blocks: `solid=False` because a
    creature may walk into it, `difficult=True` for the extra cost to
    enter. Two clauses are dropped. Destroying the familiar that pays for
    it has no verb -- `c.dispel` unwinds a zone, not a creature -- and
    the -2 for attacking through the wall is a modifier on *other*
    people's rolls conditioned on geometry no context carries."""
    barrier = c.wall(8, difficult=True, solid=False, until=When.EONT,
                     sustain=MINOR)

    def herd(ev: Any) -> None:
        if ev.ghost or team(c.world, ev.actor) == team(c.world, c.me):
            return
        if c.adjacent_to(barrier, ev.actor):
            c.slide(3, on=ev.actor)
            c.slowed(on=ev.actor, until=When.EOT)

    c.watch(TurnStart, herd, on=c.me, until=When.EONT)


# -- the divine multiclass family -------------------------------------------


@power("f1762", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1762(c: Cast) -> None:
    """`c.as_implement` is the printed "any weapon you are proficient
    with counts as an implement". The bonus it forgoes is the weapon's
    proficiency, which the implement path does not apply anyway."""
    c.grant_row("f1762b", on=c.me, until=When.ENCOUNTER)
    c.as_implement(on=c.me)


@power("f1762b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       attack=Attack(WIS, vs=WILL))
def f1762b(c: Cast) -> None:
    """No damage line at all -- the whole Hit is two conditional riders,
    each armed as a one-shot watch. `once=True` on a watch is spent only
    when the handler actually does something, so the guard on the wrong
    creature does not burn either of them."""
    victim = c.target
    if victim is None:
        return
    if not c.strike(plus=_best(c) - c.attack_mod):
        return

    def if_it_moves(ev: Any) -> None:
        if ev.actor != victim:
            return
        near = _near_allies(c, 5)
        if near:
            c.shift(1, who=near[0])

    def if_it_attacks(ev: Any) -> None:
        if ev.attacker != victim:
            return
        near = _near_allies(c, 5)
        if not near:
            return
        aimed = lambda ctx: ctx.get("target") == victim  # noqa: E731
        c.bonus("attack", 2, on=near[0], until=When.EONT, kind="power",
                when=aimed)
        c.bonus("damage", 2, on=near[0], until=When.EONT, kind="power",
                when=aimed)

    c.watch(Moved, if_it_moves, on=c.me, until=When.EONT, once=True)
    c.watch(AttackDeclared, if_it_attacks, on=c.me, until=When.EONT,
            once=True)


@power("f1763", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1763(c: Cast) -> None:
    """The training half is not a fight; the card is the row."""
    c.grant_row("f1763b", on=c.me, until=When.ENCOUNTER)


@power("f1763b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.WEAPON], attack=Attack(STR, vs=AC))
def f1763b(c: Cast) -> None:
    """"Its next attack roll" is `once=True` on the penalty, which is
    spent by the first roll rather than every roll in the window."""
    best = _best(c)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(), best)
        c.penalty("attack", 2, until=When.EONT, once=True)


_granted("f1760", "f1760b", swap=Swap(3, Usage.ENCOUNTER))


@power("f1760b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.WEAPON], attack=Attack(STR, vs=AC))
def f1760b(c: Cast) -> None:
    """The push answers the target's *declaration*, not its hit, which is
    what "makes an attack that does not include you as a target" means --
    it is paid whether the attack lands or not."""
    victim = c.target
    if victim is None:
        return
    best = _best(c)
    if not c.strike(plus=best - c.attack_mod):
        return
    c.damage(c.w(2), best)

    def riposte(ev: Any) -> None:
        if ev.attacker == victim and ev.target != c.me:
            c.push(2, on=victim)

    c.watch(AttackDeclared, riposte, on=c.me, until=When.EONT, once=True)


_granted("f1761", "f1761b", swap=Swap(3, Usage.ENCOUNTER))


@power("f1761b", level=1, cls="", usage=ENCOUNTER, action=REACTION,
       reach=Ranged(10), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT],
       attack=Attack(WIS, vs=FORT),
       trigger="an enemy within range that you can see hits an ally",
       on=Trigger(Hit, lambda w, me, ev: (
           team(w, ev.attacker) != team(w, me)
           and team(w, ev.target) == team(w, me)
           and distance_between(w, me, ev.attacker) <= 10
       ), "an enemy within range hits an ally"))
def f1761b(c: Cast) -> None:
    """Both creatures come off the event: the target is the attacker and
    the surge goes to whoever it hit."""
    foe = c.trigger.attacker
    hurt = c.trigger.target
    best = _best(c)
    if c.strike(on=foe, plus=best - c.attack_mod):
        c.damage("1d12", best, on=foe)
        c.surge(on=hurt)


_granted("f1764", "f1764b", swap=Swap(9, Usage.DAILY))


@power("f1764b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.WEAPON],
       attack=Attack(STR, vs=AC), dropped=("c.shift(toward=)",))
def f1764b(c: Cast) -> None:
    """The Aftereffect hangs on the hold's `on_end`, so the daze follows
    the effect ending whichever way it ended. The payout watch runs on
    the encounter clock and checks the hold is still live instead of
    holding a save of its own -- two `SAVE_ENDS` effects would give the
    victim two throws for one printed sentence.

    The shift's destination is dropped: `c.shift` chooses through the
    world's decider and cannot be told to land beside a named creature."""
    victim = c.target
    if victim is None:
        return
    best = _best(c)
    if not c.strike(plus=best - c.attack_mod):
        return
    c.damage(c.w(2), best, dtype=DamageType.RADIANT)

    def afterwards() -> None:
        c.dazed(on=victim, until=When.EONT)

    hold = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} radiating",
        on_end=[afterwards],
    )

    def aid(ev: Any) -> None:
        if hold.id not in c.world.effects.live:
            return
        if ev.amount <= 0 or ev.target == victim:
            return
        if team(c.world, ev.target) != team(c.world, c.me):
            return
        if distance_between(c.world, victim, ev.target) > 3:
            return
        c.temp_hp(best, on=ev.target)
        c.shift(c.speed_of())

    c.watch(DamageApplied, aid, on=c.me, until=When.ENCOUNTER)


_granted("f1765", "f1765b", swap=Swap(6, utility=True))


@power("f1765b", level=1, cls="", usage=ENCOUNTER, action=INTERRUPT,
       reach=Ranged(5), target=ONE_ALLY, keywords=DIVINE,
       trigger="an ally in range is hit by an attack",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.target != me
           and team(w, ev.target) == team(w, me)
           and distance_between(w, me, ev.target) <= 5
       ), "an ally in range is hit"),
       dropped=("c.shift(toward=)",))
def f1765b(c: Cast) -> None:
    """An interrupt, so the defences are up before the attack resolves.
    Landing the shift beside the ally is dropped -- the decider picks the
    square and takes no destination."""
    friend = c.trigger.target
    c.shift(5)
    for defence in ALL_DEFENCES:
        c.bonus(defence, 3, on=friend, until=When.SONT)


_granted("f1766", "f1766b", swap=Swap(9, Usage.DAILY))


@power("f1766b", level=1, cls="", usage=DAILY, action=FREE,
       reach=CloseBurst(3), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.RADIANT],
       trigger="you hit an enemy",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me,
                  "you hit an enemy"))
def f1766b(c: Cast) -> None:
    """`c.grant_attack`'s own `damage_bonus` is a bare number with no type
    to it, so the extra die is laid as a one-shot typed damage modifier on
    the ally instead and the granted attack spends it. Same arithmetic,
    and the radiant meets a radiant resistance the way it is printed to."""
    friend = c.target
    if friend is None:
        return
    foe = c.trigger.target
    c.surge(on=friend)
    c.bonus("damage", 0, dice="1d10", on=friend, until=When.EONT, once=True,
            dtype=DamageType.RADIANT,
            when=lambda ctx: ctx.get("target") == foe)
    c.grant_attack(friend, on=foe, attack_bonus=2)


_granted("f1767", "f1767b", swap=Swap(6, utility=True))


@power("f1767b", level=1, cls="", usage=DAILY, action=REACTION,
       reach=Ranged(10), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="an ally within range is hit by an attack",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.target != me
           and team(w, ev.target) == team(w, me)
           and distance_between(w, me, ev.target) <= 10
       ), "an ally within range is hit"),
       dropped=("c.teleport(toward=)",))
def f1767b(c: Cast) -> None:
    """"Regains hit points as if it spent a healing surge" is the surge's
    *value* without the surge, so `c.heal` rather than `c.surge`. The
    mark hangs on a save rather than a turn, which is the printed
    duration and unusual for one."""
    friend = c.trigger.target
    foe = c.trigger.attacker
    c.heal(c.surge_value(of=friend), on=friend)
    c.teleport(10)
    c.mark(on=foe, until=When.SAVE_ENDS)


# -- the f2023b family ------------------------------------------------------


@power("f2023", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2023(c: Cast) -> None:
    """The Diplomacy bonus and the ritual are not a fight; the card is."""
    c.grant_row("f2023b", on=c.me, until=When.ENCOUNTER)


@power("f2023b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, keywords=[Keyword.CHARM],
       attack=Attack(INT, vs=WILL, plus=3),
       dropped=("c.cannot_approach()",))
def f2023b(c: Cast) -> None:
    """The named hold is load-bearing: four other feats in this batch ask
    "a target currently affected by your f2023b", and `c.suffering`
    matches on the label, so without it none of them has a question.

    "Cannot willingly move closer to you" is dropped. `c.rooted` and
    `c.no_walk` both bar a whole kind of movement rather than a
    direction, and there is nothing that bars one direction only."""
    victim = c.target
    if victim is None:
        return
    best = max(c.int_mod, c.wis_mod, c.cha_mod)
    if not c.strike(plus=best - c.attack_mod):
        return
    c.grants_advantage(on=victim, until=When.EONT)
    c.effect(c.ref, on=victim, until=When.EONT)


@power("f2024", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a target with f2023b",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "f2023b"
       ), "you hit with f2023b"))
def f2024(c: Cast) -> None:
    """`to="team"` is one relation per beneficiary held on a single
    effect, so they all end together with the power's own duration."""
    c.grants_advantage(on=c.trigger.target, to="team", until=When.EONT)


@power("f2025", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.cast_from(ref=)", "c.no_provoke(when=)"))
def f2025(c: Cast) -> None:
    """`c.cast_from` moves the origin of *every* ranged and area attack
    the caster makes; narrowing it to one row is the first dropped
    clause, and the provoke waiver is the second -- `c.no_provoke` names
    a creature to be safe from, not a row to be safe while using."""
    familiar = c.familiar()
    if familiar is not None:
        c.cast_from(familiar, on=c.me, until=When.ENCOUNTER)


@power("f2027", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f2027(c: Cast) -> None:
    """`group=` is what makes this cost a channel divinity use: the
    budget is shared across every such row a character holds, from any
    source, and `uses=1` would only limit this one."""
    c.restore_use("f2023b", on=c.me)


@power("f2041", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss the target of f2023b",
       on=Trigger(Miss, lambda w, me, ev: ev.attacker == me,
                  "you miss with an attack"))
def f2041(c: Cast) -> None:
    """The narrowing is done in the body rather than the predicate: a
    trigger predicate is handed `(world, me, ev)` and `c.suffering` needs
    a `Cast` to know whose effects to look for."""
    ev = c.trigger
    if ev.target not in c.suffering("f2023b"):
        return
    p = get(ev.power)
    if p is None or p.reach.kind not in MELEE_REACH:
        return
    if not c.wielding("light blade"):
        return
    if c.choose(["shift", "move"], "which") == "move":
        c.move(c.speed_of())
    else:
        c.shift(1)


# -- proficiency and other build-time grants --------------------------------


@power("f1815", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1815(c: Cast) -> None:
    """The grant plays and the twice-per-encounter cap plays with it:
    `c.grant_row` takes a budget now, counts the holder's uses off
    `PowerUsed` and forbids the row when they run out. It is exactly
    what this row needs -- the granted card is an at-will of its own,
    so lent bare it was a free action available every turn rather than
    twice a fight.

    The ref is the one the spec prints. It used to point at a monster
    ability, which was the nearest thing in the tree before the spec
    carried an id for this clause."""
    c.grant_row("p9400", on=c.me, until=When.ENCOUNTER, uses=2)


# -- not a fight ------------------------------------------------------------


@power("f1701", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1701(c: Cast) -> None:
    """Aiding somebody else's skill check, and a language."""


@power("f1828", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1828(c: Cast) -> None:
    """Knowledge checks and a language."""


@power("f1885", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1885(c: Cast) -> None:
    """Knowledge checks and a ritual."""


@power("f1980", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1980(c: Cast) -> None:
    """A sense for something the map does not hold, and a skill bonus."""


@power("f1982", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1982(c: Cast) -> None:
    """A knowledge-check reroll and a skill bonus."""


@power("f2038", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2038(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2039", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2039(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2040", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2040(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2042", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2042(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2043", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2043(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2044", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2044(c: Cast) -> None:
    """Ritual mastery and a component waiver."""


@power("f2050", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2050(c: Cast) -> None:
    """Martial practices are the out-of-combat half of the ritual
    system."""


@power("f2093", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2093(c: Cast) -> None:
    """A skill bonus and a reroll of that same skill check. Both halves
    are a check rather than a fight, which is what makes this a finished
    row rather than one holding a `dropped`."""
