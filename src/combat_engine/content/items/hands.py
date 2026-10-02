"""Hands-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares an item. The level, the price and the slot are
columns in `game.db`; no hands item carries an enhancement bonus, so every
number below is the heroic one the card prints and a `Level 16:` line is
paragon and out of scope.

Four judgements run through the file.

* **The damage context is not as thin as this file used to say.** It
  carries `target`, `power`, `opportunity`, `charge`, `dtype`, `dtypes`,
  `crit`, `advantage`, `ranged`, `granted_by` and `granted_via`. It has no
  attacker -- the caster is `c.me`, which is who the modifier hangs on --
  and no reach of its own, so "melee attacks deal 2 extra" is still asked
  of `get(ctx["power"]).reach.kind`. "Against an enemy granting combat
  advantage to you" **is** askable, on `ctx["advantage"]`, with the
  engine's own caveat that a one-shot grant is already spent by the time
  damage is rolled.
* **Five items in this slot print the same elemental daily**: use it when
  you make an attack of some shape, that attack changes damage type and
  gains a rider, and every attack of that shape deals 1 extra for the rest
  of the fight. They share `_infusion` and `_on_next_hit`, and each drops
  `c.milestone()` -- nothing counts a day's milestones.
* **A skill modifier is real** and its context is `{actor, skill}` only,
  so "+2 to Athletics checks" is exact and "+2 to Athletics checks **to
  climb**" is the same flat modifier plus
  `narrative=("skill:athletics",)`. Not a `dropped=`: nothing on a board
  climbs, so the narrowing is not a gap waiting on a verb.
* **Stowing, drawing and applying a consumable are not modelled.** An
  alchemical item, a dose of poison and an item kept inside a glove have
  no engine object, so those rows carry markers rather than inventing one.
* **A race is asked for by one of its trait refs.** Nothing carries a
  creature's race, but a racial trait is an ordinary row in `Powers.known`
  and `c.feat(ref, on=)` reads that, so "your r3 allies" is exact where
  `c.is_kind` would have answered for every fey creature on the board.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.barbarian.rage import in_rage
from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    STR,
    WILL,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Forced,
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    PowerUsed,
    Ranged,
    Relation,
    SecondWind,
    TempHP,
    TotalDefence,
    Trigger,
    When,
    World,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    get,
    granted_via,
    power,
    query,
    targets_me,
)

ITEM = "item"

#: `cf:barbarian-f3` hands its free swing over with `c.basic`, which files
#: the feature's own ref under `granted_via` -- on the `Hit` and in the
#: damage context alike. That is what "attacks from your X class feature"
#: is a set of.
RAMPAGE = "cf:barbarian-f3"

#: One of r3's racial traits, which only an r3 character carries.
R3 = "rt:r3-trance"


# -- shared reading of the board --------------------------------------------


def _skills(c: Cast, value: int, *names: str, kind: str = "item") -> None:
    """Lay one item bonus per named skill. There is no key for a set."""
    for name in names:
        c.bonus(f"skill:{name}", value, on=c.me, until=When.ENCOUNTER, kind=kind)


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Gate on the keywords of the power in the context."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _reach_gate(*kinds: str) -> Callable[[dict[str, Any]], bool]:
    """"Melee attacks": the damage context has no reach, so the row's has
    to be read back off the power the context names."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and row.reach is not None and any(
            row.reach.kind.startswith(k) for k in kinds
        )

    return gate


def _defence_gate(defence: Any) -> Callable[[dict[str, Any]], bool]:
    """"An attack power that targets Will" -- which defence a row goes
    after is on the row, not in either context."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return (
            row is not None
            and row.attack is not None
            and row.attack.vs is defence
        )

    return gate


def _dtype_gate(*types: DamageType) -> Callable[[dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") in types

    return gate


def _is_thrown(weapon: Any) -> bool:
    """A thrown weapon, by the property the table prints.

    The word comes in two grades -- "light thrown" and "heavy thrown" --
    and no card in this slot distinguishes them.
    """
    return weapon is not None and any("thrown" in p for p in weapon.properties)


def _throwing(c: Cast) -> bool:
    """Is a ranged attack by this creature a *thrown* one?

    The same rule `Cast.weapon_of` uses, said with what a body can reach:
    a real ranged weapon is what a ranged power fires if one is in hand,
    and otherwise the thing being thrown is the thing being held. A bow
    answers False, a held dagger answers True.
    """
    held = c.held(on=c.me)
    fired = next((w for w in held if w.ranged), None)
    if fired is not None:
        return _is_thrown(fired)
    return any(_is_thrown(w) for w in held)


def _has_keyword(ref: str, *words: Keyword) -> bool:
    row = get(ref)
    return row is not None and any(w in row.keywords for w in words)


def _foe(c: Cast) -> int | None:
    """The other creature in whatever event this row is answering.

    **`target` is in the list and used not to be**, which made every row
    here that answers "when *you* hit" silently wrong: on a `Hit` of mine
    the attacker is me and is skipped, and with nothing left to read the
    fallback was `c.target` -- None on the `NO_TARGET` rows and the
    caster itself on the `SELF` one, so a row printing "make a basic
    attack against it" swung at its own bearer. Attacker first, so a row
    answering a blow aimed *at* the bearer still names the striker.
    """
    ev = c.trigger
    for name in ("attacker", "source", "actor", "target"):
        who = getattr(ev, name, None)
        if who is not None and who != c.me:
            return who
    return c.target


def _bloodied_by_a_foe(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "source", None)
    return (
        getattr(ev, "actor", None) == me
        and who is not None
        and query.team(world, who) is not query.team(world, me)
    )


def _grabbing(world: World, eid: int) -> list[int]:
    """What this creature is holding in a grab, for a `requires=` gate --
    which is handed `(world, eid)` and has no `Cast` to ask."""
    return world.relations.targets(Relation.GRABBED_BY, eid)


def _on_next_hit(c: Cast, fn: Callable[[Any], None]) -> None:
    """Answer the next blow this creature lands.

    `PowerUsed` fires *before* the body, so a row triggered on "when you
    make an attack" cannot know who it hit. The rider waits for the `Hit`
    instead, which is the same turn and the right creature."""

    def seen(ev: Hit) -> None:
        if ev.attacker == c.me:
            fn(ev)

    c.watch(Hit, seen, until=When.EOT, on=c.me, once=True)


def _infusion(c: Cast, dtype: DamageType,
              gate: Callable[[dict[str, Any]], bool],
              *, until: When = When.ENCOUNTER) -> None:
    """The half these five dailies share: the weapon deals the new type
    from now until the attack is over, and every later attack of the same
    shape deals 1 extra."""
    c.deals(dtype, on=c.me, until=When.EOT)
    c.bonus("damage", 1, on=c.me, until=until, when=gate)


# -- level 1 ----------------------------------------------------------------


@power("i824x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i824x1(c: Cast) -> None:
    _skills(c, 1, "thievery")


# -- level 2 ----------------------------------------------------------------


@power("i3098x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.grab_check()", "c.save_vs_forced()"))
def i3098x1(c: Cast) -> None:
    """The middle clause is the one that plays: `grab_defence` is read off
    the *grabber* when somebody rolls to get out, which is what "your
    defences when preventing an escape from your grab" means and is not
    the same as raising Reflex generally. A grab attack is an ordinary
    attack the engine does not label, and catching yourself on the way
    down is a saving throw nothing rolls."""
    c.bonus("grab_defence", 1, on=c.me, until=When.ENCOUNTER, kind="item")


# -- level 3 ----------------------------------------------------------------


@power("i1378x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1378x1(c: Cast) -> None:
    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not _has_keyword(ev.power, Keyword.ARCANE):
            return
        if c.marked(on=ev.target):
            c.temp_hp(2, on=c.me)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i1436p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.ignore_resistance(below=)",))
def i1436p1(c: Cast) -> None:
    """"Any resistance of 10 or lower" is a threshold and `amount=` is a
    cap, and the two part company above ten: this walks through resist 10
    entirely and shaves resist 15 down to 5, where the card leaves resist
    15 alone. Nothing at heroic tier has more than 10, so the rows differ
    only where the item never plays -- but they do differ, so the
    threshold is named rather than quietly called the same thing."""
    c.ignore_resistance(10, on=c.me, until=When.ENCOUNTER)


# -- level 4 ----------------------------------------------------------------


@power("i1313p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a light blade and have combat advantage",
       on=Trigger(Hit, by_me, "you hit a creature"),
       dropped=("c.effects_on()",))
def i1313p1(c: Cast) -> None:
    """"If the attack already deals ongoing damage of any type" cannot be
    asked: `c.suffering` only finds holds *this* caster laid, and
    `c.ongoing` enforces the rule for one type rather than for all."""
    ev = c.trigger
    foe = _foe(c)
    if foe is None or not c.wielding("light blade") or not c.had_advantage(ev):
        return
    c.ongoing(5, on=foe)


@power("i1379x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1379x1(c: Cast) -> None:
    """No type word on the card, so the bonus is untyped."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and c.bloodied(on=foe)

    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=gate)


@power("i1407p1", level=4, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=Ranged(6), target=ONE_CREATURE, attack=Attack(STR, vs=AC, plus=2))
def i1407p1(c: Cast) -> None:
    """The thrown object is flavour; what it does is the attack line."""
    if c.strike():
        c.damage("2d6", c.str_mod)


@power("i1407p2", level=4, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a melee attack",
       on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"))
def i1407p2(c: Cast) -> None:
    """`Hit` is announced before the damage is rolled, so a modifier laid
    here still reaches the roll it is meant to."""
    c.bonus("damage", 2, on=c.me, until=When.EOT, kind="power", once=True)


@power("i1532p1", level=4, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.ARCANE, Keyword.CONJURATION])
def i1532p1(c: Cast) -> None:
    """The whole block is "this row is that other row". p1227 is lent
    for the one use and not spent -- the item's use is the price."""
    c.use_power("p1227", spend=False)


@power("i1532p2", level=4, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ARCANE])
def i1532p2(c: Cast) -> None:
    """As above, with p1930."""
    c.use_power("p1930", spend=False)


@power("i2061p1", level=4, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2061p1(c: Cast) -> None:
    """Loading a dose into the gloves, which happens before a fight."""


@power("i2061p2", level=4, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.stored_dose()",))
def i2061p2(c: Cast) -> None:
    """Re-aimed. `c.apply_poison` coats a weapon now, but it coats it with
    a rider the row supplies -- and this row supplies none. What it
    applies is whatever dose i2061p1 loaded, and a dose of poison is not
    a thing the engine counts: the consumable that would be spent has no
    identity a second row can reach for."""


@power("i2673x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2673x1(c: Cast) -> None:
    """Handling animals, and no fight rolls Nature."""


@power("i2673p1", level=4, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you become bloodied from a melee attack",
       on=Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"),
       dropped=("Bloodied.power",))
def i2673p1(c: Cast) -> None:
    """`Bloodied.source` is the enemy that bloodied you, so the shove goes
    where the card puts it. "From a melee attack" is the dropped half --
    the event carries no attack, so the shape of the blow cannot be
    asked."""
    c.push(3, on=c.trigger.source)


@power("i2947x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2947x1(c: Cast) -> None:
    """A rage is a stance and `rage.in_rage` is the standing question the
    class already asks of it, so the marker here was naming something that
    had existed all along."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: in_rage(c))


@power("i2947p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def i2947p1(c: Cast) -> None:
    """The spec names the row, so the gate is the ref itself.

    The spec's `p4807` is declared nowhere; the card is declared under
    `cf:barbarian-f2c0`, the feature ref that prints it. Gated on the
    printed id this was false in every fight.
    """
    c.bonus("attack", 4, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "cf:barbarian-f2c0")


@power("i673p1", level=4, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       todo=("c.on_pact_boon()",))
def i673p1(c: Cast) -> None:
    """Nothing announces a pact boon, so the trigger cannot be declared
    and the teleport would never happen."""


@power("i893x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i893x1(c: Cast) -> None:
    """Both gates exist. `forms.in_beast_form` is the class's own reader,
    and the damage context does carry `advantage` -- with the engine's
    caveat that a *one-shot* grant is spent by the attack roll, so this
    pays on standing advantage and not on a grant used up to land the
    blow."""
    melee = _reach_gate("melee")

    def gate(ctx: dict[str, Any]) -> bool:
        return (
            in_beast_form(c.world, c.me)
            and bool(ctx.get("advantage"))
            and melee(ctx)
        )

    c.bonus("damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER,
            when=gate)


@power("i903x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.grant_weapon()",), narrative=("skill:athletics",))
def i903x1(c: Cast) -> None:
    """Two different absences. The blades are a real gap -- a weapon the
    wearer is proficient with changes what can be swung. Climbing is not:
    the flat athletics bonus is laid, and narrowing it to a climb would
    need a check nothing on a board ever calls for."""
    _skills(c, 1, "athletics")


# -- level 5 ----------------------------------------------------------------


@power("i1385x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ability_check()",))
def i1385x1(c: Cast) -> None:
    """A raw ability check is not a skill check and nothing rolls one."""
    _skills(c, 1, "athletics")


@power("i1385p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1385p1(c: Cast) -> None:
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="power",
            when=_reach_gate("melee"))


@power("i1427x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ability_check()",))
def i1427x1(c: Cast) -> None:
    _skills(c, 1, "acrobatics", "stealth")


@power("i1432p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i1432p1(c: Cast) -> None:
    """`c.save` follows the target, which is the ally, as printed."""
    c.save()


@power("i1437p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss an enemy with a melee attack power",
       on=Trigger(Miss, both(by_me, by_melee), "you miss with a melee attack"))
def i1437p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.basic(on=foe)


@power("i1743x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.roll_gate()",))
def i1743x1(c: Cast) -> None:
    """"When your attack roll is 20 or lower" is a condition on the die,
    and a modifier is decided before the die is read."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_defence_gate(FORT))


@power("i1895x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ability_check()",))
def i1895x1(c: Cast) -> None:
    _skills(c, 1, "athletics")


@power("i1895p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a melee attack",
       on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"))
def i1895p1(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.EOT, kind="power", once=True)


@power("i2018x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take the total defence or second wind action",
       on=[Trigger(SecondWind, about_me, "you take your second wind"),
           Trigger(TotalDefence, about_me, "you take the total defence action")])
def i2018x1(c: Cast) -> None:
    """Both printed actions, and the payout is the same either way.

    **The watch became two declared triggers.** It was a watch only because
    half the card could not be written: with total defence announcing itself
    there is nothing left for the body to arm, and a declared trigger is the
    right shape -- `triggers._ask` owns the window and the row stops having
    to re-arm itself every encounter. `Power.on` takes a sequence.
    """
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.SONT, kind="item")


@power("i2179x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2179x1(c: Cast) -> None:
    """Which defence a power goes after is on the row, so the damage half
    is exact; the illusion half waits for the blow to land."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            when=_defence_gate(WILL))

    def landed(ev: Hit) -> None:
        if ev.attacker == c.me and _has_keyword(ev.power, Keyword.ILLUSION):
            c.grants_advantage(on=ev.target, to=c.me, until=When.EONT)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i839x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i839x1(c: Cast) -> None:
    """Climbing. `movement.walk` charges no Athletics check in any mode, so
    there is no roll in a fight for this to reach."""


@power("i839p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("c.extend_move()",))
def i839p1(c: Cast) -> None:
    """Climbing at full speed is a movement mode at that speed; doubling
    climb movement somebody *else* grants has no verb."""
    c.mode("climb", c.speed_of(), on=c.me, until=When.ENCOUNTER)


# -- level 6 ----------------------------------------------------------------


@power("i1349x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1349x1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE, on=c.me)


@power("i1349p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE])
def i1349p1(c: Cast) -> None:
    """`c.bonus(dtype=)` carries the rider as its own typed part of the
    blow, which is what "1d6 extra *fire* damage" on a power of any type
    means: the six points meet fire resistance on their own terms and the
    power's own damage is left alone."""
    c.bonus("damage", 0, dice="1d6", dtype=DamageType.FIRE, on=c.me,
            until=When.EOT, once=True)


@power("i1459p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(STR, vs=FORT, plus=2),
       requires=lambda world, eid: bool(_grabbing(world, eid)),
       requires_text="must be holding a creature in a grab")
def i1459p1(c: Cast) -> None:
    """The grab is the entry requirement rather than a guard in the body,
    so a board with nobody held reports the row unusable instead of
    reporting one that fired and did nothing."""
    if c.strike():
        c.push(3)
        c.damage("2d10")
        c.prone()


@power("i1698x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.draw()",))
def i1698x1(c: Cast) -> None:
    """Drawing a weapon costs nothing in the first place, so there is no
    minor action for this to fold into a standard."""


@power("i1698p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a thrown weapon attack",
       on=Trigger(Hit, both(by_me, by_ranged), "you hit at range"))
def i1698p1(c: Cast) -> None:
    """`c.weapon_of` picks the weapon the triggering attack was actually
    made with, so "a thrown weapon attack" is exact and a bowshot is left
    out -- the event not carrying the weapon was never the whole story."""
    if not _is_thrown(c.weapon_of(c.trigger)):
        return
    c.bonus("damage", 5, on=c.me, until=When.EOT, kind="power", once=True)


@power("i1756p1", level=6, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_damage_dice()",))
def i1756p1(c: Cast) -> None:
    """`c.reroll_damage` rolls the whole expression again and keeps the
    higher; this rerolls one die and keeps the second result."""


@power("i2134x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2134x1(c: Cast) -> None:
    """The swing `cf:barbarian-f3` buys is announced by `c.basic`, which
    files the granting row's ref as `granted_via` -- in the damage context
    as well as on the event. So "attacks from your class feature" is a set
    a gate can test after all."""
    c.bonus("damage", 4, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: ctx.get("granted_via") == RAMPAGE)


@power("i2134p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an attack that uses that class feature",
       on=Trigger(Hit, both(by_me, granted_via(RAMPAGE)),
                  "you hit with the swing that feature bought"))
def i2134p1(c: Cast) -> None:
    """`Hit` is announced before the damage is rolled, so the extra dice
    laid here reach the roll they are printed for."""
    c.bonus("damage", 0, dice=c.w(2), on=c.me, until=When.EOT, once=True)


@power("i2168x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Healed.power",))
def i2168x1(c: Cast) -> None:
    """`Healed` says who healed whom and not which row did it, so "a power
    that allows a surge" and "an encounter or daily power" go unasked and
    every heal of mine on a construct pays out."""

    def healed(ev: Healed) -> None:
        if ev.source == c.me and ev.target != c.me and c.is_kind(
                "construct", on=ev.target):
            c.heal(c.roll("2d6"), on=ev.target)

    def temped(ev: TempHP) -> None:
        if ev.source == c.me and ev.target != c.me and c.is_kind(
                "construct", on=ev.target):
            c.temp_hp(c.roll("2d6"), on=ev.target)

    c.watch(Healed, healed, until=When.ENCOUNTER, on=c.me)
    c.watch(TempHP, temped, until=When.ENCOUNTER, on=c.me)


@power("i2452p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.NECROTIC],
       dropped=("c.next_attack_becomes()",))
def i2452p1(c: Cast) -> None:
    """`c.deals` changes what the *weapon* deals, which is the nearest
    thing to "the next arcane power you use deals necrotic" -- and it is
    only near: `Cast._typed` applies it to weapon powers alone, so an
    arcane implement power is untouched. The extra die carries the
    printed type on its own."""
    c.deals(DamageType.NECROTIC, on=c.me, until=When.EOT)
    c.bonus("damage", 0, dice="1d6", dtype=DamageType.NECROTIC, on=c.me,
            until=When.EOT, once=True)


@power("i3223x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3223x1(c: Cast) -> None:
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_dtype_gate(DamageType.NECROTIC))


@power("i3223p1", level=6, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you deal necrotic damage with an attack",
       on=Trigger(DamageApplied,
                  lambda world, me, ev: (
                      ev.source == me
                      and ev.dtype is DamageType.NECROTIC
                      and ev.target != me),
                  "you deal necrotic damage"))
def i3223p1(c: Cast) -> None:
    """"The gauntlets' level" is the item's own, which is this row's."""
    c.temp_hp(4 + get(c.ref).level, on=c.me)


@power("i476x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.alchemical()",))
def i476x1(c: Cast) -> None:
    """An alchemical item is not a thing the engine carries, so there is
    no attack of that shape to add to."""


@power("i806x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i806x1(c: Cast) -> None:
    """One point off any resistance an enemy has against your attacks,
    which is one point of ignore. The tier steps are out of scope."""
    c.ignore_resistance(1, on=c.me, until=When.ENCOUNTER)


@power("i806p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon attack, before you deal damage",
       on=Trigger(Hit, by_me, "you hit with a weapon attack"),
       dropped=("c.strip_resistance()",))
def i806p1(c: Cast) -> None:
    """Re-aimed, and now it plays. "Reduce the resistance the target has
    **against your attack**" is an ignore read off the attacker, and
    `c.ignore_resistance(when=)` is handed the damage context, so the
    five points are narrowed to the one creature.

    `c.resist(-5, on=foe)` is the other sentence and is not this one: it
    strips the resistance for everybody. A negative gated resist does
    nothing at all -- `deal_damage` clamps that term at zero.

    Dropped: the printed hold is "(save ends)" on the target, and an
    ignore lives on the attacker, where a save-ends clock would be the
    wrong creature rolling. It runs to the end of the turn instead, which
    is the attack the power is used for."""
    foe = _foe(c)
    if foe is None:
        return
    c.ignore_resistance(5, on=c.me, until=When.EOT,
                        when=lambda ctx: ctx.get("target") == foe)


@power("i825p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE],
       trigger="you make an attack with the fire keyword",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: (
                      ev.actor == me and _has_keyword(ev.power, Keyword.FIRE)),
                  "you make a fire attack"),
       dropped=("c.milestone()",))
def i825p1(c: Cast) -> None:
    """Nothing counts the day's milestones, so the larger of the two
    printed numbers is never the one that applies."""
    _infusion(c, DamageType.FIRE, _keyword_gate(Keyword.FIRE))
    _on_next_hit(c, lambda ev: c.ongoing(5, DamageType.FIRE, on=ev.target))


@power("i843p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ACID],
       trigger="you make a ranged attack",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: (
                      ev.actor == me
                      and (row := get(ev.power)) is not None
                      and row.reach is not None
                      and row.reach.kind == "ranged"),
                  "you make a ranged attack"),
       dropped=("c.milestone()",))
def i843p1(c: Cast) -> None:
    """"Hit or miss" is read off the targets the use announced, which are
    chosen before the body and are trustworthy on `PowerUsed`."""
    _infusion(c, DamageType.ACID,
              lambda ctx: bool(ctx.get("ranged")))
    for foe in getattr(c.trigger, "targets", []):
        for near in c.within(1, of=foe, side="enemy"):
            c.damage("1d6", dtype=DamageType.ACID, on=near)


@power("i1137p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1137p1(c: Cast) -> None:
    """`query.flanked_by` asks exactly this and has all along -- flanking
    is not buried inside `has_combat_advantage`.

    One modifier per creature on the team, gated on *both* the roller and
    the bearer flanking the creature being attacked. That is "you and the
    ally flanking with you" without having to know in advance which ally
    it will be; when the roller is the bearer the two halves collapse into
    one. Untyped, because the card prints "an additional +1 bonus" with no
    type word."""
    from combat_engine.engine import query

    me = c.me

    def gate(ctx: dict[str, Any]) -> bool:
        foe, roller = ctx.get("target"), ctx.get("attacker")
        return (
            foe is not None
            and roller is not None
            and query.flanked_by(c.world, foe, roller)
            and query.flanked_by(c.world, foe, me)
        )

    for mate in [me, *c.allies()]:
        c.bonus("attack", 1, on=mate, until=When.ENCOUNTER, when=gate)


# -- level 7 ----------------------------------------------------------------


@power("i1259x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1259x1(c: Cast) -> None:
    """Gaining combat advantage is the only thing this engine rolls a Bluff
    check for -- against a defender's passive Insight -- so the flat bonus
    is the printed one and the circumstance excludes nothing."""
    _skills(c, 2, "bluff")


@power("i1259p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1259p1(c: Cast) -> None:
    """One creature, chosen now, because "the next creature you attack"
    has no standing question and `once=True` spends the grant on use."""
    foe = c.choose(c.enemies(), "who to catch out")
    if foe is not None:
        c.grants_advantage(on=foe, to=c.me, until=When.EOT, once=True)


@power("i1362p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.COLD],
       trigger="you make a melee attack",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: (
                      ev.actor == me
                      and (row := get(ev.power)) is not None
                      and row.reach is not None
                      and row.reach.kind == "melee"),
                  "you make a melee attack"),
       dropped=("c.milestone()",))
def i1362p1(c: Cast) -> None:
    _infusion(c, DamageType.COLD, _reach_gate("melee"))
    _on_next_hit(c, lambda ev: c.slowed(on=ev.target, until=When.EONT))


@power("i1706x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1706x1(c: Cast) -> None:
    """`c.mount` is the standing question, so this needs no marker."""
    melee = _reach_gate("melee")
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.mount() is not None and melee(ctx))


@power("i2273p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, todo=("c.stabilise()",))
def i2273p1(c: Cast) -> None:
    """Stabilising a dying creature is not something the engine does, so
    the check that triggers this never happens."""


# -- level 8 ----------------------------------------------------------------


@power("i1388x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1388x1(c: Cast) -> None:
    """`c.forces`'s gate is handed `how`, so "any push effect you create"
    is exact and a pull or a slide is left alone."""
    c.forces(1, on=c.me, when=lambda ctx: ctx.get("how") is Forced.PUSH)


@power("i1431x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.curse_damage()",))
def i1431x1(c: Cast) -> None:
    """The curse's extra damage is rolled inside the curse and there is no
    hook that says what type it comes out as."""


@power("i1431p1", level=8, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ACID, Keyword.COLD, Keyword.FIRE],
       todo=("c.item_charges()",))
def i1431p1(c: Cast) -> None:
    """Every number in the row is priced in charges and an item keeps no
    charge pool."""


@power("i1440p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON],
       dropped=("c.next_attack_becomes()",))
def i1440p1(c: Cast) -> None:
    """As `i2452p1`: `c.deals` is the nearest thing to "the next arcane
    power you use deals poison", and the extra die at least lands as the
    printed type."""
    c.deals(DamageType.POISON, on=c.me, until=When.EOT)
    c.bonus("damage", 0, dice="1d6", dtype=DamageType.POISON, on=c.me,
            until=When.EOT, once=True)


@power("i1441x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1441x1(c: Cast) -> None:
    """Which rest a knocked-out creature wakes after is not a fight."""


@power("i1486x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.grab_check()", "c.ability_check()"))
def i1486x1(c: Cast) -> None:
    """The escape half is `escape` rather than the two skill keys: the
    card narrows it to getting out of a grab, and raising Athletics and
    Acrobatics outright would raise every climb and tumble too. The
    Strength check to grab is an ability check nothing rolls."""
    c.bonus("escape", 3, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i1560p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.RADIANT],
       trigger="you use a divine power",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: (
                      ev.actor == me and _has_keyword(ev.power, Keyword.DIVINE)),
                  "you use a divine power"),
       dropped=("c.milestone()",))
def i1560p1(c: Cast) -> None:
    _infusion(c, DamageType.RADIANT, _keyword_gate(Keyword.RADIANT))
    _on_next_hit(
        c, lambda ev: c.damage("1d6", dtype=DamageType.RADIANT, on=ev.target))


@power("i465x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i465x1(c: Cast) -> None:
    """A place to keep something the engine does not carry."""


@power("i465p1", level=8, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.alchemical()",))
def i465p1(c: Cast) -> None:
    """Spending an alchemical item on a weapon, with no such item."""


# -- level 9 ----------------------------------------------------------------


@power("i1010x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1010x1(c: Cast) -> None:
    """The spec names the racial power, so the trigger is exact.

    Nothing carries a creature's race, but a racial trait is an ordinary
    row in `Powers.known` and `c.feat(ref, on=)` reads that -- so holding
    one of r3's traits *is* being r3. `c.is_kind("fey")` was the tempting
    answer and is the wrong one: r3's origin word is shared with r4 and
    with every other fey creature on the board."""

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != "p1831":
            return
        for ally in c.allies():
            if c.feat(R3, on=ally) or c.is_kind("elf", on=ally):
                c.bonus("damage", 2, on=ally, until=When.EONT,
                        when=lambda ctx, foe=ev.target: ctx.get("target") == foe)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i1010p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1010p1(c: Cast) -> None:
    """Both halves have verbs now: `c.expend_row` spends one of the two
    named racial powers without casting it, and `c.use_power` fires the
    third. Either is acceptable payment, so the first the bearer still
    has is taken; if neither is left the block does nothing, which is
    the Requirement the card prints.

    The ally must be of the named kind and is not the bearer, so
    `side="ally"` rather than `"team"`."""
    if not any(c.is_kind("drow", on=a) for a in c.within(10, side="ally")):
        return
    for cost in ("p1450", "p1449"):
        if c.expend_row(cost):
            c.use_power("p1831", spend=False)
            return


@power("i1438p1", level=9, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i1438p1(c: Cast) -> None:
    """Putting an unattended object into a glove."""


@power("i1438p2", level=9, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1438p2(c: Cast) -> None:
    """Taking it back out again, ready to wield."""


@power("i1481p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=NO_TARGET, keywords=[Keyword.CONJURATION],
       dropped=("c.zone_condition()",))
def i1481p1(c: Cast) -> None:
    """A wall is raised and made difficult; `c.burns` gives a zone teeth
    but only damaging ones, so restraining whoever pushes through it is
    the clause with nowhere to go."""
    c.wall(8, difficult=True, until=When.EONT, sustain=MINOR)


@power("i1597x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1597x1(c: Cast) -> None:
    """`c.had_advantage` reads the advantage off the blow; asking the
    board again would be too late, since a one-shot grant is spent."""

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not _has_keyword(ev.power, Keyword.ILLUSION):
            return
        if c.had_advantage(ev):
            c.penalty("save", 2, on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=c.me)


@power("i1597p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with an illusion attack power",
       on=Trigger(Miss,
                  lambda world, me, ev: (
                      ev.attacker == me
                      and _has_keyword(ev.power, Keyword.ILLUSION)),
                  "you miss with an illusion power"))
def i1597p1(c: Cast) -> None:
    """"Must use the second result" is `keep="new"`."""
    c.reroll_attack(keep="new")


@power("i2573p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def i2573p1(c: Cast) -> None:
    """`Effects.sustaining` lists what this creature is keeping going and
    `Effects.sustain` keeps one going, both without an action being
    spent -- `actions._sustaining` is only the menu that offers them. So
    the row is two lines of `c.world`, which the older claim that
    "nothing sustains one from outside" had missed."""
    held = [
        e for e in c.world.effects.sustaining(c.me) if e.sustain_cost is MINOR
    ]
    if not held:
        return
    chosen = c.choose(held, "which effect to sustain")
    if chosen is not None:
        c.world.effects.sustain(chosen)


@power("i2732x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2732x1(c: Cast) -> None:
    """`partial=True` is exactly "but not superior cover"."""
    c.ignore_cover(on=c.me, until=When.ENCOUNTER, partial=True,
                   when=lambda ctx: bool(ctx.get("ranged")))


@power("i3221p1", level=9, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3221p1(c: Cast) -> None:
    """A hand that floats off and opens doors. The printed text rules out
    attacking with it, which leaves nothing a fight can see."""


@power("i3221p2", level=9, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       todo=("c.floating_object()",))
def i3221p2(c: Cast) -> None:
    """Swapping places with the floating gauntlet needs the gauntlet to be
    somewhere, and there is no object on the board to swap with."""


# -- level 10 ---------------------------------------------------------------


@power("i1151x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1151x1(c: Cast) -> None:
    """A thrown weapon is a *melee* weapon with a printed range --
    `chargen` deliberately leaves `Weapon.ranged` unset on one -- so the
    thing being thrown is what `c.wielding` answers for, and a bowshot is
    left out because a bow is not what is in hand to swing."""
    ranged = _reach_gate("ranged")
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: ranged(ctx) and _throwing(c))


@power("i1151p1", level=10, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE, attack=Attack(STR, vs=AC),
       dropped=("c.make_thrown()",))
def i1151p1(c: Cast) -> None:
    """Rolled here rather than through `c.basic(ranged=True)`, which asks
    for a ranged basic the wielder of a sword does not have -- the whole
    point of the row is that the melee weapon is the one being thrown.
    Making it *count* as a heavy thrown weapon is the missing half."""
    if c.strike():
        c.damage(c.w(), c.str_mod)


@power("i1380p1", level=10, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1380p1(c: Cast) -> None:
    """The block is "this row is that other row", and `c.use_power` is
    that. p1225 picks its own square, which is the whole of it; the
    printed "cast on the gauntlets" is where the hand comes from and
    the engine has no notion of an origin for a row with no area."""
    c.use_power("p1225", spend=False)


@power("i1380p2", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon attack",
       on=Trigger(Hit, by_me, "you hit with a weapon attack"))
def i1380p2(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.flat(10, dtype=DamageType.RADIANT, on=foe)


@power("i2691p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.THUNDER],
       trigger="you make a melee attack",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: (
                      ev.actor == me
                      and (row := get(ev.power)) is not None
                      and row.reach is not None
                      and row.reach.kind == "melee"),
                  "you make a melee attack"),
       dropped=("c.milestone()",))
def i2691p1(c: Cast) -> None:
    """The standing extra lasts to the end of the next turn here, not to
    the end of the encounter, which is what this one prints."""
    _infusion(c, DamageType.THUNDER, _reach_gate("melee"), until=When.EONT)
    _on_next_hit(
        c, lambda ev: c.damage("1d6", dtype=DamageType.THUNDER, on=ev.target))


@power("i2705x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2705x1(c: Cast) -> None:
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("i2705p1", level=10, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an adjacent enemy hits you",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you"))
def i2705p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None and c.adjacent(foe):
        c.basic(on=foe)


@power("i3332x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3332x1(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    c.mode("climb", half, on=c.me)
    c.mode("swim", half, on=c.me)


@power("i3460x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.basic_ability()",))
def i3460x1(c: Cast) -> None:
    """Which ability a basic attack swings with is fixed on the row it
    is, and nothing swaps one out for a turn."""


@power("i3460p1", level=10, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ACID],
       trigger="you are bloodied by a melee attack, or hit while bloodied",
       on=(Trigger(Bloodied, _bloodied_by_a_foe, "an enemy bloodies you"),
           Trigger(Hit, both(targets_me, by_melee),
                   "you are hit while bloodied")),
       dropped=("Bloodied.power",))
def i3460p1(c: Cast) -> None:
    """Two printed triggers, so two declared ones. `_foe` reads
    `Bloodied.source` on the first and the attacker on the second, so both
    pay out against the creature that struck. "By a melee attack" is
    dropped on the bloodying half only -- that event carries no attack."""
    foe = _foe(c)
    if foe is not None and foe != c.me:
        c.flat(get(c.ref).level // 2, dtype=DamageType.ACID, on=foe)


@power("i520x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.movement_tax()",))
def i520x1(c: Cast) -> None:
    """Difficult terrain is a property of a square, not of who is next to
    it, so "1 extra square to enter a square adjacent to you" has no
    shape the grid can hold."""


@power("i520p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE)
def i520p1(c: Cast) -> None:
    """A flat printed bonus, rolled in the body: `Attack(printed=)` would
    take the wearer's level term back out of a number that has none."""
    if c.attack(13, REF).hit:
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
