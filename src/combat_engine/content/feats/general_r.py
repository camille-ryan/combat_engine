"""General feats, offset 480: the implement and weapon-group tail, the
power strike riders, and the heroic multiclass run.

Five things decided nearly every row in this slice.

**An implement has no sort.** `Weapon.group` is `"implement"` and there
is nothing under it, so a holy symbol, a ki focus and a totem are one
object to this engine. Four rows here print a bonus gated on exactly
that distinction and their whole benefit is the gate, so they are
`todo` rather than a bonus quietly handed to every orb in the game.
`chargen.HOLY_SYMBOL`, `chargen.KI_FOCUS` and `chargen.TOTEM` join
`chargen.HAMMER` and the rest of that family.

**Weapon groups are a closed set**: axe, bow, crossbow, heavy blade,
implement, light blade, mace, spear, staff, unarmed. Flail, hammer,
pick and polearm are printed groups this engine does not carry, so the
six rows gated on one are marked; the spear and the staff rows beside
them are written, because those two groups are real.

**Power strike is `p12668`, and it is a ref.** A rider on it is
therefore an ordinary trigger -- but `PowerUsed` announces before the
body and `p12668` declares `NO_TARGET`, so `ev.targets` is empty and
neither event names the creature being struck. `c.damage` stamps the
row's own ref onto the blow, so `DamageApplied.detail == "p12668"` is
the one place the victim and the moment arrive together. What those
rows cannot say is the printed price, "the extra damage is reduced by
1[W]", which is `c.change_dice()`.

**"Doing so expends <your racial power>" is `c.forbid`.** Nothing
spends a use of a row on somebody's behalf, but taking the row away for
the rest of the fight is what spending its single encounter use comes
to, and it is exact rather than approximate. The five rows that print
it are written that way and carry no marker; the reroll they buy is
held to one a fight by the row's own `ENCOUNTER` budget.

**A trait may not hold a printed trigger and a standing modifier both**,
and eleven rows here print both -- a skill bonus and a rider, or two
riders with separate "once per encounter" limits. Those are traits that
arm `c.watch` in the body, which is what `AUTHORING.md` says to do, and
each limit is then a flag of its own rather than one shared budget.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    AreaBurst,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Miss,
    PowerResolved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    Summon,
    Summoned,
    SurgeSpent,
    Trigger,
    TurnEnd,
    When,
    Window,
    about_me,
    get,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.query import defence, distance_between, team, unseen_by

#: A racial power or class feature the benefit names in prose, with no
#: ref behind it for a trigger to hang on.
RACIAL = ("c.on_racial_power()",)
#: A class feature named in prose, and another class's feature likewise.
FEATURE = ("c.class_feature()",)
BORROW = ("c.borrow_feature()",)
#: The brief prints a power by name where a ref belongs.
NAMED = ("spec.power_ref()",)
#: Losing one known power to gain another is settled when the character
#: is built, not on a board.
SWAP = ("chargen.power_swap()",)
#: Which weapons and implements a character may pick up, and which
#: skills it is trained in, are both build-time columns.
PROFICIENCY = ("chargen.proficiency()",)
TRAINING = ("chargen.skill_training()",)
#: Dim light and darkness are not states of a square this engine keeps.
LOW_LIGHT = ("c.low_light()",)
#: A check "made to do <a particular thing>" -- to balance on ice, to
#: find someone hidden, to disable a trap. A skill is the finest grain
#: `skill:<name>` has.
CIRCUMSTANCE = ("c.skill_circumstance()",)
#: A minion is not a thing a row can ask about.
MINION = ("c.is_minion()",)
#: Changing the dice another row rolls -- up, down, or maximised.
DICE = ("c.change_dice()",)
#: Printed implement types the equipment table does not carry. The
#: group is `"implement"` and there is nothing under it.
HOLY_SYMBOL = ("chargen.HOLY_SYMBOL",)
KI_FOCUS = ("chargen.KI_FOCUS",)
TOTEM = ("chargen.TOTEM",)
#: Printed weapon groups this engine does not carry.
FLAIL = ("chargen.FLAIL",)
HAMMER = ("chargen.HAMMER",)
PICK = ("chargen.PICK",)
POLEARM = ("chargen.POLEARM",)

ALL_DEFENCES = (AC, FORT, REF, WILL)
NONE = ActionType.NONE


# -- reading a context ------------------------------------------------------


def _victim(ctx: dict[str, Any]) -> int | None:
    who = ctx.get("target")
    return who if isinstance(who, int) else None


def _holding(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.held)


def _main(c: Cast) -> Any:
    gear = c.world.get(c.me, Gear)
    return gear.main if gear is not None else None


# -- reading an event -------------------------------------------------------


def _used(ref: str):  # noqa: ANN202
    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power == ref

    return when


def _my_check(*skills: str):  # noqa: ANN202
    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.skill.lower() in skills

    return when


def _i_spent_a_point(world: Any, me: int, ev: Any) -> bool:
    return ev.actor == me


def _shadow_summoning(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and Keyword.SHADOW in p.keywords
        and Keyword.SUMMONING in p.keywords
    )


def _i_crit(world: Any, me: int, ev: Any) -> bool:
    return ev.attacker == me and ev.critical


def _i_dropped_a_foe(world: Any, me: int, ev: Any) -> bool:
    return ev.source == me and team(world, ev.actor) != team(world, me)


def _a_foe_dropped(world: Any, me: int, ev: Any) -> bool:
    """The killing blow need not be mine -- the printed line only asks
    that the enemy go down while carrying my shrouds."""
    return team(world, ev.actor) != team(world, me)


def _i_hit_in_melee_with_a_weapon(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.reach is not None
        and p.reach.kind == "melee"
        and Keyword.WEAPON in p.keywords
    )


def _i_hit_with_a_weapon_with_advantage(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    result = getattr(ev, "result", None)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.WEAPON in p.keywords
        and result is not None
        and bool(getattr(result, "advantage", False))
    )


def _i_missed_with_an_axe(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    gear = world.get(me, Gear)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.WEAPON in p.keywords
        and gear is not None
        and any(w.group == "axe" for w in gear.held)
    )


def _my_charge(world: Any, me: int, ev: Any) -> bool:
    return ev.attacker == me and getattr(ev, "charge", False)


def _power_strike_landed(world: Any, me: int, ev: Any) -> bool:
    """`p12668` prints `NO_TARGET` and `PowerUsed` fires above the body,
    so neither use event names the creature being struck. `c.damage`
    stamps the row's ref onto the blow, and this is where it arrives."""
    return ev.source == me and ev.detail == "p12668"


def _the_aura_bit(world: Any, me: int, ev: Any) -> bool:
    """`x6_679` is the aura the brief names; `c.damage` stamps the ref of
    whatever row deals the damage onto `detail`, so this is the hook the
    day that aura lands."""
    return ev.source == me and ev.detail == "x6_679"


def _i_bloodied_them(world: Any, me: int, ev: Any) -> bool:
    """`Bloodied` carries `actor` and no source, so "whenever **you**
    bloody an enemy" cannot be read off it. The crossing is read off the
    blow instead: hit points before the hit above half, after it not."""
    health = world.get(ev.target, Health)
    if health is None or ev.source != me or ev.amount <= 0:
        return False
    if team(world, ev.target) == team(world, me):
        return False
    half = health.max_hp // 2
    return ev.hp <= half < ev.hp + ev.amount


# -- the shapes several rows share ------------------------------------------


def _proficiency(ref: str):  # noqa: ANN202
    """A feat whose entire printed benefit is a proficiency."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=NONE,
           reach=PERSONAL, target=SELF, todo=PROFICIENCY)
    def row(c: Cast) -> None:
        pass

    row.__name__ = ref
    row.__doc__ = (
        "What a character may pick up is settled by `chargen` when it is "
        "built, and the benefit is nothing else."
    )
    return row


def _granted(ref: str, card: str, **kw: Any):  # noqa: ANN202
    """The parent half of a feat whose benefit is "you gain <card>"."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=NONE,
           reach=PERSONAL, target=SELF, **kw)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _spend_once(c: Cast, label: str) -> bool:
    """A per-encounter limit a **triggered** row has to hold itself to.

    `AT_WILL` is the only honest header on a triggered `action=NONE` row
    that prints no limit of its own -- an `ENCOUNTER` one is spent on the
    first firing whether or not the body did anything. The rows below
    whose printed price is "one use of <a racial power>" therefore keep
    the count here: `c.effect` lays the flag and `c.suffering` reads it
    back, which is the only way to ask what is standing on me.
    """
    if c.me in c.suffering(label, include_self=True):
        return False
    c.effect(label, until=When.ENCOUNTER, on=c.me)
    return True


def _surge_when_it_lands(c: Cast, ok: Any) -> None:
    """"Once per encounter, when your <stripe> encounter attack power hits
    at least one enemy, you gain a healing surge."

    The limit is kept on a flag rather than on `c.watch(once=True)`:
    `once` spends the hold only when the handler is seen to have *done*
    something, and `c.regain_surge` moves a number on a component and
    announces nothing at all.
    """
    spent: list[bool] = []

    def landed(ev: Any) -> None:
        p = get(ev.power)
        if spent or ev.attacker != c.me or p is None or not ok(p):
            return
        spent.append(True)
        c.regain_surge(on=c.me)

    c.watch(Hit, landed, until=When.ENCOUNTER)


def _skald_aura(ref: str):  # noqa: ANN202
    """The two printings of the skald's aura are the same card twice."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=MINOR,
           reach=PERSONAL, target=SELF,
           keywords=[Keyword.MARTIAL, Keyword.HEALING],
           dropped=("c.zone_condition()",))
    def card(c: Cast) -> None:
        me = c.me
        c.aura(5, label=ref, until=When.ENCOUNTER, on=me)
        left = [2]

        def spend(who: int) -> None:
            if not left[0]:
                return
            left[0] -= 1
            c.surge(on=who, bonus=c.roll("1d6"))

        for ally in [me, *[a for a in c.allies() if distance_between(c.world, me, a) <= 5]]:
            c.give(ref, spend, on=ally, uses=2, cost=MINOR)

    card.__name__ = ref
    card.__doc__ = (
        "The aura plus the two uses it carries, held on one shared count so "
        "that handing the option to five allies does not hand out ten heals. "
        "What is dropped is the membership: `c.give` puts the option in the "
        "hands of whoever is inside when the aura goes up, and an ally who "
        "walks in afterwards is not offered it. "
        "\"Only once per turn\" goes with it -- the pair of uses is already "
        "the tighter half of the printed limit."
    )
    return card


# -- cold, sight and the types that pass through ----------------------------


@power("f3562", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3562(c: Cast) -> None:
    """"A +1 feat bonus to Will", so `kind="feat"`. The paragon and epic
    steps are out of scope, as every tier line in this project is."""
    me = c.me
    c.resist(5, DamageType.COLD, on=me, until=When.ENCOUNTER)
    c.bonus(WILL, 1, on=me, until=When.ENCOUNTER, kind="feat")


@power("f3563", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=CIRCUMSTANCE)
def f3563(c: Cast) -> None:
    """"A +2 bonus to attack rolls" with no type word, so untyped; the
    Perception half prints "feat" and gets it. `query.unseen_by` is the
    one question that answers "invisible to me" -- there is no
    `Condition.INVISIBLE`, it is a relation plus what sees through it.
    The Perception bonus is widened to every Perception check: "actively
    made to find creatures hidden from you" is finer than `skill:<name>`
    can cut."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (who := _victim(ctx)) is not None and unseen_by(c.world, me, who)
        ),
    )
    c.bonus("skill:perception", 5, on=me, until=When.ENCOUNTER, kind="feat")


@power("f3564", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.ignore_insubstantial()",))
def f3564(c: Cast) -> None:
    """Insubstantial is a property of the creature taking the blow and
    `resolve` halves the damage before any row is consulted, so there is
    nothing for an attack of a named type to step around."""


@power("f3565", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=HOLY_SYMBOL)
def f3565(c: Cast) -> None:
    """Both halves are gated on the implement being a holy symbol, and
    `Weapon.group` is `"implement"` with nothing under it. Gating on the
    group instead would hand the bonus to every orb, rod and wand."""


@power("f3566", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=KI_FOCUS)
def f3566(c: Cast) -> None:
    """Same gap as `f3565`, and a ki focus is the harder half of it: it
    is worn rather than held, and rides on the weapon already in hand."""


@power("f3567", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you summon a creature with a shadow summoning power",
       on=Trigger(PowerUsed, _shadow_summoning, "you use a shadow summoning power"))
def f3567(c: Cast) -> None:
    """`Summoned` says who arrived and names no power, and `PowerUsed`
    names the power and fires above the body -- so neither alone is the
    sentence. Declaring on the use and arming a watcher for the arrival
    puts them together: the watcher is in place before the body runs,
    which is the one thing `PowerUsed` firing early is good for."""

    def arrived(ev: Any) -> None:
        if ev.actor != c.me:
            return
        c.bonus("attack", 1, on=ev.summon, until=When.ENCOUNTER, kind="feat")
        for d in ALL_DEFENCES:
            c.bonus(d, 1, on=ev.summon, until=When.ENCOUNTER, kind="feat")

    c.watch(Summoned, arrived, until=When.EOT)


@power("f3568", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f3568(c: Cast) -> None:
    """A second race's power, chosen at build time, and then a shared
    once-an-encounter budget with `p8278`. Neither half exists: there is
    no race on a character and no way to record the choice."""


# -- the dim light family ---------------------------------------------------


@power("f3569", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3569(c: Cast) -> None:
    """Two gaps, and either alone would sink the row: second wind is an
    action rather than a power and announces nothing a rider can answer,
    and the light in a square is not a thing the grid keeps."""


@power("f3570", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3570(c: Cast) -> None:
    """The whole benefit is gated on standing in dim light or darkness."""


@power("f3571", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you score a critical hit or drop a nonminion enemy",
       on=(
           Trigger(Hit, _i_crit, "you score a critical hit"),
           Trigger(Dropped, _i_dropped_a_foe, "you drop an enemy"),
       ),
       dropped=MINION)
def f3571(c: Cast) -> None:
    """Two printed triggers, so two declared ones. "Nonminion" is the
    dropped half: nothing on the board says which creatures are minions,
    so the row also answers the deaths of the ones it should not."""
    c.conceal(on=c.me, until=When.EONT)


@power("f3572", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you reduce a nonminion enemy to 0 hit points",
       on=Trigger(Dropped, _i_dropped_a_foe, "you drop an enemy"),
       dropped=("Dropped.power", *MINION))
def f3572(c: Cast) -> None:
    """`Dropped` carries `actor`, `dead` and `source` and no power, so
    "with a melee basic attack" has nothing to read -- the row answers
    any killing blow. The nonminion clause goes the same way."""
    ev = c.trigger
    others = [e for e in c.within(2, side="enemy") if e != ev.actor]
    if others:
        c.flat(c.con_mod, dtype=DamageType.NECROTIC, on=others[0])


@power("f3573", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3573(c: Cast) -> None:
    """`c.ignores_difficult` names a *sort* of rough ground -- ice, rubble
    -- and the printed gate here is the light over it instead."""


@power("f3574", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a shadow summoning power",
       on=Trigger(PowerUsed, _shadow_summoning, "you use a shadow summoning power"))
def f3574(c: Cast) -> None:
    """No printed limit, so `AT_WILL`: a triggered `action=NONE` row
    spends a use every time it fires, and `ENCOUNTER` would answer the
    first summon of the fight and nothing after it."""
    c.temp_hp(5, on=c.me)


@power("f3575", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend an action point to take an extra action",
       on=Trigger(ActionPointSpent, _i_spent_a_point, "you spend an action point"))
def f3575(c: Cast) -> None:
    """"Until the end of your current turn" is `When.EOT`, which is the
    turn the point was spent in."""
    c.insubstantial(on=c.me, until=When.EOT)


@power("f3576", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a melee weapon attack",
       on=Trigger(Hit, _i_hit_in_melee_with_a_weapon, "you hit in melee"))
def f3576(c: Cast) -> None:
    c.no_healing(on=c.trigger.target, until=When.EONT)


@power("f3577", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=CIRCUMSTANCE)
def f3577(c: Cast) -> None:
    """Ice walk is the half that plays -- `c.ignores_difficult` takes the
    sort of ground by name. The two skill bonuses are each a check "made
    to" do one thing, which is finer than `skill:<name>` cuts, so they
    would have to be handed to every Endurance and Acrobatics check the
    character ever makes."""
    c.ignores_difficult("ice", on=c.me, until=When.ENCOUNTER)


# -- the r33 run, whose racial powers are refs the tree does not hold -------


@power("f3578", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_return_to_play()",))
def f3578(c: Cast) -> None:
    """"When you return to play" is a moment nothing announces: a
    creature that leaves the board and comes back does so through
    `World.spawn`, which emits `Summoned` only for a summon."""


@power("f3579", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a creature is damaged by your aura",
       on=Trigger(DamageApplied, _the_aura_bit, "your aura damages a creature"))
def f3579(c: Cast) -> None:
    """`p14074` and its aura `x6_679` are refs no file declares yet, so
    this fires the day they land and not before -- the same bet the tree
    already takes on a card handed over by ref before it is written."""
    c.weakened(on=c.trigger.target, until=When.EONT)


@power("f3580", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f3580(c: Cast) -> None:
    """The gate names `q132`-style clauses the parser cannot express and
    the benefit names its racial power in prose, so there is no ref for a
    `PowerUsed` trigger to match."""


@power("f3581", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="immediately after you use p14075",
       on=Trigger(PowerResolved, _used("p14075"), "you use p14075"))
def f3581(c: Cast) -> None:
    """"Immediately after you use" is `PowerResolved`, not `PowerUsed`:
    the latter is announced above the body, where the power has not
    happened yet."""
    c.shift(2)


# -- swaps and borrowed class features --------------------------------------


@power("f3582", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3582(c: Cast) -> None:
    """A use of one row traded for a power of the character's choice."""


@power("f3583", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3583(c: Cast) -> None:
    """Another build's 7th-level class feature, chosen from a list the
    brief prints in prose."""


@power("f3584", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3584(c: Cast) -> None:
    """Loses a known encounter power to gain `p12668`."""


@power("f3585", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3585(c: Cast) -> None:
    """Trades `cf:wizard-arcanist-f0` for a school benefit. The ref is
    printed and the row behind it is declared nowhere, so `c.grant_row`
    has nothing to hand over either."""


@power("f3586", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3586(c: Cast) -> None:
    """The second step of the `f3585` chain, and the same gap."""


@power("f3587", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3587(c: Cast) -> None:
    """The third step of the `f3585` chain, and the same gap."""


@power("f3588", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3588(c: Cast) -> None:
    """A use of `p12710` traded for a rogue encounter power."""


@power("f3589", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3589(c: Cast) -> None:
    """Trades `cf:cleric-templar-f1` for a domain feature chosen from a
    list the brief prints in prose."""


@power("f3590", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3590(c: Cast) -> None:
    """The second step of the `f3589` chain, and the same gap."""


@power("f3591", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3591(c: Cast) -> None:
    """The third step of the `f3589` chain, and the same gap."""


@power("f3592", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3592(c: Cast) -> None:
    """Loses a known rogue encounter power to gain `p12710`."""


# -- the water, and the armour proficiencies --------------------------------


@power("f3594", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.counts_as(kind=)",))
def f3594(c: Cast) -> None:
    """The swim speed and the attack bonus play. "You are considered an
    aquatic creature" does not: `c.is_kind` reads the printed type line
    off the creature and nothing writes to it, so the row cannot make
    itself one -- which also takes breathing underwater with it."""
    me = c.me
    c.mode("swim", 5, on=me, until=When.ENCOUNTER)
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            c.terrain("aquatic")
            and (who := _victim(ctx)) is not None
            and not c.is_kind("aquatic", on=who)
        ),
    )


f3595 = _proficiency("f3595")
f3596 = _proficiency("f3596")
f3597 = _proficiency("f3597")
f3598 = _proficiency("f3598")
f3599 = _proficiency("f3599")
f3600 = _proficiency("f3600")
f3601 = _proficiency("f3601")


# -- power strike, and the weapon groups that ride on it --------------------


@power("f3602", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss with a weapon attack using an axe",
       on=Trigger(Miss, _i_missed_with_an_axe, "you miss with an axe"))
def f3602(c: Cast) -> None:
    """The price is a use of `p12668`, which has exactly one. `c.forbid`
    is how that use is spent -- nothing decrements another row's budget,
    and taking the row away for the fight is what spending its only use
    comes to -- and `_spend_once` is what keeps this row from doing it
    twice, since the header may not."""
    ev = c.trigger
    if not _spend_once(c, c.ref) or not c.may("expend p12668"):
        return
    c.forbid("p12668", on=c.me, until=When.ENCOUNTER)
    c.flat(5, on=ev.target)


@power("f3603", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FLAIL)
def f3603(c: Cast) -> None:
    """Flail is not one of this engine's weapon groups -- the set is axe,
    bow, crossbow, heavy blade, implement, light blade, mace, spear,
    staff, unarmed -- and both halves are gated on wielding one."""


@power("f3604", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FLAIL)
def f3604(c: Cast) -> None:
    """The same missing group, and the whole benefit sits behind it."""


@power("f3605", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=HAMMER)
def f3605(c: Cast) -> None:
    """Hammer is not one of this engine's weapon groups either."""


@power("f3606", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you drop an enemy with a heavy blade",
       on=Trigger(Dropped, _i_dropped_a_foe, "you drop an enemy"),
       dropped=("Dropped.power",))
def f3606(c: Cast) -> None:
    """Heavy blade is a real group, so this one is written. What is
    dropped is which blow did it: `Dropped` names no power, so the group
    is read off what is in hand instead of off the attack. `ENCOUNTER`
    is `p12668`'s single use, which the row spends with `c.forbid`."""
    ev = c.trigger
    if not _holding(c, "heavy blade"):
        return
    others = [e for e in c.within(1, side="enemy") if e != ev.actor]
    if not others:
        return
    c.forbid("p12668", on=c.me, until=When.ENCOUNTER)
    c.basic(on=others[0])


@power("f3607", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.retarget_defence()", "c.expend_row()"))
def f3607(c: Cast) -> None:
    """The whole benefit is "roll this attack against Reflex instead of
    AC", and the damage bonus beside it is only paid when that happens.
    Nothing moves an attack from one defence to another."""


@power("f3608", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.retarget_defence()", "c.expend_row()"))
def f3608(c: Cast) -> None:
    """`f3607` with a mace and Fortitude, and the same gap."""


@power("f3609", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=PICK)
def f3609(c: Cast) -> None:
    """Pick is not one of this engine's weapon groups, and both halves
    are gated on wielding one."""


@power("f3610", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=PICK)
def f3610(c: Cast) -> None:
    """The same missing group. `c.maximise` would say the payout if there
    were a pick to gate it on."""


@power("f3611", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=POLEARM)
def f3611(c: Cast) -> None:
    """Polearm is not one of this engine's weapon groups. Folding it into
    spear would widen the feat over every shortspear in the game."""


@power("f3612", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="your power strike damages a target and you wield a spear",
       on=Trigger(DamageApplied, _power_strike_landed, "power strike lands"),
       dropped=DICE)
def f3612(c: Cast) -> None:
    """Spear is a real group, so the immobilisation plays. The price --
    "the extra damage is reduced by 1[W]" -- does not: by the time the
    blow names its ref the dice are rolled and spent. `AT_WILL` because
    the limit is `p12668`'s own budget, not a second one on top."""
    if _holding(c, "spear"):
        c.immobilized(on=c.trigger.target, until=When.EONT)


@power("f3613", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="your power strike damages a target and you wield a staff",
       on=Trigger(DamageApplied, _power_strike_landed, "power strike lands"))
def f3613(c: Cast) -> None:
    """Staff is a real group and this card charges nothing for the rider,
    so it is the one power strike feat with no marker at all. "Grants
    combat advantage" with nobody named is the whole of my side."""
    if _holding(c, "staff"):
        c.grants_advantage(on=c.trigger.target, to="allies", until=When.EONT)


# -- the channel divinity pairs ---------------------------------------------


f3614 = _granted("f3614", "f3614b")


@power("f3614b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ENEMY, keywords=[Keyword.DIVINE],
       group=CHANNEL_DIVINITY)
def f3614b(c: Cast) -> None:
    """The printed Target is a filter rather than a choice, so it is read
    in the body: unseen by me, and a Will of no more than 12 + my level.
    "Becomes visible to you" is one effect on the seer rather than one per
    creature seen, and it is laid on the **last** pass and not the first:
    `c.see_invisible` is exactly what `query.unseen_by` sees through, so
    granting it on the first target makes every target after it visible
    and therefore no longer a legal one."""
    who = c.target
    if (
        who is not None
        and unseen_by(c.world, c.me, who)
        and defence(c.world, who, WILL) <= 12 + c.level
    ):
        c.grants_advantage(on=who, to=c.me, until=When.EONT)
    if c.last:
        c.see_invisible(on=c.me, until=When.EONT)


f3677 = _granted("f3677", "f3677b")


@power("f3677b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(3), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.FIRE], group=CHANNEL_DIVINITY)
def f3677b(c: Cast) -> None:
    """A wager with two ends, so one flag and two watchers. The reckoning
    is hung on `TurnEnd` rather than on a duration: "at the end of his or
    her next turn" is a payout, and a `When` only takes things away."""
    ally = c.target
    if ally is None:
        return
    done: list[bool] = []

    def landed(ev: Any) -> None:
        if ev.attacker != ally or done:
            return
        done.append(True)
        c.temp_hp(5, on=ally)

    def reckoning(ev: Any) -> None:
        if ev.actor != ally or done:
            return
        done.append(True)
        c.flat(3, dtype=DamageType.FIRE, on=ally)
        for who in c.within(1, of=ally):
            c.flat(3, dtype=DamageType.FIRE, on=who)

    c.watch(Hit, landed, until=When.ENCOUNTER)
    c.watch(TurnEnd, reckoning, until=When.ENCOUNTER)


f3678 = _granted("f3678", "f3678b")


@power("f3678b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(3), target=EACH_ALLY, keywords=[Keyword.DIVINE],
       group=CHANNEL_DIVINITY)
def f3678b(c: Cast) -> None:
    """The bonus is printed "power", so `kind="power"`. "The target grants
    combat advantage" names no beneficiary, and `to="allies"` would hand
    it to *my* side -- the ally is giving it away to the enemy, so the
    grant is laid once per enemy instead."""
    ally = c.target
    if ally is None:
        return
    c.bonus("attack", 1, on=ally, until=When.EONT, kind="power")
    done: list[bool] = []

    def landed(ev: Any) -> None:
        if ev.attacker != ally or done:
            return
        done.append(True)
        c.flat(3, on=ev.target)

    def missed(ev: Any) -> None:
        if ev.attacker != ally or done:
            return
        done.append(True)
        for foe in c.enemies():
            c.grants_advantage(on=ally, to=foe, until=When.EOTNT)

    c.watch(Hit, landed, until=When.ENCOUNTER)
    c.watch(Miss, missed, until=When.ENCOUNTER)


# -- the multiclass feats ---------------------------------------------------


@power("f3615", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*PROFICIENCY, *TRAINING, *KI_FOCUS))
def f3615(c: Cast) -> None:
    """The extra damage plays, held to once a fight by `once=True`. It is
    gated on a one-handed weapon, which is a property the table carries;
    the garrote, the blowgun and the shortbow the card also names are not
    in the table at all, so those three arms of the clause are lost with
    the ki focus proficiency."""
    me = c.me

    def one_handed(ctx: dict[str, Any]) -> bool:
        arm = _main(c)
        return arm is not None and not arm.two_handed

    c.bonus(
        "damage", 0, dice="1d8", on=me, until=When.ENCOUNTER, once=True,
        when=one_handed,
    )


@power("f3616", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*SWAP, "c.apply_poison()"))
def f3616(c: Cast) -> None:
    """A daily power chosen at build time, paid for with a vial of poison
    that is prepared during an extended rest. Both ends are `chargen`."""


@power("f3617", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.apply_poison()",))
def f3617(c: Cast) -> None:
    """Entirely a recipe learned and a vial made between fights."""


@power("f3618", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy granting combat advantage with a weapon",
       on=Trigger(
           Hit, _i_hit_with_a_weapon_with_advantage,
           "you hit an enemy granting you combat advantage",
       ),
       dropped=(*NAMED, *PROFICIENCY, *TRAINING))
def f3618(c: Cast) -> None:
    """"Once per encounter" is the row's own `ENCOUNTER` budget -- a
    triggered `action=NONE` row spends a use every time it fires, which
    is exactly the printed limit here. The advantage is read off the
    `Hit`'s live `AttackResult`; asking `has_combat_advantage` again
    would be too late, a one-shot grant having already been spent."""
    c.flat(c.cha_mod, on=c.trigger.target)


@power("f3619", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.opt_in()",))
def f3619(c: Cast) -> None:
    """The surge half plays. The second clause is a free action offered at
    the moment a power is used -- "lose a healing surge to gain a bonus to
    the damage roll" -- and a trait has no way to put a choice in front of
    a player at somebody else's moment; `c.may` answers inside a body that
    is already running."""
    _surge_when_it_lands(
        c, lambda p: Keyword.ARCANE in p.keywords and p.usage is ENCOUNTER
    )


@power("f3620", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*SWAP, *NAMED))
def f3620(c: Cast) -> None:
    """Loses a known encounter power for one the brief names in prose."""


@power("f3621", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.opt_in()", *FEATURE))
def f3621(c: Cast) -> None:
    """The surge half plays. The trade -- an ally losing a surge so that I
    gain one -- is the same "offer a choice at somebody else's moment" as
    `f3619`, and the third clause unwinds a class feature named in prose,
    which there is nothing to unwind."""
    _surge_when_it_lands(
        c, lambda p: Keyword.DIVINE in p.keywords and p.usage is ENCOUNTER
    )


@power("f3622", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.regain_surge(until=)",))
def f3622(c: Cast) -> None:
    """Two printed clauses with two separate "once" limits, so a trait
    with two watchers rather than a triggered row with one shared budget.
    What is dropped is the surge expiring unspent at the end of the
    fight -- a surge is a plain number and nothing holds one on loan."""
    me = c.me
    _surge_when_it_lands(
        c, lambda p: Keyword.MARTIAL in p.keywords and p.usage is ENCOUNTER
    )

    def bled(ev: Any) -> None:
        if ev.actor == me:
            c.regain_surge(on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER)


@power("f3623", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3623(c: Cast) -> None:
    """Both halves play, so no marker. `SurgeSpent` is emitted from every
    place that decrements a surge, which is what makes the second clause
    writable at all; "against opportunity attacks" is a gate the attack
    context answers through `opportunity`."""
    me = c.me
    _surge_when_it_lands(
        c, lambda p: p.cls == "monk" and p.usage is ENCOUNTER
    )

    def surged(ev: Any) -> None:
        if ev.actor != me:
            return
        c.bonus("speed", 2, on=me, until=When.EONT)
        for d in ALL_DEFENCES:
            c.bonus(
                d, 4, on=me, until=When.EONT,
                when=lambda ctx: ctx.get("opportunity", False),
            )

    c.watch(SurgeSpent, surged, until=When.ENCOUNTER)


@power("f3624", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3624(c: Cast) -> None:
    """"Two bonus healing surges" is a pool the character carries into the
    fight, so it is handed over as the trait arms."""
    _surge_when_it_lands(
        c, lambda p: Keyword.PRIMAL in p.keywords and p.usage is ENCOUNTER
    )
    c.regain_surge(2, on=c.me)


@power("f3625", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.regain_points()",))
def f3625(c: Cast) -> None:
    """The surge half plays; an augmented at-will is a psionic power like
    any other, so the keyword covers both arms of the printed trigger.
    Turning a surge back into power points is the dropped half."""
    _surge_when_it_lands(c, lambda p: Keyword.PSIONIC in p.keywords)


@power("f3626", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, *PROFICIENCY))
def f3626(c: Cast) -> None:
    """Three class features named in prose, with the surge pool they cost
    named beside them. Nothing here is a thing a `Cast` can lay."""


@power("f3627", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3627(c: Cast) -> None:
    """A wilderness knack is a knack for the wilderness: the whole benefit
    is exploration, so this is deliberately inert rather than unwritten."""


@power("f3628", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=(*PROFICIENCY, *TRAINING))
def f3628(c: Cast) -> None:
    """`p1455` is a ref and the row is declared, so the power half is an
    ordinary `c.grant_row`. "Once per day" is not a fight's business --
    the row carries its own usage and the day is `chargen`'s clock."""
    c.grant_row("p1455", on=c.me, until=When.ENCOUNTER)


@power("f3629", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*NAMED, *PROFICIENCY, *TRAINING))
def f3629(c: Cast) -> None:
    """`p12660` is a ref and is declared. The second power is printed by
    name only, so there is nothing for a second `c.grant_row`."""
    c.grant_row("p12660", on=c.me, until=When.ENCOUNTER)


@power("f3630", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*SWAP, *FEATURE))
def f3630(c: Cast) -> None:
    """An at-will traded for one of the powers a class feature grants, and
    the feature is named in prose."""


@power("f3631", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3631(c: Cast) -> None:
    """An encounter power traded for `p13588`."""


@power("f3632", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=SWAP)
def f3632(c: Cast) -> None:
    """An encounter power traded for `p12668`."""


@power("f3633", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.pact_boon()", *PROFICIENCY))
def f3633(c: Cast) -> None:
    """A pact boon chosen at build time, and the two powers it carries."""


# -- the assassin's shrouds -------------------------------------------------


@power("f3635", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3635(c: Cast) -> None:
    """Combat advantage is a relation rather than a modifier, so it cannot
    be laid as a standing `when=` gate -- it has to be laid on a named
    creature. The declaration is the last moment that is still early
    enough, so the grant goes on at `Window.BEFORE` and is spent by the
    roll it was laid for."""
    me = c.me

    def declared(ev: Any) -> None:
        if ev.attacker == me and c.shrouds(on=ev.target) > 0:
            c.grants_advantage(on=ev.target, to=me, until=When.EOT, once=True)

    c.watch(
        AttackDeclared, declared, until=When.ENCOUNTER, window=Window.BEFORE
    )


@power("f3636", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_invoke_shrouds()",))
def f3636(c: Cast) -> None:
    """`c.spend_shrouds` takes the whole count off in one step and says so
    to nobody, so "they are not removed" has no moment to answer."""


@power("f3637", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy carrying two or more of your shrouds drops",
       on=Trigger(Dropped, _a_foe_dropped, "an enemy drops"))
def f3637(c: Cast) -> None:
    """Moving a shroud is laying one: `c.shroud` is the only verb and the
    count on a dead creature is nobody's business, so the two shrouds are
    laid on the new victim and the old ones left where they fell."""
    ev = c.trigger
    if c.shrouds(on=ev.actor) < 2:
        return
    others = [e for e in c.within(5, side="enemy") if e != ev.actor]
    if not others or not c.may("move the shrouds"):
        return
    c.shroud(on=others[0])
    c.shroud(on=others[0])


@power("f3638", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=DICE)
def f3638(c: Cast) -> None:
    """The whole benefit is the dice another row rolls."""


@power("f3639", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=KI_FOCUS)
def f3639(c: Cast) -> None:
    """Gated on the implement being a ki focus, which has no group."""


@power("f3640", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.ability_for(ref)", *CIRCUMSTANCE))
def f3640(c: Cast) -> None:
    """One half swaps the ability a skill is rolled with, the other is an
    Arcana check "related to traps or hazards". Neither is a grain
    `skills.modifier` cuts at."""


@power("f3641", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*HAMMER, *PROFICIENCY))
def f3641(c: Cast) -> None:
    """A warhammer is a hammer, and hammer is not a group this engine
    carries, so `c.as_implement` and `c.make_thrown` have nothing to
    take hold of."""


# -- the familiar, the barbarian and the druid ------------------------------


@power("f3644", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3644(c: Cast) -> None:
    """Carrying an unattended five-pound object. There is no encumbrance
    and no inventory on the board, so this is deliberately inert."""


@power("f3645", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*FEATURE, *TRAINING))
def f3645(c: Cast) -> None:
    """Berserker Fury is a class feature named in prose, and the benefit
    is nothing but that feature with a day's limit on it."""


@power("f3646", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=SWAP)
def f3646(c: Cast) -> None:
    """The card printed beside the feat is `f3646b`, and it is the same
    door `p5032` already is; the feat's own copy is what is handed over,
    so the card is reachable rather than orphaned. The second sentence --
    trading an extra use of the card for a daily attack power -- is a
    build-time exchange."""
    c.grant_row("f3646b", on=c.me, until=When.ENCOUNTER)


@power("f3646b", level=1, cls="", usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.PRIMAL, Keyword.POLYMORPH], once_per_round=True,
       dropped=("c.in_beast_form()",))
def f3646b(c: Cast) -> None:
    """The printed form "normally doesn't change your game statistics", so
    `c.form` is taken bare -- no conditions, no modes -- with a minor
    action as the way back out, which is the "or vice versa". What is
    dropped is the restriction the form carries: nothing asks whether a
    creature is in beast form, so "you can't use powers that lack the
    beast form keyword" cannot be enforced, and the shift on the way back
    goes with it. The equipment clauses are bookkeeping with no combat
    consequence."""
    c.form(label="beast form", revert=MINOR, until=When.ENCOUNTER)


@power("f3647", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3647(c: Cast) -> None:
    """"When you enter your Berserker Fury" is a moment a class feature
    named in prose would have to announce."""


@power("f3648", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=SWAP)
def f3648(c: Cast) -> None:
    """Hands over the card printed beside it. Giving a known daily up in
    exchange is settled when the character is built."""
    c.grant_row("f3648b", on=c.me, until=When.ENCOUNTER)


@power("f3648b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=NO_TARGET,
       keywords=[Keyword.PRIMAL, Keyword.SUMMONING], summon=Summon(),
       dropped=("c.dismiss_summon()",))
def f3648b(c: Cast) -> None:
    """The block prints no numbers at all, so the summon takes `Summon`'s
    defaults -- the summoner's defences, a surge's worth of hit points, no
    attack of its own. The surge it costs when it falls is the printed
    mechanic and is watched for; dismissing it early as a minor action has
    no verb."""
    beast = c.summon_inline(get(c.ref).summon, at=c.origin)

    def fell(ev: Any) -> None:
        if ev.actor == beast:
            c.spend_surge(on=c.me)

    c.watch(Dropped, fell, until=When.ENCOUNTER)


# -- the racial powers a gate pins by ref -----------------------------------


@power("f3649", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a Stealth check",
       on=Trigger(SkillCheck, _my_check("stealth"), "you make a Stealth check"))
def f3649(c: Cast) -> None:
    """`p377` is pinned by the gate, so "expends fade away" has a ref.
    Nothing decrements another row's uses, but `c.forbid` for the rest of
    the fight is what spending the only use of an encounter power comes
    to, and `_spend_once` holds this row to the one the racial power can
    pay for."""
    if not _spend_once(c, c.ref) or not c.may("expend p377"):
        return
    c.forbid("p377", on=c.me, until=When.ENCOUNTER)
    c.reroll_check(keep="best")


@power("f3650", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(
           Miss, lambda w, me, ev: ev.target == me and ev.attacker != me,
           "an enemy misses you",
       ),
       todo=("c.use_power()",))
def f3650(c: Cast) -> None:
    """The trigger is declared and real; what is missing is the benefit,
    which is entirely "you can use `p377`". Nothing fires one row from
    inside another, so there is no half of this to keep."""


@power("f3651", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3651(c: Cast) -> None:
    """Heroic tier, so 3."""
    pet = c.familiar()
    if pet is not None and c.distance(pet) <= 10:
        c.heal(3, on=c.me)


@power("f3652", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3652(c: Cast) -> None:
    """Both bonuses print "feat". The language clause is not a mechanic
    this engine has anywhere -- there is no speech, so there is nothing
    to drop rather than a clause that has been silently lost."""
    me = c.me
    c.bonus("skill:bluff", 2, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus("skill:diplomacy", 2, on=me, until=When.ENCOUNTER, kind="feat")


@power("f3653", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=NAMED)
def f3653(c: Cast) -> None:
    """"Choose one wizard cantrip" names a list of powers in prose and no
    ref, so `c.grant_row` has nothing to be handed."""


@power("f3654", level=1, cls="", usage=ENCOUNTER, action=ActionType.FREE,
       reach=PERSONAL, target=SELF)
def f3654(c: Cast) -> None:
    """`p1449` is pinned by the gate. `c.forbid` spends it, as in `f3649`;
    the advantage is against "each enemy adjacent to you", so it is laid
    once per neighbour."""
    me = c.me
    beside = c.within(1, side="enemy")
    if not beside:
        return
    c.forbid("p1449", on=me, until=When.ENCOUNTER)
    for foe in beside:
        c.grants_advantage(on=foe, to=me, until=When.EONT)


@power("f3656", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3656(c: Cast) -> None:
    """A Thievery check at a distance, which is a lock or a trap and never
    an attack. Deliberately inert rather than unwritten."""


@power("f3658", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1217",
       on=Trigger(PowerUsed, _used("p1217"), "you use p1217"))
def f3658(c: Cast) -> None:
    """"A +5 power bonus to your **next** Bluff check" is `once=True`,
    which spends the modifier on the first check that could read it."""
    c.bonus(
        "skill:bluff", 5, on=c.me, until=When.EONT, kind="power", once=True
    )


@power("f3659", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a Diplomacy or Intimidate check",
       on=Trigger(
           SkillCheck, _my_check("diplomacy", "intimidate"),
           "you make a Diplomacy or an Intimidate check",
       ))
def f3659(c: Cast) -> None:
    """`p15829` is pinned by the gate and is declared nowhere yet, which
    costs this row nothing: `c.forbid` names a ref and does not need the
    row to exist to keep the character off it."""
    if not _spend_once(c, c.ref) or not c.may("expend p15829"):
        return
    c.forbid("p15829", on=c.me, until=When.ENCOUNTER)
    c.reroll_check(keep="best")


@power("f3661", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=(*NAMED, *PROFICIENCY, *TRAINING))
def f3661(c: Cast) -> None:
    """`f3628` with a different power, and this one is printed by name
    rather than by ref, which is the whole difference between them."""


@power("f3662", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3662(c: Cast) -> None:
    """A printed trigger and a standing modifier on one card, so the row
    is a trait and the triggered half is a `c.watch`. "Immediately after
    you use" is `PowerResolved`: `PowerUsed` fires above the body, and a
    teleport laid there would happen before the step it follows."""
    me = c.me
    c.bonus("skill:arcana", 2, on=me, until=When.ENCOUNTER, kind="feat")

    def stepped(ev: Any) -> None:
        if ev.actor == me and ev.power == "p1450":
            c.teleport(2)

    c.watch(PowerResolved, stepped, until=When.ENCOUNTER)


@power("f3663", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a Bluff or Diplomacy check",
       on=Trigger(
           SkillCheck, _my_check("bluff", "diplomacy"),
           "you make a Bluff or a Diplomacy check",
       ))
def f3663(c: Cast) -> None:
    """`f3659` with `p15842` and a different pair of skills."""
    if not _spend_once(c, c.ref) or not c.may("expend p15842"):
        return
    c.forbid("p15842", on=c.me, until=When.ENCOUNTER)
    c.reroll_check(keep="best")


# -- the bard's aura, printed twice -----------------------------------------


@power("f3664", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=(*PROFICIENCY, *TRAINING, "c.uses_per_day()"))
def f3664(c: Cast) -> None:
    """Hands over the card printed beside it rather than `f3668b`, which
    is the same card on the other feat's page. The day's limit on the
    healing is a clock no fight can see."""
    c.grant_row("f3664b", on=c.me, until=When.ENCOUNTER)


f3664b = _skald_aura("f3664b")


@power("f3668", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3668(c: Cast) -> None:
    """"You swap X for Y" is both halves and both are sayable: `c.forbid`
    takes the row away, `c.grant_row` hands the other over. The number of
    uses the aura's healing gets is `p2339`'s, which is one, and the card
    carries two -- so the count is trimmed rather than left wrong."""
    me = c.me
    c.forbid("p2339", on=me, until=When.ENCOUNTER)
    c.grant_row("f3668b", on=me, until=When.ENCOUNTER)


f3668b = _skald_aura("f3668b")


# -- the r44 and r61 runs ---------------------------------------------------


@power("f3665", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=AreaBurst(1, 5), target=NO_TARGET, dropped=RACIAL)
def f3665(c: Cast) -> None:
    """The terrain plays. What is dropped is the price -- a use of a
    racial power the benefit names in prose, with no ref behind it, so
    the row is free where the card charges for it. "For your enemies" is
    the zone plus `c.ignores_difficult_in`, which is exactly that."""
    zone = c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)
    c.ignores_difficult_in(zone, side="ally")


@power("f3666", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3666(c: Cast) -> None:
    """The saving throw bonus is the whole of the mechanics; not eating
    and not sleeping belong to the calendar. The save context carries
    `ongoing`, which is what "against ongoing damage" asks."""
    c.bonus(
        "save", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(ctx.get("ongoing")),
    )


@power("f3669", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a charge attack",
       on=Trigger(
           AttackDeclared, _my_charge, "you charge", window=Window.BEFORE
       ))
def f3669(c: Cast) -> None:
    """Combat advantage is a relation on a named creature, so it is laid
    at the declaration and spent by the roll it was laid for. `charge`
    rides on `AttackDeclared` as a plain attribute, hence the `getattr`
    in the predicate."""
    c.grants_advantage(on=c.trigger.target, to=c.me, until=When.EOT, once=True)


@power("f3670", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.share_space()",))
def f3670(c: Cast) -> None:
    """Two creatures in one square is not a thing the grid allows, so the
    condition the whole benefit is gated on can never be true."""


@power("f3671", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=TOTEM)
def f3671(c: Cast) -> None:
    """Both halves are gated on the implement being a totem, and
    `Weapon.group` is `"implement"` with nothing under it."""


@power("f3672", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3672(c: Cast) -> None:
    """"Two-handed melee weapon" is two properties the table does carry,
    so no marker. The damage half is gated on `charge`, which the damage
    context does hand out -- unlike `ranged`, which it does not."""
    me = c.me

    def two_handed_melee(ctx: dict[str, Any]) -> bool:
        arm = _main(c)
        return arm is not None and arm.two_handed and not arm.ranged

    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
        when=two_handed_melee,
    )
    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("charge", False) and two_handed_melee(ctx),
    )


@power("f3673", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=(*RACIAL, "c.reach_bonus()"))
def f3673(c: Cast) -> None:
    """The Acrobatics bonus plays. The reach half wants two things at
    once: a racial power named in prose to hang on, and a way to lengthen
    a melee reach, which `c.threatens` does for opportunity attacks and
    for nothing else."""
    c.bonus("skill:acrobatics", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3674", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3674(c: Cast) -> None:
    """A disguise assumed during a short rest and undone as a minor
    action. There is no recognition on the board, so it is inert."""


@power("f3675", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=(*PROFICIENCY, *TRAINING))
def f3675(c: Cast) -> None:
    """Hands over the card printed beside it, which is `p15850` reprinted
    on the feat's page."""
    c.grant_row("f3675b", on=c.me, until=When.ENCOUNTER)


@power("f3675b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       out_of_combat=True)
def f3675b(c: Cast) -> None:
    """A Requirement of "you must use this power during an extended rest"
    and an Effect that is a hint about the future. Narrative from end to
    end, so it is declared inert rather than left unwritten."""


@power("f3679", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.effects_on()",))
def f3679(c: Cast) -> None:
    """`c.transfer` would say the move and `c.ongoing` the increase, but
    neither can be reached: nothing lists the effects standing on *me*.
    `c.suffering` finds what I have laid on other people, which is the
    opposite question."""


@power("f3680", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3680(c: Cast) -> None:
    """Both halves are gated on the light in a square, and the second
    wants second wind to announce itself as well."""


@power("f3682", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you bloody an enemy with an attack",
       on=Trigger(DamageApplied, _i_bloodied_them, "you bloody an enemy"))
def f3682(c: Cast) -> None:
    """Declared on the blow rather than on `Bloodied`, which carries
    `actor` and no source and so cannot say whose attack did it. The
    extra five cannot loop: the second packet is dealt to a creature
    already under half, so the crossing is not made twice."""
    c.flat(5, on=c.trigger.target)


@power("f3683", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3683(c: Cast) -> None:
    """A standing bonus and a printed rider, so a trait with a `c.watch`.
    The save context carries the effect's `conditions`, which is how
    "dazing, stunning or dominating" is picked out, and its `ongoing`
    and `dtype` for the psychic burn. The payout half has only the
    effect's label to read -- `SavingThrow` carries `against` and no
    conditions -- so it matches on the same words by name."""
    me = c.me
    numbing = frozenset(
        {Condition.DAZED, Condition.STUNNED, Condition.DOMINATED}
    )

    def mine(ctx: dict[str, Any]) -> bool:
        if ctx.get("conditions", frozenset()) & numbing:
            return True
        return bool(ctx.get("ongoing")) and ctx.get("dtype") is DamageType.PSYCHIC

    c.bonus("save", 2, on=me, until=When.ENCOUNTER, kind="feat", when=mine)

    def shook_it_off(ev: Any) -> None:
        label = str(ev.against).lower()
        if ev.actor != me or not ev.saved:
            return
        if not any(w in label for w in ("dazed", "stunned", "dominated", "psychic")):
            return
        c.shift(1)
        for d in ALL_DEFENCES:
            c.bonus(d, 2, on=me, until=When.SONT)

    c.watch(SavingThrow, shook_it_off, until=When.ENCOUNTER)
