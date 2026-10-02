"""The heroic item blocks the slot-by-slot waves did not reach.

Everything here is a category with no wearable slot: boons, gifts, mounts,
companions, familiars, brands and training. Nothing declares an item --
the level, the price, the ladder and the base-item restriction are columns
in `game.db` -- and a `Level 11:` or `Level 21:` line is paragon, so only
the heroic number is written.

Six judgements run through the file.

* **A mount item is written on whichever end of the relation holds it.**
  Barding sits on the animal and a saddle's power belongs to the rider, so
  `_the_mount` reads `c.mount()` first and falls back to "I am the thing
  being ridden". Rows whose whole content is the animal's carrying
  capacity are `out_of_combat=True`; there is no encumbrance model and
  inventing one would be inventing a rule.
* **Fortune Cards are a deck the engine does not have.** Every block whose
  benefit is drawing, discarding or choosing one carries `c.draw()`. Where
  a card clause sits beside a plain skill bonus the bonus is written and
  the card half is `dropped=`.
* **"While X" is a gate, not a duration.** `Mod.applies` is asked every
  time a modifier is read, so a closure that ignores the context and
  looks at the board answers "while you are bloodied", "while you are not
  bloodied" and "while you are within 5 squares of your companion" at the
  moment the question is put. These rows used to read the condition once,
  when the trait armed, and carried `When.UNBLOODIED` and
  `c.bonus(compute=)` for a duration and a recompute that are not what is
  wanted. `_bloodied_gate` and `_near_companion` are the two shapes.
* **A skill bonus is a real modifier where it is unconditional** --
  `armour.py` set that -- and is left unwritten where the card gates it on
  a circumstance, which is `narrative=("skill:athletics",)` and not a
  marker: no check is rolled for jumping, so there is no verb to wait on.
  Over-applying "+5 to jump" to every Athletics check is worse than not
  writing it. "Skill
  checks", with no skill named, is the blanket `skill` key rather than
  seventeen guesses: `skills.modifier` adds it to every check.
* **A saving throw can be asked what it is against.** `Effects.save`
  builds the modifier context out of the hold's own label, keywords,
  `conditions` and `ongoing`, so "against fear or charm effects" is
  `_save_keywords` and "against the slowed, immobilized and restrained
  conditions" is `_save_conditions`. The *event* still carries none of
  it, which is why a row answering a save rather than modifying one --
  "roll twice and use either result" -- still names `SavingThrow.ongoing`.
* **`Bloodied` carries `actor` and `source`**, so "an enemy bloodies you,
  but does not reduce you to 0" is exact: `_bloodied_by_a_foe` asks the
  first half, and `resolve.deal_damage` emits the event only while
  `hp > 0`, which is the second.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    REGISTRY,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionSpent,
    ActionType,
    AdjacencyGained,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    EffectApplied,
    Forced,
    ForcedMove,
    Health,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Position,
    PowerResolved,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    RoundStart,
    SavingThrow,
    SecondWind,
    Size,
    SkillCheck,
    Square,
    Summon,
    SurgeSpent,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    World,
    about_me,
    both,
    by_me,
    by_melee,
    closed_on_me,
    get,
    my_check,
    power,
    query,
    spread,
    targets_me,
)
from combat_engine.engine.components import Defences
from combat_engine.engine.durations import keywords_of

ITEM = "item"

#: The four conditions a save-bonus clause in this file names, kept in one
#: place so the rows that lay the bonus and the rows that answer the
#: condition read the same list.
_HELD = (
    Condition.SLOWED,
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
)


# -- shared reading of the board --------------------------------------------


def _skills(c: Cast, value: int, *names: str, kind: str = "item") -> None:
    """Lay one bonus per named skill. There is no key for a set of them."""
    for name in names:
        c.bonus(f"skill:{name}", value, on=c.me, until=When.ENCOUNTER, kind=kind)


def _item_level(c: Cast) -> int:
    """"Equal to this boon's level" -- the row's own level, not the wearer's."""
    row = get(c.ref)
    return row.level if row is not None else c.level


def _surges(c: Cast) -> int:
    """How many healing surges the caster has left."""
    health = c.world.get(c.me, Health)
    return 0 if health is None else health.surges


def _the_mount(c: Cast) -> int | None:
    """The animal a mount item is about.

    Barding and a saddle sit on the beast; a rider's item names the beast
    it is riding. Whichever end of the relation the board hung the item
    on, this is the animal.
    """
    ridden = c.mount()
    if ridden is not None:
        return ridden
    return c.me if c.rider() is not None else None


def _square_of(c: Cast, eid: int) -> Square | None:
    pos = c.world.get(eid, Position)
    return None if pos is None else pos.square


def _free_near(c: Cast, of: int, radius: int = 1) -> Square | None:
    """An unoccupied square within `radius` of somebody, for a "to" clause."""
    here = _square_of(c, of)
    if here is None:
        return None
    grid = c.world.grid
    for sq in sorted(spread({here}, radius)):
        if sq != here and grid.occupant(sq) is None:
            return sq
    return None


def _melee_ctx(ctx: dict[str, Any]) -> bool:
    """"Melee attacks" from a damage context, which carries no `attacker`
    and no `ranged` -- so the reach has to come off the power."""
    row = get(ctx.get("power") or "")
    return row is not None and row.reach is not None and row.reach.kind == "melee"


def _dtype_gate(*types: DamageType) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") in types

    return gate


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _against(foe: int) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe

    return gate


def _opportunity(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("opportunity"))


def _crit_ctx(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("crit"))


def _ranged_ctx(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("ranged"))


def _save_keywords(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the row that laid the hold printed one of these words.
    `Effects.save` builds the context with `durations.keywords_of`, which
    reads them off the label -- that row's ref."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("keywords", ())))

    return gate


def _on_second_wind(c: Cast, fn: Callable[[], None]) -> None:
    """Arm "when you use your second wind" for the rest of the fight.

    `SecondWind` is the announcement. This used to sniff `EffectApplied`
    for a label beginning "second-wind", which only matched when the
    action menu ran it: `c.second_wind(on=ally)` labels the effect with
    the *calling row's* ref, so a leader row handing somebody a second
    wind was silently invisible here.
    """

    def seen(ev: SecondWind) -> None:
        if ev.actor == c.me:
            fn()

    c.watch(SecondWind, seen, until=When.ENCOUNTER, on=c.me)


def _bloodied_gate(c: Cast, wanted: bool) -> Callable[[dict[str, Any]], bool]:
    """"While you are bloodied", and its other half, as a live gate.

    `Mod.applies` is asked every time a modifier is read, so a closure
    that ignores the context and looks at the wearer answers the question
    at the moment it is put -- which is what "while" means. These rows
    used to read it once, when the trait armed, and carried
    `When.UNBLOODIED` for the duration they wanted instead; there is no
    duration to want, because the gate is not a duration.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=c.me) is wanted

    return gate


def _near_companion(c: Cast, beast: int, radius: int) -> Callable[..., bool]:
    """"While you are within N squares of your companion", read live."""

    def gate(ctx: dict[str, Any]) -> bool:
        return c.distance(beast) <= radius

    return gate


def _vulnerable_to(c: Cast, eid: int, dtype: DamageType) -> bool:
    """Does this creature take extra from that type right now?

    `Defences.vulnerable` is the store `c.vulnerable` writes to, and
    `c.resistances` reads the other half of the same component; there is
    no reader for this half yet.
    """
    held = c.world.get(eid, Defences)
    return bool(held and held.vulnerable.get(dtype, 0))


def _flanking_with(c: Cast, mate: int, foe: int) -> bool:
    """Do the wearer and one named creature hold opposite sides of `foe`?

    `query.flanked_by` asks whether *anybody* holds the other side, and
    the card names which creature it has to be, so the pairing is made
    here out of the same two pieces that function uses. `can_flank` is
    deliberately not asked: that permission is what a beast needs before
    it counts as *an ally* holding a side, and this card is the printed
    line granting it.
    """
    from combat_engine.engine import query

    if not (
        query.adjacent(c.world, c.me, foe)
        and query.adjacent(c.world, mate, foe)
        and query.can_act(c.world, c.me)
        and query.can_act(c.world, mate)
    ):
        return False
    space = query.squares(c.world, foe)
    return any(
        c.world.grid.flanks(a, b, space)
        for a in query.squares(c.world, c.me)
        for b in query.squares(c.world, mate)
    )


def _save_conditions(*conditions: Condition) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the hold being saved against carries one of these.

    `Effects.save` puts the effect's own `conditions` in the context, so
    "a +2 bonus to saves against being slowed, immobilized or restrained"
    is a gate rather than a bonus to every save in the fight.
    """
    wanted = set(conditions)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("conditions", ())))

    return gate


def _bloodied_by_a_foe(world: World, me: int, ev: Any) -> bool:
    """An enemy put the wearer past the half-hit-point line.

    `resolve.deal_damage` emits `Bloodied` only while `hp > 0`, so the
    printed "but does not reduce you to 0 hit points" needs nothing here.
    """
    who = getattr(ev, "source", None)
    return (
        getattr(ev, "actor", None) == me
        and who is not None
        and query.team(world, who) is not query.team(world, me)
    )


def _my_crit(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "critical", False)


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "critical", False)
        and getattr(ev, "attacker", None) != me
    )


def _my_crit_with(*words: Keyword) -> Callable[[World, int, Any], bool]:
    def gate(world: World, me: int, ev: Any) -> bool:
        if not _my_crit(world, me, ev):
            return False
        row = get(getattr(ev, "power", "") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _hit_by_me_with(*words: Keyword) -> Callable[[World, int, Any], bool]:
    def gate(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "attacker", None) != me:
            return False
        row = get(getattr(ev, "power", "") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _used_with(*words: Keyword) -> Callable[[World, int, Any], bool]:
    """"You use an arcane power" -- read off `PowerUsed`, whose subject is
    `actor` and whose row is `power`."""

    def gate(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "actor", None) != me:
            return False
        row = get(getattr(ev, "power", "") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _at_will_hit(world: World, me: int, ev: Any) -> bool:
    """"You hit an enemy with an unaugmented at-will attack power."

    A predicate is handed `(world, me, event)` and no `Cast`, so the
    augment half is asked in the body instead, where `c.points_spent` is.
    """
    if getattr(ev, "attacker", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.usage is Usage.AT_WILL


def _unaugmented(c: Cast) -> bool:
    return c.points_spent(getattr(c.trigger, "power", "") or "") == 0


def _had_advantage(world: World, me: int, ev: Any) -> bool:
    """"The attacker has combat advantage against you."

    The live `AttackResult` rides on the attack events as a plain
    attribute; asking `has_combat_advantage` again is too late, because a
    one-shot grant has already been spent by then.
    """
    if getattr(ev, "target", None) != me:
        return False
    return bool(getattr(getattr(ev, "result", None), "advantage", False))


def _held_condition(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "condition", None) in _HELD
    )


def _prone_on_me(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "condition", None) is Condition.PRONE
    )


def _marked_on_me(world: World, me: int, ev: Any) -> bool:
    """`RelationSet`, not `ConditionApplied`: a mark is a relation and is
    only mirrored into `Conditions`, so nothing announces it as a
    condition and a trigger declared on that one is silently false."""
    return (
        getattr(ev, "kind_", None) is Relation.MARKED_BY
        and getattr(ev, "target", None) == me
        and getattr(ev, "source", None) in query.enemies(world, me)
    )


def _dominated_on_me(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "kind_", None) is Relation.DOMINATED_BY
        and getattr(ev, "target", None) == me
    )


def _forced_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "source", None) != me


def _bears(label: str) -> Callable[[World, int], bool]:
    """"The creature subject to your X" as a `requires=` gate.

    A row whose only target is the bearer of another row's hold is not
    usable until that hold exists, and saying so is better than offering
    it and having it do nothing.
    """

    def gate(world: World, eid: int) -> bool:
        from combat_engine.engine import query

        for other in query.creatures(world):
            if other == eid:
                continue
            for eff in world.effects.of(other):
                if eff.source == eid and label in eff.label:
                    return True
        return False

    return gate


def _something_tiny(world: World, eid: int) -> bool:
    """A Tiny creature within 5 squares, for the polymorph's entry gate."""
    from combat_engine.engine import query

    for other in query.creatures(world):
        pos = world.get(other, Position)
        if other == eid or pos is None or pos.size is not Size.TINY:
            continue
        if query.distance_between(world, eid, other) <= 5:
            return True
    return False


def _arcane_rows(usage: Usage, level: int) -> list[str]:
    """The attack rows an arcane character class prints, by ref.

    "A power from an arcane class" is `Power.cls` and `Keyword.ARCANE`
    together. There is no power-source column to read, and the keyword on
    its own lets in the handful of martial rows that print it; the two
    together come to the six classes and nothing else.

    The `p` is load-bearing: `cf:` rows carry a class, a usage and a
    keyword list too, and the first pass here offered a warlock's class
    feature as an at-will power to choose from. Attack rows only, which
    is exactly what two of the three cards say and the useful reading of
    the third.
    """
    return sorted(
        ref
        for ref, row in REGISTRY.items()
        if ref.startswith("p")
        and row.cls
        and row.cls != ITEM
        and row.usage is usage
        and row.level <= level
        and row.attack is not None
        and Keyword.ARCANE in row.keywords
    )


def _restorable(c: Cast, usage: Usage) -> list[str]:
    """Spent rows of one usage, for a row that hands a use back."""
    out = []
    for ref in c.expended(on=c.me):
        row = get(ref)
        if row is not None and row.usage is usage:
            out.append(ref)
    return out


# -- level 1 ----------------------------------------------------------------


@power("i1613x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1613x1(c: Cast) -> None:
    """"While ridden": the resistance is laid only when the relation is
    actually set, so barding on a loose animal does nothing."""
    beast = _the_mount(c)
    if beast is not None:
        c.resist(5, on=beast, until=When.ENCOUNTER)


@power("i3365p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(10), target=NO_TARGET, out_of_combat=True)
def i3365p1(c: Cast) -> None:
    """The printed bonus is to speed *outside combat* and lasts eight
    hours, so there is no fight in which it applies."""


@power("i3476x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3476x1(c: Cast) -> None:
    _skills(c, 1, "diplomacy")


@power("i3476p1", level=1, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you make a skill check and dislike the result",
       on=Trigger(SkillCheck, my_check(), "you make a skill check"))
def i3476p1(c: Cast) -> None:
    """Declared on the check itself; "even if it's lower" is `keep="new"`."""
    c.reroll_check(keep="new")


@power("i636x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i636x1(c: Cast) -> None:
    _skills(c, 1, "acrobatics", "bluff")


@power("i636p1", level=1, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy marks you",
       on=Trigger(RelationSet, _marked_on_me, "an enemy marks you"))
def i636p1(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(1)


# -- level 2 ----------------------------------------------------------------


@power("i1330p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a psionic power",
       on=Trigger(Hit, _my_crit_with(Keyword.PSIONIC),
                  "you score a critical hit with a psionic power"))
def i1330p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.penalty("attack", 2, on=foe, until=When.EONT)


@power("i1713p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY)
def i1713p1(c: Cast) -> None:
    """"You and each ally": the caster is not in an ally burst, so the
    once-per-power line pays the caster separately."""
    left = _surges(c)
    if c.first:
        c.temp_hp(left, on=c.me)
    c.temp_hp(left)


@power("i1866x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1866x1(c: Cast) -> None:
    beast = _the_mount(c)
    if beast is not None:
        for d in (FORT, REF, WILL):
            c.bonus(d, 1, on=beast, until=When.ENCOUNTER, kind="item")


@power("i1866p1", level=2, cls=ITEM, usage=AT_WILL, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an area attack would target the mount you are riding",
       on=Trigger(AttackDeclared, lambda w, me, ev: (
           getattr(ev, "target", None) is not None
           and getattr(ev, "target", None) != me),
           "an area attack would target your mount"))
def i1866p1(c: Cast) -> None:
    """`AttackDeclared` is announced once per target, so cancelling the
    one aimed at the mount takes the mount out of the attack and leaves
    the rest of the burst standing. The area half is not asked: the
    predicate gets no reach it can trust before the branch is chosen."""
    beast = c.mount()
    if beast is not None and getattr(c.trigger, "target", None) == beast:
        c.cancel()


@power("i2403x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2403x1(c: Cast) -> None:
    """`Miss` carries no defence, but `AttackRolled` does and is announced
    for the same swing, so the two are matched on attacker and row rather
    than paying on every miss. Read off the settled `Miss` rather than
    comparing the roll to the defence in the earlier window, where a row
    answering the attack can still move either number."""
    aimed: dict[tuple[int, str], str] = {}

    def rolled(ev: AttackRolled) -> None:
        if ev.target == c.me:
            aimed[(ev.attacker, ev.power)] = str(ev.vs)

    def missed(ev: Miss) -> None:
        if ev.target != c.me or ev.attacker == c.me:
            return
        if aimed.pop((ev.attacker, ev.power), "") == "fort":
            c.temp_hp(5, on=c.me)

    c.watch(AttackRolled, rolled, until=When.ENCOUNTER)
    c.watch(Miss, missed, until=When.ENCOUNTER)


@power("i2588p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=CloseBurst(1), target=NO_TARGET, keywords=[Keyword.ZONE],
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, by_me, "you hit an enemy with an attack"),
       no_provoke=True)
def i2588p1(c: Cast) -> None:
    """"Lightly obscured" is concealment, and `c.conceal` is a modifier
    with a gate the attack context is handed -- so it is laid on everybody
    once and asked, at each swing, whether that creature is standing in
    the zone then. Hanging it on the zone object would have been a second
    way of saying the same thing. The slide is armed on `TurnStart`
    because the printed line reads "starts its turn within the zone"."""
    area = c.area()
    c.zone(area, until=When.EONT)

    for who in {c.me, *c.allies(), *c.enemies()}:
        c.conceal(on=who, until=When.EONT,
                  when=lambda ctx, w=who: w in c.in_squares(area))

    def began(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(area):
            c.slide(1, on=ev.actor)

    c.watch(TurnStart, began, until=When.EONT)


@power("i3380p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i3380p1(c: Cast) -> None:
    c.move(max(1, c.speed_of() // 2))
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT, once=True,
            when=_melee_ctx)


@power("i580x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_defiling()",))
def i580x1(c: Cast) -> None:
    """Re-aimed at the symbol `weapon.py` already uses for this feature:
    the whole property is a rider on a use of arcane defiling, which is
    not a declared row and announces nothing. `c.class_feature()` named
    a general reader nobody needs -- `cf:` refs exist and can be watched
    once this particular feature is one."""


# -- level 3 ----------------------------------------------------------------


@power("i1066x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1066x1(c: Cast) -> None:
    """The property is the permission to use `i1066p1`; the summon itself
    is that row and this one adds nothing to a fight."""


@power("i1066p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(10), target=NO_TARGET, keywords=[Keyword.SUMMONING],
       dropped=("c.best_ability()",))
def i1066p1(c: Cast) -> None:
    """The block is printed in the power's own text and the spec carries
    all of it, so a missing block was the wrong hold: the defence
    offsets, the size and the hover are written, and `dsl.Summon` could
    take the attack line too.

    What stops it is "your highest ability": `Attack` takes one named
    ability or a printed number, and nothing answers "whichever of mine is
    largest". Fifty-four rows print the phrase. Without the attack line
    the Instinctive Effect has nothing to fire, so both wait on it and the
    summon commands with whatever row drives it."""
    c.summon_inline(
        Summon(per_defence={"ac": 2, "fort": 2}, speed=0, modes={"fly": 6}),
    )


@power("i1217x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.aid_another()",))
def i1217x1(c: Cast) -> None:
    """Aid another is not an action the engine offers, so there is no
    bonus of its to raise."""


@power("i1217p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=ONE_ALLY, keywords=[Keyword.HEALING])
def i1217p1(c: Cast) -> None:
    if c.may("spend a healing surge"):
        c.surge()
    c.bonus("attack", 1, until=When.ENCOUNTER, once=True)


@power("i1247x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1247x1(c: Cast) -> None:
    fam = c.familiar()
    if fam is not None:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 1, on=fam, until=When.ENCOUNTER, kind="item")


@power("i1354p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="a saving throw you have just rolled",
       todo=("c.boost_save()",))
def i1354p1(c: Cast) -> None:
    """Re-aimed. Adding to a saving throw already on the table is not a
    reroll, so `c.reroll_save` is the wrong half of the pair; what is
    missing is `c.boost_check`'s twin. `Effects.save` announces the
    outcome before acting on it and reads `saved` back afterwards --
    which is the window `c.unsave` already writes in -- so the verb is
    that one's opposite and nothing deeper."""


@power("i1579x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1579x1(c: Cast) -> None:
    """One speed key covers every movement mode, which is what the card
    says: the modes read the creature's speed.

    Untyped, because the card reads "increases by 1 square" and names
    no type. An item bonus and an untyped one are different numbers the
    moment anything else stacks with them.
    """
    beast = _the_mount(c)
    if beast is not None:
        c.bonus("speed", 1, on=beast, until=When.ENCOUNTER)


@power("i1646x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1646x1(c: Cast) -> None:
    """"Skill checks", with no skill named, is the blanket `skill` key:
    `skills.modifier` adds it to every check alongside the per-skill one,
    so there is nothing to enumerate."""
    c.bonus("skill", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i1646p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=NO_TARGET)
def i1646p1(c: Cast) -> None:
    """"A single skill of your choice" -- the skill table is rules data,
    not flavour, so the choice is offered from it."""
    from combat_engine.engine.skills import SKILLS

    name = c.choose(sorted(SKILLS), "which skill")
    if name is None:
        return
    for who in (c.me, *c.within(5, side="team")):
        c.bonus(f"skill:{name}", 1, on=who, until=When.ENCOUNTER)


@power("i1697x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1697x1(c: Cast) -> None:
    _skills(c, 2, "intimidate", "perception")


@power("i1697p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you are knocked prone from an attack",
       on=Trigger(ConditionApplied, _prone_on_me, "you are knocked prone"))
def i1697p1(c: Cast) -> None:
    c.cure(Condition.PRONE, on=c.me)
    c.surge(on=c.me)


@power("i1700x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ability_check()",))
def i1700x1(c: Cast) -> None:
    """The Athletics half is unconditional and written; "Strength checks
    made to break objects" is a bare ability check against an object, and
    there is neither."""
    _skills(c, 2, "athletics")


@power("i1700p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1700p1(c: Cast) -> None:
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_melee_ctx)


@power("i1849x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1849x1(c: Cast) -> None:
    """Watched after the window rather than inside it, because the printed
    line is "at the end of the forced movement"."""

    def shoved(ev: ForcedMove) -> None:
        if _forced_on_me(c.world, c.me, ev):
            c.shift(1)

    c.watch(ForcedMove, shoved, until=When.ENCOUNTER)


@power("i1849p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i1849p1(c: Cast) -> None:
    c.mode("fly", 5, on=c.me, until=When.EOT)
    c.move(5, at="fly")


@power("i1851x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1851x1(c: Cast) -> None:
    """`query.speed` reads its modifiers with a context, so the gate is
    asked at every move rather than once when the trait armed."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_bloodied_gate(c, False))


@power("i1851p1", level=3, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PSIONIC],
       trigger="you hit with an unaugmented at-will attack power",
       on=Trigger(Hit, _at_will_hit, "you hit with an at-will attack power"))
def i1851p1(c: Cast) -> None:
    if _unaugmented(c):
        c.shift(2)


@power("i1886x1", level=3, cls=ITEM, action=ActionType.NONE,
)
def i1886x1(c: Cast) -> None:
    """Shortens a **push** only, which is what the card says, and the gate says so
    now: `movement.settle` reads `"forced"` with `{"how", "power"}`, so
    `ctx["how"]` is the shove's own kind. It used to shorten every push, pull and
    slide -- and the pull half mattered, because the row's *other* clause pays out
    when a pull lands you adjacent, which a shortened pull is less likely to do.

    The opportunity attack on a pull is exact -- `ForcedMove` carries `how`."""
    c.resist_forced(2, on=c.me, until=When.ENCOUNTER,
                    when=lambda ctx: ctx.get("how") == Forced.PUSH.value)

    def hauled(ev: ForcedMove) -> None:
        if (
            ev.target == c.me
            and ev.how is Forced.PULL
            and ev.source != c.me
            and c.adjacent(ev.source)
        ):
            c.basic(on=ev.source)

    c.watch(ForcedMove, hauled, until=When.ENCOUNTER)


@power("i1886p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you take damage",
       on=Trigger(DamageRolled, targets_me, "you take damage"))
def i1886p1(c: Cast) -> None:
    c.reduce(5)


@power("i1900x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1900x1(c: Cast) -> None:
    _skills(c, 1, "bluff")


@power("i1900p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       trigger="you use an arcane power",
       on=Trigger(PowerUsed, _used_with(Keyword.ARCANE),
                  "you use an arcane power"))
def i1900p1(c: Cast) -> None:
    c.invisible(on=c.me, until=When.EONT)
    c.shift(1)


@power("i2026x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2026x1(c: Cast) -> None:
    """Untyped: the card prints no word before "damage". The vulnerability
    is read off the target each time the blow lands, not once, because a
    row can hand one out mid-fight."""
    extra = max(c.wis_mod, c.con_mod)
    if extra <= 0:
        return
    c.bonus("damage", extra, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("target") is not None
                and _vulnerable_to(c, ctx["target"], DamageType.RADIANT)
            ))


@power("i2026p1", level=3, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2026p1(c: Cast) -> None:
    """Light only."""


@power("i2026p2", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=ONE_ALLY, keywords=[Keyword.HEALING])
def i2026p2(c: Cast) -> None:
    if c.may("spend a healing surge"):
        c.surge()
    c.bonus("save", 1, until=When.ENCOUNTER, kind="item")


@power("i2056p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.NECROTIC],
       dropped=("c.flat(unpreventable=)",))
def i2056p1(c: Cast) -> None:
    """"Cannot be prevented in any way" has no flag, so resistance still
    eats it. The aura is what makes the adjacency visible to the UI."""
    c.aura(1, until=When.ENCOUNTER, on=c.me)

    def ended(ev: TurnEnd) -> None:
        if ev.actor in c.enemies() and c.adjacent(ev.actor):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnEnd, ended, until=When.ENCOUNTER)


@power("i2374x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2374x1(c: Cast) -> None:
    """Carrying capacity. There is no encumbrance model and a fight does
    not weigh anything."""


@power("i2426x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.insubstantial(when=)",))
def i2426x1(c: Cast) -> None:
    """Both halves hang on "a creature that cannot see you", and the damage
    context carries no attacker to ask it of."""


@power("i2426p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="you take damage",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def i2426p1(c: Cast) -> None:
    c.teleport(2)


@power("i2858x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2858x1(c: Cast) -> None:
    """`c.jump` rolls nothing and charges no running start, so both halves
    of this property are bonuses to a check that never happens in a
    fight."""


@power("i2858p1", level=3, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, about_me, "you spend an action point"))
def i2858p1(c: Cast) -> None:
    c.mode("fly", c.speed_of(), on=c.me, until=When.EOT)


@power("i2864p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE,
       dropped=("c.reroll_damage(dice=)",))
def i2864p1(c: Cast) -> None:
    """The mark is a named hold so `i2864p2` can find its bearer.
    Re-aimed: `c.reroll_damage` exists and rerolls the whole roll, where
    the card rerolls **one die** and says outright that the rest of an
    area attack keeps its numbers, so the gap is the count."""
    c.effect(c.ref, until=When.ENCOUNTER)


@power("i2864p2", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       requires=_bears("i2864p1"),
       requires_text="a creature must bear the mark")
def i2864p2(c: Cast) -> None:
    for foe in c.suffering("i2864p1"):
        square = _free_near(c, foe)
        if square is not None:
            c.teleport(20, to=square)
        return


@power("i2906x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2906x1(c: Cast) -> None:
    """The save context carries the hold's own conditions, so the three
    the card names are a gate rather than a bonus to every save."""
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_conditions(*_HELD))


@power("i2906p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you become slowed, immobilized or restrained",
       on=Trigger(ConditionApplied, _held_condition,
                  "you become slowed, immobilized or restrained"))
def i2906p1(c: Cast) -> None:
    c.teleport(2)
    held = getattr(c.trigger, "condition", None)
    if held is not None:
        c.cure(held, on=c.me)


@power("i2944x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2944x1(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_conditions(*_HELD, Condition.STUNNED))


@power("i2944p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.CHARM],
       trigger="you take damage from an attacker with combat advantage",
       on=Trigger(Hit, _had_advantage,
                  "an attacker with combat advantage hits you"))
def i2944p1(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.dazed(on=foe, until=When.EONT)
    c.shift(1)


@power("i2969x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2969x1(c: Cast) -> None:
    beast = c.companion()
    if beast is None:
        return

    def paid() -> None:
        c.temp_hp(5, on=beast)

    _on_second_wind(c, paid)


@power("i3333x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def i3333x1(c: Cast) -> None:
    """The Bluff bonus is written; the Fortune Card clause has no deck."""
    _skills(c, 1, "bluff")


@power("i3333p1", level=3, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.draw()",))
def i3333p1(c: Cast) -> None:
    """Fortune Cards are not modelled: no deck, no hand, no draw."""


@power("i3362p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i3362p1(c: Cast) -> None:
    """Carrying a flame about. Light only, and the fire it picks up is
    scenery the printed effect explicitly cannot aim at a creature."""


@power("i3366p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3366p1(c: Cast) -> None:
    """Ten minutes of smelling out treasure."""


@power("i3378p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.redirect(recheck=)",))
def i3378p1(c: Cast) -> None:
    """`c.redirect` exists, and it is still the wrong tool here, so the
    marker names the argument rather than the verb.

    It moves a *live* result: `ev.target` and `result.target`, read back by
    the body that is still resolving. By the time a `Miss` is announced the
    comparison against a defence has already been made and `resolve.attack`
    only re-announces when `result.hit` flips -- so pointing a miss at a new
    creature moves the announcement and nothing else. Redirecting a resolved
    attack means re-reading the roll against the new target's defence, which
    is the argument this wants. (It is also printed as an immediate
    reaction, so the half would hang off `c.watch(Miss, ...)`, where
    `c.trigger` is None and `c.redirect` has nothing to move either way.)

    The free-hand requirement is read off what is in hand."""
    if len(c.held()) < 2:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 4, on=c.me, until=When.EONT, kind="power",
                    when=_ranged_ctx)
    c.move(c.speed_of())


@power("i3393p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, keywords=[Keyword.CHARM],
       attack=Attack(vs=WILL, printed=8))
def i3393p1(c: Cast) -> None:
    """The hold is named with this row's ref so `i3393p2` can find its
    bearer; the slide is armed on the target's own turn start."""
    if not c.strike():
        return
    foe = c.target
    c.effect(c.ref, on=foe, until=When.SAVE_ENDS)

    def began(ev: TurnStart) -> None:
        if ev.actor == foe:
            c.slide(1, on=foe)

    c.watch(TurnStart, began, until=When.ENCOUNTER)


@power("i3393p2", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(10), target=NO_TARGET, keywords=[Keyword.FIRE],
       requires=_bears("i3393p1"),
       requires_text="a creature must be held by i3393p1")
def i3393p2(c: Cast) -> None:
    """"The target chooses" -- `c.may` asks the creature that is choosing,
    which is the one being hit, not the caster."""
    for foe in c.suffering("i3393p1"):
        if c.may("fall prone rather than burn", who=foe):
            c.prone(on=foe)
        else:
            c.flat(5, dtype=DamageType.FIRE, on=foe)
        return


@power("i3394x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3394x1(c: Cast) -> None:
    """A natural 19 or 20 is read off `AttackRolled`, which is the only
    event carrying the die; `Hit` knows only that it landed."""

    def rolled(ev: AttackRolled) -> None:
        if ev.attacker != c.me or ev.natural < 19:
            return
        row = get(ev.power)
        if row is None or Keyword.WEAPON not in row.keywords:
            return
        friends = c.within(5, side="ally")
        if friends:
            c.shift(1, who=friends[0])

    c.watch(AttackRolled, rolled, until=When.ENCOUNTER)


@power("i3394p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=CloseBurst(5), target=EACH_ALLY, no_provoke=True,
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll initiative"))
def i3394p1(c: Cast) -> None:
    c.slide(1)


@power("i3395x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3395x1(c: Cast) -> None:
    """"The first time" is the watch's own `once`, and the number is this
    boon's level rather than the wearer's."""

    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(_item_level(c), on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER, once=True)


def _bloodied_req(world: World, eid: int) -> bool:
    h = world.get(eid, Health)
    return h is not None and h.hp <= h.max_hp // 2


@power("i3395p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       requires=_bloodied_req, requires_text="you must be bloodied",
       trigger="you hit an enemy with a melee attack",
       on=Trigger(Hit, both(by_me, by_melee),
                  "you hit an enemy with a melee attack"))
def i3395p1(c: Cast) -> None:
    """"A random creature adjacent to you" is taken as the first adjacent
    one, so a replay is reproducible; the surge is conditional on the
    swing landing, as printed."""
    near = c.within(1)
    if not near:
        return
    if c.basic(on=near[0]):
        c.surge(on=c.me)


@power("i3396x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3396x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)
    _skills(c, 1, "stealth")


@power("i3396p1", level=3, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
       trigger="an enemy bloodies you",
       on=Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"))
def i3396p1(c: Cast) -> None:
    roll = c.roll("1d8")
    if roll % 2:
        c.dazed(on=c.me, until=When.EONT)
    else:
        c.teleport(roll)
        c.invisible(on=c.me, until=When.EONT)


@power("i3447p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET, keywords=[Keyword.ZONE])
def i3447p1(c: Cast) -> None:
    """"Any creature" is `side="any"`, which is the printed line: the zone
    shelters whoever stands in it, enemies included."""
    zone = c.zone(c.area(), until=When.EONT, difficult=True)
    for d in (AC, FORT, REF, WILL):
        c.grants_in(zone, d, 2, side="any", kind="power")


@power("i3467p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=CloseBurst(5), target=SELF, no_provoke=True,
       trigger="an attack hits you or an ally within 5 squares",
       on=Trigger(Hit, lambda w, me, ev: (
           getattr(ev, "target", None) is not None
           and getattr(ev, "attacker", None) != me),
           "an attack hits you or an ally within 5 squares"))
def i3467p1(c: Cast) -> None:
    hurt = getattr(c.trigger, "target", None)
    if hurt is None:
        return
    if hurt == c.me or (hurt in c.allies() and c.distance(hurt) <= 5):
        c.cancel()


@power("i3506x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3506x1(c: Cast) -> None:
    def paid() -> None:
        c.save(on=c.me)

    _on_second_wind(c, paid)


@power("i3506p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you drop an enemy to 0 hit points",
       on=Trigger(Dropped, by_me, "you drop an enemy to 0 hit points"))
def i3506p1(c: Cast) -> None:
    """"Or" becomes "both" for an aberrant or undead enemy, so the two
    clauses are asked separately rather than as a choice between them."""
    felled = getattr(c.trigger, "actor", None)
    both_of_them = felled is not None and (
        c.is_kind("aberrant", on=felled) or c.is_kind("undead", on=felled)
    )
    spent = _restorable(c, Usage.ENCOUNTER)
    if both_of_them or not spent or c.may("spend a healing surge"):
        c.surge(on=c.me)
    if (both_of_them or not c.wounded(c.me)) and spent:
        c.restore_use(spent[0], on=c.me)


@power("i573x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i573x1(c: Cast) -> None:
    """The damage context carries `opportunity` and the save context
    carries the hold's conditions, so both halves are exact."""
    c.resist(5, on=c.me, until=When.ENCOUNTER, when=_opportunity)
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_conditions(*_HELD, Condition.DAZED,
                                  Condition.DOMINATED, Condition.STUNNED))


@power("i574x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i574x1(c: Cast) -> None:
    """The count is taken at the start of the turn, which is when the card
    asks it, and the granted shift lasts that turn."""

    def began(ev: TurnStart) -> None:
        if ev.actor == c.me and len(c.within(1, side="enemy")) >= 2:
            c.shift_as(MOVE, 2, on=c.me, until=When.EOT)

    c.watch(TurnStart, began, until=When.ENCOUNTER)


@power("i574p1", level=3, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i574p1(c: Cast) -> None:
    c.teleport(2)


@power("i589x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i589x1(c: Cast) -> None:
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_opportunity)


@power("i589p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i589p1(c: Cast) -> None:
    """The opening is made by hand: `c.provoke` is the only thing that
    opens a window outside the movement rules."""

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me or ev.target == c.me:
            return
        if ev.attacker in c.enemies() and c.adjacent(ev.attacker):
            c.provoke(c.me, on=ev.attacker, why=c.ref)

    c.watch(AttackDeclared, swung, until=When.EONT)


@power("i624x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i624x1(c: Cast) -> None:
    """Paragon steps are out of scope; this is the heroic +1."""
    c.bonus("surge_value", 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i624p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy bloodies you but does not drop you",
       on=Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"))
def i624p1(c: Cast) -> None:
    """The swing goes back at the triggering enemy, which `Bloodied.source`
    names."""
    c.basic(on=c.trigger.source)


@power("i927x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i927x1(c: Cast) -> None:
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER)


@power("i927p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack targets your Will",
       on=Trigger(AttackDeclared, lambda w, me, ev: (
           getattr(ev, "target", None) == me
           and str(getattr(ev, "vs", "")) == "will"),
           "an attack targets your Will"))
def i927p1(c: Cast) -> None:
    """Declared on `AttackDeclared` rather than `Hit`, because `Hit` does
    not carry the defence and the bonus has to be up before the roll."""
    c.bonus(WILL, 2, on=c.me, until=When.SONT, kind="power")


@power("i958x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i958x1(c: Cast) -> None:
    """"As an encounter power" is one use a fight, which is `uses=1`;
    `REGISTRY` is the index the marker here said did not exist."""
    ref = c.choose(_arcane_rows(Usage.AT_WILL, 1), "which arcane at-will")
    if ref is not None:
        c.grant_row(ref, on=c.me, uses=1)


@power("i958p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def i958p1(c: Cast) -> None:
    """The same index, one usage band over: a single use of a 1st-level
    arcane encounter power, good until the fight ends."""
    ref = c.choose(_arcane_rows(Usage.ENCOUNTER, 1), "which arcane power")
    if ref is not None:
        c.grant_row(ref, on=c.me, uses=1)


# -- level 4 ----------------------------------------------------------------


@power("i1358x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1358x1(c: Cast) -> None:
    """`SurgeSpent` is emitted wherever a surge leaves a pool, so both
    printed cases -- the companion's own and one spent for it -- are the
    same event."""
    beast = c.companion()
    if beast is None:
        return

    def spent(ev: SurgeSpent) -> None:
        if ev.actor == beast:
            c.heal(5, on=beast)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER)


@power("i1395x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1395x1(c: Cast) -> None:
    beast = _the_mount(c)
    if beast is not None:
        c.resist(10, DamageType.NECROTIC, on=beast, until=When.ENCOUNTER)


@power("i1395p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1395p1(c: Cast) -> None:
    c.phasing(on=c.me, until=When.EONT)
    beast = c.mount()
    if beast is not None:
        c.phasing(on=beast, until=When.EONT)


@power("i1629x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1629x1(c: Cast) -> None:
    """The damage context carries `crit`, so this is a gated damage bonus
    rather than a `crit_damage` rider -- the card adds a modifier, not a
    die, and `crit_damage` is rolled."""
    if c.wis_mod:
        c.bonus("damage", c.wis_mod, on=c.me, until=When.ENCOUNTER,
                when=_crit_ctx)


@power("i1850x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1850x1(c: Cast) -> None:
    """Both halves are exact now: the saving-throw context carries the
    keywords of the row that laid the hold, so "fear or charm" is a gate
    rather than a bonus against everything."""
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER)
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_keywords(Keyword.FEAR, Keyword.CHARM))


def _fear_or_charm_on_me(world: World, me: int, ev: EffectApplied) -> bool:
    """A hold laid on me by a row printing fear or charm. The label is that
    row's ref, which is what `keywords_of` reads."""
    return (
        ev.target == me
        and ev.save_ends
        and bool(
            {Keyword.FEAR, Keyword.CHARM} & set(keywords_of(ev.label or ""))
        )
    )


@power("i1850p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you are subject to a fear or charm effect",
       on=Trigger(EffectApplied, _fear_or_charm_on_me,
                  "a fear or charm effect lands on you"))
def i1850p1(c: Cast) -> None:
    """The save is rolled against the triggering hold by its label: without
    `against=` it takes whichever save-ends effect comes first, which may
    be a burn rather than the charm the card is answering."""
    c.save(on=c.me, against=getattr(c.trigger, "label", "") or "")


@power("i3039x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3039x1(c: Cast) -> None:
    c.bonus("skill:acrobatics", 4, on=c.me, until=When.ENCOUNTER,
            kind="item", when=_bloodied_gate(c, False))


@power("i3039p1", level=4, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PSIONIC],
       trigger="you hit with an unaugmented at-will attack power",
       on=Trigger(Hit, _at_will_hit, "you hit with an at-will attack power"))
def i3039p1(c: Cast) -> None:
    if not _unaugmented(c):
        return
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="item")
    c.bonus(REF, 2, on=c.me, until=When.EONT, kind="item")


@power("i3334x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def i3334x1(c: Cast) -> None:
    _skills(c, 1, "acrobatics")


@power("i3334p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.draw()",))
def i3334p1(c: Cast) -> None:
    """Fortune Cards are not modelled."""


@power("i3335x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def i3335x1(c: Cast) -> None:
    _skills(c, 1, "intimidate")


@power("i3335p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.draw()",))
def i3335p1(c: Cast) -> None:
    """Fortune Cards are not modelled."""


@power("i3336x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def i3336x1(c: Cast) -> None:
    _skills(c, 1, "insight")


@power("i3336p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.draw()",))
def i3336p1(c: Cast) -> None:
    """Fortune Cards are not modelled."""


@power("i3364p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=Target(side="other", count=1,
                                      max_size=Size.TINY),
       requires=_something_tiny, requires_text="a Tiny beast within 5 squares",
       keywords=[Keyword.POLYMORPH], dropped=("spec.stat_block()",))
def i3364p1(c: Cast) -> None:
    """"Tiny" is the target line's own `max_size`, so the body does not
    re-ask it. The size change and the mount relation are both sayable;
    the printed "same statistics as a horse" is a stat block the spec
    does not carry, so the beast keeps its own numbers."""
    beast = c.target
    if beast is None:
        return
    c.resize(Size.LARGE, on=beast, until=When.ENCOUNTER)
    c.ride(on=beast)


@power("i3367p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3367p1(c: Cast) -> None:
    """Understanding animals. A language, and the card says outright that
    it makes nothing friendly or hostile."""


@power("i3382p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.set_defence()",))
def i3382p1(c: Cast) -> None:
    """"During this movement" has no duration, so the two bonuses run to
    the end of the turn -- which is the window the opportunity attacks
    they are for happen in. Using an attack roll as a defence afterwards
    has no method at all."""
    c.bonus(AC, 4, on=c.me, until=When.EOT, kind="power")
    c.bonus(REF, 4, on=c.me, until=When.EOT, kind="power")
    c.move(c.speed_of())


@power("i3388p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i3388p1(c: Cast) -> None:
    """`"reach"` is a modifier key `dsl.extra_reach` consults when it
    works out what a melee row may be aimed at, which is the printed
    sentence; `c.threatens` writes the same key for the opportunity
    window and is the wrong half of it."""
    c.bonus("reach", 1, on=c.me, until=When.EONT)
    if c.may("shift instead of walking"):
        c.shift(max(1, c.speed_of() // 2))
    else:
        c.move(c.speed_of())


@power("i3399x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3399x1(c: Cast) -> None:
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_bloodied_gate(c, True))


@power("i3399p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a melee attack",
       on=Trigger(Hit, both(by_me, by_melee),
                  "you hit an enemy with a melee attack"))
def i3399p1(c: Cast) -> None:
    for foe in c.within(1):
        c.condition(Condition.IMMOBILIZED, on=foe, until=When.SAVE_ENDS,
                    ongoing=(5, DamageType.POISON))


@power("i3454x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_surges()",))
def i3454x1(c: Cast) -> None:
    """The size of the surge pool is a character's, set at build time, and
    nothing raises it."""


@power("i3454p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you drop below 1 hit point but do not die",
       on=Trigger(Dropped, about_me, "you drop below 1 hit point"))
def i3454p1(c: Cast) -> None:
    roll = c.roll("1d6")
    if roll >= 3:
        c.surge(on=c.me, bonus=roll)


@power("i3518p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.CHARM],
       attack=Attack(vs=WILL, printed=7),
       dropped=("Target.kind",))
def i3518p1(c: Cast) -> None:
    """"One beast" is asked in the body, since `Target` filters on side
    and size and not on what a creature is; the loss is that the menu
    still offers the row against anything. "Ends if the target is
    attacked" is `AttackDeclared` aimed at it and `c.end_effect`, which
    is a hook after all."""
    foe = c.target
    if foe is None or not c.is_kind("beast", on=foe):
        return
    if not c.strike():
        return
    held = c.cannot_attack(until=When.SAVE_ENDS)

    def swung_at(ev: AttackDeclared) -> None:
        if ev.target == foe:
            c.end_effect(held)

    c.watch(AttackDeclared, swung_at, until=When.SAVE_ENDS, once=True)


@power("i686x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i686x1(c: Cast) -> None:
    """"You can choose to make this extra damage fire damage" is a choice
    with one interesting side, and the row takes it: an untyped rider is
    shrugged off by a creature resisting everything and a fire one is
    not, and the wearer is already standing in fire to have this at all."""

    def burned(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.dtype is DamageType.FIRE:
            c.bonus("damage", 2, on=c.me, until=When.EONT,
                    dtype=DamageType.FIRE)

    c.watch(DamageApplied, burned, until=When.ENCOUNTER)


@power("i686p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE])
def i686p1(c: Cast) -> None:
    """The die is fire and carries that type, so the fire keyword on the
    card and the dice agree."""
    c.bonus("damage", 0, dice="1d12", on=c.me, until=When.EONT, once=True,
            dtype=DamageType.FIRE)


def _beside_something_bigger(world: World, eid: int) -> bool:
    """"Adjacent to a creature whose size category is larger than yours."

    `Size` is a `StrEnum`, so `>` on the values compares spelling; `.order`
    is the sequence.
    """
    from combat_engine.engine import query

    mine = world.get(eid, Position)
    if mine is None:
        return False
    for other in query.creatures(world):
        theirs = world.get(other, Position)
        if other == eid or theirs is None:
            continue
        if query.adjacent(world, eid, other) and theirs.size.order > mine.size.order:
            return True
    return False


@power("i901p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF,
       requires=_beside_something_bigger,
       requires_text="must be adjacent to a larger creature",
       dropped=("c.move_through()",))
def i901p1(c: Cast) -> None:
    """The shift is exact; entering the larger creature's space during it
    is a movement permission nothing grants."""
    c.shift(5)


@power("i972x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i972x1(c: Cast) -> None:
    """Untyped: the card prints a bare "+2 bonus". The damage context
    carries `target`, which is the whole of the condition."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("target") is not None
                and c.bloodied(on=ctx["target"])
            ))


# -- level 5 ----------------------------------------------------------------


@power("i1701x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus('save:death')",))
def i1701x1(c: Cast) -> None:
    """A death saving throw is not a separate key, so the first half goes
    unwritten rather than becoming a bonus to every save; the second wind
    half is exact."""

    def paid() -> None:
        c.bonus("damage", 2, on=c.me, until=When.EONT, once=True,
                kind="item", when=_melee_ctx)

    _on_second_wind(c, paid)


@power("i1701p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge while prone",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def i1701p1(c: Cast) -> None:
    if c.is_(Condition.PRONE, on=c.me):
        c.cure(Condition.PRONE, on=c.me)


@power("i1701p2", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you succeed on a saving throw",
       on=Trigger(SavingThrow, about_me, "you make a saving throw"))
def i1701p2(c: Cast) -> None:
    """`saved` is read back after the window, so the reaction sees the
    settled result."""
    if getattr(c.trigger, "saved", True):
        c.heal(_item_level(c), on=c.me)


@power("i2408x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2408x1(c: Cast) -> None:
    _skills(c, 1, "bluff")


@power("i2408p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=Ranged(5), target=ONE_CREATURE, no_provoke=True,
       trigger="you complete your first move or attack in an encounter",
       on=Trigger(ActionSpent, lambda w, me, ev: (
           getattr(ev, "actor", None) == me
           and getattr(ev, "cost", None) in (ActionType.MOVE,
                                             ActionType.STANDARD)),
           "you complete your first move or attack"))
def i2408p1(c: Cast) -> None:
    """`ActionSpent` is the only announcement a plain walk makes; "first"
    is the row's own daily use."""
    c.mark(until=When.SAVE_ENDS)


@power("i2714p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=NO_TARGET, keywords=[Keyword.SUMMONING],
       dropped=("spec.stat_block()",))
def i2714p1(c: Cast) -> None:
    """The summoned creature's own stat block is printed nowhere the spec
    carries -- the entry names it and never prints it -- so it takes the
    summon defaults; the saving throw that turns it hostile needs the
    replacement block too."""
    c.summon_inline(Summon())


@power("i2966x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2966x1(c: Cast) -> None:
    """`skills.modifier` reads its modifiers with a context, so the
    distance is asked at every check rather than once when the trait
    armed."""
    beast = c.companion()
    if beast is not None:
        c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER,
                kind="item", when=_near_companion(c, beast, 5))


@power("i2966p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_initiative(keep=)",))
def i2966p1(c: Cast) -> None:
    """Re-aimed at the argument rather than a verb. `c.reroll_initiative`
    exists and always takes the new number; "roll twice and use the
    higher result" is `keep="best"`, which every other reroll on `Cast`
    already understands."""


@power("i2980p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.grant_inline()",))
def i2980p1(c: Cast) -> None:
    """The zone is exact. The minor-action attack it offers once a round
    has no ref of its own and nothing grants a power a row defines
    inline."""
    c.zone(c.area(), until=When.ENCOUNTER, difficult=True)


@power("i3363p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3363p1(c: Cast) -> None:
    """A bearing on a place, held until an extended rest."""


@power("i3368p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3368p1(c: Cast) -> None:
    """Questioning statues about the last day."""


@power("i3370p1", level=5, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i3370p1(c: Cast) -> None:
    """A message left in a tree for a day."""


@power("i3398x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3398x1(c: Cast) -> None:
    """"Since the end of your last turn" is kept by hand: a set filled on
    damage and emptied when the wearer's turn ends, read by the damage
    context's `target`."""
    seen: set[int] = set()

    def hurt(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.source is not None and ev.source != c.me:
            seen.add(ev.source)

    def ended(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            seen.clear()

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER)
    c.watch(TurnEnd, ended, until=When.ENCOUNTER)
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: ctx.get("target") in seen)


@power("i3398p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.expended(unspent=)",))
def i3398p1(c: Cast) -> None:
    """The half that gains plays. The half that pays is re-aimed:
    `c.expend_row` takes a use off any creature by ref now, so spending
    is no longer the hold -- what is missing is *which* ref. The cost
    is "one ally loses a use of a daily magic item power", and nothing
    lists the rows a **different** creature still has unspent.
    `c.expended` reads the opposite set and only that one."""
    spent = _restorable(c, Usage.DAILY)
    if spent:
        c.restore_use(spent[0], on=c.me)


def _brought_low_under_mark(world: World, me: int, ev: Any) -> bool:
    """"You reduce an enemy marked by your p5736 to 10 hit points or fewer."

    `DamageApplied` is the only event carrying what the creature has left,
    and the mark is that row's own hold, found by label.
    """
    if getattr(ev, "source", None) != me or getattr(ev, "hp", 99) > 10:
        return False
    target = getattr(ev, "target", None)
    if target is None:
        return False
    return any(
        eff.source == me and "p5736" in eff.label
        for eff in world.effects.of(target)
    )


@power("i3410p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.kill()",),
       trigger="you reduce an enemy marked by your p5736 to 10 hit points",
       on=Trigger(DamageApplied, _brought_low_under_mark,
                  "you bring a marked enemy to 10 hit points or fewer"))
def i3410p1(c: Cast) -> None:
    """Re-aimed twice. `p5736` is declared after all, and its mark is an
    ordinary hold read by label, so the trigger is exact. What is still
    missing is the effect: nothing takes a creature to 0 except by
    dealing it damage, and damage is resisted and reduced where the
    printed sentence is not."""


@power("i3446x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3446x1(c: Cast) -> None:
    c.resist(3, DamageType.LIGHTNING, on=c.me, until=When.ENCOUNTER)
    c.resist(3, DamageType.THUNDER, on=c.me, until=When.ENCOUNTER)


@power("i3446p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
       trigger="you hit an enemy with a melee or ranged attack",
       on=Trigger(Hit, by_me, "you hit an enemy with an attack"))
def i3446p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.damage("1d6", dtype=DamageType.LIGHTNING, on=foe)
    for other in c.within(1, of=foe, side="enemy"):
        if other != foe:
            c.damage("1d6", dtype=DamageType.THUNDER, on=other)


@power("i811p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_initiative(keep=)",))
def i811p1(c: Cast) -> None:
    """Re-aimed to the same argument as `i2966p1`. The mount rolls with
    the rider's own modifier and the better of the two is kept, so it is
    two checks and one slot however the card phrases it."""


@power("i940x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i940x1(c: Cast) -> None:
    """"While adjacent to you" is asked of the board each time a defence
    is read; `query.defence` is handed the context that lets it."""
    beast = c.companion()
    if beast is not None:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 1, on=beast, until=When.ENCOUNTER, kind="item",
                    when=_near_companion(c, beast, 1))


# -- level 6 ----------------------------------------------------------------


@power("i1226x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1226x1(c: Cast) -> None:
    """A language."""


@power("i1226p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE],
       trigger="you hit with a primal power using a weapon",
       on=Trigger(Hit, _hit_by_me_with(Keyword.PRIMAL),
                  "you hit with a primal power"))
def i1226p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.damage("1d6", dtype=DamageType.FIRE, on=foe)
        c.ongoing(5, DamageType.FIRE, on=foe)


@power("i1409x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1409x1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power("i1409p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE])
def i1409p1(c: Cast) -> None:
    """One weapon rather than all of them is not a distinction a damage
    bonus can draw, but the wearer swings one thing. The die is fire and
    carries that type."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT,
            dtype=DamageType.FIRE)


@power("i1411p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you hit and damage an enemy with a melee attack",
       on=Trigger(Hit, both(by_me, by_melee),
                  "you hit an enemy with a melee attack"))
def i1411p1(c: Cast) -> None:
    c.heal(20 if getattr(c.trigger, "critical", False) else 10, on=c.me)


@power("i1500x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1500x1(c: Cast) -> None:
    """The extra square is laid on the hit rather than standing, so it
    only applies to the push the hit is about to make; the deafening is
    exact."""

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        c.forces(1, on=c.me, until=When.EOT)
        row = get(ev.power)
        if row is not None and Keyword.THUNDER in row.keywords:
            c.condition(Condition.DEAFENED, on=ev.target,
                        until=When.SAVE_ENDS)

    c.watch(Hit, landed, until=When.ENCOUNTER)


@power("i1500p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBlast(3), target=EACH_CREATURE, keywords=[Keyword.THUNDER],
       attack=Attack(vs=FORT, printed=8),
       damage=Damage("1d6", 0, dtype=DamageType.THUNDER))
def i1500p1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


@power("i1805x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1805x1(c: Cast) -> None:
    """"When the item is visible" is not a state anything keeps; an item
    a character is wearing is worn, so the bonus stands."""
    _skills(c, 4, "intimidate")


@power("i1805p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i1805p1(c: Cast) -> None:
    """Marking an object."""


@power("i1805p2", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you roll a natural 1 on an attack roll or a saving throw",
       on=(
           Trigger(AttackRolled, lambda w, me, ev: (
               getattr(ev, "attacker", None) == me
               and getattr(ev, "natural", 0) == 1),
               "you roll a natural 1 on an attack roll"),
           Trigger(SavingThrow, lambda w, me, ev: (
               getattr(ev, "actor", None) == me
               and getattr(ev, "natural", 0) == 1),
               "you roll a natural 1 on a saving throw"),
       ),
       dropped=("c.reroll_attacks_against()",))
def i1805p2(c: Cast) -> None:
    """Both printed rolls are declared, which is what a sequence of
    triggers is for. Forcing an *enemy* to reroll has no method."""
    if isinstance(c.trigger, SavingThrow):
        c.reroll_save(keep="new")
    else:
        c.reroll_attack(keep="new")


@power("i1809x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1809x1(c: Cast) -> None:
    beast = _the_mount(c)
    if beast is not None:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 1, on=beast, until=When.ENCOUNTER, kind="item")


@power("i1809p1", level=6, cls=ITEM, usage=AT_WILL, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack would damage the mount you are riding",
       on=Trigger(DamageRolled, lambda w, me, ev: (
           getattr(ev, "target", None) is not None
           and getattr(ev, "target", None) != me),
           "an attack would damage your mount"),
       dropped=("c.flat(unpreventable=)",))
def i1809p1(c: Cast) -> None:
    """"Nothing can reduce or prevent" the rider's share, and a flat hit
    has no flag for that, so the rider's resistances still apply."""
    beast = c.mount()
    ev = c.trigger
    if beast is None or getattr(ev, "target", None) != beast:
        return
    was = max(0, getattr(ev, "amount", 0))
    c.halve(ev)
    c.flat(was // 2, on=c.me)


@power("i2421x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2421x1(c: Cast) -> None:
    c.bonus(FORT, 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i2421p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you make an Endurance or Nature check and dislike it",
       on=Trigger(SkillCheck, my_check("endurance", "nature"),
                  "you make an Endurance or Nature check"))
def i2421p1(c: Cast) -> None:
    """"Use either result" is `keep="best"`, which is the difference
    between this and the rerolls that must take the second number."""
    c.reroll_check(keep="best")


@power("i2506x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2506x1(c: Cast) -> None:
    """Untyped in neither direction: the card prints "item bonus". Both
    halves are one gate read off the damage context's `target`, which is
    the enemy the card means by "that enemy"."""
    beast = c.companion()
    if beast is None:
        return

    def flanked(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and _flanking_with(c, beast, foe)

    for who in (c.me, beast):
        c.bonus("damage", 1, on=who, until=When.ENCOUNTER, kind="item",
                when=flanked)


@power("i3097x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3097x1(c: Cast) -> None:
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_bloodied_gate(c, True))


@power("i3097p1", level=6, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy bloodies you but does not drop you",
       on=Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"))
def i3097p1(c: Cast) -> None:
    c.reroll_damage(on=c.me, until=When.EONT)


@power("i3371x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3371x1(c: Cast) -> None:
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER)


@power("i3371p1", level=6, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PSYCHIC],
       trigger="an enemy attack hits your Will",
       on=Trigger(AttackRolled, lambda w, me, ev: (
           getattr(ev, "target", None) == me
           and str(getattr(ev, "vs", "")) == "will"
           and getattr(ev, "total", 0) >= getattr(ev, "defence", 99)),
           "an attack hits your Will"))
def i3371p1(c: Cast) -> None:
    """Declared on `AttackRolled`: the die is down and the total known, but
    the defence is read again once this window closes, so turning the blow
    aside still works. `Hit` carries no defence to ask."""
    foe = getattr(c.trigger, "attacker", None)
    c.cancel()
    if foe is not None:
        c.damage("2d10", dtype=DamageType.PSYCHIC, on=foe)
        c.dazed(on=foe, until=When.EONT)


@power("i3376p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       dropped=("c.flat(unpreventable=)",))
def i3376p1(c: Cast) -> None:
    """The ally's five damage is optional and is offered to the ally, not
    taken from them; "cannot be prevented in any way" has no flag."""
    c.shift(2)

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        friends = [a for a in c.within(5, side="ally")]
        if friends and c.may("take 5 damage", who=friends[0]):
            c.flat(5, on=friends[0])
            c.heal(10, on=c.me)
        else:
            c.heal(5, on=c.me)

    c.watch(Hit, landed, until=When.EOT, once=True)


# -- level 7 ----------------------------------------------------------------


@power("i1020x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1020x1(c: Cast) -> None:
    """`MoveEnd` carries `kind_` and fires where the creature has landed,
    which is the moment "when you shift" is asking about."""

    def moved(ev: MoveEnd) -> None:
        if ev.actor == c.me and ev.kind_ == "shift":
            c.bonus(AC, 1, on=c.me, until=When.EONT, kind="item")
            c.bonus(REF, 1, on=c.me, until=When.EONT, kind="item")

    c.watch(MoveEnd, moved, until=When.ENCOUNTER)


@power("i1020p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1020p1(c: Cast) -> None:
    c.shift(2)


@power("i1255x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1255x1(c: Cast) -> None:
    _skills(c, 1, "intimidate")


@power("i1255p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FEAR],
       trigger="you score a critical hit with a weapon attack",
       on=Trigger(Hit, _my_crit_with(Keyword.WEAPON),
                  "you score a critical hit with a weapon attack"))
def i1255p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.EONT)
    for other in c.within(1, of=foe, side="enemy"):
        if other != foe:
            c.penalty("attack", 2, on=other, until=When.EONT)


@power("i1704x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.light_level(world, square)",))
def i1704x1(c: Cast) -> None:
    """Concealment from obscured squares is not kept per square, so there
    is nothing to carry out of the square the wearer is leaving."""


@power("i1704p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON],
       trigger="you hit an enemy with a weapon attack",
       on=Trigger(Hit, _hit_by_me_with(Keyword.WEAPON),
                  "you hit an enemy with a weapon attack"))
def i1704p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.damage("1d6", dtype=DamageType.POISON, on=foe)


@power("i1742x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1742x1(c: Cast) -> None:
    """A ritual's skill check. Rituals are not a fight."""


@power("i1742p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you take damage of a specific type",
       on=Trigger(DamageRolled, lambda w, me, ev: (
           getattr(ev, "target", None) == me
           and getattr(ev, "dtype", None) is not None
           and str(getattr(ev, "dtype", "")) != "untyped"),
           "you take typed damage"))
def i1742p1(c: Cast) -> None:
    kind = getattr(c.trigger, "dtype", None)
    if kind is not None:
        c.resist(5, kind, on=c.me, until=When.ENCOUNTER)


@power("i1807x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("SurgeSpent.source",))
def i1807x1(c: Cast) -> None:
    """The resistance is exact. `SurgeSpent` names the creature whose
    surge went and not who took it, so "if an enemy causes you to lose
    one" cannot be told from spending one yourself."""
    c.resist(5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)


@power("i2101p1", level=7, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a primal power with the polymorph keyword",
       on=Trigger(PowerUsed, _used_with(Keyword.POLYMORPH),
                  "you use a polymorph power"))
def i2101p1(c: Cast) -> None:
    """Both keywords are printed; `_used_with` asks for the polymorph one,
    which is the narrower of the two and the one that names the moment."""
    c.temp_hp(2 + c.con_mod, on=c.me)


@power("i2159x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2159x1(c: Cast) -> None:
    _skills(c, 2, "stealth")


@power("i2159p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("c.blindsight()",),
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll initiative"))
def i2159p1(c: Cast) -> None:
    """Hiding is exact; nothing models blindsight or tremorsense, so the
    clause that beats them has nothing to beat."""
    c.hide(until=When.EONT)


@power("i2419x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2419x1(c: Cast) -> None:
    c.bonus("skill:athletics", 4, on=c.me, until=When.ENCOUNTER,
            kind="item", when=_bloodied_gate(c, False))


@power("i2419p1", level=7, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PSIONIC],
       trigger="you hit with an unaugmented at-will attack power",
       out_of_combat=True)
def i2419p1(c: Cast) -> None:
    """`c.jump` asks for no check and needs no running start, so the whole
    printed benefit is the removal of a cost the engine never charges.
    Inert by construction rather than unwritten: there is no jump action
    and no Athletics roll for a circumstance to be carved out of."""


@power("i2967p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.MARTIAL],
       charges=True)
def i2967p1(c: Cast) -> None:
    """`charges=True` or the engine measures the reach before the run and
    refuses the row whenever the target is further off than a sword."""
    foe = c.target
    if foe is None:
        return
    c.charge_at(foe)
    beast = c.companion()
    if beast is not None:
        c.charge_at(foe, who=beast)


@power("i3359p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3359p1(c: Cast) -> None:
    """A bearing on an object the wearer has held."""


@power("i3384p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i3384p1(c: Cast) -> None:
    """`PowerResolved` rather than `Hit`: the shift is printed as
    happening *after* the attack, hit or miss, and `PowerUsed` announces
    before the body has run."""
    c.jump(c.speed_of())

    def finished(ev: PowerResolved) -> None:
        if ev.actor != c.me or ev.power == c.ref:
            return
        row = get(ev.power)
        if row is not None and row.reach is not None and row.reach.kind == "melee":
            c.shift(max(1, c.speed_of() // 2))

    c.watch(PowerResolved, finished, until=When.EOT, once=True)


@power("i3443x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3443x1(c: Cast) -> None:
    """Five points of fire resistance, and only on a fire attack -- which
    is the damage type the context carries, not the power's keywords:
    "your fire attacks" is about what the blow deals."""
    c.ignore_resistance(
        5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("dtype") is DamageType.FIRE,
    )


@power("i3443p1", level=7, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
       trigger="a creature within 10 squares of you takes fire damage",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           getattr(ev, "dtype", None) is DamageType.FIRE
           and getattr(ev, "target", None) is not None),
           "a creature within 10 squares takes fire damage"))
def i3443p1(c: Cast) -> None:
    """"Before and after the teleportation" is two separate reads of who
    is adjacent, taken either side of the move."""
    burned = getattr(c.trigger, "target", None)
    if burned is None or c.distance(burned) > 10:
        return
    before = set(c.within(1, side="enemy"))
    square = _free_near(c, burned)
    if square is not None:
        c.teleport(10, to=square)
    for foe in before | set(c.within(1, side="enemy")):
        c.flat(3, dtype=DamageType.FIRE, on=foe)


@power("i455x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i455x1(c: Cast) -> None:
    """Traps, foraging and navigating underground. No fight rolls Thievery
    or Dungeoneering, so the whole property is narrative."""


@power("i455p1", level=7, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you make a Thievery or Dungeoneering roll and dislike it",
       on=Trigger(SkillCheck, my_check("thievery", "dungeoneering"),
                  "you make a Thievery or Dungeoneering check"))
def i455p1(c: Cast) -> None:
    """"Whether it is higher or lower" is `keep="new"`."""
    c.reroll_check(keep="new")


# -- level 8 ----------------------------------------------------------------


@power("i1132p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE,
       dropped=("c.hit_this_turn()",))
def i1132p1(c: Cast) -> None:
    """Nothing records what a creature has hit or missed this turn, so the
    printed Requirement is unenforced and "the same enemy" becomes
    whichever one the row is aimed at."""
    foe = c.target
    if foe is not None and c.basic(on=foe):
        c.grants_advantage(on=foe, until=When.EONT)


@power("i1205x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1205x1(c: Cast) -> None:
    c.bonus("skill:insight", 4, on=c.me, until=When.ENCOUNTER,
            kind="item", when=_bloodied_gate(c, False))


@power("i1205p1", level=8, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PSIONIC],
       trigger="you hit with an unaugmented at-will attack power",
       on=Trigger(Hit, _at_will_hit, "you hit with an at-will attack power"))
def i1205p1(c: Cast) -> None:
    if _unaugmented(c):
        c.temp_hp(10, on=c.me)


@power("i1614x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1614x1(c: Cast) -> None:
    _skills(c, 2, "diplomacy", "insight")


@power("i1614p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you roll a Diplomacy or Insight check",
       on=Trigger(SkillCheck, my_check("diplomacy", "insight"),
                  "you roll a Diplomacy or Insight check"))
def i1614p1(c: Cast) -> None:
    c.reroll_check(keep="new")


@power("i1695x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def i1695x1(c: Cast) -> None:
    """Running is not an action the engine takes, so there is no -5 to
    soften."""


@power("i1695p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1695p1(c: Cast) -> None:
    c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")


@power("i1908p1", level=8, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("Miss.all_targets",),
       trigger="you use an encounter or daily power and miss all targets",
       on=Trigger(Miss, by_me, "you miss with an attack"))
def i1908p1(c: Cast) -> None:
    """A `Miss` is announced per target, so "miss *all* targets" cannot be
    told from missing one of several."""
    row = get(getattr(c.trigger, "power", "") or "")
    if row is None or row.usage is Usage.AT_WILL:
        return
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True)


@power("i1908p2", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an enemy hits you while you are adjacent to an ally",
       on=Trigger(DamageRolled, targets_me, "an enemy damages you"))
def i1908p2(c: Cast) -> None:
    friends = c.within(1, side="ally")
    if not friends:
        return
    ally = friends[0]
    was = max(0, getattr(c.trigger, "amount", 0))
    c.halve()
    c.flat(was // 2, on=ally)
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.bonus("attack", 1, on=ally, until=When.EOTNT, kind="power",
                when=_against(foe))


@power("i2153p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack bloodies you or drops you to 0 hit points",
       on=(
           Trigger(Bloodied, about_me, "you are bloodied"),
           Trigger(Dropped, about_me, "you drop to 0 hit points"),
       ))
def i2153p1(c: Cast) -> None:
    beast = c.companion()
    if beast is not None:
        c.pull(10, on=beast)


@power("i2164x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2164x1(c: Cast) -> None:
    _on_second_wind(c, lambda: c.shift(1))


@power("i2164p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy bloodies you but does not drop you",
       on=Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"))
def i2164p1(c: Cast) -> None:
    c.temp_hp(c.surge_value(), on=c.me)


@power("i2383x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2383x1(c: Cast) -> None:
    _skills(c, 1, "arcana", "history", "nature", "religion")


@power("i2383p1", level=8, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i2383p1(c: Cast) -> None:
    c.teleport(1 + max(c.cha_mod, c.wis_mod))


@power("i2427p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="a critical hit is scored on you",
       on=Trigger(Hit, _crit_on_me, "a critical hit is scored on you"))
def i2427p1(c: Cast) -> None:
    c.surge(on=c.me)


@power("i2671p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="the mount you are riding would be pulled, pushed or slid",
       on=Trigger(ForcedMove, lambda w, me, ev: (
           getattr(ev, "target", None) is not None
           and getattr(ev, "target", None) != me),
           "your mount would be moved"))
def i2671p1(c: Cast) -> None:
    beast = c.mount()
    if beast is not None and getattr(c.trigger, "target", None) == beast:
        c.cancel()


@power("i2860x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2860x1(c: Cast) -> None:
    """Flying is a movement mode rather than a kind of move, so the second
    half asks `MoveEnd.kind_` for the shift and `c.moving_as` for the
    flight."""
    _skills(c, 2, "acrobatics", "athletics")

    def moved(ev: MoveEnd) -> None:
        if ev.actor != c.me:
            return
        if ev.kind_ == "shift" or c.moving_as("fly", on=c.me):
            c.bonus("attack", 1, on=c.me, until=When.EOT, kind="power",
                    once=True)

    c.watch(MoveEnd, moved, until=When.ENCOUNTER)


@power("i3386p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i3386p1(c: Cast) -> None:
    c.move(max(1, c.speed_of() // 2))

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        c.immobilized(on=ev.target, until=When.EONT)
        c.shift(1)

    c.watch(Hit, landed, until=When.EOT, once=True)


@power("i3401x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.insubstantial(when=)",))
def i3401x1(c: Cast) -> None:
    """Insubstantial is a property of the creature and not of one
    attacker's blows, and the damage context carries no attacker."""


@power("i3401p1", level=8, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON],
       trigger="you hit a creature with a melee or a ranged attack",
       on=Trigger(Hit, by_me, "you hit a creature with an attack"))
def i3401p1(c: Cast) -> None:
    """Ongoing damage is dealt with the creature that laid it as the
    source -- `durations` hands `eff.source` to `world.damage` -- so an
    ignore laid on the wearer reaches it. Gated on the burning creature
    rather than on the power, because the burn's `detail` is the effect's
    own description and not a ref."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.ongoing(5, DamageType.POISON, on=foe)
        c.ignore_resistance(
            None, DamageType.POISON, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("i3445p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=CloseBurst(10), target=SELF, no_provoke=True,
       trigger="an enemy pulls, pushes, or slides you",
       on=Trigger(ForcedMove, _forced_on_me, "an enemy moves you"))
def i3445p1(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "source", None)
    if foe is not None:
        c.push(max(1, getattr(ev, "squares", 1)), on=foe)


@power("i441p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.FEAR])
def i441p1(c: Cast) -> None:
    c.penalty("attack", 2, until=When.EOTNT)


@power("i441p2", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Ranged(3), target=ONE_ALLY, no_provoke=True,
       keywords=[Keyword.TELEPORTATION],
       trigger="an enemy hits you with an attack",
       on=Trigger(Hit, targets_me, "an enemy hits you"))
def i441p2(c: Cast) -> None:
    """`c.redirect` only works from inside the interrupt window of the
    attack being answered, which is exactly where this row is."""
    ally = c.target
    if ally is None:
        return
    c.swap(ally)
    c.redirect(to=ally)


@power("i740x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i740x1(c: Cast) -> None:
    _skills(c, 2, "insight", "perception")


@power("i865p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack hits your familiar",
       on=Trigger(Hit, lambda w, me, ev: (
           getattr(ev, "target", None) is not None
           and getattr(ev, "target", None) != me),
           "an attack hits your familiar"))
def i865p1(c: Cast) -> None:
    fam = c.familiar()
    if fam is None or getattr(c.trigger, "target", None) != fam:
        return
    c.bonus(AC, 4, on=fam, until=When.EONT, kind="power")
    c.bonus(REF, 4, on=fam, until=When.EONT, kind="power")


# -- level 9 ----------------------------------------------------------------


@power("i1021p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       requires=_bloodied_req, requires_text="you must be bloodied")
def i1021p1(c: Cast) -> None:
    c.temp_hp(c.surge_value(), on=c.me)


@power("i1716x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1716x1(c: Cast) -> None:
    """`c.initiative` adds to the check itself; it takes no `kind`, so the
    item type the card prints is not carried."""
    c.initiative(1, on=c.me)
    for friend in c.within(5, side="team"):
        c.initiative(1, on=friend)


@power("i2173x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2173x1(c: Cast) -> None:
    """Untyped: the card prints a bare "+2 bonus". "Charm or fear" is the
    keywords of the row that laid the hold, which the saving-throw context
    now carries."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER,
            when=_save_keywords(Keyword.CHARM, Keyword.FEAR))


@power("i2173p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are dominated",
       on=Trigger(RelationSet, _dominated_on_me, "you are dominated"))
def i2173p1(c: Cast) -> None:
    """`dsl.use` spends the use above the body, so the row can hand its
    own back: `c.restore_use` undoes exactly the `note_use` that was
    made on the way in."""
    if not c.save(on=c.me):
        c.restore_use(c.ref, on=c.me)


@power("i2968x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2968x1(c: Cast) -> None:
    beast = c.companion()
    if beast is not None:
        c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER,
                kind="item", when=_near_companion(c, beast, 5))


@power("i2968p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
       trigger="an adjacent enemy targets you with a melee attack",
       on=Trigger(AttackDeclared, both(targets_me, by_melee),
                  "an adjacent enemy targets you with a melee attack"))
def i2968p1(c: Cast) -> None:
    beast = c.companion()
    foe = getattr(c.trigger, "attacker", None)
    if beast is None or foe is None or not c.adjacent(beast):
        return
    square = _free_near(c, foe)
    if square is not None:
        c.slide(2, on=beast, to=square)
    c.basic(who=beast, on=foe)


@power("i3067x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3067x1(c: Cast) -> None:
    c.initiative(1, on=c.me)
    _skills(c, 1, "perception")


@power("i3067p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=WILL, printed=12),
       trigger="an enemy enters a square adjacent to you",
       on=Trigger(AdjacencyGained, closed_on_me,
                  "an enemy moves adjacent to you"))
def i3067p1(c: Cast) -> None:
    """The penalty is gated on the attack context's `target`, which is
    what "attack rolls that include you as a target" means."""
    if not c.strike():
        return
    c.grants_advantage(until=When.EONT)
    c.penalty("attack", 2, until=When.EONT, when=_against(c.me))


@power("i3110x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.water()",))
def i3110x1(c: Cast) -> None:
    """Difficult terrain is exact; there is no liquid surface to walk on,
    so that clause has nothing to apply to."""
    beast = _the_mount(c)
    if beast is not None:
        c.ignores_difficult(on=beast, until=When.ENCOUNTER)


@power("i3358p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(20), target=NO_TARGET, keywords=[Keyword.ZONE],
       out_of_combat=True)
def i3358p1(c: Cast) -> None:
    """Six hours of calmer weather. There is no weather."""


@power("i3369p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3369p1(c: Cast) -> None:
    c.bonus("skill:intimidate", 2, on=c.me, until=When.EONT, kind="power")


@power("i3400x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3400x1(c: Cast) -> None:
    """"Knowledge checks" is a named set of five skills, so it is five
    real modifiers rather than a missing key for "any"."""
    _skills(c, 2, "arcana", "dungeoneering", "history", "nature", "religion")


@power("i3400p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=ONE_ALLY)
def i3400p1(c: Cast) -> None:
    """The vulnerability and the resistance are exact, and the extra die
    is necrotic like the attacks it rides on."""
    c.vulnerable(5, DamageType.NECROTIC, until=When.ENCOUNTER)
    if not c.first:
        return
    c.resist(10, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
            dtype=DamageType.NECROTIC,
            when=_dtype_gate(DamageType.NECROTIC))


@power("i3455x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.light_level(world, square)", "SavingThrow.ongoing"))
def i3455x1(c: Cast) -> None:
    """Neither half can be said. The vision half is re-aimed at the same
    missing light model `i1704x1` wants, since low-light vision is only a
    benefit where a square can be dim. The save half stands: `Effects.save`
    puts `ongoing` and `dtypes` in the *modifier* context, and a `+2` is
    all a modifier can be -- "roll twice and use either result" has to be
    answered on the event, which carries neither."""


@power("i3455p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.FIRE, Keyword.RADIANT],
       trigger="you use an at-will attack power and hit at least one target",
       on=Trigger(Hit, _at_will_hit, "you hit with an at-will attack power"))
def i3455p1(c: Cast) -> None:
    """"Ongoing 5 fire and radiant" is one burn of two types -- five a
    turn, one save, and shrugged off only as far as the creature resists
    both. The d6 is rolled per target hit, and the trigger fires once per
    hit, so it is rolled here."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None and c.roll("1d6") >= 3:
        c.ongoing(5, dtypes=(DamageType.FIRE, DamageType.RADIANT), on=foe)


@power("i512x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i512x1(c: Cast) -> None:
    _skills(c, 2, "diplomacy", "intimidate")


@power("i512p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(3), target=NO_TARGET,
       keywords=[Keyword.PSYCHIC, Keyword.ZONE],
       dropped=("c.grants_in(when=)",))
def i512p1(c: Cast) -> None:
    """`c.grants_in` carries a flat value and no dice and no gate, so the
    die is laid on each ally standing in the zone when it is made: an
    ally who walks in later does not pick it up."""
    area = c.area()
    c.zone(area, until=When.EONT)
    for friend in c.in_squares(area, side="ally"):
        if friend == c.me:
            continue
        c.bonus("damage", 0, dice="1d6", on=friend, until=When.EONT,
                dtype=DamageType.PSYCHIC,
                when=lambda ctx: ctx.get("target") != c.me)


# -- level 10 ---------------------------------------------------------------


@power("i1493x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1493x1(c: Cast) -> None:
    """Asked on the first `RoundStart` and not here: `Encounter.start`
    arms the traits *before* it applies `Condition.SURPRISED`, so the
    obvious read at arming time is false in every fight that has a
    surprise round -- which is the only fight this clause is about."""
    beast = c.companion()
    if beast is None:
        return
    c.bonus("skill:perception", 3, on=beast, until=When.ENCOUNTER,
            kind="item")

    def opened(ev: RoundStart) -> None:
        if not c.is_(Condition.SURPRISED, on=beast):
            c.cure(Condition.SURPRISED, on=c.me)

    c.watch(RoundStart, opened, until=When.ENCOUNTER, once=True)


@power("i1675x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1675x1(c: Cast) -> None:
    """The same shape as `i958x1`; the card's "level 1" is every at-will
    there is, so the two lists are the same list."""
    ref = c.choose(_arcane_rows(Usage.AT_WILL, 1), "which arcane at-will")
    if ref is not None:
        c.grant_row(ref, on=c.me, uses=1)


@power("i1675p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("Miss.all_targets",),
       trigger="you use an arcane attack power and miss all targets",
       on=Trigger(Miss, _hit_by_me_with(Keyword.ARCANE),
                  "you miss with an arcane attack power"))
def i1675p1(c: Cast) -> None:
    """A `Miss` is announced per target, so missing *all* of them cannot
    be told from missing one."""
    c.reroll_attack(keep="new")


@power("i2838x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2838x1(c: Cast) -> None:
    """"A nonminion enemy" is `c.is_minion`, off the stat block's own
    column. `c.save` follows the target, so the saving throw the card
    gives *you* names you."""

    def felled(ev: Dropped) -> None:
        if ev.source == c.me and ev.actor != c.me and not c.is_minion(on=ev.actor):
            c.save(on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER)


@power("i2838p1", level=10, cls=ITEM, usage=DAILY, action=REACTION,
       reach=Ranged(10), target=SELF, no_provoke=True,
       trigger="an ally you can see reduces a creature to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) is not None
           and getattr(ev, "source", None) != me),
           "an ally reduces a creature to 0 hit points"))
def i2838p1(c: Cast) -> None:
    ally = getattr(c.trigger, "source", None)
    if ally is None or ally not in c.allies() or not c.can_see(ally):
        return
    c.shift(1, who=ally)
    c.basic(who=ally)
