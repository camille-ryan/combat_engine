"""Swordmage, level 9: the first seven dailies.

Three of these print an Effect the `Cast` surface can only say part of, and
each says so in its own docstring rather than quietly looking finished.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    INT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    SavingThrow,
    TurnStart,
    When,
    ZoneEntered,
    power,
)

from . import beside

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10433",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p10433(c: Cast) -> None:
    """The standing move action is a teleport mode of 1. Its other half --
    spending that move action on the *target* instead of yourself -- has no
    method behind it, so only my own step is here."""
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
    c.mode("teleport", 1, until=When.ENCOUNTER, on=c.me)


@power(
    "p16014",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=WILL),
)
def p16014(c: Cast) -> None:
    """The printed Effect cuts the target out of its own side for the
    purpose of powers and auras. Nothing on the board can change whose side
    a creature counts as, so the hold is named and the damage is the row."""
    if not c.marked():
        return
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.effect(f"{c.ref} alone", until=When.ENCOUNTER)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.effect(f"{c.ref} alone", until=When.EONT)


@power(
    "p3364",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p3364(c: Cast) -> None:
    """The light is a sight rule, not a combat effect, so it is a note."""
    if c.strike():
        c.damage(c.w(), c.int_mod)
        c.blinded(until=When.SAVE_ENDS)
        c.note(f"{c.ref}: the target sheds bright light and cannot hide in it")


@power(
    "p3365",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION, Keyword.RELIABLE],
    attack=Attack(INT, vs=AC),
)
def p3365(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        c.teleport(5, who=c.target)


@power(
    "p3366",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.CONJURATION],
    attack=Attack(INT, vs=AC),
)
def p3366(c: Cast) -> None:
    """The duplicate is a conjuration that stands in the way. The rest of
    the printed block -- sharing my actions, swinging from its square -- is
    a second body on the board, which a conjuration is not."""
    if c.strike():
        c.damage(c.w(), c.int_mod)
    spot = beside(c, c.target) if c.target is not None else None
    if spot is not None:
        c.conjure(at=spot, label=c.ref, until=When.ENCOUNTER, sustain=None)


@power(
    "p3952",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.HEALING],
    attack=Attack(INT, vs=AC),
)
def p3952(c: Cast) -> None:
    """Regeneration while bloodied is a heal at the top of each of my turns,
    checked then rather than now -- the printed line is about the state I am
    in when the turn comes round, not the state I am in as this lands."""
    me = c.me
    tick = 2 + c.con_mod
    if c.strike():
        c.damage(c.w(2), c.int_mod)

        def mend(ev: TurnStart) -> None:
            if ev.actor == me and not ev.ghost and c.bloodied(on=me):
                c.heal(tick, on=me)

        c.watch(TurnStart, mend, until=When.ENCOUNTER, on=me, label=c.ref)
    else:
        c.half_damage(c.w(2), c.int_mod)
        c.heal(tick, on=me)


@power(
    "p4803",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=AC),
)
def p4803(c: Cast) -> None:
    """The printed Effect is a token that walks the board, catching whoever
    stands on it and moving a square a round when nobody is burning.

    **`c.place_scenery()` was the wrong symbol and nothing new was
    needed.** The old note said "nothing puts an unowned, self-moving token
    on the board", and both halves of that misread what the card wants:

    * It is not **unowned**. The flames move *"at the start of your turn"*
      and are placed by *"you"*, so they are this character's, which is
      what a zone already is -- `Zone.owner`.
    * It is not **self-moving**. `c.move_zone` has existed since the five
      rows printing *"as a move action you can move the zone"*, and it is
      the same verb: a zone moved a square, keeping its shape.

    So the token is a one-square `c.zone` and the loop is three watches.
    Each of the four mechanics was driven before the row was written:

    * **a one-square zone** -- `c.zone({sq})`, and `Zones.occupants`
      reports who stands in it.
    * **moving it** -- `c.move_zone(z, 1, to=sq)` returns True and the
      footprint moves.
    * **moving it ONTO somebody** -- `move_zone` calls `Zones.refresh`,
      which diffs occupancy and announces `ZoneEntered`, so **one** watch
      covers walking in *and* being walked over. That is the mechanic the
      row would otherwise need a second, separate check for.
    * **the save that re-places it** -- `effects.save` announces
      `SavingThrow` with `against == str(eff)`, which is the match
      `_saves_against_mine` already uses.

    **On the board exactly when nobody is burning**, which is what makes
    the move clause a one-line test rather than a census. Catching a
    creature takes the flames off (`Zones.end`), and its save puts them
    back beside it -- so *"if no creature is currently affected by the
    flames"* is "the token is on the board", and no separate bookkeeping
    says which.

    **The hit's own burn is not the flames**, so the creature this lands on
    can still be caught once. The Effect line distinguishes them in as many
    words -- *"the ongoing damage from this power"* against *"these
    flames"* -- and the once-per-encounter limit is printed about the
    second.

    Two narrowings, both named rather than approximated:

    * **The flames land on a free square.** `beside` skips an occupied one,
      so they are never placed straight onto a creature. The card does not
      forbid that, and placing them there would catch instantly; this is
      the conservative reading and the convention three sibling rows in
      this file already use.
    * **A zone ends when its owner dies** -- `Zones.refresh`'s Death Ends
      rule, which is engine-wide and not this card's. The card says the
      flames last to the end of the encounter.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("1d10", c.int_mod, dtype=DamageType.FIRE)
        return
    c.damage("1d10", c.int_mod, dtype=DamageType.FIRE)
    burn = c.ongoing(5, DamageType.FIRE)
    if burn is None or victim is None:
        return

    # The token's zone id while it is on the board, and empty while a
    # creature is burning. One list because the watches below close over it.
    token: list[int] = []
    #: Whoever the flames have already caught. *"A creature can be affected
    #: by these flames only once in an encounter."*
    scorched: set[int] = set()
    #: The burns whose save puts the flames back -- the hit's own, and then
    #: one per creature caught. Matched on `str(eff)`, which is
    #: `_saves_against_mine`'s reading: `Effect.__str__` opens with `e<id>`,
    #: so it pins the one effect without parsing the display string.
    watched: set[str] = {str(burn)}

    def catch(who: int) -> None:
        """One creature standing in the flames burns, and they go out.

        **Takes the creature rather than reading `Zones.occupants`**, and
        that is not a style choice. `Zones.refresh` assigns
        `self.inside[eid] = now` **after** its emit loop, so inside a
        `ZoneEntered` handler `occupants()` still answers the *old* set --
        empty, for a zone nobody had stood in. Reading it there made the
        whole loop a no-op while every piece of it worked in isolation:
        the flames arrived, the creature was an occupant a moment later,
        and nothing had happened.
        """
        if not token or who in scorched:
            return
        caught = c.ongoing(5, DamageType.FIRE, on=who)
        if caught is None:
            return
        scorched.add(who)
        watched.add(str(caught))
        # *"And you remove the flames from the board."*
        c.world.zones.end(token.pop(), "the flames are taken up")

    def arrive(near: int) -> None:
        """*"Place the flames in a square adjacent to that creature."*"""
        if token:
            return
        spot = beside(c, near)
        if spot is None:
            return
        token.append(c.zone({spot}, until=When.ENCOUNTER, label=f"{c.ref} flames"))
        # A creature may already be standing there: `beside` refuses a
        # square with an *occupant*, but a big creature's footprint spans
        # squares the grid does not call its own. Safe to read `occupants`
        # here -- no `ZoneEntered` is in flight, which is the one moment it
        # answers staleley.
        for who in c.world.zones.occupants(token[0]):
            catch(who)

    def entered(ev: ZoneEntered) -> None:
        if token and ev.zone == token[0]:
            catch(ev.actor)

    def saved(ev: SavingThrow) -> None:
        if not ev.saved or ev.against not in watched:
            return
        watched.discard(ev.against)
        arrive(ev.actor)

    def my_turn(ev: TurnStart) -> None:
        # *"If no creature is currently affected by the flames, move the
        # flames 1 square at the start of your turn."* The token being on
        # the board **is** no creature being affected, so this needs no
        # other test. `move_zone` refreshes, so walking the flames onto
        # somebody announces the entry `entered` answers.
        if ev.ghost or ev.actor != c.me or not token:
            return
        c.move_zone(token[0], 1)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)
    c.watch(SavingThrow, saved, until=When.ENCOUNTER)
    c.watch(TurnStart, my_turn, until=When.ENCOUNTER)
