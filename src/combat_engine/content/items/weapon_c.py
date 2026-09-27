"""Weapon-slot magic items, heroic tier: the third wave of blocks.

Nothing here declares a weapon. The ladder, the enhancement bonus, the
critical rider and the base-item restriction are columns in `game.db` and
are laid on by `engine/equipment.py`; what is written here is only the part
that needs a body. A magic weapon is a longsword with extra properties, so
the group a card names -- spear, mace, hand crossbow -- is never checked
either: the item was dealt to whoever is holding it.

Four judgements run through the file.

* **The damage context carries no weapon**, so "using this weapon" is never
  a gate. The character holds the item for as long as the property is
  armed, so every swing is treated as the item's. That over-applies only
  for a character wielding two weapons of which one is magical.
* **"Once per round" is written as "once per turn of mine"**: nothing
  counts rounds for a creature, and a flag cleared on the wielder's own
  `TurnStart` is the same window for every row that prints the phrase.
* **The item's own level** is `get(c.ref).level`, for the cards printing
  "the weapon's level + 3" as an attack bonus. `Attack(printed=)` is the
  wrong tool -- it takes the *character's* level term back out again.
* **A damage type a card changes is `c.deals`**, which rewrites what the
  wielder's weapon attacks come out as; where the card changes only part
  of the damage, or hands back a way to change it again, the missing half
  is marked rather than quietly written as the whole.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    DEX,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageType,
    Defences,
    Dropped,
    Effect,
    EffectApplied,
    Forced,
    ForcedMove,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Movement,
    PowerUsed,
    Ranged,
    SecondWind,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    by_opportunity,
    by_ranged,
    get,
    power,
)

#: `PowerResolved` is the one event this file needs that the engine's
#: package does not re-export. It is the only place "you miss **every**
#: target" can be asked, so it is imported from the module it lives in
#: rather than approximated off a single `Miss`.
from combat_engine.engine.events import PowerResolved

ITEM = "item"

#: The four defences, for the cards printing "all defenses".
_DEFENCES = (AC, FORT, REF, WILL)


# -- gates on a context -----------------------------------------------------


def _against(c: Cast, *words: str):  # noqa: ANN202
    """Gate: the creature this damage or attack is aimed at is one of these."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and bool(c.kinds_of(on=foe) & set(words))

    return gate


def _dealt_by(c: Cast, *words: str):  # noqa: ANN202
    """Gate on a *resist* read: `c.resist`'s context carries `source`."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("source")
        return who is not None and bool(c.kinds_of(on=who) & set(words))

    return gate


def _swung_by(c: Cast, *words: str):  # noqa: ANN202
    """Gate on a *defence* read: the attack context carries `attacker`."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and bool(c.kinds_of(on=who) & set(words))

    return gate


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


def _opportunity(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("opportunity"))


def _aimed_at(who: int):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == who

    return gate


# -- predicates -------------------------------------------------------------


def _type_words(world: World, who: int | None) -> frozenset[str]:
    """A creature's type words, asked from a predicate.

    `c.kinds_of` is the verb and a predicate is handed `(world, me, ev)`
    with no `Cast` to call it on, so one is built as a probe.
    """
    if who is None:
        return frozenset()
    return Cast(world=world, me=who, ref="").kinds_of(on=who)


def _struck_kind(*words: str):  # noqa: ANN202
    """Predicate: I hit a creature of one of these kinds.

    The kind belongs in the predicate rather than in the body: a triggered
    daily is expended when it fires, so a row that fires on every hit and
    then finds the target is not a demon has spent itself for nothing.
    """

    def pred(world: World, me: int, ev: Any) -> bool:
        return getattr(ev, "attacker", None) == me and bool(
            _type_words(world, getattr(ev, "target", None)) & set(words)
        )

    return pred


def _my_shove(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and getattr(ev, "how", None) in (
        Forced.PUSH,
        Forced.PULL,
    )


def _all_missed(world: World, me: int, ev: Any) -> bool:
    """Every roll this use made came up short -- "you miss every target".

    `PowerResolved` carries the whole set of `AttackResult`s, which is the
    only place the question can be asked: a `Miss` is one target's.
    """
    rolls = getattr(ev, "rolls", None) or []
    return (
        getattr(ev, "actor", None) == me
        and bool(rolls)
        and not any(r.hit for r in rolls)
    )


def _once_a_turn(c: Cast) -> dict[str, bool]:
    """A flag cleared at the start of the wielder's turn.

    "The first time each round" and "once per turn" both come to this, and
    nothing on the board counts rounds per creature.
    """
    flag = {"spent": False}

    def fresh(ev: TurnStart) -> None:
        if ev.actor == c.me:
            flag["spent"] = False

    c.watch(TurnStart, fresh, until=When.ENCOUNTER)
    return flag


# -- level 8 ----------------------------------------------------------------


def _my_second_wind(world: World, me: int, ev: Any) -> bool:
    """"You use your second wind **on your turn**." The clause matters: a
    leader row can hand you one in the middle of somebody else's."""
    return getattr(ev, "actor", None) == me and world.turn == me


@power(
    "i2886x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2886x1(c: Cast) -> None:
    """`query.speed` is handed `{"charge": True}` by the three places that
    measure a charge's run and nothing at any other call site, so the gate
    is exact rather than a bonus to all movement."""
    c.bonus("speed", 2, kind="item", on=c.me, until=When.ENCOUNTER, when=_charging)


@power(
    "i2886p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def i2886p1(c: Cast) -> None:
    """`charges=True` or the engine measures reach before the run and
    refuses the row wherever a charge is worth making. Only the first swing
    is the charge's; the second is an ordinary basic at the same creature,
    and `c.landed` is what each of them hit on."""
    foe = c.target
    if foe is None:
        return
    c.charge_at(foe)
    first = c.landed
    c.basic(on=foe)
    if first and c.landed:
        c.flat(c.roll("1d6"), on=foe)


@power(
    "i2950x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2950x1(c: Cast) -> None:
    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.prone(on=ev.target)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2950p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2950p1(c: Cast) -> None:
    """"Per plus" is the enhancement as a die count, and the four printed
    conditions are asked of whoever is taking the damage."""
    dice = f"{max(1, c.enhancement)}d6"
    helpless = (
        Condition.BLINDED,
        Condition.PRONE,
        Condition.RESTRAINED,
        Condition.HELPLESS,
    )

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and any(c.is_(x, on=foe) for x in helpless)

    c.bonus("damage", 0, dice=dice, on=c.me, until=When.EONT, when=gate)


@power(
    "i2954x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2954x1(c: Cast) -> None:
    """"Crit on a 19-20" is one step of `crit_range`. The class half of the
    line is not enforced: the item was dealt to whoever is holding it."""
    c.as_implement(on=c.me)
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "i2989p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(STR, vs=WILL),
    trigger="you reduce an enemy to 0 hit points with this weapon",
    on=Trigger(Dropped, by_me, "you drop an enemy with this weapon"),
)
def i2989p1(c: Cast) -> None:
    """`Dropped` carries `source`, so `by_me` is the whole predicate. A
    burst picks its own targets, so the dispatcher does not aim this at
    the creature that just fell."""
    if c.strike():
        c.blinded(until=When.EONT)


@power(
    "i3037x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.off_hand()",),
)
def i3037x1(c: Cast) -> None:
    """Which hand a weapon is in cannot be asked -- `Gear` records what is
    held and not where -- so the bonus is laid for any wielder. The attack
    context carries `opportunity`, which is the half that is exact."""
    c.bonus(
        AC, c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
        when=_opportunity,
    )


@power(
    "i3050x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.underwater_penalty()",),
)
def i3050x1(c: Cast) -> None:
    """Waives a penalty for fighting underwater. `c.terrain("aquatic")`
    says where the fight is and nothing anywhere charges for it, so there
    is nothing yet to waive."""


@power(
    "i3050p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3050p1(c: Cast) -> None:
    """Two power bonuses do not add and the larger wins, which is exactly
    what the printed "or" means where both halves are true."""
    if c.terrain("aquatic"):
        c.bonus("attack", 2, kind="power", on=c.me, until=When.EONT, once=True)
    c.bonus(
        "attack", 5, kind="power", on=c.me, until=When.EONT, once=True,
        when=_against(c, "water", "aquatic"),
    )


@power(
    "i3057x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.heal_bonus()",),
)
def i3057x1(c: Cast) -> None:
    """Adds to the amount a healing power restores. Healing is not read
    through `Mods`, so there is no key to write a bonus under."""


@power(
    "i3099x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("ConditionApplied.power",),
)
def i3099x1(c: Cast) -> None:
    """`ConditionApplied` names the source and the condition and not the
    row that applied it, so "with a melee attack" cannot be asked -- an
    immobilisation from anything of the wielder's arms this."""

    def held(ev: ConditionApplied) -> None:
        if ev.source == c.me and ev.condition == Condition.IMMOBILIZED:
            c.grants_advantage(on=ev.target, until=When.EONT)

    c.watch(ConditionApplied, held, until=When.ENCOUNTER)


@power(
    "i3099p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    attack=Attack(CON, vs=FORT),
)
def i3099p1(c: Cast) -> None:
    """"Constitution + this weapon's enhancement bonus" is the header's
    ability with `c.strike(plus=)`, the one door for a flat add to a
    declared attack roll."""
    if c.strike(plus=c.enhancement):
        c.pull(3)


@power(
    "i3135x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(only_untyped=)",),
)
def i3135x1(c: Cast) -> None:
    """`c.deals` rewrites every weapon attack's type; the card rewrites
    only the untyped ones, so a fire blade in the other hand keeps its
    fire here and does not in print."""
    c.resist(3 + 2 * c.enhancement, DamageType.FIRE, on=c.me)
    c.deals(DamageType.COLD, on=c.me)


@power(
    "i3135p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
)
def i3135p1(c: Cast) -> None:
    """"The weapon's level + 3" is a flat number rather than an ability, so
    the roll is made in the body off the item's own declared level."""
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("1d10", dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "i3135p2",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def i3135p2(c: Cast) -> None:
    """A fire on the map is scenery, and putting one out is `c.douse`. The
    saving throw is named so it finds the burn rather than whatever else
    an ally happens to be carrying."""
    for fire in c.scenery("fire", within=5):
        c.douse(on=fire)
    for ally in c.within(5, side="ally"):
        c.save(on=ally, against="fire")


@power(
    "i3145x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3145x1(c: Cast) -> None:
    """Each wound is its own modifier, laid with `stacks=True` because the
    card says cumulative and two power bonuses would otherwise collapse to
    the largest. Striking somebody else ends the set, which is the printed
    way out of it."""
    plus = c.enhancement // 2
    if plus < 1:
        return
    flag = _once_a_turn(c)
    state: dict[str, Any] = {"foe": None, "mods": []}

    def wound(ev: Hit) -> None:
        if ev.attacker != c.me or flag["spent"]:
            return
        flag["spent"] = True
        if ev.target != state["foe"]:
            for eff in state["mods"]:
                c.world.effects.end(eff, "another enemy was struck")
            state["mods"] = []
            state["foe"] = ev.target
        state["mods"].append(
            c.bonus(
                "damage", plus, kind="power", on=c.me, until=When.ENCOUNTER,
                stacks=True, when=_aimed_at(ev.target),
            )
        )

    c.watch(Hit, wound, until=When.ENCOUNTER)


@power(
    "i3411x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonded()",),
)
def i3411x1(c: Cast) -> None:
    """The bonding, the scrying and the temporary hit points at the end of
    a rest all happen out of the fight; the wound that will not close is
    the one clause with a body. Who may use the weapon's powers is the
    bonded wielder, and nothing records a bond."""

    def hurt(ev: DamageApplied) -> None:
        if ev.source == c.me and ev.target != c.me:
            c.no_healing(on=ev.target, until=When.EOTNT)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER)


@power(
    "i3411p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3411p1(c: Cast) -> None:
    """Two of these weapons melt into one, which is a fact about the
    treasure and not about a fight. Deliberately inert."""
    c.note("i3411p1: two of these weapons meld into one, keeping the greater plus")


@power(
    "i3411p2",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    dropped=("by_class()",),
)
def i3411p2(c: Cast) -> None:
    """The extra [W] is laid as a one-shot damage modifier before the swing
    rather than dealt after it: `c.basic` rolls its own damage and there is
    no second packet to add to. "An arcane implement attack" is a class
    gate `c.grant_attack` cannot ask for."""
    foe = c.target
    if foe is None:
        return
    c.bonus("damage", 0, dice=c.w(), on=c.me, until=When.EOT, once=True)
    c.basic(on=foe)
    allies = c.within(10, side="ally")
    if allies:
        who = c.choose(allies, "who strikes after you")
        if who is not None:
            c.grant_attack(who, on=foe)


@power(
    "i3411p3",
    level=8,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    out_of_combat=True,
)
def i3411p3(c: Cast) -> None:
    """The weapon comes back to hand from a mile off. Nothing on the board
    is a mile away and nothing takes a weapon that far, so this is inert by
    choice rather than unfinished."""
    c.note("i3411p3: the weapon returns to the wielder's hand from up to a mile")


@power(
    "i3451p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def i3451p1(c: Cast) -> None:
    """The flight is granted for the turn and the charge then uses it:
    `c.charge_at` runs on whatever modes the creature has when it moves."""
    foe = c.target
    if foe is None:
        return
    c.mode("fly", c.enhancement, on=c.me, until=When.EOT)
    c.charge_at(foe)


@power(
    "i453x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.ignore_resistance()",),
)
def i453x1(c: Cast) -> None:
    """Damage that eats through resistance. `c.resist` grants one and
    `c.vulnerable` offsets one; neither bypasses what a creature has."""


@power(
    "i460x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i460x1(c: Cast) -> None:
    """The point is counted when the modifier is read, which is the moment
    the card means -- not when the property was armed."""
    c.bonus(
        "damage", 1, kind="item", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.points() >= 1,
    )


@power(
    "i556p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i556p1(c: Cast) -> None:
    """"Save ends both" is one effect with the ongoing damage hung on it,
    or the victim gets two throws and shakes off half of one sentence."""
    c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
    )


@power(
    "i678p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an adjacent enemy bloodies you with a melee attack",
    on=Trigger(Bloodied, about_me, "you are bloodied"),
    dropped=("Bloodied.source",),
)
def i678p1(c: Cast) -> None:
    """`Bloodied` names only its subject, so "by an adjacent enemy with a
    melee attack" cannot be asked and the dispatcher's own aim picks which
    enemy is answered. `c.run_at` is the printed "you must end your
    movement adjacent to that enemy"."""
    foe = c.target
    if foe is None:
        return
    c.basic(on=foe)
    if c.landed:
        c.push(5, on=foe)
        c.run_at(foe)


@power(
    "i692p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FEAR],
    trigger="you reduce an enemy to 0 hit points with this weapon",
    on=Trigger(Dropped, by_me, "you drop an enemy with this weapon"),
)
def i692p1(c: Cast) -> None:
    comp = c.companion()
    if comp is None:
        return
    for foe in c.within(1, of=comp, side="enemy"):
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "i820p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i820p1(c: Cast) -> None:
    """`partial=True` is the line the card draws: ordinary cover and
    concealment stop helping, total concealment and superior cover go on
    working, which is the second printed sentence."""
    foe = c.target
    if foe is None:
        return
    c.no_cover(on=foe, until=When.SAVE_ENDS, partial=True)
    if "shadow" in c.kinds_of(on=foe):
        c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)


@power(
    "i924x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.grants_advantage(when=)",),
)
def i924x1(c: Cast) -> None:
    """The weapon's invisibility has no reader; what it buys does. The
    grants are laid on the enemies standing there and taken back the moment
    a blow lands, which is what "until you successfully hit" means. The
    melee half cannot be gated -- combat advantage is a fact about the pair
    of creatures, not about the attack -- and an enemy that arrives later
    does not get one."""
    held = [c.grants_advantage(on=foe, until=When.ENCOUNTER) for foe in c.enemies()]

    def seen(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        for eff in held:
            if eff is not None:
                c.world.effects.end(eff, "the weapon became visible")

    c.watch(Hit, seen, until=When.ENCOUNTER, once=True)


@power(
    "i936p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i936p1(c: Cast) -> None:
    c.immobilized(until=When.SAVE_ENDS)
    if "fey" in c.kinds_of():
        c.damage("1d10")


@power(
    "i951x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i951x1(c: Cast) -> None:
    """`c.forces` is handed `how`, so the card's two kinds of shove are
    lengthened and a slide -- which this weapon does not grant -- is
    not."""
    c.forces(
        1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("how") in (Forced.PUSH, Forced.PULL),
    )


@power(
    "i951p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would pull or push a target with this weapon",
    on=Trigger(
        ForcedMove, _my_shove, "you would push or pull a target",
        window=Window.BEFORE,
    ),
)
def i951p1(c: Cast) -> None:
    """Declared in the interrupt window: `ForcedMove` is a `Decision`, so
    the printed shove can be refused and replaced, and by the reaction
    window the target has already gone."""
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is None:
        return
    squares = getattr(ev, "squares", 0)
    c.cancel()
    c.slide(squares, on=foe)


@power(
    "i997x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i997x1(c: Cast) -> None:
    """`durations` sums a `"save"` modifier on whoever is rolling, so this
    is an ordinary penalty, and `once=True` spends it on the first throw --
    which is the printed clause. `EffectApplied` is the event rather than
    `ConditionApplied`, because an effect that carries nothing but ongoing
    damage is still one a save can end."""

    def landed(ev: EffectApplied) -> None:
        if ev.source == c.me and ev.save_ends and ev.target != c.me:
            c.penalty("save", 2, on=ev.target, until=When.ENCOUNTER, once=True)

    c.watch(EffectApplied, landed, until=When.ENCOUNTER)


# -- level 9 ----------------------------------------------------------------


@power(
    "i1065x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1065x1(c: Cast) -> None:
    """`c.resist`'s gate is handed the damage context, which carries
    `source` -- so "damage dealt by demons" is a real gate rather than a
    flat resistance to everything."""
    c.resist(c.enhancement, on=c.me, when=_dealt_by(c, "demon"))


@power(
    "i1065p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you attack a demon with this weapon",
    on=Trigger(
        AttackDeclared, _struck_kind("demon"), "you attack a demon",
        window=Window.BEFORE,
    ),
    dropped=("c.ignore_resistance()",),
)
def i1065p1(c: Cast) -> None:
    """Declared in the `BEFORE` window so the modifier is in place for the
    roll it was used on, and `once=True` spends it there."""
    c.bonus("attack", 5, kind="power", on=c.me, until=When.EOT, once=True)


@power(
    "i1069p1",
    level=9,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit a demon with this weapon",
    on=Trigger(Hit, _struck_kind("demon"), "you hit a demon"),
    todo=("c.strip_resistance()",),
)
def i1069p1(c: Cast) -> None:
    """Takes a monster's variable resistance away for a round. `c.resist`
    grants one and `c.vulnerable` offsets one; neither removes what a
    creature already has."""


@power(
    "i1069p2",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1069p2(c: Cast) -> None:
    c.bonus(
        "attack", 5, kind="power", on=c.me, until=When.EONT, once=True,
        when=_against(c, "demon"),
    )


@power(
    "i1123x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1123x1(c: Cast) -> None:
    """Resistance to one named row: the damage context carries `power`, so
    the gate is the ref itself."""
    c.resist(10, on=c.me, when=lambda ctx: ctx.get("power") == "m43a4")


@power(
    "i1123p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.ignore_resistance()",),
)
def i1123p1(c: Cast) -> None:
    c.bonus(
        "attack", 5, kind="power", on=c.me, until=When.EOT, once=True,
        when=_against(c, "dragon"),
    )


@power(
    "i1185p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(STR, vs=REF),
)
def i1185p1(c: Cast) -> None:
    """1[W] and no ability modifier, as printed: the weapon's dice are the
    whole damage line."""
    if c.strike(plus=c.enhancement):
        c.damage(c.w())
        if "elemental" in c.kinds_of():
            c.blinded(until=When.SAVE_ENDS)


@power(
    "i1275x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.no_teleport()",),
)
def i1275x1(c: Cast) -> None:
    """Bars one way of moving and leaves the rest. `c.immobilized` stops
    everything and `c.rooted` stops the shift; neither is a teleport."""


@power(
    "i1419p1",
    level=9,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    dropped=("c.deals(revert=)",),
)
def i1419p1(c: Cast) -> None:
    """The way back -- "another free action returns the damage to normal"
    -- has no verb: `c.deals` lays a type on and only a duration takes it
    off again."""
    c.deals(DamageType.PSYCHIC, on=c.me)


@power(
    "i1419p2",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i1419p2(c: Cast) -> None:
    """Out of sight, unable to act and untargetable is `Condition.REMOVED`
    in one word, and the save puts the creature back where it stood."""
    c.condition(Condition.REMOVED, until=When.SAVE_ENDS)


@power(
    "i1616x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.teleport_bonus()",),
)
def i1616x1(c: Cast) -> None:
    """Lengthens every teleport the wielder makes. `c.teleport` takes the
    distance the row printed and nothing adds to it; the ritual half is
    out of the fight either way."""


@power(
    "i1616p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def i1616p1(c: Cast) -> None:
    c.teleport(5)


@power(
    "i1676x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1676x1(c: Cast) -> None:
    c.ignores_long_range(on=c.me, until=When.ENCOUNTER)


@power(
    "i1676p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss every target with an attack using this crossbow",
    on=Trigger(PowerResolved, _all_missed, "you missed with every shot"),
    dropped=("c.no_miss_effect()",),
)
def i1676p1(c: Cast) -> None:
    """`c.restore_use` is the "you don't expend the use" half. Suppressing
    what the missed power does on a miss is the other, and nothing reaches
    back into a use that has finished resolving."""
    ref = getattr(c.trigger, "power", "")
    if ref:
        c.restore_use(ref, on=c.me)


@power(
    "i1702p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.THUNDER],
    trigger="you deal damage using this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
    dropped=("DamageType.pair()",),
)
def i1702p1(c: Cast) -> None:
    """Declared on the `Hit` rather than on `DamageRolled`: the body of the
    attack rolls its damage after the hit is announced, so a one-shot
    modifier laid here is read by the roll it is meant for. Damage of two
    types at once cannot be said -- `DamageType` is one word."""
    c.bonus(
        "damage", 2 * c.enhancement, kind="item", on=c.me, until=When.EOT, once=True
    )


@power(
    "i1761x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.race()",),
)
def i1761x1(c: Cast) -> None:
    """The whole benefit is gated on the wielder's race, and nothing asks
    one: `c.kinds_of` reads a monster's type line and answers nothing at
    all for a character."""


@power(
    "i1761p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a damage roll and dislike the result",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
    dropped=("c.reroll_damage(dice=)",),
)
def i1761p1(c: Cast) -> None:
    """`c.reroll_damage` rolls the whole damage twice and keeps the better,
    which is the printed effect for a weapon whose damage is mostly [W];
    confining the reroll to the [W] dice and the critical dice is the part
    that cannot be said. Declared on the hit so the effect is standing when
    the damage is rolled -- afterwards is too late."""
    c.reroll_damage(on=c.me, until=When.EOT)


@power(
    "i1880x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("Weapon.silvered",),
)
def i1880x1(c: Cast) -> None:
    """Silver is a material a base weapon cannot record, so nothing reads
    it. The defence bonus gates on the attack context's `attacker`."""
    for d in _DEFENCES:
        c.bonus(
            d, 1, kind="item", on=c.me, until=When.ENCOUNTER,
            when=_swung_by(c, "shapechanger"),
        )


@power(
    "i1880p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with a melee attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
    dropped=("c.forbid(keyword=)",),
)
def i1880p1(c: Cast) -> None:
    """`c.forbid` takes one ref away and the card takes a keyword away, so
    the polymorph half is dropped and the daze lands."""
    c.dazed(until=When.SAVE_ENDS)


@power(
    "i2459x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.in_form()",),
)
def i2459x1(c: Cast) -> None:
    """"Not in its natural form" is a question about a creature that
    `c.form` can put into one and nothing can ask of."""


@power(
    "i2459p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    todo=("c.in_form()", "c.forbid(keyword=)"),
)
def i2459p1(c: Cast) -> None:
    """Both halves are missing: nothing ends a form from outside it, and
    nothing bars a keyword."""


@power(
    "i2498x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2498x1(c: Cast) -> None:
    """Hands and ammunition are both outside what the engine counts: a
    weapon is wielded or it is not, and nothing is ever reloaded. Inert by
    choice rather than unfinished."""
    c.note("i2498x1: fired by mental command, with no hands and no ammunition")


@power(
    "i2498p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def i2498p1(c: Cast) -> None:
    """Declared as a ranged attack with the weapon's own dice rather than
    routed through `c.basic(ranged=True)`, which looks for a ranged weapon
    in the wielder's hands: the crossbow is this item, and the base weapon
    the character is carrying may be anything."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "i2516x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2516x1(c: Cast) -> None:
    """Skill modifiers are read under `skill:<name>`. The deafening is a
    rider of the row's own rather than the `crit_damage` column, which
    carries numbers and not conditions."""
    c.bonus(
        "skill:diplomacy", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )

    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.condition(Condition.DEAFENED, until=When.EONT, on=ev.target)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2516p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2516p1(c: Cast) -> None:
    """A separate packet of thunder damage, so it carries its own type --
    unlike a bonus riding on somebody else's roll."""
    c.damage("1d6", dtype=DamageType.THUNDER)
    c.dazed(until=When.EONT)


@power(
    "i2531x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2531x1(c: Cast) -> None:
    """A fly speed is halved by granting the mode again at half what it
    was: `Movement.modes` is where it lives and nothing reduces one. The
    critical dice are rolled with `c.flat` -- `c.damage` maxes its dice on
    a critical, which would hand out 24 every time."""

    def struck(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        mv = c.world.get(ev.target, Movement)
        fly = mv.modes.get("fly", 0) if mv is not None else 0
        if fly <= 0:
            return
        c.mode("fly", fly // 2, on=ev.target, until=When.EONT)
        if ev.critical:
            c.flat(c.roll("2d12"), on=ev.target)

    c.watch(Hit, struck, until=When.ENCOUNTER)


@power(
    "i2531p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an airborne target using this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i2531p1(c: Cast) -> None:
    """`safe=True` is "takes no damage from the fall"; the card keeps the
    prone, so it is laid back on by hand."""
    foe = c.target
    if foe is None or c.height(on=foe) <= 0:
        return
    c.fall(10, on=foe, safe=True)
    c.prone(on=foe)


@power(
    "i2552x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2552x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2552p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    trigger="you hit an enemy with a charm power using this weapon",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.CHARM)), "you hit with a charm power"
    ),
    dropped=("by_class()",),
)
def i2552p1(c: Cast) -> None:
    """Two failed saves, each worse than the last, is `escalate` twice: the
    second hold carries the callback again so the third can be reached.
    "A bard charm power" is a class gate no predicate can ask."""
    foe = c.target
    if foe is None:
        return

    def worse(_eff: Effect) -> None:
        if c.is_(Condition.IMMOBILIZED, on=foe):
            c.unconscious(on=foe, until=When.SAVE_ENDS)
        else:
            c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=foe, escalate=worse
            )

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=foe, escalate=worse)


@power(
    "i2872p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2872p1(c: Cast) -> None:
    """The attack's whole payout is an answer to a yes-or-no question,
    which is knowledge and not a combat effect. Deliberately inert."""
    c.note("i2872p1: a hit answers one yes-or-no question the target knows")


@power(
    "i2964x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.crit_damage()",),
)
def i2964x1(c: Cast) -> None:
    """How much the critical rider paid out is a `Mod` rolled inside
    `resolve.deal_damage` and never announced, so healing "equal to the
    damage dealt by this weapon's critical property" has no number to
    read."""
    c.deals(DamageType.NECROTIC, on=c.me)


@power(
    "i2964p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2964p1(c: Cast) -> None:
    """The die is rolled once and spent twice, because "an equal amount" is
    the same number and not a second roll."""
    n = c.roll("1d8")
    c.flat(n, dtype=DamageType.NECROTIC)
    c.heal(n, on=c.me)


@power(
    "i3091x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.sleeping()",),
)
def i3091x1(c: Cast) -> None:
    """Nobody sleeps in a fight and nothing records that they might."""
    c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER)


@power(
    "i3091p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(5),
    target=SELF,
)
def i3091p1(c: Cast) -> None:
    """Being surprised is a condition, so ending it is `c.cure`. Written as
    a self row with the allies gathered in the body: aimed at each ally it
    would do nothing at all for a wielder standing alone, which is the one
    creature the card names first."""
    c.cure(Condition.SURPRISED, on=c.me)
    for ally in c.within(5, side="team"):
        c.cure(Condition.SURPRISED, on=ally)


@power(
    "i3148p1",
    level=9,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.retarget_defence()",),
)
def i3148p1(c: Cast) -> None:
    """Sending an attack at Reflex instead of AC cannot be said: the
    defence is read off the power's own `Attack` line before the roll."""


@power(
    "i3149x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.ignore_resistance()",),
)
def i3149x1(c: Cast) -> None:
    """"The DM chooses" is `c.choose`, which is the world's decider and is
    exactly who that is."""
    pick = c.choose(
        [
            DamageType.ACID,
            DamageType.COLD,
            DamageType.FIRE,
            DamageType.LIGHTNING,
            DamageType.POISON,
        ],
        "which damage type this weapon turns aside",
    )
    if pick is not None:
        c.resist(5, pick, on=c.me)


@power(
    "i3149p1",
    level=9,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3149p1(c: Cast) -> None:
    """The prone rides on the same attack, so it is a watch armed for the
    turn rather than a second line in this body -- the attack has not
    happened yet when the minor action is spent."""
    c.bonus(
        "damage", 3, kind="power", on=c.me, until=When.EOT, once=True,
        when=_against(c, "dragon"),
    )

    def down(ev: Hit) -> None:
        if (
            ev.attacker == c.me
            and "dragon" in c.kinds_of(on=ev.target)
            and c.may("knock the dragon prone")
        ):
            c.prone(on=ev.target)

    c.watch(Hit, down, until=When.EOT, once=True)


@power(
    "i3429x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3429x1(c: Cast) -> None:
    """Half the enhancement, so a +2 weapon slides 1 and a +1 weapon slides
    nobody -- the row arms nothing rather than rounding up."""
    squares = c.enhancement // 2
    if squares < 1:
        return
    flag = _once_a_turn(c)

    def zap(ev: Hit) -> None:
        if ev.attacker != c.me or flag["spent"]:
            return
        p = get(ev.power)
        if p is None or not ({Keyword.LIGHTNING, Keyword.THUNDER} & set(p.keywords)):
            return
        near = [w for w in c.within(1) if w != c.me]
        if not near:
            return
        flag["spent"] = True
        who = c.choose(near, "who the weapon shoves")
        if who is not None:
            c.slide(squares, on=who)

    c.watch(Hit, zap, until=When.ENCOUNTER)


@power(
    "i3429p1",
    level=9,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your second wind on your turn",
    on=Trigger(SecondWind, _my_second_wind, "you use your second wind"),
)
def i3429p1(c: Cast) -> None:
    """The defence bonus is gated on `opportunity`, which the attack
    context carries. It is held to the end of the turn rather than only
    for the flight: nothing brackets a move, and the printed line is about
    the attacks this one provokes."""
    far = c.speed_of()
    c.mode("fly", far, on=c.me, until=When.EOT)
    for d in _DEFENCES:
        c.bonus(
            d, c.enhancement, kind="power", on=c.me, until=When.EOT,
            when=_opportunity,
        )
    c.move(far, at="fly")


@power(
    "i3450p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    trigger="you hit a creature with a melee attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i3450p1(c: Cast) -> None:
    c.damage("1d6", dtype=DamageType.RADIANT)
    c.blinded(until=When.EONT)


@power(
    "i3485x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3485x1(c: Cast) -> None:
    """The ammunition clause has nothing to read it. The malfunction does:
    a natural 1 is on `AttackRolled`, the only event carrying the die
    rather than its verdict."""
    hurt = 2 * get(c.ref).level

    def fumble(ev: AttackRolled) -> None:
        if ev.attacker == c.me and ev.natural == 1:
            c.flat(hurt, dtype=DamageType.NECROTIC, on=c.me)
            c.dazed(on=c.me, until=When.SAVE_ENDS)

    c.watch(AttackRolled, fumble, until=When.ENCOUNTER)


@power(
    "i3485p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
)
def i3485p1(c: Cast) -> None:
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("2d8", dtype=DamageType.NECROTIC)
        c.stunned(until=When.EONT)


@power(
    "i3485p2",
    level=9,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
)
def i3485p2(c: Cast) -> None:
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("2d8", dtype=DamageType.FIRE)


@power(
    "i690x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i690x1(c: Cast) -> None:
    """"Miss all targets" is a fact about the whole use, and `PowerResolved`
    is the only event that carries every roll one made -- a `Miss` knows
    about one creature."""

    def whiffed(ev: PowerResolved) -> None:
        if not _all_missed(c.world, c.me, ev):
            return
        c.flat(5, on=c.me)
        c.bonus("damage", 0, dice="2d6", on=c.me, until=When.EONT, once=True)

    c.watch(PowerResolved, whiffed, until=When.ENCOUNTER)


@power(
    "i968x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.make_thrown()",),
)
def i968x1(c: Cast) -> None:
    """Gives a melee weapon the heavy thrown property and a range.
    `c.as_ranged` is the one-shot version and says "the next melee attack";
    a standing property of the weapon has no door."""


@power(
    "i968p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with a ranged weapon attack using this weapon",
    on=Trigger(Hit, both(by_me, by_ranged), "you hit with a ranged attack"),
)
def i968p1(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    c.prone(on=foe)
    for other in c.within(1, of=foe):
        if other != foe:
            c.prone(on=other)


@power(
    "i991x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(half=)",),
)
def i991x1(c: Cast) -> None:
    """Half of one blow being radiant and half not cannot be said: a hit
    carries one `DamageType`, and `c.deals` would make the whole swing
    radiant, which is strictly better than print against anything that
    resists it."""
    c.as_implement(on=c.me)


@power(
    "i991p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    todo=("Keyword.CHANNEL_DIVINITY",),
)
def i991p1(c: Cast) -> None:
    """Hands back a use of a group of rows the engine does not group:
    `c.restore_use` names one ref and nothing marks a row as belonging to
    channel divinity."""


# -- level 10 ---------------------------------------------------------------


@power(
    "i1051p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee weapon attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
    dropped=("c.in_action_point()",),
)
def i1051p1(c: Cast) -> None:
    """Whether the triggering swing was made with the extra action an
    action point bought is not on the `Hit`: `ActionPointSpent` says one
    was spent and nothing ties an attack to it."""
    c.ongoing(10)


@power(
    "i1184x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("by_class()",),
)
def i1184x1(c: Cast) -> None:
    """`DamageApplied.absorbed` is how much resistance or immunity ate,
    which is the printed condition exactly. Which class's power dealt it
    cannot be asked."""

    def blunted(ev: DamageApplied) -> None:
        if ev.source == c.me and ev.absorbed > 0:
            c.temp_hp(5, on=c.me)

    c.watch(DamageApplied, blunted, until=When.ENCOUNTER)


@power(
    "i1184p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with this dagger",
    on=Trigger(Hit, by_me, "you hit with this dagger"),
    todo=("c.strip_resistance()",),
)
def i1184p1(c: Cast) -> None:
    """Takes a resistance or an immunity away for the fight. `c.resist`
    grants one and `c.vulnerable` offsets one; neither removes."""


@power(
    "i1340x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1340x1(c: Cast) -> None:
    """`cf:rogue-scoundrel-f4` is declared, and it pays out through
    `features.strikers.extra_damage`, which adds `c.total("<the feature's
    ref> damage")` on top of its dice. That modifier key exists precisely
    so a build feature can raise the number -- the helper's own docstring
    says closing over the dice alone left nothing for one to reach -- so
    an item that raises it says the printed sentence exactly, and says it
    only on the hit the feature actually pays out on.

    Untyped: the card prints no word before "add".

    "With this weapon" is not a gate, which is this file's standing
    reading -- the damage context carries no weapon and the character
    holds the item for as long as the property is armed.
    """
    c.bonus(
        "cf:rogue-scoundrel-f4 damage", c.cha_mod,
        on=c.me, until=When.ENCOUNTER, kind="untyped",
    )


@power(
    "i1494x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.grants_in(when=)",),
)
def i1494x1(c: Cast) -> None:
    """An aura of one square is "while adjacent to you", and `c.grants_in`
    hangs the bonus on whoever stands in it. It takes no gate, so the
    bonus is to AC against everything rather than against opportunity
    attacks alone."""
    zone = c.aura(1, on=c.me, until=When.ENCOUNTER)
    c.grants_in(zone, AC, 2, side="ally", kind="untyped")


@power(
    "i1494p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an opportunity attack using this weapon",
    on=Trigger(
        Hit, both(by_me, by_opportunity), "you hit with an opportunity attack"
    ),
)
def i1494p1(c: Cast) -> None:
    """The augment is read back off how many points were spent on this
    row, and it replaces the daze rather than adding to it."""
    if c.points_spent(c.ref) >= 4:
        c.stunned(until=When.EONT)
    else:
        c.dazed(until=When.EONT)


@power(
    "i1536x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.counts_as_kind()",),
)
def i1536x1(c: Cast) -> None:
    """The increase is written as an increase: `c.resist` adds to whatever
    `Defences` already holds, so a wielder with no fire resistance is given
    none, which is the printed "if you have". Counting as a devil for
    somebody else's beneficial effect has no reader -- `c.kinds_of` is off
    the stat block and a character has no type line to add to."""
    d = c.world.get(c.me, Defences)
    if d is not None and d.resist.get(DamageType.FIRE, 0) > 0:
        c.resist(5, DamageType.FIRE, on=c.me)


@power(
    "i1536p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    trigger="you miss with an attack that targets AC",
    on=Trigger(Miss, by_me, "you miss with an attack"),
    dropped=("Miss.vs", "c.bonus(dtype=)"),
)
def i1536p1(c: Cast) -> None:
    """`Miss` carries the attacker, the target and the power and not the
    defence it went at, so "an attack that targets AC" cannot be asked.
    `c.grant_attack` takes a flat damage bonus and no type for it."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    devils = [a for a in c.within(1, of=foe, side="ally") if "devil" in c.kinds_of(on=a)]
    if not devils:
        return
    who = c.choose(devils, "which devil strikes")
    if who is not None:
        c.grant_attack(who, on=foe, damage_bonus=2 * c.enhancement)


@power(
    "i1737x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.double_damage()",),
)
def i1737x1(c: Cast) -> None:
    """Doubling a roll is not a modifier: `c.bonus` adds a number and
    `c.maximise` takes the top of the dice, and neither is twice."""


@power(
    "i1737p1",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING],
    dropped=("c.deals(revert=)",),
)
def i1737p1(c: Cast) -> None:
    c.deals(DamageType.LIGHTNING, on=c.me)


@power(
    "i2195p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    dropped=("c.alignment()",),
)
def i2195p1(c: Cast) -> None:
    """Alignment is not on a creature anywhere, so the longer daze the card
    gives against an evil target cannot be told from the shorter one."""
    c.dazed(until=When.EONT)


@power(
    "i2405x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2405x1(c: Cast) -> None:
    """A separate packet of fire, so it carries its own type; the scarring
    is flavour and has nothing to read it."""
    flag = _once_a_turn(c)

    def burn(ev: Hit) -> None:
        if ev.attacker != c.me or flag["spent"]:
            return
        flag["spent"] = True
        c.damage("1d6", dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, burn, until=When.ENCOUNTER)


@power(
    "i2405p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=NO_TARGET,
)
def i2405p1(c: Cast) -> None:
    """The printed shape is one square wide and five long, which is a line
    and not the blast the header has to declare, so the squares are taken
    from `c.line` between the wielder and the square struck. `c.terraform`
    is what sinks ground."""
    aim = c.origin
    if aim is None:
        return
    run = [sq for sq in c.line(c.here, aim) if sq != c.here][:5]
    for sq in run:
        c.terraform(sq, sink=2)
    for who in c.in_squares(run):
        if who != c.me and not c.save(on=who):
            c.fall(2, on=who)


@power(
    "i2730p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a ranged basic attack using this weapon",
    todo=("c.use_power()",),
)
def i2730p1(c: Cast) -> None:
    """Swaps a basic attack that is already happening for a different row
    of the wielder's. Nothing fires one power out of another's body, and
    `c.basic` is the basic attack rather than a chosen at-will."""


@power(
    "i3001x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3001x1(c: Cast) -> None:
    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(5, on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER)


@power(
    "i3001p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger="you hit an enemy with a melee weapon attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i3001p1(c: Cast) -> None:
    """"Save ends both" is one effect carrying both conditions."""
    c.condition(Condition.IMMOBILIZED, Condition.WEAKENED, until=When.SAVE_ENDS)


@power(
    "i3055x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("PowerUsed.result",),
)
def i3055x1(c: Cast) -> None:
    """The bonus is "equal to the result of the 1d6 roll" that m4421a6 made
    and `PowerUsed` carries no result, so the die is rolled again here --
    the same distribution and a different number."""
    c.as_implement(on=c.me)

    def racial(ev: PowerUsed) -> None:
        if ev.actor == c.me and ev.power == "m4421a6":
            c.bonus(
                "attack", c.roll("1d6"), kind="item", on=c.me, until=When.EONT,
                once=True,
            )

    c.watch(PowerUsed, racial, until=When.ENCOUNTER)


@power(
    "i3055p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i3055p1(c: Cast) -> None:
    """`c.on_attack` is "whenever that creature attacks", which is the
    printed trigger, and the dice are chosen once when the hold is laid."""
    foe = c.target
    if foe is None:
        return
    dice = "3d10" if "rakshasa" in c.kinds_of(on=foe) else "2d10"
    c.on_attack(lambda _ev: c.damage(dice, on=foe), by=foe, until=When.EONT)


@power(
    "i3096x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.extra_damage(applies=)",),
)
def i3096x1(c: Cast) -> None:
    """Lifts the once-a-turn latch on `cf:rogue-scoundrel-f4`.

    The feature is declared and its *size* is reachable -- `i1340x1` above
    raises it through the `"<ref> damage"` key. Its **latch** is not: a
    `paid` dict in `features.strikers.extra_damage`'s closure, keyed on
    the round and the initiative slot, with nothing to clear or bypass it.

    Paying a second helping from here instead would double up rather than
    guarantee one: on a critical the feature's own `Hit` watcher fires
    too, and if it has not yet paid this turn the rogue would collect
    twice. Which of the two watchers runs first is not ordered."""


@power(
    "i3134x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(only_untyped=)",),
)
def i3134x1(c: Cast) -> None:
    """`c.deals` rewrites every weapon attack's type where the card
    rewrites only the untyped ones. The splash is dealt flat: it is the
    weapon's own damage and not a rider on any roll."""
    c.resist(3 + 2 * c.enhancement, DamageType.FIRE, on=c.me)
    c.deals(DamageType.FIRE, on=c.me)
    splash = 5 + c.enhancement
    flag = _once_a_turn(c)

    def burst(ev: Dropped) -> None:
        if ev.source != c.me or flag["spent"]:
            return
        flag["spent"] = True
        for foe in c.within(1, of=ev.actor, side="enemy"):
            if foe != ev.actor:
                c.flat(splash, dtype=DamageType.FIRE, on=foe)

    c.watch(Dropped, burst, until=When.ENCOUNTER)


@power(
    "i3134p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
)
def i3134p1(c: Cast) -> None:
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("1d10", dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "i3142x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.alignment()", "c.is_minion()"),
)
def i3142x1(c: Cast) -> None:
    """Two of the three clauses have nothing to ask: alignment is not on a
    creature, and whether one is a minion is not either -- its one hit
    point is in the database and nothing says the word."""
    c.bonus(
        "damage", c.enhancement, kind="power", on=c.me, until=When.ENCOUNTER,
        when=_against(c, "undead"),
    )


@power(
    "i3142p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an undead creature with this weapon",
    on=Trigger(Hit, _struck_kind("undead"), "you hit an undead creature"),
)
def i3142p1(c: Cast) -> None:
    c.push(3)
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "i3412x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonded()",),
)
def i3412x1(c: Cast) -> None:
    """The bonding, the scrying and the temporary hit points at the end of
    a rest are all outside a fight, and nothing records a bond -- so the
    gate on who may use the weapon's powers is dropped."""
    c.resist(3 + 2 * c.enhancement, DamageType.PSYCHIC, on=c.me)


@power(
    "i3412p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3412p1(c: Cast) -> None:
    """Two of these weapons melt into one, which is a fact about the
    treasure and not about a fight. Deliberately inert."""
    c.note("i3412p1: two of these weapons meld into one, keeping the greater plus")


@power(
    "i3412p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    dropped=("by_class()",),
)
def i3412p2(c: Cast) -> None:
    """The extra [W] is laid before the swing: `c.basic` rolls its own
    damage and there is no second packet to add to. "An arcane implement
    attack" is a class gate `c.grant_attack` cannot ask for."""
    foe = c.target
    if foe is None:
        return
    c.bonus("damage", 0, dice=c.w(), on=c.me, until=When.EOT, once=True)
    c.basic(on=foe)
    allies = c.within(10, side="ally")
    if allies:
        who = c.choose(allies, "who strikes after you")
        if who is not None:
            c.grant_attack(who, on=foe)


@power(
    "i3412p3",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    out_of_combat=True,
)
def i3412p3(c: Cast) -> None:
    """The weapon comes back to hand from a mile off. Nothing on the board
    is a mile away, so this is inert by choice rather than unfinished."""
    c.note("i3412p3: the weapon returns to the wielder's hand from up to a mile")


@power(
    "i3510x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("Weapon.silvered", "c.ignore_insubstantial()"),
)
def i3510x1(c: Cast) -> None:
    """Both clauses are about what the weapon is made of. Silver has
    nowhere to be recorded, and `c.insubstantial` halves damage taken with
    nothing that pays it back."""


@power(
    "i3510p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def i3510p1(c: Cast) -> None:
    """"Each creature adjacent to your destination" is asked after the
    teleport, which is what makes the destination the destination."""
    c.teleport(5)
    for who in c.within(1):
        if who != c.me:
            c.flat(5, dtype=DamageType.RADIANT, on=who)


@power(
    "i3555x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonus(against=)", "c.immune_power()"),
)
def i3555x1(c: Cast) -> None:
    """The resistance gates on `source`, which the damage context carries.
    A skill check has no target, so an Intimidate bonus "against draconians
    and dragons" is laid for every check instead; and nothing makes a
    weapon proof against one named monster row."""
    c.resist(5, on=c.me, when=_dealt_by(c, "dragon", "draconian"))
    c.bonus(
        "skill:intimidate", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i3555p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    trigger="you hit a dragon or draconian with a melee attack using this weapon",
    on=Trigger(
        Hit, _struck_kind("dragon", "draconian"), "you hit a dragon or draconian"
    ),
)
def i3555p1(c: Cast) -> None:
    """"You do not expend this power" is `c.restore_use` on the row's own
    ref, asked after the damage because whether the target dropped is only
    knowable then."""
    foe = c.target
    if foe is None:
        return
    c.damage("3d12", dtype=DamageType.RADIANT)
    c.dazed(until=When.EONT)
    h = c.world.get(foe, Health)
    if h is not None and h.hp <= 0:
        c.restore_use(c.ref, on=c.me)


@power(
    "i3555p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit a dragon or draconian and the d20 roll is 15 or higher",
    on=Trigger(
        Hit, _struck_kind("dragon", "draconian"), "you hit a dragon or draconian"
    ),
    todo=("c.make_critical()",),
)
def i3555p2(c: Cast) -> None:
    """Turning a hit that has landed into a critical cannot be said: the
    crit is decided in `resolve.attack` off the die and nothing rewrites
    it afterwards."""


@power(
    "i553x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i553x1(c: Cast) -> None:
    for d in _DEFENCES:
        c.bonus(
            d, 1, kind="item", on=c.me, until=When.ENCOUNTER,
            when=_swung_by(c, "aberrant"),
        )


@power(
    "i553p1",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_weapon()",),
)
def i553p1(c: Cast) -> None:
    """Becomes a different base weapon, taking its dice, its reach and its
    group. The base item is a column and no body swaps it."""


@power(
    "i553p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with an attack using the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    dropped=("c.no_teleport()",),
)
def i553p2(c: Cast) -> None:
    c.dazed(until=When.EONT)
    if "aberrant" in c.kinds_of():
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "i662p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("When.CONSCIOUS",),
)
def i662p1(c: Cast) -> None:
    """"Until you fall unconscious" is not a duration the engine has, so
    the whole bargain runs to the end of the fight -- which is the longer
    half of the printed "or"."""
    c.bonus("attack", 2, kind="power", on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 2, kind="power", on=c.me, until=When.ENCOUNTER)
    for d in _DEFENCES:
        c.penalty(d, 5, on=c.me, until=When.ENCOUNTER)
    c.resist(5, on=c.me, until=When.ENCOUNTER)


@power(
    "i674x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i674x1(c: Cast) -> None:
    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.conceal(on=c.me, until=When.EONT)

    c.watch(Dropped, felled, until=When.ENCOUNTER)
