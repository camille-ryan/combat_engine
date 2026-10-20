"""General feats, the tail of the psionic/warlock batch: the hand-of-blight
pacts, the three `f1028` riders, the eladrin and shadow-race runs, and a
short row of size and terrain feats.

Five shapes account for the file.

**The pact pairs (`f3424`-`f3429`).** Each prints a skill bonus *or* a
payout when a cursed enemy drops, plus an augment clause that spends the
warlock's fell might.

**Re-aimed twice, and the second name was wrong too.** It was
`dsl.use(augment=)` first; that arrived and turned out to settle a spend of
power points against a row declaring its own augments, which no power named
here does. Then `c.lend_augment(ref, clause)` -- and **that** is now
implemented and is still not this. Lending a clause is one thing; spending
a *resource other than power points* on an augment is another, and these
rows want the second. `c.augment_with(resource)` names it, and it is the
only gap left here: the resource itself exists now as `c.spend_charge` on a
key the owning row coins, which is what `c.fell_might()` had been standing
in for (#529). So the marker is down to one symbol, and that symbol is the
augment step rather than the pool.

The lesson is the one the component file states: a marker naming the
nearest-looking verb reports ready the moment that verb lands. Twice here.

The "Associated Powers" line is a column the row cannot read, which is
`feat.associated_powers`. So the half that can be said is said and the
augment half is `dropped`.

**The `f1028` riders (`f3432`, `f3434`, `f3435`).** All three read "when
you hit with an attack made using `f1028`", and `f1028` is itself marked
`c.as_melee(ref=)`: nothing turns a ranged power into a melee one for a
single use, so no attack is ever *made using* it and the trigger can never
be true. Marked with the same symbol rather than approximated as "any hit".

That symbol used to be `c.reach_of(power=)` and was wrong for all four --
it named no verb at all, and six rows carried it wanting three different
facilities. Reading a range is `c.reach(ref)` and always existed; one of
the six, `f1817`, turned out to need no new facility whatsoever.

**The shadow-race run (`f3456`-`f3463`).** `p2482` is the racial power by
ref, so "replace your racial power with this card" is `c.forbid` plus
`c.grant_row` and needs no marker. "Insubstantial **due to** `p2482`"
needed one until this pass and no longer does: an effect's label is the
ref of the row that laid it, so `c.suffering(p2482, include_self=True)`
answers which effect made the caster insubstantial. `c.is_` alone would
have counted the insubstantiality `f3459` and `f3460` lay as well.

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
from combat_engine.content.features.sorcerer import phase_of
from combat_engine.engine import (
    AT_WILL,
    CHA,
    EACH_OTHER,
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
from combat_engine.engine.dsl import get
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.query import light_level
from combat_engine.engine.types import Light

#: **Retired. `c.augment_with(resource)` never named a gap**, and this
#: comment argued for it three times -- first as `dsl.use(augment=)`,
#: then as `c.lend_augment(ref, clause)`, then as "a resource standing
#: in for power points". It is not standing in for anything:
#: `c.spend_charge` on `features.warlock.FELL` is the spend, `c.may` is
#: the decision, `c.declare` picks which bracketed feat applies, and
#: `p12887` had been the worked example of the same mechanic the whole
#: time. Six of the seven rows are written now, with the clause in the
#: power it names; the seventh waits on an empty column and says so.
#: #630. Kept as a note rather than deleted because each re-aiming made
#: these rows read ready the moment the newly named verb landed.
#: The "Associated Powers" line is a column no row can read.
ASSOCIATED = ("feat.associated_powers",)
#: The heroic half of a card's "Associated Powers" line, by the feat naming it.
#: Each card prints four more refs at paragon and epic and this build imports
#: none of them, so naming those would record refs that resolve to nothing --
#: #281. `ABILITY_SWAP` is gone: `c.rolls_with` exists and both rows that
#: wanted it say the sentence now.
_ASSOCIATED = {"f3427": ("p5919", "p1341"), "f3429": ("p1401", "p501")}
#: Trading away the extra damage an augment would have dealt.
FORGO = ("c.forgo_damage()",)
#: `f1028`'s own hold: a power's reach is header data and is never rewritten
#: for one use, so no attack is ever "made using" it.
#:
# **`REACH` is retired and this records why the constant is gone.** It held
# `c.as_melee(ref=)` for the three riders below, re-pointed there off
# `c.reach_of(power=)` -- a symbol six rows had shared for three different
# things, which is the "a marker names one gap" rule broken three ways at
# once. The verb it finally named was never built either: #614 landed the
# mechanism as a per-character **aiming** (`dsl.branches_for`) rather than a
# verb that rewrites a reach, `f1028` is written against it, and all three
# riders now test the aiming directly. The symbol is at zero rows.

#: A skill bonus that applies only in a named circumstance.
#: `f3447`'s two live gaps, named apart after #735 split. Opening a lock
#: is a printed standard action the engine does not offer (#786); sleight
#: of hand is Camille's deferral to the story engine (#787), because it
#: palms an unattended object and is judged by onlookers, neither of which
#: is on a board. The escape half of the same card already plays.
CIRCUMSTANCE = ("actions.open_lock()", "story.skill_use()")

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
        if eff.when is When.SAVE_ENDS and wanted & set(keywords_of(eff)):
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


def _while_insubstantial(c: Cast, fn, *, due_to: str = "") -> None:  # noqa: ANN001
    """"When you hit an enemy with an attack while you are insubstantial".

    Asked at the moment of the hit rather than when the trait is armed --
    the caster is almost never insubstantial at the start of the fight.

    `due_to` is the narrower printed form, "insubstantial due to your
    <ref>". An effect's label is the ref of the row that laid it and
    `c.suffering` matches on that label, so the one insubstantiality that
    counts is told from the two other rows in this file that lay one.
    """

    def on_hit(ev: Any) -> None:
        if ev.attacker != c.me or ev.target == c.me:
            return
        if not c.is_(Condition.INSUBSTANTIAL, on=c.me):
            return
        if due_to and c.me not in c.suffering(due_to, include_self=True):
            return
        fn(ev)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=c.me)


# -- the hand-of-blight pacts -----------------------------------------------


#: The weapon `f1028` names. Its group holds fourteen other things, so the
#: three riders below ask by ref for the reason `general_r._wielding` gives.
_F1028_WEAPON = "w3594"


def _through_an_offered_aiming(c: Cast, ev: Any) -> bool:
    """Was this hit made with the melee aiming `f1028` contributes?

    `f1028` offers a ranged sorcerer power a melee aiming rather than
    replacing its printed one (#614), so "an attack made **using** `f1028`"
    is an attack aimed through that extra index. `dsl.branches_for` puts the
    extras after the printed ones, so **an index past the printed count is
    by definition an aiming some feat contributed** -- and the branch rides
    the attack events as a plain attribute, the way `Moved.kind_` does.

    The rest of the test is `f1028`'s own conditions, so a *different*
    offered aiming does not trigger these riders: a ranged row of the
    sorcerer's own class, and the named weapon in hand.

    One residual ambiguity, recorded rather than engineered around:
    `f1239` offers a melee aiming to five named rows and two of them are
    sorcerer rows, so a character holding both feats has two cards offering
    an aiming to the same power. The attack made is identical either way --
    one melee aiming at the printed reach -- so the payout is the same
    whichever card the player credits, and no reading of the page
    distinguishes them.
    """
    from combat_engine.engine.components import Gear

    p = get(getattr(ev, "power", "") or "")
    if p is None or p.reach is None:
        return False
    if getattr(ev, "branch", 0) < len(p.branches):
        return False
    if p.cls != "sorcerer" or p.reach.kind != "ranged":
        return False
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.ref == _F1028_WEAPON for w in gear.held)


@power("f3424", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3424(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead become
    invisible to the target until the end of your next turn."

    **Written, and neither symbol it carried was the gap.** p12887's
    fell-might rider had never been written -- its own comment said the
    sorcerer-king rider "has no build to ask for", and that was false.
    With the rider written and offered through
    `c.instead_of("fell_might_damage")`, `c.pre_empt` replaces it. #507.

    **Invisible to one creature, not to the board.** `c.invisible(to=)` is
    the scoped form; a bare `c.invisible` would hide the warlock from
    everything, which is wider than the card by every other enemy on it.
    """
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def vanish(using: Cast) -> None:
        foe = using.target
        if foe is not None:
            using.invisible(on=using.me, to=foe, until=When.EONT)

    c.pre_empt("p12887", "fell_might_damage", vanish)


@power("f3425", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED,
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
    pending.

    **The augment marker is gone from this row too, and it was never its
    gap.** `c.augment_with(resource)` named nothing missing -- the spend is
    `c.spend_charge` on `features.warlock.FELL` and the other six of these
    feats are written (#630) -- so carrying it here said the clause was
    waiting on a verb when it is waiting on a column. One marker, one gap:
    with no Associated Powers list there is no power to write the clause
    into, which `feat.associated_powers` already says.
    """
    c.shift(3 + c.int_mod)


@power("f3426", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3426(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead daze the
    target until the end of your next turn." The sibling of f3424 and the
    same mechanism; see there for what unblocked it.
    """
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def reel(using: Cast) -> None:
        foe = using.target
        if foe is not None:
            using.dazed(on=foe, until=When.EONT)

    c.pre_empt("p12887", "fell_might_damage", reel)


@power("f3427", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop an enemy you have cursed to 0 hit points")
def f3427(c: Cast) -> None:
    """"Each enemy cursed by you" is every live enemy carrying my curse,
    which the one going down no longer is.

    **The declared trigger became a watch so the ability swap has somewhere
    to be laid.** A row with `on=Trigger(...)` runs its body only when the
    trigger fires, and the card's last sentence is a standing property of
    the character -- laid there it would arrive only after the first cursed
    enemy fell, which is every earlier roll too late. `turns.arm_traits_of`
    arms an `action=NONE` row with no `on=`, so this becomes a trait that
    lays the swap and watches for the drop. `ranger_b.f1309` is the same
    rewrite and `trigger=` keeps the card's own words either way.

    Free, as `c.watch` is, which is right here: the payout costs no action
    on the card. A row whose trigger costs an immediate wants
    `c.arm_trigger` instead.

    Only the attack half of "attack rolls and damage rolls" lands. The swap
    is recorded against the creature and `Attack.ability_for` reads it, so
    the roll is right; a damage line naming its modifier outright belongs to
    the associated row and is not this row's to rewrite. Not claimed as a
    gap here, because this row has said all it can.

    **The augment half is written, in the two powers rather than here.**
    "You can also expend your fell might to augment any power associated
    with this feat" is #550's convention: the clause is this feat's and the
    attack is the power's, so it lives in `p5919` and `p1341` under
    `shared.augmenting`, which settles the spend above the roll because the
    pact boon's card requires the decision before any attack roll. The
    marker it carried, `c.augment_with(resource)`, named nothing missing --
    `c.spend_charge` on `features.warlock.FELL` is the spend and `p12887`
    is the worked example. #630.

    Only the two heroic refs the Associated Powers line prints. The card
    names four more at paragon and epic and this build imports none of
    them, so gating on those would point at rows that resolve to nothing.
    """
    for ref in _ASSOCIATED["f3427"]:
        c.rolls_with(ref, CHA)

    def fell(ev: Dropped) -> None:
        if not by_me(c.world, c.me, ev) or not cursed_by_me(c.world, c.me, ev):
            return
        for foe in _cursed(c):
            c.penalty("attack", 2, on=foe, until=When.EONT)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me)


@power("f3428", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3428(c: Cast) -> None:
    """"Forgo the extra damage the augment would deal to instead immobilize
    the target until the end of your next turn." The sibling of f3424; see
    there for what unblocked it.
    """
    c.bonus("skill:history", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def root(using: Cast) -> None:
        foe = using.target
        if foe is not None:
            using.immobilized(on=foe, until=When.EONT)

    c.pre_empt("p12887", "fell_might_damage", root)


@power("f3429", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop an enemy you have cursed to 0 hit points")
def f3429(c: Cast) -> None:
    """The enemy picks, not the warlock, so the choice is put to it with
    `c.may(who=)` rather than taken with `c.choose`.

    Declared trigger turned into a watch for the same reason as `f3427`
    above, and the swap is the attack half only on the same reading.

    **The augment half is written, in the two powers rather than here.**
    #550's convention: the clause is this feat's and the attack is the
    power's, so it lives in `p1401` and `p501` as `shared.thunderclap`, gated by
    `shared.augmenting` -- which settles the spend above the roll, because
    the pact boon's card requires the decision before any attack roll. The
    marker this row carried, `c.augment_with(resource)`, named nothing
    missing: `c.spend_charge` on `features.warlock.FELL` is the spend and
    `p12887` is the worked example. #630.

    Only the two heroic refs the Associated Powers line prints. The card
    names four more at paragon and epic and this build imports none of
    them.

    `p1401` is named by `f3419` too, and both print `[Greater Pact]` -- so
    that body asks `c.declare` through `augmenting` and branches on which
    ref came back, never `c.feat`, which is true for every feat held and
    cannot say which is applying. #554.
    """
    for ref in _ASSOCIATED["f3429"]:
        c.rolls_with(ref, CHA)

    def fell(ev: Dropped) -> None:
        if not by_me(c.world, c.me, ev) or not cursed_by_me(c.world, c.me, ev):
            return
        for foe in _cursed(c):
            if c.may("fall prone", who=foe):
                c.prone(on=foe)
            else:
                c.weakened(on=foe, until=When.SONT)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me)


# -- the three `f1028` riders -----------------------------------------------


@power("f3432", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3432(c: Cast) -> None:
    """Two holds, either of which is fatal on its own: no attack is ever
    made *using* `f1028`, and nothing reports which phase is current, so
    all three branches of the payout are unreachable.

    **Re-aimed twice, and the second hold is gone.** It was
    `c.cosmic_phase()` first -- a symbol only this row named -- then
    `events.ShortRested`, on the reasoning that the phase is a state
    nothing keeps because `cf:sorcerer-f0s0` is picked at a rest that
    emits no event. That event landed and that feature is written:
    `features.sorcerer.phase_of` answers which phase, and all three
    branches of the payout have somewhere to read.

    **And that last hold is gone too, so this is written.** `f1028`
    contributes a melee *aiming* rather than rewriting a reach (#614), and
    the branch rides the hit -- so "an attack made using `f1028`" is a test
    and not a guess. Both holds this row carried are now readable, which is
    why all three branches of the payout are here.

    Worth recording why naming the *feature* was wrong both times a wave
    reached for it: a ref resolves against the registry, and
    `cf:sorcerer-f0s0` has always been declared -- so the marker read as
    arrived the moment anybody ran the tracker.

    The slide is "to a square adjacent to you", which is the narrowing that
    distinguishes it from the push: `c.slide` takes the destination, so the
    adjacency is asked for rather than hoped for.
    """
    me = c.me
    last = [-1]

    def pay(ev: Hit) -> None:
        if ev.attacker != me or last[0] == c.world.round:
            return
        if not _through_an_offered_aiming(c, ev):
            return
        here = phase_of(c)
        if not here:
            return
        last[0] = c.world.round
        if here == "sun":
            c.push(1, on=ev.target)
        elif here == "moon":
            c.slide(1, on=ev.target, toward=me)
        elif here == "stars":
            c.save()

    c.watch(Hit, pay, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3434", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3434(c: Cast) -> None:
    """Written: the trigger exists now, and the shift always was trivial.

    The note here said *"an attack made using `f1028` never happens, and a
    row declared on any hit instead would fire on every at-will in the
    fight"*. Both halves were right, and the first is no longer true:
    `f1028` contributes a melee **aiming** and the branch rides the hit, so
    "made using it" is a precise test rather than a guess. #614.

    The latch is by hand because `c.on_attack(once_per_round=)` watches
    `AttackDeclared` and this pays out on the **hit** -- which is what that
    verb's own docstring says was written out three times per class before
    it existed. The round number is the latch, not a one-shot: "once per
    round" comes back every round.
    """
    me = c.me
    last = [-1]

    def shift_away(ev: Hit) -> None:
        if ev.attacker != me or last[0] == c.world.round:
            return
        if not _through_an_offered_aiming(c, ev):
            return
        last[0] = c.world.round
        c.shift(1)

    c.watch(Hit, shift_away, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3435", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("dsl.Power.energy_types",))
def f3435(c: Cast) -> None:
    """One hold left, and the missing trigger is no longer it.

    "Same missing trigger as `f3434`" was the first half of this note and is
    now false: `f1028` contributes a melee aiming, the branch rides the hit,
    and `_through_an_offered_aiming` above is the test both `f3434` and
    `f3432` are written on. #614.

    So the remaining hold is the second one alone, and it is unchanged.
    Re-aimed: it was never a blow of two types at once --
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
    if gear is None or not any(w.ref == "w3610" for w in gear.held):
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
       todo=("warlock.boon_instead_of()",),
       trigger="you drop an enemy you have cursed to 0 hit points",
       on=Trigger(Dropped, both(by_me, cursed_by_me),
                  "you drop an enemy you have cursed"))
def f3444(c: Cast) -> None:
    """Hands back the racial power in place of the pact boon.

    **Re-aimed, and the payout is written.** Two of the three holds were
    stale. The spec names the racial power by ref -- `p1449`, the same
    row `f3439` and `f3446` already spend and read -- so there is nothing
    to look up, and `c.restore_use` is ref-agnostic: it reaches the
    `Powers` store, which does not care that the row is racial. What is
    genuinely missing is the price. "Instead of gaining your normal pact
    boon" suppresses whichever pact the warlock took -- the card names no
    one of them -- and nothing announces a pact boon or stands in its
    way, so this row is free where the card charges for it.

    **The gap is a door in the boon's own body, not a missing mechanism,
    and the old symbol said otherwise.** "Nothing announces a pact boon" is
    false. The boons are declared: `cf:warlock-f1`'s own watch pays three
    legs inline, `cf:warlock-f1s4` pays a fourth, `cf:warlock-f1c10` is the
    star pact's card and `p16254` the remaining leg's.

    What is missing is that **none of those payouts asks**.
    `c.pre_empt(ref, what, clause)` is the registration and this row is one
    of its callers; the read has to happen where the boon is paid.
    `c.instead_of` cannot do it there -- it needs a non-zero `c.variant`,
    which `dsl.use` settles from a chosen menu entry, and three of these
    legs pay inside a `c.watch` callback where `variant` is 0 for ever.

    `c.instead_of_now` is written for exactly that shape and says so: *"for
    a clause that fires inside a watcher the row installed itself rather
    than from a body the menu reached"*, with the invoker's covenant
    manifestation as its worked case. It settles the objection too -- a
    question inside a watcher is invisible to `policy/`, which is
    acceptable **because a boon is a passive**: the AI never chose the
    bargain and cannot be asked to weigh it differently.

    `cf:warlock-f1c10` is the one exception and takes plain
    `c.instead_of`, because it carries a declared trigger and so is offered
    by the dispatcher -- the distinction that verb's own docstring draws
    with `rt:r24-t0`.

    So the symbol names a content door in `features/warlock.py` rather than
    a `Cast` verb, because that is where the work is. #551's verdict, read
    down to the mechanism. #641.


    `ENCOUNTER` on a triggered trait is the card's own "once per
    encounter" and not the #210 accident. "If you have already used it"
    is the gate: `c.restore_use` would answer False anyway, but asking
    first keeps the choice off the player when there is nothing to
    choose."""
    if "p1449" not in c.expended(on=c.me):
        return
    if c.may("regain p1449 instead of the pact boon"):
        c.restore_use("p1449")


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
       reach=PERSONAL, target=SELF, dropped=CIRCUMSTANCE)
def f3447(c: Cast) -> None:
    """The escape half plays -- escaping a grab is a move action the engine
    offers and rolls, Acrobatics against the grabber's Reflex or Athletics
    against its Fortitude. Restraints other than a grab are not a hold
    anything rolls against.

    **Re-aimed three times, and only the third reading is about the right
    thing.** It was `c.check(circumstance=)`, then `c.skill_circumstance()`
    -- both of which said the gap was that a check cannot be told what it is
    for. The printed rules say otherwise: opening a lock and sleight of hand
    are each a **standard action in combat**, adjacent to the lock or to the
    object. They are named actions, not purposes, and the engine offers
    neither.

    So the Thievery half splits, on Camille's call (#735):

    * **opening locks** is `actions.open_lock()`, and #786 says the honest
      caveat out loud -- the action is buildable, but no square carries a
      lock, so it would be legal nowhere until terrain grows one;
    * **sleight of hand** goes to the story engine (#787), because it palms
      an unattended object and is judged by onlookers, and neither of those
      is on a board.

    The +4 has to be **per check** either way. A blanket Thievery bonus
    would raise every use of the skill, which is the fault this note has
    warned about since its first version and the one thing all three
    readings agreed on."""
    c.bonus("escape", 4, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3448", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3448(c: Cast) -> None:
    """+4 in one sort of settlement, +2 against one sort of person.

    Inert on the **circumstance**: both bonuses are gated on where the check
    is made and on who it is made against, and a board is neither a
    settlement nor populated by that sort of person. The skills themselves
    are rolled -- `bluff` 18 times in this tree -- so "no combat consequence
    at all" was the right verdict reached through a false premise. #691."""


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
       target=EACH_OTHER, group=CHANNEL_DIVINITY,
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
       reach=PERSONAL, target=SELF)
def f3456(c: Cast) -> None:
    """"Insubstantial due to your `p2482`" is narrower than insubstantial,
    and the narrowing is sayable: the effect `p2482` lays is labelled with
    its own ref, so `c.suffering` tells it from the insubstantiality
    `f3459` and `f3460` lay on the same creature."""
    c.bonus("skill:stealth", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    _while_insubstantial(c, lambda ev: c.prone(on=ev.target),
                         due_to=SHADOW_JAUNT)


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
       reach=PERSONAL, target=SELF)
def f3458(c: Cast) -> None:
    """"Until the end of its next turn" is the enemy's clock, not mine.

    Same `due_to` narrowing as `f3456`, and for the same reason."""
    c.bonus("skill:arcana", 2, kind="feat", on=c.me, until=When.ENCOUNTER)

    def rider(ev: Any) -> None:
        c.slide(1, on=ev.target)
        c.penalty("attack", 2, on=ev.target, until=When.EOTNT)

    _while_insubstantial(c, rider, due_to=SHADOW_JAUNT)


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
       reach=PERSONAL, target=SELF)
def f3462(c: Cast) -> None:
    """Darkvision 5 -- a printed range, so it is passed."""
    c.darkvision(5)
    c.bonus("skill:stealth", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.forbid(SHADOW_JAUNT, on=c.me, until=When.ENCOUNTER)
    c.grant_row("f3462b", on=c.me, until=When.ENCOUNTER)


@power("f3462b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
)
def f3462b(c: Cast) -> None:
    """Five squares, or ten to a square that is dim or dark.

    **"How brightly a square is lit is not something the board records"
    was the note and is wrong** -- `query.light_level` reads `Grid.light`
    and any darkening zone. `c.teleport(into=)` carries the requirement.
    #685.

    **The longer hop is tried first and the plain one is the fallback**,
    which is what "you can **instead** teleport to that square" means in
    play: the choice is only ever offered when a qualifying square is in
    range, and taking it is never worse -- it is the same action for twice
    the distance. `c.teleport` returns False when nothing qualifies, which
    makes the fallback one line rather than a scan of its own."""
    dark = light_level
    if not c.teleport(
        10, into=lambda sq: dark(c.world, sq) is not Light.BRIGHT
    ):
        c.teleport(5)


def _f3463_vanish(using: Cast) -> None:
    """Out of play until the start of your next turn, instead of a teleport.

    Returning "to the square you last occupied" needs no code: a creature
    removed from play does not move, so the square is still its own.
    """
    using.condition(Condition.REMOVED, on=using.me, until=When.SONT)


@power("f3463", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,)
def f3463(c: Cast) -> None:
    """Removed from play instead of `p2482`'s teleport, back next turn.

    **Rewritten from a watcher**, which fired on `PowerUsed` and let the
    teleport it is meant to replace happen anyway. The substitution is the
    whole of this row, so hanging it anywhere else made the feat strictly
    better than printed.
    """
    c.pre_empt("p2482", "teleport", _f3463_vanish)
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
       reach=PERSONAL, target=SELF, todo=("c.prone(save_ends=)",))
def f3470(c: Cast) -> None:
    """**Re-aimed: the hook exists, the moment does not.**

    `c.on_save()` was the wrong name for this. A saving throw *is*
    answerable -- `Trigger(SavingThrow, ...)` is declared and `i3556p1`
    ships on it -- so nothing is missing on that side. What is missing is
    the throw itself: `c.prone` lays prone on a clock and never as
    something a save can avoid, so `SavingThrow.against` never names it
    and there is no success to answer. The symbol is the parameter that
    would make one happen."""


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
       reach=PERSONAL, target=SELF)
def f3476(c: Cast) -> None:
    """A racial bonus, not a feat one -- the card prints the word. The
    low-light vision is the other half and is written."""
    c.low_light()
    c.bonus("skill:dungeoneering", 2, kind="racial", on=c.me,
            until=When.ENCOUNTER)
