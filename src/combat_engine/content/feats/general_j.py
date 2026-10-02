"""General feats: the divine batch, and the r47 racial run after it.

Three shapes carry most of this file and all three already exist in the
tree, so none of them is invented here.

**The associated-power rider.** A skill bonus, then one clause per named
row. `exploits.py` wrote that machine once; `_assoc` below is the same
thing with the skill bonus laid beside it, because every one of these
cards prints both and a row may not hold a trigger *and* a standing
modifier. Every list in the batch has a ref under it now, so no row in
the family is short of something to point its clause at.

**Retyping one named row's damage.** Four of these cards read "the
power's damage changes to <type>, and it loses the keywords of its
former damage types". That is an override of the *blow*, not of this
creature's weapon, so it is not `c.deals` -- it is `DamageRolled`, which
is announced before the damage lands, carries the ref that dealt it in
`detail`, and has `dtype` read back afterwards. `_retype` below is the
whole of it.

**The granted pair.** "You gain the `fNNNb` power" is a trait that hands
over the card; the card is the row. Every card in this batch prints the
shared once-per-encounter limit, so every one carries
`group=CHANNEL_DIVINITY` rather than `uses=1` -- the budget is shared
across every such row a character holds, from any source.

**"When you use a channel divinity power".** That is not prose here: the
class feature is a ref and the cards that belong to it are exactly the
rows whose `group` is `CHANNEL_DIVINITY`, so `PowerUsed` plus a group
check says it exactly.

The r47 run at the end rides on `p8278`, which is a **ref** -- but the
row it names rolls no damage and makes no attack. Its whole payload is
`c.bonus("damage", ..., dtype=NECROTIC)`, a typed *rider* on somebody
else's blow. So "the extra necrotic damage from that power" has no
number to read, and "that power deals cold as well" has no roll to
retype: `resolve.deal_damage` splits a blow into typed parts and only
`parts[0]`, the power's own, is reachable from `DamageRolled`. That is
what `RIDER_RETYPE` names, and it is a different gap from the one
`_retype` closes above.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    AreaBurst,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Dropped,
    ForcedMove,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    Target,
    Trigger,
    TurnStart,
    UpTo,
    When,
    Window,
    about_me,
    ally_within,
    either,
    get,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.grid import burst
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    squares,
    team,
)

from .styles import among

DIVINE = [Keyword.DIVINE]
DIVINE_HEAL = [Keyword.DIVINE, Keyword.HEALING]
DEFENCES = (AC, FORT, REF, WILL)

#: "You or one ally", which the ally pool already includes the caster in.
ONE_OTHER_ALLY = Target("other_ally", 1)
EACH_OTHER_ALLY = Target("other_ally", 99, everyone=True)

#: A racial power the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one of them.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
#: `p8278`'s whole payload is a typed damage **rider** --
#: `c.bonus("damage", ..., dtype=NECROTIC)` on somebody else's blow --
#: rather than a roll of its own. `DamageRolled` retypes `parts[0]`, the
#: power's own part, and nothing reaches the part a modifier contributed,
#: so the two feats that recolour that rider have nowhere to write.
RIDER_RETYPE = ("c.bonus(retype=)",)
#: The other side of the same coin: the *size* of that rider, and the
#: moment it is paid. Four rows in the r47 run read "the additional
#: necrotic damage from `p8278`" and the blow's parts are not on the
#: event either.
EXTRA = ("c.on_extra_damage()",)
#: Which implements or weapons a character may pick up is settled when it
#: is built, not on a board with the gear already in hand.
PROFICIENCY = ("chargen.proficiency()",)


# -- shared machinery -------------------------------------------------------


def _granted(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is one card."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _assoc(ref: str, skill: str, amount: int, clauses: dict, **header: Any) -> None:
    """A feat bonus to one skill, plus a clause on each named row.

    One watcher rather than one per power: the list is four long and the
    clause is picked by which row hit. The skill half is a standing
    modifier and the rider is a trigger, so the row has to be a trait
    with `c.watch` inside it -- declared `on=Trigger(...)` the bonus
    would never be laid at all.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, **header)
    def feat(c: Cast) -> None:
        me = c.me
        c.bonus(f"skill:{skill}", amount, on=me, until=When.ENCOUNTER, kind="feat")
        if not clauses:
            return

        def on_hit(ev: Any) -> None:
            if ev.attacker != me:
                return
            clause = clauses.get(ev.power)
            if clause is not None:
                clause(c, ev)

        c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{ref} riders")

    feat.__name__ = ref
    feat.__doc__ = (
        f"+{amount} feat bonus to {skill}"
        + (
            ", and riders on " + ", ".join(sorted(clauses))
            if clauses
            else ", and nothing else the card can point at"
        )
        + "."
    )


def _cd_used(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """"When you use a channel divinity power" -- the group is the budget
    those cards share, so it is also what identifies one."""
    p = get(ev.power)
    return ev.actor == me and p is not None and p.group == CHANNEL_DIVINITY


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _used_any(*refs: str):  # noqa: ANN202
    """"A <race> racial power", where the race prints more than one."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return when


def _hit_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _bloodied_by_enemy_near(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """"You are bloodied by an enemy within 10 squares of you."

    The crossing, not the state, and `Bloodied` is emitted only on the blow
    that makes it and only while `hp > 0`, so neither has to be
    reconstructed from `DamageApplied`."""
    who = getattr(ev, "source", None)
    return (
        ev.actor == me
        and who is not None
        and team(world, who) != team(world, me)
        and distance_between(world, me, who) <= 10
    )


def _ours(world, me: int, who: int, reach: int) -> bool:  # noqa: ANN001
    return who == me or (
        team(world, who) == team(world, me)
        and distance_between(world, me, who) <= reach
    )


def _retype(c: Cast, dtype: DamageType, refs: tuple[str, ...]) -> None:
    """"The power's damage changes to X, and it loses the keywords of its
    former damage types."

    Not `c.deals`, which overrides what this creature's *weapon* rolls
    and would catch every other card in the character's hand.
    `DamageRolled` is announced before the blow lands, carries in
    `detail` the ref that dealt it, and its `dtype` is read back --
    setting `dtype` alone is the override, keywords and all, which
    `resolve.deal_damage` says out loud. A rider some other row hung on
    the same hit keeps its own type, which is also what the card means.
    """
    me = c.me
    wanted = frozenset(refs)

    def recolour(ev: Any) -> None:
        if ev.source == me and ev.detail in wanted:
            ev.dtype = dtype

    c.watch(DamageRolled, recolour, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


def _divine_radiant(p) -> bool:  # noqa: ANN001
    return (
        p is not None
        and Keyword.DIVINE in p.keywords
        and Keyword.RADIANT in p.keywords
        and p.usage in (ENCOUNTER, DAILY)
    )


# -- the associated-power riders --------------------------------------------


def _defence_penalty(c: Cast, ev: Any) -> None:
    """"The defence targeted by the power" is header data: `Hit` does not
    carry it, but the row that fired declares it."""
    p = get(ev.power)
    vs = p.attack.vs if p is not None and p.attack is not None else None
    if vs is not None:
        c.penalty(vs, 2, on=ev.target, until=When.EONT)


def _ally_defences(c: Cast, ev: Any) -> None:
    for friend in allies(c.world, c.me):
        if distance_between(c.world, c.me, friend) <= 5:
            for defence in DEFENCES:
                c.bonus(defence, 1, on=friend, kind="power", until=When.SONT)
            return


def _save_or_hinder(c: Cast, ev: Any) -> None:
    """A printed choice between shaking something off and making the
    target's next save worse. Read as: take the save when there is one to
    take, and hinder the enemy when there is not."""
    if not c.save(on=c.me):
        c.penalty("save", 2, on=ev.target, until=When.SONT, once=True)


def _vulnerable_radiant(c: Cast, ev: Any) -> None:
    c.vulnerable(3, DamageType.RADIANT, on=ev.target, until=When.EONT)


def _grants_to_ally(c: Cast, ev: Any) -> None:
    """"Your next ally who attacks it" -- one grant, spent on the first
    one to take it, which is what `once` is."""
    c.grants_advantage(on=ev.target, to="team", until=When.SONT, once=True)


def _shift_near(c: Cast, ev: Any) -> None:
    if c.adjacent(to=ev.target):
        c.shift(1)
        return
    for friend in allies(c.world, c.me):
        if c.adjacent_to(ev.target, friend):
            c.shift(1, who=friend)
            return


def _retaliate(c: Cast, ev: Any) -> None:
    foe = ev.target

    def bite(_ev: Any) -> None:
        c.flat(2, on=foe)

    c.on_attack(bite, by=foe, until=When.SONT, once=True, label="retaliation")


def _ignore_rough(c: Cast, ev: Any) -> None:
    c.ignores_difficult(on=c.me, until=When.EONT)
    for friend in allies(c.world, c.me):
        if c.adjacent(to=friend):
            c.ignores_difficult(on=friend, until=When.EONT)


_assoc("f1453", "perception", 1, {
    "p6980": _defence_penalty, "p836": _defence_penalty,
    "p7151": _defence_penalty, "p839": _defence_penalty,
})

_assoc("f1457", "heal", 2, {
    "p569": _ally_defences, "p1580": _ally_defences,
    "p835": _ally_defences, "p2849": _ally_defences,
})

_assoc("f1459", "athletics", 2, {
    "p6980": _save_or_hinder, "p2848": _save_or_hinder,
    "p7072": _save_or_hinder, "p3687": _save_or_hinder,
})

_assoc("f1469", "insight", 2, {
    "p841": _vulnerable_radiant, "p2894": _vulnerable_radiant,
    "p5137": _vulnerable_radiant, "p3687": _vulnerable_radiant,
})

_assoc("f1471", "intimidate", 2, {
    "p7241": _grants_to_ally, "p8286": _grants_to_ally,
    "p7152": _grants_to_ally, "p3423": _grants_to_ally,
})

_assoc("f1473", "thievery", 2, {
    "p2847": _shift_near, "p836": _shift_near,
    "p3423": _shift_near, "p7072": _shift_near,
})

_assoc("f1480", "intimidate", 2, {
    "p8286": _retaliate, "p2847": _retaliate,
    "p1567": _retaliate, "p2894": _retaliate,
})

_assoc("f1484", "nature", 2, {
    "p3423": _ignore_rough, "p7072": _ignore_rough,
    "p5137": _ignore_rough, "p835": _ignore_rough,
})

# -- the trio that changes a named row's damage type ------------------------
#
# The two lists that used to be missing are printed now -- an errata block
# sat between the benefit and the list and `etl/feat._benefit` took the
# rest of the paragraph with it -- so all three of these carry the same
# two halves and nothing in the family is dropped any more.


@power("f1455", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1455(c: Cast) -> None:
    """"You **can** choose to change its damage type, and if you do so
    you deal 2 extra damage": one choice, taken, because a standing
    modifier is laid once at the start of the fight and there is nothing
    to ask at that point. Both halves therefore hang on the same set.

    A standing modifier rather than a rider, because the card says "when
    you **use**" and both halves are read while the blow is resolved --
    which is why the row may not carry a trigger."""
    me = c.me
    refs = ("p836", "p2850", "p3423", "p839")
    c.bonus("skill:bluff", 2, on=me, until=When.ENCOUNTER, kind="feat")
    _retype(c, DamageType.POISON, refs)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=among(*refs))


@power("f1478", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1478(c: Cast) -> None:
    """The same two halves as f1455 and neither is optional here: the
    card states the change rather than offering it."""
    me = c.me
    refs = ("p6980", "p836", "p2850", "p841")
    c.bonus("skill:religion", 2, on=me, until=When.ENCOUNTER, kind="feat")
    _retype(c, DamageType.NECROTIC, refs)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=among(*refs))


@power("f1486", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1486(c: Cast) -> None:
    """The third of the trio. `+2 bonus to the damage roll` is a plain
    bonus, so untyped; the type change is the blow's own, not this
    creature's weapon's."""
    me = c.me
    refs = ("p6980", "p836", "p7151", "p841")
    c.bonus("skill:endurance", 2, on=me, until=When.ENCOUNTER, kind="feat")
    _retype(c, DamageType.COLD, refs)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=among(*refs))


# -- associated-power feats that are standing modifiers, not riders ---------


def _one_of(refs: frozenset[str]):  # noqa: ANN202
    return lambda ctx: ctx.get("power", "") in refs


@power("f1461", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("chargen.skill_training()",))
def f1461(c: Cast) -> None:
    """The substitution plays and names no window, so it answers the
    charge, the opportunity attack and a defender's swing alike.

    **Re-aimed.** The marker named `c.bonus('skill:any')` and that verb
    is not what is missing: `skills.modifier` totals a blanket `skill`
    key beside `skill:<name>` for every check, so "a bonus to all of
    them" is already sayable. What is missing is *which* skills this
    character is trained in -- `skills.py` says outright there is no
    training model and `game.db` carries no skill list per class -- so
    the blanket key would pay on every untrained check as well."""
    c.as_basic("p2848", "p3423", "p839", "p835")


@power("f1463", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1463(c: Cast) -> None:
    """The fourth of the retyping family, and the one whose list never
    went missing. Same shape as f1455: the choice is taken, so the type
    change and the bonus hang on one set."""
    me = c.me
    refs = ("p3423", "p839", "p835", "p2849")
    c.bonus("skill:intimidate", 2, on=me, until=When.ENCOUNTER, kind="feat")
    _retype(c, DamageType.THUNDER, refs)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=_one_of(frozenset(refs)))


@power("f1465", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1465(c: Cast) -> None:
    """A plain "+2 bonus to the damage roll", so untyped. The damage
    context carries `power`, which is the whole of the gate."""
    me = c.me
    c.bonus("skill:athletics", 2, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=_one_of(frozenset({"p2847", "p1567", "p3423", "p1580"})),
    )


@power("f1467", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1467(c: Cast) -> None:
    """+1 to the damage roll *per enemy within 3 squares of the target*.
    A modifier's value is fixed when it is laid and nothing computes one
    at the moment it is read -- but nothing has to. `PowerUsed` fires
    before the body, targets are already chosen, and the damage has not
    been rolled, so the board is counted there and a bonus of that size
    is laid for that target alone.

    One bonus per target rather than one for the power: the count is "near
    **the target**" and a burst may hit two enemies with different
    neighbours. The target is not counted among its own neighbours -- the
    sentence names it apart from "each enemy".

    The gate names the power as well as the target. Gated on the target
    alone the bonus outlives its own use: it stands until the end of the
    turn, and the next card swung at the same enemy would collect it."""
    me = c.me
    wanted = frozenset({"p7241", "p5333", "p841", "p5137"})
    c.bonus("skill:bluff", 2, on=me, until=When.ENCOUNTER, kind="feat")

    def on_use(ev: Any) -> None:
        if ev.actor != me or ev.power not in wanted:
            return
        for who in ev.targets:
            near = sum(
                1
                for foe in enemies(c.world, me)
                if foe != who and distance_between(c.world, foe, who) <= 3
            )
            if near:
                c.bonus(
                    "damage", near, on=me, until=When.EOT, once=True,
                    when=lambda ctx, w=who, p=ev.power: (
                        ctx.get("target") == w and ctx.get("power") == p
                    ),
                )

    c.watch(PowerUsed, on_use, until=When.ENCOUNTER, on=me, label="f1467 riders")


@power("f1476", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1476(c: Cast) -> None:
    """"Whether or not you hit", so this is the one rider in the family
    that belongs on `PowerUsed` rather than on `Hit`. Targets are chosen
    before the body runs, so `ev.targets` is trustworthy there."""
    me = c.me
    wanted = frozenset({"p8286", "p6980", "p2848", "p836"})
    c.bonus("skill:intimidate", 2, on=me, until=When.ENCOUNTER, kind="feat")

    def on_use(ev: Any) -> None:
        if ev.actor != me or ev.power not in wanted:
            return
        for who in ev.targets:
            c.penalty("save", 2, on=who, until=When.SONT)

    c.watch(PowerUsed, on_use, until=When.ENCOUNTER, on=me, label="f1476 riders")


@power("f1482", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1482(c: Cast) -> None:
    """Gated on the target being unbloodied, which the *attack* context
    carries -- the damage context would not."""
    me = c.me
    wanted = frozenset({"p833", "p5333", "p1580", "p7153"})
    c.bonus("skill:history", 2, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power", "") in wanted
            and ctx.get("target") is not None
            and not c.bloodied(on=ctx["target"])
        ),
    )


# -- the granted cards ------------------------------------------------------


@power("f1452b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f1452b(c: Cast) -> None:
    """Latched by hand rather than with `once=`: the watcher has to see
    every `Hit` until one of them is a fear power of mine, and `once=`
    would spend it on the first blow of any kind.

    The enemy *hits* itself, and `c.basic` rolls what it grants. Forcing
    the roll to land is what `c.as_though_hit_by` does internally and the
    only shape there is: a listener on `AttackRolled` sets `forced` on
    the result, which the recompute at the close of the window honours.
    Subscribed around the one swing and taken off again, so no other
    attack in the fight is rigged by it."""
    me = c.me
    spent: list[int] = []

    def on_hit(ev: Any) -> None:
        if spent or ev.attacker != me:
            return
        p = get(ev.power)
        if p is None or Keyword.FEAR not in p.keywords:
            return
        spent.append(ev.target)
        foe = ev.target

        def turn_on_itself(_ev: Any) -> None:
            def lands(rolled: Any) -> None:
                result = getattr(rolled, "result", None)
                if (
                    result is not None
                    and rolled.attacker == foe
                    and rolled.target == foe
                ):
                    result.forced = True

            sub = c.world.bus.on(AttackRolled, lands)
            try:
                c.basic(who=foe, on=foe)
            finally:
                c.world.bus.off(sub)

        c.on_attack(turn_on_itself, by=foe, until=When.EOTNT, once=True,
                    label="f1452b")

    c.watch(Hit, on_hit, on=me, until=When.EOT, label="f1452b")


_granted("f1454", "f1454b")


@power("f1454b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=ONE_ALLY, keywords=DIVINE_HEAL,
       group=CHANNEL_DIVINITY)
def f1454b(c: Cast) -> None:
    """The d8 at the start of each of your turns ends itself either way,
    so the watcher is latched with a flag rather than `once=`: an odd
    roll onto a target with no temporary hit points keeps it running.

    "Wisdom or Charisma modifier" is the better of the two, as every
    other either-ability line in the tree is read."""
    who = c.target
    if who is None or not c.bloodied(on=who):
        return
    c.heal(max(c.wis_mod, c.cha_mod), on=who)
    done: list[bool] = []

    def each_turn(ev: Any) -> None:
        if done or ev.actor != c.me:
            return
        roll = c.roll("1d8")
        if roll % 2:
            health = c.world.get(who, Health)
            had = health.temp if health is not None else 0
            c.temp_hp(roll, on=who)
            if had:
                done.append(True)
        else:
            c.heal(roll, on=who)
            done.append(True)

    c.watch(TurnStart, each_turn, on=c.me, until=When.ENCOUNTER,
            label="f1454b")


_granted("f1456", "f1456b")


@power("f1456b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_CREATURE, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1456b(c: Cast) -> None:
    """Against *that* creature and with poison powers only, both of which
    the attack context carries."""
    foe = c.target
    if foe is None:
        return
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT, kind="power",
        when=lambda ctx: (
            ctx.get("target") == foe
            and (p := get(ctx.get("power", ""))) is not None
            and Keyword.POISON in p.keywords
        ),
    )


_granted("f1458", "f1458b")


@power("f1458b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(5), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you or an ally within 5 squares uses his or her second wind",
       on=Trigger(SecondWind, either(about_me, ally_within(5)),
                  "you or an ally within 5 squares takes a second wind"))
def f1458b(c: Cast) -> None:
    """"The triggering character" is the event's actor rather than
    `c.target`: the burst would otherwise offer any ally standing in it,
    and the printed target is whoever was winded -- which may be you.

    `SOTNT`, not `SONT`: the printed clock is the target's next turn and
    the target is usually somebody else."""
    who = c.trigger.actor
    for what in (AC, FORT, REF, WILL):
        c.bonus(what, 3, on=who, until=When.SOTNT, kind="power")


_granted("f1460", "f1460b")


@power("f1460b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=CloseBurst(10),
       target=ONE_ALLY, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you or an ally within 10 squares is pushed, pulled or slid",
       on=Trigger(ForcedMove, lambda w, me, ev: _ours(w, me, ev.target, 10),
                  "one of ours is moved against its will"))
def f1460b(c: Cast) -> None:
    """`ForcedMove` names its subject `target`, so the predicate reads
    that and not `actor` -- which on this event is whoever did it."""
    c.slide(2, on=c.trigger.target)


_granted("f1462", "f1462b")


@power("f1462b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you make a skill check",
       on=Trigger(SkillCheck, lambda w, me, ev: ev.actor == me,
                  "you make a skill check"))
def f1462b(c: Cast) -> None:
    """`c.boost_check` is what adds to a roll already on the table; the
    standing half is an ordinary `skill:<name>` modifier, keyed off the
    skill the trigger names."""
    me = c.me
    c.boost_check(2)
    skill = c.trigger.skill
    for who in (me, *allies(c.world, me)):
        if who == me or distance_between(c.world, me, who) <= 10:
            c.bonus(f"skill:{skill}", 2, on=who, kind="power", until=When.EONT)


_granted("f1464", "f1464b")


@power("f1464b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1464b(c: Cast) -> None:
    """Your own vulnerability is the price and is not optional.

    The target's side is an either/or: no resistance and it gains the
    vulnerability, some and it loses that instead. Losing it is a
    negative `c.resist` -- the one case `c.resist` stays arithmetic
    rather than taking the highest -- for exactly what is standing, read
    off `c.resistances`, so the hold puts it back when it ends."""
    both_types = (DamageType.LIGHTNING, DamageType.THUNDER)
    for dtype in both_types:
        c.vulnerable(5, dtype, on=c.me, until=When.EONT)
    foe = c.target
    if foe is None:
        return
    standing = c.resistances(on=foe)
    held = {d: standing[d] for d in both_types if standing.get(d, 0) > 0}
    if not held:
        for dtype in both_types:
            c.vulnerable(5, dtype, on=foe, until=When.EONT)
        return
    for dtype, amount in held.items():
        c.resist(-amount, dtype, on=foe, until=When.EONT)


_granted("f1466", "f1466b")


@power("f1466b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=ONE_OTHER_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1466b(c: Cast) -> None:
    """"Its next damage roll", so the modifier is spent on one roll."""
    c.bonus("damage", c.str_mod, on=c.target, kind="power", until=When.EONT,
            once=True)


_granted("f1468", "f1468b")


@power("f1468b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=UpTo(2),
       keywords=[Keyword.CHARM, Keyword.DIVINE], group=CHANNEL_DIVINITY)
def f1468b(c: Cast) -> None:
    """"While they are within 3 squares of each other" is asked per
    attack rather than once, which is the printed line: the pair can
    break it up by walking apart."""
    foe = c.target
    if foe is None:
        return
    others = [t for t in c.targets if t != foe]
    if not others:
        c.penalty("attack", 4, on=foe, until=When.EONT)
        return
    other = others[0]
    c.penalty(
        "attack", 4, on=foe, until=When.EONT,
        when=lambda ctx: distance_between(c.world, foe, other) <= 3,
    )


_granted("f1470", "f1470b")


@power("f1470b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(2), target=EACH_ENEMY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1470b(c: Cast) -> None:
    """"Or its vulnerability increases by 5" is the same call: a second
    vulnerability of the same type replaces the standing one, and 5 on
    top of nothing is the number the card names either way."""
    c.vulnerable(5, DamageType.RADIANT, on=c.target, until=When.EONT)


_granted("f1472", "f1472b")


@power("f1472b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ENEMY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1472b(c: Cast) -> None:
    c.penalty("save", 2, on=c.target, until=When.EONT)


_granted("f1474", "f1474b")


@power("f1474b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=CloseBurst(5),
       target=ONE_CREATURE, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="an enemy within 5 squares of you makes a saving throw",
       on=Trigger(SavingThrow, lambda w, me, ev: (
           team(w, ev.actor) != team(w, me)
           and distance_between(w, me, ev.actor) <= 5
       ), "an enemy nearby makes a saving throw"))
def f1474b(c: Cast) -> None:
    """The -2 lands on the throw being answered, not on the next one.
    `SavingThrow` is announced **before** it is acted on and `saved` is
    read back -- the seam `c.unsave` uses -- and the event carries the
    die and the modifier separately, so the outcome is simply recomputed
    with two off it. Ten is the number a save beats, in
    `durations.roll_saves`.

    An immediate interrupt, so `WINDOW_OF` puts this on `Window.BEFORE`
    and the body runs inside the emit, while the answer is still
    changeable. Written the other way -- a `c.penalty("save", 2)` -- it
    would land on the *next* throw the enemy made and the printed one
    would go by untouched."""
    ev = c.trigger
    ev.saved = ev.natural + ev.bonus - 2 >= 10
    if ev.saved:
        return
    me = c.me
    for who in (me, *allies(c.world, me)):
        if distance_between(c.world, me, who) <= 5 and c.save(on=who):
            return


_granted("f1477", "f1477b")


@power("f1477b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f1477b(c: Cast) -> None:
    """A plain "+2 bonus", so untyped -- the card names no type."""
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


_granted("f1479", "f1479b")


@power("f1479b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_OTHER_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1479b(c: Cast) -> None:
    """The surge is spent for nothing and the temporary hit points are
    handed over separately, which is why this is `c.spend_surge` rather
    than `c.surge`: the target heals nothing from it."""
    who = c.target
    if who is None:
        return
    c.spend_surge(on=who)
    c.temp_hp(c.surge_value(of=who) + c.level // 2, on=who)


_granted("f1481", "f1481b")


@power("f1481b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=CloseBurst(10),
       target=ONE_CREATURE, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="you are bloodied by an enemy within 10 squares of you",
       on=Trigger(Bloodied, _bloodied_by_enemy_near,
                  "an enemy within 10 squares bloodies you"))
def f1481b(c: Cast) -> None:
    """The target is read off the trigger rather than off the burst: the
    burst would otherwise offer any enemy standing in it. Paragon steps are
    out of scope."""
    c.damage("1d8", on=c.trigger.source)


_granted("f1483", "f1483b")


@power("f1483b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_OTHER_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1483b(c: Cast) -> None:
    """"Each ally", not "you and each ally" -- the penalty half is why
    the distinction is worth the narrower target side."""
    who = c.target
    c.bonus("attack", 2, on=who, until=When.EONT)
    for defence in DEFENCES:
        c.penalty(defence, 2, on=who, until=When.EONT)


_granted("f1485", "f1485b")


@power("f1485b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=AreaBurst(1, 10), target=NO_TARGET, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1485b(c: Cast) -> None:
    c.zone(c.area(), difficult=True, until=When.EONT, label="f1485b")


_granted("f1487", "f1487b")


@power("f1487b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f1487b(c: Cast) -> None:
    """"You and each ally": the ally pool already carries the caster, so
    `EACH_ALLY` is the whole of the target line. `c.resist` is one of the
    caster-defaulting methods, hence the explicit `on=`."""
    c.resist(5, DamageType.COLD, on=c.target, until=When.EONT)


# -- racial and divine riders, heroic ---------------------------------------


@power("f1496", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1452 and the enemy's attack misses you",
       on=Trigger(PowerUsed, _used("p1452"), "you use that racial power"))
def f1496(c: Cast) -> None:
    """The surge is paid on the *miss*, and the miss belongs to the
    enemy's attack rather than to p1452, so it carries the enemy's ref
    and cannot be gated on this one. `PowerUsed` firing before the body
    is what makes the row writable: the reroll has not happened yet, so
    a one-shot watcher armed here catches exactly the attack the racial
    power was answering, and expires with the turn either way."""
    me = c.me

    def missed(ev: Any) -> None:
        if ev.target == me and c.may("spend a healing surge", who=me):
            c.surge(on=me)

    c.watch(Miss, missed, on=me, until=When.EOT, once=True)


@power("f1501", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1831",
       on=Trigger(Hit, _hit_with("p1831"), "you hit with that racial power"))
def f1501(c: Cast) -> None:
    c.vulnerable(c.cha_mod, DamageType.RADIANT, on=c.trigger.target,
                 until=When.EONT)


@power("f1503", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7548",
       on=Trigger(PowerUsed, _used("p7548"), "you use that racial power"))
def f1503(c: Cast) -> None:
    """"You or one ally in the burst" -- the burst is the racial power's
    and its radius is not on this card, so the pick is made over the
    caster and the allies standing with it, worst hurt first."""
    me = c.me
    near = [w for w in (me, *allies(c.world, me))
            if distance_between(c.world, me, w) <= 5]
    who = max(near, key=c.missing)
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)


@power("f1509", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(kind=)",))
def f1509(c: Cast) -> None:
    """Widens what a whole family of rows may be aimed at. The
    restriction lives inside each of those bodies as `c.is_kind`, and
    nothing makes a creature count as another type for one attacker."""


@power("f1511", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(kind=)",))
def f1511(c: Cast) -> None:
    """Same gap as f1509, on a different origin word."""


@power("f1513", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a channel divinity power",
       on=Trigger(PowerUsed, _cd_used, "you use a channel divinity power"))
def f1513(c: Cast) -> None:
    c.save(on=c.me)


@power("f1519", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed, _used_any(*R33), "you use a r33 racial power"))
def f1519(c: Cast) -> None:
    """The race's thirteen powers are declared and a character takes
    one, so "the racial power associated with your manifestation" is
    whichever of these it uses -- the unrecorded choice no longer stands
    between the row and its moment. `side="ally"` leaves the caster out,
    so the offer is you or one of them."""
    near = [a for a in c.within(5, side="ally") if c.can_see(a)]
    who = c.choose([c.me, *near], "who gains the temporary hit points")
    if who is not None:
        c.temp_hp(c.str_mod, on=who)


@power("f1529", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a channel divinity power",
       on=Trigger(PowerUsed, _cd_used, "you use a channel divinity power"))
def f1529(c: Cast) -> None:
    """A plain "+2 bonus to damage rolls", untyped, narrowed to divine
    attack powers -- which the damage context's `power` answers."""
    c.bonus(
        "damage", 2, on=c.me, until=When.EONT,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.DIVINE in p.keywords
        ),
    )


@power("f1532", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449",
       on=Trigger(PowerUsed, _used("p1449"), "you use that racial power"))
def f1532(c: Cast) -> None:
    """"Either your original space or your destination space" wants both
    ends of the jump, and `Moved` is the only movement event carrying
    `from_` as well as `to`. `PowerUsed` fires before the body, so the
    teleport has not happened yet: the row arms a one-shot watcher and
    reads both squares off that."""
    me = c.me

    def jumped(ev: Any) -> None:
        if ev.actor != me:
            return
        space = burst({ev.from_}, 1) | burst({ev.to}, 1)
        near = [a for a in c.in_squares(space, side="ally") if a != me]
        if not near:
            return
        friend = max(near, key=c.missing)
        c.temp_hp(c.int_mod, on=friend)
        c.shift(1, who=friend)

    c.watch(Moved, jumped, on=me, until=When.EOT, once=True)


@power("f1533", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a channel divinity power",
       on=Trigger(PowerUsed, _cd_used, "you use a channel divinity power"))
def f1533(c: Cast) -> None:
    c.conceal(on=c.me, until=When.EONT)


@power("f1535", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a channel divinity power while bloodied",
       on=Trigger(PowerUsed, _cd_used, "you use a channel divinity power"))
def f1535(c: Cast) -> None:
    """"While you are bloodied" is asked when the power is used, not when
    the bonus is read: the card gates the grant, not the swing."""
    if not c.bloodied(on=c.me):
        return
    c.bonus(
        "attack", 1, on=c.me, until=When.EONT,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and p.reach.kind == "melee"
        ),
    )


@power("f1536", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1536(c: Cast) -> None:
    """An extra success in a skill challenge. Not a fight."""


@power("f1537", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f1537(c: Cast) -> None:
    """"The target of the power" is what `PowerUsed.targets` carries, and
    targets are chosen before the body runs, so it is trustworthy here.
    The attack bonus is spent on one roll -- "his or her next attack
    roll" -- hence `once`, and it runs to the end of *that ally's* next
    turn rather than the caster's."""
    me = c.me
    near = [a for a in allies(c.world, me) if a != me and c.adjacent(to=a)]
    if not near:
        return
    friend = max(near, key=c.missing)
    c.heal(c.cha_mod, on=friend)
    foes = list(c.trigger.targets)
    if foes:
        foe = foes[0]
        c.bonus("attack", 1, on=friend, until=When.EOTNT, kind="power",
                once=True, when=lambda ctx: ctx.get("target") == foe)


@power("f1541", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("m5139a3",))
def f1541(c: Cast) -> None:
    """Mirrors onto adjacent allies "the same resistance that the power
    grants you", while that power is active.

    **Re-aimed at the row rather than at a verb.** The marker named
    `c.effects_on()`, and reading the amount back is no longer the
    binding problem: `c.resistances(on=me)` returns what is standing, by
    type. What the row names is `x_m5139a3`, which the ETL could not
    resolve and which is declared nowhere in the tree -- the same
    missing row `f2415` and `f3160` are waiting on. There is no power to
    ask whether it is active, and nothing to mirror."""


@power("f1542", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1542(c: Cast) -> None:
    """Adjacency that changes as people walk, so it is an aura of 1
    rather than a modifier laid on whoever happened to be beside you at
    the start of the fight."""
    ring = c.aura(1, label="f1542", until=When.ENCOUNTER, on=c.me)
    c.resist_in(ring, 3, DamageType.NECROTIC, side="ally")
    c.resist_in(ring, 3, DamageType.RADIANT, side="ally")


@power("f1545", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a divine encounter or daily power with the radiant keyword",
       on=Trigger(PowerUsed, lambda w, me, ev: (
           ev.actor == me and _divine_radiant(get(ev.power))
       ), "you use a radiant divine encounter or daily power"),
       dropped=("c.grants_in(when=)",))
def f1545(c: Cast) -> None:
    """The zone and its bonus play. Dropped: "with radiant powers" --
    `c.grants_in` lays a flat modifier on whoever is standing in the
    zone and takes no gate, so the narrowing has nowhere to go."""
    lit = c.zone(
        burst(squares(c.world, c.me), 1), until=When.EONT, label="f1545",
    )
    c.grants_in(lit, "attack", 1, side="ally", kind="power")


@power("f1552", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.race_option()",))
def f1552(c: Cast) -> None:
    """Swaps between a chosen at-will of another class and the one the
    r6 racial feature already granted.

    The chosen half plays: `c.borrow_row` reads the set off the registry,
    `keyword=` narrows it to the divine ones, and `uses=1` is the printed
    "as an encounter power". It already skips rows the character holds,
    which is most of "other than your own".

    **Re-aimed, and the marker was naming the wrong half.** It said
    `spec.power_ref()`, as though the other power were a name the ETL had
    failed to resolve. It is not: `rt:r6-dilettante` is declared, and
    what it is short of is the *choice* -- the card the player picked,
    which nothing records. So the pair cannot be made exclusive. Granting
    the chosen power alone is not over-generous; the card does give it as
    an encounter power, and the limit it cannot honour is "not both in
    the same encounter"."""
    c.borrow_row(keyword=Keyword.DIVINE, level=1, usage=AT_WILL, uses=1)


@power("f1557", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1557(c: Cast) -> None:
    """Adds a chosen channel divinity power of another class.

    The set used to be empty -- none of the four features deals a card, so
    "a power available as a class feature for that class" named nothing and
    the powers existed only as names in the brief. `_CHANNEL` is that set.

    "Another class" is read off the feature: a class whose feature this
    creature already has is not another class. The card adds the power to
    your list rather than lending it, so there is no use limit."""
    mine = [ref for ref in _CHANNEL if c.feat(ref, on=c.me)]
    offer = [row for ref, rows in _CHANNEL.items() if ref not in mine
             for row in rows]
    if not offer:
        return
    taken = c.choose(offer, c.ref)
    if taken:
        c.grant_row(taken, on=c.me, until=When.ENCOUNTER)


@power("f1561", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f1561(c: Cast) -> None:
    """`against="ongoing"` is the printed narrowing: without it the save
    takes whichever save-ends effect it finds first, which may well be a
    daze when the card means the burn."""
    for friend in allies(c.world, c.me):
        if c.adjacent(to=friend):
            c.temp_hp(c.con_mod, on=friend)
            c.save(on=friend, against="ongoing")
            return


# -- the channel divinity multiclass feats ----------------------------------


#: What each divine class's Channel Divinity feature actually offers.
#:
#: **The feature deals no card**, which is what made five rows in this run
#: unwritable: "a power available as a class feature for that class" named an
#: empty set, and the two powers each feat hands over were names in the brief
#: with no refs behind them. The brief carries the refs now, so the set is
#: here -- a small table for a run of rows that genuinely share a shape,
#: which is the one exception the global rule allows.
_CHANNEL: dict[str, tuple[str, ...]] = {
    "cf:cleric-templar-f0": ("p1589", "p146"),
    "cf:invoker-f0": ("cf:invoker-f1c1", "cf:invoker-f1c0"),
    "cf:paladin-f0": ("p1746", "p1747"),
    "cf:avenger-f2": ("p5330", "p5331"),
}


@power("f1622", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1622(c: Cast) -> None:
    """Two channel divinity powers of another class, and the standing
    that comes with them.

    "If you do not already have the class feature, you are considered to
    have it" is exactly `c.grant_row`, which returns `None` when the
    creature already knows the row rather than handing it twice. That is
    what every later divinity feat's prerequisite reads.

    **The two powers are no longer dropped.** The card names them in
    prose and the brief now carries their refs, so they are handed over
    with the standing. Four feats in this run have the same shape and
    differ only in the pair."""
    c.grant_row("cf:cleric-templar-f0", on=c.me, until=When.ENCOUNTER)
    for ref in ("p1589", "p146"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power("f1623", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1623(c: Cast) -> None:
    """Same shape as f1622, on another class's pair: the standing and both
    named powers."""
    c.grant_row("cf:invoker-f0", on=c.me, until=When.ENCOUNTER)
    for ref in ("cf:invoker-f1c1", "cf:invoker-f1c0"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power("f1624", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1624(c: Cast) -> None:
    """Same shape as f1622, on another class's pair: the standing and both
    named powers."""
    c.grant_row("cf:paladin-f0", on=c.me, until=When.ENCOUNTER)
    for ref in ("p1746", "p1747"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power("f1625", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1625(c: Cast) -> None:
    """Same shape as f1622, on another class's pair: the standing and both
    named powers."""
    c.grant_row("cf:avenger-f2", on=c.me, until=When.ENCOUNTER)
    for ref in ("p5330", "p5331"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power("f1627", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1627(c: Cast) -> None:
    """One chosen channel divinity power of another class, and the standing.

    The card offers a choice of four features and names no leg to read it
    off, so it goes to the decider like any other choice the sheet does not
    record. The chosen *power* is no longer dropped -- `_CHANNEL` holds what
    each feature offers.

    **Both printed branches end up granting the power**, and differ only in
    the price: without the feature it is one use a day, with it the power
    joins your list. `uses=1` is the first and the absence of it is the
    second."""
    held = [ref for ref in _CHANNEL if not c.feat(ref, on=c.me)]
    if not held:
        return
    taken = c.choose(held, c.ref)
    if not taken:
        return
    c.grant_row(taken, on=c.me, until=When.ENCOUNTER)
    power = c.choose(list(_CHANNEL[taken]), f"{c.ref}:power")
    if power:
        c.grant_row(power, on=c.me, until=When.ENCOUNTER, uses=1)


@power("f1628", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:holy-symbol",))
def f1628(c: Cast) -> None:
    """`c.grant_row` can hand over a trait now: `turns.arm_traits_of`
    re-reads `Powers.all` between passes, so a row appended while it is
    arming is armed on the next one rather than never. The implement
    proficiency is in the header already."""
    c.grant_row("cf:cleric-templar-f1")


@power("f1629", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True,
       proficiency=("w:rod", "w:staff"))
def f1629(c: Cast) -> None:
    """The training and the ritual feature are not a fight, and the
    implement grant lands when the character is built. Nothing is left
    for a board, which is what `out_of_combat` says."""


@power("f1630", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:holy-symbol",))
def f1630(c: Cast) -> None:
    """The power half plays: this one is given by ref, so it is an
    ordinary grant. How long it lasts is the granted row's own business.
    The implement grant is settled at build time, off the header."""
    c.grant_row("p3069", on=c.me, until=When.ENCOUNTER)


@power("f1631", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:holy-symbol",))
def f1631(c: Cast) -> None:
    """The same shape as f1630, and the spec names the power by ref now,
    which was the whole difference between the two. The granted row is a
    daily of its own, so it carries the printed once-a-day limit."""
    c.grant_row("p7240", on=c.me, until=When.ENCOUNTER)


# -- the r47 run ------------------------------------------------------------


@power("f1639", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RIDER_RETYPE)
def f1639(c: Cast) -> None:
    """**Re-aimed.** The marker said `c.deals(ref=)` -- retyping one
    named row rather than this creature's weapon -- and that is written
    now, four times over, in `_retype` above. It does not answer here.

    `p8278` rolls no damage and makes no attack: its whole payload is a
    typed damage rider laid on the *next* blow the character lands, so
    no `DamageRolled` ever carries `detail == "p8278"` to catch.
    `deal_damage` splits a blow into typed parts, a rider is a part of
    its own, and only `parts[0]` -- the power's own -- is reachable from
    the event. Nothing retypes the part a modifier contributed."""


@power("f1640", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f1640(c: Cast) -> None:
    """Pays out "the extra necrotic damage dealt", which is a component
    of a roll rather than the roll. `DamageApplied` carries the total and
    no power, so the component cannot be picked out of it."""


@power("f1641", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f1641(c: Cast) -> None:
    """**Unwritten, and it was worse than a marked row.** It was declared
    on `Trigger(Hit, ...)` gated on `ev.power == "p8278"`, and `p8278`
    makes no attack: it is a free action that lays a damage rider on the
    next blow the character lands. No `Hit` in any fight carries that
    ref, so the row was armed and could never fire.

    The printed moment is "when you deal the **additional necrotic
    damage** from `p8278`", which is a component of somebody else's
    blow. The number wanted here is the caster's own Constitution
    modifier and is not the problem; the moment is. `DamageRolled`
    carries the blow, and the part a modifier contributed is not on it.

    The body it had, kept for whoever closes that: on the hit, every
    other creature this caster has cursed takes `c.con_mod` necrotic."""


@power("f1642", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.living()",))
def f1642(c: Cast) -> None:
    """**Re-aimed, and written.** The marker said `c.counts_as(kind=)`
    and that verb arrived: `c.set_origin` writes a type word onto a
    creature and `instead_of` takes one off, which is the only thing
    that can. `rt:r47-origin` writes both `undead` and `living` onto
    this race; this feat takes the second back.

    The eating, drinking and breathing half is not a fight.

    Dropped, and it is the clause `rt:r47-origin` drops for the same
    reason: no row in the tree asks whether a creature is living. They
    all spell it as the absence of `undead`, so taking the word off
    changes no answer until one reader settles it."""
    c.set_origin(instead_of="living", until=When.ENCOUNTER)


@power("f1643", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.dying_as()",))
def f1643(c: Cast) -> None:
    """A minor action on the turn a racial trait buys by staying up at 0
    hit points. `c.extra_action` is the payout and `Dropped` is the
    moment, so neither half is what is missing.

    **Re-aimed at the trait this hangs off.** The condition is "if you
    choose to remain conscious due to `rt:r47-unnatural-vitality`", and
    that row is itself unwritten on `c.dying_as()` -- `resolve` applies
    the dying condition and nothing chooses what comes with it. Until it
    does, there is no choice to have made and this row would pay out on
    every knockdown."""


_granted("f1644", "f1644b")


@power("f1644b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(10), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY,
       trigger="you or an ally fails a check or a saving throw",
       on=(
           Trigger(SkillCheck, lambda w, me, ev: (
               not ev.success and _ours(w, me, ev.actor, 10)
           ), "one of ours fails a check"),
           Trigger(SavingThrow, lambda w, me, ev: (
               not ev.saved and _ours(w, me, ev.actor, 10)
           ), "one of ours fails a saving throw"),
       ))
def f1644b(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- `on=` takes a
    sequence, and declaring half of a list like this looks finished and
    is not. Both rerolls work off the event rather than off a creature,
    so an ally's roll is as reachable as the caster's."""
    if isinstance(c.trigger, SkillCheck):
        c.reroll_check(keep="best")
    else:
        c.reroll_save(keep="best")


@power("f1646", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=RIDER_RETYPE)
def f1646(c: Cast) -> None:
    """Two named rows take a damage type chosen at build time, and one
    of them plays.

    **The build choice was not missing.** The marker carried
    `chargen.race_choice()`; the r1 breath's chosen type is recorded as
    `element:<type>` on the build and `c.element` reads it -- `p1448`
    reads it for its own damage line, which is the same question. So the
    p1448 half is an ordinary retype, and "that damage type **and**
    necrotic" is a blow of two types, which is `DamageRolled.dtypes` --
    the "and", where setting `dtype` alone would be the "instead".

    Dropped: the p8278 half, for the reason f1639 gives."""
    me = c.me
    picked = c.element(on=me)
    if picked is None:
        return

    def both(ev: Any) -> None:
        if ev.source == me and ev.detail == "p1448":
            ev.dtypes = (picked, DamageType.NECROTIC)

    c.watch(DamageRolled, both, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)


@power("f1652", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f1652(c: Cast) -> None:
    """**Unwritten, and it was silently false.** It laid a damage bonus
    gated on `ctx["power"] == "p8278"`, and the damage context's `power`
    is the ref of the row whose blow is being rolled. `p8278` never
    rolls one -- it lays a rider on the next blow the character lands --
    so the gate was false in every fight and the bonus was never read.

    "+2 to the damage dealt by `p8278`" means +2 on that rider, and the
    rider is a part of somebody else's blow with no identity on the
    event."""


@power("f1656", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.race_option()",))
def f1656(c: Cast) -> None:
    """Grants a second race's feature and lets an encounter pick between
    that feature's power and `p8278`.

    **Re-aimed.** Races are declared now, so "there is no race to hold
    it" is no longer true and the marker was naming a gap that closed.
    `rt:r6-dilettante` is declared -- and is one of the twenty-one rows
    `_option` leaves on `c.race_option()`, because the feature is a
    *pick* from a printed set and nothing records which card was taken.
    An either/or between `p8278` and a card nobody can name has no
    second half."""


@power("f1659", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RIDER_RETYPE)
def f1659(c: Cast) -> None:
    """Same gap as f1639, on a different type, and re-aimed with it."""


@power("f1660", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1660(c: Cast) -> None:
    """A plain "+1 bonus", so untyped. AC is not on the list."""
    for defence in (FORT, REF, WILL):
        c.bonus(defence, 1, on=c.me, until=When.ENCOUNTER)


@power("f1662", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f1662(c: Cast) -> None:
    """The same dead trigger as f1641 and unwritten for the same reason:
    `Trigger(Hit, ev.power == "p8278")` names a hit that `p8278` never
    makes. The payout it wanted, once the moment exists, is `c.con_mod`
    necrotic onto every other enemy this caster has marked."""


@power("f1663", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, lambda w, me, ev: ev.actor == me, "you go down"))
def f1663(c: Cast) -> None:
    """`Dropped` carries `actor` and no target, which is all this needs:
    the swing is at whoever is nearest."""
    reachable = [f for f in enemies(c.world, c.me) if c.adjacent(to=f)]
    if not reachable:
        return
    c.basic(on=min(reachable, key=lambda f: distance_between(c.world, c.me, f)))


@power("f1664", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1664(c: Cast) -> None:
    """A trait is armed after the opening rolls, so `c.initiative` is
    what actually moves a creature in the order. "The end of your first
    turn" from before turn one is `EONT`.

    "And checks" is the blanket `skill` key, which `skills.modifier`
    totals beside `skill:<name>` on every check there is -- which is
    what a bonus naming no skill means. The clause was dropped on the
    belief that a skill bonus has to name one; it does not."""
    if not c.may("take a penalty to initiative"):
        return
    c.initiative(-10, on=c.me)
    c.bonus("attack", 2, on=c.me, until=When.EONT)
    c.bonus("skill", 2, on=c.me, until=When.EONT)


@power("f1666", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1666(c: Cast) -> None:
    c.resist(5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)


@power("f1667", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1667(c: Cast) -> None:
    """Skill training and a bonus to two skill checks. Not a fight."""
