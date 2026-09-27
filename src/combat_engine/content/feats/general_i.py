"""General feats, ninth batch: the divine channellers and their riders.

Three shapes fill this slice and two of them already have a machine.

**The granted pair.** Twenty-nine feats here print nothing but "you gain
the `cf:avenger-f2` power `fNNNb`". `_granted` is `general_b.py`'s helper,
rewritten here rather than imported so the two batches stay independent,
and every card carries `group=CHANNEL_DIVINITY` -- the printed "only one
per encounter" is a budget shared across every such row a character owns,
not a usage limit on the row. `f1452`'s card falls outside this slice and
is handed over by ref all the same; `c.grant_row` is right the day it
lands.

**The associated-power rider with a skill bonus on top.** Sixteen feats
print "+2 feat bonus to <skill>" and then a clause that fires on the
powers the card associates. `exploits.py`'s `_riders` says the second
half and not the first, so `_divine` here is `_riders` plus the skill
modifier -- `skill:<name>` is an ordinary key, so the bonus is real work
rather than flavour. Two of the sixteen print no list at all and carry
`dropped=("feat.associated_powers",)`: the skill half plays, the rider
has nothing to point at.

A note on the riders that read "hit **one or more** enemies": a `Hit` is
announced per target, so a burst pays out once per creature it caught.
Each of those clauses is written so a second payment is harmless -- a
`kind="power"` bonus that does not stack with itself, temporary hit
points where the highest wins, or `stacks=False`.

**The rest** are ordinary standing feats. The gaps they leave are named
on the rows.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionPointSpent,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Dropped,
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerResolved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SkillCheck,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.components import Gear, Health
from combat_engine.engine.grid import spread
from combat_engine.engine.query import (
    distance_between,
    has_combat_advantage,
    team,
)

DIVINE = [Keyword.DIVINE]
DIVINE_HEAL = [Keyword.DIVINE, Keyword.HEALING]

#: Every defence, for the cards that say "all defenses".
DEFENCES = (AC, FORT, REF, WILL)

#: The five damage types f1425b lets you pick between.
ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)

#: One clause: given the trait's cast and the triggering `Hit`, do it.
Clause = Callable[[Cast, Any], None]


# -- the machines -----------------------------------------------------------


def _granted(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is the card beside it."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _divine(
    ref: str,
    skill: str,
    *,
    clauses: dict[str, Clause] | None = None,
    also: Callable[[Cast], None] | None = None,
    **header: Any,
) -> None:
    """A skill bonus, and a clause on each power the card associates.

    One watcher rather than one subscription per named power: the list is
    four long at most, and picking the clause inside the handler keeps the
    comparison against `ev.power` in a single place.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, **header)
    def feat(c: Cast) -> None:
        me = c.me
        c.bonus(f"skill:{skill}", 2, on=me, until=When.ENCOUNTER, kind="feat")
        if clauses:
            def on_hit(ev: Any) -> None:
                if ev.attacker != me:
                    return
                clause = clauses.get(ev.power)
                if clause is not None:
                    clause(c, ev)

            c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me,
                    label=f"{ref} riders")
        if also is not None:
            also(c)

    feat.__name__ = ref
    feat.__doc__ = (
        f"+2 feat bonus to {skill}"
        + (", and riders on " + ", ".join(sorted(clauses)) if clauses else "")
        + "."
    )


def _keywords(ref: str) -> tuple[Keyword, ...]:
    p = get(ref or "")
    return tuple(p.keywords) if p is not None else ()


def _usage(ref: str) -> Usage | None:
    p = get(ref or "")
    return p.usage if p is not None else None


def _unconscious(world: Any, eid: int) -> bool:
    """Asked of the live holds rather than of a component: a condition is
    only ever a hold's contents here."""
    return any(
        Condition.UNCONSCIOUS in eff.conditions for eff in world.effects.of(eid)
    )


def _wielding(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.melee)


# -- the associated-power feats ---------------------------------------------


def _bloodied_allies_attack(c: Cast, ev: Any) -> None:
    for friend in c.within(10, side="ally"):
        if friend != c.me and c.bloodied(on=friend):
            c.bonus("attack", 1, on=friend, until=When.SONT, kind="power")


def _conceal_self(c: Cast, ev: Any) -> None:
    """"Against the next attack made against you" is narrowed only by the
    duration; nothing spends concealment on one roll."""
    c.conceal(on=c.me, until=When.EONT)


def _damage_vs_bloodied(c: Cast, ev: Any) -> None:
    if c.bloodied(on=ev.target):
        c.bonus("damage", 2, on=c.me, until=When.EOT, once=True)


def _slow_until_sont(c: Cast, ev: Any) -> None:
    c.slowed(on=ev.target, until=When.SONT)


def _save_boost(c: Cast, ev: Any) -> None:
    """"You or an ally": whoever is actually carrying something a save can
    end, and the caster when nobody is."""
    pool = [c.me, *[f for f in c.within(5, side="ally") if f != c.me]]
    who = next(
        (
            w
            for w in pool
            if any(e.when is When.SAVE_ENDS for e in c.world.effects.of(w))
        ),
        c.me,
    )
    c.bonus("save", 2, on=who, until=When.SONT, once=True, stacks=False)


def _ally_attack(c: Cast, ev: Any) -> None:
    for friend in c.within(5, side="ally"):
        if friend != c.me:
            c.bonus("attack", 1, on=friend, until=When.SONT,
                    kind="power", once=True)
            return


def _all_defences(c: Cast, ev: Any) -> None:
    for defence in DEFENCES:
        c.bonus(defence, 1, on=c.me, until=When.SONT, kind="power")


def _ally_temp_three(c: Cast, ev: Any) -> None:
    for friend in c.within(10, side="ally"):
        if friend != c.me:
            c.temp_hp(3, on=friend)
            return


def _two_allies_temp(c: Cast, ev: Any) -> None:
    for friend in [f for f in c.within(5, side="ally") if f != c.me][:2]:
        c.temp_hp(5, on=friend)


def _attack_penalty(c: Cast, ev: Any) -> None:
    c.penalty("attack", 1, on=ev.target, until=When.EONT)


_F1424 = ("p2848", "p841", "p2894", "p3687")
_F1426 = ("p833", "p2848", "p3423", "p7072")
_F1436 = ("p8286", "p2847", "p5333", "p1567")
_F1449 = ("p6980", "p1567", "p841", "p2849")


def _arcane_after(c: Cast) -> None:
    """"After using the power" -- so it is hung on the use and not on the
    hit, unlike every clause above."""
    me = c.me

    def on_used(ev: Any) -> None:
        if ev.actor == me and ev.power in _F1424:
            c.bonus(
                "attack", 1, on=me, until=When.EONT,
                when=lambda ctx: Keyword.ARCANE in _keywords(ctx.get("power", "")),
            )

    c.watch(PowerUsed, on_used, on=me, until=When.ENCOUNTER)


def _next_big_attack(c: Cast) -> None:
    """The bonus is spent on the *next* encounter or daily power, so the
    triggering row is excluded by ref -- `PowerUsed` is announced before
    the body runs, and without that guard the associated power would eat
    its own bonus."""
    me = c.me

    def on_used(ev: Any) -> None:
        if ev.actor != me or ev.power not in _F1426:
            return
        fired = ev.power
        c.bonus(
            "attack", 1, on=me, until=When.EONT, once=True,
            when=lambda ctx: (
                ctx.get("power") != fired
                and _usage(ctx.get("power", "")) in (Usage.ENCOUNTER, Usage.DAILY)
            ),
        )

    c.watch(PowerUsed, on_used, on=me, until=When.ENCOUNTER)


def _bonus_vs_bloodied(c: Cast) -> None:
    """A bonus to the attack *roll*, so it cannot be a rider on the hit --
    it is a standing modifier the attack context answers."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") in _F1436
            and ctx.get("target") is not None
            and c.bloodied(on=ctx["target"])
        ),
    )


def _wider_crit(c: Cast) -> None:
    """19-20 on the associated rows only. `crit_range` is read with the
    attack context, which carries the ref."""
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in _F1449,
    )


_divine("f1361", "religion", dropped=("feat.associated_powers",))
_divine("f1363", "insight", clauses={
    "p6980": _bloodied_allies_attack,
    "p7152": _bloodied_allies_attack,
    "p839": _bloodied_allies_attack,
    "p3687": _bloodied_allies_attack,
})
_divine("f1424", "arcana", also=_arcane_after,
        dropped=("c.counts_as(keyword=)",))
_divine("f1426", "thievery", also=_next_big_attack)
_divine("f1429", "stealth", clauses={
    "p7241": _conceal_self,
    "p3423": _conceal_self,
    "p1580": _conceal_self,
    "p7153": _conceal_self,
})
_divine("f1431", "religion", clauses={
    "p836": _damage_vs_bloodied,
    "p2894": _damage_vs_bloodied,
    "p839": _damage_vs_bloodied,
    "p7153": _damage_vs_bloodied,
})
_divine("f1433", "intimidate", dropped=("feat.associated_powers",))
_divine("f1434", "athletics", clauses={
    "p833": _slow_until_sont,
    "p3423": _slow_until_sont,
    "p7072": _slow_until_sont,
    "p7153": _slow_until_sont,
})
_divine("f1436", "insight", also=_bonus_vs_bloodied)
_divine("f1438", "acrobatics", clauses={
    "p1567": _save_boost,
    "p569": _save_boost,
    "p839": _save_boost,
    "p2849": _save_boost,
})
_divine("f1440", "diplomacy", clauses={
    "p2847": _ally_attack,
    "p569": _ally_attack,
    "p839": _ally_attack,
    "p835": _ally_attack,
})
_divine("f1443", "history", clauses={
    "p8286": _all_defences,
    "p2850": _all_defences,
    "p569": _all_defences,
    "p3687": _all_defences,
})
_divine("f1445", "heal", clauses={
    "p8286": _ally_temp_three,
    "p2847": _ally_temp_three,
    "p833": _ally_temp_three,
    "p2894": _ally_temp_three,
})
_divine("f1447", "diplomacy", clauses={
    "p2894": _two_allies_temp,
    "p7072": _two_allies_temp,
    "p5137": _two_allies_temp,
    "p3687": _two_allies_temp,
}, dropped=("c.forgo_damage()",))
_divine("f1449", "acrobatics", also=_wider_crit)
_divine("f1451", "bluff", clauses={
    "p836": _attack_penalty,
    "p3423": _attack_penalty,
    "p839": _attack_penalty,
    "p7153": _attack_penalty,
})


# -- the channelled cards ---------------------------------------------------


def _item_daily(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "item"
        and p.usage is Usage.DAILY
    )


def _my_check(world: Any, me: int, ev: Any) -> bool:
    return ev.actor == me


def _ally_dropped_by_enemy(world: Any, me: int, ev: Any) -> bool:
    return (
        ev.source is not None
        and team(world, ev.actor) == team(world, me)
        and team(world, ev.source) != team(world, me)
        and distance_between(world, me, ev.source) <= 10
    )


def _hurt_my_unconscious_ally(world: Any, me: int, ev: Any) -> bool:
    return (
        team(world, ev.target) == team(world, me)
        and team(world, ev.source) != team(world, me)
        and distance_between(world, me, ev.source) <= 10
        and _unconscious(world, ev.target)
    )


def _overheals_my_ally(world: Any, me: int, ev: Any) -> bool:
    health = world.get(ev.target, Health)
    return (
        health is not None
        and ev.amount > 0
        and team(world, ev.target) == team(world, me)
        and distance_between(world, me, ev.target) <= 5
        and ev.hp + ev.amount >= health.max_hp
    )


def _my_melee_hit(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.reach.kind == "melee"


def _my_miss(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.reach.kind in ("melee", "ranged")


def _enemy_damages_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and team(world, ev.source) != team(world, me)


def _elemental_hit_on_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and any(
        Keyword(t.value) in _keywords(ev.power) for t in ELEMENTS
    )


def _save_near_me(world: Any, me: int, ev: Any) -> bool:
    return ev.against != "death" and distance_between(world, me, ev.actor) <= 5


def _death_save_near_me(world: Any, me: int, ev: Any) -> bool:
    return ev.against == "death" and distance_between(world, me, ev.actor) <= 10


def _ally_takes_damage(world: Any, me: int, ev: Any) -> bool:
    return (
        ev.target != me
        and team(world, ev.target) == team(world, me)
        and distance_between(world, me, ev.target) <= 5
    )


_granted("f1362", "f1362b")


@power("f1362b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you use a magic item's daily power",
       on=Trigger(PowerResolved, _item_daily, "you use an item's daily power"))
def f1362b(c: Cast) -> None:
    """Declared on `PowerResolved` rather than `PowerUsed`, and that is the
    whole of the row's correctness: `Cast.used` announces `PowerUsed`
    *above* `powers.note_use`, so a use handed back there is spent again a
    line later. `PowerResolved` is the first moment the expenditure has
    actually happened."""
    if c.roll("1d20") >= 10:
        c.restore_use(c.trigger.power, on=c.me)


_granted("f1364", "f1364b")


@power("f1364b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=Ranged(10),
       target=ONE_CREATURE, keywords=[Keyword.DIVINE, Keyword.RADIANT],
       group=CHANNEL_DIVINITY,
       trigger="an enemy drops your ally or damages your unconscious ally",
       on=(
           Trigger(Dropped, _ally_dropped_by_enemy, "an enemy drops an ally"),
           Trigger(DamageRolled, _hurt_my_unconscious_ally,
                   "an enemy damages your unconscious ally"),
       ))
def f1364b(c: Cast) -> None:
    """Both printed halves are declared. `Dropped` carries `source`, so the
    triggering enemy is nameable from the first; the second is asked of
    `DamageRolled`, whose `source` is the same field."""
    c.flat(5 + c.level // 2, dtype=DamageType.RADIANT, on=c.trigger.source)


_granted("f1374", "f1374b")


@power("f1374b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you make a skill check and dislike the result",
       on=Trigger(SkillCheck, _my_check, "you make a skill check"))
def f1374b(c: Cast) -> None:
    """`SkillCheck` is a `Decision`, so the die is down but the outcome is
    not yet acted on -- which is exactly where `c.boost_check` belongs."""
    c.boost_check(c.wis_mod)


_granted("f1375", "f1375b")


@power("f1375b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE_HEAL,
       group=CHANNEL_DIVINITY)
def f1375b(c: Cast) -> None:
    """"Can spend a healing surge" -- theirs, so `c.may` asks them."""
    if c.may("spend a healing surge", who=c.target):
        c.surge(on=c.target)
    for defence in DEFENCES:
        c.bonus(defence, 2, on=c.target, until=When.EONT, kind="power")


_granted("f1376", "f1376b")


@power("f1376b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       out_of_combat=True)
def f1376b(c: Cast) -> None:
    """Two rolls on a knowledge check. Nothing in a fight turns on one."""


_granted("f1377", "f1377b")


@power("f1377b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1377b(c: Cast) -> None:
    """"The next attack that hits the target" is a one-shot watcher rather
    than `c.vulnerable`: vulnerability is a standing property and would pay
    out on every blow, and the dice are rolled when the blow lands rather
    than now."""
    victim = c.target
    if victim is None:
        return

    def on_hit(ev: Any) -> None:
        if ev.target == victim:
            c.flat(c.roll("1d6"), on=victim)

    c.watch(Hit, on_hit, on=c.me, until=When.EONT, once=True,
            label=f"{c.ref} mark")


_granted("f1378", "f1378b")


@power("f1378b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY,
       keywords=[Keyword.DIVINE, Keyword.RADIANT], group=CHANNEL_DIVINITY,
       todo=("c.reroll_ones()",))
def f1378b(c: Cast) -> None:
    """Rerolls damage dice that come up 1 or 2 on radiant powers.
    `c.reroll_damage` rolls the whole expression twice, which is a
    different and stronger rule; six rows want the one that rerolls the
    low dice. The light is scenery."""


_granted("f1379", "f1379b")


@power("f1379b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1379b(c: Cast) -> None:
    """"You and each ally in the burst": the ally pool already holds the
    caster, so there is no separate `c.first` line for yourself."""
    for defence in DEFENCES:
        c.bonus(defence, 2, on=c.target, until=When.SONT, kind="power")


_granted("f1385", "f1385b")


@power("f1385b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(5), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="a healing power restores an ally to maximum hit points",
       on=Trigger(Healed, _overheals_my_ally, "an ally is healed to full"))
def f1385b(c: Cast) -> None:
    """The surplus is only knowable *before* the hit points go on, and
    `resolve.heal` announces `Healed` exactly there -- `ev.hp` is the total
    before and `ev.amount` the offer, so the overflow is arithmetic. A
    moment later the event has been rewritten to what actually landed and
    the surplus is gone."""
    ev = c.trigger
    health = c.world.get(ev.target, Health)
    if health is None:
        return
    excess = ev.amount - (health.max_hp - ev.hp)
    if excess > 0:
        c.temp_hp(excess, on=ev.target)


_granted("f1386", "f1386b")


@power("f1386b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.IMPLEMENT,
                 Keyword.ZONE],
       group=CHANNEL_DIVINITY)
def f1386b(c: Cast) -> None:
    """One square of zone, placed where it does most good: an unoccupied
    square within 5 with the most allies standing beside it, since an ally
    has to step in and end its turn there. The payout is a `TurnEnd`
    watcher because nothing else announces "ends its turn within"."""
    c.spend_surge(on=c.me)
    value = c.surge_value()
    here = c.here
    free = [sq for sq in spread({here}, 5) if not c.in_squares([sq])]
    spot = max(
        free,
        key=lambda sq: len(c.in_squares(spread({sq}, 1), side="ally")),
        default=here,
    )
    c.zone([spot], label=c.ref, until=When.EONT)

    def on_turn_end(ev: Any) -> None:
        if ev.actor in c.in_squares([spot], side="ally"):
            c.heal(value, on=ev.actor)

    c.watch(TurnEnd, on_turn_end, on=c.me, until=When.EONT,
            label=f"{c.ref} light")


_granted("f1401", "f1401b")


@power("f1401b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you hit an enemy with a melee attack",
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"))
def f1401b(c: Cast) -> None:
    c.temp_hp(5, on=c.me)
    c.bonus("skill:athletics", 5, on=c.me, until=When.EONT, kind="power")


_granted("f1403", "f1403b")


@power("f1403b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(2), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.FIRE], group=CHANNEL_DIVINITY,
       trigger="you miss an enemy with a melee or ranged attack",
       on=Trigger(Miss, _my_miss, "you miss with a melee or ranged attack"),
       dropped=("c.bonus(dtype=)",))
def f1403b(c: Cast) -> None:
    """"You or one ally", so the caster is the answer when the burst is
    empty. The extra fire damage is dropped: a damage bonus carries no
    type, and ten rows want the same argument."""
    who = c.target if c.target is not None else c.me
    c.bonus(WILL, 2, on=who, until=When.EONT)


_granted("f1407", "f1407b")


@power("f1407b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(3), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY, dropped=("query.keywords_of(effect)",))
def f1407b(c: Cast) -> None:
    """The save and its payout play. The narrowing to a charm, fear or
    psychic effect is dropped: those are keywords on the hold rather than
    conditions, `c.save(against=)` matches a label fragment and an
    effect's label is its source ref, so a word like "charm" there would
    be silently false in every fight."""
    if c.save(on=c.target):
        c.temp_hp(c.cha_mod, on=c.target)


_granted("f1409", "f1409b")


@power("f1409b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=CloseBurst(10),
       target=ONE_ALLY, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="an enemy damages you",
       on=Trigger(DamageRolled, _enemy_damages_me, "an enemy damages you"))
def f1409b(c: Cast) -> None:
    c.temp_hp(5, on=c.target)


_granted("f1413", "f1413b")


@power("f1413b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(3), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1413b(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.target)
    c.shift(1, who=c.target)


_granted("f1414", "f1414b")


@power("f1414b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBlast(3), target=ONE_CREATURE,
       keywords=[Keyword.CHARM, Keyword.DIVINE, Keyword.IMPLEMENT],
       group=CHANNEL_DIVINITY, attack=Attack(Ability.WIS, vs=WILL))
def f1414b(c: Cast) -> None:
    """The card itself omits the one-per-encounter line that every other
    card in this batch prints, but its parent calls it a `cf:avenger-f2`
    power, so it draws on the same budget and carries the group.

    Undead only, so the blast is declared over one creature and the row
    passes over anything else."""
    if not c.is_kind("undead"):
        return
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


_granted("f1425", "f1425b")


@power("f1425b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you are hit by an attack that deals elemental damage",
       on=Trigger(Hit, _elemental_hit_on_me,
                  "you are hit by an elemental attack"))
def f1425b(c: Cast) -> None:
    """The damage type is read off the attacking power's keywords: `Hit`
    is announced before the damage is rolled, so there is no `dtype` on
    the event to ask."""
    pick = c.choose(list(ELEMENTS), "resist which type")
    if pick is not None:
        c.resist(5, pick, on=c.me, until=When.EONT)


_granted("f1427", "f1427b")


@power("f1427b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1427b(c: Cast) -> None:
    """"From the target to yourself or vice versa": theirs first, because
    that is what the card is for. `c.transfer` rebuilds the hold rather
    than ending it and writing a fresh one, which is why the save it is
    still owed survives the move."""
    if c.target is None:
        return
    theirs = [e for e in c.world.effects.of(c.target) if e.when is When.SAVE_ENDS]
    if theirs:
        c.transfer(theirs[0], to=c.me)
        return
    mine = [e for e in c.world.effects.of(c.me) if e.when is When.SAVE_ENDS]
    if mine:
        c.transfer(mine[0], to=c.target)


_granted("f1430", "f1430b")


@power("f1430b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1430b(c: Cast) -> None:
    c.conceal(on=c.target, until=When.EONT)


_granted("f1432", "f1432b")


@power("f1432b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE, keywords=DIVINE,
       group=CHANNEL_DIVINITY, dropped=("c.restore_use(group=)",))
def f1432b(c: Cast) -> None:
    """Bloodied only, and the kill is the creature's remaining hit points
    taken as untyped damage rather than a separate verb, so everything
    that watches a creature going down still fires.

    The "otherwise" clause -- you may use another channel divinity power
    this encounter -- is dropped: the budget is a group rather than a row,
    and `c.restore_use` hands back one named ref."""
    if c.target is None or not c.bloodied():
        return
    health = c.world.get(c.target, Health)
    if health is not None and 0 < health.hp <= 5 + c.level // 2:
        c.flat(health.hp, on=c.target)


_granted("f1435", "f1435b")


@power("f1435b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(2), target=EACH_ENEMY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1435b(c: Cast) -> None:
    """"You and each enemy in the burst", and the two halves are different
    conditions, so the enemy pool is declared and the caster's own
    immobilisation is the once-per-power line."""
    if c.first:
        c.immobilized(on=c.me, until=When.EONT)
    if c.target is not None:
        c.slowed(on=c.target, until=When.EONT)


_granted("f1437", "f1437b")


@power("f1437b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=Ranged(5),
       target=ONE_CREATURE, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="a creature within 5 squares makes a saving throw",
       on=Trigger(SavingThrow, _save_near_me, "a creature makes a save"))
def f1437b(c: Cast) -> None:
    """Both branches are printed and both are laid on the triggering
    creature, not on `c.target` -- the card says "the triggering creature"
    and the burst would otherwise pick somebody else."""
    who = c.trigger.actor
    if c.trigger.saved:
        c.bonus("save", 2, on=who, until=When.ENCOUNTER, once=True)
    else:
        c.penalty("save", 2, on=who, until=When.ENCOUNTER, once=True)


_granted("f1439", "f1439b")


@power("f1439b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY, dropped=("c.escape()",))
def f1439b(c: Cast) -> None:
    """The saving-throw half plays. Escaping a grab is the other choice and
    is dropped: `c.grab` sets a relation and nothing rolls to break one.

    The three named effects are picked by asking whether the ally is
    actually carrying one of those conditions, not by `c.save(against=)`:
    that matches a fragment of the hold's *label*, which is the ref of
    whatever laid it, so the condition's own word never appears there."""
    who = c.target
    if who is None:
        return
    wanted = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)
    if any(c.is_(cond, on=who) for cond in wanted):
        c.save(on=who)


_granted("f1441", "f1441b")


@power("f1441b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY, todo=("c.on_revive()",))
def f1441b(c: Cast) -> None:
    """Pays out when somebody comes back up in the same fight. `Dropped`
    announces going down and `Healed` announces the hit points, but the
    unconscious condition is cleared inside `Health` without a word, so the
    moment this card is printed for does not exist. `f609` is blocked on
    the same absence."""


_granted("f1444", "f1444b")


@power("f1444b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY, out_of_combat=True)
def f1444b(c: Cast) -> None:
    """Rerolls a knowledge check. A check, not a fight."""


_granted("f1446", "f1446b")


@power("f1446b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Ranged(10),
       target=ONE_CREATURE, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="a creature within 10 squares makes a death saving throw",
       on=Trigger(SavingThrow, _death_save_near_me, "a death saving throw"))
def f1446b(c: Cast) -> None:
    """`turns.py` rolls the death save with `against="death"`, which is the
    only thing that tells one apart from an ordinary save. The bonus is
    applied the way `f600b` applies one -- the die is already down when the
    event is announced, so it is rerolled with the bonus on."""
    c.reroll_save(bonus=10)


_granted("f1448", "f1448b")


@power("f1448b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Ranged(5),
       target=ONE_ALLY, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="an ally within 5 squares takes damage",
       on=Trigger(DamageRolled, _ally_takes_damage, "an ally takes damage"))
def f1448b(c: Cast) -> None:
    """`DamageRolled` is the interrupt window: the number exists and has
    not landed. Your own 5 is `c.flat`, which goes on raw -- "can't be
    reduced in any way" is what a flat application already is."""
    c.reduce(5, c.trigger)
    c.flat(5, on=c.me)



_granted("f1450", "f1450b")


@power("f1450b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       todo=("c.on_reroll()",))
def f1450b(c: Cast) -> None:
    """Hands back the use of whatever power granted a reroll, when the
    reroll came out worse. Nothing announces that a roll was a reroll, so
    there is no moment to answer; twelve rows want the same."""


_granted("f1452", "f1452b")


# -- the standalone feats ---------------------------------------------------


@power("f1366", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.BUILDS",))
def f1366(c: Cast) -> None:
    """Adds an option to a hybrid class entry. A hybrid entry is a build
    the chassis does not record, and nothing in a fight reads one."""


def _daily_hit(me: int):  # noqa: ANN202
    def when(ev: Any) -> bool:
        return ev.attacker == me and _usage(ev.power) is Usage.DAILY

    return when


@power("f1367", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1367(c: Cast) -> None:
    """"Saving throws against ongoing damage" is a real narrowing here and
    not a guess: `Cast.save` hands the modifier lookup a context carrying
    `ongoing`, so the penalty can ask."""
    me = c.me
    daily = _daily_hit(me)

    def on_hit(ev: Any) -> None:
        if daily(ev):
            c.penalty("save", 2, on=ev.target, until=When.ENCOUNTER,
                      when=lambda ctx: bool(ctx.get("ongoing")))

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f1368", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1368(c: Cast) -> None:
    me = c.me
    daily = _daily_hit(me)

    def on_hit(ev: Any) -> None:
        if daily(ev):
            c.penalty(WILL, 2, on=ev.target, until=When.ENCOUNTER)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f1369", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1369(c: Cast) -> None:
    """"Against you" only, which the attack context answers through its
    target. The fear keyword is flavour with nothing reading it here."""
    me = c.me
    daily = _daily_hit(me)

    def on_hit(ev: Any) -> None:
        if daily(ev):
            c.penalty("attack", 1, on=ev.target, until=When.ENCOUNTER,
                      when=lambda ctx: ctx.get("target") == me)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f1371", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.BUILDS",))
def f1371(c: Cast) -> None:
    """Knowing two arcane utility powers of each level and choosing between
    them after a rest. Which rows a character knows is settled by its
    chassis, and nothing on a board holds a second list."""


@power("f1372", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1372(c: Cast) -> None:
    """A trait with a watcher rather than a declared trigger: the damage
    bonus stands all fight and only the attack half waits on a point."""
    me = c.me
    necrotic = lambda ctx: Keyword.NECROTIC in _keywords(ctx.get("power", ""))  # noqa: E731
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=necrotic)

    def on_point(ev: Any) -> None:
        if ev.actor == me:
            c.bonus("attack", 1, on=me, until=When.EONT, kind="feat",
                    when=necrotic)

    c.watch(ActionPointSpent, on_point, on=me, until=When.ENCOUNTER)


@power("f1383", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1383(c: Cast) -> None:
    """Relays telepathy between allies. Communication, not a fight."""


@power("f1387", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1387(c: Cast) -> None:
    """Two rolls on Perception, sensing magic, and a list of rituals."""


@power("f1388", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1388(c: Cast) -> None:
    """Declared on `Moved` and not on `MoveStart`: the square this row
    steps into is the one the enemy just left, and only `Moved` carries
    `from_`. Adjacency is asked of that square rather than of where the
    enemy now stands, which is the whole point of the printed line."""
    me = c.me

    def on_move(ev: Any) -> None:
        if getattr(ev, "kind_", "") != "shift" or ev.actor == me:
            return
        if team(c.world, ev.actor) == team(c.world, me):
            return
        if not has_combat_advantage(c.world, me, ev.actor):
            return
        if ev.from_ in spread({c.here}, 1):
            c.shift(1, to=ev.from_)

    c.watch(Moved, on_move, on=me, until=When.ENCOUNTER)


@power("f1389", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.borrow_feature()",))
def f1389(c: Cast) -> None:
    """The two bonus clauses play. Using a creature's mount powers "as if
    you had" another feat is dropped -- that feat is named in prose and
    there is nothing to point `c.feat` at.

    Armed once, so a mount taken later in the fight does not get the
    bonus; the printed line is a standing property of the pair."""
    for beast in [c.mount(), *c.companions()]:
        if beast is None:
            continue
        if not c.is_kind("natural", on=beast) and not c.is_kind("beast", on=beast):
            continue
        c.bonus("speed", 2, on=beast, until=When.ENCOUNTER, kind="feat")
        c.bonus(AC, 1, on=beast, until=When.ENCOUNTER, kind="feat")


@power("f1390", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_second_wind()",))
def f1390(c: Cast) -> None:
    """The healing-power half plays off `Healed`, whose `source` is the
    healer. The Heal-check half is dropped: a second wind is an action
    rather than a power and announces nothing to hang a save on."""
    me = c.me

    def on_heal(ev: Any) -> None:
        if (
            ev.source == me
            and ev.target != me
            and team(c.world, ev.target) == team(c.world, me)
        ):
            c.save(on=ev.target)

    c.watch(Healed, on_heal, on=me, until=When.ENCOUNTER)


@power("f1391", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1391(c: Cast) -> None:
    """Healing during a short rest. A rest is between fights."""


@power("f1392", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1392(c: Cast) -> None:
    """Rituals and alchemy. A workshop, not a fight."""


@power("f1393", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.extend_shift()", "c.extend_move()"))
def f1393(c: Cast) -> None:
    """One extra square on every shift and every teleport a power grants.
    Both are distances a row names when it moves you; nothing lengthens
    one from the outside, and twelve rows between the two symbols want
    it."""


@power("f1394", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1394(c: Cast) -> None:
    """Languages, a Diplomacy bonus, rituals and scribing."""


@power("f1395", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1395(c: Cast) -> None:
    """"Before or after" the opportunity attack, and after is the half an
    event can answer -- so both outcomes are watched, since a missed
    opportunity attack still buys the step. `opportunity` rides on `Hit`
    and `Miss` as a plain attribute, not a field."""
    me = c.me

    def on_swing(ev: Any) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.shift(1)

    c.watch(Hit, on_swing, on=me, until=When.ENCOUNTER)
    c.watch(Miss, on_swing, on=me, until=When.ENCOUNTER)


@power("f1396", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.stay_hidden()",))
def f1396(c: Cast) -> None:
    """Staying hidden and staying invisible through an attack that misses
    everything. `c.hide` and `c.invisible` set the state and the attack
    clears it from inside the resolver, so there is no seam between "the
    attack missed" and "you were given away" to hold the state across."""


@power("f1397", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1397(c: Cast) -> None:
    """The flying half is gated on `c.moving_as`, which is the live
    question -- `Movement.modes` would only say the character *could*
    fly."""
    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.moving_as("fly", on=me))

    def on_hit(ev: Any) -> None:
        if ev.attacker != me:
            return
        words = _keywords(ev.power)
        if Keyword.THUNDER in words or Keyword.LIGHTNING in words:
            c.slide(1, on=ev.target)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f1398", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.amplify_bonus()", "c.mark_penalty()"))
def f1398(c: Cast) -> None:
    """Two clauses and neither has a handle. Raising every defence bonus
    your own powers hand out means editing a modifier somebody else laid,
    and the mark's -2 is a constant in `conditions.Rules` rather than a
    modifier a row can reach."""


@power("f1402", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1402(c: Cast) -> None:
    """"Until you move" is held as a flag the gate reads rather than an
    effect something has to end: `Moved` sets it and `TurnStart` clears
    it, so the bonus is live from the top of the turn until the first
    step and comes back next turn without being re-laid."""
    me = c.me
    moved = {"yes": False}

    def on_move(ev: Any) -> None:
        if ev.actor == me:
            moved["yes"] = True

    def on_turn(ev: Any) -> None:
        if ev.actor == me:
            moved["yes"] = False

    c.watch(Moved, on_move, on=me, until=When.ENCOUNTER)
    c.watch(TurnStart, on_turn, on=me, until=When.ENCOUNTER)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: not moved["yes"] and _wielding(c, "axe", "hammer"),
    )


@power("f1405", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1405(c: Cast) -> None:
    c.resist(5 + c.level // 2, DamageType.PSYCHIC, on=c.me,
             until=When.ENCOUNTER)


@power("f1406", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.escape()", "c.ignore_condition(rules=)"))
def f1406(c: Cast) -> None:
    """The combat-advantage half plays, gated on actually squeezing. Two
    clauses are dropped: escaping a grab for a minor is `c.grant_action`'s
    known blind spot -- it understands shift and stand and silently eats
    anything else -- and squeezing's -5 to attacks is a constant in
    `conditions.Rules`, not a modifier a row can cancel."""
    me = c.me
    c.no_advantage(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.is_(Condition.SQUEEZING, on=me),
    )


@power("f1408", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_power()",))
def f1408(c: Cast) -> None:
    """Skill bonuses that last as long as a racial power does. The power
    is named in prose with no ref, so there is nothing to watch and no
    duration to tie the bonus to."""


@power("f1410", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_power()",))
def f1410(c: Cast) -> None:
    """Temporary hit points whenever the same prose-named racial power is
    used. Same absence as f1408."""


@power("f1411", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.proficiency()", "spec.weapon_ref()"))
def f1411(c: Cast) -> None:
    """Proficiency and damage with three named weapons. Neither half can
    be said: what a character may pick up is settled in `chargen`, and the
    weapons reach the spec as printed names rather than refs -- none of
    the three is a weapon group, so a gate on one would be silently false
    forever."""


@power("f1415", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.proficiency()", "spec.weapon_ref()"))
def f1415(c: Cast) -> None:
    """Two more named weapons, blocked the same way as f1411."""


@power("f1423", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f1423(c: Cast) -> None:
    """Multiclass: a skill, an implement permission, and one use of
    another class's feature. `cf:artificer-f2` is a ref but no row in the
    tree carries it, so `c.grant_row` has nothing to hand over; the other
    two clauses are build-time."""
