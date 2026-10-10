"""Theme rows, batch F: fifteen themes, keyed by their alias refs.

Two attack lines recur and they are not the same problem.

**"Highest ability modifier"** is exact. `_best` computes it, the header
still names one ability so a policy can read a line without running the
body, and `_swing` carries the difference as `plus=`. No marker: nothing
is missing.

**"Primary ability"** is a fact about the *class* that took the theme, and
a theme does not know which class that was. The same stand-in is used --
right for most builds, generous for a few -- and every such row carries
`c.attack_ability()`, the symbol the tree already uses for it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    AdjacencyGained,
    AreaBurst,
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
    DamageRolled,
    DamageType,
    Dropped,
    EnterSquare,
    Healed,
    Health,
    Hit,
    Ident,
    InitiativeRolled,
    Keyword,
    Melee,
    Moved,
    OpportunityWindow,
    Pick,
    Position,
    Powers,
    PowerUsed,
    Ranged,
    SavingThrow,
    Size,
    SkillCheck,
    Stats,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    ZoneEntered,
    about_me,
    both,
    by_melee,
    by_ranged,
    closed_on_me,
    either,
    enemy_within,
    grid,
    hits_me,
    my_check,
    power,
    query,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.zones import Zone

#: "Primary ability modifier" -- see the module docstring.
PSIONIC = [Keyword.PSIONIC]
PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]
ALL_DEFENCES = (AC, FORT, REF, WILL)
#: Every skill the engine has that a "knowledge check" can be.
KNOWLEDGE = ("arcana", "dungeoneering", "history", "nature", "religion")


def _best(c: Cast) -> int:
    """"Your highest ability modifier", and the stand-in for "your primary"."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _swing(c: Cast, **kw: Any) -> Any:
    """`c.strike` with the header's named ability corrected to the best one."""
    return c.strike(plus=_best(c) - c.attack_mod, **kw)


def _live(c: Cast, zid: int) -> bool:
    """Is that zone still on the board? A watch outlives the aura it guards."""
    return any(other == zid for other, _ in c.world.zones.all())


def _inside(c: Cast, zid: int, who: int) -> bool:
    return _live(c, zid) and who in c.world.zones.occupants(zid)


def _square(c: Cast, who: int) -> tuple[int, int] | None:
    pos = c.world.get(who, Position)
    return pos.square if pos is not None else None


def _free_beside(c: Cast) -> tuple[int, int] | None:
    for sq in grid.neighbours(c.here):
        if not c.in_squares([sq]):
            return sq
    return None


def _mine(c: Cast, who: int) -> bool:
    return query.team(c.world, who) is query.team(c.world, c.me)


def _aimed_at_me(c: Cast) -> Callable[[dict[str, Any]], bool]:
    return lambda ctx: ctx.get("target") == c.me


# -- x7_658 -----------------------------------------------------------------


def _me_or_ally_rolled(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None:
        who = getattr(ev, "attacker", None)
    if who is None:
        return False
    if who == me:
        return True
    return (
        query.team(world, who) is query.team(world, me)
        and query.distance_between(world, me, who) <= 5
    )


def _ally_within_10(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    return (
        query.team(world, who) is query.team(world, me)
        and query.distance_between(world, me, who) <= 10
    )


@power(
    "p12244",
    level=0,
    cls="x7_658",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you or an ally in the burst makes an attack roll, save or check",
    on=(
        Trigger(AttackRolled, _me_or_ally_rolled, "you or an ally makes an attack roll"),
        Trigger(SavingThrow, _me_or_ally_rolled, "you or an ally makes a saving throw"),
        Trigger(SkillCheck, _me_or_ally_rolled, "you or an ally makes a skill check"),
    ),
    dropped=("c.boost_roll()",),
)
def p12244(c: Cast) -> None:
    """Three events for one printed sentence. Only the skill-check half can
    be paid: `c.boost_check` settles a check after the die is down, and there
    is no twin of it for an attack roll or a saving throw."""
    points = augment(c, 1)
    gain = c.roll("1d4") + 1 if points else 1
    if isinstance(c.trigger, SkillCheck):
        c.boost_check(gain)


@power(
    "p12245",
    level=2,
    cls="x7_658",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
    dropped=("c.retarget_defence()",),
)
def p12245(c: Cast) -> None:
    """The swap and the redirection are exact. The +2 against the triggering
    attack is not: the roll is already settled by the time a `Hit` is
    announced, so nothing the row lays can change what it is compared to."""
    mate = c.target
    if mate is None:
        return
    c.swap(mate)
    c.redirect(to=mate)


@power(
    "p12246",
    level=3,
    cls="x7_658",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12246(c: Cast) -> None:
    """The printed Requirement is a spend, not a gate on the board, so it is
    paid in the body rather than in `requires=`."""
    if c.first and not c.spend_points(2):
        return
    victim = c.target
    if not _swing(c):
        return
    c.damage("1d8", _best(c), dtype=DamageType.PSYCHIC)
    c.dazed(until=When.EONT)
    near = c.within(3, of=victim, side="ally")
    mate = c.choose(near, "who gains the bonus to damage") if near else None
    if mate is not None:
        c.bonus(
            "damage", 0, dice="1d6", on=mate, until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p12247",
    level=5,
    cls="x7_658",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12247(c: Cast) -> None:
    """One watch, not two: a second save-ends effect would give the victim a
    second throw for one printed sentence. "Bloodied by that damage" is read
    off the blow rather than off `Bloodied`, so the prone and the psychic
    damage stay one event."""
    victim = c.target
    if victim is None:
        return
    if _swing(c):
        c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    mine = _best(c)
    struck: dict[str, int] = {}

    def echo(ev: DamageApplied) -> None:
        foe = ev.target
        if foe == victim or foe not in c.enemies():
            return
        if query.distance_between(c.world, foe, victim) > 5:
            return
        if struck.get("round") == c.world.round:
            return
        struck["round"] = c.world.round
        c.flat(mine, dtype=DamageType.PSYCHIC, on=victim)
        health = c.world.get(foe, Health)
        if health is None:
            return
        half = health.max_hp // 2
        if health.hp <= half < health.hp + ev.amount:
            c.prone(on=victim)

    c.watch(DamageApplied, echo, until=When.SAVE_ENDS, on=victim, label=c.ref)


@power(
    "p12248",
    level=6,
    cls="x7_658",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.PSYCHIC],
    trigger="an ally in the burst makes a skill check or a saving throw",
    on=(
        Trigger(SkillCheck, _ally_within_10, "an ally makes a skill check"),
        Trigger(SavingThrow, _ally_within_10, "an ally makes a saving throw"),
    ),
)
def p12248(c: Cast) -> None:
    """"This power is not expended" is `c.restore_use`, paid only when the
    second roll misses, which is what the card charges for."""
    ev = c.trigger
    mate = getattr(ev, "actor", None)
    if mate is None:
        return
    if isinstance(ev, SkillCheck):
        c.reroll_check(keep="new")
        ok = bool(ev.success)
    else:
        ok = c.reroll_save()
    if not ok:
        c.flat(max(1, c.surge_value() // 2), dtype=DamageType.PSYCHIC, on=mate)
        c.restore_use(c.ref)


@power(
    "p12249",
    level=7,
    cls="x7_658",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12249(c: Cast) -> None:
    """The point cost is paid once for the use, on the first target."""
    if c.first and not c.spend_points(2):
        return
    victim = c.target
    if not _swing(c):
        return
    c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    c.slowed(until=When.EONT)
    for mate in c.in_squares(c.area(), side="ally"):
        c.bonus(
            "damage", 2, on=mate, until=When.EONT, kind="power",
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p12250",
    level=9,
    cls="x7_658",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12250(c: Cast) -> None:
    """The escalation watch is held for the encounter and gated on the daze
    still standing, rather than on a save-ends duration of its own -- two of
    those would be two saving throws for one printed effect."""
    victim = c.target
    if victim is None:
        return
    if _swing(c):
        c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    daze = c.dazed(on=victim, until=When.SAVE_ENDS)

    def worse(ev: Hit) -> None:
        if ev.target != victim or not c.is_(Condition.DAZED, on=victim):
            return
        c.end_effect(daze)
        c.stunned(on=victim, until=When.EONT)

    c.watch(Hit, worse, until=When.ENCOUNTER, once=True)


@power(
    "p12251",
    level=10,
    cls="x7_658",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
    dropped=("c.regain_points()",),
)
def p12251(c: Cast) -> None:
    """`c.spend_surge` is "spend a surge and gain nothing for it", which is
    exactly "the target loses a healing surge". Handing the points back to
    the caster is the half nothing can say."""
    mate = c.target
    if mate is not None:
        c.spend_surge(on=mate)


# -- x7_950 -----------------------------------------------------------------

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p16093",
    level=0,
    cls="x7_950",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
)
def p16093(c: Cast) -> None:
    if not _swing(c):
        return
    c.damage("1d8", _best(c), dtype=DamageType.COLD)
    c.push(2)
    c.slowed(until=When.EONT)
    c.vulnerable(5, DamageType.COLD, until=When.EONT)


@power(
    "p16094",
    level=0,
    cls="x7_950",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p16094(c: Cast) -> None:
    """The zone bites on *ending* a turn in it, which `c.hazard` does not
    say -- that one is entering and starting -- so the watch is written out."""
    if c.first:
        zid = c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)

        def scorch(ev: TurnEnd) -> None:
            if _inside(c, zid, ev.actor):
                c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

        c.watch(TurnEnd, scorch, until=When.EONT)
    if _swing(c):
        c.damage("1d6", _best(c), dtype=DamageType.THUNDER)
        c.prone()


@power(
    "p16095",
    level=2,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p16095(c: Cast) -> None:
    """"Each creature", as printed -- the caster is not excepted."""
    ring = c.aura(2, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def chill(ev: TurnStart) -> None:
        who = ev.actor
        if not _inside(c, ring, who):
            return
        c.slowed(on=who, until=When.SOTNT)
        c.vulnerable(5, DamageType.COLD, on=who, until=When.SOTNT)
        c.penalty("attack", 2, on=who, until=When.SOTNT)

    c.watch(TurnStart, chill, until=When.ENCOUNTER)


@power(
    "p16096",
    level=2,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p16096(c: Cast) -> None:
    """"Willingly leaves" is asked of `Moved`, which is the only movement
    event carrying both where the creature came from and how it got there --
    a shove out of the aura is not a departure the card charges for."""
    ring = c.aura(2, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    held = c.world.get(ring, Zone)
    if held is not None:
        held.difficult = True
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    began: dict[int, int] = {}

    def note(ev: TurnStart) -> None:
        if _inside(c, ring, ev.actor):
            began[ev.actor] = c.distance(to=ev.actor)

    def retreat(ev: TurnEnd) -> None:
        who = ev.actor
        if who not in c.enemies() or not _inside(c, ring, who):
            return
        if c.distance(to=who) > began.get(who, 0):
            c.flat(5, dtype=DamageType.FIRE, on=who)

    def leaving(ev: Moved) -> None:
        if getattr(ev, "kind_", "") in ("push", "pull", "slide", "forced"):
            return
        if ev.actor not in c.enemies() or not _live(c, ring):
            return
        zone = c.world.get(ring, Zone)
        if zone is None:
            return
        if ev.from_ in zone.squares and ev.to not in zone.squares:
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, note, until=When.ENCOUNTER)
    c.watch(TurnEnd, retreat, until=When.ENCOUNTER)
    c.watch(Moved, leaving, until=When.ENCOUNTER)


@power(
    "p16097",
    level=6,
    cls="x7_950",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.ZONE],
    dropped=("c.forces(in_zone=)", "c.ice_walk()"),
)
def p16097(c: Cast) -> None:
    """The ice and the icicles are two things: a difficult zone, and three
    solid squares with a once-a-turn bite around each. The extra square of
    forced movement inside the zone belongs to whoever is doing the shoving
    and nothing extends another creature's push; "creatures that have ice
    walk" names a trait the engine has no word for."""
    area = c.area()
    c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    free = [sq for sq in sorted(area) if not c.in_squares([sq])][:3]
    for sq in free:
        c.wall(1, at=sq, solid=True, until=When.ENCOUNTER, label=c.ref)
    cold = {n for sq in free for n in grid.neighbours(sq)} | set(free)
    bitten: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == c.me or bitten.get(who) == c.world.round:
            return
        bitten[who] = c.world.round
        c.flat(5, dtype=DamageType.COLD, on=who)

    def stepped(ev: EnterSquare) -> None:
        if ev.square in cold:
            bite(ev.actor)

    def lingered(ev: TurnEnd) -> None:
        if any(sq in cold for sq in query.squares(c.world, ev.actor)):
            bite(ev.actor)

    c.watch(EnterSquare, stepped, until=When.ENCOUNTER)
    c.watch(TurnEnd, lingered, until=When.ENCOUNTER)


@power(
    "p16098",
    level=6,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p16098(c: Cast) -> None:
    """All three clauses are laid again on each sustain, which is what
    "the effect persists until the end of your next turn" means for a set of
    one-turn modifiers."""

    def armour() -> None:
        c.resist(5, DamageType.FIRE, on=c.me, until=When.EONT)
        c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
        c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")

        def sear(ev: Hit) -> None:
            if ev.target == c.me and by_melee(c.world, c.me, ev):
                c.flat(5, dtype=DamageType.FIRE, on=ev.attacker)

        c.watch(Hit, sear, until=When.EONT)

    armour()
    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR), armour)


@power(
    "p16099",
    level=10,
    cls="x7_950",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    dropped=("c.conjure(porous=)", "c.opportunity_from(square)"),
)
def p16099(c: Cast) -> None:
    """Three solid conjurations that move on a move action, which `speed=`
    already gives them. A guardian your allies can walk through but enemies
    cannot is one wall for one side, and swinging from a guardian's square
    is a standing leave `c.strike(from_=)` cannot be given."""
    spots = [sq for sq in sorted(c.area()) if not c.in_squares([sq])][:3]
    for sq in spots:
        c.conjure(
            at=sq, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=3, solid=True
        )


# -- x7_868 -----------------------------------------------------------------

PRIMAL_POLYMORPH = [Keyword.PRIMAL, Keyword.POLYMORPH]


@power(
    "p14192",
    level=0,
    cls="x7_868",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_POLYMORPH,
    once_per_round=True,
    dropped=("c.form(on_revert=)", "c.form(keeps_gear=)"),
)
def p14192(c: Cast) -> None:
    """Tiny, unable to attack, climbing at half speed. The shift paid on
    changing *back* hangs on the reversion, which `c.form` has no hook for,
    and the equipment clause -- worn gear keeps working, shields and item
    powers do not -- is a second thing it cannot carry."""
    c.form(
        modes={"climb": max(1, c.speed_of(c.me) // 2)},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    c.resize(Size.TINY, on=c.me, until=When.ENCOUNTER)
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:stealth", 4, on=c.me, until=When.ENCOUNTER)


@power(
    "p14193",
    level=0,
    cls="x7_868",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_POLYMORPH,
    once_per_round=True,
    dropped=("etl.item.inline_block()",),
)
def p14193(c: Cast) -> None:
    """Hybrid form keeps every statistic, so the form itself lays nothing at
    all. What the card grants is the attack printed under it, and that block
    has no ref of its own -- there is nothing to decorate."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)


def _my_crit(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and bool(getattr(ev, "critical", False))


@power(
    "p14195",
    level=2,
    cls="x7_868",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.FEAR],
    trigger="you score a critical hit",
    on=Trigger(Hit, _my_crit, "you score a critical hit"),
)
def p14195(c: Cast) -> None:
    c.penalty("attack", 4, until=When.EONT, when=_aimed_at_me(c))


@power(
    "p14196",
    level=6,
    cls="x7_868",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    narrative=("skill:thievery",),
)
def p14196(c: Cast) -> None:
    """The Stealth half is exact, bonus and reroll both. Thievery is the
    other skill named and nothing on a board ever rolls one -- picking a
    lock is not a fight -- so that bonus has nowhere to go and no mechanism
    is missing behind it."""
    held = c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="power")

    def again(ev: SkillCheck) -> None:
        if ev.actor != c.me or ev.skill != "stealth":
            return
        c.end_effect(held, on=c.me)
        c.trigger = ev
        c.reroll_check(keep="new", bonus=5)

    c.arm_trigger(SkillCheck, again, cost=FREE, until=When.ENCOUNTER, label=c.ref)


@power(
    "p14197",
    level=10,
    cls="x7_868",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p14197(c: Cast) -> None:
    """"Stand up or move" is one or the other and standing is only ever the
    answer when the fight opened with you down."""
    c.initiative(4, on=c.me)
    if c.is_(Condition.PRONE, on=c.me):
        c.grant_action("stand", FREE, on=c.me)
    else:
        c.move(c.speed_of(c.me), who=c.me)


# -- x7_857 -----------------------------------------------------------------

MARTIAL = [Keyword.MARTIAL]


def _ally_within_2_hit(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    return query.distance_between(world, me, who) <= 2


def _adjacent_ally_hit(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    return query.adjacent(world, me, who)


@power(
    "p14149",
    level=0,
    cls="x7_857",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally within 2 squares is hit and you are not a target",
    on=Trigger(Hit, _ally_within_2_hit, "an ally within 2 squares is hit"),
)
def p14149(c: Cast) -> None:
    """"After the attack is resolved" is a one-shot watch on the blow landing
    -- taking the swing here would put it before the attack it answers."""
    ev = c.trigger
    mate = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if mate is None or foe is None:
        return
    c.swap(mate)
    c.redirect(to=c.me)

    def riposte(hurt: DamageApplied) -> None:
        if hurt.target == c.me:
            c.basic(on=foe)

    c.watch(DamageApplied, riposte, until=When.EOT, once=True)


@power(
    "p14151",
    level=2,
    cls="x7_857",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target("ally", 2),
    keywords=MARTIAL,
)
def p14151(c: Cast) -> None:
    """"You and one ally" is two targets from the `"ally"` pool, which in a
    *target line* is the one that already includes the caster -- `dsl` and
    `c.within` spell that side differently and only the latter leaves you
    out."""
    for defence in ALL_DEFENCES:
        c.bonus(defence, 2, until=When.EONT, kind="power")
    c.no_advantage(on=c.target, until=When.EONT)


def _surprised_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and ev.condition is Condition.SURPRISED


@power(
    "p14152",
    level=6,
    cls="x7_857",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are surprised at the start of an encounter",
    on=Trigger(ConditionApplied, _surprised_me, "you are surprised"),
)
def p14152(c: Cast) -> None:
    """`targets_me` is not usable here: `ConditionApplied` names its subject
    `target`, and the condition has to be read as well."""
    c.cure(Condition.SURPRISED, on=c.me)


@power(
    "p14153",
    level=10,
    cls="x7_857",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    trigger="an adjacent ally is hit by an attack that does not include you",
    on=Trigger(Hit, _adjacent_ally_hit, "an adjacent ally is hit"),
)
def p14153(c: Cast) -> None:
    c.redirect(to=c.me)

    def paid(hurt: DamageApplied) -> None:
        if hurt.target == c.me:
            c.surge(on=c.me)

    c.watch(DamageApplied, paid, until=When.EOT, once=True)


# -- x7_870 -----------------------------------------------------------------

PRIMAL = [Keyword.PRIMAL]


@power(
    "p14201",
    level=0,
    cls="x7_870",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p14201(c: Cast) -> None:
    """Refused at the window rather than handed out as an immunity: the
    printed line takes the *attack* away from anybody standing inside, and
    `c.no_provoke` names one protected creature at a time."""
    ring = c.aura(2, label=c.ref, until=When.EONT)

    def shut(ev: OpportunityWindow) -> None:
        if ev.actor in c.enemies() and _inside(c, ring, ev.actor):
            ev.cancel("inside the aura")

    c.watch(OpportunityWindow, shut, until=When.EONT, window=Window.BEFORE)


@power(
    "p14202",
    level=2,
    cls="x7_870",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you dislike a History, Nature or Religion check",
    on=Trigger(SkillCheck, my_check("history", "nature", "religion"), "your check"),
)
def p14202(c: Cast) -> None:
    """"Use the second result, even if it's lower" is `keep="new"`."""
    c.reroll_check(keep="new", bonus=5)


@power(
    "p14203",
    level=6,
    cls="x7_870",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    dropped=("c.ability_check()",),
)
def p14203(c: Cast) -> None:
    """Athletics is a skill the engine rolls -- an escape, a bull rush. A
    bare Strength ability check is not a skill and has no key."""
    c.bonus("skill:athletics", 4, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p14204",
    level=10,
    cls="x7_870",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
    dropped=("events.TempHP.cancel",),
)
def p14204(c: Cast) -> None:
    """`Healed` is a `Decision` so the healing half is refused outright.
    `TempHP` is a plain notification announced after the points have landed,
    so the other half of the same sentence cannot be refused at all."""
    zid = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)

    def deny(ev: Healed) -> None:
        if ev.target in c.enemies() and _inside(c, zid, ev.target):
            ev.cancel("inside the zone")

    def shelter(ev: TurnEnd) -> None:
        if _mine(c, ev.actor) and _inside(c, zid, ev.actor):
            c.temp_hp(5, on=ev.actor)

    c.watch(Healed, deny, until=When.ENCOUNTER, window=Window.BEFORE)
    c.watch(TurnEnd, shelter, until=When.ENCOUNTER)


# -- x7_916 -----------------------------------------------------------------

ARCANE = [Keyword.ARCANE]


def _guard_of(c: Cast) -> int | None:
    for eid in c.within(20, side="team"):
        ident = c.world.get(eid, Ident)
        if ident is not None and ident.ref == "x10_57":
            return eid
    return None


@power(
    "p15885",
    level=0,
    cls="x7_916",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=ARCANE,
    dropped=("c.no_turn(who)", "loader.spawn(x10_57)"),
)
def p15885(c: Cast) -> None:
    """`c.cast_from` is the printed "you make the roll using your
    statistics".

    **`x10_57` has a block now** (#459), so the `try`/`except KeyError` that
    guarded a missing row is gone -- the guard was hiding the gap, and a
    `KeyError` is what a genuinely absent ref should do. Its hit points are
    "your healing surge value" and its defences are the summoner's, which is
    what the block says and what `spawn_associate` reads.

    The half still missing is that the guard has no actions of its own and
    `c.summon` puts it in the initiative order."""
    guard = c.summon("x10_57")
    if not guard:
        return
    c.cast_from(c.me, on=guard, until=When.ENCOUNTER)

    def toll(ev: Dropped) -> None:
        if ev.actor == guard:
            c.spend_surge(on=c.me)

    c.watch(Dropped, toll, until=When.ENCOUNTER, once=True)


@power(
    "p15886",
    level=2,
    cls="x7_916",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=ARCANE,
)
def p15886(c: Cast) -> None:
    """The point only comes back if the ally actually spent one."""
    mate = c.target
    if mate is None:
        return
    if c.action_point(STANDARD, who=mate):
        c.grant_action_point(1, on=c.me)


@power(
    "p15887",
    level=6,
    cls="x7_916",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p15887(c: Cast) -> None:
    guard = _guard_of(c)
    c.move(c.speed_of(c.me) + 2, who=c.me)
    if guard is None:
        return
    c.move(c.speed_of(guard) + 2, who=guard)
    if c.adjacent(to=guard):
        value = c.surge_value()
        c.temp_hp(value, on=c.me)
        c.temp_hp(value, on=guard)


@power(
    "p15888",
    level=10,
    cls="x7_916",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    dropped=("c.surge_from(who)",),
)
def p15888(c: Cast) -> None:
    """The trade is `c.give` with a body: a minor action the ally takes once,
    which spends one of the caster's levelled rows and hands the ally back an
    expended row of the same usage and level. Spending the ally's surges as
    though they were the caster's is a standing permission and there is no
    verb that lends a surge pool."""
    mate = c.target
    if mate is None:
        return

    def trade(who: int) -> None:
        ours = c.world.get(c.me, Powers)
        if ours is None:
            return
        spent = set(c.expended())
        mine = [
            ref
            for ref in ours.known
            if ref not in spent
            and REGISTRY.get(ref) is not None
            and REGISTRY[ref].usage in (ENCOUNTER, DAILY)
            and REGISTRY[ref].level > 0
        ]
        pick = c.choose(sorted(mine), "which of your rows to give up") if mine else None
        if pick is None:
            return
        c.expend_row(pick)
        want = REGISTRY[pick]
        back = sorted(
            ref
            for ref in c.expended(on=who)
            if REGISTRY.get(ref) is not None
            and REGISTRY[ref].usage == want.usage
            and REGISTRY[ref].level == want.level
        )
        if back:
            c.restore_use(back[0], on=who)

    c.give(fn=trade, on=mate, uses=1, cost=MINOR)


# -- x7_936 -----------------------------------------------------------------


def _felled_adjacent(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and query.adjacent(world, me, ev.actor)


def _ours_bloodied_nearby(world: Any, me: int, ev: Any) -> bool:
    foe = getattr(ev, "source", None)
    if foe is None or query.team(world, foe) is query.team(world, me):
        return False
    if query.team(world, ev.actor) is not query.team(world, me):
        return False
    return query.distance_between(world, me, foe) <= 5


def _low_roll(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if who is None:
        who = getattr(ev, "actor", None)
    return who == me and 1 <= getattr(ev, "natural", 0) <= 3


@power(
    "p16005",
    level=0,
    cls="x7_936",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger="you bloody or drop an adjacent enemy",
    on=(
        Trigger(Bloodied, _felled_adjacent, "you bloody an adjacent enemy"),
        Trigger(Dropped, _felled_adjacent, "you drop an adjacent enemy"),
    ),
    dropped=("c.surrender()",),
)
def p16005(c: Cast) -> None:
    """Both halves of the trigger are declared -- `Bloodied` and `Dropped`
    each carry `source`. Forcing a beaten enemy to surrender is a second
    thing entirely: nothing takes a creature out of a fight that way."""
    held = [
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=_aimed_at_me(c))
        for foe in c.enemies()
        if c.can_see(to=foe)
    ]

    def over(ev: Hit) -> None:
        if ev.target != c.me:
            return
        for effect in held:
            c.end_effect(effect)

    c.watch(Hit, over, until=When.ENCOUNTER, once=True)


@power(
    "p16006",
    level=2,
    cls="x7_936",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you roll a natural 1, 2 or 3",
    on=(
        Trigger(AttackRolled, _low_roll, "a natural 1-3 on an attack roll"),
        Trigger(SkillCheck, _low_roll, "a natural 1-3 on a skill check"),
    ),
)
def p16006(c: Cast) -> None:
    if isinstance(c.trigger, SkillCheck):
        c.reroll_check(keep="new", bonus=c.cha_mod)
    else:
        c.reroll_attack(keep="new", bonus=c.cha_mod)


@power(
    "p16007",
    level=6,
    cls="x7_936",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p16007(c: Cast) -> None:
    """The chase is asked at `TurnEnd`, which is where the printed "ends its
    next turn" is decided; the damage bonus answers the *declaration*, so it
    is paid whether the enemy's swing lands or not."""
    victim = c.target
    if victim is None:
        return

    def closing(ev: TurnEnd) -> None:
        if ev.actor != victim or c.adjacent(to=victim):
            return
        where = _square(c, victim)
        if where is None:
            return
        for sq in grid.neighbours(where):
            if not c.in_squares([sq]):
                c.shift(c.speed_of(c.me), to=sq)
                return

    def provoked(ev: AttackDeclared) -> None:
        if ev.attacker != victim or ev.target != c.me:
            return
        c.bonus(
            "damage", 5, on=c.me, until=When.EONT, kind="power",
            when=lambda ctx: ctx.get("target") == victim,
        )

    c.watch(TurnEnd, closing, until=When.EOTNT, once=True)
    c.watch(AttackDeclared, provoked, until=When.EOTNT, once=True)


@power(
    "p16008",
    level=10,
    cls="x7_936",
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger="you or an ally is bloodied by an enemy within 5 squares",
    on=Trigger(Bloodied, _ours_bloodied_nearby, "an enemy bloodies one of yours"),
)
def p16008(c: Cast) -> None:
    """The enemy comes off `Bloodied.source`, not off `ev.targets`: this row
    is `NO_TARGET` and never touched the creature it names."""
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, until=When.ENCOUNTER, to="team")

    def cowed(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == foe:
            c.penalty("attack", 2, on=foe, until=When.EOTNT)

    c.watch(Hit, cowed, until=When.ENCOUNTER)


# -- x7_947 -----------------------------------------------------------------


def _my_melee_roll(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and by_melee(world, me, ev)


@power(
    "p16081",
    level=0,
    cls="x7_947",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.WEAPON],
    trigger="you make a melee weapon attack roll",
    on=Trigger(AttackRolled, _my_melee_roll, "you make a melee attack roll"),
    dropped=("c.reroll_attack(both=)",),
)
def p16081(c: Cast) -> None:
    """"Roll twice" is `keep="best"`. "If both rolls hit" is a question about
    the roll that was thrown away, which the settled event no longer holds."""
    c.reroll_attack(keep="best")


@power(
    "p16082",
    level=2,
    cls="x7_947",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you are bloodied by an attack",
    on=Trigger(Bloodied, about_me, "you are bloodied"),
)
def p16082(c: Cast) -> None:
    """`about_me` is right here -- `Bloodied` names its subject `actor`."""
    c.surge(on=c.me)
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
    c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p16083",
    level=6,
    cls="x7_947",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("spec.feature_ref()",),
)
def p16083(c: Cast) -> None:
    """The whole effect is "resistance equal to what your level 5 feature
    grants", and the card never prints the number. Nothing reads another
    row's amount, so there is no figure to resist with and the bloodied
    clause has nothing to add 2 to."""


@power(
    "p16084",
    level=10,
    cls="x7_947",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
    dropped=("resolve.attack.weapon",),
)
def p16084(c: Cast) -> None:
    """19-20 is `crit_range` 1; 18-20 would be 2. The gate is the nearest the
    attack context can get to "melee weapon" -- it carries `ranged` and
    `opportunity` but says nothing about what is in hand."""
    c.stance(label=c.ref)
    c.bonus(
        "crit_range", 1, on=c.me, until=When.STANCE,
        when=lambda ctx: not ctx.get("ranged"),
    )
    c.bonus(
        "attack", 2, on=c.me, until=When.STANCE, kind="power",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


# -- x7_978 -----------------------------------------------------------------


@power(
    "p16391",
    level=0,
    cls="x7_978",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM],
    dropped=("AttackDeclared.reach",),
)
def p16391(c: Cast) -> None:
    """The bar covers every attack, not only the melee and ranged ones the
    card names: `AttackDeclared` carries the power's ref and its defence and
    nothing about how far away it was thrown from."""
    held = []
    for foe in c.enemies():
        stats = c.world.get(foe, Stats)
        if stats is not None and stats.level <= c.level:
            held.append(c.cannot_attack(on=foe, against=c.me, until=When.EONT))

    def spent(ev: AttackDeclared) -> None:
        if ev.attacker != c.me:
            return
        for effect in held:
            c.end_effect(effect)

    c.watch(AttackDeclared, spent, until=When.EONT, once=True)


@power(
    "p16392",
    level=2,
    cls="x7_978",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger="you would make a Diplomacy or an Intimidate check",
    on=Trigger(SkillCheck, my_check("diplomacy", "intimidate"), "one of those checks"),
    dropped=("c.swap_check()",),
    narrative=("skill:diplomacy",),
)
def p16392(c: Cast) -> None:
    """The +2 is laid on Arcana, which is where the card moves the roll to;
    swapping one check for another is `c.pre_empt(ref, clause)`, not in `Cast`,
    so the original check still happens. Counting as sharing a language with
    the subject of a Diplomacy check is the other clause, and no board ever
    asks what language two creatures have in common."""
    c.bonus("skill:arcana", 2, on=c.me, until=When.EOT, kind="power")


@power(
    "p16393",
    level=6,
    cls="x7_978",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    narrative=("skill:diplomacy", "skill:intimidate"),
)
def p16393(c: Cast) -> None:
    """The Will bonus is exact and gated on standing in the aura. The other
    clause scales a Diplomacy and Intimidate bonus with how many allies are
    inside, and a board rolls neither check -- talking a guard round is not a
    fight -- so the scaling has nowhere to land and nothing is missing."""
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    for mate in c.allies():
        c.bonus(
            WILL, 2, on=mate, until=When.ENCOUNTER, kind="power",
            when=lambda ctx, w=mate: _inside(c, ring, w),
        )


@power(
    "p16394",
    level=10,
    cls="x7_978",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.FIRE],
    trigger="an enemy within 5 squares hits you",
    on=Trigger(Hit, both(hits_me, enemy_within(5)), "an enemy within 5 hits you"),
)
def p16394(c: Cast) -> None:
    """The burn is paid only when the second roll still lands, so the live
    result is read back off the event rather than assumed."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.reroll_attack(keep="new")
    result = getattr(c.trigger, "result", None)
    if result is not None and result.hit:
        c.flat(5 + c.level // 2, dtype=DamageType.FIRE, on=foe)


# -- x7_988 -----------------------------------------------------------------

#: "You must have a trap-making kit on your person." Mundane gear is not
#: modelled, so the Requirement never refuses the row.
#: "You must have a trap-making kit on your person."
#: **Re-aimed off `c.carrying(ref)`.** That one arrived and is not this: it
#: reads the `Item` component, which is a thing a *power* made and handed
#: over, and a kit is ordinary equipment. `Gear` records weapons, a shield,
#: armour, worn magic and ammunition and has no slot for the rest, so there
#: is no ref to ask for -- and a printed Requirement is a `requires=` gate,
#: handed `(world, eid)`, which cannot call a `Cast` method at all.
KIT = ("Gear.carried",)


def _enemy_closed(world: Any, me: int, ev: Any) -> bool:
    if not closed_on_me(world, me, ev):
        return False
    return query.team(world, ev.mover) is not query.team(world, me)


def _within_5_of(spot: tuple[int, int]) -> set[tuple[int, int]]:
    return {
        (spot[0] + dx, spot[1] + dy)
        for dx in range(-5, 6)
        for dy in range(-5, 6)
    }


@power(
    "p16442",
    level=0,
    cls="x7_988",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(INT, vs=REF, plus=2),
    trigger="an enemy enters a square adjacent to you",
    on=Trigger(AdjacencyGained, _enemy_closed, "an enemy moves adjacent to you"),
    dropped=KIT,
)
def p16442(c: Cast) -> None:
    """Aimed off `AdjacencyGained.mover` rather than off `ev.targets`: an
    immediate reaction picks its targets before it knows what set it off."""
    foe = getattr(c.trigger, "mover", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage("1d6", c.int_mod, on=foe)
    c.grants_advantage(on=foe, until=When.EONT, to="team")


@power(
    "p16443",
    level=2,
    cls="x7_988",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    dropped=(*KIT, "Condition.INVISIBLE"),
)
def p16443(c: Cast) -> None:
    """The trap is a zone five squares across that springs on the first
    creature the caster cannot see. Stripping the invisibility itself has
    nothing to take away -- there is no condition for it."""
    spot = _free_beside(c)
    if spot is None:
        return
    field = c.zone(_within_5_of(spot), label=c.ref, until=When.ENCOUNTER)

    def sprung(ev: ZoneEntered) -> None:
        if ev.zone != field or ev.actor == c.me or c.can_see(to=ev.actor):
            return
        c.penalty("skill:stealth", 10, on=ev.actor, until=When.SAVE_ENDS)
        c.dispel(field)

    c.watch(ZoneEntered, sprung, until=When.ENCOUNTER, once=True)


@power(
    "p16444",
    level=6,
    cls="x7_988",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    dropped=KIT,
)
def p16444(c: Cast) -> None:
    """One save-ends effect per creature, not two: the prone half is a watch
    held for the encounter and gated on the creature still granting combat
    advantage, so the card's single "save ends both" is one throw."""
    spot = _free_beside(c)
    if spot is None:
        return
    field = c.zone(_within_5_of(spot), label=c.ref, until=When.ENCOUNTER)
    caught: set[int] = set()

    def sprung(ev: ZoneEntered) -> None:
        if ev.zone != field or ev.actor not in c.enemies():
            return
        c.dispel(field)
        crowd = [ev.actor, *(o for o in c.within(1, of=ev.actor) if o != ev.actor)]
        caught.update(crowd)
        for one in crowd:
            c.grants_advantage(on=one, until=When.SAVE_ENDS, to="team")

    def topple(ev: Hit) -> None:
        if ev.target in caught and query.grants_ca(c.world, ev.target):
            c.prone(on=ev.target)

    c.watch(ZoneEntered, sprung, until=When.ENCOUNTER, once=True)
    c.watch(Hit, topple, until=When.ENCOUNTER)


@power(
    "p16445",
    level=10,
    cls="x7_988",
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    todo=("events.HazardTriggered",),
)
def p16445(c: Cast) -> None:
    """The whole row hangs on a hazard, an object or a trap going off, and
    nothing announces that -- `c.hazard` bites inside its own handler and
    emits only the damage. With no event there is no trigger to declare, and
    a row with a prose trigger can never fire."""


# -- x7_1001 ----------------------------------------------------------------


def _damage_to_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me


@power(
    "p16574",
    level=0,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage from an attack",
    on=Trigger(DamageRolled, _damage_to_me, "you take damage"),
)
def p16574(c: Cast) -> None:
    """Declared on `DamageRolled`, which is the window in which a number can
    still be taken off it; a `Hit` fires before the blow has been rolled."""
    c.reduce(5 + c.level)
    c.resist(5, on=c.me, until=When.SONT)


@power(
    "p16575",
    level=2,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger="you are hit by a melee or a ranged attack",
    on=Trigger(Hit, both(hits_me, either(by_melee, by_ranged)), "you are hit"),
)
def p16575(c: Cast) -> None:
    mate = c.target
    if mate is not None:
        c.redirect(to=mate)


@power(
    "p16576",
    level=6,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p16576(c: Cast) -> None:
    """The vulnerability is the ally's and the attack bonus is the caster's,
    which is the whole trade the card prints."""
    if c.target is None:
        return
    c.vulnerable(2, until=When.EONT)
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p16577",
    level=10,
    cls="x7_1001",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def p16577(c: Cast) -> None:
    """Three printed options, offered in the card's order."""
    pick = c.choose(["martial", "healing", "p488"], "which favour")
    if pick == "martial":
        for foe in c.in_squares(c.area(), side="enemy"):
            c.grants_advantage(on=foe, until=When.EONT, to="team")
            c.penalty("attack", 4, on=foe, until=When.EONT)
    elif pick == "healing":
        c.surge(on=c.me)
        mates = c.in_squares(c.area(), side="ally")
        if mates:
            c.surge(on=mates[0])
    else:
        for one in [c.me, *c.in_squares(c.area(), side="ally")]:
            c.bonus("damage", 4, on=one, until=When.EONT, kind="power")


# -- x7_1013 ----------------------------------------------------------------


def _my_opportunity_hit(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and bool(
        getattr(ev, "opportunity", False)
    )


@power(
    "p16630",
    level=0,
    cls="x7_1013",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.FEAR],
    trigger="you hit an enemy with an opportunity attack",
    on=Trigger(Hit, _my_opportunity_hit, "you hit with an opportunity attack"),
)
def p16630(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; it rides as a plain attribute."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.immobilized(on=foe, until=When.EOTNT)


@power(
    "p16631",
    level=3,
    cls="x7_1013",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.SHADOW, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p16631(c: Cast) -> None:
    if _swing(c):
        c.damage(c.w(), _best(c))
        c.penalty(WILL, 2, until=When.EONT)


@power(
    "p16632",
    level=6,
    cls="x7_1013",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.SHADOW, Keyword.STANCE],
)
def p16632(c: Cast) -> None:
    c.stance(label=c.ref)

    def struck(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        c.grants_advantage(on=ev.target, until=When.EONT, to="team")
        c.push(1, on=ev.target)

    c.watch(Hit, struck, until=When.STANCE)


@power(
    "p16633",
    level=10,
    cls="x7_1013",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
    dropped=("c.deals(untyped_only=)",),
)
def p16633(c: Cast) -> None:
    """`c.deals` is an override of the whole type, which is more than the
    card grants -- it recolours a weapon attack that already named one."""
    c.stance(label=c.ref)
    c.phasing(on=c.me, until=When.STANCE)
    c.resist(10, DamageType.NECROTIC, on=c.me, until=When.STANCE)
    c.deals(DamageType.NECROTIC, on=c.me, until=When.STANCE)


# -- x7_867 -----------------------------------------------------------------


@power(
    "p14189",
    level=2,
    cls="x7_867",
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
)
def p14189(c: Cast) -> None:
    """The halving is armed as a one-shot on `DamageRolled`: the interrupt
    answers the hit, and on a `Hit` the blow has not been rolled, so `c.halve`
    there reads an amount of nothing. The save waits for the blow to land."""

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me:
            c.halve(ev)

    def after(ev: DamageApplied) -> None:
        if ev.target == c.me:
            c.save(on=c.me)

    c.watch(DamageRolled, soften, until=When.EOT, once=True, window=Window.BEFORE)
    c.watch(DamageApplied, after, until=When.EOT, once=True)


@power(
    "p14190",
    level=6,
    cls="x7_867",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM],
)
def p14190(c: Cast) -> None:
    """One save-ends effect for the printed "save ends both": the opportunity
    bar is held on the caster for the encounter and taken off with the other
    half, rather than giving the victim a second throw."""
    victim = c.target
    if victim is None:
        return
    held = [
        c.no_provoke(from_=victim, on=c.me, until=When.ENCOUNTER),
        c.grants_advantage(on=victim, until=When.SAVE_ENDS, to="me"),
    ]

    def broken(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or ev.target != victim:
            return
        for effect in held:
            c.end_effect(effect)

    c.watch(AttackDeclared, broken, until=When.ENCOUNTER, once=True)


@power(
    "p14191",
    level=10,
    cls="x7_867",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    dropped=("query.concealed()",),
)
def p14191(c: Cast) -> None:
    """Cover is a question the attack context can be asked -- it carries the
    attacker, and the board measures the rest. Concealment is a modifier laid
    by `c.conceal` and nothing reads it back, so half the printed condition
    cannot be tested."""
    c.stance(label=c.ref)
    me = c.me

    def sheltered(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and bool(query.cover_between(c.world, who, me))

    for defence in ALL_DEFENCES:
        c.bonus(defence, 4, on=me, until=When.STANCE, kind="power", when=sheltered)
    c.ignores_difficult(kind="shift", on=me, until=When.STANCE)


# -- x7_915 -----------------------------------------------------------------


@power(
    "p15881",
    level=2,
    cls="x7_915",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p15881(c: Cast) -> None:
    """The target is the caster's companion, which is asked of the board
    rather than picked -- a companion is not a legal target line."""
    pet = c.companion()
    if pet is not None:
        c.heal(c.surge_value(), on=pet)


@power(
    "p15882",
    level=6,
    cls="x7_915",
    usage=AT_WILL,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE,
    dropped=("c.recall(who)",),
)
def p15882(c: Cast) -> None:
    """Sending the companion away is `Condition.REMOVED`. Calling it back
    into an unoccupied square beside you is the other half of the same
    sentence and nothing puts a removed creature back on the board."""
    pet = c.companion()
    if pet is not None:
        c.condition(Condition.REMOVED, on=pet, until=When.ENCOUNTER)


@power(
    "p15883",
    level=10,
    cls="x7_915",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
    dropped=("c.senses_of(who)",),
)
def p15883(c: Cast) -> None:
    """The companion's aura is copied by radius off the live zone rather than
    guessed. Its senses are a set of traits nothing enumerates."""
    pet = c.companion()
    shape = c.form(
        modes={"walk": c.speed_of(pet)} if pet is not None else None,
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    if pet is not None:
        radius = 0
        for _zid, zone in c.world.zones.all():
            if zone.owner == pet and zone.aura:
                radius = zone.aura
        if radius:
            c.aura(radius, label=c.ref, on=c.me, until=When.ENCOUNTER)

    def other(ev: PowerUsed) -> None:
        if ev.actor == c.me and ev.power != c.ref:
            c.end_effect(shape)

    c.watch(PowerUsed, other, until=When.ENCOUNTER, once=True)


# -- x7_1016 ----------------------------------------------------------------


@power(
    "p16668",
    level=2,
    cls="x7_1016",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you dislike an opposed Perception or Stealth check",
    on=Trigger(SkillCheck, my_check("perception", "stealth"), "one of those checks"),
    dropped=("SkillCheck.opposed",),
)
def p16668(c: Cast) -> None:
    """"Use either result" is `keep="best"`. Whether the check was *opposed*
    is not on the event: a `SkillCheck` carries a DC and no second roller."""
    c.reroll_check(keep="best")


@power(
    "p16669",
    level=6,
    cls="x7_1016",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you dislike an Insight, Perception, Streetwise or knowledge check",
    on=Trigger(
        SkillCheck,
        my_check("insight", "perception", "streetwise", *KNOWLEDGE),
        "one of those checks",
    ),
)
def p16669(c: Cast) -> None:
    """"As if you had rolled a 20" is arithmetic on the check that is already
    down: the difference goes on as a bonus and the total comes out right."""
    ev = c.trigger
    if isinstance(ev, SkillCheck):
        c.boost_check(20 - ev.natural)


@power(
    "p16670",
    level=10,
    cls="x7_1016",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def p16670(c: Cast) -> None:
    """Both printed ways out are declared -- taking damage and swinging --
    so the bonus is not simply left standing for the encounter."""
    held = [
        c.bonus(f"skill:{skill}", 5, on=c.me, until=When.ENCOUNTER, kind="power")
        for skill in ("perception", "insight", *KNOWLEDGE)
    ]

    def over() -> None:
        for effect in held:
            c.end_effect(effect)

    def hurt(ev: DamageApplied) -> None:
        if ev.target == c.me:
            over()

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me:
            over()

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, once=True)
    c.watch(AttackDeclared, swung, until=When.ENCOUNTER, once=True)
    # Blindsight 1, which is the printed range -- adjacent only, so it is a
    # much narrower sense than the skill bonuses beside it.
    held.append(c.blindsight(1, on=c.me, until=When.ENCOUNTER))
