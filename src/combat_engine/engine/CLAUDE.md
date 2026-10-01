# Engine

The rules kernel: events, components, resolution, durations, the grid, turns,
triggers. It decides what *happens*. It does not decide what any row does
(Content) or what the AI chooses (`combat_engine.policy`, which used to live
here and does not any more).

Global rules are in the root `CLAUDE.md`. This file is what is different
here.

## Every change here is expensive, so know why before making one

`scripts/audit.py`'s `WIDE` list widens `--changed` back to **all 12,197
rows** the moment anything under `engine/` is touched. That is correct — an
engine change moves every row at once, so a narrowed run would not be narrow,
it would be wrong — and it costs about ten minutes.

That cost **has been measured and cannot be tuned away.** Read `_changed`'s
docstring before trying: worker counts and chunk sizes were benchmarked and
the current setting is the best available, because this machine has four
performance and six efficiency cores and repeat runs vary 15%.

Use the narrow forms while iterating, and pay for the wide one once:

```
uv run scripts/audit.py --calls 'c.foo()'   rows naming a verb — seconds
uv run scripts/audit.py --verdicts          is the verdict itself honest
uv run scripts/audit.py --sample 300        a direction, not a number
```

`--calls` is right for an **additive** verb, which is most engine work. It is
blind to a row that changes behaviour without naming the verb, so it is
evidence the verb works, never evidence nothing else broke.

## The failure mode this component produces

**Silently false.** Not a crash — a predicate reading a field its event
lacks, a gate on a context key that does not exist, a modifier nothing
consults, a symbol spelled correctly with no row behind it. Every one looks
like a working row.

Worked examples, all real:

* `c.bonus("initiative")` was read by nothing, because `Initiative.bonus` is
  summed before the d20 and `Mods` is never consulted. Seven rows.
* `ev.duration is When.SAVE_ENDS` — the field is a `str` and the member is an
  enum, so the identity test was False on every event the row ever saw.
* `Relations.set` imposed a grab without emitting `ConditionApplied`, so
  thirteen rows watching for one were armed, read correctly, and could never
  fire.

So: **read the event before reading a field off it**, and the context before
gating on a key. A `getattr` with a default hides the mistake. `lint.py`'s
predicate walk catches some of this; it is not a substitute for reading.

## Rules

* **A new verb needs a reader.** A modifier nothing consults is the
  commonest bug in this component's history. `lint.py`'s
  `UNREAD_MODIFIER_KEYS` is the guard, and its one entry is a spelling that
  is banned precisely because it had no reader.
* **Header is data, body is code.** A row's decorator is read by the UI and
  the AI policy *without running anything*, which is why the attack line and
  the damage expression live there. Resolve anything per-caster in the header
  (see `Attack.ability_for`), never by making the body compute it.
* **Check the verb does not already exist** before adding one:
  `grep -n "def thing" cast.py` and `uv run scripts/vocab.py --brief`. Of
  roughly 21 verbs wanted across one issue and five comments, **15 already
  existed**.
* `cast.py` is 7,500 lines and many agents edit it at once. `lint.py` walks
  it for a duplicate `def` in a class for exactly that reason.

## The cross-cutting modules

Changing one of these reaches most of the tree. Importer counts:

| Module | Importers |
|---|---:|
| `query.py` | 325 |
| `events.py` | 247 |
| `triggers.py` | 93 |
| `dsl.py` | 87 |
| `components.py` | 81 |
| `grid.py` | 76 |
| `types.py` | 54 |

`cast.py` has only 9 direct importers and that badly understates it — it is
reached as the `Cast` passed into every power body, not by import.

## AI Policy has moved out

It used to live here, as `policy.py`, `doctrine.py` and `threat.py`. It is
`src/combat_engine/policy/` now — **what the AI chooses**, not what the rules
allow, which is a different job from everything in this directory. #228.

What that buys, and it is the reason the move was worth doing: `audit.py`'s
`WIDE` list widens `--changed` to every row for anything under `engine/`, and a
policy change cannot break a row. There used to be a `NARROW` exemption naming
`policy.py` to spare it the ten minutes — but `doctrine.py` and `threat.py` were
never in that list, so every change to either of them paid in full. Outside
`engine/`, the exemption deletes itself.

So: **label a policy issue `policy`, and a policy change audits nothing.** That
is correct and it means this instrument is not its cover — `replay` and `fight`
are, both playing whole fights through the policy, and both run in `check.py`.

`engine/__init__.py` no longer re-exports `install`, `take_turn`, `Policy`,
`Memory` or `DoctrinePolicy`; import them from `combat_engine.policy`. The
re-export had to go because `policy` imports `engine`, and keeping it would have
made that a cycle.

## Seam

* **Engine must not reach into `content/`.** It does, at five sites —
  `cast.py:382,3982,4075,4095` and `query.py:380` — all function-local to
  dodge the import cycle. The kernel needs a spawner and a row lookup and
  reaches into content to get them, which means **the kernel cannot run
  without a built database**. Do not add a sixth; if you need one, that is
  the issue to file.
* `engine` → `etl` and `engine` → `api` are both **zero**. Keep them zero.
* 638 of 677 content modules import from here, so a signature change here is
  a content-wide change. Say so in the commit.
