"""Paladin, level 10: utility. Two rows, both about saving throws.

`p1446` rolls against every save-ends effect a target is carrying rather
than calling `c.save`, which takes one and stops -- the printed line is
"every effect that a save can end", and which one `c.save` would have found
first is an accident of insertion order.

The level's third PHB1 row is left out; see the report.

Two of the later rows -- `p13564` and `p13565` -- print "once per round
until the end of the encounter, you can take a minor action to ...". That is
a standing offer rather than an effect, and the engine has no way to add an
option to a creature's turn. They are written as a watcher on the paladin's
own turn that asks whether to do it and spends the minor through
`Encounter.spend`, so the action really is paid for; what is lost is being
able to choose *when* in the turn.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    DamageType,
    Defense,
    Dropped,
    Event,
    Health,
    Hit,
    Keyword,
    Ranged,
    Relation,
    Stats,
    Target,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_melee,
    get,
    power,
    use,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import line_of_effect, team
from combat_engine.engine.query import squares as squares_of

DIVINE = [Keyword.DIVINE]


def _holds_a_mark(world: World, eid: int) -> bool:
    """"An enemy marked by you" -- there has to be one to go to."""
    return bool(world.relations.targets(Relation.MARKED_BY, eid))


def _beside(c: Cast, who: int) -> list[tuple[int, int]]:
    theirs = squares_of(c.world, who)
    return [
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]


def _each_round(c: Cast, fn) -> None:  # noqa: ANN001
    """"Once per round you can take a minor action to ..." -- offered at the
    start of the paladin's turn, and the minor is really spent."""
    me = c.me

    def offer(ev) -> None:  # noqa: ANN001
        if ev.ghost or ev.actor != me or c.world.encounter is None:
            return
        if not c.may(f"spend a minor action on {c.ref}", who=me):
            return
        if c.world.encounter.spend(me, MINOR):
            fn()

    c.watch(TurnStart, offer, until=When.ENCOUNTER, on=me, label=f"{c.ref} standing offer")


@power(
    "p10253",
    level=10,
    cls="paladin",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.TELEPORTATION],
    requires=_holds_a_mark,
)
def p10253(c: Cast) -> None:
    """The rough ground is laid where the paladin lands, which is why the
    zone comes after the blink rather than with it."""
    reach = 1 + c.cha_mod
    spots = sorted(
        sq
        for foe in c.enemies()
        if c.marked(foe)
        for sq in _beside(c, foe)
        if distance(c.here, sq) <= reach
    )
    if spots:
        dest = c.choose(spots, "where the light puts you")
        if dest is not None:
            c.teleport(reach, to=dest)
    mine = squares_of(c.world, c.me)
    c.zone(spread(mine, 1) - mine, difficult=True, until=When.EONT)


@power(
    "p10254",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.HEALING, Keyword.STANCE],
)
def p10254(c: Cast) -> None:
    """`team` rather than `c.enemies()`: a creature that has just been
    dropped is filtered out of the live enemy list, and being dropped is
    half of what this answers.

    A minion is a creature whose maximum is one hit point, which is what the
    stat block gives it and the only thing here to read.
    """
    me = c.me
    st = c.stance(label=c.ref)

    def mend(ev: Event) -> None:
        who = getattr(ev, "actor", None)
        health = c.world.get(who, Health) if who is not None else None
        if health is None or health.max_hp <= 1:
            return
        if team(c.world, who) is team(c.world, me) or c.distance(who) > 5:
            return
        pool = c.within(5, side="ally")
        hurt = [a for a in pool if c.wounded(a)]
        lucky = c.choose(sorted(hurt or pool), "who is mended")
        if lucky is not None:
            c.heal(5 + c.cha_mod, on=lucky)

    for kind in (Bloodied, Dropped):
        held = c.watch(kind, mend, until=When.ENCOUNTER, on=me, label=f"{c.ref} mercy")
        st.on_end.append(lambda e=held: c.world.effects.end(e, "the stance ended"))


_AREA_AT_ME = "you are targeted by a close attack or an area attack"


def _area_attack_on_me(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach.kind in (
        "close_burst", "close_blast", "area_burst",
    )


@power(
    "p1284",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_AREA_AT_ME,
    on=Trigger(AttackRolled, when=_area_attack_on_me, text=_AREA_AT_ME),
)
def p1284(c: Cast) -> None:
    """Declared on the roll rather than on the declaration: `c.autohit` sets
    a flag on the live result, and there is no result until the die is down.

    Which allies are also hit is read off `among`, the whole target list of
    the one power use -- so the halving spends itself as each of them takes
    its damage rather than hanging about.
    """
    ev = c.trigger
    c.autohit()
    attacker = getattr(ev, "attacker", None)
    power_ = getattr(ev, "power", "")
    caught = {a for a in getattr(ev, "among", ()) if a in c.allies()}
    if attacker is None or not caught:
        return

    def spare(hurt: DamageRolled) -> None:
        if hurt.source == attacker and hurt.detail == power_ and hurt.target in caught:
            caught.discard(hurt.target)
            hurt.amount //= 2

    c.watch(
        DamageRolled, spare, until=When.EOT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} shelter",
    )


@power(
    "p13564",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p13564(c: Cast) -> None:
    def gift() -> None:
        friends = [a for a in c.within(5, side="ally") if a != c.me]
        if not friends:
            return
        lucky = c.choose(sorted(friends), "who is steadied")
        if lucky is not None:
            c.temp_hp(5, on=lucky)
            c.note(f"{c.ref}: +2 power bonus to that ally's next skill check")

    _each_round(c, gift)


@power(
    "p13565",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.HEALING],
)
def p13565(c: Cast) -> None:
    """"This damage ignores your immunities and resistances" has no
    spelling: the ten goes through `deal_damage` like anything else.
    """

    def tend() -> None:
        friends = [a for a in c.within(2, side="ally") if a != c.me]
        hurt = [a for a in friends if c.wounded(a)]
        if not hurt:
            return
        lucky = c.choose(sorted(hurt), "who is mended")
        if lucky is not None:
            c.heal(10, on=lucky)
            c.flat(10, on=c.me)

    _each_round(c, tend)


@power(
    "p13826",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
)
def p13826(c: Cast) -> None:
    """Bloodied is asked when the aura bites rather than when it is raised:
    the printed line is "while you are bloodied", which is a state.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=f"{c.ref} gloom")

    def sting(ev: Hit) -> None:
        who = ev.target
        if not c.bloodied(on=me) or who == me:
            return
        if team(c.world, who) is team(c.world, me):
            return
        if who in c.world.zones.occupants(ring):
            c.flat(c.cha_mod, dtype=DamageType.NECROTIC, on=who)

    c.watch(Hit, sting, until=When.ENCOUNTER, on=me, label=f"{c.ref} gloom")


@power(
    "p13827",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=[],
)
def p13827(c: Cast) -> None:
    """Offered rather than imposed: it is the target's hit points and the
    target's choice, and nobody pays it with nothing to shake off.
    """
    who = c.target
    if who is None:
        return
    saves = [e for e in c.world.effects.of(who) if e.when is When.SAVE_ENDS and not e.ended]
    if not saves or not c.may("bleed for a saving throw", who=who):
        return
    stats = c.world.get(who, Stats)
    c.flat(max(1, (stats.level if stats is not None else 1) // 2), on=who)
    c.save(on=who, bonus=4)


@power(
    "p1446",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p1446(c: Cast) -> None:
    who = c.target
    if who is None:
        return
    for effect in list(c.world.effects.of(who)):
        if effect.when is When.SAVE_ENDS and not effect.ended:
            c.world.effects.save(effect)


@power(
    "p31",
    level=10,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=Target("ally", 1, label="You or one ally"),
    keywords=DIVINE,
)
def p31(c: Cast) -> None:
    """The `"ally"` pool includes the caster, which is "you or one ally"
    exactly; `ONE_ALLY` is the same thing under a card that reads wrong."""
    c.save(on=c.target, bonus=2)


@power(
    "p3291",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 2, label="You and one ally in the burst"),
    keywords=[*DIVINE, Keyword.HEALING],
)
def p3291(c: Cast) -> None:
    """Done once for the whole power rather than once per target: the surge
    is one surge, and a body called twice would spend two.
    """
    if not c.first or not c.spend_surge(on=c.me):
        return
    amount = c.surge_value()
    c.heal(amount, on=c.me)
    friend = next((t for t in c.targets if t != c.me), None)
    if friend is not None:
        c.heal(amount, on=friend)


@power(
    "p3752",
    level=10,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p3752(c: Cast) -> None:
    """Says so when there is nothing to shake off, the way `p1746` does: a
    saving throw against nothing is not a roll, and silence would look like
    a row that had not been written."""
    if any(e.when is When.SAVE_ENDS and not e.ended for e in c.world.effects.of(c.me)):
        c.save(on=c.me, bonus=1 + c.wis_mod)
    else:
        c.note(f"{c.ref}: nothing a save can end")


_ALLY_HITS_IN_MELEE = "an ally within 5 squares of you hits with a melee attack"


def _ally_hits_in_melee(world: World, me: int, ev: Event) -> bool:
    from combat_engine.engine.query import distance_between

    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 5 and by_melee(world, me, ev)


@power(
    "p7264",
    level=10,
    cls="paladin",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[*DIVINE, Keyword.HEALING],
    trigger=_ALLY_HITS_IN_MELEE,
    on=Trigger(Hit, when=_ally_hits_in_melee, text=_ALLY_HITS_IN_MELEE),
)
def p7264(c: Cast) -> None:
    """Only the surge half is written. The other branch is "make two damage
    rolls for the attack and use either result", and the damage has not been
    rolled yet -- there is no way to say reroll-and-keep-the-better. See the
    report.
    """
    friend = getattr(c.trigger, "attacker", None)
    if friend is None:
        return
    if c.may("spend a healing surge", who=friend):
        c.surge(on=friend)


_ALLY_HIT_IN_SIGHT = "an enemy hits your ally within your line of sight"


def _ally_hit_in_sight(world: World, me: int, ev: Event) -> bool:
    struck = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if struck is None or foe is None or struck == me:
        return False
    if team(world, struck) is not team(world, me):
        return False
    return team(world, foe) is not team(world, me) and line_of_effect(world, me, struck)


@power(
    "p7265",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_ALLY_HIT_IN_SIGHT,
    on=Trigger(Hit, when=_ally_hit_in_sight, text=_ALLY_HIT_IN_SIGHT),
)
def p7265(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power", once=True)
    c.bonus("damage", 2 + c.str_mod, on=c.me, until=When.EONT, kind="power", once=True)


@power(
    "p7500",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p7500(c: Cast) -> None:
    """The free action really is the paladin's own marking row, used again
    -- `use(..., spend=False)` is that row rather than a copy of what it
    does, so a paladin whose mark has been changed marks with the right one.

    "It immediately takes the damage your mark normally deals" is the same
    three plus Charisma the mark itself bites for.
    """
    me = c.me
    st = c.stance(label=c.ref)

    def answer(ev: Event) -> None:
        foe = getattr(ev, "attacker", None)
        if foe is None or foe == me or team(c.world, foe) is team(c.world, me):
            return
        if me in getattr(ev, "among", (getattr(ev, "target", None),)):
            return
        if c.distance(foe) > 5 or not c.may("mark that one", who=me):
            return
        if not use(c.world, me, "p805", targets=[foe], spend=False):
            return
        if getattr(ev, "vs", None) is Defense.WILL:
            c.flat(3 + c.cha_mod, dtype=DamageType.RADIANT, on=foe)

    held = c.watch(
        AttackDeclared, answer, until=When.ENCOUNTER, on=me, label=f"{c.ref} vigil"
    )
    st.on_end.append(lambda: c.world.effects.end(held, "the stance ended"))
