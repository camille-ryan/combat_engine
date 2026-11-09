"""Warlord, level 1.

The warlord spends its turn making somebody else's turn better, so most of
these bodies are a `c.choose` for which friend benefits followed by a bonus,
a shift or a heal aimed at them with `on=`.

Three printed lines have no vocabulary here and are marked with `c.note`
rather than approximated: granting an ally an attack, granting an ally an
opportunity attack, and a conditional "cannot shift".
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
    spread,
)
from combat_engine.engine.events import Hit, Moved
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _shift_beside(c: Cast, squares_: int, who: int) -> bool:
    """Shift up to `squares_` and finish next to `who`.

    `c.shift(squares_, toward=who)` only *offers* the near squares first
    and would still allow a step that ends out of reach, which is not "you
    must end the shift adjacent to the target". Squares already stood in
    are excluded: standing still satisfies the sentence when we are
    already beside somebody, and is never what the clause is for.

    Copied from `feats/exploits._shift_beside` with the clause it serves,
    for the reason `powers/rogue/level_1._HELD_FAST` gives -- a body
    cannot reach a feat module's privates, and a dozen lines is the cheap
    end of that duplication. The original keeps its last caller, a
    `swaps=` entry naming two creatures at once.
    """
    wanted = spread(squares_of(c.world, who), 1)
    here = squares_of(c.world, c.me)
    options = sorted(
        sq for sq in c.world.reachable_squares(c.me, squares_)
        if sq in wanted and sq not in here
    )
    where = c.choose(options, f"{c.ref}: where to end up") if options else None
    return where is not None and c.shift(squares_, to=where)


def _beside(c: Cast, foe: int | None) -> list[int]:
    """Allies adjacent to you or to the target, which is the warlord's pool.

    `side="ally"` leaves the caster out, which is what every printed line
    using this phrase says; the filter below is belt and braces.
    """
    near = set(c.within(1, side="ally"))
    if foe is not None:
        near |= set(c.within(1, of=foe, side="ally"))
    return sorted(near - {c.me})


# -- at-will ---------------------------------------------------------------


@power(
    "p1061",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
)
def p1061(c: Cast) -> None:
    """No attack of your own: the whole power is an ally's free attack.

    Nothing in `Cast` makes another creature attack, so this records what
    would happen instead of pretending something did.

    **`f985`'s clause is written in here** (#550), read off `c.declare`
    because that feat is `[Arena Fighting]` and one feat of the bracket
    applies per use. It was a `used=` rider -- the `PowerUsed` window,
    announced before the body -- and the card pays on the *use*, so it
    does not wait on a swing this row never makes.

    `f972`'s and `f994`'s clauses on this row could **not** move and are
    still riders in their own file: both are about the granted attack
    hitting, and this body does not make that attack. Reported with the
    migration.
    """
    arena = c.declare("Arena Fighting", "f985")
    if arena == "f985" and c.first and c.wielding("shield"):
        # "One ally adjacent to you gains a +1 shield bonus to AC."
        # `c.wielding("shield")` and not `c.held(what="shield")`: a shield
        # is a flag on `Gear` rather than a `Weapon`, so the `held` form
        # answers an empty list always.
        near = c.within(1, side="ally")
        pick = c.choose(near, f"{c.ref}: who takes the guard") if near else None
        if pick is not None:
            with c.credit("f985"):
                c.bonus(AC, 1, on=pick, until=When.EONT, kind="shield")
    foe = c.target
    helpers = [a for a in c.within(1, of=foe, side="ally") if a != c.me]
    who = c.choose(helpers, "which ally strikes")
    name = f"ally {who}" if who is not None else "an ally"
    c.note(
        f"p1061: {name} would make a melee basic attack against {foe} as a free action, "
        f"with {c.int_mod:+d} damage -- granting an ally an attack is not expressible"
    )


@power(
    "p1063",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1063(c: Cast) -> None:
    """**`f973`'s, `f980`'s and `f982`'s clauses are written in here**,
    which is #550's convention, with `c.credit` naming the feat for what
    this body lays.

    **One chain, not three `if`s**: all three are `[Arena Fighting]`, so
    one of them applies to one use and `c.declare` picks it before the
    attack. `c.feat` is true of every feat held and cannot say which.
    `f990` also prints a clause on this row and is still a rider in its
    own file, so it stacks with whichever of these pays.

    **`f980`'s clause needed `_shift_beside`**, which used to be the reason
    it stayed a rider: the helper lived in the feat's own file and a body
    cannot reach a feat module's privates. It is copied in above with the
    clause, which is what this file already does for a condition tuple.

    All three sit **inside the hit branch**, the window their riders were
    registered in.

    **`f982`'s effect is laid inside a watcher, so it carries its own
    `c.credit` block.** The outer block is popped when this body returns
    and the watcher fires later, so crediting only at the registration
    would attribute the grant to this row -- which is the whole thing the
    convention exists to avoid.
    """
    arena = c.declare("Arena Fighting", "f973", "f980", "f982")
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        victim = c.target
        if arena == "f973":
            with c.credit("f973"):
                # Extra damage on the opportunity attack this row's own
                # Effect line provokes, laid on each ally as a gated damage
                # modifier: the damage context carries both `opportunity`
                # and `target`, where the `Hit` event carries neither, and
                # there is no other way to tell an opportunity swing from
                # an ordinary one after the fact.
                for ally in c.allies():
                    c.bonus(
                        "damage", c.con_mod, on=ally, until=When.EONT,
                        when=lambda ctx, who=victim: (
                            bool(ctx.get("opportunity"))
                            and ctx.get("target") == who
                        ),
                    )
        elif arena == "f982" and victim is not None:
            with c.credit("f982"):
                # The target granting combat advantage if it shifts, paid
                # when the shift happens rather than read back later: by
                # the character's own next turn the board no longer records
                # that it moved. `kind_` is how `Moved` says which kind of
                # step it was.
                def shifted(moved: Any) -> None:
                    if (moved.actor == victim
                            and getattr(moved, "kind_", "") == "shift"):
                        with c.credit("f982"):
                            c.grants_advantage(on=victim, to="team",
                                               until=When.EONT)

                c.watch(Moved, shifted, until=When.EONT, on=c.me,
                        label=f"{c.ref} punish {victim}")
        elif arena == "f980" and victim is not None:
            # "If the target shifts before the end of your next turn, you
            # can also shift 1 square to a space adjacent to the target."
            # Paid when the shift happens rather than read back later: by
            # the character's own next turn the board no longer records
            # that it moved.
            def followed(moved: Any) -> None:
                if (moved.actor == victim
                        and getattr(moved, "kind_", "") == "shift"):
                    with c.credit("f980"):
                        _shift_beside(c, 1, victim)

            c.watch(Moved, followed, until=When.EONT, on=c.me,
                    label=f"{c.ref} follow {victim}")
    # The Effect line lands hit or miss. The trigger is armable, but what it
    # would fire -- an ally's opportunity attack -- is not.
    c.note(
        f"p1063: if {c.target} shifts before the start of your next turn it would provoke "
        "an opportunity attack from an ally of your choice -- not expressible"
    )


@power(
    "p315",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p315(c: Cast) -> None:
    """No weapon dice at all -- you point, and a friend takes the shot.

    **`f981`'s and `f992`'s clauses are written in here** (#550), as one
    `c.declare` chain because both are `[Arena Fighting]` and one feat of
    that bracket applies per use.

    `f981`'s goes **before `c.strike()`**: it is a bonus to this row's own
    attack roll, which is why it was a `used=` rider, and a bonus laid
    after the roll would be too late to have decided anything. The gate
    reads the bus log at the moment of the roll rather than snapshotting
    the set here -- a creature that hurts the character between this line
    and the swing is inside the printed window and a snapshot would miss
    it.

    `f992`'s is a crit rider off the `Hit` window and sits after the
    damage.

    **`f1299`'s clause is written in here too** (#550), unbracketed and so
    a plain `if` that stacks with whichever arena branch paid.

    **Its rider could never fire.** It sat in `_riders`' `landed=` table,
    which is keyed on `ev.granted_via` and gates on
    `ev.granted_by == me and ev.actor != me` -- a swing *handed over* by
    this row. This row hands over no swing: what it gives an ally is a
    bonus to its next attack roll and damage roll, so no event ever
    carried `granted_via == "p315"` and the clause paid nothing in any
    fight. Reported with the migration rather than fixed in place.

    So "the attack this exploit provides" is read as what the card
    describes -- the swing this row's own bonus is laid on -- and the
    clause watches for that ally hitting that target inside the same
    window the bonus holds for. One payout, because the card says "the
    attack"; its own `c.credit` block, because the blow arrives after this
    body has returned and the outer block is popped by then.
    """
    arena = c.declare("Arena Fighting", "f981", "f992")
    if arena == "f981":
        with c.credit("f981"):
            # **Untyped, because the feat's card prints no type word.**
            # `f981`'s clause for this row reads *"you gain a +2 bonus to
            # the attack roll with this exploit"* -- "a +2 bonus", with
            # nothing in front of it, which is `bonuses.py`'s own test for
            # untyped and the reading 225 specs share.
            #
            # It was written `kind="feat"`, which no card prints, and
            # `bonuses` went red naming this row: *"code says 'feat', the
            # card says ['power']"*. The `power` it compared against is
            # **this row's own** bonus to the ally, a different sentence --
            # the checker pools both clauses of a card and cannot see which
            # one a call came from, which is the cost `BORROWED`'s note
            # owns. But no waiver is warranted here: the feat names no
            # type, so untyped is simply correct.
            c.bonus("attack", 2, on=c.me, until=When.EOT,
                    when=lambda ctx: bool(c.hurt_me_since(ctx.get("target"))))
    if c.strike():
        c.damage(0, c.str_mod)
        foe = c.target
        if arena == "f992" and c.crit and foe is not None:
            with c.credit("f992"):
                # "Extra damage equal to your Constitution modifier and
                # grants combat advantage to the **next** one of your
                # allies to attack it" -- `once=True` is what "the next
                # one" means; without it every ally gets it.
                c.flat(c.con_mod, on=foe)
                c.grants_advantage(on=foe, to="team", until=When.EONT,
                                   once=True)
        helpers = _beside(c, foe)
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the opening")
        against = lambda ctx: ctx.get("target") == foe  # noqa: E731
        c.bonus("attack", c.cha_mod, on=friend, until=When.EOTNT, when=against, once=True,
            kind="power")
        c.bonus("damage", c.cha_mod, on=friend, until=When.EOTNT, when=against, once=True,
            kind="power")
        victim, helper = foe, friend
        if c.feat("f1299") and c.wis_mod > 0 and victim is not None:
            paid: list[bool] = []

            def ally_hit(ev: Hit) -> None:
                if paid or ev.attacker != helper or ev.target != victim:
                    return
                paid.append(True)
                with c.credit("f1299"):
                    c.ongoing(c.wis_mod, on=victim)

            c.watch(Hit, ally_hit, until=When.EOTNT, on=c.me,
                    label=f"{c.ref} f1299")


@power(
    "p620",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p620(c: Cast) -> None:
    """The Special line comes first: a friend steps, then you swing.

    **`f1102`'s clause is written in** (#550): a feat naming one power has
    its clause in that power, gated on `c.feat` and wrapped in
    `c.credit`, rather than registered as a rider from the feat. The
    rider is deleted in the same change.

    `f1102` is **unbracketed** (`feat.category` is empty in `game.db`), so
    a plain `if` and not a `c.declare` chain.

    It is a **second** step, not the printed Special line's one: that one
    is taken before the swing by whichever friend `_beside` offers, and
    this is "if your target is undead **and you hit**". So it is on the
    hit branch, and before `c.damage` because that is where the `Hit`
    rider fired.

    **`c.allies()` and `c.adjacent`, not `_beside`.** The rider measured
    adjacency to the caster, which is what this clause prints -- "one ally
    adjacent to you" -- where `_beside` also offers allies standing next
    to the *target*, which is the Special line's wider pool and not this
    one's. The first adjacent friend takes it, as the rider did.

    **`f975`'s clause is written in too** and it is the wider pool: "an
    ally adjacent to **you or the target**", which is what `_beside`
    answers. It is `[Arena Fighting]`, so it is read off `c.declare` and
    never off `c.feat`; `f1102` carries no bracket and stacks with it.
    Crit-gated, which is the printed condition, and `c.crit` is the reader
    for the `ev.critical` its rider used.
    """
    arena = c.declare("Arena Fighting", "f975")
    helpers = _beside(c, c.target)
    if helpers:
        c.shift(1, who=c.choose(helpers, "who steps before the blow"))
    if c.strike():
        if c.feat("f1102") and c.is_kind("undead"):
            with c.credit("f1102"):
                # "If your target is undead and you hit, one ally adjacent
                # to you can shift 1 square as a free action."
                for friend in c.allies():
                    if c.adjacent(to=friend):
                        c.shift(1, who=friend)
                        break
        if arena == "f975" and c.crit:
            near = _beside(c, c.target)
            pick = c.choose(near, f"{c.ref}: who steps") if near else None
            if pick is not None:
                with c.credit("f975"):
                    c.shift(1, who=pick)
        c.damage(c.w(1), c.str_mod)


# -- encounter --------------------------------------------------------------


@power(
    "p1064",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1064(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        helpers = _beside(c, foe)
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the guard")
        # "against the target's attacks": a defence mod is gated on who is
        # attacking, which is what the attacker sees in `ctx`.
        # One build makes this 1 + Charisma; `c.build(...)` can say which
        # now, so the rider is expressible where the printed +2 was all
        # this could say before.
        c.bonus(AC, 2, on=friend, when=lambda ctx: ctx.get("attacker") == foe, kind="power")


@power(
    "p1066",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1066(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        helpers = [a for a in c.within(5, side="ally") if a != c.me]
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the opening")
        # Tactical Presence would make this 1 + Intelligence; no build to read.
        c.bonus("attack", 2, on=friend, when=lambda ctx: ctx.get("target") == foe, kind="power")


@power(
    "p1412",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p1412(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        foe = c.target
        helpers = [a for a in c.within(1, of=foe, side="ally") if a != c.me]
        who = c.choose(helpers, "which ally strikes")
        name = f"ally {who}" if who is not None else "an ally"
        c.note(
            f"p1412: {name} would make a melee basic attack against {foe} as a free action, "
            f"with {c.cha_mod:+d} damage -- granting an ally an attack is not expressible"
        )


@power(
    "p1554",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1554(c: Cast) -> None:
    """Somebody trades places with the creature you just hit.

    The pool from `c.within(1, of=foe, side="ally")` already reads "you, only
    if you are adjacent to it, or an ally adjacent to it" -- the caster is in
    that list exactly when the printed proviso says so.

    A true swap cannot be written: `c.slide` has no destination argument, so
    the creature is slid a square and the swapper steps into the space it
    left, which is the same two squares of movement without the guarantee
    that they cross.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        swappers = c.within(1, of=foe, side="ally")
        if not swappers:
            return
        who = c.choose(swappers, "who changes places with it")
        vacated = c.there
        if who is not None and c.slide(1, on=foe):
            c.shift(who=who, to=vacated)


# -- daily ------------------------------------------------------------------


@power(
    "p154",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p154(c: Cast) -> None:
    landed = c.strike()
    if landed:
        c.damage(c.w(3), c.str_mod)
    for friend in [a for a in c.within(5, side="ally") if a != c.me]:
        if landed:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 1, on=friend, until=When.ENCOUNTER, kind="power")
        # The Effect line does not care whether the attack landed.
        c.temp_hp(5 + c.cha_mod, on=friend)


@power(
    "p239",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p239(c: Cast) -> None:
    """Hit and miss differ only in the size of the bonus."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        value = 1 + c.int_mod
    else:
        c.half_damage(c.w(3), c.str_mod)
        value = 1
    foe = c.target
    against = lambda ctx: ctx.get("target") == foe  # noqa: E731
    # "you and each ally within 5" is exactly what the ally pool holds.
    for friend in c.within(5, side="team"):
        c.bonus("attack", value, on=friend, when=against, kind="power")


@power(
    "p431",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p431(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    # "Cannot shift, while two of your allies flank it" is a conditional
    # veto on one kind of movement. Immobilised would stop everything, and
    # stop it unconditionally, so it is the wrong card.
    c.note(
        f"p431: for the rest of the encounter {c.target} could not shift while two of your "
        "allies were adjacent to it -- a conditional bar on shifting is not expressible"
    )


@power(
    "p1572",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1572(c: Cast) -> None:
    """A standing arrangement: every hit somebody lands nudges a friend.

    Hit and miss both leave the same trigger behind; they differ only in who
    gets to set it off, so one closure serves both with a different gate.
    """

    def nudge(ev: Hit) -> None:
        if not allowed(ev.attacker):
            return
        friends = [a for a in c.within(1, of=ev.attacker, side="ally") if a != ev.attacker]
        if friends:
            c.slide(1, on=c.choose(friends, "who is nudged a square"))

    if c.strike():
        c.damage(c.w(3), c.str_mod)
        beside_me = [a for a in c.within(1, side="ally") if a != c.me]
        if beside_me:
            c.slide(1, on=c.choose(beside_me, "who you shove a square"))
        squad = {c.me, *c.allies()}
        # "you or an ally within 10 squares of you" is asked when the hit
        # happens, not now -- people move.
        allowed = lambda who: who in squad and (who == c.me or c.distance(who) <= 10)  # noqa: E731
        c.watch(Hit, nudge, until=When.ENCOUNTER, label="p1572 (hit)")
    else:
        pool = [a for a in c.within(10, side="ally") if a != c.me]
        chosen = c.choose(pool, "who learns the trick") if pool else None
        if chosen is None:
            return
        allowed = lambda who: who == chosen  # noqa: E731
        c.watch(Hit, nudge, until=When.ENCOUNTER, label="p1572 (miss)")


# The class feature, p1590, is already written -- it is the same printed row
# as the cleric's heal and lives with it in `content/features/leaders.py`.
