"""General feats, offset 480: the implement and weapon-group tail, the
power strike riders, and the heroic multiclass run.

Five things decided nearly every row in this slice.

**An implement has no *group* of its own, but it has a ref.**
`Weapon.group` is `"implement"` for all of them, so `_holding` cannot
tell a wand from a totem -- and every card here names exactly one, so
`_wielding` asks by ref instead. The rows once marked
`chargen.HOLY_SYMBOL` and its family are written.

**Weapon groups are the printed table's**, and flail, hammer, pick and
polearm are all in it. `chargen` deals them, so the rows gated on one
ask `_holding` like any other and none of them is marked.

**Power strike is `p12668`, and it is a ref.** A rider on it is
therefore an ordinary trigger -- but `PowerUsed` announces before the
body and `p12668` declares `NO_TARGET`, so `ev.targets` is empty and
neither event names the creature being struck. `c.damage` stamps the
row's own ref onto the blow, so `detail == "p12668"` is the one place
the victim and the moment arrive together. Those rows hang on
**`DamageRolled` rather than `DamageApplied`**: the same `detail`, and
the total is still mutable there, which is what lets `c.reduce` charge
the printed price, "the extra damage is reduced by 1[W]".

**"Doing so expends <your racial power>" has two spellings here.**
`c.expend_row` is the exact one -- a use goes and the row never runs --
and `f3606`, `f3607`, `f3608` and `f3665` use it. Five older rows
(`f3602`, `f3649`, `f3654`, `f3659`, `f3663`) still say it with
`c.forbid` plus `_spend_once`, which takes the row away for the fight
instead. That is the same outcome for a racial power with one use and
not the same sentence; they are worth converting, and are left alone
here only because they play correctly as written. `c.expend_row`
refuses a row the creature has not got, which is the Requirement --
and is why `f3659`, whose `p15829` is declared nowhere, is the one that
cannot simply be swapped over.

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
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Melee,
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
    Swap,
    Trigger,
    TurnEnd,
    Usage,
    When,
    Window,
    ZoneEntered,
    about_me,
    get,
    power,
)
from combat_engine.engine.basic import MELEE as BASIC_MELEE
from combat_engine.engine.components import Health
from combat_engine.engine.query import defence, distance_between, team, unseen_by

#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one of them.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
#: The three racial powers of `r44`, which the page offers as a choice.
R44 = ("p7441", "p7442", "p7443")
#: A class feature named in prose, and another class's feature likewise.
FEATURE = ("c.class_feature()",)
#: A feature **option** the card names by name and the brief prints in
#: prose -- a school of magic, a divine domain, a weapon specialisation.
#: Handing a declared feature over is `c.grant_row` now and picking one
#: out of a list is `c.borrow_row`, so these rows are not waiting on the
#: borrowing any more; they are waiting on there being anything to point
#: at. None of the options is a ref in the tree.
BORROW = ("spec.feature_ref()",)
#: The brief prints a power by name where a ref belongs.
NAMED = ("spec.power_ref()",)
#: A suit of armour or a shield, which is not the same column as the
#: weapons and implements `chargen.proficiency` deals.
ARMOUR = ("chargen.armor_proficiency()",)
TRAINING = ("chargen.skill_training()",)
#: Dim light and darkness are not states of a square this engine keeps.
LOW_LIGHT = ("c.low_light()",)
#: Changing the dice another row rolls -- up, down, or maximised.
DICE = ("c.change_dice()",)

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


def _wielding(c: Cast, *refs: str) -> bool:
    """Which implement, by ref. The seven share one group, so `_holding`
    cannot tell a wand from a totem and every one of these cards names
    exactly one."""
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.ref in refs for w in gear.held)


# -- reading an event -------------------------------------------------------


def _used_any(*refs: str):  # noqa: ANN202
    """"A <race> racial power", where the race prints more than one."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return when


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


def _i_dropped_a_nonminion(world: Any, me: int, ev: Any) -> bool:
    """"You reduce a nonminion enemy to 0 hit points."

    `c.is_minion` is a `Cast` verb and a predicate is handed
    `(world, me, ev)`, so a bare cast is made to ask -- the same probe
    `weapon_c._type_words` uses for a type line.
    """
    return _i_dropped_a_foe(world, me, ev) and not Cast(
        world=world, me=me, ref=""
    ).is_minion(on=ev.actor)


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


def _my_basic_against_ac(group: str):  # noqa: ANN202
    """"When you make a melee basic attack with a <group> against AC."

    `basic.MELEE` is the ref the engine gives a melee basic, which is what
    `AttackDeclared.power` carries for one.
    """

    def when(world: Any, me: int, ev: Any) -> bool:
        gear = world.get(me, Gear)
        return (
            ev.attacker == me
            and ev.power == BASIC_MELEE
            and ev.vs == AC
            and gear is not None
            and any(w.group == group for w in gear.held)
        )

    return when


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
    """A feat whose entire printed benefit is an armour proficiency.

    Re-aimed: `chargen.proficiency` answers weapons and implements, and
    a suit of armour is a different column -- `ClassLine.armour` is one
    string and `ClassLine.shield` is a number, so there is nowhere for a
    second suit a character *may* wear to be written down.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=NONE,
           reach=PERSONAL, target=SELF, todo=ARMOUR)
    def row(c: Cast) -> None:
        pass

    row.__name__ = ref
    row.__doc__ = (
        "What a character may wear is settled by `chargen` when it is "
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
           keywords=[Keyword.MARTIAL, Keyword.HEALING])
    def card(c: Cast) -> None:
        me = c.me
        aura = c.aura(5, label=ref, until=When.ENCOUNTER, on=me)
        left = [2]
        handed: set[int] = set()

        def spend(who: int) -> None:
            if not left[0] or not c.in_my_aura(who, label=ref):
                return
            left[0] -= 1
            c.surge(on=who, bonus=c.roll("1d6"))

        def offer(who: int) -> None:
            if who in handed:
                return
            handed.add(who)
            c.give(ref, spend, on=who, uses=2, cost=MINOR)

        offer(me)
        for ally in c.allies():
            if distance_between(c.world, me, ally) <= 5:
                offer(ally)

        def walked_in(ev: Any) -> None:
            if ev.zone == aura and team(c.world, ev.actor) == team(c.world, me):
                offer(ev.actor)

        c.watch(ZoneEntered, walked_in, until=When.ENCOUNTER)

    card.__name__ = ref
    card.__doc__ = (
        "The aura plus the two uses it carries, held on one shared count so "
        "that handing the option to five allies does not hand out ten heals. "
        "The membership is written now: `c.aura` makes a zone, so "
        "`ZoneEntered` is what an ally walking in emits, and the option is "
        "handed over then. Standing inside is asked again at the moment of "
        "spending, through `c.in_my_aura`, so an ally who walks back out "
        "still holding the option cannot spend it. "
        "\"Only once per turn\" is not marked: the pair of uses is already "
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
       reach=PERSONAL, target=SELF)
def f3563(c: Cast) -> None:
    """"A +2 bonus to attack rolls" with no type word, so untyped; the
    Perception half prints "feat" and gets it. `query.unseen_by` is the
    one question that answers "invisible to me" -- there is no
    `Condition.INVISIBLE`, it is a relation plus what sees through it.
    The Perception half is laid flat because the only Perception this
    engine ever consults is a creature looking for a hider -- there is no
    other check for the circumstance to exclude."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (who := _victim(ctx)) is not None and unseen_by(c.world, me, who)
        ),
    )
    c.bonus("skill:perception", 5, on=me, until=When.ENCOUNTER, kind="feat")


@power("f3564", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3564(c: Cast) -> None:
    """The halving is not a resistance and `deal_damage` reads a flag of
    its own for it, which `c.ignore_resistance(insubstantial=True)` sets.
    `amount=0` because the card waives the halving alone: the blanket
    form would also walk through every resistance in the game.

    Gated on the row's keywords rather than on the blow's type, which is
    what "your necrotic attack powers" says -- a necrotic power whose
    rider deals untyped damage is still one."""

    def necrotic_or_poison(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and bool(
            {Keyword.NECROTIC, Keyword.POISON}.intersection(row.keywords)
        )

    c.ignore_resistance(
        0, on=c.me, until=When.ENCOUNTER, insubstantial=True,
        when=necrotic_or_poison,
    )


@power("f3565", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:holy-symbol",), dropped=("c.no_advantage(unless=)",))
def f3565(c: Cast) -> None:
    """The attack bonus plays -- heroic tier, so +1 -- and so does the
    rider: `c.no_advantage` is exactly "your enemies cannot gain combat
    advantage against you", laid on the swing. A standing modifier and a
    printed trigger on one card, so the trigger is a `c.watch`.

    Dropped: the carve-out, "unless you use a power or another ability
    that states that you grant combat advantage". `c.no_advantage` shuts
    every branch at once and nothing reopens one for a later grant."""
    me = c.me

    def holding(ctx: dict[str, Any]) -> bool:
        return _wielding(c, "w:holy-symbol")

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=holding)

    def swung(ev: Any) -> None:
        row = get(ev.power)
        if (
            ev.attacker == me
            and row is not None
            and Keyword.IMPLEMENT in row.keywords
            and _wielding(c, "w:holy-symbol")
        ):
            c.no_advantage(on=me, until=When.SONT)

    c.watch(AttackDeclared, swung, until=When.ENCOUNTER)

@power("f3566", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:ki-focus",))
def f3566(c: Cast) -> None:
    """Both halves. Heroic tier, so +1 each, and the damage half is gated
    on the target being bloodied rather than on the caster."""
    me = c.me

    def bloodied_foe(ctx: dict[str, Any]) -> bool:
        who = _victim(ctx)
        return (
            _wielding(c, "w:ki-focus")
            and who is not None
            and c.bloodied(on=who)
        )

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: _wielding(c, "w:ki-focus"))
    c.bonus("damage", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=bloodied_foe)

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
    """`SecondWind` says the second wind happened; the light in a square
    is still not a thing the grid keeps, and the whole benefit is gated on
    it."""


@power("f3570", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3570(c: Cast) -> None:
    """The whole benefit is gated on standing in dim light or darkness."""


@power("f3571", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you score a critical hit or drop a nonminion enemy",
       on=(
           Trigger(Hit, _i_crit, "you score a critical hit"),
           Trigger(Dropped, _i_dropped_a_nonminion, "you drop an enemy"),
       ))
def f3571(c: Cast) -> None:
    """Two printed triggers, so two declared ones. "Nonminion" qualifies
    only the second: a critical hit is a critical hit on anything."""
    c.conceal(on=c.me, until=When.EONT)


@power("f3572", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you reduce a nonminion enemy to 0 hit points",
       on=Trigger(Dropped, _i_dropped_a_nonminion, "you drop an enemy"),
       dropped=("Dropped.power",))
def f3572(c: Cast) -> None:
    """`Dropped` carries `actor`, `dead` and `source` and no power, so
    "with a melee basic attack" has nothing to read -- the row answers
    any killing blow. The nonminion clause is declared."""
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
       reach=PERSONAL, target=SELF,
       narrative=("skill:endurance", "skill:acrobatics"))
def f3577(c: Cast) -> None:
    """Ignoring icy ground is the half that plays -- `c.ignores_difficult`
    takes the sort of ground by name. The two circumstances are weather
    and footing: nothing rolls endurance against cold on a board that has
    no weather, and the acrobatics check is for staying upright while
    walking, which is not a thing a fight ever asks. Neither is a gap."""
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


@power("f3580", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed, _used_any(*R33), "you use a r33 racial power"))
def f3580(c: Cast) -> None:
    """The race's thirteen powers are declared and a character takes one
    of them, so the manifestation the gate names is whichever of these
    it uses. The defence context is handed `power`, so "against melee
    and ranged attacks" is a gate on the shape of the row coming in."""

    def melee_or_ranged(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        kind = row.reach.kind if row is not None and row.reach is not None else ""
        return kind in ("melee", "ranged", "melee_or_ranged")

    for which in (AC, FORT, REF, WILL):
        c.bonus(which, 2, on=c.me, until=When.EONT, when=melee_or_ranged)


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
       reach=PERSONAL, target=SELF, todo=("chargen.power_choice()",))
def f3582(c: Cast) -> None:
    """Not a swap: what goes back is one *use* of a row rather than the
    row, and what comes the other way is "a power of your choice" rather
    than a card. `Swap` names a card's price; this names neither end."""


@power("f3583", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3583(c: Cast) -> None:
    """Another build's 7th-level class feature, chosen from a list the
    brief prints in prose.

    Re-aimed off the multiclass symbol. The verb is there now --
    `c.borrow_row(among=...)` picks one of a list and hands it over --
    and what is missing is the list: the two options are named and
    neither is a ref, so there is nothing to put in `among`."""


@power("f3584", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.ENCOUNTER))
def f3584(c: Cast) -> None:
    """Loses a known encounter power to gain `p12668`. `chargen` takes
    the one that goes back when the character is built; the body hands
    the card over."""
    c.grant_row("p12668", on=c.me, until=When.ENCOUNTER)


@power("f3585", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3585(c: Cast) -> None:
    """Trades `cf:wizard-arcanist-f0` for a school benefit.

    The half this feat *costs* is writable now -- that row is declared,
    and `c.forbid` takes it away for the fight. The half it pays is a
    school benefit the brief prints in prose with no ref, so writing the
    cost alone would leave a wizard strictly worse off than one who never
    took the feat. Both halves or neither.

    Re-aimed: the hold is the missing ref for the school benefit, not
    the borrowing -- `c.grant_row` would hand one over the day one is
    declared."""


@power("f3586", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3586(c: Cast) -> None:
    """The second step of the `f3585` chain: no cost, and the same
    unnamed school benefit to pay."""


@power("f3587", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3587(c: Cast) -> None:
    """The third step of the `f3585` chain, and the same gap."""


@power("f3588", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.power_choice()",))
def f3588(c: Cast) -> None:
    """`f3582` for the rogue's row, and the same two ends: a use rather
    than a power, and a choice rather than a card."""


@power("f3589", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3589(c: Cast) -> None:
    """Trades `cf:cleric-templar-f1` -- a declared row -- for a domain
    feature chosen from a list the brief prints in prose. Same shape as
    `f3585`: the cost is sayable and the benefit is not, and the
    missing half is a ref rather than a verb."""


@power("f3590", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3590(c: Cast) -> None:
    """The second step of the `f3589` chain, and the same gap."""


@power("f3591", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f3591(c: Cast) -> None:
    """The third step of the `f3589` chain, and the same gap."""


@power("f3592", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.ENCOUNTER))
def f3592(c: Cast) -> None:
    """Loses a known rogue encounter power to gain `p12710`."""
    c.grant_row("p12710", on=c.me, until=When.ENCOUNTER)


# -- the water, and the armour proficiencies --------------------------------


@power("f3594", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3594(c: Cast) -> None:
    """All of it now. `c.set_origin` writes onto `kinds_of`, which is
    what `c.is_kind` reads, so "you are considered an aquatic creature"
    is sayable and the gate below reads the same word back on the other
    side. Breathing underwater has no combat consequence, so there is
    nothing dropped with it."""
    me = c.me
    c.set_origin("aquatic", on=me, until=When.ENCOUNTER)
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
       reach=PERSONAL, target=SELF, dropped=("c.instead_of_slide()",))
def f3603(c: Cast) -> None:
    """Flail is a printed group the weapon table carries and `chargen`
    now deals, so the attack bonus plays. Heroic tier, so +1.

    Dropped: "when the attack lets you slide the target, you can knock it
    prone instead". Nothing offers a choice at the moment another row's
    slide is about to happen, and knocking prone *as well* would be a
    second condition the card does not give."""
    c.bonus("attack", 1, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "flail"))


def _provokes_on_standing(c: Cast, victim: int) -> None:
    """"It provokes an opportunity attack from you if it stands up."

    Standing is not an event of its own: `actions.act` ends the prone
    hold with `why="stood up"`, so `ConditionEnded` is where the moment
    arrives, and `c.provoke` opens the window. Adjacency is asked when
    the creature rises rather than when the hold was laid, which is what
    "stands up adjacent to you" says.
    """

    def stood(ev: Any) -> None:
        if (
            ev.target == victim
            and ev.condition is Condition.PRONE
            and ev.why == "stood up"
            and c.adjacent(victim)
        ):
            c.provoke(c.me, on=victim)

    c.watch(ConditionEnded, stood, until=When.EONT, once=True)


def _power_strike_rider(ref: str, group: str, rider: Any):  # noqa: ANN202
    """"When you use p12668 with a <group>, you can <rider>, but the extra
    damage is reduced by 1[W]."

    Declared on `DamageRolled` rather than on `DamageApplied`, and that is
    what makes the printed price sayable: the blow's total rides on that
    event, it is mutable, `resolve.deal_damage` reads it back after the
    bus has finished, and `c.reduce` is the verb. `DamageRolled` carries
    `detail` too, so the hook that found the victim still finds it.

    "Reduced by 1[W]" is charged as a rolled weapon die rather than as a
    die struck off `p12668`'s own expression: the dice are gone by the
    time the ref arrives on the event and only the number is left, so the
    number is what the price comes off.
    """

    @power(ref, level=1, cls="", usage=AT_WILL, action=NONE,
           reach=PERSONAL, target=NO_TARGET,
           trigger=f"your power strike damages a target and you wield a {group}",
           on=Trigger(DamageRolled, _power_strike_landed, "power strike lands"))
    def row(c: Cast) -> None:
        ev = c.trigger
        if not _holding(c, group):
            return
        c.reduce(c.roll(c.w()), ev)
        rider(c, ev.target)

    row.__name__ = ref
    row.__doc__ = _power_strike_rider.__doc__
    return row


f3604 = _power_strike_rider(
    "f3604", "flail",
    lambda c, victim: (c.prone(on=victim), _provokes_on_standing(c, victim)),
)
f3605 = _power_strike_rider(
    "f3605", "hammer",
    lambda c, victim: c.condition(
        Condition.DAZED, on=victim, until=When.EONT
    ),
)
f3612 = _power_strike_rider(
    "f3612", "spear",
    lambda c, victim: c.immobilized(on=victim, until=When.EONT),
)


@power("f3606", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you drop an enemy with a heavy blade",
       on=Trigger(Dropped, _i_dropped_a_foe, "you drop an enemy"),
       dropped=("Dropped.power",))
def f3606(c: Cast) -> None:
    """Heavy blade is a real group, so this one is written. What is
    dropped is which blow did it: `Dropped` names no power, so the group
    is read off what is in hand instead of off the attack.

    `c.expend_row` is the printed price and the printed "instead of
    gaining the power's normal benefit" both: the use goes and `p12668`
    never runs. `AT_WILL` because that single use is the whole limit --
    an `ENCOUNTER` header would be a second budget on top of it, and the
    False `c.expend_row` returns is the Requirement."""
    ev = c.trigger
    if not _holding(c, "heavy blade"):
        return
    others = [e for e in c.within(1, side="enemy") if e != ev.actor]
    if not others or not c.expend_row("p12668"):
        return
    c.basic(on=others[0])


def _retarget(ref: str, group: str, where: Any):  # noqa: ANN202
    """"You make the attack against <defence> rather than AC."

    `resolve.attack` reads the defence back off `AttackDeclared` inside
    its own `roll` -- `vs = declared.vs` -- precisely so that a row
    answering the declaration can move it, which is the same shape
    `c.reduce` takes on `DamageRolled`. So this is not blocked any more:
    the row fires at `Window.BEFORE`, spends the use with `c.expend_row`
    (the printed "instead of gaining the power's normal benefit") and
    assigns the defence.

    `action=NONE` rather than an immediate interrupt: the swing being
    answered is the character's own, and an immediate action cannot be
    taken on your own turn. `AT_WILL` for the same reason `f3606` is --
    `p12668`'s one use is the limit.
    """

    @power(ref, level=1, cls="", usage=AT_WILL, action=NONE,
           reach=PERSONAL, target=NO_TARGET,
           trigger=f"you make a melee basic attack with a {group} against AC",
           on=Trigger(
               AttackDeclared, _my_basic_against_ac(group),
               f"you swing a {group}", window=Window.BEFORE,
           ))
    def row(c: Cast) -> None:
        ev = c.trigger
        if not c.expend_row("p12668"):
            return
        ev.vs = where
        victim = ev.target
        c.bonus(
            "damage", 2, on=c.me, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("target") == victim,
        )

    row.__name__ = ref
    row.__doc__ = _retarget.__doc__
    return row


f3607 = _retarget("f3607", "light blade", REF)
f3608 = _retarget("f3608", "mace", FORT)


@power("f3609", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3609(c: Cast) -> None:
    """Pick is a printed group the weapon table carries and `chargen` now
    deals. Heroic tier, so +1 each. The damage half is gated on the
    target being the larger creature, which is a comparison on `Size`."""
    me = c.me

    def bigger(ctx: dict[str, Any]) -> bool:
        who = _victim(ctx)
        return (
            _holding(c, "pick")
            and who is not None
            and c.size_of(who) > c.size_of(me)
        )

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "pick"))
    c.bonus("damage", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=bigger)


@power("f3610", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("c.maximise(dice=)",))
def f3610(c: Cast) -> None:
    """Re-aimed. The old marker said the attack roll could not be read,
    and it can: `AttackRolled` carries `natural`, so "if your attack roll
    was 18-20" is an ordinary watcher.

    The payout is the half that cannot be said. `c.maximise` tops a blow
    up to the maximum of the **header's** `damage=` line, and `p12668`
    has none -- its extra damage is rolled in its body -- so the listener
    reads `damage_of(0)`, finds nothing and returns. Maximising a damage
    expression a body rolls has no verb."""


@power("f3611", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3611(c: Cast) -> None:
    """Polearm is a printed group the weapon table carries and `chargen`
    now deals, so it is asked rather than folded into spear -- which
    would have widened the feat over every shortspear in the game. The
    defence half is a plain bonus gated on the attack being a charge,
    which the attack context does carry."""
    me = c.me

    def two_handed_polearm(ctx: dict[str, Any]) -> bool:
        arm = _main(c)
        return (
            arm is not None and arm.group == "polearm" and arm.two_handed
            and bool(ctx.get("charge"))
        )

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: _holding(c, "polearm"))
    for where in ALL_DEFENCES:
        c.bonus(where, 2, on=me, until=When.ENCOUNTER, when=two_handed_polearm)


@power("f3613", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="your power strike damages a target and you wield a staff",
       on=Trigger(DamageApplied, _power_strike_landed, "power strike lands"))
def f3613(c: Cast) -> None:
    """Staff is a real group and this card charges nothing for the rider,
    so it is the one power strike feat with no marker at all. "Grants
    combat advantage" with nobody named is the whole of my side."""
    if _holding(c, "staff"):
        c.grants_advantage(on=c.trigger.target, to="team", until=When.EONT)


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
    combat advantage" names no beneficiary, and `to="team"` would hand
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
       dropped=TRAINING, proficiency=("w:ki-focus",))
def f3615(c: Cast) -> None:
    """The extra damage plays, held to once a fight by `once=True`. All
    four arms of the gate can be asked now: one-handed is a property the
    weapon table carries, and the garrote, the blowgun and the shortbow
    are three rows in it."""
    me = c.me
    _NAMED_ARMS = ("w:garrote", "w:blowgun", "w:shortbow")

    def one_handed(ctx: dict[str, Any]) -> bool:
        arm = _main(c)
        return (arm is not None and not arm.two_handed) or _wielding(c, *_NAMED_ARMS)

    c.bonus(
        "damage", 0, dice="1d8", on=me, until=When.ENCOUNTER, once=True,
        when=one_handed,
    )


@power("f3616", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.power_choice()",))
def f3616(c: Cast) -> None:
    """A daily power chosen at build time, paid for with a vial of poison
    that is prepared during an extended rest. Both ends are `chargen`;
    re-aimed off `c.apply_poison`, which is about a coated blade in a
    fight and not about what is in the pack before one."""


@power("f3617", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3617(c: Cast) -> None:
    """Entirely a recipe learned and a vial made between fights, at the
    cost of a daily power the character chooses not to keep. Deliberately
    inert: every clause of it happens during an extended rest."""


@power("f3618", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=NO_TARGET,
       dropped=TRAINING, proficiency=("w:holy-symbol",))
def f3618(c: Cast) -> None:
    """`p13816` is a ref now, so the card's third clause is an ordinary
    `c.grant_row` -- and that turns the row into a trait.

    It prints a standing grant *and* a rider, and a row declared `on=`
    never lays the standing half, so the trigger moves into `c.watch`.
    "Once per encounter" is `once=True` on the watch, which is the limit
    the card prints; the row's own `ENCOUNTER` budget no longer stands in
    for it now that the row is armed rather than chosen.

    The advantage is read off the `Hit`'s live `AttackResult`; asking
    `has_combat_advantage` again would be too late, a one-shot grant
    having already been spent.
    """
    me = c.me
    c.grant_row("p13816", on=me, until=When.ENCOUNTER)

    def bite(ev: Hit) -> None:
        if _i_hit_with_a_weapon_with_advantage(c.world, me, ev):
            c.flat(c.cha_mod, on=ev.target)

    c.watch(Hit, bite, until=When.ENCOUNTER, once=True)


@power("f3619", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3619(c: Cast) -> None:
    """Both halves. The offer was said to be unsayable and is not:
    `c.may` is `world.decide`, which any watcher may ask, so the free
    action is a `PowerUsed` watcher that puts the trade to the player.
    `PowerUsed` announcing above the body is what makes it work -- the
    damage bonus is laid before the power rolls any.

    `default=False`, unlike almost everywhere else: a headless engine
    takes the first option, and a wizard who burns a surge on every
    encounter power he owns is out of surges by the third fight."""
    me = c.me
    _surge_when_it_lands(
        c, lambda p: Keyword.ARCANE in p.keywords and p.usage is ENCOUNTER
    )

    def offered(ev: Any) -> None:
        p = get(ev.power)
        if (
            ev.actor != me
            or p is None
            or p.attack is None
            or Keyword.ARCANE not in p.keywords
            or p.usage is not ENCOUNTER
        ):
            return
        if not c.may("lose a healing surge for extra damage", who=me,
                     default=False):
            return
        if c.spend_surge(on=me):
            c.bonus("damage", c.cha_mod, on=me, until=When.EOT, once=True)

    c.watch(PowerUsed, offered, until=When.ENCOUNTER)


@power("f3620", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=NAMED,
       swap=Swap(1, Usage.ENCOUNTER))
def f3620(c: Cast) -> None:
    """Loses a known encounter power for one the brief names in prose."""


@power("f3621", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.instead_of_surge()", *FEATURE))
def f3621(c: Cast) -> None:
    """The surge half plays.

    Re-aimed off `c.opt_in`: putting the choice to the ally is sayable
    now -- `f3619` does it with `c.may` inside a watcher -- and the half
    that is not is the word *instead*. The surge the ally gives up is the
    one `p929`'s own body is about to let it spend, and nothing lets a
    watcher stand in the way of another row's spend. The third clause
    unwinds a class feature named in prose, which there is nothing to
    unwind."""
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
       reach=PERSONAL, target=SELF, todo=FEATURE,
       proficiency=("w:holy-symbol", "w:ki-focus"))
def f3626(c: Cast) -> None:
    """Three class features named in prose, with the surge pool they cost
    named beside them. Nothing here is a thing a `Cast` can lay."""


@power("f3627", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3627(c: Cast) -> None:
    """A wilderness knack is a knack for the wilderness: the whole benefit
    is exploration, so this is deliberately inert rather than unwritten."""


@power("f3628", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=TRAINING,
       proficiency=("w:staff", "w:totem"))
def f3628(c: Cast) -> None:
    """`p1455` is a ref and the row is declared, so the power half is an
    ordinary `c.grant_row`. "Once per day" is not a fight's business --
    the row carries its own usage and the day is `chargen`'s clock."""
    c.grant_row("p1455", on=c.me, until=When.ENCOUNTER)


@power("f3629", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=TRAINING, proficiency=("w:holy-symbol",))
def f3629(c: Cast) -> None:
    """Both powers are refs now, so both are ordinary grants. `p13554` is
    printed as "you can use it as an encounter power" and carries its own
    usage, so there is nothing for this row to say about the budget."""
    c.grant_row("p12660", on=c.me, until=When.ENCOUNTER)
    c.grant_row("p13554", on=c.me, until=When.ENCOUNTER)


@power("f3630", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=NAMED,
       swap=Swap(1, Usage.AT_WILL))
def f3630(c: Cast) -> None:
    """An at-will traded for one of the powers a class feature grants.
    `f3620` above is the same sentence: what the row needs handed to it is
    a *power* ref, and the brief prints neither the feature's nor its
    grants'. Which rows belong to a feature is recorded nowhere even where
    the feature does have a ref."""


@power("f3631", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.ENCOUNTER))
def f3631(c: Cast) -> None:
    """An encounter power traded for `p13588`. `chargen` takes the one
    that goes back when the character is built; the body hands the card
    over."""
    c.grant_row("p13588", on=c.me, until=When.ENCOUNTER)


@power("f3632", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.ENCOUNTER))
def f3632(c: Cast) -> None:
    """An encounter power traded for `p12668`, the same way `f3584`
    trades the fighter's."""
    c.grant_row("p12668", on=c.me, until=When.ENCOUNTER)


@power("f3633", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:rod", "w:wand"))
def f3633(c: Cast) -> None:
    """The binder's pact boon, and the two rows it grants.

    `c.pact_boon` was never the hold -- a pact is a build leg and the
    warlock's legs are declared. The hold was that the brief names the boon in
    prose and its powers not at all.

    **Which boon is settled by the compendium rather than guessed.** The
    binder's own class page is entirely about vestiges -- it describes keeping
    one active, and names the two a beginning character has -- so "a binder
    pact boon" is the Vestige Pact's, which is `cf:warlock-f1s6`. Its at-will
    attack is `p6855` and the boon itself is `cf:warlock-f1c12`; both are
    declared.

    "As encounter powers" is `uses=1` on each, which is the only thing the
    feat changes about them: a pact warlock has them at will.
    """
    for ref in ("p6855", "cf:warlock-f1c12"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER, uses=1)


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
       reach=PERSONAL, target=SELF,
       proficiency=("w:ki-focus",))
def f3639(c: Cast) -> None:
    """Both halves of the gate are askable now: the ki focus is a weapon
    `chargen` deals, and the power source is a keyword on the row that is
    swinging. Heroic tier, so +2."""

    def shadow_through_the_focus(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", ""))
        return (
            row is not None
            and Keyword.SHADOW in row.keywords
            and _wielding(c, "w:ki-focus")
        )

    c.bonus("damage", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=shadow_through_the_focus)

@power("f3640", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3640(c: Cast) -> None:
    """Opening a lock and disabling a trap are not fought over, and no
    fight rolls Thievery or Arcana at all. Both halves are narrative, so
    the row is declared inert rather than left waiting on an ability swap
    no check would ever reach."""


@power("f3641", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=("c.make_thrown()",),
       proficiency=("w:warhammer",))
def f3641(c: Cast) -> None:
    """The implement half plays: `c.as_implement` writes the fact onto
    the weapon in hand, and hammer is a group the weapon table carries.

    Dropped: "treat the warhammer as a heavy thrown weapon with a range
    of 6/12". A weapon's range is a field on the `Weapon`, and nothing
    writes one onto the thing being held."""
    if _holding(c, "hammer"):
        c.as_implement(on=c.me)


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
       reach=PERSONAL, target=SELF,
       dropped=("chargen.power_choice()",))
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
       dropped=("Keyword.BEAST_FORM",))
def f3646b(c: Cast) -> None:
    """The printed form "normally doesn't change your game statistics", so
    `c.form` is taken bare -- no conditions, no modes -- with a minor
    action as the way back out, which is the "or vice versa".

    The shift on the way back is written now: `c.endable(then=)` is the
    payout for ending a hold *deliberately*, which is exactly what
    changing back is, and it runs for that and not for the clock.

    Re-aimed. Whether a creature is in the form is askable -- the hold is
    labelled and `c.suffering` reads it back -- and what is missing is
    the keyword the restriction turns on: there is no `BEAST_FORM` in
    `Keyword`, so "you can't use powers that lack it" has no set to test
    against. The equipment clauses are bookkeeping with no combat
    consequence."""
    shape = c.form(label="beast form", revert=MINOR, until=When.ENCOUNTER)
    c.endable(shape, MINOR, then=lambda: c.shift(1))


@power("f3647", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3647(c: Cast) -> None:
    """"When you enter your Berserker Fury" is a moment a class feature
    named in prose would have to announce."""


@power("f3648", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.DAILY))
def f3648(c: Cast) -> None:
    """Hands over the card printed beside it. Giving a known daily up in
    exchange is settled when the character is built."""
    c.grant_row("f3648b", on=c.me, until=When.ENCOUNTER)


@power("f3648b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=NO_TARGET,
       keywords=[Keyword.PRIMAL, Keyword.SUMMONING], summon=Summon())
def f3648b(c: Cast) -> None:
    """The block prints no numbers at all, so the summon takes `Summon`'s
    defaults -- the summoner's defences, a surge's worth of hit points, no
    attack of its own. The surge it costs when it falls is the printed
    mechanic and is watched for.

    "Until you dismiss it as a minor action" is written the way every
    other deliberate ending is: a bare hold on the summoner, `c.endable`
    to price dropping it, and `c.dismiss_companion` as what dropping it
    buys. `c.summon_inline` spawns a `Companion`, which is what that verb
    takes away."""
    beast = c.summon_inline(get(c.ref).summon, at=c.origin)
    c.endable(
        c.effect(f"{c.ref} summoned", until=When.ENCOUNTER, on=c.me),
        MINOR, then=c.dismiss_companion,
    )

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


@power("f3650", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(
           Miss, lambda w, me, ev: ev.target == me and ev.attacker != me,
           "an enemy misses you",
       ))
def f3650(c: Cast) -> None:
    """The trigger is declared and real, and the benefit is entirely
    "you can use p377", which `c.use_power` now says. The use spends
    p377, so the once-a-fight limit is that row's -- which is why the
    header is `AT_WILL` rather than carrying a second one of its own."""
    c.use_power("p377")


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
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3653(c: Cast) -> None:
    """Deliberately inert rather than blocked on the missing refs. Every
    wizard cantrip in the tree is itself `out_of_combat=True` -- the
    whole level-0 file is -- so whichever one the character picks, the
    feat's entire benefit is a row that does nothing in a fight. Naming
    the list would not change that, which is why this is finished rather
    than waiting on `spec.power_ref`."""


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
       reach=PERSONAL, target=SELF, dropped=TRAINING,
       proficiency=("w:staff", "w:totem"))
def f3661(c: Cast) -> None:
    """`f3628` with a different power, and the spec now prints that
    power's ref. `p15852` is declared, so the power half is the same
    `c.grant_row`. "Once per day" is not a fight's business -- the row
    carries its own usage and the day is `chargen`'s clock."""
    c.grant_row("p15852", on=c.me, until=When.ENCOUNTER)


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
       dropped=(*TRAINING, "c.uses_per_day()"), proficiency=("w:wand",))
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
       reach=AreaBurst(1, 5), target=NO_TARGET)
def f3665(c: Cast) -> None:
    """The terrain plays, and the price is charged now. `c.expend_row`
    is "lose one use of the power": it takes the use and never runs the
    row, which `c.forbid` -- taking the card away for the encounter --
    is a larger thing than.

    The page offers three racial powers and records nowhere which one a
    character took, so whichever of the three is still unspent pays.
    "For your enemies" is the zone plus `c.ignores_difficult_in`."""
    if not any(c.expend_row(ref) for ref in ("p7441", "p7442", "p7443")):
        return
    zone = c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)
    c.ignores_difficult_in(zone, side="team")


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
       reach=PERSONAL, target=SELF,
       proficiency=("w:totem",))
def f3671(c: Cast) -> None:
    """Both halves -- heroic tier, so +1.

    Re-read: `c.ignore_cover` is "you ignore cover **and concealment**
    when attacking", and `partial=True` is the narrower printed line,
    waiving the ordinary -2 and leaving superior cover standing. So the
    concealment half was never missing and the marker was wrong. Both
    halves are gated on the implement attack rather than laid flat: the
    card pays for the totem, not for the character."""
    me = c.me

    def through_the_totem(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return (
            row is not None
            and Keyword.IMPLEMENT in row.keywords
            and _wielding(c, "w:totem")
        )

    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=through_the_totem)
    c.ignore_cover(on=me, until=When.ENCOUNTER, partial=True,
                   when=through_the_totem)

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
       reach=PERSONAL, target=SELF)
def f3673(c: Cast) -> None:
    """Both halves.

    The old marker said `c.threatens` reached only opportunity attacks
    and that is no longer true: `dsl` measures a melee line as
    `1 + mods.total("reach")` and `movement` measures the opportunity
    ring the same way, so the one modifier lengthens both. `c.threatens`
    lays it, and its own docstring says "gains reach 2" can raise it.

    Written as a trait rather than a trigger because the skill bonus is
    a standing modifier: declared `on=Trigger(PowerUsed, ...)` the body
    would run only on the racial use and the +2 would never be laid.
    """
    me = c.me
    c.bonus("skill:acrobatics", 2, on=me, until=When.ENCOUNTER, kind="feat")

    def used_it(ev: Any) -> None:
        if ev.actor == me and ev.power in R44:
            c.threatens(2, on=me, until=When.EONT)

    c.watch(PowerUsed, used_it, until=When.ENCOUNTER)


@power("f3674", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3674(c: Cast) -> None:
    """A disguise assumed during a short rest and undone as a minor
    action. There is no recognition on the board, so it is inert."""


@power("f3675", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, dropped=TRAINING,
       proficiency=("w:orb", "w:staff", "w:wand"))
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


@power("f3679", level=1, cls="", usage=AT_WILL, action=ActionType.FREE,
       reach=Melee(1), target=ONE_ALLY, once_per_round=True)
def f3679(c: Cast) -> None:
    """A free action the character takes, not a trait, so it is a row
    with a target rather than a `c.watch`.

    Re-aimed and then finished. The old marker said nothing lists the
    effects standing on me; `Effects.of` does, and `actions.act` already
    walks it to find the prone hold when a creature stands. So the burn
    is found there, `c.transfer` moves the hold intact, and the increase
    is a fresh `c.ongoing` of the same type -- which supersedes rather
    than stacks, the higher of two burns of one type being the printed
    rule, and the higher is the one this row just made."""
    ally = c.target
    if ally is None:
        return
    burns = [
        eff for eff in c.world.effects.of(c.me)
        if eff.ongoing is not None
        and eff.ongoing[1] is DamageType.UNTYPED
        and not eff.ongoing_types
    ]
    if not burns:
        return
    worst = max(burns, key=lambda eff: eff.ongoing[0])
    amount = worst.ongoing[0]
    if c.transfer(worst, to=ally) is None:
        return
    c.ongoing(amount + 5, DamageType.UNTYPED, on=ally)


@power("f3680", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=LOW_LIGHT)
def f3680(c: Cast) -> None:
    """Both halves are gated on the light in a square, which the grid
    does not keep. The second wind is announced now; the darkness is not
    askable."""


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
