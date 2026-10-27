"""Racial powers, the third batch.

Filed by the race ref in `cls`, which is what the compendium's Class column
holds for these rows. Nothing here needs a race *model*: a racial power is an
ordinary row and the only thing that makes it racial is who is given it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from combat_engine.content.powers.augment import lent
from combat_engine.engine import (
    AC,
    AREA_OR_CLOSE,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    DEX,
    EACH_ALLY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
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
    WIS,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Dropped,
    EnterSquare,
    ForcedMove,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
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
    by_ranged,
    check_failed,
    get,
    my_check,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.cast import (
    MANOEUVRE_BULL_RUSH,
    MANOEUVRE_BULL_RUSH_FOLLOW,
)
from combat_engine.engine.query import bloodied, line_of_effect, squares, unseen_by
from combat_engine.engine.skills import modifier

if TYPE_CHECKING:
    from combat_engine.engine import World

def _bloodied(world: World, eid: int) -> bool:
    """"Requirement: you must be bloodied", asked of a creature on a board."""
    return bloodied(world, eid)


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


def _seen_by_me(world: World, me: int, ev: Any) -> bool:
    """"A creature you can see" -- somebody else, in sight, on a live turn.

    No ready-made predicate says this; the question itself is settled,
    and `Cast.can_see` is these same two calls.
    """
    who = getattr(ev, "actor", None)
    return (
        who is not None
        and who != me
        and not getattr(ev, "ghost", False)
        and line_of_effect(world, me, who)
        and not unseen_by(world, me, who)
    )


def _close_or_area(world: World, me: int, ev: Any) -> bool:
    """Was the blow dealt by a close or an area attack?

    `triggers._power_of` reads `detail` on a damage event, which is what
    makes the reach askable there at all. `by_melee` and `by_ranged` each
    cover part of this shape and neither covers it alone.
    """
    row = get(getattr(ev, "detail", "") or getattr(ev, "power", "") or "")
    return row is not None and row.reach_of(getattr(ev, "branch", 0)).kind in AREA_OR_CLOSE


def _vs_ac_or_ref(world: World, me: int, ev: Any) -> bool:
    """Was the blow dealt by an attack aimed at AC or Reflex?

    `DamageRolled` carries no defence, so the question goes to the **row**
    the event does name -- `m5788a0`'s ruling, and the same lookup
    `_close_or_area` above makes for the reach. A row declaring
    `Defense.ANY` answers no, which leaves the caster paying for the
    interrupt rather than halving a blow the card may not cover.
    """
    row = get(getattr(ev, "detail", "") or getattr(ev, "power", "") or "")
    if row is None:
        return False
    return getattr(row.attack_of(getattr(ev, "branch", 0)), "vs", None) in (AC, REF)


# -- r1 ---------------------------------------------------------------------


@power(
    "p1448",
    level=0,
    cls="r1",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack((STR, CON, DEX), vs=REF, plus=2),
    dropped=("c.race_option(damage_type=)",),
)
def p1448(c: Cast) -> None:
    """The card binds the attack ability and the damage type at character
    creation, and a racial choice is recorded nowhere -- so the header
    holds one ability, Constitution, which the damage line names anyway.
    `c.element` answers for a character whose *class* build bound an
    element and is the nearest standing reading of the second half.

    **Correction: a racial choice is not "recorded nowhere".** `Build.race`
    holds the ref, `Build.choices` emits `race:<ref>` unconditionally, and
    `c.build("race:...")` reads it -- `chargen.meets` already answers 690
    heroic feats off that field. What is missing is narrower: a race has no
    **leg** the way a class does, so there is nowhere to record *which*
    option within the race was taken. That is #235's modelling question
    asked of a different noun, and #505 records why it should not be
    answered twice.
    """
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



def _bull_rushed(world: World, me: int, ev: Any) -> bool:
    """This creature's own bull rush, landed.

    `as_` rides the `Hit` as a plain attribute, which is what makes "you
    successfully bull rush a target" askable at all -- the manoeuvre is an
    action kind and carries no ref a trigger could name.
    """
    return (getattr(ev, "attacker", None) == me
            and getattr(ev, "as_", "") == "bull_rush")


@power(
    "p14383",
    level=2,
    cls="r2",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you successfully bull rush a target",
    on=Trigger(Hit, _bull_rushed, "you successfully bull rush a target"),
)
def p14383(c: Cast) -> None:
    """"Increase the push by a number of squares up to your Constitution
    modifier, shifting into each square the target of your bull rush leaves."

    **Both halves, and they are two different allowances.** The push gets
    longer and so does the follow -- "shifting into each square the target
    leaves" is the only printed clause in the tree that lengthens the shift,
    which is why `MANOEUVRE_BULL_RUSH_FOLLOW` exists apart from the push's
    own symbol. A belt that lengthens the push alone must not also walk its
    wearer three squares.

    **This fires inside the `Hit`, before the push, and that is the point.**
    The first shape of this row waited for the bull rush to finish and then
    pushed again by hand, which read as the more literal translation of
    "increase the push" and was wrong twice over: the target ended up on the
    far side of the attacker, and the row duplicated a clause the manoeuvre
    already owns. `c.bull_rush` reads both allowances *after* the attack
    returns, so writing them here lands in time and the manoeuvre does the
    moving.

    "Up to" is a choice the card gives, and the full modifier is what gets
    written -- the engine has no way to ask for less and no reason to want
    it, since a longer push is strictly the better end of every board this
    power is used on.

    **`until=When.EOT`, and it overshoots by one clause.** The allowance
    belongs to the bull rush that triggered it and nothing finer than a turn
    is sayable, so a *second* bull rush in the same turn -- an action point,
    or a second standard somehow -- would get the squares again. The default
    `ENCOUNTER` was worse by a wide margin: every bull rush for the rest of
    the fight. Named here rather than left to be rediscovered.
    """
    c.extend_move(MANOEUVRE_BULL_RUSH, c.con_mod, until=When.EOT, on=c.me)
    c.extend_move(
        MANOEUVRE_BULL_RUSH_FOLLOW, c.con_mod, until=When.EOT, on=c.me
    )


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
    c.grants_in(ring, "skill:stealth", 2, side="team")


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
    on=Trigger(TurnStart, _seen_by_me, "a creature you can see starts its turn"),
)
def p14391(c: Cast) -> None:
    """Re-aimed: no *ready-made* predicate narrows a trigger to what the
    responder can see, but `query.unseen_by` is the question and a local
    one asks it, so the printed trigger is declared rather than widened."""
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
)
def p14387(c: Cast) -> None:
    """"You successfully use the aid another action on an adjacent ally."

    The whole content of the power is that the action succeeds, so the
    action is what it takes -- `auto=True` on `c.aid_another`, where the
    success is bought rather than rolled for.

    **Which aid, and why this one.** The card says "aid another", and the
    two readings give different benefits: the later split made aid *attack*
    the one granting +2 to an attack roll, while aid another became the
    skill-check form. This takes the skill form, because that is the action
    the card names and the engine now has all three. It is the weaker
    reading in a fight -- a +2 to a check against +2 to a swing -- and it is
    the one the words support; the row previously laid an attack bonus with
    nothing to hang it on, which is the other reading made silently.

    How much is no longer written here: `c.aid_another` reads
    `MANOEUVRE_AID`, so an item or feat raising what this character grants
    raises this too.
    """
    mate = c.choose([a for a in c.allies() if c.adjacent(a)], "who to aid")
    if mate is not None:
        c.aid_another(mate, auto=True)


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
    attack=Attack((INT, WIS, CHA), vs=REF, plus=4),
)
def p1831(c: Cast) -> None:
    """"All attacks against the target" is written as the caster's side,
    which is every attacker that matters on a two-sided board.

    `c.ignore_concealment()` was stale: `c.no_cover` is the concealment
    half as well as the cover one -- `resolve.attack` takes the larger of
    the two and `query.cover_waived` waives whichever it was. The
    invisibility half is truesight aimed at this one creature, which is
    the shape `c.truesight(of=)` prints."""
    # **A feat may lend this row an augment**, and the lend has to be
    # offered before the strike: f3158's clause swaps the defence this
    # rolls against. #507.
    lent(c)
    if c.strike():
        c.grants_advantage(to="team", until=When.EONT)
        c.no_cover(until=When.EONT)
        foe = c.target
        for watcher in (c.me, *c.allies()):
            c.truesight(of=foe, on=watcher, until=When.EONT)


@power(
    "p2473",
    level=0,
    cls="r16",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
)
def p2473(c: Cast) -> None:
    """The cloud blocks sight for everyone, which is terrain and so is a
    zone. "Blinded until they exit" is occupancy and not a sweep at the
    moment it forms, so each creature's blindness is held and ended when
    it leaves; the caster is exempt either way.

    **`f765`'s clause is written here**, not in its own row, which is the
    `implemented_in=` pattern: *"you can choose for it to lightly or
    heavily obscure its area, instead of totally obscuring it. If you
    reduce the darkness in this way, creatures inside the cloud are not
    blinded."* A feat that changes one named power belongs in that power's
    body -- it is a choice made where the zone is laid, and the feat row
    has nothing of its own to do.

    The two softer grades are the light model's: "lightly obscured" is
    `obscured="dim"` and "heavily obscured" is `"dark"`, both graded by
    `query.light_concealment` (-2 and -5) and both cancelled for whoever
    can see in that light. Totally obscuring is `blocks_sight`, which is
    terrain and binds both sides -- which is why the softer choices come
    with no blinding, exactly as printed.

    **Total is offered first on purpose.** `c.choose` takes the engine's
    own pick from the head of the list, so the default stays the printed
    power unmodified: a character holding the feat has an *option*, and
    whether it is worth taking is `policy/`'s business rather than a
    default this row should decide."""
    area = c.area()
    thinner = ""
    if c.feat("f765"):
        thinner = c.choose(
            ["", "dark", "dim"], "how thickly the cloud obscures"
        ) or ""
    if thinner:
        # No blinding, which is the second half of the printed sentence --
        # so the occupancy watch below is not armed at all rather than
        # armed and gated.
        c.zone(area, until=When.EONT, obscured=thinner)
        return
    c.zone(area, until=When.EONT, blocks_sight=True)
    held: dict[int, Any] = {}

    def refresh(_ev: Any = None) -> None:
        inside = {w for w in c.in_squares(area) if w != c.me}
        for who in inside - set(held):
            blind = c.blinded(on=who, until=When.EONT)
            if blind is not None:
                held[who] = blind
        for who in set(held) - inside:
            c.end_effect(held.pop(who), why=c.ref)

    refresh()
    c.watch(MoveEnd, refresh, until=When.EONT)
    c.watch(EnterSquare, refresh, until=When.EONT)


@power(
    "p16032",
    level=2,
    cls="r16",
    usage=AT_WILL,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def p16032(c: Cast) -> None:
    """Four glowing forms, each dimming two squares, until the end of your
    next turn.

    **"Dim light and nothing else" was the reason and the "nothing else" is
    the half that held.** The forms do have no hit points, block nothing
    and are not creatures -- and the dim light they shed conceals whoever
    stands in it, which `query.light_concealment` turns into a `Cover` the
    attack path reads. #686.

    **Four zones and not four conjurations**, because the only thing the
    forms do is dim: a conjuration would put four bodies on the board that
    block nothing and can be attacked for no reason. `c.zone(obscured=)` is
    the area form of dimming, where `c.dim` is the carried one.

    "They also vanish if you use this power again" comes free: each use
    lays its zones under this row's own label and ends the previous ones
    first."""
    from combat_engine.engine.types import Light
    from combat_engine.engine.zones import Zone

    # `Zones.end` takes the **entity id**, not the `Zone` -- passing the
    # component raised `unhashable type: 'Zone'` from the store lookup.
    for eid in c.my_zones():
        zone = c.world.get(eid, Zone)
        if zone is not None and zone.label == c.ref:
            c.world.zones.end(eid, "this power used again")
    spots = [sq for sq in sorted(c.area())
             if c.world.grid.occupant(sq) is None][:4]
    for sq in spots:
        c.zone(spread({sq}, 2), label=c.ref, until=When.EONT,
               obscured=Light.DIM)


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
)
def p16460(c: Cast) -> None:
    """Re-aimed: the reroll needs no new argument. `skills.check` has
    already totalled the modifier for the skill that was rolled, so
    "use your Bluff modifier instead" is the difference between the two
    laid on top, which `c.boost_check` reaches after the die is down."""
    ev = c.trigger
    c.reroll_check()
    if ev is not None and ev.skill in ("diplomacy", "intimidate"):
        c.boost_check(
            modifier(c.world, c.me, "bluff") - modifier(c.world, c.me, ev.skill)
        )


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
)
def p16466(c: Cast) -> None:
    pace = c.speed_of()
    c.mode("climb", pace, until=When.EOT)
    c.move(pace)
    # Full speed while squeezing. #508.
    c.waive(Condition.SQUEEZING, "halve_speed", on=c.me)


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
        # Asked for rather than written in: f1061 raises this die, and a
        # literal here is a sentence that row cannot reach.
        c.damage(c.dice_for(c.ref, "1d6"), c.str_mod)
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
)
def p14074(c: Cast) -> None:
    """Immunity to fire is resistance large enough to swallow any heroic
    burn. The ability choice takes the best of the three, which is what a
    player picks. The aura bites at the *end* of a turn, which `c.burns`
    does not do, so it is a watcher over the aura's occupants.

    "Unless you choose to be" is `c.may`, so the refusal is written out
    rather than taken from `c.immovable`, which never declines. `default`
    is False: a headless run should keep the shove off, not wave it in."""
    burn = max(c.str_mod, c.con_mod, c.dex_mod)
    c.form(conditions=[Condition.SLOWED], until=When.EONT, label=c.ref)
    c.resist(100, DamageType.FIRE, until=When.EONT, on=c.me)

    def refuse(ev: ForcedMove) -> None:
        if ev.target == c.me and not c.may("be moved", who=c.me, default=False):
            ev.cancel(c.ref)

    c.watch(ForcedMove, refuse, until=When.EONT, window=Window.BEFORE, on=c.me)
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
    on=(
        Trigger(AttackRolled, by_me, "you make an attack roll"),
        Trigger(SavingThrow, about_me, "you make a saving throw"),
        Trigger(SkillCheck, about_me, "you make a skill check"),
    ),
)
def p6186(c: Cast) -> None:
    """"Add 1d6 to the triggering roll", whatever the roll was.

    Three of the four printed kinds are declared and paid by one verb, since
    `c.boost_roll` dispatches on what triggered. The **ability check** is the
    fourth and the engine has no such roll -- that is `c.ability_check()`,
    which eleven other rows want, and it is the honest remainder here rather
    than a note.

    Not a reroll: the card adds to the number on the table. #495.

    **The die still comes through `c.dice_for`, and that is load-bearing.**
    `f1836` prints "you add 1d10 to the roll, rather than 1d6" about this
    very row, and a hard-coded `"1d6"` here makes that feat a modifier
    nothing consults -- this component's commonest bug, and `lint.py` has a
    guard named after it. The skill is handed over in the context so the
    feat can narrow to the check it names.
    

    **The ability-check arm is covered now, not dropped.** `skills
    .ability_check` announces the same `SkillCheck` event under an
    `ability:<name>` key, and this row's trigger is unnamed -- so it
    hears an ability check without a second entry. Driven in
    `drivers.ability_checks`: `my_check()` matches it and
    `my_check("athletics")` does not.
    """
    ev = c.trigger
    skill = str(getattr(ev, "skill", "") or "").lower()
    # **What kind of roll, and which power rolled it.** `f1836` narrows to a
    # Nature check or an attack roll of two keywords, and an empty `skill`
    # used to be the only thing it could read -- which lumped a saving throw
    # in with an attack roll and let the feat improve a roll its card never
    # mentions. The moment this row could boost more than a skill check,
    # "not a skill check" stopped meaning "an attack".
    kind = "check" if skill else "attack" if hasattr(ev, "result") else "save"
    c.boost_roll(
        c.roll(
            c.dice_for(
                "p6186",
                "1d6",
                {
                    "skill": skill,
                    "roll_kind": kind,
                    "power": str(getattr(ev, "power", "") or ""),
                },
            )
        )
    )


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
)
def p27(c: Cast) -> None:
    """"Save ends both" is one throw over two clauses, and only the burn
    can carry one. So the burn holds the save and the penalty runs to the
    end of the encounter gated on the burn still standing -- the one save
    ends both, which two save-ends effects side by side did not."""
    if c.strike():
        c.damage("1d8", c.con_mod, dtype=DamageType.POISON)
        burn = c.ongoing(2, DamageType.POISON, until=When.SAVE_ENDS)
        if burn is None:
            c.penalty("attack", 2, until=When.SAVE_ENDS)
        else:
            c.penalty(
                "attack",
                2,
                until=When.ENCOUNTER,
                when=lambda _ctx, e=burn: not e.ended,
            )


# -- r43 --------------------------------------------------------------------


@power(
    "p16541",
    level=0,
    cls="r43",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16541(c: Cast) -> None:
    """Two printed choices, offered as one. "You use the aid another or the
    aid attack action. If you succeed, you grant a +3 bonus, rather than the
    normal +2."

    **The aid branch takes the real action now**, which is both more faithful
    and what f3761 needs: that feat answers "when you use this power to take
    the aid attack action", and a bonus laid by hand is not an action anybody
    can have taken.

    Aid attack, not aid another, because the +3 is granted on a *success*
    against an enemy and the card names both -- the attack form is the one
    that has an enemy to name, and f3761 speaks of "the chosen enemy".

    **The +3 is written as a raise rather than as the number.** `+3 rather
    than the normal +2` is exactly what `c.change_amount` says, and laying it
    that way means a wearer who also has f2056's +4 gets the larger -- which
    `amount_for` does by taking a maximum, and which laying a literal 3 would
    have thrown away. `until=When.EOT` keeps the raise to this use.
    """
    from combat_engine.engine.cast import MANOEUVRE_AID

    exposed = [
        foe
        for foe in c.enemies()
        if any(c.adjacent_to(foe, mate) for mate in c.allies())
    ]
    mates = [mate for mate in c.allies() if c.adjacent(mate)]
    near = [foe for foe in c.enemies() if c.adjacent(foe)]
    options = [
        word
        for word, pool in (("expose", exposed), ("aid", mates and near))
        if pool
    ]
    pick = c.choose(options, "which benefit")
    if pick == "expose":
        foe = c.choose(exposed, "which enemy")
        if foe is not None:
            c.grants_advantage(on=foe, to=c.me, until=When.SONT)
    elif pick == "aid":
        mate = c.choose(mates, "who to aid")
        foe = c.choose(near, "aid against which enemy")
        if mate is not None and foe is not None:
            c.change_amount(MANOEUVRE_AID, 3, on=c.me, until=When.EOT)
            c.aid_attack(foe, mate)


@power(
    "p16544",
    level=6,
    cls="r43",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW],
)
def p16544(c: Cast) -> None:
    """Concealment is a modifier rather than the `HIDDEN_FROM` relation
    `resolve.attack` clears, so "until you attack" is a watch of its own.
    Ending it on the declaration is safe: concealment penalises attacks
    *against* the concealed creature and is never read on its own swing."""
    hidden = c.conceal(on=c.me, until=When.EONT, total=True)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me:
            c.end_effect(hidden)

    c.watch(AttackDeclared, swung, until=When.EONT, on=c.me, once=True)


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
    # `AREA_OR_CLOSE` adds the `"wall"` this omitted. #616.
    if shape not in AREA_OR_CLOSE:
        return
    # Read rather than written in, so a feat can lengthen it. #502.
    c.teleport(c.squares_for(c.ref, 3))
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
)
def p11738(c: Cast) -> None:
    """Re-aimed: a burn is not a condition but it is an `Effect`, and one
    that carries `ongoing` is exactly what the printed line ends. So the
    four conditions are cured and every burn standing on the caster is
    ended outright -- no saving throw, which is what the card says."""
    c.cure(
        Condition.DAZED,
        Condition.SLOWED,
        Condition.STUNNED,
        Condition.WEAKENED,
        on=c.me,
    )
    for eff in list(c.world.effects.of(c.me)):
        if not eff.ended and eff.ongoing is not None:
            c.end_effect(eff, why=c.ref)


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
    on=Trigger(
        DamageRolled,
        both(targets_me, by_ranged, _vs_ac_or_ref),
        "a ranged or area attack against AC or Reflex damages you",
    ),
)
def p16550(c: Cast) -> None:
    """Re-aimed. `DamageRolled.power` was stale: `triggers._power_of`
    reads the row off `detail`, so `by_ranged` -- which is "ranged" and
    "area_burst" together, exactly the printed pair -- declares the shape
    half, and `_vs_ac_or_ref` the defence half off the same lookup. A
    declared predicate is handed an event and not a stash, so the power is
    the only thing it can ask."""
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

)
def p14021(c: Cast) -> None:
    """Eating and breathing are not on a board. The nonminion half of the
    trigger is asked in the body, where there is a `Cast` to ask with; the
    melee half cannot be -- `Dropped` names no power.

    `c.is_kind("minion")` was wrong and silently false: `c.kinds_of` holds
    origin and type words and never the minion column, which is what
    `c.is_minion` reads."""
    ev = c.trigger
    if ev is None or c.is_minion(on=ev.actor):
        return
    # The melee half, which `Dropped.power` makes askable.
    if not c.struck_by(ev, kind="melee"):
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
)
def p15838(c: Cast) -> None:
    """"Until you attack" needs no watch here and must not have one:
    invisibility is held as `HIDDEN_FROM` and `resolve.attack` clears it
    for whoever swung, at the point in the swing where the attack has
    already had the benefit. A row ending the hold on `AttackDeclared`
    would take the advantage off the very attack that spends it."""
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
)
def p16360(c: Cast) -> None:
    """The two humanoid shapes change no statistic, so only the animal one
    is written: a way of moving, what the shape does to the land speed,
    and the bar on attack powers that rides with it.

    Re-aimed: `query.speed` reads a `speed` modifier, so "your land speed
    becomes 1" and "your speed increases by 2" are `c.bonus("speed", ...)`
    and want nothing new on `c.form`. Both of those and the attack bar
    hang off the form's own effect, so reverting takes all three off
    together -- the bar alone used to outlive the shape."""
    pace = c.speed_of()
    #: mode speed, and what the shape does to the land speed.
    shapes = {
        "burrow": (max(1, pace // 2), 0),
        "climb": (pace, 0),
        "fly": (1 + pace // 2, 1 - pace),
        "swim": (pace, 1 - pace),
        "walk": (0, 2),
    }
    pick = c.choose(sorted(shapes), "which animal shape", optional=True)
    if pick is None:
        return
    mode, land = shapes[pick]
    shape = c.form(
        modes={pick: mode} if mode else None,
        until=When.ENCOUNTER,
        revert=ActionType.MINOR,
        label=c.ref,
    )
    rides = [c.cannot_attack(on=c.me, until=When.ENCOUNTER)]
    if land:
        rides.append(c.bonus("speed", land, on=c.me, until=When.ENCOUNTER))

    def drop(hold: Any) -> None:
        if not hold.ended:
            c.world.effects.end(hold, f"{c.ref} ended")

    for hold in rides:
        if hold is not None:
            shape.on_end.append(lambda h=hold: drop(h))


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
    )
def p16472(c: Cast) -> None:
    """Tremorsense 5 for the encounter, which is what the card prints --
    `c.truesight` was standing in for it and answers a different question."""
    c.tremorsense(5, on=c.me, until=When.ENCOUNTER)


@power(
    "p16475",
    level=10,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CONJURATION],
)
def p16475(c: Cast) -> None:
    """The shield is a pool of hit points read off a healing surge, and it
    lasts "until it is reduced to 0 hit points" -- so the two bonuses and
    the soak all end together when the pool empties.

    Only a blow from an attack that hit AC or Reflex is soaked.
    `DamageRolled` carries no defence, but `Hit` carries one as a plain
    attribute (`resolve.py` attaches it so it stays off the wire), and the
    hit is the printed trigger -- so watching the outcome rather than
    `AttackRolled` also keeps half-damage-on-a-miss out of the pool. The
    pair is matched on attacker and row, `i2403x1`'s shape, and the match
    is spent as it is used: a rider's own packet carries its own `detail`
    and so goes unsoaked, which leaves the shield weaker than the card
    rather than stronger."""
    pool = [c.surge_value()]
    aimed: set[tuple[int, str]] = set()
    holds = [
        c.bonus(AC, 2, kind="power", on=c.me, until=When.ENCOUNTER),
        c.bonus(REF, 2, kind="power", on=c.me, until=When.ENCOUNTER),
    ]

    def landed(ev: Hit) -> None:
        if ev.target == c.me and getattr(ev, "vs", None) in (AC, REF):
            aimed.add((ev.attacker, ev.power))

    def soak(ev: DamageRolled) -> None:
        if ev.target != c.me or pool[0] <= 0:
            return
        if (ev.source, ev.detail) not in aimed:
            return
        aimed.discard((ev.source, ev.detail))
        pool[0] -= c.reduce(min(pool[0], ev.amount), ev)
        if pool[0] <= 0:
            for hold in holds:
                c.end_effect(hold)

    holds.append(c.watch(Hit, landed, until=When.ENCOUNTER))
    holds.append(
        c.watch(DamageRolled, soak, until=When.ENCOUNTER, window=Window.BEFORE)
    )


# -- r67 --------------------------------------------------------------------


@power(
    "p16654",
    level=0,
    cls="r67",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack((STR, CON, DEX), vs=REF, plus=2),
    dropped=("c.on_death(ref)",),
)
def p16654(c: Cast) -> None:
    """Bloodied value is half the maximum. The Effect line lands once and
    last, so the burst is rolled against a caster who is still standing.

    Re-aimed onto the names the rest of the tree uses: seven rows already
    want `c.flat(unpreventable=)` for "cannot be reduced by any means",
    and the attack line's choice of Strength, Constitution or Dexterity
    is the racial build decision nothing records. The Special -- this
    power firing by itself when you die -- needs a second hook, because
    a row declaring `on=` runs only when the trigger fires and this one
    is also an ordinary standard action."""
    health = c.world.get(c.me, Health)
    val = (health.max_hp // 2) if health else 0
    if c.strike():
        c.flat(val, dtype=DamageType.THUNDER)
        c.prone()
    else:
        c.flat(val // 2, dtype=DamageType.THUNDER)
    if c.last:
        # "This damage cannot be reduced by any means" is about the
        # caster's own half. The two above are what the burst deals and
        # are ordinary.
        c.flat(val, on=c.me, unpreventable=True)
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
        Trigger(
            DamageRolled,
            both(targets_me, _close_or_area),
            "a close or area attack damages you",
        ),
        Trigger(Miss, targets_me, "an attack misses you"),
    ),
)
def p16657(c: Cast) -> None:
    """Two triggers for one printed sentence: the damage half is where the
    halving can happen -- `deal_damage` reads the amount back after both
    windows -- and the miss half carries none, so only the shift lands
    there.

    Re-aimed: `DamageRolled.power` was stale. `triggers._power_of` reads
    the row off `detail`, so the close-or-area half of the first trigger
    is asked there; the second half, "any attack misses you", is the
    `Miss` and carries no shape test at all."""
    c.halve()
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p16660",
    level=10,
    cls="r69",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target("ally", 1, label="One x_m6564 or one weapon"),
)
def p16660(c: Cast) -> None:
    """Targets the wielder, there being no target for a piece of gear.
    **That is a target-line formality and not a dropped clause**, which is
    why this no longer carries one: both printed branches reach the same
    creature the card's effect reaches, so nothing a body could ask about
    the gear itself would change an outcome. (`Scenery.kind` and
    `Scenery.by` both exist in any case -- `components.py` -- and nothing
    on a board ever mints a `Scenery` for a worn thing, so neither was the
    gap either.)

    **It has its `label=` now, and the label carries a ref.** The convention
    for a card naming a thing the engine has no entity for is
    `Target(side, label=)` -- the pool is the bearer, the label is what the
    page prints -- and four artificer enchantments render "One weapon or
    implement" that way. This card's line names a **ref**, which used to
    break the convention: `Target.label` reached `render` as raw text, so
    the honest label printed `x_m6564` to a player, which is worse than the
    generic pool string it replaced.

    `wire.in_text` resolves it at display time, so the page shows the
    creature's printed name to a reader who has `localization/` and the bare
    ref to one who does not. **The ref and not the name is what is written
    here**, which is the point: a name spelled into a `label=` is text the
    page renders, shown to a player with no localisation -- the top row of
    `#447` -- and a one-word ordinary name beside its own ref is the case
    the tree-wide search is recorded as *not* catching. #895.

    The armour bonus ends when an attack against AC hits the wearer, read
    off the settled `Hit`: it carries the defence as a plain attribute, so
    the old route through `AttackRolled` -- comparing the total to the
    defence in a window where an interrupt can still move either number,
    and getting a natural 1 or 20 wrong both ways -- is no longer needed.

    The printed requirement -- that this is used during a rest -- is not a
    question a board can be asked."""
    if c.choose(["armour", "weapon"], "what the power is used on") == "armour":
        worn = c.bonus(AC, 2, kind="power", until=When.ENCOUNTER)
        wearer = c.target

        def landed(ev: Hit) -> None:
            if ev.target == wearer and getattr(ev, "vs", None) is AC:
                c.end_effect(worn)

        c.watch(Hit, landed, until=When.ENCOUNTER, once=True)
        return
    c.bonus("attack", 2, kind="power", until=When.ENCOUNTER, once=True)
    c.bonus("damage", 2, kind="power", until=When.ENCOUNTER, once=True)
