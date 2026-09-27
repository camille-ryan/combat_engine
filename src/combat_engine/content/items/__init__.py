"""Magic items: what a Property does, and what a Power does when spent.

**An item is not a new kind of thing.** A magic longsword is the printed
longsword with an enhancement bonus and some rows attached, so nothing
here declares a weapon, a weapon group or a suit of armour. The base item
is whatever the character was already carrying, and `item.base` says
which base items the magic may be laid on.

The numbers are not here either. The level ladder, the enhancement bonus,
the price, the slot and the critical rider are columns in `game.db` and
are applied by `engine/equipment.py` -- the same division of labour a
monster's hit points have. What is written here is only the part that
needs a body.

Filed by slot, because that is the column the compendium sorts on and the
unit a wave is briefed with. A file holds one slot's blocks: `i601x1` is
an item's first Property and `i601p1` its first Power, and either can
land without the other.
"""
