"""Implement-slot magic items, heroic tier, third wave: levels 5 to 8.

Nothing here declares an implement. The ladder, the enhancement bonus, the
price, the critical rider and the base-item restriction are columns in
`game.db` and are laid on by `engine/equipment.py`; what is written here is
only the part that needs a body.

The same three judgements as the two files beside this one:

* **"Using this implement" cannot be gated.** Neither the attack context
  nor the damage context carries the item, so a property phrased that way
  is armed always-on -- the carrier is holding the item for as long as the
  property is armed. That over-applies only for somebody carrying two
  implements of which one is magical.
* **The class half of a line is not enforced.** "A wizard fire power", "a
  primal attack power": the item was dealt to whoever holds it. Where the
  *keyword* is printed -- radiant, force, psychic -- `by_keyword` reads it
  off the power and the gate is real.
* **A `Level 11:` or higher line is paragon and out of scope**, so only the
  heroic number is written.

Two traps this wave walked into, recorded so the next one does not:

* **`by_me` reads `ev.attacker` or `ev.source` and nothing else.** On
  `PowerUsed`, `Moved`, `SurgeSpent` and `SavingThrow` -- which name their
  subject `actor` -- it is false forever. Those use `about_me`.
* **`c.summon` sets no relation**, so "a creature you summoned" can only be
  approximated by the servants and companions the board does record. Every
  row that needs it carries `query.is_summoned()`.

The recurring gaps, each named with the symbol it wants rather than
approximated: `c.pact_boon()` (four blocks), `c.class_feature()` (four),
`c.curse_damage()`, `c.reshape_area()`, `c.expend()` and `c.item_set()`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
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
    WIS,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    EffectApplied,
    Forced,
    ForcedMove,
    Healed,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerUsed,
    Ranged,
    Relation,
    SavingThrow,
    SurgeSpent,
    Trigger,
    Usage,
    When,
    World,
    about_me,
    both,
    by_keyword,
    by_me,
    get,
    power,
    query,
    spread,
)

ITEM = "item"

#: The four defences, for the many blocks reading "all defenses".
_DEFENCES = (AC, FORT, REF, WILL)

#: "Choose acid, cold, fire, lightning, or poison" -- one printed list, on
#: three blocks in this file.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


def _struck(c: Cast) -> int | None:
    """The creature the triggering attack was aimed at.

    A row triggered by **your own** hit is aimed at `ev.attacker` -- you --
    by the auto-targeter, so it can pick a different enemy than the one
    just hit. Every "use this power when you hit" row reads the event.
    """
    foe = getattr(c.trigger, "target", None)
    return foe if foe is not None else c.target


def _square(c: Cast, who: int | None):  # noqa: ANN202
    from combat_engine.engine import Position

    pos = c.world.get(who, Position) if who is not None else None
    return pos.square if pos is not None else None


def _keywords_of(ref: str | None) -> frozenset[Keyword]:
    p = get(ref or "")
    return frozenset(p.keywords) if p is not None else frozenset()


def _has_keyword(*words: Keyword):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return bool(_keywords_of(ctx.get("power")) & set(words))

    return gate


def _is_melee(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach_of(0).kind == "melee"


def _bloodied_target(c: Cast):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and c.bloodied(on=foe)

    return gate


def _whole_target(c: Cast):  # noqa: ANN202
    """"A creature that has maximum hit points", asked of the damage ctx."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and c.missing(on=foe) == 0

    return gate


def _just_bloodied(c: Cast, ev: Any) -> bool:
    """Did *this* blow take the creature across the halfway line?

    `Bloodied` names no source, so "an enemy **you** bloody" has to be read
    off the damage, which carries both the hit points left and how many
    came off.
    """
    h = c.world.get(getattr(ev, "target", None), Health)
    if h is None:
        return False
    half = h.max_hp // 2
    return ev.hp <= half < ev.hp + ev.amount


def _mine(c: Cast) -> list[int]:
    """The creatures on the board that answer to this one.

    `c.summon` records nothing, so this is servants and companions -- what
    the relations actually hold. Every row using it says so with
    `query.is_summoned()`.
    """
    pool = list(c.servants())
    pool += [s for s in c.companions() if s not in pool]
    return pool


def _my_side(world: World, me: int, who: int | None) -> bool:
    return who is not None and query.team(world, who) is query.team(world, me)


def _my_other_power(ref: str):  # noqa: ANN202
    """A use of mine that is not this row answering itself.

    `PowerUsed` is emitted for the free action too, so a row triggered by
    "you attack with a power" and declared on every one of them recurs
    until the stack runs out.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        return getattr(ev, "actor", None) == me and getattr(ev, "power", "") != ref

    return check


def _enemy_saving(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    return who is not None and who != me and not _my_side(world, me, who)


def _ally_hit_within(n: int):  # noqa: ANN202
    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me or not _my_side(world, me, who):
            return False
        return query.distance_between(world, me, who) <= n

    return check


def _hits_my_summon(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None:
        return False
    return who in world.relations.targets(Relation.MASTER_OF, me)


def _save_ends_near(world: World, me: int, ev: Any) -> bool:
    """"You or an ally you can see is subjected to an effect a save can end.\""""
    if not getattr(ev, "save_ends", False):
        return False
    who = getattr(ev, "target", None)
    return who is not None and _my_side(world, me, who)


def _my_push(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and getattr(ev, "how", None) is Forced.PUSH


def _long_move(world: World, me: int, ev: Any) -> bool:
    """"You move at least half your speed during this turn.\""""
    if getattr(ev, "actor", None) != me:
        return False
    a, b = ev.from_, ev.to
    gone = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
    return gone >= max(1, query.speed(world, me) // 2)


def _pick(c: Cast, radius: int) -> int:
    """"You or an ally within N squares" -- the caster is in the pool."""
    pool = [c.me, *c.within(radius, side="ally")]
    chosen = c.choose(pool, "who gains it")
    return chosen if chosen is not None else c.me


def _as_row(c: Cast, ref: str) -> None:
    """"As the <class>'s <name> power": hand the row over for one use.

    `dsl.usable` refuses a row the creature does not know, so the loan is
    what makes the use legal; `c.grant_row` returns None for a row the
    character already has, so a cleric's own copy is never touched.
    """
    borrowed = c.grant_row(ref, until=When.ENCOUNTER)
    try:
        c.grant_attack(c.me, ref=ref)
    finally:
        if borrowed is not None:
            c.world.effects.end(borrowed, "the lent row is given back")


# -- level 5 ----------------------------------------------------------------


@power(
    "i526x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.augment_area()",),
)
def i526x1(c: Cast) -> None:
    """`c.widen_areas` lengthens a blast or a burst; a zone's footprint and
    a wall's length are fixed where they are laid and nothing reaches them
    afterwards."""


@power(
    "i526p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reshape_area()",),
)
def i526p1(c: Cast) -> None:
    """`c.move_zone` carries a shape from one place to another; reshaping
    one around a square that stays put is a different operation."""


@power(
    "i704x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i704x1(c: Cast) -> None:
    """The attack context carries `target`, so "against bloodied creatures"
    is a gate the engine can read. A plain "+1 bonus": untyped."""
    c.bonus(
        "attack",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=_bloodied_target(c),
    )


@power(
    "i724x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.flurry_of_blows()",),
)
def i724x1(c: Cast) -> None:
    """Nothing counts a class feature's uses within a turn, so an extra one
    cannot be handed back."""


@power(
    "i724p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you move at least half your speed during this turn",
    on=Trigger(Moved, _long_move, "you move at least half your speed"),
)
def i724p1(c: Cast) -> None:
    """`Moved` carries `from_` and `to` and no distance, so the half-speed
    test is the step it took, measured."""
    for d in _DEFENCES:
        c.bonus(d, 2, on=c.me, until=When.EONT)


@power(
    "i744x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.ignore_resistance()", "c.tome_powers()"),
)
def i744x1(c: Cast) -> None:
    """Both halves are missing: nothing pierces a resistance by a number,
    and a tome's two stored powers are not a thing the engine holds."""


@power(
    "i744p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    todo=("c.tome_powers()", "c.expend()"),
)
def i744p1(c: Cast) -> None:
    """`x9_146` is the power the tome would lend, and no row of that ref
    exists to lend -- it is one of the two the tome stores, which nothing
    holds. Spending a daily to buy it has no hold either."""


@power(
    "i859x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.borrow_feature()",),
)
def i859x1(c: Cast) -> None:
    """The bonus and the vulnerability are one bargain, so the second is
    armed off the hit that pays the first.

    The exemptions are dropped. Having a class feature *is* askable now --
    `Powers.known` is the list -- but the one the card names by ref,
    `cf:sorcerer-f0s3`, is a ref no row in the tree declares, and the
    star pact is one of `cf:warlock-f1`'s legs with nothing naming which.
    So the bargain is charged to everybody."""
    c.bonus(
        "damage",
        c.enhancement,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_has_keyword(Keyword.PSYCHIC),
    )

    def price(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if Keyword.PSYCHIC not in _keywords_of(ev.power):
            return
        c.vulnerable(5, DamageType.PSYCHIC, on=c.me, until=When.SONT)

    c.watch(Hit, price, until=When.ENCOUNTER)


@power(
    "i859p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit with an arcane power with the psychic keyword",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.PSYCHIC)), "you hit with psychic"),
)
def i859p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.damage("1d10", dtype=DamageType.PSYCHIC, on=foe)


# -- level 6 ----------------------------------------------------------------


@power(
    "i1852p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.curse_damage()",),
)
def i1852p1(c: Cast) -> None:
    """The curse's dice are paid out inside the warlock's own feature and
    nothing announces them, so neither the trigger nor "two dice more" can
    be said."""


@power(
    "i1956p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger="a creature makes a save against one of your powers",
    on=Trigger(SavingThrow, _enemy_saving, "an enemy makes a saving throw"),
    dropped=("SavingThrow.source",),
)
def i1956p1(c: Cast) -> None:
    """`SavingThrow` names the roller and not whose effect is being shaken
    off, so "against one of **your** powers" is not narrowed. "Must take
    the new result" is `keep="new"`."""
    c.reroll_save(keep="new")


@power(
    "i1968p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.worsen_save()", "Hit.vs"),
)
def i1968p1(c: Cast) -> None:
    """Two gaps at once: `Hit` does not carry the defence that was attacked,
    and nothing makes a saving throw roll twice and keep the lower. A save
    penalty is a different number and would not be this line."""


# -- level 7 ----------------------------------------------------------------


@power(
    "i1098x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.extra_area_target()",),
)
def i1098x1(c: Cast) -> None:
    """Both halves hang on a second target for `p2273`: nothing widens
    another row's target line, and the attack bonus is gated on a use that
    would not exist."""


@power(
    "i1098p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.expend()",),
)
def i1098p1(c: Cast) -> None:
    """The spec prints the ref, so the loan is real; the price -- an unused
    utility of level 6 or higher -- has nothing to charge it to."""
    c.grant_row("p2273", until=When.ENCOUNTER)


@power(
    "i1160x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1160x1(c: Cast) -> None:
    """"Pushed, slid, or knocked prone" is two events, not one: `ForcedMove`
    names the shove before it happens and `ConditionApplied` names the
    fall. Declaring half of it would look finished."""
    from combat_engine.engine import ConditionApplied

    def shoved(ev: ForcedMove) -> None:
        if ev.source != c.me or ev.how is Forced.PULL:
            return
        c.damage("1d6", on=ev.target)

    def felled(ev: ConditionApplied) -> None:
        if ev.source != c.me or ev.condition is not Condition.PRONE:
            return
        c.damage("1d6", on=ev.target)

    c.watch(ForcedMove, shoved, until=When.ENCOUNTER)
    c.watch(ConditionApplied, felled, until=When.ENCOUNTER)


@power(
    "i1843p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
    trigger="you reduce an enemy to 0 hit points with this holy symbol",
    on=Trigger(Dropped, by_me, "you drop an enemy"),
)
def i1843p1(c: Cast) -> None:
    """`Dropped` carries `source`, so `by_me` is the whole trigger. The
    burst is measured from the creature that fell, not from the caster, so
    the row is written as a loop rather than as a declared burst."""
    fallen = getattr(c.trigger, "actor", None)
    if fallen is None:
        return
    for foe in c.within(5, of=fallen, side="enemy"):
        c.flat(c.cha_mod + c.enhancement, dtype=DamageType.RADIANT, on=foe)


@power(
    "i1884x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.silvered()",),
)
def i1884x1(c: Cast) -> None:
    """No creature in the tree resists anything by material, so there is
    nothing for a silvered implement to beat."""


@power(
    "i1884p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an arcane radiant power using this staff",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.RADIANT)), "you hit with radiant"),
)
def i1884p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.flat(5 + c.enhancement, dtype=DamageType.RADIANT, on=foe)


@power(
    "i1958p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1958p1(c: Cast) -> None:
    """"Any attack" -- an ally's as readily as yours, so the watch is not
    gated on the attacker. The prone is conditional on the fall actually
    reaching the ground, which is what the height before it says."""

    def drop(ev: Hit) -> None:
        foe = ev.target
        up = c.height(on=foe)
        if up <= 0 or c.distance(to=foe) > 10:
            return
        c.fall(10, on=foe, safe=True)
        if up <= 10:
            c.prone(on=foe)

    c.watch(Hit, drop, until=When.EONT)


@power(
    "i1979p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reshape_area()",),
)
def i1979p1(c: Cast) -> None:
    """A power's reach is header data read before the body runs; nothing
    turns a declared blast into a burst of another size."""


@power(
    "i2292p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a divine attack power using this rod",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.DIVINE)), "you hit with divine"),
)
def i2292p1(c: Cast) -> None:
    """"Until the end of its next turn" is the target's turn, not yours."""
    foe = _struck(c)
    if foe is not None:
        c.immobilized(on=foe, until=When.EOTNT)


@power(
    "i2306p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger="you attack with an implement power using this implement",
    on=Trigger(PowerUsed, _my_other_power("i2306p1"), "you use a power"),
    dropped=("c.add_keyword()",),
)
def i2306p1(c: Cast) -> None:
    """`PowerUsed` names its subject `actor`, so this is `about_me` and not
    `by_me` -- and the row must leave itself out, or answering its own free
    action recurs forever. Targets are chosen before the body runs, so
    `ev.targets` is
    the one thing on that event worth trusting -- and "hit or miss" wants
    exactly that list. Nothing adds a keyword to an attack already
    declared, so the fear half of the line is dropped."""
    for foe in getattr(c.trigger, "targets", []):
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "i2309x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.strip_resistance()",),
)
def i2309x1(c: Cast) -> None:
    """`c.resist` grants one and nothing takes one away, so "loses resist
    poison" has nowhere to land."""


@power(
    "i2330x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.curse_damage()",),
)
def i2330x1(c: Cast) -> None:
    """The curse's dice are paid inside the warlock's feature and nothing
    adds one to them."""


@power(
    "i2330p1",
    level=7,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
    dropped=("c.deals(once=)",),
)
def i2330p1(c: Cast) -> None:
    """"The next power" is one use; `c.deals` holds until something ends it,
    so this runs to the end of the fight instead."""
    c.deals(DamageType.RADIANT, on=c.me, until=When.ENCOUNTER)


@power(
    "i2586x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2586x1(c: Cast) -> None:
    """The save context carries the keywords of the row that laid the hold
    -- `durations.keywords_of` off its label -- so "against charm effects
    and fear effects" is a gate rather than a bonus on every throw."""
    c.bonus(
        "save", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(
            {Keyword.CHARM, Keyword.FEAR} & set(ctx.get("keywords", ()))
        ),
    )


@power(
    "i2586p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2586p1(c: Cast) -> None:
    """Of the four rolls the card offers, this engine rolls two: a skill
    check and an ability check are not rolled at all, so the choice is
    between the attack roll and the save."""
    what = c.choose(["attack", "save"], "which roll") or "attack"
    c.bonus(
        what,
        c.enhancement,
        kind="item",
        on=c.me,
        until=When.SONT,
        once=what == "attack",
    )


@power(
    "i2598p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy within 3 squares with a force attack",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.FORCE)), "you hit with force"),
)
def i2598p1(c: Cast) -> None:
    """The augment is written as the pull it prints -- `anchor` is the
    square a shove is measured from, so a pull toward the target's square
    is "1 square toward it"."""
    foe = _struck(c)
    if foe is None or c.distance(to=foe) > 3:
        return
    if c.spend_points(1):
        here = _square(c, foe)
        for other in c.within(3, of=foe, side="enemy"):
            if other != foe and here is not None:
                c.pull(1, on=other, anchor=here)
    c.teleport(c.enhancement, who=foe)


@power(
    "i2600p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def i2600p1(c: Cast) -> None:
    """"The next enemy to make an attack roll against that ally" is a watch
    on the declaration rather than on the hit -- the damage is owed whether
    the swing lands or not -- and `once=True` is "the next"."""
    mate = _pick(c, 10)

    def burn(ev: AttackDeclared) -> None:
        if ev.target != mate:
            return
        c.flat(10, dtype=DamageType.RADIANT, on=ev.attacker)

    c.watch(AttackDeclared, burn, until=When.ENCOUNTER, once=True)


@power(
    "i2650x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonus(dtype=)",),
)
def i2650x1(c: Cast) -> None:
    """A rolled modifier is `dice=`, read afresh on every damage roll. The
    extra dice land as untyped: a modifier carries no damage type, so the
    poison half of "+1d6 poison damage" is dropped."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=_is_melee,
    )


@power(
    "i2650p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you deal poison damage with a power cast through this staff",
    on=Trigger(
        DamageApplied,
        both(by_me, lambda w, me, ev: ev.dtype is DamageType.POISON),
        "you deal poison damage",
    ),
)
def i2650p1(c: Cast) -> None:
    """"If the power already deals ongoing poison damage, add to it" is what
    `c.ongoing` does of its own accord: one type, highest wins, and a
    weaker burn is refused rather than stacked."""
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is not None:
        c.ongoing(c.enhancement, DamageType.POISON, on=foe)


@power(
    "i2716x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("query.is_summoned()",),
)
def i2716x1(c: Cast) -> None:
    """`c.summon` sets no relation, so "a creature you summoned" is read as
    the servants and companions the board does record."""

    def spared(ev: Miss) -> None:
        mine = _mine(c)
        if ev.target not in mine:
            return
        who = c.choose([c.me, *c.within(5, of=ev.target, side="ally")], "who is spared")
        c.temp_hp(5 + c.enhancement, on=who if who is not None else c.me)

    c.watch(Miss, spared, until=When.ENCOUNTER)


@power(
    "i2716p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger="an enemy hits a creature you summoned",
    on=Trigger(Hit, _hits_my_summon, "an enemy hits a creature you summoned"),
    dropped=("query.is_summoned()",),
)
def i2716p1(c: Cast) -> None:
    """"Must use the second result" is `keep="new"`, not `"worst"`."""
    c.reroll_attack(keep="new")


@power(
    "i2775x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.item_set()",),
)
def i2775x1(c: Cast) -> None:
    """The whole benefit is conditional on the set being complete, and
    nothing asks after a set."""


@power(
    "i2776p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
    dropped=("c.save(conditions=)",),
)
def i2776p1(c: Cast) -> None:
    """`c.save` picks an effect by label, not by the condition it carries,
    so the printed list of four conditions is not enforced and whichever
    save-ends effect is found first is the one rolled against."""
    who = _pick(c, 10)
    c.save(on=who, bonus=c.enhancement)


@power(
    "i2777x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.item_set()",),
)
def i2777x1(c: Cast) -> None:
    """The two increases are a race and a completed set, neither of which
    can be asked after, so every ally gets the base 5."""

    def ward(ev: Healed) -> None:
        if ev.source != c.me or not _my_side(c.world, c.me, ev.target):
            return
        pick = c.choose(list(_ELEMENTS), "which damage type")
        c.resist(5, pick or DamageType.FIRE, on=ev.target, until=When.EONT)

    c.watch(Healed, ward, until=When.ENCOUNTER)


@power(
    "i2784p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    trigger="you hit with an attack delivered by this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i2784p1(c: Cast) -> None:
    """"As if he had spent a healing surge" still spends one here: `c.surge`
    is the only thing that pays a surge's worth, and `bonus=` is the
    printed "add the symbol's enhancement bonus"."""
    down = [a for a in c.within(20, side="ally") if c.is_(Condition.DYING, on=a)]
    if down:
        c.surge(on=down[0], bonus=c.enhancement)


@power(
    "i2785x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.penalty(once=)",),
)
def i2785x1(c: Cast) -> None:
    """`once=` is spent by watching an attack roll, which a saving throw is
    not, so "the first saving throw" is written as a penalty that lasts as
    long as the effect does."""

    laying = False

    def worsen(ev: EffectApplied) -> None:
        # The penalty is itself save-ends, so without the latch it
        # answers its own `EffectApplied` and recurses until the stack
        # runs out. Invisible until the audit started arming an item's
        # Property beside its Power.
        nonlocal laying
        if laying or ev.source != c.me or not ev.save_ends:
            return
        laying = True
        try:
            c.penalty("save", 2, on=ev.target, until=When.SAVE_ENDS)
        finally:
            laying = False

    c.watch(EffectApplied, worsen, until=When.ENCOUNTER)


@power(
    "i2798p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="you use your second wind or spend a healing surge",
    on=Trigger(SurgeSpent, about_me, "you spend a healing surge"),
)
def i2798p1(c: Cast) -> None:
    """`SurgeSpent` is emitted from every place that decrements a surge, so
    the second wind and the power that spends one are the same trigger. It
    names its subject `actor`, which is `about_me` and not `by_me`."""
    mates = c.within(5, side="ally")
    if mates and c.may("spend a healing surge", who=mates[0]):
        c.surge(on=mates[0])


@power(
    "i2799p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(2),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i2799p1(c: Cast) -> None:
    who = _pick(c, 2)
    c.bonus(AC, 2, kind="power", on=who, until=When.EONT)
    c.bonus(REF, 2, kind="power", on=who, until=When.EONT)


@power(
    "i2805x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2805x1(c: Cast) -> None:
    """"At maximum hit points" is asked when the roll is made, not when the
    property is armed, so it is a gate rather than a branch."""
    c.bonus(
        "attack",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.missing(on=c.me) == 0,
    )


@power(
    "i2907p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    trigger="you hit an enemy with a primal attack power using this totem",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.PRIMAL)), "you hit with primal"),
)
def i2907p1(c: Cast) -> None:
    """A zone with teeth is `c.hazard`; "heavily obscured" is
    `blocks_sight`. The printed duration is a flat one, so it takes no
    sustain."""
    foe = _struck(c)
    here = _square(c, foe)
    if here is None:
        return
    c.hazard(
        spread({here}, 1),
        5 + c.enhancement,
        DamageType.FIRE,
        until=When.EONT,
        blocks_sight=True,
        sustain=None,
    )


@power(
    "i3087p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit an enemy with a primal implement power using this totem",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.PRIMAL)), "you hit with primal"),
)
def i3087p1(c: Cast) -> None:
    """The extra dice land; changing the attack's own damage type after the
    roll has been made is the half nothing can do."""
    foe = _struck(c)
    if foe is not None:
        c.damage("2d6", dtype=DamageType.NECROTIC, on=foe)


@power(
    "i3173p1",
    level=7,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.sustain_all()",),
)
def i3173p1(c: Cast) -> None:
    """`c.on_sustain` says what a sustain pays out; nothing reaches in and
    sustains a standing effect from outside, let alone all of them."""
    c.temp_hp(2 + c.enhancement, on=c.me)


@power(
    "i3186p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit a creature with an attack using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i3186p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.ongoing(5, DamageType.POISON, on=foe)


@power(
    "i3203x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3203x1(c: Cast) -> None:
    """Six branches, rolled fresh each time. `PowerUsed` announces before
    the body runs, which costs nothing here: the targets are chosen by
    then, and they are all this needs. Face 4 lays its difficult ground in
    the first target's square rather than the next one hit, since the
    attack this answers is the one in hand."""

    def wild(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None or p.usage is not Usage.DAILY or p.attack is None:
            return
        face = c.roll("1d6")
        if face == 1:
            c.mode("fly", 5, on=c.me, until=When.EONT)
        elif face == 2:
            c.conceal(on=c.me, until=When.EONT)
        elif face == 3:
            c.invisible(on=c.me, until=When.EONT)
        elif face == 4:
            where = _square(c, ev.targets[0]) if ev.targets else None
            if where is not None:
                c.zone([where], difficult=True, until=When.EONT)
        elif face == 5:
            for foe in ev.targets:
                c.slowed(on=foe, until=When.EONT)
        else:
            c.dazed(on=c.me, until=When.EONT)
            for foe in ev.targets:
                c.dazed(on=foe, until=When.EONT)

    c.watch(PowerUsed, wild, until=When.ENCOUNTER)


@power(
    "i3403x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("EffectApplied.ongoing",),
)
def i3403x1(c: Cast) -> None:
    """`EffectApplied` says whether a save can end the effect and not what
    the effect carries, so the penalty is paid on every save-ends effect of
    mine rather than only on the burning ones."""

    laying = False

    def worsen(ev: EffectApplied) -> None:
        # The penalty is itself save-ends, so without the latch it
        # answers its own `EffectApplied` and recurses until the stack
        # runs out.
        nonlocal laying
        if laying or ev.source != c.me or not ev.save_ends:
            return
        laying = True
        try:
            c.penalty("save", 2, on=ev.target, until=When.SAVE_ENDS)
        finally:
            laying = False

    c.watch(EffectApplied, worsen, until=When.ENCOUNTER)


@power(
    "i3403p1",
    level=7,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    trigger="you hit and damage an enemy with an attack using this rod",
    on=Trigger(DamageRolled, by_me, "you damage an enemy with this rod"),
    dropped=("c.ongoing(on_tick=)",),
)
def i3403p1(c: Cast) -> None:
    """Declared on the roll rather than on the hit: `c.reduce` takes a
    number off damage that has been rolled and not yet dealt, and by `Hit`
    there is nothing left to reduce. The free slide each time the burn
    ticks has no hook to hang from."""
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is None:
        return
    c.reduce(5, c.trigger)
    c.ongoing(5, DamageType.ACID, on=foe)


@power(
    "i3472x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3472x1(c: Cast) -> None:
    c.resist(10, DamageType.FIRE, on=c.me)
    c.resist(10, DamageType.LIGHTNING, on=c.me)


@power(
    "i3472p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(INT, vs=FORT),
    dropped=("Attack.best_of()",),
)
def i3472p1(c: Cast) -> None:
    """"Intelligence, Constitution, or Charisma" is one attack line with
    three abilities and the header holds one, so the arcane ability is the
    one written. The enhancement is a column and is added by the engine."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


@power(
    "i3472p2",
    level=7,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(INT, vs=REF),
    dropped=("Attack.best_of()",),
)
def i3472p2(c: Cast) -> None:
    """"Creatures in the blast" is everybody, allies included."""
    if c.strike():
        c.flat(5, dtype=DamageType.THUNDER)
        c.push(3)


# -- level 8 ----------------------------------------------------------------


@power(
    "i1063x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1063x1(c: Cast) -> None:
    c.bonus(
        "damage",
        2,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_has_keyword(Keyword.IMPLEMENT),
    )


@power(
    "i1122p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i1122p1(c: Cast) -> None:
    for mate in c.within(2, side="ally"):
        for d in _DEFENCES:
            c.bonus(d, 1, kind="power", on=mate, until=When.EONT)


@power(
    "i1237p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.reroll_attacks_against()",),
)
def i1237p1(c: Cast) -> None:
    """`c.reroll_attack` reads the roll off `c.trigger`, so it means
    something only inside a row the dispatcher offered. Storing a reroll to
    be spent later, out of any trigger, has nothing to hold it."""


@power(
    "i1263p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you bloody an enemy with a primal ranged attack using this totem",
    on=Trigger(
        DamageApplied,
        lambda w, me, ev: ev.source == me,
        "you damage an enemy",
    ),
)
def i1263p1(c: Cast) -> None:
    """`Bloodied` names no source, so "an enemy **you** bloody" is read off
    the damage: the hit points left and how many came off say whether this
    blow was the one that crossed the line."""
    if not _just_bloodied(c, c.trigger):
        return
    pet = c.companion()
    if pet is None:
        return
    near = [f for f in c.enemies() if c.adjacent_to(pet, f)]
    if near:
        c.damage(f"{c.enhancement}d6", on=near[0])


@power(
    "i1293x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1293x1(c: Cast) -> None:
    """The printed parenthesis -- "stacks with the weapon's enhancement" --
    is what an untyped bonus does, so the absence of a type word is doing
    the work here rather than being an omission."""

    def arm(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        c.bonus(
            "damage",
            c.enhancement,
            on=c.me,
            until=When.EONT,
            when=lambda ctx: _is_melee(ctx)
            and Keyword.WEAPON in _keywords_of(ctx.get("power")),
        )

    c.watch(Hit, arm, until=When.ENCOUNTER)


@power(
    "i1461x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.modify_power()",),
)
def i1461x1(c: Cast) -> None:
    """Swapping one condition for another inside another row's zone would
    need a hold on that row's body, and nothing edits a power."""


@power(
    "i1461p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.expend()",),
)
def i1461p1(c: Cast) -> None:
    """The spec prints the ref, so the loan is real; the daily it is bought
    with has nothing to charge it to."""
    c.grant_row("p259", until=When.ENCOUNTER)


@power(
    "i1531p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=FORT),
    trigger="an ally within 10 squares of you that you can see is hit",
    on=Trigger(Hit, _ally_hit_within(10), "an ally within 10 squares is hit"),
    dropped=("c.area_origin()",),
)
def i1531p1(c: Cast) -> None:
    """The burst is printed as centred on the ally who was hit; nothing
    moves a declared area's origin, so the engine aims it and only the
    push is measured from the ally."""
    mate = getattr(c.trigger, "target", None)
    here = _square(c, mate)
    if c.strike():
        c.push(c.enhancement, anchor=here)


@power(
    "i1577x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.rolled_maximum()",),
)
def i1577x1(c: Cast) -> None:
    """"Whenever you deal maximum damage" needs the dice that were rolled
    compared against their ceiling, and `DamageApplied` carries the total
    only."""


@power(
    "i1649p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1649p1(c: Cast) -> None:
    """"While adjacent to your spirit companion" is an aura on the
    companion, which is what `c.aura(on=)` is for -- it hangs on anything
    with a position. A plain "+2 bonus": untyped."""
    pet = c.companion()
    if pet is None:
        return
    ring = c.aura(1, on=pet, until=When.EONT)
    for d in _DEFENCES:
        c.grants_in(ring, d, 2, side="ally", kind="untyped")


@power(
    "i1811p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an aberrant creature with an attack using this symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i1811p1(c: Cast) -> None:
    """Both halves read the same word off the creature's type set: the
    trigger checks the one just hit, the bonus checks whoever is being
    swung at next."""
    foe = _struck(c)
    if foe is None or "aberrant" not in c.kinds_of(on=foe):
        return
    c.bonus(
        "attack",
        1,
        kind="power",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and "aberrant" in c.kinds_of(on=ctx["target"]),
    )


@power(
    "i1878p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i1878p1(c: Cast) -> None:
    """"The first attack roll it makes" is `once=True`; the window closes at
    the start of your next turn whether it swung or not."""
    foe = _struck(c)
    if foe is not None:
        c.penalty("attack", 5, on=foe, until=When.SONT, once=True)


@power(
    "i1887p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i1887p1(c: Cast) -> None:
    mates = c.within(5, side="ally")
    if mates:
        c.resist(5, on=mates[0], until=When.SONT)


@power(
    "i1941p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="an attack with this orb hits the target's Will defence",
    on=Trigger(Hit, by_me, "you hit with this orb"),
    dropped=("Hit.vs",),
)
def i1941p1(c: Cast) -> None:
    """`Hit` carries attacker, target, power and critical -- not the defence
    that was attacked, which only `AttackRolled` knows."""
    foe = _struck(c)
    if foe is None:
        return
    for d in _DEFENCES:
        c.penalty(d, 2, on=foe, until=When.SAVE_ENDS)


@power(
    "i1942x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.class_feature()",),
)
def i1942x1(c: Cast) -> None:
    """Arcane defiling is a class feature rather than a row, and nothing
    announces a use of one."""


@power(
    "i1942p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    todo=("c.class_feature()",),
)
def i1942p1(c: Cast) -> None:
    """The trigger is a use of arcane defiling, which nothing announces, so
    the row cannot be declared at all."""


@power(
    "i1959p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="an attack with this orb misses its target",
    on=Trigger(Miss, by_me, "you miss with this orb"),
)
def i1959p1(c: Cast) -> None:
    """"As if the attack had hit" is `c.as_though_hit_by`, given the ref of
    the power that missed."""
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is not None:
        c.as_though_hit_by(getattr(ev, "power", ""), on=foe)


@power(
    "i1961p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    trigger="you damage an enemy with an attack",
    on=Trigger(DamageApplied, by_me, "you damage an enemy"),
)
def i1961p1(c: Cast) -> None:
    """"One of its adjacent allies" is one of *my* enemies standing next to
    it -- the pronoun is the enemy's, not the caster's."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    mates = [f for f in c.enemies() if f != foe and c.adjacent_to(foe, f)]
    if mates:
        c.grant_attack(foe, on=mates[0], attack_bonus=c.enhancement)


@power(
    "i2310x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2310x1(c: Cast) -> None:
    """The damage context carries `target`, and the extra dice are read
    before this blow has come off, so "has maximum hit points" is still
    true of the creature about to lose some."""
    c.bonus(
        "damage",
        0,
        dice="1d8",
        on=c.me,
        until=When.ENCOUNTER,
        when=_whole_target(c),
    )


@power(
    "i2321x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2321x1(c: Cast) -> None:
    """Declared on the attack rather than on the hit: "when any creature
    attacks you" is owed whether the swing lands or not."""

    def mark(ev: AttackDeclared) -> None:
        if ev.target != c.me:
            return
        who = ev.attacker
        c.bonus(
            "attack",
            1,
            kind="item",
            on=c.me,
            until=When.EONT,
            when=lambda ctx: ctx.get("target") == who,
        )

    c.watch(AttackDeclared, mark, until=When.ENCOUNTER)


@power(
    "i2323x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.extend_effect()",),
)
def i2323x1(c: Cast) -> None:
    """A duration is fixed when the effect is laid and nothing lengthens a
    live one by a round."""


@power(
    "i2323p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=EACH_ALLY,
)
def i2323p1(c: Cast) -> None:
    """"You and each ally in the burst": the caster is not an ally of
    himself, so the once-per-power line adds him."""
    pick = c.choose(list(_ELEMENTS), "which damage type") or DamageType.FIRE
    c.resist(5 + c.con_mod, pick, on=c.target, until=When.EONT)
    if c.first:
        c.resist(5 + c.con_mod, pick, on=c.me, until=When.EONT)


@power(
    "i2340x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.pact_boon()",),
)
def i2340x1(c: Cast) -> None:
    """A pact boon is a class feature rather than a row, and nothing
    announces one triggering."""


@power(
    "i2340p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def i2340p1(c: Cast) -> None:
    c.teleport(3 + c.enhancement)


@power(
    "i2343p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.pact_boon()",),
)
def i2343p1(c: Cast) -> None:
    """Nothing announces a pact boon, so the trigger cannot be declared."""


@power(
    "i2343p2",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.pact_boon()",),
)
def i2343p2(c: Cast) -> None:
    """The trigger and the thing it adds to are both the pact boon."""


@power(
    "i2344x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.pact_boon()",),
)
def i2344x1(c: Cast) -> None:
    """Nothing announces a pact boon, so there is no temporary hit point
    total to add to."""


@power(
    "i2344p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2344p1(c: Cast) -> None:
    c.temp_hp(c.level + c.int_mod, on=c.me)


@power(
    "i2468x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2468x1(c: Cast) -> None:
    """Food and drink, and the second sentence says the rest changes
    nothing."""


@power(
    "i2468p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger="you or an ally is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_near, "an effect a save can end lands"),
)
def i2468p1(c: Cast) -> None:
    """`EffectApplied` fires for every hold, `save_ends` and all --
    `ConditionApplied` would miss the ones carrying only ongoing damage,
    which is half of what this answers."""
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.save(on=who, bonus=c.enhancement)


@power(
    "i2618p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    trigger="you hit an enemy with an attack power using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i2618p1(c: Cast) -> None:
    """"One creature of your choice" -- the caster is in the pool, and the
    same modifier is printed on both rolls."""
    foe = _struck(c)
    if foe is None:
        return
    who = _pick(c, 10)
    c.grant_attack(
        who, on=foe, attack_bonus=c.int_mod, damage_bonus=c.int_mod
    )


@power(
    "i2640p1",
    level=8,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an implement power using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
    dropped=("query.is_summoned()", "c.grant_action(trigger=)"),
)
def i2640p1(c: Cast) -> None:
    """Two narrowings go: `c.summon` records no relation, so the pool is
    the servants and companions the board holds, and `c.grant_action`
    carries a cost but not a condition, so the shift is not gated on being
    hit."""
    for mine in _mine(c):
        c.grant_action("shift", INTERRUPT, squares_=2, on=mine, until=When.EONT)


@power(
    "i2643p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def i2643p1(c: Cast) -> None:
    """The spec prints the ref, so the row is lent for one use and given
    straight back rather than marked."""
    _as_row(c, "p1455")


@power(
    "i2665x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2665x1(c: Cast) -> None:
    """The class half is not enforced: the item was dealt to whoever holds
    it."""
    c.as_implement(on=c.me)


@power(
    "i2665p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
    dropped=("Keyword.CHANNEL_DIVINITY",),
)
def i2665p1(c: Cast) -> None:
    """The spec prints the ref for the first half of the choice; Channel
    Divinity is a class feature with no ref and no keyword, so the second
    half has nothing to hand a use back to."""
    c.restore_use("p1455", on=c.me)


@power(
    "i2676p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an attack roll using this holy symbol",
    on=Trigger(AttackRolled, by_me, "you make an attack roll"),
)
def i2676p1(c: Cast) -> None:
    """"Use the new result" is `keep="new"`, which is the default: the
    second face stands whether it is better or worse."""
    c.reroll_attack()


@power(
    "i2719p1",
    level=8,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
    dropped=("c.deals(revert=)",),
)
def i2719p1(c: Cast) -> None:
    """The way back -- "another free action returns the damage to normal" --
    has nothing to call, so this runs to the end of the fight."""
    c.deals(DamageType.RADIANT, on=c.me, until=When.ENCOUNTER)


@power(
    "i2806x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("spec.power_ref()",),
)
def i2806x1(c: Cast) -> None:
    """The challenge half lands.

    Divine challenge is `p805`, a declared row, and the bite it takes when
    the marked creature attacks somebody else goes through `c.flat`, which
    stamps the casting row's ref onto the blow -- so `DamageApplied.detail`
    is where the victim, the radiant damage and the row that dealt it
    arrive together. Read off `detail` rather than off `Hit`, because the
    mark's damage is not an attack and produces no `Hit` at all.

    No loop: the extra helping is dealt by this row and carries this row's
    ref, not `p805`'s.

    **Divine sanction is dropped.** It is the same arrangement, laid by
    `powers/paladin/marks.burning_mark` on behalf of two dozen different
    rows, and each of those stamps its own ref onto the blow. The card
    names the sanction and no ref, and the set of rows that lay one is
    recorded nowhere, so there is no `detail` to test against."""
    me, plus = c.me, c.enhancement

    def bitten(ev: DamageApplied) -> None:
        if ev.source != me or ev.dtype is not DamageType.RADIANT:
            return
        if getattr(ev, "detail", "") != "p805" or plus <= 0:
            return
        c.flat(plus, dtype=DamageType.RADIANT, on=ev.target)

    c.watch(DamageApplied, bitten, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "i2806p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i2806p1(c: Cast) -> None:
    """"Cannot attack anyone but you" is written the way the engine can say
    it: barred from each ally in turn, which leaves the caster as the only
    creature on this side it may swing at."""
    foe = next((f for f in c.enemies() if c.marked(on=f)), None)
    if foe is None:
        return
    for mate in c.allies():
        if mate != c.me:
            c.cannot_attack(on=foe, against=mate, until=When.EONT)


@power(
    "i2812x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2812x1(c: Cast) -> None:
    """The class half is not enforced: the item was dealt to whoever holds
    it."""
    c.as_implement(on=c.me)


@power(
    "i2812p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you score a critical hit with an attack using this holy symbol",
    on=Trigger(
        Hit,
        lambda w, me, ev: ev.attacker == me and ev.critical,
        "you score a critical hit",
    ),
    dropped=("c.bonus(dtype=)",),
)
def i2812p1(c: Cast) -> None:
    """The critical's own payout is a column; this row is only the clause
    that makes it last the fight. A modifier carries no damage type, so
    "the bonus damage is fire and radiant" is dropped."""
    for mate in c.within(5, side="ally"):
        c.bonus("damage", c.enhancement, on=mate, until=When.ENCOUNTER)


@power(
    "i2884p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.THUNDER],
    trigger="you would push one or more creatures with one of your powers",
    on=Trigger(ForcedMove, _my_push, "you would push a creature"),
)
def i2884p1(c: Cast) -> None:
    """`ForcedMove` is announced before the shove happens and is
    cancellable, which is what "instead of pushing" needs: the squares it
    was going to cover are the dice."""
    ev = c.trigger
    squares = getattr(ev, "squares", 0)
    foe = getattr(ev, "target", None)
    if foe is None or squares <= 0:
        return
    c.cancel()
    c.prone(on=foe)
    c.damage(f"{squares}d6", dtype=DamageType.THUNDER, on=foe)


@power(
    "i2921x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2921x1(c: Cast) -> None:
    """"Until the end of his or her next turn" is the ally's turn, not the
    caster's. A plain "+1 bonus": untyped."""

    def quicken(ev: Healed) -> None:
        if ev.source != c.me or ev.target == c.me:
            return
        if not _my_side(c.world, c.me, ev.target):
            return
        c.bonus("speed", 1, on=ev.target, until=When.EOTNT)

    c.watch(Healed, quicken, until=When.ENCOUNTER)


@power(
    "i2921p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with a primal attack power using this totem",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.PRIMAL)), "you hit with primal"),
)
def i2921p1(c: Cast) -> None:
    mates = [a for a in c.within(10, side="ally") if c.can_see(to=a)]
    if mates:
        c.bonus("speed", 1, kind="power", on=mates[0], until=When.ENCOUNTER)
