"""Arms-slot magic items, heroic tier: their Properties and their Powers.

Bracers and shields. Nothing here declares a shield: the base-item line --
light shield, heavy shield, any shield -- is a column in `game.db`, the
shield's own bonus to AC and Reflex belongs to the base item, and the level
and price are columns too. An arms item carries **no enhancement bonus at
all**, so `c.enhancement` never appears below; every number in this file is
one the card prints in full.

Four judgements run through the file.

* **The damage context has `power`, `opportunity`, `charge`, `dtype` and
  `crit`, and no weapon and no attacker.** "Melee damage rolls" and "damage
  from ranged and area attacks" are therefore gated on the *reach* of the
  power in the context, which is the one thing the ref can be looked up
  for. "Damage when attacking with a bow" cannot be gated that way, so it
  is asked of what the wearer is holding when the trait arms.
* **A shield's own bonus has no reader.** Three blocks print "equal to your
  shield bonus" or hand that bonus to somebody else, and `query` has no
  function that says what a shield is worth. They are marked.
* **Flanking is not a question the engine answers.** `query.flanking` does
  not exist, and three blocks turn on it.
* **`c.bonus(dice=)` is how a rolled rider is written**, and `crit_damage`
  is the modifier key `resolve.deal_damage` reads in the critical branch --
  so "+1d6 damage on a critical" is a modifier, not a watch. A rolled die
  added inside a crit branch with `c.damage` would come out maximised,
  which is why the typed ones below use `c.flat(c.roll(...))`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Healed,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    SavingThrow,
    Trigger,
    Usage,
    When,
    World,
    both,
    by_me,
    by_melee,
    get,
    power,
    query,
    targets_me,
)
from combat_engine.engine.components import Gear as _Gear
from combat_engine.engine.components import Powers as _Powers

ITEM = "item"

_ALL_DEFENCES = (AC, FORT, REF, WILL)


# -- shared shapes ----------------------------------------------------------


def _defences(c: Cast, value: int, **kw: Any) -> None:
    """"A bonus to all defences" is four modifiers; there is no key for the
    set, and inventing one would not be read by `query.defence`."""
    for d in _ALL_DEFENCES:
        c.bonus(d, value, **kw)


def _foe(c: Cast) -> int | None:
    """The other creature in the event this row is answering.

    `Triggers._at` aims a single-target enemy row at `ev.attacker`, which is
    the wrong creature for half the shapes in this slot. Reading the event
    is the only thing that is right every time.
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


def _temp(c: Cast) -> int:
    health = c.world.get(c.me, Health)
    return 0 if health is None else health.temp


def _surges(c: Cast) -> int:
    health = c.world.get(c.me, Health)
    return 0 if health is None else health.surges


def _against(who: int | None):  # noqa: ANN202
    """Attack or damage gate: this one is aimed at the named creature."""

    def gate(ctx: dict[str, Any]) -> bool:
        return who is not None and ctx.get("target") == who

    return gate


def _reach_is(*kinds: str):  # noqa: ANN202
    """Damage gate: the power in the context arrives in one of these shapes.

    The damage context carries no attacker and no `ranged` flag, so the
    power's own `Range.kind` is the only thing "melee damage rolls" and
    "damage from ranged and area attacks" have to turn on.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and p.reach is not None and p.reach.kind in kinds

    return gate


def _opportunity(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("opportunity"))


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


def _ongoing_save(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("ongoing"))


def _saves_against(*conditions: Condition, keywords: tuple[Keyword, ...] = ()):  # noqa: ANN202
    """Save gate: the hold being saved against carries one of these
    conditions, or was laid by a row printing one of those keywords --
    `durations.keywords_of` reads them back off the effect's label."""
    wanted = set(conditions)
    words = set(keywords)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("conditions") or ())) or bool(
            words & set(ctx.get("keywords", ()))
        )

    return gate


def _kind_attacking(c: Cast, word: str):  # noqa: ANN202
    """Defence gate: the creature swinging is of that type. The *attack*
    context carries `attacker`, which is why this can be said at all."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.is_kind(word, on=who)

    return gate


def _first_rounds(c: Cast):  # noqa: ANN202
    """"During the surprise round and the first nonsurprise round" -- the
    encounter counts its own rounds, so this is a gate rather than a
    duration nothing provides."""

    def gate(_ctx: dict[str, Any]) -> bool:
        return c.world.round <= 1

    return gate


def _protect(c: Cast, defence: Any, value: int) -> None:
    """The four "an attack against <defence> would hit an adjacent ally"
    interrupts, which are one shape printed four times.

    Declared on `AttackDeclared` rather than on `Hit`: the bonus is meant
    to apply to the attack being answered, and by the time a `Hit` exists
    the defence has already been compared against.
    """
    ally = getattr(c.trigger, "target", None)
    if ally is not None:
        c.bonus(defence, value, on=ally, until=When.EOT, kind="power")


# -- predicates -------------------------------------------------------------


def _adjacent_ally_targeted(*defences: Any):  # noqa: ANN202
    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if not _friend(world, me, who):
            return False
        if defences and getattr(ev, "vs", None) not in defences:
            return False
        return query.distance_between(world, me, who) <= 1

    return check


def _adjacent_ally_hit(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if not _friend(world, me, who):
        return False
    return query.distance_between(world, me, who) <= 1


def _adjacent_ally_healed(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if not _friend(world, me, who):
        return False
    return query.distance_between(world, me, who) <= 1


def _healed_in_sight(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    return who == me or _friend(world, me, who)


def _adjacent_ally_burned(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "dtype", None) is not DamageType.FIRE:
        return False
    return _adjacent_ally_hit(world, me, ev)


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "critical", False)


def _crit_on_my_ac_or_reflex(world: World, me: int, ev: Any) -> bool:
    return _crit_on_me(world, me, ev) and getattr(ev, "vs", None) in (AC, REF)


def _my_crit(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "critical", False)


def _enemy_hits_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and _enemy(
        world, me, getattr(ev, "attacker", None)
    )


def _enemy_within_10_hits_me(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if not _enemy_hits_me(world, me, ev):
        return False
    return query.distance_between(world, me, who) <= 10


def _radiant_on_me(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and Keyword.RADIANT in p.keywords


def _damage_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(
        ev, "source", None
    ) not in (None, me)


def _my_save(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me


def _enemy_saved(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "saved", False) and _enemy(
        world, me, getattr(ev, "actor", None)
    )


def _my_melee_hit(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and by_melee(world, me, ev)


def _my_adjacent_melee_hit(world: World, me: int, ev: Any) -> bool:
    if not _my_melee_hit(world, me, ev):
        return False
    return query.distance_between(world, me, getattr(ev, "target", -1)) <= 1


def _my_shield_shot_hit(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(
        ev, "power", ""
    ) == "i2875p1"


def _my_hit_on_shapechanger(world: World, me: int, ev: Any) -> bool:
    foe = getattr(ev, "target", None)
    return getattr(ev, "attacker", None) == me and foe is not None


# -- level 1 ----------------------------------------------------------------


@power("i1281x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.as_weapon()",))
def i1281x1(c: Cast) -> None:
    """A shield that is also a weapon has to become a `Weapon` in the
    wearer's hands -- a group, a die, a proficiency and an enhancement --
    and nothing turns a worn item into one."""


@power("i1322x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.water()",))
def i1322x1(c: Cast) -> None:
    """Swimming at your speed is a movement mode, which is the half that
    plays. Floating on the surface, and the Athletics and Endurance checks
    narrowed to swimming, are a water rule the board does not have."""
    if c.terrain("aquatic"):
        c.mode("swim", c.speed_of(), on=c.me, until=When.ENCOUNTER)


# -- level 2 ----------------------------------------------------------------


@power("i1013x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1013x1(c: Cast) -> None:
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_first_rounds(c))


@power("i1527x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.item_set()",))
def i1527x1(c: Cast) -> None:
    """A paired item: nothing links one worn item to another, so there is
    no second wearer to be aware of and no check to narrow onto."""


@power("i1673x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.charging()",))
def i1673x1(c: Cast) -> None:
    """The damage context carries `opportunity`, so the resistance is exact
    against every opening; nothing says the *run* was a charge, so it also
    covers the openings an ordinary walk gives. The second sentence turns
    on `AttackDeclared.charge`, which is on the event."""
    c.resist(5, on=c.me, until=When.ENCOUNTER, when=_opportunity)

    def charged(ev: AttackDeclared) -> None:
        if ev.attacker == c.me and getattr(ev, "charge", False):
            c.immovable(on=c.me, until=When.EONT)

    c.watch(AttackDeclared, charged, until=When.ENCOUNTER, on=c.me)


@power("i2098p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=NO_TARGET)
def i2098p1(c: Cast) -> None:
    amount = _surges(c)
    if amount <= 0:
        return
    c.temp_hp(amount, on=c.me)
    for ally in c.within(5, side="ally"):
        if ally != c.me:
            c.temp_hp(amount, on=ally)


@power("i2142p1", level=2, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a melee attack hits you",
       on=Trigger(Hit, both(targets_me, by_melee), "a melee attack hits you"))
def i2142p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.damage("1d8", c.con_mod, on=foe)


@power("i2474x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2474x1(c: Cast) -> None:
    c.resist(2, on=c.me, until=When.ENCOUNTER,
             when=_reach_is("ranged", "area_burst"))


@power("i2484p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i2484p1(c: Cast) -> None:
    ally = next((a for a in c.within(1, side="ally") if a != c.me), None)
    if ally is not None:
        c.bonus(AC, 1, on=ally, until=When.ENCOUNTER, kind="power")


@power("i3211x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3211x1(c: Cast) -> None:
    """`AttackDeclared` carries `charge`, and the charge's swing is the one
    moment the run can be recognised from."""

    def charged(ev: AttackDeclared) -> None:
        if ev.attacker == c.me and getattr(ev, "charge", False):
            _defences(c, 2, on=c.me, until=When.SONT, kind="item")

    c.watch(AttackDeclared, charged, until=When.ENCOUNTER, on=c.me)


@power("i702p1", level=2, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="a critical hit is scored against you",
       on=Trigger(Hit, _crit_on_me, "a critical hit lands on you"))
def i702p1(c: Cast) -> None:
    c.resist(5, on=c.me, until=When.EONT)


@power("i787x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i787x1(c: Cast) -> None:
    """Both halves are asked at read time rather than at arming time: a
    mark is laid and lifted during the fight, and a bonus fixed at the
    start of the encounter would name whoever happened to have marked the
    wearer then."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.marked(on=c.me, by=who)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=gate)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=gate)


@power("i792x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("query.is_basic_attack()",))
def i792x1(c: Cast) -> None:
    """Nothing says whether a ref is the creature's basic attack, so the
    bonus reaches every melee attack rather than only the basic."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_reach_is("melee"))


@power("i794p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.HEALING],
       trigger="an ally adjacent to you regains hit points",
       on=Trigger(Healed, _adjacent_ally_healed,
                  "an adjacent ally is healed"))
def i794p1(c: Cast) -> None:
    beside = [c.me, *(a for a in c.within(1, side="ally") if a != c.me)]
    who = c.choose(beside, "who regains the hit points")
    if who is not None:
        c.heal(c.roll("1d8"), on=who)


# -- level 3 ----------------------------------------------------------------


@power("i1229x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1229x1(c: Cast) -> None:
    """`crit_damage` is the key `resolve.deal_damage` reads in the critical
    branch, and `dice=` rolls afresh each time it is read -- which is what
    the printed "1d6 extra damage" means."""
    c.bonus("crit_damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER)


@power("i1296x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1296x1(c: Cast) -> None:
    """A `crit_damage` modifier is untyped, and this one is fire, so it is
    a watch instead. `c.flat(c.roll(...))` rather than `c.damage`, because
    `c.damage` maximises its dice on a critical and this die is rolled."""

    def crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        c.flat(c.roll("1d6"), dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


@power("i1296p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1296p1(c: Cast) -> None:
    """Typed extra damage is not a `c.bonus`, which carries no damage type
    of its own, so the next hit is watched for instead."""

    def landed(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.flat(c.roll("1d6"), dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me, once=True)


@power("i1764x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.silvered()",))
def i1764x1(c: Cast) -> None:
    """What a weapon is made of is not a property a creature can be given,
    and nothing on the board resists or fears silver."""


@power("i1764p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a shapechanger with a weapon attack",
       on=Trigger(Hit, _my_hit_on_shapechanger, "you hit a creature"),
       todo=("c.on_revert()", "c.forbid(keyword=)"))
def i1764p1(c: Cast) -> None:
    """Nothing puts a creature back into a shape it is not currently
    wearing, and `c.forbid` takes one ref rather than a keyword -- so both
    halves of the printed Effect are missing."""


@power("i2477p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=SELF)
def i2477p1(c: Cast) -> None:
    c.resist(10, on=c.me, until=When.EONT)
    ally = next((a for a in c.within(1, side="ally") if a != c.me), None)
    if ally is not None:
        c.resist(10, on=ally, until=When.EONT)


@power("i3213x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3213x1(c: Cast) -> None:
    _defences(c, 4, on=c.me, until=When.ENCOUNTER, kind="item", when=_charging)


@power("i3556p1", level=3, cls=ITEM, usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you roll a saving throw",
       on=Trigger(SavingThrow, _my_save, "you roll a saving throw"),
       dropped=("SavingThrow.condition",))
def i3556p1(c: Cast) -> None:
    """`SavingThrow` carries the effect only as a string, so the printed
    list of five conditions cannot be checked and the reroll is offered
    against any hold instead."""
    c.reroll_save()


@power("i782x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i782x1(c: Cast) -> None:
    """Asked at read time: power points are spent during the fight, and a
    bonus fixed when the trait armed would outlive the last point."""
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda _ctx: c.points() >= 1)


@power("i782p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.end_on_attack()",))
def i782p1(c: Cast) -> None:
    """The augment buys a longer hold, not a different one: "until you make
    an attack" is not a duration, so the augmented version runs to the end
    of the fight."""
    if c.spend_points(1):
        c.conceal(on=c.me, until=When.ENCOUNTER)
    else:
        c.conceal(on=c.me, until=When.SONT)


@power("i799x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("query.is_basic_attack()",))
def i799x1(c: Cast) -> None:
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_reach_is("ranged"))


# -- level 4 ----------------------------------------------------------------


@power("i1271p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       todo=("query.flanking(world, a, b)",))
def i1271p1(c: Cast) -> None:
    """"The nearest square from which you and an ally flank the target" has
    to be searched for, and nothing says whether two creatures flank."""


@power("i1893p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET)
def i1893p1(c: Cast) -> None:
    for ally in c.within(1, side="ally"):
        if ally != c.me:
            c.immovable(on=ally, until=When.EONT)


@power("i2475x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.shield_bonus()",))
def i2475x1(c: Cast) -> None:
    """A shield's contribution to AC is folded into the base item and
    nothing reports it as a number of its own."""


@power("i2475p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2475p1(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.EONT)


@power("i2478p1", level=4, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.silvered()",))
def i2478p1(c: Cast) -> None:
    """Light is not modelled and neither is what a weapon is made of, so
    both halves of this are absent rather than one."""


@power("i2479p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="a critical hit is scored against your AC or Reflex",
       on=Trigger(Hit, _crit_on_my_ac_or_reflex,
                  "a critical hit lands on your AC or Reflex"),
       dropped=("c.action_point(gain=False)",))
def i2479p1(c: Cast) -> None:
    """The encounter half is `c.expended` and `c.restore_use`. The other
    option spends an action point *without* buying an action with it, and
    `c.action_point` always hands the action over."""
    gone = []
    for ref in c.expended(on=c.me):
        p = get(ref)
        if p is not None and p.usage is Usage.ENCOUNTER and p.level <= 4:
            gone.append(ref)
    pick = c.choose(gone, "which encounter power comes back")
    if pick is not None:
        c.restore_use(pick, on=c.me)


@power("i3207p1", level=4, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=ONE_ALLY,
       todo=("query.shield_bonus()",))
def i3207p1(c: Cast) -> None:
    """Handing the shield's bonuses over needs the number they are worth,
    and nothing reports it."""


@power("i3207p2", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=ONE_ALLY, dropped=("When.UNBLOODIED",))
def i3207p2(c: Cast) -> None:
    """"Until he or she is no longer bloodied" is not a duration, so the
    resistance runs to the end of the fight."""
    hurt = [a for a in c.within(5, side="ally")
            if a != c.me and c.bloodied(on=a)]
    who = c.choose(hurt, "which bloodied ally is shielded")
    if who is not None:
        c.resist(5, on=who, until=When.ENCOUNTER)


@power("i627p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.HEALING],
       trigger="an ally adjacent to you regains hit points",
       on=Trigger(Healed, _adjacent_ally_healed,
                  "an adjacent ally is healed"))
def i627p1(c: Cast) -> None:
    """"As though it had spent a healing surge" -- the hit points arrive
    and no surge leaves the ally's pool."""
    ally = getattr(c.trigger, "target", None)
    if ally is not None:
        c.heal(c.surge_value(of=ally), on=ally)


@power("i718p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a melee attack",
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"))
def i718p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.ongoing(2 + c.cha_mod, on=foe)


@power("i963p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a melee attack misses you",
       on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses you"))
def i963p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.basic(on=foe)


# -- level 5 ----------------------------------------------------------------


@power("i1094p1", level=5, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an attack against Fortitude hits an ally adjacent to you",
       on=Trigger(AttackDeclared, _adjacent_ally_targeted(FORT),
                  "Fortitude is attacked on an adjacent ally"))
def i1094p1(c: Cast) -> None:
    _protect(c, FORT, 4)


@power("i2122x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.hit_twice()",))
def i2122x1(c: Cast) -> None:
    """Which hand swung is in the attack context and not on the `Hit`, so
    "you hit the same creature with both weapons" cannot be counted."""


@power("i2122p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.hit_twice()",))
def i2122p1(c: Cast) -> None:
    """Same missing question as the property above; the off-hand basic
    attack has no trigger to hang from."""


@power("i2492p1", level=5, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an attack against Reflex would hit an ally adjacent to you",
       on=Trigger(AttackDeclared, _adjacent_ally_targeted(REF),
                  "Reflex is attacked on an adjacent ally"))
def i2492p1(c: Cast) -> None:
    _protect(c, REF, 4)


@power("i468x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.consume_item()",))
def i468x1(c: Cast) -> None:
    """Consumable items are not carried, used or attacked with, so neither
    the attack bonus nor the waived opening has anything to attach to."""


@power("i606p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a melee attack",
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"))
def i606p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.push(c.roll("1d4"), on=foe)


@power("i785x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i785x1(c: Cast) -> None:
    """Swinging through trees without leaving tracks is the climb speed
    spent somewhere particular, which is the same modelled thing."""
    c.mode("climb", max(1, c.speed_of() // 2), on=c.me, until=When.ENCOUNTER)


@power("i804p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a melee attack",
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"),
       dropped=("c.vulnerable(once=)",))
def i804p1(c: Cast) -> None:
    """A vulnerability runs for its duration; "against the next attack that
    hits it" would spend it on the first blow, and nothing does that."""
    foe = _foe(c)
    if foe is not None:
        c.vulnerable(5, on=foe, until=When.EONT)


@power("i935p1", level=5, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an attack against Will would hit an ally adjacent to you",
       on=Trigger(AttackDeclared, _adjacent_ally_targeted(WILL),
                  "Will is attacked on an adjacent ally"))
def i935p1(c: Cast) -> None:
    _protect(c, WILL, 4)


@power("i965p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a melee attack",
       on=Trigger(Miss, both(by_me, by_melee), "you miss with a melee attack"))
def i965p1(c: Cast) -> None:
    c.reroll_attack()


# -- level 6 ----------------------------------------------------------------


@power("i1302x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1302x1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE)


@power("i1302p1", level=6, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an ally adjacent to you would take fire damage",
       on=Trigger(DamageRolled, _adjacent_ally_burned,
                  "fire is rolled against an adjacent ally"))
def i1302p1(c: Cast) -> None:
    """`DamageRolled` is announced before the damage is applied, which is
    the only window in which a resistance can still matter to it."""
    ally = getattr(c.trigger, "target", None)
    if ally is not None:
        c.resist(10, DamageType.FIRE, on=ally, until=When.EONT)


@power("i1334p1", level=6, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an attack against AC or Reflex hits an ally adjacent to you",
       on=Trigger(AttackDeclared, _adjacent_ally_targeted(AC, REF),
                  "AC or Reflex is attacked on an adjacent ally"))
def i1334p1(c: Cast) -> None:
    """"Already marked by you or an ally" is `Condition.MARKED` standing on
    the attacker, whoever laid it."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.is_(Condition.MARKED, on=foe):
        c.penalty("attack", 2, on=foe, until=When.EOT)
    else:
        c.mark(on=foe, until=When.SAVE_ENDS)


@power("i1648x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1648x1(c: Cast) -> None:
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_reach_is("melee"))


@power("i2875p1", level=6, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       attack=Attack(STR, vs=AC, plus=2))
def i2875p1(c: Cast) -> None:
    """The shield coming back to hand is what makes this at-will and costs
    nothing to say."""
    if c.strike():
        c.damage("1d8", c.str_mod)


@power("i2875p2", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with this shield's ranged attack",
       on=Trigger(Hit, _my_shield_shot_hit, "the thrown shield hits"))
def i2875p2(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.push(1, on=foe)


@power("i3036p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET)
def i3036p1(c: Cast) -> None:
    """`f650b` is a declared row, and what it is worth is a two-line rule
    rather than a stored number: +3 AC with a hand free, +1 otherwise.
    Nothing reads back a modifier already laid -- that is `Mods.applied()`
    and it is somebody else's marker -- so the rule is asked again here of
    the same gear rather than the answer being fetched.

    Gated on actually having the feature: a wearer who does not gets
    nothing, which is what "your f650b class feature" says.

    "Each ally adjacent to you" excludes the wearer, which is what
    `side="ally"` means as of today."""
    known = c.world.get(c.me, _Powers)
    if known is None or "f650b" not in known.known:
        return
    gear = c.world.get(c.me, _Gear)
    held = list(gear.held) if gear else []
    free = len(held) == 1 and not held[0].two_handed and not gear.shield
    for friend in c.within(1, side="ally"):
        c.bonus(AC, 3 if free else 1, on=friend, until=When.EONT, kind="power")


@power("i783x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i783x1(c: Cast) -> None:
    """The damage context carries no weapon, so the group is asked of what
    the wearer is holding when the trait arms and the bonus is then gated
    on the attack being a ranged one."""
    if c.held(what="bow") or c.held(what="crossbow"):
        c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
                when=_reach_is("ranged"))


@power("i783p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i783p1(c: Cast) -> None:
    """The weapon half is asked here rather than dropped: a wearer holding
    neither a bow nor a crossbow gets nothing, which is the printed rule."""
    if c.held(what="bow") or c.held(what="crossbow"):
        c.ignore_cover(on=c.me, until=When.EOT)


@power("i791p1", level=6, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.ability_for(ref)",))
def i791p1(c: Cast) -> None:
    """Which ability a roll uses is declared in the header and read from
    there; nothing swaps one out for another mid-fight."""


@power("i796x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i796x1(c: Cast) -> None:
    """The damage context carries `opportunity`, which is the whole gate."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
            when=_opportunity)


@power("i934x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i934x1(c: Cast) -> None:
    gate = _kind_attacking(c, "fey")
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, kind="item", when=gate)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, kind="item", when=gate)


# -- level 7 ----------------------------------------------------------------


@power("i1125x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.as_weapon()",))
def i1125x1(c: Cast) -> None:
    """A worn item cannot become a weapon in the wearer's hands."""


@power("i2024x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2024x1(c: Cast) -> None:
    """Two watches: the miss arms the rider, and the rider spends itself on
    the next melee hit. `once=True` is read off whether the handler did
    anything, so a miss in between does not burn it."""

    def missed(ev: Miss) -> None:
        if ev.target != c.me:
            return
        p = get(ev.power)
        if p is None or not ({Keyword.FIRE, Keyword.RADIANT} & set(p.keywords)):
            return

        def struck(hit: Hit) -> None:
            if hit.attacker == c.me and by_melee(c.world, c.me, hit):
                c.flat(2, dtype=DamageType.RADIANT, on=hit.target)

        c.watch(Hit, struck, until=When.EONT, on=c.me, once=True)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=c.me)


@power("i2141x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.escape()",))
def i2141x1(c: Cast) -> None:
    """An escape attempt is not a thing the engine has -- no action, no
    check -- so the bonus to one has nowhere to go. The grab itself is
    announced, which is where the damage hangs."""

    def seized(ev: ConditionApplied) -> None:
        if ev.target != c.me or ev.condition is not Condition.GRABBED:
            return
        c.damage("1d10", on=ev.source)

    c.watch(ConditionApplied, seized, until=When.ENCOUNTER, on=c.me)


@power("i2525p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2525p1(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d10", on=c.me, until=When.EONT, once=True)


@power("i2936p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you score a critical hit",
       on=Trigger(Hit, _my_crit, "you score a critical hit"))
def i2936p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.no_healing(on=foe, until=When.SAVE_ENDS)


@power("i786p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by a melee attack",
       on=Trigger(DamageRolled, both(targets_me, by_melee),
                  "melee damage is rolled against you"))
def i786p1(c: Cast) -> None:
    """Declared on the damage rather than on the hit: `c.reduce` needs a
    number that has been rolled and not yet applied, and `by_melee` reads
    the reach off `DamageRolled.detail`."""
    c.reduce(10, c.trigger)


@power("i788p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are the target of a melee attack",
       on=Trigger(AttackDeclared, both(targets_me, by_melee),
                  "a melee attack is aimed at you"))
def i788p1(c: Cast) -> None:
    c.teleport(2)


# -- level 8 ----------------------------------------------------------------


@power("i1501x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1501x1(c: Cast) -> None:
    """Hammer is a printed group the weapon table carries and `chargen`
    now deals, so the gate is real. An always-on Property is armed once
    and watches from there; the group is read off what is in hand,
    because `Hit` names the power and not the weapon."""
    me = c.me

    def landed(ev: Hit) -> None:
        gear = c.world.get(me, _Gear)
        if ev.attacker != me or gear is None:
            return
        if any(w.group == "hammer" for w in gear.held):
            for where in (AC, FORT, REF, WILL):
                c.bonus(where, 1, on=me, until=When.SONT)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me)


@power("i1794p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_ENEMY,
       attack=Attack(STR, vs=AC, plus=2))
def i1794p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.str_mod)


@power("i1862p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a melee attack",
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"))
def i1862p1(c: Cast) -> None:
    """The secondary attack prints a flat +11, which is the item's own
    number and not the wearer's, so `c.attack` takes it raw."""
    foe = _foe(c)
    if foe is None:
        return
    if c.attack(11, WILL, on=foe).hit:
        c.dazed(on=foe, until=When.EONT)


@power("i1873x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1873x1(c: Cast) -> None:
    def glare(ev: Hit) -> None:
        if not _radiant_on_me(c.world, c.me, ev):
            return
        c.flat(2, dtype=DamageType.RADIANT, on=ev.attacker)

    c.watch(Hit, glare, until=When.ENCOUNTER, on=c.me)


@power("i2053x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.flanking(world, a, b)",))
def i2053x1(c: Cast) -> None:
    """Nothing says whether two creatures flank a third."""


@power("i2473p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="a critical hit is scored on you",
       on=Trigger(Hit, _crit_on_me, "a critical hit lands on you"))
def i2473p1(c: Cast) -> None:
    c.surge(on=c.me)


@power("i2692x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2692x1(c: Cast) -> None:
    c.resist(5, DamageType.LIGHTNING)
    c.resist(5, DamageType.THUNDER)


@power("i2692p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
       trigger="you are hit by a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "a melee attack hits you"))
def i2692p1(c: Cast) -> None:
    """The parenthesis on the card is the general rule for a blow of two
    types, and `dtypes=` is it: resistance and immunity count only as far
    as they cover both. Paragon numbers are out of scope."""
    foe = _foe(c)
    if foe is not None:
        c.damage(
            "2d6", dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=foe
        )


@power("i3101p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, todo=("c.uncrit()",))
def i3101p1(c: Cast) -> None:
    """Turning a critical back into an ordinary hit means unmaking the
    result the roll already decided, and nothing does it."""


@power("i3206x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3206x1(c: Cast) -> None:
    c.resist(5, DamageType.LIGHTNING)
    c.resist(5, DamageType.THUNDER)


@power("i3206p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=Ranged(10), target=NO_TARGET,
       keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
       trigger="an enemy within 10 squares hits you",
       on=Trigger(Hit, _enemy_within_10_hits_me, "an enemy within 10 hits you"))
def i3206p1(c: Cast) -> None:
    """Ten points that are lightning and thunder at once. The second
    sentence hands the use back rather than never spending it, which is
    the same outcome a round later than the card describes: `c.restore_use`
    is the only door, and the use is already gone by the time a row runs.

    What the triggering attack dealt is read off the `Hit`'s live
    `AttackResult`... which does not carry a type, so it is read off the
    attacking power's keywords instead -- the card's "deals lightning or
    thunder damage" and the keyword line are the same sentence.
    """
    foe = _foe(c)
    if foe is None:
        return
    c.flat(10, dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=foe)
    theirs = get(getattr(c.trigger, "power", "") or "")
    if theirs is not None and (
        Keyword.LIGHTNING in theirs.keywords or Keyword.THUNDER in theirs.keywords
    ):
        c.restore_use(c.ref)


@power("i3212p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=SELF,
       dropped=("c.grants_in(when=)", "c.zone(ends_on=)"))
def i3212p1(c: Cast) -> None:
    """Concealment is a modifier the creature carries, and `c.grants_in`
    lays one for as long as a creature stands in the aura. It carries no
    gate, so the concealment covers melee as well as ranged, and nothing
    ends an aura when its owner moves."""
    aura = c.aura(1, label=c.ref, until=When.ENCOUNTER, on=c.me)
    if aura:
        c.grants_in(aura, "concealment", 2, side="any")


@power("i784p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i784p1(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.EONT, kind="power", when=_opportunity)


@power("i793p1", level=8, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF)
def i793p1(c: Cast) -> None:
    """"All rolls" is the attack roll, the damage roll and the saving
    throw; the defences are named separately on the card."""
    c.bonus("attack", 1, on=c.me, until=When.EONT, kind="item")
    c.bonus("damage", 1, on=c.me, until=When.EONT, kind="item")
    c.bonus("save", 1, on=c.me, until=When.EONT, kind="item")
    _defences(c, 1, on=c.me, until=When.EONT, kind="item")


@power("i863x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i863x1(c: Cast) -> None:
    """The save context says whether the hold being saved against burns,
    which is exactly "against ongoing damage"."""
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_ongoing_save)


@power("i863p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy you can see succeeds on a saving throw",
       on=Trigger(SavingThrow, _enemy_saved, "an enemy saves"))
def i863p1(c: Cast) -> None:
    c.save(on=c.me)


# -- level 9 ----------------------------------------------------------------


@power("i1082p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("query.damaged_since()",))
def i1082p1(c: Cast) -> None:
    """"A damage type you were dealt since the end of your last turn" is a
    question about the recent past, and nothing keeps that tally."""


@power("i1682x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=CloseBurst(1), target=SELF,
       dropped=("query.provoked_by()",))
def i1682x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so the bonus is exact
    against every opening; what provoked it is not recorded, so it also
    covers the openings an ally's walk gives."""
    for ally in c.within(1, side="ally"):
        if ally == c.me:
            continue
        c.bonus(AC, 2, on=ally, until=When.ENCOUNTER, kind="shield",
                when=_opportunity)
        c.bonus(REF, 2, on=ally, until=When.ENCOUNTER, kind="shield",
                when=_opportunity)


@power("i1682p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       todo=("query.provoked_by()",))
def i1682p1(c: Cast) -> None:
    """An opportunity attack does not record what provoked it, so "an ally
    provokes one by using a ranged power" has no trigger to declare."""


@power("i2155p1", level=9, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a melee attack hits you",
       on=Trigger(Hit, both(targets_me, by_melee), "a melee attack hits you"))
def i2155p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.prone(on=foe)


@power("i2455p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i2455p1(c: Cast) -> None:
    ally = next((a for a in c.within(1, side="ally") if a != c.me), None)
    if ally is not None:
        c.conceal(on=ally, until=When.SONT)


@power("i2483x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.flanking(world, a, b)",))
def i2483x1(c: Cast) -> None:
    """"While you are flanked" is the same unanswered question."""


@power("i3204x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3204x1(c: Cast) -> None:
    """Light only."""


@power("i3204p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an attack deals a particular type of damage to you",
       on=Trigger(DamageApplied, _damage_on_me, "you are damaged"))
def i3204p1(c: Cast) -> None:
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


@power("i3402x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.max_hp()",))
def i3402x1(c: Cast) -> None:
    """Three of the four named effects are conditions the hold carries;
    charm is a keyword of the row that laid it, which the save context
    now carries. Nothing lowers a creature's maximum hit points."""
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_saves_against(Condition.STUNNED, Condition.DAZED,
                                Condition.DOMINATED,
                                keywords=(Keyword.CHARM,)))


@power("i514p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=Melee(1), target=NO_TARGET,
       trigger="an ally adjacent to you is hit by an attack",
       on=Trigger(Hit, _adjacent_ally_hit, "an adjacent ally is hit"))
def i514p1(c: Cast) -> None:
    """`Hit` carries the defence it was rolled against as a plain
    attribute, which is what "the defense that the attack targeted"
    needs."""
    ally = getattr(c.trigger, "target", None)
    defence = getattr(c.trigger, "vs", None)
    if ally is not None and defence is not None:
        c.bonus(defence, 1, on=ally, until=When.ENCOUNTER, kind="power")


@power("i712p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=NO_TARGET)
def i712p1(c: Cast) -> None:
    """"This power affects bloodied targets only" is the whole choice: an
    unbloodied wearer is offered its neighbours instead."""
    hurt = [w for w in (c.me, *c.within(1, side="ally")) if c.bloodied(on=w)]
    who = c.choose(sorted(set(hurt)), "who gains the resistance")
    if who is not None:
        c.resist(5, on=who, until=When.EONT)


@power("i714p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("When.UNBLOODIED",))
def i714p1(c: Cast) -> None:
    """"Until you are no longer bloodied" is not a duration the engine
    has, so the resistance runs to the end of the fight."""
    if c.bloodied(on=c.me):
        c.resist(2, on=c.me, until=When.ENCOUNTER)


@power("i798p1", level=9, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an adjacent enemy with a melee attack power while "
               "you have temporary hit points",
       on=Trigger(Hit, _my_adjacent_melee_hit, "you hit an adjacent enemy"))
def i798p1(c: Cast) -> None:
    """The temporary hit points are spent off `Health.temp` directly:
    nothing takes them away, because nothing else in the game ever wanted
    to."""
    foe = _foe(c)
    spend = min(5, _temp(c))
    if foe is None or spend <= 0:
        return
    health = c.world.get(c.me, Health)
    if health is not None:
        health.temp -= spend
    c.flat(spend, on=foe)


# -- level 10 ---------------------------------------------------------------


@power("i1487p1", level=10, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an adjacent ally is hit by an attack",
       on=Trigger(AttackDeclared, _adjacent_ally_targeted(),
                  "an attack is aimed at an adjacent ally"),
       dropped=("c.on_damage_dealt()",))
def i1487p1(c: Cast) -> None:
    """The blow is moved with `c.redirect`, which is the whole first half.
    The resistance is "half the damage dealt", and at the moment an
    interrupt runs no damage has been rolled."""
    c.redirect(to=c.me)


@power("i1525p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       trigger="you or an ally in line of sight regains hit points",
       on=Trigger(Healed, _healed_in_sight,
                  "somebody on your side is healed"),
       dropped=("c.maximise(healing=)",))
def i1525p1(c: Cast) -> None:
    """`Healed` is announced before the hit points go on and its `amount`
    is read back, so the ability modifier is added there. Maximising the
    *source* of the healing is a different operation and has no verb."""
    ev = c.trigger
    if ev is not None:
        ev.amount += max(c.wis_mod, c.cha_mod)


@power("i604x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i604x1(c: Cast) -> None:
    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        c.bonus("attack", 1, on=c.me, until=When.EOT, when=_against(ev.target))

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i713p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("When.UNBLOODIED",))
def i713p1(c: Cast) -> None:
    if c.bloodied(on=c.me):
        c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, kind="power",
                when=_reach_is("melee"))


@power("i730p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, _damage_on_me, "you are damaged"))
def i730p1(c: Cast) -> None:
    c.temp_hp(10 if c.spend_points(1) else 5, on=c.me)
    c.shift(1)
