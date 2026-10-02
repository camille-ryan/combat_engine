"""Fourteen theme groups and the wild talent cantrips.

Two shapes recur and are worth saying once.

The cantrips are the clearest case of a *finished* row that does nothing: a
tool appears in your hand, an image hangs in the air, a message reaches an
ally. None of it touches a board, so they carry `out_of_combat=True` rather
than an invented effect. The two that would touch one -- hearing and seeing
from a square you are not in -- are marked instead, because the engine reads
sight and sound from a creature's own position and nothing can say otherwise.

`x7_918` hangs three rows off a weapon it conjures. Nothing can make a
weapon (`c.as_weapon()`), so the row whose whole content is the weapon is a
`todo` and the two riders that name it are written with the weapon clause
dropped: they fire on the hit they say they fire on, one narrowing short.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MELEE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    RANGED,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AdjacencyGained,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Event,
    ForcedMove,
    Gear,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    MoveStart,
    Pick,
    Position,
    PowerUsed,
    Ranged,
    SavingThrow,
    SkillCheck,
    Target,
    Trigger,
    TurnEnd,
    Usage,
    When,
    Window,
    World,
    both,
    by_action_point,
    by_me,
    by_melee,
    by_ranged,
    check_succeeded,
    enemy_within,
    get,
    hits_me,
    my_check,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.query import distance_between, team

WILD = "wild talent"
PSIONIC = [Keyword.PSIONIC]

OBJECT = Target("object", 1)
#: "You and each ally in the burst". `Target("ally")`'s pool already puts the
#: caster in, which is the printed reading here and not in `c.within`.
YOU_AND_ALLIES = Target("ally", 99, everyone=True)


# -- wild talent cantrips ----------------------------------------------------



def _a_hand_free(world, eid: int) -> bool:  # noqa: ANN001
    """"Requirement: You must have a hand free."

    The same reading `fighter/grips.hand_free` makes, written here because this
    file is not the fighter's and the question is one line. A shield, a second
    melee weapon, or a two-handed weapon all fill the hand. #236.
    """
    from combat_engine.engine.components import Gear

    gear = world.get(eid, Gear)
    if gear is None:
        return True
    if gear.shield or len(gear.melee) > 1:
        return False
    return gear.main is None or not gear.main.two_handed


@power(
    "p12400",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    narrative=("skill:acrobatics",),
)
def p12400(c: Cast) -> None:
    """The move is the row's combat half and is written. The other half is a
    bonus to Acrobatics checks *to balance*, and to staying on top of mud,
    silt and thin ice -- neither of which a board rolls or models, so there is
    no mechanism missing, only a circumstance the grid does not have."""
    c.move(c.speed_of(c.me))


@power(
    "p12401",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    todo=("c.can_hear()",),
)
def p12401(c: Cast) -> None:
    """Hearing from a square you do not occupy. Sound is not a thing the
    engine has at all -- `c.can_hear()` is the symbol one feat already waits
    on -- so there is nothing here to write half of."""


@power(
    "p12402",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p12402(c: Cast) -> None:
    c.note("p12402: which way is north, and an hour of surer overland travel")


@power(
    "p12403",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p12403(c: Cast) -> None:
    c.note("p12403: one simple tool, which cannot attack or hinder anybody")


@power(
    "p12404",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    out_of_combat=True,
)
def p12404(c: Cast) -> None:
    c.note("p12404: an object in your hand goes to a square or a willing hand")


@power(
    "p12405",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("any", 99, everyone=True),
    keywords=[Keyword.PSIONIC, Keyword.ILLUSION],
    out_of_combat=True,
)
def p12405(c: Cast) -> None:
    c.note("p12405: each target sees a Small or smaller object that is not there")


@power(
    "p12406",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=OBJECT,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p12406(c: Cast) -> None:
    c.note("p12406: an unattended flammable object catches fire")


@power(
    "p12407",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    todo=("c.line_of_sight_from()",),
)
def p12407(c: Cast) -> None:
    """Seeing round a corner really does change what a fight allows, so this
    is not the narrative half of anything: `query.line_of_effect` measures
    from the creature's own square and nothing can move where it looks from."""


@power(
    "p12408",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=OBJECT,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p12408(c: Cast) -> None:
    c.note("p12408: an unattended object of 20 pounds or less moves 5 squares")


@power(
    "p12409",
    level=0,
    cls=WILD,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 99, everyone=True),
    keywords=PSIONIC,
    out_of_combat=True,
)
def p12409(c: Cast) -> None:
    c.note("p12409: an image or ten words, to each ally in the burst")


# -- x7_918 ------------------------------------------------------------------

SHADOW = [Keyword.ARCANE, Keyword.SHADOW]
#: "using your shadow-wrought weapon", on both riders. The weapon does not
#: exist, so what is left is "you hit with a melee or a ranged attack".
SHADOW_BLADE = Trigger(
    Hit, by_me, "you hit an enemy with a melee attack or a ranged attack"
)


@power(
    "p15895",
    level=0,
    cls="x7_918",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    todo=("c.as_weapon()",),
    requires=_a_hand_free,
    requires_text="must have a hand free",
)
def p15895(c: Cast) -> None:
    """The whole printed Effect is a weapon: its enhancement bonus and its
    critical die are the weapon's columns, not the caster's modifiers, and
    laying them on the character instead would improve whatever they already
    hold. Nothing conjures a weapon, so there is no half to keep."""


@power(
    "p15896",
    level=2,
    cls="x7_918",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    todo=("c.darkvision()", "c.light()"),
)
def p15896(c: Cast) -> None:
    """Both clauses are senses and light, and the engine has neither."""


@power(
    "p15897",
    level=6,
    cls="x7_918",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
)
def p15897(c: Cast) -> None:
    """"Until you attack" is free: `resolve.attack` clears HIDDEN_FROM for
    whoever swung. "Until you move" is not, so it is watched."""
    unseen = c.invisible(on=c.me, until=When.ENCOUNTER)
    if unseen is None:
        return

    def stepped(ev: MoveEnd) -> None:
        if ev.actor == c.me:
            c.end_effect(unseen, why="moved")

    c.watch(MoveEnd, stepped, until=When.ENCOUNTER)


@power(
    "p15898",
    level=10,
    cls="x7_918",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    out_of_combat=True,
)
def p15898(c: Cast) -> None:
    c.note("p15898: twenty-five words to a creature on your plane, and a reply")


@power(
    "p15899",
    level=3,
    cls="x7_918",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*SHADOW, Keyword.COLD, Keyword.NECROTIC],
    trigger="you hit an enemy with a melee or ranged attack using your weapon",
    on=SHADOW_BLADE,
    dropped=("c.as_weapon()",),
)
def p15899(c: Cast) -> None:
    """Two types on one blow, which `dtypes` says and two `c.damage` calls
    would not -- resistance to either would take the whole of its own half."""
    foe = getattr(c.trigger, "target", c.target)
    if foe is None:
        return
    c.damage("1d10", 0, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=foe)
    c.slowed(until=When.EONT, on=foe)


@power(
    "p15900",
    level=5,
    cls="x7_918",
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*SHADOW, Keyword.COLD, Keyword.NECROTIC],
    trigger="you hit an enemy with a melee or ranged attack using your weapon",
    on=SHADOW_BLADE,
    dropped=("c.as_weapon()",),
)
def p15900(c: Cast) -> None:
    """"Each Failed Saving Throw" is the `escalate` hook, which is handed the
    standing effect every time its save is missed."""
    foe = getattr(c.trigger, "target", c.target)
    if foe is None:
        return
    c.condition(
        on=foe,
        until=When.SAVE_ENDS,
        ongoing=(10, DamageType.COLD),
        escalate=lambda _e: c.prone(on=foe),
    )


# -- x7_877 ------------------------------------------------------------------

MARTIAL = [Keyword.MARTIAL]


@power(
    "p14226",
    level=0,
    cls="x7_877",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p14226(c: Cast) -> None:
    """`c.hover` is the whole printed line: it lifts, it holds the creature
    airborne so `falling.ground` does not put it straight back down, and it
    sets it down without falling damage when the hold ends."""
    c.hover(4, until=When.EONT)


def _levitated(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "power", "") == "p14226"


@power(
    "p14227",
    level=0,
    cls="x7_877",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use p14226",
    on=Trigger(PowerUsed, _levitated, "you use p14226"),
)
def p14227(c: Cast) -> None:
    """The printed trigger names the level-0 row of this same theme, which is
    the only thing in the group that levitates: `p14226`.

    What this grants is the *sustain*, so the hold is re-laid with one, and
    `c.on_sustain` is the payout half -- without it the row would hold the
    caster up and never honour the three squares."""
    held = c.hover(0, until=When.SUSTAIN, sustain=MOVE)
    c.on_sustain(held, lambda: c.rise(3, on=c.me))


def _mine(world: World, me: int, ev: Event) -> bool:
    """`ev.actor` is me. `about_me` says the same thing; named here because
    four rows in this file want it on four different events and spelling it
    out once is what stops one of them reaching for `targets_me` by mistake."""
    return getattr(ev, "actor", None) == me


@power(
    "p14228",
    level=2,
    cls="x7_877",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you have cover or concealment when you roll initiative",
    on=Trigger(InitiativeRolled, _mine, "you roll initiative"),
)
def p14228(c: Cast) -> None:
    """The printed Trigger has a second half -- cover or concealment -- that
    is a state rather than an event, so it is asked in the body. Concealment
    is a modifier the caster holds; cover is measured between two squares, so
    what stands in for it is an enemy that has to shoot past something."""
    if c.total("concealment", on=c.me) <= 0:
        return
    seekers = [e for e in c.enemies() if c.can_see(e)]
    dc = max((c.passive("perception", of=e) for e in seekers), default=0)
    if c.check("stealth", dc):
        c.hide(until=When.ENCOUNTER)


@power(
    "p14229",
    level=6,
    cls="x7_877",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14229(c: Cast) -> None:
    c.shift_as(MOVE, 3, on=c.me, until=When.ENCOUNTER)


@power(
    "p14230",
    level=10,
    cls="x7_877",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14230(c: Cast) -> None:
    """Perception is consulted on a board -- passive Perception is what a
    hiding creature has to beat -- so neither of these is a narrative half."""
    c.bonus("skill:insight", 5, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("skill:perception", 5, on=c.me, until=When.ENCOUNTER, kind="power")


# -- x7_859 ------------------------------------------------------------------

DIVINE = [Keyword.DIVINE]


def _ally_damaged_by_enemy(world: World, me: int, ev: Event) -> bool:
    """"An ally within 5 squares of you takes damage from an enemy attack."

    `DamageApplied` names its subject `target` and its dealer `source`, so
    neither `about_me` nor `ally_within` answers it: the first reads `actor`
    and is false forever, the second would fall through to `target` and
    never check who dealt the blow.
    """
    hurt = getattr(ev, "target", None)
    dealer = getattr(ev, "source", None)
    if hurt is None or dealer is None or hurt == me:
        return False
    if team(world, hurt) is not team(world, me):
        return False
    if team(world, dealer) is team(world, me):
        return False
    return distance_between(world, me, hurt) <= 5


@power(
    "p14154",
    level=0,
    cls="x7_859",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[*DIVINE, Keyword.HEALING],
    trigger="an ally within 5 squares of you takes damage from an enemy attack",
    on=Trigger(
        DamageApplied,
        _ally_damaged_by_enemy,
        "an ally within 5 squares of you takes damage from an enemy attack",
    ),
)
def p14154(c: Cast) -> None:
    """"Wisdom modifier or Charisma modifier" is a choice with no downside,
    so the larger is the one anybody takes. The follow-up bonus is gated on
    the attack context's `target`, which both contexts carry, and `once=True`
    is "your **next** attack roll"."""
    ev = c.trigger
    ally = getattr(ev, "target", c.target)
    dealer = getattr(ev, "source", None)
    if ally is None:
        return
    c.heal(max(c.wis_mod, c.cha_mod), on=ally)
    if dealer is not None:
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT, kind="power", once=True,
            when=lambda ctx: ctx["target"] == dealer,
        )


@power(
    "p14155",
    level=2,
    cls="x7_859",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p14155(c: Cast) -> None:
    """"+2, or +4 if the saving throw fails" is one bonus, not two: the same
    kind does not stack, so a +2 plus a gated +2 would come to +2 forever."""
    ally = c.target
    if ally is None:
        return
    saved = c.save(on=ally)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2 if saved else 4, on=ally, until=When.EONT, kind="power")


@power(
    "p14156",
    level=6,
    cls="x7_859",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p14156(c: Cast) -> None:
    """The shift has a destination requirement, so the square is chosen here
    rather than left to the decider. The allies' half is held on each ally
    with a gate reading the attack context's `target` -- that is "while
    adjacent to you", asked when somebody swings rather than fixed now."""
    fallen = [
        a for a in c.allies()
        if c.bloodied(a) or c.is_(Condition.UNCONSCIOUS, a)
    ]
    beside: set = set()
    for a in fallen:
        pos = c.world.get(a, Position)
        if pos is not None:
            beside |= set(spread(pos.squares, 1))
    options = [
        s for s in c.world.reachable_squares(c.me, c.speed_of(c.me)) if s in beside
    ]
    if not options:
        return
    c.shift(to=c.choose(options, "end the shift beside a fallen ally"))
    c.conceal(on=c.me, until=When.EONT)
    for a in c.allies():
        c.conceal(on=a, until=When.EONT, when=lambda ctx: c.adjacent(ctx["target"]))


@power(
    "p14157",
    level=10,
    cls="x7_859",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[*DIVINE, Keyword.HEALING],
)
def p14157(c: Cast) -> None:
    ally = c.target
    if ally is None or not (c.bloodied(ally) or c.is_(Condition.UNCONSCIOUS, ally)):
        return
    c.heal(2 * c.surge_value(of=ally), on=ally)
    c.end_effect(on=ally, save_ends=True, why="p14157")


# -- x7_871 ------------------------------------------------------------------

PRIMAL = [Keyword.PRIMAL]


@power(
    "p14205",
    level=0,
    cls="x7_871",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
    once_per_round=True,
    dropped=("c.as_weapon()",),
)
def p14205(c: Cast) -> None:
    """"Special: once per round" is the header field, not a body check. The
    bite is a weapon with its own proficiency and damage die and nothing can
    make one; the form and the speed are exact. The shift on changing back
    is the *other* direction of a row that toggles, which one call cannot
    say -- it is inside the same dropped clause as the bite, since both wait
    on the form carrying a weapon."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "p14206",
    level=2,
    cls="x7_871",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL,
    trigger="your melee attack hits an enemy granting you combat advantage",
    on=Trigger(
        Hit, both(by_me, by_melee),
        "your melee attack hits an enemy that is granting you combat advantage",
    ),
)
def p14206(c: Cast) -> None:
    """"Granting you combat advantage" is read off the settled `Hit` --
    `ev.result.advantage`. Asking the board again is too late, because a
    one-shot grant has already been spent by the time this runs."""
    ev = c.trigger
    result = getattr(ev, "result", None)
    if result is None or not result.advantage:
        return
    foe = getattr(ev, "target", None)
    if foe is not None:
        c.prone(on=foe)


@power(
    "p14207",
    level=6,
    cls="x7_871",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.HEALING],
    dropped=("c.silvered()",),
)
def p14207(c: Cast) -> None:
    """The silvered-weapon suspension is the dropped clause: nothing marks a
    weapon as silver. `c.endable` is the "as a minor action you can end this"
    half, with the surge as its payout."""
    healing = c.regeneration(
        1 + c.con_mod, until=When.ENCOUNTER, on=c.me, while_bloodied=True
    )
    c.endable(healing, MINOR, then=lambda: c.surge(on=c.me))


@power(
    "p14208",
    level=10,
    cls="x7_871",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
    dropped=("c.as_weapon()",),
)
def p14208(c: Cast) -> None:
    """Same bite, same reason. Everything else is exact."""
    c.form(until=When.ENCOUNTER, revert=FREE, label=c.ref)
    c.temp_hp(10 + c.con_mod, on=c.me)
    c.bonus(FORT, 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("skill:athletics", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power")


# -- x7_920 ------------------------------------------------------------------


@power(
    "p15920",
    level=2,
    cls="x7_920",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p15920(c: Cast) -> None:
    """"If you are mounted you can instead grant your mount this" -- one
    rider, one mount, so `c.mount()` picks whose move it is."""
    who = c.mount() or c.me
    c.ignores_difficult(on=who, until=When.EOT)
    c.ignore_condition(Condition.SQUEEZING, on=who, until=When.EOT)
    c.move(c.speed_of(who), who=who)


def _crit_on_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and bool(getattr(ev, "critical", False))


def _us(world: World, me: int, who: int | None) -> bool:
    """Me, or the mount I am riding. Both halves of "you or a mount you are
    riding", which `targets_me` alone would only half answer."""
    from combat_engine.engine.types import Relation

    if who is None:
        return False
    return who == me or who in world.relations.sources(Relation.RIDDEN_BY, me)


def _forced_on_us(world: World, me: int, ev: Event) -> bool:
    return _us(world, me, getattr(ev, "target", None))


def _floored_on_us(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "condition", None) is Condition.PRONE and _us(
        world, me, getattr(ev, "target", None)
    )


@power(
    "p15921",
    level=6,
    cls="x7_920",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.HEALING],
    trigger="an enemy bloodies you or scores a critical hit against you",
    on=(
        Trigger(Bloodied, _mine, "an enemy bloodies you"),
        Trigger(Hit, _crit_on_me, "an enemy scores a critical hit against you"),
    ),
)
def p15921(c: Cast) -> None:
    """`Bloodied` names its subject `actor`, not `target`, so this is the
    `about_me` shape and `targets_me` would be false on it forever.

    "Its mount can shift instead of you" is a choice between two shifts with
    the same reach; the rider's is taken, and the mount is healed either way,
    which is the half of that sentence that is not a choice."""
    best = max(
        c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod
    )
    c.surge(on=c.me, bonus=best)
    beast = c.mount()
    if beast is not None:
        c.heal(best, on=beast)
    c.shift(max(1, c.speed_of(c.me) // 2))


@power(
    "p15922",
    level=10,
    cls="x7_920",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you or your mount is subjected to forced movement or knocked prone",
    on=(
        Trigger(ForcedMove, _forced_on_us, "you are subjected to forced movement"),
        Trigger(ConditionApplied, _floored_on_us, "you are knocked prone"),
    ),
)
def p15922(c: Cast) -> None:
    """`on=` takes the whole printed sentence, not half of it: "forced
    movement **or** knocked prone" is two events and declaring one would look
    finished. `ConditionApplied` names its subject `target`, so `about_me` is
    false on it and the predicate reads the right field.

    Only an interrupt can cancel, which is the printed action this row has.
    The shift is "up to the squares you would have been moved", which a prone
    is not, so that branch just refuses the fall."""
    ev = c.trigger
    if not c.cancel():
        return
    squares = getattr(ev, "squares", 0)
    if squares:
        c.shift(squares)


@power(
    "p15923",
    level=3,
    cls="x7_920",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL, Keyword.THUNDER],
    trigger="you hit an enemy with an at-will ranged attack",
    on=Trigger(
        Hit, both(by_me, by_ranged), "you hit an enemy with an at-will ranged attack"
    ),
)
def p15923(c: Cast) -> None:
    """"At-will" is a property of the row that swung, not of the event, so it
    is looked up rather than read off the `Hit`."""
    ev = c.trigger
    swung = get(getattr(ev, "power", ""))
    if swung is None or swung.usage is not Usage.AT_WILL:
        return
    foe = getattr(ev, "target", None)
    if foe is not None:
        c.damage("1d8", 0, dtype=DamageType.THUNDER, on=foe)


# -- x7_938 ------------------------------------------------------------------

ARCANE = [Keyword.ARCANE]


@power(
    "p16022",
    level=0,
    cls="x7_938",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE, Keyword.PSYCHIC],
)
def p16022(c: Cast) -> None:
    """The latch is by hand: `c.on_attack` has `once_per_round` but watches
    `AttackDeclared`, and this fires on the hit rather than the swing."""
    foe = c.target
    if foe is None or c.marked(on=foe, by=c.me):
        return
    last: dict[int, int] = {}

    def bit(ev: Hit) -> None:
        if ev.attacker != foe or ev.target != c.me:
            return
        if last.get(0) == c.world.round:
            return
        last[0] = c.world.round
        c.flat(2, dtype=DamageType.PSYCHIC, on=foe)

    watching = c.watch(Hit, bit, until=When.ENCOUNTER)

    def look(ev: TurnEnd) -> None:
        if ev.actor == c.me and not c.can_see(foe):
            c.end_effect(watching, why="no line of sight")

    c.watch(TurnEnd, look, until=When.ENCOUNTER)


@power(
    "p16023",
    level=2,
    cls="x7_938",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p16023(c: Cast) -> None:
    c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.see_invisible(on=c.me, until=When.ENCOUNTER)


@power(
    "p16024",
    level=6,
    cls="x7_938",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
)
def p16024(c: Cast) -> None:
    """"1d6, or 2d6 against creatures marking it" is written as 1d6 plus a
    gated 1d6 and not as 1d6 plus a gated 2d6, because the card prints no
    bonus type: untyped modifiers add, so the second is the difference."""
    ally = c.target
    if ally is None:
        return
    c.bonus("damage", 0, dice="1d6", on=ally, until=When.ENCOUNTER)
    c.bonus(
        "damage", 0, dice="1d6", on=ally, until=When.ENCOUNTER,
        when=lambda ctx: c.marked(on=ally, by=ctx["target"]),
    )


@power(
    "p16025",
    level=10,
    cls="x7_938",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE, Keyword.CHARM],
    trigger="an enemy within 10 squares of you misses you with an attack",
    on=Trigger(
        Miss, both(targets_me, enemy_within(10)),
        "an enemy within 10 squares of you misses you with an attack",
    ),
)
def p16025(c: Cast) -> None:
    """"The triggering enemy" comes off the event, not off `c.targets`: an
    immediate action declaring ONE_CREATURE is aimed by the engine and would
    name somebody this never answered."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.cannot_attack(on=foe, against=c.me, until=When.EOTNT)


# -- x7_948 ------------------------------------------------------------------


@power(
    "p16085",
    level=0,
    cls="x7_948",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    charges=True,
)
def p16085(c: Cast) -> None:
    """`charges=True` is not decoration: without it the engine measures the
    weapon's reach before the run and refuses the row whenever the target is
    further off than a sword, which is every situation a charge is for."""
    foe = c.target
    if foe is None:
        return
    c.temp_hp(5, on=c.me)
    if c.charge_at(foe) and c.landed:
        c.slowed(on=foe, until=When.EONT)


@power(
    "p16086",
    level=2,
    cls="x7_948",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16086(c: Cast) -> None:
    """The defences are for allies and the resistance is for "you and your
    allies", which is the `ally`/`team` split and not a nicety."""
    zone = c.aura(1, until=When.EONT, on=c.me)
    for defence in (AC, FORT, REF, WILL):
        c.grants_in(zone, defence, 2, side="ally", kind="power")
    pick = c.choose(
        [
            DamageType.ACID,
            DamageType.COLD,
            DamageType.FIRE,
            DamageType.LIGHTNING,
            DamageType.THUNDER,
        ],
        "which damage type the aura resists",
    )
    if pick is not None:
        c.resist_in(zone, 5, pick, side="team")


@power(
    "p16087",
    level=6,
    cls="x7_948",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def p16087(c: Cast) -> None:
    """`c.form` carries the condition and the movement mode together and has
    the way out built in, so the minor action that ends it is `revert=`."""
    c.form(
        conditions=(Condition.INSUBSTANTIAL,),
        modes={"fly": c.speed_of(c.me)},
        until=When.EONT,
        revert=MINOR,
        label=c.ref,
    )
    c.cannot_attack(on=c.me, until=When.EONT)
    c.ignore_condition(Condition.SQUEEZING, on=c.me, until=When.EONT)


@power(
    "p16088",
    level=10,
    cls="x7_948",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def p16088(c: Cast) -> None:
    c.surge(on=c.me)
    c.bonus("attack", 2, on=c.me, until=When.SONT, kind="power")


# -- x7_979 ------------------------------------------------------------------


def _ap_attack(world: World, me: int, ev: Event) -> bool:
    """"You or an ally you can see spends an action point to make an attack",
    answered after the attack rather than when the point is spent.

    `ActionPointSpent` fires before the swing, and three of the six results
    name "the target of the attack", which does not exist yet there.
    """
    from combat_engine.engine.query import line_of_effect, unseen_by

    if not by_action_point(world, me, ev):
        return False
    who = getattr(ev, "attacker", None)
    if who is None or team(world, who) is not team(world, me):
        return False
    return who == me or (
        line_of_effect(world, me, who) and not unseen_by(world, me, who)
    )


AP_BOON = (
    Trigger(Hit, _ap_attack, "you or an ally spends an action point to attack"),
    Trigger(Miss, _ap_attack, "you or an ally spends an action point to attack"),
)


@power(
    "p16397",
    level=0,
    cls="x7_979",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(20),
    target=NO_TARGET,
    trigger="you or an ally you can see spends an action point to make an attack",
    on=AP_BOON,
)
def p16397(c: Cast) -> None:
    """Six printed results, each an ordinary verb. Result 2 is untyped
    vulnerability -- "2 extra damage each time it is hit" is what that is --
    and result 6 is `c.cannot_shift`, which forbids a shift and leaves the walk."""
    ev = c.trigger
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if who is None:
        return
    roll = c.roll("1d6")
    if roll == 1:
        c.bonus("attack", 2, on=who, until=When.EONT, kind="power")
    elif roll == 2 and victim is not None:
        c.vulnerable(2, on=victim, until=When.EONT)
    elif roll == 3:
        c.bonus("speed", 2, on=who, until=When.EONT, kind="power")
    elif roll == 4 and victim is not None:
        c.grants_advantage(on=victim, until=When.EONT, to="team")
    elif roll == 5:
        c.grant_attack(who)
    elif roll == 6 and victim is not None:
        c.cannot_shift(on=victim, until=When.EONT)


@power(
    "p16398",
    level=2,
    cls="x7_979",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, _mine, "you roll initiative"),
)
def p16398(c: Cast) -> None:
    """At the moment initiative is rolled the caster has had no turn, so
    "until the end of your first turn" is `When.EONT` and not `When.EOT`."""
    c.weakened(on=c.me, until=When.EONT)
    c.restore_use("p16397")
    c.restore_use("p16397")


def _used_p16397(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "power", "") == "p16397"


@power(
    "p16399",
    level=6,
    cls="x7_979",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use p16397",
    on=Trigger(PowerUsed, _used_p16397, "you use p16397"),
    dropped=("c.pick_roll()",),
)
def p16399(c: Cast) -> None:
    """The surge is paid. The dropped clause is choosing the face.

    Re-aimed off `c.change_dice()`, which exists now and is the wrong verb:
    that one says *which* die a row rolls, and this says what the die **came
    up**, on a roll the triggering row has already made. Nothing reaches into
    a finished roll to set its result -- `c.boost_roll()` and `c.on_reroll()`
    are the neighbouring gaps and neither is this either."""
    c.spend_surge(on=c.me)


def _roll_near_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", getattr(ev, "actor", None))
    return who is not None and distance_between(world, me, who) <= 5


@power(
    "p16400",
    level=10,
    cls="x7_979",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger="a creature within 5 squares makes an attack roll or a skill check",
    on=(
        Trigger(SkillCheck, _roll_near_me, "a creature within 5 makes a skill check"),
        Trigger(
            AttackRolled, _roll_near_me, "a creature within 5 makes an attack roll"
        ),
    ),
    dropped=("c.boost_roll()",),
)
def p16400(c: Cast) -> None:
    """The skill-check half is `c.boost_check`, which adds to the triggering
    check after the die is down. The attack-roll half wants the same reader
    for an attack and there is none -- a modifier laid now applies to the
    next roll, not to the one being answered."""
    swing = c.roll("1d6")
    if isinstance(c.trigger, SkillCheck):
        c.boost_check(swing)


# -- x7_989 ------------------------------------------------------------------


@power(
    "p16446",
    level=0,
    cls="x7_989",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def p16446(c: Cast) -> None:
    c.note("p16446: an hour of knowing where one chosen item is and what it is")


_THIEVERY = my_check("thievery")


def _my_thievery(world: World, me: int, ev: Event) -> bool:
    return (
        world.turn == me
        and _mine(world, me, ev)
        and _THIEVERY(world, me, ev)
        and check_succeeded(world, me, ev)
    )


def _my_basic_hit(world: World, me: int, ev: Event) -> bool:
    return (
        world.turn == me
        and by_me(world, me, ev)
        and getattr(ev, "power", "") in (MELEE, RANGED)
    )


@power(
    "p16447",
    level=2,
    cls="x7_989",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="on your turn you succeed on a Thievery check or hit with a basic attack",
    on=(
        Trigger(SkillCheck, _my_thievery, "you succeed on a Thievery check"),
        Trigger(Hit, _my_basic_hit, "you hit an enemy with a basic attack"),
    ),
    dropped=("c.draw()",),
)
def p16447(c: Cast) -> None:
    """Nothing puts a thing into a hand or takes it out mid-fight."""
    c.shift(2)


@power(
    "p16448",
    level=6,
    cls="x7_989",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(3),
    target=YOU_AND_ALLIES,
    keywords=MARTIAL,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, _mine, "you roll initiative"),
)
def p16448(c: Cast) -> None:
    """"During the first round of combat" is the end of the caster's next
    turn as closely as a duration can say it, since the row fires before
    anybody has acted."""
    who = c.target
    if who is None:
        return
    c.initiative(2, on=who)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=who, until=When.EONT, kind="power")


@power(
    "p16449",
    level=10,
    cls="x7_989",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you make a skill check or a saving throw and dislike the result",
    on=(
        Trigger(SkillCheck, _mine, "you make a skill check"),
        Trigger(SavingThrow, _mine, "you make a saving throw"),
    ),
)
def p16449(c: Cast) -> None:
    """Both rerollers read `c.trigger` and answer 0/False for the other kind
    of event, so calling the pair is how one row covers two sentences."""
    c.reroll_check(keep="new")
    c.reroll_save(keep="new")


# -- x7_1002 -----------------------------------------------------------------


@power(
    "p16578",
    level=0,
    cls="x7_1002",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="a creature within your reach hits you with an attack",
    on=Trigger(
        Hit, both(hits_me, enemy_within(1)),
        "a creature within your reach hits you with an attack",
    ),
)
def p16578(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.slowed(on=foe, until=When.EOTNT)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p16579",
    level=2,
    cls="x7_1002",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*MARTIAL, Keyword.STANCE],
)
def p16579(c: Cast) -> None:
    """`once=True` is "the **next** creature that attacks it"; the watch is
    held `until=When.STANCE` so taking another stance takes it down."""
    c.stance(on=c.me, label=c.ref)

    def opened(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.grants_advantage(on=ev.target, until=When.EONT, to="team", once=True)

    c.watch(Hit, opened, until=When.STANCE)


@power(
    "p16580",
    level=6,
    cls="x7_1002",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*MARTIAL, Keyword.STANCE],
)
def p16580(c: Cast) -> None:
    """`MoveStart` and not `MoveEnd` for the first half: by `MoveEnd` the
    enemy has gone and `c.adjacent` is false exactly when the row should
    fire. The second half says "after the forced movement is resolved", so
    that one is the after window on `ForcedMove`."""
    c.stance(on=c.me, label=c.ref)

    def sidestep(ev: MoveStart) -> None:
        if (
            ev.kind_ == "shift"
            and ev.actor != c.me
            and ev.actor in c.enemies()
            and c.adjacent(ev.actor)
        ):
            c.shift(1)

    c.watch(MoveStart, sidestep, until=When.STANCE)

    def recover(ev: ForcedMove) -> None:
        if ev.target == c.me:
            c.shift(2)

    c.watch(ForcedMove, recover, until=When.STANCE, window=Window.AFTER)


@power(
    "p16581",
    level=10,
    cls="x7_1002",
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    trigger="you hit an enemy with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit an enemy with a melee attack"),
)
def p16581(c: Cast) -> None:
    """"Save ends **both**" is one effect carrying the condition and the
    burn, not two saves."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.condition(
            Condition.IMMOBILIZED,
            on=foe,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )


# -- x7_1014 -----------------------------------------------------------------

ILLUSION = [Keyword.ARCANE, Keyword.ILLUSION]


@power(
    "p16644",
    level=0,
    cls="x7_1014",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ILLUSION, Keyword.IMPLEMENT],
    attack=Attack(Pick.HIGHEST, vs=WILL),
)
def p16644(c: Cast) -> None:
    """A slide, and cover of a sort from the creature slid.

    **This one is `Pick.HIGHEST`, not `Pick.PRIMARY`.** The line reads
    "Highest ability modifier vs. Will", which is a different sentence from
    the "Primary ability" the rest of this wave prints and only accidentally
    the same number: half level, proficiency and enhancement are common to all
    six abilities, so the largest of them is what the line means. This row's
    marker named `c.ability_for(ref)` along with the primary-ability rows,
    which is the one thing it did not want.

    The concealment is "from the target", so it is gated on the attack
    context's `attacker` and not laid against everybody -- the same as
    `p16646` below.
    """
    if not c.strike():
        return
    c.slide(3)
    foe = c.target
    if foe is None:
        return
    c.conceal(
        on=c.me, until=When.EONT, when=lambda ctx: ctx.get("attacker") == foe
    )


@power(
    "p16646",
    level=2,
    cls="x7_1014",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ILLUSION,
)
def p16646(c: Cast) -> None:
    """The concealment is "against the target", so it is gated on the attack
    context's `attacker` rather than laid against everybody."""
    foe = c.target
    if foe is None:
        return
    if c.check("arcana", c.passive("insight", of=foe)):
        c.grants_advantage(on=foe, until=When.EONT)
        c.conceal(on=c.me, until=When.EONT, when=lambda ctx: ctx["attacker"] == foe)


@power(
    "p16647",
    level=6,
    cls="x7_1014",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ILLUSION,
    out_of_combat=True,
)
def p16647(c: Cast) -> None:
    c.note("p16647: an hour of rolling Bluff and Thievery twice, keeping the better")


def _enemy_closed(world: World, me: int, ev: Event) -> bool:
    mover = getattr(ev, "mover", 0)
    if mover in (0, me) or getattr(ev, "other", None) not in (me, mover):
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p16648",
    level=10,
    cls="x7_1014",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ILLUSION,
    trigger="an enemy moves adjacent to you",
    on=Trigger(AdjacencyGained, _enemy_closed, "an enemy moves adjacent to you"),
)
def p16648(c: Cast) -> None:
    """`AdjacencyGained` is emitted mirrored, so "an enemy moves adjacent to
    you" has to ask who moved -- otherwise the row fires on your own advance
    as readily as on theirs."""
    c.invisible(on=c.me, until=When.SONT)
    c.shift(2)


# -- x7_869 ------------------------------------------------------------------


def _enemy_ended_beside_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1


@power(
    "p14198",
    level=2,
    cls="x7_869",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="an enemy ends its turn adjacent to you",
    on=Trigger(
        TurnEnd, _enemy_ended_beside_me, "an enemy ends its turn adjacent to you"
    ),
)
def p14198(c: Cast) -> None:
    c.teleport(2)


@power(
    "p14199",
    level=6,
    cls="x7_869",
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="an enemy hits or misses you with an attack",
    on=(
        Trigger(Hit, targets_me, "an enemy hits you with an attack"),
        Trigger(Miss, targets_me, "an enemy misses you with an attack"),
    ),
)
def p14199(c: Cast) -> None:
    """The printed Requirement is about another row's remaining uses, which
    is a mid-fight question and so belongs here rather than in a chargen
    gate. `c.use_power` lends the row if the creature has not got it, which
    is wrong for a Requirement that says it must have it unspent."""
    if c.knows("p1449") is None or "p1449" in c.expended():
        return
    c.use_power("p1449")


@power(
    "p14200",
    level=10,
    cls="x7_869",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p14200(c: Cast) -> None:
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="power")

    def shrugged(ev: SavingThrow) -> None:
        if ev.actor == c.me and ev.saved:
            c.temp_hp(5 + c.wis_mod, on=c.me)

    c.watch(SavingThrow, shrugged, until=When.ENCOUNTER)


# -- x7_940 ------------------------------------------------------------------


def _melee_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.main is not None and not gear.main.ranged


@power(
    "p16029",
    level=2,
    cls="x7_940",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[*MARTIAL, *PRIMAL],
    dropped=("c.flat(unpreventable=)",),
)
def p16029(c: Cast) -> None:
    """`DamageRolled` is a decision announced before the blow lands, which is
    why `c.halve` can take half off it and hand that half here. "Nothing can
    reduce the damage you take" is the dropped clause: the share arrives as
    ordinary damage and the sharer's own resistance still eats some of it."""
    ally = c.target
    if ally is None:
        return
    c.bonus(AC, 2, on=ally, until=When.EONT, kind="power")
    c.bonus(FORT, 2, on=ally, until=When.EONT, kind="power")

    def share(ev: DamageRolled) -> None:
        if ev.target != ally or not c.adjacent(ally):
            return
        swung = get(getattr(ev, "detail", ""))
        if swung is not None and swung.reach_of(0).kind not in (
            "melee", "ranged", "close_burst", "close_blast", "area_burst"
        ):
            return
        taken = c.halve(ev)
        if taken:
            c.flat(taken, dtype=ev.dtype, on=c.me)

    c.watch(DamageRolled, share, until=When.EONT, window=Window.BEFORE)


@power(
    "p16030",
    level=6,
    cls="x7_940",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[*MARTIAL, *PRIMAL],
    requires=_melee_weapon,
    requires_text="wielding a melee weapon",
    trigger="an adjacent enemy hits you with a melee attack",
    on=Trigger(
        AttackRolled,
        both(targets_me, by_melee, enemy_within(1)),
        "an adjacent enemy hits you with a melee attack",
    ),
)
def p16030(c: Cast) -> None:
    """Declared on `AttackRolled` and not on `Hit`: the defence is read again
    once this window closes, so a bonus raised here can still turn the blow
    aside. On `Hit` the comparison has already been made and "+2 against the
    triggering attack" would do nothing at all."""
    for defence in (AC, REF):
        c.bonus(defence, 2, on=c.me, until=When.EOT, kind="power")
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p16031",
    level=10,
    cls="x7_940",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[*PRIMAL, Keyword.SUMMONING],
)
def p16031(c: Cast) -> None:
    """`c.call_companion` with no ref is the printed shape exactly: a
    creature with no numbers of its own, whose checks are rolled on its
    summoner's statistics and which takes no turn -- it acts only when the
    summoner spends an action on it.

    The watch is what the drop costs, and `c.endable` hangs the printed
    minor action to dismiss it on the same hold."""
    defender = c.call_companion()
    if not defender:
        return

    def fell(ev: Dropped) -> None:
        if ev.actor == defender and not c.spend_surge(on=c.me):
            c.flat(c.surge_value(of=c.me), on=c.me)

    watching = c.watch(Dropped, fell, until=When.ENCOUNTER)
    c.endable(watching, MINOR, then=c.dismiss_companion)
