"""Fighter, level 9: the dailies the later books added.

Two shapes worth saying once.

**"Vulnerable 10 to weapon attacks"** is not `c.vulnerable`, which takes a
damage type: the sentence names a *keyword*, so the extra is added on
`DamageRolled` after asking the registry what the row that dealt it was.

**A hold that lasts "until the grab ends"** hangs on the grab's own effect
rather than on a clock, so one thing ends both.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Keyword,
    Melee,
    MoveEnd,
    Powers,
    Relation,
    Trigger,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared, DamageRolled
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of

from .grips import hand_free, has_shield, heavy_rider, two_handed, two_melee

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL = [Keyword.MARTIAL]


def _came_alongside(world: World, me: int, ev: Any) -> bool:
    """"An enemy moves during its turn to a square adjacent to you"."""
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return adjacent(world, me, who)


def _came_within_two(world: World, me: int, ev: Any) -> bool:
    """"An enemy enters a square within 2 squares of you"."""
    from combat_engine.engine.query import distance_between

    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 2


def _my_mark_is_bloodied(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who)


_CAME_ALONGSIDE = "an enemy moves next to you on its turn"
_CAME_WITHIN_TWO = "an enemy steps within two squares of you"
_MY_MARK_IS_BLOODIED = "an enemy you marked becomes bloodied"


@power(
    "p10507",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10507(c: Cast) -> None:
    """The Effect line lands whether the swing did or not."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    hold = c.effect("open to weapons", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def bite(ev: DamageRolled) -> None:
        if ev.target != victim or ev.amount <= 0:
            return
        dealt = get(ev.detail)
        if dealt is not None and Keyword.WEAPON in dealt.keywords:
            ev.amount += 10

    hold.subs.append(
        c.world.bus.on(DamageRolled, bite, window=Window.BEFORE, owner=c.me)
    )


@power(
    "p10508",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10508(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.EONT)


@power(
    "p10509",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10509(c: Cast) -> None:
    """Both halves are gates asked when the modifier is read, not now: which
    creatures are standing where changes, and a count taken at this moment
    would freeze it."""
    if c.can_see() and c.strike():
        c.damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me

    def hard_pressed(_ctx: dict[str, Any]) -> bool:
        return len(c.within(1, of=me, side="enemy")) >= 2

    def alone(ctx: dict[str, Any]) -> bool:
        if any(a != me for a in c.within(1, of=me, side="ally")):
            return False
        wielded = get(ctx.get("power", "") or "")
        return wielded is not None and Keyword.WEAPON in wielded.keywords

    for guard in (AC, FORT, REF, WILL):
        c.bonus(guard, 1, on=me, until=When.ENCOUNTER, when=hard_pressed)
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=alone)


@power(
    "p10510",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10510(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.push(3)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod)
        c.push(1)
        c.dazed(until=When.EONT)


@power(
    "p10511",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
    trigger=_CAME_ALONGSIDE,
    on=Trigger(MoveEnd, _came_alongside, _CAME_ALONGSIDE),
)
def p10511(c: Cast) -> None:
    """"Cannot grab you or restrain you" is refused where those conditions
    are applied; entering the fighter's space is something the grid already
    forbids, so only the first half needs writing."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    me = c.me

    def shrug_off(ev: ConditionApplied) -> None:
        if ev.target != me or ev.source != victim:
            return
        if ev.condition not in (Condition.GRABBED, Condition.RESTRAINED):
            return
        for effect in list(c.world.effects.of(me)):
            if ev.condition in effect.conditions and effect.source == victim:
                c.world.effects.end(effect, c.ref)

    c.watch(ConditionApplied, shrug_off, until=When.EONT, on=me, label=f"{c.ref} braced")


@power(
    "p12197",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=6),
    requires=has_shield,
    requires_text="needs a shield",
)
def p12197(c: Cast) -> None:
    """The printed Target narrows to a creature that is prone, against
    blocking terrain, or beside an ally, which the header cannot hold; see
    the report. The Special line about charging is the same gap.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage("2d10", c.str_mod)
        c.slide(1)
        return
    c.damage("2d10", c.str_mod)
    held = c.grab()
    if held is None:
        return
    me = c.me

    def squeeze(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim and not held.ended:
            c.flat(c.str_mod, on=victim)

    held.subs.append(c.world.bus.on(TurnStart, squeeze, owner=me))


@power(
    "p12852",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=REF),
)
def p12852(c: Cast) -> None:
    """One effect carrying both penalties, so one saving throw ends both."""
    if not c.strike():
        return
    c.damage(c.w(3), c.str_mod)
    hold = c.effect("guard broken", until=When.SAVE_ENDS)
    victim = c.target
    if hold is None or victim is None:
        return
    for guard in (AC, REF):
        rider = c.penalty(guard, 2, on=victim, until=When.ENCOUNTER)
        if rider is not None:
            hold.on_end.append(lambda r=rider: c.world.effects.end(r, "saved"))


@power(
    "p16515",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p16515(c: Cast) -> None:
    """"Can score a critical hit on 18-20" is `crit_range`, gated on the
    creature being held and on the swing being a melee one -- the attack
    context carries both."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage(c.w(3), c.str_mod)
        return
    c.damage(c.w(3), c.str_mod)
    held = c.grab()
    if held is None:
        return
    widened = c.bonus(
        "crit_range", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim and not ctx.get("ranged"),
    )
    if widened is not None:
        held.on_end.append(lambda: c.world.effects.end(widened, "the grip opened"))


@power(
    "p2110",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
    trigger=_CAME_WITHIN_TWO,
    on=Trigger(MoveEnd, _came_within_two, _CAME_WITHIN_TWO),
)
def p2110(c: Cast) -> None:
    """The step comes before the swing, which is what brings a creature two
    squares out into reach.

    The Special line -- a charging target may swing at the fighter instead of
    whoever it was running at -- redirects somebody else's attack that has
    not been declared yet, and there is nothing to point `c.redirect` at.
    See the report.
    """
    victim = c.target
    if victim is None:
        return
    if not c.adjacent(victim):
        c.shift(2, to=_step_toward(c, victim))
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.immobilized(until=When.SONT)


def _step_toward(c: Cast, victim: int) -> Any:
    """The nearest square within two steps that touches the target."""
    beside = spread(squares_of(c.world, victim), 1)
    options = sorted(sq for sq in c.world.reachable_squares(c.me, 2) if sq in beside)
    return options[0] if options else None


@power(
    "p2121",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2121(c: Cast) -> None:
    """Whether it attacked the fighter is watched over its whole turn and
    answered at the end of it: "does not attack you on its turn" cannot be
    known until the turn is over."""
    victim = c.target
    if victim is None:
        return
    result = c.strike()
    if result:
        c.damage(c.w(3), c.str_mod + (c.dex_mod if result.advantage else 0))
    held = c.mark(until=When.SAVE_ENDS)
    if held is None:
        return
    me = c.me
    swung: dict[str, int] = {}

    def saw(ev: AttackDeclared) -> None:
        if ev.attacker == victim and me in getattr(ev, "among", (ev.target,)):
            swung["round"] = c.world.round

    def at_dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or held.ended:
            return
        if swung.get("round") == c.world.round or not c.may("answer it", who=me):
            return
        if adjacent(c.world, me, victim):
            c.basic(on=victim)
        else:
            c.shift(1, to=_step_toward(c, victim))

    held.subs.append(c.world.bus.on(AttackDeclared, saw, owner=me))
    held.subs.append(c.world.bus.on(TurnEnd, at_dusk, owner=me))


@power(
    "p2187",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2187(c: Cast) -> None:
    """The secondary is a Constitution attack against Will and carries the
    fear keyword, which no header field can say for half a row; it is an
    Effect line, so it goes off whether the first swing landed or not."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod + heavy_rider(c))
    for foe in sorted(c.within(3, of=victim, side="enemy")):
        if c.attack(c.con_, WILL, on=foe):
            c.push(1, on=foe)


@power(
    "p4331",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4331(c: Cast) -> None:
    """`Powers.unuse` gives back exactly one use, which is what the printed
    line says -- `restore` would hand back a row spent twice."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    if not c.first:
        return
    known = c.world.get(c.me, Powers)
    if known is None:
        return
    mine = [
        ref
        for ref in known.known
        if (p := get(ref)) is not None
        and p.cls == "fighter"
        and p.usage is ENCOUNTER
        and p.is_attack
    ]
    if not mine or not all(known.times(ref) for ref in mine):
        return
    again = c.choose(sorted(mine), "which one comes back")
    if again is not None:
        known.unuse(again)
        c.note(f"{c.ref}: {again} is available again")


@power(
    "p4332",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
    trigger=_MY_MARK_IS_BLOODIED,
    on=Trigger(Bloodied, _my_mark_is_bloodied, _MY_MARK_IS_BLOODIED),
)
def p4332(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)


@power(
    "p4333",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p4333(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(3), c.str_mod)
    toll = c.str_mod + (c.con_mod if c.wielding("pick") else 0)

    def costly(ev: MoveEnd) -> None:
        if ev.actor == victim:
            c.flat(toll, on=victim)

    c.watch(MoveEnd, costly, until=When.EONT, on=c.me, once=True, label=f"{c.ref} toll")


@power(
    "p7498",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7498(c: Cast) -> None:
    """"Each creature in the burst" is friend and foe alike, which is what
    makes this one worth thinking about before using."""
    if not c.can_see():
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.ongoing(5)
    else:
        c.half_damage(c.w(1), c.str_mod)


@power(
    "p9367",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p9367(c: Cast) -> None:
    """"If you hit at least once" is read off the log: the body runs once per
    target and a local cannot count across the calls."""
    struck = {c.target}
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.last or not (landed or _any_hit_this_use(c)):
        return
    c.shift(1)
    pool = sorted(e for e in c.within(1, side="enemy") if e not in struck)
    second = c.choose(pool, "who the off-hand catches") if pool else None
    if second is not None and c.attack(c.str_, FORT, on=second):
        c.damage(c.w(1, hand="off"), on=second)
        c.prone(on=second)


def _any_hit_this_use(c: Cast) -> bool:
    """Did this use of this row land on anybody yet?

    The body is called once per target with one `Cast`, so the tally cannot
    live in a local. `use` stamps a `PowerUsed` first and every `Hit` after
    it belongs to this one.
    """
    from combat_engine.engine.events import Hit, PowerUsed

    log = c.world.bus.log
    start = 0
    for i in range(len(log) - 1, -1, -1):
        ev = log[i]
        if isinstance(ev, PowerUsed) and ev.power == c.ref and ev.actor == c.me:
            start = i
            break
    return any(
        isinstance(ev, Hit) and ev.attacker == c.me and ev.power == c.ref
        for ev in log[start:]
    )


@power(
    "p9999",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a two-handed weapon",
)
def p9999(c: Cast) -> None:
    """The charge is at somebody else, and it is a different row from this
    one, so `use` lets `c.charge_at` through."""
    victim = c.target
    result = c.strike()
    if result:
        c.damage(c.w(2), c.str_mod + (c.str_mod if result.advantage else 0))
    others = sorted(e for e in c.enemies() if e != victim)
    another = c.choose(others, "who to run down next") if others else None
    if another is not None:
        c.charge_at(another)
