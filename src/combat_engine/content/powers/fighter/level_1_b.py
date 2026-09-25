"""Fighter, level 1: the rows the later books added, first half.

`level_1.py` holds the Player's Handbook rows; these sit beside it because
forty more would not fit in one file. Nothing else distinguishes them.

Four things recur across the whole fighter batch and are said once here.

**The grips.** "You must be using a shield", "two melee weapons", "a
two-handed weapon", "a hand free" are `requires=` gates and live in
`grips.py`.

**"You can use this power in place of a melee basic attack"** -- when
charging, or when making an opportunity attack -- has no header field.
`Powers.opportunity` exists and nothing sets it, and a charge is built out
of `Powers.basic`. Those rows are written as the standard actions they also
are, and the missing field is in the report.

**A row whose printed Requirement *is* the charge** does carry it:
`charges=True` so the reach is measured after the run, and the body raises
`c.charge` by hand and walks, because `c.charge_at` reaches its swing
through `use` and `use` will not re-enter a row already in flight.

**The Invigorating keyword** has no entry in `Keyword` -- it pays out only
through a feat the engine does not have -- so those rows carry martial and
weapon and nothing else.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Condition,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    Trigger,
    When,
    Window,
    World,
    by_melee,
    get,
    power,
    spread,
)
from combat_engine.engine.events import DamageRolled, Hit, Miss
from combat_engine.engine.query import adjacent, allies, distance_between, team
from combat_engine.engine.query import squares as squares_of

from .footwork import beside_me, ends_when_apart
from .grips import hand_free, has_shield, two_melee
from .holds import grab_until

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL = [Keyword.MARTIAL]


# -- the shapes these books repeat ------------------------------------------


def _ward(c: Cast, against: int, amount: int, *, until: When = When.EONT) -> None:
    """Resist `amount` against one named creature's attacks.

    `c.resist` takes a damage type and not a source, so "resist equal to your
    Constitution modifier against the target's attacks" is shaved off
    `DamageRolled` instead -- the one moment the number exists and has not
    come off anybody yet, which is `p1441`'s arrangement.
    """
    if amount <= 0:
        return
    me = c.me

    def shrug(ev: DamageRolled) -> None:
        if ev.target == me and ev.source == against and ev.amount > 0:
            ev.amount = max(0, ev.amount - amount)

    c.watch(
        DamageRolled, shrug, until=until, window=Window.BEFORE, on=me,
        label=f"{c.ref} ward",
    )


def _against_a_wall(c: Cast, who: int) -> bool:
    """Is that creature standing next to blocking terrain?"""
    theirs = squares_of(c.world, who)
    return any(sq in c.world.grid.blocking for sq in spread(theirs, 1) - theirs)


def _melee_at_me_or_mine(world: World, me: int, ev: object) -> bool:
    """"An enemy adjacent to you hits or misses you or an ally with a melee
    attack" -- the trigger a shield fighter answers."""
    attacker = getattr(ev, "attacker", None)
    struck = getattr(ev, "target", None)
    if attacker is None or struck is None or attacker == me:
        return False
    if team(world, attacker) is team(world, me):
        return False
    if not adjacent(world, me, attacker):
        return False
    if struck != me and struck not in allies(world, me):
        return False
    return by_melee(world, me, ev)


_ADJACENT_SWING = "an enemy next to you hits or misses you or an ally with a melee attack"


# -- at-will ----------------------------------------------------------------


@power(
    "p10331",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
)
def p10331(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    _ward(c, victim, c.con_mod)


@power(
    "p10332",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10332(c: Cast) -> None:
    """The two weapon riders are alternatives rather than a list: one weapon
    is in hand. Sheathing one and drawing another before the attack is a
    change of grip mid-row and has no expression; see the report.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod + (c.con_mod if c.wielding("axe") else 0))
    if c.wielding("heavy blade"):
        c.bonus(
            AC, 1, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("attacker") == victim,
        )


@power(
    "p10470",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10470(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
        grab_until(c, When.EONT)


@power(
    "p10471",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10471(c: Cast) -> None:
    """The secondary is a free hand rather than the weapon, so it rolls
    longhand against Reflex; the header keeps the primary for the card."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1))
    if c.attack(c.str_, REF):
        c.damage(0, (8 if c.level >= 21 else 3) + c.str_mod)


@power(
    "p10472",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10472(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1))
    for foe in sorted(c.within(1, side="enemy")):
        c.mark(on=foe)


@power(
    "p12189",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
)
def p12189(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    c.bonus(
        "attack", 3, on=c.me, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "p12844",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12844(c: Cast) -> None:
    """"An enemy adjacent to you" is any of them, not necessarily the one
    struck, so it is a choice rather than the target."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    near = sorted(c.within(1, side="enemy"))
    if near:
        c.mark(on=c.choose(near, "who is called out"))


# -- encounter --------------------------------------------------------------


@power(
    "p10473",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10473(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod)
    where = beside_me(c, victim)
    if where is not None:
        c.slide(1, to=where)
    grab_until(c, When.EONT)
    c.penalty("attack", c.dex_mod, until=When.EONT)


@power(
    "p10474",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10474(c: Cast) -> None:
    """The secondary is an Effect line, so it swings whether the first
    landed or not."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, "who the second swing catches") if others else None
    if second is not None and c.attack(c.str_, AC, on=second):
        c.damage(c.w(1), c.str_mod, on=second)


@power(
    "p10475",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10475(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    c.penalty("attack", c.dex_mod, until=When.EONT)
    if c.wielding("flail"):
        grab_until(c, When.EONT)


@power(
    "p10476",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p10476(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(0, c.str_mod)
    c.grants_advantage(until=When.EONT)
    if c.attack(c.str_, AC):
        c.damage(c.w(2, hand="off"), c.str_mod)


@power(
    "p10477",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10477(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.prone()


@power(
    "p12190",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=3),
    requires=has_shield,
    requires_text="needs a shield",
    trigger=_ADJACENT_SWING,
    on=(
        Trigger(Hit, _melee_at_me_or_mine, _ADJACENT_SWING),
        Trigger(Miss, _melee_at_me_or_mine, _ADJACENT_SWING),
    ),
)
def p12190(c: Cast) -> None:
    """Hit *or* miss, so both events are declared: half the printed line
    would look finished and answer only the blows that landed."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d10", c.str_mod)
    vacated = c.there
    if c.push(1) and vacated is not None:
        c.shift(2, to=vacated)


@power(
    "p12845",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12845(c: Cast) -> None:
    """The shift comes first: which enemies are adjacent is asked where the
    fighter ends up, not where it swung from."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    c.shift(2)
    for foe in sorted(c.within(1, side="enemy"))[:2]:
        c.mark(on=foe)


# -- daily ------------------------------------------------------------------


@power(
    "p10478",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p10478(c: Cast) -> None:
    """"That target cannot gain combat advantage from flanking you" is held
    on the fighter, because `unflankable` is read with an empty context and
    a gate on who is swinging would be silently false. So it is wider than
    printed -- no enemy flanks the fighter for the duration, not only these
    two -- and the narrowing is in the report.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    c.cannot_be_flanked(on=c.me, until=When.EONT)
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, "who the off-hand catches") if others else None
    if second is not None and c.attack(c.str_, AC, on=second):
        c.damage(c.w(2, hand="off"), c.str_mod, on=second)


@power(
    "p10479",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10479(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage(c.w(2), c.str_mod)
        c.push(1)
        return
    c.damage(c.w(2), c.str_mod)
    vacated = c.there
    if c.push(1) and vacated is not None:
        c.shift(1, to=vacated)
    if c.attack(c.str_, FORT):
        c.damage(c.w(1), c.str_mod)
        c.push(2)
        c.prone()


@power(
    "p10480",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
)
def p10480(c: Cast) -> None:
    """Pinned against something, which the grid knows about: blocking
    terrain is a square on the map rather than a creature."""
    victim = c.target
    if victim is None:
        return
    pinned = c.adjacent(victim) and _against_a_wall(c, victim)
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if pinned:
            ends_when_apart(c, c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS), victim)
    else:
        c.half_damage(c.w(2), c.str_mod)
        if pinned:
            c.immobilized(until=When.EONT)


@power(
    "p10481",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=REF),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10481(c: Cast) -> None:
    """"The target cannot attempt to escape" needs an escape to forbid, and
    the engine has none -- a grab is ended by whatever ends it, never by the
    creature held. The sentence is already true here rather than written.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.grab()


@power(
    "p10482",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10482(c: Cast) -> None:
    """Every melee weapon hit, not only this row's -- so the watcher reads
    the ref off the event and asks the registry what shape it was."""
    me = c.me
    stance = c.stance(label=c.ref)

    def follow(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        p = get(ev.power)
        if p is None or Keyword.WEAPON not in p.keywords:
            return
        pos = c.world.get(ev.target, Position)
        vacated = pos.square if pos is not None else None
        if c.push(1, on=ev.target) and vacated is not None and c.may("step in", who=me):
            c.shift(1, to=vacated)

    held = c.watch(Hit, follow, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p12191",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=3),
    requires=has_shield,
    requires_text="needs a shield",
)
def p12191(c: Cast) -> None:
    if not c.strike():
        c.half_damage("2d10", c.str_mod)
        c.push(1)
    else:
        c.damage("2d10", c.str_mod)
        vacated = c.there
        if c.push(1 + max(0, c.wis_mod)) and vacated is not None:
            c.shift(1, to=vacated)
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, "who the shield catches next") if others else None
    if second is not None and c.attack(c.str_ + 3, FORT, on=second):
        c.damage(0, c.str_mod, on=second)
        c.dazed(until=When.SAVE_ENDS, on=second)


@power(
    "p12846",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12846(c: Cast) -> None:
    """"Willingly moves" is a walk or a shift, which is what `MoveEnd`
    carries in `kind_`; a push is somebody else's doing and does not count.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    me = c.me

    def pounce(ev: MoveEnd) -> None:
        if ev.actor != victim or ev.kind_ not in ("walk", "shift", "run"):
            return
        if not any(
            a != me and distance_between(c.world, a, victim) <= 1
            for a in allies(c.world, me)
        ):
            return
        if not c.may("answer the approach", who=me):
            return
        if adjacent(c.world, me, victim):
            c.basic(on=victim)
        else:
            c.charge_at(victim)

    c.watch(MoveEnd, pounce, until=When.ENCOUNTER, on=me, label=c.ref)
