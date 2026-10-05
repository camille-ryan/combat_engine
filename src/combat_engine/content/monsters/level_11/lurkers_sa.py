"""Monster abilities, level 11: the stat-block entries of the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("1d8", 4)` -- and the engine takes the level back out
of the attack and rescales the damage if a fight is being played on another
edition's maths.

The conventions of `lurkers.py` beside this file are kept, and its helpers are
imported rather than copied: a row filed under an action heading that is
plainly a trait is declared `ActionType.NONE`, and a stat block printing no
range at all means melee 1.

Nine things this file had to settle.

**Three of these stat blocks are the same card three times**, and two more are
a second pair. m1588, m2247 and m43 print the same reach-2 at-will, the same
blast and the same darkness; m2252 and m290 print the same nine lines. The rows
are hand-written per block rather than routed into each other, because a ref
belongs to one creature and `use` would lend a row the other does not have --
but the shapes the pairs share are factored into the helpers below, which is
where the darkness and the acid pool live.

**"If the target cannot see it" has to be asked before the roll.** As
`lurkers.py` found for m2920a3, `resolve.attack` clears the hiding for whoever
swung, so m4770a0 and m4770a2 read `query.unseen_by` at the top of the body --
the last moment the answer is still the one the card means -- and keep it.

**A 6-square shift through enemies is `c.overrun`, not `c.phasing`.**
`c.phasing` walks through walls and floors as well, which is wider than
m3846a2's printed line, and nothing scopes it down. `c.overrun` is the verb
that passes through creatures and says which ones, which is what the row needs
to immobilize them; the difference left over is that it walks where the card
shifts, so it provokes. That is the marked clause.

**m2346a1's card prints no defence at all** -- "+14 vs ;" is the whole of the
attack line in the compendium -- and the row is nothing but that attack, so
there is no half to play. `etl.monster.attack_defence()` is the symbol
twenty-four other rows already carry for the same loss, and m1135a1 settled
that a lost defence is named and not guessed.

**A statue and a thicket are the same shape as m290a7**, which `lurkers.py`
settled: `Condition.STUNNED` would make the printed way *out* of the form
unreachable, because `actions.legal` offers a creature that cannot act nothing
but the end of its turn. So the attacks are taken away instead and handed back
when the form ends.

**m5333a0's fruit are handed out as they come within reach.** `c.give` is the
one-shot a creature spends on its own clock, which is exactly what a creature
drinking something that dominates it is; the pool is rolled once and counted
down, and `AdjacencyGained` is the moment somebody could pick one. What is
missing is the fruit as objects standing on the board for anybody to take,
which is `c.place_scenery()`, the symbol m4620a2 carries for the same absence.

**"+4 power bonus against ranged and area attacks"** is a gate on the range
kind of the row that swung, which the attack context does not carry as a word
-- `ctx["ranged"]` is true for a ranged attack and false for an area one. So
`_ranged_or_area` reads the kind off the power named in the context, which is
the same question `_reach_kind` asks of an event.

**m2545a1's +4 prints no duration** and m2346a3's combat advantage prints none
either. The end of the next turn and the end of this one are written, which is
what the rest of each sentence is already on.

**"-5 penalty to saving throws against this power"** is a `save` modifier
gated on `ctx["label"]`, which `Effects.roll_saves` fills with the effect's own
label -- so "against this power" is the ref and nothing else. Bounded by the
zone with `c.grants_in`, because the printed line is about standing in it.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_04.skirmishers import _has_advantage
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_09.lurkers_sa import _dominated_by_me
from combat_engine.content.monsters.level_11.controllers import (
    _held_and_softened,
)
from combat_engine.content.monsters.level_11.lurkers import (
    EVERY_DEFENCE,
    _breathe_again,
    _extra_against_the_unready,
    _frightful,
)
from combat_engine.content.monsters.level_11.skirmishers import _release_earlier
from combat_engine.content.powers.fighter.holds import release
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AdjacencyGained,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Position,
    Ranged,
    Relation,
    RelationCleared,
    RelationSet,
    SavingThrow,
    Size,
    Target,
    TurnStart,
    UpTo,
    Usage,
    When,
    ZoneEntered,
    by_melee,
    by_ranged,
    either,
    power,
    use,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerUsed, ZoneExited
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, has_combat_advantage, unseen_by
from combat_engine.engine.triggers import Trigger, about_me, both, targets_me, would_hit_me
from combat_engine.engine.zones import Zone

#: What "ranged and area attacks" comes to as range kinds. A close burst is
#: neither, which is the whole reason the pair is written out.
_RANGED_OR_AREA = ("ranged", "area_burst")


def _ranged_or_area(ctx: dict[str, Any]) -> bool:
    """Was the swing being defended against a ranged or an area attack?

    The attack context carries `ranged` as a flag and nothing for an area, so
    the kind is read off the row named in the context -- the same question
    `_reach_kind` asks of an event, asked of a dict instead.
    """
    p = get(str(ctx.get("power") or ""))
    if p is None:
        return bool(ctx.get("ranged"))
    return p.reach_of(int(ctx.get("branch") or 0)).kind in _RANGED_OR_AREA


def _acid_pool(c: Cast) -> None:
    """The dragons' blast: "ongoing 5 acid damage and a -4 penalty to AC (save
    ends both)".

    One effect carrying both, because applied separately the victim rolls
    twice and can shake off half of a thing the card prints as one.
    `_held_and_softened` takes a penalty to *all* defences; this one is to AC
    alone, so the modifier is built here.
    """
    victim = c.target
    if victim is None:
        return
    sagging = Mod(what=AC.value, value=-4, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=(5, DamageType.ACID),
        mods=[(victim, sagging)],
    )


def _darkness(c: Cast) -> None:
    """The dragons' cloud: nobody sees through it and nobody inside sees at all.

    `blocks_sight` is what `cover_between` reads and it applies to everybody;
    there is no way to exempt one creature from it, so the dragon's own sight
    through its own cloud is noted rather than invented -- the arrangement
    m43a6 settled on.

    The blinding is held per occupant and diffed by the two events that say
    who is standing in it, because a zone's own fields make squares rough or
    dark and carry no conditions. Ending the zone emits a `ZoneExited` for
    everybody inside, which is what takes the holds off.
    """
    me = c.me
    area = c.area()
    if not area:
        return
    dark = c.zone(
        area, label=c.ref, until=When.SUSTAIN, blocks_sight=True, sustain=MINOR
    )
    held: dict[int, Effect] = {}

    def swallow(who: int) -> None:
        if who == me or who in held:
            return
        blinded = c.blinded(until=When.ENCOUNTER, on=who)
        if blinded is not None:
            held[who] = blinded

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == dark:
            swallow(ev.actor)

    def left(ev: ZoneExited) -> None:
        blinded = held.pop(ev.actor, None) if ev.zone == dark else None
        if blinded is not None:
            c.world.effects.end(blinded, "out of the dark")

    watches = (
        c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in"),
        c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out"),
    )
    zone = c.world.get(dark, Zone)
    if zone is not None and zone.effect is not None:
        for watch in watches:
            zone.effect.on_end.append(
                lambda w=watch: c.world.effects.end(w, "the dark is gone")
            )
    for actor in c.world.zones.occupants(dark):
        swallow(actor)
    c.note(f"{c.ref}: it sees through its own darkness")


def _advantage_on_arrival(c: Cast, squares: int) -> None:
    """"Moves, and gains combat advantage against anything it ends beside."

    The +4 against openings goes up *before* the step, because the openings
    happen during it, and it is gated on `ctx["opportunity"]` rather than laid
    flat. The printed line gives the advantage no duration at all; the end of
    this turn is what the rest of the sentence is on -- it is there to pay for
    the attack that follows the move.
    """
    c.bonus(
        AC, 4, on=c.me, until=When.EOT,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(squares)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.grants_advantage(on=foe, until=When.EOT)


def _stone_form(c: Cast, resist: int, regeneration: int, *, blind: bool) -> Effect:
    """A shape it cannot fight in, and the way back out of it.

    `Condition.STUNNED` is the obvious way to write "can take no actions other
    than reverting" and is the wrong one: `actions.legal` offers a creature
    that cannot act nothing but the end of its turn, so the printed minor
    action would be unreachable. The attacks are taken away instead and handed
    back when the shape goes. m290a7 settled this one file along.

    An hour is longer than any fight, so the encounter is the clock.
    """
    me = c.me
    shape = c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    worn = [
        c.resist(resist, on=me, until=When.ENCOUNTER),
        c.regeneration(regeneration, on=me, until=When.ENCOUNTER),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
    ]
    if blind:
        worn.append(c.blinded(on=me, until=When.ENCOUNTER))
    for held in worn:
        if held is not None:
            shape.on_end.append(
                lambda h=held: c.world.effects.end(h, "it is flesh again")
            )
    return shape


def _spends_a_surge_and_braces(c: Cast) -> None:
    """A printed surge, and the +2 that comes with it.

    Four separate modifiers, so nothing is competing with anything: one "+2 to
    all defenses" written once would be a +2 to nothing.
    """
    c.surge(on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.SONT, on=c.me)


# ==========================================================================
# m1588
# ==========================================================================


@power(
    "m1588a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4),
)
def m1588a0(c: Cast) -> None:
    """Only the burn is acid; the blow itself is printed untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m1588a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 4),
)
def m1588a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1588a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1588a2(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m1588a1", targets=[c.target], spend=False)


_M1588_MISSED = "a melee attack misses the m1588"


@power(
    "m1588a3",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
    trigger=_M1588_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M1588_MISSED),
)
def m1588a3(c: Cast) -> None:
    """"Targets the triggering enemy" is read off the event rather than left
    to the dispatcher's aim."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.push(1, on=attacker)


@power(
    "m1588a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m1588a4(c: Cast) -> None:
    """A blast is not centred on the creature breathing it, so `EACH_CREATURE`
    does not catch the m1588 in its own line of fire."""
    if c.strike():
        c.hit()
        _acid_pool(c)


@power(
    "m1588a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m1588a5(c: Cast) -> None:
    """"Until the end of its next turn" with a printed Sustain Minor is
    `When.SUSTAIN`, which is that clock and the way to push it back."""
    _darkness(c)


@power(
    "m1588a6",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m1588a6(c: Cast) -> None:
    _frightful(c)


# ==========================================================================
# m2247
# ==========================================================================


@power(
    "m2247a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4),
)
def m2247a0(c: Cast) -> None:
    """Only the burn is acid; the blow itself is printed untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m2247a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4),
)
def m2247a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2247a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2247a2(c: Cast) -> None:
    for _ in range(2):
        use(c.world, c.me, "m2247a1", targets=[c.target], spend=False)


_M2247_MISSED = "the first time a melee attack misses the m2247"


@power(
    "m2247a3",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
    trigger=_M2247_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M2247_MISSED),
)
def m2247a3(c: Cast) -> None:
    """"The first time" each round is the header's `once_per_round`, which is
    the field the sibling m1588a3 does not print and so does not set."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.push(1, on=attacker)


@power(
    "m2247a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m2247a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        _acid_pool(c)


_M2247_BLED = "the m2247 is first bloodied"


@power(
    "m2247a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ACID],
    trigger=_M2247_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2247_BLED),
)
def m2247a5(c: Cast) -> None:
    """"First bloodied" needs no guard of its own -- `Bloodied` is emitted on
    the crossing and nowhere else."""
    _breathe_again(c, "m2247a4")


@power(
    "m2247a6",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m2247a6(c: Cast) -> None:
    _darkness(c)


@power(
    "m2247a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m2247a7(c: Cast) -> None:
    _frightful(c)


# ==========================================================================
# m2252
# ==========================================================================


@power(
    "m2252a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 8),
)
def m2252a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2252a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 8),
)
def m2252a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2252a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m2252a2(c: Cast) -> None:
    """No attack or damage is declared: the printed line is two squares and a
    basic attack at a bonus, and `c.basic` rolls whichever of this creature's
    rows its basic attack turns out to be.

    The step is taken *before* the swing, against the usual order, because
    here it is the thing that brings the target into reach. The +2 is a
    one-shot modifier rather than an argument, which is how `c.basic` can be
    given one at all, and it is spent by the roll it is for.

    So the step is aimed, too: unbiased it was as likely to walk out of reach
    as into it, and the swing landed anyway because the explicit-target arm
    applies no reach check.
    """
    victim = c.target
    c.move(2, toward=victim)
    c.bonus("attack", 2, until=When.EOT, on=c.me, once=True)
    c.basic(on=victim)


@power(
    "m2252a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 10, kind=LIMITED),
)
def m2252a3(c: Cast) -> None:
    """Two penalties rather than one: AC and Reflex are separate modifiers,
    and a single -3 written once would land on neither."""
    if not c.strike():
        return
    c.hit()
    for defended in (AC, REF):
        c.penalty(defended, 3, until=When.EONT)


_M2252_MATE_BLED = "a creature adjacent to the m2252 becomes bloodied"


@power(
    "m2252a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 8, kind=LIMITED),
    requires=_has_advantage,
    requires_text="the m2252 must have combat advantage against the target",
)
def m2252a4(c: Cast) -> None:
    """The printed Requirement names the target and `requires` is handed only
    `(world, eid)`, so the gate asks whether there is anybody it has the drop
    on and the aim is narrowed here.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to make the row available sooner. The forty-
    six is a printed number rather than a surge: no healing surge is named,
    and a monster spends one only where a row says so.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: adjacent(c.world, me, ev.actor))
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, me, victim):
        victim = c.choose(
            [
                foe
                for foe in sorted(c.enemies())
                if c.adjacent(foe) and has_combat_advantage(c.world, me, foe)
            ],
            "m2252a4: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(46, on=me)


@power(
    "m2252a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m2252a5(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    "With a -2 penalty on the saving throw" is `save_mod`, which is the one
    place a printed modifier to a save can live. The Aftereffect hangs on the
    hold ending rather than on `escalate`: escalation runs on a *failed* save
    and an aftereffect is what follows the hold going, whichever way it went.

    Only one creature at a time, so the earlier hold is ended before a new one
    is laid -- the printed sentence is about which creature is held, not about
    the row being unavailable while somebody is.
    """
    if not c.strike():
        return
    victim = c.target
    _release_earlier(c, c.ref)
    held = c.condition(
        Condition.DOMINATED, until=When.SAVE_ENDS, save_mod=-2, on=victim
    )
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.dazed(until=When.SAVE_ENDS, on=victim))


@power(
    "m2252a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2252a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range kind, so every attack carries it."""
    _extra_against_the_unready(c, "3d6")


@power(
    "m2252a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m2252a7(c: Cast) -> None:
    """A shape it cannot fight in. `_stone_form` is the wrong helper here --
    this one grants no resistance and no regeneration, and the mode it gains
    is a speed rather than a loss of senses -- so the two holds are built out:
    the attacks go and come back with the form, and an hour is longer than any
    fight, which makes the encounter the clock."""
    shape = c.form(
        conditions=(Condition.INSUBSTANTIAL,),
        modes={"fly": 12},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    barred = c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    if barred is not None:
        shape.on_end.append(lambda: c.world.effects.end(barred, "it is solid again"))


@power(
    "m2252a8",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m2252a8(c: Cast) -> None:
    """A surge is named here, so one is spent -- `c.surge` is that sentence,
    and a quarter of 186 is the forty-six the card prints."""
    _spends_a_surge_and_braces(c)


# ==========================================================================
# m2346
# ==========================================================================


@power(
    "m2346a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
    dropped=("c.reroll_ones()",),
)
def m2346a0(c: Cast) -> None:
    """The secondary attack is against another defence, so it cannot live in
    the header: its printed +13 is trimmed by hand the way `Attack.bonus_for`
    trims the header's.

    Two failed saves are a chain of `escalate`, each step ending the one
    before so the victim never carries two of these and never gets two saves
    against one printed sentence. The burn and the "save at -2" ride every
    link, because "instead of slowed" replaces the condition and nothing
    else.

    "Reroll a result of 1 on the damage die" is the dropped clause: nothing
    sets a floor under a single die of a rolled expression.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if not c.attack(c.world.scaling.trim(13, c.level), FORT, on=victim):
        return
    me, ref = c.me, c.ref

    def worse(condition: Condition, then: Any) -> Any:
        def step(eff: Effect) -> None:
            c.world.effects.end(eff, "the saving throw failed")
            c.world.effects.apply(
                eff.owner,
                me,
                When.SAVE_ENDS,
                label=ref,
                conditions=(condition,),
                ongoing=(5, DamageType.POISON),
                save_mod=-2,
                escalate=then,
            )

        return step

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=ref,
        conditions=(Condition.SLOWED,),
        ongoing=(5, DamageType.POISON),
        save_mod=-2,
        escalate=worse(Condition.IMMOBILIZED, worse(Condition.STUNNED, None)),
    )


_M2346_FELL = "the m2346 is reduced to 0 hit points"


@power(
    "m2346a1",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M2346_FELL,
    on=Trigger(Dropped, when=about_me, text=_M2346_FELL),
    todo=("etl.monster.attack_defence()",),
)
def m2346a1(c: Cast) -> None:
    """The compendium's attack line for this row is "+14 vs ;" -- the defence
    word is simply not there, and the row is nothing but that attack, so there
    is no surviving half to play. m1135a1 settled that a lost defence is named
    and never guessed; this one has no second sentence to carry it, so the
    whole row waits rather than one clause of it."""


@power(
    "m2346a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2346a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    A burn rather than a lump of damage, so `_extra_against_the_unready` is
    not the helper: that one deals dice on the hit. Read off the `Hit` with
    `c.had_advantage` all the same, because a one-shot grant has already been
    spent by the time the blow is announced.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not c.had_advantage(ev):
            return
        c.ongoing(10, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m2346a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2346a3(c: Cast) -> None:
    _advantage_on_arrival(c, 3)


@power(
    "m2346a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m2346a4(c: Cast) -> None:
    """Plain invisibility and not `_vanish`: this card prints no clause giving
    it away on an attack roll, only the clock."""
    c.invisible(until=When.EONT)


# ==========================================================================
# m2545
# ==========================================================================


@power(
    "m2545a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m2545a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2545a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=12),
)
def m2545a1(c: Cast) -> None:
    """No damage line: the hold and the opening are the whole of the hit.

    "After all attacks are resolved" is `c.last`, so the teleport and the
    guard happen once for the use rather than once per target, and they happen
    whether or not the blow landed -- they are an Effect line, not a rider.

    The +4 prints no duration at all. The end of its next turn is what the
    rest of the sentence is already on, and it is written rather than left
    open.
    """
    if c.strike():
        c.slowed(until=When.EONT)
        c.grants_advantage(until=When.EONT)
    if not c.last:
        return
    c.teleport(8)
    for defended in EVERY_DEFENCE:
        c.bonus(
            defended, 4, kind="power", on=c.me, until=When.EONT, when=_ranged_or_area
        )


@power(
    "m2545a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2545a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    melee, so the kind is narrowed."""
    _extra_against_the_unready(c, "2d6", ("melee",))


@power(
    "m2545a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_hazards()",),
)
def m2545a3(c: Cast) -> None:
    """Crossing the stuff it lives in costs it nothing, which is a label the
    map and `c.zone(difficult=...)` both give their squares -- the same word
    m2543a3 settled on for the same terrain one file along.

    "Takes no damage from contact with it" is the other half: a map feature
    that hurts whoever touches it is a hazard, and nothing exempts one
    creature from one.
    """
    c.ignores_difficult("blood", until=When.ENCOUNTER)


# ==========================================================================
# m3846
# ==========================================================================


@power(
    "m3846a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 5),
)
def m3846a0(c: Cast) -> None:
    """Only the burn is necrotic; the blow itself is printed untyped. "Save
    ends both" is one effect carrying the burn and the weakness together:
    applied separately the victim rolls twice and can shake off half of a
    thing the card prints as one."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        _held_and_softened(
            c,
            victim,
            conditions=(Condition.WEAKENED,),
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m3846a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3846a1(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy. The
    shift goes between the two swings, which is where the card puts it, and
    both callers hand the row their target outright -- the path that skips the
    range check, so the second bite still lands after six squares."""
    use(c.world, c.me, "m3846a0", targets=[c.target], spend=False)
    c.shift(6)
    use(c.world, c.me, "m3846a0", targets=[c.target], spend=False)


@power(
    "m3846a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.overrun(shift=)",),
)
def m3846a2(c: Cast) -> None:
    """"Phasing through enemies" is `c.overrun` and not `c.phasing`: the
    second walks through walls and floors as well, which is wider than the
    printed line and cannot be scoped down, while the first is the verb that
    passes through creatures *and says which ones* -- which is what the row
    needs in order to catch them.

    The card prints no attack bonus and no defence for "it attacks each enemy
    it phases through", so the hold is applied outright rather than rolled
    for. The difference left over is that `c.overrun` walks where the card
    shifts, so it leaves openings the printed move does not.
    """
    for trampled in c.overrun():
        c.immobilized(until=When.SAVE_ENDS, on=trampled)


# ==========================================================================
# m4124
# ==========================================================================


@power(
    "m4124a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m4124a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m4124a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4124a1(c: Cast) -> None:
    """No attack or damage is declared: the swing is a melee basic attack, so
    `c.basic` rolls whichever of this creature's rows that is.

    The printed recharge is a sentence on top of the die the database files,
    and `PowerUsed` carries the ref of whatever just fired. "Without provoking
    an opportunity attack from the target" is narrower than the header's
    `no_provoke`, which is about using the power rather than about the flight,
    so it is `c.no_provoke(from_=)` aimed at the one creature named.

    The flight itself is aimed as well: "at any point during the move" has no
    finer unit than fly-then-swing, so the flight is what must close.
    """
    me = c.me
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m4124a2")
    victim = c.target
    if victim is None:
        return
    c.no_provoke(from_=victim, on=me, until=When.EOT)
    c.move(8, at="fly", toward=victim)
    if c.basic(on=victim):
        c.prone(on=victim)


@power(
    "m4124a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.tremorsense()",),
)
def m4124a2(c: Cast) -> None:
    """"Loses all other senses" is written as blindness, which is the only
    sense the engine holds; the tremorsense that is supposed to replace it has
    nowhere to go, so this form is strictly worse than the card's by the one
    marked clause."""
    _stone_form(c, 25, 3, blind=True)


# ==========================================================================
# m4770
# ==========================================================================


def _could_not_see_me(c: Cast, watcher: int | None) -> bool:
    """"If the target cannot see it" -- asked **before** the attack is rolled.

    `resolve.attack` clears the hiding for whoever swung, so asked after the
    strike the answer is no on every attack the clause exists for. The same
    trap m2920a3 found one file along, from the other side.
    """
    return watcher is not None and unseen_by(c.world, watcher, c.me)


@power(
    "m4770a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m4770a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The burn is the only poison on the line; the blow is untyped."""
    victim = c.target
    unseen = _could_not_see_me(c, victim)
    if not c.strike():
        return
    c.hit()
    if unseen:
        c.ongoing(15, DamageType.POISON)


@power(
    "m4770a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4770a1(c: Cast) -> None:
    """Two *basic* attacks rather than two of a named row, so `c.basic` rolls
    whichever of this creature's rows its basic attack turns out to be."""
    for _ in range(2):
        c.basic(on=c.target)


@power(
    "m4770a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4770a2(c: Cast) -> None:
    """The penalty is "while the target is dazed", so it rides the same hold
    rather than carrying a clock of its own, and it is gated on who is being
    swung at -- `ctx["target"]` -- because it is only against this creature.

    Whether the victim could see it is read before the roll, for the reason
    `_could_not_see_me` gives.
    """
    victim = c.target
    unseen = _could_not_see_me(c, victim)
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    me = c.me
    hidden = Mod(
        what="attack",
        value=-2,
        label=c.ref,
        when=lambda ctx: ctx.get("target") == me,
    )
    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.DAZED,),
        mods=[(victim, hidden)] if unseen else (),
    )


@power(
    "m4770a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4770a3(c: Cast) -> None:
    """Plain invisibility: this card prints no clause giving it away on an
    attack roll, only the clock. Which matters on this stat block in
    particular -- two of its three attack rows pay out extra against anybody
    who cannot see it, and `_vanish` would end the veil on the first swing."""
    c.invisible(until=When.EONT)


# ==========================================================================
# m5333
# ==========================================================================


@power(
    "m5333a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    dropped=("c.place_scenery()",),
)
def m5333a0(c: Cast) -> None:
    """A thing an enemy may choose to do to itself, which is what `c.give` is:
    a one-shot in somebody's hands, spent on their own clock for the action
    the card names, paying out through a function that closes over this
    creature.

    The pool is rolled once -- four to eight -- and counted down, and
    `AdjacencyGained` is the moment a creature could reach one. Picking and
    drinking are two minor actions on the card and one spend here, because an
    `Item` carries a single cost.

    What is missing is the fruit as objects standing on the board for anybody
    at all to take, rather than handed to whoever comes within reach.
    `c.place_scenery()` is the symbol m4620a2 carries for the same absence.
    """
    me, ref = c.me, c.ref
    left = 3 + c.roll("1d5")

    def drink(spender: int) -> None:
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=spender)

    def offer(taker: int) -> None:
        nonlocal left
        if left <= 0 or c.carrying(ref, on=taker):
            return
        left -= 1
        c.give(ref, drink, on=taker, cost=MINOR)

    def arrived(ev: AdjacencyGained) -> None:
        if ev.actor == me and ev.other in c.enemies():
            offer(ev.other)

    c.watch(AdjacencyGained, arrived, until=When.ENCOUNTER, on=me, label=ref)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            offer(foe)


@power(
    "m5333a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6),
)
def m5333a1(c: Cast) -> None:
    """"Dominated by the m5333" is the relation and not the condition: a
    creature dominated by somebody else is not what the clause means."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and _dominated_by_me(c, victim):
        c.ongoing(10, DamageType.NECROTIC, on=victim)


@power(
    "m5333a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
)
def m5333a2(c: Cast) -> None:
    """"Each attack against a different target" is two targets off the header
    and a once-per-power body, because the row it uses carries the damage and
    would otherwise be rolled twice per victim."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        use(c.world, c.me, "m5333a1", targets=[victim], spend=False)


@power(
    "m5333a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.ZONE],
    attack=Attack(vs=WILL, printed=14),
)
def m5333a3(c: Cast) -> None:
    """No damage line: the hold and what follows it are the whole of the hit.

    Three clauses needed a decision. "Cannot save while at 0 hit points or
    fewer" is a listener on `SavingThrow`, which is announced before it is
    acted on and reads `saved` back -- `c.unsave` is that one line, and it is
    gated on the effect's own label so it touches no other roll. "At the start
    of the m5333's next turn" is a one-shot `TurnStart` watch armed when the
    victim falls, and the square is taken then, while there is still a body in
    it. And the slain creature not being raisable is noted: raising the dead
    is not something a board does, so there is nothing to hold.

    The zone is laid once for the use, which is what `c.first` is for.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m5333a4")
    if c.first:
        area = c.area()
        if area:
            field = c.zone(area, label=ref, until=When.EONT)
            c.grants_in(
                field,
                "save",
                -5,
                side="enemy",
                when=lambda ctx: ctx.get("label") == ref,
            )
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def doomed(ev: SavingThrow) -> None:
        health = c.world.get(victim, Health)
        if ev.actor != victim or ref not in ev.against:
            return
        if health is not None and health.hp <= 0:
            c.unsave(ev)

    def fell(ev: Dropped) -> None:
        if ev.actor != victim:
            return
        spot = c.world.get(victim, Position)
        where = spot.square if spot is not None else None

        def rises(turn: TurnStart) -> None:
            if turn.ghost or turn.actor != me:
                return
            c.summon("m5334", at=where)
            c.note(f"{ref}: the slain cannot be restored while the thrall stands")

        c.watch(
            TurnStart, rises, until=When.ENCOUNTER, on=me, once=True,
            label=f"{ref} thrall",
        )

    watches = (
        c.watch(SavingThrow, doomed, until=When.ENCOUNTER, on=victim, label=f"{ref} save"),
        c.watch(Dropped, fell, until=When.ENCOUNTER, on=victim, label=f"{ref} fall"),
    )
    for watch in watches:
        hold.on_end.append(
            lambda w=watch: c.world.effects.end(w, "the domination is over")
        )


@power(
    "m5333a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    narrative=("skill:nature",),
)
def m5333a4(c: Cast) -> None:
    """The resistance, the regeneration and the way out are exact. The DC 27
    Nature check to tell the shape from the real thing is the narrative half:
    nothing on a board ever rolls Nature to look at a creature, so a bonus or
    a DC for it would be a number nobody reads, and there is no symbol to wait
    for."""
    _stone_form(c, 15, 5, blind=False)


# ==========================================================================
# m5492
# ==========================================================================


@power(
    "m5492a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5492a0(c: Cast) -> None:
    """Four separate modifiers, so nothing is competing with anything: one
    "+2 to all defenses" written once would be a +2 to nothing. Untyped,
    because the card prints no word in front of "bonus"."""
    for defended in EVERY_DEFENCE:
        c.bonus(
            defended, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("ranged")),
        )


@power(
    "m5492a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5492a1(c: Cast) -> None:
    """A standing property that is only true while it holds somebody, which
    neither `c.insubstantial` nor `c.immovable` has a `when=` for -- and a
    `when=` would be the wrong tool anyway, since both are read off the
    creature rather than off a swing's context.

    So the two holds are put on and taken off as the grip changes. A grab is a
    **relation** and not a condition the bus announces, so `RelationSet` and
    `RelationCleared` are the two moments that can say so -- `ConditionApplied`
    is never emitted for one, which `lint.py` catches. The state is resynced
    from `c.grabbing` rather than counted, so a second captive does not lay a
    second pair and letting one of two go does not take the pair off.
    """
    me, ref = c.me, c.ref
    worn: list[Effect] = []

    def resync() -> None:
        gripping = bool(c.grabbing(of=me))
        if gripping and not worn:
            for got in (
                c.insubstantial(on=me, until=When.ENCOUNTER),
                c.immovable(on=me, until=When.ENCOUNTER),
            ):
                if got is not None:
                    worn.append(got)
        elif not gripping and worn:
            for got in worn:
                c.world.effects.end(got, "its grip is broken")
            worn.clear()

    def took(ev: RelationSet) -> None:
        if ev.kind_ is Relation.GRABBED_BY:
            resync()

    def slipped(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY:
            resync()

    c.watch(RelationSet, took, until=When.ENCOUNTER, on=me, label=f"{ref} grip")
    c.watch(RelationCleared, slipped, until=When.ENCOUNTER, on=me, label=f"{ref} slip")
    resync()


@power(
    "m5492a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m5492a2(c: Cast) -> None:
    """"If it has combat advantage" is read off the live result rather than
    asked of the board again: a one-shot grant has already been spent by the
    time the blow is announced.

    The -5 is "to attempts to escape the grab", so it goes with the grab and
    comes off with it rather than running on a clock of its own. `escape` is
    the key `escape.attempt` totals.
    """
    result = c.strike()
    if not result:
        return
    c.hit()
    if not result.advantage:
        return
    held = c.grab()
    sagging = c.penalty("escape", 5, until=When.ENCOUNTER)
    if held is not None and sagging is not None:
        held.on_end.append(
            lambda: c.world.effects.end(sagging, "the grip is gone")
        )


@power(
    "m5492a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one living creature grabbed by it",
        relation=Relation.GRABBED_BY,
        # "Living" is not a negative set. Excluding `construct` as well
        # refuses the 25 blocks that carry *both* `living` and `construct`,
        # which the card calls living; excluding only `undead` admits a
        # non-living construct. The exact test is "not undead, and not
        # construct unless it carries living", which no any-of negative can
        # say. This is the faithful half -- what the body asked before the
        # conversion -- and the exception is marked. #411.
        kinds_without=frozenset({"undead"}),
    ),
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d10", 5, dtype=DamageType.NECROTIC),
    dropped=("Target.living",),
)
def m5492a3(c: Cast) -> None:
    """The whole target line is the header's now: `relation=` for the grab and
    `kinds_without=` for "living", which is the absence of the two type words
    and not a word of its own. The redirect that asked both by hand came out.

    "If this attack bloodies the target" is the line read on both sides of the
    blow: a creature already bloodied is not bloodied again by it. "The grab
    ends" is this creature letting go and not the victim escaping, so it is
    `holds.release` -- a grab lives in the relation table and carries no
    `Condition.GRABBED`, so `c.end_effect(carrying=)` finds nothing and
    `c.escape` would announce a struggle that never happened.
    """
    me = c.me
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    was = c.bloodied(on=victim)
    c.hit(on=victim)
    release(c, victim)
    c.heal(10, on=me)
    if not was and c.bloodied(on=victim):
        c.unconscious(until=When.SAVE_ENDS, on=victim)


@power(
    "m5492a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one living creature",
        # "Living" is not a negative set. Excluding `construct` as well
        # refuses the 25 blocks that carry *both* `living` and `construct`,
        # which the card calls living; excluding only `undead` admits a
        # non-living construct. The exact test is "not undead, and not
        # construct unless it carries living", which no any-of negative can
        # say. This is the faithful half -- what the body asked before the
        # conversion -- and the exception is marked. #411.
        kinds_without=frozenset({"undead"}),
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 7, dtype=DamageType.NECROTIC),
    dropped=("Target.living",),
)
def m5492a4(c: Cast) -> None:
    """"One living creature" is the target line now. "Save ends both" is one
    effect carrying the daze and the slow together: applied separately the
    victim rolls twice and can shake off half of a thing the card prints as
    one."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    _held_and_softened(
        c, victim, conditions=(Condition.DAZED, Condition.SLOWED)
    )


# ==========================================================================
# m5566
# ==========================================================================


@power(
    "m5566a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 6),
)
def m5566a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5566a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM),
    keywords=[Keyword.ILLUSION, Keyword.POLYMORPH],
)
def m5566a1(c: Cast) -> None:
    """No attack line at all: the whole row is an Effect, so there is nothing
    to roll and the hold lands outright.

    "One Medium creature" is a size the header can say, which is why this one
    needs no correction in the body. The extra 6d8 is gated on the row the
    card names -- the weapon line printed above it on this stat block -- and
    hung on the likeness so it goes when the likeness does; `revert=None`
    because the card offers no way to drop it early, only the clock.
    """
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    shape = c.form(until=When.EONT, revert=None, label=ref)
    c.immobilized(until=When.EONT, on=victim)

    def harder(ev: Hit) -> None:
        if ev.attacker == me and ev.target == victim and ev.power == "m5566a0":
            c.damage("6d8", on=victim, detail=ref)

    watch = c.watch(Hit, harder, until=When.EONT, on=me, label=ref)
    shape.on_end.append(
        lambda: c.world.effects.end(watch, "the likeness is gone")
    )


@power(
    "m5566a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5566a2(c: Cast) -> None:
    """A disguise and nothing else: no condition, no mode, no number. The
    whole printed Effect is what it looks like and an Insight check to see
    through it, and a shape that changes nothing a fight reads would be a
    `c.form` with an empty argument list. Deliberately inert rather than
    unwritten, which is what the flag says."""


_M5566_SHIELDED = "a melee or ranged attack from an unaffected enemy targets the m5566"


@power(
    "m5566a3",
    level=11,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5566_SHIELDED,
    on=Trigger(
        AttackDeclared,
        when=both(targets_me, either(by_melee, by_ranged)),
        text=_M5566_SHIELDED,
    ),
)
def m5566a3(c: Cast) -> None:
    """The printed Requirement is asked in the body and not in `requires=`:
    it is about who is standing where *now*, and it goes from false to true
    the moment m5566a1 lands, which is after the row has been armed.

    The swap happens first and the redirect second, because `c.redirect` moves
    the live attack and the card has the two creatures change places before
    the blow arrives. `AttackDeclared` is the window where moving it is still
    possible.
    """
    me = c.me
    decoy = next((f for f in sorted(c.suffering("m5566a1")) if c.adjacent(f)), None)
    attacker = getattr(c.trigger, "attacker", None)
    if decoy is None or attacker is None or attacker == decoy:
        return
    if me != decoy and c.swap(decoy):
        c.redirect(to=decoy)


# ==========================================================================
# m6283
# ==========================================================================


@power(
    "m6283a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d4", 9),
)
def m6283a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6283a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d4", 9),
)
def m6283a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6283a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d4", 9, kind=LIMITED),
)
def m6283a2(c: Cast) -> None:
    """The Effect is unconditional and once for the use, so it sits behind
    `c.last` rather than inside the hit branch -- and after the swings, since
    the stance it enters bars attacking."""
    if c.strike():
        c.hit()
    if c.last:
        c.use_power("m6283a3", spend=False)


@power(
    "m6283a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def m6283a3(c: Cast) -> None:
    """Two clocks, a turn apart, and that is the whole of the row. The stance
    and the bar on attacking run to the start of its next turn; the payout
    runs to the **end** of that turn, which is what "before the end of the
    turn during which the stance ends" says.

    `c.cannot_attack` rather than a condition, for the reason m290a7 gives:
    a creature that cannot act is offered nothing, and this one has a turn to
    spend after the bar lifts.
    """
    me, ref = c.me, c.ref
    c.stance(on=me, label=ref)
    c.cannot_attack(on=me, until=When.SONT)
    spent = False

    def rider(ev: Hit) -> None:
        nonlocal spent
        if spent or ev.attacker != me or ev.target not in c.enemies():
            return
        spent = True
        c.damage("5d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.EONT, on=me, label=ref)


_M6283_STRUCK = "an attack hits the m6283 while it is in its m6283a3 stance"


@power(
    "m6283a4",
    level=11,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6283_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M6283_STRUCK),
)
def m6283a4(c: Cast) -> None:
    """`AttackRolled` and not `Hit`: `resolve.attack` recomputes the outcome
    from `ev.result` after this window closes, which is the only place a row
    can turn a landed blow aside. `would_hit_me` is "an attack hits it" asked
    one event early.

    A natural 1 is an automatic miss, so that is what the result is set to
    rather than arithmetic against the defence -- the card says the attack
    misses, and a 20 that crits would otherwise survive the recompute.

    The stance is the printed Requirement and is asked here, where it is
    re-read every time the trigger fires.
    """
    me = c.me
    if not any(e.label == "m6283a3" for e in c.world.effects.of(me)):
        return
    result = getattr(c.trigger, "result", None)
    if result is None or not result.hit:
        return
    rolled = c.check("acrobatics")
    if int(getattr(rolled, "total", 0)) <= result.total:
        return
    result.natural = 1
    result.critical = False
    result.hit = False
    c.shift(2)
    c.note(f"{c.ref}: the swing is turned aside")
