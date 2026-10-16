# Attributing a share of a damage roll to the modifier that laid it

#619's real gap, for four heroic `p8278` feats. Scoped, not built — the
build has a hazard worth naming before anybody starts.

## Why the rows cannot be written today

`p8278` pays its extra through a **modifier**, not a `c.damage` call:

```python
c.bonus("damage", max(c.con_mod, c.cha_mod), dice="1d8",
        until=When.EONT, on=c.me, once=True, dtype=DamageType.NECROTIC)
```

So when the blow lands, that share is summed into one number and nothing
names it. Compare `f3215`, which **is** written: the striker riders pay with
`c.damage(..., detail=label)`, so `DamageApplied.detail` names the rider
exactly. The difference is the payment mechanism, not the sentence.

What each row needs:

| row | needs |
|---|---|
| `f1640` | the **amount** p8278 contributed (temp hp equal to it) |
| `f1641` | the **moment** only — other cursed creatures take Con mod |
| `f1662` | the moment only — other marked enemies take Con mod |
| `f1652` | to **raise** the rider: "+2 feat bonus to the damage dealt by p8278" |

## Where the attribution point is

One place. `resolve.deal_damage` sums the damage modifiers through

```
_split_mods(world, source, "damage", dmg_ctx)  ->  Mods.split(what, ctx)
```

and `Mods.split` already buckets by damage type **and label** internally
(`best[(m.dtype, m.label)]`). So the information exists inside that
function and is discarded on the way out.

## The hazard, which is the reason this is a plan and not a commit

**A second pass cannot work.** `Mod.amount()` is

```python
return self.value + (self.roll() if self.roll is not None else 0)
```

and `p8278`'s rider is exactly a rolled one (`dice="1d8"`). Calling
`split` for the blow and then a new `by_label` for the attribution rolls
the die **twice** and attributes a different number from the one dealt.
Silently, and only for rolled riders.

This is the same shape as the note #619 already carries about `once=True`
being spent when read, one step over: **anything that reads a modifier
consumes something.** So:

* the breakdown must come out of the *same* `split` call that the blow
  uses — either as a second return value or by `split` returning a richer
  structure;
* every current caller of `split` is `deal_damage` (its docstring says so),
  which keeps the blast radius to one function and its two call sites
  (`"damage"` and `"crit_damage"`).

## Shape of the fix

1. `Mods.split` returns the per-label breakdown alongside the per-type one,
   from the single pass it already makes. Nothing else calls it.
2. `deal_damage` carries that breakdown onto `DamageRolled`/`DamageApplied`
   as a new field — `parts_by` or similar.
3. `c.rider_from(ref)` reads it off the triggering event, which is the
   verb the four rows are marked for.
4. `f1641` and `f1662` need only `> 0`; `f1640` needs the number.
5. `f1652` is **different and may not need any of it**: "a +2 bonus to the
   damage dealt by p8278" is a bonus on a bonus. Worth checking whether it
   can be a `c.bonus("damage", 2, when=<p8278's rider is in this blow>)`,
   which needs the breakdown at modifier-read time rather than at event
   time — i.e. possibly a different answer from the other three. Read its
   card against the other three before assuming one mechanism.

## Costs

* **All 7 replay fixtures re-record**, because a new event field changes
  every recorded event's shape. That is a repr change and not a behaviour
  change, so the re-record must be checked by counting events by kind — the
  way `level-3-full` was checked at `80d1cfd` — rather than trusted.
* `lint._event_attrs` reads the dataclass fields, so it learns the new one
  for free.
* The damage path is the one `_weapon_dtype`'s note warns about for
  ordering: it sums modifiers against `dmg_ctx["dtype"]` *before* it emits,
  so a reader added after the emit sees a settled number and a reader added
  before changes what lands.

## Not in scope

`f1114` (a rider on every target hit, not the first) and
`f2766`/`f763` (raise an **ongoing** amount already set) are #619's other
two gaps and are untouched by this. Their markers are accurate.
