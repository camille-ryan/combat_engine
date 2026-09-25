"""Rogue, level 7: the encounter attacks.

Two want a light blade at reach 1; the other two want something that throws.
`p1481`'s requirement names "a crossbow, a light thrown weapon, or a sling",
and the engine's weapons carry no thrown flag -- what a thrown one has is a
`ranged` band -- so a light blade counts for it only when it has one. A
plain dagger therefore does not, which is the honest reading of a model
where nothing about that dagger says it leaves the hand.

One row carries a build rider on each leg of the rogue's fork: Strength on
`brawny` and Charisma on `trickster`.

The rows printed in the later books follow below. Two notes for those.
`p10173` prints a standard action and the at-will opportunity attack it
grants as two cards under one id, and the registry holds one row per id, so
the swing is folded into the row that grants it. And nothing in the model
holds cover as a grant between two creatures, so where a row gives one,
what superior cover is worth -- +5 to AC and Reflex -- is what is applied.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Moved,
    Ranged,
    Relation,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import adjacent, cover_between, hidden_from
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})
MISSILE_GROUPS = frozenset({"crossbow", "sling"})

#: What holds a creature well enough that "you escape" has something to
#: escape from.
_HELD = (Condition.GRABBED, Condition.RESTRAINED)


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


def _rogue_missile(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return False
    return weapon.group in MISSILE_GROUPS or (
        weapon.is_light_blade and weapon.ranged is not None
    )


@power(
    "p1481",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p1481(c: Cast) -> None:
    """The blast already checks line of effect; "you can see" also rules out
    an enemy hidden from you."""
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p339",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p339(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        amount = c.str_mod if c.build("brawny") else 1
        c.penalty(AC, amount)
        c.penalty(REF, amount)


@power(
    "p977",
    level=7,
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
def p977(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.blinded()


@power(
    "p982",
    level=7,
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
def p982(c: Cast) -> None:
    """The miss line is a second swing at the same creature, not a rider, so
    it is another `c.strike` -- and the Charisma leg of the fork puts its
    bonus on that roll only."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    elif c.strike(plus=c.cha_mod if c.build("trickster") else 0):
        c.damage(c.w(1), c.dex_mod)


def _sling(world: World, eid: int) -> bool:
    """A sling is fired, so it is `gear.ranged` rather than `gear.main`."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return any(w.group == "sling" for w in (gear.main, gear.ranged) if w is not None)


def _is_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


def _escape_grab(c: Cast) -> None:
    """A grab is a relation held up by an effect, so ending the effect is
    the escape -- the reading `level_10.py` settled."""
    for effect in list(c.world.effects.of(c.me)):
        held = any(card in _HELD for card in effect.conditions)
        bound = any(
            kind is Relation.GRABBED_BY and target == c.me
            for kind, _source, target in effect.relations
        )
        if held or bound:
            c.world.effects.end(effect, c.ref)
    for grabber in c.world.relations.sources(Relation.GRABBED_BY, c.me):
        c.world.relations.clear(Relation.GRABBED_BY, grabber, c.me, c.ref)


def _beside(c: Cast, victim: int, squares_: int) -> bool:
    """Shift up to `squares_` squares and end adjacent to `victim`."""
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


@power(
    "p10173",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL_WEAPON,
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10173(c: Cast) -> None:
    """Two printed triggers on the granted attack -- an enemy *starts its
    turn* in a square adjacent to you, or *enters* one -- so both are
    watched. Each is offered as the printed **can**, since an opportunity
    action is permission rather than obligation.
    """
    me = c.me
    sting = 2 + c.cha_mod if c.build("trickster") else c.cha_mod

    def snap(victim: int) -> None:
        if not c.may("snap at it", who=me):
            return
        if c.attack(c.dex_, REF, on=victim):
            c.damage(c.w(1), c.dex_mod, on=victim)
            c.penalty(
                "attack", sting, on=victim, until=When.EONT,
                when=lambda ctx: ctx.get("target") == me,
            )

    def came(ev: AdjacencyGained) -> None:
        if ev.other == me and ev.mover not in (0, me) and ev.actor in c.enemies():
            snap(ev.actor)

    def began(ev: TurnStart) -> None:
        if ev.actor != me and ev.actor in c.enemies() and c.adjacent(ev.actor):
            snap(ev.actor)

    c.watch(AdjacencyGained, came, until=When.EONT, on=c.me, label=f"{c.ref} steps in")
    c.watch(TurnStart, began, until=When.EONT, on=c.me, label=f"{c.ref} stands there")


@power(
    "p10765",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10765(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.prone()
    if c.last and c.build("trickster"):
        c.shift(2)


@power(
    "p10766",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_is_hidden,
    requires_text="needs a creature you are hidden from",
)
def p10766(c: Cast) -> None:
    """"Target: one creature from which you are hidden" is a target filter
    with no header field, so it is declared as the caster's Requirement --
    is there such a creature at all -- and checked again here."""
    if c.target is None or not c.is_hidden(from_=c.target):
        return
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.shift(1)


@power(
    "p10767",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10767(c: Cast) -> None:
    """The tally counts squares crossed rather than the two ends of the
    move, the way `p999` does, and pays out once -- at the end of the
    target's *next* turn and no turn after it."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.dex_mod)
    sting = c.str_mod + c.dex_mod if c.build("brawny") else c.dex_mod
    steps = 0
    done: list[bool] = []

    def stepped(ev: Moved) -> None:
        nonlocal steps
        if ev.actor == victim:
            steps += 1

    def ended(ev: TurnEnd) -> None:
        if ev.actor != victim or done:
            return
        done.append(True)
        if steps >= 2:
            c.flat(sting, on=victim)

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} counts")
    c.watch(TurnEnd, ended, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} pays out")


@power(
    "p10769",
    level=7,
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
def p10769(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.condition(Condition.RESTRAINED)


@power(
    "p10770",
    level=7,
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
def p10770(c: Cast) -> None:
    """Superior cover is +5 to AC and Reflex, and the target itself is what
    the rogue is hiding behind -- so its own attacks are not gated."""
    victim, me = c.target, c.me
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        if victim is not None:

            def shielded(ctx: dict) -> bool:
                return ctx.get("attacker") != victim and adjacent(c.world, me, victim)

            c.bonus(AC, 5, on=c.me, until=When.EONT, when=shielded)
            c.bonus(REF, 5, on=c.me, until=When.EONT, when=shielded)
    if c.first:
        c.hide()


@power(
    "p1420",
    level=7,
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
def p1420(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)


@power(
    "p16487",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
)
def p16487(c: Cast) -> None:
    """The Special line waives the squeezing penalty on the roll, and
    nothing in the model charges one, so there is none to waive."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        if victim is not None:
            c.swap(victim)
        c.shift(c.speed_of() // 2)


@power(
    "p2269",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p2269(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p2290",
    level=7,
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
def p2290(c: Cast) -> None:
    """The shift is an Effect line and names where it ends, so it is aimed
    rather than handed to the decider -- which would as soon walk out of
    reach of the second swing it exists to set up."""
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    if victim is None:
        return
    _beside(c, victim, 1)
    if c.attack(c.dex_, AC, on=victim):
        c.damage(c.w(1), c.dex_mod, on=victim)
        c.grants_advantage(on=victim)


@power(
    "p4488",
    level=7,
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
def p4488(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.penalty("save", 2)


@power(
    "p4489",
    level=7,
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
def p4489(c: Cast) -> None:
    """"If the target could not see you before the shift" is being hidden
    from it, which is the only way the model records not being seen. The
    Stealth check after the shift is not rolled; what it buys is."""
    victim = c.target
    step = 1 + c.cha_mod if c.build("trickster") else 2
    unseen = victim is not None and c.is_hidden(from_=victim)
    if c.first and c.may("shift before the strike", who=c.me):
        c.shift(step)
    if not c.strike(advantage=True if unseen else None):
        return
    c.damage(c.w(1), c.dex_mod)
    c.shift(step)
    for foe in c.enemies():
        if cover_between(c.world, foe, c.me, ranged=True) is not Cover.NONE:
            c.hide(from_=foe)


@power(
    "p4490",
    level=7,
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
def p4490(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod + c.str_mod)
        if c.build("brawny"):
            c.slide(1)
            c.grants_advantage()


@power(
    "p671",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p671(c: Cast) -> None:
    """The shift is on the Hit line, so it is offered once per creature the
    blade reaches -- which is how a burst's riders read."""
    if c.target is None or not c.can_see(c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        if c.may("shift a square", who=c.me):
            c.shift(1)


@power(
    "p7504",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p7504(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        _escape_grab(c)
        c.shift(c.speed_of() // 2)
