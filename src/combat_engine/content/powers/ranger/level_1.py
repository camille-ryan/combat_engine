"""Ranger, level 1.

Two notes that apply to most of the rows below.

A great many ranger powers print two attack lines at once -- "Strength vs.
AC (melee) or Dexterity vs. AC (ranged)". Those are `MeleeOrRanged`, with
`attack_alt` carrying the second line, and each branch is offered as its
own option: the melee one reaches 1 square, swings what is in hand and
provokes nothing; the ranged one reaches 20, fires the bow and opens an
opportunity window. The damage line reads `c.attack_mod`, which is the
modifier of whichever ability that branch attacks with, rather than naming
Dexterity and quietly being half right.

The other recurring shape is "two attacks". That is just `c.strike()` twice
in the body, which works because the body is per-target: a row that spreads
its two attacks over one or two creatures asks `c.first and c.last` to find
out whether it is the only target and takes both shots if so.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    PowerResolved,
    Ranged,
    UpTo,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_MELEE_AGAINST_YOU = "an enemy makes a melee attack against you"

#: The four holds `f1300`'s clause on `p917` names together.
#:
#: Copied from `feats/general_h.py`, where the same tuple still serves that
#: feat's clause on the swing `p1061` hands an ally. #550's convention puts
#: a clause in the body of the row it names, and a body cannot reach a feat
#: module's privates -- four condition members is the cheap end of that
#: duplication.
_HELD_FAST = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)

#: The four creature types every clause of `f1298` names together. Copied
#: from `feats/general_h.py` for the same reason as `_HELD_FAST`.
_NAMED_KINDS = ("demon", "drow", "orc", "spider")


def _is_named_kind(c: Cast, who: int) -> bool:
    return any(c.is_kind(word, on=who) for word in _NAMED_KINDS)


def _surprise_round(c: Cast) -> bool:
    """Is this the surprise round?

    `Encounter.start` lays `Condition.SURPRISED` on whoever was caught and
    lifts every one of them when the round ends, so an enemy still holding
    it *is* the surprise round. The encounter's own `_surprise` flag is
    private and there is no query for it.

    Copied from `feats/general_h.py` for `_HELD_FAST`'s reason, and
    `powers/rogue/level_1_b.py` holds the same copy beside `f1306`'s other
    clause.
    """
    return any(c.is_(Condition.SURPRISED, on=foe) for foe in c.enemies())


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons."

    `Gear` has no hands, so this counts what is carried: two weapons that are
    not fired is as close as the model gets to one in each fist.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _ally_steps_beside(c: Cast, who: int | None) -> None:
    """"One ally adjacent to you can shift 1 square as a free action. The
    ally's shift must end in a square adjacent to the target."

    `f990`'s clause on `p919`. The second sentence is a hard filter and
    `toward=` is not one: `c.shift(1, who=friend, toward=who)` only
    *offers* the near squares first, so a step ending out of reach is
    still allowed. So the destination is narrowed to the target's own ring
    and named to `c.shift` outright.

    Written here rather than reached for: `warlord/level_1._shift_beside`
    says the same printed sentence, but it steps the **caster**, and the
    whole of this clause is that somebody else moves. A free action costs
    nothing, so the only gate the sentence prints is which ally.
    """
    if who is None:
        return
    pool = [a for a in c.within(1, side="ally") if a != c.me]
    friend = c.choose(pool, f"{c.ref}: which ally steps") if pool else None
    if friend is None:
        return
    wanted = spread(squares_of(c.world, who), 1)
    here = squares_of(c.world, friend)
    options = sorted(
        sq for sq in c.world.reachable_squares(friend, 1)
        if sq in wanted and sq not in here
    )
    where = (c.choose(options, f"{c.ref}: where that ally ends up")
             if options else None)
    if where is not None:
        c.shift(1, who=friend, to=where)


def _second_shot(c: Cast, who: int | None) -> None:
    """"If you are wielding a ranged weapon and this attack misses, you can
    grant combat advantage to all enemies until the start of your next turn
    to make a ranged basic attack against the same target as a free
    action."

    `f991`'s clause on `p917`. One optional trade and not two clauses, so a
    declined `c.may` leaves both halves alone -- the price is the character's
    own defence and the thing bought is the second shot.

    `c.grants_advantage`'s own words name the caster's side, so handing it
    to the other one is `to=<that enemy>`, once per enemy, with `on=c.me`
    for who is exposed. A bare call would say the **target** grants it,
    which is the opposite of what is being sold.

    "Against the same target" is this body's own target, which `c.strike`
    has already resolved against by the time the miss is known.
    """
    if who is None or not c.may("grant combat advantage for a second shot"):
        return
    for foe in c.enemies():
        c.grants_advantage(on=c.me, to=foe, until=When.SONT)
    c.basic(on=who, ranged=True)


def _has_ranged(world: World, eid: int) -> bool:
    """The ranged half of "two melee weapons or a ranged weapon".

    The printed Requirement is the two branches' requirements joined by
    "or", so checking it whole said yes to both branches when only one was
    true -- a ranger on the two-blade leg, carrying no bow, was offered the ranged
    branch, and an archer holding one blade was offered the melee one.
    """
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


@power(
    "p1505",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1505(c: Cast) -> None:
    """**`f980`'s and `f988`'s clauses are written in here** (#550): a feat
    naming one power has its clause in that power rather than registering a
    rider against it, with `c.credit` naming the feat for what this body
    does.

    Both are `[Arena Fighting]`, so one `c.declare` chain and one of them
    pays. Both were `resolved=` riders -- the `PowerResolved` window, after
    the whole use -- so both sit after the attack and neither reads the
    outcome, which is what their printed sentences say.

    **`f980`'s clause is a speed modifier and never `c.extend_move`.** This
    row moves nobody: its Effect line is about not provoking on the way
    out, so "if you move after the attack, you can move up to your speed +
    2" is about the character's *own* move action later in the turn and
    there is no distance here to lengthen. `When.EOT` is wider than the
    card by any second move in the same turn, which a standard action
    usually leaves none of.
    """
    arena = c.declare("Arena Fighting", "f980", "f988")
    # The Effect line -- moving away afterwards does not provoke from this
    # target -- has nowhere to go yet, so only the attack is here.
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    if arena == "f980":
        with c.credit("f980"):
            c.bonus("speed", 2, on=c.me, until=When.EOT)
    elif arena == "f988" and c.race_of() == "r3":
        with c.credit("f988"):
            # "If it is available" is `c.use_power`'s own return, and the
            # free action costs nothing because the verb never charges one.
            c.use_power("p1449")


@power(
    "p917",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC, plus=2),
    attack_alt=Attack(DEX, vs=AC, plus=2),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p917(c: Cast) -> None:
    """Four feats write a clause into this row, which is #550's convention:
    a feat naming one power has its clause in that power rather than
    registering a rider against it, credited back to the feat with
    `c.credit`.

    **Two plain `if`s and a two-branch chain.** Neither `f1297` nor `f1300`
    carries a category bracket in the compendium (`feat.category` is empty
    for both), so nothing limits how many of them apply to one use -- an
    `if`/`elif` would hand a character holding both only one of the two it
    is entitled to. `f981` and `f991` are both `[Arena Fighting]`, where one
    feat of the bracket applies per use, so they are read off `c.declare`
    and never off `c.feat`, which is true of every feat held.

    **`f991`'s is the one clause that is not about the hit.** It prints "if
    this attack **misses**", which was `_riders`' `missed=` window, so it is
    the `else` of the strike and nothing below it can see. The weapon it
    asks about is the character's and not this row's **branch**:
    `_has_ranged` is the same read `requires_alt` makes, but the card asks
    whether a bow is in hand rather than which of the two attack lines was
    taken -- a ranger can be holding one and swinging the other.

    `f981`'s half asks whether the target has damaged this character since
    the end of their last turn. `c.hurt_me_since` reads that off the bus
    log (#556), so there is nothing to arm and a body is not too late --
    which is the whole reason the clause could move.

    **All three go after the strike**, because all three were registered in
    `exploits._riders`' `clauses` table and that table is the `Hit` window.

    `f1297`'s half asks for the melee branch of this two-branch row and
    for combat advantage. `c.ranged` is the branch reader -- through
    `dsl.reach_of`, so a creature holding a reshape gets the shape it is
    using rather than the printed one, which is a shade better than the
    header read the rider did. The advantage is read off `c.result`:
    asking the board again after the roll is too late, because a one-shot
    grant has already been spent by then.

    `f1300`'s half is Constitution-gated, and the gate has to survive the
    move -- a modifier of 0 or less pays nothing.
    """
    arena = c.declare("Arena Fighting", "f981", "f991")
    if not c.strike():
        if arena == "f991" and _has_ranged(c.world, c.me):
            with c.credit("f991"):
                _second_shot(c, c.target)
        return
    c.damage(c.w(1), c.attack_mod)
    foe = c.target
    if foe is None:
        return
    if arena == "f981" and c.hurt_me_since(foe):
        with c.credit("f981"):
            c.flat(c.wis_mod, on=foe)
    if (c.feat("f1297") and not c.ranged
            and c.result is not None and c.result.advantage):
        with c.credit("f1297"):
            c.slowed(on=foe, until=When.EONT)
    if (c.feat("f1300") and c.con_mod > 0
            and any(c.is_(hold, on=foe) for hold in _HELD_FAST)):
        with c.credit("f1300"):
            c.flat(c.con_mod, on=foe)


@power(
    "p919",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p919(c: Cast) -> None:
    """**`f973`'s and `f990`'s clauses are written in here**, which is
    #550's convention, with `c.credit` naming the feat for what this body
    does.

    Read off `c.declare` rather than `c.feat`, because both are
    `[Arena Fighting]` and one feat of that bracket applies to one use.
    `f980` lays a standing modifier on this row from its own file and
    `f994` substitutes the shift below through `c.pre_empt`, so neither is
    in the chain and both can still apply alongside whichever branch pays.

    `f973`'s clause sits **inside the hit branch**, which is the window its
    rider was registered in.

    **`f990`'s turns on the shift happening, so it is read off the step's
    own return.** "If you shift after the attack, one ally adjacent to you
    can shift 1 square" -- and `c.instead_of` hands back whatever ran, so a
    character who took `f994`'s substitution and forwent the shift gets a
    falsy answer and no ally step. That is the printed condition exactly,
    with nothing to remember and nothing to re-read.

    Its rider could not say any of that: it was in `_riders`' `Hit` table,
    which fires before this line and cannot see whether the shift was taken
    -- so out there it paid on any hit, and it dropped the second printed
    sentence about where the ally has to end up as well.
    """
    arena = c.declare("Arena Fighting", "f973", "f990")
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        if arena == "f973":
            with c.credit("f973"):
                # The whole of the clause the rider laid: one square, on a
                # hit, with no further gate.
                c.shift(1)
    # "Before or after": after is the half that can be taken here.
    stepped = c.instead_of("shift", lambda: c.shift(1))
    if arena == "f990" and stepped:
        with c.credit("f990"):
            _ally_steps_beside(c, c.target)


def _both_hands(c: Cast, *groups: str) -> bool:
    """"While you wield a spear and a flail" -- both hands, not just the main.

    `c.wielding` reads the *main* weapon's group, so it answers False for
    the off-hand one and the printed pair could never both be true.
    `c.held` is every weapon in hand.

    **`on=c.me`, and it was missing: `c.held` follows `c.target`.** It is
    one of the verbs in `docs/AUTHORING.md`'s "theirs" list -- `c.my_weapon`'s
    own docstring says so outright -- so a bare call asked what the
    *creature being hit* was holding. A monster is spawned with an empty
    `Gear()`, so this answered False in every fight and `f974`'s clause on
    `p87` could never pay. Driven on a board: `c.held()` returned 0 weapons
    for a caster holding two.
    """
    return all(c.held(what=group, on=c.me) for group in groups)


def _p87_both_swings(c: Cast, arena: str, doom: bool,
                     hunts_undead: bool) -> None:
    """The five clauses on `p87` that are about **both** of its swings.

    A `PowerResolved` watcher rather than a reading taken in the body, and
    the reason is that row's target line: it spreads two attacks over one
    **or two** creatures, and a body runs once per target -- so with two
    targets neither call can see the other's roll. `PowerResolved.rolls` is
    every `AttackResult` the use made, which is the only place "both
    attacks miss" can be answered, and it is the window all three were
    registered in out in `exploits._riders`.

    Armed on the first target, and each clause carries its own `c.credit`
    block: the outer one is popped when the body returns and the event
    comes after.

    **The watch ends itself on the use that armed it, paid or not**, rather
    than latching a flag. An action point buys a second standard action, so
    two uses of this row in one turn are possible -- and a flag only stops
    the double payment when the first use *paid*. Two live watchers would
    otherwise both answer the second use's one event.

    The gate is `ev.power != ref` and that is load-bearing: a use of this
    row announces a second `PowerResolved` for the quarry feature it
    triggers, with an empty `rolls`, and it arrives **first**. A handler
    that only checked the actor would spend itself on that one and read no
    swings at all.

    **`doom` is `f1304`'s clause and is a fourth, independent decision**
    rather than a branch of the chain: that feat carries no category
    bracket, so it pays alongside whichever of the three arena branches
    did. It was a `resolved=` rider out in `exploits._riders` for the same
    reason the other three were -- "if you hit with **both** attacks" is a
    sentence about the whole use. Its rider counted the swings off the bus
    log through `general_h._swings`; `ev.rolls` is one `AttackResult` per
    swing and is the reader that function's own docstring points at.

    **`hunts_undead` is `f1102`'s clause and is the fifth, also unbracketed**,
    so it pays alongside whichever arena branch did and alongside `doom`.
    Same window and the same reader for the same reason: "extra damage ...
    if you hit with both attacks". Its rider read the swings through
    `general_h._swings` too, and that function's own docstring says what it
    needs is the per-swing ordering, "which both now give" -- `ev.rolls` is
    2 on this row whether the two swings went into one creature or two.

    The pair of blades is asked of the **hands** and not of the branch: the
    row's own Requirement is "two melee weapons *or* a ranged weapon", so
    the branch would say nothing, and the card asks about the character,
    who can hold two blades while taking the ranged leg. `ranged is None`
    is how the rows here count a melee weapon. One lot of damage on one
    creature, because the clause names an undead creature in the singular
    and two swings can catch two.

    **Every `c.held` here passes `on=c.me` and none of them did** --
    `f977`'s and `f989`'s as well as the new one. See `_both_hands` above
    for the measurement: that verb follows `c.target`, so all three asked
    the *monster* what it was holding and answered False in every fight.
    """
    me, ref = c.me, c.ref
    held: list[Any] = []

    def finished(ev: Any) -> None:
        if ev.actor != me or ev.power != ref:
            return
        if held:
            c.end_effect(held.pop(), why="this use is over")
        caught = [roll.target for roll in ev.rolls if roll.hit]
        # Not `not caught`: a use that rolled **nothing** also has no hits,
        # and "both attacks miss" is a sentence about two attacks that
        # happened.
        all_missed = bool(ev.rolls) and not caught
        if (arena == "f977" and all_missed
                and len(c.held(what="light thrown", on=c.me)) >= 2):
            # The pair is counted rather than asked for: `c.wielding` reads
            # the main hand only, so it answers True for one such weapon
            # and a shield, which is not the printed hand.
            with c.credit("f977"):
                c.shift(1)
        elif arena == "f985" and all_missed and c.wielding("two-weapon"):
            # "+2 shield bonus to AC **against the target or targets of
            # your attacks**" -- gated, because the card is explicit that it
            # is worth nothing against anybody else. `ctx["attacker"]` is
            # who is swinging, and `resolve` puts it in the defence context
            # for exactly this.
            against = {roll.target for roll in ev.rolls if roll.target}
            with c.credit("f985"):
                c.bonus(AC, 2, on=me, until=When.EONT, kind="shield",
                        when=lambda ctx: ctx.get("attacker") in against)
        elif (arena == "f989" and len(caught) > 1
                and len(c.held(what="light blade", on=c.me)) > 1):
            with c.credit("f989"):
                c.flat(c.dex_mod, on=caught[-1])
        if doom and len(caught) > 1:
            # "If you hit with both attacks, **one** target takes the
            # penalty" -- one and not one per hit. Where both swings went
            # into the same creature there is nothing to pick; where they
            # caught two, the choice is the character's.
            pool = sorted(set(caught))
            who = (pool[0] if len(pool) == 1
                   else c.choose(pool, f"{ref}: who takes the penalty"))
            if who is not None:
                with c.credit("f1304"):
                    c.penalty("attack", 2, on=who, until=When.EONT)
        if (hunts_undead and len(caught) > 1 and c.wis_mod > 0
                and len([w for w in c.held(on=c.me) if w.ranged is None]) >= 2):
            dead = [foe for foe in dict.fromkeys(caught)
                    if c.is_kind("undead", on=foe)]
            if dead:
                who = (dead[0] if len(dead) == 1 else c.choose(
                    dead, f"{ref}: who takes the extra damage"))
                if who is not None:
                    with c.credit("f1102"):
                        c.flat(c.wis_mod, on=who)

    held.append(c.watch(PowerResolved, finished, until=When.EOT, on=me,
                        label=f"{ref} both swings"))


@power(
    "p87",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p87(c: Cast) -> None:
    """Two attacks, spread over one or two creatures.

    One target and both attacks go into it; two targets and each gets one.
    `c.first and c.last` is how a per-target body asks how many there are.

    The melee branch is main weapon then off-hand, as printed; the ranged
    branch is two shots from the same bow, so `hand` only matters on the
    branch that has two hands in it.

    **`f1298`'s clause is written in here**, per #550: extra damage equal
    to the character's Intelligence modifier against one of the four kinds
    that card names. It was registered in `exploits._riders`' `clauses`
    table, which is the `Hit` window, and this row announces one `Hit`
    **per swing** -- so the clause goes inside the loop, where a
    two-swing use into one creature pays it twice exactly as the rider
    did. Outside the loop it would pay once, which is a quiet halving.

    The Intelligence gate has to survive the move: a modifier of 0 or less
    pays nothing. `foe` is read back *after* `c.strike()`, because the
    strike writes the target it actually resolved against.

    **Six more feats print a clause here and all six are
    `[Arena Fighting]`**, so they are one `c.declare` chain and exactly one
    of them pays per use. `f1298`, `f1304`, `f1306` and `f1102` carry no
    bracket and stay plain `if`s beside the chain, each stacking with
    whichever branch paid and with each other.

    **`f1102`'s clause is written in here too** (#550), off
    `feats/general_g.py`, and it is about both swings -- so it is in
    `_p87_both_swings` with `f1304`'s and for the same reason. It was the
    last `_riders` registration that file held.

    **`f1304`'s and `f1306`'s clauses are written in here** (#550), off
    `feats/general_h.py`. `f1306`'s goes inside the swing loop beside
    `f1298`'s and for the same reason: it was in the `Hit` table and this
    row announces one `Hit` per swing, so outside the loop a two-swing use
    into one creature would pay once where the rider paid twice. Its "if
    you are making melee attacks, or ... ranged attacks" is the **branch**
    this use took rather than the weapon in hand, which `c.ranged` reads
    off `dsl.reach_of` -- the rider asked the same question of the `Hit`
    through `general_h._melee_half`. `f1304`'s is about both swings and is
    in `_p87_both_swings`.

    Each clause sits in the window its printed sentence names, which is
    four different places in one body:

    * `f978`'s -- "shift 1 square after the **first** attack" -- is after
      the first swing and does not read the outcome. The double-weapon test
      is asked twice because the hand word lives in two places and neither
      is populated on every object a character can hold: `chargen`'s
      hand-written weapon constants set `properties` and leave `hands`
      empty, and a magic weapon is a copy of one of those. Its `c.held`
      half needed `on=c.me` and did not have it -- `_both_hands` above has
      the measurement, and `c.wielding` beside it was already right.
    * `f992`'s "+1 to the second attack's attack roll" needs no ordering
      machinery: a bonus laid by a hit with `once=True` is spent by the
      next roll, and for a two-swing use that is the second attack.
    * `f974`'s names **one creature hit by both attacks**, which this row
      can only do when it has a single target -- with two, each gets one
      swing -- so it reads the landings this body made rather than the use's
      whole roll list.
    * the other three, and `f1304`'s, are about both swings together and
      are in `_p87_both_swings`, which says why.

    **This body now reads Strength and Dexterity**, which it did not
    before -- `c.attack_mod` is the branch's own ability and
    `chargen._leans_on` does not read it. Every one of the ranger's five
    builds has one or both, so all five score this row higher than they
    did and the order they are offered in moves. Recorded rather than
    avoided: the two modifiers are what `f1306`'s card prints.
    """
    arena = c.declare(
        "Arena Fighting", "f974", "f977", "f978", "f985", "f989", "f992")
    doom = c.feat("f1304")
    hunts_undead = c.feat("f1102")
    if c.first and (doom or hunts_undead
                    or arena in ("f977", "f985", "f989")):
        _p87_both_swings(c, arena, doom, hunts_undead)
    shots = 2 if (c.first and c.last) else 1
    landed: list[int] = []
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        hit = c.strike()
        if (arena == "f978" and c.first and swing == 0
                and (c.wielding("double")
                     or any(w.hands.lower() == "double"
                             for w in c.held(on=c.me)))):
            with c.credit("f978"):
                c.shift(1)
        if not hit:
            continue
        c.damage(c.w(1, hand=hand), c.attack_mod)
        foe = c.target
        if arena == "f992":
            with c.credit("f992"):
                c.bonus("attack", 1, on=c.me, until=When.EOT, kind="feat",
                        once=True)
        if foe is not None:
            landed.append(foe)
        if (foe is not None and c.feat("f1298") and c.int_mod > 0
                and _is_named_kind(c, foe)):
            with c.credit("f1298"):
                c.flat(c.int_mod, on=foe)
        if foe is not None and c.feat("f1306") and _surprise_round(c):
            with c.credit("f1306"):
                c.flat(c.dex_mod if c.ranged else c.str_mod, on=foe)
    if (arena == "f974" and len(landed) == 2 and landed[0] == landed[1]
            and _both_hands(c, "spear", "flail")):
        with c.credit("f974"):
            c.slide(1, on=landed[0])


@power(
    "p1386",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p1386(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
    c.shift(1 + c.wis_mod)


@power(
    "p1510",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p1510(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p2209",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p2209(c: Cast) -> None:
    """Two swings, and a bonus if both land.

    Main weapon then off-hand in melee, two shots at range -- the printed
    line names the hands only for the branch that uses two.
    """
    landed = 0
    for swing in range(2):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand=hand), c.attack_mod)
    if landed == 2:
        c.flat(c.wis_mod)


@power(
    "p843",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    trigger=_MELEE_AGAINST_YOU,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_MELEE_AGAINST_YOU),
)
def p843(c: Cast) -> None:
    """The printed line is "make a basic attack", which nothing here can call.

    Written out longhand instead: the same roll and the same damage a ranged
    basic attack would make, with the Wisdom bonus the Special line grants.

    The printed line shoots *the triggering enemy*, and this does not: the
    body takes whatever `use` aims it at, which with two enemies in reach is
    the wrong one. Left as written -- the fix belongs in the dispatcher,
    which knows the event and hands it over as `c.trigger`.
    """
    c.shift(1)
    if c.attack(c.dex_ + c.wis_mod, AC):
        c.damage(c.w(1), c.dex_mod)


@power(
    "p851",
    level=1,
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
def p851(c: Cast) -> None:
    for _ in range(2):
        if c.strike():
            c.damage(c.w(2), c.str_mod)
        else:
            c.half_damage(c.w(2), c.str_mod)


@power(
    "p393",
    level=1,
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
def p393(c: Cast) -> None:
    """Off-hand first, then a step, then the main weapon regardless of the miss.

    Both `c.w()` calls roll the main weapon: the off-hand's own dice are not
    reachable, so the opening 1[W] is one die too large for a ranger whose
    hands hold different weapons.
    """
    if c.strike():
        c.damage(c.w(1))
    c.shift(1)
    if c.attack(c.str_, AC):
        c.damage(c.w(2), c.str_mod)
        c.weakened()


@power(
    "p868",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p868(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.ongoing(5)
    else:
        c.half_damage(c.w(2), c.attack_mod)
        c.slowed()


@power(
    "p2207",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p2207(c: Cast) -> None:
    """Two targets, one arrow each.

    The printed row rolls twice, keeps the better roll and applies that one
    result to both targets, and it wants the two of them within 3 squares of
    each other. Neither the shared roll nor the spacing can be said here, so
    each target is simply attacked on its own.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
