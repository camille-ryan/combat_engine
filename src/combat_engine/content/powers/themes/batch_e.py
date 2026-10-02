"""Fifteen themes, keyed by their alias refs.

Two unnamed-ability shapes run through this file and they are not the same
question.

**"Primary ability vs. AC"** cannot be said: a theme does not know which
class took it, and `Attack` refuses a line with neither an ability nor a
printed bonus. So the header names one -- Strength, which is what every
melee weapon theme here swings with -- the body reads `c.attack_mod` so
the damage line follows whatever the header says, and the choice itself
is `dropped=("c.ability_for(ref)",)`, the marker twenty-one rows already
carry for exactly this.

**"Highest ability modifier"** *can* be said, and is. `c.str_` and its
five siblings are whole attack bonuses over the same half-level,
proficiency and enhancement, so the largest of the six is the printed
line to the point. Those rows call `c.attack(...)` and declare no header
attack, which is the documented trade: a policy cannot read the hit
chance off the card, and in exchange the number is right.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
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
    WILL,
    ActionPointSpent,
    ActionType,
    AdjacencyGained,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Defense,
    Dropped,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    MoveEnd,
    MoveStart,
    Pick,
    Ranged,
    Relation,
    RelationSet,
    SavingThrow,
    SkillCheck,
    TurnEnd,
    TurnStart,
    When,
    ZoneEntered,
    about_me,
    both,
    by_charge,
    by_keyword,
    by_me,
    by_melee,
    either,
    get,
    leaves_me_out,
    my_check,
    not_me,
    power,
    targets_me,
)
from combat_engine.engine.query import allies, distance_between, flanked_by
from combat_engine.engine.triggers import Trigger

DEFENCES = (AC, FORT, REF, WILL)

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

#: The three kinds of movement somebody else makes you do. "Moves
#: willingly" is every other kind.
_FORCED = ("push", "pull", "slide")

_BINDING = (
    Condition.RESTRAINED,
    Condition.IMMOBILIZED,
    Condition.SLOWED,
)


def _best(c: Cast) -> int:
    """"Highest ability modifier" as a finished attack bonus.

    Each of the six carries the same half level, proficiency and
    enhancement, so the largest is the largest modifier and nothing else.
    """
    return max(c.str_, c.con_, c.dex_, c.int_, c.wis_, c.cha_)


def _best_mod(c: Cast) -> int:
    """The same question for a damage line: the bare modifier."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


# -- predicates the printed Trigger lines need ------------------------------


def _willingly(world: Any, me: int, ev: Any) -> bool:
    """"Moves willingly" -- not shoved. Both move events carry `kind_`."""
    return ev.kind_ not in _FORCED


def _with_advantage(world: Any, me: int, ev: Any) -> bool:
    """"Hits a creature granting combat advantage to you."

    The live `AttackResult` rides on the `Hit` as a plain attribute;
    asking the board again is too late, a one-shot grant is already spent.
    """
    result = getattr(ev, "result", None)
    return bool(result is not None and result.advantage)


def _flanking_me(world: Any, me: int, ev: Any) -> bool:
    """"An enemy moves to a square to flank you." Asked at `MoveEnd`,
    because the flank exists only once the creature has arrived."""
    return flanked_by(world, me, ev.actor)


def _binds_me(world: Any, me: int, ev: Any) -> bool:
    """One of the four conditions an escape or a save can shake off.

    `ConditionApplied` names its subject `target`, so this reads that and
    not `ev.actor` -- `about_me` is false here forever.
    """
    return ev.target == me and ev.condition in _BINDING


def _grabbed_me(world: Any, me: int, ev: Any) -> bool:
    """"You are grabbed." `c.grab` sets a relation with the holder as the
    source and the held creature as the target, and announces no
    condition at all."""
    return ev.kind_ is Relation.GRABBED_BY and ev.target == me


def _vs_my_will(world: Any, me: int, ev: Any) -> bool:
    """"An enemy hits your Will." `vs` is a plain attribute on the hit."""
    return ev.target == me and getattr(ev, "vs", None) is Defense.WILL


def _hurt_while_bloodied(world: Any, me: int, ev: Any) -> bool:
    """The second half of "bloodied by an attack, or damaged while bloodied"."""
    from combat_engine.engine.components import Health

    health = world.get(me, Health)
    return ev.target == me and health is not None and health.bloodied


def _ally_within(squares: int) -> Any:
    """The event's **target** is an ally of mine, that close.

    `ally_within` reads the actor, which on an attack event is whoever
    swung; these two rows are about who was swung at. `query.team` answers
    which side a creature is on and not who is on it, so the membership
    question is `query.allies`, which already leaves the caster out.
    """

    def check(world: Any, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who not in allies(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def _my_mount_hurt(world: Any, me: int, ev: Any) -> bool:
    """"A mount you are riding is damaged." A probe `Cast` answers the
    relation, the way `Attack.bonus_for` builds one to answer a bonus."""
    from combat_engine.engine.cast import Cast as _Cast

    return ev.target == _Cast(world=world, me=me, ref="").mount()


# ===========================================================================
# x7_655 -- a melee line that shoves and slows
# ===========================================================================



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
    "p11868",
    level=0,
    cls="x7_655",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11868(c: Cast) -> None:
    """The second slow is measured after the shove, which is what "adjacent
    to the target at the end of the push" says."""
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.push(2)
        c.slowed()
        for foe in c.within(1, of=c.target, side="enemy"):
            c.slowed(on=foe)


@power(
    "p11869",
    level=2,
    cls="x7_655",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy within 5 squares of you that you can see moves willingly",
    on=Trigger(
        MoveEnd,
        both(not_me, _willingly),
        "an enemy within 5 squares of you moves willingly",
    ),
)
def p11869(c: Cast) -> None:
    """A reaction answers a move that has happened, so `MoveEnd`."""
    foe = c.trigger.actor
    c.shift(max(1, c.speed_of(c.me) // 2))
    c.grants_advantage(on=foe)


@power(
    "p11870",
    level=3,
    cls="x7_655",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11870(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.attack_mod)
        c.penalty("attack", 2)


@power(
    "p11871",
    level=5,
    cls="x7_655",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p11871(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.attack_mod)
        c.grants_advantage(until=When.ENCOUNTER)


@power(
    "p12234",
    level=6,
    cls="x7_655",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you bloody an enemy or reduce an enemy to 0 hit points with a melee attack",
    on=(
        Trigger(Bloodied, by_me, "you bloody an enemy"),
        Trigger(Dropped, by_me, "you reduce an enemy to 0 hit points"),
    ),
    dropped=("Dropped.power",),
)
def p12234(c: Cast) -> None:
    """`Dropped` names who felled the creature and not what with, so the
    "with a melee attack" half of the trigger cannot be asked; `by_melee`
    on it reads a power field the event has not got and is false forever."""
    for foe in c.within(10, side="enemy"):
        if c.can_see(foe):
            c.grants_advantage(on=foe)


@power(
    "p12235",
    level=7,
    cls="x7_655",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p12235(c: Cast) -> None:
    """The Effect line stands whether or not the attack landed."""
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
    victim = c.target
    mod = c.attack_mod

    def sting(ev: TurnStart) -> None:
        if victim is not None and ev.actor in c.enemies() and c.adjacent_to(victim, ev.actor):
            c.flat(mod, on=ev.actor)

    c.watch(TurnStart, sting, until=When.EONT, on=c.me)


@power(
    "p12236",
    level=9,
    cls="x7_655",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*MARTIAL_WEAPON, Keyword.STANCE],
    attack=Attack(Pick.PRIMARY, vs=AC),
    dropped=("c.move_before_targeting()",),
)
def p12236(c: Cast) -> None:
    """The printed "before the attack, you move your speed" cannot be said:
    a burst picks its targets before the body runs, so a move taken here
    would attack whoever was adjacent before it. The punishment for
    opportunity attacks made during that move goes with it."""
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
    if not c.first:
        return
    c.stance()
    mod = c.attack_mod

    def grind(ev: TurnStart) -> None:
        if ev.actor in c.enemies() and c.adjacent(ev.actor):
            c.flat(mod, on=ev.actor)
            c.cannot_shift(on=ev.actor)

    c.watch(TurnStart, grind, until=When.STANCE, on=c.me)


@power(
    "p12237",
    level=10,
    cls="x7_655",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy you can see misses with a melee attack",
    on=Trigger(Miss, both(not_me, by_melee), "an enemy misses with a melee attack"),
)
def p12237(c: Cast) -> None:
    """The Special is the other half of the same sentence: one watch on a
    miss of mine against the same creature hands the use back."""
    foe = c.trigger.attacker
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.EONT, once=True,
        when=lambda ctx: ctx["target"] == foe and not ctx["ranged"],
    )
    c.bonus(
        "damage", 0, dice=c.w(), on=c.me, until=When.EONT, once=True,
        when=lambda ctx: ctx["target"] == foe and not ctx["ranged"],
    )

    def refund(ev: Miss) -> None:
        if ev.attacker == c.me and ev.target == foe:
            c.restore_use(c.ref)

    c.watch(Miss, refund, until=When.EONT, on=c.me, once=True)


# ===========================================================================
# x7_768 -- Bluff against passive Insight, and a flanker's answer
# ===========================================================================


@power(
    "p13431",
    level=0,
    cls="x7_768",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you make an attack",
    on=Trigger(AttackDeclared, by_me, "you make an attack"),
)
def p13431(c: Cast) -> None:
    """One Bluff roll, compared against each watcher's own passive Insight,
    so a sharp creature sees through what a dull one does not."""
    rolled = c.check("bluff")
    for foe in c.enemies():
        if rolled.total > c.passive("insight", of=foe):
            c.invisible(to=foe, on=c.me, until=When.SONT)


@power(
    "p13432",
    level=2,
    cls="x7_768",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are affected by a grabbed, restrained, immobilized or slowed condition",
    on=(
        Trigger(ConditionApplied, _binds_me, "you are restrained, immobilized or slowed"),
        Trigger(RelationSet, _grabbed_me, "you are grabbed"),
    ),
)
def p13432(c: Cast) -> None:
    """"As appropriate" is which of the two the condition answers to: a
    grab is escaped, the other three are saved against.

    A grab is a relation, and `_BINDING` leaves `GRABBED` out of the
    `ConditionApplied` half on purpose. That used to be a necessity -- the
    relation announced no condition, so watching for `Condition.GRABBED`
    was false forever -- and is now a **guard**: relation-imposed conditions
    do announce themselves, so listing it in both halves would arm this one
    reaction twice on a single grab. `RelationSet` stays the half that
    answers for the grab, because it is the one that also names who did it.
    """
    if c.is_(Condition.GRABBED, on=c.me):
        c.escape(on=c.me, bonus=2)
    else:
        c.save(on=c.me, bonus=2)


@power(
    "p13433",
    level=3,
    cls="x7_768",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
    trigger="an enemy moves to a square to flank you",
    on=Trigger(MoveEnd, _flanking_me, "an enemy moves to a square to flank you"),
)
def p13433(c: Cast) -> None:
    """"Each flanking enemy" narrows the burst, so `query.flanked_by` is
    asked again per target rather than trusted from the trigger."""
    if c.first:
        c.cannot_be_flanked(on=c.me, until=When.EONT)
    if c.target is None or not flanked_by(c.world, c.me, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.push(1)


@power(
    "p13434",
    level=5,
    cls="x7_768",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
    trigger="an enemy makes a melee attack against you",
    on=Trigger(
        AttackDeclared, both(targets_me, by_melee), "an enemy makes a melee attack against you"
    ),
)
def p13434(c: Cast) -> None:
    """The row aims itself off its own trigger, so it declares no target
    line: an interrupt's `ev.targets` would name nobody it touched."""
    foe = c.trigger.attacker
    vacated = c.here
    if c.is_(Condition.PRONE, on=c.me):
        c.cure(Condition.PRONE, on=c.me)
    c.shift(1)
    c.pull(1, on=foe, to=vacated)
    c.prone(on=foe)
    if c.strike(on=foe):
        c.damage(c.w(2), c.attack_mod, on=foe)
        for defence in DEFENCES:
            c.bonus(defence, 2, on=c.me, until=When.EOT, when=lambda ctx: ctx["attacker"] == foe)
    else:
        c.half_damage(c.w(2), c.attack_mod, on=foe)


@power(
    "p13435",
    level=6,
    cls="x7_768",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p13435(c: Cast) -> None:
    """"The first time on its turn" is per approaching creature's turn, so
    the guard is the turn number and not a plain `once`."""
    c.stance()
    c.bonus(AC, 1, kind="power", on=c.me, until=When.STANCE)
    spent: list[int | None] = []

    def sidestep(ev: AdjacencyGained) -> None:
        if ev.actor != c.me or ev.mover == c.me:
            return
        turn = c.turn_of()
        if turn in spent:
            return
        spent.append(turn)
        c.shift(1)

    c.watch(AdjacencyGained, sidestep, until=When.STANCE, on=c.me)


@power(
    "p13436",
    level=7,
    cls="x7_768",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=AC),
)
def p13436(c: Cast) -> None:
    """The immobilise asks the attack that was actually rolled, not the
    board: a one-shot grant is spent by the time `c.strike` returns."""
    if c.check("bluff").total > c.passive("insight", of=c.target):
        c.grants_advantage(once=True)
    result = c.strike()
    if result:
        c.damage(c.w(2), c.attack_mod)
        if result.advantage:
            c.immobilized()


@power(
    "p13437",
    level=9,
    cls="x7_768",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(Pick.PRIMARY, vs=FORT),
    dropped=("Target.max_size(relative=)",),
)
def p13437(c: Cast) -> None:
    """The printed size line is relative to the caster and `Target.max_size`
    is an absolute size, so the restriction is dropped. The positional
    exchange is armed rather than offered: it is an interrupt on an attack
    aimed at me while the hold stands."""
    landed = c.strike()
    c.damage(c.w(), c.attack_mod)
    if not landed:
        return
    foe = c.target
    c.grab()
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)

    def trade(ev: AttackDeclared) -> None:
        if foe is None or not c.swap(foe):
            return
        c.redirect(to=foe)
        c.escape(on=foe, auto=True)
        c.cure(Condition.DOMINATED, on=foe)

    c.arm_trigger(
        AttackDeclared, trade, when=lambda ev: ev.target == c.me,
        cost=ActionType.IMMEDIATE_INTERRUPT, until=When.SAVE_ENDS, on=c.me,
    )


@power(
    "p13438",
    level=10,
    cls="x7_768",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p13438(c: Cast) -> None:
    rolled = c.check("bluff")
    for foe in c.enemies():
        if rolled.total > c.passive("insight", of=foe):
            c.no_provoke(from_=foe, on=c.me, until=When.EONT)


# ===========================================================================
# x7_851 -- arcane, and three utilities about other powers
# ===========================================================================


@power(
    "p14123",
    level=0,
    cls="x7_851",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.FIRE, Keyword.ZONE],
)
def p14123(c: Cast) -> None:
    """No header attack line: "highest ability modifier" is the largest of
    six finished bonuses and only the body can work it out."""
    if c.attack(_best(c), REF):
        c.damage("1d10", _best_mod(c), dtype=DamageType.FIRE)
    if c.first:
        c.hazard(c.area(), 5, DamageType.FIRE, until=When.SONT, sustain=None)


@power(
    "p14124",
    level=2,
    cls="x7_851",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    todo=("c.sustain(ref)",),
)
def p14124(c: Cast) -> None:
    """Sustaining somebody's standing effect out of turn has no verb --
    `c.on_sustain` is the payout half and cannot start one."""


@power(
    "p14125",
    level=6,
    cls="x7_851",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you use a ranged or area arcane attack power",
    on=Trigger(
        AttackDeclared, by_me, "you use a ranged or area arcane attack power"
    ),
    todo=("c.reach_of(power=)",),
)
def p14125(c: Cast) -> None:
    """Nothing rewrites another row's range, and targeting is already done
    by the time this could fire -- which is the same wall the header-side
    augments hit."""


@power(
    "p14126",
    level=10,
    cls="x7_851",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p14126(c: Cast) -> None:
    """The Requirement is the natural shape of the body: with nothing
    expended there is nothing to hand back."""
    lowest = ""
    for ref in c.expended(on=c.me):
        row = get(ref)
        if row is None or row.usage is not ENCOUNTER or not row.is_attack:
            continue
        if Keyword.ARCANE not in row.keywords:
            continue
        best = get(lowest)
        if best is None or row.level < best.level:
            lowest = ref
    if lowest:
        c.restore_use(lowest)


# ===========================================================================
# x7_856 -- riding
# ===========================================================================


@power(
    "p14145",
    level=0,
    cls="x7_856",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you hit a creature with a charge attack",
    on=Trigger(Hit, both(by_me, by_charge), "you hit a creature with a charge attack"),
)
def p14145(c: Cast) -> None:
    c.immobilized(on=c.trigger.target, until=When.EOTNT)


@power(
    "p14146",
    level=2,
    cls="x7_856",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="a mount you are riding is damaged by an attack",
    on=Trigger(DamageRolled, _my_mount_hurt, "a mount you are riding is damaged"),
)
def p14146(c: Cast) -> None:
    """An interrupt catches the blow before it lands, so the halving is
    `c.halve` on the triggering roll; the shift waits for the turn's end of
    the exchange and is taken straight after."""
    mount = c.mount()
    c.halve()
    if mount is not None:
        c.shift(1, who=mount)


@power(
    "p14147",
    level=6,
    cls="x7_856",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p14147(c: Cast) -> None:
    """"Hit points equal to your healing surge value" is not a surge spent,
    so this heals the number rather than calling `c.surge`."""
    c.heal(c.surge_value(), on=c.me)
    c.save(on=c.me)


@power(
    "p14148",
    level=10,
    cls="x7_856",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    dropped=("c.resist_forced(zone=)",),
)
def p14148(c: Cast) -> None:
    """`c.grants_in` carries a modifier for as long as you stand in a zone;
    shortening a shove is `c.resist_forced`, which has no zone form, so the
    second clause is the dropped one."""
    zone = c.aura(1, until=When.EONT)
    c.grants_in(zone, AC, 2, side="team", kind="power")


# ===========================================================================
# x7_865 -- standing in front of somebody
# ===========================================================================


@power(
    "p14180",
    level=0,
    cls="x7_865",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p14180(c: Cast) -> None:
    for defence in DEFENCES:
        c.bonus(defence, 2, kind="power", until=When.SONT)
    c.temp_hp(5)


@power(
    "p14181",
    level=2,
    cls="x7_865",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14181(c: Cast) -> None:
    """"Enemies take a -2 penalty to attack rolls **against any creature other
    than you**", which is the whole point of the aura: it herds attacks onto the
    caster rather than suppressing them.

    As written it bit on every attack from inside, including attacks on the
    caster -- **stronger than the card**, and in the direction that makes the
    row do the opposite of what it is for. `c.grants_in(when=)` takes the gate
    now and `ctx["target"]` is who the attack is aimed at."""
    zone = c.aura(2, until=When.EONT)
    me = c.me
    c.grants_in(zone, "attack", -2, side="enemy", kind="power",
                when=lambda ctx: ctx.get("target") != me)


@power(
    "p14182",
    level=6,
    cls="x7_865",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally within 3 squares of you is attacked and you are not included",
    on=Trigger(
        AttackDeclared,
        both(_ally_within(3), leaves_me_out),
        "an ally within 3 squares is attacked and you are left out",
    ),
)
def p14182(c: Cast) -> None:
    """Swapping is one move for both, so `c.swap` rather than two shifts --
    and it announces the movement, which two `c.shift` calls to occupied
    squares could not do at all."""
    mate = c.trigger.target
    if c.swap(mate):
        c.redirect(to=c.me)


@power(
    "p14183",
    level=10,
    cls="x7_865",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    narrative=("skill:diplomacy",),
)
def p14183(c: Cast) -> None:
    """The Diplomacy half is the narrative one: no board rolls Diplomacy to
    decide anything, so the bonus has nowhere to go and nothing is missing.
    Everything else is re-laid on each sustain, which is what the printed
    "the effect persists" means."""

    def lay() -> None:
        for defence in DEFENCES:
            c.bonus(defence, 2, kind="power", on=c.me, until=When.EONT)
        c.bonus("save", 2, kind="power", on=c.me, until=When.EONT)
        c.immobilized(on=c.me, until=When.EONT)

    def punish(ev: AttackDeclared) -> None:
        if ev.target == c.me:
            c.grants_advantage(on=ev.attacker, to="team", until=When.EOTNT)

    lay()
    c.watch(AttackDeclared, punish, until=When.SUSTAIN, on=c.me)
    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR), lay)


# ===========================================================================
# x7_897 -- reading a creature, and stepping out of the way
# ===========================================================================


@power(
    "p14374",
    level=0,
    cls="x7_897",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="your melee attack hits a creature granting combat advantage to you",
    on=Trigger(
        Hit,
        both(by_me, both(by_melee, _with_advantage)),
        "your melee attack hits a creature granting combat advantage to you",
    ),
)
def p14374(c: Cast) -> None:
    c.dazed(on=c.trigger.target)


@power(
    "p14376",
    level=2,
    cls="x7_897",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p14376(c: Cast) -> None:
    """The whole Effect is being told numbers the engine already knows and
    the player can already see. Nothing on the board changes."""


@power(
    "p14377",
    level=6,
    cls="x7_897",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you hit with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def p14377(c: Cast) -> None:
    """"Partial concealment" is `c.conceal` without `total`, which is the
    -2 rather than the -5."""
    victim = c.trigger.target
    c.shift(max(1, c.speed_of(c.me) // 2))
    if c.within(1, side="any") and not c.adjacent(victim):
        c.conceal(on=c.me, until=When.EONT)


@power(
    "p14378",
    level=10,
    cls="x7_897",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an enemy hits your adjacent ally with a melee or ranged attack",
    on=Trigger(
        Hit,
        both(not_me, _ally_within(1)),
        "an enemy hits an adjacent ally of yours",
    ),
)
def p14378(c: Cast) -> None:
    """On a `Hit` the roll is not made again: `c.redirect` moves the live
    result with the event so the damage follows it."""
    mate = c.trigger.target
    c.redirect(to=c.me)
    c.temp_hp(2 + c.level // 2, on=mate)


# ===========================================================================
# x7_935 -- the first round, and refusing to fall over
# ===========================================================================


@power(
    "p16000",
    level=0,
    cls="x7_935",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
    dropped=("c.draw()", "query.initiative_of()"),
)
def p16000(c: Cast) -> None:
    """Drawing a weapon is not modelled, and the second paragraph wants to
    compare my initiative against every enemy's, which nothing exposes --
    so the wider crit range goes with it."""
    c.shift(max(1, c.speed_of(c.me) // 2))
    for foe in c.within(1, side="enemy"):
        c.bonus(
            "attack", 2, kind="power", on=c.me, until=When.EONT, once=True,
            when=lambda ctx, f=foe: ctx["target"] == f,
        )


@power(
    "p16001",
    level=2,
    cls="x7_935",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are bloodied by an attack, or damaged by an attack while bloodied",
    on=(
        Trigger(Bloodied, about_me, "you are bloodied by an attack"),
        Trigger(DamageApplied, _hurt_while_bloodied, "you are damaged while bloodied"),
    ),
    dropped=("SavingThrow.effect", "c.appears_unbloodied()"),
)
def p16001(c: Cast) -> None:
    """The save bonus is laid whole: a saving throw's context carries the
    effect's label and no keyword, so "against charm and fear effects"
    cannot be narrowed. Nothing hides a creature's bloodied state either."""
    c.second_wind(on=c.me, cost=ActionType.FREE)
    c.bonus("save", 5, kind="power", on=c.me, until=When.ENCOUNTER)


@power(
    "p16002",
    level=6,
    cls="x7_935",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger="an enemy within 3 squares of you moves willingly",
    on=Trigger(
        MoveStart,
        both(not_me, _willingly),
        "an enemy within 3 squares of you moves willingly",
    ),
)
def p16002(c: Cast) -> None:
    """An interrupt has to catch the creature where it started, so
    `MoveStart`: by `MoveEnd` it is out of the burst."""
    foe = c.trigger.actor
    if c.distance(foe) > 3:
        return
    c.mark(on=foe, until=When.EONT)
    c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p16003",
    level=10,
    cls="x7_935",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p16003(c: Cast) -> None:
    """`c.enhancement` is the plus on whatever this row counts as holding,
    which for a weapon-holding Requirement is the melee weapon."""
    c.save(on=c.me)
    plus = c.enhancement
    for defence in (FORT, REF, WILL):
        c.bonus(defence, plus, kind="power", on=c.me, until=When.EONT)


# ===========================================================================
# x7_946 -- fire, and two cards printed as a pair with one ref
# ===========================================================================


@power(
    "p16069",
    level=0,
    cls="x7_946",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
)
def p16069(c: Cast) -> None:
    """The second block the entry prints -- a ranged attack that requires
    this aura -- is `p16069b` now and declared below, so the aura hands it
    over. It had no ref until `parse_extra` was called for theme powers."""
    c.aura(1, until=When.EONT)
    c.grant_row("p16069b", on=c.me, until=When.EONT)
    mod = _best_mod(c)

    def scorch(ev: TurnStart) -> None:
        if c.in_my_aura(ev.actor, label=c.ref):
            c.flat(mod, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, scorch, until=When.EONT, on=c.me)


@power(
    "p16070b",
    level=3,
    cls="x7_946",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
    attack=Attack(Pick.HIGHEST, plus=2, vs=REF),
    requires=lambda world, eid: any(
        e.label.startswith("p16070") for e in world.effects.of(eid)
    ),
    requires_text="the p16070 flame must be active",
)
def p16070b(c: Cast) -> None:
    """The attack the flame exists for -- the second card in p16070's entry.

    "You gain a +2 bonus to the attack roll" is printed on the line itself,
    so it is `plus=2` in the header rather than a modifier laid at use.

    Using it is one of the three things that ends the flame, which is why the
    flame is ended here and not only by its own duration.
    """
    for held in list(c.world.effects.of(c.me)):
        if held.label.startswith("p16070"):
            c.end_effect(held, why="spent on the secondary power")
    if c.strike():
        c.damage("2d8", c.mod(c.ability_for()), dtype=DamageType.FIRE)


@power(
    "p16069b",
    level=0,
    cls="x7_946",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
    attack=Attack(Pick.HIGHEST, plus=2, vs=REF),
    requires=lambda world, eid: any(
        e.label.startswith("p16069") for e in world.effects.of(eid)
    ),
    requires_text="the p16069 aura must be active",
)
def p16069b(c: Cast) -> None:
    """The ranged attack the aura unlocks -- the second card in p16069's own
    entry, which had no ref until `parse_extra` ran for theme powers."""
    if c.strike():
        c.damage("1d8", dtype=DamageType.FIRE)


@power(
    "p16070",
    level=3,
    cls="x7_946",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
    dropped=("c.light()",),
)
def p16070(c: Cast) -> None:
    """The flame, what ends it, and the attack it exists for.

    `todo` before, because both halves were absent -- the secondary attack is
    a second block the entry gave no ref, and it is `p16070b` below now. So
    the row plays and one clause is missing, which is `dropped`.

    **The missing clause is the light itself, and `c.light()` is deliberately
    not written.** Nothing in this engine models darkness -- there is
    line-of-sight and a `sight_range` cap and no light levels -- so a verb
    recording "bright light out to 10 squares" would be a modifier nothing
    consults, which is the commonest bug in this component. `narrative=`
    would be the right marker for a clause with no combat meaning and its
    vocabulary is `skill:<name>` only, so `dropped=` is the honest one.

    Three ways out, and the third is the card's own: the encounter ends it,
    a minor action dismisses it, or using the secondary power consumes it.
    """
    flame = c.form(until=When.ENCOUNTER, revert=None, label=c.ref)
    if flame is not None:
        c.endable(flame, MINOR)
    c.grant_row("p16070b", on=c.me, until=When.ENCOUNTER)


@power(
    "p16073",
    level=7,
    cls="x7_946",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
)
def p16073(c: Cast) -> None:
    """The printed Effect is one bonus spent on any of three rolls; the
    third is a skill or ability check with no named skill, so the choice
    offered is between the two a board rolls."""
    if c.attack(_best(c) + 2, REF):
        c.damage("2d6", _best_mod(c), dtype=DamageType.FIRE)
    if not c.first:
        return
    for mate in c.in_squares(c.area(), side="ally"):
        picked = c.choose(["attack", "save"], "which roll the bonus is kept for")
        c.bonus(picked, 2, kind="power", on=mate, until=When.SONT, once=True)


@power(
    "p16076",
    level=6,
    cls="x7_946",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.ELEMENTAL],
    dropped=("c.vulnerable(zone=)", "c.grants_in(when=)", "c.douse(zone=)"),
)
def p16076(c: Cast) -> None:
    """Vulnerability lives on `Defences` and not in `Mods`, so `c.grants_in`
    cannot carry it and it is laid on arrival instead -- which means it does
    not lift on the way out. The save penalty cannot be narrowed to ongoing
    fire, and nothing holds a fire open against being put out."""
    zone = c.aura(2, until=When.ENCOUNTER)
    c.grants_in(zone, "save", -2, side="enemy", kind="power")
    for foe in c.within(2, side="enemy"):
        c.vulnerable(5, DamageType.FIRE, on=foe, until=When.ENCOUNTER)

    def arriving(ev: ZoneEntered) -> None:
        if ev.zone == zone and ev.actor in c.enemies():
            c.vulnerable(5, DamageType.FIRE, on=ev.actor, until=When.ENCOUNTER)

    c.watch(ZoneEntered, arriving, until=When.ENCOUNTER, on=c.me)


# ===========================================================================
# x7_977 -- a quarry of one's own
# ===========================================================================


@power(
    "p16374",
    level=0,
    cls="x7_977",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy with an attack"),
    dropped=("c.mark(lapses=)",),
)
def p16374(c: Cast) -> None:
    """The printed mark ends when a turn of mine passes without swinging at
    the creature; no duration says that, so it is held for the encounter and
    the lapse is the dropped clause."""
    foe = c.trigger.target
    c.immobilized(on=foe, until=When.EONT)
    c.mark(on=foe, until=When.ENCOUNTER)
    c.quarry(on=foe, until=When.ENCOUNTER)


@power(
    "p16375",
    level=2,
    cls="x7_977",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
    dropped=("c.shift(toward=)",),
)
def p16375(c: Cast) -> None:
    """The free shift is printed with a leash -- it must not take you further
    from your quarry -- and `c.shift` takes a count or a square, not a
    creature to stay near."""
    c.stance()
    c.bonus("speed", 2, kind="power", on=c.me, until=When.STANCE)
    for defence in DEFENCES:
        c.bonus(
            defence, 2, kind="power", on=c.me, until=When.STANCE,
            when=lambda ctx: ctx["opportunity"],
        )

    def edge(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            c.shift(1)

    c.watch(TurnEnd, edge, until=When.STANCE, on=c.me)


@power(
    "p16376",
    level=6,
    cls="x7_977",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy with an attack"),
)
def p16376(c: Cast) -> None:
    foe = c.trigger.target
    for defence in DEFENCES:
        c.bonus(
            defence, 2, kind="power", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx["attacker"] == foe,
        )
    if c.is_quarry(on=foe):
        c.temp_hp(c.surge_value(), on=c.me)


@power(
    "p16377",
    level=10,
    cls="x7_977",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you reduce a nonminion enemy to 0 hit points",
    on=Trigger(Dropped, by_me, "you reduce an enemy to 0 hit points"),
)
def p16377(c: Cast) -> None:
    """"Nonminion" is asked in the body: `Dropped` carries who fell and
    `c.is_minion` is the only reader of what it was."""
    foe = c.trigger.actor
    if c.is_minion(on=foe):
        return
    c.surge(on=c.me)
    c.save(on=c.me)
    if c.is_quarry(on=foe):
        c.restore_use("p16374")


# ===========================================================================
# x7_987 -- psionic, three of them augmentable
# ===========================================================================


@power(
    "p16438",
    level=0,
    cls="x7_987",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    trigger="you are hit by a charm or a psychic attack",
    on=Trigger(
        Hit,
        both(targets_me, either(by_keyword(Keyword.CHARM), by_keyword(Keyword.PSYCHIC))),
        "you are hit by a charm or a psychic attack",
    ),
    dropped=("SavingThrow.effect",),
)
def p16438(c: Cast) -> None:
    """The augment moves the save to the start of the turn; which effects it
    may be spent on -- charm and psychic ones -- is what cannot be asked, so
    the extra save is offered against whatever stands."""
    c.resist(5, DamageType.PSYCHIC, until=When.EONT, on=c.me)
    c.bonus("save", 2, kind="power", on=c.me, until=When.EONT)
    if not augment(c, 1):
        return

    def early(ev: TurnStart) -> None:
        if ev.actor == c.me:
            c.save(on=c.me)

    c.watch(TurnStart, early, until=When.ENCOUNTER, on=c.me)


@power(
    "p16439",
    level=2,
    cls="x7_987",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p16439(c: Cast) -> None:
    """"While adjacent to you" is geometry rather than a clock, so the
    augmented half is an aura with `c.grants_in` and not a snapshot."""
    for defence in DEFENCES:
        c.bonus(defence, 2, kind="power", on=c.me, until=When.EONT)
    if augment(c, 1):
        zone = c.aura(1, label=f"{c.ref} augment", until=When.EONT)
        c.grants_in(zone, WILL, 1, side="ally", kind="power")


@power(
    "p16440",
    level=6,
    cls="x7_987",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    dropped=("c.regain_points()",),
)
def p16440(c: Cast) -> None:
    """Three of the four faces are sayable; handing power points back is
    not, and `c.spend_points` only takes them."""
    face = c.roll("1d4")
    if augment(c, 1):
        face = c.choose([face, c.roll("1d4")], "which of the two rolls to keep")
    if face == 1:
        c.extra_action(ActionType.MOVE, on=c.me)
    elif face == 2:
        for defence in DEFENCES:
            c.bonus(defence, 2, kind="power", on=c.me, until=When.ENCOUNTER)
    elif face == 3:
        c.forces(2, on=c.me, until=When.ENCOUNTER)


@power(
    "p16441",
    level=10,
    cls="x7_987",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
)
def p16441(c: Cast) -> None:
    """"You grant combat advantage" names no beneficiary, and the relation
    names one, so it is laid once per enemy."""
    victim = c.target

    def lay() -> None:
        for foe in c.enemies():
            c.grants_advantage(on=c.me, to=foe, until=When.EONT)
        c.vulnerable(10, DamageType.PSYCHIC, on=victim, until=When.EONT)

    lay()
    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR), lay)


# ===========================================================================
# x7_998 -- luck, and two answers to being hit
# ===========================================================================


@power(
    "p16562",
    level=0,
    cls="x7_998",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit a creature granting combat advantage to you",
    on=Trigger(
        Hit,
        both(by_me, _with_advantage),
        "you hit a creature granting combat advantage to you",
    ),
)
def p16562(c: Cast) -> None:
    """A bare `"skill"` modifier is the one `skills.check` adds to every
    skill, which is what "skill checks" with no list printed means."""
    c.flat(5, on=c.trigger.target)
    c.bonus("attack", 2, kind="power", on=c.me, until=When.EONT)
    c.bonus("skill", 2, kind="power", on=c.me, until=When.EONT)


@power(
    "p16563",
    level=2,
    cls="x7_998",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a Diplomacy or Intimidate check and dislike the result",
    on=Trigger(
        SkillCheck,
        my_check("diplomacy", "intimidate"),
        "you make a Diplomacy or an Intimidate check",
    ),
)
def p16563(c: Cast) -> None:
    """"Use either result" is `keep="best"`; the row is only ever offered
    when one of the two checks has actually been rolled."""
    c.reroll_check(keep="best", bonus=4)


@power(
    "p16564",
    level=6,
    cls="x7_998",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with an attack",
    on=Trigger(Hit, both(targets_me, not_me), "an enemy hits you with an attack"),
)
def p16564(c: Cast) -> None:
    foe = c.trigger.attacker
    for defence in DEFENCES:
        c.bonus(
            defence, 2, kind="power", on=c.me, until=When.EOTNT,
            when=lambda ctx: ctx["attacker"] == foe,
        )
    c.bonus(
        "crit_range", 1, on=c.me, until=When.EOTNT,
        when=lambda ctx: ctx["target"] == foe,
    )


@power(
    "p16565",
    level=10,
    cls="x7_998",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.FEAR],
    trigger="an enemy hits you with an attack",
    on=Trigger(Hit, both(targets_me, not_me), "an enemy hits you with an attack"),
    dropped=("c.no_recharge()",),
)
def p16565(c: Cast) -> None:
    """Three of the four clauses have verbs; holding a monster's recharge
    roll shut has none."""
    foe = c.trigger.attacker
    c.penalty("attack", 2, on=foe, until=When.EOTNT)
    c.grants_advantage(on=foe, to="team", until=When.EOTNT)
    c.no_healing(on=foe, until=When.EOTNT)


# ===========================================================================
# x7_1012 -- a shadow that reaches two squares
# ===========================================================================


@power(
    "p16626",
    level=0,
    cls="x7_1012",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW],
    dropped=("c.grab(sustain=)",),
    requires=_a_hand_free,
    requires_text="must have a hand free",
)
def p16626(c: Cast) -> None:
    """The Special is `c.as_basic`, which is what "in place of a melee basic
    attack" means everywhere else. The grab's payout is armed, but nothing
    gives a grab a sustain cost of its own."""
    if c.attack(_best(c) + 2, REF):
        c.damage("2d8", _best_mod(c))
        c.pull(1)
        held = c.grab()
        c.on_sustain(held, lambda: c.damage("2d8", _best_mod(c)))
    c.as_basic(c.ref, window="opportunity", on=c.me)


@power(
    "p16627",
    level=2,
    cls="x7_1012",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    dropped=("c.darkvision()",),
)
def p16627(c: Cast) -> None:
    """Ignoring concealment is `c.ignore_cover`, which sits on the eye and
    covers both; seeing in the dark is a sense the engine has not got."""
    c.ignore_cover(on=c.me, until=When.EONT)


@power(
    "p16628",
    level=6,
    cls="x7_1012",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.FEAR],
)
def p16628(c: Cast) -> None:
    """"Move up to its speed away from you" is `c.flee`, which is the only
    mover that takes a direction from a creature rather than a square."""
    c.bonus(AC, 2, kind="power", on=c.me, until=When.ENCOUNTER)
    c.bonus(FORT, 2, kind="power", on=c.me, until=When.ENCOUNTER)

    def recoil(ev: TurnEnd) -> None:
        if ev.actor in c.enemies() and c.adjacent(ev.actor):
            c.flee(c.speed_of(ev.actor), on=ev.actor)

    c.watch(TurnEnd, recoil, until=When.ENCOUNTER, on=c.me)


@power(
    "p16629",
    level=10,
    cls="x7_1012",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p16629(c: Cast) -> None:
    """`c.threatens(2)` is "reach 2", which is the +1 this prints."""
    c.threatens(2, on=c.me, until=When.EONT)
    c.bonus(
        "damage", 2, kind="power", on=c.me, until=When.EONT,
        when=lambda ctx: not ctx["ranged"],
    )


# ===========================================================================
# x7_849 -- an alchemy case
# ===========================================================================


@power(
    "p14095",
    level=2,
    cls="x7_849",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    out_of_combat=True,
)
def p14095(c: Cast) -> None:
    """The target is an object and the whole Effect is a bonus to a check
    made to break it open. Nothing on a board has hit points for a lock."""


@power(
    "p14096",
    level=6,
    cls="x7_849",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def p14096(c: Cast) -> None:
    """"Heavily obscured" is the zone blocking sight; the exemption from
    opportunity attacks is per creature standing in it, so it is laid
    before the move rather than after."""
    smoke = c.area()
    c.zone(smoke, blocks_sight=True, until=When.EONT)
    for foe in c.in_squares(smoke, side="enemy"):
        c.no_provoke(from_=foe, on=c.me, until=When.EONT)
    c.move(c.speed_of(c.me))


@power(
    "p14097",
    level=10,
    cls="x7_849",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def p14097(c: Cast) -> None:
    dc = 10 + c.level // 2
    spread = c.area()
    zone = c.zone(spread, difficult=True, until=When.ENCOUNTER)

    def stumble(ev: ZoneEntered) -> None:
        if ev.zone != zone or c.check("acrobatics", dc, who=ev.actor):
            return
        c.prone(on=ev.actor)
        c.vulnerable(5, DamageType.FIRE, on=ev.actor, until=When.EOTNT)

    c.watch(ZoneEntered, stumble, until=When.ENCOUNTER, on=c.me)


# ===========================================================================
# x7_898 -- an archer's footing
# ===========================================================================


@power(
    "p14379",
    level=2,
    cls="x7_898",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14379(c: Cast) -> None:
    """`c.shift_as` is a standing change to the action menu, not a shift
    taken now; the ally's copy lasts only the turn it is granted for."""
    c.aura(3, until=When.ENCOUNTER)
    c.shift_as(ActionType.MOVE, 2, on=c.me, until=When.ENCOUNTER)

    def lend(ev: TurnStart) -> None:
        if ev.actor != c.me and ev.actor in c.allies() and c.in_my_aura(ev.actor, label=c.ref):
            c.shift_as(ActionType.MOVE, 2, on=ev.actor, until=When.EOT)

    c.watch(TurnStart, lend, until=When.ENCOUNTER, on=c.me)


@power(
    "p14380",
    level=6,
    cls="x7_898",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14380(c: Cast) -> None:
    """A Perception bonus is a real modifier here -- `skills.check` reads
    `skill:perception` -- so it is laid rather than called narrative."""
    c.bonus("skill:perception", 5, kind="power", on=c.me, until=When.EONT)
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.EONT,
        when=lambda ctx: ctx["ranged"],
    )
    c.ignores_long_range(on=c.me, until=When.EONT)
    c.ignore_cover(on=c.me, until=When.EONT, partial=True)


@power(
    "p14381",
    level=10,
    cls="x7_898",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14381(c: Cast) -> None:
    """`c.no_provoke` with no `from_` is immunity from everybody, which is
    what the bare printed line says."""
    c.ignores_difficult(on=c.me, until=When.EONT)
    c.no_provoke(on=c.me, until=When.EONT)


# ===========================================================================
# x7_1009 -- shaking things off
# ===========================================================================


@power(
    "p16616",
    level=2,
    cls="x7_1009",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits your Will with an attack",
    on=Trigger(Hit, _vs_my_will, "an enemy hits your Will with an attack"),
)
def p16616(c: Cast) -> None:
    """"One effect imposed by the triggering attack" is `against=`, which
    matches an effect's label -- and a label is the ref of whatever laid
    it, which is exactly what the hit carries."""
    c.save(on=c.me, against=c.trigger.power)


@power(
    "p16617",
    level=6,
    cls="x7_1009",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16617(c: Cast) -> None:
    """The stance ends on its own terms, so the watch ends the effect the
    stance is rather than waiting for another one to replace it."""
    held = c.stance()
    c.bonus("speed", 1, kind="power", on=c.me, until=When.STANCE)
    c.bonus("save", 1, kind="power", on=c.me, until=When.STANCE)

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            c.end_effect(held, why="spent an action point")

    c.watch(ActionPointSpent, spent, until=When.STANCE, on=c.me)


@power(
    "p16618",
    level=10,
    cls="x7_1009",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16618(c: Cast) -> None:
    """The end-of-turn save is the ordinary one and needs nothing said; the
    printed "you can still" only means the extra save does not replace it."""
    c.stance()

    def early(ev: TurnStart) -> None:
        if ev.actor == c.me:
            c.save(on=c.me)

    def rally(ev: SavingThrow) -> None:
        if ev.actor == c.me and ev.saved:
            c.temp_hp(5, on=c.me)

    c.watch(TurnStart, early, until=When.STANCE, on=c.me)
    c.watch(SavingThrow, rally, until=When.STANCE, on=c.me)
