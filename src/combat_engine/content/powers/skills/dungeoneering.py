"""Skill powers for one skill: the ten that print at levels 2, 6 and 10.

`cls` is the skill rather than a class -- see this package's `__init__`.

Three things run through the batch.

**One skill standing in for another is an exact substitution, not an
approximation.** `skills.modifier` is the ability modifier plus half level
plus training plus whatever stands on `skill:<name>`, so the difference
between two creatures' `c.passive` readings is the whole of what swapping
the skills changes, and the die is left alone. `f2913` is the precedent.

**"Underground" cannot be said.** `World.terrain` is initialised empty and
nothing in `src/` ever writes a word into it, so every `c.terrain(...)` gate
in the tree is False in every fight -- `f2718` records the measurement. Two
rows print it as a Requirement or inside a Trigger and carry
`story.terrain_words` for it.

**A printed "+N to all defences against the triggering attack" is not a
`c.bonus`.** The sum was taken when the die landed, so the two interrupt
rows raise `result.target_defence` and re-judge through `c.settle_attack`,
which is `p12245`'s shape and the door #868 built for it.
"""

from __future__ import annotations

from combat_engine.dc import dc
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    CloseBurst,
    Mods,
    Target,
    Trigger,
    When,
    World,
    both,
    by_melee,
    hits_me,
    my_check,
    power,
    query,
)
from combat_engine.engine.events import Hit, SkillCheck
from combat_engine.engine.grid import spread

#: The five skills `p16490`'s Trigger names, lowercased the way
#: `SkillCheck.skill` carries them.
_GUIDED = frozenset({
    "acrobatics", "athletics", "dungeoneering", "nature", "perception",
})


def _underground(world: World, eid: int) -> bool:
    """Is the fight being had underground?

    **The half of two printed clauses that `story.terrain_words` was
    marked for, and the marker was stale.** The pipeline it named is
    complete: `story.run.ground` does `world.terrain |= set(scene.terrain)`,
    the importer constrains a module's `terrain` list to
    `cast.TERRAIN_WORDS`, and `"underground"` is one of its eighteen words.
    So the gate is live in play rather than permanently false.

    `query.terrain` is the one reader -- a printed **Requirement** is a
    `requires=(world, eid)` gate with no `Cast` to ask, which is why that
    function exists and `c.terrain` delegates to it.

    `eid` is unused and kept so this reads as a `requires` predicate like
    its neighbour: the question is about the room, not about who is asking.
    """
    return query.terrain(world, "underground")


def _sheltered(world: World, eid: int) -> bool:
    """Any cover or concealment from any enemy, which is the degree
    `p11544`'s Requirement names.

    Looser than `actions._hiding`, which gates the ordinary hide action on
    **superior** cover or total concealment -- and that laxity is what the
    card is for, so the test belongs here rather than being borrowed.
    """
    if query.concealment_of(world, eid):
        return True
    return any(
        query.cover_between(world, foe, eid)
        for foe in query.enemies(world, eid)
    )


def _carries_light(world: World, eid: int) -> bool:
    """"You must be carrying a light source."

    A carried light is a `light_radius` modifier whatever laid it -- `c.light`
    writes one and `i1014p1` reads the same key to put the lights out -- so
    the Requirement is whether the sum is anything at all.
    """
    mods = world.get(eid, Mods)
    return bool(mods and mods.total("light_radius", {}))


def _beside_blocking(world: World, me: int, ev: object) -> bool:
    """Is this creature standing against blocking terrain?

    `Grid.blocking` is the map's own walls, which `terrain.dress` lays. The
    same read `items/consumable._against_something_big` makes, without the
    furniture half -- the card names terrain and not objects.
    """
    mine = query.squares(world, me)
    return any(sq in world.grid.blocking for sq in spread(mine, 1) - mine)


def _trap_attacks_me(world: World, me: int, ev: object) -> bool:
    """A trap or a hazard swung at this creature. `c.is_trap`'s reader."""
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and query.is_trap(world, attacker)
    )


def _ally_dislikes_a_check(world: World, me: int, ev: object) -> bool:
    """One of the five named checks, made by somebody else on my side."""
    who = getattr(ev, "actor", None)
    return (
        who is not None
        and who != me
        and who in query.allies(world, me)
        and getattr(ev, "skill", "") in _GUIDED
    )


# -- level 2 ----------------------------------------------------------------


@power(
    "p11544",
    level=2,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=lambda world, eid: _sheltered(world, eid) and _underground(world, eid),
    requires_text="you must have cover or concealment underground",
)
def p11544(c: Cast) -> None:
    """The substitution is the difference between the two modifiers, laid on
    the key `_stealth_hide` then rolls against -- so the hide is the engine's
    own, opposed by the best passive Perception on the board, with one
    skill's bonus in place of the other's.

    `once=True` because the clause is about this one check: the hide below
    spends it immediately and nothing later picks it up.

    **Both halves of the Requirement are asked now.** The underground half
    was the dropped clause and its marker -- `story.terrain_words` -- was
    stale: `query.terrain` reads `World.terrain`, which `story.run.ground`
    fills from the scene, and `"underground"` is one of
    `cast.TERRAIN_WORDS`' eighteen words. See `_underground` above.
    """
    edge = c.passive("dungeoneering") - c.passive("stealth")
    if edge:
        c.bonus("skill:stealth", edge, on=c.me, until=When.EOT, once=True)
    c.hide(check=True)


@power(
    "p16482",
    level=2,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_carries_light,
    requires_text="you must be carrying a light source",
)
def p16482(c: Cast) -> None:
    """"The squares illuminated by the light source you are carrying" is the
    carried radius, so this is an aura of exactly that size rather than a
    number of its own -- a second source or a feat that widens the light
    widens the penalty with it.

    `c.grants_in` with a negative value is a penalty: it hands the number to
    `c.bonus`, which is what `c.penalty` does, and the row's own ref is the
    label that stops two of them stacking.
    """
    radius = c.total("light_radius")
    if not radius:
        return
    lit = c.aura(radius, until=When.EONT)
    c.grants_in(lit, "attack", -2, side="enemy", kind="untyped")


@power(
    "p9311",
    level=2,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target(side="enemy", count=1, kinds=frozenset({"aberrant"})),
)
def p9311(c: Cast) -> None:
    """A monster knowledge check really is rollable from here: `c.check`
    takes `against=`, which fills `SkillCheck.target`, so the check is about
    the creature rather than about a fact.

    **The band is a judgement call.** The printed monster knowledge rule
    keys the DC to how commonly known the creature is, and the compendium
    gives no rarity column -- so this is the moderate DC for the target's
    own level, which is the common case. If a rarity ever lands, this is the
    line to change.

    **"One ally who can hear you" is written, and this paragraph used to
    say it was dropped** -- while the body three lines below it already
    called `c.can_hear`, and the comment beside that call already said
    "`query.can_hear` is the reader; it landed with this row and three
    others". So the admission and its refutation sat in the same
    docstring, and `blocked.py --prose` counted the row as unfinished on
    the strength of the stale half.

    The narrowing is real and is the whole clause: the caster is always in
    the pool, because a card reading "you or one ally who can hear you"
    does not ask you to hear yourself, and `c.can_hear` filters the rest.
    """
    foe = c.target
    if foe is None:
        return
    if not c.check("dungeoneering", dc(c.level_of(foe)), against=foe):
        return
    # "You or one ally who can hear you" -- the caster is always in the
    # pool, and `c.can_hear` narrows the rest. `query.can_hear` is the
    # reader; it landed with this row and three others.
    pool = sorted([c.me, *(a for a in c.allies() if c.can_hear(a))])
    who = c.choose(pool, f"{c.ref}: who takes the opening")
    if who is None:
        return
    c.bonus(
        "attack", 4, on=who, until=When.EONT, kind="power", once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


# -- level 6 ----------------------------------------------------------------


@power(
    "p11545",
    level=6,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would make a Perception check underground",
    on=Trigger(
        SkillCheck,
        both(my_check("perception"),
             lambda world, me, ev: _underground(world, me)),
        "you would make a Perception check underground",
    ),
)
def p11545(c: Cast) -> None:
    """The amount is the gap between the two modifiers, so the die stands
    and the roll ends up where the other skill would have put it -- whichever
    window the free action is heard in, because `skills.check` totals the
    modifiers inside its resolve callback and rebuilds the result afterwards.

    **`c.boost_roll(kind="check")` rather than `c.boost_check`**, which it
    calls. The difference is that it then announces `Boosted`, and that
    announcement is the only trace a verb changing a number already on the
    table leaves -- `audit.py`'s own note names `c.boost_check` as a verb
    whose row "fired its 48 attempts and reported SILENT while working
    perfectly". Measured: this row did exactly that until the call moved.

    The underground half of the Trigger is the dropped clause.
    """
    edge = c.passive("dungeoneering") - c.passive("perception")
    if edge:
        c.boost_roll(edge, kind="check")


@power(
    "p16490",
    level=6,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally makes one of five named skill checks and dislikes the result",
    on=Trigger(
        SkillCheck,
        _ally_dislikes_a_check,
        "an ally makes an Acrobatics, Athletics, Dungeoneering, Nature or "
        "Perception check",
    ),
)
def p16490(c: Cast) -> None:
    """"The ally can use the result of your check in place of his or her
    own result" is both halves of a result: the die and the modifier.

    So the roll is made here, `c.replace_roll` moves the ally's die to the
    face this one came up with, and the boost pays the difference between
    the two modifiers. The pair is exact in either window -- before the
    ally's own modifier is added, or after it -- because the boost writes a
    delta and `skills.check` adds the ally's modifier exactly once.

    `c.boost_roll(kind="check")` rather than `c.boost_check`, for the reason
    `p11545` records: the second one changes the number and announces
    nothing.
    """
    ev = c.trigger
    if not isinstance(ev, SkillCheck):
        return
    mine = c.check("dungeoneering")
    c.replace_roll(mine.natural, kind="check", ev=ev)
    c.boost_roll(
        c.passive("dungeoneering") - c.passive(ev.skill, of=ev.actor),
        kind="check",
    )


@power(
    "p9312",
    level=6,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p9312(c: Cast) -> None:
    """Blindsight is a sense the board keeps, and not truesight: one makes
    light irrelevant, the other sees through concealment and invisibility."""
    c.blindsight(10, on=c.me, until=When.EONT)


# -- level 10 ---------------------------------------------------------------


@power(
    "p13216",
    level=10,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with a melee attack while you are beside blocking terrain",
    on=Trigger(
        Hit,
        both(hits_me, by_melee, _beside_blocking),
        "an enemy hits you with a melee attack beside blocking terrain",
    ),
)
def p13216(c: Cast) -> None:
    """"A bonus to all defences against the attack" is one defence in
    practice -- the one that was rolled against -- so raising
    `result.target_defence` and re-judging says the whole printed line, and
    a `c.bonus` cannot: the comparison was already made.

    `c.settle_attack` rather than writing `hit` and `critical` by hand,
    which is what un-crits a blow the bonus has pushed below the defence.
    """
    result = getattr(c.trigger, "result", None)
    if result is None:
        return
    result.target_defence += c.dex_mod
    c.settle_attack()


@power(
    "p16496",
    level=10,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16496(c: Cast) -> None:
    """Personal, and the creature is chosen in the body rather than
    targeted: the printed line is "choose one aberrant creature that you can
    see within 5 squares", which is not the power's target.

    Ignoring resistance is a property of the attacker, so `c.ignore_resistance`
    sits on the caster and the gate narrows it to this one creature --
    `target` is a key the damage context really does carry. `amount=None` is
    the blanket form the card prints.

    The band is the same judgement call as `p9311`: moderate for the
    creature's level, because no rarity column exists.

    **It reports SILENT and the reason is the board, not the row.**
    `audit.board` poses beasts and one undead and no aberrant creature at
    all, and the creature is chosen in the body rather than targeted -- so
    `seen` is empty on every attempt. Driven by hand with one foe given the
    origin word it lays `p16496 ignores all resist`, and lays nothing
    without it.
    """
    seen = [foe for foe in c.within(5, side="any") if c.is_kind("aberrant", on=foe)]
    if not seen:
        return
    foe = c.choose(sorted(seen), f"{c.ref}: which creature")
    if foe is None:
        return
    if not c.check("dungeoneering", dc(c.level_of(foe)), against=foe):
        return
    c.ignore_resistance(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p16503",
    level=10,
    cls="dungeoneering",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16503(c: Cast) -> None:
    """The sense runs on the printed clock and the sustain re-lays it, which
    is what "the tremorsense persists until the end of your next turn"
    means -- a sense held `until=When.SUSTAIN` would outlast a turn nobody
    spent a minor action on.

    So the hold is an empty `c.effect` carrying the sustain cost, and
    `c.on_sustain` is the payout half; without the second the sustain line
    goes nowhere.
    """

    def sense() -> None:
        c.tremorsense(5, on=c.me, until=When.EONT)

    sense()
    hold = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    c.on_sustain(hold, sense)


@power(
    "p9313",
    level=10,
    cls="dungeoneering",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="a trap or a hazard makes a melee or a ranged attack roll against you",
    on=Trigger(
        Hit, _trap_attacks_me, "a trap or a hazard attacks you",
    ),
)
def p9313(c: Cast) -> None:
    """The defence half plays, by `p13216`'s route: the bonus is against the
    triggering attack, so it is a lift of `result.target_defence` and a
    re-judgement rather than a modifier.

    **Declared on `Hit` and not on the attack roll**, which narrows the
    printed Trigger to the half where the bonus can change anything -- on an
    attack already missing there is nothing for +4 to do.

    **The repeat is written now, and declaring on `Hit` is what makes it
    reachable rather than what blocked it.** The printed clause is *"if the
    attack misses you"*, and after `c.settle_attack` the +4 may have made it
    a miss -- which is exactly the case this row creates. An attack that was
    already missing never needed this card.

    `c.spring_trap` is the verb, and the old note's objection to
    `c.use_power` still stands and is why: borrowing the trap's row would
    make the swing **this character's**, so a rider on their attacks would
    pay out and a creature's defences against *traps* would not apply. The
    attack has to be the trap's, which is what `traps.fire` does.

    The trap chooses nobody. The card names the geometry -- an enemy
    adjacent to you -- and leaves which one to the table, so the first by id
    is taken: aiming it is not an AI decision and `c.choose` would ask a
    player to point somebody else's trap.
    """
    result = getattr(c.trigger, "result", None)
    if result is None:
        return
    result.target_defence += 4
    c.settle_attack()
    # **"If the attack misses you"** -- so the repeat is owed only when the
    # +4 above has actually turned the blow aside, which is why it is read
    # after `c.settle_attack` rather than off the trigger. A row declared on
    # `Hit` sees a hit; whether it is still one is this line's question.
    if result.hit:
        return
    springer = getattr(c.trigger, "attacker", None)
    if springer is None:
        return
    # "Against an enemy adjacent to you", and the trap chooses nobody: the
    # printed line names the geometry and leaves which one to the table, so
    # the first by id is taken rather than a scored pick -- this is not an
    # AI decision and `c.choose` would ask a player to aim a trap.
    beside = [foe for foe in c.enemies() if c.adjacent(foe)]
    if not beside:
        return
    c.spring_trap(springer, on=beside[0])
