# `c.swallowed()` is a relation, not a label

4 rows wait on `c.swallowed()` — `m3511a0`, `m2237a2`, `m3932a2` and
`i3578p1`, the last an item and so the one in the session's goal. It is
the largest non-ETL family left in the tree.

## What exists, and why no reader can span it

Being swallowed is **already written twice, by hand, with two different
conventions**:

| row | how it records the swallow |
|---|---|
| `m412a2` | `effects.apply(victim, me, SAVE_ENDS, label=_M412_INSIDE, conditions=(REMOVED,))` |
| `m6109a3` | `effects.apply(victim, me, ENCOUNTER, label=c.ref, conditions=(REMOVED,))` |

One labels with a file-local constant, the other with the row's own ref.
So nothing can ask *"is this creature inside something"* without knowing
every label any card might have used — the hand-rolled-read-in-N-files
shape.

`m412a2` also hand-rolls the capacity rule, counting live effects whose
`source` is the swallower and whose label matches its own:

```
requires=_room_inside            # fewer than 2 inside
requires_text="the m412 must not have two creatures removed from play"
```

## The fix: `Relation.SWALLOWED_BY`

`engine/relations.py`'s own module docstring is the argument, and it was
written about grabs:

> *"Grabbed, marked, dominated and hidden are not properties of a
> creature — `x is grabbed` is only half a fact, and storing it on `x`
> alone is how an engine ends up unable to answer 'grabbed by whom' when
> the grabber is knocked out."*

A swallow is the same shape and a stronger version of the grab already
there. So:

1. `types.Relation.SWALLOWED_BY`.
2. `relations.IMPLIES[SWALLOWED_BY] = Condition.REMOVED`, so setting the
   relation imposes the condition exactly as `GRABBED_BY` imposes
   `GRABBED`. Nothing new has to remember to do both.
3. The readers come for free off `Relations`:
   * `sources(SWALLOWED_BY, victim)` — **swallowed by whom**, which is
     what `i3578p1` asks;
   * `targets(SWALLOWED_BY, swallower)` — **who is inside**, which is
     the capacity rule `_room_inside` counts by hand;
   * `Target.relation=Relation.SWALLOWED_BY` works with no change, the
     way `m6109a3` already uses `relation=` for "one creature grabbed
     by it".

## Order of work

1. The relation and the `IMPLIES` entry.
2. `Cast.swallow(on=, until=, room=)` writer and `Cast.swallowed(on=)`
   reader; release through the existing `c.reappear`, whose docstring
   already describes putting a removed creature back beside the
   swallower.
3. Write `i3578p1` (the in-scope row) and the three monster rows.
4. **Migrate `m412a2` and `m6109a3` onto the relation.** Not optional:
   leaving them hand-rolled means `i3578p1` cannot detect the two
   swallows that already exist, which is the bug this plan is about.
   They are level 9 and 10, so `replay` may move — if it does, the
   re-record is its own commit.
5. One drivers rule over the family, with a plant per clause.

## What this does not do

Nothing about `m412a2`'s digest-on-your-turn or `m6109a3`'s
drop-on-death riders, which are each card's own and stay where they are.
The relation records *that* a creature is inside and *whose*; what
happens to it while there is still the card's business.
