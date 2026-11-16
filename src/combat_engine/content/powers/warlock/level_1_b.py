"""Warlock, level 1: the rows from the books after the first, part one.

Four things recur across this batch and the next, and are settled here once.

**Pacts.** `chargen.BUILDS["warlock"]` carries **eight** legs --
`infernal`, `fey`, `dark`, `elemental`, `sorcerer-king`, `star`,
`vestige`, `gloom` -- and `c.build` answers all of them.

**This paragraph used to say two, and name the other six as having "no
leg to ask for".** That is the single most expensive sentence in this
class: 33 sites across seven files dropped a printed rider citing it, and
the facility was not merely present but already in use while they were
being written -- `features/warlock.py:359` gates a whole feature on
`c.build("sorcerer-king")` and `feats/general_q.py:1828` gates a feat.

So a pact rider is **written**, with `c.build(leg)` for the leg. A *pact
boon* clause is a different mechanism and is not a build gate at all: it
is `c.spend_charge(FELL)`, whose False **is** the printed "if you spend",
settled above the attack roll because the boon's card requires the
decision before any roll. `p12887` and `p12888` are the worked pair.
#1346.

**Two damage types at once** -- "necrotic and psychic" -- is one amount
in the printed rules, and `c.damage` takes **`dtypes`** for exactly this:
"a blow that is several types at once". This paragraph used to say it
carried one `dtype` and that the first named type was dealt, which
under-sold every such row against a resistance to the second type.
#1346.

**"You do not expend this power"** is `c.restore_use(c.ref)`, which has
been on `Cast` throughout -- its own docstring is about exactly these
rows. This paragraph used to say nothing refunded a use and that was
false; `shared.backlash` carries the refund now. #1346.

**"Charisma or Constitution"** is fixed once at first level and a header
holds one ability, so the Charisma line is the one written, as `level_1.py`
already does for `p1333`.
"""

from __future__ import annotations

from combat_engine.content.features.warlock import FELL
from combat_engine.content.powers.warlock.shared import backlash
from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    MeleeOrRanged,
    MoveStart,
    Ranged,
    TurnEnd,
    UpTo,
    When,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.query import squares as squares_of

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10378",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p10378(c: Cast) -> None:
    """Losing every resistance and immunity is a named hold and nothing more.

    Nothing suppresses a creature's resistances, so the save-ends effect is
    applied for its own sake: it can be seen, it can be saved against, and
    it is what the Infernal Pact's penalty to the first save attaches to.
    """
    if c.strike():
        c.damage("3d10", c.con_mod, dtype=DamageType.PSYCHIC)
        c.effect(f"{c.ref}: resistances and immunities suppressed")
        if c.build("infernal"):
            c.penalty("save", 2, once=True)
    else:
        backlash(c)


@power(
    "p10379",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CON, vs=WILL),
)
def p10379(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        backlash(c)
        return
    c.damage("3d10", c.con_mod, dtype=DamageType.PSYCHIC)
    caught = {victim}
    if victim is not None:
        caught |= {f for f in c.within(1, of=victim, side="enemy")}
    if c.build("infernal"):
        caught |= set(c.within(2, side="enemy"))
    for foe in sorted(f for f in caught if f is not None):
        c.penalty("attack", 2, on=foe)


@power(
    "p11303",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p11303(c: Cast) -> None:
    """**This row's pact boon is written now.** It was dropped as having "no
    leg to ask for", and the leg was always there -- `BUILDS` carries
    eight. The boon itself lives in `features.warlock._granted_boon`,
    with the other seven, because `cf:warlock-f1c12` is the card that
    asks which remnant is active and pays it, and a boon fires long
    after this body has finished. The leg offers this remnant to a
    warlock that `c.knows` this row. #1346.

    **The `p6855` augment this card also prints is NOT written.** That
    is a second clause with a second home -- `_vestige_augment`, keyed
    the same way -- and `p6855` is the same card as `cf:warlock-f1c11`
    under a second compendium id. #1348.
    """
    if c.int_mod > 0 and c.may("step", who=c.me):
        c.shift(c.int_mod)  # "before or after"; before is what a body can take
    if c.strike():
        c.damage("3d6", c.con_mod)
    else:
        c.half_damage("3d6", c.con_mod)


@power(
    "p12307",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p12307(c: Cast) -> None:
    """"Reroll the attack roll" on your own miss is written as a second swing.

    `c.reroll_attack` reads the roll off `c.trigger`, and a row fired as an
    action is handed no event, so it would silently do nothing. One more
    strike at the same target, taken once and paid for the same way, is the
    same outcome by a different road.
    """
    if c.strike():
        c.damage("1d10", c.cha_mod)
        return
    if not c.may("pay for a second shot", who=c.me):
        return
    c.flat(c.level, on=c.me, from_attack=False)
    if c.strike():
        c.damage("1d10", c.cha_mod)


@power(
    "p12308",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p12308(c: Cast) -> None:
    """**Both halves of the clause are written now**, and this row carried
    no marker for either -- the note said the omission was deliberate
    ("left out of the primary and the secondary alike rather than
    approximated") and nothing declared it, so `blocked.py` could not see it
    and `todo.py` would never have reported it ready. That is the worse half
    of the two faults in this family. #728.

    `c.cannot_approach` bars a direction, which is what the old note
    correctly said `c.immovable` and `c.cannot_shift` cannot do. The primary
    clause prints **"willingly"** and the secondary does not; filtering the
    voluntary menu is right for both, since a push or a pull never goes
    through it.

    `When.EONT` on both, which is what the card clocks them on.
    """
    victim = c.target
    if c.strike():
        c.damage("2d10", c.cha_mod)
        c.cannot_approach(on=victim, until=When.EONT)
        if c.build("infernal"):
            c.resist(2 + c.int_mod, on=c.me, until=When.EONT)
        return
    c.flat(c.level, on=c.me, from_attack=False)
    pool = sorted(e for e in c.enemies() if e != victim and c.distance(e) <= 10)
    second = c.choose(pool, f"{c.ref}: who the backlash finds") if pool else None
    if second is not None and c.attack(c.cha_, FORT, on=second):
        c.half_damage("2d10", c.cha_mod, on=second)
        c.cannot_approach(on=second, until=When.EONT)


@power(
    "p12887",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=FORT),
)
def p12887(c: Cast) -> None:
    """Both branches roll the same line, so no `attack_alt` is declared.

    **The sorcerer-king rider is written now**, and the old note was wrong
    about where the charge lives. The build exists (`cf:warlock-f1s4` asks
    `c.build("sorcerer-king")` on its first line); the resource is **not**
    that row's encounter use. A trait's single use is spent by
    `turns.arm_traits` before round 1, so `c.expend_row` returned False
    here every time and this rider never fired. It is `c.spend_charge` on
    the key `features.warlock.FELL`, whose False **is** the printed "if you
    spend" clause. #529.

    **Decided before the attack roll**, which the pact boon's own card
    requires: "you must decide whether or not to spend your fell might when
    you choose to use a power, before you make any attack rolls or apply any
    of that power's effects." So the spend is settled above `c.strike()` and
    the extra damage is held until the hit, rather than asked for after the
    roll -- which would let a player buy it only on hits.

    The extra damage goes through `c.instead_of` because seven feats print
    "you can forgo the extra damage the augment would deal to instead
    <effect>". That is the clause they replace, and it has to be offered as
    one for `c.pre_empt` to reach it.
    """
    spent = c.may("spend the boon") and c.spend_charge(FELL)
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.NECROTIC)
        c.grants_advantage(to="team")
        if spent:
            c.instead_of(
                "fell_might_damage",
                lambda: c.damage("1d8", dtype=DamageType.NECROTIC),
            )


@power(
    "p12888",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p12888(c: Cast) -> None:
    """The bonus is the allies' and is spent only on this one creature, so it
    is a gated modifier held by each of them rather than anything on the
    target.

    **The sorcerer-king rider is written now**, the same way `p12887`
    writes its own in this very file: the build exists -- `cf:warlock-f1s4`
    asks `c.build("sorcerer-king")` on its first line -- and the resource
    is `c.spend_charge` on `FELL`, whose False **is** the printed "if you
    spend". #1341, #529.

    **Settled before the attack roll**, which the boon's card requires:
    "you must decide whether or not to spend your fell might when you
    choose to use a power, before you make any attack rolls or apply any
    of that power's effects". Asked afterwards it would let a player buy
    the rider only on hits.

    The rider changes two things, as printed: the bonus becomes +2, and it
    reaches damage rolls as well as attack rolls -- so the spent version
    lays a second modifier rather than a bigger one.
    """
    victim = c.target
    spent = (
        c.build("sorcerer-king")
        and c.may("spend the boon")
        and c.spend_charge(FELL)
    )
    if not c.strike() or victim is None:
        return
    c.damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
    for friend in c.allies():
        c.bonus(
            "attack",
            2 if spent else 1,
            on=friend,
            kind="power",
            until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )
        if spent:
            c.bonus(
                "damage",
                2,
                on=friend,
                kind="power",
                until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )


@power(
    "p12889",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p12889(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.grants_advantage(to="team", until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.NECROTIC)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
    c.pull(2)  # an Effect line: it lands either way


@power(
    "p13634",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p13634(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.FORCE)


@power(
    "p13635",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p13635(c: Cast) -> None:
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
            c.slowed(until=When.SAVE_ENDS)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.COLD)
    if c.last:
        # The Effect line lands whether the burst caught anybody or not,
        # which is why it hangs off the last call rather than the first hit.
        c.bonus(AC, 2, on=c.me, kind="power", until=When.ENCOUNTER)
        c.bonus(FORT, 2, on=c.me, kind="power", until=When.ENCOUNTER)


@power(
    "p13636",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p13636(c: Cast) -> None:
    if c.target is None:
        return
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p13637",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p13637(c: Cast) -> None:
    """"If you miss every target the power is not expended" is the refund
    nothing here can give back, so only the attack half is written."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    near = sorted(w for w in c.within(1, of=victim) if w != victim)
    mark = c.choose(near, f"{c.ref}: who it turns on") if near else None
    if mark is not None:
        c.grant_attack(victim, on=mark)


@power(
    "p13877",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.SHADOW],
    attack=Attack(CHA, vs=FORT),
)
def p13877(c: Cast) -> None:
    """The bite is an Effect line, so it is armed on a miss as well.

    "Your Dexterity modifier or Intelligence modifier" is the pact's
    secondary either way; Dexterity is the one written, and neither leg the
    class carries uses it, so this is the smaller of the two.
    """
    victim = c.target
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    bitten = [False]

    def stepped(ev: MoveEnd) -> None:
        if bitten[0] or ev.actor != victim or c.turn_of() != victim:
            return
        bitten[0] = True
        c.flat(2 + c.dex_mod, dtype=DamageType.COLD, on=victim)

    c.watch(MoveEnd, stepped, until=When.EOTNT)


@power(
    "p13878",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL),
)
def p13878(c: Cast) -> None:
    """The second way out -- a move action and an opposed check against you
    -- is not written: no check is rolled here and nothing spends a target's
    action to end an effect. The saving throw remains."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.FORCE)
        c.ongoing(5, DamageType.FORCE)


@power(
    "p13879",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE, Keyword.SHADOW],
    attack=Attack(CHA, vs=REF),
)
def p13879(c: Cast) -> None:
    """"Willingly enters" cannot be told from being shoved in: `ZoneEntered`
    says who arrived and not why, so everything that walks in is caught."""
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
            c.immobilized(until=When.SAVE_ENDS)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
            c.slowed(until=When.SAVE_ENDS)
    if not c.last:
        return
    area = c.area()
    if not area:
        return
    mire = c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def caught(ev: ZoneEntered) -> None:
        if ev.zone == mire:
            c.immobilized(on=ev.actor, until=When.EOTNT)

    c.watch(ZoneEntered, caught, until=When.ENCOUNTER)


@power(
    "p13902",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL),
)
def p13902(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(2)


@power(
    "p13904",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL),
)
def p13904(c: Cast) -> None:
    """**The gloom rider is written now** -- `c.build("gloom")`, and the
    leg was always there. #1346.

    "**If it doesn't move**" means under its own power. `MoveStart.kind_`
    is the field that tells the two apart -- `walk`, `shift` and
    `teleport` are the creature going somewhere, and `push`, `pull` and
    `slide` are it being taken -- and the distinction is load-bearing on
    this card in particular, because the row's own `c.push(2)` moves the
    target two squares a line earlier. Counting that as movement would
    make the rider fire never.

    **The settling watcher outlives the clock the clause names.** `EOTNT`
    ends at exactly the moment the damage is due, which would expire the
    hold before it could pay -- the trap `p13916` was written into and
    measured out of. So it waits on `ENCOUNTER` with `once=True` and is
    filtered to the target's own turn ending, which fires once and at the
    right time.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.push(2)
    if not c.build("gloom") or victim is None:
        return
    stirred = False

    def went(ev: MoveStart) -> None:
        nonlocal stirred
        if ev.actor == victim and ev.kind_ in ("walk", "shift", "teleport"):
            stirred = True

    def settle(ev: TurnEnd) -> None:
        if ev.actor == victim and not stirred:
            c.flat(
                2 + max(0, c.dex_mod),
                dtype=DamageType.PSYCHIC,
                on=victim,
            )

    c.watch(MoveStart, went, until=When.ENCOUNTER)
    c.watch(TurnEnd, settle, until=When.ENCOUNTER, once=True)


@power(
    "p13914",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.SHADOW, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p13914(c: Cast) -> None:
    """**The zone is written now** -- `c.build("star")`, and the leg was
    always there. The old note reasoned from that false premise to "no
    zone and no Zone keyword", while the header has carried
    `Keyword.ZONE` throughout. #1346.

    Laid **once per use**, not once per target: the body runs for every
    creature in the burst and a zone apiece would stack four copies of
    the same ground. The memo lives on the `Cast`, the unit `dsl.use`
    builds one of.

    And **not gated on a hit** -- "the burst also creates a zone" is
    about the burst, so a use that misses everything still leaves the
    ground difficult.
    """
    if c.target is not None and c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
        c.slowed()
    if not c.build("star") or getattr(c, "star_ground", False):
        return
    c.star_ground = True
    c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)


@power(
    "p13952",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.COLD,
        Keyword.NECROTIC,
        Keyword.CONJURATION, Keyword.SHADOW],
    attack=Attack(CHA, vs=REF),
)
def p13952(c: Cast) -> None:
    """The shadow stands next to the target and opens up whoever is beside it.

    Only the enemies standing there when it arrives are opened up: the
    printed line is a standing property of the square, and re-reading who is
    adjacent each round would need a hold on the conjuration that
    `c.conjure` does not hand back. The secondary attack printed under it is
    `p13952b`, gated on this shadow standing.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    room = sorted(
        sq
        for sq in spread(squares_of(c.world, victim), 1)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not room:
        return
    shade = c.conjure(at=room[0], label=c.ref, until=When.SUSTAIN, aura=1)
    for foe in c.enemies():
        if c.adjacent_to(shade, foe):
            c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p15902",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p15902(c: Cast) -> None:
    """**The star rider is written now** -- `c.build("star")`, and the leg
    was always there. #1346.

    Two clauses on one line of card, and they are two holds: the
    advantage is a relation and the slow is a condition, so there is
    nothing to put them on together. `to="team"` is "grants combat
    advantage" with nobody named -- the caster and allies -- which is the
    reading `p12887` in this same file already uses.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("2d6", c.con_mod, dtype=DamageType.PSYCHIC)
    if c.build("star") and victim is not None:
        c.grants_advantage(on=victim, to="team", until=When.EONT)
        c.slowed(on=victim, until=When.EONT)


@power(
    "p16256",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ELEMENTAL],
    attack=Attack(CHA, vs=REF),
)
def p16256(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    # "One creature within 5 squares of the target" -- anybody, including
    # the target itself, which is what the line allows.
    near = sorted(c.within(5, of=victim))
    splash = c.choose(near, f"{c.ref}: who the echo finds") if near else None
    if splash is not None:
        c.flat(c.con_mod, dtype=DamageType.PSYCHIC, on=splash)


@power(
    "p16261",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.ZONE, Keyword.ELEMENTAL],
    attack=Attack(CHA, vs=FORT),
)
def p16261(c: Cast) -> None:
    """The zone's bite is `c.burns`, which catches a creature entering as
    well as one starting its turn there; the printed line is "ends its
    turn", and that is the nearest the zone model comes.

    Sustaining rolls a d6 to grow or shrink the pool by a square. A zone's
    area is fixed once made, so sustaining simply keeps it.
    """
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.ACID)
            c.ongoing(5, DamageType.ACID)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.ACID)
    if not c.last:
        return
    area = c.area()
    if area:
        pool = c.zone(area, label=c.ref, until=When.SUSTAIN, difficult=True)
        c.burns(pool, 5, DamageType.ACID)


@power(
    "p16350",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON, Keyword.SHADOW],
    attack=Attack(CHA, vs=REF),
)
def p16350(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.damage("1d6", c.cha_mod)
        if c.build("fey"):
            c.flat(c.int_mod, dtype=DamageType.POISON)
