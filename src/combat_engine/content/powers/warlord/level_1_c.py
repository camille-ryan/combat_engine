"""Warlord, level 1: the rows printed outside the first book.

`c.grant_attack` and `c.charge_at` exist now, so the shape `level_1.py`
wrote down as a note -- "an ally can make a basic attack as a free action"
-- is written here rather than described. `c.charge_at(victim, who=friend)`
is the one to reach for where the printed word is *charge*: it walks the
ally in and flags the swing, which `c.grant_attack` alone does not.

Two riders name builds this chargen does not offer -- the Charisma pools on
`p2328` and `p4543`. They are gated on `c.build(...)` all the same, which is
the printed sentence and is right the moment the build exists; the ungated
half is what a warlord without it gets.

`p2328`'s extra 1[W] is the *ally's* weapon, not yours, so the die is read
off that creature's gear and rolled when the bonus is handed over rather
than when it is spent. A modifier is a number and there is nowhere to put a
die, so the alternative was rolling your own weapon for somebody else.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_ALLY,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Trigger,
    Usage,
    When,
    Window,
    World,
    by_melee,
    power,
)
from combat_engine.engine.components import Powers
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    AttackDeclared,
    Dropped,
    Healed,
    Hit,
    OpportunityWindow,
    TurnStart,
)
from combat_engine.engine.query import distance_between, team

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_ALLY_SWINGS_BASIC = "an ally within 3 squares makes a melee basic attack"
_ENEMY_FELLED_AN_ALLY = "an enemy within 5 squares reduces an ally to 0 hit points"


def _friends_within(c: Cast, radius: int) -> list[int]:
    """`side="ally"` counts the caster and every printed line here says
    "an ally", so the caster comes back out."""
    return sorted(a for a in c.within(radius, side="ally") if a != c.me)


def _their_w(c: Cast, who: int, count: int = 1) -> str:
    """`count`[W] of somebody else's weapon. `c.w` only ever reads yours."""
    gear = c.world.get(who, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return f"{count}d4"
    faces = weapon.damage.split("d")[-1]
    return f"{count}d{faces}"


def _is_weapon_attack(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", "") or "")
    return p is not None and Keyword.WEAPON in p.keywords


def _granted_hit(c: Cast, who: int, foe: int, ref: str = "") -> bool:
    """Did the swing somebody else was handed land? `c.grant_attack` reports
    that a row went off, not that it connected."""
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == who and ev.target == foe:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        c.grant_attack(who, on=foe, ref=ref)
    finally:
        c.world.bus.off(sub)
    return bool(landed)


def _heavy_thrown(world: World, eid: int) -> bool:
    """"A heavy thrown weapon."

    No weapon in the model carries a thrown flag -- what a thrown one has is
    a `ranged` band on something you also swing, the reading `rogue/
    level_1_b.py` settled -- and "heavy" is the not-a-light-blade half.

    The row is *not* `thrown_by_hand`: that field is for a melee weapon
    reaching out with no ranged band at all, and it gates on `gear.melee`,
    which a weapon carrying a band is not in. A javelin is `gear.ranged`.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    return bool(weapon and weapon.ranged and not weapon.is_light_blade)


def _shield(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.shield)


def _ally_swings_basic(radius: int) -> Callable[[World, int, Event], bool]:
    """"An ally in the burst makes a melee basic attack."

    Which row that is differs per creature -- a monster points `Powers.basic`
    at one of its own abilities -- so the event's power is compared against
    whatever that creature's basic actually is.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me or team(world, who) is not team(world, me):
            return False
        if distance_between(world, me, who) > radius:
            return False
        known = world.get(who, Powers)
        basic = (known.basic if known else "mba") or "mba"
        return getattr(ev, "power", "") == basic and by_melee(world, me, ev)

    return check


def _killer_of(world: World, victim: int) -> int | None:
    """Who put that creature down. `Dropped` names only who went down."""
    for e in reversed(world.bus.log):
        if e.kind == "DamageApplied" and getattr(e, "target", None) == victim:
            return getattr(e, "source", None)
    return None


def _enemy_felled_an_ally(radius: int) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or who == me or team(world, who) is not team(world, me):
            return False
        killer = _killer_of(world, who)
        if killer is None or team(world, killer) is team(world, me):
            return False
        return distance_between(world, me, killer) <= radius

    return check


@power(
    "p11602",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11602(c: Cast) -> None:
    """"The next time an ally hits" is one watcher that spends itself on the
    first ally's hit that actually pays out -- `c.watch(once=True)` reads
    whether the body did anything, so a miss or your own hit leaves it up."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe, me = c.target, c.me

    def cash_in(ev: Hit) -> None:
        if ev.target != foe or ev.attacker == me:
            return
        if team(c.world, ev.attacker) is not team(c.world, me):
            return
        pick = c.choose(
            ["deal 4 extra damage", "slide it 2 squares", "shift 2 squares"],
            "what that ally takes",
        )
        if pick == "slide it 2 squares":
            c.slide(2, on=foe)
        elif pick == "shift 2 squares":
            c.shift(2, who=ev.attacker)
        else:
            c.flat(4, on=foe)

    c.watch(Hit, cash_in, until=When.EONT, once=True, label=c.ref)


@power(
    "p11719",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_SWINGS_BASIC,
    on=Trigger(AttackDeclared, when=_ally_swings_basic(3), text=_ALLY_SWINGS_BASIC),
)
def p11719(c: Cast) -> None:
    """"Instead of making a melee basic attack": the basic is interrupted
    away and the ally's own at-will goes in its place, at whoever the basic
    was aimed at. The ally picks which row out of the ones it has.

    The basic itself is out of that list. It is the row being replaced and
    it is still on the stack -- `dsl.use` refuses a row already in flight --
    so offering it is offering the one option that cannot work.
    """
    friend = getattr(c.trigger, "attacker", None)
    victim = getattr(c.trigger, "target", None)
    if friend is None or victim is None:
        return
    known = c.world.get(friend, Powers)
    basic = getattr(c.trigger, "power", "")
    options = sorted(
        ref for ref in (known.all if known else []) if ref != basic and _melee_at_will(ref)
    )
    chosen = c.choose(options, "which at-will the ally uses instead") if options else None
    if chosen is None:
        return
    c.cancel()
    if _granted_hit(c, friend, victim, ref=chosen):
        c.dazed(on=victim, until=When.EOTNT)


def _melee_at_will(ref: str) -> bool:
    """A melee at-will attack somebody can be handed. Triggered rows are out:
    they come with a printed trigger this does not supply."""
    p = get(ref)
    return (
        p is not None
        and p.is_attack
        and not p.triggers
        and p.usage is Usage.AT_WILL
        and p.reach.kind == "melee"
    )


@power(
    "p11720",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11720(c: Cast) -> None:
    """Two allies, each offered the three printed choices. The bar is a
    running set: the power's own target to begin with, and then whatever the
    first ally went for, so the second cannot pile on to the same creature.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    barred = {c.target}
    picked: list[int] = []
    for _ in range(2):
        pool = [
            a for a in _friends_within(c, 5) if a not in picked and c.can_see(a)
        ]
        friend = c.choose(pool, "which ally you send in") if pool else None
        if friend is None:
            break
        picked.append(friend)
        _send_in(c, friend, barred)


def _send_in(c: Cast, friend: int, barred: set[int | None]) -> None:
    foes = sorted(f for f in c.enemies() if f not in barred)
    what = c.choose(["charge", "swing", "run"], "what that ally does") if foes else "run"
    if what == "run":
        c.move(c.speed_of(friend), who=friend)
        return
    victim = c.choose(foes, "who that ally goes for")
    if victim is None:
        return
    barred.add(victim)
    if what == "charge":
        c.charge_at(victim, who=friend)
    else:
        c.grant_attack(friend, on=victim)


@power(
    "p2328",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_heavy_thrown,
    requires_text="needs a heavy thrown weapon",
)
def p2328(c: Cast) -> None:
    """The errata'd Hit line: a *weapon* attack, which the damage context can
    be asked about through the power it names."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    radius = max(1, c.cha_mod) if c.build("resourceful") else 1
    for friend in _friends_within(c, radius):
        c.bonus(
            "damage",
            c.roll(_their_w(c, friend)),
            on=friend,
            until=When.SONT,
            when=_is_weapon_attack,
            once=True,
        )


@power(
    "p2443",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_shield,
    requires_text="needs a shield",
)
def p2443(c: Cast) -> None:
    """The temporary hit points arrive a turn late, and who is standing
    beside you then is asked then -- people move."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    me = c.me

    def rally(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for friend in _friends_within(c, 1):
            c.temp_hp(5, on=friend)

    c.watch(TurnStart, rally, until=When.EONT, once=True, on=me, label=c.ref)


@power(
    "p4541",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4541(c: Cast) -> None:
    """You open yourself up and a friend takes the opening it makes.

    The combat advantage the target gets is against *you*, so it is a
    one-shot grant put on the caster; the ally's is the mirror of it. Both
    are spent by the swing they were printed for.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    foe = c.target
    if foe is None or not c.may("swing at the warlord", who=foe):
        return
    c.grants_advantage(on=c.me, to=foe, once=True)
    if not c.grant_attack(foe, on=c.me):
        return
    pool = sorted(a for a in c.within(5, of=foe, side="ally") if a != c.me)
    friend = c.choose(pool, "who takes the opening") if pool else None
    if friend is not None:
        c.grants_advantage(on=foe, to=friend, once=True)
        c.grant_attack(friend, on=foe)


@power(
    "p4542",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p4542(c: Cast) -> None:
    """No weapon dice and no ability damage: the whole Hit line is a shove
    and then somebody else's move or swing."""
    if not c.strike():
        return
    foe = c.target
    c.push(1)
    pool = sorted(a for a in c.allies() if c.can_see(a))
    friend = c.choose(pool, "who you direct") if pool else None
    if friend is None:
        return
    if c.choose(["swing at it", "step"], "what that ally does") == "step":
        c.shift(c.int_mod, who=friend)
    else:
        c.grant_attack(friend, on=foe)


@power(
    "p4543",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p4543(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    foe = c.target
    squares_ = max(1, c.cha_mod) if c.build("bravura") else 1
    others = sorted(f for f in c.within(5, side="enemy") if f != foe)
    other = c.choose(others, "who else you drag in") if others else None
    if other is not None:
        c.pull(squares_, on=other)


@power(
    "p4544",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4544(c: Cast) -> None:
    """"After you shift" -- the ally pool is measured from where you end up,
    which is the point of the printed order."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    if not (c.may("step a square", who=c.me) and c.shift(1)):
        return
    pool = _friends_within(c, 2)
    friend = c.choose(pool, "who steps with you") if pool else None
    if friend is not None:
        c.shift(1, who=friend)


@power(
    "p4545",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.RELIABLE, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p4545(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    foe = c.target
    pool = _friends_within(c, 5)
    friend = c.choose(pool, "who is set on it") if pool else None
    if friend is None:
        return
    c.bonus(
        "damage",
        1 + c.int_mod,
        on=friend,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == foe,
    )
    # Moving a standing effect onto somebody else, on a later turn and for a
    # named action, is not something a body can arm.
    c.note(
        f"{c.ref}: as a minor action you could move that bonus to another ally within "
        "5 squares -- transferring a standing effect is not expressible"
    )


@power(
    "p4546",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4546(c: Cast) -> None:
    """The Effect line does not care whether your own blow landed."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    foe = c.target
    pool = _friends_within(c, 10)
    friend = c.choose(pool, "who takes the free swing") if pool else None
    if friend is not None and foe is not None:
        c.grant_attack(
            friend, on=foe, attack_bonus=c.int_mod, damage_bonus=c.int_mod
        )


@power(
    "p4547",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC, plus=1),
    trigger=_ENEMY_FELLED_AN_ALLY,
    on=Trigger(Dropped, when=_enemy_felled_an_ally(5), text=_ENEMY_FELLED_AN_ALLY),
)
def p4547(c: Cast) -> None:
    """The 1d6 per opening is counted rather than guessed: the openings are
    tallied off `OpportunityWindow` while the run is happening, which is the
    only moment they exist.

    `Dropped` names only who went down, so the enemy the printed Target line
    means is read off the `DamageApplied` that put them there; the
    dispatcher's own aim is the fallback.
    """
    fallen = getattr(c.trigger, "actor", None)
    foe = (_killer_of(c.world, fallen) if fallen is not None else None) or c.target
    if foe is None:
        return
    openings: list[int] = []

    def tally(ev: OpportunityWindow) -> None:
        if ev.provoker == c.me:
            openings.append(ev.actor)

    sub = c.world.bus.on(OpportunityWindow, tally, owner=c.me)
    try:
        if c.may("close on it first", who=c.me):
            c.run_at(foe)
    finally:
        c.world.bus.off(sub)
    if c.strike(on=foe):
        c.damage(c.w(2), c.str_mod, on=foe)
    if fallen is not None and c.may("spend a healing surge", who=fallen):
        c.surge(on=fallen, bonus=sum(c.roll("1d6") for _ in openings))


@power(
    "p4548",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4548(c: Cast) -> None:
    """The miss line is the better half: two allies each step and swing."""
    if c.may("step before the blow", who=c.me):
        c.shift(1)
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.grants_advantage(to="allies", until=When.SONT)
        return
    picked: list[int] = []
    for _ in range(2):
        pool = [a for a in _friends_within(c, 5) if a not in picked]
        friend = c.choose(pool, "who steps up") if pool else None
        if friend is None:
            break
        picked.append(friend)
        c.shift(1, who=friend)
        foes = sorted(c.within(1, of=friend, side="enemy"))
        victim = c.choose(foes, "who that ally swings at") if foes else None
        if victim is not None:
            c.grant_attack(friend, on=victim)


@power(
    "p6006",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p6006(c: Cast) -> None:
    """You stand in the open and it costs whatever takes the bait.

    The openings are given out in the `Window.BEFORE` half of the
    declaration: an opportunity attack interrupts the blow it answers, so a
    window opened afterwards would be one the printed line does not offer.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.mark()
    foe, me = c.target, c.me
    if foe is None:
        return
    c.grants_advantage(on=c.me, to=foe, until=When.SONT)

    def opening(ev: AttackDeclared) -> None:
        if ev.attacker != foe or ev.target != me:
            return
        for who in (me, *c.allies()):
            c.provoke(who, on=foe, why=c.ref)

    c.watch(
        AttackDeclared,
        opening,
        until=When.SONT,
        once=True,
        window=Window.BEFORE,
        label=c.ref,
    )


@power(
    "p7389",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7389(c: Cast) -> None:
    """The damage context carries `charge` and `target`, which is the whole
    of the printed gate. The Special line is a note about how the row may be
    used and not a row that charges, so no `charges=True`.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    foe = c.target

    def charging_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe and bool(ctx.get("charge"))

    for friend in c.allies():
        c.bonus("damage", c.int_mod, on=friend, until=When.EONT, when=charging_it)


@power(
    "p7398",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7398(c: Cast) -> None:
    """`Healed` is a `Decision` announced before the hit points go on, so
    the amount can still be raised.

    It names the healer and not the power, so the gate is "a heal of yours"
    rather than "a warlord healing power of yours" -- and for a warlord
    inside one turn those are the same set.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    me, extra = c.me, c.cha_mod

    def more(ev: Healed) -> None:
        if ev.source == me:
            ev.amount += extra

    c.watch(Healed, more, until=When.EONT, window=Window.BEFORE, on=me, label=c.ref)
