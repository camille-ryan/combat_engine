"""Putting a magic item on, and taking it off again.

The rule this file exists to hold is the repo owner's: **a magic item is
not a new kind of thing.** A magic longsword is the printed longsword with
an enhancement bonus and some rows attached. So equipping one never builds
a `Weapon`; it either raises the enhancement of a weapon already carried,
or it hangs a modifier and some rows on the creature.

Four things a worn item can do, and each reaches the fight by a road that
already existed:

* **an enhancement bonus to attack and damage** -- written onto the
  `Weapon`, where `Cast._attack_bonus` and `Cast._enhancement` read it;
* **an enhancement bonus to AC or to the other three defences** -- a `Mod`,
  because `query.defence` already sums `Mods.total` and is the only
  gameplay reader of `Defenses`;
* **a critical rider** -- a `Mod` on `crit_damage`, rolled, which
  `resolve.deal_damage` reads in the crit branch;
* **a quiver of magic ammunition** -- `Gear.quiver`, because a piece is
  spent on one shot rather than worn for a fight, and `engine/ammunition`
  is what ties the shot to the piece;
* **its own Properties and Powers** -- appended to `Powers.known`, so
  recharge, the action menu, the trigger dispatcher and `PowerUsed` all
  work on them without knowing they came from an object.

Nothing here reads `game.db`. A `Magic` is built by whoever is handing the
item out -- `chargen/` for treasure, a power body for a thing
picked up off the floor -- exactly as a monster's hit points are read in
`content/loader.py` and handed to the engine as numbers.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .ammunition import FIRES
from .components import Ammo, Gear, Magic, Mod, Mods, Powers, Weapon
from .types import Defense

#: Slots whose enhancement is an AC bonus, and the three defences the neck
#: raises. Both are printed on the item, not inferred from the slot -- but
#: `enh_to` says only *which group*, so this is the group.
_DEFENCES = (Defense.FORT, Defense.REF, Defense.WILL)

#: A mod laid by an item is labelled with the item's ref, so taking the
#: item off can find exactly its own and nothing else.
_LABEL = "item:"


def equip(world, eid: int, magic: Magic, *, onto: str = "", count: int = 10) -> None:  # noqa: ANN001
    """Wear or wield one magic item.

    `onto` is the ref of the base weapon an `attack_damage` item is laid
    on. Without it the item goes on whatever the creature would swing,
    which is what handing somebody a magic sword means -- but a character
    carrying two blades has to be told which.

    `count` is how many pieces of ammunition are being handed over, and is
    ignored by everything else. Not a printed number -- the card says what
    one piece does and says nothing about how many you bought -- so it is
    an argument rather than a constant, and the default is a quiver's
    worth so that a fight has something to run out of.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return

    # `worn` records **every** magic item on the creature, including the
    # one that is a weapon. The weapon additionally carries the bonus,
    # because that is where the attack roll looks -- but "what magic is
    # this creature carrying" has to have one answer, or the rows an item
    # grants belong to no item and `ItemPowerUsed` has nothing to name.
    if magic.slot == "ammunition":
        # Neither worn nor wielded: a piece of ammunition is *spent*, so it
        # goes in the quiver and its enhancement and critical rider stay on
        # the piece rather than being written onto the bow. Laid on the bow
        # they would have raised every shot the wielder ever made,
        # including the ones fired after the last magic arrow was gone.
        _into_quiver(gear, magic, count)
    else:
        gear.worn[magic.slot or magic.ref] = magic
        if magic.enh_to == "attack_damage":
            _onto_weapon(gear, magic, onto)
        else:
            _defence_mods(world, eid, magic)
        _crit_rider(world, eid, magic)

    powers = world.get(eid, Powers)
    if powers is not None:
        for ref in magic.powers:
            if ref not in powers.known:
                powers.known.append(ref)


def unequip(world, eid: int, ref: str) -> None:  # noqa: ANN001
    """Take it off. Everything it laid goes with it.

    Its mods are found by label rather than kept in a list on the item,
    because the item is a value and the modifiers live on the creature --
    and a list of objects to undo is the kind of bookkeeping that goes
    stale the first time something else ends one of them.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return
    gear.worn = {k: v for k, v in gear.worn.items() if v.ref != ref}
    gear.weapons = [
        replace(w, enhancement=0, item="") if w.item == ref else w
        for w in gear.weapons
    ]
    gear.quiver = [a for a in gear.quiver if a.ref != ref]
    mods = world.get(eid, Mods)
    if mods is not None:
        mods.items = [m for m in mods.items if m.label != f"{_LABEL}{ref}"]


def _into_quiver(gear: Gear, magic: Magic, count: int) -> None:
    """Put `count` pieces in the quiver, replacing any of the same item.

    The kind is the base-item column -- arrow, bolt or stone -- and an
    item that names none fits any launcher, which is what the two rows
    printing no base item mean.
    """
    kind = next((b for b in magic.base if b in set(FIRES.values())), "")
    gear.quiver = [a for a in gear.quiver if a.ref != magic.ref]
    gear.quiver.append(Ammo(ref=magic.ref, kind=kind, plus=magic.plus, count=count))


def _onto_weapon(gear: Gear, magic: Magic, onto: str) -> None:
    """Raise the enhancement of the thing this item *is*.

    **`dataclasses.replace`, never assignment.** `chargen`'s weapon
    constants are module-level singletons shared by every character built
    in the process, so writing an enhancement onto one writes it onto
    every fighter in the game -- and `Cast.decay`, which reduces a magic
    weapon's bonus, has been mutating them in place for as long as it has
    existed.
    """
    target = _base_for(gear, magic, onto)
    if target is None:
        return
    gear.weapons = [
        replace(w, enhancement=magic.plus, item=magic.ref) if w is target else w
        for w in gear.weapons
    ]


def _base_for(gear: Gear, magic: Magic, onto: str) -> Weapon | None:
    """Which carried weapon this item is.

    Named outright where the caller knows; otherwise the implement for an
    implement item and the swung weapon for a weapon one. `Gear.implement`
    exists because `main` answers the wrong question for a creature
    holding both -- a cleric with a mace and a holy symbol.
    """
    # **`"off"` is a reserved selector, not a weapon ref.** The lookup
    # below matches `Weapon.ref`, and the commonest two-weapon hand this
    # tree deals is **two of the same ref** -- a ranger on the `b:c5-4` leg with
    # two shortswords -- where that match takes the first and so always
    # the main hand. So a caller that means "the off hand" cannot say it
    # by naming a weapon, which is why `i3037x1`'s *"while you wield
    # this weapon in your off hand"* was unreachable by any dealt
    # character. Camille's ruling, #1492: *"for this specific item, it
    # should only be dealt for `f173` loadouts, so that it
    # is in the offhand."*
    #
    # No ref can collide with it: every weapon ref in the tree is
    # `w<digits>` or a `w:`-prefixed constant.
    if onto == "off":
        return gear.off
    if onto:
        return next((w for w in gear.weapons if w.ref == onto), None)
    if magic.slot == "implement":
        return gear.implement
    return gear.main or gear.implement


def _defence_mods(world, eid: int, magic: Magic) -> None:  # noqa: ANN001
    """Armour and neck enhancement, as modifiers on the creature.

    **Written straight into `Mods.items`, not through `Cast.bonus`.** That
    makes an `Effect`, and an effect with an encounter duration is cleared
    when the fight ends -- so a worn item would come off after the first
    fight of the day and nothing would say why.

    `kind="enhancement"` rather than `"item"` because armour and a shield
    both write to `ac`, and 4e's same-type rule keeps only the larger: an
    item bonus from somewhere else and this must not silently eat each
    other.
    """
    if not magic.plus or magic.enh_to not in ("ac", "defences"):
        return
    mods = world.get(eid, Mods)
    if mods is None:
        return
    wanted = (Defense.AC,) if magic.enh_to == "ac" else _DEFENCES
    for d in wanted:
        mods.items.append(
            Mod(what=d.value, value=magic.plus, kind="enhancement",
                label=f"{_LABEL}{magic.ref}")
        )


def _may_reroll_a_crit_die(world, eid: int) -> tuple[int, str]:  # noqa: ANN001
    """How many of a critical's extra dice this creature may reroll, and
    which row grants it.

    The hold is `c.reroll_ones(crit_dice=True)`'s, so the pair of keys is
    that verb's own: `reroll_damage_pick:crit` carries the threshold and
    `reroll_damage_pick:crit#n` the count. Only the `pick` shape is read.
    The loop shape -- reroll *until* the die is not low -- is refused
    against `ANY_FACE` by `_rolled_above` for the reason that verb gives,
    and a crit rider is the no-threshold card every time.

    Read off `Mods` directly rather than through `resolve._mods`, which is
    the usual reader: `resolve` imports this module, so reaching back for
    it would close a cycle.

    The granting ref comes back with it because the announcement needs a
    `by` -- a `Rerolled` nobody can attribute is a row that audits SILENT
    while working, which is `#1183`'s shape.
    """
    mods = world.get(eid, Mods)
    if mods is None:
        return 0, ""
    count, by = 0, ""
    for mod in mods.items:
        if mod.what == "reroll_damage_pick:crit#n" and mod.value > count:
            count, by = mod.value, (mod.label or "")
    return count, by


def _crit_rider(world, eid: int, magic: Magic) -> None:  # noqa: ANN001
    """"Critical: +1d6 damage per plus", which 734 heroic items print.

    Rolled rather than fixed, and multiplied by the plus, which is what
    "per plus" says. `Mod.roll` is called once per read, which is once per
    critical hit.

    **The individual faces are kept, not just the total**, because
    `_may_reroll_a_crit_die` swaps one of them and this is the only place
    they exist. The hold it reads is laid by
    `c.reroll_ones(crit_dice=True)`.

    This said `c.reroll_crit_die`, which **does not exist** -- named in
    this one docstring and nowhere else in the tree. A reader looking for
    it would either find nothing or, worse, take the facility for granted:
    `i1761p1` wants a *reactive* crit-dice reroll and the thing that
    exists is a standing hold, which is exactly the distinction its own
    marker turns on. Naming the real reader keeps that distinction
    readable. `Roll.bonus` is carried separately for the same reason: a crit
    rider printed as `1d6+2` would lose its `+2` to a faces-only sum.
    """
    if not magic.crit or not magic.plus:
        return
    mods = world.get(eid, Mods)
    if mods is None:
        return
    dice, plus = magic.crit, magic.plus

    def roll() -> int:
        rolled = [world.rng.roll(dice) for _ in range(plus)]
        faces = [f for r in rolled for f in r.dice]
        flat = sum(r.bonus for r in rolled)
        allow, by = _may_reroll_a_crit_die(world, eid)
        size = re.search(r"d(\d+)", str(dice))
        if allow and faces and size:
            from .events import Rerolled

            for _ in range(min(allow, len(faces))):
                # The lowest first: the holder chooses which die, and no
                # printed card makes swapping a high one worth doing.
                at = faces.index(min(faces))
                old = faces[at]
                faces[at] = world.rng.roll(f"1d{size.group(1)}").dice[0]
                said = Rerolled(actor=eid, roll="crit_damage", by=by,
                                old=old, new=faces[at])
                said.replaced = True
                world.bus.emit(said)
        return sum(faces) + flat

    mods.items.append(
        Mod(what="crit_damage", value=0, kind="untyped", roll=roll,
            label=f"{_LABEL}{magic.ref}")
    )
