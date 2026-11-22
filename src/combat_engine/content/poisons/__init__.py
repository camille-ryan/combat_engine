"""The seven heroic poisons a character can put on a weapon. #1452.

One row per printed dose, keyed on its own `poison` table ref -- `x4_1`,
`x4_2` -- which is the shape `content/diseases` uses and for the same
reason: the dispatcher runs the right row off the ref with no lookup
table.

## How a row here is reached

`c.apply_poison(bite)` coats a weapon and runs `bite(ev)` on the next hit
with it. These rows **are** that bite: `i2061p2` reads which dose is in
the gloves, hands the coated weapon a `bite` that uses the dose's row
against whoever was hit, and spends it. So a poison is not a power the
character "uses" -- `action=ActionType.NONE` and no declared trigger,
like a disease -- and the attack it makes is the dose's own, not the
character's.

**`target=ONE_CREATURE` and not `NO_TARGET`, which a disease uses.** A
disease happens to the creature carrying it; a poison **attacks** one
creature, which is what its printed Attack line says. The first draft
copied the disease header and `dsl.use` then refused every row outright:
it computes no targets for a `NO_TARGET` row, so an explicit
`targets=[victim]` was ignored and the body found `c.target` empty.
Measured -- `usable` answered True and `use` returned False, which is the
hardest shape of this to read.

**The attack bonus is the printed one and is not derived.** A poison's
`+8 vs. Fortitude` is a property of the poison, so `Attack(printed=)`
carries it and nothing scales it against whoever is carrying the vial.
That is the whole reason these are rows rather than a table of riders.

## Scope: seven of nineteen, and the test is delivery

`game.db` holds 19 printed doses and 11 are heroic. Four of the eleven
**cannot be put on a weapon** and are deliberately not declared, which is
the rule `content/diseases` sets -- a row nothing can give a character is
worse than a gap, because the audit cannot tell a wrong row from an
unreachable one:

* `x4_5` -- *"can be delivered only by way of food or drink"*, and its
  first attack is `2d6` **minutes** after the victim consumes it
* `x4_14` -- *"works only when it is inhaled"*
* `x4_19` -- applied to food or a gallon of liquid; the attack is a round
  after consuming
* `x4_18` -- *"is an ingested poison"*, attacking five minutes after a
  dose is consumed

Each of those four has no moment inside a fight at all, so there is
nothing for a body to do and no board that could pose one. The eight
paragon and epic doses are out of band for a different reason --
`etl/build.py` caps powers at level 10.

## Two clause shapes, both already in the tree

**"Save ends both" is one effect, never two.** A hold and its ongoing
damage hang on a single `c.condition(..., ongoing=)`, because two effects
would hand the victim two saving throws against one printed sentence.

**"X instead of Y" replaces and does not add.** The escalation chain ends
the standing hold and re-lays it with the worsened condition, carrying
the ongoing damage forward -- `monsters/level_07.m108a0` is the worked
precedent and prints the identical structure. `c.worsen` is the *other*
shape, for "the target is **also** dazed", and is wrong here.
"""
