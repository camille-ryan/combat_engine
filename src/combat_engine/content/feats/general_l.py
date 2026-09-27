"""General feats, the twelfth batch: action-point riders, the spellscar
family, and a long tail of weapon and posture feats.

Four shapes account for most of this file.

**The action-point rider.** Six rows here pay out when *an ally* spends a
point. `ActionPointSpent` names its subject `actor`, so `by_me` is false
on it forever -- it reads `attacker` then `source` -- and every one of
these predicates is written out by hand.

**The spellscar tail.** Eighteen rows share the gate `q416` and every one
of them ends "If you have the Student of the Plague feat, ...". That feat
is named in prose with no ref, so `c.feat` has nothing to ask about and
the clause is dropped as `spec.feat_ref()` throughout. Several of the
same rows also deal "fire and necrotic damage", which is one blow of two
types -- `DamageType.pair()`, the symbol earlier waves named.

**Weapon groups are a closed set**: axe, bow, crossbow, heavy blade,
implement, light blade, mace, spear, staff, unarmed. Hammers, picks and
polearms are printed groups this engine does not carry, so a row gated on
one of them can only be marked. `chargen.HAMMER` and `chargen.POLEARM`
join `chargen.WHIP` and the rest of that family.

**A printed Trigger keeps a row out of the action menu** -- `_powers`
refuses anything carrying one -- so the rows here whose printed benefit
has no per-encounter limit are `AT_WILL` rather than `ENCOUNTER`. An
encounter budget on "whenever you hit" would spend the whole feat on the
first blow of the fight.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    ConditionEnded,
    DamageType,
    Dropped,
    Forced,
    ForcedMove,
    Gear,
    Healed,
    Hit,
    Keyword,
    Miss,
    Moved,
    MoveEnd,
    OpportunityWindow,
    Relation,
    SavingThrow,
    Size,
    Trigger,
    Usage,
    When,
    get,
    hits_me,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.events import PowerUsed
from combat_engine.engine.query import alive, allies, distance_between, holding, team

#: A racial power the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: A class feature named in prose, with no `cf:` ref to borrow.
FEATURE = ("c.borrow_feature()",)
#: "If you have the <named> feat" -- the spec gives no ref for it.
PLAGUE = ("spec.feat_ref()",)
#: One blow of two damage types at once.
PAIR = ("DamageType.pair()",)
#: Total defence is not an action this engine has.
TOTAL_DEFENCE = ("c.total_defence()",)
#: Nothing models a bull rush.
BULL_RUSH = ("c.bull_rush()",)
#: A build choice nothing records.
BUILD = ("chargen.BUILDS",)

DIVINE = [Keyword.DIVINE]

_BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)
_CLOSE = ("melee", "close_burst", "close_blast")
#: The four the transfer card names.
_TRANSFERABLE = (
    Condition.DAZED,
    Condition.IMMOBILIZED,
    Condition.STUNNED,
    Condition.SLOWED,
)


# -- small shared questions -------------------------------------------------


def _used(ref: str):  # noqa: ANN202
    """`PowerUsed` names its subject `actor`, which `by_me` never reads."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _reach_kind(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None and p.reach is not None else ""


def _melee(ref: str) -> bool:
    return _reach_kind(ref) == "melee"


def _melee_or_close(ref: str) -> bool:
    return _reach_kind(ref) in _CLOSE


def _keyword(ref: str, word: Keyword) -> bool:
    p = get(ref)
    return p is not None and word in p.keywords


def _gear(c: Cast) -> Gear | None:
    return c.world.get(c.me, Gear)


def _group_in(c: Cast, *groups: str) -> bool:
    gear = _gear(c)
    return gear is not None and any(w.group in groups for w in gear.held)


def _armour(c: Cast) -> str:
    gear = _gear(c)
    return gear.armour if gear is not None else ""


def _ally_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """An ally spends an action point. `ActionPointSpent.actor`, by hand."""
    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_am_bloodied(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _i_dropped(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _grants(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is the card beside it."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


# -- riders on somebody else's action point ---------------------------------


@power("f2543", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2543(c: Cast) -> None:
    """The ally chooses, and the choice costs it something -- so the
    combat advantage is laid only once the ally has actually rolled, and
    against whoever it rolled at. `EOTNT` because the printed duration is
    the *ally's* next turn, and the effect is held on the ally."""
    friend = c.trigger.actor
    if not c.may("take the damage bonus", who=friend):
        return
    c.bonus("damage", 4, on=friend, until=When.EONT, once=True)
    spent = False

    def grant(ev: Any) -> None:
        nonlocal spent
        if spent or ev.attacker != friend:
            return
        spent = True
        c.grants_advantage(on=friend, to=ev.target, until=When.EOTNT)

    c.watch(AttackRolled, grant, on=friend, until=When.EONT)


def _one_hand_free(world, eid: int) -> bool:  # noqa: ANN001
    """One weapon in hand, it is not two-handed, and no shield."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    held = gear.held
    return len(held) == 1 and not held[0].two_handed and not gear.shield


@power("f2544", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("c.boost_attack()",),
       requires=_one_hand_free,
       requires_text="a weapon in one hand and nothing in the other")
def f2544(c: Cast) -> None:
    """The AC half. "A +1 bonus to an attack roll you just made" is a
    number added to a die already down: `c.boost_check` does that for a
    skill check and nothing does it for an attack.

    The free-hand requirement is a fact about the board, so it is a
    `requires=` rather than a prerequisite column.
    """
    c.bonus(AC, 1, on=c.me, until=When.SONT)


@power("f2545", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF)
def f2545(c: Cast) -> None:
    """Chainmail is `"chain"` here, and the light band is cloth, leather
    and hide -- `chargen.LIGHT`. Two weapons is `Gear.two_weapon`.

    The gear test lives in the gate rather than above the `c.bonus`,
    because dropping a weapon and picking one up are both actions: a
    check made when the free action is taken is a fact about one moment
    being held for a whole turn.
    """
    me = c.me

    def kitted(ctx: dict[str, Any]) -> bool:
        gear = _gear(c)
        return (
            gear is not None
            and gear.two_weapon
            and gear.armour in ("cloth", "leather", "hide", "chain")
            and _melee_or_close(ctx.get("power", ""))
        )

    c.bonus("damage", 1, on=me, until=When.EOT, when=kitted)


@power("f2546", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2546(c: Cast) -> None:
    """A plain "+1 bonus", so untyped, and held on the ally so `EOTNT`
    reads as the ally's next turn."""
    friend = c.trigger.actor
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=friend, until=When.EOTNT)


@power("f2547", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2547(c: Cast) -> None:
    """Hit *or* miss, so both halves are armed and the first of the
    ally's attacks to land settles which one pays. The damage bonus is
    `once`, and a `Hit` closes the miss half rather than leaving it to
    catch some later swing."""
    friend = c.trigger.actor
    c.bonus("damage", 3, on=friend, until=When.EONT, once=True)
    settled = False

    def landed(ev: Any) -> None:
        nonlocal settled
        if ev.attacker == friend:
            settled = True

    def missed(ev: Any) -> None:
        nonlocal settled
        if settled or ev.attacker != friend:
            return
        settled = True
        c.temp_hp(3, on=friend)

    c.watch(Hit, landed, on=friend, until=When.EONT)
    c.watch(Miss, missed, on=friend, until=When.EONT)


@power("f2548", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2548(c: Cast) -> None:
    """"Before or after the extra action" -- the point is announced
    before the action is taken, so this is the "before" half, which is
    the one the event can reach."""
    friend = c.trigger.actor
    if c.may("shift 1 square", who=friend):
        c.shift(1, who=friend)


@power("f2570", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.grant_action('second wind')",))
def f2570(c: Cast) -> None:
    """Second wind for a minor action. `c.grant_action` understands
    `shift` and `stand` and silently eats anything else -- its own
    docstring says so -- so writing this with it would be a finished
    looking row that never does anything."""


# -- the borrowed class features, named in prose ----------------------------


@power("f2542", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2542(c: Cast) -> None:
    """A named fighter class feature with no `cf:` ref, which is the same
    gap five rows in `general_d.py` carry."""


@power("f2549", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2549(c: Cast) -> None:
    """The benefit of a named rogue class feature for a turn. Same gap."""


@power("f2628", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2628(c: Cast) -> None:
    """A named battlemind power with a lengthened mark. No ref for the
    power, so there is nothing for `c.grant_row` to hand over."""


@power("f2694", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2694(c: Cast) -> None:
    """One of the monk's named powers, chosen at build time, plus a
    proficiency. Neither the power nor the choice has a ref."""


@power("f2731", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2731(c: Cast) -> None:
    """A chosen psion at-will, named in prose. Same gap."""


@power("f2859", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, *PLAGUE))
def f2859(c: Cast) -> None:
    """A chosen arcane at-will used as an encounter power. The choice has
    no ref and the spellscar clause names a feat that has none either."""


@power("f2697", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*BUILD, "dsl.use(augment=)"))
def f2697(c: Cast) -> None:
    """Swaps one augmentable at-will for another class's. Both the swap
    and the augmentation are build-time, and `dsl.use` has no augment."""


@power("f2698", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*BUILD, "dsl.use(augment=)"))
def f2698(c: Cast) -> None:
    """Same shape as f2697, trading an encounter power instead, and
    handing out power points for it."""


@power("f2732", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*BUILD, "dsl.use(augment=)"))
def f2732(c: Cast) -> None:
    """Same shape as f2697, in the other direction, and it costs points
    rather than granting them."""


@power("f2580", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BUILD)
def f2580(c: Cast) -> None:
    """Swaps the bonus at-will for a skill power. A retraining choice,
    settled when the character is built and recorded nowhere."""


@power("f2618", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BUILD)
def f2618(c: Cast) -> None:
    """Grants a utility power drawn from a trained skill. Which one is a
    build choice, and the spec's own ref for it is this feat."""


# -- the multiclass feats whose power the spec does name --------------------


@power("f2693", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2693(c: Cast) -> None:
    """The power arrives as a ref, so the grant is ordinary. "Once per
    day" is written as once per encounter -- see #72 -- and the row's own
    usage is what says so."""
    c.grant_row("p10273", on=c.me, until=When.ENCOUNTER)


@power("f2695", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=FEATURE)
def f2695(c: Cast) -> None:
    """The daily has a ref and is handed over; the "choose one 1st-level
    at-will" half is prose with no id."""
    c.grant_row("p9501", on=c.me, until=When.ENCOUNTER)


@power("f2696", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2696(c: Cast) -> None:
    c.grant_row("p11353", on=c.me, until=When.ENCOUNTER)


# -- the channelled pair ----------------------------------------------------


_grants("f2574", "f2574b")


def _burdened_nearby(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """`ConditionApplied` names its subject `target`, so `about_me` --
    which reads `actor` and only `actor` -- is false on it forever."""
    return (
        ev.condition in _TRANSFERABLE
        and team(world, ev.target) == team(world, me)
        and distance_between(world, me, ev.target) <= 5
    )


@power("f2574b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=CloseBurst(5),
       target=NO_TARGET, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you or an ally within range becomes dazed, immobilized, "
               "stunned or slowed",
       on=Trigger(ConditionApplied, _burdened_nearby, "an ally is held"))
def f2574b(c: Cast) -> None:
    """`c.transfer` moves the live hold intact, which is the printed
    line -- the effect keeps its duration and its save. The event does
    not carry the `Effect`, so it is found by the condition it named."""
    victim = c.trigger.target
    want = c.trigger.condition
    eff = next(
        (e for e in c.world.effects.of(victim) if want in e.conditions), None
    )
    if eff is None:
        return
    taker = next(
        (
            who
            for who in (c.me, *c.allies())
            if who != victim and c.distance(to=who) <= 5
        ),
        None,
    )
    if taker is not None:
        c.transfer(eff, to=taker)


_grants("f2575", "f2575b")


@power("f2575b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f2575b(c: Cast) -> None:
    """"You and each ally in the burst" -- the caster is added on the
    first target rather than trusted to be one of them."""
    c.ignores_difficult(on=c.target, until=When.EONT)
    if c.first:
        c.ignores_difficult(on=c.me, until=When.EONT)


# -- the r8 aura and the three feats that ride on it ------------------------


@power("f2576", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2576(c: Cast) -> None:
    """The Insight and Perception halves are checks; the card is the
    combat half and it has a ref."""
    c.grant_row("f2576b", on=c.me, until=When.ENCOUNTER)


@power("f2576b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f2576b(c: Cast) -> None:
    """An aura carrying the penalty rather than a penalty laid on each
    enemy standing there now: the printed line is "while within 5
    squares", and a creature that walks in later is inside it too.
    `c.grants_in` is what hangs a modifier on a zone."""
    me = c.me
    ring = c.aura(5, label=c.ref, on=me, until=When.EONT)
    c.grants_in(ring, "attack", -2, side="enemy", kind="untyped")

    def missed(ev: Any) -> None:
        if ev.attacker != me and c.distance(to=ev.attacker) <= 5:
            c.slide(1, on=ev.attacker)

    c.watch(Miss, missed, on=me, until=When.EONT)


@power("f2577", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2577(c: Cast) -> None:
    """Rolling an Insight check twice. Not a fight."""


def _slid_by_the_aura(c: Cast):  # noqa: ANN202
    """`Cast.slide` passes `power=self.ref`, so a slide the card made can
    be told from anybody else's."""

    def when(ev: Any) -> bool:
        return (
            ev.source == c.me
            and ev.how == Forced.SLIDE
            and ev.power == "f2576b"
        )

    return when


@power("f2578", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2578(c: Cast) -> None:
    """A trait rather than a declared trigger, because the row is armed
    once and then answers every slide the card makes."""
    me = c.me
    mine = _slid_by_the_aura(c)

    def slid(ev: Any) -> None:
        if mine(ev):
            c.mark(on=ev.target, until=When.EOTNT)

    c.watch(ForcedMove, slid, on=me, until=When.ENCOUNTER)


@power("f2579", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus('skill:any')",))
def f2579(c: Cast) -> None:
    """The attack half. "Or skill check" is dropped for the reason
    `general_b.f629b` dropped it: a skill bonus is keyed `skill:<name>`
    and the card names no skill."""
    me = c.me
    mine = _slid_by_the_aura(c)

    def slid(ev: Any) -> None:
        if mine(ev):
            c.bonus("attack", 2, on=me, until=When.EONT, once=True)

    c.watch(ForcedMove, slid, on=me, until=When.ENCOUNTER)


# -- the racial powers named in prose ---------------------------------------


@power("f2460", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2460(c: Cast) -> None:
    """Extra damage on a racial power the benefit names in prose. The
    prerequisite gives a race and an opaque term, not a ref."""


@power("f2583", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2583(c: Cast) -> None:
    """Temporary hit points when a racial power is used with an ally
    near. "A r44 racial power" is a race, not a ref."""


@power("f2584", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2584(c: Cast) -> None:
    """Same gap as f2583; the payout -- your surge heals an unconscious
    ally -- is `c.spend_surge` and `c.surge` and would be two lines."""


@power("f2600", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2600(c: Cast) -> None:
    """Three clauses, one per racial power, all three named in prose."""


@power("f2617", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.race_choice()", "c.restore_use(racial)"))
def f2617(c: Cast) -> None:
    """Changes an aspect of nature and hands back a racial power's use.
    The aspect is a race choice nothing records and the power has no
    ref, so there is nothing for `c.restore_use` to name."""


@power("f2842", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, *PLAGUE))
def f2842(c: Cast) -> None:
    """Gives a racial power a sustain. The power is named in prose; the
    prerequisite's `p377` is a different row from the one the benefit
    talks about, so it cannot stand in for it."""


@power("f2871", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*RACIAL, "c.attack_ability()"))
def f2871(c: Cast) -> None:
    """Swaps which ability a racial trait's borrowed power attacks with.
    The power is chosen at build time and named in prose, and nothing
    rewrites one row's attack line for one character."""


@power("f2873", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2873(c: Cast) -> None:
    """A mark on hitting with the racial trait's borrowed power."""


@power("f2875", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, "c.as_basic(ref)"))
def f2875(c: Cast) -> None:
    """Uses that borrowed power as a melee basic attack on a charge.
    Both halves are gaps: the power has no ref, and nothing makes a
    named row count as the basic attack."""


@power("f2877", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, "c.deals(ref=)"))
def f2877(c: Cast) -> None:
    """Radiant damage from that borrowed power. `c.deals` overrides what
    a creature's *weapon* rolls and has no way to name a row."""


@power("f2879", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2879(c: Cast) -> None:
    """Extra healing after hitting with the borrowed power."""


@power("f2753", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f2753(c: Cast) -> None:
    """A penalty when the attack `p1452` forces to be made again misses.
    `p1452` is a ref -- the gap is that nothing announces a roll is a
    reroll, which is the same hold `general_f.f216` carries."""


@power("f2846", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*REROLL, *PAIR, *PLAGUE))
def f2846(c: Cast) -> None:
    """Damage to the attacker when `p1452`'s rerolled roll misses. Same
    reroll gap as f2753, and the damage is two types at once."""


@power("f2849", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*REROLL, *PAIR, *PLAGUE))
def f2849(c: Cast) -> None:
    """Rides on `p1450`'s reroll. Same gap from the other side."""


# -- the racial powers that are refs, so the rider is ordinary --------------


@power("f2603", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use that racial power"))
def f2603(c: Cast) -> None:
    """`p11052` is a ref in the prerequisite, so the rider is an ordinary
    trigger rather than the prose gap the rest of this family has."""
    c.save(on=c.me)


@power("f2631", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use that racial power"))
def f2631(c: Cast) -> None:
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)


@power("f2851", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=PLAGUE,
       trigger="you use p1449",
       on=Trigger(PowerUsed, _used("p1449"), "you use that racial power"))
def f2851(c: Cast) -> None:
    """"Before or after" -- `PowerUsed` is announced above the body, so
    this is the before half, and it is the half the event can reach."""
    who = next((x for x in c.within(1) if x != c.me), None)
    if who is not None:
        c.slide(1, on=who)


@power("f2854", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       dropped=("PowerUsed.trigger", *PLAGUE),
       trigger="you use p6189",
       on=Trigger(PowerUsed, _used("p6189"), "you use that racial power"))
def f2854(c: Cast) -> None:
    """The half measured from you. "Adjacent to the triggering enemy" is
    dropped: `p6189` answers an enemy's attack and `PowerUsed` carries
    the targets it chose, not the event it was answering."""
    for who in c.within(1):
        if who != c.me:
            c.flat(2, dtype=DamageType.FIRE, on=who)


@power("f2841", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.under_effect(ref)", *PLAGUE))
def f2841(c: Cast) -> None:
    """A shift granted for as long as `p2484`'s effect is standing.
    `p2484` is a ref, but nothing asks whether a named row's effect is
    live on a creature, and `c.shift_as` needs the duration to end with
    it or the character keeps the shift for the rest of the fight."""


@power("f2843", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET, dropped=("c.expend()", *PLAGUE),
       trigger="you are subjected to a dazing or stunning effect",
       on=Trigger(
           ConditionApplied,
           lambda w, me, ev: (
               ev.target == me
               and ev.condition in (Condition.DAZED, Condition.STUNNED)
           ),
           "you are dazed or stunned",
       ))
def f2843(c: Cast) -> None:
    """The saving throw plays; the cost does not. Spending a named row's
    remaining use is `c.expend()`, which does not exist -- `c.expended`
    only reports what has gone."""
    c.save(on=c.me)


@power("f2847", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*PAIR, *PLAGUE))
def f2847(c: Cast) -> None:
    """The bloodied half plays. Adding a second damage type to one the
    power already deals is one blow of two types, which `c.damage` and
    `c.bonus` both take one of."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p1448" and c.bloodied(on=me),
    )


@power("f2848", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.bonus(regeneration)", "Healed.regeneration", *PLAGUE))
def f2848(c: Cast) -> None:
    """Raises the regeneration another row granted, and pays out each
    time it ticks. `c.regeneration` sets an amount and nothing adds to a
    standing one; `Healed` does not say which healing was a regeneration,
    so the second half has no moment either."""


@power("f2855", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*PAIR, *PLAGUE))
def f2855(c: Cast) -> None:
    """The +2 plays, gated on the ref the spec gives."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p8278",
    )


@power("f2857", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=PLAGUE,
       trigger="you hit an enemy with p1831",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.attacker == me and ev.power == "p1831",
           "you hit with that racial power",
       ))
def f2857(c: Cast) -> None:
    """"Each time an attack hits that enemy" -- anybody's attack, so the
    watch is on every `Hit` and the filter is the victim."""
    victim = c.trigger.target

    def bitten(ev: Any) -> None:
        if ev.target == victim:
            c.flat(2, dtype=DamageType.FIRE, on=victim)

    c.watch(Hit, bitten, on=c.me, until=When.EONT)


# -- the winter chain -------------------------------------------------------


@power("f2702", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2702(c: Cast) -> None:
    """The gate of the chain: the card, plus resist cold. Both halves are
    printed on the parent, so it is not a bare `_grants`."""
    c.grant_row("f2702b", on=c.me, until=When.ENCOUNTER)
    c.resist(5 + c.level // 2, DamageType.COLD, on=c.me, until=When.ENCOUNTER)


@power("f2702b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       keywords=[Keyword.TELEPORTATION],
       trigger="an enemy damages you with an attack",
       on=Trigger(Hit, hits_me, "an enemy hits you"))
def f2702b(c: Cast) -> None:
    """Declared on the hit rather than on the damage: `DamageApplied`
    does not say whether an attack caused it, and a hit that rolls no
    damage is not a case this card has to tell apart."""
    c.teleport(3)
    c.conceal(on=c.me, until=When.SONT)


@power("f2699", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.forgo_teleport()", "PowerUsed.trigger"))
def f2699(c: Cast) -> None:
    """Damage to the triggering enemy *instead of* the teleport. Two
    holds: nothing suppresses a clause of another row, and `f2702b`'s
    triggering enemy is not carried on the `PowerUsed` this would watch."""


@power("f2700", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2700(c: Cast) -> None:
    """`c.ignores_difficult` takes the sort of ground by name, so two
    named sorts are two calls rather than a blanket one."""
    c.ignores_difficult("ice", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("snow", on=c.me, until=When.ENCOUNTER)


@power("f2701", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use f2702b",
       on=Trigger(PowerUsed, _used("f2702b"), "you use that power"))
def f2701(c: Cast) -> None:
    """"Lightly obscured" is concealment for whoever is standing in it,
    and concealment is held on the creature rather than on the ground --
    so it is laid on everyone in the two squares' worth of area."""
    for who in (c.me, *c.within(1)):
        c.conceal(on=who, until=When.SONT)


@power("f2703", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f2703(c: Cast) -> None:
    """Lengthens the teleport `f2702b` makes. The distance is written
    into that row's body, and nothing reaches into another row's move."""


# -- standing bonuses -------------------------------------------------------


@power("f2564", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2564(c: Cast) -> None:
    """A save bonus against fear.

    **The save-modifier context has no `against`.** That is a field of
    the `SavingThrow` *event*; the context carries `actor`, `effect`,
    `label`, `conditions`, `ongoing`, `dtype` and `keywords`. Six rows
    in this file read it and were silently false in every fight.

    Fear is a keyword, so `keywords` is the key -- derived by
    `durations.keywords_of` from the row that laid the effect.
    """
    me = c.me
    c.bonus(
        "save", 5, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: Keyword.FEAR in ctx.get("keywords", ()),
    )
    # `c.initiative`, not `c.bonus("initiative", ...)`: `Initiative.bonus`
    # is summed before the d20 and `Mods` is never consulted, so the
    # modifier would be laid and no roll would read it.
    c.initiative(2, on=me)


@power("f2565", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("resolve.ctx.provoked_by",))
def f2565(c: Cast) -> None:
    """The narrowing is dropped. The defence context carries
    `opportunity` and nothing about *why* the window opened, so "an
    opportunity attack you provoked by using a ranged power" cannot be
    told from any other."""
    c.bonus(
        AC, 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("opportunity", False),
    )


@power("f2566", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Gear.heavy_shield",))
def f2566(c: Cast) -> None:
    """`c.forces` is the key the shove reads off the creature *doing* the
    pushing, and its gate is handed `how` and `power` -- which is exactly
    "your pushes and slides, with a melee attack".

    `Gear.shield` is a flag with no weight to it, so the heavy half of
    "heavy shield" is dropped rather than guessed at.
    """
    me = c.me
    c.forces(
        1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("how") in ("push", "slide")
            and _melee(ctx.get("power", ""))
            and c.wielding("shield")
        ),
    )


@power("f2569", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PLAGUE)
def f2569(c: Cast) -> None:
    """The +3 step names another feat in prose, so `c.feat` has no ref to
    ask about and that step is dropped."""
    me = c.me
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: c.bloodied(on=me) and any(
            str(x.value) in ("immobilized", "dazed", "stunned", "weakened")
            for x in ctx.get("conditions", ())
        ),
    )


@power("f2586", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2586(c: Cast) -> None:
    """A plain "+2 bonus", so untyped. `c.is_kind` reads the type line."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (t := ctx.get("target")) is not None
        and c.is_kind("aberrant", on=t),
    )


@power("f2594", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2594(c: Cast) -> None:
    c.bonus(
        "save", 4, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: any(
            str(x.value) in ("dazed", "stunned")
            for x in ctx.get("conditions", ())
        ),
    )


@power("f2595", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("resolve.prone_penalty",))
def f2595(c: Cast) -> None:
    """The damage half. There is no penalty for shooting a prone target
    in this engine -- `resolve` never asks -- so ignoring one has nothing
    to ignore, and saying so is better than a row that looks whole."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _reach_kind(ctx.get("power", "")) == "ranged"
        and (t := ctx.get("target")) is not None
        and c.is_(Condition.PRONE, on=t),
    )


@power("f2596", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("chargen.POLEARM",))
def f2596(c: Cast) -> None:
    """The staff half. Polearm is a printed weapon group this engine does
    not carry -- the set is axe, bow, crossbow, heavy blade, implement,
    light blade, mace, spear, staff, unarmed -- so it is dropped rather
    than folded into spear, which would widen the feat."""
    me = c.me

    def staffed(ctx: dict[str, Any]) -> bool:
        gear = _gear(c)
        arm = gear.main if gear is not None else None
        return arm is not None and arm.group == "staff" and arm.two_handed

    for defence in (AC, REF):
        c.bonus(
            defence, 1, on=me, until=When.ENCOUNTER, kind="shield",
            when=staffed,
        )


@power("f2597", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.HAMMER",))
def f2597(c: Cast) -> None:
    """Hammer is not one of this engine's weapon groups, and the whole
    benefit is gated on wielding one. `general_f.f69` gates on
    `group == "hammer"` and is therefore false in every fight -- see the
    report."""


@power("f2598", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2598(c: Cast) -> None:
    """Both groups are real ones, so this one needs no marker."""
    me = c.me
    c.bonus(
        "damage", 5, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _group_in(c, "axe", "heavy blade")
        and (t := ctx.get("target")) is not None
        and c.is_(Condition.PRONE, on=t),
    )


@power("f2599", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2599(c: Cast) -> None:
    """A plain "+1 bonus", so untyped. Being bloodied is asked per blow:
    a target that is whole at the top of the round need not be when the
    swing lands."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (p := get(ctx.get("power", ""))) is not None
        and p.usage is Usage.AT_WILL
        and (t := ctx.get("target")) is not None
        and c.bloodied(on=t),
    )


@power("f2612", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2612(c: Cast) -> None:
    """"Your first turn" is round 1: everybody takes exactly one turn in
    it, so the round number says the same thing the printed line does
    without needing a turn counter of its own."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.world.round <= 1 and _melee(ctx.get("power", "")),
    )


@power("f2625", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2625(c: Cast) -> None:
    """A plain "+1 bonus", so untyped, and asked per attack -- allies
    move. `c.feat` is the printed question and it takes this row's own
    ref."""
    me = c.me
    c.bonus(
        AC, 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            friend != me and c.adjacent(to=friend) and c.feat(c.ref, on=friend)
            for friend in c.allies()
        ),
    )


@power("f2626", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2626(c: Cast) -> None:
    """Cloth is what `chargen` calls both cloth armour and none -- the
    table gives it a bonus of 0 -- so the two printed cases are one."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _armour(c) in ("", "cloth"),
    )


@power("f2721", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2721(c: Cast) -> None:
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _keyword(ctx.get("power", ""), Keyword.PSYCHIC),
    )


@power("f2788", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2788(c: Cast) -> None:
    """The same printed benefit as f2721 behind a different race."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _keyword(ctx.get("power", ""), Keyword.PSYCHIC),
    )


@power("f2727", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2727(c: Cast) -> None:
    """"A +2 racial bonus", which is the word the card prints in front of
    "bonus" and so is the `kind`. The Perception half is a check."""
    c.bonus(
        "save", 2, on=c.me, until=When.ENCOUNTER, kind="racial",
        when=lambda ctx: Keyword.CHARM in ctx.get("keywords", ()),
    )


@power("f2733", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2733(c: Cast) -> None:
    """`chargen.spawn` gives scale and plate a speed of 5 and everything
    else 6, so the printed penalty exists here for scale alone -- chain
    already costs nothing. Handing back the square only where it was
    taken is the printed benefit; a flat +1 would be a speed bonus the
    feat does not grant."""
    me = c.me
    if _armour(c) == "scale":
        c.bonus("speed", 1, on=me, until=When.ENCOUNTER)
    c.bonus(
        AC, 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (a := ctx.get("attacker")) is not None
        and c.size_of(a) in _BIG,
    )


@power("f2767", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2767(c: Cast) -> None:
    """`c.ignore_cover` takes a gate, and `c.cursed` is the printed
    question -- "cursed **by you**", which is what that method asks."""
    c.ignore_cover(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (t := ctx.get("target")) is not None and c.cursed(t),
    )


@power("f2785", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2785(c: Cast) -> None:
    """"Choose a weapon group and an implement type" is a build choice
    nothing records, so it is read as the group the character is holding
    -- `general_e.f1032`'s reasoning -- and the engine has one implement
    group rather than the printed types, which is `general_c.f734`."""
    me = c.me
    gear = _gear(c)
    arm = gear.main if gear is not None else None
    group = arm.group if arm is not None else ""
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: (p := get(ctx.get("power", ""))) is not None
        and (
            (
                Keyword.WEAPON in p.keywords
                and bool(group)
                and bool(holding(c.world, me, group))
            )
            or Keyword.IMPLEMENT in p.keywords
        ),
    )


@power("f2793", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=(*PROFICIENCY, *REROLL))
def f2793(c: Cast) -> None:
    """The mounted damage half plays. Spears and shortbows are the spear
    and bow groups -- the closest this engine says it -- and the
    proficiency grant and the mount's reroll are both dropped."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: c.mount() is not None
        and _group_in(c, "spear", "bow"),
    )


@power("f2794", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.FALCHION", *PROFICIENCY))
def f2794(c: Cast) -> None:
    """Three named weapons rather than a group, and the damage bonus is
    gated on them. Gating on heavy blade instead would hand the bonus to
    every longsword in the game."""


@power("f2611", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2611(c: Cast) -> None:
    """Widens a class feature this engine does have -- and it is written
    out rather than borrowed, because `features/strikers.py:prime_shot`
    gates on `ctx["ranged"]` and an area burst is not the ranged branch.
    The two gates are disjoint, so nothing double-counts."""
    me, world = c.me, c.world

    def alone_in_the_burst(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or _reach_kind(ctx.get("power", "")) != "area_burst":
            return False
        mine = distance_between(world, me, foe)
        return all(
            distance_between(world, mate, foe) >= mine
            for mate in allies(world, me)
            if alive(world, mate)
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=alone_in_the_burst)


# -- riders on your own blows -----------------------------------------------


@power("f2550", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you are hit by a melee attack or a close attack",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.target == me and _melee_or_close(ev.power),
           "a melee or close attack hits you",
       ))
def f2550(c: Cast) -> None:
    """Once per encounter, which is the row's own usage rather than
    anything the body counts."""
    c.temp_hp(c.con_mod, on=c.me)


@power("f2567", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you are bloodied for the first time this encounter",
       on=Trigger(Bloodied, _i_am_bloodied, "you become bloodied"))
def f2567(c: Cast) -> None:
    """"The first time" is the encounter budget, not a counter in the
    body. The combat advantage is the cost of taking the swing, so it is
    laid only if the swing happened -- one relation per enemy, which is
    what `c.grants_advantage` names."""
    foe = next((f for f in c.enemies() if c.adjacent(to=f)), None)
    if foe is None or not c.basic(on=foe):
        return
    for enemy in c.enemies():
        c.grants_advantage(on=c.me, to=enemy, until=When.EONT)


@power("f2587", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss an enemy with a melee attack",
       on=Trigger(
           Miss,
           lambda w, me, ev: ev.attacker == me and _melee(ev.power),
           "you miss with a melee attack",
       ))
def f2587(c: Cast) -> None:
    """A plain "+2 bonus", so untyped, and narrowed to that one enemy --
    the attack context carries both `opportunity` and the target."""
    foe = c.trigger.target
    c.bonus(
        "attack", 2, on=c.me, until=When.SONT,
        when=lambda ctx: ctx.get("opportunity", False)
        and ctx.get("target") == foe,
    )


@power("f2590", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2590(c: Cast) -> None:
    """Two events, because neither answers the sentence alone.
    `ForcedMove` knows who is doing the shoving and what sort it is, and
    fires **before** anybody has moved; `Moved` knows where the creature
    ended up and does not know who sent it there. So the first records
    the victim and the second asks whether it landed beside me.

    The record is cleared on each new shove, so a creature pulled once
    cannot be credited to somebody else's slide later on.
    """
    me = c.me
    pending: set[int] = set()

    def shoved(ev: Any) -> None:
        pending.clear()
        if ev.source == me and ev.how in (Forced.PULL, Forced.SLIDE):
            pending.add(ev.target)

    def landed(ev: Any) -> None:
        if ev.actor not in pending:
            return
        if getattr(ev, "kind_", "") not in ("pull", "slide"):
            return
        if c.adjacent(to=ev.actor) and ev.actor in c.enemies():
            pending.discard(ev.actor)
            c.grants_advantage(on=ev.actor, to=me, until=When.EONT)

    c.watch(ForcedMove, shoved, on=me, until=When.ENCOUNTER)
    c.watch(Moved, landed, on=me, until=When.ENCOUNTER)


@power("f2621", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET, charges=True, once_per_round=True,
       trigger="you score a critical hit with a charge attack",
       on=Trigger(
           Hit,
           lambda w, me, ev: (
               ev.attacker == me
               and ev.critical
               and getattr(ev, "charge", False)
           ),
           "you crit with a charge",
       ))
def f2621(c: Cast) -> None:
    """`charge` rides on `Hit` as a plain attribute, the way
    `opportunity` does, so it is read with `getattr`. `charges=True`
    because the row's whole effect is a charge and the engine measures
    reach before the body otherwise."""
    victim = c.trigger.target
    other = next((f for f in c.enemies() if f != victim), None)
    if other is not None:
        c.charge_at(other)


@power("f2623", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you score a critical hit with a melee attack",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.attacker == me and ev.critical
           and _melee(ev.power),
           "you crit in melee",
       ))
def f2623(c: Cast) -> None:
    c.push(1, on=c.trigger.target)


@power("f2690", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a charm power",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.attacker == me
           and (p := get(ev.power)) is not None
           and Keyword.CHARM in p.keywords,
           "you hit with a charm power",
       ))
def f2690(c: Cast) -> None:
    """"Against you" narrows the penalty, and the attack context carries
    the target -- so the enemy swings at full strength at anybody else,
    which is the printed line."""
    me = c.me
    c.penalty(
        "attack", 2, on=c.trigger.target, until=When.EOTNT,
        when=lambda ctx: ctx.get("target") == me,
    )


@power("f2784", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, _i_hit, "you hit an enemy"))
def f2784(c: Cast) -> None:
    """`c.no_advantage` is laid on the creature that would be *granting*
    it -- `query.has_combat_advantage` reads the modifier off the target
    of the question -- and its gate is handed the attacker, which is how
    "that enemy" is said."""
    foe = c.trigger.target
    c.no_advantage(
        on=c.me, until=When.SONT,
        when=lambda ctx: ctx.get("attacker") == foe,
    )


@power("f2838", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, once_per_round=True,
       dropped=PLAGUE,
       trigger="you hit with an arcane daily attack power",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.attacker == me
           and (p := get(ev.power)) is not None
           and p.usage is Usage.DAILY
           and Keyword.ARCANE in p.keywords,
           "you hit with an arcane daily",
       ))
def f2838(c: Cast) -> None:
    """"One creature you hit" -- a `Hit` is announced per target, so a
    burst would otherwise mark all three. `once_per_round` is what says
    one, and a daily is not cast twice in a round."""
    victim = c.trigger.target
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power("f2839", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=PLAGUE,
       trigger="you hit with an encounter or daily attack power",
       on=Trigger(
           Hit,
           lambda w, me, ev: ev.attacker == me
           and (p := get(ev.power)) is not None
           and p.usage in (Usage.ENCOUNTER, Usage.DAILY),
           "you hit with an encounter or daily power",
       ))
def f2839(c: Cast) -> None:
    """"One defense you targeted" is the defence the power's own attack
    line names, which the header carries as data."""
    p = get(c.trigger.power)
    vs = p.attack.vs if p is not None and p.attack is not None else AC
    c.penalty(vs, 1, on=c.trigger.target, until=When.EONT)


@power("f2844", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.bonus(dtype=)", *PLAGUE))
def f2844(c: Cast) -> None:
    """The extra point plays; its being fire does not. `c.bonus` adds to
    whatever the power was already rolling and cannot name a type of its
    own, which is the hold six other rows in the tree carry."""
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (p := get(ctx.get("power", ""))) is not None
        and p.usage in (Usage.ENCOUNTER, Usage.DAILY),
    )


@power("f2850", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.bonus(dtype=)", *PLAGUE))
def f2850(c: Cast) -> None:
    """Same hold as f2844: the three points land, the necrotic does not."""
    c.bonus(
        "damage", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (t := ctx.get("target")) is not None
        and c.bloodied(on=t),
    )


@power("f2856", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=(*PAIR, *PLAGUE),
       trigger="you use a channel divinity power",
       on=Trigger(
           PowerUsed,
           lambda w, me, ev: ev.actor == me
           and (p := get(ev.power)) is not None
           and p.group == CHANNEL_DIVINITY,
           "you use a channelled power",
       ))
def f2856(c: Cast) -> None:
    """The enemy half of the choice. `Power.group` is what the card's own
    "one power per encounter" line is written as, so "a cf:avenger-f2
    power" is a question the header answers. The ally half hands out one
    blow of two damage types, which nothing says."""
    foe = next((f for f in c.enemies() if c.adjacent(to=f)), None)
    if foe is None:
        return
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, on=foe, until=When.EONT)


@power("f2881", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=(*PAIR, *PLAGUE),
       trigger="a creature marked by you attacks without including you",
       on=Trigger(
           AttackDeclared,
           lambda w, me, ev: ev.attacker != me
           and ev.target != me
           and w.relations.holds(Relation.MARKED_BY, me, ev.attacker),
           "somebody you marked attacks elsewhere",
       ))
def f2881(c: Cast) -> None:
    """Declared on `AttackDeclared` rather than `Hit`, because the
    printed line turns on the attack being *made* and a miss is still an
    attack. The point of necrotic is one of the two types printed."""
    c.flat(1, dtype=DamageType.NECROTIC, on=c.trigger.attacker)
    c.heal(1, on=c.me)


@power("f2852", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=PLAGUE,
       trigger="you save against a poison effect",
       on=Trigger(
           SavingThrow,
           lambda w, me, ev: ev.actor == me
           and ev.saved
           and "poison" in ev.against.lower(),
           "you save against poison",
       ))
def f2852(c: Cast) -> None:
    """`by_me` reads `attacker` then `source`, and `SavingThrow` names
    its subject `actor` -- so the predicate is written out."""
    c.temp_hp(1 + c.level // 2, on=c.me)


@power("f2853", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       dropped=("c.flat(unpreventable=)", *PLAGUE),
       trigger="you target an ally with a healing power",
       on=Trigger(
           PowerUsed,
           lambda w, me, ev: ev.actor == me
           and (p := get(ev.power)) is not None
           and Keyword.HEALING in p.keywords
           and any(t != me for t in ev.targets),
           "you heal an ally",
       ))
def f2853(c: Cast) -> None:
    """`PowerUsed` is announced above the body, and targets are chosen
    before it runs -- so `ev.targets` is the one thing on that event
    worth reading. "Cannot be decreased in any way" is dropped: `c.flat`
    goes through resistance like everything else."""
    friends = [t for t in c.trigger.targets if t != c.me]
    if not friends or not c.may("take the necrotic damage", who=c.me):
        return
    c.flat(3 + c.level // 2, dtype=DamageType.NECROTIC, on=c.me)
    c.heal(c.level, on=friends[0])


@power("f2876", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally within 10 squares regains hit points",
       on=Trigger(
           Healed,
           lambda w, me, ev: ev.source != me
           and ev.target != me
           and team(w, ev.target) == team(w, me)
           and distance_between(w, me, ev.target) <= 10,
           "an ally is healed nearby",
       ))
def f2876(c: Cast) -> None:
    """`ev.source != me` is load-bearing and not a tidiness: `c.heal`
    emits a `Healed` of its own, and without it this row answers itself
    and the stack goes."""
    c.heal(1, on=c.trigger.target)


@power("f2781", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(1), target=NO_TARGET,
       dropped=("c.class_feature()",),
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, _i_dropped, "you drop"))
def f2781(c: Cast) -> None:
    """A death throe: `Dropped` names its subject `actor` and carries no
    target. "Instead of the attack Ferocity grants you" is dropped --
    that racial trait is named in prose with no ref, so there is nothing
    to take away."""
    c.penalty("attack", 2, on=c.me, until=When.EOT)
    for foe in c.enemies():
        if c.adjacent(to=foe):
            c.basic(on=foe)


@power("f2782", level=1, cls="", usage=AT_WILL, action=ActionType.OPPORTUNITY,
       reach=CloseBurst(1), target=NO_TARGET,
       trigger="an enemy provokes an opportunity attack from you",
       on=Trigger(
           OpportunityWindow,
           lambda w, me, ev: ev.actor == me,
           "an enemy provokes an opportunity attack from you",
       ))
def f2782(c: Cast) -> None:
    """`OpportunityWindow.actor` is the creature offered the swing, and
    `provoker` is the one who opened it -- the naming is the other way
    round from every attack event, which is worth saying once."""
    friend = next((a for a in c.allies() if c.adjacent(to=a)), None)
    taker = c.me
    if friend is not None:
        taker = c.choose([c.me, friend], "who gains the bonus") or c.me
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=taker, until=When.EONT, kind="power")


# -- the death-save rows ----------------------------------------------------


@power("f2568", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus('save:death')",))
def f2568(c: Cast) -> None:
    """The surge half plays. `Turns._death_saves` rolls a bare d20 and
    compares it to 10 without reading a single modifier, so a bonus to a
    death saving throw has nowhere to land -- which is the same hold the
    tree already carries once.

    "Since your last rest" is `Health.failures`, which a `World` that
    lives one fight never clears anyway.
    """
    me = c.me

    def rolled(ev: Any) -> None:
        health = c.world.get(me, Health)
        if (
            ev.actor == me
            and ev.against == "death"
            and ev.natural >= 15
            and health is not None
            and health.failures >= 2
        ):
            c.surge(on=me)

    c.watch(SavingThrow, rolled, on=me, until=When.ENCOUNTER)


@power("f2627", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2627(c: Cast) -> None:
    """A natural 20 already heals a surge's worth inside `_death_saves`,
    so this row covers 18 and 19 and leaves 20 alone rather than paying
    twice for it."""
    me = c.me

    def rolled(ev: Any) -> None:
        if ev.actor == me and ev.against == "death" and 18 <= ev.natural < 20:
            c.surge(on=me)

    c.watch(SavingThrow, rolled, on=me, until=When.ENCOUNTER)


@power("f2750", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you roll a natural 1 on an attack roll or a saving throw",
       on=(
           Trigger(
               AttackRolled,
               lambda w, me, ev: ev.attacker == me and ev.natural == 1,
               "you roll a 1 on an attack",
           ),
           Trigger(
               SavingThrow,
               lambda w, me, ev: ev.actor == me and ev.natural == 1,
               "you roll a 1 on a saving throw",
           ),
       ))
def f2750(c: Cast) -> None:
    """Both halves of the printed trigger, because `on=` takes a sequence
    and declaring one of two looks finished. "Your next attack roll **or**
    saving throw" is one bonus, not both, so it is a choice rather than
    two effects laid at once."""
    pick = c.choose(["attack", "save"], "which roll the bonus goes on")
    c.bonus(pick or "attack", 2, on=c.me, until=When.EONT, once=True)


@power("f2720", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make your first attack roll of the encounter",
       on=Trigger(AttackRolled, _i_hit, "you make an attack roll"))
def f2720(c: Cast) -> None:
    """"Roll twice and use either" for a roll already thrown is
    `c.reroll_attack(keep="best")`, which reads the live `AttackResult`
    off the event.

    "First attack roll of the encounter" is **not** `usage=ENCOUNTER`,
    even though it sounds like it: the initiative test can fail, and an
    encounter budget would be spent by the attack that failed it rather
    than by the one the feat is for. So the row is at-will and takes
    itself away once it has actually paid out.
    """
    encounter = getattr(c.world, "encounter", None)
    order = getattr(encounter, "order", None) if encounter else None
    if not order or order[0] != c.me:
        return
    c.reroll_attack(keep="best")
    c.forbid(c.ref, on=c.me, until=When.ENCOUNTER)


@power("f2606", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       dropped=("actions.run_grants_ca",),
       trigger="you run",
       on=Trigger(
           MoveEnd,
           lambda w, me, ev: ev.actor == me and ev.kind_ == "run",
           "you run",
       ))
def f2606(c: Cast) -> None:
    """`MoveEnd` rather than `MoveStart`: the run is over by then, which
    is when the bonus is printed to begin. Running does not actually
    grant combat advantage in this engine -- `actions` builds the longer
    move and lays nothing -- so the second clause is dropped rather than
    written against a rule that is not there."""
    c.bonus(REF, 2, on=c.me, until=When.SONT)


@power("f2620", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you stand up",
       on=Trigger(
           ConditionEnded,
           lambda w, me, ev: ev.target == me
           and ev.condition == Condition.PRONE
           and ev.why == "stood up",
           "you stand up",
       ))
def f2620(c: Cast) -> None:
    """Standing announces itself only as the prone condition ending, and
    `ConditionEnded` names its subject `target` -- `about_me` reads
    `actor` and would be false forever."""
    c.shift(1)


# -- the postures nothing models -------------------------------------------


@power("f2604", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.shift_while_prone()",))
def f2604(c: Cast) -> None:
    """`actions._movement` returns an empty list for a prone creature
    before it reaches the shift branch, so every kind of movement is off
    together and there is no door to open for one of them."""


@power("f2622", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.ignores_difficult(squares=)",))
def f2622(c: Cast) -> None:
    """One square of difficult ground per move. `c.ignores_difficult` is
    all of it or none, and writing the blanket version would hand the
    character a benefit several feats charge much more for."""


@power("f2630", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=TOTAL_DEFENCE)
def f2630(c: Cast) -> None:
    """Total defence is not an action this engine offers, so the trigger
    has no moment."""


@power("f2632", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=TOTAL_DEFENCE)
def f2632(c: Cast) -> None:
    """Same gap as f2630."""


@power("f2723", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=TOTAL_DEFENCE)
def f2723(c: Cast) -> None:
    """Same gap as f2630."""


@power("f2585", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BULL_RUSH)
def f2585(c: Cast) -> None:
    """A bull rush is an action nothing in this engine performs, so
    "whenever you push with one" has no moment either."""


@power("f2592", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BULL_RUSH)
def f2592(c: Cast) -> None:
    """Same gap as f2585."""


@power("f2607", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*BULL_RUSH, "c.opportunity_instead()"))
def f2607(c: Cast) -> None:
    """Both halves are gaps: there is no bull rush, and the opportunity
    window offers an attack with nothing else allowed in it -- which is
    the hold `general_d.f942` carries."""


@power("f2609", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.POLEARM", "c.flank_from(square)"))
def f2609(c: Cast) -> None:
    """Polearm is not a group this engine carries, and "you are
    considered to occupy that square for flanking" wants a creature to
    be asked about from somewhere it is not standing."""


@power("f2610", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Weapon.heavy_thrown", "c.trade_accuracy()"))
def f2610(c: Cast) -> None:
    """Heavy thrown is a printed weapon property the table does not
    carry, and "take -2 to gain +2" is a choice made per attack that
    nothing offers."""


@power("f2629", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.grants_advantage(when=)",))
def f2629(c: Cast) -> None:
    """Combat advantage against a *class* of creature rather than a named
    one. `query.has_combat_advantage` is computed from the board and the
    only modifier it reads is the one that takes advantage away;
    `c.grants_advantage` names one creature and takes no gate."""


@power("f2864", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.ALCHEMICAL",))
def f2864(c: Cast) -> None:
    """Temporary hit points on hitting with a consumable alchemical item
    power. Nothing marks a row as alchemical, so the trigger cannot tell
    one from any other item power."""


@power("f2865", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*BUILD, "Keyword.ALCHEMICAL"))
def f2865(c: Cast) -> None:
    """"Choose a damage type" is a build choice nothing records --
    `c.element` answers it only for a character whose *class* bound one
    -- and the second clause needs the alchemical keyword f2864 wants."""


@power("f2624", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROFICIENCY)
def f2624(c: Cast) -> None:
    """A superior implement. Which implements a character may pick up is
    settled by its chassis in `chargen`, and a `Cast` runs on a board
    with the gear already in hand."""


@power("f2783", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROFICIENCY)
def f2783(c: Cast) -> None:
    """Four named weapons and nothing else. The whole benefit is the
    grant, so there is no second half to keep."""


@power("f2870", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*PROFICIENCY, "chargen.HAMMER"))
def f2870(c: Cast) -> None:
    """The implement half plays for axes, which is a group this engine
    has. Hammers and picks are not, and the proficiency grant belongs to
    `chargen` -- `c.as_implement` writes the fact onto the weapon in
    hand, which is what the printed sentence is about."""
    gear = _gear(c)
    if gear is not None and any(w.group == "axe" for w in gear.held):
        c.as_implement(on=c.me)


@power("f2725", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.grant_action(when=)", "c.resist_forced(when=)"))
def f2725(c: Cast) -> None:
    """Standing as a minor action is the half `c.grant_action` actually
    understands -- it takes `shift` and `stand` and eats anything else.

    Both dropped clauses are the same missing thing: a gate. The printed
    benefit holds only while the companion is adjacent, and neither
    `c.grant_action` nor `c.resist_forced` takes a `when`, so writing the
    adjacency in at arming would freeze a fact that changes every round.
    """
    c.grant_action("stand", ActionType.MINOR, on=c.me, until=When.ENCOUNTER)


@power("f2726", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.grant_action('mount')",))
def f2726(c: Cast) -> None:
    """`c.ride` is the printed sentence and the size test is `Size.order`
    -- `Size` is a `StrEnum`, so a bare `>` sorts the words. Mounting as
    a move action is dropped: `c.grant_action` eats anything that is not
    a shift or a stand."""
    beast = c.companion()
    if beast is None:
        return
    mine, theirs = c.size_of(c.me), c.size_of(beast)
    if theirs.order >= mine.order and theirs.order >= Size.MEDIUM.order:
        c.ride(on=beast)


@power("f2868", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_second_wind()", "c.forgo_healing()"))
def f2868(c: Cast) -> None:
    """Second wind is an action rather than a power: `actions` offers it
    and `Cast.second_wind` runs it, so it announces nothing a trigger can
    answer, and the trade needs the healing given up as well."""


@power("f2845", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("SavingThrow.effect", *PAIR, *PLAGUE))
def f2845(c: Cast) -> None:
    """Splash damage equal to the ongoing damage a failed save leaves
    standing. `SavingThrow` carries the label it was rolled against and
    not the effect, so there is no number to copy."""


@power("f2858", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.on_granted_save()", *PLAGUE))
def f2858(c: Cast) -> None:
    """Your own half plays, read off the label the effect carries. "When
    you grant an ally a saving throw" has no announcement: `c.save` rolls
    one and says nothing about who asked for it."""
    c.bonus(
        "save", 4, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: str(
            getattr(ctx.get("dtype"), "value", ctx.get("dtype") or "")
        ) in ("fire", "necrotic"),
    )


@power("f2840", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PLAGUE)
def f2840(c: Cast) -> None:
    """The jump half is an Athletics check. The saving throw against a
    fall is a real one and is written, gated on the label."""
    c.bonus(
        "save", 4, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: "fall" in str(ctx.get("label", "")).lower(),
    )


# -- not a fight ------------------------------------------------------------


@power("f2717", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2717(c: Cast) -> None:
    """A Stealth check made to stay hidden outdoors. A check."""


@power("f2718", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True,
       dropped=("c.terrain('outdoor')",))
def f2718(c: Cast) -> None:
    """The Perception bonus is a check. Hiding as the fight opens would
    be real, but it is gated on being outdoors with cover, and `c.terrain`
    answers a word no encounter in this tree sets."""


@power("f2728", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2728(c: Cast) -> None:
    """One skill standing in for another, and a language."""


@power("f2835", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2835(c: Cast) -> None:
    """One skill standing in for another, on traps and locks."""


@power("f2836", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2836(c: Cast) -> None:
    """A skill bonus counted in languages known."""


@power("f2867", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2867(c: Cast) -> None:
    """Two rituals and the cost of performing them."""


@power("f2869", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2869(c: Cast) -> None:
    """Checks made to notice things. Not a fight."""


@power("f2878", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2878(c: Cast) -> None:
    """A ritual, and a skill standing in for another to perform it."""


@power("f2882", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True, dropped=PLAGUE)
def f2882(c: Cast) -> None:
    """Two social skills and a disguise. The spellscar clause only
    raises the same bonuses."""


@power("f2888", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2888(c: Cast) -> None:
    """A Diplomacy bonus that climbs and then collapses. All of it is a
    conversation."""
