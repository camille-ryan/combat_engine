"""What more than one warlock file needs.

`_backlash` was written out twice, byte for byte, in `level_1_b.py` and
`level_9_b.py`. Five refs in each file call it.
"""

from __future__ import annotations

from combat_engine.content.features.warlock import FELL
from combat_engine.engine import (
    DEFENCES,
    Cast,
    DamageType,
    Keyword,
    When,
)

#: The bracketed category the `cf:warlock-f1s4` feats print. A rules word,
#: not a printed name -- the same kind of vocabulary as a keyword, and a
#: column in `game.db` since #557. The first draft of this comment named
#: the pact instead of its ref and `leaks.py` caught it, which is tier 2 of
#: #447 and the half that is worth fixing on sight.
GREATER_PACT = "greater pact"


def augmenting(c: Cast, *feats: str) -> str:
    """Which `[Greater Pact]` feat is paying for this use, or `""`.

    Six of these feats print *"you can also expend your fell might to
    augment any power associated with this feat. When you hit an enemy with
    an associated power augmented by this feat, <effect>"* -- and the
    effect is the feat's while the attack is this row's, so #550's
    convention puts the clause here and this is the gate it reads. #630.

    Three things in one call, in the order the cards impose:

    * **Which feat**, through `c.declare`, because the category is
      bracketed and the rule is one feat of a category per use. Two of
      these feats name the same power, so the body cannot ask `c.feat` --
      that is true for every feat held and cannot say which is applying.
    * **Whether to spend**, through `c.may`. The augment is optional and
      the boon is one charge a fight shared with `p12887`, which is a real
      decision rather than a free rider.
    * **Whether the charge was there**, through `c.spend_charge`, whose
      False *is* the printed "if you spend" on every card of this shape.

    **Settled before the attack roll and memoised for the whole use**, both
    for the same printed reason `p12887` quotes: *"you must decide whether
    or not to spend your fell might when you choose to use a power, before
    you make any attack rolls or apply any of that power's effects."* Asked
    after the roll it would let a player buy the clause only on hits; asked
    again per target it would charge a two-target row twice and give the
    second target nothing. `dsl.use` builds one `Cast` per use, which is
    the unit the rule names, so the memo lives there -- the same place
    `augment()` keeps its own spend for the same reason.
    """
    held = getattr(c, "greater_pact", None)
    if held is not None:
        return held
    picked = c.declare(GREATER_PACT, *feats)
    paid = bool(
        picked and c.may(f"{picked}: spend the boon") and c.spend_charge(FELL)
    )
    c.greater_pact = picked if paid else ""
    return c.greater_pact


def backlash(c: Cast) -> None:
    """The Miss line several of these share: pay psychic damage for a bonus.

    "You do not expend this power" is the half that is still not said.
    Nothing gave a use back when this was written, so what is here is the
    price and the bonus it buys against the same target.
    """
    if not c.may("take the backlash", who=c.me):
        return
    c.flat(5 + c.level // 2, dtype=DamageType.PSYCHIC, on=c.me)
    c.bonus("attack", 4, on=c.me, kind="power", until=When.EONT, once=True)


def unnerve(c: Cast) -> None:
    """`f3419`'s augment: the bystanders flinch and the power turns fearful.

    *"Each enemy adjacent to the target takes a -2 penalty to attack rolls
    until the end of your next turn. The triggering power gains the fear
    keyword if it doesn't have it already."* Written once here because the
    feat names two powers and they live in different files.

    **"Adjacent to the target" excludes the target**, which `c.within(1,
    of=…)` returns at distance 0, so it comes out by name. The same step
    `p1341`'s own splash takes four lines further down its body.

    The keyword arrives **on the hit**, where the card puts it -- both of
    its sentences sit under "when you hit an enemy". That is after the roll
    this use made, so for this use it is a label rather than a lever; it is
    written as printed rather than moved above the strike, where it would
    be a different clause. `c.counts_as_keyword` already answers "if it
    doesn't have it already": `p1401` prints fear and `p1462` does not, and
    the call is the same for both.
    """
    foe = c.target
    if foe is not None:
        for other in c.within(1, of=foe, side="enemy"):
            if other != foe:
                c.penalty("attack", 2, on=other, until=When.EONT)
    c.counts_as_keyword(c.ref, Keyword.FEAR, on=c.me, until=When.ENCOUNTER)


def rally(c: Cast) -> None:
    """`f3417`'s augment: the allies beside the target step or brace.

    *"Each ally adjacent to the target can either shift 1 square as a free
    action or gain a +2 power bonus to all defenses until the start of your
    next turn."* Written once here because the feat names two powers in
    different files.

    **The ally chooses, not the caster**, which is what "can either" means
    on a clause that benefits somebody else -- so `c.may` is asked of each
    ally in turn rather than of the warlock. `c.may`'s own note is the
    reason that distinction is kept: it is asked of the creature it is
    about, because whose resource it is decides whether it is worth
    spending, and the same holds for whose turn it interrupts.

    Not the caster even when the caster is standing there: "each ally" is
    other people, the read `p4177`'s own body already takes two lines
    further down.

    `side="ally"` is read from the warlock and not from the target, which
    is `c.within`'s documented behaviour and what the printed word means --
    an ally of *mine* standing next to that enemy.
    """
    foe = c.target
    if foe is None:
        return
    for friend in sorted(c.within(1, of=foe, side="ally")):
        if friend == c.me:
            continue
        if c.may("step instead of bracing", who=friend):
            # `who=`, not `on=`: a movement verb names its mover that way
            # and defaults it to the caster, where the modifier verbs
            # take `on=` and default to the target.
            c.shift(1, who=friend)
        else:
            for defence in DEFENCES:
                c.bonus(defence, 2, on=friend, until=When.SONT, kind="power")


def riposte(c: Cast) -> None:
    """`f3421`'s augment: the target swings where the warlock points.

    *"The target makes a basic attack against a legal target you choose."*
    The swing is `c.grant_attack`, whose first argument is who swings and
    whose `on=` is who is swung at -- a distinction four rows in the tree
    got wrong by leaving `on=` off, so the grant bailed on its own guard
    (#631).

    "A legal target" is read as a creature the target can actually reach: a
    basic attack it cannot deliver is not the clause printed. Chosen by the
    caster, which is the card's own "you choose", and the target itself is
    excluded -- it is the one swinging.
    """
    foe = c.target
    if foe is None:
        return
    reach = sorted(
        other for other in c.within(1, of=foe) if other not in (foe, c.me)
    )
    victim = c.choose(reach, f"{c.ref}: whom the target strikes") if reach else None
    if victim is not None:
        c.grant_attack(foe, on=victim)


def thunderclap(c: Cast) -> None:
    """`f3429`'s augment: an ally nearby swings, and the blow rolls thunder.

    *"One ally within 5 squares of you makes a basic attack as a free action
    and deals extra thunder damage equal to your Intelligence modifier."*

    **Typed, through `c.grant_attack(damage_type=)`.** That parameter is new
    and `Mod.dtype`'s own docstring is the argument for it: these points are
    thunder even when the ally's weapon is not, so they meet the victim's
    thunder resistance and its thunder vulnerability where the weapon's
    points do not. Untyped they would have joined the blow as whatever the
    blow already was.

    The modifier is Intelligence of the **warlock**, not of the ally: it is
    this feat paying, and `c.int_mod` on this cast is the caster's.

    "At least one enemy" is satisfied by this clause running at all --
    every row it is written into announces per target, and the clause is
    guarded to fire once a use by `c.bonus(once=)`'s reason rather than by
    counting hits: a second payout on a two-target blast would be one swing
    more than the card.
    """
    if getattr(c, "greater_pact_paid", False):
        return
    friend = next(
        iter(sorted(
            ally for ally in c.within(5, side="ally") if ally != c.me
        )),
        None,
    )
    if friend is None:
        return
    marks = sorted(
        foe for foe in c.within(1, of=friend, side="enemy") if foe != friend
    )
    if not marks:
        return
    c.greater_pact_paid = True
    c.grant_attack(friend, on=marks[0], damage_bonus=c.int_mod,
                   damage_type=DamageType.THUNDER)
