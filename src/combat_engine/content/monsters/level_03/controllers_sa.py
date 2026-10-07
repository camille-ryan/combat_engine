"""Monster abilities, level 3, controllers: the second sweep.

Thirty-seven stat blocks whose rows were still undeclared. `controllers.py`
holds the first sweep of this level and this file holds the rest; the split is
by *when* the work was done rather than by what the creatures are, so the
conventions are the ones the earlier sweeps settled and they are kept here:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=WILL, printed=7)`) and the damage line goes in the header as
  data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* a printed range of "15/30" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty;
* a printed target restriction about what a creature is *suffering* **is** the
  target line now: `Target.conditions` is a real field, the printed wording
  stays in `label=`, and the empty pool refuses the row where a `requires=`
  used to spell the same refusal by hand (#361, #401). The set tests **any** of
  its members, so it cannot say "blind creatures are immune" -- a *negative*
  condition is still missing, and m1021a1 is the one row here still marked for
  it. A line asking something else of the target wants its own symbol:
  `Target.creature_kind` for a type word, `Target.ident` for its own kind. The
  same went for "a creature the attacker has hold of", which `Target.relation`
  took;
* a row that recharges on a printed condition rather than on a die keeps the
  die in the header, because that is what `actions.recharge` rolls and what
  the card shows, and arms the condition on top of it;
* "Aftereffect" is the hold's `on_end`, and "Each Failed Saving Throw" is
  `escalate=` -- neither needs a marker, which four rows here would otherwise
  have carried.

Eleven helpers are imported rather than rewritten: the two goblin-leader
shapes alone account for five blocks that differ only in a damage type.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.skirmishers import _level_of, _ref_of
from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.controllers_sa import (
    _kin_within,
    _recharge_on_miss,
)
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.controllers import (
    _SAVE_ENDS_ON_ME,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.skirmishers import (
    _SMALL_ENOUGH,
    _free_square_beside,
    _not_grabbing,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _adjacent_foes,
    _recharge_when_bloodied,
    _while_bloodied,
)
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
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, allies, distance_between, team
from combat_engine.engine.query import holding as held_by
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_ranged,
    targets_me,
)
from combat_engine.engine.zones import Zone

#: The four conditions the undead leader's finisher looks for.
_HELPLESS_ENOUGH = (
    Condition.DAZED,
    Condition.DOMINATED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


# --------------------------------------------------------------------------
# What the blocks in this file share
# --------------------------------------------------------------------------


def _kin(c: Cast, ref: str, radius: int, *, of: int | None = None) -> list[int]:
    """Allies that are a **named** stat block, standing near somebody.

    `_kin_within` asks for the caster's own kind, which is the commoner
    question; a leader whose line names a different block ("any <m499> within
    2 squares") needs the ref compared against something other than its own.
    """
    return [w for w in c.within(radius, of=of, side="ally") if _ref_of(c, w) == ref]

def _kin_in_reach(ref: str, radius: int) -> Callable[[World, int], bool]:
    """"Up to four <that block> within N squares" as a Requirement.

    Without it the row is offered every turn, resolves against whichever ally
    is nearest and does nothing, which from the outside is a row written
    wrong.
    """

    def check(world: World, eid: int) -> bool:
        return any(
            _block_of(world, mate) == ref
            and distance_between(world, eid, mate) <= radius
            for mate in allies(world, eid)
        )

    return check


def _block_of(world: World, who: int) -> str:
    """Which stat block a creature is, asked without a `Cast`."""
    ident = world.get(who, Ident)
    return ident.ref if ident else ""


def _wielding(word: str) -> Callable[[World, int], bool]:
    """A printed Requirement about what is in the creature's own hand.

    `query.holding` matches by slug as well as by group, which is what a card
    naming one weapon needs. Asked as a `requires=` rather than in the body:
    a body that checks and returns has already spent the standard action.
    """

    def check(world: World, eid: int) -> bool:
        return bool(held_by(world, eid, word))

    return check


def _ally_used(ref: str) -> Callable[[World, int, Any], bool]:
    """"When an ally uses <that row>." Read off `PowerUsed.actor`.

    Not `by_me`: the whole point of the pair is that somebody else moved.
    """

    def check(world: World, me: int, ev: PowerUsed) -> bool:
        actor = getattr(ev, "actor", None)
        return (
            actor is not None
            and actor != me
            and team(world, actor) is team(world, me)
            and getattr(ev, "power", "") == ref
        )

    return check


def _hurt_while_bloodied(world: World, me: int, ev: DamageRolled) -> bool:
    """"It takes damage while bloodied." The threshold is read now, before the
    blow lands, which is what "while" means -- the creature has to have been
    bloodied already for the row to be the answer to this hit."""
    if getattr(ev, "target", None) != me:
        return False
    hp = world.get(me, Health)
    return hp is not None and 0 < hp.hp <= hp.max_hp // 2


def _arcane_hit_me(world: World, me: int, ev: Hit) -> bool:
    """"An arcane attack hits it." The keyword is on the row that swung."""
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and Keyword.ARCANE in p.keywords


def _duck_behind(c: Cast) -> None:
    """"Change the attack's target to an adjacent ally of its level or lower."

    An interrupt, so the blow has not been rolled yet and `c.redirect` moves
    the declaration. Five blocks in this file print the sentence verbatim.
    """
    mine = _level_of(c, c.me)
    for mate in c.within(1, side="ally"):
        if _level_of(c, mate) <= mine:
            c.redirect(to=mate)
            return


def _let_it_swing(c: Cast, mate: int, *, step: int = 0) -> None:
    """"The ally can shift N squares and make an attack."

    The ally needs a victim of its own: this row's target is whoever the
    leader pointed at and may be nowhere near the creature being told to
    swing.
    """
    if step:
        c.shift(step, who=mate)
    reachable = [foe for foe in c.enemies() if c.adjacent_to(foe, mate)]
    if reachable:
        c.basic(who=mate, on=reachable[0])


def _hurts_when_it_moves(c: Cast) -> None:
    """"The target takes <damage> if it moves during its turn (save ends)."

    One effect, not two: the watch's own hold carries the save, so a separate
    `c.effect` beside it would give the victim a second saving throw against
    one printed sentence. Once per round, because "if it moves" is a toll on
    the turn and not on every square of it, and `c.turn_of` is what makes it
    *its* turn rather than anybody's movement.
    """
    victim = c.target
    if victim is None:
        return
    spent: dict[str, int] = {}

    def walked(ev: Moved) -> None:
        if ev.actor != victim or spent.get("round") == c.world.round:
            return
        if c.turn_of() != victim:
            return
        spent["round"] = c.world.round
        c.hit(on=victim)

    c.watch(
        Moved, walked, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} snare"
    )


def _sustained_zone(c: Cast, squares_: Any, far: int, *, until: When = When.SUSTAIN) -> int:
    """A zone that is kept up as a minor action and walks when it is.

    "Sustain Minor: the zone persists, and it can be moved up to N squares"
    has a payout as well as a clock, and the clock alone is what every row of
    this shape used to carry. The zone's own `Effect` is where `c.on_sustain`
    hangs it -- `c.zone` hands back the zone's id, and `Zone.effect` is the
    hold that id's duration lives on.
    """
    zone = c.zone(squares_, until=until, sustain=MINOR)
    body = c.world.get(zone, Zone)
    if body is not None and far:
        c.on_sustain(body.effect, lambda: c.move_zone(zone, far))
    return zone


def _replace_my_zone(c: Cast) -> None:
    """"...until the end of the encounter or until it uses this power again."

    `c.dispel` rather than `Zones.end`: the holds the zone laid on whoever was
    standing in it live on those creatures and outlast it otherwise.
    """
    for zone in c.my_zones():
        body = c.world.get(zone, Zone)
        if body is not None and body.label == c.ref:
            c.dispel(zone)


def _hold_while_inside(
    c: Cast,
    zone: int,
    allowed: Callable[[int], bool],
    lay: Callable[[int], list[Effect | None]],
) -> None:
    """Hold something on each qualifying creature in a zone, and lift it.

    `_aura_holds` next door does this for enemies and for one effect; an aura
    reading "all **undead allies** gain +1 to attack rolls and resist 5
    radiant" needs the other side and two holds, so the pool is a predicate
    and the payout is a list. Membership is diffed by the zone, because
    `ZoneEntered` and `ZoneExited` are exactly the two moments the hold should
    arrive and go; whoever is already standing inside is handled at the end,
    since making the zone refreshes membership before its id exists for a
    listener to recognise.
    """
    held: dict[int, list[Effect]] = {}

    def arrive(who: int) -> None:
        if who in held or not allowed(who):
            return
        got = [e for e in lay(who) if e is not None]
        if got:
            held[who] = got

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            arrive(ev.actor)

    def left(ev: ZoneExited) -> None:
        got = held.pop(ev.actor, None) if ev.zone == zone else None
        for one in got or ():
            c.world.effects.end(one, "left the zone")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(zone):
        arrive(actor)


def _ends_turn_in_zone(c: Cast, area: Any, amount: int, dtype: DamageType) -> None:
    """The toll a zone takes as a turn closes, for enemies only.

    `c.burns` is the wrong shape here: it bites on entry *and* at the start of
    a turn, and "ends its turn there" is neither of those moments.
    """
    me = c.me
    squares_ = frozenset(area)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if ev.actor in c.in_squares(squares_, side="enemy"):
            c.flat(amount, dtype=dtype, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _starts_turn_in_zone(c: Cast, area: Any, amount: int) -> None:
    """The same toll, taken at the top of a turn instead of the bottom."""
    me = c.me
    squares_ = frozenset(area)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if ev.actor in c.in_squares(squares_, side="enemy"):
            c.flat(amount, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _necrotic_while_warded(c: Cast, mate: int) -> None:
    """"While the target has these temporary hit points, its melee attacks
    deal 3 extra necrotic damage."

    A gated bonus rather than a bonus plus a clock: the condition is "has it
    still got the cushion", which is a question about `Health.temp` and not
    about a turn boundary, so it is asked as the blow is dealt.
    """

    def still_warded(ctx: dict[str, Any]) -> bool:
        hp = c.world.get(mate, Health)
        if hp is None or hp.temp <= 0:
            return False
        p = get(ctx.get("power") or "")
        return p is not None and p.reach.kind == "melee"

    c.bonus(
        "damage",
        3,
        on=mate,
        until=When.ENCOUNTER,
        dtype=DamageType.NECROTIC,
        when=still_warded,
    )


# --------------------------------------------------------------------------
# m1021
# --------------------------------------------------------------------------


@power(
    "m1021a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m1021a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1021a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=Target(
        side="enemy", everyone=True,
        label="not blinded",
        conditions_without=frozenset({Condition.BLINDED}),
    ),
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=7),
)
def m1021a1(c: Cast) -> None:
    """"Blind creatures are immune" is the negative of a condition, which is
    `conditions_without` and not `conditions` -- and not `without=` either,
    which inverts `relation` alone. The blast narrows before the area is
    applied, so an immune creature is never a target rather than being made one
    and then skipped. #401."""
    if c.strike():
        c.dazed()


@power(
    "m1021a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=NO_TARGET,
)
def m1021a2(c: Cast) -> None:
    """Its own kind, read off the stat block ref -- the only thing an author is
    given with which to ask "all of these within 10 squares". `side="team"`
    puts the caster in the pool, which is what "all of them" means: spending a
    standard action does not stop it taking a free one.""" 
    for mate in _kin_within(c, 10, c.me):
        c.move(c.speed_of(mate), who=mate)


# --------------------------------------------------------------------------
# m1049
# --------------------------------------------------------------------------


@power(
    "m1049a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=3),
    damage=Damage("1d8", 1),
)
def m1049a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1049a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d4", 2, dtype=DamageType.FORCE),
)
def m1049a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1049a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d8", 2, dtype=DamageType.THUNDER),
)
def m1049a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m1049a3",
    level=3,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1049a3(c: Cast) -> None:
    c.teleport(5)


# --------------------------------------------------------------------------
# m1056
# --------------------------------------------------------------------------


@power(
    "m1056a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m1056a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1056a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 1),
)
def m1056a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1056a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 1, kind=LIMITED),
)
def m1056a2(c: Cast) -> None:
    """The damage is in the header even though it is only ever dealt from
    inside a watch: that is where `c.hit` reads it and where a rescale finds
    it."""
    if c.strike():
        _hurts_when_it_moves(c)


@power(
    "m1056a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.conceal_in()",),
)
def m1056a3(c: Cast) -> None:
    """Automatic hit, so there is no attack line to declare. The penalty is a
    bare "-2 to attack rolls" and therefore untyped; `c.grants_in` defaults to
    a power bonus, which would quietly refuse to stack with the next one.

    The concealment the zone hands its maker's side is the dropped clause --
    `c.conceal` is a hold on a creature and nothing hangs one on a zone."""
    zone = _sustained_zone(c, c.area(), 5)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")


@power(
    "m1056a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=ONE_ALLY,
    trigger="an ally uses m1056a5",
    on=Trigger(PowerUsed, _ally_used("m1056a5"), "an ally uses m1056a5"),
)
def m1056a4(c: Cast) -> None:
    """The ally is the one that triggered this, not the one `ev.targets` names
    -- that row aims at nobody."""
    mate = getattr(c.trigger, "actor", None)
    if mate is not None:
        _let_it_swing(c, mate, step=2)


@power(
    "m1056a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m1056a5(c: Cast) -> None:
    c.shift(1)


@power(
    "m1056a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it is targeted by a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "it is targeted by a ranged attack",
    ),
)
def m1056a6(c: Cast) -> None:
    _duck_behind(c)


# --------------------------------------------------------------------------
# m1123
# --------------------------------------------------------------------------


@power(
    "m1123a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
)
def m1123a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1123a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d8"),
)
def m1123a1(c: Cast) -> None:
    """"Ranged 15/30" takes the normal range: inside it the creature shoots
    without the long-range penalty, which is the band the card is about."""
    if c.strike():
        c.hit()


@power(
    "m1123a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
)
def m1123a2(c: Cast) -> None:
    """"It or one adjacent ally" is a real choice and is offered as one."""
    if not c.strike():
        return
    c.hit()
    beside = c.within(1, side="ally")
    who = c.me
    if beside:
        picked = c.choose([c.me, *beside], c.ref)
        who = picked if picked is not None else c.me
    c.bonus(AC, 1, on=who, kind="power", until=When.EONT)


@power(
    "m1123a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m1123a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m1123a4",
    level=3,
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m1123a4(c: Cast) -> None:
    """"Spends a healing surge and regains an additional 1d6+3" is one call:
    `c.surge` takes the extra on top of the surge value, and splitting it into
    a spend and a heal would announce two healings for one printed line.

    The card prints no range for this, so it is read as a touch -- the only
    reading that does not invent a number."""
    c.surge(bonus=c.roll("1d6") + 3)


@power(
    "m1123a5",
    level=3,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m1123a5(c: Cast) -> None:
    """Surge *value*, not a surge: no surge is spent, so this is `c.heal` with
    the number `c.surge_value` reports for the creature being touched."""
    mate = c.target
    if mate is not None:
        c.heal(c.surge_value(of=mate) + 3, on=mate)


@power(
    "m1123a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1123a6(c: Cast) -> None:
    """Two printed sentences, both sayable: forced movement is one square
    shorter and a knockdown can be shrugged off. Filed as a standard action in
    the database and plainly a trait, so it is written as one."""
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# --------------------------------------------------------------------------
# m1125
# --------------------------------------------------------------------------


@power(
    "m1125a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d8"),
)
def m1125a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1125a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4, dtype=DamageType.FORCE),
)
def m1125a1(c: Cast) -> None:
    """"This power counts as a ranged basic attack" is `c.as_basic`, filed on
    first use because this creature has no trait row to arm it from -- so the
    substitution is available from the second use onward rather than the
    first, the one way this row differs from its card."""
    if c.first:
        c.as_basic(c.ref, until=When.ENCOUNTER)
    if c.strike():
        c.hit()


@power(
    "m1125a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.FORCE),
)
def m1125a2(c: Cast) -> None:
    """The lingering 2 force is `c.hazard`, which is a zone with teeth: enter
    it or start a turn in it and it bites, which is the printed pair."""
    if c.first:
        c.hazard(
            c.area(), 2, DamageType.FORCE, until=When.EONT, sustain=None
        )
    if c.strike():
        c.hit()


@power(
    "m1125a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m1125a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m1125a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1125a4(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, kind="power", until=When.EONT)
    c.bonus(REF, 4, on=c.me, kind="power", until=When.EONT)


# --------------------------------------------------------------------------
# m115785
# --------------------------------------------------------------------------


@power(
    "m115785a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115785a0(c: Cast) -> None:
    """The beast has to be adjacent **when it hits**, which is why this is a
    watch rather than a hold laid on whoever happens to be standing beside it
    at the start of the fight."""
    me = c.me

    def rewarded(ev: Hit) -> None:
        beast = ev.attacker
        if beast == me or team(c.world, beast) is not team(c.world, me):
            return
        if not adjacent(c.world, me, beast):
            return
        if not (c.is_kind("beast", on=beast) or c.is_kind("magical beast", on=beast)):
            return
        c.temp_hp(5, on=beast)

    c.watch(Hit, rewarded, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115785a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m115785a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115785a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 5),
)
def m115785a2(c: Cast) -> None:
    """Melee **3**: the reach is printed on the line and is not a sword's.
    The slide is an Effect, so it happens whether or not the blow landed."""
    if c.strike():
        c.hit()
        c.prone()
    c.slide(1)


@power(
    "m115785a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="ally",
        label="beast or magical beast",
        kinds=frozenset({"beast"}),
    ),
)
def m115785a3(c: Cast) -> None:
    """Both printed type lines are the one word: a magical beast's type words
    carry "beast" as well, so the any-of set of one refuses nothing the card
    allows and accepts nothing it does not. The gate restated the target
    restriction and came out -- an empty pool is the same refusal."""
    mate = c.target
    if mate is None:
        return
    _let_it_swing(c, mate)


@power(
    "m115785a4",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=EACH_ALLY,
)
def m115785a4(c: Cast) -> None:
    """"The target must shift to a square adjacent to it" names a destination
    rather than a distance, so the square is chosen here -- a bare `c.shift`
    asks the controller and on a quiet board walks the ally away."""
    mate = c.target
    if mate is not None:
        beside = _free_square_beside(c, c.me)
        if beside is not None:
            c.shift(1, who=mate, to=beside)
        else:
            c.shift(1, who=mate)
    if c.first:
        c.shift(1)


# --------------------------------------------------------------------------
# m115819
# --------------------------------------------------------------------------

#: The hold m115819a1 lays, which m115819a2 drags along by its label.
_NET = "m115819a1"


@power(
    "m115819a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m115819a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115819a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 3),
    requires=_wielding("net"),
    requires_text="it must be wielding a net",
)
def m115819a1(c: Cast) -> None:
    """The immobilisation carries this row's ref as its label, which is how
    m115819a2 finds the creatures its net is holding. "A square not in the
    blast" is the destination on the miss, so the step is aimed."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
        return
    victim = c.target
    if victim is None:
        return
    blast = c.area()
    taken = squares_of(c.world, victim)
    out = [
        sq
        for sq in sorted(spread(taken, 1) - taken)
        if sq not in blast
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    c.slide(1, to=out[0] if out else None)


@power(
    "m115819a2",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115819a2(c: Cast) -> None:
    """The creatures dragged along are the ones *this* block's net is holding,
    found by the label `c.condition` stamped on the hold. The waiver is armed
    before the move, because by the time the move is over the opening it was
    meant to close has already been taken."""
    caught = c.suffering(_NET)
    for foe in caught:
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
    walked = c.move(c.speed_of())
    for foe in caught:
        if walked:
            c.pull(walked, on=foe)


@power(
    "m115819a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    requires=_while_bloodied,
    requires_text="it must be bloodied",
)
def m115819a3(c: Cast) -> None:
    if c.strike():
        c.slide(1)


# --------------------------------------------------------------------------
# m1652
# --------------------------------------------------------------------------


@power(
    "m1652a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m1652a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1652a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 1, dtype=DamageType.COLD),
)
def m1652a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m1652a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 1, dtype=DamageType.COLD, kind=LIMITED),
)
def m1652a2(c: Cast) -> None:
    if c.strike():
        _hurts_when_it_moves(c)


@power(
    "m1652a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.ZONE],
    dropped=("c.conceal_in()", "c.zone(exempt=)"),
)
def m1652a3(c: Cast) -> None:
    """Two clauses are absent and they are different absences. Nothing hangs
    concealment on a zone; and a zone that exempts *some* of the creatures in
    it has no form -- `c.ignores_difficult_in` waives the terrain for a whole
    side, which is not what "creatures with that ability can ignore this"
    says."""
    _sustained_zone(c, c.area(), 5)


@power(
    "m1652a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=ONE_ALLY,
    trigger="an ally uses m1652a5",
    on=Trigger(PowerUsed, _ally_used("m1652a5"), "an ally uses m1652a5"),
)
def m1652a4(c: Cast) -> None:
    mate = getattr(c.trigger, "actor", None)
    if mate is not None:
        _let_it_swing(c, mate, step=2)


@power(
    "m1652a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m1652a5(c: Cast) -> None:
    c.shift(1)


@power(
    "m1652a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it is targeted by a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "it is targeted by a ranged attack",
    ),
)
def m1652a6(c: Cast) -> None:
    _duck_behind(c)


@power(
    "m1652a7",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1652a7(c: Cast) -> None:
    """"Until the end of **that creature's** next turn" is `When.EOTNT`, which
    is read against whoever carries the hold -- the attacker here, not this
    creature."""
    me = c.me

    def chilled(ev: Hit) -> None:
        if ev.target != me or ev.attacker == me:
            return
        p = get(ev.power or "")
        if p is None or p.reach.kind not in ("melee", "close_burst", "close_blast"):
            return
        c.slowed(until=When.EOTNT, on=ev.attacker)

    c.watch(Hit, chilled, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m3511
# --------------------------------------------------------------------------


@power(
    "m3511a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
    dropped=("c.swallowed()",),
)
def m3511a0(c: Cast) -> None:
    """Being inside the creature is modelled as what the card says it does --
    stunned and burning, both ended by one save. What is dropped is the rest
    of being swallowed: nothing has line of sight or effect to the victim, and
    only one creature can be held at a time, so the row is not refused while
    it already has somebody."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and c.size_of(on=victim) in _SMALL_ENOUGH:
        c.condition(
            Condition.STUNNED,
            until=When.SAVE_ENDS,
            on=victim,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m3511a1",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3511a1(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(4)


@power(
    "m3511a2",
    level=3,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
)
def m3511a2(c: Cast) -> None:
    if c.strike():
        c.pull(2)


# --------------------------------------------------------------------------
# m4181
# --------------------------------------------------------------------------


@power(
    "m4181a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4, dtype=DamageType.COLD),
)
def m4181a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m4181a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m4181a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4181a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4181a2(c: Cast) -> None:
    """Three printed clauses in order, with the step in the middle doing the
    work: "a different target" is only reachable because of it. `c.use_power`
    spends this row's action rather than two more."""
    bitten = next(iter(_adjacent_foes(c)), None)
    if bitten is not None:
        c.use_power("m4181a0", on=bitten)
    c.shift(2)
    other = next((foe for foe in _adjacent_foes(c) if foe != bitten), None)
    if other is not None:
        c.use_power("m4181a1", on=other)


@power(
    "m4181a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=Target(
        side="enemy", everyone=True,
        label="slowed or restrained creatures",
        conditions=frozenset({Condition.SLOWED, Condition.RESTRAINED}),
    ),
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d6", 3, kind=LIMITED),
)
def m4181a3(c: Cast) -> None:
    """"This forced movement can affect a creature restrained by its own
    m4181a4" is not a clause the engine has to be told: `c.push` moves a
    restrained creature already, because restraint stops its own walking and
    not somebody else's shove.

    The target line is `Target.conditions` now, so the burst never contains an
    unqualified creature and the Requirement is the empty pool."""
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m4181a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m4181a4(c: Cast) -> None:
    """"Recharges when first bloodied" is armed on top of the die, which stays
    in the header because that is what `actions.recharge` rolls. The
    Aftereffect is the hold's `on_end`: it follows the restraint going
    whichever way it went, which a second save-ends effect laid now would
    not."""
    _recharge_when_bloodied(c)
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    held = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    if held is not None:
        held.on_end.append(
            lambda: c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
        )


# --------------------------------------------------------------------------
# m4229
# --------------------------------------------------------------------------


@power(
    "m4229a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 3),
)
def m4229a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4229a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=6),
    dropped=("c.blindsight()",),
)
def m4229a1(c: Cast) -> None:
    """Concealment is a -2 to the attack, and the creature that suffers it is
    the *target* -- so the hold goes on the target and is gated on whom it is
    swinging at, which is the only way round to say "it treats everything
    further off than arm's reach as concealed".

    "Creatures that do not rely on sight are immune" is the dropped clause:
    nothing in the engine has blindsight to be asked about."""
    victim = c.target
    if victim is None or not c.strike():
        return

    def at_a_distance(ctx: dict[str, Any]) -> bool:
        other = ctx.get("target")
        return other is not None and not adjacent(c.world, victim, other)

    c.penalty("attack", 2, on=victim, until=When.EONT, when=at_a_distance)


@power(
    "m4229a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 3, dtype=DamageType.NECROTIC),
)
def m4229a2(c: Cast) -> None:
    """"The next attack against the target has a +2 bonus" is combat advantage
    by another name -- the same number, spent once -- and `once=True` is what
    makes it the *next* attack rather than every one until a clock runs out."""
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", once=True, until=When.ENCOUNTER)


@power(
    "m4229a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4229a3(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4229a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it takes damage from an attack",
    on=Trigger(DamageRolled, targets_me, "it takes damage from an attack"),
    dropped=("etl.monster.scenery()",),
)
def m4229a4(c: Cast) -> None:
    """`c.halve` returns the points it took off, which is exactly "the rest"
    the ally is handed -- so the two halves add back up to the blow rather
    than each being computed from the same number twice.

    "Only while she is adjacent to her shard" is the dropped clause, and the
    gap is in extraction rather than in the engine: `c.scenery` can find a
    piece of scenery and `c.distance` can measure to it, but nothing reads a
    stat block's props and puts one on the board, so the requirement cannot be
    asked and the row fires without it."""
    taken = c.halve()
    mate = next((a for a in c.within(5, side="ally") if a != c.me), None)
    if mate is not None and taken > 0:
        c.flat(taken, on=mate)


# --------------------------------------------------------------------------
# m4458
# --------------------------------------------------------------------------


@power(
    "m4458a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 2, dtype=DamageType.NECROTIC),
)
def m4458a0(c: Cast) -> None:
    """"Loses a healing surge" is `c.spend_surge`, which takes one off without
    healing anybody -- `c.surge` is the other half and would hand the victim
    the hit points the card is taking away."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.push(2)
    if victim is not None and c.is_(Condition.IMMOBILIZED, on=victim):
        c.spend_surge(on=victim)


@power(
    "m4458a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m4458a1(c: Cast) -> None:
    """Cold *and* necrotic on one roll, which resistance reads as a unit.
    Keeping the number in the header where a rescale can find it costs the
    cold half of the type."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m4458a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=Target(
        side="enemy", everyone=True,
        label="immobilized enemies",
        conditions=frozenset({Condition.IMMOBILIZED}),
    ),
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=False),
    dropped=("Damage(dtypes=)",),
)
def m4458a2(c: Cast) -> None:
    """The miss line is not half damage -- it is the same dice and one summon
    instead of two -- so `half_on_miss` is off and the miss branch rolls the
    header for itself. `c.summon` puts the newcomer in the initiative order as
    well as on the board, which is the half `loader.spawn` alone misses."""
    victim = c.target
    if victim is None:
        return
    landed = c.strike()
    c.hit()
    wisps = 2 if landed else 1
    if landed:
        c.spend_surge(on=victim)
    for _ in range(wisps):
        where = _free_square_beside(c, victim)
        if where is None:
            break
        c.summon("m4456", at=where)


# --------------------------------------------------------------------------
# m4589
# --------------------------------------------------------------------------


@power(
    "m4589a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 1),
)
def m4589a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4589a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("3d4", 4, dtype=DamageType.FORCE),
)
def m4589a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4589a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m4589a2(c: Cast) -> None:
    """`by=` is the whole point of this line: the mark belongs to the ally,
    not to the creature that laid it, and a mark with the wrong owner punishes
    the wrong attack."""
    if not c.strike():
        return
    c.hit()
    mate = next((a for a in c.within(5, side="ally") if a != c.me), None)
    if mate is not None:
        c.mark(by=mate, until=When.EONT)


@power(
    "m4589a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    todo=("c.light()",),
)
def m4589a3(c: Cast) -> None:
    """The whole printed Effect is light: nothing else happens. The engine has
    no light level, so there is nothing here that works and the row is refused
    in play rather than offered as a minor action that does nothing."""


@power(
    "m4589a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=6),
)
def m4589a4(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.EONT)
        c.penalty("attack", 4, until=When.EONT)


@power(
    "m4589a5",
    level=3,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4589a5(c: Cast) -> None:
    c.shift(2 * c.speed_of())


# --------------------------------------------------------------------------
# m4594
# --------------------------------------------------------------------------


@power(
    "m4594a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC),
)
def m4594a0(c: Cast) -> None:
    """"Knocked prone and can't stand up (save ends)" is two clocks on one
    knockdown, which is what `held=` is for: prone lasts until the creature
    stands, and for as long as the save is unmade it may not."""
    if c.strike():
        c.hit()
        c.prone(held=When.SAVE_ENDS)


@power(
    "m4594a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4594a1(c: Cast) -> None:
    """The slide names a destination -- beside this creature -- so the square
    is picked rather than left to the controller, which on five squares of
    slack would otherwise walk the victim anywhere."""
    if not c.strike():
        return
    c.hit()
    beside = _free_square_beside(c, c.me)
    c.slide(5, to=beside)


# --------------------------------------------------------------------------
# m4596
# --------------------------------------------------------------------------


@power(
    "m4596a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
    requires=_not_grabbing,
    requires_text="it must not already be grabbing a creature",
)
def m4596a0(c: Cast) -> None:
    """"Only one creature grabbed at a time" is the Requirement, asked as a
    gate: without it the row is offered every turn and quietly replaces the
    hold it already has."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4596a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("3d4", 4, dtype=DamageType.FORCE),
)
def m4596a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4596a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        side="enemy", label="the creature it is grabbing",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=6),
)
def m4596a2(c: Cast) -> None:
    """"Targets the grabbed creature" is the target line itself now, so the
    pool cannot offer anything else and the printed Requirement is the empty
    pool refusing the row. #401."""
    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
        c.spend_surge(on=c.target)  # defaults to the caster


@power(
    "m4596a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m4596a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    mate = next((a for a in c.within(5, side="ally") if a != c.me), None)
    if mate is not None:
        c.mark(by=mate, until=When.EONT)


@power(
    "m4596a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=6),
)
def m4596a4(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.EONT)
        c.penalty("attack", 4, until=When.EONT)


# --------------------------------------------------------------------------
# m4734
# --------------------------------------------------------------------------


@power(
    "m4734a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 1),
)
def m4734a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4734a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d4", 3),
)
def m4734a1(c: Cast) -> None:
    """"First Failed Saving Throw" is `escalate=`, which runs on **every**
    failed save -- `_also` is idempotent, which is where "first" comes from.
    "Save ends both" is why the daze joins the standing hold rather than
    becoming an effect of its own with a second save attached."""
    if not c.strike():
        return
    c.hit()

    def failed(eff: Effect) -> None:
        c.worsen(eff, Condition.DAZED)

    c.condition(Condition.BLINDED, until=When.SAVE_ENDS, escalate=failed)


@power(
    "m4734a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 1, kind=LIMITED),
)
def m4734a2(c: Cast) -> None:
    if c.strike():
        _hurts_when_it_moves(c)


@power(
    "m4734a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.ZONE],
    dropped=("c.zone_condition()", "c.conceal_in()"),
)
def m4734a3(c: Cast) -> None:
    """The defence penalty is held by the zone and ends with the geometry
    rather than on a clock, which is what `c.grants_in` is for. The slow is
    the gap: nothing hangs a *condition* on standing in a zone, and a
    save-ends slow laid once would outlive leaving it."""
    zone = _sustained_zone(c, c.area(), 5)
    c.grants_in(zone, WILL, -2, side="enemy", kind="untyped")


@power(
    "m4734a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="it takes damage from an attack",
    on=Trigger(DamageRolled, targets_me, "it takes damage from an attack"),
)
def m4734a4(c: Cast) -> None:
    """"Or" is a real choice. Shaking off a save-ends effect is only on the
    table when it is carrying one, so the menu is built from what is true."""
    held = [
        eff
        for eff in c.world.effects.of(c.me)
        if eff.when is When.SAVE_ENDS
    ]
    pick = "heal"
    if held:
        pick = c.choose(["heal", "shake it off"], c.ref) or "heal"
    if pick == "heal" or not held:
        c.heal(11, on=c.me)
    else:
        c.end_effect(held[0], on=c.me, why=c.ref)


@power(
    "m4734a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it is targeted by a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "it is targeted by a ranged attack",
    ),
)
def m4734a5(c: Cast) -> None:
    _duck_behind(c)


@power(
    "m4734a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m4734a6(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5071
# --------------------------------------------------------------------------


@power(
    "m5071a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 3, kind=MINION),
)
def m5071a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


# --------------------------------------------------------------------------
# m5147
# --------------------------------------------------------------------------


@power(
    "m5147a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 7),
)
def m5147a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5147a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 1),
)
def m5147a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m5147a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("3d6", 1, kind=LIMITED),
)
def m5147a2(c: Cast) -> None:
    if c.strike():
        _hurts_when_it_moves(c)


@power(
    "m5147a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5147a3(c: Cast) -> None:
    """Nothing is dropped here: the zone's whole printed content is the
    attack penalty, and sustaining it both refreshes the clock and walks it."""
    zone = _sustained_zone(c, c.area(), 5)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")


@power(
    "m5147a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m5147a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m5147a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits it with a ranged attack",
    on=Trigger(
        Hit, both(targets_me, by_ranged), "an enemy hits it with a ranged attack"
    ),
)
def m5147a5(c: Cast) -> None:
    """This one triggers on the **hit** rather than on the declaration, which
    is what its card says; `c.redirect` moves the live result with the event,
    so the damage follows the blow to the ally."""
    _duck_behind(c)


# --------------------------------------------------------------------------
# m5447
# --------------------------------------------------------------------------


@power(
    "m5447a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5447a0(c: Cast) -> None:
    """Both halves of the aura hang on the creatures standing in it and are
    lifted as they leave, which is the half a duration cannot say. The
    "undead" narrowing is asked when a creature arrives rather than gated on
    the modifier, so a living ally never carries the hold at all."""
    ring = c.aura(5, until=When.ENCOUNTER)
    mine = team(c.world, c.me)

    def undead_ally(who: int) -> bool:
        return (
            who != c.me
            and team(c.world, who) is mine
            and c.is_kind("undead", on=who)
        )

    def gifts(who: int) -> list[Effect | None]:
        return [
            c.bonus("attack", 1, on=who, until=When.ENCOUNTER),
            c.resist(5, DamageType.RADIANT, on=who, until=When.ENCOUNTER),
        ]

    _hold_while_inside(c, ring, undead_ally, gifts)


@power(
    "m5447a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5447a1(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m5447a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5447a2(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m5447a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 1),
)
def m5447a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5447a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d9", 4, dtype=DamageType.NECROTIC),
)
def m5447a4(c: Cast) -> None:
    """The die is printed as a d9 and is written as one: the header is what
    the card says, and correcting it here would hide a compendium defect."""
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5447a5",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d10", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5447a5(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn, not two: applied
    separately the victim gets two saving throws and can shake off half of a
    thing the card says is one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m5447a6",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 3, kind=LIMITED, half_on_miss=True),
)
def m5447a6(c: Cast) -> None:
    """The toll is "starts its turn", which is neither of the two moments
    `c.burns` bites at -- so it is a `TurnStart` watch instead, and a creature
    merely walking through pays nothing."""
    if c.first:
        area = c.area()
        c.zone(area, until=When.ENCOUNTER, difficult=True)
        _starts_turn_in_zone(c, area, 5)
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m5450
# --------------------------------------------------------------------------


@power(
    "m5450a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m5450a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m5450a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m5450a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.EONT)


@power(
    "m5450a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=7),
)
def m5450a2(c: Cast) -> None:
    if c.strike():
        c.condition(
            Condition.DOMINATED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )
    else:
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m5450a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m5450a3(c: Cast) -> None:
    """"Vulnerable 3 to all damage" is `c.vulnerable` with no type at all,
    which is the difference between a blanket weakness and a dozen typed
    ones."""
    if c.strike():
        c.hit()
        c.vulnerable(3, None, until=When.EONT)


@power(
    "m5450a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=7),
)
def m5450a4(c: Cast) -> None:
    """"Each Failed Saving Throw" is `escalate=` without a guard -- the
    callback is meant to run every time, which is exactly what it does. The
    miss line is a flat 5 and not half of anything, so it is written as one."""

    def burns(eff: Effect) -> None:
        c.flat(5, dtype=DamageType.PSYCHIC, on=eff.owner)

    if c.strike():
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
            escalate=burns,
        )
    else:
        c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m5450a5",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5450a5(c: Cast) -> None:
    """`Bloodied` is announced once per creature and the row is an encounter
    power, so "first" needs nothing on top of those two.

    `about_me`, not `targets_me`: `Bloodied` names its subject `actor`, and
    `targets_me` reads `ev.target` and only that -- it would have been false
    here forever, which looks exactly like a trigger that never happens."""
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5450a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger="an enemy misses it with a melee or ranged attack",
    on=Trigger(Miss, targets_me, "an enemy misses it with an attack"),
)
def m5450a6(c: Cast) -> None:
    """The order is the printed one: it vanishes and only then steps, so the
    step is taken unseen."""
    c.invisible(on=c.me, until=When.SONT)
    c.shift(3)


# --------------------------------------------------------------------------
# m5487
# --------------------------------------------------------------------------


@power(
    "m5487a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 2),
)
def m5487a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5487a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE),
)
def m5487a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m5487a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=7),
)
def m5487a2(c: Cast) -> None:
    """"Recharge if the power misses" sits on top of the die, which stays in
    the header because that is what `actions.recharge` rolls and what the card
    shows; the two only ever agree to offer the row sooner."""
    _recharge_on_miss(c)
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5799
# --------------------------------------------------------------------------


@power(
    "m5799a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d4", 4, dtype=DamageType.FIRE),
)
def m5799a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m5799a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 6, dtype=DamageType.FIRE),
)
def m5799a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
        c.grants_advantage(to="team", until=When.EONT)


@power(
    "m5799a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
)
def m5799a2(c: Cast) -> None:
    """The extra damage is gated on the cushion still being there rather than
    on a clock, because "until the target has no temporary hit points" is a
    question about `Health.temp` and not about a turn boundary."""
    _recharge_when_bloodied(c)
    mate = c.target
    if mate is None:
        return
    c.slide(3, on=mate)
    c.temp_hp(10, on=mate)
    _necrotic_while_warded(c, mate)


# --------------------------------------------------------------------------
# m6035
# --------------------------------------------------------------------------


@power(
    "m6035a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6035a0(c: Cast) -> None:
    """"Minion allies" is asked as a creature arrives, so a non-minion never
    carries the hold -- a gated modifier would have had to answer the question
    from inside a defence lookup, which carries no defender."""
    ring = c.aura(3, until=When.ENCOUNTER)
    mine = team(c.world, c.me)

    def minion_ally(who: int) -> bool:
        return who != c.me and team(c.world, who) is mine and c.is_minion(on=who)

    def gifts(who: int) -> list[Effect | None]:
        return [
            c.bonus(what, 2, on=who, until=When.ENCOUNTER)
            for what in (AC, FORT, REF, WILL)
        ]

    _hold_while_inside(c, ring, minion_ally, gifts)


@power(
    "m6035a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", dtype=DamageType.NECROTIC),
)
def m6035a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6035a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m6035a2(c: Cast) -> None:
    """"The target can choose not to be" is `c.may`, which asks the creature
    being dominated and not the one dominating it -- the damage is the price
    of refusing and so lives in the header where a rescale finds it."""
    if not c.strike():
        c.slide(2)
        return
    if c.may("be dominated"):
        c.condition(Condition.DOMINATED, until=When.EONT)
    else:
        c.hit()


@power(
    "m6035a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.ZONE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m6035a3(c: Cast) -> None:
    """"Difficult terrain **to its enemies**" is a zone that bites one side
    only, and the way to say that is to make it difficult for everybody and
    then waive it for its own team -- which is the one combination the engine
    does have."""
    if c.first:
        zone = c.zone(c.area(), until=When.EONT, difficult=True)
        c.ignores_difficult_in(zone, side="team")
    if c.strike():
        c.hit()


@power(
    "m6035a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="a minion ally in its line of sight drops to 0 hit points",
    on=Trigger(
        Dropped,
        lambda world, me, ev: (
            getattr(ev, "actor", None) is not None
            and ev.actor != me
            and team(world, ev.actor) is team(world, me)
        ),
        "a minion ally drops to 0 hit points",
    ),
)
def m6035a4(c: Cast) -> None:
    """`query.enemies` and `query.allies` both filter out the dead, so a
    `Dropped` predicate has to compare `team()` directly. Whether the body
    actually pays out is asked here, where `c.is_minion` and `c.can_see` can
    both be put to the corpse."""
    who = getattr(c.trigger, "actor", None)
    if who is None or not c.is_minion(on=who) or not c.can_see(who):
        return
    c.temp_hp(5, on=c.me)


# --------------------------------------------------------------------------
# m6037
# --------------------------------------------------------------------------


@power(
    "m6037a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 5, dtype=DamageType.LIGHTNING),
)
def m6037a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m6037a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d8", 6, dtype=DamageType.COLD),
)
def m6037a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.EONT)


@power(
    "m6037a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6037a2(c: Cast) -> None:
    """The slide is an Effect, so it happens on a miss too -- which is the one
    thing a reader of the hit line alone gets wrong about this card."""
    if c.strike():
        c.hit()
        c.dazed()
    c.slide(3)


@power(
    "m6037a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
    trigger="it takes damage from an attack",
    on=Trigger(DamageRolled, targets_me, "it takes damage from an attack"),
)
def m6037a3(c: Cast) -> None:
    """The daze is read before the push: a creature shoved out of the burst is
    still the one the card is talking about."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    dazed = c.is_(Condition.DAZED, on=victim)
    c.push(2)
    if dazed:
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=victim)


# --------------------------------------------------------------------------
# m6044
# --------------------------------------------------------------------------


@power(
    "m6044a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 1),
)
def m6044a0(c: Cast) -> None:
    """"1d8 + 1 damage **plus** 5 force damage" is two rolls of two types, not
    one -- so the weapon half stays in the header as data and the force rider
    is a second, flat blow that resistance to force can answer on its own."""
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.FORCE)
        c.slide(3)


@power(
    "m6044a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 6, dtype=DamageType.FIRE),
)
def m6044a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
        c.grants_advantage(to="team", until=When.EONT)


@power(
    "m6044a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
)
def m6044a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    mate = c.target
    if mate is None:
        return
    c.slide(3, on=mate)
    c.temp_hp(10, on=mate)
    _necrotic_while_warded(c, mate)


@power(
    "m6044a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE),
    trigger="an enemy within 5 squares makes an attack that includes it",
    on=Trigger(
        AttackDeclared,
        targets_me,
        "an enemy within 5 squares makes an attack that includes it",
    ),
)
def m6044a3(c: Cast) -> None:
    """An immediate action aimed at "the triggering enemy" declares no target
    of its own and reads the attacker off the event: `ev.targets` would name
    whoever the *other* row was pointed at, which is this creature.

    "Until the end of its current turn" is `When.EOT` -- this resolves inside
    the attacker's turn, so the caster's own clock is the right one."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or c.distance(foe) > 5:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)
        c.penalty("attack", 2, on=foe, until=When.EOT)


# --------------------------------------------------------------------------
# m6269
# --------------------------------------------------------------------------


@power(
    "m6269a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6269a0(c: Cast) -> None:
    """The extra damage follows the creature in and out of the aura, which is
    what makes it an aura rather than a bonus with a clock on it."""
    ring = c.aura(2, until=When.ENCOUNTER)
    mine = team(c.world, c.me)

    def undead_ally(who: int) -> bool:
        return (
            who != c.me
            and team(c.world, who) is mine
            and c.is_kind("undead", on=who)
        )

    def gifts(who: int) -> list[Effect | None]:
        return [
            c.bonus(
                "damage", 5, on=who, until=When.ENCOUNTER, dtype=DamageType.NECROTIC
            )
        ]

    _hold_while_inside(c, ring, undead_ally, gifts)


@power(
    "m6269a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    todo=("query.light_level(world, square)",),
)
def m6269a1(c: Cast) -> None:
    """The whole trait is a toll for standing in sunlight, and the engine has
    no light level to ask about, so there is nothing here that works."""


@power(
    "m6269a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6269a2(c: Cast) -> None:
    """Healing on an extended rest, and a place it may not take one. Neither
    half happens on a board: this is a finished row that deliberately does
    nothing in a fight."""


@power(
    "m6269a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 2),
)
def m6269a3(c: Cast) -> None:
    """"After the attack" is an Effect, so the slide happens on a miss as
    well."""
    if c.strike():
        c.hit()
    c.slide(2)


@power(
    "m6269a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6269a4(c: Cast) -> None:
    """"Twice, or once and lend a swing" is a real choice, and the second half
    is only on the table while an undead ally is near enough to take it."""
    mate = next(
        (a for a in c.within(5, side="ally") if a != c.me and c.is_kind("undead", on=a)),
        None,
    )
    pick = "twice"
    if mate is not None:
        pick = c.choose(["twice", "once, and lend a swing"], c.ref) or "twice"
    first = next(iter(_adjacent_foes(c)), None)
    if first is not None:
        c.use_power("m6269a3", on=first)
    if pick == "twice" or mate is None:
        again = next(iter(_adjacent_foes(c)), None)
        if again is not None:
            c.use_power("m6269a3", on=again, again=True)
    else:
        _let_it_swing(c, mate)


@power(
    "m6269a5",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6269a5(c: Cast) -> None:
    """The penalty is only for swings aimed back at this creature, which is a
    gate read as the attack resolves rather than a flat -2."""
    if not c.strike():
        return
    c.hit()
    me = c.me
    c.slowed(until=When.EONT)
    c.penalty(
        "attack", 2, until=When.EONT, when=lambda ctx: ctx.get("target") == me
    )


@power(
    "m6269a6",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m6269a6(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me and c.is_kind("undead", on=mate):
                c.temp_hp(10, on=mate)
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m6269a7",
    level=3,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy",
        label="one dazed, dominated, stunned, or unconscious creature",
        conditions=frozenset(_HELPLESS_ENOUGH),
    ),
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m6269a7(c: Cast) -> None:
    """The four states are the target line, so the chooser is never handed a
    creature the card refuses and the body has nothing left to re-pick."""
    if c.strike():
        c.hit()
        c.heal(5, on=c.me)


@power(
    "m6269a8",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    trigger="it takes damage while bloodied",
    on=Trigger(DamageRolled, _hurt_while_bloodied, "it takes damage while bloodied"),
    dropped=("c.form(forbids=)",),
)
def m6269a8(c: Cast) -> None:
    """The form carries the insubstantiality and the flight together, so
    reverting as a minor action takes both away at once. What is dropped is
    the ban: `c.cannot_attack` hangs on the encounter rather than on the form,
    so dropping the shape early does not hand the attack back."""
    c.form(
        conditions=[Condition.INSUBSTANTIAL],
        modes={"fly": 12},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    c.shift(12)


# --------------------------------------------------------------------------
# m6271
# --------------------------------------------------------------------------


@power(
    "m6271a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6271a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6271a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6271a1(c: Cast) -> None:
    """Nothing on a board drowns, so breathing underwater has nothing to model
    and is noted rather than marked -- which is how `aquatic_edge` next door
    settled the same sentence. The bonus is a **power** bonus here: the card
    prints the word, where the sibling blocks print a bare "+2" and are untyped
    instead, and that is the difference between stacking and not.

    `c.terrain` is asked inside the gate rather than once when the trait is
    armed, because an ordinary fight answers False and the trait still has to
    be live if the board ever floods."""

    def against_a_landlubber(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            c.terrain("aquatic")
            and victim is not None
            and not c.is_kind("aquatic", on=victim)
        )

    c.bonus(
        "attack",
        2,
        on=c.me,
        kind="power",
        until=When.ENCOUNTER,
        when=against_a_landlubber,
    )
    c.note(f"{c.ref}: it can breathe underwater")


@power(
    "m6271a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6271a2(c: Cast) -> None:
    """Half speed, the -5 and the combat advantage it hands out are the *whole*
    of what squeezing is, and the card waives all three -- so the hold is
    taken off as it lands rather than three counterweights being written."""
    _squeezes_freely(c)


@power(
    "m6271a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4),
)
def m6271a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m6271a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6271a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6271a5",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=6),
)
def m6271a5(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)
    else:
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m6510
# --------------------------------------------------------------------------


@power(
    "m6510a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 6, dtype=DamageType.PSYCHIC),
)
def m6510a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.EONT)


@power(
    "m6510a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=6),
)
def m6510a1(c: Cast) -> None:
    """The slide comes first, because who the victim can reach afterwards is
    the whole point of moving it. "A creature of its choice" is read as one of
    the victim's own side where there is one, which is what the line is for."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.slide(3)
    beside = [one for one in c.within(1, of=victim, side="any") if one != victim]
    mates = [one for one in beside if team(c.world, one) is not team(c.world, c.me)]
    pick = next(iter(mates or beside), None)
    if pick is not None:
        c.basic(who=victim, on=pick)


@power(
    "m6510a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
)
def m6510a2(c: Cast) -> None:
    """The Aftereffect is the hold's `on_end`: it follows the domination going
    whichever way it went, where a second save-ends effect laid now would
    start burning while the victim was still being puppeted."""
    _recharge_on_miss(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    held = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if held is not None:
        held.on_end.append(
            lambda: c.ongoing(5, DamageType.PSYCHIC, on=victim)
        )


@power(
    "m6510a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    trigger="an arcane attack hits it",
    on=Trigger(Hit, _arcane_hit_me, "an arcane attack hits it"),
)
def m6510a3(c: Cast) -> None:
    """No attack roll is printed, so the burn simply lands."""
    c.ongoing(5, DamageType.PSYCHIC)


# --------------------------------------------------------------------------
# m6555
# --------------------------------------------------------------------------


@power(
    "m6555a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4),
)
def m6555a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m6555a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 4),
)
def m6555a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m6555a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
    dropped=("Damage(dtypes=)",),
)
def m6555a2(c: Cast) -> None:
    """Lightning *and* thunder on one roll, which resistance reads as a unit;
    the header holds one type so the number stays rescalable."""
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m6555a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6555a3(c: Cast) -> None:
    c.insubstantial(until=When.EONT, on=c.me)


@power(
    "m6555a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6555a4(c: Cast) -> None:
    """Looking like somebody else changes no number on a board and the check
    that sees through it is rolled by whoever is talking to the disguise, not
    in a fight. A finished row that deliberately does nothing here -- and
    `out_of_combat` is also what keeps a policy from spending a minor action
    on it every single turn."""


# --------------------------------------------------------------------------
# m6578
# --------------------------------------------------------------------------


@power(
    "m6578a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6578a0(c: Cast) -> None:
    """The healing works; the switch that turns it off for a round does not.
    `c.regeneration` has no way to be suspended by a damage type, and a watch
    that ended and re-laid the whole effect would lose the clock it hangs on.
    """
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m6578a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6578a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6578a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m6578a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m6578a3",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(obscured=)",),
)
def m6578a3(c: Cast) -> None:
    """Lightly obscured is concealment, not blocked sight, and `c.zone` has
    only the second -- `blocks_sight=True` would stop the creature seeing out
    of its own cloud, which is a different and stronger thing. The zone itself
    stands and is sustained."""
    _sustained_zone(c, c.area(), 0)


# --------------------------------------------------------------------------
# m6585
# --------------------------------------------------------------------------


@power(
    "m6585a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6585a0(c: Cast) -> None:
    """As its sibling: the healing works, the type-triggered pause does not."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m6585a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6585a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6585a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.ACID, Keyword.ZONE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
    dropped=("c.zone(obscured=)",),
)
def m6585a2(c: Cast) -> None:
    """"Or until it uses this power again" is one zone at a time, and the old
    one is dispelled rather than left to its clock -- `c.dispel` also unwinds
    the holds it laid on whoever was standing in it."""
    if c.first:
        _replace_my_zone(c)
        area = c.area()
        c.zone(area, until=When.ENCOUNTER)
        _ends_turn_in_zone(c, area, 5, DamageType.ACID)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6585a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
)
def m6585a3(c: Cast) -> None:
    if c.strike():
        c.slide(2)
    else:
        c.push(1)


# --------------------------------------------------------------------------
# m6671
# --------------------------------------------------------------------------


@power(
    "m6671a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.auto_save(against=)",),
)
def m6671a0(c: Cast) -> None:
    """"Automatically succeed on saving throws against slowing and
    immobilizing effects" is the whole of this trait and nothing says it.
    `c.unsave` is the opposite half -- it makes a save fail -- and there is no
    verb for forcing one to pass, so nothing here works. Immunity is not a
    substitute: that would stop the condition landing at all rather than
    letting the creature shake it off at the end of its turn, which is
    stronger than the card and in a way a reader could not see."""


@power(
    "m6671a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m6671a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m6671a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POISON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d12", 5, dtype=DamageType.POISON),
)
def m6671a2(c: Cast) -> None:
    """"Until the end of **its** next turn" is the target's clock, which is
    `When.EOTNT` and not the caster's `EONT`."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOTNT)


@power(
    "m6671a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.ZONE],
)
def m6671a3(c: Cast) -> None:
    """Granting combat advantage is a hold on a creature rather than a
    modifier, so it goes on and comes off with the geometry; the poison is a
    toll taken as a turn closes, which is neither of the moments `c.burns`
    bites at."""
    _replace_my_zone(c)
    area = c.area()
    zone = c.zone(area, until=When.ENCOUNTER)
    mine = team(c.world, c.me)

    def a_foe(who: int) -> bool:
        return who != c.me and team(c.world, who) is not mine

    def gifts(who: int) -> list[Effect | None]:
        return [c.grants_advantage(on=who, to="team", until=When.ENCOUNTER)]

    _hold_while_inside(c, zone, a_foe, gifts)
    _ends_turn_in_zone(c, area, 5, DamageType.POISON)


# --------------------------------------------------------------------------
# m858
# --------------------------------------------------------------------------

#: The stat block this leader fields, named by ref because that is the only
#: handle an author is given.
_M858_KIN = "m499"


@power(
    "m858a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m858a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m858a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
)
def m858a1(c: Cast) -> None:
    """Who is adjacent is asked **after** the slide, because dragging the
    victim into the pack is the whole point of the line."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.slide(3)
    for mate in _kin(c, _M858_KIN, 1, of=victim):
        c.basic(who=mate, on=victim)


@power(
    "m858a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=Target(side="ally", count=4, label="of its own kind"),
    requires=_kin_in_reach(_M858_KIN, 10),
    requires_text="one of its own kind must be within 10 squares",
    dropped=("Target.ident",),
)
def m858a2(c: Cast) -> None:
    """"Up to four of them" counts a kind, which `Target` cannot filter on, so
    the ref is compared here and a target of the wrong block is passed over."""
    mate = c.target
    if mate is None or _ref_of(c, mate) != _M858_KIN:
        return
    _let_it_swing(c, mate)


@power(
    "m858a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
)
def m858a3(c: Cast) -> None:
    """`c.summon` puts each newcomer in the initiative order as well as on the
    board; `loader.spawn` alone would leave four creatures standing there that
    never act."""
    for _ in range(4):
        where = _free_square_beside(c, c.me)
        if where is None:
            break
        c.summon(_M858_KIN, at=where)


@power(
    "m858a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m858a4(c: Cast) -> None:
    """The grab belongs to the creature that hit, not to the leader, which is
    what `by=` says -- a hold with the wrong owner is sustained and escaped
    against the wrong creature."""
    me = c.me

    def latched(ev: Hit) -> None:
        if ev.attacker == me or _ref_of(c, ev.attacker) != _M858_KIN:
            return
        if team(c.world, ev.attacker) is not team(c.world, me):
            return
        if distance_between(c.world, me, ev.attacker) > 2:
            return
        c.grab(on=ev.target, by=ev.attacker)

    c.watch(Hit, latched, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m866
# --------------------------------------------------------------------------


@power(
    "m866a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 1),
)
def m866a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m866a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC),
)
def m866a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m866a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d4", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m866a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.blinded(until=When.EONT)


# --------------------------------------------------------------------------
# m930
# --------------------------------------------------------------------------


@power(
    "m930a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 1),
)
def m930a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m930a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
    requires=_wielding("quarterstaff"),
    requires_text="it must be wielding a quarterstaff",
)
def m930a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m930a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m930a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m930a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 4, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m930a3(c: Cast) -> None:
    """The miss line says the shove and the knockdown are *not* delivered, so
    the only thing in the else branch is the halved damage."""
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m930a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_SAVE_ENDS_ON_ME,
    on=Trigger(ConditionApplied, _save_ends_on_me, _SAVE_ENDS_ON_ME),
)
def m930a4(c: Cast) -> None:
    """A save rolled out of turn against the effect that just landed.
    `c.end_effect(save_ends=True)` rolls it, announces it and ends the hold on
    a success, so a failure really does leave the effect standing."""
    c.end_effect(on=c.me, save_ends=True, why=c.ref)


# --------------------------------------------------------------------------
# m934
# --------------------------------------------------------------------------


@power(
    "m934a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m934a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m934a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m934a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m934a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    dropped=("c.spring_trap()",),
)
def m934a2(c: Cast) -> None:
    """A square that bites what walks into it, which is what `c.hazard` is.
    What is dropped is the rest of the printed trap: it rolls an attack of its
    own against Reflex, it slows what it hits, and it is destroyed the first
    time it lands a blow. A hazard has no attack line and no one-shot."""
    where = _free_square_beside(c, c.me)
    if where is not None:
        c.hazard(
            {where}, "2d4+4", until=When.ENCOUNTER, sustain=None, label=c.ref
        )


@power(
    "m934a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
    dropped=("c.spring_trap()",),
)
def m934a3(c: Cast) -> None:
    """The shove works. "If a creature is attacked by a trap because of this
    forced movement it grants combat advantage to the trap" is the dropped
    half, and it waits on the same thing the caltrops do: a trap that makes an
    attack of its own, which nothing on the board does."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m934a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m934a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m934a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m934a5(c: Cast) -> None:
    """"Against traps" is a circumstance, so this is a gated modifier read as
    the attack is resolved rather than a flat +2 -- `resolve.attack` hands the
    defence lookup a context with the attacker in it, which is what makes the
    question askable at all."""

    def by_a_trap(ctx: dict[str, Any]) -> bool:
        attacker = ctx.get("attacker")
        return attacker is not None and c.is_trap(attacker)

    for what in (AC, FORT, REF, WILL):
        c.bonus(what, 2, on=c.me, until=When.ENCOUNTER, when=by_a_trap)


# --------------------------------------------------------------------------
# m967
# --------------------------------------------------------------------------


@power(
    "m967a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m967a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m967a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("3d6", 1, dtype=DamageType.FIRE, kind=LIMITED),
)
def m967a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m967a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 1, kind=LIMITED),
)
def m967a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EOTNT)


@power(
    "m967a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 1, kind=LIMITED),
)
def m967a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m967a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is targeted by a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "it is targeted by a ranged attack",
    ),
)
def m967a4(c: Cast) -> None:
    """This one ducks behind an **enemy**, not an ally, and asks nothing about
    its level -- which is why it is written out rather than sharing the helper
    the other four blocks use."""
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.redirect(to=foe)


@power(
    "m967a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m967a5(c: Cast) -> None:
    c.shift(1)
