"""Sorcerer: the fork the class page draws, and the utility that rewrites it.

The class's two builds are a choice of *source*, and the page gives each of
them four clauses. Two are written here: the damage every arcane power of
this sorcerer's gains, and the resistance -- chosen and kept on one leg,
rolled for each fight on the other. That is a class-page feature with no
compendium row, so it carries a `cf:` ref like every other one.

**The numbers are now transcribed and were previously guessed.** The
feature was written before the class features were imported, when nothing
could print them: the ladder was read off `p3763`'s own tier line and the
roll was a d6 over six types. The ladder turns out to be right -- 5, then
10 at 11th and 15 at 21st, on both legs. The roll was wrong: one leg picks
from six types and the other rolls a **d10** over ten.

**Two printed clauses are not here** and both are in `docs/blocked.json`.
`cf:sorcerer-soul-pierce` is the sentence each source ends on -- the
caster's arcane powers ignore a target's resistance to the sworn type up
to the value of this one -- which `resolve.damage` has no way to be told.
`cf:sorcerer-soul-nat20` is the pair of riders that fire on a natural 20
or a natural 1 *after* the attack's other effects, which is a moment
nothing announces. The page prints two further sources, and
`cf:sorcerer-soul-rest` says why neither has a leg in `chargen.BUILDS`;
nothing is invented for them here.

The type is held twice over: once in `c.resist`, which has nowhere to
record which type it covered, and once in a marker effect whose label names
it. `p3763` reads the marker, and ending the marker ends the resistance
with it -- so "change the resistance to one of the other damage types"
is one call rather than a search.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Effect,
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import AttackRolled, Bloodied

#: The armours the resilience clause rules out. Named rather than inverted
#: from the light list, because "not heavy" is the printed wording.
_HEAVY = ("chain", "scale", "plate")

#: The feature's ref, and the stem of both holds it lays.
SOUL = "cf:sorcerer-f0"

#: The six the leg that *chooses* may swear to. Untyped and force are not
#: on the printed list, and neither are necrotic, psychic or radiant.
SOUL_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
    DamageType.THUNDER,
)

#: The ten the other leg rolls a d10 across, in the printed order of the
#: table -- the order is the die, so it is not sorted or deduplicated.
ROLLED_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.PSYCHIC,
    DamageType.RADIANT,
    DamageType.THUNDER,
)

ARCANE = [Keyword.ARCANE]


def soul_resist(level: int) -> int:
    return 5 + 5 * ((level >= 11) + (level >= 21))


def soul_damage(level: int) -> int:
    """What the source adds to an arcane power's damage, over the modifier.

    Both legs print the same ladder and differ only in which ability the
    modifier comes off, so the step is written once here.
    """
    return 2 * (level >= 11) + 2 * (level >= 21)


def _arcane_power(ctx: dict[str, object]) -> bool:
    """"The damage rolls of arcane powers", as a modifier gate.

    Asked of the row being used rather than laid flat, because a sorcerer
    swinging a mace is not casting and the printed line says arcane.
    """
    from combat_engine.engine.dsl import get

    declared = get(str(ctx.get("power") or ""))
    return declared is not None and Keyword.ARCANE in declared.keywords


def soul_of(c: Cast) -> DamageType | None:
    """Which type this sorcerer's soul currently resists, if any."""
    by_value = {d.value: d for d in DamageType}
    for effect in c.world.effects.of(c.me):
        if effect.label.startswith(_SWORN_TO):
            return by_value.get(effect.label.rsplit(" ", 1)[1])
    return None


#: The stem of the marker alone. **Not** `SOUL`: every modifier and watch
#: this feature lays is labelled with the ref, so a swap that swept up
#: everything starting with it took the damage bonus and the riders down
#: with the resistance -- and then found no marker to read, which left
#: `p3763` doing nothing at all.
_SWORN_TO = f"{SOUL} is "


def wear_soul(c: Cast, kind: DamageType) -> Effect | None:
    """Swear the soul to a type, dropping whatever it was sworn to before.

    Only the marker is ended here. The resistance goes with it: the marker
    carries an `on_end` that takes it down, which is the one place the
    pairing is written.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(_SWORN_TO):
            c.world.effects.end(effect, "the soul changed")
    guard = c.resist(soul_resist(c.level), kind, until=When.ENCOUNTER)
    mark = c.effect(f"{SOUL} is {kind.value}", until=When.ENCOUNTER, on=c.me)
    if mark is not None and guard is not None:
        mark.on_end.append(lambda: c.world.effects.end(guard, "the soul changed"))
    return mark


def _scales(c: Cast) -> None:
    """"The first time you become bloodied during an encounter, you gain a
    +2 bonus to AC until the end of the encounter."

    Once, and the latch is here rather than `once=True` on the watch --
    `c.watch(once=True)` spends itself on the first event of the class
    whoever it is about, and a bloodied ally is not this sentence.
    """
    me = c.me
    done: list[bool] = []

    def on_blood(ev: Bloodied) -> None:
        if ev.actor != me or done:
            return
        done.append(True)
        c.bonus(AC, 2, until=When.ENCOUNTER, on=me, kind="untyped")

    c.watch(Bloodied, on_blood, until=When.ENCOUNTER, on=me, label=SOUL)


def _chaos_burst(c: Cast) -> None:
    """"Your first attack roll during each of your turns determines a
    benefit you gain in that round."

    Even buys a point of AC to the start of the next turn; odd buys a
    saving throw. The throw is a real one against whatever the sorcerer is
    carrying, and `bare=False` is deliberate -- with nothing to shake off
    there is nothing for the clause to do, which is what the sentence
    comes to.

    "The first during each of your turns" is latched on the round and the
    initiative slot together, because a creature with two turns in a round
    gets the benefit on each.
    """
    me = c.me
    seen: dict[int, object] = {}

    def on_roll(ev: AttackRolled) -> None:
        if ev.attacker != me:
            return
        fight = c.world.encounter
        if fight is None or c.world.turn != me:
            return
        now = (c.world.round, fight.index)
        if seen.get(me) == now:
            return
        seen[me] = now
        if ev.natural % 2 == 0:
            c.bonus(AC, 1, until=When.SONT, on=me, kind="untyped")
        else:
            c.save(on=me)

    c.watch(AttackRolled, on_roll, until=When.ENCOUNTER, on=me, label=SOUL)


def _resilience(c: Cast) -> None:
    """"While you are not wearing heavy armor, you can use your Strength
    modifier in place of your Dexterity or Intelligence modifier to
    determine your AC."

    `chargen.defences` has already put the better of Dexterity and
    Intelligence into the number, so what this is worth is the difference
    and nothing else. A swap written as a replacement would have to reach
    into a component the feature does not own.
    """
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in _HEAVY:
        return
    step = c.str_mod - max(c.dex_mod, c.int_mod)
    if step > 0:
        c.bonus(AC, step, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    SOUL,
    level=0,
    cls="sorcerer",
    # A trait: the soul is simply what the sorcerer is, and nobody spends
    # an action on it.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def sorcerer_soul(c: Cast) -> None:
    """Everything the chosen source is, bar the clause nothing can hear.

    One leg picks its resisted type from six and keeps it; the other rolls
    a d10 across ten. The roll is taken here rather than at an extended
    rest for the reason the wizard's book is prepared here: arming a trait
    is the only moment the engine has, and it is the same moment for
    everything that reads it.

    The damage is the same ladder on both legs and differs only in the
    ability. The two remaining clauses are one apiece and are not shared,
    so each leg calls its own.
    """
    if c.build("dragon"):
        ability = c.str_mod
        kind = c.choose(list(SOUL_TYPES), f"{SOUL}: which damage type")
        _resilience(c)
        _scales(c)
    elif c.build("wild"):
        ability = c.dex_mod
        kind = ROLLED_TYPES[(c.roll("1d10") - 1) % len(ROLLED_TYPES)]
        _chaos_burst(c)
    else:
        return
    c.bonus(
        "damage",
        ability + soul_damage(c.level),
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=_arcane_power,
    )
    if kind is not None:
        wear_soul(c, kind)


@power(
    "p3763",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p3763(c: Cast) -> None:
    """"One of the **other** damage types" -- the one it already resists is
    not on offer, which is what makes this a change rather than a renewal.

    The ally's share is a separate resistance of its own rather than the
    sorcerer's stretched over two creatures, because the printed amount is
    5 and the sorcerer's is not.
    """
    was = soul_of(c)
    if was is None:
        return
    # "One of the **other** damage types" is read off the list the soul was
    # sworn from, which is six on one leg and ten on the other -- offering
    # the six to a sorcerer whose soul is one of the other four would have
    # left the row unable to name the type it already has.
    pool = ROLLED_TYPES if c.build("wild") else SOUL_TYPES
    kind = c.choose(
        [k for k in pool if k is not was], f"{c.ref}: which damage type now"
    )
    if kind is None:
        return
    wear_soul(c, kind)
    mates = [a for a in c.allies() if c.adjacent(a)]
    if mates:
        mate = c.choose(mates, f"{c.ref}: who shares the resistance")
        if mate is not None:
            c.resist(soul_resist(c.level), kind, on=mate, until=When.ENCOUNTER)
