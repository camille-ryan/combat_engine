"""General feats, fifth batch: the last exploit riders and a few
standalone ones worth the space.

`_riders` is the same machine `exploits.py` uses -- one watcher per
feat, the clause picked by which power hit -- so an Associated Powers row
is one short entry rather than four `c.watch` calls.

**No clause rides from this file any more.** #550's convention writes a
feat's clause into the body of the power it names, and the last three
registrations here moved with it: `f990`'s `p2105`, `p919` and `p1063`,
`f993`'s `p4541` and `p4369`, and `f991`'s `p917`. So all four of the
Associated Powers cards in this file are declared pointers carrying
`implemented_in=`, and each call below says which rows hold its clauses.

Three of those six moves also **changed window**, which is the thing a
migration can fix and a rider cannot: `_riders`' default table is a `Hit`
watcher, and `p2105`'s and `p4369`'s clauses print "before the attack"
while `p4541`'s is about a swing somebody else makes. Each host's
docstring says so where the clause now lives.
"""

from __future__ import annotations

from combat_engine.content.feats.exploits import _riders
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    Ability,
    ActionType,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, holding

# **Every clause of this card is written into the row it names**, per #550.
# `p971`'s moved first and the other three now. None of the four survived
# the move unchanged, which is the point of it rather than a cost:
#
# * `p971`'s says *"if you score a critical hit"*, where the shared
#   `c.shift(1)` helper this file used to hold could say no condition at
#   all.
# * `p2105`'s is *"before the attack"*, so registered in the `Hit` table
#   here it paid after the swing -- the one moment the step is no use. It
#   is above that row's `c.strike()` now.
# * `p919`'s is *"if you shift after the attack"*, which a `Hit` rider
#   cannot see; that row reads it off the step's own return, and the
#   printed second sentence about where the ally must end up is written
#   too, which the rider dropped.
# * `p1063`'s wants combat advantage on the blow, read off `c.result`.
_riders("f990", {}, implemented_in=("p971", "p2105", "p919", "p1063"))

# **Every clause of this card is written into the row it names**, per #550:
# `p992` behind `c.declare("Arena Fighting", "f993")` (#780), `p2248`'s
# Intimidate bonus in that row's hit branch, and now `p4541` and `p4369`.
#
# `p4369` was held back by a collision rather than by the clause -- a
# **second** `c.declare` call for one category in one body is defeated by
# the memo, `Cast.declared_feats` answering the first call's pick for every
# later one -- so the clause joins that body's existing chain and the one
# call moved to the top of the body, which is where its `used=` window is.
#
# `p4541`'s was in the wrong window here as well as in the wrong file: the
# card reads *"if your **ally** hits the target with the granted basic
# attack"* and this table is a `Hit` watcher gated on `ev.attacker == me`,
# so it paid on the character's own hit and never once on the ally's. That
# row already had `_granted_hit` for the same reading of the same swing,
# and the two clauses share the one call -- two would be two swings.
_riders("f993", {}, implemented_in=("p4541", "p992", "p2248", "p4369"))

# **Both clauses of this card are written into the rows they name**, per
# #550: `p970`'s first and `p917`'s now. `p917`'s is the `missed=` window,
# so it is the `else` of that row's `c.strike()`, and the ranged weapon it
# asks about is the one in the character's hand rather than the attack
# branch the use took -- a ranger can hold a bow and swing a blade.
_riders("f991", {}, implemented_in=("p917", "p970"))


# **Fully migrated, so there is no rider left and no clause here.** Both of
# this feat's powers carry its clause in their own body -- `p4542` since
# #550's first pair and `p1000` now -- so the row is a pointer and
# `audit.py` buckets it ELSEWHERE rather than firing it.
#
# Declared by hand rather than through `_riders`, and **the reason given
# here was false.** It said `_riders` with every table empty generates
# *"No clause of this card is writable yet; see the marker"*: that fallback
# needs `implemented_in=` to be empty **too**, and with hosts named the
# generated line is "Every clause of this card is written into the row it
# names", which is exactly right -- the three pointers above take it. What
# a hand-written row buys is the paragraph below, saying *where in each
# host* the clause sits, which no generated line can. The header is the one
# `_riders` builds, field for field.
@power("f995", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, implemented_in=("p4542", "p1000"))
def f995(c: Cast) -> None:
    """Both clauses live in the rows this card names, per #550.

    `p4542` adds the shield bonus to that row's attack roll, before its
    `c.strike()`, because the clause changes the roll. `p1000` lays the
    +1 shield bonus on an ally beside the target at the top of its hit
    branch, with the `Moved` watcher that is the second of the two printed
    endings.

    Nothing runs here. `lint._dangling_implementations` is what checks that
    both hosts still name this feat.
    """


@power("f1002", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1002(c: Cast) -> None:
    """Combat advantage at range against anyone your allies are flanking
    -- which is normally a melee-only benefit, and is the whole point of
    the feat. `query.flanked` is the printed question."""
    from combat_engine.engine.query import flanked_by

    me = c.me

    def by_my_allies(ctx: dict) -> bool:
        foe = ctx.get("target")
        if not ctx.get("ranged", False) or foe is None:
            return False
        # `flanked_by` asks whether *that* creature flanks the target,
        # so the question is asked once per ally rather than once: the
        # printed line is about the allies flanking, not about me.
        return any(
            friend != me and flanked_by(c.world, foe, friend)
            for friend in allies(c.world, me)
        )

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=by_my_allies)


@power("f1032", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1032(c: Cast) -> None:
    """"Choose a weapon group" is a build-time choice nothing records,
    so the group is read as the one the character is carrying -- which
    is what the choice comes to for a character with one weapon, and
    every chassis has one."""
    gear = c.world.get(c.me, Gear)
    arm = gear.main if gear else None
    if arm is None:
        return
    group = arm.group
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(holding(c.world, c.me, group))
        and (p := get(ctx.get("power", ""))) is not None
        and Keyword.WEAPON in p.keywords,
    )


@power("f1033", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1033(c: Cast) -> None:
    """Rolling a check twice is narrative; the initiative bonus is not,
    and it is the reason this is not an `out_of_combat` row.

    **`c.bonus("initiative", ...)` is read by nothing.**
    `Initiative.bonus` is summed before the d20 and `Mods` is never
    consulted, which `c.initiative`'s own docstring says outright -- so
    the modifier I laid here sat in the table and no roll ever saw it.
    `c.initiative` moves the creature in the order after the fact,
    which is the only thing that can say this from a trait.

    A trait is armed *after* the opening rolls, so this lands as an
    adjustment rather than a bonus -- the same arrangement `f288` and
    `f2055` make.
    """
    c.initiative(3, on=c.me)


@power("f1016", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1016(c: Cast) -> None:
    """Swaps which ability a melee basic attack rolls.

    **Re-aimed off `c.basic_ability()` and then written.** The header on
    `mba` is indeed shared and must not be rewritten -- but the printed
    line is arithmetic, not a rewrite: `mba` rolls Strength and adds
    `c.str_mod` to the damage, so the swap is the difference between the
    two abilities, laid as a gated modifier on the one row. Exactly the
    printed numbers, and the shared header is untouched.

    "Choose an ability other than Strength" is a build-time choice
    nothing records, so it is read as the character's best other one --
    the same proxy `f1032` makes for a weapon group, and for the same
    reason: it is what the choice comes to for the chassis in hand.
    """
    best = max(c.dex_mod, c.con_mod, c.int_mod, c.wis_mod, c.cha_mod)
    # A printed "you can", so it is taken only where it is an
    # improvement -- laid unguarded on a chassis whose Strength is the
    # better score it was a **penalty** to the basic attack, which is
    # what an optional benefit written as a compulsory one looks like.
    if best <= c.str_mod:
        return
    swing = lambda ctx: ctx.get("power") == "mba"  # noqa: E731
    c.bonus("attack", best - c.str_mod, on=c.me, until=When.ENCOUNTER,
            when=swing)
    c.bonus("damage", best // 2 - c.str_mod, on=c.me, until=When.ENCOUNTER,
            when=swing)


@power("f1023", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1023(c: Cast) -> None:
    """Maximises healing after a rest, **before the next encounter**.

    **Re-aimed off `c.maximise(healing=)`, which would not help.** The
    duration is the hold, and it is not a duration this engine is
    missing -- it is one that ends where the engine begins. Every hit
    point this feat maximises is restored between fights, so there is
    no moment inside an encounter at which it is ever true. That is an
    inert row rather than a marked one, and a `c.maximise(healing=)`
    would sit in the tree waiting for a verb that would change nothing.
    """


@power("f969", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f969(c: Cast) -> None:
    c.grant_row("f969b", on=c.me, until=When.ENCOUNTER)


@power("f969b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.WEAPON])
def f969b(c: Cast) -> None:
    """Threaten at the whip's reach rather than at adjacency.

    I marked this `c.threaten_at(reach)`. **`c.threatens` exists** and
    is that verb -- "it can make opportunity attacks against enemies
    within 2 squares" is its docstring's own example, and it is held as
    a modifier so a reach weapon can raise it.
    """
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power("f970", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f970(c: Cast) -> None:
    c.grant_row("f970b", on=c.me, until=When.ENCOUNTER)


@power("f970b", level=1, cls="", usage=DAILY, action=ActionType.STANDARD,
       reach=Melee(2), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
       attack=Attack(Ability.DEX, vs=REF),
       dropped=("c.forbid(weapon=)",))
def f970b(c: Cast) -> None:
    """The grab and the prone land on a hit *and* on a miss -- only the
    damage differs -- so both are written outside the branch.

    **Re-pointed, and the count was wrong: three clauses are unwritten,
    not one.** The old marker said `c.grab(pull_as_minor=)` and named a
    parameter on the wrong verb -- the engine already has the door.
    "You can pull it 1 square as a minor action" is a line in the action
    menu, which is `c.grant_action` plus a word in `actions.GRANTABLE`
    and a reader beside it; a kwarg on `c.grab` would have to grow its own
    menu entry anyway. That is the symbol now, and it is **not free**: a
    new granted action widens what the AI can choose, so it owes a
    `winrate` reading and probably a fixture re-record rather than riding
    along with a content commit.

    Reading the card for the re-point turned up two more clauses nothing
    had recorded:

    * *"While grabbing the target, you cannot make attacks with the
      whip"* -- `c.forbid` takes `ref`, `keyword`, `lacking`, `usage`,
      `only` and `attacks_only`, and none of them narrows to a **weapon**.
      Marked.
    * *"You can sustain the grab as long as the target is within 2 squares
      of you"* -- deliberately **not** marked, because `sustain=` in the
      header with `until=When.SUSTAIN` exists (`m2295a1` is the worked
      example) and I have not established that the range condition cannot
      be written with it. A symbol is a claim that something is missing,
      and that one is unverified. #560."""
    hit = c.strike().hit
    if hit:
        c.damage(c.w(2), c.dex_mod)
    c.grab()
    c.prone()
    c.penalty("escape", 5)
    # **"You can pull it 1 square as a minor action", which is a line in
    # the action menu.** `actions.GRANTABLE` carries `pull_grabbed` now and
    # `actions` offers it one option per legal destination square, so the
    # choice of square stays the puller's -- which is what the clause is
    # for. #888.
    #
    # `until=When.ENCOUNTER` rather than a stance: the printed condition is
    # "while you have the target grabbed", and the grant is harmless once
    # the grab ends because the reader asks `Relation.GRABBED_BY` live and
    # offers nothing when the answer is empty. Tying the effect's own clock
    # to the grab would need a second mechanism for the same gate.
    #
    # **`on=c.me`, and a bare call would have granted it to the victim.**
    # This body runs once per target and `c.target` is the creature being
    # grabbed, so the default would hand the pull to whoever is being
    # dragged -- `content/CLAUDE.md`'s "commonest single mistake here", and
    # silent: `grant_action` returns `None` for a missing subject rather
    # than raising, so the clause would simply never have existed.
    c.grant_action("pull_grabbed", ActionType.MINOR, squares_=1, on=c.me)
