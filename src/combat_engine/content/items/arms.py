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
* **A shield's own bonus has no reader.** Two blocks print "equal to your
  shield bonus" or hand that bonus to somebody else. `Gear.shield` is a
  bool and the number is folded into the base item's AC, so nothing says
  what a shield is worth. They are marked.
* **Flanking *is* answered.** `query.flanked_by(world, target, attacker)`
  is the whole question for "while you are flanked"; the two shapes that
  name a particular partner need the pairwise half underneath it, which is
  `world.grid.flanks(a, b, space)` -- `_flank_pair` below.
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
    DamageApplied,
    DamageRolled,
    DamageType,
    Healed,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    OpportunityWindow,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    SavingThrow,
    Trigger,
    TurnEnd,
    Usage,
    When,
    Window,
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


def _flank_pair(world: World, me: int, mate: int, foe: int) -> bool:
    """Do `me` and `mate` in particular flank `foe`?

    `query.flanked_by` asks whether *anybody* holds the far side, which is
    the wrong question for "that ally gains" -- the card pays the partner,
    so the partner has to be named. This is `flanked_by`'s inner loop with
    the mate fixed.
    """
    if me == mate or mate == foe:
        return False
    if not query.can_act(world, me) or not query.can_act(world, mate):
        return False
    space = query.squares(world, foe)
    return any(
        world.grid.flanks(a, b, space)
        for a in query.squares(world, me)
        for b in query.squares(world, mate)
    )


def _is_basic(c: Cast, ref: str, window: str = "") -> bool:
    """Is that ref the wearer's basic attack, or something standing in for
    one? `Powers.basic`/`Powers.ranged` name the swing itself and
    `instead_of_basic` names what `c.as_basic` has filed beside it, which
    by the printed rule counts as a basic attack too."""
    known = c.world.get(c.me, _Powers)
    if known is None:
        return False
    own = (known.ranged if window == "ranged" else known.basic) or (
        "rba" if window == "ranged" else "mba"
    )
    return ref == own or ref in known.instead_of_basic(window)


def _while_bloodied(c: Cast, who: int, effect: Any) -> None:
    """"...until he or she is no longer bloodied."

    Not a `When`, and it does not need to be: nothing but healing lifts a
    creature back out of bloodied, and `Healed` is announced for every
    point that arrives. The watch is hung on the beneficiary so it travels
    with them.
    """
    if effect is None:
        return

    def mended(ev: Healed) -> None:
        if ev.target == who and not c.bloodied(on=who):
            c.end_effect(effect, on=who, why="no longer bloodied")

    c.watch(Healed, mended, until=When.ENCOUNTER, on=who)


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


def _polymorph_rows(world: World, who: int | None) -> list[str]:
    """Which of that creature's rows change its shape.

    No type line is loaded mid-fight, so "a shapechanger" is read as a
    creature that has somewhere to change to -- which is also the only
    thing the printed Effect acts on.
    """
    known = None if who is None else world.get(who, _Powers)
    if known is None:
        return []
    return [
        ref
        for ref in known.known
        if (p := get(ref)) is not None and Keyword.POLYMORPH in p.keywords
    ]


def _my_hit_on_shapechanger(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and bool(
        _polymorph_rows(world, getattr(ev, "target", None))
    )


def _my_attack_on_adjacent(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    who = getattr(ev, "target", None)
    return who is not None and query.distance_between(world, me, who) <= 1


def _ally_provokes_ranged(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "provoker", None)
    if not _friend(world, me, who):
        return False
    if "ranged power" not in getattr(ev, "why", ""):
        return False
    return query.distance_between(world, me, who) <= 1


_HELD_SAVES = frozenset(
    {
        Condition.DAZED,
        Condition.IMMOBILIZED,
        Condition.PETRIFIED,
        Condition.RESTRAINED,
        Condition.STUNNED,
    }
)


def _my_save_against_hold(world: World, me: int, ev: Any) -> bool:
    """`SavingThrow.against` is `str(eff)` and carries no conditions -- but
    the effect it names is still standing on the saver, so the printed list
    of five is checked there instead of on the event."""
    if getattr(ev, "actor", None) != me:
        return False
    against = getattr(ev, "against", "")
    return any(
        str(eff) == against and _HELD_SAVES & set(eff.conditions)
        for eff in world.effects.of(me)
    )


# -- level 1 ----------------------------------------------------------------


@power("i1281x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, )
def i1281x1(c: Cast) -> None:
    """A shield that is also a heavy blade: +3 proficiency, 1d6, off-hand.

    `i1125x1`'s sibling and the same argument -- see it for why the profile
    is hand-written and why the weapon starts on the belt.
    """
    c.as_weapon(damage="1d6", group="heavy blade", proficiency=3,
                properties=frozenset({"off-hand"}))
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
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1527x1(c: Cast) -> None:
    """Deliberately inert. The whole printed benefit is knowledge about
    whoever wears the other half of the pair -- their heartbeat, whether
    they are bloodied or held, and a bonus to one skill check against
    them. That person is somewhere else by construction, so nothing here
    can change a fight the wearer is in."""


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
       reach=PERSONAL, target=SELF)
def i792x1(c: Cast) -> None:
    """Which ref a creature's basic attack is *is* recorded --
    `Powers.basic`, plus whatever `c.as_basic` has filed beside it, which
    the printed rule counts as a basic attack too. So the gate is exact
    and the bonus does not leak onto every melee swing."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: _is_basic(c, ctx.get("power") or ""))


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
       reach=PERSONAL, target=SELF, todo=("compendium.silvered",))
def i1764x1(c: Cast) -> None:
    """What a weapon is made of is not a property a creature can be given,
    and nothing on the board resists or fears silver."""


@power("i1764p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a shapechanger with a weapon attack",
       on=Trigger(Hit, _my_hit_on_shapechanger,
                  "you hit a creature that can change shape"),
       dropped=("c.on_revert()",))
def i1764p1(c: Cast) -> None:
    """Shutting the shapes off is `c.forbid` on each of the target's own
    polymorph rows: `c.forbid` takes one ref rather than a keyword, so the
    keyword is spread over them here. Having any such row is also what the
    trigger reads as "a shapechanger", since no type line is loaded
    mid-fight.

    Putting a creature back into a shape it is not currently wearing has
    no verb -- `c.form(revert=)` ends a form the *caster* took."""
    foe = _foe(c)
    for ref in _polymorph_rows(c.world, foe):
        c.forbid(ref, on=foe, until=When.SAVE_ENDS)


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
       on=Trigger(SavingThrow, _my_save_against_hold,
                  "you save against a hold this item answers"))
def i3556p1(c: Cast) -> None:
    """The printed list of five is checked in the predicate, off the
    effect rather than off the event -- see `_my_save_against_hold`. That
    is where it belongs: narrowing in the body would spend the use on a
    save the card does not cover.

    `keep="new"` is the default, which is "even if it is lower"."""
    c.reroll_save()


@power("i782x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i782x1(c: Cast) -> None:
    """Asked at read time: power points are spent during the fight, and a
    bonus fixed when the trait armed would outlive the last point."""
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda _ctx: c.points() >= 1)


@power("i782p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i782p1(c: Cast) -> None:
    """"Until you make an attack" is not a `When` and does not need to be:
    the augmented concealment is held to the end of the fight and torn
    down on the wearer's next `AttackDeclared`, which is the event that
    sentence names."""
    if not c.spend_points(1):
        c.conceal(on=c.me, until=When.SONT)
        return
    hidden = c.conceal(on=c.me, until=When.ENCOUNTER)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me:
            c.end_effect(hidden, on=c.me, why="you made an attack")

    c.watch(AttackDeclared, swung, until=When.ENCOUNTER, on=c.me)


@power("i799x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i799x1(c: Cast) -> None:
    """The ranged half of the same question: `Powers.ranged` names the
    shot, and `instead_of_basic("ranged")` names what stands in for it."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: _is_basic(c, ctx.get("power") or "", "ranged"))


# -- level 4 ----------------------------------------------------------------


@power("i1271p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="you attack an adjacent target, before you roll",
       on=Trigger(AttackDeclared, _my_attack_on_adjacent,
                  "you aim an attack at an adjacent creature"))
def i1271p1(c: Cast) -> None:
    """Declared on `AttackDeclared`, which is the "before you roll" window.

    "The nearest square from which you and an ally flank the target" is a
    search: every square beside the target, kept when some ally already
    holds the far side of it, taken in order of how far it is from where
    the wearer stands. `c.teleport(to=)` refuses a square the wearer does
    not fit in, so the list is tried in order rather than filtered first.
    """
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    space = query.squares(c.world, foe)
    here = min(query.squares(c.world, c.me))
    beside = [
        b
        for mate in c.allies()
        if query.can_act(c.world, mate)
        for b in query.squares(c.world, mate)
    ]

    def flanks_from(sq: Any) -> bool:
        return any(c.world.grid.flanks(sq, b, space) for b in beside)

    options = sorted(
        (sq for sq in query.spread(space, 1) - space if flanks_from(sq)),
        key=lambda sq: (max(abs(sq[0] - here[0]), abs(sq[1] - here[1])), sq),
    )
    for sq in options:
        if c.teleport(10, to=sq):
            return


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
       reach=PERSONAL, target=SELF, todo=("compendium.silvered",))
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
       reach=CloseBurst(5), target=ONE_ALLY)
def i3207p2(c: Cast) -> None:
    """"Or until he or she is no longer bloodied, whichever comes first":
    held to the end of the encounter and torn down by `_while_bloodied`,
    which watches the ally's own healing."""
    hurt = [a for a in c.within(5, side="ally")
            if a != c.me and c.bloodied(on=a)]
    who = c.choose(hurt, "which bloodied ally is shielded")
    if who is not None:
        _while_bloodied(c, who, c.resist(5, on=who, until=When.ENCOUNTER))


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
       reach=PERSONAL, target=SELF)
def i2122x1(c: Cast) -> None:
    """`hand` rides the `Hit` as a plain attribute, so `getattr`. The
    printed line is "when using a power", so the tally is per use and is
    cleared on the next announcement rather than at the end of the turn."""
    me = c.me
    struck: dict[int, set[str]] = {}

    def fresh(ev: PowerUsed) -> None:
        if ev.actor == me:
            struck.clear()

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        hands = struck.setdefault(ev.target, set())
        hand = getattr(ev, "hand", "main")
        if hand in hands:
            return
        hands.add(hand)
        if len(hands) > 1:
            c.damage("1d6", on=ev.target, detail=c.ref)

    c.watch(PowerUsed, fresh, until=When.ENCOUNTER)
    c.watch(Hit, landed, until=When.ENCOUNTER)


@power("i2122p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       trigger="you hit with both your main weapon and your off-hand "
               "weapon using one power",
       dropped=("Cast.basic(hand=)", "query.hit_with_both_hands()"))
def i2122p1(c: Cast) -> None:
    """Two halves are missing and neither stops the swing. `c.basic` takes
    no hand, so the basic attack is swung with whatever the creature's
    basic is; and nothing in the world records that both weapons landed
    under one power -- the property beside this one counts it in a closure
    a separate row cannot read -- so the printed Trigger is unenforced."""
    c.basic()


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
       on=Trigger(Hit, _my_melee_hit, "you hit with a melee attack"))
def i804p1(c: Cast) -> None:
    """"Against the next attack that hits it before the end of your next
    turn" is both ends: the `When` is the outer limit and the inner one is
    the first blow that gets through. `DamageApplied` is announced after
    resistance and vulnerability have both been counted, so tearing the
    effect down there spends it on exactly one attack."""
    foe = _foe(c)
    if foe is None:
        return
    weak = c.vulnerable(5, on=foe, until=When.EONT)
    if weak is None:
        return

    def struck(ev: DamageApplied) -> None:
        if ev.target == foe:
            c.end_effect(weak, on=foe, why="spent on the next attack")

    c.watch(DamageApplied, struck, until=When.EONT, on=foe)


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
       reach=PERSONAL, target=SELF, dropped=("c.ability_check()",))
def i791p1(c: Cast) -> None:
    """"Use your Intelligence, Wisdom, or Charisma modifier in place of
    your Strength modifier" is the difference between the two added to the
    roll. The *attack* context carries the ref and the header says which
    ability that row rolls, so the swap lands on a Strength attack and
    nothing else, and `once=True` spends it on one roll as printed.

    A Strength check and a Strength-based skill check are the dropped
    half: `c.check` takes a skill and no ability to roll it with."""
    delta = max(c.int_mod, c.wis_mod, c.cha_mod) - c.str_mod
    if delta <= 0:
        return

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return (
            p is not None and p.attack is not None and p.attack.ability is STR
        )

    c.bonus("attack", delta, on=c.me, until=When.EONT, once=True, when=gate)


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
       reach=PERSONAL, target=SELF, )
def i1125x1(c: Cast) -> None:
    """A shield that is also a pick: +2 proficiency, 1d6, high crit, off-hand.

    The profile is on the card and hand-written here, because there is no
    `weapon` row for a shield -- it is an item. `c.as_weapon` puts it in
    `Gear.weapons` so everything that asks what is in hand finds it, and it
    carries the shield's own enhancement, which is the printed "+2
    enhancement bonus to attack rolls and damage rolls when used as a
    weapon".

    On the belt rather than in hand: it is a second weapon the character
    may take up, and arriving held would silently disarm the main hand.
    """
    c.as_weapon(damage="1d6", group="pick", proficiency=2,
                properties=frozenset({"high crit", "off-hand"}))
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
       reach=PERSONAL, target=SELF)
def i2141x1(c: Cast) -> None:
    """The damage hangs on `RelationSet` and not on `ConditionApplied`:
    `Relations._apply_condition` writes the condition straight onto the
    component, so a grab is never announced as one and the watch this
    row had was silently dead."""
    c.bonus("escape", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    me = c.me

    def seized(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != me:
            return
        c.damage("1d10", on=ev.source)

    c.watch(RelationSet, seized, until=When.ENCOUNTER, on=me)


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
       reach=PERSONAL, target=SELF)
def i2053x1(c: Cast) -> None:
    """The card pays the *partner*, so the pair has to be named --
    `query.flanked_by` answers "flanked by anybody", which would pay an
    ally standing somewhere else. `_flank_pair` is the same test with the
    mate fixed.

    Laid on everyone on the wearer's side and gated at read time, because
    who is flanking whom changes every round."""

    def gate_for(mate: int):  # noqa: ANN202
        def gate(_ctx: dict[str, Any]) -> bool:
            return any(
                _flank_pair(c.world, c.me, mate, foe) for foe in c.enemies()
            )

        return gate

    for ally in c.allies():
        gate = gate_for(ally)
        c.bonus(AC, 1, on=ally, until=When.ENCOUNTER, kind="shield", when=gate)
        c.bonus(REF, 1, on=ally, until=When.ENCOUNTER, kind="shield", when=gate)


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
       reach=PERSONAL, target=SELF,
       trigger="a critical hit would be scored against you",
       on=Trigger(Hit, _crit_on_me, "a critical hit lands on you"))
def i3101p1(c: Cast) -> None:
    """"The attack becomes a normal hit." Both the announcement and the
    live `AttackResult` are written down: `c.damage` maximises its dice
    off `result.critical`, and every crit rider in the tree reads
    `Hit.critical`. `result.hit` is left alone -- it is still a hit, and
    `resolve.attack`'s `confirm` would cancel the event if it were not.

    Written here rather than as a verb because the interrupt window on
    `Hit` runs after `resolve` has recomputed both from the die, so
    nothing recomputes them again afterwards."""
    ev = c.trigger
    if ev is None:
        return
    ev.critical = False
    result = getattr(ev, "result", None)
    if result is not None:
        result.critical = False


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


def _vs_ranged(ctx: dict[str, Any]) -> bool:
    """"Against ranged attacks" -- and only those.

    A **close or area** attack is not a ranged one: the card narrows to the
    `Ranged` line and those are separate reach kinds. Read off the attacking
    row, because `concealment_of` is handed the real attack context and
    `ctx["power"]` is the row that is swinging.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach is not None and p.reach.kind == "ranged"


@power("i3212p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=SELF)
def i3212p1(c: Cast) -> None:
    """Concealment is a modifier the creature carries, and `c.grants_in`
    lays one for as long as a creature stands in the aura.

    **The gate was the whole marker and it arrived**, so the concealment no
    longer covers melee as well: `concealment_of` reads `mods.total` with the
    real attack context, so `ctx["power"]` says what is swinging and
    `_vs_ranged` is the card's own narrowing.

    "Or until you move" is the aura's other end, and `c.dispel` on the
    wearer's first `Moved` is it."""
    aura = c.aura(1, label=c.ref, until=When.ENCOUNTER, on=c.me)
    if not aura:
        return
    c.grants_in(aura, "concealment", 2, side="any", when=_vs_ranged)

    def walked(ev: Moved) -> None:
        if ev.actor == c.me:
            c.dispel(aura)

    c.watch(Moved, walked, until=When.ENCOUNTER, on=c.me)


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
       reach=PERSONAL, target=SELF)
def i1082p1(c: Cast) -> None:
    """"Since the end of your last turn" is read off the bus's own log,
    which keeps every event in order: walk it backwards to the wearer's
    last `TurnEnd` and collect what hurt them after it. Untyped damage is
    not a type anything can resist, so it is left out of the offer."""
    seen: list[DamageType] = []
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnEnd) and ev.actor == c.me:
            break
        if not isinstance(ev, DamageApplied) or ev.target != c.me:
            continue
        for dtype in ev.dtypes or ((ev.dtype,) if ev.dtype else ()):
            if dtype is not DamageType.UNTYPED and dtype not in seen:
                seen.append(dtype)
    pick = c.choose(seen, "which damage type is resisted")
    if pick is not None:
        c.resist(10, pick, on=c.me, until=When.ENCOUNTER)


@power("i1682x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=CloseBurst(1), target=SELF)
def i1682x1(c: Cast) -> None:
    """What provoked the opening *is* recorded: `dsl._survive_provoking`
    stamps the window's `why` with the ref and the words "ranged power".
    Watched in the BEFORE window, the way `c.no_provoke` is, so the bonus
    is standing before the swing it answers -- laid on the ally who
    provoked and gated on `opportunity`, so it covers that opening and no
    other."""

    def opened(ev: OpportunityWindow) -> None:
        ally = ev.provoker
        if "ranged power" not in ev.why or not _friend(c.world, c.me, ally):
            return
        if query.distance_between(c.world, c.me, ally) > 1:
            return
        c.bonus(AC, 2, on=ally, until=When.EOT, kind="shield",
                when=_opportunity)
        c.bonus(REF, 2, on=ally, until=When.EOT, kind="shield",
                when=_opportunity)

    c.watch(OpportunityWindow, opened, until=When.ENCOUNTER, on=c.me,
            window=Window.BEFORE)


@power("i1682p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=NO_TARGET,
       trigger="an ally adjacent to you provokes an opportunity attack by "
               "using a ranged or area power",
       on=Trigger(OpportunityWindow, _ally_provokes_ranged,
                  "an adjacent ally provokes by shooting"))
def i1682p1(c: Cast) -> None:
    """"The opportunity attack targets you instead": the window is refused
    and reopened against the wearer. `c.redirect` is the wrong door -- the
    attack has not been declared yet, so there is no `target` on the event
    for it to move."""
    ev = c.trigger
    foe = getattr(ev, "actor", None)
    if foe is None:
        return
    c.cancel()
    c.provoke(foe, on=c.me, why=getattr(ev, "why", "") or c.ref)


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
       reach=PERSONAL, target=SELF)
def i2483x1(c: Cast) -> None:
    """"While you are flanked" is `query.flanked_by` asked of each enemy,
    at read time rather than at arming time. A plain "+1 bonus" with no
    type word in front of it is untyped, so there is no `kind=`."""

    def gate(_ctx: dict[str, Any]) -> bool:
        return any(query.flanked_by(c.world, c.me, foe) for foe in c.enemies())

    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER, when=gate)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER, when=gate)


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
       reach=PERSONAL, target=SELF)
def i3402x1(c: Cast) -> None:
    """Three of the four named effects are conditions the hold carries;
    charm is a keyword of the row that laid it, which the save context
    now carries.

    The penalty goes straight onto `Health.max_hp`, which is a plain
    field. Nothing else in the game lowers a maximum, so there is no verb
    -- and the two things that follow from it, the bloodied line and what
    a healing surge is worth, are both computed from it."""
    health = c.world.get(c.me, Health)
    if health is not None and c.me not in c.suffering(c.ref, include_self=True):
        # Guarded, because this one writes rather than laying a modifier:
        # a trait that armed twice would take ten off and keep going.
        c.effect(c.ref, until=When.ENCOUNTER, on=c.me)
        health.max_hp = max(1, health.max_hp - 5)
        health.hp = min(health.hp, health.max_hp)
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
       reach=PERSONAL, target=SELF)
def i714p1(c: Cast) -> None:
    """"Whichever comes first" is both halves: the encounter is the `When`
    and `_while_bloodied` is the other one."""
    if c.bloodied(on=c.me):
        _while_bloodied(c, c.me, c.resist(2, on=c.me, until=When.ENCOUNTER))


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
                  "an attack is aimed at an adjacent ally"))
def i1487p1(c: Cast) -> None:
    """The blow is moved with `c.redirect`. "Half the damage dealt by the
    attack" cannot be read where the interrupt runs -- nothing has been
    rolled yet -- so the resistance is laid by the `DamageApplied` that
    follows, which is the first moment the number exists. "(if any)" is
    the card allowing for a miss, which is the `once=` watch simply never
    firing."""
    if not c.redirect(to=c.me):
        return

    def landed(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.amount > 0:
            c.resist(ev.amount // 2, on=c.me, until=When.SONT)

    c.watch(DamageApplied, landed, until=When.EOT, on=c.me, once=True)


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
       reach=PERSONAL, target=SELF)
def i713p1(c: Cast) -> None:
    """The same two-ended duration as i714p1, on a damage bonus rather
    than a resistance."""
    if c.bloodied(on=c.me):
        _while_bloodied(c, c.me, c.bonus(
            "damage", 5, on=c.me, until=When.ENCOUNTER, kind="power",
            when=_reach_is("melee")))


@power("i730p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, _damage_on_me, "you are damaged"))
def i730p1(c: Cast) -> None:
    c.temp_hp(10 if c.spend_points(1) else 5, on=c.me)
    c.shift(1)
