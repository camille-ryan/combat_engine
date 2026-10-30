"""Implement-slot magic items, heroic tier, second wave: levels 3 to 5.

Nothing here declares an implement. The ladder, the enhancement bonus, the
price, the critical rider and the base-item restriction are columns in
`game.db` and are laid on by `engine/equipment.py`; what is written here is
only the part that needs a body.

Three judgements run through the whole file.

* **"Using this implement" cannot be gated.** The damage context carries
  `target`, `power`, `opportunity`, `charge`, `dtype` and `crit` -- not the
  weapon -- so every property phrased that way is armed always-on, on the
  ground that the carrier is holding the item for as long as the property
  is. The resist context is the one exception: it carries `source`, which
  is what "resistance to that creature's attacks" needs.
* **The class half of a line is not enforced.** "An artificer attack
  power", "a wizard lightning power" -- the item was dealt to whoever is
  holding it, and the same reading the weapon wave took.
* **The riders that hang on a named power are writable now.** The specs
  used to print the compendium name and no ref, so nine blocks carried
  `by_ref()`; the ETL fixes put the refs back, and `_on_hit_with` is the
  shape they all wanted -- watch `Hit`, compare `ev.power`. Only `i3525x1`
  still names its power in prose. Where the whole block is "as the
  <class>'s <power>", `c.use_power(ref, spend=False)` is it, and
  `c.grant_attack(c.me, ref=...)` where the row is a swing.

Recurring gaps, each marked with the symbol it wants rather than
approximated: `c.pact_boon()`, `c.regain_points()` and
`c.store_points()`. "Ongoing 5 fire and radiant damage" is one number of
two types and not two numbers, and `c.ongoing(dtypes=)` is it.

**Four of those markers were stale and are gone.** The monk's attack
flurry is `FLURRIES` -- five declared rows, one per tradition -- and
`c.flurry_of_blows()` names whichever one a carrier holds, so the blocks
that named `cf:monk-f0c0`..`c4` are written. `c.fell_might()` was
likewise never a gap: the boon is a row with `usage=ENCOUNTER`, so
`c.expend_row` spends its charge. `c.tome_powers()` named a store that
turns out to have no business in a round -- `_tome_trade` is what a fight
reaches the tome's dailies through. And `c.curse_damage()` named two
numbers that `features/strikers.py` publishes by label: the flat bonus is
`c.total(f"{CURSE} damage")` and the die is `c.dice_for(CURSE, ...)`.

A row's **range** is reachable too, which three markers denied:
`dsl.area_of` hands `dsl._stretched` a context naming the row, so a gated
`c.bonus("range", ...)` lengthens exactly the rows a card names. An area
burst's `within` is the one part of that still missing.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.paladin import _shaken_off
from combat_engine.content.features.warlock import FELL
from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.content.powers.monk.level_0 import FLURRIES
from combat_engine.engine import (
    AC,
    AREA_OR_CLOSE,
    AT_WILL,
    CHA,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageType,
    Dropped,
    EffectApplied,
    Healed,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    MoveStart,
    Position,
    PowerUsed,
    Ranged,
    Relation,
    SavingThrow,
    SecondWind,
    Summoned,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    about_me,
    both,
    by_action_point,
    by_charge,
    by_keyword,
    by_me,
    by_melee,
    by_ranged,
    either,
    get,
    hits_me,
    power,
    spread,
)
from combat_engine.engine.components import Powers
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import charging

ITEM = "item"

#: The cf:warlock-f4 rider, labelled as `features/strikers.py` labels it.
#: Both halves of it are reachable by that name: the flat bonus it pays is
#: `c.total(f"{CURSE} damage")` and the die it rolls is
#: `c.dice_for(CURSE, ...)`, which is the read half `c.change_dice` needs.
CURSE = "cf:warlock-f4"


def _one_more_die(dice: str) -> str:
    """"An extra die of it" -- one more of whatever is being rolled.

    Read back rather than assumed, so a feat that has already raised the
    die keeps its own face.
    """
    count, _, face = dice.partition("d")
    return f"{int(count or 1) + 1}d{face}" if face.isdigit() else dice

def _from_a_flurry(ev: Any) -> bool:
    """Was this damage dealt by the carrier's own attack flurry?

    `DamageApplied` carries no `power` field at all -- `detail` is "what
    dealt it, a power ref where one did" -- so the gate reads that.
    """
    return getattr(ev, "detail", "") in FLURRIES


def _opportunity_hit_on_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits you with an opportunity attack."

    `Hit` does not declare `opportunity`; `resolve.attack` sets it as a
    plain attribute after the fact, so it is read with `getattr`.
    """
    return (getattr(ev, "target", None) == me
            and bool(getattr(ev, "opportunity", False)))


def _i_used_a_flurry(world: World, me: int, ev: Any) -> bool:
    """"You use your <class feature> power" -- whichever of the five it is."""
    return getattr(ev, "actor", None) == me and getattr(ev, "power", "") in FLURRIES


def _my_flurry_damaged(world: World, me: int, ev: Any) -> bool:
    """"You damage an enemy with your <class feature> power.\""""
    return getattr(ev, "source", None) == me and _from_a_flurry(ev)


def _struck(c: Cast) -> int | None:
    """The creature the triggering attack was aimed at.

    A row triggered by **your own** hit is aimed at `ev.attacker` -- you --
    by the auto-targeter, so it can pick a different enemy than the one
    just hit. Every "use this power when you hit" row reads the event.
    """
    foe = getattr(c.trigger, "target", None)
    return foe if foe is not None else c.target


def _square(c: Cast, who: int | None):  # noqa: ANN202
    pos = c.world.get(who, Position) if who is not None else None
    return pos.square if pos is not None else None


def _nonminion(c: Cast, who: int) -> bool:
    """A minion's card is one hit point and nothing else marks one."""
    h = c.world.get(who, Health)
    return h is None or h.max_hp > 1


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


def _tome_trade(
    c: Cast,
    cap: int,
    *words: Keyword,
    usage: Usage | None = None,
    attacks: bool | None = True,
) -> str:
    """A tome's whole printed sentence: take one of its cards, pay for one.

    > You choose a power contained in the tome and expend an unused wizard
    > attack power of an equal or higher level.

    `c.borrow_row` is the verb for "the card names a set and asks the
    character to take one of it", which is exactly what a tome's two
    chosen powers are. It matches the level **exactly** and the card says
    "equal to or lower than that of the tome", so the ladder is walked
    from the tome's rung down. Several `words` because one card names two
    keywords; `usage` and `attacks` narrow the **price** -- one of these
    cards asks for a *daily* power and takes an attack or a utility.

    **The two halves are one loop, and that is the whole point of this
    function.** Seven rows had them as two statements and each got the
    same three things wrong:

    * **The price was charged when there was nothing to lend.** `i2898p1`
      and `i2717p1` have an empty borrowable set in the tree today, so
      using either one burnt the item's daily *and* one of the
      character's attack powers for nothing. `i2717p1`'s own docstring
      flagged the risk and then argued *for* the order that causes it.
    * **The price was charged at the tome's rung.** The clause is "of an
      equal or higher level" -- higher than **the card actually taken** --
      and the ladder is walked downwards, so a level-9 tome lending a
      level-2 card demanded a level-9 price and refused uses the card
      allows. The floor has to be the rung, which means it can only be
      known inside the walk.
    * **Nothing stopped the loan paying for itself.** `c.borrow_row`
      *grants* the chosen card, which puts a fresh wizard power of exactly
      the right class and level into `Powers.all` -- so a price read after
      the borrow could pick the borrowed card and the trade would cost
      nothing. The candidates are read before `c.borrow_row` and the pick
      is made from that list.

    Returns the ref taken, or `""` -- which happens when no rung has both
    a card to lend and a price the bearer can pay, and that `""` **is**
    the printed Requirement.
    """
    for word in words:
        for lvl in range(cap, 0, -1):
            # Read before the borrow, so the borrowed card cannot be the
            # thing that pays for it.
            pool = c.unspent(cls="wizard", level=lvl, usage=usage, attacks=attacks)
            if not pool:
                continue
            taken = c.borrow_row(
                cls="wizard", level=lvl, usage=DAILY, keyword=word, uses=1
            )
            if not taken:
                continue
            pick = c.choose(pool, c.ref)
            if pick:
                c.expend_row(pick)
            return taken
    return ""


def _crit_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "critical", False)


def _vs_ac_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "vs", None) == AC


def _used_by_me(*refs: str):  # noqa: ANN202
    """"When you use <ref>", for one row or for any of a named few."""

    def check(world: World, me: int, ev: Any) -> bool:
        return getattr(ev, "actor", None) == me and getattr(ev, "power", "") in refs

    return check


#: The three cards `cf:artificer-f2` deals from. The feature itself is a
#: declared row and is never *used* -- it is the budget, `action=NONE` --
#: so "when you use that class feature" is a use of one of these.
#: `feats/artificer_b.py` keeps the same tuple for the same reason, and
#: says why a local copy beats a cross-file hook for one predicate.
_INFUSIONS = ("p4128", "p7635", "p10187")


def _resolved_by_me(*words: Keyword):  # noqa: ANN202
    """A use of mine that has **finished** -- "after resolving the attack"."""

    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "actor", None) != me:
            return False
        p = get(getattr(ev, "power", ""))
        return p is not None and bool(set(p.keywords) & set(words))

    return check


def _area_by_me(world: World, me: int, ev: Any) -> bool:
    """A close or an area attack of mine."""
    if getattr(ev, "attacker", getattr(ev, "actor", None)) != me:
        return False
    p = get(getattr(ev, "power", ""))
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in AREA_OR_CLOSE


def _area_at_me(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", ""))
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in AREA_OR_CLOSE


def _my_cursed_drop(world: World, me: int, ev: Any) -> bool:
    foe = getattr(ev, "actor", None)
    return foe is not None and world.relations.holds(Relation.CURSED_BY, me, foe)


def _my_teleport(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "kind_", "") == "teleport"


def _bloodied_req(world: World, eid: int) -> bool:
    h = world.get(eid, Health)
    return h is not None and h.hp <= h.max_hp // 2


def _keywords_of(ctx: dict[str, Any]) -> frozenset[Keyword]:
    p = get(ctx.get("power", ""))
    return frozenset(p.keywords) if p is not None else frozenset()


def _has_keyword(*words: Keyword):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return bool(_keywords_of(ctx) & set(words))

    return gate


def _of_type(*types: DamageType):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") in types

    return gate


def _target_is(c: Cast, *words: str):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and bool(c.kinds_of(on=foe) & set(words))

    return gate


def _is_melee(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach_of(0).kind == "melee"


def _augmented(world: World, who: int, ref: str) -> bool:
    """Did that creature spend power points on that row this fight?

    `c.points_spent` is the same read from inside a body; a declared
    trigger's predicate is handed `(world, me, ev)` and no `Cast`.
    """
    from combat_engine.engine.components import PowerPoints

    pool = world.get(who, PowerPoints)
    return pool is not None and pool.augmented.get(ref, 0) > 0


def _ally_miss_within(radius: int):  # noqa: ANN202
    """"An ally within N squares misses with an augmented power."

    `Miss` names the swinger `attacker`, so `about_me` and `ally_within`
    -- which read `actor` -- are both false here forever.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me:
            return False
        from combat_engine.engine import query

        if who not in query.allies(world, me):
            return False
        if query.distance_between(world, me, who) > radius:
            return False
        return _augmented(world, who, getattr(ev, "power", ""))

    return check


def _on_hit_with(c: Cast, ref: str, fn: Any) -> None:
    """Hang a rider on the wielder's hits with one named row.

    The shape nine properties in this file wanted and could not have while
    the specs printed their power in prose: the ref is in the spec now, so
    "when you hit with <ref> using this wand" is `ev.power` and nothing
    cleverer.
    """

    def on_hit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.power == ref:
            fn(ev)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


# -- level 3 ----------------------------------------------------------------


@power(
    "i3033x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3033x1(c: Cast) -> None:
    """`partial=True` is exactly the printed narrowing: superior cover
    still costs, and only the penalty for the lesser sort goes."""
    c.ignore_cover(on=c.me, until=When.ENCOUNTER, partial=True)


@power(
    "i3049x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3049x1(c: Cast) -> None:
    """Skill modifiers are read under `skill:<name>`, so this is a real
    modifier rather than an inert row."""
    c.bonus(
        "skill:perception", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i3049p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3049p1(c: Cast) -> None:
    """Needs a spirit companion on the board; with none there is no square
    to measure adjacency from and the row has nothing to arm."""
    pet = c.companion()
    if pet is None:
        return

    def hurt(ev: DamageApplied) -> None:
        if ev.source not in c.enemies() or ev.target not in c.allies():
            return
        if c.adjacent_to(pet, ev.target):
            c.flat(2 * c.enhancement, on=ev.source)

    c.watch(DamageApplied, hurt, until=When.EONT)


@power(
    "i3080x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3080x1(c: Cast) -> None:
    """"While flying" is asked two ways because neither alone is the whole
    of it: `c.moving_as` is true during the flight and `height` is true of
    a creature that has gone up and stopped. A plain "+1 bonus" with no
    type word is untyped."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _is_melee(ctx)
        and (c.moving_as("fly") or c.height(on=c.me) > 0),
    )


@power(
    "i3080p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i3080p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.push(c.enhancement, on=foe)


@power(
    "i3174x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3174x1(c: Cast) -> None:
    """"You can increase" is written as always increasing: a shove one
    square longer is never a thing the wielder would decline, and asking
    per shove costs a decision for no branch."""
    c.forces(1, on=c.me, until=When.ENCOUNTER)


@power(
    "i3187p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with an attack using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i3187p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.weakened(on=foe, until=When.SAVE_ENDS)


@power(
    "i3197x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3197x1(c: Cast) -> None:
    c.bonus(
        "skill:intimidate", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i3197p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit a target with an attack using this wand",
    on=Trigger(Hit, by_me, "you hit with this wand"),
)
def i3197p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.push(c.enhancement, on=foe)


@power(
    "i3200x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3200x1(c: Cast) -> None:
    """"Miss every target" is a question about a whole use, so it is asked
    of `PowerResolved` -- which carries every roll the use made -- rather
    than of `Miss`, which only ever knows about one target."""

    def finished(ev: PowerResolved) -> None:
        if ev.actor != c.me or not ev.rolls:
            return
        p = get(ev.power)
        if p is None or p.usage != Usage.AT_WILL:
            return
        if any(getattr(r, "hit", False) for r in ev.rolls):
            return
        ref = ev.power
        c.bonus(
            "attack", 2, kind="item", on=c.me, until=When.EONT, once=True,
            when=lambda ctx: ctx.get("power") == ref,
        )

    c.watch(PowerResolved, finished, until=When.ENCOUNTER)


@power(
    "i3344x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3344x1(c: Cast) -> None:
    """"At 0 hit points or fewer" is read back from the event: `hp` is
    where the creature landed and `amount` is what put it there. The
    "primal healing power" half is dropped -- `Healed` names no power, so
    the keyword cannot be asked. The guard stops the extra healing from
    answering itself."""
    busy: list[int] = []

    def topped_up(ev: Healed) -> None:
        # The "primal healing power" half, which `Healed.power` answers.
        if not c.healed_by(ev, keyword=Keyword.PRIMAL):
            return
        if busy or ev.source != c.me or ev.amount <= 0:
            return
        if ev.hp - ev.amount > 0:
            return
        busy.append(1)
        try:
            c.heal(c.roll(f"{max(1, c.enhancement)}d6"), on=ev.target)
        finally:
            busy.clear()

    c.watch(Healed, topped_up, until=When.ENCOUNTER)


@power(
    "i3345x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3345x1(c: Cast) -> None:
    c.forces(1, on=c.me, until=When.ENCOUNTER)


@power(
    "i3374x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3374x1(c: Cast) -> None:
    """A reroll of the ones on one named power's damage, against the victim
    the card names.

    `p13799` is printed and declared, so the power the rider hangs on was
    never the hold -- the rider itself was. Not `c.reroll_damage`, which
    rolls the whole expression twice and keeps the higher.

    **The combat-advantage condition is written now, and the old note said
    exactly why it could not be.** It read: *"the floor is read where the
    dice are rolled, and nothing there is told whether the target was
    granting advantage. So this rerolls that power's ones against anybody,
    which is wider than the card."* Correct, and a widening -- which is why
    it was `dropped=`. `Cast._reroll_ctx` tells the read site who is being
    hit, and `c.reroll_ones(when=)` reads it.
    """
    from combat_engine.engine.query import has_combat_advantage

    me = c.me
    c.reroll_ones(
        ref="p13799", on=me,
        when=lambda ctx: (ctx.get("target") is not None
                          and has_combat_advantage(c.world, me, ctx["target"])),
    )
@power(
    "i3406p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i3406p1(c: Cast) -> None:
    """As `p416`, and the creature dies if the blow leaves it at 5 or fewer.

    `c.kill` and not damage for the remainder: a blow is resisted, is halved
    by being insubstantial, and feeds every "when you damage" rider on the
    board, where the printed sentence does none of those.
    """
    victim = c.target
    c.use_power("p416", on=c.target, spend=False)
    if victim is None:
        return
    body = c.world.get(victim, Health)
    if body is not None and 0 < body.hp <= 5:
        c.kill(on=victim)
@power(
    "i3406p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you reduce a creature to 15 or fewer hit points with this wand",
    on=Trigger(DamageApplied, by_me, "you damage a creature with this wand"),
)
def i3406p2(c: Cast) -> None:
    """Reduce a creature to 15 hit points or fewer with this wand and it dies.

    The threshold is read off the trigger, which is a `DamageApplied` and
    carries the hit points the blow left -- so "reduce *to* 15 or fewer" is
    the state after the damage rather than a second measurement.
    """
    victim = getattr(c.trigger, "target", None)
    left = getattr(c.trigger, "hp", None)
    if victim is not None and left is not None and 0 < left <= 15:
        c.kill(on=victim)
@power(
    "i3434x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3434x1(c: Cast) -> None:
    """A penalty takes no `kind`, by the rule. Half of a +1 is 0, so the
    printed minimum does the work at the bottom of the ladder."""

    def on_blood(ev: DamageApplied) -> None:
        if ev.source != c.me or not _just_bloodied(c, ev):
            return
        n = max(1, c.enhancement // 2)
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, n, on=ev.target, until=When.EONT)

    c.watch(DamageApplied, on_blood, until=When.ENCOUNTER)


@power(
    "i3465x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3465x1(c: Cast) -> None:
    """The spec prints `p10137` now, so the rider is an ordinary watch on
    the wielder's hits with that one row. `c.flat` rather than `c.bonus`:
    the number is fixed and the card adds it to the power's own damage
    rather than to every roll the wielder makes."""
    _on_hit_with(
        c, "p10137",
        lambda ev: c.flat(c.enhancement, dtype=DamageType.FIRE, on=ev.target),
    )


@power(
    "i3465p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def i3465p1(c: Cast) -> None:
    """The whole printed Effect is p10137, declared and finished. That
    row is an area burst hitting everything in it, so the aiming belongs
    to it: `NO_TARGET` here and no `on=`, rather than the single ranged
    target this header guessed while the block had nothing to name."""
    c.use_power("p10137", spend=False)


@power(
    "i3504p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    dropped=("c.teleport(adjacent_to=)",),
)
def i3504p1(c: Cast) -> None:
    """The destination restriction -- next to a plant or a fey creature --
    is dropped: `to=` names one square outright and nothing narrows the
    decider's choice to a set. Dropping it only makes the row freer."""
    c.teleport(5)


@power(
    "i3525x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("by_ref()",),
)
def i3525x1(c: Cast) -> None:
    """Rolls bigger dice for a named power's damage when it was triggered by an
    attack made with this implement.

    **One gap now, not two.** `c.change_dice()` was the second marker and
    exists; it is also the right verb, and it takes the ref of the row whose
    dice change. The spec names that row in prose, so there is nothing to pass
    it. The whole of what is missing is the ref."""


@power(
    "i3527p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i3527p1(c: Cast) -> None:
    """`Dropped.dead` is the kill rather than the knockdown, and `source`
    is who struck the blow. Adjacency is asked while the body is still on
    the board, which is why this answers `Dropped` and not `Died`."""
    ev = c.trigger
    foe = getattr(ev, "actor", None)
    if foe is None or not getattr(ev, "dead", False):
        return
    if not c.adjacent(to=foe) or not _nonminion(c, foe):
        return
    c.regain_surge(2, on=c.me)


@power(
    "i684p1",
    level=3,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you make a melee attack using this ki focus",
    on=Trigger(AttackDeclared, both(by_me, by_melee), "you swing in melee"),
)
def i684p1(c: Cast) -> None:
    """`c.deals` is an override rather than an addition, which is the
    printed "instead of any other damage type". It is declared on the
    swing, so it has to be in place before the damage is rolled -- hence
    `AttackDeclared` rather than `Hit`."""
    c.deals(DamageType.FIRE, on=c.me, until=When.EOT, implement=True)


@power(
    "i726x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i726x1(c: Cast) -> None:
    """One modifier, gated on both halves of the printed condition.

    **"When charging" was already answerable and the old note was stale.**
    It said speed is totalled with no context at all; `query.speed` takes a
    `ctx` and its own docstring is this very clause: *"'+4 to speed when
    charging' -- a gate on a key the context did not carry -- was silently
    false … The three places that measure a charge's run pass the word."*

    **The ctx key and not `query.charging`**, which is the other half of
    #732 and is the wrong tool here: a charge's reach is measured by
    `actions._charges` **before** the charge starts, to decide whether one
    is even on offer, so the creature is not charging yet at the moment this
    bonus has to count. Both facts are real and they are a moment apart.

    **And the shape is asked in the gate too, which fixes two faults in the
    old shape of this row.** It laid the bonus from a `granted()` helper,
    called once if the druid was already in beast form and again from an
    `EffectApplied` watcher whenever the shape was taken:

    * the bonus was `until=When.ENCOUNTER` and ungated on the form, so it
      **kept paying after the druid left beast form**, for the rest of the
      fight;
    * shaping twice laid it twice, and two untyped bonuses stack, so a druid
      that shifted out and back had **+2 speed** where the card says +1.
      Found by this row's own driver reading `5 -> 7`.

    Asking both conditions inside one modifier cannot do either, and reads
    the card more directly: it is a property of the item, true exactly when
    both things are.

    No type word on the card, so untyped."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: (
                bool(ctx.get("charge")) and in_beast_form(c.world, c.me)
            ))


@power(
    "i726p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a charge attack using this totem",
    on=Trigger(Hit, both(by_me, by_charge), "you hit with a charge"),
)
def i726p1(c: Cast) -> None:
    """"The space it vacated" has to be read before the shove, not after.
    The beast-form requirement is a real gate now: `in_beast_form` reads
    the label every druid shape wears."""
    foe = _struck(c)
    if foe is None or not in_beast_form(c.world, c.me):
        return
    vacated = _square(c, foe)
    c.push(1, on=foe)
    if vacated is not None:
        c.shift(1, to=vacated)


@power(
    "i812p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you score a critical hit with a divine radiant power",
    on=Trigger(
        Hit,
        both(_crit_by_me, by_keyword(Keyword.RADIANT)),
        "you crit with a radiant power",
    ),
)
def i812p1(c: Cast) -> None:
    """The worship requirement is a build-time line, not a board one."""
    foe = _struck(c)
    if foe is not None:
        c.stunned(on=foe, until=When.EONT)


@power(
    "i836p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with an attack using this ki focus",
    on=Trigger(Miss, by_me, "you miss with this ki focus"),
)
def i836p1(c: Cast) -> None:
    c.reroll_attack()


@power(
    "i847p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you use p8278",
    on=Trigger(PowerUsed, _used_by_me("p8278"), "you use p8278"),
)
def i847p1(c: Cast) -> None:
    """The card says "the creature that **triggered** p8278", and this read
    its *targets* instead -- so it returned at its first line on 48 of 48
    attempts, because p8278 prints no Target line and genuinely picks
    nobody.

    `PowerUsed.trigger` is what the watched power was used in answer to,
    which for p8278 is the `Dropped` event its own card names: "a creature
    within 5 squares of you is reduced to 0 hit points". So the creature
    this row is about is that event's `actor`.

    **`PowerUsed`'s own docstring predicted this exact mistake** -- *"`targets`
    is not that thing and is not a stand-in for it: an immediate action is
    routinely NO_TARGET, or aims itself at a creature off its own trigger,
    so the two name different creatures exactly when the distinction
    matters."* This row was the case it was warning about. #941."""
    dropped = getattr(c.trigger, "trigger", None)
    who = getattr(dropped, "actor", None)
    if who is None:
        return
    near = [e for e in c.enemies() if e != who and c.adjacent_to(who, e)]
    if not near:
        return
    pick = c.choose(near, "grants combat advantage")
    if pick is not None:
        c.grants_advantage(on=pick, until=When.EONT, to="team")


@power(
    "i998x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.guild_training()",),
)
def i998x1(c: Cast) -> None:
    """Adds to the temporary hit points one named class feature hands out,
    and nothing models that feature or announces its payout."""


@power(
    "i998p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an unbloodied enemy",
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def i998p1(c: Cast) -> None:
    """`Hit` fires before the damage, so "unbloodied" is still true of a
    creature this very blow is about to bloody -- which is the printed
    reading."""
    foe = _struck(c)
    if foe is None or c.bloodied(on=foe):
        return
    c.shift(max(1, c.con_mod))


@power(
    "i1015x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("cf:warlock-f1c0",),
)
def i1015x1(c: Cast) -> None:
    """Re-aimed at the ref. The extra damage is the running value of the
    star pact's boon, and that boon is a row -- `cf:warlock-f1c0`, named
    by `cf:warlock-f1s0` -- which is not declared. A verb was the wrong
    thing to ask for: once the row exists its value is the row's."""


@power(
    "i1032p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target",
    on=Trigger(Hit, by_me, "you hit a target"),
)
def i1032p1(c: Cast) -> None:
    """`c.shroud` is the once-per-turn limit's own door and does not count
    against it, which is exactly what the printed exception asks for."""
    foe = _struck(c)
    if foe is not None:
        c.shroud(on=foe)


# -- level 4 ----------------------------------------------------------------


@power(
    "i1085x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1085x1(c: Cast) -> None:
    """"The next attack that hits that enemy" is anybody's attack, not just
    yours, so this is a one-shot watch on `Hit` rather than a damage bonus
    on the wielder. The flag rather than `once=True`: the effect would
    otherwise expire on the first unrelated hit on the board."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        p = get(ev.power)
        if p is None or Keyword.FORCE not in p.keywords:
            return
        foe = ev.target
        spent: list[int] = []

        def extra(later: Hit) -> None:
            if spent or later.target != foe:
                return
            spent.append(1)
            c.flat(1, dtype=DamageType.FORCE, on=foe)

        c.watch(Hit, extra, until=When.ENCOUNTER)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1085p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1085p1(c: Cast) -> None:
    """The printed Effect is p4200, which is declared and finished, so
    `c.use_power` is the whole block. Lent and not spent: the item's own
    daily use is the price, and the bearer does not own that row."""
    c.use_power("p4200", on=c.target, spend=False)


@power(
    "i1197x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1197x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so this gate is real --
    it is the damage side that is thin. No type word, so untyped."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "i1197p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with an opportunity attack",
    on=Trigger(Hit, _opportunity_hit_on_me, "an enemy hits you with an opportunity"),
)
def i1197p1(c: Cast) -> None:
    """**Written: the payout had a ref all along.** The marker named
    `cf:monk-f0c0`..`c4`, which are not rows; the five are `FLURRIES` and
    `c.flurry_of_blows()` names whichever one the tradition granted.

    `again=True` is the printed "even if you have already used it during
    this round" -- it waives `once_per_round`, which every one of the five
    declares. `spend=` is left alone because the flurry is at-will.

    Aimed at `ev.attacker`: the enemy made the opportunity attack, so it is
    the creature in reach, and the flurry's own line targets one creature.
    The row's own `target=SELF` is the trigger's subject, not the swing's.
    """
    flurry = c.flurry_of_blows()
    foe = getattr(c.trigger, "attacker", None)
    if flurry and foe is not None:
        c.use_power(flurry, on=foe, again=True)


@power(
    "i1278p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="an attack made with this implement hits",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i1278p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.dazed(on=foe, until=When.EONT)


@power(
    "i1398p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    trigger="you make an attack that targets AC",
    on=Trigger(
        AttackDeclared, _vs_ac_by_me, "you attack against AC",
        window=Window.BEFORE,
    ),
)
def i1398p1(c: Cast) -> None:
    """Moves the triggering attack onto Will and makes all its damage
    psychic.

    **The trigger gained `window=Window.BEFORE` and that is the fix.** It
    was offered in the ordinary window, where `resolve.roll` has already
    read `vs` off the event -- so the swap would have set the field after
    anything could read it. The damage half worked there, which is why
    nothing looked wrong. #509.
    """
    c.retarget_defence(WILL)
    c.deals(DamageType.PSYCHIC, on=c.me, until=When.EOT, implement=True)


@power(
    "i1515x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1515x1(c: Cast) -> None:
    """Written. The old note said a skill modifier is read with no context,
    so the bonus stood all fight -- which it did, and the narrowing does not
    need a context: `query.charging` is a fact about the creature, so the
    gate asks it directly.

    **"To jump as part of that charge" is not separated from "during that
    charge", and that is exact rather than lazy.** A charge is a run and a
    swing; the only Athletics check it can contain is the jump over
    something in the way. So a gate on the charge alone cannot pay out on
    any other check, and splitting the two would be a distinction the board
    cannot produce.

    `2 + c.enhancement`, which is the printed sum, and untyped -- no type
    word on the card. #732."""
    c.bonus("skill:athletics", 2 + c.enhancement, on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: charging(c.world, c.me))


@power(
    "i1515p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def i1515p1(c: Cast) -> None:
    """`c.borrowed_rows` is the list a row that swaps out the basic attack
    needs, and `c.charge_at(ref=)` is where it goes. `charges=True` or the
    engine measures the sword's reach before the run and refuses this."""
    victim = c.target
    if victim is None:
        return
    c.no_provoke(on=c.me, until=When.EOT)
    rows = c.borrowed_rows(of=c.me, at_will=True, melee=True)
    pick = c.choose(rows, "in place of a melee basic attack") if rows else None
    c.charge_at(victim, ref=pick or "")


@power(
    "i1533p1",
    level=4,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def i1533p1(c: Cast) -> None:
    """`c.deals` is an override and covers every attack rather than only
    the melee and close ones -- the damage context does not carry the
    weapon, so it cannot be narrowed. Re-taking this is harmless: the same
    override lands on top of itself.

    The bright light it sheds out to 5 squares is written and carried, so it
    moves with the wielder."""
    c.deals(DamageType.FIRE, on=c.me, until=When.ENCOUNTER, implement=True)
    c.light(5, on=c.me, until=When.ENCOUNTER)


@power(
    "i1533p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.FIRE],
    trigger="you hit an enemy with an attack power using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i1533p2(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.damage("1d8", dtype=DamageType.FIRE, on=foe)
    c.push(3, on=foe)


@power(
    "i1588p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your class feature's attack flurry",
    on=Trigger(PowerUsed, _i_used_a_flurry, "you use that class power"),
)
def i1588p1(c: Cast) -> None:
    """**Written: both halves had a ref all along.** The marker named
    `cf:monk-f0c0`..`c4`; the five rows are `FLURRIES`.

    Declared on `PowerUsed`, which `dsl.use` announces *before* running the
    body -- which is the only window in which a damage modifier can be in
    place for the flurry's own roll. The push is the other way round, so it
    hangs on a one-shot `PowerResolved` watch: pushing first would move the
    creature before the extra damage it is owed.

    The extra damage is gated on the power rather than spent `once=True`,
    because "each target" is plural on the card; `until=When.EOT` cannot
    leak to a second flurry, since all five are `once_per_round`.
    """
    enh = c.enhancement
    c.bonus(
        "damage", enh, on=c.me, until=When.EOT,
        when=lambda ctx: ctx.get("power") in FLURRIES,
    )

    me = c.me

    def shoved(ev: PowerResolved) -> None:
        # Gated, not `once=True`: this row's own `PowerResolved` lands
        # first and would eat a one-shot watch.
        if ev.actor != me or ev.power not in FLURRIES:
            return
        for foe in ev.targets:
            c.push(enh, on=foe)

    c.watch(PowerResolved, shoved, until=When.EOT, on=me, label=c.ref)


@power(
    "i1594p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    trigger="you hit an enemy with an implement power using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i1594p1(c: Cast) -> None:
    """"Ongoing 5 fire and radiant" is five damage of two types at once,
    not five of each, and `c.ongoing(dtypes=)` is that: one burn, one
    save, shrugged off only as far as the creature resists both. Paragon
    numbers are out of scope."""
    foe = _struck(c)
    if foe is not None:
        c.ongoing(
            5, dtypes=(DamageType.FIRE, DamageType.RADIANT),
            on=foe, until=When.SAVE_ENDS,
        )


@power(
    "i1825x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.within(extend=)",),
)
def i1825x1(c: Cast) -> None:
    """The curse-damage half is written; the reach half is dropped.

    **`todo` became `dropped` and both symbols were re-aimed.** The curse's
    extra damage was never unreachable: `features/strikers.extra_damage`
    pays it as `c.damage(rolled, c.total(f"{CURSE} damage"), ...)`, so a
    modifier on that key *is* the printed "+1 bonus to it". Laid in
    `Window.BEFORE` off the triggering `Hit`, because the striker's own
    payout is an ordinary `AFTER` watch on the same event and the bonus has
    to be standing by the time it reads the total.

    `until=When.EOT` rather than a one-shot: the striker's latch is per
    round and pays on the first qualifying hit, which -- once the bonus is
    laid -- is this one, so "for that attack" and "until the end of the
    turn" come to the same payment.

    What is left is the other clause. The distance at which `p6855` picks
    its second creature is the literal 3 in `c.within(3, of=victim, ...)`
    inside *that row's body*, and no modifier reaches a literal.
    `c.bonus("range", ...)` -- which the old marker pointed at -- is the
    wrong lever: it lengthens a row's own printed range line, which p6855
    already gets right.

    **The marker is right about the obstacle and wrong about the answer,
    and the answer is one line in another file.** This tree does not teach
    a modifier to reach a literal; it teaches the laying row to *read a
    raise*. #715 settled it -- "the answer is for the laying row to READ a
    raise rather than for this one to reach into it, which is what
    `c.change_amount` / `c.amount_for` has always been for" -- and
    `i1986p1`, this row's own sibling, is written exactly that way.

    So the finished shape is: `p6855` asks
    `c.within(c.amount_for(SPREAD, 3), of=victim, side="enemy")` and this
    row adds `c.change_amount(SPREAD, 5, on=c.me, until=When.ENCOUNTER)`
    beside the bonus below. `amount_for` takes the largest, so the printed
    3 and the raised 5 coexist, and the ordering is not a trap here -- this
    is a standing trait and `p6855` reads the amount when its body runs,
    which is the half `i1986p1` had to declare a trigger for.

    Not written because `p6855` lives in `powers/warlock/level_1_c.py`,
    which this wave did not own. The marker stays naming the symbol that
    does not exist, rather than being re-pointed at a verb that does.
    """
    me = c.me

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "p6855":
            return
        c.bonus(f"{CURSE} damage", 1, on=me, until=When.EOT)

    c.watch(
        Hit, on_hit, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=c.ref,
    )


@power(
    "i1825p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1825p1(c: Cast) -> None:
    """The whole printed Effect is p6855, declared and finished. Lent for
    the one use and not spent: the wand's encounter use is the price."""
    c.use_power("p6855", on=c.target, spend=False)


@power(
    "i1827x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1827x1(c: Cast) -> None:
    """The spec prints `p3214`, whose own hit lays a -2 to attack rolls
    until the end of the wielder's next turn. "While it is taking the
    penalty" is therefore that window and not a second question: the
    second watch is hung with the same duration the penalty has, so it
    stops when the penalty does."""

    def struck(ev: Hit) -> None:
        foe = ev.target

        def swung(later: AttackDeclared) -> None:
            if later.attacker == foe:
                c.flat(3 + c.enhancement, dtype=DamageType.PSYCHIC, on=foe)

        c.watch(AttackDeclared, swung, until=When.EONT)

    _on_hit_with(c, "p3214", struck)


@power(
    "i1827p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1827p1(c: Cast) -> None:
    """The whole printed Effect is p3214, declared and finished."""
    c.use_power("p3214", on=c.target, spend=False)


@power(
    "i1829x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1829x1(c: Cast) -> None:
    """The spec prints the ref here, so the rider is writable. "The ally
    that marked a target" is found by asking each ally whether the mark on
    the victim is theirs -- `c.marked(by=)` is relational."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != "p2365":
            return
        foe = ev.target
        for mate in c.allies():
            if c.marked(on=foe, by=mate):
                c.bonus(
                    "attack", 1, on=mate, until=When.EONT,
                    when=lambda ctx, f=foe: ctx.get("target") == f,
                )

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1829p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def i1829p1(c: Cast) -> None:
    """The spec prints the ref, so the row can simply resolve it.
    `c.grant_attack` takes a ref and a swinger, and the swinger here is
    the wielder."""
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p2365")


@power(
    "i1830x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1830x1(c: Cast) -> None:
    """The spec prints `p4305`, and `c.forces` is gated on `power` and
    `how`, so "one extra square of *that* row's slide" is exact rather
    than a blanket extra square on everything the wielder shoves."""
    c.forces(
        1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p4305" and ctx.get("how") == "slide",
    )


@power(
    "i1830p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1830p1(c: Cast) -> None:
    """The whole printed Effect is p4305, declared and finished."""
    c.use_power("p4305", on=c.target, spend=False)


@power(
    "i1833x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1833x1(c: Cast) -> None:
    """**Written: the curse's die is `c.dice_for`, not an unreachable roll.**

    `features/strikers.extra_damage` rolls it as `c.dice_for(CURSE,
    "1d6", {"target": ev.target})` -- which is exactly the read half
    `c.change_dice` says a row must have to be changed. "An extra die of
    it" is therefore one more of whatever the warlock is currently
    rolling, read back rather than assumed, so a feat that has already
    raised the die keeps its own face.

    Laid in `Window.BEFORE` off the triggering `Hit`, like `i1825x1`: the
    striker pays from an ordinary `AFTER` watch on the same event, and
    "with the p3403 power" is not a key the `dice_for` context carries --
    only `target` is -- so that narrowing has to be made at the moment
    rather than in the gate.

    "At maximum hit points" is read on the `Hit`, which is announced
    before any damage is rolled, so the creature is still whole there.
    """
    me = c.me

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "p3403":
            return
        foe = ev.target
        if c.wounded(on=foe) or not c.cursed(foe):
            return
        bigger = _one_more_die(c.dice_for(CURSE, "1d6", {"target": foe}))
        c.change_dice(
            CURSE, bigger, on=me, until=When.EOT,
            when=lambda ctx: ctx.get("target") == foe,
        )

    c.watch(
        Hit, on_hit, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=c.ref,
    )


@power(
    "i1833p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1833p1(c: Cast) -> None:
    """The spec prints the ref, so the row resolves it outright."""
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p3403")


@power(
    "i1834x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_damage_reduced()",),
)
def i1834x1(c: Cast) -> None:
    """Re-aimed. `p7636` is printed and declared, so the ref is no longer
    the hold. The trigger is that row's own clause about reducing the
    damage its target would deal, and nothing announces a reduction --
    `c.reduce` takes the number off and emits no event of its own, so
    there is no moment to hang this on."""


@power(
    "i1834p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
)
def i1834p1(c: Cast) -> None:
    """The whole printed Effect is p7636, declared and finished. The
    reach is that row's -- a melee 5 -- rather than the ranged 10 this
    header guessed while the block had nothing to point at."""
    c.use_power("p7636", on=c.target, spend=False)


@power(
    "i1835x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1835x1(c: Cast) -> None:
    """The spec prints `p4199`, whose own hit pushes 1 square. The card
    replaces that number with the wielder's Wisdom modifier, and
    `c.forces` adds rather than sets, so the difference is what is laid
    -- gated on that row's pushes and nothing else. Floored at 0: a
    modifier of 1 or less is the printed number already, and a negative
    would shorten somebody else's shove."""
    c.forces(
        max(0, c.wis_mod - 1), on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p4199" and ctx.get("how") == "push",
    )


@power(
    "i1835p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
)
def i1835p1(c: Cast) -> None:
    """The whole printed Effect is p4199, declared and finished. That row
    is a close burst picking an ally out of it, not the ranged single
    target this header guessed, so the aiming is left to it: `NO_TARGET`
    here and no `on=`, and p4199 chooses the way it does on any turn."""
    c.use_power("p4199", spend=False)


@power(
    "i1837x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1837x1(c: Cast) -> None:
    """The spec prints `p2780`. "A different enemy within 2 squares of
    the target" is a choice, so it is offered rather than picked; a
    penalty takes no `kind`, by the rule."""

    def struck(ev: Hit) -> None:
        near = [e for e in c.within(2, of=ev.target, side="enemy") if e != ev.target]
        if not near:
            return
        pick = c.choose(near, "takes the penalty to attack rolls")
        if pick is not None:
            c.penalty("attack", 2, on=pick, until=When.EONT)

    _on_hit_with(c, "p2780", struck)


@power(
    "i1837p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
)
def i1837p1(c: Cast) -> None:
    """The whole printed Effect is p2780, declared and finished."""
    c.use_power("p2780", on=c.target, spend=False)


@power(
    "i1856x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1856x1(c: Cast) -> None:
    """**Written: the five rows the marker named as missing are `FLURRIES`.**

    A trait, armed once, laying one untyped point on the flurry's damage --
    the shape `feats/defenders.py` already uses for the same family.

    "When it is triggered by an attack using this ki focus" is the file's
    standing judgement: the damage context carries no weapon, so a property
    phrased that way is armed always-on for as long as the item is worn.
    """
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in FLURRIES,
    )


@power(
    "i1856p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i1856p1(c: Cast) -> None:
    """"You ignore **the enemy's** immunities and resistances", so the
    hold is gated on the creature that was hit rather than laid against
    everybody. Blanket, because no number is printed."""
    foe = c.trigger.target
    c.ignore_resistance(
        None, on=c.me, until=When.EONT, immunity=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "i1950p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1950p1(c: Cast) -> None:
    """"Target's save ends **both**", and a duration cannot name another
    creature's saving throw -- so the bonus hangs on the encounter clock and
    is taken off when the target's save lands.

    `SavingThrow` carries `against`, which is the hold's own `str`, so the
    throw that ends the penalty is told from any other save the target rolls
    -- an ongoing burn, somebody else's daze. `saved` is read at the AFTER
    window, which is after the roll and before `Effects.save` acts on it.
    """
    foe = c.target
    if foe is None:
        return
    hold = c.penalty("save", 2, on=foe, until=When.SAVE_ENDS)
    friends = [c.me, *c.within(10, side="ally")]
    who = c.choose(friends, "gains the bonus to saving throws")
    if who is None or hold is None:
        return
    boon = c.bonus("save", 2, kind="power", on=who, until=When.ENCOUNTER)
    if boon is None:
        return

    def ends_both(ev: SavingThrow) -> None:
        if ev.actor == foe and ev.saved and ev.against == str(hold):
            c.end_effect(boon, why=f"{c.ref}: the target saved")

    c.watch(SavingThrow, ends_both, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "i1954p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you hit with a power that has the thunder keyword",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.THUNDER)), "you hit with thunder"
    ),
)
def i1954p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.condition(Condition.DEAFENED, on=foe, until=When.ENCOUNTER)
    c.ongoing(5, DamageType.THUNDER, on=foe, until=When.SAVE_ENDS)


@power(
    "i1972p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally within 5 squares misses with an augmented psionic power",
    on=Trigger(Miss, _ally_miss_within(5), "an ally within 5 squares misses"),
)
def i1972p1(c: Cast) -> None:
    """Written: `c.regain_points` is the payout that was missing.

    The trigger was already real -- `Miss` names the swinger `attacker`,
    and an augmented use is one `Pool.augmented` has a number for. The
    gap was only that `c.spend_points` took points away, `c.points`
    counted what was left, and nothing put any back.

    The *ally's* miss is the trigger and the *wielder* regains, so the
    payout takes no `on=`: `c.regain_points` defaults to the caster, which
    is this item's owner and not the creature that missed.
    """
    c.regain_points(2)


@power(
    "i1990p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit an enemy with a psychic attack using this orb",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.PSYCHIC)), "you hit with psychic"
    ),
)
def i1990p1(c: Cast) -> None:
    """`c.points_spent` reads how much was put into this row, which is the
    Augment line asked as a question rather than written as a branch."""
    foe = _struck(c)
    if foe is None:
        return
    augmented = c.points_spent(c.ref) >= 2

    def failed(ev: SavingThrow) -> None:
        if ev.actor != foe or ev.saved:
            return
        amount = c.roll("1d10") + c.enhancement if augmented else c.enhancement
        c.flat(amount, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(SavingThrow, failed, until=When.ENCOUNTER)


@power(
    "i1993x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1993x1(c: Cast) -> None:
    c.bonus("skill:bluff", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1993p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
    keywords=[Keyword.AUGMENTABLE],
)
def i1993p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.grants_advantage(on=foe, until=When.EONT, to="team")
    if c.points_spent(c.ref) >= 2:
        c.dazed(on=foe, until=When.EONT)


@power(
    "i1994x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1994x1(c: Cast) -> None:
    c.bonus(
        "skill:diplomacy", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i1994p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.AUGMENTABLE],
    trigger="you hit an enemy with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
)
def i1994p1(c: Cast) -> None:
    """`c.grant_attack` is the verb for somebody else swinging now, and
    `attack_bonus=` is where the Augment's power bonus goes."""
    foe = _struck(c)
    if foe is None:
        return
    near = [x for x in c.within(1, of=foe) if x != foe]
    if not near:
        return
    victim = c.choose(near, "the enemy attacks this one")
    if victim is None:
        return
    plus = c.wis_mod if c.points_spent(c.ref) >= 2 else 0
    c.grant_attack(foe, on=victim, attack_bonus=plus)


@power(
    "i1995x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1995x1(c: Cast) -> None:
    c.bonus("skill:stealth", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1995p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
    keywords=[Keyword.AUGMENTABLE],
)
def i1995p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    if c.points_spent(c.ref) >= 1:
        c.invisible(on=c.me, until=When.EONT)
    else:
        c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "i1996x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1996x1(c: Cast) -> None:
    c.bonus("skill:insight", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1996p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit an enemy with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
)
def i1996p1(c: Cast) -> None:
    """`c.flee` is the creature running under its own power, which is what
    "moves its speed away from you as a free action" is."""
    foe = _struck(c)
    if foe is not None:
        c.flee(c.speed_of(foe), on=foe)


@power(
    "i1997x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1997x1(c: Cast) -> None:
    c.bonus("skill:insight", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1997p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an area or a close attack with a psionic power",
    on=Trigger(AttackDeclared, _area_by_me, "you make a close or area attack"),
    todo=("c.exclude_squares()",),
    keywords=[Keyword.AUGMENTABLE],
)
def i1997p1(c: Cast) -> None:
    """`c.widen_areas` grows a burst and nothing punches holes in one, so
    the squares cannot be left out and the Augment has nothing to count."""


@power(
    "i1999x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1999x1(c: Cast) -> None:
    c.bonus("skill:insight", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1999p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit an enemy with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
)
def i1999p1(c: Cast) -> None:
    """The damage dealt is not known when `Hit` fires, so the relay waits
    for the `DamageApplied` that follows.

    **Written: the whole target set is `Hit.among`, not `Hit.targets`.**
    `resolve.attack` sets `landed.among = among or (target,)` after
    building the event, so it is a plain attribute rather than a declared
    field -- which is why reading the dataclass says it does not exist.
    That is the one list "not included as a target of your attack" needs,
    so the relay now excludes every creature the use touched rather than
    only the one it was announced against."""
    foe = _struck(c)
    if foe is None:
        return
    struck = frozenset(getattr(c.trigger, "among", ()) or (foe,))
    done: list[int] = []

    def relay(ev: DamageApplied) -> None:
        if done or ev.source != c.me or ev.target != foe:
            return
        done.append(1)
        near = [x for x in c.within(1, of=foe) if x not in struck]
        pick = c.choose(near, "takes the same damage") if near else None
        if pick is not None:
            c.flat(ev.amount, dtype=DamageType.PSYCHIC, on=pick)

    c.watch(DamageApplied, relay, until=When.EOT)


@power(
    "i2115p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you damage an enemy with your class feature's attack flurry",
    on=Trigger(DamageApplied, _my_flurry_damaged, "your flurry damages an enemy"),
)
def i2115p1(c: Cast) -> None:
    """**Written: the trigger had a ref all along.** The marker named
    `cf:monk-f0c0`..`c4`; the five rows are `FLURRIES`.

    `DamageApplied` rather than `Hit`: the card says *damage*, and the
    flurry's payout is a flat addition that can be resisted away to
    nothing. `detail` is the field that names the row -- `DamageApplied`
    has no `power`.

    `on=` is passed explicitly. The header declares `ONE_CREATURE`, so
    `c.target` is whoever the chooser picked, and the card means the
    creature the flurry hurt.
    """
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "i2305p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy under your cf:warlock-f4 drops to 0 hit points",
    on=Trigger(Dropped, _my_cursed_drop, "a creature you cursed drops"),
    dropped=("c.decline_boon()",),
)
def i2305p1(c: Cast) -> None:
    """The curse is relational and `Relation.CURSED_BY` reads back, so the
    trigger is real, and the +1 it pays lands. "Instead of triggering your
    pact boon" is the clause still missing, and it is a **cost** -- which
    is why this stays `dropped=` and the row is a widening until the door
    lands.

    **Re-pointed off `warlock.boon_instead_of()`, which turned out to be
    three gaps under one symbol.** That door landed: every payout offers
    itself as the clause `features.warlock.BOON`, and `f3444` trades the
    boon away through `c.pre_empt`. **This row cannot use it.** A
    substitution has to be registered *before* the event, and the only
    thing that registers before a fight is a trait -- `turns.arm_traits`
    arms `action=NONE` rows with no declared trigger and nothing else. This
    is a daily immediate reaction answering the very `Dropped` the boon
    pays on, which is the header the card prints, so there is no earlier
    moment to register from and no second block on this item to register
    from instead.

    What it wants is to **forgo** a payout that is firing beside it, which
    is `c.decline_boon()` -- `i2296x1` prints "instead of taking its normal
    benefit" and had already coined the symbol for exactly this. One
    symbol, one gap, so the two rows share it rather than this one riding a
    verb that cannot reach it. #641.
    """
    c.bonus("attack", 1, kind="power", on=c.me, until=When.ENCOUNTER, once=True)


@power(
    "i2312p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a divine attack power using this rod",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.DIVINE)), "you hit with a divine power"
    ),
)
def i2312p1(c: Cast) -> None:
    """A free action answering a hit already resolves after the triggering
    push, which is the printed ordering."""
    foe = _struck(c)
    if foe is None:
        return
    c.push(2, on=foe)
    c.prone(on=foe)


@power(
    "i2324x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("events.RowExpended",),
)
def i2324x1(c: Cast) -> None:
    """**Re-aimed: the feature is modelled, the moment is not announced.**

    `c.fell_might()` was the wrong symbol -- the boon's charge exists, as
    `c.spend_charge` on the key `features.warlock.FELL`, which is what
    `i2324p1` beside this now spends. What this row needs is the
    *announcement*: spending a charge emits a bare `Note`, which carries
    `text` and nothing else -- no actor, no ref -- so there is no event a
    trigger can read to know a charge went. Watching `i2324p1` instead
    would pay the temporary hit points on a use that found nothing to
    spend, since the row still resolves when the Requirement refuses it."""


@power(
    "i2324p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit an enemy with an arcane attack power using this rod",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.ARCANE)), "you hit with an arcane power"
    ),
)
def i2324p1(c: Cast) -> None:
    """**The cost is a charge, not the boon row's encounter use.**

    The first version spent `c.expend_row("cf:warlock-f1s4")` on the
    reasoning that "the boon is a declared row with `usage=ENCOUNTER`, so
    its charge *is* a use of the feature -- `features/warlock.py` says so
    outright". Both halves were wrong together: a trait's single use is
    spent by `turns.arm_traits` before round 1, so `c.expend_row` returned
    False for every warlock and **this row returned early every time it
    fired** -- inert in play, not merely missing a clause. It was the
    `features/warlock.py` note that was wrong, and it has been corrected.
    #529.

    `c.spend_charge(FELL)` is the cost. Its False is still the printed
    Requirement, which is why the row returns rather than paying the burn
    for free.

    Only the one leg's boon is named, because that is the only leg whose
    boon this card's wording can be spending.
    """
    if not c.spend_charge(FELL):
        return
    foe = _struck(c)
    if foe is not None:
        c.ongoing(
            2 * c.enhancement, DamageType.NECROTIC, on=foe, until=When.SAVE_ENDS
        )


@power(
    "i2335p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def i2335p1(c: Cast) -> None:
    """Finished: `c.slide` takes `toward=` now.

    The destination clause -- "to a space adjacent to one of your allies" --
    used to be dropped, because `to=` names one square outright and nothing
    narrowed the decider to a set of legal ones. `toward=` is that: the ally
    nearest the enemy is chosen and the slide walks the line at it, stopping
    at the last square it can legally enter, which is beside that ally when
    three squares reach and as near as they get when they do not.

    The nearest ally rather than a free choice, because the card says "one of
    your allies" and getting the enemy beside *somebody* is the point; the
    nearest is the one three squares is most likely to reach.
    """
    from combat_engine.engine.query import distance_between

    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is None:
        return
    mate = min(
        (a for a in c.allies() if a != c.me),
        key=lambda a: distance_between(c.world, foe, a),
        default=None,
    )
    c.slide(3, on=foe, toward=mate) if mate is not None else c.slide(3, on=foe)


@power(
    "i2339x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2339x1(c: Cast) -> None:
    """`c.element` is the reader that was missing: the breath's damage
    type is a build choice `chargen` records beside the leg, and `p1448`
    reads it the same way. A carrier whose build names no element gets
    nothing, which is the printed prerequisite rather than a silent row.
    "Using this implement" is armed always-on, as everywhere in this
    file -- the damage context does not carry the weapon."""
    breath = c.element()
    if breath is not None:
        c.deals(breath, on=c.me, until=When.ENCOUNTER, implement=True)


@power(
    "i2339p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a cursed target with an arcane power using this rod",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.ARCANE)), "you hit with an arcane power"
    ),
    dropped=("c.cast_from(ref=)", "c.add_target(pending=)"),
)
def i2339p1(c: Cast) -> None:
    """Re-aimed and written. `p1448` is declared, so the racial attack is
    no longer the hold, and "treat the affected creature as the origin
    square of the blast" is `c.cast_from` -- which is read in
    `dsl.measured_from`, so the borrowed square decides what may be aimed
    at as well as where the line is traced.

    Two clauses are dropped. `c.cast_from` is a standing change and takes
    no ref, so it moves the origin of every area attack the wielder makes
    in the window rather than only the breath's; and "the attack also
    targets the affected creature" has to be said about a use that has
    not begun -- `c.add_target` only reaches a power already running
    underneath this one."""
    foe = _struck(c)
    if foe is None or not c.cursed(on=foe):
        return
    c.cast_from(foe, on=c.me, until=When.EONT)


@power(
    "i2345x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2345x1(c: Cast) -> None:
    """A choice made when the item is acquired and never again: nothing
    happens on a board, so this is deliberately inert rather than
    unwritten."""


@power(
    "i2345p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.vestige()",),
)
def i2345p1(c: Cast) -> None:
    """Switching which of a warlock's vestiges is active is a class
    mechanic nothing models."""


@power(
    "i2348x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2348x1(c: Cast) -> None:
    """`c.curse` lands as a labelled effect, so `EffectApplied` is where
    "whenever you place a curse" is heard. `c.conceal` is handed the
    *attack* context, which carries `attacker` -- so "from the target"
    is a real gate and the concealment is not granted against the rest
    of the board."""

    def cursed(ev: EffectApplied) -> None:
        if ev.source != c.me or "curse" not in ev.label:
            return
        foe = ev.target
        c.conceal(
            on=c.me, until=When.EONT,
            when=lambda ctx, f=foe: ctx.get("attacker") == f,
        )

    c.watch(EffectApplied, cursed, until=When.ENCOUNTER)


@power(
    "i2489x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2489x1(c: Cast) -> None:
    """No type word on the card, so the +2 to AC is untyped."""

    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        who = c.choose([c.me, *c.within(5, side="ally")], "gains +2 AC")
        if who is not None:
            c.bonus(AC, 2, on=who, until=When.EONT)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2489p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i2489p1(c: Cast) -> None:
    """The whole printed Effect is p4133, declared and finished."""
    c.use_power("p4133", on=c.target, spend=False)


@power(
    "i2596p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy within 3 squares with a force attack",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.FORCE)), "you hit with a force attack"
    ),
    keywords=[Keyword.AUGMENTABLE],
)
def i2596p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None and c.distance(foe) > 3:
        return
    for enemy in c.within(1, side="enemy"):
        c.push(c.enhancement, on=enemy)
    if c.points_spent(c.ref) >= 1:
        c.resist(3 + c.wis_mod, on=c.me, until=When.EONT)


@power(
    "i2607x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2607x1(c: Cast) -> None:
    """`c.forces` lengthens pushes, pulls and slides alike; the card names
    only the first two, and the gate it offers carries `how` and `power`
    but not which the row means at write time."""
    c.forces(1, on=c.me, until=When.ENCOUNTER)


@power(
    "i2607p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a force attack using this staff",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.FORCE)), "you hit with a force attack"
    ),
)
def i2607p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.prone(on=foe)


@power(
    "i2610x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use cf:artificer-f2 on an ally",
    on=Trigger(PowerUsed, _used_by_me(*_INFUSIONS),
               "you use that class feature on an ally"),
)
def i2610x1(c: Cast) -> None:
    """The old note said the trigger was one named class feature nothing
    models. It is modelled: `cf:artificer-f2` is declared, a feat grants it,
    and its three cards -- `p4128`, `p7635`, `p10187` -- are all declared
    rows that announce a `PowerUsed`.

    All three, not the heal alone. The card says "your cf:artificer-f2 class
    feature", where the three feats riding on this feature elsewhere each
    name one of the cards; the feature itself is the budget row and is never
    used, so a use of it is a use of one of the three.

    `PowerUsed` because the targets are picked before the body runs, which
    is the one thing that event can be trusted for -- and nothing here reads
    what the infusion laid, which is the case that needs `PowerResolved`
    instead. "On an ally" needs no gate: all three declare `ONE_ALLY`.

    Resistance with no type named is resistance to all damage, the way
    `i2610p1` writes the same word."""
    for who in c.trigger.targets:
        c.resist(c.enhancement, on=who, until=When.EONT)


@power(
    "i2610p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def i2610p1(c: Cast) -> None:
    if c.target is not None:
        c.resist(c.wis_mod + c.enhancement, on=c.target, until=When.EONT)


@power(
    "i2612p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
)
def i2612p1(c: Cast) -> None:
    """**The old note was wrong that nothing on the board is lit or unlit,
    and wrong about both siblings it named.** The board has recorded
    lighting since #685/#686: `query.light_level` is the reader, a carried
    radius is a `light_radius` modifier, and `i1533p1` (above) and `i630p2`
    (below) each *lay* one.

    `c.total("light_radius")` rather than the literal, and read inside the
    handler rather than closed over: the card says "within the radius of
    the light", so a feat or a second source that widens the light widens
    the burn, and the two numbers cannot drift apart.

    **`query.light_level` is the wrong reader here**, which is worth saying
    because it is the obvious one. It answers `BRIGHT` for every square on
    a board nobody has darkened -- deliberately, so the attack path's light
    term costs nothing -- so a burn gated on "is this square lit" would
    cook every undead on every map. The question is the *radius*, not the
    level.

    The light itself is laid here. The printed Requirement is that the
    spell is on **this staff**, and a staff is carried, so the staff's
    light is a radius on the wielder -- `i1533p1`'s shape exactly. It is
    laid rather than read because `p1225` is declared `out_of_combat` with
    a `c.note` and sheds nothing; **if `p1225` is ever given its own
    `c.light`, this line must go**, since two carried radii add and the
    light would double.

    `ev.ghost` is skipped the way `m6367a0`'s own turn watcher skips it: a
    dead creature's turn is ticked so durations can reach their end, and
    nothing should be burned on it.
    """
    me = c.me
    # p1225's printed radius, which is the one thing about the spell this
    # card borrows.
    c.light(4, on=me, until=When.ENCOUNTER)
    burn = c.enhancement

    def dawn(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == me or not c.is_kind("undead", on=who):
            return
        radius = c.total("light_radius")
        if radius and c.distance(who) <= radius:
            c.flat(burn, dtype=DamageType.RADIANT, on=who)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} glare")


@power(
    "i2619x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2619x1(c: Cast) -> None:
    """Paragon numbers are out of scope; this is the heroic +1."""
    c.bonus("skill:arcana", 1, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i2619p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a psionic area or close attack using this staff",
    on=Trigger(AttackDeclared, _area_by_me, "you make a close or area attack"),
    keywords=[Keyword.AUGMENTABLE],
)
def i2619p1(c: Cast) -> None:
    """`c.widen_areas` grows the next burst rather than the one already
    declared, which is as close as the engine gets to enlarging an attack
    mid-flight. `c.restore_use` is the Augment's own line."""
    c.widen_areas(1, on=c.me, until=When.EONT)
    if c.points_spent(c.ref) >= 2:
        c.restore_use(c.ref, on=c.me)


@power(
    "i2620x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2620x1(c: Cast) -> None:
    c.bonus("skill:intimidate", 1, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i2620p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit an enemy with a psionic attack using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i2620p1(c: Cast) -> None:
    """"You can slide it" -- so the follow-up is offered, not forced."""
    foe = _struck(c)
    if foe is None:
        return
    c.slide(1, on=foe)

    def again(ev: DamageApplied) -> None:
        if ev.target == foe and c.may("slide it 1 square", who=c.me):
            c.slide(1, on=foe)

    c.watch(DamageApplied, again, until=When.EONT)


@power(
    "i2635x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("dsl._stretched(within=)",),
)
def i2635x1(c: Cast) -> None:
    """The ranged half is written; the area half is the dropped clause.

    **`todo` became `dropped`, and the symbol was re-aimed.** A ranged
    line's range really is reachable: `dsl.area_of` hands `_stretched` a
    context of `{"power": p.ref, "kind": r.kind}` and it reads
    `Mods.total("range", ctx)`, so a gated `c.bonus("range", ...)` is the
    printed sentence for every ranged arcane power.

    An **area** power is the half that is still missing, and the card's own
    worked example is exactly it -- the number that grows is the `within`
    an area burst may be placed at. `_stretched` deliberately does not
    touch that: for an area kind it reads `"blast_size"`, which is the
    burst's own radius, and growing that would widen the blast instead of
    reaching further. So the symbol is the missing parameter rather than a
    new mechanism.
    """
    c.bonus(
        "range", c.enhancement, on=c.me, until=When.ENCOUNTER,
        when=_has_keyword(Keyword.ARCANE),
    )


@power(
    "i2637p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    attack=Attack((INT, CHA), vs=FORT),
)
def i2637p1(c: Cast) -> None:
    """**Written: `Attack` holds two abilities after all.** Its `ability`
    takes a `tuple[Ability, ...]` and `Attack.ability_for` answers
    `max(..., key=stats.mod)`, so "Intelligence or Charisma" is the header
    and not a dropped clause. Best-of is the right resolution here because
    the choice is the user's at the moment of use -- unlike `p1448`, whose
    three abilities are bound once at character creation, which is why
    that row keeps its marker and this one does not."""
    if c.strike():
        c.push(c.enhancement)
        c.prone()


@power(
    "i2638p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with a cold attack using this staff",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.COLD)), "you hit with a cold attack"
    ),
)
def i2638p1(c: Cast) -> None:
    for enemy in c.within(3, side="enemy"):
        c.immobilized(on=enemy, until=When.SAVE_ENDS)


@power(
    "i2639x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2639x1(c: Cast) -> None:
    c.bonus("skill:perception", 1, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i2639p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
    keywords=[Keyword.AUGMENTABLE],
)
def i2639p1(c: Cast) -> None:
    """An interrupt resolves before the damage, so resistance laid here is
    in place for the blow that triggered it."""
    amount = 5 + c.enhancement
    c.resist(amount, on=c.me, until=When.SONT)
    if c.points_spent(c.ref) >= 1:
        for mate in c.within(1, side="ally"):
            c.resist(amount, on=mate, until=When.SONT)


@power(
    "i2652x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2652x1(c: Cast) -> None:
    c.bonus("skill:history", 1, kind="item", on=c.me, until=When.ENCOUNTER)


def _dazed_or_stunned_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and getattr(ev, "condition", None) in (
        Condition.DAZED,
        Condition.STUNNED,
    )


@power(
    "i2652p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you daze or stun an enemy with a psionic attack using this staff",
    on=Trigger(ConditionApplied, _dazed_or_stunned_by_me, "you daze or stun"),
)
def i2652p1(c: Cast) -> None:
    """`ConditionApplied` names its subject `target`, so the caster is
    `source` -- `about_me` would be false here forever."""
    pick = c.choose([MOVE, MINOR], "an extra action this turn")
    c.extra_action(pick or MOVE, on=c.me)


@power(
    "i2653p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a ranged attack using this staff",
    on=Trigger(
        AttackDeclared, both(by_me, by_ranged), "you make a ranged attack"
    ),
)
def i2653p1(c: Cast) -> None:
    """`c.cast_from` is exactly "determine line of sight and effect as
    though you were standing there"."""
    near = c.within(5, side="ally")
    if not near:
        return
    mate = c.choose(near, "the attack comes from here")
    if mate is not None:
        c.cast_from(mate, on=c.me, until=When.EOT)


@power(
    "i2756p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i2756p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None and "elemental" in c.kinds_of(on=foe):
        c.damage("1d10", on=foe)


@power(
    "i2782p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2782p1(c: Cast) -> None:
    """Two gated one-shots rather than one branch, because which die is
    rolled depends on a target that is not chosen yet. The dice come out
    now and the gates decide which one is read; they are mutually
    exclusive, so the pair cannot both land."""
    undead = _target_is(c, "undead", "immortal")
    c.bonus(
        "damage", c.roll("1d4"), on=c.me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: not undead(ctx),
    )
    c.bonus(
        "damage", c.roll("1d8"), on=c.me, until=When.ENCOUNTER, once=True,
        when=undead,
    )


@power(
    "i2801p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    todo=("by_ref()",),
)
def i2801p1(c: Cast) -> None:
    """Re-aimed. The class feature is not the hold: 115 rows carry
    `group="channel divinity"`, `c.expended(group=)` reads which are
    gone and `c.restore_use` hands one back, so "even if you have
    already used it this encounter" is sayable. What is missing is
    *which* row -- the spec names the one power in prose and prints no
    ref, and picking any channel-divinity row the bearer happens to own
    would be a different card."""


@power(
    "i2803p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i2803p1(c: Cast) -> None:
    """Both branches are written, and the old note's premise was false.

    It read "nothing keeps that history: the events are gone by the time
    this row is asked", and **the bus log keeps every event of the fight**.
    "Since the end of your last turn" is the `seq` of this creature's last
    `TurnEnd`, which makes the history a slice rather than something a
    component has to remember. See `query.since_turn_ended`. #757.

    **The bigger branch wins outright and the two do not add**: "you
    *instead* deal an extra 2d8" is one printed word doing that work, so a
    target that both hurt you and dropped you pays 2d8 and not 3d8.

    "You or an ally" on both branches, which `or_an_ally=` asks -- the
    allies are read now rather than remembered, the same simplification
    every other `query.allies` caller makes.

    **1d8 and 2d8, which is the heroic band and the whole of it.** The card
    prints "Level 14 or 19: 2d8" and "Level 24 or 29: 3d8" above the base,
    and those are paragon and epic -- out of this tier, so they are not
    written rather than guessed at. `c.w` is not the expression either:
    these are flat dice on a rider, not a weapon line."""
    foe = c.trigger.target if c.trigger is not None else None
    if foe is None:
        return
    if c.floored_me_since(foe, or_an_ally=True):
        c.flat(c.roll("2d8"), on=foe)
    elif c.hurt_me_since(foe, or_an_ally=True):
        c.flat(c.roll("1d8"), on=foe)


@power(
    "i2811x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2811x1(c: Cast) -> None:
    """The spec prints `p1455`. `PowerUsed` is safe to read here -- the
    rider turns on the declaration and not on anything that row's body
    does. "During a combat encounter" is every moment this trait is
    armed, so it is not a second gate."""

    def used(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != "p1455":
            return
        amount = c.cha_mod + c.enhancement
        for who in (c.me, *c.within(5, side="ally")):
            c.temp_hp(amount, on=who)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power(
    "i2879p1",
    level=4,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you make a melee attack using this ki focus",
    on=Trigger(AttackDeclared, both(by_me, by_melee), "you swing in melee"),
)
def i2879p1(c: Cast) -> None:
    c.deals(DamageType.THUNDER, on=c.me, until=When.EOT, implement=True)


@power(
    "i2879p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you make a melee attack using this ki focus",
    on=Trigger(AttackDeclared, both(by_me, by_melee), "you swing in melee"),
)
def i2879p2(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    best = max(
        c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod
    )
    for other in c.within(1, of=foe):
        if other == foe or other == c.me:
            continue
        c.flat(best, dtype=DamageType.THUNDER, on=other)
        c.condition(Condition.DEAFENED, on=other, until=When.SAVE_ENDS)


@power(
    "i2894x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2894x1(c: Cast) -> None:
    """`ConditionApplied` names the caster `source` and the victim
    `target`, which is why this reads `source` rather than using
    `about_me`."""

    def pinned(ev: ConditionApplied) -> None:
        if ev.source == c.me and ev.condition == Condition.IMMOBILIZED:
            c.flat(c.con_mod, on=ev.target)

    c.watch(ConditionApplied, pinned, until=When.ENCOUNTER)


@power(
    "i2894p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use a wizard summoning power",
    # `about_me`, not `by_me`: `Summoned` names its subject `actor`,
    # and `by_me` reads `attacker`/`source` -- false here forever.
    on=Trigger(Summoned, about_me, "you summon a creature"),
)
def i2894p1(c: Cast) -> None:
    """`MoveStart` is the right half of the shift, not `MoveEnd`: by the
    end the shifter has left and the adjacency the row measures is already
    false. It is also the window an opportunity attack belongs in."""
    pet = getattr(c.trigger, "summon", None)
    if pet is None:
        return

    def shifted(ev: MoveStart) -> None:
        if ev.actor == pet or getattr(ev, "kind_", "") != "shift":
            return
        if c.adjacent_to(pet, ev.actor):
            c.provoke(pet, on=ev.actor, why="shifted away from the summon")

    c.watch(MoveStart, shifted, until=When.ENCOUNTER)


@power(
    "i2898x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2898x1(c: Cast) -> None:
    """The crit range works.

    **Marker removed, as `i2717x1`.** The second paragraph describes what
    the tome holds; the one moment a fight reaches those powers is
    `i2898p1`, which `_tome_trade` already writes. Choosing them at
    acquisition and adding them to a spellbook both happen before a
    board."""
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=_has_keyword(Keyword.LIGHTNING),
    )


@power(
    "i2898p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i2898p1(c: Cast) -> None:
    """Re-aimed and written. `c.borrow_row` is the verb for exactly this
    shape -- the card names a *set* and asks the character to take one of
    it -- and it reads the set off the registry by class, level and
    usage, which is where the tome's two powers would have been chosen
    from. `uses=1` is the printed "during this encounter".

    **The price is charged now, and the old marker was wrong about why it
    could not be.** It asked for `c.expend_row(among=)` on the reading
    that nothing lists the bearer's unspent powers;
    `implement_c._spend_unused` had listed them since `i744p1` was
    written, and six sibling rows paid with it. `c.unspent` is where that
    read lives now, and `_tome_trade` is the whole sentence. The printed
    clause says *attack* power and nothing about daily, so the price
    takes no usage.

    The borrowable set is empty in the tree today -- the only wizard daily
    lightning power declared is level 5 and this tome is level 4 -- so the
    row is quiet until one is written. That is a content gap and not a
    hole in the row: it fills itself the day the power lands. **This row
    is why `_tome_trade` charges nothing when it lends nothing**: with the
    price as a separate statement, a bearer using the tome today paid a
    wizard attack power for an empty set."""
    _tome_trade(c, 4, Keyword.LIGHTNING)


@power(
    "i2912x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.worsen_save()",),
)
def i2912x1(c: Cast) -> None:
    """`EffectApplied` fires for a hold carrying nothing but a burn, which
    is the only announcement an ongoing-damage effect makes. What is
    dropped is the narrowing: the penalty cannot be hung on the one
    effect, so it sits on the creature's saving throws generally, and
    `EffectApplied` does not say the burn was fire."""

    def burning(ev: EffectApplied) -> None:
        if ev.source != c.me or not ev.save_ends:
            return
        if not ev.label.startswith("ongoing"):
            return
        c.penalty("save", c.enhancement, on=ev.target, until=When.SAVE_ENDS)

    c.watch(EffectApplied, burning, until=When.ENCOUNTER)


@power(
    "i3017x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3017x1(c: Cast) -> None:
    """**Both halves written: the range was reachable all along.**

    `dsl.area_of` measures a row's range through `dsl._stretched`, which
    reads `Mods.total("range", ctx)` with `ctx = {"power": p.ref, "kind":
    r.kind}` -- so a gated `c.bonus("range", ...)` lengthens exactly the
    rows the card names and nothing else. The marker's claim that a range
    is a header field nothing reaches was false.

    The gate asks only the keyword. It needs no test for a ranged line:
    `_stretched` reads the `"range"` key **only** on a ranged kind -- a
    blast or a burst reads `"blast_size"` instead -- so the modifier is
    unreachable from anything else by construction. `Level 14:`/`24:` are
    paragon and out of scope, so the printed heroic 2 is the number.
    """
    c.bonus(
        "range", 2, on=c.me, until=When.ENCOUNTER,
        when=_has_keyword(Keyword.CHARM),
    )
    c.ignore_cover(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("ranged"))
        and Keyword.CHARM in _keywords_of(ctx),
    )


@power(
    "i3017p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT],
)
def i3017p1(c: Cast) -> None:
    """The whole printed Effect is p2346, declared and finished. The
    range is that row's 5, not the 10 this header guessed."""
    c.use_power("p2346", on=c.target, spend=False)


@power(
    "i3075x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3075x1(c: Cast) -> None:
    """The save context carries the burn's damage type, so "against
    ongoing fire damage" narrows: `dtype` is set only for an effect that
    burns. No type word on the card, so untyped."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx["dtype"] is DamageType.FIRE)


@power(
    "i3075p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    trigger="you hit an enemy with a primal fire power using this totem",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.FIRE)), "you hit with a fire power"
    ),
)
def i3075p1(c: Cast) -> None:
    for enemy in c.within(1, side="enemy"):
        c.ongoing(5, DamageType.FIRE, on=enemy, until=When.SAVE_ENDS)


@power(
    "i3086p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal attack power using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i3086p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.weakened(on=foe, until=When.EONT)


@power(
    "i3089p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal cold power and deal damage to it",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.COLD)), "you hit with a cold power"
    ),
)
def i3089p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.vulnerable(3, DamageType.COLD, on=foe, until=When.EONT)


@power(
    "i3169x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3169x1(c: Cast) -> None:
    """Both halves are gated on the victim's type words now.

    **The forced-movement half was a bug rather than a gap.** The square was
    being laid unconditionally, because the shove's context carried `how` and
    `power` and never said who was being moved -- so an extra square printed
    for undead lengthened every push, pull and slide the character made.
    Written, firing, and stronger than print, which is the shape this project
    treats as worse than an absent row. #748 put `target` in that context and
    the same `_target_is` helper the damage half already used does the rest.

    One helper for both clauses deliberately: it is the same printed word
    about the same creature, and the two contexts spell the victim the same
    way now."""
    undead = _target_is(c, "undead")
    c.forces(1, on=c.me, until=When.ENCOUNTER, when=undead)
    c.bonus(
        "damage", 2, kind="item", on=c.me, until=When.ENCOUNTER,
        when=undead,
    )


@power(
    "i3170x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3170x1(c: Cast) -> None:
    """Written, and the marker was stale rather than waiting. It asked for
    `c.deals(only_untyped=)`; "unless the damage already has a type" **is**
    `from_=DamageType.UNTYPED`, which has existed since #613 -- its own
    docstring calls that case out by name, as "the narrow behaviour this
    method used to have by accident". Nothing needed building.

    Found while landing three other narrowings on the same verb (#711),
    which is the argument for reading a verb's whole signature rather than
    the parameter a marker happens to name."""
    c.deals(
        DamageType.FIRE, on=c.me, until=When.ENCOUNTER, implement=True,
        from_=DamageType.UNTYPED,
    )


@power(
    "i3170p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def i3170p1(c: Cast) -> None:
    """The grab is read both ways round, because the card is: whoever is
    holding whom, the burn is on the other one's turn."""
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    c.vulnerable(5, DamageType.COLD, on=c.me, until=When.ENCOUNTER)

    def burn(ev: TurnStart) -> None:
        who = ev.actor
        if who == c.me:
            return
        if who in c.grabbing(of=c.me) or c.me in c.grabbing(of=who):
            c.flat(5, dtype=DamageType.FIRE, on=who)

    c.watch(TurnStart, burn, until=When.ENCOUNTER)


@power(
    "i3175x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3175x1(c: Cast) -> None:
    c.bonus("skill:insight", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i3175p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit a target with an attack using this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
)
def i3175p1(c: Cast) -> None:
    """"During which it hit you or one of your allies" is a fact about a
    whole turn, so a flag is set on the hit and read at the turn's end.

    Three watches hold the power up and all three have to go together, so
    the first is the one made `c.endable` and its deliberate end takes the
    other two with it."""
    foe = _struck(c)
    if foe is None:
        return
    swung: list[int] = []

    def hit_us(ev: Hit) -> None:
        if ev.attacker == foe and (ev.target == c.me or ev.target in c.allies()):
            swung.append(1)

    def turn_over(ev: TurnEnd) -> None:
        if ev.actor != foe or not swung:
            return
        swung.clear()
        c.flat(2 + c.enhancement, dtype=DamageType.PSYCHIC, on=foe)

    def fell(ev: Dropped) -> None:
        if ev.actor == foe:
            c.spend_surge(on=c.me)

    holds = [
        c.watch(Hit, hit_us, until=When.ENCOUNTER),
        c.watch(TurnEnd, turn_over, until=When.ENCOUNTER),
        c.watch(Dropped, fell, until=When.ENCOUNTER),
    ]

    def dismiss() -> None:
        for hold in holds[1:]:
            c.end_effect(hold)

    c.endable(holds[0], then=dismiss)


@power(
    "i3178p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a creature with an active aura using this rod",
    on=Trigger(Hit, by_me, "you hit with this rod"),
    dropped=("c.suppress_aura()",),
)
def i3178p1(c: Cast) -> None:
    """`c.dispel` takes the aura off the board and `c.made_by` says whose
    it was. Stopping it coming back is the dropped clause -- nothing bars
    a creature from re-arming what it owns."""
    foe = _struck(c)
    if foe is None:
        return
    for thing in c.conjurations():
        if c.made_by(thing) == foe:
            c.dispel(thing)


@power(
    "i3178p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are targeted by a close or an area attack power",
    on=Trigger(AttackDeclared, _area_at_me, "a close or area attack targets you"),
)
def i3178p2(c: Cast) -> None:
    """"All of the power's attack rolls" is the gate: the penalty is hung
    on the ref rather than on the one roll being answered, so the rest of
    the burst takes it too."""
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    ref = getattr(ev, "power", "")
    if attacker is None or not ref:
        return
    c.penalty(
        "attack", 5, on=attacker, until=When.EOT,
        when=lambda ctx: ctx.get("power") == ref,
    )


@power(
    "i3184x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3184x1(c: Cast) -> None:
    c.bonus(
        "skill:diplomacy", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i3184p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with a charm power using this staff",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.CHARM)), "you hit with a charm power"
    ),
)
def i3184p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.slide(c.enhancement, on=foe)
    c.grants_advantage(on=foe, until=When.EONT)


@power(
    "i3185p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an adjacent creature with an attack using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i3185p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None or not c.adjacent(to=foe):
        return
    c.push(1, on=foe)
    c.prone(on=foe)


@power(
    "i3199x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3199x1(c: Cast) -> None:
    c.resist(3 + 2 * c.enhancement, DamageType.COLD, on=c.me, until=When.ENCOUNTER)


@power(
    "i3199p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with a cold attack using this wand",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.COLD)), "you hit with a cold attack"
    ),
)
def i3199p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.immobilized(on=foe, until=When.SAVE_ENDS)


@power(
    "i3199p2",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.water()",),
)
def i3199p2(c: Cast) -> None:
    """The whole row measures a body of water: which squares are liquid,
    how many are contiguous, and which of them are empty. The map has no
    such feature, and `c.terrain` answers only what sort of place the
    fight is in."""


@power(
    "i3431x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3431x1(c: Cast) -> None:
    """Three printed clauses, all sayable: two skill modifiers, an attack
    bonus gated on the victim's type words, and a rider read off the
    damage that crossed the halfway line."""
    c.bonus("skill:arcana", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)
    c.bonus(
        "skill:religion", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )
    c.bonus(
        "attack", 2, kind="item", on=c.me, until=When.ENCOUNTER,
        when=_target_is(c, "elemental"),
    )

    def on_blood(ev: DamageApplied) -> None:
        if ev.source != c.me or not _just_bloodied(c, ev):
            return
        if "elemental" not in c.kinds_of(on=ev.target):
            return
        c.flat(2 * c.enhancement, dtype=DamageType.RADIANT, on=ev.target)

    c.watch(DamageApplied, on_blood, until=When.ENCOUNTER)


@power(
    "i3432x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your second wind",
    on=Trigger(SecondWind, about_me, "you use your second wind"),
)
def i3432x1(c: Cast) -> None:
    """"Using this ki focus" is the implement keyword: one focus is held
    at a time. The extra damage is cold and carries that type."""
    c.bonus("damage", c.enhancement, on=c.me, until=When.EONT,
            dtype=DamageType.COLD,
            when=_has_keyword(Keyword.IMPLEMENT))


@power(
    "i3432p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    trigger="you hit an adjacent enemy with an attack using this ki focus",
    on=Trigger(Hit, by_me, "you hit with this ki focus"),
)
def i3432p1(c: Cast) -> None:
    """"Until it takes damage" is `c.cure` on a damage watch; the extra
    cold is a second watch with the shorter duration, because only that
    half stops at the end of your next turn. "Until it uses a standard
    action to end this effect" is `c.endable`, and it is the target who is
    offered the drop because the hold sits on the target."""
    foe = _struck(c)
    if foe is None or not c.adjacent(to=foe):
        return
    c.endable(
        c.immobilized(on=foe, until=When.ENCOUNTER), ActionType.STANDARD
    )
    freed: list[int] = []
    paid: list[int] = []

    def release(ev: DamageApplied) -> None:
        if freed or ev.target != foe:
            return
        freed.append(1)
        c.cure(Condition.IMMOBILIZED, on=foe)

    def bite(ev: DamageApplied) -> None:
        if paid or ev.target != foe:
            return
        paid.append(1)
        c.flat(3 + c.enhancement, dtype=DamageType.COLD, on=foe)

    c.watch(DamageApplied, release, until=When.ENCOUNTER)
    c.watch(DamageApplied, bite, until=When.EONT)


@power(
    "i3524p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3524p1(c: Cast) -> None:
    """`c.spend_surge` is a surge gone for nothing, which is the printed
    cost -- `c.surge` would heal, and this does not."""
    c.spend_surge(on=c.me)
    c.bonus(
        "damage", 2 * c.enhancement, kind="power", on=c.me, until=When.EONT
    )


@power(
    "i442x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i442x1(c: Cast) -> None:
    """"Melee basic attack" is askable after all: `Powers.basic` is what
    that creature's basic attack actually is -- `"mba"` for a character,
    one of its own abilities for a monster -- so the ref is compared
    against that rather than against every melee row. The reach is still
    asked, because `Powers.basic` also answers for the ranged swing."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        mine = c.world.get(c.me, Powers)
        if ev.power != (mine.basic if mine is not None else "mba"):
            return
        p = get(ev.power)
        if p is None or p.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        if c.may("slide the target 1 square", who=c.me):
            c.slide(1, on=ev.target)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i442p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i442p1(c: Cast) -> None:
    """The enemy's landing square has to be next to where you end up, so
    your own hop resolves first and the free squares beside it are what is
    offered to `to=`."""
    foe = _struck(c)
    if foe is None:
        return
    c.teleport(5)
    beside = [sq for sq in spread({c.here}, 1) if sq != c.here and not c.in_squares([sq])]
    if beside:
        c.teleport(5, who=foe, to=beside[0])


@power(
    "i563p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.TELEPORTATION],
    trigger="you hit an enemy with a primal attack power using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i563p1(c: Cast) -> None:
    """"Neither line of sight nor line of effect to anything, and nothing
    to the ally" is `Condition.REMOVED` -- off the board and back at the
    start of its own next turn. "Can" -- so it is offered."""
    near = c.within(5, side="ally")
    if not near:
        return
    mate = c.choose(near, "regains hit points")
    if mate is None:
        return
    c.heal(2 * c.enhancement, on=mate)
    if c.may("vanish to a place of safety", who=mate):
        c.condition(Condition.REMOVED, on=mate, until=When.SOTNT)


@power(
    "i612x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i612x1(c: Cast) -> None:
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "i612p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with a melee attack using this staff",
    on=Trigger(Miss, both(by_me, by_melee), "you miss in melee"),
)
def i612p1(c: Cast) -> None:
    """`keep="new"` is the printed "even if it is lower"; `"best"` would
    be the other, kinder row."""
    c.reroll_attack(keep="new")


@power(
    "i630p1",
    level=4,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i630p1(c: Cast) -> None:
    """The whole printed Effect is a lamp. Deliberately inert."""


@power(
    "i630p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a fire or radiant attack",
    on=Trigger(
        Hit,
        both(by_me, either(by_keyword(Keyword.FIRE), by_keyword(Keyword.RADIANT))),
        "you hit with fire or radiant",
    ),
)
def i630p2(c: Cast) -> None:
    """Combat advantage is the half with teeth. The light is carried by the
    creature that was hit, out to 20 squares, and is clocked on the same save
    -- a target that shakes the effect stops glowing with it."""
    foe = _struck(c)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.SAVE_ENDS, to="team")
        c.light(20, on=foe, until=When.SAVE_ENDS)


@power(
    "i698x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("warlock.pay_boon()",),
)
def i698x1(c: Cast) -> None:
    """Adds a second trigger to a class feature that is fully modelled.

    **Re-pointed off `warlock.boon_instead_of()`, which was two gaps under
    one symbol.** That door landed -- each payout offers itself as the
    clause `features.warlock.BOON` and `f3444` trades the boon away through
    it -- and it does nothing for this row. A substitution replaces a
    payout that is already firing; this card asks for the payout to fire on
    an event it would not otherwise answer, which is the opposite
    direction.

    So: **the boon's payout has to be callable.** Three of the five refs in
    `features.warlock.BOONS` are rows, which `c.use_power` would reach, but
    `cf:warlock-f1` pays its three legs inline inside the watcher it
    installs -- using that row again installs a second watcher and pays
    nothing. The door is a helper in `features/warlock.py` paying whichever
    leg the character took, and it has to reach the payouts in
    `features/strikers.py` and `powers/warlock/pacts.py` to be true for
    every pact.

    `f2759` is the same gap and carries the same symbol -- it takes the
    boon early off `Bloodied` where this one adds `Bloodied` as a second
    trigger. #641.
    """


@power(
    "i719x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i719x1(c: Cast) -> None:
    """The damage context carries `target`, so "against a bloodied enemy"
    is a real gate even though "using this ki focus" is not."""
    c.bonus(
        "damage", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and c.bloodied(on=ctx["target"]),
    )


# -- level 5 ----------------------------------------------------------------


@power(
    "i1076x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.min_die()",),
)
def i1076x1(c: Cast) -> None:
    """**The premise was wrong; the symbol is still right.**

    The old note said the dice are gone by the time anything can look at
    them. They are not: `Cast._roll_damage` has them in hand, which is
    where `c.maximise` and `c.reroll_ones` are both read, and
    `_rolled_above` already works per die rather than per expression.

    But `c.reroll_ones(below=3)` is not this card. `_rolled_above`
    **rerolls** each low die until it is not low -- its own docstring says
    "until it shows a different number" -- where this card *sets* the die
    to 3. On a d6 that is an average of 4.5 against a flat 3, so writing
    the row with the existing verb would be a stronger item than the
    printed one. What is missing is a floor that replaces rather than
    rerolls, which is what `c.min_die()` names."""


@power(
    "i1511x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1511x1(c: Cast) -> None:
    c.bonus("skill:intimidate", 3, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i1511p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
)
def i1511p1(c: Cast) -> None:
    """Both halves now: the ally pays a surge and the wielder gets the
    points. `c.regain_points` is the payout -- it defaults to the caster
    and caps at the pool's maximum, which is what a *regain* means.

    The ally pays first and the points follow only if they did, because
    `c.spend_surge` returns False for an ally with none left and the card
    is one sentence: no surge, no points.

    The paragon and epic lines are out of scope, as every item's are.
    """
    if c.target is None or not c.spend_surge(on=c.target):
        return
    c.regain_points(2)


@power(
    "i1650x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1650x1(c: Cast) -> None:
    """The resist context is the one damage-side context that carries
    `source`, which is what "resistance to *that target's* attacks" needs
    -- the damage-bonus context does not, and this would be silently false
    written there."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        foe = ev.target
        c.resist(
            2 + c.enhancement, on=c.me, until=When.EONT,
            when=lambda ctx, f=foe: ctx.get("source") == f,
        )

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1966p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.augment_free()",),
)
def i1966p1(c: Cast) -> None:
    """Paying for an augment with something other than power points has no
    door: `c.spend_points` is the only way a row is augmented."""


@power(
    "i1978p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with an attack made with this orb",
    on=Trigger(Hit, by_me, "you hit with this orb"),
)
def i1978p1(c: Cast) -> None:
    """"Each bloodied creature" is everybody, not only enemies."""
    for who in c.within(5):
        if who != c.me and c.bloodied(on=who):
            c.damage("1d8", on=who)


@power(
    "i1980p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.store_points()",),
)
def i1980p1(c: Cast) -> None:
    """An item that holds power points is a pool the engine does not have;
    `c.points` is the creature's and there is nowhere else to put any."""


@power(
    "i1980p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.store_points()",),
)
def i1980p2(c: Cast) -> None:
    """Spends out of the store the item cannot hold."""


@power(
    "i1987p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with an augmented attack power using this orb",
    on=Trigger(Miss, by_me, "you miss with this orb"),
)
def i1987p1(c: Cast) -> None:
    """"The power points you spent to augment the power" is this use's
    number, so `c.augmented` and **not** `c.points_spent`.

    The two differ exactly here: `c.points_spent` is the encounter's
    running total for a row, so a second miss would hand back everything
    spent on every earlier use as well. `c.augmented` is what bought the
    latest use, which is the one that just missed.

    The ref comes off the trigger rather than from `c.ref` -- the row that
    missed is the augmented attack, not this orb.
    """
    missed = getattr(c.trigger, "power", "")
    if missed:
        c.regain_points(c.augmented(missed))


@power(
    "i2002p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a nonminion enemy with an at-will arcane attack power",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.ARCANE)), "you hit with an arcane power"
    ),
)
def i2002p1(c: Cast) -> None:
    """`reentrant=True` is exactly "repeat the attack": the row being
    granted is the very one this is answering, so the in-flight guard and
    the usage limit both have to stand aside. A minion's card is one hit
    point, which is the only thing that marks one."""
    ev = c.trigger
    foe = getattr(ev, "target", None)
    ref = getattr(ev, "power", "")
    if foe is None or not ref:
        return
    p = get(ref)
    if p is None or p.usage != Usage.AT_WILL or not _nonminion(c, foe):
        return
    others = [e for e in c.enemies() if e != foe and _nonminion(c, e)]
    if not others:
        return
    pick = c.choose(others, "repeat the attack against")
    if pick is not None:
        c.grant_attack(c.me, on=pick, ref=ref, reentrant=True)


@power(
    "i2110p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def i2110p1(c: Cast) -> None:
    if c.target is not None:
        c.heal(c.roll(f"{max(1, c.enhancement)}d6"), on=c.target)


@power(
    "i2319x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2319x1(c: Cast) -> None:
    """`c.curse` lands as a labelled effect, which is what announces the
    curse being placed."""

    def cursed(ev: EffectApplied) -> None:
        if ev.source != c.me or "curse" not in ev.label:
            return
        if _nonminion(c, ev.target):
            c.flat(c.enhancement, on=ev.target)

    c.watch(EffectApplied, cursed, until=When.ENCOUNTER)


@power(
    "i2592x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2592x1(c: Cast) -> None:
    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        near = c.within(5, side="ally")
        pick = c.choose(near, "regains hit points") if near else None
        if pick is not None:
            c.heal(2 * c.enhancement, on=pick)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2592p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you hit an enemy with a primal attack power using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i2592p1(c: Cast) -> None:
    near = c.within(5, side="ally")
    if not near:
        return
    pick = c.choose(near, "gains regeneration")
    if pick is not None:
        c.regeneration(2 * c.enhancement, on=pick, until=When.ENCOUNTER)


@power(
    "i2597p1",
    level=5,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with an implement power using this staff",
    on=Trigger(Hit, by_me, "you hit with this staff"),
)
def i2597p1(c: Cast) -> None:
    """A summoned creature is bound to its summoner, so `c.servants` is
    the set the printed line names."""
    for pet in c.servants():
        c.bonus("attack", 2, on=pet, until=When.EONT)
        c.bonus("damage", 2, on=pet, until=When.EONT)


@power(
    "i2602p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    trigger="you use a power with the fire keyword",
    on=Trigger(
        PowerResolved, _resolved_by_me(Keyword.FIRE), "a fire power of yours resolves"
    ),
)
def i2602p1(c: Cast) -> None:
    """"After resolving the attack" is `PowerResolved` and not
    `PowerUsed`: the latter announces before the body runs, so the burst
    would land first. A close burst 1 catches allies too."""
    c.resist(10, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    for who in c.within(1):
        if who != c.me:
            c.damage("1d8", dtype=DamageType.FIRE, on=who)


@power(
    "i2624p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC, Keyword.AUGMENTABLE],
    trigger="you hit an enemy with a psychic or a radiant attack",
    on=Trigger(
        Hit,
        both(by_me, either(by_keyword(Keyword.PSYCHIC), by_keyword(Keyword.RADIANT))),
        "you hit with psychic or radiant",
    ),
)
def i2624p1(c: Cast) -> None:
    """The Augment grows the burst, which the header cannot do at run
    time, so the reach is measured in the body instead."""
    radius = 2 if c.points_spent(c.ref) >= 1 else 1
    for enemy in c.within(radius, side="enemy"):
        c.vulnerable(5, DamageType.PSYCHIC, on=enemy, until=When.SAVE_ENDS)


@power(
    "i2629p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    trigger="you use a power with the lightning or the thunder keyword",
    on=Trigger(
        PowerResolved,
        _resolved_by_me(Keyword.LIGHTNING, Keyword.THUNDER),
        "a lightning or thunder power of yours resolves",
    ),
)
def i2629p1(c: Cast) -> None:
    """One 1d8 that is lightning *and* thunder, not two rolls. "Every
    creature" includes allies. A free action answering a trigger is not
    aimed anywhere, so `c.area` can come back empty and the blast is
    measured from the wielder instead."""
    area = c.area() or spread({c.here}, 3)
    for who in c.in_squares(area):
        if who != c.me:
            c.damage(
                "1d8", dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=who
            )


@power(
    "i2649p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with an augmented psionic attack power",
    on=Trigger(Hit, by_me, "you hit with an attack"),
)
def i2649p1(c: Cast) -> None:
    """`c.regain_points` is the payout, and it exists now.

    The printed trigger says *augmented psionic*; the declared one is a
    plain hit of the wielder's, so the augmented half is read in the body
    off the row that hit. An unaugmented hit regains nothing, which is the
    Requirement.
    """
    hit_with = getattr(c.trigger, "power", "")
    if hit_with and c.augmented(hit_with):
        c.regain_points(2)


@power(
    "i2654x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.shift_as_teleport()",),
)
def i2654x1(c: Cast) -> None:
    """"Instead" means the shift never happens, and only an interrupt can
    stop a move -- a trait cannot, and a reaction on `MoveEnd` arrives
    after the creature has already walked."""


@power(
    "i2654p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="you teleport using a psionic teleportation power",
    on=Trigger(Moved, _my_teleport, "you teleport"),
)
def i2654p1(c: Cast) -> None:
    """`Moved` is the only one of the three move events that carries both
    ends of the step, which is what "the same number of squares" needs."""
    ev = c.trigger
    start = getattr(ev, "from_", None)
    end = getattr(ev, "to", None)
    if start is None or end is None:
        return
    squares = max(0, len(c.line(start, end)) - 1)
    if squares:
        c.teleport(squares)


@power(
    "i2717x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2717x1(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; it rides as a plain attribute
    set afterwards, so it is read with `getattr`.

    **Marker removed: the second paragraph is not a missing clause.** It
    says what the tome *contains* -- two dailies at or below its level,
    chosen when it is acquired, addable to the spellbook. The only thing a
    fight does with them is `i2717p1`, which is "you gain the use of the
    chosen power during this encounter", and that is written: `_tome_trade`
    walks the ladder from the tome's rung down through `c.borrow_row`. The
    choice itself happens before any board exists and the spellbook line is
    chargen's; there is no round in which this property owes anything
    further."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me or not getattr(ev, "opportunity", False):
            return
        p = get(ev.power)
        if p is None:
            return
        if not ({Keyword.CONJURATION, Keyword.SUMMONING} & set(p.keywords)):
            return
        c.flat(c.enhancement, on=ev.target)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i2717p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.SUMMONING],
)
def i2717p1(c: Cast) -> None:
    """Re-aimed and written, as `i2898p1`: `c.borrow_row` enumerates the
    set the tome would have been stocked from.

    **The price is charged now.** It was the dropped clause, on the reading
    that nothing enumerates the bearer's unspent powers -- and
    `implement_c._spend_unused` did, off `Powers.all`. `c.unspent` is where
    that read lives now, and `_tome_trade` is the whole sentence.

    No wizard daily summoning power at or below level 5 is declared yet, so
    the borrowable set is empty and the row is quiet until one lands. That
    is a gap in the powers rather than in this row.

    **This docstring used to argue for the order that broke it**, and the
    correction is worth leaving visible: it said the price was charged
    first so that "a bearer with nothing to borrow should not be charged",
    which is exactly backwards -- charging first is what charges them.
    With an empty borrowable set, every use of this tome spent one of the
    character's attack powers and handed back nothing. `_tome_trade`
    charges inside the rung walk, so no card lent means no price paid."""
    _tome_trade(c, 5, Keyword.SUMMONING)


@power(
    "i2724x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2724x1(c: Cast) -> None:
    """The damage context carries `dtype`, so "a power that deals radiant
    or fire damage" is asked of the damage itself rather than of the
    power's keywords -- which is the printed wording."""
    c.bonus(
        "damage", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
        when=_of_type(DamageType.RADIANT, DamageType.FIRE),
    )


@power(
    "i2724p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    trigger="you hit an enemy with a primal daily attack power using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i2724p1(c: Cast) -> None:
    """One burn of two types, not two burns -- so one number a turn and
    one saving throw, which is what `dtypes=` says."""
    foe = _struck(c)
    if foe is None:
        return
    c.blinded(on=foe, until=When.SAVE_ENDS)
    c.ongoing(
        2 * c.enhancement, dtypes=(DamageType.FIRE, DamageType.RADIANT),
        on=foe, until=When.SAVE_ENDS,
    )


@power(
    "i2757p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=Trigger(Hit, by_me, "you hit with this holy symbol"),
)
def i2757p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.damage("1d10", on=foe)


@power(
    "i2765x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2765x1(c: Cast) -> None:
    """`by_action_point` rides on all four attack events, so "spends an
    action point to make an attack" is one question at declaration time --
    early enough for the damage bonus to be in place. No type word on the
    card, so untyped."""

    def bought(ev: AttackDeclared) -> None:
        who = ev.attacker
        if who == c.me or who not in c.within(5, side="ally"):
            return
        if not by_action_point(c.world, c.me, ev):
            return
        c.bonus("damage", c.enhancement, on=who, until=When.EOT, once=True)

    c.watch(AttackDeclared, bought, until=When.ENCOUNTER)


@power(
    "i2768x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2768x1(c: Cast) -> None:
    """`c.marked` is relational and defaults to "by you", which is the
    printed narrowing. No type word, so untyped."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and c.marked(on=ctx["target"]),
    )


@power(
    "i2796p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you fail your first saving throw against an effect",
    on=Trigger(
        SavingThrow,
        lambda w, me, ev: getattr(ev, "actor", None) == me
        and not getattr(ev, "saved", True),
        "you fail a saving throw",
    ),
)
def i2796p1(c: Cast) -> None:
    """The trigger is real now -- `SavingThrow` carries `actor`, `saved`
    and `against`, the label of the effect being rolled against, and a
    once-per-encounter row answering a failure is the printed "first"
    closely enough.

    **The payout is written, and both halves of the old note were wrong.**

    *Aiming at the hold that was failed.* `against` is not a bare label:
    `durations.save` sets it to `str(eff)`, which opens with the effect's
    own id, so the hold is findable again and the window is early enough
    that it is still live. `feats.paladin._shaken_off` is that read and is
    imported rather than copied -- one parser for one format.

    *Lifting it without ending it.* `Effects.suspend`/`resume` is the pair
    and `c.suspend_effect` was the wrong thing to wait for; `p16414` is the
    same operation written out and its docstring argues the verb choice.
    `c.end_effect` would be wrong twice here: the card says the effect
    comes back, and ending a save-ends hold would stop it owing the throws
    it still owes. A suspended effect keeps being saved against -- nothing
    in `durations` skips one -- which is what makes the suppression a
    reprieve rather than a cure.

    The resumption hangs on a bookkeeping hold clocked at the printed
    moment, `p16414`'s shape. A hold that ended on its own in the meantime
    is skipped by `resume`, which refuses an ended effect.

    The second printed sentence -- a changing effect not counting as the
    first failure -- is the card narrowing which throw triggers this, and
    `usage=ENCOUNTER` is already stricter than it: one firing a fight,
    whatever changes.
    """
    hold = _shaken_off(c, getattr(c.trigger, "against", "") or "")
    if hold is None:
        return
    if not c.world.effects.suspend(hold, f"{c.ref} shrugged it off"):
        return
    clock = c.world.effects.apply(c.me, c.me, When.EONT, label=f"{c.ref} respite")
    clock.on_end.append(lambda: c.world.effects.resume(hold))


@power(
    "i3012x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3012x1(c: Cast) -> None:
    """The temporary hit points and the daze-for-more trade both work off
    `PowerUsed`, which is safe here: the row reads only the declaration,
    not anything the body does.

    **Marker removed, as `i2717x1`.** The tome's two stored powers are
    reached by `i3012p1` through `_tome_trade`, and nothing else in a
    fight asks after them."""

    def used(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None:
            return
        if not ({Keyword.PSYCHIC, Keyword.TELEPORTATION} & set(p.keywords)):
            return
        if c.may("take the daze for more temporary hit points", who=c.me):
            c.dazed(on=c.me, until=When.EONT)
            best = max(c.cha_mod, c.int_mod, c.wis_mod)
            c.temp_hp(2 * (c.enhancement + best), on=c.me)
        else:
            c.temp_hp(c.enhancement, on=c.me)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power(
    "i3012p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[
        Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION,
    ],
)
def i3012p1(c: Cast) -> None:
    """Re-aimed and written, as `i2898p1`. "Psychic or teleportation" is
    two sets and `c.borrow_row` narrows on one keyword, so they are asked
    in turn and the first with anything in it answers.

    **The price is charged now.** This card prints it more narrowly than
    its six siblings -- a *daily* power, and an attack **or** utility one
    -- which is exactly the two knobs: `usage=DAILY`, and `attacks=None`
    for "do not narrow on the attack line at all". `attacks=True` would
    refuse a utility the card allows, and leaving the usage off would
    accept an encounter power it does not."""
    _tome_trade(
        c, 5, Keyword.PSYCHIC, Keyword.TELEPORTATION,
        usage=DAILY, attacks=None,
    )


@power(
    "i3192p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit a target with an attack using this totem while bloodied",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i3192p1(c: Cast) -> None:
    """"Surges spent since your last extended rest" needs no day's
    bookkeeping: an extended rest hands every surge back, so the count
    is `max_surges` less what is left, which `Health` carries both of.
    "While you are bloodied" is a fact about the wielder at the moment
    of the hit, so it is asked in the body rather than as a
    `requires=`."""
    foe = _struck(c)
    if foe is None or not c.bloodied(on=c.me):
        return
    h = c.world.get(c.me, Health)
    spent = max(0, h.max_surges - h.surges) if h is not None else 0
    if spent:
        c.flat(spent, dtype=DamageType.PSYCHIC, on=foe)


@power(
    "i3192p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_bloodied_req,
    requires_text="you must be bloodied",
)
def i3192p2(c: Cast) -> None:
    """A printed Requirement the board has to meet, so it is a `requires=`
    gate rather than a branch in the body."""
    c.spend_surge(on=c.me)
    c.temp_hp(5 + c.surge_value() + c.enhancement, on=c.me)


@power(
    "i3194p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target with an attack using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i3194p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.condition(Condition.RESTRAINED, on=foe, until=When.SAVE_ENDS)


@power(
    "i3194p2",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3194p2(c: Cast) -> None:
    """A rope to an unattended object. Deliberately inert: nothing on a
    board is an object this could twine around or retract."""


@power(
    "i3194p3",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ZONE],
    trigger="you use a close or an area primal attack power with this totem",
    on=Trigger(PowerUsed, _area_by_me, "you use a close or area power"),
)
def i3194p3(c: Cast) -> None:
    """`PowerUsed` announces before the body, but the targets are chosen
    by then and that is all this reads. The zone is laid over the squares
    those targets are standing in, which is the part of the area that
    mattered."""
    spots = set()
    for who in getattr(c.trigger, "targets", None) or []:
        square = _square(c, who)
        if square is not None:
            spots.add(square)
    if spots:
        c.zone(spread(frozenset(spots), 0), difficult=True, until=When.EONT)


@power(
    "i3409x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3409x1(c: Cast) -> None:
    c.bonus(
        "attack", 1, kind="item", on=c.me, until=When.ENCOUNTER,
        when=_has_keyword(Keyword.FEAR, Keyword.CHARM),
    )


@power(
    "i3409p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit a creature with an attack using this totem",
    on=Trigger(Hit, by_me, "you hit with this totem"),
)
def i3409p1(c: Cast) -> None:
    """"Closer than where it started the turn" is measured from where the
    shove left it, which is the same square unless something else moves it
    first -- close enough, and the only reading the board can supply."""
    foe = _struck(c)
    if foe is None:
        return
    c.push(c.speed_of(foe), on=foe)
    was = c.distance(foe)
    checked: list[int] = []

    def ended(ev: TurnEnd) -> None:
        if checked or ev.actor != foe:
            return
        checked.append(1)
        if c.distance(foe) < was:
            c.restore_use(c.ref, on=c.me)

    c.watch(TurnEnd, ended, until=When.ENCOUNTER)


@power(
    "i3435x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3435x1(c: Cast) -> None:
    def scorched(ev: DamageApplied) -> None:
        if ev.target != c.me:
            return
        if ev.dtype not in (DamageType.ACID, DamageType.FIRE):
            return
        c.bonus("speed", 2, kind="item", on=c.me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER)


@power(
    "i3435p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.FIRE],
    trigger="you bloody an enemy with an implement attack using this ki focus",
    on=Trigger(DamageApplied, by_me, "you damage an enemy"),
)
def i3435p1(c: Cast) -> None:
    """"You bloody" is read off the damage -- `Bloodied` names no source.
    One burn that is acid and fire at once, which is one save and one
    number rather than two of each."""
    ev = c.trigger
    if not _just_bloodied(c, ev):
        return
    c.ongoing(
        2 + c.enhancement, dtypes=(DamageType.ACID, DamageType.FIRE),
        on=ev.target, until=When.SAVE_ENDS,
    )


@power(
    "i3436x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3436x1(c: Cast) -> None:
    c.bonus("skill:arcana", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:history", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i3436p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit one or more enemies with an arcane attack power",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.ARCANE)), "you hit with an arcane power"
    ),
)
def i3436p1(c: Cast) -> None:
    """Difficult terrain was a property of ground and not of a creature:
    `c.zone` roughs up squares, and until #831 nothing made the whole board
    cost one creature double. `c.difficult_for` is that, and this is the one
    row in its family with **no geometry** -- "all squares" is the board, so
    it takes the bare call rather than an area.

    `c.trigger.target` and not `c.target`: the card says "each enemy that
    you hit", and the enemy is the one named by the `Hit` that fired this,
    which for an area power is one firing per enemy.

    Save ends, which is what the card prints, and the save is the burdened
    creature's -- so `When.SAVE_ENDS` is already measured against the right
    creature and needs no second argument."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.difficult_for(on=foe, until=When.SAVE_ENDS)
