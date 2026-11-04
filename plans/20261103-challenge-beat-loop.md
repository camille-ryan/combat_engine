# #932: wire the skill challenge to the beat loop

Camille, playing 2026-10-29:

> *"skill challenges look to be currently automatic. They should be based on
> the actions the player (and NPCs) decide to do."*

and, correcting my first reading of the log:

> *"I don't know that the result was incorrect. But skill challenges should
> be an opportunity for narration."*

The prerequisite #932 named is **done** — the fixture challenge carries seven
skills with phrasings and win/lose facts, so the loop can be proved offline
with no model. What is left is the loop itself.

## What is wired today

`run._challenge` calls `play_challenge(...)`, which runs the **whole**
challenge internally, and then prints the attempts afterwards:

```python
run = play_challenge(scene, table, party_level=..., choose=choose)
for made in run.attempts:
    step.say(f"  {made}", "roll")
```

`step()` holds `ask_human` and `director` and hands them **only** to
`_roleplay`. So a challenge gets no declare, no match, no narration and no
DM reply. `choose` is non-`None` only under `--dm`; otherwise
`challenge.taking_turns` rotates the party deterministically, which is a
sound fallback and is currently the only behaviour anybody sees.

## The integration point, and the hazard that decides the design

`beat.one_beat(playing, table, actors, director, *, ask_human, party_level)`
is *"declare, match, roll, react"* — one exchange. The issue's own sketch is
right: a challenge beat is the roleplay beat with the affordance list
replaced by the challenge's skills.

**But `one_beat` rolls, and it rolls the wrong way for a challenge.** Read:

```python
chosen = scene.affordance(wanted) if wanted != "none" else None
...
target = chosen.dc or dc_for(level, chosen.band)
rolled = table.check(intent.slot, chosen.skill, target)
```

`challenge.attempt(run, table, slot, skill)` also ends in `table.check` —
but around it, it applies **the band reached, the per-skill cap
(`won_with`), `cap_bonus`, a spent reroll, the carried `pending_bonus`, the
secondary effects, and the tally**. None of that is in `one_beat`.

So presenting the challenge's skills as ordinary affordances would roll them
through the wrong door and silently lose every one of those. That is the
same shape as the group-skill refusal already in `challenge.attempt`: a roll
that looks like a success and was scored by the wrong rule.

**Therefore the roll must stay in `challenge.py`** and `one_beat` must be
able to delegate it.

## The change

**1. `beat.one_beat` gains a `resolve=` hook**, defaulting to today's
behaviour, so no existing caller moves:

```python
def one_beat(..., resolve: Resolver | None = None) -> Beat
```

where a `Resolver` is handed `(intent, chosen)` and returns the `Ruling`.
The default is the four lines quoted above, lifted verbatim into a module
function so the two paths cannot drift.

Why a hook rather than a flag: a flag would put challenge vocabulary inside
`beat.py`, which knows nothing about bands or tallies and should not start.
The hook keeps the *conversation* in `beat.py` and the *scoring* in
`challenge.py`, which is the existing seam.

**2. `challenge` exposes a per-turn entry.** `play_challenge` is
all-or-nothing today. Wanted:

* `start(scene, table, party_level) -> Running` — what `play_challenge`
  builds before its loop;
* `ended(run) -> bool` — the win/lose test its loop uses;
* `attempt` / `group_attempt` already take `(run, table, slot, skill)`.

`play_challenge` is then rewritten in terms of the three, so the automatic
path and the narrated path run the *same* scoring code. That is the point:
two loops would be two rulebooks.

**3. `run._challenge` drives beats.** Per exchange:

* build the affordance list from the challenge's `primary` / `secondary`
  skills, so `Director.match` turns an intent into one of them or `"none"`;
* `one_beat(..., resolve=)` where the resolver routes
  `scene.group_of(skill)` to `group_attempt` and everything else to
  `attempt`, maps the returned `Attempt` onto a `Ruling`, and carries
  `scene.means(skill, won=)` into `Ruling.fact`;
* stop when `ended(run)`, then `step.outcome = "won" if run.won else "lost"`.

`step()` must hand `director` and `ask_human` to `_challenge` as it already
does to `_roleplay` — that one-line omission is the structural cause the
issue names.

**4. `taking_turns` stays** as the no-director fallback. With `--no-dm` and
no local model there is nobody to declare an intent, and a deterministic
rotation is the printed intent rather than a stub.

## What this must not change

* **The tally.** A group check scores the party **once** however many dice
  it took; the per-skill cap counts one. Both live in `challenge.py` and the
  hook keeps them there.
* **`attempt`'s refusals.** It refuses a group skill through the
  per-character door, and `group_attempt` refuses a non-group skill. A
  resolver that bypassed either would make the challenge strictly easier or
  harder with nothing reporting it.
* **The `means` de-duplication.** `_challenge` already prints each fact once
  — *"a fact does not become true again on the second success with the same
  skill"* — and the probe that found it printed one brazier toppling three
  times. Moving the print into the beat loop must keep the `meant_already`
  set.

## Verification

The fixture module is the board, and it needs no model:

* **`drivers.fixture_challenge`** already has 5 assertions and asks through
  `Scene.means` rather than off the dataclass. Extend it: with a scripted
  `Director`, an intent naming a primary skill is **rolled through
  `challenge.attempt`** — assert the tally moved by one and the band
  advanced, which `table.check` alone cannot do.
* **The plant that matters** is the hazard above: make the resolver fall
  back to `one_beat`'s own roll and assert the challenge's tally **does not**
  move. If that stays green the hook is not wired and everything else is
  vacuous.
* **A second plant**: a group skill declared through the per-character
  resolver must still be refused.
* `replay` and `play` green; `audit --since` for the `story/` change, which
  is WIDE.

## Not in scope

* The chapter-1 challenge in `modules/` still has no phrasings, and that one
  is **Camille's** — it is her adventure, so the importer brief asks for
  them rather than my writing them in.
* A secondary's prose does not pitch the next primary, and there is no
  per-check register. Both are on #932's list and neither blocks the loop.

## Why this is a plan and not a commit

It touches `beat.py`, `challenge.py` and `run.py` together, and the part
that is easy to get wrong is invisible: a resolver wired to the wrong roller
produces a challenge that reads correctly, narrates well, and is scored by
rules nobody chose. That wants the plant written before the feature, which
is the order `scripts/CLAUDE.md` asks for and not the order a rushed change
takes.

---

## Landed, `1927924e`. All 29 instruments clean.

Every step of this plan is in, and three things it got wrong are worth
leaving on the record.

**Step 2 was already done.** The plan asked `challenge` for `start` and
`ended`; `open_challenge` and `run.over` already were those. What was
genuinely missing was the **router** -- `play` did the `group_of` test
inline -- so `challenge.resolve` is the one new function there, and it
exists so the automatic and narrated paths cannot disagree about which
door a skill goes through.

**The plan missed the phrasing gate.** `_narratable` has to require
`scene.tries` as well as a director. Without it, every converted challenge
-- all of them bare today -- would be narrated against a matcher measured
at **3 of 12**, with failures that stretch an intent onto the wrong skill.
The plan treated phrasings as a prerequisite that was already met and did
not notice they are met only for the fixture.

**And three of its specified plants could not be posed on the fixture.**
Each needed a board built:

* the `stop` hook -- a director naming one skill never finishes the
  challenge, so `max_beats` bounds the loop and the check is invisible. A
  **cycling** director resolves it in 3 beats of 6;
* the group router -- `Scene.group_of` answers `""` for every skill of
  every converted challenge, so the group skill is a
  `dataclasses.replace` copy rather than something read off the tree;
* the phrasing gate -- posed on a copy with `tries=()`.

## The four-round diagnosis, which is the transferable part

The wiring assertion read "0 declared lines" and I took it for the hook
not being called. It was the probe each time:

1. `control` held the class name; `Campaign.controls` reads anything
   unrecognised as `"human"`, so nobody declared;
2. `Director.joins` is a **model** call and gates who is asked at all;
3. `declare` and `react` are two more -- the first probe spent 58 seconds
   reaching for an ollama that was not serving;
4. and `Line.__new__` silently relabels a kind outside `KINDS` as
   `"scene"`, so 18 `"say"` lines existed under another name.

Four separate reasons a correct implementation reports as an unwired one.
The rule now asserts that every emitted kind is in `KINDS`, which would
have collapsed rounds 1-4 into one.

The `"say"` caption was also contradicting a documented decision:
`_roleplay` does not print a companion's declaration on purpose. Read the
convention before adding to it.

## Not done

The chapter-1 challenge in `modules/` has no phrasings and that one is
Camille's -- `#932` is tagged `question` for it. Until it has them the
adventure she plays runs the automatic path, so the loop is live and her
campaign has not changed.
