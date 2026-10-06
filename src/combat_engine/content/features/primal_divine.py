"""Class-page sub-options that the tree does not already carry elsewhere.

Every ref here is a **sub-option**: one arm of a fork the class page prints,
or a power card printed under a feature rather than in the power lists. They
became extractable only now, which is why four classes that already have
`cf:` rows in `defenders.py`, `strikers_sb.py` and `controllers_sd.py` get a
second file rather than an edit.

**Ten of the batch's twenty-six refs are not here, on purpose.** The
extraction over-reached: some `-fNcM` refs are verbatim a card the tree
already declares under its own `p` ref, and some `-fNsM` refs restate a
branch their parent feature already lays. Declaring either would put the
same encounter card in the menu twice, or -- worse, because it is invisible
-- stack a second copy of an untyped bonus. They are skipped rather than
stubbed, so that the count still says they are absent:

* `cf:avenger-f1s0`, `cf:avenger-f1s1` -- `cf:avenger-f1`
* `cf:avenger-f3c0` -- `p3069`
* `cf:druid-f1s0`, `cf:druid-f1s1` -- `cf:druid-f1`
* `cf:druid-f3c0` -- `p5032`
* `cf:fighter-weaponmaster-f0c0` -- `p10469`
* `cf:fighter-weaponmaster-f3s3`, `-f3s5` -- `cf:fighter-weaponmaster-f3`
* `cf:invoker-f1s1` -- `cf:invoker-f1`

**`cf:fighter-weaponmaster-f3s1` was on that list and has come off it.** It
is not a restatement: it has three clauses and the parent lays the first
only. The other two -- the damage bonus the parent names as unwritten, and
the temporary hit points a missed invigorating power pays -- are nowhere in
the tree, so the row is here and the first clause is written out with it.
Repeating that one clause is free, which is measured rather than assumed:
`resolve.temp_hp` keeps the larger pool, so two handlers offering the same
number leave one pool of that size. The parent's copy is redundant now.

What is left is what is genuinely new: the arms of each fork that the parent
reads no leg for and leaves out, and the two covenant cards, which are not
`p5186` or `p7150` and are not anywhere else either.

**Channel Divinity is already sayable.** "You can use only one such ability
per encounter" is a budget across a set of rows, which is exactly
`group=CHANNEL_DIVINITY` plus `dsl._group_spent`: `usable` refuses a row
whose group sibling has been used this fight. So `cf:avenger-f2` and
`cf:invoker-f0` have nothing of their own left to lay, and the two covenant
cards declare the group like every other channelled row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.content.features.builds import on_leg
from combat_engine.content.features.controllers_sd import out_of_heavy_armour
from combat_engine.content.powers.avenger.oath import sworn
from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    ActionType,
    Cast,
    CloseBurst,
    DamageType,
    Gear,
    Health,
    Keyword,
    Trigger,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import Hit, PowerResolved, PowerUsed
from combat_engine.engine.query import alive, allies, distance_between, team

#: The reach kinds "a melee or a close attack" names, as `Range.kind` spells
#: them. Same tuple `defenders.py` keeps for the same sentence.
_MELEE_OR_CLOSE = ("melee", "close_burst", "close_blast")

#: "A melee attack or a ranged attack", for the damage side, where the only
#: thing the context carries about the attack is which row rolled it.
_MELEE_OR_RANGED = ("melee", "ranged")

#: The armours "light armor or chainmail" names. Chain is heavy for every
#: *other* sentence in the tree, so this cannot be `chargen.LIGHT`.
_LIGHT_OR_CHAIN = ("", "cloth", "leather", "hide", "chain")

#: "The offhand property", as `Weapon.properties` spells it.
_OFF_HAND = "off-hand"

#: What a `-fNsM` row says when the leg it belongs to is not the one taken.
_NOT_MY_OPTION = "needs the option this belongs to"


def _tier(level: int) -> int:
    """0, 1 or 2 -- the step these ladders climb at 11 and at 21."""
    return (level >= 11) + (level >= 21)


def _row(ctx: dict[str, Any]) -> Any:
    """Whatever row is rolling, off either the attack or the damage context.

    Both spell it `power` and both carry a ref rather than a `Power`, so one
    reader serves the two sides and a gate cannot silently read a key its
    context does not have.
    """
    return get(ctx.get("power") or "")


def _weapon_row(ctx: dict[str, Any]) -> bool:
    """"A weapon attack roll"."""
    p = _row(ctx)
    return p is not None and Keyword.WEAPON in p.keywords


def _light_or_chain(c: Cast) -> bool:
    """"When wearing light armor or chainmail"."""
    gear = c.world.get(c.me, Gear)
    return gear is None or gear.armour in _LIGHT_OR_CHAIN


# ----------------------------------------------------------------- avenger

#: How many allies can stand next to one creature. Eight squares touch a
#: Medium one, and the bonus below is laid once per square rather than once
#: because `c.bonus` takes a fixed number and the count is only known when
#: the damage is rolled.
_CROWD = 8


@power(
    "cf:avenger-f1s2",
    level=0,
    cls="avenger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def avenger_censure_crowd(c: Cast) -> None:
    """The third arm of the censure: the sworn enemy is worth more when it
    is surrounded.

    This is the arm `cf:avenger-f1` names in its docstring and leaves out.
    The other two are told apart by the ability each reads, and this one
    reads no ability at all -- so it needed a leg of its own rather than a
    secondary to share, and `chargen.BUILDS["avenger"]` now has one. Until
    it did, this armed for every avenger alongside whichever arm the leg
    took, which is two censures on one character.

    "For each ally adjacent to that target" is a count taken when the damage
    is rolled, and `c.bonus` takes a number decided when it is laid. So the
    bonus is laid eight times -- once per square that can touch a Medium
    creature -- and the *k*th copy is gated on there being at least *k*
    allies there. Untyped, so they add, and the total is the count.

    The gate asks who is sworn at the moment the damage is rolled rather
    than closing over a creature, because half a dozen rows in the class
    re-swear mid-fight and a closure would keep paying out against whoever
    was sworn first.
    """
    if not c.build("unity"):
        return
    me, world = c.me, c.world
    each = 1 + _tier(c.level)

    def crowd(ctx: dict[str, Any]) -> int:
        victim = ctx.get("target")
        if victim is None or not sworn(world, me, victim):
            return 0
        return sum(
            1
            for friend in allies(world, me)
            if friend != me and distance_between(world, friend, victim) <= 1
        )

    for k in range(1, _CROWD + 1):
        c.bonus(
            "damage", each, until=When.ENCOUNTER, on=me,
            when=lambda ctx, k=k: crowd(ctx) >= k,
        )


@power(
    "cf:avenger-f2",
    level=0,
    cls="avenger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def avenger_channel(c: Cast) -> None:
    """The channelled-power allowance, which is a header field and not a body.

    The feature prints one mechanical sentence -- "regardless of how many
    different uses you know, you can use only one per encounter" -- and that
    sentence is a budget shared across a set of rows. `group=` is the field
    that says so and `dsl._group_spent` is what enforces it: `usable`
    refuses a row whose group sibling has already been spent this fight.
    Every channelled row in the tree declares `group=CHANNEL_DIVINITY`,
    including the two covenant cards below.

    So there is nothing left for this row to lay, and it is inert on purpose
    rather than unwritten. It is **not** `todo`: a marker here would refuse
    a row that has no work to do and would go red against a symbol that
    already exists.
    """


@power(
    "cf:avenger-f3",
    level=0,
    cls="avenger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def avenger_oath_grant(c: Cast) -> None:
    """One sentence: the avenger gains `p3069`.

    Not a second copy of that card -- the card itself is `p3069` and stays
    there; this is the feature that hands it over. `chargen.loadout` deals a
    class every level 0 row it has, so the grant is a no-op for an avenger
    the generator built, and it is written anyway because a creature
    assembled any other way has the feature and would not have the row.

    Nothing is taken away from anybody here: unlike
    `cf:fighter-weaponmaster-f0`, this is not one of a mutually exclusive
    set, so there is no leg that should be without it.
    """
    c.grant_row("p3069")


# ------------------------------------------------------------------- druid


@power(
    "cf:druid-f0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    out_of_combat=True,
)
def druid_balance(c: Cast) -> None:
    """A rule about which at-wills may be chosen, and nothing else.

    "One of your three, and no more than two, must be a beast form power"
    is a constraint on the loadout, so it belongs to `chargen` and there is
    nothing for a trait armed at the start of a fight to do. Inert on
    purpose, like `cf:druid-f2`.

    Worth saying because it could not be written even if somebody wanted to:
    there is no beast form keyword. `forms.beast_row` reads the printed
    keyword off a row's `requires` gate instead, which is a fight-time
    question and not a selection-time one.
    """


@power(
    "cf:druid-f1s2",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def druid_aspect_thick(c: Cast) -> None:
    """Melee and ranged attacks land softer while this druid is a beast.

    One of the two arms `cf:druid-f1` leaves out, and **the leg exists after
    all**. This row went in ungated, arming for every druid, on the reading
    that the two arms are told apart only by the ability each reads -- and
    this one reads Constitution just as one of those does, so no *derived*
    leg separates them. True, and beside the point: `BUILDS["druid"]`
    carries four real sub-option legs, `f1s0`-`f1s3`, and `Build.choices`
    puts `leg.name` on the character verbatim. So `c.build("f1s2")` names
    this aspect exactly, whatever ability pair it shares with a sibling.

    The idiom was already in the tree when this was written --
    `powers/bard/level_7_b.py:231` is `c.build("f1s2") and c.con_mod > 0`,
    which is this row's gate to the letter.

    Reduction rather than a condition, so `c.resist` with no damage type:
    the printed line takes a number off the damage whatever the damage is.
    It is gated instead of filtered, because "from either type of attack"
    is about the *attack* and not about the harm.

    **The gate reads the row, because the damage context has nothing else.**
    That context carries `target`, `power`, `opportunity` and `charge` --
    no attacker and no `ranged` flag -- so "a melee attack or a ranged
    attack" has to be asked as `reach.kind`, which is what `power` is there
    for. Anything that is neither, an area or a close burst, is not reduced,
    and that is the printed sentence rather than an approximation of it.

    Beast form and the armour are asked inside the gate rather than outside
    it: the trait is armed at the start of the fight and the druid changes
    shape all through it, so a check at arming time would answer for the
    wrong shape.
    """
    me, world = c.me, c.world
    if not c.build("f1s2") or c.con_mod <= 0:
        return

    def softened(ctx: dict[str, Any]) -> bool:
        p = _row(ctx)
        if p is None or p.reach.kind not in _MELEE_OR_RANGED:
            return False
        return in_beast_form(world, me) and out_of_heavy_armour(c)

    c.resist(c.con_mod, until=When.ENCOUNTER, on=me, when=softened)


#: The four elements the last aspect sharpens. Read off the row's keywords,
#: which is where a printed keyword lives.
_ELEMENTS = (Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING, Keyword.THUNDER)


@power(
    "cf:druid-f1s3",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def druid_aspect_storm(c: Cast) -> None:
    """A square of accuracy with the elemental half of the class's list.

    The other arm `cf:druid-f1` leaves out, and the one that reads no
    ability at all. That was taken to mean nothing in
    `chargen.BUILDS["druid"]` distinguishes it, and it is the same mistake
    `cf:druid-f1s2` made: an aspect is a **named** sub-option leg, not an
    ability pair, and `c.build("f1s3")` asks for it directly. Reading no
    ability is exactly why the derived fork cannot see it and exactly why
    the leg name has to be the gate.

    "Druid attack powers and druid paragon path attack powers" is `cls` and
    `is_attack` on the row that is rolling; the project stops at 10, so the
    paragon clause is the same test and adds nothing to write.

    Untyped: the card prints "+1 bonus" with no type word in front of it.
    """
    me = c.me

    def elemental(ctx: dict[str, Any]) -> bool:
        p = _row(ctx)
        if p is None or p.cls != "druid" or not p.is_attack:
            return False
        return any(word in p.keywords for word in _ELEMENTS)

    if c.build("f1s3") and out_of_heavy_armour(c):
        c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=elemental)


@power(
    "cf:druid-f3",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def druid_shape_grant(c: Cast) -> None:
    """One sentence: the druid gains `p5032`.

    The feature, not the card -- the card is `p5032` and stays there. A
    no-op for a druid `chargen` built, and written for the same reason
    `cf:avenger-f3` is. The rest of the printed paragraph describes what the
    form looks like, which the card itself says has no effect on the
    statistics, so there is nothing else in it.
    """
    c.grant_row("p5032")


# ----------------------------------------------------------------- fighter


@power(
    "cf:fighter-weaponmaster-f3s0",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg("arena"),
    requires_text=_NOT_MY_OPTION,
    dropped=(
        "c.improvised()",
        "Weapon.proficiency",
        "c.chosen_weapon_group()",
    ),
)
def fighter_talent_arena(c: Cast) -> None:
    """The talent that fights with whatever is to hand.

    One of the three `cf:fighter-weaponmaster-f3` leaves out, and its leg
    already exists -- `chargen.BUILDS["fighter"]` has all six -- so the
    header asks for it and the parent never fires for this leg.

    The AC half is written and is the whole of what the engine can say. The
    other three clauses are dropped, each naming what it wants:

    * A weapon the wielder is not proficient with counts as improvised, and
      an improvised weapon deals 1d8 or 1d10 with a +2 to hit. There is no
      improvised weapon at all -- `c.improvised()` is already the symbol
      other rows wait on -- and `Weapon.proficiency` is a column, not
      something a feature can raise.
    * Two chosen weapons become proficient. `c.chosen_weapon_group()` is the
      standing request for "a weapon this character picked at build time".
    * Feat bonuses earned for one of the two apply to the other. This used
      to be marked `feat.associated_powers`, which was simply the wrong
      symbol -- this card prints no Associated Powers list and the clause
      is not about one. It is downstream of the bullet above: until a
      character records which two weapons it chose there is no "other" to
      carry a bonus to, so `c.chosen_weapon_group()` is the whole of the
      hold and the marker says it once.

    The AC bonus is untyped -- the card prints "+1 bonus" with no type word
    -- and climbs the usual ladder. A fighter's chassis wears scale, so the
    gate is false today; it is asked anyway because it is the card's own
    sentence and another row can change what is worn.
    """
    if out_of_heavy_armour(c):
        c.bonus(AC, 1 + _tier(c.level), until=When.ENCOUNTER, on=c.me)


#: "An axe, a hammer, a mace, or a pick", as `Weapon.group` spells them.
_BATTLERAGER_GROUPS = ("axe", "hammer", "mace", "pick")


@power(
    "cf:fighter-weaponmaster-f3s1",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg("battlerager"),
    requires_text=_NOT_MY_OPTION,
    dropped=("Keyword.INVIGORATING", "c.temp_hp(add=)"),
)
def fighter_talent_battlerager(c: Cast) -> None:
    """The talent that feeds on landing a blow.

    Three clauses. `cf:fighter-weaponmaster-f3` lays the first of them on
    this same leg and names the third as unwritten, so this row is not a
    restatement of it -- see the note at the top of the file for why
    repeating the first one is free.

    **The pool is laid after the blow, which is the printed "only after the
    attack is resolved".** A `Hit` watch at the default window is already
    past the swing it answers.

    **The damage half is two mutually exclusive bonuses, not a +1 and a
    gated +1.** Written as two that can both be true they would come to +1
    forever, because the larger of two same-kind bonuses wins; written as a
    +1 and a gated +2 the engine would have to be trusted to prefer the
    second. Gating one on the four weapon groups and the other on *not*
    them makes the question moot, and "wielding" is read off either hand
    because that is the word the card uses rather than "attacking with".

    "Whenever you have temporary hit points" is asked inside the gate, when
    the damage is rolled, rather than latched when the trait arms -- the
    pool comes and goes several times in a fight. A fighter's chassis wears
    scale, so `_light_or_chain` is false for every fighter in the tree today
    and this half lays nothing; it is asked anyway, the way
    `cf:fighter-weaponmaster-f3s0`'s armour gate is, because another row can
    change what is worn.

    Two clauses are dropped. The invigorating keyword does not exist, so
    "you use an invigorating attack power and miss every target" has no
    first half to test -- `Keyword.INVIGORATING` is the symbol five feats
    already wait on. And "plus any temporary hit points normally granted by
    the power" needs two pools to **add**, which is a printed exception to
    the rule `resolve.temp_hp` keeps: it takes the larger and returns, so a
    power granting 5 beside a Constitution modifier of 3 leaves 5 where the
    card says 8. `c.temp_hp(add=)` is what that wants.
    """
    me, world = c.me, c.world

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me:
            return
        dealt = get(ev.power)
        if dealt is not None and dealt.reach.kind in _MELEE_OR_CLOSE:
            c.temp_hp(c.con_mod, on=me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=c.ref)

    if not _light_or_chain(c):
        return

    def fed_and_in_close(ctx: dict[str, Any]) -> bool:
        p = _row(ctx)
        if p is None or Keyword.WEAPON not in p.keywords:
            return False
        if p.reach.kind not in _MELEE_OR_CLOSE:
            return False
        health = world.get(me, Health)
        return health is not None and health.temp > 0

    def heavy_grip() -> bool:
        gear = world.get(me, Gear)
        if gear is None:
            return False
        return any(
            held is not None and held.group in _BATTLERAGER_GROUPS
            for held in (gear.main, gear.off)
        )

    c.bonus(
        "damage", 2, until=When.ENCOUNTER, on=me,
        when=lambda ctx: fed_and_in_close(ctx) and heavy_grip(),
    )
    c.bonus(
        "damage", 1, until=When.ENCOUNTER, on=me,
        when=lambda ctx: fed_and_in_close(ctx) and not heavy_grip(),
    )


@power(
    "cf:fighter-weaponmaster-f3s2",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg("brawling"),
    requires_text=_NOT_MY_OPTION,
    dropped=("c.off_hand()", "c.on_grab_attack()"),
)
def fighter_talent_brawling(c: Cast) -> None:
    """The talent that keeps one hand empty for grabbing people.

    The second of the three `cf:fighter-weaponmaster-f3` leaves out.

    The two defences are written. The three attack bonuses are dropped and
    the symbols say why: `c.off_hand()` is the standing request for "the
    attack was made with the empty hand", which is what the unarmed bonus
    needs and which no attack context carries, and `c.on_grab_attack()` is
    the same for a grab attempt and for an attack to move whoever is already
    held. Without either, all three would have to be laid on every attack
    roll, which is a much larger number than the card prints.

    The Requirement is read once, when the trait is armed, so a fighter who
    puts a second weapon in hand mid-fight keeps the bonus. That is the same
    limitation every armour gate in this tree has, and is recorded rather
    than worked around.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.main is None:
        return
    # "Your off hand is free or grabbing a creature." A shield occupies it
    # just as a second weapon does.
    free = gear.off is None and not gear.shield
    if not free and not c.grabbing():
        return
    c.bonus(AC, 1, until=When.ENCOUNTER, on=c.me)
    c.bonus(FORT, 2, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:fighter-weaponmaster-f3s4",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg("tempest"),
    requires_text=_NOT_MY_OPTION,
    dropped=("c.off_hand()",),
)
def fighter_talent_two_weapon(c: Cast) -> None:
    """The talent for fighting with a weapon in each hand.

    The last of the three `cf:fighter-weaponmaster-f3` leaves out.

    **The attack bonus is exact, and the damage step is not, and the
    difference is one key.** The attack context carries `hand`, so "with
    weapons that have the offhand property" is the hand that swung and the
    property on the weapon in it, asked outright. The damage context does
    not carry it -- it has `target`, `power`, `opportunity`, `charge`,
    `dtype`, `crit`, `advantage` and `ranged`, and no hand -- so the step
    from +1 to +2 has nothing to gate on. Rather than approximate it off
    `Gear.main`, which would pay the larger number on main-hand swings of a
    fighter whose main weapon happens to carry the property, the step is
    **dropped** and `c.off_hand()` names what it wants. The +1 is written
    and plays.

    The bonus feat is `c.feat`, which is the verb for "you gain <feat> even
    if you don't meet the prerequisites": it does not consult
    `chargen.meets`, which is the printed exception.
    """
    me, world = c.me, c.world
    gear = world.get(me, Gear)
    if gear is None or not gear.two_weapon:
        return

    c.feat("f172", on=me)

    def swung_off_hand(ctx: dict[str, Any]) -> bool:
        if not _weapon_row(ctx) or ctx.get("hand") != "off":
            return False
        held = world.get(me, Gear)
        spare = held.off if held is not None else None
        return spare is not None and _OFF_HAND in spare.properties

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=swung_off_hand)

    if not _light_or_chain(c):
        return

    def melee_weapon(ctx: dict[str, Any]) -> bool:
        p = _row(ctx)
        return (
            p is not None
            and Keyword.WEAPON in p.keywords
            and p.reach.kind in _MELEE_OR_CLOSE
        )

    c.bonus("damage", 1, until=When.ENCOUNTER, on=me, when=melee_weapon)


# ----------------------------------------------------------------- invoker


@power(
    "cf:invoker-f0",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def invoker_channel(c: Cast) -> None:
    """The same allowance `cf:avenger-f2` prints, word for word.

    A separate row because it is a separate class's feature, not a second
    copy of one: neither class page's feature is declared anywhere else.
    Inert for the same reason -- the one mechanical sentence is
    `group=CHANNEL_DIVINITY` on each channelled row, which
    `dsl._group_spent` enforces, and the two covenant cards below declare
    it.
    """


_ALLY_STRUCK = "an enemy within 10 squares of you hits your ally"


def _ally_struck_near_me(world: World, me: int, ev: Hit) -> bool:
    if ev.target == me or ev.attacker == me:
        return False
    if team(world, ev.target) is not team(world, me):
        return False
    if team(world, ev.attacker) is team(world, me):
        return False
    return distance_between(world, me, ev.attacker) <= 10


@power(
    "cf:invoker-f1c0",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    group=CHANNEL_DIVINITY,
    trigger=_ALLY_STRUCK,
    on=Trigger(Hit, _ally_struck_near_me, _ALLY_STRUCK),
)
def invoker_covenant_card_a(c: Cast) -> None:
    """The channelled card one covenant hands over: an answer to seeing a
    friend hit.

    New, not a second spelling of anything: the two channelled invocations
    the class list already carries are `p5186` and `p7150`, and neither is
    an immediate reaction, neither is personal, and neither reads
    Intelligence.

    `Hit` and not `AttackDeclared`: the printed trigger is the blow landing,
    and a declaration that an interrupt cancels never hits anybody.

    "Your next attack roll against the triggering enemy" is `once=True`,
    which spends the bonus on the first roll that satisfies the gate rather
    than on the first roll of any kind. The window is `When.EONT`, which is
    the printed "before the end of your next turn" exactly.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or c.int_mod <= 0:
        return
    c.bonus(
        "attack", c.int_mod, until=When.EONT, on=c.me, once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


_STRUCK_ME = "an enemy within 5 squares of you hits you"


def _struck_me_near(world: World, me: int, ev: Hit) -> bool:
    if ev.target != me or ev.attacker == me:
        return False
    if team(world, ev.attacker) is team(world, me):
        return False
    return distance_between(world, me, ev.attacker) <= 5


@power(
    "cf:invoker-f1c1",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
    group=CHANNEL_DIVINITY,
    trigger=_STRUCK_ME,
    on=Trigger(Hit, _struck_me_near, _STRUCK_ME),
)
def invoker_covenant_card_b(c: Cast) -> None:
    """The channelled card the other covenant hands over: a burn for whoever
    landed the blow. New for the reason the first one is.

    "The triggering enemy in the burst" is not something the targeting layer
    can pick, so the row reads the creature off its own trigger and aims
    there with `on=`, guarded by `c.first` so a second target in the burst
    does not burn it twice. Aiming at `c.target` and returning otherwise
    would have made the row silently do nothing whenever the engine chose
    somebody else.

    `c.flat` rather than `c.damage`: the printed line is a modifier and not
    a die, so there is nothing for a critical to maximise.

    The Level 11 and Level 21 lines add dice and are paragon; the project
    stops at 10, so they are out of scope rather than missing.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.first:
        return
    c.flat(c.con_mod, dtype=DamageType.RADIANT, on=foe)
    c.push(2, on=foe)


#: "A divine encounter or daily **attack** power", as the header fields that
#: say so. The same test `cf:invoker-f1` makes, restated here because this
#: file must not reach into that one for a private.
_MANIFESTING = (Usage.ENCOUNTER, Usage.DAILY)


def _manifests(ref: str) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.DIVINE in p.keywords
        and p.usage in _MANIFESTING
        and p.is_attack
    )


@power(
    "cf:invoker-f1s0",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    requires=on_leg("malediction"),
    requires_text=_NOT_MY_OPTION,
)
def invoker_covenant_curse(c: Cast) -> None:
    """The covenant whose manifestation shoves whoever was hit.

    Not a restatement of `cf:invoker-f1`: that row reads two legs and
    returns for this one, so the third covenant has never manifested. It
    does lay *this* push on the leg named for the other covenant, which is
    the wrong arm of the fork -- reported, not fixed here.

    **`PowerResolved`, not `PowerUsed`.** The printed line is "after the
    power's effect is resolved", and `PowerUsed` is announced before the
    body runs -- a push hung there would land before the damage it is meant
    to follow. `PowerResolved.rolls` is also the only place that says which
    targets were *hit*, which this half needs and which no other event
    carries for a whole use at once.

    "On your turn" is `c.turn_of`: an invocation used off an immediate
    action in somebody else's turn does not manifest.

    **The channelled power is `p7150`, and the old note here was wrong about
    it.** It said `p5186` and `p7150` "belong to neither of the two covenants
    below", so reaching for one would be granting the wrong row. In fact
    `p7150` is this covenant's own channelled invocation -- the names line up
    and the ref was there all along -- so it is granted, and the row no longer
    carries a marker for a ref it had.
    """
    me = c.me
    c.grant_row("p7150", on=me, until=When.ENCOUNTER)

    def after(ev: PowerResolved) -> None:
        if ev.actor != me or c.turn_of() != me or not _manifests(ev.power):
            return
        struck = [
            r.target
            for r in ev.rolls
            if getattr(r, "hit", False) and alive(c.world, r.target)
        ]
        who = c.choose(
            sorted(dict.fromkeys(struck)),
            f"{c.ref}: which target is pushed",
            optional=True,
        )
        if who is not None:
            c.push(1, on=who)

    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:invoker-f1s2",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    requires=on_leg("wrath"),
    requires_text=_NOT_MY_OPTION,
)
def invoker_covenant_wrath(c: Cast) -> None:
    """The covenant whose manifestation pays for hitting a crowd.

    Not a restatement either, and this is the one worth checking twice:
    `cf:invoker-f1` does fire for this leg, but what it lays there is the
    *other* covenant's push. This manifestation -- a damage bonus counting
    the enemies the invocation caught -- is written nowhere. The parent's
    mis-mapping is in the report.

    **`PowerUsed` here, and `PowerResolved` on the other covenant.** This
    manifestation is a bonus to the invocation's *own* damage roll, so it
    has to be laid before the body rolls it; `PowerResolved` is announced
    after, and a bonus laid there would pay out on the next power instead.
    `PowerUsed` fires above `p.body(cast)` and its targets are chosen before
    the body, so the count is trustworthy in that window even though
    nothing the body *does* is.

    The bonus is gated on the ref that is rolling and expires at the end of
    the turn, rather than `once=True`: the printed line is one bonus for the
    whole power, and a power that hits three creatures rolls damage three
    times.

    The channelled card this covenant hands over is `cf:invoker-f1c1`, which
    the spec labels with this covenant's own name -- the first thing in the
    tree to say which channelled invocation belongs to which covenant.
    `cf:invoker-f1` had to leave the pairing out for want of exactly that.
    """
    me = c.me
    # The other covenant's card is in every invoker's loadout already --
    # both are level-0 rows of the class -- so what this leg has to say is
    # that it does not have that one. `cf:invoker-f1` says the mirror of it.
    c.grant_row("cf:invoker-f1c1")
    c.forbid("cf:invoker-f1c0", until=When.ENCOUNTER, on=me)

    def before(ev: PowerUsed) -> None:
        if ev.actor != me or c.turn_of() != me or not _manifests(ev.power):
            return
        count = sum(1 for who in ev.targets if who in c.enemies())
        if count <= 0:
            return
        ref = ev.power
        c.bonus(
            "damage", count, until=When.EOT, on=me,
            when=lambda ctx: ctx.get("power") == ref,
        )

    c.watch(PowerUsed, before, until=When.ENCOUNTER, on=me, label=c.ref)
