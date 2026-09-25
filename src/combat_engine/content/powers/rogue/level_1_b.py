"""Rogue, level 1, the rows printed after the first book.

`level_1.py` holds the nine that came first; these are the rest, and the
file is split rather than grown because the two together run past a
thousand lines.

Three notes apply across the whole batch.

**Sneak attack is not in the model.** A dozen of these rows carry a rider
about it -- "you may deal your sneak attack damage even without combat
advantage", "if you don't apply your sneak attack, 1d6 extra". There is no
sneak attack to permit, so a permissive rider is inert and its negative
twin (the 1d6) simply always applies, which is what the absence of the
feature actually means.

**The rattling keyword does not exist.** `Keyword` has no member for it and
nothing implements the attack penalty it carries, so the rows printed with
it are declared with the keywords the engine has. Rows whose *content* is
rattling are left out and listed.

**The second fork.** `chargen` records two rogue builds, `brawny` and
`trickster`. The Strength rider is `brawny`'s and the Charisma rider is
`trickster`'s; the Intelligence one belongs to a leg the model does not
have, so those rows are the base line only.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Powers,
    Ranged,
    Relation,
    Trigger,
    UpTo,
    When,
    Window,
    World,
    by_melee,
    get,
    power,
)
from combat_engine.engine.events import RelationSet
from combat_engine.engine.query import (
    can_act,
    creatures,
    distance_between,
    has_combat_advantage,
    hidden_from,
    team,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})
MISSILE_GROUPS = frozenset({"crossbow", "sling"})

#: What holds a creature well enough that a row saying "you escape" has
#: something to escape from.
_HELD = (Condition.GRABBED, Condition.RESTRAINED)


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


def _rogue_missile(world: World, eid: int) -> bool:
    """"A crossbow, a light thrown weapon, or a sling."

    The engine's weapons carry no thrown flag -- what a thrown one has is a
    `ranged` band -- so a light blade counts only when it has one, the
    reading `level_7.py` settled.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return False
    return weapon.group in MISSILE_GROUPS or (
        weapon.is_light_blade and weapon.ranged is not None
    )


def _sling(world: World, eid: int) -> bool:
    """Both hands are asked. A sling is fired, so it is `gear.ranged` and
    not `gear.main` -- a creature with a blade in the other hand answers
    `main` with the blade, and the requirement would never be met."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return any(w.group == "sling" for w in (gear.main, gear.ranged) if w is not None)


def _somebody_grants_me_ca(world: World, eid: int) -> bool:
    """"Target: one creature granting combat advantage to you."

    A target filter with no header field, so it is declared as the caster's
    Requirement -- is there such a creature at all -- and checked again
    against the chosen one in the body.
    """
    from combat_engine.engine.query import enemies

    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _escape_grab(c: Cast) -> None:
    """Whatever is holding the caster stops holding it. The reading
    `level_10.py` settled: a grab is a relation held up by an effect, so
    ending the effect is the escape."""
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


def _hits_this_use(c: Cast) -> int:
    """How many targets this use of this row has hit so far.

    The body is called once per target with one `Cast`, so a tally cannot
    live in a local. The log can answer it: `c.used()` stamps a `PowerUsed`
    at the start of the use, and every `Hit` after it belongs to this one.
    """
    log = c.world.bus.log
    start = 0
    for i in range(len(log) - 1, -1, -1):
        e = log[i]
        if e.kind == "PowerUsed" and getattr(e, "power", "") == c.ref:
            start = i
            break
    return sum(
        1
        for e in log[start:]
        if e.kind == "Hit"
        and getattr(e, "attacker", None) == c.me
        and getattr(e, "power", "") == c.ref
    )


def _i_bloodied_it(world: World, me: int, ev: Event) -> bool:
    """"You bloody an enemy with a melee attack."

    `Bloodied` names only the creature that crossed the line -- no source,
    no power -- so who did it is read off the `DamageApplied` that caused
    it, which is the event immediately before it in the log.
    """
    who = getattr(ev, "actor", None)
    if who is None or team(world, who) is team(world, me):
        return False
    for e in reversed(world.bus.log):
        if e.kind == "DamageApplied" and getattr(e, "target", None) == who:
            return getattr(e, "source", None) == me and by_melee(world, me, e)
    return False


@power(
    "p10165",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10165(c: Cast) -> None:
    """No weapon dice at all: the damage line is the modifier alone."""
    if c.strike():
        c.damage(0, c.dex_mod)
        c.slide(1)
        c.shift(1)


@power(
    "p10166",
    level=1,
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
def p10166(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if c.first:
        c.bonus(AC, c.cha_mod, on=c.me)
        c.bonus(REF, c.cha_mod, on=c.me)


@power(
    "p10167",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10167(c: Cast) -> None:
    """The stance and the interrupt it grants are printed as two cards under
    one id, and the registry holds one row per id -- so the swing is folded
    into the stance and offered as the printed **can** each time it comes up.

    The listener hangs on the stance's own effect rather than on a clock of
    its own, so taking another stance takes the riposte with it.
    """
    stance = c.stance()
    me = c.me

    def riposte(ev: AttackDeclared) -> None:
        if ev.target != me or ev.attacker == me or not c.adjacent(ev.attacker):
            return
        if not c.may("strike back", who=me):
            return
        if c.attack(c.dex_, REF, on=ev.attacker):
            c.damage(c.w(1), c.dex_mod, on=ev.attacker)

    stance.subs.append(c.world.bus.on(AttackDeclared, riposte, owner=me))


@power(
    "p10732",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10732(c: Cast) -> None:
    """"Before or after the attack": before is the half that can be taken
    here, since the shift has to be decided before the swing is rolled."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        _escape_grab(c)


@power(
    "p10733",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10733(c: Cast) -> None:
    """The Stealth check is not rolled -- the model has no skills -- so what
    is left of it is the concealment it buys."""
    if c.strike():
        c.damage(c.w(1))
    if c.first:
        if c.int_mod > 0:
            c.shift(c.int_mod)
        c.hide()


@power(
    "p10734",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10734(c: Cast) -> None:
    if c.strike():
        c.damage(0, c.dex_mod + c.int_mod)
        c.grants_advantage()


@power(
    "p10735",
    level=1,
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
def p10735(c: Cast) -> None:
    """Moving through the squares of the enemies hit is not expressible --
    a shift is a shift -- so what is written is its distance."""
    if c.target is None or not c.can_see(c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    if c.last:
        hit = _hits_this_use(c)
        if hit and c.may("shift away", who=c.me):
            c.shift(hit)


@power(
    "p10736",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10736(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.dex_mod)
    beside = sorted(a for a in c.allies() if c.adjacent_to(victim, a))
    if beside:
        friend = c.choose(beside, "who the opening is for")
        if friend is not None:
            c.grants_advantage(to=friend)


@power(
    "p10737",
    level=1,
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
def p10737(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1))


@power(
    "p10738",
    level=1,
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
def p10738(c: Cast) -> None:
    """Attacking gives a hiding creature away, so "remain hidden" is said by
    hiding again from whoever could not see the rogue when it swung."""
    unseeing = sorted(hidden_from(c.world, c.me))
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    for watcher in unseeing:
        c.hide(from_=watcher)


@power(
    "p10739",
    level=1,
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
def p10739(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.dex_mod)
    nearby = sorted(
        f
        for f in c.enemies()
        if f != victim and distance_between(c.world, victim, f) <= 10
    )
    if not nearby:
        return
    second = c.choose(nearby, "where the shot goes next")
    if second is None:
        return
    if c.attack(c.dex_, AC, on=second):
        c.damage(0, c.dex_mod, on=second)
        c.dazed(on=second)


@power(
    "p10741",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10741(c: Cast) -> None:
    """"You do not expend this power" is `Powers.unuse`, the same door the
    Reliable keyword goes through. The use is spent before the body runs, so
    giving it back here is the whole of it.

    The push is anchored on the target rather than on the rogue, because the
    printed line says away from *the target*.
    """
    victim = c.target
    unseen = victim is not None and c.is_hidden(from_=victim)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    elif unseen:
        powers = c.world.get(c.me, Powers)
        if powers is not None:
            powers.unuse(c.ref)
    if victim is None:
        return
    centre = c.there
    for foe in c.enemies():
        if foe == victim or not c.adjacent_to(victim, foe):
            continue
        c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)
        c.push(1, on=foe, anchor=centre)


@power(
    "p10742",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10742(c: Cast) -> None:
    c.shift(c.speed_of())
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)
    c.shift(c.speed_of())


@power(
    "p10743",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10743(c: Cast) -> None:
    """Nothing in the model holds concealment as a state between two
    creatures. What concealment buys against that one creature is the -2 on
    its attack rolls, so that is what the hold is written as.
    """
    victim, me = c.target, c.me
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        until = When.SAVE_ENDS
    else:
        c.half_damage(c.w(2), c.dex_mod)
        until = When.EONT
    if victim is not None:
        c.penalty(
            "attack", 2, on=victim, until=until,
            when=lambda ctx: ctx.get("target") == me,
        )


@power(
    "p13217",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p13217(c: Cast) -> None:
    """The Effect line is drawing an item from a pouch, which the model has
    no inventory to do."""
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p2248",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p2248(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p2253",
    level=1,
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
def p2253(c: Cast) -> None:
    """The rider immobilises a target already carrying the penalty from one
    of the rogue's rattling attacks. Neither the keyword nor the build that
    names it is in the model, so this is the base line."""
    if c.strike():
        c.damage(c.w(1), c.dex_mod + c.cha_mod)


@power(
    "p2254",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p2254(c: Cast) -> None:
    """The Special line -- usable in place of a melee basic when charging --
    has no header field; `Powers.basic` names one row and this is not it."""
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.shift(2)


@power(
    "p2503",
    level=1,
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
def p2503(c: Cast) -> None:
    """A mark is a relation, so negating the ones the target has applied is
    clearing them. "Cannot mark any targets" has no switch to throw, so it is
    written as the relation being taken off again the moment it is set.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        if victim is not None:
            for marked in c.world.relations.targets(Relation.MARKED_BY, victim):
                c.world.relations.clear(Relation.MARKED_BY, victim, marked, c.ref)

            def undo(ev: RelationSet) -> None:
                if ev.kind_ is Relation.MARKED_BY and ev.source == victim:
                    c.world.relations.clear(
                        Relation.MARKED_BY, victim, ev.target, c.ref
                    )

            c.watch(RelationSet, undo, until=When.EONT, label=f"{c.ref} no marks")
    if c.first:
        c.shift(1)


@power(
    "p2504",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_somebody_grants_me_ca,
    requires_text="needs a creature granting you combat advantage",
)
def p2504(c: Cast) -> None:
    """The 1d6 is printed for an attack that does *not* carry sneak attack
    damage. The model has no sneak attack, so it never does, and the die
    always lands. Rolled through `c.damage` rather than `c.flat` so a
    critical maxes it with the rest of the line, which is the printed rule.
    """
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if c.strike():
        extra = c.str_mod if c.build("brawny") else 0
        c.damage(c.w(1), c.dex_mod + extra)
        c.damage("1d6")
        c.grants_advantage()


@power(
    "p2515",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p2515(c: Cast) -> None:
    """The Effect line is the *target* swinging, which is `c.grant_attack`
    rather than anything the rogue rolls."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.dex_mod)
    prey = sorted(
        x for x in creatures(c.world) if x != victim and c.adjacent_to(victim, x)
    )
    if not prey:
        return
    pick = c.choose(prey, "who the target is turned on")
    if pick is not None:
        c.grant_attack(victim, on=pick)


@power(
    "p4468",
    level=1,
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
def p4468(c: Cast) -> None:
    """The secondary is an interrupt, so it is armed in the `Window.BEFORE`
    half of `AttackDeclared`: the -2 has to reach the triggering roll, and by
    the reaction window that roll has been made.

    The latch is kept by hand rather than with `once=True`, which would burn
    on an attack aimed at somebody else.
    """
    victim, me = c.target, c.me
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if victim is None:
        return
    spent: list[bool] = []

    def riposte(ev: AttackDeclared) -> None:
        row = get(ev.power)
        if spent or ev.attacker != victim or ev.target != me:
            return
        if row is None or row.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        spent.append(True)
        c.penalty(
            "attack", 2, on=victim, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("target") == me,
        )
        if c.attack(c.str_, AC, on=victim):
            c.damage(c.w(1), c.str_mod, on=victim)

    c.watch(
        AttackDeclared, riposte, until=When.SONT,
        window=Window.BEFORE, label=f"{c.ref} riposte",
    )


@power(
    "p4469",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p4469(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.push(1)


@power(
    "p4470",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p4470(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed()


@power(
    "p4471",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4471(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.dex_mod)
        c.penalty("attack", 2, until=When.EOTNT)


@power(
    "p4472",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4472(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)


@power(
    "p4473",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="you bloody an enemy with a melee attack",
    on=Trigger(Bloodied, _i_bloodied_it, "you bloody an enemy with a melee attack"),
)
def p4473(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p6593",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p6593(c: Cast) -> None:
    """"You have combat advantage against the target **while it is slowed by
    this attack**" is one hold, not two: the opening ends when the slow does,
    so both ride on a single effect and a single saving throw.
    """
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(1), c.dex_mod)
        return
    c.damage(c.w(1), c.dex_mod)
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} slowed and open",
        conditions=(Condition.SLOWED,),
        relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
    )


@power(
    "p7388",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p7388(c: Cast) -> None:
    """"Able to attack it" is `can_act`, which is the printed rule flanking
    uses for the same sentence."""
    victim = c.target
    helped = victim is not None and any(
        c.adjacent_to(victim, mate) and can_act(c.world, mate) for mate in c.allies()
    )
    if c.strike(advantage=True if helped else None):
        c.damage(c.w(1), c.dex_mod)


@power(
    "p7396",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p7396(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    if victim is not None:
        c.bonus(
            "attack", 1, on=c.me, until=When.EONT, once=True,
            when=lambda ctx: ctx.get("target") == victim,
        )
