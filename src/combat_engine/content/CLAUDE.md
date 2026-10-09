# Content

677 modules of hand-written rows: what each power, monster ability, item
block, feat, class feature and racial power actually *does*. Written in the
engine's DSL; read numbers from `data/game.db`; never generated.

Global rules are in the root `CLAUDE.md`. **`docs/AUTHORING.md` is the
long-form reference and must be read before writing rows** — the `Cast`
surface, and a list of the things that are *silently false* and have each
cost somebody an hour. This file is the rules; that one is the why.

## The shape of a row

A decorated function. **The decorator header is data** — read by the UI and
the AI policy without running anything — and **the body is code** against a
`Cast` called `c`.

* The body runs **once per target**. `c.first` guards a once-per-power line.
* Almost every `Cast` method defaults to `c.target`, not `c.me`. If the
  sentence is about the character, pass `on=c.me`. This is the commonest
  single mistake here.
* A declared trigger must be `on=Trigger(event, predicate, text)`.
  `trigger="..."` **alone is prose the engine never reads** — the row will
  never fire.
* A row holds either a printed trigger **or** standing modifiers, not both:
  declared `on=`, the body runs only when the trigger fires, so modifiers
  laid there are never laid.

## Markers — six, and three of them take words

* `todo=(symbols,)` — nothing works. Refused in play.
* `dropped=(symbols,)` — plays, one named clause missing.
* `narrative=("skill:name",)` — finished; the clause has no combat meaning.
* `obsolete="why"` — **superseded by a rules change. Never offered, not waiting.**
  A reason in plain words, because there is no symbol to wait for. The other three
  could not say this: `todo=` means "nothing works yet", so `todo.py` reports the
  row ready the moment its symbol arrives — exactly wrong for a row nobody will
  ever want. Refused by `usable` and excluded from every chargen draw, so it
  reaches neither a player's list nor the dealer's.
  Requires a docstring saying why.
* `declined="why"` — **we are not building this.** Not unfinished, not
  superseded, not a gap in the source: a decision that the mechanism is out of
  scope. A reason in plain words, and **say whose call it was and when** — the
  next reader's question is "can this be revisited" and nothing else in the row
  answers it. Refused by `usable` and excluded from every chargen draw, exactly
  as `obsolete=` is.

  The other five all say something false here. `todo=` and `dropped=` name a
  symbol, so `todo.py` reports the row ready the moment that symbol lands —
  exactly wrong for a row nobody intends to finish. `narrative=` claims it
  plays. `defect=` blames the compendium, which has the page. `obsolete=` is
  the closest and is the one worth keeping clean: that row was retired by a
  *rules change*, and writing a scope decision into it would blur the single
  word carrying that argument.

  Does not count toward `blocked.py`, which reads `todo + dropped` — a
  declined row is not work owed, and needs no bucket of its own there.

  **The unit is the thing, not the row.** First use was the 11 Fortune Card
  rows (Camille's call, 2026-10-09, #482), and the instructive one is
  `i3333x1`: it prints only a +1 to Bluff and names no card at all, and it
  is declined anyway, because `i3333p1` is a Fortune Card power and a bonus
  on an item nobody can otherwise use is not worth keeping. Decline the
  item, not the lines that happen to mention it.

  So it is **not** the marker for "one clause of a working row is declined".
  That case was designed for, built in `blocked.py`, and removed when the
  call turned out to be item-level — if it comes back, the row keeps
  `dropped=` and the bucket comes back with it.
* `defect="why"` — **the compendium is missing what the row would be written
  from.** Not a gap in this engine: a gap in the source, so no symbol will ever
  close it and `todo=`/`dropped=` both lie by naming one. Refused by `usable`
  and excluded from every chargen draw, like `obsolete=`, and it **cannot** be
  combined with any other marker or with `out_of_combat`.

  **Only when nothing survives.** A blank defence on a row that never rolls that
  line still plays, and takes `dropped=` with the clause named. Of 26 rows with
  a blank attack defence, **23 play and 3 do not** — flagging all 26 would have
  refused 23 working rows.

  **On a monster it defects the whole stat block.** `loader.defective` derives
  it from the rows and `pick` stops offering the creature — a monster fielded
  without the ability its card is about is wrong in every fight. `todo=` and
  `dropped=` do not do this: those mean unfinished, not wrong.

  **You do not decide this yourself.** An authoring agent cannot read the
  compendium. Refer the garbled line up to the main session, which can, and
  which answers with what the page says or tells you to flag it. See
  `docs/AUTHORING.md`, "When you cannot *read* the card". #360.

Plus `out_of_combat=True` for a row that is complete and inert in a fight.

**Symbols only, never prose** — a sentence is refused at import. Reuse a
symbol already in the tree so the groups mean something:
`uv run scripts/blocked.py --group`.

**A marker names one gap.** A symbol doing duty for two different needs
cannot go red or green correctly for either: `c.ability_for(ref)` served
three, so twelve rows reported ready when a third of it landed. If two rows
wait on different things, they want different symbols.

**Check the verb does not already exist before marking**:
`grep -n "def verb" ../engine/cast.py` and `uv run scripts/vocab.py --brief`.
Most gaps filed here have turned out to exist under another name.

## Never be shown a name

You are never given a printed name or flavour text and must not go and find
one. Refs only. Not in a docstring, not in a comment, not in a variable, not
in a section header — two theme files leaked a feat's name through a comment
that merely *described* a power, inferred from its keywords.

Searching the web for **a mechanic you do not understand is encouraged**.
Searching for a name is not. Reading `game.db` for **numbers** is fine;
reading it for names is not.

## By subdirectory

**`monsters/`** — numbers load from the database and are never hand-written.
A stat block prints a finished total, so `Attack(vs=AC, printed=6)` says what
the page says and the engine takes the level back out according to
`world.scaling`. Damage goes in the header as data so MM3 rescaling works.

**`items/`** — an item is a base item with properties laid on top. **The unit
of work is a block** (`i601p1`, `i601x1`), not an item. An item Power is an
ordinary `@power` with `cls="item"`; an always-on Property is `action=NONE`.
Crit riders and enhancement are columns, not body code. `Level 11:` / `21:`
lines are out of scope and must not be marked `todo`.

**`feats/`** — a feat is usually a trait. `kind=` is the word the card prints
before "bonus" and nothing else. A prerequisite is a **column** enforced by
`chargen.meets`, never `Power.requires`. A power-granting feat is a pair
(`f959` / `f960b`) — the `b` suffix is the convention for a second card with
no ref of its own.

**`races/`** — `cls` holds a **race ref** (`r33`), not a class, for the same
reason a theme row holds `x7_642`: a printed name in that column is a leak.
A racial trait says its race in its own ref (`rt:r33-...`).

**`features/`** — class features, which no spec file lists. Distinct from
feats.

## Chargen has moved out

It used to live here as `chargen.py`. It is now
`src/combat_engine/chargen/`, its own package, because it is its own
component and six files *here* import it — which is the inversion that
argued for the move: content should be the thing chargen deals, not the
other way round.

What that means for you: `from combat_engine.chargen import LIGHT` rather
than `from combat_engine.content.chargen import LIGHT`. Six files in this
tree do that, all for a constant.

A prerequisite is still enforced by `chargen.meets` and is still not yours
to write — see above.

## Checking

Your own refs, by name:

```
uv run scripts/lint.py <your file>
uv run scripts/audit.py <your refs>
uv run scripts/show.py <ref>       printed text beside emitted events
```

Not `--monsters`, not `--class`, not `check.py`.

**Who you are changes two rules.** A parallel content agent lints **only its
own file** — a tree-wide `ruff --fix` has destroyed another agent's work —
and never touches git. The main session lints the tree and commits.

`lint.py` takes paths for exactly that reason, and **it did not until #388**:
this file said "only its own file" and named a command that walked all 776 of
them, so the one tool the rule offered did the one thing the rule forbids. Four
waves in a single round each had to pick their own faults out of a tree-wide
report. With no argument it still lints everything, which is what `check.py`
wants.

Running it tree-wide while other agents are writing is its own trap: the walk
sees whatever half-finished state they are in. One wave reported a tree-wide
blocker that the owning agent had already fixed by the time anyone looked.

`audit` reporting `ok` is weaker than it looks for a row hanging clauses on
a `Hit`: it once credited the harness's own provocation to the row. Fixed,
but if a row's verdict matters, prove it with a positive **and** a negative
control.
