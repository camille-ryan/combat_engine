"""Ranger, level 1, beyond the first book: the first half.

Three shapes recur here and are worth setting out once.

**The beast companion is not in this engine.** There is no entity for it, no
`[B]` die and no attack bonus of its own, so a row whose *attack* is the
beast's is absent rather than approximated. Where the companion is only a
rider on a swing the ranger makes -- "your beast can shift 1 square", "extra
damage if your companion is a cat" -- the row is written and the rider is
dropped, noted on the row itself.

**A thrown weapon** has no flag on `Weapon`, and neither ranger build holds
one. A row printing "Ranged weapon (thrown weapon)" is declared as a ranged
reach with `thrown_by_hand=True`, which is the header field that makes the
ranged gate ask for a melee weapon in hand instead of a bow, and its damage
rolls `c.w(..., ranged=False)` so the blade in the hand is what is thrown.

**"Before the attack, you move"** on a melee row needs `charges=True` --
not because the swing is a charge, but because the reach test otherwise
measures a sword's length before the run and refuses the row in exactly the
situation it exists for. `charges` is read only by that test; `c.run_at`
covers the ground without marking the swing.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    Attack,
    AttackDeclared,
    Cast,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    MoveEnd,
    Powers,
    Ranged,
    Target,
    TurnStart,
    UpTo,
    When,
    World,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.events import EnterSquare
from combat_engine.engine.query import alive
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_QUARRY = Target("enemy", 1, label="One creature designated as your quarry")


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _melee_in_hand(world: World, eid: int) -> bool:
    """"You must be wielding both a thrown weapon and a melee weapon."

    A thrown weapon is a melee weapon that leaves the hand, and nothing on
    `Weapon` distinguishes one, so the half that can be checked is checked.
    """
    gear = world.get(eid, Gear)
    return gear is not None and bool(gear.melee)


def _step_beside(c: Cast, who: int, squares_: int) -> None:
    """Aim a shift at a square next to `who`, for the swing that follows.

    The world's shift decider knows nothing about the attack coming after it
    and will happily step out of reach of it. Copied from `level_5.py`,
    which is where this first had to be written.
    """
    beside = squares_of(c.world, who)
    steps = [
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if any(distance(s, f) <= 1 for f in beside)
    ]
    if steps:
        c.shift(squares_, to=steps[0])


def _step_off(c: Cast, foe: int | None, squares_: int) -> None:
    """Shift, ending somewhere not adjacent to `foe`."""
    if foe is None:
        c.shift(squares_)
        return
    held = squares_of(c.world, foe)
    away = sorted(
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if not any(distance(s, at) <= 1 for at in held)
    )
    if away:
        c.shift(squares_, to=away[0])


def _melee_power(ctx: dict[str, Any]) -> bool:
    """Was the damage being rolled dealt by a melee row?

    The damage context carries `power` and no branch, so a dual-range row
    answers by its printed reach -- "melee" for both halves. The alternative
    is a gate on a key that is not there, which is silently false.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach.kind == "melee"


def _unexpend(c: Cast) -> None:
    """"This power is not expended." `use` counts the use before the body."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.unuse(c.ref)


@power(
    "p10591",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10591(c: Cast) -> None:
    """Both branches roll Dexterity, so there is no second attack line to
    declare -- `attack_alt` is for a row whose two halves differ."""
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        _step_off(c, victim, 2)


@power(
    "p10592",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10592(c: Cast) -> None:
    """The Special line -- usable in place of a melee basic when charging --
    is a property of the charge action, not of this body."""
    if c.strike():
        c.damage(c.w(1), c.str_mod + c.wis_mod)


@power(
    "p10593",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
    requires=_melee_in_hand,
)
def p10593(c: Cast) -> None:
    """No `requires_text`: `chargen.build_for` looks for the word
    "requirement" in a refusal to decide which build can hold a row, and a
    custom message hides it."""
    primary = c.target
    if c.strike():
        c.damage(c.w(1, ranged=False))
    c.move(c.speed_of(c.me))
    pool = [f for f in c.within(1, side="enemy") if f != primary]
    other = c.choose(pool, "p10593: who the follow-up catches") if pool else None
    if other is not None:
        c.basic(on=other)


@power(
    "p10595",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p10595(c: Cast) -> None:
    if c.target is not None and not c.adjacent():
        _step_beside(c, c.target, 2)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed()


@power(
    "p10596",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
    charges=True,
    requires=_melee_in_hand,
)
def p10596(c: Cast) -> None:
    """Throw, then run in after it. `charges=True` is what lets the row be
    offered at throwing distance rather than at sword's length."""
    victim = c.target
    if victim is None:
        return
    c.quarry(on=victim)
    if c.strike():
        c.damage(c.w(1, ranged=False), c.str_mod)
    c.charge_at(victim)


@power(
    "p10597",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=2),
    charges=True,
)
def p10597(c: Cast) -> None:
    """The printed exemption is the *first* square only; `c.no_provoke`
    closes every opening for the whole walk, which is the reading
    `level_5.py` settled on and is a square too generous."""
    victim = c.target
    if victim is not None and not c.adjacent():
        for foe in c.enemies():
            c.no_provoke(from_=foe, until=When.EOT)
        c.run_at(victim)
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p10598",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10598(c: Cast) -> None:
    if c.first:
        c.move(c.speed_of(c.me))
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p10599",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=_QUARRY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10599(c: Cast) -> None:
    """"Until the target is no longer your quarry" is the rest of the fight:
    nothing releases a quarry short of the encounter ending."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)
    c.bonus(
        "damage",
        2 + c.wis_mod,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim and _melee_power(ctx),
    )


@power(
    "p10600",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10600(c: Cast) -> None:
    """The secondary attack is the beast companion's and is not written.
    The primary, and the refund for felling with it, are."""
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        if victim is not None and not alive(c.world, victim):
            _unexpend(c)
    else:
        c.half_damage(c.w(1), c.str_mod)


@power(
    "p10601",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10601(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if not c.is_quarry() and c.may("push it"):
            c.push(max(0, c.wis_mod))
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p10602",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10602(c: Cast) -> None:
    """"Strength or Dexterity" is fixed when the power is taken and a header
    holds one ability, so this is the Strength half. The opening shift is
    aimed at the target rather than handed to the decider, which would as
    soon step out of reach of the swing that follows."""
    if c.first and c.target is not None and not c.adjacent():
        _step_beside(c, c.target, 2)
    for _ in range(2):
        if c.strike():
            c.damage(c.w(1))
            c.prone()
        else:
            c.half_damage(c.w(1))


@power(
    "p10603",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10603(c: Cast) -> None:
    """The 1d8 is rolled when the stance pays out rather than when the blow
    lands: `c.bonus` carries a number, not an expression.

    The two watchers are held for the encounter and ended by hand when the
    stance ends -- a second stance-clocked effect confuses
    `Effects.stance_of`, which is the arrangement `fighter/level_6.py`
    settled on.
    """
    stance = c.stance(label=c.ref)
    mine = c.me
    origin = [c.here]

    def remember(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == mine:
            origin[0] = c.here

    def reward(ev: Any) -> None:
        if ev.actor != mine or distance(origin[0], c.here) < 4:
            return
        c.bonus(AC, 2, on=mine, until=When.SONT)
        c.bonus(REF, 2, on=mine, until=When.SONT)
        c.bonus("damage", c.roll("1d8"), on=mine, until=When.EONT, once=True)

    for event, fn in ((TurnStart, remember), (MoveEnd, reward)):
        held = c.watch(event, fn, until=When.ENCOUNTER, on=mine)
        stance.on_end.append(
            lambda eff=held: c.world.effects.end(eff, "stance ended")
        )


@power(
    "p10696",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10696(c: Cast) -> None:
    """The watched square is chosen, the second shot is taken longhand: it
    is a different attack line -- no ability modifier on its damage -- so
    `c.strike` would roll the header's."""
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod)
    victim = c.target
    if victim is None:
        return
    spots = sorted(spread(squares_of(c.world, victim), 1))
    spot = c.choose(spots, "p10696: which square is watched")
    if spot is None:
        return
    mine, dex = c.me, c.dex_

    def stepped(ev: EnterSquare) -> None:
        if ev.actor == mine or ev.square != spot:
            return
        if c.attack(dex, AC, on=ev.actor):
            c.damage(c.w(1), on=ev.actor)

    c.watch(EnterSquare, stepped, until=When.SONT, on=mine, once=True)


@power(
    "p10697",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10697(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed()


@power(
    "p10698",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10698(c: Cast) -> None:
    """The standing offer is a watcher rather than a declared trigger: it is
    armed by this row and only against one named pair, which `on=` -- a
    property of the row for the whole fight -- cannot say."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)
    if victim is None:
        return
    friends = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    ward = c.choose(friends, "p10698: which ally is watched") if friends else None
    if ward is None:
        return

    def answer(ev: AttackDeclared) -> None:
        if ev.attacker != victim or ev.target != ward:
            return
        if c.marked(on=victim, by=ward):
            return
        c.basic(on=victim, ranged=True)

    c.watch(AttackDeclared, answer, until=When.ENCOUNTER, on=c.me)
