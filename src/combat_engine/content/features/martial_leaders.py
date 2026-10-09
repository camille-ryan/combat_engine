"""Class-page features and their printed sub-options: warlord, artificer,
bard, swordmage.

Everything here whose ref ends in `-fNsM` is a **sub-option**: a build
choice printed under the feature. They were only extractable today.

**Thirteen of the refs dealt with this file are not declared here, on
purpose.** The extraction over-reached: a `-fNcM` ref is the feature
section's reprint of a card the compendium also gives a `p` ref, and four
`-fNsM` refs restate a branch their parent feature already implements.
Declaring either would put the same card in the menu twice -- two separate
uses of an encounter power -- or, for a modifier, silently double an
untyped number. They are listed in this batch's report so the extraction
can be fixed at the source, and there is no placeholder for them here
because a do-nothing row would hide the fault rather than record it.

What that leaves is the features themselves, the sub-options with no
sibling already in the tree, and one recurring gap: four artificer rows and
the bard's rest song happen *during* a rest.

**The rest itself is not the gap.** `turns.short_rest` and
`turns.extended_rest` both exist and both have callers now, so a marker
saying "there is no rest" would be a row refused in play for nothing.
What is missing is narrower and is what these rows name: nothing
**announces** a rest, so no row can run inside one -- `events.ShortRested` -- and
`turns.short_rest` does not spend healing surges, which is the only moment
the bard's song has to pay out at.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    WILL,
    ActionPointSpent,
    ActionType,
    Cast,
    CloseBurst,
    Keyword,
    Trigger,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import Hit, ItemPowerUsed, Miss, PowerResolved
from combat_engine.engine.query import distance_between, team

from .builds import on_leg

ARCANE = [Keyword.ARCANE]
ARCANE_HEAL = [Keyword.ARCANE, Keyword.HEALING]
MARTIAL = [Keyword.MARTIAL]

#: The four defences, for the one option that lays a modifier on all of them.
_DEFENCES = (AC, FORT, REF, WILL)

#: The event that would give a row a moment inside a rest. `turns.short_rest`
#: exists and restores what it should; nothing announces it, so a row whose
#: printed effect happens *during* a rest has nowhere to hang.
_REST = "events.ShortRested"


# -- artificer --------------------------------------------------------------


@power(
    "cf:artificer-f0",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=(_REST,),
)
def artificer_empower(c: Cast) -> None:
    """The per-day allowance the two `-f0s*` options spend.

    Not narrative -- both options it pays for have a reading in a fight --
    but the allowance is granted and spent only inside a rest, and nothing
    announces one. `turns.short_rest` runs and restores encounter powers;
    it emits nothing, so a row that is supposed to *do* something while it
    runs has no moment to be called at.

    `docs/blocked.json`'s `cf:artificer-items` named the item half of this
    before `Gear.worn` and `ItemPowerUsed` existed; those two have landed
    since, which is why that entry is out of date and this is not.
    """


@power(
    "cf:artificer-f0s0",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=(_REST, "c.boost_roll()"),
)
def artificer_empower_reservoir(c: Cast) -> None:
    """Both halves are missing, which is why this is `todo` and not
    `dropped`.

    The reservoir is laid during a rest, and it is spent as a free action
    *after* an attack roll has already been made -- `c.bonus` applies to
    the next roll, not to one that has landed, so a +2 written with it
    would be a different, later number.
    """


@power(
    "cf:artificer-f0s1",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=(_REST, "c.restore_use(item=)"),
)
def artificer_empower_recharge(c: Cast) -> None:
    """`Gear.worn` records magic items and `Magic.powers` lists their rows,
    so *which* row to recharge is answerable now -- but `c.restore_use`
    takes a ref and nothing picks an item's daily out of the slots, and the
    recharge happens over a rest either way.
    """


@power(
    "cf:artificer-f1",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE_HEAL,
)
def artificer_transfer(c: Cast) -> None:
    """`ItemPowerUsed` is what makes this writable, and it is new.

    `docs/blocked.json` records this feature as having no subject at all;
    the event exists now, `Cast.used` emits it beside every `PowerUsed` off
    a worn item, and "a magic item's **daily** power" is the declared row's
    own usage read back off the ref. Nothing in the tree fires it yet -- no
    chassis wears an item with a power -- but the hook is the printed one
    rather than an approximation of it.

    The artificer's own item powers are left out: the card says "one of the
    artificer's allies".
    """
    me = c.me
    amount = c.level // 2 + c.int_mod

    def used(ev: ItemPowerUsed) -> None:
        if ev.actor == me or team(c.world, ev.actor) is not team(c.world, me):
            return
        declared = get(ev.power)
        if declared is None or declared.usage is not DAILY:
            return
        c.temp_hp(amount, on=ev.actor)

    c.watch(ItemPowerUsed, used, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:artificer-f2",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE_HEAL,
    todo=(_REST, "chargen.power_choice()"),
)
def artificer_infusions(c: Cast) -> None:
    """The budget the class's three infusion cards draw on, and the swap
    offered when the character is made.

    Two infusions are crafted at an extended rest, one is spent per card
    used, and a spent one is replenished by a healing surge during a short
    rest. `group=` is a one-per-encounter allowance and would be a third of
    the printed one, so `p4128`, `p7635` and `p10187` each carry their own
    `once_per_round` instead -- which is three separate allowances rather
    than one shared one, and this row is the thing that is missing.
    The other half is the swap the page offers when the character is made
    -- one card taken in place of another. That is not an ability leg and
    `chargen.BUILDS` was the wrong symbol for it: a `Build` records which
    secondary a fork leans on and carries no card list.
    `chargen.power_choice()` is what the sorcerer's own swap already names.
    """


# -- bard -------------------------------------------------------------------


def _enemy_hits_nearby_ally(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits one ally within 5 squares of you" -- and not you."""
    victim, attacker = ev.target, ev.attacker
    if victim == me or attacker == me:
        return False
    if team(world, victim) is not team(world, me):
        return False
    if team(world, attacker) is team(world, me):
        return False
    return distance_between(world, me, victim) <= 5


@power(
    "cf:bard-f1s1",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    trigger="an enemy hits one ally within 5 squares of you",
    on=Trigger(Hit, _enemy_hits_nearby_ally, "an enemy hits a nearby ally"),
)
def bard_virtue_valour(c: Cast) -> None:
    """The third of the three printed virtues, and the only one `cf:bard-f1`
    does not already write -- that row takes the other two.

    It is also the only one of the three that is a card rather than a
    standing trait: an immediate action with a printed once-per-encounter
    limit, which is what `usage=ENCOUNTER` says here honestly rather than
    by the accident issue #210 is about.

    **A reaction, not an interrupt.** The bonus runs to the end of the
    triggering enemy's turn, so it is for that creature's *remaining*
    attacks; cancelling the blow that caused it is not what the card says.

    "The defence targeted by the triggering enemy" is read off the declared
    row -- `Hit` carries `power` but no `vs`, while the header does. The
    triggering ally is read off the event rather than chosen, because the
    card names it; `c.target` is the fallback when there is no trigger.

    `chargen.BUILDS["bard"]` carries a leg per virtue now, named for the
    option's own ref, so the choose-one is enforced: a bard on either of
    the other two legs never holds this card. It is asked in the body
    rather than as `requires=`, because a trigger's predicate runs before
    `requires` is consulted and a row that can never fire should say so in
    the one place the audit reads.
    """
    if not c.build("f1s1"):
        return
    ev = c.trigger
    who = getattr(ev, "target", None) or c.target
    if who is None:
        return
    declared = get(getattr(ev, "power", "") or "")
    defence = declared.attack.vs if declared is not None and declared.attack else AC
    c.bonus(defence, max(c.wis_mod, 1), kind="power", until=When.EOT, on=who)


#: The bard's class heal, already a level 0 bard row of its own.
_BARD_HEAL = "p2339"

#: The bard's class-feature minor action, already a level 0 bard row.
_BARD_WORD = "p2887"


@power(
    "cf:bard-f2",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE_HEAL,
)
def bard_heal_feature(c: Cast) -> None:
    """Whose entire printed benefit is the row it names.

    `chargen.loadout` deals a class every level 0 row it has, so the grant
    is already true and this re-states it rather than inventing anything --
    the same shape, and the same reasoning, as `cf:warlord-marshal-f1`.
    """
    c.grant_row(_BARD_HEAL)


@power(
    "cf:bard-f5",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE_HEAL,
    todo=(_REST, "turns.short_rest(surges=)"),
)
def bard_song_of_rest(c: Cast) -> None:
    """Every word of this is about a short rest: it is set up during one and
    it pays out on the surges spent at the end of one.

    Two separate things are missing and both are named. Nothing announces
    a rest, so the song cannot be started; and `turns.short_rest` does not
    spend healing surges at all -- it restores encounter powers and says so
    -- so even a song that was running would have nothing to add its hit
    points to. The one-at-a-time rule it ends with has nothing to arbitrate
    until both land.

    `docs/blocked.json` records this ref as wanting "a short rest in the
    engine", which has since arrived; the two clauses above are what is
    actually left.
    """


@power(
    "cf:bard-f6",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def bard_word_feature(c: Cast) -> None:
    """A grant and nothing else, like `cf:bard-f2`. The row it hands over is
    itself deliberately inert -- its whole Effect is a social check -- but
    that is that row's call to have made, not this one's."""
    c.grant_row(_BARD_WORD)


# -- swordmage --------------------------------------------------------------


@power(
    "cf:swordmage-f0",
    level=0,
    cls="swordmage",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=("c.pick_up()", "Gear.owned"),
)
def swordmage_bond(c: Cast) -> None:
    """Only one clause of this has a reading inside a fight -- calling the
    bonded blade back to hand as a standard action from ten squares away --
    and it has nothing to change.

    `c.disarm` drops a weapon into the disarmed creature's square and
    nothing anywhere picks one back up, and `Gear` records what is held,
    stowed and worn but not what is *owned and elsewhere*. So the recall
    would be a standard action that moves nothing. The rest of the card is
    an hour of meditation between fights. `docs/blocked.json` has the same
    two wants under this ref.
    """


#: The three aegis rows, by the leg that takes each.
_AEGIS_ASSAULT = "p3322"
_AEGIS_ENSNARE = "p5736"
_AEGIS_SHIELD = "p3323"
_AEGIS_BY_LEG = {
    "assault": _AEGIS_ASSAULT,
    "ensnarement": _AEGIS_ENSNARE,
    "shielding": _AEGIS_SHIELD,
}


@power(
    "cf:swordmage-f1",
    level=0,
    cls="swordmage",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def swordmage_aegis(c: Cast) -> None:
    """The parent of the fork, and what it carries is the half that is true
    whichever branch was taken: **choose one**.

    The grant is the children's -- `cf:swordmage-f1s0` and its two siblings
    each hand over the row their own leg names -- so this does the other
    side of the exclusivity and takes away the two that were not chosen.
    `chargen.loadout` deals a swordmage all three, and `requires=` on each
    only refuses the *use*; `c.forbid` is the removal, and it is what the
    printed "choose one" actually says. Splitting it this way is why parent
    and children do not restate each other.

    `c.forbid` follows `c.target` and a trait has none, so `on=c.me` is not
    optional here -- without it this takes the rows away from nobody, which
    is the bug `cf:warlord-marshal-f1` was fixed for.
    """
    taken = next((leg for leg in _AEGIS_BY_LEG if c.build(leg)), "")
    mine = _AEGIS_BY_LEG.get(taken, "")
    for ref in _AEGIS_BY_LEG.values():
        if ref != mine:
            c.forbid(ref, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:swordmage-f1s0",
    level=0,
    cls="swordmage",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("assault"),
    requires_text="needs the aegis that answers with an attack",
)
def swordmage_aegis_assault_choice(c: Cast) -> None:
    """One of the three build choices under `cf:swordmage-f1`. What the
    choice adds is the row; the exclusivity is the parent's."""
    c.grant_row(_AEGIS_ASSAULT)


@power(
    "cf:swordmage-f1s1",
    level=0,
    cls="swordmage",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("ensnarement"),
    requires_text="needs the aegis that hauls the foe back",
)
def swordmage_aegis_ensnare_choice(c: Cast) -> None:
    """The second of the three; see `cf:swordmage-f1s0`."""
    c.grant_row(_AEGIS_ENSNARE)


@power(
    "cf:swordmage-f1s2",
    level=0,
    cls="swordmage",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("shielding"),
    requires_text="needs the aegis that blunts the blow",
)
def swordmage_aegis_shield_choice(c: Cast) -> None:
    """The third of the three; see `cf:swordmage-f1s0`."""
    c.grant_row(_AEGIS_SHIELD)


# -- warlord ----------------------------------------------------------------


@power(
    "cf:warlord-marshal-f0",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    todo=("c.attacks_with(ability=)", "chargen.armor_proficiency()",
          "chargen.second_fork()"),
)
def warlord_archer(c: Cast) -> None:
    """Three clauses and none of them has a subject.

    **`chargen.BUILDS` re-aimed to `chargen.second_fork()`, and the paragraph
    below is why.** It already states that "adding legs does not supply it" --
    so naming the thing that exists made this row red the moment legs were dealt,
    against a symbol that was never the hold. What is wanted is a *second fork
    per class*, which is a different shape from a longer list of legs.

    Two are proficiency, which nothing models in either direction -- the
    row drops two and adds one. The third rewrites which ability a ranged
    basic attack rolls, and `basic.RANGED` fixes that in its own header
    where no modifier can reach it. `chargen.BUILDS` is wanted as well and
    **adding legs does not supply it**: the class's six legs are already
    spent on the six options of a different printed fork, and a character
    takes one leg and stays on it, so an archer leg would make this choice
    exclusive with a commanding presence, which the page does not. What is
    wanted is a second fork per class. `docs/blocked.json` records the
    same under `cf:warlord-archer`.
    """


def _paying_ally(c: Cast, ev: ActionPointSpent) -> int | None:
    """The ally this feature answers for, or None.

    All six printed options share a first half -- "an ally who can see you
    spends an action point" -- so it is asked once. The warlord is never
    the ally; every one of the six says so.
    """
    who = ev.actor
    if who == c.me or who not in c.allies() or not c.can_see(who):
        return None
    return who


def _bought_with_a_point(ev: Any) -> bool:
    """"Uses the action to make an attack", read off the attack itself.

    `resolve.attack` rides this flag on all four attack events and puts it
    in the attack context, the way it does `charge`, so the narrower half
    of the printed trigger is answerable -- `ActionPointSpent` alone cannot
    say what the extra action was spent on.
    """
    return bool(getattr(ev, "action_point", False))


@power(
    "cf:warlord-marshal-f4s0",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=on_leg("bravura"),
    requires_text="needs the leg whose presence is a gamble",
)
def warlord_presence_gamble(c: Cast) -> None:
    """The one option of the six that can go wrong, so the opt-in is real
    and is asked of the **ally**, before the roll -- "the ally can choose to
    take advantage of this feature before the attack roll".

    The latch is per action point rather than per round: a second point in
    the same turn is a second offer, which is what the card says.

    "Grants combat advantage to all enemies" is one relation per enemy --
    `c.grants_advantage(to=)` names a single beneficiary, and `"team"`
    would be the warlord's own side, which is the wrong one.

    The free basic attack needs somebody to swing at and the card does not
    name one, so it goes to an enemy already next to the ally; with none
    adjacent, the move action is what is left and is taken instead.
    """
    me = c.me

    def spent(ev: ActionPointSpent) -> None:
        ally = _paying_ally(c, ev)
        if ally is None or not c.may("gamble on the presence", who=ally):
            return
        done = {"yet": False}

        def landed(hit: Hit) -> None:
            if done["yet"] or hit.attacker != ally or not _bought_with_a_point(hit):
                return
            done["yet"] = True
            if c.may("make a basic attack", who=ally):
                victim = next(iter(c.within(1, of=ally, side="enemy")), None)
                if victim is not None:
                    c.grant_attack(ally, on=victim)
                    return
            c.extra_action(ActionType.MOVE, on=ally)

        def whiffed(miss: Miss) -> None:
            if done["yet"] or miss.attacker != ally or not _bought_with_a_point(miss):
                return
            done["yet"] = True
            for foe in c.enemies():
                c.grants_advantage(on=ally, to=foe, until=When.EOTNT)

        c.watch(Hit, landed, until=When.EOT, on=me, label=c.ref)
        c.watch(Miss, whiffed, until=When.EOT, on=me, label=c.ref)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warlord-marshal-f4s1",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=on_leg("shielding"),
    requires_text="needs the leg whose presence is a guard",
)
def warlord_presence_guard(c: Cast) -> None:
    """The only one of the six that does not care what the extra action is
    spent on -- "spends an action point to take an extra action" and
    nothing further -- so the bare `ActionPointSpent` is the whole trigger.

    "Half your Wisdom modifier **or** half your Charisma modifier" is a
    choice between two numbers, and the better of the two is what anybody
    would take. Untyped: the card prints no word before "bonus".
    """
    me = c.me
    amount = max(c.wis_mod, c.cha_mod) // 2

    def spent(ev: ActionPointSpent) -> None:
        ally = _paying_ally(c, ev)
        if ally is None or amount <= 0:
            return
        def all_defences() -> None:
            for defence in _DEFENCES:
                c.bonus(defence, amount, until=When.SOTNT, on=ally)

        # "That ally can forgo the normal bonus to all defences to instead
        # gain a bonus to a single defence" -- the ally's choice and not the
        # marshal's. Read at the clause because this fires inside a watcher
        # on `ActionPointSpent`, which no menu entry reached.
        c.instead_of_now("all_defences", all_defences, on=ally)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warlord-marshal-f4s3",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=on_leg("resourceful"),
    requires_text="needs the leg whose presence pays either way",
)
def warlord_presence_resource(c: Cast) -> None:
    """Two payouts, and the second is the interesting one: "if the attack
    hits no target".

    `PowerResolved` is what can answer that and `Hit`/`Miss` cannot -- a
    burst that missed two and hit one is three events, and only the
    finished use knows the whole set. `rolls` is every `AttackResult` it
    produced, so "hit nothing" is no roll that landed; a use that rolled
    nothing at all is not an attack and is skipped.

    The damage bonus is laid for the turn with `once=True` rather than
    gated on the attack: the damage context carries `charge` and
    `opportunity` and **no** `action_point`, so a gate there would read a
    key it does not have, which is silently false.
    """
    me = c.me
    hurt = c.level // 2 + c.int_mod
    cushion = c.level // 2 + c.cha_mod

    def spent(ev: ActionPointSpent) -> None:
        ally = _paying_ally(c, ev)
        if ally is None:
            return
        c.bonus("damage", hurt, until=When.EOT, on=ally, once=True)
        done = {"yet": False}

        def finished(resolved: PowerResolved) -> None:
            if done["yet"] or resolved.actor != ally or not resolved.rolls:
                return
            done["yet"] = True
            if not any(getattr(roll, "hit", False) for roll in resolved.rolls):
                c.temp_hp(cushion, on=ally)

        c.watch(PowerResolved, finished, until=When.EOT, on=me, label=c.ref)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warlord-marshal-f4s4",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=on_leg("insightful"),
    requires_text="needs the leg whose presence buys a step",
)
def warlord_presence_step(c: Cast) -> None:
    """"A free action to shift, before or after the attack" is a line in the
    action menu rather than a movement this row performs, which is what
    `c.grant_action("shift", ...)` is for -- and `shift` is one of the
    three words it actually reads rather than silently carries.

    "Your Intelligence **or** Wisdom modifier" is a choice, so the larger.
    Held to the end of the turn the point was spent on, which is the window
    "before or after the attack" lives in.
    """
    me = c.me
    squares = max(c.int_mod, c.wis_mod)

    def spent(ev: ActionPointSpent) -> None:
        ally = _paying_ally(c, ev)
        if ally is None or squares <= 0:
            return
        c.grant_action(
            "shift", ActionType.FREE, squares_=squares, on=ally, until=When.EOT
        )

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=me, label=c.ref)


#: The warlord's class heal, already a row of its own in `features/leaders.py`.
_WARLORD_WORD = "p1590"


@power(
    "cf:warlord-marshal-f5",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def warlord_word_feature(c: Cast) -> None:
    """A grant and nothing else, like `cf:warlord-marshal-f1`'s first half:
    `loadout` has already dealt the row, and this says so rather than
    inventing a second effect for it."""
    c.grant_row(_WARLORD_WORD)
