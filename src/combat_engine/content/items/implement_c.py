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
approximated: `c.class_feature()`, `c.reshape_area()`, `c.tome_powers()`
and `c.item_set()`.

Three of the old recurring gaps closed once the specs gained refs and the
engine was read rather than its prose:

* **A pact boon is announceable.** `cf:warlock-f1` pays each leg off a
  `Dropped` whose subject this caster had cursed, and `c.build` says which
  leg. So "when your <pact> boon triggers" is that event plus those two
  questions, and only the star leg -- which `cf:warlock-f1` pays nothing
  for -- is still out of reach.
* **Warlock's Curse damage carries its label.** `features.strikers.
  extra_damage` stamps `detail="cf:warlock-f4"` on the blow, so
  `DamageApplied.detail` is where "when you deal your curse damage"
  is asked. The die size is the feature's own 1d6 at heroic and is
  written as that number, since nothing publishes it.
* **`c.expend_row` is the price half** of "expend an unused power of level
  N or higher"; the set it is chosen from is read off `Powers.all`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.paladin.marks import SANCTIONS
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


def _hit_defence(ev: Any):  # noqa: ANN202
    """Which defence the attack behind a `Hit` was aimed at.

    `Hit` carries attacker, target, power and critical and not the defence
    -- only `AttackRolled` does -- but the defence is header data: the row
    that swung declares it. So "an attack that succeeds against Will" is
    read off the power rather than off the event, which is why neither
    block here carries a marker for `Hit.vs`.
    """
    p = get(getattr(ev, "power", "") or "")
    line = p.attack_of(0) if p is not None else None
    return line.vs if line is not None else None


def _spend_unused(
    c: Cast,
    *,
    cls: str,
    level: int,
    attacks: bool,
    usage: Usage | None = None,
) -> bool:
    """"Expend an unused wizard daily attack power of level 5 or higher."

    `c.expend_row` is the spend and refuses a row that is not owned, is an
    at-will or is already gone -- but it takes a ref and the card names a
    *set*, so the set is read off what the character actually carries. A
    card that names no usage leaves `usage` off: an at-will is refused by
    `c.expend_row` anyway, having nothing to count down.

    Returns False when there is nothing to charge, which is the printed
    Requirement.
    """
    from combat_engine.engine.components import Powers

    known = c.world.get(c.me, Powers)
    if known is None:
        return False
    for ref in sorted(known.all):
        p = get(ref)
        if p is None or p.cls != cls or p.level < level:
            continue
        if usage is not None and p.usage is not usage:
            continue
        if (p.attack is not None) is not attacks:
            continue
        if c.expend_row(ref):
            return True
    return False


def _boon_drop(leg: str):  # noqa: ANN202
    """"When your <pact> boon triggers" -- the event and the two questions.

    `cf:warlock-f1` pays every leg off a `Dropped` it reads the curse from,
    so the boon's moment is that drop: an enemy, cursed by this caster,
    with this leg taken. `Dropped` is announced before the corpse is
    cleared, so the curse is still readable, and `query.enemies` filters
    out the dead -- so the side is compared directly, as the feature does.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        from combat_engine.engine.components import Build

        who = getattr(ev, "actor", None)
        if who is None or who == me or _my_side(world, me, who):
            return False
        if not world.relations.holds(Relation.CURSED_BY, me, who):
            return False
        held = world.get(me, Build)
        return held is not None and leg in held.choices

    return check


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
    dropped=("c.tome_powers()",),
)
def i744x1(c: Cast) -> None:
    """The first half plays: a wizard fire power used through this tome
    reduces the target's fire resistance by 10, which from the
    attacker's side is ten points walked through. Heroic, so 10.

    The second is dropped -- a tome's two stored powers are not a thing
    the engine holds."""

    def wizard_fire(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return (
            p is not None and p.cls == "wizard" and Keyword.FIRE in p.keywords
        )

    c.ignore_resistance(
        10, DamageType.FIRE, on=c.me, until=When.ENCOUNTER, when=wizard_fire
    )


@power(
    "i744p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    todo=("c.tome_powers()",),
)
def i744p1(c: Cast) -> None:
    """Re-aimed to one gap. The price half is sayable now -- `c.expend_row`
    spends a use without running the row, and `i1098p1` beside this writes
    it -- but there is nothing to buy: the chosen power is one of the two
    the tome stores, and nothing holds a tome's contents. The row can
    never run, so the price is not written either."""


@power(
    "i859x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("cf:sorcerer-f0s3",),
)
def i859x1(c: Cast) -> None:
    """The bonus and the vulnerability are one bargain, so the second is
    armed off the hit that pays the first.

    **One of the two exemptions plays now.** Having a class feature is
    knowing its row, which is what `c.feat` reads off `Powers.all`, and
    `cf:warlock-f1s5` is declared -- so a character with that feature is
    let off the vulnerability, which is the printed line.

    Dropped, and re-aimed a second time: the other exemption names
    `cf:sorcerer-f0s3`, and no row in the tree declares it. The spec prints
    the ref now, so `spec.feature_ref()` is no longer what is missing --
    the marker names the undeclared ref itself, which is."""
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
        if c.feat("cf:warlock-f1s5", on=c.me):
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
    target=NO_TARGET,
    trigger="you deal your cf:warlock-f4 damage",
    on=Trigger(
        DamageApplied,
        lambda w, me, ev: ev.source == me
        and getattr(ev, "detail", "") == "cf:warlock-f4",
        "you deal your curse damage",
    ),
)
def i1852p1(c: Cast) -> None:
    """`features.strikers.extra_damage` stamps `detail="cf:warlock-f4"` on
    the blow, so the curse payout announces itself after all and both
    halves of the line can be said.

    "Two dice" is two of the feature's own, which is 1d6 at heroic and is
    written as that number -- nothing publishes the die. Ending the curse
    is the price and takes the relation with it, so the target may be
    cursed again normally, which is the printed proviso. The pact boon
    needs nothing: `cf:warlock-f1` reads the curse off the `Dropped`, and
    that is announced before this row's damage has removed it."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.damage("2d6", on=foe)
    c.end_effect(on=foe, against="curse", why="the bargain is called in")


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
    todo=("c.worsen_save()",),
)
def i1968p1(c: Cast) -> None:
    """Re-aimed to one gap. `Hit.vs` is not missing after all: the defence
    an attack was aimed at is header data on the row that swung, which
    `_hit_defence` reads, so "succeeds against Will" is sayable.

    What is left is the whole Effect -- nothing makes a saving throw roll
    twice and keep the lower. `c.reroll_save(keep="worst")` is the same
    arithmetic but only inside a row the dispatcher offered for that one
    throw, and this stands over every save against the effects of one
    attack. A save penalty is a different number and would not be this
    line."""


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
)
def i1098p1(c: Cast) -> None:
    """The price is real now: `c.expend_row` spends a use without running
    the row, which is exactly what "expend an unused power" charges, and
    the set it is picked from is read off what the character owns. Its
    False is the printed Requirement, so the loan is refused when there is
    nothing to pay with."""
    if _spend_unused(c, cls="wizard", level=6, attacks=False):
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
)
def i2330x1(c: Cast) -> None:
    """The curse payout announces itself: `features.strikers.extra_damage`
    stamps `detail="cf:warlock-f4"` on the blow, so "an extra die of that
    damage" is a watch on it rather than a reach into the feature.

    The die is the feature's own 1d6 at heroic, written as that number
    because nothing publishes it. The extra helping carries this row's ref
    and not the feature's, so it does not answer its own watch."""
    me = c.me

    def again(ev: DamageApplied) -> None:
        if ev.source != me or getattr(ev, "detail", "") != "cf:warlock-f4":
            return
        if "undead" not in c.kinds_of(on=ev.target):
            return
        c.damage("1d6", on=ev.target)

    c.watch(DamageApplied, again, until=When.ENCOUNTER, on=me, label=c.ref)


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
    """`c.deals(implement=True)` is the conversion: it beats the type the
    power printed and speaks for `Keyword.IMPLEMENT` rows, which is both
    halves of what this line needs.

    What is left is the scope. Nothing spends the override on one use, so
    it is held to the end of the turn rather than to "the next power"."""
    c.deals(DamageType.RADIANT, on=c.me, until=When.EOT, implement=True)


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
)
def i2650x1(c: Cast) -> None:
    """A rolled modifier is `dice=`, read afresh on every damage roll, and
    the poison half of "+1d6 poison damage" is the `dtype`: those dice
    meet a poison resistance the staff's own damage does not."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        dtype=DamageType.POISON,
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
)
def i2776p1(c: Cast) -> None:
    """`c.save` picks by label fragment and not by the condition an effect
    carries, but `Effect.conditions` is readable -- `c.end_effect(carrying=)`
    reads it -- so the printed list of four is enforced by finding the
    hold first.

    Rolled against that hold rather than handed back to `c.save(against=)`,
    because a label is the ref of the row that laid the effect and one row
    routinely lays two: a slow and a weaken off one hit share the label
    `p...`, and the fragment would find whichever came first. The caster is
    in the pool, and the bonus is the symbol's own."""
    who = _pick(c, 10)
    wanted = {
        Condition.DOMINATED,
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        Condition.SLOWED,
    }
    held = next(
        (
            eff
            for eff in sorted(c.world.effects.of(who), key=lambda e: e.id)
            if not eff.ended
            and eff.when is When.SAVE_ENDS
            and wanted & set(eff.conditions)
        ),
        None,
    )
    if held is not None:
        held.save_mod += c.enhancement
        c.world.effects.save(held)


@power(
    "i2777x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.item_set()", "chargen.race_choice()"),
)
def i2777x1(c: Cast) -> None:
    """The two increases are a race and a completed set. Neither can be
    asked after -- nothing on `Cast` or `query` reads a character's race,
    and `c.kinds_of` answers off a stat block's type line, which a
    character has not got -- so every ally gets the base 5. Re-aimed: the
    race half was not named before and is a gap of its own."""

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
)
def i2785x1(c: Cast) -> None:
    """The old note here was stale and cost the row its second half.
    `c.bonus(once=)` has a `"save"` branch that spends the modifier on
    `SavingThrow`, so "the **first** saving throw" is `once=True` after
    all.

    And it is the first save against *that* effect, not against anything:
    the save context carries the label of the hold being shaken off, so
    the gate names the one this row answered."""

    laying = False

    def worsen(ev: EffectApplied) -> None:
        # The penalty is itself save-ends, so without the latch it
        # answers its own `EffectApplied` and recurses until the stack
        # runs out. Invisible until the audit started arming an item's
        # Property beside its Power.
        nonlocal laying
        if laying or ev.source != c.me or not ev.save_ends:
            return
        label = ev.label
        laying = True
        try:
            c.penalty(
                "save",
                2,
                on=ev.target,
                until=When.SAVE_ENDS,
                once=True,
                when=lambda ctx: ctx.get("label") == label,
            )
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
)
def i3403x1(c: Cast) -> None:
    """`EffectApplied` names no field for the burn, but it carries the
    **label**, and `c.ongoing` stamps one that begins `"ongoing "`. So
    "an attack that deals ongoing damage" is read there, and `.ongoing`
    was not the gap.

    The other half is the save side: the saving-throw context carries
    `ongoing`, so the penalty is paid only on throws to end a burn and
    not on every throw the creature makes. No latch is needed now -- the
    penalty's own label is this row's ref, so it cannot answer itself."""
    me = c.me

    def worsen(ev: EffectApplied) -> None:
        if ev.source != me or not ev.label.startswith("ongoing "):
            return
        c.penalty(
            "save",
            2,
            on=ev.target,
            until=When.SAVE_ENDS,
            when=lambda ctx: bool(ctx.get("ongoing")),
        )

    c.watch(EffectApplied, worsen, until=When.ENCOUNTER, on=me, label=c.ref)


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
    todo=("c.reroll_attack(ev=)",),
)
def i1237p1(c: Cast) -> None:
    """Re-aimed to the exact gap. `c.reroll_attack` reads the roll off
    `c.trigger` and nothing else, so it means something only inside a row
    the dispatcher offered for that one roll. This card stores a reroll
    and spends it later, from a `c.watch` on somebody else's attack, where
    `c.trigger` is not the roll in hand -- and rerolling by hand off
    `AttackRolled.result` would be the engine's arithmetic copied into a
    content file."""


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
)
def i1461p1(c: Cast) -> None:
    """As `i1098p1`: `c.expend_row` is the price and its False is the
    printed Requirement, so the loan is refused when the character has no
    unused daily attack power of the printed level to burn."""
    if _spend_unused(c, cls="wizard", usage=Usage.DAILY, level=5, attacks=True):
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
    on=Trigger(
        Hit,
        lambda w, me, ev: ev.attacker == me and _hit_defence(ev) is WILL,
        "you hit a creature's Will defence",
    ),
)
def i1941p1(c: Cast) -> None:
    """`Hit` carries no defence, but it does not have to: the defence an
    attack is aimed at is declared in the header of the row that swung, so
    `_hit_defence` reads it off the power. `Hit.vs` was not the gap."""
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
)
def i2340x1(c: Cast) -> None:
    """The boon does announce itself after all. `cf:warlock-f1` pays every
    leg off a `Dropped` whose subject this caster had cursed, so the
    boon's moment is that event plus `c.cursed` plus `c.build` -- which is
    what `_boon_drop` asks.

    Two teleports rather than one lengthened, because nothing reaches into
    a distance already travelled; the squares come to the same total and
    the caster ends up where the card puts him."""
    me = c.me

    def further(ev: Dropped) -> None:
        if not _boon_drop("fey")(c.world, me, ev):
            return
        c.teleport(c.enhancement, who=me)

    c.watch(Dropped, further, until=When.ENCOUNTER, on=me, label=c.ref)


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
    target=NO_TARGET,
    trigger="your star pact boon triggers",
    on=Trigger(Dropped, _boon_drop("star"), "an enemy you cursed drops"),
)
def i2343p1(c: Cast) -> None:
    """The trigger is the drop `cf:warlock-f1` pays its boons off, asked of
    the star leg. `cf:warlock-f1` pays nothing for that leg, but the
    moment is the same moment whether the boon has a body or not, so the
    trigger is real.

    "Any one d20 roll" is the two this engine rolls -- an attack and a
    save -- each spent by its own first roll. A skill check takes no
    modifier and is not offered in a fight."""
    for mate in c.within(c.enhancement, side="ally"):
        c.bonus("attack", 1, on=mate, until=When.EONT, once=True)
        c.bonus("save", 1, on=mate, until=When.EONT, once=True)


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
    """Re-read and still blocked, for the second half rather than the
    first. The trigger is sayable now -- `i2343p1` above declares it off
    the same `Dropped` -- but the Effect adds a number to the bonus the
    star pact gives, and `cf:warlock-f1` pays that leg nothing. There is
    no bonus to add to."""


@power(
    "i2344x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2344x1(c: Cast) -> None:
    """The same drop `cf:warlock-f1` pays the infernal leg off, and the
    addition is written as the whole total rather than as an increment:
    temporary hit points do not stack, the larger pool wins, so laying
    `level + enhancement` beside the feature's `level` is exactly "add the
    enhancement bonus to the number gained" however the two are ordered."""
    me = c.me

    def richer(ev: Dropped) -> None:
        if not _boon_drop("infernal")(c.world, me, ev):
            return
        c.temp_hp(c.level + c.enhancement, on=me)

    c.watch(Dropped, richer, until=When.ENCOUNTER, on=me, label=c.ref)


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
)
def i2665p1(c: Cast) -> None:
    """Channel Divinity is not a keyword, it is an allowance: every
    channelled row declares `group=CHANNEL_DIVINITY` and `dsl._group_spent`
    is what enforces the one-per-fight. So "an additional use of the class
    feature" is a use handed back to whichever row of that group has been
    spent, which `c.expended(group=)` and `c.restore_use` say between
    them.

    The printed choice is made on the board rather than here, and the
    class feature's own ref is not restorable -- `cf:avenger-f2` and its
    three siblings are inert rows that lay nothing."""
    from combat_engine.content.features import CHANNEL_DIVINITY

    spent = c.expended()
    pool = [r for r in spent if r == "p1455" or r in c.expended(group=CHANNEL_DIVINITY)]
    if not pool:
        return
    c.restore_use(c.choose(pool, "which use comes back") or pool[0], on=c.me)


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
)
def i2719p1(c: Cast) -> None:
    """The way back is `c.endable`: it hangs a deliberate drop on the
    effect, `actions.legal` offers it to whoever holds it, and a free
    action is what the card charges. So `c.deals(revert=)` was not the
    gap.

    `implement=True` is the reach of the conversion: it overrides the type
    the power printed, on the `Keyword.IMPLEMENT` rows this symbol casts."""
    c.endable(
        c.deals(
            DamageType.RADIANT, on=c.me, until=When.ENCOUNTER, implement=True
        ),
        FREE,
    )


@power(
    "i2806x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2806x1(c: Cast) -> None:
    """Both halves land now.

    Divine challenge is `p805`, a declared row, and the bite it takes when
    the marked creature attacks somebody else goes through `c.flat`, which
    stamps the casting row's ref onto the blow -- so `DamageApplied.detail`
    is where the victim, the radiant damage and the row that dealt it
    arrive together. Read off `detail` rather than off `Hit`, because the
    mark's damage is not an attack and produces no `Hit` at all.

    No loop: the extra helping is dealt by this row and carries this row's
    ref, not `p805`'s.

    **Divine sanction used to be dropped** because "the set of rows that lay
    one is recorded nowhere, so there is no `detail` to test against". It is
    recorded now: `marks.SANCTIONS` collects the ref of every row that lays a
    sanction, as it lays it, and the bite is dealt by that same row -- so the
    ref is always in the set by the time its damage is seen.

    The card names the sanction and gives no ref, which is why this was marked
    `spec.power_ref()`. That was the wrong gap: a mechanic rather than a row,
    and the Glossary says so."""
    me, plus = c.me, c.enhancement

    def bitten(ev: DamageApplied) -> None:
        if ev.source != me or ev.dtype is not DamageType.RADIANT:
            return
        detail = getattr(ev, "detail", "")
        if plus <= 0 or (detail != "p805" and detail not in SANCTIONS):
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
)
def i2812p1(c: Cast) -> None:
    """The critical's own payout is a column; this row is only the clause
    that makes it last the fight. "The bonus damage is fire and radiant"
    is one rider of two types rather than two riders, which is what a
    sequence of types means: it is shrugged off only by a creature that
    resists both."""
    for mate in c.within(5, side="ally"):
        c.bonus("damage", c.enhancement, on=mate, until=When.ENCOUNTER,
                dtype=(DamageType.FIRE, DamageType.RADIANT))


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
