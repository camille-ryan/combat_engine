"""General feats, the tail of the list: channel divinity cards, the monk
and runepriest stragglers, the ritual categories, and a long run of racial
feats.

Four shapes account for most of this file.

**The ritual category.** Nine rows here (`f3704` through `f3713`) are a
ritual category and a skill substitution and nothing else. Those are
`out_of_combat=True` -- finished rows that deliberately do nothing -- and
not gaps. `f3708` is the exception: it also prints a bonus to initiative
checks, which is `c.initiative` and a real combat consequence, so that
one is an ordinary trait.

**The channel divinity pair.** Eight feats here print nothing but "you
gain the power `fNNNb`", and the card beside them is the work. The parent
is `c.grant_row`; the card carries `group=CHANNEL_DIVINITY`, which is
what the printed "only one of these per encounter" Special line means.

**Elemental companions.** `f3724` through `f3727b` all turn on a
companion creature with an active and a passive mode. The engine now has
companions -- a shaman's spirit, a ranger's beast, a familiar -- and this
is none of them: the creature is granted by the feat itself and its page
prints no defences, no hit points and no ref, so there is nothing to put
on the board. `c.elemental_companion()` is that gap and
`c.familiar_state()` is the mode, and the family is marked rather than
approximated. The ranger's beast, which these used to share a symbol
with, exists now.

**Weapon groups are a closed set**: axe, bow, crossbow, heavy blade,
implement, light blade, mace, spear, staff, unarmed. Sickles, scythes,
flails, tomes, wands, holy symbols, glaives and halberds are all printed
here and none of them is a group this engine carries, so a bonus narrowed
to one of them is `spec.weapon_ref()` or the named family constant --
`chargen.POLEARM`, `chargen.FLAIL`. Where the printed line names a group
the engine *does* have alongside one it does not -- crossbow and wand,
spear and flail -- the half that can be said is said and the other half
is `dropped`.

**A printed Trigger keeps a row out of the action menu**, and a triggered
`action=NONE` row spends a use every time it fires, so the standing
riders here are `AT_WILL` unless the card prints a limit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Ability,
    ActionType,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageType,
    Dropped,
    EffectApplied,
    Gear,
    Hit,
    Keyword,
    MoveEnd,
    PowerResolved,
    PowerUsed,
    SecondWind,
    SurgeSpent,
    Swap,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    World,
    about_me,
    distance,
    get,
    hits_me,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.query import has_combat_advantage, team


def _furious_on_p4807(world, me: int, ev) -> bool:  # noqa: ANN001
    """`p6189`, used in answer to a hit `p4807` landed.

    The pairing is the event the racial power was answering: it is a
    free action off a `Hit`, and `Hit` names the row that made it.
    """
    return (
        ev.actor == me
        and ev.power == "p6189"
        and getattr(getattr(ev, "trigger", None), "power", "") == "p4807"
    )

#: The monk's flurry, which the class page prints as a power and the
#: importer gave no ref. Four rows here trigger on it or add a use of it.
FLURRY = ("c.flurry_of_blows()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: The elemental companion, which is a creature the *feat* grants and the
#: importer never captured a stat block for: its page prints no defences,
#: no hit points and no ref, so there is nothing for `c.summon_inline` to
#: be handed. A ranger's beast is a different creature and now exists.
COMPANION = ("c.elemental_companion()",)
#: "Beast attack powers and beast form attack powers" is a druid keyword
#: and not a companion at all. The engine's keyword set is closed.
BEAST_KEYWORD = ("Keyword.BEAST",)
#: The animal companion a different class feature grants, whose printed
#: line is a *combined* attack -- one the character and the creature make
#: together. Nothing pairs two attacks that way.
COMBINED = ("c.combined_attack()",)
#: Active and passive mode, which only a familiar has.
MODE = ("c.familiar_state()",)
#: A printed weapon the engine has no group and no ref for.
WEAPON_REF = ("spec.weapon_ref()",)
#: Lengthening somebody else's printed shift.
EXTEND = ("c.extend_shift()",)


def _concealed_by(c: Cast, ref: str) -> bool:
    """Concealment laid by one named row, not concealment from anywhere.

    `query.concealment_of` answers the wide question. `c.conceal` is a
    modifier and `c.bonus` labels what it lays `"<ref> <key><amount>"`, so
    the one row's concealment is the effect on the caster whose label opens
    that way. The bare ref will not do: a row arms watches too, and those
    are effects carrying the ref as their whole label.
    """
    return any(
        eff.label.startswith(f"{ref} concealment")
        for eff in c.world.effects.of(c.me)
    )

#: The five the two spellscarred riders name.
ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)
#: What the engine's armour strings call the heavy band.
HEAVY = ("chain", "scale", "plate")
#: The two basic attacks, by the refs `engine/basic.py` declares them under.
BASICS = ("mba", "rba")

DIVINE = [Keyword.DIVINE]


# -- small shared questions -------------------------------------------------


def _gear(c: Cast) -> Gear | None:
    return c.world.get(c.me, Gear)


def _armour(c: Cast) -> str:
    gear = _gear(c)
    return gear.armour if gear is not None else ""


def _holding(c: Cast, *groups: str) -> bool:
    gear = _gear(c)
    return gear is not None and any(w.group in groups for w in gear.held)


def _holding_ref(c: Cast, *refs: str) -> bool:
    gear = _gear(c)
    return gear is not None and any(w.ref in refs for w in gear.held)


def _wielding_ref(*refs: str) -> Callable[[World, int], bool]:
    """`_holding_ref` as a `(world, eid)` predicate, which is what
    `c.rolls_with(when=)` takes.

    Asked on every roll rather than once when the feat armed, because the
    swap is laid at the start of the fight and a hand can be filled with
    something else later. The ranger's style feats have the same helper for
    the same reason -- `ranger_b._wields` -- gating on a weapon *group*; this
    one gates on the ref, because the monk's strike is the only member of its
    group today and a plain unarmed attack joining it later (#282) must not
    silently inherit the feat.
    """

    def holds(world: World, eid: int) -> bool:
        gear = world.get(eid, Gear)
        return bool(gear) and any(w.ref in refs for w in gear.melee)

    return holds


def _keyword(ref: str, word: Keyword) -> bool:
    p = get(ref)
    return p is not None and word in p.keywords


def _ally_dropped(squares: int):  # noqa: ANN202
    """An ally within `squares` drops a creature.

    `Dropped` carries `actor` -- the creature going down -- and `source`,
    whoever put it there. There is no `target`, and `by_me` would read the
    `source` and answer for the wrong half of the sentence.
    """

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        who = ev.source
        if who is None or who == me or team(world, who) is not team(world, me):
            return False
        return distance(_at(world, me), _at(world, who)) <= squares

    return when


def _at(world, eid: int):  # noqa: ANN001, ANN202
    from combat_engine.engine.components import Position

    pos = world.get(eid, Position)
    return pos.square if pos is not None else (0, 0)


def _grants_ca(c: Cast, who: int, until: When) -> None:
    """"The target grants combat advantage" -- to everyone, not to me.

    `c.grants_advantage` names one beneficiary at a time and `to="team"`
    means *my* side, which is the wrong side for a creature on it. One
    relation per enemy is what the printed sentence actually says.
    """
    for foe in c.enemies():
        c.grants_advantage(on=who, to=foe, until=until)


def _grants(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is the card beside it."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


# -- combat advantage, second wind and the first turn -----------------------


def _melee_or_ranged(ctx: dict[str, Any]) -> bool:
    """"Your melee and ranged attacks", read off the row that made them.

    The damage context carries no `ranged` flag, so the reach of the row
    is the only place to ask.
    """
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in ("melee", "ranged")


@power("f3684", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.effects_on()",))
def f3684(c: Cast) -> None:
    """Held on the enemy for its own save-ends duration rather than tied to
    the effect that earned it, because nothing reads back which holds a
    creature is carrying. Two saves instead of one: it can end early or
    late, and `c.effects_on()` is what would couple them.
    """

    # **The grant must not answer itself.** What this watches for is "a
    # save-ends effect from this character on somebody else", and the grant it
    # lays *is* one -- so it re-answered its own application until the
    # interpreter ran out of stack. Not a slow row: unbounded, 1000 frames
    # deep, and it took three unrelated rows down with it in the wide audit
    # (p180, p3667, p7099) for no more than applying ongoing damage while
    # somebody nearby held this feat. The grant's label is the one thing that
    # tells it apart, and `c.grants_advantage` writes a fixed one.
    mine = f"{c.ref} advantage"

    def granted(ev: Any) -> None:
        if ev.label == mine:
            return
        if ev.source == c.me and ev.save_ends and ev.target != c.me:
            c.grants_advantage(on=ev.target, to="team", until=When.SAVE_ENDS)

    c.watch(EffectApplied, granted, until=When.ENCOUNTER)


@power("f3685", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind on your turn",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3685(c: Cast) -> None:
    """"On your turn" is printed, and an ally's row can hand you a second
    wind off-turn, so the turn is asked."""
    if c.turn_of() != c.me:
        return
    for foe in [f for f in c.enemies() if c.can_see(f)][:2]:
        c.grants_advantage(on=foe, to=c.me, until=When.EONT)


@power("f3686", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.can_hear()",),
       trigger="you use your second wind on your turn",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3686(c: Cast) -> None:
    """Hearing is not modelled, so the ally is chosen from all of them."""
    if c.turn_of() != c.me:
        return
    mate = c.choose(c.allies())
    if mate is not None:
        c.shift(3, who=mate)


@power("f3688", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("SurgeSpent.healed",))
def f3688(c: Cast) -> None:
    """`resolve.spend_surge` is the only place a surge is decremented and
    it announces every one of them, so this fires for `c.spend_surge` --
    a surge spent for no hit points -- as well as for the healing kind the
    card names. `SurgeSpent` carries no way to tell them apart."""

    def spent(ev: Any) -> None:
        if ev.actor == c.me:
            c.bonus("attack", 1, on=c.me, until=When.EONT)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER)


@power("f3689", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3689(c: Cast) -> None:
    """The bonus is laid at the start of the first of *my* turns rather
    than when the trait is armed: a trait is armed before initiative, and
    `until=When.EOT` measured from there expires before the turn it is
    about. Heroic tier, so the extra damage is 2.
    """
    armed = False

    def mine(ev: Any) -> None:
        nonlocal armed
        if armed or ev.actor != c.me:
            return
        armed = True
        c.bonus("attack", 1, on=c.me, until=When.EOT, once=True,
                when=lambda ctx: _keyword(ctx.get("power", ""), Keyword.WEAPON))
        c.bonus("damage", 2, on=c.me, until=When.EOT, once=True)

    c.watch(TurnStart, mine, until=When.ENCOUNTER)


# -- channel divinity: the drop-triggered pair ------------------------------


f3690 = _grants("f3690", "f3690b")


@power("f3690b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(3), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="an ally within 3 squares of you drops a creature",
       on=Trigger(Dropped, _ally_dropped(3), "an ally drops a creature"))
def f3690b(c: Cast) -> None:
    """"Charge or make a basic attack" is one grant either way --
    `c.grant_attack` hands the ally its own basic and the policy picks the
    victim, and a charge differs only in how it gets there."""
    friend = c.trigger.source
    c.grant_attack(friend)
    _grants_ca(c, friend, When.EOTNT)


f3691 = _grants("f3691", "f3691b")


@power("f3691b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=CloseBurst(3),
       target=ONE_ALLY, keywords=[Keyword.DIVINE, Keyword.HEALING,
                                  Keyword.TELEPORTATION],
       group=CHANNEL_DIVINITY,
       trigger="an enemy hits you with an attack",
       on=Trigger(Hit, hits_me, "an enemy hits you"))
def f3691b(c: Cast) -> None:
    """The swap has to happen before the redirect, because `c.redirect`
    moves the live result onto whoever is standing in the blow -- and the
    printed order is that the ally arrives in your square first.

    "You or one ally adjacent to you (other than the target)" -- the
    caster is the one the policy can answer for, so the surge is offered
    to the caster.
    """
    ally = c.target
    c.swap(ally)
    c.redirect(to=ally)
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


f3692 = _grants("f3692", "f3692b")


@power("f3692b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="an enemy hits you with an attack",
       on=Trigger(Hit, hits_me, "an enemy hits you"))
def f3692b(c: Cast) -> None:
    """Heroic tier, so 2 extra damage. The rider is a watch rather than a
    `c.vulnerable`, because it is "each time you or an ally hits" -- a
    thing that happens on the blow, not a property of the creature, and
    vulnerability would pay out for a hit by anybody at all."""
    foe = c.trigger.attacker
    c.shift(3)
    friends = {c.me, *c.allies()}

    def struck(ev: Any) -> None:
        if ev.target == foe and ev.attacker in friends:
            c.flat(2, on=foe)

    c.watch(Hit, struck, until=When.EONT)


f3693 = _grants("f3693", "f3693b")


def _melee_hit_adjacent(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.triggers import by_melee

    return (
        ev.attacker == me
        and by_melee(world, me, ev)
        and distance(_at(world, me), _at(world, ev.target)) <= 1
    )


@power("f3693b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you hit an adjacent enemy with a melee attack",
       on=Trigger(Hit, _melee_hit_adjacent, "you hit an adjacent enemy"))
def f3693b(c: Cast) -> None:
    """The escape clause is a hold the creature buys its way out of:
    `c.endable` puts the free action on the target's own menu, because
    the hold sits on the target, and `then=` is the five damage it costs
    to take it. Heroic number only -- the two tiers above are out of
    scope."""
    foe = c.trigger.target
    c.endable(
        c.immobilized(on=foe, until=When.SAVE_ENDS),
        ActionType.FREE,
        then=lambda: c.flat(5, on=foe),
    )


@power("f3695", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.retarget()", "c.flat(unpreventable=)"))
def f3695(c: Cast) -> None:
    """Heroic tier, so +2. The interrupt half moves an attack that has
    been *declared* onto a different creature, which is a retarget rather
    than the `c.redirect` an interrupt row does with its own trigger --
    and the 5 damage that buys it "cannot be reduced in any way", which
    `c.flat` has no way to promise."""
    c.bonus(WILL, 2, kind="feat", on=c.me, until=When.ENCOUNTER)


f3696 = _grants("f3696", "f3696b")


@power("f3696b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(5), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="an ally within 5 squares of you drops a creature",
       on=Trigger(Dropped, _ally_dropped(5), "an ally drops a creature"))
def f3696b(c: Cast) -> None:
    """"A creature granting combat advantage to him or her" cannot be
    asked once it is down: `query.enemies` filters out the dead and the
    grant went with the creature. Heroic tier, so 5 temporary hit points.

    `c.conceal` with `total` left off is the printed partial kind, and
    `When.EOTNT` is "his or her next turn" -- the ally's, not mine.
    """
    friend = c.trigger.source
    c.temp_hp(5, on=friend)
    c.conceal(on=friend, until=When.EOTNT)


# -- monk -------------------------------------------------------------------


@power("f3697", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FLURRY)
def f3697(c: Cast) -> None:
    """A second use of the monk's flurry in a turn the action point
    bought. The prerequisite resolves `cf:monk-f1` -- the unarmed strike
    -- but the flurry itself is neither that row nor any other: it is a
    power the class page prints and the importer never gave a ref, which
    is the same hold five item rows carry."""


@power("f3698", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=FLURRY)
def f3698(c: Cast) -> None:
    """Dexterity in place of Strength on a basic attack made with the monk's
    strike. The flurry the second sentence retriggers is still not a row.

    `mba` is the ref to swap, not the monk's weapon: the card says "when
    making a melee basic attack **with** your monk unarmed strike", so the
    row being rolled is the basic attack and the strike is the gate on it.
    Gated with `when=` rather than checked once, because the swap is laid
    when the feat arms and a hand can be filled later.

    **`todo` became `dropped`**: the row plays, with one of its two
    sentences missing.

    Only the attack half of "attack rolls and damage rolls" lands.
    `Attack.ability_for` reads the swap, so the roll is right; `mba`'s damage
    names its modifier in its own body and is not this row's to rewrite.
    """
    c.rolls_with("mba", Ability.DEX, when=_wielding_ref("w:monk-unarmed-strike"))


@power("f3699", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("spec.weapon_ref()",), proficiency=("w:ki-focus",))
def f3699(c: Cast) -> None:
    """The ki focus is header data `chargen` reads at build time and the
    training is not a fight. The feature it hands over is `cf:monk-f1`,
    which is declared -- and declared `todo` itself, because the feature
    *is* a weapon and `w:unarmed`'s off-hand property and free-hand
    requirement are fields on a weapon row nothing declares. Granting
    that row here would hand over a card refused in play, so the gap this
    waits on is the one `cf:monk-f1` waits on."""


@power("f3700", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(group=)",))
def f3700(c: Cast) -> None:
    """The whole benefit is one weapon counting as another group -- unarmed
    read as a light blade -- for the rows that ask which group is in hand.
    """


@power("f3701", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.cover_from()", *FLURRY))
def f3701(c: Cast) -> None:
    """Partial cover against one sort of attack and not another is a
    narrowing `c.no_cover`'s mirror does not have, and the trigger is the
    flurry, which has no ref."""


@power("f3702", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*FLURRY, "spec.weapon_ref()"))
def f3702(c: Cast) -> None:
    """A sickle is not one of the ten weapon groups and the spec gives no
    ref for it, so "while you are wielding a sickle" cannot be asked --
    and the power it would change the outcome of has no ref either."""


# -- runepriest -------------------------------------------------------------


@power("f3703", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:glaive", "w:halberd"))
def f3703(c: Cast) -> None:
    """Both halves. Polearm is a printed group the weapon table carries
    and `chargen` now deals, so the slide has something to hang on. It
    rides on a `Hit` rather than a declared trigger because a row with a
    printed Trigger is kept out of the action menu, and this one has no
    per-fight limit to spend."""
    me = c.me

    def struck(ev: Any) -> None:
        row = get(ev.power)
        if (
            ev.attacker == me
            and row is not None
            and row.usage.name == "AT_WILL"
            and _holding(c, "polearm")
        ):
            c.slide(1, on=ev.target)

    c.watch(Hit, struck, until=When.ENCOUNTER)


@power("f3704", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3704(c: Cast) -> None:
    """Ritual mastery and scroll scribing. No combat consequence at all."""


# -- the ritual categories --------------------------------------------------


@power("f3705", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3705(c: Cast) -> None:
    """Skill substitution when talking to things, and a binding ritual."""


@power("f3706", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3706(c: Cast) -> None:
    """Performing rituals faster, and making alchemical items."""


@power("f3707", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3707(c: Cast) -> None:
    """A Bluff bonus and a deception ritual's components."""


@power("f3708", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3708(c: Cast) -> None:
    """The one in this run with a combat half. `c.bonus("initiative", ...)`
    is read by nothing -- `c.initiative` is the only door to the order --
    and the divination clauses beside it are ritual mastery, which is
    not a dropped clause but a thing outside a fight entirely."""
    c.initiative(2, on=c.me)


@power("f3709", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3709(c: Cast) -> None:
    """Substituting a knowledge skill for Endurance, out of a fight."""


@power("f3710", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.heal_check()",))
def f3710(c: Cast) -> None:
    """Re-aimed twice over. `events.SkillCheck` exists and is declarable,
    so "when you succeed on a check" is not the gap; `c.second_wind` is
    the one door to a second wind and already lays the defence bonus the
    first clause is about, so `c.grant_action('second wind')` is not it
    either.

    What is missing is the Heal check as an action in a fight: nothing
    offers one, so no `SkillCheck` with that skill is ever announced, and
    the event names an `actor` and no patient -- the same absence `f1390`
    and `i650x1` carry."""


@power("f3711", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3711(c: Cast) -> None:
    """Scrying rituals and the DC to notice a sensor."""


@power("f3712", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3712(c: Cast) -> None:
    """Travel rituals and overland speed."""


@power("f3713", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3713(c: Cast) -> None:
    """Finding and disabling traps, and warding rituals."""


# -- the elemental line -----------------------------------------------------


@power("f3716", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3716(c: Cast) -> None:
    """Two skill bonuses and a language."""


@power("f3718", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3718(c: Cast) -> None:
    """Two triggers for one payout. `Bloodied` carries `actor` and nothing
    else, and being knocked unconscious arrives as a `ConditionApplied`,
    whose subject is `target` -- `about_me` is false on that one forever.
    """

    def burn(_ev: Any) -> None:
        near = [e for e in c.enemies() if c.distance(e) <= 2]
        if not near:
            return
        victim = c.choose(near, "who takes the fire")
        if victim is not None:
            c.flat(c.con_mod, dtype=DamageType.FIRE, on=victim)

    def bloodied(ev: Any) -> None:
        if ev.actor == c.me:
            burn(ev)

    def out(ev: Any) -> None:
        if ev.target == c.me and ev.condition is Condition.UNCONSCIOUS:
            burn(ev)

    c.watch(Bloodied, bloodied, until=When.ENCOUNTER, once=True)
    c.watch(ConditionApplied, out, until=When.ENCOUNTER)


@power("f3719", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.surface()",))
def f3719(c: Cast) -> None:
    """What the square is made of is not recorded anywhere: `c.terrain`
    asks about the fight, not about the ground under one creature."""


@power("f3720", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3720(c: Cast) -> None:
    """"Your next saving throw" is `once=True` on a bonus that lasts the
    encounter: the modifier is read by `durations` when a save is rolled
    and spent by the first one."""

    def hurt(ev: Any) -> None:
        if (
            ev.target == c.me
            and ev.dtype in ELEMENTS
            and ev.source is not None
            and ev.source != c.me
            and team(c.world, ev.source) is not team(c.world, c.me)
        ):
            c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, once=True)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER)


@power("f3721", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3721(c: Cast) -> None:
    """All three halves. "You count as having the aquatic keyword" is a
    type word laid on the creature, and `c.set_origin` is where a word a
    character's row cannot carry is written: `c.kinds_of` reads it back
    for character and monster alike, which is what `c.is_kind("aquatic")`
    asks below.

    The bonus is gated rather than skipped outside water because
    `c.terrain` is a fact about the fight and is true or false for all of
    it -- so asking once, when the trait is armed, is the same answer.
    """
    c.mode("swim", c.speed_of(), on=c.me, until=When.ENCOUNTER)
    c.set_origin("aquatic", on=c.me, until=When.ENCOUNTER)
    if c.terrain("aquatic"):
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: not c.is_kind("aquatic", ctx.get("target")),
        )


@power("f3722", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ignores_difficult(when=)",))
def f3722(c: Cast) -> None:
    """`c.ignores_difficult` is a standing fact about the creature with
    nowhere to hang "but only while charging or running", so this is
    strictly wider than print: it ignores rough ground on an ordinary
    walk too. The armour half is a fact about what is worn and is asked
    when the trait is armed."""
    if _armour(c) not in HEAVY:
        c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power("f3724", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*COMPANION, *MODE))
def f3724(c: Cast) -> None:
    """The companion itself. `c.summon` needs a ref for the creature and
    the spec gives the feat's own id, which is not one."""


@power("f3725", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=MODE, swap=Swap(2, utility=True))
def f3725(c: Cast) -> None:
    """A utility power traded away at build time, and a skill bonus that
    depends on the companion's mode."""


@power("f3725b", level=1, cls="", usage=DAILY, action=MOVE,
       reach=CloseBurst(10), target=SELF, keywords=[Keyword.TELEPORTATION],
       todo=COMPANION)
def f3725b(c: Cast) -> None:
    """Swap places with the companion. Printed Daily, but there is no
    companion on the board to swap with."""


@power("f3726", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*COMPANION, *MODE))
def f3726(c: Cast) -> None:
    """A surge pays out to everyone standing next to the companion."""


@power("f3727", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=MODE, swap=Swap(6, utility=True))
def f3727(c: Cast) -> None:
    """A power swap and an attack bonus measured from the companion."""


@power("f3727b", level=1, cls="", usage=DAILY,
       action=ActionType.IMMEDIATE_REACTION, reach=CloseBurst(1),
       target=NO_TARGET, todo=COMPANION)
def f3727b(c: Cast) -> None:
    """Triggered by the companion being destroyed, and centred on the
    square it last occupied. Both halves are the companion."""


@power("f3729", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3729(c: Cast) -> None:
    """`c.resist` adds to whatever is already stored for the type, which
    is exactly the printed "if you already have fire resistance, it
    instead increases by 5" -- so one call says both sentences. Heroic
    tier, so 5.

    A watcher rather than a declared trigger: the resistance has to be
    standing from the start of the fight, and a triggered row is not armed
    until its trigger fires. The extra die is fire and carries that type
    of its own."""
    me = c.me
    c.resist(5, DamageType.FIRE, on=me, until=When.ENCOUNTER)

    def winded(ev: SecondWind) -> None:
        if ev.actor != me:
            return
        c.bonus("damage", 0, dice="1d6", on=me, until=When.EONT,
                when=_melee_or_ranged, dtype=DamageType.FIRE)

    c.watch(SecondWind, winded, on=me, until=When.ENCOUNTER)


@power("f3733", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3733(c: Cast) -> None:
    """The damage half of the same spellscarred pair as `f3720`."""

    def hurt(ev: Any) -> None:
        if (
            ev.target == c.me
            and ev.dtype in ELEMENTS
            and ev.source is not None
            and ev.source != c.me
            and team(c.world, ev.source) is not team(c.world, c.me)
        ):
            c.bonus("damage", 2, on=c.me, until=When.EONT)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER)


# -- implement and weapon accuracy ------------------------------------------


@power("f3736", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*WEAPON_REF, "Defences.immune_keywords"))
def f3736(c: Cast) -> None:
    """A tome is one implement among many and the engine's only implement
    group is "implement", so the accuracy half cannot be narrowed to it.

    The conjuration half is re-laid at the start of each of my turns
    rather than once: a conjuration put down on round three has to start
    granting then, and enemies walk in and out of the ring.

    "Immune to fear is immune to this" is re-aimed: `query.immune_to`
    exists and answers for a `Condition`, and fear is a `Keyword` with no
    condition to stand for it, so the gap is keyword immunity on the
    creature and not a reader.
    """

    def ring(ev: Any) -> None:
        if ev.actor != c.me:
            return
        things = [*c.my_zones(), *c.servants()]
        for foe in c.enemies():
            if any(c.adjacent_to(thing, foe) for thing in things):
                c.grants_advantage(on=foe, to="team", until=When.EONT)

    c.watch(TurnStart, ring, until=When.ENCOUNTER)


@power("f3738", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:orb", "w:rod", "w:staff", "w:wand"))
def f3738(c: Cast) -> None:
    """Heroic tier, so +1. "Any weapon or implement with which you have
    proficiency" is everything the creature can actually swing, so the
    gate is on the power rather than on the gear: arcane, or one of the
    two basic attacks."""

    def arcane_or_basic(ctx: dict[str, Any]) -> bool:
        ref = ctx.get("power", "")
        return ref in BASICS or _keyword(ref, Keyword.ARCANE)

    c.bonus("attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=arcane_or_basic)


@power("f3739", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*WEAPON_REF, "c.reload()"))
def f3739(c: Cast) -> None:
    """Crossbow is a group; a wand is not. Drawing, stowing and loading
    are gear handling the engine does not spend actions on, so the free
    actions the card grants have nothing to make cheaper."""
    c.bonus("attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "crossbow"))


@power("f3740", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3740(c: Cast) -> None:
    """"Any weapon with which you have proficiency, and a wand or another
    bard implement" is everything in hand, so the accuracy half is
    ungated. The forced-movement half is `c.forces`, which takes the
    gate the damage side does not."""
    c.bonus("attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.forces(1, on=c.me, until=When.ENCOUNTER,
             when=lambda ctx: _cls_of(ctx.get("power", "")) == "bard")


def _cls_of(ref: str) -> str:
    p = get(ref)
    return p.cls if p is not None else ""


def _one_handed_melee(c: Cast) -> bool:
    gear = _gear(c)
    if gear is None:
        return False
    return any(not w.two_handed and not w.ranged for w in gear.held)


@power("f3741", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=WEAPON_REF)
def f3741(c: Cast) -> None:
    """The shield half is a bonus laid on everybody else and typed
    `shield`, so a second source of one does not stack with it -- which
    is the printed rule and the reason the word matters.

    A holy symbol is one implement among many and the engine carries only
    the group, so the implement half of the accuracy cannot be narrowed.
    Named `spec.weapon_ref()` with the tomes and the sickles rather than
    a second spelling of its own: it is the same absence.
    """
    c.bonus("attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _one_handed_melee(c))
    gear = _gear(c)
    if gear is not None and gear.shield:
        for friend in c.allies():
            c.bonus(AC, 1, kind="shield", on=friend, until=When.ENCOUNTER)


@power("f3742", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*WEAPON_REF, "c.no_provoke(when=)"))
def f3742(c: Cast) -> None:
    """`c.no_provoke` names a creature you may walk away from, not a shape
    of attack you may make, so "ranged and area attacks do not provoke"
    has nowhere to go. The holy symbol is `spec.weapon_ref()`, as in
    `f3741`."""
    c.bonus(
        "attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _holding_two_handed(c),
    )


def _holding_two_handed(c: Cast) -> bool:
    gear = _gear(c)
    return gear is not None and any(
        w.two_handed and not w.ranged for w in gear.held
    )


@power("f3743", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3743(c: Cast) -> None:
    """Both halves. Light blade and heavy blade are both groups, so the
    accuracy half is exact -- and it is "arcane powers **and basic
    attacks**", which the gate had lost: a basic attack carries no
    keywords, so asking for `Keyword.ARCANE` alone answered false for
    half the printed sentence.

    The -5 is a gate on the attack context, which carries `target`; it is
    the damage side that is thin. Penalties take no `kind`, and the
    narrower "arcane attack power" is the printed wording of that clause
    -- a basic attack does not carry it.
    """
    me = c.me

    def blade(ctx: dict[str, Any]) -> bool:
        return _holding(c, "light blade", "heavy blade")

    def arcane_or_basic(ctx: dict[str, Any]) -> bool:
        ref = ctx.get("power", "")
        return (ref in BASICS or _keyword(ref, Keyword.ARCANE)) and blade(ctx)

    def at_a_friend(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            _keyword(ctx.get("power", ""), Keyword.ARCANE)
            and blade(ctx)
            and who is not None
            and who != me
            and team(c.world, who) is team(c.world, me)
        )

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=arcane_or_basic)
    c.penalty("attack", 5, on=me, until=When.ENCOUNTER, when=at_a_friend)


# -- the goblin run ---------------------------------------------------------


def _bigger_than_me(c: Cast):  # noqa: ANN202
    mine = c.size_of(c.me).order

    def when(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.size_of(who).order > mine

    return when


@power("f3745", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3745(c: Cast) -> None:
    """The damage context carries `target`, so "against creatures larger
    than you" is a gate rather than a marker. `Size.order` is the
    sequence; the raw value is a word.

    The critical rider is `c.flat(c.roll(...))` and not `c.damage`: a
    critical maxes dice, and 1d6 rolled inside the crit branch would come
    out 6 every time.
    """
    c.bonus("damage", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=_bigger_than_me(c))
    mine = c.size_of(c.me).order

    def crit(ev: Any) -> None:
        if ev.attacker == c.me and ev.critical and c.size_of(ev.target).order > mine:
            c.flat(c.roll("1d6"), on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("f3746", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTEND)
def f3746(c: Cast) -> None:
    """Two extra squares on the shift p1489 prints. `PowerUsed` is
    announced before the body runs, so by the time a watcher sees it the
    shift has not happened and there is nothing yet to lengthen."""


@power("f3747", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3747(c: Cast) -> None:
    """"The enemy that missed you" is the creature p1489 was itself a
    reaction to, and `PowerUsed.trigger` is that event now -- a `Miss`,
    whose `attacker` is the enemy. `ev.targets` would be no use: p1489
    is `target=SELF` and never names the creature it answers."""
    me = c.me

    def used(ev: Any) -> None:
        if ev.actor != me or ev.power != "p1489":
            return
        foe = getattr(getattr(ev, "trigger", None), "attacker", None)
        if foe is not None:
            c.grants_advantage(on=foe, to=me, until=When.EONT)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power("f3748", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=EXTEND)
def f3748(c: Cast) -> None:
    """The concealment half lands: `c.conceal` with `total` left off is
    the printed partial kind. The extra square on p1489's shift is
    dropped -- `PowerUsed` is announced before the body runs, so there is
    nothing yet to lengthen, and by `PowerResolved` the shift is spent."""
    me = c.me

    def used(ev: Any) -> None:
        if ev.actor == me and ev.power == "p1489":
            c.conceal(on=me, until=When.EONT)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power("f3749", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_ones()",))
def f3749(c: Cast) -> None:
    """Rerolling ones in a damage expression is a property of the roll,
    and `c.reroll_damage` rolls the whole thing twice instead."""


@power("f3750", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3750(c: Cast) -> None:
    """"Right before you shift" is the one place `PowerUsed` firing ahead
    of the body is the wanted order rather than the trap: the
    announcement is made above `p.body`, so the damage lands while p1489
    has not moved yet. `PowerUsed.trigger` is the `Miss` it answered and
    `attacker` is the enemy; heroic tier, so 1d4.

    Adjacency is asked with `c.adjacent_to`, which names both creatures:
    the bare `c.adjacent` measures from `c.target`, which a watcher has
    not got."""
    me = c.me

    def used(ev: Any) -> None:
        if ev.actor != me or ev.power != "p1489":
            return
        foe = getattr(getattr(ev, "trigger", None), "attacker", None)
        if foe is not None and c.adjacent_to(foe, me):
            c.damage("1d4", on=foe)

    c.watch(PowerUsed, used, until=When.ENCOUNTER)


@power("f3751", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SavingThrow.effect",))
def f3751(c: Cast) -> None:
    """Two dice on a save against daze or stun. `SavingThrow` carries
    `against` as a string built from the effect and not the effect
    itself, so which conditions a save is against cannot be asked --
    and `c.reroll_save` reads the trigger, which a watcher has not got."""


@power("f3752", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3752(c: Cast) -> None:
    """Measured from the square the turn started in, not from squares
    walked: "at least 3 squares away from where you started" is a
    distance and a creature that walks a loop has moved none of it.

    `MoveEnd` rather than `MoveStart`, because the question is where the
    creature has arrived.
    """
    start: list[tuple[int, int]] = []

    def began(ev: Any) -> None:
        if ev.actor == c.me:
            start[:] = [_at(c.world, c.me)]

    def landed(ev: Any) -> None:
        if ev.actor != c.me or not start or distance(start[0], ev.at) < 3:
            return
        for foe in c.enemies():
            if c.cursed(on=foe):
                c.grants_advantage(on=foe, to="me", until=When.SONT)

    c.watch(TurnStart, began, until=When.ENCOUNTER)
    c.watch(MoveEnd, landed, until=When.ENCOUNTER)


@power("f3753", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3753(c: Cast) -> None:
    """A plain "+1 bonus", so untyped. The question is asked of the
    creature being hit as the *attacker* -- does it have combat advantage
    against me -- which is the reverse of the usual direction."""
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and has_combat_advantage(c.world, ctx["target"], c.me)
        ),
    )


@power("f3754", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTEND)
def f3754(c: Cast) -> None:
    """Two extra squares on a shift p2479 hands out, and the same timing
    problem: the shift is gone by the time anything is announced."""


@power("f3755", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3755(c: Cast) -> None:
    """Spotting and disarming traps, which is skill work."""


@power("f3756", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3756(c: Cast) -> None:
    """Climbing bonuses, lent to an ally."""


@power("f3757", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3757(c: Cast) -> None:
    """Watched on `PowerResolved` rather than `PowerUsed`, and this is the
    reason for the rule: temporary hit points do not stack -- the larger
    pool wins -- so a top-up announced *before* p16469's own body would be
    silently thrown away by the pool the body then lays. The addition is
    made on top of whatever is standing once the power has finished.

    Heroic tier, so 3 a head.
    """

    def after(ev: Any) -> None:
        marked = sum(1 for foe in c.enemies() if c.marked(on=foe))
        if not marked:
            return
        health = c.world.get(c.me, Health)
        standing = health.temp if health is not None else 0
        c.temp_hp(standing + 3 * marked, on=c.me)

    def resolved(ev: Any) -> None:
        if ev.actor == c.me and ev.power == "p16469":
            after(ev)

    c.watch(PowerResolved, resolved, until=When.ENCOUNTER)


@power("f3758", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3758(c: Cast) -> None:
    """p1455 chooses its own target and announces it on `PowerResolved`,
    so the temporary hit points follow whoever was actually healed."""

    def after(ev: Any) -> None:
        if ev.actor != c.me or ev.power != "p1455":
            return
        for who in ev.targets:
            c.temp_hp(c.con_mod, on=who)

    c.watch(PowerResolved, after, until=When.ENCOUNTER)


@power("f3759", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3759(c: Cast) -> None:
    """p16469 lays its concealment with `c.conceal`, so the narrow
    question -- concealment *from that row* rather than from anywhere --
    is the label `c.bonus` wrote, which is what `_concealed_by` reads.
    `query.concealment_of` would answer the wider one and pay out for
    dim light the card says nothing about.

    "Or until you attack" is a second end, so the hold is kept and ended
    on the first swing rather than left to run its duration."""
    me = c.me

    def struck(ev: Any) -> None:
        if ev.target != me or not _concealed_by(c, "p16469"):
            return
        hidden = c.invisible(on=me, until=When.EONT)
        if hidden is None:
            return

        def swung(attack: Any) -> None:
            if attack.attacker == me:
                c.end_effect(hidden)

        c.watch(AttackDeclared, swung, until=When.EONT, once=True)

    c.watch(Hit, struck, until=When.ENCOUNTER)


@power("f3761", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.aid_another()",))
def f3761(c: Cast) -> None:
    """"Which enemy p16541 made grant combat advantage" is `c.suffering`:
    `c.grants_advantage` labels the effect it lays `"<ref> advantage"`,
    so the relation's cause is readable after all and the first half
    lands. Watched on `PowerResolved`, because p16541 chooses inside its
    body and there is nothing to find before it runs.

    Filtered to enemies because p16541's other branch lays a +3 on an
    ally under the same label, and `c.suffering` matches by substring.

    The aid half is dropped: the aid another action is not on the menu,
    so p16541's second branch is a bonus laid directly and there is no
    "used it to aid" to answer."""
    me = c.me

    def resolved(ev: Any) -> None:
        if ev.actor != me or ev.power != "p16541":
            return
        foes = set(c.enemies())
        for foe in c.suffering("p16541"):
            if foe not in foes:
                continue
            c.bonus(
                "damage", 3, kind="feat", on=me, until=When.SONT,
                when=lambda ctx, foe=foe: ctx.get("target") == foe,
            )

    c.watch(PowerResolved, resolved, until=When.ENCOUNTER)


@power("f3762", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3762(c: Cast) -> None:
    """Throwing a mimicked sound, settled by a Bluff check."""


@power("f3763", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3763(c: Cast) -> None:
    """Blindsight 1 is written as truesight at that radius, which is the
    nearest thing the engine has: both see what cannot be seen inside a
    radius, and truesight also refuses invisibility, which blindsight
    does at this range anyway. The skill bonuses and the sense of
    direction are outside a fight."""
    c.truesight(1, on=c.me, until=When.ENCOUNTER)


@power("f3764", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.crawl()",))
def f3764(c: Cast) -> None:
    """Crawling is not an action this engine has, so there is no half
    speed to raise to a full one."""


@power("f3766", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.no_provoke(when=)",))
def f3766(c: Cast) -> None:
    """`Gear` has hands, not limbs, and already lets two one-handers be
    held at once -- so what is left of the printed line is the ranged
    attacks not provoking, which `c.no_provoke` cannot narrow to."""


@power("f3767", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.no_provoke(when=)",))
def f3767(c: Cast) -> None:
    """The thrown-weapon twin of `f3766`, and the same two gaps."""


@power("f3768", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PROFICIENCY)
def f3768(c: Cast) -> None:
    """The spec names these two by weapon ref, so the gate is exact --
    and false for every character `chargen` can build today, because
    neither ref is in the weapon table `chargen.PRINTED` loads. The same
    shape `general_q.py`'s `_wielding` documents: the row reports UNUSED
    rather than wrong. Heroic tier, so +2."""
    c.bonus(
        "damage", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _holding_ref(c, "m5495a1", "m5732a1"),
    )


@power("f3769", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.regain_points()",))
def f3769(c: Cast) -> None:
    """Re-aimed. The price is writable now -- `c.expend_row` loses the
    use of p11739 without casting it -- and what is left is the payout:
    nothing puts a power point back into the pool, `c.spend_points`
    only takes them out. Named with the symbol ten other rows use for
    the same absence, rather than a second spelling of it."""


@power("f3770", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SurgeSpent.power",))
def f3770(c: Cast) -> None:
    """`c.regain_surge` and `c.spend_surge` between them would say "the
    ally keeps its surge and I lose one" -- but only for a surge my own
    power asked for, and `SurgeSpent` does not say which power caused it.
    Armed on every surge anybody spends, this would pay for the enemy's
    second wind."""


f3771 = _grants("f3771", "f3771b")


@power("f3771b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=CloseBurst(1), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
       group=CHANNEL_DIVINITY, dropped=("c.scenery(size=)",))
def f3771b(c: Cast) -> None:
    """"You and one ally", so the caster shifts once on the first target
    and the ally shifts on its own call. The teleport alternative needs a
    Large-or-larger plant beside both ends of the move; `c.scenery` finds
    map features but carries no size."""
    if c.first:
        c.shift(5, who=c.me)
    c.shift(5, who=c.target)


@power("f3773", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3773(c: Cast) -> None:
    """`c.resist` adds, so the "if you already have fire resistance"
    clause is the same call. The damage half reads both keys the damage
    context does carry -- the power, for its keywords, and the target,
    for its type words."""
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)

    def against_fire(ctx: dict[str, Any]) -> bool:
        ref = ctx.get("power", "")
        who = ctx.get("target")
        return (
            who is not None
            and c.is_kind("fire", who)
            and (_keyword(ref, Keyword.DIVINE) or _keyword(ref, Keyword.PRIMAL))
        )

    c.bonus("damage", c.wis_mod, on=c.me, until=When.ENCOUNTER,
            when=against_fire)


@power("f3774", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BEAST_KEYWORD)
def f3774(c: Cast) -> None:
    """"Beast attack powers and beast form attack powers" is a keyword the
    engine's closed set does not carry, so the bonus cannot be narrowed
    to them and an ungated one would apply to everything.

    Not a companion: the druid's own shape-changing rows are what the
    word means here, and no creature is involved."""


@power("f3775", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3775(c: Cast) -> None:
    """A ritual performed during a short rest. Nothing in a fight."""


f3776 = _grants("f3776", "f3776b")


def _divine_or_primal_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and (
        _keyword(ev.power, Keyword.DIVINE) or _keyword(ev.power, Keyword.PRIMAL)
    )


@power("f3776b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you hit a creature with a divine or primal attack power",
       on=Trigger(Hit, _divine_or_primal_hit, "you hit with a divine power"))
def f3776b(c: Cast) -> None:
    """The printed range is "Special" -- it reaches whatever the
    triggering attack reached -- so the row takes no target of its own and
    works on the creature the trigger names."""
    who = c.trigger.target
    c.prone(on=who)
    c.slowed(on=who, until=When.SAVE_ENDS)


@power("f3777", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.lend_defences()", "c.lend_skills()"))
def f3777(c: Cast) -> None:
    """A mount using its rider's defences is a substitution, not a bonus:
    "not including any temporary bonuses" rules out computing the
    difference and laying it as a modifier, because the difference would
    then change every time either number did."""


@power("f3778", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3778(c: Cast) -> None:
    """A point of everything for the beast while it stands beside you,
    and a second effect shaken off the beast when p2478 fires.

    The card prints standing modifiers *and* a rider on another row, so
    the modifiers are the trait and the rider is a `c.watch`: declaring
    `on=Trigger(...)` would mean the bonuses were never laid at all.

    "Feat bonus", printed, so `kind="feat"`. Read `c.beast()` inside the
    gate rather than capturing it: the beast can be killed and called
    again and a captured id goes quietly stale. The watcher reads it
    afresh for the same reason."""
    pet = c.beast()
    if pet is None:
        return

    def at_heel(ctx: dict[str, Any]) -> bool:
        return c.adjacent_to(pet, c.me)

    for where in (AC, FORT, REF, WILL):
        c.bonus(where, 1, on=pet, until=When.ENCOUNTER, kind="feat",
                when=at_heel)

    def alongside(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != "p2478":
            return
        beast = c.beast()
        if beast is not None and c.adjacent_to(beast, c.me):
            c.end_effect(on=beast, save_ends=True)

    c.watch(PowerUsed, alongside, until=When.ENCOUNTER, on=c.me)


@power("f3779", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.armor_proficiency()",))
def f3779(c: Cast) -> None:
    """Shield proficiency and the check penalty for wearing one are both
    settled when the character is built, and a shield is a different
    column from a weapon: `ClassLine.shield` is a number, so there is
    nowhere for a shield a character merely *may* carry to be written."""


@power("f3780", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:flail", "w:spear"))
def f3780(c: Cast) -> None:
    """Both groups now: flail is one the weapon table carries and
    `chargen` deals. Heroic tier, so +2."""
    c.bonus("damage", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "spear", "flail"))


@power("f3781", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("TempHP.power",))
def f3781(c: Cast) -> None:
    """`cf:bard-f1s2` is a ref the prerequisite prints, and no row carries
    it: `cf:bard-f1` writes that virtue inline on its `second-con` leg.
    What it does is lay temporary hit points, and `TempHP` carries a
    source, a target and an amount and no power -- so "when you use your
    `cf:bard-f1s2`" cannot be told from any other pool the bard lays."""


@power("f3782", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reshape_area()",))
def f3782(c: Cast) -> None:
    """Cutting one square out of a blast or burst. An area is computed
    from the header when the power runs and nothing narrows it."""


@power("f3783", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=CloseBurst(1), target=ONE_ALLY)
def f3783(c: Cast) -> None:
    """`c.expend_row` charges the printed price, so the cap is p2478's
    own use rather than the stand-in `ENCOUNTER` this row carried while
    the cost could not be said. Same budget, said by the right row."""
    if c.expend_row("p2478"):
        c.save(on=c.target)


# -- the unarmed run --------------------------------------------------------


@power("f3784", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("chargen.plain_unarmed",))
def f3784(c: Cast) -> None:
    """Unarmed *is* one of the ten groups, so the accuracy half is exact and
    the word the card prints is "proficiency".

    **The die is re-aimed, not written.** It was waiting on `c.change_dice()`;
    that verb exists now and is the wrong one -- a weapon's die is a field on
    the `Weapon`, which `c.weapon_dice` edits. The clause still cannot be
    written, for a different reason: there is no plain fist to raise. Every
    row in the group is a better fist than a bare one, so raising the group
    would lower a monk's strike. #282, and f2400 is the other row on it."""
    c.bonus("attack", 2, kind="proficiency", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "unarmed"))


@power("f3785", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.counts_as(property=)",))
def f3785(c: Cast) -> None:
    """A weapon property laid on a weapon after the fact.

    **One gap now, not two.** It also waited on `Weapon.high_crit`, on the
    argument that nothing read the property; `Cast._high_crit` reads it now
    (#240), so the whole of what is missing is the writer.
    """


@power("f3786", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.counts_as(property=)",))
def f3786(c: Cast) -> None:
    """The racial burst rolls d8s, and the unarmed attack gains a property.

    The dice half is written -- `p5599` asks `c.dice_for` for its die now.

    The property half is the dropped clause: a weapon's properties are
    columns on the row the character is holding, shared by every copy of that
    weapon, so "this character's counts as off-hand" has nowhere to be
    recorded. Same verb f3784 beside it wants, and the same reason."""
    c.change_dice("p5599", "1d8")


@power("f3787", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_racial_bonus()",))
def f3787(c: Cast) -> None:
    """The critical half lands. "Double your racial bonus to damage" needs
    to find a bonus somebody else laid and change its size, and a modifier
    is a number with no handle on it once stored."""

    def crit(ev: Any) -> None:
        if ev.attacker == c.me and ev.critical and _keyword(ev.power, Keyword.ARCANE):
            c.prone(on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("f3788", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("spec.feature_ref()",))
def f3788(c: Cast) -> None:
    """`engine/equipment.py` puts no speed penalty on heavy armour, so the
    first clause has nothing to cancel. What is left is an altitude limit
    on a *racial* trait.

    Re-aimed: racial traits are imported now and `rt:` rows exist, but not
    for this race -- r68 has two racial powers in `content/races/` and no
    trait row at all, so the thing this raises a ceiling on has no ref.
    The same absence a dozen rows carry as `spec.feature_ref()`."""


@power("f3789", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3789(c: Cast) -> None:
    """Heroic tier, so 5 of each."""
    c.resist(5, DamageType.ACID, on=c.me, until=When.ENCOUNTER)
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)


@power("f3790", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3790(c: Cast) -> None:
    """A rider on a racial power the spec names by ref, so it can be
    watched. `PowerResolved` rather than `PowerUsed`: the save is "also",
    after the power has done its own work."""
    def resolved(ev: Any) -> None:
        if ev.actor == c.me and ev.power == "p16657":
            c.save(on=c.me)

    c.watch(PowerResolved, resolved, until=When.ENCOUNTER)


@power("f3791", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("events.ShortRested",))
def f3791(c: Cast) -> None:
    """`cf:artificer-f0` is declared, so the feature this adds a use to
    has a row. Its own marker is the reason this one cannot move: the
    per-day allowance is granted and spent inside a rest, `turns
    .short_rest` emits nothing, and a use added to a pool nothing fills
    has nowhere to go."""


@power("f3792", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3792(c: Cast) -> None:
    """A cantrip making skill checks at a distance."""


@power("f3793", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.extra_target()",))
def f3793(c: Cast) -> None:
    """The first clause has nothing to cancel. `rt:r69-quick-fix` is
    declared and declared deliberately inert -- the checks it covers are
    not made in a fight and cost no action there -- so the -4 this feat
    lifts is never laid.

    What is left is widening `p16660`'s target line, and `c.add_target`
    adds one to the power being cast, not to a power somebody will cast
    later."""


@power("f3794", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.counts_as(property=)",),
       proficiency=("w:sickle", "w:scythe"))
def f3794(c: Cast) -> None:
    """Neither is a group, but both are rows in the weapon table, so the
    bonus is gated on the ref. Heroic tier, so +2.

    Dropped: "you treat the scythe as having the high crit property".
    `Weapon.properties` is read off the weapon and nothing writes to the
    one in hand."""
    c.bonus("damage", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _holding_ref(c, "w:sickle", "w:scythe"))


f3795 = _grants("f3795", "f3795b")


def _a_drop_near_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """"You drop an enemy, or an enemy adjacent to you drops."

    `Dropped` names the creature going down `actor` and its killer
    `source`, so the two halves read different fields of the same event.
    """
    if ev.source == me:
        return True
    return distance(_at(world, me), _at(world, ev.actor)) <= 1


@power("f3795b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.NECROTIC], group=CHANNEL_DIVINITY,
       trigger="you drop an enemy, or an enemy adjacent to you drops",
       on=Trigger(Dropped, _a_drop_near_me, "a creature near you drops"))
def f3795b(c: Cast) -> None:
    """"Only once per turn" is a set cleared at the start of each turn
    rather than a `once=True`, because the limit is per creature and per
    turn, not per aura.

    Both payouts are hung on the aura's own duration, so when it lapses
    the watchers go with it.

    "Partial concealment against enemies in the aura" is `c.conceal` with
    a gate: the *attack* context carries `attacker`, which the damage one
    does not, and `query.concealment_of` is handed that context -- so the
    narrowing the card prints is sayable rather than a blanket -2.
    """
    ring = c.aura(1, label=c.ref, until=When.EONT)
    paid: set[int] = set()

    def in_the_ring(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.in_my_aura(who, label=c.ref)

    def bite(who: int) -> None:
        if who in paid or who == c.me or not c.in_my_aura(who, label=c.ref):
            return
        paid.add(who)
        c.flat(c.wis_mod, dtype=DamageType.NECROTIC, on=who)

    def turn_ended(ev: Any) -> None:
        paid.discard(ev.actor)
        bite(ev.actor)

    def swung(ev: Any) -> None:
        from combat_engine.engine.triggers import by_melee

        if ev.target == c.me and by_melee(c.world, c.me, ev):
            bite(ev.attacker)

    if ring:
        c.conceal(on=c.me, until=When.EONT, when=in_the_ring)
        c.watch(TurnEnd, turn_ended, until=When.EONT)
        c.watch(AttackDeclared, swung, until=When.EONT)


@power("f3796", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Healed.power",))
def f3796(c: Cast) -> None:
    """Both names are refs now -- `p6189` and `f3668b`, and `f3668b` is a
    real row -- so what is left is telling the two apart at the moment
    of the heal.

    `Healed` carries `source`, `target`, `amount` and `hp` and does not
    say which row paid out, and `f3668b` heals through a `c.give`
    one-shot that announces nothing of its own. Written without that,
    the top-up would ride on *every* heal this caster sourced for the
    round, which is more than the card prints -- so the whole row waits
    rather than half of it playing too wide.
    """


@power("f3797", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=COMBINED)
def f3797(c: Cast) -> None:
    """A combined attack -- the character and its creature swinging as one
    row -- and the right to use a second row off the back of that hit.

    Not the ranger's beast, which now exists: this is the animal a
    different class feature grants, and what the row turns on is the
    pairing of the two attacks rather than the creature.

    Re-aimed off `c.use_power()`: firing `p6189` is one line now, and
    the whole remaining hold is the combined attack this rides on."""


@power("f3798", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p6189 with p4807's attack",
       on=Trigger(PowerResolved, _furious_on_p4807, "you use it with that"))
def f3798(c: Cast) -> None:
    """"With p4807's attack" is the `Hit` the racial power answered, and
    the event names it now.

    On the resolution rather than the use, because `dsl.use` marks the
    row spent between the two -- handing the use back any earlier gives
    it back before it is taken.
    """
    c.restore_use("p6189")
