"""Monster abilities, level 11: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the ten levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; a printed "Range 10/20" is a
normal range and a long one and the normal one is what `Range` holds; and a
helper written for an earlier level is imported rather than copied.

Six things this file had to settle.

**"While it is invisible its attacks deal twice the ongoing damage"** cannot
be asked when the burn is applied: `resolve.attack` breaks the hiding for
whoever swung, so by the time the body reaches its `ongoing` line the answer
is no on every attack the rider exists for. The trait reads it in the
`AttackDeclared` window instead -- which is before the roll callback, and the
last moment the creature is still unseen -- keeps the answer, and doubles the
burn the attack goes on to lay. Doubling in place also means it does not
matter which door the burn came through: `c.ongoing` and a "save ends both"
`Effects.apply` both end up holding the same field.

**Ongoing damage of one type no longer stacks**, so a second burn of the same
type is refused and the standing one handed back. Nothing here prints the
"increase it" shape, but m2920's three attack rows all lay poison and the
doubling above supersedes rather than adds, which is the same rule seen from
the other side.

**A poison is a row.** m164 prints its coating as a stat block entry of its
own and both weapon rows say "see m164a4 for the effect", so it is written
once and `use`d rather than copied twice. It prints no range of its own --
the weapon carrying it does -- so the melee row's reach stands in for the
header, and both callers hand it their target explicitly, which skips the
range check entirely.

**"Resist 5 to all damage of the triggering attack"** is not a duration. The
guard goes up in the interrupt window and comes down as the packet it answers
lands, with the start of the m2905's next turn as the backstop for an attack
that deals no damage at all -- the same shape `_until_that_blow_lands` settled
on four levels down for a defence bonus, moved one event later because this
one has to survive the `Hit` it is answering.

**A breath weapon that recharges itself** is `Powers.restore` plus a use, the
arrangement m2895a6 settled on. Both dragons here print that line naming
*another* stat block's id for their own breath; the row every sentence
plainly means is the one on the same card, which is how m4990a1 read the same
slip.

**"Whenever the target takes 10 damage or more it can make a saving throw"**
against an effect that lasts until the end of the encounter is
`Effects.save` called directly: `c.save` only answers a `When.SAVE_ENDS`
effect, and making this one save-ends would hand the victim a free roll at
the end of every turn, which is the clock the printed line replaced.

Each stat block in ref order.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_04.skirmishers import _has_advantage
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_11.controllers import (
    _held_and_softened,
    _softened,
)
from combat_engine.content.monsters.level_11.skirmishers import _release_earlier
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Powers,
    Ranged,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    ZoneEntered,
    by_melee,
    power,
    use,
)
from combat_engine.engine.events import EffectApplied, ZoneExited
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, has_combat_advantage
from combat_engine.engine.triggers import Trigger, about_me, both, targets_me
from combat_engine.engine.zones import Zone

#: The four defences, for a printed "a +2 bonus to all defenses".
EVERY_DEFENCE = (AC, FORT, REF, WILL)

#: What "melee and ranged attacks" means as a range kind. A close burst is
#: neither, which is the whole reason the pair is written out.
_WEAPON_RANGES = ("melee", "ranged")


def _extra_against_the_unready(c: Cast, dice: str, kinds: tuple[str, ...] = ()) -> None:
    """"Deals an extra NdM against any target it has combat advantage against."

    Read off the `Hit` with `c.had_advantage` rather than asked of the board
    again: a one-shot grant has already been spent by the time the blow is
    announced, so a second asking answers no on exactly the attacks the rider
    is for. `kinds` narrows it where the printed line names melee and ranged;
    empty means every attack, which is what a line naming none says.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not c.had_advantage(ev):
            return
        if kinds and _reach_kind(ev) not in kinds:
            return
        c.damage(dice, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _frightful(c: Cast) -> None:
    """A burst that stuns, and the lighter hold that follows it.

    No damage at all -- the stun is the whole of the hit. The Aftereffect
    begins when the stun ends, whichever way it ended, and the end of an
    effect is the only moment that can be seen, so it is hung there.
    """
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT)
    if held is not None and victim is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


def _breathe_again(c: Cast, breath: str) -> None:
    """"Its breath weapon recharges, and it uses it immediately."

    `Powers.restore` is what a recharge is. "First bloodied" needs no guard
    of its own -- `Bloodied` is emitted on the crossing and nowhere else.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore(breath)
    use(c.world, c.me, breath)


# ==========================================================================
# m164
# ==========================================================================


def _coated(c: Cast, victim: int | None) -> None:
    """The secondary attack both weapon rows print, and what it carries.

    A second attack line against a different defence cannot live in the
    header, so its printed +13 is trimmed by hand the way `Attack.bonus_for`
    trims the header's. The effect is the poison's own row rather than a copy
    of it in two places.
    """
    if victim is None:
        return
    if c.attack(c.world.scaling.trim(13, c.level), FORT, on=victim):
        use(c.world, c.me, "m164a4", targets=[victim], spend=False)


@power(
    "m164a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m164a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        _coated(c, c.target)


@power(
    "m164a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 4),
)
def m164a1(c: Cast) -> None:
    """10/20 is a normal range and a long one, and `Range` holds one number,
    so the normal range is written."""
    if c.strike():
        c.hit()
        _coated(c, c.target)


@power(
    "m164a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
)
def m164a2(c: Cast) -> None:
    """No damage line: the opening is the whole of the hit.

    "Grants combat advantage to all attacks" is wider than the relation table
    can say -- it names one beneficiary at a time -- and `to="allies"` is the
    whole of the m164's side, which is every attacker the printed line will
    ever be asked about.

    The second half is left as a note, the way m2947a4 left the same
    sentence: cover and concealment are computed between two positions at the
    moment of the attack, so there is no state to put a creature into.
    """
    if c.strike():
        c.grants_advantage(until=When.EONT, to="allies")
        c.note("m164a2: the target cannot benefit from invisibility or concealment")


@power(
    "m164a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m164a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    _extra_against_the_unready(c, "2d6", _WEAPON_RANGES)


@power(
    "m164a4",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
)
def m164a4(c: Cast) -> None:
    """The coating, as a row, because both weapon rows name it.

    It prints no range of its own -- whatever is dipped in it does -- so the
    melee row's reach stands in for the header and both callers hand it their
    target outright, which is the path that skips the range check.

    Two failed saves are a chain of `escalate`, each step ending the one
    before so the victim never carries two of these and never gets two saves
    against one printed sentence. "Is *also* weakened" keeps the -2, which is
    why the second hold carries the modifier again.
    """
    victim = c.target
    if victim is None:
        return

    def collapse(eff: Effect) -> None:
        c.world.effects.end(eff, "the second save failed")
        c.unconscious(until=When.ENCOUNTER, on=eff.owner)

    def weaken(eff: Effect) -> None:
        c.world.effects.end(eff, "the first save failed")
        c.world.effects.apply(
            eff.owner,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.WEAKENED,),
            mods=[(eff.owner, m) for m in _softened(c, attack=2)],
            escalate=collapse,
        )

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, m) for m in _softened(c, attack=2)],
        escalate=weaken,
    )


# ==========================================================================
# m290
# ==========================================================================


@power(
    "m290a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 8),
)
def m290a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m290a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 8),
)
def m290a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m290a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m290a2(c: Cast) -> None:
    """The printed attack line is an empty one -- a defence and no damage --
    and the Effect below it is the whole row: two squares and a basic attack
    at a bonus. So no attack or damage is declared here; `c.basic` rolls
    whichever of this creature's rows its basic attack turns out to be.

    The step is taken *before* the swing, against the usual order, because
    here it is the thing that brings the target into reach. The +2 is a
    one-shot modifier rather than an argument, which is how `c.basic` can be
    given one at all, and it is spent by the roll it is for.
    """
    c.move(2)
    c.bonus("attack", 2, until=When.EOT, on=c.me, once=True)
    c.basic(on=c.target)


@power(
    "m290a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 10, kind=LIMITED),
)
def m290a3(c: Cast) -> None:
    """Two penalties rather than one: AC and Reflex are separate modifiers,
    and a single -3 written once would land on neither."""
    if not c.strike():
        return
    c.hit()
    for defended in (AC, REF):
        c.penalty(defended, 3, until=When.EONT)


_M290_MATE_BLED = "a creature adjacent to the m290 is first bloodied"


@power(
    "m290a4",
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
    requires_text="the m290 must have combat advantage against the target",
)
def m290a4(c: Cast) -> None:
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
            "m290a4: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(46, on=me)


@power(
    "m290a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m290a5(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    "With a -2 penalty on the saving throw" is `save_mod`, which is the one
    place a printed modifier to a save can live. The Aftereffect hangs on the
    hold ending rather than on `escalate`: escalation runs on a *failed* save
    and an aftereffect is what follows the hold going, whichever way it went.

    Only one creature at a time, so the earlier hold is ended before a new
    one is laid -- the printed sentence is about which creature is held, not
    about the row being unavailable while somebody is.
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
    "m290a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m290a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range kind, so every attack carries it."""
    _extra_against_the_unready(c, "3d6")


@power(
    "m290a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m290a7(c: Cast) -> None:
    """A shape it cannot fight in.

    `Condition.STUNNED` would be the obvious way to write "cannot make
    attacks" and is the wrong one: `actions.legal` offers a creature that
    cannot act nothing but the end of its turn, so the printed way *out* of
    the shape -- a minor action -- would be unreachable. The attacks are
    taken away instead and handed back when the shape goes.

    An hour is longer than any fight, so the encounter is the clock.
    """
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
    "m290a8",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m290a8(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Sunlight is a property of the fight rather than of anybody in it, which
    is what `c.terrain` asks, and it is asked at each end of the turn rather
    than now, because a fight can move into the open. The arrangement m812a1
    settled on a level down.

    "Only a single move action" is the budget itself: there is no condition
    that takes the standard and the minor and leaves the move.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = 0
            budget.minor = 0
        c.note("m290a8: sunlight leaves it a single move action")

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} dawn")
    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label=f"{c.ref} dusk")


@power(
    "m290a9",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m290a9(c: Cast) -> None:
    """A surge is named here, so one is spent -- `c.surge` is that sentence,
    and a quarter of 186 is the forty-six the card prints. Four separate
    modifiers, so nothing is competing with anything: one "+2 to all
    defenses" written once would be a +2 to nothing."""
    c.surge(on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.SONT, on=c.me)


# ==========================================================================
# m2905
# ==========================================================================


@power(
    "m2905a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 5),
)
def m2905a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2905a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2905a2(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m2905a1", targets=[c.target], spend=False)


_M2905_STRUCK = "the m2905 is hit by an attack"


def _until_that_damage_lands(c: Cast, attacker: int, guard: Effect | None) -> None:
    """End a hold as soon as that creature's blow has actually bitten.

    "Resist 5 to all damage of the triggering attack" has to survive the
    `Hit` it is answering -- which is where `_until_that_blow_lands` takes a
    defence bonus off -- and go the moment the packet it is for has been
    counted. An attack that deals no damage at all leaves nothing to hear, so
    the hold carries the start of the next turn as a backstop.
    """
    if guard is None:
        return
    me = c.me

    def done(ev: DamageApplied) -> None:
        if ev.source == attacker and ev.target == me and not guard.ended:
            c.world.effects.end(guard, "the attack is over")

    c.watch(
        DamageApplied, done, until=When.SONT, on=me, once=True,
        label=f"{c.ref} guard",
    )


@power(
    "m2905a3",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 3),
    trigger=_M2905_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M2905_STRUCK),
)
def m2905a3(c: Cast) -> None:
    """The guard goes up between the blow landing and the damage arriving.

    `Hit` rather than `AttackRolled`: this one does not turn a hit aside, it
    softens the packet, and the packet is rolled after the `Hit` is
    announced. The swing back names no target on the card; the creature that
    just struck it is the only one the sentence can mean, and reach 2 is what
    every other melee line on this stat block prints.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    _until_that_damage_lands(c, attacker, c.resist(5, on=c.me, until=When.SONT))
    if c.strike(on=attacker):
        c.hit(on=attacker)


@power(
    "m2905a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 6, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m2905a4(c: Cast) -> None:
    """A blast is not centred on the creature breathing it, so `EACH_CREATURE`
    does not catch the m2905 in its own line of fire."""
    if c.strike():
        c.hit()
        c.pull(3)
    else:
        c.hit(half=True)


_M2905_BLED = "the m2905 is first bloodied"


@power(
    "m2905a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2905_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2905_BLED),
)
def m2905a5(c: Cast) -> None:
    """The card spells the breath as another stat block's id; the row every
    sentence plainly means is the one printed above it on this card."""
    _breathe_again(c, "m2905a4")


@power(
    "m2905a6",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=12),
)
def m2905a6(c: Cast) -> None:
    _frightful(c)


# ==========================================================================
# m2920
# ==========================================================================


@power(
    "m2920a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 3),
)
def m2920a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The burn is printed untyped, which is the only reason it is not
    the same effect as the poison the other two rows lay."""
    if c.strike():
        c.hit()
        c.ongoing(5)


_M2920_BIT = "the m2920 hits with its m2920a0 attack"


@power(
    "m2920a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", kind=LIMITED),
    requires=_has_advantage,
    requires_text="the m2920 must have combat advantage against the target",
)
def m2920a1(c: Cast) -> None:
    """The printed Requirement names the target and `requires` is handed only
    `(world, eid)`, so the gate asks whether there is anybody it has the drop
    on and the aim is narrowed here.

    "Save ends both" is one effect carrying the burn and the penalty
    together: applied separately the victim rolls twice and can shake off
    half of a thing the card prints as one.
    """
    me = c.me
    _recharge_on(c, Hit, lambda ev: ev.attacker == me and ev.power == "m2920a0")
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, me, victim):
        victim = c.choose(
            [
                foe
                for foe in sorted(c.enemies())
                if c.adjacent(foe) and has_combat_advantage(c.world, me, foe)
            ],
            "m2920a1: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    _held_and_softened(
        c, victim, ongoing=(5, DamageType.POISON), attack=2
    )


@power(
    "m2920a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8"),
)
def m2920a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        _held_and_softened(c, victim, ongoing=(5, DamageType.POISON), attack=2)


@power(
    "m2920a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2920a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Whether it was unseen is read in the `AttackDeclared` window, which runs
    before the resolve callback and is therefore the last moment the answer
    is still yes: `resolve.attack` clears the hiding for whoever swung, and
    the veil this creature wears ends on its own attack roll besides. Asked
    where the burn is laid, the answer is no on every attack this rider
    exists for.

    The burn is doubled in place rather than re-laid, so it does not matter
    whether the attack went through `c.ongoing` or through the "save ends
    both" door, and the doubling cannot be refused for being a second burn of
    a type already standing. The flag is cleared as it is spent: one attack
    lays one burn, and nothing else this creature applies should be doubled
    by a reading taken for an earlier swing.
    """
    me = c.me
    unseen = False

    def sighting(ev: AttackDeclared) -> None:
        nonlocal unseen
        if ev.attacker == me:
            unseen = c.is_hidden(from_=ev.target)

    def doubled(ev: EffectApplied) -> None:
        nonlocal unseen
        if not unseen or ev.source != me:
            return
        laid = [
            eff
            for eff in c.world.effects.of(ev.target)
            if eff.source == me and eff.label == ev.label and eff.ongoing is not None
        ]
        if not laid:
            return
        worst = max(laid, key=lambda eff: eff.id)
        unseen = False
        worst.ongoing = (worst.ongoing[0] * 2, worst.ongoing[1])

    c.watch(
        AttackDeclared, sighting, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} sighting",
    )
    c.watch(EffectApplied, doubled, until=When.ENCOUNTER, on=me, label=c.ref)


def _in_the_dark(world: World, eid: int) -> bool:
    """Half of a printed Requirement, and the half that can be asked.

    Light is a property of the fight, which is what `c.terrain` reads. The
    other half -- adjacent to an object or a wall of at least a square -- has
    nothing to ask: the engine holds no objects and no walls. So the gate is
    the light alone, `requires_text` prints the whole sentence, and the rest
    is in the report.
    """
    ask = Cast(world=world, me=eid, ref="m2920a4")
    return ask.terrain("darkness") or ask.terrain("dim light")


@power(
    "m2920a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_in_the_dark,
    requires_text=(
        "the m2920 must be in dim light or darkness and adjacent to an object "
        "or a wall that occupies at least 1 square"
    ),
)
def m2920a4(c: Cast) -> None:
    """"Until the end of its next turn or until after it hits or misses with
    an attack" is both of `_vanish`'s ends: a clock, and the attack roll that
    gives it away whichever way the die falls."""
    _vanish(c, When.EONT)


# ==========================================================================
# m43
# ==========================================================================


@power(
    "m43a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4),
)
def m43a0(c: Cast) -> None:
    """Only the burn is acid; the blow itself is printed untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m43a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 4),
)
def m43a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m43a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m43a2(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m43a1", targets=[c.target], spend=False)


_M43_MISSED = "a melee attack misses the m43"


@power(
    "m43a3",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
    trigger=_M43_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M43_MISSED),
)
def m43a3(c: Cast) -> None:
    """"Targets the enemy that missed it" is read off the event rather than
    left to the dispatcher's aim."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.push(1, on=attacker)


@power(
    "m43a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m43a4(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the penalty
    together: applied separately the victim rolls twice and can shake off
    half of a thing the card prints as one. `_held_and_softened` is the
    helper for that shape and takes a penalty to *all* defences; this one is
    to AC alone, so the modifier is built here.

    A blast is not centred on the creature breathing it, so `EACH_CREATURE`
    does not catch the m43 in its own line of fire.
    """
    if not c.strike():
        return
    c.hit()
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


_M43_BLED = "the m43 is first bloodied"


@power(
    "m43a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ACID],
    trigger=_M43_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M43_BLED),
)
def m43a5(c: Cast) -> None:
    _breathe_again(c, "m43a4")


@power(
    "m43a6",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m43a6(c: Cast) -> None:
    """A cloud that nobody can see through and nobody inside can see at all.

    `blocks_sight` is what `cover_between` reads and it applies to everybody;
    there is no way to exempt one creature from it, so the m43's own sight
    through its cloud is noted rather than invented.

    The blinding is held per occupant and diffed by the two events that say
    who is standing in it -- the arrangement m5051a3 settled on -- because a
    zone's own fields make squares rough or dark and carry no conditions.
    Ending the zone emits a `ZoneExited` for everybody inside, which is what
    takes the holds off.

    "Until the end of its next turn" with a printed Sustain Minor is
    `When.SUSTAIN`, which is that clock and the way to push it back.
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
    c.note("m43a6: the m43 sees through its own darkness")


@power(
    "m43a7",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m43a7(c: Cast) -> None:
    _frightful(c)


# ==========================================================================
# m4941
# ==========================================================================


@power(
    "m4941a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 5),
)
def m4941a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4941a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.DISEASE, Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=14),
)
def m4941a1(c: Cast) -> None:
    """No damage line: the hold and what rides with it are the whole hit.

    The three riders are re-armed rather than carried over when the first
    save fails: `escalate` ends the hold it is given and a new one replaces
    it, so anything hung on the old hold's ending has already come off by
    then. Arming them again from the new hold is shorter than a flag saying
    not to.

    The extra 2d6 is dealt by the m4941 rather than by the creature swinging
    -- `c.damage` sources everything to the caster, which is the compromise
    every rider of this shape in the tree makes.

    The disease itself has nowhere to go: the engine holds no diseases and no
    track to move along, so being exposed is noted. The saving throw the
    second paragraph offers is `Effects.save` called outright, because
    `c.save` answers only a `When.SAVE_ENDS` effect and this hold has been
    taken off that clock by the sentence above it.
    """
    me, ref = c.me, c.ref
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.note("m4941a1: the target is exposed to the m4941's corruption")

    def rides(hold: Effect) -> None:
        veil = c.invisible(to=victim, until=When.ENCOUNTER)

        def harder(ev: Hit) -> None:
            if ev.attacker == victim:
                c.damage("2d6", on=ev.target, detail=ref)

        rider = c.watch(Hit, harder, until=When.ENCOUNTER, on=victim, label=ref)
        for worn in (veil, rider):
            if worn is not None:
                hold.on_end.append(
                    lambda w=worn: c.world.effects.end(w, "the disarray passed")
                )

    def deepen(eff: Effect) -> None:
        c.world.effects.end(eff, "the first save failed")
        lasting = c.condition(Condition.DOMINATED, until=When.ENCOUNTER, on=victim)
        if lasting is None:
            return
        rides(lasting)

        def mirrored(ev: DamageApplied) -> None:
            if ev.target != victim or ev.amount < 10 or lasting.ended:
                return
            c.flat(ev.amount, on=me)
            c.world.effects.save(lasting)

        mirror = c.watch(
            DamageApplied, mirrored, until=When.ENCOUNTER, on=victim,
            label=f"{ref} mirror",
        )
        lasting.on_end.append(
            lambda: c.world.effects.end(mirror, "the disarray passed")
        )

    first = c.condition(
        Condition.DOMINATED, until=When.SAVE_ENDS, on=victim, escalate=deepen
    )
    if first is not None:
        rides(first)


@power(
    "m4941a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m4941a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m4941a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4941a3(c: Cast) -> None:
    c.teleport(8)
