"""Barbarian feats, the second batch. 19 rows, 4 of them still waiting.

**This docstring described a state the file left, and said so in its own
first sentence.** It opened *"`Keyword.RAGE` does not exist, so 'while
raging' is not a state anything can ask about. Six rows here want it"* --
while `f1858`'s own note further down reads *"Re-pointed: `Keyword.RAGE`
exists now (#503)"*. It does exist, and **no row in this file waits on it**;
the six mentions of `RAGE` are rows reading the keyword, not rows blocked on
it. Rewritten from the markers the file actually carries. #838.

What is actually left, by marker, one row each:

* `Gear.ranged(thrown=)` -- a weapon made throwable. The old text named
  `c.make_thrown()` and `c.weapon_range()` for this, and the second is the
  trap `#838` is about: `c.weapon_range` sets `Weapon.thrown` on the
  character's own copy and buys the row nothing, because whether a power
  offers a thrown branch is decided by `thrown_by_hand`, a **header field on
  the power**. The two notes further down say this per row.
* `chargen.IMPROVISED` -- a chair leg swung as a weapon.
* `c.choose(before_damage=)`
* `Defences.immune_keywords`

The other fifteen play.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.barbarian.rage import in_rage
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    PowerRecharged,
    PowerUsed,
    SecondWind,
    Trigger,
    TurnEnd,
    When,
    about_me,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import distance_between, team


def _used_one_of(*refs: str):  # noqa: ANN202
    """`PowerUsed` for any of several named rows, by this creature.

    `_i_used` above takes one ref; two cards here print a pair, and asking
    twice with two Triggers would fire the row twice when both are somehow
    used in one window.
    """

    def check(world, me: int, ev) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return check


def _took_the_charge(world, me: int, ev: object) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p4809"

#: "Instead of": a printed swap for something a class feature does inside
#: its own body. The feature has a ref now; declining half of what it does
#: is the operation nothing has.
INSTEAD = ("c.pre_empt(ref, clause)",)

_DEFENCES = (AC, FORT, REF, WILL)


def _i_used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _my_fear_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "barbarian"
        and Keyword.FEAR in p.keywords
    )


def _i_bloodied_it(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """Damage from a barbarian attack power of mine that took a creature
    across the halfway mark.

    `Bloodied` carries `source` now, but not the row that did it, so the
    crossing is still worked out from the blow: `DamageApplied.hp` is what
    is left afterwards and `amount` is what landed, so the hit points
    before it are their sum. `detail` is the ref of the row that dealt the
    damage -- `c.damage` stamps it with the caster's own ref -- which is
    where "with a barbarian attack power" is read.
    """
    if ev.source != me or ev.target == me or ev.amount <= 0:
        return False
    p = get(ev.detail)
    if p is None or p.cls != "barbarian" or not p.is_attack:
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return ev.hp > 0 and ev.hp <= half < ev.hp + ev.amount


# -- the rows that turn on something the board announces -------------------


@power("f1879", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1879(c: Cast) -> None:
    """A plain "+2 bonus", so untyped.

    `c.marked(on=c.me, by=them)` is the question -- `c.marked(on=them)`
    would ask whether *I* have marked *it*, which is the opposite
    sentence. The mark is asked per attack because it comes and goes.
    """
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.marked(on=c.me, by=ctx["target"])
        ),
    )


@power("f2204", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4932",
       on=Trigger(PowerUsed, _i_used("p4932"), "you use p4932"))
def f2204(c: Cast) -> None:
    """Allies in that feature's burst, which is not the same set as its
    targets -- it targets enemies. So the radius is read off the row's
    own header rather than guessed, and the allies standing inside it
    are found from the board."""
    p = get("p4932")
    radius = p.reach.size if p is not None else 5
    for friend in c.within(radius, side="ally"):
        for defence in _DEFENCES:
            c.bonus(defence, 1, on=friend, until=When.EONT)


@power("f2706", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2706(c: Cast) -> None:
    """Extra damage with one named row at exactly 2 squares.

    Both halves of the gate are asked per damage roll rather than when
    the trait is armed: a weapon can be swapped and the distance is the
    whole point of the clause. The damage context carries `power` and
    `target`, which is exactly the pair this needs.

    **The row named is `cf:barbarian-f2c0`.** The spec names it `p4807`,
    which is declared nowhere: the same card is declared under the feature
    ref that prints it, so the gate was false in every fight and said
    nothing about why. `cf:barbarian-f2c0` carries its own marker, so the
    clause is still inert -- but it is inert against a row that exists and
    goes live the day that row does.
    """
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") == "cf:barbarian-f2c0"
            and c.wielding("two-handed")
            and c.wielding("reach")
            and ctx.get("target") is not None
            and distance_between(c.world, c.me, ctx["target"]) == 2
        ),
    )


@power("f2792", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a barbarian fear power",
       on=Trigger(Hit, _my_fear_hit,
                  "you hit with a barbarian fear power"))
def f2792(c: Cast) -> None:
    """"A barbarian fear attack power" is two header fields and no
    naming gap at all: the class and the fear keyword."""
    c.push(1, on=c.trigger.target)


@power("f2883", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you bloody an enemy with a barbarian attack power",
       on=Trigger(DamageApplied, _i_bloodied_it, "you bloody an enemy"))
def f2883(c: Cast) -> None:
    """Both halves land now.

    The clause naming the row was dropped on the reading that nothing
    says which power dealt a blow; `DamageApplied.detail` does, and the
    predicate reads it. `Bloodied` is still the wrong event to hang this
    on -- it announces the crossing and not the amount, so the halfway
    line has to be re-derived from `hp` and `amount` either way.
    """
    c.temp_hp(c.cha_mod, on=c.me)


# -- rage, which nothing declares ------------------------------------------


@power("f1831", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1766 or p1769",
       on=Trigger(PowerUsed, _used_one_of("p1766", "p1769"),
                  "you use one of those racial powers"))
def f1831(c: Cast) -> None:
    """+2 to attack rolls until the end of your next turn, after one of two
    racial powers, **while raging**.

    Its own note said the rage gate was what was left and that "a row that
    paid out of rage as well as in it would be wrong in every fight". The
    gate existed: `rage.in_rage()` -- see the note on `RAGE` above. #503.
    """
    if in_rage(c):
        # No `kind=`: the card prints no word in front of "bonus", so it is
        # untyped and stacks. Fourth time this slipped past me in one
        # session, and `bonuses.py` is the only thing that reads the card.
        c.bonus("attack", 2, on=c.me, until=When.EONT)


@power("f1858", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.choose(before_damage=)",))
def f1858(c: Cast) -> None:
    """Trade a die of weapon damage for ongoing damage, on a hit with
    "any rage power". Which rows those are is the same gap: nothing
    marks a row as one.

    **Re-pointed: `Keyword.RAGE` exists now (#503).** "Any rage power" is
    askable. What is left is the printed *option* -- reducing the damage
    by 1[W] **before you roll it** -- which is a choice put to the holder
    at a moment nothing currently offers one.
    """


@power("f1991", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1991(c: Cast) -> None:
    """+1 to damage rolls while raging, and +1 more for each nearby ally
    holding a feat of this feat's own printed category.

    **The old note was half right and the half that mattered was wrong.**
    `c.feat(ref)` does ask about one feat by ref, but feats are not
    ungrouped: `feat.category` is a column in `game.db` -- the bracket
    after a printed name -- and `c.feats(category=, on=)` reads it for
    somebody *else*, which is the half that makes "nearby allies" askable
    rather than only "you". #692. Ten feats carry this one.

    **One gated +1 per ally, not one bonus of a counted size.** The count
    is read when the damage is rolled, not when the trait is armed, and
    allies move; `c.bonus` takes a fixed `value`, so the live read has to
    sit in a `when=` gate, and untyped bonuses add -- which is what makes a
    stack of +1s come to the printed total. The *pool* is walked once at
    arming, because who holds which feat cannot change inside a fight,
    where who is standing within 10 squares can.

    No melee narrowing and no bonus type, both as printed: the card says
    "damage rolls" and puts no word in front of "bonus".
    """
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: in_rage(c))
    for mate in c.allies():
        if not c.feats(category="Tribal", on=mate):
            continue
        c.bonus(
            "damage", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx, who=mate: (
                in_rage(c) and who in c.within(10, side="ally")
            ),
        )


@power("f2296", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2296(c: Cast) -> None:
    """+2 melee damage while raging, and 2 damage to yourself if you end a
    turn having hurt nobody.

    The self-harm half was always writable; what the docstring said it
    lacked was the rage gate, "without which it would bite every turn of the
    fight". `rage.in_rage()` was that gate all along -- see the note on
    `RAGE` above. Both halves carry it, so a barbarian not raging neither
    gains the bonus nor pays for it. #503.
    """
    step = 2 + (c.level >= 11) + 2 * (c.level >= 21)
    c.bonus(
        "damage", step, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: in_rage(c) and not ctx.get("ranged"),
    )
    hurt = {"any": False}

    def dealt(ev: Hit) -> None:
        if ev.attacker == c.me:
            hurt["any"] = True

    def settle(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != c.me:
            return
        if in_rage(c) and not hurt["any"]:
            c.flat(step, on=c.me)
        hurt["any"] = False

    c.watch(Hit, dealt, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} dealt")
    c.watch(TurnEnd, settle, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} toll")


@power("f2705", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2705(c: Cast) -> None:
    """Reroll any weapon damage die showing a 1, while raging and wielding a
    two-handed reach weapon.

    **Written, and no verb was needed.** `c.reroll_ones` takes no `when=`,
    but it is one line -- `self.bonus("reroll_damage_below...", below,
    stacks=False)` -- and `c.bonus` has always taken a gate, which
    `Mods.total` asks on every read. So the hold is laid through the verb
    and the gate is set on the modifier it laid, rather than by
    hand-writing the engine's own key here: `reroll_ones` is the only
    thing that knows how the keyword narrowing is spelled.

    `keyword=Keyword.WEAPON` is the "weapon damage die" half --
    `_reroll_floor` asks the *rolling* row for its keywords -- and the two
    standing conditions are read inside the gate rather than when the
    trait arms, exactly as `f2707` reads the same grip: a barbarian can
    change hands and can stop raging.

    **"When making melee attacks" is carried by the grip, not asked.**
    `_reroll_floor` reads the hold with no context at all, so there is no
    `kind` for a gate to look at. It costs nothing here: both hands are on
    the weapon, so `Gear.ranged` is empty and `can_branch` refuses every
    ranged weapon branch, and the class prints no ranged weapon row to
    begin with. #503.
    """
    def armed(_ctx: dict[str, Any]) -> bool:
        return in_rage(c) and c.wielding("two-handed") and c.wielding("reach")

    held = c.reroll_ones(keyword=Keyword.WEAPON, on=c.me)
    for _owner, mod in held.mods if held is not None else ():
        mod.when = armed


@power("f2885", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you take a second wind"))
def f2885(c: Cast) -> None:
    """Charisma modifier in extra hit points from a second wind taken while
    raging.

    **It was never blocked.** The docstring said "nothing says a barbarian
    is raging"; `powers/barbarian/rage.py` has exported `raging()` and
    `in_rage()` the whole time, with a module docstring stating that two
    dozen rows print the requirement and something has to answer them. See
    the note on `RAGE` above. #503.
    """
    if in_rage(c):
        c.heal(c.cha_mod, on=c.me)


# -- class features named in prose -----------------------------------------


@power("f1834", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4809",
       on=Trigger(PowerUsed, _took_the_charge, "you take that free charge"))
def f1834(c: Cast) -> None:
    """The prerequisite's feature hands over `p4809`, and that row's whole
    printed effect is "you charge an enemy" -- so the charge this rides on
    is the one it is about to make.

    The swing itself is announced under the basic attack's ref, not under
    `p4809`, so the hit is matched on `charge` and narrowed by the window
    instead: the watch is laid when `p4809` is used and dies with the turn,
    and a hand-rolled latch spends it on the first charging hit rather than
    on the first hit of any kind -- `c.watch(once=True)` would be spent by
    an event that did not match.
    """
    me = c.me
    spent: list[int] = []

    def landed(ev: Hit) -> None:
        if spent or ev.attacker != me or not getattr(ev, "charge", False):
            return
        spent.append(1)
        c.push(1, on=ev.target)

    c.watch(Hit, landed, until=When.EOT, on=me, label=c.ref)


@power("f1878", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1878(c: Cast) -> None:
    """Shift Dexterity modifier squares instead of 2, on `cf:barbarian-f1s3`.

    **`c.extend_every`, not `c.extend_move`, and that is the whole of what
    unblocked it.** The old note was right that the feature says
    `c.shift(2, who=me)` with the number in hand and so reads no
    `c.squares_for` -- and that only blocks the ref-keyed verb.
    `c.extend_every` is read inside `c.shift` itself and asks its gate with
    `ctx["power"]`, which is the **moving row's own ref**, so the one row
    this card names is sayable as a gate and the feature needs no change at
    all. `f2263` and `f2469` are the same arrangement for "a swordmage
    power" and "a martial encounter or daily power"; a single ref is the
    narrowest case of it, not a different problem.

    `dex_mod - 2` because the entries add: the card replaces the printed 2
    rather than adding to it. Guarded at positive, so a barbarian whose
    modifier is below 2 keeps the printed shift -- the card says "you can",
    and nothing printed is made worse by holding a feat.

    The budget is raised rather than a second step taken, for the reason
    the old note gave and which still holds: the feature measures who
    grants combat advantage *from where its shift ended*, so stepping
    further afterwards would read the wrong squares and prompt twice for
    one printed shift.

    The feature's own prompt still reads "shift 2 squares" while the
    budget is larger. That text is in a file this change does not touch
    and it is wording, not distance -- `c.shift` offers every square the
    raised budget reaches."""
    extra = c.dex_mod - 2
    if extra <= 0:
        return

    def the_whirl(ctx: dict[str, Any]) -> bool:
        return ctx.get("power", "") == "cf:barbarian-f1s3"

    c.extend_every("shift", extra, on=c.me, when=the_whirl)


@power("f1880", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1880(c: Cast) -> None:
    """Five more thunder off the same bloodying `cf:barbarian-f1s2` answers.

    Laid as its own burn on the same event rather than reached into the
    feature: the feature's amount is a literal in its closure. That makes
    two thunder instances where the card prints one, which differs only
    against thunder resistance.

    The once-a-round latch is keyed on the world's round exactly as the
    feature keys its own, so the two fire together and never apart. The
    leg is not asked again -- `chargen.meets` has already checked the
    feature is held, and the feature checks the leg.
    """
    me = c.me
    paid: dict[int, int] = {}

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if ev.source != me or team(c.world, victim) is team(c.world, me):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        for foe in c.within(1, side="enemy"):
            c.flat(5, dtype=DamageType.THUNDER, on=foe)

    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


#: The class feature both rows below ride on. Its body calls `c.basic`,
#: so the swing it hands over is stamped with this ref.
RAMPAGE = "cf:barbarian-f3"


@power("f2707", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2707(c: Cast) -> None:
    """A damage bonus on the free basic attack the class feature grants,
    at exactly 2 squares.

    The grip and the reach are asked inside the gate rather than when
    the trait arms: a barbarian can change hands, and the gate is read
    at the moment the damage is rolled. "2 squares away" is exactly 2 --
    the printed line is about a reach weapon's outer square, not about
    anything at 2 or more.
    """
    def far_enough(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return (
            ctx.get("granted_via") == RAMPAGE
            and ctx.get("granted_by") == c.me
            and c.wielding("two-handed")
            and c.wielding("reach")
            and foe is not None
            and distance_between(c.world, c.me, foe) == 2
        )

    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=far_enough)


@power("f2884", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("Defences.immune_keywords",))
def f2884(c: Cast) -> None:
    """An attack penalty on whoever the class feature's free swing hits.

    Read off `PowerResolved` rather than the `Hit`: the use is what
    carries where the swing came from.

    Dropped: "a creature immune to fear is not subject to this penalty".
    `Defences` holds immunity per damage type and nothing records
    immunity to a *keyword*, so the narrowing has nothing to ask. Gating
    on it anyway would be silently false one way or the other.
    """
    def punished(ev: Any) -> None:
        if ev.actor != c.me or ev.granted_via != RAMPAGE or ev.granted_by != c.me:
            return
        for roll in ev.rolls:
            if roll.hit:
                c.penalty("attack", 2, on=roll.target, until=When.EONT)

    c.watch(PowerResolved, punished, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} rampage rider")


# -- weapons treated as something they are not -----------------------------


@power("f1841", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Gear.ranged(thrown=)",))
def f1841(c: Cast) -> None:
    """Throw an off-hand blade like a handaxe, at 5/10.

    **Re-pointed, and the gate is no longer the story.** The old note said
    the blocker was `dsl.can_branch` asking `gear.ranged is not None` for a
    ranged branch, and that `Gear.ranged` means "can be fired". That is
    accurate, and the compendium does say *"a creature can make a ranged
    basic attack as long as it has something to throw **or** shoot"* -- so
    the gate is wrong about the rule and `dsl._reach` has always agreed with
    the page, substituting a thrown weapon's range *"fired first, then
    thrown"*.

    **Opening it was built, measured, and taken back out.** With the gate
    admitting a thrown weapon, the printed rule holds and the AI gets
    measurably worse, because the engine gives a thrown weapon **no cost**:
    you throw the dagger and still have it. `scripts/winrate.py`, the smart
    policies against the chassis baseline:

        level  5 scored   +10% -> +3%
        level  5 rated    +13% -> +7%
        level 10 scored   +20% -> -10%     <- worse than the baseline
        level 10 rated    +27% -> +10%

    and the provocation lines say why: `rba is a ranged power x45` where it
    had barely appeared, so the policy throws the free infinite dagger and
    eats opportunity attacks for it. 6 of 7 replay fixtures diverged on the
    policy taking it over real powers.

    So this waits on **#520** -- "nothing runs out of a thrown weapon or a
    mundane shot: one net is infinite nets" -- and not on the gate. That
    issue's fix is counts on a weapon, with the ETL data already recorded
    (#516); once a throw costs something, the gate can open and this row is
    two lines. The order of work was the thing that needed finding. #838.

    **Half right, and the surviving half is the one that blocks.**
    `c.weapon_dice` proves a body *can* rewrite a `Weapon` -- `Gear.weapons`
    holds per-character copies -- so `thrown=(5, 10)` is writable here and
    was the easy half. It buys nothing: the only reader of `Gear.thrown` is
    `dsl._reach`, and a ranged weapon branch never gets that far, because
    `Power.can_branch` asks `gear.ranged is not None` and a blade cannot be
    *fired*. Setting `ranged` instead is worse -- `Gear.melee` is "held and
    not ranged", so it takes the weapon out of the melee hand entirely.

    A standing `c.bonus("reach", 4)` is the other near miss. It is what
    `c.as_ranged` lays, but that one is `once=True` on the creature's *next*
    melee attack; standing, it would reach five squares with the greataxe in
    the main hand, which is not this card.
    **Re-pointed: a range *write* landed and is not what this card needs.**
    `c.weapon_range` sets `Weapon.thrown` on this character's own copy, and
    `f1841`'s note was substantially right that it buys nothing here: the
    clause these three print is "you may make a **ranged attack** with this
    melee weapon", and what decides that is not the weapon's field.

    Read down, since the old note had one detail wrong. `dsl.can_branch`
    *does* open a ranged branch off a melee weapon -- `return bool(gear.melee)
    if self.thrown_by_hand else gear.ranged is not None` -- so the gate is
    not unconditionally `gear.ranged`. But `thrown_by_hand` is a **header
    field on the power**, true for everybody holding that card, set by five
    declared rows. These feats change the *weapon*, not the card, so no row
    the character holds becomes throwable by writing the field.

    So the gap is the ranged basic attack accepting a thrown melee weapon --
    `Gear.ranged` is "can be fired", and its own comment is the argument
    against widening it: *"a dagger cannot be -- letting it answer that
    question hands a rogue a ranged basic attack it does not have."* That is
    the site, and it is a `Gear`/basic-attack change rather than a weapon
    field. #643.
    """


@power("f1843", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.IMPROVISED",))
def f1843(c: Cast) -> None:
    """"Use improvised melee weapons as heavy thrown weapons", plus a +2
    feat bonus to attack and damage when you do.

    **Re-pointed: this one never waited on the gate.** An improvised melee
    weapon is not a thing `Gear` holds, and this card says "not including
    unarmed attacks", so `chargen.UNARMED` is explicitly not it -- the
    compendium's Improvised Weapons entry gives a separate line (Prof. --,
    1d4, group "None or unarmed"). Both halves wait on the same thing: with
    no improvised weapon in hand there is nothing to give a range to and
    nothing for the bonus to narrow on. One weapon declared the way
    `chargen.STAFF` and `chargen.TOME` are, plus a way to pick one up.

    Kept separate from `f1841` deliberately: that row waits on #520, this
    one does not, and the shared marker hid the difference.
    **Re-pointed: a range *write* landed and is not what this card needs.**
    `c.weapon_range` sets `Weapon.thrown` on this character's own copy, and
    `f1841`'s note was substantially right that it buys nothing here: the
    clause these three print is "you may make a **ranged attack** with this
    melee weapon", and what decides that is not the weapon's field.

    Read down, since the old note had one detail wrong. `dsl.can_branch`
    *does* open a ranged branch off a melee weapon -- `return bool(gear.melee)
    if self.thrown_by_hand else gear.ranged is not None` -- so the gate is
    not unconditionally `gear.ranged`. But `thrown_by_hand` is a **header
    field on the power**, true for everybody holding that card, set by five
    declared rows. These feats change the *weapon*, not the card, so no row
    the character holds becomes throwable by writing the field.

    So the gap is the ranged basic attack accepting a thrown melee weapon --
    `Gear.ranged` is "can be fired", and its own comment is the argument
    against widening it: *"a dagger cannot be -- letting it answer that
    question hands a rogue a ranged basic attack it does not have."* That is
    the site, and it is a `Gear`/basic-attack change rather than a weapon
    field. #643.
    """


# -- the event the bus now carries -----------------------------------------


@power("f1992", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1992(c: Cast) -> None:
    """A damage bonus against an adjacent enemy that recharges a power.

    **The premise was true when this was written and is not now.** The
    note said `actions.recharge` puts the row back silently; `#605` minted
    `PowerRecharged` and emits it on *both* recharge paths, and the event
    carries `actor`, `ref` and `rolled`, which is everything this needs.
    `m6180a3` watches it the same way.

    `ev.rolled` is the printed "at the start of its turn". The die is
    rolled by `actions.recharge`, which `policy.take_turn` calls before
    the creature acts, and it is reported as the number that brought the
    row back; `triggers.Triggers` restores a row whose printed *condition*
    fired at any other moment and reports 0. Without that gate the feat
    would pay on a mid-round condition recharge, which the card does not
    print.
    """
    step = 2 + (c.level >= 11) + (c.level >= 21)

    def boost(ev: PowerRecharged) -> None:
        foe = ev.actor
        if not ev.rolled or foe not in c.enemies() or not c.adjacent(foe):
            return
        c.bonus(
            "damage", step, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("target") == foe,
        )

    c.watch(PowerRecharged, boost, until=When.ENCOUNTER, on=c.me, label=c.ref)
