"""The executioner, the assassin's second chassis.

`#642`'s wave. 27 printed rows, and the chassis where **a grant is finally
load-bearing** -- not because `loadout` misses the powers, but because the
guild fork gives three of nine and the other six have to be taken away.

The shape:

    11  play
     3  a ladder rung superseding a lower number -- `#1261`
     7  the poison recipe-and-vial ladder, one shared symbol
     3  a utility power of your choice
     1  a disguise crafted on a short rest
     2  `defect=`: the row names itself as the power it grants

## The guild fork is about forbidding, not granting

`-f2` offers three guilds and each option grants three powers. All nine are
declared `cls="assassin"` at level 0, so `chargen.loadout` has dealt every
one of them to every assassin -- measured, 9 of 9 -- which makes the grants
no-ops and the **exclusivity** the whole content of the fork. So each
option forbids the other six, which is `cf:barbarian-f1`'s arrangement:
*"the row therefore takes the power away from the legs that did not choose
it, which is the only way the exclusivity can be true."*

## Two clauses needed no verb and the second was a surprise

`-f4` is the slayer's `-f4` word for word -- *"once during each of your
turns, you can take a free action to draw or stow a weapon and then draw
another weapon"* -- so it is `c.draws_free(per_turn=1)` again.

`-f5` grants one of two named feats, and `c.grant_row` does it. A feat is
an ordinary row in `Powers.known`, which is what lets one arm itself at the
start of a fight, so granting a feat is granting a row -- checked rather
than assumed: `c.grant_row("f162")` returns an effect and `f162` is in
`Powers.all` afterwards. **`c.feat` is a reader and not a granter**, which
is worth saying because its name reads the other way and one row in
`features/primal_divine.py` calls it and discards the answer.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import _weapon_attack, pay_extra
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    SELF,
    Ability,
    ActionType,
    Cast,
    Fell,
    Keyword,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.events import Hit
from combat_engine.engine.triggers import about_me

#: The three guilds, each with the three powers it hands over. Written out
#: rather than derived from the refs, because the exclusivity below is the
#: whole content of the fork and a derived list would make the one thing
#: this fork does depend on a naming convention.
GUILDS: dict[str, tuple[str, ...]] = {
    "cf:assassin-executioner-f2s0": ("p13796", "p13797", "p13798"),
    "cf:assassin-executioner-f2s1": ("p13793", "p13794", "p13795"),
    "cf:assassin-executioner-f2s2": ("p15911", "p15912", "p15913"),
}

#: The four arms `-f1`'s extra damage names. A garrote and a blowgun are
#: not in `chargen`, so the groups are what the engine can say: anything
#: one-handed, plus the shortbow's group.
_ONE_HANDED = "one-handed"
_SHOOTER_GROUPS = ("bow",)

#: The label `-f1` pays its extra damage under -- its own, because no other
#: row in this tree prints this table. Contrast `features/thief.py`, where
#: the card says outright to read the scoundrel's.
SNEAK = "cf:assassin-executioner-f1"


def _with_a_quiet_weapon(c: Cast) -> Any:
    """"A one-handed weapon, a garrote, a blowgun, or a shortbow."

    Two of the four printed arms do not exist in `chargen`, so what is
    asked is the two that do: a one-handed weapon by its property, and the
    shortbow by its group. Narrower than the card and **deliberately** --
    widening it to "any weapon" would pay a greataxe, which the card plainly
    does not.

    `_weapon_attack` rather than the main hand, for `features/thief.py`'s
    reason: an assassin carries a blade and a shooter, and a rider reading
    the main hand would pay a bowshot for the blade's sake.
    """
    me, world = c.me, c.world

    def gate(ctx: dict[str, Any]) -> bool:
        weapon = _weapon_attack(world, me, ctx)
        if weapon is None:
            return False
        return (_ONE_HANDED in weapon.properties
                or weapon.group in _SHOOTER_GROUPS)

    return gate


def _finishable(c: Cast, victim: int, ceiling: int) -> bool:
    """"If it has N hit points or fewer **after the damage is dealt**."

    Asked after the blow lands, which is what the printed "after" means and
    is why these rows watch `Hit` rather than declaring an interrupt: an
    interrupt answers a blow that has not happened yet and could not know
    the number.

    `Health.hp` off the world and not a `Cast` verb, because there is no
    `c.hp` -- `c.temp_hp` is the only hit-point member and it is the
    writer. `query.bloodied` is the nearest reader and asks a different
    question.
    """
    health = c.world.get(victim, Health)
    return health is not None and 0 < health.hp <= ceiling


# -- the eleven rows that play -----------------------------------------------


@power(
    "cf:assassin-executioner-f0",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_strike(c: Cast) -> None:
    """"You gain the p13799 power."

    A no-op grant: `p13799` is a level-0 assassin row, so `loadout` has
    dealt it. `#1259`.
    """
    c.grant_row("p13799", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:assassin-executioner-f1",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_attack(c: Cast) -> None:
    """Dexterity for melee basic attacks, and once a turn an extra `1d8`
    with one of the four quiet arms.

    *"You can use Dexterity instead of Strength for your melee basic
    attacks"* is `c.rolls_with`, and one call pays the attack roll and the
    damage roll both. No weapon gate on this half: the card puts none on
    it, unlike the half below.

    The extra damage is `pay_extra`, which is the once-a-turn latch the
    rogue and the ranger already share -- *"once per turn"* is this latch
    and not a second one of its own, and factoring it out is why `f1722`
    could pay the quarry damage on a miss without a second payout to keep
    in step. Under this row's **own** label, because no other row prints
    this table; the thief shares the scoundrel's only because its card says
    to.

    The ladder is `1d8` / `2d8` at 11th / `3d8` at 21st, which `_tier`'s
    steps are -- counted inline here rather than imported, because
    `strikers_sb._tier` is in another file for the barbarian's sake and one
    expression is cheaper than a cross-import.
    """
    me = c.me
    c.rolls_with("mba", Ability.DEX, on=me, until=When.ENCOUNTER)
    dice = 1 + (c.level >= 11) + (c.level >= 21)
    gate = _with_a_quiet_weapon(c)

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not gate({"power": ev.power}):
            return
        pay_extra(c, SNEAK, f"{dice}d8", on=ev.target, per_turn=True)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:assassin-executioner-f2",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_guild(c: Cast) -> None:
    """*"You become a member of an assassin guild."*

    A **parent**, so `chargen.ladder_row` deals it and it chooses among its
    own three options. `chargen.BUILD_OPTIONS` and not a leg: the
    assassin's three legs are the base class's fork
    (`cf:assassin-f1s0`..`s2`) and a character takes one leg.

    All three options are declared below, so this grants rather than
    repeating what they say.
    """
    guild = (c.chosen_option("cf:assassin-executioner-f2")
             or "cf:assassin-executioner-f2s0")
    c.grant_row(guild, on=c.me, until=When.ENCOUNTER)


def _guild(ref: str, extra: str = "") -> Any:
    """One guild: three powers kept and the other six taken away.

    The one helper the global rule allows, for a run of rows that share a
    shape -- three here, and each `GUILDS` entry above names its own three
    powers out loud.

    **The forbidding is the content.** All nine powers are level-0 assassin
    rows, so `loadout` has dealt every one to every assassin and
    `c.grant_row` returns `None` for all three of this guild's. What makes
    the printed choice mean anything is that the other two guilds' six
    become unusable, which is `cf:barbarian-f1`'s arrangement and its
    sentence: *"the row therefore takes the power away from the legs that
    did not choose it, which is the only way the exclusivity can be
    true."*

    `c.forbid` follows `c.target` and a trait has none, so `on=c.me` is
    required -- the commonest single mistake in this tree and one
    `cf:barbarian-f1` records in a comment of its own.
    """

    @power(
        ref,
        level=0,
        cls="assassin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.SHADOW],
        dropped=(extra,) if extra else (),
    )
    def row(c: Cast) -> None:
        me = c.me
        for ours in GUILDS[ref]:
            c.grant_row(ours, on=me, until=When.ENCOUNTER)
        for other, theirs in GUILDS.items():
            if other == ref:
                continue
            for gone in theirs:
                c.forbid(gone, on=me, until=When.ENCOUNTER)

    row.__name__ = "executioner_guild_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One guild: {', '.join(GUILDS[ref])} kept, the other two guilds' "
        "six forbidden.\n\n"
        "The grants are no-ops -- every one of the nine is a level-0 "
        "assassin row that `loadout` has already dealt -- so the six "
        "`c.forbid` calls are what the printed choice is worth. The helper "
        "above has the argument."
        + (f"\n\nDropped: `{extra}`." if extra else "")
    )
    return row


executioner_guild_0 = _guild("cf:assassin-executioner-f2s0")
executioner_guild_1 = _guild("cf:assassin-executioner-f2s1")
executioner_guild_2 = _guild(
    "cf:assassin-executioner-f2s2", "chargen.proficiency(w3750)")


@power(
    "cf:assassin-executioner-f4",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_handy(c: Cast) -> None:
    """"Once during each of your turns, you can take a free action to draw
    or stow a weapon and then draw another weapon."

    `cf:fighter-slayer-f4`'s sentence word for word, so it is the same
    call: `c.draws_free(per_turn=1)` on a free cost, with
    `Gear.draws_left` refilling at the start of each of this creature's
    turns. The second printed draw is the same allowance spent twice --
    a stow and a draw are both draws to `actions._wielding`.

    Written out rather than shared with the slayer's row for
    `cf:rogue-thief-f1`'s reason: an executioner is dealt no fighter row,
    so if this did not pay the clause nobody would.
    """
    c.draws_free(cost=ActionType.FREE, per_turn=1, on=c.me,
                 until=When.ENCOUNTER)


@power(
    "cf:assassin-executioner-f7",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_finish(c: Cast) -> None:
    """"When you hit an enemy with a melee or a ranged attack that deals
    damage, you can choose to reduce the enemy to 0 hit points
    automatically if it has 10 hit points or fewer after the damage is
    dealt."

    A `Hit` watch and **not** an interrupt, which is the printed "after the
    damage is dealt": an interrupt answers a blow that has not landed and
    could not know the number. `c.hp` is read when the watch runs, so the
    ceiling is tested against what is left.

    *"You can choose"* is `c.may`, so declining is one of the answers --
    and it is a real choice, since a creature at 1 hit point will usually
    fall to the next blow anyway and this is once per hit rather than once
    per encounter.

    **The ladder two rows climb is written here**: `-f15` and `-f21`
    print *"20 hit points or fewer"* and *"30"*, so they are pointers
    carrying `implemented_in=` and this body reads them. Rising order and
    plain `if`, so the highest held ceiling replaces rather than adds --
    and `combat_engine.levels` is what keeps a 1st-level executioner from
    holding the 30 (`#1261`).

    The ceiling is read **inside the watch**, not once at arming: `c.feat`
    is cheap and a row granted mid-fight would otherwise be missed.
    """
    me = c.me

    def finish(ev: Hit) -> None:
        if ev.attacker != me or ev.target == me:
            return
        ceiling = 10
        if c.feat("cf:assassin-executioner-f15"):
            ceiling = 20
        if c.feat("cf:assassin-executioner-f21"):
            ceiling = 30
        if not _finishable(c, ev.target, ceiling):
            return
        if c.may("finish it off"):
            c.kill(on=ev.target)

    c.watch(Hit, finish, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:assassin-executioner-f8",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
    trigger="you take falling damage",
    on=Trigger(Fell, about_me, "you take falling damage"),
)
def executioner_tumble(c: Cast) -> None:
    """"When you take falling damage, you can take a free action to reduce
    the damage by 6 + your level. If this reduces the damage to 0, you don't
    fall prone."

    **A declared trigger, not a trait laying `c.arm_trigger`**, and that
    distinction is the whole of why this works. `c.cushion` softens *"the
    fall being answered"* -- it reads `self.trigger` and returns `False` for
    anything that is not a `Fell`. A trait's `Cast` has no trigger, so the
    first draft here armed a watch, charged the free action (`ActionSpent`
    fired twice in the probe) and softened **nothing**: the handler ran and
    the verb declined. `p13314` is the shape that works and it is a
    declared-trigger row.

    `action=ActionType.FREE` is the printed cost, and `turns.arm_traits`
    deliberately skips a row with a declared trigger -- *"arming it at the
    start would fire it once, out of nowhere, and never again"* -- so the
    row waits for the fall.

    `Fell` is a `Decision` and both of its readable fields are what this
    clause sets: `c.cushion(amount)` adds to `soften` and announces
    `Cushioned`, which is what keeps a row whose whole content is this call
    from being invisible (`#756`). The second printed sentence is read off
    the first -- `c.cushion` answers whether it applied.

    *"If this reduces the damage to 0"* is **not** asserted here, and that
    is the one honest gap: `c.cushion` adds to `soften` and the fall's
    damage is computed afterwards, so whether `6 + level` covered it is not
    knowable at this point. `ev.prone` is left alone rather than guessed --
    a slayer dropping 20 squares still falls over, which is the card.
    """
    ev = c.trigger
    if not isinstance(ev, Fell):
        return
    c.cushion(6 + c.level)


@power(
    "cf:assassin-executioner-f11",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_shroud(c: Cast) -> None:
    """"You gain the p13806 power." A no-op grant -- a level-0 assassin
    row, already dealt. `#1259`."""
    c.grant_row("p13806", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:assassin-executioner-f18",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
)
def executioner_veil(c: Cast) -> None:
    """"You gain the p13813 power." A no-op grant -- a level-0 assassin
    row, already dealt. `#1259`."""
    c.grant_row("p13813", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:assassin-executioner-f5",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    dropped=("chargen.meets(waived=)",),
)
def executioner_bonus_feat(c: Cast) -> None:
    """"You choose a bonus feat, either f162 or f172. You don't have to meet
    the feat's prerequisite."

    **The grant works and that was the surprise.** `c.grant_row` puts a ref
    in `Powers.known`, a feat is an ordinary row there, and that is what
    lets one arm itself at the start of a fight -- so granting a feat is
    granting a row. Checked rather than assumed, because `c.feat`'s name
    reads like the granter and is the **reader**:
    `c.grant_row("f162")` returns an effect and `f162` is in `Powers.all`
    afterwards.

    The choice is `chargen.BUILD_OPTIONS`, two options, same as every other
    printed pick-one in this wave.

    Dropped: *"you don't have to meet the feat's prerequisite."* Granting
    the row directly sidesteps `chargen.meets` entirely, so the clause is
    **already true** of this path and is marked anyway -- because the day
    the grant goes through the dealer instead, the prerequisite comes back
    and nothing would say so. One symbol, naming the waiver rather than the
    grant.
    """
    feat = (c.chosen_option("cf:assassin-executioner-f5") or "f162")
    c.grant_row(feat, on=c.me, until=When.ENCOUNTER)


# -- the three rungs that supersede a lower number ---------------------------


def _finish_rung(ref: str, ceiling: int) -> Any:
    """One rung of `-f7`'s ceiling, refused for want of a level."""

    @power(
        ref,
        level=0,
        cls="assassin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.SHADOW],
        implemented_in=("cf:assassin-executioner-f7",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "executioner_finish_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"`cf:assassin-executioner-f7`'s ceiling rises to {ceiling} hit "
        "points.\n\n"
        "**Written into `cf:assassin-executioner-f7`**, whose `Hit` watch "
        "reads the ceiling: no modifier can reach into another row's "
        "watch, so this is a pointer and carries `implemented_in=`.\n\n"
        "What made it unwritable was the level, not a verb: every class "
        "feature armed at the start of every fight because "
        f"`class_feature` carries none, so a ceiling of {ceiling} reached "
        "a 1st-level executioner finishing off anything below it. "
        "`combat_engine.levels` carries the printed levels now and "
        "`chargen.ladder_row` reads them. `#1261`."
    )
    return row


executioner_finish_15 = _finish_rung("cf:assassin-executioner-f15", 20)
executioner_finish_21 = _finish_rung("cf:assassin-executioner-f21", 30)


# -- the poison ladder: seven rows, one gap ----------------------------------


def _poison_rung(ref: str, what: str) -> Any:
    """One rung of the recipe-and-vial ladder.

    Seven rows, **one** symbol, because they are one gap seven times: the
    recipes are a draw, the vials are an extended-rest allowance, and the
    two are inseparable on every one of the seven cards -- a row that
    learned a recipe with nowhere to prepare it would be inert, and a vial
    allowance with no recipe would be empty.

    The poison table itself exists -- 19 rows -- so unlike some gaps in
    this wave the content is here and what is missing is the machinery
    between an extended rest and a consumable.
    """

    @power(
        ref,
        level=0,
        cls="assassin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.SHADOW],
        todo=("chargen.poison_recipes()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "executioner_poison_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        "One of seven rows on this ladder and they share one symbol -- the "
        "helper above has the argument. `turns.extended_rest` is where the "
        "preparing would live and `i293` is the kit the card requires; the "
        "19-row `poison` table is the content, already imported."
    )
    return row


executioner_poison_3 = _poison_rung(
    "cf:assassin-executioner-f3",
    "Two 1st-level recipes learned, and one vial prepared per extended "
    "rest.")
executioner_poison_9 = _poison_rung(
    "cf:assassin-executioner-f9", "Another 1st-level recipe; two vials.")
executioner_poison_13 = _poison_rung(
    "cf:assassin-executioner-f13", "Another 1st-level recipe; three vials.")
executioner_poison_16 = _poison_rung(
    "cf:assassin-executioner-f16",
    "A 15th-level recipe, and one vial may be up to 15th level.")
executioner_poison_19 = _poison_rung(
    "cf:assassin-executioner-f19",
    "Another 15th-level recipe; two vials may be 15th level.")
executioner_poison_22 = _poison_rung(
    "cf:assassin-executioner-f22",
    "A 25th-level recipe; one vial up to 25th and two up to 15th.")
executioner_poison_23 = _poison_rung(
    "cf:assassin-executioner-f23",
    "Another 25th-level recipe; two vials up to 25th and one up to 15th.")


# -- the three utility picks -------------------------------------------------


def _utility_pick(ref: str, what: str, *, gained: bool = False) -> Any:
    """One of the three rows reading "you gain a c466 utility power".

    `gained=True` is the one whose own text states the level -- *"a
    2nd-level"* -- so it carries a `chargen.EXTRA_GAINS` entry and no
    marker. The other two say *"of your level or lower"* and name none,
    and `class_feature` carries none (`#1261`), so an entry would be a
    guess about when the gain happens.
    """

    @power(
        ref,
        level=0,
        cls="assassin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.SHADOW],
        todo=() if gained else ("chargen.power_choice()",),
        out_of_combat=gained,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "executioner_utility_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        + ("**Finished.** The card states the level the gain happens at, "
           "so `chargen.EXTRA_GAINS` carries it and `loadout` deals the "
           "extra power to a character holding this row and nobody else "
           "(`#1112`). `out_of_combat=True`: the whole row is a draw."
           if gained else
           "A draw from a named printed family -- and specifically the "
           "**level** half of `chargen.power_choice()`: this card says "
           "*of your level or lower* and names no level for the gain, "
           "which `#1261` is about. The row beside it that does name one "
           "is finished.")
    )
    return row


executioner_utility_6 = _utility_pick(
    "cf:assassin-executioner-f6", "A 2nd-level `c466` utility power.",
    gained=True)
executioner_utility_10 = _utility_pick(
    "cf:assassin-executioner-f10",
    "A `c466` utility power of your level or lower.", gained=True)
executioner_utility_14 = _utility_pick(
    "cf:assassin-executioner-f14",
    "Another `c466` utility power of your level or lower.", gained=True)


# -- the disguise, and the two the import cannot supply ----------------------


@power(
    "cf:assassin-executioner-f12",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    todo=("story.disguise()",),
)
def executioner_disguise(c: Cast) -> None:
    """A disguise crafted on a short rest, seen through by an Insight check
    opposed by Bluff.

    The story engine's and not the kernel's: it happens on a rest, the
    contest is a skill check against a party member or an NPC, and what it
    changes is who a creature appears to be -- none of which a `World` has
    a field for.

    **Not `narrative=`**, which would claim the clause has no combat
    meaning. An opposed check that decides whether a guard attacks is
    exactly combat meaning; what it lacks is a writer. `story/` owns the
    rest and the contest, so the symbol names that side.
    """


def _defective(ref: str) -> Any:
    """One of the two rows naming itself as the power it grants."""

    why = (f"the spec reads 'you gain the {ref} power' -- the feature names "
           "itself as the power it grants, and no such ref exists")

    @power(
        ref,
        level=0,
        cls="assassin",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.SHADOW],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "executioner_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


executioner_defect_17 = _defective("cf:assassin-executioner-f17")
executioner_defect_20 = _defective("cf:assassin-executioner-f20")
