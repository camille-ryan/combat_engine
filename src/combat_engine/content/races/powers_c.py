"""Racial powers, the third batch.

Filed by the race ref in `cls`, which is what the compendium's Class column
holds for these rows. Nothing here needs a race *model*: a racial power is an
ordinary row and the only thing that makes it racial is who is given it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Dropped,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    SavingThrow,
    Size,
    SkillCheck,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    about_me,
    both,
    by_me,
    by_melee,
    check_failed,
    get,
    my_check,
    not_me,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.query import squares

if TYPE_CHECKING:
    from combat_engine.engine import World

def _bloodied(world: World, eid: int) -> bool:
    """"Requirement: you must be bloodied", asked of a creature on a board."""
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _storm(ctx: dict[str, Any]) -> bool:
    """Is the row rolling damage a thunder or a lightning one?

    The damage context carries the ref and not the keywords, so the keyword
    half is a registry lookup -- the same shape `features/strikers.py` uses.
    """
    row = get(ctx.get("power") or "")
    return row is not None and bool(
        {Keyword.THUNDER, Keyword.LIGHTNING} & set(row.keywords)
    )


def _melee_hit_on_me(c: Cast, ev: Any) -> bool:
    """An adjacent creature hit or missed the caster with a melee attack."""
    row = get(getattr(ev, "power", "") or "")
    return (
        getattr(ev, "target", None) == c.me
        and c.adjacent(ev.attacker)
        and row is not None
        and getattr(row.reach, "kind", "") == "melee"
    )


# -- r1 ---------------------------------------------------------------------


@power(
    "p1448",
    level=0,
    cls="r1",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    attack=Attack(CON, vs=REF, plus=2),
    dropped=("Attack.by_choice",),
)
def p1448(c: Cast) -> None:
    """The card binds the attack to Strength, Constitution or Dexterity at
    character creation; the header holds one, and Constitution is the score
    the damage line names anyway. The damage type is the other half of that
    one choice and `c.element` is where it is recorded."""
    if c.strike():
        c.damage("1d6", c.con_mod, dtype=c.element(on=c.me) or DamageType.UNTYPED)


@power(
    "p16381",
    level=10,
    cls="r1",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage of the type you chose for your p1448 power",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
)
def p16381(c: Cast) -> None:
    """The bound type is read off the build, the way `p1448` reads it. A
    character who never bound one takes the resistance against whatever is
    landing, which is the only reading left."""
    ev = c.trigger
    took = getattr(ev, "dtype", None)
    mine = c.element(on=c.me)
    if took is None or (mine is not None and took is not mine):
        return
    c.resist(5 + c.level // 2, took, until=When.ENCOUNTER, on=c.me)


# -- r2 ---------------------------------------------------------------------


@power(
    "p13211",
    level=0,
    cls="r2",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p13211(c: Cast) -> None:
    """`c.second_wind` is the one door, so the use is counted and the +2 to
    all defences comes with it; `cost` is the printed minor."""
    c.second_wind(on=c.me, cost=ActionType.MINOR)


@power(
    "p14383",
    level=2,
    cls="r2",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you successfully bull rush a target",
    todo=("c.bull_rush()",),
)
def p14383(c: Cast) -> None:
    """Nothing in the engine is a bull rush, so neither the trigger nor the
    extra squares of push can be declared."""


# -- r3 ---------------------------------------------------------------------


@power(
    "p16039",
    level=6,
    cls="r3",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="an enemy misses you with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you with a melee attack"),
)
def p16039(c: Cast) -> None:
    c.teleport(5)


# -- r4 ---------------------------------------------------------------------


@power(
    "p16043",
    level=6,
    cls="r4",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16043(c: Cast) -> None:
    """The tracking half is not on a board. The allies' share of the Stealth
    bonus is an aura rather than a sweep of whoever happens to be beside you
    now, because the card says "allies adjacent to you" and that moves."""
    c.stance(on=c.me, label=c.ref)
    c.bonus("skill:stealth", 2, kind="power", on=c.me, until=When.STANCE)
    ring = c.aura(1, until=When.STANCE)
    c.grants_in(ring, "skill:stealth", 2, side="ally")


# -- r5 ---------------------------------------------------------------------


@power(
    "p1452",
    level=0,
    cls="r5",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p1452(c: Cast) -> None:
    """`keep="new"` is the printed "even if it is lower"."""
    c.reroll_attack(keep="new")


@power(
    "p14391",
    level=2,
    cls="r5",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="a creature you can see starts its turn",
    on=Trigger(TurnStart, not_me, "a creature other than you starts its turn"),
    dropped=("triggers.seen_by_me",),
)
def p14391(c: Cast) -> None:
    """No predicate narrows a trigger to what the responder can see."""
    c.shift(2)


# -- r6 ---------------------------------------------------------------------


@power(
    "p14387",
    level=2,
    cls="r6",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.aid_another()",),
)
def p14387(c: Cast) -> None:
    """The aid another action is not in the menu, so what it would grant --
    +2 to the ally's next attack -- is laid directly."""
    mate = c.choose([a for a in c.allies() if c.adjacent(a)], "who to aid")
    if mate is not None:
        c.bonus("attack", 2, on=mate, until=When.EONT, once=True)


# -- r7 ---------------------------------------------------------------------


@power(
    "p14395",
    level=2,
    cls="r7",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a saving throw and dislike the result",
    on=Trigger(SavingThrow, about_me, "you make a saving throw"),
)
def p14395(c: Cast) -> None:
    """The penalty is laid after the reroll so it cannot eat its own bonus,
    and `once=True` is the printed "the next saving throw"."""
    c.reroll_save(bonus=2)
    c.penalty("save", 2, on=c.me, until=When.ENCOUNTER, once=True)


# -- r8 ---------------------------------------------------------------------


@power(
    "p16389",
    level=10,
    cls="r8",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def p16389(c: Cast) -> None:
    burn = c.cha_mod
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, kind="power", on=c.me, until=When.EONT)

    def scald(ev: Hit) -> None:
        if _melee_hit_on_me(c, ev):
            c.flat(burn, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, scald, until=When.EONT)


# -- r14 --------------------------------------------------------------------


@power(
    "p7546",
    level=0,
    cls="r14",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p7546(c: Cast) -> None:
    """Opposed by passive Insight, which is what `c.passive` is for."""
    if c.check("bluff", c.passive("insight", of=c.target)):
        c.grants_advantage(until=When.EONT, to=c.me)


# -- r16 --------------------------------------------------------------------


@power(
    "p1831",
    level=0,
    cls="r16",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(CHA, vs=REF, plus=4),
    dropped=("Attack.by_choice", "c.ignore_concealment()"),
)
def p1831(c: Cast) -> None:
    """"All attacks against the target" is written as the caster's side,
    which is every attacker that matters on a two-sided board. Cover is
    taken off the target for everybody; concealment has no such reader."""
    if c.strike():
        c.grants_advantage(to="allies", until=When.EONT)
        c.no_cover(until=When.EONT)


@power(
    "p2473",
    level=0,
    cls="r16",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    dropped=("c.blind_in(zone)",),
)
def p2473(c: Cast) -> None:
    """The cloud blocks sight for everyone, which is terrain and so is a
    zone. Blinding is laid on whoever is standing in it as it forms: nothing
    blinds by occupancy, and the caster is exempt either way."""
    c.zone(c.area(), until=When.EONT, blocks_sight=True)
    for who in c.in_squares(c.area()):
        if who != c.me:
            c.blinded(on=who, until=When.EONT)


@power(
    "p16032",
    level=2,
    cls="r16",
    usage=AT_WILL,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def p16032(c: Cast) -> None:
    """Dim light and nothing else: the forms have no hit points, block
    nothing and are not creatures."""


@power(
    "p16035",
    level=6,
    cls="r16",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit while you have cover or concealment from the attacker",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p16035(c: Cast) -> None:
    """`Hit` is a decision, so beating the attack roll refuses it outright.
    The live `AttackResult` rides on the event and carries the total."""
    ev = c.trigger
    if ev is None:
        return
    result = getattr(ev, "result", None)
    if c.check("stealth").total <= getattr(result, "total", 0):
        return
    ev.cancel("went unseen")
    c.grants_advantage(on=ev.attacker, to=c.me, until=When.EONT)


# -- r19 --------------------------------------------------------------------


@power(
    "p2476",
    level=0,
    cls="r19",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def p2476(c: Cast) -> None:
    """The extra damage is gated on charging rather than added by hand, so
    it lands on whichever swing the run ends in."""
    extra = 4 if c.bloodied(on=c.me) else 2
    c.bonus("damage", extra, on=c.me, until=When.EOT, when=lambda ctx: ctx["charge"])
    if extra == 4:
        c.temp_hp(extra, on=c.me)
    foe = c.target
    if foe is not None:
        c.charge_at(foe)


# -- r21 --------------------------------------------------------------------


@power(
    "p16460",
    level=2,
    cls="r21",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you fail a Bluff, Diplomacy or Intimidate check",
    on=Trigger(
        SkillCheck,
        both(my_check("bluff", "diplomacy", "intimidate"), check_failed),
        "you fail one of three checks",
    ),
    dropped=("c.reroll_check(skill=)",),
)
def p16460(c: Cast) -> None:
    """Rolling the other two under the Bluff modifier needs a reroll that
    can change which skill is being rolled."""
    c.reroll_check()


@power(
    "p16463",
    level=10,
    cls="r21",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16463(c: Cast) -> None:
    """The shift has to finish beside the chosen creature, so the square is
    named rather than left to the mover. Medium or larger is everything but
    the two small categories."""
    big = [
        foe
        for foe in c.enemies()
        if c.adjacent(foe) and c.size_of(on=foe) not in (Size.TINY, Size.SMALL)
    ]
    foe = c.choose(big, "which creature to circle")
    if foe is None:
        return
    here = c.here
    beside = sorted(
        spread(squares(c.world, foe), 1),
        key=lambda s: abs(s[0] - here[0]) + abs(s[1] - here[1]),
        reverse=True,
    )
    for square in beside:
        if square != here and c.shift(5, to=square):
            return


# -- r22 --------------------------------------------------------------------


@power(
    "p16634",
    level=2,
    cls="r22",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
)
def p16634(c: Cast) -> None:
    """Sleep is held as unconscious, which is the condition the engine has
    for it."""
    c.temp_hp(5)
    c.cure(Condition.UNCONSCIOUS)
    if c.is_(Condition.PRONE):
        c.grant_action("stand", FREE, until=When.EOTNT)


# -- r23 --------------------------------------------------------------------


@power(
    "p16466",
    level=6,
    cls="r23",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.ignore_squeeze_penalty()",),
)
def p16466(c: Cast) -> None:
    pace = c.speed_of()
    c.mode("climb", pace, until=When.EOT)
    c.move(pace)


# -- r24 --------------------------------------------------------------------


@power(
    "p2480",
    level=0,
    cls="r24",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(STR, vs=AC, plus=4),
)
def p2480(c: Cast) -> None:
    """`c.run_at` covers the ground without swinging, because this row's own
    attack is what lands at the end of the run in place of the basic one.
    The card offers Strength, Constitution or Dexterity; the header holds
    one and the damage line follows whichever it is."""
    foe = c.target
    if foe is not None:
        c.run_at(foe)
    if c.strike():
        c.damage("1d6", c.str_mod)
        c.prone()


# -- r27 --------------------------------------------------------------------


@power(
    "p2483",
    level=0,
    cls="r27",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p2483(c: Cast) -> None:
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)
    c.regeneration(2, until=When.ENCOUNTER, while_bloodied=True)


# -- r33 --------------------------------------------------------------------


@power(
    "p1769",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
)
def p1769(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d8", on=c.me, until=When.EONT, when=_storm)


@power(
    "p10045",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
)
def p10045(c: Cast) -> None:
    """Only *starting* a turn beside you bites, so this is a watcher rather
    than `c.burns`, which also bites on entering. Allies are caught too --
    the card says any creature."""

    def bite(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor != c.me and c.adjacent(ev.actor):
            c.flat(5, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnStart, bite, until=When.EONT)


@power(
    "p14074",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.POLYMORPH],
    dropped=("c.immovable(optional=)",),
)
def p14074(c: Cast) -> None:
    """Immunity to fire is resistance large enough to swallow any heroic
    burn. The ability choice takes the best of the three, which is what a
    player picks. The aura bites at the *end* of a turn, which `c.burns`
    does not do, so it is a watcher over the aura's occupants."""
    burn = max(c.str_mod, c.con_mod, c.dex_mod)
    c.form(conditions=[Condition.SLOWED], until=When.EONT, label=c.ref)
    c.resist(100, DamageType.FIRE, until=When.EONT, on=c.me)
    c.immovable(until=When.EONT)
    c.aura(1, until=When.EONT)

    def scorch(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor != c.me and c.in_my_aura(ev.actor):
            c.flat(burn, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.EONT)


# -- r35 --------------------------------------------------------------------


@power(
    "p6186",
    level=0,
    cls="r35",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an attack roll, a saving throw, a skill check or an "
    "ability check and dislike the result",
    on=Trigger(SkillCheck, about_me, "you make a skill check"),
    dropped=("c.boost_attack()", "c.boost_save()"),
)
def p6186(c: Cast) -> None:
    """Only the skill-check branch can be answered once the die is down:
    `c.boost_check` is the one verb that reaches a settled roll."""
    c.boost_check(c.roll("1d6"))


# -- r36 --------------------------------------------------------------------


@power(
    "p16385",
    level=10,
    cls="r36",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you hit a bloodied enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p16385(c: Cast) -> None:
    """`Hit` announces before the damage, so the victim being bloodied is
    read as the card means it -- bloodied when you hit it, not after."""
    ev = c.trigger
    if ev is None or not c.bloodied(on=ev.target):
        return
    c.surge(on=c.me)
    c.save(on=c.me, bonus=2)


@power(
    "p16689",
    level=10,
    cls="r36",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2),
)
def p16689(c: Cast) -> None:
    """"Who can hear you" has no reading on the board."""
    c.save()


# -- r38 --------------------------------------------------------------------


@power(
    "p16639",
    level=2,
    cls="r38",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16639(c: Cast) -> None:
    """Hit or miss both pay, so the same watcher is armed on each."""
    back = 3 + c.level // 2
    c.stance(on=c.me, conditions=[Condition.SLOWED], label=c.ref)
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, on=c.me, until=When.STANCE)

    def spite(ev: Any) -> None:
        if _melee_hit_on_me(c, ev):
            c.flat(back, on=ev.attacker)

    c.watch(Hit, spite, until=When.STANCE)
    c.watch(Miss, spite, until=When.STANCE)


# -- r42 --------------------------------------------------------------------


@power(
    "p27",
    level=0,
    cls="r42",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(CON, vs=AC, plus=2),
    dropped=("c.ongoing(with_=)",),
)
def p27(c: Cast) -> None:
    """"Save ends both" is one throw over two clauses; they are laid as two
    effects here and so are saved against separately."""
    if c.strike():
        c.damage("1d8", c.con_mod, dtype=DamageType.POISON)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
        c.ongoing(2, DamageType.POISON, until=When.SAVE_ENDS)


# -- r43 --------------------------------------------------------------------


@power(
    "p16541",
    level=0,
    cls="r43",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.aid_another()",),
)
def p16541(c: Cast) -> None:
    """Two printed choices, offered as one. The second is the aid another
    action, which the menu has not got, so its +3 is laid directly."""
    exposed = [
        foe
        for foe in c.enemies()
        if any(c.adjacent_to(foe, mate) for mate in c.allies())
    ]
    mates = [mate for mate in c.allies() if c.adjacent(mate)]
    options = [
        word
        for word, pool in (("expose", exposed), ("aid", mates))
        if pool
    ]
    pick = c.choose(options, "which benefit")
    if pick == "expose":
        foe = c.choose(exposed, "which enemy")
        if foe is not None:
            c.grants_advantage(on=foe, to=c.me, until=When.SONT)
    elif pick == "aid":
        mate = c.choose(mates, "who to aid")
        if mate is not None:
            c.bonus("attack", 3, on=mate, until=When.EONT, once=True)


@power(
    "p16544",
    level=6,
    cls="r43",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW],
    dropped=("c.end_effect()",),
)
def p16544(c: Cast) -> None:
    """"Until you attack" needs an effect a body can end; the clock half of
    the duration stands."""
    c.conceal(on=c.me, until=When.EONT, total=True)


# -- r44 --------------------------------------------------------------------


@power(
    "p7441",
    level=0,
    cls="r44",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy with a close or area attack",
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p7441(c: Cast) -> None:
    """The close-or-area half of the trigger is asked of the row that hit,
    which `Hit` names, rather than of a predicate that cannot see it."""
    ev = c.trigger
    if ev is None:
        return
    row = get(getattr(ev, "power", "") or "")
    shape = getattr(getattr(row, "reach", None), "kind", "")
    if shape not in ("close_burst", "close_blast", "area_burst"):
        return
    c.teleport(3)
    c.grants_advantage(on=ev.target, to=c.me, until=When.EONT)
    mate = c.choose([a for a in c.allies() if c.can_see(a)], "which ally")
    if mate is not None:
        c.grants_advantage(on=ev.target, to=mate, until=When.EONT)


# -- r50 --------------------------------------------------------------------


@power(
    "p11738",
    level=0,
    cls="r50",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you start your turn",
    on=Trigger(TurnStart, about_me, "you start your turn"),
    dropped=("c.end_ongoing()",),
)
def p11738(c: Cast) -> None:
    """The four conditions go; nothing ends ongoing damage outright."""
    c.cure(
        Condition.DAZED,
        Condition.SLOWED,
        Condition.STUNNED,
        Condition.WEAKENED,
        on=c.me,
    )


# -- r51 --------------------------------------------------------------------


@power(
    "p16547",
    level=2,
    cls="r51",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    no_provoke=True,
)
def p16547(c: Cast) -> None:
    c.jump(c.speed_of())


@power(
    "p16550",
    level=6,
    cls="r51",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    no_provoke=True,
    trigger="you take damage from an area or a ranged attack against AC or Reflex",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
    dropped=("DamageRolled.vs", "DamageRolled.power"),
)
def p16550(c: Cast) -> None:
    """Which attacks qualify cannot be read off the damage event, so every
    blow is halved rather than only the two printed shapes."""
    c.halve()
    c.jump(max(1, c.speed_of() // 2))


# -- r52 --------------------------------------------------------------------


@power(
    "p14016",
    level=2,
    cls="r52",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p14016(c: Cast) -> None:
    c.invisible(until=When.EOT)
    c.bonus("skill:stealth", 5, kind="power", on=c.me, until=When.EONT)


@power(
    "p14032",
    level=0,
    cls="r52",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    todo=("query.can_hide(world, eid)",),
)
def p14032(c: Cast) -> None:
    """The whole benefit is a permission -- when a Stealth check to go unseen
    may be attempted, and what counts as cover for it. Nothing asks that
    question, so there is no rule here to relax."""


# -- r53 --------------------------------------------------------------------


@power(
    "p14021",
    level=2,
    cls="r53",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger="you kill a nonminion enemy with a melee attack",
    on=Trigger(Dropped, by_me, "you drop an enemy"),
    dropped=("Dropped.power",),
)
def p14021(c: Cast) -> None:
    """Eating and breathing are not on a board. The nonminion half of the
    trigger is asked in the body, where there is a `Cast` to ask with; the
    melee half cannot be -- `Dropped` names no power."""
    ev = c.trigger
    if ev is None or c.is_kind("minion", on=ev.actor):
        return
    c.bonus(
        "save",
        2,
        kind="power",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx["label"] == "death" or ctx["ongoing"],
    )


# -- r60 --------------------------------------------------------------------


@power(
    "p15830",
    level=2,
    cls="r60",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p15830(c: Cast) -> None:
    """The sustain re-lays all three, because the printed line sustains the
    vulnerability along with the bonuses."""
    c.temp_hp(3 + c.level // 2, on=c.me)

    def lay() -> None:
        c.bonus(AC, 2, kind="power", on=c.me, until=When.EONT)
        c.bonus(FORT, 2, kind="power", on=c.me, until=When.EONT)
        c.vulnerable(5, DamageType.FIRE, on=c.me, until=When.EONT)

    lay()
    c.on_sustain(
        c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=ActionType.MINOR), lay
    )


# -- r61 --------------------------------------------------------------------


@power(
    "p15835",
    level=0,
    cls="r61",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def p15835(c: Cast) -> None:
    """The flight is granted for the length of the move and no longer."""
    c.mode("fly", 6, on=c.target, until=When.EOT)
    c.move(6, who=c.target)


@power(
    "p15838",
    level=6,
    cls="r61",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    dropped=("c.end_effect()",),
)
def p15838(c: Cast) -> None:
    """"Until you attack" needs an effect a body can end."""
    c.invisible(until=When.EONT)


# -- r62 --------------------------------------------------------------------


@power(
    "p15843",
    level=2,
    cls="r62",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p15843(c: Cast) -> None:
    """The check bonus and the running start only set how far, and the
    printed cap is the character's speed, so the jump is taken at the cap."""
    c.bonus("skill:athletics", 10, kind="power", on=c.me, until=When.EOT)
    c.jump(c.speed_of())


# -- r65 --------------------------------------------------------------------


@power(
    "p16360",
    level=0,
    cls="r65",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    once_per_round=True,
    dropped=("c.form(speed=)",),
)
def p16360(c: Cast) -> None:
    """The two humanoid shapes change no statistic, so only the animal one
    is written: a way of moving, and the bar on attack powers that rides
    with it. The land speeds the card also changes have no hold -- `c.mode`
    grants a mode and cannot take walking away."""
    pace = c.speed_of()
    shapes = {
        "burrow": max(1, pace // 2),
        "climb": pace,
        "fly": 1 + pace // 2,
        "swim": pace,
    }
    pick = c.choose(sorted(shapes), "which animal shape", optional=True)
    if pick is None:
        return
    c.form(
        modes={pick: shapes[pick]},
        until=When.ENCOUNTER,
        revert=ActionType.MINOR,
        label=c.ref,
    )
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)


# -- r66 --------------------------------------------------------------------


@power(
    "p16469",
    level=0,
    cls="r66",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def p16469(c: Cast) -> None:
    c.conceal(on=c.me, until=When.EONT)
    c.temp_hp(5, on=c.me)


@power(
    "p16472",
    level=6,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.tremorsense()",),
)
def p16472(c: Cast) -> None:
    """Truesight is the nearest sense the engine holds. A tremorsense whose
    radius can be spent up to is what the card wants, and with it the
    once-a-round minor that widens it."""
    c.truesight(5, on=c.me, until=When.ENCOUNTER)


@power(
    "p16475",
    level=10,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CONJURATION],
    dropped=("DamageRolled.vs", "c.end_effect()"),
)
def p16475(c: Cast) -> None:
    """The shield is a pool of hit points read off a healing surge. Nothing
    on the damage event says which defence was hit, so every blow may be
    soaked; and when the pool runs out the two bonuses should go with it."""
    pool = [c.surge_value()]
    c.bonus(AC, 2, kind="power", on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 2, kind="power", on=c.me, until=When.ENCOUNTER)

    def soak(ev: DamageRolled) -> None:
        if ev.target == c.me and pool[0] > 0:
            pool[0] -= c.reduce(min(pool[0], ev.amount), ev)

    c.watch(DamageRolled, soak, until=When.ENCOUNTER, window=Window.BEFORE)


# -- r67 --------------------------------------------------------------------


@power(
    "p16654",
    level=0,
    cls="r67",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(CON, vs=REF, plus=2),
    dropped=("c.flat(unreducible=)", "c.on_death(ref)"),
)
def p16654(c: Cast) -> None:
    """Bloodied value is half the maximum. The Effect line lands once and
    last, so the burst is rolled against a caster who is still standing."""
    health = c.world.get(c.me, Health)
    val = (health.max_hp // 2) if health else 0
    if c.strike():
        c.flat(val, dtype=DamageType.THUNDER)
        c.prone()
    else:
        c.flat(val // 2, dtype=DamageType.THUNDER)
    if c.last:
        c.flat(val, on=c.me)
        c.prone(on=c.me)


# -- r69 --------------------------------------------------------------------


@power(
    "p16657",
    level=0,
    cls="r69",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an area or close attack hits or misses you, or any attack misses you",
    on=(
        Trigger(DamageRolled, targets_me, "you take damage"),
        Trigger(Miss, targets_me, "an attack misses you"),
    ),
    dropped=("DamageRolled.power",),
)
def p16657(c: Cast) -> None:
    """Two triggers for one printed sentence: the damage half is where the
    halving can happen -- `deal_damage` reads the amount back after both
    windows -- and the miss half carries none, so only the shift lands
    there. Which attacks qualify cannot be read off the damage event."""
    c.halve()
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p16660",
    level=10,
    cls="r69",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    dropped=("Target.kind", "c.end_effect()"),
)
def p16660(c: Cast) -> None:
    """Targets the wielder, there being no target kind for a piece of gear.
    The armour bonus should also end when an attack against AC lands; only
    the encounter clock ends it here. The printed requirement -- that this
    is used during a rest -- is not a question a board can be asked."""
    if c.choose(["armour", "weapon"], "what the power is used on") == "armour":
        c.bonus(AC, 2, kind="power", until=When.ENCOUNTER)
        return
    c.bonus("attack", 2, kind="power", until=When.ENCOUNTER, once=True)
    c.bonus("damage", 2, kind="power", until=When.ENCOUNTER, once=True)
