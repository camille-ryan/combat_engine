"""Warlord, level 5: the later books' daily attacks.

Three recurring judgements, made once here rather than in every docstring.

**"Vulnerable to that ally's attacks" is written as that ally's damage
bonus.** The damage context carries `target`, `power`, `opportunity` and
`charge` and no attacker at all, so a gate naming who is swinging is
silently false; `c.vulnerable` has no gate either. The same number reaches
the same board from the other end, and where a printed "save ends both"
binds it to something else it goes on the one hold through
`Effects.apply`, so one saving throw ends the pair.

**A standing "your allies gain ..." is a modifier per ally with a live
gate,** not a snapshot of who was in range. `c.within` answers where people
were standing when the power went off; the printed lines here -- adjacent
to you, in your line of sight, on difficult terrain -- are asked again
every time somebody rolls.

**Three rows print a weapon Requirement no chassis in `chargen` can meet**
(a reach weapon, a heavy thrown weapon) and three reach at range with a
weapon the warlord does not carry. They are declared honestly and are
simply not offered to a warlord holding a sword.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Effect,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Moved,
    OpportunityWindow,
    Ranged,
    Relation,
    Square,
    Target,
    Trigger,
    When,
    Window,
    World,
    distance,
    get,
    power,
)
from combat_engine.engine.query import adjacent, squares, team

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_ENEMY_STEPS_INTO_REACH = "an enemy enters a square within your reach"


def _friends(c: Cast, radius: int, *, of: int | None = None) -> list[int]:
    """"An ally within N squares" -- never the warlord itself."""
    return sorted(a for a in c.within(radius, of=of, side="ally") if a != c.me)


def _stand(c: Cast, who: int) -> bool:
    """Standing up is ending whatever is holding the creature down.

    Prone runs on the encounter clock, so nothing else ever takes it off;
    `actions.perform` does exactly this for the stand-up action.
    """
    floored = [e for e in c.world.effects.of(who) if Condition.PRONE in e.conditions]
    for effect in floored:
        c.world.effects.end(effect, f"{c.ref}: stands up")
    return bool(floored)


def _weapon_has(world: World, eid: int, prop: str) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and prop in gear.main.properties)


def _reach_weapon(world: World, eid: int) -> bool:
    return _weapon_has(world, eid, "reach")


def _heavy_thrown(world: World, eid: int) -> bool:
    return _weapon_has(world, eid, "heavy thrown")


def _reach_of(world: World, eid: int) -> int:
    """How far the weapon in hand can hit.

    `Weapon.reach` is 1 on every weapon `chargen` builds, including the one
    carrying the "reach" property, so the property is what says two squares.
    `movement._threat` is the other number and is the wrong one: it is how
    far the creature threatens for opportunity attacks.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return 1
    return max(weapon.reach, 2 if "reach" in weapon.properties else 1)


def _steps_into_my_reach(world: World, me: int, ev: Event) -> bool:
    """One step that finishes within reach of me, taken by an enemy.

    `Moved` is per step and carries both ends, which is the only event that
    can answer "enters a square": `MoveEnd` fires once for a whole walk and
    would miss an enemy that passed through reach and kept going.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    mine = squares(world, me)
    if not mine:
        return False
    reach = _reach_of(world, me)
    was = min(distance(ev.from_, sq) for sq in mine)
    now = min(distance(ev.to, sq) for sq in mine)
    return now <= reach < was


def _near(world: World, who: int, where: Square, radius: int = 1) -> bool:
    held = squares(world, who)
    return bool(held) and min(distance(where, sq) for sq in held) <= radius


@power(
    "p10124",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10124(c: Cast) -> None:
    """Both halves of "save ends both" go on one hold, so one saving throw
    ends the opening and the vulnerability together."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    foe = c.target
    pool = _friends(c, 5, of=foe)
    friend = c.choose(pool, "who it turns its back on") if pool else None
    if foe is None or friend is None:
        return

    def against(ctx: dict) -> bool:
        return ctx.get("target") == foe

    c.world.effects.apply(
        foe,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} opening",
        relations=[(Relation.GRANTS_CA_TO, foe, friend)],
        mods=[
            (friend, Mod(what="damage", value=c.cha_mod, kind="untyped", when=against))
        ],
    )


@power(
    "p10125",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10125(c: Cast) -> None:
    """The Effect line lands whether or not the swing did, and both halves
    of it are printed "can", so each friend is asked."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    for friend in _friends(c, 5):
        down = c.is_(Condition.UNCONSCIOUS, on=friend) or c.is_(Condition.DYING, on=friend)
        if down and c.may("try to throw it off", who=friend):
            c.save(on=friend)
        if c.is_(Condition.PRONE, on=friend) and c.may("get up", who=friend):
            _stand(c, friend)


@power(
    "p10925",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10925(c: Cast) -> None:
    """`c.no_provoke` is the wrong card twice over: it excuses the caster
    alone and it excuses everything, where this excuses a squad and only
    shooting. `dsl._survive_provoking` says why it opened the window, which
    is the one place the distinction is recorded.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        shooter = ev.provoker
        if "ranged power" not in ev.why:
            return
        if shooter != me and not (
            team(c.world, shooter) is team(c.world, me) and c.distance(shooter) <= 2
        ):
            return
        ev.cancel(f"{c.ref}: covering fire")

    c.watch(
        OpportunityWindow,
        veto,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=f"{c.ref} covering fire",
    )


@power(
    "p10926",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10926(c: Cast) -> None:
    """The Special line is a note about how the row may be *used* -- in place
    of a melee basic attack when charging -- not a row whose Effect is a
    charge, so no `charges=True`.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)

    def charging(ctx: dict) -> bool:
        return bool(ctx.get("charge"))

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=charging)
    for friend in c.allies():

        def in_sight(ctx: dict, who: int = friend) -> bool:
            return bool(ctx.get("charge")) and c.can_see(who)

        c.bonus("attack", 1, on=friend, until=When.ENCOUNTER, when=in_sight)


@power(
    "p10927",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10927(c: Cast) -> None:
    """"Whenever you hit the target with a ranged attack" is read off the
    row the `Hit` names: the attack context's `ranged` never reaches a
    watcher, and the branch matters for a two-range row.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    foe, me = c.target, c.me
    if foe is None:
        return
    step = max(c.int_mod, c.wis_mod)

    def opening(ev: Hit) -> None:
        if ev.attacker != me or ev.target != foe:
            return
        p = get(ev.power)
        if p is None or p.reach_of(getattr(ev, "branch", 0)).kind != "ranged":
            return
        pool = _friends(c, 1, of=foe)
        friend = c.choose(pool, "who takes the opening") if pool else None
        if friend is None:
            return
        if c.choose(["swing", "step"], "what that ally does") == "swing":
            c.grant_attack(friend, on=foe)
        else:
            c.shift(step, who=friend)

    c.watch(Hit, opening, until=When.ENCOUNTER, on=me, label=f"{c.ref} opening")


@power(
    "p10928",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p10928(c: Cast) -> None:
    """"Until the target is no longer affected by this power" is the hold
    itself, so the extra damage is granted for the encounter and gated on
    that hold still being live -- an attacker's modifier cannot carry the
    target's save-ends clock without handing the attacker the saving throw.
    """
    victim = c.target
    if victim is None:
        return
    squad = [c.me, *c.allies()]
    hold: Effect | None = None
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        hold = c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=f"{c.ref} undone",
            conditions=[Condition.WEAKENED],
            relations=[(Relation.GRANTS_CA_TO, victim, who) for who in squad],
        )
        extra, until = 5, When.ENCOUNTER
    else:
        c.weakened(until=When.EONT, on=victim)
        c.grants_advantage(on=victim, to="allies", until=When.EONT)
        extra, until = 2, When.EONT

    def against(ctx: dict) -> bool:
        if ctx.get("target") != victim:
            return False
        return hold is None or not hold.ended

    for who in squad:
        c.bonus("damage", extra, on=who, until=until, when=against, kind="untyped")


@power(
    "p10929",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10929(c: Cast) -> None:
    """"Any ally adjacent to you" is asked when the blow arrives, not now:
    the warlord moves and so do they."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    for friend in c.allies():

        def beside(ctx: dict, who: int = friend) -> bool:
            return c.adjacent(who)

        for defence in (AC, REF):
            c.bonus(defence, 2, on=friend, until=When.ENCOUNTER, when=beside)


def _second_wind(c: Cast, who: int) -> bool:
    """One second wind, taken by somebody else off the warlord's action.

    `actions.perform` owns the only other copy: a use counted in `Powers`, a
    surge, and +2 to AC until the start of that creature's next turn. There
    is no `Cast` door to it, and a bare `c.surge` would leave the use
    uncounted, so a creature could take a second one of its own afterwards.
    """
    from combat_engine.engine import Powers

    known = c.world.get(who, Powers)
    if known is None or known.times("second-wind"):
        return False
    known.note_use("second-wind", c.world.round)
    if not c.surge(on=who):
        return False
    c.bonus(AC, 2, on=who, until=When.SONT, kind="untyped")
    return True


@power(
    "p11609",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p11609(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    pool = set(_friends(c, 1)) | set(_friends(c, 1, of=c.target))
    for friend in sorted(pool):
        if c.may("take a second wind", who=friend):
            _second_wind(c, friend)


@power(
    "p11723",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11723(c: Cast) -> None:
    """`c.charge_at` is the move *and* the charge flag: `c.grant_attack`
    alone would hand the second ally a swing from wherever it happens to be
    standing, which is the half of the printed line that does not matter.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    near = _friends(c, 1, of=foe)
    runner = c.choose(near, "who steps clear") if near else None
    if runner is not None:
        c.shift(c.speed_of(runner), who=runner)
    pool = [a for a in _friends(c, 5) if a != runner and c.can_see(a)]
    charger = c.choose(pool, "who charges it") if pool else None
    if charger is not None:
        c.charge_at(foe, who=charger)


@power(
    "p16517",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p16517(c: Cast) -> None:
    """`World.difficult` folds the map and every live zone together, which
    is what "on difficult terrain" has to mean -- a zone of rubble counts
    and the grid's own dictionary does not know about it."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slide(3)
        if c.there in c.world.difficult():
            c.prone()
    else:
        c.half_damage(c.w(2), c.str_mod)

    def on_rough(ctx: dict) -> bool:
        who = ctx.get("target")
        rough = c.world.difficult()
        return who is not None and bool(squares(c.world, who) & rough)

    for friend in [c.me, *c.allies()]:
        c.bonus("attack", 2, on=friend, until=When.ENCOUNTER, when=on_rough)


@power(
    "p2451",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*MARTIAL_WEAPON, Keyword.STANCE],
)
def p2451(c: Cast) -> None:
    """The listener hangs off the stance rather than carrying `When.STANCE`
    itself -- a second stance-clocked effect confuses `Effects.stance_of`,
    which `fighter/level_5.py` settled.

    The 1[W] is rolled and dealt flat: `c.damage` maxes its dice on a
    critical, and the critical it would read is whatever the last attack
    this `Cast` rolled was, which is somebody else's miss.
    """
    me = c.me
    stance = c.stance(label=c.ref)

    def punish(ev: Miss) -> None:
        foe, friend = ev.attacker, ev.target
        if foe == me or team(c.world, foe) is team(c.world, me):
            return
        if not adjacent(c.world, me, foe):
            return
        if friend == me or team(c.world, friend) is not team(c.world, me):
            return
        marked = c.build("tactical") and any(c.marked(on=foe, by=a) for a in c.allies())
        c.flat(c.roll(c.w(1)) + c.int_mod if marked else c.int_mod, on=foe)

    watching = c.watch(Miss, punish, until=When.ENCOUNTER, on=me, label=f"{c.ref} reprisal")
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))


@power(
    "p2530",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=[Keyword.MARTIAL],
)
def p2530(c: Cast) -> None:
    """No attack of the warlord's own: the whole row is everybody else's
    swing, and the pool each of them may swing at is whatever bloodied enemy
    it is already standing next to."""
    friend = c.target
    if friend is None:
        return
    prey = sorted(f for f in c.within(1, of=friend, side="enemy") if c.bloodied(f))
    victim = c.choose(prey, "who that ally finishes") if prey else None
    if victim is not None and c.may("take a free swing", who=friend):
        c.grant_attack(friend, on=victim)


@power(
    "p2534",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p2534(c: Cast) -> None:
    """"As an opportunity action" is `c.provoke`, not `c.grant_attack`: the
    window is the ally's to answer or decline, and answering costs it the
    opportunity action it would otherwise have kept.
    """
    if not c.strike():
        c.half_damage(c.w(1), c.str_mod)
        return
    c.damage(c.w(1), c.str_mod)
    if not c.push(1):
        return
    for friend in _friends(c, 1, of=c.target):
        c.provoke(friend, on=c.target, why=f"{c.ref}: shoved into reach")


@power(
    "p4558",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_reach_weapon,
    requires_text="needs a reach weapon",
    trigger=_ENEMY_STEPS_INTO_REACH,
    on=Trigger(Moved, when=_steps_into_my_reach, text=_ENEMY_STEPS_INTO_REACH),
)
def p4558(c: Cast) -> None:
    """The standing Effect is a square wider than the trigger and a square
    narrower than the weapon: it is adjacency to the warlord or to somebody
    beside it, which is what the printed line says rather than reach.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    me = c.me

    def sting(ev: Moved) -> None:
        foe = ev.actor
        if foe == me or team(c.world, foe) is team(c.world, me):
            return
        beside_me = _near(c.world, me, ev.to)
        shield = [a for a in c.allies() if adjacent(c.world, me, a)]
        if not beside_me and not any(_near(c.world, a, ev.to) for a in shield):
            return
        c.flat(c.str_mod, on=foe)

    c.watch(Moved, sting, until=When.ENCOUNTER, on=me, label=f"{c.ref} bristle")


@power(
    "p4559",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
    requires=_heavy_thrown,
    requires_text="needs a heavy thrown weapon",
)
def p4559(c: Cast) -> None:
    """"When hitting with combat advantage" cannot be a damage modifier: the
    damage context carries no `advantage`, so the gate would be silently
    false. It is read off the `Hit` instead, where the live `AttackResult`
    still says what the roll had.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    me = c.me
    squad = {me, *_friends(c, 10)}

    def press(ev: Hit) -> None:
        if ev.attacker not in squad or not c.had_advantage(ev):
            return
        # Resourceful Presence. `chargen` names no such build, so this is
        # inert until one exists -- the plain rider is the printed default.
        extra = c.roll(c.w(1)) if c.build("resourceful") else 0
        c.flat(extra + c.int_mod, on=ev.target)

    c.watch(Hit, press, until=When.EONT, on=me, label=f"{c.ref} pressed")
