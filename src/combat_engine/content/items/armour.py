"""Armour-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares a suit of armour. The ladder, the enhancement bonus,
the price and the base-item restriction are columns in `game.db`, and the
enhancement reaches the defence as a `Mod` laid by `engine/equipment.py` --
so an item whose whole printed content is "+N AC" has no block at all.

Three judgements run through the file.

* **`kind="enhancement"` is spoken for on AC.** `equipment._defence_mods`
  writes the armour's own plus as an `enhancement` mod, and two of a kind
  do not stack, so a second one here would silently eat the armour. Every
  AC bonus below is `item`, `power` or untyped, as the card prints it.
* **The damage context carries `target`, `power`, `opportunity`, `charge`,
  `dtype` and `crit` -- and no attacker.** `Cast.resist`'s docstring
  promises `source`; `resolve.deal_damage` does not build it. So "resist 5
  against damage from swarms" and "resistance against attacks by your oath
  target" cannot be gated and are marked, not approximated.
* **The saving-throw context is `actor`, `effect`, `label`, `conditions`,
  `ongoing`, `dtype` and `keywords`.** That is enough for "against ongoing
  necrotic damage" (the effect carries its burn), for "against effects that
  daze, dominate or stun" (it carries its conditions) and now for "against
  fear effects" too: `durations.keywords_of` reads the keywords back off
  the label, which is the ref of the row that laid the hold.

One verb the slot keeps asking for and that does not exist: `c.escape()`.
An escape attempt is not modelled at all -- no action, no check -- and
six blocks print a bonus to one. "The ongoing damage ends", which used
to be marked beside it, is `_burn_on` plus `c.end_effect`: the burn lives
on the hold, so having the hold is having the number and the way to end
it.

Death saves are rolled in `turns._death_saves` with `bonus=0`, so a
standing `c.bonus("save", ...)` never reaches them; the three blocks that
print one ride the `SavingThrow` read-back instead. The same read-back is
how the two blocks that bargain over a *later* throw are written -- the
throw is announced before it is acted on, so its answer can be changed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.content.powers.avenger.oath import oath_target
from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    EffectApplied,
    Healed,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    MoveStart,
    OpportunityWindow,
    PowerResolved,
    Powers,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    SurgeSpent,
    TempHP,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    World,
    about_me,
    both,
    by_charge,
    by_me,
    by_melee,
    by_ranged,
    get,
    power,
    query,
    targets_me,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.events import Bloodied, Event, ForcedMove
from combat_engine.engine.zones import Zone

ITEM = "item"

_ALL_DEFENCES = (AC, FORT, REF, WILL)

_RESIST_LIST = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.PSYCHIC,
    DamageType.THUNDER,
)


def _defences(c: Cast, value: int, **kw: Any) -> None:
    """"A bonus to all defences" is four modifiers; there is no key for
    the set, and writing one would not be read by `query.defence`."""
    for d in _ALL_DEFENCES:
        c.bonus(d, value, **kw)


def _foe(c: Cast) -> int | None:
    """The other creature in the event this row is answering.

    `Triggers._at` aims a single-target enemy row at `ev.attacker`, which
    is the wrong creature for half the shapes in this slot -- a row
    answering your own `Dropped` has no attacker at all. Reading the event
    is the only thing that is right every time.
    """
    ev = c.trigger
    for name in ("attacker", "source", "actor"):
        who = getattr(ev, name, None)
        if who is not None and who != c.me:
            return who
    return c.target


def _auto_save(c: Cast, *words: str) -> None:
    """"You automatically succeed on saving throws against X."

    `c.unsave` says the opposite line and nothing says this one, but
    `SavingThrow` is a `Decision` that `Effects.save` reads back, and its
    `against` is `str(effect)` -- which spells out "ongoing N <type>".
    """

    def rider(ev: SavingThrow) -> None:
        if ev.actor != c.me or not all(w in ev.against for w in words):
            return
        ev.saved = True

    c.watch(SavingThrow, rider, until=When.ENCOUNTER, on=c.me)


def _death_save(c: Cast, value: int, *, per_failure: int = 0) -> None:
    """A standing bonus to death saving throws.

    `turns._death_saves` rolls with `bonus=0` and consults no modifier, so
    `c.bonus("save", ...)` cannot reach it. It does announce the throw and
    read the answer back, which is where this goes. The failures are
    counted here rather than read off `Health`, so the count is per-fight
    the way the card says.
    """
    failed = [0]

    def rider(ev: SavingThrow) -> None:
        if ev.actor != c.me or ev.against != "death":
            return
        ev.bonus += value + per_failure * failed[0]
        ev.saved = ev.natural + ev.bonus >= 10
        if not ev.saved:
            failed[0] += 1

    c.watch(SavingThrow, rider, until=When.ENCOUNTER, on=c.me)


def _burning(dtype: DamageType | None = None):  # noqa: ANN202
    """Save gate: the effect being saved against carries ongoing damage."""

    def gate(ctx: dict[str, Any]) -> bool:
        burn = getattr(ctx.get("effect"), "ongoing", None)
        return burn is not None and (dtype is None or burn[1] == dtype)

    return gate


def _holding(*conditions: Condition):  # noqa: ANN202
    """Save gate: the effect being saved against imposes one of these."""
    wanted = set(conditions)

    def gate(ctx: dict[str, Any]) -> bool:
        held = getattr(ctx.get("effect"), "conditions", ())
        return bool(wanted & set(held))

    return gate


def _keyworded(*words: Keyword):  # noqa: ANN202
    """Attack or damage gate: the power in the context prints one of these."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and bool(wanted & set(p.keywords))

    return gate


def _from(who: int | None):  # noqa: ANN202
    """Attack gate: this attack is the named creature's."""

    def gate(ctx: dict[str, Any]) -> bool:
        return who is not None and ctx.get("attacker") == who

    return gate


def _against(who: int | None):  # noqa: ANN202
    """Attack or damage gate: this one is aimed at the named creature."""

    def gate(ctx: dict[str, Any]) -> bool:
        return who is not None and ctx.get("target") == who

    return gate


def _enemy(world: World, me: int, who: int | None) -> bool:
    if who is None or who == me:
        return False
    return query.team(world, who) is not query.team(world, me)


def _crit_on_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "critical", False)


def _rolled_on_me(world: World, me: int, ev: Event) -> bool:
    """An attack roll that landed on me. `Hit` carries no `vs`."""
    return getattr(ev, "target", None) == me and getattr(
        ev, "total", 0
    ) >= getattr(ev, "defence", 1)


def _missed_by_me_vs_will(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "attacker", None) == me
        and getattr(ev, "vs", None) == WILL
        and getattr(ev, "total", 0) < getattr(ev, "defence", 1)
    )


def _hit_my_will(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "vs", None) == WILL and _rolled_on_me(world, me, ev)


def _hit_my_ac(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "vs", None) == AC


def _condition_on_me(*conditions: Condition):  # noqa: ANN202
    wanted = set(conditions)

    def check(world: World, me: int, ev: Event) -> bool:
        return (
            getattr(ev, "target", None) == me
            and getattr(ev, "condition", None) in wanted
        )

    return check


def _adjacent_enemy_moves(*kinds: str):  # noqa: ANN202
    """An enemy standing next to me starts a move of one of these kinds.

    `MoveStart`, not `MoveEnd`: by the end of a shift the enemy is no
    longer adjacent, which is precisely when the row should have fired.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", None)
        if not _enemy(world, me, who):
            return False
        if kinds and getattr(ev, "kind_", "") not in kinds:
            return False
        return query.distance_between(world, me, who) <= 1

    return check


def _ally_beside_me_attacked(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "target", None)
    if foe is None or foe == me:
        return False
    if query.team(world, foe) is not query.team(world, me):
        return False
    return query.distance_between(world, me, foe) <= 1


def _my_power_with(*words: Keyword, other_than: str = ""):  # noqa: ANN202
    """One of my powers printing one of these keywords.

    `other_than` keeps a row off its own trigger. A healing row answering
    "you use a healing power" prints the keyword itself, so `PowerUsed`
    from its own use re-offered it and the dispatcher recursed until the
    stack ran out.
    """
    wanted = set(words)

    def check(world: World, me: int, ev: Event) -> bool:
        if getattr(ev, "actor", getattr(ev, "attacker", None)) != me:
            return False
        ref = getattr(ev, "power", "") or ""
        if other_than and ref == other_than:
            return False
        p = get(ref)
        return p is not None and bool(wanted & set(p.keywords))

    return check


def _typed_damage_on_me(*types: DamageType):  # noqa: ANN202
    wanted = set(types)

    def check(world: World, me: int, ev: Event) -> bool:
        return getattr(ev, "target", None) == me and (
            getattr(ev, "dtype", None) in wanted if wanted else True
        )

    return check


def _ally_hits(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    return query.team(world, who) is query.team(world, me)


def _save_ends_on_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "save_ends", False)


def _fear_save_ends_on_me(world: World, me: int, ev: Event) -> bool:
    """A save-ends hold laid on me by a row printing the fear keyword.
    `EffectApplied.label` is that row's ref, which is what `keywords_of`
    reads."""
    return _save_ends_on_me(world, me, ev) and Keyword.FEAR in keywords_of(
        getattr(ev, "label", "") or ""
    )


def _save_keywords(*words: Keyword) -> Any:
    """Save gate: the row that laid the hold printed one of these words.
    The saving-throw context carries them via `durations.keywords_of`."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("keywords", ())))

    return gate


def _forced_on_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", getattr(ev, "actor", None))
    return who == me


def _opportunity_on_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(
        ev, "opportunity", False
    )


def _my_death_save(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "against", "") == "death"


def _spikes(c: Cast, dice: str, bonus: int, dtype: DamageType, until: When) -> None:
    """"Any creature that hits you with a melee attack takes ..." -- six
    blocks, all the same watch."""

    def sting(ev: Hit) -> None:
        if ev.target != c.me or not by_melee(c.world, c.me, ev):
            return
        c.damage(dice, bonus, dtype=dtype, on=ev.attacker)

    c.watch(Hit, sting, until=until, on=c.me)


def _channel_divinity(world: World, me: int, ev: Event) -> bool:
    """"You use a Channel Divinity power."

    `Keyword` has no member for it and gating on `Keyword.DIVINE` would
    fire on every cleric at-will. What the four class features share is
    the `group=` that makes them one use an encounter, which is the same
    fact the printed line names.
    """
    if getattr(ev, "actor", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.group == CHANNEL_DIVINITY


def _in_beast_form(c: Cast):  # noqa: ANN202
    """Gate: the wearer is wearing a shape. The printed Beast Form keyword
    is written as `in_beast_form` everywhere else in the tree."""
    return lambda ctx: in_beast_form(c.world, c.me)


def _burn_on(world: World, me: int, dtype: DamageType | None = None) -> Effect | None:
    """The live hold carrying ongoing damage, of one type or any.

    `EffectApplied` names a label and a duration and not the burn, and
    `c.save` rolls where the card does not. The number and the way to end
    it are both on the hold, so the rows that print "the ongoing damage
    ends" want the hold itself.
    """
    for eff in sorted(world.effects.of(me), key=lambda e: e.id):
        if eff.ended or not eff.ongoing:
            continue
        types = set(eff.ongoing_types or (eff.ongoing[1],))
        if dtype is None or dtype in types:
            return eff
    return None


def _gains_burn(dtype: DamageType | None = None):  # noqa: ANN202
    """Trigger: a hold carrying ongoing damage has just landed on me.
    Read off the creature, because the event does not carry it."""

    def check(world: World, me: int, ev: Event) -> bool:
        return (
            getattr(ev, "target", None) == me
            and _burn_on(world, me, dtype) is not None
        )

    return check


def _enemy_attacks_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and _enemy(
        world, me, getattr(ev, "attacker", None)
    )


def _erode(c: Cast, held: Effect | None, event: type, when) -> None:  # noqa: ANN001
    """A bonus that comes down by 1 each time something happens, and ends
    at 0.

    The live `Mod` is mutated rather than relaid: two bonuses of a kind do
    not stack and the larger wins, so a fresh smaller one would be ignored
    in favour of the one it was meant to replace -- which is a bonus that
    never wears off at all.
    """
    if held is None:
        return

    def wear(ev: Event) -> None:
        if held.ended or not when(c.world, c.me, ev):
            return
        # `Effect.mods` is a list of `(holder, Mod)`, not of modifiers.
        for _holder, mod in held.mods:
            mod.value -= 1
        if all(mod.value <= 0 for _holder, mod in held.mods):
            c.end_effect(held)

    c.watch(event, wear, until=When.ENCOUNTER, on=c.me)


def _no_provoke_for_attacks(c: Cast) -> None:
    """"Your ranged and area attacks do not provoke opportunity attacks."

    `c.no_provoke` shuts every window this creature opens, walking away
    included, which is a wider rule than the card prints. The window a
    ranged or area power opens is `dsl._survive_provoking`'s, and it says
    so in `why` -- so the narrow sentence is that one window and no other.
    """

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker == c.me and str(ev.why).endswith("is a ranged power"):
            ev.cancel("this armour's ranged attacks do not provoke")

    c.watch(
        OpportunityWindow, veto, until=When.ENCOUNTER, on=c.me,
        window=Window.BEFORE,
    )


# -- level 2 ----------------------------------------------------------------


def _arcane_power(ctx: dict[str, Any]) -> bool:
    """"With arcane attack powers": read off the row the context names."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.ARCANE in p.keywords


@power("i1044x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1044x1(c: Cast) -> None:
    """The save half reads the effect out of the context rather than its
    label: `c.ongoing` labels a burn "ongoing N" with no type in it."""
    c.resist(5, DamageType.NECROTIC)
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_burning(DamageType.NECROTIC))


@power("i1147x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1147x1(c: Cast) -> None:
    c.bonus("skill:endurance", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i1147p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i1147p1(c: Cast) -> None:
    """"As if you had spent a surge", so no surge leaves the pool."""
    c.heal(c.surge_value(), on=c.me)


@power("i1198x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def i1198x1(c: Cast) -> None:
    """An escape attempt is not a thing the engine has: no action, no
    check, nothing to hang a bonus on."""


@power("i1198p1", level=2, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you are immobilized by an attack",
       on=Trigger(ConditionApplied, _condition_on_me(Condition.IMMOBILIZED),
                  "you are immobilized"))
def i1198p1(c: Cast) -> None:
    """Augment 1 buys half your speed instead of the printed square."""
    c.cure(Condition.IMMOBILIZED, on=c.me)
    c.shift(c.speed_of() // 2 if c.spend_points(1) else 1)


@power("i1212p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you use a channel divinity power",
       on=Trigger(PowerUsed, _channel_divinity,
                  "you use a channel divinity power"))
def i1212p1(c: Cast) -> None:
    """"A bonus to AC", with no type word, so it is untyped. The four
    class features the card names are one `group=` -- see
    `_channel_divinity`."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER)
    c.heal(5, on=c.me)


@power("i1423p1", level=2, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def i1423p1(c: Cast) -> None:
    c.conceal(on=c.me, until=When.EONT)
    if c.spend_points(1):
        c.restore_use(c.ref)


@power("i1513x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1513x1(c: Cast) -> None:
    """A death save takes no modifier -- see `_death_save`."""
    _death_save(c, 2, per_failure=1)


@power("i1552x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1552x1(c: Cast) -> None:
    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me:
            return
        _defences(c, 2, on=c.me, until=When.EONT)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=c.me)


@power("i1552p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, about_me, "you spend an action point"))
def i1552p1(c: Cast) -> None:
    """Forgoing the property's bonus is `c.end_effect` against i1552x1's
    label, and it is done twice: both rows answer the same
    `ActionPointSpent` and nothing fixes which of the two the dispatcher
    reaches first, so the bonuses are taken off if they are already there
    and taken off again as they land."""
    def forgo() -> None:
        while c.end_effect(on=c.me, against="i1552x1") is not None:
            pass

    forgo()

    def landed(ev: EffectApplied) -> None:
        if ev.target == c.me and ev.label.startswith("i1552x1"):
            forgo()

    c.watch(EffectApplied, landed, until=When.EOT, on=c.me)
    mate = next(iter(c.within(5, side="ally")), None)
    if mate is not None:
        c.second_wind(on=mate)


@power("i1569p1", level=2, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy reduces you to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you are dropped"))
def i1569p1(c: Cast) -> None:
    """"A bonus", with no type word, so both are untyped."""
    foe = _foe(c)
    if foe is None:
        return
    c.bonus("attack", c.enhancement, on=c.me, until=When.EOT)
    c.bonus("damage", c.enhancement, on=c.me, until=When.EOT)
    c.basic(on=foe)


@power("i1586x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1586x1(c: Cast) -> None:
    """A defence bonus takes a `when=`, so the shape is asked at the roll
    rather than once when the fight starts -- which is what a property
    that turns on a shape assumed later needs."""
    c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_in_beast_form(c))


@power("i1586p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, requires=in_beast_form)
def i1586p1(c: Cast) -> None:
    """The printed Beast Form keyword is a Requirement -- that is what the
    keyword means -- so the interface refuses the row out of shape rather
    than the body quietly doing nothing."""
    c.shift(2)


@power("i1600x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1600x1(c: Cast) -> None:
    _auto_save(c, "ongoing", "poison")


@power("i1600p1", level=2, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you gain ongoing poison damage",
       on=Trigger(EffectApplied, _gains_burn(DamageType.POISON),
                  "you gain ongoing poison damage"))
def i1600p1(c: Cast) -> None:
    """Ending the burn is ending the hold that carries it. The predicate
    reads the hold off the creature rather than off `EffectApplied`, which
    announces a label and a duration and not the number."""
    c.end_effect(_burn_on(c.world, c.me, DamageType.POISON))


@power("i1617x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1617x1(c: Cast) -> None:
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


@power("i1765p1", level=2, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you"))
def i1765p1(c: Cast) -> None:
    foe = _foe(c)
    vacated = c.here
    c.shift(1)
    if foe is not None:
        c.slide(1, on=foe, to=vacated)


@power("i1808p1", level=2, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1808p1(c: Cast) -> None:
    c.penalty(AC, 1, on=c.me, until=When.EONT)
    for mate in c.within(1, side="ally"):
        c.bonus(AC, 1, on=mate, until=When.EONT, kind="power")


@power("i1808p2", level=2, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an adjacent ally is attacked",
       on=Trigger(AttackDeclared, _ally_beside_me_attacked,
                  "an adjacent ally is attacked"))
def i1808p2(c: Cast) -> None:
    mate = getattr(c.trigger, "target", None)
    c.penalty(AC, c.enhancement, on=c.me, until=When.EONT)
    if mate is not None:
        c.bonus(AC, c.enhancement, on=mate, until=When.EONT, kind="power")


@power("i1859x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1859x1(c: Cast) -> None:
    held = _holding(Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.points() >= 1 and held(ctx))


@power("i1872x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.armour_penalty(world, eid)",))
def i1872x1(c: Cast) -> None:
    """Armour imposes no check or speed penalty in the first place, so
    there is nothing for this to cancel."""


@power("i2137x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.resist_from()", "c.move_through()"))
def i2137x1(c: Cast) -> None:
    """All three clauses turn on who is dealing the damage or whose square
    is being crossed, and the damage context carries neither."""


@power("i2140x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2140x1(c: Cast) -> None:
    def spike(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return
        if not by_melee(c.world, c.me, ev):
            return
        c.damage("1d10", c.dex_mod, on=ev.attacker)

    c.watch(Hit, spike, until=When.ENCOUNTER, on=c.me)


@power("i2170p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2170p1(c: Cast) -> None:
    """The printed reaction is folded into the hold: the push is not a
    separate row, so there is nothing for a policy to be offered."""

    def stepped(ev: MoveEnd) -> None:
        who = getattr(ev, "actor", None)
        if not _enemy(c.world, c.me, who) or not c.adjacent(who):
            return
        c.push(1, on=who)

    c.watch(MoveEnd, stepped, until=When.ENCOUNTER, on=c.me)


@power("i2281x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2281x1(c: Cast) -> None:
    c.immune(Condition.BLINDED, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:perception", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2285p1", level=2, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.RADIANT],
       out_of_combat=True)
def i2285p1(c: Cast) -> None:
    """Light, and nothing else."""


@power("i2285p2", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(2), target=EACH_ENEMY, keywords=[Keyword.RADIANT],
       attack=Attack(INT, vs=WILL))
def i2285p2(c: Cast) -> None:
    """"Intelligence or Charisma" is one attack line with two abilities and
    the header holds one, so Intelligence is written and the difference to
    Charisma goes to `c.strike(plus=)` when Charisma is the better. `c.int_`
    and `c.cha_` are whole attack bonuses, so their difference is exactly
    what swapping the ability is worth. The printed enhancement bonus to
    the roll is the armour's own plus, laid on the attack rather than on
    AC, so `kind="enhancement"` is free here."""
    if c.first:
        c.bonus("attack", c.enhancement, on=c.me, until=When.EOT,
                kind="enhancement")
    if c.strike(plus=max(0, c.cha_ - c.int_)):
        c.dazed(until=When.SAVE_ENDS)


@power("i2397x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2397x1(c: Cast) -> None:
    c.bonus("skill:intimidate", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2397p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=EACH_ENEMY)
def i2397p1(c: Cast) -> None:
    c.push(1)


@power("i2417x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2417x1(c: Cast) -> None:
    c.bonus("skill:intimidate", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2417p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.FEAR])
def i2417p1(c: Cast) -> None:
    c.penalty("attack", 2, until=When.EONT)


@power("i2441x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.stealth_speed()",))
def i2441x1(c: Cast) -> None:
    """Moving fast while hidden costs a Stealth penalty that is not
    modelled, so there is no penalty to lift."""


@power("i2534x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def i2534x1(c: Cast) -> None:
    """An escape action is not modelled, so a bonus to one has no roll."""


@power("i2986x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2986x1(c: Cast) -> None:
    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != c.me:
            return
        c.bonus("attack", 1, on=c.me, until=When.EONT, kind="item")
        _defences(c, 1, on=c.me, until=When.EONT, kind="item")

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=c.me)


@power("i2992x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2992x1(c: Cast) -> None:
    c.bonus(FORT, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


@power("i3040x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3040x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so the whole line is one
    gate -- the companion is asked each time rather than at arming."""
    c.bonus(AC, 4, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: bool(ctx.get("opportunity"))
            and c.companion() is not None)


@power("i3117x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def i3117x1(c: Cast) -> None:
    """The second clause -- the armour cannot be taken off -- is not a
    combat effect; the first has no escape attempt to modify."""


@power("i3130p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3130p1(c: Cast) -> None:
    """Producing a torch or a rope is shopping, not a fight."""


@power("i462x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i462x1(c: Cast) -> None:
    c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


@power("i531p1", level=2, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a creature you have marked targets you and an ally",
       on=Trigger(DamageRolled, targets_me, "a marked enemy hits you"),
       dropped=("c.aegis()",))
def i531p1(c: Cast) -> None:
    """The mark is asked in the body because the predicate gets no `Cast`.
    Two clauses go unsaid and both are named: the mark has to be a
    particular class feature's, and the attack has to catch an ally too --
    the damage event is per-target and knows nothing of the rest."""
    foe = _foe(c)
    if foe is None or not c.marked(on=foe):
        return
    c.reduce(5 + c.enhancement, c.trigger)


@power("i537p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i537p1(c: Cast) -> None:
    c.second_wind(on=c.me)
    c.heal(sum(c.roll("1d6") for _ in range(max(1, c.enhancement))), on=c.me)


@power("i541x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i541x1(c: Cast) -> None:
    c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i541p1", level=2, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy targets you while you grant it combat advantage",
       on=Trigger(AttackDeclared, targets_me, "an enemy attacks you"))
def i541p1(c: Cast) -> None:
    """"For this attack" is a gate on the attacker rather than a duration:
    the hold runs to the end of the turn and only answers that enemy."""
    c.no_advantage(on=c.me, until=When.EOT, when=_from(_foe(c)))


@power("i544x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i544x1(c: Cast) -> None:
    """"Chosen when the armour is created" is a build-time choice the
    engine has no column for, so it is asked once at arming."""
    dtype = c.choose(list(_RESIST_LIST), "the damage type this armour turns")
    if dtype is not None:
        c.resist(5, dtype)


@power("i561x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i561x1(c: Cast) -> None:
    """A property, so the rider is a watch rather than a declared trigger
    -- the row has standing content and a printed occasion both, and a
    declared trigger would keep the body from ever laying the modifiers."""

    def channelled(ev: PowerUsed) -> None:
        if not _channel_divinity(c.world, c.me, ev):
            return
        for d in (AC, FORT):
            c.bonus(d, 2, on=c.me, until=When.EONT, kind="item")

    c.watch(PowerUsed, channelled, until=When.ENCOUNTER, on=c.me)


@power("i579x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i579x1(c: Cast) -> None:
    """"A +1 bonus" with no type word, so untyped."""
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(on=c.me))


@power("i579p1", level=2, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you are surprised",
       on=Trigger(ConditionApplied, _condition_on_me(Condition.SURPRISED),
                  "you are surprised"))
def i579p1(c: Cast) -> None:
    c.cure(Condition.SURPRISED, on=c.me)


@power("i960p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i960p1(c: Cast) -> None:
    """"Does not end an existing grab" is what `c.immune` already does --
    it bars the condition landing and touches nothing standing."""
    c.no_provoke(on=c.me, until=When.EONT)
    c.immune(Condition.GRABBED, on=c.me, until=When.EONT)


# -- level 3 ----------------------------------------------------------------


@power("i1001p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, trigger="an enemy hits you",
       on=Trigger(Hit, targets_me, "an enemy hits you"))
def i1001p1(c: Cast) -> None:
    """`Effect.escalate` is the *failed* save, and this pays on the
    successful one -- which `SavingThrow` announces before it is acted on,
    with `against` spelling out the hold, label and all. Latched, because
    the weaker penalty wears the same label and would otherwise breed a
    third and a fourth."""
    foe = _foe(c)
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)
    again = [False]

    def shrugged(ev: SavingThrow) -> None:
        if ev.actor != foe or not ev.saved or again[0]:
            return
        if c.ref not in ev.against:
            return
        again[0] = True
        c.penalty("attack", 1, on=foe, until=When.SAVE_ENDS)

    c.watch(SavingThrow, shrugged, until=When.ENCOUNTER, on=foe)


@power("i1055p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET, trigger="an enemy hits you",
       on=Trigger(AttackRolled, _rolled_on_me, "an enemy hits you"))
def i1055p1(c: Cast) -> None:
    """Declared on `AttackRolled` rather than `Hit` because the defence
    that was hit is the whole of the effect and only that event says
    which. Augment 1 raises the bonus to +5."""
    hit = getattr(c.trigger, "vs", AC)
    c.bonus(hit, 5 if c.spend_points(1) else 2, on=c.me, until=When.SONT)


@power("i1061p1", level=3, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you roll a saving throw",
       on=Trigger(SavingThrow, about_me, "you roll a saving throw"))
def i1061p1(c: Cast) -> None:
    """"Use the new result" is the read-back `SavingThrow` exists for."""
    ev = c.trigger
    if ev is None:
        return
    ev.bonus += 2
    ev.saved = ev.natural + ev.bonus >= 10


@power("i1103p1", level=3, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy hits you with a melee or a close attack",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you"))
def i1103p1(c: Cast) -> None:
    """`by_melee` counts close attacks, which is the printed pair."""
    c.bonus("damage", c.enhancement, on=c.me, until=When.EONT,
            when=_against(_foe(c)))


@power("i1176x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.teleport_bonus()", "query.armour_penalty(world, eid)"))
def i1176x1(c: Cast) -> None:
    """A teleport's distance is the number the row asks for; nothing adds
    to every one of them."""


@power("i1288x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1288x1(c: Cast) -> None:
    _auto_save(c, "ongoing", "fire")


@power("i1288p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE])
def i1288p1(c: Cast) -> None:
    _spikes(c, "1d8", c.cha_mod, DamageType.FIRE, When.EONT)


@power("i1529x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1529x1(c: Cast) -> None:
    """The save bonus is a gate on the keywords of the row that laid the
    hold; no type word on the card, so untyped.

    The second wind's half is a watcher rather than a declared trigger:
    the save bonus has to be standing from the start of the fight, and a
    triggered row is not armed until it fires."""
    me = c.me
    c.bonus("save", c.enhancement, on=me, until=When.ENCOUNTER,
            when=_save_keywords(Keyword.FEAR))

    def winded(ev: SecondWind) -> None:
        if ev.actor == me:
            c.temp_hp(3 * c.enhancement, on=me)

    c.watch(SecondWind, winded, on=me, until=When.ENCOUNTER)


@power("i1558p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.resist_from()",))
def i1558p1(c: Cast) -> None:
    """Half the marker is gone: `powers.avenger.oath.oath_target` names
    the sworn enemy. What is still missing is the gate -- `resolve` builds
    no `attacker` into the damage context, so "resistance against attacks
    by that one creature" cannot be told from resistance against
    everything, which is strictly stronger than print."""


@power("i1654p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you"))
def i1654p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.damage("1d10" if c.spend_points(2) else "1d6", on=foe)


@power("i1727p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="an enemy scores a critical hit against you",
       on=Trigger(Hit, _crit_on_me, "an enemy crits you"))
def i1727p1(c: Cast) -> None:
    c.surge(on=c.me, bonus=c.enhancement)


@power("i1732x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1732x1(c: Cast) -> None:
    c.resist(5, DamageType.NECROTIC)


@power("i1732p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i1732p1(c: Cast) -> None:
    """"Usable only while bloodied" is asked here rather than as a
    `requires=`, which is a build-time shape. `c.regain_surge(0)` is the
    only reader of how many surges are left."""
    if not c.bloodied(on=c.me):
        return
    c.heal(max(0, 20 - c.regain_surge(0, on=c.me)), on=c.me)


@power("i1848x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1848x1(c: Cast) -> None:
    """A milestone is a thing that happens between fights."""


@power("i1877x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.light_level(world, square)",))
def i1877x1(c: Cast) -> None:
    """Light is not on the board, so "in darkness or dim light" is a gate
    that would be false in every fight."""


@power("i1911x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1911x1(c: Cast) -> None:
    """The resistance stands, and the save bonus is now narrowed to the
    three printed keywords -- `keywords_of` reads them off the ref of the
    row that laid the hold. `c.resist` is the caster's by default."""
    c.resist(5, DamageType.PSYCHIC)
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_keywords(Keyword.CHARM, Keyword.FEAR, Keyword.PSYCHIC))


@power("i2094x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2094x1(c: Cast) -> None:
    """See `i1586x1`: the shape is asked at the roll, not at arming."""
    for d in (FORT, WILL):
        c.bonus(d, 1, on=c.me, until=When.ENCOUNTER, kind="item",
                when=_in_beast_form(c))


@power("i2094p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy adjacent to you shifts",
       on=Trigger(MoveStart, _adjacent_enemy_moves("shift"),
                  "an adjacent enemy shifts"),
       requires=in_beast_form)
def i2094p1(c: Cast) -> None:
    """`MoveStart`, because by the end of a shift the enemy is no longer
    adjacent and the trigger would be false exactly when it matters."""
    foe = _foe(c)
    if foe is None:
        return
    c.bonus("attack", c.enhancement, on=c.me, until=When.EONT,
            when=_against(foe))
    c.bonus("damage", c.enhancement, on=c.me, until=When.EONT,
            when=_against(foe))


@power("i2095x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2095x1(c: Cast) -> None:
    def struck(ev: Hit) -> None:
        if ev.attacker != c.me or not c.is_quarry(on=ev.target):
            return
        _defences(c, 1, on=c.me, until=When.EONT, when=_from(ev.target))

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me)


@power("i2275p1", level=3, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you"))
def i2275p1(c: Cast) -> None:
    c.shift(1)


@power("i2283p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an adjacent enemy makes a melee attack against you",
       on=Trigger(AttackDeclared, both(targets_me, by_melee),
                  "an adjacent enemy swings at you"))
def i2283p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is None:
        return
    c.damage(f"{max(1, c.enhancement)}d6", on=foe)
    c.ongoing(c.enhancement, on=foe)


@power("i2366x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2366x1(c: Cast) -> None:
    """The Arcana half is an item bonus, which the card prints; the damage
    half prints no type word at all, so it is untyped. A watcher rather
    than a declared trigger, because the skill bonus has to be standing
    from the start of the fight."""
    me = c.me
    c.bonus("skill:arcana", c.enhancement, on=me, until=When.ENCOUNTER,
            kind="item")

    def winded(ev: SecondWind) -> None:
        if ev.actor == me:
            c.bonus("damage", c.enhancement, on=me, until=When.EONT,
                    when=_arcane_power)

    c.watch(SecondWind, winded, on=me, until=When.ENCOUNTER)


@power("i2391x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2391x1(c: Cast) -> None:
    """`oath_target` reads the sworn enemy back off the relation the oath
    lays, and who that is changes during the fight -- so the gate is a
    `when=` asked at the roll rather than a creature read once. "A +1
    bonus" prints no type word, so all four are untyped."""

    def sworn_bloodied(ctx: dict[str, Any]) -> bool:
        victim = oath_target(c)
        return victim is not None and c.bloodied(on=victim)

    _defences(c, 1, on=c.me, until=When.ENCOUNTER, when=sworn_bloodied)


@power("i2434p1", level=3, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.move_through()",))
def i2434p1(c: Cast) -> None:
    """Crossing an occupied square is not something a shift can be told
    to do; the distance is the half that plays."""
    c.shift(3)


@power("i2460p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ILLUSION])
def i2460p1(c: Cast) -> None:
    """See `_erode`. Augment 1 buys the larger starting number, and the
    hold ends itself when it reaches nothing."""
    _erode(
        c,
        c.bonus(AC, 4 if c.spend_points(1) else 2, on=c.me,
                until=When.ENCOUNTER),
        AttackDeclared,
        _enemy_attacks_me,
    )


@power("i2519x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2519x1(c: Cast) -> None:
    c.bonus("skill:bluff", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    c.bonus("skill:diplomacy", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i2519p1", level=3, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy targets you with a melee attack",
       on=Trigger(AttackDeclared, both(targets_me, by_melee),
                  "an enemy swings at you"))
def i2519p1(c: Cast) -> None:
    beside = [w for w in c.within(1) if w != c.me and w != _foe(c)]
    victim = c.choose(beside, "who the attack lands on instead")
    if victim is not None:
        c.redirect(to=victim)


@power("i2582p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i2582p1(c: Cast) -> None:
    """No check is printed. The Effect line is "you escape the grab", flat,
    so the grab is simply lifted -- the marker here was for the escape
    *action*, which this card does not ask anybody to attempt. The
    Requirement is asked in the body because a grab is a condition rather
    than something `requires=` would read."""
    if not c.is_(Condition.GRABBED, on=c.me):
        return
    holder = next((f for f in c.enemies() if c.me in c.grabbing(of=f)), None)
    c.cure(Condition.GRABBED, on=c.me)
    if holder is not None:
        c.damage(f"{max(1, c.enhancement)}d6", on=holder)


@power("i2660x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2660x1(c: Cast) -> None:
    c.bonus("save", c.enhancement, on=c.me, until=When.ENCOUNTER,
            kind="item", when=_burning(DamageType.UNTYPED))


@power("i2660p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i2660p1(c: Cast) -> None:
    c.surge(on=c.me, bonus=c.enhancement)


@power("i2684p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2684p1(c: Cast) -> None:
    c.temp_hp(10 + c.con_mod, on=c.me)


@power("i2688p1", level=3, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2688p1(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


@power("i2754x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2754x1(c: Cast) -> None:
    c.bonus("skill:athletics", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")
    c.bonus("skill:stealth", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i2870x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2870x1(c: Cast) -> None:
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i2870p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i2870p1(c: Cast) -> None:
    """"Against enemies more than 2 squares away" is a gate on the
    attacker, which the attack context does carry."""
    c.conceal(
        on=c.me, until=When.EONT, total=bool(c.spend_points(1)),
        when=lambda ctx: ctx.get("attacker") is not None
        and c.distance(to=ctx["attacker"]) > 2,
    )


@power("i2983p1", level=3, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF,
       todo=("query.armour_penalty(world, eid)",))
def i2983p1(c: Cast) -> None:
    """Trading AC for the armour's penalties is half a bargain: nothing
    charges the penalty, so only the cost would be real."""


@power("i3015p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy hits or misses you with a bull rush or a charge",
       on=(Trigger(Hit, both(targets_me, by_charge), "an enemy charges you"),
           Trigger(Miss, both(targets_me, by_charge),
                   "an enemy charges you")),
       dropped=("c.bull_rush()",))
def i3015p1(c: Cast) -> None:
    """Both halves of "hits or misses" are declared. A bull rush is not an
    attack the engine has."""
    foe = _foe(c)
    if foe is None:
        return
    c.damage(f"{max(1, c.enhancement)}d6", on=foe)
    c.prone(on=foe)


@power("i3042p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with an arcane attack power",
       on=Trigger(Hit, _my_power_with(Keyword.ARCANE, other_than="i3042p1"),
                  "you hit with an arcane power"))
def i3042p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    mate = next(
        (a for a in c.allies() if a != c.me and c.distance(to=a) <= 10
         and query.distance_between(c.world, a, foe) <= 5),
        None,
    )
    if mate is not None:
        c.bonus("attack", c.enhancement, on=mate, until=When.EONT,
                kind="power", when=_against(foe))


@power("i3072x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3072x1(c: Cast) -> None:
    c.resist(5, DamageType.RADIANT)


@power("i3072p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3072p1(c: Cast) -> None:
    """"Change the type" is two operations. `c.resist` files an undo on
    the hold it lays, so ending `i3072x1`'s hold by label puts the radiant
    resistance back where it came from and the new one is laid on top of
    nothing."""
    dtype = c.choose(
        [DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER],
        "what this armour turns instead",
    )
    if dtype is None:
        return
    c.end_effect(on=c.me, against="i3072x1")
    c.resist(5, dtype, until=When.ENCOUNTER)


@power("i3123x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3123x1(c: Cast) -> None:
    """`c.enemies` drops the dead, so the team is compared directly --
    otherwise the creature that just fell is never an enemy."""
    c.resist(3 + 2 * c.enhancement, DamageType.NECROTIC)

    def fell(ev: Dropped) -> None:
        who = getattr(ev, "actor", None)
        if not _enemy(c.world, c.me, who) or c.distance(to=who) > 1:
            return
        c.temp_hp(3 + c.enhancement, on=c.me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me)


@power("i454p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       trigger="an enemy misses you with a melee attack",
       on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you"))
def i454p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.ongoing(5, DamageType.POISON, on=foe)
    c.shift(c.enhancement)


@power("i533x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i533x1(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_burning())


@power("i540x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i540x1(c: Cast) -> None:
    """Storing a power happens during a rest, and the whole property is
    the bookkeeping around it."""


@power("i540p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, todo=("c.stored_row()",))
def i540p1(c: Cast) -> None:
    """There is nowhere to put a borrowed row: `c.grant_row` hands one to
    a creature, not to an object."""


@power("i549x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i549x1(c: Cast) -> None:
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_burning())


@power("i549p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i549p1(c: Cast) -> None:
    """Both halves come off the hold: the number is `Effect.ongoing` and
    ending it is `c.end_effect`. "You can use this power when you are
    taking ongoing damage" is left as a body check rather than a
    `requires=`, because the burn is a hold and not a condition."""
    burn = _burn_on(c.world, c.me)
    if burn is None:
        return
    amount = burn.ongoing[0]
    c.end_effect(burn)
    c.regeneration(amount, until=When.ENCOUNTER, on=c.me)


@power("i664p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a target after a charge",
       on=Trigger(Hit, both(by_me, by_charge), "you hit with a charge"))
def i664p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.bonus("attack", 2, on=c.me, until=When.EOT, kind="power", once=True)
    c.basic(on=foe)


@power("i805p1", level=3, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i805p1(c: Cast) -> None:
    """The wall is the fiction; three squares of sightless teleport is the
    rule, and `c.teleport` already needs no line of sight."""
    c.teleport(3)


# -- level 4 ----------------------------------------------------------------


@power("i1012x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1012x1(c: Cast) -> None:
    """"The first attack made against you" is `once=True`, which spends
    the hold when the blow lands or misses."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="item", once=True)


@power("i1024x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1024x1(c: Cast) -> None:
    """The attack context carries the power, so the printed keywords are
    a gate -- unlike the same sentence written about a saving throw."""
    _defences(c, 2, on=c.me, until=When.ENCOUNTER, kind="item",
              when=_keyworded(Keyword.CHARM, Keyword.FEAR, Keyword.PSYCHIC))


@power("i1024p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=EACH_ENEMY)
def i1024p1(c: Cast) -> None:
    c.penalty("attack", 2, until=When.SAVE_ENDS)


@power("i1111p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET, trigger="another creature grabs you",
       on=Trigger(ConditionApplied, _condition_on_me(Condition.GRABBED),
                  "you are grabbed"),
       dropped=("c.escape()",))
def i1111p1(c: Cast) -> None:
    """The grab goes; the +5 to the escape attempt has no roll to join."""
    foe = _foe(c)
    c.cure(Condition.GRABBED, on=c.me)
    if foe is not None:
        c.flat(5, on=foe)


@power("i1175x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1175x1(c: Cast) -> None:
    c.resist(5, DamageType.PSYCHIC)


@power("i1175p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, trigger="an enemy hits you",
       on=Trigger(Hit, targets_me, "an enemy hits you"))
def i1175p1(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)
    if c.spend_points(1):
        c.phasing(on=c.me, until=When.EONT)


@power("i1181x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.armour_penalty(world, eid)",))
def i1181x1(c: Cast) -> None:
    """Armour costs no speed, so there is no penalty to waive."""


@power("i1181p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1181p1(c: Cast) -> None:
    c.bonus("damage", c.enhancement, on=c.me, until=When.EOT,
            when=_keyworded(Keyword.ARCANE))


@power("i1258p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.PSYCHIC],
       trigger="you use a psychic power",
       on=Trigger(PowerUsed, _my_power_with(Keyword.PSYCHIC, other_than="i1258p1"),
                  "you use a psychic power"))
def i1258p1(c: Cast) -> None:
    spent = c.spend_points(4) or c.spend_points(2)
    dice = "3d6" if spent >= 4 else "2d6" if spent >= 2 else "1d6"
    for who in c.within(1):
        if who == c.me:
            continue
        c.damage(dice, dtype=DamageType.PSYCHIC, on=who)
        c.push(1, on=who)


@power("i1324p1", level=4, cls=ITEM, usage=ENCOUNTER,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       trigger="you are subjected to an effect that a save can end",
       on=Trigger(EffectApplied, _save_ends_on_me, "a save-ends effect lands"))
def i1324p1(c: Cast) -> None:
    """`EffectApplied` rather than `ConditionApplied`: a hold that carries
    only ongoing damage imposes no condition and would never announce."""
    c.save(on=c.me, bonus=c.enhancement if c.spend_points(1) else 0)


@power("i1352x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1352x1(c: Cast) -> None:
    """The live `AttackResult` rides on `Hit` as a plain attribute and
    `Cast.crit` reads the flag back off it, so clearing it in the window
    before the hit is acted on is exactly `c.maximise(critical=True)` run
    backwards. The event's own copy goes too, for anything reading that."""

    def soften(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if result is None or not _crit_on_me(c.world, c.me, ev):
            return
        if c.roll("1d20") >= 16:
            result.critical = False
            ev.critical = False

    c.watch(Hit, soften, until=When.ENCOUNTER, on=c.me, window=Window.BEFORE)


@power("i1366x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1366x1(c: Cast) -> None:
    c.resist(5, DamageType.COLD)


@power("i1366p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.COLD],
       trigger="you are struck by a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "a melee attack hits you"))
def i1366p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is None:
        return
    c.damage(f"{max(1, c.enhancement)}d6", dtype=DamageType.COLD, on=foe)
    c.immobilized(on=foe, until=When.EONT)


@power("i1392x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1392x1(c: Cast) -> None:
    """Attunement is a choice made when the armour is made."""


@power("i1392p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.racial_row()",))
def i1392p1(c: Cast) -> None:
    """`c.grant_row` needs a ref, and which one this is depends on a
    choice the item carries and nothing reads."""


@power("i1674p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def i1674p1(c: Cast) -> None:
    times = 3 if c.spend_points(1) else 2
    for mate in c.within(1, side="ally"):
        c.temp_hp(times * c.enhancement, on=mate)


@power("i1731x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1731x1(c: Cast) -> None:
    """A +1 item bonus on the extra save `cf:warden-f0` rolls, and on no
    other save.

    The feature now comes through as a ref, so both halves of the
    sentence can be asked. "Have the class feature" is `Powers.known`,
    read in the gate rather than at the top: a property that returns
    early lays nothing, and a row that lays nothing is indistinguishable
    from one that was never written.

    "At the start of your turn" is a **window**, not a duration. The
    feature rolls its throw from a `TurnStart` watcher in the ordinary
    `AFTER` window, so this opens the window in `BEFORE` and shuts it
    with a `late=True` subscription in `AFTER` -- which `Bus._run` puts
    behind every ordinary listener of that window. Between those two the
    only saves rolled are the feature's, and the ordinary end-of-turn
    ones are out of reach: `Effects` clocks those off `TurnEnd`.

    Shutting it on `TurnEnd` instead would have been the obvious way and
    would have paid the bonus on any save taken during the warden's own
    turn as well. "Each saving throw" is why the window is not simply
    spent by the first one: the daily beside this property rolls several
    inside it.
    """
    me = c.me
    window = {"open": False}

    def has_font() -> bool:
        known = c.world.get(me, Powers)
        return known is not None and "cf:warden-f0" in known.known

    def opened(ev: TurnStart) -> None:
        window["open"] = ev.actor == me and not ev.ghost and has_font()

    def shut(ev: TurnStart) -> None:
        if ev.actor == me:
            window["open"] = False

    hold = c.watch(TurnStart, opened, until=When.ENCOUNTER,
                   window=Window.BEFORE, on=me, label=c.ref)
    hold.subs.append(
        c.world.bus.on(TurnStart, shut, owner=me, late=True)
    )
    c.bonus("save", 1, on=me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: window["open"] and ctx["actor"] == me)


@power("i1731p1", level=4, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you start your turn",
       on=Trigger(TurnStart, about_me, "you start your turn"))
def i1731p1(c: Cast) -> None:
    """"Against each" is `c.save` once per hold, each named by its own
    label: with no `against` the call takes whichever save-ends hold it
    finds first, so a failed one would be found again and the loop would
    never reach the second. The holds are snapshotted before rolling,
    because a successful save takes one out from under the walk.

    `cf:warden-f0` is a ref with a row behind it, so "and have the class
    feature" is a look in `Powers.known`."""
    known = c.world.get(c.me, Powers)
    if known is None or "cf:warden-f0" not in known.known:
        return
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: e.id):
        if not eff.ended and eff.when is When.SAVE_ENDS:
            c.save(on=c.me, against=eff.label)


@power("i1870p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="a melee or ranged attack hits you",
       on=Trigger(DamageRolled, targets_me, "an attack hits you"))
def i1870p1(c: Cast) -> None:
    """Declared on the damage rather than the hit: `c.halve` works on a
    number that has been rolled and not yet dealt."""
    c.halve(c.trigger)


@power("i2017x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2017x1(c: Cast) -> None:
    """A pool that refills on an extended rest and is spent by the power
    beside it."""


@power("i2017p1", level=4, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.charges()",))
def i2017p1(c: Cast) -> None:
    """An item with a pool of its own is not a thing `Magic` carries."""


@power("i2023x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2023x1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE)
    c.resist(5, DamageType.RADIANT)


@power("i2046x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2046x1(c: Cast) -> None:
    c.resist(5, DamageType.PSYCHIC)


@power("i2046p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=CloseBurst(1), target=EACH_ENEMY, keywords=[Keyword.PSYCHIC],
       trigger="an enemy attack hits your Will",
       on=Trigger(AttackRolled, _hit_my_will, "an attack hits your Will"),
       dropped=("c.augment_area()",))
def i2046p1(c: Cast) -> None:
    """Augment 1 widens the burst, and targets are chosen before the body
    runs -- `c.widen_areas` would arrive a step too late."""
    c.flat(3 + c.enhancement, dtype=DamageType.PSYCHIC)
    c.penalty("attack", 2, until=When.EONT, when=_against(c.me))


@power("i2088p1", level=4, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, charges=True,
       dropped=("c.jump_charge()",))
def i2088p1(c: Cast) -> None:
    """The charge is declared so the engine measures reach the way a
    charge needs; replacing its run with a jump is the missing half."""
    foe = c.target
    if foe is not None:
        c.charge_at(foe)


@power("i2088p2", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.charge_with()",))
def i2088p2(c: Cast) -> None:
    """`c.charge_at` takes a ref but the charge is already resolving by
    the time this row could answer it."""


@power("i2089x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2089x1(c: Cast) -> None:
    """`PowerResolved`, not `PowerUsed`: the announcement comes *before*
    the body runs, so on the earlier event the new shape is not on yet and
    the shift would be taken out of the old one."""

    def changed(ev: PowerResolved) -> None:
        if ev.actor == c.me and ev.power == "p5032":
            c.shift(1)

    c.watch(PowerResolved, changed, until=When.ENCOUNTER, on=c.me)


@power("i2089p1", level=4, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, requires=in_beast_form)
def i2089p1(c: Cast) -> None:
    """"Must end adjacent to an enemy" is the destination, not advice, so
    the square is chosen here rather than left to the decider. With no
    such square reachable the printed move cannot be made at all."""
    beside = [
        sq for sq in c.world.reachable_squares(c.me, 5)
        if any(
            query.distance_between(c.world, c.me, foe) >= 0
            and max(abs(sq[0] - s[0]), abs(sq[1] - s[1])) <= 1
            for foe in c.enemies()
            for s in query.squares(c.world, foe)
        )
    ]
    if not beside:
        return
    c.shift(5, to=c.choose(sorted(beside), "where to land"))


@power("i2151x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2151x1(c: Cast) -> None:
    def struck(ev: Hit) -> None:
        if not _my_power_with(Keyword.DIVINE)(c.world, c.me, ev):
            return
        _defences(c, 1, on=c.me, until=When.EONT, when=_from(ev.target))

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me)


@power("i2158p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, todo=("c.defend_with()",))
def i2158p1(c: Cast) -> None:
    """Answering one defence with another's number is not something
    `query.defence` can be told to do."""


@power("i2162x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2162x1(c: Cast) -> None:
    def hurt(ev: DamageApplied) -> None:
        if ev.target != c.me or not by_melee(c.world, c.me, ev):
            return
        _defences(c, 1, on=c.me, until=When.SONT, kind="item")

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=c.me)


@power("i2277p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.HEALING, Keyword.TELEPORTATION],
       trigger="an attack damages you while you are bloodied",
       on=Trigger(DamageApplied, targets_me, "an attack damages you"))
def i2277p1(c: Cast) -> None:
    if not c.bloodied(on=c.me):
        return
    c.teleport(6)
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


@power("i2380x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2380x1(c: Cast) -> None:
    def mended(ev: Healed) -> None:
        if ev.target != c.me:
            return
        c.bonus(AC, 1, on=c.me, until=When.EONT, kind="item")

    c.watch(Healed, mended, until=When.ENCOUNTER, on=c.me)


@power("i2401x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def i2401x1(c: Cast) -> None:
    """No escape check exists to take the bonus."""


@power("i2401p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an effect dazes, immobilizes, slows or stuns you",
       on=Trigger(ConditionApplied,
                  _condition_on_me(Condition.DAZED, Condition.IMMOBILIZED,
                                   Condition.SLOWED, Condition.STUNNED),
                  "one of those conditions lands on you"))
def i2401p1(c: Cast) -> None:
    c.save(on=c.me)


@power("i2413x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.tremorsense()",))
def i2413x1(c: Cast) -> None:
    """Tremorsense is not a sense the board has."""


@power("i2413p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.POISON],
       attack=Attack(vs=REF, printed=4),
       trigger="an enemy adjacent to you willingly moves",
       on=Trigger(MoveStart, _adjacent_enemy_moves("walk", "shift", "run"),
                  "an adjacent enemy moves"))
def i2413p1(c: Cast) -> None:
    """"Your level + 4" is written as a printed 4: the engine adds the
    level term itself, which is the same arithmetic."""
    if c.strike():
        c.flat(5, dtype=DamageType.POISON)
        c.immobilized(until=When.EONT)


@power("i2431x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2431x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON)


@power("i2431p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy adjacent to you shifts",
       on=Trigger(MoveStart, _adjacent_enemy_moves("shift"),
                  "an adjacent enemy shifts"))
def i2431p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.flat(5 + c.enhancement, on=foe)


@power("i2491x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2491x1(c: Cast) -> None:
    """See `_no_provoke_for_attacks`: the narrow sentence is one window
    and not every window, which is what `c.no_provoke` would have shut."""
    _no_provoke_for_attacks(c)


@power("i2887x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2887x1(c: Cast) -> None:
    """Initiative is a place in the order rather than a modifier, so the
    bonus is applied rather than stored."""
    c.initiative(c.enhancement, on=c.me)


@power("i2887p1", level=4, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you roll initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll initiative"))
def i2887p1(c: Cast) -> None:
    c.reroll_initiative(on=c.me)


@power("i2985x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2985x1(c: Cast) -> None:
    _death_save(c, 2)


@power("i2985p1", level=4, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you fail a saving throw",
       on=Trigger(SavingThrow, about_me, "you roll a saving throw"))
def i2985p1(c: Cast) -> None:
    ev = c.trigger
    if ev is None or ev.saved:
        return
    ev.natural = 20
    ev.saved = True


@power("i3132x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3132x1(c: Cast) -> None:
    """`c.terrain` is what "in snowy or icy environments" asks, so the
    Stealth half is armed only where the fight is being had."""
    c.resist(3 + 2 * c.enhancement, DamageType.COLD)
    if c.terrain("snow") or c.terrain("ice"):
        c.bonus("skill:stealth", c.enhancement, on=c.me,
                until=When.ENCOUNTER)


@power("i3132p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3132p1(c: Cast) -> None:
    """`c.aura` takes no `difficult`, but the `Zone` it spawns carries the
    flag and `Zones.difficult_squares` reads it off every zone, aura or
    not -- so the missing verb was a keyword argument and not a mechanism.
    "For creatures other than you" is the exemption rather than a second
    zone, and the printed minor action to switch it off is `c.endable` on
    the zone's own hold."""
    zid = c.aura(1, until=When.ENCOUNTER)
    zone = c.world.get(zid, Zone)
    if zone is None:
        return
    zone.difficult = True
    c.world.zones.refresh()
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    c.endable(zone.effect, MINOR)


@power("i451x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i451x1(c: Cast) -> None:
    c.resist(1)


@power("i507x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.escape()",))
def i507x1(c: Cast) -> None:
    """The save bonus stands -- a hold carries its conditions -- and the
    escape half has no check."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_holding(Condition.RESTRAINED, Condition.IMMOBILIZED))


@power("i530x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i530x1(c: Cast) -> None:
    dtype = c.choose(
        [d for d in _RESIST_LIST if d is not DamageType.PSYCHIC],
        "the damage type this armour turns",
    )
    if dtype is not None:
        c.resist(5, dtype)


@power("i530p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you take damage of a type this armour does not turn",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def i530p1(c: Cast) -> None:
    """"The armour's resistance changes" is two operations: `i530x1`'s
    hold goes -- `c.resist` files an undo on it, so ending it puts the old
    number back -- and the new one is laid in its place."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None:
        return
    c.end_effect(on=c.me, against="i530x1")
    c.resist(5, dtype, until=When.ENCOUNTER)
    if c.spend_points(1):
        c.resist(5, dtype, until=When.EONT)


@power("i535x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i535x1(c: Cast) -> None:
    c.bonus("skill:bluff", c.enhancement, on=c.me, until=When.ENCOUNTER,
            kind="item")
    c.bonus("skill:intimidate", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")
    _defences(c, 2, on=c.me, until=When.ENCOUNTER, kind="item",
              when=lambda ctx: c.cursed(on=ctx.get("attacker")))


@power("i535p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE)
def i535p1(c: Cast) -> None:
    """The printed benefit is *which* enemy may be cursed, so the row is
    simply the curse aimed where the player wants it."""
    c.curse()


@power("i536x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i536x1(c: Cast) -> None:
    """`query.surge_value` reads `Mods.total`, so the raise is an ordinary
    modifier. The number is the armour's own enhancement bonus."""
    c.bonus("surge_value", c.enhancement, on=c.me, until=When.ENCOUNTER,
            kind="item")


@power("i610x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def i610x1(c: Cast) -> None:
    """Drawing a weapon costs no action the engine charges."""
    c.initiative(c.enhancement, on=c.me)


@power("i632p1", level=4, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally near your spirit companion hits an enemy",
       on=Trigger(Hit, _ally_hits, "an ally hits an enemy"))
def i632p1(c: Cast) -> None:
    """The companion is the centre of both halves, so the distance is
    measured from it rather than from you."""
    spirit = c.companion()
    if spirit is None:
        return
    for mate in [c.me, *c.allies()]:
        if query.distance_between(c.world, spirit, mate) <= 5:
            c.temp_hp(5 + c.con_mod, on=mate)


@power("i669x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i669x1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE)
    c.resist(5, DamageType.NECROTIC)


@power("i699p1", level=4, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF)
def i699p1(c: Cast) -> None:
    if c.bloodied(on=c.me):
        c.resist(10, until=When.EONT)


@power("i728p1", level=4, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, todo=("Bloodied.source",))
def i728p1(c: Cast) -> None:
    """`Bloodied` names only the creature that was bloodied, and the
    payout goes to whoever did it -- so the row has no one to reward.
    `Dropped` was given a `source` for exactly this shape; `Bloodied` was
    not."""


@power("i993x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i993x1(c: Cast) -> None:
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


# -- level 5 ----------------------------------------------------------------


@power("i1041x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1041x1(c: Cast) -> None:
    c.resist(5, DamageType.NECROTIC)
    c.resist(5, DamageType.POISON)


@power("i1041p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.NECROTIC],
       trigger="an enemy hits you with a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you"))
def i1041p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.damage("1d10", c.cha_mod, dtype=DamageType.NECROTIC, on=foe)


@power("i1211x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1211x1(c: Cast) -> None:
    """`SurgeSpent` rather than `Healed`: the card pays on the surge, so a
    second wind and an ally's heal that spends one both count, and a heal
    that spends none does not."""

    def spent(ev: SurgeSpent) -> None:
        if ev.actor == c.me and in_beast_form(c.world, c.me):
            c.heal(2, on=c.me)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=c.me)


@power("i1211p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i1211p1(c: Cast) -> None:
    c.surge(on=c.me)


@power("i1227p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       dropped=("Healed.power",))
def i1227p1(c: Cast) -> None:
    """"By one of your encounter or daily powers" is dropped: `Healed`
    names the source and the number and not the row that did it, so the
    top-up pays out on any healing of mine."""

    def mended(ev: Healed) -> None:
        if ev.source != c.me:
            return
        c.heal(c.roll("1d10") + c.cha_mod, on=ev.target)

    c.watch(Healed, mended, until=When.EOT, on=c.me)


@power("i1522x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Healed.surge",))
def i1522x1(c: Cast) -> None:
    """"A power that lets a creature spend a surge" narrows this to one
    kind of healing, and the event does not say which kind it was."""

    def mended(ev: Healed) -> None:
        if ev.source != c.me or ev.target == c.me:
            return
        c.heal(c.enhancement, on=ev.target)

    c.watch(Healed, mended, until=When.ENCOUNTER, on=c.me)


@power("i2013p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       todo=("Hit.damage",))
def i2013p1(c: Cast) -> None:
    """Half the marker named something that already exists under another
    name: `query.flanked_by(world, victim, attacker)` answers the flanking
    clause, and the rest of the trigger -- an ally within 5, a melee
    attack -- is ordinary.

    What is left is the number. The heal is half the attack's damage and
    `Hit` carries none; `DamageApplied` carries one and names no power, so
    it cannot tell a melee attack from a burst or a burn."""


@power("i2049p1", level=5, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, trigger="an enemy hits you",
       on=Trigger(AttackDeclared, _hit_my_ac, "an enemy attacks your AC"))
def i2049p1(c: Cast) -> None:
    """An interrupt has to arrive before the roll, so this answers the
    declaration; `once=True` spends it on that one attack."""
    c.bonus(AC, 2, on=c.me, until=When.EOT, kind="power", once=True)


@power("i2124x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2124x1(c: Cast) -> None:
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.points() >= 1)


@power("i2124p1", level=5, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2124p1(c: Cast) -> None:
    c.shift(1)


@power("i2445p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage from an attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def i2445p1(c: Cast) -> None:
    if c.spend_points(1):
        c.conceal(on=c.me, until=When.EONT, total=True)
        mate = next(iter(c.within(3, side="team")), None)
        if mate is not None:
            c.conceal(on=mate, until=When.EONT, total=True)
        return
    c.conceal(on=c.me, until=When.EONT)
    for mate in c.within(3, side="team"):
        c.conceal(on=mate, until=When.EONT)


@power("i2446x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2446x1(c: Cast) -> None:
    """See `_no_provoke_for_attacks`, and `i2491x1`, which prints the same
    sentence the other way round."""
    _no_provoke_for_attacks(c)


@power("i2446p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.light()",))
def i2446p1(c: Cast) -> None:
    """Dim light and darkness are not on the board."""


@power("i2465p1", level=5, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an attack gives you ongoing damage",
       on=Trigger(EffectApplied, _gains_burn(), "you gain ongoing damage"))
def i2465p1(c: Cast) -> None:
    """"An equal amount" is read off the hold rather than off
    `EffectApplied`, which announces a label and a duration and not the
    number -- see `_burn_on`. Untyped going back, as the card prints."""
    burn = _burn_on(c.world, c.me)
    foe = _foe(c)
    if burn is None or foe is None:
        return
    c.ongoing(burn.ongoing[0], on=foe, until=When.SAVE_ENDS)


@power("i2497x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2497x1(c: Cast) -> None:
    c.resist(5, DamageType.LIGHTNING)


@power("i2497p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, trigger="you take lightning damage",
       on=Trigger(DamageApplied, _typed_damage_on_me(DamageType.LIGHTNING),
                  "you take lightning damage"))
def i2497p1(c: Cast) -> None:
    """Both contexts carry the power, so "this armour's daily" is a gate
    on the ref rather than a flag hung on the other row."""
    mine = "i2497p2"
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == mine)
    c.bonus("damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == mine)


@power("i2497p2", level=5, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.LIGHTNING],
       attack=Attack(vs=FORT, printed=8),
       trigger="an enemy adjacent to you targets you with an attack",
       on=Trigger(AttackDeclared, both(targets_me, by_melee),
                  "an adjacent enemy attacks you"))
def i2497p2(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", dtype=DamageType.LIGHTNING)
        c.dazed(until=When.EONT)


@power("i2529p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, trigger="you make a check to jump",
       on=Trigger(SkillCheck, about_me, "you make a skill check"))
def i2529p1(c: Cast) -> None:
    """A jump is its own verb rather than a check with a distance, so the
    extra squares are jumped rather than added to the roll."""
    c.jump(c.enhancement, on=c.me)


@power("i2727p1", level=5, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an effect dazes or stuns you",
       on=Trigger(ConditionApplied,
                  _condition_on_me(Condition.DAZED, Condition.STUNNED),
                  "you are dazed or stunned"))
def i2727p1(c: Cast) -> None:
    c.save(on=c.me)


@power("i2814x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.ability_bonus()",))
def i2814x1(c: Cast) -> None:
    """An ability modifier is read straight off `Stats` wherever a row
    asks for it, so there is one place to add to and it is everywhere."""


@power("i3119p1", level=5, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       trigger="you start a charge",
       on=Trigger(AttackDeclared, both(by_me, by_charge), "you charge"),
       dropped=("MoveStart.charge",))
def i3119p1(c: Cast) -> None:
    """The charge is only knowable once the swing is declared, so the
    invisibility arrives at the end of the run rather than the start."""
    c.invisible(on=c.me, until=When.EOT)


@power("i3122p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE)
def i3122p1(c: Cast) -> None:
    """"Until that enemy drops below 1 hit point" is free: `c.enemies`
    leaves out the dead, so the gate stops holding when it falls."""
    foe = c.target
    if foe is None:
        return
    best = max(_ALL_DEFENCES, key=lambda d: query.defence(c.world, foe, d))
    c.bonus(best, 2, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: foe in c.enemies())


@power("i3125x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3125x1(c: Cast) -> None:
    c.bonus("skill:stealth", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3125p1", level=5, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i3125p1(c: Cast) -> None:
    """"Until you attack" wants no watch: invisibility is `HIDDEN_FROM`
    and `resolve.attack` clears it for whoever swung, after the swing has
    had the benefit. "You can end this effect as a minor action" is
    `c.endable`, which puts a `drop` on the wearer's action menu."""
    c.endable(c.invisible(on=c.me, until=When.ENCOUNTER))


@power("i3424x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3424x1(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_burning(DamageType.FIRE))


@power("i3424p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE],
       trigger="you take damage from an enemy attack",
       on=Trigger(DamageApplied, targets_me, "you take damage"))
def i3424p1(c: Cast) -> None:
    """`c.burns` is the once-a-turn payout the printed aura wants."""
    ring = c.aura(1, until=When.EONT)
    c.burns(ring, 3 + c.enhancement, DamageType.FIRE)


@power("i3425x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3425x1(c: Cast) -> None:
    """"Ongoing damage that has a type" is every burn but the untyped
    one, which the effect itself says."""

    def gate(ctx: dict[str, Any]) -> bool:
        burn = getattr(ctx.get("effect"), "ongoing", None)
        return burn is not None and burn[1] is not DamageType.UNTYPED

    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item", when=gate)


@power("i3425p1", level=5, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you take damage that has a type",
       on=Trigger(DamageApplied, targets_me, "you take damage"),
       dropped=("c.extra_damage()", "c.on_expire()"))
def i3425p1(c: Cast) -> None:
    """The extra die lands, untyped: `c.bonus` has no damage type. The
    clause that turns the die back on you if you do not swing wants
    something to run when a one-shot expires unspent."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True)


@power("i461x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i461x1(c: Cast) -> None:
    """The cap is the heroic one; the paragon ceilings are out of scope."""
    value = max(0, min(c.dex_mod, 1))
    if value:
        c.bonus(AC, value, on=c.me, until=When.ENCOUNTER, kind="item",
                when=lambda ctx: not c.bloodied(on=c.me))


@power("i466x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i466x1(c: Cast) -> None:
    """What is stowed, and what that turns, is settled on an extended
    rest."""


@power("i545p1", level=5, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE)
def i545p1(c: Cast) -> None:
    """`world.effects.of` is how the rest of the tree reads somebody
    else's holds, so the marker was asking for a reader that is already
    reachable; `c.transfer` then moves one intact -- conditions, burn and
    saving throw together.

    The last clause rides the `SavingThrow` read-back: the throw is
    announced before it is acted on, so refusing it until the end of my
    next turn is `ev.saved = False` and not a modifier, which could only
    make the throw harder and never impossible."""
    mate = c.target
    if mate is None or not c.adjacent(mate):
        return
    held = [
        eff for eff in sorted(c.world.effects.of(mate), key=lambda e: e.id)
        if not eff.ended and eff.when is When.SAVE_ENDS
    ]
    picked = c.choose(held, "which effect to take on")
    if picked is None:
        return
    moved = c.transfer(picked, to=c.me)
    if moved is None:
        return
    mine = f"e{moved.id}["

    def too_soon(ev: SavingThrow) -> None:
        if ev.actor == c.me and mine in ev.against:
            ev.saved = False

    c.watch(SavingThrow, too_soon, until=When.EONT, on=c.me)


@power("i545p2", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.HEALING])
def i545p2(c: Cast) -> None:
    """You spend the surge; the ally heals "as though" one had been
    spent, so none leaves their pool."""
    mate = next(iter(c.within(5, side="ally")), None)
    c.spend_surge(on=c.me)
    if mate is not None:
        c.heal(c.surge_value(of=mate), on=mate)


@power("i603p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i603p1(c: Cast) -> None:
    """See `_erode`. "Each time an attack hits your AC", so the trigger is
    the hit and the defence it was aimed at, not every attack."""
    _erode(
        c,
        c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="power"),
        Hit,
        _hit_my_ac,
    )


@power("i626x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind while you are bloodied",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def i626x1(c: Cast) -> None:
    """Bloodied is asked of the world before the hit points come back,
    which is what `SecondWind` being announced ahead of the healing is
    for. Heroic tier, so 1d10; the level steps are paragon and epic."""
    if c.bloodied(on=c.me):
        c.heal(c.roll("1d10"), on=c.me)


@power("i721x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i721x1(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


# -- level 6 ----------------------------------------------------------------


@power("i1375x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1375x1(c: Cast) -> None:
    """The bargain is between the first throw of a turn and the second, so
    the count resets when the turn does. Written on the `SavingThrow`
    read-back for the same reason `_death_save` is: a standing modifier
    cannot tell one throw from the next, and this one has to pay the
    second throw back for what the first was lent.

    Death saves are left out. There is only ever one a turn, so the second
    half of the bargain could never be collected."""
    run = {"n": 0, "taken": False}

    def reset(ev: TurnStart) -> None:
        if ev.actor == c.me and not getattr(ev, "ghost", False):
            run["n"], run["taken"] = 0, False

    def rider(ev: SavingThrow) -> None:
        if ev.actor != c.me or ev.against == "death":
            return
        run["n"] += 1
        if run["n"] == 1:
            run["taken"] = c.may("gamble on the first saving throw", who=c.me)
            if not run["taken"]:
                return
            ev.bonus += 2
        elif run["n"] == 2 and run["taken"]:
            ev.bonus -= 2
        else:
            return
        ev.saved = ev.natural + ev.bonus >= 10

    c.watch(TurnStart, reset, until=When.ENCOUNTER, on=c.me)
    c.watch(SavingThrow, rider, until=When.ENCOUNTER, on=c.me)


@power("i1375p1", level=6, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, trigger="an enemy hits you",
       on=Trigger(AttackRolled, _rolled_on_me, "an enemy hits you"))
def i1375p1(c: Cast) -> None:
    """`c.reroll_attack` sets `critical` from the new face; the card says
    the second result crits whatever it shows, so the flag is set again
    afterwards. `AttackRolled` is the window for both: `Hit` is announced
    with the flag already copied off the result."""
    if not c.reroll_attack(keep="new"):
        return
    result = getattr(c.trigger, "result", None)
    if result is not None and result.hit:
        result.critical = True


@power("i1615p1", level=6, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH],
       out_of_combat=True)
def i1615p1(c: Cast) -> None:
    """A disguise: the armour bonus it gives up is a column, and the
    Bluff check is not a fight."""


@power("i2715p1", level=6, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2715p1(c: Cast) -> None:
    """Putting the armour away and calling it back."""


# -- level 7 ----------------------------------------------------------------


@power("i1037x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.death_threshold()",))
def i1037x1(c: Cast) -> None:
    """Three failures is written into `turns._death_saves` as a literal."""


@power("i1037p1", level=7, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you roll a death saving throw",
       on=Trigger(SavingThrow, _my_death_save, "you roll a death save"))
def i1037p1(c: Cast) -> None:
    """The throw is announced with `bonus=0` and read back, which is the
    only door a death-save modifier has."""
    ev = c.trigger
    if ev is None:
        return
    ev.bonus += 2
    ev.saved = ev.natural + ev.bonus >= 10


@power("i1039x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1039x1(c: Cast) -> None:
    _auto_save(c, "ongoing", "necrotic")


@power("i1039p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.NECROTIC])
def i1039p1(c: Cast) -> None:
    _spikes(c, "1d8", c.con_mod, DamageType.NECROTIC, When.EONT)


@power("i1261x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.grant_weapon()",))
def i1261x1(c: Cast) -> None:
    """An item is a base item with properties laid on it and never a new
    one, so a suit of armour that *is* also a weapon has nowhere to put
    the weapon: nothing adds one to `Gear.weapons` from a body."""


@power("i1261p1", level=7, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(1), target=EACH_ENEMY,
       dropped=("c.grant_weapon()",))
def i1261p1(c: Cast) -> None:
    """The burst of basic attacks plays; each one swings whatever the
    wearer is actually holding rather than the armour's claw."""
    c.basic()


@power("i1598p1", level=7, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.FIRE],
       trigger="you are marked",
       on=Trigger(ConditionApplied, _condition_on_me(Condition.MARKED),
                  "you are marked"))
def i1598p1(c: Cast) -> None:
    foe = _foe(c)
    c.cure(Condition.MARKED, on=c.me)
    if foe is not None:
        c.flat(5, dtype=DamageType.FIRE, on=foe)


@power("i1660p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with an attack that targets Will",
       on=Trigger(AttackRolled, _missed_by_me_vs_will,
                  "you miss against Will"))
def i1660p1(c: Cast) -> None:
    """Declared on the roll, not on `Miss`, because only the roll says
    which defence was aimed at."""
    c.reroll_attack(keep="new", bonus=c.enhancement)


@power("i1803x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1803x1(c: Cast) -> None:
    def ran(ev: AttackDeclared) -> None:
        if getattr(ev, "attacker", None) != c.me:
            return
        if not by_charge(c.world, c.me, ev):
            return
        c.bonus(AC, 1, on=c.me, until=When.EONT)

    c.watch(AttackDeclared, ran, until=When.ENCOUNTER, on=c.me)


@power("i1803p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you hit with a charge attack",
       on=Trigger(Hit, both(by_me, by_charge), "you hit with a charge"))
def i1803p1(c: Cast) -> None:
    """"Or" is a choice, so it is asked."""
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me, bonus=c.enhancement)
    else:
        c.save(on=c.me, bonus=c.enhancement)


@power("i2127x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2127x1(c: Cast) -> None:
    c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i2127p1", level=7, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, trigger="you shift one or more squares",
       on=Trigger(MoveEnd, about_me, "you finish a move"))
def i2127p1(c: Cast) -> None:
    """Half of a +1 is nothing, which is what the card says at heroic."""
    if getattr(c.trigger, "kind_", "") != "shift":
        return
    extra = c.enhancement // 2
    if extra:
        c.shift(extra)


@power("i2440p1", level=7, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, trigger="you become bloodied",
       on=Trigger(Bloodied, about_me, "you become bloodied"))
def i2440p1(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)


@power("i2494x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.save_vs_forced()",))
def i2494x1(c: Cast) -> None:
    """Forced movement is shortened by `c.resist_forced` and never saved
    against, so there is no throw to add to."""


@power("i2541x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignore_squeeze_penalty()",))
def i2541x1(c: Cast) -> None:
    """The combat-advantage half is a gate on the condition; the attack
    penalty squeezing costs is applied where no row can reach it."""
    c.no_advantage(on=c.me, until=When.ENCOUNTER,
                   when=lambda ctx: c.is_(Condition.SQUEEZING, on=c.me))


@power("i2541p1", level=7, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.move_through()",))
def i2541p1(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power("i2725x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2725x1(c: Cast) -> None:
    c.resist(5, DamageType.RADIANT)


@power("i2725p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.RADIANT],
       trigger="an enemy hits you with an opportunity attack",
       on=Trigger(Hit, _opportunity_on_me, "an enemy takes an opening"))
def i2725p1(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; `resolve.attack` hangs it on
    afterwards, so the predicate reads it with `getattr`."""
    foe = _foe(c)
    if foe is not None:
        c.damage("1d10", c.dex_mod, dtype=DamageType.RADIANT, on=foe)


@power("i3000x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3000x1(c: Cast) -> None:
    """"At the start of your next turn" is a second watch rather than an
    immediate payout, because the card holds it back."""

    def crit(ev: Hit) -> None:
        if not _crit_on_me(c.world, c.me, ev):
            return

        def later(_: TurnStart) -> None:
            c.temp_hp(5 + c.enhancement, on=c.me)

        c.watch(TurnStart, later, until=When.SONT, on=c.me, once=True)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


@power("i3116x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3116x1(c: Cast) -> None:
    def hurt(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.amount < 20:
            return

        def later(_: TurnEnd) -> None:
            c.temp_hp(5, on=c.me)

        c.watch(TurnEnd, later, until=When.EOT, on=c.me, once=True)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=c.me)


@power("i608p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=NO_TARGET)
def i608p1(c: Cast) -> None:
    """Either yourself or a neighbour, so it is asked."""
    marked = [
        w for w in [c.me, *c.within(1, side="ally")]
        if c.is_(Condition.MARKED, on=w)
    ]
    who = c.choose(marked, "whose mark ends")
    if who is not None:
        c.cure(Condition.MARKED, on=who)


# -- level 8 ----------------------------------------------------------------


@power("i1199x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1199x1(c: Cast) -> None:
    c.bonus("save", 5, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_holding(Condition.SLOWED, Condition.IMMOBILIZED))


@power("i1199p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1199p1(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.EONT, kind="power")


@power("i1684x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1684x1(c: Cast) -> None:
    _defences(c, 4, on=c.me, until=When.ENCOUNTER, kind="item",
              when=_keyworded(Keyword.POLYMORPH))


@power("i1892p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are pushed, pulled or slid",
       on=Trigger(ForcedMove, _forced_on_me, "you are moved against your will"))
def i1892p1(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.EOT)


@power("i2136p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH])
def i2136p1(c: Cast) -> None:
    """Sustain standard, revert free: `c.form` holds the shape and the
    two bars are separate holds on the same clock."""
    c.form(until=When.SUSTAIN, revert=FREE)
    c.cannot_attack(on=c.me, until=When.SUSTAIN)
    c.bonus("skill:stealth", 5, on=c.me, until=When.SUSTAIN)


@power("i2172x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2172x1(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power("i2172p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an effect forces you to move",
       on=Trigger(ForcedMove, _forced_on_me, "you are moved against your will"))
def i2172p1(c: Cast) -> None:
    """`ForcedMove` is a `Decision`, so an interrupt can simply refuse
    it -- which is what "you ignore the forced movement" says."""
    foe = _foe(c)
    c.cancel()
    if foe is not None:
        c.prone(on=foe)


@power("i2412p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you take force, lightning, psychic or radiant damage",
       on=Trigger(DamageRolled,
                  _typed_damage_on_me(DamageType.FORCE, DamageType.LIGHTNING,
                                      DamageType.PSYCHIC, DamageType.RADIANT),
                  "you take damage of one of those types"))
def i2412p1(c: Cast) -> None:
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, until=When.ENCOUNTER)


@power("i2466x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2466x1(c: Cast) -> None:
    def given(ev: TempHP) -> None:
        if getattr(ev, "source", None) != c.me or ev.target == c.me:
            return
        c.temp_hp(getattr(ev, "amount", 0) // 2, on=c.me)

    c.watch(TempHP, given, until=When.ENCOUNTER, on=c.me)


@power("i2535p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ACID])
def i2535p1(c: Cast) -> None:
    def sting(ev: Hit) -> None:
        if ev.target != c.me or not by_melee(c.world, c.me, ev):
            return
        c.ongoing(5, DamageType.ACID, on=ev.attacker)

    c.watch(Hit, sting, until=When.EONT, on=c.me)


@power("i2542x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2542x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON)


@power("i2542p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       trigger="you take damage from a melee attack",
       on=Trigger(DamageApplied, both(targets_me, by_melee),
                  "a melee attack damages you"))
def i2542p1(c: Cast) -> None:
    """"This armour's poison resist value" is the number its property
    prints, which is 5 through heroic."""
    foe = _foe(c)
    if foe is not None:
        c.ongoing(5, DamageType.POISON, on=foe)


@power("i2581x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2581x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON)


@power("i2581p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an adjacent enemy hits you with a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you"))
def i2581p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.condition(Condition.RESTRAINED, until=When.EOTNT, on=foe)


@power("i2686p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2686p1(c: Cast) -> None:
    """`c.expend_row` is the verb the marker wanted: a use goes and the
    row never runs, which is exactly the price this card charges. The
    choice is optional, because the card's "you can" is, and declining
    leaves the base resistance standing."""
    resist = 5
    known = c.world.get(c.me, Powers)
    fuel = sorted(
        ref
        for ref in (known.known if known is not None else ())
        if (p := get(ref)) is not None
        and p.usage in (ENCOUNTER, DAILY)
        and Keyword.ARCANE in p.keywords
    )
    picked = c.choose(fuel, "a power to burn for resistance", optional=True)
    if picked is not None and c.expend_row(picked):
        resist += 5
    c.resist(resist, until=When.EONT)


@power("i3124x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3124x1(c: Cast) -> None:
    c.mode("swim", 3 + c.enhancement, on=c.me, until=When.ENCOUNTER)


@power("i634p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i634p1(c: Cast) -> None:
    """"Must make a saving throw to attack you, and once it saves it can
    attack normally" is exactly a save-ends bar against one creature."""
    for foe in c.enemies():
        if "beast" in c.kinds_of(on=foe):
            c.cannot_attack(on=foe, against=c.me, until=When.SAVE_ENDS)


@power("i689x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i689x1(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("i689p1", level=8, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="an enemy misses you with an attack",
       on=Trigger(Miss, targets_me, "an enemy misses you"))
def i689p1(c: Cast) -> None:
    c.teleport(2 + c.enhancement)
    if c.spend_points(1):
        c.restore_use(c.ref)


@power("i705x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i705x1(c: Cast) -> None:
    def struck(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        c.bonus(AC, 2, on=c.me, until=When.EONT, kind="item",
                when=_from(ev.target))

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me)


@power("i808p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i808p1(c: Cast) -> None:
    _spikes(c, 0, c.enhancement, DamageType.UNTYPED, When.ENCOUNTER)


# -- level 9 ----------------------------------------------------------------


@power("i1067p1", level=9, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you take acid, cold, fire or lightning damage",
       on=Trigger(DamageRolled,
                  _typed_damage_on_me(DamageType.ACID, DamageType.COLD,
                                      DamageType.FIRE, DamageType.LIGHTNING),
                  "you take damage of one of those types"))
def i1067p1(c: Cast) -> None:
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, until=When.ENCOUNTER)


@power("i1353x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1353x1(c: Cast) -> None:
    """"A bonus ... equal to the armor's enhancement bonus" prints no type
    word, so untyped. The narrowing is the keywords of the row that laid
    the hold, which the saving-throw context now carries."""
    c.bonus("save", c.enhancement, on=c.me, until=When.ENCOUNTER,
            when=_save_keywords(Keyword.FEAR))


@power("i1353p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="a fear power hits you with a save-ends effect",
       on=Trigger(EffectApplied, _fear_save_ends_on_me,
                  "a fear effect a save can end lands on you"))
def i1353p1(c: Cast) -> None:
    """The save is rolled against the hold that triggered the row, by its
    label: without `against=` it takes whichever save-ends effect it finds
    first, which may be the burn rather than the fear."""
    c.save(on=c.me, bonus=5, against=getattr(c.trigger, "label", "") or "")
    _defences(c, 2, on=c.me, until=When.EONT, kind="power")


@power("i1401x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1401x1(c: Cast) -> None:
    c.resist(5, DamageType.NECROTIC)


@power("i1401p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1401p1(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)


@power("i1625x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1625x1(c: Cast) -> None:
    c.resist(5, DamageType.COLD)
    c.resist(5, DamageType.NECROTIC)


@power("i1625p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1625p1(c: Cast) -> None:
    """"Any ally adjacent to you" keeps being asked, so this is an aura
    with `c.resist_in` rather than a snapshot of who is standing near."""
    ring = c.aura(1, until=When.ENCOUNTER)
    c.resist_in(ring, 5, DamageType.COLD)
    c.resist_in(ring, 5, DamageType.NECROTIC)


@power("i1708x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1708x1(c: Cast) -> None:
    c.resist(5, DamageType.NECROTIC)


@power("i1708p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.NECROTIC],
       trigger="you are struck by a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "a melee attack hits you"))
def i1708p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is None:
        return
    c.damage(f"{max(1, c.enhancement)}d6", dtype=DamageType.NECROTIC, on=foe)
    c.penalty(FORT, 2, on=foe, until=When.EONT)


@power("i1751p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE,
       dropped=("query.footing(world, square)",))
def i1751p1(c: Cast) -> None:
    """"Standing on soil or sand" is a property of the square the target
    is in. `query.ground` was the wrong name twice over: what exists is
    `falling.ground(world, eid)`, which settles a creature onto the floor
    of its square and answers how far it fell, and it is about a creature
    rather than a square.

    What the board carries per square is `Grid.blocking`, `Grid.elevation`
    and `Grid.difficult` -- and `difficult` is a word for rough going
    ("mud", "rubble"), so plain soil never appears in it and reading it
    here would gate the row on a map nothing draws. The missing thing is
    what a square is *made of*, asked the way `query.light_level(world,
    square)` is asked."""
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power("i1785p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(3), target=ONE_CREATURE)
def i1785p1(c: Cast) -> None:
    c.pull(3)
    if c.adjacent():
        c.immobilized(until=When.SAVE_ENDS)


@power("i1869x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1869x1(c: Cast) -> None:
    gaze = _keyworded(Keyword.RADIANT, Keyword.GAZE)
    _defences(c, 2, on=c.me, until=When.ENCOUNTER, kind="item", when=gaze)

    def struck(ev: Hit) -> None:
        if ev.target != c.me or not gaze({"power": ev.power}):
            return
        c.penalty("attack", 2, on=ev.attacker, until=When.EOTNT)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me)


@power("i1869p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you are targeted by a ranged attack",
       on=Trigger(AttackDeclared, both(targets_me, by_ranged),
                  "a ranged attack is aimed at you"))
def i1869p1(c: Cast) -> None:
    foe = _foe(c)
    others = [w for w in c.within(5) if w not in (c.me, foe)]
    victim = c.choose(others, "who the shot finds instead")
    if victim is not None:
        c.redirect(to=victim)


@power("i2194x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2194x1(c: Cast) -> None:
    """The live `AttackResult` rides on the `Hit`; asking whether the
    enemy has combat advantage again is too late, because a one-shot
    grant has already been spent."""

    def struck(ev: Hit) -> None:
        if ev.target != c.me or not c.had_advantage(ev):
            return
        c.flat(c.enhancement, dtype=DamageType.RADIANT, on=ev.attacker)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me)


@power("i2545p1", level=9, cls=ITEM, usage=AT_WILL, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you take radiant damage",
       on=Trigger(DamageApplied, _typed_damage_on_me(DamageType.RADIANT),
                  "you take radiant damage"))
def i2545p1(c: Cast) -> None:
    c.surge(on=c.me, bonus=c.enhancement)


@power("i2545p2", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(2), target=EACH_ENEMY, keywords=[Keyword.RADIANT])
def i2545p2(c: Cast) -> None:
    c.flat(2 * c.enhancement, dtype=DamageType.RADIANT)
    c.penalty("attack", 2, until=When.EONT)


@power("i2737p1", level=9, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET, trigger="you are hit by an attack",
       on=Trigger(DamageRolled, targets_me, "an attack hits you"))
def i2737p1(c: Cast) -> None:
    """`c.absorb` takes the number off the event and deals it elsewhere,
    which is the only way damage already rolled can change hands."""
    mate = c.choose(c.within(5, side="ally"), "who takes it instead")
    if mate is not None:
        c.absorb(c.trigger, on=mate)


@power("i2881p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
       trigger="you take lightning or thunder damage",
       on=Trigger(DamageApplied,
                  _typed_damage_on_me(DamageType.LIGHTNING,
                                      DamageType.THUNDER),
                  "you take lightning or thunder damage"))
def i2881p1(c: Cast) -> None:
    dtype = getattr(c.trigger, "dtype", DamageType.UNTYPED)
    for foe in c.within(2, side="enemy"):
        c.flat(5, dtype=dtype, on=foe)


@power("i3118x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3118x1(c: Cast) -> None:
    c.bonus("skill:diplomacy", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")
    c.bonus("skill:intimidate", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3118p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.CHARM],
       dropped=("c.aura_effect()",))
def i3118p1(c: Cast) -> None:
    """The aura is on the board and follows you; what it does to whoever
    walks into it later is the missing half -- `c.grants_in` carries a
    modifier and `c.burns` carries damage, and neither carries a bar."""
    c.aura(2, until=When.ENCOUNTER)
    for foe in c.within(2, side="enemy"):
        c.cannot_attack(on=foe, against=c.me, until=When.SAVE_ENDS)


@power("i3120x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3120x1(c: Cast) -> None:
    c.bonus("skill:stealth", c.enhancement, on=c.me,
            until=When.ENCOUNTER, kind="item")


@power("i3120p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i3120p1(c: Cast) -> None:
    _defences(c, 2, on=c.me, until=When.EOT, kind="power")
    c.shift(3)


@power("i3131p1", level=9, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you start your turn while dying",
       on=Trigger(TurnStart, about_me, "your turn begins"))
def i3131p1(c: Cast) -> None:
    if not c.is_(Condition.DYING, on=c.me):
        return
    c.surge(on=c.me)
    c.cure(Condition.PRONE, on=c.me)
    c.resist(5 + c.enhancement, DamageType.NECROTIC)
    c.vulnerable(5 + c.enhancement, DamageType.RADIANT,
                 until=When.ENCOUNTER, on=c.me)


@power("i661p1", level=9, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you use a healing power",
       on=Trigger(PowerUsed, _my_power_with(Keyword.HEALING, other_than="i661p1"),
                  "you use a healing power"))
def i661p1(c: Cast) -> None:
    """`PowerUsed` is announced before the body runs, so the top-up is
    armed for the rest of the turn rather than paid out here."""

    topping_up = False

    def mended(ev: Healed) -> None:
        # The top-up is itself a heal from the same source, so without
        # the latch it answers its own `Healed` and recurses until the
        # stack runs out.
        nonlocal topping_up
        if topping_up or ev.source != c.me or ev.target == c.me:
            return
        topping_up = True
        try:
            c.heal(c.cha_mod, on=ev.target)
        finally:
            topping_up = False

    c.watch(Healed, mended, until=When.EOT, on=c.me)


@power("i661p2", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       trigger="you use a healing power",
       on=Trigger(PowerUsed, _my_power_with(Keyword.HEALING, other_than="i661p2"),
                  "you use a healing power"))
def i661p2(c: Cast) -> None:
    mate = next(iter(c.within(1, side="ally")), None)
    if mate is not None:
        c.surge(on=mate, bonus=c.cha_mod)


@power("i852p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, trigger="you are hit by an attack",
       on=Trigger(DamageRolled, targets_me, "an attack hits you"))
def i852p1(c: Cast) -> None:
    """Declared on the damage because the number is the payout."""
    c.temp_hp(max(0, getattr(c.trigger, "amount", 0)), on=c.me)


# -- level 10 ---------------------------------------------------------------


@power("i1223p1", level=10, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=SELF,
       requires=lambda world, eid: bool(query.hidden_from(world, eid)),
       requires_text="must be invisible")
def i1223p1(c: Cast) -> None:
    """The Requirement is an entry gate, not a guard in the body, so a
    creature nobody has lost sight of is never offered a row that would
    only re-lay what it has.

    `c.is_hidden` is not a different question after all -- `c.invisible`
    and `c.hide` both hold the same `Relation.HIDDEN_FROM`, so
    `query.hidden_from` is who cannot see you however you went unseen,
    which is what "you must be invisible" asks. Read as the free function
    because a `requires=` gate is handed `(world, eid)` and has no
    `Cast`."""
    c.invisible(on=c.me, until=When.EONT)


@power("i1729x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1729x1(c: Cast) -> None:
    """"After each rest" is the start of the fight, which is when a
    property is armed."""
    c.temp_hp(5, on=c.me)


@power("i2444x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2444x1(c: Cast) -> None:
    """The gate was thought unsayable and is not. `c.conceal` is
    `c.bonus`, so the concealment `cf:warlock-f3` grants is a hold wearing
    that feature's ref as its label -- which is what tells it from
    concealment out of a spell, a zone or the dark. The modifier itself
    records no source; the hold that carries it does.

    Laid on `AttackDeclared` rather than as a standing relation because
    both halves come and go within a turn and `c.grants_advantage` takes
    no `when=`. `once=True`, so the grant is spent on the attack that
    asked for it."""

    def shadowed(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or not c.cursed(ev.target):
            return
        if not any(
            e.label.startswith("cf:warlock-f3") and not e.ended
            for e in c.world.effects.of(c.me)
        ):
            return
        c.grants_advantage(on=ev.target, to=c.me, until=When.EONT, once=True)

    c.watch(AttackDeclared, shadowed, until=When.ENCOUNTER, on=c.me,
            window=Window.BEFORE)


@power("i3043p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET)
def i3043p1(c: Cast) -> None:
    """The range is the armour's own plus, so the burst is sized here
    rather than in the header."""
    for foe in c.within(c.enhancement, side="enemy"):
        c.pull(c.enhancement, on=foe, to=None)


@power("i3484x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.blindsight()", "c.malfunction()"))
def i3484x1(c: Cast) -> None:
    """Blindsight and tremorsense are not senses the board keeps, and
    the malfunction turns on a natural 1 on an attack roll doing
    something to the roller, which nothing watches for."""


@power("i3484p1", level=10, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3484p1(c: Cast) -> None:
    c.mode("fly", c.speed_of(), on=c.me, until=When.EONT)


@power("i550p1", level=10, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="an enemy hits you",
       on=Trigger(Hit, targets_me, "an enemy hits you"))
def i550p1(c: Cast) -> None:
    """The augment moves the neighbours too, and `share=True` is what
    carries them along."""
    if c.spend_points(1):
        c.teleport(5, share=True)
        return
    c.teleport(5)


@power("i962x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i962x1(c: Cast) -> None:
    """"The first enemy that hits you during an encounter" is `once`."""

    def struck(ev: Hit) -> None:
        if ev.target != c.me:
            return
        c.ongoing(5, on=ev.attacker)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=c.me, once=True)
