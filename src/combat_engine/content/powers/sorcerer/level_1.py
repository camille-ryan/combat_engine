"""Sorcerer, level 1: the first half of the attack rows.

Three things recur across the whole class and are settled once here.

**The forks are not modelled.** `chargen` derives one build, `standard`, so
a rider printed under Dragon Magic, Wild Magic, Storm Magic, Cosmic Magic or
Chaos Sorcerer has no leg to ask for. Where such a rider is the *whole* of a
row the row is left out and recorded; where it is one clause of a row that
works without it, the rest is written and the dropped clause is named in a
comment. Neither is an approximation: the base line is what the card prints
for everybody.

**One damage type per packet.** `DamageType` carries a single type, so a
line reading "cold and lightning damage" is dealt as the first printed type
and the second rides in the keywords, which is what every level below
settled on.

**A d6 table is rolled, not chosen.** `c.roll("1d6")` indexes a tuple of
types. The Cosmic and Chaos riders that let the sorcerer pick instead of
rolling are exactly the dropped clauses above.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    MOVE,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    get,
    power,
)
from combat_engine.engine.query import creatures, distance_between

from . import wild_even
from .ground import beside
from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The at-will d6 table, in printed order.
_SIX_TYPES = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.RADIANT,
    DamageType.THUNDER,
)


@power(
    "p10319",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p10319(c: Cast) -> None:
    """"You can use this power as a ranged basic attack" is a property of the
    creature -- `Powers.basic` -- and not of the row, so there is no header
    field to declare it in. Written down and no more.
    """
    kind = _SIX_TYPES[c.roll("1d6") - 1]
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=kind)
        c.resist(5, kind, on=c.me, until=When.EONT)


@power(
    "p1163",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1163(c: Cast) -> None:
    """One roll settles both the damage type and the rider, and the Miss
    line uses the same table -- so it is rolled before the attack and read
    twice rather than rolled twice."""
    face = c.roll("1d6")
    kind = (
        DamageType.RADIANT,
        DamageType.FIRE,
        DamageType.POISON,
        DamageType.LIGHTNING,
        DamageType.COLD,
        DamageType.PSYCHIC,
    )[face - 1]
    victim = c.target

    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=kind)
    else:
        c.damage("1d10", dtype=kind)

    if face == 1:
        c.dazed(until=When.SAVE_ENDS)
    elif face == 2:
        for near in c.within(1, of=victim, side="any"):
            if near != victim:
                c.flat(c.dex_mod, dtype=DamageType.FIRE, on=near, from_attack=False)
    elif face == 3:
        c.ongoing(5, DamageType.POISON)
    elif face == 4:
        c.slide(c.dex_mod)
    elif face == 5:
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.penalty(AC, 2, until=When.SAVE_ENDS)


@power(
    "p12465",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=FORT),
)
def p12465(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p12466",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p12466(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
        c.penalty(AC, 2)


@power(
    "p12467",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.ACID],
    attack=Attack(CHA, vs=REF),
    reads_parity=True,
)
def p12467(c: Cast) -> None:
    """The damage type is read off the parity of the roll just made -- and it
    decides the Miss line too, so the roll is kept rather than the hit alone.

    **`reads_parity=True`, and this is the one row where the clause is
    unconditional.** The other eight sorcerer rows printing a parity clause
    gate it on the Wild Magic build or on an active familiar; this one
    simply reads the roll, so it qualifies for `p5845` on every character
    that holds it. `#1302`.

    The claim that *"nothing in the engine is a familiar"* below is wrong
    and is corrected rather than deleted: `query.familiar_active` and this
    package's `has_familiar` both exist, and `p12470` beside it is written
    against them now. What this row's Active Familiar rider waits on is
    narrower -- 5 extra damage next to the familiar -- and it is still
    unwritten here.

    The Active Familiar rider -- 5 extra damage next to the familiar -- is
    dropped: nothing in the engine is a familiar.
    """
    shot = c.strike()
    kind = DamageType.ACID if shot.parity == "even" else DamageType.RADIANT
    if shot:
        c.damage("2d10", c.cha_mod, dtype=kind)
        c.push(c.dex_mod)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=kind)


@power(
    "p13425",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13425(c: Cast) -> None:
    """The riposte is the whole Spell Source clause -- its size *and* its
    damage type both come off the fork -- and the fork is not modelled, so
    it is dropped and the weapon damage stands. "You can use this power in
    place of a melee basic attack" is a property of the creature rather
    than a header field; see p10319.
    """
    if c.strike():
        c.damage(c.w(), c.cha_mod)


@power(
    "p13426",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13426(c: Cast) -> None:
    """The Effect line runs whatever the primary did, so the teleport and
    the secondary are outside the branch; only the advantage depends on the
    primary having landed."""
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(), c.cha_mod)

    where = beside(c, c.target)
    if where is not None:
        c.teleport(20, to=where)
    if c.strike(advantage=True if landed else None):
        c.slowed()
        c.weakened()


@power(
    "p3005",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p3005(c: Cast) -> None:
    """The Storm Magic clause -- moving the Storm Power bonus from one
    packet to the other -- is dropped with the fork."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    pool = sorted(f for f in c.enemies() if f != victim and c.distance(f) <= 10)
    second = c.choose(pool, f"{c.ref}: who the arc jumps to") if pool else None
    if second is not None:
        c.flat(c.dex_mod, dtype=DamageType.LIGHTNING, on=second, from_attack=False)


@power(
    "p3009",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p3009(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod)
        c.prone()


@power(
    "p3033",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p3033(c: Cast) -> None:
    """**Both branches are written now.** The old note dropped them on
    "concealment is not modelled", and the whole clause turned out to be
    three facilities this tree already had. #1341.

    The sentence runs from the **target's** eyes -- it "treats each
    creature more than 5 squares away as having concealment" -- so the
    concealment is laid on everyone else and gated on the target being the
    one looking. `c.conceal(when=)` is handed the attack context, which is
    what makes that sayable; concealment against everybody would be the
    much stronger thing the old note rightly refused.

    **The distance is read live, not at cast time.** A creature that walks
    within 5 squares stops being hard to see, which is what the printed
    line means and what a snapshot of the board would get wrong.

    The Hit branch is an *aftereffect*: the card says "when the blinded
    condition ends, the target then treats...", so it hangs off the
    blindness with `c.aftereffect` rather than running beside it. The Miss
    branch has no blindness to wait for and lands at once.
    """
    victim = c.target

    def blinkered(until: When) -> None:
        """Everyone more than 5 squares from the target is concealed from it."""
        if victim is None:
            return
        for other in creatures(c.world):
            if other == victim:
                continue
            c.conceal(
                on=other,
                until=until,
                when=lambda ctx, o=other: (
                    ctx.get("attacker") == victim
                    and distance_between(c.world, victim, o) > 5
                ),
            )

    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.aftereffect(c.blinded(), lambda: blinkered(When.SAVE_ENDS))
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
        blinkered(When.EONT)


@power(
    "p3034",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p3034(c: Cast) -> None:
    """A zone plus a `TurnStart` watch rather than `c.hazard`: the printed
    bite is only for a creature *starting* its turn inside, and a hazard
    also bites on entry.

    **"As a move action, you can move the zone 3 squares" is written now,
    and nothing had to be built for it.** The old note here said `c.zone`
    "takes no speed and nothing offers moving one", and both halves were
    already false: `c.move_zone` translates a zone's squares, `"move_zone"`
    is in `actions.GRANTABLE`, the action menu has read it since, and
    several monster rows grant it exactly this way.

    `until=ENCOUNTER` rather than the zone's own `EONT` because the zone is
    Sustain Minor and may stand for the whole fight -- and the menu gates
    the entry on a live, non-aura zone of this creature's, so the grant
    offers nothing once the wind is gone. #1342.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)
        c.slide(c.dex_mod)

    if not c.first:
        return
    area = c.area()
    if not area:
        return
    wind = c.zone(area, label=c.ref, until=When.EONT)
    c.grant_action("move_zone", MOVE, squares_=3, on=c.me,
                   until=When.ENCOUNTER)
    bite = c.cha_mod

    def gust(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(wind):
            c.flat(bite, dtype=DamageType.THUNDER, on=ev.actor)

    c.watch(TurnStart, gust, until=When.EONT, on=c.me, label=f"{c.ref} wind")


@power(
    "p3035",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p3035(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
        c.ongoing(5, DamageType.COLD)
    else:
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.COLD)


@power(
    "p3162",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
    reads_parity=True,
)
def p3162(c: Cast) -> None:
    """The Wild Magic clause lands now: a slide by Dexterity **instead of**
    the push, on an even roll.

    It was dropped "with the fork", on the premise that the build was not
    dealt. It is -- `chargen.BUILDS["sorcerer"]`'s first leg is `wild`, and
    the missing thing was the class-feature row rather than the build. See
    `wild_even`. `#1303`.

    "Instead of pushing it" is an either/or and not an extra square, so the
    push is in the else rather than both running."""
    shot = c.strike()
    if shot:
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        if wild_even(c, shot):
            c.slide(c.dex_mod)
        else:
            c.push(1)


@power(
    "p3171",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p3171(c: Cast) -> None:
    """**The fork IS modelled, and "dropped with the fork" was false.**
    `chargen.BUILDS["sorcerer"]` carries all four sources -- `dragon`,
    `storm`, `cosmic`, `wild` -- beside the four elemental legs, and
    content asks for them at twelve sites already (`souls.py` dispatches
    on `dragon` and `wild`, `feats/sorcerer_b.py` on `wild`). The
    printed refs map to legs off their own spec text: `f0s0` cosmic,
    `f0s1` dragon, `f0s2` storm, `f0s3` wild. #1341, #1346.

    So the Dragon Magic clause is written: `c.build("dragon")` for the
    leg and `c.bloodied()` for the target's state. **It replaces the
    distance rather than adding to it** -- "3 squares **instead of** 1"
    -- so it is one `c.push` with a chosen number and not a second push
    on top of the first.

    `c.bloodied()` with no argument asks about the **target**, which is
    what this card means, and the burst re-asks it per enemy -- so a
    bloodied one is pushed 3 while the one beside it is pushed 1.
    """
    if c.strike():
        c.damage("1d10", c.cha_mod)
        far = 3 if (c.build("dragon") and c.bloodied()) else 1
        c.push(far)


@power(
    "p3172",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.FEAR],
    attack=Attack(CHA, vs=FORT),
)
def p3172(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
        c.penalty("attack", 2)


@power(
    "p3701",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3701(c: Cast) -> None:
    """**The fork IS modelled, and "dropped with the fork" was false.**
    `chargen.BUILDS["sorcerer"]` carries all four sources -- `dragon`,
    `storm`, `cosmic`, `wild` -- beside the four elemental legs, and
    content asks for them at twelve sites already (`souls.py` dispatches
    on `dragon` and `wild`, `feats/sorcerer_b.py` on `wild`). The
    printed refs map to legs off their own spec text: `f0s0` cosmic,
    `f0s1` dragon, `f0s2` storm, `f0s3` wild. #1341, #1346.

    So the Dragon Magic clause is written. Three words in it carry the
    whole shape:

    * "**the next** enemy" -- one payout, spent by the first melee hit
      that qualifies, which is the `paid` latch rather than `once=` on a
      hold: the hold here is a watcher, and `once=` would spend it on
      any `Hit` at all;
    * "**that hits you**" -- filtered on `ev.target == me`, so an ally
      being hit does not spend it;
    * "with a **melee** attack" -- read off the swinging row's own reach
      kind, the same way `p12891` reads it.

    Laid once per use and not once per creature in the blast: the body
    runs per target and the clause is the caster's, so the memo lives on
    the `Cast`.
    """
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.FIRE)
    if not c.build("dragon") or getattr(c, "dragon_scorch", False):
        return
    c.dragon_scorch = True
    paid = [False]
    me = c.me

    def scorch(ev: Hit) -> None:
        if paid[0] or ev.target != me:
            return
        swung = get(ev.power)
        if swung is None or swung.reach.kind != "melee":
            return
        paid[0] = True
        c.flat(
            max(0, c.str_mod),
            dtype=DamageType.FIRE,
            on=ev.attacker,
            from_attack=False,
        )

    c.watch(Hit, scorch, until=When.EONT)


@power(
    "p3705",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
    basic="ranged",
)
def p3705(c: Cast) -> None:
    """"Can be used as a ranged basic attack" -- see p10319."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.COLD)
        c.push(1)


@power(
    "p3716",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=REF),
)
def p3716(c: Cast) -> None:
    """**"The target can't gain combat advantage against any creature" is
    written now.** The old note said `c.cannot_be_flanked` "closes one
    route to it and nothing denies the advantage itself", and that was
    already false: `c.no_advantage(gains=True)` denies the gaining rather
    than the granting, which is this card's direction, and
    `battlemind/level_7.py` has been calling it that way.

    `gains=True` is the whole point. The default denies *granting* -- "you
    do not grant combat advantage to any of your enemies" -- which is the
    opposite sentence and would have made this row help the creature it is
    aimed at. #1341.

    The Dragon Magic concealment goes with the fork.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.ACID)
        c.no_advantage(gains=True, on=c.target, until=When.EONT)
