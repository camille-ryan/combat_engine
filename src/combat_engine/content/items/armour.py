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
* **The saving-throw context is `actor`, `effect` and `label`.** That is
  enough for "against ongoing necrotic damage" (the effect carries its
  burn) and for "against effects that daze, dominate or stun" (it carries
  its conditions), and not enough for "against fear effects" -- a save has
  no power and therefore no keywords. Those clauses are marked.

Two verbs the slot keeps asking for and that do not exist: `c.escape()`
(an escape attempt is not modelled at all, and eight blocks print a bonus
to one) and `c.end_ongoing()` ("the ongoing damage ends", with no saving
throw). Death saves are rolled in `turns._death_saves` with `bonus=0`, so
a standing `c.bonus("save", ...)` never reaches them; the three blocks
that print one ride the `SavingThrow` read-back instead.
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
    Hit,
    Keyword,
    Miss,
    MoveEnd,
    MoveStart,
    Ranged,
    SavingThrow,
    Trigger,
    When,
    World,
    about_me,
    both,
    by_charge,
    by_me,
    by_melee,
    get,
    power,
    query,
    targets_me,
)
from combat_engine.engine.events import Event

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


def _my_power_with(*words: Keyword):  # noqa: ANN202
    wanted = set(words)

    def check(world: World, me: int, ev: Event) -> bool:
        if getattr(ev, "actor", getattr(ev, "attacker", None)) != me:
            return False
        p = get(getattr(ev, "power", "") or "")
        return p is not None and bool(wanted & set(p.keywords))

    return check


def _typed_damage_on_me(*types: DamageType):  # noqa: ANN202
    wanted = set(types)

    def check(world: World, me: int, ev: Event) -> bool:
        return getattr(ev, "target", None) == me and (
            getattr(ev, "dtype", None) in wanted if wanted else True
        )

    return check


def _save_ends_on_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "save_ends", False)


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


# -- level 2 ----------------------------------------------------------------


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
       todo=("Keyword.CHANNEL_DIVINITY",))
def i1212p1(c: Cast) -> None:
    """The trigger is the whole row: nothing marks a power as Channel
    Divinity, and gating on `Keyword.DIVINE` would fire on every cleric
    at-will."""


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
       on=Trigger(ActionPointSpent, about_me, "you spend an action point"),
       dropped=("c.end_effect()",))
def i1552p1(c: Cast) -> None:
    """Forgoing the property's bonus needs a live hold to be cancelled by
    another row, and nothing takes one off."""
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
       reach=PERSONAL, target=SELF, todo=("c.in_form()",))
def i1586x1(c: Cast) -> None:
    """`c.form` assumes a shape and nothing asks which one is on, so
    "while you are in beast form" has no gate."""


@power("i1586p1", level=2, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.in_form()",))
def i1586p1(c: Cast) -> None:
    """Beast form is the usage restriction, not the effect."""
    c.shift(2)


@power("i1600x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1600x1(c: Cast) -> None:
    _auto_save(c, "ongoing", "poison")


@power("i1600p1", level=2, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF, todo=("c.end_ongoing()",))
def i1600p1(c: Cast) -> None:
    """Ending a burn outright, with no saving throw, has no verb:
    `c.cure` takes conditions and `c.save` rolls."""


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
       attack=Attack(INT, vs=WILL), dropped=("Attack.best_of()",))
def i2285p2(c: Cast) -> None:
    """"Intelligence or Charisma" is one attack line with two abilities and
    the header holds one; Intelligence is written. The printed enhancement
    bonus to the roll is the armour's own plus, laid on the attack rather
    than on AC, so `kind="enhancement"` is free here."""
    if c.first:
        c.bonus("attack", c.enhancement, on=c.me, until=When.EOT,
                kind="enhancement")
    if c.strike():
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
       reach=PERSONAL, target=SELF, todo=("Keyword.CHANNEL_DIVINITY",))
def i561x1(c: Cast) -> None:
    """Nothing marks a power as Channel Divinity."""


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
       on=Trigger(Hit, targets_me, "an enemy hits you"),
       dropped=("c.on_save()",))
def i1001p1(c: Cast) -> None:
    """The second, weaker penalty arrives when the first one is saved
    against, and nothing runs on a *successful* save -- `escalate` is the
    failed one."""
    foe = _foe(c)
    if foe is not None:
        c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)


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
       reach=PERSONAL, target=SELF,
       todo=("query.keywords_of(effect)", "c.on_second_wind()"))
def i1529x1(c: Cast) -> None:
    """Both halves are unsayable. A saving throw knows the effect but not
    the power that laid it, so "against fear" has no gate; and a second
    wind announces only the surge it spends, which any healing row does."""


@power("i1558p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       todo=("c.oath_target()", "c.resist_from()"))
def i1558p1(c: Cast) -> None:
    """Resistance against one creature's attacks: the damage context has
    no attacker, and nothing names an oath of enmity target."""


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
       reach=PERSONAL, target=SELF, dropped=("query.keywords_of(effect)",))
def i1911x1(c: Cast) -> None:
    """The resistance stands; the save bonus is dropped, because the save
    context carries the effect and not the power that laid it."""
    c.resist(5, DamageType.PSYCHIC)


@power("i2094x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.in_form()",))
def i2094x1(c: Cast) -> None:
    """Nothing asks which shape a creature is wearing."""


@power("i2094p1", level=3, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy adjacent to you shifts",
       on=Trigger(MoveStart, _adjacent_enemy_moves("shift"),
                  "an adjacent enemy shifts"),
       dropped=("c.in_form()",))
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
       reach=PERSONAL, target=SELF, dropped=("c.on_second_wind()",))
def i2366x1(c: Cast) -> None:
    """A second wind is a surge like any other from the outside, so the
    arcane damage half has no trigger of its own."""
    c.bonus("skill:arcana", c.enhancement, on=c.me, until=When.ENCOUNTER,
            kind="item")


@power("i2391x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.oath_target()",))
def i2391x1(c: Cast) -> None:
    """Nothing names an oath of enmity target."""


@power("i2434p1", level=3, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.move_through()",))
def i2434p1(c: Cast) -> None:
    """Crossing an occupied square is not something a shift can be told
    to do; the distance is the half that plays."""
    c.shift(3)


@power("i2460p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ILLUSION], dropped=("c.decay_bonus()",))
def i2460p1(c: Cast) -> None:
    """A bonus that wears down by 1 per attack has no verb: `stacks=False`
    keeps the *larger*, which is the wrong direction."""
    c.bonus(AC, 4 if c.spend_points(1) else 2, on=c.me, until=When.ENCOUNTER)


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
       reach=PERSONAL, target=SELF, dropped=("c.escape()",))
def i2582p1(c: Cast) -> None:
    """The grab is lifted with `c.cure`, which is the outcome; the escape
    *attempt* -- a contested check somebody can fail -- is what is
    missing."""
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
       on=Trigger(Hit, _my_power_with(Keyword.ARCANE),
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
       reach=PERSONAL, target=SELF, dropped=("c.end_resist()",))
def i3072p1(c: Cast) -> None:
    """The new resistance is laid on; taking the radiant one *off* needs a
    verb that cancels another row's standing hold."""
    dtype = c.choose(
        [DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER],
        "what this armour turns instead",
    )
    if dtype is not None:
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
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       todo=("c.end_ongoing()",))
def i549p1(c: Cast) -> None:
    """Both halves need the burn in hand: one to end it, the other to read
    the number off it, and nothing hands a body its own effects."""


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
