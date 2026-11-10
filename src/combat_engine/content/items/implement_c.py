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
* **"A creature you summoned" is answerable now**, and this said it could
  only be approximated by the servants and companions the board records.
  `c.summon` still sets no *relation* -- what it records is a `Summon`
  fact, on both summon paths, and `query.is_summoned(world, eid, by=)`
  reads it. The old reading was wider than the print in a way `i3422p1`
  names outright: it lists an allied beast and a summoned creature as two
  different things. #1218.

The recurring gaps, each named with the symbol it wants rather than
approximated: `c.class_feature()`, `c.tome_powers()` and `c.item_set()`.
`c.reshape_area()` was on that list and landed on #614; `i1979p1` calls
it.

Three of the old recurring gaps closed once the specs gained refs and the
engine was read rather than its prose:

* **A pact boon is announceable.** `cf:warlock-f1` pays each leg off a
  `Dropped` whose subject this caster had cursed, and `c.build` says which
  leg. So "when your <pact> boon triggers" is that event plus those two
  questions, and only the star leg -- which `cf:warlock-f1` pays nothing
  for -- is still out of reach.
* **cf:warlock-f4 damage carries its label.** `features.strikers.
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
    CHA,
    CON,
    DAILY,
    EACH_ENEMY,
    EACH_OTHER,
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
    YOU_AND_EACH_ALLY,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
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
    PowerResolved,
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


def _maximum_damage(ev: Any) -> bool:
    """Did this blow come out at the ceiling of its own dice?

    **The old marker said nothing could ask, having looked at the wrong
    event.** `DamageApplied` does carry the total only -- that part was
    right -- but `DamageRolled` carries the live `rng.Roll` as a plain
    attribute, which is `#703`: `roll.expr` is the expression and
    `roll.dice` is the faces that came up. `i1761p1` and `i3191x1` already
    read that object.

    Two ways a blow reaches the ceiling and they look different here.

    A **critical** maximises every face before anything is rolled, so
    `cast._roll_damage_dice` hands back no `Roll` at all -- its own
    docstring says a crit means no die was rolled and no second result
    exists -- and `cast._max_of`'s says every face at its highest is "what
    a critical hit deals". So the crit is the printed case rather than an
    approximation of it, and the tell is `ev.ctx["crit"]`, the context the
    emit site hangs on the event beside the roll.

    An **ordinary roll** that happens to come up all top faces is the
    other, and is the test on `roll.dice`.

    `roll.bonus` and the enhancement are deliberately not looked at: they
    are flat terms and cannot roll high. That is `i1761p1`'s measurement of
    this same object -- `expr='1d12' dice=[11] bonus=0` -- and it is also
    why the total cannot be used for the comparison, since the total
    carries modifiers the dice know nothing about.

    A line with no dice behind it answers False: a flat payout, an ongoing
    tick and a minion's damage are never "maximum damage", and `roll.dice`
    is empty for all three.

    The expression is split here rather than through `cast._faces_of`,
    which is private to that module. `powers/seeker.extra_dice` and
    `implement_b._one_more_die` split one the same way.
    """
    ctx = getattr(ev, "ctx", None) or {}
    if ctx.get("crit"):
        return True
    roll = getattr(ev, "roll", None)
    if roll is None or not roll.dice:
        return False
    _, _, rest = str(roll.expr).partition("d")
    face, sign, _tail = rest.partition("+")
    if not sign:
        face, _sign, _tail = rest.partition("-")
    return face.isdigit() and all(d == int(face) for d in roll.dice)


def _my_summons(c: Cast) -> list[int]:
    """The creatures this one summoned. *"A creature you summoned."*

    This was `_mine` and read servants plus companions -- every relation
    the board held -- on the stated ground that *"`c.summon` records
    nothing"*. What it did not record was a **relation**; the fact is
    recorded now and `query.is_summoned` reads it, on both summon paths.
    #1218.

    The old reading was wider than the print in a way `i3422p1` names
    outright: it lists an allied beast and a summoned creature as two
    different things, so counting a beast as a summon cannot be what any
    of these cards means.
    """
    return [e for e in query.creatures(c.world) if query.is_summoned(c.world, e, c.me)]


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


def _saves_against_mine(world: World, me: int, ev: Any) -> bool:
    """*"A creature makes a save against one of your powers."*

    **The marker was `SavingThrow.source` and the event neither carries one
    nor needs one.** `durations.save` emits this throw **before** it calls
    `end(eff, "saved")` -- the comment at that site says the outcome is
    announced first so a listener can change it -- and a declared trigger
    is offered from a bus subscriber, so the hold being shaken off is still
    in `effects.live` while this predicate runs. `Effect.source` is the
    creature that laid it, which is the question.

    Matched by `str(eff) == ev.against` rather than by parsing the display
    string: `Effect.__str__` opens with `e<id>`, so the comparison pins the
    one effect and nothing has to be read out of the text.

    Walked over `effects.live` and **not** `effects.of(saver)`, because
    `Effect.saver` lets a different creature roll the throw -- the hold
    would then sit on somebody this event does not name. Same reading as
    `f2294`, which was written off this marker first.

    What it cannot say is *power*: `Effect.source` is a creature, so a hold
    laid by an item property or by a feat through `c.credit` answers True
    as well. That is wider than the print by the handful of effects a
    character lays that are not a power's doing, and very much narrower
    than the no-gate it replaces.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    against = getattr(ev, "against", "")
    return any(
        eff.source == me and str(eff) == against
        for eff in world.effects.live.values()
    )


def _ally_hit_within(n: int):  # noqa: ANN202
    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me or not _my_side(world, me, who):
            return False
        return query.distance_between(world, me, who) <= n

    return check


def _hits_my_summon(world: World, me: int, ev: Any) -> bool:
    """*"An enemy hits a creature you summoned."*

    Was `Relation.MASTER_OF`, which is who commands whom and is a wider
    and differently-shaped question: a beast companion answers to its
    ranger without having been summoned. #1218.
    """
    who = getattr(ev, "target", None)
    return who is not None and query.is_summoned(world, who, me)


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
    attacks: bool | None,
    usage: Usage | None = None,
) -> bool:
    """"Expend an unused wizard daily attack power of level 5 or higher."

    `c.expend_row` is the spend and refuses a row that is not owned, is an
    at-will or is already gone -- but it takes a ref and the card names a
    *set*. `c.unspent` is that set: the refs `c.expend_row` would accept,
    narrowed by class, a level **floor**, usage and attack line. A card
    that names no usage leaves `usage` off; `attacks=None` is the card
    that says "attack or utility".

    **The pick is offered.** This walked the sorted candidates and burned
    the first one, so the engine chose which of the character's dailies
    the player lost -- and `c.borrow_row` asks `world.decide` for the
    other half of the same printed sentence. Spending one daily rather
    than another is a real cost and no audit verdict can see it go wrong.

    Returns False when there is nothing to charge, which is the printed
    Requirement.
    """
    pool = c.unspent(cls=cls, level=level, usage=usage, attacks=attacks)
    if not pool:
        return False
    pick = c.choose(pool, c.ref)
    return bool(pick) and c.expend_row(pick)


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
    dropped=("c.lengthen_wall()",),
)
def i526x1(c: Cast) -> None:
    """**The zone half is written and the old note had the mechanism
    backwards.** It said a zone's footprint is "fixed where it is laid and
    nothing reaches it afterwards", which is true and is not how this card
    works: a zone is not laid and then edited, it is **computed at cast
    time** from the area the power is measured over. 177 sites in the tree
    write `c.zone(c.area(), ...)`, and `c.area` goes through
    `dsl.area_of` -> `reach_of` -> `_stretched`, which reads
    `Mods.total("blast_size", ctx)`. So a `blast_size` modifier standing
    when the row is used makes the zone it lays bigger, by construction, in
    the same breath as the attack it covers -- which is what "add squares
    to the area" means.

    `Keyword.ZONE` is how "a zone" is said, and it is printed: 395 rows
    carry it. 338 of them are a close burst, a close blast or an area
    burst, which are exactly the three kinds `_stretched` grows.

    **`c.bonus` and not `c.widen_areas`, for the gate.** The verb is the
    same modifier one argument shorter and takes no `when=`, so it would
    have grown *every* burst the carrier throws -- strictly more than a
    card that says "a zone or a wall". `_stretched`'s own context carries
    `power`, which its docstring offers for exactly this ("the range of
    your **arcane** powers" is a gate rather than a blanket stretch).

    **The wall half is what is left, and it is a different quantity rather
    than the same one missing a case.** `dsl`'s own note on
    `AREA_OR_CLOSE` says so: the `blast_size` set is
    `("close_burst", "close_blast", "area_burst")` deliberately, because
    "a wall's size is its length rather than a radius", and `_stretched`
    returns 0 for `kind == "wall"`. So the marker names a term of its own
    instead of a parameter on the burst verb. Two rows in the tree are
    wall-kind zones.

    `_keywords_of` reads the header rather than `dsl.keywords_of`, as the
    rest of this file's gates do. Nothing grants `ZONE` to a row that was
    not printed with it, so the two answers cannot differ here."""
    c.bonus(
        "blast_size",
        c.enhancement,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: Keyword.ZONE in _keywords_of(ctx.get("power")),
    )


@power(
    "i526p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    todo=("c.move_zone(reshape=)",),
)
def i526p1(c: Cast) -> None:
    """`c.move_zone` carries a shape from one place to another; reshaping
    one around a square that stays put is a different operation.

    **Re-pointed off `c.reshape_area()`, which was one symbol over two
    mechanisms.** The other six rows on it all change the area a power
    covers *as it is used* -- the header's shape, computed before the body
    runs -- and all six say so in the same words. This row is the odd one:
    it mutates a **wall already standing on the board**, with at least one
    square pinned. Nothing about a header, and no overlap with the other
    six beyond the English word "reshape".

    Named on `c.move_zone` rather than as a new verb, because that is the
    facility this extends and `c.move_zone(with_me=)` already marks a
    second gap on it. The difference from the existing call is exactly the
    pinned square: `move_zone` translates and keeps the shape, where this
    changes the shape and keeps a square. #614.

    **Confirmed, and it is the cheap bucket.** `c.move_zone(zone, squares_,
    *, to=)` exists, so this is one parameter on a live verb rather than a
    facility nobody has started. Two things it owes beyond the pinned
    square, both measured here: `Zone` carries no kind at all, so "a wall
    effect" has to be identified through `zone.label` -- which leads with
    the laying row's ref, whose `reach.kind` is `"wall"` -- and the
    reshaped squares still have to form a legal wall of the same length.
    Hand-rolling that here the way `p5052` writes zone squares would be a
    geometry search with no owner; the verb is the owner.
    """


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
    todo=("c.restore_use(once_per_round=)",),
)
def i724x1(c: Cast) -> None:
    """**Re-pointed, and the old note's premise was wrong.** It said this
    needs "the once-per-turn limit to exist before anything can add to it".
    It exists: all five of the rows `c.flurry_of_blows()` picks between are
    declared `once_per_round=True`, and `dsl.usable` refuses them with
    "already used this round" off `Powers.last_round`. The ref, the limit
    and the place the limit is recorded are all in hand.

    **What refuses is `c.restore_use`, and a sibling is already broken on
    it.** Those rows are at-wills, so `dsl.use` records a use with
    `Powers.note_round` and never touches `used` -- and `restore_use`
    answers False whenever `powers.times(ref) == 0`, which is always.
    Measured on a monk board: `note_round` set, `usable` refuses,
    `c.restore_use` returns False, the round mark is untouched and `usable`
    still refuses. `Powers.restore` would have popped it; nothing reaches
    `Powers.restore`.

    So `f3697` -- a second use of that row in a turn an action point bought
    -- is inert today, carries no marker, and waits on this same parameter.
    One keyword on `c.restore_use` pays both rows, which is why the symbol
    is named there rather than as a verb of this row's own.

    The rest of the card needs nothing further. "An additional time during
    your turn" is one hand-back a turn, which `c.latch(per_turn=True)`
    holds; the two uses are triggered by two different `Hit` events by
    construction, which is the printed distinctness clause; and
    `c.struck_with` is the read for "with this ki focus" -- its own
    docstring names a ki focus as the case it is right for, where
    `c.weapon_of` is not."""


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
)
def i744x1(c: Cast) -> None:
    """The first half plays: a wizard fire power used through this tome
    reduces the target's fire resistance by 10, which from the
    attacker's side is ten points walked through. Heroic, so 10.

    "A tome's two stored powers are not a thing the engine holds" is stale,
    and the marker is gone rather than re-aimed: the contents are reached by
    `implement_b._tome_trade`, which walks `c.borrow_row` down the level
    ladder this card prints. They are also not a *combat* clause of this
    property -- choosing them happens when the tome is acquired, and the
    only thing that ever spends them is `i744p1` beside this, which now
    does."""

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
)
def i744p1(c: Cast) -> None:
    """There is something to buy after all. `implement_b._tome_trade` is the
    tome's contents: `c.borrow_row` is "the card names a set and asks the
    character to take one of it", which is exactly what two chosen dailies
    are, and it walks the ladder down from the tome's own rung because the
    card says "equal to or lower than that of the tome".

    The price and the loan are one walk now, in `_tome_trade`: this row
    had them as two statements, and that shape charged at the tome's rung
    rather than the lent card's and charged at all when the set was empty.
    `""` is the printed Requirement -- no card lent and no price paid."""
    from combat_engine.content.items.implement_b import _tome_trade

    _tome_trade(c, 5, Keyword.FIRE)


@power(
    "i859x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i859x1(c: Cast) -> None:
    """The bonus and the vulnerability are one bargain, so the second is
    armed off the hit that pays the first.

    **Both exemptions play.** Having a class feature is knowing its row,
    which is what `c.feat` reads off `Powers.all`, and `cf:warlock-f1s5`
    is declared -- so a character with that feature is let off the
    vulnerability, which is the printed line.

    **The second exemption is a build, not a row, and the marker was
    waiting for a row that will never be written.** `cf:sorcerer-f0s3` has
    no row of its own because that source is written inside
    `cf:sorcerer-f0`, on the `wild` leg of `chargen.BUILDS["sorcerer"]` --
    `feats/sorcerer.py`'s module note says so and `f1001` asks exactly
    `c.build("wild")` for the same feature. `c.feat("cf:sorcerer-f0s3")`
    would have been a correctly spelled ref with nothing behind it, which
    is the silent form of this mistake; `f2175` retired the sibling marker
    `cf:sorcerer-f0s1` on the same reasoning."""
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
        if c.feat("cf:warlock-f1s5", on=c.me) or c.build("wild", on=c.me):
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
    on=Trigger(
        SavingThrow,
        both(_enemy_saving, _saves_against_mine),
        "an enemy saves against one of your powers",
    ),
)
def i1956p1(c: Cast) -> None:
    """**"Against one of your powers" is narrowed now.** The old note said
    `SavingThrow` names the roller and not whose effect is being shaken
    off, which is true of the event and was the wrong place to look: the
    effect itself is still live while the trigger is being offered, and it
    carries the source. `_saves_against_mine` is the whole argument and the
    reading `f2294` reached first.

    Before this the row fired on **every** enemy saving throw on the board,
    so a daily was being offered against a hold somebody else had laid --
    which is the shape the print exists to exclude.

    "Must take the new result" is `keep="new"`, not `"worst"`: the card
    takes the second roll whether it is better or worse.

    `_enemy_saving` is left in front of it, and it is a narrowing the card
    does not print -- the printed subject is "a creature". It costs nothing
    and is kept deliberately: a hold this character laid sits on an enemy
    in every case on the board, and the one offer it declines is a reroll
    of an **ally's** save against the caster's own stray burst, where
    "must take the new result" is a gamble taken against the party. Not a
    marker, because no engine facility is missing for it."""
    c.reroll_save(keep="new")


@power(
    "i1968p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="an attack with this orb succeeds against the target's Will defence",
    on=Trigger(
        Hit,
        lambda w, me, ev: ev.attacker == me and _hit_defence(ev) is WILL,
        "you hit a creature's Will defence",
    ),
)
def i1968p1(c: Cast) -> None:
    """**Written. `c.worsen_save()` was the wrong shape twice over.**

    The trigger half was already conceded: `Hit` carries no defence and
    does not need to, because the defence an attack was aimed at is header
    data on the row that swung. `_hit_defence` reads it, exactly as
    `i1941p1` beside this does.

    The payout half is `c.reroll_save(keep="worst", ev=)`, and the old note
    rejected it on a premise that is false: it said the verb only works
    "inside a row the dispatcher offered for that one throw". `ev=` is
    there for precisely the other case -- its docstring says so, *"a banked
    reroll is a `c.watch`, and its handler closes over the row's `Cast`
    rather than the roll"* -- and `durations.save` reads `rolled.saved`
    back off the event after the emit, so a listener mutating it during the
    emit is the supported route. "Roll twice and take the lower" is
    `keep="worst"` by construction: the verb rolls once more and keeps
    `min(again, ev.natural)`.

    A save penalty was rejected for the reason the old note gives and it
    still holds -- two rolls and a flat subtraction are different numbers.

    **"An effect from that attack" is the part that needed thinking about,
    and it is a diff rather than a label.** A label leads with the laying
    row's ref for most verbs and with the printed amount for `c.ongoing`,
    so matching on the ref would have silently excluded exactly the burn
    this kind of card most often lays. Instead: the live effect ids are
    snapshotted here -- this body runs inside the `Hit` emit, so the
    attacking row has not laid anything yet -- and the diff is taken when
    `PowerResolved` says that same use has **finished**. What that catches
    is every hold the use laid, whatever it is labelled, and nothing laid
    by a later attack of the caster's. `PowerUsed` would have been the
    wrong event for the reason its own docstring gives: it says a use has
    started.

    `rolls_the_save == foe` rather than `owner == foe`, because
    `Effect.saver` lets another creature roll and the printed sentence is
    about the throw.

    The throw itself is pinned by `str(eff) == ev.against`, not parsed out
    of it: `Effect.__str__` opens with `e<id>`.

    "With this orb" is the half this file cannot gate, by the module
    docstring's first judgement."""
    foe = _struck(c)
    if foe is None:
        return
    me = c.me
    ref = getattr(c.trigger, "power", "") or ""
    standing = set(c.world.effects.live)
    from_attack: set[int] = set()
    closed: list[bool] = []

    def settled(ev: PowerResolved) -> None:
        if closed or ev.actor != me or ev.power != ref:
            return
        closed.append(True)
        from_attack.update(
            eff.id
            for eff in c.world.effects.live.values()
            if eff.id not in standing
            and eff.source == me
            and eff.rolls_the_save == foe
        )

    def twice(ev: SavingThrow) -> None:
        if ev.actor != foe or not from_attack:
            return
        hold = next(
            (e for e in c.world.effects.live.values() if str(e) == ev.against),
            None,
        )
        if hold is not None and hold.id in from_attack:
            c.reroll_save(keep="worst", ev=ev)

    c.watch(PowerResolved, settled, until=When.ENCOUNTER)
    c.watch(SavingThrow, twice, until=When.ENCOUNTER)


# -- level 7 ----------------------------------------------------------------


@power(
    "i1098x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.extra_area_target()",),
)
def i1098x1(c: Cast) -> None:
    """Split: the bonus half plays and the second target does not.

    The bonus is gated on a use that does exist -- `i1098p1` beside this
    grants `p2273` for the encounter -- so "to attack rolls to destroy them"
    is a modifier narrowed to that ref, and `item` is the word the card
    prints in front of "bonus".

    The second target stays dropped, and `c.add_target` is not it, twice
    over: it appends a **creature** to a use running *below an immediate
    interrupt*, where this is a standing property whose extra target is a
    conjuration or a zone. `running_below` refuses it outright from a
    trait, and the target line being widened is not a creature line.

    **And there is no target line to widen, which is narrower still.**
    `p2273` is declared `target=NO_TARGET`: it gathers the zones and
    conjurations in reach itself and offers **one** of them through
    `c.choose`, for the reason its own docstring gives -- a zone is not a
    creature, so it cannot be a printed target. So neither `c.add_target`
    nor an `Effect.retarget` replacement could ever reach this clause.
    Where it has to land is inside `p2273`'s own body, which is the shape
    `#550` settled for a feat naming one power -- and that is another
    file, plus a reader for "the caster is holding this item" that the
    `c.feat` gate has no equivalent of here. The marker stays on the
    facility rather than being re-pointed at a file this row cannot
    edit."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER, kind="item",
        when=lambda ctx: ctx.get("power") == "p2273",
    )


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
    todo=("c.struck_by_property(implement=)",),
)
def i1884x1(c: Cast) -> None:
    """**Re-pointed, and the old note's closing claim was false.** It said
    no creature in the tree resists anything by material, "so there is
    nothing for a silvered implement to beat". Counted off `game.db`:
    **11** stat blocks carry `regen_unless_struck_by = "silvered"`, nine of
    them heroic, and `c.regeneration(unless_struck_by=)` is the live
    mechanism every one of them goes through. The benefit this card buys is
    real and it is in band.

    The **write** is real too, and is not the gap. `c.gains_property`
    matches `mine=True` on `Weapon.item`, which an implement block carries
    -- measured on a level-8 caster holding this item, it finds the one
    entry and answers 1. `i1764x1` and `f1075` write the same property as a
    blanket and `i1880x1` writes it for one weapon.

    **The reader is the gap, one layer below the verb.** The only thing
    that asks after a weapon property is `c.struck_by_property`, and it
    resolves the swing through `c.weapon_of` -> `Gear.main`, whose
    fallbacks skip implements on purpose -- a creature holding nothing but
    an implement is holding nothing it can swing. So the property would sit
    on the item and nothing could ever see it. `c.struck_with` *is* the
    read that finds an implement, and `struck_by_property`'s own docstring
    says it deliberately does not use it, because a treated weapon is one
    weapon and the other must not carry it. Reconciling those two readings
    is the parameter.

    Left unwritten rather than written inert, and the marker stays `todo`:
    laying a property nothing reads would make this row fire and report
    finished while the card does nothing in any fight, which is the worst
    of the three outcomes."""


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
)
def i1979p1(c: Cast) -> None:
    """The blast becomes a burst two squares smaller, minimum 1.

    **"A power's reach is header data read before the body runs" was the
    hold and #614 answered it.** `c.reshape_area` lays the shape on the
    creature and `dsl.reach_of` resolves it per caster per use, so nothing
    rewrites the header and the wielder still throws a burst. `i683p1` is
    the same card with an arcane narrowing and carries the longer note; the
    two judgements worth repeating here:

    * **`into` is a callable so the new size can be derived from the old.**
      "2 smaller than the blast" belongs to whichever power is thrown.
    * **No `on=Trigger` for the printed "use this power when you use a
      close blast power.**" `dsl.use` picks the targets and the area before
      `cast.used()` announces `PowerUsed`, so a reshape laid in answer to
      that event would reach the blast *after* it was aimed. The free
      action is spent first instead and the blast arrives reshaped.

    Unnarrowed by keyword or class, because this card prints neither: any
    close blast through this implement. It ends on the use it was bought
    for rather than on being measured -- `dsl.area_of` is a query the
    renderer calls, so a one-shot spent by measurement would be gone before
    the power was thrown."""
    held = c.reshape_area(
        lambda r: CloseBurst(max(r.size - 2, 1), from_=r.from_),
        kinds=("close_blast",),
        on=c.me,
        until=When.ENCOUNTER,
    )

    def spent(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        row = get(getattr(ev, "power", ""))
        # The printed line, so still a blast: `Power.reach_of` answers the
        # header and only `dsl.reach_of` sees the reshape.
        if row is None or row.reach_of().kind != "close_blast":
            return
        if held is not None:
            c.world.effects.end(held, "spent")

    c.watch(PowerUsed, spent, until=When.ENCOUNTER, on=c.me, label=c.ref)


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
)
def i2306p1(c: Cast) -> None:
    """`PowerUsed` names its subject `actor`, so this is `about_me` and not
    `by_me` -- and the row must leave itself out, or answering its own free
    action recurs forever. Targets are chosen before the body runs, so
    `ev.targets` is the one thing on that event worth trusting -- and "hit
    or miss" wants exactly that list.

    **The keyword half is written, and `c.add_keyword()` was an absence
    that is not there.** `c.counts_as_keyword` writes
    `Powers.granted_keywords`, which `dsl.keywords_of` unions into the
    header tuple -- and that function is the single door all 22 keyword
    reads in the engine go through, by its own docstring, so a keyword
    granted here is seen by a trigger, a modifier gate, a resistance and
    the card alike. It exists for the twelve feats printing "your <row>
    gains the reliable keyword", and "the attack gains the fear keyword" is
    the same sentence aimed at one use.

    **"The attack", not "the power", is why it is handed back.** The verb's
    shortest duration is `When.ENCOUNTER`, and leaving it there would give
    the fear keyword to every later use of that row as well -- strictly
    more than the card. So the grant is ended on `PowerResolved` for that
    same use, which is the event that says a use has *finished*; the window
    the keyword is live for is exactly the resolution of the attack this
    daily was spent on. `PowerUsed` fires before the body, so the grant is
    standing before the first roll.

    None back from the verb means the row already carries fear, so there is
    nothing to grant and nothing to take away."""
    ev = c.trigger
    ref = getattr(ev, "power", "") or ""
    held = c.counts_as_keyword(ref, Keyword.FEAR) if ref else None
    if held is not None:

        def give_back(done: PowerResolved) -> None:
            if done.actor != c.me or done.power != ref or held.ended:
                return
            c.world.effects.end(held, "the use it was granted for is over")

        c.watch(PowerResolved, give_back, until=When.ENCOUNTER)
    for foe in getattr(ev, "targets", []):
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "i2309x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2309x1(c: Cast) -> None:
    """"`c.resist` grants one and nothing takes one away" is false of
    `c.resist` itself: its negative branch is the other printed sentence,
    "the target loses resist 10 to fire", and it is arithmetic -- the
    standing number is remembered and the hold's `undo` puts it back, which
    is what makes a save end this rather than leave it stripped.

    So the amount is read off the target first: "loses resist poison" is all
    of whatever it had, not a printed number.

    Declared on `RelationSet` because that is what `c.curse` emits -- it
    lays `Relation.CURSED_BY` and announces it -- so "when you place a curse
    upon a target" is that event with the source asked. The paragon
    vulnerability lines are out of scope."""
    from combat_engine.engine.components import Defences
    from combat_engine.engine.events import RelationSet

    def cursed(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.CURSED_BY or ev.source != c.me:
            return
        defences = c.world.get(ev.target, Defences)
        standing = defences.resist.get(DamageType.POISON, 0) if defences else 0
        if standing > 0:
            c.resist(
                -standing, DamageType.POISON, on=ev.target,
                until=When.SAVE_ENDS,
            )

    c.watch(RelationSet, cursed, until=When.ENCOUNTER, on=c.me)


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
)
def i2330p1(c: Cast) -> None:
    """Written, and the old note understated what was missing. It said
    `implement=True` was "both halves of what this line needs" and only
    the one-use scope was dropped -- but the card narrows the **source**
    too: "the next **necrotic or poison** power you use through this rod".
    Written as a bare override it recoloured everything the rod cast, which
    is wider than the card rather than narrower, and so the kind of gap no
    audit verdict can see.

    Three narrowings, all parameters now: `implement=True` for the rod,
    `from_` taking the pair, and `once=True` for "the next"."""
    c.deals(
        DamageType.RADIANT, on=c.me, until=When.ENCOUNTER, implement=True,
        from_=(DamageType.NECROTIC, DamageType.POISON), once=True,
    )


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
    keywords=[Keyword.TELEPORTATION, Keyword.AUGMENTABLE],
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
)
def i2716x1(c: Cast) -> None:
    """`c.summon` sets no relation, so "a creature you summoned" is read as
    the servants and companions the board does record."""

    def spared(ev: Miss) -> None:
        mine = _my_summons(c)
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
    todo=("c.modify_power()",),
)
def i2775x1(c: Cast) -> None:
    """**Re-pointed off `c.item_set()`, and this row never belonged to that
    group.** The old note read the first printed sentence as "the whole
    benefit is conditional on the set being complete". That sentence is
    `When this item is x6_679`, and `x6_679` is a row in the `background`
    table -- not an item set, and not a thing an item can be "in". The
    four genuine holders of that symbol say so in plain words
    ("items you have from this set", "one or more items from this set"),
    which is what a real set reference looks like in a brief. So the first
    sentence is a garbled cross-reference; the other four rows keep
    `c.item_set()` and should not follow this.

    **Referred up and answered.** The main session read the page, which an
    authoring agent cannot. The printed property is a **build-time choice
    among five creature kinds** -- "when this item is <made>, choose one of
    five, and your turn-undead power can target that kind instead of
    undead" -- so the first sentence names no set and no background. The
    ETL had matched an ordinary past participle in the text against a
    `kind='Birth'` background whose printed name is that same word, and
    swapped in its ref.

    `#1234` has the census: **53 specs** across two such refs, every name
    gate reading them as correct because a substituted ref is still a
    valid ref. So this is `#1152`'s fault recurring in a second table
    rather than a one-row oddity.

    What that changes here: the first sentence is `chargen.BUILD_OPTIONS`
    work -- the shape `items/armour.i1392p1` was re-pointed to today --
    and **not** a gate on anything readable in a fight. Had it been
    written from the brief as it stands, it would have been a condition on
    a background, which is False in every fight.

    The marker does not move on the strength of that, because the second
    sentence below blocks the row either way.

    **The second sentence blocks the row under either reading of the first,
    which is why the marker moved here rather than away.** "You can target
    creatures of the chosen kind instead of undead creatures" changes
    `p146`, whose body opens `if not c.is_kind("undead"): return` -- so
    this is the #550 shape: a clause written into that row's body, in
    another file, gated on the caster holding this item, exactly as
    `i1461x1` below. `c.pre_empt` is not a way round it, because `what=`
    has to be read by the row itself with `c.instead_of` and `p146` reads
    neither.

    Not approximated by laying an `origin:undead` label on the chosen
    enemies, which `query.kinds_of` would believe: that makes them undead
    for every other card in the fight, which is far stronger than print.

    The choice itself is writable and is worth nothing alone -- `c.choose`
    over the five kinds, the shape `i2323p1` and `i2777x1` beside this
    already use."""


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
    dropped=("c.item_set()",),
)
def i2777x1(c: Cast) -> None:
    """"Nothing on `Cast` or `query` reads a character's race" is stale:
    `c.race_of` does, and the note's own reasoning about `c.kinds_of` is why
    it has to -- `kinds_of` answers *origin*, which 21 races share, so it
    cannot tell one race from another. `c.race_of` returns the ref off the
    `race:<ref>` that `Build.choices` carries, which is the question this
    card asks about the ally rather than about the caster.

    The set half stays dropped; a completed item set is still not a thing
    the engine holds."""

    def ward(ev: Healed) -> None:
        if ev.source != c.me or not _my_side(c.world, c.me, ev.target):
            return
        pick = c.choose(list(_ELEMENTS), "which damage type")
        amount = 5 + (5 if c.race_of(on=ev.target) == "r1" else 0)
        c.resist(amount, pick or DamageType.FIRE, on=ev.target, until=When.EONT)

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
)
def i3173p1(c: Cast) -> None:
    """**`c.sustain_all()` was a false marker**, and the claim it rested on
    -- that nothing sustains a standing effect from outside -- is the one
    `i2573p1` already refuted. `Effects.sustaining` lists what this creature
    is keeping going and `Effects.sustain` keeps one going, both public and
    neither spending an action; `actions._sustaining` is only the menu.

    So "all of them" is that pair with the choice taken out, which is the
    whole difference between this block and `i2573p1`'s one-of.
    `sustain_cost` is the printed action, so the `MINOR` filter is the
    other half of the sentence rather than an assumption.
    """
    effects = c.world.effects
    for eff in effects.sustaining(c.me):
        if eff.sustain_cost is MINOR:
            effects.sustain(eff)
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
)
def i3403p1(c: Cast) -> None:
    """Declared on the roll rather than on the hit: `c.reduce` takes a
    number off damage that has been rolled and not yet dealt, and by `Hit`
    there is nothing left to reduce.

    **The per-tick slide is written, and `c.ongoing(on_tick=)` was a false
    marker.** The hook the old note could not find is `DamageApplied.detail`:
    `Effects._on_turn_start` stamps the burn it deals with `str(eff)`, so a
    tick is told apart from every other blow that creature takes, and
    `p3273` has been paying off exactly that read.

    The subscription goes on the effect's own `subs`, as `p3273` does it, so
    a save that ends the burn takes the slide with it rather than leaving a
    listener behind for the next one.
    """
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is None:
        return
    c.reduce(5, c.trigger)
    burn = c.ongoing(5, DamageType.ACID, on=foe)
    if burn is None:
        return
    me, tag = c.me, str(burn)

    def shove(ev: DamageApplied) -> None:
        if ev.target == foe and ev.detail == tag:
            c.slide(1, on=foe)

    burn.subs.append(c.world.bus.on(DamageApplied, shove, owner=me))


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
    attack=Attack((INT, CON, CHA), vs=FORT),
)
def i3472p1(c: Cast) -> None:
    """"Intelligence, Constitution, or Charisma" is the tuple form of
    `Attack.ability`, which `ability_for` resolves to whichever of the three
    this holder is best at -- the pick a player would make, and the only one
    that can be made without asking mid-roll. Writing one of them was worth
    several points of attack on the wrong character. The enhancement is a
    column and is added by the engine."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


@power(
    "i3472p2",
    level=7,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack((INT, CON, CHA), vs=REF),
)
def i3472p2(c: Cast) -> None:
    """"Creatures in the blast" is everybody, allies included. The three
    abilities are the tuple form of `Attack.ability`, as on i3472p1."""
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
)
def i1237p1(c: Cast) -> None:
    """Bank a forced reroll against the creature you just hit.

    **The gap was `ev=` and it has arrived.** `c.reroll_attack` read the
    roll off `c.trigger` and nothing else, so it meant something only
    inside a row the dispatcher offered for that one roll. This card stores
    a reroll and spends it later, from a `c.watch` on somebody else's
    attack, where `c.trigger` is still the free action that drank it.

    Three narrowings, and the card states each:

    * **that creature.** "The target you hit" -- not any enemy, so the
      watch closes over `foe` rather than asking who is attacking.
    * **against you.** `ev.target == c.me`; a roll it makes at an ally is
      not this.
    * **at any one time.** `once=True`, and `When.ENCOUNTER` is the card's
      own span.

    `keep="new"` is "it must use the new result" -- the reroll may be
    *better* for the enemy and the card accepts that, which is why this is
    not `worst`. The choice to spend it is the holder's, so `c.may` is
    asked on the holder's side rather than the victim's.
    """
    foe = c.target

    def forced(ev: Any) -> None:
        if getattr(ev, "attacker", None) != foe:
            return
        if getattr(ev, "target", None) != c.me:
            return
        if c.may("force that attack to be rolled again"):
            c.reroll_attack(ev=ev, keep="new")

    c.watch(AttackRolled, forced, until=When.ENCOUNTER, on=c.me,
            once=True, label=c.ref)


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
    """**The symbol stays and its reason was wrong.** "Nothing edits a
    power" states a facility gap; what is owed is an *edit*, and #550
    settled that a clause naming one power is written into that power's
    body rather than reached from outside it.

    `p259` lays the hold this card changes inside a `MoveEnd` watch of its
    own -- immobilized, save ends, for a creature that ends its move in the
    zone -- and that clause alone is what the card swaps, not the hit line
    above it, which applies the same condition and is left as printed. So
    the work is one branch in `powers/wizard/level_5.py`, gated on the
    caster holding this item, which `c.held(on=..., what="magic")` answers
    through `Weapon.item`. The reader exists; the branch does not.

    `c.pre_empt(ref, what, clause)` is the sanctioned route for a clause
    reaching into a named row and still needs that file: `what=` is read by
    the row itself with `c.instead_of`, and `p259` calls neither.

    So the symbol is a stand-in for work this file cannot do -- the same
    reading `i1098x1` above records, for the same reason, since a marker
    cannot name a file. Said plainly so the next reader does not go and
    build a power-editing facility, which is the thing #550 decided
    against."""


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
    push is measured from the ally.

    **Marker confirmed rather than re-derived.** `c.area_origin()` is the
    *writer* half of a split `i1832x1` records: a row that **reads** another
    use's origin keeps an event field instead, and only a row that **moves**
    one keeps this. This row declares a real area -- `reach=AreaBurst(1, 10)`
    -- so it is one of the two legitimate holders.

    And the aim is settled before any body could speak: `dsl.use` calls
    `_auto_targets`, which walks `aim_points` and keeps whichever origin
    catches the most creatures, then hands the result to the `Cast`. So
    `c.origin` is already decided by the time this row runs, which is why
    this is a header-time gap and not a verb the body can call.
    `dsl.use(origin=)` is the parameter that exists for a caller who knows
    where to aim; a dispatched trigger has nobody to pass it."""
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
)
def i1577x1(c: Cast) -> None:
    """**Written. The marker asserted an absence and was looking at the
    wrong event.** It said "`DamageApplied` carries the total only", which
    is true and is not where the dice are: `DamageRolled` carries the live
    `rng.Roll` beside its total as a plain attribute, so the faces that
    came up and the expression they came from are both in hand.
    `_maximum_damage` above is the whole argument, including the critical,
    which reaches the ceiling without rolling anything.

    "With an implement power" is the keyword, which is printed, so this is
    one of the real gates the module docstring's second judgement allows --
    `by_keyword` reads it off the row that dealt the blow, which is
    `DamageRolled.detail`.

    "To an enemy" is asked of the creature being hit rather than assumed:
    a burst of the caster's own can catch an ally, and marking an ally is
    not a smaller version of this card, it is a different one.

    Watched on `DamageRolled` and not on `DamageApplied`, for two reasons
    rather than convenience. The faces only exist on the first. And a
    blow turned aside never reaches this handler at all: `DamageRolled` is
    a `Decision`, `c.watch` subscribes in `Window.AFTER`, and `Bus.emit`
    skips that window outright once an event is cancelled -- so the mark
    cannot be laid for damage that did not happen. What it does not wait
    for is resistance eating the number, which is right: the card is about
    the roll.

    "Until the end of your next turn" is `c.mark`'s own default and is
    passed anyway, since the default is the thing a reader would have to go
    and check. No `lapses=`: this card prints no engage clause.

    "Using this holy symbol" is the half this file cannot gate, by the
    module docstring's first judgement."""
    me = c.me

    def topped(ev: DamageRolled) -> None:
        if ev.source != me:
            return
        foe = getattr(ev, "target", None)
        if foe is None or _my_side(c.world, me, foe):
            return
        if Keyword.IMPLEMENT not in _keywords_of(getattr(ev, "detail", "")):
            return
        if not _maximum_damage(ev):
            return
        c.mark(on=foe, until=When.EONT)

    c.watch(DamageRolled, topped, until=When.ENCOUNTER, on=me, label=c.ref)


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
    defect=(
        "the player's arcane defiling power is not in the"
        " compendium: 0 Power or ClassFeature rows name it,"
        " and the 2 Power rows whose names mention defiling"
        " are paragon powers that consume it (#878)"
    ),
)
def i1942x1(c: Cast) -> None:
    """Temporary hit points whenever an ally takes necrotic damage from
    the holder's defiling.

    **Re-aimed off `c.class_feature()`**, which was wrong twice and the
    same way `f3190` and `i580x1` were. It is not a class feature: the
    prerequisite parser files the ability under `q39`, `kind = 'power'`,
    six feats share that term, and `game.db` holds no row of any kind
    for it -- 0 in `power`, 0 in `class_feature`. So there is no `cf:`
    ref to read and a general feature reader would not help.

    What this clause rides on is the **act** of defiling, which nothing
    announces, so the hook is the gap and `c.on_defiling()` is the one
    five other rows already wait on."""


@power(
    "i1942p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    defect=(
        "the player's arcane defiling power is not in the"
        " compendium: 0 Power or ClassFeature rows name it,"
        " and the 2 Power rows whose names mention defiling"
        " are paragon powers that consume it (#878)"
    ),
)
def i1942p1(c: Cast) -> None:
    """The printed trigger is a use of the holder's defiling, which nothing
    announces, so the row cannot be declared at all.

    **Re-aimed off `c.class_feature()`** -- see `i1942x1` above for the
    lookup. The payout half is already here: "necrotic damage equal to
    half your healing surge value" is `c.surge_value() // 2`. Only the
    trigger is missing, so one symbol names the whole gap."""


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
    todo=("durations.When.EOTAN",),
)
def i2323x1(c: Cast) -> None:
    """**Re-pointed off `c.extend_effect()`, which named a door onto a rung
    that does not exist.**

    Finding the effects is not the problem, and neither is re-clocking one.
    `c.resist` labels its hold `"<ref> resist"` and a label leads with the
    laying row's ref, so "resistance granted by your artificer powers" is
    readable off `world.effects.of(c.me)`; and `i1960p1` and `p5052` both
    write `effect.when`, `effect.clock` and `effect.latch` from a body, so
    a `Cast` door was never the thing missing.

    The duration is, and it is a **rung**. Both of those precedents move
    `When.EOT` to `When.EONT`, which the ladder already has. This card asks
    for the end of the caster's turn on the round *after* next, and `When`
    has no such value: the ladder is EOT, EONT, SONT, EOTNT, SOTNT, and
    EONT is already the top of it for a source-clocked hold.

    Spelled `durations.When.` and not a bare `When.`, because that is the
    only form that can ever go green: `blocked._surface` indexes the enum
    under its module, and neither `triggers` nor `events` re-exports it, so
    a bare `When.X` resolves against nothing for ever. #1231.

    **`Effect.latch` is not the cheap way out, and the two rows this card
    is about are what show it.** `latch` is a bool consumed by one turn
    end, so setting it buys exactly one extra round and only on a hold that
    did not already have it. Of the two artificer rows granting resistance
    `until=When.EONT`, `p10195` is an immediate interrupt and so lands on
    somebody else's turn -- `latch` False, where the bool would work --
    and `p4145` is a standard action on the caster's own turn, where
    `latch` is already True and setting it does nothing. Half the cases is
    worse than none here, because nothing would report the other half.

    The premise holds either way: there are two rows in the tree for this
    to lengthen, and both are heroic."""


@power(
    "i2323p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=YOU_AND_EACH_ALLY,
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
    # The printed trigger names the pact's boon, and that heading became a
    # ref's printed name when #586 imported the builds -- so the words a
    # player is shown are the moment itself, which is what `Trigger` below
    # already says. The pact is still carried, by `_boon_drop("star")`.
    trigger="an enemy you cursed drops",
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
    target=NO_TARGET,
    trigger="an enemy you cursed drops",
    on=Trigger(Dropped, _boon_drop("star"), "an enemy you cursed drops"),
)
def i2343p2(c: Cast) -> None:
    """The rod's enhancement, added to what the pact pays.

    **The line this row waited for landed in the other file.** Its own note
    said so: "the one content line that would close this is in
    `features/warlock.py` and not in this one". `cf:warlock-f1c10` pays the
    star pact's boon and hard-coded its `1`, so there was no number to add
    to -- which is the `change_amount` family's whole argument, and the
    commonest bug in it is the mirror image, a `change_amount` on a body
    that still hard-codes. That body now reads
    `c.amount_for("cf:warlock-f1c10", 1)`.

    **The new value, not a delta.** `change_amount` names what the mechanic
    hands out and `amount_for` takes the largest, so "add the enhancement
    bonus of this rod to the bonus your pact gives you" is `1 +
    c.enhancement` -- the printed 1 plus the rod's own number, which is why
    the `+2` and `+3` printings are one row.

    The trigger is `i2343p1`'s, and for the reason its note gives: the
    printed heading names the pact's boon, which became a ref's printed name
    when #586 imported the builds, so the words a player is shown are the
    moment itself. `_boon_drop("star")` carries the pact."""
    c.change_amount("cf:warlock-f1c10", 1 + c.enhancement, until=When.EONT)


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
)
def i2640p1(c: Cast) -> None:
    """**The trigger is written, and `c.grant_action(trigger=)` was a false
    marker.** The verb carries the *cost*; the condition is the **watch that
    lays it**, which is how `f3210` and `f3204` both hang an off-turn grant
    on something happening. So the offer goes up when one of these creatures
    is hit instead of standing open to all of them for two turns whatever
    happens.

    "A melee or ranged attack" is the attacking row's own
    `reach_of(0).kind`, the narrower half of what `_is_melee` above asks: a
    close or area attack is neither and must not arm it.

    The pool is read **inside** the watcher, so a creature called up after
    this row fires is covered for the rest of the window rather than
    snapshotted out of it.

    What stays approximate, and it is `c.grant_action`'s shape rather than
    this row's: `actions.legal` builds the menu for the creature whose turn
    it is, so an interrupt-cost grant is spent at the holder's first
    opportunity inside the window rather than in the interrupt window
    itself. Every grant in the tree is offered that way.

    Still dropped: `c.summon` records no relation, so "summoned by your
    artificer powers" is the servants and companions the board does hold.
    """
    def struck(ev: Any) -> None:
        who = getattr(ev, "target", None)
        if who is None or who not in _my_summons(c):
            return
        p = get(getattr(ev, "power", "") or "")
        if p is None or p.reach_of(0).kind not in ("melee", "ranged"):
            return
        c.grant_action("shift", INTERRUPT, squares_=2, on=who, until=When.EONT)

    c.watch(Hit, struck, until=When.EONT, on=c.me, label=f"{c.ref} struck")


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
