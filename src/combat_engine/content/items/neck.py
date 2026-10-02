"""Neck-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares an amulet, a cloak or a brooch. The ladder, the price
and the enhancement bonus are columns in `game.db`, and a neck item's plus
reaches Fortitude, Reflex and Will as three `Mod`s laid by
`engine/equipment.py` -- so an item whose whole printed content is "+N to
your defences" has no block here at all. `c.enhancement` reads the plus back
at run time; the number never appears as a literal.

Four judgements run through the file.

* **A saving throw carries its keywords after all.** `Effects.save` builds
  `actor`, `label`, `conditions`, `ongoing`, `dtype`, `dtypes` and
  **`keywords`** -- the last read back off the laying row through
  `durations.keywords_of`. So "against charm, fear or illusion effects",
  the single commonest line in this slot, is a gate and not a gap, and
  every block below says it with `_saves_against(keywords=...)`.
* **A skill check has no target.** `SkillCheck` is `actor`, `skill`, `dc`
  and the roll, so "Heal checks to administer first aid **to you**" and
  "Intimidate checks **except against gargoyles**" cannot be narrowed. The
  bonus itself is ordinary: `c.bonus("skill:heal", n)`.
* **`kind="enhancement"` is spoken for on Fortitude, Reflex and Will.**
  `equipment._defence_mods` writes the neck's own plus there and two of a
  kind do not stack, so every defence bonus below is `item`, `power` or
  untyped, exactly as the card prints it.
* **A Property is a trait, armed once at the start of each fight.** So
  `until=When.ENCOUNTER` is its natural duration and `c.bonus` is the right
  tool; the standing modifiers that have to survive the fight are the ones
  `equipment.py` lays, and none of those are written here.

Two verbs the slot kept asking for both arrived, and the blocks that named
them are written now. An end that is not a duration -- "until an attack
hits you", "until you leave your space", "until you attack it" -- is
`c.watch` plus `c.end_effect(hold)`, holding the effect a `c.bonus` handed
back. The printed failure case "you don't expend the use of this power" is
`c.restore_use(c.ref)`, since `dsl.use` counts the use above the body.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Companion,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    EffectApplied,
    Fell,
    Healed,
    Health,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    Moved,
    Powers,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    SurgeSpent,
    Trigger,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    by_ranged,
    either,
    get,
    power,
    query,
    targets_me,
)
from combat_engine.engine.durations import keywords_of

ITEM = "item"

_ALL_DEFENCES = (AC, FORT, REF, WILL)

#: The conditions a save can end, for "you end one condition that a save can
#: end". `Effects` keys a hold by the conditions it carries, so the question
#: is asked of the creature rather than of a list of effects.
_SAVE_ENDS = (
    Condition.BLINDED,
    Condition.DAZED,
    Condition.DOMINATED,
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.SLOWED,
    Condition.STUNNED,
    Condition.WEAKENED,
)

_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


# -- shared shapes ----------------------------------------------------------


def _defences(c: Cast, value: int, **kw: Any) -> None:
    """"A bonus to all defences" is four modifiers; there is no key for the
    set, and inventing one would not be read by `query.defence`."""
    for d in _ALL_DEFENCES:
        c.bonus(d, value, **kw)


def _foe(c: Cast) -> int | None:
    """The other creature in the event this row is answering.

    `Triggers._at` aims a single-target enemy row at `ev.attacker`, which is
    wrong for half the shapes here -- a row answering a `Dropped` or a
    `SavingThrow` has no attacker at all. Reading the event is the only
    thing that is right every time.
    """
    ev = c.trigger
    for name in ("attacker", "source", "actor"):
        who = getattr(ev, name, None)
        if who is not None and who != c.me:
            return who
    return c.target


def _enemy(world: World, me: int, who: int | None) -> bool:
    if who is None or who == me:
        return False
    return query.team(world, who) is not query.team(world, me)


def _friend(world: World, me: int, who: int | None) -> bool:
    if who is None or who == me:
        return False
    return query.team(world, who) is query.team(world, me)


def _surges(c: Cast) -> int:
    health = c.world.get(c.me, Health)
    return 0 if health is None else health.surges


def _against(who: int | None):  # noqa: ANN202
    """Attack or damage gate: this one is aimed at the named creature."""

    def gate(ctx: dict[str, Any]) -> bool:
        return who is not None and ctx.get("target") == who

    return gate


def _keyworded(*words: Keyword):  # noqa: ANN202
    """Attack gate: the power being resolved prints one of these."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and bool(wanted & set(p.keywords))

    return gate


def _with_advantage(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("advantage"))


def _far_ranged(c: Cast):  # noqa: ANN202
    """Defence gate: a ranged attack from more than five squares off. The
    attack context carries `ranged` and `attacker`, so both halves are
    askable; the damage context carries neither."""

    def gate(ctx: dict[str, Any]) -> bool:
        if not ctx.get("ranged"):
            return False
        who = ctx.get("attacker")
        return who is not None and query.distance_between(c.world, c.me, who) > 5

    return gate


def _saves_against(*conditions: Condition, dtype: DamageType | None = None, keywords: tuple[Keyword, ...] = ()):  # noqa: ANN202, E501
    """Save gate: the effect being saved against holds one of these
    conditions, burns with that damage type, or was laid by a row
    printing one of those keywords -- `durations.keywords_of` reads them
    back off the effect's label."""
    wanted = set(conditions)
    words = set(keywords)

    def gate(ctx: dict[str, Any]) -> bool:
        if wanted & set(ctx.get("conditions") or ()):
            return True
        if words & set(ctx.get("keywords", ())):
            return True
        return dtype is not None and ctx.get("dtype") is dtype

    return gate


def _labelled(ref: str):  # noqa: ANN202
    """Save gate: this is a save against something *that power* laid. The
    save context carries the effect's label, and a hold laid by a row is
    labelled with the row's ref."""

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("label") == ref

    return gate


def _poisoned_save(ctx: dict[str, Any]) -> bool:
    return ctx.get("dtype") is DamageType.POISON


def _death_save(c: Cast, value: int) -> None:
    """A standing bonus to death saving throws.

    `turns._death_saves` rolls with `bonus=0` and consults no modifier, so
    `c.bonus("save", ...)` cannot reach it. It does announce the throw and
    read the answer back, which is where this goes.
    """

    def rider(ev: SavingThrow) -> None:
        if ev.actor != c.me or ev.against != "death":
            return
        ev.bonus += value
        ev.saved = ev.natural + ev.bonus >= 10

    c.watch(SavingThrow, rider, until=When.ENCOUNTER, on=c.me)


# -- predicates -------------------------------------------------------------


def _i_failed(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and not getattr(ev, "saved", True)


def _ally_failed_within_10(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if not _friend(world, me, who) or getattr(ev, "saved", True):
        return False
    return query.distance_between(world, me, who) <= 10


def _my_check(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me


def _my_social_check(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "skill", "") in (
        "bluff",
        "diplomacy",
    )


def _save_ends_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "save_ends", False)


def _my_save_ends_effect(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and getattr(ev, "save_ends", False)


def _condition_on_me(*conditions: Condition):  # noqa: ANN202
    wanted = set(conditions)

    def check(world: World, me: int, ev: Any) -> bool:
        return (
            getattr(ev, "target", None) == me
            and getattr(ev, "condition", None) in wanted
        )

    return check


def _adjacent_enemy_hits_me(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if getattr(ev, "target", None) != me or not _enemy(world, me, who):
        return False
    return query.distance_between(world, me, who) <= 1


def _adjacent_enemy_misses_me(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if getattr(ev, "target", None) != me or not _enemy(world, me, who):
        return False
    return query.distance_between(world, me, who) <= 1


def _adjacent_ally_hit(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if not _friend(world, me, who):
        return False
    return query.distance_between(world, me, who) <= 1


def _ally_bloodied_one(world: World, me: int, ev: Any) -> bool:
    """An ally within 10, not the wearer, put an enemy past the line."""
    who = getattr(ev, "source", None)
    return (
        _enemy(world, me, getattr(ev, "actor", None))
        and who is not None
        and who != me
        and query.team(world, who) is query.team(world, me)
        and query.distance_between(world, me, who) <= 10
    )


def _not_melee(world: World, me: int, ev: Any) -> bool:
    """An area, close or ranged attack -- everything a reach does not cover.
    `Range.kind` is the one field that says which shape arrived."""
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach is not None and p.reach.kind != "melee"


def _melee_or_ranged(ref: str) -> bool:
    """A single-target swing or shot, which is what "targeted by a melee or
    a ranged attack" means -- a burst is neither."""
    p = get(ref or "")
    return p is not None and p.reach is not None and p.reach.kind in ("melee", "ranged")


def _companions_of(world: World, me: int) -> list[int]:
    """The wearer and whatever companion it has on the board.

    `Cast.companion` is this walk and a predicate cannot call it -- it is
    handed the world and an eid and no `Cast` -- but the component it reads
    is right there, so "adjacent to you **or your spirit companion**" is
    declarable rather than dropped.
    """
    mine = [me]
    for eid in world.having(Companion):
        held = world.get(eid, Companion)
        if held is not None and held.owner == me:
            mine.append(eid)
    return mine


def _misses_me_or_my_spirit(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if not _enemy(world, me, who):
        return False
    return any(
        query.distance_between(world, s, who) <= 1 for s in _companions_of(world, me)
    )


def _typed_on_me(*types: DamageType):  # noqa: ANN202
    wanted = set(types)

    def check(world: World, me: int, ev: Any) -> bool:
        return (
            getattr(ev, "target", None) == me
            and getattr(ev, "dtype", None) in wanted
            and getattr(ev, "source", None) not in (None, me)
        )

    return check


def _rolled_with_no_surges(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "actor", None) != me:
        return False
    health = world.get(me, Health)
    return health is not None and health.surges <= 0


def _ally_about_to_be_bloodied(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if not _friend(world, me, who) or query.distance_between(world, me, who) > 5:
        return False
    health = world.get(who, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return health.hp > half >= health.hp - getattr(ev, "amount", 0)


def _hit_from_hiding(world: World, me: int, ev: Any) -> bool:
    foe = getattr(ev, "target", None)
    return getattr(ev, "attacker", None) == me and me in query.hidden_from(world, foe)


def _hit_with_cover(world: World, me: int, ev: Any) -> bool:
    """"While you have any cover or concealment" -- cover is a fact about
    two positions and concealment a modifier the creature carries, so the
    two are asked of different functions."""
    foe = getattr(ev, "target", None)
    if getattr(ev, "attacker", None) != me or foe is None:
        return False
    return bool(
        query.concealment_of(world, me) or query.cover_between(world, foe, me)
    )


_CHARMING = either(
    by_keyword(Keyword.CHARM), by_keyword(Keyword.FEAR), by_keyword(Keyword.PSYCHIC)
)

_CHARM_OR_FEAR = either(by_keyword(Keyword.CHARM), by_keyword(Keyword.FEAR))


# -- level 2 ----------------------------------------------------------------


@power("i1734x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SkillCheck.target",))
def i1734x1(c: Cast) -> None:
    """A Heal check names no patient. Laid as a plain +5 to every ally's
    Heal check it would be five points too large for every other use."""


@power("i2740p1", level=2, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, trigger="a power you could sustain would end",
       dropped=("events.SustainDue",))
def i2740p1(c: Cast) -> None:
    """A free action that sustains **is** "you sustain that power without
    using the action normally required": `Effects.sustain` is the same
    door `actions.run` goes through for a paid sustain, and
    `actions._sustaining` only offers that one while the creature can
    still afford the cost -- which is the hole this power fills.

    Only the wearer's own holds, only ones with a cost printed on them,
    and only ones not already sustained this round, which is the same
    three tests the paid action makes.

    Dropped: the trigger. Nothing announces a sustainable effect reaching
    its last round, so the row is offered as a free action rather than
    declared against the moment the card names."""
    mine = [
        e for e in c.world.effects.live.values()
        if e.source == c.me and e.sustain_cost is not None
        and not e.ended and e.sustained < c.world.round
    ]
    pick = c.choose(mine, "which effect is sustained for free")
    if pick is not None:
        c.world.effects.sustain(pick)


@power("i2997x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2997x1(c: Cast) -> None:
    """Gaze is a keyword and the save context now carries the laying
    row's. "Affects your eyes or sight" is taken as blinded, the only
    sight condition there is; "originates in the attacker's eyes" is
    printed as DM discretion and is not a mechanic to gate on."""
    c.bonus("save", c.enhancement, on=c.me, until=When.ENCOUNTER,
            kind="item",
            when=_saves_against(Condition.BLINDED, keywords=(Keyword.GAZE,)))


@power("i2997p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def i2997p1(c: Cast) -> None:
    """"An effect against which this item grants a bonus to saving throws"
    is the property above: a hold that blinds, or one a gaze row laid.

    `c.save` walks the live effects and acts on `When.SAVE_ENDS` alone,
    which is the one thing this power is the exception to -- so the throw
    is rolled `bare` against the hold's own label, and the hold is ended
    by hand when it lands. Rolling it bare is also what puts the label in
    the save context, so the property's own bonus is read."""
    held = [
        e for e in c.world.effects.of(c.me)
        if not e.ended
        and (Condition.BLINDED in e.conditions
             or Keyword.GAZE in keywords_of(e.label))
    ]
    pick = c.choose(held, "which effect the saving throw is against")
    if pick is not None and c.save(on=c.me, bare=True, against=pick.label):
        c.end_effect(pick)


@power("i3238x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3238x1(c: Cast) -> None:
    """How long a corpse stays raisable is a thing between fights."""


@power("i3245x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.charging()",))
def i3245x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so half of the gate is
    exact. The other half is not: `actions.run` walks a charge's path with
    the ordinary `walk`, so the openings it provokes are indistinguishable
    from any other step and `c.charge` is asked of a *use* that has not
    happened yet. Marked rather than dropped because the whole benefit is
    the narrowing -- standing +4 against every opportunity attack in the
    fight is a strictly better item than the printed one."""


@power("i488x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i488x1(c: Cast) -> None:
    def crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        c.save(on=c.me, bonus=c.enhancement)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


@power("i489p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a power that produces an effect a save can end",
       on=Trigger(EffectApplied, _my_save_ends_effect,
                  "a save-ends effect of yours lands"))
def i489p1(c: Cast) -> None:
    """"Each target of the power" is read as everybody currently carrying
    one of my holds: the trigger fires once per target, and the daily
    should not have to be spent once per target to cover them all."""
    for who in c.suffering():
        c.penalty("save", c.enhancement, on=who, until=When.SAVE_ENDS, once=True)


@power("i496x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i496x1(c: Cast) -> None:
    """Three keywords, read off the row that laid the effect."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_saves_against(keywords=(Keyword.CHARM, Keyword.ILLUSION,
                                          Keyword.SLEEP)))


@power("i497x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i497x1(c: Cast) -> None:
    """Three conditions the hold carries, plus poison by the laying row's
    keyword -- with the burn's own type kept as the fallback for an
    ongoing poison laid by a row that prints none."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_saves_against(Condition.WEAKENED, Condition.SLOWED,
                                Condition.IMMOBILIZED, dtype=DamageType.POISON,
                                keywords=(Keyword.POISON,)))


@power("i500p1", level=2, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you fail a saving throw",
       on=Trigger(SavingThrow, _i_failed, "you fail a saving throw"))
def i500p1(c: Cast) -> None:
    """"Even if it's lower" is `keep="new"`, which is the default."""
    c.reroll_save()


@power("i585x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i585x1(c: Cast) -> None:
    """"When you charge, your movement made as part of the charge doesn't provoke."

    The charge's own movement can be told apart now: `actions.execute` passes
    `kind="charge"` to `walk`, so `ctx["kind"]` says so and the rest of the
    creature's walking still provokes (#301).

    Laid for the encounter rather than armed per charge, which the card allows --
    it is a property of wearing the amulet, and the gate is what makes it narrow
    rather than the duration."""
    c.no_provoke(on=c.me, until=When.ENCOUNTER,
                 when=lambda ctx: ctx.get("kind") == "charge")


@power("i912p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i912p1(c: Cast) -> None:
    c.resist(5, on=c.me, until=When.SONT)


# -- level 3 ----------------------------------------------------------------


@power("i1424x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.light_level(world, square)",))
def i1424x1(c: Cast) -> None:
    """Light is not on the board, so "in dim light or darkness" is a gate
    that would be false in every fight."""


@power("i1424p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(10), target=SELF, keywords=[Keyword.ZONE],
       todo=("c.light()",))
def i1424p1(c: Cast) -> None:
    """A zone whose whole content is the light level in it, and light is
    not a thing the board has -- neither making it nor reading it. Laid as
    a zone with no rider it would be a shape nothing consults. Named for
    the verb the other eight rows of this shape want."""


@power("i1904x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1904x1(c: Cast) -> None:
    """Opening a lock is not a thing a fight contains."""


@power("i1904p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i1904p1(c: Cast) -> None:
    """A grab is held by reach, so being three squares away ends it; being
    restrained is a save-ends hold and survives the trip, which is why only
    the one condition is cured."""
    if not (c.is_(Condition.GRABBED, on=c.me) or c.is_(Condition.RESTRAINED, on=c.me)):
        return
    if c.teleport(3):
        c.cure(Condition.GRABBED, on=c.me)


@power("i2003x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2003x1(c: Cast) -> None:
    c.bonus("skill:perception", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2003p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2003p1(c: Cast) -> None:
    """Written as a defence bonus that appears exactly when the attacker has
    combat advantage, which cancels the printed +2 and leaves every other
    benefit standing. `c.no_advantage` would take the advantage itself
    away, which is a different and larger sentence."""
    _defences(c, 2, on=c.me, until=When.ENCOUNTER, when=_with_advantage)


@power("i2109p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2109p1(c: Cast) -> None:
    c.resist(10 if c.spend_points(1) else 5, on=c.me, until=When.SONT)


@power("i2378x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2378x1(c: Cast) -> None:
    """`Fell.soften` is damage, not distance, and `falling` charges 10 a
    square -- so ten feet of shortened drop is two squares' worth. The
    landing on your feet is `Fell.prone`."""

    def caught(ev: Fell) -> None:
        if ev.actor != c.me:
            return
        ev.soften += 20 * c.enhancement
        ev.prone = False

    c.watch(Fell, caught, until=When.ENCOUNTER, on=c.me)


@power("i2580p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2580p1(c: Cast) -> None:
    c.mode("climb", c.speed_of(), on=c.me, until=When.EOT)


@power("i3246x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, narrative=("skill:endurance",))
def i3246x1(c: Cast) -> None:
    """Disease is a keyword of the row that laid the hold, so the save
    half is exact. The other half is the disease track between fights --
    an endurance check made over days, which a board that runs for a
    handful of rounds has no moment for."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_saves_against(keywords=(Keyword.DISEASE,)))


@power("i492x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i492x1(c: Cast) -> None:
    c.resist(2 * c.enhancement, DamageType.POISON)


@power("i504p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally adjacent to you is hit by an attack",
       on=Trigger(Hit, _adjacent_ally_hit, "an adjacent ally is hit"))
def i504p1(c: Cast) -> None:
    ally = getattr(c.trigger, "target", None)
    if ally is not None:
        _defences(c, c.enhancement, on=ally, until=When.SONT, kind="power")


@power("i586p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.TELEPORTATION],
       trigger="an enemy adjacent to you misses you with a melee attack",
       on=Trigger(Miss, both(_adjacent_enemy_misses_me, by_melee),
                  "an adjacent enemy misses you in melee"))
def i586p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.swap(foe)


@power("i821p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=Ranged(10), target=NO_TARGET,
       trigger="an ally within 10 squares fails a saving throw",
       on=Trigger(SavingThrow, _ally_failed_within_10,
                  "an ally within 10 squares fails a save"))
def i821p1(c: Cast) -> None:
    """`c.reroll_save` acts on the triggering throw, which is the ally's --
    the bonus rides the event rather than being laid on anybody."""
    c.reroll_save(bonus=2)


@power("i822x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i822x1(c: Cast) -> None:
    c.resist(10, DamageType.FORCE)


@power("i822p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by an area, close or ranged attack",
       on=Trigger(AttackDeclared, both(targets_me, _not_melee),
                  "an area, close or ranged attack reaches you"))
def i822p1(c: Cast) -> None:
    """"Equal to the brooch's resist force value" is the property above,
    which is a printed 10 and not the enhancement."""
    c.resist(10, on=c.me, until=When.EOT)


@power("i917x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i917x1(c: Cast) -> None:
    c.bonus("skill:heal", c.enhancement, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i917p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE)
def i917p1(c: Cast) -> None:
    ally = next((a for a in c.within(1, side="ally") if a != c.me), None)
    if ally is not None:
        c.regain_surge(1, on=ally)


# -- level 4 ----------------------------------------------------------------


@power("i1095p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by a fire, force, lightning, psychic, radiant or "
               "thunder attack",
       on=Trigger(DamageApplied,
                  _typed_on_me(DamageType.FIRE, DamageType.FORCE,
                               DamageType.LIGHTNING, DamageType.PSYCHIC,
                               DamageType.RADIANT, DamageType.THUNDER),
                  "one of six damage types reaches you"))
def i1095p1(c: Cast) -> None:
    """`DamageApplied` rather than `Hit`, because the printed list is of
    damage types and only the damage event carries one."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


@power("i1220x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1220x1(c: Cast) -> None:
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i1220p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1220p1(c: Cast) -> None:
    c.bonus("skill:stealth", 5, on=c.me, until=When.EONT, kind="power", once=True)


@power("i1365x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1365x1(c: Cast) -> None:
    c.resist(5, DamageType.COLD)


@power("i1365p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy adjacent to you hits you",
       on=Trigger(Hit, _adjacent_enemy_hits_me, "an adjacent enemy hits you"))
def i1365p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.prone(on=foe)


@power("i1523x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1523x1(c: Cast) -> None:
    """`Healed` is announced before the hit points go on and its `amount` is
    read back afterwards, which is the seam this needs. The source is the
    healer, so an ally's own regeneration is left alone."""

    def more(ev: Healed) -> None:
        if ev.source != c.me:
            return
        ev.amount += c.enhancement

    c.watch(Healed, more, until=When.ENCOUNTER, on=c.me)


@power("i1759p1", level=4, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with an attack or fail a check or a saving throw",
       on=(Trigger(Miss, by_me, "you miss with an attack"),
           Trigger(SkillCheck, _my_check, "you make a skill check"),
           Trigger(SavingThrow, _i_failed, "you fail a saving throw")))
def i1759p1(c: Cast) -> None:
    """Three rolls, three seams. The check is `c.boost_check` and the save
    is the `SavingThrow` read-back.

    The attack is the live `AttackResult`, which rides on the `Miss` as a
    plain attribute -- the same thing `c.reroll_attack` reaches for, and
    `resolve.attack` re-announces the outcome until it stops changing, so
    a miss raised past the defence becomes a real `Hit` with its riders.
    Raising the total is not rerolling: the die is left alone, which is
    why the critical is not reconsidered."""
    ev = c.trigger
    roll = c.roll("1d6")
    if isinstance(ev, SkillCheck):
        c.boost_check(roll)
    elif isinstance(ev, SavingThrow):
        ev.bonus += roll
        ev.saved = ev.natural + ev.bonus >= 10
    else:
        result = getattr(ev, "result", None)
        if result is not None:
            result.total += roll
            result.hit = (
                result.natural != 1 and result.total >= result.target_defence
            )


@power("i2032x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2032x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON)


@power("i2032p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from a poison attack",
       on=Trigger(DamageRolled, _typed_on_me(DamageType.POISON),
                  "poison damage is rolled against you"))
def i2032p1(c: Cast) -> None:
    """Resistances of one type do not add -- the highest applies -- so the
    increase is laid as the combined number rather than as a second 15."""
    c.resist(20, DamageType.POISON, on=c.me, until=When.EONT)


@power("i3420x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3420x1(c: Cast) -> None:
    """Catching a disease is a thing that happens after the fight."""


@power("i3420p1", level=4, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a shapechanger is hit by your attack",
       on=Trigger(Hit, by_me, "you hit a creature"))
def i3420p1(c: Cast) -> None:
    """`c.forbid` takes one ref and the card names a keyword, so the rows
    are found first: `Powers.all` is what the creature owns and the
    keyword is read off each. Forbidding nothing is the ordinary case --
    most shapechangers print one polymorph row and some print none."""
    foe = _foe(c)
    if foe is None or not c.is_kind("shapechanger", on=foe):
        return
    c.no_healing(on=foe, until=When.SAVE_ENDS)
    powers = c.world.get(foe, Powers)
    for ref in list(powers.all if powers is not None else ()):
        p = get(ref)
        if p is not None and Keyword.POLYMORPH in p.keywords:
            c.forbid(ref, on=foe, until=When.SAVE_ENDS)


@power("i3526x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3526x1(c: Cast) -> None:
    """The gate reads the surge pool at query time rather than at arming
    time, so the bonus arrives the moment the last surge goes."""
    for d in (FORT, REF, WILL):
        c.bonus(d, 1, on=c.me, until=When.ENCOUNTER, kind="item",
                when=lambda _ctx: _surges(c) == 0)


@power("i3526p1", level=4, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative and you have no healing surges",
       on=Trigger(InitiativeRolled, _rolled_with_no_surges,
                  "you roll initiative with no surges left"))
def i3526p1(c: Cast) -> None:
    c.temp_hp(5 * c.enhancement, on=c.me)


@power("i908x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i908x1(c: Cast) -> None:
    _defences(c, c.enhancement, on=c.me, until=When.ENCOUNTER, kind="item",
              when=_far_ranged(c))


@power("i920x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i920x1(c: Cast) -> None:
    """The allies get the shift as an action they may take; the wearer's own
    is taken here, since the row is being resolved on the wearer's behalf."""

    def rallied(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != "p4932":
            return
        c.shift(1)
        for mate in c.within(1, side="ally"):
            if mate != c.me:
                c.grant_action("shift", FREE, on=mate, until=When.EONT)

    c.watch(PowerUsed, rallied, until=When.ENCOUNTER, on=c.me)


@power("i920p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=CloseBurst(5), target=NO_TARGET, keywords=[Keyword.FEAR],
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, by_me, "you drop an enemy"))
def i920p1(c: Cast) -> None:
    """`Dropped` carries `source`, which is what `by_me` reads -- it has no
    `target`, so the creature that fell is `actor`."""
    for foe in c.within(5, side="enemy"):
        c.penalty("attack", 2, on=foe, until=When.EONT)


@power("i923x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i923x1(c: Cast) -> None:
    """Bloodied is asked of the world the second wind was declared in --
    `SecondWind` is announced before the hit points come back, which the
    old `EffectApplied` sniff was not. The extra surge is spent with
    `c.surge`, which heals from it."""

    def winded(ev: SecondWind) -> None:
        if ev.actor == c.me and c.bloodied(on=c.me):
            c.surge(on=c.me)

    c.watch(SecondWind, winded, until=When.ENCOUNTER, on=c.me)


@power("i937x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i937x1(c: Cast) -> None:
    def spent(ev: SurgeSpent) -> None:
        if ev.actor == c.me:
            c.heal(c.enhancement, on=c.me)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=c.me)


# -- level 5 ----------------------------------------------------------------


@power("i3390x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3390x1(c: Cast) -> None:
    """"You can end this effect by removing the cloak as a minor action"
    is `c.endable`, which hangs a minor-action drop on the hold itself and
    offers it to whoever carries it -- so the escape clause costs the
    printed action and takes the burn off, without the engine having to
    model unequipping mid-fight."""

    def fumbled(ev: Any) -> None:
        who = getattr(ev, "actor", getattr(ev, "attacker", None))
        if who != c.me or getattr(ev, "natural", 0) != 1:
            return
        c.endable(c.ongoing(10, DamageType.POISON, on=c.me), MINOR)

    c.watch(AttackRolled, fumbled, until=When.ENCOUNTER, on=c.me)
    c.watch(SavingThrow, fumbled, until=When.ENCOUNTER, on=c.me)


@power("i3390p1", level=5, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       trigger="an adjacent enemy hits you with a melee attack",
       on=Trigger(Hit, both(_adjacent_enemy_hits_me, by_melee),
                  "an adjacent enemy hits you in melee"))
def i3390p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.ongoing(5, DamageType.POISON, on=foe)


@power("i494p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def i494p1(c: Cast) -> None:
    c.surge(on=c.me)


@power("i499x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.save_order()",))
def i499x1(c: Cast) -> None:
    """Which holds it means is answerable now -- charm, fear and psychic
    are keywords `keywords_of` reads back. The whole of the benefit is
    the other half: moving the throw from the end of the turn to the
    start, and suppressing the end-of-turn one after a failure. Rolling
    an extra save at the start instead would be a strictly better item
    than the printed one."""


@power("i499p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.PSYCHIC],
       trigger="an enemy hits or misses you with a charm, fear or psychic power",
       on=(Trigger(Hit, both(targets_me, _CHARMING), "one of those hits you"),
           Trigger(Miss, both(targets_me, _CHARMING), "one of those misses you")))
def i499p1(c: Cast) -> None:
    """"Hits or misses" is two events, and `on=` takes both -- declaring one
    of them would look finished and answer half the printed trigger."""
    foe = _foe(c)
    if foe is not None:
        c.flat(10, dtype=DamageType.PSYCHIC, on=foe)


@power("i502x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i502x1(c: Cast) -> None:
    """"A charm effect I imposed" is askable now: `EffectApplied` names the
    source, and its label is the ref of the row that laid the hold, which
    `keywords_of` turns back into keywords.

    `once=True` on a `save` modifier is spent by the holder's next saving
    throw -- the one branch of `c.bonus` that watches `SavingThrow` -- so
    "the first saving throw" is the duration rather than a counter."""
    c.bonus("skill:bluff", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    c.bonus("skill:diplomacy", 2, on=c.me, until=When.ENCOUNTER, kind="item")

    def charmed(ev: EffectApplied) -> None:
        label = ev.label or ""
        if (ev.source != c.me or not ev.save_ends
                or Keyword.CHARM not in keywords_of(label)):
            return
        c.penalty("save", 2, on=ev.target, until=When.ENCOUNTER,
                  once=True, when=_labelled(label))

    c.watch(EffectApplied, charmed, until=When.ENCOUNTER, on=c.me)


@power("i502p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=ONE_CREATURE, keywords=[Keyword.CHARM],
       attack=Attack(CHA, vs=WILL))
def i502p1(c: Cast) -> None:
    """"The amulet's enhancement bonus" is added through `c.strike(plus=)`,
    because the header is data and the plus is a column. The hold ends the
    first time the target takes damage from anything at all, which is the
    printed "from any source".

    The interposition is `AttackDeclared.target`, assigned in the BEFORE
    window: `resolve.attack` reads the target back off the event before it
    rolls, which is the whole of what `c.redirect` does for an interrupt
    answering one. A burst is neither a melee nor a ranged attack and is
    left alone."""
    if not c.strike(plus=c.enhancement):
        return
    foe = c.target
    charmed = c.cannot_attack(against=c.me, until=When.SAVE_ENDS)

    def struck(ev: DamageApplied) -> None:
        if ev.target == foe and charmed is not None and not charmed.ended:
            c.end_effect(charmed)

    def interpose(ev: AttackDeclared) -> None:
        if charmed is None or charmed.ended or ev.target != c.me:
            return
        if ev.attacker == foe or not _melee_or_ranged(ev.power):
            return
        if foe is not None and c.adjacent(foe):
            ev.target = foe

    c.watch(DamageApplied, struck, until=When.ENCOUNTER)
    c.watch(AttackDeclared, interpose, until=When.ENCOUNTER,
            window=Window.BEFORE)


@power("i832p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.TELEPORTATION],
       trigger="you are hit by an attack",
       on=Trigger(Hit, targets_me, "you are hit"))
def i832p1(c: Cast) -> None:
    foe = _foe(c)
    c.teleport(5)
    if foe is not None:
        c.grants_advantage(on=foe, to="me", until=When.EONT)


# -- level 7 ----------------------------------------------------------------


@power("i1052x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1052x1(c: Cast) -> None:
    """Carrying capacity only."""


@power("i1052p1", level=7, cls=ITEM, action=FREE, reach=PERSONAL,
       target=SELF, once_per_round=True, out_of_combat=True)
def i1052p1(c: Cast) -> None:
    """Drawing and stowing gear is not modelled."""


@power("i1201x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1201x1(c: Cast) -> None:
    c.bonus("skill:stealth", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i1246x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.skill_circumstance()",))
def i1246x1(c: Cast) -> None:
    """`c.set_origin` is exactly "you are considered to have that
    creature's origin and keywords", and `c.endable` is the printed minor
    action that takes it off again.

    The choice is printed as one made between fights; the trait arms once
    a fight, so it is asked then, out of the words the creatures on the
    board actually carry -- a word nobody here has is worth nothing, and
    "if doing so is beneficial" is the card saying the same.

    Dropped: the Bluff bonus, which is narrowed to passing yourself off
    as that creature and a skill check cannot be told what it is for. The
    language half is out of combat."""
    words = sorted({
        word for who in c.within(20) if who != c.me for word in c.kinds_of(on=who)
    })
    pick = c.choose(words, "whose origin and keywords you are taken for")
    if pick is not None:
        c.endable(c.set_origin(pick, on=c.me, until=When.ENCOUNTER), MINOR)


@power("i1290x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1290x1(c: Cast) -> None:
    """The extra damage is fire and carries that type of its own, so a
    creature resisting fire shrugs it off and takes the rest."""

    def burned(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.dtype is not DamageType.FIRE:
            return
        if ev.source in (None, c.me):
            return
        c.bonus("damage", c.enhancement, on=c.me, until=When.EONT,
                once=True, dtype=DamageType.FIRE)

    c.watch(DamageApplied, burned, until=When.ENCOUNTER, on=c.me)


@power("i2406x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("chargen.race_choice()",))
def i2406x1(c: Cast) -> None:
    """Two of the three clauses name a creature word `c.is_kind` can read.
    The third names a race by ref, and a character's race is a build-time
    choice with no word on the board."""

    def beside(word: str) -> bool:
        return any(c.is_kind(word, on=a) for a in c.within(10, side="ally")
                   if a != c.me)

    if beside("drow"):
        c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER, kind="item")
        c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    if beside("elf"):
        c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER, kind="item")
        c.bonus("skill:nature", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i2818x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2818x1(c: Cast) -> None:
    """"Ongoing effects of the power" is narrowed on the save context's
    label: a hold laid by a row is labelled with that row's ref, so the
    penalty reaches the fear power's own effects and nothing else."""

    def feared(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None or Keyword.FEAR not in p.keywords:
            return
        for who in ev.targets:
            c.penalty("save", 1, on=who, until=When.ENCOUNTER,
                      when=_labelled(ev.power))

    c.watch(PowerUsed, feared, until=When.ENCOUNTER, on=c.me)


@power("i3567x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3567x1(c: Cast) -> None:
    c.bonus("skill:insight", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3567p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(10), target=SELF, dropped=("c.blindsight()",))
def i3567p1(c: Cast) -> None:
    """Truesight is the half that exists: nothing stays unseen inside it.
    Seeing through a closed door is line of effect, which truesight does
    not waive."""
    c.truesight(10, on=c.me, until=When.EOT)


@power("i505p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i505p1(c: Cast) -> None:
    c.bonus("skill:diplomacy", c.enhancement, on=c.me,
            until=When.EONT, kind="item")
    c.bonus(WILL, c.enhancement, on=c.me, until=When.EONT, kind="item")
    c.bonus("save", c.enhancement, on=c.me, until=When.EONT, kind="item",
            when=_saves_against(keywords=(Keyword.CHARM,)))


@power("i918p1", level=7, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.TELEPORTATION],
       trigger="while bloodied, an enemy adjacent to you misses with a melee "
               "attack",
       on=Trigger(Miss, both(_misses_me_or_my_spirit, by_melee),
                  "an enemy next to you or your companion misses in melee"))
def i918p1(c: Cast) -> None:
    """The trigger is about where the *enemy* is standing, not about who
    it swung at -- "an enemy adjacent to you or your spirit companion
    misses with a melee attack" names no victim. A predicate gets the
    world and the wearer, which is all `Companion` needs to be read."""
    mate = c.companion()
    if mate is None or not c.bloodied(on=c.me):
        return
    foe = _foe(c)
    c.swap(mate)
    if foe is not None:
        c.grants_advantage(on=foe, to="me", until=When.EONT)


# -- level 8 ----------------------------------------------------------------


@power("i1225x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1225x1(c: Cast) -> None:
    """`c.had_advantage` reads the live result off the event; asking
    `has_combat_advantage` again would be too late, since a one-shot grant
    has already been spent by the time the blow lands."""

    def sting(ev: Hit) -> None:
        if ev.target != c.me or not c.had_advantage(ev):
            return
        c.flat(c.enhancement, dtype=DamageType.NECROTIC, on=ev.attacker)

    c.watch(Hit, sting, until=When.ENCOUNTER, on=c.me)


@power("i1492p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Ranged(5), target=NO_TARGET, keywords=[Keyword.TELEPORTATION],
       trigger="an ally within 5 squares would be bloodied by an attack",
       on=Trigger(DamageRolled, _ally_about_to_be_bloodied,
                  "an ally within 5 squares would be bloodied"),
       dropped=("c.item_set()",))
def i1492p1(c: Cast) -> None:
    """"The wearer of the attuned circlet" is a paired item and nothing
    links two items together, so this answers for any ally in range."""
    ally = getattr(c.trigger, "target", None)
    if ally is None:
        return
    c.swap(ally)
    c.absorb(c.trigger)


@power("i2001p1", level=8, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=Ranged(10), target=NO_TARGET,
       trigger="an ally within 10 squares bloodies an enemy",
       on=Trigger(Bloodied, _ally_bloodied_one, "an ally bloodies an enemy"))
def i2001p1(c: Cast) -> None:
    """The temporary hit points go to the ally who struck the blow, which
    `Bloodied.source` now names."""
    who = getattr(c.trigger, "source", None)
    if who is not None:
        c.temp_hp(3 + c.enhancement, on=who)


@power("i2020p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2020p1(c: Cast) -> None:
    """"Until you leave your current space" is not a duration, but it is
    an event: `Moved` names the wearer and carries `from_` and `to`, and
    `c.end_effect` takes the two holds off when they differ. A teleport
    and a shove leave the space as surely as a walk does, which is why
    this watches `Moved` rather than a kind of move."""
    ac = c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="power")
    ref = c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="power")

    def stepped(ev: Moved) -> None:
        if ev.actor != c.me or ev.to == ev.from_:
            return
        for hold in (ac, ref):
            if hold is not None and not hold.ended:
                c.end_effect(hold)

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=c.me)


@power("i2021x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2021x1(c: Cast) -> None:
    c.bonus("skill:diplomacy", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2021p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, keywords=[Keyword.CHARM])
def i2021p1(c: Cast) -> None:
    """The penalty is gated on the attack being aimed at the wearer, which
    is what "against you" means, and on its being a swing or a shot, which
    is the rest of the printed sentence.

    "Or until you attack it" is `AttackDeclared` by the wearer at that
    creature: the hold is ended there rather than run to the end of the
    encounter. Declared, not `once=True`, because the first attack the
    wearer makes is usually at somebody else."""
    foe = c.target
    hold = c.penalty("attack", 2, until=When.ENCOUNTER,
                     when=lambda ctx: (ctx.get("target") == c.me
                                       and _melee_or_ranged(ctx.get("power") or "")))

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or ev.target != foe:
            return
        if hold is not None and not hold.ended:
            c.end_effect(hold)

    c.watch(AttackDeclared, swung, until=When.ENCOUNTER, on=c.me)


@power("i2033x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2033x1(c: Cast) -> None:
    _death_save(c, 2)


@power("i2171p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by an attack that deals ongoing damage",
       on=Trigger(EffectApplied, _save_ends_on_me,
                  "a save-ends effect lands on you"),
       dropped=("EffectApplied.ongoing",))
def i2171p1(c: Cast) -> None:
    """`c.save(against="ongoing")` picks the burn out of whatever else is
    holding the wearer, which is the half the event cannot narrow --
    `EffectApplied` says a save-ends hold landed and not what it carries,
    so the trigger fires wider than the card prints.

    "On a failure, you don't expend the use of this power" is
    `c.restore_use`: `dsl.use` counts the use above the body, so the use
    is there to be handed back. A trigger that fired on a hold with no
    burn in it finds nothing to save against, fails, and refunds -- which
    is why the wide trigger costs nothing."""
    if not c.save(on=c.me, against="ongoing"):
        c.restore_use(c.ref, on=c.me)


@power("i2178x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=CloseBurst(10), target=SELF)
def i2178x1(c: Cast) -> None:
    """A printed Property, not an aura: the company is read once, when the
    trait arms, rather than followed around the board."""
    for who in [c.me, *(a for a in c.within(10, side="ally") if a != c.me)]:
        c.bonus(WILL, 2, on=who, until=When.ENCOUNTER,
                when=_keyworded(Keyword.CHARM, Keyword.FEAR, Keyword.ILLUSION))


@power("i2669p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are dazed or stunned by an attack",
       on=Trigger(ConditionApplied,
                  _condition_on_me(Condition.DAZED, Condition.STUNNED),
                  "you are dazed or stunned"))
def i2669p1(c: Cast) -> None:
    """The throw is against the hold that carries the triggering
    condition, named by the condition rather than by the row that laid
    it. Failing hands the use back, which is the printed price of
    missing."""
    condition = getattr(c.trigger, "condition", None)
    held = next(
        (e for e in c.world.effects.of(c.me)
         if not e.ended and e.when is When.SAVE_ENDS and condition in e.conditions),
        None,
    )
    saved = c.save(on=c.me, against=held.label) if held is not None else c.save(on=c.me)
    if not saved:
        c.restore_use(c.ref, on=c.me)


@power("i873x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i873x1(c: Cast) -> None:
    c.bonus("skill:bluff", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")
    c.bonus("skill:diplomacy", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i873p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you roll a Bluff or a Diplomacy check",
       on=Trigger(SkillCheck, _my_social_check, "you roll Bluff or Diplomacy"))
def i873p1(c: Cast) -> None:
    c.reroll_check()


@power("i964x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i964x1(c: Cast) -> None:
    """Charm and fear are keywords of the row that laid the hold, which
    is what the save context reads back off the effect's label."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_saves_against(keywords=(Keyword.CHARM, Keyword.FEAR)))


@power("i964p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.CHARM],
       trigger="an enemy targets you with a charm or fear power",
       on=Trigger(AttackDeclared, both(targets_me, _CHARM_OR_FEAR),
                  "a charm or fear power is aimed at you"))
def i964p1(c: Cast) -> None:
    """Declared on `AttackDeclared`: by the time it has hit, the target is
    no longer a thing an interrupt can change."""
    others = [w for w in c.within(5) if w != c.me and w != _foe(c)]
    victim = c.choose(others, "who the power lands on instead")
    if victim is not None:
        c.redirect(to=victim)


# -- level 9 ----------------------------------------------------------------


@power("i1683x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1683x1(c: Cast) -> None:
    """The choice is printed as one made after an extended rest; the trait
    arms once a fight, so it is asked once a fight instead."""
    pick = c.choose(list(_ELEMENTS), "which damage type the amulet turns")
    c.resist(5, pick or DamageType.FIRE)


@power("i1683p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=NO_TARGET)
def i1683p1(c: Cast) -> None:
    """"The resistance from the amulet" is not a choice made here -- the
    property above already chose it, so it is read back off the wearer
    with `c.resistances` rather than asked again.

    "Losing that resistance yourself" is the property's own hold, which
    `c.resist` labels with the row that laid it, so `c.end_effect` finds
    it by that label and its `undo` puts back whatever the wearer resisted
    before. Read before the hold is ended, since ending it takes the
    number away."""
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    who = c.choose(mates, "who the resistance passes to")
    if who is None:
        return
    mine = c.resistances(on=c.me)
    pick = next((t for t in _ELEMENTS if mine.get(t)), None)
    amount = mine.get(pick, 5) if pick is not None else 5
    c.end_effect(on=c.me, against="i1683x1 resist")
    c.resist(amount, pick or DamageType.FIRE, on=who, until=When.ENCOUNTER)


@power("i1842p1", level=9, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are reduced to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you drop"))
def i1842p1(c: Cast) -> None:
    """"Per plus" is the enhancement, which is a column."""
    c.heal(3 * c.enhancement, on=c.me)


@power("i1845x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1845x1(c: Cast) -> None:
    """`Healed` is the one announcement a healing power makes about its
    recipient, and the first-aid half of the printed sentence is the same
    clause reached through a skill check the engine does not model."""
    c.bonus("skill:heal", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")

    def mended(ev: Healed) -> None:
        if ev.source != c.me or ev.target == c.me:
            return
        c.save(on=ev.target, against="ongoing")

    c.watch(Healed, mended, until=When.ENCOUNTER, on=c.me)


@power("i2138x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2138x1(c: Cast) -> None:
    c.resist(5, DamageType.COLD)
    c.resist(5, DamageType.NECROTIC)


@power("i2138p1", level=9, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you fail a saving throw",
       on=Trigger(SavingThrow, _i_failed, "you fail a saving throw"))
def i2138p1(c: Cast) -> None:
    """A death save announces itself as `against="death"`, which is the
    only way to tell the two bonuses apart."""
    ev = c.trigger
    death = getattr(ev, "against", "") == "death"
    c.reroll_save(bonus=10 if death else 5)


@power("i2448p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit or miss an enemy you are hidden from",
       on=(Trigger(Hit, _hit_from_hiding, "you hit an enemy you are hidden from"),
           Trigger(Miss, _hit_from_hiding, "you miss an enemy you are hidden from")))
def i2448p1(c: Cast) -> None:
    """Attacking gives a hidden creature away, which `resolve.attack` does
    on its own -- so the row unhides first and then buys the one creature
    back with the check, which is what the printed sentence comes to."""
    foe = _foe(c)
    if foe is None:
        return
    kept = c.check("stealth", c.passive("perception", of=foe))
    c.unhide()
    if kept:
        c.hide(from_=foe)


@power("i3239x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_miss_damage(half=)",))
def i3239x1(c: Cast) -> None:
    """`deal_damage` is handed a `miss` flag and keeps it out of the damage
    context, so the only reader is the all-or-nothing `no_miss_damage` mod;
    halving needs the flag where a gate can see it."""


@power("i3248x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3248x1(c: Cast) -> None:
    c.bonus("skill:stealth", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3248p1", level=9, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ILLUSION],
       trigger="you hit a creature while you have cover or concealment",
       on=Trigger(Hit, _hit_with_cover, "you hit from cover"))
def i3248p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.invisible(to=foe, on=c.me, until=When.SAVE_ENDS)


@power("i3423x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3423x1(c: Cast) -> None:
    """Forest walk is difficult terrain of one kind ignored; the Stealth
    bonus is gated on the fight being had in a forest at all."""
    c.ignores_difficult("forest", on=c.me, until=When.ENCOUNTER)
    if c.terrain("forest"):
        c.bonus("skill:stealth", c.enhancement, on=c.me,
                until=When.ENCOUNTER, kind="item")


@power("i3423p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i3423p1(c: Cast) -> None:
    """`c.end_effect` ends a hold outright, with no throw, which is what
    "you can end one poison effect" prints. A poison effect is one that
    burns with poison or one a poison row laid -- the two ways the engine
    can see the word -- and the choice is the card's "one"."""
    c.surge(on=c.me)
    poisoned = [
        e for e in c.world.effects.of(c.me)
        if not e.ended
        and ((e.ongoing is not None and e.ongoing[1] is DamageType.POISON)
             or Keyword.POISON in keywords_of(e.label))
    ]
    pick = c.choose(poisoned, "which poison effect ends")
    if pick is not None:
        c.end_effect(pick)


@power("i3463x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3463x1(c: Cast) -> None:
    _defences(c, c.enhancement, on=c.me, until=When.ENCOUNTER, kind="item",
              when=_keyworded(Keyword.ACID, Keyword.FIRE, Keyword.COLD,
                              Keyword.THUNDER, Keyword.LIGHTNING))


@power("i3560x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("SkillCheck.target",))
def i3560x1(c: Cast) -> None:
    """A skill check names no subject, so "except against gargoyles" cannot
    be taken back out of the bonus. Being sensed by one is narrative."""
    c.bonus("skill:intimidate", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3560p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH],
       dropped=("c.tremorsense()", "c.restrict_action()"))
def i3560p1(c: Cast) -> None:
    """`c.form` holds the shape and gives back the minor action that ends
    it. What the shape forbids -- everything but a second wind -- and its
    tremorsense are the two clauses with no verb."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label="statue")
    c.resist(20, on=c.me, until=When.ENCOUNTER)

    def hardening(ev: TurnStart) -> None:
        if getattr(ev, "actor", None) == c.me:
            c.temp_hp(5, on=c.me)

    c.watch(TurnStart, hardening, until=When.ENCOUNTER, on=c.me)


@power("i491p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i491p1(c: Cast) -> None:
    if c.bloodied(on=c.me):
        c.temp_hp(c.surge_value(), on=c.me)


@power("i503x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i503x1(c: Cast) -> None:
    """`query.surge_value` reads `Mods.total`, which is where the standing
    raise lives; `c.surge(bonus=)` would have raised one surge and not the
    value. Untyped -- the card prints no word in front of it."""
    c.bonus("surge_value", max(0, c.enhancement - 1), on=c.me,
            until=When.ENCOUNTER)


@power("i503p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you spend a healing surge to regain hit points",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def i503p1(c: Cast) -> None:
    """"As if you had spent another" -- the hit points arrive and no second
    surge leaves the pool, so this is `c.heal`, not `c.surge`."""
    c.heal(c.surge_value(), on=c.me)


@power("i913x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i913x1(c: Cast) -> None:
    c.bonus("skill:endurance", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")
    c.resist(5, DamageType.COLD)
    c.resist(5, DamageType.FIRE)


@power("i914x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i914x1(c: Cast) -> None:
    def blinked(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None or Keyword.TELEPORTATION not in p.keywords:
            return
        c.bonus(AC, 2, on=c.me, until=When.EONT)
        c.bonus(REF, 2, on=c.me, until=When.EONT)

    c.watch(PowerUsed, blinked, until=When.ENCOUNTER, on=c.me)


@power("i914p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i914p1(c: Cast) -> None:
    """`c.expended` is the list of rows already used up, which is exactly
    what "already used during this encounter" asks for."""
    gone = []
    for ref in c.expended(on=c.me):
        p = get(ref)
        if p is None or p.usage is not Usage.ENCOUNTER:
            continue
        if Keyword.TELEPORTATION in p.keywords:
            gone.append(ref)
    pick = c.choose(gone, "which teleportation power comes back")
    if pick is not None:
        c.restore_use(pick, on=c.me)


@power("i916p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i916p1(c: Cast) -> None:
    """A wearer who attacks is stunned and loses the speed in the same
    breath -- "this effect ends and you are stunned"."""
    fast = c.bonus("speed", 5, on=c.me, until=When.EONT, kind="power")

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me:
            c.end_effect(fast)
            c.stunned(on=c.me, until=When.EONT)

    c.watch(AttackDeclared, swung, until=When.EONT, on=c.me, once=True)


# -- level 10 ---------------------------------------------------------------


@power("i1077x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1077x1(c: Cast) -> None:
    c.resist(10, DamageType.FIRE)


@power("i1077p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, attack=Attack(CHA, vs=WILL),
       dropped=("chargen.race_choice()",))
def i1077p1(c: Cast) -> None:
    """"Charisma or Constitution" is the better of the two, reached by
    topping up the declared Charisma attack with the difference.

    The second creature the line names is a **race**, by ref, and a
    character's race is a build-time choice with no word on the board --
    the same gap `i2406x1` has, named the same way."""
    foe = c.target
    if foe is None or not c.is_kind("devil", on=foe):
        return
    plus = c.enhancement + max(0, c.con_mod - c.cha_mod)
    if c.strike(plus=plus):
        c.condition(Condition.DOMINATED, until=When.EONT)


@power("i2031p1", level=10, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2031p1(c: Cast) -> None:
    """"End a condition" outright, with no throw -- `c.cure` is the verb and
    the conditions a save can end are the list it is asked from."""
    held = [x for x in _SAVE_ENDS if c.is_(x, on=c.me)]
    pick = c.choose(held, "which condition ends")
    if pick is not None:
        c.cure(pick, on=c.me)


@power("i3511x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3511x1(c: Cast) -> None:
    def spent(ev: SurgeSpent) -> None:
        if ev.actor != c.me:
            return
        seen = [f for f in c.enemies() if c.can_see(f)]
        foe = c.choose(seen, "which enemy the surge marks")
        if foe is None:
            return
        c.bonus("attack", 2, on=c.me, until=When.EONT, when=_against(foe))
        c.bonus("damage", 2, on=c.me, until=When.EONT, when=_against(foe))

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=c.me)


@power("i3511p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=NO_TARGET)
def i3511p1(c: Cast) -> None:
    for ally in c.within(5, side="ally"):
        if ally != c.me and c.bloodied(on=ally):
            c.temp_hp(10, on=ally)


@power("i485x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i485x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON)


@power("i485p1", level=10, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       trigger="an enemy hits you with a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you in melee"))
def i485p1(c: Cast) -> None:
    """The save penalty is gated on the burn's damage type, which the save
    context does carry -- it is poison *effects* the line narrows to, and a
    poison effect that burns is the shape the engine can see."""
    foe = _foe(c)
    if foe is None:
        return
    c.damage("1d10", dtype=DamageType.POISON, on=foe)
    c.ongoing(5, DamageType.POISON, on=foe)
    c.penalty("save", 2, on=foe, until=When.ENCOUNTER, when=_poisoned_save)


@power("i907x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i907x1(c: Cast) -> None:
    """"At the start of each encounter" is what a trait already is.

    "Until an attack against either of those defences hits you" is not a
    duration but it is an event: `resolve.attack` hangs `vs` on the `Hit`
    as a plain attribute for exactly this sentence, so the pair is ended
    when one of the two is beaten. Both go, which is what "until an
    attack against **either**" reads as -- one bonus, printed twice."""
    ac = c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="item")
    ref = c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="item")

    def landed(ev: Hit) -> None:
        if ev.target != c.me or getattr(ev, "vs", None) not in (AC, REF):
            return
        for hold in (ac, ref):
            if hold is not None and not hold.ended:
                c.end_effect(hold)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i907p1", level=10, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="you are hit by a melee or a ranged attack",
       on=Trigger(Hit, both(targets_me, either(by_melee, by_ranged)),
                  "a melee or ranged attack hits you"))
def i907p1(c: Cast) -> None:
    """`resolve.attack` re-announces the outcome when an interrupt changes
    it, so a reroll that turns the hit into a miss is a real miss -- which
    is what the teleport is conditional on."""
    if not c.reroll_attack():
        return
    result = getattr(c.trigger, "result", None)
    if result is not None and not result.hit:
        c.teleport(1)
