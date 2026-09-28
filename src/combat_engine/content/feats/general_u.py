"""General feats, the tail of the psionic/warlock batch: the hand-of-blight
pacts, the three `f1028` riders, the eladrin and shadow-race runs, and a
short row of size and terrain feats.

Five shapes account for the file.

**The pact pairs (`f3424`-`f3429`).** Each prints a skill bonus *or* a
payout when a cursed enemy drops, plus an augment clause that spends the
warlock's fell might. Nothing augments a power from outside its own card
-- `c.lend_augment(ref, clause)`, re-aimed off `dsl.use(augment=)` once
that arrived and turned out to be a different thing: it settles a spend of
power points against a row that declares its own augments, and no power
named here prints an Augment line. The "Associated Powers" line is a
column the row cannot read, which is `feat.associated_powers`. So the half
that can be said is said and the augment half is `dropped`.

**The `f1028` riders (`f3432`, `f3434`, `f3435`).** All three read "when
you hit with an attack made using `f1028`", and `f1028` is itself marked
`c.reach_of(power=)`: nothing rewrites a power's reach for one use, so
no attack is ever *made using* it and the trigger can never be true.
Marked with the same symbol rather than approximated as "any hit".

**The shadow-race run (`f3456`-`f3463`).** `p2482` is the racial power by
ref, so "replace your racial power with this card" is `c.forbid` plus
`c.grant_row` and needs no marker. What three of them do need is
*which effect* made the caster insubstantial: `c.is_` answers whether,
never why, and `c.effects_on()` is the symbol for the difference.

**A `when=` gate may only read a key its own context carries.** The save
context carries `conditions`, `keywords`, `label` and `dtype`; the damage
context carries `power`. Both are used here and nothing else is.

**A triggered `action=NONE` row spends a use every time it fires**, so
those are `AT_WILL`; a trait armed once at the start of the fight is
`ENCOUNTER`, as everywhere else in this directory.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AT_WILL,
    CHA,
    EACH_CREATURE,
    ENCOUNTER,
    FREE,
    MOVE,
    PERSONAL,
    SELF,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Position,
    PowerUsed,
    SecondWind,
    Size,
    Trigger,
    TurnStart,
    When,
    Window,
    about_me,
    both,
    by_me,
    cursed_by_me,
    enemy_within,
    hits_me,
    power,
    spread,
)
from combat_engine.engine.durations import keywords_of

#: Nothing augments another row's card from outside it.
#:
#: **Re-aimed.** `dsl.use(augment=)` arrived and is not what these want.
#: It settles a spend of *power points* against a row that declares its
#: own augments, before targeting. These six spend the warlock's fell
#: might -- a different currency entirely -- on a power whose card prints
#: no Augment line at all, which is an offer added to another row from
#: outside it. Same symbol the psionic aspect dailies name.
AUGMENT = ("c.lend_augment(ref, clause)",)
#: The "Associated Powers" line is a column no row can read.
ASSOCIATED = ("feat.associated_powers",)
#: "You can use Charisma instead of Constitution" for a named list.
ABILITY_SWAP = ("c.ability_for(ref)",)
#: Trading away the extra damage an augment would have dealt.
FORGO = ("c.forgo_damage()",)
#: `f1028`'s own hold: a power's reach is header data and is never rewritten
#: for one use, so no attack is ever "made using" it.
REACH = ("c.reach_of(power=)",)
#: Which effect put a condition on a creature. `c.is_` says whether, not why.
WHY = ("c.effects_on()",)
#: A skill bonus that applies only in a named circumstance.
CIRCUMSTANCE = ("c.skill_circumstance()",)

#: Large and up, for the three feats that turn on a big enemy.
BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)
#: The heal half of the artificer's infusion feature, by ref.
HEAL_INFUSION = "p4128"
#: The shadow race's racial power, named by ref in every prerequisite here.
SHADOW_JAUNT = "p2482"


def _used(ref: str):  # noqa: ANN202
    """"When you use <ref>". `by_me` reads `actor` off events that have one
    and `PowerUsed` does, but it also answers True for a use by anybody on
    my side, which is not what any of these print."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _save_against(c: Cast, who: int, *words: Keyword, bonus: int = 0) -> bool:
    """One saving throw against a hold whose source row printed one of
    these keywords.

    `c.save(against=)` picks by label fragment and a keyword is not one --
    but an effect's label is the ref of the row that laid it, so
    `durations.keywords_of` names the hold to ask for. Without it the throw
    takes whichever save-ends effect comes first, which may be a burn.
    """
    wanted = set(words)
    for eff in c.world.effects.of(who):
        # `keywords_of` answers a *tuple* whatever its annotation says.
        if eff.when is When.SAVE_ENDS and wanted & set(keywords_of(eff.label)):
            return c.save(on=who, bonus=bonus, against=eff.label)
    return False


def _best(c: Cast) -> int:
    """"Your highest ability modifier". The header can only name one, so the
    roll carries the difference as `plus=`."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _beside(c: Cast, who: int) -> Any:
    """An unoccupied square next to a creature, for a teleport that names its
    destination rather than leaving it to the decider."""
    pos = c.world.get(who, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq != pos.square and not c.in_squares([sq]):
            return sq
    return None


def _cursed(c: Cast) -> list[int]:
    """Every enemy under this caster's curse."""
    return [foe for foe in c.enemies() if c.cursed(on=foe)]


def _while_insubstantial(c: Cast, fn) -> None:  # noqa: ANN001
    """"When you hit an enemy with an attack while you are insubstantial".

    Asked at the moment of the hit rather than when the trait is armed --
    the caster is almost never insubstantial at the start of the fight.
    """

    def on_hit(ev: Any) -> None:
        if ev.attacker != c.me or ev.target == c.me:
            return
        if not c.is_(Condition.INSUBSTANTIAL, on=c.me):
            return
        fn(ev)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=c.me)


# -- the hand-of-blight pacts -----------------------------------------------


@power("f3424", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AUGMENT + FORGO)
def f3424(c: Cast) -> None:
    """The skill bonus is the whole of the half that can be said: the
    invisibility is bought by giving up an augment's extra damage, and
    neither the augment nor the trade has anything to hang on."""
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f3425", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AUGMENT + ASSOCIATED,
       trigger="you drop an enemy you have cursed to 0 hit points",
       on=Trigger(Dropped, both(by_me, cursed_by_me),
                  "you drop an enemy you have cursed"))
def f3425(c: Cast) -> None:
    """`Dropped` carries `source` as well as `actor`, so `by_me` reads the
    killer and `cursed_by_me` the creature going down -- which is the two
    halves of the printed sentence and the reason both are declared.

    This is the one of the three whose page prints **no** Associated
    Powers list at all -- its two siblings print one and it arrived as
    refs -- so `feat.associated_powers` here is permanent rather than
    pending."""
    c.shift(3 + c.int_mod)


@power("f3426", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AUGMENT + FORGO)
def f3426(c: Cast) -> None:
    """Skill bonus only; the daze is an augment's traded damage."""
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f3427", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=AUGMENT + ABILITY_SWAP,
       trigger="you drop an enemy you have cursed to 0 hit points",
       on=Trigger(Dropped, both(by_me, cursed_by_me),
                  "you drop an enemy you have cursed"))
def f3427(c: Cast) -> None:
    """"Each enemy cursed by you" is every live enemy carrying my curse,
    which the one going down no longer is.

    `feat.associated_powers` is gone from the marker: the card's list is
    refs now, and both clauses that wanted it are held by something else
    -- one by the augment nothing lends, one by the ability swap."""
    for foe in _cursed(c):
        c.penalty("attack", 2, on=foe, until=When.EONT)


@power("f3428", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AUGMENT + FORGO)
def f3428(c: Cast) -> None:
    """Skill bonus only; the immobilisation is an augment's traded damage."""
    c.bonus("skill:history", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f3429", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=AUGMENT + ABILITY_SWAP,
       trigger="you drop an enemy you have cursed to 0 hit points",
       on=Trigger(Dropped, both(by_me, cursed_by_me),
                  "you drop an enemy you have cursed"))
def f3429(c: Cast) -> None:
    """The enemy picks, not the warlock, so the choice is put to it with
    `c.may(who=)` rather than taken with `c.choose`.

    `feat.associated_powers` is gone from the marker for the same reason
    as `f3427`: the list is refs now, and the clauses reading it are held
    by the augment and the ability swap instead."""
    for foe in _cursed(c):
        if c.may("fall prone", who=foe):
            c.prone(on=foe)
        else:
            c.weakened(on=foe, until=When.SONT)


# -- the three `f1028` riders -----------------------------------------------


@power("f3432", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*REACH, "c.cosmic_phase()"))
def f3432(c: Cast) -> None:
    """Two holds, either of which is fatal on its own: no attack is ever
    made *using* `f1028`, and nothing reports which phase is current, so
    all three branches of the payout are unreachable."""


@power("f3434", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REACH)
def f3434(c: Cast) -> None:
    """The shift is trivial; the trigger is not. `f1028` turns a ranged
    power into a melee one and nothing rewrites a reach for one use, so
    an attack "made using" it never happens and a row declared on any hit
    instead would fire on every at-will in the fight."""


@power("f3435", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*REACH, "dsl.Power.energy_types"))
def f3435(c: Cast) -> None:
    """Same missing trigger as `f3434`, and a second hold beside it.

    Re-aimed: the second hold was never a blow of two types at once --
    this is "roll twice and choose **either** result", which `c.choose`
    over damage types already says (`psion_b.f3307` does exactly that).
    What is missing is the list to choose from. A power "that has a
    variable energy type" declares no such set anywhere in the header,
    and `c.element` answers a build's single sworn element, which is a
    different question.
    """


# -- eladrin ----------------------------------------------------------------


@power("f3438", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3438(c: Cast) -> None:
    """Two skills chosen from a class list, and no combat consequence
    whichever two they are. Deliberately inert, not unwritten."""


@power("f3439", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       )
def f3439(c: Cast) -> None:
    """Moves the conjuration or the summoned creature, whichever is to
    hand; the printed size limits are checked here because both are real
    and neither is expensive.

    Both markers are gone. The racial power is `p1449`, which the spec
    names and the tree declares, and `c.expend_row` spends its use
    without running it -- which is exactly the card, since the teleport
    that happens is this row's and not p1449's.
    """
    if not c.expend_row("p1449"):
        return
    for who in c.servants():
        if c.distance(to=who) <= 5 and c.size_of(on=who) not in BIG:
            c.teleport(5, who=who)
            return
    for thing in c.conjurations(within=5, side="ally"):
        if c.move_zone(thing, 5):
            return


@power("f3440", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your healing infusion",
       on=Trigger(PowerUsed, _used(HEAL_INFUSION), "you use that infusion"))
def f3440(c: Cast) -> None:
    """Declared on `PowerUsed` because the targets are chosen before the
    body runs, which is the one thing that event can be trusted for.

    "A single charm or fear effect" plays now: the keywords belong to the
    row that laid the hold and an effect's label is that row's ref, so
    `keywords_of` finds the right hold and `c.save(against=)` rolls
    against it by label. "Constitution **or** Wisdom" is the player's
    choice and the better of the two is always the one to take.
    """
    bonus = max(c.con_mod, c.wis_mod)
    for who in c.trigger.targets:
        _save_against(c, who, Keyword.CHARM, Keyword.FEAR, bonus=bonus)


@power("f3442", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3442(c: Cast) -> None:
    """A plain "+1 bonus" with no type word, so untyped.

    The weapon is asked once, when the trait is armed: the attack context
    carries `power` and `hand` and not the weapon in it, and a warlock who
    swaps blades mid-fight is not a case this card contemplates.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(w.ref == "w:longsword" for w in gear.held):
        return
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx["power"] == "p7402")


@power("f3443", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3443(c: Cast) -> None:
    """The damage context carries `power`, which is the whole of the gate."""
    if c.int_mod > 0:
        c.bonus("damage", c.int_mod, kind="feat", on=c.me,
                until=When.ENCOUNTER,
                when=lambda ctx: ctx["power"] == "p1333")


@power("f3444", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.racial_row()", "c.restore_use(racial)", "c.on_pact_boon()"))
def f3444(c: Cast) -> None:
    """Hands back the racial power in place of the pact boon. Three holds
    and the whole row is one of them: the racial power has no ref to
    restore, `c.restore_use` cannot be pointed at a racial row, and
    nothing announces or suppresses a pact boon."""


@power("f3446", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449 with your familiar within 10 squares",
       on=Trigger(PowerUsed, _used("p1449"), "you use that racial power"))
def f3446(c: Cast) -> None:
    """`PowerUsed` rather than `PowerResolved` on purpose: "your familiar
    is within 10 squares of you" is asked of where the caster is
    standing *when the power is used*, and `p1449` is the teleport
    itself -- measured after it, the range would be taken from the
    destination and a familiar left behind would qualify."""
    fam = c.familiar()
    if fam is not None and c.distance(to=fam) <= 10:
        c.teleport(5, who=fam)


# -- the freed-slave run ----------------------------------------------------


@power("f3447", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.check(circumstance=)",))
def f3447(c: Cast) -> None:
    """The escape half plays. The Thievery half is narrowed to opening
    locks and sleight of hand, and a check's circumstance is not
    sayable -- a blanket bonus to the skill would raise every use of it
    -- so that clause is dropped rather than widened. Restraints other
    than a grab are not a hold anything rolls against."""
    c.bonus("escape", 4, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3448", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3448(c: Cast) -> None:
    """Social checks in a named sort of place and against a named sort of
    person. No combat consequence at all."""


@power("f3449", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3449(c: Cast) -> None:
    """The save context carries the effect's `conditions`, which is exactly
    what "against effects that dominate, immobilize, or slow" narrows on --
    the label would be whatever ref laid it."""
    named = frozenset(
        {Condition.DOMINATED, Condition.IMMOBILIZED, Condition.SLOWED}
    )
    c.bonus("save", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx["conditions"] & named))


@power("f3450", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3450(c: Cast) -> None:
    """Two knowledge skills and a language."""


@power("f3451", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3451(c: Cast) -> None:
    """A standing modifier and a triggered half, so the trigger is armed
    with `c.watch` from inside the trait rather than declared -- a row
    given `on=` never lays its modifiers at all.

    The resistance is taken off the blow before it is moved: the damage is
    the caster's either way and `c.reduce` then `c.absorb` comes to the
    same number as absorbing it and resisting 5 of it.
    """
    c.bonus("save", 2, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: Keyword.CHARM in ctx["keywords"])

    def shield(ev: DamageRolled) -> None:
        if ev.source != c.me or ev.target == c.me:
            return
        if ev.target not in c.allies() or not c.may("take the damage"):
            return
        c.reduce(5, ev)
        c.absorb(ev, on=c.me)

    c.watch(DamageRolled, shield, until=When.ENCOUNTER, window=Window.BEFORE,
            on=c.me, label=f"{c.ref} takes it instead")


@power("f3452", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.obscure(level=)",))
def f3452(c: Cast) -> None:
    """Downgrades total concealment to ordinary concealment. `c.conceal`
    lays concealment on a creature and has no notion of a level on the
    board to step down from."""


# -- the channel divinity pair ----------------------------------------------


@power("f3454", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3454(c: Cast) -> None:
    """Hands over f3454b, which is the whole of the feat."""
    c.grant_row("f3454b", on=c.me, until=When.ENCOUNTER)


@power("f3454b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=CloseBurst(2),
       target=EACH_CREATURE, group=CHANNEL_DIVINITY,
       keywords=[Keyword.DIVINE, Keyword.FEAR, Keyword.IMPLEMENT],
       attack=Attack(CHA, vs=WILL),
       trigger="an enemy within 2 squares of you damages you with an attack",
       on=Trigger(Hit, both(hits_me, enemy_within(2)),
                  "an enemy within 2 squares hits you"))
def f3454b(c: Cast) -> None:
    """"Your highest ability" -- the header names one and the roll carries
    the difference as `plus=`.

    The blindness ends itself: the rider watches damage landing on this
    target and `c.cure` takes the condition off, which is the printed
    "the blindness ends" without needing to hold the effect.
    """
    if not c.strike(plus=_best(c) - c.cha_mod):
        return
    foe = c.target
    if foe is None or c.blinded(until=When.SONT) is None:
        return

    def ends(ev: DamageApplied) -> None:
        if ev.target != foe or ev.amount <= 0:
            return
        c.cure(Condition.BLINDED, on=foe)
        c.slide(3, on=foe)

    c.watch(DamageApplied, ends, until=When.SONT, on=c.me, once=True,
            label=f"{c.ref} blindness ends")


# -- the shadow race --------------------------------------------------------


@power("f3456", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=WHY)
def f3456(c: Cast) -> None:
    """"Insubstantial due to your shadow jaunt" is narrower than
    insubstantial: `c.is_` answers whether the condition is on, never
    which effect put it there."""
    c.bonus("skill:stealth", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    _while_insubstantial(c, lambda ev: c.prone(on=ev.target))


@power("f3457", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3457(c: Cast) -> None:
    """This one prints no "due to" clause, so plain insubstantial is the
    whole condition and nothing is dropped."""
    c.bonus("skill:intimidate", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def rider(ev: Any) -> None:
        c.push(2, on=ev.target)
        c.slowed(on=ev.target, until=When.EONT)

    _while_insubstantial(c, rider)


@power("f3458", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=WHY)
def f3458(c: Cast) -> None:
    """"Until the end of its next turn" is the enemy's clock, not mine."""
    c.bonus("skill:arcana", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def rider(ev: Any) -> None:
        c.slide(1, on=ev.target)
        c.penalty("attack", 2, on=ev.target, until=When.EOTNT)

    _while_insubstantial(c, rider)


@power("f3459", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3459(c: Cast) -> None:
    """Unexpended is the test, so the row has to be known and not spent."""
    if c.knows("p2482") is None or "p2482" in c.expended(on=c.me):
        return
    c.insubstantial(on=c.me, until=When.SONT)


@power("f3460", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3460(c: Cast) -> None:
    """"Replace your racial power with this card" is `c.forbid` and
    `c.grant_row` together -- the racial power is named by ref in the
    prerequisite, so neither half needs a marker."""
    c.bonus("skill:intimidate", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.forbid(SHADOW_JAUNT, on=c.me, until=When.ENCOUNTER)
    c.grant_row("f3460b", on=c.me, until=When.ENCOUNTER)

    def on_crit(ev: Hit) -> None:
        if ev.target == c.me and ev.critical:
            c.insubstantial(on=c.me, until=When.EONT)

    c.watch(Hit, on_crit, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} after a critical")


@power("f3460b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       keywords=[Keyword.TELEPORTATION],
       trigger="an enemy within 3 squares of you damages you with an attack",
       on=Trigger(Hit, both(hits_me, enemy_within(3)),
                  "an enemy within 3 squares hits you"))
def f3460b(c: Cast) -> None:
    """The destination is named outright, so `c.teleport(to=)` takes the
    square rather than leaving it to the decider, which would happily put
    the caster nowhere near the creature it means to close with."""
    foe = c.trigger.attacker
    square = _beside(c, foe)
    if square is not None:
        c.teleport(0, to=square)
    c.grants_advantage(on=foe, to=c.me, until=When.EONT)


@power("f3462", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.darkvision()",))
def f3462(c: Cast) -> None:
    """The swap is writable; the sight is not -- darkvision is not a sense
    the engine grants."""
    c.bonus("skill:stealth", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.forbid(SHADOW_JAUNT, on=c.me, until=When.ENCOUNTER)
    c.grant_row("f3462b", on=c.me, until=When.ENCOUNTER)


@power("f3462b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       dropped=("c.light()",))
def f3462b(c: Cast) -> None:
    """The longer hop to a dark square is dropped: how brightly a square is
    lit is not something the board records."""
    c.teleport(5)


@power("f3463", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.forgo_teleport()",),
       trigger="you use your shadow jaunt",
       on=Trigger(PowerUsed, _used(SHADOW_JAUNT), "you use that power"))
def f3463(c: Cast) -> None:
    """Removal from play is `Condition.REMOVED` on the caster's own clock,
    and returning "to the square you last occupied" is then free -- a
    creature removed from play does not move.

    The teleport it is meant to replace still happens: `PowerUsed` is
    announced before the body runs and is not a decision anything can
    stop, so the substitution is the dropped half.
    """
    c.condition(Condition.REMOVED, on=c.me, until=When.SONT)


# -- fighting something bigger ----------------------------------------------


@power("f3464", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3464(c: Cast) -> None:
    """Who is standing beside whom changes every round, so the trait
    re-asks at the top of each turn rather than answering once when it is
    armed. The grant is the caster's alone, not the party's."""

    def scan(ev: Any = None) -> None:
        for foe in c.enemies():
            if c.size_of(on=foe) not in BIG or not c.adjacent_to(foe, c.me):
                continue
            if any(a != c.me and c.adjacent_to(foe, a) for a in c.allies()):
                c.grants_advantage(on=foe, to=c.me, until=When.EONT)

    scan()
    c.watch(TurnStart, scan, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} beside a big one")


@power("f3467", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3467(c: Cast) -> None:
    """`c.damage` maxes its dice on a critical, which is the whole point of
    a crit rider, so the extra die is rolled first and applied flat."""

    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        if c.size_of(on=ev.target) in BIG:
            c.flat(c.roll("1d6"), on=ev.target)

    c.watch(Hit, on_crit, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} critical against a big one")


@power("f3470", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_save()",))
def f3470(c: Cast) -> None:
    """Prone is applied on the encounter clock and is never saved against,
    and `SavingThrow.against` is the label of whatever effect is being
    shaken off -- so "a saving throw to avoid being knocked prone" is a
    moment that does not exist to answer."""


# -- the small standing ones ------------------------------------------------


@power("f3471", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3471(c: Cast) -> None:
    """The 11th- and 21st-level steps are out of scope; the heroic number
    is the one written."""
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)


@power("f3472", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3472(c: Cast) -> None:
    c.bonus("speed", 1, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f3475", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3475(c: Cast) -> None:
    """`c.ignores_difficult` takes one sort of ground at a time and the
    parenthesis names three."""
    c.ignores_difficult("rubble", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("stone", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("earth", on=c.me, until=When.ENCOUNTER)


@power("f3476", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.low_light()",))
def f3476(c: Cast) -> None:
    """A racial bonus, not a feat one -- the card prints the word."""
    c.bonus("skill:dungeoneering", 2, kind="racial", on=c.me,
            until=When.ENCOUNTER)
