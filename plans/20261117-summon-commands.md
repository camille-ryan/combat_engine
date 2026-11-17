# A summon's commands, one row each

## The gap

`dsl.Summon` carries **one** attack line (`attack`, `damage`) shared by the
standard and opportunity commands. Six power rows print commands that
differ from each other in shape, target count and rider, so the shared line
cannot say them and all six carry `dropped=("dsl.Summon.commands",)` — the
largest remaining dropped-clause group among the power rows.

What the six actually print:

| row | the commands |
|---|---|
| `p3314` | standard **close burst 1**; opportunity melee 1, same numbers |
| `p11840` | standard melee 1, **one or two creatures** |
| `p7641` | standard **melee 1 or ranged 5**; opportunity melee 1 **and a mark** |
| `p7657` | standard melee 1 **and the summon shifts 2**; opportunity plain |
| `p11842` | standard melee 1, **ongoing 5 poison**, **the imp turns invisible** |
| `p11296` | standard melee 1 targeting **one ally**, **heals 1d6**; **move action**: it and one adjacent ally fly 8 |

So a command needs a cost, a reach, a target line, an attack, a damage line
**and an arbitrary rider**. That last one is why no fixed set of fields on
`Summon` will do: `p11842`'s imp turning invisible and `p11296`'s heal are
body code.

## The design: a command is an ordinary row

Declare each command as a normal `@power` with its own ref and let
`Summon.commands` name them. Content then writes reach, targets, attack,
damage and riders the way it writes everything else, and the engine learns
one field.

**Three things measured on 2026-11-17 that make this small rather than
large.** Each was checked rather than assumed:

* **The executor already uses an arbitrary ref.** `actions.perform`'s
  `kind == "command"` branch ends in
  `use(world, beast, action.ref, targets=..., spend=False)`. Nothing there
  needs changing — it has never been specific to `Powers.basic`.
* **A summon already carries the summoner's `Stats`, identically.**
  Probed on `p3314`: summon and summoner both read
  `Stats(level=1, scores={WIS: 16, CON: 14, INT: 16, STR: 13, DEX: 10, CHA: 12})`.
  So a command row declared `Attack(WIS, vs=REF)` rolls the **right
  numbers from the beast**, and none of `c.command`'s `bonus_for`
  machinery has to be reproduced.
* **`Powers.known` is `None` on an inline summon.** That is why
  `_commands` offers nothing for `p3314` today — it reads `known.basic`.
  The grant has to be made when the summon is built.

## The change, in order

1. **`dsl.Summon.commands: tuple[tuple[ActionType, str], ...]`** — (cost,
   row ref), empty by default so every existing summon is untouched.
2. **`Cast.summon_inline`** puts each command ref into the summon's
   `Powers.known` (making the component if absent — `c.resist`'s
   `get(...) or add(...)` idiom, see
   `defences-and-defenses-are-two-components`).
3. **`actions._commands`** offers one `Action` per entry rather than one for
   `known.basic`: `_aimings(world, eid, ref, cost=cost)` already reads the
   named row's reach and target line, so a burst command is aimed as a
   burst for free. Keep the `known.basic` path for the summons that declare
   no commands.
4. **Content**: declare the command rows. The ref convention is
   `<summon ref>c<n>` — `dsl.entry_of` already keeps a `c<n>` suffix as its
   own entry (`m1932c0a0`), which is what stops a defective command
   defecting the summoning power.
5. Drop `dropped=("dsl.Summon.commands",)` from the six.

## Verification

* **Per command row**: `lint.py <file>`, `audit.py <ref>`.
* **A `drivers` rule**, `summon_commands`, with these assertions and a plant
  for each:
  * the menu offers one command per entry, at the printed cost;
  * `p3314`'s standard is aimed as a **close burst 1** — more than one
    target in the burst, which is the whole point of the change, and the
    negative control is that the opportunity command is aimed as melee 1;
  * `p11840`'s standard offers **two** targets and not one or three;
  * the attack rolls the **summoner's** ability, not a default — assert
    the bonus against `Attack.bonus_for(world, summoner, ...)`;
  * a summon declaring **no** commands still offers its `Powers.basic`,
    which is the regression this change could cause and nothing else
    watches.
* **Engine change, so a wide sweep is owed** — batch it with whatever else
  is in flight rather than sweeping for this alone.

## Residue, stated so it is not discovered later

`p11296`'s **move** command moves the summon *and an ally*, with the ally
falling if it does not land. The grant and the aiming are the same as any
other command; the "or he or she falls" half wants `falling.drop` on a
creature that ends a forced flight in the air, which is a second clause and
may want its own marker rather than holding this row.

## The rest of the dropped-clause tail, for ordering after this

Counted 2026-11-17: **114 power rows, 106 distinct symbols**, largest group
6. So the cheap seams are worked out and what is left is mostly one row per
symbol. The groups above 1:

```
6  dsl.Summon.commands      this plan
4  c.grant_action_row()     p10278 p12423 p13621 p7428 -- each a second
                            action in one turn, or a destination test
3  c.offer_augment()        p11158 p11165 p11172
2  c.initiative_bonus()     spent -- both rows written 2026-11-17
2  query.resting()          p11540 p9307
2  c.conjure_weapon()       p15899 p15900 -- blocked behind the damage
                            context carrying `weapon`, see #1357
```

And the eight power rows still **refused in play** are diagnosed on `#1357`
with what each needs; three of those were run down to the exact blocker and
left deliberately (`p15895` wants one key in the damage context, `p14125`
wants a pre-targeting hook that is structurally absent, `p16491` would be a
writer with no reader).
