"""Warlord, level 3: the encounter attacks the later books added.

`level_3.py` holds the first four; these are the rest. Four notes apply
across the batch.

**Somebody else swings.** `c.grant_attack` hands over the blow itself and
reports that a row went off rather than that it connected, so a rider that
reads "if the ally's attack hits" watches `Hit` around it -- `_granted_hit`
below.

**The presences.** `chargen` knows two warlord builds, `inspiring` and
`tactical`, so a rider keyed to any of the others has no fork to read and
those rows are the printed base line only, the reading `level_1_b.py` took.

**A power that is not expended** is `Powers.unuse`, the counter `usable`
reads -- the same door the reliable keyword goes through in `dsl.use`. It
works on somebody else's counter as readily as on your own.

**"Ranged weapon"** is `Ranged(20)`, and the warlord's chassis carries a
longsword and nothing to fire, so `can_branch` refuses such a row on the
audit board. It is written for the warlord who owns a crossbow.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    Event,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    OpportunityWindow,
    Powers,
    PowerUsed,
    Ranged,
    Relation,
    Trigger,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.events import DamageRolled, MoveEnd
from combat_engine.engine.query import adjacent, enemies, flanked_by, hidden_from, team

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

#: The warlord's level-0 healing row, which one of these rows riders off.
WARLORD_HEAL = "p1590"


def _friends_within(c: Cast, squares: int) -> list[int]:
    """Allies in range -- "an ally", so never the warlord itself."""
    return [a for a in c.within(squares, side="ally") if a != c.me]


def _beside(c: Cast, thing: int) -> list[int]:
    """Allies standing next to something, sorted so a headless fight is
    deterministic."""
    return sorted(a for a in c.allies() if adjacent(c.world, a, thing))


def _granted_hit(c: Cast, who: int, foe: int, **kw: Any) -> bool:
    """Did the swing somebody else was handed land? `c.grant_attack` reports
    that a row went off, not that it connected."""
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == who and ev.target == foe:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        c.grant_attack(who, on=foe, **kw)
    finally:
        c.world.bus.off(sub)
    return bool(landed)


@power(
    "p10122",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10122(c: Cast) -> None:
    """The ally takes the square the enemy was standing in, so the slide
    names its destination outright rather than leaving it to the decider --
    which would happily have slid the ally three squares the other way."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    foe = c.target
    vacated = c.there
    c.slide(1, on=foe)
    pool = _beside(c, c.me)
    friend = c.choose(pool, "who takes its place") if pool else None
    if friend is None:
        return
    c.slide(3, on=friend, to=vacated)
    c.grant_attack(friend, on=foe)


@power(
    "p10123",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10123(c: Cast) -> None:
    """The standing half rides on the warlord's own level-0 heal, which
    announces itself as a `PowerUsed` naming the ally it was aimed at.

    Three squares of walking beats one of shifting often enough to be the
    first option, and a headless fight takes the first option.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        pool = sorted(a for a in c.allies() if c.can_see(a))
        friend = c.choose(pool, "who gets moving") if pool else None
        if friend is not None:
            _step_or_run(c, friend, 3)

    def onward(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != WARLORD_HEAL:
            return
        for who in ev.targets:
            _step_or_run(c, who, c.int_mod)

    c.watch(PowerUsed, onward, until=When.EONT, on=c.me, label=c.ref)


def _step_or_run(c: Cast, who: int, squares: int) -> None:
    """"Shift 1 square or move N squares as a free action" -- offered, since
    both halves of the printed line are a **can**."""
    if squares > 1 and c.choose(
        [f"move {squares} squares", "shift a square"], "how it moves"
    ) != "shift a square":
        c.move(squares, who=who)
    elif c.may("shift a square", who=who):
        c.shift(1, who=who)


@power(
    "p10920",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p10920(c: Cast) -> None:
    """No damage line at all on the hit -- it knocks the target down and
    nothing else -- and the Effect lands whether or not the swing did."""
    if c.strike():
        c.prone()
    foe = c.target
    if foe is None:
        return
    pool = _beside(c, foe)
    friend = c.choose(pool, "who swings at it") if pool else None
    if friend is not None:
        c.grant_attack(friend, on=foe)


@power(
    "p10921",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10921(c: Cast) -> None:
    """`c.no_provoke` covers the caster and only the caster, and the printed
    line covers the allies standing next to the target as well -- so the veto
    is written once, over both, and asks about adjacency at the moment the
    window opens rather than now.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.actor != foe:
            return
        if ev.provoker == me or (
            ev.provoker in c.allies() and adjacent(c.world, ev.provoker, foe)
        ):
            ev.cancel(c.ref)

    c.watch(
        OpportunityWindow,
        veto,
        until=When.EONT,
        window=Window.BEFORE,
        on=me,
        label=f"{c.ref} no provoke",
    )


@power(
    "p10922",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10922(c: Cast) -> None:
    """The ally's choice, so the ally is asked. The Effect line lands whether
    or not the swing did."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    pool = _beside(c, c.me)
    friend = c.choose(pool, "who takes heart") if pool else None
    if friend is None:
        return
    if c.choose(["hit harder", "temporary hit points"], "which") == "hit harder":
        c.bonus("damage", c.int_mod, on=friend, until=When.EONT)
    else:
        c.temp_hp(c.cha_mod, on=friend)


_ALLY_MISSED = "an ally misses with an encounter or a daily attack"


def _ally_missed_outright(world: World, me: int, ev: Miss) -> bool:
    """An ally's limited attack came to nothing.

    "Misses **every** target" is not readable off one `Miss` -- the event
    names one target and nothing carries the tally for the rest -- so what
    is declared is the miss itself, which is the whole of the printed line
    for the single-target attacks it is nearly always answering.
    """
    who = getattr(ev, "attacker", None)
    if who is None or who == me or team(world, who) is not team(world, me):
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.usage in (Usage.ENCOUNTER, Usage.DAILY)


@power(
    "p10923",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_ALLY_MISSED,
    on=Trigger(Miss, when=_ally_missed_outright, text=_ALLY_MISSED),
)
def p10923(c: Cast) -> None:
    """The creature the ally swung at is read off the event: the dispatcher
    re-aims at whoever an event was *about*, which here is the ally, and an
    ally is not in an enemy-side pool -- so it falls back to auto-targeting
    and may pick a different enemy entirely.
    """
    foe = getattr(c.trigger, "target", None)
    if foe is None or foe not in c.enemies() or not c.adjacent(foe):
        foe = c.target
    if foe is None or not c.strike(on=foe):
        return
    c.damage(c.w(2), c.str_mod, on=foe)
    friend = getattr(c.trigger, "attacker", None)
    spent = getattr(c.trigger, "power", "")
    known = c.world.get(friend, Powers) if friend is not None else None
    if known is not None and spent:
        known.unuse(spent)


@power(
    "p10924",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
)
def p10924(c: Cast) -> None:
    """"After the move" is `MoveEnd`, not `MoveStart`, which fires before a
    step has been taken; "the first time" is the hold spending itself; and
    "during its next turn" is the hold's own duration plus a check that the
    turn in progress is the target's, since a forced slide on somebody
    else's turn is not the target moving.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target

    def trip(ev: MoveEnd) -> None:
        if ev.actor == foe and c.world.turn == foe:
            c.prone(on=foe)

    c.watch(MoveEnd, trip, until=When.EOTNT, on=foe, once=True, label=c.ref)


@power(
    "p11606",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11606(c: Cast) -> None:
    """The answer is an interrupt, so it is armed in `Window.BEFORE` of the
    target's declaration: the ally swings and the penalty lands while the
    roll is still to come. Armed in the *after* window both would have
    arrived a beat late, and the penalty would have hung over the next
    attack rather than this one.

    "Does not include you as a target" reads `among`, which is everybody the
    one power use is aimed at -- `ev.target` alone is one creature of a
    burst, and a burst that catches the warlord is not the printed sentence.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    me = c.me
    c.mark(until=When.EONT)

    def answer(ev: AttackDeclared) -> None:
        if ev.attacker != foe or me in getattr(ev, "among", (ev.target,)):
            return
        pool = _beside(c, foe)
        friend = c.choose(pool, "who answers it") if pool else None
        if friend is None:
            return
        if _granted_hit(c, friend, foe, trigger=ev):
            c.penalty("attack", 2, on=foe, until=When.EOT, once=True)

    c.watch(
        AttackDeclared,
        answer,
        until=When.EONT,
        window=Window.BEFORE,
        on=me,
        once=True,
        label=c.ref,
    )


@power(
    "p11608",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11608(c: Cast) -> None:
    """"Your allies" and not you, so the relations are listed out one per
    ally rather than taken from `to="allies"`, which includes the caster.

    Not written: the Effect line, which pays out on an attack an ally gained
    from an action point. Nothing in the engine has one. See the report.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    friends = c.allies()
    if not friends:
        return
    c.world.effects.apply(
        foe,
        c.me,
        When.EONT,
        label=f"{c.ref} advantage",
        relations=[(Relation.GRANTS_CA_TO, foe, a) for a in friends],
    )


@power(
    "p11722",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11722(c: Cast) -> None:
    """There are no skill checks here, so the Stealth check is the hiding
    itself: `c.invisible` on the ally holds the same `HIDDEN_FROM` relation
    `c.hide` does, and `resolve.attack` breaks it when the ally swings,
    which is when the printed line ends too.

    The damage bonus is gated on the *ally* being hidden from whatever it is
    hitting, asked when the blow lands rather than now -- a creature can see
    it again by then.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    pool = sorted(a for a in c.allies() if c.can_see(a))
    friend = c.choose(pool, "who slips away") if pool else None
    if friend is None:
        return
    c.shift(max(1, c.speed_of(friend) // 2), who=friend)
    c.invisible(on=friend, until=When.ENCOUNTER)
    c.bonus(
        "damage",
        3,
        on=friend,
        until=When.EONT,
        once=True,
        when=lambda ctx: ctx.get("target") in hidden_from(c.world, friend),
    )


@power(
    "p2327",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2327(c: Cast) -> None:
    """The Special line is a note about how the row may be used -- in place
    of a melee basic attack on a charge -- and not a row that charges, so it
    carries no `charges` flag.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    pool = sorted(_friends_within(c, 10))
    friend = c.choose(pool, "who picks up the pace") if pool else None
    if friend is not None:
        c.bonus("speed", 2, on=friend, until=When.EONT)


@power(
    "p2329",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2329(c: Cast) -> None:
    """The printed target is a bloodied creature; a header filters by side
    and not by state, so that much of the line is not enforced."""
    if c.strike():
        c.damage(c.w(2), c.str_mod + c.int_mod)


_OA_HITS_ALLY = "an adjacent enemy hits an ally with an opportunity attack"


def _oa_hits_ally(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    result = getattr(ev, "result", None)
    if who is None or victim is None or victim == me:
        return False
    if not getattr(ev, "opportunity", False) or not (result and result.hit):
        return False
    if team(world, victim) is not team(world, me):
        return False
    return adjacent(world, me, who)


@power(
    "p2538",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_OA_HITS_ALLY,
    on=Trigger(AttackRolled, when=_oa_hits_ally, text=_OA_HITS_ALLY),
)
def p2538(c: Cast) -> None:
    """"The opportunity attack hits you instead" is the damage moving, not
    the attack being re-rolled: `c.redirect` only works before the die, and
    the printed trigger is the blow having already landed. So the blow is
    taken off the ally as it is dealt, which is what `c.absorb` is for.
    """
    ev = c.trigger
    friend = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None) or c.target
    if friend is None or foe is None:
        return

    def take_it(hurt: DamageRolled) -> None:
        if hurt.target == friend and hurt.source == foe:
            c.absorb(hurt)

    c.watch(
        DamageRolled,
        take_it,
        until=When.EOT,
        window=Window.BEFORE,
        on=c.me,
        once=True,
        label=f"{c.ref} in the way",
    )
    if c.strike(on=foe):
        c.damage(c.w(2), c.str_mod, on=foe)
        c.shift(2, who=friend)


@power(
    "p2539",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires_text="needs a charge",
    charges=True,
)
def p2539(c: Cast) -> None:
    """A row whose printed Requirement *is* the charge.

    `c.charge_at` reaches its swing through `use`, which refuses to re-enter
    a row already in flight, so the flag goes up by hand and `c.run_at`
    walks -- the shape `fighter/level_1_c.py` settled on.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    c.charge = True
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.prone()
    else:
        c.grants_advantage(on=c.me, to=victim, until=When.SONT)


def _flanked(world: World, eid: int) -> bool:
    """"You must be flanked": somebody has you between two of them."""
    return any(flanked_by(world, eid, foe) for foe in enemies(world, eid))


@power(
    "p4555",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_flanked,
    requires_text="you must be flanked",
)
def p4555(c: Cast) -> None:
    """Every enemy standing next to the warlord opens up, and to a named set
    of allies rather than to the whole side -- so it is one hold per enemy
    carrying one relation per ally."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    friends = _friends_within(c, 5)
    if not friends:
        return
    for foe in c.within(1, side="enemy"):
        c.world.effects.apply(
            foe,
            c.me,
            When.EONT,
            label=f"{c.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, foe, a) for a in friends],
        )
