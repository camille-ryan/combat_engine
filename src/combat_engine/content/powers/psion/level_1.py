"""Psion, level 1.

The augmentable rows here ask `augment` how many power points this use is
bought with and branch on the answer. A clause that rewrites the **header**
-- a wider target line, a burst where the base is a single target -- is the
one shape a body cannot honour, because targeting happens before the body
runs; those are named in the docstring and recorded in `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Augment,
    Cast,
    Damage,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    Ranged,
    Summon,
    TurnEnd,
    TurnStart,
    When,
    Window,
    get,
    power,
    spread,
)

PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]
PSIONIC_FORCE = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]


@power(
    "p11269",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_FORCE, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=FORT),
)
def p11269(c: Cast) -> None:
    """Augment 1 pushes the target by Wisdom instead of 1 square; the enemies
    beside you are pushed 1 either way. Augment 2 adds Wisdom to the damage and
    knocks the target prone."""
    spent = augment(c)
    if c.strike():
        extra = c.wis_mod if spent == 2 else 0
        c.damage("1d8", c.int_mod + extra, dtype=DamageType.FORCE)
        if spent == 2:
            c.prone()
        c.push(c.wis_mod if spent == 1 else 1)
        for foe in c.within(1, of=c.me, side="enemy"):
            if foe != c.target:
                c.push(1, on=foe)


@power(
    "p11270",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_FORCE, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=REF),
    #: *"You can use this power unaugmented as a ranged basic attack."*
    #: "As" and not "in place of", which 4e means differently -- see
    #: `Power.basic`, which carries Camille's wording -- so this row **is**
    #: a ranged basic attack and collects a "with basic attacks" modifier.
    #: `basic_at` is the printed word *unaugmented*: augment it and it is
    #: an ordinary power again. #1298.
    basic="ranged",
    basic_at=(0,),
)
def p11270(c: Cast) -> None:
    """Both augments raise the dice and pull by Wisdom rather than 1 square.

    The printed Special -- usable unaugmented as a ranged basic attack -- is
    declared in the header: `basic="ranged"`, scoped by `basic_at=(0,)` to
    the form the card names. #1298.
    """
    spent = augment(c)
    if c.strike():
        c.damage(("1d8", "1d10", "2d10")[spent], c.int_mod, dtype=DamageType.FORCE)
        c.pull(1 if spent == 0 else c.wis_mod)


@power(
    "p11271",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=REF),
)
def p11271(c: Cast) -> None:
    """The standing "use a minor action to push the target 1 square" is written
    as a sustain-minor hold with the push as its payout -- the same shape, and
    the only one that gives a minor action somewhere to go.

    **"This effect ends if you end your turn adjacent to the target" is
    written now**, and the note calling it dropped named no obstacle --
    because there is none. It is a `TurnEnd` watch on the caster asking
    one adjacency question, and `world.effects.end` is how a row takes its
    own hold down early; `p12660` does the same thing for an aura that
    ends when its owner falls.

    The watch is bounded by the hold rather than by a clock of its own:
    `on_end` closes it, so the two cannot outlive each other.

    **And the hold is `on=c.me` now, which is a bug this clause exposed.**
    `c.effect` defaults `on=` to the **target**, so the sustain was filed
    on the enemy -- and `actions.legal` offers a sustain to the effect's
    *owner*, meaning the minor action that keeps a psion's own power up
    was being offered to the creature it was aimed at. Measured before the
    fix: `owner=2 label='p11271' sustain=minor` with the caster as 1.
    Nothing reported it, because the row fired and did something either
    way.
    """
    victim = c.target
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.FORCE)

    def shove() -> None:
        if victim is not None and c.distance(victim) <= 5:
            c.push(1, on=victim)

    hold = c.effect(c.ref, on=c.me, until=When.SUSTAIN, sustain=MINOR)
    c.on_sustain(hold, shove)
    if hold is None or victim is None:
        return
    me = c.me

    def stepped_up(ev: TurnEnd) -> None:
        if ev.actor == me and not hold.ended and c.adjacent_to(victim, me):
            c.world.effects.end(hold, "you ended your turn beside it")

    watcher = c.watch(TurnEnd, stepped_up, until=When.ENCOUNTER, on=me)
    hold.on_end.append(
        lambda: c.world.effects.end(watcher, "the hold is over")
    )


@power(
    "p11272",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11272(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.FORCE)

    spent = [False]

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == victim and not spent[0]:
            spent[0] = True
            c.flat(5, dtype=DamageType.FORCE, on=victim)

    c.watch(MoveEnd, stirred, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p13302",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.TELEPORTATION, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=FORT),
)
def p13302(c: Cast) -> None:
    """Both augments narrow the burst to enemies, which a body can honour by
    leaving anybody else alone -- a *narrower* target line is the one kind the
    header does not have to be rewritten for. Augment 2 also raises the dice
    and lets the target land inside the burst rather than only outside it."""
    spent = augment(c)
    victim = c.target
    if spent and victim not in c.enemies():
        return
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod)
        burst = c.area()
        ring = spread(burst, 1) if spent == 2 else spread(burst, 1) - burst
        for sq in sorted(ring):
            if c.teleport(3, who=victim, to=sq):
                break


@power(
    "p13303",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.FORCE,
        Keyword.CONJURATION, Keyword.AUGMENTABLE],
)
def p13303(c: Cast) -> None:
    """Two clauses are dropped. "Any enemy that enters the shard's space"
    cannot happen: `c.conjure` occupies its square, so a zone laid over that
    one square would never have anybody in it -- a dead clause rather than a
    weak one. The minor-action attack made through the shard is `p13303b`,
    which the importer now gives a ref of its own; Augment 2 is that block's
    dice, so it belongs to that row rather than this one.

    Augment 1 is the shard's speed: `speed=` is how far its creator may move
    it with a move action, which is exactly what the clause grants.

    **The offer is `(2, 1)` even though Augment 2 belongs to the other
    block.** The points are spent *here* -- `augment` is called on this row
    and `spend_points` happens once -- so a parent offering only 1 makes the
    second block's Augment 2 unreachable for ever: `spent_on` can never
    return 2 because 2 was never on the menu. The clause lives there and the
    *choice* has to live here.

    And the Augment 1 clause below is gated on `spent == 1`, not on `spent`
    being truthy. An Augment line **replaces** the printed one above it
    rather than adding to it, so at 2 points this row's own clause is not
    paid at all.
    """
    spent = augment(c, 2, 1)
    c.conjure(until=When.EONT, sustain=None,
              speed=5 if spent == 1 else 0)


@power(
    "p13305",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_PSYCHIC, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=WILL),
    augments=(
        Augment(1),
        Augment(2, reach=AreaBurst(1, 10), target=EACH_CREATURE),
    ),
)
def p13305(c: Cast) -> None:
    """Augment 1 roots the target as well.

    Augment 2 swaps the single shot for an area burst against each creature
    in it, which is the header, so it is declared there and the points are
    spent before the burst is aimed. It prints no Hit line of its own, so
    the base one applies to everybody caught -- and the root is Augment 1's
    alone."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)
        if spent == 1:
            c.cannot_shift(until=When.EONT)


@power(
    "p13308",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p13308(c: Cast) -> None:
    """The once-per-round secondary -- slide the held target 10 squares and
    attack somebody it passes -- is `p13308b`, gated on this hold standing on
    somebody. Only the primary is here."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p13310",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p13310(c: Cast) -> None:
    """**The lightly obscured squares are written now.** The old note said
    "`c.zone` only knows `blocks_sight`, which is total obscurement", and
    `c.zone` takes `obscured=` as well -- `"dim"` is lightly obscured and
    `"dark"` is heavily, which that kwarg's own docstring spells out.
    `blocks_sight` is the wrong flag here for the reason it gives: it is
    terrain and blinds both sides. #1341.

    **Hung on the ongoing damage, not on the hit.** The card says "WHEN the
    target takes ongoing damage from this power", which is a later turn's
    event rather than this body's -- so it is a `DamageApplied` watch
    reading `"ongoing"` out of `ev.detail`, the same way `p9411` tells its
    own ongoing tick from an ordinary blow.

    The squares are re-read each time, because the target may have moved
    between ticks and the card says "adjacent to the target" rather than
    naming a place.
    """
    if c.strike():
        c.damage("2d8", c.int_mod)
    else:
        c.half_damage("2d8", c.int_mod)
    c.ongoing(5)
    victim = c.target
    if victim is None:
        return

    def fogged(ev: DamageApplied) -> None:
        if ev.target != victim or "ongoing" not in (ev.detail or ""):
            return
        spot = c.world.get(victim, Position)
        if spot is None:
            return
        c.zone(
            sorted(spread({spot.square}, 1) - {spot.square}),
            label=f"{c.ref} haze", until=When.EONT, obscured="dim",
        )

    c.watch(DamageApplied, fogged, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} hazes")


@power(
    "p13312",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.CHARM,
    ],
    attack=Attack(INT, vs=WILL),
)
def p13312(c: Cast) -> None:
    """The save-ends hold *is* the watch: one effect on the target, so one save
    ends both the subjection and the free swing it pays out."""
    victim = c.target
    if victim is None:
        return

    def neighbours() -> list[int]:
        return [x for x in c.within(1, of=victim, side="any") if x not in (victim, c.me)]

    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)

        def each_turn(ev: TurnStart) -> None:
            if ev.actor != c.me:
                return
            near = neighbours()
            foe = c.choose(near, f"{c.ref}: whom the target strikes") if near else None
            if foe is not None:
                c.grant_attack(victim, on=foe)

        c.watch(TurnStart, each_turn, until=When.SAVE_ENDS, on=victim, label=c.ref)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
        near = neighbours()
        if near:
            foe = c.choose(near, f"{c.ref}: whom the target strikes")
            if foe is not None:
                penalty = -2 if foe in c.allies() else 0
                c.grant_attack(victim, on=foe, attack_bonus=penalty)


@power(
    "p13462",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.LIGHTNING,
        Keyword.CONJURATION, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=REF),
)
def p13462(c: Cast) -> None:
    """The detonation is the second block, `p13462b`, which fires off its own
    trigger at the start of the psion's next turn and rolls from the mote's
    square. The mote is not despawned when it goes off -- its own duration
    takes it away at the end of that turn instead.

    The augment is bought here, when the mote is conjured, and `p13462b`
    reads the spend back: Augment 1 drags one of the creatures the burst
    caught toward the mote's square, Augment 2 raises the dice."""
    augment(c)
    mote = c.conjure(until=When.EONT, sustain=None, aura=1)
    if not mote:
        return

    def creep(ev: TurnStart) -> None:
        pos = c.world.get(mote, Position)
        if pos is None or ev.actor == c.me:
            return
        if ev.actor in c.in_squares(spread({pos.square}, 1), side="any"):
            c.slowed(on=ev.actor, until=When.EOT)

    c.watch(TurnStart, creep, until=When.EONT, label=c.ref)


@power(
    "p8226",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*PSIONIC_PSYCHIC, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=WILL),
)
def p8226(c: Cast) -> None:
    """Augment 2 raises the dice and makes the penalty Charisma rather than 2.

    Augment 1 stops the target making opportunity attacks, which no method
    says: `c.cannot_attack` bars every attack. `AttackDeclared` carries
    `opportunity` as a plain attribute, so refusing the declaration when that
    is set is the whole clause and nothing wider."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", c.cha_mod if spent == 2 else 2, until=When.EONT)
        if spent == 1 and victim is not None:

            def refuse(ev: AttackDeclared) -> None:
                if ev.attacker == victim and getattr(ev, "opportunity", False):
                    ev.cancel("cannot make opportunity attacks")

            c.watch(
                AttackDeclared, refuse, until=When.EONT, window=Window.BEFORE,
                on=victim, label=c.ref,
            )


@power(
    "p8227",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_PSYCHIC, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=WILL),
    augments=(
        Augment(1),
        Augment(2, reach=AreaBurst(1, 10), target=EACH_CREATURE),
    ),
)
def p8227(c: Cast) -> None:
    """Augment 1 holds the invisibility a turn longer.

    Augment 2 is an area burst against each creature in it, which is the
    header, so it is declared there; its dice are doubled and its
    invisibility is the base card's shorter one, which is what the card
    prints under that heading rather than "as above"."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.invisible(
            to=c.target, on=c.me, until=When.EONT if spent == 1 else When.SONT
        )


@power(
    "p8228",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_PSYCHIC, Keyword.AUGMENTABLE],
    attack=Attack(INT, vs=WILL),
    #: *"You can use this power unaugmented as a ranged basic attack."*
    #: "As" and not "in place of", which 4e means differently -- see
    #: `Power.basic`, which carries Camille's wording -- so this row **is**
    #: a ranged basic attack and collects a "with basic attacks" modifier.
    #: `basic_at` is the printed word *unaugmented*: augment it and it is
    #: an ordinary power again. #1298.
    basic="ranged",
    basic_at=(0,),
)
def p8228(c: Cast) -> None:
    """Augment 1 is a penalty to Will equal to Charisma; Augment 2 raises the
    dice and puts that penalty on every defence.

    The Special that makes the unaugmented form a ranged basic attack is
    declared now -- `basic="ranged"` with `basic_at=(0,)`, the printed word
    being *unaugmented*. This said it "still has no header field", which was
    true of the name the two marked rows reached for and not of `Power.basic`
    beside it. #1298."""
    spent = augment(c)
    if c.strike():
        c.damage("2d10" if spent == 2 else "1d10", c.int_mod, dtype=DamageType.PSYCHIC)
        if spent == 1:
            c.penalty(WILL, c.cha_mod, until=When.EONT)
        elif spent == 2:
            for d in (AC, FORT, REF, WILL):
                c.penalty(d, c.cha_mod, until=When.EONT)


@power(
    "p8229",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8229(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    c.vulnerable(5, DamageType.PSYCHIC, until=When.SAVE_ENDS)


@power(
    "p8230",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8230(c: Cast) -> None:
    """The secondary is an Effect line -- it happens whether or not the primary
    landed -- and rolls the same attack, so it is folded in here."""
    primary = c.target
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.ongoing(5, DamageType.PSYCHIC)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.ongoing(3, DamageType.PSYCHIC)
    for foe in c.within(1, of=primary, side="enemy"):
        if foe != primary and c.strike(on=foe):
            c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC, on=foe)
            c.ongoing(5, DamageType.PSYCHIC, on=foe)


@power(
    "p13311",
    level=1,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*PSIONIC_PSYCHIC, Keyword.AUGMENTABLE, Keyword.SUMMONING],
    summon=Summon(
        speed=8,
        attack=Attack(INT, vs=AC),
        damage=Damage("1d10", "int", dtype=DamageType.PSYCHIC),
    ),
)
def p13311(c: Cast) -> None:
    """Augment 1 gives the servant a third command -- an opportunity action
    that makes a Heal check on a dying ally. `Summon` declares a standard and
    an opportunity attack and nothing else, so there is nowhere to put it."""
    c.summon_inline(get(c.ref).summon, at=c.origin)
