"""Ranger, level 9: the daily attacks.

`p459` prints "Ranged 1" and then says the attack does not provoke, which is
the header's `no_provoke` rather than anything the body does. Its ranged
reach on a row carrying `Keyword.WEAPON` is already a bow in hand, so no
Requirement of its own is declared.

`p384` prints its move inside the attack line -- "at any point during your
move" -- and a body starts after the power is aimed, so the walk is taken
first and the two swings follow it. The printed freedom to shoot halfway
through is the one clause that does not survive.

Four of the rows the later books add print their Target as "one creature
designated as your quarry". Nothing on a board ever names one, so a body
that refused to act without a quarry would report itself silent; the
restriction is declared on the card with a `Target` label and the riders
that read `c.is_quarry` are the part with teeth.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    INTERRUPT,
    ONE_CREATURE,
    STANDARD,
    STR,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Target,
    Trigger,
    UpTo,
    When,
    World,
    distance,
    get,
    power,
)
from combat_engine.engine.events import AdjacencyGained, Hit, ZoneEntered
from combat_engine.engine.movement import walk
from combat_engine.engine.query import hidden_from, team
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_QUARRY_TARGET = Target("enemy", 1, label="One creature designated as your quarry")
_ENEMY_CLOSES = "an enemy moves adjacent to you"


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me."""
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


def _melee_row(ref: str) -> bool:
    p = get(ref or "")
    return p is not None and p.reach.kind == "melee"


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


@power(
    "p160",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p160(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p384",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p384(c: Cast) -> None:
    """Two swings over one or two creatures, both 3[W]: one target takes
    both, two take one each. `c.attack_mod` is what keeps the damage line on
    the branch actually being used -- Strength in reach, Dexterity at range.
    """
    if c.first:
        c.move(c.speed_of(c.me))
    shots = 2 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike():
            c.damage(c.w(3), c.attack_mod)
        else:
            c.half_damage(c.w(3), c.attack_mod)


@power(
    "p459",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    no_provoke=True,
)
def p459(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(4), c.dex_mod)
    else:
        c.half_damage(c.w(4), c.dex_mod)


@power(
    "p714",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p714(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p10631",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
)
def p10631(c: Cast) -> None:
    """The Effect line names the quarry, so by the time the Hit line asks
    whether the target is one, it is -- which is what the printed row means
    by putting the designation before the attack."""
    c.quarry()
    if not c.strike():
        c.half_damage(c.w(3), c.str_mod)
        return
    c.damage(c.w(3), c.str_mod)
    if c.is_quarry():
        c.ongoing(5)


@power(
    "p10632",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=_QUARRY_TARGET,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10632(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)

    victim = c.target
    me = c.me

    def feed(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim or not _melee_row(ev.power):
            return
        c.temp_hp(5 + c.wis_mod, on=me)

    c.watch(Hit, feed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p10633",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=_QUARRY_TARGET,
    keywords=[*MARTIAL_RANGED, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p10633(c: Cast) -> None:
    """The last sentence adds two dice to Hunter's Quarry damage against this
    target. That damage is a rider held inside `cf:ranger-quarry`, closed
    over its own dice string, and nothing reaches into it from here -- so the
    clause is left unwritten rather than paid out as flat damage, which is a
    different card."""
    if c.strike():
        c.damage(c.w(3), c.attack_mod)
        c.mark(until=When.EONT)


@power(
    "p10634",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10634(c: Cast) -> None:
    """The Special line offers the row in place of a melee basic attack when
    charging. There is no header field for what a row may be *used as*, so it
    is declared as the standard action it also is."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "p10635",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p10635(c: Cast) -> None:
    """The step is filtered rather than handed to the decider: "must not end
    the shift adjacent to the triggering enemy" is a condition on the square,
    and `c.shift` would as soon stay in reach. The immobilising is an Effect
    line, so it lands whether or not the shot did.
    """
    foe = getattr(c.trigger, "actor", None)
    held = squares_of(c.world, foe) if foe is not None else frozenset()
    paths = c.world.reachable_paths(c.me, 2)
    away = sorted(
        sq for sq in paths if not any(distance(sq, at) <= 1 for at in held)
    )
    dest = c.choose(away, f"{c.ref}: where to break off to") if away else None
    if dest is not None:
        walk(c.world, c.me, paths[dest])
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "p10704",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10704(c: Cast) -> None:
    """The standing area is a zone, laid once for the whole burst rather than
    once per creature caught in it. Moving it with a move action is not
    written -- nothing relocates a zone once it is placed -- and is in the
    report."""
    if c.first:
        zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
        me = c.me

        def loose(ev: ZoneEntered) -> None:
            if ev.zone != zone or ev.actor == me:
                return
            if c.may("take the shot", who=me):
                c.basic(on=ev.actor, ranged=True)

        c.watch(ZoneEntered, loose, until=When.ENCOUNTER, on=me, label=c.ref)
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p11575",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=_QUARRY_TARGET,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p11575(c: Cast) -> None:
    """The Effect rerolls low Hunter's Quarry dice. Those dice are rolled
    inside `cf:ranger-quarry`'s own rider and nothing here can reach the
    roll, so the clause is left unwritten -- see `p10633`."""
    if c.strike():
        c.damage(c.w(3), c.dex_mod)


@power(
    "p12504",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12504(c: Cast) -> None:
    """"Adjacent to you at any point during the shift" cannot be said -- the
    step is one jump and targets are chosen before the body runs -- so the
    shift is taken first and whoever is in reach afterwards is who it
    catches.

    Where the slide ends -- next to the beast companion -- has nowhere to go:
    the companion is not modelled and `c.slide` takes no anchor, so the
    destination is the mover's decider's, the reading `level_2.py`'s `p923`
    settled. The trailing beast Effect is dropped whole.
    """
    if c.first:
        c.shift(4)
    alone = c.first and c.last
    if c.strike():
        c.damage(c.w(2 if alone else 1), c.str_mod)
        c.slide(5)
    else:
        c.half_damage(c.w(1), c.str_mod)
        c.slide(3)


@power(
    "p4406",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p4406(c: Cast) -> None:
    """One burn or the other, never both: ongoing damage of a type does not
    stack, so the quarry's 10 is applied instead of the 5 rather than on top
    of it -- written the other way round, the weaker one would be refused and
    the stronger never reached."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.ongoing(10 if c.is_quarry() else 5)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p4407",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p4407(c: Cast) -> None:
    for _ in range(3):
        if c.strike():
            c.damage(c.w(1))
            c.push(1)
        else:
            c.half_damage(c.w(1))


@power(
    "p4409",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=Target(
        "enemy", 1, label="One creature that is surprised or unaware of your presence"
    ),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p4409(c: Cast) -> None:
    """The printed Target is a creature that cannot see it coming, which no
    `Target` can filter on, so the restriction is on the card only.

    Staying hidden afterwards is `c.hide` again, and only worth doing if the
    ranger was hidden from this creature to begin with -- `resolve` gives an
    attacker away, so a row that keeps its concealment has to say so.
    """
    victim = c.target
    was_hidden = victim is not None and c.me in hidden_from(c.world, victim)
    if c.strike():
        c.damage(c.w(3), c.attack_mod + c.wis_mod)
        c.shift(2)
    else:
        c.half_damage(c.w(3), c.attack_mod + c.wis_mod)
        c.shift(1)
    if was_hidden and victim is not None:
        c.hide(from_=victim)


@power(
    "p4410",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p4410(c: Cast) -> None:
    """Regaining a spent encounter power is not written: `Powers` counts uses
    and nothing gives one back, so the clause would be prose. The other half
    of the same "or" -- the extra dice against the quarry -- is, and with the
    first branch absent it is simply taken when it applies.
    """
    quarry = c.is_quarry()
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        if quarry:
            c.damage(c.w(2))
    c.shift(max(1, c.speed_of(c.me) // 2))


@power(
    "p7502",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p7502(c: Cast) -> None:
    """The grab lands; what sustaining it pays out does not.

    `c.grab` is encounter-clocked and carries no sustain cost, so nothing
    ever sustains it and `c.on_sustain` would never fire -- and the -2 to
    escape attempts has nothing to modify, because escaping a grab is not an
    action the engine has. Both are in the report.
    """
    landed = 0
    for swing in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
        else:
            c.half_damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
    if landed == 2:
        c.grab()
