"""Wondrous-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares an item. The level, the price and the slot are
columns in `game.db`; the few wondrous items that carry an enhancement
bonus get it from `engine/equipment.py`. What is written here is only the
part that needs a body -- and in this slot that is nearly all of it, since
a wondrous item has no enhancement bonus to hide behind.

Three judgements run through the file.

* **Light is not modelled**, and `docs/AUTHORING.md` names lighting a lamp
  as the example of a narrative-only effect. Every row whose whole printed
  Effect is "sheds bright light / dim light / no light" is therefore
  `out_of_combat=True` rather than a marker. So is every bag, rope, chalk,
  ledger and ritual focus, which is a large part of the slot.
* **"A nonminion enemy"** is `c.is_minion`, off the stat block's own
  column. Seven rows here print the same critical-hit sentence, so the
  clause is asked once inside `_crit_on_me` and not seven times.
* **A figurine's beast** is printed as a stat block below the power, so
  the summons here take `Summon`'s own defaults -- the summoner's
  defences, a healing surge's worth of hit points -- and the numbers and
  the attack line are missing. `dsl.Summon` can say all of it; what is
  missing is the block, and the marker names where from:
  `etl.item.inline_block()` where the entry does print one and
  `etl.item._own_page` cuts it off, `spec.stat_block()` where the entry
  prints none and no amount of ETL will produce one.

"When you use your second wind" is `SecondWind`, which `Cast.second_wind`
emits from the one place a second wind is ever taken; `_on_second_wind`
watches it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
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
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    DamageType,
    Effect,
    Gear,
    Health,
    Hit,
    Ident,
    Keyword,
    Melee,
    Miss,
    PowerResolved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    Size,
    Square,
    Summon,
    SurgeSpent,
    Target,
    Trigger,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    ZoneEntered,
    ally_within,
    both,
    by_keyword,
    by_me,
    either,
    get,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.types import Light

ITEM = "item"


# -- shared reading of the board --------------------------------------------


def _ends_when_it_wakes(
    c: Cast, held: Effect, victim: int, *, also: Effect | None = None
) -> None:
    """"Until the creature regains consciousness or dies."

    Two shrouds print this and both were marked `When.CONSCIOUS`, which is
    the wrong kind of answer: `When` is clocks and waking is an event.
    `ConditionEnded` names the condition that lifted, so the end hangs off
    that and not off a duration -- and dying is the other half, which is
    the same event with the hold's own encounter clock behind it.

    `Condition.UNCONSCIOUS` **and** `Condition.DYING`, because a creature
    below zero carries both and either one lifting is the card's sentence.
    """

    def woke(ev: ConditionEnded) -> None:
        if ev.target != victim or ev.condition not in (
            Condition.UNCONSCIOUS, Condition.DYING
        ):
            return
        c.end_effect(held, on=victim)
        if also is not None:
            c.end_effect(also, on=victim)

    c.watch(
        ConditionEnded, woke, until=When.ENCOUNTER, on=c.me,
        label=f"{c.ref} wakes",
    )


def _spent_surges(c: Cast) -> int:
    """Healing surges gone since the last extended rest.

    `Health.max_surges` is the pool a rest refills to, so the difference is
    exactly the printed count. Six rows in this slot ask for it and no
    `Cast` method does.
    """
    health = c.world.get(c.me, Health)
    if health is None:
        return 0
    return max(0, health.max_surges - health.surges)


def _aquatic(world: World, eid: int) -> bool:
    """"There must be a body of water adjacent" -- a `requires=` gate, which
    gets `(world, eid)` and no `Cast`. Written as an entry requirement
    rather than as a guard in the body so a dry board reports the row as
    unusable rather than as one that fired and did nothing."""
    return "aquatic" in getattr(world, "terrain", frozenset())


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    """A **nonminion** enemy scored a critical hit on me.

    Every card in this family prints the same sentence, so the nonminion
    clause lives here rather than seven times over. A predicate is handed
    `(world, me, ev)` and `c.is_minion` is a `Cast` verb, so a bare one is
    made to ask -- the same way `weapon_b` reads a type line from a gate.
    """
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "critical", False)
        and attacker is not None
        and attacker != me
        and not Cast(world=world, me=me, ref="").is_minion(on=attacker)
    )


def _my_crit_on_my_turn(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "attacker", None) == me
        and getattr(ev, "critical", False)
        and world.turn == me
    )


def _took(dtype: DamageType) -> Callable[[World, int, Any], bool]:
    """"You take fire damage from an enemy attack." Reads `DamageApplied`."""

    def gate(world: World, me: int, ev: Any) -> bool:
        return (
            getattr(ev, "target", None) == me
            and getattr(ev, "dtype", None) is dtype
            and getattr(ev, "source", None) not in (None, me)
        )

    return gate


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Gate a modifier on the keywords of the power being used.

    The attack context carries `power`, so this is the only way to say
    "with charm powers"; the damage context carries `dtype` instead.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        if row is None:
            return False
        return any(w in row.keywords for w in words)

    return gate


def _dtype_gate(*types: DamageType) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") in types

    return gate


def _against(foe: int) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe

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


def _free_near(c: Cast, radius: int = 1, of: int | None = None) -> Square | None:
    """An unoccupied square within `radius` of somebody, for a "to" clause."""
    who = c.me if of is None else of
    from combat_engine.engine import Position

    pos = c.world.get(who, Position)
    if pos is None:
        return None
    grid = c.world.grid
    for sq in sorted(spread({pos.square}, radius)):
        if sq != pos.square and grid.occupant(sq) is None:
            return sq
    return None


def _allies_with(c: Cast, ref: str) -> list[int]:
    """"Each ally you can see who also has a <this item>."""
    return [
        a for a in c.allies() if c.can_see(a) and c.carrying(ref, on=a)
    ]


def _missed_everything(world: World, me: int, ev: Any) -> bool:
    """"You miss all targets with an encounter power of level 3 or lower."

    Read off `PowerResolved`, whose `rolls` is the attack result for each
    target the use actually reached. A `Miss` cannot answer it: it is one
    event per target, so the first of them is true while the use as a
    whole is not.
    """
    if getattr(ev, "actor", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    if row is None or row.usage is not Usage.ENCOUNTER or row.level > 3:
        return False
    rolls = [r for r in getattr(ev, "rolls", ()) if r is not None]
    return bool(rolls) and not any(getattr(r, "hit", False) for r in rolls)


def _gap(a: Square, b: Square) -> int:
    """How far apart two squares are, the way the grid counts."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _shift_by_distance(c: Cast, who: int, *, closer: bool) -> bool:
    """"Shift 1 square closer to you", and its opposite.

    `c.shift` picks its square through the world's decider and takes no
    direction -- but it takes `to=`, so a direction is said by naming the
    square rather than by asking for one. Nothing moves unless a square
    that genuinely improves the distance exists: the printed line is
    permissive, and standing still is the right answer when it does not.
    """
    options = c.world.reachable_squares(who, 1)
    if not options:
        return False
    now = c.distance(who)
    ranked = sorted(options, key=lambda sq: (_gap(sq, c.here), sq))
    pick = ranked[0] if closer else ranked[-1]
    step = _gap(pick, c.here)
    if (step < now) if closer else (step > now):
        return c.shift(1, who=who, to=pick)
    return False


def _steam(c: Cast, dice: str) -> None:
    """A zone that burns whoever starts a turn in it, the caster excepted.

    `c.hazard` is the obvious tool and is wrong twice over here: it burns
    on entering as well, which neither card prints, and it takes no
    exemption for "any creature other than you". A plain zone plus a
    `TurnStart` watch says both.

    The watch is clocked on the encounter and gated on the zone still
    standing, because sustaining refreshes the *zone's* clock and would
    leave a watch clocked on the same duration to lapse under it.
    """
    area = c.area()
    zone = c.zone(area, until=When.EONT, sustain=MINOR)
    c.cover_in(zone, side="any")

    def burn(ev: TurnStart) -> None:
        if ev.actor == c.me or zone not in c.my_zones():
            return
        if ev.actor in c.in_squares(area, side="any"):
            c.damage(dice, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, burn, until=When.ENCOUNTER)


def _figurine(c: Cast, **kw: Any) -> int:
    """The shared body of a figurine whose entry prints **no** stat block.

    `dsl.Summon`'s numbers come off the summoner -- its `defences` field is
    an offset, not an absolute -- so this is only honest where the page
    gives no numbers to be wrong about. Where it does, use `_conjured`.
    """
    made = c.summon_inline(Summon(**kw))
    if made and c.may("spend a healing surge"):
        c.spend_surge(on=c.me)
        c.temp_hp(c.surge_value(), on=made)
    return made


def _beside_my_beast(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to the beast attacks you" -- both halves.

    `triggers.targets_me` is only the second half, and a trigger that
    fires on any attack would lend the beast a free swing whenever
    anything hit the wielder, anywhere on the board. The beast is found
    through the `MASTER_OF` relation `_conjured` sets rather than by
    walking allies for a ref, so somebody else's identical conjuration is
    not mistaken for this item's.
    """
    from combat_engine.engine.components import Ident as _Ident
    from combat_engine.engine.query import adjacent
    from combat_engine.engine.relations import Relation

    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None:
        return False
    for mine in world.relations.targets(Relation.MASTER_OF, me):
        who = world.get(mine, _Ident)
        if who is not None and who.ref == "m1932c0" and adjacent(world, mine, attacker):
            return True
    return False


def _conjured(c: Cast, ref: str, *, surge: bool = True) -> int:
    """A figurine whose entry prints the beast's whole stat block. #601.

    The block was unimportable until the ETL learned to cut past an item's
    second `<h1>`, so these rows had no ref to name and used `_figurine` --
    which hands `dsl.Summon` a hand-picked size and mode list and takes the
    rest from the summoner. Now the numbers are a real `monster` row and
    `loader.spawn` reads them, level term and all.

    **`after=c.me` is the printed line.** Ten of the twelve blocks say
    "Initiative as conjurer" outright, which is a turn on the summoner's
    count rather than a rolled one.

    Bound, because every one of these cards says the creature obeys you and
    `c.servants()` is how a second row on the same item finds it again --
    `i1932p2` is the case, and before this there was nothing to find.
    """
    made = c.summon(ref, after=c.me)
    if not made:
        return 0
    c.bind(on=made)
    if surge and c.may("spend a healing surge"):
        c.spend_surge(on=c.me)
        c.temp_hp(c.surge_value(), on=made)
    return made


def _restorable(c: Cast, *, top: int, who: int | None = None) -> list[str]:
    """Spent rows of at most `top` level, for a row that hands a use back."""
    out = []
    for ref in c.expended(on=who):
        row = get(ref)
        if row is not None and row.usage is Usage.ENCOUNTER and row.level <= top:
            out.append(ref)
    return out


# -- level 1 ----------------------------------------------------------------


@power("i1222x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1222x1(c: Cast) -> None:
    """Chalk that does not wear out and writing that does not rub off."""


@power("i1645x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1645x1(c: Cast) -> None:
    """Reusable writing material and a faster ritual scroll."""


@power("i2180x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2180x1(c: Cast) -> None:
    """The temporary hit points are paid at the end of an extended rest,
    which is not a moment a fight has."""


@power("i2720x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2720x1(c: Cast) -> None:
    """Bright or dim light, 5 or 10 squares, or none -- a free action.

    **"Light only" was the whole docstring and it stopped being true**
    (#686), and the four-way choice is written now (#687). All five
    settings the card prints, brightest first so a headless engine takes
    the one a party in the dark wants."""
    c.illuminate((Light.BRIGHT, 10), (Light.BRIGHT, 5),
                 (Light.DIM, 10), (Light.DIM, 5), None,
                 on=c.me, until=When.ENCOUNTER)


@power("i3005x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3005x1(c: Cast) -> None:
    """Chalk that does not wear out."""


@power(
    "i3094p1",
    level=1,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("c.stabilise()",),
)
def i3094p1(c: Cast) -> None:
    """The ongoing half is `c.end_effect`, which takes a live hold off
    early: the burns are found by the type they tick in, since `Effect`
    carries `ongoing` as an amount and a type and the card names the
    untyped ones only. Stopping death saves is still unsayable -- nothing
    holds a dying creature short of healing it."""
    who = c.target
    if who is None:
        return
    for eff in list(c.world.effects.of(who)):
        burn = getattr(eff, "ongoing", None)
        if burn and burn[1] is DamageType.UNTYPED:
            c.end_effect(eff, why=f"{c.ref} ended it")


@power("i3269x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3269x1(c: Cast) -> None:
    """A deck that deals the card you want."""


@power("i3347p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET)
def i3347p1(c: Cast) -> None:
    """All light within 10 squares becomes dim, for the encounter.

    **"There is no light model to dim" was the reason and it stopped being
    true**: `query.light_level` reads darkening zones and
    `light_concealment` turns the level into a `Cover` the attack path
    takes the larger of. #686.

    **A zone and not `c.dim`.** The card dims an *area* measured from the
    bottle, which is put down and stays put -- where `c.dim` is a radius
    carried by a creature. The two are different printings and this is the
    first one.

    Dim light conceals everybody standing in it, the thrower included,
    which is what the card does and is why this is never inert."""
    from combat_engine.engine import Position

    here = c.world.get(c.me, Position)
    if here is None:
        return
    c.zone(spread({here.square}, 10), label=c.ref,
           until=When.ENCOUNTER, obscured=Light.DIM)


@power("i564x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i564x1(c: Cast) -> None:
    """A spellbook in another shape."""


@power("i685x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i685x1(c: Cast) -> None:
    """A ritual book that holds more pages."""


# -- level 2 ----------------------------------------------------------------


#: The three settings of one lamp, and the two rows that share the trick.
#:
#: `i1062` prints dim 20, bright 20 and "no light" as three separate free
#: actions, which are **settings** rather than three effects to hold at
#: once. Laying two would leave the reader's order to decide which won --
#: `query.light_level` asks the brightening pass first -- so a bright 20
#: would silently swallow a dim 20 the player had just chosen.
#:
#: So each row clears its siblings before laying its own. A row ending
#: another row's effect is ordinary (`c.dispel` and `Effects.end` are the
#: machinery); what makes it right here is that the card says these are one
#: lamp. #686, #687.
#:
#: **Only two of the three clearings are observable, and that is worth
#: knowing before somebody "simplifies" it.** A dimmer already beats a
#: carried light -- `query._dimmed` runs after the brightening pass, which
#: is `i1213x1`'s printed rule -- so `i1062p1` laying dim over a live
#: bright 20 reads dim whether it cleared or not. A plant removing its
#: clearing stays **green** for that reason. `i1062p2` and `i1062p3` are
#: the ones the state depends on, and `drivers.lamp_settings` plants
#: against the second of them. The first keeps the call so the three rows
#: read alike and so the stored state matches what the player chose rather
#: than only the answer happening to be right.
_LAMP_SETTINGS = ("i1062p1", "i1062p2", "i1062p3")


def _one_setting(c: Cast, *family: str) -> None:
    """Clear every setting of this lamp, so the next one laid is the only one."""
    for eff in list(c.world.effects.of(c.me)):
        if any(eff.label.startswith(ref) for ref in family):
            c.world.effects.end(eff, "another setting chosen")


@power("i1062x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1062x1(c: Cast) -> None:
    """`spec.py` prints this property with no text at all -- see the report.

    **Still inert, and for the reason it always was rather than the one
    beside it.** The other rows of this item were inert on "light only",
    which stopped being true (#686); this one has no printed text to write
    from at all, which is a different thing and is unchanged.

    Not `defect=`: that marker drops the **whole compendium entry**, and
    this item's three light settings are written and play. A property with
    no text is a gap in the printing of one block, not a reason to take the
    lamp off the board."""


@power("i1062p1", level=2, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET)
def i1062p1(c: Cast) -> None:
    """Dim light, 20 squares -- one of this lamp's three settings.

    **"Light only" was the whole docstring and it stopped being true.**
    Dim light conceals, which `query.light_concealment` turns into a
    `Cover` the attack path takes the larger of, so a lamp set to dim
    conceals everybody within twenty squares of it. #686.

    `c.dim` and not `c.light`: this *lowers* the level. See `_one_setting`
    for why it clears its siblings first."""
    _one_setting(c, *_LAMP_SETTINGS)
    c.dim(20, on=c.me, until=When.ENCOUNTER)


@power("i1062p2", level=2, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET)
def i1062p2(c: Cast) -> None:
    """Bright light, 20 squares -- the second of this lamp's settings.

    Inert on a board nothing has darkened, which is what bright light is
    and is `c.light`'s own stated position -- not a reason to declare the
    row inert, because it plays the moment a square goes dark. #686."""
    _one_setting(c, *_LAMP_SETTINGS)
    c.light(20, on=c.me, until=When.ENCOUNTER)


@power("i1062p3", level=2, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET)
def i1062p3(c: Cast) -> None:
    """"The i1062 sheds no light" -- the third setting, and it is the one
    that makes the other two mean anything.

    Turning the lamp off is a real choice on a board where dim light
    conceals: a party that wants to be seen puts it on bright, a rogue
    turns it off. So this clears the family and lays nothing, which is
    exactly what the card prints. #686."""
    _one_setting(c, *_LAMP_SETTINGS)


@power("i1106x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1106x1(c: Cast) -> None:
    """An alarm on a door, on a one-hour clock no encounter reaches."""


@power("i1584p1", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i1584p1(c: Cast) -> None:
    """A twelve-hour campfire that cannot be seen from outside its radius."""


@power(
    "i2050x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2050x1(c: Cast) -> None:
    """Untyped: the card prints a bare "+2 bonus". "If you are raging" is
    `powers.barbarian.rage.in_rage`, which the class wrote for the two
    dozen rows that print the same requirement -- imported inside the body
    because both files are loaded by the same walk. Paragon numbers are out
    of scope."""
    from combat_engine.content.powers.barbarian.rage import in_rage

    def paid() -> None:
        c.bonus("damage", 2, on=c.me, until=When.EONT, once=True)
        if in_rage(c):
            c.bonus("attack", 2, on=c.me, until=When.EONT, once=True)

    _on_second_wind(c, paid)


@power("i2104p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=NO_TARGET, keywords=[Keyword.CONJURATION],
       out_of_combat=True)
def i2104p1(c: Cast) -> None:
    """A spirit that fetches and carries. Every printed clause is about
    moving an object; it cannot attack and nothing can attack it."""


@power(
    "i2500p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def i2500p1(c: Cast) -> None:
    """Resist 20 while it lies there, gone the moment it wakes or the
    shroud is lifted.

    **`When.CONSCIOUS` was the wrong shape of answer.** There is no such
    duration and there should not be: the `When` enum is clocks -- turn
    boundaries, saves, the encounter -- and waking up is an *event*.
    `ConditionEnded` carries the condition that lifted, so the end is a
    watch rather than a clock, and the hold is kept so the watch can find
    the one effect this row laid.

    Both printed ends are here: `c.endable` is the standard action that
    takes the shroud off, and the watch is the creature waking. Either
    one ends it, which is what "whichever comes first" says.
    """
    victim = c.target
    if victim is None:
        return
    held = c.resist(20, on=victim, until=When.ENCOUNTER)
    if held is None:
        return
    _ends_when_it_wakes(c, held, victim)
    c.endable(held, cost=ActionType.STANDARD)


@power("i2508x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2508x1(c: Cast) -> None:
    """A Stealth bonus while doing a tool's own work, and tools only."""


@power("i2998x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2998x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power("i2998p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=CloseBurst(5), target=NO_TARGET)
def i2998p1(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EONT)
    for friend in c.within(5, side="team"):
        c.ignores_difficult(on=friend, until=When.EONT)
    c.move(c.speed_of())


@power("i3079x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3079x1(c: Cast) -> None:
    """A safe landing from one particular window, which is scenery rather
    than anything a board has."""


@power("i3256x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3256x1(c: Cast) -> None:
    """Hides one object from a search."""


@power("i477x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i477x1(c: Cast) -> None:
    """A campfire that unfolds out of a box."""


@power(
    "i614p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def i614p1(c: Cast) -> None:
    """Only the marked enemies, and only against anyone but their own marker.

    **Both halves are written now that the damage context says who is dealing
    it** (#302). `ctx["source"]` is the enemy swinging, so "that are marked" is
    `c.marked(on=source)` and "other than the one that marked them" is the
    target *not* being its marker -- `c.marked(on=source, by=target)` asked in
    the negative, which is the same relation read from the other end rather than
    a second mechanism.

    Gated on `from_attack` as well, because the card says "damage rolls": a
    zone's burn or an ongoing effect is damage this creature deals and is not a
    roll it makes, and the context distinguishes them so the row may as well.

    Pulling the standard back out of the ground is still not modelled -- nothing
    can be planted -- but that clause ends the zone rather than the penalty, and
    the zone does end with the encounter."""
    zone = c.zone(c.area(), until=When.ENCOUNTER)

    def marked_elsewhere(ctx: dict[str, Any]) -> bool:
        who, at = ctx.get("source"), ctx.get("target")
        if who is None or at is None or not ctx.get("from_attack"):
            return False
        return c.marked(on=who) and not c.marked(on=who, by=at)

    c.grants_in(zone, "damage", -1, side="enemy", kind="untyped",
                when=marked_elsewhere)


# -- level 3 ----------------------------------------------------------------


@power("i1068x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1068x1(c: Cast) -> None:
    """Paragon resistances are out of scope; this is the heroic 5."""

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me:
            return
        pick = c.choose(
            [
                DamageType.ACID,
                DamageType.COLD,
                DamageType.FIRE,
                DamageType.LIGHTNING,
                DamageType.THUNDER,
            ],
            "which damage type to resist",
        )
        if pick is not None:
            c.resist(5, pick, on=c.me, until=When.ENCOUNTER)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


@power(
    "i1219x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1219x1(c: Cast) -> None:
    def crit(ev: Hit) -> None:
        if _crit_on_me(c.world, c.me, ev):
            c.teleport(3)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power(
    "i1312x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1312x1(c: Cast) -> None:
    """The power the page prints inline has no ref, so `c.grant_row` has
    nothing to name -- but `c.give` takes the payout as a function instead
    of a ref, which is exactly the shape of a one-shot with no card. Its
    `cost` is the printed minor action; drinking and using are collapsed
    into that one spend, since the elixir is drunk to be used.

    "Level + 5" is the character's level, and the blast is aimed at the
    nearest enemy -- `c.area()` reads the row's own reach and this row is
    the property, not the power."""
    def swallow(spender: int) -> None:
        from combat_engine.engine import Position
        from combat_engine.engine.grid import blast

        foes = sorted(c.enemies(), key=lambda f: c.distance(f))
        spot = c.world.get(foes[0], Position) if foes else None
        if spot is None:
            return
        area = blast({c.here}, 3, spot.square)
        for foe in c.in_squares(area, side="enemy"):
            if c.attack(c.level + 5, REF, on=foe):
                c.damage("1d6", c.con_mod, dtype=DamageType.FIRE, on=foe)

    c.give(fn=swallow, on=c.me, uses=1, cost=MINOR)


@power("i1321x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("Gear.left_hanging",))
def i1321x1(c: Cast) -> None:
    """A lantern that lights 10 squares, hangs where you leave it, and can
    be sent ahead.

    **The light is the half that plays** and it was the whole of the old
    one-line docstring's "light" -- bright 10, carried, inert on a lit
    board and real on a dark one. #686.

    **The settings are written now** -- bright 10, dim 5, or off -- which
    is `c.illuminate`, one carried level at a time (#687). "By anyone
    holding or adjacent" is not: the chooser is the holder, and a card that
    lets a *neighbour* reach into somebody else's gear has no door here.
    That is folded into the one remaining marker rather than given its own,
    because it is the same missing idea.

    **The floating lantern** is an object left on the board that keeps
    lighting and can be commanded to move: a conjuration in everything but
    name, and `Gear` has no notion of an item put down and still
    working."""
    c.illuminate((Light.BRIGHT, 10), (Light.DIM, 5), None,
                 on=c.me, until=When.ENCOUNTER)


@power("i1328x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1328x1(c: Cast) -> None:
    """The enhancement bonus and the critical die are columns."""
    c.as_implement(on=c.me)


@power("i1328p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1328p1(c: Cast) -> None:
    """Used during a short rest and paid out at the end of it."""


@power("i1508p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(20), target=NO_TARGET)
def i1508p1(c: Cast) -> None:
    """Skill modifiers are real -- `skills` reads `skill:<name>` -- so this
    is a row rather than a narrative one. It takes in everybody, as
    printed, the caster included."""
    c.penalty("skill:perception", 15, on=c.me, until=When.EONT)
    for who in c.within(20, side="other"):
        c.penalty("skill:perception", 15, on=who, until=When.EONT)


@power("i1509x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1509x1(c: Cast) -> None:
    """The three blessings are the item's own p2, p3 and p4. Gaining the
    second and third at 5th and 10th level is a chargen clause, not a
    thing a fight can watch, so one is chosen here."""
    pick = c.choose(["i1509p2", "i1509p3", "i1509p4"], "which blessing")
    if pick is not None:
        c.grant_row(pick, on=c.me)


@power(
    "i1509p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i1509p1(c: Cast) -> None:
    """"You use one of the blessings you have gained" is `c.use_power`,
    which spends another row at this row's action cost. "That you have
    gained" is read off the board rather than assumed: `i1509x1` grants
    exactly one, and a blessing standing on somebody else is not this
    character's. One of the three carries a `todo` and `dsl.usable`
    refuses it, so it is left out of the choice rather than offered and
    then declined."""
    mine = [
        ref
        for ref in ("i1509p2", "i1509p3", "i1509p4")
        if c.knows(ref) == c.me
        and (row := get(ref)) is not None
        and not row.todo
    ]
    if not mine:
        return
    pick = c.choose(mine, "which blessing to use")
    if pick is not None:
        c.use_power(pick)


@power(
    "i1509p2",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with an attack",
    on=Trigger(Miss, by_me, "you miss with an attack"),
)
def i1509p2(c: Cast) -> None:
    """"Roll 1d6 and add the result to the triggering attack roll."

    **Written.** `c.boost_roll` is the verb the old note said did not exist:
    it adds to a roll already made and recomputes the outcome from the
    untouched natural, so a 1 stays a miss and a boost cannot manufacture a
    critical. That is the whole difference from `c.reroll_attack`, which
    throws the die away -- and the card says *add*.

    `kind="attack"` rather than the bare call, because the same verb serves
    saving throws and skill checks and this row answers only a `Miss`.
    """
    c.boost_roll(c.roll("1d6"), kind="attack")


@power(
    "i1509p3",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
)
def i1509p3(c: Cast) -> None:
    c.reduce(5 + c.level // 2)


@power(
    "i1509p4",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you fail a saving throw",
    on=Trigger(
        SavingThrow,
        lambda world, me, ev: ev.actor == me and not ev.saved,
        "you fail a saving throw",
    ),
)
def i1509p4(c: Cast) -> None:
    """`c.save` against the same label is the reroll: the failed throw has
    already been resolved by the time a no-action answers it."""
    c.save(on=c.me, bonus=2, against=getattr(c.trigger, "against", ""))


@power("i1769p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1769p1(c: Cast) -> None:
    """An hour of music."""


@power("i1769p2", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.CHARM])
def i1769p2(c: Cast) -> None:
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.EONT,
        kind="item",
        when=_keyword_gate(Keyword.CHARM),
    )


@power("i3006x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3006x1(c: Cast) -> None:
    """A lantern that hangs where it is left."""


@power("i3006p1", level=3, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET)
def i3006p1(c: Cast) -> None:
    """Bright 10, dim 5, or off, while holding the lantern or beside it.

    The same card as `i1321x1`'s settings clause, printed as a power of its
    own here, and written the same way -- `c.illuminate`, one carried level
    at a time. #686, #687.

    "Or adjacent to it" is the half neither row can say: the chooser is the
    holder. One lantern, two printings, one missing idea, and `i1321x1`
    carries the marker for it."""
    c.illuminate((Light.BRIGHT, 10), (Light.DIM, 5), None,
                 on=c.me, until=When.ENCOUNTER)


@power("i3006p2", level=3, cls=ITEM, usage=AT_WILL, action=MOVE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3006p2(c: Cast) -> None:
    """Walking a lantern about. It is not a creature and carries nothing."""


@power("i3078p1", level=3, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i3078p1(c: Cast) -> None:
    """A static picture in a window pane."""


@power("i3466x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3466x1(c: Cast) -> None:
    """Read once, when the property arms: `c.knows` finds the only other
    holder the board could have, and two of these standing within a square
    of each other for the whole fight is the printed situation."""
    other = c.knows("i3466p1")
    if other is not None and other != c.me and c.distance(other) <= 1:
        c.forbid("i3466p1", on=c.me, until=When.ENCOUNTER)
        c.forbid("i3466p2", on=c.me, until=When.ENCOUNTER)


@power("i3466p1", level=3, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET)
def i3466p1(c: Cast) -> None:
    """Dim 2, bright 10, or no light -- all three. #686, #687.

    Brightest first, which is not the card's own order: it prints dim
    first, and `c.may`'s note is the reason to reorder -- "an engine with
    nobody playing takes the first option", and a lamp a party is carrying
    in the dark wants to be lit."""
    c.illuminate((Light.BRIGHT, 10), (Light.DIM, 2), None,
                 on=c.me, until=When.ENCOUNTER)


@power(
    "i3466p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=Target(side="enemy", count=99, everyone=True),
    dropped=("c.consume_item()",),
)
def i3466p2(c: Cast) -> None:
    """No attack roll is printed. The globe destroying itself is dropped --
    an item cannot take itself off its own wearer."""
    c.blinded(until=When.SOTNT)


@power("i3557x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3557x1(c: Cast) -> None:
    """The paired item is read off what the character is carrying, which is
    what "in the other hand" comes to here."""
    c.as_implement(on=c.me)
    if c.carrying("i3558"):
        c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="shield")
        c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, kind="shield")


@power(
    "i3557p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with a charm, psychic or thunder implement power",
    on=Trigger(
        Miss,
        both(
            by_me,
            either(
                by_keyword(Keyword.CHARM),
                by_keyword(Keyword.PSYCHIC),
                by_keyword(Keyword.THUNDER),
            ),
        ),
        "you miss with a charm, psychic or thunder implement power",
    ),
)
def i3557p1(c: Cast) -> None:
    """"Use either result" is `keep="best"`: nothing would ever keep the
    miss."""
    c.reroll_attack(keep="best")


@power("i613p1", level=3, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(5), target=NO_TARGET,
       keywords=[Keyword.HEALING, Keyword.ZONE])
def i613p1(c: Cast) -> None:
    """The payout is not a modifier the zone can carry, so it is a watch on
    `SurgeSpent` that checks both feet -- the spender's and the healed."""
    area = c.area()
    c.zone(area, until=When.ENCOUNTER)

    def surged(ev: SurgeSpent) -> None:
        inside = c.in_squares(area, side="team")
        if ev.actor not in inside:
            return
        for who in inside:
            c.heal(1, on=who)

    c.watch(SurgeSpent, surged, until=When.ENCOUNTER)


@power("i837x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i837x1(c: Cast) -> None:
    """A cask that refills with ale each day."""


# -- level 4 ----------------------------------------------------------------


@power("i1224x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1224x1(c: Cast) -> None:
    """Food and water after an extended rest."""


@power("i1291x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1291x1(c: Cast) -> None:
    """Paragon numbers are out of scope; this is the heroic 5."""

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            c.temp_hp(5, on=c.me)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


@power(
    "i1932p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i1932p1(c: Cast) -> None:
    _conjured(c, "m1932c0")


@power(
    "i1932p2",
    level=4,
    cls=ITEM,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy adjacent to the beast attacks you",
    on=Trigger(AttackDeclared, _beside_my_beast, "an enemy beside it attacks you"),
)
def i1932p2(c: Cast) -> None:
    """The bite is `m1932c0a0` now, and it has a ref.

    The old docstring said the bite line was printed in a stat block the
    brief does not carry, and that was true until the block was importable
    (#601). It is a real `monster_power` row, so the swing is lent to the
    beast rather than rolled by the wielder -- `c.grant_attack(who,
    on=victim, ref=...)` rolls the creature's own numbers from the
    creature's own square, where `c.strike` would have rolled the
    character's.

    **The trigger was half the printed sentence.** `targets_me` alone is
    "an enemy attacks you"; the card is "an enemy **adjacent to the
    beast** attacks you", which cannot fire at all until there is a beast,
    and `_beside_my_beast` is both halves. `c.servants()` is what finds
    it, since `_conjured` binds what it summons.
    """
    beast = next((a for a in c.servants()
                  if (who := c.world.get(a, Ident)) is not None
                  and who.ref == "m1932c0"), None)
    foe = getattr(c.trigger, "attacker", None)
    if beast is None or foe is None:
        return
    c.grant_attack(beast, on=foe, ref="m1932c0a0")


@power("i2507x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2507x1(c: Cast) -> None:
    """Eavesdropping on a room, which is a place rather than a board."""


@power("i2823x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2823x1(c: Cast) -> None:
    """`Bloodied` does not say who did it, so the crossing is read off
    `DamageApplied`, which carries the source. Paragon numbers are out of
    scope; this is the heroic 3."""

    def hurt(ev: DamageApplied) -> None:
        if ev.target != c.me or not c.bloodied(on=c.me):
            return
        if ev.source in (None, c.me):
            return
        c.flat(3, dtype=DamageType.FORCE, on=ev.source)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, once=True)


@power("i2850x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2850x1(c: Cast) -> None:
    """A ritual focus."""


@power("i2960x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2960x1(c: Cast) -> None:
    """A ritual focus."""


@power("i3267p1", level=4, cls=ITEM, usage=DAILY, action=MOVE,
       reach=CloseBurst(10), target=ONE_ALLY,
       keywords=[Keyword.TELEPORTATION])
def i3267p1(c: Cast) -> None:
    """The destination is named outright, which is what `to=` is for; the
    distance is the burst rather than a teleport range."""
    sq = _free_near(c)
    if c.target is not None and sq is not None:
        c.teleport(10, who=c.target, to=sq)


@power("i3493p1", level=4, cls=ITEM, usage=AT_WILL, action=MOVE,
       reach=PERSONAL, target=SELF,
       requires_text="you must be lying on the sled")
def i3493p1(c: Cast) -> None:
    """The malfunction's "random direction" is left to the mover's own
    decider -- there is no way to name a direction, only a square, and
    picking one would be less random than letting it choose."""
    if c.roll("1d20") == 1:
        c.move(5)
        c.prone(on=c.me)
        return
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.move(10)


@power("i615p1", level=4, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(5), target=NO_TARGET, keywords=[Keyword.ZONE])
def i615p1(c: Cast) -> None:
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    c.grants_in(zone, "damage", 1, side="team", kind="power")


@power("i635x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i635x1(c: Cast) -> None:
    """A shorter extended rest."""


@power("i809p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.CONJURATION],
       out_of_combat=True)
def i809p1(c: Cast) -> None:
    """A twelve-hour riding horse that "does not attack even in defense".
    It is transport, and putting it on the board would give the policy a
    body to push around that the card says cannot fight."""


@power("i869p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i869p1(c: Cast) -> None:
    """A watch-chime that wakes sleepers."""


# -- level 5 ----------------------------------------------------------------


@power("i1053x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1053x1(c: Cast) -> None:
    """An hour of air."""


@power("i1207x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1207x1(c: Cast) -> None:
    """A Nature bonus for calming or training a beast."""


@power("i1294x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1294x1(c: Cast) -> None:
    """You always know where the nearest drink is."""


@power("i1294p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1294p1(c: Cast) -> None:
    """Five minutes of dowsing."""


@power("i1631p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1631p1(c: Cast) -> None:
    """A campsite out of a satchel."""


@power("i1705x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1705x1(c: Cast) -> None:
    """The radius is the lantern's light, and the lantern is on the wearer,
    so it is read as 10 squares around them."""
    for who in [c.me, *c.within(10, side="ally")]:
        c.bonus("skill:insight", 1, on=who, until=When.ENCOUNTER, kind="power")
        c.bonus(
            "skill:perception", 1, on=who, until=When.ENCOUNTER, kind="power"
        )


@power("i1768x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1768x1(c: Cast) -> None:
    """The enhancement bonus and the critical die are columns."""
    c.as_implement(on=c.me)


@power("i1768p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       out_of_combat=True)
def i1768p1(c: Cast) -> None:
    """Used during a short rest and paid out at the end of it."""


@power("i1876x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1876x1(c: Cast) -> None:
    """A ritual focus that splits into eight."""


@power(
    "i1925p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i1925p1(c: Cast) -> None:
    _conjured(c, "m1925c0")


@power("i2086x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2086x1(c: Cast) -> None:
    """Coins in, platinum out."""


@power("i2090p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       requires_text="you must have reached a milestone today")
def i2090p1(c: Cast) -> None:
    """"Of 1st or 3rd level" is read as "of 3rd level or lower", which is
    the same set: there are no 2nd-level encounter attack powers."""
    spent = _restorable(c, top=3)
    if not spent:
        return
    pick = c.choose(spent, "which power to get back")
    if pick is not None:
        c.restore_use(pick, on=c.me)


@power("i2361x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2361x1(c: Cast) -> None:
    """Drawing a weapon costs nothing here, and drawing is not an action
    the engine charges for."""


@power(
    "i2361p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you attack with the weapon most recently sheathed",
    on=Trigger(AttackDeclared, by_me, "you attack"),
    dropped=("c.sheathed()",),
)
def i2361p1(c: Cast) -> None:
    """Which weapon was last in the scabbard is not recorded anywhere, so
    the bonus is given to the next damage roll whatever is in hand."""
    c.bonus("damage", 1, on=c.me, until=When.EONT, kind="power", once=True)


@power(
    "i2550p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you score a critical hit on your turn",
    on=Trigger(Hit, _my_crit_on_my_turn, "you score a critical hit"),
)
def i2550p1(c: Cast) -> None:
    """Written. "In addition to its normal damage types" was the one thing
    `c.deals` would not do, and `add=True` is now that: `Cast._retyped`
    already holds the type the card printed, so the whole of it is
    answering `(printed, *mine)` rather than `mine`. The printed type stays
    **first**, because `resolve.deal_damage` takes the primary from there
    and every event reader asks about it -- the attack is still its own
    type, with one more.

    "Radiant damage **or** fire damage" is a real choice and is offered as
    one, before the retype is laid: the two are not interchangeable against
    a target that resists either.

    `once=True` because the clause is about **the triggering attack** and
    nothing after it, and `When.EOT` so the hold cannot outlive the turn if
    that attack somehow rolls no damage."""
    word = c.choose([DamageType.RADIANT, DamageType.FIRE], c.ref)
    if word is None:
        return
    c.deals(word, on=c.me, until=When.EOT, add=True, once=True)


@power(
    "i2829x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2829x1(c: Cast) -> None:
    """Untyped: the card prints a bare "+3 bonus". Paragon numbers are out
    of scope."""

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        c.bonus(
            "damage",
            3,
            on=c.me,
            until=When.ENCOUNTER,
            when=_against(ev.attacker),
        )

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("i2843x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2843x1(c: Cast) -> None:
    """The class half of the line is not enforced."""
    c.as_implement(on=c.me)


@power("i2843p1", level=5, cls=ITEM, usage=DAILY, action=MOVE,
       reach=Melee(1), target=SELF)
def i2843p1(c: Cast) -> None:
    """The burst is measured from where the teleport ended, which is why
    the enemies are gathered after the move rather than before it."""
    friends = [a for a in c.within(1, side="ally")]
    who = c.me
    if friends:
        pick = c.choose([c.me, *friends], "who teleports", optional=False)
        if pick is not None:
            who = pick
    c.teleport(5, who=who)
    for foe in c.within(3, of=who, side="enemy"):
        c.damage("1d6", dtype=DamageType.LIGHTNING, on=foe)


@power("i3348x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3348x1(c: Cast) -> None:
    """Monster knowledge checks about one origin."""


@power("i3528x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3528x1(c: Cast) -> None:
    """A hiding place behind a painting."""


@power("i3528p1", level=5, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3528p1(c: Cast) -> None:
    """Opening that hiding place."""


@power("i3534p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3534p1(c: Cast) -> None:
    """An oracle, used during a rest."""


@power("i587x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i587x1(c: Cast) -> None:
    """A bag that holds more than it should. Encumbrance is not modelled."""


@power("i870p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i870p1(c: Cast) -> None:
    """Opening locks and disarming traps on an object, by check."""


# -- level 6 ----------------------------------------------------------------


@power("i1102x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1102x1(c: Cast) -> None:
    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            c.cure(Condition.MARKED, on=c.me)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


@power("i1282x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1282x1(c: Cast) -> None:
    """A courier that lives inside a warforged and leaves on an errand."""


@power("i1282p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1282p1(c: Cast) -> None:
    """Loading the courier with a message."""


@power("i1282p2", level=6, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1282p2(c: Cast) -> None:
    """Sending it on its way."""


@power("i1282p3", level=6, cls=ITEM, usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="you are killed", out_of_combat=True)
def i1282p3(c: Cast) -> None:
    """The trigger is real but what it does is post an errand: the courier
    leaves the board and delivers a message. Nothing happens in the fight,
    so it is declared inert rather than given a `Trigger` that would offer
    a corpse a free action."""


@power("i1325p1", level=6, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF)
def i1325p1(c: Cast) -> None:
    """The allies are gathered after the shift, since the printed radius is
    measured from the destination."""
    c.shift(2)
    for friend in c.within(5, side="ally"):
        c.shift(1, who=friend)


@power(
    "i1933p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    requires=_aquatic,
    requires_text="there must be a body of water adjacent to you",
)
def i1933p1(c: Cast) -> None:
    _conjured(c, "m1933c0")


@power("i2063x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2063x1(c: Cast) -> None:
    """One language, while you carry only one of these."""


@power("i2428x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2428x1(c: Cast) -> None:
    """A ritual focus with a longer range."""


@power("i2428p1", level=6, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=Ranged(10), target=NO_TARGET, out_of_combat=True)
def i2428p1(c: Cast) -> None:
    """Throwing your voice. Nothing hears it mechanically."""


@power(
    "i2548p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you score a critical hit on your turn",
    on=Trigger(Hit, _my_crit_on_my_turn, "you score a critical hit"),
)
def i2548p1(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "i2825x1",
    level=6,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2825x1(c: Cast) -> None:
    """"Closer to you" is `_shift_by_distance`: the direction is said by
    naming the square, which `c.shift` takes."""

    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        for friend in _allies_with(c, "i2825"):
            _shift_by_distance(c, friend, closer=True)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, once=True)


@power(
    "i2826x1",
    level=6,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2826x1(c: Cast) -> None:
    """"Farther from you", as above and the other way round."""

    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        for friend in _allies_with(c, "i2826"):
            _shift_by_distance(c, friend, closer=False)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, once=True)


@power("i3048x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3048x1(c: Cast) -> None:
    """A bonus to the checks a warding ritual asks for."""


@power("i3258p1", level=6, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3258p1(c: Cast) -> None:
    """A rope fired at a wall. It deals no damage if it hits a creature,
    and a rope trailing to a point of impact is climbing gear."""


@power("i3270p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBlast(2), target=NO_TARGET, keywords=[Keyword.ZONE])
def i3270p1(c: Cast) -> None:
    """A twenty-foot pit is four squares of sunk ground, which `c.terraform`
    says outright -- walking in is then a fall of that depth and climbing
    out is the Athletics check the engine already charges for."""
    area = c.area()
    c.zone(area, until=When.ENCOUNTER)
    for sq in area:
        c.terraform(sq, sink=4)


@power("i3492p1", level=6, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3492p1(c: Cast) -> None:
    """A Thievery check against a lock, and a wardrobe malfunction."""


@power("i3530p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3530p1(c: Cast) -> None:
    """A bonus to one skill check and nothing else."""


@power("i3532x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3532x1(c: Cast) -> None:
    """Dice that come up as told. They are not the dice a power rolls."""


@power("i523x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i523x1(c: Cast) -> None:
    """A focus for two rituals about doors."""


@power("i523p1", level=6, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i523p1(c: Cast) -> None:
    """Locking a door on another plane."""


@power(
    "i961x1",
    level=6,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i961x1(c: Cast) -> None:
    """"When you use your second wind, you can choose to change your phase
    to the next higher-numbered phase."

    **Written.** The phase exists now: `events.ShortRested` landed, so
    `cf:sorcerer-f0s0` holds one, and `features.sorcerer.step_phase`
    advances it -- stars wrapping back to sun.

    No check for the feature. `step_phase` returns `""` for a creature in no
    phase, which is every character without Cosmic Magic, so the printed "if
    you have the sorcerer class feature" enforces itself rather than being
    asked separately.

    **"Can choose" is a choice**, so it asks rather than stepping: the
    higher phase is not always the better one, and a tattoo that advanced
    the cycle without consent would be a downgrade on the turn a sorcerer
    wanted the stars' teleport.
    """
    from combat_engine.content.features.sorcerer import phase_of, step_phase
    from combat_engine.engine.events import SecondWind

    me = c.me

    def winded(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) != me or not phase_of(c):
            return
        if c.choose([True, False], "step the cosmic phase on"):
            step_phase(c)

    c.watch(SecondWind, winded, until=When.ENCOUNTER, on=me)


# -- level 7 ----------------------------------------------------------------


@power("i1107x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1107x1(c: Cast) -> None:
    """The enhancement bonus and the critical dice are columns."""
    c.as_implement(on=c.me)


@power("i1107p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1107p1(c: Cast) -> None:
    """Used during a short rest and paid out at the end of it."""


@power("i1213x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1213x1(c: Cast) -> None:
    """A candle that dims the light around it -- and that is a combat fact.

    **The one-line docstring was the whole reason it was inert**, and the
    card is explicit about an operation the engine had no way to express:
    "this candle sheds dim light in a 2-square radius … **bright light
    within the candle's radius is reduced to dim light**". `c.light` makes
    its radius bright however dark the square is, which is the opposite;
    `c.dim` is the reduction, and that sentence is where its ordering comes
    from. #686, #687.

    Carried, because the candle is. It conceals whoever holds it as much as
    anybody else standing in the radius, which is what the card says and
    not a side effect to design around."""
    c.dim(2, on=c.me, until=When.ENCOUNTER)


@power(
    "i1213p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def i1213p1(c: Cast) -> None:
    """"Invisible to those outside the area" is exactly `c.invisible(to=)`,
    one pairing per outsider, which is why this is a nested loop rather
    than a blanket hide.

    The candle going out is `c.on_attack` -- which watches everybody, not
    just the caster -- plus `c.end_effect` on each hold it laid. The holds
    are kept in a local for that: everything that lays one hands one back,
    which is the shape `c.end_effect` documents."""
    area = spread({c.here}, 2)
    inside = c.in_squares(area)
    outside = [w for w in c.within(20, side="any") if w not in inside]
    holds: list[Effect] = []
    for who in inside:
        for watcher in outside:
            hold = c.invisible(on=who, to=watcher, until=When.ENCOUNTER)
            if hold is not None:
                holds.append(hold)

    def snuffed(ev: AttackDeclared) -> None:
        if ev.attacker not in inside:
            return
        for hold in holds:
            c.end_effect(hold, why=f"{c.ref} was put out")
        holds.clear()

    c.on_attack(snuffed, until=When.ENCOUNTER)


@power("i1574p1", level=7, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1574p1(c: Cast) -> None:
    """A horn heard a mile off that tells allies where you are."""


@power(
    "i1666p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def i1666p1(c: Cast) -> None:
    """"Any creature other than you that starts its turn" -- see `_steam`,
    which is why this is not `c.hazard`."""
    _steam(c, "1d6")


@power("i1718p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1718p1(c: Cast) -> None:
    """An hour of reading a language you do not know."""


@power("i1754x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1754x1(c: Cast) -> None:
    """`Hit` is announced inside `c.strike` and the body rolls damage after
    it, so a one-shot damage bonus laid here is read by the very attack
    that triggered it. Untyped: the card prints a bare "bonus"."""

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        row = get(ev.power)
        if row is None or row.usage is not Usage.DAILY:
            return
        gone = _spent_surges(c)
        if gone:
            c.bonus("damage", gone, on=c.me, until=When.EOT, once=True)

    c.watch(Hit, landed, until=When.ENCOUNTER)


@power("i1802x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1802x1(c: Cast) -> None:
    """Checks made to navigate overland."""


@power("i1802p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1802p1(c: Cast) -> None:
    """A map of ten miles of country."""


@power("i2039p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=NO_TARGET, keywords=[Keyword.ILLUSION])
def i2039p1(c: Cast) -> None:
    """Every printed clause has a verb: one hit point, the caster's own
    defences, no damage on a miss, and flanking. It never attacks, so no
    attack line is given."""
    made = c.summon_inline(Summon(hp=1, speed=c.speed_of()))
    if not made:
        return
    c.no_miss_damage(on=made, until=When.ENCOUNTER)
    c.can_flank(on=made, until=When.ENCOUNTER)


@power("i2117x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2117x1(c: Cast) -> None:
    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me:
            return
        for friend in _allies_with(c, "i2117"):
            c.shift(1, who=friend)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


@power(
    "i2502p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def i2502p1(c: Cast) -> None:
    """As i2500p1, plus the death-save bonus, and ended the same two ways.

    The bonus is ended beside the resistance rather than left on its own
    clock: one printed sentence governs both, so a wake-up that lifted
    only half of it would leave a bonus standing on a creature the card
    says is no longer under the shroud."""
    victim = c.target
    if victim is None:
        return
    held = c.resist(20, on=victim, until=When.ENCOUNTER)
    bonus = c.bonus("save", 2, on=victim, until=When.ENCOUNTER, kind="power")
    if held is None:
        return
    _ends_when_it_wakes(c, held, victim, also=bonus)
    c.endable(held, cost=ActionType.STANDARD)


@power("i2517x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2517x1(c: Cast) -> None:
    """The enhancement bonus and the critical dice are columns."""
    c.as_implement(on=c.me)


@power("i2517p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2517p1(c: Cast) -> None:
    """Used during a rest and paid out at the end of it."""


@power("i2710p1", level=7, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2710p1(c: Cast) -> None:
    """A pen that writes in another language."""


@power("i2824x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2824x1(c: Cast) -> None:
    """Read off `DamageApplied` rather than `Bloodied`, which does not name
    who did it. Paragon save penalties are out of scope."""

    def hurt(ev: DamageApplied) -> None:
        if ev.target != c.me or not c.bloodied(on=c.me):
            return
        if ev.source in (None, c.me):
            return
        c.immobilized(on=ev.source, until=When.SAVE_ENDS)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, once=True)


@power("i2833x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2833x1(c: Cast) -> None:
    """"A daily attack power that has an effect on a miss" is a header
    field: `Damage.half_on_miss`. Untyped."""

    def missed(ev: Miss) -> None:
        if ev.attacker != c.me:
            return
        row = get(ev.power)
        if row is None or row.usage is not Usage.DAILY:
            return
        if row.damage is None or not row.damage.half_on_miss:
            return
        gone = _spent_surges(c)
        if gone:
            c.bonus("damage", gone, on=c.me, until=When.EOT, once=True)

    c.watch(Miss, missed, until=When.ENCOUNTER)


@power("i2834x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2834x1(c: Cast) -> None:
    """Untyped, and both one-shot: "your next attack roll" and "your next
    damage roll"."""

    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, once=True)
        c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, once=True)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, once=True)


@power("i2996x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2996x1(c: Cast) -> None:
    """The class half of the line is not enforced."""
    c.as_implement(on=c.me)


@power("i2996p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2996p1(c: Cast) -> None:
    """A ritual, free of its components, during a short rest."""


@power("i3261p1", level=7, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3261p1(c: Cast) -> None:
    """Water by the gallon. The geyser's door-breaking is a check against
    an object and its recoil a Strength check, neither of which has a
    creature on the other end."""


@power(
    "i3271p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss all targets with an encounter power of level 3 or lower",
    on=Trigger(
        PowerResolved,
        _missed_everything,
        "you miss all targets with an encounter power of level 3 or lower",
    ),
)
def i3271p1(c: Cast) -> None:
    """Asked of `PowerResolved` rather than of `Miss`, because "all
    targets" is a question about a use and a `Miss` is announced once per
    target -- declared there, the first miss of a multi-target power
    answered even when a later one landed.

    `PowerResolved` is emitted after the body has run and after the use
    was noted, so the roll per target is on `rolls` and there is a spent
    use for `c.restore_use` to hand back. Paragon levels are out of
    scope."""
    ref = getattr(c.trigger, "power", "")
    if ref:
        c.restore_use(ref, on=c.me)


@power(
    "i3438x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3438x1(c: Cast) -> None:
    """"Only one shard at a time" is a carrying rule rather than a combat
    one. Paragon numbers are out of scope; this is the heroic +1."""
    c.set_origin("elemental", until=When.ENCOUNTER)
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        kind="item",
        when=_dtype_gate(DamageType.LIGHTNING, DamageType.THUNDER),
    )


@power(
    "i3438p1",
    level=7,
    cls=ITEM,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=Target(side="enemy", count=99, everyone=True),
    keywords=[Keyword.THUNDER],
    trigger="you take lightning damage from an enemy attack",
    on=Trigger(
        DamageApplied, _took(DamageType.LIGHTNING), "you take lightning damage"
    ),
)
def i3438p1(c: Cast) -> None:
    """No attack roll is printed. Paragon numbers are out of scope."""
    c.flat(3, dtype=DamageType.THUNDER)


@power(
    "i3440x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3440x1(c: Cast) -> None:
    """Ice walk is `c.ignores_difficult` naming the sort of ground, which is
    what its `kind` argument is for. Paragon numbers are out of scope."""
    c.set_origin("elemental", until=When.ENCOUNTER)
    c.ignores_difficult("ice", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("snow", on=c.me, until=When.ENCOUNTER)
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        kind="item",
        when=_dtype_gate(DamageType.COLD),
    )


@power(
    "i3440p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(1),
    target=Target(side="enemy", count=99, everyone=True),
    attack=Attack(vs=FORT, printed=12),
    trigger="you take cold damage from an enemy attack",
    on=Trigger(DamageApplied, _took(DamageType.COLD), "you take cold damage"),
)
def i3440p1(c: Cast) -> None:
    """"The shard's level + 5" is 12 at level 7, printed as the page prints
    it. Paragon bursts are out of scope."""
    if c.strike():
        c.immobilized(until=When.EONT)
        c.vulnerable(5, DamageType.COLD, until=When.EONT)


@power(
    "i777p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE],
)
def i777p1(c: Cast) -> None:
    """As i1666p1. Paragon numbers are out of scope."""
    _steam(c, "1d6")


# -- level 8 ----------------------------------------------------------------


@power(
    "i1031p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def i1031p1(c: Cast) -> None:
    """The attack half gates on the power's keywords and the damage half on
    the damage type, because those are the two contexts' words for the same
    sentence.

    A modifier carries no sustain cost, but `c.effect(sustain=)` does: a
    bare hold is what the minor action pays for and `c.on_sustain` lays
    the bonuses again each time it is paid. Laying them again rather than
    extending them is the same thing here -- they are gated, not
    one-shot, so a second copy of the same `kind` does not add."""

    def lay() -> None:
        for who in [c.me, *c.within(10, side="ally")]:
            c.bonus(
                "attack",
                1,
                on=who,
                until=When.EONT,
                kind="power",
                when=_keyword_gate(Keyword.NECROTIC),
            )
            c.bonus(
                "damage",
                1,
                on=who,
                until=When.EONT,
                kind="power",
                when=_dtype_gate(DamageType.NECROTIC),
            )

    lay()
    held = c.effect(
        f"{c.ref} sustained", until=When.SUSTAIN, on=c.me, sustain=MINOR
    )
    c.on_sustain(held, lay)


@power("i1142p1", level=8, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1142p1(c: Cast) -> None:
    """Five minutes of detecting magic, and an Arcana bonus."""


@power(
    "i1249p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=Target(side="enemy", count=1, max_size=Size.LARGE),
    attack=Attack(vs=FORT, printed=13),
    dropped=("c.movement_tax()",),
)
def i1249p1(c: Cast) -> None:
    """The push is the whole of what lands. "Each square closer costs an
    extra square" is a cost on one direction of movement and nothing
    charges for direction; sustaining it goes with it."""
    if c.strike():
        c.push(2)


@power("i1315x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1315x1(c: Cast) -> None:
    """Untyped. Paragon numbers are out of scope; this is the heroic +1."""

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            c.bonus("speed", 1, on=c.me, until=When.EONT)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


@power(
    "i1655x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1655x1(c: Cast) -> None:
    """Resistance has a duration and no spend, so "against the next damage
    dealt to you" is not `c.resist` at all: it is `c.reduce` in the
    before-window of the one blow, which is the same arithmetic and does
    happen once.

    The latch is by hand rather than `once=True`, because `c.reduce`
    changes a number and announces nothing -- and `c.watch`'s `once`
    reads whether the handler did anything off the log, so a reduction
    would never spend the hold. Paragon multipliers are out of scope."""

    def surged(ev: SurgeSpent) -> None:
        if ev.actor != c.me:
            return
        gone = _spent_surges(c)
        if not gone:
            return
        used: list[bool] = []

        def soak(hurt: DamageRolled) -> None:
            if used or hurt.target != c.me:
                return
            if c.reduce(gone, hurt):
                used.append(True)

        c.watch(
            DamageRolled, soak, until=When.ENCOUNTER, window=Window.BEFORE
        )

    c.watch(SurgeSpent, surged, until=When.ENCOUNTER)


@power(
    "i1662p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    defect="the card defers the statistics and the entry prints no block",
)
def i1662p1(c: Cast) -> None:
    """The horse is an ally that carries you, so it is a summon and a
    mount. Losing a surge when it drops is a clause about a creature that
    is gone; nothing watches its death."""
    made = c.summon_inline(Summon(speed=10))
    if made:
        c.ride(on=made)


@power("i1663p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.CONJURATION])
def i1663p1(c: Cast) -> None:
    """**It is not `m324`, and it was, for this row's whole life.**

    The entry's second `<h1>` prints a reduced block of its own and it is
    the one that governs: HP 13 against `m324`'s 82, no level or role at
    all, Reflex 20 and Will 19 against 18 and 18, and the first attack
    without the mark clause `m324a0` carries. So this row put a level-7
    soldier with **six times the printed hit points** on the board, with a
    rider the card does not grant, and reported finished -- invisible to
    every sweep, because firing and doing something is all `audit` asks.

    Found by comparing the two blocks while re-pointing the family: the
    row said "the page names by id", and the page does, immediately above
    a different block. #601.
    """
    _conjured(c, "m1663c0")


@power(
    "i1663p2",
    level=8,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def i1663p2(c: Cast) -> None:
    """The card names the power it hands back, and now there is a ref for
    it: the beast's second row, `m1663c0a1`.

    **Two things here were wrong and both followed from `i1663p1`'s ref.**
    It searched for `m324`, which is not what the page prints, so on a
    board holding the right creature this found nobody and returned. And
    it filtered `c.expended` to `Usage.RECHARGE` -- the block prints
    "(standard, encounter)", so even the wrong creature's spent power
    would not have matched. A row that could not fire either way.

    `c.servants()` rather than a walk over `c.allies()` reading `Ident`:
    `_conjured` binds what it summons, which is the relation this question
    is actually about, and an ally with the same ref somebody else
    summoned is not this item's beast.
    """
    beast = next((a for a in c.servants()
                  if (who := c.world.get(a, Ident)) is not None
                  and who.ref == "m1663c0"), None)
    if beast is None:
        return
    if "m1663c0a1" in c.expended(on=beast):
        c.restore_use("m1663c0a1", on=beast)


@power("i1750p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1750p1(c: Cast) -> None:
    """Finding a portal, during a rest."""


@power("i2490x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2490x1(c: Cast) -> None:
    """Mortar that makes a building harder to climb."""


@power(
    "i2693x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("cf:sorcerer-soul-nat20",),
)
def i2693x1(c: Cast) -> None:
    """The whole benefit widens a trigger that is not laid. The storm
    source is `cf:sorcerer-f0s2`, which plays -- but the natural-20 rider
    this card loosens to a 16 is that row's own dropped clause, so there
    is nothing standing for a wider trigger to fire."""


@power("i2708x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2708x1(c: Cast) -> None:
    """The count is taken after the surge that triggered this, which is the
    printed reading -- the surge just spent is one of them. Paragon
    multipliers are out of scope."""

    def surged(ev: SurgeSpent) -> None:
        if ev.actor != c.me:
            return
        gone = _spent_surges(c)
        if gone:
            c.heal(gone, on=c.me)

    c.watch(SurgeSpent, surged, until=When.ENCOUNTER)


@power(
    "i2830x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.teleport_as()",),
)
def i2830x1(c: Cast) -> None:
    """The whole benefit is a new way to spend a minor action, and the word
    has to be one `actions` reads back off the `"<what> as <cost>"` carrier
    `c.grant_action` lays. Counted: `shift` (`actions._movement`), `stand`
    and `escape` and `second_wind` (`_recovery`), `instinctive`, `command`,
    and a **power ref** (`_recasts`, the `c.recast` path). Nothing else, and
    anything else "is carried, costs nothing and does nothing".

    So a seventh word is a reader in `actions.legal` and not this row's to
    write, and the ref path is no way round it: the card prints no row to
    grant, and minting one would be inventing a ref. `c.teleport` itself
    works, and `c.shift_as` is this sentence for a shift."""


@power(
    "i2948x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2948x1(c: Cast) -> None:
    """Both bonuses untyped. "While you are raging" is the class's own
    `rage.raging`, as in i2050x1. Paragon numbers are out of scope."""
    from combat_engine.content.powers.barbarian.rage import raging

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev) or not raging(c.world, c.me):
            return
        c.bonus(
            "attack", 1, on=c.me, until=When.ENCOUNTER,
            when=_against(ev.attacker),
        )
        c.bonus(
            "damage", 2, on=c.me, until=When.ENCOUNTER,
            when=_against(ev.attacker),
        )

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("i3068p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(10), target=NO_TARGET)
def i3068p1(c: Cast) -> None:
    """Drawing a weapon is not an action the engine charges for, so the
    shift is the whole of what is left."""
    for friend in c.within(10, side="ally"):
        c.shift(1, who=friend)


@power(
    "i3111p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    dropped=("i3111p1.hit_rider",),
)
def i3111p1(c: Cast) -> None:
    """The d8 table modifies a base creature, and the base is `m3111c0`.

    Before the block was importable this hand-built a 1-hit-point Tiny
    `Summon` and the printed AC 18, the three non-AC defences and the
    `+6 vs AC` attack were simply absent -- so five of the eight faces had
    nothing to modify. Now the creature is a real row and the faces that
    are **properties of the creature** all land: a fly speed, darkvision,
    not provoking, a flat attack bonus, a climb speed.

    Still dropped, and it is now one clause rather than five: faces 3, 5
    and 8 change what the creature's *hit* does -- prone, extra poison,
    ongoing poison -- which is a rider on somebody else's attack row
    (`m3111c0a0`), and nothing scopes a hit rider onto another creature's
    row. That is a different gap from the missing block and gets its own
    symbol, per "one marker names one gap".
    """
    roll = c.roll("1d8")
    made = _conjured(c, "m3111c0", surge=False)
    if not made:
        return
    if roll == 1:
        c.mode("fly", 6, on=made, until=When.ENCOUNTER)
    elif roll == 2:
        c.darkvision(on=made, until=When.ENCOUNTER)
    elif roll == 4:
        c.no_provoke(on=made, until=When.ENCOUNTER)
    elif roll == 6:
        c.bonus("attack", 1, on=made, until=When.ENCOUNTER, kind="untyped")
    elif roll == 7:
        c.mode("climb", 6, on=made, until=When.ENCOUNTER)


@power(
    "i3115p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i3115p1(c: Cast) -> None:
    """Face 4-5 reads "the first attack that hits the target", by anybody
    -- so it is a `Hit` watch on the victim rather than a bonus on the
    wielder, which would only have covered the wielder's own swings.
    `once=True` is safe with the guard: the hold is spent by the first
    event that actually pays out, not by the first `Hit` of any kind."""
    roll = c.roll("1d6")
    if roll == 1:
        c.penalty("attack", 2, until=When.EOTNT)
    elif roll == 2:
        swing = c.roll("1d20")
        if swing % 2 == 0:
            c.flat(swing)
        else:
            c.heal(swing)
    elif roll == 3:
        c.prone()
    elif roll in (4, 5):
        foe = c.target
        if foe is None:
            return

        def struck(ev: Hit) -> None:
            if ev.target == foe:
                c.flat(c.roll("2d6"), on=foe)

        c.watch(Hit, struck, until=When.EONT, once=True)
    else:
        c.damage("1d10", dtype=DamageType.LIGHTNING)
        for near in c.within(1, of=c.target, side="any"):
            c.damage("1d10", dtype=DamageType.LIGHTNING, on=near)


@power("i3259x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3259x1(c: Cast) -> None:
    """An Arcana bonus for scrying rituals."""


@power("i3259p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3259p1(c: Cast) -> None:
    """Scrying at a hundred squares, opposed by Perception."""


@power(
    "i3439x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3439x1(c: Cast) -> None:
    """Earth walk names three sorts of ground, which is what
    `c.ignores_difficult`'s `kind` takes one at a time."""
    c.set_origin("elemental", until=When.ENCOUNTER)
    for ground in ("rubble", "uneven stone", "earth"):
        c.ignores_difficult(ground, on=c.me, until=When.ENCOUNTER)


@power(
    "i3439p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="you take fire damage from an enemy attack",
    on=Trigger(DamageApplied, _took(DamageType.FIRE), "you take fire damage"),
)
def i3439p1(c: Cast) -> None:
    """"Adjacent at the end of the shift" is why the enemies are gathered
    after it. Paragon numbers are out of scope."""
    c.shift(max(1, c.speed_of() // 2))
    for foe in c.within(1, side="enemy"):
        c.vulnerable(5, DamageType.FIRE, on=foe, until=When.SAVE_ENDS)


@power("i475x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i475x1(c: Cast) -> None:
    """A workshop that makes better alchemy."""


@power(
    "i780x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("query.race_named()",),
)
def i780x1(c: Cast) -> None:
    """A **standing** modifier gated on `reroll_by`, not a triggered one,
    and that is the whole simplification. `c.reroll_attack` re-sums the
    attack with `reroll_by` set to the ref that forced the roll and takes
    the *difference*, so a bonus laid once at arming reaches exactly the
    roll `p1450` buys and nothing else -- not the next attack, and not a
    magic weapon's reroll. `f217` is the same sentence without the ally
    clause. Untyped: the card prints no word in front of the bonus.

    The ally clause is asked inside the gate rather than at arming, because
    the card asks it at the moment of the reroll and allies move.

    Still dropped: of the two allies the line names, one is a race **by
    ref**, which `c.race_of` answers, and one is a race by its printed
    *word*. Nothing bridges a word to a ref -- the `race` table carries no
    word column, unlike `weapon.slug` -- so the second finds only a monster
    carrying it on its type line, never a character of that race."""

    def rerolling(ctx: dict[str, Any]) -> bool:
        if ctx.get("reroll_by") != "p1450":
            return False
        return any(c.is_kind("drow", on=a) or c.race_of(on=a) == "r3"
                   for a in c.within(10, side="ally"))

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=rerolling)


@power(
    "i780p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with the bow while an elf ally is within 10 squares",
    on=Trigger(
        Miss, both(by_me, ally_within(10)), "you miss with an ally near"
    ),
)
def i780p1(c: Cast) -> None:
    """The cost is charged now: `c.expend_row("p1449")` takes the use of
    the one racial power the brief names by ref, and the reroll only
    happens if it went through.

    The card offers a second, alternative price -- a racial trait's use
    -- which arrives as a name with no ref; an either/or whose second
    branch cannot be spelled is written as the branch that can, not as
    no price at all. Which weapon the bowstring is fitted to is not
    recorded either, so any miss answers."""
    if c.expend_row("p1449"):
        c.reroll_attack(keep="new")


@power("i826x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i826x1(c: Cast) -> None:
    """A planted blade that warns of burrowing, after standing a day."""


@power("i999x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i999x1(c: Cast) -> None:
    """A penalty takes no `kind`, which is the rule for all of them."""

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me:
            return
        seen = [f for f in c.within(10, side="enemy") if c.can_see(f)]
        if not seen:
            return
        foe = c.choose(seen, "which enemy takes the save penalty")
        if foe is not None:
            c.penalty("save", 2, on=foe, until=When.SAVE_ENDS)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


# -- level 9 ----------------------------------------------------------------


@power("i1014p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(10), target=NO_TARGET, keywords=[Keyword.ILLUSION])
def i1014p1(c: Cast) -> None:
    """Every active light source within 10 squares is suppressed.

    **"Light level only, in the other direction" was the whole docstring**,
    and the other direction is the one that matters: putting the lights out
    *creates* concealment where turning them on only removes it. #686.

    **Suspended, not ended**, which is what "suppressed" means and is why
    `Effects.suspend` exists (#470): the lamp is not destroyed and comes
    back when the encounter does. The card's own next sentence is the
    proof -- "light sources activated after you use this power function
    normally" -- so this is a one-time sweep of what is burning now and not
    a standing ban.

    Found by looking at the effect's **mods** rather than its label: a
    carried light is a `light_radius` entry whatever row laid it, and this
    card does not care which."""
    for who in [c.me, *c.within(10, side="any")]:
        for eff in list(c.world.effects.of(who)):
            # `Effect.mods` is `[(eid, Mod)]`, not `[Mod]`.
            if any(m.what == "light_radius" for _, m in eff.mods):
                c.world.effects.suspend(eff)


@power("i1109x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1109x1(c: Cast) -> None:
    """"The type you resist with your Dragon Soul resistance" is the build's
    own element, which `c.element` answers. A character with no such build
    has no type to deal, and the property correctly does nothing."""

    def paid() -> None:
        dtype = c.element(on=c.me)
        if dtype is None:
            return
        for foe in c.within(5, side="enemy"):
            c.flat(5, dtype=dtype, on=foe)

    _on_second_wind(c, paid)


@power(
    "i1171p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i1171p1(c: Cast) -> None:
    """The printed fly speed is 10, not the 8 this row guessed before the
    block was importable -- which is why a hand-picked mode list is not a
    substitute for the page."""
    _conjured(c, "m1171c0")


@power("i1208p1", level=9, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1208p1(c: Cast) -> None:
    """A pint of water."""


@power("i1209x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1209x1(c: Cast) -> None:
    """Ammunition is not counted, so a quiver that never runs out changes
    nothing a fight can see."""


@power("i1210p1", level=9, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.CONJURATION],
       out_of_combat=True)
def i1210p1(c: Cast) -> None:
    """As i1209x1: ammunition is not counted."""


@power("i1256p1", level=9, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1256p1(c: Cast) -> None:
    """Dinner for twelve."""


@power("i1256p2", level=9, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1256p2(c: Cast) -> None:
    """Clearing it away."""


@power("i1506p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(10), target=NO_TARGET)
def i1506p1(c: Cast) -> None:
    """`c.save(against=)` matches the effect's label by substring, which is
    how "an effect with the charm or fear keyword" is asked."""
    for who in [c.me, *c.within(10, side="ally")]:
        c.save(on=who, against="charm")
        c.save(on=who, against="fear")
        c.resist(10, DamageType.PSYCHIC, on=who, until=When.EONT)


@power("i1801x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1801x1(c: Cast) -> None:
    """A map that draws itself as you go."""


@power("i1854x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1854x1(c: Cast) -> None:
    """The enhancement bonus and the critical dice are columns."""
    c.as_implement(on=c.me)


@power("i1854p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.CHARM])
def i1854p1(c: Cast) -> None:
    """"Within 5 squares of the harp" is a zone rather than a duration --
    the penalty has to end when an enemy walks out of it, which is exactly
    what `c.grants_in` does and a plain `c.penalty` cannot. The harp stays
    where it was put, so the zone is anchored on the caster's square."""
    zone = c.zone(
        spread({c.here}, 5), until=When.EONT, sustain=MINOR
    )
    c.grants_in(zone, WILL, -2, side="enemy", kind="untyped")


@power(
    "i2022p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    requires=_aquatic,
    requires_text="there must be a body of water adjacent to you",
)
def i2022p1(c: Cast) -> None:
    """The water is a printed requirement, not a flavour line."""
    _conjured(c, "m2022c0")


@power("i2084p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET)
def i2084p1(c: Cast) -> None:
    """Freezing a liquid surface is laying ground where there was none,
    which is `c.floor`. Twenty contiguous squares is the burst 2 around
    the caster, near enough."""
    c.floor(spread({c.here}, 2), until=When.ENCOUNTER, sustain=None)


@power(
    "i2161x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2161x1(c: Cast) -> None:
    """"To a space within 3 squares of you" names the destination, so the
    teleport is given a square rather than a distance."""

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        for friend in c.allies():
            if not c.can_see(friend):
                continue
            sq = _free_near(c, 3)
            if sq is not None:
                c.teleport(20, who=friend, to=sq)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power(
    "i2704x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2704x1(c: Cast) -> None:
    """Untyped."""

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER,
            when=_against(ev.attacker),
        )

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("i3045p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(10), target=NO_TARGET)
def i3045p1(c: Cast) -> None:
    """"Not surprised when he or she wakes" is a condition the engine
    carries, so the row has something to take off even though waking a
    sleeper is not a thing a board does."""
    for friend in c.within(10, side="ally"):
        c.cure(Condition.UNCONSCIOUS, Condition.SURPRISED, on=friend)


@power(
    "i3262x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3262x1(c: Cast) -> None:
    """`c.wielding` reads what is in hand, but what is *worn* is
    `Gear.armour` and `chargen.LIGHT` is the set of weights that count as
    light -- the same pair four class features and two monsters already
    ask. No armour at all is cloth, which is in that set. Paragon numbers
    are out of scope; this is the heroic +1."""
    from combat_engine.chargen import LIGHT

    gear = c.world.get(c.me, Gear)
    if gear is None or gear.armour in LIGHT:
        c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i3351p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3351p1(c: Cast) -> None:
    """A toast, paid out at the end of an extended rest."""


@power("i3352x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3352x1(c: Cast) -> None:
    """Seeing across planes from the Feywild."""


@power(
    "i3441x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.shift_through_enemies()",),
)
def i3441x1(c: Cast) -> None:
    """Dropped, and re-aimed off `c.move_through_enemies()`, which is three
    different sentences in the tree. This one is a **standing permission on
    the mover** and there is nothing to lay it on: `share=True` is a
    permission on one *step*, passed by whoever calls `movement.shift`, and
    `movement._occupied` consults only the occupant's `shares_space` -- so a
    property cannot change what a shift the player chooses later is allowed
    to do. `c.overrun` is a trample, which this card does not print, and
    `c.phasing` goes through walls rather than through people. Without the
    movement the acid damage has no trigger either.

    The escape bonus is written and is not a skill bonus: `escape.attempt`
    sums an `escape` key off the struggling creature -- deliberately not
    `skill:acrobatics`, because a bonus to getting out of a grab is not a
    bonus to tumbling -- which is exactly "skill checks made as part of the
    escape action"."""
    c.set_origin("elemental", until=When.ENCOUNTER)
    c.bonus("escape", 5, on=c.me, until=When.ENCOUNTER, kind="item")


@power(
    "i3441p1",
    level=9,
    cls=ITEM,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="you take acid damage from an enemy attack",
    on=Trigger(DamageApplied, _took(DamageType.ACID), "you take acid damage"),
)
def i3441p1(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power(
    "i3538p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Defences.immune_keywords", "c.instinctive(fn=)"),
    requires_text="you must have used a summoning power near the tapestry",
)
def i3538p1(c: Cast) -> None:
    """"The summoned creature" is one creature, so this is the newest
    companion and not every one standing: `c.companions` arrives in order,
    and the Requirement puts this row's use immediately after the summoning
    one. Resist with no type is resist all damage, which is the printed
    line. Paragon numbers are out of scope.

    Re-aimed off `c.immune_keyword()`: `c.immune` takes a `Condition` and
    charm and fear are `Keyword`s with no condition standing for either, so
    the missing thing is immunity to a keyword recorded on `Defences` --
    which is the gap `f2884` and `f3736` already wait on from the asking
    side, under `Defences.immune_keywords`. One gap, one symbol.

    The self-command half was `c.instinctive(made)` and that is the wrong
    verb twice over. It **fires the block's own** Instinctive Effect, found
    through `Companion.ref`, so it answers False for exactly the creatures
    this clause is about -- the ones that "normally do nothing" print none.
    And `turns._uncommanded` already runs that effect at the end of the
    owner's turn for free, so where it did fire it fired a second time and
    at the wrong moment, the instant the tapestry was activated.

    What the card wants is to **lend** an instinctive effect to a block that
    prints none, which is `c.instinctive(fn=)`. Writing it here instead
    would mean rebinding the cast to `Companion.ref` by hand, because
    `c.command` reads `summon=` off the paying row's header and marks the
    creature commanded as a side effect -- engine plumbing that
    `c.instinctive` exists to hold."""
    mine = c.companions()
    if mine:
        c.resist(5, on=mine[-1], until=When.ENCOUNTER)


@power(
    "i3559p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i3559p1(c: Cast) -> None:
    """Four satyrs are four +1 item bonuses, and two of a kind do not
    stack -- so the bonus has to be one number, or the whole thing is
    worth +1. A modifier cannot lose a point, so the countdown is written
    as taking the holds down and laying them again one lower, which comes
    to the same number and keeps the printed `kind`.

    A satyr goes with each point: they are conjurations, so `c.dispel` is
    what removes one. They are given a label of their own, and that is
    load-bearing: `c.dispel` unwinds every effect its maker laid whose
    label begins with the conjuration's ref, so an unlabelled satyr would
    take this row's own bonuses -- and its two watchers -- down with the
    first one to leave."""
    satyrs: list[int] = []
    for sq in sorted(spread({c.here}, 1)):
        if len(satyrs) >= 4:
            break
        if sq == c.here or c.world.grid.occupant(sq) is not None:
            continue
        made = c.conjure(
            at=sq, label=f"{c.ref} satyr", until=When.ENCOUNTER,
            sustain=None, solid=True,
        )
        if made:
            satyrs.append(made)
    if not satyrs:
        return
    holds: list[Effect] = []

    def lay() -> None:
        for hold in holds:
            c.end_effect(hold, why=f"{c.ref} lost a satyr")
        holds.clear()
        left = len(satyrs)
        if not left:
            return
        for what in (AC, FORT, REF, WILL, "save"):
            hold = c.bonus(
                what, left, on=c.me, until=When.ENCOUNTER, kind="item"
            )
            if hold is not None:
                holds.append(hold)

    def spend() -> None:
        if not satyrs:
            return
        c.dispel(satyrs.pop())
        lay()

    def missed(ev: Miss) -> None:
        if ev.target == c.me:
            spend()

    def saved(ev: SavingThrow) -> None:
        if ev.actor == c.me and ev.saved:
            spend()

    lay()
    c.watch(Miss, missed, until=When.ENCOUNTER)
    c.watch(SavingThrow, saved, until=When.ENCOUNTER)


@power("i583x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i583x1(c: Cast) -> None:
    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        near = c.within(1, side="enemy") or c.enemies()
        if near:
            c.basic(on=near[0])

    c.watch(Bloodied, bled, until=When.ENCOUNTER, once=True)


@power("i619p1", level=9, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(3), target=NO_TARGET, keywords=[Keyword.ZONE])
def i619p1(c: Cast) -> None:
    """"Pulled toward the standard" is `anchor=`, which is the one way to
    say which way a forced move goes. The standard stands where it was
    planted, so the anchor is the caster's square at the time."""
    area = c.area()
    here = c.here
    c.zone(area, until=When.ENCOUNTER)

    def sweep() -> None:
        for foe in c.in_squares(area, side="enemy"):
            c.pull(2, on=foe, anchor=here)
            c.slowed(on=foe, until=When.SONT)

    sweep()

    def turn(ev: TurnStart) -> None:
        if getattr(ev, "actor", None) == c.me:
            sweep()

    c.watch(TurnStart, turn, until=When.ENCOUNTER)


@power(
    "i857x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i857x1(c: Cast) -> None:
    """The chaos source is the `wild` leg of `cf:sorcerer-f0`, whose burst
    is a latch on the first attack roll of each turn. This card's clause
    is a *second* burst rather than a change to that one -- it fires
    "even if it has already triggered this turn" -- so it is written as
    its own watch with its own numbers and the feature's latch is left
    alone. Both bonuses are untyped, as the class prints them, so a turn
    in which the feature's own burst also lands adds its +1 on top; the
    card says the bonus "increases to +3" and there is no kind to say it
    with."""

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me or not c.build("wild"):
            return

        def rolled(swing: AttackRolled) -> None:
            if swing.attacker != c.me:
                return
            if swing.natural % 2 == 0:
                c.bonus(AC, 3, on=c.me, until=When.SONT, kind="untyped")
            else:
                c.save(on=c.me, bonus=2)

        c.watch(AttackRolled, rolled, until=When.EOT, once=True)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER)


# -- level 10 ---------------------------------------------------------------


@power(
    "i1145p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(DEX, vs=REF),
    dropped=("c.object_target()",),
)
def i1145p1(c: Cast) -> None:
    """An item's rows *are* enumerable from a body, so "its powers cannot
    be activated" plays.

    `equipment.equip` installs them out of `Magic.powers` and puts the
    record in `Gear.worn`, so the list is one dictionary read away -- and
    `c.forbid` is exactly the sentence: the creature keeps the row, cannot
    reach it, and gets it back when the save lands.

    The attacker picks which worn item, because the card aims at an object
    and this row aims at the creature holding it. The enhancement half
    stays `c.decay`, which reaches a held magic weapon's attack and damage
    plus -- so it is called only for the item that carries one, and a
    chosen item whose bonus goes to a defence keeps it. That narrowness is
    `c.decay`'s and was here before.

    Dropped: an unattended object or a standing magical effect as the
    target, with its Reflex of 10 + level. Neither is a thing a power can
    be aimed at here -- only creatures and squares are."""
    if not c.strike():
        return
    foe = c.target
    gear = c.world.get(foe, Gear) if foe is not None else None
    worn = sorted(gear.worn) if gear is not None else []
    slot = worn[0] if len(worn) == 1 else c.choose(worn, f"{c.ref}: which item")
    if slot is None or gear is None:
        return
    item = gear.worn[slot]
    for ref in item.powers:
        c.forbid(ref, on=foe, until=When.SAVE_ENDS)
    if item.enh_to == "attack_damage":
        c.decay(on=foe, amount=item.plus or 6, until=When.SAVE_ENDS)


@power("i1154x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1154x1(c: Cast) -> None:
    """Paid out at the end of a short rest."""


@power(
    "i1179p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i1179p1(c: Cast) -> None:
    """One of the two blocks printing a real level and role, so this is a
    level-6 creature with 70 hit points rather than the surge-value beast
    `_figurine` made of it. Its printed speed is 2 with a fly 6 -- the row
    guessed a flat fly 10, five squares out and in the wrong field."""
    _conjured(c, "m1179c0")


@power("i1228x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1228x1(c: Cast) -> None:
    """An inventory of everything nearby, after a day standing still."""


@power("i1228p1", level=10, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1228p1(c: Cast) -> None:
    """Reading that inventory's total."""


@power("i1504x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1504x1(c: Cast) -> None:
    """A pack that holds more than it should."""


@power("i1592x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1592x1(c: Cast) -> None:
    """Ice that does not melt, with hit points of its own."""


@power("i1592p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1592p1(c: Cast) -> None:
    """A route through the dark."""


@power(
    "i1659p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    defect="the card defers the statistics and the entry prints no block",
)
def i1659p1(c: Cast) -> None:
    _figurine(c, speed=8)


@power(
    "i1664p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    requires=_aquatic,
    requires_text="there must be a body of water adjacent to you",
)
def i1664p1(c: Cast) -> None:
    _conjured(c, "m1664c0")


@power("i1717p1", level=10, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1717p1(c: Cast) -> None:
    """A bonus to monster knowledge checks and nothing else."""


@power(
    "i1804p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def i1804p1(c: Cast) -> None:
    _conjured(c, "m1804c0")


@power("i2037x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2037x1(c: Cast) -> None:
    """A bridle for a steed a ritual makes, outside a fight."""


@power("i2065p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2065p1(c: Cast) -> None:
    """Holding a ritual portal open."""


@power("i2354x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2354x1(c: Cast) -> None:
    """A very strong rope."""


@power("i2354p1", level=10, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2354p1(c: Cast) -> None:
    """A rope that ties itself, and explicitly cannot touch a creature."""


@power("i2381p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i2381p1(c: Cast) -> None:
    """The surge is spent instead of healing, which is `c.spend_surge`
    rather than `c.surge`. "One encounter attack power" is any level."""
    who = c.target
    if who is None:
        return
    spent = _restorable(c, top=c.level, who=who)
    if not spent or not c.may("spend a healing surge", who=who):
        return
    if not c.spend_surge(on=who):
        return
    pick = c.choose(spent, "which power to get back")
    if pick is not None:
        c.restore_use(pick, on=who)


@power("i2400x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2400x1(c: Cast) -> None:
    """Drawing a weapon costs nothing here, as in i2361x1."""


@power(
    "i2400p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
    trigger="you attack with the weapon most recently sheathed",
    on=Trigger(AttackDeclared, by_me, "you attack"),
    dropped=("c.sheathed()",),
)
def i2400p1(c: Cast) -> None:
    """One of the two clauses landed. `c.deals(once=True)` is "**the next**
    attack you make with that weapon", spent by the blow it recolours, where
    this held the retype for the whole printed window and recoloured every
    swing in it -- a row more generous than its card. `todo.py` went red
    naming this row the moment the parameter arrived, which is what that
    instrument is for. #711.

    `until=When.EONT` stays: the card prints a window as well as a count
    ("before the end of your next turn"), so the hold has to expire even if
    no attack is ever made.

    Still dropped: which weapon was last sheathed is not recorded --
    `Gear.stowed` is an unordered `set[str]` and no extended rest is
    modelled -- so the recolour reaches whatever is in hand, as in
    `i2361p1`. `c.sheathed()` is the symbol that row already waits on."""
    c.deals(DamageType.RADIANT, on=c.me, until=When.EONT, once=True)


@power("i2487x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2487x1(c: Cast) -> None:
    """A focus that sharpens a ritual circle."""


@power("i2493x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2493x1(c: Cast) -> None:
    """`PowerUsed` is announced before the body runs, which is right here:
    the row turns on the declaration rather than on any consequence. The
    sundial is where it was set down, read as the wearer's square. Both
    bonuses untyped, and they take in everybody, as printed."""

    def used(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        row = get(ev.power)
        if row is None or Keyword.RADIANT not in row.keywords:
            return
        for who in [c.me, *c.within(10, side="any")]:
            c.bonus("attack", 1, on=who, until=When.EONT)
            c.bonus("damage", 3, on=who, until=When.EONT)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power("i2522p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2522p1(c: Cast) -> None:
    """A Thievery check against a lock."""


@power("i2594p1", level=10, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2594p1(c: Cast) -> None:
    """Copying a page into a quill."""


@power("i2594p2", level=10, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2594p2(c: Cast) -> None:
    """Writing that page out again."""


@power(
    "i2827x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2827x1(c: Cast) -> None:
    """Two watches, because `DamageRolled` does not say the blow was a
    critical and `Hit` comes too early to move the number: the crit arms a
    one-shot interrupt and the interrupt moves the damage.

    "By any amount" is not `c.absorb`, which moves the whole blow or none
    of it -- it is `c.reduce` for the share and `c.flat` for the ally who
    takes it, which is the same pair `c.absorb` is built from. The share
    is offered largest first, so a board with nobody to ask still soaks
    the whole blow, which is the choice an ally with the item is
    presumably wearing it to make."""

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        helpers = _allies_with(c, "i2827")
        if not helpers:
            return

        def soak(hurt: DamageRolled) -> None:
            if hurt.target != c.me or hurt.amount <= 0:
                return
            share = c.choose(
                list(range(hurt.amount, -1, -1)), "how much of the blow to take"
            )
            if not share:
                return
            taken = c.reduce(share, hurt)
            if taken:
                c.flat(taken, on=helpers[0])

        c.watch(
            DamageRolled, soak, until=When.EOT, window=Window.BEFORE,
            once=True,
        )

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power(
    "i2828x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2828x1(c: Cast) -> None:
    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        for friend in _allies_with(c, "i2828"):
            c.grant_attack(friend, on=ev.attacker)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("i2892x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2892x1(c: Cast) -> None:
    """Twenty hours of recorded speech."""


@power("i2938p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH])
def i2938p1(c: Cast) -> None:
    """"You are considered an object and can take no actions" is petrified,
    which is that sentence exactly; `revert` is the printed minor action
    back out."""
    c.form(
        conditions=(Condition.PETRIFIED,),
        until=When.ENCOUNTER,
        revert=MINOR,
    )


@power(
    "i3106p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you score a critical hit on your turn",
    on=Trigger(Hit, _my_crit_on_my_turn, "you score a critical hit"),
)
def i3106p1(c: Cast) -> None:
    """The victim is read off the event: a self-triggered row aimed at one
    enemy would otherwise fall through to the auto-targeter."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.slide(2, on=foe)
    c.prone(on=foe)


@power(
    "i3263p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
)
def i3263p1(c: Cast) -> None:
    """**The old docstring had the card backwards.** It said a summon has
    no initiative slot of its own, and this card says the opposite in so
    many words: the creature "takes its turn on your initiative count
    according to commands you give to it". So it is in the order, on the
    caster's count, which is `after=c.me` -- and it was a bare `Summon()`
    with the summoner's defences standing in for a printed AC 24.

    No surge: this card grants none, unlike the figurines.
    """
    _conjured(c, "m3263c0", surge=False)


@power("i3353p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3353p1(c: Cast) -> None:
    """Overland travel, and it says so: "outside combat"."""


@power("i779p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i779p1(c: Cast) -> None:
    """Cleansing food and drink."""


@power(
    "i871p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def i871p1(c: Cast) -> None:
    """The zone attacks what walks into it, which is `ZoneEntered` and not
    a hazard -- a hazard deals damage and this rolls.

    "The effect ends if you or an ally attacks while in the zone" is
    `c.dispel`, which takes the zone down and unwinds the holds it laid;
    `c.on_attack` is the watch, since the swing may be anybody's on the
    team. It fires in the declaration window, so the zone is gone before
    the attack it answers resolves -- which is the printed order."""
    area = c.area()
    here = c.here
    zone = c.zone(area, until=When.EONT, sustain=STANDARD)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone != zone or ev.actor not in c.enemies():
            return
        if c.attack(15, FORT, on=ev.actor):
            c.push(1, on=ev.actor, anchor=here)
            c.immobilized(on=ev.actor, until=When.SOTNT)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)

    def struck(ev: AttackDeclared) -> None:
        if zone in c.my_zones() and ev.attacker in c.in_squares(area, side="team"):
            c.dispel(zone)

    c.on_attack(struck, until=When.ENCOUNTER)


@power("i994x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i994x1(c: Cast) -> None:
    """An Arcana bonus during a scrying ritual."""
