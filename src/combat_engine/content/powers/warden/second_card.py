"""Warden: the attack printed beside each guardian form.

Every row here is the second stat block on a form's card -- the one swing
the form unlocks, gated on being in it. `in_form` is that gate: it reads
the stance `assume` leaves on the warden. `p11075` is the single exception,
because its parent lays an aura and an aura's hold sits on the zone entity
rather than on the warden, so a gate of its own is written below.

Three of these open "Effect: before the attack, you shift/move your speed".
The engine chooses targets before the body runs, so the move happens where
the card prints it but cannot widen what the row may be aimed at.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.query import adjacent, distance_between, team
from combat_engine.engine.query import squares as squares_of

from . import in_form

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
FORM_WEAPON = [Keyword.PRIMAL, Keyword.POLYMORPH, Keyword.WEAPON]


def _lasts_with(c: Cast, hold: Effect, watcher: Effect) -> None:
    """Tie a watcher to the hold it enforces, so one saving throw ends the
    whole of a printed "while the target is ... (save ends)" sentence."""
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the hold ended"))


def _step_beside(c: Cast, who: int) -> bool:
    """Shift into a free square next to somebody, nearest one first."""
    body = squares_of(c.world, who)
    for sq in sorted(spread(body, 1) - body, key=lambda s: (distance(s, c.here), s)):
        if c.shift(to=sq):
            return True
    return False


_AT_MY_ALLY = "an enemy adjacent to you makes an attack roll against your ally"


def _swings_at_my_ally(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if who is None or victim is None or who == me or victim == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if team(world, victim) is not team(world, me):
        return False
    return adjacent(world, me, who)


_IN_REACH_AT_MY_ALLY = "an enemy within your reach makes a melee attack against your ally"


def _reach_of(world: World, eid: int) -> int:
    """How far this creature's melee arm goes. The form that wants it adds
    a square, and the printed trigger is measured against the total."""
    mods = world.get(eid, Mods)
    return max(1, 1 + (mods.total("reach", {}) if mods is not None else 0))


def _melee_in_reach_at_my_ally(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if who is None or victim is None or who == me or victim == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if team(world, victim) is not team(world, me):
        return False
    if distance_between(world, me, who) > _reach_of(world, me):
        return False
    return by_melee(world, me, ev)


# -- level 1 ----------------------------------------------------------------


@power(
    "p11072b",
    level=1,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=in_form("p11072"),
    requires_text="the p11072 power must be active",
)
def p11072b(c: Cast) -> None:
    """The burn and the daze are one hold, so one save ends both, and the
    ring of heat is armed against that hold rather than on a clock of its
    own -- "while a target is dazed **by this effect**".

    "Your Constitution modifier or your Wisdom modifier" is the warden's
    choice, so: the better of the two, as `p11075` already reads it.
    """
    if c.strike():
        c.damage(c.w(), c.str_mod)
    victim = c.target
    hold = c.condition(
        Condition.DAZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.FIRE)
    )
    heat = max(c.con_mod, c.wis_mod)
    if victim is None or hold is None or heat <= 0:
        return

    def singe(ev: TurnStart) -> None:
        if ev.actor in (c.me, victim) or team(c.world, ev.actor) is team(c.world, c.me):
            return
        if c.adjacent_to(victim, ev.actor):
            c.flat(heat, dtype=DamageType.FIRE, on=ev.actor)

    _lasts_with(c, hold, c.watch(TurnStart, singe, until=When.ENCOUNTER))


@power(
    "p5103b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=in_form("p5103"),
    requires_text="the p5103 power must be active",
)
def p5103b(c: Cast) -> None:
    """"You then shift into a space that must be adjacent to the target"
    names the constraint and no distance, so the shift is aimed rather than
    measured; on a miss the square the shove emptied is the instruction."""
    victim = c.target
    if victim is None:
        return
    c.shift(c.speed_of())
    was = c.there
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(3)
        c.prone()
        _step_beside(c, victim)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.push(1)
        c.shift(to=was)


@power(
    "p5104b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=in_form("p5104"),
    requires_text="the p5104 power must be active",
)
def p5104b(c: Cast) -> None:
    c.shift(c.speed_of())
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.ongoing(2)


@power(
    "p5105b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=in_form("p5105"),
    requires_text="the p5105 power must be active",
    trigger=_AT_MY_ALLY,
    on=Trigger(AttackDeclared, _swings_at_my_ally, _AT_MY_ALLY),
)
def p5105b(c: Cast) -> None:
    """The penalty is `once=True`: an interrupt resolves before the die is
    rolled, so the next roll that enemy makes is the triggering one."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.penalty("attack", 4, once=True)
    else:
        c.half_damage(c.w(), c.str_mod)
        c.penalty("attack", 2, once=True)


@power(
    "p5106b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.COLD, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=in_form("p5106"),
    requires_text="the p5106 power must be active",
)
def p5106b(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.EONT)


@power(
    "p5532b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.PRIMAL, Keyword.POISON, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=in_form("p5532"),
    requires_text="the p5532 power must be active",
)
def p5532b(c: Cast) -> None:
    """"Save ends both" is one hold carrying the slow and the burn: applied
    separately they would be two saving throws."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.POISON)
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
        )
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.POISON)
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(2, DamageType.POISON)
        )


@power(
    "p5575b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=in_form("p5575"),
    requires_text="the p5575 power must be active",
)
def p5575b(c: Cast) -> None:
    """"1[W] extra damage" against a target already held up is a third die
    in the one call, so a critical maxes all of it rather than some."""
    pinned = any(
        c.is_(cond)
        for cond in (
            Condition.DAZED,
            Condition.IMMOBILIZED,
            Condition.SLOWED,
            Condition.STUNNED,
        )
    )
    if c.strike():
        c.damage(c.w(3 if pinned else 2), c.str_mod)
        c.grab()
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p5576b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="One bloodied creature"),
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=in_form("p5576"),
    requires_text="the p5576 power must be active",
)
def p5576b(c: Cast) -> None:
    """A header filters by side and not by state, so "one bloodied
    creature" is printed on the card and not enforced."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(), c.str_mod)


@power(
    "p9822b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=in_form("p9822"),
    requires_text="the p9822 power must be active",
)
def p9822b(c: Cast) -> None:
    """"Can't gain concealment or total concealment" is a penalty to the
    concealment the target carries, not `c.no_cover`: that would also strip
    the cover the printed line says nothing about. 5 is what total
    concealment is worth, so the total can never come out above zero."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    c.penalty("concealment", 5, until=When.SAVE_ENDS)


@power(
    "p9825b",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[
        Keyword.PRIMAL,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
        Keyword.POLYMORPH,
        Keyword.WEAPON,
    ],
    attack=Attack(STR, vs=REF),
    requires=in_form("p9825"),
    requires_text="the p9825 power must be active",
)
def p9825b(c: Cast) -> None:
    """The Effect is one payout for the whole burst, so it goes on the
    first target; "each enemy you can see" is the guard after it."""
    if c.first and c.str_mod > 0:
        for foe in c.enemies():
            if c.marked(foe):
                c.flat(c.str_mod, dtype=DamageType.LIGHTNING, on=foe)
    if not c.can_see():
        return
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.THUNDER)
        c.prone()
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.THUNDER)


# -- level 5 ----------------------------------------------------------------


def _grit_up(world: World, eid: int) -> bool:
    """"Requirement: the p11075 power must be active."

    That parent lays an aura rather than a stance, and an aura's hold sits
    on the zone entity, so `in_form` -- which reads the warden's own
    effects -- is false for it forever.
    """
    return any(
        z.aura and z.owner == eid and z.label == "p11075" for _zid, z in world.zones.all()
    )


def _gore(c: Cast, who: int | None) -> None:
    """One swing of p11075b, wherever the victim came from."""
    if who is None or not c.strike(on=who):
        return
    c.damage(c.w(2), c.str_mod, on=who)
    # One effect, not four calls to `c.penalty`: "save ends" on a line
    # naming all the defences is one saving throw.
    c.world.effects.apply(
        who,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[
            (who, Mod(what=d.value, value=-2, kind="untyped", label=c.ref))
            for d in (AC, FORT, REF, WILL)
        ],
    )


@power(
    "p11075b",
    level=5,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=Target(
        "enemy", 99, everyone=True,
        label="Each enemy in the blast and each enemy adjacent to you",
    ),
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=3),
    requires=_grit_up,
    requires_text="the p11075 power must be active",
)
def p11075b(c: Cast) -> None:
    """The second half of the target line -- "and each enemy adjacent to
    you" -- falls outside the blast, and a header carries one area, so
    those swings are made here. `c.add_target` cannot serve: it appends to
    the power a row is nested *inside*, and this one is on top.

    That does mean a blast catching nobody never reaches the adjacent
    enemies either, because a row with no targets has no body call.
    """
    if c.first:
        grit = c.my_aura("p11075")
        if grit:
            c.dispel(grit)
        beside = sorted(f for f in c.enemies() if f not in c.targets and c.adjacent(f))
        for foe in beside:
            _gore(c, foe)
    _gore(c, c.target)


# -- level 9 ----------------------------------------------------------------


@power(
    "p11078b",
    level=9,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=FORT),
    requires=in_form("p11078"),
    requires_text="the p11078 power must be active",
)
def p11078b(c: Cast) -> None:
    """The Effect is a hold with no condition in it -- only the bad saving
    throw the last sentence prints -- and a watcher tied to it, so one save
    ends the whole line. "As a free action" costs the warden nothing the
    engine bills for, the slide being the warden's own."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    victim = c.target
    hold = c.condition(until=When.SAVE_ENDS, save_mod=-2)
    if victim is None or hold is None:
        return

    def recoil(ev: DamageApplied) -> None:
        if ev.source != victim or team(c.world, ev.target) is not team(c.world, c.me):
            return
        blow = get(ev.detail)
        if blow is None or blow.attack is None:
            return
        c.flat(5, dtype=DamageType.THUNDER, on=victim)
        c.slide(1, on=victim)

    _lasts_with(c, hold, c.watch(DamageApplied, recoil, until=When.ENCOUNTER))


@power(
    "p5126b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=in_form("p5126"),
    requires_text="the p5126 power must be active",
    trigger=_IN_REACH_AT_MY_ALLY,
    on=Trigger(AttackDeclared, _melee_in_reach_at_my_ally, _IN_REACH_AT_MY_ALLY),
)
def p5126b(c: Cast) -> None:
    """Taking the blow is an Effect line, so it happens whether the swing
    lands or not; the interrupt resolves before the attack it answers, so
    moving that attack's target is the whole of it."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    c.redirect(to=c.me)


@power(
    "p5127b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=in_form("p5127"),
    requires_text="the p5127 power must be active",
)
def p5127b(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(), c.str_mod)
        c.ongoing(2)


@power(
    "p5128b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=in_form("p5128"),
    requires_text="the p5128 power must be active",
)
def p5128b(c: Cast) -> None:
    """"You **can** spend a healing surge" is an offer, and the surge is
    the warden's own, so both halves are named."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


@power(
    "p5129b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.LIGHTNING, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=in_form("p5129"),
    requires_text="the p5129 power must be active",
)
def p5129b(c: Cast) -> None:
    c.move(c.speed_of())
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
        c.dazed(until=When.EONT)


@power(
    "p5579b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=REF),
    requires=in_form("p5579"),
    requires_text="the p5579 power must be active",
)
def p5579b(c: Cast) -> None:
    """No Miss line, and the burn is an Effect: it lands whether the swing
    did or not."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    c.ongoing(10, DamageType.FIRE)


@power(
    "p9855b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=in_form("p9855"),
    requires_text="the p9855 power must be active",
)
def p9855b(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.str_mod)
        c.blinded(until=When.EONT)


@power(
    "p9858b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=in_form("p9858"),
    requires_text="the p9858 power must be active",
)
def p9858b(c: Cast) -> None:
    """"If the target is bloodied" is asked after the damage, which is the
    order the card prints it in and the only reading under which a swing
    that bloodies its victim pays out."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if c.bloodied():
            c.ongoing(5 + c.wis_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
        if c.bloodied() and c.wis_mod > 0:
            c.ongoing(c.wis_mod)


@power(
    "p9859b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.POLYMORPH, Keyword.WEAPON],
    attack=Attack(STR, vs=FORT),
    requires=in_form("p9859"),
    requires_text="the p9859 power must be active",
)
def p9859b(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS)
        c.damage(c.w(), c.str_mod)
    else:
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.EONT)
        c.half_damage(c.w(), c.str_mod)


@power(
    "p9860b",
    level=9,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=FORM_WEAPON,
    attack=Attack(STR, vs=FORT, plus=2),
    requires=in_form("p9860"),
    requires_text="the p9860 power must be active",
)
def p9860b(c: Cast) -> None:
    """No Miss line. The square to shift into is read before the slide,
    because afterwards there is nothing left to say which one it was."""
    was = c.there
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slide(2)
        c.prone()
        c.shift(to=was)
