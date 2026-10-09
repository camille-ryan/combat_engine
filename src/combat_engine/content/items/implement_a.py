"""Implement-slot magic items, heroic tier: their Properties and Powers.

Nothing here declares an implement. The ladder, the enhancement bonus, the
price, the critical rider and the base-item restriction are columns in
`game.db` and are laid on by `engine/equipment.py`; what is written here is
only the part that needs a body.

Three things shape the whole file.

* **"using this implement" cannot be gated.** Neither context carries the
  item. Since the character is holding the implement for as long as the
  property is armed, every such rider is written always-on. That
  over-applies only for somebody carrying two implements of which one is
  magical.

  What the contexts *do* carry has grown, and the list that stood here was
  a season out of date. The damage context is `target`, `power`, `dtype`,
  `dtypes`, `crit`, `opportunity`, `charge`, `granted_by`, `granted_via`
  and -- both added since -- `advantage` and `ranged`; the attack context
  is that plus `attacker`, `branch`, `action_point` and `hand`. The old
  note said the damage side was thin and that `ranged` lived only on the
  attack side, and two rows in this file were written around a gate that
  is now perfectly readable.
* **"Class X can use this as a Y implement"** is `c.as_implement`, and the
  class half is not enforced: the item was dealt to whoever holds it.
* **`c.enhancement`** is the item's own plus, which a great many of these
  lines are equal to.

**An item's blocks name one another's rows.** A wand's Property and its
Power are separate refs on one page and, for the whole wand family here,
they are about the same row: `i1832x1` and `i1832p1` both resolved to
`p1166`, `i1836` to `p1169`, `i1822` to `p1457`. So where the Power block
resolved and the Property block did not, the Property's ref is the
Power's -- `i1821x1` is `i1821p1`'s `p1164`, `i1823x1` is `i1823p1`'s
`p1333`, `i1831x1` is `i1831p1`'s `p1167`, and `i2614p1` is `i2614x1`'s
`p463`. Four blocks were written off this join rather than waiting for the
ETL. Check the sibling block before believing a `spec.power_ref()`.

Four gaps account for most of the markers, and each is named with the
symbol it wants rather than approximated:

* **`spec.power_ref()`** -- the brief prints a prose power name where a ref
  belongs, and a name is the one thing this project may not go and look up.
  Nine blocks, down from twenty-six: the label matcher now reads a
  bracketed class, so most of "as the <class>'s <name> power" resolves and
  `_as_row` says the rest. The example that used to stand here was itself a
  printed name and has been taken out.
* **`c.as_weapon()`** -- the mirror of `c.as_implement`: a rod that is also
  a mace.
* **`c.power_range()`** -- lengthen another power's printed range.
* **`c.class_feature()`** -- ask after, or modify, a class feature that is
  not a row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    AttackDeclared,
    Bloodied,
    Cast,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageType,
    Dropped,
    Event,
    Healed,
    Hit,
    Initiative,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    Powers,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    SavingThrow,
    Summoned,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    World,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    by_ranged,
    get,
    power,
    query,
    spread,
    targets_me,
)

ITEM = "item"

#: The printed allowance `cf:paladin-f0` is: `dsl._group_spent` refuses a
#: row of this group once any sibling has been used, so restoring that
#: sibling is what "regain the use of the feature" comes to. Written out
#: in each body rather than shared, because `audit._wants_expended` reads
#: the body's own source to decide whether to spend a sibling for it.
_CHANNEL = CHANNEL_DIVINITY

#: The five energy keywords a resistance can be named against, and the
#: damage type each one means.
_ELEMENTS = {
    Keyword.ACID: DamageType.ACID,
    Keyword.COLD: DamageType.COLD,
    Keyword.FIRE: DamageType.FIRE,
    Keyword.LIGHTNING: DamageType.LIGHTNING,
    Keyword.THUNDER: DamageType.THUNDER,
}

#: "Immobilize, petrify, slow or restrain" -- one printed list.
_HOLDS = (
    Condition.IMMOBILIZED,
    Condition.PETRIFIED,
    Condition.SLOWED,
    Condition.RESTRAINED,
)


def _struck(c: Cast) -> int | None:
    """The creature the triggering attack was aimed at.

    A row triggered by **your own** hit is aimed at `ev.attacker`, which is
    you, so it falls through to the auto-targeter and can pick a different
    enemy than the one just hit. Every "use this power when you hit" row
    reads the event instead.
    """
    foe = getattr(c.trigger, "target", None)
    return foe if foe is not None else c.target


def _reach_of(ref: str | None) -> str:
    p = get(ref or "")
    return p.reach.kind if p is not None and p.reach is not None else ""


def _keywords_of(ref: str | None) -> frozenset[Keyword]:
    p = get(ref or "")
    return frozenset(p.keywords) if p is not None else frozenset()


def _of_type(dtype: DamageType):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") == dtype

    return gate


def _with_keywords(*words: Keyword):  # noqa: ANN202
    """Damage gate: the power that dealt this printed all of `words`."""

    def gate(ctx: dict[str, Any]) -> bool:
        kw = _keywords_of(ctx.get("power"))
        return all(w in kw for w in words)

    return gate


def _save_keywords(*words: Keyword):  # noqa: ANN202
    """Save gate: the row that laid the effect printed one of these.
    `durations.keywords_of` reads them back off the effect's label."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("keywords", ())))

    return gate


def _crit_by_me(c: Cast, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == c.me and getattr(ev, "critical", False)


def _my_side(world: World, me: int, who: int | None) -> bool:
    return who is not None and query.team(world, who) is query.team(world, me)


def _ally_crit(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    return (
        who is not None
        and who != me
        and bool(getattr(ev, "critical", False))
        and _my_side(world, me, who)
    )


def _fire_by_me(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "source", None) == me
        and getattr(ev, "dtype", None) == DamageType.FIRE
    )


def _psychic_on_me(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "dtype", None) == DamageType.PSYCHIC
    )


def _melee_on_my_side(world: World, me: int, ev: Event) -> bool:
    """An enemy hits an ally of yours -- or your companion -- in melee."""
    who = getattr(ev, "target", None)
    return who is not None and who != me and _my_side(world, me, who) and by_melee(
        world, me, ev
    )


def _i_bloodied_one(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return (
        getattr(ev, "source", None) == me
        and who is not None
        and not _my_side(world, me, who)
    )


def _enemy_saving(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return who is not None and who != me and not _my_side(world, me, who)


def _vs_will(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "vs", None) == WILL


def _vs_ac_or_fort(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "vs", None) in (AC, FORT)


def _immobilising(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "condition", None) is Condition.IMMOBILIZED


def _my_area_power(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and _reach_of(
        getattr(ev, "power", "")
    ) in ("area_burst", "close_blast", "close_burst")


def _my_summoning(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and Keyword.SUMMONING in _keywords_of(
        getattr(ev, "power", "")
    )


def _elemental_on_ally(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me or not _my_side(world, me, who):
        return False
    return bool(_keywords_of(getattr(ev, "power", "")) & frozenset(_ELEMENTS))


def _attacking_with(ref: str):  # noqa: ANN202
    """`AttackDeclared` gate: the swing being declared is that row's."""

    def gate(world: World, me: int, ev: Event) -> bool:
        return getattr(ev, "attacker", None) == me and getattr(ev, "power", "") == ref

    return gate


def _damage_from(ref: str):  # noqa: ANN202
    """`DamageApplied` gate: you dealt it and that row is what dealt it.

    `detail` is the ref for anything a body deals -- it is the same string
    the damage context hands over as `power`.
    """

    def gate(world: World, me: int, ev: Event) -> bool:
        return getattr(ev, "source", None) == me and getattr(ev, "detail", "") == ref

    return gate


def _is_row(ref: str):  # noqa: ANN202
    """Damage or attack gate: the blow came from that exact row."""

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") == ref

    return gate


HIT_BY_ME = Trigger(Hit, by_me, "you hit an enemy with this implement")


def _as_row(c: Cast, ref: str) -> None:
    """"As the <class>'s <name> power": hand the swing to that row.

    `dsl.usable` refuses a row the creature does not know, so
    `c.grant_attack(ref=)` alone is silent for every one of these. The row
    is lent for the length of the one swing and given straight back --
    `c.grant_row` returns None for a row the character already has, so a
    wizard's own copy is never touched.
    """
    borrowed = c.grant_row(ref, until=When.ENCOUNTER)
    try:
        c.grant_attack(c.me, ref=ref)
    finally:
        if borrowed is not None:
            c.world.effects.end(borrowed, "the lent row is given back")


def _pick(c: Cast, radius: int) -> int:
    """"You or an ally within N squares" -- the caster is in the pool."""
    pool = [c.me, *c.within(radius, side="ally")]
    chosen = c.choose(pool, "who gains it")
    return chosen if chosen is not None else c.me


# -- level 2 ----------------------------------------------------------------


@power(
    "i1056x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1056x1(c: Cast) -> None:
    """Both halves. The gate is "if you have the `cf:wizard-arcanist-f0c2`
    class feature", and a feature is a row like any other: `Powers.known`
    is the list, so having one is an ordinary membership test rather than
    something only `chargen` could answer.

    Asked once, when the property arms, because a character does not
    acquire a class feature mid-fight."""
    for d in (FORT, REF, WILL):
        c.bonus(d, 1, kind="item", on=c.me, until=When.ENCOUNTER)
    known = c.world.get(c.me, Powers)
    if known is not None and "cf:wizard-arcanist-f0c2" in known.known:
        c.bonus(AC, 1, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1203p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def i1203p1(c: Cast) -> None:
    """Paragon numbers are out of scope; this is the heroic 5."""
    for foe in c.within(1, side="enemy"):
        c.flat(5, dtype=DamageType.FIRE, on=foe)
    c.shift(2)


@power(
    "i1216x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1216x1(c: Cast) -> None:
    """The damage context carries `dtype`, so "a poison damage roll" is a
    gate the engine can actually read."""
    c.bonus(
        "damage",
        c.enhancement,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_of_type(DamageType.POISON),
    )


@power(
    "i1399x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1399x1(c: Cast) -> None:
    """`c.ignore_resistance(insubstantial=True)` is exactly the printed
    piercing, and the old marker was written before it existed.

    `amount=0` keeps it to that one clause: the blanket call waives every
    resistance as well, which this line does not say. The two halves of
    the gate are the power's own reach and the damage context's
    `advantage`, both readable there now. Being insubstantial needs no
    test of its own -- the mod is consulted nowhere but on the halving
    line, so a solid target never reaches it."""
    c.ignore_resistance(
        0,
        on=c.me,
        until=When.ENCOUNTER,
        insubstantial=True,
        when=lambda ctx: _reach_of(ctx.get("power")) == "melee"
        and bool(ctx.get("advantage")),
    )


@power(
    "i1583x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1583x1(c: Cast) -> None:
    """`c.call_companion(at=)` moves the companion you already have, which
    is the only way to put it in a named square."""

    def follow(ev: Hit) -> None:
        if not _crit_by_me(c, ev):
            return
        mine = c.companion()
        pos = c.world.get(ev.target, Position)
        if mine is None or pos is None:
            return
        for sq in spread({pos.square}, 1):
            if sq != pos.square and not c.in_squares([sq]):
                c.call_companion(at=sq)
                return

    c.watch(Hit, follow, until=When.ENCOUNTER)


@power(
    "i1583p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    trigger="you hit an enemy adjacent to your spirit companion",
    on=HIT_BY_ME,
)
def i1583p1(c: Cast) -> None:
    """The adjacency gate is only applied when there *is* a companion on the
    board: the item is a totem, so a wielder without one is a board
    limitation rather than a creature the row should refuse."""
    foe = _struck(c)
    if foe is None:
        return
    mine = c.companion()
    if mine is not None and not c.adjacent_to(mine, foe):
        return
    c.surge(on=c.me)
    mates = [a for a in c.within(2, of=foe, side="ally") if a != c.me]
    if mates and c.may("spend a healing surge", who=mates[0]):
        c.surge(on=mates[0])


@power(
    "i1587p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this ki focus",
    on=HIT_BY_ME,
)
def i1587p1(c: Cast) -> None:
    """"Until it hits you" is not a duration the engine has, so it is the
    encounter clock plus a watch that ends the hold on the first blow the
    target lands on the wearer."""
    foe = _struck(c)
    if foe is None:
        return
    blind = c.no_cover(on=foe, until=When.ENCOUNTER)

    def repaid(ev: Hit) -> None:
        if ev.attacker == foe and ev.target == c.me:
            c.end_effect(blind)

    c.watch(Hit, repaid, until=When.ENCOUNTER, once=True)


@power(
    "i1647x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1647x1(c: Cast) -> None:
    """The class half is not enforced: the item was dealt to whoever holds
    it."""
    c.as_implement(on=c.me)


@power(
    "i1875x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i1875x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i1875p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1875p1(c: Cast) -> None:
    """The level ceilings are chargen arithmetic; `c.prepare` does the swap
    and puts the displaced power back."""
    book = c.spellbook()
    if not book:
        return
    pick = c.choose(book, "which power to prepare")
    if pick:
        c.prepare(pick)


@power(
    "i1920p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="an ally you can see scores a critical hit",
    on=Trigger(Hit, _ally_crit, "an ally you can see scores a critical hit"),
    dropped=("c.uncrit()",),
)
def i1920p1(c: Cast) -> None:
    """Giving the critical back is the price of the surge and nothing can
    downgrade a hit that has already been declared critical, so the ally
    gets the surge for free here."""
    mate = getattr(c.trigger, "attacker", None)
    if mate is not None:
        c.surge(on=mate)


@power(
    "i1923x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i1923x1(c: Cast) -> None:
    """Two skill-check bonuses and nothing else."""


@power(
    "i1923p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    trigger="you hit an enemy with a primal implement power using this totem",
    on=HIT_BY_ME,
)
def i1923p1(c: Cast) -> None:
    """`c.surge(bonus=)` is the printed "and regain extra hit points equal
    to"."""
    foe = _struck(c)
    near = set(c.within(1, side="ally"))
    if foe is not None:
        near |= set(c.within(1, of=foe, side="ally"))
    mate = next(iter(sorted(near)), None)
    if mate is not None:
        c.surge(on=mate, bonus=c.enhancement)


@power(
    "i1930x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1930x1(c: Cast) -> None:
    """"The first ... during an encounter" is `once=True` on the watch."""

    def burn(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        c.flat(c.wis_mod, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, burn, until=When.ENCOUNTER, once=True)


@power(
    "i1930p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1930p1(c: Cast) -> None:
    """A weapon is not a targetable thing, so the bonus goes on whoever is
    holding it -- the caster or an adjacent ally. Plain "a bonus", so
    untyped."""
    pool = [c.me, *c.within(1, side="ally")]
    who = c.choose(pool, "whose weapon")
    c.bonus(
        "damage",
        c.enhancement,
        on=who if who is not None else c.me,
        until=When.EONT,
        once=True,
    )


@power(
    "i1943p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="an attack with this orb hits the target's Fortitude",
    on=HIT_BY_ME,
    dropped=("Hit.vs",),
)
def i1943p1(c: Cast) -> None:
    """`Hit` carries attacker, target, power and critical -- not the defence
    that was attacked, which only `AttackRolled` knows."""
    foe = _struck(c)
    if foe is not None:
        c.slowed(on=foe, until=When.SAVE_ENDS)


@power(
    "i1951p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you deal fire damage to an enemy",
    on=Trigger(DamageApplied, _fire_by_me, "you deal fire damage to an enemy"),
)
def i1951p1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is not None:
        c.ongoing(5, DamageType.FIRE, on=foe)


@power(
    "i1975p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1975p1(c: Cast) -> None:
    """"Against one effect until that effect ends" is one saving throw's
    worth, which is `once=True`."""
    c.bonus(
        "save",
        c.enhancement,
        kind="power",
        on=_pick(c, 5),
        until=When.ENCOUNTER,
        once=True,
    )


@power(
    "i2118p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a creature with a power using this rod",
    on=HIT_BY_ME,
)
def i2118p1(c: Cast) -> None:
    foe = _struck(c)
    for other in c.enemies():
        if other != foe and c.can_see(other):
            c.curse(on=other)
            return


@power(
    "i2274p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal attack power using this totem",
    on=HIT_BY_ME,
)
def i2274p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.prone(on=foe)


@power(
    "i2295x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.boost_roll()",),
)
def i2295x1(c: Cast) -> None:
    """Adds 1 to a d6 `x_m4421a6` rolls. Nothing reaches inside a row's
    own roll to change it.

    Re-aimed onto the name nine other rows already use for that, since
    the ref the property is gated on is given and the naming gap was
    never the hold. `c.boost_check` is the near neighbour and answers a
    `SkillCheck` trigger only."""


@power(
    "i2297x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2297x1(c: Cast) -> None:
    """`c.curse` hangs a relation, and `relations.set` announces it, so the
    curse being laid is a readable event."""

    def laid(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.CURSED_BY or ev.source != c.me:
            return
        for d in (FORT, REF, WILL):
            c.bonus(d, 1, kind="power", on=c.me, until=When.EONT)

    c.watch(RelationSet, laid, until=When.ENCOUNTER)


@power(
    "i2298x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2298x1(c: Cast) -> None:
    def laid(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.CURSED_BY or ev.source != c.me:
            return
        c.bonus(AC, 1, kind="power", on=c.me, until=When.SONT)

    c.watch(RelationSet, laid, until=When.ENCOUNTER)


@power(
    "i2299x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reroll_crit_die()",),
)
def i2299x1(c: Cast) -> None:
    """The critical rider is a column applied by `engine/equipment.py`, and
    `c.reroll_damage` keeps the higher of two rolls rather than the second
    of them -- the opposite of what is printed."""


@power(
    "i2308p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an implement power using this rod",
    on=HIT_BY_ME,
)
def i2308p1(c: Cast) -> None:
    kind = c.choose(
        [DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING],
        "which energy",
    )
    amount = 5 + c.con_mod
    c.resist(amount, kind or DamageType.FIRE, on=c.me, until=When.EONT)
    for mate in c.within(1, side="team"):
        c.resist(amount, kind or DamageType.FIRE, on=mate, until=When.EONT)


@power(
    "i2314x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2314x1(c: Cast) -> None:
    """`Dropped.source` is who struck the killing blow, which is the only
    event that says "you reduced it" rather than "it took damage"."""

    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(c.enhancement, on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER)


@power(
    "i2318p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.fell_might()",),
)
def i2318p1(c: Cast) -> None:
    """Gives back a pact boon's once-per-encounter charge.

    **Re-aimed off `spec.power_ref()`.** The brief does print the thing by
    name and give no ref, but that is not the gap: what the card restores is
    `cf:warlock-f1s4`'s boon charge, and the compendium describes that boon in
    the warlock class text rather than filing it as a row. `cf:warlock-f1s4`
    is the feature and it is a row; the charge inside it is not, which is
    exactly what that row's own `c.fell_might()` marker says.

    `c.restore_use` is ready for the moment there is a use to restore. Four
    other rows wait on the same charge, so this joins a group that means
    something instead of a group that cannot be satisfied."""


@power(
    "i2320p1",
    level=2,
    cls=ITEM,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an implement power using this rod",
    on=HIT_BY_ME,
)
def i2320p1(c: Cast) -> None:
    """"An artificer healing power on an ally" is read as any healing you
    do to somebody else: `Healed` carries a source and a target and no
    power, so that is as close as the event gets."""

    def paid(ev: Healed) -> None:
        if ev.source == c.me and ev.target != c.me:
            c.heal(c.enhancement, on=c.me)

    c.watch(Healed, paid, until=When.EONT)


@power(
    "i2341p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a cursed enemy with an attack power using this rod",
    todo=("c.active_vestige()",),
)
def i2341p1(c: Cast) -> None:
    """Vestiges are a pact's rotating set of granted rows and nothing
    models one."""


@power(
    "i2407p1",
    level=2,
    cls=ITEM,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy",
    on=HIT_BY_ME,
    dropped=("c.clear_shrouds()",),
)
def i2407p1(c: Cast) -> None:
    """The shrouds are laid on the new enemy but not lifted off the old
    one: `c.spend_shrouds` invokes them, which is a different thing, and
    nothing simply removes them."""
    foe = _struck(c)
    if foe is None:
        return
    count = c.shrouds(on=foe)
    others = [e for e in c.within(10, side="enemy") if e != foe]
    if not count or not others:
        return
    for _ in range(count):
        c.shroud(on=others[0])


@power(
    "i2601x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2601x1(c: Cast) -> None:
    """The class half is not enforced."""
    c.as_implement(on=c.me)


@power(
    "i2605p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("AttackDeclared.origin",),
)
def i2605p1(c: Cast) -> None:
    """`c.widen_areas` is the wrong verb -- it grows the burst, catching a
    different set of squares -- but `c.add_target` is the right one, and
    the old marker predates it.

    A watcher's own `Cast` is long off the stack, so `dsl.running_below`
    falls through to whatever row is running *now*, which is exactly the
    burst being declared. `AttackDeclared` is announced from inside that
    row's target loop, so an appended creature is one its body is then
    called for.

    What is dropped is the shape of the reach: the event names an
    attacker, a target, a power and a defence, and not the square the
    burst was centred on -- the same field `i1832x1` wants off `Hit`. So
    "adjacent to the burst" is read as "adjacent to somebody in it",
    which misses a creature standing beside an empty edge square.
    `c.add_target` refuses a creature already in the list, so the loop
    simply tries the next one.

    Paragon's second and third creatures are out of scope."""
    spent: list[int] = []

    def widen(ev: AttackDeclared) -> None:
        if spent or ev.attacker != c.me:
            return
        if _reach_of(ev.power) not in ("area_burst", "close_blast", "close_burst"):
            return
        for foe in c.within(1, of=ev.target, side="enemy"):
            if c.add_target(foe):
                spent.append(1)
                return

    c.watch(AttackDeclared, widen, until=When.EONT)


@power(
    "i2606p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.reroll_damage_dice()",),
)
def i2606p1(c: Cast) -> None:
    """Re-aimed from a `todo` to a `dropped`: `c.reroll_damage(keyword=)`
    is a real reroll narrowed to the printed keyword, so refusing the
    whole row threw away the half the engine can say.

    Two clauses go. It rolls the whole expression twice and keeps the
    higher, where the card rerolls a counted number of dice and makes
    you keep the new result even when it is worse -- so this is the
    generous reading. And there is no `once=`, so it stands for the rest
    of the turn rather than for the one power the free action answers."""
    c.reroll_damage(keyword=Keyword.FIRE, on=c.me, until=When.EOT)


@power(
    "i2609x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2609x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i2609p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2609p1(c: Cast) -> None:
    """The sustain is held on the caster and re-lays the concealment denial
    each time it is paid for, because `c.no_cover` is per-enemy and there
    is nothing board-wide to keep alive."""

    def deny() -> None:
        for foe in c.enemies():
            c.no_cover(on=foe, until=When.EONT)

    deny()
    c.on_sustain(
        c.effect(
            "ignores concealment", until=When.SUSTAIN, on=c.me, sustain=MINOR
        ),
        lambda: deny() if c.spend_points(1) else None,
    )


@power(
    "i2611p1",
    level=2,
    cls=ITEM,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.transform_item()",),
)
def i2611p1(c: Cast) -> None:
    """The base item is a column. Nothing swaps one for another mid-fight,
    and the second critical rider printed in the header is that column's
    other half."""


@power(
    "i2614x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2614x1(c: Cast) -> None:
    """`p463` is a ref now, and the damage context carries `power`, so the
    gate is the ordinary one. This is an *item* bonus on top of the
    enhancement that row's own Special already adds -- two different
    kinds, so they stack."""
    c.bonus(
        "damage", c.enhancement, on=c.me, until=When.ENCOUNTER, kind="item",
        when=lambda ctx: ctx.get("power") == "p463",
    )


@power(
    "i2614p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use p463",
    on=Trigger(DamageApplied, _damage_from("p463"), "p463 goes off"),
)
def i2614p1(c: Cast) -> None:
    """The ref is `p463`, read off this item's other block, which already
    names it. `c.add_target` is the verb.

    **`PowerUsed` is the wrong window for it, and looks like the right
    one.** `add_target` appends to whatever `dsl.running_below` finds,
    and `dsl.use` calls `cast.used()` *above* `_RUNNING.append(cast)` --
    so during the announcement the row is not on the stack and there is
    nothing to append to. `PowerUsed.targets` is a `list(...)` copy, so
    reaching for it instead changes nothing either. The same reasoning
    `i1828x1` writes out: the consequence is readable where the
    declaration is not.

    So the window is the row going off. `p463` rolls no attack -- its
    whole body is one `c.flat` -- so its damage is the first thing it
    emits from inside the target loop, and a row answering that runs
    nested with the loop still walking. The appended creature is one the
    body is then called for.

    "No target can be more than 5 squares from any other" is, for the two
    the heroic tier allows, the pool within 5 of the one already hit.
    Paragon's third target is out of scope."""
    first = getattr(c.trigger, "target", None)
    if first is None:
        return
    for foe in c.within(5, of=first, side="enemy"):
        if foe != first and c.distance(foe) <= 20 and c.can_see(foe):
            c.add_target(foe)
            return


@power(
    "i2631x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2631x1(c: Cast) -> None:
    """A skill bonus and a language."""


@power(
    "i2641p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def i2641p1(c: Cast) -> None:
    """"Take 10" is not a bonus, so each creature's own roll is read back
    off `Initiative` and the difference handed to `c.initiative`, which is
    the one thing that moves a creature in the order after the roll."""

    def take_ten(who: int) -> None:
        ini = c.world.get(who, Initiative)
        rolled = ini.rolled if ini is not None else 0
        if rolled < 10:
            c.initiative(10 - rolled, on=who)

    take_ten(c.me)
    for mate in c.within(5, side="team"):
        take_ten(mate)


@power(
    "i2769p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a divine attack power using this symbol",
    on=HIT_BY_ME,
)
def i2769p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.push(c.enhancement, on=foe)


@power(
    "i2772p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
)
def i2772p1(c: Cast) -> None:
    """The twin of `i2304p1`, and the marker was aimed at the wrong thing.

    The printed line does not name a *row* at all: the allowance is the
    `CHANNEL_DIVINITY` group, refused by `dsl._group_spent` once any
    sibling has been used, so handing a use back is restoring whichever
    sibling spent it. No ref is wanted and none was ever missing.

    `c.first` because the importer gave this row a target and the effect
    is about the wielder, not about it."""
    if not c.first:
        return
    spent = c.expended(group=_CHANNEL)
    pick = c.choose(spent, f"{c.ref}: which expended row comes back") if spent else None
    if pick is not None:
        c.restore_use(pick)


@power(
    "i2773p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.check_bonus()",),
)
def i2773p1(c: Cast) -> None:
    """The attack-roll half is written; "ability check or skill check" has
    no modifier key, so the ally always spends it on the swing."""
    mate = next(iter(c.within(10, side="ally")), None)
    if mate is not None:
        c.bonus(
            "attack",
            c.enhancement,
            kind="power",
            on=mate,
            until=When.ENCOUNTER,
            once=True,
        )


@power(
    "i2778p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=HIT_BY_ME,
)
def i2778p1(c: Cast) -> None:
    c.bonus("attack", 2, kind="power", on=c.me, until=When.EONT, once=True)


@power(
    "i2780p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack made with this holy symbol",
    on=HIT_BY_ME,
    dropped=("Healed.power",),
)
def i2780p1(c: Cast) -> None:
    """"By your encounter and daily powers" cannot be told from any other
    healing: `Healed` names a source and a target and no power. Paragon
    numbers are out of scope."""

    def extra(ev: Healed) -> None:
        if ev.source == c.me:
            c.heal(c.roll("1d6"), on=ev.target)

    c.watch(Healed, extra, until=When.EOT)


@power(
    "i2792p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with an attack delivered by this holy symbol",
    on=HIT_BY_ME,
)
def i2792p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.penalty("save", 2, on=foe, until=When.EONT)
    c.no_healing(on=foe, until=When.EONT)


@power(
    "i2793p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack delivered by this symbol",
    on=HIT_BY_ME,
)
def i2793p1(c: Cast) -> None:
    c.save(on=_pick(c, 10), bonus=c.enhancement)


@power(
    "i2809x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2809x1(c: Cast) -> None:
    """The class half is not enforced."""
    c.as_implement(on=c.me)


@power(
    "i2819x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2819x1(c: Cast) -> None:
    """"Charm and illusion effects" is the pair of keywords the row that
    laid the hold printed, which the save context carries."""
    c.bonus("save", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
            when=_save_keywords(Keyword.CHARM, Keyword.ILLUSION))


@power(
    "i2900x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_any_sustain()", "c.tome_powers()"),
)
def i2900x1(c: Cast) -> None:
    """`c.on_sustain` answers the sustaining of an effect *this row* made,
    and this pays out when some other row is sustained. The second half --
    a tome holding two chosen daily powers -- has no store."""


@power(
    "i2900p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    todo=("c.tome_powers()",),
)
def i2900p1(c: Cast) -> None:
    """Nothing holds the two powers the tome contains."""


@power(
    "i2911p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="an enemy hits your spirit companion or a nearby ally in melee",
    on=Trigger(Hit, _melee_on_my_side, "an enemy hits an ally in melee"),
)
def i2911p1(c: Cast) -> None:
    """A companion is on your side and in the target pool, so the one
    predicate covers both halves of the printed trigger."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    mate = getattr(ev, "target", None)
    if foe is None or mate is None or c.distance(mate) > 5:
        return
    c.flat(c.wis_mod, dtype=DamageType.THUNDER, on=foe)
    c.push(c.enhancement, on=foe)


@power(
    "i2962x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.power_range()",),
)
def i2962x1(c: Cast) -> None:
    """A row's reach is header data and nothing lengthens another row's."""


@power(
    "i2982x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2982x1(c: Cast) -> None:
    """The class half is not enforced."""
    c.as_implement(on=c.me)


@power(
    "i3181p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you",
    on=Trigger(Hit, targets_me, "an enemy hits you"),
)
def i3181p1(c: Cast) -> None:
    """"When you attack it using this rod" cannot be gated, so the
    advantage stands for every swing until the end of your next turn."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.EONT, to="me")


@power(
    "i3182x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    
)
def i3182x1(c: Cast) -> None:
    """A rod usable as a melee weapon, functioning as a mace.

    `i1656x1`'s sibling, and the same mace profile for the same reason: the
    card names the weapon it functions as and prints no numbers of its own.
    """
    c.as_weapon(damage="1d8", group="mace", proficiency=2)
@power(
    "i3193x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i3193x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i3195x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i3195x1(c: Cast) -> None:
    """A skill-check bonus and a short-rest ritual."""


@power(
    "i3195p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3195p1(c: Cast) -> None:
    """Recalling the item to your hand moves an object, not a creature, and
    has no consequence a fight can see."""


@power(
    "i3503x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3503x1(c: Cast) -> None:
    """Ranged or area **divine** powers only, which is narrower than what this
    laid.

    It vetoed the window whatever opened it, so it also covered walking away --
    which the printed line does not, and which made the property **stronger
    than its card**. `c.no_provoke` takes a `when=` now.

    **The gate tests only the keyword.** `Power.provokes_on` opens this window
    for `ranged`, `area_burst` and `wall` and nothing else, so a window that
    exists is already a ranged or area attack; re-checking the shape would be a
    second copy of that rule. `ctx["why"]` reads `"<ref> is a ranged power"`, so
    the provoking row is its first token.

    "With this implement" is not tested, for the reason `f3742` gives: the
    implement in hand is not on the context, and a divine implement attack made
    while holding this symbol is made with it."""
    def divine_ranged(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("why", "")).split(" ", 1)[0])
        return row is not None and Keyword.DIVINE in row.keywords

    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=divine_ranged)


@power(
    "i569x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i569x1(c: Cast) -> None:
    """Plain "extra damage", so untyped."""
    c.bonus(
        "damage",
        1 + c.enhancement // 2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and c.bloodied(on=ctx["target"]),
    )


@power(
    "i577x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i577x1(c: Cast) -> None:
    """The damage context carries `target`, so the victim's type words are
    the gate. Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and "construct" in c.kinds_of(on=ctx["target"]),
    )


@power(
    "i577p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you hit an enemy with a primal implement power using this totem",
    on=HIT_BY_ME,
)
def i577p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.flat(5, dtype=DamageType.FIRE, on=foe)


@power(
    "i578x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i578x1(c: Cast) -> None:
    """The attack context carries `attacker`, and `c.suffering` is exactly
    "subject to an effect caused by you"."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(
            d,
            2,
            kind="item",
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("attacker") in c.suffering(),
        )


@power(
    "i928x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i928x1(c: Cast) -> None:
    """Poison by the laying row's keyword, with the burn's own type as
    the fallback for an ongoing poison laid by a row printing none."""
    c.bonus(
        "save", 2, kind="item", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: Keyword.POISON in ctx.get("keywords", ())
        or ctx.get("dtype") is DamageType.POISON,
    )


@power(
    "i928p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=Trigger(Hit, both(by_me, by_melee), "you hit in melee with this focus"),
)
def i928p1(c: Cast) -> None:
    """"Your Strength or Wisdom modifier" is the wielder's choice, taken as
    the better of the two. Paragon numbers are out of scope."""
    foe = _struck(c)
    if foe is not None:
        c.ongoing(2 + max(c.str_mod, c.wis_mod), DamageType.POISON, on=foe)


# -- level 3 ----------------------------------------------------------------


@power(
    "i1029p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you bloody an enemy with an attack",
    on=Trigger(Bloodied, _i_bloodied_one, "you bloody an enemy"),
)
def i1029p1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.SAVE_ENDS, to="me")


@power(
    "i1035p1",
    level=3,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
    trigger="you make a melee attack using this ki focus",
    on=Trigger(
        AttackDeclared, both(by_me, by_melee), "you make a melee attack"
    ),
)
def i1035p1(c: Cast) -> None:
    c.deals(DamageType.NECROTIC, until=When.EOT, on=c.me, implement=True)


@power(
    "i1162x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1162x1(c: Cast) -> None:
    """"The first saving throw it makes against that condition" is
    `once=True`: the penalty is spent by whichever save comes first."""

    def held(ev: ConditionApplied) -> None:
        if ev.source != c.me or ev.condition not in _HOLDS:
            return
        c.penalty("save", 2, on=ev.target, until=When.ENCOUNTER, once=True)

    c.watch(ConditionApplied, held, until=When.ENCOUNTER)


@power(
    "i1202p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are first bloodied during an encounter",
    on=Trigger(Bloodied, about_me, "you are bloodied"),
)
def i1202p1(c: Cast) -> None:
    """"First bloodied" is the encounter usage: a creature is bloodied once
    on the way down and the row has one use."""
    c.bonus("damage", c.str_mod, kind="power", on=c.me, until=When.EONT)


@power(
    "i1260p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
)
def i1260p1(c: Cast) -> None:
    """"The next power ... during this turn" is latched on the first ref
    seen, so the rider rides every target of that one power and nothing
    after it. Paragon numbers are out of scope."""
    latch: list[str] = []

    def bite(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if not latch:
            latch.append(ev.power)
        if ev.power == latch[0]:
            c.ongoing(5, DamageType.POISON, on=ev.target)

    c.watch(Hit, bite, until=When.EOT)


@power(
    "i1283x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1283x1(c: Cast) -> None:
    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.shift(1)

    c.watch(Dropped, felled, until=When.ENCOUNTER)


@power(
    "i1298x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1298x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.FIRE, Keyword.IMPLEMENT),
    )


@power(
    "i1298p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
)
def i1298p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1166")


@power(
    "i1344x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1344x1(c: Cast) -> None:
    def flatten(ev: Hit) -> None:
        if _crit_by_me(c, ev):
            c.prone(on=ev.target)

    c.watch(Hit, flatten, until=When.ENCOUNTER)


@power(
    "i1344p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    trigger="you hit with a power that has the force keyword",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.FORCE)), "you hit with a force power"
    ),
)
def i1344p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.slide(c.enhancement, on=foe)


@power(
    "i1345x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1345x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.FORCE),
    )


@power(
    "i1345p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
)
def i1345p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p463")


@power(
    "i1355p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=Trigger(Hit, both(by_me, by_melee), "you hit in melee with this focus"),
)
def i1355p1(c: Cast) -> None:
    """The flight is granted only for the move it pays for, so "you must
    land at the end of this movement" needs nothing said: the mode expires
    with the turn and the creature is back on the floor."""
    c.no_provoke(on=c.me, until=When.EOT)
    c.mode("fly", c.enhancement, on=c.me, until=When.EOT)
    c.move(c.enhancement, at="fly")


@power(
    "i1534x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1534x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.FIRE, Keyword.IMPLEMENT),
    )


@power(
    "i1534p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
)
def i1534p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1458")


@power(
    "i1555p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack power using this rod",
    on=HIT_BY_ME,
)
def i1555p1(c: Cast) -> None:
    """The reaction is armed rather than offered: the whole clause is "the
    next time that enemy misses you", which is one watch with its own
    latch. `c.conceal` is board-wide, so "against that enemy" over-applies
    for the one turn it lasts."""
    foe = _struck(c)
    if foe is None:
        return
    spent: list[int] = []

    def missed(ev: Miss) -> None:
        if spent or ev.attacker != foe or ev.target != c.me:
            return
        spent.append(1)
        c.shift(3)
        c.conceal(on=c.me, until=When.EONT)

    c.watch(Miss, missed, until=When.ENCOUNTER)


@power(
    "i1612x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1612x1(c: Cast) -> None:
    """A plain "+2 bonus" with no type word, so untyped. "Melee attacks" is
    the power's reach, which the damage context does carry. Paragon
    numbers are out of scope."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or _reach_of(ctx.get("power")) != "melee":
            return False
        return c.is_(Condition.DAZED, on=foe) or c.is_(Condition.STUNNED, on=foe)

    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=gate)


#: The monk's Flurry of Blows, which is five rows and not one: each monastic
#: tradition grants its own, and a card saying "your flurry of blows power"
#: means whichever you have. All five are declared.
_FLURRIES = frozenset({"p7448", "p11207", "p13123", "p16131", "p16132"})


@power(
    "i1612p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use one of p7448, p11207, p13123, p16131, p16132",
    on=Trigger(
        PowerUsed,
        lambda w, me, ev: ev.actor == me and ev.power in _FLURRIES,
        "you use that class power",
    ),
)
def i1612p1(c: Cast) -> None:
    """Bloodied enemies the flurry damages stop healing for a round.

    **The trigger is a family, not a row**, which is why it had nothing to
    declare `on=` against: the monk's flurry is one of five, each granted by a
    different monastic tradition, and the card means whichever one you have.
    `_FLURRIES` is that set -- all five are declared -- and the predicate asks
    whether the power used is any of them.

    "During this turn ... you damage" is a second watcher rather than a
    clause on the trigger: the trigger is the *use*, and the damage lands
    once per target afterwards. Bloodied is read at the moment the blow
    lands, which is what the card asks.
    """
    me = c.me

    def stops_healing(ev: DamageApplied) -> None:
        # **`detail`, not `power`.** `DamageApplied` carries no `power` field
        # at all -- its own docstring says `detail` is "what dealt it, a power
        # ref where one did" -- so a gate on `ev.power` is false in every
        # fight and the row would look written and do nothing.
        if ev.source != me or getattr(ev, "detail", "") not in _FLURRIES:
            return
        if c.bloodied(on=ev.target):
            c.no_healing(on=ev.target, until=When.EONT)

    c.watch(DamageApplied, stops_healing, until=When.EOT, on=me, label=c.ref)


@power(
    "i1656x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    
)
def i1656x1(c: Cast) -> None:
    """A rod that is also a mace, as well as an implement.

    The card gives no die or proficiency of its own -- "functions as a
    mace" -- so it takes a mace's: a simple one-handed weapon, 1d8, +2
    proficiency. The enhancement is the rod's own, which is the printed
    "applies its enhancement bonus to attack and damage rolls".

    It stays an implement: `c.as_weapon` adds a profile and takes nothing
    away, so `c.as_implement`'s side of the item is untouched.
    """
    c.as_weapon(damage="1d8", group="mace", proficiency=2)
@power(
    "i1656p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    trigger="you hit a target with an attack using this rod",
    on=HIT_BY_ME,
)
def i1656p1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    foe = _struck(c)
    if foe is None:
        return
    c.damage("1d8", dtype=DamageType.ACID, on=foe)
    c.penalty("attack", 2, on=foe, until=When.EONT)


@power(
    "i1712p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you spend an action point to take an extra action",
    on=Trigger(ActionPointSpent, about_me, "you spend an action point"),
)
def i1712p1(c: Cast) -> None:
    c.save(on=c.me, bonus=c.enhancement)


@power(
    "i1738x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1738x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.LIGHTNING),
    )


@power(
    "i1738p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1738p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p12732")


@power(
    "i1821x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1821x1(c: Cast) -> None:
    """The ref is `p1164`, read off this item's other block -- `i1821p1`
    is that row and the property is about the zone that row lays.

    Doubling a standing zone's bite is still not something anything does,
    but it does not have to be: `Cast.burns` deals the zone's damage with
    `detail=f"{ref} zone"`, so the bite is a readable `DamageApplied` and
    a second helping of the same size doubles it from outside. The
    printed minimum of 2 is the row's own `max(1, wis_mod)` paid twice."""

    def again(ev: DamageApplied) -> None:
        if ev.source == c.me and ev.detail == "p1164 zone" and ev.amount > 0:
            c.flat(max(1, c.wis_mod), dtype=DamageType.FORCE, on=ev.target)

    c.watch(DamageApplied, again, until=When.ENCOUNTER)


@power(
    "i1821p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
)
def i1821p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1164")


@power(
    "i1822x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.movement_tax()",),
)
def i1822x1(c: Cast) -> None:
    """Re-aimed: `p1457` is a ref now, so the naming gap is closed and was
    never the hold. "Each square moved toward you costs 1 extra" is
    difficult terrain that follows one creature and only in one
    direction; `c.zone` is laid on squares and `c.slowed` caps a whole
    move instead."""


@power(
    "i1822p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FEAR, Keyword.IMPLEMENT, Keyword.RADIANT],
)
def i1822p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1457")


@power(
    "i1823x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1823x1(c: Cast) -> None:
    """The ref is `p1333`, read off this item's other block: `i1823p1`
    resolves to it and the property names the same row. The damage
    context carries `power`, so the gate is the one `i2614x1` uses.
    Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_is_row("p1333"),
    )


@power(
    "i1823p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def i1823p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1333")


@power(
    "i1824x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1824x1(c: Cast) -> None:
    """The brief gives this one's ref, so the power can be named outright.
    "Your first attack next turn" is `once=True` on a grant that runs to
    the end of that turn."""

    def linger(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != "p1456":
            return
        c.grants_advantage(on=ev.target, until=When.EONT, to="me", once=True)

    c.watch(Hit, linger, until=When.ENCOUNTER)


@power(
    "i1824p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
)
def i1824p1(c: Cast) -> None:
    """"As the <name> power" with the ref given: the item's row hands the
    swing straight to the named row rather than restating it."""
    _as_row(c, "p1456")


@power(
    "i1826x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("DamageApplied.from_attack",),
)
def i1826x1(c: Cast) -> None:
    """Re-aimed: the ref is `p1333`'s neighbour `p1458`, read off this
    item's other block, so the naming gap is closed and was never the
    hold.

    What holds it is telling that row's two blows apart. It deals its
    hit with `c.damage` and its rebound with `c.flat`, both as
    `DamageApplied(source=me, target=victim, dtype=FIRE,
    detail="p1458")` -- identical on every field the event carries. Only
    the rebound is "damage from attacking you", and splashing both would
    give the at-will a second area it does not print. The damage context
    knows `from_attack`; the event does not carry it."""


@power(
    "i1826p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
)
def i1826p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1458")


@power(
    "i1828x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1828x1(c: Cast) -> None:
    """The ref is given now, so the push is writable.

    Hung on `Hit` rather than on `PowerUsed`: the use is announced before
    the body runs, so a push laid there would happen before the damage
    the printed line waits for. "Used through this wand" cannot be gated,
    as the file's opening note says, so it is written always-on."""
    me = c.me

    def shove(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "p463":
            c.push(1, on=ev.target)

    c.watch(Hit, shove, until=When.ENCOUNTER)


@power(
    "i1828p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
)
def i1828p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p463")


@power(
    "i1831x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1831x1(c: Cast) -> None:
    """The ref is `p1167`, read off this item's other block. `query.
    cover_waived` is handed the whole attack context, `power` included,
    so `c.ignore_cover(when=)` narrows to the one row."""
    c.ignore_cover(
        on=c.me, until=When.ENCOUNTER, when=_is_row("p1167")
    )


@power(
    "i1831p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
)
def i1831p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1167")


@power(
    "i1832x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("Hit.origin",),
)
def i1832x1(c: Cast) -> None:
    """The ref is given now; the origin square is not, and the earlier
    note on this row was wrong. `c.origin` is *this* row's own aim, and a
    watcher on another row's `Hit` is handed `attacker`, `target`,
    `power`, `critical` and `branch` -- the square the burst was centred
    on is nowhere on the event."""


@power(
    "i1832p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
)
def i1832p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1166")


@power(
    "i1836x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reshape_area()",),
)
def i1836x1(c: Cast) -> None:
    """The ref is given, but a row's reach is header data: `c.widen_areas`
    grows a burst and nothing turns one shape into another."""


@power(
    "i1836p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
)
def i1836p1(c: Cast) -> None:
    _as_row(c, "p1169")


@power(
    "i1927p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1927p1(c: Cast) -> None:
    """`cf:paladin-f0` is declared now, and its own docstring says what
    "the use of it" means: the feature lays nothing and grants no power,
    and the once-a-fight allowance is `group=CHANNEL_DIVINITY` on the rows
    that spend it, refused by `dsl._group_spent` the moment any sibling
    has been used. So handing the use back is handing back whichever
    sibling was spent -- the idiom `c.expended`'s own docstring was
    written for, and `p11291` already uses.

    Returns without spending the item's day if nothing has been used,
    which is the Requirement the line implies. The old marker named the
    naming gap, which has closed; it had already."""
    spent = c.expended(group=_CHANNEL)
    pick = c.choose(spent, f"{c.ref}: which expended row comes back") if spent else None
    if pick is not None:
        c.restore_use(pick)


@power(
    "i1949p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.range_to()",),
)
def i1949p1(c: Cast) -> None:
    """Halving the measured distance to one creature is not a modifier
    anything reads: `query.distance` is geometry."""


@power(
    "i1949p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a ranged attack on the enemy this orb has marked out",
    on=Trigger(
        AttackDeclared, both(by_me, by_ranged), "you make a ranged attack"
    ),
)
def i1949p2(c: Cast) -> None:
    """The concealment and cover half is `c.ignore_cover`; line of sight
    and line of effect are geometry with no override. Which enemy the
    orb's encounter power marked out is not tracked, since that row is
    itself unwritten."""
    c.ignore_cover(on=c.me, until=When.EOT)


@power(
    "i1952p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(5),
    target=ONE_CREATURE,
    trigger="an enemy within 5 squares of you saves against ongoing damage",
    on=Trigger(SavingThrow, _enemy_saving, "an enemy makes a saving throw"),
    dropped=("SavingThrow.ongoing",),
)
def i1952p1(c: Cast) -> None:
    """`SavingThrow.against` is a free-text label, so "against ongoing
    damage" cannot be told from any other save and the row answers the
    first one an enemy in range makes."""
    ev = c.trigger
    who = getattr(ev, "actor", None)
    if who is None or c.distance(who) > 5:
        return
    c.unsave(ev)


@power(
    "i1960p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack made with this orb",
    todo=("c.extend_effect()",),
)
def i1960p1(c: Cast) -> None:
    """A live effect's duration is fixed when it is applied and nothing
    lengthens one afterwards."""


@power(
    "i1962p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an arcane attack power using this orb",
    on=HIT_BY_ME,
)
def i1962p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.push(c.enhancement, on=foe)


@power(
    "i1964x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.dispel_defence()",),
)
def i1964x1(c: Cast) -> None:
    """`c.dispel` destroys a zone outright and rolls nothing against a
    defence, so there is no check for the bonus to apply to."""


@power(
    "i1964p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.sustain_free()",),
)
def i1964p1(c: Cast) -> None:
    """The sustain cost is a field on the effect, set when it was made.
    Nothing pays one off from outside."""


@power(
    "i1967x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i1967x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i1967p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy attack targets your AC or Fortitude",
    on=Trigger(
        AttackDeclared,
        both(targets_me, _vs_ac_or_fort),
        "an enemy attack targets your AC or Fortitude",
    ),
)
def i1967p1(c: Cast) -> None:
    """`AttackDeclared` is a `Decision` announced before the roll and the
    resolver reads the defence back off it, so redirecting the attack is
    an assignment rather than a new verb."""
    ev = c.trigger
    if ev is not None:
        ev.vs = WILL
    if c.points_spent(c.ref) >= 1:
        c.bonus(WILL, 4, on=c.me, until=When.EONT)


@power(
    "i1970x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.initiative_bonus()",),
)
def i1970x1(c: Cast) -> None:
    """`c.initiative` moves a creature in an order that has already been
    rolled; a trait is armed after the rolls, so there is no way to add to
    the check itself."""


@power(
    "i1970p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def i1970p1(c: Cast) -> None:
    c.shift(c.int_mod)
    if c.points_spent(c.ref) >= 1:
        c.restore_use(c.ref)


@power(
    "i1973p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    trigger="you make an attack using this orb",
    on=Trigger(AttackDeclared, by_me, "you make an attack"),
)
def i1973p1(c: Cast) -> None:
    c.deals(DamageType.PSYCHIC, until=When.EOT, on=c.me, implement=True)


@power(
    "i1973p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    trigger="you take psychic damage from an attack",
    on=Trigger(DamageApplied, _psychic_on_me, "you take psychic damage"),
    dropped=("c.suffering_save_ends()",),
)
def i1973p2(c: Cast) -> None:
    """`c.suffering` returns everyone carrying an effect of mine and cannot
    be narrowed to the save-ends ones, so a few enemies under a shorter
    hold are caught too."""
    foes = set(c.enemies())
    for who in c.suffering():
        if who in foes:
            c.flat(5, dtype=DamageType.PSYCHIC, on=who)


@power(
    "i1982p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1982p1(c: Cast) -> None:
    """The reach of the power that landed is in the damage and attack
    contexts and on the ref itself, so "an arcane close blast" is a real
    gate rather than a guess."""

    def flatten(ev: Hit) -> None:
        if ev.attacker != c.me or _reach_of(ev.power) != "close_blast":
            return
        c.prone(on=ev.target)

    c.watch(Hit, flatten, until=When.EOT)


@power(
    "i1983p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def i1983p1(c: Cast) -> None:
    """"Add 5 + the enhancement bonus of the orb" names a type in the
    *amount*, not in the bonus being granted, so this is untyped.
    Typing it after the phrase would be the one thing that must not be
    done: `equipment.armour` lays armour's AC bonus with exactly that
    kind, and the larger of two would win, swallowing the armour's."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 5 + c.enhancement, on=c.me, until=When.EONT)


@power(
    "i1986p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you use your orb of imposition on a creature this orb hit",
    todo=("c.amplify_bonus()",),
)
def i1986p1(c: Cast) -> None:
    """Deepens a saving-throw penalty `cf:wizard-arcanist-f0` laid.

    The brief prints `cf:wizard-arcanist-f0c1` and nothing declares that
    ref; the thing it names is the control leg written inline inside
    `cf:wizard-arcanist-f0`, which chooses a victim, chooses one of that
    victim's save-ends effects and lays `c.penalty("save", wis_mod, ...)`
    gated on that one effect. Both the effect and the size of the penalty
    are locals in its closure, so adding 2 means editing a modifier
    somebody else laid -- and a second, separate penalty would be gated on
    nothing and would bite every save the creature made.

    Re-aimed: the brief does give a ref, so `spec.power_ref()` was the
    wrong thing to be waiting for and kept this row in a queue the fix
    would never reach. What is missing is the deepening."""


@power(
    "i1989p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with an attack with this implement",
    on=HIT_BY_ME,
)
def i1989p1(c: Cast) -> None:
    """`c.transfer` moves a live hold intact, ending it on the old
    subject and rebuilding it on the new one with its conditions, its
    burn and the saving throw it is still owed -- this line's verb
    exactly. The old marker said nothing hands back the effects standing
    on a creature; `world.effects.of` does, and this file already reaches
    the same object in `_as_row`.

    Narrowed to holds an enemy laid, because the printed line is about
    getting rid of something and a chooser offered the party's own buffs
    would hand one of them to the enemy. `c.transfer` refuses a hold
    carrying a relation or a subscription and says so in its own
    docstring, so those never reach the list."""
    foe = _struck(c)
    if foe is None:
        return
    live = [
        eff
        for who in (c.me, *c.within(5, side="ally"))
        for eff in c.world.effects.of(who)
        if not eff.ended
        and not eff.relations
        and not eff.subs
        and (eff.conditions or eff.ongoing)
        and not _my_side(c.world, c.me, eff.source)
    ]
    if not live:
        return
    by_label = {str(eff): eff for eff in live}
    pick = c.choose(sorted(by_label), f"{c.ref}: which effect moves")
    if pick is not None:
        c.transfer(by_label[pick], to=foe)


@power(
    "i2106x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2106x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i2133x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2133x1(c: Cast) -> None:
    def spill(ev: Dropped) -> None:
        if ev.source != c.me:
            return
        for foe in c.within(1, side="enemy"):
            if foe != ev.actor:
                c.flat(2 + c.enhancement, on=foe)
                return

    c.watch(Dropped, spill, until=When.ENCOUNTER)


@power(
    "i2133p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("c.hit_this_turn()",),
)
def i2133p1(c: Cast) -> None:
    """"An at-will attack" is taken as the basic, which is the one row
    every creature is certain to have. Nothing records who was hit earlier
    this turn, so the target restriction is gone."""
    c.basic(on=c.target)


@power(
    "i2289x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_pact_boon()",),
)
def i2289x1(c: Cast) -> None:
    """A pact boon is a class feature that pays out when a cursed enemy
    drops, and nothing announces one."""


@power(
    "i2289p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2289p1(c: Cast) -> None:
    """`c.aura` marks out the squares but carries no teeth, so the bite is
    a watch on the turn ending. Paragon numbers are out of scope."""

    def sting(ev: TurnEnd) -> None:
        who = ev.actor
        if who != c.me and who in c.enemies() and c.adjacent(who):
            c.flat(5, dtype=DamageType.PSYCHIC, on=who)

    c.watch(TurnEnd, sting, until=When.ENCOUNTER)


@power(
    "i2291p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use p1333",
    on=Trigger(
        AttackDeclared, _attacking_with("p1333"), "p1333 declares its swing"
    ),
)
def i2291p1(c: Cast) -> None:
    """The twin of `i2614p1`, with the same verb and the same reason for
    not using `PowerUsed`; only the ref took one more step to reach.

    This item has no second block to read it off. `i1823` does: its
    property and its power are one row between them, its power resolves
    to `p1333`, and the token its property prints for that row is the
    token this row's trigger prints. So the join is `i1823x1`'s, applied
    across two items rather than within one -- worth knowing, because if
    it is wrong this row is inert rather than wrong-headed, which is the
    same shape the marker left behind.

    `p1333` does roll an attack, so the nested window is the declaration
    rather than the damage: `resolve.attack` announces it from inside
    the target loop, which is where `c.add_target` needs to be standing.
    Paragon's third target is out of scope, and the printed line puts no
    distance between the targets -- only `p1333`'s own Ranged 10."""
    first = getattr(c.trigger, "target", None)
    if first is None:
        return
    for foe in c.within(10, side="enemy"):
        if foe != first and c.can_see(foe):
            c.add_target(foe)
            return


@power(
    "i2296x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_pact_boon()",),
)
def i2296x1(c: Cast) -> None:
    """Nothing announces a pact boon."""


@power(
    "i2304p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with a divine attack power using this rod",
)
def i2304p1(c: Cast) -> None:
    """"One extra use of `cf:paladin-f0` during this encounter" comes to
    the same thing `i1927p1` does and is written the same way: the
    allowance is the `CHANNEL_DIVINITY` group, and giving a use back is
    restoring the sibling that spent it.

    `c.first` because the header the importer gave this row carries a
    target and the effect is about the wielder, not about it."""
    if not c.first:
        return
    spent = c.expended(group=_CHANNEL)
    pick = c.choose(spent, f"{c.ref}: which expended row comes back") if spent else None
    if pick is not None:
        c.restore_use(pick)


@power(
    "i2315p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def i2315p1(c: Cast) -> None:
    n = c.enhancement
    c.teleport(n)
    mate = next(iter(c.within(5, side="ally")), None)
    if mate is not None:
        c.teleport(n, who=mate)
    foe = next(iter(c.within(5, side="enemy")), None)
    if foe is not None:
        c.teleport(n, who=foe)


@power(
    "i2332p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a ranged attack using this implement",
    on=Trigger(
        AttackDeclared, both(by_me, by_ranged), "you make a ranged attack"
    ),
)
def i2332p1(c: Cast) -> None:
    """`c.no_provoke` vetoes the window whatever opened it, which for the
    length of one turn is the printed line."""
    c.no_provoke(on=c.me, until=When.EOT)


@power(
    "i2442x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.once_per_round_bonus()",),
)
def i2442x1(c: Cast) -> None:
    """Re-aimed: `c.bonus(dtype=)` exists and is the type of the *extra*
    damage, which is this line exactly, so the typing half was waiting
    for something already there. What is still dropped is the latch --
    it pays out on every qualifying hit rather than once a round per
    enemy."""
    c.bonus(
        "damage",
        4 + c.enhancement,
        dtype=DamageType.NECROTIC,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and c.is_hidden(from_=ctx["target"]),
    )


@power(
    "i2603x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2603x1(c: Cast) -> None:
    """Skill and ability checks, and the line says outright that it is not
    Strength-based attacks."""


@power(
    "i2603p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="an attack with this implement hits",
    on=HIT_BY_ME,
)
def i2603p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.slowed(on=foe, until=When.EONT)


@power(
    "i2621p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(3),
    target=ONE_CREATURE,
    trigger="you hit a nearby enemy with a psychic attack using this staff",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.PSYCHIC)), "you hit with a psychic power"
    ),
)
def i2621p1(c: Cast) -> None:
    """The augment widens the radius rather than adding a second effect, so
    one loop covers both readings."""
    radius = 3 if c.points_spent(c.ref) >= 1 else 1
    for foe in c.within(radius, side="enemy"):
        c.grants_advantage(on=foe, until=When.SAVE_ENDS, to="me")


@power(
    "i2622p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2622p1(c: Cast) -> None:
    """`c.spend_surge` is the surge going with nothing gained for it, which
    is what "but regain no hit points" asks for."""
    c.spend_surge(on=c.me)
    c.temp_hp(2 * c.surge_value(), on=c.me)


@power(
    "i2623x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2623x1(c: Cast) -> None:
    c.bonus(
        "damage", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i2626x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2626x1(c: Cast) -> None:
    """The attack context carries the power's ref, so its keywords are
    readable. Paragon numbers are out of scope."""

    def gate(ctx: dict[str, Any]) -> bool:
        kw = _keywords_of(ctx.get("power"))
        return Keyword.ARCANE in kw and bool(kw & {Keyword.CHARM, Keyword.SLEEP})

    c.bonus("attack", 1, kind="item", on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "i2627x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_sustain(group=)",),
)
def i2627x1(c: Cast) -> None:
    """Re-aimed: `c.use_power` runs the named row from inside this one,
    so conjuring several hands is writable. Folding their sustains into
    one minor action is not -- `c.on_sustain` holds one effect at a
    time -- and that clause is the whole reason the property is worth
    having, so the row stays refused rather than shipping the half that
    makes the wizard pay a minor per hand."""


@power(
    "i2633x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.amplify_bonus()",),
)
def i2633x1(c: Cast) -> None:
    """Deepens one form of `cf:wizard-arcanist-f0`.

    That form is `cf:wizard-arcanist-f0c2`, which is declared: an
    immediate interrupt that reads the attacked defence off
    `AttackDeclared` and lays `c.bonus(vs, con_mod, once=True)` on it. The
    defence it picked is a local in that body, and `PowerResolved` does
    not carry it, so a second bonus laid from here would have to be
    spread across all four defences and would be spent by whichever
    attack came next. Raising the one modifier that was laid is the
    printed sentence, and nothing reaches a stored modifier."""


@power(
    "i2636p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would use an area power",
    on=Trigger(PowerUsed, _my_area_power, "you use an area power"),
)
def i2636p1(c: Cast) -> None:
    """`PowerUsed` fires before the body runs, but targets are chosen
    before the body too, so `ev.targets` is the set of creatures in the
    area and is trustworthy here."""
    for who in getattr(c.trigger, "targets", ()):
        c.slowed(on=who, until=When.EONT)


@power(
    "i2642x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2642x1(c: Cast) -> None:
    """The old note was wrong: `durations` builds a context for the save
    and `holder.total("save", ctx)` is handed it, so the modifier is not
    contextless at all. It carries `conditions` -- the frozenset the
    effect holds -- alongside the `keywords` two other rows in this file
    already gate on, and "against being immobilized or slowed" is that
    set intersected."""
    c.bonus(
        "save", 2, kind="item", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(
            ctx.get("conditions", frozenset())
            & {Condition.IMMOBILIZED, Condition.SLOWED}
        ),
    )


@power(
    "i2642p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="you are immobilized by an attack",
    on=Trigger(
        ConditionApplied,
        both(targets_me, _immobilising),
        "you are immobilized",
    ),
)
def i2642p1(c: Cast) -> None:
    """`ConditionApplied` names its subject `target`, so `targets_me` is
    the predicate and `about_me` would be false forever."""
    c.cure(Condition.IMMOBILIZED, on=c.me)
    c.teleport(5)


@power(
    "i2645x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2645x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER)


@power(
    "i2645p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy targets you with an attack against Will",
    on=Trigger(
        AttackDeclared, both(targets_me, _vs_will), "an enemy attacks your Will"
    ),
)
def i2645p1(c: Cast) -> None:
    n = c.enhancement
    if c.points_spent(c.ref) >= 1:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, n, on=c.me, until=When.SONT)
    else:
        c.bonus(WILL, n, on=c.me, until=When.SONT)


@power(
    "i2655p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i2655p1(c: Cast) -> None:
    c.widen_areas(1, on=c.me, until=When.EOT)


@power(
    "i2713x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2713x1(c: Cast) -> None:
    def bind(ev: Hit) -> None:
        if _crit_by_me(c, ev):
            c.condition(Condition.RESTRAINED, until=When.EONT, on=ev.target)

    c.watch(Hit, bind, until=When.ENCOUNTER)


@power(
    "i2713p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2713p1(c: Cast) -> None:
    """"For your enemies" is the zone plus `c.ignores_difficult_in`, which
    hands your own side a way through the ground you just broke."""
    zone = c.zone(spread({c.here}, 5), difficult=True, until=When.EONT)
    c.ignores_difficult_in(zone, side="team")


@power(
    "i2759p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with a divine attack power using this holy symbol",
    on=HIT_BY_ME,
)
def i2759p1(c: Cast) -> None:
    """The basic attack is aimed at whoever the row is pointed at, not at
    the creature that triggered it -- the printed line does not say they
    are the same. Paragon numbers are out of scope."""
    foe = c.target
    if foe is None or not c.basic(on=foe):
        return
    if c.marked(on=foe):
        c.flat(c.roll("1d10"), on=foe)


@power(
    "i2762p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    todo=("c.extend_effect()",),
)
def i2762p1(c: Cast) -> None:
    """Re-aimed: the feature is `p805` and arrives as a ref now, so the
    naming gap is closed. What is left is the whole of the row -- nothing
    lengthens an effect that is already live, and "even if it would
    normally end" is exactly that."""


@power(
    "i2771x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.power_range()",),
)
def i2771x1(c: Cast) -> None:
    """A row's reach is header data and nothing lengthens another row's."""


@power(
    "i2779p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack made with this holy symbol",
    on=HIT_BY_ME,
)
def i2779p1(c: Cast) -> None:
    c.save(on=_pick(c, 5), bonus=5)


@power(
    "i2808p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_CREATURE,
    trigger="an enemy attacks a nearby ally with an energy power",
    on=Trigger(
        AttackDeclared,
        _elemental_on_ally,
        "an enemy attacks an ally with an energy power",
    ),
)
def i2808p1(c: Cast) -> None:
    """"Against that keyword" is read off the declared attack's own row,
    which is where the keyword lives. Paragon numbers are out of scope."""
    ev = c.trigger
    mate = getattr(ev, "target", None)
    if mate is None or c.distance(mate) > 5:
        return
    for word in _keywords_of(getattr(ev, "power", "")):
        if word in _ELEMENTS:
            c.resist(5, _ELEMENTS[word], on=mate, until=When.ENCOUNTER)
            return


@power(
    "i2876x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2876x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.IMPLEMENT, Keyword.THUNDER),
    )


@power(
    "i2876p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
)
def i2876p1(c: Cast) -> None:
    _as_row(c, "p1169")


@power(
    "i2897x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2897x1(c: Cast) -> None:
    """The bonus is laid as each summon arrives rather than on the ones
    already standing, because a trait is armed before any of them exist."""

    def quicken(ev: Summoned) -> None:
        if ev.actor == c.me:
            c.bonus("speed", 1, kind="item", on=ev.summon, until=When.ENCOUNTER)

    c.watch(Summoned, quicken, until=When.ENCOUNTER)


@power(
    "i2897p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use a summoning power",
    on=Trigger(PowerUsed, _my_summoning, "you use a summoning power"),
    dropped=("c.restrict_action()",),
)
def i2897p1(c: Cast) -> None:
    """The extra move action is handed out at the start of each of your
    turns; "that you can use only to command the creature" cannot be said,
    so it is an unrestricted move action."""

    def each_round(ev: TurnStart) -> None:
        if ev.actor == c.me:
            c.extra_action(MOVE, on=c.me)

    c.watch(TurnStart, each_round, until=When.ENCOUNTER)


@power(
    "i2899x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.tome_powers()",),
)
def i2899x1(c: Cast) -> None:
    """The rider is written for any slowed creature carrying an effect of
    mine, since "a cold power through this tome" is not in the movement
    event. The second paragraph -- two chosen daily powers the tome holds
    -- has no store."""

    def bleed(ev: Moved) -> None:
        who = ev.actor
        if c.is_(Condition.SLOWED, on=who) and who in c.suffering():
            c.flat(c.con_mod, on=who)

    c.watch(Moved, bleed, until=When.ENCOUNTER)


@power(
    "i2899p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
    todo=("c.tome_powers()",),
)
def i2899p1(c: Cast) -> None:
    """Nothing holds the two powers the tome contains."""


@power(
    "i2987x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.curse_damage()",),
)
def i2987x1(c: Cast) -> None:
    """The curse's own damage dice are a class feature's, not this row's,
    and nothing reaches them."""


@power(
    "i3019x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3019x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.COLD, Keyword.IMPLEMENT),
    )


@power(
    "i3019p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
)
def i3019p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1167")


@power(
    "i3025x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3025x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.IMPLEMENT, Keyword.PSYCHIC),
    )


@power(
    "i3025p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
)
def i3025p1(c: Cast) -> None:
    _as_row(c, "p1456")


@power(
    "i3026x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3026x1(c: Cast) -> None:
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.IMPLEMENT, Keyword.RADIANT),
    )


@power(
    "i3026p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FEAR, Keyword.IMPLEMENT, Keyword.RADIANT],
)
def i3026p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1457")


@power(
    "i3027p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.NECROTIC],
)
def i3027p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p416")


@power(
    "i3030x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3030x1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_with_keywords(Keyword.FORCE, Keyword.IMPLEMENT),
    )


@power(
    "i3030p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
)
def i3030p1(c: Cast) -> None:
    """"As the <class>'s <name> power" with the ref given: the item's
    row hands the swing straight to the named row rather than restating
    it."""
    _as_row(c, "p1164")


@power(
    "i3032p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
)
def i3032p1(c: Cast) -> None:
    _as_row(c, "p1459")
