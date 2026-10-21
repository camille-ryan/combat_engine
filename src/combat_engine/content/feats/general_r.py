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
from combat_engine.engine.query import (
    creatures,
    defence,
    distance_between,
    team,
    unseen_by,
)
from combat_engine.engine.query import squares as squares_of

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
#: **Split off `c.class_feature()`, which was three gaps in one name.** That
#: symbol collected eleven rows tree-wide and no two of these four wanted
#: the same thing, so it could not go green or red correctly for any:
#:
#: * `f3621` and `f3626` name a feature of a class this project does not
#:   build. `chargen.CLASSES` holds 25 and the compendium holds 77; the ETL
#:   skips any class not in that set (`build._class_features`' own
#:   `wanted` gate), so the feature has no row, no ref and no printed name
#:   in the localisation. The parser is not at fault -- it finds 19
#:   sections and both headings on that page. Whether the class is in scope
#:   is a decision, not a verb, which is why this names the decision.
#: * `f3645` and `f3647` name `cf:barbarian-berserker-f0`, of a class that
#:   *is* in scope and whose feature row simply is not declared yet. Naming
#:   the ref is the tree's own convention for that -- `items/waist.i640x1`
#:   does it one line from a row that had this same wrong symbol.
UNBUILT_CLASS = ("chargen.CLASSES.vampire",)
BERSERKER_FORM = ("cf:barbarian-berserker-f0",)
#: **Retired: `etl.build_sub_option()`. The taxonomy landed, and the seven
#: rows that shared the symbol stopped sharing a gap.**
#:
#: What this note used to say was that `game.db` had no school or domain
#: table among its 24 and that "the taxonomy is absent, so there is no ref
#: to resolve". Both halves are false now -- #581's decision, imported as
#: #584/#585/#586 and #589. Measured in the built database: **25** tables,
#: and `class_feature` holds **342** refs of the form `-f<N>s<N>`, 88 of
#: them under `cf:cleric-warpriest` and 24 under `cf:wizard-mage`.
#: Tree-wide, 97 of the 342 are declared rows.
#:
#: Handing a declared feature over was already `c.grant_row` and picking
#: one out of a printed list is `c.borrow_row(among=)`, so the borrowing
#: was never the hold. With something to point at, each of the seven names
#: what it is actually waiting on, because one symbol could not go green or
#: red correctly for any of them:
#:
#: * `f3585` is **written**. All six `cf:wizard-mage-f0s<N>` are declared
#:   and unmarked, so `among=` has something to hold.
#: * `f3586`, `f3587`, `f3590` and `f3591` print "the <option> you chose
#:   for your <earlier feat>", and nothing records which option a
#:   `c.borrow_row` settled on. That verb's own docstring says so -- the
#:   pick "is a build choice with nowhere to live" and goes to
#:   `world.decide`. It *could* be read back off the row the earlier feat
#:   granted, and that is the wrong row to write: `turns.arm_traits` walks
#:   `Powers.all` in list order, so it would be correct only while arming
#:   happened to reach the two feats in the order the character was dealt
#:   them. The choice belongs where the other printed choices are recorded.
#: * `f3589`, `f3590` and `f3591` want the nine options under each of
#:   `cf:cleric-warpriest-f1`, `-f5` and `-f8`. All 27 are in the database
#:   and **none** is declared, so these name the undeclared parent -- which
#:   is `BERSERKER_FORM` above, and for the same reason.
#: * `f3583` is the one row still partly an ETL question, and a much
#:   narrower one than this symbol was. Its card names the options of two
#:   builds. One build's three are in the database and undeclared
#:   (`cf:fighter-knight-f9s0`-`s2`); the other build's three are **not in
#:   the database at all**, because `etl.build._section_rows` drops any
#:   feature section whose own prose matches `_POWER_LIST` -- "choose ... of
#:   the following" -- a guard meant for a printed power list that also
#:   catches a real feature introducing its options that way. Measured
#:   across every class page: 94 sections dropped by that guard, **7 of
#:   which carry sub-options**, 25 rows in all, across six builds. A
#:   section with sub-options is never a power list.
#:
#: The leak argument the old note ended on is unaffected and still holds:
#: importing the taxonomy removes the cause rather than detecting the
#: symptom, which is what #494's budget ceiling asks for. #581.
#:
#: **Not #548, which is the sibling it was briefly merged with.** That one
#: is `racial_trait`: `rt:<race>-s<N>` sub-options, 18 of which have no row.
FEATURE_CHOICE = ("chargen.feature_choice()",)
#: A suit of armour or a shield, which is not the same column as the
#: weapons and implements `chargen.proficiency` deals.
ARMOUR = ("chargen.armor_proficiency()",)
#: **Retired: the rows that shared it no longer share a gap.** `feat.trains`
#: read 14 of 69 printed trainings because the commonest form is "training
#: in **the** Nature skill" and the extractor dropped it to the article
#: (#574). With three columns -- granted, a choice of named skills, a choice
#: from a class list -- four of these rows are satisfied outright and three
#: are refused for a different reason, so one symbol cannot report for
#: either set. A marker names one gap.
#:
#: What is left is only the **build** case: `class_skill` is keyed by class,
#: and these three cards name a build whose list is a subset of its
#: parent's. `chargen._from_class_list` trains nothing rather than offering
#: the parent's wider list, which is the conservative direction and a
#: refusal rather than an approximation.
BUILD_SKILLS = ("class_skill.build",)
#: Dim light and darkness are not states of a square this engine keeps.
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


def _skald_aura(ref: str, *, per_day: int = 0):  # noqa: ANN202
    """The two printings of the skald's aura are the same card twice.

    `per_day` is the day's allowance one of the two printings carries and
    the other does not, so it is a parameter rather than a line in the
    shared body.
    """

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
            # The day's allowance, where one printing has one: charged to
            # the skald rather than to whoever is being healed.
            if per_day and not c.spend_per_day(ref, per_day):
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
    once-an-encounter budget with `p8278`.

    The old reason was false: `c.race_of` reads the `race:<ref>` that
    `Build.choices` carries, so a character does have a race. What is
    missing is the *second* one -- the race another racial feature chose,
    and which of its powers was taken -- and nothing in `Build.choices`
    records either, so there is no ref for `c.grant_row` to hand over.
    The shared budget is sayable once that ref exists: `c.expend_row`
    spends the other end."""


# -- the dim light family ---------------------------------------------------


@power("f3569", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3569(c: Cast) -> None:
    """Asked at the moment the second wind happens, not when the feat arms:
    the creature may have moved into shadow since. `c.unlit` reads the
    square it is standing in then."""
    me = c.me

    def extra(ev: SecondWind) -> None:
        if getattr(ev, "actor", None) == me and c.unlit(on=me):
            c.heal(c.surge_value(on=me) // 2, on=me)

    c.watch(SecondWind, extra, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3570", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3570(c: Cast) -> None:
    """+1 to all defences while standing in dim light or darkness. The gate
    is live rather than settled when the feat arms -- `c.unlit` is asked each
    time the modifier is consulted, so walking into shadow turns it on."""
    for which in ALL_DEFENCES:
        c.bonus(which, 1, on=c.me, until=When.ENCOUNTER,
                when=lambda ctx: c.unlit())


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
)
def f3572(c: Cast) -> None:
    """"With a melee basic attack" is askable now: `Dropped.power` names
    the row that struck and `c.struck_by(basic=True)` is the reading.
    Before it the row answered any killing blow, including ongoing
    damage. The nonminion clause is declared."""
    ev = c.trigger
    if not c.struck_by(ev, basic=True):
        return
    others = [e for e in c.within(2, side="enemy") if e != ev.actor]
    if others:
        c.flat(c.con_mod, dtype=DamageType.NECROTIC, on=others[0])


@power("f3573", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.ignores_difficult(in_light=)",))
def f3573(c: Cast) -> None:
    """Ignoring difficult terrain **in unlit squares**, and the gate is the
    whole of it: written ungated this is free movement over every kind of
    rough going anywhere, which is a far bigger feat than the card.

    The light half is readable now -- `c.unlit` answers it -- so what is left
    is a *gated* ignore. `c.ignores_difficult` has grown a `when=` since this
    was written, but it is a **move kind**: `movement.PRICED_KINDS`, so
    `when="shift"` or `"charge"`, and anything outside the set raises. What
    this card gates on is a property of the *square* the creature is in, and
    `Movement.ignores` is a set of labels with nowhere to hang a predicate."""


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
       reach=PERSONAL, target=SELF,
       todo=("cf:fighter-knight-f9", "etl.build.keeps_sections_with_options"))
def f3583(c: Cast) -> None:
    """One 7th-level class feature of either of two other builds, chosen
    from the six options the two of them print between them.

    Re-aimed off the multiclass symbol, and then off the taxonomy symbol:
    the verb is `c.borrow_row(among=...)` and the list is half there.

    **Two gaps, and they are at different layers.** One build's three
    options are `cf:fighter-knight-f9s0`-`s2`, in the database since #586
    and declared nowhere, so the first symbol names their undeclared
    parent. The other build's three are absent from the database
    altogether: `etl.build._section_rows` skips the whole section on
    `_POWER_LIST`, and the two sections are near-identical cards that
    differ only in how their one introducing sentence is phrased. See the
    note above `FEATURE_CHOICE` for the tree-wide count, and #812.

    **The second symbol names the behaviour that does not exist, not the
    regex that does.** It was `etl.build._POWER_LIST` for one commit and
    `todo.py` was right to go red: that constant is present, so a marker
    naming it can never be satisfied by its arrival, which is the whole job
    of a marker. What is missing is a `_section_rows` that keeps a section
    carrying sub-marks -- a power-list heading has none and a feature with
    options always does -- so that is what the symbol says."""


@power("f3584", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.ENCOUNTER))
def f3584(c: Cast) -> None:
    """Loses a known encounter power to gain `p12668`. `chargen` takes
    the one that goes back when the character is built; the body hands
    the card over."""
    c.grant_row("p12668", on=c.me, until=When.ENCOUNTER)


@power("f3585", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3585(c: Cast) -> None:
    """Trades `cf:wizard-arcanist-f0` for one of the six benefits printed
    under `cf:wizard-mage-f0`.

    Both halves, which is what the row was holding out for: writing the
    cost alone would leave a wizard strictly worse off than one who never
    took the feat. The cost is a declared row and `c.forbid` takes it away
    for the fight; the six benefits are declared in `features/arcanist.py`
    and unmarked, so `among=` has a list to pick from.

    **`uses=0`, against `c.borrow_row`'s default of 1.** That default is
    the multiclass sentence -- a borrowed at-will capped at one use per
    fight -- and it works by forbidding the row after one `PowerUsed`. A
    class feature prints no such cap, and these six are standing traits
    that `turns.arm_traits` spends on arming, so the default would forbid
    the benefit at the moment it arrived."""
    c.forbid("cf:wizard-arcanist-f0", on=c.me, until=When.ENCOUNTER)
    c.borrow_row(
        among=(
            "cf:wizard-mage-f0s0",
            "cf:wizard-mage-f0s1",
            "cf:wizard-mage-f0s2",
            "cf:wizard-mage-f0s3",
            "cf:wizard-mage-f0s4",
            "cf:wizard-mage-f0s5",
        ),
        uses=0,
        until=When.ENCOUNTER,
    )


@power("f3586", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE_CHOICE)
def f3586(c: Cast) -> None:
    """The second step of the `f3585` chain: no cost, and one of the six
    benefits printed under `cf:wizard-mage-f4`.

    All six are declared, so the list is not the hold any more. The card
    says the benefit is the one belonging to *the school chosen for
    `f3585`*, and that choice is not recorded anywhere this row can read
    it. Offering the six over again is the shape to avoid: it would let a
    character take a second school's benefit, which is a row stronger than
    its printed line."""


@power("f3587", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=(*FEATURE_CHOICE, "cf:wizard-mage-f6s4", "cf:wizard-mage-f6s5"))
def f3587(c: Cast) -> None:
    """The third step of the `f3585` chain: `cf:wizard-mage-f6`'s benefit
    for the school `f3585` chose.

    The same unrecorded choice as `f3586`, **and** a second gap of its own:
    four of the six options under that feature are declared and two are
    not. `c.borrow_row` drops an option with no registry row silently, so
    with only the first symbol closed this row would quietly offer four
    schools out of six."""


@power("f3588", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.power_choice()",))
def f3588(c: Cast) -> None:
    """`f3582` for the rogue's row, and the same two ends: a use rather
    than a power, and a choice rather than a card."""


@power("f3589", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=("cf:cleric-warpriest-f1",))
def f3589(c: Cast) -> None:
    """Trades `cf:cleric-templar-f1` -- a declared row -- for one of the
    nine domain features printed under `cf:cleric-warpriest-f1`.

    The same shape as `f3585` and not the same answer, because the nine
    options are in the database and **none of them is declared**, so
    `among=` would be filtered empty and `c.borrow_row` would return `""`.
    The cost half alone leaves the cleric strictly worse off, so this stays
    refused rather than part-written, and the symbol names the undeclared
    parent the way `BERSERKER_FORM` does.

    One clause to carry over when those rows land: *if the feature grants
    powers, this feat does not grant them* -- so the benefit is the feature
    only, never the cards printed beside it."""


@power("f3590", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("cf:cleric-warpriest-f5", *FEATURE_CHOICE))
def f3590(c: Cast) -> None:
    """The second step of the `f3589` chain: the `cf:cleric-warpriest-f5`
    feature of the domain `f3589` chose.

    Two gaps rather than one. Its nine options are undeclared like `f1`'s,
    and the domain `f3589` settled on is not recorded anywhere this row can
    read -- `f3586`'s half of the chain has the second one alone, which is
    why they are separate symbols."""


@power("f3591", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       todo=("cf:cleric-warpriest-f8", *FEATURE_CHOICE))
def f3591(c: Cast) -> None:
    """The third step of the `f3589` chain, and `f3590`'s two gaps one tier
    up: the nine options under `cf:cleric-warpriest-f8` are undeclared, and
    the domain is still the one `f3589` chose."""


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
       dropped=("Dropped.weapon",))
def f3606(c: Cast) -> None:
    """Heavy blade is a real group, so this one is written. What is
    dropped is which *weapon* did it.

    **Re-pointed off `Dropped.power`, which landed and is the wrong
    half.** The event names the row that struck now, and this card asks
    what *weapon* struck -- a group, which lives on the `Weapon` and not
    on the row. Reading the weapon in hand is the approximation already
    here and is not the same question: a character may hold two.


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


@power("f3610", level=1, cls="", usage=AT_WILL, action=NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p12668 with a pick",
       on=Trigger(PowerUsed, _used("p12668"), "you use p12668"))
def f3610(c: Cast) -> None:
    """Re-read: the payout half was wrong about `c.maximise`.

    It lays **two** things, and the old note only saw the first. The
    `DamageRolled` listener does read the header's `damage=` line and
    does give up on `p12668`, which has none -- but the verb also
    appends a `maximise` modifier, and that one is consumed inside
    `_roll_damage`, "the one place the dice are actually in hand",
    written for exactly the case where a body rolls the expression.

    Declared on `PowerUsed` rather than on the `Hit`, because that
    modifier is one-shot: announced above `p12668`'s body, the next
    damage roll the character makes is that body's `1[W]`. The roll is
    read off `PowerUsed.trigger` -- the `Hit` that provoked the free
    action -- where the live `AttackResult` rides as a plain
    attribute."""
    ev = c.trigger
    landed = getattr(ev, "trigger", None) if ev is not None else None
    result = getattr(landed, "result", None)
    if result is None or result.natural < 18 or not _holding(c, "pick"):
        return
    c.maximise(on=c.me, ref="p12668", until=When.EOT)


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
       dropped=BUILD_SKILLS, proficiency=("w:ki-focus",))
def f3615(c: Cast) -> None:
    """The extra damage plays, held to once a fight by `once=True`. All
    four arms of the gate can be asked now: one-handed is a property the
    weapon table carries, and the garrote, the blowgun and the shortbow
    are three rows in it."""
    me = c.me
    _NAMED_ARMS = ("w3663", "w3662", "w3630")

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
       dropped=BUILD_SKILLS, proficiency=("w:holy-symbol",))
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


def _melee_at_will(ref: str) -> bool:
    """Is this ref a melee at-will attack power?"""
    row = get(ref)
    if row is None or row.attack is None or row.reach is None:
        return False
    return row.usage is Usage.AT_WILL and row.reach.kind == "melee"


@power(
    "p13853",
    level=0,
    cls="",
    usage=ENCOUNTER,
    action=NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger="you hit an enemy with a melee at-will attack power",
    on=Trigger(
        Hit,
        lambda w, me, ev: ev.attacker == me and _melee_at_will(getattr(ev, "power", "")),
        "you hit with a melee at-will attack power",
    ),
)
def p13853(c: Cast) -> None:
    """The card `f3620` below trades for, declared here because that feat is
    the only route to it.

    **Its own class is not imported**, so the row has no entry in `game.db`
    -- which is ordinary rather than novel: 120 declared rows are in that
    position, `mba` and every `rt:` trait among them. The numbers are
    hand-written off the printed card, as every row's are.

    The printed trigger narrows to *that class's* melee at-wills. That
    narrowing cannot be expressed and does not need to be: no row of that
    class exists to be the trigger, and the only character who can hold this
    card is one who took `f3620`, whose own clause widens the trigger to any
    melee at-will. So the gate is the wider sentence, which is the one that
    can ever be true.
    """
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None:
        return
    c.flat(c.roll("1d10"), on=victim)
    c.regain_surge(on=c.me)


@power("f3620", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       swap=Swap(1, Usage.ENCOUNTER))
def f3620(c: Cast) -> None:
    """Loses a known encounter power for the card above.

    The brief names that card in prose and gives no ref, because the class it
    belongs to is not imported -- so it is declared as `p13853` directly
    above, and this hands it over. `chargen` takes the power that goes back;
    that is the `Swap` in the header.

    The feat's own widening -- "also triggered if you hit an adjacent enemy
    with a melee at-will attack power" -- is `p13853`'s trigger as written, for
    the reason given there. The adjacency is implied by the melee reach.
    """
    c.grant_row("p13853", on=c.me, until=When.ENCOUNTER)


@power("f3621", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=UNBUILT_CLASS)
def f3621(c: Cast) -> None:
    """Both surge halves play. What is left is the third clause, which
    unwinds a class feature named in prose -- there is nothing to unwind.

    The word *instead* was said to be unsayable because nothing lets a
    watcher stand in the way of another row's spend. It does:
    `SurgeSpent` is a `Decision`, so a `Window.BEFORE` watch refuses the
    spend the divine power was about to allow -- `c.surge` returns 0 and
    heals nobody -- and the printed trade is then paid out by hand, the
    ally losing the surge for nothing and this character gaining one.

    `ev.source` is the caster `c.surge` stamps, which is what narrows the
    watch to a surge one of this character's own powers offered. The
    keyword gate reads the stamped `ev.power`, not a ref: the clause
    names a class of powers, not one.

    `default=False`, as `f3619` has it and for the same reason: the choice
    is the ally's, giving up the healing costs the ally and buys this
    character a surge, and a headless engine takes the first option. So
    the clause is live and declined in an unattended fight -- which is
    the conservative half, not the inert one.
    """
    me = c.me
    _surge_when_it_lands(
        c, lambda p: Keyword.DIVINE in p.keywords and p.usage is ENCOUNTER
    )
    traded: list[bool] = []

    def offered(ev: Any) -> None:
        p = get(ev.power)
        if (
            traded
            or ev.source != me
            or ev.actor == me
            or p is None
            or Keyword.DIVINE not in p.keywords
        ):
            return
        if not c.may("lose the surge instead of spending it",
                     who=ev.actor, default=False):
            return
        traded.append(True)
        ev.cancel("lost instead of spent")
        c.spend_surge(on=ev.actor)
        c.regain_surge(on=me)

    c.watch(SurgeSpent, offered, until=When.ENCOUNTER, window=Window.BEFORE)


@power("f3622", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF)
def f3622(c: Cast) -> None:
    """Two printed clauses with two separate "once" limits, so a trait
    with two watchers rather than a triggered row with one shared budget.

    No number has to be held on loan for the surge expiring unspent. The
    hold that notices the spending is a `When.ENCOUNTER` watch, and
    `on_end` fires for every end alike -- the fight finishing included --
    so the expiry is that hold's own teardown: nothing spent after the
    grant means the surge goes again. A surge is fungible, so *any* spend
    after the grant is the printed "spend the surge".

    "The first time you are bloodied" is a flag of its own, because a
    creature healed above half and bloodied again crosses the line twice.
    """
    me = c.me
    _surge_when_it_lands(
        c, lambda p: Keyword.MARTIAL in p.keywords and p.usage is ENCOUNTER
    )
    bloodied: list[bool] = []

    def bled(ev: Any) -> None:
        if ev.actor != me or bloodied:
            return
        bloodied.append(True)
        c.regain_surge(on=me)
        kept = [True]

        def spent(sev: Any) -> None:
            if sev.actor == me:
                kept[0] = False

        def expire() -> None:
            if kept[0]:
                c.spend_surge(on=me)

        hold = c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me)
        hold.on_end.append(expire)

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
       reach=PERSONAL, target=SELF,
       dropped=("c.grant_points(expiring=)",))
def f3625(c: Cast) -> None:
    """The surge half plays; an augmented at-will is a psionic power like
    any other, so the keyword covers both arms of the printed trigger.

    **Re-pointed off `c.regain_points()`, which arrived and does not fit.**
    The second printed sentence trades a surge for "2 power points that
    expire at the end of your turn", and a regain is the wrong shape twice
    over: it caps at the pool's maximum, where these sit on top of it, and
    it has no duration, where these end on a named beat. What is wanted is
    a *grant* with an expiry, which is a different verb and arrives with
    `i1793p1`'s identical gap rather than with this one.
    """
    _surge_when_it_lands(c, lambda p: Keyword.PSIONIC in p.keywords)


@power("f3626", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=UNBUILT_CLASS,
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
       reach=PERSONAL, target=SELF,        proficiency=("w:staff", "w:totem"))
def f3628(c: Cast) -> None:
    """`p1455` is a ref and the row is declared, so the power half is an
    ordinary `c.grant_row`. "Once per day" is not a fight's business --
    the row carries its own usage and the day is `chargen`'s clock."""
    c.grant_row("p1455", on=c.me, until=When.ENCOUNTER)


@power("f3629", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       dropped=BUILD_SKILLS, proficiency=("w:holy-symbol",))
def f3629(c: Cast) -> None:
    """Both powers are refs now, so both are ordinary grants. `p13554` is
    printed as "you can use it as an encounter power" and carries its own
    usage, so there is nothing for this row to say about the budget."""
    c.grant_row("p12660", on=c.me, until=When.ENCOUNTER)
    c.grant_row("p13554", on=c.me, until=When.ENCOUNTER)


#: The three powers the ranger's archery feature grants.
#:
#: **Which rows belong to a feature is recorded nowhere in the tables** -- that
#: was this row's hold -- but the class page says it outright: "You gain the
#: following three powers", with all three cards printed underneath. Read off
#: the compendium rather than guessed, and only the refs are written here.
_ARCHER_GRANTS = ("p13585", "p13586", "p13587")


@power("f3630", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF,
       swap=Swap(1, Usage.AT_WILL))
def f3630(c: Cast) -> None:
    """An at-will traded for one of the powers a class feature grants.

    `chargen` takes the one that goes back -- that is the `Swap` in the header
    -- and the body hands a card over, the way `f3631` below does. The choice
    among the three goes to the decider, since the sheet does not record it.

    The hold was that neither the feature's ref nor its grants' were in the
    brief, and that which rows a feature grants is recorded nowhere. The class
    page records it: see `_ARCHER_GRANTS`.
    """
    taken = c.choose(list(_ARCHER_GRANTS), c.ref)
    if taken:
        c.grant_row(taken, on=c.me, until=When.ENCOUNTER)


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
       reach=PERSONAL, target=SELF)
def f3638(c: Cast) -> None:
    """Each shroud is worth a d8 rather than a d6 when they are invoked.

    `p9400` reads the **face** off `c.dice_for` and keeps the count for
    itself, which is the shape the card asks for: "per shroud" means the feat
    chooses the die and the board chooses how many.

    The rest of the sentence raises a flat addition at 11th and 21st level.
    Out of scope rather than missing -- this build stops at 10, and the
    feature's own version of that addition is already written the same way."""
    c.change_dice("p9400", "1d8")


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
       reach=PERSONAL, target=SELF, dropped=("Gear.ranged(thrown=)",),
       proficiency=("w3607",))
def f3641(c: Cast) -> None:
    """The implement half plays: `c.as_implement` writes the fact onto
    the weapon in hand, and hammer is a group the weapon table carries.

    Dropped: "treat the warhammer as a heavy thrown weapon with a range
    of 6/12". A weapon's range is a field on the `Weapon`, and nothing
    writes one onto the thing being held.
    **Re-pointed: a range *write* landed and is not what this card needs.**
    `c.weapon_range` sets `Weapon.thrown` on this character's own copy, and
    `f1841`'s note was substantially right that it buys nothing here: the
    clause these three print is "you may make a **ranged attack** with this
    melee weapon", and what decides that is not the weapon's field.

    Read down, since the old note had one detail wrong. `dsl.can_branch`
    *does* open a ranged branch off a melee weapon -- `return bool(gear.melee)
    if self.thrown_by_hand else gear.ranged is not None` -- so the gate is
    not unconditionally `gear.ranged`. But `thrown_by_hand` is a **header
    field on the power**, true for everybody holding that card, set by five
    declared rows. These feats change the *weapon*, not the card, so no row
    the character holds becomes throwable by writing the field.

    So the gap is the ranged basic attack accepting a thrown melee weapon --
    `Gear.ranged` is "can be fired", and its own comment is the argument
    against widening it: *"a dagger cannot be -- letting it answer that
    question hands a rogue a ranged basic attack it does not have."* That is
    the site, and it is a `Gear`/basic-attack change rather than a weapon
    field. #643.
    """
    if _holding(c, "hammer"):
        c.as_implement(on=c.me)


# -- the familiar, the barbarian and the druid ------------------------------


@power("f3644", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3644(c: Cast) -> None:
    """Carrying an unattended five-pound object. There is no encumbrance
    and no inventory on the board, so this is deliberately inert."""


@power("f3645", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BERSERKER_FORM)
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
       )
def f3646b(c: Cast) -> None:
    """The printed form "normally doesn't change your game statistics", so
    `c.form` is taken bare -- no conditions, no modes -- with a minor
    action as the way back out, which is the "or vice versa".

    The shift on the way back is written now: `c.endable(then=)` is the
    payout for ending a hold *deliberately*, which is exactly what
    changing back is, and it runs for that and not for the clock.

    Re-aimed twice, and this note is the second time. It used to say the
    missing piece was "the keyword the restriction turns on: there is no
    `BEAST_FORM` in `Keyword`, so 'you can't use powers that lack it' has no
    set to test against." **The keyword arrived and the set is testable
    now** -- `Keyword.BEAST_FORM` is declared on 67 rows.

    What is left is the *refusal*, which is a different thing from the set:
    nothing can bar a character from using powers that lack a keyword.
    `c.forbid(keyword=)` is the symbol, and `p16525` and `p16535` carry it
    for the identical sentence on two themes, so this is one gap across
    three rows rather than three.

    `name=` as well as the label, so the form answers `c.in_form("beast")`
    and not only `c.suffering`. Only the second knows the word, and the
    restriction will need the state as well as the keyword.

    The equipment clauses are bookkeeping with no combat consequence."""
    shape = c.form(label="beast form", revert=MINOR, until=When.ENCOUNTER,
                   name="beast")
    c.forbid(lacking=Keyword.BEAST_FORM, on=c.me, until=When.ENCOUNTER)
    c.endable(shape, MINOR, then=lambda: c.shift(1))


@power("f3647", level=1, cls="", usage=ENCOUNTER, action=NONE,
       reach=PERSONAL, target=SELF, todo=BERSERKER_FORM)
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
       reach=PERSONAL, target=SELF,        proficiency=("w:staff", "w:totem"))
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
       proficiency=("w:wand",))
def f3664(c: Cast) -> None:
    """Hands over the card printed beside it rather than `f3668b`, which
    is the same card on the other feat's page.

    The day's limit on the healing is written now: `c.spend_per_day`
    counts against `Powers.per_day`, which both rests outlive, so
    `f3664b` carries `per_day=1` and `f3668b` -- whose page prints no
    such limit -- does not."""
    c.grant_row("f3664b", on=c.me, until=When.ENCOUNTER)


f3664b = _skald_aura("f3664b", per_day=1)


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
       reach=PERSONAL, target=SELF, )
def f3670(c: Cast) -> None:
    """Written. Both halves of the paragraph this row went through are now true.

    The gate was never the problem -- two creatures in one square is a thing
    the grid allows, and `query.squares` overlapping an ally's is the read.
    The payout was, and the fix was at the read site rather than at a door:
    `query.cover_between` passes the attack context down to
    `_carried_cover`, which until now asked the carried `"cover"` modifier
    with `{}`. So `ctx["reach"]` is readable inside the gate and the card's
    enumeration is sayable exactly as printed. #644.

    **The enumeration is the point, so it is spelled out rather than
    negated.** "Melee attacks and ranged attacks" is two of the six
    `Range.kind` words; writing it as "not a burst" would have quietly
    covered a `personal` row and a wall. `dsl.AREA_OR_CLOSE` exists for the
    opposite question and is deliberately not used here -- it lumps close
    and area together, and this card distinguishes them by not mentioning
    either.
    """
    me = c.me

    def shielded_by_an_ally(ctx: dict[str, Any]) -> bool:
        if ctx.get("reach") not in ("melee", "ranged"):
            return False
        mine = squares_of(c.world, me)
        if not mine:
            return False
        side = team(c.world, me)
        return any(
            other != me
            and team(c.world, other) is side
            and squares_of(c.world, other) & mine
            for other in creatures(c.world)
        )

    c.cover(on=me, until=When.ENCOUNTER, when=shielded_by_an_ally)



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
       reach=PERSONAL, target=SELF,        proficiency=("w:orb", "w:staff", "w:wand"))
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
       reach=PERSONAL, target=SELF, narrative=("skill:stealth",))
def f3680(c: Cast) -> None:
    """The Stealth half is a skill check and is why this carries
    `narrative=`: a +5 to hide is not a thing a fight rolls.

    What *is* written is the other half of the card, and it is gated on
    standing in darkness, which `c.unlit` now answers."""
    c.bonus("skill:stealth", 5, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.unlit())


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
