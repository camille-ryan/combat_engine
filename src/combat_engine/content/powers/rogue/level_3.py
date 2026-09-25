"""Rogue, level 3: the encounter attack powers.

Three of the four want a light blade and reach one square. The fourth
prints "Melee or Ranged weapon" over the rogue's own three weapon groups and
is `MeleeOrRanged`; Dexterity attacks on either branch, so there is no
second attack line, and what differs is the range, the weapon rolled and
whether firing provokes.

One row carries a build rider. The two legs of the rogue's fork are named
`brawny` and `trickster` here, and the Charisma one is the leg that rider
belongs to, so `c.build("trickster")` is what asks for it.

The rows printed in the later books follow below. Several of them carry a
rider for a leg the model does not have -- the Intelligence one -- and
those are the base line only; `level_1_b.py` records the reading.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_CREATURE,
    OPPORTUNITY,
    REACTION,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    World,
    both,
    by_me,
    by_melee,
    by_ranged,
    distance,
    enemy_within,
    power,
    spread,
)
from combat_engine.engine.events import EnterSquare
from combat_engine.engine.query import defence, flanked_by, hidden_from
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


def _sling(world: World, eid: int) -> bool:
    """A sling is fired, so it is `gear.ranged` rather than `gear.main`."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return any(w.group == "sling" for w in (gear.main, gear.ranged) if w is not None)


def _walked_near(world: World, me: int, ev: Event) -> bool:
    """"Moves without shifting or teleporting" -- a walk, which is what
    `MoveEnd.kind_` says. Being shoved is not the creature moving."""
    return getattr(ev, "kind_", "") == "walk" and enemy_within(2)(world, me, ev)


def _beside(c: Cast, victim: int, squares_: int) -> bool:
    """Shift up to `squares_` squares into a square adjacent to `victim`.

    Handing the distance to the decider would as soon walk away from the
    creature the shift exists to reach.
    """
    if c.adjacent(victim):
        return True
    standing = squares_of(c.world, victim)
    here = c.here
    room = sorted(
        sq
        for sq in spread(standing, 1) - standing
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and distance(here, sq) <= squares_
    )
    if not room:
        return False
    where = c.choose(room, "where you come up beside it")
    return where is not None and c.shift(to=where)


def _provoked_and_missed(c: Cast, victim: int) -> bool:
    """Open the printed opening and say whether the swing went wide.

    The engine never decides what goes in an opportunity window -- a
    controller answers -- so with nobody playing the target this is False
    and the attack goes against AC, which is the printed default.
    """
    seen: list[bool] = []

    def note(ev: Hit | Miss) -> None:
        if ev.attacker == victim and ev.target == c.me:
            seen.append(isinstance(ev, Miss))

    subs = [c.world.bus.on(Hit, note), c.world.bus.on(Miss, note)]
    try:
        c.provoke(victim, on=c.me, why=c.ref)
    finally:
        for sub in subs:
            c.world.bus.off(sub)
    return bool(seen) and all(seen)


@power(
    "p1387",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1387(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.grants_advantage()


@power(
    "p1480",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=WILL),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1480(c: Cast) -> None:
    """The trade of places is the printed slide-and-shift in one move.

    `c.swap` moves both at once, which is the same end state and cannot
    leave the two of them stacked. The second shift is the free one, and the
    Charisma leg of the fork lengthens it.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        victim = c.target
        if victim is not None:
            c.swap(victim)
        c.shift(c.cha_mod if c.build("trickster") else 1)


@power(
    "p209",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p209(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.prone()


@power(
    "p550",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p550(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.bonus(AC, c.cha_mod, on=c.me, until=When.SONT)


@power(
    "p10159",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    trigger=(
        "an enemy within 2 squares makes a ranged or area attack, "
        "or moves without shifting or teleporting"
    ),
    on=[
        Trigger(
            AttackDeclared,
            both(enemy_within(2), by_ranged),
            "an enemy within 2 squares makes a ranged or area attack",
        ),
        Trigger(MoveEnd, _walked_near, "an enemy within 2 squares moves"),
    ],
)
def p10159(c: Cast) -> None:
    """Both halves of the printed trigger are declared. Declaring one would
    leave the row looking finished and answering half of what it says."""
    victim = c.target
    if victim is None:
        return
    _beside(c, victim, 2)
    if c.strike(advantage=True):
        c.damage(c.w(1), c.dex_mod)


@power(
    "p10170",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10170(c: Cast) -> None:
    """"At any point during this shift" is not expressible -- a shift is one
    move -- so the whole of it is taken before the swing."""
    if c.first and c.cha_mod > 0:
        c.shift(c.cha_mod)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p10749",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10749(c: Cast) -> None:
    """The defence is not known until the opening has been answered, so the
    attack is rolled longhand rather than declared in the header."""
    victim = c.target
    if victim is None:
        return
    vs = AC
    if _provoked_and_missed(c, victim) and defence(
        c.world, victim, REF
    ) < defence(c.world, victim, AC):
        vs = REF
    if c.attack(c.dex_, vs, on=victim):
        c.damage(c.w(3), c.dex_mod)


@power(
    "p10750",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10750(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.dex_mod)
    c.push(1)
    splash = 2 + c.str_mod if c.build("brawny") else 3
    for foe in c.enemies():
        if foe != victim and c.adjacent_to(victim, foe):
            c.flat(splash, on=foe)


@power(
    "p10751",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_sling,
    requires_text="needs a sling",
)
def p10751(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.push(1)
        c.prone()


@power(
    "p10752",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10752(c: Cast) -> None:
    if c.first:
        c.shift(3)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.shift(3)


@power(
    "p10753",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10753(c: Cast) -> None:
    """The knock down is an Effect line, so a miss gets it too. The Special
    line -- usable in place of a melee basic when charging -- has no header
    field to go in."""
    landed = bool(c.strike())
    c.prone()
    if landed:
        c.damage(c.w(2), c.dex_mod)


@power(
    "p10754",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10754(c: Cast) -> None:
    """The slide is a printed choice, and which way the opening falls is the
    consequence of taking it."""
    if not c.strike():
        return
    c.damage(c.w(2), c.dex_mod)
    moved = c.slide(1) if c.may("slide it a square", who=c.me) else 0
    seen = sorted(a for a in c.allies() if c.can_see(a))
    if moved and seen:
        friend = c.choose(seen, "who the opening is for")
        c.grants_advantage(to=friend if friend is not None else c.me)
    else:
        c.grants_advantage()


@power(
    "p10755",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10755(c: Cast) -> None:
    if c.first:
        c.shift(c.speed_of())
        c.hide()
    unseeing = sorted(hidden_from(c.world, c.me))
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    for watcher in unseeing:
        c.hide(from_=watcher)


@power(
    "p16505",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="an enemy enters a square within 3 squares of you",
    on=Trigger(
        EnterSquare, enemy_within(3), "an enemy enters a square within 3 squares of you"
    ),
)
def p16505(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    _beside(c, victim, 2)
    if c.strike(advantage=True):
        c.damage(c.w(1), c.dex_mod)
        c.penalty("attack", 2)


@power(
    "p2251",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p2251(c: Cast) -> None:
    """"For every square you shifted" is counted from where the shift began
    and where it ended, which is what a shift of two squares can differ by.
    The Athletics half of the Effect line is a skill the model has none of.
    """
    start = c.here
    if c.first and c.may("shift before the strike", who=c.me):
        c.shift(2)
    crossed = distance(start, c.here)
    if c.strike():
        c.damage(c.w(1), c.dex_mod + crossed * c.str_mod)


@power(
    "p2284",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p2284(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p2509",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p2509(c: Cast) -> None:
    """"Marked by an ally of yours" -- a mark is a relation naming who set
    it, so the question is asked once per ally rather than of the board."""
    victim = c.target
    if not c.strike():
        return
    extra = 0
    if victim is not None and any(c.marked(victim, by=mate) for mate in c.allies()):
        extra = c.cha_mod
    c.damage(c.w(2), c.dex_mod + extra)


@power(
    "p4477",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4477(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod + c.cha_mod)
        if c.build("trickster"):
            c.shift(1)


@power(
    "p4478",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4478(c: Cast) -> None:
    """"Your Strength modifier or your Charisma modifier" is the leg of the
    fork the character took, not a free choice at the table."""
    victim = c.target
    extra = 0
    if victim is not None and flanked_by(c.world, victim, c.me):
        extra = c.str_mod if c.build("brawny") else c.cha_mod
    if c.strike():
        c.damage(c.w(1), c.dex_mod + extra)
        c.slide(1)
        c.slowed()


@power(
    "p4479",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="you miss with a melee attack",
    on=Trigger(Miss, both(by_me, by_melee), "you miss with a melee attack"),
)
def p4479(c: Cast) -> None:
    if c.strike(advantage=True):
        extra = c.str_mod if c.build("brawny") else 0
        c.damage(c.w(1), c.dex_mod + extra)
        c.shift(1)
