"""Fourteen themes, level 0 to 10.

Three things recur across the batch and are worth reading once.

**"Primary ability vs. Will."** A theme does not know which class took it,
so five of the `x7_664` rows print an attack line that names no ability.
`Attack` takes one named ability or a printed number and refuses to be
built with neither, so each of those rows names one and carries
`c.ability_for(ref)` -- the symbol nineteen warlock and ranger rows
already wait on for the same reason. "Highest ability modifier" is a
different sentence and is not a gap: `_best` computes it and the roll
carries the difference as `plus=`, which is the house answer.

**"The next ally who hits and damages the target."** Eight `x7_664` rows
end on it. `_next_ally` is the one watcher, on `DamageApplied` rather
than `Hit` because the printed line wants both and damage is the later of
the two.

**Zones that only hold some of who is in them.** `Cast._while_inside` is
private and holds one effect chosen by a side word; three rows here hand
out several at once and pick by what the creature *is* -- its origin, or
whether it is an enemy. `_while_in` is that, and it ends what it gave
when the creature leaves.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    INTERRUPT,
    MELEE,
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
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Dropped,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    MoveStart,
    Pick,
    Position,
    Powers,
    PowerUsed,
    Ranged,
    SavingThrow,
    Size,
    SkillCheck,
    Square,
    Stats,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    Window,
    ZoneEntered,
    ZoneExited,
    about_me,
    ally_within,
    both,
    by_me,
    by_melee,
    check_succeeded,
    distance,
    enemy_target_within,
    enemy_within,
    get,
    my_check,
    power,
    query,
    spread,
    targets_me,
)
from combat_engine.engine.movement import walk
from combat_engine.engine.skills import SKILLS

# -- the themes, by alias ref ------------------------------------------------

X7_664 = "x7_664"
X7_917 = "x7_917"
X7_866 = "x7_866"
X7_854 = "x7_854"
X7_863 = "x7_863"
X7_886 = "x7_886"
X7_926 = "x7_926"
X7_944 = "x7_944"
X7_973 = "x7_973"
X7_985 = "x7_985"
X7_993 = "x7_993"
X7_1006 = "x7_1006"
X7_1021 = "x7_1021"
X7_939 = "x7_939"

ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.RADIANT,
    DamageType.THUNDER,
)
ORIGINS = ("aberrant", "fey", "elemental", "immortal", "natural", "shadow")
DEFENCES = (AC, FORT, REF, WILL)

#: "Each ally in the burst", which leaves the caster out. `EACH_ALLY` is
#: `side="ally"`, and a `Target`'s "ally" pool puts the actor back in -- the
#: word does not mean here what it means on `c.within`.
EACH_OTHER_ALLY = Target(side="other_ally", count=99, everyone=True)


# -- the vocabulary this file needs ------------------------------------------


def _best(c: Cast) -> int:
    """"Your highest ability modifier". The header names one ability, so the
    roll carries the difference as `plus=` and the damage line reads this."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _mod_of(c: Cast, ref: str) -> int:
    """"The ability modifier used in the triggering attack", read off the row
    that rolled it. A monster's line names no ability and answers 0."""
    row = get(ref) if ref else None
    ability = getattr(getattr(row, "attack", None), "ability", None)
    if ability is None:
        return 0
    stats = c.world.get(c.me, Stats)
    return stats.mod(ability) if stats is not None else 0


def _next_ally(
    c: Cast,
    hits: Callable[[int], bool],
    reward: Callable[[int], None],
    *,
    until: When = When.EONT,
) -> None:
    """"The next ally who hits and damages the target gains ..."

    Watched on `DamageApplied`: the printed line asks for both halves and
    the damage is the later of the two, so one watcher says it. It spends
    itself on the first ally it credits, which is what "the next" means.
    """
    spent = [False]

    def landed(ev: DamageApplied) -> None:
        if spent[0] or ev.amount <= 0 or ev.source == c.me:
            return
        if ev.source not in c.allies() or not hits(ev.target):
            return
        spent[0] = True
        reward(ev.source)

    c.watch(DamageApplied, landed, until=until)


def _while_in(
    c: Cast, zone: int, give: Callable[[int], list[Any]]
) -> None:
    """Hold things on whoever stands in a zone and take them back on the way
    out. `Cast._while_inside` is private, holds a single effect and picks by
    a side word; these rows hand out several and pick by what the creature
    is."""
    held: dict[int, list[Any]] = {}

    def arrive(who: int) -> None:
        if who in held:
            return
        got = [eff for eff in give(who) if eff is not None]
        if got:
            held[who] = got

    def leave(who: int) -> None:
        for eff in held.pop(who, []):
            c.world.effects.end(eff, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            arrive(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            leave(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)
    c.watch(ZoneExited, exited, until=When.ENCOUNTER)
    for who in c.world.zones.occupants(zone):
        arrive(who)


def _zone_effect(c: Cast, zone: int) -> Any:
    """The effect a zone's duration lives on, which is what `c.on_sustain`
    needs and what `c.aura` -- which hands back an id -- does not give."""
    standing = dict(c.world.zones.all()).get(zone)
    return getattr(standing, "effect", None)


def _free_beside(c: Cast, who: int) -> Square | None:
    """An unoccupied square next to a creature, for a move that names its
    destination rather than leaving it to the decider."""
    pos = c.world.get(who, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq != pos.square and not c.in_squares([sq]):
            return sq
    return None


def _beside_enemy(c: Cast, sq: Square) -> bool:
    return any(
        (pos := c.world.get(foe, Position)) is not None
        and distance(sq, pos.square) == 1
        for foe in c.enemies()
    )


def _step_beside_enemy(c: Cast, squares_: int) -> bool:
    """"Shift up to N squares to a square adjacent to an enemy." The
    destination is constrained, so the reachable set is filtered before the
    decider ever sees it."""
    good = [sq for sq in c.world.reachable_squares(c.me, squares_) if _beside_enemy(c, sq)]
    if not good:
        return False
    dest = c.world.decide(c.me, "shift", sorted(good), f"{c.ref}: shift {squares_}")
    return c.shift(squares_, to=dest)


def _walk_beside_enemy(c: Cast, who: int) -> bool:
    """"Move your speed, as long as the movement ends adjacent to an enemy."
    Same filter, one step lower: a walk keeps its path, so the paths are
    filtered by where they end."""
    paths = c.world.reachable_paths(who, c.speed_of(who))
    good = {sq: path for sq, path in paths.items() if _beside_enemy(c, sq)}
    if not good:
        return False
    dest = c.world.decide(who, "move", sorted(good), f"{c.ref}: move")
    walk(c.world, who, good[dest])
    return True


def _auto_save(c: Cast, who: int) -> None:
    """"Automatically succeeds on any one saving throw."

    `SavingThrow` is announced before it is acted on and `saved` is read
    back afterwards -- the door `c.reroll_save` goes through -- so setting
    it in the before window is the printed line. A bonus large enough to be
    certain would be a different rule wearing its clothes.
    """
    spent = [False]

    def pass_it(ev: SavingThrow) -> None:
        if spent[0] or ev.actor != who:
            return
        spent[0] = True
        ev.saved = True

    c.watch(SavingThrow, pass_it, until=When.EOTNT, window=Window.BEFORE, on=who)


def _on_the_ground(world: Any, eid: int) -> bool:
    """"Requirement: You must be on the ground."" """
    return not query.moving_as(world, eid, "fly")


def _adjacent_attacker(world: Any, me: int, ev: Any) -> bool:
    """"An adjacent creature makes an attack roll against you" -- any
    creature, so `enemy_within` is the wrong side of the question."""
    who = getattr(ev, "attacker", None)
    return who is not None and who != me and query.distance_between(world, me, who) <= 1


def _with_advantage(world: Any, me: int, ev: Any) -> bool:
    """"An enemy attacks you while it has combat advantage against you."

    Asked of the board at the interrupt window rather than off the event:
    `AttackDeclared` carries no `advantage` -- only `AttackRolled` does --
    and by the time it did the grant might already be spent."""
    who = getattr(ev, "attacker", None)
    return who is not None and query.has_combat_advantage(world, who, me)


def _self_moving(world: Any, me: int, ev: Any) -> bool:
    """A move the creature made, not one done to it."""
    return getattr(ev, "kind_", "") in ("walk", "shift", "run", "teleport")


def _at_will_and_bloodied(world: Any, me: int, ev: Any) -> bool:
    row = get(getattr(ev, "power", "") or "")
    if row is None or row.usage is not Usage.AT_WILL or row.attack is None:
        return False
    return query.is_(world, me, Condition.DYING) is False and _bloodied(world, me)


def _bloodied(world: Any, eid: int) -> bool:
    from combat_engine.engine import Health

    health = world.get(eid, Health)
    return health is not None and health.hp * 2 <= health.max_hp


def _bloodied_me(world: Any, me: int, ev: Any) -> bool:
    return _bloodied(world, me)


def _save_failed(world: Any, me: int, ev: Any) -> bool:
    return not getattr(ev, "saved", False)


def _used(ref: str) -> Callable[[Any, int, Any], bool]:
    def when(world: Any, me: int, ev: Any) -> bool:
        return getattr(ev, "actor", None) == me and getattr(ev, "power", "") == ref

    return when


def _is_mba(ctx: dict[str, Any]) -> bool:
    """"A melee basic attack", as a modifier gate."""
    return ctx.get("power") == MELEE


def _weapon_ctx(ctx: dict[str, Any]) -> bool:
    row = get(ctx.get("power") or "")
    return row is not None and Keyword.WEAPON in row.keywords


# ===========================================================================
# x7_664 -- a leader that hands the next ally the payout
# ===========================================================================


@power(
    "p12315", level=0, cls=X7_664, usage=ENCOUNTER, action=STANDARD,
    reach=CloseBurst(5), target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12315(c: Cast) -> None:
    """The Effect line is unconditional -- it is not hung on the hit -- so
    the watcher is laid whether or not the attack landed."""
    foe = c.target
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)
    if foe is None:
        return
    _next_ally(
        c,
        lambda who: who == foe,
        lambda ally: c.bonus(
            "attack", 3, on=ally, until=When.EOTNT, kind="power"
        ),
    )


@power(
    "p12316", level=2, cls=X7_664, usage=ENCOUNTER, action=STANDARD,
    reach=CloseBurst(5), target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p12316(c: Cast) -> None:
    """"Ends his or her turn adjacent to the target" is a `TurnEnd` and an
    adjacency between two other creatures, which is `c.adjacent_to` rather
    than `c.adjacent` -- neither of them is the caster."""
    foe = c.target
    if foe is None:
        return
    spent = [False]

    def ended(ev: TurnEnd) -> None:
        who = ev.actor
        if spent[0] or ev.ghost or who == c.me or who not in c.allies():
            return
        if not c.adjacent_to(foe, who):
            return
        spent[0] = True
        if c.may("spend a healing surge", who=who):
            c.surge(on=who)
        c.save(on=who)

    c.watch(TurnEnd, ended, until=When.EONT)


@power(
    "p12318", level=3, cls=X7_664, usage=ENCOUNTER, action=STANDARD,
    reach=AreaBurst(2, 10), target=EACH_CREATURE,
    keywords=[
        Keyword.ARCANE, Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC
    ],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12318(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)
    if not c.last:
        return
    caught = set(c.targets)
    _next_ally(c, caught.__contains__, lambda ally: _auto_save(c, ally))


@power(
    "p12319", level=5, cls=X7_664, usage=DAILY, action=STANDARD,
    reach=AreaBurst(2, 10), target=EACH_ENEMY,
    keywords=[
        Keyword.ARCANE, Keyword.HEALING, Keyword.IMPLEMENT, Keyword.RADIANT
    ],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12319(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.RADIANT)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d10", c.int_mod, dtype=DamageType.RADIANT)
        c.slowed(until=When.EONT)
    if not c.last:
        return
    caught = set(c.targets)
    _next_ally(
        c,
        caught.__contains__,
        lambda ally: c.regeneration(3, until=When.ENCOUNTER, on=ally),
    )


@power(
    "p12320", level=6, cls=X7_664, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE, Keyword.FEAR],
)
def p12320(c: Cast) -> None:
    """"While adjacent to you" is geometry, not a clock, so the two holds go
    on an aura 1 and come off when the enemy steps out -- an enemy that
    closes after the power is used is caught by the same line.

    The -4 is gated on the attack naming *you*: a blanket -4 would follow
    the enemy into every other fight it picks this round.
    """
    aura = c.aura(1, until=When.EONT)

    def hold(who: int) -> list[Any]:
        return [
            c.penalty(
                "attack", 4, on=who, until=When.EONT,
                when=lambda ctx: ctx.get("target") == c.me,
            ),
            c.grants_advantage(on=who, to="team", until=When.EONT),
        ]

    _while_in(c, aura, lambda who: hold(who) if who in c.enemies() else [])

    def beside_me(victim: int) -> bool:
        return victim in c.enemies() and c.adjacent(victim)

    _next_ally(
        c,
        beside_me,
        lambda ally: c.grant_action_point(1, on=ally),
        until=When.ENCOUNTER,
    )


@power(
    "p12321", level=7, cls=X7_664, usage=ENCOUNTER, action=STANDARD,
    reach=CloseBurst(2), target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
    dropped=("c.reroll_attack(ev=)",),
)
def p12321(c: Cast) -> None:
    """The attack half is written. The payout is not: "rolls twice on any one
    attack roll and uses either result" has to reach an attack somebody else
    is making, and `c.reroll_attack` reads `c.trigger` -- which is the
    dispatcher's event and is None inside a watcher."""
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.prone()


@power(
    "p12322", level=9, cls=X7_664, usage=DAILY, action=STANDARD,
    reach=CloseBurst(2), target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12322(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    if not c.last:
        return
    caught = set(c.targets)

    def regain(ally: int) -> None:
        gone = [
            ref
            for ref in c.expended(on=ally)
            if (row := get(ref)) is not None
            and row.usage is Usage.ENCOUNTER
            and row.attack is not None
            and row.level <= 9
        ]
        if not gone:
            return
        pick = c.choose(sorted(gone), "regain which power")
        if pick:
            c.restore_use(pick, on=ally)

    _next_ally(c, caught.__contains__, regain, until=When.ENCOUNTER)


@power(
    "p12323", level=10, cls=X7_664, usage=DAILY, action=MINOR,
    reach=CloseBurst(5), target=EACH_OTHER_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p12323(c: Cast) -> None:
    """The target list is narrowed in the body: `Target` says "each ally" and
    the card says which allies, and that is a condition read off the board at
    the moment of use rather than a shape the header can hold."""
    who = c.target
    if who is None:
        return
    shaken = c.is_(Condition.DAZED, who) or c.is_(Condition.STUNNED, who)
    if not (c.bloodied(who) or shaken or c.is_(Condition.PRONE, who)):
        return
    picks = ["spend a healing surge"]
    if shaken:
        picks.append("shrug it off")
    if c.is_(Condition.PRONE, who):
        picks.append("stand up")
    pick = c.choose(picks, "which benefit")
    if pick == "stand up":
        c.cure(Condition.PRONE, on=who)
    elif pick == "shrug it off":
        c.cure(Condition.DAZED, Condition.STUNNED, on=who)
    elif c.may("spend a healing surge", who=who):
        c.surge(on=who)
    _walk_beside_enemy(c, who)


# ===========================================================================
# x7_917 -- a shape-changer
# ===========================================================================


@power(
    "p15889", level=2, cls=X7_917, usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
    todo=("c.replace_roll()",),
)
def p15889(c: Cast) -> None:
    """A d20 rolled at the start of the fight and kept, to be put in place of
    a later one. Nothing can substitute a stored face: `c.reroll_attack`,
    `c.reroll_check` and `c.reroll_save` all roll again, and none of them
    takes a number to use instead."""


@power(
    "p15890", level=2, cls=X7_917, usage=AT_WILL, action=MINOR,
    reach=PERSONAL, target=SELF, once_per_round=True,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
    narrative=("skill:stealth",),
)
def p15890(c: Cast) -> None:
    """The combat half is real and is a drawback: while you wear the form you
    cannot attack. So the row is not narrative whole -- only the Stealth
    clause is. Hiding behind cover from your own allies, and moving your
    speed without the usual penalty, are circumstances on a check no fight
    rolls, and there is no verb waiting to be built for either.

    `revert=None` and an explicit `c.endable`, because the way out has to
    take the attack ban and the size with it. `c.form`'s own revert ends the
    form alone, which would have left a character able to step back into
    humanoid shape and still unable to swing.
    """
    beast = c.form(until=When.ENCOUNTER, revert=None, label=c.ref)
    barred = c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    small = c.resize(Size.TINY, until=When.ENCOUNTER)

    def back(*_: Any) -> None:
        for hold in (barred, small):
            if hold is not None:
                c.end_effect(hold, on=c.me, why="left the form")

    c.endable(beast, MINOR, then=back)


@power(
    "p15891", level=6, cls=X7_917, usage=DAILY, action=MINOR,
    reach=CloseBurst(5), target=ONE_CREATURE, keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p15891(c: Cast) -> None:
    """The whole printed Effect turns on somebody knowingly lying, and a
    board never has anyone speak. The restrained-and-weakened half is real
    but it has no trigger a fight can produce, so this is a finished row that
    deliberately does nothing rather than an unwritten one."""


@power(
    "p15892", level=6, cls=X7_917, usage=DAILY, action=MINOR,
    reach=CloseBurst(5), target=ONE_CREATURE, keywords=[Keyword.ARCANE],
    dropped=("c.mark(sustain=)",),
)
def p15892(c: Cast) -> None:
    """The mark and the payout are written. "Sustain Minor" is not: a
    sustain cost is stored beside the effect and only `c.effect`, `c.zone`
    and `c.aura` take one -- `c.mark` and `c.condition` have nowhere to put
    it, so the mark runs its one round and stops."""
    foe = c.target
    if foe is None:
        return
    c.mark(until=When.EONT, on=foe)
    gain = 3 + _best(c)

    def landed(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == foe and c.marked(foe, by=c.me):
            c.temp_hp(gain, on=c.me)

    c.watch(Hit, landed, until=When.EONT)


@power(
    "p15893", level=10, cls=X7_917, usage=ENCOUNTER, action=INTERRUPT,
    reach=CloseBurst(5), target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM],
    trigger="an enemy within 5 squares targets you with a melee or ranged attack",
    on=Trigger(
        AttackDeclared, both(targets_me, enemy_within(5)),
        "an enemy within 5 squares attacks you",
    ),
)
def p15893(c: Cast) -> None:
    """"In range" is read as "at least as close to it as you are": the attack
    reached you, so anything nearer is reachable by the same swing. Its own
    enemies first, its allies second, and nothing at all leaves the attack
    where it was -- which is the printed "expended with no effect"."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    reach = max(1, c.distance(foe))
    near = [
        who
        for who in c.within(reach, of=foe, side="any")
        if who not in (c.me, foe)
    ]
    mine = [who for who in near if who in c.allies()]
    if mine:
        c.redirect(to=sorted(mine)[0])
    elif near:
        c.redirect(to=sorted(near)[0])


@power(
    "p15894", level=10, cls=X7_917, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
    dropped=("events.ExtendedRested",),
)
def p15894(c: Cast) -> None:
    """The slow is written and is gated on the aura rather than on a clock,
    so a sustained aura keeps slowing and a lapsed one stops.

    Brutal 2 is dropped -- nothing rerolls a weapon damage die that comes up
    low -- and so is the extended-rest clause, which needs an event no rest
    emits.
    """
    c.aura(1, until=When.EONT, sustain=MINOR)

    def starts(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == c.me or who not in c.enemies():
            return
        if c.in_my_aura(who, label=c.ref):
            c.slowed(on=who, until=When.EONT)

    c.watch(TurnStart, starts, until=When.ENCOUNTER)


# ===========================================================================
# x7_866 -- a wanderer
# ===========================================================================


@power(
    "p14184", level=0, cls=X7_866, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p14184(c: Cast) -> None:
    """Reading a language. There is nothing on a board to understand."""


@power(
    "p14185", level=0, cls=X7_866, usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.DIVINE],
    trigger="you make a skill check and dislike the result",
    on=Trigger(SkillCheck, my_check(), "you make a skill check"),
)
def p14185(c: Cast) -> None:
    """"Use the second roll, even if it's lower" is `keep="new"` and not
    `keep="best"` -- the difference is the whole of the printed clause."""
    c.reroll_check(keep="new")


@power(
    "p14186", level=2, cls=X7_866, usage=DAILY, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.DIVINE],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p14186(c: Cast) -> None:
    """`c.initiative` moves the creature in the order by a delta, so the
    second result is expressed as the difference between the two."""
    ev = c.trigger
    rolled = getattr(ev, "rolled", 0)
    got = c.check("insight")
    if got.total > rolled:
        c.initiative(got.total - rolled, on=c.me)


@power(
    "p14187", level=6, cls=X7_866, usage=ENCOUNTER, action=INTERRUPT,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.DIVINE],
    trigger="an adjacent creature makes an attack roll against you",
    on=Trigger(
        AttackDeclared, both(targets_me, _adjacent_attacker),
        "an adjacent creature attacks you",
    ),
)
def p14187(c: Cast) -> None:
    """The slide names its destination: "to a square adjacent to you" is an
    instruction and not a choice, so it goes through `to=`."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    sq = _free_beside(c, c.me)
    if sq is not None:
        c.slide(2, on=foe, to=sq)
    c.penalty("attack", 2, on=foe, until=When.EONT)
    c.penalty("save", 2, on=foe, until=When.EONT)


@power(
    "p14188", level=10, cls=X7_866, usage=ENCOUNTER, action=MOVE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.DIVINE],
)
def p14188(c: Cast) -> None:
    _step_beside_enemy(c, 3)
    friends = c.within(5, side="ally")
    if not friends:
        return
    mate = c.choose(sorted(friends), "who shifts")
    if mate is not None:
        c.shift(3, who=mate)


# ===========================================================================
# x7_854 -- a scholar
# ===========================================================================


@power(
    "p14137", level=0, cls=X7_854, usage=ENCOUNTER, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
    trigger="you succeed on a monster knowledge check against a monster",
    on=Trigger(
        SkillCheck,
        both(
            my_check("arcana", "dungeoneering", "history", "nature", "religion"),
            check_succeeded,
        ),
        "you succeed on a monster knowledge check",
    ),
    todo=("SkillCheck.target",),
)
def p14137(c: Cast) -> None:
    """Every clause is about "the monster" and "the target", and a
    `SkillCheck` says who rolled, which skill and what it beat -- never what
    it was rolled about. Without that there is no creature to raise defences
    against, no creature to add Intelligence against, and no creature to
    halve damage to, so all three halves wait on the same field."""


@power(
    "p14138", level=2, cls=X7_854, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
)
def p14138(c: Cast) -> None:
    """A skill bonus is not narrative here: `skill:<name>` is a modifier key
    `skills.modifier` reads, so the printed line is sayable and is said."""
    pick = c.choose(sorted(SKILLS), "which skill")
    if pick:
        c.bonus(f"skill:{pick}", 5, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p14139", level=6, cls=X7_854, usage=ENCOUNTER, action=MINOR,
    reach=CloseBurst(1), target=EACH_ALLY, keywords=[Keyword.ARCANE],
)
def p14139(c: Cast) -> None:
    """One choice for the whole use, so it is made on the first target and
    applied across `c.targets` rather than asked once per creature."""
    if not c.first:
        return
    pick = c.choose(list(ELEMENTS), "which damage type")
    if pick is None:
        return
    for who in c.targets:
        c.deals(pick, until=When.EONT, on=who)


@power(
    "p14140", level=10, cls=X7_854, usage=DAILY, action=MINOR,
    reach=CloseBurst(2), target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
    dropped=("query.deals_half(ctx=)",),
)
def p14140(c: Cast) -> None:
    """The penalties are held on the geometry and on what the creature is --
    `c.grants_in` carries neither the origin test nor five effects at once,
    so `_while_in` does it.

    The half-damage clause is dropped. **Re-aimed off `c.deals_half(when=)`,**
    which read as arrived only because `query.deals_half` exists and a
    marker naming a lowercase owner is looked for anywhere on the surface.
    That one is the *read*: it is derived from being weakened and takes
    `(world, eid)` and no context, so it cannot say "only against what is
    standing in the zone". `c.weakened` would halve the creature's damage
    everywhere instead.
    """
    word = c.choose(list(ORIGINS), "which origin")
    zone = c.zone(c.area(), until=When.EONT, sustain=MINOR)
    if word is None:
        return

    def hold(who: int) -> list[Any]:
        if not c.is_kind(word, who):
            return []
        held = [c.penalty("attack", 2, on=who, until=When.EONT)]
        held += [
            c.penalty(defence, 2, on=who, until=When.EONT)
            for defence in DEFENCES
        ]
        return held

    _while_in(c, zone, hold)


# ===========================================================================
# x7_863 -- a brawler
# ===========================================================================


@power(
    "p14171", level=0, cls=X7_863, usage=ENCOUNTER, action=ActionType.NONE,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.MARTIAL],
    trigger="you hit an enemy adjacent to you with an attack",
    on=Trigger(
        Hit, both(by_me, enemy_target_within(1)), "you hit an adjacent enemy"
    ),
)
def p14171(c: Cast) -> None:
    """"The ability modifier used in the triggering attack" is read off the
    row that rolled it, through `Hit.power`, rather than guessed from the
    character. `c.flat` and not `c.damage`, because the number is already
    settled and a crit must not maximise it."""
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is None:
        return
    c.flat(_mod_of(c, getattr(ev, "power", "")), on=foe)
    c.prone(on=foe)


@power(
    "p14172", level=2, cls=X7_863, usage=DAILY, action=INTERRUPT,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
    trigger="an enemy attacks you while it has combat advantage against you",
    on=Trigger(
        AttackDeclared, both(targets_me, _with_advantage),
        "an enemy with combat advantage attacks you",
    ),
)
def p14172(c: Cast) -> None:
    """"You do not grant combat advantage to the triggering enemy" is one
    enemy and not all of them, so the suppression is gated on the attacker
    in the modifier's context."""
    ev = c.trigger
    c.temp_hp(3 + c.level // 2, on=c.me)
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    c.no_advantage(
        on=c.me, until=When.EONT, when=lambda ctx: ctx.get("attacker") == foe
    )
    c.grants_advantage(on=foe, to="me", until=When.EONT)


@power(
    "p14173", level=6, cls=X7_863, usage=ENCOUNTER, action=REACTION,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
    trigger="an enemy adjacent to you moves away from you",
    on=Trigger(
        MoveStart, both(enemy_within(1), _self_moving),
        "an adjacent enemy moves away",
    ),
)
def p14173(c: Cast) -> None:
    """Declared on `MoveStart`, because the adjacency the card asks about is
    true before the enemy goes and false after it. The reaction resolves once
    the move has happened, which is where the shift is aimed."""
    ev = c.trigger
    foe = getattr(ev, "actor", None)
    if foe is None:
        return
    pos = c.world.get(foe, Position)
    if pos is None:
        return
    good = sorted(
        sq
        for sq in c.world.reachable_squares(c.me, 2)
        if distance(sq, pos.square) == 1
    )
    if good:
        c.shift(2, to=good[0])


@power(
    "p14174", level=10, cls=X7_863, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
)
def p14174(c: Cast) -> None:
    """`Dropped` carries `source`, so "you reduce an enemy to 0 hit points"
    is read there rather than rebuilt from the damage that did it."""
    gain = 3 + c.level // 2

    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(gain, on=c.me)

    def crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.temp_hp(gain, on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER)
    c.watch(Hit, crit, until=When.ENCOUNTER)


# ===========================================================================
# x7_886 -- one that pays in hit points and surges
# ===========================================================================


@power(
    "p14322", level=0, cls=X7_886, usage=ENCOUNTER, action=ActionType.NONE,
    reach=Melee(1), target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC, Keyword.SHADOW],
    trigger="you hit a creature adjacent to you with an attack",
    on=Trigger(Hit, by_me, "you hit a creature with an attack"),
)
def p14322(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is None or not c.adjacent(foe):
        return
    c.damage("1d6", dtype=DamageType.NECROTIC, on=c.me)
    c.damage("1d12", dtype=DamageType.NECROTIC, on=foe)


@power(
    "p14323", level=2, cls=X7_886, usage=DAILY, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE, Keyword.SHADOW],
    trigger="you make a d20 roll and dislike the result",
    on=(
        Trigger(AttackRolled, by_me, "you make an attack roll"),
        Trigger(SkillCheck, my_check(), "you make a skill check"),
        Trigger(SavingThrow, about_me, "you make a saving throw"),
    ),
    dropped=("c.ability_check()",),
)
def p14323(c: Cast) -> None:
    """"A d20 roll" is three events, so it is three declared triggers rather
    than one that reads a field none of them share. The fourth kind -- a bare
    ability check -- is not rolled on a board and is dropped."""
    ev = c.trigger
    c.spend_surge(on=c.me)
    if isinstance(ev, AttackRolled):
        c.reroll_attack(keep="new")
    elif isinstance(ev, SkillCheck):
        c.reroll_check(keep="new")
    elif isinstance(ev, SavingThrow):
        c.reroll_save(keep="new")


@power(
    "p14324", level=6, cls=X7_886, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE, Keyword.SHADOW],
    )
def p14324(c: Cast) -> None:
    """The whole printed Effect is darkvision, until the end of your next
    turn."""
    c.darkvision(until=When.EONT)


@power(
    "p14325", level=10, cls=X7_886, usage=DAILY, action=INTERRUPT,
    reach=CloseBurst(5), target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.SHADOW],
    trigger="an ally within 5 squares misses or fails a saving throw",
    on=(
        Trigger(Miss, ally_within(5), "an ally within 5 squares misses"),
        Trigger(
            SavingThrow, both(ally_within(5), _save_failed),
            "an ally within 5 squares fails a saving throw",
        ),
    ),
)
def p14325(c: Cast) -> None:
    """"This power is not expended" is `c.restore_use` on the row's own ref,
    and the second outcome is read off the live `AttackResult` riding on the
    event rather than from `c.landed` -- the attack is the ally's."""
    ev = c.trigger
    c.spend_surge(on=c.me)
    if isinstance(ev, SavingThrow):
        if not c.reroll_save(bonus=4):
            c.restore_use(c.ref, on=c.me)
        return
    c.reroll_attack(keep="new", bonus=4)
    result = getattr(ev, "result", None)
    if result is not None and not result.hit:
        c.restore_use(c.ref, on=c.me)


# ===========================================================================
# x7_926 -- one that fights harder for being hurt
# ===========================================================================


@power(
    "p15949", level=0, cls=X7_926, usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.FEAR],
    trigger="you hit an adjacent enemy with a melee weapon attack",
    on=Trigger(
        Hit, both(by_me, by_melee, enemy_target_within(1)),
        "you hit an adjacent enemy in melee",
    ),
)
def p15949(c: Cast) -> None:
    """"You grant combat advantage" has no side word: `c.grants_advantage`
    names one beneficiary or one of your own sides, so granting it to the
    creatures you are fighting is that relation once per enemy."""
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is not None:
        for who in c.within(1, of=foe, side="any"):
            if who not in (c.me, foe):
                c.damage(c.w(), on=who)
    for enemy in c.enemies():
        c.grants_advantage(on=c.me, to=enemy, until=When.EONT)
    for near in c.within(2, side="enemy"):
        c.grants_advantage(on=near, to="team", until=When.EONT)


@power(
    "p15950", level=2, cls=X7_926, usage=ENCOUNTER, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
    trigger="you drop a creature below 1 hit point",
    on=Trigger(Dropped, by_me, "you drop a creature"),
)
def p15950(c: Cast) -> None:
    """`by_me` reads `Dropped.source`, which is who crossed the line --
    `query.enemies` filters the dead out, so asking whether the corpse is
    still an enemy of yours is false every time."""
    c.shift(c.speed_of() + 2)


@power(
    "p15951", level=6, cls=X7_926, usage=DAILY, action=REACTION,
    reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL, Keyword.FEAR],
    trigger="an attack bloodies you, or damages you while you are bloodied",
    on=(
        Trigger(Bloodied, about_me, "an attack bloodies you"),
        Trigger(
            DamageApplied, both(targets_me, _bloodied_me),
            "an attack damages you while you are bloodied",
        ),
    ),
    dropped=("c.aura(vulnerable=)",),
)
def p15951(c: Cast) -> None:
    """The aura is laid. "Vulnerable 3 to weapon attacks" is not a damage
    type, and `c.vulnerable` takes one of those or nothing at all -- there is
    no gate on it, so the clause has nowhere to sit and a blanket
    vulnerability would be a much larger rule."""
    c.aura(1, until=When.ENCOUNTER)


@power(
    "p15952", level=10, cls=X7_926, usage=DAILY, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
    trigger="you are bloodied and start your turn dazed, dominated or stunned",
    on=Trigger(
        TurnStart, both(about_me, _bloodied_me),
        "you start your turn bloodied",
    ),
)
def p15952(c: Cast) -> None:
    """The trigger narrows to "bloodied and starting your turn"; which of the
    three conditions is on you is asked in the body, because `c.end_effect`
    has to name the one it is taking off."""
    holds = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)
    ended = False
    for condition in holds:
        if c.is_(condition, c.me):
            c.end_effect(on=c.me, carrying=condition, why=c.ref)
            ended = True
    if ended:
        c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")


# ===========================================================================
# x7_944 -- one that stands on the ground
# ===========================================================================


@power(
    "p16061", level=0, cls=X7_944, usage=ENCOUNTER, action=STANDARD,
    reach=CloseBurst(1), target=EACH_OTHER,
    keywords=[Keyword.ELEMENTAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC), requires=_on_the_ground,
    requires_text="you must be on the ground",
)
def p16061(c: Cast) -> None:
    """"Highest ability modifier" is not a gap: the header names one ability
    and the roll carries the difference as `plus=`, which is the house
    answer for the phrase."""
    if c.strike(plus=_best(c) - c.str_mod):
        c.damage(c.w(), _best(c))
    if not c.first:
        return
    c.slowed(on=c.me, until=When.EONT)
    c.resist(1 + c.level // 2, until=When.EONT, on=c.me)


@power(
    "p16062", level=2, cls=X7_944, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ELEMENTAL],
    requires=_on_the_ground, requires_text="you must be on the ground",
    dropped=("c.ability_check()",),
)
def p16062(c: Cast) -> None:
    """"Or until you are no longer on the ground" is asked of the board by
    the gate itself, so the bonus lapses the moment the character leaves it
    and comes back when he lands -- a duration could not say that.

    Strength checks are dropped: `skill:<name>` reaches the seventeen
    skills and nothing rolls a bare ability check.
    """
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER, kind="power",
        when=lambda ctx: not ctx.get("ranged") and not c.moving_as("fly"),
    )


@power(
    "p16063", level=6, cls=X7_944, usage=ENCOUNTER, action=MOVE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ELEMENTAL],
)
def p16063(c: Cast) -> None:
    """Both holds end with the turn, because the card gives them "during this
    movement" and not for a round."""
    c.ignores_difficult("earth", until=When.EOT)
    c.phasing(until=When.EOT)
    c.move(c.speed_of())


@power(
    "p16064", level=10, cls=X7_944, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ELEMENTAL],
    requires=_on_the_ground, requires_text="you must be on the ground",
    dropped=("c.aura(difficult=)",),
)
def p16064(c: Cast) -> None:
    """The sustain payout is written, hung on the aura's own effect --
    `c.aura` hands back an id and `c.on_sustain` wants the effect, which is
    what `_zone_effect` is for.

    The difficult ground is dropped. A zone carries `difficult` and an aura
    has no way to be given it, and the printed line narrows it further to
    enemies without earth walk, which a terrain flag cannot say either.
    """
    aura = c.aura(2, until=When.EONT, sustain=MINOR)

    def payout() -> None:
        inside = [
            who for who in c.world.zones.occupants(aura)
            if who == c.me or who in c.allies()
        ]
        if inside:
            c.temp_hp(c.level // 2, on=sorted(inside)[0])

    c.on_sustain(_zone_effect(c, aura), payout)


# ===========================================================================
# x7_973 -- a drill sergeant
# ===========================================================================


@power(
    "p16366", level=0, cls=X7_973, usage=AT_WILL, action=MINOR,
    reach=PERSONAL, target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p16366(c: Cast) -> None:
    """The choice is made at the start of each of your turns, so it is a
    watcher on `TurnStart` held for the life of the stance -- not three
    modifiers laid once, which would run all three benefits at once."""
    c.stance(label=c.ref)

    def offence() -> None:
        c.bonus(
            "attack", 1, on=c.me, until=When.SONT, kind="power", when=_is_mba
        )

    def defence() -> None:
        def landed(ev: Hit) -> None:
            if ev.attacker != c.me or not _is_mba({"power": ev.power}):
                return
            beside = [who for who in c.within(1, side="ally")]
            if not beside:
                return
            mate = sorted(beside)[0]
            for defensive in DEFENCES:
                c.bonus(
                    defensive, 1, on=mate, until=When.SONT, kind="power"
                )

        c.watch(Hit, landed, until=When.SONT)

    def tactics() -> None:
        def landed(ev: Hit) -> None:
            if ev.attacker == c.me and _is_mba({"power": ev.power}):
                c.shift(1)

        c.watch(Hit, landed, until=When.SONT)

    def each_turn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != c.me:
            return
        pick = c.choose(["offence", "defence", "tactics"], "which benefit")
        if pick == "offence":
            offence()
        elif pick == "defence":
            defence()
        elif pick == "tactics":
            tactics()

    c.watch(TurnStart, each_turn, until=When.STANCE)


@power(
    "p16367", level=2, cls=X7_973, usage=ENCOUNTER, action=FREE,
    reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.MARTIAL],
    trigger="you miss an enemy with a melee attack",
    on=Trigger(Miss, both(by_me, by_melee), "you miss with a melee attack"),
)
def p16367(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is not None:
        c.grants_advantage(on=foe, to="team", until=When.SONT)


@power(
    "p16368", level=6, cls=X7_973, usage=ENCOUNTER, action=MOVE,
    reach=CloseBurst(5), target=EACH_OTHER_ALLY, keywords=[Keyword.MARTIAL],
)
def p16368(c: Cast) -> None:
    """Your move happens once and before any of the shifts, which is what
    `c.first` is for -- the allies are shifting to where you ended up."""
    if c.first:
        c.move(c.speed_of() // 2)
    mate = c.target
    if mate is None:
        return
    pos = c.world.get(c.me, Position)
    if pos is None:
        return
    good = sorted(
        sq
        for sq in c.world.reachable_squares(mate, c.speed_of(mate))
        if distance(sq, pos.square) == 1
    )
    if good:
        c.shift(c.speed_of(mate), who=mate, to=good[0])


@power(
    "p16369", level=10, cls=X7_973, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
    dropped=("c.resist_in(when=)",),
)
def p16369(c: Cast) -> None:
    """`side="ally"` and not `"team"`: the card says "each ally", and the
    caster is not in that pool. "Who can hear you" is dropped -- the
    resistance is handed out by geometry and nothing filters it by what a
    creature can perceive."""
    aura = c.aura(1, until=When.ENCOUNTER)
    c.resist_in(aura, _best(c), side="ally")


# ===========================================================================
# x7_985 -- one that fights best when it is losing
# ===========================================================================


@power(
    "p16429", level=0, cls=X7_985, usage=ENCOUNTER, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
    trigger="you miss with an at-will attack power while you are bloodied",
    on=Trigger(
        Miss, both(by_me, _at_will_and_bloodied),
        "you miss with an at-will power while bloodied",
    ),
)
def p16429(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "p16430", level=2, cls=X7_985, usage=ENCOUNTER, action=MINOR,
    reach=CloseBurst(5), target=ONE_CREATURE, keywords=[Keyword.MARTIAL],
)
def p16430(c: Cast) -> None:
    """The penalty is gated on the attack *not* naming the target. An area
    attack that catches the target and somebody else is announced once per
    creature, so this reads narrower than the printed "attacks that do not
    include the target" on exactly those."""
    foe = c.target
    if foe is None or not c.can_see(foe):
        return
    c.grants_advantage(on=foe, to="me", until=When.EONT)
    for defensive in DEFENCES:
        c.bonus(
            defensive, 2, on=c.me, until=When.EONT, kind="power",
            when=lambda ctx: ctx.get("attacker") == foe,
        )
    c.penalty(
        "attack", 2, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") != foe,
    )


@power(
    "p16431", level=6, cls=X7_985, usage=DAILY, action=FREE,
    reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p16431(c: Cast) -> None:
    """`c.extra_action` drops an action into the budget the turn is already
    spending, and initiative is rolled before anybody has a turn -- so the
    grant waits for the first `TurnStart` rather than being made now and
    thrown away."""
    spent = [False]

    def first_turn(ev: TurnStart) -> None:
        if spent[0] or ev.ghost or ev.actor != c.me:
            return
        spent[0] = True
        c.extra_action(MOVE, on=c.me)

    c.watch(TurnStart, first_turn, until=When.ENCOUNTER)


@power(
    "p16432", level=10, cls=X7_985, usage=DAILY, action=INTERRUPT,
    reach=PERSONAL, target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    trigger="you drop below 1 hit point",
    on=Trigger(Dropped, about_me, "you drop below 1 hit point"),
)
def p16432(c: Cast) -> None:
    """"If the attack reduces its target to 0 hit points" is watched rather
    than read back: the row borrows one of your own at-wills and whether it
    felled anything is a `Dropped` of yours during that use."""
    powers = c.world.get(c.me, Powers)
    if powers is None:
        return
    mine = [
        ref
        for ref in powers.known
        if (row := get(ref)) is not None
        and row.usage is Usage.AT_WILL
        and row.attack is not None
    ]
    if not mine:
        return
    pick = c.choose(sorted(mine), "which at-will")
    if pick is None:
        return
    felled = [False]

    def down(ev: Dropped) -> None:
        if ev.source == c.me:
            felled[0] = True

    watching = c.watch(Dropped, down, until=When.EOT)
    c.use_power(pick, spend=False)
    c.end_effect(watching, on=c.me, why=c.ref)
    if felled[0] and c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


# ===========================================================================
# x7_993 -- a beast form
# ===========================================================================


@power(
    "p16530", level=0, cls=X7_993, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH],
    dropped=("spec.inline_block()", "c.forbid(keyword=)"),
)
def p16530(c: Cast) -> None:
    """The form itself is written: it holds until the encounter ends, it is
    Small, and it can be stepped out of as a minor action with a shift.

    Three clauses are dropped. The page prints a **second block** -- a melee
    attack usable at will while the form lasts -- under this same ref and
    with no ref of its own, so there is nothing to decorate and nothing to
    grant. The ban is by keyword rather than by row, and `c.forbid` names one
    row. Low-light vision is the twelve-row hold it always is.
    """
    beast = c.form(until=When.ENCOUNTER, revert=None, label=c.ref)
    small = c.resize(Size.SMALL, until=When.ENCOUNTER)

    def back() -> None:
        if small is not None:
            c.end_effect(small, on=c.me, why="left the form")
        c.shift(1)

    c.endable(beast, MINOR, then=back)
    c.low_light(until=When.ENCOUNTER)


@power(
    "p16532", level=2, cls=X7_993, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING, Keyword.BEAST_FORM],
    requires=lambda world, eid: _bloodied(world, eid),
    requires_text="you must have started this turn bloodied",
)
def p16532(c: Cast) -> None:
    """Both benefits are printed "while you are in beast form", and the form
    is a labelled hold, so `c.suffering` is the question -- with
    `include_self=True`, which it needs because the form is the caster's
    own."""
    if c.me not in c.suffering("p16530", include_self=True):
        return
    c.mode("climb", max(1, c.speed_of() // 2), until=When.ENCOUNTER)
    c.regeneration(2, until=When.ENCOUNTER, while_bloodied=True)


@power(
    "p16533",
    keywords=[Keyword.BEAST_FORM], level=6, cls=X7_993, usage=AT_WILL, action=MOVE,
    reach=PERSONAL, target=SELF,
)
def p16533(c: Cast) -> None:
    c.shift(2)


@power(
    "p16534",
    keywords=[Keyword.BEAST_FORM], level=10, cls=X7_993, usage=ENCOUNTER, action=FREE,
    reach=CloseBurst(2), target=EACH_ENEMY,
    trigger="you use the p16530 power",
    on=Trigger(PowerUsed, _used("p16530"), "you use the p16530 power"),
)
def p16534(c: Cast) -> None:
    """`PowerUsed` is announced before the body of the row it names runs, but
    nothing here reads what that body did -- only that it happened."""
    foe = c.target
    if foe is not None and c.can_see(foe):
        c.grants_advantage(on=foe, to="me", until=When.EONT)


# ===========================================================================
# x7_1006 -- a theme mixing divine, shadow and poison
# ===========================================================================


@power(
    "p16596", level=0, cls=X7_1006, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF,
    keywords=[Keyword.DIVINE, Keyword.POISON, Keyword.SHADOW],
)
def p16596(c: Cast) -> None:
    """"That enemy is granting combat advantage to you" is `advantage` on the
    damage context -- the settled answer for the blow that is landing.
    Asking the board again would be too late, since a one-shot grant is
    already spent by then."""
    c.bonus(
        "damage", 4, on=c.me, until=When.EONT, dtype=DamageType.POISON,
        when=lambda ctx: bool(ctx.get("advantage")) and _weapon_ctx(ctx),
    )


@power(
    "p16597", level=2, cls=X7_1006, usage=ENCOUNTER, action=MINOR,
    reach=CloseBurst(2), target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.SHADOW, Keyword.ZONE],
    dropped=("c.save(against_trap=)",),
)
def p16597(c: Cast) -> None:
    """The defence bonus is exact: `c.is_trap` reads the attacker off the
    modifier's context, which is what the clause asks.

    The free save is given but not narrowed. Nothing records that an effect
    came from a trap -- `c.save(against=)` matches an effect's label -- so
    the ally saves against whatever is on him rather than against the trap's
    half alone.
    """
    zone = c.zone(c.area(), until=When.EONT, sustain=MINOR)

    def hold(who: int) -> list[Any]:
        if who != c.me and who not in c.allies():
            return []
        return [
            c.bonus(
                defensive, 3, on=who, until=When.EONT, kind="power",
                when=lambda ctx: c.is_trap(ctx.get("attacker")),
            )
            for defensive in DEFENCES
        ]

    _while_in(c, zone, hold)

    def starts(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == c.me or who not in c.allies():
            return
        if who in c.world.zones.occupants(zone):
            c.save(on=who)

    c.watch(TurnStart, starts, until=When.ENCOUNTER)


@power(
    "p16598", level=6, cls=X7_1006, usage=ENCOUNTER, action=MOVE,
    reach=PERSONAL, target=SELF,
    keywords=[
        Keyword.DIVINE, Keyword.POISON, Keyword.SHADOW, Keyword.TELEPORTATION
    ],
)
def p16598(c: Cast) -> None:
    """`c.burns` bites on entering a zone or starting a turn in it, and this
    card says *ends* its turn -- a different moment -- so the payout is its
    own `TurnEnd` watcher."""
    c.teleport(5)
    c.conceal(on=c.me, until=When.EONT)
    aura = c.aura(1, until=When.EONT)

    def ended(ev: TurnEnd) -> None:
        who = ev.actor
        if ev.ghost or who not in c.enemies():
            return
        if who in c.world.zones.occupants(aura):
            c.damage(0, 5, dtype=DamageType.POISON, on=who)

    c.watch(TurnEnd, ended, until=When.ENCOUNTER)


@power(
    "p16599", level=10, cls=X7_1006, usage=DAILY, action=MINOR,
    reach=CloseBurst(3), target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.ILLUSION, Keyword.SHADOW],
    out_of_combat=True,
)
def p16599(c: Cast) -> None:
    """A disguise that lasts an hour, unpicked by an Insight check against a
    Bluff check. Nothing on a board looks at anybody's face."""


# ===========================================================================
# x7_1021 -- one that rolls more dice
# ===========================================================================


@power(
    "p16691", level=0, cls=X7_1021, usage=ENCOUNTER, action=FREE,
    reach=PERSONAL, target=SELF,
    trigger="you make an attack roll, a skill check or an ability check",
    on=(
        Trigger(AttackRolled, by_me, "you make an attack roll"),
        Trigger(SkillCheck, my_check(), "you make a skill check"),
    ),
    dropped=("c.ability_check()",),
)
def p16691(c: Cast) -> None:
    """"Roll two d20s and use either" is one reroll keeping the better, which
    is the same distribution. The doubles clause is read off
    `AttackResult.rolls`, which keeps every face the attack has shown -- for
    a check `c.reroll_check` hands back the second face directly."""
    _two_dice(c, 1)


@power(
    "p16692", level=2, cls=X7_1021, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF,
)
def p16692(c: Cast) -> None:
    """The creature is named here rather than being read off a check, which
    is what makes this writable where `p14137` is not."""
    seen = [
        foe
        for foe in c.enemies()
        if c.can_see(foe)
        and any(c.is_kind(word, foe) for word in ("beast", "humanoid", "magical beast"))
    ]
    if not seen:
        return
    foe = c.choose(sorted(seen), "which creature")
    if foe is None:
        return
    if c.check("history", 20):
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power(
    "p16693", level=6, cls=X7_1021, usage=DAILY, action=FREE,
    reach=PERSONAL, target=SELF,
    trigger="you make an attack roll, a skill check or an ability check",
    on=(
        Trigger(AttackRolled, by_me, "you make an attack roll"),
        Trigger(SkillCheck, my_check(), "you make a skill check"),
    ),
    dropped=("c.ability_check()",),
)
def p16693(c: Cast) -> None:
    """Three dice is two rerolls keeping the best, and the doubles clause
    widens to "any two the same", which is what the set test says."""
    _two_dice(c, 2)


def _two_dice(c: Cast, extra: int) -> None:
    """"Roll N d20s and use any result", and the daze if two come up alike."""
    ev = c.trigger
    if isinstance(ev, AttackRolled):
        for _ in range(extra):
            c.reroll_attack(keep="best")
        result = getattr(ev, "result", None)
        faces = list(getattr(result, "rolls", []) or [])
    else:
        faces = [getattr(ev, "natural", 0)]
        for _ in range(extra):
            faces.append(c.reroll_check(keep="best"))
    if len(faces) > 1 and len(set(faces)) < len(faces):
        c.dazed(on=c.me, until=When.EONT)


@power(
    "p16694", level=10, cls=X7_1021, usage=DAILY, action=STANDARD,
    reach=PERSONAL, target=SELF,
)
def p16694(c: Cast) -> None:
    """"The next two turns, reappear at the start of the third" is counted in
    `TurnStart`s of the caster's own, because no duration word says "two of
    mine". The square is not restored: a removed creature keeps its position,
    so it comes back where it went."""
    gone = c.condition(Condition.REMOVED, on=c.me, until=When.ENCOUNTER)
    turns = [0]

    def starts(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != c.me or gone is None or gone.ended:
            return
        turns[0] += 1
        if turns[0] < 3:
            return
        c.end_effect(gone, on=c.me, why=c.ref)
        if c.may("spend a healing surge", who=c.me):
            c.surge(on=c.me)
        c.grant_action_point(1, on=c.me)

    c.watch(TurnStart, starts, until=When.ENCOUNTER)


# ===========================================================================
# x7_939 -- one that lends its allies an edge
# ===========================================================================


@power(
    "p16046", level=0, cls=X7_939, usage=ENCOUNTER, action=MINOR,
    reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE, Keyword.PRIMAL],
    dropped=("c.aura(vulnerable=)",),
)
def p16046(c: Cast) -> None:
    """The resistance half is exact and is held on the geometry, so it comes
    off when a creature walks out of the aura.

    The vulnerability is dropped: it is narrowed to *your* attacks of the
    chosen type, and `c.vulnerable` reads a damage type and nothing about who
    is swinging. Applied plainly it would hand every attacker in the fight a
    +5, which is a much larger card.
    """
    pick = c.choose(
        [
            DamageType.COLD,
            DamageType.FIRE,
            DamageType.LIGHTNING,
            DamageType.NECROTIC,
            DamageType.THUNDER,
        ],
        "which damage type",
    )
    aura = c.aura(2, until=When.EONT)
    if pick is not None:
        c.resist_in(aura, 5, pick, side="team")


@power(
    "p16026", level=2, cls=X7_939, usage=DAILY, action=MINOR,
    reach=Ranged(5), target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.PRIMAL, Keyword.SUMMONING],
    todo=("spec.summon_block()",),
)
def p16026(c: Cast) -> None:
    """The spec carries the summon's behaviour and none of its numbers: no
    defences, no hit points, no size, no speed. `c.summon` wants a ref and
    `c.summon_inline` wants a `Summon` built from a block, and there is
    neither -- so nothing can be put on the board, and the clause that costs
    you a surge when it falls has nothing to fall."""


@power(
    "p16027", level=6, cls=X7_939, usage=DAILY, action=MINOR,
    reach=PERSONAL, target=SELF,
    keywords=[Keyword.ARCANE, Keyword.PRIMAL],
)
def p16027(c: Cast) -> None:
    """"Against creatures other than you" is a gate on the damage context's
    `target`, which is why this cannot be `c.grants_in` -- that carries a
    flat modifier and no condition."""
    aura = c.aura(3, until=When.EONT, sustain=MINOR)
    penalty = _best(c)

    def hold(who: int) -> list[Any]:
        if who not in c.enemies():
            return []
        return [
            c.penalty(
                "damage", penalty, on=who, until=When.EONT,
                when=lambda ctx: ctx.get("target") != c.me,
            )
        ]

    _while_in(c, aura, hold)
