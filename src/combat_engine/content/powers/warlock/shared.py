"""What more than one warlock file needs.

`_backlash` was written out twice, byte for byte, in `level_1_b.py` and
`level_9_b.py`. Five refs in each file call it.
"""

from __future__ import annotations

from combat_engine.content.features.warlock import FELL
from combat_engine.engine import Cast, DamageType, Keyword, When

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
