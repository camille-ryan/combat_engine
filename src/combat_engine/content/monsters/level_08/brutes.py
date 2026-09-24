"""Monster abilities, level 8: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=13)` and `Damage("2d6", 13)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the seven levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard or free
actions are plainly traits or immediate actions and are written as such; and
a secondary attack is a second attack line, so its printed bonus is trimmed
by hand the way `Attack.bonus_for` trims the header's.

Four things this file had to settle.

**A charge whose blow is the row's own attack line.** `c.charge_at` is the
right card for "it charges and makes a melee basic attack", and the wrong
one here: it reaches the swing through `use`, and `use` refuses to re-enter
a row already in flight -- which a row that *is* the charge always is. So
those rows raise `c.charge` themselves, walk with `c.run_at`, and roll their
own declared line. The flag is not decoration: it is what puts `charge` on
the attack events and in both modifier contexts, which is what every charge
rider reads.

**A rider on a charge, read from the other side.** The same re-entry rule
bites a trait that answers its owner's charge by swinging again, because the
charge's attack is the basic and the basic is the row it would call. Those
traits carry the printed line in their own header instead and roll it.

**Attribution for "bloodies an enemy".** `Bloodied` and `Dropped` name only
the creature that fell. Who felled it exists in one place -- the log -- and
the nearest earlier `DamageApplied` on that creature is the answer, which is
also where the reach of the blow is read for the half of these lines that
says "with a melee attack".

**An aura that pays two different amounts.** A modifier is one number, so
"+1, or +2 while its owner is bloodied" is two of them: a flat one and a
gated one, laid together and taken off together when the occupant walks out.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Event,
    Health,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Size,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_charge,
    by_keyword,
    hits_me,
)

#: The reaches that count as a melee attack, for the rows whose rider is on
#: "its melee attacks" rather than on one named row.
MELEE_KINDS = ("melee",)

#: Sizes a printed "Medium size or smaller" covers.
SMALL_ENOUGH = (Size.TINY, Size.SMALL, Size.MEDIUM)


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _melee_ctx(ctx: dict[str, Any]) -> bool:
    """Is the attack this modifier is being read for a melee one?

    The attack context carries `ranged`; the damage context does not, and a
    gate on a key the context has no entry for is silently false. Both carry
    the row's ref, so the reach is looked up from that instead.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach_of(ctx.get("branch", 0)).kind in MELEE_KINDS


def _crowded(c: Cast, who: int, count: int) -> bool:
    """Is that creature hemmed in by `count` or more of the caster's allies?

    The caster is left out of the tally every time: every printed line of
    this shape counts *its allies*, and the `ally` pool puts the creature
    itself in.
    """
    return sum(1 for a in c.within(1, of=who, side="ally") if a != c.me) >= count


def _holding(world: World, eid: int) -> list[int]:
    """Whoever this creature has hold of."""
    return list(world.relations.targets(Relation.GRABBED_BY, eid))


def _has_hold(world: World, eid: int) -> bool:
    return bool(_holding(world, eid))


def _struck_by(world: World, ev: Event, victim: int) -> int | None:
    """Who landed the blow that caused this `Bloodied` or `Dropped`.

    Neither event carries a source, and both are emitted from inside the
    damage that caused them -- immediately after the `DamageApplied` that
    did it. So the attribution exists in exactly one place, which is the log,
    and the nearest earlier blow on that creature is the one to read.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            return past.source
    return None


def _struck_in_melee(world: World, ev: Event, victim: int) -> bool:
    """Was that blow a melee one?

    Read off the same `DamageApplied` the attribution comes from: `detail`
    carries the ref of the row that dealt it, and the reach is a property of
    the row. Nothing on `Bloodied` says how the wound was made.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            p = get(past.detail or "")
            return p is not None and p.reach.kind in MELEE_KINDS
    return False


def _felled_by_me(world: World, me: int, ev: Event) -> bool:
    """Sides are compared directly rather than through `enemies`, which
    filters out the dead -- and a creature that has just dropped is exactly
    what the second half of this trigger is about, so asking that way made
    the kill half of the line silently false."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    theirs = team(world, who)
    if theirs is None or theirs is team(world, me):
        return False
    return _struck_by(world, ev, who) == me


def _aura(
    c: Cast,
    radius: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
) -> int:
    """An aura whose occupants carry a hold for as long as they are inside.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the hold should go on and
    come off. Whoever is already standing inside is caught at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(radius, until=When.ENCOUNTER)

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        take(actor)
    return ring


def _squeezes_freely(c: Cast) -> None:
    """Folding into a small space costs this creature nothing.

    Half speed, the -5 to attacks and the combat advantage it hands out are
    the *whole* of what `Condition.SQUEEZING` is, and the printed line waives
    all three -- so the hold is taken off as it lands rather than three
    separate counterweights being written against it. `Effects.apply`
    installs everything before it announces, which is what makes ending an
    effect from inside `ConditionApplied` safe.
    """
    me, ref = c.me, c.ref

    def unsqueeze(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.SQUEEZING:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.SQUEEZING in eff.conditions:
                c.world.effects.end(eff, ref)

    c.watch(ConditionApplied, unsqueeze, until=When.ENCOUNTER, on=me, label=ref)


def _in_shape(prefix: str, word: str):  # noqa: ANN202
    """A printed Requirement naming one of a shapechanger's two forms.

    A creature that has not changed shape yet is in whatever shape it was
    found in, which the stat block does not say -- so an undeclared form
    rules out neither attack. Once it has changed, the hold is the answer.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(prefix):
                return effect.label.endswith(word)
        return True

    return gate


def _change_shape(c: Cast, prefix: str, shapes: tuple[str, ...]) -> None:
    """Take one of two shapes, ending whichever was worn before.

    A polymorph is not a stance, so `c.form` does not clear the old one for
    itself. The form carries no conditions and no movement modes: the printed
    line changes what the creature looks like and which rows it can reach,
    and nothing else.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(prefix):
            c.world.effects.end(effect, "changed shape")
    shape = c.choose(list(shapes), "which shape")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{prefix}{shape}")


# ==========================================================================
# Brutes
# ==========================================================================

# -- m106 -------------------------------------------------------------------


@power(
    "m106a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m106a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means.

    Only the burn is printed as fire; the declared line is untyped, so the
    header carries no type and the ongoing names one.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m106a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m106a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: nobody chooses it, it
    is a rider on a charge the m106 has already made.

    Both `Hit` and `Miss` are watched. The printed moment is the end of the
    charge, so the sweep is owed whether or not the charging blow landed, and
    those two events are the only places a resolved swing can be read from.
    Exactly one of them fires per attack, so the sweep happens once.

    The blow is declared here rather than reached through m106a0. A charge's
    attack *is* m106a0, so that row is in flight when this trait answers, and
    `use` refuses to re-enter a row already in flight -- the sweep would have
    been silently skipped every time. The line is copied because the engine
    offers nowhere else to put it.

    No recursion: the sweep's own swings are not charges, so `by_charge` is
    false for the `Hit`s they announce.
    """
    me = c.me

    def sweep(ev: Event) -> None:
        if getattr(ev, "attacker", None) != me or not by_charge(c.world, me, ev):
            return
        for foe in sorted(c.within(1, side="enemy")):
            if c.strike(on=foe):
                c.hit(on=foe)
                c.ongoing(5, DamageType.FIRE, on=foe)

    c.watch(Hit, sweep, until=When.ENCOUNTER, on=me, label="m106a1 hit")
    c.watch(Miss, sweep, until=When.ENCOUNTER, on=me, label="m106a1 miss")


@power(
    "m106a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m106a2(c: Cast) -> None:
    """Temporary hit points cannot ride a modifier, so this hangs off the two
    events that announce the crossing. Neither names who caused it, which is
    what `_struck_by` is for."""
    me = c.me

    def toll(ev: Event) -> None:
        if _felled_by_me(c.world, me, ev):
            c.temp_hp(5, on=me)

    c.watch(Bloodied, toll, until=When.ENCOUNTER, on=me, label="m106a2 blood")
    c.watch(Dropped, toll, until=When.ENCOUNTER, on=me, label="m106a2 kill")


# -- m231 -------------------------------------------------------------------

#: The hold m231a4 lays for a turn, read by m231a1 -- which is a separate row
#: and cannot be reached into any other way.
_M231_TWO = "m231a4 two allies"


def _answering_allies(c: Cast) -> int:
    return 2 if any(e.label == _M231_TWO for e in c.world.effects.of(c.me)) else 1


@power(
    "m231a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m231a0(c: Cast) -> None:
    """An aura 5 for the board to draw, with the bonus held per occupant.

    "+1, or +2 while the m231 is bloodied" is two modifiers rather than one
    gated number, because a modifier carries a single value. They are the
    whole +1 and the whole +2 rather than a point plus a point: two power
    bonuses to the same thing do not stack, the larger one wins, and that is
    exactly the printed line -- the +2 is live only while its owner bleeds,
    and the +1 is what is left the rest of the time. Written as +1 and a
    second +1 they came to +1 whatever the m231's hit points were.

    The two are tied together so that walking out of the aura takes both off.
    """
    me = c.me

    def hold(who: int) -> Effect | None:
        base = c.bonus("attack", 1, until=When.ENCOUNTER, on=who)
        if base is None:
            return None
        extra = c.bonus(
            "attack", 2, until=When.ENCOUNTER, on=who, when=lambda _ctx: c.bloodied(me)
        )
        if extra is not None:
            base.on_end.append(lambda: c.world.effects.end(extra, "left the aura"))
        return base

    _aura(c, 5, lambda who: who != me and who in c.allies(), hold)


@power(
    "m231a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m231a1(c: Cast) -> None:
    """The immediate reaction the printed line grants is not a row anybody
    chooses, so this is a trait that hands the swing over.

    `Bloodied` names only who fell. Both halves of the printed condition --
    that the m231 struck the blow, and that the blow was a melee one -- come
    off the `DamageApplied` just behind it in the log.

    How many allies answer is m231a4's business, which is a separate row and
    reaches this one through a hold rather than a call.
    """
    me = c.me

    def answer(ev: Bloodied) -> None:
        victim = ev.actor
        if _struck_by(c.world, ev, victim) != me:
            return
        if not _struck_in_melee(c.world, ev, victim):
            return
        theirs = team(c.world, victim)
        if theirs is None or theirs is team(c.world, me):
            return
        helpers = [a for a in sorted(c.within(1, of=victim, side="ally")) if a != me]
        for ally in helpers[: _answering_allies(c)]:
            c.grant_attack(ally, on=victim)

    c.watch(Bloodied, answer, until=When.ENCOUNTER, on=me, label="m231a1")


@power(
    "m231a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m231a2(c: Cast) -> None:
    """A gated damage modifier, so the extra rides the blow it belongs to and
    meets the same resistance.

    No reach gate: the printed line is "the m231's attacks", not its melee
    attacks. Who is crowding the victim changes every time anything moves, so
    the count is taken at the moment of the blow rather than stored.
    """
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who in c.enemies() and _crowded(c, who, 2)

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=mobbed)


@power(
    "m231a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 13),
)
def m231a3(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here.

    "Bloodied **after** taking this damage" is the state and not the
    crossing, so it is read once the blow has landed -- a target already
    bleeding falls over too.
    """
    who = c.target
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d6", 15)
    else:
        c.hit()
    if who is not None and alive(c.world, who) and c.bloodied(who):
        c.prone(on=who)


@power(
    "m231a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def m231a4(c: Cast) -> None:
    """A hold with no mechanical content of its own: the whole of this row is
    a number m231a1 reads, and that row is out of reach of this one except
    through something it can find on the board."""
    c.effect(_M231_TWO, until=When.EOT, on=c.me)


# -- m259 -------------------------------------------------------------------


@power(
    "m259a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC),
)
def m259a0(c: Cast) -> None:
    """The contagion is a disease track the engine has no model of, so it is
    noted rather than invented."""
    if c.strike():
        c.hit()
        c.note("m259a0: the target contracts this stat block's disease")


# -- m2908 ------------------------------------------------------------------


@power(
    "m2908a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m2908a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2908a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m2908a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2908a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m2908a2(c: Cast) -> None:
    """The row that prints the claw is used rather than copied, so its attack
    and damage lines stay in one place. The header carries them too, because
    a policy forecasts from the header and one declaring neither would look
    like a row that hurts nobody."""
    if c.target is not None:
        use(c.world, c.me, "m2908a1", targets=[c.target], spend=False)


_M2908_FLANKED = "an enemy attacks the m2908 while flanking it"


def _flanker_swings(world: World, me: int, ev: AttackDeclared) -> bool:
    return ev.target == me and flanked_by(world, me, ev.attacker)


@power(
    "m2908a3",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
    trigger=_M2908_FLANKED,
    on=Trigger(AttackDeclared, when=_flanker_swings, text=_M2908_FLANKED),
)
def m2908a3(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher
    points a triggered row at whoever the event names, and the second victim
    is not named by the event at all.

    Flanking is recomputed rather than stored, so the partner is found the
    same way the trigger found the first one -- whoever else is flanking the
    m2908 is by definition flanking *with* the triggering enemy.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    partner = next(
        (
            f
            for f in sorted(c.within(2, side="enemy"))
            if f != who and flanked_by(c.world, c.me, f)
        ),
        None,
    )
    for foe in (who, partner):
        if foe is not None and c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m2908a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 5, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m2908a4(c: Cast) -> None:
    """"Vulnerable 5 to all damage" is every type at once, which is what
    `c.vulnerable` does when no type is named."""
    if c.strike():
        c.hit()
        c.vulnerable(5, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M2908_BLED = "the m2908 is first bloodied"


@power(
    "m2908a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2908_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2908_BLED),
)
def m2908a5(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.

    The spec prints the recharging row's id as one belonging to a different
    stat block -- a creature three levels higher, whose breath this one does
    not know and could never use. The row it plainly names is this creature's
    own recharge blast, and that is the one given back and spent.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m2908a4")
    use(c.world, c.me, "m2908a4")


@power(
    "m2908a6",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
)
def m2908a6(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the condition.

    An aftereffect is what follows when the first hold ends, whether that was
    a save or the clock, so it hangs off the hold's own ending rather than
    being applied alongside it -- and not on `escalate`, which runs on a
    *failed* save and would never run at all for a hold on a turn clock.
    """
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# -- m3015 ------------------------------------------------------------------


@power(
    "m3015a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 6),
)
def m3015a0(c: Cast) -> None:
    """"A -2 penalty to melee attack rolls" is narrower than a penalty to
    attacks, and the difference is a gate: the reach is read off whichever
    row the victim is swinging when the modifier is consulted."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT, when=_melee_ctx)


@power(
    "m3015a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d8", 6, kind=LIMITED),
    requires_text="the m3015 must use this power with a m161a1",
)
def m3015a1(c: Cast) -> None:
    """The printed Requirement names a weapon, and a monster in this engine
    carries no `Gear` -- `c.wielding` answers for a character's kit and is
    false for every stat block there is. The requirement is carried as the
    printed text so the card shows it, and not as a gate, which would refuse
    the row for a reason that is about the engine rather than the board. See
    the report.
    """
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT, when=_melee_ctx)


# -- m3052 ------------------------------------------------------------------


@power(
    "m3052a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3052a0(c: Cast) -> None:
    """An ooze pours through a gap without slowing down or opening up."""
    _squeezes_freely(c)


@power(
    "m3052a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("4d6", 6, dtype=DamageType.ACID),
)
def m3052a1(c: Cast) -> None:
    """"Before or after the attack" is a choice with no board state to decide
    it on, and the step is the same either way once it is taken -- so it is
    taken after, where it can carry the ooze away from whatever it just ate.
    An Effect line happens on a miss too."""
    if c.strike():
        c.hit()
    c.shift(c.speed_of())


@power(
    "m3052a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("4d6", 6, dtype=DamageType.ACID),
)
def m3052a2(c: Cast) -> None:
    """The printed target is "creatures in the blast", which is both sides.

    The printed escape DC is not written: a grab is held as a relation and
    the engine sets the difficulty of breaking it from the grabber, so there
    is no number on this end to put it in.
    """
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3052a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    damage=Damage("2d6", 15, dtype=DamageType.ACID),
    requires=_has_hold,
    requires_text="the m3052 must have a creature grabbed",
)
def m3052a3(c: Cast) -> None:
    """The printed target is "a creature grabbed by the m3052", which no
    `Target` can say, so the header takes one enemy and the body aims at
    whoever is actually being held.

    "It takes 10 extra if it has no healing surges" is the same question as
    "did losing one work": `c.spend_surge` is False exactly when the pool was
    already empty, so one call answers both halves of the line.
    """
    held = _holding(c.world, c.me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    c.hit(on=victim)
    if not c.spend_surge(on=victim):
        c.flat(10, dtype=DamageType.ACID, on=victim)


_M3052_STRUCK = "an enemy hits the m3052 with a weapon attack"


@power(
    "m3052a4",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3052_STRUCK,
    on=Trigger(
        Hit, when=both(hits_me, by_keyword(Keyword.WEAPON)), text=_M3052_STRUCK
    ),
)
def m3052a4(c: Cast) -> None:
    """`c.summon` and not `loader.spawn`: a creature put on the board without
    an initiative slot stands there and never acts.

    With no square named, `c.summon` takes the nearest free one, which is
    what the printed line asks for.
    """
    c.summon("m3053")


# -- m3053 ------------------------------------------------------------------


@power(
    "m3053a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3053a0(c: Cast) -> None:
    """An ooze pours through a gap without slowing down or opening up."""
    _squeezes_freely(c)


@power(
    "m3053a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage(bonus=10, dtype=DamageType.ACID, kind=MINION),
)
def m3053a1(c: Cast) -> None:
    """A minion's fixed damage. The step is printed on the hit, so a miss
    buys nothing."""
    if c.strike():
        c.hit()
        c.shift(c.speed_of())


# -- m3082 ------------------------------------------------------------------


@power(
    "m3082a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 8),
)
def m3082a0(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("3d6", 13)
    else:
        c.hit()


@power(
    "m3082a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 8, kind=LIMITED),
)
def m3082a1(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("3d6", 13)
    else:
        c.hit()
    c.prone()


_M3082_KIN_STRUCK = "an enemy within 2 squares attacks one of the m3082's allies"


def _swings_at_my_kin(world: World, me: int, ev: AttackDeclared) -> bool:
    mine = team(world, me)
    if ev.attacker == me or team(world, ev.attacker) is mine:
        return False
    if ev.target == me or team(world, ev.target) is not mine:
        return False
    return distance_between(world, me, ev.attacker) <= 2


@power(
    "m3082a2",
    level=8,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3082_KIN_STRUCK,
    on=Trigger(AttackDeclared, when=_swings_at_my_kin, text=_M3082_KIN_STRUCK),
)
def m3082a2(c: Cast) -> None:
    """Filed as a free action; the printed Effect names an immediate
    interrupt, which is what it is written as.

    The recharge is given back before the row is used, because a recharge row
    that has been spent is refused -- handing it back is the whole first half
    of the printed line. The row that prints the attack is used rather than
    copied, and it is aimed at the triggering enemy rather than at whoever
    the interrupt happens to stand next to.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m3082a1")
    use(c.world, c.me, "m3082a1", targets=[who])


_M3082_FELLED = "the m3082 bloodies an enemy or drops one to 0 hit points or fewer"


@power(
    "m3082a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3082_FELLED,
    on=[
        Trigger(Bloodied, when=_felled_by_me, text="the m3082 bloodies an enemy"),
        Trigger(Dropped, when=_felled_by_me, text="or drops one to 0 hit points"),
    ],
)
def m3082a3(c: Cast) -> None:
    """Two printed triggers, so two are declared: `on=` takes a sequence and
    the row answers whichever happened.

    Declared with no target at all: the beneficiary is the m3082, and a row
    that took itself as a target would be aimed by the dispatcher at the
    creature that just went down.
    """
    c.temp_hp(c.roll("1d10") + 3, on=c.me)


# -- m3113 ------------------------------------------------------------------


@power(
    "m3113a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3),
)
def m3113a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3113a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 5),
)
def m3113a1(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m3113a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3113a2(c: Cast) -> None:
    """A charge with its own attack line in place of the basic one.

    `c.charge_at` is the card for a charge that ends in a melee basic attack;
    it reaches that swing through `use`, which refuses to re-enter a row
    already in flight -- and the row in flight here is this one. So the flag
    is raised by hand, `c.run_at` walks the approach, and the declared line is
    rolled. The flag is what puts `charge` on the attack events and in both
    modifier contexts, which is what every charge rider reads.

    The secondary is an Effect line, so it is made whether or not the charge
    landed, and a second attack line's printed bonus is trimmed by hand the
    way `Attack.bonus_for` trims the header's. The flag comes back down
    first: the charge is the blow that stands in for the melee basic, and
    leaving it up would pay every charge rider in the fight a second time.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    c.run_at(victim)
    if c.strike(on=victim):
        c.hit(on=victim)
    c.charge = False
    other = next((f for f in sorted(c.within(2, side="enemy")) if f != victim), None)
    if other is None:
        return
    if c.attack(c.world.scaling.trim(11, c.level), AC, on=other):
        c.damage("2d6", 5, on=other)


@power(
    "m3113a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3113a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    "Melee attacks" is a gate on the reach of the row landing the blow: the
    damage context carries no `attacker` and no `ranged`, so the reach is
    looked up from the ref both contexts do carry.
    """
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return who in c.enemies() and _crowded(c, who, 2)

    c.bonus("damage", 2, until=When.ENCOUNTER, on=me, when=mobbed)


# -- m365 -------------------------------------------------------------------


@power(
    "m365a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d6", 6),
)
def m365a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m365a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m365a1(c: Cast) -> None:
    """Two uses of the row that prints the attack, so its damage line stays
    in one place.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is bitten twice.
    That is the only reading that loses nothing.

    "If both attacks hit the same creature" cannot be read off `use`, which
    reports whether the row could be used and not whether it landed, so the
    hits are counted off the bus for as long as this row is swinging.
    """
    who = c.target
    if who is None:
        return
    me = c.me
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m365a0":
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label="m365a1")
    try:
        for _ in range(2 if c.first and c.last else 1):
            if not alive(c.world, who):
                return
            use(c.world, me, "m365a0", targets=[who], spend=False)
    finally:
        c.world.effects.end(counter, "the bites are done")
    if landed.count(who) >= 2 and len(_holding(c.world, me)) < 2:
        c.grab(on=who)


@power(
    "m365a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("4d8", 22),
    requires=_has_hold,
    requires_text="the m365 must have a creature grabbed",
)
def m365a2(c: Cast) -> None:
    """The printed target is "a creature grabbed by the m365", which no
    `Target` can say, so the header takes one enemy and the body aims at
    whoever is actually being held. No attack roll is printed."""
    held = _holding(c.world, c.me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None:
        c.hit(on=victim)


_M365_BLED = "the m365 is first bloodied"


@power(
    "m365a3",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    trigger=_M365_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M365_BLED),
)
def m365a3(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the condition. The
    printed target is "creatures in the blast", which is both sides."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


# -- m423 -------------------------------------------------------------------


@power(
    "m423a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
)
def m423a0(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales.

    The secondary is a second attack line and a row carries one, so its
    printed +11 is trimmed by hand the way `Attack.bonus_for` trims the
    header's -- the row still moves with whatever scaling the fight is on.
    """
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("1d10", 5)
    else:
        c.hit()
    if c.attack(c.world.scaling.trim(11, c.level), FORT):
        c.ongoing(5, DamageType.POISON)


# -- m479 -------------------------------------------------------------------

#: The prefix on m479a3's hold, so the two gated rows can read which of the
#: two shapes is in force.
_M479_SHAPE = "m479a3 "
_M479_SHAPES = ("m485", "human")


@power(
    "m479a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 4),
    requires=_in_shape(_M479_SHAPE, "human"),
    requires_text="the m479 must not be in its m485 shape",
)
def m479a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m479a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
    requires=_in_shape(_M479_SHAPE, "m485"),
    requires_text="the m479 must be in its m485 shape",
)
def m479a1(c: Cast) -> None:
    """The ongoing damage is untyped, as printed. The contagion is a disease
    track the engine has no model of, so it is noted rather than invented --
    and it is the same one the m479 is itself immune to."""
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.note("m479a1: the target contracts this stat block's disease")


@power(
    "m479a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m479a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Whether the victim is
    bleeding changes with every blow, so the gate is read at the moment of
    the damage rather than stored."""
    me = c.me

    def bleeding(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return who in c.enemies() and c.bloodied(who)

    c.bonus("damage", 4, until=When.ENCOUNTER, on=me, when=bleeding)


@power(
    "m479a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m479a3(c: Cast) -> None:
    """Which rows the shape closes off is declared on those rows as a printed
    Requirement rather than taken away here: `c.forbid` would have to know
    which shape was being left, and the gate reads the hold directly.

    The second shape is named by the id of the creature it imitates, because
    that is the only name this project has for anything.
    """
    _change_shape(c, _M479_SHAPE, _M479_SHAPES)


# -- m4883 ------------------------------------------------------------------


@power(
    "m4883a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4883a0(c: Cast) -> None:
    """A bonus to a skill check against a passive score, and nothing else.
    Neither is rolled in a fight, so the row is declared inert rather than
    given an invented mechanic."""
    c.note("m4883a0: it goes unnoticed where a duller creature would not")


@power(
    "m4883a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m4883a1(c: Cast) -> None:
    """The free action is a use of the row that prints the drag, so that row
    is used rather than copied. It is printed on the hit, so a miss buys
    nothing."""
    if c.strike():
        c.hit()
        use(c.world, c.me, "m4883a3", spend=False)


@power(
    "m4883a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 5),
)
def m4883a2(c: Cast) -> None:
    """A charge with its own attack line in place of the basic one; see
    m3113a2 for why the flag is raised by hand rather than through
    `c.charge_at`.

    "Ongoing 5 until the grab ends" is a clock no duration names, so the burn
    is hung on the encounter and tied to the hold: whatever ends the grab --
    a save, an escape, a death -- ends the damage with it.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    c.run_at(victim)
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    hold = c.grab(on=victim)
    burn = c.ongoing(5, on=victim, until=When.ENCOUNTER)
    if hold is not None and burn is not None:
        hold.on_end.append(lambda: c.world.effects.end(burn, "the grab ended"))


@power(
    "m4883a3",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4883a3(c: Cast) -> None:
    """The drag is a pull rather than a second walk: the held creature is
    moved by the m4883, and a pull is the forced move that ends closer to
    whoever is doing it, so it lands beside the m4883 wherever it stopped.

    The move happens whether or not anything is being held -- the printed
    line describes the passenger, it does not require one.

    Only half of "do not provoke from each other" is written: `c.no_provoke`
    excuses the caster from a named creature and has no `on=` to excuse the
    other one. The half that is missing is a forced move, which opens no
    window anyway. See the report.
    """
    held = sorted(_holding(c.world, c.me))
    victim = held[0] if held else None
    if victim is not None:
        c.no_provoke(from_=victim, until=When.EOT)
    moved = c.move(max(1, c.speed_of() // 2))
    if victim is not None and moved:
        c.pull(moved, on=victim)


# -- m498 -------------------------------------------------------------------


@power(
    "m498a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5),
)
def m498a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m498a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m498a1(c: Cast) -> None:
    """"Targets Medium size or smaller" is a per-target exemption no `Target`
    can say, so the body drops the big ones before the roll rather than
    after it."""
    if c.target is None or c.size_of() not in SMALL_ENOUGH:
        return
    if c.strike():
        c.hit()
        c.prone()


# -- m689 -------------------------------------------------------------------


@power(
    "m689a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m689a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m689a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m689a1(c: Cast) -> None:
    """The row that prints the club is used rather than copied, so its damage
    line stays in one place, and the second die is thrown in the
    `AttackRolled` window -- which is where `resolve.attack` is still willing
    to read the result back.

    The watch is one-shot and torn down afterwards, because the printed line
    is two rolls for *this* swing and nothing later.
    """
    victim = c.target
    if victim is None:
        return
    me, spent = c.me, [False]

    def twice(ev: AttackRolled) -> None:
        if spent[0] or ev.attacker != me or ev.power != "m689a0":
            return
        spent[0] = True
        c.trigger = ev
        c.reroll_attack(keep="best")

    watching = c.watch(AttackRolled, twice, until=When.EOT, on=me, label="m689a1")
    try:
        use(c.world, me, "m689a0", targets=[victim], spend=False)
    finally:
        c.world.effects.end(watching, "the second die is thrown")


# -- m703 -------------------------------------------------------------------


@power(
    "m703a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 5),
)
def m703a0(c: Cast) -> None:
    """A printed "crit 1d12 + 17" line *replaces* the damage rather than
    adding to it, and it is a roll -- so it is applied flat, past the
    engine's own rule that a critical maxes the declared dice, which would
    read the wrong number off this header."""
    if not c.strike():
        return
    if c.crit:
        c.flat(c.roll("1d12") + 17)
    else:
        c.hit()


_M703_KIN_DOWN = "an ally within 10 squares drops to 0 hit points"


@power(
    "m703a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger=_M703_KIN_DOWN,
    on=Trigger(Dropped, when=ally_within(10), text=_M703_KIN_DOWN),
)
def m703a1(c: Cast) -> None:
    """The ally's last swing, made as it falls.

    `c.grant_attack` and `c.basic` both refuse it: a creature that has just
    dropped cannot act, and neither of them has anywhere to say that this is
    the one shape where that gate must be stood down. `use` does -- it takes
    the event being answered and stands the gate down when that event is the
    actor's own downfall, which is exactly what this one is -- so the swing
    is handed over through `use` directly. See the report.

    Declared with no target and aimed by hand: `Dropped` names the ally, so
    the dispatcher would point the row at its own beneficiary.
    """
    ally = getattr(c.trigger, "actor", None)
    if ally is None:
        return
    foe = next(
        (f for f in sorted(c.enemies()) if distance_between(c.world, ally, f) <= 1),
        None,
    )
    if foe is None:
        return
    known = c.world.get(ally, Powers)
    ref = (known.basic if known else "") or "mba"
    use(c.world, ally, ref, targets=[foe], spend=False, trigger=c.trigger)


@power(
    "m703a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="the m703 must be bloodied",
)
def m703a2(c: Cast) -> None:
    """A basic attack rather than a named row: `c.basic` swings whatever this
    creature's basic actually is, which for a monster is one of its own rows.

    The surge and the number are two printed clauses and not one: 54 is a
    quarter of this creature's maximum only by coincidence of the numbers it
    happens to have, so the surge is spent for nothing and the healing given
    flat, which is what the card says.
    """
    if c.target is not None:
        c.basic(on=c.target)
    c.spend_surge(on=c.me)
    c.heal(54, on=c.me)


# -- m78 --------------------------------------------------------------------


@power(
    "m78a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 3),
)
def m78a0(c: Cast) -> None:
    """Bloodied swaps the dice rather than adding to them, so the header
    keeps the printed line that rescales and the larger expression is rolled
    here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("3d8", 3)
    else:
        c.hit()


@power(
    "m78a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m78a1(c: Cast) -> None:
    """Two uses of the row that prints the attack, so its damage line stays
    in one place. The printed Effect does not say whether the two land on one
    creature or two, so the header takes up to two and a single target is
    struck twice."""
    who = c.target
    if who is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, who):
            return
        use(c.world, c.me, "m78a0", targets=[who], spend=False)


_M78_BLED = "the m78 is first bloodied"


@power(
    "m78a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M78_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M78_BLED),
)
def m78a2(c: Cast) -> None:
    """"The m78 and all allies within 5" is wider than `EACH_ALLY`, which
    leaves the caster out, so the burst is walked by hand and the m78 given
    its own point.

    Declared with no target: `Bloodied` names nobody but the creature it is
    about, so the dispatcher would aim a targeted row at the m78 itself and
    the allies would go unblessed.
    """
    for who in {c.me, *c.within(5, side="ally")}:
        c.bonus("attack", 2, until=When.EONT, on=who)


#: The five the printed trigger names. Untyped damage is not one of them, and
#: neither is the sixth element the card leaves out.
_M78_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)

_M78_SCALDED = "the m78 takes acid, cold, fire, lightning or thunder damage"


def _element_struck_me(world: World, me: int, ev: Event) -> bool:
    """`DamageApplied` names its subject `target`, so `about_me` -- which
    reads `ev.actor` and only that -- is false here forever."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _M78_ELEMENTS
    )


@power(
    "m78a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M78_SCALDED,
    on=Trigger(DamageApplied, when=_element_struck_me, text=_M78_SCALDED),
)
def m78a3(c: Cast) -> None:
    """Resist to the one type that just arrived, read off the event rather
    than chosen: the printed line says "the triggering damage type". A free
    action resolves after the blow, so the first hit of that type is taken in
    full and every later one is not."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(10, dtype, until=When.ENCOUNTER)
