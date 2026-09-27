"""Implement-slot magic items, heroic tier: their Properties and Powers.

Nothing here declares an implement. The ladder, the enhancement bonus, the
price, the critical rider and the base-item restriction are columns in
`game.db` and are laid on by `engine/equipment.py`; what is written here is
only the part that needs a body.

Three things shape the whole file.

* **"using this implement" cannot be gated.** The damage context carries
  `target`, `power`, `opportunity`, `charge`, `dtype` and `crit`, and the
  attack context adds `attacker` and `ranged` -- neither carries the item.
  Since the character is holding the implement for as long as the property
  is armed, every such rider is written always-on. That over-applies only
  for somebody carrying two implements of which one is magical.
* **"Class X can use this as a Y implement"** is `c.as_implement`, and the
  class half is not enforced: the item was dealt to whoever holds it.
* **`c.enhancement`** is the item's own plus, which a great many of these
  lines are equal to.

Four gaps account for most of the markers, and each is named with the
symbol it wants rather than approximated:

* **`spec.power_ref()`** -- the brief prints a prose power name where a ref
  belongs ("as the wizard's scorching burst power"), and a name is the one
  thing this project may not go and look up. Twenty-six blocks.
* **`c.as_weapon()`** -- the mirror of `c.as_implement`: a rod that is also
  a mace.
* **`c.power_range()`** -- lengthen another power's printed range.
* **`c.class_feature()`** -- ask after, or modify, a class feature that is
  not a row.
"""

from __future__ import annotations

from typing import Any

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


def _enemy_bloodied(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return who is not None and who != me and not _my_side(world, me, who)


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
    dropped=("c.class_feature()",),
)
def i1056x1(c: Cast) -> None:
    """The AC half is conditional on a class feature, and nothing can ask
    whether a character has one."""
    for d in (FORT, REF, WILL):
        c.bonus(d, 1, kind="item", on=c.me, until=When.ENCOUNTER)


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
    todo=("c.ignore_insubstantial()",),
)
def i1399x1(c: Cast) -> None:
    """`c.insubstantial` grants the quality and nothing pierces it."""


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
    dropped=("c.end_effect()",),
)
def i1587p1(c: Cast) -> None:
    """"Until it hits you" is not a duration the engine has, and nothing can
    end a live effect early, so this runs to the end of the fight."""
    foe = _struck(c)
    if foe is not None:
        c.no_cover(on=foe, until=When.ENCOUNTER)


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
    todo=("c.boost_row_die()",),
)
def i2295x1(c: Cast) -> None:
    """Adds 1 to a d6 another row rolls. Nothing reaches inside a row's own
    roll to change it."""


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
    for mate in c.within(1, side="ally"):
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
    todo=("spec.power_ref()",),
)
def i2318p1(c: Cast) -> None:
    """`c.restore_use` is the verb; the brief prints the class feature by
    name and never gives its ref."""


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
    todo=("c.extra_area_target()",),
)
def i2605p1(c: Cast) -> None:
    """`c.widen_areas` grows the burst, which catches a different set of
    squares; "also target 1 creature adjacent to it" adds one creature
    outside the area and leaves the area alone."""


@power(
    "i2606p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reroll_damage_dice()",),
)
def i2606p1(c: Cast) -> None:
    """`c.reroll_damage` rolls the whole expression twice and keeps the
    higher; this rerolls a counted number of dice and must keep the new
    result even when it is worse."""


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
    todo=("spec.power_ref()",),
)
def i2614x1(c: Cast) -> None:
    """A damage bonus gated on `ctx["power"]`, which needs the ref of the
    power the brief names only in prose."""


@power(
    "i2614p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()",),
)
def i2614p1(c: Cast) -> None:
    """Same missing ref, plus the retarget."""


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
    for mate in c.within(5, side="ally"):
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
    todo=("spec.power_ref()",),
)
def i2772p1(c: Cast) -> None:
    """An extra use of a class feature is `c.restore_use`, which needs the
    feature's ref; the brief prints only its name."""


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
    dropped=("SavingThrow.keywords",),
)
def i2819x1(c: Cast) -> None:
    """The save modifier is read with no context at all -- `c.save` totals
    `"save"` bare -- so "against charm and illusion effects" cannot narrow
    it and the bonus applies to every saving throw."""
    c.bonus("save", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


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
    todo=("c.as_weapon()",),
)
def i3182x1(c: Cast) -> None:
    """The mirror of `c.as_implement`, which exists; this direction does
    not, and the base item is a column no body can change."""


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
    dropped=("c.no_provoke_ranged()",),
)
def i3503x1(c: Cast) -> None:
    """`c.no_provoke` vetoes the opportunity window whatever opened it, so
    this also covers walking away -- which the printed line does not."""
    c.no_provoke(on=c.me, until=When.ENCOUNTER)


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
    dropped=("SavingThrow.keywords",),
)
def i928x1(c: Cast) -> None:
    """The save modifier is totalled with no context, so "against poison"
    cannot narrow it."""
    c.bonus("save", 2, kind="item", on=c.me, until=When.ENCOUNTER)


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
    on=Trigger(Bloodied, _enemy_bloodied, "an enemy is bloodied"),
    dropped=("Bloodied.source",),
)
def i1029p1(c: Cast) -> None:
    """`Bloodied` carries only the creature, so "you bloody it" is read as
    "it becomes bloodied" -- the daily usage keeps that from mattering
    more than once."""
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
    c.deals(DamageType.NECROTIC, until=When.EOT, on=c.me)


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
    todo=("spec.power_ref()",),
)
def i1298p1(c: Cast) -> None:
    """"As the <class>'s <name> power" -- `c.grant_attack(c.me, ref=...)`
    says it, and the brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i1345p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i1534p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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


@power(
    "i1612p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your flurry of blows power",
    todo=("spec.power_ref()",),
)
def i1612p1(c: Cast) -> None:
    """The trigger is a named class power and the brief prints its name
    rather than its ref, so there is nothing to declare `on=` against."""


@power(
    "i1656x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_weapon()",),
)
def i1656x1(c: Cast) -> None:
    """The mirror of `c.as_implement`, which does not exist."""


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
    todo=("spec.power_ref()",),
)
def i1738p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1821x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()", "c.zone_damage()"),
)
def i1821x1(c: Cast) -> None:
    """Doubles the bite of one named zone power. The ref is prose in the
    brief, and nothing changes a standing zone's damage after the fact."""


@power(
    "i1821p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
    todo=("spec.power_ref()",),
)
def i1821p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1822x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()", "c.movement_tax()"),
)
def i1822x1(c: Cast) -> None:
    """"Each square moved toward you costs 1 extra" is difficult terrain
    that follows one creature and only in one direction; `c.zone` is laid
    on squares and `c.slowed` caps a whole move instead."""


@power(
    "i1822p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FEAR, Keyword.IMPLEMENT, Keyword.RADIANT],
    todo=("spec.power_ref()",),
)
def i1822p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1823x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()",),
)
def i1823x1(c: Cast) -> None:
    """A damage bonus gated on `ctx["power"]`, and the ref is prose."""


@power(
    "i1823p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    todo=("spec.power_ref()",),
)
def i1823p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i1826x1(c: Cast) -> None:
    """Splashes half of one named power's rebound onto adjacent allies, and
    the ref is prose in the brief."""


@power(
    "i1826p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    todo=("spec.power_ref()",),
)
def i1826p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1828x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()",),
)
def i1828x1(c: Cast) -> None:
    """A push on one named power's damage, and the ref is prose."""


@power(
    "i1828p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    todo=("spec.power_ref()",),
)
def i1828p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1831x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()",),
)
def i1831x1(c: Cast) -> None:
    """`c.ignore_cover(when=)` says it; the ref of the power it is gated on
    is prose in the brief."""


@power(
    "i1831p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
    todo=("spec.power_ref()",),
)
def i1831p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i1832x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.power_ref()",),
)
def i1832x1(c: Cast) -> None:
    """Extra damage in one named power's origin square. `c.origin` is the
    square an area was aimed at, so only the ref is missing."""


@power(
    "i1832p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    todo=("spec.power_ref()",),
)
def i1832p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i1927p1(c: Cast) -> None:
    """`c.restore_use` is the verb; the class feature's ref is prose."""


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
    c.deals(DamageType.PSYCHIC, until=When.EOT, on=c.me)


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
    todo=("spec.power_ref()", "c.class_feature()"),
)
def i1986p1(c: Cast) -> None:
    """Deepens a class feature's saving-throw penalty. The feature is named
    in prose and nothing asks after one."""


@power(
    "i1989p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with an attack with this implement",
    todo=("c.effects_on()",),
)
def i1989p1(c: Cast) -> None:
    """`c.transfer` moves a live hold intact and is exactly this line's
    verb -- but nothing hands back the effects standing on a creature, so
    there is no hold to pass it."""


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
    todo=("spec.power_ref()",),
)
def i2291p1(c: Cast) -> None:
    """Retargets one named power, whose ref is prose in the brief."""


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
    todo=("spec.power_ref()",),
)
def i2304p1(c: Cast) -> None:
    """An extra use of a class feature is `c.restore_use`, and the
    feature's ref is prose in the brief."""


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
    dropped=("c.typed_damage_bonus()", "c.once_per_round_bonus()"),
)
def i2442x1(c: Cast) -> None:
    """The extra damage is untyped rather than necrotic -- `c.bonus` has no
    `dtype` -- and it pays out on every qualifying hit rather than once a
    round per enemy."""
    c.bonus(
        "damage",
        4 + c.enhancement,
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
    todo=("spec.power_ref()",),
)
def i2627x1(c: Cast) -> None:
    """Multiplies one named conjuration and folds its sustains into one
    action. The ref is prose in the brief."""


@power(
    "i2633x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.class_feature()",),
)
def i2633x1(c: Cast) -> None:
    """Deepens one form of a class feature, and nothing asks after one."""


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
    dropped=("SavingThrow.condition",),
)
def i2642x1(c: Cast) -> None:
    """The save modifier is totalled with no context, so "against being
    immobilized or slowed" cannot narrow it."""
    c.bonus("save", 2, kind="item", on=c.me, until=When.ENCOUNTER)


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
    c.ignores_difficult_in(zone, side="ally")


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
    todo=("spec.power_ref()", "c.extend_effect()"),
)
def i2762p1(c: Cast) -> None:
    """Holds a class feature's mark past the moment it would lapse. The
    feature is named in prose and nothing lengthens a live effect."""


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
    todo=("spec.power_ref()",),
)
def i3019p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i3026p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


@power(
    "i3027p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    todo=("spec.power_ref()",),
)
def i3027p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
    todo=("spec.power_ref()",),
)
def i3030p1(c: Cast) -> None:
    """The brief gives a prose name instead of a ref."""


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
